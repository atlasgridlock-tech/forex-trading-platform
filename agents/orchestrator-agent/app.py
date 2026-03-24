"""
Orchestrator / CIO Agent - Nexus v3.0
Final decision authority with weighted confluence engine
Rich Trading Platform Dashboard
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(env_path)

import json
import asyncio
import httpx
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Union
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from enum import Enum

# Configure logging to suppress noisy HTTP logs
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# Import rich dashboard
try:
    from dashboard import get_dashboard_html
    RICH_DASHBOARD = True
except ImportError:
    RICH_DASHBOARD = False
    print("[Nexus] Rich dashboard not available, using basic")

# Import monitoring dashboard
try:
    from monitoring import get_monitoring_dashboard_html, get_message_stats, log_message
    MONITORING_AVAILABLE = True
except ImportError:
    MONITORING_AVAILABLE = False
    print("[Nexus] Monitoring dashboard not available")

app = FastAPI(title="Nexus - Orchestrator/CIO Agent", version="3.0")

# Import workflow routes
try:
    from workflows import get_workflow_api_routes, scheduler
    app.include_router(get_workflow_api_routes())
    WORKFLOWS_AVAILABLE = True
except ImportError:
    WORKFLOWS_AVAILABLE = False

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
AGENT_NAME = "Nexus"
WORKSPACE = Path("/app/workspace")

# Agent URLs
AGENT_URLS = {
    "curator": os.getenv("CURATOR_URL", "http://data-agent:8000"),
    "sentinel": os.getenv("SENTINEL_URL", "http://news-agent:8000"),
    "oracle": os.getenv("ORACLE_URL", "http://macro-agent:8000"),
    "atlas": os.getenv("ATLAS_URL", "http://technical-agent:8000"),
    "architect": os.getenv("ARCHITECT_URL", "http://structure-agent:8000"),
    "pulse": os.getenv("PULSE_URL", "http://sentiment-agent:8000"),
    "compass": os.getenv("COMPASS_URL", "http://regime-agent:8000"),
    "tactician": os.getenv("TACTICIAN_URL", "http://strategy-agent:8000"),
    "guardian": os.getenv("GUARDIAN_URL", "http://risk-agent:8000"),
    "balancer": os.getenv("BALANCER_URL", "http://portfolio-agent:8000"),
    "executor": os.getenv("EXECUTOR_URL", "http://execution-agent:8000"),
    "chronicle": os.getenv("CHRONICLE_URL", "http://journal-agent:8000"),
    "arbiter": os.getenv("ARBITER_URL", "http://governance-agent:8000"),
    "insight": os.getenv("ANALYTICS_URL", "http://analytics-agent:8000"),
}


class Decision(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    WATCHLIST = "WATCHLIST"
    NO_TRADE = "NO_TRADE"


class ChatRequest(BaseModel):
    message: str


class TradeCandidate(BaseModel):
    symbol: str
    direction: str  # "long" or "short"
    strategy: str
    entry_price: float
    stop_loss: float
    take_profit: float
    timeframe: str = "H4"


# Configuration (could be loaded from file)
CONFIG = {
    "confluence_weights": {
        "technical": 0.25,
        "structure": 0.20,
        "macro": 0.15,
        "sentiment": 0.10,
        "regime": 0.15,
        "risk_execution": 0.15,
    },
    "decision_thresholds": {
        "execute": 68,      # Lowered from 75 - March 2026
        "watchlist": 55,    # Lowered from 60 - March 2026
        "no_trade": 40,
    },
    "hard_gates": {
        "max_spread_major": 2.5,
        "max_spread_cross": 4.0,
        "min_data_quality": 70,
        "max_exposure_score": 80,
        "event_block_hours": 4,
    },
}

# ═══════════════════════════════════════════════════════════════
# AUTO-TRADING CONFIGURATION
# ═══════════════════════════════════════════════════════════════
AUTO_TRADE_ENABLED = os.getenv("AUTO_TRADE_ENABLED", "true").lower() == "true"
DEFAULT_LOT_SIZE = float(os.getenv("DEFAULT_LOT_SIZE", "0.01"))  # Fallback if risk calc fails
MAX_LOT_SIZE = float(os.getenv("MAX_LOT_SIZE", "0.5"))  # Safety cap
MIN_LOT_SIZE = float(os.getenv("MIN_LOT_SIZE", "0.01"))  # Minimum lot size

# Risk-based position sizing
RISK_PERCENT = float(os.getenv("RISK_PERCENT", "1.0"))  # Risk 1% of account per trade
USE_RISK_BASED_SIZING = os.getenv("USE_RISK_BASED_SIZING", "true").lower() == "true"

# Track executed signals to prevent duplicates
executed_signals: Dict[str, datetime] = {}
SIGNAL_COOLDOWN_MINUTES = 60  # Don't re-execute same signal within this window

# Cache for account balance
cached_account_balance: float = 0.0
last_balance_fetch: Optional[datetime] = None
BALANCE_CACHE_SECONDS = 30

# In-memory storage
decisions_log: List[dict] = []
watchlist: Dict[str, dict] = {}
agent_status: Dict[str, dict] = {}


async def fetch_agent_data(agent: str, endpoint: str, timeout: float = 5.0) -> Optional[dict]:
    """Fetch data from an agent using pooled HTTP client."""
    url = AGENT_URLS.get(agent)
    if not url:
        return None
    
    import time
    start_time = time.time()
    try:
        # Use pooled client for connection reuse
        from shared import pooled_get
        result = await pooled_get(f"{url}{endpoint}", timeout=timeout)
        latency = (time.time() - start_time) * 1000
        if result is not None:
            if MONITORING_AVAILABLE:
                log_message("nexus", agent, endpoint, "success", latency)
            return result
        else:
            if MONITORING_AVAILABLE:
                log_message("nexus", agent, endpoint, "error", latency)
    except Exception as e:
        latency = (time.time() - start_time) * 1000
        if MONITORING_AVAILABLE:
            log_message("nexus", agent, endpoint, "error", latency)
        print(f"Error fetching from {agent}: {e}")
    return None


async def post_to_agent(agent: str, endpoint: str, data: dict, timeout: float = 10.0) -> Optional[dict]:
    """Post data to an agent using pooled HTTP client."""
    url = AGENT_URLS.get(agent)
    if not url:
        return None
    
    import time
    start_time = time.time()
    try:
        # Use pooled client for connection reuse
        from shared import pooled_post
        result = await pooled_post(f"{url}{endpoint}", data, timeout=timeout)
        latency = (time.time() - start_time) * 1000
        if result is not None:
            if MONITORING_AVAILABLE:
                log_message("nexus", agent, f"POST {endpoint}", "success", latency)
            return result
        else:
            if MONITORING_AVAILABLE:
                log_message("nexus", agent, f"POST {endpoint}", "error", latency)
    except Exception as e:
        latency = (time.time() - start_time) * 1000
        if MONITORING_AVAILABLE:
            log_message("nexus", agent, f"POST {endpoint}", "error", latency)
        print(f"Error posting to {agent}: {e}")
    return None


async def get_account_balance() -> float:
    """Fetch account balance from Data Agent with caching."""
    global cached_account_balance, last_balance_fetch
    
    now = datetime.utcnow()
    
    # Use cached value if fresh enough
    if last_balance_fetch and (now - last_balance_fetch).total_seconds() < BALANCE_CACHE_SECONDS:
        return cached_account_balance
    
    # Fetch from Data Agent
    account_data = await fetch_agent_data("curator", "/api/account")
    
    if account_data and account_data.get("balance"):
        cached_account_balance = float(account_data["balance"])
        last_balance_fetch = now
        return cached_account_balance
    
    # Return cached value or default
    return cached_account_balance if cached_account_balance > 0 else 10000.0  # Default fallback


async def calculate_position_size(
    symbol: str,
    entry_price: float,
    stop_loss: float,
) -> tuple[float, dict]:
    """
    Calculate position size based on risk percentage.
    Returns (lot_size, calculation_details).
    """
    from shared import calculate_lot_size, calculate_stop_loss_pips, pip_value_per_lot
    
    details = {
        "method": "fixed" if not USE_RISK_BASED_SIZING else "risk_based",
        "risk_percent": RISK_PERCENT,
    }
    
    if not USE_RISK_BASED_SIZING:
        return DEFAULT_LOT_SIZE, details
    
    # Get account balance
    balance = await get_account_balance()
    details["account_balance"] = balance
    
    # Calculate stop loss in pips
    sl_pips = calculate_stop_loss_pips(entry_price, stop_loss, symbol)
    details["stop_loss_pips"] = round(sl_pips, 1)
    
    if sl_pips <= 0:
        details["error"] = "Invalid stop loss distance"
        return DEFAULT_LOT_SIZE, details
    
    # Calculate lot size
    lot_size = calculate_lot_size(
        account_balance=balance,
        risk_percent=RISK_PERCENT,
        stop_loss_pips=sl_pips,
        symbol=symbol,
        min_lot=MIN_LOT_SIZE,
        max_lot=MAX_LOT_SIZE,
    )
    
    details["calculated_lot_size"] = lot_size
    details["pip_value_per_lot"] = pip_value_per_lot(symbol)
    details["risk_amount"] = round(balance * (RISK_PERCENT / 100), 2)
    
    return lot_size, details


async def route_to_executor(
    symbol: str,
    direction: str,  # "long" or "short"
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    strategy: str,
    confidence: int,
) -> Optional[dict]:
    """
    Route a qualified trade signal to the Execution Agent.
    Returns execution receipt or None if failed/blocked.
    """
    global executed_signals
    
    if not AUTO_TRADE_ENABLED:
        print(f"[Nexus] ⚠️ Auto-trade DISABLED - would execute {direction.upper()} {symbol}")
        return None
    
    # Check signal cooldown (prevent duplicate executions)
    signal_key = f"{symbol}_{direction}"
    now = datetime.utcnow()
    
    if signal_key in executed_signals:
        last_exec = executed_signals[signal_key]
        minutes_since = (now - last_exec).total_seconds() / 60
        if minutes_since < SIGNAL_COOLDOWN_MINUTES:
            print(f"[Nexus] ⏳ Signal cooldown: {symbol} {direction} executed {minutes_since:.0f}m ago")
            return None
    
    # Calculate lot size using risk-based sizing
    lot_size, size_details = await calculate_position_size(symbol, entry_price, stop_loss)
    
    # Build order request
    order = {
        "symbol": symbol,
        "direction": direction,
        "lot_size": lot_size,
        "entry_price": entry_price,  # None for market order
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "comment": f"Nexus|{strategy}|{confidence}%",
    }
    
    # Log with sizing details
    sizing_info = f"Risk: {size_details.get('risk_percent', '?')}% of ${size_details.get('account_balance', '?'):,.0f}" if USE_RISK_BASED_SIZING else "Fixed size"
    print(f"[Nexus] 🚀 AUTO-EXECUTING: {direction.upper()} {symbol} @ {entry_price or 'MARKET'}")
    print(f"        SL: {stop_loss} ({size_details.get('stop_loss_pips', '?')} pips) | TP: {take_profit}")
    print(f"        Size: {lot_size} lots ({sizing_info})")
    
    # Send to Executor
    result = await post_to_agent("executor", "/api/execute", order, timeout=30.0)
    
    if result:
        status = result.get("status", "UNKNOWN")
        if status == "EXECUTED":
            print(f"[Nexus] ✅ ORDER FILLED: {result.get('order_id')} - Health: {result.get('health_score', 0)}/100")
            executed_signals[signal_key] = now
            # Add sizing details to result
            result["position_sizing"] = size_details
        elif status == "REJECTED":
            print(f"[Nexus] ❌ ORDER REJECTED: {result.get('reason', 'Unknown')}")
        else:
            print(f"[Nexus] ⚠️ ORDER STATUS: {status} - {result.get('error', result.get('reason', ''))}")
        return result
    else:
        print(f"[Nexus] ❌ Failed to reach Executor agent")
        return None


async def check_hard_gates(symbol: str, direction: str, strategy: str, stop_loss: float) -> Tuple[bool, List[dict]]:
    """Check all hard gates. Returns (all_passed, gate_results)."""
    gates = []
    all_passed = True
    
    # 1. Event Risk (Sentinel)
    sentinel_data = await fetch_agent_data("sentinel", f"/api/risk/{symbol}")
    if sentinel_data:
        # Sentinel uses "mode" not "trading_mode"
        trading_mode = sentinel_data.get("mode", sentinel_data.get("trading_mode", "normal")).upper()
        blocked = sentinel_data.get("blocked", False)
        event_risk = trading_mode != "PAUSE" and not blocked
        gates.append({
            "gate": "Event Risk",
            "passed": event_risk,
            "value": f"{trading_mode} (blocked: {blocked})",
            "threshold": "!= PAUSE and not blocked",
            "source": "Sentinel",
        })
        if not event_risk:
            all_passed = False
    else:
        gates.append({"gate": "Event Risk", "passed": True, "value": "No data", "source": "Sentinel"})
    
    # 2. Spread (Curator)
    curator_data = await fetch_agent_data("curator", f"/api/snapshot/spread/{symbol}")
    if curator_data:
        # API returns current_spread, not spread_pips
        spread = curator_data.get("current_spread", curator_data.get("spread_pips", 0))
        max_spread = CONFIG["hard_gates"]["max_spread_major"] if "JPY" not in symbol else CONFIG["hard_gates"]["max_spread_cross"]
        spread_ok = spread <= max_spread
        gates.append({
            "gate": "Spread",
            "passed": spread_ok,
            "value": f"{spread:.1f} pips",
            "threshold": f"<= {max_spread}",
            "source": "Curator",
        })
        if not spread_ok:
            all_passed = False
    else:
        gates.append({"gate": "Spread", "passed": True, "value": "No data", "source": "Curator"})
    
    # 3. Stop Logic (only fail if this is a real trade evaluation, not just confluence check)
    if stop_loss is not None and stop_loss > 0:
        # Real trade evaluation - stop is defined ✓
        gates.append({
            "gate": "Stop Defined",
            "passed": True,
            "value": f"{stop_loss:.5f}",
            "threshold": "Must be defined",
            "source": "Input",
        })
    elif stop_loss == 0:
        # Confluence check only - skip this gate (N/A)
        gates.append({
            "gate": "Stop Defined",
            "passed": True,
            "value": "N/A (confluence check)",
            "threshold": "Must be defined for trades",
            "source": "Input",
        })
    else:
        # Real trade without stop - FAIL
        gates.append({
            "gate": "Stop Defined",
            "passed": False,
            "value": "None",
            "threshold": "Must be defined",
            "source": "Input",
        })
        all_passed = False
    
    # 4. Regime Match (Compass)
    compass_data = await fetch_agent_data("compass", f"/api/regime/{symbol}")
    if compass_data:
        regime = compass_data.get("primary_regime", compass_data.get("regime", "unknown"))
        compatible = compass_data.get("recommended_strategies", compass_data.get("strategy_families", []))
        
        # Check if strategy is compatible with regime
        strategy_base = strategy.split("-")[0].upper() if strategy else ""
        regime_match = any(s.upper() in strategy_base or strategy_base in s.upper() for s in compatible)
        
        gates.append({
            "gate": "Regime Match",
            "passed": regime_match,
            "value": f"{regime} (compatible: {', '.join(compatible[:3])})",
            "threshold": "Strategy in compatible list",
            "source": "Compass",
        })
        if not regime_match:
            all_passed = False
    else:
        gates.append({"gate": "Regime Match", "passed": True, "value": "No data", "source": "Compass"})
    
    # 4b. Regime/Structure Alignment (Compass vs Architect must agree)
    architect_data = await fetch_agent_data("architect", f"/api/structure/{symbol}")
    if compass_data and architect_data:
        compass_regime = compass_data.get("primary_regime", "unknown").lower()
        architect_regime = architect_data.get("structure_state", architect_data.get("market_structure", "unknown")).lower()
        
        # Map structure descriptions to regime types
        structure_to_regime = {
            "trending": ["trending", "bullish", "bearish", "directional"],
            "ranging": ["ranging", "range", "consolidating", "sideways", "neutral"],
            "breakout": ["breakout", "breakout_ready", "breaking"],
        }
        
        # Check alignment
        aligned = False
        compass_type = None
        architect_type = None
        
        for regime_type, keywords in structure_to_regime.items():
            if any(k in compass_regime for k in keywords):
                compass_type = regime_type
            if any(k in architect_regime for k in keywords):
                architect_type = regime_type
        
        aligned = compass_type == architect_type or compass_type is None or architect_type is None
        
        gates.append({
            "gate": "Regime/Structure Align",
            "passed": aligned,
            "value": f"Compass: {compass_regime}, Architect: {architect_regime}",
            "threshold": "Both agents agree on regime type",
            "source": "Compass + Architect",
        })
        if not aligned:
            all_passed = False
    
    # 5. Data Quality (Curator)
    quality_data = await fetch_agent_data("curator", f"/api/quality/{symbol}")
    if quality_data:
        # Curator returns 0-1 scale, convert to 0-100
        quality_raw = quality_data.get("overall", 0.7)
        quality = quality_raw * 100 if quality_raw <= 1 else quality_raw
        quality_ok = quality >= CONFIG["hard_gates"]["min_data_quality"]
        gates.append({
            "gate": "Data Quality",
            "passed": quality_ok,
            "value": f"{quality:.0f}/100",
            "threshold": f">= {CONFIG['hard_gates']['min_data_quality']}",
            "source": "Curator",
        })
        if not quality_ok:
            all_passed = False
    else:
        gates.append({"gate": "Data Quality", "passed": True, "value": "No data", "source": "Curator"})
    
    # 6. Portfolio Exposure (Balancer)
    balancer_data = await fetch_agent_data("balancer", "/api/exposure")
    if balancer_data:
        exposure_score = balancer_data.get("exposure_score", 0)
        exposure_ok = exposure_score < CONFIG["hard_gates"]["max_exposure_score"]
        gates.append({
            "gate": "Portfolio Exposure",
            "passed": exposure_ok,
            "value": f"{exposure_score}/100",
            "threshold": f"< {CONFIG['hard_gates']['max_exposure_score']}",
            "source": "Balancer",
        })
        if not exposure_ok:
            all_passed = False
    else:
        gates.append({"gate": "Portfolio Exposure", "passed": True, "value": "No data", "source": "Balancer"})
    
    # 7. Guardian Approval
    guardian_data = await fetch_agent_data("guardian", "/api/status")
    if guardian_data:
        risk_mode = guardian_data.get("mode", "normal")
        guardian_ok = risk_mode not in ["halted"]
        gates.append({
            "gate": "Guardian Mode",
            "passed": guardian_ok,
            "value": risk_mode,
            "threshold": "!= halted",
            "source": "Guardian",
        })
        if not guardian_ok:
            all_passed = False
    else:
        gates.append({"gate": "Guardian Mode", "passed": True, "value": "No data", "source": "Guardian"})
    
    # 8. Model Version (Arbiter)
    arbiter_data = await fetch_agent_data("arbiter", f"/api/versions/{strategy.split('-v')[0] if '-v' in strategy else strategy}")
    if arbiter_data and arbiter_data.get("current"):
        version_status = arbiter_data["current"].get("status", "unknown")
        version_ok = version_status == "active"
        gates.append({
            "gate": "Model Version",
            "passed": version_ok,
            "value": f"{arbiter_data['current'].get('version', 'unknown')} ({version_status})",
            "threshold": "status = active",
            "source": "Arbiter",
        })
        if not version_ok:
            all_passed = False
    else:
        gates.append({"gate": "Model Version", "passed": True, "value": "Not versioned", "source": "Arbiter"})
    
    return all_passed, gates


async def calculate_confluence_score(symbol: str, direction: str, strategy: str, log_inputs: bool = False) -> Tuple[int, Dict[str, dict]]:
    """Calculate weighted confluence score across all categories.
    
    Args:
        symbol: Trading pair
        direction: "long" or "short"
        strategy: Strategy identifier
        log_inputs: If True, print raw agent data for debugging score discrepancies
    """
    scores = {}
    weights = CONFIG["confluence_weights"]
    
    # 1. Technical Alignment (25%) - from Atlas Jr.
    technical_data = await fetch_agent_data("atlas", f"/api/analysis/{symbol}")
    tech_score = 0
    tech_max = 25
    tech_details = []
    
    if technical_data:
        trend_grade = technical_data.get("trend_grade", "D")
        # Atlas Jr. uses "directional_lean" not "trend_direction"
        trend_direction = technical_data.get("directional_lean", technical_data.get("trend_direction", "neutral"))
        # Atlas Jr. uses "mtf_alignment" (string) not "mtf_aligned" (boolean)
        mtf_alignment = technical_data.get("mtf_alignment", "")
        mtf_aligned = "BULLISH" in mtf_alignment.upper() or "BEARISH" in mtf_alignment.upper()
        
        if log_inputs:
            print(f"   [DEBUG] Atlas data: grade={trend_grade}, direction={trend_direction}, mtf={mtf_alignment}")
        
        # Base score by grade
        grade_scores = {"A": 15, "B": 12, "C": 8, "D": 4, "F": 0}
        tech_score += grade_scores.get(trend_grade, 0)
        tech_details.append(f"Grade {trend_grade}")
        
        # Direction alignment
        dir_match = (direction == "long" and trend_direction == "bullish") or \
                    (direction == "short" and trend_direction == "bearish")
        if dir_match:
            tech_score += 5
            tech_details.append("Direction aligned")
        
        # MTF alignment
        if mtf_aligned:
            tech_score += 5
            tech_details.append(f"MTF {mtf_alignment}")
    else:
        tech_score = 15  # Default to moderate if no data
        tech_details.append("No data (default)")
    
    scores["technical"] = {
        "score": min(tech_score, tech_max),
        "max": tech_max,
        "weight": weights["technical"],
        "details": ", ".join(tech_details),
    }
    
    # 2. Market Structure (20%) - from Architect
    # Strip broker suffix for Architect (stores without suffix)
    clean_symbol = symbol.replace(".s", "").replace(".S", "")
    structure_data = await fetch_agent_data("architect", f"/api/structure/{clean_symbol}")
    struct_score = 0
    struct_max = 20
    struct_details = []
    
    if structure_data:
        structural_bias = structure_data.get("structural_bias", "neutral")
        current_price = structure_data.get("current_price", 0)
        key_zones = structure_data.get("key_zones", [])
        fvgs = structure_data.get("fvgs", [])
        
        # Structure alignment with direction
        if (direction == "long" and structural_bias == "bullish") or \
           (direction == "short" and structural_bias == "bearish"):
            struct_score += 8
            struct_details.append(f"Structure {structural_bias}")
        elif structural_bias == "neutral":
            struct_score += 4
            struct_details.append("Structure neutral")
        else:
            struct_details.append(f"Structure {structural_bias} (counter)")
        
        # === NEW: Check if price is AT a key zone ===
        at_zone = False
        zone_type = None
        for zone in key_zones:
            zone_lower = zone.get("lower", zone.get("price", 0) - 0.0010)
            zone_upper = zone.get("upper", zone.get("price", 0) + 0.0010)
            if zone_lower <= current_price <= zone_upper:
                at_zone = True
                zone_type = zone.get("type", "zone")
                break
        
        if at_zone:
            # Bonus for being at a key level
            if (direction == "long" and zone_type == "support") or \
               (direction == "short" and zone_type == "resistance"):
                struct_score += 6
                struct_details.append(f"At {zone_type} ✓")
            else:
                struct_score += 3
                struct_details.append(f"At {zone_type}")
        else:
            struct_details.append("No zone")
        
        # === NEW: Check if price is inside an unfilled FVG ===
        in_fvg = False
        fvg_type = None
        for fvg in fvgs:
            if fvg.get("lower", 0) <= current_price <= fvg.get("upper", 0):
                in_fvg = True
                fvg_type = fvg.get("type", "fvg")
                break
        
        if in_fvg:
            # Bonus for being in FVG (imbalance zone)
            if (direction == "long" and fvg_type == "bullish") or \
               (direction == "short" and fvg_type == "bearish"):
                struct_score += 6
                struct_details.append(f"In {fvg_type} FVG ✓")
            else:
                struct_score += 2
                struct_details.append(f"In {fvg_type} FVG")
        
    else:
        struct_score = 10
        struct_details.append("No data (default)")
    
    scores["structure"] = {
        "score": min(struct_score, struct_max),
        "max": struct_max,
        "weight": weights["structure"],
        "details": ", ".join(struct_details),
    }
    
    # 3. Macro Alignment (15%) - from Oracle
    # Oracle uses /api/pair/{symbol} endpoint, not /api/outlook
    macro_data = await fetch_agent_data("oracle", f"/api/pair/{symbol}")
    macro_score = 0
    macro_max = 15
    macro_details = []
    
    if macro_data:
        # Oracle uses "pair_bias" not "bias"
        macro_bias = macro_data.get("pair_bias", macro_data.get("bias", "neutral"))
        confidence = macro_data.get("confidence", 50)
        
        if (direction == "long" and macro_bias == "bullish") or \
           (direction == "short" and macro_bias == "bearish"):
            macro_score += 10 + int(confidence / 20)  # Up to 15
            macro_details.append(f"Macro {macro_bias} ({confidence}% conf)")
        elif macro_bias == "neutral":
            macro_score += 7
            macro_details.append("Macro neutral")
        else:
            macro_score += 3
            macro_details.append(f"Macro counter ({macro_bias})")
    else:
        macro_score = 7
        macro_details.append("No data (default)")
    
    scores["macro"] = {
        "score": min(macro_score, macro_max),
        "max": macro_max,
        "weight": weights["macro"],
        "details": ", ".join(macro_details),
    }
    
    # 4. Sentiment/Positioning (10%) - from Pulse
    sentiment_data = await fetch_agent_data("pulse", f"/api/sentiment/{symbol}")
    sent_score = 0
    sent_max = 10
    sent_details = []
    
    if sentiment_data:
        classification = sentiment_data.get("classification", "neutral")
        retail = sentiment_data.get("retail_positioning", {})
        long_pct = retail.get("long_pct", 50)
        
        if classification == "trend_supportive":
            sent_score += 8
            sent_details.append(f"Trend supportive ({long_pct}% retail long)")
        elif classification == "contrarian_opportunity":
            sent_score += 10  # Contrarian is great
            sent_details.append(f"Contrarian opportunity! ({long_pct}% retail)")
        elif classification == "overcrowded":
            sent_score += 2  # Penalty
            sent_details.append(f"OVERCROWDED ({long_pct}% retail long)")
        else:
            sent_score += 5
            sent_details.append(f"Neutral ({long_pct}% retail long)")
    else:
        sent_score = 5
        sent_details.append("No data (default)")
    
    scores["sentiment"] = {
        "score": min(sent_score, sent_max),
        "max": sent_max,
        "weight": weights["sentiment"],
        "details": ", ".join(sent_details),
    }
    
    # 5. Regime Suitability (15%) - from Compass
    regime_data = await fetch_agent_data("compass", f"/api/regime/{symbol}")
    regime_score = 0
    regime_max = 15
    regime_details = []
    
    if regime_data:
        regime = regime_data.get("primary_regime", regime_data.get("regime", "unknown"))
        transition_prob = regime_data.get("transition_probability", 0.5)
        risk_mult = regime_data.get("risk_multiplier", 1.0)
        compatible = regime_data.get("recommended_strategies", regime_data.get("strategy_families", []))
        
        # Strategy compatibility
        strategy_base = strategy.split("-")[0].upper() if strategy else ""
        if any(s.upper() in strategy_base or strategy_base in s.upper() for s in compatible):
            regime_score += 10
            regime_details.append(f"Strategy fits {regime}")
        else:
            regime_score += 3
            regime_details.append(f"Strategy marginal for {regime}")
        
        # Stability bonus
        if transition_prob < 0.3:
            regime_score += 5
            regime_details.append("Stable regime")
        elif transition_prob < 0.5:
            regime_score += 3
            regime_details.append("Moderately stable")
    else:
        regime_score = 8
        regime_details.append("No data (default)")
    
    scores["regime"] = {
        "score": min(regime_score, regime_max),
        "max": regime_max,
        "weight": weights["regime"],
        "details": ", ".join(regime_details),
    }
    
    # 6. Risk & Execution (15%) - from Guardian + Executor
    risk_score = 0
    risk_max = 15
    risk_details = []
    
    guardian_data = await fetch_agent_data("guardian", "/api/status")
    if guardian_data:
        risk_mode = guardian_data.get("mode", "normal")
        if risk_mode == "normal":
            risk_score += 8
            risk_details.append("Risk normal")
        elif risk_mode == "reduced":
            risk_score += 5
            risk_details.append("Risk reduced")
        elif risk_mode == "defensive":
            risk_score += 3
            risk_details.append("Risk defensive")
    
    executor_data = await fetch_agent_data("executor", "/api/status")
    if executor_data:
        exec_mode = executor_data.get("mode", "paper")
        bridge_status = executor_data.get("bridge_status", "unknown")
        if bridge_status == "READY":
            risk_score += 7
            risk_details.append("Execution ready")
        else:
            risk_score += 3
            risk_details.append(f"Bridge: {bridge_status}")
    else:
        risk_score += 5
        risk_details.append("Executor status unknown")
    
    scores["risk_execution"] = {
        "score": min(risk_score, risk_max),
        "max": risk_max,
        "weight": weights["risk_execution"],
        "details": ", ".join(risk_details),
    }
    
    # Calculate total score
    total_score = sum(s["score"] for s in scores.values())
    
    return total_score, scores


async def make_decision(candidate: TradeCandidate) -> dict:
    """Make final trading decision for a candidate."""
    symbol = candidate.symbol
    direction = candidate.direction
    strategy = candidate.strategy
    
    decision_record = {
        "timestamp": datetime.utcnow().isoformat(),
        "symbol": symbol,
        "direction": direction,
        "strategy": strategy,
        "entry_price": candidate.entry_price,
        "stop_loss": candidate.stop_loss,
        "take_profit": candidate.take_profit,
    }
    
    # Step 1: Check hard gates
    gates_passed, gate_results = await check_hard_gates(symbol, direction, strategy, candidate.stop_loss)
    decision_record["hard_gates"] = gate_results
    decision_record["gates_passed"] = gates_passed
    
    if not gates_passed:
        # Find first failed gate
        failed_gate = next((g for g in gate_results if not g["passed"]), None)
        decision_record["decision"] = Decision.NO_TRADE.value
        decision_record["reason"] = f"Hard gate failed: {failed_gate['gate'] if failed_gate else 'Unknown'}"
        decision_record["confluence_score"] = 0
        decisions_log.append(decision_record)
        return decision_record
    
    # Step 2: Calculate confluence score
    total_score, score_breakdown = await calculate_confluence_score(symbol, direction, strategy)
    decision_record["confluence_score"] = total_score
    decision_record["score_breakdown"] = score_breakdown
    
    # Step 3: Determine decision
    thresholds = CONFIG["decision_thresholds"]
    
    if total_score >= thresholds["execute"]:
        if direction == "long":
            decision_record["decision"] = Decision.BUY.value
        else:
            decision_record["decision"] = Decision.SELL.value
        decision_record["reason"] = f"Strong confluence ({total_score}/100), all gates passed"
    elif total_score >= thresholds["watchlist"]:
        decision_record["decision"] = Decision.WATCHLIST.value
        decision_record["reason"] = f"Moderate confluence ({total_score}/100), monitor for improvement"
        # Add to watchlist
        watchlist[f"{symbol}_{direction}"] = {
            "symbol": symbol,
            "direction": direction,
            "score": total_score,
            "added_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(hours=24)).isoformat(),
        }
    else:
        decision_record["decision"] = Decision.NO_TRADE.value
        decision_record["reason"] = f"Insufficient confluence ({total_score}/100)"
    
    decisions_log.append(decision_record)
    
    # Step 4: Route if executable
    if decision_record["decision"] in [Decision.BUY.value, Decision.SELL.value]:
        # Log to Chronicle
        await post_to_agent("chronicle", "/api/trade/propose", {
            "symbol": symbol,
            "side": direction,
            "entry_price": candidate.entry_price,
            "stop_loss": candidate.stop_loss,
            "take_profit": candidate.take_profit,
            "timeframe": candidate.timeframe,
            "strategy_family": strategy,
            "confidence": total_score,
            "entry_reason": decision_record["reason"],
        })
        
        # ═══════════════════════════════════════════════════════════
        # AUTO-EXECUTION: Route to Executor agent
        # ═══════════════════════════════════════════════════════════
        exec_result = await route_to_executor(
            symbol=symbol,
            direction=direction,
            entry_price=candidate.entry_price,
            stop_loss=candidate.stop_loss,
            take_profit=candidate.take_profit,
            strategy=strategy,
            confidence=total_score,
        )
        
        if exec_result:
            decision_record["execution"] = {
                "order_id": exec_result.get("order_id"),
                "status": exec_result.get("status"),
                "fill_price": exec_result.get("fill_price"),
                "health_score": exec_result.get("health_score"),
            }
    
    return decision_record


async def call_claude(prompt: str, context: str = "") -> str:
    if not ANTHROPIC_API_KEY:
        return "[No API key configured]"
    
    soul = (WORKSPACE / "SOUL.md").read_text() if (WORKSPACE / "SOUL.md").exists() else ""
    
    try:
        # Use pooled HTTP client for connection reuse
        from shared import get_pooled_client
        client = await get_pooled_client()
        
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 2048,
                "system": soul,
                "messages": [{"role": "user", "content": f"{context}\n\n{prompt}" if context else prompt}]
            },
            timeout=60.0
        )
        if r.status_code == 200:
            return r.json()["content"][0]["text"]
    except Exception as e:
        print(f"Claude API error: {e}")
    
    return "[Error calling Claude API]"


async def fetch_all_agent_status():
    """Fetch status from all agents with in-memory caching."""
    global agent_status
    
    # Use in-memory cache for agent status (30 second TTL)
    from shared import InMemoryCache
    cache = InMemoryCache(default_ttl=30)
    
    agents = [
        ("curator", "data-agent"),
        ("sentinel", "news-agent"),
        ("oracle", "macro-agent"),
        ("atlas", "technical-agent"),
        ("architect", "structure-agent"),
        ("pulse", "sentiment-agent"),
        ("compass", "regime-agent"),
        ("tactician", "strategy-agent"),
        ("guardian", "risk-agent"),
        ("balancer", "portfolio-agent"),
        ("executor", "execution-agent"),
        ("chronicle", "journal-agent"),
        ("arbiter", "governance-agent"),
        ("insight", "analytics-agent"),
    ]
    
    for agent_key, _ in agents:
        # Check cache first
        cache_key = f"agent_status:{agent_key}"
        cached = cache.get(cache_key)
        if cached:
            agent_status[agent_key] = cached
            continue
        
        data = await fetch_agent_data(agent_key, "/api/status")
        if data:
            status_entry = {
                "status": "online",
                "name": data.get("name", agent_key),
                "data": data,
                "last_check": datetime.utcnow().isoformat(),
            }
            agent_status[agent_key] = status_entry
            cache.set(cache_key, status_entry)
        else:
            status_entry = {
                "status": "offline",
                "name": agent_key,
                "last_check": datetime.utcnow().isoformat(),
            }
            agent_status[agent_key] = status_entry
            cache.set(cache_key, status_entry, ttl=10)  # Shorter TTL for offline status


@app.on_event("startup")
async def startup():
    print(f"🚀 {AGENT_NAME} (Orchestrator/CIO Agent) v2.0 starting...")
    asyncio.create_task(fetch_all_agent_status())


async def fetch_dashboard_data():
    """Fetch all data needed for the rich dashboard."""
    
    # Symbols to track
    SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "GBPJPY", "USDCHF", "USDCAD", "EURAUD", "AUDNZD", "AUDUSD"]
    
    # Market data from Curator
    market_data = {}
    curator_market = await fetch_agent_data("curator", "/api/market")
    if curator_market and isinstance(curator_market, dict):
        for sym in SYMBOLS:
            sym_data = curator_market.get(sym, {})
            if sym_data:
                market_data[sym] = {
                    "price": sym_data.get("price", sym_data.get("bid", 0)),
                    "change_pct": 0,  # TODO: Calculate from candle data
                    "spread": sym_data.get("spread", 0),
                }
            else:
                market_data[sym] = {"price": 0, "change_pct": 0, "spread": 0}
    else:
        # Fallback if curator unavailable
        for sym in SYMBOLS:
            market_data[sym] = {"price": 0, "change_pct": 0, "spread": 0}
    
    # Confluence data from various agents
    confluence_data = {}
    for sym in SYMBOLS:
        # Get technical bias
        tech_data = await fetch_agent_data("atlas", f"/api/analysis/{sym}")
        # Get structure
        struct_data = await fetch_agent_data("architect", f"/api/structure/{sym}")
        # Get regime
        regime_data = await fetch_agent_data("compass", f"/api/regime/{sym}")
        
        # Calculate quick confluence
        tech_score = tech_data.get("alignment_score", 50) if tech_data else 50
        struct_conf = struct_data.get("confidence", 50) if struct_data else 50
        regime_conf = regime_data.get("confidence", 50) if regime_data else 50
        
        # Determine direction
        tech_bias = (tech_data.get("bias", "neutral") if tech_data else "neutral").lower()
        struct_bias = (struct_data.get("bias", "neutral") if struct_data else "neutral").lower()
        
        if "bull" in tech_bias or "long" in tech_bias:
            direction = "bullish"
        elif "bear" in tech_bias or "short" in tech_bias:
            direction = "bearish"
        else:
            direction = "neutral"
        
        avg_score = int((tech_score + struct_conf + regime_conf) / 3)
        
        confluence_data[sym] = {
            "score": avg_score,
            "direction": direction,
        }
    
    # Account data from Curator (which reads MT5 files)
    account_data = {"balance": 0, "equity": 0, "daily_pnl": 0, "daily_pnl_pct": 0}
    curator_account = await fetch_agent_data("curator", "/api/account")
    if curator_account and not curator_account.get("error"):
        account_data["balance"] = curator_account.get("balance", 0)
        account_data["equity"] = curator_account.get("equity", 0)
        account_data["daily_pnl"] = curator_account.get("profit", 0)
    
    # Also try Guardian for daily P/L percentage
    guardian_data = await fetch_agent_data("guardian", "/api/status")
    if guardian_data:
        account_data["daily_pnl_pct"] = guardian_data.get("daily_pnl", 0)
    
    # Positions from Curator (reads MT5 positions file)
    positions = []
    positions_data = await fetch_agent_data("curator", "/api/positions")
    if positions_data:
        raw_positions = positions_data.get("positions", [])
        for pos in raw_positions:
            positions.append({
                "symbol": pos.get("symbol", "?"),
                "side": pos.get("direction", "long").upper(),  # "short" -> "SHORT", "long" -> "LONG"
                "lots": pos.get("volume", 0),
                "entry": pos.get("open_price", 0),
                "sl": pos.get("sl", 0),
                "tp": pos.get("tp", 0),
                "pnl": pos.get("profit", 0),
            })
    
    # Events from Sentinel
    events = []
    events_data = await fetch_agent_data("sentinel", "/api/events")
    if events_data:
        # Handle both list and dict responses
        raw_events = events_data if isinstance(events_data, list) else events_data.get("events", [])
        for ev in raw_events[:6]:
            if isinstance(ev, dict):
                # Parse ISO time format: 2026-03-13T04:42:54.292035 -> 04:42
                time_str = str(ev.get("time", ""))
                if "T" in time_str:
                    time_display = time_str.split("T")[1][:5]  # Get HH:MM after T
                else:
                    time_display = time_str[:5]
                events.append({
                    "time": time_display if time_display else "?",
                    "currency": ev.get("currency", "?"),
                    "event": ev.get("event", "?"),
                    "impact": ev.get("impact", "low"),
                })
    
    # Guardian status
    guardian_status = {
        "mode": "NORMAL",
        "drawdown": 0,
        "open_positions": 0,
        "max_positions": 5,
    }
    if guardian_data:
        guardian_status["mode"] = guardian_data.get("mode", "NORMAL").upper()
        guardian_status["drawdown"] = abs(guardian_data.get("drawdown", 0))
        guardian_status["open_positions"] = guardian_data.get("open_positions", 0)
        guardian_status["max_positions"] = guardian_data.get("max_positions", 5)
    
    # Session info
    hour = datetime.utcnow().hour
    if 21 <= hour or hour < 6:
        session = "Sydney Session"
    elif 0 <= hour < 9:
        session = "Tokyo Session"
    elif 7 <= hour < 16:
        session = "London Session"
    else:
        session = "New York Session"
    
    return market_data, confluence_data, account_data, positions, events, guardian_status, session


@app.get("/", response_class=HTMLResponse)
async def home():
    await fetch_all_agent_status()
    
    # Check if rich dashboard is available
    if RICH_DASHBOARD:
        # Fetch all dashboard data
        market_data, confluence_data, account_data, positions, events, guardian_status, session_info = await fetch_dashboard_data()
        
        return get_dashboard_html(
            agent_status=agent_status,
            decisions_log=decisions_log,
            watchlist=watchlist,
            market_data=market_data,
            confluence_data=confluence_data,
            account_data=account_data,
            positions=positions,
            events=events,
            guardian_status=guardian_status,
            session_info=session_info,
            CONFIG=CONFIG,  # Pass trading settings
        )
    
    # Fallback to basic dashboard
    agent_cards = ""
    for key, status in agent_status.items():
        online = status.get("status") == "online"
        color = "#22c55e" if online else "#ef4444"
        name = status.get("name", key)
        agent_cards += f'<div style="background:#1a1a24;padding:10px;border-radius:8px;border-left:3px solid {color}">{name}: {status.get("status", "?")}</div>'
    
    return f'''<!DOCTYPE html>
<html><head><title>Nexus</title><meta http-equiv="refresh" content="30">
<style>body{{background:#0a0a0f;color:#e0e0e0;font-family:sans-serif;padding:20px}}h1{{color:#f97316}}</style>
</head><body>
<h1>🎯 Nexus v3.0</h1>
<p>Rich dashboard loading failed. Basic mode.</p>
<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:20px 0">{agent_cards}</div>
<p>Decisions: {len(decisions_log)} | Watchlist: {len(watchlist)}</p>
</body></html>'''


@app.post("/chat")
async def chat(request: ChatRequest):
    context = f"Recent decisions: {json.dumps(decisions_log[-5:], default=str)[:2000]}\nAgent status: {json.dumps(agent_status, default=str)[:1000]}"
    return {"response": await call_claude(request.message, context)}


@app.get("/monitor", response_class=HTMLResponse)
async def monitoring_dashboard():
    """Agent monitoring dashboard with health status and message flow."""
    await fetch_all_agent_status()
    
    if MONITORING_AVAILABLE:
        message_stats = get_message_stats(minutes=5)
        return get_monitoring_dashboard_html(agent_status, message_stats)
    
    # Fallback basic monitoring
    online = len([a for a in agent_status.values() if a.get("status") == "online"])
    return f'''<!DOCTYPE html>
<html><head><title>Monitor</title><meta http-equiv="refresh" content="10">
<style>body{{background:#0a0a0f;color:#e0e0e0;font-family:sans-serif;padding:20px}}</style>
</head><body>
<h1>Agent Monitor</h1>
<p>Online: {online}/{len(agent_status)}</p>
<a href="/">Back to Dashboard</a>
</body></html>'''


@app.get("/api/monitor/stats")
async def get_monitor_stats():
    """Get monitoring statistics as JSON."""
    await fetch_all_agent_status()
    
    stats = {
        "agents": {},
        "messages": get_message_stats(minutes=5) if MONITORING_AVAILABLE else {},
    }
    
    for key, status in agent_status.items():
        stats["agents"][key] = {
            "online": status.get("status") == "online",
            "name": status.get("name", key),
            "last_check": status.get("last_check"),
        }
    
    return stats


@app.get("/docs/how-i-work", response_class=HTMLResponse)
async def how_i_work():
    """Serve the Agent Data Reference documentation."""
    docs_path = Path("/app/docs/Agent_Data_Reference.html")
    if docs_path.exists():
        return FileResponse(docs_path, media_type="text/html")
    else:
        return HTMLResponse("<h1>Documentation not found</h1><p>Agent_Data_Reference.html is missing.</p>", status_code=404)


@app.get("/docs/charts/{filename}")
async def serve_chart(filename: str):
    """Serve chart images for documentation."""
    chart_path = Path(f"/app/docs/charts/{filename}")
    if chart_path.exists() and chart_path.suffix.lower() in [".png", ".jpg", ".jpeg", ".gif", ".webp"]:
        media_type = "image/png" if chart_path.suffix.lower() == ".png" else "image/jpeg"
        return FileResponse(chart_path, media_type=media_type)
    else:
        raise HTTPException(status_code=404, detail="Chart not found")


@app.get("/api/pair-analysis/{symbol}")
async def get_pair_analysis(symbol: str):
    """Get comprehensive analysis for a symbol from all agents with Nexus commentary."""
    
    analysis = {
        "symbol": symbol,
        "timestamp": datetime.utcnow().isoformat(),
        "agents": {},
        "confluence": {},
        "nexus_commentary": "",
    }
    
    # Use pooled HTTP client for all agent fetches
    from shared import get_pooled_client
    client = await get_pooled_client()
    
    # Curator - Market Data
    try:
        r = await client.get(f"{AGENT_URLS['curator']}/api/market/{symbol}", timeout=10.0)
        if r.status_code == 200:
            analysis["agents"]["curator"] = {
                "name": "Curator",
                "data": r.json(),
                "summary": f"Price: {r.json().get('price', 0):.5f}, Spread: {r.json().get('spread', 0):.1f} pips"
            }
    except: pass
    
    # Sentinel - Event Risk
    try:
        r = await client.get(f"{AGENT_URLS['sentinel']}/api/risk/{symbol}", timeout=10.0)
        if r.status_code == 200:
            data = r.json()
            analysis["agents"]["sentinel"] = {
                "name": "Sentinel",
                "data": data,
                "summary": f"Event Risk: {data.get('risk_score', 0)}/100, Upcoming: {data.get('upcoming_events', 0)} events"
            }
    except: pass
    
    # Oracle - Macro (use /api/pair/{pair})
    try:
        r = await client.get(f"{AGENT_URLS['oracle']}/api/pair/{symbol}", timeout=10.0)
        if r.status_code == 200:
            data = r.json()
            bias = data.get('relative_bias', 'neutral')
            conf = data.get('confidence', 0)
            diff = data.get('score_difference', 0)
            analysis["agents"]["oracle"] = {
                "name": "Oracle",
                "data": data,
                "summary": f"Macro Bias: {bias.upper()}, Confidence: {conf}%, Score Diff: {diff:+.1f}"
            }
    except: pass
    
    # Atlas Jr. - Technical (use /api/analysis/{symbol})
    try:
        r = await client.get(f"{AGENT_URLS['atlas']}/api/analysis/{symbol}", timeout=10.0)
        if r.status_code == 200:
            data = r.json()
            analysis["agents"]["atlas"] = {
                "name": "Atlas Jr.",
                "data": data,
                "summary": f"Bias: {data.get('directional_lean', 'neutral').upper()}, Grade: {data.get('trend_grade', '?')}, Setup: {data.get('setup_type', 'none')}, Alignment: {data.get('mtf_alignment', 'N/A')}"
            }
    except: pass
    
    # Architect - Structure
    try:
        r = await client.get(f"{AGENT_URLS['architect']}/api/structure/{symbol}", timeout=10.0)
        if r.status_code == 200:
            data = r.json()
            struct_bias = data.get('structural_bias', data.get('bias', 'neutral'))
            analysis["agents"]["architect"] = {
                "name": "Architect",
                "data": data,
                "summary": f"Structure: {struct_bias.upper()}, Bias: {struct_bias}, Confidence: {data.get('confidence', 0)}%"
            }
    except: pass
    
    # Pulse - Sentiment
    try:
        r = await client.get(f"{AGENT_URLS['pulse']}/api/sentiment/{symbol}", timeout=10.0)
        if r.status_code == 200:
            data = r.json()
            analysis["agents"]["pulse"] = {
                "name": "Pulse",
                "data": data,
                "summary": f"Retail: {data.get('retail_positioning', {}).get('long_pct', 50)}% Long, Status: {data.get('classification', 'neutral').upper()}"
            }
    except: pass
    
    # Compass - Regime
    try:
        r = await client.get(f"{AGENT_URLS['compass']}/api/regime/{symbol}", timeout=10.0)
        if r.status_code == 200:
            data = r.json()
            regime = data.get('primary_regime', data.get('regime', 'unknown'))
            analysis["agents"]["compass"] = {
                "name": "Compass",
                "data": data,
                "summary": f"Regime: {regime.upper()}, Confidence: {data.get('confidence', 0)}%, Risk Mult: {data.get('risk_multiplier', 1):.2f}x"
            }
    except: pass
    
    # Tactician - Strategy (show detailed checks)
    try:
        r = await client.get(f"{AGENT_URLS['tactician']}/api/strategy/{symbol}", timeout=10.0)
        if r.status_code == 200:
            data = r.json()
            selected = data.get('selected_strategy', {})
            if isinstance(selected, dict):
                strategy_name = selected.get('name', 'None')
                strategy_id = selected.get('strategy_id', 'UNKNOWN')
                strategy_score = selected.get('score', 0)
                qualified = '✅' if selected.get('qualified') else '❌'
                
                # Build checks summary
                checks = selected.get('checks', [])
                checks_summary = []
                for c in checks:
                    icon = '✅' if c.get('passed') else '❌'
                    checks_summary.append(f"{icon} {c.get('check', '?')}: {c.get('message', '')}")
                checks_str = " | ".join(checks_summary) if checks_summary else "No checks"
                
                summary = f"📋 {strategy_name} ({strategy_id}) — Score: {strategy_score}%, Qualified: {qualified}\n\nChecks: {checks_str}"
            else:
                summary = f"Strategy: {selected or 'None'}"
            
            analysis["agents"]["tactician"] = {
                "name": "Tactician",
                "data": data,
                "summary": summary
            }
    except: pass
    
    # Guardian - Risk (use /api/status)
    try:
        r = await client.get(f"{AGENT_URLS['guardian']}/api/status", timeout=10.0)
        if r.status_code == 200:
            data = r.json()
            mode = data.get('risk_mode', data.get('mode', 'unknown')).upper()
            mode_icon = '🟢' if mode == 'NORMAL' else '🟡' if mode == 'DEFENSIVE' else '🔴'
            dd = data.get('system_drawdown', data.get('drawdown', 0))
            pos = data.get('open_positions', 0)
            max_pos = data.get('max_positions', 5)
            analysis["agents"]["guardian"] = {
                "name": "Guardian",
                "data": data,
                "summary": f"{mode_icon} {mode} Mode, Drawdown: {dd:.1f}%, Positions: {pos}/{max_pos}"
            }
    except: pass
    
    # Balancer - Portfolio
    try:
        r = await client.get(f"{AGENT_URLS['balancer']}/api/exposure/{symbol}", timeout=10.0)
        if r.status_code == 200:
            data = r.json()
            analysis["agents"]["balancer"] = {
                "name": "Balancer",
                "data": data,
                "summary": f"Current Exposure: {data.get('exposure', 0):.2f}%, Recommendation: {data.get('recommendation', 'none')}"
            }
    except: pass
    
    # Calculate confluence - fetch actual strategy from Tactician
    try:
        # Get strategy from Tactician for accurate regime matching
        tactician_data = await fetch_agent_data("tactician", f"/api/strategy/{symbol}")
        strategy = "generic"
        if tactician_data:
            selected = tactician_data.get("selected_strategy", {})
            if selected:
                strategy = selected.get("strategy_id", selected.get("name", "generic"))
        
        score, breakdown = await calculate_confluence_score(symbol, "long", strategy)
        analysis["confluence"]["long"] = {"score": score, "breakdown": breakdown}
        
        score_short, breakdown_short = await calculate_confluence_score(symbol, "short", strategy)
        analysis["confluence"]["short"] = {"score": score_short, "breakdown": breakdown_short}
    except Exception as e:
        analysis["confluence"]["error"] = str(e)
    
    # Generate Nexus commentary using Claude
    try:
        agent_summaries = "\n".join([f"- {v['name']}: {v['summary']}" for v in analysis["agents"].values()])
        
        prompt = f"""Analyze {symbol} based on the following agent reports and provide a concise trading commentary (3-4 sentences max):

{agent_summaries}

Confluence Scores:
- Long: {analysis['confluence'].get('long', {}).get('score', 0)}/100
- Short: {analysis['confluence'].get('short', {}).get('score', 0)}/100

Provide your assessment: Is there a clear trade setup? What's the bias? Any concerns?"""
        
        analysis["nexus_commentary"] = await call_claude(prompt, "")
    except Exception as e:
        analysis["nexus_commentary"] = f"Commentary unavailable: {str(e)}"
    
    return analysis


@app.post("/api/evaluate")
async def evaluate_trade(candidate: TradeCandidate):
    """Evaluate a trade candidate through the decision engine."""
    return await make_decision(candidate)


@app.get("/api/confluence/{symbol}")
async def get_confluence(symbol: str, direction: str = "long"):
    """Get confluence analysis for a symbol."""
    import time
    request_time = datetime.utcnow().isoformat()
    
    # Fetch actual strategy from Tactician instead of using "generic"
    tactician_data = await fetch_agent_data("tactician", f"/api/strategy/{symbol}")
    strategy = "generic"
    if tactician_data:
        selected = tactician_data.get("selected_strategy", {})
        if selected:
            strategy = selected.get("strategy_id", selected.get("name", "generic"))
    
    score, breakdown = await calculate_confluence_score(symbol, direction, strategy)
    gates_passed, gates = await check_hard_gates(symbol, direction, strategy, 0)
    
    return {
        "symbol": symbol,
        "direction": direction,
        "confluence_score": score,
        "score_breakdown": breakdown,
        "hard_gates": gates,
        "all_gates_passed": gates_passed,
        "calculated_at": request_time,  # Timestamp to track when this score was calculated
        "strategy_used": strategy,
    }


@app.get("/api/confluence/{symbol}/debug")
async def get_confluence_debug(symbol: str, direction: str = "long"):
    """
    Debug endpoint: Get confluence score with detailed agent input data.
    
    Use this to investigate score discrepancies between dashboard views and lifecycle logs.
    Returns raw agent data alongside the calculated score to identify what changed.
    """
    import time
    request_time = datetime.utcnow().isoformat()
    
    # Fetch actual strategy from Tactician
    tactician_data = await fetch_agent_data("tactician", f"/api/strategy/{symbol}")
    strategy = "generic"
    if tactician_data:
        selected = tactician_data.get("selected_strategy", {})
        if selected:
            strategy = selected.get("strategy_id", selected.get("name", "generic"))
    
    # Collect raw agent data for debugging
    raw_inputs = {}
    
    # Atlas Jr. - Technical
    atlas_data = await fetch_agent_data("atlas", f"/api/analysis/{symbol}")
    raw_inputs["atlas"] = {
        "trend_grade": atlas_data.get("trend_grade") if atlas_data else None,
        "directional_lean": atlas_data.get("directional_lean") if atlas_data else None,
        "mtf_alignment": atlas_data.get("mtf_alignment") if atlas_data else None,
    }
    
    # Architect - Structure
    clean_symbol = symbol.replace(".s", "").replace(".S", "")
    struct_data = await fetch_agent_data("architect", f"/api/structure/{clean_symbol}")
    raw_inputs["architect"] = {
        "structural_bias": struct_data.get("structural_bias") if struct_data else None,
        "current_price": struct_data.get("current_price") if struct_data else None,
        "key_zones_count": len(struct_data.get("key_zones", [])) if struct_data else 0,
        "fvgs_count": len(struct_data.get("fvgs", [])) if struct_data else 0,
    }
    
    # Oracle - Macro
    macro_data = await fetch_agent_data("oracle", f"/api/pair/{symbol}")
    raw_inputs["oracle"] = {
        "pair_bias": macro_data.get("pair_bias") if macro_data else None,
        "confidence": macro_data.get("confidence") if macro_data else None,
    }
    
    # Pulse - Sentiment
    sentiment_data = await fetch_agent_data("pulse", f"/api/sentiment/{symbol}")
    raw_inputs["pulse"] = {
        "classification": sentiment_data.get("classification") if sentiment_data else None,
        "retail_long_pct": sentiment_data.get("retail_positioning", {}).get("long_pct") if sentiment_data else None,
    }
    
    # Compass - Regime
    regime_data = await fetch_agent_data("compass", f"/api/regime/{symbol}")
    raw_inputs["compass"] = {
        "primary_regime": regime_data.get("primary_regime") if regime_data else None,
        "transition_probability": regime_data.get("transition_probability") if regime_data else None,
        "recommended_strategies": regime_data.get("recommended_strategies", [])[:3] if regime_data else [],
    }
    
    # Guardian - Risk
    guardian_data = await fetch_agent_data("guardian", "/api/status")
    raw_inputs["guardian"] = {
        "mode": guardian_data.get("mode") if guardian_data else None,
    }
    
    # Executor - Execution
    executor_data = await fetch_agent_data("executor", "/api/status")
    raw_inputs["executor"] = {
        "bridge_status": executor_data.get("bridge_status") if executor_data else None,
    }
    
    # Calculate score
    score, breakdown = await calculate_confluence_score(symbol, direction, strategy)
    gates_passed, gates = await check_hard_gates(symbol, direction, strategy, 0)
    
    return {
        "symbol": symbol,
        "direction": direction,
        "confluence_score": score,
        "score_breakdown": breakdown,
        "hard_gates": gates,
        "all_gates_passed": gates_passed,
        "calculated_at": request_time,
        "strategy_used": strategy,
        "raw_agent_inputs": raw_inputs,  # Raw data that drove the score calculation
        "note": "Use this to compare with lifecycle logs. Score differences are usually due to agent data changing between requests.",
    }



@app.get("/api/decisions")
async def get_decisions(limit: int = 50):
    """Get recent decisions."""
    return {
        "decisions": decisions_log[-limit:],
        "count": len(decisions_log),
    }


@app.get("/api/watchlist")
async def get_watchlist():
    """Get current watchlist."""
    # Clean expired items
    now = datetime.utcnow()
    expired = [k for k, v in watchlist.items() 
               if datetime.fromisoformat(v.get("expires_at", now.isoformat())) < now]
    for k in expired:
        del watchlist[k]
    
    return {
        "watchlist": list(watchlist.values()),
        "count": len(watchlist),
    }


# ═══════════════════════════════════════════════════════════════
# SCORE HISTORY ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.get("/api/score-history/{symbol}")
async def get_score_history(symbol: str, hours: int = 24):
    """
    Get confluence score history for a symbol.
    Shows how the score evolved over time.
    """
    try:
        from score_history import get_tracker
        tracker = get_tracker()
        history = tracker.get_history(symbol, hours)
        
        return {
            "symbol": symbol,
            "hours": hours,
            "readings": len(history),
            "history": history,
            "latest": history[-1] if history else None,
        }
    except Exception as e:
        return {"error": str(e), "symbol": symbol, "history": []}


@app.get("/api/score-history/{symbol}/chart")
async def get_score_history_chart(symbol: str, hours: int = 24, breakdown: bool = True):
    """
    Get a PNG chart showing confluence score evolution over time.
    """
    from fastapi.responses import Response
    
    try:
        from score_history import get_tracker, generate_score_history_chart
        tracker = get_tracker()
        history = tracker.get_history(symbol, hours)
        
        if not history:
            return {"error": "No score history available for this symbol"}
        
        chart_bytes = generate_score_history_chart(
            history=history,
            symbol=symbol,
            show_breakdown=breakdown,
        )
        
        if chart_bytes:
            return Response(content=chart_bytes, media_type="image/png")
        else:
            return {"error": "Failed to generate chart"}
            
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/score-history")
async def get_all_score_history(hours: int = 12):
    """
    Get score history summary for all symbols.
    """
    try:
        from score_history import get_tracker
        tracker = get_tracker()
        
        symbols = tracker.get_all_symbols()
        summary = {}
        
        for symbol in symbols:
            history = tracker.get_history(symbol, hours)
            if history:
                scores = [h.get("total", 0) for h in history]
                summary[symbol] = {
                    "readings": len(history),
                    "latest": history[-1].get("total", 0),
                    "avg": round(sum(scores) / len(scores), 1),
                    "max": max(scores),
                    "min": min(scores),
                    "latest_decision": history[-1].get("decision", ""),
                    "latest_direction": history[-1].get("direction", ""),
                }
        
        return {
            "symbols": summary,
            "hours": hours,
            "total_symbols": len(summary),
        }
    except Exception as e:
        return {"error": str(e), "symbols": {}}


@app.get("/api/score-history/compare/chart")
async def get_multi_symbol_chart(symbols: str = "USDJPY,GBPUSD,AUDNZD", hours: int = 12):
    """
    Get a PNG chart comparing confluence scores across multiple symbols.
    
    Args:
        symbols: Comma-separated list of symbols
        hours: How many hours of history to show
    """
    from fastapi.responses import Response
    
    try:
        from score_history import get_tracker, generate_multi_symbol_chart
        tracker = get_tracker()
        symbol_list = [s.strip() for s in symbols.split(",")]
        
        chart_bytes = generate_multi_symbol_chart(
            tracker=tracker,
            symbols=symbol_list,
            hours=hours,
        )
        
        if chart_bytes:
            return Response(content=chart_bytes, media_type="image/png")
        else:
            return {"error": "Failed to generate chart or no data available"}
            
    except Exception as e:
        return {"error": str(e)}




@app.get("/api/agents")
async def get_agents():
    """Get status of all agents."""
    await fetch_all_agent_status()
    return {
        "agents": agent_status,
        "online": len([a for a in agent_status.values() if a.get("status") == "online"]),
        "total": len(agent_status),
    }


@app.get("/api/config")
async def get_config():
    """Get current configuration."""
    return CONFIG


@app.post("/api/config")
async def update_config(new_config: dict):
    """Update configuration."""
    global CONFIG
    CONFIG.update(new_config)
    return {"status": "updated", "config": CONFIG}


# ═══════════════════════════════════════════════════════════════
# AUTO-TRADING CONTROL ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.get("/api/auto-trade")
async def get_auto_trade_status():
    """Get auto-trading status, risk settings, and recent executions."""
    # Get current account balance for display
    balance = await get_account_balance()
    
    return {
        "enabled": AUTO_TRADE_ENABLED,
        "position_sizing": {
            "method": "risk_based" if USE_RISK_BASED_SIZING else "fixed",
            "risk_percent": RISK_PERCENT,
            "account_balance": balance,
            "min_lot_size": MIN_LOT_SIZE,
            "max_lot_size": MAX_LOT_SIZE,
            "default_lot_size": DEFAULT_LOT_SIZE,
        },
        "signal_cooldown_minutes": SIGNAL_COOLDOWN_MINUTES,
        "recent_executions": [
            {"signal": k, "executed_at": v.isoformat()}
            for k, v in sorted(executed_signals.items(), key=lambda x: x[1], reverse=True)[:10]
        ],
        "thresholds": CONFIG["decision_thresholds"],
    }


@app.post("/api/auto-trade/toggle")
async def toggle_auto_trade(enabled: bool = True):
    """Enable or disable auto-trading."""
    global AUTO_TRADE_ENABLED
    AUTO_TRADE_ENABLED = enabled
    status = "ENABLED" if enabled else "DISABLED"
    print(f"[Nexus] 🔔 Auto-trading {status}")
    return {"auto_trade_enabled": AUTO_TRADE_ENABLED, "message": f"Auto-trading {status}"}


@app.post("/api/auto-trade/lot-size")
async def set_lot_size(lot_size: float):
    """Set default/fallback lot size for auto-trades."""
    global DEFAULT_LOT_SIZE
    if lot_size <= 0 or lot_size > MAX_LOT_SIZE:
        raise HTTPException(status_code=400, detail=f"Lot size must be between {MIN_LOT_SIZE} and {MAX_LOT_SIZE}")
    DEFAULT_LOT_SIZE = lot_size
    print(f"[Nexus] 📊 Default lot size set to {lot_size}")
    return {"default_lot_size": DEFAULT_LOT_SIZE}


@app.post("/api/auto-trade/risk-percent")
async def set_risk_percent(risk_percent: float):
    """Set risk percentage per trade (e.g., 1.0 for 1%)."""
    global RISK_PERCENT
    if risk_percent <= 0 or risk_percent > 5.0:
        raise HTTPException(status_code=400, detail="Risk percent must be between 0.1 and 5.0")
    RISK_PERCENT = risk_percent
    print(f"[Nexus] 📊 Risk percent set to {risk_percent}%")
    return {"risk_percent": RISK_PERCENT}


@app.post("/api/auto-trade/toggle-risk-sizing")
async def toggle_risk_based_sizing(enabled: bool = True):
    """Enable or disable risk-based position sizing."""
    global USE_RISK_BASED_SIZING
    USE_RISK_BASED_SIZING = enabled
    method = "RISK-BASED" if enabled else "FIXED"
    print(f"[Nexus] 📊 Position sizing method: {method}")
    return {"use_risk_based_sizing": USE_RISK_BASED_SIZING, "message": f"Position sizing: {method}"}


@app.post("/api/auto-trade/clear-cooldowns")
async def clear_signal_cooldowns():
    """Clear all signal cooldowns (allows re-execution of signals)."""
    global executed_signals
    count = len(executed_signals)
    executed_signals = {}
    print(f"[Nexus] 🔄 Cleared {count} signal cooldowns")
    return {"cleared": count}


@app.get("/api/auto-trade/calculate-size")
async def preview_position_size(symbol: str, entry_price: float, stop_loss: float):
    """Preview position size calculation without executing."""
    lot_size, details = await calculate_position_size(symbol, entry_price, stop_loss)
    return {
        "symbol": symbol,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "calculated_lot_size": lot_size,
        "details": details,
    }


# Storage for agent data ingestion
agent_data_store: Dict[str, List[dict]] = {}

@app.post("/api/ingest")
async def ingest_agent_data(data: dict):
    """
    Receive data from other agents.
    This endpoint collects alerts, analysis results, and other outputs from all agents.
    """
    agent_id = data.get("agent_id", "unknown")
    output_type = data.get("output_type", "unknown")
    
    # Store in memory (keep last 100 per agent)
    if agent_id not in agent_data_store:
        agent_data_store[agent_id] = []
    
    agent_data_store[agent_id].append({
        "timestamp": data.get("timestamp", datetime.utcnow().isoformat()),
        "type": output_type,
        "data": data.get("data", {}),
    })
    
    # Keep only last 100 entries per agent
    if len(agent_data_store[agent_id]) > 100:
        agent_data_store[agent_id] = agent_data_store[agent_id][-100:]
    
    return {"status": "ok", "agent_id": agent_id, "type": output_type}


@app.get("/api/status")
async def get_status():
    await fetch_all_agent_status()
    online = len([a for a in agent_status.values() if a.get("status") == "online"])
    
    return {
        "agent_id": "orchestrator",
        "name": AGENT_NAME,
        "status": "active",
        "version": "2.0",
        "agents_online": online,
        "agents_total": len(agent_status),
        "decisions_made": len(decisions_log),
        "trades_approved": len([d for d in decisions_log if d.get("decision") in ["BUY", "SELL"]]),
        "watchlist_count": len(watchlist),
        "active_trades": len(lifecycle_manager.active_trades) if lifecycle_manager else 0,
    }


# ═══════════════════════════════════════════════════════════════════════════
# LIFECYCLE MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════

from lifecycle import LifecycleManager

lifecycle_manager = LifecycleManager(AGENT_URLS)

# Set up watchlist callback so lifecycle can add items to the watchlist
def add_to_watchlist(symbol: str, direction: str, score: int, setup_id: str = None):
    """Add item to watchlist from lifecycle manager."""
    key = f"{symbol}_{direction}"
    watchlist[key] = {
        "symbol": symbol,
        "direction": direction,
        "score": score,
        "setup_id": setup_id,
        "added_at": datetime.utcnow().isoformat(),
        "expires_at": (datetime.utcnow() + timedelta(hours=24)).isoformat(),
    }

lifecycle_manager.set_watchlist_callback(add_to_watchlist)

MAJOR_PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "GBPJPY", "USDCHF", "USDCAD", "EURAUD", "AUDNZD", "AUDUSD"]


@app.post("/api/lifecycle/scan")
async def lifecycle_scan(symbols: List[str] = None):
    """Run a full lifecycle scan."""
    scan_symbols = symbols or MAJOR_PAIRS
    result = await lifecycle_manager.run_full_cycle(scan_symbols)
    return result


@app.get("/api/lifecycle/active")
async def get_active_trades():
    """Get all active trades being monitored."""
    trades = []
    for trade_id, trade in lifecycle_manager.active_trades.items():
        trades.append({
            "trade_id": trade_id,
            "symbol": trade.setup.symbol,
            "direction": trade.setup.direction,
            "entry": trade.entry_price_actual,
            "current_pnl_r": trade.current_pnl_r,
            "current_pnl_pips": trade.current_pnl_pips,
            "bars": trade.bars_in_trade,
            "status": trade.status.value,
        })
    return {"active_trades": trades, "count": len(trades)}


@app.get("/api/lifecycle/completed")
async def get_completed_trades(limit: int = 50):
    """Get completed trades."""
    trades = []
    for trade in lifecycle_manager.completed_trades[-limit:]:
        trades.append({
            "trade_id": trade.trade_id,
            "symbol": trade.setup.symbol,
            "direction": trade.setup.direction,
            "template": trade.setup.template,
            "entry": trade.entry_price_actual,
            "exit": trade.exit_price,
            "pnl_r": trade.current_pnl_r,
            "pnl_pips": trade.current_pnl_pips,
            "exit_reason": trade.exit_reason.value if trade.exit_reason else None,
            "bars_held": trade.bars_in_trade,
            "mfe": trade.max_favorable_excursion,
            "mae": trade.max_adverse_excursion,
        })
    return {"completed_trades": trades, "count": len(lifecycle_manager.completed_trades)}


@app.get("/api/lifecycle/log")
async def get_lifecycle_log(limit: int = 100):
    """Get lifecycle event log."""
    return {
        "log": lifecycle_manager.lifecycle_log[-limit:],
        "count": len(lifecycle_manager.lifecycle_log),
    }


@app.get("/api/lifecycle/pending")
async def get_pending_orders():
    """Get all tracked pending (limit) orders."""
    orders = []
    for order_id, order in lifecycle_manager.pending_orders.items():
        age_hours = (datetime.utcnow() - order.created_at).total_seconds() / 3600
        orders.append({
            "order_id": order_id,
            "ticket": order.ticket,
            "symbol": order.symbol,
            "direction": order.direction,
            "entry_price": order.entry_price,
            "lots": order.lots,
            "stop_loss": order.stop_loss,
            "take_profit": order.take_profit,
            "status": order.status,
            "created_at": order.created_at.isoformat(),
            "age_hours": round(age_hours, 2),
            "expiration_hours": order.expiration_hours,
            "expires_in_hours": round(order.expiration_hours - age_hours, 2),
        })
    return {
        "pending_orders": orders,
        "count": len(orders),
        "expiration_default": lifecycle_manager.pending_order_expiration_hours,
    }


@app.post("/api/lifecycle/cancel-pending/{order_id}")
async def cancel_pending_order(order_id: str):
    """Cancel a pending order by ID."""
    success = await lifecycle_manager.cancel_pending_order(order_id)
    if success:
        return {"status": "cancelled", "order_id": order_id}
    return {"status": "error", "message": "Order not found or already cancelled"}


@app.post("/api/lifecycle/monitor")
async def monitor_active():
    """Manually trigger monitoring of all active trades."""
    results = []
    for trade_id, trade in list(lifecycle_manager.active_trades.items()):
        monitor_result = await lifecycle_manager.stage_active_monitoring(trade)
        exit_result = await lifecycle_manager.stage_exit_management(trade)
        results.append({
            "trade_id": trade_id,
            "monitoring": monitor_result,
            "exit_triggered": exit_result is not None,
            "exit_reason": exit_result.value if exit_result else None,
        })
    return {"results": results}


@app.post("/api/lifecycle/sync")
async def sync_with_mt5():
    """Sync lifecycle active trades with MT5 positions."""
    before_count = len(lifecycle_manager.active_trades)
    await lifecycle_manager.sync_with_mt5()
    after_count = len(lifecycle_manager.active_trades)
    return {
        "before": before_count,
        "after": after_count,
        "active_trades": [
            {"trade_id": t.trade_id, "symbol": t.setup.symbol, "ticket": t.broker_ticket}
            for t in lifecycle_manager.active_trades.values()
        ]
    }


@app.get("/api/templates")
async def get_strategy_templates():
    """Get available strategy templates and their requirements."""
    return {
        "templates": [
            {
                "name": "PULLBACK_IN_TREND",
                "family": "trend_following",
                "regimes": ["trending_up", "trending_down"],
                "min_confidence": 70,
                "typical_rr": "2.5:1",
                "win_rate_target": "55-60%",
            },
            {
                "name": "BREAKOUT_WITH_CONFIRMATION",
                "family": "breakout",
                "regimes": ["compression", "ranging"],
                "min_confidence": 75,
                "typical_rr": "2:1",
                "win_rate_target": "45-50%",
            },
            {
                "name": "LIQUIDITY_SWEEP_RECLAIM",
                "family": "reversal",
                "regimes": ["any"],
                "min_confidence": 80,
                "typical_rr": "3:1",
                "win_rate_target": "50-55%",
            },
            {
                "name": "RANGE_FADE_MEAN_REVERSION",
                "family": "mean_reversion",
                "regimes": ["ranging"],
                "min_confidence": 70,
                "typical_rr": "1.5:1",
                "win_rate_target": "60-65%",
            },
            {
                "name": "FAILED_BREAKOUT_REVERSAL",
                "family": "reversal",
                "regimes": ["any"],
                "min_confidence": 75,
                "typical_rr": "2:1",
                "win_rate_target": "55-60%",
            },
            {
                "name": "SESSION_OPEN_DRIVE",
                "family": "momentum",
                "regimes": ["trending_up", "trending_down", "volatile"],
                "min_confidence": 70,
                "typical_rr": "2:1",
                "win_rate_target": "50-55%",
            },
            {
                "name": "VOLATILITY_EXPANSION_BREAKOUT",
                "family": "breakout",
                "regimes": ["compression"],
                "min_confidence": 75,
                "typical_rr": "2.5:1",
                "win_rate_target": "50-55%",
            },
            {
                "name": "EVENT_CATALYST_BREAKOUT",
                "family": "event",
                "regimes": ["any"],
                "min_confidence": 70,
                "typical_rr": "3:1+",
                "win_rate_target": "45-50%",
            },
        ],
        "exit_frameworks": [
            "fixed_r_target",
            "structure_based",
            "atr_trailing",
            "partial_tp_runner",
            "time_stop",
            "event_risk_exit",
            "thesis_invalidation",
        ],
    }


@app.on_event("startup")
async def startup_event():
    """Start workflow scheduler and lifecycle monitoring on startup."""
    auto_start = os.getenv("AUTO_START_WORKFLOWS", "false").lower() == "true"
    if WORKFLOWS_AVAILABLE and auto_start:
        await scheduler.start()
    
    # Start lifecycle monitoring loop (1 second interval for active trades)
    lifecycle_manager.start_monitoring()
    print("🔄 Lifecycle trade monitor started (1s interval)")


@app.on_event("shutdown")
async def shutdown_event():
    """Stop workflow scheduler on shutdown."""
    if WORKFLOWS_AVAILABLE:
        await scheduler.stop()


@app.get("/api/performance")
async def get_performance_metrics():
    """Get HTTP client pool and cache performance metrics."""
    from shared import get_metrics
    metrics = get_metrics()
    stats = metrics.get_stats()
    return {
        "http_pool": stats,
        "status": "pooled_http_client_active",
        "optimization": "connection_reuse_enabled",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, access_log=False)
