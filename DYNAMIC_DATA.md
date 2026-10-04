# Live data and hardcoded content audit

## What is live now

The signal feed retrieves actual public RSS and API results. Source configuration lives in the database, seeded from `backend/config/sources.json`. The worker polls each source at its configured interval: Hacker News every 5 minutes, selected RSS feeds every 15 minutes, and arXiv/GitHub repositories every 30 minutes by default. It retries transient failures once, backs off persistently after failures, records sync health, and deduplicates existing URLs. The browser refreshes its data every minute while visible. This is **near-real-time**: actual freshness is limited by publisher release time, API availability and poll intervals.

The company page also shows recent **mentions** from the live feed when they match a company name. A mention is not treated as evidence that the company adopted a technology.

## What is still curated

The historical timeline, baseline company claims, use cases and opportunity hypotheses start from `backend/app/seed.py`. They are static **starter records**, clearly cited. They can be updated without changing application code using the operator-only JSON importer:

```bash
cd backend
uv run python -m app.content path/to/reviewed-records.json
```

The importer accepts a JSON list with `type` of `knowledge`, `company`, `evidence`, `use_case` or `opportunity`. Each record uses the corresponding SQLAlchemy model field names and must provide a source or evidence URL. It upserts by lowercase slug `id`. Company and use-case evidence should be reviewed by a human before publishing. There is no public write API.

## Current fixed rules and how to expand them

| Current rule | Where | Expansion |
|---|---|
| Initial source catalog | `config/sources.json` | Add RSS sources with `app.sources add-rss`; add new API families through a small adapter plus registry entry. |
| Poll intervals and API query options | `sources` table | Change through `app.sources set-interval` and `set-options`; persist across restarts. |
| Signal type tabs and source adapters | Frontend and `app/ingest.py` | New RSS feeds appear under News automatically. A new content type needs an adapter, database kind, API filter and display card. |
| AI relevance terms and category tags | `app/ingest.py` | Move to an editorial taxonomy table, per-source rules, and a labeled relevance evaluation set. |
| Signal scoring | `app/ingest.py` | Calibrate on user feedback and source quality; store score components and model version. Avoid opaque claims of “high signal.” |
| Historical lineage | `knowledge.related_ids` | Resolve entities from permitted paper metadata and review proposed graph edges before publishing. |
| Companies and use cases | Reviewed starter data / JSON import | Build source adapters for licensed case-study feeds, candidate extraction, deduplication and human approval. |
| Opportunity map | Curated hypotheses | Build a sourced workflow taxonomy and validated denominators before any penetration or market-size score. |
| Bookmarks | Browser local storage | Move to account-backed persistence when identity and sync are required. |
| Q&A retrieval | Bounded lexical ranking | Add PostgreSQL full-text search, then pgvector hybrid retrieval and evaluation as corpus grows. |
| Navigation, page copy and suggested questions | `frontend/src/App.tsx` | Navigation and copy are product UI. Suggestions and the timeline preview now derive from loaded content; a CMS is appropriate if editors need to change page copy without deploys. |
| First signal page size | `frontend/src/App.tsx` | The first 100 load quickly; readers can load older items in additional pages. At large scale use cursor pagination to avoid shifting offsets. |

## Why not auto-publish every extracted claim?

News mentions do not prove adoption, vendor case studies can be selective, and scraped pages may contain outdated or restricted material. The scalable design is a two-stage pipeline: automated discovery creates source-linked **candidates**, then validation checks entity identity, recency, permissions, duplicate claims and evidence quality. Only approved records become company intelligence, use cases or gap analysis. Feed aggregation itself remains fully automatic.

## Suggested next data connectors

1. Add more permitted publisher RSS feeds using the CLI, with per-source relevance tests.
2. Import arXiv and Crossref/OpenAlex metadata into a separate paper catalog, retaining publication identifiers and licenses; do not automatically call every paper a historical milestone.
3. Add Hugging Face model metadata and GitHub release events with their official API limits and license fields.
4. Build company and use-case candidate queues from approved sources; require review before displaying factual claims.
5. Add jobs only from permitted ATS feeds with posting expiry and duplicate handling.
