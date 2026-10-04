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


def setup_module():
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        seed(session)


def teardown_module():
    engine.dispose()
    _temp.cleanup()


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
        before = session.scalar(select(func.count()).select_from(Item).where(Item.published_at >= now - timedelta(hours=24))) or 0
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
        assert company_search["total"] == 1
        assert company_search["results"][0]["url"] == "https://example.org/together-role"
