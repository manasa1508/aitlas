# Decisions for the next build

The current code uses conservative defaults so it can run now. These decisions change the product and infrastructure materially.

| Decision | Current default | Other viable path | When to decide |
|---|---|---|---|
| Audience and accounts | Public read-only content; bookmarks stay in the browser | Private workspace with OIDC login, organization tenancy, server-side saved items and follows | Before public personalization or team data |
| First deep domain | LLMs and Transformer lineage | Start with vision, robotics, AI engineering or a chosen industry | Before growing the archive and entity graph |
| AI answer engine | Extractive retrieval; optional local Qwen3 via Ollama | vLLM for higher throughput; no generated synthesis | Before exposing Q&A at scale |
| Search index | SQL filters plus bounded lexical ranking | PostgreSQL full-text search, then pgvector hybrid retrieval using an Apache-licensed embedding model | Once the corpus exceeds roughly 10k indexed records or relevance suffers |
| Content partnerships | Headlines, short excerpts and links from public feeds; hand-reviewed case summaries | Licensed datasets and direct publisher agreements | Before bulk importing external libraries |
| Opportunity scoring | Human-readable hypotheses with barriers and adjacent evidence | Quantitative market and workflow model with sourced denominators, confidence intervals and review | Before showing scores or percentages |
| Jobs | No live job listing yet | Greenhouse/Lever company feeds or another permitted source, with expiry and location normalization | When career signals become a priority |
| Notifications | No email or push in V1 | Self-hosted mail infrastructure and opted-in digest service | After accounts and consent design |

**Recommended sequence:** pick a target user and one deep domain, validate source rights, then add accounts and saved server state. Add embeddings, jobs and a measured gap model only after the corresponding data is reliable.
