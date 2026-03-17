"""
Paper Trading Service
=====================
Simulates trade execution without connecting to a real broker.

From 07_EXECUTION_AND_MT5.txt:
- Maintains virtual equity
- Tracks virtual open positions
- Simulates fills with configurable slippage
- All the same risk checks as live mode
"""
import structlog
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from dataclasses import dataclass, field
from uuid import uuid4
import random

logger = structlog.get_logger()


@dataclass
class PaperPosition:
    """A simulated position."""
    ticket: int
    symbol: str
    direction: str  # "long" or "short"
    volume: float
    entry_price: float
    entry_time: datetime
    stop_loss: float
    take_profit: Optional[float] = None
    
    # Current state
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pips: float = 0.0
    
    # Tracking
    mae_pips: float = 0.0  # Maximum Adverse Excursion
    mfe_pips: float = 0.0  # Maximum Favorable Excursion
    
    # Metadata
    plan_id: Optional[str] = None
    strategy: str = ""
    comment: str = ""
    
    def update_price(self, bid: float, ask: float, pip_value: float = 0.0001) -> None:
        """Update position with current prices."""
        if self.direction == "long":
            self.current_price = bid
            price_diff = bid - self.entry_price
        else:
            self.current_price = ask
            price_diff = self.entry_price - ask
        
        self.unrealized_pips = price_diff / pip_value
        self.unrealized_pnl = price_diff * self.volume * 100000  # Simplified
        
        # Track MAE/MFE
        if self.unrealized_pips < 0:
            self.mae_pips = min(self.mae_pips, self.unrealized_pips)
        else:
            self.mfe_pips = max(self.mfe_pips, self.unrealized_pips)


@dataclass
class PaperOrder:
    """A pending order."""
    order_id: int
    symbol: str
    order_type: str  # "limit", "stop"
    direction: str
    volume: float
    price: float
    stop_loss: float
    take_profit: Optional[float] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    plan_id: Optional[str] = None


@dataclass
class PaperFill:
    """Record of a fill."""
    fill_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    symbol: str = ""
    direction: str = ""
    volume: float = 0.0
    requested_price: float = 0.0
    fill_price: float = 0.0
    slippage_pips: float = 0.0
    action: str = ""  # "open", "close", "partial_close"
    ticket: Optional[int] = None
    pnl: float = 0.0


@dataclass
class PaperAccount:
    """Virtual account state."""
    balance: float = 10000.0
    equity: float = 10000.0
    margin_used: float = 0.0
    free_margin: float = 10000.0
    unrealized_pnl: float = 0.0
    realized_pnl_today: float = 0.0
    peak_equity: float = 10000.0
    current_drawdown_pct: float = 0.0


class PaperTradingService:
    """
    Paper trading simulation service.
    
    Simulates all aspects of real trading without actual broker connection.
    """
    
    def __init__(
        self,
        starting_balance: float = 10000.0,
        max_slippage_pips: float = 1.0,
        default_spread_pips: float = 1.5,
        leverage: int = 100,
    ):
        self.starting_balance = starting_balance
        self.max_slippage_pips = max_slippage_pips
        self.default_spread_pips = default_spread_pips
        self.leverage = leverage
        
        # State
        self.account = PaperAccount(
            balance=starting_balance,
            equity=starting_balance,
            free_margin=starting_balance,
            peak_equity=starting_balance,
        )
        
        self.positions: dict[int, PaperPosition] = {}
        self.pending_orders: dict[int, PaperOrder] = {}
        self.fill_history: list[PaperFill] = []
        self.equity_history: list[tuple[datetime, float]] = []
        
        # Counters
        self._next_ticket = 1000
        self._next_order_id = 2000
        
        self._logger = logger.bind(service="paper_trading")
    
    def place_market_order(
        self,
        symbol: str,
        direction: str,
        volume: float,
        stop_loss: float,
        take_profit: Optional[float] = None,
        current_price: float = 0.0,
        plan_id: Optional[str] = None,
        strategy: str = "",
    ) -> tuple[bool, Optional[PaperFill], str]:
        """
        Place a market order.
        
        Returns:
            Tuple of (success, fill, error_message)
        """
        # Validate
        if volume <= 0:
            return False, None, "Invalid volume"
        
        if stop_loss <= 0:
            return False, None, "Stop loss is required"
        
        if current_price <= 0:
            return False, None, "Current price required"
        
        # Check margin
        required_margin = self._calculate_required_margin(volume)
        if required_margin > self.account.free_margin:
            return False, None, f"Insufficient margin: need {required_margin:.2f}, have {self.account.free_margin:.2f}"
        
        # Simulate fill with slippage
        slippage = random.uniform(0, self.max_slippage_pips) * 0.0001
        
        if direction == "long":
            # Buy at ask + slippage
            fill_price = current_price + self.default_spread_pips * 0.0001 / 2 + slippage
        else:
            # Sell at bid - slippage
            fill_price = current_price - self.default_spread_pips * 0.0001 / 2 - slippage
        
        slippage_pips = abs(fill_price - current_price) / 0.0001
        
        # Create position
        ticket = self._next_ticket
        self._next_ticket += 1
        
        position = PaperPosition(
            ticket=ticket,
            symbol=symbol,
            direction=direction,
            volume=volume,
            entry_price=fill_price,
            entry_time=datetime.now(timezone.utc),
            stop_loss=stop_loss,
            take_profit=take_profit,
            current_price=fill_price,
            plan_id=plan_id,
            strategy=strategy,
        )
        
        self.positions[ticket] = position
        
        # Update account
        self.account.margin_used += required_margin
        self.account.free_margin -= required_margin
        
        # Create fill record
        fill = PaperFill(
            symbol=symbol,
            direction=direction,
            volume=volume,
            requested_price=current_price,
            fill_price=fill_price,
            slippage_pips=slippage_pips,
            action="open",
            ticket=ticket,
        )
        self.fill_history.append(fill)
        
        self._logger.info(
            "Paper order filled",
            ticket=ticket,
            symbol=symbol,
            direction=direction,
            volume=volume,
            fill_price=fill_price,
            slippage_pips=slippage_pips,
        )
        
        return True, fill, ""
    
    def place_pending_order(
        self,
        symbol: str,
        order_type: str,
        direction: str,
        volume: float,
        price: float,
        stop_loss: float,
        take_profit: Optional[float] = None,
        plan_id: Optional[str] = None,
    ) -> tuple[bool, int, str]:
        """
        Place a pending order (limit or stop).
        
        Returns:
            Tuple of (success, order_id, error_message)
        """
        if order_type not in ["limit", "stop"]:
            return False, 0, "Invalid order type"
        
        order_id = self._next_order_id
        self._next_order_id += 1
        
        order = PaperOrder(
            order_id=order_id,
            symbol=symbol,
            order_type=order_type,
            direction=direction,
            volume=volume,
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            plan_id=plan_id,
        )
        
        self.pending_orders[order_id] = order
        
        self._logger.info(
            "Pending order placed",
            order_id=order_id,
            symbol=symbol,
            order_type=order_type,
            direction=direction,
            price=price,
        )
        
        return True, order_id, ""
    
    def close_position(
        self,
        ticket: int,
        current_price: float,
        volume: Optional[float] = None,
    ) -> tuple[bool, Optional[PaperFill], str]:
        """
        Close a position (full or partial).
        
        Returns:
            Tuple of (success, fill, error_message)
        """
        if ticket not in self.positions:
            return False, None, f"Position {ticket} not found"
        
        position = self.positions[ticket]
        close_volume = volume if volume else position.volume
        
        if close_volume > position.volume:
            return False, None, "Close volume exceeds position volume"
        
        # Simulate fill
        slippage = random.uniform(0, self.max_slippage_pips) * 0.0001
        
        if position.direction == "long":
            # Sell at bid - slippage
            fill_price = current_price - self.default_spread_pips * 0.0001 / 2 - slippage
            pnl = (fill_price - position.entry_price) * close_volume * 100000
        else:
            # Buy at ask + slippage
            fill_price = current_price + self.default_spread_pips * 0.0001 / 2 + slippage
            pnl = (position.entry_price - fill_price) * close_volume * 100000
        
        slippage_pips = slippage / 0.0001
        
        # Update account
        self.account.balance += pnl
        self.account.realized_pnl_today += pnl
        
        margin_released = self._calculate_required_margin(close_volume)
        self.account.margin_used -= margin_released
        self.account.free_margin += margin_released + pnl
        
        # Partial or full close
        if close_volume >= position.volume:
            # Full close
            del self.positions[ticket]
            action = "close"
        else:
            # Partial close
            position.volume -= close_volume
            action = "partial_close"
        
        # Create fill record
        fill = PaperFill(
            symbol=position.symbol,
            direction="short" if position.direction == "long" else "long",
            volume=close_volume,
            requested_price=current_price,
            fill_price=fill_price,
            slippage_pips=slippage_pips,
            action=action,
            ticket=ticket,
            pnl=pnl,
        )
        self.fill_history.append(fill)
        
        self._logger.info(
            "Paper position closed",
            ticket=ticket,
            action=action,
            volume=close_volume,
            fill_price=fill_price,
            pnl=pnl,
        )
        
        return True, fill, ""
    
    def update_prices(self, prices: dict[str, tuple[float, float]]) -> list[int]:
        """
        Update all positions with current prices.
        
        Args:
            prices: Dict of symbol -> (bid, ask)
            
        Returns:
            List of tickets that hit SL or TP
        """
        closed_tickets = []
        total_unrealized = 0.0
        
        for ticket, position in list(self.positions.items()):
            if position.symbol not in prices:
                continue
            
            bid, ask = prices[position.symbol]
            position.update_price(bid, ask)
            total_unrealized += position.unrealized_pnl
            
            # Check stop loss
            if position.direction == "long" and bid <= position.stop_loss:
                self.close_position(ticket, bid)
                closed_tickets.append(ticket)
                self._logger.info("Stop loss hit", ticket=ticket, price=bid)
            elif position.direction == "short" and ask >= position.stop_loss:
                self.close_position(ticket, ask)
                closed_tickets.append(ticket)
                self._logger.info("Stop loss hit", ticket=ticket, price=ask)
            
            # Check take profit
            elif position.take_profit:
                if position.direction == "long" and bid >= position.take_profit:
                    self.close_position(ticket, bid)
                    closed_tickets.append(ticket)
                    self._logger.info("Take profit hit", ticket=ticket, price=bid)
                elif position.direction == "short" and ask <= position.take_profit:
                    self.close_position(ticket, ask)
                    closed_tickets.append(ticket)
                    self._logger.info("Take profit hit", ticket=ticket, price=ask)
        
        # Update account equity
        self.account.unrealized_pnl = total_unrealized
        self.account.equity = self.account.balance + total_unrealized
        self.account.free_margin = self.account.equity - self.account.margin_used
        
        # Track peak and drawdown
        if self.account.equity > self.account.peak_equity:
            self.account.peak_equity = self.account.equity
        
        if self.account.peak_equity > 0:
            self.account.current_drawdown_pct = (
                (self.account.peak_equity - self.account.equity) / self.account.peak_equity * 100
            )
        
        # Record equity point
        self.equity_history.append((datetime.now(timezone.utc), self.account.equity))
        
        # Check pending orders
        for order_id, order in list(self.pending_orders.items()):
            if order.symbol not in prices:
                continue
            
            bid, ask = prices[order.symbol]
            triggered = False
            
            if order.order_type == "limit":
                if order.direction == "long" and ask <= order.price:
                    triggered = True
                elif order.direction == "short" and bid >= order.price:
                    triggered = True
            elif order.order_type == "stop":
                if order.direction == "long" and ask >= order.price:
                    triggered = True
                elif order.direction == "short" and bid <= order.price:
                    triggered = True
            
            if triggered:
                # Convert to market order
                current = ask if order.direction == "long" else bid
                success, _, _ = self.place_market_order(
                    symbol=order.symbol,
                    direction=order.direction,
                    volume=order.volume,
                    stop_loss=order.stop_loss,
                    take_profit=order.take_profit,
                    current_price=current,
                    plan_id=order.plan_id,
                )
                if success:
                    del self.pending_orders[order_id]
        
        return closed_tickets
    
    def modify_position(
        self,
        ticket: int,
        new_stop_loss: Optional[float] = None,
        new_take_profit: Optional[float] = None,
    ) -> tuple[bool, str]:
        """Modify position SL/TP."""
        if ticket not in self.positions:
            return False, f"Position {ticket} not found"
        
        position = self.positions[ticket]
        
        if new_stop_loss:
            # Validate: can only move stop in favorable direction or to breakeven
            if position.direction == "long" and new_stop_loss < position.stop_loss:
                return False, "Cannot move stop loss away from entry"
            if position.direction == "short" and new_stop_loss > position.stop_loss:
                return False, "Cannot move stop loss away from entry"
            position.stop_loss = new_stop_loss
        
        if new_take_profit:
            position.take_profit = new_take_profit
        
        return True, ""
    
    def _calculate_required_margin(self, volume: float) -> float:
        """Calculate required margin for position."""
        # Simplified: assuming $100,000 per lot and leverage
        notional = volume * 100000
        return notional / self.leverage
    
    def get_account_state(self) -> dict:
        """Get current account state."""
        return {
            "balance": self.account.balance,
            "equity": self.account.equity,
            "margin_used": self.account.margin_used,
            "free_margin": self.account.free_margin,
            "unrealized_pnl": self.account.unrealized_pnl,
            "realized_pnl_today": self.account.realized_pnl_today,
            "peak_equity": self.account.peak_equity,
            "current_drawdown_pct": self.account.current_drawdown_pct,
            "open_positions": len(self.positions),
            "pending_orders": len(self.pending_orders),
        }
    
    def get_open_positions(self) -> list[dict]:
        """Get all open positions."""
        return [
            {
                "ticket": p.ticket,
                "symbol": p.symbol,
                "direction": p.direction,
                "volume": p.volume,
                "entry_price": p.entry_price,
                "entry_time": p.entry_time.isoformat(),
                "stop_loss": p.stop_loss,
                "take_profit": p.take_profit,
                "current_price": p.current_price,
                "unrealized_pnl": p.unrealized_pnl,
                "unrealized_pips": p.unrealized_pips,
                "mae_pips": p.mae_pips,
                "mfe_pips": p.mfe_pips,
                "strategy": p.strategy,
            }
            for p in self.positions.values()
        ]
    
    def reset(self) -> None:
        """Reset to initial state."""
        self.account = PaperAccount(
            balance=self.starting_balance,
            equity=self.starting_balance,
            free_margin=self.starting_balance,
            peak_equity=self.starting_balance,
        )
        self.positions.clear()
        self.pending_orders.clear()
        self.fill_history.clear()
        self.equity_history.clear()
        self._next_ticket = 1000
        self._next_order_id = 2000
