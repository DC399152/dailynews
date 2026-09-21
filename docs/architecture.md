# Architecture decisions

## Product boundary

This repository demonstrates two capabilities at once: a model-controlled Agent Loop
and the engineering required to ship it as a small web product. It is not intended to
be a general-purpose agent framework or a second version of FreeToCode.

## ADR-001: Hand-written function-calling loop

**Decision:** Implement the core loop directly on top of an OpenAI-compatible model
API rather than hiding it behind LangChain or LangGraph.

**Why:** The assignment explicitly evaluates whether the model decides tool order,
repetition, and termination. A small loop is easier to explain, trace, test with a
fake model, and review for failure conditions.

**Required controls:** maximum turns, maximum tool calls, wall-clock timeout, validated
tool arguments, captured errors, and a deterministic fake-model test suite.

## ADR-002: FastAPI with server-rendered pages

**Decision:** Use FastAPI, Jinja2, and small amounts of vanilla JavaScript.

**Why:** A separate SPA would add a second build system without strengthening the
Agent signal. Server-rendered pages are sufficient for subscription editing, manual
runs, history, and trace inspection.

## ADR-003: SQLite for the submission

**Decision:** Use SQLite through SQLAlchemy and Alembic.

**Why:** Option A does not require MySQL. SQLite makes the five-minute setup goal
realistic while migrations and a repository/service boundary preserve a future path
to PostgreSQL or MySQL.

## ADR-004: RSS-first news discovery

**Decision:** Provide an RSS-backed `search_news` tool, with an optional external
search provider added only if time permits.

**Why:** Reviewers must be able to run the project without another paid API. The LLM
still decides search queries, repetition, selection, and article retrieval.

## ADR-005: SMTP with a development outbox

**Decision:** Use SMTP for real delivery and a local outbox when SMTP is disabled.

**Why:** Email clearly satisfies the push requirement, while the outbox keeps local
and CI runs deterministic and credential-free.

## Runtime flow

1. A manual action or scheduler creates an `AgentRun` for a user.
2. The digest service supplies the goal and user identifier to the Agent Loop.
3. The model returns zero or more function calls.
4. The registry validates each call, executes the tool, and records its result.
5. Tool observations are returned to the model for the next turn.
6. A final answer is persisted as a digest and delivered through the chosen tool.
7. Budget exhaustion or an unrecoverable error closes the run with a clear status.

## Implemented Agent runtime

The Day 1 runtime is split across four small boundaries:

- `app.agent.model.ModelClient`: provider-neutral async protocol;
- `OpenAICompatibleModelClient`: translates internal messages and JSON Schema tools;
- `app.tools.registry.ToolRegistry`: validates arguments and normalizes tool outcomes;
- `app.agent.loop.AgentLoop`: owns conversation state, budgets, observations, and trace.

Expected tool failures—including unknown tools, invalid arguments, handler exceptions,
and per-tool timeouts—are returned to the model as structured observations so it can
recover. Invalid model responses and exhausted run budgets instead raise typed errors
that retain the trace and counters accumulated before failure.

## Planned persistence

- `users`: identity, email, timezone;
- `subscriptions`: topics, keywords, exclusions, delivery time, enabled state;
- `digests`: content, cited sources, status, delivery timestamp;
- `agent_runs`: model, status, budgets, timing, final error;
- `tool_calls`: turn, name, validated arguments, result preview, latency, success.

## Operational limitations

The submission scheduler is designed for one application process. A production
multi-replica deployment would move scheduling and jobs to a dedicated worker and
queue. This trade-off is deliberate and will be documented rather than disguised.

The subscription tool currently depends on a small provider protocol and uses an
in-memory implementation in the default factory. Day 3 will replace that provider
with the SQLAlchemy repository without changing the Agent-facing tool contract.

RSS endpoints are trusted application configuration, not model-controlled URLs.
Article URLs are model-controlled and therefore receive stricter validation. DNS
addresses and every redirect target are checked before requests, although preventing
DNS rebinding completely would require a transport that pins the validated address.
