"""
Smart theme selection for agentic search responses.

Provides multiple strategies for introducing styling variations:
1. Smart selection based on query intent
2. User preference (via API parameter)
3. Time-based selection (day/night)
4. Random with weighted probabilities
5. Context-aware (data type, topic)
"""

import random
from datetime import datetime
from typing import Optional


def select_theme_by_intent(query_intent: str) -> str:
    """
    Select theme based on the query intent classification.

    Maps query types to appropriate visual themes:
    - ANALYTICAL/COMPARATIVE → professional (clean, data-focused)
    - INFORMATIONAL → minimal (clean, easy to read)
    - TEMPORAL/TRENDING → vibrant (energetic, modern)
    - EXPLORATORY → nature (organic, discovery)
    - SPECIFIC/TECHNICAL → dark (focused, developer-friendly)

    Args:
        query_intent: Intent classification from execution plan reasoning

    Returns:
        Theme name
    """
    intent_upper = query_intent.upper()

    # Analytical/Data-heavy queries → Professional
    if any(word in intent_upper for word in ['ANALYTICAL', 'COMPARATIVE', 'AGGREGATIVE', 'STATISTICAL']):
        return 'professional'

    # Simple informational → Minimal
    if 'INFORMATIONAL' in intent_upper:
        return 'minimal'

    # Time-sensitive/Trending → Vibrant
    if any(word in intent_upper for word in ['TEMPORAL', 'RECENT', 'TRENDING', 'LATEST', 'EXPLORATORY']):
        return 'vibrant'

    # Specific lookups → Dark (technical)
    if any(word in intent_upper for word in ['SPECIFIC', 'LOOKUP', 'ID', 'RID', 'DOCID']):
        return 'dark'

    # Multi-entity/Complex → Nature (organic)
    if 'MULTI-ENTITY' in intent_upper:
        return 'nature'

    # Default: random selection
    return random.choice(['professional', 'minimal', 'vibrant'])


def select_theme_by_time() -> str:
    """
    Select theme based on time of day.

    - Morning (6-12): vibrant (energetic start)
    - Afternoon (12-18): professional (work hours)
    - Evening (18-22): nature (calming)
    - Night (22-6): dark (easy on eyes)

    Returns:
        Theme name
    """
    hour = datetime.now().hour

    if 6 <= hour < 12:
        return 'vibrant'  # Morning energy
    elif 12 <= hour < 18:
        return 'professional'  # Work hours
    elif 18 <= hour < 22:
        return 'nature'  # Evening calm
    else:
        return 'dark'  # Night mode


def select_theme_weighted_random() -> str:
    """
    Random selection with weighted probabilities.

    Weights ensure variety while favoring readable themes:
    - professional: 35% (most versatile)
    - minimal: 25% (clean, simple)
    - vibrant: 20% (energetic)
    - nature: 15% (unique)
    - dark: 5% (specialty)

    Returns:
        Theme name
    """
    themes = ['professional', 'minimal', 'vibrant', 'nature', 'dark']
    weights = [0.35, 0.25, 0.20, 0.15, 0.05]

    return random.choices(themes, weights=weights, k=1)[0]


def select_theme_by_keywords(query: str) -> str:
    """
    Select theme based on query keywords.

    Detects topic/mood from query text:
    - Financial/Business → professional
    - Climate/Environment → nature
    - Tech/Development → dark
    - News/Events → vibrant
    - General → minimal

    Args:
        query: User query text

    Returns:
        Theme name
    """
    query_lower = query.lower()

    # Financial/Business keywords
    business_keywords = ['stock', 'finance', 'market', 'revenue', 'profit', 'business', 'economy', 'investment']
    if any(kw in query_lower for kw in business_keywords):
        return 'professional'

    # Climate/Environment keywords
    nature_keywords = ['climate', 'environment', 'green', 'nature', 'ecology', 'sustainability', 'renewable']
    if any(kw in query_lower for kw in nature_keywords):
        return 'nature'

    # Tech/Development keywords
    tech_keywords = ['code', 'api', 'developer', 'software', 'programming', 'bug', 'debug', 'technical']
    if any(kw in query_lower for kw in tech_keywords):
        return 'dark'

    # News/Events keywords
    news_keywords = ['news', 'event', 'happening', 'latest', 'recent', 'today', 'breaking']
    if any(kw in query_lower for kw in news_keywords):
        return 'vibrant'

    # Default: minimal (clean, neutral)
    return 'minimal'


def select_theme_smart(
    query: str,
    execution_plan_reasoning: Optional[str] = None,
    user_preference: Optional[str] = None,
    strategy: str = 'auto'
) -> str:
    """
    Smart theme selection with multiple strategies.

    Priority order:
    1. User preference (if provided)
    2. Strategy-based selection
    3. Fallback to weighted random

    Args:
        query: User query text
        execution_plan_reasoning: Reasoning from execution plan (contains intent)
        user_preference: User's theme preference (overrides all)
        strategy: Selection strategy
            - 'auto': Use intent if available, else keywords
            - 'intent': Based on query intent classification
            - 'time': Based on time of day
            - 'keywords': Based on query keywords
            - 'weighted': Weighted random selection
            - 'random': Pure random (all 5 themes equal)

    Returns:
        Theme name
    """
    # Priority 1: User preference overrides everything
    if user_preference:
        valid_themes = ['professional', 'minimal', 'dark', 'vibrant', 'nature']
        if user_preference in valid_themes:
            return user_preference

    # Priority 2: Strategy-based selection
    if strategy == 'intent' and execution_plan_reasoning:
        return select_theme_by_intent(execution_plan_reasoning)

    elif strategy == 'time':
        return select_theme_by_time()

    elif strategy == 'keywords':
        return select_theme_by_keywords(query)

    elif strategy == 'weighted':
        return select_theme_weighted_random()

    elif strategy == 'random':
        return random.choice(['professional', 'minimal', 'dark', 'vibrant', 'nature'])

    elif strategy == 'auto':
        # Try intent first, fall back to keywords
        if execution_plan_reasoning:
            return select_theme_by_intent(execution_plan_reasoning)
        else:
            return select_theme_by_keywords(query)

    # Fallback: weighted random
    return select_theme_weighted_random()


# Convenience functions for direct use
def get_theme_for_query(query: str, intent: Optional[str] = None) -> str:
    """Convenience wrapper for smart theme selection"""
    return select_theme_smart(query, execution_plan_reasoning=intent, strategy='auto')


def get_random_theme() -> str:
    """Get a random theme with weighted probabilities"""
    return select_theme_weighted_random()


# Example usage
if __name__ == "__main__":
    # Test different strategies
    test_query = "What are the latest climate change events?"

    print(f"Query: '{test_query}'")
    print(f"  Intent-based (TEMPORAL): {select_theme_by_intent('TEMPORAL')}")
    print(f"  Keyword-based: {select_theme_by_keywords(test_query)}")
    print(f"  Time-based: {select_theme_by_time()}")
    print(f"  Weighted random: {select_theme_weighted_random()}")
    print(f"  Smart auto: {select_theme_smart(test_query, strategy='auto')}")
