"""Source-linked discovery views. Topic matches and comparisons are candidates, not fact verification."""
from functools import lru_cache
import json
from pathlib import Path
import re
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from .db import utcnow
from .jobs import JOB_SOURCE_KINDS, apply_job_filters, job_board_url
from .models import Item, Source


@lru_cache(maxsize=1)
def config():
    return json.loads((Path(__file__).resolve().parents[1] / "config" / "intelligence.json").read_text())


def matches(text, terms):
    return any(re.search(r"\b" + re.escape(term) + r"\b", text, re.I) for term in terms)


def attention(item):
    d = item.details or {}
    if item.kind == "repo":
        return int(d.get("stars") or 0) >= 25
    if item.kind == "model":
        return d.get("trending_rank") is not None
    if item.kind == "paper":
        return int(d.get("upvotes") or 0) >= 5
    return item.source.kind != "hacker_news" or int(d.get("points") or 0) >= 10


def build_intelligence(db, serialize, days=7, topic="all"):
    now = utcnow()
    rows = db.scalars(select(Item).options(selectinload(Item.source)).where(Item.active.is_(True), Item.kind.in_(("news", "paper", "repo", "model")), Item.published_at >= now - timedelta(days=days * 2), Item.published_at <= now).order_by(Item.published_at.desc()).limit(2000)).all()
    current, previous = [], []
    for item in rows:
        published = item.published_at
        if published.tzinfo is None:
            from datetime import timezone
            published = published.replace(tzinfo=timezone.utc)
        (current if published >= now - timedelta(days=days) else previous).append(item)
    def in_topic(item, terms):
        return matches(f"{item.title} {item.summary}", terms)
    topics = []
    for entry in config()["topics"]:
        found = [item for item in current if in_topic(item, entry["terms"])]
        topics.append({"id": entry["id"], "name": entry["name"], "count": len(found), "previous_count": sum(in_topic(item, entry["terms"]) for item in previous), "source_count": len({item.source_id for item in found})})
    selected = next((entry for entry in config()["topics"] if entry["id"] == topic), None)
    scoped = [item for item in current if not selected or in_topic(item, selected["terms"])]
    discoveries = [item for item in scoped if item.kind == "paper" or (item.source.options or {}).get("category") == "research"]
    changes = []
    for item in scoped:
        if item.kind not in {"news", "paper"}:
            continue
        text = f"{item.title}. {item.summary}"
        kind = "Deprecation or migration" if matches(text, ["deprecated", "deprecation", "end of support", "migration", "supersedes", "replaces", "replacing"]) else "Comparison claim" if matches(text, ["outperforms", "outperform", "alternative to", "versus", "leapfrog", "faster than", "better than"]) else None
        if kind:
            sentences = re.split(r"(?<=[.!?])\s+", text)
            excerpt = next((s for s in sentences if re.search(r"deprecat|migrat|supersed|replac|outperform|alternative to|versus|leapfrog|faster than|better than", s, re.I)), text)
            changes.append({"item": serialize(item), "label": kind, "claim_excerpt": excerpt, "status": "Publisher claim; not independently validated"})
    repos = sorted((item for item in scoped if item.kind == "repo" and attention(item)), key=lambda item: int((item.details or {}).get("stars") or 0), reverse=True)
    markets = []
    for company in config()["market_watchlist"]:
        news = [item for item in current if item.kind == "news" and matches(f"{item.title} {item.summary}", company["aliases"])]
        reactions = [item for item in news if re.search(r"\b(?:stocks?|shares)\b.{0,60}\b(?:rose|rise|rises|fell|fall|falls|drops?|dropped|gains?|gained|surge[sd]?|plunge[sd]?|rall(?:y|ied)|slump(?:ed)?|tumbl(?:e|ed)|jump(?:ed)?)\b|market cap|market value|sell.off|\bnasdaq\b|stock market", f"{item.title} {item.summary}", re.I)]
        markets.append({**company, "news_count": len(news), "reports": [serialize(item) for item in news[:5]], "reaction_reports": [serialize(item) for item in reactions[:3]], "quote_status": "not_connected", "quote_url": f"https://finance.yahoo.com/quote/{company['symbol']}/"})
    return {"window_days": days, "sample_size": len(rows), "sample_limit": 2000, "sample_truncated": len(rows) == 2000,
        "topics": sorted(topics, key=lambda row: row["count"], reverse=True), "discoveries": [serialize(item) for item in discoveries[:30]],
        "repos": [serialize(item) for item in repos[:30]], "shifts": changes[:30], "markets": markets,
        "methodology": "Trends count matching records in a bounded source sample, not global popularity. Stars, votes and model ranks measure attention, not quality. Comparisons are publisher claims. News and price movements alone do not establish causation."}


def employer_directory(db, city="target", ai_only=False, role="all"):
    employers = []
    sources = db.scalars(select(Source).where(Source.kind.in_(JOB_SOURCE_KINDS), Source.enabled.is_(True)).order_by(Source.name)).all()
    scoped = apply_job_filters(select(Item).where(Item.kind == "job", Item.active.is_(True)), city, ai_only=ai_only)
    if role != "all":
        scoped = scoped.where(Item.details["role"].as_string() == role)
    counts = dict(db.execute(scoped.with_only_columns(Item.source_id, func.count()).group_by(Item.source_id)).all())
    locations = {}
    for source_id, value in db.execute(scoped.with_only_columns(Item.source_id, Item.details["location"].as_string()).distinct()).all():
        group = locations.setdefault(source_id, [])
        if value and len(group) < 8:
            group.append(value)
    profiles = config().get("employer_profiles", {})
    discovery_sources = config().get("employer_discovery_sources", [])
    discovery_by_id = {entry["id"]: entry for entry in discovery_sources if entry["status"] == "reviewed"}
    for source in sources:
        name = str((source.options or {}).get("company") or source.name)
        career_url = job_board_url(source)
        employers.append({"name": name, "category": "Product and technology", **profiles.get(name, {}), "open_roles": counts.get(source.id, 0), "locations": locations.get(source.id, []), "url": career_url, "coverage": "public_feed", "adapter": source.kind, "last_error": source.last_error, "last_checked": source.last_success_at.isoformat() if source.last_success_at else None})
    connected_names = {row["name"].casefold() for row in employers}
    links_only = [entry for entry in config()["career_links"] if entry["name"].casefold() not in connected_names]
    employers.extend({**entry, **profiles.get(entry["name"], {}), "open_roles": None, "locations": [], "coverage": "official_link", "last_checked": None} for entry in links_only)
    for employer in employers:
        employer["discovery_sources"] = [discovery_by_id[key] for key in employer.get("discovery_source_ids", []) if key in discovery_by_id]
    return {"employers": employers, "city": city, "ai_only": ai_only, "role": role,
        "discovery_sources": discovery_sources,
        "coverage_summary": {"connected_employers": len(sources), "synced_employers": sum(bool(source.last_success_at) for source in sources), "failing_employers": sum(bool(source.last_error) for source in sources), "career_links_only": len(links_only), "matching_roles": sum(counts.get(source.id, 0) for source in sources)},
        "rating_status": "Employee ratings are not connected. Dated awards and list membership are cited where verified; they do not rate an individual role or team. Coverage is a selected employer registry, not every GCC or Fortune 500 company."}
