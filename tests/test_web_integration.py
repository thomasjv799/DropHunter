"""Real PostgreSQL authorization and 100-game query contracts (CI disposable DB)."""

import os
from pathlib import Path
from uuid import uuid4

import psycopg2
import pytest

from web.repository import Repository

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="No test Postgres")
ROOT = Path(__file__).resolve().parents[1]
OWNER = "111111111111111111"
OTHER = "222222222222222222"


@pytest.fixture(params=["public", "drophunter"])
def repo(request, monkeypatch):
    schema = request.param
    dsn = os.environ["TEST_DATABASE_URL"]
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    with conn.cursor() as cur:
        base = "db/schema.sql" if schema == "public" else "db/migrations/001_drophunter_schema.sql"
        cur.execute((ROOT / base).read_text())
        cur.execute(f"SET search_path TO {schema}")
        cur.execute((ROOT / "db/migrations/20260915180826_cloud_notifications.sql").read_text())
        migration = (ROOT / "supabase/migrations/20260926121657_dashboard_access.sql").read_text()
        cur.execute(migration)
        cur.execute(migration)
        cur.execute(
            "INSERT INTO allowed_users (user_id) VALUES (%s),(%s) ON CONFLICT DO NOTHING",
            (OWNER, OTHER),
        )
    monkeypatch.setenv("DATABASE_URL", dsn)
    monkeypatch.setenv("DB_SCHEMA", schema)
    monkeypatch.setenv("OWNER_ID", OWNER)
    yield Repository()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM games WHERE user_id IN (%s,%s)", (OWNER, OTHER))
        cur.execute("DELETE FROM allowed_users WHERE user_id IN (%s,%s)", (OWNER, OTHER))
        cur.execute("DELETE FROM dashboard.accounts WHERE discord_id IN (%s,%s)", (OWNER, OTHER))
    conn.close()


def test_scoped_pagination_and_history(repo):
    ids = []
    for i in range(100):
        ids.append(repo.add_game(OWNER, f"Game {i:03}", f"itad-{i}", 500)["id"])
    other = repo.add_game(OTHER, "Other secret game", "itad-secret", 99)["id"]
    assert repo.list_games(OWNER, page=10)["items"][-1]["title"] == "Game 099"
    assert repo.list_games(OWNER)["total"] == 100
    assert len(repo.list_games(OWNER)["items"]) == 10
    assert repo.list_games(OWNER, query="09")["total"] == 11
    with pytest.raises(ValueError, match="100"):
        repo.add_game(OWNER, "Over limit", "over-limit", 1)
    assert repo.add_game(OWNER, "Game 000", "itad-0", 999)["existing"] is True
    assert repo.game(OWNER, ids[0])["target_price"] == 500
    assert repo.game(OWNER, other) is None
    assert repo.update_game(OWNER, other, 1) is False
    assert repo.remove_game(OWNER, other) is False
    with repo.cursor() as cur:
        for game in (ids[0], other):
            cur.execute(
                """INSERT INTO price_history
                (game_id,price,regular_price,store,fetched_at) VALUES
                (%s,300,999,'Steam',now()),(%s,600,999,'GOG',now()-interval '45 days')""",
                (game, game),
            )
    assert len(repo.history(OWNER, ids[0], 30)) == 1
    assert len(repo.history(OWNER, ids[0], 90)) == 2
    assert repo.history(OWNER, other, 90) == []
    assert repo.list_games(OWNER, status="deal")["total"] == 1
    assert repo.summary(OWNER)["unknown"] == 99
    assert repo.summary(OWNER)["at_target"] == 1
    assert repo.list_games(OWNER, sort="price")["items"][0]["id"] == ids[0]
    assert repo.update_game(OWNER, ids[0], 200) is True
    assert repo.summary(OWNER)["at_target"] == 0


def test_account_revocation_and_private_mapping(repo):
    auth_id = str(uuid4())
    with repo.cursor() as cur:
        cur.execute(
            """INSERT INTO dashboard.accounts
            (auth_id,discord_id,approved,approved_by) VALUES (%s,%s,true,'test')""",
            (auth_id, OTHER),
        )
        cur.execute("SELECT relrowsecurity FROM pg_class WHERE oid='dashboard.accounts'::regclass")
        assert cur.fetchone()["relrowsecurity"] is True
    assert repo.account(auth_id)["discord_id"] == OTHER
    with repo.cursor() as cur:
        cur.execute("DELETE FROM allowed_users WHERE user_id=%s", (OTHER,))
    assert repo.account(auth_id) is None
    with repo.cursor() as cur:
        cur.execute("INSERT INTO allowed_users(user_id) VALUES (%s)", (OTHER,))
        cur.execute("UPDATE dashboard.accounts SET approved=false WHERE auth_id=%s", (auth_id,))
    assert repo.account(auth_id) is None


def test_email_save_cannot_restore_revoked_permission(repo):
    # The permission can disappear after API authentication but before saving settings.
    with repo.cursor() as cur:
        cur.execute("DELETE FROM allowed_users WHERE user_id=%s", (OTHER,))
    with pytest.raises(PermissionError):
        repo.set_email(OTHER, "person@example.com")
    with repo.cursor() as cur:
        cur.execute("SELECT 1 FROM allowed_users WHERE user_id=%s", (OTHER,))
        assert cur.fetchone() is None
    repo.set_email(OWNER, "owner@example.com")
    assert repo.settings(OWNER)["email"] == "owner@example.com"
