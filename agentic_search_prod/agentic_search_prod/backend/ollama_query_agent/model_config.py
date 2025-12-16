"""
Model Configuration - Available LLM providers and models

This file defines all available LLM providers and their supported models.
Add new models here to make them available in the UI.
"""

from typing import Dict, List

# Available models for each provider
AVAILABLE_MODELS: Dict[str, List[Dict[str, str]]] = {
    "anthropic": [
        {
            "id": "claude-3-5-sonnet-20241022",
            "name": "Claude 3.5 Sonnet",
            "description": "Most capable model - excellent for complex reasoning and analysis"
        },
        {
            "id": "claude-3-5-haiku-20241022",
            "name": "Claude 3.5 Haiku",
            "description": "Fast and efficient - good for quick searches and simple queries"
        },
        {
            "id": "claude-3-opus-20240229",
            "name": "Claude 3 Opus",
            "description": "Previous generation flagship - very capable but slower"
        },
    ],
    "ollama": [
        {
            "id": "llama3.2:latest",
            "name": "Llama 3.2 (Latest)",
            "description": "Meta's latest model - good general performance"
        },
        {
            "id": "llama3.1:8b",
            "name": "Llama 3.1",
            "description": "Meta's previous version - stable and reliable"
        },
        {
            "id": "qwen2.5:latest",
            "name": "Qwen 2.5",
            "description": "Alibaba's model - strong multilingual support"
        },
        {
            "id": "mistral:latest",
            "name": "Mistral (Latest)",
            "description": "Mistral AI's model - efficient and fast"
        },
        {
            "id": "gemma2:latest",
            "name": "Gemma 2",
            "description": "Google's open model - good for general tasks"
        },
    ]
}

# Provider display names
PROVIDER_NAMES: Dict[str, str] = {
    "anthropic": "Anthropic (Claude)",
    "ollama": "Ollama (Local)"
}

# Default selections
DEFAULT_PROVIDER = "ollama"
DEFAULT_MODELS: Dict[str, str] = {
    "anthropic": "claude-3-5-sonnet-20241022",
    "ollama": "llama3.2:latest"
}


def get_available_providers() -> List[Dict[str, str]]:
    """Get list of available providers with display names"""
    return [
        {"id": provider_id, "name": PROVIDER_NAMES.get(provider_id, provider_id)}
        for provider_id in AVAILABLE_MODELS.keys()
    ]


def get_models_for_provider(provider: str) -> List[Dict[str, str]]:
    """Get available models for a specific provider"""
    return AVAILABLE_MODELS.get(provider, [])


def get_default_model(provider: str) -> str:
    """Get default model for a provider"""
    return DEFAULT_MODELS.get(provider, "")


def validate_provider_model(provider: str, model: str) -> bool:
    """Validate that a provider and model combination is valid"""
    if provider not in AVAILABLE_MODELS:
        return False

    model_ids = [m["id"] for m in AVAILABLE_MODELS[provider]]
    return model in model_ids
