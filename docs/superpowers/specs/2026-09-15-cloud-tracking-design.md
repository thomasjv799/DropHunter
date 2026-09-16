# Cloud game tracking and notification extensions

## Approved scope

Restore scheduled game tracking on GitHub-hosted Actions using the existing
Supabase database. Preserve self-hosted operation. Add issues #9 (Resend email
and job logging) and #10 (OmniRoute configuration). Defer #8 and #11. The user
authorized implementation, PR creation, review, tests, and merge.

## Database and scheduling

Keep psycopg2 and the existing SQL operations. Prefer DATABASE_URL, falling back
to LOCAL_DB_URL. DB_SCHEMA selects public (the existing Supabase backup) or
drophunter (the home-server installation); default to drophunter locally.
Configure the connection search path with pg_catalog first and a validated
schema. Use a session pooler with TLS from GitHub-hosted runners. Do not copy,
delete, or merge live watchlists: the Supabase snapshot is the cloud source.

The game workflow runs every 12 hours on ubuntu-latest by default. Repository
variables select another runner/schema and can disable the schedule. Watch and
backup workflows stay opt-in on self-hosted runners, avoiding queued jobs or
overwriting cloud data from a stale home-server copy. Manual runs remain available
when those workflows are enabled. CI runs independently of deployment secrets.

## Email and operational visibility

Add nullable email on allowed_users in the selected schema. Authorized users,
including the owner, register their own address through /setemail; this must not
grant access to an unapproved user. Keep the command ready for the bot's return.
The owner can insert their own allowlist row to store an address. Revocation
removes the row and address together.

Resend is optional and never breaks Discord delivery. Use the same deal and
deduplication rules for both channels, escape HTML, and keep credentials and email
addresses out of logs. Preserve notification history only after successful
Discord delivery. Record one ops.job_runs row per sweep with timestamps, status,
error types, and counts. Continue through individual item failures but return a
failing process status so Actions does not silently show success. AI commentary
failure must not suppress a real price alert.

Migrations are additive, transactional, and support either existing schema. RLS
protects new tables; access is server-side. Existing unrelated application tables
in Supabase are outside scope.

## OmniRoute

Add an AIProvider implementation using its OpenAI-compatible chat/completions
endpoint, selected by AI_PROVIDER=omniroute. Configure base URL, model, API key,
and request timeout. Normalize text, tool calls, and token usage to the existing
provider contract. Reject malformed responses instead of executing invalid tools.
Use HTTPS remotely and allow HTTP only for loopback development. Do not assume
the home-server OmniRoute endpoint is reachable from Actions.

## Validation and rollout

Run existing tests first; add regression tests for connection selection,
authorization, email failure isolation, run failures, and provider response
normalization. Add a real PostgreSQL integration test for migrations and per-user
queries. Validate workflows, run CI on the PR, review the final diff, then merge
after checks pass. Verify a cloud run only when deployment secrets are available.
Missing secrets must be reported explicitly, without claiming a live deployment.
