"""
Simple Custom LLM client - override _build_body() for different APIs.
"""

import requests
import json
import logging
from typing import Any, Dict, Optional, Sequence
from llama_index.core.base.llms.types import (
    ChatMessage,
    ChatResponse,
    ChatResponseGen,
    CompletionResponse,
    CompletionResponseGen,
    LLMMetadata,
)
from llama_index.core.llms.callbacks import llm_chat_callback, llm_completion_callback
from llama_index.core.llms.custom import CustomLLM

logger = logging.getLogger(__name__)


class CustomGatewayLLM(CustomLLM):
    """Generic LLM client - override _build_body() for different APIs."""

    # Configuration
    api_url: str
    model_name: str
    temperature: float = 0.1
    max_tokens: int = 2048
    request_timeout: float = 120.0

    # Optional
    api_key: Optional[str] = None
    use_bearer_token: bool = True
    custom_headers: Dict[str, str] = {}
    custom_response_parser: str = ""

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(
            context_window=4096,
            num_output=self.max_tokens,
            model_name=self.model_name,
        )

    def _build_headers(self) -> Dict[str, str]:
        """Build request headers."""
        headers = {"Content-Type": "application/json"}
        if self.api_key and self.use_bearer_token:
            headers["Authorization"] = f"Bearer {self.api_key}"
        headers.update(self.custom_headers)
        return headers

    def _build_body(self, prompt: str) -> Dict[str, Any]:
        """Build request body - OVERRIDE THIS for different APIs."""
        return {
            "model": self.model_name,
            "prompt": prompt,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

    def _parse_response(self, response: requests.Response) -> str:
        """Parse response - handles common formats."""
        # Try regular JSON first
        try:
            data = response.json()
        except json.JSONDecodeError:
            # Handle NDJSON (Ollama streaming)
            lines = [line.strip() for line in response.text.split('\n') if line.strip()]
            if lines:
                objects = [json.loads(line) for line in lines]
                if all("response" in obj for obj in objects):
                    combined = "".join(obj.get("response", "") for obj in objects)
                    data = objects[-1].copy()
                    data["response"] = combined
                else:
                    data = objects[-1]
            else:
                raise ValueError(f"Could not parse response: {response.text[:200]}")

        # Custom parser (e.g., "data.result.text")
        if self.custom_response_parser:
            value = data
            for key in self.custom_response_parser.split("."):
                value = value.get(key, {}) if isinstance(value, dict) else {}
            return str(value) if value else ""

        # Auto-detect common formats
        if "response" in data:  # Ollama
            return data["response"]
        if "content" in data and isinstance(data["content"], list):  # Anthropic
            return data["content"][0].get("text", "")
        if "result" in data and isinstance(data["result"], list):  # Gateway
            return data["result"][0].get("text", "")
        if "choices" in data:  # OpenAI
            return data["choices"][0].get("text", "")
        if "message" in data:  # OpenAI chat
            return data["message"].get("content", "")

        # Common fields
        for field in ["text", "output", "completion"]:
            if field in data:
                return str(data[field])

        raise ValueError(f"Could not parse response. Keys: {list(data.keys())}")

    @llm_completion_callback()
    def complete(self, prompt: str, **kwargs: Any) -> CompletionResponse:
        """Main completion method."""
        logger.info(f"LLM call: {self.api_url} | {self.model_name}")

        try:
            response = requests.post(
                self.api_url,
                headers=self._build_headers(),
                json=self._build_body(prompt),
                timeout=self.request_timeout,
            )
            response.raise_for_status()
            text = self._parse_response(response)

            if not text:
                return CompletionResponse(text="Error: Empty response")

            logger.info(f"Response: {text[:100]}...")
            return CompletionResponse(text=text)

        except Exception as e:
            logger.error(f"LLM error: {e}")
            raise RuntimeError(f"LLM request failed: {e}")

    @llm_completion_callback()
    def stream_complete(self, prompt: str, **kwargs: Any) -> CompletionResponseGen:
        yield self.complete(prompt, **kwargs)

    @llm_chat_callback()
    def chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResponse:
        prompt = "\n".join([f"{msg.role}: {msg.content}" for msg in messages])
        completion = self.complete(prompt, **kwargs)
        return ChatResponse(message=ChatMessage(role="assistant", content=completion.text))

    @llm_chat_callback()
    def stream_chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResponseGen:
        yield self.chat(messages, **kwargs)


class CustomOllamaLLM(CustomGatewayLLM):
    """Ollama-specific LLM - hardcoded request format."""

    def _build_body(self, prompt: str) -> Dict[str, Any]:
        """Ollama API format."""
        return {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            }
        }
