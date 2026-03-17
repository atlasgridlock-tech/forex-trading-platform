"""
Chronicle Dashboard - Trade Journal
Rich HTML dashboard for trade journaling with proper details
"""

def generate_dashboard(trades: list, stats: dict, chat_history: list = None) -> str:
    """Generate the Chronicle dashboard HTML."""
    
    # Process trades for display
    trades_html = ""
    for trade in sorted(trades, key=lambda x: x.get("created_at", ""), reverse=True)[:20]:
        trade_id = trade.get("trade_id", "?")
        symbol = trade.get("symbol", "?")
        direction = trade.get("direction", "?").upper()
        status = trade.get("status", "unknown")
        entry = trade.get("fill_price", trade.get("entry_price", 0))
        sl = trade.get("stop_loss", 0)
        tp = trade.get("take_profit", 0)
        exit_price = trade.get("exit_price", 0)
        result_r = trade.get("result_r", 0)
        lot_size = trade.get("lot_size", 0)
        
        # Calculate risk in pips
        risk_pips = abs(entry - sl) * 10000 if sl and entry else 0
        
        # Calculate R:R ratio
        reward_pips = abs(tp - entry) * 10000 if tp and entry else 0
        rr_ratio = reward_pips / risk_pips if risk_pips else 0
        
        # Status badge color
        status_colors = {
            "executed": "#3b82f6",
            "closed": "#22c55e" if result_r > 0 else "#ef4444",
            "pending": "#f59e0b",
            "proposed": "#888",
        }
        status_color = status_colors.get(status, "#888")
        
        # Direction color
        dir_color = "#22c55e" if direction == "LONG" else "#ef4444" if direction == "SHORT" else "#888"
        
        # Get stored reasoning/thesis
        thesis = trade.get("thesis", {})
        why_here = thesis.get("why_here", trade.get("why_here", ""))
        why_now = thesis.get("why_now", trade.get("why_now", ""))
        why_direction = thesis.get("why_direction", trade.get("why_direction", ""))
        
        # Get confluence scores at entry
        confluence = trade.get("confluence_at_entry", {})
        conf_score = confluence.get("total", 0)
        
        # Lessons learned
        lessons = trade.get("lessons", [])
        review = trade.get("post_trade_review", "")
        
        trades_html += f'''
        <div class="trade-card" onclick="toggleDetails('{trade_id}')">
            <div class="trade-header">
                <div class="trade-symbol">
                    <span class="direction" style="color:{dir_color}">{direction}</span>
                    <span class="symbol">{symbol}</span>
                </div>
                <div class="trade-meta">
                    <span class="status" style="background:{status_color}">{status.upper()}</span>
                    <span class="result" style="color:{'#22c55e' if result_r > 0 else '#ef4444' if result_r < 0 else '#888'}">{result_r:+.2f}R</span>
                </div>
            </div>
            
            <div class="trade-details" id="details-{trade_id}">
                <div class="detail-grid">
                    <div class="detail-section">
                        <h4>📍 Entry Details</h4>
                        <div class="detail-row"><span>Entry:</span><span>{entry:.5f}</span></div>
                        <div class="detail-row"><span>Stop Loss:</span><span>{sl:.5f}</span></div>
                        <div class="detail-row"><span>Take Profit:</span><span>{f'{tp:.5f}' if tp else 'Managed'}</span></div>
                        <div class="detail-row"><span>Risk:</span><span>{risk_pips:.1f} pips</span></div>
                        <div class="detail-row"><span>R:R:</span><span>1:{rr_ratio:.1f}</span></div>
                        <div class="detail-row"><span>Size:</span><span>{lot_size} lots</span></div>
                    </div>
                    
                    <div class="detail-section">
                        <h4>🎯 Confluence @ Entry</h4>
                        <div class="confluence-bar">
                            <div class="conf-fill" style="width:{min(conf_score, 100)}%"></div>
                            <span class="conf-score">{conf_score}/100</span>
                        </div>
                        <div class="conf-breakdown">
                            <span>Tech: {confluence.get('technical', '?')}</span>
                            <span>Struct: {confluence.get('structure', '?')}</span>
                            <span>Macro: {confluence.get('macro', '?')}</span>
                        </div>
                    </div>
                </div>
                
                <div class="thesis-section">
                    <h4>📝 Trade Thesis</h4>
                    <div class="thesis-item"><strong>Why Here:</strong> {why_here or 'Not recorded'}</div>
                    <div class="thesis-item"><strong>Why Now:</strong> {why_now or 'Not recorded'}</div>
                    <div class="thesis-item"><strong>Why {direction}:</strong> {why_direction or 'Not recorded'}</div>
                </div>
                
                {f"""
                <div class="review-section">
                    <h4>📖 Post-Trade Review</h4>
                    <div class="review-text">{review}</div>
                </div>
                """ if review else ""}
                
                {f"""
                <div class="lessons-section">
                    <h4>💡 Lessons Learned</h4>
                    <ul class="lessons-list">
                        {''.join(f'<li>{l}</li>' for l in lessons)}
                    </ul>
                </div>
                """ if lessons else ""}
                
                <div class="action-buttons">
                    <button onclick="addReview('{trade_id}')" class="btn-review">Add Review</button>
                    <button onclick="addLesson('{trade_id}')" class="btn-lesson">Add Lesson</button>
                </div>
            </div>
        </div>
        '''
    
    if not trades_html:
        trades_html = '''
        <div class="empty-state">
            <div class="empty-icon">📔</div>
            <p>No trades recorded yet</p>
            <p class="empty-hint">Trades will appear here when executed</p>
        </div>
        '''
    
    # Stats
    win_rate = stats.get("win_rate", 0)
    total_r = stats.get("total_r", 0)
    avg_r = stats.get("avg_r", 0)
    total_trades = stats.get("total_trades", len(trades))
    
    return f'''<!DOCTYPE html>
<html><head>
    <title>📔 Chronicle - Trade Journal</title>
    <meta http-equiv="refresh" content="30">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #0a0a0f; color: #e0e0e0; padding: 20px; line-height: 1.5; }}
        
        .header {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 25px; padding-bottom: 15px; border-bottom: 1px solid #333; }}
        .header h1 {{ color: #f59e0b; font-size: 24px; }}
        .header-sub {{ color: #888; font-size: 13px; }}
        
        .stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 25px; }}
        .stat {{ background: linear-gradient(135deg, #1a1a24 0%, #12121a 100%); border-radius: 12px; padding: 20px; text-align: center; border: 1px solid #2a2a3a; }}
        .stat-value {{ font-size: 32px; font-weight: 700; }}
        .stat-value.positive {{ color: #22c55e; }}
        .stat-value.negative {{ color: #ef4444; }}
        .stat-value.neutral {{ color: #888; }}
        .stat-label {{ font-size: 11px; color: #666; margin-top: 5px; text-transform: uppercase; letter-spacing: 0.5px; }}
        
        .section-title {{ font-size: 14px; color: #888; margin-bottom: 15px; text-transform: uppercase; letter-spacing: 1px; display: flex; align-items: center; gap: 8px; }}
        
        .trade-card {{ background: #1a1a24; border-radius: 12px; margin-bottom: 12px; border: 1px solid #2a2a3a; overflow: hidden; transition: all 0.2s; cursor: pointer; }}
        .trade-card:hover {{ border-color: #f59e0b40; }}
        
        .trade-header {{ display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; }}
        .trade-symbol {{ display: flex; align-items: center; gap: 12px; }}
        .direction {{ font-weight: 600; font-size: 12px; padding: 4px 8px; border-radius: 4px; background: currentColor; background-opacity: 0.1; }}
        .symbol {{ font-size: 18px; font-weight: 600; }}
        .trade-meta {{ display: flex; align-items: center; gap: 15px; }}
        .status {{ font-size: 10px; padding: 4px 10px; border-radius: 20px; font-weight: 600; }}
        .result {{ font-size: 18px; font-weight: 700; }}
        
        .trade-details {{ display: none; padding: 0 20px 20px; border-top: 1px solid #2a2a3a; }}
        .trade-details.open {{ display: block; }}
        
        .detail-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 15px; }}
        .detail-section {{ background: #12121a; padding: 15px; border-radius: 8px; }}
        .detail-section h4 {{ font-size: 12px; color: #888; margin-bottom: 12px; }}
        .detail-row {{ display: flex; justify-content: space-between; font-size: 13px; padding: 4px 0; }}
        .detail-row span:first-child {{ color: #888; }}
        
        .confluence-bar {{ background: #0a0a0f; height: 24px; border-radius: 12px; position: relative; overflow: hidden; margin: 10px 0; }}
        .conf-fill {{ height: 100%; background: linear-gradient(90deg, #f59e0b, #22c55e); border-radius: 12px; }}
        .conf-score {{ position: absolute; right: 10px; top: 50%; transform: translateY(-50%); font-size: 12px; font-weight: 600; }}
        .conf-breakdown {{ display: flex; gap: 15px; font-size: 11px; color: #888; }}
        
        .thesis-section, .review-section, .lessons-section {{ margin-top: 15px; padding: 15px; background: #12121a; border-radius: 8px; }}
        .thesis-section h4, .review-section h4, .lessons-section h4 {{ font-size: 12px; color: #888; margin-bottom: 10px; }}
        .thesis-item {{ font-size: 13px; padding: 6px 0; border-bottom: 1px solid #1a1a24; }}
        .thesis-item:last-child {{ border: none; }}
        .review-text {{ font-size: 13px; color: #aaa; }}
        .lessons-list {{ padding-left: 20px; font-size: 13px; }}
        .lessons-list li {{ margin: 5px 0; }}
        
        .action-buttons {{ display: flex; gap: 10px; margin-top: 15px; }}
        .action-buttons button {{ padding: 8px 16px; border-radius: 6px; border: none; font-size: 12px; cursor: pointer; font-weight: 500; }}
        .btn-review {{ background: #3b82f620; color: #3b82f6; border: 1px solid #3b82f640; }}
        .btn-lesson {{ background: #f59e0b20; color: #f59e0b; border: 1px solid #f59e0b40; }}
        
        .chat-section {{ background: #1a1a24; border-radius: 12px; padding: 20px; margin-top: 20px; border: 1px solid #2a2a3a; }}
        .chat-section h2 {{ color: #f59e0b; font-size: 16px; margin-bottom: 15px; }}
        .chat-messages {{ height: 150px; overflow-y: auto; background: #0a0a0f; border-radius: 8px; padding: 12px; margin-bottom: 12px; }}
        .chat-input {{ display: flex; gap: 10px; }}
        .chat-input input {{ flex: 1; padding: 12px 15px; border-radius: 8px; border: 1px solid #333; background: #0a0a0f; color: #fff; font-size: 14px; }}
        .chat-input input:focus {{ outline: none; border-color: #f59e0b; }}
        .chat-input button {{ padding: 12px 24px; background: #f59e0b; color: #000; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; }}
        
        .empty-state {{ text-align: center; padding: 60px 20px; }}
        .empty-icon {{ font-size: 48px; margin-bottom: 15px; }}
        .empty-state p {{ color: #666; }}
        .empty-hint {{ font-size: 13px; margin-top: 5px; }}
        
        @media (max-width: 768px) {{
            .stats {{ grid-template-columns: repeat(2, 1fr); }}
            .detail-grid {{ grid-template-columns: 1fr; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📔 Chronicle</h1>
        <span class="header-sub">Trade Journal Agent v1.0</span>
    </div>
    
    <div class="stats">
        <div class="stat">
            <div class="stat-value neutral">{total_trades}</div>
            <div class="stat-label">Total Trades (30d)</div>
        </div>
        <div class="stat">
            <div class="stat-value {'positive' if win_rate >= 50 else 'negative' if win_rate > 0 else 'neutral'}">{win_rate:.1f}%</div>
            <div class="stat-label">Win Rate</div>
        </div>
        <div class="stat">
            <div class="stat-value {'positive' if total_r > 0 else 'negative' if total_r < 0 else 'neutral'}">{total_r:+.1f}R</div>
            <div class="stat-label">Total R</div>
        </div>
        <div class="stat">
            <div class="stat-value {'positive' if avg_r > 0 else 'negative' if avg_r < 0 else 'neutral'}">{avg_r:+.2f}</div>
            <div class="stat-label">Avg R/Trade</div>
        </div>
    </div>
    
    <div class="section-title">📊 Trade History</div>
    {trades_html}
    
    <div class="chat-section">
        <h2>💬 Ask Chronicle</h2>
        <div class="chat-messages" id="messages"></div>
        <div class="chat-input">
            <input type="text" id="input" placeholder="Ask about trades, patterns, lessons..." onkeypress="if(event.key==='Enter')sendMessage()">
            <button onclick="sendMessage()">Send</button>
        </div>
    </div>
    
    <script>
        function toggleDetails(tradeId) {{
            const details = document.getElementById('details-' + tradeId);
            details.classList.toggle('open');
        }}
        
        function addReview(tradeId) {{
            event.stopPropagation();
            const review = prompt('Enter your post-trade review:');
            if (review) {{
                fetch('/api/trade/review', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{trade_id: tradeId, review: review}})
                }}).then(() => location.reload());
            }}
        }}
        
        function addLesson(tradeId) {{
            event.stopPropagation();
            const lesson = prompt('What lesson did you learn from this trade?');
            if (lesson) {{
                fetch('/api/trade/lesson', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{trade_id: tradeId, lesson: lesson}})
                }}).then(() => location.reload());
            }}
        }}
        
        async function sendMessage() {{
            const input = document.getElementById('input');
            const msg = input.value.trim();
            if (!msg) return;
            input.value = '';
            
            const messages = document.getElementById('messages');
            messages.innerHTML += '<div style="background:#333;padding:8px;border-radius:6px;margin:8px 0;margin-left:20%">' + msg + '</div>';
            
            const response = await fetch('/chat', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{message: msg}})
            }});
            const data = await response.json();
            messages.innerHTML += '<div style="background:#4d3a1a;padding:8px;border-radius:6px;margin:8px 0;margin-right:20%">' + data.response + '</div>';
            messages.scrollTop = messages.scrollHeight;
        }}
    </script>
</body>
</html>'''
