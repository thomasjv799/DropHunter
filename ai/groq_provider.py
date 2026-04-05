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
        import re
        import groq

        try:
            response = self._client.chat.completions.create(
                model=_MODEL,
                messages=messages,
                tools=tools if tools else None,
            )
        except groq.BadRequestError as e:
            body = getattr(e, "body", {})
            err = body.get("error", {})
            if err.get("code") == "tool_use_failed" and "failed_generation" in err:
                failed_gen = err["failed_generation"]
                # Try to salvage different malformed formats:
                # <function=get_current_price{"title": "..."}</function>
                # <function=get_current_price {"title": "..."}>
                match = re.search(r"<function=([a-zA-Z0-9_]+)\s*(.*)", failed_gen)
                if match:
                    name = match.group(1)
                    args_str = match.group(2).strip()
                    if args_str.endswith("</function>"):
                        args_str = args_str[:-11].strip()
                    elif args_str.endswith(">"):
                        args_str = args_str[:-1].strip()

                    try:
                        args = json.loads(args_str) if args_str else {}
                        return {"tool_calls": [{"name": name, "arguments": args}], "usage": {}}
                    except json.JSONDecodeError:
                        pass
            raise

        usage = {}
        if response.usage is not None:
            usage = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            }

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
            return {"tool_calls": tool_calls, "usage": usage}
        return {"text": message.content, "usage": usage}
