"""
Regime Detection Agent - Compass
Market regime classification, strategy gating, risk adjustment
"""

import os
import json
import asyncio
import httpx
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from enum import Enum

app = FastAPI(title="Compass - Regime Detection Agent", version="2.0")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CURATOR_URL = os.getenv("CURATOR_URL", "http://data-agent:8000")
NEWS_URL = os.getenv("NEWS_URL", "http://news-agent:8000")
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://orchestrator-agent:8000")
AGENT_NAME = "Compass"
WORKSPACE = Path("/app/workspace")

SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "GBPJPY", "USDCHF", "USDCAD", "EURAUD", "AUDNZD", "AUDUSD"]
TIMEFRAMES = ["M30", "H1", "H4", "D1"]

# Regime cache
regime_data: Dict[str, dict] = {}


class ChatRequest(BaseModel):
    message: str


class Regime(str, Enum):
    TRENDING = "trending"
    MEAN_REVERTING = "mean_reverting"
    RANGE_BOUND = "range_bound"
    BREAKOUT_READY = "breakout_ready"
    EVENT_DRIVEN = "event_driven"
    UNSTABLE_NOISY = "unstable_noisy"
    LOW_VOL_DRIFT = "low_vol_drift"
    HIGH_VOL_EXPANSION = "high_vol_expansion"


# Strategy families per regime
REGIME_STRATEGIES = {
    Regime.TRENDING: ["trend_continuation", "pullback", "breakout_continuation"],
    Regime.MEAN_REVERTING: ["range_fade", "mean_reversion", "scalp"],
    Regime.RANGE_BOUND: ["range_fade", "breakout_watch"],
    Regime.BREAKOUT_READY: ["breakout", "compression_trade"],
    Regime.EVENT_DRIVEN: ["event_straddle"],
    Regime.UNSTABLE_NOISY: [],  # No strategies
    Regime.LOW_VOL_DRIFT: ["position_trade", "carry_trade"],
    Regime.HIGH_VOL_EXPANSION: ["trend_following_reduced"],
}

# Risk multipliers per regime
REGIME_RISK_MULTIPLIERS = {
    Regime.TRENDING: 1.0,
    Regime.MEAN_REVERTING: 0.8,
    Regime.RANGE_BOUND: 0.8,
    Regime.BREAKOUT_READY: 0.7,
    Regime.EVENT_DRIVEN: 0.5,
    Regime.UNSTABLE_NOISY: 0.0,
    Regime.LOW_VOL_DRIFT: 0.6,
    Regime.HIGH_VOL_EXPANSION: 0.5,
}


async def fetch_candles(symbol: str, timeframe: str) -> List[dict]:
    """Fetch candles from Curator."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{CURATOR_URL}/api/snapshot/timeframe/{symbol}/{timeframe}", timeout=5.0)
            if r.status_code == 200:
                return r.json().get("candles", [])
    except:
        pass
    return []


async def check_event_risk(symbol: str) -> bool:
    """Check if symbol is in event-driven mode."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{NEWS_URL}/api/risk/{symbol}", timeout=3.0)
            if r.status_code == 200:
                risk = r.json()
                return risk.get("mode") == "pause" or risk.get("risk_score", 0) > 80
    except:
        pass
    return False


def calculate_adx(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
    """Calculate ADX."""
    if len(closes) < period + 1:
        return 0
    
    plus_dm, minus_dm, tr_vals = [], [], []
    
    for i in range(1, len(closes)):
        high_diff = highs[i] - highs[i-1]
        low_diff = lows[i-1] - lows[i]
        
        plus_dm.append(max(high_diff, 0) if high_diff > low_diff else 0)
        minus_dm.append(max(low_diff, 0) if low_diff > high_diff else 0)
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        tr_vals.append(tr)
    
    if len(tr_vals) < period:
        return 0
    
    atr = sum(tr_vals[-period:]) / period
    if atr == 0:
        return 0
    
    plus_di = sum(plus_dm[-period:]) / period / atr * 100
    minus_di = sum(minus_dm[-period:]) / period / atr * 100
    
    if plus_di + minus_di == 0:
        return 0
    
    dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100
    return dx


def calculate_atr_percentile(atr: float, historical_atrs: List[float]) -> float:
    """Calculate ATR percentile vs history."""
    if not historical_atrs:
        return 50
    sorted_atrs = sorted(historical_atrs)
    rank = sum(1 for a in sorted_atrs if a <= atr)
    return rank / len(sorted_atrs) * 100


def detect_bollinger_squeeze(closes: List[float], period: int = 20) -> bool:
    """Detect Bollinger Band squeeze."""
    if len(closes) < period * 2:
        return False
    
    # Current bandwidth
    sma = sum(closes[-period:]) / period
    variance = sum((p - sma) ** 2 for p in closes[-period:]) / period
    current_std = variance ** 0.5
    current_width = current_std / sma if sma > 0 else 0
    
    # Historical average bandwidth
    widths = []
    for i in range(period, len(closes)):
        hist_sma = sum(closes[i-period:i]) / period
        hist_var = sum((p - hist_sma) ** 2 for p in closes[i-period:i]) / period
        hist_std = hist_var ** 0.5
        hist_width = hist_std / hist_sma if hist_sma > 0 else 0
        widths.append(hist_width)
    
    avg_width = sum(widths) / len(widths) if widths else current_width
    return current_width < avg_width * 0.75


def classify_timeframe_regime(candles: List[dict], event_driven: bool = False) -> Tuple[Regime, float]:
    """Classify regime for a single timeframe."""
    if len(candles) < 30:
        return Regime.UNSTABLE_NOISY, 30
    
    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    
    # Calculate indicators
    adx = calculate_adx(highs, lows, closes)
    
    # ATR and volatility
    atr_values = []
    for i in range(1, len(candles)):
        tr = max(
            candles[i]["high"] - candles[i]["low"],
            abs(candles[i]["high"] - candles[i-1]["close"]),
            abs(candles[i]["low"] - candles[i-1]["close"])
        )
        atr_values.append(tr)
    
    current_atr = sum(atr_values[-14:]) / 14 if len(atr_values) >= 14 else 0
    atr_percentile = calculate_atr_percentile(current_atr, atr_values)
    
    # Bollinger squeeze
    squeeze = detect_bollinger_squeeze(closes)
    
    # Price range (last 20 bars)
    recent_high = max(highs[-20:])
    recent_low = min(lows[-20:])
    range_size = (recent_high - recent_low) / closes[-1] if closes[-1] > 0 else 0
    
    # Trend direction
    sma20 = sum(closes[-20:]) / 20
    sma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else sma20
    price_vs_ma = closes[-1] > sma20 > sma50
    
    # Classification logic
    if event_driven:
        return Regime.EVENT_DRIVEN, 85
    
    if adx < 15 and range_size < 0.01:
        if atr_percentile < 25:
            return Regime.LOW_VOL_DRIFT, 70
        else:
            return Regime.UNSTABLE_NOISY, 60
    
    if squeeze:
        return Regime.BREAKOUT_READY, 75
    
    if atr_percentile > 80:
        if adx > 25:
            return Regime.HIGH_VOL_EXPANSION, 80
        else:
            return Regime.UNSTABLE_NOISY, 55
    
    if adx > 25:
        return Regime.TRENDING, min(50 + adx, 90)
    
    if adx < 20 and range_size < 0.02:
        return Regime.RANGE_BOUND, 70
    
    if adx < 22:
        return Regime.MEAN_REVERTING, 65
    
    # ADX 22-25 is a gray zone - not clearly trending or ranging
    # Default to UNSTABLE_NOISY to avoid false trend signals
    return Regime.UNSTABLE_NOISY, 50


def calculate_transition_probability(current_regime: Regime, confidence: float, atr_trend: str) -> Dict[str, float]:
    """Calculate probability of transitioning to other regimes."""
    base_stay = confidence / 100
    transitions = {current_regime.value: base_stay}
    
    remaining = 1 - base_stay
    
    # Regime-specific transitions
    if current_regime == Regime.TRENDING:
        transitions["range_bound"] = remaining * 0.3
        transitions["mean_reverting"] = remaining * 0.3
        transitions["high_vol_expansion"] = remaining * 0.2
        transitions["other"] = remaining * 0.2
    
    elif current_regime == Regime.RANGE_BOUND:
        transitions["breakout_ready"] = remaining * 0.4
        transitions["trending"] = remaining * 0.3
        transitions["mean_reverting"] = remaining * 0.2
        transitions["other"] = remaining * 0.1
    
    elif current_regime == Regime.BREAKOUT_READY:
        transitions["trending"] = remaining * 0.4
        transitions["high_vol_expansion"] = remaining * 0.3
        transitions["range_bound"] = remaining * 0.2
        transitions["other"] = remaining * 0.1
    
    else:
        transitions["trending"] = remaining * 0.25
        transitions["range_bound"] = remaining * 0.25
        transitions["mean_reverting"] = remaining * 0.25
        transitions["other"] = remaining * 0.25
    
    return {k: round(v * 100, 1) for k, v in transitions.items()}


async def analyze_symbol(symbol: str) -> dict:
    """Perform full regime analysis for a symbol."""
    # Check event risk
    event_driven = await check_event_risk(symbol)
    
    # Analyze each timeframe
    tf_regimes = {}
    
    for tf in TIMEFRAMES:
        candles = await fetch_candles(symbol, tf)
        if len(candles) >= 30:
            regime, confidence = classify_timeframe_regime(candles, event_driven and tf in ["M30", "H1"])
            tf_regimes[tf] = {
                "regime": regime.value,
                "confidence": confidence,
            }
    
    if not tf_regimes:
        return {"error": "Insufficient data"}
    
    # Determine primary regime (highest TF with confidence > 65%)
    primary_regime = None
    primary_confidence = 0
    
    for tf in reversed(TIMEFRAMES):  # Start from highest TF
        if tf in tf_regimes and tf_regimes[tf]["confidence"] >= 65:
            primary_regime = Regime(tf_regimes[tf]["regime"])
            primary_confidence = tf_regimes[tf]["confidence"]
            break
    
    if not primary_regime:
        # Fall back to highest confidence
        best_tf = max(tf_regimes.keys(), key=lambda t: tf_regimes[t]["confidence"])
        primary_regime = Regime(tf_regimes[best_tf]["regime"])
        primary_confidence = tf_regimes[best_tf]["confidence"]
    
    # Calculate TF alignment
    regimes_list = [tf_regimes[tf]["regime"] for tf in tf_regimes]
    alignment = regimes_list.count(primary_regime.value) / len(regimes_list)
    
    # Calculate risk multiplier
    base_risk = REGIME_RISK_MULTIPLIERS.get(primary_regime, 0.5)
    alignment_factor = 0.5 + alignment * 0.5  # 0.5 to 1.0 based on alignment
    risk_multiplier = round(base_risk * alignment_factor, 2)
    
    # Get transition probabilities
    transitions = calculate_transition_probability(primary_regime, primary_confidence, "stable")
    
    # Get recommended strategies
    recommended_strategies = REGIME_STRATEGIES.get(primary_regime, [])
    blocked_strategies = []
    for regime, strategies in REGIME_STRATEGIES.items():
        if regime != primary_regime:
            for s in strategies:
                if s not in recommended_strategies and s not in blocked_strategies:
                    blocked_strategies.append(s)
    
    # Determine tradeable status
    tradeable = primary_regime not in [Regime.UNSTABLE_NOISY, Regime.EVENT_DRIVEN] or (
        primary_regime == Regime.EVENT_DRIVEN and primary_confidence < 80
    )
    
    return {
        "symbol": symbol,
        "primary_regime": primary_regime.value,
        "confidence": primary_confidence,
        "timeframe_regimes": tf_regimes,
        "tf_alignment": round(alignment * 100, 0),
        "transitions": transitions,
        "risk_multiplier": risk_multiplier,
        "recommended_strategies": recommended_strategies,
        "blocked_strategies": blocked_strategies[:5],
        "tradeable": tradeable,
        "regime_duration": "Unknown",  # Would need historical tracking
        "timestamp": datetime.utcnow().isoformat(),
    }


async def send_to_orchestrator(symbol: str, analysis: dict):
    """Send regime analysis to Orchestrator."""
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{ORCHESTRATOR_URL}/api/ingest",
                json={
                    "agent_id": "regime",
                    "agent_name": AGENT_NAME,
                    "output_type": "signal",
                    "timestamp": datetime.utcnow().isoformat(),
                    "data": {
                        "symbol": symbol,
                        "direction": "bullish" if "trending" in analysis["primary_regime"].lower() else "neutral",
                        "confidence": analysis["confidence"] / 100,
                        "reason": f"{analysis['primary_regime']} (risk: {analysis['risk_multiplier']}x)",
                    },
                },
                timeout=5.0
            )
    except:
        pass


async def background_analysis():
    """Background regime analysis loop."""
    global regime_data
    
    while True:
        for symbol in SYMBOLS:
            try:
                analysis = await analyze_symbol(symbol)
                if "error" not in analysis:
                    regime_data[symbol] = analysis
                    await send_to_orchestrator(symbol, analysis)
            except Exception as e:
                print(f"[Compass] Error analyzing {symbol}: {e}")
        
        await asyncio.sleep(60)


async def call_claude(prompt: str, context: str = "") -> str:
    if not ANTHROPIC_API_KEY:
        return "[No API key]"
    soul = (WORKSPACE / "SOUL.md").read_text() if (WORKSPACE / "SOUL.md").exists() else ""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": "claude-sonnet-4-20250514", "max_tokens": 2048, "system": soul,
                      "messages": [{"role": "user", "content": f"{context}\n\n{prompt}" if context else prompt}]},
                timeout=60.0
            )
            if r.status_code == 200:
                return r.json()["content"][0]["text"]
    except:
        pass
    return "[Error]"


@app.on_event("startup")
async def startup():
    global regime_data
    print(f"🚀 {AGENT_NAME} (Regime Detection Agent) v2.0 starting...")
    
    # Initial analysis
    for symbol in SYMBOLS:
        try:
            regime_data[symbol] = await analyze_symbol(symbol)
        except:
            pass
    
    asyncio.create_task(background_analysis())


@app.get("/", response_class=HTMLResponse)
async def home():
    cards_html = ""
    
    for symbol in SYMBOLS:
        r = regime_data.get(symbol, {})
        regime = r.get("primary_regime", "unknown")
        conf = r.get("confidence", 0)
        risk_mult = r.get("risk_multiplier", 0)
        alignment = r.get("tf_alignment", 0)
        tradeable = r.get("tradeable", False)
        strategies = r.get("recommended_strategies", [])
        tf_regimes = r.get("timeframe_regimes", {})
        
        # Regime colors
        regime_colors = {
            "trending": "#22c55e",
            "mean_reverting": "#3b82f6",
            "range_bound": "#f59e0b",
            "breakout_ready": "#8b5cf6",
            "event_driven": "#ef4444",
            "unstable_noisy": "#dc2626",
            "low_vol_drift": "#6b7280",
            "high_vol_expansion": "#f97316",
        }
        color = regime_colors.get(regime, "#888")
        
        # TF breakdown
        tf_html = ""
        for tf in TIMEFRAMES:
            if tf in tf_regimes:
                tf_r = tf_regimes[tf]
                tf_html += f'<div class="tf-item">{tf}: {tf_r["regime"][:8]} ({tf_r["confidence"]:.0f}%)</div>'
        
        # Strategies
        strat_html = ", ".join(strategies[:2]) if strategies else "None"
        
        cards_html += f'''
        <div class="card" style="border-left: 4px solid {color}">
            <div class="card-header">
                <span class="symbol">{symbol}</span>
                <span class="tradeable">{"✅" if tradeable else "❌"}</span>
            </div>
            <div class="regime" style="color:{color}">{regime.upper().replace("_", " ")}</div>
            <div class="conf-row">
                <span>Conf: {conf:.0f}%</span>
                <span>Risk: {risk_mult}x</span>
                <span>Align: {alignment:.0f}%</span>
            </div>
            <div class="tf-breakdown">{tf_html}</div>
            <div class="strategies">Strategies: {strat_html}</div>
        </div>
        '''
    
    return f'''<!DOCTYPE html>
<html><head>
    <title>🧭 Compass - Regime Agent</title>
    <meta http-equiv="refresh" content="30">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, sans-serif; background: #0a0a0f; color: #e0e0e0; padding: 20px; }}
        .header {{ display: flex; align-items: center; gap: 15px; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid #333; }}
        .header h1 {{ color: #06b6d4; }}
        .status {{ background: #22c55e20; color: #22c55e; padding: 5px 12px; border-radius: 20px; font-size: 14px; }}
        .grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-bottom: 20px; }}
        .card {{ background: #1a1a24; border-radius: 10px; padding: 15px; }}
        .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
        .symbol {{ font-size: 16px; font-weight: bold; }}
        .tradeable {{ font-size: 14px; }}
        .regime {{ font-size: 14px; font-weight: bold; margin-bottom: 8px; }}
        .conf-row {{ display: flex; gap: 15px; font-size: 11px; color: #888; margin-bottom: 8px; }}
        .tf-breakdown {{ background: #0a0a0f; border-radius: 6px; padding: 8px; margin-bottom: 8px; }}
        .tf-item {{ font-size: 10px; color: #aaa; margin: 3px 0; }}
        .strategies {{ font-size: 11px; color: #666; }}
        .chat-section {{ background: #1a1a24; border-radius: 12px; padding: 20px; }}
        .chat-section h2 {{ color: #06b6d4; margin-bottom: 15px; }}
        .chat-messages {{ height: 150px; overflow-y: auto; background: #0a0a0f; border-radius: 8px; padding: 10px; margin-bottom: 10px; }}
        .chat-input {{ display: flex; gap: 10px; }}
        .chat-input input {{ flex: 1; padding: 10px; border-radius: 8px; border: 1px solid #333; background: #0a0a0f; color: #fff; }}
        .chat-input button {{ padding: 10px 20px; background: #06b6d4; color: #000; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; }}
        .message {{ margin: 8px 0; padding: 8px; border-radius: 6px; font-size: 13px; }}
        .message.user {{ background: #333; margin-left: 20%; }}
        .message.agent {{ background: #1a3d4d; margin-right: 20%; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🧭 Compass</h1>
        <span class="status">● CLASSIFYING</span>
        <span style="color: #888; margin-left: auto;">Regime Detection Agent v2.0</span>
    </div>
    
    <div class="grid">{cards_html}</div>
    
    <div class="chat-section">
        <h2>💬 Ask Compass</h2>
        <div class="chat-messages" id="messages"></div>
        <div class="chat-input">
            <input type="text" id="input" placeholder="Ask about regimes..." onkeypress="if(event.key==='Enter')sendMessage()">
            <button onclick="sendMessage()">Send</button>
        </div>
    </div>
    <script>
        const CHAT_KEY = 'compass_chat_history';
        
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
    context = f"Regime Data:\n{json.dumps(regime_data, indent=2, default=str)[:6000]}"
    return {"response": await call_claude(request.message, context)}


@app.get("/api/regimes")
async def get_all_regimes():
    return regime_data


@app.get("/api/regime/{symbol}")
async def get_symbol_regime(symbol: str):
    return regime_data.get(symbol.upper(), {"error": "Not found"})


@app.get("/api/tradeable")
async def get_tradeable():
    return {s: r for s, r in regime_data.items() if r.get("tradeable")}


@app.get("/api/status")
async def get_status():
    tradeable_count = sum(1 for r in regime_data.values() if r.get("tradeable"))
    return {
        "agent_id": "regime",
        "name": AGENT_NAME,
        "status": "active",
        "symbols_classified": len(regime_data),
        "tradeable_symbols": tradeable_count,
        "version": "2.0",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
