# AI Daily Brief

AI Daily Brief is a personalized AI-news assistant built for the KUAFUAI Agent
development take-home assignment. A user describes who they are and what they care
about; a model-driven agent then chooses which tools to call, gathers recent news,
creates a cited digest, and delivers it on a schedule.

The project is intentionally scoped as a small, reviewable product. The central
technical requirement is a real function-calling loop: tool order, repetition, and
termination are decided by the model rather than encoded as a fixed pipeline.

## Current status

Day 0 through Day 4 are complete. The repository now includes the engineering
baseline, model-driven Agent Loop, all nine tools, persistent SQLAlchemy models,
Alembic migrations, a database-backed subscription provider, run orchestration, and
REST APIs for users, subscriptions, runs, traces, and digests. A responsive web UI
supports profile creation, subscription editing, manual runs, live status, trace
inspection, and digest history. APScheduler registers one timezone-aware daily job per
enabled subscription.

The Loop deliberately has no news-specific branching. Tests demonstrate that the
same runtime follows `search -> write` or `write -> search` solely from model tool
calls, then returns each structured observation to the model before its next turn.

## MVP

A user will be able to:

- enter an identity, topics, keywords, exclusions, email, timezone, and delivery time;
- create or update a subscription;
- manually trigger a digest and receive one on a daily schedule;
- inspect historical digests, cited sources, and an execution trace.

The agent will be able to:

- decide dynamically which tool to call and when to stop;
- use the five required filesystem/shell tools plus news and delivery tools;
- recover from ordinary tool errors within fixed turn, call, and time budgets;
- persist its run status and tool-call trace for debugging.

## Explicit non-goals

The first submission will not include multi-agent orchestration, RAG/vector search,
complex authentication, Redis/Celery/Kafka, a JavaScript SPA, or durable process
resume. These would dilute the assignment's core signal and the one-week delivery
budget.

## Tool surface

Required by the assignment:

```text
list_dir(path)
read_file(path)
search_content(keyword, dir)
write_file(path, content)
bash(command)
```

Product tools:

```text
get_subscription(user_id)
search_news(query, hours, limit)
fetch_article(url)
send_digest(user_id, subject, content)
```

All filesystem access is confined to `workspace/`. Shell execution uses a command
allowlist, fixed working directory, timeout, output cap, and filtered environment.
Article fetching rejects private-network targets and caps response size. See
[`docs/tool-security.md`](docs/tool-security.md) for precise controls and limitations.

## Architecture

```text
Browser (Jinja + vanilla JS)
              |
              v
          FastAPI API ----> SQLite
              |               |
              v               +--> subscriptions / digests / traces
       Digest Service
              |
              v
  LLM <--> Agent Loop <--> Tool Registry
                             |  |  |  |
              filesystem / shell / news / delivery
```

See [`docs/architecture.md`](docs/architecture.md) for the decisions and boundaries.

## Local development

Prerequisites: Python 3.11–3.13 and [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Open `http://localhost:8000/docs` or check:

```bash
curl http://localhost:8000/health
```

The user-facing dashboard is at `http://localhost:8000/`.

Run quality checks:

```bash
uv run ruff check .
uv run pytest
```

## Docker

```bash
cp .env.example .env
docker compose up --build
```

Runtime database and workspace files are stored in the local `data/` and
`workspace/` directories and are ignored by Git. The container applies Alembic
migrations before starting Uvicorn.

## API workflow

After startup, use `http://localhost:8000/docs` to execute the complete backend flow:

```text
POST /api/users
PUT  /api/users/{user_id}/subscription
POST /api/users/{user_id}/digest-runs
GET  /api/runs/{run_id}
GET  /api/runs/{run_id}/tool-calls
GET  /api/users/{user_id}/digests
GET  /api/digests/{digest_id}
```

Starting a run returns `202 Accepted`. The in-process background task moves it through
`pending`, `running`, and a terminal `completed` or `failed` state. A partial unique
database index prevents the same user from having two active runs.

## Scheduling

Each enabled subscription is registered as an APScheduler `CronTrigger` using the
user's IANA timezone and selected delivery time. Jobs are synchronized on application
startup and immediately after subscription updates. Disable scheduling for tests or
API-only development with `SCHEDULER_ENABLED=false`.

The scheduler and background execution are intentionally single-process for this
take-home. A production multi-replica deployment should replace them with a durable
queue and transactional outbox.

## Configuration and secrets

Copy `.env.example` to `.env`. Never commit `.env` or API credentials. The model
client will use an OpenAI-compatible API configured through `LLM_API_KEY`,
`LLM_BASE_URL`, and `LLM_MODEL`. With SMTP disabled, delivery will write to a local
development outbox so the complete flow remains testable without mail credentials.

## Delivery plan

The ordered implementation backlog and acceptance criteria are in
[`docs/backlog.md`](docs/backlog.md). Development is intentionally incremental: each
feature must remain runnable, tested, and reviewable before the next feature begins.

## Test coverage

The test suite does not require model, news, or SMTP credentials. It covers alternate
model-selected tool orders, Agent budgets, argument validation, tool recovery,
workspace traversal and symlink escape, restricted commands, RSS freshness and
deduplication, SSRF and redirect checks, streamed response limits, outbox delivery,
and a complete Agent Loop using the real workspace tools.
