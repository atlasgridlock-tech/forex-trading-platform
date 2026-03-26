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
        # Trade not found - this can happen for trades opened before Chronicle sync
        # Log it but don't fail - the trade closed in MT5 regardless
        print(f"[Chronicle] Trade {trade_id} not found for close - may be pre-sync trade")
        return {
            "trade_id": trade_id,
            "status": "not_found",
            "message": "Trade not in Chronicle - may have been opened before sync",
        }
    
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


@app.get("/api/trades/{trade_id}")
async def get_trade_by_id(trade_id: str):
    """Get a single trade by ID (alias for /api/trade/{trade_id})."""
    # Check in-memory first
    if trade_id in trades:
        return trades[trade_id]
    
    # Check loaded trades
    recent = load_trades(60)
    for t in recent:
        if t.get("trade_id") == trade_id:
            return t
    
    raise HTTPException(status_code=404, detail="Trade not found")


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
    
    # Count open trades from in-memory trades dict
    open_trades_list = [t for t in trades.values() if t.get("status") == "open"]
    open_count = len(open_trades_list)
    
    # Combine recent trades from logs with current open trades
    all_trades = list(trades.values()) + [t for t in recent if t.get("trade_id") not in trades]
    
    # Recent trades HTML with OPEN buttons that work
    trades_html = ""
    for t in sorted(all_trades, key=lambda x: x.get("executed_at", x.get("created_at", "")), reverse=True)[:15]:
        outcome = t.get("outcome", t.get("status", "open"))
        if outcome == "open":
            outcome_color = "#f59e0b"
        elif outcome == "win" or outcome == "closed_tp":
            outcome_color = "#26a69a"
        elif outcome == "loss" or outcome == "closed_sl":
            outcome_color = "#ef5350"
        else:
            outcome_color = "#888"
        
        result_r = t.get("result_r", 0) or 0
        direction = t.get("direction", "?")
        direction_color = "#26a69a" if direction.lower() in ["long", "bullish"] else "#ef5350"
        
        entry_price = t.get("entry_price", 0)
        stop_loss = t.get("stop_loss", 0)
        take_profit = t.get("take_profit", t.get("take_profit_1", 0))
        current_pnl = t.get("current_pnl", 0)
        strategy = t.get("strategy", "Unknown")
        trade_id = t.get("trade_id", "")
        journal_path = t.get("journal_path", "")
        executed_at = t.get("executed_at", t.get("created_at", ""))[:16] if t.get("executed_at") or t.get("created_at") else ""
        
        trades_html += f'''
        <div class="trade-card" onclick="showTradeDetails('{trade_id}')">
            <div class="trade-header">
                <div class="trade-pair">
                    <span class="symbol">{t.get("symbol", "?")}</span>
                    <span class="direction" style="color: {direction_color};">{direction.upper()}</span>
                </div>
                <div class="trade-result" style="color: {outcome_color};">
                    {result_r:+.2f}R
                </div>
            </div>
            <div class="trade-details">
                <div class="detail-row">
                    <span class="label">Strategy</span>
                    <span class="value">{strategy}</span>
                </div>
                <div class="detail-row">
                    <span class="label">Entry</span>
                    <span class="value">{entry_price:.5f}</span>
                </div>
                <div class="detail-row">
                    <span class="label">SL / TP</span>
                    <span class="value">{stop_loss:.5f} / {take_profit:.5f if take_profit else "—"}</span>
                </div>
                <div class="detail-row">
                    <span class="label">Time</span>
                    <span class="value">{executed_at}</span>
                </div>
            </div>
            <div class="trade-footer">
                <span class="status-badge" style="background: {outcome_color}20; color: {outcome_color};">
                    {outcome.upper().replace("_", " ")}
                </span>
                ''' + (f"<button class='open-btn' onclick='event.stopPropagation(); openJournal(\"{journal_path}\")'>📂 Journal</button>" if journal_path else "") + '''
            </div>
        </div>
        '''
    
    if not trades_html:
        trades_html = '<div class="empty-state">No trades recorded yet. Start trading to see your history here.</div>'
    
    # Strategy performance with more detail
    strategy_html = ""
    by_strategy = stats.get("by_strategy", {})
    for strat, data in sorted(by_strategy.items(), key=lambda x: x[1].get("total_r", 0), reverse=True):
        wr = data.get("win_rate", 0)
        total_r = data.get("total_r", 0)
        count = data.get("count", 0)
        wr_color = "#26a69a" if wr >= 50 else "#ef5350"
        r_color = "#26a69a" if total_r >= 0 else "#ef5350"
        
        strategy_html += f'''
        <div class="strategy-row">
            <div class="strategy-name">{strat}</div>
            <div class="strategy-stats">
                <span class="stat-item" style="color: {wr_color}">{wr:.0f}%</span>
                <span class="stat-item" style="color: {r_color}">{total_r:+.1f}R</span>
                <span class="stat-item trades">{count} trades</span>
            </div>
        </div>
        '''
    
    # Recent lessons/patterns section
    lessons_html = ""
    patterns = stats.get("patterns", [])
    for pattern in patterns[:5]:
        lessons_html += f'''<div class="lesson-item">{pattern}</div>'''
    
    return f'''<!DOCTYPE html>
<html><head>
    <title>Chronicle - Trade Journal v2.0</title>
    <meta http-equiv="refresh" content="30">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; 
            background: linear-gradient(135deg, #0a0a0f 0%, #12121a 100%); 
            color: #e0e0e0; 
            padding: 24px; 
            min-height: 100vh;
        }}
        
        .header {{ 
            display: flex; 
            align-items: center; 
            gap: 15px; 
            margin-bottom: 24px; 
            padding-bottom: 20px; 
            border-bottom: 1px solid rgba(255,255,255,0.1); 
        }}
        .header h1 {{ color: #f59e0b; font-size: 28px; letter-spacing: -0.5px; }}
        .version {{ background: rgba(245,158,11,0.15); color: #f59e0b; padding: 4px 12px; border-radius: 12px; font-size: 11px; font-weight: 600; }}
        .subtitle {{ color: #666; margin-left: auto; font-size: 13px; }}
        
        .stats {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 16px; margin-bottom: 24px; }}
        .stat {{ 
            background: rgba(26,26,36,0.8); 
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.05);
            border-radius: 12px; 
            padding: 20px; 
            text-align: center; 
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .stat:hover {{ transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0,0,0,0.3); }}
        .stat-value {{ font-size: 32px; font-weight: 700; letter-spacing: -1px; }}
        .stat-value.green {{ color: #26a69a; }}
        .stat-value.red {{ color: #ef5350; }}
        .stat-value.yellow {{ color: #f59e0b; }}
        .stat-label {{ font-size: 10px; color: #666; margin-top: 8px; text-transform: uppercase; letter-spacing: 1px; }}
        
        .main-grid {{ display: grid; grid-template-columns: 1.5fr 1fr; gap: 24px; }}
        
        .card {{ 
            background: rgba(26,26,36,0.8); 
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.05);
            border-radius: 16px; 
            padding: 24px; 
            margin-bottom: 24px; 
        }}
        .card h2 {{ 
            font-size: 12px; 
            color: #888; 
            margin-bottom: 20px; 
            text-transform: uppercase; 
            letter-spacing: 1.5px; 
            font-weight: 600;
        }}
        
        .trade-card {{ 
            background: rgba(10,10,15,0.8); 
            border: 1px solid rgba(255,255,255,0.05);
            border-radius: 12px; 
            padding: 16px; 
            margin-bottom: 12px; 
            cursor: pointer;
            transition: all 0.2s;
        }}
        .trade-card:hover {{ 
            background: rgba(20,20,30,0.9); 
            border-color: rgba(245,158,11,0.3);
            transform: translateX(4px);
        }}
        
        .trade-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }}
        .trade-pair {{ display: flex; align-items: center; gap: 8px; }}
        .symbol {{ font-size: 15px; font-weight: 700; color: #2196f3; }}
        .direction {{ font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 4px; background: rgba(255,255,255,0.05); }}
        .trade-result {{ font-size: 18px; font-weight: 700; }}
        
        .trade-details {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; padding: 12px 0; border-top: 1px solid rgba(255,255,255,0.05); border-bottom: 1px solid rgba(255,255,255,0.05); }}
        .detail-row {{ display: flex; justify-content: space-between; }}
        .detail-row .label {{ color: #555; font-size: 11px; }}
        .detail-row .value {{ color: #aaa; font-size: 11px; font-family: 'SF Mono', monospace; }}
        
        .trade-footer {{ display: flex; justify-content: space-between; align-items: center; margin-top: 12px; }}
        .status-badge {{ padding: 4px 10px; border-radius: 6px; font-size: 10px; font-weight: 600; text-transform: uppercase; }}
        .open-btn {{ 
            background: rgba(245,158,11,0.15); 
            color: #f59e0b; 
            border: 1px solid rgba(245,158,11,0.3);
            padding: 6px 12px; 
            border-radius: 6px; 
            font-size: 11px; 
            cursor: pointer;
            transition: all 0.2s;
        }}
        .open-btn:hover {{ background: rgba(245,158,11,0.25); }}
        
        .strategy-row {{ 
            display: flex; 
            justify-content: space-between; 
            align-items: center;
            padding: 12px 0; 
            border-bottom: 1px solid rgba(255,255,255,0.05); 
        }}
        .strategy-row:last-child {{ border-bottom: none; }}
        .strategy-name {{ font-size: 13px; font-weight: 500; }}
        .strategy-stats {{ display: flex; gap: 16px; }}
        .stat-item {{ font-size: 12px; font-weight: 600; }}
        .stat-item.trades {{ color: #666; font-weight: 400; }}
        
        .empty-state {{ 
            color: #555; 
            text-align: center; 
            padding: 40px 20px; 
            font-size: 14px;
        }}
        
        .lesson-item {{
            padding: 10px 12px;
            background: rgba(10,10,15,0.6);
            border-radius: 8px;
            margin-bottom: 8px;
            font-size: 12px;
            color: #aaa;
            border-left: 3px solid #f59e0b;
        }}
        
        .chat-section {{ 
            background: rgba(26,26,36,0.8); 
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.05);
            border-radius: 16px; 
            padding: 24px; 
        }}
        .chat-section h2 {{ color: #f59e0b; font-size: 16px; margin-bottom: 16px; }}
        .chat-messages {{ 
            height: 180px; 
            overflow-y: auto; 
            background: rgba(10,10,15,0.6); 
            border-radius: 12px; 
            padding: 16px; 
            margin-bottom: 16px; 
        }}
        .chat-input {{ display: flex; gap: 12px; }}
        .chat-input input {{ 
            flex: 1; 
            padding: 14px 16px; 
            border-radius: 10px; 
            border: 1px solid rgba(255,255,255,0.1); 
            background: rgba(10,10,15,0.8); 
            color: #fff; 
            font-size: 13px;
            transition: border-color 0.2s;
        }}
        .chat-input input:focus {{ outline: none; border-color: rgba(245,158,11,0.5); }}
        .chat-input button {{ 
            padding: 14px 28px; 
            background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); 
            color: #000; 
            border: none; 
            border-radius: 10px; 
            cursor: pointer; 
            font-weight: 600;
            font-size: 13px;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .chat-input button:hover {{ transform: translateY(-1px); box-shadow: 0 4px 12px rgba(245,158,11,0.3); }}
        
        /* Modal for trade details */
        .modal {{ 
            display: none; 
            position: fixed; 
            top: 0; left: 0; right: 0; bottom: 0; 
            background: rgba(0,0,0,0.8); 
            z-index: 1000; 
            padding: 40px;
            overflow-y: auto;
        }}
        .modal.active {{ display: flex; justify-content: center; }}
        .modal-content {{ 
            background: #1a1a24; 
            border-radius: 16px; 
            padding: 32px; 
            max-width: 600px; 
            width: 100%;
            max-height: 90vh;
            overflow-y: auto;
        }}
        .modal-close {{ 
            float: right; 
            background: none; 
            border: none; 
            color: #888; 
            font-size: 24px; 
            cursor: pointer; 
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Chronicle</h1>
        <span class="version">v2.0</span>
        <span class="subtitle">Trade Journal & Performance Analytics</span>
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
    
    <div class="main-grid">
        <div class="card">
            <h2>Recent Trades</h2>
            <div style="max-height: 500px; overflow-y: auto;">
                {trades_html}
            </div>
        </div>
        
        <div>
            <div class="card">
                <h2>Strategy Performance</h2>
                {strategy_html if strategy_html else '<div class="empty-state">Trade more to see strategy analysis</div>'}
            </div>
            
            <div class="card">
                <h2>Journal Location</h2>
                <div style="font-family: 'SF Mono', monospace; font-size: 11px; color: #666; word-break: break-all; padding: 12px; background: rgba(10,10,15,0.6); border-radius: 8px;">
                    {JOURNAL_DIR}
                </div>
                <button onclick="copyPath()" style="margin-top: 12px; padding: 8px 16px; background: rgba(255,255,255,0.1); border: none; border-radius: 6px; color: #888; cursor: pointer; font-size: 11px;">
                    📋 Copy Path
                </button>
            </div>
        </div>
    </div>
    
    <div class="chat-section">
        <h2>Ask Chronicle</h2>
        <div class="chat-messages" id="messages">
            <div style="color: #555; font-size: 12px; text-align: center; padding: 20px;">
                Ask me about your trading patterns, performance, or specific trades...
            </div>
        </div>
        <div class="chat-input">
            <input type="text" id="input" placeholder="e.g., What's my best performing strategy?" onkeypress="if(event.key==='Enter')sendMessage()">
            <button onclick="sendMessage()">Send</button>
        </div>
    </div>
    
    <!-- Trade Detail Modal -->
    <div class="modal" id="tradeModal">
        <div class="modal-content">
            <button class="modal-close" onclick="closeModal()">&times;</button>
            <div id="tradeDetails"></div>
        </div>
    </div>
    
    <script>
        function copyPath() {{
            navigator.clipboard.writeText("{JOURNAL_DIR}");
            alert("Journal path copied to clipboard!");
        }}
        
        function openJournal(path) {{
            if (path) {{
                // Open in file explorer (works on macOS)
                window.open("file://" + path, "_blank");
                // Also show alert with path
                alert("Journal folder: " + path + String.fromCharCode(10) + String.fromCharCode(10) + "If it didn't open, copy the path above.");
            }}
        }}
        
        async function showTradeDetails(tradeId) {{
            if (!tradeId) return;
            try {{
                const response = await fetch('/api/trades/' + tradeId);
                if (response.ok) {{
                    const trade = await response.json();
                    document.getElementById('tradeDetails').innerHTML = `
                        <h2 style="color: #f59e0b; margin-bottom: 20px;">${{trade.symbol}} ${{trade.direction?.toUpperCase()}}</h2>
                        <div style="display: grid; gap: 12px;">
                            <div><strong>Strategy:</strong> ${{trade.strategy}}</div>
                            <div><strong>Entry:</strong> ${{trade.entry_price}}</div>
                            <div><strong>Stop Loss:</strong> ${{trade.stop_loss}}</div>
                            <div><strong>Take Profit:</strong> ${{trade.take_profit || "—"}}</div>
                            <div><strong>Result:</strong> ${{trade.result_r?.toFixed(2) || "0.00"}}R</div>
                            <div><strong>Status:</strong> ${{trade.status}}</div>
                            <div><strong>Confluence:</strong> ${{trade.confluence_score || "—"}}/100</div>
                            <hr style="border-color: #333;">
                            <div><strong>Thesis:</strong></div>
                            <div style="font-size: 12px; color: #888;">
                                ${{trade.thesis?.why_here || "—"}}<br>
                                ${{trade.thesis?.why_now || "—"}}<br>
                                ${{trade.thesis?.invalidation || "—"}}
                            </div>
                        </div>
                    `;
                    document.getElementById('tradeModal').classList.add('active');
                }}
            }} catch (e) {{
                console.error(e);
            }}
        }}
        
        function closeModal() {{
            document.getElementById('tradeModal').classList.remove('active');
        }}
        
        // Close modal on outside click
        document.getElementById('tradeModal').addEventListener('click', function(e) {{
            if (e.target === this) closeModal();
        }});
        
        async function sendMessage() {{
            const input = document.getElementById('input');
            const messages = document.getElementById('messages');
            const text = input.value.trim();
            if (!text) return;
            messages.innerHTML += `<div style="margin:8px 0;padding:12px;background:rgba(255,255,255,0.05);border-radius:10px;font-size:13px">${{text}}</div>`;
            input.value = '';
            messages.scrollTop = messages.scrollHeight;
            
            try {{
                const response = await fetch('/chat', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{message: text}})
                }});
                const data = await response.json();
                messages.innerHTML += `<div style="margin:8px 0;padding:12px;background:rgba(245,158,11,0.1);border-left:3px solid #f59e0b;border-radius:10px;font-size:13px">${{data.response.replace(/\\n/g, '<br>')}}</div>`;
            }} catch (e) {{
                messages.innerHTML += `<div style="color:#ef5350;font-size:12px;padding:12px">Error: ${{e.message}}</div>`;
            }}
            messages.scrollTop = messages.scrollHeight;
        }}
    </script>
</body>
</html>'''


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, access_log=False)
