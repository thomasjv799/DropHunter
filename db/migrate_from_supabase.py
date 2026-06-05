"""
One-time migration: reads all data from Supabase via REST API,
writes it to the local Postgres drophunter schema via psycopg2.

Run once:
    python -m db.migrate_from_supabase

Requires both SUPABASE_URL + SUPABASE_KEY and LOCAL_DB_URL in .env.
Safe to re-run — uses ON CONFLICT DO NOTHING so existing rows are skipped.
"""

import logging
import os

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("migrate")

load_dotenv()


def _supa():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])


def _local():
    conn = psycopg2.connect(os.environ["LOCAL_DB_URL"])
    conn.autocommit = True
    return conn


def _fetch_all(client, table: str) -> list:
    rows = []
    offset = 0
    batch = 1000
    while True:
        result = client.table(table).select("*").range(offset, offset + batch - 1).execute()
        rows.extend(result.data)
        if len(result.data) < batch:
            break
        offset += batch
    log.info("  fetched %d rows from %s", len(rows), table)
    return rows


def _insert(cur, table: str, rows: list, conflict_col: str = "id") -> int:
    if not rows:
        return 0
    cols = list(rows[0].keys())
    placeholders = ", ".join(["%s"] * len(cols))
    col_str = ", ".join(f'"{c}"' for c in cols)
    sql = (
        f"INSERT INTO drophunter.{table} ({col_str}) VALUES ({placeholders}) "
        f"ON CONFLICT ({conflict_col}) DO NOTHING"
    )
    count = 0
    for row in rows:
        cur.execute(sql, [row[c] for c in cols])
        count += cur.rowcount
    return count


def migrate():
    client = _supa()
    conn = _local()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Insert order respects FK dependencies
    steps = [
        ("allowed_users", "user_id"),
        ("games", "id"),
        ("watches", "id"),
        ("price_history", "id"),
        ("notifications_log", "id"),
        ("watch_price_history", "id"),
        ("watch_notifications_log", "id"),
        ("chat_summary", "id"),
        ("chat_messages", "id"),
    ]

    total = 0
    for table, conflict_col in steps:
        log.info("Migrating %s ...", table)
        rows = _fetch_all(client, table)
        inserted = _insert(cur, table, rows, conflict_col)
        log.info("  inserted %d new rows into drophunter.%s", inserted, table)
        total += inserted

    cur.close()
    conn.close()
    log.info("Migration complete. %d rows inserted total.", total)


if __name__ == "__main__":
    migrate()
