# Engram Integrations

Integration tests validating the full learn-retrieve-improve loop against two real-world agent projects.

## Projects

### Langflow Customer Support Agent (`langflow/`)

Simulates a Langflow-based multi-agent customer support system (Streamlit + Langflow).

- **Agent ID:** `langflow-support-v1`
- **Domain:** `customer-support`
- **25 fixture traces:** 8 success, 12 failure, 5 partial
- **Failure groups:** 4× CRM API timeout, 3× payment gateway auth failure (enables batch root_cause extraction)
- **Scenarios:** cold_start (first lessons), learning_loop (full cycle with batch analysis)

### TestZeus Hercules (`hercules/`)

Simulates a Hercules-based test automation system (AutoGen + Playwright).

- **Agent ID:** `hercules-test-v1`
- **Domain:** `test-automation`
- **34 fixture traces:** 10 success, 18 failure, 6 partial
- **Failure groups:** 4× element not found, 3× navigation timeout, 3× assertion failed
- **Scenarios:** cold_start (first lessons), failure_cluster (batch analysis from grouped failures)

## Prerequisites

- Engram backend running on `http://localhost:8000`
- PostgreSQL + Redis running
- Celery worker running (for trace processing and lesson extraction)

```bash
# Start infrastructure
cd backend
docker compose up -d  # or start postgres/redis locally
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000 &
uv run celery -A app.workers.celery_app worker --loglevel=info &
```

## Setup

```bash
cd integrations
pip install -e .
# or
pip install httpx pydantic pytest pytest-asyncio
```

## Seed Lessons (Cold Start)

```bash
python -m integrations.langflow.seed_lessons
python -m integrations.hercules.seed_lessons
```

## Run Tests

```bash
# All integration tests (requires running backend)
pytest integrations/ -v -m integration --tb=short

# Skip live tests
pytest integrations/ -v -k "not live" --tb=short

# Single project
pytest integrations/langflow/tests/ -v --tb=short
pytest integrations/hercules/tests/ -v --tb=short
```

## Verify in Dashboard

After running tests, check the dashboard to see lessons, traces, and failure queue:

```
http://localhost:5173/lessons
http://localhost:5173/failure-queue
http://localhost:5173/flagged
```

## Structure

```
integrations/
├── README.md
├── pyproject.toml
├── .env.example
├── conftest.py                    # Shared fixtures: base_url, run_id, outcomes_client
├── shared/
│   ├── trace_builder.py           # TraceBuilder, load_fixture(), generate_run_id()
│   ├── outcomes_client.py         # POST /api/v1/outcomes wrapper
│   └── verify.py                  # poll_until(), wait_for_processing(), wait_for_lesson()
├── langflow/
│   ├── adapter.py                 # LangflowEngramAdapter
│   ├── seed_lessons.py            # Seed 7 customer support lessons
│   ├── fixtures/                  # 25 trace JSON files
│   ├── scenarios/
│   │   ├── cold_start.py          # First lessons scenario
│   │   └── learning_loop.py       # Full learn-retrieve-improve cycle
│   └── tests/
│       └── test_langflow.py       # 13 integration tests
└── hercules/
    ├── adapter.py                 # HerculesEngramAdapter
    ├── seed_lessons.py            # Seed 7 test automation lessons
    ├── fixtures/                  # 34 trace JSON files
    ├── scenarios/
    │   ├── cold_start.py          # First lessons scenario
    │   └── failure_cluster.py     # Batch failure analysis scenario
    └── tests/
        └── test_hercules.py       # 8 integration tests
```

## Key Design Decisions

- **Fixture-based:** Traces are JSON files, not generated at runtime. This ensures reproducibility.
- **Run ID stamping:** Each test session gets a unique `run_id` injected into trace data to avoid SHA-256 dedup collisions.
- **OutcomesClient:** The SDK's `report_outcome()` calls `POST /traces/{id}/process` (reprocessing only). The `OutcomesClient` calls `POST /api/v1/outcomes` which triggers the full Bellman update + penalty propagation pipeline.
- **No backend imports:** Tests only interact via HTTP API — they validate the system as an external consumer would.
