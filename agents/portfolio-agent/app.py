"""
Portfolio Exposure Agent - Balancer
Currency-level exposure, theme analysis, concentration detection
"""

import os
import json
import asyncio
import httpx
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from dataclasses import dataclass

app = FastAPI(title="Balancer - Portfolio Exposure Agent", version="2.0")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://orchestrator-agent:8000")
AGENT_NAME = "Balancer"
WORKSPACE = Path("/app/workspace")

CURRENCIES = ["EUR", "GBP", "USD", "JPY", "CHF", "CAD", "AUD", "NZD"]


class ChatRequest(BaseModel):
    message: str


class PositionRequest(BaseModel):
    symbol: str
    direction: str  # "long" or "short"
    risk_pct: float
    entry_price: float
    current_price: Optional[float] = None
    realized_pnl: float = 0.0


# ═══════════════════════════════════════════════════════════════
# THEMATIC CLUSTERS
# ═══════════════════════════════════════════════════════════════

RISK_ON_CURRENCIES = ["AUD", "NZD"]  # Commodity/high-beta
RISK_OFF_CURRENCIES = ["JPY", "CHF", "USD"]  # Safe havens
CARRY_LONGS = ["AUD", "NZD"]  # Higher yield
CARRY_SHORTS = ["JPY", "CHF"]  # Lower yield

# Correlation matrix (simplified, 0-1 scale)
PAIR_CORRELATIONS = {
    ("EURUSD", "GBPUSD"): 0.85,
    ("EURUSD", "AUDUSD"): 0.70,
    ("GBPUSD", "AUDUSD"): 0.65,
    ("USDJPY", "USDCHF"): 0.60,
    ("AUDUSD", "NZDUSD"): 0.90,
    ("EURJPY", "GBPJPY"): 0.80,
    ("AUDJPY", "NZDJPY"): 0.88,
}


# Global state
positions: List[dict] = []
realized_pnl: Dict[str, float] = {}  # By symbol
theme_pnl: Dict[str, float] = {"risk_on": 0, "risk_off": 0, "dollar": 0, "carry": 0}


@dataclass
class ExposureLimits:
    max_single_currency: float = 1.5  # Max exposure to one currency
    max_theme_exposure: float = 1.0   # Max exposure to one theme
    concentration_warning: float = 1.0  # Warn above this
    concentration_danger: float = 1.5   # Block above this


limits = ExposureLimits()


def decompose_pair(symbol: str, direction: str, risk_pct: float) -> Dict[str, float]:
    """Decompose a pair trade into currency exposures."""
    base = symbol[:3]
    quote = symbol[3:]
    
    if direction.lower() == "long":
        # Long pair = long base, short quote
        return {base: risk_pct, quote: -risk_pct}
    else:
        # Short pair = short base, long quote
        return {base: -risk_pct, quote: risk_pct}


def calculate_currency_exposure() -> Dict[str, float]:
    """Calculate net exposure by currency."""
    exposure = {c: 0.0 for c in CURRENCIES}
    
    for pos in positions:
        decomposed = decompose_pair(pos["symbol"], pos["direction"], pos["risk_pct"])
        for curr, exp in decomposed.items():
            if curr in exposure:
                exposure[curr] += exp
    
    return exposure


def calculate_theme_exposure() -> Dict[str, float]:
    """Calculate exposure by economic theme."""
    themes = {
        "risk_on": 0.0,
        "risk_off": 0.0,
        "dollar": 0.0,
        "carry": 0.0,
    }
    
    currency_exp = calculate_currency_exposure()
    
    # Risk-On: Long AUD, NZD exposure
    for curr in RISK_ON_CURRENCIES:
        if currency_exp.get(curr, 0) > 0:
            themes["risk_on"] += currency_exp[curr]
    
    # Risk-Off: Long JPY, CHF, USD exposure
    for curr in RISK_OFF_CURRENCIES:
        if currency_exp.get(curr, 0) > 0:
            themes["risk_off"] += currency_exp[curr]
    
    # Dollar: All USD exposure (absolute)
    themes["dollar"] = abs(currency_exp.get("USD", 0))
    
    # Carry: Long high-yield vs short low-yield
    for curr in CARRY_LONGS:
        themes["carry"] += max(0, currency_exp.get(curr, 0))
    for curr in CARRY_SHORTS:
        themes["carry"] += max(0, -currency_exp.get(curr, 0))  # Short is positive carry
    
    return themes


def find_correlated_clusters() -> List[dict]:
    """Find clusters of correlated positions."""
    clusters = []
    
    # Group by currency
    currency_positions = {}
    for pos in positions:
        decomposed = decompose_pair(pos["symbol"], pos["direction"], pos["risk_pct"])
        for curr, exp in decomposed.items():
            if curr not in currency_positions:
                currency_positions[curr] = []
            currency_positions[curr].append({
                "symbol": pos["symbol"],
                "direction": pos["direction"],
                "exposure": exp,
            })
    
    # Find concentrated clusters
    for curr, pos_list in currency_positions.items():
        same_direction = [p for p in pos_list if p["exposure"] > 0]
        if len(same_direction) >= 2:
            total_exp = sum(p["exposure"] for p in same_direction)
            clusters.append({
                "type": "currency_concentration",
                "currency": curr,
                "direction": "long",
                "positions": [p["symbol"] for p in same_direction],
                "total_exposure": round(total_exp, 2),
                "count": len(same_direction),
            })
        
        same_direction = [p for p in pos_list if p["exposure"] < 0]
        if len(same_direction) >= 2:
            total_exp = sum(abs(p["exposure"]) for p in same_direction)
            clusters.append({
                "type": "currency_concentration",
                "currency": curr,
                "direction": "short",
                "positions": [p["symbol"] for p in same_direction],
                "total_exposure": round(total_exp, 2),
                "count": len(same_direction),
            })
    
    # Find pair correlations
    symbols = [p["symbol"] for p in positions]
    for i, sym1 in enumerate(symbols):
        for sym2 in symbols[i+1:]:
            key = (sym1, sym2) if (sym1, sym2) in PAIR_CORRELATIONS else (sym2, sym1)
            corr = PAIR_CORRELATIONS.get(key, 0)
            if corr >= 0.7:
                clusters.append({
                    "type": "pair_correlation",
                    "pairs": [sym1, sym2],
                    "correlation": corr,
                    "warning": "High correlation reduces diversification",
                })
    
    return clusters


def calculate_exposure_score() -> int:
    """Calculate overall exposure score (0-100, lower is better)."""
    score = 0
    
    currency_exp = calculate_currency_exposure()
    theme_exp = calculate_theme_exposure()
    
    # Currency concentration (0-40)
    max_currency_exp = max(abs(v) for v in currency_exp.values()) if currency_exp else 0
    score += min(40, int(max_currency_exp / limits.max_single_currency * 40))
    
    # Theme overlap (0-30)
    max_theme_exp = max(theme_exp.values()) if theme_exp else 0
    score += min(30, int(max_theme_exp / limits.max_theme_exposure * 30))
    
    # Correlation penalty (0-20)
    clusters = find_correlated_clusters()
    corr_clusters = [c for c in clusters if c["type"] == "pair_correlation" and c["correlation"] >= 0.8]
    score += min(20, len(corr_clusters) * 10)
    
    # Position count (0-10)
    score += min(10, len(positions) * 2)
    
    return min(100, score)


def calculate_unrealized_pnl() -> Dict[str, float]:
    """Calculate unrealized P&L by symbol."""
    pnl = {}
    for pos in positions:
        if pos.get("current_price") and pos.get("entry_price"):
            if pos["direction"].lower() == "long":
                pnl_pct = (pos["current_price"] - pos["entry_price"]) / pos["entry_price"] * 100
            else:
                pnl_pct = (pos["entry_price"] - pos["current_price"]) / pos["entry_price"] * 100
            pnl[pos["symbol"]] = round(pnl_pct * pos["risk_pct"], 4)
    return pnl


def calculate_pnl_by_currency() -> Dict[str, float]:
    """Calculate P&L by currency exposure."""
    currency_pnl = {c: 0.0 for c in CURRENCIES}
    unrealized = calculate_unrealized_pnl()
    
    for pos in positions:
        symbol_pnl = unrealized.get(pos["symbol"], 0) + realized_pnl.get(pos["symbol"], 0)
        decomposed = decompose_pair(pos["symbol"], pos["direction"], 1.0)  # Direction only
        
        for curr, direction in decomposed.items():
            if curr in currency_pnl:
                # Attribute P&L to the currencies involved
                currency_pnl[curr] += symbol_pnl * (1 if direction > 0 else -1) / 2
    
    return {k: round(v, 4) for k, v in currency_pnl.items()}


def generate_recommendations() -> List[dict]:
    """Generate portfolio recommendations."""
    recommendations = []
    
    currency_exp = calculate_currency_exposure()
    theme_exp = calculate_theme_exposure()
    clusters = find_correlated_clusters()
    
    # Check currency concentration
    for curr, exp in currency_exp.items():
        if abs(exp) > limits.concentration_danger:
            direction = "long" if exp > 0 else "short"
            # Find newest position contributing to this
            contributing = []
            for pos in positions:
                decomposed = decompose_pair(pos["symbol"], pos["direction"], pos["risk_pct"])
                if curr in decomposed and (decomposed[curr] > 0) == (exp > 0):
                    contributing.append(pos)
            
            if contributing:
                newest = contributing[-1]  # Last added
                recommendations.append({
                    "type": "REDUCE",
                    "severity": "high",
                    "message": f"{curr} {direction} exposure at {abs(exp):.2f}% exceeds {limits.concentration_danger}%",
                    "action": f"Consider closing {newest['symbol']} {newest['direction']}",
                    "target": newest["symbol"],
                })
        
        elif abs(exp) > limits.concentration_warning:
            direction = "long" if exp > 0 else "short"
            recommendations.append({
                "type": "MONITOR",
                "severity": "medium",
                "message": f"{curr} {direction} exposure at {abs(exp):.2f}%",
                "action": "Avoid adding more positions in this direction",
            })
    
    # Check theme concentration
    for theme, exp in theme_exp.items():
        if exp > limits.max_theme_exposure:
            recommendations.append({
                "type": "HEDGE",
                "severity": "medium",
                "message": f"{theme.replace('_', '-').title()} theme at {exp:.2f}%",
                "action": f"Consider counter-theme position for balance",
            })
    
    # Check for netting opportunities
    currency_positions = {}
    for pos in positions:
        base, quote = pos["symbol"][:3], pos["symbol"][3:]
        if base not in currency_positions:
            currency_positions[base] = {"long": [], "short": []}
        if quote not in currency_positions:
            currency_positions[quote] = {"long": [], "short": []}
        
        if pos["direction"].lower() == "long":
            currency_positions[base]["long"].append(pos)
            currency_positions[quote]["short"].append(pos)
        else:
            currency_positions[base]["short"].append(pos)
            currency_positions[quote]["long"].append(pos)
    
    # Find offsetting positions
    for curr, dirs in currency_positions.items():
        if dirs["long"] and dirs["short"]:
            recommendations.append({
                "type": "NET",
                "severity": "low",
                "message": f"Offsetting {curr} positions detected",
                "action": f"Consider netting {dirs['long'][0]['symbol']} and {dirs['short'][0]['symbol']}",
            })
    
    return recommendations


def evaluate_new_position(symbol: str, direction: str, risk_pct: float) -> dict:
    """Evaluate impact of adding a new position."""
    # Current state
    current_exp = calculate_currency_exposure()
    current_score = calculate_exposure_score()
    
    # Simulate adding position
    new_decomposed = decompose_pair(symbol, direction, risk_pct)
    new_exp = current_exp.copy()
    for curr, exp in new_decomposed.items():
        if curr in new_exp:
            new_exp[curr] += exp
    
    # Check limits
    violations = []
    for curr, exp in new_exp.items():
        if abs(exp) > limits.concentration_danger:
            violations.append(f"{curr} would reach {abs(exp):.2f}% (limit: {limits.concentration_danger}%)")
    
    # Estimate new score
    positions.append({"symbol": symbol, "direction": direction, "risk_pct": risk_pct})
    new_score = calculate_exposure_score()
    positions.pop()
    
    approved = len(violations) == 0
    
    return {
        "approved": approved,
        "current_exposure": {k: round(v, 2) for k, v in current_exp.items() if abs(v) > 0.01},
        "new_exposure": {k: round(v, 2) for k, v in new_exp.items() if abs(v) > 0.01},
        "score_before": current_score,
        "score_after": new_score,
        "violations": violations,
        "recommendation": "BLOCKED" if violations else "APPROVED",
    }


async def send_to_orchestrator():
    """Send portfolio state to Orchestrator."""
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{ORCHESTRATOR_URL}/api/ingest",
                json={
                    "agent_id": "portfolio",
                    "agent_name": AGENT_NAME,
                    "output_type": "analysis",
                    "timestamp": datetime.utcnow().isoformat(),
                    "data": {
                        "exposure_score": calculate_exposure_score(),
                        "currency_exposure": calculate_currency_exposure(),
                        "theme_exposure": calculate_theme_exposure(),
                        "position_count": len(positions),
                        "recommendations": len(generate_recommendations()),
                    },
                },
                timeout=5.0
            )
    except:
        pass


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
    print(f"🚀 {AGENT_NAME} (Portfolio Exposure Agent) v2.0 starting...")


@app.get("/", response_class=HTMLResponse)
async def home():
    currency_exp = calculate_currency_exposure()
    theme_exp = calculate_theme_exposure()
    score = calculate_exposure_score()
    recommendations = generate_recommendations()
    clusters = find_correlated_clusters()
    unrealized = calculate_unrealized_pnl()
    
    # Score color
    if score <= 25:
        score_color = "#22c55e"
        score_label = "Well Diversified"
    elif score <= 50:
        score_color = "#f59e0b"
        score_label = "Moderate Concentration"
    elif score <= 75:
        score_color = "#f97316"
        score_label = "High Concentration"
    else:
        score_color = "#ef4444"
        score_label = "Dangerous Concentration"
    
    # Currency exposure bars
    curr_html = ""
    max_exp = max(abs(v) for v in currency_exp.values()) if any(currency_exp.values()) else 1
    for curr in CURRENCIES:
        exp = currency_exp.get(curr, 0)
        width = abs(exp) / max(max_exp, 0.01) * 100
        color = "#22c55e" if exp > 0 else "#ef4444" if exp < 0 else "#333"
        curr_html += f'''
        <div class="exp-row">
            <span class="curr">{curr}</span>
            <div class="exp-bar-container">
                <div class="exp-bar" style="width:{width}%;background:{color}"></div>
            </div>
            <span class="exp-val" style="color:{color}">{exp:+.2f}%</span>
        </div>
        '''
    
    # Theme exposure
    theme_html = ""
    for theme, exp in theme_exp.items():
        theme_html += f'<div class="theme-row"><span>{theme.replace("_", " ").title()}</span><span>{exp:.2f}%</span></div>'
    
    # Positions
    pos_html = ""
    if positions:
        for pos in positions:
            pnl = unrealized.get(pos["symbol"], 0)
            pnl_color = "#22c55e" if pnl >= 0 else "#ef4444"
            pos_html += f'''
            <div class="position">
                <span>{pos["symbol"]} {pos["direction"].upper()}</span>
                <span>{pos["risk_pct"]}%</span>
                <span style="color:{pnl_color}">{pnl:+.4f}%</span>
            </div>
            '''
    else:
        pos_html = '<div style="color:#666">No positions</div>'
    
    # Recommendations
    rec_html = ""
    for rec in recommendations[:5]:
        sev_color = "#ef4444" if rec["severity"] == "high" else "#f59e0b" if rec["severity"] == "medium" else "#3b82f6"
        rec_html += f'''
        <div class="rec" style="border-left:3px solid {sev_color}">
            <div class="rec-type">{rec["type"]}</div>
            <div class="rec-msg">{rec["message"]}</div>
            <div class="rec-action">{rec["action"]}</div>
        </div>
        '''
    if not rec_html:
        rec_html = '<div style="color:#666">No recommendations</div>'
    
    # Clusters
    cluster_html = ""
    for cluster in clusters[:3]:
        if cluster["type"] == "currency_concentration":
            cluster_html += f'<div class="cluster">{cluster["count"]}x {cluster["currency"]} {cluster["direction"]}s ({cluster["total_exposure"]}% total)</div>'
        else:
            cluster_html += f'<div class="cluster">{cluster["pairs"][0]}/{cluster["pairs"][1]} corr: {cluster["correlation"]}</div>'
    if not cluster_html:
        cluster_html = '<div style="color:#666">No clusters</div>'
    
    return f'''<!DOCTYPE html>
<html><head>
    <title>⚖️ Balancer - Portfolio Agent</title>
    <meta http-equiv="refresh" content="15">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, sans-serif; background: #0a0a0f; color: #e0e0e0; padding: 20px; }}
        .header {{ display: flex; align-items: center; gap: 15px; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid #333; }}
        .header h1 {{ color: #8b5cf6; }}
        .score-badge {{ background: {score_color}20; color: {score_color}; padding: 8px 16px; border-radius: 20px; font-weight: bold; }}
        .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }}
        .card {{ background: #1a1a24; border-radius: 12px; padding: 20px; }}
        .card h2 {{ font-size: 14px; color: #888; margin-bottom: 15px; text-transform: uppercase; }}
        .exp-row {{ display: flex; align-items: center; gap: 10px; margin: 8px 0; }}
        .curr {{ width: 40px; font-weight: bold; }}
        .exp-bar-container {{ flex: 1; height: 12px; background: #333; border-radius: 6px; overflow: hidden; }}
        .exp-bar {{ height: 100%; border-radius: 6px; }}
        .exp-val {{ width: 60px; text-align: right; font-size: 12px; }}
        .theme-row {{ display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #333; }}
        .position {{ display: flex; justify-content: space-between; padding: 10px; background: #0a0a0f; border-radius: 8px; margin: 8px 0; font-size: 13px; }}
        .rec {{ padding: 10px; background: #0a0a0f; border-radius: 8px; margin: 8px 0; padding-left: 15px; }}
        .rec-type {{ font-weight: bold; font-size: 12px; color: #888; }}
        .rec-msg {{ font-size: 13px; margin: 5px 0; }}
        .rec-action {{ font-size: 11px; color: #666; }}
        .cluster {{ padding: 8px; background: #0a0a0f; border-radius: 6px; margin: 5px 0; font-size: 12px; }}
        .score-display {{ text-align: center; padding: 20px; }}
        .score-value {{ font-size: 48px; font-weight: bold; color: {score_color}; }}
        .score-label {{ font-size: 14px; color: #888; }}
        .chat-section {{ background: #1a1a24; border-radius: 12px; padding: 20px; }}
        .chat-section h2 {{ color: #8b5cf6; margin-bottom: 15px; }}
        .chat-messages {{ height: 120px; overflow-y: auto; background: #0a0a0f; border-radius: 8px; padding: 10px; margin-bottom: 10px; }}
        .chat-input {{ display: flex; gap: 10px; }}
        .chat-input input {{ flex: 1; padding: 10px; border-radius: 8px; border: 1px solid #333; background: #0a0a0f; color: #fff; }}
        .chat-input button {{ padding: 10px 20px; background: #8b5cf6; color: #fff; border: none; border-radius: 8px; cursor: pointer; }}
        .message {{ margin: 8px 0; padding: 8px; border-radius: 6px; font-size: 13px; }}
        .message.user {{ background: #333; margin-left: 20%; }}
        .message.agent {{ background: #3d1a4d; margin-right: 20%; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>⚖️ Balancer</h1>
        <span class="score-badge">Score: {score}/100</span>
        <span style="color:{score_color}">{score_label}</span>
        <span style="color: #888; margin-left: auto;">Portfolio Exposure Agent v2.0</span>
    </div>
    
    <div class="grid">
        <div class="card">
            <h2>💱 Currency Exposure</h2>
            {curr_html}
        </div>
        <div class="card">
            <div class="score-display">
                <div class="score-value">{score}</div>
                <div class="score-label">Exposure Score (lower is better)</div>
            </div>
            <h2 style="margin-top:15px">📊 Theme Exposure</h2>
            {theme_html}
        </div>
    </div>
    
    <div class="grid">
        <div class="card">
            <h2>📈 Open Positions ({len(positions)})</h2>
            {pos_html}
        </div>
        <div class="card">
            <h2>🔗 Correlated Clusters</h2>
            {cluster_html}
        </div>
    </div>
    
    <div class="card" style="margin-bottom:20px">
        <h2>💡 Recommendations</h2>
        {rec_html}
    </div>
    
    <div class="chat-section">
        <h2>💬 Ask Balancer</h2>
        <div class="chat-messages" id="messages"></div>
        <div class="chat-input">
            <input type="text" id="input" placeholder="Ask about portfolio..." onkeypress="if(event.key==='Enter')sendMessage()">
            <button onclick="sendMessage()">Send</button>
        </div>
    </div>
    <script>
        const CHAT_KEY = 'balancer_chat_history';
        
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
    context = f"""Portfolio State:
- Positions: {len(positions)}
- Currency Exposure: {json.dumps(calculate_currency_exposure())}
- Theme Exposure: {json.dumps(calculate_theme_exposure())}
- Exposure Score: {calculate_exposure_score()}
- Recommendations: {json.dumps(generate_recommendations())}"""
    return {"response": await call_claude(request.message, context)}


@app.post("/api/position/add")
async def add_position(request: PositionRequest):
    """Add a position to tracking."""
    positions.append({
        "symbol": request.symbol,
        "direction": request.direction,
        "risk_pct": request.risk_pct,
        "entry_price": request.entry_price,
        "current_price": request.current_price or request.entry_price,
    })
    await send_to_orchestrator()
    return {"added": True, "total_positions": len(positions)}


@app.post("/api/position/remove")
async def remove_position(symbol: str, realized: float = 0):
    """Remove a position from tracking."""
    global positions
    removed = [p for p in positions if p["symbol"] == symbol]
    positions = [p for p in positions if p["symbol"] != symbol]
    
    if realized != 0:
        realized_pnl[symbol] = realized_pnl.get(symbol, 0) + realized
    
    await send_to_orchestrator()
    return {"removed": len(removed), "total_positions": len(positions)}


@app.post("/api/evaluate")
async def evaluate(symbol: str, direction: str, risk_pct: float):
    """Evaluate a potential new position."""
    return evaluate_new_position(symbol, direction, risk_pct)


@app.get("/api/exposure")
async def get_exposure():
    """Get current exposure breakdown."""
    return {
        "currency": calculate_currency_exposure(),
        "theme": calculate_theme_exposure(),
        "score": calculate_exposure_score(),
    }


@app.get("/api/recommendations")
async def get_recommendations():
    """Get portfolio recommendations."""
    return generate_recommendations()


@app.get("/api/clusters")
async def get_clusters():
    """Get correlated clusters."""
    return find_correlated_clusters()


@app.get("/api/status")
async def get_status():
    return {
        "agent_id": "portfolio",
        "name": AGENT_NAME,
        "status": "active",
        "positions": len(positions),
        "exposure_score": calculate_exposure_score(),
        "recommendations": len(generate_recommendations()),
        "version": "2.0",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
