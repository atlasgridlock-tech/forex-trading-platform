"""
Risk Manager Agent
==================
Has the HIGHEST AUTHORITY in the system after the Orchestrator.
Its DENY decision CANNOT be overridden by any other agent.

From 06_RISK_FRAMEWORK.txt:
If Risk Manager says no, the answer is NO.
"""
import structlog
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Optional
from dataclasses import dataclass, field

from app.agents.base_agent import BaseAgent, AgentMessage, AgentHealthStatus

logger = structlog.get_logger()


@dataclass
class PositionSizeResult:
    """Result of position sizing calculation."""
    approved: bool
    risk_amount_currency: float = 0.0
    risk_percent: float = 0.0
    lot_size: float = 0.0
    stop_distance_pips: float = 0.0
    effective_stop_pips: float = 0.0  # Including spread
    spread_cost_pct: float = 0.0
    regime_multiplier_applied: float = 1.0
    confidence_adjustment_applied: float = 1.0
    drawdown_mode: str = "normal"
    reasons: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


@dataclass
class RiskApproval:
    """Complete risk approval/denial for a trade."""
    approved: bool
    risk_mode: str = "normal"  # normal, reduced, defensive, halted
    position_sizing: Optional[PositionSizeResult] = None
    stop_approved: bool = False
    take_profit_approved: bool = False
    denial_reasons: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    adjustments_made: list = field(default_factory=list)
    
    # Portfolio impact
    current_open_risk_pct: float = 0.0
    after_trade_risk_pct: float = 0.0
    positions_same_direction: int = 0
    correlated_exposure: int = 0


# Default risk parameters
DEFAULT_RISK_PARAMS = {
    "default_risk_per_trade_pct": 0.35,
    "min_risk_per_trade_pct": 0.10,
    "max_risk_per_trade_pct": 0.50,
    "absolute_max_risk_per_trade_pct": 1.00,
    "max_daily_loss_pct": 2.00,
    "max_weekly_drawdown_pct": 4.00,
    "max_simultaneous_positions": 5,
    "max_positions_per_symbol": 1,
    "max_same_direction_positions": 3,
    "max_trades_per_symbol_per_day": 2,
    "max_total_new_trades_per_day": 6,
    "cooldown_after_consecutive_losses": 2,
    "cooldown_duration_minutes": 60,
    "min_risk_reward": 1.5,
    "max_spread_to_stop_ratio": 0.30,
}

# Spread limits per symbol (pips)
DEFAULT_SPREAD_LIMITS = {
    "EURUSD": 2.0,
    "GBPUSD": 2.5,
    "USDJPY": 2.0,
    "GBPJPY": 4.0,
    "USDCHF": 2.5,
    "USDCAD": 2.5,
    "EURAUD": 3.5,
    "AUDNZD": 3.5,
    "AUDUSD": 2.0,
}

# Risk mode multipliers
RISK_MODE_MULTIPLIERS = {
    "normal": 1.0,
    "reduced": 0.60,
    "defensive": 0.30,
    "halted": 0.0,
}


class RiskManagerAgent(BaseAgent):
    """
    Risk Manager Agent - The guardian of capital.
    
    CRITICAL: This agent's DENY cannot be overridden.
    
    Responsibilities:
    - Calculate position sizes
    - Enforce drawdown limits
    - Check portfolio concentration
    - Apply risk mode adjustments
    - Track consecutive losses
    """
    
    def __init__(
        self,
        name: str = "risk_manager_agent",
        config: Optional[dict[str, Any]] = None,
    ):
        super().__init__(name, config)
        
        # Risk parameters
        self.params = {**DEFAULT_RISK_PARAMS}
        if config and "risk_params" in config:
            self.params.update(config["risk_params"])
        
        self.spread_limits = {**DEFAULT_SPREAD_LIMITS}
        if config and "spread_limits" in config:
            self.spread_limits.update(config["spread_limits"])
        
        # State tracking
        self._risk_mode = "normal"
        self._daily_loss_pct = 0.0
        self._weekly_drawdown_pct = 0.0
        self._consecutive_losses = 0
        self._last_loss_time: Optional[datetime] = None
        self._trades_today: dict[str, int] = {}  # symbol -> count
        self._total_trades_today = 0
        self._open_positions: list[dict] = []
        
        # Kill switch state
        self._daily_halt = False
        self._weekly_halt = False
        self._system_halt = False
    
    async def initialize(self) -> None:
        """Initialize the agent."""
        self.is_initialized = True
        self.is_running = True
        self.started_at = datetime.now(timezone.utc)
        self._logger.info(
            "Risk Manager Agent initialized",
            risk_mode=self._risk_mode,
            max_daily_loss=self.params["max_daily_loss_pct"],
        )
    
    async def run(self, context: dict[str, Any]) -> AgentMessage:
        """
        Evaluate a trade for risk approval.
        
        Args:
            context: Must contain:
                - symbol: Trading symbol
                - direction: "long" or "short"
                - stop_loss: Stop loss price
                - entry_price: Entry price
                - take_profit: Take profit price (optional)
                - equity: Current account equity
                - regime_risk_multiplier: From Regime Agent
                - confidence: From Orchestrator
                - spread_pips: Current spread
        """
        symbol = context.get("symbol")
        direction = context.get("direction")
        stop_loss = context.get("stop_loss")
        entry_price = context.get("entry_price")
        
        if not all([symbol, direction, stop_loss, entry_price]):
            return self._create_message(
                message_type="risk_denial",
                payload={"error": "Missing required trade parameters"},
                symbol=symbol,
                confidence=0.0,
                errors=["Missing symbol, direction, stop_loss, or entry_price"],
            )
        
        # Evaluate risk
        approval = await self._evaluate_risk(context)
        
        return self._create_message(
            message_type="risk_approval" if approval.approved else "risk_denial",
            payload=self._approval_to_dict(approval),
            symbol=symbol,
            confidence=1.0 if approval.approved else 0.0,
            warnings=approval.warnings,
            errors=approval.denial_reasons if not approval.approved else [],
        )
    
    async def _evaluate_risk(self, context: dict[str, Any]) -> RiskApproval:
        """Perform full risk evaluation."""
        symbol = context["symbol"]
        direction = context["direction"]
        stop_loss = float(context["stop_loss"])
        entry_price = float(context["entry_price"])
        take_profit = context.get("take_profit")
        equity = float(context.get("equity", 10000))
        regime_multiplier = float(context.get("regime_risk_multiplier", 1.0))
        confidence = float(context.get("confidence", 0.5))
        spread_pips = float(context.get("spread_pips", 2.0))
        
        approval = RiskApproval(approved=True, risk_mode=self._risk_mode)
        
        # CHECK 1: System halt
        if self._system_halt:
            approval.approved = False
            approval.denial_reasons.append("SYSTEM HALT: Trading suspended until manual reset")
            return approval
        
        # CHECK 2: Daily halt
        if self._daily_halt:
            approval.approved = False
            approval.denial_reasons.append("DAILY HALT: Daily loss limit reached")
            return approval
        
        # CHECK 3: Weekly halt
        if self._weekly_halt:
            approval.approved = False
            approval.denial_reasons.append("WEEKLY HALT: Weekly drawdown limit reached")
            return approval
        
        # CHECK 4: Regime risk multiplier
        if regime_multiplier == 0.0:
            approval.approved = False
            approval.denial_reasons.append("REGIME BLOCKED: Unfavorable market regime")
            return approval
        
        # CHECK 5: Spread limit
        max_spread = self.spread_limits.get(symbol, 3.0)
        if spread_pips > max_spread:
            approval.approved = False
            approval.denial_reasons.append(
                f"SPREAD TOO HIGH: {spread_pips:.1f} pips > limit {max_spread} pips"
            )
            return approval
        
        # CHECK 6: Symbol daily limit
        symbol_trades = self._trades_today.get(symbol, 0)
        if symbol_trades >= self.params["max_trades_per_symbol_per_day"]:
            approval.approved = False
            approval.denial_reasons.append(
                f"SYMBOL LIMIT: Already {symbol_trades} trades on {symbol} today"
            )
            return approval
        
        # CHECK 7: Total daily limit
        if self._total_trades_today >= self.params["max_total_new_trades_per_day"]:
            approval.approved = False
            approval.denial_reasons.append(
                f"DAILY LIMIT: Already {self._total_trades_today} trades today"
            )
            return approval
        
        # CHECK 8: Position limit per symbol
        symbol_positions = sum(1 for p in self._open_positions if p.get("symbol") == symbol)
        if symbol_positions >= self.params["max_positions_per_symbol"]:
            approval.approved = False
            approval.denial_reasons.append(
                f"POSITION LIMIT: Already have position on {symbol}"
            )
            return approval
        
        # CHECK 9: Total positions
        if len(self._open_positions) >= self.params["max_simultaneous_positions"]:
            approval.approved = False
            approval.denial_reasons.append(
                f"MAX POSITIONS: Already at {len(self._open_positions)} positions"
            )
            return approval
        
        # CHECK 10: Same direction limit
        same_direction = sum(
            1 for p in self._open_positions if p.get("direction") == direction
        )
        approval.positions_same_direction = same_direction
        if same_direction >= self.params["max_same_direction_positions"]:
            approval.approved = False
            approval.denial_reasons.append(
                f"DIRECTION LIMIT: Already {same_direction} {direction} positions"
            )
            return approval
        
        # CHECK 11: Consecutive loss cooldown
        if self._consecutive_losses >= self.params["cooldown_after_consecutive_losses"]:
            if self._last_loss_time:
                cooldown_end = self._last_loss_time + timedelta(
                    minutes=self.params["cooldown_duration_minutes"]
                )
                if datetime.now(timezone.utc) < cooldown_end:
                    remaining = (cooldown_end - datetime.now(timezone.utc)).seconds // 60
                    approval.approved = False
                    approval.denial_reasons.append(
                        f"COOLDOWN: {remaining} minutes remaining after {self._consecutive_losses} consecutive losses"
                    )
                    return approval
        
        # Calculate stop distance
        stop_distance = abs(entry_price - stop_loss)
        stop_distance_pips = stop_distance / 0.0001  # Simplified pip calc
        
        # CHECK 12: Valid stop distance
        if stop_distance_pips < 5:
            approval.approved = False
            approval.denial_reasons.append(
                f"STOP TOO TIGHT: {stop_distance_pips:.1f} pips is too small"
            )
            return approval
        
        # CHECK 13: Spread to stop ratio
        spread_ratio = spread_pips / stop_distance_pips
        if spread_ratio > self.params["max_spread_to_stop_ratio"]:
            approval.approved = False
            approval.denial_reasons.append(
                f"SPREAD/STOP RATIO: {spread_ratio:.0%} > {self.params['max_spread_to_stop_ratio']:.0%}"
            )
            return approval
        
        # CHECK 14: Risk:Reward
        if take_profit:
            tp_distance = abs(float(take_profit) - entry_price)
            rr_ratio = tp_distance / stop_distance if stop_distance > 0 else 0
            if rr_ratio < self.params["min_risk_reward"]:
                approval.warnings.append(
                    f"LOW R:R: {rr_ratio:.2f} below preferred {self.params['min_risk_reward']}"
                )
                # Not a hard denial, but warn
            approval.take_profit_approved = rr_ratio >= self.params["min_risk_reward"]
        
        approval.stop_approved = True
        
        # CALCULATE POSITION SIZE
        sizing = self._calculate_position_size(
            equity=equity,
            stop_distance_pips=stop_distance_pips,
            spread_pips=spread_pips,
            regime_multiplier=regime_multiplier,
            confidence=confidence,
        )
        
        approval.position_sizing = sizing
        
        if not sizing.approved:
            approval.approved = False
            approval.denial_reasons.extend(sizing.reasons)
            return approval
        
        # Track portfolio impact
        current_risk = sum(p.get("risk_pct", 0) for p in self._open_positions)
        approval.current_open_risk_pct = current_risk
        approval.after_trade_risk_pct = current_risk + sizing.risk_percent
        
        # Final check: aggregate risk
        max_aggregate = self.params["absolute_max_risk_per_trade_pct"] * 3
        if approval.after_trade_risk_pct > max_aggregate:
            approval.approved = False
            approval.denial_reasons.append(
                f"AGGREGATE RISK: {approval.after_trade_risk_pct:.2f}% > limit {max_aggregate:.2f}%"
            )
            return approval
        
        # Apply any adjustments
        if sizing.regime_multiplier_applied < 1.0:
            approval.adjustments_made.append(
                f"Regime multiplier: {sizing.regime_multiplier_applied:.0%}"
            )
        if sizing.confidence_adjustment_applied < 1.0:
            approval.adjustments_made.append(
                f"Confidence adjustment: {sizing.confidence_adjustment_applied:.0%}"
            )
        if self._risk_mode != "normal":
            approval.adjustments_made.append(f"Risk mode: {self._risk_mode}")
        
        return approval
    
    def _calculate_position_size(
        self,
        equity: float,
        stop_distance_pips: float,
        spread_pips: float,
        regime_multiplier: float,
        confidence: float,
    ) -> PositionSizeResult:
        """Calculate position size with all adjustments."""
        result = PositionSizeResult(approved=True)
        
        # Base risk
        base_risk_pct = self.params["default_risk_per_trade_pct"]
        
        # Apply regime multiplier
        adjusted_risk = base_risk_pct * regime_multiplier
        result.regime_multiplier_applied = regime_multiplier
        
        # Apply confidence adjustment
        if confidence < 0.7:
            adjusted_risk *= 0.75
            result.confidence_adjustment_applied = 0.75
        elif confidence < 0.6:
            adjusted_risk *= 0.50
            result.confidence_adjustment_applied = 0.50
        else:
            result.confidence_adjustment_applied = 1.0
        
        # Apply risk mode
        mode_multiplier = RISK_MODE_MULTIPLIERS.get(self._risk_mode, 1.0)
        adjusted_risk *= mode_multiplier
        result.drawdown_mode = self._risk_mode
        
        # Clamp to limits
        adjusted_risk = max(
            self.params["min_risk_per_trade_pct"],
            min(adjusted_risk, self.params["max_risk_per_trade_pct"])
        )
        
        result.risk_percent = adjusted_risk
        
        # Calculate risk amount in currency
        result.risk_amount_currency = equity * (adjusted_risk / 100)
        
        # Calculate effective stop (including spread)
        result.stop_distance_pips = stop_distance_pips
        result.effective_stop_pips = stop_distance_pips + spread_pips
        
        # Spread cost as percentage of stop
        result.spread_cost_pct = (spread_pips / stop_distance_pips) * 100 if stop_distance_pips > 0 else 0
        
        # Calculate lots (simplified - assumes $10/pip for standard lot)
        pip_value = 10.0  # Simplified, should be calculated per symbol
        result.lot_size = result.risk_amount_currency / (result.effective_stop_pips * pip_value)
        
        # Round to valid lot size
        result.lot_size = round(result.lot_size, 2)
        
        # Minimum lot check
        if result.lot_size < 0.01:
            result.approved = False
            result.reasons.append(
                f"Position size too small: {result.lot_size:.4f} lots < 0.01 minimum"
            )
            return result
        
        # Maximum lot check (configurable)
        max_lots = 10.0  # Should be from config
        if result.lot_size > max_lots:
            result.lot_size = max_lots
            result.warnings.append(f"Lot size capped at maximum {max_lots}")
        
        return result
    
    def _approval_to_dict(self, approval: RiskApproval) -> dict:
        """Convert approval to serializable dict."""
        sizing_dict = None
        if approval.position_sizing:
            sizing_dict = {
                "approved": approval.position_sizing.approved,
                "risk_amount_currency": approval.position_sizing.risk_amount_currency,
                "risk_percent": approval.position_sizing.risk_percent,
                "lot_size": approval.position_sizing.lot_size,
                "stop_distance_pips": approval.position_sizing.stop_distance_pips,
                "effective_stop_pips": approval.position_sizing.effective_stop_pips,
                "spread_cost_pct": approval.position_sizing.spread_cost_pct,
                "regime_multiplier_applied": approval.position_sizing.regime_multiplier_applied,
                "confidence_adjustment_applied": approval.position_sizing.confidence_adjustment_applied,
                "drawdown_mode": approval.position_sizing.drawdown_mode,
            }
        
        return {
            "approved": approval.approved,
            "risk_mode": approval.risk_mode,
            "position_sizing": sizing_dict,
            "stop_approved": approval.stop_approved,
            "take_profit_approved": approval.take_profit_approved,
            "denial_reasons": approval.denial_reasons,
            "warnings": approval.warnings,
            "adjustments_made": approval.adjustments_made,
            "current_open_risk_pct": approval.current_open_risk_pct,
            "after_trade_risk_pct": approval.after_trade_risk_pct,
            "positions_same_direction": approval.positions_same_direction,
        }
    
    # ============ State Management Methods ============
    
    def record_trade_result(self, is_win: bool, pnl_pct: float) -> None:
        """Record a trade result for tracking."""
        if is_win:
            self._consecutive_losses = 0
        else:
            self._consecutive_losses += 1
            self._last_loss_time = datetime.now(timezone.utc)
            self._daily_loss_pct += abs(pnl_pct)
            self._weekly_drawdown_pct += abs(pnl_pct)
        
        # Check limits
        if self._daily_loss_pct >= self.params["max_daily_loss_pct"]:
            self._daily_halt = True
            self._logger.warning("DAILY HALT ACTIVATED", loss_pct=self._daily_loss_pct)
        
        if self._weekly_drawdown_pct >= self.params["max_weekly_drawdown_pct"]:
            self._weekly_halt = True
            self._logger.warning("WEEKLY HALT ACTIVATED", drawdown_pct=self._weekly_drawdown_pct)
        
        # Update risk mode
        self._update_risk_mode()
    
    def _update_risk_mode(self) -> None:
        """Update risk mode based on current state."""
        daily_pct = self._daily_loss_pct / self.params["max_daily_loss_pct"] * 100
        weekly_pct = self._weekly_drawdown_pct / self.params["max_weekly_drawdown_pct"] * 100
        
        if daily_pct > 75 or weekly_pct > 75:
            self._risk_mode = "defensive"
        elif daily_pct > 50 or weekly_pct > 50:
            self._risk_mode = "reduced"
        else:
            self._risk_mode = "normal"
    
    def add_position(self, position: dict) -> None:
        """Track a new position."""
        self._open_positions.append(position)
        symbol = position.get("symbol", "")
        self._trades_today[symbol] = self._trades_today.get(symbol, 0) + 1
        self._total_trades_today += 1
    
    def remove_position(self, ticket: int) -> None:
        """Remove a closed position."""
        self._open_positions = [p for p in self._open_positions if p.get("ticket") != ticket]
    
    def reset_daily_counters(self) -> None:
        """Reset daily counters (call at day start)."""
        self._trades_today = {}
        self._total_trades_today = 0
        self._daily_loss_pct = 0.0
        self._daily_halt = False
        self._update_risk_mode()
    
    def reset_weekly_counters(self) -> None:
        """Reset weekly counters (call at week start)."""
        self._weekly_drawdown_pct = 0.0
        self._weekly_halt = False
        self._update_risk_mode()
    
    def activate_system_halt(self, reason: str) -> None:
        """Activate system-wide trading halt."""
        self._system_halt = True
        self._risk_mode = "halted"
        self._logger.critical("SYSTEM HALT ACTIVATED", reason=reason)
    
    def deactivate_system_halt(self) -> None:
        """Deactivate system halt (requires manual intervention)."""
        self._system_halt = False
        self._update_risk_mode()
        self._logger.info("System halt deactivated")
    
    async def health_check(self) -> AgentHealthStatus:
        return AgentHealthStatus(
            agent_name=self.name,
            is_healthy=self.is_initialized and not self._system_halt,
            last_run=self.last_run,
            last_success=self.last_success,
            last_error=self.last_error,
            consecutive_failures=self.consecutive_failures,
            uptime_seconds=self._get_uptime_seconds(),
        )
    
    def get_dependencies(self) -> list[str]:
        return []  # Risk manager has no agent dependencies
