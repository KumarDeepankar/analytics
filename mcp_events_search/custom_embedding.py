"""
Simple Custom Embedding client - override _build_body() for different APIs.
"""

import requests
import json
import logging
from typing import Any, Dict, List, Optional
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.bridge.pydantic import PrivateAttr

logger = logging.getLogger(__name__)


class CustomGatewayEmbedding(BaseEmbedding):
    """Generic Embedding client - override _build_body() for different APIs."""

    # Configuration
    api_url: str
    request_timeout: float = 60.0

    # Optional
    api_key: Optional[str] = None
    use_bearer_token: bool = True
    custom_headers: Dict[str, str] = {}
    custom_response_parser: str = ""
    expected_dimension: Optional[int] = None  # Expected embedding dimension for validation

    # Private
    _session: Any = PrivateAttr()
    _detected_dimension: Optional[int] = PrivateAttr(default=None)

    def __init__(self, api_url: str, model_name: str = "default", expected_dimension: Optional[int] = None, **kwargs):
        """Initialize embedding client."""
        super().__init__(
            model_name=model_name,
            api_url=api_url,
            expected_dimension=expected_dimension,
            **kwargs
        )
        self._session = requests.Session()
        self._detected_dimension = None

    @classmethod
    def class_name(cls) -> str:
        return "CustomGatewayEmbedding"

    def _build_headers(self) -> Dict[str, str]:
        """Build request headers."""
        headers = {"Content-Type": "application/json"}
        if self.api_key and self.use_bearer_token:
            headers["Authorization"] = f"Bearer {self.api_key}"
        headers.update(self.custom_headers)
        return headers

    def _build_body(self, texts: List[str]) -> Dict[str, Any]:
        """Build request body - OVERRIDE THIS for different APIs."""
        return {
            "model": self.model_name,
            "input": texts,
        }

    def _parse_response(self, response: requests.Response) -> List[List[float]]:
        """Parse response - handles common formats. Returns list of embeddings."""
        # Try regular JSON first
        try:
            data = response.json()
        except json.JSONDecodeError:
            # Handle NDJSON (Ollama)
            lines = [line.strip() for line in response.text.split('\n') if line.strip()]
            if lines:
                objects = [json.loads(line) for line in lines]
                data = objects[-1]  # Use last object
            else:
                raise ValueError(f"Could not parse response: {response.text[:200]}")

        # Custom parser (e.g., "data.embeddings")
        if self.custom_response_parser:
            value = data
            for key in self.custom_response_parser.split("."):
                value = value.get(key, {}) if isinstance(value, dict) else {}
            # Check if it's list of embeddings or single embedding
            if isinstance(value, list):
                if value and isinstance(value[0], list):
                    return value  # List of embeddings
                elif value and isinstance(value[0], (int, float)):
                    return [value]  # Single embedding
            raise ValueError(f"Custom parser returned invalid format: {value}")

        # Auto-detect common formats
        # Ollama: {"embedding": [0.1, 0.2, ...]}
        if "embedding" in data and isinstance(data["embedding"], list):
            return [data["embedding"]]

        # OpenAI: {"data": [{"embedding": [...]}, {"embedding": [...]}]}
        if "data" in data and isinstance(data["data"], list):
            embeddings = []
            for item in data["data"]:
                if "embedding" in item:
                    embeddings.append(item["embedding"])
                elif "vector" in item:
                    embeddings.append(item["vector"])
            if embeddings:
                return embeddings

        # Gateway: {"result": {"embeddings": [[...], [...]]}}
        if "result" in data:
            result = data["result"]
            if isinstance(result, dict) and "embeddings" in result:
                return result["embeddings"]
            elif isinstance(result, list):
                return result

        # Direct arrays
        for key in ["embeddings", "vectors"]:
            if key in data and isinstance(data[key], list):
                result = data[key]
                if result and isinstance(result[0], list):
                    return result
                elif result and isinstance(result[0], (int, float)):
                    return [result]

        raise ValueError(f"Could not parse embedding response. Keys: {list(data.keys())}")

    def _validate_embedding_dimensions(self, embeddings: List[List[float]]) -> None:
        """
        Validate that all embeddings have consistent dimensions.
        Enforces constant dimension across all embeddings.

        Args:
            embeddings: List of embedding vectors

        Raises:
            ValueError: If dimensions are inconsistent or don't match expected dimension
        """
        if not embeddings:
            return

        # Check dimensions within this batch
        dimensions = [len(emb) for emb in embeddings]
        if len(set(dimensions)) > 1:
            raise ValueError(
                f"Inconsistent embedding dimensions within batch: {set(dimensions)}. "
                f"All embeddings must have the same dimension."
            )

        current_dim = dimensions[0]

        # First embedding - detect and store dimension
        if self._detected_dimension is None:
            self._detected_dimension = current_dim
            logger.info(f"✓ Detected embedding dimension: {current_dim}")

            # If expected dimension is configured, validate against it
            if self.expected_dimension is not None:
                if current_dim != self.expected_dimension:
                    raise ValueError(
                        f"❌ Embedding dimension mismatch! "
                        f"Expected: {self.expected_dimension}, Got: {current_dim}. "
                        f"Check your embedding model configuration."
                    )
                logger.info(f"✓ Validated: dimension matches expected {self.expected_dimension}")
        else:
            # Subsequent embeddings - ensure consistency with first
            if current_dim != self._detected_dimension:
                raise ValueError(
                    f"❌ Embedding dimension changed! "
                    f"Previously: {self._detected_dimension}, Now: {current_dim}. "
                    f"All embeddings must have constant dimension throughout the pipeline."
                )

    def _get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings for multiple texts."""
        logger.info(f"Embedding call: {self.api_url} | {len(texts)} texts")

        try:
            response = self._session.post(
                self.api_url,
                headers=self._build_headers(),
                json=self._build_body(texts),
                timeout=self.request_timeout,
            )
            response.raise_for_status()

            embeddings = self._parse_response(response)

            if len(embeddings) != len(texts):
                raise ValueError(f"Expected {len(texts)} embeddings, got {len(embeddings)}")

            # Validate embedding dimensions for consistency
            self._validate_embedding_dimensions(embeddings)

            logger.info(f"Got {len(embeddings)} embeddings, dim: {len(embeddings[0])}")
            return embeddings

        except Exception as e:
            logger.error(f"Embedding error: {e}")
            raise RuntimeError(f"Embedding request failed: {e}")

    def _get_query_embedding(self, query: str) -> List[float]:
        """Get embedding for query (required by LlamaIndex)."""
        return self._get_embeddings([query])[0]

    def _get_text_embedding(self, text: str) -> List[float]:
        """Get embedding for text (required by LlamaIndex)."""
        return self._get_embeddings([text])[0]

    def _get_text_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings for multiple texts (required by LlamaIndex)."""
        return self._get_embeddings(texts)

    async def _aget_query_embedding(self, query: str) -> List[float]:
        """Async query embedding (fallback to sync)."""
        return self._get_query_embedding(query)

    async def _aget_text_embedding(self, text: str) -> List[float]:
        """Async text embedding (fallback to sync)."""
        return self._get_text_embedding(text)


class CustomOllamaEmbedding(CustomGatewayEmbedding):
    """Ollama-specific embedding - handles one-at-a-time API limitation."""

    def _build_body(self, texts: List[str]) -> Dict[str, Any]:
        """Ollama API format (single text only)."""
        return {
            "model": self.model_name,
            "prompt": texts[0],  # Ollama only accepts one text at a time
        }

    def _get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Override to handle Ollama's one-at-a-time limitation."""
        embeddings = []

        for text in texts:
            try:
                response = self._session.post(
                    self.api_url,
                    headers=self._build_headers(),
                    json=self._build_body([text]),
                    timeout=self.request_timeout,
                )
                response.raise_for_status()

                # Parse response (returns list, we want first element)
                embedding = self._parse_response(response)[0]
                embeddings.append(embedding)

            except Exception as e:
                logger.error(f"Ollama embedding error: {e}")
                raise RuntimeError(f"Ollama embedding failed: {e}")

        # Validate embedding dimensions for consistency
        self._validate_embedding_dimensions(embeddings)

        logger.info(f"Got {len(embeddings)} embeddings from Ollama, dim: {len(embeddings[0]) if embeddings else 0}")
        return embeddings
