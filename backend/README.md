# ACME Pay Insights — Backend

FastAPI + SQLAlchemy 2 backend. See `../doc/architecture.md` for the design and
its rationale.

## Setup

```bash
uv venv .venv
uv pip install --python .venv/bin/python -e ".[dev]"
cp .env.example .env
```

> Pass `--python .venv/bin/python` explicitly. Without it `uv pip install`
> resolves against whatever interpreter is first on `PATH`, which may not be
> this project's virtualenv.

## Commands

| Task | Command |
|---|---|
| Run the API | `.venv/bin/uvicorn app.main:app --reload` |
| Tests | `.venv/bin/python -m pytest` |
| Lint | `.venv/bin/ruff check .` |
| Format | `.venv/bin/ruff format .` |
| Type check | `.venv/bin/mypy app tests` |
| Apply migrations | `.venv/bin/alembic upgrade head` |
| New migration | `.venv/bin/alembic revision --autogenerate -m "message"` |
| Verify models match migrations | `.venv/bin/alembic check` |

Interactive docs at http://localhost:8000/docs (disabled in production).

## Layout

```
app/
  core/          config (env-based settings), error hierarchy
  db/            declarative base, engine and session
  domain/        pure business logic: Money, currencies, effective dating
  models/        SQLAlchemy ORM models
  schemas/       Pydantic request/response contracts
  repositories/  query construction
  services/      business rules and transaction boundaries
  api/           routers, dependencies, RFC 7807 error handlers
alembic/         migrations
tests/
```

Dependencies point one way: `api → services → repositories → models`, with
`domain/` at the bottom depending on nothing. Services never import FastAPI;
domain functions never import SQLAlchemy. That is what lets the compensation
rules be tested without a database or an HTTP client.

## Conventions worth knowing

- **Money is integer minor units plus a currency**, never a float. Use
  `app.domain.money.Money`; cross-currency arithmetic raises.
- **Compensation is effective-dated.** Employees have no salary column. Periods
  are half-open `[effective_from, effective_to)`.
- **The schema targets SQLite ∩ PostgreSQL.** No `JSONB`, arrays, or native
  `ENUM` types. Foreign keys are enabled explicitly on SQLite, which has them
  off by default.
- **Errors** subclass `app.core.errors.AppError` and are rendered as RFC 7807
  problem details with a stable `type` slug.
