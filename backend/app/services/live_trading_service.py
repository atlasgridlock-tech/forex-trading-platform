"""
Live Trading Service

THE BRIDGE TO REAL MONEY.

This service is the final gateway between the trading system and live execution.
Every safety mechanism in the system converges here.

CRITICAL: This service MUST NOT be enabled until all promotion gates pass.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import asyncio
import json

from app.data.mt5_connector import MT5Connector, MT5ConnectionStatus
from app.services.paper_trading_service import PaperTradingService


class TradingMode(Enum):
    """System trading mode."""
    PAPER = "paper"  # Paper trading only
    SHADOW = "shadow"  # Real signals, paper execution
    LIVE = "live"  # Real execution (requires explicit enable)


class PromotionGate(Enum):
    """Gates that must pass for live trading."""
    MIN_TRADES = "min_trades"
    MIN_DAYS = "min_days"
    PROFIT_FACTOR = "profit_factor"
    MAX_DRAWDOWN = "max_drawdown"
    WIN_RATE = "win_rate"
    AVG_RR = "avg_rr"
    MANUAL_APPROVAL = "manual_approval"


@dataclass
class PromotionStatus:
    """Current promotion gate status."""
    gate: PromotionGate
    required: Any
    actual: Any
    passed: bool
    checked_at: datetime


@dataclass
class LiveTradingConfig:
    """Live trading configuration."""
    # Mode
    mode: TradingMode = TradingMode.PAPER
    
    # Promotion requirements
    min_paper_trades: int = 100
    min_paper_days: int = 30
    min_profit_factor: float = 1.3
    max_drawdown_pct: float = 5.0
    min_win_rate: float = 0.40
    min_avg_rr: float = 1.5
    
    # Live trading limits (additional safety)
    live_max_daily_loss_pct: float = 1.0  # Tighter than paper
    live_max_position_size: float = 0.5  # Max 0.5 lots
    live_max_positions: int = 3  # Fewer than paper
    live_max_risk_per_trade: float = 0.25  # Lower than paper
    
    # Kill switches
    emergency_stop_enabled: bool = True
    daily_loss_kill_switch: bool = True
    weekly_loss_kill_switch: bool = True
    
    # Manual approval required
    manual_approval_required: bool = True
    manual_approval_by: Optional[str] = None
    manual_approval_at: Optional[datetime] = None


@dataclass 
class ExecutionReceipt:
    """Receipt for executed trade."""
    receipt_id: str
    timestamp: datetime
    mode: TradingMode
    
    # Order details
    symbol: str
    direction: str
    volume: float
    order_type: str
    
    # Execution
    requested_price: float
    executed_price: float
    slippage_pips: float
    
    # Result
    success: bool
    ticket: Optional[int] = None
    error: Optional[str] = None
    
    # Safety checks passed
    safety_checks: Dict[str, bool] = field(default_factory=dict)


class LiveTradingService:
    """
    Live trading service - the bridge to real money.
    
    This service implements multiple layers of protection:
    1. Mode enforcement (PAPER → SHADOW → LIVE)
    2. Promotion gates (must pass all before live)
    3. Pre-execution safety checks
    4. Kill switches
    5. Position limits
    6. Audit trail
    """
    
    def __init__(
        self,
        mt5_connector: MT5Connector,
        paper_service: PaperTradingService,
        config: LiveTradingConfig = None,
        db_session=None,
        redis_client=None,
    ):
        self.mt5 = mt5_connector
        self.paper = paper_service
        self.config = config or LiveTradingConfig()
        self.db = db_session
        self.redis = redis_client
        
        # State
        self._initialized = False
        self._kill_switch_active = False
        self._kill_switch_reason = ""
        self._daily_pnl = 0.0
        self._weekly_pnl = 0.0
        self._last_reset_date = None
        
        # Audit
        self._execution_log: List[ExecutionReceipt] = []
        
    async def initialize(self):
        """Initialize the live trading service."""
        # CRITICAL: Start in PAPER mode always
        if self.config.mode == TradingMode.LIVE:
            # Verify this is intentional
            if not await self._verify_live_mode_authorization():
                self.config.mode = TradingMode.PAPER
                raise RuntimeError(
                    "SAFETY: Live mode requested but authorization failed. "
                    "Reverted to PAPER mode."
                )
        
        # Connect to MT5 if needed
        if self.config.mode in (TradingMode.SHADOW, TradingMode.LIVE):
            if not await self.mt5.connect():
                raise RuntimeError("Failed to connect to MT5")
        
        self._initialized = True
        self._last_reset_date = datetime.utcnow().date()
        
    async def _verify_live_mode_authorization(self) -> bool:
        """Verify that live mode is properly authorized."""
        
        # Check all promotion gates
        gates = await self.check_promotion_gates()
        
        if not all(g.passed for g in gates):
            failed = [g.gate.value for g in gates if not g.passed]
            print(f"SAFETY: Promotion gates not passed: {failed}")
            return False
        
        # Check manual approval
        if self.config.manual_approval_required:
            if not self.config.manual_approval_by:
                print("SAFETY: Manual approval required but not provided")
                return False
            
            # Approval must be recent (within 24 hours)
            if self.config.manual_approval_at:
                age = datetime.utcnow() - self.config.manual_approval_at
                if age > timedelta(hours=24):
                    print("SAFETY: Manual approval has expired (>24h)")
                    return False
        
        return True
    
    async def check_promotion_gates(self) -> List[PromotionStatus]:
        """Check all promotion gates."""
        # Get paper trading metrics
        metrics = await self._get_paper_metrics()
        
        gates = []
        now = datetime.utcnow()
        
        # Gate 1: Minimum trades
        gates.append(PromotionStatus(
            gate=PromotionGate.MIN_TRADES,
            required=self.config.min_paper_trades,
            actual=metrics.get("total_trades", 0),
            passed=metrics.get("total_trades", 0) >= self.config.min_paper_trades,
            checked_at=now,
        ))
        
        # Gate 2: Minimum days
        days_trading = metrics.get("days_trading", 0)
        gates.append(PromotionStatus(
            gate=PromotionGate.MIN_DAYS,
            required=self.config.min_paper_days,
            actual=days_trading,
            passed=days_trading >= self.config.min_paper_days,
            checked_at=now,
        ))
        
        # Gate 3: Profit factor
        pf = metrics.get("profit_factor", 0)
        gates.append(PromotionStatus(
            gate=PromotionGate.PROFIT_FACTOR,
            required=self.config.min_profit_factor,
            actual=round(pf, 2),
            passed=pf >= self.config.min_profit_factor,
            checked_at=now,
        ))
        
        # Gate 4: Max drawdown
        dd = metrics.get("max_drawdown_pct", 100)
        gates.append(PromotionStatus(
            gate=PromotionGate.MAX_DRAWDOWN,
            required=f"≤{self.config.max_drawdown_pct}%",
            actual=f"{round(dd, 2)}%",
            passed=dd <= self.config.max_drawdown_pct,
            checked_at=now,
        ))
        
        # Gate 5: Win rate
        wr = metrics.get("win_rate", 0)
        gates.append(PromotionStatus(
            gate=PromotionGate.WIN_RATE,
            required=f"≥{self.config.min_win_rate:.0%}",
            actual=f"{wr:.1%}",
            passed=wr >= self.config.min_win_rate,
            checked_at=now,
        ))
        
        # Gate 6: Average R:R
        avg_rr = metrics.get("avg_rr", 0)
        gates.append(PromotionStatus(
            gate=PromotionGate.AVG_RR,
            required=f"≥{self.config.min_avg_rr}",
            actual=round(avg_rr, 2),
            passed=avg_rr >= self.config.min_avg_rr,
            checked_at=now,
        ))
        
        # Gate 7: Manual approval
        gates.append(PromotionStatus(
            gate=PromotionGate.MANUAL_APPROVAL,
            required="Required" if self.config.manual_approval_required else "Not required",
            actual=self.config.manual_approval_by or "Not approved",
            passed=not self.config.manual_approval_required or bool(self.config.manual_approval_by),
            checked_at=now,
        ))
        
        return gates
    
    async def _get_paper_metrics(self) -> Dict[str, Any]:
        """Get paper trading performance metrics."""
        # Would query from PerformanceAnalyticsAgent
        # Placeholder for now
        return {
            "total_trades": 0,
            "days_trading": 0,
            "profit_factor": 0,
            "max_drawdown_pct": 0,
            "win_rate": 0,
            "avg_rr": 0,
        }
    
    async def execute_trade(
        self,
        symbol: str,
        direction: str,
        volume: float,
        stop_loss: float,
        take_profit: Optional[float] = None,
        order_type: str = "market",
        price: Optional[float] = None,
        trade_id: Optional[str] = None,
    ) -> ExecutionReceipt:
        """
        Execute a trade with full safety checks.
        
        This is THE critical function that bridges to real money.
        """
        
        receipt_id = f"EXEC-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
        timestamp = datetime.utcnow()
        
        # Initialize safety checks dict
        safety_checks = {
            "mode_check": False,
            "kill_switch_check": False,
            "position_limit_check": False,
            "risk_limit_check": False,
            "stop_loss_check": False,
            "daily_loss_check": False,
            "mt5_connection_check": False,
        }
        
        # ═══════════════════════════════════════════════════════════════
        # SAFETY CHECK 1: MODE CHECK
        # ═══════════════════════════════════════════════════════════════
        if self.config.mode == TradingMode.PAPER:
            # Paper mode - execute on paper service
            safety_checks["mode_check"] = True
            return await self._execute_paper(
                symbol, direction, volume, stop_loss, take_profit,
                receipt_id, timestamp, safety_checks
            )
        
        safety_checks["mode_check"] = True
        
        # ═══════════════════════════════════════════════════════════════
        # SAFETY CHECK 2: KILL SWITCH
        # ═══════════════════════════════════════════════════════════════
        if self._kill_switch_active:
            return ExecutionReceipt(
                receipt_id=receipt_id,
                timestamp=timestamp,
                mode=self.config.mode,
                symbol=symbol,
                direction=direction,
                volume=volume,
                order_type=order_type,
                requested_price=price or 0,
                executed_price=0,
                slippage_pips=0,
                success=False,
                error=f"KILL SWITCH ACTIVE: {self._kill_switch_reason}",
                safety_checks=safety_checks,
            )
        
        safety_checks["kill_switch_check"] = True
        
        # ═══════════════════════════════════════════════════════════════
        # SAFETY CHECK 3: STOP LOSS REQUIRED
        # ═══════════════════════════════════════════════════════════════
        if not stop_loss or stop_loss <= 0:
            return ExecutionReceipt(
                receipt_id=receipt_id,
                timestamp=timestamp,
                mode=self.config.mode,
                symbol=symbol,
                direction=direction,
                volume=volume,
                order_type=order_type,
                requested_price=price or 0,
                executed_price=0,
                slippage_pips=0,
                success=False,
                error="CRITICAL: Stop loss is REQUIRED for all trades",
                safety_checks=safety_checks,
            )
        
        safety_checks["stop_loss_check"] = True
        
        # ═══════════════════════════════════════════════════════════════
        # SAFETY CHECK 4: POSITION LIMITS
        # ═══════════════════════════════════════════════════════════════
        current_positions = await self._get_open_position_count()
        if current_positions >= self.config.live_max_positions:
            return ExecutionReceipt(
                receipt_id=receipt_id,
                timestamp=timestamp,
                mode=self.config.mode,
                symbol=symbol,
                direction=direction,
                volume=volume,
                order_type=order_type,
                requested_price=price or 0,
                executed_price=0,
                slippage_pips=0,
                success=False,
                error=f"Position limit reached ({current_positions}/{self.config.live_max_positions})",
                safety_checks=safety_checks,
            )
        
        safety_checks["position_limit_check"] = True
        
        # ═══════════════════════════════════════════════════════════════
        # SAFETY CHECK 5: VOLUME/RISK LIMITS
        # ═══════════════════════════════════════════════════════════════
        if volume > self.config.live_max_position_size:
            return ExecutionReceipt(
                receipt_id=receipt_id,
                timestamp=timestamp,
                mode=self.config.mode,
                symbol=symbol,
                direction=direction,
                volume=volume,
                order_type=order_type,
                requested_price=price or 0,
                executed_price=0,
                slippage_pips=0,
                success=False,
                error=f"Volume {volume} exceeds max {self.config.live_max_position_size}",
                safety_checks=safety_checks,
            )
        
        safety_checks["risk_limit_check"] = True
        
        # ═══════════════════════════════════════════════════════════════
        # SAFETY CHECK 6: DAILY LOSS LIMIT
        # ═══════════════════════════════════════════════════════════════
        account = await self.mt5.get_account_info()
        if account:
            balance = account.get("balance", 0)
            daily_loss_limit = balance * (self.config.live_max_daily_loss_pct / 100)
            
            if self._daily_pnl <= -daily_loss_limit:
                self._activate_kill_switch("Daily loss limit reached")
                return ExecutionReceipt(
                    receipt_id=receipt_id,
                    timestamp=timestamp,
                    mode=self.config.mode,
                    symbol=symbol,
                    direction=direction,
                    volume=volume,
                    order_type=order_type,
                    requested_price=price or 0,
                    executed_price=0,
                    slippage_pips=0,
                    success=False,
                    error="Daily loss limit reached - trading halted",
                    safety_checks=safety_checks,
                )
        
        safety_checks["daily_loss_check"] = True
        
        # ═══════════════════════════════════════════════════════════════
        # SAFETY CHECK 7: MT5 CONNECTION
        # ═══════════════════════════════════════════════════════════════
        if not self.mt5.is_connected():
            return ExecutionReceipt(
                receipt_id=receipt_id,
                timestamp=timestamp,
                mode=self.config.mode,
                symbol=symbol,
                direction=direction,
                volume=volume,
                order_type=order_type,
                requested_price=price or 0,
                executed_price=0,
                slippage_pips=0,
                success=False,
                error="MT5 not connected",
                safety_checks=safety_checks,
            )
        
        safety_checks["mt5_connection_check"] = True
        
        # ═══════════════════════════════════════════════════════════════
        # ALL CHECKS PASSED - EXECUTE
        # ═══════════════════════════════════════════════════════════════
        
        if self.config.mode == TradingMode.SHADOW:
            # Shadow mode - log but don't execute real trade
            return await self._execute_shadow(
                symbol, direction, volume, stop_loss, take_profit,
                receipt_id, timestamp, safety_checks
            )
        
        # LIVE MODE - Execute real trade
        return await self._execute_live(
            symbol, direction, volume, stop_loss, take_profit,
            order_type, price, receipt_id, timestamp, safety_checks
        )
    
    async def _execute_paper(
        self,
        symbol: str,
        direction: str,
        volume: float,
        stop_loss: float,
        take_profit: Optional[float],
        receipt_id: str,
        timestamp: datetime,
        safety_checks: Dict[str, bool],
    ) -> ExecutionReceipt:
        """Execute on paper trading service."""
        
        result = await self.paper.open_position(
            symbol=symbol,
            direction=direction,
            volume=volume,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        
        return ExecutionReceipt(
            receipt_id=receipt_id,
            timestamp=timestamp,
            mode=TradingMode.PAPER,
            symbol=symbol,
            direction=direction,
            volume=volume,
            order_type="market",
            requested_price=result.get("entry_price", 0),
            executed_price=result.get("entry_price", 0),
            slippage_pips=0,
            success=result.get("success", False),
            ticket=result.get("ticket"),
            error=result.get("error"),
            safety_checks=safety_checks,
        )
    
    async def _execute_shadow(
        self,
        symbol: str,
        direction: str,
        volume: float,
        stop_loss: float,
        take_profit: Optional[float],
        receipt_id: str,
        timestamp: datetime,
        safety_checks: Dict[str, bool],
    ) -> ExecutionReceipt:
        """Shadow mode - log signal but execute on paper."""
        
        # Get current market price
        tick = await self.mt5.get_symbol_tick(symbol)
        current_price = tick.get("bid" if direction == "short" else "ask", 0) if tick else 0
        
        # Log that we WOULD have executed
        print(f"SHADOW MODE: Would execute {direction} {volume} {symbol} @ {current_price}")
        
        # Execute on paper for tracking
        paper_result = await self.paper.open_position(
            symbol=symbol,
            direction=direction,
            volume=volume,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        
        return ExecutionReceipt(
            receipt_id=receipt_id,
            timestamp=timestamp,
            mode=TradingMode.SHADOW,
            symbol=symbol,
            direction=direction,
            volume=volume,
            order_type="market",
            requested_price=current_price,
            executed_price=current_price,
            slippage_pips=0,
            success=True,
            ticket=paper_result.get("ticket"),
            safety_checks=safety_checks,
        )
    
    async def _execute_live(
        self,
        symbol: str,
        direction: str,
        volume: float,
        stop_loss: float,
        take_profit: Optional[float],
        order_type: str,
        price: Optional[float],
        receipt_id: str,
        timestamp: datetime,
        safety_checks: Dict[str, bool],
    ) -> ExecutionReceipt:
        """Execute real live trade on MT5."""
        
        # Get current price
        tick = await self.mt5.get_symbol_tick(symbol)
        if not tick:
            return ExecutionReceipt(
                receipt_id=receipt_id,
                timestamp=timestamp,
                mode=TradingMode.LIVE,
                symbol=symbol,
                direction=direction,
                volume=volume,
                order_type=order_type,
                requested_price=price or 0,
                executed_price=0,
                slippage_pips=0,
                success=False,
                error="Failed to get current price",
                safety_checks=safety_checks,
            )
        
        requested_price = price or (tick["ask"] if direction == "long" else tick["bid"])
        
        # Execute via MT5
        result = await self.mt5.place_order(
            symbol=symbol,
            direction=direction,
            volume=volume,
            order_type=order_type,
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        
        if not result.get("success"):
            return ExecutionReceipt(
                receipt_id=receipt_id,
                timestamp=timestamp,
                mode=TradingMode.LIVE,
                symbol=symbol,
                direction=direction,
                volume=volume,
                order_type=order_type,
                requested_price=requested_price,
                executed_price=0,
                slippage_pips=0,
                success=False,
                error=result.get("error", "Unknown execution error"),
                safety_checks=safety_checks,
            )
        
        # Calculate slippage
        executed_price = result.get("price", requested_price)
        pip_size = 0.01 if "JPY" in symbol else 0.0001
        slippage = abs(executed_price - requested_price) / pip_size
        
        receipt = ExecutionReceipt(
            receipt_id=receipt_id,
            timestamp=timestamp,
            mode=TradingMode.LIVE,
            symbol=symbol,
            direction=direction,
            volume=volume,
            order_type=order_type,
            requested_price=requested_price,
            executed_price=executed_price,
            slippage_pips=slippage,
            success=True,
            ticket=result.get("ticket"),
            safety_checks=safety_checks,
        )
        
        # Log execution
        self._execution_log.append(receipt)
        await self._persist_execution(receipt)
        
        return receipt
    
    async def _get_open_position_count(self) -> int:
        """Get current open position count."""
        if self.config.mode == TradingMode.LIVE:
            positions = await self.mt5.get_positions()
            return len(positions) if positions else 0
        else:
            return len(self.paper.positions)
    
    def _activate_kill_switch(self, reason: str):
        """Activate emergency kill switch."""
        self._kill_switch_active = True
        self._kill_switch_reason = reason
        print(f"⚠️ KILL SWITCH ACTIVATED: {reason}")
    
    def deactivate_kill_switch(self, authorized_by: str):
        """Deactivate kill switch (requires authorization)."""
        self._kill_switch_active = False
        self._kill_switch_reason = ""
        print(f"Kill switch deactivated by {authorized_by}")
    
    async def _persist_execution(self, receipt: ExecutionReceipt):
        """Persist execution receipt to database."""
        # TODO: Save to database
        pass
    
    async def close_position(self, ticket: int, volume: Optional[float] = None) -> ExecutionReceipt:
        """Close an open position."""
        
        receipt_id = f"CLOSE-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
        timestamp = datetime.utcnow()
        
        if self._kill_switch_active:
            return ExecutionReceipt(
                receipt_id=receipt_id,
                timestamp=timestamp,
                mode=self.config.mode,
                symbol="",
                direction="close",
                volume=volume or 0,
                order_type="market",
                requested_price=0,
                executed_price=0,
                slippage_pips=0,
                success=False,
                error=f"KILL SWITCH ACTIVE: {self._kill_switch_reason}",
                safety_checks={},
            )
        
        if self.config.mode == TradingMode.PAPER:
            result = await self.paper.close_position(ticket)
            return ExecutionReceipt(
                receipt_id=receipt_id,
                timestamp=timestamp,
                mode=TradingMode.PAPER,
                symbol=result.get("symbol", ""),
                direction="close",
                volume=result.get("volume", 0),
                order_type="market",
                requested_price=result.get("exit_price", 0),
                executed_price=result.get("exit_price", 0),
                slippage_pips=0,
                success=result.get("success", False),
                ticket=ticket,
                error=result.get("error"),
                safety_checks={},
            )
        
        # Live close
        result = await self.mt5.close_position(ticket, volume)
        
        return ExecutionReceipt(
            receipt_id=receipt_id,
            timestamp=timestamp,
            mode=self.config.mode,
            symbol=result.get("symbol", ""),
            direction="close",
            volume=result.get("volume", 0),
            order_type="market",
            requested_price=result.get("price", 0),
            executed_price=result.get("price", 0),
            slippage_pips=0,
            success=result.get("success", False),
            ticket=ticket,
            error=result.get("error"),
            safety_checks={},
        )
    
    async def emergency_close_all(self) -> List[ExecutionReceipt]:
        """Emergency close all positions."""
        
        print("⚠️ EMERGENCY CLOSE ALL TRIGGERED")
        
        receipts = []
        
        if self.config.mode == TradingMode.PAPER:
            positions = list(self.paper.positions.values())
        else:
            positions = await self.mt5.get_positions() or []
        
        for pos in positions:
            ticket = pos.get("ticket") or pos.ticket
            receipt = await self.close_position(ticket)
            receipts.append(receipt)
        
        self._activate_kill_switch("Emergency close all executed")
        
        return receipts
    
    def get_status(self) -> Dict[str, Any]:
        """Get current service status."""
        return {
            "mode": self.config.mode.value,
            "initialized": self._initialized,
            "kill_switch_active": self._kill_switch_active,
            "kill_switch_reason": self._kill_switch_reason,
            "daily_pnl": self._daily_pnl,
            "weekly_pnl": self._weekly_pnl,
            "execution_count": len(self._execution_log),
            "limits": {
                "max_daily_loss_pct": self.config.live_max_daily_loss_pct,
                "max_position_size": self.config.live_max_position_size,
                "max_positions": self.config.live_max_positions,
                "max_risk_per_trade": self.config.live_max_risk_per_trade,
            },
        }
    
    async def request_live_mode(self, requested_by: str, reason: str) -> Dict[str, Any]:
        """
        Request promotion to live mode.
        
        This is a formal request that must be manually approved.
        """
        
        # Check all gates
        gates = await self.check_promotion_gates()
        all_passed = all(g.passed for g in gates if g.gate != PromotionGate.MANUAL_APPROVAL)
        
        request = {
            "request_id": f"LIVE-REQ-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            "requested_by": requested_by,
            "requested_at": datetime.utcnow().isoformat(),
            "reason": reason,
            "gates": [
                {
                    "gate": g.gate.value,
                    "required": g.required,
                    "actual": g.actual,
                    "passed": g.passed,
                }
                for g in gates
            ],
            "all_gates_passed": all_passed,
            "status": "pending_approval" if all_passed else "gates_not_met",
        }
        
        # Persist request
        if self.redis:
            await self.redis.set(
                f"live_request:{request['request_id']}",
                json.dumps(request),
                ex=86400 * 7,  # 7 days
            )
        
        return request
    
    async def approve_live_mode(self, request_id: str, approved_by: str) -> Dict[str, Any]:
        """
        Approve a live mode request.
        
        This is the final authorization step.
        """
        
        # Load request
        if self.redis:
            request_data = await self.redis.get(f"live_request:{request_id}")
            if not request_data:
                return {"error": "Request not found"}
            request = json.loads(request_data)
        else:
            return {"error": "Redis not available"}
        
        if request["status"] != "pending_approval":
            return {"error": f"Request status is {request['status']}, not pending_approval"}
        
        # Set approval
        self.config.manual_approval_by = approved_by
        self.config.manual_approval_at = datetime.utcnow()
        self.config.mode = TradingMode.LIVE
        
        return {
            "success": True,
            "message": f"Live trading approved by {approved_by}",
            "mode": self.config.mode.value,
            "approved_at": self.config.manual_approval_at.isoformat(),
        }
