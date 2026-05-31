# tests/test_discord_webhook.py
from unittest.mock import MagicMock, patch

import pytest


def test_send_deal_alert_posts_to_webhook():
    from utils.discord import send_deal_alert

    mock_response = MagicMock()
    mock_response.status_code = 204
    with patch("utils.discord.requests.post", return_value=mock_response) as mock_post:
        send_deal_alert(
            game_title="Elden Ring",
            price=29.99,
            regular_price=59.99,
            store="Steam",
            cut=50,
            ai_commentary="Lowest price in 2 years.",
        )
    mock_post.assert_called_once()
    payload = mock_post.call_args[1]["json"]
    assert "Elden Ring" in payload["content"]
    assert "29.99" in payload["content"]
    assert "Steam" in payload["content"]
    assert "Lowest price in 2 years." in payload["content"]
    mock_response.raise_for_status.assert_called_once()


def test_send_deal_alert_raises_when_webhook_url_missing(monkeypatch):
    from utils.discord import send_deal_alert

    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    with patch("utils.discord.load_dotenv"):
        with pytest.raises(EnvironmentError, match="DISCORD_WEBHOOK_URL"):
            send_deal_alert("Game", 9.99, 19.99, "GOG", 50, "Great deal.")


def test_send_watch_alert_posts_message(mocker, monkeypatch):
    from utils import discord

    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/webhook")
    mock_post = mocker.patch("utils.discord.requests.post")
    mock_post.return_value.raise_for_status.return_value = None

    discord.send_watch_alert(
        watch_name="Casio G1714",
        price=29000.0,
        seller="Swiss Time House",
        target_price=30000.0,
        ai_commentary="Great time to buy.",
    )

    mock_post.assert_called_once()
    _, kwargs = mock_post.call_args
    body = kwargs["json"]["content"]
    assert "Casio G1714" in body
    assert "29000" in body
    assert "Swiss Time House" in body


def test_send_dm_opens_channel_and_posts(mocker, monkeypatch):
    from utils import discord

    monkeypatch.setenv("DISCORD_BOT_TOKEN", "tok")
    open_resp = mocker.MagicMock()
    open_resp.json.return_value = {"id": "dm123"}
    open_resp.raise_for_status.return_value = None
    msg_resp = mocker.MagicMock()
    msg_resp.raise_for_status.return_value = None
    mock_post = mocker.patch("utils.discord.requests.post", side_effect=[open_resp, msg_resp])

    discord.send_dm("user42", "hello there")

    assert mock_post.call_count == 2
    open_call, msg_call = mock_post.call_args_list
    assert open_call.args[0].endswith("/users/@me/channels")
    assert open_call.kwargs["json"] == {"recipient_id": "user42"}
    assert msg_call.args[0].endswith("/channels/dm123/messages")
    assert msg_call.kwargs["json"] == {"content": "hello there"}
    assert "Bot tok" in open_call.kwargs["headers"]["Authorization"]
