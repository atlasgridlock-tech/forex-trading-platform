"""
Position Lifecycle Manager
Handles partial TPs, trailing stops, and break-even logic for paper and live modes.
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum


class LifecycleState(str, Enum):
    OPEN = "open"
    TP1_HIT = "tp1_hit"
    TP2_HIT = "tp2_hit"
    TP3_HIT = "tp3_hit"
    BREAKEVEN = "breakeven"
    TRAILING = "trailing"
    CLOSED = "closed"


@dataclass
class PositionLifecycle:
    """Tracks the lifecycle state of a position."""
    order_id: str
    symbol: str
    direction: str  # "long" or "short"
    entry_price: float
    original_lot_size: float
    current_lot_size: float
    stop_loss: float
    original_sl: float
    
    # Take profit levels (optional)
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    take_profit_3: Optional[float] = None
    
    # Partial close percentages at each TP
    tp1_close_pct: float = 33.0  # Close 33% at TP1
    tp2_close_pct: float = 50.0  # Close 50% of remaining at TP2
    tp3_close_pct: float = 100.0  # Close all at TP3
    
    # Trailing stop config
    trailing_enabled: bool = False
    trailing_trigger_pips: float = 20.0  # Start trailing after X pips profit
    trailing_distance_pips: float = 15.0  # Keep SL X pips behind price
    
    # Break-even config
    breakeven_enabled: bool = True
    breakeven_trigger_pips: float = 10.0  # Move SL to BE after X pips
    breakeven_offset_pips: float = 1.0  # Add small buffer to BE
    
    # State tracking
    state: LifecycleState = LifecycleState.OPEN
    tp1_hit_at: Optional[datetime] = None
    tp2_hit_at: Optional[datetime] = None
    tp3_hit_at: Optional[datetime] = None
    breakeven_triggered: bool = False
    trailing_active: bool = False
    highest_favorable_price: float = 0.0
    
    # Realized P/L tracking
    realized_pnl: float = 0.0
    partial_closes: List[dict] = field(default_factory=list)
    
    def __post_init__(self):
        """Initialize highest favorable price."""
        self.highest_favorable_price = self.entry_price


class LifecycleManager:
    """
    Manages position lifecycles including partial TPs, trailing stops, and break-even.
    Works in both paper and live modes.
    """
    
    def __init__(self, pip_value_func=None):
        self.positions: Dict[str, PositionLifecycle] = {}
        self.closed_positions: List[PositionLifecycle] = []
        self.pip_value_func = pip_value_func or self._default_pip_value
    
    def _default_pip_value(self, symbol: str) -> float:
        """Get pip value for symbol."""
        return 0.01 if "JPY" in symbol.upper() else 0.0001
    
    def create_lifecycle(
        self,
        order_id: str,
        symbol: str,
        direction: str,
        entry_price: float,
        lot_size: float,
        stop_loss: float,
        take_profit_1: float = None,
        take_profit_2: float = None,
        take_profit_3: float = None,
        trailing_trigger_pips: float = None,
        trailing_distance_pips: float = None,
    ) -> PositionLifecycle:
        """Create a new position lifecycle tracker."""
        
        lifecycle = PositionLifecycle(
            order_id=order_id,
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            original_lot_size=lot_size,
            current_lot_size=lot_size,
            stop_loss=stop_loss,
            original_sl=stop_loss,
            take_profit_1=take_profit_1,
            take_profit_2=take_profit_2,
            take_profit_3=take_profit_3,
        )
        
        # Enable trailing if configured
        if trailing_trigger_pips is not None:
            lifecycle.trailing_enabled = True
            lifecycle.trailing_trigger_pips = trailing_trigger_pips
            if trailing_distance_pips:
                lifecycle.trailing_distance_pips = trailing_distance_pips
        
        self.positions[order_id] = lifecycle
        return lifecycle
    
    def update_price(self, order_id: str, current_price: float) -> dict:
        """
        Update lifecycle based on current price.
        Returns actions to take (partial close, modify SL, etc.)
        """
        if order_id not in self.positions:
            return {"error": "Position not found"}
        
        lifecycle = self.positions[order_id]
        actions = []
        pip_value = self.pip_value_func(lifecycle.symbol)
        
        # Calculate current P/L in pips
        if lifecycle.direction == "long":
            pips_profit = (current_price - lifecycle.entry_price) / pip_value
            favorable_direction = current_price > lifecycle.highest_favorable_price
        else:
            pips_profit = (lifecycle.entry_price - current_price) / pip_value
            favorable_direction = current_price < lifecycle.highest_favorable_price
        
        # Update highest favorable price
        if favorable_direction:
            lifecycle.highest_favorable_price = current_price
        
        # Check stop loss hit
        if self._is_sl_hit(lifecycle, current_price):
            actions.append({
                "action": "CLOSE",
                "reason": "stop_loss_hit",
                "price": current_price,
                "lot_size": lifecycle.current_lot_size,
            })
            lifecycle.state = LifecycleState.CLOSED
            self._move_to_closed(order_id)
            return {"actions": actions, "state": lifecycle.state.value}
        
        # Check TP1
        if (lifecycle.state in [LifecycleState.OPEN, LifecycleState.BREAKEVEN, LifecycleState.TRAILING] and 
            lifecycle.take_profit_1 and 
            not lifecycle.tp1_hit_at and  # Haven't hit TP1 yet
            self._is_tp_hit(lifecycle, current_price, lifecycle.take_profit_1)):
            
            close_lots = lifecycle.current_lot_size * (lifecycle.tp1_close_pct / 100)
            actions.append({
                "action": "PARTIAL_CLOSE",
                "reason": "tp1_hit",
                "price": current_price,
                "lot_size": round(close_lots, 2),
                "close_percent": lifecycle.tp1_close_pct,
            })
            lifecycle.current_lot_size -= close_lots
            lifecycle.state = LifecycleState.TP1_HIT
            lifecycle.tp1_hit_at = datetime.utcnow()
            lifecycle.partial_closes.append({
                "level": "TP1",
                "price": current_price,
                "lots": close_lots,
                "time": lifecycle.tp1_hit_at.isoformat(),
            })
        
        # Check TP2
        if (lifecycle.tp1_hit_at and  # TP1 was hit
            not lifecycle.tp2_hit_at and  # TP2 not hit yet
            lifecycle.take_profit_2 and 
            self._is_tp_hit(lifecycle, current_price, lifecycle.take_profit_2)):
            
            close_lots = lifecycle.current_lot_size * (lifecycle.tp2_close_pct / 100)
            actions.append({
                "action": "PARTIAL_CLOSE",
                "reason": "tp2_hit",
                "price": current_price,
                "lot_size": round(close_lots, 2),
                "close_percent": lifecycle.tp2_close_pct,
            })
            lifecycle.current_lot_size -= close_lots
            lifecycle.state = LifecycleState.TP2_HIT
            lifecycle.tp2_hit_at = datetime.utcnow()
            lifecycle.partial_closes.append({
                "level": "TP2",
                "price": current_price,
                "lots": close_lots,
                "time": lifecycle.tp2_hit_at.isoformat(),
            })
        
        # Check TP3 (final)
        if (lifecycle.tp1_hit_at and  # At least TP1 was hit
            not lifecycle.tp3_hit_at and  # TP3 not hit yet
            lifecycle.take_profit_3 and 
            self._is_tp_hit(lifecycle, current_price, lifecycle.take_profit_3)):
            
            actions.append({
                "action": "CLOSE",
                "reason": "tp3_hit",
                "price": current_price,
                "lot_size": lifecycle.current_lot_size,
            })
            lifecycle.state = LifecycleState.TP3_HIT
            lifecycle.tp3_hit_at = datetime.utcnow()
            self._move_to_closed(order_id)
        
        # Check break-even trigger
        if (lifecycle.breakeven_enabled and 
            not lifecycle.breakeven_triggered and 
            pips_profit >= lifecycle.breakeven_trigger_pips):
            
            # Calculate break-even SL with offset
            if lifecycle.direction == "long":
                new_sl = lifecycle.entry_price + (lifecycle.breakeven_offset_pips * pip_value)
            else:
                new_sl = lifecycle.entry_price - (lifecycle.breakeven_offset_pips * pip_value)
            
            # Only move SL if it improves the position
            if self._is_better_sl(lifecycle, new_sl):
                actions.append({
                    "action": "MODIFY_SL",
                    "reason": "breakeven",
                    "new_sl": round(new_sl, 5 if "JPY" not in lifecycle.symbol else 3),
                    "old_sl": lifecycle.stop_loss,
                })
                lifecycle.stop_loss = new_sl
                lifecycle.breakeven_triggered = True
                if lifecycle.state == LifecycleState.OPEN:
                    lifecycle.state = LifecycleState.BREAKEVEN
        
        # Check trailing stop
        if (lifecycle.trailing_enabled and 
            pips_profit >= lifecycle.trailing_trigger_pips):
            
            # Calculate trailing SL
            if lifecycle.direction == "long":
                trailing_sl = lifecycle.highest_favorable_price - (lifecycle.trailing_distance_pips * pip_value)
            else:
                trailing_sl = lifecycle.highest_favorable_price + (lifecycle.trailing_distance_pips * pip_value)
            
            # Only move SL if it improves
            if self._is_better_sl(lifecycle, trailing_sl):
                actions.append({
                    "action": "MODIFY_SL",
                    "reason": "trailing",
                    "new_sl": round(trailing_sl, 5 if "JPY" not in lifecycle.symbol else 3),
                    "old_sl": lifecycle.stop_loss,
                })
                lifecycle.stop_loss = trailing_sl
                lifecycle.trailing_active = True
                if lifecycle.state not in [LifecycleState.TP1_HIT, LifecycleState.TP2_HIT]:
                    lifecycle.state = LifecycleState.TRAILING
        
        return {
            "actions": actions,
            "state": lifecycle.state.value,
            "pips_profit": round(pips_profit, 1),
            "current_lot_size": round(lifecycle.current_lot_size, 2),
            "current_sl": lifecycle.stop_loss,
            "trailing_active": lifecycle.trailing_active,
            "breakeven_triggered": lifecycle.breakeven_triggered,
        }
    
    def _is_sl_hit(self, lifecycle: PositionLifecycle, price: float) -> bool:
        """Check if stop loss is hit."""
        if lifecycle.direction == "long":
            return price <= lifecycle.stop_loss
        else:
            return price >= lifecycle.stop_loss
    
    def _is_tp_hit(self, lifecycle: PositionLifecycle, price: float, tp_level: float) -> bool:
        """Check if take profit level is hit."""
        if lifecycle.direction == "long":
            return price >= tp_level
        else:
            return price <= tp_level
    
    def _is_better_sl(self, lifecycle: PositionLifecycle, new_sl: float) -> bool:
        """Check if new SL is better (more protective) than current."""
        if lifecycle.direction == "long":
            return new_sl > lifecycle.stop_loss
        else:
            return new_sl < lifecycle.stop_loss
    
    def _move_to_closed(self, order_id: str):
        """Move position from active to closed."""
        if order_id in self.positions:
            self.closed_positions.append(self.positions[order_id])
            del self.positions[order_id]
    
    def get_position(self, order_id: str) -> Optional[PositionLifecycle]:
        """Get a position by order ID."""
        return self.positions.get(order_id)
    
    def get_all_positions(self) -> List[dict]:
        """Get all active positions as dicts."""
        return [
            {
                "order_id": p.order_id,
                "symbol": p.symbol,
                "direction": p.direction,
                "entry_price": p.entry_price,
                "current_lot_size": p.current_lot_size,
                "stop_loss": p.stop_loss,
                "state": p.state.value,
                "trailing_active": p.trailing_active,
                "breakeven_triggered": p.breakeven_triggered,
                "partial_closes": p.partial_closes,
            }
            for p in self.positions.values()
        ]
    
    def close_position(self, order_id: str, close_price: float, reason: str = "manual") -> dict:
        """Manually close a position."""
        if order_id not in self.positions:
            return {"error": "Position not found"}
        
        lifecycle = self.positions[order_id]
        lifecycle.state = LifecycleState.CLOSED
        
        result = {
            "order_id": order_id,
            "close_price": close_price,
            "reason": reason,
            "lot_size": lifecycle.current_lot_size,
            "partial_closes": lifecycle.partial_closes,
        }
        
        self._move_to_closed(order_id)
        return result


# Global lifecycle manager instance
lifecycle_manager = LifecycleManager()
