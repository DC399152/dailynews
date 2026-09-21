# Submission checklist

## Automated evidence

- [x] Ruff lint and formatting checks pass.
- [x] All 60 tests pass without model, RSS, or SMTP credentials.
- [x] GitHub Actions passes on the public repository.
- [x] Docker image builds successfully.
- [x] A clean repository clone applies migrations and reaches Uvicorn application startup.
- [x] Alembic can create the schema from an empty database.
- [x] No `.env`, database, log, private key, or real credential is tracked.

## Manual evidence still required

- [ ] Open the dashboard at `http://localhost:8000/` and complete one real-model run.
- [ ] Capture `docs/screenshots/dashboard.png` with a configured subscription.
- [ ] Capture `docs/screenshots/run-trace.png` with a completed multi-tool trace.
- [ ] Capture `docs/screenshots/digest.png` with sources visible.
- [ ] Follow `docs/demo-script.md` and record a video shorter than three minutes.
- [ ] Watch the exported video once and verify no secret or personal inbox is visible.

The screenshots and video must represent a real run. Do not use mock content or fabricated
screens for the final submission.

## Final repository review

- [ ] Replace placeholder Git author metadata if desired before submission.
- [ ] Confirm the CI badge is green on the repository front page.
- [ ] Test the public repository link in a private browser window.
- [ ] Add the video link to the submission email or repository README.
- [ ] Submit the repository link, resume, and “Option A” label.
