"""Real Postgres contracts; CI supplies TEST_DATABASE_URL for a disposable DB."""

import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import pytest

from db import client as db

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="No test Postgres")
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(params=["public", "drophunter"])
def database(request, monkeypatch):
    dsn = os.environ["TEST_DATABASE_URL"]
    schema = request.param
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    with conn.cursor() as cur:
        base = "db/schema.sql" if schema == "public" else "db/migrations/001_drophunter_schema.sql"
        cur.execute((ROOT / base).read_text())
        migration = (ROOT / "db/migrations/20260915180826_cloud_notifications.sql").read_text()
        cur.execute(migration)
        cur.execute(migration)  # Must be safe to apply again without losing data.
    monkeypatch.setenv("DATABASE_URL", dsn)
    monkeypatch.setenv("DB_SCHEMA", schema)
    monkeypatch.setenv("OWNER_ID", "owner")
    if db._conn is not None:
        db._conn.close()
    monkeypatch.setattr(db, "_conn", None)
    yield schema
    if db._conn is not None:
        db._conn.close()
    db._conn = None
    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM {schema}.games WHERE user_id IN ('owner', 'other')")
        cur.execute(f"DELETE FROM {schema}.allowed_users WHERE user_id IN ('owner', 'other')")
        cur.execute("DELETE FROM ops.job_runs WHERE job_name = 'test.integration'")
    conn.close()


def test_per_user_state_and_job_logging(database):
    db.add_game("owner", "Hades", "integration-hades", 100)
    db.add_game("other", "Hades", "integration-hades", 200)
    assert len(db.get_games("owner")) == 1
    assert float(db.get_games("owner")[0]["target_price"]) == 100
    assert float(db.get_games("other")[0]["target_price"]) == 200
    assert db.set_user_email("owner", "owner@example.com") is True
    assert db.get_user_email("owner") == "owner@example.com"
    with pytest.raises(PermissionError):
        db.set_user_email("other", "other@example.com")
    db.add_allowed_user("other", "owner")
    assert db.set_user_email("other", "other@example.com") is True
    db.remove_allowed_user("other")
    assert db.get_user_email("other") is None
    now = datetime.now(timezone.utc)
    db.log_job_run("test.integration", now, now, "ok", None, {"rows_swept": 2})
    with db._cursor() as cur:
        cur.execute("SELECT counts FROM ops.job_runs WHERE job_name = 'test.integration'")
        assert cur.fetchone()["counts"] == {"rows_swept": 2}
        cur.execute("SELECT relrowsecurity FROM pg_class WHERE oid = 'ops.job_runs'::regclass")
        assert cur.fetchone()["relrowsecurity"] is True
