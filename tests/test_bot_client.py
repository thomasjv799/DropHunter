
def test_is_owner_true(monkeypatch):
    from bot import client
    monkeypatch.setenv("OWNER_ID", "owner123")
    assert client._is_owner("owner123") is True


def test_is_owner_false(monkeypatch):
    from bot import client
    monkeypatch.setenv("OWNER_ID", "owner123")
    assert client._is_owner("someone_else") is False
