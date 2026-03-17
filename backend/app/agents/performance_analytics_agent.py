"""
Performance Analytics Agent

Calculates comprehensive trading performance metrics:
- Win rate, profit factor, expectancy
- Drawdown analysis
- R-multiple distribution
- Time-based performance patterns
- Strategy and symbol breakdowns
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import statistics
import math

from app.agents.base_agent import BaseAgent, AgentOutput


class TimeFrame(Enum):
    """Analysis timeframes."""
    TODAY = "today"
    THIS_WEEK = "this_week"
    THIS_MONTH = "this_month"
    ALL_TIME = "all_time"
    LAST_30_DAYS = "last_30_days"
    LAST_90_DAYS = "last_90_days"


@dataclass
class TradeResult:
    """Single trade result for analysis."""
    trade_id: str
    symbol: str
    direction: str
    strategy_name: str
    entry_time: datetime
    exit_time: Optional[datetime]
    entry_price: float
    exit_price: Optional[float]
    stop_loss: float
    take_profit: Optional[float]
    volume: float
    pnl: float
    pnl_pct: float
    r_multiple: float
    mae_pips: float
    mfe_pips: float
    duration_minutes: int
    session: str
    regime: str
    confluence_score: float
    exit_type: str  # sl_hit, tp_hit, manual, trailing_stop


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics."""
    # Core metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0
    win_rate: float = 0.0
    
    # P&L metrics
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    profit_factor: float = 0.0
    
    # Average metrics
    avg_win: float = 0.0
    avg_loss: float = 0.0
    avg_trade: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    
    # R-multiple metrics
    total_r: float = 0.0
    avg_r: float = 0.0
    expectancy: float = 0.0  # (win_rate * avg_win_r) - (loss_rate * avg_loss_r)
    avg_win_r: float = 0.0
    avg_loss_r: float = 0.0
    
    # Extremes
    largest_win: float = 0.0
    largest_loss: float = 0.0
    largest_win_r: float = 0.0
    largest_loss_r: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    
    # Risk metrics
    max_drawdown_pct: float = 0.0
    max_drawdown_duration_days: int = 0
    recovery_factor: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    
    # Time metrics
    avg_duration_minutes: float = 0.0
    avg_win_duration: float = 0.0
    avg_loss_duration: float = 0.0
    
    # Efficiency metrics
    avg_mae_pips: float = 0.0
    avg_mfe_pips: float = 0.0
    edge_ratio: float = 0.0  # avg_mfe / avg_mae
    
    # Exit analysis
    sl_hit_count: int = 0
    tp_hit_count: int = 0
    manual_exit_count: int = 0
    trailing_stop_count: int = 0


@dataclass
class BreakdownMetrics:
    """Performance breakdown by category."""
    category: str
    value: str
    trades: int
    win_rate: float
    pnl: float
    profit_factor: float
    avg_r: float
    expectancy: float


class PerformanceAnalyticsAgent(BaseAgent):
    """Calculates and tracks trading performance."""
    
    def __init__(self, db_session=None, redis_client=None):
        super().__init__(
            name="PerformanceAnalyticsAgent",
            description="Calculates comprehensive trading performance metrics",
            dependencies=["JournalReviewAgent"]
        )
        self.db = db_session
        self.redis = redis_client
        
    async def analyze(self, context: Dict[str, Any]) -> AgentOutput:
        """Calculate performance metrics."""
        try:
            timeframe = context.get("timeframe", TimeFrame.ALL_TIME)
            trades = await self._load_trades(timeframe)
            
            if not trades:
                return AgentOutput(
                    agent_name=self.name,
                    timestamp=datetime.utcnow(),
                    data={"metrics": PerformanceMetrics().__dict__},
                    confidence=1.0,
                    metadata={"trade_count": 0}
                )
            
            # Calculate all metrics
            metrics = self._calculate_metrics(trades)
            
            # Calculate breakdowns
            by_symbol = self._breakdown_by_category(trades, "symbol")
            by_strategy = self._breakdown_by_category(trades, "strategy_name")
            by_session = self._breakdown_by_category(trades, "session")
            by_regime = self._breakdown_by_category(trades, "regime")
            by_direction = self._breakdown_by_category(trades, "direction")
            by_day_of_week = self._breakdown_by_day_of_week(trades)
            
            # Calculate equity curve
            equity_curve = self._calculate_equity_curve(trades)
            
            # Calculate R distribution
            r_distribution = self._calculate_r_distribution(trades)
            
            # Performance trends
            weekly_performance = self._calculate_weekly_performance(trades)
            monthly_performance = self._calculate_monthly_performance(trades)
            
            return AgentOutput(
                agent_name=self.name,
                timestamp=datetime.utcnow(),
                data={
                    "metrics": metrics.__dict__,
                    "by_symbol": [b.__dict__ for b in by_symbol],
                    "by_strategy": [b.__dict__ for b in by_strategy],
                    "by_session": [b.__dict__ for b in by_session],
                    "by_regime": [b.__dict__ for b in by_regime],
                    "by_direction": [b.__dict__ for b in by_direction],
                    "by_day_of_week": [b.__dict__ for b in by_day_of_week],
                    "equity_curve": equity_curve,
                    "r_distribution": r_distribution,
                    "weekly_performance": weekly_performance,
                    "monthly_performance": monthly_performance,
                },
                confidence=1.0,
                metadata={
                    "trade_count": len(trades),
                    "timeframe": timeframe.value if isinstance(timeframe, TimeFrame) else timeframe,
                    "analysis_time": datetime.utcnow().isoformat()
                }
            )
            
        except Exception as e:
            self.logger.error(f"Performance analysis failed: {e}")
            return AgentOutput(
                agent_name=self.name,
                timestamp=datetime.utcnow(),
                data={},
                confidence=0.0,
                errors=[str(e)]
            )
    
    async def _load_trades(self, timeframe: TimeFrame) -> List[TradeResult]:
        """Load trades from database for the given timeframe."""
        # TODO: Implement actual database query
        # For now, return empty list (would query JournalEntry table)
        return []
    
    def _calculate_metrics(self, trades: List[TradeResult]) -> PerformanceMetrics:
        """Calculate comprehensive metrics from trades."""
        metrics = PerformanceMetrics()
        
        if not trades:
            return metrics
        
        # Basic counts
        metrics.total_trades = len(trades)
        metrics.winning_trades = sum(1 for t in trades if t.pnl > 0)
        metrics.losing_trades = sum(1 for t in trades if t.pnl < 0)
        metrics.breakeven_trades = sum(1 for t in trades if t.pnl == 0)
        
        # Win rate
        if metrics.total_trades > 0:
            metrics.win_rate = metrics.winning_trades / metrics.total_trades
        
        # P&L metrics
        metrics.total_pnl = sum(t.pnl for t in trades)
        metrics.total_pnl_pct = sum(t.pnl_pct for t in trades)
        metrics.gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
        metrics.gross_loss = abs(sum(t.pnl for t in trades if t.pnl < 0))
        
        # Profit factor
        if metrics.gross_loss > 0:
            metrics.profit_factor = metrics.gross_profit / metrics.gross_loss
        elif metrics.gross_profit > 0:
            metrics.profit_factor = float('inf')
        
        # Average metrics
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl < 0]
        
        if wins:
            metrics.avg_win = sum(t.pnl for t in wins) / len(wins)
            metrics.avg_win_pct = sum(t.pnl_pct for t in wins) / len(wins)
            metrics.avg_win_r = sum(t.r_multiple for t in wins) / len(wins)
            metrics.avg_win_duration = sum(t.duration_minutes for t in wins) / len(wins)
        
        if losses:
            metrics.avg_loss = sum(t.pnl for t in losses) / len(losses)
            metrics.avg_loss_pct = sum(t.pnl_pct for t in losses) / len(losses)
            metrics.avg_loss_r = sum(t.r_multiple for t in losses) / len(losses)
            metrics.avg_loss_duration = sum(t.duration_minutes for t in losses) / len(losses)
        
        if trades:
            metrics.avg_trade = metrics.total_pnl / len(trades)
            metrics.avg_duration_minutes = sum(t.duration_minutes for t in trades) / len(trades)
        
        # R-multiple metrics
        metrics.total_r = sum(t.r_multiple for t in trades)
        if trades:
            metrics.avg_r = metrics.total_r / len(trades)
        
        # Expectancy: (Win% * Avg Win R) - (Loss% * Avg Loss R)
        loss_rate = 1 - metrics.win_rate
        metrics.expectancy = (metrics.win_rate * metrics.avg_win_r) + (loss_rate * metrics.avg_loss_r)
        
        # Extremes
        if trades:
            metrics.largest_win = max((t.pnl for t in trades), default=0)
            metrics.largest_loss = min((t.pnl for t in trades), default=0)
            metrics.largest_win_r = max((t.r_multiple for t in trades), default=0)
            metrics.largest_loss_r = min((t.r_multiple for t in trades), default=0)
        
        # Consecutive wins/losses
        metrics.max_consecutive_wins = self._max_consecutive(trades, lambda t: t.pnl > 0)
        metrics.max_consecutive_losses = self._max_consecutive(trades, lambda t: t.pnl < 0)
        
        # Drawdown
        equity_curve = self._calculate_equity_curve(trades)
        metrics.max_drawdown_pct = self._calculate_max_drawdown(equity_curve)
        
        # Sharpe ratio (simplified - daily returns)
        if len(trades) > 1:
            returns = [t.pnl_pct for t in trades]
            if statistics.stdev(returns) > 0:
                metrics.sharpe_ratio = (statistics.mean(returns) / statistics.stdev(returns)) * math.sqrt(252)
            
            # Sortino (only downside deviation)
            negative_returns = [r for r in returns if r < 0]
            if negative_returns and statistics.stdev(negative_returns) > 0:
                metrics.sortino_ratio = (statistics.mean(returns) / statistics.stdev(negative_returns)) * math.sqrt(252)
        
        # Calmar ratio
        if metrics.max_drawdown_pct > 0:
            # Annualized return / max drawdown
            days_trading = (trades[-1].entry_time - trades[0].entry_time).days or 1
            annual_return = (metrics.total_pnl_pct / days_trading) * 365
            metrics.calmar_ratio = annual_return / metrics.max_drawdown_pct
        
        # Recovery factor
        if metrics.max_drawdown_pct > 0:
            metrics.recovery_factor = metrics.total_pnl_pct / metrics.max_drawdown_pct
        
        # MAE/MFE
        if trades:
            metrics.avg_mae_pips = sum(t.mae_pips for t in trades) / len(trades)
            metrics.avg_mfe_pips = sum(t.mfe_pips for t in trades) / len(trades)
            if metrics.avg_mae_pips > 0:
                metrics.edge_ratio = metrics.avg_mfe_pips / metrics.avg_mae_pips
        
        # Exit analysis
        metrics.sl_hit_count = sum(1 for t in trades if t.exit_type == "sl_hit")
        metrics.tp_hit_count = sum(1 for t in trades if t.exit_type == "tp_hit")
        metrics.manual_exit_count = sum(1 for t in trades if t.exit_type == "manual")
        metrics.trailing_stop_count = sum(1 for t in trades if t.exit_type == "trailing_stop")
        
        return metrics
    
    def _max_consecutive(self, trades: List[TradeResult], condition) -> int:
        """Calculate maximum consecutive trades matching condition."""
        max_streak = 0
        current_streak = 0
        
        for trade in trades:
            if condition(trade):
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 0
        
        return max_streak
    
    def _calculate_equity_curve(self, trades: List[TradeResult]) -> List[Dict]:
        """Calculate equity curve from trades."""
        curve = []
        cumulative_pnl = 0.0
        
        for trade in sorted(trades, key=lambda t: t.exit_time or t.entry_time):
            cumulative_pnl += trade.pnl
            curve.append({
                "timestamp": (trade.exit_time or trade.entry_time).isoformat(),
                "pnl": trade.pnl,
                "cumulative_pnl": cumulative_pnl,
                "trade_id": trade.trade_id,
            })
        
        return curve
    
    def _calculate_max_drawdown(self, equity_curve: List[Dict]) -> float:
        """Calculate maximum drawdown from equity curve."""
        if not equity_curve:
            return 0.0
        
        peak = 0.0
        max_dd = 0.0
        
        for point in equity_curve:
            cumulative = point["cumulative_pnl"]
            if cumulative > peak:
                peak = cumulative
            
            if peak > 0:
                dd = (peak - cumulative) / peak * 100
                max_dd = max(max_dd, dd)
        
        return max_dd
    
    def _breakdown_by_category(self, trades: List[TradeResult], category: str) -> List[BreakdownMetrics]:
        """Calculate performance breakdown by a category."""
        from collections import defaultdict
        
        groups = defaultdict(list)
        for trade in trades:
            key = getattr(trade, category, "unknown")
            groups[key].append(trade)
        
        breakdowns = []
        for value, group_trades in groups.items():
            if not group_trades:
                continue
            
            wins = [t for t in group_trades if t.pnl > 0]
            losses = [t for t in group_trades if t.pnl < 0]
            
            gross_profit = sum(t.pnl for t in wins) if wins else 0
            gross_loss = abs(sum(t.pnl for t in losses)) if losses else 0
            pf = gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0
            
            win_rate = len(wins) / len(group_trades) if group_trades else 0
            avg_r = sum(t.r_multiple for t in group_trades) / len(group_trades) if group_trades else 0
            
            avg_win_r = sum(t.r_multiple for t in wins) / len(wins) if wins else 0
            avg_loss_r = sum(t.r_multiple for t in losses) / len(losses) if losses else 0
            expectancy = (win_rate * avg_win_r) + ((1 - win_rate) * avg_loss_r)
            
            breakdowns.append(BreakdownMetrics(
                category=category,
                value=str(value),
                trades=len(group_trades),
                win_rate=win_rate,
                pnl=sum(t.pnl for t in group_trades),
                profit_factor=pf,
                avg_r=avg_r,
                expectancy=expectancy,
            ))
        
        return sorted(breakdowns, key=lambda b: b.pnl, reverse=True)
    
    def _breakdown_by_day_of_week(self, trades: List[TradeResult]) -> List[BreakdownMetrics]:
        """Performance breakdown by day of week."""
        from collections import defaultdict
        
        groups = defaultdict(list)
        for trade in trades:
            day = trade.entry_time.strftime("%A")
            groups[day].append(trade)
        
        return self._calculate_group_metrics(groups, "day_of_week")
    
    def _calculate_group_metrics(self, groups: Dict, category: str) -> List[BreakdownMetrics]:
        """Calculate metrics for grouped trades."""
        breakdowns = []
        
        for value, group_trades in groups.items():
            if not group_trades:
                continue
            
            wins = [t for t in group_trades if t.pnl > 0]
            losses = [t for t in group_trades if t.pnl < 0]
            
            gross_profit = sum(t.pnl for t in wins) if wins else 0
            gross_loss = abs(sum(t.pnl for t in losses)) if losses else 0
            pf = gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0
            
            win_rate = len(wins) / len(group_trades)
            avg_r = sum(t.r_multiple for t in group_trades) / len(group_trades)
            
            avg_win_r = sum(t.r_multiple for t in wins) / len(wins) if wins else 0
            avg_loss_r = sum(t.r_multiple for t in losses) / len(losses) if losses else 0
            expectancy = (win_rate * avg_win_r) + ((1 - win_rate) * avg_loss_r)
            
            breakdowns.append(BreakdownMetrics(
                category=category,
                value=str(value),
                trades=len(group_trades),
                win_rate=win_rate,
                pnl=sum(t.pnl for t in group_trades),
                profit_factor=pf,
                avg_r=avg_r,
                expectancy=expectancy,
            ))
        
        return breakdowns
    
    def _calculate_r_distribution(self, trades: List[TradeResult]) -> Dict:
        """Calculate R-multiple distribution."""
        if not trades:
            return {}
        
        r_values = [t.r_multiple for t in trades]
        
        # Bucket R values
        buckets = {
            "< -2R": 0,
            "-2R to -1R": 0,
            "-1R to 0": 0,
            "0 to 1R": 0,
            "1R to 2R": 0,
            "2R to 3R": 0,
            "> 3R": 0,
        }
        
        for r in r_values:
            if r < -2:
                buckets["< -2R"] += 1
            elif r < -1:
                buckets["-2R to -1R"] += 1
            elif r < 0:
                buckets["-1R to 0"] += 1
            elif r < 1:
                buckets["0 to 1R"] += 1
            elif r < 2:
                buckets["1R to 2R"] += 1
            elif r < 3:
                buckets["2R to 3R"] += 1
            else:
                buckets["> 3R"] += 1
        
        return {
            "distribution": buckets,
            "mean": statistics.mean(r_values) if r_values else 0,
            "median": statistics.median(r_values) if r_values else 0,
            "std_dev": statistics.stdev(r_values) if len(r_values) > 1 else 0,
            "min": min(r_values) if r_values else 0,
            "max": max(r_values) if r_values else 0,
        }
    
    def _calculate_weekly_performance(self, trades: List[TradeResult]) -> List[Dict]:
        """Calculate weekly performance summary."""
        from collections import defaultdict
        
        weeks = defaultdict(list)
        for trade in trades:
            # ISO week number
            week_key = trade.entry_time.strftime("%Y-W%W")
            weeks[week_key].append(trade)
        
        result = []
        for week, week_trades in sorted(weeks.items()):
            pnl = sum(t.pnl for t in week_trades)
            wins = sum(1 for t in week_trades if t.pnl > 0)
            result.append({
                "week": week,
                "trades": len(week_trades),
                "pnl": pnl,
                "win_rate": wins / len(week_trades) if week_trades else 0,
                "total_r": sum(t.r_multiple for t in week_trades),
            })
        
        return result
    
    def _calculate_monthly_performance(self, trades: List[TradeResult]) -> List[Dict]:
        """Calculate monthly performance summary."""
        from collections import defaultdict
        
        months = defaultdict(list)
        for trade in trades:
            month_key = trade.entry_time.strftime("%Y-%m")
            months[month_key].append(trade)
        
        result = []
        for month, month_trades in sorted(months.items()):
            pnl = sum(t.pnl for t in month_trades)
            wins = sum(1 for t in month_trades if t.pnl > 0)
            result.append({
                "month": month,
                "trades": len(month_trades),
                "pnl": pnl,
                "win_rate": wins / len(month_trades) if month_trades else 0,
                "total_r": sum(t.r_multiple for t in month_trades),
            })
        
        return result
    
    async def get_promotion_readiness(self) -> Dict[str, Any]:
        """Check if system meets promotion gate requirements."""
        # Load all paper trades
        trades = await self._load_trades(TimeFrame.ALL_TIME)
        
        if not trades:
            return {
                "ready": False,
                "gates_passed": 0,
                "gates_total": 6,
                "details": {
                    "min_trades": {"required": 100, "actual": 0, "passed": False},
                    "min_days": {"required": 30, "actual": 0, "passed": False},
                    "profit_factor": {"required": 1.3, "actual": 0, "passed": False},
                    "max_drawdown": {"required": 5.0, "actual": 0, "passed": False},
                    "win_rate": {"required": 0.40, "actual": 0, "passed": False},
                    "avg_rr": {"required": 1.5, "actual": 0, "passed": False},
                }
            }
        
        metrics = self._calculate_metrics(trades)
        
        # Calculate days trading
        first_trade = min(t.entry_time for t in trades)
        days_trading = (datetime.utcnow() - first_trade).days
        
        gates = {
            "min_trades": {
                "required": 100,
                "actual": metrics.total_trades,
                "passed": metrics.total_trades >= 100
            },
            "min_days": {
                "required": 30,
                "actual": days_trading,
                "passed": days_trading >= 30
            },
            "profit_factor": {
                "required": 1.3,
                "actual": round(metrics.profit_factor, 2),
                "passed": metrics.profit_factor >= 1.3
            },
            "max_drawdown": {
                "required": 5.0,
                "actual": round(metrics.max_drawdown_pct, 2),
                "passed": metrics.max_drawdown_pct <= 5.0
            },
            "win_rate": {
                "required": 0.40,
                "actual": round(metrics.win_rate, 3),
                "passed": metrics.win_rate >= 0.40
            },
            "avg_rr": {
                "required": 1.5,
                "actual": round(metrics.avg_win_r / abs(metrics.avg_loss_r) if metrics.avg_loss_r else 0, 2),
                "passed": (metrics.avg_win_r / abs(metrics.avg_loss_r) if metrics.avg_loss_r else 0) >= 1.5
            },
        }
        
        gates_passed = sum(1 for g in gates.values() if g["passed"])
        
        return {
            "ready": gates_passed == len(gates),
            "gates_passed": gates_passed,
            "gates_total": len(gates),
            "details": gates,
            "recommendation": self._promotion_recommendation(gates_passed, len(gates), metrics)
        }
    
    def _promotion_recommendation(self, passed: int, total: int, metrics: PerformanceMetrics) -> str:
        """Generate promotion recommendation."""
        if passed == total:
            return "All gates passed. System is ready for shadow trading phase."
        elif passed >= total - 1:
            return f"Almost ready. {total - passed} gate(s) remaining. Continue paper trading."
        elif passed >= total // 2:
            return "Making progress. Focus on improving consistency before promotion."
        else:
            return "Not ready for promotion. Significant improvements needed in paper trading."
