# tests/test_db.py
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixture: mock psycopg2 connection + cursor
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_cur(mocker):
    """Patches _ensure_conn and returns a mock cursor pre-wired as a context manager."""
    cur = MagicMock()
    conn = MagicMock()
    # Make cursor() work as a context manager yielding `cur`
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mocker.patch("db.client._ensure_conn", return_value=conn)
    import db.client as db_module
    db_module._conn = None
    return cur


# ---------------------------------------------------------------------------
# Game tests
# ---------------------------------------------------------------------------

def test_get_games_returns_list(mock_cur):
    from db.client import get_games

    mock_cur.fetchall.return_value = [
        {"id": "abc", "title": "Elden Ring", "itad_id": "eldenring", "user_id": "A",
         "target_price": None, "added_at": "2024-01-01T00:00:00+00:00"}
    ]
    result = get_games()
    assert result[0]["title"] == "Elden Ring"


def test_add_game_inserts_row(mock_cur):
    from db.client import add_game

    mock_cur.fetchone.return_value = {
        "id": "abc", "title": "Elden Ring", "itad_id": "eldenring",
        "user_id": "A", "target_price": None, "added_at": "2024-01-01T00:00:00+00:00"
    }
    result = add_game("A", "Elden Ring", "eldenring")
    assert result["title"] == "Elden Ring"
    mock_cur.execute.assert_called_once()
    sql, params = mock_cur.execute.call_args[0]
    assert "ON CONFLICT" in sql
    assert params == ("A", "Elden Ring", "eldenring", None)


def test_remove_game_deletes_row(mocker):
    from db import client

    mocker.patch.object(client, "get_games", return_value=[{"id": "abc", "title": "Elden Ring"}])
    cur = MagicMock()
    cur.rowcount = 1
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mocker.patch("db.client._ensure_conn", return_value=conn)
    assert client.remove_game("A", "Elden Ring") is True


def test_remove_game_returns_false_when_not_found(mocker):
    from db import client

    mocker.patch.object(client, "get_games", return_value=[])
    assert client.remove_game("A", "Unknown Game") is False


def test_insert_price_history(mock_cur):
    from db.client import insert_price_history

    mock_cur.fetchone.return_value = {
        "id": "xyz", "game_id": "abc", "price": 29.99,
        "regular_price": 59.99, "store": "Steam", "fetched_at": "2024-01-01T00:00:00+00:00"
    }
    result = insert_price_history("abc", 29.99, 59.99, "Steam")
    assert result["price"] == 29.99
    mock_cur.execute.assert_called_once()
    sql, params = mock_cur.execute.call_args[0]
    assert "INSERT INTO drophunter.price_history" in sql
    assert params == ("abc", 29.99, 59.99, "Steam")


def test_get_historical_low_returns_min_price(mock_cur):
    from db.client import get_historical_low

    mock_cur.fetchone.return_value = {"price": 14.99}
    assert get_historical_low("abc") == 14.99


def test_get_historical_low_returns_none_when_no_history(mock_cur):
    from db.client import get_historical_low

    mock_cur.fetchone.return_value = None
    assert get_historical_low("abc") is None


def test_was_recently_notified_true(mock_cur):
    from db.client import was_recently_notified

    mock_cur.fetchone.return_value = {"id": "n1"}
    assert was_recently_notified("abc") is True


def test_was_recently_notified_false(mock_cur):
    from db.client import was_recently_notified

    mock_cur.fetchone.return_value = None
    assert was_recently_notified("abc") is False


def test_was_recently_notified_custom_hours(mock_cur):
    from datetime import datetime, timedelta, timezone

    from db.client import was_recently_notified

    mock_cur.fetchone.return_value = None
    was_recently_notified("abc", hours=24)
    sql, params = mock_cur.execute.call_args[0]
    assert "notified_at" in sql
    # params[1] is the cutoff ISO string
    cutoff = datetime.fromisoformat(params[1])
    expected = datetime.now(timezone.utc) - timedelta(hours=24)
    assert abs((cutoff - expected).total_seconds()) < 5


def test_log_notification(mock_cur):
    from db.client import log_notification

    mock_cur.fetchone.return_value = {
        "id": "n1", "game_id": "abc", "price": 29.99,
        "notified_at": "2024-01-01T00:00:00+00:00"
    }
    result = log_notification("abc", 29.99)
    assert result["game_id"] == "abc"


def test_get_recent_deals(mocker):
    from db import client

    cur = MagicMock()
    cur.fetchall.return_value = [
        {
            "id": "n1", "game_id": "g1", "price": 9.99,
            "notified_at": "2024-01-01T10:00:00+00:00",
            "game_title": "Hades", "game_user_id": "A",
        }
    ]
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mocker.patch("db.client._ensure_conn", return_value=conn)

    result = client.get_recent_deals("A")
    assert len(result) == 1
    assert result[0]["games"]["title"] == "Hades"
    assert result[0]["price"] == 9.99


# ---------------------------------------------------------------------------
# Chat memory tests
# ---------------------------------------------------------------------------

from db.client import get_chat_context, save_turn, get_message_count, summarize_if_needed


def _make_conn(mocker, summary_data=None, messages_data=None, count=0):
    cur = MagicMock()

    def fetchone_side_effect():
        if not hasattr(fetchone_side_effect, "_called"):
            fetchone_side_effect._called = True
            return summary_data[0] if summary_data else None
        return None

    cur.fetchone.side_effect = fetchone_side_effect
    cur.fetchall.return_value = messages_data or []
    cur.rowcount = count

    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mocker.patch("db.client._ensure_conn", return_value=conn)
    return cur


def test_get_chat_context_no_history(mocker):
    cur = MagicMock()
    cur.fetchone.return_value = None
    cur.fetchall.return_value = []
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mocker.patch("db.client._ensure_conn", return_value=conn)

    result = get_chat_context("user123")
    assert result == {"summary": None, "messages": []}


def test_get_chat_context_with_summary_and_messages(mocker):
    results = [
        {"summary": "User tracks Hades."},
        None,
    ]
    call_count = {"n": 0}

    cur = MagicMock()

    def _fetchone():
        val = results[call_count["n"]] if call_count["n"] < len(results) else None
        call_count["n"] += 1
        return val

    cur.fetchone.side_effect = _fetchone
    cur.fetchall.return_value = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mocker.patch("db.client._ensure_conn", return_value=conn)

    result = get_chat_context("user123")
    assert result["summary"] == "User tracks Hades."
    assert len(result["messages"]) == 2


def test_get_chat_context_failure_returns_empty(mocker):
    mocker.patch("db.client._ensure_conn", side_effect=Exception("connection refused"))
    result = get_chat_context("user123")
    assert result == {"summary": None, "messages": []}


def test_save_turn_inserts_two_messages(mock_cur):
    save_turn("user123", "track hades", "Now tracking Hades.")
    mock_cur.execute.assert_called_once()
    sql, params = mock_cur.execute.call_args[0]
    assert "INSERT INTO drophunter.chat_messages" in sql
    assert "user123" in params
    assert "track hades" in params
    assert "Now tracking Hades." in params


def test_get_message_count(mock_cur):
    mock_cur.fetchone.return_value = {"cnt": 12}
    assert get_message_count("user123") == 12


def test_summarize_if_needed_skips_when_under_threshold(mocker):
    mocker.patch("db.client.get_message_count", return_value=10)
    mock_gemini = MagicMock()
    summarize_if_needed("user123", mock_gemini)
    mock_gemini.generate_text.assert_not_called()


def test_summarize_if_needed_triggers_and_deletes(mocker):
    mocker.patch("db.client.get_message_count", return_value=21)

    oldest_msgs = [{"id": f"id{i}", "role": "user", "content": f"msg{i}"} for i in range(15)]

    call_count = {"n": 0}

    cur = MagicMock()

    def _fetchall():
        call_count["n"] += 1
        if call_count["n"] == 1:
            return oldest_msgs
        return []

    def _fetchone():
        return None

    cur.fetchall.side_effect = _fetchall
    cur.fetchone.side_effect = _fetchone

    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mocker.patch("db.client._ensure_conn", return_value=conn)

    mock_gemini = MagicMock()
    mock_gemini.generate_text.return_value = "User tracks Hades with target ₹500."
    summarize_if_needed("user123", mock_gemini)

    mock_gemini.generate_text.assert_called_once()
    # Verify DELETE was called with the list of IDs
    delete_calls = [c for c in cur.execute.call_args_list if "DELETE" in str(c)]
    assert len(delete_calls) == 1


# ---------------------------------------------------------------------------
# Watch tests
# ---------------------------------------------------------------------------

def test_add_watch_upserts(mock_cur):
    from db import client

    mock_cur.fetchone.return_value = {"id": "w1", "name": "Casio G1714"}
    result = client.add_watch(
        "A", name="Casio G1714", brand="Casio", reference_no="G1714",
        target_price=30000.0, swisstimehouse_url="https://www.swisstimehouse.com/casio-g1714",
    )
    assert result["id"] == "w1"
    sql, params = mock_cur.execute.call_args[0]
    assert "ON CONFLICT" in sql
    assert params[0] == "A"
    assert params[4] == 30000.0


def test_get_watches_returns_rows(mock_cur):
    from db import client

    mock_cur.fetchall.return_value = [{"id": "w1", "name": "Casio G1714"}]
    rows = client.get_watches("A")
    assert rows == [{"id": "w1", "name": "Casio G1714"}]


def test_set_watch_target_updates_match(mocker):
    from db import client

    mocker.patch.object(
        client, "get_watches", return_value=[{"id": "w1", "name": "Casio G1714"}]
    )
    cur = MagicMock()
    cur.rowcount = 1
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mocker.patch("db.client._ensure_conn", return_value=conn)

    assert client.set_watch_target("A", "casio g1714", 25000.0) is True
    client.get_watches.assert_called_once_with("A")


def test_set_watch_target_no_match(mocker):
    from db import client

    mocker.patch.object(client, "get_watches", return_value=[])
    assert client.set_watch_target("A", "nonexistent", 25000.0) is False


def test_remove_watch_deletes_match(mocker):
    from db import client

    mocker.patch.object(
        client, "get_watches", return_value=[{"id": "w1", "name": "Casio G1714"}]
    )
    cur = MagicMock()
    cur.rowcount = 1
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mocker.patch("db.client._ensure_conn", return_value=conn)

    assert client.remove_watch("A", "Casio G1714") is True


def test_get_last_watch_notified_price(mock_cur):
    from db import client

    mock_cur.fetchone.return_value = {"price": 28000}
    assert client.get_last_watch_notified_price("w1") == 28000.0


def test_log_watch_notification(mock_cur):
    from db import client

    mock_cur.fetchone.return_value = {
        "id": "n1", "watch_id": "w1", "price": 29000.0,
        "seller": "Swiss Time House", "notified_at": "2024-01-01T00:00:00+00:00"
    }
    result = client.log_watch_notification("w1", 29000.0, "Swiss Time House")
    assert result["id"] == "n1"
    sql, params = mock_cur.execute.call_args[0]
    assert params[2] == "Swiss Time House"


# ---------------------------------------------------------------------------
# Allowlist tests
# ---------------------------------------------------------------------------

def test_is_user_allowed_owner(monkeypatch):
    from db import client
    monkeypatch.setenv("OWNER_ID", "owner123")
    assert client.is_user_allowed("owner123") is True


def test_is_user_allowed_allowlisted(monkeypatch, mock_cur):
    from db import client
    monkeypatch.setenv("OWNER_ID", "owner123")
    mock_cur.fetchone.return_value = {"user_id": "u2"}
    assert client.is_user_allowed("u2") is True


def test_is_user_allowed_stranger(monkeypatch, mock_cur):
    from db import client
    monkeypatch.setenv("OWNER_ID", "owner123")
    mock_cur.fetchone.return_value = None
    assert client.is_user_allowed("stranger") is False


def test_add_allowed_user(mock_cur):
    from db import client
    mock_cur.fetchone.return_value = {"user_id": "u2", "added_by": "owner123", "added_at": "2024-01-01T00:00:00+00:00"}
    result = client.add_allowed_user("u2", "owner123")
    assert result["user_id"] == "u2"


def test_remove_allowed_user(mock_cur):
    from db import client
    mock_cur.rowcount = 1
    assert client.remove_allowed_user("u2") is True


def test_list_allowed_users(mock_cur):
    from db import client
    mock_cur.fetchall.return_value = [{"user_id": "u2", "added_by": "owner123", "added_at": "2024-01-01T00:00:00+00:00"}]
    result = client.list_allowed_users()
    assert result == [{"user_id": "u2", "added_by": "owner123", "added_at": "2024-01-01T00:00:00+00:00"}]


# ---------------------------------------------------------------------------
# Scope / multi-user isolation tests
# ---------------------------------------------------------------------------

def test_get_games_scopes_to_user(mock_cur):
    from db import client
    mock_cur.fetchall.return_value = [{"id": "g1", "user_id": "A"}]
    client.get_games("A")
    sql, params = mock_cur.execute.call_args[0]
    assert "user_id = %s" in sql
    assert params == ("A",)


def test_get_games_no_user_returns_all(mock_cur):
    from db import client
    mock_cur.fetchall.return_value = [{"id": "g1"}, {"id": "g2"}]
    rows = client.get_games()
    sql = mock_cur.execute.call_args[0][0]
    assert "user_id" not in sql
    assert len(rows) == 2


def test_add_game_scopes_and_composite_conflict(mock_cur):
    from db import client
    mock_cur.fetchone.return_value = {"id": "g1"}
    client.add_game("A", "Elden Ring", "itad1", target_price=500.0)
    sql, params = mock_cur.execute.call_args[0]
    assert "ON CONFLICT (user_id, itad_id)" in sql
    assert params[0] == "A"


def test_set_target_price_scoped(mocker):
    from db import client
    mocker.patch.object(client, "get_games", return_value=[{"id": "g1", "title": "Elden Ring"}])
    cur = MagicMock()
    cur.rowcount = 1
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mocker.patch("db.client._ensure_conn", return_value=conn)
    assert client.set_target_price("A", "elden ring", 400.0) is True
    client.get_games.assert_called_once_with("A")


def test_remove_game_scoped(mocker):
    from db import client
    mocker.patch.object(client, "get_games", return_value=[{"id": "g1", "title": "Elden Ring"}])
    cur = MagicMock()
    cur.rowcount = 1
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mocker.patch("db.client._ensure_conn", return_value=conn)
    assert client.remove_game("A", "Elden Ring") is True
    client.get_games.assert_called_once_with("A")


def test_get_watches_scopes_to_user(mock_cur):
    from db import client
    mock_cur.fetchall.return_value = [{"id": "w1"}]
    client.get_watches("A")
    sql, params = mock_cur.execute.call_args[0]
    assert "user_id = %s" in sql
    assert params == ("A",)


def test_get_watches_no_user_returns_all(mock_cur):
    from db import client
    mock_cur.fetchall.return_value = [{"id": "w1"}, {"id": "w2"}]
    rows = client.get_watches()
    sql = mock_cur.execute.call_args[0][0]
    assert "user_id" not in sql
    assert len(rows) == 2


def test_add_watch_scopes_and_composite_conflict(mock_cur):
    from db import client
    mock_cur.fetchone.return_value = {"id": "w1"}
    client.add_watch("A", name="Casio", brand="Casio", reference_no="G1",
                     target_price=30000.0, swisstimehouse_url="https://www.swisstimehouse.com/x")
    sql, params = mock_cur.execute.call_args[0]
    assert "ON CONFLICT (user_id, swisstimehouse_url)" in sql
    assert params[0] == "A"


def test_set_watch_target_scoped(mocker):
    from db import client
    mocker.patch.object(client, "get_watches", return_value=[{"id": "w1", "name": "Casio G1714"}])
    cur = MagicMock()
    cur.rowcount = 1
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mocker.patch("db.client._ensure_conn", return_value=conn)
    assert client.set_watch_target("A", "casio g1714", 25000.0) is True
    client.get_watches.assert_called_once_with("A")


def test_remove_watch_scoped(mocker):
    from db import client
    mocker.patch.object(client, "get_watches", return_value=[{"id": "w1", "name": "Casio G1714"}])
    cur = MagicMock()
    cur.rowcount = 1
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mocker.patch("db.client._ensure_conn", return_value=conn)
    assert client.remove_watch("A", "Casio G1714") is True
    client.get_watches.assert_called_once_with("A")
