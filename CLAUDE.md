# CLAUDE.md — Engram: Experiential Memory Layer for AI Agents

## WHY — Project Purpose

Engram is an **experiential memory service** that enables AI agents to learn from their own execution history. Unlike Mem0 (user/conversation memory) or Letta (stateful context), Engram captures **procedural lessons** from agent successes and failures — "what worked, what didn't, and what to do differently."

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
│                    Engram Service                          │
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
engram/
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
│       ├── engram/
│       │   ├── __init__.py
│       │   ├── client.py        # EngramClient — main SDK class
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
   from engram import EngramClient

   client = EngramClient(api_key="...", agent_id="support-bot-v2")

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
DATABASE_URL=postgresql+asyncpg://engram:password@localhost:5432/engram
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


# CLAUDE.md — Engram Phase 3: Management Dashboard

## WHAT THIS IS

Engram is an experiential memory service for AI agents. The backend (FastAPI + PostgreSQL + pgvector) is complete through Phase 2.5. This prompt builds the **management dashboard** — a React SPA that lets teams monitor, explore, and curate their agent memory pool.

**This is an enterprise developer tool, not a consumer product.** The audience is ML engineers and platform teams running production AI agents. They care about data density, fast navigation, and actionable insights — not flashy animations. Think Linear or Datadog, not Dribbble.

---

## FRONTEND TECH STACK

| Tool | Why |
|------|-----|
| **Vite** | Fast builds, HMR, no Next.js overhead (this is a SPA, no SSR needed) |
| **React 19** + **TypeScript 5** strict mode | Type safety, latest React features |
| **shadcn/ui** | Own every component, no black-box dep, accessible via Radix primitives |
| **Tailwind CSS v4** | Utility-first, consistent with shadcn |
| **TanStack Router** | Type-safe file-based routing, better than React Router for SPAs |
| **TanStack Query** | Server state management, caching, refetching, optimistic updates |
| **TanStack Table** | Headless table with sorting, filtering, pagination — critical for data-heavy views |
| **Recharts** | Composable React charts built on D3, works well with shadcn theming |
| **Zustand** | Lightweight client state (sidebar collapse, theme, filters) |
| **Zod** | Schema validation for API responses and forms |

**Do NOT use:** Next.js, Redux, Axios (use native fetch + TanStack Query), CSS modules, Emotion/styled-components, any animation library (keep it fast and functional).

---

## PROJECT STRUCTURE

The dashboard lives in a `dashboard/` directory at the project root, **sibling to the existing `engram/` backend**.

```
dashboard/
├── index.html
├── vite.config.ts
├── tsconfig.json
├── tailwind.config.ts
├── components.json              # shadcn/ui config
├── package.json
├── src/
│   ├── main.tsx                 # App entry, providers
│   ├── app.tsx                  # Root layout (sidebar + content)
│   ├── routes/
│   │   ├── __root.tsx           # Root route layout
│   │   ├── index.tsx            # Redirects to /overview
│   │   ├── overview/
│   │   │   └── index.tsx        # Overview dashboard page
│   │   ├── lessons/
│   │   │   ├── index.tsx        # Lessons data table
│   │   │   └── $lessonId.tsx    # Lesson detail + provenance
│   │   ├── traces/
│   │   │   └── index.tsx        # Traces data table
│   │   ├── failure-queue/
│   │   │   └── index.tsx        # Failure queue monitoring
│   │   ├── review/
│   │   │   └── index.tsx        # Flagged + conflicts review
│   │   └── settings/
│   │       └── index.tsx        # System config display
│   ├── components/
│   │   ├── ui/                  # shadcn/ui components (generated)
│   │   ├── layout/
│   │   │   ├── app-sidebar.tsx  # Collapsible sidebar nav
│   │   │   ├── header.tsx       # Top bar with breadcrumbs
│   │   │   └── page-header.tsx  # Page title + actions slot
│   │   ├── charts/
│   │   │   ├── utility-distribution.tsx
│   │   │   ├── lessons-over-time.tsx
│   │   │   ├── outcome-breakdown.tsx
│   │   │   └── confidence-decay-curve.tsx
│   │   ├── lessons/
│   │   │   ├── lessons-table.tsx          # TanStack Table config
│   │   │   ├── lesson-card.tsx            # Compact lesson preview
│   │   │   ├── provenance-graph.tsx       # Parent/child chain viz
│   │   │   ├── utility-badge.tsx          # Color-coded utility score
│   │   │   └── lesson-type-badge.tsx      # success_pattern/root_cause/etc
│   │   ├── traces/
│   │   │   └── traces-table.tsx
│   │   ├── failure-queue/
│   │   │   ├── queue-stats.tsx
│   │   │   └── failure-group-card.tsx
│   │   └── review/
│   │       ├── flagged-lessons-list.tsx
│   │       └── conflict-pair-card.tsx
│   ├── lib/
│   │   ├── api.ts               # API client (fetch wrapper + base URL)
│   │   ├── utils.ts             # cn() helper, formatters
│   │   └── constants.ts         # API base URL, polling intervals
│   ├── hooks/
│   │   ├── use-lessons.ts       # TanStack Query hooks for lessons
│   │   ├── use-traces.ts
│   │   ├── use-failure-queue.ts
│   │   ├── use-overview-stats.ts
│   │   └── use-provenance.ts
│   ├── types/
│   │   └── api.ts               # Zod schemas + inferred TypeScript types
│   └── stores/
│       └── ui-store.ts          # Zustand: sidebar state, theme, filters
└── .env                         # VITE_API_BASE_URL=http://localhost:8000
```

---

## BACKEND API ENDPOINTS (already built — dashboard consumes these)

```
GET    /lessons                       # List lessons, supports ?type=, ?is_archived=, ?needs_review=
GET    /lessons/{id}                  # Single lesson with all fields
GET    /lessons/{id}/provenance       # Causal chain + retrieval history
GET    /lessons/conflicts             # Lessons with has_conflict=true
GET    /lessons/flagged               # Lessons with needs_review=true
POST   /retrieve                      # Hybrid retrieval (for "test a query" feature)
GET    /traces                        # List traces
POST   /traces                        # Submit trace (for testing)
POST   /outcomes                      # Report outcome (for testing)
GET    /failure-queue/stats           # Queue stats (pending, by_category, by_signature)
POST   /failure-queue/analyze         # Force batch analysis
```

All endpoints return JSON. Pagination via `?offset=&limit=`. Sorting via `?sort_by=&sort_dir=`. No auth yet (Phase 4).

---

## PAGES TO BUILD

### 1. Overview (`/overview`)

The command center. Shows system health at a glance. No clicks needed to understand "is my memory pool healthy?"

**KPI Cards (top row, 4 cards):**
- Total active lessons (excluding archived) + trend sparkline (7d)
- Average utility score across all lessons + up/down indicator vs 7d ago
- Failure queue depth (pending count) + warning color if > 20
- Lessons flagged for review (needs_review count) + link to review page

**Charts (2×2 grid below KPIs):**
- **Lesson creation over time** — stacked area chart by `lesson_type` (success_pattern, root_cause, comparative_insight, general). X-axis: past 30 days. This is the primary "is the system learning?" indicator.
- **Utility distribution** — histogram of utility scores across all active lessons. Healthy = bell curve centered above 0.5. Unhealthy = bimodal or left-skewed.
- **Outcome breakdown** — donut chart showing success/failure/partial ratio across all traces in the past 30 days.
- **Confidence decay curve** — line chart showing average confidence over lesson age (days since creation). Validates that the decay function is working correctly.

**Recent activity feed (right sidebar or below charts):**
- Last 10 provenance events (lesson extracted, penalty propagated, auto-archived, etc.). Each shows event_type icon, lesson snippet, timestamp. Clickable → lesson detail.

### 2. Lessons Explorer (`/lessons`)

The primary data table. Enterprise users will spend most of their time here.

**TanStack Table with:**
- Columns: content (truncated 100 chars), lesson_type (badge), utility (color bar), confidence (color bar), retrieval_count, success_count, outcome, propagation_penalty, created_at, needs_review (icon)
- Server-side pagination (offset/limit)
- Column sorting (click headers)
- Filter bar: lesson_type multi-select, utility range slider, confidence range slider, outcome select, is_archived toggle, needs_review toggle, text search on content
- Row click → navigates to `/lessons/{id}`
- Bulk actions: archive selected, unarchive selected

**Important UX details:**
- Utility and confidence show as tiny horizontal bars inside the cell, not just numbers. Green (> 0.7), yellow (0.3–0.7), red (< 0.3).
- Rows with `needs_review=true` get a subtle left border accent (amber).
- Rows with `propagation_penalty > 0.3` show a warning icon.

### 3. Lesson Detail (`/lessons/:lessonId`)

Everything about one lesson. Three sections:

**Top section — Lesson content + metadata:**
- Full lesson content in a readable card
- Metadata grid: lesson_type, utility, confidence, retrieval_count, success_count, outcome, created_at, extraction_mode, propagation_penalty
- Action buttons: archive/unarchive, mark reviewed (clears needs_review)

**Middle section — Provenance chain:**
- Visual graph showing parent lessons → this lesson → child lessons. Use a simple horizontal node-link diagram (not a full graph library — just flexbox/grid with connecting lines via CSS/SVG). Each node shows lesson content snippet + utility score. Clicking a node navigates to that lesson.
- Below the graph: retrieval history table from `lesson_retrievals` — each row shows trace_id, retrieved_at, outcome, reward. Color-coded by outcome.

**Bottom section — Conflicts:**
- If `has_conflict=true`, show the conflicting lessons in side-by-side cards with their content + outcomes highlighted. Let the user pick which to archive.

### 4. Traces Explorer (`/traces`)

**TanStack Table with:**
- Columns: content (truncated), agent_id, outcome (badge), is_influenced (icon if true), extraction_mode, created_at
- Server-side pagination + sorting
- Filter: outcome select, agent_id search, date range picker, is_influenced toggle
- Row expansion (accordion) showing full trace content + `retrieved_lesson_ids` as clickable links

### 5. Failure Queue (`/failure-queue`)

Monitoring view for the batch failure analysis pipeline.

**Top section — Stats cards:**
- Pending count (big number, warning if > 20)
- Grouped by error_category (bar chart)
- Grouped by error_signature (top 10 list with counts)

**Main section — Pending failures grouped by signature:**
- Accordion/expandable cards, one per error_signature
- Each shows: signature, category, count of pending failures, list of trace snippets
- Groups with 3+ entries show a "Ready for analysis" badge
- **Action button: "Run Batch Analysis Now"** — calls `POST /failure-queue/analyze`, shows loading state, refreshes stats on completion

**Bottom section — Recent batch results:**
- List of recently created `root_cause` lessons from batch analysis. Each shows the lesson content + which traces it was extracted from.

### 6. Review Queue (`/review`)

Two tabs:

**Tab 1 — Flagged Lessons:**
- List of lessons with `needs_review=true`
- Each shows: content snippet, review_reason, utility, propagation_penalty, retrieval_count
- Actions: "Mark Reviewed" (clears flag), "Archive" (removes from pool), "View Detail" (→ lesson detail page)

**Tab 2 — Conflicts:**
- List of lesson pairs where `has_conflict=true`
- Side-by-side comparison card: Lesson A (success) vs Lesson B (failure) with same context
- Actions: "Keep A, Archive B" / "Keep B, Archive A" / "Keep Both" / "Archive Both"

### 7. Settings (`/settings`)

Read-only display of system configuration (fetched from a `GET /config` endpoint — **you'll need to add this endpoint to the backend**).

Display: learning_rate, discount_factor, failure_penalty, propagation_decay, max_propagation_depth, penalty_threshold, confidence_half_life_days, min_confidence_threshold, batch_failure_threshold.

Include a brief description of what each constant controls. This page is for visibility, not editing (editing would require backend restart, so not useful in a dashboard).

---

## DESIGN DIRECTION

**Aesthetic: Functional minimalism.** Think Linear's density meets Datadog's data-richness. Not playful, not brutalist — precise and professional.

**Color system:**
- Background: `zinc-950` (dark mode default — this is a monitoring tool, people use it in dark rooms)
- Surface: `zinc-900` cards on `zinc-950` background
- Primary accent: `blue-500` (trustworthy, enterprise)
- Success: `emerald-500`, Warning: `amber-500`, Danger: `rose-500`
- Utility color scale: `rose-500` (0.0) → `amber-500` (0.5) → `emerald-500` (1.0)
- Text: `zinc-100` primary, `zinc-400` secondary

**Typography:** Use shadcn defaults (Geist family or system fonts). Don't overthink this — it's a data tool.

**Layout:**
- Collapsible sidebar (240px expanded, 48px collapsed icons-only)
- Sidebar nav items: Overview, Lessons, Traces, Failure Queue, Review (with badge count if pending > 0), Settings
- Content area: max-width 1400px, centered, with comfortable padding
- All tables should be full-width within the content area

**Key interaction patterns:**
- Tables are the primary UI — invest in making them fast, sortable, filterable
- Click-through navigation: KPI card → filtered table view → detail page
- Loading states: skeleton loaders on cards and tables (not spinners)
- Polling: overview stats and failure queue stats auto-refresh every 30 seconds via TanStack Query's `refetchInterval`
- Toast notifications for actions (archive, trigger batch analysis, mark reviewed)

---

## CODE CONVENTIONS

- **TypeScript strict mode.** No `any`, no `as` casts unless absolutely necessary, no `@ts-ignore`.
- **Zod for API types.** Define response schemas in `types/api.ts` with Zod, infer TypeScript types with `z.infer<>`. Validate API responses at the boundary.
- **TanStack Query for all data fetching.** Every API call goes through a custom hook in `hooks/`. No raw `fetch` in components. Use `queryKey` conventions: `['lessons', filters]`, `['lesson', id]`, `['overview-stats']`.
- **Server state only in TanStack Query.** Client UI state (sidebar collapsed, active tab) in Zustand. Never mix the two.
- **Component files export one component.** Name file same as component in kebab-case.
- **No prop drilling beyond 2 levels.** Use context or Zustand.
- **Accessible.** All interactive elements have aria labels. Tables have proper thead/tbody. Buttons have focus rings. Colors meet WCAG AA contrast.

## HOW TO VERIFY

```bash
cd dashboard
npm run dev          # Should start on localhost:5173, proxy API to localhost:8000
npm run typecheck    # tsc --noEmit
npm run lint         # ESLint
npm run build        # Production build should succeed with zero errors
```

---

## BUILD ORDER

Build the skeleton first, then add pages one at a time. After each page, verify it renders with mock data before connecting to the real API.

1. **Scaffold** — Vite + React + TypeScript + Tailwind + shadcn/ui + TanStack Router + TanStack Query + Zustand. Get a blank app with sidebar layout rendering.
2. **API layer + types** — `lib/api.ts` fetch wrapper, `types/api.ts` Zod schemas for all API responses, all custom hooks in `hooks/`.
3. **Overview page** — KPI cards (static first, then wired to API), charts.
4. **Lessons table** — TanStack Table with all columns, filters, pagination. Row click navigation.
5. **Lesson detail** — Content card, metadata, provenance chain, retrieval history, conflicts.
6. **Traces table** — Similar pattern to lessons table.
7. **Failure queue** — Stats cards, grouped failures, batch trigger button.
8. **Review page** — Flagged tab + conflicts tab.
9. **Settings page** — Config display (add GET /config to backend if not present).
10. **Polish** — Loading states, error boundaries, empty states, responsive sidebar collapse.