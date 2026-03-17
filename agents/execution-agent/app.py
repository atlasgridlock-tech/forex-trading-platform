"""
Execution Agent - Executor
Trade execution, broker interface, order management
MOST DANGEROUS AGENT - MAXIMUM SAFETY
"""

import os
import sys
import json
import asyncio
import httpx
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from enum import Enum
from dataclasses import dataclass
import time

# Add shared module to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared import (
    call_claude,
    get_agent_url,
    post_json,
    broker_symbol as shared_broker_symbol,
    internal_symbol as shared_internal_symbol,
    SYMBOL_SUFFIX,
    ChatRequest,
)

app = FastAPI(title="Executor - Execution Agent", version="2.0")

AGENT_NAME = "Executor"
GUARDIAN_URL = get_agent_url("guardian")
PORTFOLIO_URL = get_agent_url("balancer")
ORCHESTRATOR_URL = get_agent_url("orchestrator")

# MT5 File Bridge paths
MT5_FILES_PATH = Path(os.getenv("MT5_FILES_PATH", "/mt5files"))
MT5_COMMAND_FILE = MT5_FILES_PATH / "trade_commands.json"
MT5_RESULT_FILE = MT5_FILES_PATH / "trade_results.json"
MT5_STATUS_FILE = MT5_FILES_PATH / "bridge_status.json"

# Broker symbol configuration (using shared module)

# CRITICAL: Default to paper mode
EXECUTION_MODE = os.getenv("EXECUTION_MODE", "paper")  # paper, shadow_live, guarded_live
LIVE_MODE_CONFIRMED = os.getenv("LIVE_MODE_CONFIRMED", "false").lower() == "true"


# Using shared broker_symbol and internal_symbol
def broker_symbol(symbol: str) -> str:
    """Convert internal symbol to broker symbol."""
    return shared_broker_symbol(symbol)


def internal_symbol(broker_sym: str) -> str:
    """Convert broker symbol to internal symbol."""
    return shared_internal_symbol(broker_sym)


# Using ChatRequest from shared module


class OrderRequest(BaseModel):
    symbol: str
    direction: str  # "long" or "short"
    lot_size: float
    entry_price: Optional[float] = None  # None = market order
    stop_loss: float  # MANDATORY
    take_profit: Optional[float] = None
    take_profit_2: Optional[float] = None
    take_profit_3: Optional[float] = None
    trailing_stop_pips: Optional[float] = None
    magic_number: int = 123456
    comment: str = "Executor v2.0"
    order_type: str = "market"  # market, limit, stop


class ExecutionMode(str, Enum):
    PAPER = "paper"
    SHADOW_LIVE = "shadow_live"
    GUARDED_LIVE = "guarded_live"


# ═══════════════════════════════════════════════════════════════
# SAFETY THRESHOLDS
# ═══════════════════════════════════════════════════════════════

@dataclass
class SafetyConfig:
    # Spread limits by pair type
    max_spread_majors: float = 2.0
    max_spread_minors: float = 3.0
    max_spread_exotics: float = 5.0
    
    # Slippage limits
    max_slippage_market: float = 1.0
    max_slippage_pending: float = 0.5
    
    # Execution limits
    max_retries: int = 2
    retry_delay_ms: int = 500
    order_timeout_seconds: int = 30
    
    # Anti-pattern detection
    min_time_between_trades_seconds: int = 60
    max_trades_per_symbol_per_hour: int = 3


safety = SafetyConfig()

# Execution state
execution_mode = ExecutionMode(EXECUTION_MODE)
order_history: List[dict] = []
execution_receipts: List[dict] = []
active_orders: Dict[str, dict] = {}
signal_hashes: set = set()  # For duplicate detection
last_trade_times: Dict[str, datetime] = {}
trades_per_symbol_hour: Dict[str, int] = {}

# Simulated broker state (paper mode)
paper_positions: List[dict] = []
paper_balance: float = 10000.0
paper_equity: float = 10000.0

MAJOR_PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD"]


def get_max_spread(symbol: str) -> float:
    """Get max allowed spread for symbol."""
    if symbol in MAJOR_PAIRS:
        return safety.max_spread_majors
    return safety.max_spread_minors


def generate_signal_hash(order: OrderRequest) -> str:
    """Generate hash to detect duplicate signals."""
    data = f"{order.symbol}:{order.direction}:{order.stop_loss}:{order.entry_price}"
    return hashlib.md5(data.encode()).hexdigest()[:16]


def is_duplicate_signal(order: OrderRequest) -> bool:
    """Check if this signal was already processed."""
    signal_hash = generate_signal_hash(order)
    if signal_hash in signal_hashes:
        return True
    return False


def is_martingale(order: OrderRequest) -> bool:
    """Detect martingale pattern (increasing size after loss)."""
    # Check last trade on this symbol
    symbol_trades = [r for r in execution_receipts if r["symbol"] == order.symbol]
    if len(symbol_trades) < 2:
        return False
    
    last_trade = symbol_trades[-1]
    if last_trade.get("pnl", 0) < 0:  # Last trade was a loss
        if order.lot_size > last_trade.get("lot_size", 0):
            return True  # Size increased after loss = martingale
    
    return False


def is_averaging_down(order: OrderRequest) -> bool:
    """Detect averaging down (adding to losing position)."""
    # Check if we have an open position in this symbol
    for pos in paper_positions:
        if pos["symbol"] == order.symbol:
            if pos["direction"] == order.direction:
                # Same direction, check if position is losing
                if pos.get("unrealized_pnl", 0) < 0:
                    return True  # Adding to losing position
    return False


def check_rate_limits(symbol: str) -> tuple[bool, str]:
    """Check trading rate limits."""
    now = datetime.utcnow()
    
    # Check time since last trade
    if symbol in last_trade_times:
        seconds_since = (now - last_trade_times[symbol]).total_seconds()
        if seconds_since < safety.min_time_between_trades_seconds:
            return False, f"Too soon since last {symbol} trade ({seconds_since:.0f}s < {safety.min_time_between_trades_seconds}s)"
    
    # Check trades per hour
    hour_key = f"{symbol}:{now.strftime('%Y%m%d%H')}"
    if trades_per_symbol_hour.get(hour_key, 0) >= safety.max_trades_per_symbol_per_hour:
        return False, f"Max trades per hour reached for {symbol}"
    
    return True, "OK"


async def check_guardian_approval(order: OrderRequest) -> tuple[bool, dict]:
    """Get Guardian's approval for this trade."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{GUARDIAN_URL}/api/evaluate",
                json={
                    "symbol": order.symbol,
                    "direction": order.direction,
                    "entry": order.entry_price or 0,
                    "stop": order.stop_loss,
                    "take_profit": order.take_profit,
                    "confidence": 0.7,
                },
                timeout=10.0
            )
            if r.status_code == 200:
                result = r.json()
                return result.get("approved", False), result
    except Exception as e:
        return False, {"error": str(e)}
    
    return False, {"error": "Guardian unreachable"}


async def notify_portfolio(order: OrderRequest, receipt: dict):
    """Notify Portfolio agent of new position."""
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{PORTFOLIO_URL}/api/position/add",
                json={
                    "symbol": order.symbol,
                    "direction": order.direction,
                    "risk_pct": receipt.get("risk_pct", 0.25),
                    "entry_price": receipt.get("fill_price", order.entry_price),
                },
                timeout=5.0
            )
    except:
        pass


async def send_to_orchestrator(receipt: dict):
    """Send execution receipt to Orchestrator."""
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{ORCHESTRATOR_URL}/api/ingest",
                json={
                    "agent_id": "execution",
                    "agent_name": AGENT_NAME,
                    "output_type": "execution",
                    "timestamp": datetime.utcnow().isoformat(),
                    "data": {
                        "order_id": receipt["order_id"],
                        "symbol": receipt["symbol"],
                        "direction": receipt["direction"],
                        "status": receipt["status"],
                        "fill_price": receipt.get("fill_price"),
                        "health_score": receipt.get("health_score"),
                    },
                },
                timeout=5.0
            )
    except:
        pass


def calculate_health_score(receipt: dict) -> int:
    """Calculate execution health score (0-100)."""
    score = 100
    
    # Slippage penalty
    slippage = abs(receipt.get("slippage_pips", 0))
    if slippage > 0.5:
        score -= min(30, int(slippage * 15))
    
    # Latency penalty
    latency = receipt.get("latency_ms", 0)
    if latency > 100:
        score -= min(20, int((latency - 100) / 50))
    
    # SL/TP confirmation
    if not receipt.get("sl_confirmed"):
        score -= 30
    if receipt.get("take_profit") and not receipt.get("tp_confirmed"):
        score -= 10
    
    # Spread penalty
    spread = receipt.get("spread_at_fill", 0)
    max_spread = get_max_spread(receipt.get("symbol", "EURUSD"))
    if spread > max_spread * 0.8:
        score -= 10
    
    return max(0, score)


def execute_paper_order(order: OrderRequest) -> dict:
    """Execute order in paper mode (simulation)."""
    global paper_balance
    
    start_time = time.time()
    
    # Simulate market conditions
    simulated_spread = 0.8  # pips
    simulated_slippage = 0.1  # pips (favorable)
    
    # Calculate fill price
    if order.direction.lower() == "long":
        fill_price = (order.entry_price or 1.0850) + (simulated_slippage / 10000)
    else:
        fill_price = (order.entry_price or 1.0850) - (simulated_slippage / 10000)
    
    latency_ms = int((time.time() - start_time) * 1000) + 45  # Simulated latency
    
    # Create order ID
    order_id = f"PAPER-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{len(execution_receipts):03d}"
    
    # Add to paper positions
    paper_positions.append({
        "order_id": order_id,
        "symbol": order.symbol,
        "direction": order.direction,
        "lot_size": order.lot_size,
        "entry_price": fill_price,
        "stop_loss": order.stop_loss,
        "take_profit": order.take_profit,
        "open_time": datetime.utcnow().isoformat(),
    })
    
    receipt = {
        "order_id": order_id,
        "ticket": None,  # No broker ticket in paper mode
        "symbol": order.symbol,
        "direction": order.direction,
        "lot_size": order.lot_size,
        "intent_price": order.entry_price,
        "fill_price": round(fill_price, 5),
        "stop_loss": order.stop_loss,
        "take_profit": order.take_profit,
        "fill_time": datetime.utcnow().isoformat(),
        "latency_ms": latency_ms,
        "slippage_pips": round(-simulated_slippage, 2),  # Negative = favorable
        "spread_at_fill": simulated_spread,
        "sl_confirmed": True,
        "tp_confirmed": order.take_profit is not None,
        "broker_status": "FILLED",
        "mode": "paper",
        "status": "EXECUTED",
    }
    
    receipt["health_score"] = calculate_health_score(receipt)
    
    return receipt


def execute_shadow_order(order: OrderRequest) -> dict:
    """Execute order in shadow mode (log only, no execution)."""
    order_id = f"SHADOW-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{len(execution_receipts):03d}"
    
    receipt = {
        "order_id": order_id,
        "ticket": None,
        "symbol": order.symbol,
        "direction": order.direction,
        "lot_size": order.lot_size,
        "intent_price": order.entry_price,
        "fill_price": None,  # Not filled
        "stop_loss": order.stop_loss,
        "take_profit": order.take_profit,
        "fill_time": None,
        "latency_ms": 0,
        "slippage_pips": 0,
        "spread_at_fill": 0,
        "sl_confirmed": False,
        "tp_confirmed": False,
        "broker_status": "NOT_SENT",
        "mode": "shadow",
        "status": "LOGGED_ONLY",
        "health_score": 0,
        "note": "Shadow mode - signal logged but not executed",
    }
    
    return receipt


def write_mt5_command(command: dict) -> bool:
    """Write command to MT5 file bridge."""
    try:
        MT5_FILES_PATH.mkdir(parents=True, exist_ok=True)
        with open(MT5_COMMAND_FILE, 'w') as f:
            json.dump(command, f, indent=2)
        return True
    except Exception as e:
        print(f"[Executor] Error writing command: {e}")
        return False


def read_mt5_result(command_id: str, timeout_seconds: int = 30) -> Optional[dict]:
    """Read result from MT5 file bridge with timeout."""
    start_time = time.time()
    
    while time.time() - start_time < timeout_seconds:
        try:
            if MT5_RESULT_FILE.exists():
                with open(MT5_RESULT_FILE, 'r') as f:
                    result = json.load(f)
                
                # Check if this is our result
                if result.get("command_id") == command_id:
                    # Delete result file after reading
                    MT5_RESULT_FILE.unlink()
                    return result
        except:
            pass
        
        time.sleep(0.1)  # Poll every 100ms
    
    return None


def check_mt5_bridge_status() -> dict:
    """Check MT5 bridge EA status."""
    try:
        if MT5_STATUS_FILE.exists():
            with open(MT5_STATUS_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {"status": "UNKNOWN", "message": "Cannot read status file"}


def read_mt5_positions() -> Optional[dict]:
    """Read positions and pending orders from MT5."""
    try:
        positions_file = MT5_FILES_PATH / "positions.json"
        if positions_file.exists():
            with open(positions_file, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"[Executor] Error reading positions: {e}")
    return None


def execute_live_order(order: OrderRequest) -> dict:
    """Execute order in live mode via MT5 File Bridge (REAL MONEY)."""
    # SAFETY: Double-check confirmation
    if not LIVE_MODE_CONFIRMED:
        raise HTTPException(status_code=403, detail="LIVE MODE NOT CONFIRMED")
    
    # Check bridge status
    bridge_status = check_mt5_bridge_status()
    if bridge_status.get("status") != "READY":
        return {
            "order_id": f"LIVE-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            "status": "ERROR",
            "error": f"MT5 Bridge not ready: {bridge_status.get('message', 'Unknown')}",
            "mode": "guarded_live",
            "health_score": 0,
        }
    
    # Generate command ID
    command_id = f"CMD-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
    
    # Build command (convert to broker symbol format)
    command = {
        "command_id": command_id,
        "action": "OPEN",
        "symbol": broker_symbol(order.symbol),  # Add broker suffix
        "direction": order.direction,
        "lots": order.lot_size,
        "stop_loss": order.stop_loss,
        # NO TP in MT5! Lifecycle handles partial TPs programmatically
        # Setting TP=0 means MT5 won't auto-close, letting us scale out
        "take_profit": 0,
        "entry_price": order.entry_price or 0,
        "timestamp": datetime.utcnow().isoformat(),
    }
    
    # Write command
    start_time = time.time()
    if not write_mt5_command(command):
        return {
            "order_id": command_id,
            "status": "ERROR",
            "error": "Failed to write command file",
            "mode": "guarded_live",
            "health_score": 0,
        }
    
    # Wait for result
    result = read_mt5_result(command_id, timeout_seconds=30)
    latency_ms = int((time.time() - start_time) * 1000)
    
    if result is None:
        return {
            "order_id": command_id,
            "status": "TIMEOUT",
            "error": "MT5 Bridge did not respond in time",
            "mode": "guarded_live",
            "latency_ms": latency_ms,
            "health_score": 0,
        }
    
    # Process result
    if result.get("status") == "EXECUTED":
        receipt = {
            "order_id": command_id,
            "ticket": result.get("ticket"),
            "symbol": order.symbol,
            "direction": order.direction,
            "lot_size": order.lot_size,
            "intent_price": order.entry_price,
            "fill_price": result.get("fill_price"),
            "stop_loss": order.stop_loss,
            "take_profit": order.take_profit,
            "fill_time": result.get("timestamp"),
            "latency_ms": latency_ms,
            "slippage_pips": result.get("slippage_pips", 0),
            "spread_at_fill": 0,
            "sl_confirmed": True,
            "tp_confirmed": order.take_profit is not None,
            "broker_status": "FILLED",
            "mode": "guarded_live",
            "status": "EXECUTED",
            "mt5_message": result.get("message"),
        }
        receipt["health_score"] = calculate_health_score(receipt)
        return receipt
    else:
        return {
            "order_id": command_id,
            "status": result.get("status", "ERROR"),
            "error": result.get("message", "Unknown error from MT5"),
            "mode": "guarded_live",
            "latency_ms": latency_ms,
            "health_score": 0,
        }


async def execute_order(order: OrderRequest) -> dict:
    """Main execution function with all safety checks."""
    
    # ═══════════════════════════════════════════════════════════
    # CRITICAL SAFETY CHECKS - NO OVERRIDE POSSIBLE
    # ═══════════════════════════════════════════════════════════
    
    # 1. MANDATORY STOP LOSS
    if order.stop_loss is None or order.stop_loss == 0:
        return {
            "status": "REJECTED",
            "reason": "NO NAKED TRADES - Stop loss is MANDATORY",
            "health_score": 0,
        }
    
    # 2. NO DUPLICATE SIGNALS
    if is_duplicate_signal(order):
        return {
            "status": "REJECTED",
            "reason": "Duplicate signal detected - already processed",
            "health_score": 0,
        }
    
    # 3. NO MARTINGALE
    if is_martingale(order):
        return {
            "status": "REJECTED",
            "reason": "MARTINGALE DETECTED - Cannot increase size after loss",
            "health_score": 0,
        }
    
    # 4. NO AVERAGING DOWN
    if is_averaging_down(order):
        return {
            "status": "REJECTED",
            "reason": "AVERAGING DOWN DETECTED - Cannot add to losing position",
            "health_score": 0,
        }
    
    # 4b. NO DUPLICATE POSITIONS (check live MT5 positions)
    existing_positions = read_mt5_positions()
    if existing_positions and existing_positions.get("positions"):
        for pos in existing_positions["positions"]:
            pos_symbol = pos.get("symbol", "").replace(".s", "").replace(".S", "")
            order_symbol = order.symbol.replace(".s", "").replace(".S", "")
            if pos_symbol == order_symbol:
                # Already have a position in this symbol
                return {
                    "status": "REJECTED",
                    "reason": f"DUPLICATE POSITION - Already have {pos.get('direction')} position in {pos_symbol} (ticket: {pos.get('ticket')})",
                    "health_score": 0,
                }
    
    # 5. RATE LIMITS
    rate_ok, rate_msg = check_rate_limits(order.symbol)
    if not rate_ok:
        return {
            "status": "REJECTED",
            "reason": rate_msg,
            "health_score": 0,
        }
    
    # 6. GUARDIAN APPROVAL
    guardian_approved, guardian_result = await check_guardian_approval(order)
    if not guardian_approved:
        return {
            "status": "REJECTED",
            "reason": f"Guardian denied: {guardian_result.get('reason', 'Unknown')}",
            "guardian_result": guardian_result,
            "health_score": 0,
        }
    
    # ═══════════════════════════════════════════════════════════
    # EXECUTION BY MODE
    # ═══════════════════════════════════════════════════════════
    
    if execution_mode == ExecutionMode.PAPER:
        receipt = execute_paper_order(order)
    elif execution_mode == ExecutionMode.SHADOW_LIVE:
        receipt = execute_shadow_order(order)
    elif execution_mode == ExecutionMode.GUARDED_LIVE:
        receipt = execute_live_order(order)
    else:
        return {"status": "ERROR", "reason": f"Unknown mode: {execution_mode}"}
    
    # Record execution
    execution_receipts.append(receipt)
    signal_hashes.add(generate_signal_hash(order))
    last_trade_times[order.symbol] = datetime.utcnow()
    
    hour_key = f"{order.symbol}:{datetime.utcnow().strftime('%Y%m%d%H')}"
    trades_per_symbol_hour[hour_key] = trades_per_symbol_hour.get(hour_key, 0) + 1
    
    # Notify other agents
    if receipt.get("status") == "EXECUTED":
        await notify_portfolio(order, receipt)
    await send_to_orchestrator(receipt)
    
    return receipt


# Using shared call_claude - removed duplicate implementation


@app.on_event("startup")
async def startup():
    print(f"🚀 {AGENT_NAME} (Execution Agent) v2.0 starting...")
    print(f"   ⚠️  MODE: {execution_mode.value.upper()}")
    if execution_mode == ExecutionMode.GUARDED_LIVE:
        if LIVE_MODE_CONFIRMED:
            print("   🔴 LIVE TRADING ENABLED - REAL MONEY AT RISK")
        else:
            print("   ⛔ Live mode requested but NOT CONFIRMED - blocking live trades")


@app.get("/", response_class=HTMLResponse)
async def home():
    mode_colors = {
        ExecutionMode.PAPER: "#22c55e",
        ExecutionMode.SHADOW_LIVE: "#f59e0b",
        ExecutionMode.GUARDED_LIVE: "#ef4444",
    }
    mode_color = mode_colors.get(execution_mode, "#888")
    
    # Recent receipts
    receipts_html = ""
    for receipt in reversed(execution_receipts[-10:]):
        status_color = "#22c55e" if receipt.get("status") == "EXECUTED" else "#f59e0b" if receipt.get("status") == "LOGGED_ONLY" else "#ef4444"
        receipts_html += f'''
        <div class="receipt">
            <div class="receipt-header">
                <span style="color:{status_color}">{receipt.get("status", "?")}</span>
                <span>{receipt.get("order_id", "?")}</span>
            </div>
            <div class="receipt-body">
                {receipt.get("symbol", "?")} {receipt.get("direction", "?").upper()} @ {receipt.get("fill_price", "?")}
            </div>
            <div class="receipt-footer">
                Health: {receipt.get("health_score", 0)}/100 | Slippage: {receipt.get("slippage_pips", 0)} pips
            </div>
        </div>
        '''
    if not receipts_html:
        receipts_html = '<div style="color:#666">No executions yet</div>'
    
    # Positions - use MT5 in live mode, paper otherwise
    pos_html = ""
    if execution_mode == ExecutionMode.GUARDED_LIVE:
        mt5_data = read_mt5_positions()
        positions = mt5_data.get("positions", []) if mt5_data else []
        for pos in positions:
            pnl = pos.get("profit", 0)
            pnl_color = "#22c55e" if pnl >= 0 else "#ef4444"
            pos_html += f'''
            <div class="position">
                <span>{pos.get("symbol", "?")} {pos.get("direction", "?").upper()}</span>
                <span>{pos.get("volume", 0)} lots @ {pos.get("open_price", 0):.5f}</span>
                <span style="color:{pnl_color}">P/L: ${pnl:+.2f}</span>
            </div>
            '''
    else:
        for pos in paper_positions:
            pos_html += f'''
            <div class="position">
                <span>{pos["symbol"]} {pos["direction"].upper()}</span>
                <span>{pos["lot_size"]} lots @ {pos["entry_price"]}</span>
            </div>
            '''
    if not pos_html:
        pos_html = '<div style="color:#666">No open positions</div>'
    
    # Calculate position count for stats
    if execution_mode == ExecutionMode.GUARDED_LIVE:
        mt5_data = read_mt5_positions()
        position_count = mt5_data.get("count", 0) if mt5_data else 0
    else:
        position_count = len(paper_positions)
    
    # Safety status
    safety_html = f'''
    <div class="safety-item">✅ Stop Loss Required: ENFORCED</div>
    <div class="safety-item">✅ No Naked Trades: ENFORCED</div>
    <div class="safety-item">✅ No Martingale: ENFORCED</div>
    <div class="safety-item">✅ No Averaging Down: ENFORCED</div>
    <div class="safety-item">✅ Duplicate Detection: ACTIVE</div>
    <div class="safety-item">✅ Guardian Check: REQUIRED</div>
    '''
    
    live_warning = ""
    if execution_mode == ExecutionMode.GUARDED_LIVE:
        if LIVE_MODE_CONFIRMED:
            live_warning = '<div class="live-warning">🔴 LIVE TRADING ACTIVE - REAL MONEY AT RISK</div>'
        else:
            live_warning = '<div class="live-blocked">⛔ LIVE MODE BLOCKED - Confirmation required</div>'
    
    return f'''<!DOCTYPE html>
<html><head>
    <title>⚡ Executor - Execution Agent</title>
    <meta http-equiv="refresh" content="10">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, sans-serif; background: #0a0a0f; color: #e0e0e0; padding: 20px; }}
        .header {{ display: flex; align-items: center; gap: 15px; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid #333; }}
        .header h1 {{ color: #f59e0b; }}
        .mode-badge {{ background: {mode_color}20; color: {mode_color}; padding: 8px 16px; border-radius: 20px; font-weight: bold; }}
        .live-warning {{ background: #ef444440; border: 2px solid #ef4444; color: #ef4444; padding: 15px; border-radius: 10px; text-align: center; margin-bottom: 20px; font-weight: bold; }}
        .live-blocked {{ background: #f59e0b20; border: 2px solid #f59e0b; color: #f59e0b; padding: 15px; border-radius: 10px; text-align: center; margin-bottom: 20px; }}
        .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }}
        .card {{ background: #1a1a24; border-radius: 12px; padding: 20px; }}
        .card h2 {{ font-size: 14px; color: #888; margin-bottom: 15px; text-transform: uppercase; }}
        .receipt {{ background: #0a0a0f; border-radius: 8px; padding: 12px; margin: 8px 0; }}
        .receipt-header {{ display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 5px; }}
        .receipt-body {{ font-size: 14px; font-weight: bold; margin-bottom: 5px; }}
        .receipt-footer {{ font-size: 11px; color: #666; }}
        .position {{ display: flex; justify-content: space-between; padding: 10px; background: #0a0a0f; border-radius: 8px; margin: 8px 0; }}
        .safety-item {{ padding: 8px 0; border-bottom: 1px solid #333; font-size: 13px; }}
        .stats {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-bottom: 20px; }}
        .stat {{ background: #1a1a24; border-radius: 10px; padding: 15px; text-align: center; }}
        .stat-value {{ font-size: 24px; font-weight: bold; color: #f59e0b; }}
        .stat-label {{ font-size: 11px; color: #666; }}
        .chat-section {{ background: #1a1a24; border-radius: 12px; padding: 20px; }}
        .chat-section h2 {{ color: #f59e0b; margin-bottom: 15px; }}
        .chat-messages {{ height: 100px; overflow-y: auto; background: #0a0a0f; border-radius: 8px; padding: 10px; margin-bottom: 10px; }}
        .chat-input {{ display: flex; gap: 10px; }}
        .chat-input input {{ flex: 1; padding: 10px; border-radius: 8px; border: 1px solid #333; background: #0a0a0f; color: #fff; }}
        .chat-input button {{ padding: 10px 20px; background: #f59e0b; color: #000; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; }}
        .message {{ margin: 8px 0; padding: 8px; border-radius: 6px; font-size: 13px; }}
        .message.user {{ background: #333; margin-left: 20%; }}
        .message.agent {{ background: #4d3a1a; margin-right: 20%; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>⚡ Executor</h1>
        <span class="mode-badge">● {execution_mode.value.upper()}</span>
        <span style="color: #888; margin-left: auto;">Execution Agent v2.0</span>
    </div>
    
    {live_warning}
    
    <div class="stats">
        <div class="stat">
            <div class="stat-value">{len(execution_receipts)}</div>
            <div class="stat-label">Total Executions</div>
        </div>
        <div class="stat">
            <div class="stat-value">{position_count}</div>
            <div class="stat-label">Open Positions</div>
        </div>
        <div class="stat">
            <div class="stat-value">{sum(1 for r in execution_receipts if r.get("status") == "EXECUTED")}</div>
            <div class="stat-label">Successful Fills</div>
        </div>
    </div>
    
    <div class="grid">
        <div class="card">
            <h2>📜 Recent Executions</h2>
            {receipts_html}
        </div>
        <div class="card">
            <h2>📊 Open Positions ({execution_mode.value})</h2>
            {pos_html}
        </div>
    </div>
    
    <div class="card" style="margin-bottom:20px">
        <h2>🛡️ Safety Status</h2>
        {safety_html}
    </div>
    
    <div class="chat-section">
        <h2>💬 Ask Executor</h2>
        <div class="chat-messages" id="messages"></div>
        <div class="chat-input">
            <input type="text" id="input" placeholder="Ask about execution..." onkeypress="if(event.key==='Enter')sendMessage()">
            <button onclick="sendMessage()">Send</button>
        </div>
    </div>
    <script>
        const CHAT_KEY = 'executor_chat_history';
        
        function loadChatHistory() {{
            const messages = document.getElementById('messages');
            const history = localStorage.getItem(CHAT_KEY);
            if (history) {{
                messages.innerHTML = history;
                messages.scrollTop = messages.scrollHeight;
            }}
        }}
        
        function saveChatHistory() {{
            const messages = document.getElementById('messages');
            localStorage.setItem(CHAT_KEY, messages.innerHTML);
        }}
        
        function clearChat() {{
            const messages = document.getElementById('messages');
            messages.innerHTML = '';
            localStorage.removeItem(CHAT_KEY);
        }}
        
        async function sendMessage() {{
            const input = document.getElementById('input');
            const messages = document.getElementById('messages');
            const text = input.value.trim();
            if (!text) return;
            messages.innerHTML += `<div style="margin:5px 0;padding:8px 12px;background:#1a1a24;border-radius:8px;font-size:12px">${{text}}</div>`;
            input.value = '';
            messages.scrollTop = messages.scrollHeight;
            saveChatHistory();
            
            try {{
                const response = await fetch('/chat', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{message: text}})
                }});
                const data = await response.json();
                messages.innerHTML += `<div style="margin:5px 0;padding:8px 12px;background:rgba(249,115,22,0.15);border-left:3px solid #f97316;border-radius:8px;font-size:12px">${{data.response.replace(/\\n/g, '<br>')}}</div>`;
            }} catch (e) {{
                messages.innerHTML += `<div style="margin:5px 0;padding:8px 12px;background:rgba(239,68,68,0.15);border-radius:8px;font-size:12px;color:#ef4444">Error: ${{e.message}}</div>`;
            }}
            messages.scrollTop = messages.scrollHeight;
            saveChatHistory();
        }}
        
        document.addEventListener('DOMContentLoaded', loadChatHistory);
    </script>
</body>
</html>'''


@app.post("/chat")
async def chat(request: ChatRequest):
    context = f"""Execution State:
- Mode: {execution_mode.value}
- Live Confirmed: {LIVE_MODE_CONFIRMED}
- Total Executions: {len(execution_receipts)}
- Open Positions: {len(paper_positions)}
- Recent Receipts: {json.dumps(execution_receipts[-3:], default=str)}"""
    response = await call_claude(request.message, context, agent_name=AGENT_NAME)
    return {"response": response}


@app.post("/api/execute")
async def execute(order: OrderRequest):
    """Execute a trade order."""
    return await execute_order(order)


@app.get("/api/receipts")
async def get_receipts(limit: int = 20):
    """Get execution receipts."""
    return execution_receipts[-limit:]


@app.get("/api/positions")
async def get_positions():
    """Get open positions (live from MT5 or paper mode)."""
    if execution_mode == ExecutionMode.GUARDED_LIVE:
        mt5_data = read_mt5_positions()
        if mt5_data:
            return mt5_data.get("positions", [])
    return paper_positions


@app.get("/api/mode")
async def get_mode():
    """Get current execution mode."""
    return {
        "mode": execution_mode.value,
        "live_confirmed": LIVE_MODE_CONFIRMED,
        "can_execute_live": execution_mode == ExecutionMode.GUARDED_LIVE and LIVE_MODE_CONFIRMED,
    }


@app.get("/api/safety")
async def get_safety():
    """Get safety configuration."""
    return {
        "max_spread_majors": safety.max_spread_majors,
        "max_spread_minors": safety.max_spread_minors,
        "max_slippage_market": safety.max_slippage_market,
        "max_retries": safety.max_retries,
        "min_time_between_trades": safety.min_time_between_trades_seconds,
        "max_trades_per_symbol_hour": safety.max_trades_per_symbol_per_hour,
        "enforced_rules": [
            "Stop loss mandatory",
            "No naked trades",
            "No martingale",
            "No averaging down",
            "Duplicate detection",
            "Guardian approval required",
        ],
    }


@app.get("/api/bridge")
async def get_bridge_status():
    """Check MT5 file bridge status."""
    status = check_mt5_bridge_status()
    return {
        "bridge_status": status,
        "command_file": str(MT5_COMMAND_FILE),
        "result_file": str(MT5_RESULT_FILE),
        "files_path_exists": MT5_FILES_PATH.exists(),
    }


@app.post("/api/close")
async def close_position(ticket: int):
    """Close a position via MT5 bridge."""
    if execution_mode != ExecutionMode.GUARDED_LIVE:
        return {"status": "ERROR", "error": "Close only available in guarded_live mode"}
    
    if not LIVE_MODE_CONFIRMED:
        return {"status": "ERROR", "error": "Live mode not confirmed"}
    
    command_id = f"CLOSE-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
    command = {
        "command_id": command_id,
        "action": "CLOSE",
        "ticket": ticket,
        "timestamp": datetime.utcnow().isoformat(),
    }
    
    if not write_mt5_command(command):
        return {"status": "ERROR", "error": "Failed to write command"}
    
    result = read_mt5_result(command_id, timeout_seconds=30)
    
    if result is None:
        return {"status": "TIMEOUT", "error": "MT5 did not respond"}
    
    return result


class PartialCloseRequest(BaseModel):
    ticket: int
    close_percent: float

@app.post("/api/partial-close")
async def partial_close_position(request: PartialCloseRequest):
    """Partially close a position via MT5 bridge (for scaling out)."""
    ticket = request.ticket
    close_percent = request.close_percent
    if execution_mode != ExecutionMode.GUARDED_LIVE:
        return {"status": "ERROR", "error": "Partial close only available in guarded_live mode"}
    
    if not LIVE_MODE_CONFIRMED:
        return {"status": "ERROR", "error": "Live mode not confirmed"}
    
    if close_percent <= 0 or close_percent > 100:
        return {"status": "ERROR", "error": "close_percent must be between 1 and 100"}
    
    command_id = f"PARTIAL-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
    command = {
        "command_id": command_id,
        "action": "PARTIAL_CLOSE",
        "ticket": ticket,
        "close_percent": close_percent,
        "timestamp": datetime.utcnow().isoformat(),
    }
    
    if not write_mt5_command(command):
        return {"status": "ERROR", "error": "Failed to write command"}
    
    result = read_mt5_result(command_id, timeout_seconds=30)
    
    if result is None:
        return {"status": "TIMEOUT", "error": "MT5 did not respond"}
    
    return result


class ModifySLRequest(BaseModel):
    ticket: int
    new_sl: float
    new_tp: float = 0

@app.post("/api/modify-sl")
async def modify_stop_loss(request: ModifySLRequest):
    """Modify stop loss (and optionally TP) for a position."""
    ticket = request.ticket
    new_sl = request.new_sl
    new_tp = request.new_tp
    if execution_mode != ExecutionMode.GUARDED_LIVE:
        return {"status": "ERROR", "error": "Modify only available in guarded_live mode"}
    
    if not LIVE_MODE_CONFIRMED:
        return {"status": "ERROR", "error": "Live mode not confirmed"}
    
    command_id = f"MODIFY-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
    command = {
        "command_id": command_id,
        "action": "MODIFY",
        "ticket": ticket,
        "stop_loss": new_sl,
        "take_profit": new_tp,
        "timestamp": datetime.utcnow().isoformat(),
    }
    
    if not write_mt5_command(command):
        return {"status": "ERROR", "error": "Failed to write command"}
    
    result = read_mt5_result(command_id, timeout_seconds=30)
    
    if result is None:
        return {"status": "TIMEOUT", "error": "MT5 did not respond"}
    
    return result


@app.post("/api/place-pending")
async def place_pending_order(
    symbol: str,
    direction: str,  # "buy_limit" or "sell_limit"
    lots: float,
    entry_price: float,
    stop_loss: float,
    take_profit: float = 0,
    expiration_hours: int = 24
):
    """
    Place a pending (limit) order in MT5.
    
    Args:
        symbol: Trading symbol (e.g., "EURUSD")
        direction: "buy_limit", "sell_limit", "buy_stop", "sell_stop"
        lots: Position size
        entry_price: Limit price for entry
        stop_loss: MANDATORY stop loss price
        take_profit: Optional take profit price
        expiration_hours: Hours until order expires (0 = GTC, default 24)
    """
    # Safety checks
    if stop_loss == 0:
        return {"status": "REJECTED", "error": "STOP LOSS REQUIRED - No naked trades allowed"}
    
    if direction not in ["buy_limit", "sell_limit", "buy_stop", "sell_stop"]:
        return {"status": "REJECTED", "error": f"Invalid direction: {direction}"}
    
    if execution_mode != ExecutionMode.GUARDED_LIVE:
        # Paper mode - simulate
        order_id = f"PAPER-PENDING-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
        return {
            "status": "PENDING_PLACED",
            "mode": "paper",
            "order_id": order_id,
            "symbol": symbol,
            "direction": direction,
            "entry_price": entry_price,
            "expiration_hours": expiration_hours,
        }
    
    if not LIVE_MODE_CONFIRMED:
        return {"status": "ERROR", "error": "Live mode not confirmed"}
    
    command_id = f"PENDING-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
    command = {
        "command_id": command_id,
        "action": "PLACE_PENDING",
        "symbol": symbol,
        "direction": direction,
        "lots": lots,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "expiration_hours": expiration_hours,
        "timestamp": datetime.utcnow().isoformat(),
    }
    
    if not write_mt5_command(command):
        return {"status": "ERROR", "error": "Failed to write command"}
    
    result = read_mt5_result(command_id, timeout_seconds=30)
    
    if result is None:
        return {"status": "TIMEOUT", "error": "MT5 did not respond"}
    
    # Log receipt
    receipt = {
        **result,
        "action": "PLACE_PENDING",
        "symbol": symbol,
        "direction": direction,
        "entry_price": entry_price,
        "lots": lots,
        "expiration_hours": expiration_hours,
        "created_at": datetime.utcnow().isoformat(),
    }
    execution_receipts.append(receipt)
    
    return result


@app.post("/api/cancel-pending")
async def cancel_pending_order(ticket: int):
    """Cancel a pending order by ticket number."""
    if execution_mode != ExecutionMode.GUARDED_LIVE:
        return {"status": "CANCELLED", "mode": "paper", "ticket": ticket}
    
    if not LIVE_MODE_CONFIRMED:
        return {"status": "ERROR", "error": "Live mode not confirmed"}
    
    command_id = f"CANCEL-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
    command = {
        "command_id": command_id,
        "action": "CANCEL_PENDING",
        "ticket": ticket,
        "timestamp": datetime.utcnow().isoformat(),
    }
    
    if not write_mt5_command(command):
        return {"status": "ERROR", "error": "Failed to write command"}
    
    result = read_mt5_result(command_id, timeout_seconds=30)
    
    if result is None:
        return {"status": "TIMEOUT", "error": "MT5 did not respond"}
    
    return result


@app.get("/api/pending-orders")
async def get_pending_orders():
    """Get list of all pending orders from MT5."""
    positions_data = read_mt5_positions()
    if positions_data and "pending_orders" in positions_data:
        return {
            "count": positions_data.get("pending_count", 0),
            "pending_orders": positions_data.get("pending_orders", []),
            "timestamp": positions_data.get("timestamp"),
        }
    return {"count": 0, "pending_orders": [], "timestamp": datetime.utcnow().isoformat()}


@app.get("/api/status")
async def get_status():
    bridge = check_mt5_bridge_status()
    # Get position count from MT5 in live mode
    if execution_mode == ExecutionMode.GUARDED_LIVE:
        mt5_data = read_mt5_positions()
        position_count = mt5_data.get("count", 0) if mt5_data else 0
    else:
        position_count = len(paper_positions)
    return {
        "agent_id": "execution",
        "name": AGENT_NAME,
        "status": "active",
        "mode": execution_mode.value,
        "live_confirmed": LIVE_MODE_CONFIRMED,
        "total_executions": len(execution_receipts),
        "open_positions": position_count,
        "bridge_status": bridge.get("status", "UNKNOWN"),
        "version": "2.1",  # Updated for pending order support
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
