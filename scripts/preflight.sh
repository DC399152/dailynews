#!/bin/sh
set -eu

for forbidden in '.env' '*.db' '*.sqlite' '*.log' '*.pem' '*.key'; do
  if git ls-files --error-unmatch "$forbidden" >/dev/null 2>&1; then
    echo "Refusing submission: tracked forbidden file: $forbidden" >&2
    exit 1
  fi
done

if git grep -nEI '(sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|BEGIN (RSA|OPENSSH|EC) PRIVATE KEY)' -- . ':!uv.lock'; then
  echo 'Refusing submission: possible credential found in tracked files.' >&2
  exit 1
fi

uv run ruff check .
uv run ruff format --check .
uv run pytest
docker compose config --quiet

echo 'Preflight passed: tracked files, quality checks, tests, and Compose config are clean.'
