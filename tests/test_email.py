import pytest
import requests


@pytest.fixture
def email_config(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "secret-test-key")
    monkeypatch.setenv("EMAIL_FROM", "DropHunter <alerts@example.com>")


def test_resend_payload_and_success(email_config, mocker):
    from utils.email import send_email

    post = mocker.patch("utils.email.requests.post")
    assert send_email("user@example.com", "Deal", "<p>Deal</p>", "Deal") is True
    assert post.call_args.args == ("https://api.resend.com/emails",)
    assert post.call_args.kwargs["json"] == {
        "from": "DropHunter <alerts@example.com>",
        "to": ["user@example.com"],
        "subject": "Deal",
        "html": "<p>Deal</p>",
        "text": "Deal",
    }
    assert post.call_args.kwargs["timeout"] == 15


def test_resend_failure_is_swallowed_and_redacted(email_config, mocker, caplog):
    from utils.email import send_email

    mocker.patch("utils.email.requests.post", side_effect=requests.Timeout("secret-test-key"))
    assert send_email("user@example.com", "Deal", "<p>Deal</p>") is False
    assert "secret-test-key" not in caplog.text
    assert "user@example.com" not in caplog.text


def test_resend_http_error_is_failure(email_config, mocker):
    from utils.email import send_email

    post = mocker.patch("utils.email.requests.post")
    post.return_value.raise_for_status.side_effect = requests.HTTPError("403")
    assert send_email("user@example.com", "Deal", "Deal") is False


def test_unconfigured_email_does_not_make_request(monkeypatch, mocker):
    from utils.email import send_email

    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    mocker.patch("utils.email.load_dotenv")
    post = mocker.patch("utils.email.requests.post")
    assert send_email("user@example.com", "Deal", "Deal") is False
    post.assert_not_called()


@pytest.mark.parametrize("address", ["", "x", "a@b", "a@b.com\nBcc: x@y.com", "a b@x.com"])
def test_email_validation_rejects_invalid_addresses(address):
    from utils.email import validate_email

    with pytest.raises(ValueError):
        validate_email(address)


def test_email_validation_trims_input():
    from utils.email import validate_email

    assert validate_email("  user@example.com  ") == "user@example.com"
