"""
Forex Trading Platform - Central Dashboard
Polished UI aggregating all agent data
"""

import os
import asyncio
import httpx
from datetime import datetime
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

app = FastAPI(title="Forex Trading Platform Dashboard", version="1.0")

# Agent URLs - use host.docker.internal when running in Docker
import os
HOST = os.getenv("AGENT_HOST", "host.docker.internal")

AGENTS = {
    "curator": f"http://{HOST}:3021",
    "sentinel": f"http://{HOST}:3010",
    "oracle": f"http://{HOST}:3011",
    "atlas": f"http://{HOST}:3012",
    "architect": f"http://{HOST}:3014",
    "pulse": f"http://{HOST}:3015",
    "compass": f"http://{HOST}:3016",
    "tactician": f"http://{HOST}:3017",
    "guardian": f"http://{HOST}:3013",
    "balancer": f"http://{HOST}:3018",
    "executor": f"http://{HOST}:3019",
    "nexus": f"http://{HOST}:3020",
    "chronicle": f"http://{HOST}:3022",
    "insight": f"http://{HOST}:3023",
    "arbiter": f"http://{HOST}:3024",
}

SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD", "EURGBP", "EURJPY"]


async def fetch(url: str, timeout: float = 3.0) -> Optional[dict]:
    """Fetch data from an agent."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(url, timeout=timeout)
            if r.status_code == 200:
                return r.json()
    except:
        pass
    return None


async def fetch_all_agents() -> Dict[str, dict]:
    """Fetch status from all agents."""
    results = {}
    for name, url in AGENTS.items():
        data = await fetch(f"{url}/api/status")
        results[name] = data if data else {"status": "offline"}
    return results


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Main dashboard page."""
    return get_dashboard_html()


@app.get("/api/overview")
async def api_overview():
    """Get overview data."""
    # Fetch from relevant agents
    guardian = await fetch(f"{AGENTS['guardian']}/api/status") or {}
    executor = await fetch(f"{AGENTS['executor']}/api/status") or {}
    balancer = await fetch(f"{AGENTS['balancer']}/api/exposure") or {}
    sentinel = await fetch(f"{AGENTS['sentinel']}/api/events") or {}
    curator = await fetch(f"{AGENTS['curator']}/api/account") or {}
    nexus = await fetch(f"{AGENTS['nexus']}/api/status") or {}
    
    return {
        "equity": curator.get("equity", 10000),
        "balance": curator.get("balance", 10000),
        "realized_pnl": guardian.get("daily_pnl", 0),
        "unrealized_pnl": curator.get("profit", 0),
        "risk_mode": guardian.get("risk_mode", "normal"),
        "open_positions": executor.get("open_positions", balancer.get("position_count", 0)),
        "blocked_symbols": sentinel.get("blocked_symbols", []),
        "upcoming_events": sentinel.get("upcoming_events", [])[:5],
        "watchlist_count": nexus.get("watchlist_count", 0),
        "decisions_today": nexus.get("decisions_made", 0),
    }


@app.get("/api/market")
async def api_market():
    """Get market monitor data."""
    market_data = []
    
    for symbol in SYMBOLS:
        # Fetch from multiple agents
        curator = await fetch(f"{AGENTS['curator']}/api/quality/{symbol}") or {}
        compass = await fetch(f"{AGENTS['compass']}/api/regime/{symbol}") or {}
        pulse = await fetch(f"{AGENTS['pulse']}/api/sentiment/{symbol}") or {}
        oracle = await fetch(f"{AGENTS['oracle']}/api/outlook/{symbol}") or {}
        atlas = await fetch(f"{AGENTS['atlas']}/api/analysis/{symbol}") or {}
        spread = await fetch(f"{AGENTS['curator']}/api/snapshot/spread/{symbol}") or {}
        
        market_data.append({
            "symbol": symbol,
            "regime": compass.get("regime", "unknown"),
            "regime_confidence": compass.get("confidence", 0),
            "spread": spread.get("spread_pips", 0),
            "quality": curator.get("overall", 70),
            "sentiment_score": pulse.get("crowding_score", 50),
            "sentiment_class": pulse.get("classification", "neutral"),
            "macro_bias": oracle.get("bias", "neutral"),
            "macro_strength": oracle.get("confidence", 50),
            "technical_grade": atlas.get("trend_grade", "C"),
            "technical_direction": atlas.get("trend_direction", "neutral"),
        })
    
    return {"symbols": market_data}


@app.get("/api/ideas")
async def api_ideas():
    """Get trade ideas from Nexus."""
    nexus = await fetch(f"{AGENTS['nexus']}/api/watchlist") or {}
    decisions = await fetch(f"{AGENTS['nexus']}/api/decisions?limit=10") or {}
    
    ideas = []
    for item in nexus.get("watchlist", []):
        confluence = await fetch(f"{AGENTS['nexus']}/api/confluence/{item['symbol']}?direction={item['direction']}") or {}
        ideas.append({
            **item,
            "score": confluence.get("confluence_score", item.get("score", 0)),
            "breakdown": confluence.get("score_breakdown", {}),
            "gates": confluence.get("hard_gates", []),
            "gates_passed": confluence.get("all_gates_passed", False),
        })
    
    # Add recent rejected trades
    for decision in decisions.get("decisions", []):
        if decision.get("decision") == "NO_TRADE":
            ideas.append({
                "symbol": decision.get("symbol"),
                "direction": decision.get("direction"),
                "score": decision.get("confluence_score", 0),
                "status": "rejected",
                "reason": decision.get("reason", ""),
                "timestamp": decision.get("timestamp"),
            })
    
    return {"ideas": ideas[:15]}


@app.get("/api/positions")
async def api_positions():
    """Get open positions."""
    curator = await fetch(f"{AGENTS['curator']}/api/positions") or {}
    lifecycle = await fetch(f"{AGENTS['nexus']}/api/lifecycle/active") or {}
    
    positions = []
    for pos in curator.get("positions", []):
        positions.append({
            "ticket": pos.get("ticket"),
            "symbol": pos.get("symbol"),
            "type": pos.get("type"),
            "volume": pos.get("volume"),
            "entry": pos.get("open_price"),
            "current": pos.get("current_price"),
            "stop": pos.get("sl"),
            "target": pos.get("tp"),
            "pnl": pos.get("profit"),
            "pnl_pips": pos.get("pips", 0),
            "open_time": pos.get("open_time"),
        })
    
    # Add lifecycle data if available
    for trade in lifecycle.get("active_trades", []):
        for pos in positions:
            if pos["symbol"] == trade.get("symbol"):
                pos["pnl_r"] = trade.get("current_pnl_r", 0)
                pos["bars"] = trade.get("bars", 0)
    
    return {"positions": positions}


@app.get("/api/journal")
async def api_journal(
    pair: str = None,
    regime: str = None,
    strategy: str = None,
    days: int = 30
):
    """Get journal entries."""
    chronicle = await fetch(f"{AGENTS['chronicle']}/api/trades?days={days}") or {}
    
    trades = chronicle.get("trades", [])
    
    # Apply filters
    if pair:
        trades = [t for t in trades if t.get("symbol") == pair]
    if regime:
        trades = [t for t in trades if t.get("regime") == regime]
    if strategy:
        trades = [t for t in trades if t.get("strategy_family") == strategy]
    
    return {
        "trades": trades,
        "count": len(trades),
        "filters": {"pair": pair, "regime": regime, "strategy": strategy, "days": days}
    }


@app.get("/api/analytics")
async def api_analytics():
    """Get analytics data."""
    insight = await fetch(f"{AGENTS['insight']}/api/analytics") or {}
    
    return {
        "core_metrics": insight.get("core_metrics", {}),
        "by_symbol": insight.get("by_symbol", {}),
        "by_regime": insight.get("by_regime", {}),
        "by_strategy": insight.get("by_strategy", {}),
        "edge_status": insight.get("edge_status", {}),
        "cost_analysis": insight.get("cost_analysis", {}),
    }


@app.get("/api/governance")
async def api_governance():
    """Get governance data."""
    arbiter = await fetch(f"{AGENTS['arbiter']}/api/status") or {}
    requests = await fetch(f"{AGENTS['arbiter']}/api/requests") or {}
    
    # Get version info for each strategy
    versions = {}
    for strategy in ["PULLBACK_TREND", "BREAKOUT", "RANGE_FADE"]:
        v = await fetch(f"{AGENTS['arbiter']}/api/versions/{strategy}")
        if v:
            versions[strategy] = v
    
    return {
        "status": arbiter,
        "pending_requests": [r for r in requests.get("requests", []) if r.get("status") == "pending"],
        "recent_requests": requests.get("requests", [])[:10],
        "versions": versions,
        "kill_switches": {
            "guardian": (await fetch(f"{AGENTS['guardian']}/api/status") or {}).get("kill_switch", False),
            "executor": (await fetch(f"{AGENTS['executor']}/api/status") or {}).get("mode") == "halted",
        }
    }


@app.get("/api/health")
async def api_health():
    """Get system health."""
    agents = await fetch_all_agents()
    
    # Check specific health indicators
    curator = await fetch(f"{AGENTS['curator']}/api/status") or {}
    executor = await fetch(f"{AGENTS['executor']}/api/bridge") or {}
    
    return {
        "agents": {name: {"status": data.get("status", "offline"), "name": data.get("name", name)} 
                   for name, data in agents.items()},
        "agents_online": sum(1 for a in agents.values() if a.get("status") != "offline"),
        "agents_total": len(agents),
        "mt5_connected": executor.get("bridge_status") == "READY",
        "mt5_status": executor.get("bridge_status", "UNKNOWN"),
        "data_feed": curator.get("status") == "active",
        "data_quality": curator.get("avg_quality", 0),
        "last_update": datetime.utcnow().isoformat(),
    }


def get_dashboard_html():
    """Generate the dashboard HTML."""
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Forex Trading Platform</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        :root {
            --bg-primary: #0a0a0f;
            --bg-secondary: #12121a;
            --bg-card: #1a1a24;
            --border: #2a2a35;
            --text-primary: #ffffff;
            --text-secondary: #a0a0b0;
            --text-muted: #606070;
            --accent: #3b82f6;
            --accent-green: #22c55e;
            --accent-red: #ef4444;
            --accent-yellow: #f59e0b;
            --accent-purple: #8b5cf6;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
        }
        
        /* Navigation */
        .nav {
            position: fixed;
            left: 0;
            top: 0;
            bottom: 0;
            width: 220px;
            background: var(--bg-secondary);
            border-right: 1px solid var(--border);
            padding: 20px 0;
            z-index: 100;
        }
        
        .nav-logo {
            padding: 0 20px 20px;
            border-bottom: 1px solid var(--border);
            margin-bottom: 20px;
        }
        
        .nav-logo h1 {
            font-size: 18px;
            color: var(--accent);
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .nav-item {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 12px 20px;
            color: var(--text-secondary);
            text-decoration: none;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .nav-item:hover, .nav-item.active {
            background: var(--bg-card);
            color: var(--text-primary);
            border-left: 3px solid var(--accent);
        }
        
        .nav-item .icon { width: 20px; text-align: center; }
        
        /* Main Content */
        .main {
            margin-left: 220px;
            padding: 20px 30px;
            min-height: 100vh;
        }
        
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 25px;
            padding-bottom: 15px;
            border-bottom: 1px solid var(--border);
        }
        
        .header h2 { font-size: 24px; font-weight: 600; }
        
        .header-right {
            display: flex;
            align-items: center;
            gap: 15px;
        }
        
        .status-badge {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 16px;
            background: var(--bg-card);
            border-radius: 20px;
            font-size: 13px;
        }
        
        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--accent-green);
        }
        
        .status-dot.warning { background: var(--accent-yellow); }
        .status-dot.error { background: var(--accent-red); }
        
        /* Section */
        .section { display: none; }
        .section.active { display: block; }
        
        /* Cards */
        .card-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 25px;
        }
        
        .card {
            background: var(--bg-card);
            border-radius: 12px;
            padding: 20px;
            border: 1px solid var(--border);
        }
        
        .card-lg {
            grid-column: span 2;
        }
        
        .card-title {
            font-size: 12px;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 8px;
        }
        
        .card-value {
            font-size: 28px;
            font-weight: 600;
        }
        
        .card-value.positive { color: var(--accent-green); }
        .card-value.negative { color: var(--accent-red); }
        .card-value.warning { color: var(--accent-yellow); }
        
        .card-subtitle {
            font-size: 12px;
            color: var(--text-secondary);
            margin-top: 4px;
        }
        
        /* Tables */
        .table-container {
            background: var(--bg-card);
            border-radius: 12px;
            border: 1px solid var(--border);
            overflow: hidden;
            margin-bottom: 25px;
        }
        
        .table-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 15px 20px;
            border-bottom: 1px solid var(--border);
        }
        
        .table-header h3 {
            font-size: 14px;
            font-weight: 600;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
        }
        
        th {
            text-align: left;
            padding: 12px 16px;
            font-size: 11px;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            border-bottom: 1px solid var(--border);
        }
        
        td {
            padding: 12px 16px;
            font-size: 13px;
            border-bottom: 1px solid var(--border);
        }
        
        tr:hover { background: rgba(255,255,255,0.02); }
        
        .badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 500;
        }
        
        .badge-green { background: rgba(34,197,94,0.15); color: var(--accent-green); }
        .badge-red { background: rgba(239,68,68,0.15); color: var(--accent-red); }
        .badge-yellow { background: rgba(245,158,11,0.15); color: var(--accent-yellow); }
        .badge-blue { background: rgba(59,130,246,0.15); color: var(--accent); }
        .badge-purple { background: rgba(139,92,246,0.15); color: var(--accent-purple); }
        .badge-gray { background: rgba(160,160,176,0.15); color: var(--text-secondary); }
        
        /* Filters */
        .filters {
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
        }
        
        .filter-select {
            padding: 8px 12px;
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 8px;
            color: var(--text-primary);
            font-size: 13px;
        }
        
        /* Progress bars */
        .progress-bar {
            height: 6px;
            background: var(--bg-secondary);
            border-radius: 3px;
            overflow: hidden;
            margin-top: 8px;
        }
        
        .progress-fill {
            height: 100%;
            border-radius: 3px;
            transition: width 0.3s;
        }
        
        /* Charts container */
        .chart-container {
            position: relative;
            height: 200px;
            margin-top: 15px;
        }
        
        /* Loading */
        .loading {
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 40px;
            color: var(--text-muted);
        }
        
        /* Health grid */
        .health-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 10px;
        }
        
        .health-item {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 12px;
            background: var(--bg-secondary);
            border-radius: 8px;
        }
        
        .health-icon {
            width: 32px;
            height: 32px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 14px;
        }
        
        .health-icon.online { background: rgba(34,197,94,0.15); color: var(--accent-green); }
        .health-icon.offline { background: rgba(239,68,68,0.15); color: var(--accent-red); }
        
        /* Score breakdown */
        .score-breakdown {
            display: flex;
            flex-direction: column;
            gap: 8px;
            margin-top: 10px;
        }
        
        .score-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 12px;
        }
        
        .score-bar {
            flex: 1;
            margin: 0 10px;
            height: 4px;
            background: var(--bg-secondary);
            border-radius: 2px;
        }
        
        .score-fill {
            height: 100%;
            background: var(--accent);
            border-radius: 2px;
        }
        
        /* Responsive */
        @media (max-width: 1200px) {
            .card-grid { grid-template-columns: repeat(2, 1fr); }
        }
        
        @media (max-width: 900px) {
            .nav { width: 60px; }
            .nav-logo h1 span, .nav-item span { display: none; }
            .main { margin-left: 60px; }
        }
    </style>
</head>
<body>
    <!-- Navigation -->
    <nav class="nav">
        <div class="nav-logo">
            <h1>📊 <span>Trading Platform</span></h1>
        </div>
        <a class="nav-item active" data-section="overview">
            <span class="icon">🏠</span>
            <span>Overview</span>
        </a>
        <a class="nav-item" data-section="market">
            <span class="icon">📈</span>
            <span>Market Monitor</span>
        </a>
        <a class="nav-item" data-section="ideas">
            <span class="icon">💡</span>
            <span>Trade Ideas</span>
        </a>
        <a class="nav-item" data-section="positions">
            <span class="icon">📋</span>
            <span>Open Positions</span>
        </a>
        <a class="nav-item" data-section="journal">
            <span class="icon">📔</span>
            <span>Journal</span>
        </a>
        <a class="nav-item" data-section="analytics">
            <span class="icon">📊</span>
            <span>Analytics</span>
        </a>
        <a class="nav-item" data-section="governance">
            <span class="icon">⚖️</span>
            <span>Governance</span>
        </a>
        <a class="nav-item" data-section="health">
            <span class="icon">🏥</span>
            <span>System Health</span>
        </a>
    </nav>
    
    <!-- Main Content -->
    <main class="main">
        <!-- Overview Section -->
        <section id="overview" class="section active">
            <div class="header">
                <h2>Overview</h2>
                <div class="header-right">
                    <div class="status-badge">
                        <span class="status-dot" id="system-status"></span>
                        <span id="system-status-text">Connecting...</span>
                    </div>
                    <div class="status-badge">
                        <span id="current-time"></span>
                    </div>
                </div>
            </div>
            
            <div class="card-grid">
                <div class="card">
                    <div class="card-title">Account Equity</div>
                    <div class="card-value" id="equity">$10,000</div>
                    <div class="card-subtitle" id="equity-change">Loading...</div>
                </div>
                <div class="card">
                    <div class="card-title">Today's P&L</div>
                    <div class="card-value" id="daily-pnl">$0.00</div>
                    <div class="card-subtitle" id="daily-pnl-pct">0.00%</div>
                </div>
                <div class="card">
                    <div class="card-title">Unrealized P&L</div>
                    <div class="card-value" id="unrealized-pnl">$0.00</div>
                    <div class="card-subtitle" id="open-positions-count">0 positions</div>
                </div>
                <div class="card">
                    <div class="card-title">Risk Mode</div>
                    <div class="card-value" id="risk-mode">NORMAL</div>
                    <div class="card-subtitle" id="risk-mode-detail">0.5% max risk</div>
                </div>
            </div>
            
            <div class="card-grid">
                <div class="card card-lg">
                    <div class="card-title">Upcoming Events</div>
                    <div id="events-list" class="loading">Loading events...</div>
                </div>
                <div class="card">
                    <div class="card-title">Watchlist</div>
                    <div class="card-value" id="watchlist-count">0</div>
                    <div class="card-subtitle">potential setups</div>
                </div>
                <div class="card">
                    <div class="card-title">Decisions Today</div>
                    <div class="card-value" id="decisions-count">0</div>
                    <div class="card-subtitle">trade evaluations</div>
                </div>
            </div>
            
            <div class="table-container">
                <div class="table-header">
                    <h3>Blocked Symbols</h3>
                </div>
                <div id="blocked-symbols" style="padding: 20px; color: var(--text-muted);">No blocked symbols</div>
            </div>
        </section>
        
        <!-- Market Monitor Section -->
        <section id="market" class="section">
            <div class="header">
                <h2>Market Monitor</h2>
            </div>
            
            <div class="table-container">
                <div class="table-header">
                    <h3>Watchlist</h3>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>Regime</th>
                            <th>Spread</th>
                            <th>Quality</th>
                            <th>Sentiment</th>
                            <th>Macro</th>
                            <th>Technical</th>
                        </tr>
                    </thead>
                    <tbody id="market-table">
                        <tr><td colspan="7" class="loading">Loading market data...</td></tr>
                    </tbody>
                </table>
            </div>
        </section>
        
        <!-- Trade Ideas Section -->
        <section id="ideas" class="section">
            <div class="header">
                <h2>Trade Ideas</h2>
            </div>
            
            <div class="table-container">
                <div class="table-header">
                    <h3>Ranked Candidates</h3>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>Direction</th>
                            <th>Score</th>
                            <th>Status</th>
                            <th>Reason / Blockers</th>
                        </tr>
                    </thead>
                    <tbody id="ideas-table">
                        <tr><td colspan="5" class="loading">Loading trade ideas...</td></tr>
                    </tbody>
                </table>
            </div>
        </section>
        
        <!-- Positions Section -->
        <section id="positions" class="section">
            <div class="header">
                <h2>Open Positions</h2>
            </div>
            
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>Type</th>
                            <th>Size</th>
                            <th>Entry</th>
                            <th>Current</th>
                            <th>Stop</th>
                            <th>Target</th>
                            <th>P&L</th>
                            <th>R</th>
                        </tr>
                    </thead>
                    <tbody id="positions-table">
                        <tr><td colspan="9" class="loading">Loading positions...</td></tr>
                    </tbody>
                </table>
            </div>
        </section>
        
        <!-- Journal Section -->
        <section id="journal" class="section">
            <div class="header">
                <h2>Trade Journal</h2>
            </div>
            
            <div class="filters">
                <select class="filter-select" id="filter-pair">
                    <option value="">All Pairs</option>
                    <option value="EURUSD">EURUSD</option>
                    <option value="GBPUSD">GBPUSD</option>
                    <option value="USDJPY">USDJPY</option>
                </select>
                <select class="filter-select" id="filter-regime">
                    <option value="">All Regimes</option>
                    <option value="trending">Trending</option>
                    <option value="ranging">Ranging</option>
                </select>
                <select class="filter-select" id="filter-strategy">
                    <option value="">All Strategies</option>
                    <option value="pullback">Pullback</option>
                    <option value="breakout">Breakout</option>
                </select>
            </div>
            
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Date</th>
                            <th>Symbol</th>
                            <th>Side</th>
                            <th>Strategy</th>
                            <th>Regime</th>
                            <th>Entry</th>
                            <th>Exit</th>
                            <th>Result</th>
                        </tr>
                    </thead>
                    <tbody id="journal-table">
                        <tr><td colspan="8" class="loading">Loading journal...</td></tr>
                    </tbody>
                </table>
            </div>
        </section>
        
        <!-- Analytics Section -->
        <section id="analytics" class="section">
            <div class="header">
                <h2>Performance Analytics</h2>
            </div>
            
            <div class="card-grid">
                <div class="card">
                    <div class="card-title">Expectancy</div>
                    <div class="card-value" id="expectancy">0.00R</div>
                    <div class="card-subtitle">per trade</div>
                </div>
                <div class="card">
                    <div class="card-title">Win Rate</div>
                    <div class="card-value" id="win-rate">0%</div>
                    <div class="card-subtitle" id="win-loss-count">0W / 0L</div>
                </div>
                <div class="card">
                    <div class="card-title">Profit Factor</div>
                    <div class="card-value" id="profit-factor">0.00</div>
                    <div class="card-subtitle">gross profit / loss</div>
                </div>
                <div class="card">
                    <div class="card-title">Max Drawdown</div>
                    <div class="card-value negative" id="max-dd">0%</div>
                    <div class="card-subtitle">peak to trough</div>
                </div>
            </div>
            
            <div class="card-grid">
                <div class="card card-lg">
                    <div class="card-title">Performance by Symbol</div>
                    <div id="symbol-performance"></div>
                </div>
                <div class="card card-lg">
                    <div class="card-title">Performance by Regime</div>
                    <div id="regime-performance"></div>
                </div>
            </div>
        </section>
        
        <!-- Governance Section -->
        <section id="governance" class="section">
            <div class="header">
                <h2>Governance</h2>
            </div>
            
            <div class="card-grid">
                <div class="card">
                    <div class="card-title">Strategies Tracked</div>
                    <div class="card-value" id="strategies-count">0</div>
                </div>
                <div class="card">
                    <div class="card-title">Total Versions</div>
                    <div class="card-value" id="versions-count">0</div>
                </div>
                <div class="card">
                    <div class="card-title">Pending Changes</div>
                    <div class="card-value warning" id="pending-count">0</div>
                </div>
                <div class="card">
                    <div class="card-title">Kill Switches</div>
                    <div class="card-value" id="kill-switch-status">OFF</div>
                </div>
            </div>
            
            <div class="table-container">
                <div class="table-header">
                    <h3>Recent Change Requests</h3>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>Request ID</th>
                            <th>Strategy</th>
                            <th>Type</th>
                            <th>Status</th>
                            <th>Overfit Score</th>
                            <th>Date</th>
                        </tr>
                    </thead>
                    <tbody id="governance-table">
                        <tr><td colspan="6" class="loading">Loading governance data...</td></tr>
                    </tbody>
                </table>
            </div>
        </section>
        
        <!-- System Health Section -->
        <section id="health" class="section">
            <div class="header">
                <h2>System Health</h2>
            </div>
            
            <div class="card-grid">
                <div class="card">
                    <div class="card-title">Agents Online</div>
                    <div class="card-value" id="agents-online">0/15</div>
                </div>
                <div class="card">
                    <div class="card-title">MT5 Connection</div>
                    <div class="card-value" id="mt5-status">UNKNOWN</div>
                </div>
                <div class="card">
                    <div class="card-title">Data Quality</div>
                    <div class="card-value" id="data-quality">0%</div>
                </div>
                <div class="card">
                    <div class="card-title">Last Update</div>
                    <div class="card-value" id="last-update" style="font-size:16px">--</div>
                </div>
            </div>
            
            <div class="card">
                <div class="card-title">Agent Status</div>
                <div class="health-grid" id="health-grid">
                    <div class="loading">Loading agent status...</div>
                </div>
            </div>
        </section>
    </main>
    
    <script>
        // Navigation
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', () => {
                document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
                document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
                item.classList.add('active');
                document.getElementById(item.dataset.section).classList.add('active');
                loadSection(item.dataset.section);
            });
        });
        
        // Update time
        function updateTime() {
            document.getElementById('current-time').textContent = new Date().toLocaleTimeString();
        }
        setInterval(updateTime, 1000);
        updateTime();
        
        // Load section data
        async function loadSection(section) {
            switch(section) {
                case 'overview': loadOverview(); break;
                case 'market': loadMarket(); break;
                case 'ideas': loadIdeas(); break;
                case 'positions': loadPositions(); break;
                case 'journal': loadJournal(); break;
                case 'analytics': loadAnalytics(); break;
                case 'governance': loadGovernance(); break;
                case 'health': loadHealth(); break;
            }
        }
        
        // Format currency
        function formatCurrency(val) {
            return '$' + parseFloat(val).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
        }
        
        // Get badge class
        function getBadgeClass(value, type) {
            if (type === 'regime') {
                if (value.includes('trend')) return 'badge-green';
                if (value.includes('rang')) return 'badge-blue';
                if (value.includes('volat')) return 'badge-yellow';
                return 'badge-gray';
            }
            if (type === 'sentiment') {
                if (value === 'trend_supportive') return 'badge-green';
                if (value === 'overcrowded') return 'badge-red';
                if (value === 'contrarian') return 'badge-purple';
                return 'badge-gray';
            }
            if (type === 'status') {
                if (value === 'approved') return 'badge-green';
                if (value === 'rejected') return 'badge-red';
                if (value === 'pending') return 'badge-yellow';
                return 'badge-gray';
            }
            return 'badge-gray';
        }
        
        // Load Overview
        async function loadOverview() {
            try {
                const data = await fetch('/api/overview').then(r => r.json());
                
                document.getElementById('equity').textContent = formatCurrency(data.equity);
                document.getElementById('equity-change').textContent = `Balance: ${formatCurrency(data.balance)}`;
                
                const dailyPnl = data.realized_pnl || 0;
                document.getElementById('daily-pnl').textContent = formatCurrency(dailyPnl);
                document.getElementById('daily-pnl').className = 'card-value ' + (dailyPnl >= 0 ? 'positive' : 'negative');
                document.getElementById('daily-pnl-pct').textContent = ((dailyPnl / data.balance) * 100).toFixed(2) + '%';
                
                const unrealized = data.unrealized_pnl || 0;
                document.getElementById('unrealized-pnl').textContent = formatCurrency(unrealized);
                document.getElementById('unrealized-pnl').className = 'card-value ' + (unrealized >= 0 ? 'positive' : 'negative');
                document.getElementById('open-positions-count').textContent = data.open_positions + ' positions';
                
                const mode = data.risk_mode.toUpperCase();
                document.getElementById('risk-mode').textContent = mode;
                document.getElementById('risk-mode').className = 'card-value ' + (mode === 'HALTED' ? 'negative' : mode === 'DEFENSIVE' ? 'warning' : '');
                
                document.getElementById('watchlist-count').textContent = data.watchlist_count;
                document.getElementById('decisions-count').textContent = data.decisions_today;
                
                // Events
                const eventsHtml = data.upcoming_events.length ? 
                    data.upcoming_events.map(e => `<div style="padding:8px 0;border-bottom:1px solid var(--border)">${e.time || ''} - ${e.event || e}</div>`).join('') :
                    '<div style="color:var(--text-muted)">No upcoming events</div>';
                document.getElementById('events-list').innerHTML = eventsHtml;
                
                // Blocked symbols
                const blockedHtml = data.blocked_symbols.length ?
                    data.blocked_symbols.map(s => `<span class="badge badge-red">${s}</span>`).join(' ') :
                    'No blocked symbols';
                document.getElementById('blocked-symbols').innerHTML = blockedHtml;
                
                // System status
                const health = await fetch('/api/health').then(r => r.json());
                const statusDot = document.getElementById('system-status');
                const statusText = document.getElementById('system-status-text');
                
                if (health.agents_online >= 13 && health.mt5_connected) {
                    statusDot.className = 'status-dot';
                    statusText.textContent = 'All Systems Online';
                } else if (health.agents_online >= 10) {
                    statusDot.className = 'status-dot warning';
                    statusText.textContent = `${health.agents_online}/${health.agents_total} Agents`;
                } else {
                    statusDot.className = 'status-dot error';
                    statusText.textContent = 'System Issues';
                }
            } catch (e) {
                console.error('Error loading overview:', e);
            }
        }
        
        // Load Market
        async function loadMarket() {
            try {
                const data = await fetch('/api/market').then(r => r.json());
                const tbody = document.getElementById('market-table');
                
                tbody.innerHTML = data.symbols.map(s => `
                    <tr>
                        <td><strong>${s.symbol}</strong></td>
                        <td><span class="badge ${getBadgeClass(s.regime, 'regime')}">${s.regime}</span></td>
                        <td>${s.spread.toFixed(1)} pips</td>
                        <td>
                            <div style="display:flex;align-items:center;gap:8px">
                                <span>${s.quality}%</span>
                                <div class="progress-bar" style="width:60px">
                                    <div class="progress-fill" style="width:${s.quality}%;background:${s.quality > 80 ? 'var(--accent-green)' : s.quality > 60 ? 'var(--accent-yellow)' : 'var(--accent-red)'}"></div>
                                </div>
                            </div>
                        </td>
                        <td><span class="badge ${getBadgeClass(s.sentiment_class, 'sentiment')}">${s.sentiment_class}</span></td>
                        <td><span class="badge ${s.macro_bias === 'bullish' ? 'badge-green' : s.macro_bias === 'bearish' ? 'badge-red' : 'badge-gray'}">${s.macro_bias}</span></td>
                        <td><strong style="color:${s.technical_grade === 'A' ? 'var(--accent-green)' : s.technical_grade === 'B' ? 'var(--accent-yellow)' : 'var(--text-muted)'}">${s.technical_grade}</strong> ${s.technical_direction}</td>
                    </tr>
                `).join('');
            } catch (e) {
                console.error('Error loading market:', e);
            }
        }
        
        // Load Ideas
        async function loadIdeas() {
            try {
                const data = await fetch('/api/ideas').then(r => r.json());
                const tbody = document.getElementById('ideas-table');
                
                if (!data.ideas.length) {
                    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-muted)">No trade ideas currently</td></tr>';
                    return;
                }
                
                tbody.innerHTML = data.ideas.map(idea => `
                    <tr>
                        <td><strong>${idea.symbol}</strong></td>
                        <td><span class="badge ${idea.direction === 'long' ? 'badge-green' : 'badge-red'}">${idea.direction.toUpperCase()}</span></td>
                        <td><strong>${idea.score}/100</strong></td>
                        <td><span class="badge ${idea.status === 'rejected' ? 'badge-red' : idea.gates_passed ? 'badge-green' : 'badge-yellow'}">${idea.status || (idea.gates_passed ? 'READY' : 'BLOCKED')}</span></td>
                        <td style="font-size:12px;color:var(--text-secondary)">${idea.reason || (idea.gates ? idea.gates.filter(g => !g.passed).map(g => g.gate).join(', ') : '')}</td>
                    </tr>
                `).join('');
            } catch (e) {
                console.error('Error loading ideas:', e);
            }
        }
        
        // Load Positions
        async function loadPositions() {
            try {
                const data = await fetch('/api/positions').then(r => r.json());
                const tbody = document.getElementById('positions-table');
                
                if (!data.positions.length) {
                    tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--text-muted)">No open positions</td></tr>';
                    return;
                }
                
                tbody.innerHTML = data.positions.map(p => `
                    <tr>
                        <td><strong>${p.symbol}</strong></td>
                        <td><span class="badge ${p.type === 0 ? 'badge-green' : 'badge-red'}">${p.type === 0 ? 'BUY' : 'SELL'}</span></td>
                        <td>${p.volume}</td>
                        <td>${p.entry}</td>
                        <td>${p.current}</td>
                        <td style="color:var(--accent-red)">${p.stop || '-'}</td>
                        <td style="color:var(--accent-green)">${p.target || '-'}</td>
                        <td class="${p.pnl >= 0 ? 'positive' : 'negative'}">${formatCurrency(p.pnl)}</td>
                        <td><strong>${(p.pnl_r || 0).toFixed(2)}R</strong></td>
                    </tr>
                `).join('');
            } catch (e) {
                console.error('Error loading positions:', e);
            }
        }
        
        // Load Journal
        async function loadJournal() {
            try {
                const pair = document.getElementById('filter-pair').value;
                const regime = document.getElementById('filter-regime').value;
                const strategy = document.getElementById('filter-strategy').value;
                
                let url = '/api/journal?days=30';
                if (pair) url += '&pair=' + pair;
                if (regime) url += '&regime=' + regime;
                if (strategy) url += '&strategy=' + strategy;
                
                const data = await fetch(url).then(r => r.json());
                const tbody = document.getElementById('journal-table');
                
                if (!data.trades.length) {
                    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--text-muted)">No trades found</td></tr>';
                    return;
                }
                
                tbody.innerHTML = data.trades.slice(0, 50).map(t => `
                    <tr>
                        <td>${(t.closed_at || t.created_at || '').substring(0, 10)}</td>
                        <td><strong>${t.symbol}</strong></td>
                        <td><span class="badge ${t.side === 'long' ? 'badge-green' : 'badge-red'}">${t.side}</span></td>
                        <td>${t.strategy_family || '-'}</td>
                        <td><span class="badge ${getBadgeClass(t.regime || '', 'regime')}">${t.regime || '-'}</span></td>
                        <td>${t.entry_price || '-'}</td>
                        <td>${t.close_price || '-'}</td>
                        <td class="${(t.result_r || 0) >= 0 ? 'positive' : 'negative'}"><strong>${(t.result_r || 0).toFixed(2)}R</strong></td>
                    </tr>
                `).join('');
            } catch (e) {
                console.error('Error loading journal:', e);
            }
        }
        
        // Load Analytics
        async function loadAnalytics() {
            try {
                const data = await fetch('/api/analytics').then(r => r.json());
                const core = data.core_metrics || {};
                
                document.getElementById('expectancy').textContent = (core.expectancy || 0).toFixed(2) + 'R';
                document.getElementById('win-rate').textContent = (core.win_rate || 0).toFixed(1) + '%';
                document.getElementById('win-rate').className = 'card-value ' + ((core.win_rate || 0) >= 50 ? 'positive' : 'negative');
                document.getElementById('win-loss-count').textContent = `${core.wins || 0}W / ${core.losses || 0}L`;
                document.getElementById('profit-factor').textContent = (core.profit_factor || 0).toFixed(2);
                document.getElementById('max-dd').textContent = (core.max_drawdown_r || 0).toFixed(1) + 'R';
                
                // Symbol performance
                const symbolHtml = Object.entries(data.by_symbol || {}).map(([sym, stats]) => `
                    <div class="score-row">
                        <span>${sym}</span>
                        <span class="${stats.total_r >= 0 ? 'positive' : 'negative'}">${stats.total_r.toFixed(1)}R (${stats.win_rate.toFixed(0)}%)</span>
                    </div>
                `).join('') || '<div style="color:var(--text-muted)">No data</div>';
                document.getElementById('symbol-performance').innerHTML = symbolHtml;
                
                // Regime performance
                const regimeHtml = Object.entries(data.by_regime || {}).map(([regime, stats]) => `
                    <div class="score-row">
                        <span>${regime}</span>
                        <span class="${stats.total_r >= 0 ? 'positive' : 'negative'}">${stats.total_r.toFixed(1)}R (${stats.win_rate.toFixed(0)}%)</span>
                    </div>
                `).join('') || '<div style="color:var(--text-muted)">No data</div>';
                document.getElementById('regime-performance').innerHTML = regimeHtml;
            } catch (e) {
                console.error('Error loading analytics:', e);
            }
        }
        
        // Load Governance
        async function loadGovernance() {
            try {
                const data = await fetch('/api/governance').then(r => r.json());
                
                document.getElementById('strategies-count').textContent = data.status.strategies_tracked || 0;
                document.getElementById('versions-count').textContent = data.status.total_versions || 0;
                document.getElementById('pending-count').textContent = data.pending_requests.length || 0;
                
                const killActive = data.kill_switches.guardian || data.kill_switches.executor;
                document.getElementById('kill-switch-status').textContent = killActive ? 'ACTIVE' : 'OFF';
                document.getElementById('kill-switch-status').className = 'card-value ' + (killActive ? 'negative' : 'positive');
                
                const tbody = document.getElementById('governance-table');
                if (!data.recent_requests.length) {
                    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-muted)">No change requests</td></tr>';
                    return;
                }
                
                tbody.innerHTML = data.recent_requests.map(r => `
                    <tr>
                        <td>${r.request_id}</td>
                        <td><strong>${r.strategy_name}</strong></td>
                        <td>${r.change_type}</td>
                        <td><span class="badge ${getBadgeClass(r.status, 'status')}">${r.status.toUpperCase()}</span></td>
                        <td>${r.overfit_score || '-'}</td>
                        <td>${(r.created_at || '').substring(0, 16)}</td>
                    </tr>
                `).join('');
            } catch (e) {
                console.error('Error loading governance:', e);
            }
        }
        
        // Load Health
        async function loadHealth() {
            try {
                const data = await fetch('/api/health').then(r => r.json());
                
                document.getElementById('agents-online').textContent = `${data.agents_online}/${data.agents_total}`;
                document.getElementById('agents-online').className = 'card-value ' + (data.agents_online >= 13 ? 'positive' : data.agents_online >= 10 ? 'warning' : 'negative');
                
                document.getElementById('mt5-status').textContent = typeof data.mt5_status === 'string' ? data.mt5_status : (data.mt5_connected ? 'READY' : 'UNKNOWN');
                document.getElementById('mt5-status').className = 'card-value ' + (data.mt5_connected ? 'positive' : 'negative');
                
                document.getElementById('data-quality').textContent = (data.data_quality * 100 || 70) + '%';
                document.getElementById('last-update').textContent = new Date(data.last_update).toLocaleTimeString();
                
                const grid = document.getElementById('health-grid');
                grid.innerHTML = Object.entries(data.agents).map(([key, agent]) => `
                    <div class="health-item">
                        <div class="health-icon ${agent.status === 'active' || agent.status === 'online' ? 'online' : 'offline'}">
                            ${agent.status === 'active' || agent.status === 'online' ? '✓' : '✗'}
                        </div>
                        <div>
                            <div style="font-size:13px;font-weight:500">${agent.name || key}</div>
                            <div style="font-size:11px;color:var(--text-muted)">${agent.status}</div>
                        </div>
                    </div>
                `).join('');
            } catch (e) {
                console.error('Error loading health:', e);
            }
        }
        
        // Filter change handlers
        document.getElementById('filter-pair').addEventListener('change', loadJournal);
        document.getElementById('filter-regime').addEventListener('change', loadJournal);
        document.getElementById('filter-strategy').addEventListener('change', loadJournal);
        
        // Initial load
        loadOverview();
        
        // Auto-refresh
        setInterval(() => {
            const activeSection = document.querySelector('.section.active').id;
            loadSection(activeSection);
        }, 30000);
    </script>
</body>
</html>'''


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)
