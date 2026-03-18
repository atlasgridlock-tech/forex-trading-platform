"""
Trade Journal Agent - Chronicle
Trade journaling, review, lessons learned, pattern detection
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
from pydantic import BaseModel
from enum import Enum
import uuid

# Add shared module to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared import (
    call_claude,
    get_agent_url,
    post_json,
    ChatRequest,
)

# Import dashboard generator
try:
    from dashboard import generate_dashboard
except ImportError:
    generate_dashboard = None

app = FastAPI(title="Chronicle - Trade Journal Agent", version="1.0")

AGENT_NAME = "Chronicle"
ORCHESTRATOR_URL = get_agent_url("orchestrator")

# Use configurable workspace - default to local ./workspace if /app doesn't exist
if os.path.exists("/app") and os.access("/app", os.W_OK):
    WORKSPACE = Path("/app/workspace")
else:
    # Local development - use workspace relative to script
    WORKSPACE = Path(__file__).parent / "workspace"

JOURNAL_DIR = WORKSPACE / "journal"

# Ensure journal directory exists
try:
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
except OSError as e:
    print(f"[Chronicle] Warning: Could not create journal dir: {e}")
    # Fallback to temp directory
    import tempfile
    JOURNAL_DIR = Path(tempfile.gettempdir()) / "forex_platform" / "journal"
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)


class TradeStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    MODIFIED = "modified"
    CLOSED = "closed"


class TradeEntry(BaseModel):
    # Core
    symbol: str
    side: str
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    lot_size: Optional[float] = None
    risk_pct: Optional[float] = None
    
    # Context
    timeframe: Optional[str] = None
    regime: Optional[str] = None
    strategy_family: Optional[str] = None
    session: Optional[str] = None
    
    # Signals
    technical_signal: Optional[str] = None
    macro_context: Optional[str] = None
    sentiment: Optional[str] = None
    news_risk: Optional[str] = None
    structure: Optional[str] = None
    
    # Reasoning
    entry_reason: Optional[str] = None
    conflicting_signals: Optional[List[str]] = None
    confidence: Optional[float] = None


class CloseEntry(BaseModel):
    trade_id: str
    close_price: float
    close_reason: str
    notes: Optional[str] = None


class ReviewEntry(BaseModel):
    trade_id: str
    expectation_met: bool
    expectation_notes: str
    lesson_tags: List[str]
    grade: str  # A, B, C, D, F
    after_action_notes: str


# In-memory storage (would be database in production)
trades: Dict[str, dict] = {}
lessons: List[dict] = []
statistics: Dict[str, dict] = {}


def generate_trade_id() -> str:
    return f"TRD-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"


def calculate_result_r(entry: float, exit: float, stop: float, side: str) -> float:
    """Calculate result in R (risk multiples)."""
    if side.lower() in ["long", "buy"]:
        risk = entry - stop
        reward = exit - entry
    else:
        risk = stop - entry
        reward = entry - exit
    
    if risk == 0:
        return 0
    return round(reward / abs(risk), 2)


def calculate_pips(entry: float, exit: float, side: str, symbol: str) -> float:
    """Calculate result in pips."""
    multiplier = 100 if "JPY" in symbol else 10000
    if side.lower() in ["long", "buy"]:
        return round((exit - entry) * multiplier, 1)
    else:
        return round((entry - exit) * multiplier, 1)


def save_trade_to_file(trade: dict):
    """Save trade to daily journal file."""
    date = datetime.utcnow().strftime("%Y-%m-%d")
    file_path = JOURNAL_DIR / f"trades_{date}.json"
    
    # Load existing trades
    existing = []
    if file_path.exists():
        try:
            with open(file_path, 'r') as f:
                existing = json.load(f)
        except:
            existing = []
    
    # Update or append
    updated = False
    for i, t in enumerate(existing):
        if t.get("trade_id") == trade.get("trade_id"):
            existing[i] = trade
            updated = True
            break
    
    if not updated:
        existing.append(trade)
    
    # Save
    with open(file_path, 'w') as f:
        json.dump(existing, f, indent=2, default=str)


def load_recent_trades(days: int = 7) -> List[dict]:
    """Load trades from recent days."""
    all_trades = []
    for i in range(days):
        date = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
        file_path = JOURNAL_DIR / f"trades_{date}.json"
        if file_path.exists():
            try:
                with open(file_path, 'r') as f:
                    all_trades.extend(json.load(f))
            except:
                pass
    return all_trades


def calculate_statistics() -> dict:
    """Calculate aggregate statistics from trade history."""
    recent_trades = load_recent_trades(30)
    closed_trades = [t for t in recent_trades if t.get("status") == "closed"]
    
    if not closed_trades:
        return {"message": "No closed trades to analyze"}
    
    # Overall stats
    total = len(closed_trades)
    wins = len([t for t in closed_trades if t.get("result_r", 0) > 0])
    losses = len([t for t in closed_trades if t.get("result_r", 0) < 0])
    
    total_r = sum(t.get("result_r", 0) for t in closed_trades)
    avg_r = total_r / total if total > 0 else 0
    
    # By regime
    by_regime = {}
    for t in closed_trades:
        regime = t.get("regime", "unknown")
        if regime not in by_regime:
            by_regime[regime] = {"count": 0, "wins": 0, "total_r": 0}
        by_regime[regime]["count"] += 1
        by_regime[regime]["total_r"] += t.get("result_r", 0)
        if t.get("result_r", 0) > 0:
            by_regime[regime]["wins"] += 1
    
    for regime in by_regime:
        count = by_regime[regime]["count"]
        by_regime[regime]["win_rate"] = round(by_regime[regime]["wins"] / count * 100, 1) if count > 0 else 0
        by_regime[regime]["avg_r"] = round(by_regime[regime]["total_r"] / count, 2) if count > 0 else 0
    
    # By strategy
    by_strategy = {}
    for t in closed_trades:
        strat = t.get("strategy_family", "unknown")
        if strat not in by_strategy:
            by_strategy[strat] = {"count": 0, "wins": 0, "total_r": 0}
        by_strategy[strat]["count"] += 1
        by_strategy[strat]["total_r"] += t.get("result_r", 0)
        if t.get("result_r", 0) > 0:
            by_strategy[strat]["wins"] += 1
    
    for strat in by_strategy:
        count = by_strategy[strat]["count"]
        by_strategy[strat]["win_rate"] = round(by_strategy[strat]["wins"] / count * 100, 1) if count > 0 else 0
        by_strategy[strat]["avg_r"] = round(by_strategy[strat]["total_r"] / count, 2) if count > 0 else 0
    
    # Lesson frequency
    lesson_counts = {}
    for t in closed_trades:
        for tag in t.get("lesson_tags", []):
            lesson_counts[tag] = lesson_counts.get(tag, 0) + 1
    
    return {
        "period": "30 days",
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / total * 100, 1) if total > 0 else 0,
        "total_r": round(total_r, 2),
        "avg_r": round(avg_r, 2),
        "by_regime": by_regime,
        "by_strategy": by_strategy,
        "top_lessons": dict(sorted(lesson_counts.items(), key=lambda x: x[1], reverse=True)[:10]),
    }


async def generate_after_action_review(trade: dict) -> str:
    """Generate AI-powered after-action review."""
    if not ANTHROPIC_API_KEY:
        return "AI review unavailable"
    
    prompt = f"""Generate a brief after-action review for this trade:

Trade: {trade.get('symbol')} {trade.get('side').upper()}
Entry: {trade.get('entry_price')} → Exit: {trade.get('close_price')}
Result: {trade.get('result_r', 0)}R | {trade.get('result_pips', 0)} pips

Context at entry:
- Regime: {trade.get('regime')}
- Strategy: {trade.get('strategy_family')}
- Entry reason: {trade.get('entry_reason')}
- Conflicting signals: {trade.get('conflicting_signals')}

Close reason: {trade.get('close_reason')}

Provide:
1. What went well
2. What could improve
3. Key lesson (one sentence)"""

    try:
        # Use pooled HTTP client
        from shared import get_pooled_client
        client = await get_pooled_client()
        
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": "claude-sonnet-4-20250514", "max_tokens": 500,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=30.0
        )
        if r.status_code == 200:
            return r.json()["content"][0]["text"]
    except:
        pass
    return "Review generation failed"


# Using shared call_claude - removed duplicate implementation


@app.on_event("startup")
async def startup():
    print(f"🚀 {AGENT_NAME} (Trade Journal Agent) v1.0 starting...")
    print(f"   Journal directory: {JOURNAL_DIR}")


@app.get("/", response_class=HTMLResponse)
async def home():
    recent = load_recent_trades(30)
    stats = calculate_statistics()
    
    # Use new dashboard if available
    if generate_dashboard:
        return generate_dashboard(recent, stats)
    
    # Fallback to basic dashboard
    return f'''<!DOCTYPE html>
<html><head>
    <title>📔 Chronicle - Journal Agent</title>
    <meta http-equiv="refresh" content="30">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, sans-serif; background: #0a0a0f; color: #e0e0e0; padding: 20px; }}
        .header {{ display: flex; align-items: center; gap: 15px; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid #333; }}
        .header h1 {{ color: #f59e0b; }}
        .stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 20px; }}
        .stat {{ background: #1a1a24; border-radius: 10px; padding: 20px; text-align: center; }}
        .stat-value {{ font-size: 28px; font-weight: bold; }}
        .stat-value.green {{ color: #22c55e; }}
        .stat-value.red {{ color: #ef4444; }}
        .stat-label {{ font-size: 12px; color: #666; margin-top: 5px; }}
        .card {{ background: #1a1a24; border-radius: 12px; padding: 20px; margin-bottom: 20px; }}
        .card h2 {{ font-size: 14px; color: #888; margin-bottom: 15px; text-transform: uppercase; }}
        .trade-row {{ display: flex; justify-content: space-between; align-items: center; padding: 10px; background: #0a0a0f; border-radius: 8px; margin: 8px 0; font-size: 13px; }}
        .trade-id {{ color: #888; font-family: monospace; }}
        .status {{ background: #333; padding: 2px 8px; border-radius: 4px; font-size: 11px; }}
        .chat-section {{ background: #1a1a24; border-radius: 12px; padding: 20px; }}
        .chat-section h2 {{ color: #f59e0b; margin-bottom: 15px; }}
        .chat-messages {{ height: 120px; overflow-y: auto; background: #0a0a0f; border-radius: 8px; padding: 10px; margin-bottom: 10px; }}
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
        <h1>📔 Chronicle</h1>
        <span style="color: #888; margin-left: auto;">Trade Journal Agent v1.0</span>
    </div>
    
    <div class="stats">
        <div class="stat">
            <div class="stat-value">{stats.get("total_trades", 0)}</div>
            <div class="stat-label">Total Trades (30d)</div>
        </div>
        <div class="stat">
            <div class="stat-value {'green' if win_rate >= 50 else 'red'}">{win_rate:.1f}%</div>
            <div class="stat-label">Win Rate</div>
        </div>
        <div class="stat">
            <div class="stat-value {'green' if total_r >= 0 else 'red'}">{total_r:+.1f}R</div>
            <div class="stat-label">Total R</div>
        </div>
        <div class="stat">
            <div class="stat-value {'green' if avg_r >= 0 else 'red'}">{avg_r:+.2f}</div>
            <div class="stat-label">Avg R/Trade</div>
        </div>
    </div>
    
    <div class="card">
        <h2>📊 Recent Trades</h2>
        {trades_html}
    </div>
    
    <div class="chat-section">
        <h2>💬 Ask Chronicle</h2>
        <div class="chat-messages" id="messages"></div>
        <div class="chat-input">
            <input type="text" id="input" placeholder="Ask about trades, patterns, lessons..." onkeypress="if(event.key==='Enter')sendMessage()">
            <button onclick="sendMessage()">Send</button>
        </div>
    </div>
    <script>
        const CHAT_KEY = 'chronicle_chat_history';
        
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
    stats = calculate_statistics()
    recent = load_recent_trades(7)
    context = f"Statistics: {json.dumps(stats)}\nRecent trades: {len(recent)}"
    response = await call_claude(request.message, context, agent_name=AGENT_NAME)
    return {"response": response}


@app.post("/api/trade/propose")
async def propose_trade(entry: TradeEntry):
    """Log a proposed trade."""
    trade_id = generate_trade_id()
    
    trade = {
        "trade_id": trade_id,
        "status": TradeStatus.PROPOSED.value,
        "created_at": datetime.utcnow().isoformat(),
        "proposed_at": datetime.utcnow().isoformat(),
        **entry.dict(),
    }
    
    trades[trade_id] = trade
    save_trade_to_file(trade)
    
    return {"trade_id": trade_id, "status": "proposed"}


@app.post("/api/trade/approve/{trade_id}")
async def approve_trade(trade_id: str, lot_size: float, risk_pct: float):
    """Log trade approval from Guardian."""
    if trade_id not in trades:
        return {"error": "Trade not found"}
    
    trades[trade_id]["status"] = TradeStatus.APPROVED.value
    trades[trade_id]["approved_at"] = datetime.utcnow().isoformat()
    trades[trade_id]["lot_size"] = lot_size
    trades[trade_id]["risk_pct"] = risk_pct
    
    save_trade_to_file(trades[trade_id])
    return {"trade_id": trade_id, "status": "approved"}


@app.post("/api/trade/reject/{trade_id}")
async def reject_trade(trade_id: str, reason: str):
    """Log trade rejection."""
    if trade_id not in trades:
        return {"error": "Trade not found"}
    
    trades[trade_id]["status"] = TradeStatus.REJECTED.value
    trades[trade_id]["rejected_at"] = datetime.utcnow().isoformat()
    trades[trade_id]["rejection_reason"] = reason
    
    save_trade_to_file(trades[trade_id])
    return {"trade_id": trade_id, "status": "rejected"}


class ExecuteTradeRequest(BaseModel):
    fill_price: float
    slippage_pips: float = 0
    ticket: int = 0
    symbol: Optional[str] = None
    direction: Optional[str] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    lot_size: Optional[float] = None
    # Confluence scores at entry
    confluence_at_entry: Optional[dict] = None
    # Trade thesis
    thesis: Optional[dict] = None
    # Entry details
    entry_trigger: Optional[str] = None
    entry_type: Optional[str] = None


@app.post("/api/trade/execute/{trade_id}")
async def execute_trade(trade_id: str, request: ExecuteTradeRequest):
    """Log trade execution. Creates trade if not exists."""
    # Create trade if not exists (for direct execution without propose)
    if trade_id not in trades:
        trades[trade_id] = {
            "trade_id": trade_id,
            "symbol": request.symbol or trade_id.split("-")[0],
            "direction": request.direction or "unknown",
            "entry_price": request.fill_price,
            "stop_loss": request.stop_loss or 0,
            "take_profit": request.take_profit or 0,
            "lot_size": request.lot_size or 0.01,
            "status": TradeStatus.PROPOSED.value,
            "created_at": datetime.utcnow().isoformat(),
            # Include confluence and thesis if provided
            "confluence_at_entry": request.confluence_at_entry or {},
            "thesis": request.thesis or {},
            "entry_trigger": request.entry_trigger or "",
            "entry_type": request.entry_type or "market",
        }
    
    trades[trade_id]["status"] = TradeStatus.EXECUTED.value
    trades[trade_id]["executed_at"] = datetime.utcnow().isoformat()
    trades[trade_id]["fill_price"] = request.fill_price
    trades[trade_id]["entry_price"] = request.fill_price  # Update entry to actual fill
    trades[trade_id]["slippage_pips"] = request.slippage_pips
    trades[trade_id]["broker_ticket"] = request.ticket
    
    # Store confluence scores at entry (for journaling)
    if request.confluence_at_entry:
        trades[trade_id]["confluence_at_entry"] = request.confluence_at_entry
    
    # Store trade thesis (why we took this trade)
    if request.thesis:
        trades[trade_id]["thesis"] = request.thesis
        # Also flatten for easier access
        trades[trade_id]["why_here"] = request.thesis.get("why_here", "")
        trades[trade_id]["why_now"] = request.thesis.get("why_now", "")
        trades[trade_id]["why_direction"] = request.thesis.get("why_direction", "")
        trades[trade_id]["invalidation"] = request.thesis.get("invalidation", "")
    
    # Entry details
    if request.entry_trigger:
        trades[trade_id]["entry_trigger"] = request.entry_trigger
    if request.entry_type:
        trades[trade_id]["entry_type"] = request.entry_type
    
    save_trade_to_file(trades[trade_id])
    return {"trade_id": trade_id, "status": "executed"}


@app.post("/api/trade/close")
async def close_trade(close: CloseEntry):
    """Log trade closure and calculate results."""
    trade_id = close.trade_id
    if trade_id not in trades:
        # Try to load from file
        recent = load_recent_trades(30)
        for t in recent:
            if t.get("trade_id") == trade_id:
                trades[trade_id] = t
                break
    
    if trade_id not in trades:
        return {"error": "Trade not found"}
    
    trade = trades[trade_id]
    trade["status"] = TradeStatus.CLOSED.value
    trade["closed_at"] = datetime.utcnow().isoformat()
    trade["close_price"] = close.close_price
    trade["close_reason"] = close.close_reason
    
    # Calculate results
    entry = trade.get("fill_price") or trade.get("entry_price", 0)
    stop = trade.get("stop_loss", 0)
    side = trade.get("side", "long")
    symbol = trade.get("symbol", "EURUSD")
    
    trade["result_r"] = calculate_result_r(entry, close.close_price, stop, side)
    trade["result_pips"] = calculate_pips(entry, close.close_price, side, symbol)
    
    # Estimate currency result
    lot_size = trade.get("lot_size", 0.1)
    pip_value = 10 if "JPY" not in symbol else 9
    trade["result_currency"] = round(trade["result_pips"] * pip_value * lot_size, 2)
    
    if close.notes:
        trade["close_notes"] = close.notes
    
    save_trade_to_file(trade)
    
    # Generate after-action review
    review = await generate_after_action_review(trade)
    trade["ai_review"] = review
    save_trade_to_file(trade)
    
    return {
        "trade_id": trade_id,
        "status": "closed",
        "result_r": trade["result_r"],
        "result_pips": trade["result_pips"],
        "result_currency": trade["result_currency"],
    }


@app.post("/api/trade/review")
async def add_review(review: ReviewEntry):
    """Add manual review and lessons to a trade."""
    trade_id = review.trade_id
    if trade_id not in trades:
        recent = load_recent_trades(30)
        for t in recent:
            if t.get("trade_id") == trade_id:
                trades[trade_id] = t
                break
    
    if trade_id not in trades:
        return {"error": "Trade not found"}
    
    trade = trades[trade_id]
    trade["expectation_met"] = review.expectation_met
    trade["expectation_notes"] = review.expectation_notes
    trade["lesson_tags"] = review.lesson_tags
    trade["grade"] = review.grade
    trade["after_action_notes"] = review.after_action_notes
    trade["reviewed_at"] = datetime.utcnow().isoformat()
    
    save_trade_to_file(trade)
    
    # Add to lessons list
    for tag in review.lesson_tags:
        lessons.append({
            "trade_id": trade_id,
            "tag": tag,
            "timestamp": datetime.utcnow().isoformat(),
        })
    
    return {"trade_id": trade_id, "status": "reviewed"}


class LessonEntry(BaseModel):
    trade_id: str
    lesson: str


@app.post("/api/trade/lesson")
async def add_lesson(entry: LessonEntry):
    """Add a lesson learned to a trade."""
    trade_id = entry.trade_id
    
    # Find the trade
    if trade_id not in trades:
        recent = load_recent_trades(30)
        for t in recent:
            if t.get("trade_id") == trade_id:
                trades[trade_id] = t
                break
    
    if trade_id not in trades:
        return {"error": "Trade not found"}
    
    trade = trades[trade_id]
    if "lessons" not in trade:
        trade["lessons"] = []
    trade["lessons"].append(entry.lesson)
    
    save_trade_to_file(trade)
    
    return {"trade_id": trade_id, "status": "lesson_added", "lessons": trade["lessons"]}


@app.get("/api/trades")
async def get_trades(days: int = 7, status: Optional[str] = None):
    """Get trade history."""
    recent = load_recent_trades(days)
    if status:
        recent = [t for t in recent if t.get("status") == status]
    return {"trades": recent, "count": len(recent)}


@app.get("/api/trade/{trade_id}")
async def get_trade(trade_id: str):
    """Get specific trade details."""
    if trade_id in trades:
        return trades[trade_id]
    
    recent = load_recent_trades(30)
    for t in recent:
        if t.get("trade_id") == trade_id:
            return t
    
    return {"error": "Trade not found"}


@app.get("/api/statistics")
async def get_statistics():
    """Get aggregate trading statistics."""
    return calculate_statistics()


@app.get("/api/lessons")
async def get_lessons(limit: int = 50):
    """Get recent lessons and patterns."""
    stats = calculate_statistics()
    return {
        "top_lessons": stats.get("top_lessons", {}),
        "recent_lessons": lessons[-limit:],
    }


@app.get("/api/status")
async def get_status():
    recent = load_recent_trades(7)
    stats = calculate_statistics()
    return {
        "agent_id": "journal",
        "name": AGENT_NAME,
        "status": "active",
        "trades_recorded": len(recent),
        "win_rate": stats.get("win_rate", 0),
        "total_r": stats.get("total_r", 0),
        "version": "1.0",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, access_log=False)
