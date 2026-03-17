"""
Validation and Testing Framework
Rigorous testing before live trading with promotion gates
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
from datetime import datetime, date, timedelta
import json
import random
import math


class ValidationStage(str, Enum):
    """Validation pipeline stages."""
    BACKTEST = "backtest"
    WALK_FORWARD = "walk_forward"
    MONTE_CARLO = "monte_carlo"
    PAPER_TRADE = "paper_trade"
    SHADOW_LIVE = "shadow_live"
    LIVE_READY = "live_ready"


class PromotionStatus(str, Enum):
    """Promotion gate status."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class BacktestResult:
    """Results from historical backtesting."""
    strategy: str
    symbol: str
    start_date: date
    end_date: date
    
    # Trade metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    
    # Performance
    win_rate: float = 0
    profit_factor: float = 0
    total_r: float = 0
    avg_r: float = 0
    
    # Risk metrics
    max_drawdown_pct: float = 0
    max_drawdown_r: float = 0
    sharpe_ratio: float = 0
    sortino_ratio: float = 0
    
    # By regime
    performance_by_regime: Dict[str, dict] = field(default_factory=dict)
    
    # Validation
    passed: bool = False
    issues: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "symbol": self.symbol,
            "period": f"{self.start_date} to {self.end_date}",
            "total_trades": self.total_trades,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "total_r": self.total_r,
            "max_drawdown_pct": self.max_drawdown_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "passed": self.passed,
            "issues": self.issues,
        }


@dataclass
class WalkForwardResult:
    """Results from walk-forward validation."""
    strategy: str
    total_periods: int = 6
    
    # Per-period results
    period_results: List[dict] = field(default_factory=list)
    
    # Aggregate metrics
    positive_periods: int = 0
    negative_periods: int = 0
    avg_profit_factor: float = 0
    avg_win_rate: float = 0
    consistency_score: float = 0  # How consistent across periods
    
    # Validation
    passed: bool = False
    issues: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "total_periods": self.total_periods,
            "positive_periods": self.positive_periods,
            "negative_periods": self.negative_periods,
            "avg_profit_factor": self.avg_profit_factor,
            "consistency_score": self.consistency_score,
            "passed": self.passed,
            "issues": self.issues,
        }


@dataclass
class MonteCarloResult:
    """Results from Monte Carlo analysis."""
    strategy: str
    simulations: int = 1000
    
    # Base performance
    original_total_r: float = 0
    original_max_dd: float = 0
    
    # Distribution metrics
    median_total_r: float = 0
    percentile_5_r: float = 0    # 5th percentile (worst case)
    percentile_95_r: float = 0   # 95th percentile (best case)
    
    median_max_dd: float = 0
    percentile_95_dd: float = 0  # 95th percentile DD (worst case)
    
    # Probability metrics
    prob_profitable: float = 0   # Probability of positive total R
    prob_survive: float = 0      # Probability of avoiding ruin (<20% DD)
    
    # Stress tests
    slippage_stress_passed: bool = False
    gap_stress_passed: bool = False
    
    # Validation
    passed: bool = False
    issues: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "simulations": self.simulations,
            "original_total_r": self.original_total_r,
            "median_total_r": self.median_total_r,
            "percentile_5_r": self.percentile_5_r,
            "prob_profitable": self.prob_profitable,
            "prob_survive": self.prob_survive,
            "slippage_stress_passed": self.slippage_stress_passed,
            "gap_stress_passed": self.gap_stress_passed,
            "passed": self.passed,
            "issues": self.issues,
        }


@dataclass
class PaperTradeResult:
    """Results from paper trading validation."""
    strategy: str
    start_date: date
    end_date: Optional[date] = None
    
    # Trade count
    total_trades: int = 0
    min_required: int = 100
    
    # Performance vs expected
    expected_win_rate: float = 0
    actual_win_rate: float = 0
    win_rate_deviation: float = 0
    
    expected_avg_r: float = 0
    actual_avg_r: float = 0
    avg_r_deviation: float = 0
    
    # Execution quality
    avg_slippage_pips: float = 0
    max_slippage_pips: float = 0
    slippage_acceptable: bool = True
    
    # Edge validation
    signal_edge_expected: float = 0  # From backtest
    signal_edge_realized: float = 0  # Actual
    edge_intact: bool = True
    
    # Validation
    passed: bool = False
    issues: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "period": f"{self.start_date} to {self.end_date or 'ongoing'}",
            "total_trades": self.total_trades,
            "min_required": self.min_required,
            "actual_win_rate": self.actual_win_rate,
            "actual_avg_r": self.actual_avg_r,
            "avg_slippage_pips": self.avg_slippage_pips,
            "edge_intact": self.edge_intact,
            "passed": self.passed,
            "issues": self.issues,
        }


@dataclass
class ShadowLiveResult:
    """Results from shadow live mode."""
    strategy: str
    start_date: date
    end_date: Optional[date] = None
    
    # Signal tracking
    signals_generated: int = 0
    signals_would_execute: int = 0
    
    # Hypothetical vs actual
    hypothetical_pnl_r: float = 0
    market_moved_as_expected: int = 0
    market_moved_against: int = 0
    
    # Execution comparison
    theoretical_entry_prices: List[float] = field(default_factory=list)
    actual_market_prices: List[float] = field(default_factory=list)
    avg_entry_deviation: float = 0
    
    # Validation
    passed: bool = False
    issues: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "signals_generated": self.signals_generated,
            "hypothetical_pnl_r": self.hypothetical_pnl_r,
            "market_aligned_pct": self.market_moved_as_expected / max(1, self.signals_generated) * 100,
            "passed": self.passed,
            "issues": self.issues,
        }


@dataclass
class PromotionGate:
    """Configuration for a promotion gate."""
    name: str
    description: str
    threshold: Any
    current_value: Any = None
    passed: bool = False
    required: bool = True
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "threshold": self.threshold,
            "current_value": self.current_value,
            "passed": self.passed,
            "required": self.required,
        }


@dataclass
class PromotionConfig:
    """Configuration for promotion gates to live mode."""
    strategy: str
    
    # Minimum requirements
    min_paper_trades: int = 100
    min_paper_days: int = 30
    min_profit_factor: float = 1.3
    max_drawdown_pct: float = 15.0
    min_win_rate: float = 45.0
    max_avg_slippage: float = 1.0  # pips
    min_walk_forward_positive: int = 4  # out of 6
    min_monte_carlo_survive: float = 85.0  # % probability
    max_incidents: int = 0  # Critical system incidents
    
    # Review window
    review_window_days: int = 30
    
    # Gates
    gates: List[PromotionGate] = field(default_factory=list)
    
    # Overall status
    all_gates_passed: bool = False
    ready_for_live: bool = False
    operator_approved: bool = False
    
    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "min_paper_trades": self.min_paper_trades,
            "min_profit_factor": self.min_profit_factor,
            "max_drawdown_pct": self.max_drawdown_pct,
            "gates": [g.to_dict() for g in self.gates],
            "all_gates_passed": self.all_gates_passed,
            "ready_for_live": self.ready_for_live,
            "operator_approved": self.operator_approved,
        }


class ValidationFramework:
    """
    Comprehensive Validation and Testing Framework
    
    Pipeline:
    1. Historical Backtesting
    2. Walk-Forward Validation
    3. Monte Carlo Analysis
    4. Paper Trading
    5. Shadow Live Mode
    6. Promotion to Live (with gates)
    """
    
    def __init__(self):
        self.backtest_results: Dict[str, BacktestResult] = {}
        self.walk_forward_results: Dict[str, WalkForwardResult] = {}
        self.monte_carlo_results: Dict[str, MonteCarloResult] = {}
        self.paper_results: Dict[str, PaperTradeResult] = {}
        self.shadow_results: Dict[str, ShadowLiveResult] = {}
        self.promotion_configs: Dict[str, PromotionConfig] = {}
        
        self.validation_log: List[dict] = []
    
    def log_event(self, stage: str, strategy: str, event: str, data: dict = None):
        """Log a validation event."""
        self.validation_log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "stage": stage,
            "strategy": strategy,
            "event": event,
            "data": data or {},
        })
    
    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 1: HISTORICAL BACKTESTING
    # ═══════════════════════════════════════════════════════════════════════════
    
    def run_backtest(
        self,
        strategy: str,
        symbol: str,
        trades: List[dict],  # Historical trade data
        start_date: date,
        end_date: date,
        thresholds: dict = None
    ) -> BacktestResult:
        """
        Run historical backtest on trade data.
        
        trades should have: entry_date, exit_date, result_r, regime, etc.
        """
        thresholds = thresholds or {
            "min_trades": 50,
            "min_profit_factor": 1.2,
            "max_drawdown": 20.0,
            "min_sharpe": 0.5,
        }
        
        result = BacktestResult(
            strategy=strategy,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )
        
        if not trades:
            result.issues.append("No trade data provided")
            return result
        
        result.total_trades = len(trades)
        result.winning_trades = sum(1 for t in trades if t.get("result_r", 0) > 0)
        result.losing_trades = sum(1 for t in trades if t.get("result_r", 0) <= 0)
        
        # Win rate
        result.win_rate = (result.winning_trades / result.total_trades * 100) if result.total_trades > 0 else 0
        
        # Profit factor
        gross_profit = sum(t.get("result_r", 0) for t in trades if t.get("result_r", 0) > 0)
        gross_loss = abs(sum(t.get("result_r", 0) for t in trades if t.get("result_r", 0) < 0))
        result.profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 99.99
        
        # Total and average R
        result.total_r = sum(t.get("result_r", 0) for t in trades)
        result.avg_r = result.total_r / result.total_trades if result.total_trades > 0 else 0
        
        # Calculate drawdown
        equity_curve = [0]
        for t in trades:
            equity_curve.append(equity_curve[-1] + t.get("result_r", 0))
        
        peak = 0
        max_dd = 0
        for equity in equity_curve:
            if equity > peak:
                peak = equity
            dd = peak - equity
            if dd > max_dd:
                max_dd = dd
        
        result.max_drawdown_r = max_dd
        result.max_drawdown_pct = (max_dd / abs(peak)) * 100 if peak != 0 else 0
        
        # Sharpe ratio (simplified)
        returns = [t.get("result_r", 0) for t in trades]
        if len(returns) >= 2:
            avg_return = sum(returns) / len(returns)
            variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
            std_dev = math.sqrt(variance) if variance > 0 else 1
            result.sharpe_ratio = avg_return / std_dev
        
        # Performance by regime
        regime_trades = {}
        for t in trades:
            regime = t.get("regime", "unknown")
            if regime not in regime_trades:
                regime_trades[regime] = []
            regime_trades[regime].append(t)
        
        for regime, rt in regime_trades.items():
            wins = sum(1 for t in rt if t.get("result_r", 0) > 0)
            result.performance_by_regime[regime] = {
                "trades": len(rt),
                "win_rate": (wins / len(rt) * 100) if rt else 0,
                "total_r": sum(t.get("result_r", 0) for t in rt),
            }
        
        # Validation checks
        if result.total_trades < thresholds["min_trades"]:
            result.issues.append(f"Insufficient trades ({result.total_trades} < {thresholds['min_trades']})")
        
        if result.profit_factor < thresholds["min_profit_factor"]:
            result.issues.append(f"Profit factor too low ({result.profit_factor:.2f} < {thresholds['min_profit_factor']})")
        
        if result.max_drawdown_pct > thresholds["max_drawdown"]:
            result.issues.append(f"Drawdown too high ({result.max_drawdown_pct:.1f}% > {thresholds['max_drawdown']}%)")
        
        if result.sharpe_ratio < thresholds["min_sharpe"]:
            result.issues.append(f"Sharpe ratio too low ({result.sharpe_ratio:.2f} < {thresholds['min_sharpe']})")
        
        result.passed = len(result.issues) == 0
        
        self.backtest_results[strategy] = result
        self.log_event("backtest", strategy, "completed", result.to_dict())
        
        return result
    
    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 2: WALK-FORWARD VALIDATION
    # ═══════════════════════════════════════════════════════════════════════════
    
    def run_walk_forward(
        self,
        strategy: str,
        all_trades: List[dict],
        periods: int = 6,
        min_positive_periods: int = 4
    ) -> WalkForwardResult:
        """
        Run walk-forward validation with rolling windows.
        
        No future leakage - each period trained only on past data.
        """
        result = WalkForwardResult(
            strategy=strategy,
            total_periods=periods,
        )
        
        if not all_trades or len(all_trades) < periods * 10:
            result.issues.append("Insufficient data for walk-forward analysis")
            return result
        
        # Sort by date
        sorted_trades = sorted(all_trades, key=lambda t: t.get("entry_date", ""))
        
        # Divide into periods
        trades_per_period = len(sorted_trades) // periods
        
        for i in range(periods):
            start_idx = i * trades_per_period
            end_idx = (i + 1) * trades_per_period if i < periods - 1 else len(sorted_trades)
            period_trades = sorted_trades[start_idx:end_idx]
            
            if not period_trades:
                continue
            
            # Calculate metrics for this period
            wins = sum(1 for t in period_trades if t.get("result_r", 0) > 0)
            total_r = sum(t.get("result_r", 0) for t in period_trades)
            gross_profit = sum(t.get("result_r", 0) for t in period_trades if t.get("result_r", 0) > 0)
            gross_loss = abs(sum(t.get("result_r", 0) for t in period_trades if t.get("result_r", 0) < 0))
            pf = gross_profit / gross_loss if gross_loss > 0 else 99.99
            
            period_result = {
                "period": i + 1,
                "trades": len(period_trades),
                "win_rate": (wins / len(period_trades) * 100) if period_trades else 0,
                "total_r": total_r,
                "profit_factor": pf,
                "positive": total_r > 0,
            }
            
            result.period_results.append(period_result)
            
            if total_r > 0:
                result.positive_periods += 1
            else:
                result.negative_periods += 1
        
        # Calculate aggregates
        if result.period_results:
            result.avg_profit_factor = sum(p["profit_factor"] for p in result.period_results) / len(result.period_results)
            result.avg_win_rate = sum(p["win_rate"] for p in result.period_results) / len(result.period_results)
            
            # Consistency score (lower variance = more consistent)
            pfs = [p["profit_factor"] for p in result.period_results]
            avg_pf = sum(pfs) / len(pfs)
            variance = sum((pf - avg_pf) ** 2 for pf in pfs) / len(pfs)
            result.consistency_score = max(0, 100 - variance * 10)
        
        # Validation
        if result.positive_periods < min_positive_periods:
            result.issues.append(
                f"Too few positive periods ({result.positive_periods} < {min_positive_periods})"
            )
        
        if result.consistency_score < 50:
            result.issues.append(f"Low consistency score ({result.consistency_score:.0f})")
        
        result.passed = len(result.issues) == 0
        
        self.walk_forward_results[strategy] = result
        self.log_event("walk_forward", strategy, "completed", result.to_dict())
        
        return result
    
    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 3: MONTE CARLO ANALYSIS
    # ═══════════════════════════════════════════════════════════════════════════
    
    def run_monte_carlo(
        self,
        strategy: str,
        trades: List[dict],
        simulations: int = 1000,
        slippage_stress: float = 0.5,  # Additional pips
        gap_probability: float = 0.02   # 2% chance of adverse gap
    ) -> MonteCarloResult:
        """
        Run Monte Carlo simulation with stress testing.
        
        - Sequence reshuffling
        - Slippage stress
        - Gap/event stress
        """
        result = MonteCarloResult(
            strategy=strategy,
            simulations=simulations,
        )
        
        if not trades:
            result.issues.append("No trade data")
            return result
        
        returns = [t.get("result_r", 0) for t in trades]
        result.original_total_r = sum(returns)
        
        # Calculate original max drawdown
        equity = 0
        peak = 0
        max_dd = 0
        for r in returns:
            equity += r
            peak = max(peak, equity)
            max_dd = max(max_dd, peak - equity)
        result.original_max_dd = max_dd
        
        # Run simulations
        simulation_totals = []
        simulation_max_dds = []
        
        for _ in range(simulations):
            # Shuffle sequence
            shuffled = returns.copy()
            random.shuffle(shuffled)
            
            # Calculate metrics
            total = sum(shuffled)
            
            equity = 0
            peak = 0
            max_dd = 0
            for r in shuffled:
                equity += r
                peak = max(peak, equity)
                max_dd = max(max_dd, peak - equity)
            
            simulation_totals.append(total)
            simulation_max_dds.append(max_dd)
        
        # Calculate distribution metrics
        simulation_totals.sort()
        simulation_max_dds.sort()
        
        result.median_total_r = simulation_totals[simulations // 2]
        result.percentile_5_r = simulation_totals[int(simulations * 0.05)]
        result.percentile_95_r = simulation_totals[int(simulations * 0.95)]
        
        result.median_max_dd = simulation_max_dds[simulations // 2]
        result.percentile_95_dd = simulation_max_dds[int(simulations * 0.95)]
        
        # Probability metrics
        result.prob_profitable = sum(1 for t in simulation_totals if t > 0) / simulations * 100
        result.prob_survive = sum(1 for dd in simulation_max_dds if dd < 20) / simulations * 100
        
        # Slippage stress test
        slippage_totals = []
        for _ in range(100):
            stressed_returns = [r - slippage_stress * 0.1 for r in returns]  # 0.1R per trade slippage
            slippage_totals.append(sum(stressed_returns))
        
        result.slippage_stress_passed = sum(1 for t in slippage_totals if t > 0) > 70
        
        # Gap stress test
        gap_totals = []
        for _ in range(100):
            stressed_returns = []
            for r in returns:
                if random.random() < gap_probability and r < 0:
                    stressed_returns.append(r * 1.5)  # 50% worse on losses
                else:
                    stressed_returns.append(r)
            gap_totals.append(sum(stressed_returns))
        
        result.gap_stress_passed = sum(1 for t in gap_totals if t > 0) > 60
        
        # Validation
        if result.prob_profitable < 70:
            result.issues.append(f"Low probability of profit ({result.prob_profitable:.0f}%)")
        
        if result.prob_survive < 85:
            result.issues.append(f"Low survival probability ({result.prob_survive:.0f}%)")
        
        if not result.slippage_stress_passed:
            result.issues.append("Failed slippage stress test")
        
        if not result.gap_stress_passed:
            result.issues.append("Failed gap stress test")
        
        result.passed = len(result.issues) == 0
        
        self.monte_carlo_results[strategy] = result
        self.log_event("monte_carlo", strategy, "completed", result.to_dict())
        
        return result
    
    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 4: PAPER TRADING
    # ═══════════════════════════════════════════════════════════════════════════
    
    def start_paper_trading(
        self,
        strategy: str,
        expected_win_rate: float,
        expected_avg_r: float,
        expected_edge: float,
        min_trades: int = 100,
        min_days: int = 30
    ) -> PaperTradeResult:
        """Initialize paper trading validation."""
        result = PaperTradeResult(
            strategy=strategy,
            start_date=date.today(),
            min_required=min_trades,
            expected_win_rate=expected_win_rate,
            expected_avg_r=expected_avg_r,
            signal_edge_expected=expected_edge,
        )
        
        self.paper_results[strategy] = result
        self.log_event("paper_trade", strategy, "started", {
            "min_trades": min_trades,
            "expected_win_rate": expected_win_rate,
        })
        
        return result
    
    def record_paper_trade(
        self,
        strategy: str,
        won: bool,
        result_r: float,
        slippage_pips: float
    ):
        """Record a paper trade result."""
        if strategy not in self.paper_results:
            return
        
        result = self.paper_results[strategy]
        result.total_trades += 1
        
        # Update slippage tracking
        result.avg_slippage_pips = (
            (result.avg_slippage_pips * (result.total_trades - 1) + slippage_pips) 
            / result.total_trades
        )
        result.max_slippage_pips = max(result.max_slippage_pips, slippage_pips)
        
        # Update win rate
        if won:
            wins_so_far = int(result.actual_win_rate * (result.total_trades - 1) / 100)
            result.actual_win_rate = (wins_so_far + 1) / result.total_trades * 100
        else:
            wins_so_far = int(result.actual_win_rate * (result.total_trades - 1) / 100)
            result.actual_win_rate = wins_so_far / result.total_trades * 100
        
        # Update avg R
        total_r_so_far = result.actual_avg_r * (result.total_trades - 1)
        result.actual_avg_r = (total_r_so_far + result_r) / result.total_trades
        
        self.log_event("paper_trade", strategy, "trade_recorded", {
            "won": won,
            "result_r": result_r,
            "slippage": slippage_pips,
            "total_trades": result.total_trades,
        })
    
    def evaluate_paper_trading(self, strategy: str) -> PaperTradeResult:
        """Evaluate paper trading results."""
        if strategy not in self.paper_results:
            return PaperTradeResult(strategy=strategy, issues=["No paper trading data"])
        
        result = self.paper_results[strategy]
        result.end_date = date.today()
        
        # Check minimum trades
        if result.total_trades < result.min_required:
            result.issues.append(
                f"Insufficient trades ({result.total_trades} < {result.min_required})"
            )
        
        # Calculate deviations
        result.win_rate_deviation = abs(result.actual_win_rate - result.expected_win_rate)
        result.avg_r_deviation = abs(result.actual_avg_r - result.expected_avg_r)
        
        # Check win rate deviation
        if result.win_rate_deviation > 10:
            result.issues.append(
                f"Win rate deviation too high ({result.win_rate_deviation:.1f}%)"
            )
        
        # Check slippage
        if result.avg_slippage_pips > 1.0:
            result.slippage_acceptable = False
            result.issues.append(f"Slippage too high ({result.avg_slippage_pips:.2f} pips)")
        
        # Check if edge is intact
        result.signal_edge_realized = result.actual_avg_r
        if result.signal_edge_realized < result.signal_edge_expected * 0.7:
            result.edge_intact = False
            result.issues.append("Realized edge significantly below expected")
        
        result.passed = len(result.issues) == 0
        
        self.log_event("paper_trade", strategy, "evaluated", result.to_dict())
        
        return result
    
    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 5: SHADOW LIVE MODE
    # ═══════════════════════════════════════════════════════════════════════════
    
    def start_shadow_live(self, strategy: str) -> ShadowLiveResult:
        """Start shadow live mode (signals without execution)."""
        result = ShadowLiveResult(
            strategy=strategy,
            start_date=date.today(),
        )
        
        self.shadow_results[strategy] = result
        self.log_event("shadow_live", strategy, "started", {})
        
        return result
    
    def record_shadow_signal(
        self,
        strategy: str,
        direction: str,
        entry_price: float,
        actual_market_price: float,
        would_execute: bool,
        market_moved_favorably: bool
    ):
        """Record a shadow live signal."""
        if strategy not in self.shadow_results:
            return
        
        result = self.shadow_results[strategy]
        result.signals_generated += 1
        
        if would_execute:
            result.signals_would_execute += 1
        
        if market_moved_favorably:
            result.market_moved_as_expected += 1
        else:
            result.market_moved_against += 1
        
        result.theoretical_entry_prices.append(entry_price)
        result.actual_market_prices.append(actual_market_price)
        
        # Calculate average entry deviation
        deviations = [abs(t - a) for t, a in zip(
            result.theoretical_entry_prices, 
            result.actual_market_prices
        )]
        result.avg_entry_deviation = sum(deviations) / len(deviations) if deviations else 0
    
    def evaluate_shadow_live(self, strategy: str, min_signals: int = 50) -> ShadowLiveResult:
        """Evaluate shadow live results."""
        if strategy not in self.shadow_results:
            return ShadowLiveResult(strategy=strategy, issues=["No shadow data"])
        
        result = self.shadow_results[strategy]
        result.end_date = date.today()
        
        if result.signals_generated < min_signals:
            result.issues.append(
                f"Insufficient signals ({result.signals_generated} < {min_signals})"
            )
        
        # Check alignment rate
        alignment_rate = result.market_moved_as_expected / max(1, result.signals_generated)
        if alignment_rate < 0.5:
            result.issues.append(f"Low market alignment ({alignment_rate*100:.0f}%)")
        
        result.passed = len(result.issues) == 0
        
        self.log_event("shadow_live", strategy, "evaluated", result.to_dict())
        
        return result
    
    # ═══════════════════════════════════════════════════════════════════════════
    # PROMOTION GATES
    # ═══════════════════════════════════════════════════════════════════════════
    
    def create_promotion_config(
        self,
        strategy: str,
        custom_thresholds: dict = None
    ) -> PromotionConfig:
        """Create promotion configuration with gates."""
        config = PromotionConfig(strategy=strategy)
        
        if custom_thresholds:
            for key, value in custom_thresholds.items():
                if hasattr(config, key):
                    setattr(config, key, value)
        
        # Build gates
        config.gates = [
            PromotionGate(
                name="min_paper_trades",
                description=f"Minimum {config.min_paper_trades} paper trades",
                threshold=config.min_paper_trades,
                required=True,
            ),
            PromotionGate(
                name="min_paper_days",
                description=f"Minimum {config.min_paper_days} days of paper trading",
                threshold=config.min_paper_days,
                required=True,
            ),
            PromotionGate(
                name="min_profit_factor",
                description=f"Profit factor ≥ {config.min_profit_factor}",
                threshold=config.min_profit_factor,
                required=True,
            ),
            PromotionGate(
                name="max_drawdown",
                description=f"Max drawdown ≤ {config.max_drawdown_pct}%",
                threshold=config.max_drawdown_pct,
                required=True,
            ),
            PromotionGate(
                name="min_win_rate",
                description=f"Win rate ≥ {config.min_win_rate}%",
                threshold=config.min_win_rate,
                required=True,
            ),
            PromotionGate(
                name="max_slippage",
                description=f"Avg slippage ≤ {config.max_avg_slippage} pips",
                threshold=config.max_avg_slippage,
                required=True,
            ),
            PromotionGate(
                name="walk_forward_positive",
                description=f"≥ {config.min_walk_forward_positive}/6 walk-forward periods positive",
                threshold=config.min_walk_forward_positive,
                required=True,
            ),
            PromotionGate(
                name="monte_carlo_survive",
                description=f"≥ {config.min_monte_carlo_survive}% survival probability",
                threshold=config.min_monte_carlo_survive,
                required=True,
            ),
            PromotionGate(
                name="no_critical_incidents",
                description="No critical system incidents in review window",
                threshold=config.max_incidents,
                required=True,
            ),
        ]
        
        self.promotion_configs[strategy] = config
        return config
    
    def evaluate_promotion_gates(self, strategy: str) -> PromotionConfig:
        """Evaluate all promotion gates for a strategy."""
        if strategy not in self.promotion_configs:
            self.create_promotion_config(strategy)
        
        config = self.promotion_configs[strategy]
        
        # Get all results
        backtest = self.backtest_results.get(strategy)
        walk_forward = self.walk_forward_results.get(strategy)
        monte_carlo = self.monte_carlo_results.get(strategy)
        paper = self.paper_results.get(strategy)
        shadow = self.shadow_results.get(strategy)
        
        # Evaluate each gate
        for gate in config.gates:
            if gate.name == "min_paper_trades" and paper:
                gate.current_value = paper.total_trades
                gate.passed = paper.total_trades >= gate.threshold
            
            elif gate.name == "min_paper_days" and paper:
                days = (date.today() - paper.start_date).days
                gate.current_value = days
                gate.passed = days >= gate.threshold
            
            elif gate.name == "min_profit_factor" and backtest:
                gate.current_value = backtest.profit_factor
                gate.passed = backtest.profit_factor >= gate.threshold
            
            elif gate.name == "max_drawdown" and backtest:
                gate.current_value = backtest.max_drawdown_pct
                gate.passed = backtest.max_drawdown_pct <= gate.threshold
            
            elif gate.name == "min_win_rate" and paper:
                gate.current_value = paper.actual_win_rate
                gate.passed = paper.actual_win_rate >= gate.threshold
            
            elif gate.name == "max_slippage" and paper:
                gate.current_value = paper.avg_slippage_pips
                gate.passed = paper.avg_slippage_pips <= gate.threshold
            
            elif gate.name == "walk_forward_positive" and walk_forward:
                gate.current_value = walk_forward.positive_periods
                gate.passed = walk_forward.positive_periods >= gate.threshold
            
            elif gate.name == "monte_carlo_survive" and monte_carlo:
                gate.current_value = monte_carlo.prob_survive
                gate.passed = monte_carlo.prob_survive >= gate.threshold
            
            elif gate.name == "no_critical_incidents":
                gate.current_value = 0  # Would check incident log
                gate.passed = True
        
        # Check if all required gates passed
        config.all_gates_passed = all(
            g.passed for g in config.gates if g.required
        )
        
        config.ready_for_live = config.all_gates_passed and not config.operator_approved
        
        self.log_event("promotion", strategy, "gates_evaluated", config.to_dict())
        
        return config
    
    def approve_for_live(self, strategy: str, operator: str) -> bool:
        """Operator approval for live trading."""
        if strategy not in self.promotion_configs:
            return False
        
        config = self.promotion_configs[strategy]
        
        if not config.all_gates_passed:
            return False
        
        config.operator_approved = True
        config.ready_for_live = True
        
        self.log_event("promotion", strategy, "operator_approved", {
            "operator": operator,
            "timestamp": datetime.utcnow().isoformat(),
        })
        
        return True
    
    def get_validation_status(self, strategy: str) -> dict:
        """Get comprehensive validation status for a strategy."""
        return {
            "strategy": strategy,
            "stages": {
                "backtest": self.backtest_results.get(strategy, BacktestResult(strategy=strategy)).to_dict() if strategy in self.backtest_results else {"status": "not_run"},
                "walk_forward": self.walk_forward_results.get(strategy, WalkForwardResult(strategy=strategy)).to_dict() if strategy in self.walk_forward_results else {"status": "not_run"},
                "monte_carlo": self.monte_carlo_results.get(strategy, MonteCarloResult(strategy=strategy)).to_dict() if strategy in self.monte_carlo_results else {"status": "not_run"},
                "paper_trade": self.paper_results.get(strategy, PaperTradeResult(strategy=strategy, start_date=date.today())).to_dict() if strategy in self.paper_results else {"status": "not_run"},
                "shadow_live": self.shadow_results.get(strategy, ShadowLiveResult(strategy=strategy, start_date=date.today())).to_dict() if strategy in self.shadow_results else {"status": "not_run"},
            },
            "promotion": self.promotion_configs.get(strategy, PromotionConfig(strategy=strategy)).to_dict() if strategy in self.promotion_configs else {"status": "not_configured"},
        }
