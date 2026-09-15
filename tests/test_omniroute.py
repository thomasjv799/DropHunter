import pytest
import requests


@pytest.fixture
def provider(monkeypatch):
    from ai.omniroute_provider import OmniRouteProvider

    monkeypatch.setenv("OMNIROUTE_BASE_URL", "https://router.example.com/v1/")
    monkeypatch.setenv("OMNIROUTE_API_KEY", "secret-test-key")
    monkeypatch.setenv("OMNIROUTE_MODEL", "my-combo")
    return OmniRouteProvider()


def test_text_request_and_usage(provider, mocker):
    post = mocker.patch("ai.omniroute_provider.requests.post")
    post.return_value.json.return_value = {
        "choices": [{"message": {"content": "Good deal"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 4},
    }
    assert provider.chat_with_tools([{"role": "user", "content": "Deal?"}], []) == {
        "text": "Good deal",
        "usage": {"input_tokens": 12, "output_tokens": 4},
    }
    assert post.call_args.args == ("https://router.example.com/v1/chat/completions",)
    assert post.call_args.kwargs["json"] == {
        "model": "my-combo",
        "messages": [{"role": "user", "content": "Deal?"}],
    }
    assert provider.generate_text("Deal?") == "Good deal"


def test_tool_call_normalization(provider, mocker):
    post = mocker.patch("ai.omniroute_provider.requests.post")
    post.return_value.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {
                                "name": "add_game",
                                "arguments": '{"title":"Hades"}',
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ]
    }
    tools = [{"type": "function", "function": {"name": "add_game"}}]
    assert provider.chat_with_tools([{"role": "user", "content": "Track Hades"}], tools) == {
        "tool_calls": [{"name": "add_game", "arguments": {"title": "Hades"}}],
        "usage": {},
    }
    assert post.call_args.kwargs["json"]["tools"] == tools


@pytest.mark.parametrize("arguments", ["oops", "[]", "null"])
def test_malformed_tool_arguments_rejected(provider, mocker, arguments):
    post = mocker.patch("ai.omniroute_provider.requests.post")
    post.return_value.json.return_value = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {"name": "add_game", "arguments": arguments},
                        },
                    ]
                },
                "finish_reason": "tool_calls",
            }
        ]
    }
    with pytest.raises(ValueError):
        provider.chat_with_tools([{"role": "user", "content": "hello"}], [])


@pytest.mark.parametrize(
    "response",
    [
        {"choices": []},
        {"choices": [{"message": {"content": None}}]},
        {"choices": [{"message": {"content": "partial"}, "finish_reason": "length"}]},
    ],
)
def test_empty_or_truncated_response_rejected(provider, mocker, response):
    post = mocker.patch("ai.omniroute_provider.requests.post")
    post.return_value.json.return_value = response
    with pytest.raises(ValueError):
        provider.generate_text("hello")


def test_http_error_propagates_without_response_body(provider, mocker):
    post = mocker.patch("ai.omniroute_provider.requests.post")
    post.return_value.status_code = 401
    post.return_value.raise_for_status.side_effect = requests.HTTPError("secret-test-key")
    with pytest.raises(RuntimeError, match="401") as exc:
        provider.generate_text("hello")
    assert "secret-test-key" not in str(exc.value)


def test_provider_selection_uses_omniroute(provider, monkeypatch):
    from ai import get_provider
    from ai.omniroute_provider import OmniRouteProvider

    monkeypatch.setenv("AI_PROVIDER", "omniroute")
    assert isinstance(get_provider(), OmniRouteProvider)


def test_remote_plaintext_endpoint_rejected(provider, monkeypatch):
    from ai.omniroute_provider import OmniRouteProvider

    monkeypatch.setenv("OMNIROUTE_BASE_URL", "http://router.example.com/v1")
    with pytest.raises(ValueError, match="HTTPS"):
        OmniRouteProvider()
