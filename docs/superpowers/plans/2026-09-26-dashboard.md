# DropHunter dashboard implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement task-by-task. User explicitly authorized starting after issue #11 was expanded.

**Goal:** Ship an independently deployable dashboard with Google authentication and owner-approved Discord account linking.
**Architecture:** Flask serves a bundled Vite frontend and a same-origin JSON API. Supabase Auth verifies identity; a private approval table determines authorization. Each web request uses its own database transaction.
**Tech stack:** Python 3.11+, Flask, psycopg2, Vite, vanilla JavaScript, Supabase JS.
**Spec:** ../specs/2026-09-26-dashboard-design.md; GitHub issue #11.

## Global constraints
- Existing bot and GitHub sweeps remain operational; public/drophunter database schemas supported.
- 100 tracked games per user; server pagination capped at 50 rows; 7/30/90-day selected-game charts.
- Google sign-in, approved users only; never auto-link by email or trust a request's user ID.
- Browser sees only a Supabase publishable key. Database credentials remain server-side.
- No modifications to unrelated public tables. No live migration until tests and review pass.

## Review focus
- Forged/expired tokens and revoked mappings must not expose data: API auth tests.
- Cross-user record IDs must return 404: PostgreSQL and API tests.
- Missing, stale, and sparse history must remain explicit: frontend model tests.
- Negative/nonfinite prices, malformed JSON and huge limits must be rejected: API tests.
- Network failures and duplicate submissions must not create false success: HTTP/UI checks.

## Task 1 — identity, approval, and scoped data
Files: web/auth.py, web/repository.py, web/admin.py, supabase/migrations/*, tests/test_web.py, tests/test_web_integration.py.
- [x] Write tests: reject unauthenticated/unapproved access; enforce mapping and cross-user isolation.
- [x] Run `python -m pytest tests/test_web.py -q` and observe missing implementation.
- [x] Implement `create_app()` with injectable identity verifier and repository for HTTP tests; `Repository` with parameterized SQL and per-request connections.
- [x] Add private account mapping and game/time indexes. Approval is an administrator CLI using the Supabase UUID and Discord ID.
- [x] Run unit tests and database contract tests.

## Task 2 — dashboard and authentication UI
Files: frontend/package.json, frontend/package-lock.json, frontend/src/*, frontend/index.html.
- [x] Add node tests for chart series, missing/stale prices and safe URL handling; run `npm test` red.
- [x] Build login, pending approval, game pagination/search/filter/sort, selected-game chart, add/edit/remove, watches, activity, notification email.
- [x] Use PKCE Supabase Google login and Authorization headers. Render text through DOM APIs, not raw API-supplied HTML.
- [x] Run frontend tests/build and browser smoke checks with explicit demo mode.

## Task 3 — reliability, packaging, docs, review
Files: utils/itad.py, requirements-web.txt, Dockerfile.web, .github/workflows/ci.yml, docs/dashboard.md, README.md.
- [x] Test and add bounded ITAD HTTP timeouts.
- [x] Package separately from the bot; document provider configuration, migration, approval/revocation, deployment, rollback.
- [x] Run full pytest/ruff/build and PostgreSQL contracts; request independent security/correctness review.
- [x] Fix findings; create PR, wait for CI, merge only after checks pass under prior user authorization.

## Execution record
- Scope and implementation authorized by user after detailed issue #11, without another design-approval stop.
- Chose a feature branch in the current checkout; preserved pre-existing untracked files.
- Backend/access tests written before implementation; target validation, token rejection, signed selections and revocation covered.
- Independent review: corrected email-save permission restoration; bounded search timeouts and removed web retries; discarded stale search/workspace responses; added and observed a failing browser regression for demo session isolation before fixing it.
- Initial CI: 204 Python/PostgreSQL tests, 6 frontend unit tests, 4 browser tests passed. Added fifth browser regression subsequently.
- Local Docker is offline; real PostgreSQL 17 validation runs in GitHub CI for both tracker schemas.
- Production Google setup, HTTPS host, migration application, and approval mapping remain activation steps; no live database changes made.
