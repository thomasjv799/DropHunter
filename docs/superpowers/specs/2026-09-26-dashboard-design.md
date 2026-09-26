## Approved scope
Build the agreed charcoal dashboard with rounded navigation and blue/pink accents, preserving the existing Python bot and GitHub Actions sweeps. Support 50–100 tracked games per user. Google sign-in only; access requires owner approval and an explicit link to the existing Discord user ID.

## Verified starting point
Supabase contains 7 games, 1,117 price observations, 4 game alerts, 6 watches, and no Supabase Auth users. Existing rows belong to Discord IDs. DropHunter tables have RLS enabled with no browser-access policies. The project also contains unrelated application tables; do not reuse or modify those. Main is 7b3c6bc (PR #12).

## Product behavior
- Google sign-in, sign-out, pending-approval and expired-session states. An unapproved account sees no tracker data.
- Searchable game list with status filtering, sorting, and server pagination; selected-game chart with 7/30/90-day history.
- Chart labels “Best available price”, includes store/timestamp per observation, and does not fabricate history during outages. No claim of all-time low from partial history.
- Summary counts derive from the same user's latest observations; distinguish unknown/stale prices.
- Add a PC game, edit target, remove with confirmation. List watches, recent game alerts, and update the user's notification email.
- Keep demo data clearly separate from authenticated live data. Responsive layout, keyboard navigation, empty/loading/error states.
- PS5 remains a planned feature blocked by provider selection (#13). Do not simulate working console tracking.

## Architecture and security
- Separate lightweight Python web API and static web frontend; reuse the existing database and ITAD integration without exposing database/bot/service credentials.
- Supabase Google OAuth; backend verifies the access token against Supabase Auth. Use verified auth identity, never client-submitted Discord IDs or editable metadata, to determine account ownership.
- Add an application-specific approval mapping (Supabase UUID -> Discord ID) in a private schema. Owner approval/revocation via an explicit administrative command; do not auto-link by email or name. Recheck approval for each request.
- Every data query and mutation is scoped to the mapped user; inaccessible IDs return 404. Keep raw job errors and other users' activity private.
- Separate database connections for web requests; do not reuse the bot's global connection across concurrent web requests.
- Keep RLS closed to direct browser access; web API is the authorized data boundary. Restrict OAuth redirects, validate targets/emails/IDs, apply request limits, and avoid credential-bearing logs.

## Efficiency and repository quality
- Add compound game/time indexes for history and notification lookups.
- Load only the selected game's requested history window; paginate list queries and use latest-observation joins instead of per-game requests.
- Add bounded HTTP timeouts to ITAD calls. Assess further batching after measurement; do not claim speedups without evidence.
- Add pinned web dependencies/lockfile, build checks, API authorization tests, PostgreSQL integration tests, and frontend checks.
- Document architecture, local development, Google provider setup, approval commands, migrations, deployment, rollback, and secret boundaries. Ship the web service independently of the always-on bot.

## Acceptance criteria
- [ ] Issue raised in detail before implementation.
- [ ] Google login implemented; unauthorized, unapproved, revoked, and cross-user access rejected.
- [ ] 100-game fixture paginates/searches/sorts correctly; selected chart changes and date ranges constrain actual data.
- [ ] Game creation, target changes, deletion, watch listing, history, alerts, and notification email work with the user's scoped data.
- [ ] Backend errors produce safe, useful UI messages; empty and stale data are explicit.
- [ ] New migration is additive and does not touch unrelated application tables.
- [ ] Existing tracker tests and new web checks pass, including database isolation tests.
- [ ] Independent review completed; PR and deployment requirements documented.

## Deployment boundary
Implementation includes local demo, production build, API, migration, and deployment instructions. Live Google sign-in requires Google OAuth client credentials, a configured Supabase provider, an approved account mapping, and a chosen HTTPS host. These cannot be inferred from the Discord bot token. Do not expose live data through the unauthenticated design preview.
