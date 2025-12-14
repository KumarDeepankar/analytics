"""
LLM Client Selector - Choose between Ollama and Claude based on configuration
"""
import os
import logging
from typing import Optional
from .model_config import DEFAULT_PROVIDER, DEFAULT_MODELS, validate_provider_model

logger = logging.getLogger(__name__)


def create_llm_client(provider: Optional[str] = None, model: Optional[str] = None):
    """
    Create an LLM client with specific provider and model

    Args:
        provider: "ollama" or "anthropic" (default: from env or "ollama")
        model: Model name (default: provider-specific defaults)

    Returns:
        Client instance (OllamaClient or ClaudeClient)

    Example:
        # Use specific provider and model
        client = create_llm_client("anthropic", "claude-3-5-sonnet-20241022")

        # Use defaults from environment
        client = create_llm_client()

        # Then use it the same way regardless of provider
        result = await client.generate_structured_response(...)
    """
    # Determine provider (priority: parameter > env > default)
    if provider is None:
        provider = os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER).lower()
    else:
        provider = provider.lower()

    # Normalize provider name
    if provider == "claude":
        provider = "anthropic"

    # Determine model (priority: parameter > env > default)
    if model is None:
        model = os.getenv("LLM_MODEL", DEFAULT_MODELS.get(provider, ""))

    # Validate provider and model combination
    if not validate_provider_model(provider, model):
        logger.warning(f"Invalid provider/model combination: {provider}/{model}, using defaults")
        provider = DEFAULT_PROVIDER
        model = DEFAULT_MODELS[provider]

    # Create appropriate client
    if provider == "anthropic":
        logger.info(f"Creating Anthropic Claude client with model: {model}")
        from .claude_client import ClaudeClient
        return ClaudeClient(model=model)

    else:  # Default to Ollama
        logger.info(f"Creating Ollama client with model: {model}")
        from .ollama_client import OllamaClient
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        return OllamaClient(model=model, base_url=base_url)


def get_llm_client():
    """
    Get the appropriate LLM client based on environment variables (backward compatibility)

    Environment Variables:
        LLM_PROVIDER: "ollama" or "anthropic" (default: "ollama")
        LLM_MODEL: Model name (provider-specific defaults)
        ANTHROPIC_API_KEY: Required for Claude
        OLLAMA_BASE_URL: Ollama URL (default: http://localhost:11434)

    Returns:
        Client instance (OllamaClient or ClaudeClient)
    """
    return create_llm_client()


# Create singleton instance based on environment (for backward compatibility)
llm_client = get_llm_client()

# Backward compatibility: keep ollama_client name
ollama_client = llm_client
