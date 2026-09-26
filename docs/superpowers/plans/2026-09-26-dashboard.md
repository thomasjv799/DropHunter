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
- [ ] Write tests: reject unauthenticated/unapproved access; enforce mapping and cross-user isolation.
- [ ] Run `python -m pytest tests/test_web.py -q` and observe missing implementation.
- [ ] Implement `create_app()` with injectable identity verifier and repository for HTTP tests; `Repository` with parameterized SQL and per-request connections.
- [ ] Add private account mapping and game/time indexes. Approval is an administrator CLI using the Supabase UUID and Discord ID.
- [ ] Run unit tests and database contract tests.

## Task 2 — dashboard and authentication UI
Files: frontend/package.json, frontend/package-lock.json, frontend/src/*, frontend/index.html.
- [ ] Add node tests for chart series, missing/stale prices and safe URL handling; run `npm test` red.
- [ ] Build login, pending approval, game pagination/search/filter/sort, selected-game chart, add/edit/remove, watches, activity, notification email.
- [ ] Use PKCE Supabase Google login and Authorization headers. Render text through DOM APIs, not raw API-supplied HTML.
- [ ] Run frontend tests/build and browser smoke checks with explicit demo mode.

## Task 3 — reliability, packaging, docs, review
Files: utils/itad.py, requirements-web.txt, Dockerfile.web, .github/workflows/ci.yml, docs/dashboard.md, README.md.
- [ ] Test and add bounded ITAD HTTP timeouts.
- [ ] Package separately from the bot; document provider configuration, migration, approval/revocation, deployment, rollback.
- [ ] Run full pytest/ruff/build and PostgreSQL contracts; request independent security/correctness review.
- [ ] Fix findings; create PR, wait for CI, merge only after checks pass under prior user authorization.
