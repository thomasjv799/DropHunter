from unittest.mock import AsyncMock, MagicMock

import pytest

from db import client as db


def test_unapproved_user_cannot_register_email(mocker):
    mocker.patch.object(db, "is_user_allowed", return_value=False)
    cursor = mocker.patch.object(db, "_cursor")
    with pytest.raises(PermissionError):
        db.set_user_email("stranger", "x@example.com")
    cursor.assert_not_called()


def test_owner_can_store_email_without_existing_row(monkeypatch, mocker):
    monkeypatch.setenv("OWNER_ID", "owner")
    cur = MagicMock()
    mocker.patch.object(db, "_cursor").return_value.__enter__.return_value = cur
    assert db.set_user_email("owner", " x@example.com ") is True
    sql, params = cur.execute.call_args.args
    assert "INSERT INTO allowed_users" in sql
    assert "ON CONFLICT" in sql
    assert params == ("owner", "x@example.com")


def test_revoked_user_cannot_be_reinserted_by_email_update(monkeypatch, mocker):
    monkeypatch.setenv("OWNER_ID", "owner")
    mocker.patch.object(db, "is_user_allowed", return_value=True)
    cur = MagicMock(rowcount=0)
    mocker.patch.object(db, "_cursor").return_value.__enter__.return_value = cur
    assert db.set_user_email("permitted", "x@example.com") is False
    assert "UPDATE allowed_users" in cur.execute.call_args.args[0]


@pytest.mark.asyncio
async def test_setemail_command_rejects_unauthorized_user(mocker):
    from bot.client import setemail

    mocker.patch.object(db, "set_user_email", side_effect=PermissionError)
    interaction = MagicMock()
    interaction.user.id = 123
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    await setemail.callback(interaction, "x@example.com")
    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    assert "not authorized" in interaction.followup.send.call_args.args[0]
