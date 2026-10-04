"""Bounded, idempotent ingestion of public feeds and APIs."""
import html
import base64
import logging
import re
import ssl
import time
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import feedparser
import httpx
import truststore
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import settings, utcnow
from .models import Item, JobRun, Source

LOG = logging.getLogger(__name__)

AI_TERMS = {
    "artificial intelligence", "machine learning", "generative ai", "language model", "llm",
    "transformer", "deep learning", "neural", "ai agent", "agentic", "open source model",
    "copilot", "inference", "fine-tuning", "rag", "embedding", "robotics", "diffusion",
    "pytorch", "hugging face", "model weights", "ai safety", "ai research", "multimodal",
}


def clean_text(value: str, limit: int = 700) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit].rstrip()


def canonical_url(value: str) -> str | None:
    try:
        parsed = urlparse(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return None
        query = urlencode([(k, v) for k, v in parse_qsl(parsed.query) if not k.lower().startswith("utm_") and k.lower() not in {"ref", "source", "fbclid", "gclid"}])
        return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/") or "/", "", query, ""))
    except ValueError:
        return None


def fingerprint(title: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", title.lower()))[:300]


def parse_date(value: str | None) -> datetime:
    if not value:
        return utcnow()
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return utcnow()
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def classify(text: str) -> list[str]:
    lower = text.lower()
    groups = {
        "Models": ["model", "llm", "transformer", "multimodal"],
        "Research": ["paper", "research", "arxiv", "benchmark"],
        "Developer tools": ["developer", "coding", "github", "copilot", "framework"],
        "Policy": ["policy", "regulation", "safety", "governance"],
        "Open source": ["open source", "open-source", "weights", "repository"],
    }
    return [label for label, words in groups.items() if any(word in lower for word in words)][:3] or ["AI"]


def relevant(title: str, summary: str, source: Source) -> bool:
    if source.kind in {"arxiv", "github_repos"} or (source.options or {}).get("ai_focused"):
        return True
    text = f"{title} {summary}".lower()
    return any(term in text for term in AI_TERMS)


def upsert_source(session: Session, id_: str, name: str, url: str, kind: str) -> Source:
    source = session.get(Source, id_)
    if not source:
        source = Source(id=id_, name=name, url=url, kind=kind)
        session.add(source)
        session.flush()
    return source


def insert_item(session: Session, *, kind: str, title: str, summary: str, url: str, source_id: str, published_at: datetime) -> bool:
    url = canonical_url(url)
    title = clean_text(title, 500)
    summary = clean_text(summary)
    source = session.get(Source, source_id)
    if not source or not url or len(title) < 8 or not relevant(title, summary, source):
        return False
    if session.scalar(select(Item.id).where(Item.url == url)):
        return False
    fp = fingerprint(title)
    cutoff = published_at - timedelta(days=3)
    candidates = session.scalars(select(Item).where(Item.published_at >= cutoff, Item.published_at <= published_at + timedelta(days=3)).order_by(Item.discovered_at.desc()).limit(300)).all()
    if any(SequenceMatcher(None, fp, candidate.title_fingerprint).ratio() > 0.91 for candidate in candidates):
        return False
    tags = classify(f"{title} {summary}")
    source_bonus = 20 if source.kind == "arxiv" or (source.options or {}).get("ai_focused") else 10
    score = min(100.0, 45 + source_bonus + (10 if "Research" in tags else 0) + (8 if "Open source" in tags else 0))
    session.add(Item(kind=kind, title=title, summary=summary or title, url=url, source_id=source_id, published_at=published_at, tags=tags, score=score, title_fingerprint=fp))
    session.flush()
    return True


def ingest_feed(session: Session, client: httpx.Client, source: Source) -> int:
    response = get_with_retry(client, source.url)
    response.raise_for_status()
    parsed = feedparser.parse(response.content)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"invalid feed: {parsed.bozo_exception}")
    count = 0
    for entry in parsed.entries[:40]:
        title = entry.get("title", "")
        summary = entry.get("summary", entry.get("description", ""))
        if insert_item(session, kind="news", title=title, summary=summary, url=entry.get("link", ""), source_id=source.id, published_at=parse_date(entry.get("published", entry.get("updated")))):
            count += 1
    return count


def ingest_arxiv(session: Session, client: httpx.Client, source: Source) -> int:
    options = source.options or {}
    categories = options.get("categories", ["cs.AI", "cs.LG", "cs.CL"])
    query = " OR ".join(f"cat:{category}" for category in categories[:10])
    response = get_with_retry(client, source.url, params={"search_query": query, "start": 0, "max_results": min(50, int(options.get("max_results", 25))), "sortBy": "submittedDate", "sortOrder": "descending"})
    response.raise_for_status()
    parsed = feedparser.parse(response.content)
    if parsed.bozo and not parsed.entries:
        raise ValueError("invalid arXiv response")
    return sum(insert_item(session, kind="paper", title=e.get("title", ""), summary=e.get("summary", ""), url=e.get("link", ""), source_id=source.id, published_at=parse_date(e.get("published"))) for e in parsed.entries)


def ingest_hn(session: Session, client: httpx.Client, source: Source) -> int:
    options = source.options or {}
    limit = min(100, int(options.get("hits_per_page", 40)))
    response = get_with_retry(client, source.url, params={"query": str(options.get("query", "AI")), "tags": "story", "hitsPerPage": limit})
    response.raise_for_status()
    data = response.json()
    return sum(insert_item(session, kind="news", title=e.get("title") or "", summary=e.get("story_text") or "Discussion on Hacker News", url=e.get("url") or f"https://news.ycombinator.com/item?id={e.get('objectID')}", source_id=source.id, published_at=parse_date(e.get("created_at"))) for e in data.get("hits", [])[:limit])


def ingest_github(session: Session, client: httpx.Client, source: Source) -> int:
    options = source.options or {}
    since = (utcnow() - timedelta(days=min(90, int(options.get("days_back", 14))))).date().isoformat()
    response = get_with_retry(client, source.url, params={"q": f"{options.get('query', 'topic:machine-learning')} created:>={since}", "sort": "stars", "order": "desc", "per_page": min(100, int(options.get("per_page", 20)))})
    response.raise_for_status()
    data = response.json()
    count = 0
    for repo in data.get("items", []):
        # Total stars are source facts; we intentionally do not infer 24-hour velocity.
        title = f"{repo.get('full_name', '')} · {repo.get('stargazers_count', 0):,} stars"
        count += insert_item(session, kind="repo", title=title, summary=repo.get("description") or "New machine learning repository", url=repo.get("html_url", ""), source_id=source.id, published_at=parse_date(repo.get("created_at")))
    return count


def get_with_retry(client: httpx.Client, url: str, *, params: dict | None = None) -> httpx.Response:
    """Retry transient source failures once; never retry a permanent 4xx response."""
    # A GitHub credential must never accompany a configured RSS or other API URL.
    parsed = urlparse(url)
    headers = {"Authorization": f"Bearer {settings.github_token}"} if settings.github_token and parsed.scheme == "https" and parsed.hostname == "api.github.com" else None
    for attempt in range(2):
        try:
            response = client.get(url, params=params, headers=headers)
            if response.status_code not in {429, 500, 502, 503, 504} or attempt:
                response.raise_for_status()
                return response
            retry_after = response.headers.get("Retry-After", "")
            delay = min(5.0, float(retry_after)) if retry_after.isdigit() else 1.0
        except (httpx.TimeoutException, httpx.ConnectError):
            if attempt:
                raise
            delay = 1.0
        time.sleep(delay)
    raise RuntimeError("unreachable retry state")


def run_ingestion(session: Session, *, force: bool = False) -> JobRun | None:
    now = utcnow()
    sources = session.scalars(select(Source).where(Source.enabled.is_(True)).order_by(Source.name)).all()

    def due(source: Source) -> bool:
        next_at = source.next_fetch_at
        if next_at and next_at.tzinfo is None:
            next_at = next_at.replace(tzinfo=timezone.utc)
        return force or next_at is None or next_at <= now

    due_sources = [source for source in sources if due(source)]
    if not due_sources:
        return None
    run = JobRun(status="running", errors=[])
    session.add(run)
    session.commit()
    adapters = {"rss": ingest_feed, "arxiv": ingest_arxiv, "hacker_news": ingest_hn, "github_repos": ingest_github}
    headers = {"User-Agent": settings.user_agent, "Accept": "application/json, application/atom+xml, application/rss+xml, */*"}
    errors: list[str] = []
    inserted = 0
    if settings.ca_cert_base64:
        verify = ssl.create_default_context()
        verify.load_verify_locations(cadata=base64.b64decode(settings.ca_cert_base64, validate=True).decode("ascii"))
    elif settings.ca_bundle_path:
        verify = ssl.create_default_context(cafile=settings.ca_bundle_path)
    else:
        verify = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    with httpx.Client(timeout=httpx.Timeout(20.0), follow_redirects=True, headers=headers, verify=verify) as client:
        for candidate in due_sources:
            source = session.get(Source, candidate.id)
            try:
                count = adapters[source.kind](session, client, source)
                source.last_success_at = utcnow()
                source.last_attempt_at = utcnow()
                source.last_error = None
                source.last_count = count
                source.failure_count = 0
                source.next_fetch_at = utcnow() + timedelta(minutes=source.interval_minutes)
                inserted += count
                session.commit()
                LOG.info("%s: %s new items", source.name, count)
            except Exception as exc:
                session.rollback()
                source = session.get(Source, candidate.id)
                source.last_attempt_at = utcnow()
                source.last_error = str(exc)[:500]
                source.failure_count += 1
                source.next_fetch_at = utcnow() + timedelta(minutes=min(360, 5 * 2 ** min(source.failure_count - 1, 6)))
                errors.append(f"{source.name}: {type(exc).__name__}: {exc}")
                session.commit()
                LOG.warning("%s failed: %s", source.name, exc)
    run = session.get(JobRun, run.id)
    run.finished_at = utcnow()
    run.inserted = inserted
    run.errors = errors
    run.status = "partial" if errors else "success"
    session.commit()
    return run
