# Interview notes

Use these as prompts, not a script to memorize. Be ready to point to the relevant code and
explain it in your own words.

## One-minute project explanation

AI Daily Brief is a small Agent product rather than a fixed news pipeline. A handwritten
function-calling loop sends the goal and tool schemas to an OpenAI-compatible model. The
model can call any registered tool repeatedly and receives a structured observation after
each call. The application adds execution budgets, tool policies, persistence, trace views,
daily scheduling, and a browser workflow around that loop.

## Why these choices?

### Why hand-write the Agent Loop?

The assignment's main signal is whether the LLM controls tool order. A small loop makes
that behavior visible and testable without framework internals. Tests prove the same loop
can follow different valid tool sequences solely because the fake model requests them.

### Why FastAPI + Jinja instead of a SPA?

The interface only needs subscription editing, manual execution, history, and trace views.
Server-rendered entry pages plus small JavaScript files avoid a second build system and keep
the review focused on Agent behavior.

### Why SQLite and an in-process scheduler?

They make the reviewer setup genuinely short. Database migrations, service boundaries, and
the run coordinator leave a clear path to PostgreSQL and a durable worker. The current
single-process limitation is explicit.

### Why RSS and a development outbox?

Both make the full workflow usable without extra paid services. RSS is real input; SMTP is
supported when configured. The outbox provides a deterministic fallback for local runs and
CI.

## Agent behavior and failure handling

- `AgentLoop` owns turns, tool-call count, run timeout, per-tool timeout, messages, and trace.
- `ToolRegistry` validates model arguments with Pydantic and converts expected failures into
  structured observations, allowing the model to choose a safe alternative.
- Protocol errors and exhausted budgets terminate the run with typed errors and retained
  trace data.
- `DigestService` guarantees that ordinary failures reach a terminal database state and
  persists completed tool-call pairs for inspection.
- A partial unique index prevents two active runs for one user even if requests race.

## Security points worth demonstrating

- Filesystem tools resolve every path under one workspace and reject traversal and symlink
  escapes.
- The shell accepts one allowlisted executable, rejects shell syntax, filters the environment,
  caps output, and enforces a timeout.
- Article fetching rejects credentials, nonstandard ports, private/reserved IPs, unsafe
  redirects, unsupported content types, and oversized bodies.
- Retrieved pages and tool results are treated as untrusted data in the system prompt.
- Secrets come only from environment variables and `.env` is ignored.

## Evaluation and testing story

The tests replace external nondeterminism rather than internal business logic. A scripted
model makes tool decisions reproducible; fake news removes network variance; the real API,
Agent Loop, registry, filesystem, outbox, database, and migrations remain in the path. The
suite also tests failure recovery, all budgets, security boundaries, preference filtering,
scheduling, and database constraints. GitHub Actions runs the same locked environment.

## Bugs and gaps found during development

- The initial product plan relied too much on model-only preference filtering. Day 5 added
  deterministic include/exclude filtering inside `search_news` while preserving model control.
- API and scheduler run creation originally risked diverging. Both now use one
  `DigestRunCoordinator` and the same active-run constraint.
- Run responses originally depended on relationship loading. Digest IDs are now queried
  explicitly, avoiding lazy-loading surprises after sessions close.
- External tools needed stronger boundaries than file operations. Redirect targets, response
  sizes, shell syntax, environment leakage, and symlink escape now have dedicated tests.

## What I would build next

1. Transactional outbox plus durable queue/worker and idempotent delivery.
2. Authentication and per-user authorization.
3. PostgreSQL, production observability, retry policy, and alerting.
4. A durable append-only Agent event log and checkpoint/resume.
5. A small evaluation set for relevance, citation correctness, and preference adherence.

## AI-assisted development disclosure

AI coding tools were used to accelerate scaffolding, tests, and documentation. The important
engineering work was defining the boundaries, reviewing generated code, running deterministic
checks, correcting unsafe or unverifiable behavior, and documenting trade-offs. In an
interview, describe only decisions and code paths you have personally reviewed and can explain.
