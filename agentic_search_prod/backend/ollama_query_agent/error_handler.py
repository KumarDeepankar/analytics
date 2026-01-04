"""
User-friendly error handler for LLM and API errors.

This module categorizes errors and provides actionable, user-friendly messages
instead of exposing raw error details to end users.
"""
import re
import logging
from typing import Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """Categories of errors for user-friendly handling"""
    TOKEN_LIMIT = "token_limit"
    RATE_LIMIT = "rate_limit"
    CONNECTION = "connection"
    TIMEOUT = "timeout"
    AUTHENTICATION = "authentication"
    SERVER_ERROR = "server_error"
    UNKNOWN = "unknown"


# Error patterns to match against error messages
ERROR_PATTERNS = {
    ErrorCategory.TOKEN_LIMIT: [
        r"token[s]?\s*(limit|exceeded|too\s*long)",
        r"maximum\s*context\s*length",
        r"input\s*too\s*long",
        r"prompt\s*is\s*too\s*long",
        r"request\s*too\s*large",
        r"max_tokens",
        r"context_length_exceeded",
        r"prompt.*exceed",
        r"string too long",
        r"content too large",
    ],
    ErrorCategory.RATE_LIMIT: [
        r"rate\s*limit",
        r"too\s*many\s*requests",
        r"429",
        r"quota\s*exceeded",
        r"capacity",
        r"overloaded",
        r"throttl",
    ],
    ErrorCategory.CONNECTION: [
        r"connect(ion)?\s*(error|failed|refused)",
        r"network\s*(error|unreachable)",
        r"dns\s*(error|failed)",
        r"cannot\s*connect",
        r"connection\s*reset",
        r"no\s*route\s*to\s*host",
        r"econnrefused",
        r"enotfound",
    ],
    ErrorCategory.TIMEOUT: [
        r"timeout",
        r"timed?\s*out",
        r"deadline\s*exceeded",
        r"request\s*took\s*too\s*long",
    ],
    ErrorCategory.AUTHENTICATION: [
        r"401",
        r"403",
        r"unauthorized",
        r"forbidden",
        r"invalid\s*api\s*key",
        r"authentication\s*(failed|error|required)",
        r"invalid\s*credentials",
    ],
    ErrorCategory.SERVER_ERROR: [
        r"500",
        r"502",
        r"503",
        r"504",
        r"internal\s*server\s*error",
        r"bad\s*gateway",
        r"service\s*unavailable",
        r"gateway\s*timeout",
    ],
}

# User-friendly messages for each error category
USER_FRIENDLY_MESSAGES = {
    ErrorCategory.TOKEN_LIMIT: (
        "Your query requires analyzing too much data. "
        "Please try narrowing your search by:\n"
        "- Using a shorter time range (e.g., last 3 months instead of 1 year)\n"
        "- Being more specific in your query\n"
        "- Breaking your question into smaller parts"
    ),
    ErrorCategory.RATE_LIMIT: (
        "The service is currently experiencing high demand. "
        "Please wait a moment and try again. If the issue persists, "
        "try again in a few minutes."
    ),
    ErrorCategory.CONNECTION: (
        "Unable to connect to the AI service. "
        "This may be a temporary network issue. Please try again, "
        "or raise a support ticket if the problem continues."
    ),
    ErrorCategory.TIMEOUT: (
        "Your request took too long to process. "
        "Please try simplifying your query or using a shorter time range. "
        "If the issue persists, please raise a support ticket."
    ),
    ErrorCategory.AUTHENTICATION: (
        "There was an authentication issue with the AI service. "
        "Please raise a support ticket so we can investigate."
    ),
    ErrorCategory.SERVER_ERROR: (
        "The AI service is temporarily unavailable. "
        "Please try again in a few minutes. If the issue persists, "
        "please raise a support ticket."
    ),
    ErrorCategory.UNKNOWN: (
        "An unexpected error occurred while processing your request. "
        "Please try again, or raise a support ticket if the problem continues."
    ),
}


def categorize_error(error_message: str) -> ErrorCategory:
    """
    Categorize an error message into a known error category.

    Args:
        error_message: The raw error message from LLM or API

    Returns:
        ErrorCategory enum value
    """
    if not error_message:
        return ErrorCategory.UNKNOWN

    error_lower = error_message.lower()

    for category, patterns in ERROR_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, error_lower, re.IGNORECASE):
                logger.info(f"Error categorized as {category.value}: matched pattern '{pattern}'")
                return category

    return ErrorCategory.UNKNOWN


def get_user_friendly_error(error_message: str) -> Tuple[str, ErrorCategory]:
    """
    Convert a raw error message to a user-friendly message.

    Args:
        error_message: The raw error message from LLM or API

    Returns:
        Tuple of (user-friendly message, error category)
    """
    category = categorize_error(error_message)
    user_message = USER_FRIENDLY_MESSAGES[category]

    # Log the original error for debugging
    logger.error(f"Original error: {error_message}")
    logger.info(f"Returning user-friendly message for category: {category.value}")

    return user_message, category


def format_error_for_display(error_message: str, include_category: bool = False) -> str:
    """
    Format an error message for display to the user.

    Args:
        error_message: The raw error message
        include_category: Whether to include the error category in the response

    Returns:
        Formatted user-friendly error message
    """
    user_message, category = get_user_friendly_error(error_message)

    if include_category:
        return f"[{category.value}] {user_message}"

    return user_message


def is_token_limit_error(error_message: str) -> bool:
    """
    Check if an error is due to token/context limit exceeded.

    Used to trigger retry with reduced sample parameters.

    Args:
        error_message: The raw error message

    Returns:
        True if error is a token limit error
    """
    return categorize_error(error_message) == ErrorCategory.TOKEN_LIMIT
