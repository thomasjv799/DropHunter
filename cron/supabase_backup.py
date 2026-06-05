"""
Syncs the local drophunter Postgres schema to Supabase (backup).
Runs every 3 days via crontab.

Crontab entry (run at 03:00 every 3 days):
    0 3 */3 * * cd /home/thomas/repos/DropHunter && python -m cron.supabase_backup >> /var/log/drophunter_backup.log 2>&1

Strategy: upsert-only — inserts new rows and updates existing ones by primary key.
Rows deleted locally are NOT deleted from Supabase (Supabase acts as a cold archive).
"""

import logging
import os
from datetime import datetime, timezone

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

# Tables in FK dependency order. Each entry: (table_name, upsert_conflict_cols)
TABLES = [
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

BATCH_SIZE = 500


def _local_conn():
    return psycopg2.connect(os.environ["LOCAL_DB_URL"])


def _fetch_local(conn, table: str) -> list:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(f"SELECT * FROM drophunter.{table}")
        rows = cur.fetchall()
    result = []
    for row in rows:
        d = {}
        for k, v in row.items():
            d[k] = v.isoformat() if isinstance(v, datetime) else v
        result.append(d)
    return result


def _upsert_batch(client, table: str, rows: list, conflict: str) -> int:
    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        client.table(table).upsert(batch, on_conflict=conflict).execute()
        total += len(batch)
    return total


def run_backup():
    log.info("=== DropHunter Supabase backup started ===")
    start = datetime.now(timezone.utc)

    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    conn = _local_conn()

    total_rows = 0
    try:
        for table, conflict in TABLES:
            rows = _fetch_local(conn, table)
            if not rows:
                log.info("  %s: 0 rows, skipping", table)
                continue
            count = _upsert_batch(client, table, rows, conflict)
            log.info("  %s: upserted %d rows", table, count)
            total_rows += count
    finally:
        conn.close()

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    log.info("=== Backup complete: %d rows in %.1fs ===", total_rows, elapsed)


if __name__ == "__main__":
    run_backup()
