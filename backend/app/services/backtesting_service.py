"""
Backtesting Service

Simulates trading strategies on historical data with:
- Realistic spread and slippage simulation
- Walk-forward optimization
- Monte Carlo analysis
- Multi-timeframe support
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import random
import statistics
import math
from collections import defaultdict

import pandas as pd
import numpy as np


class BacktestMode(Enum):
    """Backtesting modes."""
    SIMPLE = "simple"  # Basic backtest
    WALK_FORWARD = "walk_forward"  # Walk-forward analysis
    MONTE_CARLO = "monte_carlo"  # Monte Carlo simulation


@dataclass
class BacktestConfig:
    """Backtesting configuration."""
    # Data settings
    symbol: str = "EURUSD"
    start_date: datetime = None
    end_date: datetime = None
    timeframe: str = "M30"
    
    # Account settings
    initial_balance: float = 10000.0
    leverage: int = 100
    
    # Execution settings
    spread_pips: float = 1.5
    slippage_pips: float = 0.5
    commission_per_lot: float = 0.0
    
    # Risk settings
    risk_per_trade_pct: float = 0.35
    max_positions: int = 1
    
    # Walk-forward settings
    in_sample_pct: float = 0.7
    out_of_sample_pct: float = 0.3
    walk_forward_windows: int = 5
    
    # Monte Carlo settings
    monte_carlo_runs: int = 1000
    shuffle_trades: bool = True


@dataclass
class BacktestTrade:
    """Single backtest trade."""
    trade_id: int
    symbol: str
    direction: str  # 'long' or 'short'
    entry_time: datetime
    entry_price: float
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    stop_loss: float = 0.0
    take_profit: Optional[float] = None
    volume: float = 0.01
    pnl: float = 0.0
    pnl_pct: float = 0.0
    r_multiple: float = 0.0
    mae_pips: float = 0.0
    mfe_pips: float = 0.0
    exit_reason: str = ""
    strategy_name: str = ""
    
    
@dataclass
class BacktestResult:
    """Complete backtest result."""
    # Config
    config: BacktestConfig = None
    
    # Trades
    trades: List[BacktestTrade] = field(default_factory=list)
    
    # Performance metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    
    net_profit: float = 0.0
    net_profit_pct: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    profit_factor: float = 0.0
    
    avg_trade: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    
    total_r: float = 0.0
    avg_r: float = 0.0
    expectancy: float = 0.0
    
    # Equity curve
    equity_curve: List[Dict] = field(default_factory=list)
    
    # Walk-forward results (if applicable)
    walk_forward_results: List[Dict] = field(default_factory=list)
    
    # Monte Carlo results (if applicable)
    monte_carlo_results: Dict = field(default_factory=dict)


class BacktestingService:
    """Service for running backtests."""
    
    def __init__(self, data_provider=None):
        self.data_provider = data_provider
        self.pip_values = {
            "EURUSD": 10.0, "GBPUSD": 10.0, "AUDUSD": 10.0,
            "USDJPY": 9.0, "GBPJPY": 9.0,
            "USDCHF": 10.0, "USDCAD": 10.0,
            "EURAUD": 10.0, "AUDNZD": 10.0,
        }
        self.pip_sizes = {
            "EURUSD": 0.0001, "GBPUSD": 0.0001, "AUDUSD": 0.0001,
            "USDJPY": 0.01, "GBPJPY": 0.01,
            "USDCHF": 0.0001, "USDCAD": 0.0001,
            "EURAUD": 0.0001, "AUDNZD": 0.0001,
        }
    
    async def run_backtest(
        self,
        config: BacktestConfig,
        strategy: Callable,
        mode: BacktestMode = BacktestMode.SIMPLE
    ) -> BacktestResult:
        """Run a backtest with the given strategy."""
        
        if mode == BacktestMode.SIMPLE:
            return await self._run_simple_backtest(config, strategy)
        elif mode == BacktestMode.WALK_FORWARD:
            return await self._run_walk_forward(config, strategy)
        elif mode == BacktestMode.MONTE_CARLO:
            result = await self._run_simple_backtest(config, strategy)
            result.monte_carlo_results = self._run_monte_carlo(result, config)
            return result
        
        raise ValueError(f"Unknown backtest mode: {mode}")
    
    async def _run_simple_backtest(
        self,
        config: BacktestConfig,
        strategy: Callable
    ) -> BacktestResult:
        """Run a simple backtest."""
        
        # Load historical data
        data = await self._load_data(config)
        if data.empty:
            return BacktestResult(config=config)
        
        # Initialize state
        balance = config.initial_balance
        equity_curve = []
        trades = []
        open_positions = []
        trade_counter = 0
        
        pip_size = self.pip_sizes.get(config.symbol, 0.0001)
        pip_value = self.pip_values.get(config.symbol, 10.0)
        
        # Iterate through data
        for i in range(len(data)):
            bar = data.iloc[i]
            timestamp = bar.name if hasattr(bar, 'name') else data.index[i]
            
            # Check stop losses and take profits
            for pos in open_positions[:]:
                should_close, exit_price, exit_reason = self._check_exit_conditions(
                    pos, bar, pip_size, config
                )
                
                if should_close:
                    pos = self._close_position(pos, exit_price, timestamp, exit_reason, pip_size, pip_value)
                    balance += pos.pnl
                    trades.append(pos)
                    open_positions.remove(pos)
            
            # Track MAE/MFE for open positions
            for pos in open_positions:
                self._update_mae_mfe(pos, bar, pip_size)
            
            # Get strategy signal (pass historical data up to current bar)
            historical = data.iloc[:i+1]
            signal = strategy(historical, config.symbol)
            
            # Check for new trade signal
            if signal and len(open_positions) < config.max_positions:
                direction = signal.get("direction")
                stop_loss = signal.get("stop_loss")
                take_profit = signal.get("take_profit")
                
                if direction and stop_loss:
                    # Calculate position size
                    entry_price = bar["close"]
                    
                    # Apply slippage
                    slippage = config.slippage_pips * pip_size
                    if direction == "long":
                        entry_price += slippage
                    else:
                        entry_price -= slippage
                    
                    # Calculate stop distance and position size
                    stop_distance_pips = abs(entry_price - stop_loss) / pip_size
                    risk_amount = balance * (config.risk_per_trade_pct / 100)
                    volume = risk_amount / (stop_distance_pips * pip_value)
                    volume = max(0.01, round(volume, 2))
                    
                    trade_counter += 1
                    pos = BacktestTrade(
                        trade_id=trade_counter,
                        symbol=config.symbol,
                        direction=direction,
                        entry_time=timestamp,
                        entry_price=entry_price,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        volume=volume,
                        strategy_name=signal.get("strategy", "unknown"),
                    )
                    open_positions.append(pos)
            
            # Record equity
            unrealized_pnl = sum(
                self._calculate_unrealized_pnl(p, bar["close"], pip_size, pip_value)
                for p in open_positions
            )
            equity_curve.append({
                "timestamp": timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp),
                "balance": balance,
                "equity": balance + unrealized_pnl,
                "open_positions": len(open_positions),
            })
        
        # Close remaining positions at end
        if open_positions and len(data) > 0:
            last_bar = data.iloc[-1]
            last_time = data.index[-1]
            for pos in open_positions:
                pos = self._close_position(
                    pos, last_bar["close"], last_time, "end_of_test", pip_size, pip_value
                )
                balance += pos.pnl
                trades.append(pos)
        
        # Calculate result metrics
        result = self._calculate_result_metrics(trades, config, equity_curve)
        return result
    
    async def _run_walk_forward(
        self,
        config: BacktestConfig,
        strategy: Callable
    ) -> BacktestResult:
        """Run walk-forward analysis."""
        
        data = await self._load_data(config)
        if data.empty:
            return BacktestResult(config=config)
        
        window_size = len(data) // config.walk_forward_windows
        results = []
        all_trades = []
        
        for i in range(config.walk_forward_windows):
            start_idx = i * window_size
            end_idx = min((i + 2) * window_size, len(data))
            
            if start_idx >= len(data):
                break
            
            window_data = data.iloc[start_idx:end_idx]
            
            # Split into in-sample and out-of-sample
            split_idx = int(len(window_data) * config.in_sample_pct)
            
            # In-sample optimization (simplified - just run strategy)
            is_config = BacktestConfig(
                symbol=config.symbol,
                initial_balance=config.initial_balance,
                leverage=config.leverage,
                spread_pips=config.spread_pips,
                slippage_pips=config.slippage_pips,
                risk_per_trade_pct=config.risk_per_trade_pct,
            )
            
            # Out-of-sample test
            oos_data = window_data.iloc[split_idx:]
            
            oos_result = await self._run_on_data(oos_data, config, strategy)
            
            results.append({
                "window": i + 1,
                "in_sample_start": window_data.index[0].isoformat() if hasattr(window_data.index[0], 'isoformat') else str(window_data.index[0]),
                "out_of_sample_start": oos_data.index[0].isoformat() if len(oos_data) > 0 and hasattr(oos_data.index[0], 'isoformat') else "",
                "oos_trades": len(oos_result.trades),
                "oos_profit": oos_result.net_profit,
                "oos_win_rate": oos_result.win_rate,
                "oos_profit_factor": oos_result.profit_factor,
            })
            
            all_trades.extend(oos_result.trades)
        
        # Combine all out-of-sample results
        final_result = self._calculate_result_metrics(all_trades, config, [])
        final_result.walk_forward_results = results
        
        return final_result
    
    async def _run_on_data(
        self,
        data: pd.DataFrame,
        config: BacktestConfig,
        strategy: Callable
    ) -> BacktestResult:
        """Run backtest on specific data subset."""
        # Similar to simple backtest but on subset
        balance = config.initial_balance
        trades = []
        open_positions = []
        trade_counter = 0
        
        pip_size = self.pip_sizes.get(config.symbol, 0.0001)
        pip_value = self.pip_values.get(config.symbol, 10.0)
        
        for i in range(len(data)):
            bar = data.iloc[i]
            timestamp = data.index[i]
            
            # Check exits
            for pos in open_positions[:]:
                should_close, exit_price, exit_reason = self._check_exit_conditions(
                    pos, bar, pip_size, config
                )
                if should_close:
                    pos = self._close_position(pos, exit_price, timestamp, exit_reason, pip_size, pip_value)
                    balance += pos.pnl
                    trades.append(pos)
                    open_positions.remove(pos)
            
            # Get signal
            signal = strategy(data.iloc[:i+1], config.symbol)
            
            if signal and len(open_positions) < config.max_positions:
                direction = signal.get("direction")
                stop_loss = signal.get("stop_loss")
                
                if direction and stop_loss:
                    entry_price = bar["close"]
                    stop_distance_pips = abs(entry_price - stop_loss) / pip_size
                    risk_amount = balance * (config.risk_per_trade_pct / 100)
                    volume = risk_amount / (stop_distance_pips * pip_value)
                    volume = max(0.01, round(volume, 2))
                    
                    trade_counter += 1
                    pos = BacktestTrade(
                        trade_id=trade_counter,
                        symbol=config.symbol,
                        direction=direction,
                        entry_time=timestamp,
                        entry_price=entry_price,
                        stop_loss=stop_loss,
                        take_profit=signal.get("take_profit"),
                        volume=volume,
                        strategy_name=signal.get("strategy", "unknown"),
                    )
                    open_positions.append(pos)
        
        return self._calculate_result_metrics(trades, config, [])
    
    def _run_monte_carlo(
        self,
        result: BacktestResult,
        config: BacktestConfig
    ) -> Dict:
        """Run Monte Carlo simulation on trade results."""
        
        if not result.trades:
            return {}
        
        r_values = [t.r_multiple for t in result.trades]
        
        final_equities = []
        max_drawdowns = []
        
        for _ in range(config.monte_carlo_runs):
            if config.shuffle_trades:
                shuffled = random.sample(r_values, len(r_values))
            else:
                shuffled = r_values
            
            # Simulate equity curve
            balance = config.initial_balance
            peak = balance
            max_dd = 0
            risk_per_trade = config.initial_balance * (config.risk_per_trade_pct / 100)
            
            for r in shuffled:
                pnl = r * risk_per_trade
                balance += pnl
                
                if balance > peak:
                    peak = balance
                
                dd = (peak - balance) / peak * 100 if peak > 0 else 0
                max_dd = max(max_dd, dd)
            
            final_equities.append(balance)
            max_drawdowns.append(max_dd)
        
        # Calculate percentiles
        final_equities.sort()
        max_drawdowns.sort()
        
        def percentile(data, p):
            idx = int(len(data) * p / 100)
            return data[min(idx, len(data) - 1)]
        
        return {
            "runs": config.monte_carlo_runs,
            "final_equity": {
                "min": min(final_equities),
                "max": max(final_equities),
                "mean": statistics.mean(final_equities),
                "median": statistics.median(final_equities),
                "p5": percentile(final_equities, 5),
                "p25": percentile(final_equities, 25),
                "p75": percentile(final_equities, 75),
                "p95": percentile(final_equities, 95),
            },
            "max_drawdown": {
                "min": min(max_drawdowns),
                "max": max(max_drawdowns),
                "mean": statistics.mean(max_drawdowns),
                "median": statistics.median(max_drawdowns),
                "p5": percentile(max_drawdowns, 5),
                "p95": percentile(max_drawdowns, 95),
            },
            "probability_of_profit": sum(1 for e in final_equities if e > config.initial_balance) / len(final_equities),
            "risk_of_ruin_10pct": sum(1 for e in final_equities if e < config.initial_balance * 0.9) / len(final_equities),
            "risk_of_ruin_25pct": sum(1 for e in final_equities if e < config.initial_balance * 0.75) / len(final_equities),
        }
    
    async def _load_data(self, config: BacktestConfig) -> pd.DataFrame:
        """Load historical data for backtest."""
        # TODO: Implement actual data loading from MT5 or database
        # For now, return empty DataFrame
        return pd.DataFrame()
    
    def _check_exit_conditions(
        self,
        position: BacktestTrade,
        bar: pd.Series,
        pip_size: float,
        config: BacktestConfig
    ) -> tuple:
        """Check if position should be closed."""
        
        high = bar["high"]
        low = bar["low"]
        
        # Apply spread to exit
        spread = config.spread_pips * pip_size
        
        if position.direction == "long":
            # Stop loss hit
            if low <= position.stop_loss:
                return True, position.stop_loss - config.slippage_pips * pip_size, "sl_hit"
            
            # Take profit hit
            if position.take_profit and high >= position.take_profit:
                return True, position.take_profit - spread, "tp_hit"
        
        else:  # short
            # Stop loss hit
            if high >= position.stop_loss:
                return True, position.stop_loss + config.slippage_pips * pip_size, "sl_hit"
            
            # Take profit hit
            if position.take_profit and low <= position.take_profit:
                return True, position.take_profit + spread, "tp_hit"
        
        return False, 0, ""
    
    def _close_position(
        self,
        position: BacktestTrade,
        exit_price: float,
        exit_time: datetime,
        exit_reason: str,
        pip_size: float,
        pip_value: float
    ) -> BacktestTrade:
        """Close a position and calculate P&L."""
        
        position.exit_time = exit_time
        position.exit_price = exit_price
        position.exit_reason = exit_reason
        
        # Calculate P&L
        if position.direction == "long":
            pips = (exit_price - position.entry_price) / pip_size
        else:
            pips = (position.entry_price - exit_price) / pip_size
        
        position.pnl = pips * pip_value * position.volume
        
        # Calculate R-multiple
        stop_distance_pips = abs(position.entry_price - position.stop_loss) / pip_size
        risk_amount = stop_distance_pips * pip_value * position.volume
        
        if risk_amount > 0:
            position.r_multiple = position.pnl / risk_amount
        
        return position
    
    def _update_mae_mfe(self, position: BacktestTrade, bar: pd.Series, pip_size: float):
        """Update MAE and MFE for position."""
        
        if position.direction == "long":
            # MAE is furthest below entry
            adverse = (position.entry_price - bar["low"]) / pip_size
            favorable = (bar["high"] - position.entry_price) / pip_size
        else:
            adverse = (bar["high"] - position.entry_price) / pip_size
            favorable = (position.entry_price - bar["low"]) / pip_size
        
        position.mae_pips = max(position.mae_pips, max(0, adverse))
        position.mfe_pips = max(position.mfe_pips, max(0, favorable))
    
    def _calculate_unrealized_pnl(
        self,
        position: BacktestTrade,
        current_price: float,
        pip_size: float,
        pip_value: float
    ) -> float:
        """Calculate unrealized P&L."""
        
        if position.direction == "long":
            pips = (current_price - position.entry_price) / pip_size
        else:
            pips = (position.entry_price - current_price) / pip_size
        
        return pips * pip_value * position.volume
    
    def _calculate_result_metrics(
        self,
        trades: List[BacktestTrade],
        config: BacktestConfig,
        equity_curve: List[Dict]
    ) -> BacktestResult:
        """Calculate comprehensive backtest metrics."""
        
        result = BacktestResult(config=config)
        result.trades = trades
        result.equity_curve = equity_curve
        
        if not trades:
            return result
        
        result.total_trades = len(trades)
        result.winning_trades = sum(1 for t in trades if t.pnl > 0)
        result.losing_trades = sum(1 for t in trades if t.pnl < 0)
        
        if result.total_trades > 0:
            result.win_rate = result.winning_trades / result.total_trades
        
        result.net_profit = sum(t.pnl for t in trades)
        result.net_profit_pct = (result.net_profit / config.initial_balance) * 100
        
        result.gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
        result.gross_loss = abs(sum(t.pnl for t in trades if t.pnl < 0))
        
        if result.gross_loss > 0:
            result.profit_factor = result.gross_profit / result.gross_loss
        
        if result.total_trades > 0:
            result.avg_trade = result.net_profit / result.total_trades
        
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl < 0]
        
        if wins:
            result.avg_win = sum(t.pnl for t in wins) / len(wins)
        if losses:
            result.avg_loss = sum(t.pnl for t in losses) / len(losses)
        
        # R metrics
        result.total_r = sum(t.r_multiple for t in trades)
        if result.total_trades > 0:
            result.avg_r = result.total_r / result.total_trades
        
        # Expectancy
        if wins and losses:
            avg_win_r = sum(t.r_multiple for t in wins) / len(wins)
            avg_loss_r = sum(t.r_multiple for t in losses) / len(losses)
            result.expectancy = (result.win_rate * avg_win_r) + ((1 - result.win_rate) * avg_loss_r)
        
        # Drawdown
        result.max_drawdown, result.max_drawdown_pct = self._calculate_max_drawdown(equity_curve, config.initial_balance)
        
        # Sharpe/Sortino
        if len(trades) > 1:
            returns = [t.pnl / config.initial_balance for t in trades]
            if statistics.stdev(returns) > 0:
                result.sharpe_ratio = (statistics.mean(returns) / statistics.stdev(returns)) * math.sqrt(252)
            
            neg_returns = [r for r in returns if r < 0]
            if neg_returns and statistics.stdev(neg_returns) > 0:
                result.sortino_ratio = (statistics.mean(returns) / statistics.stdev(neg_returns)) * math.sqrt(252)
        
        # Calmar
        if result.max_drawdown_pct > 0:
            result.calmar_ratio = result.net_profit_pct / result.max_drawdown_pct
        
        return result
    
    def _calculate_max_drawdown(self, equity_curve: List[Dict], initial_balance: float) -> tuple:
        """Calculate maximum drawdown."""
        
        if not equity_curve:
            return 0.0, 0.0
        
        peak = initial_balance
        max_dd = 0.0
        max_dd_pct = 0.0
        
        for point in equity_curve:
            equity = point.get("equity", point.get("balance", initial_balance))
            
            if equity > peak:
                peak = equity
            
            dd = peak - equity
            dd_pct = (dd / peak * 100) if peak > 0 else 0
            
            if dd > max_dd:
                max_dd = dd
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct
        
        return max_dd, max_dd_pct
