# Cloud Tracking Implementation Plan

> Execute inline using superpowers:executing-plans, with regression tests before
> implementation and a final review before the user-authorized merge.

**Goal:** Restore portable game sweeps and complete issues #9 and #10.

**Architecture:** Existing Python entrypoints and psycopg2 data access remain.
Configuration selects the database, schema, runner and AI provider. Optional email
delivery sits alongside Discord, with operational records for each sweep.

**Tech Stack:** Python 3.11, PostgreSQL, requests, pytest, GitHub Actions.

**Spec:** ../specs/2026-09-15-cloud-tracking-design.md

## Constraints

- Preserve per-user ownership and current price deduplication.
- Never log secrets or send test messages to real recipients.
- Keep UI/SSO and percentage bounds outside this PR.
- Preserve pre-existing untracked workspace files.

## Tasks

- [ ] Database portability: in db/client.py prefer DATABASE_URL with LOCAL_DB_URL
  fallback, select DB_SCHEMA=public|drophunter, use a validated search path and
  connection timeout. Extend tests/test_db.py to catch wrong connection selection.
- [ ] Optional email: create utils/email.py with send_email(to, subject, html,
  text=None) -> bool, validate addresses, isolate failures, and add tests/test_email.py.
  Add get_user_email/set_user_email with authorization, and /setemail in bot/client.py.
- [ ] Operational logging: add an additive migration and ops.job_runs writer.
  Update cron/price_check.py to count swept rows and delivered notifications,
  continue after item errors, and return nonzero for partial failures. Cover
  commentary fallback, failed delivery, skipped recipients and accurate counts.
- [ ] OmniRoute: create ai/omniroute_provider.py; use explicit base URL, model,
  API key and bounded timeout. Exercise text, tool calls, usage and malformed/HTTP
  errors in tests/test_omniroute.py before implementation; register in ai/__init__.py.
- [ ] Deployment: update .github/workflows/price_check.yml to cloud default with
  runner/schema overrides and correct secrets. Gate watch and backup schedules.
  Add CI and real PostgreSQL integration tests. Update .env.example and README.
- [ ] Finish: run full tests and lint, inspect the final diff and migrations,
  create PR, verify GitHub checks, merge, and report deployment prerequisites or
  verify the live run when configured.

## Regression examples

```python
# Wrong connection precedence must fail.
monkeypatch.setenv("DATABASE_URL", "postgresql://cloud/db")
monkeypatch.setenv("LOCAL_DB_URL", "postgresql://local/db")
db._ensure_conn()
assert connect.call_args.args == ("postgresql://cloud/db",)

# A missing or failed AI provider must not prevent Discord delivery.
mocker.patch("cron.price_check.get_provider", side_effect=RuntimeError("unavailable"))
process_game(eligible_game)
send_dm.assert_called_once()

# A failed row must not hide the failure or prevent remaining rows being checked.
assert run(games=True, watches=False) == 1
```

## Validation commands

```sh
python -m pytest -q
ruff check .
python -m pytest tests/test_db_integration.py -q
git diff --check
```
