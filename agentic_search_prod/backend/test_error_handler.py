"""
Test script to verify error handler produces user-friendly messages.
Run: python test_error_handler.py
"""
from ollama_query_agent.error_handler import format_error_for_display, categorize_error, ErrorCategory

# Test cases simulating real errors
test_errors = [
    # Token limit errors
    ("Claude API error - 400: prompt is too long", ErrorCategory.TOKEN_LIMIT),
    ("HTTP 400: maximum context length exceeded", ErrorCategory.TOKEN_LIMIT),
    ("Error: token limit exceeded", ErrorCategory.TOKEN_LIMIT),
    ("request too large for model", ErrorCategory.TOKEN_LIMIT),

    # Rate limit errors
    ("HTTP 429: rate limit exceeded", ErrorCategory.RATE_LIMIT),
    ("too many requests", ErrorCategory.RATE_LIMIT),
    ("quota exceeded", ErrorCategory.RATE_LIMIT),

    # Connection errors
    ("connection error to Claude", ErrorCategory.CONNECTION),
    ("Cannot connect to API", ErrorCategory.CONNECTION),
    ("network unreachable", ErrorCategory.CONNECTION),

    # Timeout errors
    ("request timed out", ErrorCategory.TIMEOUT),
    ("timeout error", ErrorCategory.TIMEOUT),

    # Auth errors
    ("HTTP 401: unauthorized", ErrorCategory.AUTHENTICATION),
    ("HTTP 403: forbidden", ErrorCategory.AUTHENTICATION),
    ("invalid api key", ErrorCategory.AUTHENTICATION),

    # Server errors
    ("HTTP 500: internal server error", ErrorCategory.SERVER_ERROR),
    ("HTTP 502: bad gateway", ErrorCategory.SERVER_ERROR),
    ("HTTP 503: service unavailable", ErrorCategory.SERVER_ERROR),

    # Unknown errors
    ("some random error", ErrorCategory.UNKNOWN),
    ("Claude API error - 500", ErrorCategory.SERVER_ERROR),
]

print("=" * 80)
print("ERROR HANDLER TEST")
print("=" * 80)

passed = 0
failed = 0

for error_msg, expected_category in test_errors:
    actual_category = categorize_error(error_msg)
    user_friendly = format_error_for_display(error_msg)

    status = "✅ PASS" if actual_category == expected_category else "❌ FAIL"
    if actual_category == expected_category:
        passed += 1
    else:
        failed += 1

    print(f"\n{status}")
    print(f"  Input:    {error_msg}")
    print(f"  Expected: {expected_category.value}")
    print(f"  Actual:   {actual_category.value}")
    print(f"  Message:  {user_friendly[:80]}...")

print("\n" + "=" * 80)
print(f"RESULTS: {passed} passed, {failed} failed")
print("=" * 80)
