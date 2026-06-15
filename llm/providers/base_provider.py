"""Base provider class for LLM integration."""

from abc import ABC, abstractmethod


class BaseLLMProvider(ABC):
    """Abstract base class for all LLM providers."""

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Generate response text for the given prompt."""
        pass

    @abstractmethod
    def verify_model_exists(self) -> None:
        """Verify that the configured model exists/is available."""
        pass
