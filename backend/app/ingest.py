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
    value = html.unescape(html.unescape(value or ""))
    value = re.sub(r"<[^>]+>", " ", value)
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


def audience_for(text: str, source: Source) -> str:
    lower = text.lower()
    business = any(term in lower for term in ("funding", "revenue", "enterprise", "acquisition", "startup", "investment", "market", "partnership", "adoption", "regulation", "policy", "business"))
    developer = any(term in lower for term in ("developer", "repository", "github", "code", "sdk", "api", "framework", "benchmark", "open source", "pytorch", "inference", "fine-tuning"))
    if business and developer:
        return "both"
    if business:
        return "business"
    if developer:
        return "developer"
    return (source.options or {}).get("audience", "general")


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


def insert_item(session: Session, *, kind: str, title: str, summary: str, url: str, source_id: str, published_at: datetime, details: dict | None = None) -> bool:
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
    session.add(Item(kind=kind, title=title, summary=summary or title, url=url, source_id=source_id, published_at=published_at, tags=tags, details={"audience": audience_for(f"{title} {summary}", source), **(details or {})}, score=score, title_fingerprint=fp))
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
        url = canonical_url(repo.get("html_url", ""))
        if not url:
            continue
        stars = int(repo.get("stargazers_count") or 0)
        title = clean_text(repo.get("full_name", ""), 500)
        summary = clean_text(repo.get("description") or "Machine learning repository")
        existing = session.scalar(select(Item).where(Item.url == url))
        if existing and existing.kind == "repo":
            previous = (existing.details or {}).get("stars")
            delta = stars - previous if isinstance(previous, int) else None
            existing.details = {"audience": "developer", "stars": stars, "stars_delta_since_last_sync": delta, "language": repo.get("language"), "license": (repo.get("license") or {}).get("spdx_id"), "last_observed_at": utcnow().isoformat()}
            existing.title = title
            existing.summary = summary
            existing.last_seen_at = utcnow()
            existing.score = min(100.0, 55 + min(35, max(0, delta or 0) * 2))
        elif not existing:
            count += insert_item(session, kind="repo", title=title, summary=summary, url=url, source_id=source.id, published_at=parse_date(repo.get("created_at")), details={"audience": "developer", "stars": stars, "stars_delta_since_last_sync": None, "language": repo.get("language"), "license": (repo.get("license") or {}).get("spdx_id"), "last_observed_at": utcnow().isoformat()})
    return count


def job_role(title: str) -> str:
    lower = title.lower()
    if any(term in lower for term in ("research", "scientist", "machine learning", "ai engineer", "ml engineer")):
        return "Research & AI"
    if any(term in lower for term in ("engineer", "developer", "architect", "infrastructure", "security", "data", "technical")):
        return "Engineering"
    if any(term in lower for term in ("product", "design", "ux")):
        return "Product & design"
    return "Business & operations"


def ingest_greenhouse_jobs(session: Session, client: httpx.Client, source: Source) -> int:
    response = get_with_retry(client, source.url, params={"content": "true"})
    response.raise_for_status()
    payload = response.json()
    jobs = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(jobs, list) or len(jobs) > 2000:
        raise ValueError("Greenhouse returned an invalid or oversized jobs list")
    existing = {row.url: row for row in session.scalars(select(Item).where(Item.source_id == source.id, Item.kind == "job")).all()}
    seen: set[str] = set()
    now = utcnow()
    company = str((source.options or {}).get("company") or source.name).strip()[:160]
    added = 0
    for job in jobs:
        if not isinstance(job, dict) or job.get("internal_job_id") is None:
            continue
        url = canonical_url(job.get("absolute_url") or "")
        if not url or urlparse(url).scheme != "https":
            continue
        title = clean_text(job.get("title") or "", 300)
        if len(title) < 4:
            continue
        seen.add(url)
        location = clean_text((job.get("location") or {}).get("name") or "Location not specified", 160)
        department = ", ".join(clean_text(d.get("name") or "", 80) for d in (job.get("departments") or [])[:3])
        description = clean_text(job.get("content") or "", 700)
        details = {"audience": "developer" if job_role(title) in {"Research & AI", "Engineering"} else "business", "company": company, "location": location, "department": department, "role": job_role(title), "updated_at": job.get("updated_at"), "misses": 0}
        if url in existing:
            row = existing[url]
            row.title = title
            row.summary = description or f"{title} at {company} · {location}"
            row.details = details
            row.active = True
            row.last_seen_at = now
        else:
            session.add(Item(kind="job", title=title, summary=description or f"{title} at {company} · {location}", url=url, source_id=source.id, published_at=parse_date(job.get("first_published") or job.get("updated_at")), tags=[job_role(title)], details=details, active=True, last_seen_at=now, score=60, title_fingerprint=fingerprint(f"{company} {title} {location}")))
            added += 1
    for url, row in existing.items():
        if url not in seen and row.active:
            misses = int((row.details or {}).get("misses", 0)) + 1
            row.details = {**(row.details or {}), "misses": misses}
            if misses >= 2:
                row.active = False
    session.flush()
    return added


def ingest_hf_models(session: Session, client: httpx.Client, source: Source) -> int:
    limit = min(100, max(1, int((source.options or {}).get("limit", 30))))
    response = get_with_retry(client, source.url, params={"sort": "trendingScore", "direction": "-1", "limit": limit})
    response.raise_for_status()
    models = response.json()
    if not isinstance(models, list):
        raise ValueError("Hugging Face returned an invalid model list")
    count = 0
    for rank, model in enumerate(models[:limit], start=1):
        model_id = model.get("id") or model.get("modelId")
        if not isinstance(model_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", model_id):
            continue
        url = f"https://huggingface.co/{model_id}"
        license_tag = next((tag.removeprefix("license:") for tag in model.get("tags", []) if isinstance(tag, str) and tag.startswith("license:")), None)
        details = {"audience": "developer", "task": model.get("pipeline_tag"), "downloads": model.get("downloads"), "likes": model.get("likes"), "trending_score": model.get("trendingScore"), "trending_rank": rank, "license": license_tag}
        summary = f"Trending model on Hugging Face · {model.get('pipeline_tag') or 'task not specified'} · {int(model.get('downloads') or 0):,} downloads"
        existing = session.scalar(select(Item).where(Item.url == url))
        if existing and existing.kind == "model":
            existing.summary = summary
            existing.details = details
            existing.last_seen_at = utcnow()
            existing.score = max(50.0, 100.0 - rank)
        elif not existing:
            session.add(Item(kind="model", title=model_id, summary=summary, url=url, source_id=source.id, published_at=parse_date(model.get("createdAt")), tags=["Models"], details=details, active=True, last_seen_at=utcnow(), score=max(50.0, 100.0 - rank), title_fingerprint=fingerprint(model_id)))
            count += 1
    session.flush()
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
    adapters = {"rss": ingest_feed, "arxiv": ingest_arxiv, "hacker_news": ingest_hn, "github_repos": ingest_github, "greenhouse_jobs": ingest_greenhouse_jobs, "hf_models": ingest_hf_models}
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
