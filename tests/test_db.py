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

    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": "abc", "title": "Elden Ring", "itad_id": "eldenring"}
    ]
    result = add_game("Elden Ring", "eldenring")
    mock_supabase.table.return_value.insert.assert_called_once_with(
        {"title": "Elden Ring", "itad_id": "eldenring"}
    )
    assert result["title"] == "Elden Ring"


def test_remove_game_deletes_row(mock_supabase):
    from db.client import remove_game

    chain = mock_supabase.table.return_value.delete.return_value
    chain.ilike.return_value.execute.return_value.data = [{"id": "abc"}]
    result = remove_game("Elden Ring")
    assert result is True


def test_remove_game_returns_false_when_not_found(mock_supabase):
    from db.client import remove_game

    chain = mock_supabase.table.return_value.delete.return_value
    chain.ilike.return_value.execute.return_value.data = []
    result = remove_game("Unknown Game")
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


def test_get_recent_deals(mock_supabase):
    from db.client import get_recent_deals

    chain = mock_supabase.table.return_value.select.return_value
    chain.order.return_value.limit.return_value \
        .execute.return_value.data = [
        {"id": "n1", "price": 9.99, "games": {"title": "Hades"}}
    ]
    result = get_recent_deals()
    assert len(result) == 1
    assert result[0]["games"]["title"] == "Hades"
    assert result[0]["price"] == 9.99
