"""
Orchestrator / CIO Agent
========================
The ONLY agent authorized to approve trades.

From 04_SUPERVISOR_ORCHESTRATOR.txt:
This is the brain. It synthesizes all inputs, applies hard gates, computes
confluence scores, checks vetoes, and makes the final BUY/SELL/NO_TRADE decision.

WORKFLOW:
1. Gather all agent outputs
2. Run 8 hard gates (any fail = NO_TRADE)
3. Compute weighted confluence score
4. Check 4 veto conditions
5. Make final decision
6. Generate trade plan
7. Log everything

CRITICAL: If uncertain, the answer is NO_TRADE.
Conservative approach: missed opportunities < bad trades.
"""
import structlog
from datetime import datetime, timezone
from typing import Any, Optional
from dataclasses import dataclass, field
from uuid import uuid4

from app.agents.base_agent import BaseAgent, AgentMessage, AgentHealthStatus

logger = structlog.get_logger()


# Scoring weights from 04_SUPERVISOR_ORCHESTRATOR.txt
CONFLUENCE_WEIGHTS = {
    "technical_alignment": 0.25,
    "structural_quality": 0.20,
    "macro_alignment": 0.15,
    "regime_fit": 0.15,
    "sentiment_alignment": 0.10,
    "risk_execution_viability": 0.15,
}

# Decision thresholds
TRADE_THRESHOLD = 0.65
WATCHLIST_THRESHOLD = 0.50


@dataclass
class HardGateResult:
    """Result of a single hard gate check."""
    gate_name: str
    passed: bool
    reason: str = ""
    value: Any = None


@dataclass
class VetoResult:
    """Result of a veto condition check."""
    veto_name: str
    vetoed: bool
    reason: str = ""


@dataclass
class TradePlan:
    """Complete trade plan if approved."""
    plan_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    symbol: str = ""
    direction: str = ""  # "long" or "short"
    
    entry_type: str = "market"
    entry_price: Optional[float] = None
    stop_loss: float = 0.0
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    
    risk_percent: float = 0.0
    lot_size: float = 0.0
    
    strategy_name: str = ""
    regime: str = ""
    timeframe: str = "M30"
    
    confluence_score: float = 0.0
    score_breakdown: dict = field(default_factory=dict)
    
    supporting_evidence: list = field(default_factory=list)
    contradicting_evidence: list = field(default_factory=list)
    
    # Rationales (plain English)
    summary: str = ""
    rationale_direction: str = ""
    rationale_location: str = ""
    rationale_timing: str = ""
    invalidation_thesis: str = ""
    risk_sizing_rationale: str = ""
    
    # Execution mode
    execution_mode: str = "paper"


@dataclass
class OrchestratorDecision:
    """Complete orchestrator decision."""
    symbol: str
    timestamp: datetime
    correlation_id: str = field(default_factory=lambda: str(uuid4()))
    
    # Decision
    decision: str = "NO_TRADE"  # BUY, SELL, WATCHLIST, NO_TRADE
    confidence: float = 0.0
    
    # Hard gates
    hard_gates_passed: bool = True
    hard_gates_results: list = field(default_factory=list)
    failed_gates: list = field(default_factory=list)
    
    # Scoring
    confluence_score: float = 0.0
    score_breakdown: dict = field(default_factory=dict)
    
    # Vetoes
    was_vetoed: bool = False
    veto_results: list = field(default_factory=list)
    active_vetoes: list = field(default_factory=list)
    
    # Trade plan (if approved)
    trade_plan: Optional[TradePlan] = None
    
    # Reasoning
    decision_reasoning: str = ""
    warnings: list = field(default_factory=list)
    
    # Snapshot of all inputs
    agent_snapshot: dict = field(default_factory=dict)


class OrchestratorAgent(BaseAgent):
    """
    Orchestrator / CIO Agent - The decision maker.
    
    CRITICAL PRINCIPLES:
    1. If data quality is degraded → NO_TRADE
    2. If any hard gate fails → NO_TRADE
    3. If any veto is active → NO_TRADE
    4. If uncertain → NO_TRADE
    5. Risk Manager veto is ABSOLUTE
    
    Conservative approach: We'd rather miss a good trade than take a bad one.
    """
    
    def __init__(
        self,
        name: str = "orchestrator_agent",
        config: Optional[dict[str, Any]] = None,
    ):
        super().__init__(name, config)
        
        self.weights = config.get("weights", CONFLUENCE_WEIGHTS) if config else CONFLUENCE_WEIGHTS
        self.trade_threshold = config.get("trade_threshold", TRADE_THRESHOLD) if config else TRADE_THRESHOLD
        self.watchlist_threshold = config.get("watchlist_threshold", WATCHLIST_THRESHOLD) if config else WATCHLIST_THRESHOLD
        self.min_data_quality = config.get("min_data_quality", 0.7) if config else 0.7
        
        # Execution mode
        self.execution_mode = config.get("execution_mode", "paper") if config else "paper"
    
    async def initialize(self) -> None:
        """Initialize the orchestrator."""
        self.is_initialized = True
        self.is_running = True
        self.started_at = datetime.now(timezone.utc)
        self._logger.info(
            "Orchestrator Agent initialized",
            execution_mode=self.execution_mode,
            trade_threshold=self.trade_threshold,
        )
    
    async def run(self, context: dict[str, Any]) -> AgentMessage:
        """
        Make a trading decision.
        
        Args:
            context: Must contain all agent outputs:
                - symbol: Trading symbol
                - market_data: MarketDataSnapshot
                - technical: TechnicalAssessment
                - structure: MarketStructureAssessment  
                - regime: RegimeAssessment
                - strategy: StrategySelectionResult
                - risk_approval: RiskApproval (if signal exists)
                - portfolio_exposure: PortfolioExposureCheck (if signal exists)
                - macro (optional): FundamentalMacroAssessment
                - news (optional): NewsEventAssessment
                - sentiment (optional): SentimentAssessment
        """
        symbol = context.get("symbol")
        
        if not symbol:
            return self._create_message(
                message_type="error",
                payload={"error": "Missing symbol"},
                confidence=0.0,
                errors=["Symbol is required"],
            )
        
        # Make decision
        decision = await self._make_decision(symbol, context)
        
        # Log the decision
        self._logger.info(
            "Orchestrator decision",
            symbol=symbol,
            decision=decision.decision,
            confluence_score=decision.confluence_score,
            hard_gates_passed=decision.hard_gates_passed,
            was_vetoed=decision.was_vetoed,
        )
        
        return self._create_message(
            message_type="orchestrator_decision",
            payload=self._decision_to_dict(decision),
            symbol=symbol,
            confidence=decision.confidence,
            warnings=decision.warnings,
        )
    
    async def _make_decision(
        self,
        symbol: str,
        context: dict[str, Any],
    ) -> OrchestratorDecision:
        """Execute the full decision workflow."""
        decision = OrchestratorDecision(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
        )
        
        # Store agent snapshot for auditability
        decision.agent_snapshot = self._create_agent_snapshot(context)
        
        # ========== STEP 1: HARD GATES ==========
        gate_results = self._check_hard_gates(context)
        decision.hard_gates_results = [self._gate_to_dict(g) for g in gate_results]
        decision.failed_gates = [g.gate_name for g in gate_results if not g.passed]
        decision.hard_gates_passed = len(decision.failed_gates) == 0
        
        if not decision.hard_gates_passed:
            decision.decision = "NO_TRADE"
            decision.decision_reasoning = f"Hard gate(s) failed: {', '.join(decision.failed_gates)}"
            decision.confidence = 0.0
            return decision
        
        # ========== STEP 2: CHECK FOR SIGNAL ==========
        strategy = context.get("strategy", {})
        selected_signal = strategy.get("selected_signal")
        
        if not selected_signal:
            decision.decision = "NO_TRADE"
            decision.decision_reasoning = "No valid strategy signal generated"
            decision.confidence = 0.0
            return decision
        
        # ========== STEP 3: COMPUTE CONFLUENCE SCORE ==========
        score, breakdown = self._compute_confluence_score(context, selected_signal)
        decision.confluence_score = score
        decision.score_breakdown = breakdown
        
        # ========== STEP 4: CHECK VETOES ==========
        veto_results = self._check_vetoes(context, selected_signal, score)
        decision.veto_results = [self._veto_to_dict(v) for v in veto_results]
        decision.active_vetoes = [v.veto_name for v in veto_results if v.vetoed]
        decision.was_vetoed = len(decision.active_vetoes) > 0
        
        if decision.was_vetoed:
            decision.decision = "NO_TRADE"
            decision.decision_reasoning = f"Vetoed: {', '.join(decision.active_vetoes)}"
            decision.confidence = 0.0
            return decision
        
        # ========== STEP 5: APPLY THRESHOLDS ==========
        if score >= self.trade_threshold:
            decision.decision = selected_signal.get("direction", "").upper()
            if decision.decision == "LONG":
                decision.decision = "BUY"
            elif decision.decision == "SHORT":
                decision.decision = "SELL"
            decision.confidence = score
            
            # Generate trade plan
            decision.trade_plan = self._generate_trade_plan(
                symbol, context, selected_signal, score, breakdown
            )
            decision.decision_reasoning = self._generate_reasoning(
                decision, context, selected_signal
            )
            
        elif score >= self.watchlist_threshold:
            decision.decision = "WATCHLIST"
            decision.confidence = score
            decision.decision_reasoning = f"Score {score:.2f} above watchlist threshold but below trade threshold"
            
        else:
            decision.decision = "NO_TRADE"
            decision.confidence = 0.0
            decision.decision_reasoning = f"Score {score:.2f} below watchlist threshold"
        
        # Add warnings
        decision.warnings = self._gather_warnings(context, decision)
        
        return decision
    
    def _check_hard_gates(self, context: dict[str, Any]) -> list[HardGateResult]:
        """Check all 8 hard gates. Any failure = NO_TRADE."""
        gates = []
        
        # GATE 1: Data Quality
        market_data = context.get("market_data", {})
        data_quality = market_data.get("data_quality_score", 0)
        gates.append(HardGateResult(
            gate_name="data_quality",
            passed=data_quality >= self.min_data_quality,
            reason=f"Quality {data_quality:.2f} {'≥' if data_quality >= self.min_data_quality else '<'} {self.min_data_quality}",
            value=data_quality,
        ))
        
        # GATE 2: Event Risk
        news = context.get("news", {})
        is_event_blocked = news.get("is_blocked", False)
        gates.append(HardGateResult(
            gate_name="event_risk",
            passed=not is_event_blocked,
            reason="No blocking event" if not is_event_blocked else "High-impact event window",
            value=is_event_blocked,
        ))
        
        # GATE 3: Spread
        spread = market_data.get("current_spread_pips", 99)
        max_spread = context.get("max_spread", 4.0)
        gates.append(HardGateResult(
            gate_name="spread",
            passed=spread <= max_spread,
            reason=f"Spread {spread:.1f} {'≤' if spread <= max_spread else '>'} {max_spread}",
            value=spread,
        ))
        
        # GATE 4: Regime
        regime = context.get("regime", {})
        regime_multiplier = regime.get("regime_risk_multiplier", 0)
        gates.append(HardGateResult(
            gate_name="regime",
            passed=regime_multiplier > 0,
            reason=f"Regime multiplier: {regime_multiplier}" if regime_multiplier > 0 else "Regime blocked trading",
            value=regime_multiplier,
        ))
        
        # GATE 5: Risk Limits (from risk manager)
        risk_approval = context.get("risk_approval", {})
        risk_approved = risk_approval.get("approved", True)  # Default true if not yet checked
        risk_denial = risk_approval.get("denial_reasons", [])
        gates.append(HardGateResult(
            gate_name="risk_limits",
            passed=risk_approved or not risk_denial,
            reason="Risk approved" if risk_approved else f"Risk denied: {risk_denial[0] if risk_denial else 'unknown'}",
            value=risk_approved,
        ))
        
        # GATE 6: Concentration
        exposure = context.get("portfolio_exposure", {})
        exposure_ok = exposure.get("is_acceptable", True)
        gates.append(HardGateResult(
            gate_name="concentration",
            passed=exposure_ok,
            reason=exposure.get("reasoning", "OK") if exposure_ok else "Portfolio too concentrated",
            value=exposure.get("concentration_score", 0),
        ))
        
        # GATE 7: Stop Loss Logic
        strategy = context.get("strategy", {})
        signal = strategy.get("selected_signal", {})
        has_stop = signal.get("stop_loss", 0) > 0 if signal else True
        gates.append(HardGateResult(
            gate_name="stop_logic",
            passed=has_stop or not signal,
            reason="Stop loss defined" if has_stop else "NO STOP LOSS - BLOCKED",
            value=signal.get("stop_loss") if signal else None,
        ))
        
        # GATE 8: MT5 Health (if live trading)
        if self.execution_mode != "paper":
            mt5_health = context.get("mt5_health", {})
            mt5_ok = mt5_health.get("connected", False) and mt5_health.get("trade_allowed", False)
            gates.append(HardGateResult(
                gate_name="mt5_health",
                passed=mt5_ok,
                reason="MT5 connected and trading allowed" if mt5_ok else "MT5 not ready",
                value=mt5_ok,
            ))
        else:
            gates.append(HardGateResult(
                gate_name="mt5_health",
                passed=True,
                reason="Paper mode - MT5 not required",
                value=None,
            ))
        
        return gates
    
    def _compute_confluence_score(
        self,
        context: dict[str, Any],
        signal: dict,
    ) -> tuple[float, dict]:
        """Compute weighted confluence score."""
        breakdown = {}
        
        # Technical Alignment (0.25)
        technical = context.get("technical", {})
        tech_score = self._score_technical(technical, signal)
        breakdown["technical_alignment"] = tech_score
        
        # Structural Quality (0.20)
        structure = context.get("structure", {})
        struct_score = self._score_structure(structure, signal)
        breakdown["structural_quality"] = struct_score
        
        # Macro Alignment (0.15)
        macro = context.get("macro", {})
        macro_score = self._score_macro(macro, signal)
        breakdown["macro_alignment"] = macro_score
        
        # Regime Fit (0.15)
        regime = context.get("regime", {})
        regime_score = self._score_regime(regime, signal)
        breakdown["regime_fit"] = regime_score
        
        # Sentiment Alignment (0.10)
        sentiment = context.get("sentiment", {})
        sentiment_score = self._score_sentiment(sentiment, signal)
        breakdown["sentiment_alignment"] = sentiment_score
        
        # Risk/Execution Viability (0.15)
        risk_approval = context.get("risk_approval", {})
        exposure = context.get("portfolio_exposure", {})
        risk_score = self._score_risk_execution(risk_approval, exposure, signal)
        breakdown["risk_execution_viability"] = risk_score
        
        # Weighted sum
        total = sum(
            breakdown[k] * self.weights[k]
            for k in breakdown
        )
        
        return total, breakdown
    
    def _score_technical(self, technical: dict, signal: dict) -> float:
        """Score technical alignment."""
        score = 0.5  # Base
        
        direction = signal.get("direction", "")
        tech_lean = technical.get("directional_lean", "neutral")
        tech_strength = technical.get("directional_strength", 0)
        mtf = technical.get("mtf_alignment", "mixed")
        
        # Direction match
        if (direction == "long" and tech_lean == "bullish") or \
           (direction == "short" and tech_lean == "bearish"):
            score += 0.2
            score += tech_strength * 0.2
        
        # MTF alignment
        if mtf == f"aligned_{tech_lean}":
            score += 0.1
        elif mtf == "conflicting":
            score -= 0.2
        
        return max(0.0, min(1.0, score))
    
    def _score_structure(self, structure: dict, signal: dict) -> float:
        """Score structural quality."""
        score = 0.5
        
        direction = signal.get("direction", "")
        price_location = structure.get("price_location", "")
        is_definable = structure.get("is_risk_definable_here", False)
        is_asymmetric = structure.get("is_setup_asymmetric", False)
        location_quality = structure.get("risk_reward_location_quality", 0.5)
        
        # Good location for direction
        if direction == "long" and price_location == "at_support":
            score += 0.2
        elif direction == "short" and price_location == "at_resistance":
            score += 0.2
        elif price_location == "mid_range":
            score -= 0.1
        
        # Risk definability
        if is_definable:
            score += 0.1
        
        # Asymmetric setup
        if is_asymmetric:
            score += 0.1
        
        score += (location_quality - 0.5) * 0.2
        
        return max(0.0, min(1.0, score))
    
    def _score_macro(self, macro: dict, signal: dict) -> float:
        """Score macro alignment."""
        if not macro:
            return 0.5  # Neutral if no macro data
        
        # Placeholder - would check currency bias alignment
        return 0.5
    
    def _score_regime(self, regime: dict, signal: dict) -> float:
        """Score regime fit."""
        score = 0.5
        
        regime_confidence = regime.get("regime_confidence", 0.5)
        regime_stability = regime.get("regime_stability", 0.5)
        recommended = regime.get("recommended_strategy_families", [])
        strategy_name = signal.get("strategy_name", "")
        
        # Strategy in recommended list
        if strategy_name in recommended:
            score += 0.3
        
        # Regime confidence
        score += (regime_confidence - 0.5) * 0.2
        
        # Stability
        score += (regime_stability - 0.5) * 0.1
        
        return max(0.0, min(1.0, score))
    
    def _score_sentiment(self, sentiment: dict, signal: dict) -> float:
        """Score sentiment alignment."""
        if not sentiment:
            return 0.5  # Neutral if no sentiment data
        return 0.5
    
    def _score_risk_execution(
        self,
        risk: dict,
        exposure: dict,
        signal: dict,
    ) -> float:
        """Score risk and execution viability."""
        score = 0.5
        
        # R:R ratio
        rr = signal.get("risk_reward_ratio", 0)
        if rr >= 2.0:
            score += 0.2
        elif rr >= 1.5:
            score += 0.1
        elif rr < 1.0:
            score -= 0.2
        
        # Concentration
        concentration = exposure.get("concentration_score", 0.5)
        if concentration < 0.3:
            score += 0.1  # Well diversified
        elif concentration > 0.7:
            score -= 0.1  # Concentrated
        
        # Risk mode
        sizing = risk.get("position_sizing", {})
        drawdown_mode = sizing.get("drawdown_mode", "normal")
        if drawdown_mode == "normal":
            score += 0.1
        elif drawdown_mode == "defensive":
            score -= 0.1
        
        return max(0.0, min(1.0, score))
    
    def _check_vetoes(
        self,
        context: dict[str, Any],
        signal: dict,
        score: float,
    ) -> list[VetoResult]:
        """Check veto conditions."""
        vetoes = []
        
        # VETO 1: Risk Manager Denial (ABSOLUTE)
        risk = context.get("risk_approval", {})
        if risk.get("denial_reasons"):
            vetoes.append(VetoResult(
                veto_name="risk_manager_denial",
                vetoed=True,
                reason=risk["denial_reasons"][0],
            ))
        else:
            vetoes.append(VetoResult(
                veto_name="risk_manager_denial",
                vetoed=False,
            ))
        
        # VETO 2: Major Agent Disagreement
        technical = context.get("technical", {})
        structure = context.get("structure", {})
        
        tech_lean = technical.get("directional_lean", "neutral")
        struct_state = structure.get("structure_state", "unknown")
        signal_dir = signal.get("direction", "")
        
        disagreement = 0
        if signal_dir == "long" and tech_lean == "bearish":
            disagreement += 1
        if signal_dir == "short" and tech_lean == "bullish":
            disagreement += 1
        if signal_dir == "long" and struct_state == "trending_down":
            disagreement += 1
        if signal_dir == "short" and struct_state == "trending_up":
            disagreement += 1
        
        vetoes.append(VetoResult(
            veto_name="agent_disagreement",
            vetoed=disagreement >= 2,
            reason=f"{disagreement} agents disagree with signal direction" if disagreement >= 2 else "OK",
        ))
        
        # VETO 3: Low Setup Quality with Low R:R
        setup_quality = signal.get("setup_quality", 0)
        rr = signal.get("risk_reward_ratio", 0)
        
        vetoes.append(VetoResult(
            veto_name="quality_rr_combo",
            vetoed=(setup_quality < 0.4 and rr < 1.5),
            reason="Low quality setup with inadequate R:R" if (setup_quality < 0.4 and rr < 1.5) else "OK",
        ))
        
        # VETO 4: Contradicting Higher Timeframe
        mtf = technical.get("mtf_alignment", "mixed")
        expected = f"aligned_{'bullish' if signal_dir == 'long' else 'bearish'}"
        opposite = f"aligned_{'bearish' if signal_dir == 'long' else 'bullish'}"
        
        vetoes.append(VetoResult(
            veto_name="htf_contradiction",
            vetoed=(mtf == opposite),
            reason="Higher timeframes contradict signal" if mtf == opposite else "OK",
        ))
        
        return vetoes
    
    def _generate_trade_plan(
        self,
        symbol: str,
        context: dict[str, Any],
        signal: dict,
        score: float,
        breakdown: dict,
    ) -> TradePlan:
        """Generate complete trade plan."""
        risk = context.get("risk_approval", {})
        sizing = risk.get("position_sizing", {})
        regime = context.get("regime", {})
        
        plan = TradePlan(
            symbol=symbol,
            direction=signal.get("direction", ""),
            entry_type=signal.get("entry_type", "market"),
            entry_price=signal.get("entry_price"),
            stop_loss=signal.get("stop_loss", 0),
            take_profit_1=signal.get("take_profit_1"),
            take_profit_2=signal.get("take_profit_2"),
            risk_percent=sizing.get("risk_percent", 0),
            lot_size=sizing.get("lot_size", 0),
            strategy_name=signal.get("strategy_name", ""),
            regime=regime.get("current_regime", ""),
            confluence_score=score,
            score_breakdown=breakdown,
            supporting_evidence=signal.get("supporting_factors", []),
            contradicting_evidence=signal.get("contradicting_factors", []),
            summary=signal.get("rationale", ""),
            invalidation_thesis=signal.get("invalidation", ""),
            execution_mode=self.execution_mode,
        )
        
        # Generate rationales
        plan.rationale_direction = self._explain_direction(context, signal)
        plan.rationale_location = self._explain_location(context, signal)
        plan.rationale_timing = self._explain_timing(context)
        plan.risk_sizing_rationale = self._explain_sizing(sizing)
        
        return plan
    
    def _explain_direction(self, context: dict, signal: dict) -> str:
        technical = context.get("technical", {})
        return f"Direction {signal.get('direction')} based on {technical.get('directional_lean')} lean with {technical.get('directional_strength', 0):.0%} strength"
    
    def _explain_location(self, context: dict, signal: dict) -> str:
        structure = context.get("structure", {})
        return f"Entry at {structure.get('price_location', 'current level')} with R:R {signal.get('risk_reward_ratio', 0):.1f}"
    
    def _explain_timing(self, context: dict) -> str:
        regime = context.get("regime", {})
        return f"Regime: {regime.get('current_regime', 'unknown')} with {regime.get('regime_confidence', 0):.0%} confidence"
    
    def _explain_sizing(self, sizing: dict) -> str:
        return f"Risk {sizing.get('risk_percent', 0):.2f}% = {sizing.get('lot_size', 0):.2f} lots (regime adj: {sizing.get('regime_multiplier_applied', 1):.0%})"
    
    def _generate_reasoning(
        self,
        decision: OrchestratorDecision,
        context: dict,
        signal: dict,
    ) -> str:
        """Generate human-readable decision reasoning."""
        parts = [
            f"APPROVED: {signal.get('strategy_name')} {signal.get('direction').upper()}",
            f"Confluence: {decision.confluence_score:.2f}",
            f"R:R: {signal.get('risk_reward_ratio', 0):.1f}",
        ]
        
        if signal.get("supporting_factors"):
            parts.append(f"Support: {', '.join(signal['supporting_factors'][:2])}")
        
        return " | ".join(parts)
    
    def _gather_warnings(
        self,
        context: dict,
        decision: OrchestratorDecision,
    ) -> list[str]:
        """Gather all warnings."""
        warnings = []
        
        technical = context.get("technical", {})
        if technical.get("contradicting_factors"):
            warnings.extend(technical["contradicting_factors"][:2])
        
        if decision.confluence_score < 0.7:
            warnings.append(f"Moderate confluence ({decision.confluence_score:.2f})")
        
        regime = context.get("regime", {})
        if regime.get("transition_probability", 0) > 0.4:
            warnings.append("Regime may be transitioning")
        
        return warnings
    
    def _create_agent_snapshot(self, context: dict) -> dict:
        """Create snapshot of all agent inputs for audit."""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "has_market_data": "market_data" in context,
            "has_technical": "technical" in context,
            "has_structure": "structure" in context,
            "has_regime": "regime" in context,
            "has_strategy": "strategy" in context,
            "has_risk": "risk_approval" in context,
            "has_exposure": "portfolio_exposure" in context,
            "has_macro": "macro" in context,
            "has_news": "news" in context,
            "has_sentiment": "sentiment" in context,
        }
    
    def _gate_to_dict(self, gate: HardGateResult) -> dict:
        return {
            "gate_name": gate.gate_name,
            "passed": gate.passed,
            "reason": gate.reason,
            "value": gate.value,
        }
    
    def _veto_to_dict(self, veto: VetoResult) -> dict:
        return {
            "veto_name": veto.veto_name,
            "vetoed": veto.vetoed,
            "reason": veto.reason,
        }
    
    def _decision_to_dict(self, decision: OrchestratorDecision) -> dict:
        """Convert decision to serializable dict."""
        plan_dict = None
        if decision.trade_plan:
            p = decision.trade_plan
            plan_dict = {
                "plan_id": p.plan_id,
                "timestamp": p.timestamp.isoformat(),
                "symbol": p.symbol,
                "direction": p.direction,
                "entry_type": p.entry_type,
                "entry_price": p.entry_price,
                "stop_loss": p.stop_loss,
                "take_profit_1": p.take_profit_1,
                "take_profit_2": p.take_profit_2,
                "risk_percent": p.risk_percent,
                "lot_size": p.lot_size,
                "strategy_name": p.strategy_name,
                "regime": p.regime,
                "confluence_score": p.confluence_score,
                "summary": p.summary,
                "rationale_direction": p.rationale_direction,
                "rationale_location": p.rationale_location,
                "rationale_timing": p.rationale_timing,
                "invalidation_thesis": p.invalidation_thesis,
                "execution_mode": p.execution_mode,
            }
        
        return {
            "symbol": decision.symbol,
            "timestamp": decision.timestamp.isoformat(),
            "correlation_id": decision.correlation_id,
            "decision": decision.decision,
            "confidence": decision.confidence,
            "hard_gates_passed": decision.hard_gates_passed,
            "hard_gates_results": decision.hard_gates_results,
            "failed_gates": decision.failed_gates,
            "confluence_score": decision.confluence_score,
            "score_breakdown": decision.score_breakdown,
            "was_vetoed": decision.was_vetoed,
            "veto_results": decision.veto_results,
            "active_vetoes": decision.active_vetoes,
            "trade_plan": plan_dict,
            "decision_reasoning": decision.decision_reasoning,
            "warnings": decision.warnings,
        }
    
    async def health_check(self) -> AgentHealthStatus:
        return AgentHealthStatus(
            agent_name=self.name,
            is_healthy=self.is_initialized,
            last_run=self.last_run,
            last_success=self.last_success,
            last_error=self.last_error,
            consecutive_failures=self.consecutive_failures,
            uptime_seconds=self._get_uptime_seconds(),
        )
    
    def get_dependencies(self) -> list[str]:
        return [
            "market_data_agent",
            "technical_analysis_agent",
            "market_structure_agent",
            "regime_detection_agent",
            "strategy_selection_agent",
            "risk_manager_agent",
            "portfolio_exposure_agent",
        ]
