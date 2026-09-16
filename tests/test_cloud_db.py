from unittest.mock import MagicMock

import pytest

from db import client as db


@pytest.fixture
def connection(monkeypatch, mocker):
    monkeypatch.setattr(db, "_conn", None)
    mocker.patch("db.client.load_dotenv")
    for key in ("DATABASE_URL", "LOCAL_DB_URL", "DB_SCHEMA"):
        monkeypatch.delenv(key, raising=False)
    conn = MagicMock(closed=False)
    connect = mocker.patch("db.client.psycopg2.connect", return_value=conn)
    return connect


def test_cloud_dsn_takes_precedence(connection, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://cloud/db")
    monkeypatch.setenv("LOCAL_DB_URL", "postgresql://local/db")
    monkeypatch.setenv("DB_SCHEMA", "public")
    conn = db._ensure_conn()
    assert connection.call_args.args == ("postgresql://cloud/db",)
    assert connection.call_args.kwargs["options"] == "-c search_path=pg_catalog,public"
    assert connection.call_args.kwargs["connect_timeout"] == 15
    assert conn.autocommit is True


def test_local_dsn_remains_supported(connection, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("LOCAL_DB_URL", "postgresql://local/db")
    db._ensure_conn()
    assert connection.call_args.args == ("postgresql://local/db",)
    assert connection.call_args.kwargs["options"] == "-c search_path=pg_catalog,drophunter"


def test_missing_dsn_has_actionable_error(connection):
    with pytest.raises(EnvironmentError, match="DATABASE_URL"):
        db._ensure_conn()
    connection.assert_not_called()


def test_invalid_schema_never_reaches_database(connection, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://cloud/db")
    monkeypatch.setenv("DB_SCHEMA", "public -c log_statement=all")
    with pytest.raises(ValueError, match="DB_SCHEMA"):
        db._ensure_conn()
    connection.assert_not_called()
