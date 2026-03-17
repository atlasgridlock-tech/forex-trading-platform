"""
Comprehensive Risk Management Framework
Dynamic risk sizing with daily discipline rules
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set
from enum import Enum
from datetime import datetime, date, timedelta
import json


class RiskMode(str, Enum):
    """System-wide risk modes."""
    NORMAL = "normal"           # Standard risk: 0.25-0.50%
    REDUCED = "reduced"         # Elevated caution: 0.15-0.25%
    DEFENSIVE = "defensive"     # High caution: 0.10-0.15%
    HALTED = "halted"          # No new trades: 0%


class DrawdownState(str, Enum):
    """Current drawdown status."""
    NORMAL = "normal"           # DD < 1%
    ELEVATED = "elevated"       # DD 1-2%
    WARNING = "warning"         # DD 2-4%
    CRITICAL = "critical"       # DD 4-6%
    HALT = "halt"              # DD > 6%


@dataclass
class DailyDiscipline:
    """Daily trading discipline state."""
    date: date
    
    # Trade counts
    trades_today: int = 0
    trades_per_symbol: Dict[str, int] = field(default_factory=dict)
    max_trades_per_symbol: int = 3
    max_trades_total: int = 10
    
    # Risk exposure
    new_risk_today: float = 0  # Total new risk added today
    max_new_risk_daily: float = 1.5  # Max 1.5% new risk per day
    
    # Loss tracking
    losses_today: int = 0
    consecutive_losses: int = 0
    daily_pnl: float = 0  # In account %
    
    # Discipline flags
    stop_after_losses: int = 2  # Stop trading after N consecutive losses
    cooldown_after_loss: int = 30  # Minutes cooldown after loss
    last_loss_time: Optional[datetime] = None
    no_trade_after_daily_loss: float = -2.0  # Stop if daily P&L hits this %
    
    # Block reasons
    blocked: bool = False
    block_reasons: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "trades_today": self.trades_today,
            "trades_per_symbol": self.trades_per_symbol,
            "new_risk_today": self.new_risk_today,
            "losses_today": self.losses_today,
            "consecutive_losses": self.consecutive_losses,
            "daily_pnl": self.daily_pnl,
            "blocked": self.blocked,
            "block_reasons": self.block_reasons,
        }


@dataclass
class PositionRisk:
    """Risk assessment for a single position."""
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    position_size: float
    
    risk_pips: float = 0
    risk_currency: float = 0
    risk_percent: float = 0
    
    # Currency exposure
    base_currency: str = ""
    quote_currency: str = ""
    base_exposure: float = 0
    quote_exposure: float = 0
    
    # Correlation
    correlated_with: List[str] = field(default_factory=list)
    theme: str = ""  # risk_on, risk_off, dollar, carry, etc.


@dataclass
class PortfolioRisk:
    """Aggregate portfolio risk."""
    timestamp: datetime
    
    # Position count
    open_positions: int = 0
    pending_orders: int = 0
    
    # Risk exposure
    total_risk_percent: float = 0  # Sum of all position risks
    max_single_risk: float = 0     # Largest single position risk
    
    # Currency exposure
    currency_exposure: Dict[str, float] = field(default_factory=dict)
    max_currency_exposure: float = 1.5  # Max 1.5% per currency
    
    # Theme exposure
    theme_exposure: Dict[str, float] = field(default_factory=dict)
    max_theme_risk: float = 1.0  # Max 1% same-theme risk
    
    # Correlation
    correlated_groups: List[List[str]] = field(default_factory=list)
    
    # Drawdown
    drawdown_state: DrawdownState = DrawdownState.NORMAL
    current_drawdown: float = 0
    peak_equity: float = 0
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "open_positions": self.open_positions,
            "total_risk_percent": self.total_risk_percent,
            "currency_exposure": self.currency_exposure,
            "theme_exposure": self.theme_exposure,
            "drawdown_state": self.drawdown_state.value,
            "current_drawdown": self.current_drawdown,
        }


@dataclass
class RiskDecision:
    """Risk decision for a proposed trade."""
    symbol: str
    direction: str
    
    # Decision
    approved: bool = False
    position_size: float = 0
    risk_percent: float = 0
    
    # Adjustments made
    base_risk: float = 0.25  # Starting risk
    final_risk: float = 0.25
    adjustments: List[str] = field(default_factory=list)
    
    # Rejection reasons
    rejected: bool = False
    rejection_reasons: List[str] = field(default_factory=list)
    
    # Warnings
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "approved": self.approved,
            "position_size": self.position_size,
            "risk_percent": self.risk_percent,
            "base_risk": self.base_risk,
            "final_risk": self.final_risk,
            "adjustments": self.adjustments,
            "rejected": self.rejected,
            "rejection_reasons": self.rejection_reasons,
            "warnings": self.warnings,
        }


class RiskFramework:
    """
    Comprehensive Risk Management Framework
    
    Features:
    - Dynamic risk sizing based on conditions
    - Daily discipline rules
    - Currency and theme exposure tracking
    - Drawdown management
    - Correlation analysis
    """
    
    # Risk parameters
    DEFAULT_RISK = 0.25          # 0.25% default
    MAX_RISK_NORMAL = 0.50       # 0.50% max in normal mode
    MAX_RISK_REDUCED = 0.25      # 0.25% max in reduced mode
    MAX_RISK_DEFENSIVE = 0.15    # 0.15% max in defensive mode
    ABSOLUTE_MAX_RISK = 1.0      # Never exceed 1% per trade
    
    # Drawdown thresholds
    DRAWDOWN_REDUCED = 2.0       # Switch to reduced mode at 2% DD
    DRAWDOWN_DEFENSIVE = 4.0     # Switch to defensive mode at 4% DD
    DRAWDOWN_HALT = 8.0          # Halt trading at 8% DD
    
    # Daily limits
    MAX_TRADES_PER_SYMBOL = 3
    MAX_TRADES_TOTAL = 10
    MAX_NEW_RISK_DAILY = 1.5     # 1.5% max new risk per day
    
    # Correlation groups
    CORRELATED_PAIRS = {
        "USD": ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD"],
        "EUR": ["EURUSD", "EURGBP", "EURJPY", "EURAUD", "EURNZD", "EURCHF", "EURCAD"],
        "GBP": ["GBPUSD", "EURGBP", "GBPJPY", "GBPAUD", "GBPNZD", "GBPCHF", "GBPCAD"],
        "JPY": ["USDJPY", "EURJPY", "GBPJPY", "AUDJPY", "NZDJPY", "CADJPY", "CHFJPY"],
        "risk_on": ["AUDUSD", "NZDUSD", "AUDJPY", "NZDJPY"],
        "risk_off": ["USDJPY", "USDCHF", "CHFJPY"],
        "dollar": ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD"],
    }
    
    def __init__(self, account_balance: float = 10000):
        self.account_balance = account_balance
        self.peak_equity = account_balance
        self.current_equity = account_balance
        
        self.risk_mode = RiskMode.NORMAL
        self.drawdown_state = DrawdownState.NORMAL
        
        self.positions: Dict[str, PositionRisk] = {}
        self.daily_discipline = DailyDiscipline(date=date.today())
        
        self.portfolio_risk = PortfolioRisk(timestamp=datetime.utcnow())
    
    def update_equity(self, equity: float):
        """Update current equity and drawdown state."""
        self.current_equity = equity
        
        if equity > self.peak_equity:
            self.peak_equity = equity
        
        # Calculate drawdown
        dd_pct = ((self.peak_equity - equity) / self.peak_equity) * 100
        self.portfolio_risk.current_drawdown = dd_pct
        
        # Update drawdown state
        if dd_pct >= self.DRAWDOWN_HALT:
            self.drawdown_state = DrawdownState.HALT
            self.risk_mode = RiskMode.HALTED
        elif dd_pct >= self.DRAWDOWN_DEFENSIVE:
            self.drawdown_state = DrawdownState.CRITICAL
            self.risk_mode = RiskMode.DEFENSIVE
        elif dd_pct >= self.DRAWDOWN_REDUCED:
            self.drawdown_state = DrawdownState.WARNING
            self.risk_mode = RiskMode.REDUCED
        elif dd_pct >= 1.0:
            self.drawdown_state = DrawdownState.ELEVATED
        else:
            self.drawdown_state = DrawdownState.NORMAL
            # Don't auto-upgrade from defensive/reduced without manual reset
    
    def reset_daily_discipline(self):
        """Reset daily discipline for new trading day."""
        today = date.today()
        if self.daily_discipline.date != today:
            self.daily_discipline = DailyDiscipline(date=today)
    
    def record_trade_result(self, symbol: str, pnl_percent: float, won: bool):
        """Record a trade result for discipline tracking."""
        self.reset_daily_discipline()
        
        self.daily_discipline.daily_pnl += pnl_percent
        
        if not won:
            self.daily_discipline.losses_today += 1
            self.daily_discipline.consecutive_losses += 1
            self.daily_discipline.last_loss_time = datetime.utcnow()
        else:
            self.daily_discipline.consecutive_losses = 0
        
        # Check daily loss limit
        if self.daily_discipline.daily_pnl <= self.daily_discipline.no_trade_after_daily_loss:
            self.daily_discipline.blocked = True
            self.daily_discipline.block_reasons.append(
                f"Daily loss limit hit ({self.daily_discipline.daily_pnl:.2f}%)"
            )
    
    def calculate_risk_adjustment(
        self,
        symbol: str,
        direction: str,
        regime_stable: bool = True,
        macro_aligned: bool = True,
        spread_normal: bool = True,
        execution_quality: str = "good"
    ) -> Tuple[float, List[str]]:
        """
        Calculate risk adjustment based on conditions.
        
        Returns: (adjusted_risk_pct, list_of_adjustments)
        """
        adjustments = []
        
        # Start with base risk based on mode
        if self.risk_mode == RiskMode.NORMAL:
            risk = self.DEFAULT_RISK
            max_risk = self.MAX_RISK_NORMAL
        elif self.risk_mode == RiskMode.REDUCED:
            risk = 0.15
            max_risk = self.MAX_RISK_REDUCED
        elif self.risk_mode == RiskMode.DEFENSIVE:
            risk = 0.10
            max_risk = self.MAX_RISK_DEFENSIVE
        else:  # HALTED
            return 0, ["Trading halted"]
        
        adjustments.append(f"Base risk: {risk:.2f}% ({self.risk_mode.value} mode)")
        
        # Adjustment 1: Unstable regime → reduce 30%
        if not regime_stable:
            risk *= 0.70
            adjustments.append("Unstable regime: -30%")
        
        # Adjustment 2: Macro misalignment → reduce 25%
        if not macro_aligned:
            risk *= 0.75
            adjustments.append("Macro misalignment: -25%")
        
        # Adjustment 3: Wide spread → reduce 20%
        if not spread_normal:
            risk *= 0.80
            adjustments.append("Wide spread: -20%")
        
        # Adjustment 4: Poor execution quality → reduce 15%
        if execution_quality == "poor":
            risk *= 0.85
            adjustments.append("Poor execution: -15%")
        elif execution_quality == "uncertain":
            risk *= 0.90
            adjustments.append("Uncertain execution: -10%")
        
        # Adjustment 5: Drawdown state
        if self.drawdown_state == DrawdownState.ELEVATED:
            risk *= 0.90
            adjustments.append("Elevated drawdown: -10%")
        elif self.drawdown_state == DrawdownState.WARNING:
            risk *= 0.75
            adjustments.append("Warning drawdown: -25%")
        elif self.drawdown_state == DrawdownState.CRITICAL:
            risk *= 0.50
            adjustments.append("Critical drawdown: -50%")
        
        # Adjustment 6: Consecutive losses
        if self.daily_discipline.consecutive_losses >= 2:
            risk *= 0.75
            adjustments.append(f"{self.daily_discipline.consecutive_losses} consecutive losses: -25%")
        
        # Cap at max for mode
        if risk > max_risk:
            risk = max_risk
            adjustments.append(f"Capped at {max_risk:.2f}%")
        
        # Absolute floor
        risk = max(risk, 0.05)  # Minimum 0.05%
        
        return round(risk, 3), adjustments
    
    def check_currency_exposure(
        self,
        symbol: str,
        direction: str,
        proposed_risk: float
    ) -> Tuple[bool, List[str]]:
        """Check if adding this trade would exceed currency exposure limits."""
        warnings = []
        
        base = symbol[:3]
        quote = symbol[3:]
        
        # Calculate current exposure
        current_exposure = self.portfolio_risk.currency_exposure.copy()
        
        # Add proposed exposure
        if direction == "long":
            current_exposure[base] = current_exposure.get(base, 0) + proposed_risk
            current_exposure[quote] = current_exposure.get(quote, 0) - proposed_risk
        else:
            current_exposure[base] = current_exposure.get(base, 0) - proposed_risk
            current_exposure[quote] = current_exposure.get(quote, 0) + proposed_risk
        
        # Check limits
        for ccy, exposure in current_exposure.items():
            if abs(exposure) > self.portfolio_risk.max_currency_exposure:
                warnings.append(
                    f"{ccy} exposure would be {exposure:.2f}% (max {self.portfolio_risk.max_currency_exposure}%)"
                )
        
        return len(warnings) == 0, warnings
    
    def check_theme_exposure(
        self,
        symbol: str,
        direction: str,
        proposed_risk: float
    ) -> Tuple[bool, List[str]]:
        """Check if adding this trade would exceed theme risk limits."""
        warnings = []
        
        # Identify themes for this pair
        themes = []
        for theme, pairs in self.CORRELATED_PAIRS.items():
            if symbol in pairs and theme in ["risk_on", "risk_off", "dollar"]:
                themes.append(theme)
        
        # Check theme exposure
        current_theme_risk = self.portfolio_risk.theme_exposure.copy()
        
        for theme in themes:
            current = current_theme_risk.get(theme, 0)
            new_exposure = current + proposed_risk
            
            if new_exposure > self.portfolio_risk.max_theme_risk:
                warnings.append(
                    f"{theme} theme risk would be {new_exposure:.2f}% (max {self.portfolio_risk.max_theme_risk}%)"
                )
        
        return len(warnings) == 0, warnings
    
    def check_correlation(
        self,
        symbol: str,
        direction: str
    ) -> Tuple[bool, List[str]]:
        """Check for correlated existing positions."""
        warnings = []
        
        base = symbol[:3]
        quote = symbol[3:]
        
        # Check existing positions with same currencies
        for pos_symbol, pos in self.positions.items():
            if pos_symbol == symbol:
                continue
            
            pos_base = pos_symbol[:3]
            pos_quote = pos_symbol[3:]
            
            # Same base currency
            if base == pos_base or base == pos_quote or quote == pos_base or quote == pos_quote:
                warnings.append(f"Correlated with existing {pos_symbol} {pos.direction}")
        
        return len(warnings) <= 1, warnings  # Allow 1 correlated position
    
    def check_daily_discipline(self, symbol: str) -> Tuple[bool, List[str]]:
        """Check daily discipline rules."""
        self.reset_daily_discipline()
        
        reasons = []
        
        # Check if blocked
        if self.daily_discipline.blocked:
            return False, self.daily_discipline.block_reasons
        
        # Check max trades per symbol
        symbol_trades = self.daily_discipline.trades_per_symbol.get(symbol, 0)
        if symbol_trades >= self.daily_discipline.max_trades_per_symbol:
            reasons.append(f"Max trades for {symbol} reached ({symbol_trades})")
        
        # Check max total trades
        if self.daily_discipline.trades_today >= self.daily_discipline.max_trades_total:
            reasons.append(f"Max daily trades reached ({self.daily_discipline.trades_today})")
        
        # Check consecutive losses
        if self.daily_discipline.consecutive_losses >= self.daily_discipline.stop_after_losses:
            reasons.append(
                f"Stop after {self.daily_discipline.stop_after_losses} losses triggered"
            )
        
        # Check cooldown after loss
        if self.daily_discipline.last_loss_time:
            cooldown_end = self.daily_discipline.last_loss_time + timedelta(
                minutes=self.daily_discipline.cooldown_after_loss
            )
            if datetime.utcnow() < cooldown_end:
                remaining = (cooldown_end - datetime.utcnow()).seconds // 60
                reasons.append(f"Loss cooldown: {remaining} minutes remaining")
        
        # Check daily risk limit
        if self.daily_discipline.new_risk_today >= self.daily_discipline.max_new_risk_daily:
            reasons.append(
                f"Daily new risk limit reached ({self.daily_discipline.new_risk_today:.2f}%)"
            )
        
        return len(reasons) == 0, reasons
    
    def calculate_position_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        risk_percent: float
    ) -> float:
        """Calculate position size based on risk."""
        # Calculate pips at risk
        pip_value = 0.0001 if "JPY" not in symbol else 0.01
        pips_at_risk = abs(entry_price - stop_loss) / pip_value
        
        if pips_at_risk == 0:
            return 0
        
        # Risk in currency
        risk_amount = self.current_equity * (risk_percent / 100)
        
        # Pip value (simplified - would need actual conversion in production)
        # Assuming standard lot where 1 pip = $10 for majors
        pip_value_per_lot = 10.0
        
        # Position size in lots
        position_size = risk_amount / (pips_at_risk * pip_value_per_lot)
        
        # Round to 2 decimal places
        return round(position_size, 2)
    
    def evaluate_trade(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        regime_stable: bool = True,
        macro_aligned: bool = True,
        spread_normal: bool = True,
        execution_quality: str = "good"
    ) -> RiskDecision:
        """
        Comprehensive trade risk evaluation.
        
        Checks all risk rules and returns decision with sizing.
        """
        decision = RiskDecision(symbol=symbol, direction=direction)
        
        # 1. Check if trading is halted
        if self.risk_mode == RiskMode.HALTED:
            decision.rejected = True
            decision.rejection_reasons.append("Trading halted due to drawdown")
            return decision
        
        # 2. Check daily discipline
        discipline_ok, discipline_reasons = self.check_daily_discipline(symbol)
        if not discipline_ok:
            decision.rejected = True
            decision.rejection_reasons.extend(discipline_reasons)
            return decision
        
        # 3. Calculate adjusted risk
        adjusted_risk, adjustments = self.calculate_risk_adjustment(
            symbol, direction, regime_stable, macro_aligned, spread_normal, execution_quality
        )
        decision.base_risk = self.DEFAULT_RISK
        decision.final_risk = adjusted_risk
        decision.adjustments = adjustments
        
        # 4. Check currency exposure
        currency_ok, currency_warnings = self.check_currency_exposure(
            symbol, direction, adjusted_risk
        )
        if not currency_ok:
            decision.rejected = True
            decision.rejection_reasons.extend(currency_warnings)
            return decision
        if currency_warnings:
            decision.warnings.extend(currency_warnings)
        
        # 5. Check theme exposure
        theme_ok, theme_warnings = self.check_theme_exposure(
            symbol, direction, adjusted_risk
        )
        if not theme_ok:
            decision.rejected = True
            decision.rejection_reasons.extend(theme_warnings)
            return decision
        if theme_warnings:
            decision.warnings.extend(theme_warnings)
        
        # 6. Check correlation
        correlation_ok, correlation_warnings = self.check_correlation(symbol, direction)
        if not correlation_ok:
            # Don't reject, but warn and reduce risk
            adjusted_risk *= 0.75
            decision.adjustments.append("Correlation reduction: -25%")
        if correlation_warnings:
            decision.warnings.extend(correlation_warnings)
        
        # 7. Check if adding this exceeds daily risk limit
        if self.daily_discipline.new_risk_today + adjusted_risk > self.daily_discipline.max_new_risk_daily:
            # Reduce to fit within limit
            available = self.daily_discipline.max_new_risk_daily - self.daily_discipline.new_risk_today
            if available > 0.05:  # Minimum viable risk
                adjusted_risk = available
                decision.adjustments.append(f"Reduced to fit daily limit: {adjusted_risk:.2f}%")
            else:
                decision.rejected = True
                decision.rejection_reasons.append("Daily risk limit would be exceeded")
                return decision
        
        # 8. Validate stop loss exists
        if stop_loss == 0 or stop_loss == entry_price:
            decision.rejected = True
            decision.rejection_reasons.append("Invalid or missing stop loss")
            return decision
        
        # 9. Calculate position size
        position_size = self.calculate_position_size(
            symbol, entry_price, stop_loss, adjusted_risk
        )
        
        if position_size < 0.01:
            decision.rejected = True
            decision.rejection_reasons.append("Position size too small")
            return decision
        
        # Approved!
        decision.approved = True
        decision.position_size = position_size
        decision.risk_percent = adjusted_risk
        decision.final_risk = adjusted_risk
        
        return decision
    
    def approve_trade(self, decision: RiskDecision):
        """Record an approved trade in the system."""
        if not decision.approved:
            return
        
        self.reset_daily_discipline()
        
        # Update daily tracking
        self.daily_discipline.trades_today += 1
        self.daily_discipline.trades_per_symbol[decision.symbol] = \
            self.daily_discipline.trades_per_symbol.get(decision.symbol, 0) + 1
        self.daily_discipline.new_risk_today += decision.risk_percent
        
        # Update portfolio risk tracking
        self.portfolio_risk.total_risk_percent += decision.risk_percent
        self.portfolio_risk.open_positions += 1
        
        # Update currency exposure
        base = decision.symbol[:3]
        quote = decision.symbol[3:]
        if decision.direction == "long":
            self.portfolio_risk.currency_exposure[base] = \
                self.portfolio_risk.currency_exposure.get(base, 0) + decision.risk_percent
            self.portfolio_risk.currency_exposure[quote] = \
                self.portfolio_risk.currency_exposure.get(quote, 0) - decision.risk_percent
        else:
            self.portfolio_risk.currency_exposure[base] = \
                self.portfolio_risk.currency_exposure.get(base, 0) - decision.risk_percent
            self.portfolio_risk.currency_exposure[quote] = \
                self.portfolio_risk.currency_exposure.get(quote, 0) + decision.risk_percent
    
    def get_status(self) -> dict:
        """Get current risk framework status."""
        return {
            "risk_mode": self.risk_mode.value,
            "drawdown_state": self.drawdown_state.value,
            "current_drawdown": self.portfolio_risk.current_drawdown,
            "account_balance": self.account_balance,
            "current_equity": self.current_equity,
            "peak_equity": self.peak_equity,
            "open_positions": self.portfolio_risk.open_positions,
            "total_risk_percent": self.portfolio_risk.total_risk_percent,
            "currency_exposure": self.portfolio_risk.currency_exposure,
            "daily_discipline": self.daily_discipline.to_dict(),
            "max_risk_current_mode": {
                RiskMode.NORMAL: self.MAX_RISK_NORMAL,
                RiskMode.REDUCED: self.MAX_RISK_REDUCED,
                RiskMode.DEFENSIVE: self.MAX_RISK_DEFENSIVE,
                RiskMode.HALTED: 0,
            }.get(self.risk_mode, 0),
        }
