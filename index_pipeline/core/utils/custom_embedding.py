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


class GeminiEmbedding(BaseEmbedding):
    """Gemini-specific embedding using Google Generative AI SDK with local caching."""

    # Configuration
    api_key: str
    expected_dimension: Optional[int] = None
    cache_enabled: bool = True
    cache_max_size: int = 10000

    # Private
    _detected_dimension: Optional[int] = PrivateAttr(default=None)
    _cache: Dict[str, List[float]] = PrivateAttr(default_factory=dict)
    _cache_hits: int = PrivateAttr(default=0)
    _cache_misses: int = PrivateAttr(default=0)

    def __init__(
        self,
        api_key: str,
        model_name: str = "models/text-embedding-004",
        expected_dimension: Optional[int] = 768,
        cache_enabled: bool = True,
        cache_max_size: int = 10000,
        **kwargs
    ):
        """Initialize Gemini embedding client with local caching.

        Args:
            api_key: Gemini API key
            model_name: Embedding model name
            expected_dimension: Expected embedding dimension
            cache_enabled: Enable local embedding cache (default: True)
            cache_max_size: Maximum cache entries (default: 10000)
        """
        super().__init__(
            model_name=model_name,
            api_key=api_key,
            expected_dimension=expected_dimension,
            cache_enabled=cache_enabled,
            cache_max_size=cache_max_size,
            **kwargs
        )
        self._detected_dimension = None
        self._cache = {}
        self._cache_hits = 0
        self._cache_misses = 0

        # Configure Gemini API
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            logger.info(f"Gemini embedding initialized with model: {model_name}, cache: {'enabled' if cache_enabled else 'disabled'}")
        except ImportError as e:
            raise ImportError(f"google-generativeai package required. Install with: pip install google-generativeai. Error: {e}")
        except Exception as e:
            logger.warning(f"Gemini API configuration warning: {e}")

    @classmethod
    def class_name(cls) -> str:
        return "GeminiEmbedding"

    def _validate_embedding_dimensions(self, embeddings: List[List[float]]) -> None:
        """Validate embedding dimensions for consistency."""
        if not embeddings:
            return

        dimensions = [len(emb) for emb in embeddings]
        if len(set(dimensions)) > 1:
            raise ValueError(f"Inconsistent embedding dimensions: {set(dimensions)}")

        current_dim = dimensions[0]

        if self._detected_dimension is None:
            self._detected_dimension = current_dim
            logger.info(f"✓ Detected Gemini embedding dimension: {current_dim}")

            if self.expected_dimension is not None and current_dim != self.expected_dimension:
                raise ValueError(
                    f"❌ Gemini embedding dimension mismatch! "
                    f"Expected: {self.expected_dimension}, Got: {current_dim}"
                )
        elif current_dim != self._detected_dimension:
            raise ValueError(
                f"❌ Gemini embedding dimension changed! "
                f"Previously: {self._detected_dimension}, Now: {current_dim}"
            )

    def _get_cache_key(self, text: str) -> str:
        """Generate cache key from text using hash."""
        import hashlib
        return hashlib.md5(text.encode('utf-8')).hexdigest()

    def _get_embedding(self, text: str) -> List[float]:
        """Get embedding for a single text using Gemini with caching."""
        import google.generativeai as genai

        # Check cache first
        if self.cache_enabled:
            cache_key = self._get_cache_key(text)
            if cache_key in self._cache:
                self._cache_hits += 1
                if self._cache_hits % 100 == 0:
                    logger.info(f"Gemini cache stats: {self._cache_hits} hits, {self._cache_misses} misses, {len(self._cache)} cached")
                return self._cache[cache_key]
            self._cache_misses += 1

        try:
            response = genai.embed_content(
                model=self.model_name,
                content=text
            )
            embedding = response.get("embedding", [])

            if not embedding:
                raise ValueError("Gemini returned empty embedding")

            # Store in cache
            if self.cache_enabled:
                # Evict oldest entries if cache is full (simple FIFO)
                if len(self._cache) >= self.cache_max_size:
                    # Remove first 10% of entries
                    keys_to_remove = list(self._cache.keys())[:self.cache_max_size // 10]
                    for key in keys_to_remove:
                        del self._cache[key]
                    logger.info(f"Gemini cache evicted {len(keys_to_remove)} entries")

                self._cache[cache_key] = embedding

            return embedding

        except Exception as e:
            logger.error(f"Gemini embedding error: {e}")
            raise RuntimeError(f"Gemini embedding failed: {e}")

    def _get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings for multiple texts."""
        embeddings = []

        for text in texts:
            embedding = self._get_embedding(text)
            embeddings.append(embedding)

        # Validate dimensions
        self._validate_embedding_dimensions(embeddings)

        logger.info(f"Got {len(embeddings)} embeddings from Gemini, dim: {len(embeddings[0]) if embeddings else 0}")
        return embeddings

    def _get_query_embedding(self, query: str) -> List[float]:
        """Get embedding for query (required by LlamaIndex)."""
        embeddings = self._get_embeddings([query])
        return embeddings[0]

    def _get_text_embedding(self, text: str) -> List[float]:
        """Get embedding for text (required by LlamaIndex)."""
        embeddings = self._get_embeddings([text])
        return embeddings[0]

    def _get_text_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings for multiple texts (required by LlamaIndex)."""
        return self._get_embeddings(texts)

    async def _aget_query_embedding(self, query: str) -> List[float]:
        """Async query embedding (fallback to sync)."""
        return self._get_query_embedding(query)

    async def _aget_text_embedding(self, text: str) -> List[float]:
        """Async text embedding (fallback to sync)."""
        return self._get_text_embedding(text)

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_requests = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total_requests * 100) if total_requests > 0 else 0
        return {
            "enabled": self.cache_enabled,
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "cached_entries": len(self._cache),
            "max_size": self.cache_max_size,
            "hit_rate": f"{hit_rate:.1f}%"
        }

    def clear_cache(self):
        """Clear the embedding cache."""
        self._cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0
        logger.info("Gemini embedding cache cleared")
