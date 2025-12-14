"""
Custom Knowledge Graph Extraction Prompts

This file contains customizable prompts for extracting nodes and relationships
from text documents. You can modify these prompts to improve extraction quality
for your specific domain.
"""

# Default LlamaIndex-style prompt
DEFAULT_KG_TRIPLET_EXTRACT_TMPL = (
    "Some text is provided below. Given the text, extract up to "
    "{max_knowledge_triplets} "
    "knowledge triplets in the form of (subject, predicate, object). Avoid stopwords.\n"
    "---------------------\n"
    "Example:\n"
    "Text: Alice is Bob's mother.\n"
    "Triplets:\n(Alice, is mother of, Bob)\n"
    "Text: Philz is a coffee shop founded in Berkeley in 1982.\n"
    "Triplets:\n"
    "(Philz, is, coffee shop)\n"
    "(Philz, founded in, Berkeley)\n"
    "(Philz, founded in, 1982)\n"
    "---------------------\n"
    "Text: {text}\n"
    "Triplets:\n"
)

# Enhanced prompt with more detailed instructions
ENHANCED_KG_TRIPLET_EXTRACT_TMPL = (
    "Some text is provided below. Given the text, extract up to "
    "{max_knowledge_triplets} "
    "knowledge triplets in the form of (subject, predicate, object). "
    "Focus on meaningful relationships and use descriptive predicates. Avoid stopwords.\n"
    "---------------------\n"
    "Example:\n"
    "Text: Dr. Sarah Chen, a researcher at MIT, published a paper on quantum computing in 2023.\n"
    "Triplets:\n"
    "(Dr. Sarah Chen, works at, MIT)\n"
    "(Dr. Sarah Chen, is, researcher)\n"
    "(Dr. Sarah Chen, published, paper on quantum computing)\n"
    "(paper on quantum computing, published in year, 2023)\n"
    "(paper on quantum computing, topic is, quantum computing)\n"
    "Text: The Apollo 11 mission landed on the Moon on July 20, 1969.\n"
    "Triplets:\n"
    "(Apollo 11, is, space mission)\n"
    "(Apollo 11, landed on, Moon)\n"
    "(Apollo 11, landing date, July 20, 1969)\n"
    "---------------------\n"
    "Text: {text}\n"
    "Triplets:\n"
)

# Domain-specific prompt for business/organizational data
BUSINESS_KG_TRIPLET_EXTRACT_TMPL = (
    "Extract up to {max_knowledge_triplets} business-related knowledge triplets.\n\n"
    "FOCUS ON:\n"
    "- People and their roles/positions\n"
    "- Organizations and their relationships\n"
    "- Products, services, and offerings\n"
    "- Events, meetings, and transactions\n"
    "- Locations and facilities\n"
    "- Dates and timelines\n"
    "\n"
    "FORMAT: (subject, predicate, object)\n"
    "---------------------\n"
    "EXAMPLE:\n"
    "Text: John Smith joined Acme Corp as CTO in January 2023 and leads the AI team in San Francisco.\n"
    "Triplets:\n"
    "(John Smith, joined, Acme Corp)\n"
    "(John Smith, role, CTO)\n"
    "(John Smith, joined date, January 2023)\n"
    "(John Smith, leads, AI team)\n"
    "(AI team, located in, San Francisco)\n"
    "(Acme Corp, has team, AI team)\n"
    "---------------------\n"
    "Text: {text}\n"
    "Triplets:\n"
)

# Scientific/Research prompt
RESEARCH_KG_TRIPLET_EXTRACT_TMPL = (
    "Extract up to {max_knowledge_triplets} research-related knowledge triplets.\n\n"
    "FOCUS ON:\n"
    "- Researchers and their affiliations\n"
    "- Research topics and areas\n"
    "- Publications and findings\n"
    "- Methods and techniques\n"
    "- Experiments and results\n"
    "- Citations and references\n"
    "\n"
    "FORMAT: (subject, predicate, object)\n"
    "---------------------\n"
    "EXAMPLE:\n"
    "Text: Stanford researchers used machine learning to analyze climate data.\n"
    "Triplets:\n"
    "(Stanford, conducts, climate research)\n"
    "(researchers, affiliated with, Stanford)\n"
    "(researchers, used, machine learning)\n"
    "(machine learning, applied to, climate data)\n"
    "(climate data, analyzed by, researchers)\n"
    "---------------------\n"
    "Text: {text}\n"
    "Triplets:\n"
)

# Available prompt templates
PROMPT_TEMPLATES = {
    "default": DEFAULT_KG_TRIPLET_EXTRACT_TMPL,
    "enhanced": ENHANCED_KG_TRIPLET_EXTRACT_TMPL,
    "business": BUSINESS_KG_TRIPLET_EXTRACT_TMPL,
    "research": RESEARCH_KG_TRIPLET_EXTRACT_TMPL,
}

def get_prompt_template(template_name: str = "default") -> str:
    """
    Get a prompt template by name.

    Args:
        template_name: Name of the template (default, enhanced, business, research)

    Returns:
        The prompt template string
    """
    return PROMPT_TEMPLATES.get(template_name, DEFAULT_KG_TRIPLET_EXTRACT_TMPL)
