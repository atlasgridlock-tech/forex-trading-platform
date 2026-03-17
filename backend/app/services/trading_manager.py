"""
Trading Service Manager

Provides a singleton trading service instance that's shared across the application.
This ensures consistent state management for paper trading positions.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from app.services.paper_trading_service import PaperTradingService, PaperFill

logger = logging.getLogger(__name__)

# Global paper trading service instance
_paper_service: Optional[PaperTradingService] = None


def get_paper_service() -> PaperTradingService:
    """Get or create the global paper trading service."""
    global _paper_service
    if _paper_service is None:
        _paper_service = PaperTradingService(starting_balance=10000.0)
        logger.info("Paper trading service initialized with $10,000 balance")
    return _paper_service


def reset_paper_service() -> PaperTradingService:
    """Reset the paper trading service to initial state."""
    global _paper_service
    _paper_service = PaperTradingService(starting_balance=10000.0)
    logger.info("Paper trading service reset")
    return _paper_service


@dataclass
class TradeExecutionResult:
    """Result of a trade execution."""
    success: bool
    receipt_id: str
    mode: str = "paper"
    ticket: Optional[int] = None
    symbol: str = ""
    direction: str = ""
    volume: float = 0.0
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: Optional[float] = None
    slippage_pips: float = 0.0
    error: Optional[str] = None
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


def execute_market_trade(
    symbol: str,
    direction: str,
    volume: float,
    stop_loss: float,
    take_profit: Optional[float] = None,
    entry_price: Optional[float] = None,
) -> TradeExecutionResult:
    """
    Execute a market trade on the paper trading service.
    
    Args:
        symbol: Trading symbol (e.g., EURUSD)
        direction: 'long' or 'short'
        volume: Position size in lots
        stop_loss: Stop loss price (REQUIRED)
        take_profit: Take profit price (optional)
        entry_price: Entry price (if None, will use default)
    
    Returns:
        TradeExecutionResult with execution details
    """
    receipt_id = f"EXEC-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')[:18]}"
    
    # Validate inputs
    if not symbol:
        return TradeExecutionResult(
            success=False,
            receipt_id=receipt_id,
            error="Symbol is required"
        )
    
    if direction not in ("long", "short"):
        return TradeExecutionResult(
            success=False,
            receipt_id=receipt_id,
            error="Direction must be 'long' or 'short'"
        )
    
    if volume <= 0:
        return TradeExecutionResult(
            success=False,
            receipt_id=receipt_id,
            error="Volume must be positive"
        )
    
    if not stop_loss or stop_loss <= 0:
        return TradeExecutionResult(
            success=False,
            receipt_id=receipt_id,
            error="Stop loss is REQUIRED and must be positive"
        )
    
    # Get default price if not provided
    if entry_price is None:
        # Use a simulated price based on symbol
        # In production, this would come from market data
        base_prices = {
            "EURUSD": 1.0850,
            "GBPUSD": 1.2650,
            "USDJPY": 149.50,
            "GBPJPY": 189.20,
            "USDCHF": 0.8850,
            "USDCAD": 1.3550,
            "EURAUD": 1.6550,
            "AUDNZD": 1.0950,
            "AUDUSD": 0.6550,
        }
        entry_price = base_prices.get(symbol, 1.0000)
    
    # Validate stop loss relative to entry and direction
    if direction == "long":
        if stop_loss >= entry_price:
            return TradeExecutionResult(
                success=False,
                receipt_id=receipt_id,
                error=f"For LONG positions, stop loss ({stop_loss}) must be BELOW entry price ({entry_price})"
            )
    else:  # short
        if stop_loss <= entry_price:
            return TradeExecutionResult(
                success=False,
                receipt_id=receipt_id,
                error=f"For SHORT positions, stop loss ({stop_loss}) must be ABOVE entry price ({entry_price})"
            )
    
    # Validate take profit if provided
    warnings = []
    if take_profit:
        if direction == "long":
            if take_profit <= entry_price:
                return TradeExecutionResult(
                    success=False,
                    receipt_id=receipt_id,
                    error=f"For LONG positions, take profit ({take_profit}) must be ABOVE entry price ({entry_price})"
                )
        else:  # short
            if take_profit >= entry_price:
                return TradeExecutionResult(
                    success=False,
                    receipt_id=receipt_id,
                    error=f"For SHORT positions, take profit ({take_profit}) must be BELOW entry price ({entry_price})"
                )
    
    # Get the paper trading service
    paper_service = get_paper_service()
    
    # Execute the trade
    try:
        success, fill, error = paper_service.place_market_order(
            symbol=symbol,
            direction=direction,
            volume=volume,
            stop_loss=stop_loss,
            take_profit=take_profit,
            current_price=entry_price,
            plan_id=receipt_id,
            strategy="manual",
        )
        
        if success and fill:
            logger.info(f"Trade executed: {direction} {volume} {symbol} @ {fill.fill_price}, ticket={fill.ticket}")
            return TradeExecutionResult(
                success=True,
                receipt_id=receipt_id,
                mode="paper",
                ticket=fill.ticket,
                symbol=symbol,
                direction=direction,
                volume=fill.volume,
                entry_price=fill.fill_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                slippage_pips=fill.slippage_pips,
                warnings=warnings,
            )
        else:
            return TradeExecutionResult(
                success=False,
                receipt_id=receipt_id,
                error=error or "Unknown execution error"
            )
            
    except Exception as e:
        logger.error(f"Trade execution error: {e}")
        return TradeExecutionResult(
            success=False,
            receipt_id=receipt_id,
            error=str(e)
        )


def close_position(
    ticket: int,
    current_price: Optional[float] = None,
    volume: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Close a position by ticket number.
    
    Args:
        ticket: Position ticket number
        current_price: Current market price (optional, will use position's current price)
        volume: Volume to close (optional, closes full position if not specified)
    
    Returns:
        Dict with close result
    """
    paper_service = get_paper_service()
    
    # Get the position first to get its current price
    positions = paper_service.get_open_positions()
    position = None
    for pos in positions:
        if pos["ticket"] == ticket:
            position = pos
            break
    
    if not position:
        return {
            "success": False,
            "error": f"Position {ticket} not found"
        }
    
    # Use current price from position if not provided
    if current_price is None:
        current_price = position.get("current_price") or position.get("entry_price")
    
    success, fill, error = paper_service.close_position(
        ticket=ticket,
        current_price=current_price,
        volume=volume,
    )
    
    if success and fill:
        logger.info(f"Position {ticket} closed @ {fill.fill_price}, PnL: ${fill.pnl:.2f}")
        return {
            "success": True,
            "ticket": ticket,
            "symbol": position["symbol"],
            "direction": position["direction"],
            "volume": fill.volume,
            "exit_price": fill.fill_price,
            "pnl": fill.pnl,
        }
    else:
        return {
            "success": False,
            "ticket": ticket,
            "error": error or "Unknown close error"
        }


def get_open_positions() -> List[Dict[str, Any]]:
    """Get all open positions."""
    paper_service = get_paper_service()
    return paper_service.get_open_positions()


def get_account_state() -> Dict[str, Any]:
    """Get current account state."""
    paper_service = get_paper_service()
    return paper_service.get_account_state()


def modify_position(
    ticket: int,
    new_stop_loss: Optional[float] = None,
    new_take_profit: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Modify a position's stop loss or take profit.
    
    Args:
        ticket: Position ticket number
        new_stop_loss: New stop loss price
        new_take_profit: New take profit price
    
    Returns:
        Dict with modification result
    """
    paper_service = get_paper_service()
    
    success, error = paper_service.modify_position(
        ticket=ticket,
        new_stop_loss=new_stop_loss,
        new_take_profit=new_take_profit,
    )
    
    if success:
        return {
            "success": True,
            "ticket": ticket,
            "message": "Position modified successfully"
        }
    else:
        return {
            "success": False,
            "ticket": ticket,
            "error": error or "Unknown modification error"
        }


def update_market_prices(prices: Dict[str, tuple]) -> List[int]:
    """
    Update all positions with current market prices and check for SL/TP hits.
    
    Args:
        prices: Dict of symbol -> (bid, ask) tuples
    
    Returns:
        List of tickets that were closed due to SL/TP hit
    """
    paper_service = get_paper_service()
    return paper_service.update_prices(prices)
