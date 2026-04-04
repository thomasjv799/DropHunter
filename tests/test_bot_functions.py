# tests/test_bot_functions.py


def test_add_game_success(mocker):
    from bot.functions import add_game

    mocker.patch("bot.functions.search_game", return_value={"id": "abc123", "title": "Elden Ring"})
    mock_db_add = mocker.patch("bot.functions.db_add_game", return_value={"title": "Elden Ring"})
    result = add_game("Elden Ring")
    assert "Elden Ring" in result
    assert "tracking" in result.lower()
    mock_db_add.assert_called_once_with("Elden Ring", "abc123")


def test_add_game_not_found(mocker):
    from bot.functions import add_game

    mocker.patch("bot.functions.search_game", return_value=None)
    result = add_game("Nonexistent XYZ 99999")
    assert "not found" in result.lower()


def test_remove_game_success(mocker):
    from bot.functions import remove_game

    mocker.patch("bot.functions.db_remove_game", return_value=True)
    result = remove_game("Elden Ring")
    assert "removed" in result.lower() or "no longer tracking" in result.lower()


def test_remove_game_not_found(mocker):
    from bot.functions import remove_game

    mocker.patch("bot.functions.db_remove_game", return_value=False)
    result = remove_game("Unknown Game")
    assert "not found" in result.lower() or "wasn't" in result.lower()


def test_list_games_with_games(mocker):
    from bot.functions import list_games

    mocker.patch(
        "bot.functions.db_get_games",
        return_value=[
            {"title": "Elden Ring"},
            {"title": "Hollow Knight"},
        ],
    )
    result = list_games()
    assert "Elden Ring" in result
    assert "Hollow Knight" in result


def test_list_games_empty(mocker):
    from bot.functions import list_games

    mocker.patch("bot.functions.db_get_games", return_value=[])
    result = list_games()
    assert "no games" in result.lower() or "empty" in result.lower()


def test_get_current_price_success(mocker):
    from bot.functions import get_current_price

    mocker.patch("bot.functions.search_game", return_value={"id": "abc123", "title": "Hades"})
    mocker.patch(
        "bot.functions.get_best_price",
        return_value={"price": 9.99, "regular_price": 24.99, "store": "Steam", "cut": 60},
    )
    result = get_current_price("Hades")
    assert "9.99" in result
    assert "Steam" in result


def test_get_current_price_not_found(mocker):
    from bot.functions import get_current_price

    mocker.patch("bot.functions.search_game", return_value=None)
    result = get_current_price("Unknown Game")
    assert "not found" in result.lower()


def test_get_recent_deals_with_results(mocker):
    from bot.functions import get_recent_deals

    mocker.patch(
        "bot.functions.db_get_recent_deals",
        return_value=[
            {"price": 9.99, "notified_at": "2026-04-04T00:00:00+00:00", "games": {"title": "Hades"}}
        ],
    )
    result = get_recent_deals()
    assert "Hades" in result
    assert "9.99" in result


def test_get_recent_deals_empty(mocker):
    from bot.functions import get_recent_deals

    mocker.patch("bot.functions.db_get_recent_deals", return_value=[])
    result = get_recent_deals()
    assert "no recent" in result.lower() or "no deals" in result.lower()


def test_dispatch_routes_to_correct_function(mocker):
    from bot.functions import dispatch

    mocker.patch("bot.functions.db_remove_game", return_value=True)
    result = dispatch("remove_game", {"title": "Hades"})
    assert "no longer tracking" in result.lower() or "removed" in result.lower()


def test_dispatch_returns_error_for_unknown_tool():
    from bot.functions import dispatch

    result = dispatch("nonexistent_tool", {})
    assert "unknown tool" in result.lower()
