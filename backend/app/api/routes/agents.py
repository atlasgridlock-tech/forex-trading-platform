"""
Agent API Routes
================
Endpoints for agent status and manual triggering.
"""
from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
from typing import Any

router = APIRouter(prefix="/api/agents", tags=["agents"])


# Agent registry (to be populated on startup)
_agents: dict[str, Any] = {}


def register_agent(name: str, agent: Any) -> None:
    """Register an agent in the API registry."""
    _agents[name] = agent


@router.get("/")
async def list_agents() -> dict:
    """List all registered agents and their status."""
    agents_status = []
    
    for name, agent in _agents.items():
        try:
            health = await agent.health_check()
            agents_status.append({
                "name": name,
                "is_healthy": health.is_healthy,
                "last_run": health.last_run.isoformat() if health.last_run else None,
                "last_success": health.last_success.isoformat() if health.last_success else None,
                "last_error": health.last_error,
                "consecutive_failures": health.consecutive_failures,
                "uptime_seconds": health.uptime_seconds,
                "dependencies": agent.get_dependencies(),
            })
        except Exception as e:
            agents_status.append({
                "name": name,
                "is_healthy": False,
                "error": str(e),
            })
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_agents": len(_agents),
        "agents": agents_status,
    }


@router.get("/{agent_name}")
async def get_agent_status(agent_name: str) -> dict:
    """Get detailed status for a specific agent."""
    if agent_name not in _agents:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    
    agent = _agents[agent_name]
    health = await agent.health_check()
    
    return {
        "name": agent_name,
        "is_healthy": health.is_healthy,
        "last_run": health.last_run.isoformat() if health.last_run else None,
        "last_success": health.last_success.isoformat() if health.last_success else None,
        "last_error": health.last_error,
        "consecutive_failures": health.consecutive_failures,
        "uptime_seconds": health.uptime_seconds,
        "dependencies": agent.get_dependencies(),
        "total_runs": agent.total_runs,
        "total_successes": agent.total_successes,
    }


@router.post("/{agent_name}/run")
async def trigger_agent(agent_name: str, context: dict = None) -> dict:
    """
    Manually trigger an agent run.
    
    Args:
        agent_name: Name of the agent to run
        context: Context data to pass to the agent
    """
    if agent_name not in _agents:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    
    agent = _agents[agent_name]
    context = context or {}
    
    try:
        result = await agent._execute(context)
        
        return {
            "success": True,
            "agent": agent_name,
            "message_id": result.message_id,
            "message_type": result.message_type,
            "confidence": result.confidence,
            "data_quality": result.data_quality,
            "warnings": result.warnings,
            "errors": result.errors,
            "payload": result.payload,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
