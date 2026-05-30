# tests/test_cron.py
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def sample_game():
    return {"id": "game-uuid-1", "title": "Elden Ring", "itad_id": "018d937f-aaaa"}


def test_process_game_sends_alert_when_deal_detected(sample_game, mocker):
    from cron.price_check import process_game

    mocker.patch(
        "cron.price_check.get_best_price",
        return_value={"price": 14.99, "regular_price": 59.99, "store": "Steam", "cut": 75},
    )
    mocker.patch("cron.price_check.insert_price_history", return_value={})
    mocker.patch("cron.price_check.get_historical_low", return_value=14.99)
    mocker.patch("cron.price_check.get_last_notified_price", return_value=None)
    mock_provider = MagicMock()
    mock_provider.generate_text.return_value = "Best price ever!"
    mocker.patch("cron.price_check.get_provider", return_value=mock_provider)
    mock_alert = mocker.patch("cron.price_check.send_deal_alert")
    mock_log = mocker.patch("cron.price_check.log_notification")

    process_game(sample_game)

    mock_alert.assert_called_once_with(
        game_title="Elden Ring",
        price=14.99,
        regular_price=59.99,
        store="Steam",
        cut=75,
        ai_commentary="Best price ever!",
    )
    mock_log.assert_called_once_with("game-uuid-1", 14.99)


def test_process_game_skips_when_not_a_deal(sample_game, mocker):
    from cron.price_check import process_game

    mocker.patch(
        "cron.price_check.get_best_price",
        return_value={"price": 50.00, "regular_price": 59.99, "store": "Steam", "cut": 17},
    )
    mocker.patch("cron.price_check.insert_price_history", return_value={})
    mocker.patch("cron.price_check.get_historical_low", return_value=14.99)
    mock_alert = mocker.patch("cron.price_check.send_deal_alert")

    process_game(sample_game)

    mock_alert.assert_not_called()


def test_process_game_skips_when_already_notified_at_same_price(sample_game, mocker):
    from cron.price_check import process_game

    mocker.patch(
        "cron.price_check.get_best_price",
        return_value={"price": 14.99, "regular_price": 59.99, "store": "Steam", "cut": 75},
    )
    mocker.patch("cron.price_check.insert_price_history", return_value={})
    mocker.patch("cron.price_check.get_historical_low", return_value=14.99)
    # Same price as last notification — should skip
    mocker.patch("cron.price_check.get_last_notified_price", return_value=14.99)
    mock_alert = mocker.patch("cron.price_check.send_deal_alert")

    process_game(sample_game)

    mock_alert.assert_not_called()


def test_process_game_skips_when_no_price_data(sample_game, mocker):
    from cron.price_check import process_game

    mocker.patch("cron.price_check.get_best_price", return_value=None)
    mock_insert = mocker.patch("cron.price_check.insert_price_history")

    process_game(sample_game)

    mock_insert.assert_not_called()


def test_process_game_skips_when_historical_low_is_none(sample_game, mocker):
    from cron.price_check import process_game

    mocker.patch(
        "cron.price_check.get_best_price",
        return_value={"price": 14.99, "regular_price": 59.99, "store": "Steam", "cut": 75},
    )
    mocker.patch("cron.price_check.insert_price_history", return_value={})
    mocker.patch("cron.price_check.get_historical_low", return_value=None)
    mock_alert = mocker.patch("cron.price_check.send_deal_alert")

    process_game(sample_game)

    mock_alert.assert_not_called()


def test_run_checks_all_games(mocker):
    from cron.price_check import run

    mocker.patch(
        "cron.price_check.get_games",
        return_value=[
            {"id": "1", "title": "Game A", "itad_id": "aaa"},
            {"id": "2", "title": "Game B", "itad_id": "bbb"},
        ],
    )
    mocker.patch("cron.price_check.get_watches", return_value=[])
    mock_process = mocker.patch("cron.price_check.process_game")

    run()

    assert mock_process.call_count == 2
    mock_process.assert_any_call({"id": "1", "title": "Game A", "itad_id": "aaa"})
    mock_process.assert_any_call({"id": "2", "title": "Game B", "itad_id": "bbb"})


@pytest.fixture
def sample_watch():
    return {
        "id": "watch-uuid-1",
        "name": "Casio G1714",
        "target_price": 30000.0,
        "swisstimehouse_url": "https://www.swisstimehouse.com/casio-g1714",
        "myntra_url": None,
    }


def test_process_watch_sends_alert_below_target(sample_watch, mocker):
    from cron.price_check import process_watch

    mocker.patch(
        "cron.price_check.fetch_swisstimehouse",
        return_value={
            "name": "Casio G1714", "brand": "Casio", "reference": "G1714", "price": 29000.0
        },
    )
    mock_hist = mocker.patch("cron.price_check.insert_watch_price_history")
    mocker.patch("cron.price_check.get_last_watch_notified_price", return_value=None)
    mock_provider = MagicMock()
    mock_provider.generate_text.return_value = "Buy now!"
    mocker.patch("cron.price_check.get_provider", return_value=mock_provider)
    mock_alert = mocker.patch("cron.price_check.send_watch_alert")
    mock_log = mocker.patch("cron.price_check.log_watch_notification")

    process_watch(sample_watch)

    mock_hist.assert_called_once_with(
        watch_id="watch-uuid-1", swisstimehouse_price=29000.0, myntra_price=None
    )
    mock_alert.assert_called_once()
    _, kwargs = mock_alert.call_args
    assert kwargs["watch_name"] == "Casio G1714"
    assert kwargs["price"] == 29000.0
    assert kwargs["seller"] == "Swiss Time House"
    mock_log.assert_called_once_with("watch-uuid-1", 29000.0, "Swiss Time House")


def test_process_watch_skips_above_target(sample_watch, mocker):
    from cron.price_check import process_watch

    mocker.patch(
        "cron.price_check.fetch_swisstimehouse",
        return_value={
            "name": "Casio G1714", "brand": "Casio", "reference": "G1714", "price": 34997.0
        },
    )
    mocker.patch("cron.price_check.insert_watch_price_history")
    mock_alert = mocker.patch("cron.price_check.send_watch_alert")

    process_watch(sample_watch)
    mock_alert.assert_not_called()


def test_process_watch_skips_when_not_lower_than_last_notified(sample_watch, mocker):
    from cron.price_check import process_watch

    mocker.patch(
        "cron.price_check.fetch_swisstimehouse",
        return_value={
            "name": "Casio G1714", "brand": "Casio", "reference": "G1714", "price": 29000.0
        },
    )
    mocker.patch("cron.price_check.insert_watch_price_history")
    mocker.patch("cron.price_check.get_last_watch_notified_price", return_value=29000.0)
    mock_alert = mocker.patch("cron.price_check.send_watch_alert")

    process_watch(sample_watch)
    mock_alert.assert_not_called()


def test_process_watch_skips_when_no_price(sample_watch, mocker):
    from cron.price_check import process_watch

    mocker.patch("cron.price_check.fetch_swisstimehouse", return_value=None)
    mock_hist = mocker.patch("cron.price_check.insert_watch_price_history")
    mock_alert = mocker.patch("cron.price_check.send_watch_alert")

    process_watch(sample_watch)
    mock_hist.assert_called_once_with(
        watch_id="watch-uuid-1", swisstimehouse_price=None, myntra_price=None
    )
    mock_alert.assert_not_called()


def test_run_checks_watches_too(mocker):
    from cron.price_check import run

    mocker.patch("cron.price_check.get_games", return_value=[])
    mocker.patch(
        "cron.price_check.get_watches",
        return_value=[{"id": "w1", "name": "Casio G1714"}],
    )
    mock_process_watch = mocker.patch("cron.price_check.process_watch")

    run()
    mock_process_watch.assert_called_once_with({"id": "w1", "name": "Casio G1714"})


def test_process_watch_handles_missing_url(sample_watch, mocker):
    from cron.price_check import process_watch

    sample_watch = {**sample_watch, "swisstimehouse_url": None}
    mock_fetch = mocker.patch("cron.price_check.fetch_swisstimehouse")
    mock_hist = mocker.patch("cron.price_check.insert_watch_price_history")
    mock_alert = mocker.patch("cron.price_check.send_watch_alert")

    process_watch(sample_watch)

    mock_fetch.assert_not_called()
    mock_hist.assert_called_once_with(
        watch_id="watch-uuid-1", swisstimehouse_price=None, myntra_price=None
    )
    mock_alert.assert_not_called()


def test_parse_scope_no_flags_runs_both():
    from cron.price_check import _parse_scope
    assert _parse_scope([]) == (True, True)


def test_parse_scope_games_only():
    from cron.price_check import _parse_scope
    assert _parse_scope(["--games"]) == (True, False)


def test_parse_scope_watches_only():
    from cron.price_check import _parse_scope
    assert _parse_scope(["--watches"]) == (False, True)


def test_parse_scope_both_flags():
    from cron.price_check import _parse_scope
    assert _parse_scope(["--games", "--watches"]) == (True, True)


def test_run_games_only_skips_watches(mocker):
    from cron.price_check import run
    mock_games = mocker.patch("cron.price_check.get_games", return_value=[])
    mock_watches = mocker.patch("cron.price_check.get_watches", return_value=[])
    run(games=True, watches=False)
    mock_games.assert_called_once()
    mock_watches.assert_not_called()


def test_run_watches_only_skips_games(mocker):
    from cron.price_check import run
    mock_games = mocker.patch("cron.price_check.get_games", return_value=[])
    mock_watches = mocker.patch("cron.price_check.get_watches", return_value=[])
    run(games=False, watches=True)
    mock_watches.assert_called_once()
    mock_games.assert_not_called()
