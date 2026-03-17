"""
Performance Analytics Agent - Insight
Performance analysis, edge detection, statistical validation
"""

import os
import json
import asyncio
import httpx
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from collections import defaultdict

app = FastAPI(title="Insight - Performance Analytics Agent", version="1.0")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
JOURNAL_URL = os.getenv("JOURNAL_URL", "http://journal-agent:8000")
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://orchestrator-agent:8000")
AGENT_NAME = "Insight"
WORKSPACE = Path("/app/workspace")


class ChatRequest(BaseModel):
    message: str


# Cache for analytics
analytics_cache: Dict[str, dict] = {}
last_compute: Optional[datetime] = None


async def fetch_trades(days: int = 30) -> List[dict]:
    """Fetch trades from Chronicle."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{JOURNAL_URL}/api/trades?days={days}", timeout=10.0)
            if r.status_code == 200:
                data = r.json()
                return data.get("trades", [])
    except Exception as e:
        print(f"Error fetching trades: {e}")
    return []


def calculate_expectancy(trades: List[dict]) -> float:
    """Calculate expectancy per trade."""
    if not trades:
        return 0
    
    wins = [t for t in trades if t.get("result_r", 0) > 0]
    losses = [t for t in trades if t.get("result_r", 0) < 0]
    
    if not trades:
        return 0
    
    win_rate = len(wins) / len(trades)
    loss_rate = len(losses) / len(trades)
    
    avg_win = sum(t.get("result_r", 0) for t in wins) / len(wins) if wins else 0
    avg_loss = abs(sum(t.get("result_r", 0) for t in losses) / len(losses)) if losses else 0
    
    expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
    return round(expectancy, 3)


def calculate_profit_factor(trades: List[dict]) -> float:
    """Calculate profit factor (gross profit / gross loss)."""
    gross_profit = sum(t.get("result_r", 0) for t in trades if t.get("result_r", 0) > 0)
    gross_loss = abs(sum(t.get("result_r", 0) for t in trades if t.get("result_r", 0) < 0))
    
    if gross_loss == 0:
        return 99.99 if gross_profit > 0 else 0
    
    return round(gross_profit / gross_loss, 2)


def calculate_max_drawdown(trades: List[dict]) -> Tuple[float, int]:
    """Calculate maximum drawdown in R and duration."""
    if not trades:
        return 0, 0
    
    # Sort by close time
    sorted_trades = sorted(trades, key=lambda x: x.get("closed_at", ""))
    
    cumulative = 0
    peak = 0
    max_dd = 0
    dd_start = 0
    max_dd_duration = 0
    current_dd_start = 0
    
    for i, t in enumerate(sorted_trades):
        cumulative += t.get("result_r", 0)
        
        if cumulative > peak:
            peak = cumulative
            current_dd_start = i
        
        dd = peak - cumulative
        if dd > max_dd:
            max_dd = dd
            max_dd_duration = i - current_dd_start
    
    return round(max_dd, 2), max_dd_duration


def calculate_sharpe_ratio(trades: List[dict]) -> float:
    """Calculate Sharpe-like ratio for R values."""
    if len(trades) < 2:
        return 0
    
    returns = [t.get("result_r", 0) for t in trades]
    avg_return = sum(returns) / len(returns)
    
    variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
    std_dev = math.sqrt(variance) if variance > 0 else 0
    
    if std_dev == 0:
        return 0
    
    return round(avg_return / std_dev, 2)


def calculate_sortino_ratio(trades: List[dict]) -> float:
    """Calculate Sortino ratio (only downside deviation)."""
    if len(trades) < 2:
        return 0
    
    returns = [t.get("result_r", 0) for t in trades]
    avg_return = sum(returns) / len(returns)
    
    # Only negative returns for downside deviation
    negative_returns = [r for r in returns if r < 0]
    if not negative_returns:
        return 99.99 if avg_return > 0 else 0
    
    downside_variance = sum(r ** 2 for r in negative_returns) / len(negative_returns)
    downside_dev = math.sqrt(downside_variance)
    
    if downside_dev == 0:
        return 0
    
    return round(avg_return / downside_dev, 2)


def calculate_ulcer_index(trades: List[dict]) -> float:
    """Calculate Ulcer Index (RMS of drawdowns)."""
    if not trades:
        return 0
    
    sorted_trades = sorted(trades, key=lambda x: x.get("closed_at", ""))
    
    cumulative = 0
    peak = 0
    squared_dds = []
    
    for t in sorted_trades:
        cumulative += t.get("result_r", 0)
        peak = max(peak, cumulative)
        dd_pct = ((peak - cumulative) / peak * 100) if peak > 0 else 0
        squared_dds.append(dd_pct ** 2)
    
    if not squared_dds:
        return 0
    
    return round(math.sqrt(sum(squared_dds) / len(squared_dds)), 2)


def calculate_win_rate(trades: List[dict]) -> float:
    """Calculate win rate percentage."""
    if not trades:
        return 0
    wins = len([t for t in trades if t.get("result_r", 0) > 0])
    return round(wins / len(trades) * 100, 1)


def calculate_payoff_ratio(trades: List[dict]) -> float:
    """Calculate average win / average loss."""
    wins = [t.get("result_r", 0) for t in trades if t.get("result_r", 0) > 0]
    losses = [abs(t.get("result_r", 0)) for t in trades if t.get("result_r", 0) < 0]
    
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 1
    
    if avg_loss == 0:
        return 99.99 if avg_win > 0 else 0
    
    return round(avg_win / avg_loss, 2)


def calculate_z_score(trades: List[dict]) -> float:
    """Calculate Z-score for win rate statistical significance."""
    n = len(trades)
    if n < 10:
        return 0
    
    win_rate = calculate_win_rate(trades) / 100
    # Z = (observed - expected) / standard error
    # Expected = 0.5 (random), SE = sqrt(0.25/n)
    z = (win_rate - 0.5) / math.sqrt(0.25 / n)
    return round(z, 2)


def segment_by_field(trades: List[dict], field: str) -> Dict[str, dict]:
    """Segment performance by a specific field."""
    segments = defaultdict(list)
    
    for t in trades:
        key = t.get(field, "unknown")
        if key is None:
            key = "unknown"
        segments[str(key)].append(t)
    
    results = {}
    for key, segment_trades in segments.items():
        if len(segment_trades) < 3:  # Minimum sample
            continue
        results[key] = {
            "count": len(segment_trades),
            "win_rate": calculate_win_rate(segment_trades),
            "expectancy": calculate_expectancy(segment_trades),
            "profit_factor": calculate_profit_factor(segment_trades),
            "avg_r": round(sum(t.get("result_r", 0) for t in segment_trades) / len(segment_trades), 2),
            "total_r": round(sum(t.get("result_r", 0) for t in segment_trades), 2),
        }
    
    return results


def segment_by_day(trades: List[dict]) -> Dict[str, dict]:
    """Segment by day of week."""
    segments = defaultdict(list)
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    
    for t in trades:
        closed_at = t.get("closed_at", "")
        if closed_at:
            try:
                dt = datetime.fromisoformat(closed_at.replace("Z", "+00:00"))
                day_name = days[dt.weekday()]
                segments[day_name].append(t)
            except:
                pass
    
    results = {}
    for day, segment_trades in segments.items():
        if len(segment_trades) < 2:
            continue
        results[day] = {
            "count": len(segment_trades),
            "win_rate": calculate_win_rate(segment_trades),
            "avg_r": round(sum(t.get("result_r", 0) for t in segment_trades) / len(segment_trades), 2),
        }
    
    return results


def segment_by_hour(trades: List[dict]) -> Dict[str, dict]:
    """Segment by hour of day."""
    segments = defaultdict(list)
    
    for t in trades:
        closed_at = t.get("closed_at", "")
        if closed_at:
            try:
                dt = datetime.fromisoformat(closed_at.replace("Z", "+00:00"))
                hour = f"{dt.hour:02d}:00"
                segments[hour].append(t)
            except:
                pass
    
    results = {}
    for hour, segment_trades in segments.items():
        if len(segment_trades) < 2:
            continue
        results[hour] = {
            "count": len(segment_trades),
            "win_rate": calculate_win_rate(segment_trades),
            "avg_r": round(sum(t.get("result_r", 0) for t in segment_trades) / len(segment_trades), 2),
        }
    
    return results


def calculate_rolling_metrics(trades: List[dict], window: int = 20) -> List[dict]:
    """Calculate rolling metrics to detect edge decay."""
    if len(trades) < window:
        return []
    
    sorted_trades = sorted(trades, key=lambda x: x.get("closed_at", ""))
    rolling = []
    
    for i in range(window, len(sorted_trades) + 1):
        window_trades = sorted_trades[i - window:i]
        rolling.append({
            "index": i,
            "win_rate": calculate_win_rate(window_trades),
            "profit_factor": calculate_profit_factor(window_trades),
            "expectancy": calculate_expectancy(window_trades),
        })
    
    return rolling


def detect_edge_decay(trades: List[dict]) -> dict:
    """Detect if edge is decaying over time."""
    rolling = calculate_rolling_metrics(trades, window=20)
    
    if len(rolling) < 5:
        return {"status": "insufficient_data", "message": "Need more trades for decay analysis"}
    
    # Compare first half to second half of rolling metrics
    mid = len(rolling) // 2
    first_half = rolling[:mid]
    second_half = rolling[mid:]
    
    first_avg_pf = sum(r["profit_factor"] for r in first_half) / len(first_half)
    second_avg_pf = sum(r["profit_factor"] for r in second_half) / len(second_half)
    
    first_avg_wr = sum(r["win_rate"] for r in first_half) / len(first_half)
    second_avg_wr = sum(r["win_rate"] for r in second_half) / len(second_half)
    
    pf_change = ((second_avg_pf - first_avg_pf) / first_avg_pf * 100) if first_avg_pf > 0 else 0
    wr_change = second_avg_wr - first_avg_wr
    
    if pf_change < -20 or wr_change < -10:
        status = "decaying"
        message = f"Edge decay detected: PF {pf_change:+.1f}%, WR {wr_change:+.1f}%"
    elif pf_change < -10 or wr_change < -5:
        status = "warning"
        message = f"Possible edge weakening: PF {pf_change:+.1f}%, WR {wr_change:+.1f}%"
    else:
        status = "stable"
        message = f"Edge stable: PF {pf_change:+.1f}%, WR {wr_change:+.1f}%"
    
    return {
        "status": status,
        "message": message,
        "pf_change_pct": round(pf_change, 1),
        "wr_change": round(wr_change, 1),
        "current_pf": round(second_avg_pf, 2),
        "current_wr": round(second_avg_wr, 1),
    }


def calculate_cost_analysis(trades: List[dict]) -> dict:
    """Analyze slippage and spread costs."""
    total_slippage = sum(abs(t.get("slippage_pips", 0)) for t in trades)
    total_trades = len(trades)
    
    avg_slippage = total_slippage / total_trades if total_trades > 0 else 0
    
    # Estimate spread cost (would come from actual data)
    estimated_spread_per_trade = 1.0  # pips
    total_spread_cost = total_trades * estimated_spread_per_trade
    
    total_profit_pips = sum(t.get("result_pips", 0) for t in trades if t.get("result_pips", 0) > 0)
    
    slippage_impact = (total_slippage / total_profit_pips * 100) if total_profit_pips > 0 else 0
    spread_impact = (total_spread_cost / total_profit_pips * 100) if total_profit_pips > 0 else 0
    
    return {
        "total_slippage_pips": round(total_slippage, 1),
        "avg_slippage_pips": round(avg_slippage, 2),
        "estimated_spread_cost_pips": round(total_spread_cost, 1),
        "slippage_impact_pct": round(slippage_impact, 1),
        "spread_impact_pct": round(spread_impact, 1),
        "total_cost_pct": round(slippage_impact + spread_impact, 1),
    }


async def compute_full_analytics(days: int = 30) -> dict:
    """Compute full analytics suite."""
    trades = await fetch_trades(days)
    closed_trades = [t for t in trades if t.get("status") == "closed"]
    
    if not closed_trades:
        return {"error": "No closed trades found", "trades_analyzed": 0}
    
    # Core metrics
    core = {
        "trades_analyzed": len(closed_trades),
        "period_days": days,
        "win_rate": calculate_win_rate(closed_trades),
        "expectancy": calculate_expectancy(closed_trades),
        "profit_factor": calculate_profit_factor(closed_trades),
        "payoff_ratio": calculate_payoff_ratio(closed_trades),
        "sharpe_ratio": calculate_sharpe_ratio(closed_trades),
        "sortino_ratio": calculate_sortino_ratio(closed_trades),
        "ulcer_index": calculate_ulcer_index(closed_trades),
        "z_score": calculate_z_score(closed_trades),
        "total_r": round(sum(t.get("result_r", 0) for t in closed_trades), 2),
    }
    
    # Max drawdown
    max_dd, dd_duration = calculate_max_drawdown(closed_trades)
    core["max_drawdown_r"] = max_dd
    core["max_dd_duration_trades"] = dd_duration
    
    # Win/loss stats
    wins = [t for t in closed_trades if t.get("result_r", 0) > 0]
    losses = [t for t in closed_trades if t.get("result_r", 0) < 0]
    core["wins"] = len(wins)
    core["losses"] = len(losses)
    core["avg_win_r"] = round(sum(t.get("result_r", 0) for t in wins) / len(wins), 2) if wins else 0
    core["avg_loss_r"] = round(sum(t.get("result_r", 0) for t in losses) / len(losses), 2) if losses else 0
    
    # Segmented analysis
    by_symbol = segment_by_field(closed_trades, "symbol")
    by_regime = segment_by_field(closed_trades, "regime")
    by_strategy = segment_by_field(closed_trades, "strategy_family")
    by_day = segment_by_day(closed_trades)
    
    # Edge decay
    edge_decay = detect_edge_decay(closed_trades)
    
    # Cost analysis
    costs = calculate_cost_analysis(closed_trades)
    
    # Statistical significance
    z = core["z_score"]
    if z > 2.0:
        significance = "Highly significant (p < 0.05)"
    elif z > 1.65:
        significance = "Significant (p < 0.10)"
    elif z > 1.0:
        significance = "Marginally significant"
    else:
        significance = "Not statistically significant - may be luck"
    
    return {
        "computed_at": datetime.utcnow().isoformat(),
        "core_metrics": core,
        "by_symbol": by_symbol,
        "by_regime": by_regime,
        "by_strategy": by_strategy,
        "by_day": by_day,
        "edge_status": edge_decay,
        "cost_analysis": costs,
        "statistical_significance": significance,
    }


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
    print(f"🚀 {AGENT_NAME} (Performance Analytics Agent) v1.0 starting...")


@app.get("/", response_class=HTMLResponse)
async def home():
    analytics = await compute_full_analytics(30)
    core = analytics.get("core_metrics", {})
    edge = analytics.get("edge_status", {})
    
    # Determine colors
    pf = core.get("profit_factor", 0)
    pf_color = "#22c55e" if pf >= 1.5 else "#f59e0b" if pf >= 1.0 else "#ef4444"
    
    wr = core.get("win_rate", 0)
    wr_color = "#22c55e" if wr >= 55 else "#f59e0b" if wr >= 50 else "#ef4444"
    
    sharpe = core.get("sharpe_ratio", 0)
    sharpe_color = "#22c55e" if sharpe >= 1.0 else "#f59e0b" if sharpe >= 0.5 else "#ef4444"
    
    edge_status = edge.get("status", "unknown")
    edge_color = "#22c55e" if edge_status == "stable" else "#f59e0b" if edge_status == "warning" else "#ef4444"
    
    # Segment tables
    def make_segment_table(data: dict, title: str) -> str:
        if not data:
            return f"<div style='color:#666'>No {title.lower()} data</div>"
        
        rows = ""
        for key, vals in sorted(data.items(), key=lambda x: x[1].get("total_r", 0), reverse=True):
            wr = vals.get("win_rate", 0)
            color = "#22c55e" if wr >= 55 else "#f59e0b" if wr >= 50 else "#ef4444"
            rows += f'''<tr>
                <td>{key}</td>
                <td>{vals.get("count", 0)}</td>
                <td style="color:{color}">{wr:.1f}%</td>
                <td>{vals.get("profit_factor", 0):.2f}</td>
                <td>{vals.get("total_r", 0):+.2f}R</td>
            </tr>'''
        
        return f'''<table class="segment-table">
            <tr><th>{title}</th><th>Trades</th><th>Win%</th><th>PF</th><th>Total R</th></tr>
            {rows}
        </table>'''
    
    symbol_table = make_segment_table(analytics.get("by_symbol", {}), "Symbol")
    regime_table = make_segment_table(analytics.get("by_regime", {}), "Regime")
    strategy_table = make_segment_table(analytics.get("by_strategy", {}), "Strategy")
    
    return f'''<!DOCTYPE html>
<html><head>
    <title>📈 Insight - Analytics Agent</title>
    <meta http-equiv="refresh" content="60">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, sans-serif; background: #0a0a0f; color: #e0e0e0; padding: 20px; }}
        .header {{ display: flex; align-items: center; gap: 15px; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid #333; }}
        .header h1 {{ color: #3b82f6; }}
        .stats {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 15px; margin-bottom: 20px; }}
        .stat {{ background: #1a1a24; border-radius: 10px; padding: 15px; text-align: center; }}
        .stat-value {{ font-size: 24px; font-weight: bold; }}
        .stat-label {{ font-size: 11px; color: #666; margin-top: 5px; }}
        .grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-bottom: 20px; }}
        .card {{ background: #1a1a24; border-radius: 12px; padding: 15px; }}
        .card h3 {{ font-size: 12px; color: #888; margin-bottom: 10px; text-transform: uppercase; }}
        .segment-table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
        .segment-table th {{ text-align: left; padding: 6px; border-bottom: 1px solid #333; color: #888; }}
        .segment-table td {{ padding: 6px; border-bottom: 1px solid #222; }}
        .edge-box {{ background: {edge_color}20; border: 1px solid {edge_color}; border-radius: 10px; padding: 15px; margin-bottom: 20px; }}
        .edge-status {{ color: {edge_color}; font-weight: bold; font-size: 16px; }}
        .chat-section {{ background: #1a1a24; border-radius: 12px; padding: 20px; }}
        .chat-section h2 {{ color: #3b82f6; margin-bottom: 15px; }}
        .chat-messages {{ height: 100px; overflow-y: auto; background: #0a0a0f; border-radius: 8px; padding: 10px; margin-bottom: 10px; }}
        .chat-input {{ display: flex; gap: 10px; }}
        .chat-input input {{ flex: 1; padding: 10px; border-radius: 8px; border: 1px solid #333; background: #0a0a0f; color: #fff; }}
        .chat-input button {{ padding: 10px 20px; background: #3b82f6; color: #fff; border: none; border-radius: 8px; cursor: pointer; }}
        .message {{ margin: 8px 0; padding: 8px; border-radius: 6px; font-size: 13px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📈 Insight</h1>
        <span style="color: #888; margin-left: auto;">Performance Analytics Agent v1.0</span>
    </div>
    
    <div class="stats">
        <div class="stat">
            <div class="stat-value">{core.get("trades_analyzed", 0)}</div>
            <div class="stat-label">Trades (30d)</div>
        </div>
        <div class="stat">
            <div class="stat-value" style="color:{wr_color}">{core.get("win_rate", 0):.1f}%</div>
            <div class="stat-label">Win Rate</div>
        </div>
        <div class="stat">
            <div class="stat-value" style="color:{pf_color}">{core.get("profit_factor", 0):.2f}</div>
            <div class="stat-label">Profit Factor</div>
        </div>
        <div class="stat">
            <div class="stat-value" style="color:{sharpe_color}">{core.get("sharpe_ratio", 0):.2f}</div>
            <div class="stat-label">Sharpe Ratio</div>
        </div>
        <div class="stat">
            <div class="stat-value" style="color:{"#22c55e" if core.get("total_r", 0) >= 0 else "#ef4444"}">{core.get("total_r", 0):+.1f}R</div>
            <div class="stat-label">Total R</div>
        </div>
    </div>
    
    <div class="edge-box">
        <div class="edge-status">Edge Status: {edge_status.upper()}</div>
        <div style="font-size:13px;margin-top:5px">{edge.get("message", "")}</div>
        <div style="font-size:11px;color:#888;margin-top:5px">{analytics.get("statistical_significance", "")}</div>
    </div>
    
    <div class="grid">
        <div class="card">
            <h3>By Symbol</h3>
            {symbol_table}
        </div>
        <div class="card">
            <h3>By Regime</h3>
            {regime_table}
        </div>
        <div class="card">
            <h3>By Strategy</h3>
            {strategy_table}
        </div>
    </div>
    
    <div class="chat-section">
        <h2>💬 Ask Insight</h2>
        <div class="chat-messages" id="messages"></div>
        <div class="chat-input">
            <input type="text" id="input" placeholder="Ask about performance..." onkeypress="if(event.key==='Enter')sendMessage()">
            <button onclick="sendMessage()">Send</button>
        </div>
    </div>
    <script>
        const CHAT_KEY = 'insight_chat_history';
        
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
    analytics = await compute_full_analytics(30)
    context = f"Analytics: {json.dumps(analytics, default=str)[:4000]}"
    return {"response": await call_claude(request.message, context)}


@app.get("/api/analytics")
async def get_analytics(days: int = 30):
    """Get full analytics."""
    return await compute_full_analytics(days)


@app.get("/api/metrics")
async def get_core_metrics(days: int = 30):
    """Get core performance metrics."""
    analytics = await compute_full_analytics(days)
    return analytics.get("core_metrics", {})


@app.get("/api/segments/{field}")
async def get_segment(field: str, days: int = 30):
    """Get performance segmented by field."""
    trades = await fetch_trades(days)
    closed = [t for t in trades if t.get("status") == "closed"]
    return segment_by_field(closed, field)


@app.get("/api/edge")
async def get_edge_status(days: int = 30):
    """Get edge decay status."""
    analytics = await compute_full_analytics(days)
    return analytics.get("edge_status", {})


@app.get("/api/costs")
async def get_costs(days: int = 30):
    """Get cost analysis."""
    analytics = await compute_full_analytics(days)
    return analytics.get("cost_analysis", {})


@app.get("/api/status")
async def get_status():
    analytics = await compute_full_analytics(30)
    core = analytics.get("core_metrics", {})
    return {
        "agent_id": "analytics",
        "name": AGENT_NAME,
        "status": "active",
        "trades_analyzed": core.get("trades_analyzed", 0),
        "profit_factor": core.get("profit_factor", 0),
        "win_rate": core.get("win_rate", 0),
        "version": "1.0",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
