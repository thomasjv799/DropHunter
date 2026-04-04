import os

from dotenv import load_dotenv


def get_provider():
    """Return the AI provider configured by the AI_PROVIDER env var (groq or gemini)."""
    load_dotenv()
    provider = os.environ.get("AI_PROVIDER", "groq").lower()
    if provider == "groq":
        from ai.groq_provider import GroqProvider

        return GroqProvider()
    if provider == "gemini":
        from ai.gemini_provider import GeminiProvider

        return GeminiProvider()
    raise ValueError(f"Unknown AI_PROVIDER: {provider!r}. Must be 'groq' or 'gemini'.")
