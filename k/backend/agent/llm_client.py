"""
LLM Client - Supports multiple LLM providers.
"""

import os
import logging
from typing import Optional, AsyncIterator
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseLLMClient(ABC):
    """Base class for LLM clients."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Generate a response from the LLM."""
        pass

    @abstractmethod
    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """Generate a streaming response from the LLM."""
        pass


class AnthropicClient(BaseLLMClient):
    """Anthropic Claude client."""

    def __init__(self, model: str = "claude-3-5-sonnet-20241022"):
        self.model = model
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic
                self._client = AsyncAnthropic(api_key=self.api_key)
            except ImportError:
                raise ImportError("anthropic package not installed. Run: pip install anthropic")
        return self._client

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        client = self._get_client()

        messages = [{"role": "user", "content": prompt}]

        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
            "temperature": temperature,
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        response = await client.messages.create(**kwargs)

        return response.content[0].text

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        client = self._get_client()

        messages = [{"role": "user", "content": prompt}]

        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
            "temperature": temperature,
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        async with client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text


class OllamaClient(BaseLLMClient):
    """Ollama client for local LLMs."""

    def __init__(self, model: str = "llama3.2:latest"):
        self.model = model
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import httpx
                self._client = httpx.AsyncClient(
                    base_url=self.base_url,
                    timeout=httpx.Timeout(120.0, connect=10.0),
                )
            except ImportError:
                raise ImportError("httpx package not installed. Run: pip install httpx")
        return self._client

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        client = self._get_client()

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            }
        }

        if system_prompt:
            payload["system"] = system_prompt

        response = await client.post("/api/generate", json=payload)
        response.raise_for_status()

        result = response.json()
        return result.get("response", "")

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        import httpx
        import json

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            }
        }

        if system_prompt:
            payload["system"] = system_prompt

        async with httpx.AsyncClient(base_url=self.base_url) as client:
            async with client.stream("POST", "/api/generate", json=payload, timeout=120.0) as response:
                async for line in response.aiter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            if "response" in data:
                                yield data["response"]
                        except json.JSONDecodeError:
                            continue


class LLMClientSelector:
    """Factory for creating LLM clients based on provider."""

    VALID_PROVIDERS = {"anthropic", "ollama"}

    PROVIDER_MODELS = {
        "anthropic": [
            "claude-3-5-sonnet-20241022",
            "claude-3-opus-20240229",
            "claude-3-haiku-20240307",
        ],
        "ollama": [
            "llama3.2:latest",
            "llama3.1:latest",
            "mistral:latest",
            "codellama:latest",
        ],
    }

    DEFAULT_MODELS = {
        "anthropic": "claude-3-5-sonnet-20241022",
        "ollama": "llama3.2:latest",
    }

    @classmethod
    def create_client(
        cls,
        provider: str = "ollama",
        model: Optional[str] = None,
    ) -> BaseLLMClient:
        """
        Create an LLM client for the specified provider.

        Args:
            provider: LLM provider ("anthropic" or "ollama")
            model: Specific model to use (optional)

        Returns:
            LLM client instance
        """
        # Normalize provider
        provider = provider.lower()

        # Validate provider
        if provider not in cls.VALID_PROVIDERS:
            logger.warning(f"Invalid provider '{provider}', falling back to ollama")
            provider = "ollama"

        # Get model
        if not model:
            model = cls.DEFAULT_MODELS[provider]
        elif model not in cls.PROVIDER_MODELS.get(provider, []):
            logger.warning(f"Model '{model}' not in known models for {provider}, using anyway")

        # Create client
        if provider == "anthropic":
            return AnthropicClient(model=model)
        else:
            return OllamaClient(model=model)

    @classmethod
    def get_available_models(cls, provider: str) -> list[str]:
        """Get available models for a provider."""
        return cls.PROVIDER_MODELS.get(provider.lower(), [])

    @classmethod
    def get_default_model(cls, provider: str) -> str:
        """Get default model for a provider."""
        return cls.DEFAULT_MODELS.get(provider.lower(), "llama3.2:latest")
