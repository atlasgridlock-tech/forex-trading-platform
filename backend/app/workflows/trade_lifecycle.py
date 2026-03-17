"""
Trade Lifecycle State Machine
=============================
Every trade moves through defined states with logged transitions.

From 09_WORKFLOWS.txt:
IDEA -> EVALUATING -> APPROVED / REJECTED / WATCHLISTED
(if approved) PENDING_EXECUTION -> EXECUTING -> OPEN
(while open) MONITORING -> [MODIFY_STOP | MODIFY_TP | PARTIAL_CLOSE]
(exit triggered) CLOSING -> CLOSED
(post-trade) JOURNALED -> ANALYZED
"""
import structlog
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from dataclasses import dataclass, field
from uuid import uuid4

logger = structlog.get_logger()


class TradeState(str, Enum):
    """Trade lifecycle states."""
    IDEA = "idea"
    EVALUATING = "evaluating"
    APPROVED = "approved"
    REJECTED = "rejected"
    WATCHLISTED = "watchlisted"
    PENDING_EXECUTION = "pending_execution"
    EXECUTING = "executing"
    OPEN = "open"
    MONITORING = "monitoring"
    CLOSING = "closing"
    CLOSED = "closed"
    JOURNALED = "journaled"
    ANALYZED = "analyzed"
    ERROR = "error"


# Valid state transitions
VALID_TRANSITIONS = {
    TradeState.IDEA: [TradeState.EVALUATING],
    TradeState.EVALUATING: [TradeState.APPROVED, TradeState.REJECTED, TradeState.WATCHLISTED, TradeState.ERROR],
    TradeState.APPROVED: [TradeState.PENDING_EXECUTION, TradeState.ERROR],
    TradeState.REJECTED: [],  # Terminal
    TradeState.WATCHLISTED: [TradeState.EVALUATING, TradeState.REJECTED],  # Can re-evaluate
    TradeState.PENDING_EXECUTION: [TradeState.EXECUTING, TradeState.ERROR],
    TradeState.EXECUTING: [TradeState.OPEN, TradeState.ERROR],
    TradeState.OPEN: [TradeState.MONITORING, TradeState.CLOSING, TradeState.ERROR],
    TradeState.MONITORING: [TradeState.MONITORING, TradeState.CLOSING],
    TradeState.CLOSING: [TradeState.CLOSED, TradeState.ERROR],
    TradeState.CLOSED: [TradeState.JOURNALED],
    TradeState.JOURNALED: [TradeState.ANALYZED],
    TradeState.ANALYZED: [],  # Terminal
    TradeState.ERROR: [],  # Terminal (requires manual intervention)
}


@dataclass
class StateTransition:
    """Record of a state transition."""
    from_state: TradeState
    to_state: TradeState
    timestamp: datetime
    reason: str
    actor: str = "system"  # Who/what triggered the transition
    metadata: dict = field(default_factory=dict)


@dataclass
class TradeLifecycle:
    """
    Manages the lifecycle of a single trade idea through all states.
    """
    trade_id: str = field(default_factory=lambda: str(uuid4()))
    symbol: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Current state
    current_state: TradeState = TradeState.IDEA
    
    # History
    transitions: list = field(default_factory=list)
    
    # Associated data
    plan_id: Optional[str] = None
    receipt_id: Optional[str] = None
    position_ticket: Optional[int] = None
    journal_id: Optional[str] = None
    
    # Outcome
    result_r: Optional[float] = None
    result_pnl: Optional[float] = None
    exit_type: Optional[str] = None
    
    def transition_to(
        self,
        new_state: TradeState,
        reason: str,
        actor: str = "system",
        metadata: Optional[dict] = None,
    ) -> bool:
        """
        Attempt to transition to a new state.
        
        Returns:
            True if transition was valid and executed
        """
        if new_state not in VALID_TRANSITIONS.get(self.current_state, []):
            logger.warning(
                "Invalid state transition attempted",
                trade_id=self.trade_id,
                from_state=self.current_state.value,
                to_state=new_state.value,
            )
            return False
        
        transition = StateTransition(
            from_state=self.current_state,
            to_state=new_state,
            timestamp=datetime.now(timezone.utc),
            reason=reason,
            actor=actor,
            metadata=metadata or {},
        )
        
        self.transitions.append(transition)
        self.current_state = new_state
        
        logger.info(
            "Trade state transition",
            trade_id=self.trade_id,
            symbol=self.symbol,
            from_state=transition.from_state.value,
            to_state=transition.to_state.value,
            reason=reason,
        )
        
        return True
    
    def get_time_in_state(self, state: TradeState) -> Optional[float]:
        """Get total time spent in a state (seconds)."""
        total_seconds = 0.0
        entry_time = None
        
        for t in self.transitions:
            if t.to_state == state:
                entry_time = t.timestamp
            elif entry_time and t.from_state == state:
                total_seconds += (t.timestamp - entry_time).total_seconds()
                entry_time = None
        
        # If currently in state
        if self.current_state == state and entry_time:
            total_seconds += (datetime.now(timezone.utc) - entry_time).total_seconds()
        
        return total_seconds if total_seconds > 0 else None
    
    def to_dict(self) -> dict:
        """Convert to serializable dict."""
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "created_at": self.created_at.isoformat(),
            "current_state": self.current_state.value,
            "transitions": [
                {
                    "from_state": t.from_state.value,
                    "to_state": t.to_state.value,
                    "timestamp": t.timestamp.isoformat(),
                    "reason": t.reason,
                    "actor": t.actor,
                }
                for t in self.transitions
            ],
            "plan_id": self.plan_id,
            "receipt_id": self.receipt_id,
            "position_ticket": self.position_ticket,
            "journal_id": self.journal_id,
            "result_r": self.result_r,
            "result_pnl": self.result_pnl,
            "exit_type": self.exit_type,
        }


class TradeLifecycleManager:
    """
    Manages all active trade lifecycles.
    """
    
    def __init__(self):
        self._trades: dict[str, TradeLifecycle] = {}
        self._logger = logger.bind(component="lifecycle_manager")
    
    def create_trade(self, symbol: str) -> TradeLifecycle:
        """Create a new trade lifecycle."""
        trade = TradeLifecycle(symbol=symbol)
        self._trades[trade.trade_id] = trade
        
        self._logger.info(
            "Trade lifecycle created",
            trade_id=trade.trade_id,
            symbol=symbol,
        )
        
        return trade
    
    def get_trade(self, trade_id: str) -> Optional[TradeLifecycle]:
        """Get a trade by ID."""
        return self._trades.get(trade_id)
    
    def get_trades_by_state(self, state: TradeState) -> list[TradeLifecycle]:
        """Get all trades in a specific state."""
        return [t for t in self._trades.values() if t.current_state == state]
    
    def get_active_trades(self) -> list[TradeLifecycle]:
        """Get all trades that are not in terminal states."""
        terminal_states = {TradeState.REJECTED, TradeState.ANALYZED, TradeState.ERROR}
        return [t for t in self._trades.values() if t.current_state not in terminal_states]
    
    def get_open_positions(self) -> list[TradeLifecycle]:
        """Get trades with open positions."""
        open_states = {TradeState.OPEN, TradeState.MONITORING}
        return [t for t in self._trades.values() if t.current_state in open_states]
    
    def cleanup_old_trades(self, max_age_days: int = 30) -> int:
        """Remove old terminal trades from memory."""
        terminal_states = {TradeState.REJECTED, TradeState.ANALYZED, TradeState.ERROR}
        cutoff = datetime.now(timezone.utc).timestamp() - (max_age_days * 86400)
        
        to_remove = []
        for trade_id, trade in self._trades.items():
            if trade.current_state in terminal_states:
                if trade.created_at.timestamp() < cutoff:
                    to_remove.append(trade_id)
        
        for trade_id in to_remove:
            del self._trades[trade_id]
        
        return len(to_remove)
