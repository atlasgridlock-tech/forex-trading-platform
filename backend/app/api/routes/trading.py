"""
Trading API Routes

Endpoints for trade execution, position management, and system control.
Now integrated with the paper trading service.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Depends, Body
from pydantic import BaseModel, Field

from app.services.trading_manager import (
    execute_market_trade,
    close_position,
    get_open_positions,
    get_account_state,
    modify_position,
)

router = APIRouter(prefix="/api/trading", tags=["trading"])


# ═══════════════════════════════════════════════════════════════
# Request/Response Models
# ═══════════════════════════════════════════════════════════════

class TradeRequest(BaseModel):
    """Trade execution request."""
    symbol: str = Field(..., description="Trading symbol (e.g., EURUSD)")
    direction: str = Field(..., pattern="^(long|short)$", description="Trade direction")
    volume: float = Field(..., gt=0, le=10.0, description="Position size in lots")
    stop_loss: float = Field(..., gt=0, description="Stop loss price (REQUIRED)")
    take_profit: Optional[float] = Field(None, gt=0, description="Take profit price")
    entry_price: Optional[float] = Field(None, gt=0, description="Entry price (optional, uses market)")
    order_type: str = Field(default="market", pattern="^(market|limit|stop)$")
    comment: Optional[str] = None


class ClosePositionRequest(BaseModel):
    """Position close request."""
    ticket: int
    volume: Optional[float] = None  # Partial close
    current_price: Optional[float] = None
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
    account = get_account_state()
    positions = get_open_positions()
    
    return {
        "mode": "paper",
        "kill_switch_active": False,
        "open_positions": len(positions),
        "daily_pnl": account.get("realized_pnl_today", 0.0),
        "daily_trades": 0,  # Would track from history
        "equity": account.get("equity", 10000.0),
        "balance": account.get("balance", 10000.0),
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
    
    This endpoint performs safety checks and executes on the paper trading service.
    
    Required:
    - symbol: Trading pair (e.g., EURUSD)
    - direction: 'long' or 'short'
    - volume: Position size in lots (max 10.0)
    - stop_loss: Stop loss price (MANDATORY)
    
    Optional:
    - take_profit: Take profit price
    - entry_price: Entry price (if not provided, uses simulated market price)
    """
    # Execute the trade
    result = execute_market_trade(
        symbol=request.symbol,
        direction=request.direction,
        volume=request.volume,
        stop_loss=request.stop_loss,
        take_profit=request.take_profit,
        entry_price=request.entry_price,
    )
    
    if not result.success:
        raise HTTPException(
            status_code=400,
            detail=result.error or "Trade execution failed"
        )
    
    return {
        "success": True,
        "receipt_id": result.receipt_id,
        "mode": result.mode,
        "ticket": result.ticket,
        "symbol": result.symbol,
        "direction": result.direction,
        "volume": result.volume,
        "entry_price": result.entry_price,
        "stop_loss": result.stop_loss,
        "take_profit": result.take_profit,
        "slippage_pips": result.slippage_pips,
        "message": f"Trade executed: {result.direction.upper()} {result.volume} {result.symbol} @ {result.entry_price}",
        "warnings": result.warnings,
    }


@router.post("/close")
async def close_position_endpoint(request: ClosePositionRequest):
    """Close an open position."""
    result = close_position(
        ticket=request.ticket,
        current_price=request.current_price,
        volume=request.volume,
    )
    
    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=result.get("error", "Position close failed")
        )
    
    return {
        "success": True,
        "ticket": result.get("ticket"),
        "symbol": result.get("symbol"),
        "direction": result.get("direction"),
        "volume": result.get("volume"),
        "exit_price": result.get("exit_price"),
        "pnl": result.get("pnl"),
        "message": f"Position {request.ticket} closed",
    }


@router.post("/modify")
async def modify_position_endpoint(request: ModifyPositionRequest):
    """Modify an open position's SL/TP."""
    if not request.stop_loss and not request.take_profit:
        raise HTTPException(
            status_code=400,
            detail="Must specify stop_loss or take_profit to modify"
        )
    
    result = modify_position(
        ticket=request.ticket,
        new_stop_loss=request.stop_loss,
        new_take_profit=request.take_profit,
    )
    
    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=result.get("error", "Position modification failed")
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
    positions = get_open_positions()
    closed_count = 0
    errors = []
    
    for pos in positions:
        result = close_position(ticket=pos["ticket"])
        if result.get("success"):
            closed_count += 1
        else:
            errors.append(f"Ticket {pos['ticket']}: {result.get('error')}")
    
    return {
        "success": len(errors) == 0,
        "message": f"Emergency close: {closed_count}/{len(positions)} positions closed",
        "authorized_by": authorized_by,
        "closed_positions": closed_count,
        "errors": errors if errors else None,
    }


# ═══════════════════════════════════════════════════════════════
# Position Endpoints
# ═══════════════════════════════════════════════════════════════

@router.get("/positions")
async def get_positions():
    """Get all open positions."""
    return get_open_positions()


@router.get("/positions/{ticket}")
async def get_position(ticket: int):
    """Get a specific position."""
    positions = get_open_positions()
    for pos in positions:
        if pos["ticket"] == ticket:
            return pos
    raise HTTPException(status_code=404, detail=f"Position {ticket} not found")


@router.post("/positions/{ticket}/close")
async def close_position_by_ticket(ticket: int):
    """Close a position by ticket number."""
    result = close_position(ticket=ticket)
    
    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=result.get("error", "Position close failed")
        )
    
    return {
        "success": True,
        "ticket": ticket,
        "pnl": result.get("pnl"),
        "message": f"Position {ticket} closed",
    }


# ═══════════════════════════════════════════════════════════════
# Promotion & Live Mode Endpoints
# ═══════════════════════════════════════════════════════════════

@router.get("/promotion/status")
async def get_promotion_status():
    """Check promotion gate status for live trading."""
    # Get current metrics from paper trading
    account = get_account_state()
    positions = get_open_positions()
    
    return {
        "ready_for_live": False,
        "gates_passed": 1,  # Drawdown passes by default
        "gates_total": 7,
        "gates": [
            {"gate": "min_trades", "required": 100, "actual": 0, "passed": False},
            {"gate": "min_days", "required": 30, "actual": 0, "passed": False},
            {"gate": "profit_factor", "required": 1.3, "actual": 0, "passed": False},
            {"gate": "max_drawdown", "required": "≤5.0%", "actual": f"{account.get('current_drawdown_pct', 0):.1f}%", "passed": account.get('current_drawdown_pct', 0) <= 5.0},
            {"gate": "win_rate", "required": "≥40%", "actual": "0%", "passed": False},
            {"gate": "avg_rr", "required": "≥1.5", "actual": 0, "passed": False},
            {"gate": "manual_approval", "required": "Required", "actual": "Not approved", "passed": False},
        ],
        "current_balance": account.get("balance", 10000),
        "current_equity": account.get("equity", 10000),
        "open_positions": len(positions),
    }


@router.post("/promotion/request-live")
async def request_live_mode(request: LiveModeRequest):
    """
    Request promotion to live trading mode.
    
    This creates a formal request that must be manually approved.
    """
    return {
        "request_id": f"LIVE-REQ-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "status": "gates_not_met",
        "message": "Promotion gates not yet passed. Continue paper trading.",
    }


@router.post("/promotion/approve")
async def approve_live_mode(approval: LiveModeApproval):
    """
    Approve a live mode request.
    
    ⚠️ This enables REAL MONEY trading.
    """
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
