"""
Deep Research Agent

A multi-agent research system with specialized sub-agents for comprehensive
document analysis. The Planner agent orchestrates reusable sub-agents to
perform deep research across large document sets.

Sub-Agents:
- Decomposer: Breaks complex queries into atomic sub-questions
- Perspective: Generates diverse research angles
- Aggregator: Computes dataset-wide statistics via OpenSearch aggregations
- Scanner: Iterates through large result sets in batches
- Sampler: Gets representative samples across categories
- Extractor: Extracts structured facts from documents
- Synthesizer: Combines findings into coherent narrative
- Validator: Checks findings for accuracy and contradictions
- GapAnalyzer: Identifies coverage gaps and suggests next steps
"""

from .graph_definition import compiled_agent as research_compiled_agent

__all__ = ["research_compiled_agent"]
