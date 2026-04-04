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
