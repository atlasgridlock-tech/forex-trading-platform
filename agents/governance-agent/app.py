"""
Model Governance Agent - Arbiter
Version control, change validation, overfit detection
"""

import os
import json
import asyncio
import httpx
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from enum import Enum
import hashlib
import uuid

app = FastAPI(title="Arbiter - Model Governance Agent", version="1.0")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://orchestrator-agent:8000")
AGENT_NAME = "Arbiter"
WORKSPACE = Path("/app/workspace")
VERSIONS_DIR = WORKSPACE / "versions"
CHANGELOG_FILE = WORKSPACE / "CHANGELOG.md"
REQUESTS_DIR = WORKSPACE / "requests"

# Ensure directories exist
VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
REQUESTS_DIR.mkdir(parents=True, exist_ok=True)


class ChangeType(str, Enum):
    MAJOR = "major"      # Logic change
    MINOR = "minor"      # Parameter adjustment
    PATCH = "patch"      # Bug fix
    ROLLBACK = "rollback"


class RequestStatus(str, Enum):
    PENDING = "pending"
    VALIDATING = "validating"
    APPROVED = "approved"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


class ValidationResults(BaseModel):
    in_sample_pf: float = 0
    in_sample_wr: float = 0
    in_sample_trades: int = 0
    out_of_sample_pf: float = 0
    out_of_sample_wr: float = 0
    out_of_sample_trades: int = 0
    walk_forward_positive: int = 0
    walk_forward_total: int = 6
    paper_trades: int = 0
    paper_result_r: float = 0


class ChangeRequest(BaseModel):
    strategy_name: str
    change_type: ChangeType
    description: str
    rationale: str
    changes: Dict[str, Any]  # {"param_name": {"old": x, "new": y}}
    requested_by: str
    validation: Optional[ValidationResults] = None


class ChatRequest(BaseModel):
    message: str


# In-memory storage (would be DB in production)
versions: Dict[str, List[dict]] = {}  # strategy_name -> [version_records]
change_requests: Dict[str, dict] = {}  # request_id -> request_record


def generate_request_id() -> str:
    return f"CR-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"


def get_current_version(strategy_name: str) -> str:
    """Get current version string for a strategy."""
    if strategy_name not in versions or not versions[strategy_name]:
        return f"{strategy_name}-v1.0.0"
    
    latest = versions[strategy_name][-1]
    return latest.get("version", f"{strategy_name}-v1.0.0")


def increment_version(current: str, change_type: ChangeType) -> str:
    """Increment version based on change type."""
    # Parse current version: STRATEGY-vX.Y.Z
    try:
        parts = current.rsplit("-v", 1)
        name = parts[0]
        version_parts = parts[1].split(".")
        major = int(version_parts[0])
        minor = int(version_parts[1])
        patch = int(version_parts[2])
    except:
        return f"{current.split('-v')[0]}-v1.0.0"
    
    if change_type == ChangeType.MAJOR:
        major += 1
        minor = 0
        patch = 0
    elif change_type == ChangeType.MINOR:
        minor += 1
        patch = 0
    else:  # PATCH
        patch += 1
    
    return f"{name}-v{major}.{minor}.{patch}"


def calculate_overfit_score(validation: ValidationResults, changes: Dict) -> int:
    """Calculate overfit risk score (0-100)."""
    score = 0
    
    # Parameter count penalty (assuming changes dict contains params)
    param_count = len(changes)
    if param_count > 10:
        score += 30
    elif param_count > 5:
        score += 15
    elif param_count > 3:
        score += 5
    
    # In-sample vs out-of-sample gap
    if validation.in_sample_pf > 0 and validation.out_of_sample_pf > 0:
        pf_gap = (validation.in_sample_pf - validation.out_of_sample_pf) / validation.in_sample_pf
        if pf_gap > 0.5:
            score += 35  # Severe degradation
        elif pf_gap > 0.3:
            score += 25
        elif pf_gap > 0.2:
            score += 15
        elif pf_gap > 0.1:
            score += 5
    
    # Win rate gap
    if validation.in_sample_wr > 0 and validation.out_of_sample_wr > 0:
        wr_gap = validation.in_sample_wr - validation.out_of_sample_wr
        if wr_gap > 15:
            score += 20
        elif wr_gap > 10:
            score += 10
        elif wr_gap > 5:
            score += 5
    
    # Walk-forward consistency
    if validation.walk_forward_total > 0:
        wf_ratio = validation.walk_forward_positive / validation.walk_forward_total
        if wf_ratio < 0.5:
            score += 25  # Fails more than passes
        elif wf_ratio < 0.67:
            score += 15
        elif wf_ratio < 0.83:
            score += 5
    
    # Suspiciously good in-sample results
    if validation.in_sample_pf > 4.0:
        score += 15
    if validation.in_sample_wr > 70:
        score += 10
    
    return min(score, 100)


def detect_red_flags(validation: ValidationResults, changes: Dict) -> List[str]:
    """Detect specific red flags in the change request."""
    flags = []
    
    # Suspiciously good in-sample
    if validation.in_sample_pf > 4.0:
        flags.append(f"❌ Suspiciously good in-sample PF ({validation.in_sample_pf:.1f})")
    if validation.in_sample_wr > 70:
        flags.append(f"❌ Suspiciously high in-sample win rate ({validation.in_sample_wr:.0f}%)")
    
    # Severe OOS degradation
    if validation.in_sample_pf > 0 and validation.out_of_sample_pf > 0:
        gap = (validation.in_sample_pf - validation.out_of_sample_pf) / validation.in_sample_pf * 100
        if gap > 50:
            flags.append(f"❌ Severe OOS degradation ({gap:.0f}% drop)")
        elif gap > 30:
            flags.append(f"⚠️ Significant OOS degradation ({gap:.0f}% drop)")
    
    # Walk-forward failure
    if validation.walk_forward_total > 0:
        if validation.walk_forward_positive < validation.walk_forward_total * 0.5:
            flags.append(f"❌ Walk-forward fails ({validation.walk_forward_positive}/{validation.walk_forward_total})")
    
    # Excessive parameters
    if len(changes) > 10:
        flags.append(f"❌ Excessive parameters ({len(changes)})")
    elif len(changes) > 7:
        flags.append(f"⚠️ Many parameters ({len(changes)})")
    
    # No paper validation for major changes
    if validation.paper_trades == 0:
        flags.append("⚠️ No paper trade validation")
    elif validation.paper_trades < 20:
        flags.append(f"⚠️ Limited paper trades ({validation.paper_trades})")
    
    # OOS profit factor below 1
    if validation.out_of_sample_pf < 1.0 and validation.out_of_sample_trades > 10:
        flags.append(f"❌ OOS profit factor below 1 ({validation.out_of_sample_pf:.2f})")
    
    return flags


def evaluate_change_request(request: dict) -> dict:
    """Evaluate a change request and determine approval."""
    validation = request.get("validation", {})
    changes = request.get("changes", {})
    change_type = request.get("change_type", "minor")
    
    # Convert validation dict to ValidationResults if needed
    if isinstance(validation, dict):
        val = ValidationResults(**validation)
    else:
        val = validation
    
    overfit_score = calculate_overfit_score(val, changes)
    red_flags = detect_red_flags(val, changes)
    
    # Decision logic
    approved = True
    reasons = []
    
    # Automatic rejection criteria
    if overfit_score > 75:
        approved = False
        reasons.append("Overfit score too high (>75)")
    
    if val.out_of_sample_pf < 1.0 and val.out_of_sample_trades > 20:
        approved = False
        reasons.append("Out-of-sample profit factor below 1")
    
    if val.walk_forward_total > 0 and val.walk_forward_positive < val.walk_forward_total * 0.5:
        approved = False
        reasons.append("Walk-forward analysis fails majority of periods")
    
    # Major changes need more validation
    if change_type == "major":
        if val.paper_trades < 30:
            approved = False
            reasons.append("Major changes require 30+ paper trades")
        if val.walk_forward_total == 0:
            approved = False
            reasons.append("Major changes require walk-forward analysis")
    
    # Minor changes need some validation
    if change_type == "minor":
        if val.out_of_sample_trades < 20:
            reasons.append("Recommend more out-of-sample data")
    
    return {
        "approved": approved,
        "overfit_score": overfit_score,
        "red_flags": red_flags,
        "rejection_reasons": reasons if not approved else [],
        "warnings": [f for f in red_flags if f.startswith("⚠️")],
    }


def save_version(strategy_name: str, version_record: dict):
    """Save a version record."""
    if strategy_name not in versions:
        versions[strategy_name] = []
    versions[strategy_name].append(version_record)
    
    # Persist to file
    version_file = VERSIONS_DIR / f"{strategy_name}.json"
    with open(version_file, "w") as f:
        json.dump(versions[strategy_name], f, indent=2, default=str)


def load_versions():
    """Load all versions from disk."""
    global versions
    for f in VERSIONS_DIR.glob("*.json"):
        try:
            with open(f) as file:
                strategy_name = f.stem
                versions[strategy_name] = json.load(file)
        except Exception as e:
            print(f"Error loading {f}: {e}")


def update_changelog(version_record: dict):
    """Append to changelog."""
    entry = f"""
## [{version_record['version'].split('-v')[1]}] - {version_record['created_at'][:10]}
### {version_record['change_type'].title()}
- {version_record['description']}
- Rationale: {version_record['rationale']}

### Validation
- OOS PF: {version_record.get('validation', {}).get('out_of_sample_pf', 'N/A')}
- WF: {version_record.get('validation', {}).get('walk_forward_positive', 0)}/{version_record.get('validation', {}).get('walk_forward_total', 6)} periods positive
- Paper: {version_record.get('validation', {}).get('paper_result_r', 0):+.1f}R over {version_record.get('validation', {}).get('paper_trades', 0)} trades

### Approved
- By: {AGENT_NAME}
- Rollback: {version_record.get('rollback_version', 'N/A')}

---
"""
    
    # Read existing or create new
    if CHANGELOG_FILE.exists():
        content = CHANGELOG_FILE.read_text()
    else:
        content = f"# Strategy Changelog\n\nManaged by {AGENT_NAME}\n\n---\n"
    
    # Insert after header
    parts = content.split("---", 1)
    if len(parts) > 1:
        content = parts[0] + "---" + entry + parts[1]
    else:
        content += entry
    
    CHANGELOG_FILE.write_text(content)


async def call_claude(prompt: str, context: str = "") -> str:
    if not ANTHROPIC_API_KEY:
        return "[No API key configured]"
    
    soul = (WORKSPACE / "SOUL.md").read_text() if (WORKSPACE / "SOUL.md").exists() else ""
    
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 2048,
                    "system": soul,
                    "messages": [{"role": "user", "content": f"{context}\n\n{prompt}" if context else prompt}]
                },
                timeout=60.0
            )
            if r.status_code == 200:
                return r.json()["content"][0]["text"]
    except Exception as e:
        print(f"Claude API error: {e}")
    
    return "[Error calling Claude API]"


@app.on_event("startup")
async def startup():
    load_versions()
    print(f"🚀 {AGENT_NAME} (Model Governance Agent) v1.0 starting...")
    print(f"   Loaded {len(versions)} strategy version histories")


@app.get("/", response_class=HTMLResponse)
async def home():
    # Count stats
    total_versions = sum(len(v) for v in versions.values())
    total_strategies = len(versions)
    pending_requests = len([r for r in change_requests.values() if r.get("status") == "pending"])
    
    # Recent requests
    recent = sorted(change_requests.values(), key=lambda x: x.get("created_at", ""), reverse=True)[:10]
    
    request_rows = ""
    for req in recent:
        status = req.get("status", "unknown")
        status_color = "#22c55e" if status == "approved" else "#ef4444" if status == "rejected" else "#f59e0b"
        request_rows += f'''<tr>
            <td>{req.get("request_id", "?")}</td>
            <td>{req.get("strategy_name", "?")}</td>
            <td>{req.get("change_type", "?")}</td>
            <td style="color:{status_color}">{status.upper()}</td>
            <td>{req.get("overfit_score", "?")}</td>
            <td>{req.get("created_at", "?")[:16]}</td>
        </tr>'''
    
    if not request_rows:
        request_rows = '<tr><td colspan="6" style="text-align:center;color:#666">No change requests yet</td></tr>'
    
    # Strategy versions
    strategy_rows = ""
    for strategy_name, vers in versions.items():
        if vers:
            latest = vers[-1]
            strategy_rows += f'''<tr>
                <td>{strategy_name}</td>
                <td>{latest.get("version", "?")}</td>
                <td>{len(vers)}</td>
                <td>{latest.get("created_at", "?")[:10]}</td>
            </tr>'''
    
    if not strategy_rows:
        strategy_rows = '<tr><td colspan="4" style="text-align:center;color:#666">No strategies versioned yet</td></tr>'
    
    return f'''<!DOCTYPE html>
<html><head>
    <title>⚖️ Arbiter - Governance Agent</title>
    <meta http-equiv="refresh" content="30">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, sans-serif; background: #0a0a0f; color: #e0e0e0; padding: 20px; }}
        .header {{ display: flex; align-items: center; gap: 15px; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid #333; }}
        .header h1 {{ color: #f59e0b; }}
        .stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 20px; }}
        .stat {{ background: #1a1a24; border-radius: 10px; padding: 20px; text-align: center; }}
        .stat-value {{ font-size: 28px; font-weight: bold; color: #f59e0b; }}
        .stat-label {{ font-size: 11px; color: #666; margin-top: 5px; }}
        .section {{ background: #1a1a24; border-radius: 12px; padding: 20px; margin-bottom: 20px; }}
        .section h2 {{ color: #f59e0b; margin-bottom: 15px; font-size: 14px; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
        th {{ text-align: left; padding: 10px; border-bottom: 1px solid #333; color: #888; }}
        td {{ padding: 10px; border-bottom: 1px solid #222; }}
        .chat-section {{ background: #1a1a24; border-radius: 12px; padding: 20px; }}
        .chat-section h2 {{ color: #f59e0b; margin-bottom: 15px; }}
        .chat-messages {{ height: 100px; overflow-y: auto; background: #0a0a0f; border-radius: 8px; padding: 10px; margin-bottom: 10px; }}
        .chat-input {{ display: flex; gap: 10px; }}
        .chat-input input {{ flex: 1; padding: 12px; border-radius: 8px; border: 1px solid #333; background: #0a0a0f; color: #fff; }}
        .chat-input button {{ padding: 12px 25px; background: #f59e0b; color: #000; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>⚖️ Arbiter</h1>
        <span style="color: #888; margin-left: auto;">Model Governance Agent v1.0</span>
    </div>
    
    <div class="stats">
        <div class="stat">
            <div class="stat-value">{total_strategies}</div>
            <div class="stat-label">Strategies Tracked</div>
        </div>
        <div class="stat">
            <div class="stat-value">{total_versions}</div>
            <div class="stat-label">Total Versions</div>
        </div>
        <div class="stat">
            <div class="stat-value">{len(change_requests)}</div>
            <div class="stat-label">Change Requests</div>
        </div>
        <div class="stat">
            <div class="stat-value">{pending_requests}</div>
            <div class="stat-label">Pending Review</div>
        </div>
    </div>
    
    <div class="section">
        <h2>📋 RECENT CHANGE REQUESTS</h2>
        <table>
            <tr><th>Request ID</th><th>Strategy</th><th>Type</th><th>Status</th><th>Overfit Score</th><th>Date</th></tr>
            {request_rows}
        </table>
    </div>
    
    <div class="section">
        <h2>📦 STRATEGY VERSIONS</h2>
        <table>
            <tr><th>Strategy</th><th>Current Version</th><th>Total Versions</th><th>Last Updated</th></tr>
            {strategy_rows}
        </table>
    </div>
    
    <div class="chat-section">
        <h2>💬 Ask Arbiter</h2>
        <div class="chat-messages" id="messages"></div>
        <div class="chat-input">
            <input type="text" id="input" placeholder="Ask about governance, versions, validation..." onkeypress="if(event.key==='Enter')sendMessage()">
            <button onclick="sendMessage()">Send</button>
        </div>
    </div>
    <script>
        const CHAT_KEY = 'arbiter_chat_history';
        
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
    context = f"Versions: {json.dumps(versions, default=str)[:2000]}\nRequests: {json.dumps(list(change_requests.values())[-5:], default=str)[:2000]}"
    return {"response": await call_claude(request.message, context)}


@app.post("/api/request")
async def submit_change_request(request: ChangeRequest):
    """Submit a change request for review."""
    request_id = generate_request_id()
    current_version = get_current_version(request.strategy_name)
    
    record = {
        "request_id": request_id,
        "strategy_name": request.strategy_name,
        "change_type": request.change_type.value,
        "description": request.description,
        "rationale": request.rationale,
        "changes": request.changes,
        "requested_by": request.requested_by,
        "validation": request.validation.dict() if request.validation else {},
        "current_version": current_version,
        "created_at": datetime.utcnow().isoformat(),
        "status": RequestStatus.PENDING.value,
    }
    
    change_requests[request_id] = record
    
    return {"request_id": request_id, "status": "pending", "current_version": current_version}


@app.post("/api/evaluate/{request_id}")
async def evaluate_request(request_id: str):
    """Evaluate a pending change request."""
    if request_id not in change_requests:
        raise HTTPException(status_code=404, detail="Request not found")
    
    request = change_requests[request_id]
    if request["status"] != "pending":
        return {"error": f"Request already {request['status']}"}
    
    # Update status
    request["status"] = RequestStatus.VALIDATING.value
    
    # Evaluate
    evaluation = evaluate_change_request(request)
    
    request["overfit_score"] = evaluation["overfit_score"]
    request["red_flags"] = evaluation["red_flags"]
    request["warnings"] = evaluation["warnings"]
    
    if evaluation["approved"]:
        request["status"] = RequestStatus.APPROVED.value
        
        # Create new version
        new_version = increment_version(request["current_version"], ChangeType(request["change_type"]))
        
        version_record = {
            "version": new_version,
            "created_at": datetime.utcnow().isoformat(),
            "created_by": request["requested_by"],
            "change_type": request["change_type"],
            "description": request["description"],
            "rationale": request["rationale"],
            "changes": request["changes"],
            "validation": request["validation"],
            "approved_by": AGENT_NAME,
            "rollback_version": request["current_version"],
            "request_id": request_id,
            "overfit_score": evaluation["overfit_score"],
            "status": "active",
        }
        
        save_version(request["strategy_name"], version_record)
        update_changelog(version_record)
        
        request["new_version"] = new_version
    else:
        request["status"] = RequestStatus.REJECTED.value
        request["rejection_reasons"] = evaluation["rejection_reasons"]
    
    request["evaluated_at"] = datetime.utcnow().isoformat()
    
    return {
        "request_id": request_id,
        "status": request["status"],
        "overfit_score": evaluation["overfit_score"],
        "red_flags": evaluation["red_flags"],
        "approved": evaluation["approved"],
        "rejection_reasons": evaluation.get("rejection_reasons", []),
        "new_version": request.get("new_version"),
    }


@app.post("/api/rollback/{strategy_name}")
async def rollback_strategy(strategy_name: str, to_version: Optional[str] = None):
    """Rollback a strategy to a previous version."""
    if strategy_name not in versions or not versions[strategy_name]:
        raise HTTPException(status_code=404, detail="Strategy not found")
    
    strategy_versions = versions[strategy_name]
    
    if len(strategy_versions) < 2:
        raise HTTPException(status_code=400, detail="No previous version to rollback to")
    
    if to_version:
        # Find specific version
        target = None
        for v in strategy_versions:
            if v["version"] == to_version:
                target = v
                break
        if not target:
            raise HTTPException(status_code=404, detail=f"Version {to_version} not found")
    else:
        # Rollback to previous
        target = strategy_versions[-2]
    
    # Create rollback record
    rollback_record = {
        "version": target["version"] + "-rollback",
        "created_at": datetime.utcnow().isoformat(),
        "created_by": "operator",
        "change_type": "rollback",
        "description": f"Rollback to {target['version']}",
        "rationale": "Manual rollback requested",
        "rolled_back_from": strategy_versions[-1]["version"],
        "rolled_back_to": target["version"],
        "status": "active",
    }
    
    # Mark current as inactive
    strategy_versions[-1]["status"] = "rolled_back"
    
    save_version(strategy_name, rollback_record)
    
    return {
        "status": "rolled_back",
        "from_version": strategy_versions[-2]["version"],
        "to_version": target["version"],
    }


@app.get("/api/versions/{strategy_name}")
async def get_versions(strategy_name: str):
    """Get version history for a strategy."""
    if strategy_name not in versions:
        return {"strategy": strategy_name, "versions": [], "count": 0}
    
    return {
        "strategy": strategy_name,
        "versions": versions[strategy_name],
        "count": len(versions[strategy_name]),
        "current": versions[strategy_name][-1] if versions[strategy_name] else None,
    }


@app.get("/api/requests")
async def get_requests(status: Optional[str] = None):
    """Get change requests, optionally filtered by status."""
    if status:
        filtered = [r for r in change_requests.values() if r.get("status") == status]
    else:
        filtered = list(change_requests.values())
    
    return {
        "requests": sorted(filtered, key=lambda x: x.get("created_at", ""), reverse=True),
        "count": len(filtered),
    }


@app.get("/api/overfit/{strategy_name}")
async def check_overfit_risk(strategy_name: str):
    """Check overfit risk for a strategy based on its history."""
    if strategy_name not in versions or not versions[strategy_name]:
        return {"strategy": strategy_name, "risk": "unknown", "message": "No version history"}
    
    # Analyze version history for overfit patterns
    vers = versions[strategy_name]
    recent = vers[-5:] if len(vers) >= 5 else vers
    
    avg_overfit = sum(v.get("overfit_score", 50) for v in recent) / len(recent)
    frequent_changes = len([v for v in vers if v.get("created_at", "")[:7] == datetime.utcnow().strftime("%Y-%m")]) > 3
    
    if avg_overfit > 60 or frequent_changes:
        risk = "high"
        message = "Strategy shows signs of over-optimization"
    elif avg_overfit > 40:
        risk = "medium"
        message = "Strategy has moderate complexity"
    else:
        risk = "low"
        message = "Strategy appears robust"
    
    return {
        "strategy": strategy_name,
        "risk": risk,
        "avg_overfit_score": round(avg_overfit, 1),
        "version_count": len(vers),
        "recent_changes": len([v for v in vers if v.get("created_at", "")[:7] == datetime.utcnow().strftime("%Y-%m")]),
        "message": message,
    }


@app.get("/api/changelog")
async def get_changelog():
    """Get the changelog."""
    if CHANGELOG_FILE.exists():
        return {"changelog": CHANGELOG_FILE.read_text()}
    return {"changelog": "No changelog yet"}


@app.get("/api/status")
async def get_status():
    total_versions = sum(len(v) for v in versions.values())
    pending = len([r for r in change_requests.values() if r.get("status") == "pending"])
    
    return {
        "agent_id": "governance",
        "name": AGENT_NAME,
        "status": "active",
        "strategies_tracked": len(versions),
        "total_versions": total_versions,
        "pending_requests": pending,
        "version": "1.0",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
