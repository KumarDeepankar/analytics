"""
Prompts for the Decomposer Sub-Agent
"""

DECOMPOSER_SYSTEM_PROMPT = """You break down user queries into simple sub-questions. Always return valid JSON."""


def create_decomposer_prompt(
    query: str,
    context: str = "",
    max_questions: int = 5
) -> str:
    """Create the prompt for query decomposition"""

    return f"""Break down this query into 3-5 simple sub-questions.

QUERY: {query}

Return JSON with this exact format:
{{
  "sub_questions": [
    {{"id": "sq_1", "question": "What is the total count?", "priority": 5, "depends_on": []}},
    {{"id": "sq_2", "question": "What is the distribution?", "priority": 4, "depends_on": []}},
    {{"id": "sq_3", "question": "What are the top items?", "priority": 3, "depends_on": []}}
  ],
  "reasoning": "Breaking down the query into countable parts"
}}

EXAMPLE for "Events by country":
{{
  "sub_questions": [
    {{"id": "sq_1", "question": "Which countries have the most events?", "priority": 5, "depends_on": []}},
    {{"id": "sq_2", "question": "What is the event count per country?", "priority": 4, "depends_on": []}},
    {{"id": "sq_3", "question": "What types of events occur in top countries?", "priority": 3, "depends_on": ["sq_1"]}}
  ],
  "reasoning": "Analyzing events distribution across countries"
}}

Now generate sub_questions for: {query}"""
