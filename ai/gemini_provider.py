import os

import google.generativeai as genai
from dotenv import load_dotenv

from ai.base import AIProvider

_MODEL = "gemini-3-flash-preview"


def _to_gemini_tools(tools: list) -> list:
    """Convert OpenAI-style tool dicts to Gemini FunctionDeclaration list."""
    declarations = []
    for t in tools:
        fn = t.get("function", {})
        declarations.append(
            genai.types.FunctionDeclaration(
                name=fn.get("name", ""),
                description=fn.get("description", ""),
                parameters=fn.get("parameters", {}),
            )
        )
    return [genai.types.Tool(function_declarations=declarations)] if declarations else []


def _to_gemini_history(messages: list) -> list:
    """Convert OpenAI-style message list to Gemini chat history, skipping system messages."""
    history = []
    for m in messages[:-1]:  # last message sent via send_message
        if m["role"] == "system":
            continue
        role = "user" if m["role"] == "user" else "model"
        history.append({"role": role, "parts": [m["content"]]})
    return history


class GeminiProvider(AIProvider):
    def __init__(self):
        load_dotenv()
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError("GEMINI_API_KEY is not set. Add it to your .env file.")
        genai.configure(api_key=api_key)
        self._model_name = _MODEL

    def generate_text(self, prompt: str) -> str:
        model = genai.GenerativeModel(self._model_name)
        response = model.generate_content(prompt)
        return response.text

    def chat_with_tools(self, messages: list, tools: list) -> dict:
        if not messages:
            raise ValueError("messages list cannot be empty")
        # Extract system message and pass as system_instruction
        system_instruction = None
        if messages and messages[0]["role"] == "system":
            system_instruction = messages[0]["content"]

        gemini_tools = _to_gemini_tools(tools)
        model = genai.GenerativeModel(
            self._model_name,
            tools=gemini_tools or None,
            system_instruction=system_instruction,
        )
        history = _to_gemini_history(messages)
        chat = model.start_chat(history=history)
        response = chat.send_message(messages[-1]["content"])

        tool_calls = [
            {"name": part.function_call.name, "arguments": dict(part.function_call.args)}
            for part in response.parts
            if part.function_call.name
        ]
        if tool_calls:
            return {"tool_calls": tool_calls}
        try:
            return {"text": response.text}
        except ValueError as exc:
            raise ValueError(
                f"Gemini returned no usable text (response may be blocked): {exc}"
            ) from exc
