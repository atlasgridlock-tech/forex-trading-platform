"""
Trade Journal Agent - Chronicle v2.0
Enhanced trade journaling with chart generation, rich context capture, and AI analysis
"""

import os
import sys
import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from enum import Enum
import uuid

# Add shared module to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared import (
    call_claude,
    get_agent_url,
    post_json,
    fetch_json,
    ChatRequest,
)

# Import chart generator
from chart_generator import (
    create_trade_journal_entry,
    generate_trade_chart,
    fetch_ohlc_data,
)

app = FastAPI(title="Chronicle - Trade Journal Agent", version="2.0")

AGENT_NAME = "Chronicle"
ORCHESTRATOR_URL = get_agent_url("orchestrator")

# Configurable paths - with fallback for local development
def get_journal_paths():
    """Get journal paths with fallback for local development."""
    mt5_path = Path(os.getenv("MT5_FILES_PATH", "/mt5files"))
    
    # Check if MT5 path is writable
    try:
        mt5_path.mkdir(parents=True, exist_ok=True)
        test_file = mt5_path / ".write_test"
        test_file.touch()
        test_file.unlink()
        return mt5_path / "trade_journal", mt5_path / "journal_logs"
    except (OSError, PermissionError):
        pass
    
    # Fallback to local workspace directory
    local_workspace = Path(__file__).parent.parent / "workspace" / "journal"
    try:
        local_workspace.mkdir(parents=True, exist_ok=True)
        return local_workspace / "trade_journal", local_workspace / "journal_logs"
    except (OSError, PermissionError):
        pass
    
    # Last resort: temp directory
    import tempfile
    temp_path = Path(tempfile.gettempdir()) / "forex_journal"
    temp_path.mkdir(parents=True, exist_ok=True)
    return temp_path / "trade_journal", temp_path / "journal_logs"

JOURNAL_DIR, LOGS_DIR = get_journal_paths()
JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)


class TradeStatus(str, Enum):
    PENDING = "pending"
    EXECUTED = "executed"
    MODIFIED = "modified"
    CLOSED_TP = "closed_tp"
    CLOSED_SL = "closed_sl"
    CLOSED_MANUAL = "closed_manual"
    CLOSED_BE = "closed_breakeven"
    CANCELLED = "cancelled"


class TradeOutcome(str, Enum):
    WIN = "win"
    LOSS = "loss"
    BREAKEVEN = "breakeven"
    OPEN = "open"


# ═══════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ═══════════════════════════════════════════════════════════════

class TradeExecutionRequest(BaseModel):
    """Request to log a trade execution with full context."""
    trade_id: str
    symbol: str
    direction: str  # "long" or "short"
    entry_price: float
    stop_loss: float
    take_profit: float
    lot_size: float = 0.01
    
    # Strategy context
    strategy: str
    strategy_score: int = 0
    
    # Confluence at entry
    confluence_score: int = 0
    confluence_breakdown: dict = {}
    
    # Trade thesis (why we took this trade)
    thesis: dict = {}
    
    # Agent verdicts at entry
    agent_verdicts: dict = {}
    
    # Optional
    broker_ticket: int = 0
    entry_type: str = "market"  # "market" or "limit"
    timeframe: str = "H1"


class TradeCloseRequest(BaseModel):
    """Request to close a trade."""
    trade_id: str
    exit_price: float
    exit_reason: str  # "tp", "sl", "manual", "breakeven"
    notes: Optional[str] = None


class TradeReviewRequest(BaseModel):
    """Manual trade review/grading."""
    trade_id: str
    grade: str  # A, B, C, D, F
    expectation_met: bool
    lessons: List[str] = []
    notes: str = ""


# ═══════════════════════════════════════════════════════════════
# IN-MEMORY STATE
# ═══════════════════════════════════════════════════════════════

trades: Dict[str, dict] = {}  # Active trades in memory
trade_history: List[dict] = []  # Recent closed trades


# ═══════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def generate_trade_id(symbol: str) -> str:
    """Generate unique trade ID."""
    ts = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    uid = uuid.uuid4().hex[:4].upper()
    return f"{symbol}-{ts}-{uid}"


def calculate_pips(entry: float, exit: float, direction: str, symbol: str) -> float:
    """Calculate pip difference."""
    multiplier = 100 if "JPY" in symbol else 10000
    if direction.lower() in ["long", "buy"]:
        return round((exit - entry) * multiplier, 1)
    else:
        return round((entry - exit) * multiplier, 1)


def calculate_r_multiple(entry: float, exit: float, stop: float, direction: str) -> float:
    """Calculate R-multiple (reward relative to risk)."""
    if direction.lower() in ["long", "buy"]:
        risk = abs(entry - stop)
        reward = exit - entry
    else:
        risk = abs(stop - entry)
        reward = entry - exit
    
    if risk == 0:
        return 0.0
    return round(reward / risk, 2)


def save_trade_to_log(trade: dict):
    """Save trade to daily log file."""
    date = datetime.utcnow().strftime("%Y-%m-%d")
    log_file = LOGS_DIR / f"trades_{date}.json"
    
    # Load existing
    existing = []
    if log_file.exists():
        try:
            with open(log_file, 'r') as f:
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
    with open(log_file, 'w') as f:
        json.dump(existing, f, indent=2, default=str)


def load_trades(days: int = 30) -> List[dict]:
    """Load trades from recent days."""
    all_trades = []
    for i in range(days):
        date = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
        log_file = LOGS_DIR / f"trades_{date}.json"
        if log_file.exists():
            try:
                with open(log_file, 'r') as f:
                    all_trades.extend(json.load(f))
            except:
                pass
    return all_trades


def calculate_statistics(trades_list: List[dict]) -> dict:
    """Calculate aggregate statistics."""
    closed = [t for t in trades_list if t.get("status", "").startswith("closed")]
    
    if not closed:
        return {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0,
            "total_r": 0,
            "avg_r": 0,
            "best_trade": None,
            "worst_trade": None,
        }
    
    wins = [t for t in closed if t.get("result_r", 0) > 0]
    losses = [t for t in closed if t.get("result_r", 0) < 0]
    
    total_r = sum(t.get("result_r", 0) for t in closed)
    
    # Best/worst
    sorted_by_r = sorted(closed, key=lambda x: x.get("result_r", 0))
    
    # By strategy
    by_strategy = {}
    for t in closed:
        strat = t.get("strategy", "unknown")
        if strat not in by_strategy:
            by_strategy[strat] = {"count": 0, "wins": 0, "total_r": 0}
        by_strategy[strat]["count"] += 1
        by_strategy[strat]["total_r"] += t.get("result_r", 0)
        if t.get("result_r", 0) > 0:
            by_strategy[strat]["wins"] += 1
    
    for strat in by_strategy:
        count = by_strategy[strat]["count"]
        by_strategy[strat]["win_rate"] = round(by_strategy[strat]["wins"] / count * 100, 1)
        by_strategy[strat]["avg_r"] = round(by_strategy[strat]["total_r"] / count, 2)
    
    return {
        "total_trades": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(closed) - len(wins) - len(losses),
        "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else 0,
        "total_r": round(total_r, 2),
        "avg_r": round(total_r / len(closed), 2) if closed else 0,
        "best_trade": sorted_by_r[-1] if sorted_by_r else None,
        "worst_trade": sorted_by_r[0] if sorted_by_r else None,
        "by_strategy": by_strategy,
    }


# ═══════════════════════════════════════════════════════════════
# API ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.on_event("startup")
async def startup():
    print(f"🚀 {AGENT_NAME} (Trade Journal Agent) v2.0 starting...")
    print(f"   📁 Journal directory: {JOURNAL_DIR}")
    print(f"   📁 Logs directory: {LOGS_DIR}")
    print(f"   (Directories will be created automatically if they don't exist)")


@app.get("/api/status")
async def get_status():
    """Get agent status."""
    recent = load_trades(7)
    stats = calculate_statistics(recent)
    return {
        "agent_id": "journal",
        "name": AGENT_NAME,
        "status": "active",
        "version": "2.0",
        "trades_this_week": len(recent),
        "open_trades": len(trades),
        "win_rate": stats.get("win_rate", 0),
        "total_r": stats.get("total_r", 0),
    }


@app.post("/api/trade/execute")
async def execute_trade(request: TradeExecutionRequest):
    """
    Log a trade execution with full context and generate journal entry.
    This is called when a trade is actually executed.
    """
    trade_id = request.trade_id
    
    # Create trade record
    trade = {
        "trade_id": trade_id,
        "symbol": request.symbol,
        "direction": request.direction,
        "entry_price": request.entry_price,
        "stop_loss": request.stop_loss,
        "take_profit": request.take_profit,
        "lot_size": request.lot_size,
        "strategy": request.strategy,
        "strategy_score": request.strategy_score,
        "confluence_score": request.confluence_score,
        "confluence_breakdown": request.confluence_breakdown,
        "thesis": request.thesis,
        "agent_verdicts": request.agent_verdicts,
        "broker_ticket": request.broker_ticket,
        "entry_type": request.entry_type,
        "timeframe": request.timeframe,
        "status": TradeStatus.EXECUTED.value,
        "executed_at": datetime.utcnow().isoformat(),
        "outcome": TradeOutcome.OPEN.value,
    }
    
    # Calculate risk in pips
    trade["risk_pips"] = abs(request.entry_price - request.stop_loss) * (
        100 if "JPY" in request.symbol else 10000
    )
    
    # Store in memory and log
    trades[trade_id] = trade
    save_trade_to_log(trade)
    
    # Generate journal entry with charts
    journal_result = {}
    try:
        journal_result = await create_trade_journal_entry(
            trade_id=trade_id,
            symbol=request.symbol,
            direction=request.direction,
            entry_price=request.entry_price,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
            confluence_breakdown=request.confluence_breakdown,
            thesis=request.thesis,
            strategy=request.strategy,
            output_dir=str(JOURNAL_DIR),
        )
        trade["journal_folder"] = journal_result.get("folder", "")
        trade["journal_files"] = journal_result.get("files", {})
        save_trade_to_log(trade)
        
        print(f"[Chronicle] Trade executed and journaled: {trade_id}")
        print(f"   Symbol: {request.symbol} {request.direction.upper()}")
        print(f"   Entry: {request.entry_price}, SL: {request.stop_loss}, TP: {request.take_profit}")
        print(f"   Confluence: {request.confluence_score}/100")
        print(f"   Journal: {journal_result.get('folder', 'N/A')}")
        
    except Exception as e:
        print(f"[Chronicle] Journal generation error: {e}")
        import traceback
        traceback.print_exc()
    
    return {
        "trade_id": trade_id,
        "status": "executed",
        "journal": journal_result,
    }


@app.post("/api/trade/close")
async def close_trade(request: TradeCloseRequest):
    """Close a trade and calculate results."""
    trade_id = request.trade_id
    
    # Find trade
    if trade_id not in trades:
        # Try to load from logs
        recent = load_trades(30)
        for t in recent:
            if t.get("trade_id") == trade_id:
                trades[trade_id] = t
                break
    
    if trade_id not in trades:
        raise HTTPException(status_code=404, detail="Trade not found")
    
    trade = trades[trade_id]
    
    # Determine status
    if request.exit_reason == "tp":
        trade["status"] = TradeStatus.CLOSED_TP.value
    elif request.exit_reason == "sl":
        trade["status"] = TradeStatus.CLOSED_SL.value
    elif request.exit_reason == "breakeven":
        trade["status"] = TradeStatus.CLOSED_BE.value
    else:
        trade["status"] = TradeStatus.CLOSED_MANUAL.value
    
    trade["exit_price"] = request.exit_price
    trade["exit_reason"] = request.exit_reason
    trade["closed_at"] = datetime.utcnow().isoformat()
    trade["close_notes"] = request.notes or ""
    
    # Calculate results
    entry = trade.get("entry_price", 0)
    stop = trade.get("stop_loss", 0)
    direction = trade.get("direction", "long")
    symbol = trade.get("symbol", "EURUSD")
    
    trade["result_pips"] = calculate_pips(entry, request.exit_price, direction, symbol)
    trade["result_r"] = calculate_r_multiple(entry, request.exit_price, stop, direction)
    
    # Determine outcome
    if trade["result_r"] > 0.1:
        trade["outcome"] = TradeOutcome.WIN.value
    elif trade["result_r"] < -0.1:
        trade["outcome"] = TradeOutcome.LOSS.value
    else:
        trade["outcome"] = TradeOutcome.BREAKEVEN.value
    
    # Estimate monetary result (assuming $10/pip for standard lot)
    lot_size = trade.get("lot_size", 0.01)
    pip_value = 10 if "JPY" not in symbol else 9
    trade["result_usd"] = round(trade["result_pips"] * pip_value * lot_size * 10, 2)
    
    # Save updated trade
    save_trade_to_log(trade)
    trade_history.append(trade)
    
    # Update journal folder with exit info
    if trade.get("journal_folder"):
        try:
            exit_file = Path(trade["journal_folder"]) / "exit_info.json"
            with open(exit_file, 'w') as f:
                json.dump({
                    "exit_price": request.exit_price,
                    "exit_reason": request.exit_reason,
                    "result_pips": trade["result_pips"],
                    "result_r": trade["result_r"],
                    "result_usd": trade["result_usd"],
                    "outcome": trade["outcome"],
                    "closed_at": trade["closed_at"],
                    "notes": request.notes,
                }, f, indent=2)
        except Exception as e:
            print(f"[Chronicle] Could not save exit info: {e}")
    
    # Remove from active trades
    del trades[trade_id]
    
    print(f"[Chronicle] Trade closed: {trade_id}")
    print(f"   Result: {trade['result_pips']:.1f} pips | {trade['result_r']:.2f}R | ${trade['result_usd']:.2f}")
    print(f"   Outcome: {trade['outcome'].upper()}")
    
    return {
        "trade_id": trade_id,
        "status": trade["status"],
        "outcome": trade["outcome"],
        "result_pips": trade["result_pips"],
        "result_r": trade["result_r"],
        "result_usd": trade["result_usd"],
    }


@app.post("/api/trade/review")
async def review_trade(request: TradeReviewRequest):
    """Add manual review to a closed trade."""
    trade_id = request.trade_id
    
    # Find trade
    trade = None
    recent = load_trades(30)
    for t in recent:
        if t.get("trade_id") == trade_id:
            trade = t
            break
    
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    
    # Add review
    trade["review"] = {
        "grade": request.grade,
        "expectation_met": request.expectation_met,
        "lessons": request.lessons,
        "notes": request.notes,
        "reviewed_at": datetime.utcnow().isoformat(),
    }
    
    save_trade_to_log(trade)
    
    # Save to journal folder
    if trade.get("journal_folder"):
        try:
            review_file = Path(trade["journal_folder"]) / "review.json"
            with open(review_file, 'w') as f:
                json.dump(trade["review"], f, indent=2)
        except:
            pass
    
    return {"trade_id": trade_id, "status": "reviewed"}


@app.get("/api/trades")
async def get_trades(days: int = 7, status: Optional[str] = None, outcome: Optional[str] = None):
    """Get trade history with filtering."""
    recent = load_trades(days)
    
    if status:
        recent = [t for t in recent if t.get("status", "").startswith(status)]
    if outcome:
        recent = [t for t in recent if t.get("outcome") == outcome]
    
    return {
        "trades": recent,
        "count": len(recent),
        "statistics": calculate_statistics(recent),
    }


@app.get("/api/trade/{trade_id}")
async def get_trade(trade_id: str):
    """Get specific trade details."""
    # Check memory first
    if trade_id in trades:
        return trades[trade_id]
    
    # Search logs
    recent = load_trades(60)
    for t in recent:
        if t.get("trade_id") == trade_id:
            return t
    
    raise HTTPException(status_code=404, detail="Trade not found")


@app.get("/api/trade/{trade_id}/chart")
async def get_trade_chart(trade_id: str):
    """Get the chart image for a trade."""
    recent = load_trades(60)
    for t in recent:
        if t.get("trade_id") == trade_id:
            chart_path = t.get("journal_files", {}).get("chart_h1")
            if chart_path and Path(chart_path).exists():
                return FileResponse(chart_path, media_type="image/png")
    
    raise HTTPException(status_code=404, detail="Chart not found")


@app.get("/api/statistics")
async def get_statistics(days: int = 30):
    """Get aggregate trading statistics."""
    recent = load_trades(days)
    return calculate_statistics(recent)


@app.get("/api/journal/{trade_id}")
async def get_journal_entry(trade_id: str):
    """Get full journal entry for a trade."""
    recent = load_trades(60)
    for t in recent:
        if t.get("trade_id") == trade_id:
            folder = t.get("journal_folder")
            if folder and Path(folder).exists():
                # Read all JSON files
                result = {"trade": t, "files": {}}
                for f in Path(folder).glob("*.json"):
                    try:
                        with open(f, 'r') as file:
                            result["files"][f.stem] = json.load(file)
                    except:
                        pass
                return result
    
    raise HTTPException(status_code=404, detail="Journal entry not found")


@app.get("/api/lessons")
async def get_lessons(days: int = 30):
    """Extract lessons from reviewed trades."""
    recent = load_trades(days)
    reviewed = [t for t in recent if t.get("review")]
    
    all_lessons = []
    lesson_counts = {}
    
    for t in reviewed:
        review = t.get("review", {})
        for lesson in review.get("lessons", []):
            all_lessons.append({
                "lesson": lesson,
                "trade_id": t.get("trade_id"),
                "symbol": t.get("symbol"),
                "outcome": t.get("outcome"),
                "result_r": t.get("result_r"),
            })
            lesson_counts[lesson] = lesson_counts.get(lesson, 0) + 1
    
    return {
        "lessons": all_lessons,
        "top_lessons": dict(sorted(lesson_counts.items(), key=lambda x: x[1], reverse=True)[:20]),
        "reviewed_count": len(reviewed),
    }


@app.post("/chat")
async def chat(request: ChatRequest):
    """Chat with Chronicle about trades and patterns."""
    stats = calculate_statistics(load_trades(30))
    recent = load_trades(7)
    
    context = f"""Trading Statistics (30 days):
- Total trades: {stats.get('total_trades', 0)}
- Win rate: {stats.get('win_rate', 0)}%
- Total R: {stats.get('total_r', 0)}
- Average R: {stats.get('avg_r', 0)}
- By strategy: {json.dumps(stats.get('by_strategy', {}), indent=2)}

Recent trades (7 days): {len(recent)}
Open trades: {len(trades)}
"""
    
    response = await call_claude(request.message, context, agent_name=AGENT_NAME)
    return {"response": response}


@app.get("/", response_class=HTMLResponse)
async def home():
    """Dashboard homepage."""
    recent = load_trades(30)
    stats = calculate_statistics(recent)
    open_count = len(trades)
    
    # Recent trades HTML
    trades_html = ""
    for t in sorted(recent, key=lambda x: x.get("executed_at", ""), reverse=True)[:10]:
        outcome = t.get("outcome", "open")
        outcome_color = "#26a69a" if outcome == "win" else "#ef5350" if outcome == "loss" else "#f59e0b"
        result_r = t.get("result_r", 0)
        
        trades_html += f'''
        <div class="trade-row">
            <div>
                <span style="color: #2196f3; font-weight: 600;">{t.get("symbol", "?")}</span>
                <span style="color: {"#26a69a" if t.get("direction") == "long" else "#ef5350"}; margin-left: 8px;">
                    {t.get("direction", "?").upper()}
                </span>
            </div>
            <div style="color: #888; font-size: 11px;">{t.get("strategy", "?")}</div>
            <div style="color: {outcome_color}; font-weight: 600;">
                {result_r:+.2f}R
            </div>
            <div class="status" style="background: {outcome_color}20; color: {outcome_color};">
                {outcome.upper()}
            </div>
        </div>
        '''
    
    if not trades_html:
        trades_html = '<div style="color: #666; text-align: center; padding: 20px;">No trades yet</div>'
    
    # Strategy performance
    strategy_html = ""
    for strat, data in stats.get("by_strategy", {}).items():
        wr_color = "#26a69a" if data["win_rate"] >= 50 else "#ef5350"
        strategy_html += f'''
        <div style="display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #333;">
            <span>{strat}</span>
            <span style="color: {wr_color}">{data["win_rate"]}% ({data["count"]} trades)</span>
        </div>
        '''
    
    return f'''<!DOCTYPE html>
<html><head>
    <title>Chronicle - Trade Journal v2.0</title>
    <meta http-equiv="refresh" content="30">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, sans-serif; background: #0a0a0f; color: #e0e0e0; padding: 20px; }}
        .header {{ display: flex; align-items: center; gap: 15px; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid #333; }}
        .header h1 {{ color: #f59e0b; }}
        .version {{ background: #f59e0b20; color: #f59e0b; padding: 4px 12px; border-radius: 12px; font-size: 12px; }}
        .stats {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 15px; margin-bottom: 20px; }}
        .stat {{ background: #1a1a24; border-radius: 10px; padding: 20px; text-align: center; }}
        .stat-value {{ font-size: 28px; font-weight: bold; }}
        .stat-value.green {{ color: #26a69a; }}
        .stat-value.red {{ color: #ef5350; }}
        .stat-value.yellow {{ color: #f59e0b; }}
        .stat-label {{ font-size: 11px; color: #666; margin-top: 5px; text-transform: uppercase; }}
        .grid {{ display: grid; grid-template-columns: 2fr 1fr; gap: 20px; }}
        .card {{ background: #1a1a24; border-radius: 12px; padding: 20px; margin-bottom: 20px; }}
        .card h2 {{ font-size: 13px; color: #888; margin-bottom: 15px; text-transform: uppercase; letter-spacing: 1px; }}
        .trade-row {{ display: grid; grid-template-columns: 1fr 1fr 80px 80px; gap: 10px; align-items: center; padding: 12px; background: #0a0a0f; border-radius: 8px; margin: 8px 0; font-size: 13px; }}
        .status {{ padding: 4px 10px; border-radius: 6px; font-size: 10px; text-align: center; font-weight: 600; }}
        .chat-section {{ background: #1a1a24; border-radius: 12px; padding: 20px; }}
        .chat-messages {{ height: 150px; overflow-y: auto; background: #0a0a0f; border-radius: 8px; padding: 10px; margin-bottom: 10px; }}
        .chat-input {{ display: flex; gap: 10px; }}
        .chat-input input {{ flex: 1; padding: 12px; border-radius: 8px; border: 1px solid #333; background: #0a0a0f; color: #fff; }}
        .chat-input button {{ padding: 12px 24px; background: #f59e0b; color: #000; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Chronicle</h1>
        <span class="version">v2.0</span>
        <span style="color: #888; margin-left: auto;">Trade Journal with Chart Generation</span>
    </div>
    
    <div class="stats">
        <div class="stat">
            <div class="stat-value yellow">{open_count}</div>
            <div class="stat-label">Open Trades</div>
        </div>
        <div class="stat">
            <div class="stat-value">{stats.get("total_trades", 0)}</div>
            <div class="stat-label">Total (30d)</div>
        </div>
        <div class="stat">
            <div class="stat-value {"green" if stats.get("win_rate", 0) >= 50 else "red"}">{stats.get("win_rate", 0):.1f}%</div>
            <div class="stat-label">Win Rate</div>
        </div>
        <div class="stat">
            <div class="stat-value {"green" if stats.get("total_r", 0) >= 0 else "red"}">{stats.get("total_r", 0):+.1f}R</div>
            <div class="stat-label">Total R</div>
        </div>
        <div class="stat">
            <div class="stat-value {"green" if stats.get("avg_r", 0) >= 0 else "red"}">{stats.get("avg_r", 0):+.2f}</div>
            <div class="stat-label">Avg R/Trade</div>
        </div>
    </div>
    
    <div class="grid">
        <div class="card">
            <h2>Recent Trades</h2>
            {trades_html}
        </div>
        
        <div>
            <div class="card">
                <h2>Strategy Performance</h2>
                {strategy_html if strategy_html else '<div style="color: #666;">No data yet</div>'}
            </div>
            
            <div class="card">
                <h2>Journal Folder</h2>
                <div style="font-family: monospace; font-size: 11px; color: #888; word-break: break-all;">
                    {JOURNAL_DIR}
                </div>
            </div>
        </div>
    </div>
    
    <div class="chat-section">
        <h2 style="color: #f59e0b; margin-bottom: 15px;">Ask Chronicle</h2>
        <div class="chat-messages" id="messages"></div>
        <div class="chat-input">
            <input type="text" id="input" placeholder="Ask about trades, patterns, lessons..." onkeypress="if(event.key==='Enter')sendMessage()">
            <button onclick="sendMessage()">Send</button>
        </div>
    </div>
    
    <script>
        async function sendMessage() {{
            const input = document.getElementById('input');
            const messages = document.getElementById('messages');
            const text = input.value.trim();
            if (!text) return;
            messages.innerHTML += `<div style="margin:5px 0;padding:8px 12px;background:#1a1a24;border-radius:8px;font-size:12px">${{text}}</div>`;
            input.value = '';
            messages.scrollTop = messages.scrollHeight;
            
            try {{
                const response = await fetch('/chat', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{message: text}})
                }});
                const data = await response.json();
                messages.innerHTML += `<div style="margin:5px 0;padding:8px 12px;background:rgba(249,158,11,0.15);border-left:3px solid #f59e0b;border-radius:8px;font-size:12px">${{data.response.replace(/\\n/g, '<br>')}}</div>`;
            }} catch (e) {{
                messages.innerHTML += `<div style="color:#ef5350;font-size:12px">Error: ${{e.message}}</div>`;
            }}
            messages.scrollTop = messages.scrollHeight;
        }}
    </script>
</body>
</html>'''


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, access_log=False)
