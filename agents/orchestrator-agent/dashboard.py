"""
Rich Dashboard Template for Nexus v3.0
Full Trading Platform Experience
"""

def get_dashboard_html(
    agent_status: dict,
    decisions_log: list,
    watchlist: dict,
    market_data: dict,
    confluence_data: dict,
    account_data: dict,
    positions: list,
    events: list,
    guardian_status: dict,
    session_info: str,
):
    """Generate rich dashboard HTML."""
    
    # Count agents online
    agents_online = len([a for a in agent_status.values() if a.get("status") == "online"])
    total_agents = len(agent_status)
    
    # Agent status badges with clickable links
    agent_badges = ""
    agent_ports = {
        "curator": 3021, "sentinel": 3010, "oracle": 3011, "atlas": 3012,
        "architect": 3014, "pulse": 3015, "compass": 3016, "tactician": 3017,
        "guardian": 3013, "balancer": 3018, "executor": 3019, "chronicle": 3022, "arbiter": 3024
    }
    agent_order = ["curator", "sentinel", "oracle", "atlas", "architect", "pulse", "compass", "tactician", "guardian", "balancer", "executor", "chronicle", "arbiter"]
    for key in agent_order:
        status = agent_status.get(key, {})
        online = status.get("status") == "online"
        name = status.get("name", key.title())
        color = "#22c55e" if online else "#ef4444"
        port = agent_ports.get(key, 8000)
        agent_badges += f'''<a href="http://localhost:{port}" target="_blank" class="agent-badge {'online' if online else 'offline'}" title="Open {name} Dashboard">
            <span class="agent-dot" style="background:{color}"></span>
            <span class="agent-name">{name}</span>
        </a>'''
    
    # Market overview cards
    market_cards = ""
    for symbol, data in market_data.items():
        price = data.get("price", 0)
        change = data.get("change_pct", 0)
        confluence = confluence_data.get(symbol, {}).get("score", 0)
        direction = confluence_data.get(symbol, {}).get("direction", "neutral")
        spread = data.get("spread", 0)
        
        change_color = "#22c55e" if change >= 0 else "#ef4444"
        conf_color = "#22c55e" if confluence >= 75 else "#f59e0b" if confluence >= 60 else "#666"
        dir_icon = "↑" if direction == "bullish" else "↓" if direction == "bearish" else "→"
        dir_color = "#22c55e" if direction == "bullish" else "#ef4444" if direction == "bearish" else "#888"
        
        market_cards += f'''<div class="market-card" onclick="showPairAnalysis('{symbol}')" style="cursor:pointer">
            <div class="market-header">
                <span class="market-symbol">{symbol}</span>
                <span class="market-dir" style="color:{dir_color}">{dir_icon}</span>
            </div>
            <div class="market-price">{price:.5f}</div>
            <div class="market-change" style="color:{change_color}">{'+' if change >= 0 else ''}{change:.2f}%</div>
            <div class="market-confluence">
                <div class="conf-bar" style="width:{confluence}%;background:{conf_color}"></div>
                <span class="conf-value">{confluence}</span>
            </div>
            <div class="market-spread">Spread: {spread:.1f}</div>
        </div>'''
    
    # Confluence heatmap
    heatmap_cells = ""
    for symbol, data in confluence_data.items():
        score = data.get("score", 0)
        direction = data.get("direction", "neutral")
        
        if score >= 75:
            cell_color = "#22c55e"
            cell_bg = "rgba(34, 197, 94, 0.2)"
        elif score >= 60:
            cell_color = "#f59e0b"
            cell_bg = "rgba(245, 158, 11, 0.15)"
        else:
            cell_color = "#666"
            cell_bg = "rgba(100, 100, 100, 0.1)"
        
        dir_symbol = "▲" if direction == "bullish" else "▼" if direction == "bearish" else "◆"
        
        heatmap_cells += f'''<div class="heatmap-cell" onclick="showPairAnalysis('{symbol}')" style="background:{cell_bg};border-color:{cell_color};cursor:pointer">
            <div class="hm-symbol">{symbol}</div>
            <div class="hm-score" style="color:{cell_color}">{score}</div>
            <div class="hm-dir">{dir_symbol}</div>
        </div>'''
    
    # Recent decisions
    decision_rows = ""
    recent = decisions_log[-10:] if decisions_log else []
    for d in reversed(recent):
        dec = d.get("decision", "?")
        if dec in ["BUY", "SELL"]:
            dec_class = "decision-trade"
        elif dec == "WATCHLIST":
            dec_class = "decision-watch"
        else:
            dec_class = "decision-reject"
        
        decision_rows += f'''<tr>
            <td class="td-time">{d.get("timestamp", "?")[11:16]}</td>
            <td class="td-symbol">{d.get("symbol", "?")}</td>
            <td class="td-dir {'dir-long' if d.get('direction') == 'long' else 'dir-short'}">{d.get("direction", "?").upper()}</td>
            <td class="{dec_class}">{dec}</td>
            <td class="td-score">{d.get("confluence_score", 0)}</td>
            <td class="td-reason">{d.get("reason", "")[:40]}</td>
        </tr>'''
    
    if not decision_rows:
        decision_rows = '<tr><td colspan="6" class="empty-row">No decisions yet</td></tr>'
    
    # Watchlist items
    watchlist_rows = ""
    for key, item in watchlist.items():
        score = item.get("score", 0)
        score_class = "score-high" if score >= 70 else "score-mid" if score >= 60 else "score-low"
        
        watchlist_rows += f'''<tr>
            <td class="td-symbol">{item.get("symbol", "?")}</td>
            <td class="td-dir {'dir-long' if item.get('direction') == 'long' else 'dir-short'}">{item.get("direction", "?").upper()}</td>
            <td class="{score_class}">{score}</td>
            <td class="td-expires">{item.get("expires_at", "?")[11:16]}</td>
            <td class="td-trigger">{item.get("trigger", "-")}</td>
        </tr>'''
    
    if not watchlist_rows:
        watchlist_rows = '<tr><td colspan="5" class="empty-row">Watchlist empty</td></tr>'
    
    # Open positions
    position_rows = ""
    for pos in positions:
        pnl = pos.get("pnl", 0)
        pnl_class = "pnl-positive" if pnl >= 0 else "pnl-negative"
        
        position_rows += f'''<tr>
            <td class="td-symbol">{pos.get("symbol", "?")}</td>
            <td class="td-dir {'dir-long' if pos.get('side') == 'buy' else 'dir-short'}">{pos.get("side", "?").upper()}</td>
            <td>{pos.get("lots", 0)}</td>
            <td>{pos.get("entry", 0):.5f}</td>
            <td>{pos.get("sl", 0):.5f}</td>
            <td>{pos.get("tp", 0):.5f}</td>
            <td class="{pnl_class}">${pnl:+.2f}</td>
        </tr>'''
    
    if not position_rows:
        position_rows = '<tr><td colspan="7" class="empty-row">No open positions</td></tr>'
    
    # Upcoming events
    event_rows = ""
    for ev in events[:6]:
        impact = ev.get("impact", "low")
        impact_class = f"impact-{impact.lower()}"
        
        event_rows += f'''<div class="event-item {impact_class}">
            <div class="event-time">{ev.get("time", "?")}</div>
            <div class="event-cur">{ev.get("currency", "?")}</div>
            <div class="event-name">{ev.get("event", "?")[:30]}</div>
            <div class="event-impact">{impact.upper()}</div>
        </div>'''
    
    if not event_rows:
        event_rows = '<div class="event-item">No upcoming events</div>'
    
    # Account stats
    balance = account_data.get("balance", 0)
    equity = account_data.get("equity", 0)
    daily_pnl = account_data.get("daily_pnl", 0)
    daily_pnl_pct = account_data.get("daily_pnl_pct", 0)
    
    # Guardian risk status
    g_mode = guardian_status.get("mode", "NORMAL")
    g_drawdown = guardian_status.get("drawdown", 0)
    g_positions = guardian_status.get("open_positions", 0)
    g_max = guardian_status.get("max_positions", 5)
    mode_color = "#22c55e" if g_mode == "NORMAL" else "#f59e0b" if g_mode == "DEFENSIVE" else "#ef4444"
    
    return f'''<!DOCTYPE html>
<html><head>
    <title>🎯 Nexus Trading Platform</title>
    <!-- No auto-refresh - using JavaScript for partial updates -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        :root {{
            --bg-primary: #0a0a0f;
            --bg-secondary: #12121a;
            --bg-card: #1a1a24;
            --bg-hover: #222230;
            --accent: #f97316;
            --accent-dim: rgba(249, 115, 22, 0.15);
            --success: #22c55e;
            --warning: #f59e0b;
            --danger: #ef4444;
            --text-primary: #e0e0e0;
            --text-secondary: #888;
            --text-muted: #555;
            --border: #2a2a35;
        }}
        
        body {{
            font-family: 'Inter', -apple-system, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
        }}
        
        /* Header */
        .header {{
            background: linear-gradient(180deg, var(--bg-secondary) 0%, var(--bg-primary) 100%);
            padding: 15px 25px;
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        
        .header-left {{
            display: flex;
            align-items: center;
            gap: 20px;
        }}
        
        .logo {{
            font-size: 24px;
            font-weight: 700;
            color: var(--accent);
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        
        .session-badge {{
            background: var(--accent-dim);
            color: var(--accent);
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
        }}
        
        .header-right {{
            display: flex;
            align-items: center;
            gap: 25px;
        }}
        
        .how-btn {{
            background: linear-gradient(135deg, rgba(139, 92, 246, 0.2), rgba(59, 130, 246, 0.2));
            border: 1px solid rgba(139, 92, 246, 0.4);
            padding: 8px 16px;
            border-radius: 8px;
            color: #a78bfa;
            text-decoration: none;
            font-size: 13px;
            font-weight: 500;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        
        .how-btn:hover {{
            background: linear-gradient(135deg, rgba(139, 92, 246, 0.3), rgba(59, 130, 246, 0.3));
            border-color: rgba(139, 92, 246, 0.6);
            transform: translateY(-1px);
        }}
        
        .account-stat {{
            text-align: right;
        }}
        
        .account-label {{
            font-size: 10px;
            color: var(--text-secondary);
            text-transform: uppercase;
        }}
        
        .account-value {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 16px;
            font-weight: 600;
        }}
        
        .account-value.positive {{ color: var(--success); }}
        .account-value.negative {{ color: var(--danger); }}
        
        /* Agents strip */
        .agents-strip {{
            background: var(--bg-secondary);
            padding: 10px 25px;
            display: flex;
            gap: 8px;
            border-bottom: 1px solid var(--border);
            overflow-x: auto;
        }}
        
        .agent-badge {{
            display: flex;
            align-items: center;
            gap: 6px;
            padding: 6px 12px;
            background: var(--bg-card);
            border-radius: 6px;
            font-size: 11px;
            white-space: nowrap;
            text-decoration: none;
            color: inherit;
            transition: all 0.2s;
        }}
        
        .agent-badge:hover {{
            background: var(--bg-hover);
            transform: translateY(-1px);
        }}
        
        .agent-badge.online {{ border: 1px solid rgba(34, 197, 94, 0.3); }}
        .agent-badge.offline {{ border: 1px solid rgba(239, 68, 68, 0.3); opacity: 0.6; }}
        
        .agent-dot {{
            width: 6px;
            height: 6px;
            border-radius: 50%;
        }}
        
        /* Main layout */
        .main {{
            display: grid;
            grid-template-columns: 1fr 380px;
            gap: 20px;
            padding: 20px 25px;
            max-width: 1800px;
            margin: 0 auto;
        }}
        
        .left-col {{
            display: flex;
            flex-direction: column;
            gap: 20px;
        }}
        
        .right-col {{
            display: flex;
            flex-direction: column;
            gap: 20px;
        }}
        
        /* Cards */
        .card {{
            background: var(--bg-card);
            border-radius: 12px;
            border: 1px solid var(--border);
            overflow: hidden;
        }}
        
        .card-header {{
            padding: 15px 20px;
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        
        .card-title {{
            font-size: 13px;
            font-weight: 600;
            color: var(--text-primary);
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        
        .card-title span {{
            color: var(--accent);
        }}
        
        .card-badge {{
            font-size: 11px;
            padding: 4px 10px;
            border-radius: 12px;
            background: var(--accent-dim);
            color: var(--accent);
        }}
        
        .card-body {{
            padding: 15px 20px;
        }}
        
        /* Market grid */
        .market-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
        }}
        
        .market-card {{
            background: var(--bg-secondary);
            border-radius: 10px;
            padding: 14px;
            border: 1px solid var(--border);
            transition: all 0.2s;
        }}
        
        .market-card:hover {{
            border-color: var(--accent);
            transform: translateY(-2px);
        }}
        
        .market-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }}
        
        .market-symbol {{
            font-weight: 600;
            font-size: 14px;
        }}
        
        .market-dir {{
            font-size: 18px;
            font-weight: bold;
        }}
        
        .market-price {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 18px;
            font-weight: 600;
            color: var(--text-primary);
        }}
        
        .market-change {{
            font-size: 12px;
            margin: 4px 0;
        }}
        
        .market-confluence {{
            height: 4px;
            background: var(--bg-primary);
            border-radius: 2px;
            margin: 8px 0;
            position: relative;
        }}
        
        .conf-bar {{
            height: 100%;
            border-radius: 2px;
            transition: width 0.3s;
        }}
        
        .conf-value {{
            position: absolute;
            right: 0;
            top: -16px;
            font-size: 10px;
            font-weight: 600;
            color: var(--text-secondary);
        }}
        
        .market-spread {{
            font-size: 10px;
            color: var(--text-muted);
        }}
        
        /* Heatmap */
        .heatmap-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
        }}
        
        .heatmap-cell {{
            padding: 12px;
            border-radius: 8px;
            border: 1px solid;
            text-align: center;
            transition: all 0.2s;
        }}
        
        .heatmap-cell:hover {{
            transform: scale(1.02);
        }}
        
        .hm-symbol {{
            font-size: 12px;
            font-weight: 600;
            margin-bottom: 4px;
        }}
        
        .hm-score {{
            font-size: 24px;
            font-weight: 700;
        }}
        
        .hm-dir {{
            font-size: 14px;
            opacity: 0.7;
        }}
        
        /* Tables */
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
        }}
        
        th {{
            text-align: left;
            padding: 10px 12px;
            background: var(--bg-secondary);
            color: var(--text-secondary);
            font-weight: 500;
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        td {{
            padding: 10px 12px;
            border-bottom: 1px solid var(--border);
        }}
        
        tr:hover td {{
            background: var(--bg-hover);
        }}
        
        .empty-row {{
            text-align: center;
            color: var(--text-muted);
            padding: 30px;
        }}
        
        .td-symbol {{ font-weight: 600; }}
        .td-time {{ color: var(--text-secondary); font-family: 'JetBrains Mono', monospace; }}
        .td-score {{ font-family: 'JetBrains Mono', monospace; }}
        .td-reason {{ color: var(--text-secondary); font-size: 11px; }}
        .td-expires {{ color: var(--text-secondary); font-family: 'JetBrains Mono', monospace; }}
        
        .dir-long {{ color: var(--success); font-weight: 600; }}
        .dir-short {{ color: var(--danger); font-weight: 600; }}
        
        .decision-trade {{ color: var(--success); font-weight: 700; }}
        .decision-watch {{ color: var(--warning); font-weight: 600; }}
        .decision-reject {{ color: var(--text-muted); }}
        
        .score-high {{ color: var(--success); font-weight: 600; }}
        .score-mid {{ color: var(--warning); font-weight: 600; }}
        .score-low {{ color: var(--text-muted); }}
        
        .pnl-positive {{ color: var(--success); font-weight: 600; }}
        .pnl-negative {{ color: var(--danger); font-weight: 600; }}
        
        /* Events */
        .events-list {{
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}
        
        .event-item {{
            display: grid;
            grid-template-columns: 50px 35px 1fr 50px;
            gap: 10px;
            padding: 10px 12px;
            background: var(--bg-secondary);
            border-radius: 8px;
            font-size: 11px;
            align-items: center;
            border-left: 3px solid transparent;
        }}
        
        .event-item.impact-high {{ border-left-color: var(--danger); }}
        .event-item.impact-medium {{ border-left-color: var(--warning); }}
        .event-item.impact-low {{ border-left-color: var(--text-muted); }}
        
        .event-time {{ font-family: 'JetBrains Mono', monospace; color: var(--text-secondary); }}
        .event-cur {{ font-weight: 600; }}
        .event-name {{ color: var(--text-primary); }}
        .event-impact {{ font-size: 9px; font-weight: 600; text-align: right; }}
        
        .impact-high .event-impact {{ color: var(--danger); }}
        .impact-medium .event-impact {{ color: var(--warning); }}
        
        /* Risk panel */
        .risk-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 12px;
        }}
        
        .risk-stat {{
            background: var(--bg-secondary);
            border-radius: 8px;
            padding: 14px;
            text-align: center;
        }}
        
        .risk-value {{
            font-size: 22px;
            font-weight: 700;
            margin-bottom: 4px;
        }}
        
        .risk-label {{
            font-size: 10px;
            color: var(--text-secondary);
            text-transform: uppercase;
        }}
        
        .risk-mode {{
            grid-column: span 2;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            padding: 12px;
            border-radius: 8px;
        }}
        
        .risk-mode.normal {{ background: rgba(34, 197, 94, 0.15); color: var(--success); }}
        .risk-mode.defensive {{ background: rgba(245, 158, 11, 0.15); color: var(--warning); }}
        .risk-mode.halted {{ background: rgba(239, 68, 68, 0.15); color: var(--danger); }}
        
        /* Chat */
        .chat-messages {{
            height: 120px;
            overflow-y: auto;
            background: var(--bg-secondary);
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 12px;
        }}
        
        .chat-msg {{
            margin: 6px 0;
            padding: 8px 12px;
            border-radius: 8px;
            font-size: 12px;
            line-height: 1.5;
        }}
        
        .chat-msg.user {{ background: var(--bg-card); }}
        .chat-msg.bot {{ background: var(--accent-dim); border-left: 3px solid var(--accent); }}
        
        .chat-input {{
            display: flex;
            gap: 10px;
        }}
        
        .chat-input input {{
            flex: 1;
            padding: 12px 16px;
            border-radius: 8px;
            border: 1px solid var(--border);
            background: var(--bg-secondary);
            color: var(--text-primary);
            font-size: 13px;
        }}
        
        .chat-input input:focus {{
            outline: none;
            border-color: var(--accent);
        }}
        
        .chat-input button {{
            padding: 12px 24px;
            background: var(--accent);
            color: white;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }}
        
        .chat-input button:hover {{
            background: #ea580c;
        }}
        
        /* Animations */
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.5; }}
        }}
        
        .live-dot {{
            width: 8px;
            height: 8px;
            background: var(--success);
            border-radius: 50%;
            animation: pulse 2s infinite;
        }}
        
        /* Scrollbar */
        ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
        ::-webkit-scrollbar-track {{ background: var(--bg-primary); }}
        ::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 3px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: var(--text-muted); }}
        
        /* Modal */
        .modal-overlay {{
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.8);
            z-index: 1000;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }}
        
        .modal-overlay.active {{
            display: flex;
        }}
        
        .modal {{
            background: var(--bg-card);
            border-radius: 16px;
            max-width: 900px;
            width: 100%;
            max-height: 90vh;
            overflow-y: auto;
            border: 1px solid var(--border);
        }}
        
        .modal-header {{
            padding: 20px 25px;
            border-bottom: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: sticky;
            top: 0;
            background: var(--bg-card);
            z-index: 10;
        }}
        
        .modal-title {{
            font-size: 20px;
            font-weight: 700;
            color: var(--accent);
        }}
        
        .modal-close {{
            background: none;
            border: none;
            color: var(--text-secondary);
            font-size: 24px;
            cursor: pointer;
            padding: 5px 10px;
        }}
        
        .modal-close:hover {{
            color: var(--text-primary);
        }}
        
        .modal-body {{
            padding: 25px;
        }}
        
        .analysis-section {{
            margin-bottom: 20px;
        }}
        
        .analysis-section h3 {{
            font-size: 14px;
            color: var(--accent);
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        
        .agent-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 12px;
        }}
        
        .agent-analysis {{
            background: var(--bg-secondary);
            border-radius: 10px;
            padding: 14px;
            border-left: 3px solid var(--accent);
        }}
        
        .agent-analysis h4 {{
            font-size: 13px;
            font-weight: 600;
            margin-bottom: 8px;
            color: var(--text-primary);
        }}
        
        .agent-analysis p {{
            font-size: 12px;
            color: var(--text-secondary);
            line-height: 1.5;
        }}
        
        .confluence-box {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 15px;
            margin-bottom: 20px;
        }}
        
        .conf-card {{
            background: var(--bg-secondary);
            border-radius: 10px;
            padding: 20px;
            text-align: center;
        }}
        
        .conf-card.long {{ border: 2px solid var(--success); }}
        .conf-card.short {{ border: 2px solid var(--danger); }}
        
        .conf-card .direction {{
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 8px;
        }}
        
        .conf-card.long .direction {{ color: var(--success); }}
        .conf-card.short .direction {{ color: var(--danger); }}
        
        .conf-card .score {{
            font-size: 36px;
            font-weight: 700;
        }}
        
        .conf-card.long .score {{ color: var(--success); }}
        .conf-card.short .score {{ color: var(--danger); }}
        
        .nexus-commentary {{
            background: linear-gradient(135deg, rgba(249, 115, 22, 0.1) 0%, rgba(249, 115, 22, 0.05) 100%);
            border: 1px solid rgba(249, 115, 22, 0.3);
            border-radius: 12px;
            padding: 20px;
        }}
        
        .nexus-commentary h3 {{
            color: var(--accent);
            margin-bottom: 12px;
        }}
        
        .nexus-commentary p {{
            font-size: 14px;
            line-height: 1.7;
            color: var(--text-primary);
        }}
        
        .loading {{
            text-align: center;
            padding: 40px;
            color: var(--text-secondary);
        }}
        
        .loading::after {{
            content: '';
            animation: dots 1.5s infinite;
        }}
        
        @keyframes dots {{
            0%, 20% {{ content: '.'; }}
            40% {{ content: '..'; }}
            60%, 100% {{ content: '...'; }}
        }}
    </style>
</head>
<body>
    <!-- Header -->
    <div class="header">
        <div class="header-left">
            <div class="logo">🎯 Nexus</div>
            <div class="session-badge">📍 {session_info}</div>
            <div class="live-dot"></div>
        </div>
        <div class="header-right">
            <a href="/docs/how-i-work" target="_blank" class="how-btn" title="System Documentation">📖 How I Work</a>
            <div class="account-stat">
                <div class="account-label">Balance</div>
                <div class="account-value">${balance:,.2f}</div>
            </div>
            <div class="account-stat">
                <div class="account-label">Equity</div>
                <div class="account-value">${equity:,.2f}</div>
            </div>
            <div class="account-stat">
                <div class="account-label">Today</div>
                <div class="account-value {'positive' if daily_pnl >= 0 else 'negative'}">{'+' if daily_pnl >= 0 else ''}${daily_pnl:.2f} ({daily_pnl_pct:+.2f}%)</div>
            </div>
        </div>
    </div>
    
    <!-- Agents strip -->
    <div class="agents-strip">
        {agent_badges}
    </div>
    
    <!-- Main content -->
    <div class="main">
        <!-- Left column -->
        <div class="left-col">
            <!-- Market overview -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title"><span>📊</span> Market Overview</div>
                    <div class="card-badge">9 Pairs</div>
                </div>
                <div class="card-body">
                    <div class="market-grid">
                        {market_cards}
                    </div>
                </div>
            </div>
            
            <!-- Technical Pulse heatmap -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title"><span>📡</span> Technical Pulse</div>
                    <div class="card-badge">Quick Read</div>
                </div>
                <div class="card-body">
                    <div class="heatmap-grid">
                        {heatmap_cells}
                    </div>
                </div>
            </div>
            
            <!-- Recent decisions -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title"><span>📋</span> Recent Decisions</div>
                    <div class="card-badge">{len(decisions_log)} Total</div>
                </div>
                <div class="card-body" style="padding:0">
                    <table>
                        <thead>
                            <tr><th>Time</th><th>Symbol</th><th>Dir</th><th>Decision</th><th>Score</th><th>Reason</th></tr>
                        </thead>
                        <tbody>
                            {decision_rows}
                        </tbody>
                    </table>
                </div>
            </div>
            
            <!-- Open positions -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title"><span>💼</span> Open Positions</div>
                    <div class="card-badge">{len(positions)} Active</div>
                </div>
                <div class="card-body" style="padding:0">
                    <table>
                        <thead>
                            <tr><th>Symbol</th><th>Side</th><th>Lots</th><th>Entry</th><th>SL</th><th>TP</th><th>P/L</th></tr>
                        </thead>
                        <tbody>
                            {position_rows}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        
        <!-- Right column -->
        <div class="right-col">
            <!-- Risk status -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title"><span>🛡️</span> Risk Status</div>
                </div>
                <div class="card-body">
                    <div class="risk-grid">
                        <div class="risk-mode {g_mode.lower()}">
                            <span style="font-size:20px">{'✅' if g_mode == 'NORMAL' else '⚠️' if g_mode == 'DEFENSIVE' else '🛑'}</span>
                            <span style="font-weight:700">{g_mode} MODE</span>
                        </div>
                        <div class="risk-stat">
                            <div class="risk-value" style="color: {'var(--success)' if g_drawdown < 2 else 'var(--warning)' if g_drawdown < 5 else 'var(--danger)'}">{g_drawdown:.1f}%</div>
                            <div class="risk-label">Drawdown</div>
                        </div>
                        <div class="risk-stat">
                            <div class="risk-value">{g_positions}/{g_max}</div>
                            <div class="risk-label">Positions</div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Watchlist -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title"><span>👁️</span> Watchlist</div>
                    <div class="card-badge">{len(watchlist)} Items</div>
                </div>
                <div class="card-body" style="padding:0">
                    <table>
                        <thead>
                            <tr><th>Symbol</th><th>Dir</th><th>Score</th><th>Expires</th><th>Trigger</th></tr>
                        </thead>
                        <tbody>
                            {watchlist_rows}
                        </tbody>
                    </table>
                </div>
            </div>
            
            <!-- Upcoming events -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title"><span>📅</span> Upcoming Events</div>
                    <div class="card-badge">Next 24h</div>
                </div>
                <div class="card-body">
                    <div class="events-list">
                        {event_rows}
                    </div>
                </div>
            </div>
            
            <!-- Ask Nexus -->
            <div class="card" style="flex:1">
                <div class="card-header">
                    <div class="card-title"><span>💬</span> Ask Nexus</div>
                    <button onclick="clearChat()" style="background:transparent;border:1px solid var(--border);color:var(--text-secondary);padding:4px 10px;border-radius:4px;font-size:10px;cursor:pointer">Clear</button>
                </div>
                <div class="card-body">
                    <div class="chat-messages" id="messages"></div>
                    <div class="chat-input">
                        <input type="text" id="input" placeholder="Ask about confluence, decisions..." onkeypress="if(event.key==='Enter')sendMessage()">
                        <button onclick="sendMessage()">Send</button>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <!-- Analysis Modal -->
    <div class="modal-overlay" id="analysisModal" onclick="if(event.target===this)closeModal()">
        <div class="modal">
            <div class="modal-header">
                <div class="modal-title" id="modalTitle">📊 Pair Analysis</div>
                <button class="modal-close" onclick="closeModal()">✕</button>
            </div>
            <div class="modal-body" id="modalBody">
                <div class="loading">Loading analysis</div>
            </div>
        </div>
    </div>
    
    <script>
        // Pair Analysis Modal
        async function showPairAnalysis(symbol) {{
            const modal = document.getElementById('analysisModal');
            const title = document.getElementById('modalTitle');
            const body = document.getElementById('modalBody');
            
            title.textContent = `📊 ${{symbol}} Analysis`;
            body.innerHTML = '<div class="loading">Fetching analysis from all agents</div>';
            modal.classList.add('active');
            
            try {{
                const response = await fetch(`/api/pair-analysis/${{symbol}}`);
                const data = await response.json();
                
                // Build agent summaries
                let agentHTML = '';
                for (const [key, agent] of Object.entries(data.agents || {{}})) {{
                    // Handle multi-line summaries (like Tactician)
                    const summaryHTML = agent.summary.replace(/\\n/g, '<br>');
                    agentHTML += `
                        <div class="agent-analysis">
                            <h4>${{agent.name}}</h4>
                            <p>${{summaryHTML}}</p>
                        </div>`;
                }}
                
                // Build confluence scores
                const longScore = data.confluence?.long?.score || 0;
                const shortScore = data.confluence?.short?.score || 0;
                
                body.innerHTML = `
                    <div class="analysis-section">
                        <h3>🎯 Confluence Scores</h3>
                        <div class="confluence-box">
                            <div class="conf-card long">
                                <div class="direction">Long</div>
                                <div class="score">${{longScore}}</div>
                            </div>
                            <div class="conf-card short">
                                <div class="direction">Short</div>
                                <div class="score">${{shortScore}}</div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="analysis-section">
                        <h3>🤖 Agent Reports</h3>
                        <div class="agent-grid">
                            ${{agentHTML || '<p style="color:var(--text-muted)">No agent data available</p>'}}
                        </div>
                    </div>
                    
                    <div class="nexus-commentary">
                        <h3>🎯 Nexus Commentary</h3>
                        <p>${{data.nexus_commentary?.replace(/\\n/g, '<br>') || 'No commentary available'}}</p>
                    </div>
                `;
            }} catch (e) {{
                body.innerHTML = `<div style="color:var(--danger);padding:20px">Error loading analysis: ${{e.message}}</div>`;
            }}
        }}
        
        function closeModal() {{
            document.getElementById('analysisModal').classList.remove('active');
        }}
        
        // Close modal on Escape key
        document.addEventListener('keydown', (e) => {{
            if (e.key === 'Escape') closeModal();
        }});
        
        // Auto-refresh management - pause when modal is open
        let refreshInterval = null;
        let modalOpen = false;
        
        function startAutoRefresh() {{
            if (refreshInterval) clearInterval(refreshInterval);
            refreshInterval = setInterval(() => {{
                if (!modalOpen) {{
                    location.reload();
                }}
            }}, 15000);
        }}
        
        // Override showPairAnalysis to track modal state
        const originalShowPairAnalysis = showPairAnalysis;
        showPairAnalysis = async function(symbol) {{
            modalOpen = true;
            await originalShowPairAnalysis(symbol);
        }};
        
        // Override closeModal to track modal state
        const originalCloseModal = closeModal;
        closeModal = function() {{
            modalOpen = false;
            originalCloseModal();
        }};
        
        // Start auto-refresh on page load
        startAutoRefresh();
        
        // Load chat history from localStorage
        function loadChatHistory() {{
            const messages = document.getElementById('messages');
            const history = localStorage.getItem('nexus_chat_history');
            if (history) {{
                messages.innerHTML = history;
                messages.scrollTop = messages.scrollHeight;
            }}
        }}
        
        // Save chat history to localStorage
        function saveChatHistory() {{
            const messages = document.getElementById('messages');
            localStorage.setItem('nexus_chat_history', messages.innerHTML);
        }}
        
        async function sendMessage() {{
            const input = document.getElementById('input');
            const messages = document.getElementById('messages');
            const text = input.value.trim();
            if (!text) return;
            messages.innerHTML += `<div class="chat-msg user">${{text}}</div>`;
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
                messages.innerHTML += `<div class="chat-msg bot">${{data.response.replace(/\\n/g, '<br>')}}</div>`;
            }} catch (e) {{
                messages.innerHTML += `<div class="chat-msg bot" style="color:var(--danger)">Error: ${{e.message}}</div>`;
            }}
            messages.scrollTop = messages.scrollHeight;
            saveChatHistory();
        }}
        
        // Clear chat history
        function clearChat() {{
            const messages = document.getElementById('messages');
            messages.innerHTML = '';
            localStorage.removeItem('nexus_chat_history');
        }}
        
        // Partial refresh - reload page data without losing chat
        async function refreshData() {{
            try {{
                const response = await fetch('/api/dashboard-data');
                if (response.ok) {{
                    // For now, just reload the page but chat is preserved in localStorage
                    location.reload();
                }}
            }} catch (e) {{
                console.log('Refresh failed:', e);
            }}
        }}
        
        // Load chat on page load
        document.addEventListener('DOMContentLoaded', loadChatHistory);
    </script>
</body>
</html>'''
