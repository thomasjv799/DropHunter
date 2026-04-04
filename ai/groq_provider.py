import json
import os

from dotenv import load_dotenv

from ai.base import AIProvider

_MODEL = "llama-3.3-70b-versatile"


class GroqProvider(AIProvider):
    def __init__(self):
        from groq import Groq

        load_dotenv()
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise EnvironmentError("GROQ_API_KEY is not set. Add it to your .env file.")
        self._client = Groq(api_key=api_key)

    def generate_text(self, prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content

    def chat_with_tools(self, messages: list[dict], tools: list[dict]) -> dict:
        response = self._client.chat.completions.create(
            model=_MODEL,
            messages=messages,
            tools=tools if tools else None,
        )
        message = response.choices[0].message
        if message.tool_calls:
            tool_calls = []
            for tc in message.tool_calls:
                try:
                    arguments = json.loads(tc.function.arguments)
                except json.JSONDecodeError as e:
                    raise ValueError(
                        f"Invalid JSON in tool call arguments: {tc.function.arguments!r}"
                    ) from e
                tool_calls.append(
                    {
                        "name": tc.function.name,
                        "arguments": arguments,
                    }
                )
            return {"tool_calls": tool_calls}
        return {"text": message.content}
