"""
Journal / Trade Review Agent
============================
Generates comprehensive journal entries for every trade.

From 08_POST_TRADE_AND_ANALYTICS.txt:
- Record every trade with full context
- Log rejected trade ideas
- Enable post-trade review
- Support learning and improvement
"""
import structlog
from datetime import datetime, timezone
from typing import Any, Optional
from dataclasses import dataclass, field
from uuid import uuid4

from app.agents.base_agent import BaseAgent, AgentMessage, AgentHealthStatus

logger = structlog.get_logger()


@dataclass
class JournalEntry:
    """Complete journal entry for a trade."""
    journal_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Trade identification
    trade_id: Optional[str] = None
    plan_id: Optional[str] = None
    receipt_id: Optional[str] = None
    position_ticket: Optional[int] = None
    
    # Trade details
    symbol: str = ""
    direction: str = ""
    entry_price: float = 0.0
    exit_price: Optional[float] = None
    stop_loss: float = 0.0
    take_profit: Optional[float] = None
    lot_size: float = 0.0
    
    # Context
    strategy_name: str = ""
    regime: str = ""
    session: str = ""
    day_of_week: str = ""
    
    # Market context at entry
    technical_summary: str = ""
    structure_summary: str = ""
    macro_context: str = ""
    
    # Decision
    confluence_score: float = 0.0
    score_breakdown: dict = field(default_factory=dict)
    entry_reason: str = ""
    supporting_signals: list = field(default_factory=list)
    conflicting_signals: list = field(default_factory=list)
    
    # Result
    result_r: Optional[float] = None
    result_pips: Optional[float] = None
    result_pnl: Optional[float] = None
    exit_type: str = ""  # stop_loss, take_profit, manual, trailing_stop, etc.
    holding_time_minutes: Optional[int] = None
    mae_pips: float = 0.0
    mfe_pips: float = 0.0
    
    # Post-trade review
    pre_trade_expectation: str = ""
    post_trade_reality: str = ""
    what_went_right: list = field(default_factory=list)
    what_went_wrong: list = field(default_factory=list)
    lessons_learned: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    
    # Quality assessment
    trade_quality_rating: Optional[float] = None  # 0.0 to 1.0
    thesis_correct: Optional[bool] = None
    execution_good: Optional[bool] = None
    exit_optimal: Optional[bool] = None
    
    reviewed_at: Optional[datetime] = None


@dataclass
class RejectedTradeEntry:
    """Record of a rejected trade idea."""
    rejection_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    symbol: str = ""
    proposed_direction: str = ""
    proposed_strategy: str = ""
    confluence_score: float = 0.0
    
    rejection_stage: str = ""  # hard_gate, veto, threshold, risk
    rejection_reasons: list = field(default_factory=list)
    
    # For later analysis
    would_have_been_profitable: Optional[bool] = None
    hypothetical_result: Optional[float] = None


class JournalReviewAgent(BaseAgent):
    """
    Journal / Trade Review Agent.
    
    Creates and manages trade journal entries for learning and analysis.
    """
    
    def __init__(
        self,
        name: str = "journal_review_agent",
        config: Optional[dict[str, Any]] = None,
    ):
        super().__init__(name, config)
        
        # In-memory storage (would be database in production)
        self._journal_entries: dict[str, JournalEntry] = {}
        self._rejected_entries: list[RejectedTradeEntry] = []
    
    async def initialize(self) -> None:
        """Initialize the agent."""
        self.is_initialized = True
        self.is_running = True
        self.started_at = datetime.now(timezone.utc)
        self._logger.info("Journal Review Agent initialized")
    
    async def run(self, context: dict[str, Any]) -> AgentMessage:
        """
        Create or update a journal entry.
        
        Args:
            context: Contains either:
                - action: "create_entry" with trade details
                - action: "record_rejection" with rejection details
                - action: "update_result" with trade result
                - action: "add_review" with review notes
        """
        action = context.get("action", "create_entry")
        
        if action == "create_entry":
            entry = await self._create_entry(context)
            return self._create_message(
                message_type="journal_entry_created",
                payload=self._entry_to_dict(entry),
                symbol=entry.symbol,
                confidence=1.0,
            )
        
        elif action == "record_rejection":
            rejection = await self._record_rejection(context)
            return self._create_message(
                message_type="rejection_recorded",
                payload=self._rejection_to_dict(rejection),
                symbol=rejection.symbol,
                confidence=1.0,
            )
        
        elif action == "update_result":
            entry = await self._update_result(context)
            if entry:
                return self._create_message(
                    message_type="result_updated",
                    payload=self._entry_to_dict(entry),
                    symbol=entry.symbol,
                    confidence=1.0,
                )
            return self._create_message(
                message_type="error",
                payload={"error": "Entry not found"},
                confidence=0.0,
            )
        
        elif action == "add_review":
            entry = await self._add_review(context)
            if entry:
                return self._create_message(
                    message_type="review_added",
                    payload=self._entry_to_dict(entry),
                    symbol=entry.symbol,
                    confidence=1.0,
                )
            return self._create_message(
                message_type="error",
                payload={"error": "Entry not found"},
                confidence=0.0,
            )
        
        return self._create_message(
            message_type="error",
            payload={"error": f"Unknown action: {action}"},
            confidence=0.0,
        )
    
    async def _create_entry(self, context: dict[str, Any]) -> JournalEntry:
        """Create a new journal entry from trade data."""
        trade_plan = context.get("trade_plan", {})
        execution = context.get("execution", {})
        technical = context.get("technical", {})
        structure = context.get("structure", {})
        regime = context.get("regime", {})
        
        entry = JournalEntry(
            trade_id=context.get("trade_id"),
            plan_id=trade_plan.get("plan_id"),
            receipt_id=execution.get("receipt_id"),
            position_ticket=execution.get("ticket"),
            symbol=trade_plan.get("symbol", ""),
            direction=trade_plan.get("direction", ""),
            entry_price=execution.get("fill_price", trade_plan.get("entry_price", 0)),
            stop_loss=trade_plan.get("stop_loss", 0),
            take_profit=trade_plan.get("take_profit_1"),
            lot_size=trade_plan.get("lot_size", 0),
            strategy_name=trade_plan.get("strategy_name", ""),
            regime=regime.get("current_regime", ""),
            session=self._determine_session(),
            day_of_week=datetime.now(timezone.utc).strftime("%A"),
            technical_summary=self._summarize_technical(technical),
            structure_summary=self._summarize_structure(structure),
            confluence_score=trade_plan.get("confluence_score", 0),
            score_breakdown=trade_plan.get("score_breakdown", {}),
            entry_reason=trade_plan.get("summary", ""),
            supporting_signals=trade_plan.get("supporting_evidence", []),
            conflicting_signals=trade_plan.get("contradicting_evidence", []),
        )
        
        self._journal_entries[entry.journal_id] = entry
        
        self._logger.info(
            "Journal entry created",
            journal_id=entry.journal_id,
            symbol=entry.symbol,
            direction=entry.direction,
        )
        
        return entry
    
    async def _record_rejection(self, context: dict[str, Any]) -> RejectedTradeEntry:
        """Record a rejected trade idea."""
        decision = context.get("decision", {})
        strategy = context.get("strategy", {})
        signal = strategy.get("selected_signal", {})
        
        rejection = RejectedTradeEntry(
            symbol=context.get("symbol", ""),
            proposed_direction=signal.get("direction", ""),
            proposed_strategy=signal.get("strategy_name", ""),
            confluence_score=decision.get("confluence_score", 0),
            rejection_stage=self._determine_rejection_stage(decision),
            rejection_reasons=self._extract_rejection_reasons(decision),
        )
        
        self._rejected_entries.append(rejection)
        
        # Keep only recent rejections
        if len(self._rejected_entries) > 1000:
            self._rejected_entries = self._rejected_entries[-500:]
        
        return rejection
    
    async def _update_result(self, context: dict[str, Any]) -> Optional[JournalEntry]:
        """Update entry with trade result."""
        journal_id = context.get("journal_id")
        if not journal_id or journal_id not in self._journal_entries:
            # Try to find by position ticket
            ticket = context.get("position_ticket")
            if ticket:
                for entry in self._journal_entries.values():
                    if entry.position_ticket == ticket:
                        journal_id = entry.journal_id
                        break
        
        if not journal_id or journal_id not in self._journal_entries:
            return None
        
        entry = self._journal_entries[journal_id]
        
        entry.exit_price = context.get("exit_price")
        entry.result_pnl = context.get("pnl")
        entry.exit_type = context.get("exit_type", "")
        entry.mae_pips = context.get("mae_pips", 0)
        entry.mfe_pips = context.get("mfe_pips", 0)
        
        # Calculate R-multiple
        if entry.exit_price and entry.stop_loss and entry.entry_price:
            risk = abs(entry.entry_price - entry.stop_loss)
            reward = entry.exit_price - entry.entry_price
            if entry.direction == "short":
                reward = entry.entry_price - entry.exit_price
            if risk > 0:
                entry.result_r = reward / risk
        
        # Calculate pips
        if entry.exit_price and entry.entry_price:
            diff = entry.exit_price - entry.entry_price
            if entry.direction == "short":
                diff = entry.entry_price - entry.exit_price
            entry.result_pips = diff / 0.0001
        
        # Calculate holding time
        if context.get("entry_time") and context.get("exit_time"):
            entry.holding_time_minutes = int(
                (context["exit_time"] - context["entry_time"]).total_seconds() / 60
            )
        
        return entry
    
    async def _add_review(self, context: dict[str, Any]) -> Optional[JournalEntry]:
        """Add review notes to an entry."""
        journal_id = context.get("journal_id")
        if not journal_id or journal_id not in self._journal_entries:
            return None
        
        entry = self._journal_entries[journal_id]
        
        if context.get("pre_trade_expectation"):
            entry.pre_trade_expectation = context["pre_trade_expectation"]
        if context.get("post_trade_reality"):
            entry.post_trade_reality = context["post_trade_reality"]
        if context.get("what_went_right"):
            entry.what_went_right = context["what_went_right"]
        if context.get("what_went_wrong"):
            entry.what_went_wrong = context["what_went_wrong"]
        if context.get("lessons_learned"):
            entry.lessons_learned = context["lessons_learned"]
        if context.get("tags"):
            entry.tags = context["tags"]
        if context.get("trade_quality_rating") is not None:
            entry.trade_quality_rating = context["trade_quality_rating"]
        if context.get("thesis_correct") is not None:
            entry.thesis_correct = context["thesis_correct"]
        if context.get("execution_good") is not None:
            entry.execution_good = context["execution_good"]
        if context.get("exit_optimal") is not None:
            entry.exit_optimal = context["exit_optimal"]
        
        entry.reviewed_at = datetime.now(timezone.utc)
        
        return entry
    
    def _determine_session(self) -> str:
        """Determine current trading session."""
        hour = datetime.now(timezone.utc).hour
        if 7 <= hour < 16:
            return "london" if hour < 12 else "london_new_york"
        elif 12 <= hour < 21:
            return "new_york"
        elif hour >= 23 or hour < 8:
            return "asian"
        return "transition"
    
    def _summarize_technical(self, technical: dict) -> str:
        """Generate technical summary."""
        lean = technical.get("directional_lean", "neutral")
        strength = technical.get("directional_strength", 0)
        mtf = technical.get("mtf_alignment", "mixed")
        return f"Direction: {lean} ({strength:.0%}), MTF: {mtf}"
    
    def _summarize_structure(self, structure: dict) -> str:
        """Generate structure summary."""
        state = structure.get("structure_state", "unknown")
        location = structure.get("price_location", "unknown")
        return f"State: {state}, Location: {location}"
    
    def _determine_rejection_stage(self, decision: dict) -> str:
        """Determine at which stage the trade was rejected."""
        if decision.get("failed_gates"):
            return "hard_gate"
        if decision.get("active_vetoes"):
            return "veto"
        if decision.get("confluence_score", 0) < 0.5:
            return "threshold"
        return "unknown"
    
    def _extract_rejection_reasons(self, decision: dict) -> list:
        """Extract rejection reasons from decision."""
        reasons = []
        
        for gate in decision.get("hard_gates_results", []):
            if not gate.get("passed"):
                reasons.append(f"Gate '{gate['gate_name']}': {gate.get('reason', 'failed')}")
        
        for veto in decision.get("veto_results", []):
            if veto.get("vetoed"):
                reasons.append(f"Veto '{veto['veto_name']}': {veto.get('reason', 'active')}")
        
        if not reasons and decision.get("decision_reasoning"):
            reasons.append(decision["decision_reasoning"])
        
        return reasons
    
    def _entry_to_dict(self, entry: JournalEntry) -> dict:
        """Convert entry to serializable dict."""
        return {
            "journal_id": entry.journal_id,
            "created_at": entry.created_at.isoformat(),
            "trade_id": entry.trade_id,
            "plan_id": entry.plan_id,
            "position_ticket": entry.position_ticket,
            "symbol": entry.symbol,
            "direction": entry.direction,
            "entry_price": entry.entry_price,
            "exit_price": entry.exit_price,
            "stop_loss": entry.stop_loss,
            "take_profit": entry.take_profit,
            "lot_size": entry.lot_size,
            "strategy_name": entry.strategy_name,
            "regime": entry.regime,
            "session": entry.session,
            "confluence_score": entry.confluence_score,
            "result_r": entry.result_r,
            "result_pips": entry.result_pips,
            "result_pnl": entry.result_pnl,
            "exit_type": entry.exit_type,
            "holding_time_minutes": entry.holding_time_minutes,
            "mae_pips": entry.mae_pips,
            "mfe_pips": entry.mfe_pips,
            "trade_quality_rating": entry.trade_quality_rating,
            "reviewed_at": entry.reviewed_at.isoformat() if entry.reviewed_at else None,
        }
    
    def _rejection_to_dict(self, rejection: RejectedTradeEntry) -> dict:
        """Convert rejection to serializable dict."""
        return {
            "rejection_id": rejection.rejection_id,
            "timestamp": rejection.timestamp.isoformat(),
            "symbol": rejection.symbol,
            "proposed_direction": rejection.proposed_direction,
            "proposed_strategy": rejection.proposed_strategy,
            "confluence_score": rejection.confluence_score,
            "rejection_stage": rejection.rejection_stage,
            "rejection_reasons": rejection.rejection_reasons,
        }
    
    def get_entries(
        self,
        symbol: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """Get journal entries, optionally filtered."""
        entries = list(self._journal_entries.values())
        
        if symbol:
            entries = [e for e in entries if e.symbol == symbol]
        
        entries.sort(key=lambda e: e.created_at, reverse=True)
        
        return [self._entry_to_dict(e) for e in entries[:limit]]
    
    def get_rejections(self, limit: int = 50) -> list[dict]:
        """Get recent rejections."""
        rejections = sorted(
            self._rejected_entries,
            key=lambda r: r.timestamp,
            reverse=True,
        )
        return [self._rejection_to_dict(r) for r in rejections[:limit]]
    
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
        return []
