# Backend decision: workload before language

Decision date: 2026-10-31. These are architecture judgments for this application, not benchmark results. No comparative load test has established a winner.

AItlas does four distinct kinds of work: network-bound source ingestion, relational search and filtering, CPU-bound parsing/ranking, and optional inference. The API language does not determine model inference speed when inference runs in Ollama or vLLM over HTTP. Query indexes, source quotas, connection pools and caching can dominate response time. A faster web framework does not repair incomplete source coverage or unsupported claims.

## Actual alternatives

| Backend | Advantages here | Costs and failure modes here | Choose when |
|---|---|---|---|
| Python / FastAPI | Pydantic contracts and OpenAPI; convenient feed/data/model tooling; API and ingestion can share schemas and normalization; concise adapters | Pure Python CPU work needs process-level parallelism or native libraries; blocking calls inside async handlers stall the event loop; worker/thread/database pools must be bounded; auth/admin/jobs need explicit components | Small team primarily building data ingestion and retrieval; current default |
| TypeScript / Fastify or NestJS | Shared language with React; good concurrent I/O; mature web tooling; Fastify is lean, Nest provides DI/modules | CPU-heavy parsing/ranking can block the event loop; TypeScript types disappear at runtime, so validate inputs; Python-only libraries require a separate worker or replacement; npm dependency surface needs management | Team is strongest in TypeScript; especially good for an API with model inference served separately |
| Go / net/http or Chi | Straightforward goroutines and cancellation; compiled deployment artifact; useful for concurrent fetchers and APIs; static types | Fewer ready-made ML/data integrations; more explicit schema/error plumbing; goroutines still need concurrency limits and backpressure; garbage collection and database waits still exist | Lean, resource-efficient ingestion/API service with an experienced Go team |
| Java / Spring Boot | Strong contracts, transaction/security/batch ecosystem; Actuator metrics and health; JVM tooling; virtual threads help blocking I/O workloads | More framework configuration; startup and memory commonly higher than lean Go/Rust services, but must measure; ORM query behavior/pool sizing still matter; JVM deployment/tuning overhead | Long-lived product run by a Java team with substantial identity, workflow, and integration needs |
| Rust / Axum + Tokio | Memory safety in safe Rust without GC; explicit ownership; efficient native execution; strong fit for measured CPU/resource bottlenecks | Higher implementation/review cost without Rust experience; async ownership/error patterns add work; fewer comparable feed/ML integrations; blocking tasks still need isolation; unsafe code/native dependencies remain risks | Tight memory/latency requirements or CPU-heavy components with profiling evidence and Rust expertise |
| C# / ASP.NET Core | Strong tooling, async I/O, DI, middleware, observability; viable on Linux with open-source .NET; good fit for C# teams | Separate Python ecosystem if needed; GC/allocation/pool behavior requires measurement; larger application platform than minimal Go/Rust deployments | C# is the team's strongest language or integrations favor .NET |
| Python / Django | Built-in admin, authentication, ORM and migrations can accelerate editorial workflows and user accounts | Heavier framework; async/sync boundaries still require care; separate worker and model serving still needed | Editorial review and account management dominate the roadmap |

Kotlin/Spring has substantially the same operational tradeoffs as Java/Spring. Neither Node nor Rust is inherently less secure than FastAPI; application design, dependencies and configuration determine most risks here. No framework provides highly available storage or durable job execution by itself.

## Recommendation

Keep FastAPI plus Python workers for the current single-team build. Run inference separately and keep HTTP contracts stable. Choose TypeScript/Fastify instead if the maintainers are significantly stronger in TypeScript; a Python API is not required simply because the product concerns AI. Java/Spring or ASP.NET Core are equally credible when team expertise and operational support favor them. Adopt Go/Rust only for a demonstrated cost/latency requirement or team preference, with a scoped pilot before a rewrite.

The current `POST /ask` uses a synchronous handler because its database session is synchronous. FastAPI dispatches ordinary handlers through its thread pool; it must not perform those blocking database operations directly inside an async event-loop handler. An alternative is an entirely async SQLAlchemy driver/session stack, introduced consistently with connection/concurrency limits.

Before revisiting language, benchmark representative workloads on the same resources: source fetch/normalize throughput, indexed search p50/p95/p99, concurrent ask requests with inference isolated, CPU/RSS, pool saturation and failure recovery. Compare end-to-end behavior with the same database and caching, not hello-world HTTP benchmarks.

## Primary references

- [FastAPI concurrency](https://fastapi.tiangolo.com/async/)
- [Node: avoid blocking the event loop](https://nodejs.org/en/learn/asynchronous-work/dont-block-the-event-loop)
- [Go concurrency](https://go.dev/doc/effective_go#concurrency)
- [Tokio runtime](https://tokio.rs/tokio/tutorial)
- [Spring Boot operational features](https://docs.spring.io/spring-boot/reference/actuator/index.html)
- [Spring Boot virtual threads](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.virtual-threads)
- [ASP.NET Core performance guidance](https://learn.microsoft.com/en-us/aspnet/core/performance/overview)
- [Django async support](https://docs.djangoproject.com/en/5.2/topics/async/)
