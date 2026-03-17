"""
Agent Monitoring Dashboard - Real-time health and message flow visualization
"""

from datetime import datetime, timedelta
from typing import Dict, List
import json

# Message flow tracking (in-memory for now)
message_log: List[dict] = []
MAX_LOG_SIZE = 500

def log_message(source: str, target: str, endpoint: str, status: str, latency_ms: float = 0):
    """Log an inter-agent message."""
    global message_log
    message_log.append({
        "timestamp": datetime.utcnow().isoformat(),
        "source": source,
        "target": target,
        "endpoint": endpoint,
        "status": status,
        "latency_ms": round(latency_ms, 2),
    })
    if len(message_log) > MAX_LOG_SIZE:
        message_log = message_log[-MAX_LOG_SIZE:]

def get_message_stats(minutes: int = 5) -> dict:
    """Get message statistics for the last N minutes."""
    cutoff = datetime.utcnow() - timedelta(minutes=minutes)
    recent = [m for m in message_log if datetime.fromisoformat(m["timestamp"]) > cutoff]
    
    total = len(recent)
    success = len([m for m in recent if m["status"] == "success"])
    failed = len([m for m in recent if m["status"] == "error"])
    avg_latency = sum(m["latency_ms"] for m in recent) / total if total > 0 else 0
    
    # Group by route
    routes = {}
    for m in recent:
        route = f"{m['source']} → {m['target']}"
        if route not in routes:
            routes[route] = {"count": 0, "success": 0, "failed": 0, "avg_latency": 0, "latencies": []}
        routes[route]["count"] += 1
        routes[route]["latencies"].append(m["latency_ms"])
        if m["status"] == "success":
            routes[route]["success"] += 1
        else:
            routes[route]["failed"] += 1
    
    for route in routes:
        lats = routes[route]["latencies"]
        routes[route]["avg_latency"] = round(sum(lats) / len(lats), 2) if lats else 0
        del routes[route]["latencies"]
    
    return {
        "period_minutes": minutes,
        "total_messages": total,
        "success": success,
        "failed": failed,
        "success_rate": round(success / total * 100, 1) if total > 0 else 100,
        "avg_latency_ms": round(avg_latency, 2),
        "routes": routes,
    }

def get_monitoring_dashboard_html(agent_status: dict, message_stats: dict) -> str:
    """Generate monitoring dashboard HTML."""
    
    # Agent health cards
    agent_cards = ""
    agent_info = {
        "curator": {"name": "Curator", "port": 3021, "role": "Market Data", "icon": "📡"},
        "sentinel": {"name": "Sentinel", "port": 3010, "role": "News/Events", "icon": "📰"},
        "oracle": {"name": "Oracle", "port": 3011, "role": "Macro Analysis", "icon": "🏛️"},
        "atlas": {"name": "Atlas Jr.", "port": 3012, "role": "Technical", "icon": "📊"},
        "architect": {"name": "Architect", "port": 3014, "role": "Structure", "icon": "🏗️"},
        "pulse": {"name": "Pulse", "port": 3015, "role": "Sentiment", "icon": "💓"},
        "compass": {"name": "Compass", "port": 3016, "role": "Regime", "icon": "🧭"},
        "tactician": {"name": "Tactician", "port": 3017, "role": "Strategy", "icon": "🎯"},
        "guardian": {"name": "Guardian", "port": 3013, "role": "Risk", "icon": "🛡️"},
        "balancer": {"name": "Balancer", "port": 3018, "role": "Portfolio", "icon": "⚖️"},
        "executor": {"name": "Executor", "port": 3019, "role": "Execution", "icon": "⚡"},
        "chronicle": {"name": "Chronicle", "port": 3022, "role": "Journal", "icon": "📜"},
        "arbiter": {"name": "Arbiter", "port": 3024, "role": "Governance", "icon": "⚖️"},
    }
    
    for key, info in agent_info.items():
        status = agent_status.get(key, {})
        online = status.get("status") == "online"
        data = status.get("data", {})
        
        status_color = "#22c55e" if online else "#ef4444"
        status_text = "ONLINE" if online else "OFFLINE"
        
        # Extract key metrics from agent data
        metrics = []
        if key == "curator":
            metrics = [
                f"Tradeable: {data.get('tradeable_symbols', 0)}/{data.get('total_symbols', 0)}",
                f"Quality: {data.get('avg_quality', 0):.1%}",
            ]
        elif key == "guardian":
            metrics = [
                f"Mode: {data.get('risk_mode', data.get('mode', 'unknown')).upper()}",
                f"Drawdown: {data.get('system_drawdown', 0):.1f}%",
            ]
        elif key == "executor":
            metrics = [
                f"Mode: {data.get('mode', 'unknown').upper()}",
                f"Bridge: {data.get('bridge_status', 'unknown')}",
            ]
        elif key == "compass":
            metrics = [
                f"Classified: {data.get('symbols_classified', 0)}",
                f"Tradeable: {data.get('tradeable_symbols', 0)}",
            ]
        elif key == "sentinel":
            metrics = [
                f"Mode: {data.get('mode', 'unknown').upper()}",
                f"Events: {data.get('events_tracked', 0)}",
            ]
        else:
            metrics = [f"Status: {data.get('status', 'active').upper()}"]
        
        metrics_html = "".join([f'<div class="agent-metric">{m}</div>' for m in metrics])
        
        agent_cards += f'''
        <div class="agent-card {'online' if online else 'offline'}">
            <div class="agent-header">
                <span class="agent-icon">{info['icon']}</span>
                <div class="agent-title">
                    <span class="agent-name">{info['name']}</span>
                    <span class="agent-role">{info['role']}</span>
                </div>
                <span class="agent-status" style="color:{status_color}">{status_text}</span>
            </div>
            <div class="agent-metrics">{metrics_html}</div>
            <div class="agent-port">Port: {info['port']}</div>
        </div>
        '''
    
    # Message flow stats
    routes_html = ""
    for route, stats in message_stats.get("routes", {}).items():
        success_rate = stats["success"] / stats["count"] * 100 if stats["count"] > 0 else 100
        rate_color = "#22c55e" if success_rate >= 95 else "#f59e0b" if success_rate >= 80 else "#ef4444"
        routes_html += f'''
        <div class="route-row">
            <span class="route-name">{route}</span>
            <span class="route-count">{stats['count']} msgs</span>
            <span class="route-rate" style="color:{rate_color}">{success_rate:.0f}%</span>
            <span class="route-latency">{stats['avg_latency']:.0f}ms</span>
        </div>
        '''
    
    if not routes_html:
        routes_html = '<div class="no-data">No message data yet</div>'
    
    # Calculate overall health
    online_count = len([a for a in agent_status.values() if a.get("status") == "online"])
    total_count = len(agent_info)
    health_pct = online_count / total_count * 100 if total_count > 0 else 0
    health_color = "#22c55e" if health_pct >= 90 else "#f59e0b" if health_pct >= 70 else "#ef4444"
    
    return f'''<!DOCTYPE html>
<html>
<head>
    <title>Agent Monitor - Forex Trading Platform</title>
    <meta http-equiv="refresh" content="10">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono&display=swap" rel="stylesheet">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        :root {{
            --bg-primary: #0a0a0f;
            --bg-secondary: #12121a;
            --bg-card: #1a1a24;
            --accent: #3b82f6;
            --success: #22c55e;
            --warning: #f59e0b;
            --danger: #ef4444;
            --text: #e0e0e0;
            --text-dim: #888;
        }}
        
        body {{
            font-family: 'Inter', sans-serif;
            background: var(--bg-primary);
            color: var(--text);
            min-height: 100vh;
            padding: 20px;
        }}
        
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 1px solid #2a2a35;
        }}
        
        .header h1 {{
            font-size: 24px;
            color: var(--accent);
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        
        .health-badge {{
            display: flex;
            align-items: center;
            gap: 15px;
        }}
        
        .health-circle {{
            width: 60px;
            height: 60px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 18px;
            font-weight: 700;
            border: 3px solid {health_color};
            color: {health_color};
        }}
        
        .health-label {{
            font-size: 14px;
            color: var(--text-dim);
        }}
        
        .health-value {{
            font-size: 20px;
            font-weight: 600;
        }}
        
        .dashboard-grid {{
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 20px;
        }}
        
        .section {{
            background: var(--bg-card);
            border-radius: 12px;
            padding: 20px;
        }}
        
        .section-title {{
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 15px;
            color: var(--accent);
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        
        .agents-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
        }}
        
        .agent-card {{
            background: var(--bg-secondary);
            border-radius: 8px;
            padding: 12px;
            border-left: 3px solid var(--success);
        }}
        
        .agent-card.offline {{
            border-left-color: var(--danger);
            opacity: 0.7;
        }}
        
        .agent-header {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 8px;
        }}
        
        .agent-icon {{
            font-size: 18px;
        }}
        
        .agent-title {{
            flex: 1;
        }}
        
        .agent-name {{
            font-weight: 600;
            font-size: 13px;
            display: block;
        }}
        
        .agent-role {{
            font-size: 10px;
            color: var(--text-dim);
        }}
        
        .agent-status {{
            font-size: 9px;
            font-weight: 600;
            font-family: 'JetBrains Mono', monospace;
        }}
        
        .agent-metrics {{
            margin-bottom: 6px;
        }}
        
        .agent-metric {{
            font-size: 11px;
            color: var(--text-dim);
            font-family: 'JetBrains Mono', monospace;
        }}
        
        .agent-port {{
            font-size: 10px;
            color: #555;
            font-family: 'JetBrains Mono', monospace;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 12px;
            margin-bottom: 20px;
        }}
        
        .stat-card {{
            background: var(--bg-secondary);
            border-radius: 8px;
            padding: 12px;
            text-align: center;
        }}
        
        .stat-value {{
            font-size: 24px;
            font-weight: 700;
            color: var(--accent);
        }}
        
        .stat-label {{
            font-size: 11px;
            color: var(--text-dim);
            margin-top: 4px;
        }}
        
        .routes-list {{
            max-height: 300px;
            overflow-y: auto;
        }}
        
        .route-row {{
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 8px 0;
            border-bottom: 1px solid #2a2a35;
            font-size: 12px;
        }}
        
        .route-name {{
            flex: 1;
            font-family: 'JetBrains Mono', monospace;
            color: var(--text-dim);
        }}
        
        .route-count {{
            color: var(--text-dim);
            min-width: 60px;
        }}
        
        .route-rate {{
            font-weight: 600;
            min-width: 40px;
        }}
        
        .route-latency {{
            color: var(--text-dim);
            min-width: 50px;
            text-align: right;
        }}
        
        .no-data {{
            color: var(--text-dim);
            font-style: italic;
            padding: 20px;
            text-align: center;
        }}
        
        .back-link {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            color: var(--accent);
            text-decoration: none;
            font-size: 13px;
        }}
        
        .back-link:hover {{
            text-decoration: underline;
        }}
        
        .timestamp {{
            font-size: 11px;
            color: var(--text-dim);
            font-family: 'JetBrains Mono', monospace;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🔍 Agent Monitoring Dashboard</h1>
        <div class="health-badge">
            <div>
                <div class="health-label">System Health</div>
                <div class="health-value">{online_count}/{total_count} Online</div>
            </div>
            <div class="health-circle">{health_pct:.0f}%</div>
        </div>
    </div>
    
    <div class="dashboard-grid">
        <div class="section">
            <div class="section-title">🤖 Agent Status</div>
            <div class="agents-grid">
                {agent_cards}
            </div>
        </div>
        
        <div class="section">
            <div class="section-title">📊 Message Flow Stats ({message_stats.get('period_minutes', 5)}min)</div>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value">{message_stats.get('total_messages', 0)}</div>
                    <div class="stat-label">Total Messages</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" style="color: var(--success)">{message_stats.get('success_rate', 100):.0f}%</div>
                    <div class="stat-label">Success Rate</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{message_stats.get('failed', 0)}</div>
                    <div class="stat-label">Errors</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{message_stats.get('avg_latency_ms', 0):.0f}ms</div>
                    <div class="stat-label">Avg Latency</div>
                </div>
            </div>
            
            <div class="section-title">🔄 Route Activity</div>
            <div class="routes-list">
                {routes_html}
            </div>
        </div>
    </div>
    
    <div style="margin-top: 20px; display: flex; justify-content: space-between; align-items: center;">
        <a href="/" class="back-link">← Back to Main Dashboard</a>
        <span class="timestamp">Last updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</span>
    </div>
</body>
</html>'''
