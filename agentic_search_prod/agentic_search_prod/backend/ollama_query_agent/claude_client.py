"""
Anthropic Claude Client with structured output support via Tool Use API

PROMPT CACHING SUPPORT:
This client implements Anthropic's Prompt Caching feature for cost and latency optimization.

How it works:
- Static content (tool lists, instructions, schemas) is marked with cache_control: {"type": "ephemeral"}
- Cached content is stored for 5 minutes and reused across requests
- Cache hits reduce cost by 10× ($3.75/M → $0.375/M for input tokens)
- Cache hits reduce latency by ~2-3 seconds (skips KV computation for cached tokens)

Benefits for agentic search:
- Tool list (3,900 tokens): Cached across all queries
- Decision rules (280 tokens): Cached across all queries
- Schema definitions (220 tokens): Cached across all queries
- Total: ~4,400 tokens cached = $0.0165 → $0.00165 per request (90% savings!)

Cache invalidation:
- Automatic after 5 minutes
- Automatic if cached content changes (content-based cache key)
- Perfect for conversational agents with stable context

Anthropic API docs: https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
"""
import json
import logging
import os
from typing import Type, TypeVar, Optional
import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)


class ClaudeClient:
    """Client for communicating with Anthropic Claude API"""

    def __init__(
        self,
        model: str = "claude-3-5-sonnet-20241022",
        api_key: Optional[str] = None,
        base_url: str = "https://api.anthropic.com"
    ):
        self.model = model
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.base_url = base_url

        # HTTP client optimization (Priority 4)
        limits = httpx.Limits(
            max_connections=50,
            max_keepalive_connections=10,
            keepalive_expiry=60.0
        )

        timeout = httpx.Timeout(
            connect=10.0,   # 10s to connect to Anthropic
            read=120.0,     # 120s for LLM response generation
            write=10.0,     # 10s to send request
            pool=5.0        # 5s to acquire connection
        )

        # Try to enable HTTP/2 if available, fallback to HTTP/1.1
        try:
            self.client = httpx.AsyncClient(
                timeout=timeout,
                limits=limits,
                http2=True
            )
            logger.info("HTTP/2 enabled for Claude client")
        except ImportError:
            logger.warning("HTTP/2 not available (h2 package not installed), using HTTP/1.1")
            self.client = httpx.AsyncClient(
                timeout=timeout,
                limits=limits,
                http2=False
            )

        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable or api_key parameter is required")

        logger.info(f"Initialized Claude client: {self.model}")

    async def generate_response(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        cacheable_prefix: Optional[str] = None
    ) -> str:
        """
        Generate a complete response from Claude with optional prompt caching

        Args:
            prompt: User prompt (dynamic content)
            system_prompt: Optional system prompt
            cacheable_prefix: Optional static content to cache (e.g., tool list, instructions)
                            This content will be cached for 5 minutes, reducing cost by 10×

        Returns:
            Generated text response

        Example:
            # Without caching:
            response = await client.generate_response("What is the weather?")

            # With caching (for repeated queries with same context):
            response = await client.generate_response(
                prompt="What is the weather?",
                cacheable_prefix="<tools>...50 tool descriptions...</tools>"
            )
        """
        try:
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }

            # Build message content with caching support
            if cacheable_prefix:
                # Multi-block message: cacheable content + dynamic content
                message_content = [
                    {
                        "type": "text",
                        "text": cacheable_prefix,
                        "cache_control": {"type": "ephemeral"}  # Cache for 5 minutes
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            else:
                # Simple string message (no caching)
                message_content = prompt

            payload = {
                "model": self.model,
                "max_tokens": 4096,
                "temperature": 0.1,
                "messages": [{"role": "user", "content": message_content}]
            }

            if system_prompt:
                payload["system"] = system_prompt

            logger.info(f"Sending request to Claude ({self.model})")
            response = await self.client.post(
                f"{self.base_url}/v1/messages",
                headers=headers,
                json=payload
            )
            response.raise_for_status()

            result = response.json()

            # Log cache performance metrics if available
            if "usage" in result:
                usage = result["usage"]
                cache_creation = usage.get("cache_creation_input_tokens", 0)
                cache_read = usage.get("cache_read_input_tokens", 0)

                if cache_creation > 0:
                    logger.info(f"💾 Cache CREATION: {cache_creation} tokens cached")
                if cache_read > 0:
                    logger.info(f"⚡ Cache HIT: {cache_read} tokens loaded from cache (10× cheaper!)")

                # Calculate savings
                if cache_read > 0:
                    regular_cost = cache_read * 3.75 / 1_000_000  # $3.75/M for input
                    cached_cost = cache_read * 0.375 / 1_000_000  # $0.375/M for cached
                    savings = regular_cost - cached_cost
                    logger.info(f"💰 Cost savings: ${savings:.4f} (${regular_cost:.4f} → ${cached_cost:.4f})")

            # Handle gateway's wrapped response format - direct extraction
            if "result" in result and isinstance(result["result"], list) and len(result["result"]) > 0:
                # Gateway wraps response in {"status": "success", "result": [...]}
                logger.info("Detected gateway wrapped response format")
                content_blocks = result["result"]
                if len(content_blocks) == 1 and content_blocks[0].get("type") == "text":
                    logger.info("✓ Using direct extraction for single text block")
                    return content_blocks[0].get("text", "")

            if "content" in result:
                # Standard Anthropic format
                content_blocks = result.get("content", [])
                if len(content_blocks) == 1 and content_blocks[0].get("type") == "text":
                    logger.info("✓ Using direct extraction for single text block")
                    return content_blocks[0].get("text", "")

            # Should not reach here for typical responses
            logger.warning(f"Unexpected response format. Keys: {result.keys()}")
            response_text = ""

            if not response_text:
                logger.warning("Claude returned empty response")
                return "Error: Empty response from Claude"

            return response_text

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error from Claude: {e.response.status_code} - {e.response.text}")
            return f"Error: Claude API error - {e.response.status_code}"
        except httpx.ConnectError as e:
            logger.error(f"Connection error to Claude: {e}")
            return "Error: Cannot connect to Claude API. Please check your internet connection"
        except httpx.TimeoutException as e:
            logger.error(f"Timeout error from Claude: {e}")
            return "Error: Claude request timed out"
        except Exception as e:
            logger.error(f"Error generating response from Claude: {e}")
            return f"Error: Unable to generate response - {str(e)}"

    async def generate_structured_response(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        cacheable_prefix: Optional[str] = None
    ) -> T:
        """
        Generate a structured response using Claude's Tool Use API with optional prompt caching

        This uses Claude's native tool calling feature to guarantee structured output.
        Claude is forced to call a tool with arguments matching your Pydantic model.

        Args:
            prompt: User prompt (dynamic content)
            response_model: Pydantic model class defining the structure
            system_prompt: Optional system prompt
            cacheable_prefix: Optional static content to cache (e.g., tool list, instructions)
                            This content will be cached for 5 minutes, reducing cost by 10×

        Returns:
            Instance of response_model

        Example:
            class Plan(BaseModel):
                reasoning: str
                tasks: List[Task]

            # Without caching:
            result = await client.generate_structured_response(
                prompt="Create a plan",
                response_model=Plan
            )

            # With caching (for repeated queries with same static context):
            result = await client.generate_structured_response(
                prompt="<query>Create a plan</query>",
                response_model=Plan,
                cacheable_prefix="<tools>...50 tool descriptions...</tools><decision>...</decision>"
            )
        """
        # Convert Pydantic model to tool schema
        tool_name = f"provide_{response_model.__name__.lower()}"
        tool_schema = {
            "name": tool_name,
            "description": f"Provide structured output as {response_model.__name__}",
            "input_schema": response_model.model_json_schema()
        }

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        # Build message content with caching support
        if cacheable_prefix:
            # Multi-block message: cacheable content + dynamic content
            message_content = [
                {
                    "type": "text",
                    "text": cacheable_prefix,
                    "cache_control": {"type": "ephemeral"}  # Cache for 5 minutes
                },
                {
                    "type": "text",
                    "text": prompt
                }
            ]
        else:
            # Simple string message (no caching)
            message_content = prompt

        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "temperature": 0.1,
            "tools": [tool_schema],
            "tool_choice": {"type": "tool", "name": tool_name},  # Force tool use
            "messages": [{"role": "user", "content": message_content}]
        }

        if system_prompt:
            payload["system"] = system_prompt

        logger.info(f"Sending structured request to Claude ({self.model})")

        try:
            response = await self.client.post(
                f"{self.base_url}/v1/messages",
                headers=headers,
                json=payload
            )
            response.raise_for_status()

            result = response.json()

            # Log cache performance metrics if available
            if "usage" in result:
                usage = result["usage"]
                cache_creation = usage.get("cache_creation_input_tokens", 0)
                cache_read = usage.get("cache_read_input_tokens", 0)

                if cache_creation > 0:
                    logger.info(f"💾 Cache CREATION: {cache_creation} tokens cached")
                if cache_read > 0:
                    logger.info(f"⚡ Cache HIT: {cache_read} tokens loaded from cache (10× cheaper!)")

                # Calculate savings
                if cache_read > 0:
                    regular_cost = cache_read * 3.75 / 1_000_000  # $3.75/M for input
                    cached_cost = cache_read * 0.375 / 1_000_000  # $0.375/M for cached
                    savings = regular_cost - cached_cost
                    logger.info(f"💰 Cost savings: ${savings:.4f} (${regular_cost:.4f} → ${cached_cost:.4f})")

            # Handle gateway's wrapped response format
            content_blocks = []
            if "result" in result and isinstance(result["result"], list) and len(result["result"]) > 0:
                # Gateway wraps response in {"status": "success", "result": [...]}
                logger.info("Detected gateway wrapped response format")
                actual_response = result["result"][0]
                content_blocks = actual_response.get("content", [])
            elif "content" in result:
                # Standard Anthropic format
                content_blocks = result.get("content", [])
            else:
                logger.error(f"Unexpected response format. Keys: {result.keys()}")
                logger.error(f"Full response: {json.dumps(result, indent=2)}")

            # Extract tool use from response
            for content_block in content_blocks:
                if content_block.get("type") == "tool_use":
                    tool_input = content_block.get("input", {})

                    logger.info(f"Tool input keys: {list(tool_input.keys())}")

                    # Handle nested structure where input is wrapped in an extra key
                    # Example: {"symbol": {actual_data}} -> {actual_data}
                    if len(tool_input) == 1:
                        single_key = list(tool_input.keys())[0]
                        single_value = tool_input[single_key]
                        if isinstance(single_value, dict):
                            logger.info(f"Unwrapping extra key: '{single_key}'")
                            tool_input = single_value

                    # Validate and parse into Pydantic model
                    validated_model = response_model.model_validate(tool_input)

                    logger.info(f"✓ Structured output validated successfully")
                    return validated_model

            raise ValueError("Claude did not return tool use content")

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error from Claude: {e.response.status_code}")
            logger.error(f"Response: {e.response.text}")
            raise ValueError(f"Claude API error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Error in structured response: {e}")
            raise

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()


# Create a singleton instance (only if ANTHROPIC_API_KEY is set)
claude_client = None
if os.getenv("ANTHROPIC_API_KEY"):
    try:
        claude_client = ClaudeClient()
    except Exception as e:
        logger.warning(f"Could not initialize Claude client: {e}")
