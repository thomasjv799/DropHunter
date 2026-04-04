create extension if not exists "pgcrypto";

create table if not exists games (
    id uuid primary key default gen_random_uuid(),
    title text not null,
    itad_id text not null unique,
    target_price numeric null,
    added_at timestamptz not null default now()
);

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
