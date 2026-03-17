"""
Workflow Scheduler
==================
Orchestrates the scheduled workflows that run the trading system.

From 09_WORKFLOWS.txt:
- Workflow A: Market Open Prep
- Workflow B: Continuous Intraday Scan
- Workflow C: Pre-Trade Approval
- Workflow D: Trade Execution
- Workflow E: Active Position Management
- Workflow F: End-of-Day Review
- Workflow H: Incident Response
"""
import structlog
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum

logger = structlog.get_logger()


class WorkflowStatus(str, Enum):
    """Workflow execution status."""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DISABLED = "disabled"


@dataclass
class WorkflowResult:
    """Result of a workflow execution."""
    workflow_name: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: WorkflowStatus = WorkflowStatus.COMPLETED
    duration_seconds: float = 0.0
    trades_evaluated: int = 0
    trades_approved: int = 0
    trades_rejected: int = 0
    positions_managed: int = 0
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    details: dict = field(default_factory=dict)


class WorkflowScheduler:
    """
    Main scheduler for all trading workflows.
    
    Manages workflow timing, execution, and coordination.
    """
    
    def __init__(
        self,
        scan_interval_seconds: int = 30,
        position_check_interval_seconds: int = 10,
    ):
        self.scan_interval = scan_interval_seconds
        self.position_check_interval = position_check_interval_seconds
        
        self._is_running = False
        self._workflows_enabled = True
        self._scan_task: Optional[asyncio.Task] = None
        self._position_task: Optional[asyncio.Task] = None
        
        # Workflow handlers (to be registered)
        self._scan_handler: Optional[Callable] = None
        self._position_handler: Optional[Callable] = None
        self._eod_handler: Optional[Callable] = None
        
        # State
        self._last_scan: Optional[datetime] = None
        self._last_position_check: Optional[datetime] = None
        self._last_eod_review: Optional[datetime] = None
        
        # Results history
        self._recent_results: list[WorkflowResult] = []
        
        self._logger = logger.bind(component="scheduler")
    
    def register_scan_handler(self, handler: Callable) -> None:
        """Register the intraday scan handler."""
        self._scan_handler = handler
    
    def register_position_handler(self, handler: Callable) -> None:
        """Register the position management handler."""
        self._position_handler = handler
    
    def register_eod_handler(self, handler: Callable) -> None:
        """Register the end-of-day review handler."""
        self._eod_handler = handler
    
    async def start(self) -> None:
        """Start the scheduler."""
        if self._is_running:
            return
        
        self._is_running = True
        self._logger.info("Workflow scheduler starting")
        
        # Start background tasks
        self._scan_task = asyncio.create_task(self._scan_loop())
        self._position_task = asyncio.create_task(self._position_loop())
        
        self._logger.info(
            "Workflow scheduler started",
            scan_interval=self.scan_interval,
            position_interval=self.position_check_interval,
        )
    
    async def stop(self) -> None:
        """Stop the scheduler."""
        self._is_running = False
        
        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
        
        if self._position_task:
            self._position_task.cancel()
            try:
                await self._position_task
            except asyncio.CancelledError:
                pass
        
        self._logger.info("Workflow scheduler stopped")
    
    async def _scan_loop(self) -> None:
        """Continuous intraday scan loop (Workflow B)."""
        while self._is_running:
            try:
                if self._workflows_enabled and self._scan_handler:
                    result = await self._run_workflow("intraday_scan", self._scan_handler)
                    self._last_scan = datetime.now(timezone.utc)
                    self._store_result(result)
                
                await asyncio.sleep(self.scan_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error("Scan loop error", error=str(e), exc_info=True)
                await asyncio.sleep(self.scan_interval)
    
    async def _position_loop(self) -> None:
        """Position management loop (Workflow E)."""
        while self._is_running:
            try:
                if self._workflows_enabled and self._position_handler:
                    result = await self._run_workflow("position_management", self._position_handler)
                    self._last_position_check = datetime.now(timezone.utc)
                    self._store_result(result)
                
                await asyncio.sleep(self.position_check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error("Position loop error", error=str(e), exc_info=True)
                await asyncio.sleep(self.position_check_interval)
    
    async def _run_workflow(
        self,
        name: str,
        handler: Callable,
    ) -> WorkflowResult:
        """Run a workflow with timing and error handling."""
        result = WorkflowResult(
            workflow_name=name,
            started_at=datetime.now(timezone.utc),
        )
        
        try:
            details = await handler()
            result.status = WorkflowStatus.COMPLETED
            result.details = details or {}
            
            # Extract metrics if provided
            if isinstance(details, dict):
                result.trades_evaluated = details.get("trades_evaluated", 0)
                result.trades_approved = details.get("trades_approved", 0)
                result.trades_rejected = details.get("trades_rejected", 0)
                result.positions_managed = details.get("positions_managed", 0)
                result.warnings = details.get("warnings", [])
            
        except Exception as e:
            result.status = WorkflowStatus.FAILED
            result.errors.append(str(e))
            self._logger.error(
                "Workflow failed",
                workflow=name,
                error=str(e),
                exc_info=True,
            )
        
        result.completed_at = datetime.now(timezone.utc)
        result.duration_seconds = (
            result.completed_at - result.started_at
        ).total_seconds()
        
        return result
    
    def _store_result(self, result: WorkflowResult) -> None:
        """Store workflow result, keeping recent history."""
        self._recent_results.append(result)
        
        # Keep only last 100 results
        if len(self._recent_results) > 100:
            self._recent_results = self._recent_results[-100:]
    
    async def run_eod_review(self) -> WorkflowResult:
        """Run end-of-day review (Workflow F) on demand."""
        if not self._eod_handler:
            return WorkflowResult(
                workflow_name="eod_review",
                started_at=datetime.now(timezone.utc),
                status=WorkflowStatus.FAILED,
                errors=["No EOD handler registered"],
            )
        
        result = await self._run_workflow("eod_review", self._eod_handler)
        self._last_eod_review = datetime.now(timezone.utc)
        self._store_result(result)
        return result
    
    def enable_workflows(self) -> None:
        """Enable workflow execution."""
        self._workflows_enabled = True
        self._logger.info("Workflows enabled")
    
    def disable_workflows(self) -> None:
        """Disable workflow execution (emergency stop)."""
        self._workflows_enabled = False
        self._logger.warning("Workflows disabled")
    
    def get_status(self) -> dict:
        """Get current scheduler status."""
        return {
            "is_running": self._is_running,
            "workflows_enabled": self._workflows_enabled,
            "scan_interval_seconds": self.scan_interval,
            "position_check_interval_seconds": self.position_check_interval,
            "last_scan": self._last_scan.isoformat() if self._last_scan else None,
            "last_position_check": self._last_position_check.isoformat() if self._last_position_check else None,
            "last_eod_review": self._last_eod_review.isoformat() if self._last_eod_review else None,
            "recent_results_count": len(self._recent_results),
        }
    
    def get_recent_results(self, limit: int = 10) -> list[dict]:
        """Get recent workflow results."""
        return [
            {
                "workflow_name": r.workflow_name,
                "started_at": r.started_at.isoformat(),
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "status": r.status.value,
                "duration_seconds": r.duration_seconds,
                "trades_evaluated": r.trades_evaluated,
                "trades_approved": r.trades_approved,
                "errors": r.errors,
            }
            for r in self._recent_results[-limit:]
        ]


class TradingWorkflows:
    """
    Implementation of the core trading workflows.
    
    These are the actual workflow implementations that get registered
    with the scheduler.
    """
    
    def __init__(
        self,
        symbols: list[str],
        market_data_agent,
        technical_agent,
        structure_agent,
        regime_agent,
        strategy_agent,
        orchestrator_agent,
        risk_manager_agent,
        portfolio_agent,
        execution_agent,
    ):
        self.symbols = symbols
        self.market_data = market_data_agent
        self.technical = technical_agent
        self.structure = structure_agent
        self.regime = regime_agent
        self.strategy = strategy_agent
        self.orchestrator = orchestrator_agent
        self.risk_manager = risk_manager_agent
        self.portfolio = portfolio_agent
        self.execution = execution_agent
        
        self._logger = logger.bind(component="trading_workflows")
    
    async def intraday_scan(self) -> dict:
        """
        Workflow B: Continuous Intraday Scan
        
        Scans all symbols for trade opportunities.
        """
        results = {
            "trades_evaluated": 0,
            "trades_approved": 0,
            "trades_rejected": 0,
            "watchlisted": 0,
            "warnings": [],
            "symbols_scanned": [],
        }
        
        for symbol in self.symbols:
            try:
                # Get market data
                data_msg = await self.market_data._execute({"symbol": symbol})
                if data_msg.errors:
                    results["warnings"].append(f"{symbol}: Data errors")
                    continue
                
                market_data = data_msg.payload.get("snapshots", {}).get(symbol, {})
                
                # Skip if data quality too low
                if market_data.get("data_quality_score", 0) < 0.7:
                    continue
                
                results["symbols_scanned"].append(symbol)
                
                # Run analysis pipeline
                tech_msg = await self.technical._execute({
                    "symbol": symbol,
                    "market_data": market_data,
                })
                
                struct_msg = await self.structure._execute({
                    "symbol": symbol,
                    "market_data": market_data,
                })
                
                regime_msg = await self.regime._execute({
                    "symbol": symbol,
                    "technical": tech_msg.payload,
                    "structure": struct_msg.payload,
                })
                
                # Strategy selection
                strategy_msg = await self.strategy._execute({
                    "symbol": symbol,
                    "technical": tech_msg.payload,
                    "structure": struct_msg.payload,
                    "regime": regime_msg.payload,
                    "market_data": market_data,
                })
                
                results["trades_evaluated"] += 1
                
                # If no signal, skip
                if not strategy_msg.payload.get("selected_signal"):
                    continue
                
                # Pre-trade risk check
                signal = strategy_msg.payload["selected_signal"]
                equity = self.execution.get_account_state().get("equity", 10000)
                
                risk_msg = await self.risk_manager._execute({
                    "symbol": symbol,
                    "direction": signal.get("direction"),
                    "stop_loss": signal.get("stop_loss"),
                    "entry_price": signal.get("entry_price") or market_data.get("current_price", 0),
                    "take_profit": signal.get("take_profit_1"),
                    "equity": equity,
                    "regime_risk_multiplier": regime_msg.payload.get("regime_risk_multiplier", 1.0),
                    "confidence": signal.get("confidence", 0.5),
                    "spread_pips": market_data.get("current_spread_pips", 2.0),
                })
                
                # Portfolio exposure check
                positions = self.execution.get_open_positions()
                exposure_msg = await self.portfolio._execute({
                    "symbol": symbol,
                    "direction": signal.get("direction"),
                    "lot_size": risk_msg.payload.get("position_sizing", {}).get("lot_size", 0.01),
                    "risk_pct": risk_msg.payload.get("position_sizing", {}).get("risk_percent", 0.35),
                    "open_positions": positions,
                })
                
                # Orchestrator decision
                decision_msg = await self.orchestrator._execute({
                    "symbol": symbol,
                    "market_data": market_data,
                    "technical": tech_msg.payload,
                    "structure": struct_msg.payload,
                    "regime": regime_msg.payload,
                    "strategy": strategy_msg.payload,
                    "risk_approval": risk_msg.payload,
                    "portfolio_exposure": exposure_msg.payload,
                })
                
                decision = decision_msg.payload.get("decision", "NO_TRADE")
                
                if decision in ["BUY", "SELL"]:
                    results["trades_approved"] += 1
                    
                    # Execute the trade
                    trade_plan = decision_msg.payload.get("trade_plan")
                    if trade_plan:
                        # Get current prices
                        prices = {
                            symbol: (
                                market_data.get("current_price", 0) - 0.00005,
                                market_data.get("current_price", 0) + 0.00005,
                            )
                        }
                        
                        exec_msg = await self.execution._execute({
                            "trade_plan": trade_plan,
                            "current_prices": prices,
                        })
                        
                        if not exec_msg.payload.get("success"):
                            results["warnings"].append(
                                f"{symbol}: Execution failed - {exec_msg.payload.get('error_message')}"
                            )
                
                elif decision == "WATCHLIST":
                    results["watchlisted"] += 1
                else:
                    results["trades_rejected"] += 1
                
            except Exception as e:
                self._logger.error(
                    "Symbol scan error",
                    symbol=symbol,
                    error=str(e),
                    exc_info=True,
                )
                results["warnings"].append(f"{symbol}: {str(e)}")
        
        return results
    
    async def position_management(self) -> dict:
        """
        Workflow E: Active Position Management
        
        Monitors open positions for SL/TP hits and potential modifications.
        """
        results = {
            "positions_managed": 0,
            "stops_hit": 0,
            "targets_hit": 0,
            "modifications": 0,
            "warnings": [],
        }
        
        positions = self.execution.get_open_positions()
        results["positions_managed"] = len(positions)
        
        # Collect current prices for all symbols with positions
        symbols_needed = list(set(p["symbol"] for p in positions))
        prices = {}
        
        for symbol in symbols_needed:
            data_msg = await self.market_data._execute({"symbol": symbol})
            snapshot = data_msg.payload.get("snapshots", {}).get(symbol, {})
            current_price = snapshot.get("current_price", 0)
            spread = snapshot.get("current_spread_pips", 1.5) * 0.0001
            if current_price:
                prices[symbol] = (current_price - spread/2, current_price + spread/2)
        
        # Update prices (this triggers SL/TP checks)
        closed_tickets = self.execution.update_prices(prices)
        results["stops_hit"] = len([t for t in closed_tickets])  # Simplified
        
        # Check for trailing stop opportunities
        for pos in positions:
            if pos["ticket"] in closed_tickets:
                continue
            
            # Example: Trail stop if position is profitable
            unrealized_pips = pos.get("unrealized_pips", 0)
            if unrealized_pips > 20:  # In profit by 20+ pips
                # Could implement trailing logic here
                pass
        
        return results
    
    async def eod_review(self) -> dict:
        """
        Workflow F: End-of-Day Review
        
        Generates daily summary and performance metrics.
        """
        results = {
            "trades_today": 0,
            "wins": 0,
            "losses": 0,
            "pnl_today": 0.0,
            "open_positions": 0,
        }
        
        account = self.execution.get_account_state()
        positions = self.execution.get_open_positions()
        
        results["pnl_today"] = account.get("realized_pnl_today", 0)
        results["open_positions"] = len(positions)
        
        # Would normally aggregate journal entries for today
        # This is simplified
        
        self._logger.info(
            "End of day review",
            pnl=results["pnl_today"],
            open_positions=results["open_positions"],
        )
        
        return results
