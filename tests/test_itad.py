# tests/test_itad.py
from unittest.mock import MagicMock, patch

import pytest


def test_search_game_returns_match():
    from utils.itad import search_game

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"id": "018d937f-1111-7000-aaaa-000000000001", "slug": "eldenring", "title": "ELDEN RING"}
    ]
    with patch("utils.itad.requests.get", return_value=mock_response):
        result = search_game("Elden Ring")
    assert result is not None
    assert result["id"] == "018d937f-1111-7000-aaaa-000000000001"
    assert result["title"] == "ELDEN RING"


def test_search_game_returns_none_when_empty():
    from utils.itad import search_game

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = []
    with patch("utils.itad.requests.get", return_value=mock_response):
        result = search_game("Nonexistent Game XYZ")
    assert result is None


def test_get_best_price_returns_cheapest_deal():
    from utils.itad import get_best_price

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {
            "id": "018d937f-1111-7000-aaaa-000000000001",
            "deals": [
                {
                    "shop": {"id": "steam", "name": "Steam"},
                    "price": {"amount": 29.99, "currency": "USD"},
                    "regular": {"amount": 59.99, "currency": "USD"},
                    "cut": 50,
                },
                {
                    "shop": {"id": "gog", "name": "GOG"},
                    "price": {"amount": 24.99, "currency": "USD"},
                    "regular": {"amount": 59.99, "currency": "USD"},
                    "cut": 58,
                },
            ],
        }
    ]
    with patch("utils.itad.requests.post", return_value=mock_response):
        result = get_best_price("018d937f-1111-7000-aaaa-000000000001")
    assert result is not None
    assert result["price"] == 24.99
    assert result["store"] == "GOG"
    assert result["regular_price"] == 59.99
    assert result["cut"] == 58


def test_get_best_price_returns_none_when_no_deals():
    from utils.itad import get_best_price

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [{"id": "018d937f-1111-7000-aaaa-000000000001", "deals": []}]
    with patch("utils.itad.requests.post", return_value=mock_response):
        result = get_best_price("018d937f-1111-7000-aaaa-000000000001")
    assert result is None


def test_search_game_raises_on_http_error():
    import requests as req

    from utils.itad import search_game

    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = req.HTTPError("403 Forbidden")
    with patch("utils.itad.requests.get", return_value=mock_response):
        with pytest.raises(req.HTTPError):
            search_game("Elden Ring")


def test_get_best_price_raises_on_http_error():
    import requests as req

    from utils.itad import get_best_price

    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = req.HTTPError("500 Server Error")
    with patch("utils.itad.requests.post", return_value=mock_response):
        with pytest.raises(req.HTTPError):
            get_best_price("018d937f-1111-7000-aaaa-000000000001")
