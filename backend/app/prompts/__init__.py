"""Industrial-grade prompts for all agents.

This module contains production-ready system messages and prompt templates
following industry best practices for LLM-based applications.
"""

from .investment_advisor import INVESTMENT_ADVISOR_SYSTEM_MESSAGE
from .react_analyst import REACT_ANALYST_SYSTEM_MESSAGE
from .research_analyst import RESEARCH_ANALYST_SYSTEM_MESSAGE
from .financial_analyst import FINANCIAL_ANALYST_SYSTEM_MESSAGE
from .routing import ROUTER_CLASSIFIER_SYSTEM_MESSAGE, INTENT_CLASSIFIER_SYSTEM_MESSAGE
from .memory import MEMORY_REFLECTION_SYSTEM_MESSAGE, MEMORY_COMPRESSION_SYSTEM_MESSAGE

__all__ = [
    "INVESTMENT_ADVISOR_SYSTEM_MESSAGE",
    "REACT_ANALYST_SYSTEM_MESSAGE",
    "RESEARCH_ANALYST_SYSTEM_MESSAGE",
    "FINANCIAL_ANALYST_SYSTEM_MESSAGE",
    "ROUTER_CLASSIFIER_SYSTEM_MESSAGE",
    "INTENT_CLASSIFIER_SYSTEM_MESSAGE",
    "MEMORY_REFLECTION_SYSTEM_MESSAGE",
    "MEMORY_COMPRESSION_SYSTEM_MESSAGE",
]
