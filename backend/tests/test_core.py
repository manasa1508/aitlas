import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

_temp = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_temp.name) / 'test.db'}"

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.ingest import canonical_url, insert_item, upsert_source  # noqa: E402
from app import ingest  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Item, Source  # noqa: E402
from app.seed import seed  # noqa: E402
from app.sources import sync_defaults  # noqa: E402
from app.sources import DEFAULTS  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
import json  # noqa: E402


def pinpoint_posting(identifier="one", location="India - Hyderabad"):
    return {"id": identifier, "title": "Machine Learning Engineer", "url": f"https://careers.dazn.com/en/postings/{identifier}", "description": "Develop inference systems", "job": {"department": {"name": "Engineering"}}, "location": {"name": location}, "employment_type_text": "Permanent", "workplace_type_text": "Hybrid"}


def setup_module():
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        seed(session)
        from app.employers import sync_employer_defaults
        sync_employer_defaults(session)


def teardown_module():
    engine.dispose()
    _temp.cleanup()


def test_pinpoint_filters_and_first_seen_dates():
    import httpx
    payload = {"data": [pinpoint_posting(), pinpoint_posting("london", "London"), pinpoint_posting("pakistan", "Hyderabad, Sindh, Pakistan")]}
    with SessionLocal() as session, httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))) as client:
        source = upsert_source(session, "pinpoint-test", "DAZN test", "https://careers.dazn.com/postings.json", "pinpoint_jobs")
        source.options = {"company": "Daznprobe", "target_cities_only": True}
        assert ingest.ingest_pinpoint_jobs(session, client, source) == 1
        session.commit()
        row = session.scalar(select(Item).where(Item.source_id == source.id))
        first_seen = row.published_at
        assert row.details["date_basis"] == "first_seen"
        assert row.details["ai_related"] is True
        assert row.details["workplace_type"] == "Hybrid"
        assert ingest.ingest_pinpoint_jobs(session, client, source) == 0
        assert row.published_at == first_seen
    with TestClient(app) as client:
        assert client.get("/api/items", params={"kind":"job", "city":"hyderabad", "company":"Daznprobe", "ai_only":True}).json()["total"] == 1


def test_pinpoint_malformed_snapshots_preserve_jobs_and_complete_misses_expire():
    import httpx
    import pytest
    with SessionLocal() as session:
        source = upsert_source(session, "pinpoint-protect", "Pinpoint protect", "https://careers.dazn.com/postings.json", "pinpoint_jobs")
        with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"data": [pinpoint_posting("existing")]}))) as client:
            ingest.ingest_pinpoint_jobs(session, client, source)
        session.commit()
        row = session.scalar(select(Item).where(Item.source_id == source.id))
        checked = row.details["last_checked_at"]
        malformed = [None, {}, {"data": {}}, {"data": [], "links": {"next": "/page2"}}, {"data": [], "meta": {"total": 2}}, {"data": [], "errors": ["unavailable"]}, {"data": [pinpoint_posting("dup"), pinpoint_posting("dup")]}, {"data": [pinpoint_posting("new"), {**pinpoint_posting("bad"), "location": None}]}, {"data": [{**pinpoint_posting("evil"), "url":"https://careers.dazn.com.evil.example/en/postings/evil"}]}]
        for payload in malformed:
            with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))) as client, pytest.raises(ValueError):
                ingest.ingest_pinpoint_jobs(session, client, source)
            assert row.active and row.details["misses"] == 0
            assert row.details["last_checked_at"] == checked
            assert session.scalar(select(func.count()).select_from(Item).where(Item.source_id == source.id)) == 1
        with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"data": []}))) as client:
            ingest.ingest_pinpoint_jobs(session, client, source)
            assert row.active
            ingest.ingest_pinpoint_jobs(session, client, source)
            assert not row.active


def test_pinpoint_source_validation_and_public_board_links():
    import pytest
    from app.sources import validate_source
    from app.jobs import job_board_url
    for endpoint in ("https://careers.dazn.com/postings.json", "https://example.pinpointhq.com/postings.json"):
        validate_source("pinpoint_jobs", endpoint, 120, {})
        assert job_board_url(Source(kind="pinpoint_jobs", url=endpoint)) == endpoint.removesuffix("/postings.json")
    for endpoint in ("https://careers.dazn.com.evil.example/postings.json", "https://unknown.example/postings.json", "https://example.pinpointhq.com/jobs.json", "https://example.pinpointhq.com/postings.json?location_id=1", "https://example.pinpointhq.com:8443/postings.json"):
        with pytest.raises(ValueError):
            validate_source("pinpoint_jobs", endpoint, 120, {})
    assert job_board_url(Source(kind="lever_jobs",url="https://api.eu.lever.co/v0/postings/example")) == "https://jobs.eu.lever.co/example"
    assert job_board_url(Source(kind="smartrecruiters",url="https://api.smartrecruiters.com/v1/companies/Example/postings")) == "https://jobs.smartrecruiters.com/Example"
    assert job_board_url(Source(kind="greenhouse_jobs",url="https://boards-api.greenhouse.io/v1/boards/example/jobs")) == "https://job-boards.greenhouse.io/example"


def test_company_directory_discovery_evidence_is_not_ratings_or_job_data():
    from app.intelligence import config, employer_directory
    data = config()
    references = {row["id"]:row for row in data["employer_discovery_sources"]}
    assert len(references) == len(data["employer_discovery_sources"])
    assert len({row["url"] for row in references.values()}) == len(references)
    assert references["ambitionbox"]["status"] == "unavailable"
    for name, profile in data["employer_profiles"].items():
        assert all(references[key]["status"] == "reviewed" for key in profile.get("discovery_source_ids", []))
        assert not {"rating", "salary", "headcount"}.intersection(profile)
    assert "flexiple" in data["employer_profiles"]["Backbase"]["discovery_source_ids"]
    assert "kas" in data["employer_profiles"]["Amgen"]["discovery_source_ids"]
    with SessionLocal() as session:
        directory = employer_directory(session)
        amgen = next(row for row in directory["employers"] if row["name"] == "Amgen")
        assert amgen["coverage"] == "official_link" and amgen["open_roles"] is None
        assert amgen["discovery_sources"]
        assert all(ref["id"] != "ambitionbox" for row in directory["employers"] for ref in row["discovery_sources"])


def test_knowledge_and_grounded_ask():
    with TestClient(app) as client:
        history = client.get("/api/knowledge")
        assert history.status_code == 200
        assert any(row["id"] == "transformer-2017" for row in history.json())
        answer = client.post("/api/ask", json={"question": "What is retrieval augmented generation?"})
        assert answer.status_code == 200
        data = answer.json()
        assert data["mode"] == "extractive"
        assert any(c["url"].startswith("https://arxiv.org/") for c in data["citations"])
        assert "[1]" in data["answer"]


def test_canonical_dedup_and_bad_links():
    assert canonical_url("javascript:alert(1)") is None
    assert canonical_url("https://example.org/ai/?utm_source=test&x=1") == "https://example.org/ai?x=1"
    with SessionLocal() as session:
        upsert_source(session, "test", "Test", "https://example.org/feed", "rss")
        now = datetime.now(timezone.utc)
        first = insert_item(session, kind="news", title="New transformer model research", summary="An LLM system", url="https://example.org/ai?utm_source=test", source_id="test", published_at=now)
        duplicate = insert_item(session, kind="news", title="New transformer model research", summary="An LLM system", url="https://example.org/ai?utm_medium=email", source_id="test", published_at=now)
        near_duplicate = insert_item(session, kind="news", title="New transformer model research", summary="An LLM system", url="https://another.example.org/ai", source_id="test", published_at=now)
        session.commit()
        assert first is True
        assert duplicate is False
        assert near_duplicate is False


def test_empty_and_missing_context():
    with TestClient(app) as client:
        assert client.get("/api/context/missing").status_code == 404
        invalid = client.post("/api/ask", json={"question": "x"})
        assert invalid.status_code == 422


def test_dynamic_source_scheduling_and_backoff(monkeypatch):
    with SessionLocal() as session:
        assert sync_defaults(session) == len(json.loads(DEFAULTS.read_text()))
        assert sync_defaults(session) == 0
        for source in session.scalars(select(Source)).all():
            source.enabled = source.id == "hacker-news"
        session.commit()

        monkeypatch.setattr(ingest, "ingest_hn", lambda *_: 2)
        first = ingest.run_ingestion(session)
        assert first and first.inserted == 2
        source = session.get(Source, "hacker-news")
        assert source.next_fetch_at is not None
        assert ingest.run_ingestion(session) is None

        def fail(*_):
            raise ValueError("temporary source failure")

        monkeypatch.setattr(ingest, "ingest_hn", fail)
        second = ingest.run_ingestion(session, force=True)
        assert second and second.status == "partial"
        session.refresh(source)
        assert source.failure_count == 1
        assert "temporary source failure" in source.last_error


def test_github_token_is_only_sent_to_github_api(monkeypatch):
    import httpx

    seen = []

    def respond(request):
        seen.append((str(request.url), request.headers.get("Authorization")))
        return httpx.Response(200, text="ok")

    monkeypatch.setattr(ingest.settings, "github_token", "test-token")
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        ingest.get_with_retry(client, "https://example.org/feed")
        ingest.get_with_retry(client, "https://api.github.com/search/repositories")
        ingest.get_with_retry(client, "https://api.github.com.evil.example/feed")
    assert seen == [
        ("https://example.org/feed", None),
        ("https://api.github.com/search/repositories", "Bearer test-token"),
        ("https://api.github.com.evil.example/feed", None),
    ]


def test_daily_brief_counts_beyond_first_page():
    now = datetime.now(timezone.utc)
    with SessionLocal() as session:
        upsert_source(session, "bulk", "Bulk test", "https://example.org/feed", "rss")
        before = session.scalar(select(func.count()).select_from(Item).where(Item.published_at >= now - timedelta(hours=24), Item.kind.in_(("news", "paper", "repo", "model")))) or 0
        session.add_all(Item(kind="news", title=f"AI news item {i}", summary="Test item", url=f"https://example.org/bulk/{i}", source_id="bulk", published_at=now, tags=["Research"], score=50, title_fingerprint=f"bulk {i}") for i in range(121))
        session.commit()
    with TestClient(app) as client:
        brief = client.get("/api/overview").json()["brief"]
        assert brief["window"] == "last 24 hours"
        assert brief["count"] == before + 121


def test_job_board_expiry_needs_two_complete_misses():
    import httpx

    jobs = [{"id": 123, "internal_job_id": 456, "title": "Machine Learning Engineer", "absolute_url": "https://job-boards.greenhouse.io/example/jobs/123", "location": {"name": "Remote"}, "first_published": "2026-10-01T00:00:00Z", "content": "Build models"}]
    def respond(_):
        return httpx.Response(200, json={"jobs": jobs})

    with SessionLocal() as session, httpx.Client(transport=httpx.MockTransport(respond)) as client:
        source = upsert_source(session, "test-jobs", "Test jobs", "https://boards-api.greenhouse.io/v1/boards/example/jobs", "greenhouse_jobs")
        source.options = {"company": "Example AI"}
        assert ingest.ingest_greenhouse_jobs(session, client, source) == 1
        session.commit()
        row = session.scalar(select(Item).where(Item.kind == "job", Item.source_id == source.id))
        assert row.active and row.details["location"] == "Remote"
        jobs.clear()
        ingest.ingest_greenhouse_jobs(session, client, source)
        session.commit()
        assert row.active
        ingest.ingest_greenhouse_jobs(session, client, source)
        session.commit()
        assert not row.active


def test_trending_model_is_source_labeled():
    import httpx

    payload = [{"id": "example/model-one", "downloads": 120, "likes": 10, "trendingScore": 99, "pipeline_tag": "text-generation", "tags": ["license:apache-2.0"], "createdAt": "2026-10-01T00:00:00Z"}]
    with SessionLocal() as session, httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))) as client:
        source = upsert_source(session, "test-models", "Models", "https://huggingface.co/api/models", "hf_models")
        assert ingest.ingest_hf_models(session, client, source) == 1
        session.commit()
        row = session.scalar(select(Item).where(Item.kind == "model", Item.source_id == source.id))
        assert row.details["license"] == "apache-2.0"
        assert row.details["trending_rank"] == 1


def test_search_reaches_deep_active_catalog():
    now = datetime.now(timezone.utc)
    with SessionLocal() as session:
        upsert_source(session, "deep-search", "Deep search", "https://example.org/feed", "rss")
        session.add_all(Item(kind="job", title=f"Atlas Engineer {i}", summary="Develop AI systems", url=f"https://example.org/atlas-job/{i}", source_id="deep-search", published_at=now, tags=["Engineering"], details={"company": "Example", "location": "Remote", "role": "Engineering", "audience": "developer"}, active=True, score=50, title_fingerprint=f"atlas engineer {i}") for i in range(510))
        session.add(Item(kind="job", title="Research role", summary="Build AI systems", url="https://example.org/together-role", source_id="deep-search", published_at=now, tags=["Research"], details={"company": "Together AI", "location": "Remote", "role": "Research & AI", "audience": "developer"}, active=True, score=50, title_fingerprint="together role"))
        session.commit()
    with TestClient(app) as client:
        data = client.get("/api/search", params={"q": "Atlas", "offset": 500, "limit": 10}).json()
        assert data["total"] >= 510
        assert len(data["results"]) == 10
        assert all(row["type"] == "job" for row in data["results"])
        assert all(row["kind"] != "job" for row in client.get("/api/items", params={"limit": 100}).json()["items"])
        assert client.get("/api/items", params={"kind": "job", "role": "Engineering"}).json()["total"] >= 510
        company_search = client.get("/api/search", params={"q": "Together AI"}).json()
        assert any(row["type"] == "job" and row["url"] == "https://example.org/together-role" for row in company_search["results"])


def test_latest_answer_respects_time_and_excludes_jobs():
    now = datetime.now(timezone.utc)
    with SessionLocal() as session:
        source = upsert_source(session, "recency", "Recency source", "https://example.org/recent", "rss")
        source.last_success_at = now
        for key, kind, age, title in [("new", "news", 1, "Recencyprobe AI release"), ("old", "news", 240, "Recencyprobe latest AI news today"), ("job", "job", 0, "Recencyprobe AI Engineer")]:
            session.add(Item(kind=kind, title=title, summary="Recencyprobe AI", url=f"https://example.org/recency/{key}", source_id=source.id, published_at=now-timedelta(hours=age), tags=["AI"], score=80, title_fingerprint=key))
        session.commit()
    with TestClient(app) as client:
        data = client.post("/api/ask", json={"question": "What are the latest Recencyprobe AI developments today?"}).json()
        assert len(data["citations"]) == 1
        assert data["citations"][0]["type"] == "news"
        assert "release" in data["citations"][0]["title"]
        assert "last 24 hours" in data["answer"]
        assert "no live web search" in data["answer"]
        missing = client.post("/api/ask", json={"question": "Latest nonexistenttopicprobe news?"}).json()
        assert missing["mode"] == "no_match"
        assert "does not mean no developments" in missing["answer"]


def test_model_rank_is_cleared_after_leaving_current_list():
    import httpx
    payload = [{"id": "test/first", "createdAt": datetime.now(timezone.utc).isoformat()}]
    with SessionLocal() as session, httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))) as client:
        source = upsert_source(session, "rank-expiry", "Rank expiry", "https://huggingface.co/api/models", "hf_models")
        ingest.ingest_hf_models(session, client, source)
        session.commit()
        payload[:] = [{"id": "test/second", "createdAt": datetime.now(timezone.utc).isoformat()}]
        ingest.ingest_hf_models(session, client, source)
        session.commit()
        old = session.scalar(select(Item).where(Item.url == "https://huggingface.co/test/first"))
        assert old.details["trending_rank"] is None
    with TestClient(app) as client:
        current = client.get("/api/items", params={"kind":"model", "sort":"trending", "q":"test/first"}).json()
        assert current["total"] == 0


def test_city_and_ai_filters_use_role_not_company_boilerplate():
    from app.jobs import ai_related, target_location
    assert target_location("Bangalore, India") and target_location("Bengaluru")
    assert not target_location("Hyderabad, Sindh, Pakistan")
    assert ai_related("Machine Learning Engineer")
    assert not ai_related("Payroll Manager", "Finance")
    with SessionLocal() as session:
        source = upsert_source(session, "city-test", "City test", "https://example.org/jobs", "greenhouse_jobs")
        for i, (location, ai) in enumerate([("Bangalore, India", True), ("Hyderabad, India", False), ("London, UK", True), ("Pune, India", True), ("Chennai, India", True)]):
            session.add(Item(kind="job", title=f"Cityprobe Engineer {i}", summary="We are an AI company", url=f"https://example.org/city/{i}", source_id=source.id, published_at=datetime.now(timezone.utc), details={"company":"Cityprobe", "location":location, "ai_related":ai, "role":"Engineering"}, title_fingerprint=f"city {i}"))
        session.commit()
    with TestClient(app) as client:
        rows = client.get("/api/items", params={"kind":"job","city":"target","ai_only":True,"company":"Cityprobe","role":"Engineering"}).json()
        assert rows["total"] == 3
        assert client.get("/api/items",params={"kind":"job","city":"bengaluru","company":"Cityprobe"}).json()["total"] == 1


def test_smartrecruiters_partial_snapshot_never_expires_jobs():
    import httpx
    import pytest
    data = {"totalFound":2,"content":[{"id":"one","name":"AI Engineer","releasedDate":"2026-10-01T00:00:00Z","location":{"city":"Pune","country":"in"}}]}
    def respond(request):
        assert request.url.params["destination"] == "PUBLIC"
        assert request.url.params["country"] == "in"
        return httpx.Response(200,json=data if request.url.params["offset"] == "0" else {"totalFound":2,"content":[]})
    with SessionLocal() as session, httpx.Client(transport=httpx.MockTransport(respond)) as client:
        source = upsert_source(session,"smart-test","Smart test","https://api.smartrecruiters.com/v1/companies/Example/postings","smartrecruiters")
        with pytest.raises(ValueError,match="Incomplete"):
            ingest.ingest_smartrecruiters(session,client,source)
        assert session.scalar(select(func.count()).select_from(Item).where(Item.source_id==source.id)) == 0


def test_lever_pagination_locations_and_date_provenance():
    import httpx
    calls = []
    def respond(request):
        offset = int(request.url.params["skip"])
        calls.append(offset)
        assert request.url.params["mode"] == "json"
        return httpx.Response(200, json=[{"id": str(i), "text": "Machine Learning Engineer", "hostedUrl": f"https://jobs.lever.co/pagination/{i}", "createdAt": 1790812800000 if i else None, "categories": {"location": "London", "allLocations": ["London", "Bengaluru, India"], "department": "AI", "commitment": "Full-time"}} for i in range(offset, min(offset + 100, 101))])
    with SessionLocal() as session, httpx.Client(transport=httpx.MockTransport(respond)) as client:
        source = upsert_source(session, "lever-pages", "Lever pages", "https://api.lever.co/v0/postings/pagination", "lever_jobs")
        source.options = {"company": "Paginationprobe", "target_cities_only": True}
        assert ingest.ingest_lever_jobs(session, client, source) == 101
        assert calls == [0, 100]
        session.commit()
        row = session.scalar(select(Item).where(Item.url == "https://jobs.lever.co/pagination/0"))
        first_seen = row.published_at
        assert row.details["date_basis"] == "first_seen"
        assert row.details["ai_related"] is True
        assert row.details["last_checked_at"]
        assert row.details["employment_type"] == "Full-time"
        assert "Bengaluru" in row.details["location"]
        assert ingest.ingest_lever_jobs(session, client, source) == 0
        assert row.published_at == first_seen
    with TestClient(app) as client:
        assert client.get("/api/items", params={"kind": "job", "city": "bengaluru", "company": "Paginationprobe", "ai_only": True}).json()["total"] == 101


def test_lever_repeated_or_failed_pages_preserve_existing_jobs():
    import httpx
    import pytest
    posting = lambda i: {"id": str(i), "text": "Software Engineer", "hostedUrl": f"https://jobs.lever.co/protect/{i}", "categories": {"location": "Pune"}}
    with SessionLocal() as session:
        source = upsert_source(session, "lever-protect", "Lever protect", "https://api.lever.co/v0/postings/protect", "lever_jobs")
        with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[posting("existing")]))) as client:
            ingest.ingest_lever_jobs(session, client, source)
        session.commit()
        row = session.scalar(select(Item).where(Item.source_id == source.id))
        original_checked = row.details["last_checked_at"]
        for failure in ("repeated", "http"):
            def respond(request):
                if request.url.params["skip"] == "0":
                    return httpx.Response(200, json=[posting(i) for i in range(100)])
                return httpx.Response(200, json=[posting(0)]) if failure == "repeated" else httpx.Response(403)
            with httpx.Client(transport=httpx.MockTransport(respond)) as client, pytest.raises((ValueError, httpx.HTTPStatusError)):
                ingest.ingest_lever_jobs(session, client, source)
            assert row.active and row.details["misses"] == 0
            assert row.details["last_checked_at"] == original_checked
            assert session.scalar(select(func.count()).select_from(Item).where(Item.source_id == source.id)) == 1


def test_lever_eu_validation_and_successful_expiry():
    import httpx
    import pytest
    from app.sources import validate_source
    endpoint = "https://api.eu.lever.co/v0/postings/example"
    validate_source("lever_jobs", endpoint, 120, {})
    for invalid in ("https://api.lever.co.evil.example/v0/postings/example", "https://api.lever.co/private/example"):
        with pytest.raises(ValueError):
            validate_source("lever_jobs", invalid, 120, {})
    payload = [{"id": "eu", "text": "Software Engineer", "hostedUrl": "https://jobs.eu.lever.co/example/eu", "categories": {"location": "Chennai"}}]
    with SessionLocal() as session, httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))) as client:
        source = upsert_source(session, "lever-eu", "Lever EU", endpoint, "lever_jobs")
        ingest.ingest_lever_jobs(session, client, source)
        session.commit()
        row = session.scalar(select(Item).where(Item.source_id == source.id))
        payload[0]["hostedUrl"] = "https://jobs.eu.lever.co.evil.example/example/eu"
        with pytest.raises(ValueError, match="Invalid public"):
            ingest.ingest_lever_jobs(session, client, source)
        assert row.details["misses"] == 0
        payload.clear()
        ingest.ingest_lever_jobs(session, client, source)
        assert row.active and row.details["misses"] == 1
        ingest.ingest_lever_jobs(session, client, source)
        assert not row.active


def test_external_job_searches_preserve_city_keywords_and_scope():
    from urllib.parse import parse_qs, urlparse
    with TestClient(app) as client:
        data = client.get("/api/job-search-links", params={"city": "hyderabad", "q": "R&D / C++", "ai_only": True}).json()
        assert len(data["searches"]) == 1
        assert "not downloaded or indexed" in data["coverage"]
        links = {row["name"]: row["url"] for row in data["searches"][0]["links"]}
        linkedin = parse_qs(urlparse(links["LinkedIn"]).query)
        assert linkedin["keywords"] == ["R&D / C++ AI"]
        assert linkedin["location"] == ["Hyderabad, Telangana, India"]
        assert len(client.get("/api/job-search-links", params={"city": "all"}).json()["searches"]) == 4
        assert client.get("/api/job-search-links", params={"city": "invalid"}).status_code == 422


def test_employer_directory_counts_combine_filters_and_disclose_coverage():
    from app.intelligence import employer_directory
    with SessionLocal() as session:
        source = session.get(Source, "city-test")
        source.enabled = True
        source.options = {"company": "Cityprobe"}
        data = employer_directory(session, "bengaluru", True, "Engineering")
        employer = next(row for row in data["employers"] if row["name"] == "Cityprobe")
        assert employer["open_roles"] == 1
        assert employer["coverage"] == "public_feed"
        assert data["coverage_summary"]["career_links_only"] >= 40
        assert employer_directory(session, "bengaluru", True, "Business & operations")["coverage_summary"]["matching_roles"] == 0
        assert "ratings are not connected" in data["rating_status"]
        for row in data["employers"]:
            if row["coverage"] == "official_link":
                assert row["open_roles"] is None
            for recognition in row.get("recognitions", []):
                assert recognition["source_url"].startswith("https://") and recognition["year"]


def test_daily_papers_updates_legacy_arxiv_record_and_attention():
    import httpx
    with SessionLocal() as session:
        source=upsert_source(session,"daily-test","Daily test","https://huggingface.co/api/daily_papers","hf_papers")
        session.add(Item(kind="paper",title="Attentionprobe research paper",summary="AI research",url="http://arxiv.org/abs/2610.99999v1",source_id=source.id,published_at=datetime.now(timezone.utc),title_fingerprint="attention probe"))
        session.commit()
        payload=[{"paper":{"id":"2610.99999","title":"Attentionprobe research paper","upvotes":20}}]
        with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json=payload))) as client:
            ingest.ingest_hf_papers(session,client,source)
        session.commit()
    with TestClient(app) as client:
        data=client.get("/api/items",params={"kind":"paper","attention":"popular","q":"Attentionprobe"}).json()
        assert data["total"] == 1
        assert data["items"][0]["details"]["upvotes"] == 20
        assert data["items"][0]["url"] == "https://arxiv.org/abs/2610.99999"


def test_source_staleness_and_intelligence_boundaries():
    from app.main import source_health
    with SessionLocal() as session:
        source=upsert_source(session,"stale-test","Stale test","https://example.org/stale","rss")
        source.enabled=True
        source.last_success_at=datetime.now(timezone.utc)-timedelta(days=2)
        assert source_health(source) == "stale"
        source.last_error="request failed"
        assert source_health(source) == "error"
        source.enabled=False
        assert source_health(source) == "paused"
        session.commit()
    with TestClient(app) as client:
        data=client.get("/api/intelligence").json()
        assert "not global popularity" in data["methodology"]
        assert all(row["quote_status"] == "not_connected" for row in data["markets"])
        assert "rating" in client.get("/api/employers").json()["rating_status"]
        assert all(item["kind"] != "job" for item in client.get("/api/overview").json()["latest"])


def test_bounded_fetch_decodes_compressed_feed_once():
    import gzip
    import httpx
    body = b"<rss><channel><title>AI feed</title></channel></rss>"
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,content=gzip.compress(body),headers={"Content-Encoding":"gzip"}))) as client:
        response=ingest.get_with_retry(client,"https://example.org/compressed")
        assert response.content == body


def test_relevance_matches_ai_without_substring_noise():
    with SessionLocal() as session:
        source=upsert_source(session,"relevance-test","General feed","https://example.org/relevance","rss")
        assert ingest.relevant("AI raises new questions", "Industry developments",source)
        assert ingest.relevant("RAG architecture", "New retrieval research",source)
        assert not ingest.relevant("Storage fragmentation tips", "Pragmatic computing",source)


def test_natural_trend_and_repository_questions():
    now=datetime.now(timezone.utc)
    with SessionLocal() as session:
        source=upsert_source(session,"repo-intent","Repo intent","https://api.github.com/search/repositories","github_repos")
        session.add(Item(kind="repo",title="intentprobe/popular",summary="AI tools",url="https://github.com/intentprobe/popular",source_id=source.id,published_at=now,details={"stars":100,"created_at":now.isoformat()},title_fingerprint="intentprobe popular"))
        session.commit()
    with TestClient(app) as client:
        trends=client.post("/api/ask",json={"question":"What are the latest AI trends?"}).json()
        assert trends["mode"] == "extractive"
        assert all(c["type"] != "job" for c in trends["citations"])
        repos=client.post("/api/ask",json={"question":"What are the top new GitHub repos?"}).json()
        assert repos["citations"]
        assert all(c["type"] == "repo" for c in repos["citations"])
        news=client.post("/api/ask",json={"question":"What is the latest AI technology news?"}).json()
        assert news["citations"]
        assert all(c["type"] == "news" for c in news["citations"])


def test_us500_parser_requires_complete_company_table():
    import pytest
    from app.employers import parse_us500
    table = '<table><tr><th>Rank</th><th>Company</th><th>Revenue</th></tr><tr><td>1</td><td>Example &amp; Co</td><td>999</td></tr><tr><td>2</td><td>Another Company</td><td>888</td></tr></table>'
    assert parse_us500(table, min_rows=2) == [{"name":"Example & Co"}, {"name":"Another Company"}]
    for invalid in (table.removesuffix('</table>'), table.replace('<td>2</td>', '<td>3</td>'), table.replace('Another Company', 'Example &amp; Co'), '<p>Too many requests</p>'):
        with pytest.raises(ValueError):
            parse_us500(invalid, min_rows=2)
    with pytest.raises(ValueError):
        parse_us500(table, min_rows=2, previous_size=10)


def test_catalog_discovery_persists_new_companies_without_enabling_job_feeds():
    from app.employers import sync_catalog_snapshot, name_key
    from app.models import Employer
    with SessionLocal() as session:
        source = upsert_source(session, 'catalog-dynamic-test', 'Catalog test', 'https://us500.com/fortune-500-companies', 'employer_catalog')
        source.options = {'reference_id':'catalog-test'}
        before_sources = session.scalar(select(func.count()).select_from(Source))
        original = session.scalar(select(Employer).where(Employer.name_key == name_key('IBM')))
        assert sync_catalog_snapshot(session, source, [{'name':'International Business Machines'}, {'name':'Discoveryprobe New Company'}]) == 1
        session.commit()
        assert session.scalar(select(func.count()).select_from(Source)) == before_sources
        assert session.scalar(select(Employer).where(Employer.name_key == name_key('IBM'))).id == original.id
        row = session.scalar(select(Employer).where(Employer.name_key == name_key('Discoveryprobe New Company')))
        assert row.careers_url is None and row.active
        assert row.references[0]['id'] == 'catalog-test'
        assert sync_catalog_snapshot(session, source, [{'name':'Discoveryprobe New Company'}, {'name':'Dynamicprobe Added Later'}]) == 1
        session.commit()
    with TestClient(app) as client:
        data = client.get('/api/employers').json()
        row = next(row for row in data['employers'] if row['name'] == 'Dynamicprobe Added Later')
        assert row['coverage'] == 'discovery_only' and row['open_roles'] is None and row['url'] is None
        assert row['discovery_sources'][0]['id'] == 'catalog-test'
        search = client.get('/api/search', params={'q':'Dynamicprobe Added Later'}).json()
        assert any(row['type'] == 'employer' and 'unverified' in row['snippet'] for row in search['results'])


def test_catalog_withdrawal_never_retires_jobs_and_preserves_manual_records():
    import pytest
    from app.employers import sync_catalog_snapshot, name_key
    from app.models import Employer
    with SessionLocal() as session:
        source = upsert_source(session, 'catalog-withdraw', 'Catalog withdraw', 'https://us500.com/fortune-500-companies', 'employer_catalog')
        source.options = {'reference_id':'catalog-withdraw'}
        sync_catalog_snapshot(session, source, [{'name':'Microsoft'}, {'name':'Withdrawprobe Company'}])
        session.add(Item(kind='job', title='Withdrawprobe AI Engineer', summary='Public test job', url='https://example.org/catalog-job', source_id=source.id, published_at=datetime.now(timezone.utc), active=True, title_fingerprint='withdrawprobe'))
        session.commit()
        row = session.scalar(select(Employer).where(Employer.name_key == name_key('Withdrawprobe Company')))
        with pytest.raises(ValueError):
            sync_catalog_snapshot(session, source, [{'name':'Invalidprobe'}, {'unexpected':'field'}])
        assert row.references[0]['misses'] == 0
        for _ in range(2):
            sync_catalog_snapshot(session, source, [{'name':'Keepaliveprobe Company'}])
        assert row.active is False
        assert session.get(Employer, row.id) is row
        assert session.scalar(select(Employer).where(Employer.name_key == 'microsoft')).active
        assert session.scalar(select(Item).where(Item.url == 'https://example.org/catalog-job')).active
        with pytest.raises(ValueError, match='older'):
            sync_catalog_snapshot(session, source, [{'name':'Oldprobe Company'}], observed_at=datetime.now(timezone.utc)-timedelta(days=1))


def test_employer_defaults_preserve_database_edits():
    from app.employers import sync_employer_defaults
    from app.models import Employer
    with SessionLocal() as session:
        row = session.scalar(select(Employer).where(Employer.name_key == 'amgen'))
        row.careers_url = 'https://careers.amgen.com/en'
        row.profile = {**row.profile, 'category':'Operator reviewed category'}
        session.commit()
        sync_employer_defaults(session)
        assert row.profile['category'] == 'Operator reviewed category'
        assert row.careers_url == 'https://careers.amgen.com/en'


def test_rate_limits_use_persistent_retry_after_and_keep_catalog():
    import httpx
    import pytest
    calls = []
    def respond(request):
        calls.append(str(request.url))
        return httpx.Response(429, headers={'Retry-After':'7200'})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client, pytest.raises(httpx.HTTPStatusError):
        ingest.get_with_retry(client, 'https://us500.com/fortune-500-companies')
    assert len(calls) == 1
    from unittest.mock import patch
    def fail(*args):
        raise httpx.HTTPStatusError('rate limited', request=httpx.Request('GET','https://us500.com/fortune-500-companies'), response=httpx.Response(429,headers={'Retry-After':'7200'}))
    with SessionLocal() as session:
        for row in session.scalars(select(Source)).all():
            row.enabled = row.id == 'catalog-dynamic-test'
        source = session.get(Source, 'catalog-dynamic-test')
        source.last_success_at = datetime.now(timezone.utc)-timedelta(hours=1)
        success = source.last_success_at
        session.commit()
        with patch.object(ingest, 'ingest_employer_catalog', fail):
            run = ingest.run_ingestion(session, force=True)
        assert run.status == 'partial'
        assert source.next_fetch_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc)+timedelta(minutes=119)
        assert source.last_success_at.replace(tzinfo=timezone.utc) == success
