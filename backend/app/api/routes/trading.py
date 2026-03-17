"""
Trading API Routes

Endpoints for trade execution, position management, and system control.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Depends, Body
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/trading", tags=["trading"])


# ═══════════════════════════════════════════════════════════════
# Request/Response Models
# ═══════════════════════════════════════════════════════════════

class TradeRequest(BaseModel):
    """Trade execution request."""
    symbol: str
    direction: str = Field(..., pattern="^(long|short)$")
    volume: float = Field(..., gt=0, le=1.0)
    stop_loss: float = Field(..., gt=0)
    take_profit: Optional[float] = None
    order_type: str = Field(default="market", pattern="^(market|limit|stop)$")
    price: Optional[float] = None
    comment: Optional[str] = None


class ClosePositionRequest(BaseModel):
    """Position close request."""
    ticket: int
    volume: Optional[float] = None  # Partial close
    reason: Optional[str] = None


class ModifyPositionRequest(BaseModel):
    """Position modification request."""
    ticket: int
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


class LiveModeRequest(BaseModel):
    """Request to enable live mode."""
    requested_by: str
    reason: str


class LiveModeApproval(BaseModel):
    """Approval for live mode."""
    request_id: str
    approved_by: str


class KillSwitchAction(BaseModel):
    """Kill switch control."""
    action: str = Field(..., pattern="^(activate|deactivate)$")
    reason: Optional[str] = None
    authorized_by: str


# ═══════════════════════════════════════════════════════════════
# Status Endpoints
# ═══════════════════════════════════════════════════════════════

@router.get("/status")
async def get_trading_status():
    """Get current trading system status."""
    # Would get from injected service
    return {
        "mode": "paper",
        "kill_switch_active": False,
        "open_positions": 0,
        "daily_pnl": 0.0,
        "daily_trades": 0,
    }


@router.get("/mode")
async def get_trading_mode():
    """Get current trading mode."""
    return {
        "mode": "paper",
        "can_trade": True,
        "reason": None,
    }


# ═══════════════════════════════════════════════════════════════
# Execution Endpoints
# ═══════════════════════════════════════════════════════════════

@router.post("/execute")
async def execute_trade(request: TradeRequest):
    """
    Execute a trade.
    
    This endpoint goes through all safety checks before execution.
    """
    # Validate stop loss exists (redundant but explicit)
    if not request.stop_loss or request.stop_loss <= 0:
        raise HTTPException(
            status_code=400,
            detail="Stop loss is REQUIRED for all trades"
        )
    
    # Would call live_trading_service.execute_trade()
    return {
        "success": True,
        "receipt_id": f"EXEC-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        "mode": "paper",
        "message": "Trade executed on paper trading",
    }


@router.post("/close")
async def close_position(request: ClosePositionRequest):
    """Close an open position."""
    # Would call live_trading_service.close_position()
    return {
        "success": True,
        "ticket": request.ticket,
        "message": "Position closed",
    }


@router.post("/modify")
async def modify_position(request: ModifyPositionRequest):
    """Modify an open position's SL/TP."""
    if not request.stop_loss and not request.take_profit:
        raise HTTPException(
            status_code=400,
            detail="Must specify stop_loss or take_profit to modify"
        )
    
    return {
        "success": True,
        "ticket": request.ticket,
        "message": "Position modified",
    }


@router.post("/emergency-close-all")
async def emergency_close_all(authorized_by: str = Body(..., embed=True)):
    """
    Emergency close all positions.
    
    ⚠️ This will close ALL open positions immediately.
    """
    # Would call live_trading_service.emergency_close_all()
    return {
        "success": True,
        "message": "Emergency close initiated",
        "authorized_by": authorized_by,
        "closed_positions": 0,
    }


# ═══════════════════════════════════════════════════════════════
# Position Endpoints
# ═══════════════════════════════════════════════════════════════

@router.get("/positions")
async def get_positions():
    """Get all open positions."""
    return []


@router.get("/positions/{ticket}")
async def get_position(ticket: int):
    """Get a specific position."""
    raise HTTPException(status_code=404, detail="Position not found")


# ═══════════════════════════════════════════════════════════════
# Promotion & Live Mode Endpoints
# ═══════════════════════════════════════════════════════════════

@router.get("/promotion/status")
async def get_promotion_status():
    """Check promotion gate status for live trading."""
    # Would call live_trading_service.check_promotion_gates()
    return {
        "ready_for_live": False,
        "gates_passed": 0,
        "gates_total": 7,
        "gates": [
            {"gate": "min_trades", "required": 100, "actual": 0, "passed": False},
            {"gate": "min_days", "required": 30, "actual": 0, "passed": False},
            {"gate": "profit_factor", "required": 1.3, "actual": 0, "passed": False},
            {"gate": "max_drawdown", "required": "≤5.0%", "actual": "0.0%", "passed": True},
            {"gate": "win_rate", "required": "≥40%", "actual": "0%", "passed": False},
            {"gate": "avg_rr", "required": "≥1.5", "actual": 0, "passed": False},
            {"gate": "manual_approval", "required": "Required", "actual": "Not approved", "passed": False},
        ],
    }


@router.post("/promotion/request-live")
async def request_live_mode(request: LiveModeRequest):
    """
    Request promotion to live trading mode.
    
    This creates a formal request that must be manually approved.
    """
    # Would call live_trading_service.request_live_mode()
    return {
        "request_id": f"LIVE-REQ-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        "status": "gates_not_met",
        "message": "Promotion gates not yet passed. Continue paper trading.",
    }


@router.post("/promotion/approve")
async def approve_live_mode(approval: LiveModeApproval):
    """
    Approve a live mode request.
    
    ⚠️ This enables REAL MONEY trading.
    """
    # Would call live_trading_service.approve_live_mode()
    return {
        "success": False,
        "error": "Promotion gates not met",
    }


# ═══════════════════════════════════════════════════════════════
# Kill Switch Endpoints
# ═══════════════════════════════════════════════════════════════

@router.get("/kill-switch/status")
async def get_kill_switch_status():
    """Get kill switch status."""
    return {
        "active": False,
        "reason": None,
        "activated_at": None,
    }


@router.post("/kill-switch")
async def control_kill_switch(action: KillSwitchAction):
    """
    Control the kill switch.
    
    - activate: Stop all trading immediately
    - deactivate: Resume trading (requires authorization)
    """
    if action.action == "activate":
        return {
            "success": True,
            "message": f"Kill switch activated: {action.reason}",
            "authorized_by": action.authorized_by,
        }
    else:
        return {
            "success": True,
            "message": "Kill switch deactivated",
            "authorized_by": action.authorized_by,
        }


# ═══════════════════════════════════════════════════════════════
# Execution History
# ═══════════════════════════════════════════════════════════════

@router.get("/executions")
async def get_executions(
    limit: int = 50,
    mode: Optional[str] = None,
):
    """Get execution history."""
    return []


@router.get("/executions/{receipt_id}")
async def get_execution(receipt_id: str):
    """Get a specific execution receipt."""
    raise HTTPException(status_code=404, detail="Execution not found")
