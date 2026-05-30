# tests/test_bot_functions.py


def test_add_game_success(mocker):
    from bot.functions import add_game

    mocker.patch("bot.functions.search_game", return_value={"id": "abc123", "title": "Elden Ring"})
    mock_db_add = mocker.patch("bot.functions.db_add_game", return_value={"title": "Elden Ring"})
    result = add_game("Elden Ring")
    assert "Elden Ring" in result
    assert "tracking" in result.lower()
    mock_db_add.assert_called_once_with("Elden Ring", "abc123", target_price=None)


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
        "bot.functions.get_all_prices",
        return_value=[{"price": 9.99, "regular_price": 24.99, "store": "Steam", "cut": 60}],
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


_CASIO_WATCH = {"name": "Casio G1714", "brand": "Casio", "reference": "G1714", "price": 34997.0}


def test_add_watch_asks_for_target_when_missing(mocker):
    from bot.functions import add_watch

    mocker.patch("bot.functions.fetch_swisstimehouse", return_value=_CASIO_WATCH)
    mock_db = mocker.patch("bot.functions.db_add_watch")
    result = add_watch("https://www.swisstimehouse.com/casio-g1714")
    assert "34997" in result
    assert "target" in result.lower()
    mock_db.assert_not_called()


def test_add_watch_stores_with_target(mocker):
    from bot.functions import add_watch

    mocker.patch("bot.functions.fetch_swisstimehouse", return_value=_CASIO_WATCH)
    mock_db = mocker.patch(
        "bot.functions.db_add_watch", return_value={"id": "w1", "name": "Casio G1714"}
    )
    result = add_watch("https://www.swisstimehouse.com/casio-g1714", target_price=30000.0)
    assert "Casio G1714" in result
    assert "30000" in result
    mock_db.assert_called_once_with(
        name="Casio G1714",
        brand="Casio",
        reference_no="G1714",
        target_price=30000.0,
        swisstimehouse_url="https://www.swisstimehouse.com/casio-g1714",
    )


def test_add_watch_fetch_failure(mocker):
    from bot.functions import add_watch

    mocker.patch("bot.functions.fetch_swisstimehouse", return_value=None)
    result = add_watch("https://www.swisstimehouse.com/bad", target_price=30000.0)
    assert (
        "couldn't" in result.lower()
        or "could not" in result.lower()
        or "unable" in result.lower()
    )


def test_list_watches_with_rows(mocker):
    from bot.functions import list_watches

    mocker.patch(
        "bot.functions.db_get_watches",
        return_value=[{"name": "Casio G1714", "target_price": 30000.0}],
    )
    result = list_watches()
    assert "Casio G1714" in result
    assert "30000" in result


def test_list_watches_empty(mocker):
    from bot.functions import list_watches

    mocker.patch("bot.functions.db_get_watches", return_value=[])
    result = list_watches()
    assert "empty" in result.lower() or "no watches" in result.lower()


def test_set_watch_target_success(mocker):
    from bot.functions import set_watch_target

    mocker.patch("bot.functions.db_set_watch_target", return_value=True)
    result = set_watch_target("Casio G1714", 25000.0)
    assert "25000" in result


def test_remove_watch_success(mocker):
    from bot.functions import remove_watch

    mocker.patch("bot.functions.db_remove_watch", return_value=True)
    result = remove_watch("Casio G1714")
    assert "no longer" in result.lower() or "removed" in result.lower()


def test_dispatch_routes_to_add_watch(mocker):
    from bot.functions import dispatch

    mocker.patch("bot.functions.fetch_swisstimehouse", return_value=_CASIO_WATCH)
    mocker.patch(
        "bot.functions.db_add_watch", return_value={"id": "w1", "name": "Casio G1714"}
    )
    result = dispatch(
        "add_watch",
        {"url": "https://www.swisstimehouse.com/casio-g1714", "target_price": 30000.0},
    )
    assert "Casio G1714" in result


def test_get_watch_price_not_found(mocker):
    from bot.functions import get_watch_price

    mocker.patch("bot.functions.db_find_watch_by_name", return_value=None)
    result = get_watch_price("Unknown Watch")
    assert "isn't on your watch list" in result.lower() or "not" in result.lower()


def test_get_watch_price_success(mocker):
    from bot.functions import get_watch_price

    mocker.patch(
        "bot.functions.db_find_watch_by_name",
        return_value={"name": "Casio G1714", "swisstimehouse_url": "https://www.swisstimehouse.com/casio-g1714"},
    )
    mocker.patch(
        "bot.functions.fetch_swisstimehouse",
        return_value={
            "name": "Casio G1714", "brand": "Casio",
            "reference": "G1714", "price": 33000.0,
        },
    )
    result = get_watch_price("casio g1714")
    assert "33000" in result
