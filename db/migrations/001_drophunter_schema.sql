-- Creates the drophunter schema and all tables.
-- Run once against the homelab Postgres DB.
-- docker exec homelab-postgres psql -U homelab -d homelab -f /path/to/this/file

CREATE SCHEMA IF NOT EXISTS drophunter;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS drophunter.games (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id text NOT NULL,
    title text NOT NULL,
    itad_id text NOT NULL,
    target_price numeric NULL,
    added_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, itad_id)
);

CREATE INDEX IF NOT EXISTS idx_dh_games_user_id ON drophunter.games(user_id);

CREATE TABLE IF NOT EXISTS drophunter.price_history (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id uuid NOT NULL REFERENCES drophunter.games(id) ON DELETE CASCADE,
    price numeric NOT NULL,
    regular_price numeric NOT NULL,
    store text NOT NULL,
    fetched_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dh_price_history_game_id ON drophunter.price_history(game_id);

CREATE TABLE IF NOT EXISTS drophunter.notifications_log (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id uuid NOT NULL REFERENCES drophunter.games(id) ON DELETE CASCADE,
    price numeric NOT NULL,
    notified_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dh_notifications_log_game_id ON drophunter.notifications_log(game_id);

CREATE TABLE IF NOT EXISTS drophunter.chat_messages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id text NOT NULL,
    role text NOT NULL,
    content text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dh_chat_messages_user_id ON drophunter.chat_messages(user_id);

CREATE TABLE IF NOT EXISTS drophunter.chat_summary (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id text NOT NULL UNIQUE,
    summary text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS drophunter.watches (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id text NOT NULL,
    name text NOT NULL,
    brand text NULL,
    reference_no text NULL,
    target_price numeric NOT NULL,
    swisstimehouse_url text NULL,
    myntra_url text NULL,
    added_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, swisstimehouse_url)
);

CREATE INDEX IF NOT EXISTS idx_dh_watches_user_id ON drophunter.watches(user_id);

CREATE TABLE IF NOT EXISTS drophunter.watch_price_history (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    watch_id uuid NOT NULL REFERENCES drophunter.watches(id) ON DELETE CASCADE,
    swisstimehouse_price numeric NULL,
    myntra_price numeric NULL,
    fetched_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dh_watch_price_history_watch_id ON drophunter.watch_price_history(watch_id);

CREATE TABLE IF NOT EXISTS drophunter.watch_notifications_log (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    watch_id uuid NOT NULL REFERENCES drophunter.watches(id) ON DELETE CASCADE,
    price numeric NOT NULL,
    seller text NOT NULL,
    notified_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dh_watch_notifications_log_watch_id ON drophunter.watch_notifications_log(watch_id);

CREATE TABLE IF NOT EXISTS drophunter.allowed_users (
    user_id text PRIMARY KEY,
    added_by text NULL,
    added_at timestamptz NOT NULL DEFAULT now()
);
