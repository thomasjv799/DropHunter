"""
Syncs local Postgres data to Supabase (backup).
Covers: drophunter schema (DropHunter) + public schema (Smart Reminder vehicles).
Runs every 3 days via GitHub Actions (supabase_backup.yml).

Strategy: upsert-only — inserts new rows and updates existing ones by primary key.
Rows deleted locally are NOT deleted from Supabase (Supabase acts as a cold archive).
"""

import logging
import os
from datetime import date, datetime, timezone
from decimal import Decimal

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from supabase import create_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("supabase_backup")

load_dotenv()

# drophunter schema tables — FK dependency order. (table, conflict_cols)
DROPHUNTER_TABLES = [
    ("allowed_users", "user_id"),
    ("games", "user_id,itad_id"),
    ("watches", "user_id,swisstimehouse_url"),
    ("price_history", "id"),
    ("notifications_log", "id"),
    ("watch_price_history", "id"),
    ("watch_notifications_log", "id"),
    ("chat_summary", "user_id"),
    ("chat_messages", "id"),
]

# public schema tables — FK dependency order. (table, conflict_cols)
PUBLIC_TABLES = [
    ("vehicles", "id"),
    ("reminder_log", "id"),
    ("reminder_snooze", "id"),
]

BATCH_SIZE = 500


def _local_conn():
    return psycopg2.connect(os.environ["LOCAL_DB_URL"])


def _serialize(row) -> dict:
    d = {}
    for k, v in row.items():
        if isinstance(v, (datetime, date)):
            d[k] = v.isoformat()
        elif isinstance(v, Decimal):
            d[k] = float(v)
        else:
            d[k] = v
    return d


def _fetch_local(conn, schema: str, table: str) -> list:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(f"SELECT * FROM {schema}.{table}")
        return [_serialize(row) for row in cur.fetchall()]


def _upsert_batch(client, table: str, rows: list, conflict: str) -> int:
    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        client.table(table).upsert(batch, on_conflict=conflict).execute()
        total += len(batch)
    return total


def _backup_section(client, conn, label: str, schema: str, tables: list) -> int:
    log.info("-- %s --", label)
    total = 0
    for table, conflict in tables:
        rows = _fetch_local(conn, schema, table)
        if not rows:
            log.info("  %s: 0 rows, skipping", table)
            continue
        count = _upsert_batch(client, table, rows, conflict)
        log.info("  %s: upserted %d rows", table, count)
        total += count
    return total


def run_backup():
    log.info("=== Supabase backup started ===")
    start = datetime.now(timezone.utc)

    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    conn = _local_conn()

    total_rows = 0
    try:
        total_rows += _backup_section(client, conn, "DropHunter (drophunter schema)", "drophunter", DROPHUNTER_TABLES)
        total_rows += _backup_section(client, conn, "Smart Reminder (public schema)", "public", PUBLIC_TABLES)
    finally:
        conn.close()

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    log.info("=== Backup complete: %d rows in %.1fs ===", total_rows, elapsed)


if __name__ == "__main__":
    run_backup()
