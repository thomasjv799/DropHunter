# tests/test_discord_webhook.py
import pytest


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


def test_send_dm_raises_when_token_missing(mocker, monkeypatch):
    from utils import discord

    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    mocker.patch("utils.discord.load_dotenv")
    with pytest.raises(EnvironmentError, match="DISCORD_BOT_TOKEN"):
        discord.send_dm("user42", "hi")
