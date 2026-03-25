"""
Risk Manager Agent - Guardian
Position sizing, risk limits, exposure management, kill switches
HIGHEST AUTHORITY AFTER ORCHESTRATOR
"""

import os
import sys
import json
import asyncio
import httpx
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from enum import Enum
from dataclasses import dataclass, field

# Add shared module to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared import (
    call_claude,
    get_agent_url,
    fetch_json,
    post_json,
    FOREX_SYMBOLS,
    ChatRequest,
)
from pydantic import BaseModel

app = FastAPI(title="Guardian - Risk Manager Agent", version="2.0")

AGENT_NAME = "Guardian"
REGIME_URL = get_agent_url("compass")
ORCHESTRATOR_URL = get_agent_url("orchestrator")

# MT5 file bridge for reading live positions
MT5_FILES_PATH = Path(os.getenv("MT5_FILES_PATH", "/mt5files"))

SYMBOLS = FOREX_SYMBOLS


class TradeRequest(BaseModel):
    symbol: str
    direction: str  # "long" or "short"
    entry: float
    stop: float
    take_profit: Optional[float] = None
    requested_risk_pct: Optional[float] = None  # Override default
    confidence: Optional[float] = 0.7


class RiskMode(str, Enum):
    NORMAL = "normal"
    REDUCED = "reduced"
    DEFENSIVE = "defensive"
    HALTED = "halted"


# ═══════════════════════════════════════════════════════════════
# RISK CONFIGURATION
# ═══════════════════════════════════════════════════════════════

@dataclass
class RiskConfig:
    # Per-Trade Limits
    default_risk_pct: float = 0.25
    max_risk_pct: float = 0.50
    absolute_max_risk_pct: float = 1.00
    
    # Drawdown Limits
    max_daily_loss_pct: float = 2.0
    max_weekly_drawdown_pct: float = 4.0
    max_system_drawdown_pct: float = 8.0
    
    # Position Limits
    max_open_positions: int = 5
    max_positions_per_currency: int = 2
    max_correlated_exposure_pct: float = 1.5
    
    # Anti-Overtrading
    max_trades_per_day: int = 8
    min_minutes_between_trades: int = 15
    max_consecutive_losses: int = 3
    
    # Account (would come from broker API)
    equity: float = 10000.0
    
    # Risk Mode Thresholds
    reduced_mode_daily_loss: float = 1.0
    defensive_mode_weekly_loss: float = 3.0


# Global state
config = RiskConfig()
risk_mode = RiskMode.NORMAL
kill_switch_active = False
kill_switch_reason = ""

# Tracking
daily_pnl_pct: float = 0.0
weekly_pnl_pct: float = 0.0
system_drawdown_pct: float = 0.0
consecutive_losses: int = 0
trades_today: int = 0
last_trade_time: Optional[datetime] = None
open_positions: List[dict] = []
trade_history: List[dict] = []


def sync_positions_from_mt5():
    """Sync open_positions from MT5 file bridge."""
    global open_positions
    try:
        positions_file = MT5_FILES_PATH / "positions.json"
        if positions_file.exists():
            with open(positions_file, 'r') as f:
                data = json.load(f)
            # Map MT5 positions to Guardian format
            open_positions = []
            for pos in data.get("positions", []):
                open_positions.append({
                    "ticket": pos.get("ticket"),
                    "symbol": pos.get("symbol", "").replace(".s", "").replace(".S", ""),
                    "direction": pos.get("direction", "long"),
                    "volume": pos.get("volume", 0),
                    "entry": pos.get("open_price", 0),
                    "sl": pos.get("sl", 0),
                    "tp": pos.get("tp", 0),
                    "profit": pos.get("profit", 0),
                })
    except Exception as e:
        print(f"[Guardian] Error syncing positions: {e}")


# ═══════════════════════════════════════════════════════════════
# CORRELATION CLUSTERS
# ═══════════════════════════════════════════════════════════════

CORRELATION_CLUSTERS = {
    "EUR": ["EURUSD", "EURGBP", "EURJPY", "EURAUD", "AUDNZD"],
    "GBP": ["GBPUSD", "GBPJPY", "EURGBP"],
    "JPY": ["USDJPY", "EURJPY", "GBPJPY", "AUDJPY"],
    "AUD": ["AUDUSD", "AUDNZD", "EURAUD", "AUDJPY"],
    "USD": ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD"],
    "CHF": ["USDCHF", "EURCHF"],
    "CAD": ["USDCAD", "AUDCAD"],
    "NZD": ["AUDNZD", "NZDUSD"],
}

# Pip values per standard lot (approximate, USD account)
PIP_VALUES = {
    "EURUSD": 10.0, "GBPUSD": 10.0, "AUDUSD": 10.0, "NZDUSD": 10.0,
    "USDJPY": 9.0, "USDCHF": 10.5, "USDCAD": 7.5,
    "EURJPY": 9.0, "GBPJPY": 9.0, "AUDJPY": 9.0,
    "EURGBP": 12.5, "EURAUD": 7.5, "AUDNZD": 6.5,
    "GBPJPY": 9.0,
}


def get_currency_exposure(symbol: str, direction: str) -> Dict[str, str]:
    """Get currency exposure from a trade."""
    base = symbol[:3]
    quote = symbol[3:]
    
    if direction.lower() == "long":
        return {base: "long", quote: "short"}
    else:
        return {base: "short", quote: "long"}


def calculate_exposure_by_currency() -> Dict[str, float]:
    """Calculate current exposure per currency."""
    exposure = {c: 0.0 for c in ["EUR", "GBP", "USD", "JPY", "CHF", "CAD", "AUD", "NZD"]}
    
    for pos in open_positions:
        currencies = get_currency_exposure(pos["symbol"], pos["direction"])
        for curr, direction in currencies.items():
            if curr in exposure:
                risk = pos.get("risk_pct", 0.25)
                exposure[curr] += risk if direction == "long" else -risk
    
    return exposure


def get_correlated_exposure(symbol: str, new_risk_pct: float, direction: str) -> float:
    """Calculate total correlated exposure if trade is added."""
    base = symbol[:3]
    quote = symbol[3:]
    
    total = new_risk_pct
    
    for pos in open_positions:
        pos_base = pos["symbol"][:3]
        pos_quote = pos["symbol"][3:]
        
        # Same base currency
        if base == pos_base or base == pos_quote:
            total += pos.get("risk_pct", 0.25)
        # Same quote currency
        elif quote == pos_base or quote == pos_quote:
            total += pos.get("risk_pct", 0.25)
    
    return total


def calculate_risk_multiplier(regime: str, confidence: float) -> float:
    """Calculate risk multiplier based on regime and confidence."""
    # Regime multiplier
    regime_multipliers = {
        "trending": 1.0,
        "mean_reverting": 0.8,
        "range_bound": 0.8,
        "breakout_ready": 0.7,
        "event_driven": 0.5,
        "unstable_noisy": 0.0,  # No trading
        "low_vol_drift": 0.6,
        "high_vol_expansion": 0.5,
    }
    regime_mult = regime_multipliers.get(regime, 0.5)
    
    # Confidence multiplier (0.5 to 1.0)
    conf_mult = 0.5 + (confidence * 0.5)
    
    # Drawdown multiplier
    if system_drawdown_pct > 5:
        dd_mult = 0.5
    elif system_drawdown_pct > 3:
        dd_mult = 0.7
    elif system_drawdown_pct > 1:
        dd_mult = 0.85
    else:
        dd_mult = 1.0
    
    # Consecutive loss multiplier
    if consecutive_losses >= 3:
        loss_mult = 0.5
    elif consecutive_losses >= 2:
        loss_mult = 0.7
    elif consecutive_losses >= 1:
        loss_mult = 0.85
    else:
        loss_mult = 1.0
    
    return regime_mult * conf_mult * dd_mult * loss_mult


def update_risk_mode():
    """Update risk mode based on current state."""
    global risk_mode
    
    if kill_switch_active or system_drawdown_pct >= config.max_system_drawdown_pct:
        risk_mode = RiskMode.HALTED
    elif weekly_pnl_pct <= -config.defensive_mode_weekly_loss or consecutive_losses >= 3:
        risk_mode = RiskMode.DEFENSIVE
    elif daily_pnl_pct <= -config.reduced_mode_daily_loss or consecutive_losses >= 2:
        risk_mode = RiskMode.REDUCED
    else:
        risk_mode = RiskMode.NORMAL


def get_max_risk_for_mode() -> float:
    """Get maximum allowed risk for current mode."""
    mode_limits = {
        RiskMode.NORMAL: config.max_risk_pct,
        RiskMode.REDUCED: 0.25,
        RiskMode.DEFENSIVE: 0.15,
        RiskMode.HALTED: 0.0,
    }
    return mode_limits.get(risk_mode, 0.25)


def get_max_positions_for_mode() -> int:
    """Get maximum positions for current mode."""
    mode_limits = {
        RiskMode.NORMAL: config.max_open_positions,
        RiskMode.REDUCED: 3,
        RiskMode.DEFENSIVE: 2,
        RiskMode.HALTED: 0,
    }
    return mode_limits.get(risk_mode, 3)


async def fetch_regime(symbol: str) -> str:
    """Fetch regime from Compass using pooled client."""
    from shared import pooled_get
    try:
        result = await pooled_get(f"{REGIME_URL}/api/regime/{symbol}", timeout=5.0)
        if result:
            return result.get("primary_regime", "unknown")
    except:
        pass
    return "unknown"


def check_revenge_trading() -> tuple[bool, str]:
    """Check for revenge trading patterns."""
    if not last_trade_time:
        return True, "OK"
    
    minutes_since = (datetime.utcnow() - last_trade_time).total_seconds() / 60
    
    if minutes_since < config.min_minutes_between_trades:
        return False, f"Too soon ({minutes_since:.0f}m < {config.min_minutes_between_trades}m)"
    
    # Check if sizing up after loss
    if consecutive_losses > 0 and trade_history:
        last_trade = trade_history[-1]
        # Would need to track if they're requesting larger size
    
    return True, "OK"


def calculate_lot_size(risk_amount: float, stop_pips: float, symbol: str) -> float:
    """Calculate lot size from risk amount and stop distance."""
    pip_value = PIP_VALUES.get(symbol, 10.0)
    
    if stop_pips <= 0 or pip_value <= 0:
        return 0.0
    
    lots = risk_amount / (stop_pips * pip_value)
    
    # Round to 2 decimal places (0.01 lot minimum)
    lots = round(lots, 2)
    
    return max(0.01, lots)


async def evaluate_trade(request: TradeRequest) -> dict:
    """Evaluate a trade request against all risk rules."""
    checks = []
    
    # Update risk mode first
    update_risk_mode()
    
    # 1. Kill switch check
    if kill_switch_active:
        return {
            "approved": False,
            "reason": f"Kill switch active: {kill_switch_reason}",
            "checks": [{"check": "kill_switch", "passed": False, "message": kill_switch_reason}],
        }
    
    # 2. Risk mode check
    if risk_mode == RiskMode.HALTED:
        return {
            "approved": False,
            "reason": "Trading HALTED due to drawdown limits",
            "checks": [{"check": "risk_mode", "passed": False, "message": "Mode: HALTED"}],
        }
    
    # Calculate stop distance in pips
    if request.direction.lower() == "long":
        stop_pips = abs(request.entry - request.stop) * 10000
        if "JPY" in request.symbol:
            stop_pips = abs(request.entry - request.stop) * 100
    else:
        stop_pips = abs(request.stop - request.entry) * 10000
        if "JPY" in request.symbol:
            stop_pips = abs(request.stop - request.entry) * 100
    
    # 3. Validate stop distance
    # Minimum 1 pip for majors (tight scalping allowed), 1 pip absolute minimum
    min_stop_pips = 1.0 if "JPY" not in request.symbol else 1.0
    if stop_pips < min_stop_pips:
        checks.append({"check": "stop_distance", "passed": False, "message": f"Stop too tight ({stop_pips:.1f} pips < {min_stop_pips})"})
    elif stop_pips > 100:
        checks.append({"check": "stop_distance", "passed": False, "message": f"Stop too wide ({stop_pips:.1f} pips)"})
    else:
        checks.append({"check": "stop_distance", "passed": True, "message": f"Stop valid ({stop_pips:.1f} pips)"})
    
    # 4. Determine risk percentage
    requested_risk = request.requested_risk_pct or config.default_risk_pct
    max_allowed = get_max_risk_for_mode()
    
    if requested_risk > config.absolute_max_risk_pct:
        checks.append({"check": "absolute_max", "passed": False, "message": f"Risk {requested_risk}% > absolute max {config.absolute_max_risk_pct}%"})
    elif requested_risk > max_allowed:
        checks.append({"check": "mode_max", "passed": False, "message": f"Risk {requested_risk}% > mode max {max_allowed}% ({risk_mode.value})"})
    else:
        checks.append({"check": "risk_limit", "passed": True, "message": f"Risk {requested_risk}% ≤ {max_allowed}%"})
    
    # 5. Daily loss limit
    if daily_pnl_pct <= -config.max_daily_loss_pct:
        checks.append({"check": "daily_limit", "passed": False, "message": f"Daily loss {daily_pnl_pct:.2f}% hit limit"})
    else:
        checks.append({"check": "daily_limit", "passed": True, "message": f"Daily P/L: {daily_pnl_pct:+.2f}%"})
    
    # 6. Weekly drawdown
    if weekly_pnl_pct <= -config.max_weekly_drawdown_pct:
        checks.append({"check": "weekly_limit", "passed": False, "message": f"Weekly drawdown {weekly_pnl_pct:.2f}% hit limit"})
    else:
        checks.append({"check": "weekly_limit", "passed": True, "message": f"Weekly P/L: {weekly_pnl_pct:+.2f}%"})
    
    # 7. Position limit
    max_positions = get_max_positions_for_mode()
    if len(open_positions) >= max_positions:
        checks.append({"check": "position_limit", "passed": False, "message": f"Max positions {len(open_positions)}/{max_positions}"})
    else:
        checks.append({"check": "position_limit", "passed": True, "message": f"Positions: {len(open_positions)}/{max_positions}"})
    
    # 8. Correlated exposure
    corr_exposure = get_correlated_exposure(request.symbol, requested_risk, request.direction)
    if corr_exposure > config.max_correlated_exposure_pct:
        checks.append({"check": "correlation", "passed": False, "message": f"Correlated exposure {corr_exposure:.2f}% > {config.max_correlated_exposure_pct}%"})
    else:
        checks.append({"check": "correlation", "passed": True, "message": f"Correlated exposure: {corr_exposure:.2f}%"})
    
    # 9. Trades per day
    if trades_today >= config.max_trades_per_day:
        checks.append({"check": "daily_trades", "passed": False, "message": f"Max daily trades reached ({trades_today})"})
    else:
        checks.append({"check": "daily_trades", "passed": True, "message": f"Trades today: {trades_today}/{config.max_trades_per_day}"})
    
    # 10. Revenge trading check
    revenge_ok, revenge_msg = check_revenge_trading()
    checks.append({"check": "revenge_trading", "passed": revenge_ok, "message": revenge_msg})
    
    # 11. Regime check
    regime = await fetch_regime(request.symbol)
    regime_mult = calculate_risk_multiplier(regime, request.confidence or 0.7)
    if regime_mult == 0:
        checks.append({"check": "regime", "passed": False, "message": f"Regime {regime} blocks trading"})
    else:
        checks.append({"check": "regime", "passed": True, "message": f"Regime: {regime} ({regime_mult:.1f}x)"})
    
    # 12. Take profit validation
    if request.take_profit:
        if request.direction.lower() == "long":
            tp_pips = (request.take_profit - request.entry) * 10000
            if "JPY" in request.symbol:
                tp_pips = (request.take_profit - request.entry) * 100
        else:
            tp_pips = (request.entry - request.take_profit) * 10000
            if "JPY" in request.symbol:
                tp_pips = (request.entry - request.take_profit) * 100
        
        rr_ratio = tp_pips / stop_pips if stop_pips > 0 else 0
        if rr_ratio < 1.0:
            checks.append({"check": "take_profit", "passed": False, "message": f"R:R {rr_ratio:.1f}:1 < minimum 1:1"})
        else:
            checks.append({"check": "take_profit", "passed": True, "message": f"R:R {rr_ratio:.1f}:1"})
    
    # Determine approval
    failed_checks = [c for c in checks if not c["passed"]]
    approved = len(failed_checks) == 0
    
    # Calculate position sizing if approved
    lot_size = 0.0
    risk_amount = 0.0
    final_risk_pct = 0.0
    
    if approved:
        # Apply multipliers
        final_risk_pct = min(requested_risk, max_allowed) * regime_mult
        risk_amount = config.equity * (final_risk_pct / 100)
        lot_size = calculate_lot_size(risk_amount, stop_pips, request.symbol)
    
    # Currency exposure
    exposure = calculate_exposure_by_currency()
    currencies = get_currency_exposure(request.symbol, request.direction)
    
    return {
        "approved": approved,
        "reason": failed_checks[0]["message"] if failed_checks else "All checks passed",
        "checks": checks,
        "sizing": {
            "lot_size": lot_size,
            "risk_amount": round(risk_amount, 2),
            "risk_pct": round(final_risk_pct, 3),
            "stop_pips": round(stop_pips, 1),
        },
        "portfolio_impact": {
            "currencies_affected": currencies,
            "new_exposure": {k: round(v + (final_risk_pct if k in currencies else 0), 2) for k, v in exposure.items()},
            "positions_after": len(open_positions) + (1 if approved else 0),
            "correlated_exposure": round(corr_exposure, 2),
        },
        "current_state": {
            "risk_mode": risk_mode.value,
            "daily_pnl": round(daily_pnl_pct, 2),
            "weekly_pnl": round(weekly_pnl_pct, 2),
            "consecutive_losses": consecutive_losses,
            "regime": regime,
        },
        "request": {
            "symbol": request.symbol,
            "direction": request.direction,
            "entry": request.entry,
            "stop": request.stop,
            "take_profit": request.take_profit,
        },
        "timestamp": datetime.utcnow().isoformat(),
    }


async def send_to_orchestrator(evaluation: dict):
    """Send risk decision to Orchestrator using shared post_json."""
    output_type = "approval" if evaluation["approved"] else "veto"
    await post_json(
        f"{ORCHESTRATOR_URL}/api/ingest",
        {
            "agent_id": "risk",
            "agent_name": AGENT_NAME,
            "output_type": output_type,
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "symbol": evaluation["request"]["symbol"],
                "approved": evaluation["approved"],
                "reason": evaluation["reason"],
                "lot_size": evaluation["sizing"]["lot_size"],
                "risk_pct": evaluation["sizing"]["risk_pct"],
            },
        }
    )


# Using shared call_claude - removed duplicate implementation


@app.on_event("startup")
async def startup():
    print(f"🚀 {AGENT_NAME} (Risk Manager Agent) v2.0 starting...")
    print(f"   Risk Mode: {risk_mode.value}")
    print(f"   Max Risk/Trade: {config.max_risk_pct}%")
    print(f"   Absolute Max: {config.absolute_max_risk_pct}%")


@app.get("/", response_class=HTMLResponse)
async def home():
    sync_positions_from_mt5()  # Sync live positions from MT5
    update_risk_mode()
    
    mode_colors = {
        RiskMode.NORMAL: "#22c55e",
        RiskMode.REDUCED: "#f59e0b",
        RiskMode.DEFENSIVE: "#f97316",
        RiskMode.HALTED: "#ef4444",
    }
    mode_color = mode_colors.get(risk_mode, "#888")
    
    # Position cards
    pos_html = ""
    if open_positions:
        for pos in open_positions:
            pos_html += f'''
            <div class="position">
                <span>{pos["symbol"]}</span>
                <span>{pos["direction"].upper()}</span>
                <span>{pos.get("risk_pct", 0.25)}%</span>
            </div>
            '''
    else:
        pos_html = '<div style="color:#666">No open positions</div>'
    
    # Exposure by currency
    exposure = calculate_exposure_by_currency()
    exp_html = ""
    for curr, exp in exposure.items():
        if abs(exp) > 0.01:
            color = "#22c55e" if exp > 0 else "#ef4444"
            exp_html += f'<div class="exp-item"><span>{curr}</span><span style="color:{color}">{exp:+.2f}%</span></div>'
    if not exp_html:
        exp_html = '<div style="color:#666">No exposure</div>'
    
    return f'''<!DOCTYPE html>
<html><head>
    <title>🛡️ Guardian - Risk Agent</title>
    <meta http-equiv="refresh" content="10">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, sans-serif; background: #0a0a0f; color: #e0e0e0; padding: 20px; }}
        .header {{ display: flex; align-items: center; gap: 15px; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid #333; }}
        .header h1 {{ color: #ef4444; }}
        .mode-badge {{ background: {mode_color}20; color: {mode_color}; padding: 8px 16px; border-radius: 20px; font-weight: bold; }}
        .grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-bottom: 20px; }}
        .card {{ background: #1a1a24; border-radius: 12px; padding: 20px; }}
        .card h3 {{ color: #888; font-size: 12px; margin-bottom: 10px; text-transform: uppercase; }}
        .stat {{ font-size: 28px; font-weight: bold; margin-bottom: 5px; }}
        .stat.green {{ color: #22c55e; }}
        .stat.red {{ color: #ef4444; }}
        .stat.yellow {{ color: #f59e0b; }}
        .limit {{ font-size: 12px; color: #666; }}
        .positions {{ background: #1a1a24; border-radius: 12px; padding: 20px; margin-bottom: 20px; }}
        .positions h2 {{ color: #ef4444; margin-bottom: 15px; }}
        .position {{ display: flex; justify-content: space-between; padding: 10px; background: #0a0a0f; border-radius: 8px; margin: 8px 0; }}
        .exposure {{ background: #1a1a24; border-radius: 12px; padding: 20px; margin-bottom: 20px; }}
        .exposure h2 {{ color: #f59e0b; margin-bottom: 15px; }}
        .exp-item {{ display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #333; }}
        .limits {{ background: #1a1a24; border-radius: 12px; padding: 20px; margin-bottom: 20px; }}
        .limits h2 {{ color: #3b82f6; margin-bottom: 15px; }}
        .limit-row {{ display: flex; justify-content: space-between; padding: 8px 0; font-size: 14px; }}
        .chat-section {{ background: #1a1a24; border-radius: 12px; padding: 20px; }}
        .chat-section h2 {{ color: #ef4444; margin-bottom: 15px; }}
        .chat-messages {{ height: 120px; overflow-y: auto; background: #0a0a0f; border-radius: 8px; padding: 10px; margin-bottom: 10px; }}
        .chat-input {{ display: flex; gap: 10px; }}
        .chat-input input {{ flex: 1; padding: 10px; border-radius: 8px; border: 1px solid #333; background: #0a0a0f; color: #fff; }}
        .chat-input button {{ padding: 10px 20px; background: #ef4444; color: #fff; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; }}
        .kill-switch {{ background: {"#ef444440" if kill_switch_active else "#1a1a24"}; border: 2px solid {"#ef4444" if kill_switch_active else "transparent"}; border-radius: 12px; padding: 15px; margin-bottom: 20px; text-align: center; }}
        .message {{ margin: 8px 0; padding: 8px; border-radius: 6px; font-size: 13px; }}
        .message.user {{ background: #333; margin-left: 20%; }}
        .message.agent {{ background: #4d1a1a; margin-right: 20%; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🛡️ Guardian</h1>
        <span class="mode-badge">● {risk_mode.value.upper()}</span>
        <span style="color: #888; margin-left: auto;">Risk Manager Agent v2.0</span>
    </div>
    
    <div class="kill-switch">
        {"⚠️ KILL SWITCH ACTIVE: " + kill_switch_reason if kill_switch_active else "✅ Kill Switch: OFF"}
    </div>
    
    <div class="grid">
        <div class="card">
            <h3>Daily P/L</h3>
            <div class="stat {'green' if daily_pnl_pct >= 0 else 'red'}">{daily_pnl_pct:+.2f}%</div>
            <div class="limit">Limit: -{config.max_daily_loss_pct}%</div>
        </div>
        <div class="card">
            <h3>Weekly P/L</h3>
            <div class="stat {'green' if weekly_pnl_pct >= 0 else 'red'}">{weekly_pnl_pct:+.2f}%</div>
            <div class="limit">Limit: -{config.max_weekly_drawdown_pct}%</div>
        </div>
        <div class="card">
            <h3>System Drawdown</h3>
            <div class="stat {'green' if system_drawdown_pct < 3 else 'yellow' if system_drawdown_pct < 6 else 'red'}">{system_drawdown_pct:.2f}%</div>
            <div class="limit">HALT at: {config.max_system_drawdown_pct}%</div>
        </div>
    </div>
    
    <div class="grid">
        <div class="card">
            <h3>Open Positions</h3>
            <div class="stat">{len(open_positions)}/{get_max_positions_for_mode()}</div>
        </div>
        <div class="card">
            <h3>Consecutive Losses</h3>
            <div class="stat {'red' if consecutive_losses >= 3 else 'yellow' if consecutive_losses >= 2 else 'green'}">{consecutive_losses}</div>
            <div class="limit">Limit: {config.max_consecutive_losses}</div>
        </div>
        <div class="card">
            <h3>Trades Today</h3>
            <div class="stat">{trades_today}/{config.max_trades_per_day}</div>
        </div>
    </div>
    
    <div class="grid" style="grid-template-columns: 1fr 1fr;">
        <div class="positions">
            <h2>📊 Open Positions</h2>
            {pos_html}
        </div>
        <div class="exposure">
            <h2>💱 Currency Exposure</h2>
            {exp_html}
        </div>
    </div>
    
    <div class="limits">
        <h2>⚙️ Current Limits ({risk_mode.value.upper()} mode)</h2>
        <div class="limit-row"><span>Max Risk/Trade:</span><span>{get_max_risk_for_mode()}%</span></div>
        <div class="limit-row"><span>Absolute Max:</span><span>{config.absolute_max_risk_pct}%</span></div>
        <div class="limit-row"><span>Max Positions:</span><span>{get_max_positions_for_mode()}</span></div>
        <div class="limit-row"><span>Max Correlated:</span><span>{config.max_correlated_exposure_pct}%</span></div>
    </div>
    
    <div class="chat-section">
        <h2>💬 Ask Guardian</h2>
        <div class="chat-messages" id="messages"></div>
        <div class="chat-input">
            <input type="text" id="input" placeholder="Ask about risk..." onkeypress="if(event.key==='Enter')sendMessage()">
            <button onclick="sendMessage()">Send</button>
            <button onclick="clearChat()" style="background: #666;">Clear</button>
        </div>
    </div>
    <script>
        const CHAT_KEY = 'guardian_chat_history';
        
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
    context = f"""Risk State:
- Mode: {risk_mode.value}
- Daily P/L: {daily_pnl_pct}%
- Weekly P/L: {weekly_pnl_pct}%
- System Drawdown: {system_drawdown_pct}%
- Consecutive Losses: {consecutive_losses}
- Open Positions: {len(open_positions)}
- Kill Switch: {kill_switch_active}
- Config: {json.dumps(config.__dict__)}"""
    response = await call_claude(request.message, context, agent_name=AGENT_NAME)
    return {"response": response}


@app.post("/api/evaluate")
async def evaluate(request: TradeRequest):
    """Evaluate a trade request."""
    evaluation = await evaluate_trade(request)
    await send_to_orchestrator(evaluation)
    return evaluation


@app.post("/api/kill-switch")
async def toggle_kill_switch(reason: str = "Manual activation"):
    """Toggle kill switch."""
    global kill_switch_active, kill_switch_reason
    kill_switch_active = not kill_switch_active
    kill_switch_reason = reason if kill_switch_active else ""
    update_risk_mode()
    return {"kill_switch": kill_switch_active, "reason": kill_switch_reason, "mode": risk_mode.value}


@app.post("/api/record-trade")
async def record_trade(symbol: str, direction: str, risk_pct: float, pnl_pct: float = 0):
    """Record a completed trade result."""
    global daily_pnl_pct, weekly_pnl_pct, system_drawdown_pct, consecutive_losses, trades_today, last_trade_time
    
    # Update P/L
    daily_pnl_pct += pnl_pct
    weekly_pnl_pct += pnl_pct
    
    if pnl_pct < 0:
        system_drawdown_pct += abs(pnl_pct)
        consecutive_losses += 1
    else:
        consecutive_losses = 0
    
    trades_today += 1
    last_trade_time = datetime.utcnow()
    
    trade_history.append({
        "symbol": symbol,
        "direction": direction,
        "risk_pct": risk_pct,
        "pnl_pct": pnl_pct,
        "timestamp": datetime.utcnow().isoformat(),
    })
    
    update_risk_mode()
    
    return {"recorded": True, "mode": risk_mode.value}


@app.get("/api/status")
async def get_status():
    sync_positions_from_mt5()  # Sync live positions from MT5
    update_risk_mode()
    return {
        "agent_id": "risk",
        "name": AGENT_NAME,
        "status": "active",
        "risk_mode": risk_mode.value,
        "kill_switch": kill_switch_active,
        "daily_pnl": round(daily_pnl_pct, 2),
        "weekly_pnl": round(weekly_pnl_pct, 2),
        "system_drawdown": round(system_drawdown_pct, 2),
        "consecutive_losses": consecutive_losses,
        "open_positions": len(open_positions),
        "max_risk_allowed": get_max_risk_for_mode(),
        "version": "2.0",
    }


@app.get("/api/limits")
async def get_limits():
    """Get current risk limits."""
    return {
        "mode": risk_mode.value,
        "max_risk_per_trade": get_max_risk_for_mode(),
        "absolute_max": config.absolute_max_risk_pct,
        "max_positions": get_max_positions_for_mode(),
        "max_daily_loss": config.max_daily_loss_pct,
        "max_weekly_drawdown": config.max_weekly_drawdown_pct,
        "max_system_drawdown": config.max_system_drawdown_pct,
        "max_correlated_exposure": config.max_correlated_exposure_pct,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, access_log=False)
