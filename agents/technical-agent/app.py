"""
Technical Analysis Agent - Atlas Jr.
Multi-timeframe technical analysis with full indicator toolkit
"""

import os
import sys
import json
import asyncio
import httpx
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from collections import defaultdict
import math

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

app = FastAPI(title="Atlas Jr. - Technical Analysis Agent", version="2.0")

AGENT_NAME = "Atlas Jr."
CURATOR_URL = get_agent_url("curator")
ORCHESTRATOR_URL = get_agent_url("orchestrator")

SYMBOLS = FOREX_SYMBOLS
TIMEFRAMES = ["M30", "H1", "H4", "D1"]

# Analysis cache
analysis_cache: Dict[str, dict] = {}


# ═══════════════════════════════════════════════════════════════
# INDICATOR CALCULATIONS
# ═══════════════════════════════════════════════════════════════

def calculate_ema(prices: List[float], period: int) -> List[float]:
    """Calculate Exponential Moving Average."""
    if len(prices) < period:
        return []
    multiplier = 2 / (period + 1)
    ema = [sum(prices[:period]) / period]
    for price in prices[period:]:
        ema.append((price - ema[-1]) * multiplier + ema[-1])
    return ema


def calculate_sma(prices: List[float], period: int) -> List[float]:
    """Calculate Simple Moving Average."""
    if len(prices) < period:
        return []
    return [sum(prices[i:i+period]) / period for i in range(len(prices) - period + 1)]


def calculate_rsi(prices: List[float], period: int = 14) -> float:
    """Calculate Relative Strength Index."""
    if len(prices) < period + 1:
        return 50.0
    
    gains, losses = [], []
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        gains.append(max(0, change))
        losses.append(max(0, -change))
    
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calculate_macd(prices: List[float]) -> dict:
    """Calculate MACD (12, 26, 9)."""
    if len(prices) < 26:
        return {"macd": 0, "signal": 0, "histogram": 0}
    
    ema12 = calculate_ema(prices, 12)
    ema26 = calculate_ema(prices, 26)
    
    if not ema12 or not ema26:
        return {"macd": 0, "signal": 0, "histogram": 0}
    
    # Align lengths
    min_len = min(len(ema12), len(ema26))
    macd_line = [ema12[-(min_len-i)] - ema26[-(min_len-i)] for i in range(min_len)]
    
    signal_line = calculate_ema(macd_line, 9) if len(macd_line) >= 9 else [0]
    
    macd_val = macd_line[-1] if macd_line else 0
    signal_val = signal_line[-1] if signal_line else 0
    
    return {
        "macd": round(macd_val, 6),
        "signal": round(signal_val, 6),
        "histogram": round(macd_val - signal_val, 6),
    }


def calculate_stochastic(highs: List[float], lows: List[float], closes: List[float], k_period: int = 14, d_period: int = 3) -> dict:
    """Calculate Stochastic Oscillator."""
    if len(closes) < k_period:
        return {"k": 50, "d": 50}
    
    k_values = []
    for i in range(k_period - 1, len(closes)):
        high_max = max(highs[i-k_period+1:i+1])
        low_min = min(lows[i-k_period+1:i+1])
        if high_max - low_min == 0:
            k_values.append(50)
        else:
            k_values.append(100 * (closes[i] - low_min) / (high_max - low_min))
    
    d_values = calculate_sma(k_values, d_period) if len(k_values) >= d_period else [50]
    
    return {
        "k": round(k_values[-1] if k_values else 50, 2),
        "d": round(d_values[-1] if d_values else 50, 2),
    }


def calculate_atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
    """Calculate Average True Range."""
    if len(closes) < period + 1:
        return 0.0
    
    tr_values = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
        tr_values.append(tr)
    
    return sum(tr_values[-period:]) / period if tr_values else 0


def calculate_adx(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> dict:
    """Calculate ADX and directional indicators."""
    if len(closes) < period + 1:
        return {"adx": 0, "plus_di": 0, "minus_di": 0}
    
    plus_dm, minus_dm, tr_values = [], [], []
    
    for i in range(1, len(closes)):
        high_diff = highs[i] - highs[i-1]
        low_diff = lows[i-1] - lows[i]
        
        plus_dm.append(high_diff if high_diff > low_diff and high_diff > 0 else 0)
        minus_dm.append(low_diff if low_diff > high_diff and low_diff > 0 else 0)
        
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        tr_values.append(tr)
    
    if len(tr_values) < period:
        return {"adx": 0, "plus_di": 0, "minus_di": 0}
    
    atr = sum(tr_values[-period:]) / period
    plus_dm_avg = sum(plus_dm[-period:]) / period
    minus_dm_avg = sum(minus_dm[-period:]) / period
    
    plus_di = (plus_dm_avg / atr * 100) if atr > 0 else 0
    minus_di = (minus_dm_avg / atr * 100) if atr > 0 else 0
    
    dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100 if (plus_di + minus_di) > 0 else 0
    
    return {
        "adx": round(dx, 2),
        "plus_di": round(plus_di, 2),
        "minus_di": round(minus_di, 2),
    }


def calculate_bollinger_bands(prices: List[float], period: int = 20, std_dev: float = 2.0) -> dict:
    """Calculate Bollinger Bands."""
    if len(prices) < period:
        return {"upper": 0, "middle": 0, "lower": 0, "width": 0, "squeeze": False}
    
    sma = sum(prices[-period:]) / period
    variance = sum((p - sma) ** 2 for p in prices[-period:]) / period
    std = math.sqrt(variance)
    
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    width = (upper - lower) / sma if sma > 0 else 0
    
    # Squeeze detection: width below 20-period average width
    historical_widths = []
    for i in range(period, len(prices)):
        hist_sma = sum(prices[i-period:i]) / period
        hist_var = sum((p - hist_sma) ** 2 for p in prices[i-period:i]) / period
        hist_std = math.sqrt(hist_var)
        hist_width = (hist_sma + std_dev * hist_std - (hist_sma - std_dev * hist_std)) / hist_sma if hist_sma > 0 else 0
        historical_widths.append(hist_width)
    
    avg_width = sum(historical_widths) / len(historical_widths) if historical_widths else width
    squeeze = width < avg_width * 0.8
    
    return {
        "upper": round(upper, 5),
        "middle": round(sma, 5),
        "lower": round(lower, 5),
        "width": round(width * 100, 2),
        "squeeze": squeeze,
    }


def calculate_donchian(highs: List[float], lows: List[float], period: int = 20) -> dict:
    """Calculate Donchian Channels."""
    if len(highs) < period:
        return {"upper": 0, "lower": 0, "middle": 0}
    
    upper = max(highs[-period:])
    lower = min(lows[-period:])
    middle = (upper + lower) / 2
    
    return {
        "upper": round(upper, 5),
        "lower": round(lower, 5),
        "middle": round(middle, 5),
    }


def calculate_pivot_points(high: float, low: float, close: float) -> dict:
    """Calculate classic pivot points."""
    pivot = (high + low + close) / 3
    r1 = 2 * pivot - low
    r2 = pivot + (high - low)
    r3 = high + 2 * (pivot - low)
    s1 = 2 * pivot - high
    s2 = pivot - (high - low)
    s3 = low - 2 * (high - pivot)
    
    return {
        "pivot": round(pivot, 5),
        "r1": round(r1, 5), "r2": round(r2, 5), "r3": round(r3, 5),
        "s1": round(s1, 5), "s2": round(s2, 5), "s3": round(s3, 5),
    }


# ═══════════════════════════════════════════════════════════════
# ANALYSIS FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def grade_trend_quality(ema_aligned: bool, adx: float, price_vs_emas: str) -> str:
    """Grade trend quality A-F."""
    score = 0
    if ema_aligned:
        score += 2
    if adx > 25:
        score += 2
    elif adx > 20:
        score += 1
    if price_vs_emas in ["above_all", "below_all"]:
        score += 1
    
    if score >= 5:
        return "A"
    elif score >= 4:
        return "B"
    elif score >= 3:
        return "C"
    elif score >= 2:
        return "D"
    return "F"


def detect_condition(bb_squeeze: bool, atr_trend: str, rsi: float, price_vs_ma: float) -> str:
    """Detect market condition."""
    if bb_squeeze:
        return "compression"
    if atr_trend == "expanding" and abs(price_vs_ma) < 0.5:
        return "expansion"
    if abs(price_vs_ma) > 2.0:  # More than 2 ATR from MA
        return "stretched"
    if abs(price_vs_ma) < 0.3 and 40 < rsi < 60:
        return "reversion"
    return "normal"


def check_mtf_alignment(tf_biases: Dict[str, str]) -> Tuple[str, int]:
    """Check multi-timeframe alignment."""
    bullish = sum(1 for b in tf_biases.values() if b == "bullish")
    bearish = sum(1 for b in tf_biases.values() if b == "bearish")
    total = len(tf_biases)
    
    if bullish == total:
        return "ALIGNED_BULLISH", 100
    if bearish == total:
        return "ALIGNED_BEARISH", 100
    if bullish >= total * 0.75:
        return "MOSTLY_BULLISH", 75
    if bearish >= total * 0.75:
        return "MOSTLY_BEARISH", 75
    if bullish > bearish:
        return "MIXED_BULLISH", 50
    if bearish > bullish:
        return "MIXED_BEARISH", 50
    return "CONFLICTING", 25


async def fetch_candles(symbol: str, timeframe: str) -> List[dict]:
    """Fetch candles from Curator using shared fetch_json."""
    data = await fetch_json(f"{CURATOR_URL}/api/snapshot/timeframe/{symbol}/{timeframe}")
    return data.get("candles", []) if data else []


async def analyze_symbol(symbol: str) -> dict:
    """Perform full technical analysis on a symbol."""
    tf_analyses = {}
    
    for tf in TIMEFRAMES:
        candles = await fetch_candles(symbol, tf)
        if len(candles) < 30:
            continue
        
        closes = [c["close"] for c in candles]
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        
        # Calculate all indicators
        ema8 = calculate_ema(closes, 8)
        ema21 = calculate_ema(closes, 21)
        ema50 = calculate_ema(closes, 50)
        ema200 = calculate_ema(closes, 200) if len(closes) >= 200 else []
        
        sma20 = calculate_sma(closes, 20)
        sma50 = calculate_sma(closes, 50)
        
        rsi = calculate_rsi(closes)
        macd = calculate_macd(closes)
        stoch = calculate_stochastic(highs, lows, closes)
        adx_data = calculate_adx(highs, lows, closes)
        atr = calculate_atr(highs, lows, closes)
        bb = calculate_bollinger_bands(closes)
        donchian = calculate_donchian(highs, lows)
        
        # Current price
        current_price = closes[-1]
        
        # EMA alignment check
        ema_values = []
        if ema8: ema_values.append(("ema8", ema8[-1]))
        if ema21: ema_values.append(("ema21", ema21[-1]))
        if ema50: ema_values.append(("ema50", ema50[-1]))
        if ema200: ema_values.append(("ema200", ema200[-1]))
        
        ema_bullish = all(ema_values[i][1] > ema_values[i+1][1] for i in range(len(ema_values)-1)) if len(ema_values) > 1 else False
        ema_bearish = all(ema_values[i][1] < ema_values[i+1][1] for i in range(len(ema_values)-1)) if len(ema_values) > 1 else False
        ema_aligned = ema_bullish or ema_bearish
        
        # Price position vs EMAs
        if ema_values:
            above_count = sum(1 for _, v in ema_values if current_price > v)
            if above_count == len(ema_values):
                price_vs_emas = "above_all"
            elif above_count == 0:
                price_vs_emas = "below_all"
            else:
                price_vs_emas = "mixed"
        else:
            price_vs_emas = "unknown"
        
        # Determine bias
        bullish_signals = 0
        bearish_signals = 0
        
        if ema_bullish: bullish_signals += 2
        if ema_bearish: bearish_signals += 2
        if price_vs_emas == "above_all": bullish_signals += 1
        if price_vs_emas == "below_all": bearish_signals += 1
        if rsi > 55: bullish_signals += 1
        if rsi < 45: bearish_signals += 1
        if macd["histogram"] > 0: bullish_signals += 1
        if macd["histogram"] < 0: bearish_signals += 1
        if adx_data["plus_di"] > adx_data["minus_di"]: bullish_signals += 1
        if adx_data["minus_di"] > adx_data["plus_di"]: bearish_signals += 1
        
        if bullish_signals > bearish_signals + 2:
            bias = "bullish"
        elif bearish_signals > bullish_signals + 2:
            bias = "bearish"
        else:
            bias = "neutral"
        
        # Calculate distance from MA in ATR units
        ma_distance = (current_price - (sma20[-1] if sma20 else current_price)) / atr if atr > 0 else 0
        
        # Trend quality grade
        trend_grade = grade_trend_quality(ema_aligned, adx_data["adx"], price_vs_emas)
        
        # Condition detection
        atr_trend = "normal"  # Would need historical ATR for proper detection
        condition = detect_condition(bb["squeeze"], atr_trend, rsi, ma_distance)
        
        # Previous day high/low (use D1 data)
        pdh = max(highs[-2:-1]) if len(highs) > 1 else highs[-1] if highs else 0
        pdl = min(lows[-2:-1]) if len(lows) > 1 else lows[-1] if lows else 0
        
        # Pivots (from previous candle)
        if len(candles) > 1:
            pivots = calculate_pivot_points(candles[-2]["high"], candles[-2]["low"], candles[-2]["close"])
        else:
            pivots = {}
        
        tf_analyses[tf] = {
            "bias": bias,
            "trend_grade": trend_grade,
            "condition": condition,
            "indicators": {
                "rsi": round(rsi, 2),
                "macd": macd,
                "stochastic": stoch,
                "adx": adx_data,
                "atr": round(atr, 6),
                "bollinger": bb,
                "donchian": donchian,
            },
            "emas": {k: round(v, 5) for k, v in ema_values},
            "ema_aligned": ema_aligned,
            "price_vs_emas": price_vs_emas,
            "pivots": pivots,
            "pdh": round(pdh, 5),
            "pdl": round(pdl, 5),
            "current_price": round(current_price, 5),
        }
    
    if not tf_analyses:
        return {"error": "No data"}
    
    # Multi-timeframe alignment
    tf_biases = {tf: data["bias"] for tf, data in tf_analyses.items()}
    mtf_alignment, mtf_confidence = check_mtf_alignment(tf_biases)
    
    # Overall analysis
    primary_tf = "H1" if "H1" in tf_analyses else list(tf_analyses.keys())[0]
    primary = tf_analyses[primary_tf]
    
    # Determine directional lean
    bullish_tfs = sum(1 for b in tf_biases.values() if b == "bullish")
    bearish_tfs = sum(1 for b in tf_biases.values() if b == "bearish")
    
    if bullish_tfs > bearish_tfs:
        directional_lean = "bullish"
    elif bearish_tfs > bullish_tfs:
        directional_lean = "bearish"
    else:
        directional_lean = "neutral"
    
    # Confidence score
    base_confidence = mtf_confidence
    if primary["trend_grade"] in ["A", "B"]:
        base_confidence += 10
    if primary["condition"] in ["normal", "expansion"]:
        base_confidence += 5
    confidence = min(base_confidence, 95)
    
    # Supporting and contradictory evidence
    supporting = []
    contradictory = []
    
    if primary["ema_aligned"]:
        supporting.append(f"EMA stack aligned ({primary['price_vs_emas']})")
    else:
        contradictory.append("EMAs not aligned")
    
    if primary["indicators"]["adx"]["adx"] > 25:
        supporting.append(f"Strong trend (ADX {primary['indicators']['adx']['adx']})")
    elif primary["indicators"]["adx"]["adx"] < 15:
        contradictory.append(f"Weak trend (ADX {primary['indicators']['adx']['adx']})")
    
    rsi_val = primary["indicators"]["rsi"]
    if directional_lean == "bullish" and rsi_val < 70:
        supporting.append(f"RSI not overbought ({rsi_val})")
    elif directional_lean == "bearish" and rsi_val > 30:
        supporting.append(f"RSI not oversold ({rsi_val})")
    elif rsi_val > 70:
        contradictory.append(f"RSI overbought ({rsi_val})")
    elif rsi_val < 30:
        contradictory.append(f"RSI oversold ({rsi_val})")
    
    if primary["indicators"]["bollinger"]["squeeze"]:
        supporting.append("Bollinger squeeze (compression)")
    
    # Invalidation level
    if directional_lean == "bullish":
        invalidation = primary.get("pdl", primary["current_price"] * 0.99)
        setup_type = "Pullback Long" if primary["condition"] == "normal" else "Breakout Long"
    elif directional_lean == "bearish":
        invalidation = primary.get("pdh", primary["current_price"] * 1.01)
        setup_type = "Pullback Short" if primary["condition"] == "normal" else "Breakout Short"
    else:
        invalidation = 0
        setup_type = "No Setup"
    
    # Entry style
    if primary["condition"] == "compression":
        entry_style = "Wait for breakout"
    elif primary["condition"] == "stretched":
        entry_style = "Wait for reversion"
    elif primary["trend_grade"] in ["A", "B"]:
        entry_style = "Limit order at EMA pullback"
    else:
        entry_style = "No entry recommended"
    
    return {
        "symbol": symbol,
        "directional_lean": directional_lean,
        "confidence": confidence,
        "setup_type": setup_type,
        "invalidation": round(invalidation, 5),
        "entry_style": entry_style,
        "trend_grade": primary["trend_grade"],
        "condition": primary["condition"],
        "mtf_alignment": mtf_alignment,
        "supporting_evidence": supporting,
        "contradictory_evidence": contradictory,
        "timeframes": tf_analyses,
        "timestamp": datetime.utcnow().isoformat(),
    }


async def send_to_orchestrator(symbol: str, analysis: dict):
    """Send analysis to Orchestrator using shared post_json."""
    await post_json(
        f"{ORCHESTRATOR_URL}/api/ingest",
        {
            "agent_id": "technical",
            "agent_name": AGENT_NAME,
            "output_type": "signal",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "symbol": symbol,
                "direction": analysis["directional_lean"],
                "confidence": analysis["confidence"] / 100,
                "reason": f"{analysis['setup_type']} - {analysis['mtf_alignment']}",
                "invalidation": analysis["invalidation"],
            },
        }
    )


async def background_analysis():
    """Background analysis loop."""
    while True:
        for symbol in SYMBOLS:
            try:
                analysis = await analyze_symbol(symbol)
                if "error" not in analysis:
                    analysis_cache[symbol] = analysis
                    await send_to_orchestrator(symbol, analysis)
            except Exception as e:
                print(f"[Atlas Jr.] Error analyzing {symbol}: {e}")
        await asyncio.sleep(60)


# Using shared call_claude - removed duplicate implementation


@app.on_event("startup")
async def startup():
    print(f"🚀 {AGENT_NAME} (Technical Analysis Agent) v2.0 starting...")
    asyncio.create_task(background_analysis())


@app.get("/", response_class=HTMLResponse)
async def home():
    cards_html = ""
    for symbol in SYMBOLS:
        a = analysis_cache.get(symbol, {})
        lean = a.get("directional_lean", "?")
        conf = a.get("confidence", 0)
        grade = a.get("trend_grade", "?")
        condition = a.get("condition", "?")
        mtf = a.get("mtf_alignment", "?")
        setup = a.get("setup_type", "?")
        
        lean_color = "#22c55e" if lean == "bullish" else "#ef4444" if lean == "bearish" else "#888"
        grade_color = "#22c55e" if grade in ["A", "B"] else "#f59e0b" if grade == "C" else "#ef4444"
        
        cards_html += f'''
        <div class="card">
            <div class="card-header">
                <span class="symbol">{symbol}</span>
                <span class="confidence">{conf}%</span>
            </div>
            <div class="lean" style="color:{lean_color}">{lean.upper()}</div>
            <div class="meta">
                <span class="grade" style="background:{grade_color}20;color:{grade_color}">Grade {grade}</span>
                <span class="condition">{condition}</span>
            </div>
            <div class="setup">{setup}</div>
            <div class="mtf">{mtf}</div>
        </div>
        '''
    
    return f'''<!DOCTYPE html>
<html><head>
    <title>📊 Atlas Jr. - Technical Agent</title>
    <meta http-equiv="refresh" content="30">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, sans-serif; background: #0a0a0f; color: #e0e0e0; padding: 20px; }}
        .header {{ display: flex; align-items: center; gap: 15px; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid #333; }}
        .header h1 {{ color: #22c55e; }}
        .status {{ background: #22c55e20; color: #22c55e; padding: 5px 12px; border-radius: 20px; font-size: 14px; }}
        .grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-bottom: 20px; }}
        .card {{ background: #1a1a24; border-radius: 10px; padding: 15px; }}
        .card-header {{ display: flex; justify-content: space-between; margin-bottom: 8px; }}
        .symbol {{ font-size: 16px; font-weight: bold; }}
        .confidence {{ font-size: 14px; color: #22c55e; }}
        .lean {{ font-size: 18px; font-weight: bold; margin-bottom: 8px; }}
        .meta {{ display: flex; gap: 10px; margin-bottom: 8px; }}
        .grade {{ padding: 2px 8px; border-radius: 4px; font-size: 11px; }}
        .condition {{ font-size: 11px; color: #888; }}
        .setup {{ font-size: 12px; color: #aaa; margin-bottom: 4px; }}
        .mtf {{ font-size: 11px; color: #666; }}
        .chat-section {{ background: #1a1a24; border-radius: 12px; padding: 20px; }}
        .chat-section h2 {{ color: #22c55e; margin-bottom: 15px; }}
        .chat-messages {{ height: 200px; overflow-y: auto; background: #0a0a0f; border-radius: 8px; padding: 10px; margin-bottom: 10px; }}
        .chat-input {{ display: flex; gap: 10px; }}
        .chat-input input {{ flex: 1; padding: 10px; border-radius: 8px; border: 1px solid #333; background: #0a0a0f; color: #fff; }}
        .chat-input button {{ padding: 10px 20px; background: #22c55e; color: #000; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; }}
        .message {{ margin: 8px 0; padding: 8px; border-radius: 6px; font-size: 13px; white-space: pre-wrap; }}
        .message.user {{ background: #333; margin-left: 20%; }}
        .message.agent {{ background: #0a3d0a; margin-right: 20%; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 Atlas Jr.</h1>
        <span class="status">● ANALYZING</span>
        <span style="color: #888; margin-left: auto;">Technical Analysis Agent v2.0 • {len(analysis_cache)} pairs</span>
    </div>
    <div class="grid">{cards_html}</div>
    <div class="chat-section">
        <h2>💬 Ask Atlas Jr.</h2>
        <div class="chat-messages" id="messages"></div>
        <div class="chat-input">
            <input type="text" id="input" placeholder="Ask about technicals..." onkeypress="if(event.key==='Enter')sendMessage()">
            <button onclick="sendMessage()">Send</button>
        </div>
    </div>
    <script>
        const CHAT_KEY = 'atlasjr_chat_history';
        
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
    context = f"Current analysis:\n{json.dumps(analysis_cache, indent=2, default=str)[:8000]}"
    response = await call_claude(request.message, context, agent_name=AGENT_NAME)
    return {"response": response}


@app.get("/api/analysis")
async def get_all_analysis():
    return analysis_cache


@app.get("/api/analysis/{symbol}")
async def get_symbol_analysis(symbol: str):
    symbol = symbol.upper()
    if symbol not in analysis_cache:
        analysis = await analyze_symbol(symbol)
        analysis_cache[symbol] = analysis
    return analysis_cache.get(symbol, {"error": "Not found"})


@app.get("/api/status")
async def get_status():
    return {
        "agent_id": "technical",
        "name": AGENT_NAME,
        "status": "active",
        "symbols_analyzed": len(analysis_cache),
        "version": "2.0",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, access_log=False)
