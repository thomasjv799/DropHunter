"""OmniRoute's OpenAI-compatible, non-streaming chat API."""

import json
import math
import os
from urllib.parse import urlsplit

import requests
from dotenv import load_dotenv

from ai.base import AIProvider


class OmniRouteProvider(AIProvider):
    def __init__(self):
        load_dotenv()
        base = os.environ.get("OMNIROUTE_BASE_URL", "").strip().rstrip("/")
        self._key = os.environ.get("OMNIROUTE_API_KEY", "")
        self._model = os.environ.get("OMNIROUTE_MODEL", "").strip()
        if not base or not self._key or not self._model:
            raise EnvironmentError("Set OMNIROUTE_BASE_URL, OMNIROUTE_API_KEY and OMNIROUTE_MODEL.")
        parsed = urlsplit(base)
        local_http = parsed.scheme == "http" and parsed.hostname in {
            "localhost",
            "127.0.0.1",
            "::1",
        }
        if not parsed.hostname or not (parsed.scheme == "https" or local_http):
            raise ValueError("OMNIROUTE_BASE_URL requires HTTPS (HTTP is allowed on loopback).")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("OMNIROUTE_BASE_URL must not include credentials, query or fragment.")
        self._url = f"{base}/chat/completions"
        self._timeout = float(os.environ.get("OMNIROUTE_TIMEOUT_SECONDS") or "60")
        if not math.isfinite(self._timeout) or not 0 < self._timeout <= 120:
            raise ValueError("OMNIROUTE_TIMEOUT_SECONDS must be greater than 0 and at most 120.")

    def generate_text(self, prompt: str) -> str:
        result = self.chat_with_tools([{"role": "user", "content": prompt}], [])
        if "text" not in result:
            raise ValueError("OmniRoute returned tool calls when text was required.")
        return result["text"]

    def chat_with_tools(self, messages: list[dict], tools: list[dict]) -> dict:
        if not messages:
            raise ValueError("messages list cannot be empty")
        payload = {"model": self._model, "messages": messages}
        if tools:
            payload["tools"] = tools
        try:
            response = requests.post(
                self._url,
                headers={"Authorization": f"Bearer {self._key}"},
                json=payload,
                timeout=self._timeout,
                allow_redirects=False,
            )
            response.raise_for_status()
        except requests.HTTPError:
            raise RuntimeError(f"OmniRoute HTTP error {response.status_code}") from None
        except requests.RequestException as exc:
            raise RuntimeError(f"OmniRoute request failed ({type(exc).__name__})") from None
        try:
            data = response.json()
            choice = data["choices"][0]
            if choice.get("finish_reason") in {"length", "content_filter"}:
                raise ValueError("OmniRoute returned an incomplete response.")
            message = choice["message"]
            raw_usage = data.get("usage") or {}
            usage = (
                {
                    "input_tokens": raw_usage.get("prompt_tokens", 0),
                    "output_tokens": raw_usage.get("completion_tokens", 0),
                }
                if raw_usage
                else {}
            )
            if message.get("tool_calls"):
                calls = []
                for call in message["tool_calls"]:
                    function = call["function"]
                    arguments = json.loads(function["arguments"])
                    if not isinstance(arguments, dict) or not isinstance(function["name"], str):
                        raise ValueError("OmniRoute returned invalid tool arguments.")
                    calls.append({"name": function["name"], "arguments": arguments})
                return {"tool_calls": calls, "usage": usage}
            content = message.get("content")
            if not isinstance(content, str) or not content.strip():
                raise ValueError("OmniRoute returned no usable text.")
            return {"text": content, "usage": usage}
        except (KeyError, IndexError, TypeError, ValueError):
            raise ValueError("OmniRoute returned an invalid or incomplete response.") from None
