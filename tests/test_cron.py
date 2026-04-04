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
    mock_process = mocker.patch("cron.price_check.process_game")

    run()

    assert mock_process.call_count == 2
    mock_process.assert_any_call({"id": "1", "title": "Game A", "itad_id": "aaa"})
    mock_process.assert_any_call({"id": "2", "title": "Game B", "itad_id": "bbb"})
