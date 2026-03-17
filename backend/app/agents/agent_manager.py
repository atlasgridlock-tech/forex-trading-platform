"""
Agent Manager

Coordinates all AI agents, handles lifecycle, and provides API interface.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from .base_agent import BaseAgent
from .news_agent import NewsAgent
from .macro_agent import MacroAgent

logger = logging.getLogger(__name__)


class AgentManager:
    """
    Central manager for all trading agents.
    
    Responsibilities:
    - Start/stop agents
    - Route queries to appropriate agents
    - Aggregate views from all agents
    - Coordinate agent communication
    """
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.agents: Dict[str, BaseAgent] = {}
        self.tasks: Dict[str, asyncio.Task] = {}
        self.running = False
        
        # Initialize agents
        self._init_agents()
    
    def _init_agents(self):
        """Initialize all agent instances."""
        self.agents = {
            "news": NewsAgent(redis_url=self.redis_url),
            "macro": MacroAgent(redis_url=self.redis_url),
            # Future agents:
            # "sentiment": SentimentAgent(redis_url=self.redis_url),
            # "technical": TechnicalAgent(redis_url=self.redis_url),
            # "risk": RiskAgent(redis_url=self.redis_url),
        }
    
    async def start_all(self):
        """Start all agents."""
        if self.running:
            logger.warning("Agent manager already running")
            return
        
        self.running = True
        logger.info("Starting all agents...")
        
        for agent_id, agent in self.agents.items():
            task = asyncio.create_task(agent.run())
            self.tasks[agent_id] = task
            logger.info(f"Started agent: {agent.name}")
        
        logger.info(f"All {len(self.agents)} agents started")
    
    async def stop_all(self):
        """Stop all agents."""
        if not self.running:
            return
        
        logger.info("Stopping all agents...")
        
        for agent_id, agent in self.agents.items():
            agent.running = False
        
        for agent_id, task in self.tasks.items():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        self.tasks.clear()
        self.running = False
        logger.info("All agents stopped")
    
    async def get_agent_status(self) -> Dict[str, Any]:
        """Get status of all agents."""
        statuses = {}
        
        for agent_id, agent in self.agents.items():
            statuses[agent_id] = {
                "name": agent.name,
                "role": agent.role,
                "status": agent.state.get("status", "unknown"),
                "last_update": agent.state.get("last_update"),
                "current_view": agent.state.get("current_view", {}),
            }
        
        return {
            "manager_running": self.running,
            "agent_count": len(self.agents),
            "agents": statuses,
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    async def query_agent(self, agent_id: str, query: str) -> Dict[str, Any]:
        """Send a query to a specific agent."""
        agent = self.agents.get(agent_id)
        if not agent:
            return {"error": f"Agent '{agent_id}' not found"}
        
        response = await agent.handle_query(query)
        
        return {
            "agent": agent.name,
            "query": query,
            "response": response,
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    async def get_agent_view(self, agent_id: str, symbol: str = None) -> Dict[str, Any]:
        """Get an agent's current view."""
        agent = self.agents.get(agent_id)
        if not agent:
            return {"error": f"Agent '{agent_id}' not found"}
        
        view = await agent.get_view(symbol)
        
        return {
            "agent": agent.name,
            "symbol": symbol,
            "view": view,
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    async def get_aggregated_view(self, symbol: str = None) -> Dict[str, Any]:
        """Get aggregated view from all agents."""
        views = {}
        
        for agent_id, agent in self.agents.items():
            try:
                views[agent_id] = await agent.get_view(symbol)
            except Exception as e:
                views[agent_id] = {"error": str(e)}
        
        return {
            "symbol": symbol,
            "views": views,
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    async def trigger_analysis(self, agent_id: str = None) -> Dict[str, Any]:
        """Manually trigger analysis for one or all agents."""
        results = {}
        
        agents_to_analyze = [self.agents[agent_id]] if agent_id else self.agents.values()
        
        for agent in agents_to_analyze:
            try:
                result = await agent.analyze()
                results[agent.agent_id] = {"status": "success", "result": result}
            except Exception as e:
                results[agent.agent_id] = {"status": "error", "error": str(e)}
        
        return results


# Global instance
_manager: Optional[AgentManager] = None


def get_agent_manager() -> AgentManager:
    """Get or create the global agent manager."""
    global _manager
    if _manager is None:
        _manager = AgentManager()
    return _manager


async def start_agents():
    """Start all agents (called on app startup)."""
    manager = get_agent_manager()
    await manager.start_all()


async def stop_agents():
    """Stop all agents (called on app shutdown)."""
    manager = get_agent_manager()
    await manager.stop_all()
