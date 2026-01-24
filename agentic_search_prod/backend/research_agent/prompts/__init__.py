"""
Prompts for Deep Research Agent and Sub-Agents
"""
from .decomposer_prompts import DECOMPOSER_SYSTEM_PROMPT, create_decomposer_prompt
from .perspective_prompts import PERSPECTIVE_SYSTEM_PROMPT, create_perspective_prompt
from .planner_prompts import PLANNER_SYSTEM_PROMPT, create_planner_prompt

__all__ = [
    "DECOMPOSER_SYSTEM_PROMPT",
    "create_decomposer_prompt",
    "PERSPECTIVE_SYSTEM_PROMPT",
    "create_perspective_prompt",
    "PLANNER_SYSTEM_PROMPT",
    "create_planner_prompt"
]
