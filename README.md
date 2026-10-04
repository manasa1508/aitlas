# AItlas

A local-first, open-source AI intelligence application. It combines live news, papers and repositories with a cited knowledge timeline, company evidence, real use cases, opportunity hypotheses, unified search, and source-grounded Q&A.

The attached concept note describes a much larger platform. This repository implements a useful **V1**, and [ARCHITECTURE.md](ARCHITECTURE.md) describes how to extend it without presenting unverified market estimates as facts.

## Run locally

Prerequisites: Python 3.11+, [uv](https://docs.astral.sh/uv/), Node.js 20+, npm. Docker is optional.

```bash
cd backend
cp .env.example .env
uv sync --extra dev
uv run python -m app.bootstrap
uv run python -m app.worker --once
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). The API docs are at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs). SQLite is the default local store. Re-run `uv run python -m app.worker --once --force` whenever you want to poll all sources now, or run it without `--once` for continuous source-specific schedules. The browser refreshes its view every minute.

## Optional local LLM

Q&A works without a model through extractive retrieval. To add local synthesis, install [Ollama](https://ollama.com/), run `ollama pull qwen3:8b`, and set the following in `backend/.env`:

```env
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:8b
```

[Qwen3-8B is Apache-2.0 licensed](https://huggingface.co/Qwen/Qwen3-8B). Model responses are marked for source review. The API falls back to extractive answers when the model is unavailable or fails citation validation.

## Docker deployment

The Compose configuration runs PostgreSQL, a migration/seed step, API, ingestion worker, and Nginx frontend. The stack and a six-source containerized ingestion cycle were verified on the authoring host. Run the commands below in your own environment to check your network and credentials.

```bash
cp .env.example .env
# Set a unique POSTGRES_PASSWORD and update DATABASE_URL to match it.
docker compose up --build -d
```

Open [http://127.0.0.1:8080](http://127.0.0.1:8080). The web port binds to loopback. To deploy publicly, put it behind HTTPS, set a persistent database backup schedule, configure proxy rate limits and monitoring, and review source usage terms. See [ARCHITECTURE.md](ARCHITECTURE.md).

If your network inspects TLS traffic through an organization certificate, set `CA_CERT_BASE64` in the untracked `.env` to a base64-encoded PEM certificate. The worker adds that CA to its normal trust store. A mounted PEM can instead be supplied through `CA_BUNDLE_PATH`. Do not disable certificate verification or commit the certificate or `.env`.

## Included features

- Source ingestion: OpenAI RSS, Google AI RSS, GitHub Blog RSS, arXiv, Hacker News, and recent GitHub ML repositories.
- Database-backed source registry with per-source polling schedules, exponential failure backoff, and an operator CLI for adding feeds or changing source options without code edits.
- URL and near-title deduplication, bounded fetches, error isolation by source, sync health and timestamps.
- Auto-computed 24-hour coverage brief with a seven-day fallback, diverse signal selection, filters, historical context matches, and browser-local bookmarks.
- Eight cited AI milestones, three cited company profiles, three documented use cases, and three explicitly labeled opportunity hypotheses.
- Search across the indexed corpus and Q&A with numbered citations. Optional local Ollama synthesis.
- Responsive frontend, API docs, SQLite local mode, PostgreSQL Compose mode, an Alembic initial migration, and backend tests.

Company information and case study outcomes are reported by their linked publishers. The app does not infer that a company's full AI stack, adoption level, or outcomes are independently verified.

### Add or adjust live sources

```bash
cd backend
uv run python -m app.sources list
uv run python -m app.sources add-rss --id pytorch-blog --name "PyTorch Blog" --url https://pytorch.org/blog/feed.xml --interval 15
uv run python -m app.sources set-interval arxiv 30
uv run python -m app.sources set-enabled github-blog false
```

The default registry is in [`backend/config/sources.json`](backend/config/sources.json). `sync-defaults` adds missing defaults without overwriting operator changes. New RSS feeds can be added without a code change; new API families require an adapter. Curated history, companies, use cases and hypotheses can be updated through `uv run python -m app.content reviewed-records.json`, which requires cited URLs. See [DYNAMIC_DATA.md](DYNAMIC_DATA.md) for the exact boundary between live data and reviewed content.

## Check the build

```bash
cd backend && uv run pytest -q
cd ../frontend && npm run build
```

## Decisions to make before wider deployment

See [DECISIONS.md](DECISIONS.md). The main choices are audience and authentication, which content licenses permit automated reuse, whether to operate a local model in production, and the first industry to cover deeply.

## License

Application code is MIT licensed. Each linked article, paper, repository and model retains its own license and terms. AItlas stores headlines, excerpts and links; it does not republish full articles.
