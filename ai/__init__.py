import logging
import os

from dotenv import load_dotenv

from ai.base import AIProvider

logger = logging.getLogger("drophunter.ai")


class _FallbackProvider(AIProvider):
    """Wraps a primary and fallback provider. On any exception from primary, uses fallback."""

    def __init__(self, primary: AIProvider, fallback: AIProvider):
        self._primary = primary
        self._fallback = fallback

    def generate_text(self, prompt: str) -> str:
        try:
            return self._primary.generate_text(prompt)
        except Exception as exc:
            logger.warning("Primary provider failed, falling back to Gemini: %s", exc)
            return self._fallback.generate_text(prompt)

    def chat_with_tools(self, messages: list[dict], tools: list[dict]) -> dict:
        try:
            return self._primary.chat_with_tools(messages, tools)
        except Exception as exc:
            logger.warning("Primary provider failed, falling back to Gemini: %s", exc)
            return self._fallback.chat_with_tools(messages, tools)


def get_provider() -> AIProvider:
    """
    Return the configured AI provider.
    - If AI_PROVIDER=groq (default) and GEMINI_API_KEY is set, wraps Groq with Gemini fallback.
    - If AI_PROVIDER=gemini, returns Gemini directly.
    - If AI_PROVIDER=groq and no GEMINI_API_KEY, returns Groq directly.
    """
    load_dotenv()
    provider = os.environ.get("AI_PROVIDER", "groq").lower()

    if provider == "gemini":
        from ai.gemini_provider import GeminiProvider
        return GeminiProvider()

    if provider == "groq":
        from ai.groq_provider import GroqProvider
        groq = GroqProvider()
        if os.environ.get("GEMINI_API_KEY"):
            from ai.gemini_provider import GeminiProvider
            return _FallbackProvider(primary=groq, fallback=GeminiProvider())
        return groq

    raise ValueError(f"Unknown AI_PROVIDER: {provider!r}. Must be 'groq' or 'gemini'.")
