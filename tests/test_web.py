"""API boundary tests: rejection must happen before any private data access."""

from unittest.mock import Mock
from uuid import uuid4

import pytest

from web.app import create_app

UID = "b08b0d32-9b0d-4ac7-b45b-c460853d7023"


@pytest.fixture
def client():
    repo = Mock()
    repo.account.return_value = {"discord_id": "123456789012345678", "approved": True}
    repo.list_games.return_value = {"items": [], "total": 0}
    repo.game.return_value = None
    app = create_app(repository=repo, verifier=lambda token: {"id": UID, "email": "a@example.com"})
    app.config["TESTING"] = True
    return app.test_client(), repo


def test_missing_token_cannot_read_data(client):
    http, repo = client
    assert http.get("/api/games").status_code == 401
    repo.list_games.assert_not_called()


def test_unapproved_account_cannot_read_data(client):
    http, repo = client
    repo.account.return_value = None
    assert http.get("/api/games", headers={"Authorization": "Bearer test"}).status_code == 403
    repo.list_games.assert_not_called()


def test_revocation_takes_effect_next_request(client):
    http, repo = client
    headers = {"Authorization": "Bearer test"}
    assert http.get("/api/games", headers=headers).status_code == 200
    repo.account.return_value = None
    assert http.get("/api/games", headers=headers).status_code == 403


@pytest.mark.parametrize("query", ["limit=500", "page=0", "sort=sql", "status=bad"])
def test_invalid_pagination_rejected(client, query):
    http, _ = client
    assert http.get("/api/games?" + query, headers={"Authorization": "Bearer t"}).status_code == 400


def test_foreign_game_history_is_not_found(client):
    http, _ = client
    assert (
        http.get(
            "/api/games/" + str(uuid4()) + "/history", headers={"Authorization": "Bearer t"}
        ).status_code
        == 404
    )


@pytest.mark.parametrize("target", [-1, "NaN", "Infinity", True, "oops"])
def test_invalid_targets_rejected(client, target):
    http, _ = client
    response = http.patch(
        "/api/games/" + str(uuid4()),
        json={"target_price": target},
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 400


def test_malformed_json_is_safe(client):
    http, _ = client
    response = http.patch(
        "/api/settings",
        data="{bad",
        content_type="application/json",
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 400
    assert response.is_json


def test_sensitive_error_not_returned(client):
    http, repo = client
    repo.list_games.side_effect = RuntimeError("postgres://password@private-host")
    response = http.get("/api/games", headers={"Authorization": "Bearer t"})
    assert response.status_code == 503
    assert b"password" not in response.data


def test_auth_verifier_rejects_invalid_token():
    from web.auth import AuthError

    def reject(token):
        raise AuthError("Session expired", 401)

    http = create_app(repository=Mock(), verifier=reject).test_client()
    assert http.get("/api/games", headers={"Authorization": "Bearer bad"}).status_code == 401


def test_supabase_identity_must_be_google_and_confirmed(monkeypatch):
    from web.auth import AuthError, verify_token

    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    response = Mock(status_code=200)
    response.json.return_value = {
        "id": UID,
        "email_confirmed_at": "now",
        "identities": [{"provider": "email"}],
    }
    monkeypatch.setattr("web.auth.requests.get", lambda *a, **k: response)
    with pytest.raises(AuthError):
        verify_token("token")
    response.json.return_value["identities"] = [{"provider": "google"}]
    assert verify_token("token")["id"] == UID


def test_email_repository_cannot_insert_non_owner(monkeypatch):
    from contextlib import contextmanager

    from web.repository import Repository

    cursor = Mock(rowcount=0)
    cursor.fetchone.return_value = None

    @contextmanager
    def connection():
        yield cursor

    monkeypatch.setenv("OWNER_ID", "999999")
    repo = Repository()
    monkeypatch.setattr(repo, "cursor", connection)
    with pytest.raises(PermissionError):
        repo.set_email("123456", "person@example.com")
    assert "INSERT" not in cursor.execute.call_args[0][0]


def test_search_confirmation_is_bound_to_authenticated_account(client, monkeypatch):
    from itsdangerous import URLSafeTimedSerializer

    http, repo = client
    monkeypatch.setenv("WEB_SECRET_KEY", "x" * 40)
    signer = URLSafeTimedSerializer("x" * 40, salt="game-selection-v1")
    token = signer.dumps({"user": str(uuid4()), "id": "game", "title": "Hades"})
    response = http.post(
        "/api/games",
        json={"selection": token, "target_price": 5},
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 403
    repo.add_game.assert_not_called()


def test_search_confirmation_cannot_be_forged(client, monkeypatch):
    http, repo = client
    monkeypatch.setenv("WEB_SECRET_KEY", "x" * 40)
    response = http.post(
        "/api/games",
        json={"selection": "forged", "target_price": 5},
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 400
    repo.add_game.assert_not_called()


def test_config_never_falls_back_to_service_key(monkeypatch):
    monkeypatch.delenv("SUPABASE_PUBLISHABLE_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_KEY", "secret-service-role")
    response = create_app(repository=Mock()).test_client().get("/api/config")
    assert response.status_code == 503
    assert b"secret-service-role" not in response.data
