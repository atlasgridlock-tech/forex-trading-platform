"""
Agent API Routes

Provides REST endpoints to:
- Query agents
- Get agent status
- Interact with agents conversationally
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from ...agents.agent_manager import get_agent_manager

router = APIRouter(prefix="/api/ai-agents", tags=["ai-agents"])


class QueryRequest(BaseModel):
    query: str


# ═══════════════════════════════════════════════════════════════
# Static routes (must be BEFORE dynamic /{agent_id} routes)
# ═══════════════════════════════════════════════════════════════

@router.get("")
async def list_agents():
    """List all available agents."""
    manager = get_agent_manager()
    return {
        "agents": [
            {
                "id": agent_id,
                "name": agent.name,
                "role": agent.role,
                "status": agent.state.get("status", "unknown"),
            }
            for agent_id, agent in manager.agents.items()
        ]
    }


@router.get("/status")
async def get_agents_status():
    """Get status of all agents."""
    manager = get_agent_manager()
    return await manager.get_agent_status()


@router.get("/views/aggregated")
async def get_aggregated_views(symbol: Optional[str] = None):
    """Get aggregated views from all agents."""
    manager = get_agent_manager()
    return await manager.get_aggregated_view(symbol)


@router.post("/analyze/all")
async def trigger_all_analysis():
    """Manually trigger analysis for all agents."""
    manager = get_agent_manager()
    results = await manager.trigger_analysis()
    return results


# ═══════════════════════════════════════════════════════════════
# News Agent shortcuts
# ═══════════════════════════════════════════════════════════════

@router.get("/news/latest")
async def get_latest_news(symbol: Optional[str] = None):
    """Get latest news from the News Agent."""
    manager = get_agent_manager()
    return await manager.get_agent_view("news", symbol)


# ═══════════════════════════════════════════════════════════════
# Macro Agent shortcuts
# ═══════════════════════════════════════════════════════════════

@router.get("/macro/rates")
async def get_interest_rates():
    """Get current interest rates and differentials."""
    manager = get_agent_manager()
    macro = manager.agents.get("macro")
    if not macro:
        raise HTTPException(status_code=503, detail="Macro agent not available")
    
    return {
        "rates": macro.CENTRAL_BANKS,
        "view": await macro.get_view(),
    }


@router.get("/macro/calendar")
async def get_economic_calendar():
    """Get upcoming economic events."""
    manager = get_agent_manager()
    result = await manager.get_agent_view("macro")
    return result.get("view", {}).get("upcoming_events", [])


# ═══════════════════════════════════════════════════════════════
# Dynamic agent routes (LAST - uses path parameter)
# ═══════════════════════════════════════════════════════════════

@router.get("/{agent_id}")
async def get_agent_info(agent_id: str):
    """Get detailed info about a specific agent."""
    manager = get_agent_manager()
    agent = manager.agents.get(agent_id)
    
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    
    return {
        "id": agent_id,
        "name": agent.name,
        "role": agent.role,
        "status": agent.state.get("status"),
        "last_update": agent.state.get("last_update"),
        "current_view": agent.state.get("current_view", {}),
        "system_prompt": agent.system_prompt[:500] + "..." if len(agent.system_prompt) > 500 else agent.system_prompt,
    }


@router.post("/{agent_id}/query")
async def query_agent(agent_id: str, request: QueryRequest):
    """
    Send a natural language query to an agent.
    
    Example: "What's your view on EURUSD?" or "Any high-impact news today?"
    """
    manager = get_agent_manager()
    result = await manager.query_agent(agent_id, request.query)
    
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    
    return result


@router.get("/{agent_id}/view")
async def get_agent_view(agent_id: str, symbol: Optional[str] = None):
    """Get an agent's current view, optionally for a specific symbol."""
    manager = get_agent_manager()
    result = await manager.get_agent_view(agent_id, symbol)
    
    if "error" in result.get("view", {}):
        raise HTTPException(status_code=404, detail=result["view"]["error"])
    
    return result


@router.post("/{agent_id}/analyze")
async def trigger_agent_analysis(agent_id: str):
    """Manually trigger analysis for an agent."""
    manager = get_agent_manager()
    
    if agent_id not in manager.agents:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    
    results = await manager.trigger_analysis(agent_id)
    return results
