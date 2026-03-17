"""
Market Data Agent - Curator
Data ingestion, validation, quality scoring, and distribution
"""

import os
import json
import asyncio
import httpx
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from enum import Enum
import csv
from collections import defaultdict
import logging

# TimescaleDB integration
try:
    from timescale_store import get_store, TimescaleStore
    TIMESCALE_AVAILABLE = True
except ImportError:
    TIMESCALE_AVAILABLE = False
    print("⚠️ TimescaleDB module not available, running in-memory only")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Curator - Market Data Agent", version="2.0")

# Configuration
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://orchestrator-agent:8000")
QUALITY_THRESHOLD = float(os.getenv("QUALITY_THRESHOLD", "0.7"))
AGENT_NAME = "Curator"
WORKSPACE = Path("/app/workspace")

# MT5 data paths (mounted from host)
MT5_DATA_PATH = Path("/app/mt5_data")
CANDLE_FILE = MT5_DATA_PATH / "candle_data.csv"
MARKET_FILE = MT5_DATA_PATH / "market_data.csv"
ACCOUNT_FILE = MT5_DATA_PATH / "account_data.json"
POSITIONS_FILE = MT5_DATA_PATH / "positions.json"
BRIDGE_STATUS_FILE = MT5_DATA_PATH / "bridge_status.json"

# Symbols and timeframes
SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "GBPJPY", "USDCHF", "USDCAD", "EURAUD", "AUDNZD", "AUDUSD"]
TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]
TIMEFRAME_MINUTES = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}

# Broker symbol configuration
# Some brokers use suffixes like ".s", ".r", "m" etc.
SYMBOL_SUFFIX = os.getenv("SYMBOL_SUFFIX", "")  # e.g., ".s" for JustMarkets


def broker_symbol(symbol: str) -> str:
    """Convert internal symbol to broker symbol (add suffix)."""
    if SYMBOL_SUFFIX and not symbol.endswith(SYMBOL_SUFFIX):
        return symbol + SYMBOL_SUFFIX
    return symbol


def internal_symbol(broker_sym: str) -> str:
    """Convert broker symbol to internal symbol (strip suffix)."""
    if SYMBOL_SUFFIX and broker_sym.endswith(SYMBOL_SUFFIX):
        return broker_sym[:-len(SYMBOL_SUFFIX)]
    return broker_sym

# Trading sessions (UTC hours)
SESSIONS = {
    "Sydney": (21, 6),
    "Tokyo": (0, 9),
    "London": (7, 16),
    "NewYork": (12, 21),
}

# State
data_cache: Dict[str, Dict[str, dict]] = {}  # symbol -> timeframe -> data
quality_scores: Dict[str, dict] = {}  # symbol -> quality metrics
spread_history: Dict[str, List[float]] = defaultdict(list)
circuit_breaker_active = False
last_ingest = None

class ChatRequest(BaseModel):
    message: str

class QualityStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    HALTED = "halted"


def get_current_session() -> str:
    """Determine current trading session."""
    utc_hour = datetime.utcnow().hour
    for session, (start, end) in SESSIONS.items():
        if start <= end:
            if start <= utc_hour < end:
                return session
        else:  # Crosses midnight
            if utc_hour >= start or utc_hour < end:
                return session
    return "Off-hours"


def parse_mt5_timestamp(ts_str: str) -> Optional[datetime]:
    """Parse MT5 timestamp formats."""
    formats = [
        "%Y.%m.%d %H:%M:%S",
        "%Y.%m.%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(ts_str.strip(), fmt)
        except ValueError:
            continue
    return None


def validate_ohlc(o: float, h: float, l: float, c: float) -> Tuple[bool, List[str]]:
    """Validate OHLC integrity."""
    errors = []
    if h < o or h < c:
        errors.append("High < Open or Close")
    if l > o or l > c:
        errors.append("Low > Open or Close")
    if h < l:
        errors.append("High < Low")
    if any(v <= 0 for v in [o, h, l, c]):
        errors.append("Non-positive price")
    return len(errors) == 0, errors


def calculate_spread_pips(symbol: str, bid: float, ask: float) -> float:
    """Calculate spread in pips."""
    if "JPY" in symbol:
        return (ask - bid) * 100
    return (ask - bid) * 10000


def detect_missing_bars(candles: List[dict], timeframe: str) -> List[dict]:
    """Detect missing bars in candle sequence."""
    if len(candles) < 2:
        return []
    
    missing = []
    interval_minutes = TIMEFRAME_MINUTES.get(timeframe, 30)
    
    for i in range(1, len(candles)):
        prev_time = candles[i-1].get("timestamp")
        curr_time = candles[i].get("timestamp")
        
        if prev_time and curr_time:
            expected_diff = timedelta(minutes=interval_minutes)
            actual_diff = curr_time - prev_time
            
            if actual_diff > expected_diff * 1.5:  # Allow some tolerance
                missing.append({
                    "after": prev_time.isoformat(),
                    "before": curr_time.isoformat(),
                    "expected_bars": int(actual_diff.total_seconds() / (interval_minutes * 60)) - 1
                })
    
    return missing


def detect_duplicates(candles: List[dict]) -> List[dict]:
    """Detect duplicate candles."""
    seen = set()
    duplicates = []
    
    for candle in candles:
        ts = candle.get("timestamp")
        if ts:
            key = ts.isoformat()
            if key in seen:
                duplicates.append(candle)
            seen.add(key)
    
    return duplicates


def calculate_quality_score(symbol: str, data: dict) -> dict:
    """Calculate comprehensive quality score for a symbol."""
    scores = {}
    issues = []
    
    # Freshness score (0-1)
    last_update = data.get("last_update")
    if last_update:
        age_seconds = (datetime.utcnow() - last_update).total_seconds()
        if age_seconds < 60:
            scores["freshness"] = 1.0
        elif age_seconds < 300:
            scores["freshness"] = 0.8
        elif age_seconds < 600:
            scores["freshness"] = 0.5
        else:
            scores["freshness"] = 0.2
            issues.append(f"Stale data: {age_seconds:.0f}s old")
    else:
        scores["freshness"] = 0.0
        issues.append("No timestamp")
    
    # Completeness score
    expected_bars = data.get("expected_bars", 0)
    received_bars = data.get("received_bars", 0)
    if expected_bars > 0:
        scores["completeness"] = min(received_bars / expected_bars, 1.0)
        if scores["completeness"] < 0.9:
            issues.append(f"Missing bars: {expected_bars - received_bars}")
    else:
        scores["completeness"] = 1.0
    
    # Integrity score
    ohlc_valid = data.get("ohlc_valid", True)
    no_duplicates = data.get("no_duplicates", True)
    
    integrity = 1.0
    if not ohlc_valid:
        integrity -= 0.3
        issues.append("OHLC integrity failed")
    if not no_duplicates:
        integrity -= 0.2
        issues.append("Duplicate candles detected")
    scores["integrity"] = max(integrity, 0.0)
    
    # Spread score
    spread = data.get("spread_pips", 0)
    avg_spread = data.get("avg_spread", spread)
    if avg_spread > 0:
        spread_ratio = spread / avg_spread
        if spread_ratio <= 1.5:
            scores["spread"] = 1.0
        elif spread_ratio <= 2.0:
            scores["spread"] = 0.7
        elif spread_ratio <= 3.0:
            scores["spread"] = 0.4
            issues.append(f"Wide spread: {spread:.1f} pips")
        else:
            scores["spread"] = 0.1
            issues.append(f"Very wide spread: {spread:.1f} pips")
    else:
        scores["spread"] = 0.8  # No reference
    
    # Overall score (weighted average)
    weights = {"freshness": 0.3, "completeness": 0.3, "integrity": 0.25, "spread": 0.15}
    overall = sum(scores.get(k, 0) * w for k, w in weights.items())
    
    # Determine status
    if overall >= 0.85:
        status = QualityStatus.HEALTHY
    elif overall >= 0.7:
        status = QualityStatus.DEGRADED
    elif overall >= 0.5:
        status = QualityStatus.CRITICAL
    else:
        status = QualityStatus.HALTED
    
    return {
        "symbol": symbol,
        "scores": scores,
        "overall": round(overall, 3),
        "status": status.value,
        "issues": issues,
        "tradeable": overall >= QUALITY_THRESHOLD and not circuit_breaker_active,
        "timestamp": datetime.utcnow().isoformat(),
    }


async def ingest_market_data():
    """Ingest current market data from MT5 files - TAB separated, UTF-16."""
    global last_ingest
    
    market_data = {}
    
    # Read market_data.csv (current prices) - TAB separated, UTF-16 encoded
    if MARKET_FILE.exists():
        try:
            with open(MARKET_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                
                # Skip header
                for line in lines[1:]:
                    parts = line.strip().split('\t')
                    if len(parts) < 4:
                        continue
                    
                    try:
                        symbol = internal_symbol(parts[0].strip())  # Strip broker suffix
                        
                        if symbol not in SYMBOLS:
                            continue
                        
                        bid = float(parts[1])
                        ask = float(parts[2])
                        spread = calculate_spread_pips(symbol, bid, ask)
                        
                        market_data[symbol] = {
                            "symbol": symbol,
                            "bid": bid,
                            "ask": ask,
                            "spread_pips": round(spread, 2),
                            "last_update": datetime.utcnow(),
                        }
                        
                        # Track spread history
                        spread_history[symbol].append(spread)
                        if len(spread_history[symbol]) > 100:
                            spread_history[symbol] = spread_history[symbol][-100:]
                    except (ValueError, IndexError):
                        continue
                        
            print(f"[Curator] Loaded market data: {len(market_data)} symbols")
        except Exception as e:
            print(f"[Curator] Error reading market data: {e}")
    
    last_ingest = datetime.utcnow()
    return market_data


async def ingest_candle_data():
    """Ingest candle data from MT5 files - TAB separated."""
    candle_data = defaultdict(lambda: defaultdict(list))
    
    print(f"[Curator] Reading candle file: {CANDLE_FILE}, exists: {CANDLE_FILE.exists()}")
    print(f"[Curator] SYMBOL_SUFFIX: '{SYMBOL_SUFFIX}'")
    
    if CANDLE_FILE.exists():
        try:
            with open(CANDLE_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                
                print(f"[Curator] Read {len(lines)} lines from candle file")
                
                matched = 0
                # Skip header
                for line in lines[1:]:
                    parts = line.strip().split('\t')
                    if len(parts) < 8:
                        continue
                    
                    try:
                        symbol = internal_symbol(parts[0].strip())  # Strip broker suffix
                        timeframe = parts[1].strip()
                        
                        if symbol not in SYMBOLS or timeframe not in TIMEFRAMES:
                            continue
                        
                        # Parse timestamp (format: "2026.03.12 17:16:00" or Unix)
                        ts_str = parts[2].strip()
                        try:
                            if '.' in ts_str and ':' in ts_str:
                                # MT5 format: "2026.03.12 17:16:00"
                                ts = datetime.strptime(ts_str, "%Y.%m.%d %H:%M:%S")
                            else:
                                # Unix timestamp
                                ts = datetime.utcfromtimestamp(int(ts_str))
                        except:
                            continue
                        
                        o = float(parts[3])
                        h = float(parts[4])
                        l = float(parts[5])
                        c = float(parts[6])
                        v = float(parts[7])
                        
                        valid, errors = validate_ohlc(o, h, l, c)
                        
                        candle_data[symbol][timeframe].append({
                            "timestamp": ts,
                            "open": o,
                            "high": h,
                            "low": l,
                            "close": c,
                            "volume": v,
                            "valid": valid,
                            "errors": errors,
                        })
                        matched += 1
                    except (ValueError, IndexError) as e:
                        continue
                
                print(f"[Curator] Matched {matched} candles")
            total_bars = sum(len(tfs) for sym in candle_data.values() for tfs in sym.values())
            print(f"[Curator] Loaded candles: {total_bars} bars")
        except Exception as e:
            print(f"[Curator] Error reading candle data: {e}")
    
    return candle_data


async def process_and_validate():
    """Main processing loop: ingest, validate, score, distribute."""
    global circuit_breaker_active, data_cache, quality_scores
    
    # Ingest data
    market_data = await ingest_market_data()
    candle_data = await ingest_candle_data()
    
    # Store in TimescaleDB (persistent storage)
    if TIMESCALE_AVAILABLE:
        try:
            store = get_store()
            if store.enabled:
                # Convert candle data for storage
                candles_to_store = []
                for symbol, timeframes in candle_data.items():
                    for tf, candles in timeframes.items():
                        for c in candles:
                            candles_to_store.append({
                                'time': c['timestamp'],
                                'symbol': symbol,
                                'timeframe': tf,
                                'open': c['open'],
                                'high': c['high'],
                                'low': c['low'],
                                'close': c['close'],
                                'volume': c.get('volume', 0),
                                'spread': 0  # Will update with market data
                            })
                
                if candles_to_store:
                    stored = store.store_candles(candles_to_store)
                    if stored > 0:
                        logger.info(f"📦 Stored {stored} candles in TimescaleDB")
        except Exception as e:
            logger.error(f"TimescaleDB storage error: {e}")
    
    # Process each symbol
    for symbol in SYMBOLS:
        symbol_data = market_data.get(symbol, {})
        
        # Add candle metrics
        for tf in TIMEFRAMES:
            candles = candle_data.get(symbol, {}).get(tf, [])
            
            if candles:
                # Detect issues
                missing = detect_missing_bars(candles, tf)
                duplicates = detect_duplicates(candles)
                ohlc_valid = all(c.get("valid", True) for c in candles)
                
                # Store in cache
                if symbol not in data_cache:
                    data_cache[symbol] = {}
                
                data_cache[symbol][tf] = {
                    "candles": candles[-50:],  # Keep last 50
                    "missing_bars": missing,
                    "duplicates": len(duplicates),
                    "ohlc_valid": ohlc_valid,
                    "bar_count": len(candles),
                }
        
        # Calculate ATR for volatility
        h1_candles = candle_data.get(symbol, {}).get("H1", [])
        if len(h1_candles) >= 14:
            atr_values = []
            for i in range(1, min(15, len(h1_candles))):
                tr = max(
                    h1_candles[i]["high"] - h1_candles[i]["low"],
                    abs(h1_candles[i]["high"] - h1_candles[i-1]["close"]),
                    abs(h1_candles[i]["low"] - h1_candles[i-1]["close"])
                )
                atr_values.append(tr)
            atr = sum(atr_values) / len(atr_values) if atr_values else 0
            symbol_data["atr"] = atr
            symbol_data["atr_pips"] = atr * (100 if "JPY" in symbol else 10000)
        
        # Calculate quality score
        symbol_data["last_update"] = symbol_data.get("last_update") or datetime.utcnow()
        symbol_data["received_bars"] = sum(len(candle_data.get(symbol, {}).get(tf, [])) for tf in TIMEFRAMES)
        symbol_data["expected_bars"] = 50 * len(TIMEFRAMES)  # Rough expectation
        symbol_data["ohlc_valid"] = all(
            data_cache.get(symbol, {}).get(tf, {}).get("ohlc_valid", True) 
            for tf in TIMEFRAMES
        )
        symbol_data["no_duplicates"] = all(
            data_cache.get(symbol, {}).get(tf, {}).get("duplicates", 0) == 0
            for tf in TIMEFRAMES
        )
        symbol_data["avg_spread"] = (
            sum(spread_history[symbol]) / len(spread_history[symbol])
            if spread_history[symbol] else symbol_data.get("spread_pips", 2.0)
        )
        
        quality_scores[symbol] = calculate_quality_score(symbol, symbol_data)
    
    # Check circuit breaker
    avg_quality = sum(q.get("overall", 0) for q in quality_scores.values()) / len(quality_scores) if quality_scores else 0
    
    if avg_quality < QUALITY_THRESHOLD and not circuit_breaker_active:
        circuit_breaker_active = True
        await send_alert("critical", f"Circuit breaker ACTIVATED: avg quality {avg_quality:.2f} < {QUALITY_THRESHOLD}")
    elif avg_quality >= QUALITY_THRESHOLD and circuit_breaker_active:
        circuit_breaker_active = False
        await send_alert("info", f"Circuit breaker DEACTIVATED: quality recovered to {avg_quality:.2f}")


async def send_alert(level: str, message: str):
    """Send alert to Orchestrator."""
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{ORCHESTRATOR_URL}/api/ingest",
                json={
                    "agent_id": "data",
                    "agent_name": AGENT_NAME,
                    "output_type": "alert",
                    "timestamp": datetime.utcnow().isoformat(),
                    "data": {"level": level, "message": message},
                },
                timeout=5.0
            )
    except:
        pass


async def send_snapshot(symbol: str):
    """Send symbol snapshot to Orchestrator."""
    quality = quality_scores.get(symbol, {})
    
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{ORCHESTRATOR_URL}/api/ingest",
                json={
                    "agent_id": "data",
                    "agent_name": AGENT_NAME,
                    "output_type": "analysis",
                    "timestamp": datetime.utcnow().isoformat(),
                    "data": {
                        "symbol": symbol,
                        "quality_score": quality.get("overall", 0),
                        "tradeable": quality.get("tradeable", False),
                        "status": quality.get("status", "unknown"),
                    },
                },
                timeout=5.0
            )
    except:
        pass


async def background_loop():
    """Background processing loop."""
    while True:
        try:
            await process_and_validate()
            # Send snapshots to Orchestrator
            for symbol in SYMBOLS:
                await send_snapshot(symbol)
        except Exception as e:
            print(f"[Curator] Background loop error: {e}")
        await asyncio.sleep(1)  # Every 1 second for real-time monitoring


async def call_claude(prompt: str, context: str = "") -> str:
    if not ANTHROPIC_API_KEY:
        return "[No API key]"
    soul = (WORKSPACE / "SOUL.md").read_text() if (WORKSPACE / "SOUL.md").exists() else ""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": "claude-sonnet-4-20250514", "max_tokens": 1024, "system": soul,
                      "messages": [{"role": "user", "content": f"{context}\n\n{prompt}" if context else prompt}]},
                timeout=30.0
            )
            if r.status_code == 200:
                return r.json()["content"][0]["text"]
    except:
        pass
    return "[Error]"


@app.on_event("startup")
async def startup():
    print(f"🚀 {AGENT_NAME} (Market Data Agent) starting...")
    print(f"   Quality threshold: {QUALITY_THRESHOLD}")
    print(f"   MT5 data path: {MT5_DATA_PATH}")
    asyncio.create_task(background_loop())


@app.get("/", response_class=HTMLResponse)
async def home():
    session = get_current_session()
    
    # Build quality cards
    cards_html = ""
    for symbol in SYMBOLS:
        q = quality_scores.get(symbol, {"overall": 0, "status": "unknown", "tradeable": False, "issues": []})
        score = q.get("overall", 0) * 100
        status = q.get("status", "unknown")
        tradeable = q.get("tradeable", False)
        issues = q.get("issues", [])
        
        # Color based on status
        if status == "healthy":
            color = "#22c55e"
        elif status == "degraded":
            color = "#f59e0b"
        elif status == "critical":
            color = "#ef4444"
        else:
            color = "#666"
        
        issues_html = "".join([f"<div class='issue'>⚠️ {i}</div>" for i in issues[:2]])
        
        cards_html += f'''
        <div class="card" style="border-left: 4px solid {color}">
            <div class="card-header">
                <span class="symbol">{symbol}</span>
                <span class="score" style="color:{color}">{score:.0f}%</span>
            </div>
            <div class="status">{status.upper()}</div>
            <div class="tradeable">{"✅ Tradeable" if tradeable else "❌ Not tradeable"}</div>
            {issues_html}
        </div>
        '''
    
    circuit_html = f'''
        <div class="circuit {'active' if circuit_breaker_active else ''}">
            🔌 Circuit Breaker: {"🔴 ACTIVE - TRADING HALTED" if circuit_breaker_active else "🟢 OK"}
        </div>
    '''
    
    return f'''<!DOCTYPE html>
<html><head>
    <title>📡 Curator - Market Data Agent</title>
    <meta http-equiv="refresh" content="10">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, sans-serif; background: #0a0a0f; color: #e0e0e0; padding: 20px; }}
        .header {{ display: flex; align-items: center; gap: 15px; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid #333; }}
        .header h1 {{ color: #06b6d4; }}
        .status-badge {{ background: #22c55e20; color: #22c55e; padding: 5px 12px; border-radius: 20px; font-size: 14px; }}
        .session {{ background: #3b82f620; color: #3b82f6; padding: 5px 12px; border-radius: 20px; font-size: 14px; }}
        .circuit {{ background: #1a1a24; padding: 15px; border-radius: 8px; margin-bottom: 20px; font-weight: 600; }}
        .circuit.active {{ background: #7f1d1d; color: #fca5a5; }}
        .grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-bottom: 20px; }}
        .card {{ background: #1a1a24; border-radius: 10px; padding: 15px; }}
        .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
        .symbol {{ font-size: 16px; font-weight: bold; }}
        .score {{ font-size: 18px; font-weight: bold; }}
        .status {{ font-size: 12px; color: #888; margin-bottom: 5px; }}
        .tradeable {{ font-size: 12px; margin-bottom: 8px; }}
        .issue {{ font-size: 11px; color: #f59e0b; margin: 3px 0; }}
        .metrics {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 20px; }}
        .metric {{ background: #1a1a24; border-radius: 10px; padding: 15px; text-align: center; }}
        .metric-value {{ font-size: 24px; font-weight: bold; color: #06b6d4; }}
        .metric-label {{ font-size: 12px; color: #888; }}
        .chat-section {{ background: #1a1a24; border-radius: 12px; padding: 20px; }}
        .chat-section h2 {{ color: #06b6d4; margin-bottom: 15px; }}
        .chat-messages {{ height: 150px; overflow-y: auto; background: #0a0a0f; border-radius: 8px; padding: 10px; margin-bottom: 10px; }}
        .chat-input {{ display: flex; gap: 10px; }}
        .chat-input input {{ flex: 1; padding: 10px; border-radius: 8px; border: 1px solid #333; background: #0a0a0f; color: #fff; }}
        .chat-input button {{ padding: 10px 20px; background: #06b6d4; color: #000; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; }}
        .message {{ margin: 8px 0; padding: 8px; border-radius: 6px; font-size: 13px; }}
        .message.user {{ background: #333; margin-left: 20%; }}
        .message.agent {{ background: #0a3d4d; margin-right: 20%; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📡 Curator</h1>
        <span class="status-badge">● INGESTING</span>
        <span class="session">Session: {session}</span>
        <span style="color: #888; margin-left: auto;">Market Data Agent • Threshold: {QUALITY_THRESHOLD}</span>
    </div>
    
    {circuit_html}
    
    <div class="metrics">
        <div class="metric">
            <div class="metric-value">{len([q for q in quality_scores.values() if q.get('tradeable')])}/{len(SYMBOLS)}</div>
            <div class="metric-label">Tradeable Symbols</div>
        </div>
        <div class="metric">
            <div class="metric-value">{sum(q.get('overall', 0) for q in quality_scores.values()) / len(quality_scores) * 100 if quality_scores else 0:.0f}%</div>
            <div class="metric-label">Avg Quality</div>
        </div>
        <div class="metric">
            <div class="metric-value">{len([q for q in quality_scores.values() if q.get('issues')])}</div>
            <div class="metric-label">Symbols with Issues</div>
        </div>
        <div class="metric">
            <div class="metric-value">{(datetime.utcnow() - last_ingest).seconds if last_ingest else '?'}s</div>
            <div class="metric-label">Last Ingest</div>
        </div>
    </div>
    
    <div class="grid">{cards_html}</div>
    
    <div class="chat-section">
        <h2>💬 Ask Curator</h2>
        <div class="chat-messages" id="messages"></div>
        <div class="chat-input">
            <input type="text" id="input" placeholder="Ask about data quality..." onkeypress="if(event.key==='Enter')sendMessage()">
            <button onclick="sendMessage()">Send</button>
        </div>
    </div>
    
    <script>
        const CHAT_KEY = 'curator_chat_history';
        
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
    context = f"""Current Quality Scores:
{json.dumps(quality_scores, indent=2, default=str)}

Circuit Breaker: {'ACTIVE' if circuit_breaker_active else 'OK'}
Session: {get_current_session()}
Last Ingest: {last_ingest.isoformat() if last_ingest else 'Never'}
"""
    return {"response": await call_claude(request.message, context)}


# === Live Data Ingestion Endpoints (MT5 Bridge) ===

class TickData(BaseModel):
    symbols: Dict[str, dict]

class CandleData(BaseModel):
    candles: Dict[str, Dict[str, List[dict]]]  # symbol -> timeframe -> candles

# In-memory live market data
live_market_data: Dict[str, dict] = {}
live_candle_data: Dict[str, Dict[str, List[dict]]] = defaultdict(lambda: defaultdict(list))
last_tick_update: Optional[datetime] = None
last_candle_update: Optional[datetime] = None


@app.post("/api/market-data/update")
async def update_market_data(data: TickData):
    """Receive live tick data from MT5 bridge."""
    global live_market_data, last_tick_update, last_ingest
    
    count = 0
    for symbol, tick in data.symbols.items():
        # Normalize symbol (strip suffix)
        clean_symbol = internal_symbol(symbol)
        
        live_market_data[clean_symbol] = {
            "symbol": clean_symbol,
            "bid": tick.get("bid", 0),
            "ask": tick.get("ask", 0),
            "price": (tick.get("bid", 0) + tick.get("ask", 0)) / 2,
            "spread": tick.get("spread", 0),
            "volume": tick.get("volume", 0),
            "time": tick.get("time"),
            "updated": datetime.utcnow().isoformat(),
        }
        
        # Update spread history
        spread = tick.get("spread", 0)
        spread_history[clean_symbol].append(spread)
        if len(spread_history[clean_symbol]) > 100:
            spread_history[clean_symbol] = spread_history[clean_symbol][-100:]
        
        count += 1
    
    last_tick_update = datetime.utcnow()
    last_ingest = last_tick_update
    
    # Recalculate quality scores
    await recalculate_quality()
    
    logger.info(f"[Curator] Received {count} ticks from MT5 bridge")
    return {"status": "ok", "symbols_updated": count, "timestamp": last_tick_update.isoformat()}


@app.post("/api/candles/update")
async def update_candles(data: CandleData):
    """Receive live candle data from MT5 bridge."""
    global live_candle_data, last_candle_update, last_ingest
    
    total_candles = 0
    symbols_updated = []
    
    for symbol, timeframes in data.candles.items():
        clean_symbol = internal_symbol(symbol)
        symbols_updated.append(clean_symbol)
        
        for tf, candles in timeframes.items():
            # Store candles (keep last 200 per timeframe)
            existing = live_candle_data[clean_symbol][tf]
            
            for candle in candles:
                # Add to cache, avoiding duplicates by time
                candle_time = candle.get("time")
                if not any(c.get("time") == candle_time for c in existing):
                    existing.append(candle)
                    total_candles += 1
            
            # Sort by time and keep latest 200
            existing.sort(key=lambda c: c.get("time", 0))
            live_candle_data[clean_symbol][tf] = existing[-200:]
            
            # Also update data_cache for compatibility with existing code
            if clean_symbol not in data_cache:
                data_cache[clean_symbol] = {}
            data_cache[clean_symbol][tf] = {
                "candles": live_candle_data[clean_symbol][tf],
                "updated": datetime.utcnow().isoformat(),
            }
    
    last_candle_update = datetime.utcnow()
    last_ingest = last_candle_update
    
    logger.info(f"[Curator] Received {total_candles} candles for {len(symbols_updated)} symbols from MT5 bridge")
    return {
        "status": "ok", 
        "candles_received": total_candles, 
        "symbols": symbols_updated,
        "timestamp": last_candle_update.isoformat()
    }


async def recalculate_quality():
    """Recalculate quality scores after receiving new data."""
    global quality_scores
    
    for symbol in live_market_data:
        data = live_market_data.get(symbol, {})
        spread = data.get("spread", 0)
        has_candles = symbol in live_candle_data and len(live_candle_data[symbol]) > 0
        
        # Quality based on spread, freshness, and data availability
        spread_score = max(0, 1 - (spread / 5))  # 5 pip spread = 0 score
        freshness_score = 1.0 if last_tick_update and (datetime.utcnow() - last_tick_update).seconds < 60 else 0.5
        candle_score = 0.8 if has_candles else 0.3
        
        overall = (spread_score * 0.4 + freshness_score * 0.3 + candle_score * 0.3)
        
        quality_scores[symbol] = {
            "overall": round(overall, 3),
            "spread_score": round(spread_score, 3),
            "freshness_score": round(freshness_score, 3),
            "candle_score": round(candle_score, 3),
            "tradeable": overall >= QUALITY_THRESHOLD,
            "updated": datetime.utcnow().isoformat(),
        }


@app.get("/api/live/status")
async def get_live_status():
    """Get live data feed status."""
    return {
        "live_feed_active": last_tick_update is not None and (datetime.utcnow() - last_tick_update).seconds < 120,
        "last_tick_update": last_tick_update.isoformat() if last_tick_update else None,
        "last_candle_update": last_candle_update.isoformat() if last_candle_update else None,
        "symbols_with_ticks": list(live_market_data.keys()),
        "symbols_with_candles": list(live_candle_data.keys()),
        "tick_count": len(live_market_data),
        "session": get_current_session(),
    }


# === API Endpoints (Outputs) ===

@app.get("/api/status")
async def get_status():
    tradeable = len([q for q in quality_scores.values() if q.get("tradeable")])
    avg_quality = sum(q.get("overall", 0) for q in quality_scores.values()) / len(quality_scores) if quality_scores else 0
    return {
        "agent_id": "data",
        "name": AGENT_NAME,
        "status": "halted" if circuit_breaker_active else "active",
        "tradeable_symbols": tradeable,
        "total_symbols": len(SYMBOLS),
        "avg_quality": round(avg_quality, 3),
        "circuit_breaker": circuit_breaker_active,
        "session": get_current_session(),
    }


@app.get("/api/quality")
async def get_all_quality():
    """Get quality scores for all symbols."""
    return quality_scores


@app.get("/api/quality/{symbol}")
async def get_symbol_quality(symbol: str):
    """Get quality score for a specific symbol."""
    symbol = symbol.upper()
    if symbol not in quality_scores:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")
    return quality_scores[symbol]


@app.get("/api/snapshot/symbol/{symbol}")
async def get_symbol_snapshot(symbol: str):
    """Symbol snapshot output."""
    symbol = symbol.upper()
    q = quality_scores.get(symbol, {})
    
    # Get latest market data
    spread = spread_history.get(symbol, [0])[-1] if spread_history.get(symbol) else 0
    
    return {
        "symbol": symbol,
        "spread_pips": round(spread, 2),
        "last_update": last_ingest.isoformat() if last_ingest else None,
        "quality_score": q.get("overall", 0),
        "tradeable": q.get("tradeable", False),
        "session": get_current_session(),
    }


@app.get("/api/snapshot/timeframe/{symbol}/{timeframe}")
async def get_timeframe_snapshot(symbol: str, timeframe: str):
    """Timeframe snapshot output."""
    symbol = symbol.upper()
    timeframe = timeframe.upper()
    
    tf_data = data_cache.get(symbol, {}).get(timeframe, {})
    candles = tf_data.get("candles", [])
    
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "candles": [
            {
                "time": c["timestamp"].isoformat() if c.get("timestamp") else None,
                "open": c["open"],
                "high": c["high"],
                "low": c["low"],
                "close": c["close"],
                "volume": c["volume"],
            }
            for c in candles[-100:]
        ],
        "bars_received": len(candles),
        "missing_bars": tf_data.get("missing_bars", []),
        "duplicates": tf_data.get("duplicates", 0),
        "quality_score": quality_scores.get(symbol, {}).get("overall", 0),
    }


@app.get("/api/snapshot/volatility/{symbol}")
async def get_volatility_snapshot(symbol: str):
    """Volatility snapshot output."""
    symbol = symbol.upper()
    
    atr_by_tf = {}
    for tf in TIMEFRAMES:
        tf_data = data_cache.get(symbol, {}).get(tf, {})
        candles = tf_data.get("candles", [])
        if len(candles) >= 14:
            atr_values = []
            for i in range(1, min(15, len(candles))):
                tr = max(
                    candles[i]["high"] - candles[i]["low"],
                    abs(candles[i]["high"] - candles[i-1]["close"]),
                    abs(candles[i]["low"] - candles[i-1]["close"])
                )
                atr_values.append(tr)
            atr = sum(atr_values) / len(atr_values) if atr_values else 0
            multiplier = 100 if "JPY" in symbol else 10000
            atr_by_tf[tf] = round(atr * multiplier, 2)
    
    # Determine volatility state
    h1_atr = atr_by_tf.get("H1", 0)
    if h1_atr > 20:
        state = "high"
    elif h1_atr < 8:
        state = "low"
    else:
        state = "normal"
    
    return {
        "symbol": symbol,
        "atr_pips": atr_by_tf,
        "volatility_state": state,
    }


@app.get("/api/snapshot/spread/{symbol}")
async def get_spread_snapshot(symbol: str):
    """Spread/liquidity snapshot output."""
    symbol = symbol.upper()
    
    history = spread_history.get(symbol, [])
    current = history[-1] if history else 0
    avg = sum(history) / len(history) if history else 0
    max_spread = max(history) if history else 0
    
    # Liquidity score based on spread
    if avg > 0:
        ratio = current / avg
        if ratio <= 1.2:
            liquidity_score = 1.0
        elif ratio <= 1.5:
            liquidity_score = 0.8
        elif ratio <= 2.0:
            liquidity_score = 0.6
        else:
            liquidity_score = 0.3
    else:
        liquidity_score = 0.5
    
    return {
        "symbol": symbol,
        "current_spread": round(current, 2),
        "avg_spread": round(avg, 2),
        "max_spread": round(max_spread, 2),
        "liquidity_score": round(liquidity_score, 2),
        "session": get_current_session(),
    }


@app.get("/api/tradeable")
async def get_tradeable_symbols():
    """Get list of symbols that pass quality threshold."""
    return {
        "tradeable": [s for s, q in quality_scores.items() if q.get("tradeable")],
        "not_tradeable": [s for s, q in quality_scores.items() if not q.get("tradeable")],
        "circuit_breaker": circuit_breaker_active,
    }


@app.get("/api/market")
async def get_market_data():
    """Get current market prices for all symbols. Prefers live data over file data."""
    market = {}
    
    # First, use live data if available
    if live_market_data:
        for symbol, data in live_market_data.items():
            if symbol in SYMBOLS:
                market[symbol] = data
    
    # Fall back to file data for symbols not in live feed
    try:
        if MARKET_FILE.exists():
            with open(MARKET_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                for line in lines[1:]:
                    parts = line.strip().split('\t')
                    if len(parts) >= 4:
                        raw_symbol = parts[0].strip()
                        symbol = internal_symbol(raw_symbol)
                        if symbol in SYMBOLS and symbol not in market:  # Don't override live data
                            bid = float(parts[1])
                            ask = float(parts[2])
                            # Spread is in column 3 (index 3), column 4 is Point
                            spread_pips = float(parts[3]) if len(parts) > 3 else 0
                            market[symbol] = {
                                "symbol": symbol,
                                "bid": bid,
                                "ask": ask,
                                "price": (bid + ask) / 2,
                                "spread": spread_pips,
                            }
    except Exception as e:
        print(f"[Curator] Error reading market data: {e}")
    return market


@app.get("/api/market/{symbol}")
async def get_symbol_market_data(symbol: str):
    """Get current market price for a specific symbol."""
    market = await get_market_data()
    if symbol in market:
        return market[symbol]
    return {"error": f"Symbol {symbol} not found"}


@app.get("/api/account")
async def get_account():
    """Get account data from MT5."""
    try:
        if ACCOUNT_FILE.exists():
            with open(ACCOUNT_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        return {"error": str(e)}
    return {"error": "Account file not found"}


@app.get("/api/positions")
async def get_positions():
    """Get open positions from MT5."""
    try:
        if POSITIONS_FILE.exists():
            with open(POSITIONS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        return {"error": str(e)}
    return {"error": "Positions file not found", "count": 0, "positions": []}


@app.get("/api/bridge")
async def get_bridge_status():
    """Get AgentBridge EA status."""
    try:
        if BRIDGE_STATUS_FILE.exists():
            with open(BRIDGE_STATUS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        return {"error": str(e)}
    return {"status": "UNKNOWN", "message": "Bridge status file not found"}


# ═══════════════════════════════════════════════════════════════
# TIMESCALEDB ENDPOINTS (Historical Data)
# ═══════════════════════════════════════════════════════════════

@app.get("/api/timescale/stats")
async def get_timescale_stats():
    """Get TimescaleDB storage statistics."""
    if not TIMESCALE_AVAILABLE:
        return {"enabled": False, "message": "TimescaleDB module not available"}
    
    store = get_store()
    return store.get_data_stats()


@app.get("/api/timescale/symbols")
async def get_timescale_symbols():
    """Get list of symbols with historical data in TimescaleDB."""
    if not TIMESCALE_AVAILABLE:
        return {"enabled": False, "symbols": []}
    
    store = get_store()
    return {"enabled": store.enabled, "symbols": store.get_symbols_with_data()}


@app.get("/api/history/{symbol}/{timeframe}")
async def get_historical_candles(symbol: str, timeframe: str, limit: int = 500, days: int = 30):
    """
    Get historical candle data from TimescaleDB.
    
    Args:
        symbol: Trading symbol (e.g., EURUSD)
        timeframe: Candle timeframe (M1, M5, M15, M30, H1, H4, D1)
        limit: Maximum number of candles to return (default 500)
        days: Number of days of history to fetch (default 30)
    """
    if not TIMESCALE_AVAILABLE:
        return {"enabled": False, "candles": [], "message": "TimescaleDB not available"}
    
    store = get_store()
    if not store.enabled:
        return {"enabled": False, "candles": [], "message": "TimescaleDB not connected"}
    
    start = datetime.utcnow() - timedelta(days=days)
    candles = store.get_candles(symbol, timeframe, start=start, limit=limit)
    
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "count": len(candles),
        "candles": candles
    }


@app.get("/api/history/latest/{symbol}/{timeframe}")
async def get_latest_historical_candle(symbol: str, timeframe: str):
    """Get the most recent candle from TimescaleDB."""
    if not TIMESCALE_AVAILABLE:
        return {"enabled": False, "candle": None}
    
    store = get_store()
    candle = store.get_latest_candle(symbol, timeframe)
    return {"symbol": symbol, "timeframe": timeframe, "candle": candle}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
