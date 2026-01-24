"""
Sub-Agents for Deep Research Agent

Each sub-agent is a specialized component with a specific skill that can be
called by the Planner agent to perform deep research tasks.
"""
from .base import SubAgent, SubAgentRegistry
from .decomposer import DecomposerAgent
from .perspective import PerspectiveAgent
from .aggregator import AggregatorAgent
from .scanner import ScannerAgent
from .sampler import SamplerAgent
from .extractor import ExtractorAgent
from .synthesizer import SynthesizerAgent
from .validator import ValidatorAgent
from .gap_analyzer import GapAnalyzerAgent

# Initialize the registry with all sub-agents
def create_sub_agent_registry() -> SubAgentRegistry:
    """Create and populate the sub-agent registry"""
    registry = SubAgentRegistry()

    # Register all sub-agents
    registry.register(DecomposerAgent())
    registry.register(PerspectiveAgent())
    registry.register(AggregatorAgent())
    registry.register(ScannerAgent())
    registry.register(SamplerAgent())
    registry.register(ExtractorAgent())
    registry.register(SynthesizerAgent())
    registry.register(ValidatorAgent())
    registry.register(GapAnalyzerAgent())

    return registry

__all__ = [
    "SubAgent",
    "SubAgentRegistry",
    "DecomposerAgent",
    "PerspectiveAgent",
    "AggregatorAgent",
    "ScannerAgent",
    "SamplerAgent",
    "ExtractorAgent",
    "SynthesizerAgent",
    "ValidatorAgent",
    "GapAnalyzerAgent",
    "create_sub_agent_registry"
]
