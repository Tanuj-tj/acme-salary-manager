# ACME Pay Insights

Employee salary management and compensation analytics platform.

**Primary persona:** HR Manager — someone who needs to answer real compensation
questions (pay equity, band placement, budget impact of a raise cycle), not
someone who wants to browse database tables.

**Product principle:** this should feel like a real HR compensation tool, not a
CRUD demo. Prefer features that answer a compensation question over features
that merely expose a table.

## Scale and domain constraints

These are design constraints, not aspirations. Assume them in every feature.

- **~10,000 employees.** Endpoints and queries must paginate, filter, and
  aggregate in the database. No "load everything and filter in Python", no
  N+1 query patterns in list or analytics endpoints.
- **Multiple countries.** Country affects compensation bands, statutory
  rules, and effective dates. Never assume a single locale.
- **Multiple currencies.** Store the currency alongside every monetary
  amount. Never sum or compare amounts across currencies without an explicit
  conversion and an explicit rate. Money is not a float — use integer minor
  units or `Decimal`, consistently.

## Technology stack

**Backend**

- Python + FastAPI
- SQLAlchemy 2 (modern typed style: `Mapped[...]`, `mapped_column`, `select()`)
- Pydantic for validation and API contracts
- SQLite for local development; keep the schema and queries
  PostgreSQL-compatible so production can run on Postgres
- Alembic for migrations
- pytest for tests

**Frontend**

- React + TypeScript + Vite
- TanStack Query for server-state and data fetching
- shadcn/ui for components
- Recharts for charts

Do not add a dependency unless it provides clear value over what is already
here. Prefer the stack above to a new library that does the same job.

## Engineering principles

1. **Modular monolith over microservices.** One deployable backend, organized
   into clear internal modules.
2. **No business logic in route handlers.** A route parses input, calls a
   service, and shapes the response. Rules, calculations, and policy live in
   the service layer.
3. **Service/repository boundaries where useful.** Use them when they earn
   their keep — not as ceremony on every table.
4. **Pydantic schemas are the API contract.** Never return ORM models
   directly; define explicit request and response schemas.
5. **Parameterized queries only.** Never build SQL by string interpolation or
   f-strings.
6. **Never expose unrestricted database access to an LLM.** No arbitrary
   SQL execution driven by model output. AI features read through vetted,
   scoped functions with predictable shapes.
7. **AI functionality sits behind a well-defined interface.** Provider and
   prompt details stay behind that boundary so they can be swapped or stubbed
   in tests.
8. **Deterministic unit tests for core business logic.** Compensation math,
   currency handling, and band logic must be tested without network, clock, or
   randomness dependencies.
9. **Avoid premature abstraction.** Two similar things are not yet a pattern.
10. **Favor simple, readable, production-quality code.** Clarity over
    cleverness.
11. **Every meaningful feature ships with tests.**
12. **Preserve backward compatibility of existing APIs** where reasonably
    possible. If a break is genuinely necessary, call it out explicitly rather
    than shipping it quietly.
13. **Run tests and linting before considering a feature complete.**

## Development workflow

Work incrementally. For each task:

1. **Inspect the existing code first.** Match the conventions already present
   rather than importing new ones.
2. **Briefly explain the intended approach** before implementing.
3. **Implement the smallest coherent change** that delivers the feature.
4. **Run the relevant tests** (and linting).
5. **Report what changed:** files touched and tests run, with real results. If
   a test fails, say so and show the output.

Do not rewrite unrelated code, and do not reformat files you did not otherwise
need to touch. Do not silently change product requirements — if a requirement
looks wrong or underspecified, say so and then proceed under a stated
assumption.

## Repository layout

```
backend/          FastAPI service (see backend/README.md)
  app/
    core/         env-based settings, error hierarchy
    db/           declarative base, engine and session
    domain/       pure business logic: Money, currencies, effective dating
    models/       SQLAlchemy ORM models
    schemas/      Pydantic request/response contracts
    repositories/ query construction
    services/     business rules and transaction boundaries
    api/          routers, dependencies, RFC 7807 error handlers
  alembic/        migrations
  tests/
doc/              architecture.md, requirements.md
```

The frontend is not yet scaffolded; it will live in a sibling `frontend/`
directory. `doc/requirements.md` is still empty — the architecture document
records the requirements assumed in its absence.

Dependencies point one way: `api → services → repositories → models`, with
`domain/` at the bottom depending on nothing. Services never import FastAPI;
domain functions never import SQLAlchemy.

## Backend commands

Run from `backend/`:

| Task | Command |
|---|---|
| Install | `uv pip install --python .venv/bin/python -e ".[dev]"` |
| Run the API | `.venv/bin/uvicorn app.main:app --reload` |
| Tests | `.venv/bin/python -m pytest` |
| Lint | `.venv/bin/ruff check .` |
| Format | `.venv/bin/ruff format .` |
| Type check | `.venv/bin/mypy app tests` |
| Apply migrations | `.venv/bin/alembic upgrade head` |
| New migration | `.venv/bin/alembic revision --autogenerate -m "message"` |
| Verify models match migrations | `.venv/bin/alembic check` |

Before considering a feature complete, run tests, lint, and type check.

## Established conventions

- **Money is integer minor units plus a currency**, never a float. Use
  `app.domain.money.Money`; cross-currency arithmetic raises rather than
  coercing. Currency precision comes from the registry — JPY has 0 minor-unit
  digits, so "divide by 100" is wrong.
- **Compensation is effective-dated.** Employees have no salary column;
  `SalaryRecord` periods are half-open `[effective_from, effective_to)`, and at
  most one open record exists per (employee, pay_type).
- **The schema targets SQLite ∩ PostgreSQL.** No `JSONB`, arrays, or native
  `ENUM` types. Foreign keys are enabled explicitly on SQLite, which has them
  off by default.
- **Errors** subclass `app.core.errors.AppError` and render as RFC 7807 problem
  details with a stable machine-readable `type` slug.
- **`flake8-type-checking` (TC) rules are intentionally disabled** in ruff:
  SQLAlchemy and Pydantic resolve annotations at runtime, so moving those
  imports under `TYPE_CHECKING` breaks model configuration.
