"""
Forex Trading Platform — Workflow Engine
8 Core Workflows orchestrating 15 agents
"""

import asyncio
import httpx
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("workflows")


# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

class WorkflowConfig:
    """Global workflow configuration."""
    
    # Agent URLs - use host.docker.internal when running in Docker
    import os
    HOST = os.getenv("AGENT_HOST", "host.docker.internal")
    
    # Broker symbol suffix (e.g., ".s" for JustMarkets)
    SYMBOL_SUFFIX = os.getenv("SYMBOL_SUFFIX", "")
    
    @staticmethod
    def broker_symbol(symbol: str) -> str:
        """Convert internal symbol to broker symbol."""
        suffix = WorkflowConfig.SYMBOL_SUFFIX
        if suffix and not symbol.endswith(suffix):
            return symbol + suffix
        return symbol
    
    @staticmethod
    def internal_symbol(broker_sym: str) -> str:
        """Convert broker symbol to internal symbol."""
        suffix = WorkflowConfig.SYMBOL_SUFFIX
        if suffix and broker_sym.endswith(suffix):
            return broker_sym[:-len(suffix)]
        return broker_sym
    
    AGENTS = {
        "curator": f"http://{HOST}:3021",
        "sentinel": f"http://{HOST}:3010",
        "oracle": f"http://{HOST}:3011",
        "atlas": f"http://{HOST}:3012",
        "guardian": f"http://{HOST}:3013",
        "architect": f"http://{HOST}:3014",
        "pulse": f"http://{HOST}:3015",
        "compass": f"http://{HOST}:3016",
        "tactician": f"http://{HOST}:3017",
        "balancer": f"http://{HOST}:3018",
        "executor": f"http://{HOST}:3019",
        "nexus": f"http://{HOST}:3020",
        "chronicle": f"http://{HOST}:3022",
        "insight": f"http://{HOST}:3023",
        "arbiter": f"http://{HOST}:3024",
    }
    
    # Trading symbols (must match Curator's configured symbols)
    SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "GBPJPY", "USDCHF", "USDCAD", "EURAUD", "AUDNZD", "AUDUSD"]
    
    # Timing
    INTRADAY_SCAN_INTERVAL_SECONDS = 300  # 5 minutes
    POSITION_MONITOR_INTERVAL_SECONDS = 60  # 1 minute
    
    # Thresholds
    HIGH_QUALITY_SETUP_SCORE = 75
    DATA_QUALITY_MINIMUM = 0.7  # 0-1 scale (0.7 = 70%)
    MAX_DRAWDOWN_DAILY = 2.0  # percent
    MAX_DRAWDOWN_WEEKLY = 4.0
    MAX_DRAWDOWN_TOTAL = 10.0


# ═══════════════════════════════════════════════════════════════
# WORKFLOW STATE
# ═══════════════════════════════════════════════════════════════

class WorkflowStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    HALTED = "halted"


@dataclass
class WorkflowResult:
    """Result of a workflow execution."""
    workflow: str
    status: WorkflowStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0
    steps_completed: int = 0
    steps_total: int = 0
    outputs: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "workflow": self.workflow,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "steps_completed": self.steps_completed,
            "steps_total": self.steps_total,
            "outputs": self.outputs,
            "errors": self.errors,
        }


@dataclass
class SystemState:
    """Global system state tracking."""
    trading_mode: str = "paper"  # paper | shadow | guarded_live
    trading_halted: bool = False
    halt_reason: Optional[str] = None
    last_market_open_prep: Optional[datetime] = None
    last_eod_review: Optional[datetime] = None
    last_weekly_review: Optional[datetime] = None
    active_positions: List[str] = field(default_factory=list)
    watchlist: List[Dict] = field(default_factory=list)
    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    total_drawdown: float = 0.0
    incidents: List[Dict] = field(default_factory=list)


# Global state
system_state = SystemState()
workflow_history: List[WorkflowResult] = []


# ═══════════════════════════════════════════════════════════════
# HTTP CLIENT
# ═══════════════════════════════════════════════════════════════

async def call_agent(agent: str, endpoint: str, method: str = "GET", 
                     data: dict = None, timeout: float = 10.0) -> Optional[dict]:
    """Call an agent's API endpoint."""
    url = f"{WorkflowConfig.AGENTS[agent]}{endpoint}"
    try:
        async with httpx.AsyncClient() as client:
            if method == "GET":
                r = await client.get(url, timeout=timeout)
            else:
                r = await client.post(url, json=data or {}, timeout=timeout)
            
            if r.status_code == 200:
                return r.json()
            else:
                logger.warning(f"Agent {agent} returned {r.status_code}: {r.text[:200]}")
                return None
    except Exception as e:
        logger.error(f"Failed to call {agent}: {e}")
        return None


async def call_agents_parallel(calls: List[tuple]) -> Dict[str, Any]:
    """Call multiple agents in parallel. calls = [(agent, endpoint, method, data), ...]"""
    async def single_call(agent, endpoint, method="GET", data=None):
        return agent, await call_agent(agent, endpoint, method, data)
    
    tasks = [single_call(*c) for c in calls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    return {
        name: result for name, result in results 
        if not isinstance(result, Exception) and result[1] is not None
    }


# ═══════════════════════════════════════════════════════════════
# WORKFLOW A: MARKET OPEN PREP
# ═══════════════════════════════════════════════════════════════

async def workflow_market_open_prep() -> WorkflowResult:
    """
    Market Open Preparation Workflow
    Run before each major session (Sydney, Tokyo, London, NY)
    
    Steps:
    1. Refresh all market data
    2. Compute daily/weekly levels
    3. Update macro summary
    4. Update event calendar
    5. Classify regime for all symbols
    6. Generate initial watchlist
    """
    result = WorkflowResult(
        workflow="market_open_prep",
        status=WorkflowStatus.RUNNING,
        started_at=datetime.utcnow(),
        steps_total=6
    )
    
    try:
        # Step 1: Refresh market data
        logger.info("[A.1] Refreshing market data...")
        data_refresh = await call_agent("curator", "/api/refresh", "POST")
        if not data_refresh:
            result.errors.append("Failed to refresh market data")
        result.steps_completed += 1
        result.outputs["data_refresh"] = data_refresh
        
        # Step 2: Compute daily/weekly levels
        logger.info("[A.2] Computing key levels...")
        levels = {}
        for symbol in WorkflowConfig.SYMBOLS:
            level_data = await call_agent("architect", f"/api/levels/{symbol}")
            if level_data:
                levels[symbol] = level_data
        result.steps_completed += 1
        result.outputs["levels"] = levels
        
        # Step 3: Update macro summary
        logger.info("[A.3] Updating macro summary...")
        macro_calls = [("oracle", f"/api/outlook/{sym}") for sym in WorkflowConfig.SYMBOLS]
        macro_data = {}
        for symbol in WorkflowConfig.SYMBOLS:
            outlook = await call_agent("oracle", f"/api/outlook/{symbol}")
            if outlook:
                macro_data[symbol] = outlook
        result.steps_completed += 1
        result.outputs["macro"] = macro_data
        
        # Step 4: Update event calendar
        logger.info("[A.4] Updating event calendar...")
        events = await call_agent("sentinel", "/api/events")
        blocked = await call_agent("sentinel", "/api/blocked")
        result.steps_completed += 1
        result.outputs["events"] = events
        result.outputs["blocked_windows"] = blocked
        
        # Step 5: Classify regime for all symbols
        logger.info("[A.5] Classifying regimes...")
        regimes = {}
        for symbol in WorkflowConfig.SYMBOLS:
            regime = await call_agent("compass", f"/api/regime/{symbol}")
            if regime:
                regimes[symbol] = regime
        result.steps_completed += 1
        result.outputs["regimes"] = regimes
        
        # Step 6: Generate watchlist
        logger.info("[A.6] Generating watchlist...")
        watchlist = []
        for symbol in WorkflowConfig.SYMBOLS:
            # Get quality check
            quality = await call_agent("curator", f"/api/quality/{symbol}")
            if not quality or quality.get("overall", 0) < WorkflowConfig.DATA_QUALITY_MINIMUM:
                continue
            
            # Get regime
            regime = regimes.get(symbol, {})
            if not regime.get("tradeable", True):
                continue
            
            # Check for setups
            setups = await call_agent("tactician", f"/api/setups/{symbol}")
            if setups and setups.get("setups"):
                for setup in setups["setups"]:
                    watchlist.append({
                        "symbol": symbol,
                        "setup": setup.get("template"),
                        "direction": setup.get("direction"),
                        "score": setup.get("score", 0),
                        "regime": regime.get("regime"),
                        "added_at": datetime.utcnow().isoformat()
                    })
        
        # Sort by score
        watchlist.sort(key=lambda x: x.get("score", 0), reverse=True)
        result.steps_completed += 1
        result.outputs["watchlist"] = watchlist[:10]  # Top 10
        
        # Update global state
        system_state.watchlist = watchlist[:10]
        system_state.last_market_open_prep = datetime.utcnow()
        
        result.status = WorkflowStatus.COMPLETED
        result.completed_at = datetime.utcnow()
        result.duration_seconds = (result.completed_at - result.started_at).total_seconds()
        
        logger.info(f"[A] Market Open Prep complete: {len(watchlist)} candidates on watchlist")
        
    except Exception as e:
        result.status = WorkflowStatus.FAILED
        result.errors.append(str(e))
        result.completed_at = datetime.utcnow()
        logger.error(f"[A] Market Open Prep failed: {e}")
    
    workflow_history.append(result)
    return result


# ═══════════════════════════════════════════════════════════════
# WORKFLOW B: CONTINUOUS INTRADAY SCAN
# ═══════════════════════════════════════════════════════════════

async def workflow_intraday_scan(notify_callback: Callable = None) -> WorkflowResult:
    """
    Continuous Intraday Scan Workflow
    Runs every N minutes to scan for new opportunities
    
    Steps:
    1. Scan all symbols for new data
    2. Update candidate setups
    3. Re-score all opportunities
    4. Notify if high-quality setup emerges
    """
    result = WorkflowResult(
        workflow="intraday_scan",
        status=WorkflowStatus.RUNNING,
        started_at=datetime.utcnow(),
        steps_total=4
    )
    
    try:
        # Check if trading is halted
        if system_state.trading_halted:
            result.status = WorkflowStatus.HALTED
            result.errors.append(f"Trading halted: {system_state.halt_reason}")
            return result
        
        # Step 1: Scan for new data
        logger.info("[B.1] Scanning symbols...")
        scan_results = {}
        for symbol in WorkflowConfig.SYMBOLS:
            quality = await call_agent("curator", f"/api/quality/{symbol}")
            scan_results[symbol] = {
                "quality": quality.get("overall", 0) if quality else 0,
                "tradeable": quality.get("overall", 0) >= WorkflowConfig.DATA_QUALITY_MINIMUM if quality else False
            }
        result.steps_completed += 1
        result.outputs["scan"] = scan_results
        
        # Step 2: Update candidate setups
        logger.info("[B.2] Finding setups...")
        candidates = []
        for symbol in WorkflowConfig.SYMBOLS:
            if not scan_results.get(symbol, {}).get("tradeable"):
                continue
            
            # Get regime
            regime = await call_agent("compass", f"/api/regime/{symbol}")
            if not regime or not regime.get("tradeable", True):
                continue
            
            # Get setups from Tactician
            setups = await call_agent("tactician", f"/api/setups/{symbol}")
            if setups and setups.get("setups"):
                for setup in setups["setups"]:
                    candidates.append({
                        "symbol": symbol,
                        "setup": setup.get("template"),
                        "direction": setup.get("direction"),
                        "entry": setup.get("entry"),
                        "stop": setup.get("stop"),
                        "targets": setup.get("targets", []),
                        "initial_score": setup.get("score", 0),
                        "regime": regime.get("regime"),
                    })
        result.steps_completed += 1
        result.outputs["candidates_found"] = len(candidates)
        
        # Step 3: Re-score opportunities through Nexus
        logger.info("[B.3] Scoring opportunities...")
        scored_candidates = []
        for candidate in candidates:
            confluence = await call_agent(
                "nexus", 
                f"/api/confluence/{candidate['symbol']}?direction={candidate['direction']}"
            )
            if confluence:
                candidate["confluence_score"] = confluence.get("confluence_score", 0)
                candidate["gates_passed"] = confluence.get("all_gates_passed", False)
                candidate["blocking_gates"] = [
                    g["gate"] for g in confluence.get("hard_gates", []) 
                    if not g.get("passed")
                ]
                scored_candidates.append(candidate)
        
        # Sort by confluence score
        scored_candidates.sort(key=lambda x: x.get("confluence_score", 0), reverse=True)
        result.steps_completed += 1
        result.outputs["scored_candidates"] = scored_candidates[:10]
        
        # Step 4: Notify on high-quality setups
        logger.info("[B.4] Checking for alerts...")
        high_quality = [
            c for c in scored_candidates 
            if c.get("confluence_score", 0) >= WorkflowConfig.HIGH_QUALITY_SETUP_SCORE
            and c.get("gates_passed")
        ]
        
        if high_quality and notify_callback:
            for setup in high_quality:
                await notify_callback({
                    "type": "high_quality_setup",
                    "symbol": setup["symbol"],
                    "direction": setup["direction"],
                    "score": setup["confluence_score"],
                    "setup": setup["setup"],
                    "timestamp": datetime.utcnow().isoformat()
                })
        
        result.steps_completed += 1
        result.outputs["high_quality_alerts"] = len(high_quality)
        result.outputs["high_quality_setups"] = high_quality
        
        # Update watchlist
        system_state.watchlist = scored_candidates[:10]
        
        result.status = WorkflowStatus.COMPLETED
        result.completed_at = datetime.utcnow()
        result.duration_seconds = (result.completed_at - result.started_at).total_seconds()
        
        logger.info(f"[B] Intraday Scan complete: {len(scored_candidates)} candidates, {len(high_quality)} high-quality")
        
    except Exception as e:
        result.status = WorkflowStatus.FAILED
        result.errors.append(str(e))
        result.completed_at = datetime.utcnow()
        logger.error(f"[B] Intraday Scan failed: {e}")
    
    workflow_history.append(result)
    return result


# ═══════════════════════════════════════════════════════════════
# WORKFLOW C: PRE-TRADE APPROVAL
# ═══════════════════════════════════════════════════════════════

async def workflow_pre_trade_approval(
    symbol: str, 
    direction: str, 
    entry: float,
    stop: float,
    targets: List[float],
    size: float = None,
    strategy: str = None
) -> WorkflowResult:
    """
    Pre-Trade Approval Workflow
    Full multi-agent approval before any trade execution
    
    Steps:
    1. Technical check (Atlas Jr.)
    2. Structure check (Architect)
    3. Macro check (Oracle)
    4. Sentiment check (Pulse)
    5. Event check (Sentinel)
    6. Portfolio check (Balancer)
    7. Risk check (Guardian)
    8. Execution feasibility check (Executor)
    9. Final decision
    """
    result = WorkflowResult(
        workflow="pre_trade_approval",
        status=WorkflowStatus.RUNNING,
        started_at=datetime.utcnow(),
        steps_total=9
    )
    
    result.outputs["request"] = {
        "symbol": symbol,
        "direction": direction,
        "entry": entry,
        "stop": stop,
        "targets": targets,
        "size": size,
        "strategy": strategy
    }
    
    approvals = {}
    vetoes = []
    
    try:
        # Check if trading is halted
        if system_state.trading_halted:
            result.status = WorkflowStatus.HALTED
            result.errors.append(f"Trading halted: {system_state.halt_reason}")
            result.outputs["decision"] = "REJECTED"
            result.outputs["reason"] = "Trading halted"
            return result
        
        # Step 1: Technical check
        logger.info(f"[C.1] Technical check for {symbol}...")
        technical = await call_agent("atlas", f"/api/analysis/{symbol}")
        if technical:
            tech_aligned = (
                (direction == "long" and technical.get("trend_direction") in ["bullish", "neutral"]) or
                (direction == "short" and technical.get("trend_direction") in ["bearish", "neutral"])
            )
            approvals["technical"] = {
                "approved": tech_aligned,
                "trend": technical.get("trend_direction"),
                "grade": technical.get("trend_grade"),
                "details": technical.get("supporting_evidence", [])[:3]
            }
            if not tech_aligned:
                vetoes.append(("technical", f"Trend is {technical.get('trend_direction')}, trade is {direction}"))
        result.steps_completed += 1
        
        # Step 2: Structure check
        logger.info(f"[C.2] Structure check for {symbol}...")
        structure = await call_agent("architect", f"/api/structure/{symbol}")
        if structure:
            # Check if entry is near key level
            levels = structure.get("key_levels", [])
            near_level = any(
                abs(entry - lvl.get("price", 0)) / entry < 0.002  # Within 0.2%
                for lvl in levels
            )
            approvals["structure"] = {
                "approved": True,  # Structure is informational
                "near_key_level": near_level,
                "market_structure": structure.get("structure"),
                "key_levels": levels[:3]
            }
        result.steps_completed += 1
        
        # Step 3: Macro check
        logger.info(f"[C.3] Macro check for {symbol}...")
        macro = await call_agent("oracle", f"/api/outlook/{symbol}")
        if macro:
            macro_aligned = (
                (direction == "long" and macro.get("bias") in ["bullish", "neutral"]) or
                (direction == "short" and macro.get("bias") in ["bearish", "neutral"])
            )
            approvals["macro"] = {
                "approved": macro_aligned,
                "bias": macro.get("bias"),
                "confidence": macro.get("confidence"),
                "key_factors": macro.get("key_factors", [])[:3]
            }
            # Macro doesn't veto, just informs
        result.steps_completed += 1
        
        # Step 4: Sentiment check
        logger.info(f"[C.4] Sentiment check for {symbol}...")
        sentiment = await call_agent("pulse", f"/api/sentiment/{symbol}")
        if sentiment:
            classification = sentiment.get("classification", "neutral")
            # Overcrowded = warning
            sentiment_warning = classification == "overcrowded"
            approvals["sentiment"] = {
                "approved": not sentiment_warning,
                "classification": classification,
                "crowding_score": sentiment.get("crowding_score"),
                "warning": "Overcrowded - consider reduced size" if sentiment_warning else None
            }
            if sentiment_warning:
                vetoes.append(("sentiment", "Market is overcrowded on this side"))
        result.steps_completed += 1
        
        # Step 5: Event check
        logger.info(f"[C.5] Event check for {symbol}...")
        event_risk = await call_agent("sentinel", f"/api/risk/{symbol}")
        if event_risk:
            blocked = event_risk.get("in_blocked_window", False)
            risk_level = event_risk.get("risk_level", "low")
            approvals["events"] = {
                "approved": not blocked,
                "blocked": blocked,
                "risk_level": risk_level,
                "upcoming_events": event_risk.get("upcoming_events", [])[:3]
            }
            if blocked:
                vetoes.append(("events", f"Symbol blocked due to {risk_level} event risk"))
        result.steps_completed += 1
        
        # Step 6: Portfolio check
        logger.info(f"[C.6] Portfolio check...")
        exposure = await call_agent("balancer", "/api/exposure")
        if exposure:
            exposure_score = exposure.get("exposure_score", 0)
            too_exposed = exposure_score > 80
            
            # Check currency concentration
            base, quote = symbol[:3], symbol[3:]
            currency_exposure = exposure.get("by_currency", {})
            
            approvals["portfolio"] = {
                "approved": not too_exposed,
                "exposure_score": exposure_score,
                "position_count": exposure.get("position_count", 0),
                "currency_exposure": {
                    base: currency_exposure.get(base, 0),
                    quote: currency_exposure.get(quote, 0)
                }
            }
            if too_exposed:
                vetoes.append(("portfolio", f"Portfolio exposure too high: {exposure_score}/100"))
        result.steps_completed += 1
        
        # Step 7: Risk check (Guardian has veto power)
        logger.info(f"[C.7] Risk check (Guardian)...")
        risk_request = {
            "symbol": symbol,
            "direction": direction,
            "entry": entry,
            "stop_loss": stop,
            "position_size": size
        }
        risk_check = await call_agent("guardian", "/api/approve", "POST", risk_request)
        if risk_check:
            approved = risk_check.get("approved", False)
            approvals["risk"] = {
                "approved": approved,
                "risk_mode": risk_check.get("risk_mode"),
                "position_size": risk_check.get("recommended_size"),
                "risk_percent": risk_check.get("risk_percent"),
                "block_reasons": risk_check.get("block_reasons", [])
            }
            if not approved:
                reasons = risk_check.get("block_reasons", ["Guardian rejected"])
                vetoes.append(("risk", "; ".join(reasons)))
        result.steps_completed += 1
        
        # Step 8: Execution feasibility check
        logger.info(f"[C.8] Execution feasibility check...")
        exec_check = await call_agent("executor", "/api/feasibility", "POST", {
            "symbol": symbol,
            "direction": direction,
            "entry": entry,
            "stop": stop
        })
        if exec_check:
            feasible = exec_check.get("feasible", False)
            approvals["execution"] = {
                "approved": feasible,
                "spread_ok": exec_check.get("spread_ok"),
                "current_spread": exec_check.get("current_spread"),
                "slippage_estimate": exec_check.get("slippage_estimate"),
                "issues": exec_check.get("issues", [])
            }
            if not feasible:
                vetoes.append(("execution", "; ".join(exec_check.get("issues", ["Not feasible"]))))
        result.steps_completed += 1
        
        # Step 9: Final decision
        logger.info(f"[C.9] Making final decision...")
        
        # Count approvals
        approved_count = sum(1 for a in approvals.values() if a.get("approved"))
        total_checks = len(approvals)
        
        # Check for any vetoes from veto-capable agents (Guardian, Sentinel)
        hard_vetoes = [v for v in vetoes if v[0] in ["risk", "events", "execution"]]
        
        if hard_vetoes:
            decision = "REJECTED"
            reason = f"Hard veto: {hard_vetoes[0][1]}"
        elif len(vetoes) >= 3:
            decision = "REJECTED"
            reason = f"Too many concerns: {len(vetoes)} vetoes"
        elif approved_count < total_checks * 0.6:
            decision = "REJECTED"
            reason = f"Insufficient approvals: {approved_count}/{total_checks}"
        else:
            decision = "APPROVED"
            reason = f"Passed {approved_count}/{total_checks} checks"
        
        result.steps_completed += 1
        result.outputs["approvals"] = approvals
        result.outputs["vetoes"] = vetoes
        result.outputs["decision"] = decision
        result.outputs["reason"] = reason
        result.outputs["recommended_size"] = approvals.get("risk", {}).get("position_size")
        
        result.status = WorkflowStatus.COMPLETED
        result.completed_at = datetime.utcnow()
        result.duration_seconds = (result.completed_at - result.started_at).total_seconds()
        
        logger.info(f"[C] Pre-Trade Approval: {decision} - {reason}")
        
    except Exception as e:
        result.status = WorkflowStatus.FAILED
        result.errors.append(str(e))
        result.outputs["decision"] = "REJECTED"
        result.outputs["reason"] = f"Workflow error: {e}"
        result.completed_at = datetime.utcnow()
        logger.error(f"[C] Pre-Trade Approval failed: {e}")
    
    workflow_history.append(result)
    return result


# ═══════════════════════════════════════════════════════════════
# WORKFLOW D: TRADE EXECUTION
# ═══════════════════════════════════════════════════════════════

async def workflow_trade_execution(
    symbol: str,
    direction: str,
    entry: float,
    stop: float,
    targets: List[float],
    size: float,
    strategy: str = None,
    skip_approval: bool = False
) -> WorkflowResult:
    """
    Trade Execution Workflow
    Execute a trade after approval
    
    Steps:
    1. Run pre-trade approval (if not skipped)
    2. Send order via Executor
    3. Validate broker response
    4. Log receipt in Chronicle
    5. Begin position monitoring
    """
    result = WorkflowResult(
        workflow="trade_execution",
        status=WorkflowStatus.RUNNING,
        started_at=datetime.utcnow(),
        steps_total=5
    )
    
    result.outputs["request"] = {
        "symbol": symbol,
        "direction": direction,
        "entry": entry,
        "stop": stop,
        "targets": targets,
        "size": size,
        "strategy": strategy
    }
    
    try:
        # Step 1: Pre-trade approval
        if not skip_approval:
            logger.info(f"[D.1] Running pre-trade approval...")
            approval = await workflow_pre_trade_approval(
                symbol, direction, entry, stop, targets, size, strategy
            )
            result.outputs["approval"] = approval.to_dict()
            
            if approval.outputs.get("decision") != "APPROVED":
                result.status = WorkflowStatus.COMPLETED
                result.outputs["executed"] = False
                result.outputs["reason"] = approval.outputs.get("reason", "Not approved")
                result.completed_at = datetime.utcnow()
                return result
            
            # Use recommended size if provided
            if approval.outputs.get("recommended_size"):
                size = approval.outputs["recommended_size"]
        else:
            logger.info(f"[D.1] Skipping approval (pre-approved)")
        result.steps_completed += 1
        
        # Step 2: Send order
        logger.info(f"[D.2] Sending order to Executor...")
        order_request = {
            "symbol": symbol,
            "side": "buy" if direction == "long" else "sell",
            "volume": size,
            "entry_price": entry,
            "stop_loss": stop,
            "take_profits": targets,
            "strategy": strategy or "manual",
            "mode": system_state.trading_mode
        }
        
        order_response = await call_agent("executor", "/api/execute", "POST", order_request)
        result.steps_completed += 1
        
        if not order_response:
            result.status = WorkflowStatus.FAILED
            result.errors.append("No response from Executor")
            result.outputs["executed"] = False
            result.completed_at = datetime.utcnow()
            return result
        
        result.outputs["order_response"] = order_response
        
        # Step 3: Validate broker response
        logger.info(f"[D.3] Validating broker response...")
        execution_successful = order_response.get("status") in ["filled", "pending", "success"]
        
        if not execution_successful:
            result.status = WorkflowStatus.FAILED
            result.errors.append(f"Execution failed: {order_response.get('error', 'Unknown error')}")
            result.outputs["executed"] = False
            result.completed_at = datetime.utcnow()
            return result
        
        result.outputs["ticket"] = order_response.get("ticket")
        result.outputs["fill_price"] = order_response.get("fill_price", entry)
        result.outputs["executed"] = True
        result.steps_completed += 1
        
        # Step 4: Log receipt in Chronicle
        logger.info(f"[D.4] Logging trade in Chronicle...")
        trade_log = {
            "symbol": symbol,
            "side": direction,
            "entry_price": order_response.get("fill_price", entry),
            "stop_loss": stop,
            "take_profit": targets[0] if targets else None,
            "volume": size,
            "strategy_family": strategy,
            "ticket": order_response.get("ticket"),
            "mode": system_state.trading_mode
        }
        
        journal_response = await call_agent("chronicle", "/api/trades", "POST", trade_log)
        result.outputs["journal_id"] = journal_response.get("trade_id") if journal_response else None
        result.steps_completed += 1
        
        # Step 5: Register for position monitoring
        logger.info(f"[D.5] Registering for monitoring...")
        system_state.active_positions.append({
            "ticket": order_response.get("ticket"),
            "symbol": symbol,
            "direction": direction,
            "entry": order_response.get("fill_price", entry),
            "stop": stop,
            "targets": targets,
            "opened_at": datetime.utcnow().isoformat()
        })
        result.steps_completed += 1
        
        result.status = WorkflowStatus.COMPLETED
        result.completed_at = datetime.utcnow()
        result.duration_seconds = (result.completed_at - result.started_at).total_seconds()
        
        logger.info(f"[D] Trade Execution complete: {symbol} {direction} @ {result.outputs.get('fill_price')}")
        
    except Exception as e:
        result.status = WorkflowStatus.FAILED
        result.errors.append(str(e))
        result.outputs["executed"] = False
        result.completed_at = datetime.utcnow()
        logger.error(f"[D] Trade Execution failed: {e}")
    
    workflow_history.append(result)
    return result


# ═══════════════════════════════════════════════════════════════
# WORKFLOW E: ACTIVE POSITION MANAGEMENT
# ═══════════════════════════════════════════════════════════════

async def workflow_position_management(position: dict) -> WorkflowResult:
    """
    Active Position Management Workflow
    Monitor and manage an open position
    
    Steps:
    1. Monitor thesis health
    2. Check stop movement rules
    3. Check scale-out rules
    4. Check exit conditions
    5. Execute any required actions
    """
    result = WorkflowResult(
        workflow="position_management",
        status=WorkflowStatus.RUNNING,
        started_at=datetime.utcnow(),
        steps_total=5
    )
    
    symbol = position.get("symbol")
    direction = position.get("direction")
    entry = position.get("entry")
    current_stop = position.get("stop")
    targets = position.get("targets", [])
    ticket = position.get("ticket")
    
    result.outputs["position"] = position
    actions_taken = []
    
    try:
        # Step 1: Monitor thesis health
        logger.info(f"[E.1] Checking thesis health for {symbol}...")
        
        # Get current technical state
        technical = await call_agent("atlas", f"/api/analysis/{symbol}")
        regime = await call_agent("compass", f"/api/regime/{symbol}")
        
        thesis_health = 100  # Start at full health
        health_concerns = []
        
        if technical:
            # Check if trend still supports position
            trend = technical.get("trend_direction")
            if direction == "long" and trend == "bearish":
                thesis_health -= 40
                health_concerns.append("Trend turned bearish")
            elif direction == "short" and trend == "bullish":
                thesis_health -= 40
                health_concerns.append("Trend turned bullish")
        
        if regime:
            # Check if regime changed unfavorably
            current_regime = regime.get("regime")
            if current_regime in ["high_volatility", "choppy"]:
                thesis_health -= 20
                health_concerns.append(f"Regime changed to {current_regime}")
        
        result.outputs["thesis_health"] = thesis_health
        result.outputs["health_concerns"] = health_concerns
        result.steps_completed += 1
        
        # Step 2: Check stop movement rules
        logger.info(f"[E.2] Checking stop movement rules...")
        
        # Get current price
        snapshot = await call_agent("curator", f"/api/snapshot/price/{symbol}")
        current_price = snapshot.get("price") if snapshot else None
        
        new_stop = current_stop
        if current_price:
            # Calculate current R
            risk = abs(entry - current_stop)
            if direction == "long":
                current_r = (current_price - entry) / risk if risk > 0 else 0
            else:
                current_r = (entry - current_price) / risk if risk > 0 else 0
            
            result.outputs["current_r"] = current_r
            
            # Move stop to breakeven at +1R
            if current_r >= 1.0:
                if direction == "long" and current_stop < entry:
                    new_stop = entry
                    actions_taken.append({"action": "move_stop_to_breakeven", "new_stop": entry})
                elif direction == "short" and current_stop > entry:
                    new_stop = entry
                    actions_taken.append({"action": "move_stop_to_breakeven", "new_stop": entry})
            
            # Trail stop at +2R (lock in 1R)
            if current_r >= 2.0:
                if direction == "long":
                    trail_stop = entry + risk  # Lock in 1R
                    if trail_stop > new_stop:
                        new_stop = trail_stop
                        actions_taken.append({"action": "trail_stop", "new_stop": trail_stop, "locked_r": 1.0})
                else:
                    trail_stop = entry - risk
                    if trail_stop < new_stop:
                        new_stop = trail_stop
                        actions_taken.append({"action": "trail_stop", "new_stop": trail_stop, "locked_r": 1.0})
        
        result.outputs["new_stop"] = new_stop
        result.steps_completed += 1
        
        # Step 3: Check scale-out rules
        logger.info(f"[E.3] Checking scale-out rules...")
        
        scale_out_actions = []
        if current_price and targets:
            # Check if we hit any targets
            for i, target in enumerate(targets):
                hit = (direction == "long" and current_price >= target) or \
                      (direction == "short" and current_price <= target)
                if hit:
                    scale_out_actions.append({
                        "action": "partial_close",
                        "target_index": i + 1,
                        "target_price": target,
                        "percent": 33 if i == 0 else 50  # 33% at TP1, 50% at TP2
                    })
        
        if scale_out_actions:
            actions_taken.extend(scale_out_actions)
        result.outputs["scale_out_checks"] = scale_out_actions
        result.steps_completed += 1
        
        # Step 4: Check exit conditions
        logger.info(f"[E.4] Checking exit conditions...")
        
        should_exit = False
        exit_reason = None
        
        # Exit on thesis invalidation (health < 40%)
        if thesis_health < 40:
            should_exit = True
            exit_reason = f"Thesis invalidated: {', '.join(health_concerns)}"
        
        # Exit on event risk
        event_risk = await call_agent("sentinel", f"/api/risk/{symbol}")
        if event_risk and event_risk.get("in_blocked_window"):
            should_exit = True
            exit_reason = "Major event risk - exiting before event"
        
        # Exit on Guardian halt
        guardian_status = await call_agent("guardian", "/api/status")
        if guardian_status and guardian_status.get("kill_switch"):
            should_exit = True
            exit_reason = "Guardian kill switch activated"
        
        result.outputs["should_exit"] = should_exit
        result.outputs["exit_reason"] = exit_reason
        result.steps_completed += 1
        
        # Step 5: Execute actions
        logger.info(f"[E.5] Executing actions...")
        
        executed_actions = []
        
        # Modify stop if changed
        if new_stop != current_stop:
            modify_result = await call_agent("executor", "/api/modify", "POST", {
                "ticket": ticket,
                "stop_loss": new_stop
            })
            if modify_result and modify_result.get("success"):
                executed_actions.append({"type": "stop_modified", "new_stop": new_stop})
                position["stop"] = new_stop
        
        # Execute scale-outs
        for scale_action in scale_out_actions:
            close_result = await call_agent("executor", "/api/partial_close", "POST", {
                "ticket": ticket,
                "percent": scale_action["percent"]
            })
            if close_result and close_result.get("success"):
                executed_actions.append({
                    "type": "partial_close",
                    "percent": scale_action["percent"],
                    "price": scale_action["target_price"]
                })
        
        # Full exit if required
        if should_exit:
            close_result = await call_agent("executor", "/api/close", "POST", {
                "ticket": ticket,
                "reason": exit_reason
            })
            if close_result and close_result.get("success"):
                executed_actions.append({"type": "full_close", "reason": exit_reason})
                # Remove from active positions
                system_state.active_positions = [
                    p for p in system_state.active_positions 
                    if p.get("ticket") != ticket
                ]
        
        result.outputs["actions_taken"] = actions_taken
        result.outputs["executed_actions"] = executed_actions
        result.steps_completed += 1
        
        result.status = WorkflowStatus.COMPLETED
        result.completed_at = datetime.utcnow()
        result.duration_seconds = (result.completed_at - result.started_at).total_seconds()
        
        logger.info(f"[E] Position Management: {len(executed_actions)} actions executed")
        
    except Exception as e:
        result.status = WorkflowStatus.FAILED
        result.errors.append(str(e))
        result.completed_at = datetime.utcnow()
        logger.error(f"[E] Position Management failed: {e}")
    
    workflow_history.append(result)
    return result


# ═══════════════════════════════════════════════════════════════
# WORKFLOW F: END-OF-DAY REVIEW
# ═══════════════════════════════════════════════════════════════

async def workflow_eod_review() -> WorkflowResult:
    """
    End-of-Day Review Workflow
    Summarize the trading day
    
    Steps:
    1. Summarize all decisions made
    2. List trades taken
    3. List trades rejected (and why)
    4. Identify missed opportunities
    5. Compute daily performance metrics
    6. Generate journal notes
    """
    result = WorkflowResult(
        workflow="eod_review",
        status=WorkflowStatus.RUNNING,
        started_at=datetime.utcnow(),
        steps_total=6
    )
    
    today = datetime.utcnow().strftime("%Y-%m-%d")
    
    try:
        # Step 1: Summarize decisions
        logger.info(f"[F.1] Summarizing decisions...")
        
        decisions = await call_agent("nexus", f"/api/decisions?date={today}")
        decision_summary = {
            "total": len(decisions.get("decisions", [])) if decisions else 0,
            "executed": 0,
            "watchlist": 0,
            "rejected": 0
        }
        
        if decisions:
            for d in decisions.get("decisions", []):
                if d.get("decision") == "EXECUTE":
                    decision_summary["executed"] += 1
                elif d.get("decision") == "WATCHLIST":
                    decision_summary["watchlist"] += 1
                else:
                    decision_summary["rejected"] += 1
        
        result.outputs["decision_summary"] = decision_summary
        result.steps_completed += 1
        
        # Step 2: List trades taken
        logger.info(f"[F.2] Listing trades taken...")
        
        trades = await call_agent("chronicle", f"/api/trades?date={today}")
        trades_taken = []
        
        if trades:
            for t in trades.get("trades", []):
                trades_taken.append({
                    "symbol": t.get("symbol"),
                    "side": t.get("side"),
                    "entry": t.get("entry_price"),
                    "exit": t.get("close_price"),
                    "result_r": t.get("result_r", 0),
                    "pnl": t.get("pnl", 0),
                    "strategy": t.get("strategy_family"),
                    "status": t.get("status")
                })
        
        result.outputs["trades_taken"] = trades_taken
        result.outputs["trades_count"] = len(trades_taken)
        result.steps_completed += 1
        
        # Step 3: List rejected trades
        logger.info(f"[F.3] Listing rejected trades...")
        
        rejected_trades = []
        if decisions:
            for d in decisions.get("decisions", []):
                if d.get("decision") in ["NO_TRADE", "REJECTED"]:
                    rejected_trades.append({
                        "symbol": d.get("symbol"),
                        "direction": d.get("direction"),
                        "score": d.get("confluence_score"),
                        "reason": d.get("reason"),
                        "blocking_gates": d.get("blocking_gates", [])
                    })
        
        result.outputs["rejected_trades"] = rejected_trades
        result.steps_completed += 1
        
        # Step 4: Identify missed opportunities
        logger.info(f"[F.4] Identifying missed opportunities...")
        
        # Get symbols that moved significantly today
        missed = []
        for symbol in WorkflowConfig.SYMBOLS:
            # Get daily range
            candles = await call_agent("curator", f"/api/candles/{symbol}/D1?limit=1")
            if candles and candles.get("candles"):
                candle = candles["candles"][0]
                high = candle.get("high", 0)
                low = candle.get("low", 0)
                open_price = candle.get("open", 0)
                close = candle.get("close", 0)
                
                # Calculate movement
                range_pips = (high - low) * (10000 if "JPY" not in symbol else 100)
                direction = "bullish" if close > open_price else "bearish"
                
                # Check if we traded this symbol
                traded = any(t["symbol"] == symbol for t in trades_taken)
                
                # If big move (>50 pips) and we didn't trade
                if range_pips > 50 and not traded:
                    # Check if it was in watchlist
                    was_watchlist = any(
                        d["symbol"] == symbol and d.get("decision") == "WATCHLIST"
                        for d in decisions.get("decisions", [])
                    ) if decisions else False
                    
                    if was_watchlist:
                        missed.append({
                            "symbol": symbol,
                            "direction": direction,
                            "range_pips": round(range_pips, 1),
                            "reason": "Was on watchlist but not executed"
                        })
        
        result.outputs["missed_opportunities"] = missed
        result.steps_completed += 1
        
        # Step 5: Compute performance metrics
        logger.info(f"[F.5] Computing performance metrics...")
        
        daily_metrics = {
            "total_trades": len(trades_taken),
            "winners": sum(1 for t in trades_taken if t.get("result_r", 0) > 0),
            "losers": sum(1 for t in trades_taken if t.get("result_r", 0) < 0),
            "total_r": sum(t.get("result_r", 0) for t in trades_taken),
            "total_pnl": sum(t.get("pnl", 0) for t in trades_taken),
            "best_trade": max((t.get("result_r", 0) for t in trades_taken), default=0),
            "worst_trade": min((t.get("result_r", 0) for t in trades_taken), default=0),
        }
        
        if daily_metrics["total_trades"] > 0:
            daily_metrics["win_rate"] = daily_metrics["winners"] / daily_metrics["total_trades"] * 100
            daily_metrics["avg_r"] = daily_metrics["total_r"] / daily_metrics["total_trades"]
        else:
            daily_metrics["win_rate"] = 0
            daily_metrics["avg_r"] = 0
        
        result.outputs["daily_metrics"] = daily_metrics
        
        # Update system state
        system_state.daily_pnl = daily_metrics["total_pnl"]
        result.steps_completed += 1
        
        # Step 6: Generate journal notes
        logger.info(f"[F.6] Generating journal notes...")
        
        journal_entry = {
            "date": today,
            "summary": f"Trades: {daily_metrics['total_trades']} | "
                      f"Win Rate: {daily_metrics['win_rate']:.1f}% | "
                      f"P&L: {daily_metrics['total_r']:.2f}R (${daily_metrics['total_pnl']:.2f})",
            "trades_taken": len(trades_taken),
            "trades_rejected": len(rejected_trades),
            "missed_opportunities": len(missed),
            "key_observations": [],
            "improvements": []
        }
        
        # Add observations
        if daily_metrics["total_trades"] == 0:
            journal_entry["key_observations"].append("No trades taken - was market opportunity lacking or were we too cautious?")
        if len(rejected_trades) > 5:
            journal_entry["key_observations"].append(f"High rejection rate ({len(rejected_trades)} rejected) - review criteria")
        if missed:
            journal_entry["key_observations"].append(f"Missed {len(missed)} significant moves - review watchlist → execution flow")
        
        # Save to Chronicle
        await call_agent("chronicle", "/api/journal", "POST", journal_entry)
        
        result.outputs["journal_entry"] = journal_entry
        result.steps_completed += 1
        
        # Update state
        system_state.last_eod_review = datetime.utcnow()
        
        result.status = WorkflowStatus.COMPLETED
        result.completed_at = datetime.utcnow()
        result.duration_seconds = (result.completed_at - result.started_at).total_seconds()
        
        logger.info(f"[F] EOD Review complete: {daily_metrics['total_trades']} trades, {daily_metrics['total_r']:.2f}R")
        
    except Exception as e:
        result.status = WorkflowStatus.FAILED
        result.errors.append(str(e))
        result.completed_at = datetime.utcnow()
        logger.error(f"[F] EOD Review failed: {e}")
    
    workflow_history.append(result)
    return result


# ═══════════════════════════════════════════════════════════════
# WORKFLOW G: WEEKLY STRATEGY REVIEW
# ═══════════════════════════════════════════════════════════════

async def workflow_weekly_review() -> WorkflowResult:
    """
    Weekly Strategy Review Workflow
    Deep analysis and improvement proposals
    
    Steps:
    1. Analyze results by regime
    2. Analyze results by strategy
    3. Identify weaknesses
    4. Propose changes
    5. Queue validation tasks
    """
    result = WorkflowResult(
        workflow="weekly_review",
        status=WorkflowStatus.RUNNING,
        started_at=datetime.utcnow(),
        steps_total=5
    )
    
    try:
        # Step 1: Analyze by regime
        logger.info(f"[G.1] Analyzing by regime...")
        
        analytics = await call_agent("insight", "/api/analytics")
        
        by_regime = {}
        if analytics:
            by_regime = analytics.get("by_regime", {})
        
        result.outputs["by_regime"] = by_regime
        result.steps_completed += 1
        
        # Step 2: Analyze by strategy
        logger.info(f"[G.2] Analyzing by strategy...")
        
        by_strategy = {}
        if analytics:
            by_strategy = analytics.get("by_strategy", {})
        
        result.outputs["by_strategy"] = by_strategy
        result.steps_completed += 1
        
        # Step 3: Identify weaknesses
        logger.info(f"[G.3] Identifying weaknesses...")
        
        weaknesses = []
        
        # Check each regime
        for regime, stats in by_regime.items():
            if stats.get("win_rate", 50) < 40:
                weaknesses.append({
                    "type": "regime",
                    "area": regime,
                    "metric": "win_rate",
                    "value": stats.get("win_rate"),
                    "severity": "high" if stats.get("win_rate", 50) < 30 else "medium"
                })
            if stats.get("expectancy", 0) < 0:
                weaknesses.append({
                    "type": "regime",
                    "area": regime,
                    "metric": "expectancy",
                    "value": stats.get("expectancy"),
                    "severity": "high"
                })
        
        # Check each strategy
        for strategy, stats in by_strategy.items():
            if stats.get("total_r", 0) < -5:
                weaknesses.append({
                    "type": "strategy",
                    "area": strategy,
                    "metric": "total_r",
                    "value": stats.get("total_r"),
                    "severity": "high"
                })
            if stats.get("trade_count", 0) > 10 and stats.get("win_rate", 50) < 35:
                weaknesses.append({
                    "type": "strategy",
                    "area": strategy,
                    "metric": "win_rate",
                    "value": stats.get("win_rate"),
                    "severity": "medium"
                })
        
        result.outputs["weaknesses"] = weaknesses
        result.steps_completed += 1
        
        # Step 4: Propose changes
        logger.info(f"[G.4] Proposing changes...")
        
        proposals = []
        
        for weakness in weaknesses:
            if weakness["severity"] == "high":
                if weakness["type"] == "regime":
                    proposals.append({
                        "type": "regime_filter",
                        "action": f"Reduce or disable trading in {weakness['area']} regime",
                        "reason": f"{weakness['metric']} at {weakness['value']}",
                        "priority": "high"
                    })
                elif weakness["type"] == "strategy":
                    proposals.append({
                        "type": "strategy_review",
                        "action": f"Review and potentially disable {weakness['area']} strategy",
                        "reason": f"{weakness['metric']} at {weakness['value']}",
                        "priority": "high"
                    })
        
        # Check for edge decay
        if analytics:
            edge_status = analytics.get("edge_status", {})
            if edge_status.get("status") == "decaying":
                proposals.append({
                    "type": "system_review",
                    "action": "Overall edge appears to be decaying - full system review needed",
                    "reason": f"Recent expectancy: {edge_status.get('recent_expectancy')}",
                    "priority": "critical"
                })
        
        result.outputs["proposals"] = proposals
        result.steps_completed += 1
        
        # Step 5: Queue validation tasks
        logger.info(f"[G.5] Queuing validation tasks...")
        
        validation_tasks = []
        
        for proposal in proposals:
            if proposal["priority"] in ["high", "critical"]:
                # Create change request for Arbiter
                change_request = {
                    "strategy_name": proposal.get("action", "unknown"),
                    "change_type": proposal["type"],
                    "description": proposal["reason"],
                    "proposed_by": "weekly_review_workflow"
                }
                
                arbiter_response = await call_agent("arbiter", "/api/request", "POST", change_request)
                
                if arbiter_response:
                    validation_tasks.append({
                        "request_id": arbiter_response.get("request_id"),
                        "proposal": proposal,
                        "status": "queued"
                    })
        
        result.outputs["validation_tasks"] = validation_tasks
        result.steps_completed += 1
        
        # Update state
        system_state.last_weekly_review = datetime.utcnow()
        
        result.status = WorkflowStatus.COMPLETED
        result.completed_at = datetime.utcnow()
        result.duration_seconds = (result.completed_at - result.started_at).total_seconds()
        
        logger.info(f"[G] Weekly Review complete: {len(weaknesses)} weaknesses, {len(proposals)} proposals")
        
    except Exception as e:
        result.status = WorkflowStatus.FAILED
        result.errors.append(str(e))
        result.completed_at = datetime.utcnow()
        logger.error(f"[G] Weekly Review failed: {e}")
    
    workflow_history.append(result)
    return result


# ═══════════════════════════════════════════════════════════════
# WORKFLOW H: INCIDENT RESPONSE
# ═══════════════════════════════════════════════════════════════

async def workflow_incident_response(
    incident_type: str = None,
    auto_detect: bool = True
) -> WorkflowResult:
    """
    Incident Response Workflow
    Handle system issues and halt trading when necessary
    
    Incident Types:
    - mt5_disconnect: MT5 connection lost
    - data_corruption: Data feed issues
    - drawdown_breach: Exceeded drawdown limits
    - event_risk: Major event risk spike
    - system_error: General system error
    """
    result = WorkflowResult(
        workflow="incident_response",
        status=WorkflowStatus.RUNNING,
        started_at=datetime.utcnow(),
        steps_total=4
    )
    
    detected_incidents = []
    
    try:
        # Step 1: Detect incidents (if auto-detect)
        if auto_detect:
            logger.info(f"[H.1] Detecting incidents...")
            
            # Check MT5 connection via Curator (which has MT5 files mounted)
            bridge_status = await call_agent("curator", "/api/bridge")
            if bridge_status:
                if bridge_status.get("status") != "READY":
                    detected_incidents.append({
                        "type": "mt5_disconnect",
                        "severity": "critical",
                        "details": f"Bridge status: {bridge_status.get('status', 'UNKNOWN')} - {bridge_status.get('message', '')}"
                    })
            else:
                detected_incidents.append({
                    "type": "mt5_disconnect",
                    "severity": "critical",
                    "details": "Cannot reach Curator agent for bridge status"
                })
            
            # Check data feed
            curator_status = await call_agent("curator", "/api/status")
            if curator_status:
                avg_quality_raw = curator_status.get("avg_quality", 1.0)
                # Curator returns 0-1 scale, convert to percentage
                avg_quality = avg_quality_raw * 100 if avg_quality_raw <= 1 else avg_quality_raw
                if avg_quality < 50:
                    detected_incidents.append({
                        "type": "data_corruption",
                        "severity": "high",
                        "details": f"Data quality: {avg_quality:.1f}%"
                    })
            
            # Check drawdown
            guardian_status = await call_agent("guardian", "/api/status")
            if guardian_status:
                daily_dd = guardian_status.get("daily_drawdown_pct", 0)
                weekly_dd = guardian_status.get("weekly_drawdown_pct", 0)
                
                if daily_dd >= WorkflowConfig.MAX_DRAWDOWN_DAILY:
                    detected_incidents.append({
                        "type": "drawdown_breach",
                        "severity": "critical",
                        "details": f"Daily drawdown: {daily_dd}% (limit: {WorkflowConfig.MAX_DRAWDOWN_DAILY}%)"
                    })
                elif weekly_dd >= WorkflowConfig.MAX_DRAWDOWN_WEEKLY:
                    detected_incidents.append({
                        "type": "drawdown_breach",
                        "severity": "critical",
                        "details": f"Weekly drawdown: {weekly_dd}% (limit: {WorkflowConfig.MAX_DRAWDOWN_WEEKLY}%)"
                    })
            
            # Check event risk
            sentinel_status = await call_agent("sentinel", "/api/status")
            if sentinel_status:
                if sentinel_status.get("global_risk_level") == "extreme":
                    detected_incidents.append({
                        "type": "event_risk",
                        "severity": "high",
                        "details": "Extreme global event risk"
                    })
        
        # Add manual incident if specified
        if incident_type:
            detected_incidents.append({
                "type": incident_type,
                "severity": "critical",
                "details": "Manually triggered"
            })
        
        result.outputs["detected_incidents"] = detected_incidents
        result.steps_completed += 1
        
        # Step 2: Determine response action
        logger.info(f"[H.2] Determining response...")
        
        response_action = "none"
        halt_trading = False
        close_positions = False
        
        critical_incidents = [i for i in detected_incidents if i["severity"] == "critical"]
        high_incidents = [i for i in detected_incidents if i["severity"] == "high"]
        
        if critical_incidents:
            response_action = "halt_and_close"
            halt_trading = True
            close_positions = True
        elif high_incidents:
            response_action = "halt_new_trades"
            halt_trading = True
            close_positions = False
        
        result.outputs["response_action"] = response_action
        result.outputs["halt_trading"] = halt_trading
        result.outputs["close_positions"] = close_positions
        result.steps_completed += 1
        
        # Step 3: Execute response
        logger.info(f"[H.3] Executing response: {response_action}...")
        
        actions_taken = []
        
        if halt_trading:
            # Halt via Guardian
            await call_agent("guardian", "/api/halt", "POST", {
                "reason": "; ".join([i["details"] for i in detected_incidents])
            })
            system_state.trading_halted = True
            system_state.halt_reason = detected_incidents[0]["details"] if detected_incidents else "Unknown"
            actions_taken.append("trading_halted")
        
        if close_positions:
            # Close all positions
            close_result = await call_agent("executor", "/api/close_all", "POST", {
                "reason": "Incident response"
            })
            if close_result and close_result.get("success"):
                actions_taken.append(f"closed_{close_result.get('count', 0)}_positions")
                system_state.active_positions = []
        
        result.outputs["actions_taken"] = actions_taken
        result.steps_completed += 1
        
        # Step 4: Log incident
        logger.info(f"[H.4] Logging incident...")
        
        incident_log = {
            "timestamp": datetime.utcnow().isoformat(),
            "incidents": detected_incidents,
            "response_action": response_action,
            "actions_taken": actions_taken,
            "trading_halted": halt_trading
        }
        
        # Log to Chronicle
        await call_agent("chronicle", "/api/incident", "POST", incident_log)
        
        # Add to system state
        system_state.incidents.append(incident_log)
        
        result.outputs["incident_log"] = incident_log
        result.steps_completed += 1
        
        result.status = WorkflowStatus.COMPLETED
        result.completed_at = datetime.utcnow()
        result.duration_seconds = (result.completed_at - result.started_at).total_seconds()
        
        logger.info(f"[H] Incident Response complete: {len(detected_incidents)} incidents, action={response_action}")
        
    except Exception as e:
        result.status = WorkflowStatus.FAILED
        result.errors.append(str(e))
        result.completed_at = datetime.utcnow()
        logger.error(f"[H] Incident Response failed: {e}")
    
    workflow_history.append(result)
    return result


# ═══════════════════════════════════════════════════════════════
# WORKFLOW SCHEDULER
# ═══════════════════════════════════════════════════════════════

class WorkflowScheduler:
    """Manages scheduled and continuous workflows."""
    
    def __init__(self):
        self.running = False
        self.tasks: Dict[str, asyncio.Task] = {}
        self.notify_callback: Callable = None
    
    def set_notify_callback(self, callback: Callable):
        """Set callback for notifications."""
        self.notify_callback = callback
    
    async def start(self):
        """Start all scheduled workflows."""
        self.running = True
        logger.info("Starting workflow scheduler...")
        
        # Start continuous tasks
        self.tasks["intraday_scan"] = asyncio.create_task(
            self._run_periodic(
                workflow_intraday_scan,
                WorkflowConfig.INTRADAY_SCAN_INTERVAL_SECONDS,
                "intraday_scan"
            )
        )
        
        self.tasks["position_monitor"] = asyncio.create_task(
            self._run_position_monitor()
        )
        
        self.tasks["incident_monitor"] = asyncio.create_task(
            self._run_periodic(
                lambda: workflow_incident_response(auto_detect=True),
                60,  # Check every minute
                "incident_monitor"
            )
        )
        
        logger.info("Workflow scheduler started")
    
    async def stop(self):
        """Stop all scheduled workflows."""
        self.running = False
        for name, task in self.tasks.items():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self.tasks.clear()
        logger.info("Workflow scheduler stopped")
    
    async def _run_periodic(self, workflow_func: Callable, interval_seconds: int, name: str):
        """Run a workflow periodically."""
        while self.running:
            try:
                if self.notify_callback and name == "intraday_scan":
                    await workflow_func(notify_callback=self.notify_callback)
                else:
                    await workflow_func()
            except Exception as e:
                logger.error(f"Error in periodic workflow {name}: {e}")
            
            await asyncio.sleep(interval_seconds)
    
    async def _run_position_monitor(self):
        """Monitor active positions."""
        while self.running:
            try:
                for position in system_state.active_positions.copy():
                    await workflow_position_management(position)
            except Exception as e:
                logger.error(f"Error in position monitor: {e}")
            
            await asyncio.sleep(WorkflowConfig.POSITION_MONITOR_INTERVAL_SECONDS)
    
    async def trigger(self, workflow_name: str, **kwargs) -> Optional[WorkflowResult]:
        """Manually trigger a workflow."""
        workflows = {
            "market_open_prep": workflow_market_open_prep,
            "intraday_scan": workflow_intraday_scan,
            "pre_trade_approval": workflow_pre_trade_approval,
            "trade_execution": workflow_trade_execution,
            "position_management": workflow_position_management,
            "eod_review": workflow_eod_review,
            "weekly_review": workflow_weekly_review,
            "incident_response": workflow_incident_response,
        }
        
        if workflow_name not in workflows:
            logger.error(f"Unknown workflow: {workflow_name}")
            return None
        
        return await workflows[workflow_name](**kwargs)


# Global scheduler instance
scheduler = WorkflowScheduler()


# ═══════════════════════════════════════════════════════════════
# API ENDPOINTS (for integration with Orchestrator)
# ═══════════════════════════════════════════════════════════════

def get_workflow_api_routes():
    """Return FastAPI routes for workflow management."""
    from fastapi import APIRouter
    
    router = APIRouter(prefix="/api/workflows", tags=["workflows"])
    
    @router.get("/status")
    async def workflow_status():
        return {
            "scheduler_running": scheduler.running,
            "active_tasks": list(scheduler.tasks.keys()),
            "system_state": {
                "trading_mode": system_state.trading_mode,
                "trading_halted": system_state.trading_halted,
                "halt_reason": system_state.halt_reason,
                "active_positions": len(system_state.active_positions),
                "watchlist_size": len(system_state.watchlist),
                "daily_pnl": system_state.daily_pnl,
            },
            "recent_workflows": [w.to_dict() for w in workflow_history[-10:]]
        }
    
    @router.post("/trigger/{workflow_name}")
    async def trigger_workflow(workflow_name: str, params: dict = None):
        result = await scheduler.trigger(workflow_name, **(params or {}))
        if result:
            return result.to_dict()
        return {"error": f"Unknown workflow: {workflow_name}"}
    
    @router.post("/start")
    async def start_scheduler():
        await scheduler.start()
        return {"status": "started"}
    
    @router.post("/stop")
    async def stop_scheduler():
        await scheduler.stop()
        return {"status": "stopped"}
    
    @router.get("/history")
    async def workflow_history_endpoint(limit: int = 20):
        return {
            "workflows": [w.to_dict() for w in workflow_history[-limit:]]
        }
    
    @router.post("/halt")
    async def halt_trading(reason: str = "Manual halt"):
        system_state.trading_halted = True
        system_state.halt_reason = reason
        return {"status": "halted", "reason": reason}
    
    @router.post("/resume")
    async def resume_trading():
        system_state.trading_halted = False
        system_state.halt_reason = None
        return {"status": "resumed"}
    
    @router.get("/watchlist")
    async def get_watchlist():
        return {"watchlist": system_state.watchlist}
    
    @router.get("/positions")
    async def get_positions():
        return {"positions": system_state.active_positions}
    
    return router


if __name__ == "__main__":
    # Test workflow execution
    async def test():
        print("Testing Market Open Prep...")
        result = await workflow_market_open_prep()
        print(f"Result: {result.status.value}")
        print(f"Watchlist: {result.outputs.get('watchlist', [])}")
    
    asyncio.run(test())
