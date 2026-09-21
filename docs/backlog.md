# Implementation backlog

Each milestone has a runnable exit condition. Tasks should be completed in order.

## Day 0 — Engineering baseline

- [x] Define MVP, non-goals, architecture, and security boundaries.
- [x] Initialize the Python package and application directories.
- [x] Add environment-based configuration without committed secrets.
- [x] Add a health endpoint and first automated test.
- [x] Add Docker and Compose definitions.
- [x] Add lint and test configuration.
- [x] Verify the container build and `/health` endpoint through Docker Compose.

Exit condition: `uv run ruff check .` and `uv run pytest` pass; application exposes
`GET /health`; Compose configuration validates.

## Day 1 — Model-driven Agent Loop

- [x] Define model messages, tool-call requests, observations, and final result types.
- [x] Implement a model-client protocol and OpenAI-compatible adapter.
- [x] Implement a Tool Registry with Pydantic argument validation.
- [x] Implement the loop with turn, tool-call, and wall-clock budgets.
- [x] Add structured in-memory trace events.
- [x] Build a scripted FakeModel for deterministic tests.
- [x] Prove two tests can choose different valid tool orders without changing loop code.

Exit condition: a fake model can call multiple registered tools, consume their
observations, stop by itself, and fail clearly when a budget is exhausted.

## Day 2 — Safe tools

- [x] Implement `list_dir`, `read_file`, `search_content`, and `write_file`.
- [x] Reject absolute paths, traversal, symlink escape, and oversized I/O.
- [x] Implement restricted `bash` with allowlist, timeout, output cap, and clean env.
- [x] Implement RSS-backed `search_news` with freshness and result limits.
- [x] Implement `fetch_article` with SSRF, timeout, type, and size checks.
- [x] Implement subscription lookup and SMTP/development-outbox delivery tools.
- [x] Add success, invalid-input, and failure tests for every tool.

Exit condition: all nine tools are registered and tested; unsafe file, shell, and URL
inputs are rejected.

## Day 3 — Persistence and API workflow

- [x] Add SQLAlchemy models for users, subscriptions, digests, runs, and tool calls.
- [x] Add Alembic and the initial migration.
- [x] Add subscription create/read/update endpoints.
- [x] Add manual digest-run endpoint and status endpoint.
- [x] Persist run transitions, tool calls, sources, and completed digests.
- [x] Prevent duplicate active runs for the same user.

Exit condition: an API request launches a real agent run and its complete outcome can
be read back from SQLite.

## Day 4 — Web UI and scheduling

- [x] Add subscription form and validation feedback.
- [x] Add manual-run action and visible run status.
- [x] Add digest history/detail pages with source links.
- [x] Add a concise trace inspection view.
- [x] Add timezone-aware daily scheduling with documented single-process semantics.

Exit condition: the required user journey works entirely from the browser.

## Day 5 — Reliability and CI

- [x] Test tool failure recovery and budget exhaustion.
- [x] Test path traversal, unsafe commands, private URLs, and oversized content.
- [x] Test news deduplication and preference-based filtering.
- [x] Add API/database integration tests.
- [x] Add a credential-free end-to-end test using fake model, news, and delivery.
- [x] Add GitHub Actions for Ruff and pytest.

Exit condition: CI passes and the complete mocked workflow is deterministic.

## Day 6 — Submission

- [ ] Test README setup from a clean checkout.
- [ ] Build and run the container.
- [ ] Audit tracked files and logs for credentials or personal data.
- [ ] Add screenshots, final architecture diagram, trade-offs, and limitations.
- [ ] Record a three-minute demo following a prepared script.
- [ ] Prepare interview notes covering decisions, AI-assisted work, and corrected bugs.

Exit condition: a reviewer can start the project in five minutes and reproduce the
demonstrated workflow.
