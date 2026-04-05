# tests/test_providers.py
from unittest.mock import MagicMock


# ── GroqProvider ────────────────────────────────────────────────────────────

def _make_groq_response(content=None, tool_calls=None, prompt_tokens=10, completion_tokens=20):
    """Build a mock Groq chat completion response."""
    response = MagicMock()
    response.usage.prompt_tokens = prompt_tokens
    response.usage.completion_tokens = completion_tokens
    msg = response.choices[0].message
    msg.content = content
    msg.tool_calls = tool_calls
    return response


def _groq_provider(mocker, response):
    """Return a GroqProvider whose underlying client returns `response`."""
    mocker.patch.dict("os.environ", {"GROQ_API_KEY": "test-key"})
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = response
    mocker.patch("groq.Groq", return_value=mock_client)
    from ai.groq_provider import GroqProvider
    return GroqProvider()


def test_groq_chat_with_tools_text_response_has_usage(mocker):
    response = _make_groq_response(content="Hello!", tool_calls=None)
    provider = _groq_provider(mocker, response)
    result = provider.chat_with_tools(
        messages=[{"role": "user", "content": "hi"}], tools=[]
    )
    assert "text" in result
    assert result["usage"] == {"input_tokens": 10, "output_tokens": 20}


def test_groq_chat_with_tools_tool_call_response_has_usage(mocker):
    mock_tc = MagicMock()
    mock_tc.function.name = "list_games"
    mock_tc.function.arguments = "{}"
    response = _make_groq_response(tool_calls=[mock_tc], prompt_tokens=15, completion_tokens=5)
    provider = _groq_provider(mocker, response)

    tools = [{"type": "function", "function": {"name": "list_games", "description": "...", "parameters": {}}}]
    result = provider.chat_with_tools(
        messages=[{"role": "user", "content": "list"}], tools=tools
    )
    assert "tool_calls" in result
    assert result["usage"] == {"input_tokens": 15, "output_tokens": 5}


# ── GeminiProvider ───────────────────────────────────────────────────────────

def _make_gemini_chat_response(text=None, tool_name=None, prompt_tokens=8, candidate_tokens=12):
    """Build a mock Gemini chat response."""
    response = MagicMock()
    response.usage_metadata.prompt_token_count = prompt_tokens
    response.usage_metadata.candidates_token_count = candidate_tokens
    if tool_name:
        part = MagicMock()
        part.function_call.name = tool_name
        part.function_call.args = {}
        response.parts = [part]
        response.text = None
    else:
        part = MagicMock()
        part.function_call.name = ""
        response.parts = [part]
        response.text = text or "Hi there"
    return response


def _gemini_provider(mocker, chat_response):
    """Return a GeminiProvider whose chat returns `chat_response`."""
    mocker.patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
    mocker.patch("google.generativeai.configure")
    mock_chat = MagicMock()
    mock_chat.send_message.return_value = chat_response
    mock_model = MagicMock()
    mock_model.start_chat.return_value = mock_chat
    mocker.patch("google.generativeai.GenerativeModel", return_value=mock_model)
    from ai.gemini_provider import GeminiProvider
    return GeminiProvider()


def test_gemini_chat_with_tools_text_response_has_usage(mocker):
    response = _make_gemini_chat_response(text="Here's the list.", prompt_tokens=8, candidate_tokens=12)
    provider = _gemini_provider(mocker, response)
    result = provider.chat_with_tools(
        messages=[{"role": "user", "content": "hi"}], tools=[]
    )
    assert "text" in result
    assert result["usage"] == {"input_tokens": 8, "output_tokens": 12}


def test_gemini_chat_with_tools_tool_call_response_has_usage(mocker):
    response = _make_gemini_chat_response(tool_name="list_games", prompt_tokens=5, candidate_tokens=3)
    provider = _gemini_provider(mocker, response)
    tools = [{"type": "function", "function": {"name": "list_games", "description": "...", "parameters": {}}}]
    result = provider.chat_with_tools(
        messages=[{"role": "user", "content": "list"}], tools=tools
    )
    assert "tool_calls" in result
    assert result["usage"] == {"input_tokens": 5, "output_tokens": 3}
