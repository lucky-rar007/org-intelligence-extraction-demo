"""Utility for loading and rendering prompt templates from the prompts/ directory."""

import logging
from pathlib import Path
from typing import Any

from config import PROMPTS_DIR

logger = logging.getLogger(__name__)


class PromptNotFoundError(Exception):
    """Raised when a requested prompt template file does not exist on disk."""
    pass


class PromptRenderError(Exception):
    """Raised when there is an error rendering the prompt template."""
    pass


class PromptLoader:
    """Loads and renders prompt templates from the configured prompts directory."""

    def __init__(self, prompts_dir: Path = PROMPTS_DIR) -> None:
        """Initialize PromptLoader with a prompts directory path."""
        self.prompts_dir = prompts_dir

    def load_prompt(self, prompt_name: str) -> str:
        """Load the raw text content of a prompt template file.

        Args:
            prompt_name: The filename of the prompt template (without extension).

        Returns:
            The raw text content of the prompt template.

        Raises:
            PromptNotFoundError: If the prompt template file does not exist.
        """
        file_path = self.prompts_dir / f"{prompt_name}.txt"

        if not file_path.exists() or not file_path.is_file():
            logger.error("Prompt missing: %s", file_path)
            raise PromptNotFoundError(
                f"Prompt template file '{prompt_name}.txt' not found at {self.prompts_dir}"
            )

        try:
            content = file_path.read_text(encoding="utf-8")
            logger.info("Prompt loaded: %s", prompt_name)
            return content
        except Exception as e:
            logger.error("Failed to read prompt file %s: %s", file_path, str(e))
            raise PromptNotFoundError(
                f"Failed to load prompt '{prompt_name}': {e}"
            ) from e

    def render_prompt(self, prompt_name: str, variables: dict[str, Any]) -> str:
        """Load a prompt template and render it using the provided variables.

        Args:
            prompt_name: The name of the prompt template.
            variables: A dictionary of key-value pairs to format the template placeholders.

        Returns:
            The fully rendered prompt string.

        Raises:
            PromptNotFoundError: If the prompt template file does not exist.
            PromptRenderError: If the variables do not match the template placeholders.
        """
        template = self.load_prompt(prompt_name)
        try:
            rendered = template.format(**variables)
            logger.info("Prompt rendered: %s", prompt_name)
            return rendered
        except KeyError as e:
            logger.error("Render failure: prompt=%s, missing variable=%s", prompt_name, str(e))
            raise PromptRenderError(
                f"Missing template variable {e} for prompt '{prompt_name}'"
            ) from e
        except Exception as e:
            logger.error("Render failure: prompt=%s. Error: %s", prompt_name, str(e))
            raise PromptRenderError(
                f"Failed to render prompt '{prompt_name}': {e}"
            ) from e
