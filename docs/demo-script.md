# Three-minute demo script

Keep the recording between 2:30 and 2:50 so there is room for natural pauses.

## Before recording

1. Copy `.env.example` to `.env` and configure an OpenAI-compatible model.
2. Run `docker compose up --build` and wait for the server to start.
3. Prepare one enabled user whose preferences include `AI agents` and `tool calling`.
4. Keep the dashboard and repository README open in separate windows.
5. Clear any failed practice runs so the history is easy to read.

## 00:00–00:25 — Problem and result

Show the dashboard. Say:

> This is AI Daily Brief, a personalized news Agent built for the KUAFUAI assignment.
> The model—not a hard-coded workflow—decides which tools to call, in what order, and
> when to stop. The surrounding application makes those decisions safe, observable,
> persistent, and schedulable.

## 00:25–00:55 — Subscription

Select the prepared user. Point out identity, topics, include keywords, exclusion terms,
timezone, and daily delivery time. Change one preference and save it. Mention that the
scheduler immediately replaces that user's timezone-aware job.

## 00:55–01:35 — Run the Agent

Start a manual digest. Open the run page and show the status changing. When it completes,
walk down the tool trace. Highlight that the sequence came from model function calls and
that each call records arguments, success/failure, latency, and a bounded result preview.

## 01:35–02:05 — Result and delivery

Open the generated digest. Show its Markdown content and cited source links. Explain that
SMTP can deliver it for real; with credentials disabled, the same flow writes a development
outbox record, keeping local development and CI credential-free.

## 02:05–02:35 — Engineering evidence

Show the README architecture and GitHub Actions badge. Say:

> The repository includes 60 deterministic tests covering alternate tool orders, recovery,
> budgets, filesystem and shell isolation, SSRF, persistence, scheduling, and the complete
> API-to-outbox workflow. CI runs lint, formatting, and tests on every push.

## 02:35–02:50 — Honest limitation

Close with:

> The take-home intentionally uses one process and SQLite for a five-minute setup. In
> production I would move jobs to a durable queue, add authentication, and use a managed
> database. Those boundaries are documented rather than hidden.

## Capture checklist

- Record at 1080p with browser zoom between 90% and 110%.
- Keep API keys, email inboxes, terminal history, and `.env` outside the frame.
- Do not cut out waiting time in a way that suggests the run completed instantly.
- Verify source links are readable before exporting.
- Export MP4/H.264 and keep the final file under the submission platform's limit.
