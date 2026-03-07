# Engram Backend

Experiential memory layer for AI agents.

## Development

```bash
uv sync
uv run alembic upgrade head
uv run pytest
uv run uvicorn app.main:app --reload --port 8000
```
