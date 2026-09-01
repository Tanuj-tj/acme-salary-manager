# ACME Pay Insights — Architecture & Implementation Plan

Status: **proposal, not yet implemented.** No code exists in this repository yet.

---

## 0. Preface: requirements were not available

`doc/requirements.md` is empty at the time of writing. This plan therefore
derives its requirements from `CLAUDE.md` and the product brief (HR Manager
persona, ~10,000 employees, multi-country, multi-currency, salary management +
compensation analytics + natural-language querying).

Everything below rests on the assumptions in §0.2. **Read that section first.**
Where a wrong assumption would change the design materially, it is flagged
inline. When `requirements.md` is written, this document should be reconciled
against it before implementation starts.

### 0.1 Assumed scope

In scope:

- Employee and organisation records (department, manager, location, job).
- Compensation records with full history — salary changes over time.
- Salary bands per job level / country, with compa-ratio and band placement.
- Multi-currency amounts, normalised to a chosen reporting currency.
- Compensation analytics: payroll cost, band placement, pay equity, distribution.
- A natural-language question interface over those analytics.
- Authenticated HR users with role-based access.

Out of scope (explicitly, unless requirements say otherwise):

- **Payroll execution.** Calculating and disbursing actual pay is a regulated
  problem an order of magnitude harder than analytics. This tool analyses
  compensation; it does not pay people.
- Tax, statutory benefits, pension, or social-contribution modelling.
- Performance management, recruiting, ATS, time and attendance.
- Being the system of record. Assume an upstream HRIS owns employee truth.

### 0.2 Assumptions requiring confirmation

| # | Assumption | If wrong |
|---|---|---|
| A1 | Data is imported from an upstream HRIS; Pay Insights is a downstream analytics + planning tool | If it is the system of record, write paths, audit, and data-integrity requirements grow substantially |
| A2 | Daily data freshness is acceptable; nothing needs to be real-time | Real-time would require a sync/event pipeline |
| A3 | Users are HR staff and (later) people managers — roughly 50–250 named users, not all 10,000 employees | Self-service for all 10,000 changes the auth model and raises peak concurrency ~50× |
| A4 | Base salary is the primary compensation element; bonus and equity are secondary | If total-reward modelling is central, the compensation model needs more element types up front |
| A5 | Demographic attributes needed for pay-equity analysis (e.g. gender) are available and legally permitted to store per country | Pay-equity analytics would be limited to non-demographic dimensions in some jurisdictions |
| A6 | Single tenant — one company, ACME | Multi-tenancy would need a tenant key on every table from day one; retrofitting it is painful |
| A7 | An LLM API (Claude) is available server-side for the NL feature | The NL feature would fall back to a keyword/grammar parser over the same intent catalog |

---

## 1. Scale: what 10,000 employees actually means

Every decision in this document is justified against this section, so it comes
first. The headline finding: **10,000 employees is a small dataset.** The
architecture should be designed for correctness and iteration speed, not for
throughput.

| Entity | Rough row count | Basis |
|---|---|---|
| Employees | 10,000 | given |
| Compensation records | ~100,000 | 10k employees × ~10 records over 5 years of history |
| Salary bands | ~500 | ~12 levels × ~8 job families × ~15 countries, sparsely populated |
| FX rates | ~1,000 | ~15 currencies × monthly close × 5 years |
| Departments / locations / jobs | < 1,000 combined | |

Total: **well under 100 MB.** The entire working set fits comfortably in the
page cache of the smallest production database instance available from any
managed provider. A full aggregate scan of the compensation table is a
sub-100 ms operation, and with the indexes in §3.5 the real analytics queries
land in single-digit to low-tens of milliseconds.

Concurrency (per A3): 50–250 named users, of whom a realistic peak might be 20
active simultaneously, generating well under 10 requests/second. A single
2-vCPU application instance is roughly two orders of magnitude over-provisioned
for that.

**The consequences, which recur throughout this document:**

- No microservices, no message broker, no Redis, no read replicas, no
  materialised views, no caching layer, no search cluster, no OLAP store. None
  of these solve a problem that exists at this scale, and each adds a failure
  mode, a deployment surface, and a class of consistency bug.
- Analytics are computed **synchronously, at request time, in SQL**. There is
  no ETL pipeline and no pre-aggregation.
- The scarce resource is not CPU or I/O — it is **correctness**. A payroll-cost
  number that is 3% wrong because of an FX or effective-dating bug is far more
  damaging to an HR Manager than a query that takes 200 ms instead of 20 ms.
  Engineering effort belongs in the domain model and its tests.

What 10,000 *does* demand, and where sloppiness would genuinely hurt:

- **No N+1 queries.** Rendering an employee list must not issue 50 queries for
  bands and 50 for FX rates. At 10 rows in dev this is invisible; at 10,000 it
  is a timeout.
- **No unbounded responses.** Every list endpoint paginates with a hard cap.
- **Aggregation in the database, not in Python.** Pulling 100,000 compensation
  rows into the app to sum them is ~50 MB of ORM objects per request.
- **Indexes on every filter and join column** used by analytics.

---

## 2. Domain model

The domain model is the part of this system worth taking seriously. It is what
separates a compensation tool from a CRUD app over a `salary` column.

### 2.1 The three concepts that define the product

**1. Compensation is effective-dated, not a field on an employee.**

An employee does not *have* a salary; they have a *history* of compensation
records, each valid over a date range. "What is Priya's salary?" is shorthand
for "what compensation record is in effect for Priya today?" and the tool must
equally answer "…on 1 January last year?"

This single decision is what makes it possible to answer the questions an HR
Manager actually asks: what did payroll cost last quarter, how much has the
average salary in Engineering moved this year, what is the run-rate impact of
the raises we approved. A mutable `salary` column on `employees` cannot answer
any of them, and no amount of later work recovers the discarded history.

*Why appropriate at 10,000 employees:* the cost is ~100,000 rows and one
resolver function — trivially cheap. The alternative (a separate audit-log
table, with current state denormalised onto the employee) is the pattern that
scales *worse*, because every analytical question becomes a reconstruction job.

**2. Money is an amount plus a currency, and never a float.**

A bare number is not money. `Money` is a value object of
`(amount_minor: int, currency: str)` — integer minor units (cents, pence, yen)
to eliminate binary floating-point drift, with the currency inseparable from
the amount. Adding two `Money` values of different currencies raises; it does
not silently coerce.

*Why appropriate at 10,000 employees:* across ~15 countries, cross-currency
aggregation happens on essentially every analytics query. Making the illegal
operation unrepresentable in the type is the cheapest possible defence, and
float drift over 10,000 summed salaries is large enough to be visible in a
reported total.

**3. Every cross-currency comparison names its rate and its date.**

Converting requires an explicit `(from, to, as_of_date)` lookup. A missing rate
is an error, never a silent 1.0. Any UI that displays a normalised total also
displays the reporting currency and the rate date.

*Why appropriate at 10,000 employees:* at this size the company is genuinely
multi-country, so nearly every headline figure is a converted figure. An
unlabelled "total payroll: 812M" is not just imprecise, it is unusable — the
HR Manager cannot reconcile it against anything.

### 2.2 Entities

```
Employee ─┬─< CompensationRecord >── Currency
          │         │
          │         └── change_reason, effective_from, effective_to
          ├── Department (hierarchical)
          ├── Location ── Country ── default Currency
          ├── Job (JobFamily + JobLevel)
          ├── manager → Employee (self-referential)
          └─── EmployeeDemographics (optional, separately permissioned)

SalaryBand ── (JobFamily, JobLevel, Country) → min / mid / max + Currency
FxRate ── (base, quote, rate_date) → rate
User ── role
NlQueryLog ── question, resolved intent, params, outcome
```

**Employee** — identity and employment facts only, never a salary amount.
`employee_number` (stable external ID from the HRIS), name, email, hire date,
termination date (nullable), status, and FKs to department, location, job, and
manager. Termination date matters: analytics must be able to exclude leavers,
and "active headcount as of date X" is an effective-dated question too.

**CompensationRecord** — the heart of the model. `employee_id`, `Money`
(amount_minor + currency), `pay_type` (base / bonus / allowance), `pay_period`
(annual / monthly / hourly, normalised to annual for comparison),
`effective_from`, `effective_to` (nullable = currently in effect),
`change_reason` (hire, merit, promotion, market adjustment, FX correction,
demotion), and `created_at`/`created_by` for audit.

Invariant: for a given `(employee_id, pay_type)`, records must not overlap in
time, and at most one may be open-ended. Enforced in the service layer on
write, backed by a partial unique index (§3.5).

**Job = JobFamily × JobLevel.** Separating the two is what makes bands and
like-for-like equity cohorts possible: "Engineering" is a family, "L4" is a
level, and a band is defined on the pair plus country. Collapsing them into a
free-text job title destroys the ability to compare.

**SalaryBand** — min / mid / max in a stated currency for a
(family, level, country) triple, itself effective-dated (bands are re-set
annually). Yields the two metrics HR Managers actually use:

- **Compa-ratio** = salary ÷ band midpoint. 1.0 means paid at midpoint.
- **Range penetration** = (salary − min) ÷ (max − min). Position in the band.

*Why appropriate at 10,000 employees:* bands are how an organisation of this
size maintains any pay consistency at all. Below ~200 people bands are
overkill; at 10,000 across multiple countries they are the only mechanism that
makes "is this person paid correctly?" an answerable question rather than a
matter of opinion. Modelling them per country is essential — an L4 engineer's
band in Poland and in Switzerland are different numbers in different
currencies, and a single global band would be actively misleading.

**EmployeeDemographics** — a deliberately separate table (per A5) holding
attributes used only for equity analysis. Separate because access is separately
permissioned, some jurisdictions restrict storage, and it must be easy to
locate, audit, and delete this data as a unit.

**FxRate** — `(base_currency, quote_currency, rate_date, rate)`. Monthly close
rates rather than daily (§5.4).

### 2.3 Domain services (pure, no I/O)

These are ordinary Python functions over value objects, holding the rules that
must be right. They take data in and return data out — no session, no clock, no
network — which is precisely what makes them deterministically testable per
principle 8.

- `money.py` — `Money`, arithmetic, allocation, minor-unit handling.
- `fx.py` — conversion given an explicit rate; raises on missing rate.
- `effective_dating.py` — resolve the record in effect at a date; detect
  overlaps; close an open interval when a new record supersedes it.
- `bands.py` — compa-ratio, range penetration, in/below/above band.
- `equity.py` — unadjusted and cohort-adjusted gap; small-cohort suppression.
- `annualisation.py` — normalise hourly/monthly to annual for comparison.

---

## 3. Database schema

SQLite locally, PostgreSQL in production, one schema for both.

### 3.1 Compatibility rules

The dual-database choice is a genuine risk (§10, R1), managed by restricting
the schema to the intersection of both engines:

- No Postgres-only types: no `JSONB` (use `JSON`), no arrays, no `ENUM` types,
  no range types. Enums live in Python and are stored as short `VARCHAR` with a
  `CHECK` constraint.
- No SQLite-specific behaviour: never rely on its permissive typing, its
  implicit `rowid`, or `AUTOINCREMENT` quirks.
- Integer surrogate primary keys — identical behaviour on both engines, half
  the index size of UUIDs, and human-readable in support conversations. External
  identity is carried by `employee_number`, not the PK.
- Dates as `DATE`, timestamps as `TIMESTAMP` stored in UTC. SQLite has no native
  date type; SQLAlchemy's `Date`/`DateTime` handle the mapping, but comparisons
  must be done through SQLAlchemy rather than in raw SQL.
- Money as `BIGINT` minor units plus a `CHAR(3)` currency. Never `FLOAT`, and
  not `NUMERIC` — integers behave identically on both engines, whereas SQLite
  silently degrades `NUMERIC` to float.
- Foreign keys declared everywhere, with `PRAGMA foreign_keys=ON` set on every
  SQLite connection (it is off by default — a real source of dev/prod drift).

*Why appropriate at 10,000 employees:* the dataset is small enough that SQLite
is a perfectly adequate development database, and a zero-setup `git clone &&
pytest` loop is worth real money in iteration speed. The intersection
restriction costs almost nothing, because none of the excluded features are
needed here.

### 3.2 Core tables

```
employees
  id PK · employee_number UNIQUE · first_name · last_name · work_email UNIQUE
  hire_date · termination_date NULL · status
  department_id FK · location_id FK · job_id FK · manager_id FK→employees.id
  created_at · updated_at

compensation_records
  id PK · employee_id FK
  amount_minor BIGINT · currency_code FK→currencies
  pay_type · pay_period
  effective_from DATE · effective_to DATE NULL
  change_reason · note NULL
  created_at · created_by FK→users

departments
  id PK · name · code UNIQUE · parent_department_id FK→departments.id NULL

locations
  id PK · name · city · country_code FK→countries

countries
  code PK CHAR(2) · name · default_currency_code FK→currencies

currencies
  code PK CHAR(3) · name · minor_unit_digits SMALLINT   -- JPY=0, USD=2

job_families        id PK · name · code UNIQUE
job_levels          id PK · name · rank SMALLINT UNIQUE   -- ordered
jobs                id PK · job_family_id FK · job_level_id FK · title
                    UNIQUE (job_family_id, job_level_id)

salary_bands
  id PK · job_family_id FK · job_level_id FK · country_code FK
  min_minor · mid_minor · max_minor BIGINT · currency_code FK
  effective_from DATE · effective_to DATE NULL

fx_rates
  id PK · base_currency FK · quote_currency FK · rate_date DATE
  rate NUMERIC(18,8)
  UNIQUE (base_currency, quote_currency, rate_date)

employee_demographics
  employee_id PK FK · gender NULL · date_of_birth NULL · ...

users               id PK · email UNIQUE · hashed_password · role · is_active
audit_log           id PK · user_id FK · action · entity · entity_id
                    · payload JSON · created_at
nl_query_log        id PK · user_id FK · question · resolved_intent NULL
                    · params JSON NULL · status · latency_ms · created_at
```

`minor_unit_digits` on `currencies` is not pedantry: JPY has no minor unit, and
hardcoding "divide by 100" produces answers wrong by 100× for Japanese
employees — a bug that a multi-country tool will hit in its first demo.

### 3.3 Why FX rates are a table, not a config value or an API call

Rates must be reproducible. If last quarter's payroll report is regenerated in
six months, it must produce the same number, which requires the rate that was
used, stored, and dated. Calling a live FX API at query time would make every
historical report non-reproducible and add a network dependency to the critical
path. Rates are refreshed by a scheduled job (§9.4) and written to this table.

### 3.4 What is deliberately *not* denormalised

No `current_salary` column on `employees`, and no pre-converted
`amount_in_usd_minor` on `compensation_records`.

Both are tempting and both are wrong here. A cached current salary is a
second source of truth that will drift from the record history the first time
something writes to one and not the other. A stored USD conversion bakes in one
reporting currency and one rate policy, silently going stale when rates are
corrected or when a user wants totals in EUR.

*Why appropriate at 10,000 employees:* the denormalisation buys a join on
100,000 rows — microseconds. It costs a permanent class of consistency bug.
That trade is only worth making at a scale this system will never see. This is
principle 9 applied to the schema: if profiling later shows a real problem, a
materialised snapshot table can be added deliberately, with a documented refresh
path.

### 3.5 Indexes

```
compensation_records  (employee_id, effective_from DESC)   -- history lookup
                      (effective_from, effective_to)       -- as-of scans
                      partial UNIQUE (employee_id, pay_type)
                          WHERE effective_to IS NULL       -- one open record
employees             (department_id) · (location_id) · (job_id) · (manager_id)
                      (status, termination_date)           -- active filtering
salary_bands          (job_family_id, job_level_id, country_code, effective_from)
fx_rates              (base_currency, quote_currency, rate_date DESC)
```

Partial indexes are supported by both SQLite (≥3.8) and Postgres, so the
"exactly one open compensation record" invariant is enforced by the database on
both, not just by application code that a future bug could bypass.

### 3.6 Migrations

A single linear Alembic chain, autogenerate-assisted but always hand-reviewed.
`render_as_batch=True` in `env.py` so SQLite's limited `ALTER TABLE` support
does not block schema evolution locally.

Reference data (currencies, countries) ships *in* migrations — it is part of the
schema's meaning and every environment needs it. Sample or demo data never
does; that is the seeder's job (§8). Mixing the two makes production
deployments carry fake employees.

---

## 4. API structure

### 4.1 Layering

```
routers/     HTTP only: parse, validate, authorise, delegate, shape response
services/    business logic, transactions, orchestration — the real work
repositories/ query construction and persistence
domain/      pure functions and value objects (§2.3)
models/      SQLAlchemy ORM
schemas/     Pydantic request/response contracts
```

A router is expected to be a handful of lines (principle 2). Services never
import FastAPI; domain functions never import SQLAlchemy. That direction of
dependency is what allows the compensation rules to be tested without a
database or an HTTP client.

Per principle 3, repositories are introduced where they earn it — compensation,
analytics, and employees, where query construction is non-trivial and worth
testing in isolation. Reference lookups (countries, currencies) can query
directly from their service without a repository layer of ceremony.

### 4.2 Module boundaries

Modular monolith (principle 1) — one deployable, organised by domain:

```
app/modules/
  employees/      roster, org structure, employee detail
  compensation/   comp records, history, raises, band placement
  bands/          salary band administration
  analytics/      aggregate metrics (§5)
  insights/       natural-language querying (§6)
  reference/      countries, currencies, departments, jobs, FX
  auth/           users, login, RBAC
```

*Why appropriate at 10,000 employees:* microservices solve organisational
scaling (many teams shipping independently) and heterogeneous resource profiles.
Neither applies. What they would add here is network calls where function calls
would do, distributed transactions across employee and compensation writes, and
an inability to compute a payroll aggregate in a single SQL statement — the
analytics story would get dramatically worse. Module boundaries inside one
process give the organisational clarity without any of that cost, and leave the
door open to extraction later if it is ever warranted.

### 4.3 Endpoints

All under `/api/v1` (principle 12 — versioning is how backward compatibility
stays cheap when it eventually cannot be preserved).

```
Employees
  GET  /employees                    paginated, filtered
  GET  /employees/{id}
  GET  /employees/{id}/compensation  full history
  GET  /employees/{id}/reports       direct reports

Compensation
  POST /employees/{id}/compensation  record a change (closes prior interval)
  GET  /compensation/changes         recent changes feed

Bands
  GET  /bands
  GET  /bands/placement              compa-ratio distribution per cohort

Analytics                            all accept ?as_of= and ?currency=
  GET  /analytics/summary            KPI tiles
  GET  /analytics/payroll-cost       grouped by dept / country / level
  GET  /analytics/compa-ratio
  GET  /analytics/pay-equity
  GET  /analytics/salary-distribution
  GET  /analytics/compensation-trend

Insights
  POST /insights/query               natural-language question
  GET  /insights/capabilities        what it can answer

Reference
  GET  /reference/{departments|locations|jobs|currencies}
```

### 4.4 Cross-cutting API decisions

**Two shared query parameters, on every analytics endpoint.** `as_of` (default
today) and `currency` (default the user's reporting currency). Every analytics
response echoes both back, plus the FX rate date used. Making these universal
rather than per-endpoint is what keeps point-in-time and multi-currency from
being bolted on inconsistently — and it means the NL layer (§6) has a uniform
surface to target.

**Offset pagination, `limit` default 50 and hard-capped at 200.** Keyset
pagination is strictly better for deep paging, but at 10,000 rows the worst case
is `OFFSET 9950`, which is a few milliseconds on an indexed table. Offset gives
jump-to-page, which HR Managers scanning a roster genuinely use. This is
principle 9: take the simpler option, and revisit if the row count ever
justifies it.

**Filtering is a fixed allowlist** of parameters (department, country, level,
family, status, employment dates), each mapped to a typed Pydantic field and
bound as a parameter. No generic filter-expression syntax — that is a SQL
injection surface and an unbounded-query surface for no real gain.

**Errors** are RFC 7807 problem details with a stable machine-readable `type`,
so the frontend can branch on failure modes without string-matching.

**PII never appears in logs.** Request logging records user ID, route, and
timing — never names, emails, or amounts.

---

## 5. Analytics architecture

### 5.1 The core decision: SQL at request time

Aggregations are ordinary parameterised `SELECT … GROUP BY` statements built
with SQLAlchemy Core, executed synchronously inside the request. There is no
warehouse, no cube, no pre-aggregation job, no cache.

*Why appropriate at 10,000 employees:* the largest table is ~100,000 rows. A
grouped aggregate with the §3.5 indexes is single-digit to low-tens of
milliseconds. A pre-aggregation pipeline would add a staleness window, a
backfill problem, a scheduling dependency, and a whole category of "the
dashboard disagrees with the employee page" bugs — to save perhaps 30 ms. The
correct engineering decision is to not build it. If a query ever does become
slow, the first move is an index, the second is a narrower query, and only the
third is caching.

### 5.2 Structure

```
analytics/
  metrics.py       pure functions: compa-ratio, gap, percentiles, cohort stats
  repository.py    the aggregate SQL
  service.py       orchestration: resolve as-of, apply FX, suppress, assemble
  schemas.py       response contracts
```

The split matters for testing: `metrics.py` is pure arithmetic verified against
hand-computed fixtures, while `repository.py` is verified against a small known
dataset. A wrong number is the worst possible failure for this product (§10,
R8), and this separation is what makes each half independently checkable.

### 5.3 Point-in-time resolution

Every analytics query resolves, per employee, the compensation record where
`effective_from <= as_of AND (effective_to IS NULL OR effective_to > as_of)` —
a half-open interval `[from, to)`, applied consistently everywhere. Half-open is
chosen because it makes consecutive intervals abut without gaps or overlaps at
the boundary, which is where effective-dating bugs live.

This resolution happens **in SQL**, as a join, not by looping in Python.

*Why appropriate at 10,000 employees:* the Python loop would be 10,000
round-trips (N+1 at its worst). The SQL join is one query. This is the single
most likely place for the codebase to acquire an N+1 problem, so it is worth
having exactly one shared helper that constructs this join, used by every
analytics query.

### 5.4 Currency normalisation

Conversion to the reporting currency happens in SQL via a join to `fx_rates`,
selecting the rate effective at the analytics `as_of` date. Rates are
**month-end close**, not daily.

*Why month-end:* if the dashboard used daily spot rates, total payroll cost
would change every morning without a single compensation record having changed.
An HR Manager cannot plan against a number that moves on its own, and cannot
reconcile it with a report they ran yesterday. Month-end close rates are what
finance functions actually use, they make figures stable and reconcilable, and
they cut the rate table from ~27,000 rows to ~1,000.

A missing rate raises rather than defaulting (§10, R4). Every normalised figure
carries its currency and rate date in the response.

### 5.5 The metrics

**Payroll cost** — sum of annualised base compensation for active employees at
`as_of`, grouped by department, country, or level. The run-rate figure.

**Compa-ratio distribution** — placement against band, bucketed
(below min / 0.8–0.9 / 0.9–1.0 / 1.0–1.1 / above max). The single most useful
view in the product: it surfaces both retention risk (a strong performer at 0.82)
and budget leakage (a cohort clustered above max).

**Pay equity** — reported two ways, always together:

- *Unadjusted gap*: raw median difference across the whole population. Simple,
  and the figure most jurisdictions require for reporting.
- *Adjusted gap*: difference within like-for-like cohorts (same job family,
  level, and country), aggregated. Answers the different and more actionable
  question of whether comparable people are paid comparably.

Reporting only one is misleading in opposite directions — the unadjusted gap
mostly measures role distribution, the adjusted gap can hide the fact that a
group is systematically in lower-paid roles. A real HR tool shows both and
explains the difference.

**Small-cohort suppression:** any cohort with fewer than 5 members returns
suppressed rather than a value. With 10,000 employees across ~15 countries and
~12 levels, the cohort grid is sparse — many cells will hold 1–3 people, and a
"median salary" for a cell of one is that person's salary, disclosed to anyone
with dashboard access. Suppression is a hard product requirement, not a
setting. It is implemented in the service layer so it cannot be bypassed by
calling a different endpoint.

**Salary distribution** — percentiles (p10/p25/median/p75/p90) per cohort,
computed in SQL. Note that `PERCENTILE_CONT` exists in Postgres but not SQLite;
this is the one metric needing a dialect-aware implementation (an ordered
offset-based selection works on both) — see §10, R1.

**Compensation trend** — a metric time series over the last N months, derived
by repeating the as-of resolution at each month boundary.

### 5.6 Deliberately not built

Cohort drill-down to arbitrary depth, custom metric builders, saved report
definitions, scheduled report emails. Each is plausible; none is needed to prove
the product. Principle 9.

---

## 6. Natural-language query architecture

This is the highest-risk feature in the product and the one where the
architecture matters most. Principles 6 and 7 govern it absolutely.

### 6.1 The decision: intent resolution, not SQL generation

**The LLM never writes SQL, never sees the schema, and never touches the
database.** It performs exactly one job: mapping a natural-language question
onto one of a fixed catalog of hand-written, pre-vetted analytics functions,
returning a typed parameter object.

```
question
   │
   ├─ 1. Guardrails: length, rate limit, authenticated user
   │
   ├─ 2. Intent resolution  ── LLM ──  receives: the question + the intent
   │                                   catalog (names, descriptions, parameter
   │                                   schemas, enum values)
   │                                   returns: { intent, params, confidence }
   │                                   never receives: schema, rows, or PII
   │
   ├─ 3. Validation: intent ∈ catalog? params valid against its Pydantic model?
   │                 Reject → "I can't answer that yet" + capabilities list
   │
   ├─ 4. Authorisation: does this user have access to this metric and scope?
   │
   ├─ 5. Execution: the *existing* §5 analytics service. Same code path as the
   │                dashboard. Parameterised. Suppression applied.
   │
   ├─ 6. Narration (optional) ── LLM ── receives only the aggregated, suppressed
   │                                    result rows; writes one sentence
   │
   └─ 7. Response: { answer, data, chart_hint, intent, params } + audit log
```

Step 5 is the crux: the NL feature is a *routing layer over the existing
analytics API*, not a parallel data path. Anything it can answer, the dashboard
can already compute, through the same tested code, with the same suppression and
the same permissions.

### 6.2 Why not text-to-SQL

Text-to-SQL demos beautifully and is the wrong choice here:

- **It is unrestricted database access to an LLM** — exactly what principle 6
  forbids. Sandboxing it (read-only user, statement timeouts, table allowlists)
  mitigates but never closes the surface.
- **It fails silently.** A syntactically valid query answering a subtly
  different question returns a confident, plausible, wrong number. For pay
  equity, wrong numbers are the failure mode with real consequences.
- **It cannot be tested deterministically**, violating principle 8. The intent
  catalog can: the routing is stubbed, the execution is pure code.
- **It bypasses suppression.** Generated SQL has no reason to respect the
  minimum-cohort rule, so it becomes a PII disclosure channel.
- **It leaks the schema** into prompts, and with it the shape of the data.

The intent catalog answers fewer questions. Every question it answers, it
answers correctly, verifiably, and within policy. For compensation data that is
the right trade (§11, T2).

*Why appropriate at 10,000 employees:* an organisation this size has real
compensation questions but a bounded set of them — cost, placement, equity,
distribution, trend, sliced by the handful of dimensions that exist. A catalog
of 8–12 intents covers the great majority of what an HR Manager asks. The
open-ended tail that text-to-SQL would theoretically reach is not worth the risk
surface.

### 6.3 The interface (principle 7)

```python
class IntentResolver(Protocol):
    def resolve(self, question: str, catalog: IntentCatalog) -> ResolvedIntent | None: ...
```

Implementations:

- `ClaudeIntentResolver` — production. Prompt and provider details live here and
  nowhere else.
- `StubIntentResolver` — CI and tests. Deterministic question→intent mapping.
- `KeywordIntentResolver` — a keyword/pattern fallback over the same catalog,
  which also covers assumption A7 failing entirely.

Nothing outside this module imports an LLM SDK or knows a prompt exists. The
API contract, the tests, and the frontend are all unchanged if the provider
changes.

### 6.4 Safety properties

- **No PII to the model, in either direction.** Resolution sends the question
  and the catalog. Narration sends aggregated, already-suppressed rows.
- **Prompt injection is structurally contained.** Employee free-text fields
  never enter a prompt. Even a successful injection can only select a different
  catalog intent with valid parameters — it cannot reach the database, exfiltrate
  rows, or escape the user's permissions. This containment is a *consequence of
  the architecture*, not of prompt wording, which is why it is trustworthy.
- **Refusal over guessing.** Below a confidence threshold or on validation
  failure, the response says it cannot answer and lists what it can. An HR tool
  that confidently invents a pay gap figure is worse than one that declines.
- **Every question is logged** to `nl_query_log` with the resolved intent and
  parameters — for audit, and to see which unsupported questions users actually
  ask, which is the input to deciding the next intent to build.
- **Provenance in the UI.** The answer always shows which metric ran with which
  parameters, so the user can verify it against the dashboard rather than
  trusting prose.

---

## 7. Testing strategy

Principle 8 requires deterministic tests of core logic; principle 11 requires
tests with every meaningful feature. The shape follows from where the risk is:
this system's danger is *wrong numbers*, not *slow responses*, so the weight
goes on domain arithmetic and query correctness.

### 7.1 Layers

**Domain unit tests — the bulk, and the priority.** Pure functions from §2.3:
money arithmetic and rounding, FX conversion, effective-dating boundaries,
compa-ratio, equity math, annualisation, suppression thresholds. No database, no
clock, no network; milliseconds to run. Boundary cases get explicit tests: a
record effective exactly on `as_of`, back-to-back intervals, zero-width
intervals, JPY's zero minor digits, a band with min == max.

**Repository/integration tests.** Against a small fixture dataset with
hand-computed expected values, so an aggregate query producing 4,317,500 can be
checked against a number a human derived independently. Transaction-per-test
with rollback for isolation.

**API tests.** FastAPI `TestClient` with the DB session dependency overridden.
Cover contract shape, pagination limits, filter allowlists, authorisation
(a user without demographic permission must not reach equity endpoints), and
error format.

**Frontend tests.** Vitest + React Testing Library, with MSW mocking the API at
the network boundary. Focus on the things that break silently: currency and
date formatting, filter state in the URL, empty and suppressed states, loading
and error rendering. One Playwright smoke path (log in → dashboard → employee →
compensation history) rather than a broad E2E suite.

### 7.2 Determinism rules

Non-negotiable, since flaky tests on a correctness-critical system destroy trust
in the suite:

- **Time is injected**, never read ambiently. A `Clock` dependency, fixed in
  tests. No global `datetime` monkeypatching.
- **Randomness is seeded.** Fixed seed in the seeder and in any test data.
- **FX rates are fixtures**, never fetched.
- **The LLM is always stubbed in CI.** `StubIntentResolver` is wired in the test
  settings. No test ever makes a model call.
- **No network in the test suite at all**, enforced by a socket-blocking fixture.

### 7.3 The dialect problem

Because dev is SQLite and prod is Postgres (§10, R1), the integration suite runs
against **both**: SQLite by default for local speed, and Postgres in CI via a
service container, selected by an env var. Without this, dialect drift is
discovered in production — and §5.5's percentile query is a concrete example of
a metric that behaves differently on the two engines.

### 7.4 Guards, not just assertions

- **Query-count assertions** on list and analytics endpoints. An N+1 regression
  is invisible against 10 fixture rows and fatal against 10,000 — a test that
  fails when an endpoint issues more than N queries is the only reliable way to
  catch it before production.
- **A performance smoke test** against the full 10,000-employee seed, asserting
  analytics endpoints stay under a generous threshold. Not a benchmark; a
  tripwire for accidental full scans.

Coverage is a diagnostic, not a target. The rule that matters is principle 11:
a feature without tests is not done.

---

## 8. Seeding strategy

Seed data is not a developer convenience here — it is what determines whether
the product can be evaluated at all. Analytics over 20 fake employees with
random salaries show nothing; the dashboard looks empty and the NL feature has
nothing true to find.

### 8.1 Profiles

| Profile | Employees | Use |
|---|---|---|
| `minimal` | ~20 | unit and API tests; hand-verifiable |
| `demo` | ~500 | fast local dev, full UI exercise |
| `full` | 10,000 | performance testing, realistic demo |

`python -m app.seed --profile full --seed 42`, idempotent, transactional, and
entirely separate from Alembic (§3.6).

### 8.2 Realism is the requirement

Uniformly random salaries produce a symmetric distribution with no band
violations, no pay gap, and no outliers — every analytics view renders correctly
and says nothing. The seeder must generate data with the structure real
compensation data has:

- **A real org tree.** Realistic spans of control (5–8 reports), an executive
  layer, deeper hierarchy in large functions. Makes the org and manager rollup
  views meaningful.
- **Log-normal salary distribution within each band**, centred slightly below
  midpoint — which is what actual populations look like, since new hires enter
  low and tenure pushes people up.
- **Country-correct currencies and realistic level-to-band mappings**, including
  at least one zero-minor-unit currency (JPY) to keep §3.2's rounding honest.
- **3–5 years of compensation history per employee** with plausible reasons —
  hires, annual merit cycles clustered in one month, occasional promotions with
  a step change. Without history, every point-in-time and trend feature is
  untestable and undemonstrable.
- **Deliberately planted findings.** A handful of employees below band minimum;
  one department with a measurable adjusted pay gap; a cohort clustered above
  band maximum; a few employees with no compensation record at all; a country
  missing an FX rate for one month. These exist so the analytics have something
  true to discover, and so error paths are exercised by real data rather than
  only by unit tests.

*Why appropriate at 10,000 employees:* the planted anomalies are how the product
demonstrates that it is a compensation tool rather than a table viewer — a demo
where the equity view shows a real gap in a real department, and the NL query
finds it, is a fundamentally different artefact from one showing uniform noise.

### 8.3 Mechanics

Bulk inserts (`insert().values([...])` in batches), not 10,000 individual ORM
adds — the difference is minutes versus seconds. Fixed seed for reproducibility,
so a bug found against seeded data can be reproduced exactly. Generated
deterministically without external data downloads.

---

## 9. Deployment architecture

### 9.1 The shape

```
  Browser
     │  HTTPS
  ┌──▼──────────────────────────────┐
  │ Reverse proxy / static host     │   /        → React build (static)
  │                                 │   /api/*   → FastAPI
  └──┬──────────────────────────────┘
     │
  ┌──▼───────────────┐        ┌──────────────────┐
  │ FastAPI container│───────▶│ Managed Postgres │
  │ uvicorn workers  │        │ + daily backups  │
  └──┬───────────────┘        └──────────────────┘
     │
  ┌──▼──────────────┐
  │ Scheduled task  │  nightly FX refresh
  └─────────────────┘
```

That is the entire production topology: **one application container, one managed
database, static assets, one scheduled job.**

*Why appropriate at 10,000 employees:* per §1, expected peak is under 10
requests/second against a sub-100 MB database. A single small instance handles
this with roughly two orders of magnitude of headroom. Kubernetes, a service
mesh, autoscaling groups, Redis, and a message broker would each add operational
surface, failure modes, and debugging complexity to solve load that does not
exist. The system can be scaled — if ever needed — by running two or three
identical stateless containers behind the proxy, because the app holds no local
state.

### 9.2 Frontend and backend on one origin

The React build is served by the same proxy that fronts the API, under the same
domain. This eliminates CORS configuration, cross-site cookie handling, and a
class of "works locally, breaks in staging" auth bugs — for the cost of one
proxy rule. Vite's dev server proxies `/api` locally to match.

### 9.3 Migrations and releases

Alembic runs as an explicit release step *before* the new container takes
traffic, never on application startup — startup migrations race when more than
one instance boots. Migrations are expand-then-contract (add nullable, backfill,
switch reads, drop later) so a deploy can be rolled back without data loss.

### 9.4 The scheduled job

FX rate refresh, nightly. A scheduled container running a CLI command, not a
Celery/Redis worker pool. One job, running once a day, taking seconds, is not a
distributed-systems problem, and introducing a broker and result backend to run
it would be the clearest possible case of unnecessary infrastructure. If
background work later becomes genuinely long-running or numerous (bulk HRIS
imports, large exports), revisit then — with evidence.

### 9.5 Configuration, secrets, observability

Config through environment variables into Pydantic `Settings`, validated at
startup so a misconfiguration fails immediately and loudly. Secrets — database
URL, JWT signing key, LLM API key — from the platform's secret store, never the
repository. **The LLM key is server-side only**; the frontend never calls a
model provider directly, which is both a cost control and the reason the §6
guardrails cannot be bypassed from the client.

Structured JSON logs with a request ID, no PII. `/health` (liveness) and
`/health/ready` (database reachable) endpoints. Error tracking via Sentry or
equivalent. No metrics stack initially — request logs answer every performance
question at this scale.

### 9.6 Environments

| | Database | LLM | Data |
|---|---|---|---|
| Local | SQLite file | stub or real key | `demo` seed |
| CI | SQLite + Postgres | always stub | `minimal` seed |
| Staging | Postgres | real | `full` seed |
| Production | Postgres | real | real data |

---

## 10. Key engineering risks

**R1 — SQLite/Postgres dialect drift.** *High likelihood.* Development passes,
production fails, or worse, produces different numbers. Concrete instances:
percentile functions (§5.5), `NUMERIC` degrading to float in SQLite, foreign
keys off by default, case-sensitivity in `LIKE`, differing `NULL` ordering in
`ORDER BY`.
*Mitigation:* the §3.1 intersection rules, CI running integration tests against
Postgres, foreign keys explicitly enabled on SQLite, staging on Postgres before
production. *Accepted residual risk* — the developer-experience gain justifies
it, but this is the risk most likely to actually bite.

**R2 — Money handled as float, or currencies silently mixed.** Rounding drift
across 10,000 summed salaries becomes visible in reported totals; mixed-currency
sums are catastrophically wrong.
*Mitigation:* integer minor units at the type level, a `Money` value object that
raises on cross-currency arithmetic, `minor_unit_digits` per currency, and no
raw amount arithmetic outside `domain/money.py`.

**R3 — Effective-dating errors.** Off-by-one at interval boundaries, overlapping
records, or a forgotten `effective_to` closure double-counts an employee in
payroll cost. Silent, and plausible-looking.
*Mitigation:* exactly one resolver function used everywhere, half-open
intervals applied uniformly, the partial unique index enforcing one open record
per employee, and boundary-focused unit tests.

**R4 — FX gaps and restatement.** A missing rate defaulting to 1.0 would report
a Japanese salary as if it were dollars. Rate corrections silently restate
history.
*Mitigation:* missing rates raise, never default; month-end close rates for
stability; rate date surfaced in every response; the rate table is append-only
with corrections written as new rows.

**R5 — LLM-specific risks:** hallucinated figures presented as fact, prompt
injection through employee free-text, non-deterministic tests, cost and latency.
*Mitigation:* the entire §6 architecture. The model routes; it does not compute,
does not see data, and cannot reach the database. Always stubbed in CI. Rate
limited and logged per user.

**R6 — PII exposure.** Compensation and demographic data is among the most
sensitive data an organisation holds. Exposure routes: over-broad roles,
inference from small cohorts, PII in logs or error traces, PII in LLM prompts.
*Mitigation:* RBAC with demographics separately permissioned, mandatory
small-cohort suppression in the service layer, PII-free structured logging,
scrubbed error reporting, an audit log of sensitive reads.

**R7 — N+1 and unbounded queries.** Invisible in development against fixtures,
fatal at 10,000 rows.
*Mitigation:* query-count assertions in tests (§7.4), hard pagination caps,
explicit eager-loading strategies, and the full-scale performance smoke test.

**R8 — Analytics that are subtly wrong.** The most damaging failure this
product has. A pay-equity number that is wrong in the trusted direction could
inform a real decision about real people's pay. Unlike a crash, nothing signals
it.
*Mitigation:* pure metric functions separated from queries so each is
independently verifiable; hand-computed expected values in fixtures; showing
both adjusted and unadjusted gaps so they cross-check; surfacing cohort sizes
and methodology in the UI so a user can sanity-check rather than simply trust.

**R9 — Scope drift toward payroll.** "Can it just calculate net pay?" is the
question that turns a tractable analytics tool into a regulated multi-year
compliance project.
*Mitigation:* §0.1 states it as out of scope, in writing, up front.

**R10 — Frontend/backend contract drift.** Hand-written TypeScript types silently
diverge from Pydantic schemas after a rename.
*Mitigation:* generate TS types from the OpenAPI schema as a build step; a CI
check fails if generated types are stale.

---

## 11. Important product trade-offs

**T1 — Analytical depth over CRUD completeness.** Given finite effort, build
five analytics views that answer real compensation questions well rather than
complete CRUD over every entity. *Cost:* some entities (job families, bands)
may initially be seed- or admin-managed rather than fully editable in the UI.
*Why:* this is the product principle in `CLAUDE.md` made concrete — an
exhaustive CRUD surface is precisely what makes a tool feel like a demo.

**T2 — A constrained NL interface over an open-ended one.** Fewer answerable
questions, every answer trustworthy and auditable. *Cost:* a user asking
something outside the catalog is refused, and the demo is less dazzling than
text-to-SQL. *Why:* in compensation, a confidently wrong answer is worse than no
answer. An HR Manager who catches the tool inventing a pay gap once will never
trust any number it produces again — and trust is the entire value of an
analytics product.

**T3 — Point-in-time correctness over model simplicity.** Effective dating makes
every query harder to write than `SELECT salary FROM employees`. *Why:* it is
the difference between a compensation tool and a spreadsheet. Every question an
HR Manager asks about budget, trend, or cycle impact is a historical question,
and history that was never stored cannot be recovered later.

**T4 — Privacy over analytical granularity.** Small-cohort suppression will
blank cells the user wants to see, and at 10,000 employees across a sparse
country × level grid, that is a meaningful number of cells. *Why:* the
alternative is a dashboard that discloses individual salaries by inference to
anyone with access. Suppression is the correct default; a narrowly-scoped,
audited override for authorised comp analysts is the right escape hatch if
requirements demand one.

**T5 — Both pay-equity numbers, with explanation, over one clean headline.** Two
figures require the UI to explain the difference. *Why:* either figure alone is
misleading, in opposite directions. A tool that reports only the adjusted gap
can conceal systematic under-levelling; one that reports only the unadjusted gap
mostly measures role distribution. Showing both, with cohort sizes and
methodology, is what a credible HR tool does.

**T6 — SQLite locally over Postgres-everywhere.** Zero-setup onboarding and a
fast test loop, at the cost of R1. *Why:* the iteration-speed gain is
substantial and the drift risk is directly mitigable by running CI on Postgres.
Reversible: if drift proves painful, move local development to Postgres in
Docker.

**T7 — Analytics as read-mostly, with compensation *planning* as the write
path.** The tool records compensation changes and models proposals; the HRIS
remains the system of record (A1). *Why:* becoming the source of truth for pay
data pulls in integration, reconciliation, and compliance obligations far beyond
the scope of an analytics product.

**T8 — Deferring authentication sophistication.** Email/password with JWTs and
role-based access at first; SSO/SAML and SCIM provisioning deferred. *Why:* an
enterprise selling to a 10,000-person company will eventually require SSO, but
it is a well-understood, self-contained addition that blocks nothing. Building
it first would delay every feature that demonstrates the product's value.

**T9 — Monthly-close FX over live rates.** Figures are stable and reconcilable
but not to-the-minute current. *Why:* §5.4 — a payroll total that drifts
overnight without any compensation change is unusable for planning, and matches
neither how finance functions operate nor what the user expects.

---

## 12. Suggested build order

Incremental, per the `CLAUDE.md` workflow — each step is independently
demonstrable and testable.

1. **Foundations.** Project skeleton, settings, DB session, Alembic, CI running
   pytest and lint on both engines.
2. **Domain core.** `Money`, FX conversion, effective dating, band math — pure
   functions, fully unit tested, before any endpoint exists. This is the
   foundation everything else computes on, so it gets verified first.
3. **Schema and reference data.** Models, initial migration, currencies and
   countries.
4. **Seeder.** `minimal` and `demo` profiles. Early, because every subsequent
   step needs realistic data to build and verify against.
5. **Employees and compensation API.** Roster, detail, history, recording a
   change. First vertical slice through all layers.
6. **Bands and placement.** Compa-ratio, range penetration.
7. **Frontend shell.** Layout, auth, API client, generated types, employee list
   and detail. First point at which the product is visible.
8. **Analytics.** Payroll cost, distribution, compa-ratio, trend — API then
   dashboard.
9. **Pay equity.** Both gap measures, with suppression.
10. **`full` seed profile + performance smoke test.** Validate the §1
    assumptions against 10,000 real rows before building on them further.
11. **NL insights.** Intent catalog and stub resolver first — the whole feature
    working deterministically end-to-end — then the Claude resolver behind the
    same interface.
12. **Hardening.** RBAC, audit log, error handling, observability, deployment.

Steps 1–4 build no user-visible feature and are the ones under most pressure to
skip. They are also where every correctness risk in §10 is either mitigated or
locked in.
