# tests/test_ai.py
from unittest.mock import MagicMock, patch


def test_groq_generate_text():
    from ai.groq_provider import GroqProvider

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices = [
        MagicMock(message=MagicMock(content="Great deal! Buy now."))
    ]
    with patch("groq.Groq", return_value=mock_client):
        provider = GroqProvider()
        result = provider.generate_text("Is this a good deal?")
    assert result == "Great deal! Buy now."


def test_groq_chat_with_tools_returns_tool_call():
    from ai.groq_provider import GroqProvider

    tool_call = MagicMock()
    tool_call.function.name = "add_game"
    tool_call.function.arguments = '{"title": "Elden Ring"}'
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content=None,
                tool_calls=[tool_call],
            )
        )
    ]
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    with patch("groq.Groq", return_value=mock_client):
        provider = GroqProvider()
        result = provider.chat_with_tools(
            messages=[{"role": "user", "content": "Track Elden Ring"}],
            tools=[{"type": "function", "function": {"name": "add_game"}}],
        )
    assert result["tool_calls"] == [{"name": "add_game", "arguments": {"title": "Elden Ring"}}]


def test_groq_chat_with_tools_returns_text():
    from ai.groq_provider import GroqProvider

    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content="I can help with that.", tool_calls=None))
    ]
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    with patch("groq.Groq", return_value=mock_client):
        provider = GroqProvider()
        result = provider.chat_with_tools(
            messages=[{"role": "user", "content": "Hello"}],
            tools=[],
        )
    assert result["text"] == "I can help with that."
    assert "tool_calls" not in result


def test_gemini_generate_text():
    from ai.gemini_provider import GeminiProvider

    mock_model = MagicMock()
    mock_model.generate_content.return_value.text = "Solid deal, pick it up."
    mock_genai = MagicMock()
    mock_genai.GenerativeModel.return_value = mock_model
    with patch("ai.gemini_provider.genai", mock_genai):
        provider = GeminiProvider()
        result = provider.generate_text("Is this worth buying?")
    assert result == "Solid deal, pick it up."


def test_gemini_chat_with_tools_returns_tool_call():
    from ai.gemini_provider import GeminiProvider

    mock_part = MagicMock()
    mock_part.function_call.name = "list_games"
    mock_part.function_call.args = {}
    mock_part.text = None

    mock_response = MagicMock()
    mock_response.parts = [mock_part]

    mock_chat = MagicMock()
    mock_chat.send_message.return_value = mock_response

    mock_model = MagicMock()
    mock_model.start_chat.return_value = mock_chat

    mock_genai = MagicMock()
    mock_genai.GenerativeModel.return_value = mock_model

    with patch("ai.gemini_provider.genai", mock_genai):
        provider = GeminiProvider()
        result = provider.chat_with_tools(
            messages=[{"role": "user", "content": "What am I tracking?"}],
            tools=[{"type": "function", "function": {"name": "list_games"}}],
        )
    assert result["tool_calls"] == [{"name": "list_games", "arguments": {}}]


def test_gemini_chat_with_tools_returns_text():
    from ai.gemini_provider import GeminiProvider

    mock_part = MagicMock()
    mock_part.function_call.name = ""  # empty = no tool call

    mock_response = MagicMock()
    mock_response.parts = [mock_part]
    mock_response.text = "Here are your tracked games."

    mock_chat = MagicMock()
    mock_chat.send_message.return_value = mock_response

    mock_model = MagicMock()
    mock_model.start_chat.return_value = mock_chat

    mock_genai = MagicMock()
    mock_genai.GenerativeModel.return_value = mock_model

    with patch("ai.gemini_provider.genai", mock_genai):
        provider = GeminiProvider()
        result = provider.chat_with_tools(
            messages=[{"role": "user", "content": "Show me my games"}],
            tools=[],
        )
    assert result["text"] == "Here are your tracked games."
    assert "tool_calls" not in result
