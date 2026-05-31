# tests/test_db.py
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_supabase(mocker):
    mock = MagicMock()
    mocker.patch("db.client.create_client", return_value=mock)
    import db.client as db_module

    db_module._client = None
    return mock


def test_get_games_returns_list(mock_supabase):
    from db.client import get_games

    mock_supabase.table.return_value.select.return_value.execute.return_value.data = [
        {"id": "abc", "title": "Elden Ring", "itad_id": "eldenring"}
    ]
    result = get_games()
    assert result == [{"id": "abc", "title": "Elden Ring", "itad_id": "eldenring"}]


def test_add_game_inserts_row(mock_supabase):
    from db.client import add_game

    mock_supabase.table.return_value.upsert.return_value.execute.return_value.data = [
        {"id": "abc", "title": "Elden Ring", "itad_id": "eldenring"}
    ]
    result = add_game("A", "Elden Ring", "eldenring")
    mock_supabase.table.return_value.upsert.assert_called_once_with(
        {"user_id": "A", "title": "Elden Ring", "itad_id": "eldenring", "target_price": None},
        on_conflict="user_id,itad_id",
    )
    assert result["title"] == "Elden Ring"


def test_remove_game_deletes_row(mocker):
    from db import client

    mocker.patch.object(client, "get_games", return_value=[{"id": "abc", "title": "Elden Ring"}])
    fake_table = mocker.MagicMock()
    fake_table.delete.return_value.eq.return_value.execute.return_value.data = [{"id": "abc"}]
    mocker.patch.object(client, "_get_client",
                        return_value=mocker.MagicMock(table=lambda *_: fake_table))
    result = client.remove_game("A", "Elden Ring")
    assert result is True


def test_remove_game_returns_false_when_not_found(mocker):
    from db import client

    mocker.patch.object(client, "get_games", return_value=[])
    result = client.remove_game("A", "Unknown Game")
    assert result is False


def test_insert_price_history(mock_supabase):
    from db.client import insert_price_history

    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": "xyz", "game_id": "abc", "price": 29.99}
    ]
    result = insert_price_history("abc", 29.99, 59.99, "Steam")
    mock_supabase.table.return_value.insert.assert_called_once_with(
        {"game_id": "abc", "price": 29.99, "regular_price": 59.99, "store": "Steam"}
    )
    assert result["price"] == 29.99


def test_get_historical_low_returns_min_price(mock_supabase):
    from db.client import get_historical_low

    chain = mock_supabase.table.return_value.select.return_value
    chain.eq.return_value.order.return_value.limit.return_value \
        .execute.return_value.data = [{"price": 14.99}]
    result = get_historical_low("abc")
    assert result == 14.99


def test_get_historical_low_returns_none_when_no_history(mock_supabase):
    from db.client import get_historical_low

    chain = mock_supabase.table.return_value.select.return_value
    chain.eq.return_value.order.return_value.limit.return_value \
        .execute.return_value.data = []
    result = get_historical_low("abc")
    assert result is None


def test_was_recently_notified_true(mock_supabase):
    from db.client import was_recently_notified

    chain = mock_supabase.table.return_value.select.return_value
    chain.eq.return_value.gte.return_value.execute.return_value.data = [
        {"id": "n1"}
    ]
    assert was_recently_notified("abc") is True


def test_was_recently_notified_false(mock_supabase):
    from db.client import was_recently_notified

    chain = mock_supabase.table.return_value.select.return_value
    chain.eq.return_value.gte.return_value.execute.return_value.data = []
    assert was_recently_notified("abc") is False


def test_was_recently_notified_custom_hours(mock_supabase):
    from datetime import datetime, timedelta, timezone

    from db.client import was_recently_notified

    chain = mock_supabase.table.return_value.select.return_value
    chain.eq.return_value.gte.return_value.execute.return_value.data = []
    was_recently_notified("abc", hours=24)
    # Verify the cutoff passed to .gte() is approximately 24 hours ago
    gte_call_args = (
        chain.eq.return_value.gte.call_args
    )
    field, cutoff_str = gte_call_args[0]
    assert field == "notified_at"
    cutoff = datetime.fromisoformat(cutoff_str)
    expected = datetime.now(timezone.utc) - timedelta(hours=24)
    assert abs((cutoff - expected).total_seconds()) < 5


def test_log_notification(mock_supabase):
    from db.client import log_notification

    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": "n1", "game_id": "abc", "price": 29.99}
    ]
    result = log_notification("abc", 29.99)
    assert result["game_id"] == "abc"


def test_get_recent_deals(mocker):
    from db import client

    fake_table = mocker.MagicMock()
    chain = fake_table.select.return_value.eq.return_value
    chain.order.return_value.limit.return_value.execute.return_value.data = [
        {"id": "n1", "price": 9.99, "games": {"title": "Hades", "user_id": "A"}}
    ]
    mocker.patch.object(client, "_get_client",
                        return_value=mocker.MagicMock(table=lambda *_: fake_table))
    result = client.get_recent_deals("A")
    assert len(result) == 1
    assert result[0]["games"]["title"] == "Hades"
    assert result[0]["price"] == 9.99


from db.client import get_chat_context, save_turn, get_message_count, summarize_if_needed


def _make_client(summary_data=None, messages_data=None, count=0):
    """Helper: returns a mock Supabase client wired up for memory queries."""
    client = MagicMock()
    # chat_summary select chain
    summary_chain = MagicMock()
    summary_chain.execute.return_value.data = summary_data or []
    client.table("chat_summary").select.return_value.eq.return_value = summary_chain
    # chat_messages select chain
    msg_chain = MagicMock()
    msg_chain.execute.return_value.data = messages_data or []
    msg_chain.execute.return_value.count = count
    (client.table("chat_messages").select.return_value
     .eq.return_value.order.return_value.limit.return_value) = msg_chain
    return client


def test_get_chat_context_no_history(mocker):
    mock_client = _make_client()
    mocker.patch("db.client._get_client", return_value=mock_client)
    result = get_chat_context("user123")
    assert result == {"summary": None, "messages": []}


def test_get_chat_context_with_summary_and_messages(mocker):
    mock_client = _make_client(
        summary_data=[{"summary": "User tracks Hades."}],
        messages_data=[
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ],
    )
    mocker.patch("db.client._get_client", return_value=mock_client)
    result = get_chat_context("user123")
    assert result["summary"] == "User tracks Hades."
    assert len(result["messages"]) == 2


def test_get_chat_context_supabase_failure_returns_empty(mocker):
    mocker.patch("db.client._get_client", side_effect=Exception("connection refused"))
    result = get_chat_context("user123")
    assert result == {"summary": None, "messages": []}


def test_save_turn_inserts_two_messages(mocker):
    mock_client = MagicMock()
    mocker.patch("db.client._get_client", return_value=mock_client)
    save_turn("user123", "track hades", "Now tracking Hades.")
    mock_client.table("chat_messages").insert.assert_called_once_with([
        {"user_id": "user123", "role": "user", "content": "track hades"},
        {"user_id": "user123", "role": "assistant", "content": "Now tracking Hades."},
    ])


def test_get_message_count(mocker):
    mock_client = MagicMock()
    mock_client.table("chat_messages").select.return_value.eq.return_value.execute.return_value.count = 12
    mocker.patch("db.client._get_client", return_value=mock_client)
    assert get_message_count("user123") == 12


def test_summarize_if_needed_skips_when_under_threshold(mocker):
    mock_client = MagicMock()
    mock_client.table("chat_messages").select.return_value.eq.return_value.execute.return_value.count = 10
    mocker.patch("db.client._get_client", return_value=mock_client)
    mock_gemini = MagicMock()
    summarize_if_needed("user123", mock_gemini)
    mock_gemini.generate_text.assert_not_called()


def test_summarize_if_needed_triggers_and_deletes(mocker):
    mock_client = MagicMock()
    # count > 20
    mock_client.table("chat_messages").select.return_value.eq.return_value.execute.return_value.count = 21
    # oldest 15 messages
    oldest_msgs = [{"id": f"id{i}", "role": "user", "content": f"msg{i}"} for i in range(15)]
    (mock_client.table("chat_messages").select.return_value
     .eq.return_value.order.return_value.limit.return_value.execute.return_value.data) = oldest_msgs
    # no existing summary
    mock_client.table("chat_summary").select.return_value.eq.return_value.execute.return_value.data = []
    mocker.patch("db.client._get_client", return_value=mock_client)

    mock_gemini = MagicMock()
    mock_gemini.generate_text.return_value = "User tracks Hades with target ₹500."
    summarize_if_needed("user123", mock_gemini)

    mock_gemini.generate_text.assert_called_once()
    mock_client.table("chat_summary").upsert.assert_called_once()
    ids = [f"id{i}" for i in range(15)]
    mock_client.table("chat_messages").delete.return_value.in_.assert_called_once_with("id", ids)


def test_add_watch_upserts(mocker):
    from db import client

    fake_table = mocker.MagicMock()
    fake_table.upsert.return_value.execute.return_value.data = [
        {"id": "w1", "name": "Casio G1714"}
    ]
    mock_supa = mocker.MagicMock(table=lambda *_: fake_table)
    mocker.patch.object(client, "_get_client", return_value=mock_supa)

    result = client.add_watch(
        "A", name="Casio G1714", brand="Casio", reference_no="G1714",
        target_price=30000.0, swisstimehouse_url="https://www.swisstimehouse.com/casio-g1714",
    )
    assert result["id"] == "w1"
    fake_table.upsert.assert_called_once()
    args, kwargs = fake_table.upsert.call_args
    assert args[0]["user_id"] == "A"
    assert kwargs.get("on_conflict") == "user_id,swisstimehouse_url"
    assert args[0]["target_price"] == 30000.0


def test_get_watches_returns_rows(mocker):
    from db import client

    fake_table = mocker.MagicMock()
    fake_table.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "w1", "name": "Casio G1714"}
    ]
    mock_supa = mocker.MagicMock(table=lambda *_: fake_table)
    mocker.patch.object(client, "_get_client", return_value=mock_supa)

    rows = client.get_watches("A")
    assert rows == [{"id": "w1", "name": "Casio G1714"}]


def test_set_watch_target_updates_match(mocker):
    from db import client

    mocker.patch.object(
        client, "get_watches", return_value=[{"id": "w1", "name": "Casio G1714"}]
    )
    fake_table = mocker.MagicMock()
    fake_table.update.return_value.eq.return_value.execute.return_value.data = [{"id": "w1"}]
    mock_supa = mocker.MagicMock(table=lambda *_: fake_table)
    mocker.patch.object(client, "_get_client", return_value=mock_supa)

    assert client.set_watch_target("A", "casio g1714", 25000.0) is True
    client.get_watches.assert_called_once_with("A")


def test_set_watch_target_no_match(mocker):
    from db import client

    mocker.patch.object(client, "get_watches", return_value=[])
    assert client.set_watch_target("A", "nonexistent", 25000.0) is False
    client.get_watches.assert_called_once_with("A")


def test_remove_watch_deletes_match(mocker):
    from db import client

    mocker.patch.object(
        client, "get_watches", return_value=[{"id": "w1", "name": "Casio G1714"}]
    )
    fake_table = mocker.MagicMock()
    fake_table.delete.return_value.eq.return_value.execute.return_value.data = [{"id": "w1"}]
    mock_supa = mocker.MagicMock(table=lambda *_: fake_table)
    mocker.patch.object(client, "_get_client", return_value=mock_supa)

    assert client.remove_watch("A", "Casio G1714") is True
    client.get_watches.assert_called_once_with("A")


def test_get_last_watch_notified_price(mocker):
    from db import client

    fake_table = mocker.MagicMock()
    chain = fake_table.select.return_value.eq.return_value.order.return_value.limit.return_value
    chain.execute.return_value.data = [{"price": 28000}]
    mock_supa = mocker.MagicMock(table=lambda *_: fake_table)
    mocker.patch.object(client, "_get_client", return_value=mock_supa)

    assert client.get_last_watch_notified_price("w1") == 28000.0


def test_log_watch_notification(mocker):
    from db import client

    fake_table = mocker.MagicMock()
    fake_table.insert.return_value.execute.return_value.data = [
        {"id": "n1", "watch_id": "w1", "price": 29000.0, "seller": "Swiss Time House"}
    ]
    mock_supa = mocker.MagicMock(table=lambda *_: fake_table)
    mocker.patch.object(client, "_get_client", return_value=mock_supa)

    result = client.log_watch_notification("w1", 29000.0, "Swiss Time House")
    assert result["id"] == "n1"
    args, _ = fake_table.insert.call_args
    assert args[0]["seller"] == "Swiss Time House"


def test_is_user_allowed_owner(monkeypatch):
    from db import client
    monkeypatch.setenv("OWNER_ID", "owner123")
    assert client.is_user_allowed("owner123") is True


def test_is_user_allowed_allowlisted(monkeypatch, mocker):
    from db import client
    monkeypatch.setenv("OWNER_ID", "owner123")
    fake_table = mocker.MagicMock()
    fake_table.select.return_value.eq.return_value.execute.return_value.data = [{"user_id": "u2"}]
    mocker.patch.object(client, "_get_client",
                        return_value=mocker.MagicMock(table=lambda *_: fake_table))
    assert client.is_user_allowed("u2") is True


def test_is_user_allowed_stranger(monkeypatch, mocker):
    from db import client
    monkeypatch.setenv("OWNER_ID", "owner123")
    fake_table = mocker.MagicMock()
    fake_table.select.return_value.eq.return_value.execute.return_value.data = []
    mocker.patch.object(client, "_get_client",
                        return_value=mocker.MagicMock(table=lambda *_: fake_table))
    assert client.is_user_allowed("stranger") is False


def test_add_allowed_user(mocker):
    from db import client
    fake_table = mocker.MagicMock()
    fake_table.upsert.return_value.execute.return_value.data = [
        {"user_id": "u2", "added_by": "owner123"}
    ]
    mocker.patch.object(client, "_get_client",
                        return_value=mocker.MagicMock(table=lambda *_: fake_table))
    assert client.add_allowed_user("u2", "owner123")["user_id"] == "u2"


def test_remove_allowed_user(mocker):
    from db import client
    fake_table = mocker.MagicMock()
    fake_table.delete.return_value.eq.return_value.execute.return_value.data = [{"user_id": "u2"}]
    mocker.patch.object(client, "_get_client",
                        return_value=mocker.MagicMock(table=lambda *_: fake_table))
    assert client.remove_allowed_user("u2") is True


def test_list_allowed_users(mocker):
    from db import client
    fake_table = mocker.MagicMock()
    fake_table.select.return_value.execute.return_value.data = [{"user_id": "u2"}]
    mocker.patch.object(client, "_get_client",
                        return_value=mocker.MagicMock(table=lambda *_: fake_table))
    assert client.list_allowed_users() == [{"user_id": "u2"}]


def test_get_games_scopes_to_user(mocker):
    from db import client
    fake_table = mocker.MagicMock()
    chain = fake_table.select.return_value.eq.return_value
    chain.execute.return_value.data = [{"id": "g1", "user_id": "A"}]
    mocker.patch.object(client, "_get_client",
                        return_value=mocker.MagicMock(table=lambda *_: fake_table))
    rows = client.get_games("A")
    fake_table.select.return_value.eq.assert_called_once_with("user_id", "A")
    assert rows == [{"id": "g1", "user_id": "A"}]


def test_get_games_no_user_returns_all(mocker):
    from db import client
    fake_table = mocker.MagicMock()
    fake_table.select.return_value.execute.return_value.data = [{"id": "g1"}, {"id": "g2"}]
    mocker.patch.object(client, "_get_client",
                        return_value=mocker.MagicMock(table=lambda *_: fake_table))
    rows = client.get_games()
    fake_table.select.return_value.eq.assert_not_called()
    assert len(rows) == 2


def test_add_game_scopes_and_composite_conflict(mocker):
    from db import client
    fake_table = mocker.MagicMock()
    fake_table.upsert.return_value.execute.return_value.data = [{"id": "g1"}]
    mocker.patch.object(client, "_get_client",
                        return_value=mocker.MagicMock(table=lambda *_: fake_table))
    client.add_game("A", "Elden Ring", "itad1", target_price=500.0)
    args, kwargs = fake_table.upsert.call_args
    assert args[0]["user_id"] == "A"
    assert kwargs.get("on_conflict") == "user_id,itad_id"


def test_set_target_price_scoped(mocker):
    from db import client
    mocker.patch.object(client, "get_games", return_value=[{"id": "g1", "title": "Elden Ring"}])
    fake_table = mocker.MagicMock()
    fake_table.update.return_value.eq.return_value.execute.return_value.data = [{"id": "g1"}]
    mocker.patch.object(client, "_get_client",
                        return_value=mocker.MagicMock(table=lambda *_: fake_table))
    assert client.set_target_price("A", "elden ring", 400.0) is True
    client.get_games.assert_called_once_with("A")


def test_remove_game_scoped(mocker):
    from db import client
    mocker.patch.object(client, "get_games", return_value=[{"id": "g1", "title": "Elden Ring"}])
    fake_table = mocker.MagicMock()
    fake_table.delete.return_value.eq.return_value.execute.return_value.data = [{"id": "g1"}]
    mocker.patch.object(client, "_get_client",
                        return_value=mocker.MagicMock(table=lambda *_: fake_table))
    assert client.remove_game("A", "Elden Ring") is True
    client.get_games.assert_called_once_with("A")


def test_get_watches_scopes_to_user(mocker):
    from db import client
    fake_table = mocker.MagicMock()
    fake_table.select.return_value.eq.return_value.execute.return_value.data = [{"id": "w1"}]
    mocker.patch.object(client, "_get_client",
                        return_value=mocker.MagicMock(table=lambda *_: fake_table))
    client.get_watches("A")
    fake_table.select.return_value.eq.assert_called_once_with("user_id", "A")


def test_get_watches_no_user_returns_all(mocker):
    from db import client
    fake_table = mocker.MagicMock()
    fake_table.select.return_value.execute.return_value.data = [{"id": "w1"}, {"id": "w2"}]
    mocker.patch.object(client, "_get_client",
                        return_value=mocker.MagicMock(table=lambda *_: fake_table))
    assert len(client.get_watches()) == 2
    fake_table.select.return_value.eq.assert_not_called()


def test_add_watch_scopes_and_composite_conflict(mocker):
    from db import client
    fake_table = mocker.MagicMock()
    fake_table.upsert.return_value.execute.return_value.data = [{"id": "w1"}]
    mocker.patch.object(client, "_get_client",
                        return_value=mocker.MagicMock(table=lambda *_: fake_table))
    client.add_watch("A", name="Casio", brand="Casio", reference_no="G1",
                     target_price=30000.0, swisstimehouse_url="https://www.swisstimehouse.com/x")
    args, kwargs = fake_table.upsert.call_args
    assert args[0]["user_id"] == "A"
    assert kwargs.get("on_conflict") == "user_id,swisstimehouse_url"


def test_set_watch_target_scoped(mocker):
    from db import client
    mocker.patch.object(client, "get_watches", return_value=[{"id": "w1", "name": "Casio G1714"}])
    fake_table = mocker.MagicMock()
    fake_table.update.return_value.eq.return_value.execute.return_value.data = [{"id": "w1"}]
    mocker.patch.object(client, "_get_client",
                        return_value=mocker.MagicMock(table=lambda *_: fake_table))
    assert client.set_watch_target("A", "casio g1714", 25000.0) is True
    client.get_watches.assert_called_once_with("A")


def test_remove_watch_scoped(mocker):
    from db import client
    mocker.patch.object(client, "get_watches", return_value=[{"id": "w1", "name": "Casio G1714"}])
    fake_table = mocker.MagicMock()
    fake_table.delete.return_value.eq.return_value.execute.return_value.data = [{"id": "w1"}]
    mocker.patch.object(client, "_get_client",
                        return_value=mocker.MagicMock(table=lambda *_: fake_table))
    assert client.remove_watch("A", "Casio G1714") is True
    client.get_watches.assert_called_once_with("A")
