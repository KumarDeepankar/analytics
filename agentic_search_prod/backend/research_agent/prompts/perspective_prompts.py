"""
Prompts for the Perspective Sub-Agent
"""

PERSPECTIVE_SYSTEM_PROMPT = """You are a research methodology expert specializing in multi-perspective analysis.

Your goal is to generate diverse research perspectives that ensure comprehensive topic coverage and avoid blind spots.

Guidelines:
1. Create distinct personas that would approach the topic differently
2. Each perspective should have unique focus areas
3. Consider stakeholder perspectives (user, business, technical, etc.)
4. Include contrarian or skeptical perspectives when appropriate
5. Perspectives should be complementary, not overlapping
"""


def create_perspective_prompt(
    topic: str,
    domain: str = "",
    num_perspectives: int = 3,
    existing_perspectives: list = None
) -> str:
    """Create the prompt for perspective generation"""
    domain_section = f"\nDOMAIN CONTEXT: {domain}" if domain else ""

    existing_section = ""
    if existing_perspectives:
        existing_section = f"\nALREADY COVERED PERSPECTIVES (avoid these):\n" + \
            "\n".join(f"- {p}" for p in existing_perspectives)

    return f"""Generate {num_perspectives} diverse research perspectives for this topic.

TOPIC: {topic}
{domain_section}
{existing_section}

For each perspective, provide:
- name: A descriptive name (e.g., "Business Analyst", "End User Advocate")
- focus: What this perspective focuses on
- questions: 2-3 questions this perspective would ask
- keywords: Search terms this perspective would use

The perspectives should be:
1. Distinct and non-overlapping
2. Complementary in coverage
3. Relevant to the topic and domain
4. Practical for research purposes

Return a JSON object with:
{{
  "perspectives": [
    {{
      "name": "Perspective Name",
      "focus": "What this perspective emphasizes",
      "questions": ["Question 1", "Question 2"],
      "keywords": ["keyword1", "keyword2"]
    }}
  ],
  "reasoning": "Why these perspectives were chosen"
}}"""
