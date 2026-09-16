import pytest


def test_missing_discord_token_blocks_sweep_before_database(monkeypatch, mocker):
    from cron.preflight import check_config

    mocker.patch("cron.preflight.load_dotenv")
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    cursor = mocker.patch("cron.preflight._cursor")
    with pytest.raises(EnvironmentError, match="DISCORD_BOT_TOKEN"):
        check_config()
    cursor.assert_not_called()


def test_preflight_verifies_migrated_schema(monkeypatch, mocker):
    from cron.preflight import check_config

    monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")
    monkeypatch.setenv("OWNER_ID", "123")
    monkeypatch.setenv("ITAD_API_KEY", "test-key")
    cur = mocker.MagicMock()
    cur.fetchone.return_value = {"count": 7}
    mocker.patch("cron.preflight._cursor").return_value.__enter__.return_value = cur
    assert check_config() == 7
    statements = [call.args[0] for call in cur.execute.call_args_list]
    assert any("email" in sql for sql in statements)
    assert any("ops.job_runs" in sql for sql in statements)
