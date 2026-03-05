# CLAUDE.md — Mnemosyne: Experiential Memory Layer for AI Agents

## WHY — Project Purpose

Mnemosyne is an **experiential memory service** that enables AI agents to learn from their own execution history. Unlike Mem0 (user/conversation memory) or Letta (stateful context), Mnemosyne captures **procedural lessons** from agent successes and failures — "what worked, what didn't, and what to do differently."

The core insight: current agent memory tools store *facts and conversations*, not *how to handle errors*. Research (PRAXIS, ReasoningBank, SkillWeaver) shows 10–50% success rate improvements when agents can recall past execution experience. No startup or tool offers this as a first-class product today.

**Target users:** Teams running production AI agents (support bots, coding assistants, data pipeline agents) who suffer from repeated, learnable failures.

**Core value prop:** Agents that self-improve from execution history, reducing failure rates, inference costs, and human intervention.

---

## WHAT — Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                      Agent Frameworks                         │
│  (LangGraph · CrewAI · OpenAI Agents SDK · Custom)           │
│         ↕ OpenTelemetry / SDK instrumentation                │
├──────────────────────────────────────────────────────────────┤
│                    Mnemosyne Service                          │
│                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────┐ │
│  │ Trace       │  │ Lesson       │  │ Retrieval &         │ │
│  │ Ingestion   │→ │ Extraction   │→ │ Serving API         │ │
│  │ (OTel/SDK)  │  │ (LLM-based)  │  │ (vector + keyword)  │ │
│  └─────────────┘  └──────────────┘  └─────────────────────┘ │
│         ↓                ↓                    ↓              │
│  ┌──────────────────────────────────────────────────────────┐│
│  │              PostgreSQL + pgvector                        ││
│  │  traces table │ lessons table │ embeddings │ metadata     ││
│  └──────────────────────────────────────────────────────────┘│
│         ↕                                                    │
│  ┌──────────────┐  ┌──────────────────────────────────────┐  │
│  │ Redis        │  │ Management Dashboard (React)          │  │
│  │ (cache/queue)│  │ Browse · Approve · Edit · Analytics   │  │
│  └──────────────┘  └──────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### Data Model — "Lesson" (core entity)

```python
class Lesson:
    id: UUID
    agent_id: str                    # which agent produced this
    task_context: str                # what the agent was trying to do
    state_snapshot: dict             # environment state when lesson was learned
    action_taken: str                # what the agent did
    outcome: Literal["success", "failure", "partial"]
    lesson_text: str                 # LLM-distilled takeaway
    embedding: list[float]           # vector for semantic retrieval
    confidence: float                # 0–1, decays over time
    created_at: datetime
    last_validated: datetime | None
    tags: list[str]
    source_trace_id: str             # link back to original OTel trace
    version: int                     # for staleness tracking
    domain: str                      # e.g. "web-browsing", "code-gen", "support"
```

---

## HOW — Tech Stack & Development

### Backend (Python)
- **FastAPI** — async API server (REST + WebSocket for real-time)
- **PostgreSQL 16 + pgvector** — relational storage + vector similarity search (no external vector DB dependency)
- **SQLAlchemy 2.0** (async) + **Alembic** — ORM and migrations
- **Redis** — caching hot lessons, rate limiting, Celery task queue broker
- **Celery** — background workers for lesson extraction and embedding generation
- **OpenTelemetry SDK** — trace ingestion receiver (OTLP/gRPC + OTLP/HTTP)
- **Anthropic Claude API** (claude-sonnet-4-5-20250929) — LLM-based lesson extraction from traces
- **sentence-transformers** — local embedding generation (BAAI/bge-small-en-v1.5, 384-dim)

### Frontend (React)
- **React 18 + TypeScript**
- **Tailwind CSS** — styling
- **Recharts** — analytics/charts
- **TanStack Query** — data fetching
- **shadcn/ui** — component library

### Infrastructure
- **Docker Compose** — local dev (postgres, redis, api, worker, dashboard)
- **Pytest + httpx** — backend tests
- **Vitest + React Testing Library** — frontend tests

### Project Structure

```
mnemosyne/
├── CLAUDE.md                    # ← this file
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── pyproject.toml           # use uv or poetry
│   ├── alembic/
│   │   └── versions/
│   ├── app/
│   │   ├── main.py              # FastAPI app factory
│   │   ├── config.py            # pydantic-settings
│   │   ├── db/
│   │   │   ├── engine.py        # async SQLAlchemy engine
│   │   │   ├── models.py        # SQLAlchemy ORM models
│   │   │   └── migrations.py
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   │   ├── traces.py    # POST /traces — ingest agent traces
│   │   │   │   ├── lessons.py   # GET/POST/PATCH /lessons
│   │   │   │   ├── retrieve.py  # POST /retrieve — query lessons for an agent
│   │   │   │   └── health.py
│   │   │   └── deps.py          # dependency injection
│   │   ├── services/
│   │   │   ├── ingestion.py     # parse OTel traces into internal format
│   │   │   ├── extraction.py    # LLM-based lesson extraction from traces
│   │   │   ├── embedding.py     # generate embeddings for lessons
│   │   │   ├── retrieval.py     # vector + keyword search for relevant lessons
│   │   │   └── curation.py      # dedup, confidence decay, conflict detection
│   │   ├── workers/
│   │   │   └── tasks.py         # Celery tasks for async extraction
│   │   └── schemas/
│   │       ├── trace.py         # Pydantic models for trace input
│   │       ├── lesson.py        # Pydantic models for lessons
│   │       └── retrieve.py      # Pydantic models for retrieval requests/responses
│   └── tests/
│       ├── conftest.py
│       ├── test_ingestion.py
│       ├── test_extraction.py
│       ├── test_retrieval.py
│       └── test_api.py
├── frontend/
│   ├── package.json
│   ├── src/
│   │   ├── App.tsx
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx    # overview: lesson count, success rates, top agents
│   │   │   ├── Lessons.tsx      # browse/search/filter lessons
│   │   │   ├── LessonDetail.tsx # view/edit single lesson
│   │   │   ├── Traces.tsx       # view raw ingested traces
│   │   │   └── Settings.tsx     # agent configs, decay policies
│   │   ├── components/
│   │   └── lib/
│   │       └── api.ts           # typed API client
│   └── tests/
├── sdk/
│   └── python/
│       ├── mnemosyne/
│       │   ├── __init__.py
│       │   ├── client.py        # MnemosyneClient — main SDK class
│       │   ├── middleware.py     # LangChain/LangGraph middleware hooks
│       │   └── otel.py          # OTel exporter for auto-instrumentation
│       └── pyproject.toml
└── docs/
    ├── quickstart.md
    ├── architecture.md
    └── api-reference.md
```

---

## Development Commands

```bash
# Start all services
docker compose up -d

# Backend
cd backend
uv sync                           # install deps
uv run alembic upgrade head       # run migrations
uv run pytest                     # run tests
uv run uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev                       # vite dev server on :5173
npm test

# Celery worker
cd backend
uv run celery -A app.workers.tasks worker --loglevel=info
```

---

## Code Conventions

- **Python:** 3.12+, type hints everywhere, `ruff` for linting/formatting, `mypy` for type checking
- **Async-first:** all DB and HTTP operations use async/await
- **Pydantic v2** for all request/response schemas
- **Tests:** pytest with async fixtures, use `httpx.AsyncClient` for API tests, aim for >80% coverage on services/
- **Git:** conventional commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`)
- **Error handling:** raise domain exceptions in services, catch and map to HTTP in routes
- **Env vars:** all config via pydantic-settings, never hardcode secrets
- **SQL:** prefer SQLAlchemy ORM for queries; raw SQL only for complex pgvector operations

---

## Key Design Decisions

1. **pgvector over Pinecone/Weaviate** — keeps everything in one DB, avoids vendor lock-in, supports hybrid queries (metadata filters + vector similarity). Use HNSW index for <1M lessons, IVFFlat if scaling beyond.

2. **Lesson extraction via LLM** — each trace is processed by Claude Sonnet to extract structured lessons. Prompt pattern:
   ```
   Given this agent execution trace:
   [trace JSON]

   Extract a lesson in this format:
   - task_context: what was the agent trying to do?
   - action_taken: what specific action was taken?
   - outcome: success/failure/partial
   - lesson_text: a concise, reusable takeaway (1-3 sentences)
   - tags: relevant categories
   ```

3. **Retrieval = vector similarity + BM25 keyword + metadata filters** — hybrid search ensures both semantic and exact matches. Return top-k lessons, format as prompt context for the agent.

4. **Confidence decay** — lessons lose confidence over time (configurable half-life). Lessons validated by successful reuse get confidence boosted. Stale lessons are auto-archived, not deleted.

5. **SDK-first integration** — the Python SDK wraps common patterns:
   ```python
   from mnemosyne import MnemosyneClient

   client = MnemosyneClient(api_key="...", agent_id="support-bot-v2")

   # At agent decision time — retrieve relevant lessons
   lessons = client.retrieve(context="user asking about refund policy", top_k=5)

   # After agent execution — report outcome
   client.report_outcome(trace_id="...", outcome="success")
   ```

6. **OpenTelemetry native** — agents instrumented with OTel (LangChain, LangGraph, CrewAI all support it) can export traces directly. The ingestion service accepts OTLP/gRPC on port 4317 and OTLP/HTTP on port 4318.

---

## Implementation Priorities (Build Order)

### Phase 1: Core Loop (MVP)
1. DB schema + models (traces, lessons) with pgvector
2. Trace ingestion API (accept JSON traces, store raw)
3. Lesson extraction worker (Celery + Claude API)
4. Embedding generation (sentence-transformers)
5. Retrieval API (vector search + format as prompt context)
6. Basic Python SDK client

### Phase 2: Intelligence
7. Hybrid retrieval (add BM25 keyword search via pg_trgm or ts_vector)
8. Confidence decay + auto-curation worker
9. Conflict detection (flag contradictory lessons)
10. Batch extraction from historical traces

### Phase 3: Dashboard
11. React dashboard — lesson browser with search/filter
12. Lesson detail view with edit/approve/archive actions
13. Analytics — lessons per agent, retrieval hit rate, outcome trends
14. Trace viewer — inspect raw traces linked to lessons

### Phase 4: Production Hardening
15. OTel receiver (OTLP/gRPC ingestion endpoint)
16. LangChain/LangGraph middleware (auto-instrument + auto-retrieve)
17. Rate limiting, auth (API keys), multi-tenancy
18. Staleness detection + environment versioning

---

## Research References (for context, don't need to read)

- **PRAXIS** — stores (state, action, result) tuples, ~10% accuracy lift on web tasks
- **ReasoningBank** — distills reasoning strategies from successes AND failures, 34% improvement
- **SkillWeaver** — agents discover reusable skills, 30-40% success rate increase
- **LEGOMem** — modular memory: orchestrator-level (planning) vs agent-level (execution)
- **FLEX** — library of experiences that evolves via reflection, +23% on math benchmarks
- **Evo-Memory benchmark** — shows existing memory tools (Mem0, etc.) fail on procedural tasks

---

## Environment Variables

```env
# Database
DATABASE_URL=postgresql+asyncpg://mnemosyne:password@localhost:5432/mnemosyne
REDIS_URL=redis://localhost:6379/0

# LLM (for lesson extraction)
ANTHROPIC_API_KEY=sk-ant-...
EXTRACTION_MODEL=claude-sonnet-4-5-20250929

# Embeddings
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
EMBEDDING_DIM=384

# Server
API_HOST=0.0.0.0
API_PORT=8000
OTEL_GRPC_PORT=4317
OTEL_HTTP_PORT=4318

# Auth
API_KEY_SECRET=...        # for signing/validating API keys

# Curation
LESSON_CONFIDENCE_HALF_LIFE_DAYS=30
MAX_LESSONS_PER_RETRIEVAL=10
MIN_CONFIDENCE_THRESHOLD=0.3
```

---

## Important Notes

- **Cold start problem:** New users have no lessons. Phase 1 should include a "seed lessons" feature — import domain-specific lesson packs (e.g., "common LangChain errors") or generate from existing logs.
- **Cost control:** Lesson extraction calls Claude API. Batch extraction and dedup before calling LLM. Budget ~$0.01–0.05 per trace extraction.
- **Latency budget:** Retrieval API must respond in <300ms. pgvector HNSW index + Redis cache for hot lessons should achieve this.
- **Don't over-engineer early:** Start with simple cosine similarity retrieval. Add BM25 hybrid, reranking, and conflict detection in Phase 2.
