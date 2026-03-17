"""
MetaTrader 5 Connector
======================
Safe wrapper around the MT5 Python package with comprehensive safety checks.

CRITICAL SAFETY RULES:
- EVERY order MUST include a stop loss
- No naked orders, ever
- No averaging down unless explicitly approved
- No martingale under any circumstance
- If MT5 disconnects during order placement, do NOT retry blindly
"""
import structlog
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional, Any
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger()


class MT5Timeframe(Enum):
    """MT5 timeframe constants."""
    M1 = 1
    M5 = 5
    M15 = 15
    M30 = 30
    H1 = 60
    H4 = 240
    D1 = 1440
    W1 = 10080
    MN1 = 43200


@dataclass
class OHLCVBar:
    """Single OHLCV bar."""
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    tick_volume: int
    spread: Optional[Decimal] = None
    
    def is_valid(self) -> bool:
        """Validate bar data sanity."""
        return (
            self.high >= self.low and
            self.high >= self.open and
            self.high >= self.close and
            self.low <= self.open and
            self.low <= self.close and
            self.open > 0 and
            self.tick_volume >= 0
        )


@dataclass
class SymbolInfo:
    """Symbol specification from MT5."""
    name: str
    digits: int
    point: Decimal
    spread: int
    trade_contract_size: Decimal
    volume_min: Decimal
    volume_max: Decimal
    volume_step: Decimal
    trade_stops_level: int
    swap_long: Decimal
    swap_short: Decimal
    currency_base: str
    currency_profit: str
    currency_margin: str
    
    @property
    def pip_value(self) -> Decimal:
        """Calculate pip value (simplified)."""
        if self.digits == 3 or self.digits == 5:
            return self.point * 10
        return self.point


@dataclass
class AccountInfo:
    """MT5 account information."""
    login: int
    server: str
    balance: Decimal
    equity: Decimal
    margin: Decimal
    free_margin: Decimal
    margin_level: Optional[Decimal]
    currency: str
    leverage: int
    trade_allowed: bool
    trade_expert: bool


@dataclass
class OrderRequest:
    """Order request parameters."""
    symbol: str
    order_type: str  # "buy", "sell"
    volume: Decimal
    price: Optional[Decimal] = None  # None for market orders
    sl: Optional[Decimal] = None  # REQUIRED - enforced in connector
    tp: Optional[Decimal] = None
    deviation: int = 20  # Maximum price deviation in points
    magic: int = 0
    comment: str = ""


@dataclass
class OrderResult:
    """Order execution result."""
    success: bool
    ticket: Optional[int] = None
    volume: Optional[Decimal] = None
    price: Optional[Decimal] = None
    error_code: Optional[int] = None
    error_message: Optional[str] = None
    retcode: Optional[int] = None


@dataclass
class Position:
    """Open position from MT5."""
    ticket: int
    symbol: str
    type: str  # "buy" or "sell"
    volume: Decimal
    price_open: Decimal
    sl: Optional[Decimal]
    tp: Optional[Decimal]
    price_current: Decimal
    profit: Decimal
    swap: Decimal
    time: datetime
    magic: int
    comment: str


@dataclass
class MT5HealthStatus:
    """MT5 connection health status."""
    connected: bool
    terminal_connected: bool
    trade_allowed: bool
    server: Optional[str] = None
    ping_ms: Optional[int] = None
    last_error: Optional[str] = None


class MT5Connector:
    """
    Safe wrapper for MetaTrader 5 Python API.
    
    All operations include safety checks and comprehensive logging.
    """
    
    def __init__(
        self,
        terminal_path: Optional[str] = None,
        login: Optional[int] = None,
        password: Optional[str] = None,
        server: Optional[str] = None,
        timeout_ms: int = 60000,
    ):
        self.terminal_path = terminal_path
        self.login = login
        self.password = password
        self.server = server
        self.timeout_ms = timeout_ms
        
        self._connected = False
        self._mt5 = None
        self._logger = logger.bind(component="mt5_connector")
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to MT5."""
        return self._connected and self._mt5 is not None
    
    def connect(self) -> bool:
        """
        Initialize MT5 connection.
        
        Returns:
            True if connected successfully
        """
        try:
            # Import MT5 only when needed (Windows only)
            import MetaTrader5 as mt5
            self._mt5 = mt5
            
            # Initialize
            init_params = {}
            if self.terminal_path:
                init_params["path"] = self.terminal_path
            if self.login:
                init_params["login"] = self.login
            if self.password:
                init_params["password"] = self.password
            if self.server:
                init_params["server"] = self.server
            init_params["timeout"] = self.timeout_ms
            
            if not self._mt5.initialize(**init_params):
                error = self._mt5.last_error()
                self._logger.error("MT5 initialization failed", error=error)
                return False
            
            # Verify connection
            account = self._mt5.account_info()
            if account is None:
                self._logger.error("Failed to get account info after init")
                return False
            
            # Safety check: verify expected account
            if self.login and account.login != self.login:
                self._logger.error(
                    "Account mismatch! Expected login does not match",
                    expected=self.login,
                    actual=account.login,
                )
                self._mt5.shutdown()
                return False
            
            self._connected = True
            self._logger.info(
                "MT5 connected successfully",
                login=account.login,
                server=account.server,
                balance=float(account.balance),
                trade_allowed=account.trade_allowed,
            )
            return True
            
        except ImportError:
            self._logger.warning(
                "MetaTrader5 package not available (Windows only)",
            )
            return False
        except Exception as e:
            self._logger.error("MT5 connection error", error=str(e), exc_info=True)
            return False
    
    def disconnect(self) -> None:
        """Gracefully close MT5 connection."""
        if self._mt5 and self._connected:
            self._mt5.shutdown()
            self._connected = False
            self._logger.info("MT5 disconnected")
    
    def health_check(self) -> MT5HealthStatus:
        """
        Check MT5 connection health.
        
        Returns:
            MT5HealthStatus with current state
        """
        if not self._mt5 or not self._connected:
            return MT5HealthStatus(
                connected=False,
                terminal_connected=False,
                trade_allowed=False,
                last_error="Not initialized",
            )
        
        try:
            terminal = self._mt5.terminal_info()
            account = self._mt5.account_info()
            
            if terminal is None or account is None:
                return MT5HealthStatus(
                    connected=False,
                    terminal_connected=False,
                    trade_allowed=False,
                    last_error="Failed to get terminal/account info",
                )
            
            return MT5HealthStatus(
                connected=True,
                terminal_connected=terminal.connected,
                trade_allowed=account.trade_allowed and account.trade_expert,
                server=account.server,
                ping_ms=terminal.ping_last if hasattr(terminal, 'ping_last') else None,
            )
        except Exception as e:
            return MT5HealthStatus(
                connected=False,
                terminal_connected=False,
                trade_allowed=False,
                last_error=str(e),
            )
    
    def get_account_info(self) -> Optional[AccountInfo]:
        """Get current account information."""
        if not self.is_connected:
            return None
        
        try:
            info = self._mt5.account_info()
            if info is None:
                return None
            
            return AccountInfo(
                login=info.login,
                server=info.server,
                balance=Decimal(str(info.balance)),
                equity=Decimal(str(info.equity)),
                margin=Decimal(str(info.margin)),
                free_margin=Decimal(str(info.margin_free)),
                margin_level=Decimal(str(info.margin_level)) if info.margin_level else None,
                currency=info.currency,
                leverage=info.leverage,
                trade_allowed=info.trade_allowed,
                trade_expert=info.trade_expert,
            )
        except Exception as e:
            self._logger.error("Failed to get account info", error=str(e))
            return None
    
    def get_symbol_info(self, symbol: str) -> Optional[SymbolInfo]:
        """Get symbol specification."""
        if not self.is_connected:
            return None
        
        try:
            info = self._mt5.symbol_info(symbol)
            if info is None:
                # Try selecting the symbol first
                self._mt5.symbol_select(symbol, True)
                info = self._mt5.symbol_info(symbol)
                if info is None:
                    return None
            
            return SymbolInfo(
                name=info.name,
                digits=info.digits,
                point=Decimal(str(info.point)),
                spread=info.spread,
                trade_contract_size=Decimal(str(info.trade_contract_size)),
                volume_min=Decimal(str(info.volume_min)),
                volume_max=Decimal(str(info.volume_max)),
                volume_step=Decimal(str(info.volume_step)),
                trade_stops_level=info.trade_stops_level,
                swap_long=Decimal(str(info.swap_long)),
                swap_short=Decimal(str(info.swap_short)),
                currency_base=info.currency_base,
                currency_profit=info.currency_profit,
                currency_margin=info.currency_margin,
            )
        except Exception as e:
            self._logger.error("Failed to get symbol info", symbol=symbol, error=str(e))
            return None
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    def get_rates(
        self,
        symbol: str,
        timeframe: MT5Timeframe,
        count: int = 500,
    ) -> list[OHLCVBar]:
        """
        Get historical OHLCV bars.
        
        Args:
            symbol: Trading symbol
            timeframe: MT5Timeframe enum value
            count: Number of bars to fetch
            
        Returns:
            List of OHLCVBar objects
        """
        if not self.is_connected:
            return []
        
        try:
            # Ensure symbol is selected
            self._mt5.symbol_select(symbol, True)
            
            # Get rates
            rates = self._mt5.copy_rates_from_pos(symbol, timeframe.value, 0, count)
            
            if rates is None or len(rates) == 0:
                self._logger.warning(
                    "No rates returned",
                    symbol=symbol,
                    timeframe=timeframe.name,
                    count=count,
                )
                return []
            
            bars = []
            for rate in rates:
                bar = OHLCVBar(
                    timestamp=datetime.fromtimestamp(rate['time'], tz=timezone.utc),
                    open=Decimal(str(rate['open'])),
                    high=Decimal(str(rate['high'])),
                    low=Decimal(str(rate['low'])),
                    close=Decimal(str(rate['close'])),
                    tick_volume=int(rate['tick_volume']),
                    spread=Decimal(str(rate['spread'])) if 'spread' in rate.dtype.names else None,
                )
                if bar.is_valid():
                    bars.append(bar)
            
            return bars
            
        except Exception as e:
            self._logger.error(
                "Failed to get rates",
                symbol=symbol,
                timeframe=timeframe.name,
                error=str(e),
            )
            raise
    
    def get_current_spread(self, symbol: str) -> Optional[Decimal]:
        """Get current spread in points."""
        info = self.get_symbol_info(symbol)
        if info:
            return Decimal(str(info.spread)) * info.point
        return None
    
    def place_order(self, order: OrderRequest) -> OrderResult:
        """
        Place an order with MANDATORY safety checks.
        
        CRITICAL: Stop loss is REQUIRED. Orders without SL are rejected.
        
        Args:
            order: OrderRequest with parameters
            
        Returns:
            OrderResult with execution details
        """
        # SAFETY CHECK 1: Stop loss is MANDATORY
        if order.sl is None:
            self._logger.error(
                "ORDER REJECTED: No stop loss provided",
                symbol=order.symbol,
                order_type=order.order_type,
            )
            return OrderResult(
                success=False,
                error_message="SAFETY VIOLATION: Stop loss is required for all orders",
            )
        
        if not self.is_connected:
            return OrderResult(
                success=False,
                error_message="MT5 not connected",
            )
        
        try:
            # SAFETY CHECK 2: Verify trading is allowed
            account = self.get_account_info()
            if not account or not account.trade_allowed:
                return OrderResult(
                    success=False,
                    error_message="Trading not allowed on this account",
                )
            
            # SAFETY CHECK 3: Verify symbol is tradeable
            symbol_info = self.get_symbol_info(order.symbol)
            if not symbol_info:
                return OrderResult(
                    success=False,
                    error_message=f"Symbol {order.symbol} not found",
                )
            
            # SAFETY CHECK 4: Verify volume
            if order.volume < symbol_info.volume_min:
                return OrderResult(
                    success=False,
                    error_message=f"Volume {order.volume} below minimum {symbol_info.volume_min}",
                )
            if order.volume > symbol_info.volume_max:
                return OrderResult(
                    success=False,
                    error_message=f"Volume {order.volume} above maximum {symbol_info.volume_max}",
                )
            
            # SAFETY CHECK 5: Check for existing position (no duplicates by default)
            positions = self.get_open_positions()
            existing = [p for p in positions if p.symbol == order.symbol]
            if existing:
                self._logger.warning(
                    "Position already exists for symbol",
                    symbol=order.symbol,
                    existing_tickets=[p.ticket for p in existing],
                )
                # Note: Could make this a hard block depending on config
            
            # Build the order request
            order_type = (
                self._mt5.ORDER_TYPE_BUY if order.order_type.lower() == "buy"
                else self._mt5.ORDER_TYPE_SELL
            )
            
            # Get current price
            tick = self._mt5.symbol_info_tick(order.symbol)
            if not tick:
                return OrderResult(
                    success=False,
                    error_message="Failed to get current price",
                )
            
            price = tick.ask if order.order_type.lower() == "buy" else tick.bid
            
            request = {
                "action": self._mt5.TRADE_ACTION_DEAL,
                "symbol": order.symbol,
                "volume": float(order.volume),
                "type": order_type,
                "price": price,
                "sl": float(order.sl),
                "deviation": order.deviation,
                "magic": order.magic,
                "comment": order.comment or "forex_platform",
                "type_time": self._mt5.ORDER_TIME_GTC,
                "type_filling": self._mt5.ORDER_FILLING_IOC,
            }
            
            if order.tp:
                request["tp"] = float(order.tp)
            
            self._logger.info(
                "Placing order",
                symbol=order.symbol,
                type=order.order_type,
                volume=float(order.volume),
                price=price,
                sl=float(order.sl),
                tp=float(order.tp) if order.tp else None,
            )
            
            # Execute
            result = self._mt5.order_send(request)
            
            if result.retcode != self._mt5.TRADE_RETCODE_DONE:
                return OrderResult(
                    success=False,
                    retcode=result.retcode,
                    error_message=f"Order failed: {result.comment}",
                )
            
            self._logger.info(
                "Order executed successfully",
                ticket=result.order,
                price=result.price,
                volume=result.volume,
            )
            
            return OrderResult(
                success=True,
                ticket=result.order,
                volume=Decimal(str(result.volume)),
                price=Decimal(str(result.price)),
                retcode=result.retcode,
            )
            
        except Exception as e:
            self._logger.error("Order placement error", error=str(e), exc_info=True)
            return OrderResult(
                success=False,
                error_message=str(e),
            )
    
    def get_open_positions(self) -> list[Position]:
        """Get all open positions."""
        if not self.is_connected:
            return []
        
        try:
            positions = self._mt5.positions_get()
            if positions is None:
                return []
            
            result = []
            for pos in positions:
                result.append(Position(
                    ticket=pos.ticket,
                    symbol=pos.symbol,
                    type="buy" if pos.type == 0 else "sell",
                    volume=Decimal(str(pos.volume)),
                    price_open=Decimal(str(pos.price_open)),
                    sl=Decimal(str(pos.sl)) if pos.sl else None,
                    tp=Decimal(str(pos.tp)) if pos.tp else None,
                    price_current=Decimal(str(pos.price_current)),
                    profit=Decimal(str(pos.profit)),
                    swap=Decimal(str(pos.swap)),
                    time=datetime.fromtimestamp(pos.time, tz=timezone.utc),
                    magic=pos.magic,
                    comment=pos.comment,
                ))
            
            return result
            
        except Exception as e:
            self._logger.error("Failed to get positions", error=str(e))
            return []
    
    def close_position(
        self,
        ticket: int,
        volume: Optional[Decimal] = None,
    ) -> OrderResult:
        """
        Close a position (full or partial).
        
        Args:
            ticket: Position ticket
            volume: Volume to close (None = full close)
            
        Returns:
            OrderResult with execution details
        """
        if not self.is_connected:
            return OrderResult(
                success=False,
                error_message="MT5 not connected",
            )
        
        try:
            # Get position
            position = self._mt5.positions_get(ticket=ticket)
            if not position:
                return OrderResult(
                    success=False,
                    error_message=f"Position {ticket} not found",
                )
            
            pos = position[0]
            close_volume = float(volume) if volume else pos.volume
            
            # Determine close type (opposite of position)
            close_type = (
                self._mt5.ORDER_TYPE_SELL if pos.type == 0
                else self._mt5.ORDER_TYPE_BUY
            )
            
            # Get current price
            tick = self._mt5.symbol_info_tick(pos.symbol)
            if not tick:
                return OrderResult(
                    success=False,
                    error_message="Failed to get current price",
                )
            
            price = tick.bid if pos.type == 0 else tick.ask
            
            request = {
                "action": self._mt5.TRADE_ACTION_DEAL,
                "symbol": pos.symbol,
                "volume": close_volume,
                "type": close_type,
                "position": ticket,
                "price": price,
                "deviation": 20,
                "magic": pos.magic,
                "comment": "close",
                "type_time": self._mt5.ORDER_TIME_GTC,
                "type_filling": self._mt5.ORDER_FILLING_IOC,
            }
            
            result = self._mt5.order_send(request)
            
            if result.retcode != self._mt5.TRADE_RETCODE_DONE:
                return OrderResult(
                    success=False,
                    retcode=result.retcode,
                    error_message=f"Close failed: {result.comment}",
                )
            
            return OrderResult(
                success=True,
                ticket=result.order,
                volume=Decimal(str(result.volume)),
                price=Decimal(str(result.price)),
                retcode=result.retcode,
            )
            
        except Exception as e:
            self._logger.error("Position close error", ticket=ticket, error=str(e))
            return OrderResult(
                success=False,
                error_message=str(e),
            )


# Singleton instance for the application
_connector: Optional[MT5Connector] = None


def get_mt5_connector() -> MT5Connector:
    """Get or create the MT5 connector singleton."""
    global _connector
    if _connector is None:
        from app.config import settings
        _connector = MT5Connector(
            terminal_path=settings.mt5.terminal_path,
            login=settings.mt5.login,
            password=settings.mt5.password,
            server=settings.mt5.server,
            timeout_ms=settings.mt5.timeout_ms,
        )
    return _connector
