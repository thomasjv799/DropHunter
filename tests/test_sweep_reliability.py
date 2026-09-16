from datetime import datetime
from unittest.mock import MagicMock

import pytest

from cron import price_check as cron


@pytest.fixture
def eligible_game(mocker):
    game = {"id": "g1", "user_id": "A", "title": "<Hades>", "itad_id": "itad1"}
    mocker.patch.object(
        cron,
        "get_best_price",
        return_value={
            "price": 10,
            "regular_price": 30,
            "store": "Steam",
            "cut": 67,
        },
    )
    mocker.patch.object(cron, "insert_price_history")
    mocker.patch.object(cron, "get_historical_low", return_value=10)
    mocker.patch.object(cron, "get_last_notified_price", return_value=None)
    mocker.patch.object(cron, "is_user_allowed", return_value=True)
    mocker.patch.object(
        cron,
        "get_provider",
        return_value=MagicMock(
            generate_text=MagicMock(return_value="Buy <now>!"),
        ),
    )
    mocker.patch.object(cron, "log_notification")
    mocker.patch.object(cron, "send_dm")
    mocker.patch.object(cron, "get_user_email", return_value=None)
    return game


def test_ai_failure_does_not_suppress_deal(eligible_game, mocker):
    mocker.patch.object(cron, "get_provider", side_effect=RuntimeError("quota"))
    cron.process_game(eligible_game)
    cron.send_dm.assert_called_once()
    cron.log_notification.assert_called_once_with("g1", 10)


def test_email_is_per_user_and_html_escaped(eligible_game, mocker):
    lookup = mocker.patch.object(cron, "get_user_email", return_value="a@example.com")
    send = mocker.patch.object(cron, "send_email", return_value=True)
    assert cron.process_game(eligible_game) == 1
    lookup.assert_called_once_with("A")
    assert send.call_args.args[0] == "a@example.com"
    assert "&lt;Hades&gt;" in send.call_args.args[2]
    assert "<Hades>" not in send.call_args.args[2]


def test_email_failure_does_not_block_discord_history(eligible_game, mocker):
    mocker.patch.object(cron, "get_user_email", side_effect=RuntimeError("DB error"))
    cron.process_game(eligible_game)
    cron.send_dm.assert_called_once()
    cron.log_notification.assert_called_once_with("g1", 10)


def test_no_email_skips_sender(eligible_game, mocker):
    mocker.patch.object(cron, "get_user_email", return_value=None)
    send = mocker.patch.object(cron, "send_email")
    cron.process_game(eligible_game)
    send.assert_not_called()


def test_failed_discord_delivery_is_not_deduplicated(eligible_game):
    cron.send_dm.side_effect = RuntimeError("Discord unavailable")
    with pytest.raises(RuntimeError):
        cron.process_game(eligible_game)
    cron.log_notification.assert_not_called()


def test_partial_failure_processes_remaining_rows_and_fails_run(mocker):
    mocker.patch.object(
        cron,
        "get_games",
        return_value=[
            {"id": "bad", "title": "Bad"},
            {"id": "good", "title": "Good"},
        ],
    )
    process = mocker.patch.object(cron, "process_game", side_effect=[RuntimeError("secret"), 1])
    record = mocker.patch.object(cron, "log_job_run")
    assert cron.run(games=True, watches=False) == 1
    assert process.call_count == 2
    args = record.call_args.kwargs
    assert args["job_name"] == "drophunter.games"
    assert args["status"] == "error"
    assert args["counts"] == {"rows_swept": 2, "notifications_sent": 1, "errors": 1}
    assert "secret" not in args["error_text"]
    assert isinstance(args["started_at"], datetime)


def test_failed_fetch_still_records_job_failure(mocker):
    mocker.patch.object(cron, "get_games", side_effect=ConnectionError("secret DSN"))
    record = mocker.patch.object(cron, "log_job_run")
    assert cron.run(games=True, watches=False) == 1
    assert record.call_args.kwargs["status"] == "error"
    assert record.call_args.kwargs["counts"]["rows_swept"] == 0


def test_logging_failure_returns_nonzero(mocker):
    mocker.patch.object(cron, "get_games", return_value=[])
    mocker.patch.object(cron, "log_job_run", side_effect=RuntimeError("missing migration"))
    assert cron.run(games=True, watches=False) == 1


def test_empty_sweep_records_success(mocker):
    mocker.patch.object(cron, "get_games", return_value=[])
    record = mocker.patch.object(cron, "log_job_run")
    assert cron.run(games=True, watches=False) == 0
    assert record.call_args.kwargs["status"] == "ok"
    assert record.call_args.kwargs["counts"]["notifications_sent"] == 0
