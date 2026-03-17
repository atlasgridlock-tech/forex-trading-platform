"""
Agent Registry
==============
All AI-powered agents in the forex trading platform.
"""
from .base_agent import BaseAgent
from .agent_manager import AgentManager, get_agent_manager, start_agents, stop_agents
from .news_agent import NewsAgent
from .macro_agent import MacroAgent

__all__ = [
    "BaseAgent",
    "AgentManager",
    "get_agent_manager",
    "start_agents",
    "stop_agents",
    "NewsAgent",
    "MacroAgent",
]
