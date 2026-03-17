"""
Market Structure Agent - Architect
Structure analysis, zone mapping, liquidity detection
"""

import os
import sys
import json
import asyncio
import httpx
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from enum import Enum

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

app = FastAPI(title="Architect - Market Structure Agent", version="2.0")

AGENT_NAME = "Architect"
CURATOR_URL = get_agent_url("curator")
ORCHESTRATOR_URL = get_agent_url("orchestrator")

SYMBOLS = FOREX_SYMBOLS

# Analysis cache
structure_cache: Dict[str, dict] = {}


# Using ChatRequest from shared module - removed duplicate

class StructureState(str, Enum):
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    TRANSITIONING = "transitioning"
    BREAKING_UP = "breaking_up"
    BREAKING_DOWN = "breaking_down"


class ZoneFreshness(str, Enum):
    FRESH = "fresh"
    TESTED_ONCE = "tested_once"
    TESTED_MULTIPLE = "tested_multiple"
    BROKEN = "broken"


class SwingType(str, Enum):
    HH = "HH"  # Higher High
    HL = "HL"  # Higher Low
    LH = "LH"  # Lower High
    LL = "LL"  # Lower Low
    SH = "SH"  # Swing High (neutral)
    SL = "SL"  # Swing Low (neutral)


# ═══════════════════════════════════════════════════════════════
# STRUCTURE DETECTION
# ═══════════════════════════════════════════════════════════════

def find_swing_points(candles: List[dict], lookback: int = 3) -> List[dict]:
    """Find swing highs and lows."""
    swings = []
    
    for i in range(lookback, len(candles) - lookback):
        high = candles[i]["high"]
        low = candles[i]["low"]
        time = candles[i].get("time", "")
        
        # Check for swing high
        is_swing_high = all(
            candles[i-j]["high"] < high and candles[i+j]["high"] < high
            for j in range(1, lookback + 1)
        )
        
        # Check for swing low
        is_swing_low = all(
            candles[i-j]["low"] > low and candles[i+j]["low"] > low
            for j in range(1, lookback + 1)
        )
        
        if is_swing_high:
            swings.append({
                "type": "high",
                "price": high,
                "index": i,
                "time": time,
            })
        
        if is_swing_low:
            swings.append({
                "type": "low",
                "price": low,
                "index": i,
                "time": time,
            })
    
    return sorted(swings, key=lambda x: x["index"])


def label_swing_sequence(swings: List[dict]) -> List[dict]:
    """Label swings as HH/HL/LH/LL."""
    if len(swings) < 2:
        return swings
    
    labeled = []
    last_high = None
    last_low = None
    
    for swing in swings:
        swing_copy = swing.copy()
        
        if swing["type"] == "high":
            if last_high is None:
                swing_copy["label"] = SwingType.SH.value
            elif swing["price"] > last_high:
                swing_copy["label"] = SwingType.HH.value
            else:
                swing_copy["label"] = SwingType.LH.value
            last_high = swing["price"]
        else:  # low
            if last_low is None:
                swing_copy["label"] = SwingType.SL.value
            elif swing["price"] > last_low:
                swing_copy["label"] = SwingType.HL.value
            else:
                swing_copy["label"] = SwingType.LL.value
            last_low = swing["price"]
        
        labeled.append(swing_copy)
    
    return labeled


def determine_structure_state(swings: List[dict], current_price: float) -> Tuple[StructureState, int]:
    """Determine current market structure state."""
    if len(swings) < 4:
        return StructureState.RANGING, 30
    
    # Get recent swings
    recent = swings[-6:] if len(swings) >= 6 else swings
    labels = [s.get("label", "") for s in recent]
    
    # Count HH/HL vs LH/LL
    bullish_count = labels.count("HH") + labels.count("HL")
    bearish_count = labels.count("LH") + labels.count("LL")
    
    # Get last swing high and low
    last_sh = next((s for s in reversed(swings) if s["type"] == "high"), None)
    last_sl = next((s for s in reversed(swings) if s["type"] == "low"), None)
    
    # Check for breakout
    if last_sh and current_price > last_sh["price"] * 1.001:
        return StructureState.BREAKING_UP, 70
    if last_sl and current_price < last_sl["price"] * 0.999:
        return StructureState.BREAKING_DOWN, 70
    
    # Trending conditions
    if bullish_count >= 3 and bearish_count <= 1:
        return StructureState.TRENDING_UP, 75 + bullish_count * 5
    if bearish_count >= 3 and bullish_count <= 1:
        return StructureState.TRENDING_DOWN, 75 + bearish_count * 5
    
    # Check for structure shift (transition)
    if len(labels) >= 3:
        if labels[-1] in ["LH", "LL"] and labels[-2] in ["HH", "HL"]:
            return StructureState.TRANSITIONING, 60
        if labels[-1] in ["HH", "HL"] and labels[-2] in ["LH", "LL"]:
            return StructureState.TRANSITIONING, 60
    
    return StructureState.RANGING, 50


def identify_zones(swings: List[dict], candles: List[dict], current_price: float) -> List[dict]:
    """Identify key support/resistance zones."""
    zones = []
    
    for swing in swings[-10:]:  # Last 10 swings
        zone_type = "resistance" if swing["type"] == "high" else "support"
        price = swing["price"]
        
        # Determine zone boundaries (small buffer)
        if "JPY" in str(price) or price > 100:
            buffer = 0.10  # 10 pips for JPY pairs
        else:
            buffer = 0.0010  # 10 pips for others
        
        zone = {
            "price": round(price, 5),
            "type": zone_type,
            "swing_label": swing.get("label", "?"),
            "upper": round(price + buffer, 5),
            "lower": round(price - buffer, 5),
            "time": swing.get("time", ""),
        }
        
        # Count tests
        tests = sum(1 for c in candles if zone["lower"] <= c["high"] <= zone["upper"] or zone["lower"] <= c["low"] <= zone["upper"])
        
        if tests == 0:
            zone["freshness"] = ZoneFreshness.FRESH.value
        elif tests == 1:
            zone["freshness"] = ZoneFreshness.TESTED_ONCE.value
        else:
            zone["freshness"] = ZoneFreshness.TESTED_MULTIPLE.value
        
        # Check if broken
        if zone_type == "resistance" and current_price > zone["upper"]:
            zone["freshness"] = ZoneFreshness.BROKEN.value
        if zone_type == "support" and current_price < zone["lower"]:
            zone["freshness"] = ZoneFreshness.BROKEN.value
        
        zones.append(zone)
    
    # Sort by price descending
    return sorted(zones, key=lambda x: x["price"], reverse=True)


def detect_liquidity_sweeps(candles: List[dict], swings: List[dict]) -> List[dict]:
    """Detect liquidity sweep events."""
    sweeps = []
    
    for i in range(2, len(candles)):
        candle = candles[i]
        prev = candles[i-1]
        
        # Check each recent swing
        for swing in swings[-8:]:
            swing_price = swing["price"]
            
            # Sweep above swing high
            if swing["type"] == "high":
                if candle["high"] > swing_price and candle["close"] < swing_price:
                    wick_size = candle["high"] - max(candle["open"], candle["close"])
                    body_size = abs(candle["close"] - candle["open"])
                    if wick_size > body_size * 0.5:
                        sweeps.append({
                            "type": "sweep_high",
                            "swing_price": swing_price,
                            "sweep_price": candle["high"],
                            "time": candle.get("time", ""),
                            "candle_index": i,
                            "reversal": "bearish",
                        })
            
            # Sweep below swing low
            if swing["type"] == "low":
                if candle["low"] < swing_price and candle["close"] > swing_price:
                    wick_size = min(candle["open"], candle["close"]) - candle["low"]
                    body_size = abs(candle["close"] - candle["open"])
                    if wick_size > body_size * 0.5:
                        sweeps.append({
                            "type": "sweep_low",
                            "swing_price": swing_price,
                            "sweep_price": candle["low"],
                            "time": candle.get("time", ""),
                            "candle_index": i,
                            "reversal": "bullish",
                        })
    
    return sweeps[-5:]  # Return last 5 sweeps


def detect_fvg(candles: List[dict]) -> List[dict]:
    """Detect Fair Value Gaps (imbalances)."""
    fvgs = []
    
    for i in range(2, len(candles)):
        c1 = candles[i-2]
        c2 = candles[i-1]
        c3 = candles[i]
        
        # Bullish FVG: c3 low > c1 high (gap up)
        if c3["low"] > c1["high"]:
            fvgs.append({
                "type": "bullish",
                "upper": c3["low"],
                "lower": c1["high"],
                "size": c3["low"] - c1["high"],
                "time": c2.get("time", ""),
                "filled": False,
            })
        
        # Bearish FVG: c3 high < c1 low (gap down)
        if c3["high"] < c1["low"]:
            fvgs.append({
                "type": "bearish",
                "upper": c1["low"],
                "lower": c3["high"],
                "size": c1["low"] - c3["high"],
                "time": c2.get("time", ""),
                "filled": False,
            })
    
    # Check if FVGs are filled
    for fvg in fvgs:
        fvg_idx = next((i for i, c in enumerate(candles) if c.get("time") == fvg["time"]), 0)
        for c in candles[fvg_idx+1:]:
            if fvg["type"] == "bullish" and c["low"] <= fvg["lower"]:
                fvg["filled"] = True
            if fvg["type"] == "bearish" and c["high"] >= fvg["upper"]:
                fvg["filled"] = True
    
    return [f for f in fvgs if not f["filled"]][-5:]  # Return unfilled FVGs


def detect_wick_rejections(candles: List[dict]) -> List[dict]:
    """Detect significant wick rejection candles."""
    rejections = []
    
    for i, candle in enumerate(candles[-20:], start=len(candles)-20):
        body = abs(candle["close"] - candle["open"])
        upper_wick = candle["high"] - max(candle["open"], candle["close"])
        lower_wick = min(candle["open"], candle["close"]) - candle["low"]
        total_range = candle["high"] - candle["low"]
        
        if total_range == 0:
            continue
        
        # Upper wick rejection (bearish)
        if upper_wick > body * 2 and upper_wick / total_range > 0.6:
            rejections.append({
                "type": "upper_wick",
                "price": candle["high"],
                "wick_pct": round(upper_wick / total_range * 100, 1),
                "time": candle.get("time", ""),
                "bias": "bearish",
            })
        
        # Lower wick rejection (bullish)
        if lower_wick > body * 2 and lower_wick / total_range > 0.6:
            rejections.append({
                "type": "lower_wick",
                "price": candle["low"],
                "wick_pct": round(lower_wick / total_range * 100, 1),
                "time": candle.get("time", ""),
                "bias": "bullish",
            })
    
    return rejections[-5:]


def generate_path_scenarios(state: StructureState, zones: List[dict], current_price: float, swings: List[dict]) -> List[dict]:
    """Generate possible path scenarios."""
    scenarios = []
    
    # Find nearest support and resistance
    resistance = next((z for z in zones if z["type"] == "resistance" and z["price"] > current_price), None)
    support = next((z for z in reversed(zones) if z["type"] == "support" and z["price"] < current_price), None)
    
    if state == StructureState.TRENDING_DOWN:
        scenarios.append({
            "name": "Continuation",
            "probability": 60,
            "description": f"Price continues down to {support['price'] if support else 'next support'}",
            "bias": "bearish",
        })
        scenarios.append({
            "name": "Pullback then continue",
            "probability": 25,
            "description": f"Price retraces to {resistance['price'] if resistance else 'resistance'}, then continues down",
            "bias": "bearish",
        })
        scenarios.append({
            "name": "Reversal",
            "probability": 15,
            "description": f"Price breaks above {resistance['price'] if resistance else 'resistance'}, structure shifts",
            "bias": "bullish",
        })
    
    elif state == StructureState.TRENDING_UP:
        scenarios.append({
            "name": "Continuation",
            "probability": 60,
            "description": f"Price continues up to {resistance['price'] if resistance else 'next resistance'}",
            "bias": "bullish",
        })
        scenarios.append({
            "name": "Pullback then continue",
            "probability": 25,
            "description": f"Price retraces to {support['price'] if support else 'support'}, then continues up",
            "bias": "bullish",
        })
        scenarios.append({
            "name": "Reversal",
            "probability": 15,
            "description": f"Price breaks below {support['price'] if support else 'support'}, structure shifts",
            "bias": "bearish",
        })
    
    elif state == StructureState.RANGING:
        scenarios.append({
            "name": "Continue ranging",
            "probability": 50,
            "description": "Price oscillates between support and resistance",
            "bias": "neutral",
        })
        scenarios.append({
            "name": "Break up",
            "probability": 25,
            "description": f"Price breaks above {resistance['price'] if resistance else 'range high'}",
            "bias": "bullish",
        })
        scenarios.append({
            "name": "Break down",
            "probability": 25,
            "description": f"Price breaks below {support['price'] if support else 'range low'}",
            "bias": "bearish",
        })
    
    else:
        scenarios.append({
            "name": "Await confirmation",
            "probability": 100,
            "description": "Structure unclear, wait for resolution",
            "bias": "neutral",
        })
    
    return scenarios


async def fetch_candles(symbol: str, timeframe: str) -> List[dict]:
    """Fetch candles from Curator using shared fetch_json."""
    data = await fetch_json(f"{CURATOR_URL}/api/snapshot/timeframe/{symbol}/{timeframe}")
    return data.get("candles", []) if data else []


async def analyze_structure(symbol: str) -> dict:
    """Perform full structure analysis."""
    # Use H1 as primary timeframe for structure
    candles = await fetch_candles(symbol, "H1")
    
    if len(candles) < 20:
        return {"error": "Insufficient data"}
    
    current_price = candles[-1]["close"]
    
    # Find swing points
    swings = find_swing_points(candles, lookback=2)
    labeled_swings = label_swing_sequence(swings)
    
    # Determine structure state
    state, confidence = determine_structure_state(labeled_swings, current_price)
    
    # Identify zones
    zones = identify_zones(labeled_swings, candles, current_price)
    
    # Detect events
    sweeps = detect_liquidity_sweeps(candles, labeled_swings)
    fvgs = detect_fvg(candles)
    rejections = detect_wick_rejections(candles)
    
    # Generate scenarios
    scenarios = generate_path_scenarios(state, zones, current_price, labeled_swings)
    
    # Determine invalidation levels
    last_sh = next((s for s in reversed(labeled_swings) if s["type"] == "high"), None)
    last_sl = next((s for s in reversed(labeled_swings) if s["type"] == "low"), None)
    
    bullish_invalidation = last_sh["price"] if last_sh else current_price * 1.01
    bearish_invalidation = last_sl["price"] if last_sl else current_price * 0.99
    
    # Swing sequence string
    swing_sequence = " → ".join([s.get("label", "?") for s in labeled_swings[-6:]])
    
    # Structural bias
    if state in [StructureState.TRENDING_DOWN, StructureState.BREAKING_DOWN]:
        bias = "bearish"
    elif state in [StructureState.TRENDING_UP, StructureState.BREAKING_UP]:
        bias = "bullish"
    else:
        bias = "neutral"
    
    return {
        "symbol": symbol,
        "structure_state": state.value,
        "confidence": confidence,
        "swing_sequence": swing_sequence,
        "current_price": round(current_price, 5),
        "key_zones": zones[:8],  # Top 8 zones
        "recent_swings": labeled_swings[-6:],
        "liquidity_sweeps": sweeps,
        "fvgs": fvgs,
        "wick_rejections": rejections,
        "invalidation": {
            "bullish": round(bullish_invalidation, 5),
            "bearish": round(bearish_invalidation, 5),
        },
        "path_scenarios": scenarios,
        "structural_bias": bias,
        "timestamp": datetime.utcnow().isoformat(),
    }


async def send_to_orchestrator(symbol: str, analysis: dict):
    """Send analysis to Orchestrator using shared post_json."""
    await post_json(
        f"{ORCHESTRATOR_URL}/api/ingest",
        {
            "agent_id": "structure",
            "agent_name": AGENT_NAME,
            "output_type": "signal",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "symbol": symbol,
                "direction": analysis["structural_bias"],
                "confidence": analysis["confidence"] / 100,
                "reason": f"{analysis['structure_state']} - {analysis['swing_sequence']}",
            },
        }
    )


async def background_analysis():
    """Background analysis loop."""
    while True:
        for symbol in SYMBOLS:
            try:
                analysis = await analyze_structure(symbol)
                if "error" not in analysis:
                    structure_cache[symbol] = analysis
                    await send_to_orchestrator(symbol, analysis)
            except Exception as e:
                print(f"[Architect] Error analyzing {symbol}: {e}")
        await asyncio.sleep(60)


# Using shared call_claude - removed duplicate implementation


@app.on_event("startup")
async def startup():
    print(f"🚀 {AGENT_NAME} (Market Structure Agent) v2.0 starting...")
    asyncio.create_task(background_analysis())


@app.get("/", response_class=HTMLResponse)
async def home():
    cards_html = ""
    for symbol in SYMBOLS:
        a = structure_cache.get(symbol, {})
        state = a.get("structure_state", "?")
        conf = a.get("confidence", 0)
        bias = a.get("structural_bias", "?")
        sequence = a.get("swing_sequence", "?")
        zones = a.get("key_zones", [])
        sweeps = a.get("liquidity_sweeps", [])
        fvgs = a.get("fvgs", [])
        
        state_color = "#22c55e" if "up" in state else "#ef4444" if "down" in state else "#f59e0b" if state == "ranging" else "#888"
        
        zones_html = ""
        for z in zones[:4]:
            z_color = "#ef4444" if z["type"] == "resistance" else "#22c55e"
            fresh_icon = "🔥" if z["freshness"] == "fresh" else "✓" if z["freshness"] == "tested_once" else ""
            zones_html += f'<div class="zone" style="border-left: 2px solid {z_color}">{z["price"]} {z["swing_label"]} {fresh_icon}</div>'
        
        events_html = ""
        if sweeps:
            events_html += f'<div class="event">⚡ {len(sweeps)} sweep(s)</div>'
        if fvgs:
            events_html += f'<div class="event">📊 {len(fvgs)} FVG(s)</div>'
        
        cards_html += f'''
        <div class="card">
            <div class="card-header">
                <span class="symbol">{symbol}</span>
                <span class="conf">{conf}%</span>
            </div>
            <div class="state" style="color:{state_color}">{state.upper().replace("_", " ")}</div>
            <div class="bias">Bias: {bias}</div>
            <div class="sequence">{sequence}</div>
            <div class="zones">{zones_html}</div>
            <div class="events">{events_html}</div>
        </div>
        '''
    
    return f'''<!DOCTYPE html>
<html><head>
    <title>🏗️ Architect - Structure Agent</title>
    <meta http-equiv="refresh" content="30">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, sans-serif; background: #0a0a0f; color: #e0e0e0; padding: 20px; }}
        .header {{ display: flex; align-items: center; gap: 15px; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid #333; }}
        .header h1 {{ color: #a855f7; }}
        .status {{ background: #22c55e20; color: #22c55e; padding: 5px 12px; border-radius: 20px; font-size: 14px; }}
        .grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-bottom: 20px; }}
        .card {{ background: #1a1a24; border-radius: 10px; padding: 15px; }}
        .card-header {{ display: flex; justify-content: space-between; margin-bottom: 8px; }}
        .symbol {{ font-size: 16px; font-weight: bold; }}
        .conf {{ font-size: 14px; color: #a855f7; }}
        .state {{ font-size: 14px; font-weight: bold; margin-bottom: 5px; }}
        .bias {{ font-size: 12px; color: #888; margin-bottom: 5px; }}
        .sequence {{ font-size: 11px; color: #666; margin-bottom: 8px; font-family: monospace; }}
        .zones {{ margin-bottom: 8px; }}
        .zone {{ font-size: 11px; padding: 2px 6px; margin: 2px 0; background: #0a0a0f; border-radius: 3px; }}
        .events {{ font-size: 11px; color: #f59e0b; }}
        .event {{ margin: 2px 0; }}
        .chat-section {{ background: #1a1a24; border-radius: 12px; padding: 20px; }}
        .chat-section h2 {{ color: #a855f7; margin-bottom: 15px; }}
        .chat-messages {{ height: 200px; overflow-y: auto; background: #0a0a0f; border-radius: 8px; padding: 10px; margin-bottom: 10px; }}
        .chat-input {{ display: flex; gap: 10px; }}
        .chat-input input {{ flex: 1; padding: 10px; border-radius: 8px; border: 1px solid #333; background: #0a0a0f; color: #fff; }}
        .chat-input button {{ padding: 10px 20px; background: #a855f7; color: #fff; border: none; border-radius: 8px; cursor: pointer; }}
        .message {{ margin: 8px 0; padding: 8px; border-radius: 6px; font-size: 13px; white-space: pre-wrap; }}
        .message.user {{ background: #333; margin-left: 20%; }}
        .message.agent {{ background: #2d1a4d; margin-right: 20%; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🏗️ Architect</h1>
        <span class="status">● MAPPING</span>
        <span style="color: #888; margin-left: auto;">Market Structure Agent v2.0 • {len(structure_cache)} pairs</span>
    </div>
    <div class="grid">{cards_html}</div>
    <div class="chat-section">
        <h2>💬 Ask Architect</h2>
        <div class="chat-messages" id="messages"></div>
        <div class="chat-input">
            <input type="text" id="input" placeholder="Ask about structure..." onkeypress="if(event.key==='Enter')sendMessage()">
            <button onclick="sendMessage()">Send</button>
        </div>
    </div>
    <script>
        const CHAT_KEY = 'architect_chat_history';
        
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
    context = f"Current structure analysis:\n{json.dumps(structure_cache, indent=2, default=str)[:8000]}"
    response = await call_claude(request.message, context, agent_name=AGENT_NAME)
    return {"response": response}


@app.get("/api/structure")
async def get_all_structure():
    return structure_cache


@app.get("/api/structure/{symbol}")
async def get_symbol_structure(symbol: str):
    symbol = symbol.upper()
    if symbol not in structure_cache:
        analysis = await analyze_structure(symbol)
        structure_cache[symbol] = analysis
    return structure_cache.get(symbol, {"error": "Not found"})


@app.get("/api/status")
async def get_status():
    return {
        "agent_id": "structure",
        "name": AGENT_NAME,
        "status": "active",
        "symbols_mapped": len(structure_cache),
        "version": "2.0",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
