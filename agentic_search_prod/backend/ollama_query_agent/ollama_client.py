"""
Ollama Client with structured output support
"""
import asyncio
import json
import logging
from typing import Dict, Any, List, Optional, AsyncGenerator, Type, TypeVar
import httpx
from pydantic import BaseModel
from .error_handler import format_error_for_display

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)


class OllamaClient:
    """Client for communicating with Ollama API"""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.1:8b"):
        self.base_url = base_url
        self.model = model

        # HTTP client optimization (Priority 4)
        limits = httpx.Limits(
            max_connections=50,
            max_keepalive_connections=10,
            keepalive_expiry=60.0
        )

        timeout = httpx.Timeout(
            connect=5.0,    # 5s to connect to local Ollama
            read=120.0,     # 120s for LLM response generation
            write=5.0,      # 5s to send request
            pool=2.0        # 2s to acquire connection
        )

        self.client = httpx.AsyncClient(
            timeout=timeout,
            limits=limits,
            http2=False  # Ollama doesn't support HTTP/2
        )

        logger.info(f"Initialized Ollama client: {self.model} at {self.base_url}")

    async def generate_response(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate a complete response from Ollama"""
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "top_p": 0.9
                }
            }

            if system_prompt:
                payload["system"] = system_prompt

            logger.info(f"Sending request to Ollama at {self.base_url}")
            response = await self.client.post(f"{self.base_url}/api/generate", json=payload)
            response.raise_for_status()

            result = response.json()
            response_text = result.get("response", "")

            if not response_text:
                logger.warning("Ollama returned empty response")
                return "Error: Empty response from Ollama"

            return response_text

        except httpx.ConnectError as e:
            logger.error(f"Connection error to Ollama: {e}")
            return f"Error: {format_error_for_display('connection error')}"
        except httpx.TimeoutException as e:
            logger.error(f"Timeout error from Ollama: {e}")
            return f"Error: {format_error_for_display('timeout')}"
        except Exception as e:
            logger.error(f"Error generating response from Ollama: {e}")
            return f"Error: {format_error_for_display(str(e))}"

    async def generate_structured_response(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None
    ) -> T:
        """
        Generate a structured response conforming to a Pydantic model using Ollama's JSON mode

        Args:
            prompt: User prompt
            response_model: Pydantic model class defining the structure
            system_prompt: Optional system prompt

        Returns:
            Instance of response_model

        Example:
            class Plan(BaseModel):
                reasoning: str
                tasks: List[Task]

            result = await client.generate_structured_response(
                prompt="Create a plan",
                response_model=Plan
            )
        """
        # Build simpler schema description (not the full JSON schema)
        schema = response_model.model_json_schema()

        # Extract field descriptions
        field_descriptions = []
        properties = schema.get("properties", {})
        required_fields = schema.get("required", [])

        for field_name, field_info in properties.items():
            field_type = field_info.get("type", "any")
            field_desc = field_info.get("description", "")
            is_required = "required" if field_name in required_fields else "optional"

            if field_desc:
                field_descriptions.append(f"  - {field_name} ({field_type}, {is_required}): {field_desc}")
            else:
                field_descriptions.append(f"  - {field_name} ({field_type}, {is_required})")

        schema_description = "\n".join(field_descriptions)

        # Enhance prompt with simplified schema
        enhanced_prompt = f"""{prompt}

CRITICAL INSTRUCTIONS:
1. You must respond with valid JSON data matching these fields:
{schema_description}

2. DO NOT return the schema definition itself (no "$defs", no "properties", no "type": "object")
3. DO NOT return the example structure - fill it with actual content
4. Your response must start with {{ and contain actual data values

Example of CORRECT response format:
{json.dumps({k: f"your {k} here" for k in properties.keys()}, indent=2)}

Generate the actual JSON data now (not the schema):"""

        payload = {
            "model": self.model,
            "prompt": enhanced_prompt,
            "stream": False,
            "format": "json",  # Enable JSON mode
            "options": {
                "temperature": 0.1,
                "top_p": 0.9
            }
        }

        if system_prompt:
            payload["system"] = system_prompt

        logger.info(f"Sending structured request to Ollama ({self.model})")

        try:
            response = await self.client.post(
                f"{self.base_url}/api/generate",
                json=payload
            )
            response.raise_for_status()

            result = response.json()
            response_text = result.get("response", "")

            if not response_text:
                raise ValueError("Ollama returned empty response")

            # Debug: log what Ollama returned
            logger.info(f"[DEBUG] Ollama response (first 500 chars): {response_text[:500]}")

            # Parse JSON response into Pydantic model
            json_data = json.loads(response_text)

            # Check if Ollama returned the schema itself (common mistake)
            if "$defs" in json_data or "properties" in json_data:
                logger.error(f"⚠️ Ollama returned the schema instead of data!")
                logger.error(f"Full response: {response_text}")
                raise ValueError("Ollama returned JSON schema instead of actual data. Try using a more capable model like llama3.1 or llama3.2:3b+")

            validated_model = response_model.model_validate(json_data)

            logger.info(f"✓ Structured output validated successfully")
            return validated_model

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from Ollama: {e}")
            logger.error(f"Response: {response_text[:500]}")
            raise ValueError(f"Invalid JSON from Ollama: {e}")
        except Exception as e:
            logger.error(f"Error in structured response: {e}")
            raise

    async def generate_streaming_response(self, prompt: str, system_prompt: Optional[str] = None) -> AsyncGenerator[str, None]:
        """Generate a streaming response from Ollama"""
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": True
            }

            if system_prompt:
                payload["system"] = system_prompt

            async with self.client.stream("POST", f"{self.base_url}/api/generate", json=payload) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if line.strip():
                        try:
                            data = json.loads(line)
                            if "response" in data:
                                yield data["response"]
                            if data.get("done", False):
                                break
                        except json.JSONDecodeError:
                            continue

        except Exception as e:
            logger.error(f"Error streaming response from Ollama: {e}")
            yield f"Error: {format_error_for_display(str(e))}"

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()


# Create a singleton instance
ollama_client = OllamaClient()
