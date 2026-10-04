import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

_temp = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_temp.name) / 'test.db'}"

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.ingest import canonical_url, insert_item, upsert_source  # noqa: E402
from app import ingest  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Source  # noqa: E402
from app.seed import seed  # noqa: E402
from app.sources import sync_defaults  # noqa: E402
from sqlalchemy import select  # noqa: E402


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
        assert sync_defaults(session) == 6
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
