"""
Execution Agent
===============
Handles trade execution in paper or live mode.

From 07_EXECUTION_AND_MT5.txt:
- Receives approved trade plans from Orchestrator
- Performs final pre-execution checks
- Executes via Paper Trading Service or MT5
- Generates execution receipts
- NEVER executes without a stop loss
"""
import structlog
from datetime import datetime, timezone
from typing import Any, Optional
from dataclasses import dataclass, field
from uuid import uuid4

from app.agents.base_agent import BaseAgent, AgentMessage, AgentHealthStatus
from app.services.paper_trading_service import PaperTradingService, PaperFill

logger = structlog.get_logger()


@dataclass
class ExecutionReceipt:
    """Record of an execution attempt."""
    receipt_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    plan_id: str = ""
    
    # Request
    symbol: str = ""
    direction: str = ""
    requested_volume: float = 0.0
    requested_price: Optional[float] = None
    stop_loss: float = 0.0
    take_profit: Optional[float] = None
    
    # Result
    success: bool = False
    execution_mode: str = "paper"
    ticket: Optional[int] = None
    fill_price: Optional[float] = None
    fill_volume: Optional[float] = None
    slippage_pips: float = 0.0
    
    # Verification
    stop_confirmed: bool = False
    tp_confirmed: bool = False
    
    # Timing
    latency_ms: int = 0
    
    # Issues
    error_message: Optional[str] = None
    warnings: list = field(default_factory=list)


class ExecutionAgent(BaseAgent):
    """
    Execution Agent.
    
    Executes approved trade plans via paper trading or live broker.
    
    CRITICAL SAFETY:
    - NEVER executes without a stop loss
    - Performs final safety checks before execution
    - All executions are logged
    """
    
    def __init__(
        self,
        name: str = "execution_agent",
        config: Optional[dict[str, Any]] = None,
    ):
        super().__init__(name, config)
        
        self.execution_mode = config.get("execution_mode", "paper") if config else "paper"
        
        # Paper trading service
        starting_balance = config.get("starting_balance", 10000.0) if config else 10000.0
        self._paper_service = PaperTradingService(starting_balance=starting_balance)
        
        # Live trading service would be initialized here if mode is live
        self._live_service = None
    
    async def initialize(self) -> None:
        """Initialize the agent."""
        self.is_initialized = True
        self.is_running = True
        self.started_at = datetime.now(timezone.utc)
        self._logger.info(
            "Execution Agent initialized",
            execution_mode=self.execution_mode,
        )
    
    async def run(self, context: dict[str, Any]) -> AgentMessage:
        """
        Execute a trade plan.
        
        Args:
            context: Must contain:
                - trade_plan: TradePlan from Orchestrator
                - current_prices: Dict of symbol -> (bid, ask)
        """
        trade_plan = context.get("trade_plan")
        current_prices = context.get("current_prices", {})
        
        if not trade_plan:
            return self._create_message(
                message_type="error",
                payload={"error": "No trade plan provided"},
                confidence=0.0,
                errors=["Missing trade_plan"],
            )
        
        # Execute
        receipt = await self._execute_trade(trade_plan, current_prices)
        
        return self._create_message(
            message_type="execution_receipt",
            payload=self._receipt_to_dict(receipt),
            symbol=trade_plan.get("symbol"),
            confidence=1.0 if receipt.success else 0.0,
            warnings=receipt.warnings,
            errors=[receipt.error_message] if receipt.error_message else [],
        )
    
    async def _execute_trade(
        self,
        trade_plan: dict,
        current_prices: dict,
    ) -> ExecutionReceipt:
        """Execute the trade plan."""
        start_time = datetime.now(timezone.utc)
        
        receipt = ExecutionReceipt(
            plan_id=trade_plan.get("plan_id", ""),
            symbol=trade_plan.get("symbol", ""),
            direction=trade_plan.get("direction", ""),
            requested_volume=trade_plan.get("lot_size", 0),
            requested_price=trade_plan.get("entry_price"),
            stop_loss=trade_plan.get("stop_loss", 0),
            take_profit=trade_plan.get("take_profit_1"),
            execution_mode=self.execution_mode,
        )
        
        # ========== FINAL SAFETY CHECKS ==========
        
        # CHECK 1: Stop loss MUST be defined
        if receipt.stop_loss <= 0:
            receipt.success = False
            receipt.error_message = "BLOCKED: No stop loss defined"
            self._logger.error("Execution blocked: no stop loss", plan_id=receipt.plan_id)
            return receipt
        
        # CHECK 2: Valid volume
        if receipt.requested_volume <= 0:
            receipt.success = False
            receipt.error_message = "BLOCKED: Invalid volume"
            return receipt
        
        # CHECK 3: Get current price
        symbol = receipt.symbol
        if symbol not in current_prices:
            # Try to use requested price
            if not receipt.requested_price:
                receipt.success = False
                receipt.error_message = "BLOCKED: No current price available"
                return receipt
            current_price = receipt.requested_price
        else:
            bid, ask = current_prices[symbol]
            current_price = ask if receipt.direction == "long" else bid
        
        # CHECK 4: Re-check spread (final check)
        if symbol in current_prices:
            bid, ask = current_prices[symbol]
            spread_pips = (ask - bid) / 0.0001
            if spread_pips > 5.0:  # Hard limit
                receipt.success = False
                receipt.error_message = f"BLOCKED: Spread too high ({spread_pips:.1f} pips)"
                return receipt
            if spread_pips > 3.0:
                receipt.warnings.append(f"Elevated spread: {spread_pips:.1f} pips")
        
        # CHECK 5: Verify execution mode allows trading
        if self.execution_mode == "paper":
            pass  # Always allowed
        elif self.execution_mode == "live":
            if not self._live_service:
                receipt.success = False
                receipt.error_message = "BLOCKED: Live trading not configured"
                return receipt
        
        # ========== EXECUTE ==========
        
        if self.execution_mode == "paper":
            success, fill, error = self._paper_service.place_market_order(
                symbol=receipt.symbol,
                direction=receipt.direction,
                volume=receipt.requested_volume,
                stop_loss=receipt.stop_loss,
                take_profit=receipt.take_profit,
                current_price=current_price,
                plan_id=receipt.plan_id,
                strategy=trade_plan.get("strategy_name", ""),
            )
            
            if success and fill:
                receipt.success = True
                receipt.ticket = fill.ticket
                receipt.fill_price = fill.fill_price
                receipt.fill_volume = fill.volume
                receipt.slippage_pips = fill.slippage_pips
                receipt.stop_confirmed = True
                receipt.tp_confirmed = receipt.take_profit is not None
            else:
                receipt.success = False
                receipt.error_message = error
        
        elif self.execution_mode == "live":
            # Live execution would go here
            receipt.success = False
            receipt.error_message = "Live trading not yet implemented"
        
        # Calculate latency
        receipt.latency_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
        
        # Log execution
        if receipt.success:
            self._logger.info(
                "Trade executed",
                plan_id=receipt.plan_id,
                ticket=receipt.ticket,
                symbol=receipt.symbol,
                direction=receipt.direction,
                volume=receipt.fill_volume,
                fill_price=receipt.fill_price,
                slippage_pips=receipt.slippage_pips,
                mode=self.execution_mode,
            )
        else:
            self._logger.warning(
                "Trade execution failed",
                plan_id=receipt.plan_id,
                error=receipt.error_message,
            )
        
        return receipt
    
    async def close_position(
        self,
        ticket: int,
        current_price: float,
        volume: Optional[float] = None,
    ) -> ExecutionReceipt:
        """Close an existing position."""
        receipt = ExecutionReceipt(
            execution_mode=self.execution_mode,
        )
        
        if self.execution_mode == "paper":
            success, fill, error = self._paper_service.close_position(
                ticket=ticket,
                current_price=current_price,
                volume=volume,
            )
            
            if success and fill:
                receipt.success = True
                receipt.ticket = ticket
                receipt.fill_price = fill.fill_price
                receipt.fill_volume = fill.volume
                receipt.slippage_pips = fill.slippage_pips
            else:
                receipt.success = False
                receipt.error_message = error
        
        return receipt
    
    async def modify_position(
        self,
        ticket: int,
        new_stop_loss: Optional[float] = None,
        new_take_profit: Optional[float] = None,
    ) -> tuple[bool, str]:
        """Modify position SL/TP."""
        if self.execution_mode == "paper":
            return self._paper_service.modify_position(
                ticket=ticket,
                new_stop_loss=new_stop_loss,
                new_take_profit=new_take_profit,
            )
        return False, "Live modification not implemented"
    
    def update_prices(self, prices: dict[str, tuple[float, float]]) -> list[int]:
        """Update prices and check SL/TP hits."""
        if self.execution_mode == "paper":
            return self._paper_service.update_prices(prices)
        return []
    
    def get_account_state(self) -> dict:
        """Get current account state."""
        if self.execution_mode == "paper":
            return self._paper_service.get_account_state()
        return {}
    
    def get_open_positions(self) -> list[dict]:
        """Get all open positions."""
        if self.execution_mode == "paper":
            return self._paper_service.get_open_positions()
        return []
    
    def _receipt_to_dict(self, receipt: ExecutionReceipt) -> dict:
        """Convert receipt to serializable dict."""
        return {
            "receipt_id": receipt.receipt_id,
            "timestamp": receipt.timestamp.isoformat(),
            "plan_id": receipt.plan_id,
            "symbol": receipt.symbol,
            "direction": receipt.direction,
            "requested_volume": receipt.requested_volume,
            "requested_price": receipt.requested_price,
            "stop_loss": receipt.stop_loss,
            "take_profit": receipt.take_profit,
            "success": receipt.success,
            "execution_mode": receipt.execution_mode,
            "ticket": receipt.ticket,
            "fill_price": receipt.fill_price,
            "fill_volume": receipt.fill_volume,
            "slippage_pips": receipt.slippage_pips,
            "stop_confirmed": receipt.stop_confirmed,
            "tp_confirmed": receipt.tp_confirmed,
            "latency_ms": receipt.latency_ms,
            "error_message": receipt.error_message,
            "warnings": receipt.warnings,
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
        return ["orchestrator_agent"]
