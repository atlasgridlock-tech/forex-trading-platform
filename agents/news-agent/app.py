"""
News and Event Risk Agent - Sentinel
Event risk monitoring, calendar tracking, trading window management
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
import feedparser

# Add shared module to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared import (
    call_claude,
    get_agent_url,
    post_json,
    FOREX_SYMBOLS,
    ChatRequest,
)

app = FastAPI(title="Sentinel - News & Event Risk Agent", version="2.0")

AGENT_NAME = "Sentinel"
ORCHESTRATOR_URL = get_agent_url("orchestrator")

SYMBOLS = FOREX_SYMBOLS

# News and event cache
headlines: List[dict] = []
economic_calendar: List[dict] = []
symbol_risk_scores: Dict[str, dict] = {}
current_mode: str = "normal"


class TradingMode(str, Enum):
    NORMAL = "normal"
    REDUCED = "reduced"
    PAUSE = "pause"


class EventImpact(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# Path to MT5 calendar data file
MT5_DATA_PATH = Path(os.getenv("MT5_DATA_PATH", "/app/mt5_data"))
CALENDAR_FILE = MT5_DATA_PATH / "calendar_data.json"

# ═══════════════════════════════════════════════════════════════
# ECONOMIC CALENDAR (Real data from multiple sources)
# ═══════════════════════════════════════════════════════════════

# Import the economic calendar module
try:
    from shared.economic_calendar import (
        get_economic_calendar, 
        get_upcoming_events, 
        get_high_impact_events,
        format_event_for_display
    )
    HAS_CALENDAR_MODULE = True
except ImportError:
    HAS_CALENDAR_MODULE = False
    print("[Sentinel] Warning: economic_calendar module not found, using fallback")


def load_calendar_from_mt5() -> List[dict]:
    """Load real economic calendar from MT5 export file."""
    events = []
    try:
        if CALENDAR_FILE.exists():
            with open(CALENDAR_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                data = json.load(f)
            
            raw_events = data.get("events", [])
            print(f"[Sentinel] Loaded {len(raw_events)} events from MT5 calendar")
            
            for ev in raw_events:
                # Parse time from MT5 format: "2026.03.14 08:30:00"
                time_str = ev.get("time", "")
                try:
                    if "." in time_str:
                        event_time = datetime.strptime(time_str, "%Y.%m.%d %H:%M:%S")
                    else:
                        event_time = datetime.fromisoformat(time_str.replace("Z", ""))
                except:
                    continue
                
                currency = ev.get("currency", "USD")
                
                # Determine affected pairs based on currency
                affected = []
                for sym in SYMBOLS:
                    if currency in sym:
                        affected.append(sym)
                
                events.append({
                    "time": event_time,
                    "event": ev.get("event", "Unknown Event"),
                    "currency": currency,
                    "impact": ev.get("impact", "low"),
                    "forecast": ev.get("forecast"),
                    "previous": ev.get("previous"),
                    "actual": ev.get("actual"),
                    "affected_pairs": affected if affected else [sym for sym in SYMBOLS if currency in sym],
                })
            
            if events:
                return events
                
    except Exception as e:
        print(f"[Sentinel] Error loading MT5 calendar: {e}")
    
    return []


async def load_live_calendar() -> List[dict]:
    """Load economic calendar from live sources."""
    if not HAS_CALENDAR_MODULE:
        return []
    
    try:
        raw_events = await get_economic_calendar()
        events = []
        
        for ev in raw_events:
            # Parse datetime
            try:
                date_str = ev.get('date', '')
                time_str = ev.get('time', '12:00')
                if time_str in ['All Day', 'Tentative', '']:
                    time_str = '12:00'
                
                if 'T' in date_str:
                    event_time = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                else:
                    event_time = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            except:
                continue
            
            currency = ev.get('currency', '')
            
            # Determine affected pairs
            affected = []
            for sym in SYMBOLS:
                if currency in sym:
                    affected.append(sym)
            
            events.append({
                "time": event_time,
                "event": ev.get('title', 'Unknown'),
                "currency": currency,
                "impact": ev.get('impact', 'LOW').lower(),
                "forecast": ev.get('forecast'),
                "previous": ev.get('previous'),
                "affected_pairs": affected if affected else [sym for sym in SYMBOLS if currency in sym],
                "source": ev.get('source', 'live')
            })
        
        print(f"[Sentinel] Loaded {len(events)} events from live calendar")
        return events
        
    except Exception as e:
        print(f"[Sentinel] Error loading live calendar: {e}")
        return []


def generate_calendar_events() -> List[dict]:
    """Get calendar events - uses live data from multiple sources."""
    # Try MT5 file first
    real_events = load_calendar_from_mt5()
    if real_events:
        return real_events
    
    # Try live calendar API (run in new event loop if needed)
    try:
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            # We're in an async context - will fetch on demand via endpoint
            pass
        except RuntimeError:
            # No running loop - we can run synchronously
            live_events = asyncio.run(load_live_calendar())
            if live_events:
                return live_events
    except Exception as e:
        print(f"[Sentinel] Could not load live calendar: {e}")
    
    print("[Sentinel] Using fallback calendar events")
    now = datetime.utcnow()
    
    # Simulated events (in production: fetch from ForexFactory, Investing.com, etc.)
    events = [
        # Today's events
        {
            "time": now + timedelta(hours=2),
            "event": "US Core CPI",
            "currency": "USD",
            "impact": EventImpact.HIGH.value,
            "forecast": "3.7%",
            "previous": "3.8%",
            "affected_pairs": ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD"],
        },
        {
            "time": now + timedelta(hours=4),
            "event": "Fed Chair Powell Speech",
            "currency": "USD",
            "impact": EventImpact.HIGH.value,
            "forecast": None,
            "previous": None,
            "affected_pairs": ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD"],
        },
        {
            "time": now + timedelta(hours=6),
            "event": "FOMC Meeting Minutes",
            "currency": "USD",
            "impact": EventImpact.MEDIUM.value,
            "forecast": None,
            "previous": None,
            "affected_pairs": ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD"],
        },
        {
            "time": now + timedelta(hours=12),
            "event": "UK GDP",
            "currency": "GBP",
            "impact": EventImpact.HIGH.value,
            "forecast": "0.2%",
            "previous": "0.1%",
            "affected_pairs": ["GBPUSD", "GBPJPY", "EURGBP"],
        },
        {
            "time": now + timedelta(hours=18),
            "event": "ECB Interest Rate Decision",
            "currency": "EUR",
            "impact": EventImpact.HIGH.value,
            "forecast": "4.50%",
            "previous": "4.50%",
            "affected_pairs": ["EURUSD", "EURAUD", "EURGBP"],
        },
        # Tomorrow's events
        {
            "time": now + timedelta(hours=26),
            "event": "US NFP",
            "currency": "USD",
            "impact": EventImpact.HIGH.value,
            "forecast": "185K",
            "previous": "216K",
            "affected_pairs": ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD"],
        },
        {
            "time": now + timedelta(hours=30),
            "event": "CAD Employment Change",
            "currency": "CAD",
            "impact": EventImpact.MEDIUM.value,
            "forecast": "25K",
            "previous": "37K",
            "affected_pairs": ["USDCAD"],
        },
        {
            "time": now + timedelta(hours=40),
            "event": "AUD RBA Rate Decision",
            "currency": "AUD",
            "impact": EventImpact.HIGH.value,
            "forecast": "4.35%",
            "previous": "4.35%",
            "affected_pairs": ["AUDUSD", "AUDNZD", "EURAUD"],
        },
    ]
    
    return sorted(events, key=lambda x: x["time"])


# ═══════════════════════════════════════════════════════════════
# RISK WINDOW CALCULATIONS
# ═══════════════════════════════════════════════════════════════

def get_event_windows(event: dict) -> dict:
    """Calculate pre-event, event, and post-event windows."""
    event_time = event["time"]
    impact = event["impact"]
    
    if impact == EventImpact.HIGH.value:
        pre_start = event_time - timedelta(hours=2)
        pre_end = event_time - timedelta(minutes=30)
        block_start = event_time - timedelta(minutes=30)
        block_end = event_time + timedelta(minutes=15)
        post_start = event_time + timedelta(minutes=15)
        post_end = event_time + timedelta(hours=2)
    elif impact == EventImpact.MEDIUM.value:
        pre_start = event_time - timedelta(hours=1)
        pre_end = event_time - timedelta(minutes=15)
        block_start = event_time - timedelta(minutes=15)
        block_end = event_time + timedelta(minutes=10)
        post_start = event_time + timedelta(minutes=10)
        post_end = event_time + timedelta(hours=1)
    else:
        pre_start = event_time - timedelta(minutes=30)
        pre_end = event_time - timedelta(minutes=5)
        block_start = event_time - timedelta(minutes=5)
        block_end = event_time + timedelta(minutes=5)
        post_start = event_time + timedelta(minutes=5)
        post_end = event_time + timedelta(minutes=30)
    
    return {
        "pre_event": {"start": pre_start, "end": pre_end, "mode": TradingMode.REDUCED.value},
        "blocked": {"start": block_start, "end": block_end, "mode": TradingMode.PAUSE.value},
        "post_event": {"start": post_start, "end": post_end, "mode": TradingMode.REDUCED.value},
    }


def calculate_symbol_risk(symbol: str, events: List[dict], now: datetime) -> dict:
    """Calculate risk score for a symbol based on upcoming events."""
    risk_score = 0
    active_events = []
    blocked = False
    reduced = False
    next_clear_time = now
    
    for event in events:
        if symbol not in event.get("affected_pairs", []):
            continue
        
        windows = get_event_windows(event)
        
        # Check if we're in any window
        if windows["blocked"]["start"] <= now <= windows["blocked"]["end"]:
            blocked = True
            risk_score = max(risk_score, 100)
            active_events.append({"event": event["event"], "status": "BLOCKED"})
            next_clear_time = max(next_clear_time, windows["post_event"]["end"])
        
        elif windows["pre_event"]["start"] <= now <= windows["pre_event"]["end"]:
            reduced = True
            risk_score = max(risk_score, 70)
            active_events.append({"event": event["event"], "status": "PRE_EVENT"})
            next_clear_time = max(next_clear_time, windows["post_event"]["end"])
        
        elif windows["post_event"]["start"] <= now <= windows["post_event"]["end"]:
            reduced = True
            risk_score = max(risk_score, 60)
            active_events.append({"event": event["event"], "status": "POST_EVENT"})
            next_clear_time = max(next_clear_time, windows["post_event"]["end"])
        
        # Upcoming events (next 4 hours)
        elif now <= event["time"] <= now + timedelta(hours=4):
            time_to_event = (event["time"] - now).total_seconds() / 3600
            if event["impact"] == EventImpact.HIGH.value:
                risk_score = max(risk_score, int(50 - time_to_event * 10))
            active_events.append({"event": event["event"], "status": f"IN_{time_to_event:.1f}H"})
    
    # Determine mode
    if blocked:
        mode = TradingMode.PAUSE.value
    elif reduced:
        mode = TradingMode.REDUCED.value
    else:
        mode = TradingMode.NORMAL.value
    
    return {
        "symbol": symbol,
        "risk_score": min(risk_score, 100),
        "mode": mode,
        "blocked": blocked,
        "reduced": reduced,
        "active_events": active_events,
        "next_clear_time": next_clear_time.isoformat() if next_clear_time > now else None,
        "tradeable": not blocked,
    }


def get_blocked_windows(events: List[dict], now: datetime) -> List[dict]:
    """Get all blocked trading windows in next 24 hours."""
    blocked = []
    cutoff = now + timedelta(hours=24)
    
    for event in events:
        if event["time"] > cutoff:
            continue
        
        windows = get_event_windows(event)
        blocked.append({
            "event": event["event"],
            "currency": event["currency"],
            "start": windows["blocked"]["start"].strftime("%H:%M UTC"),
            "end": windows["blocked"]["end"].strftime("%H:%M UTC"),
            "affected_pairs": event["affected_pairs"],
        })
    
    return blocked


def get_reduced_windows(events: List[dict], now: datetime) -> List[dict]:
    """Get all reduced-risk windows in next 24 hours."""
    reduced = []
    cutoff = now + timedelta(hours=24)
    
    for event in events:
        if event["time"] > cutoff:
            continue
        
        windows = get_event_windows(event)
        reduced.append({
            "event": event["event"],
            "pre_start": windows["pre_event"]["start"].strftime("%H:%M UTC"),
            "pre_end": windows["pre_event"]["end"].strftime("%H:%M UTC"),
            "post_start": windows["post_event"]["start"].strftime("%H:%M UTC"),
            "post_end": windows["post_event"]["end"].strftime("%H:%M UTC"),
        })
    
    return reduced


async def fetch_headlines():
    """Fetch news headlines from RSS feeds."""
    global headlines
    
    feeds = [
        ("ForexLive", "https://www.forexlive.com/feed/"),
        ("FXStreet", "https://www.fxstreet.com/rss/news"),
    ]
    
    new_headlines = []
    
    # Import pooled client
    from shared import get_pooled_client
    client = await get_pooled_client()
    
    for source_name, feed_url in feeds:
        try:
            r = await client.get(feed_url, timeout=10.0, follow_redirects=True)
            if r.status_code == 200:
                feed = feedparser.parse(r.text)
                for entry in feed.entries[:30]:  # Get more entries per feed
                    # Parse time
                    pub_time = entry.get("published", "")
                    if pub_time:
                        try:
                            from email.utils import parsedate_to_datetime
                            dt = parsedate_to_datetime(pub_time)
                            time_str = dt.strftime("%H:%M")
                        except:
                            time_str = pub_time[:5]
                    else:
                        time_str = ""
                    
                    new_headlines.append({
                        "title": entry.get("title", "").replace('<![CDATA[', '').replace(']]>', ''),
                        "source": source_name,
                        "time": time_str,
                        "link": entry.get("link", ""),
                    })
        except Exception as e:
            print(f"[Sentinel] Error fetching {source_name}: {e}")
    
    # Sort by time (most recent first) and limit
    headlines = new_headlines[:50]
    print(f"[Sentinel] 📰 Loaded {len(headlines)} headlines from {len(feeds)} sources")


def determine_overall_mode() -> tuple:
    """Determine overall trading mode based on all symbol risks."""
    global current_mode
    
    pause_count = sum(1 for s in symbol_risk_scores.values() if s.get("mode") == TradingMode.PAUSE.value)
    reduced_count = sum(1 for s in symbol_risk_scores.values() if s.get("mode") == TradingMode.REDUCED.value)
    
    if pause_count >= 3:
        mode = TradingMode.PAUSE.value
        reason = f"{pause_count} symbols in pause mode"
    elif pause_count > 0 or reduced_count >= 5:
        mode = TradingMode.REDUCED.value
        reason = f"{pause_count} paused, {reduced_count} reduced"
    else:
        mode = TradingMode.NORMAL.value
        reason = "All clear"
    
    current_mode = mode
    return mode, reason


async def send_to_orchestrator():
    """Send risk assessment to Orchestrator using shared post_json."""
    mode, reason = determine_overall_mode()
    
    await post_json(
        f"{ORCHESTRATOR_URL}/api/ingest",
        {
            "agent_id": "news",
            "agent_name": AGENT_NAME,
            "output_type": "alert",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "level": "warning" if mode != TradingMode.NORMAL.value else "info",
                "message": f"Trading mode: {mode.upper()} - {reason}",
                "mode": mode,
                "symbol_risks": {s: r.get("risk_score", 0) for s, r in symbol_risk_scores.items()},
            },
        }
    )


async def background_monitoring():
    """Background event monitoring loop."""
    global economic_calendar, symbol_risk_scores
    
    while True:
        # Update calendar
        economic_calendar = generate_calendar_events()
        
        # Calculate symbol risks
        now = datetime.utcnow()
        for symbol in SYMBOLS:
            symbol_risk_scores[symbol] = calculate_symbol_risk(symbol, economic_calendar, now)
        
        # Fetch headlines
        await fetch_headlines()
        
        # Send to orchestrator
        await send_to_orchestrator()
        
        await asyncio.sleep(60)  # Update every minute


# Using shared call_claude - removed duplicate implementation


@app.on_event("startup")
async def startup():
    global economic_calendar, symbol_risk_scores
    print(f"🚀 {AGENT_NAME} (News & Event Risk Agent) v2.0 starting...")
    
    economic_calendar = generate_calendar_events()
    now = datetime.utcnow()
    for symbol in SYMBOLS:
        symbol_risk_scores[symbol] = calculate_symbol_risk(symbol, economic_calendar, now)
    
    asyncio.create_task(background_monitoring())


@app.get("/", response_class=HTMLResponse)
async def home():
    now = datetime.utcnow()
    mode, reason = determine_overall_mode()
    
    # Mode styling
    if mode == TradingMode.PAUSE.value:
        mode_color = "#ef4444"
        mode_icon = "⛔"
    elif mode == TradingMode.REDUCED.value:
        mode_color = "#f59e0b"
        mode_icon = "⚠️"
    else:
        mode_color = "#22c55e"
        mode_icon = "✅"
    
    # Upcoming events
    events_html = ""
    for event in economic_calendar[:8]:
        time_diff = event["time"] - now
        hours_away = time_diff.total_seconds() / 3600
        
        impact_color = "#ef4444" if event["impact"] == "high" else "#f59e0b" if event["impact"] == "medium" else "#888"
        
        events_html += f'''
        <div class="event">
            <div class="event-time">{event["time"].strftime("%H:%M UTC")}</div>
            <div class="event-name">{event["event"]}</div>
            <div class="event-meta">
                <span class="impact" style="background:{impact_color}20;color:{impact_color}">{event["impact"].upper()}</span>
                <span class="currency">{event["currency"]}</span>
                <span class="countdown">{hours_away:.1f}h</span>
            </div>
        </div>
        '''
    
    # Symbol risks
    symbols_html = ""
    for symbol in SYMBOLS:
        risk = symbol_risk_scores.get(symbol, {})
        score = risk.get("risk_score", 0)
        mode_s = risk.get("mode", "normal")
        
        if mode_s == TradingMode.PAUSE.value:
            symbol_color = "#ef4444"
            symbol_icon = "⛔"
        elif mode_s == TradingMode.REDUCED.value:
            symbol_color = "#f59e0b"
            symbol_icon = "⚠️"
        else:
            symbol_color = "#22c55e"
            symbol_icon = "✅"
        
        symbols_html += f'''
        <div class="symbol-risk">
            <span class="symbol-name">{symbol}</span>
            <div class="risk-bar"><div class="risk-fill" style="width:{score}%;background:{symbol_color}"></div></div>
            <span class="risk-score">{score}</span>
            <span class="risk-icon">{symbol_icon}</span>
        </div>
        '''
    
    # Blocked windows
    blocked = get_blocked_windows(economic_calendar, now)
    blocked_html = ""
    for b in blocked[:5]:
        blocked_html += f'<div class="blocked-window">⛔ {b["start"]}-{b["end"]}: {b["event"]}</div>'
    
    # Headlines - show all with timestamps
    headlines_html = ""
    for h in headlines:
        time_str = h.get("time", "")[:5] if h.get("time") else ""
        source = h.get("source", "")[:10]
        headlines_html += f'<div class="headline"><span class="hl-time">{time_str}</span> <span class="hl-source">[{source}]</span> {h["title"][:100]}</div>'
    
    return f'''<!DOCTYPE html>
<html><head>
    <title>📰 Sentinel - Event Risk Agent</title>
    <meta http-equiv="refresh" content="30">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, sans-serif; background: #0a0a0f; color: #e0e0e0; padding: 20px; }}
        .header {{ display: flex; align-items: center; gap: 15px; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid #333; }}
        .header h1 {{ color: #3b82f6; }}
        .mode-badge {{ background: {mode_color}20; color: {mode_color}; padding: 8px 16px; border-radius: 20px; font-size: 14px; font-weight: bold; }}
        .grid {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px; margin-bottom: 20px; }}
        .card {{ background: #1a1a24; border-radius: 12px; padding: 20px; }}
        .card h2 {{ color: #3b82f6; font-size: 14px; margin-bottom: 15px; }}
        .event {{ padding: 10px; border-left: 3px solid #333; margin: 8px 0; background: #0a0a0f; border-radius: 0 6px 6px 0; }}
        .event-time {{ font-family: monospace; color: #888; font-size: 12px; }}
        .event-name {{ font-weight: 600; margin: 4px 0; }}
        .event-meta {{ display: flex; gap: 10px; font-size: 11px; }}
        .impact {{ padding: 2px 6px; border-radius: 4px; }}
        .currency {{ color: #888; }}
        .countdown {{ color: #3b82f6; }}
        .symbol-risk {{ display: flex; align-items: center; gap: 10px; padding: 8px 0; border-bottom: 1px solid #222; }}
        .symbol-name {{ width: 70px; font-weight: 600; }}
        .risk-bar {{ flex: 1; height: 8px; background: #333; border-radius: 4px; overflow: hidden; }}
        .risk-fill {{ height: 100%; border-radius: 4px; }}
        .risk-score {{ width: 30px; text-align: right; font-size: 12px; }}
        .risk-icon {{ width: 20px; }}
        .blocked-window {{ padding: 6px 10px; background: #7f1d1d20; border-radius: 4px; margin: 5px 0; font-size: 12px; color: #fca5a5; }}
        .headline {{ padding: 8px 12px; border-bottom: 1px solid #222; font-size: 12px; color: #ccc; transition: background 0.2s; }}
        .headline:hover {{ background: #252530; }}
        .hl-time {{ color: #3b82f6; font-family: monospace; font-size: 11px; }}
        .hl-source {{ color: #666; font-size: 10px; }}
        .headlines-container {{ height: 400px; overflow-y: auto; background: #0a0a0f; border-radius: 8px; scroll-behavior: smooth; }}
        .headlines-container::-webkit-scrollbar {{ width: 6px; }}
        .headlines-container::-webkit-scrollbar-track {{ background: #1a1a24; }}
        .headlines-container::-webkit-scrollbar-thumb {{ background: #3b82f6; border-radius: 3px; }}
        .chat-section {{ background: #1a1a24; border-radius: 12px; padding: 20px; }}
        .chat-section h2 {{ color: #3b82f6; margin-bottom: 15px; }}
        .chat-messages {{ height: 150px; overflow-y: auto; background: #0a0a0f; border-radius: 8px; padding: 10px; margin-bottom: 10px; }}
        .chat-input {{ display: flex; gap: 10px; }}
        .chat-input input {{ flex: 1; padding: 10px; border-radius: 8px; border: 1px solid #333; background: #0a0a0f; color: #fff; }}
        .chat-input button {{ padding: 10px 20px; background: #3b82f6; color: #fff; border: none; border-radius: 8px; cursor: pointer; }}
        .message {{ margin: 8px 0; padding: 8px; border-radius: 6px; font-size: 13px; }}
        .message.user {{ background: #333; margin-left: 20%; }}
        .message.agent {{ background: #1a2d4d; margin-right: 20%; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📰 Sentinel</h1>
        <span class="mode-badge">{mode_icon} {mode.upper()}</span>
        <span style="color: #888; margin-left: auto;">Event Risk Agent v2.0 • {reason}</span>
    </div>
    
    <div class="grid">
        <div class="card">
            <h2>📅 Upcoming Events (24h)</h2>
            {events_html}
        </div>
        
        <div class="card">
            <h2>📊 Symbol Risk Scores</h2>
            {symbols_html}
        </div>
        
        <div class="card">
            <h2>⛔ Blocked Windows</h2>
            {blocked_html if blocked_html else '<div style="color:#666">No blocked windows active</div>'}
        </div>
    </div>
    
    <div class="card" style="margin-bottom: 20px;">
        <h2>📰 Live News Feed ({len(headlines)} headlines)</h2>
        <div class="headlines-container" id="headlines-scroll">
            {headlines_html if headlines_html else '<div style="color:#666; padding: 20px;">No headlines available</div>'}
        </div>
    </div>
    
    <div class="chat-section">
        <h2>💬 Ask Sentinel</h2>
        <div class="chat-messages" id="messages"></div>
        <div class="chat-input">
            <input type="text" id="input" placeholder="Ask about events..." onkeypress="if(event.key==='Enter')sendMessage()">
            <button onclick="sendMessage()">Send</button>
        </div>
    </div>
    <script>
        const CHAT_KEY = 'sentinel_chat_history';
        
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
        
        // Auto-scroll headlines
        let scrollPaused = false;
        const headlinesContainer = document.getElementById('headlines-scroll');
        
        if (headlinesContainer) {{
            // Pause scroll on hover
            headlinesContainer.addEventListener('mouseenter', () => scrollPaused = true);
            headlinesContainer.addEventListener('mouseleave', () => scrollPaused = false);
            
            // Auto-scroll animation
            let scrollPos = 0;
            setInterval(() => {{
                if (!scrollPaused && headlinesContainer.scrollHeight > headlinesContainer.clientHeight) {{
                    scrollPos += 1;
                    if (scrollPos >= headlinesContainer.scrollHeight - headlinesContainer.clientHeight) {{
                        scrollPos = 0;  // Reset to top
                    }}
                    headlinesContainer.scrollTop = scrollPos;
                }}
            }}, 100);
        }}
    </script>
</body>
</html>'''


@app.post("/chat")
async def chat(request: ChatRequest):
    context = f"""Current Mode: {current_mode}
    
Upcoming Events:
{json.dumps([{**e, 'time': e['time'].isoformat()} for e in economic_calendar[:5]], indent=2)}

Symbol Risk Scores:
{json.dumps(symbol_risk_scores, indent=2, default=str)}

Headlines:
{json.dumps(headlines[:5], indent=2)}
"""
    response = await call_claude(request.message, context, agent_name=AGENT_NAME)
    return {"response": response}


@app.get("/api/mode")
async def get_mode():
    mode, reason = determine_overall_mode()
    return {"mode": mode, "reason": reason}


@app.get("/api/events")
async def get_events():
    return [{**e, "time": e["time"].isoformat()} for e in economic_calendar]


@app.get("/api/risk/{symbol}")
async def get_symbol_risk(symbol: str):
    return symbol_risk_scores.get(symbol.upper(), {"error": "Not found"})


@app.get("/api/risks")
async def get_all_risks():
    return symbol_risk_scores


@app.get("/api/blocked")
async def get_blocked():
    return get_blocked_windows(economic_calendar, datetime.utcnow())


@app.get("/api/headlines")
async def get_headlines():
    return headlines


@app.get("/api/status")
async def get_status():
    mode, reason = determine_overall_mode()
    return {
        "agent_id": "news",
        "name": AGENT_NAME,
        "status": "active",
        "mode": mode,
        "events_tracked": len(economic_calendar),
        "headlines": len(headlines),
        "version": "2.0",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
