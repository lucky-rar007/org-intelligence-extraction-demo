"""Ollama provider implementation for LLM integration."""

import subprocess
import httpx
import ollama
from .base_provider import BaseLLMProvider


class OllamaProvider(BaseLLMProvider):
    """LLM provider using local Ollama instance."""

    def __init__(
        self,
        base_url: str,
        model_name: str,
        timeout: int = 120,
        temperature: float = 0.0
    ) -> None:
        """Initialize the Ollama provider."""
        self.base_url = base_url
        self.model_name = model_name
        self.timeout = timeout
        self.temperature = temperature

    def verify_model_exists(self) -> None:
        """Verify that the configured model is installed locally in Ollama."""
        try:
            # Try running the 'ollama list' command directly via subprocess
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                check=True
            )
            output = result.stdout
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            # Fall back to using the python client library if the shell command fails
            try:
                client = ollama.Client(host=self.base_url)
                models_res = client.list()
                models = [m.model for m in getattr(models_res, "models", [])]
                output = "\n".join(models)
            except Exception as lib_err:
                raise ConnectionError(
                    f"Failed to connect to Ollama at {self.base_url} to verify models. "
                    f"Ensure Ollama is running. Error: {lib_err}"
                ) from e

        # Check if the configured model name is in the output/list
        if self.model_name not in output:
            raise ValueError(
                f"Required model '{self.model_name}' is NOT installed locally in Ollama. "
                f"Please run 'ollama pull {self.model_name}' before running the pipeline."
            )

    def generate(self, prompt: str) -> str:
        """Generate response text for the given prompt using Ollama."""
        try:
            client = ollama.Client(host=self.base_url, timeout=self.timeout)
            response = client.chat(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": self.temperature}
            )

            if not response or not hasattr(response, "message") or not response.message.content:
                raise ValueError("Received an empty or invalid response from Ollama.")

            return response.message.content.strip()

        except httpx.TimeoutException as e:
            raise TimeoutError(
                f"Ollama generation request timed out after {self.timeout} seconds: {e}"
            ) from e
        except (httpx.ConnectError, httpx.RequestError, ollama.RequestError) as e:
            raise ConnectionError(
                f"Failed to communicate with Ollama at {self.base_url}: {e}"
            ) from e
        except ollama.ResponseError as e:
            raise ValueError(
                f"Ollama returned an error response: {e}"
            ) from e
        except Exception as e:
            raise RuntimeError(
                f"An unexpected error occurred during Ollama generation: {e}"
            ) from e
