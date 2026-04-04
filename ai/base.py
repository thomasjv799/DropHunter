from abc import ABC, abstractmethod


class AIProvider(ABC):
    @abstractmethod
    def generate_text(self, prompt: str) -> str:
        """Generate a plain text response for a prompt."""

    @abstractmethod
    def chat_with_tools(self, messages: list[dict], tools: list[dict]) -> dict:
        """
        Send messages with tool definitions. Returns either:
          {"text": "..."}                             — plain response
          {"tool_calls": [{"name": "...", "arguments": {...}}, ...]}  — tool invocation
        """
