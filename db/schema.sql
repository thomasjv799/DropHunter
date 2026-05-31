create extension if not exists "pgcrypto";

create table if not exists games (
    id uuid primary key default gen_random_uuid(),
    user_id text not null,
    title text not null,
    itad_id text not null,
    target_price numeric null,
    added_at timestamptz not null default now(),
    unique (user_id, itad_id)
);

create index if not exists idx_games_user_id on games(user_id);

create table if not exists price_history (
    id uuid primary key default gen_random_uuid(),
    game_id uuid not null references games(id) on delete cascade,
    price numeric not null,
    regular_price numeric not null,
    store text not null,
    fetched_at timestamptz not null default now()
);

create table if not exists notifications_log (
    id uuid primary key default gen_random_uuid(),
    game_id uuid not null references games(id) on delete cascade,
    price numeric not null,
    notified_at timestamptz not null default now()
);

create index if not exists idx_price_history_game_id on price_history(game_id);
create index if not exists idx_notifications_log_game_id on notifications_log(game_id);

create table if not exists chat_messages (
    id uuid primary key default gen_random_uuid(),
    user_id text not null,
    role text not null,
    content text not null,
    created_at timestamptz not null default now()
);

create table if not exists chat_summary (
    id uuid primary key default gen_random_uuid(),
    user_id text not null unique,
    summary text not null,
    updated_at timestamptz not null default now()
);

create index if not exists idx_chat_messages_user_id on chat_messages(user_id);

create table if not exists watches (
    id uuid primary key default gen_random_uuid(),
    user_id text not null,
    name text not null,
    brand text null,
    reference_no text null,
    target_price numeric not null,
    swisstimehouse_url text null,
    myntra_url text null,
    added_at timestamptz not null default now(),
    unique (user_id, swisstimehouse_url)
);

create index if not exists idx_watches_user_id on watches(user_id);

create table if not exists watch_price_history (
    id uuid primary key default gen_random_uuid(),
    watch_id uuid not null references watches(id) on delete cascade,
    swisstimehouse_price numeric null,
    myntra_price numeric null,
    fetched_at timestamptz not null default now()
);

create table if not exists watch_notifications_log (
    id uuid primary key default gen_random_uuid(),
    watch_id uuid not null references watches(id) on delete cascade,
    price numeric not null,
    seller text not null,
    notified_at timestamptz not null default now()
);

create index if not exists idx_watch_price_history_watch_id on watch_price_history(watch_id);
create index if not exists idx_watch_notifications_log_watch_id on watch_notifications_log(watch_id);

create table if not exists allowed_users (
    user_id text primary key,
    added_by text null,
    added_at timestamptz not null default now()
);
