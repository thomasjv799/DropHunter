-- Additive: use the active tracker schema. Unrelated public tables are untouched.
BEGIN;
CREATE SCHEMA IF NOT EXISTS dashboard;
REVOKE ALL ON SCHEMA dashboard FROM PUBLIC;
CREATE TABLE IF NOT EXISTS dashboard.accounts (
    auth_id uuid PRIMARY KEY,
    discord_id text NOT NULL UNIQUE CHECK (discord_id ~ '^[0-9]{5,25}$'),
    approved boolean NOT NULL DEFAULT false,
    approved_at timestamptz,
    approved_by text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE dashboard.accounts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON dashboard.accounts FROM PUBLIC;
-- A trusted server role/table owner is required; no client-facing policies.
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
        REVOKE ALL ON SCHEMA dashboard FROM anon;
        REVOKE ALL ON dashboard.accounts FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
        REVOKE ALL ON SCHEMA dashboard FROM authenticated;
        REVOKE ALL ON dashboard.accounts FROM authenticated;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_price_history_game_time
    ON price_history (game_id, fetched_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_game_time
    ON notifications_log (game_id, notified_at DESC);
CREATE INDEX IF NOT EXISTS idx_watch_history_watch_time
    ON watch_price_history (watch_id, fetched_at DESC, id DESC);
COMMIT;
