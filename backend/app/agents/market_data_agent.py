"""
Market Data Agent
=================
The foundation agent. Ingests, validates, normalizes, and serves all market data.

From 02_AGENT_DEFINITIONS_DATA_LAYER.txt:
- Connect to MT5 and pull OHLCV data
- Collect data for ALL configured symbols across ALL required timeframes
- Normalize timestamps to UTC
- Handle broker-specific symbol suffixes
- Detect and handle gaps, duplicates, anomalies
- Compute and record spread, swap rates, session info
- Produce data quality score per symbol
- Store in PostgreSQL, cache in Redis
"""
import structlog
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional
from dataclasses import dataclass, field

from app.agents.base_agent import BaseAgent, AgentMessage, AgentHealthStatus
from app.data.mt5_connector import (
    MT5Connector,
    MT5Timeframe,
    OHLCVBar,
    get_mt5_connector,
)
from app.data.data_validator import DataValidator, DataNormalizer, ValidationResult

logger = structlog.get_logger()


# Timeframe string to enum mapping
TIMEFRAME_MAP = {
    "M1": MT5Timeframe.M1,
    "M5": MT5Timeframe.M5,
    "M15": MT5Timeframe.M15,
    "M30": MT5Timeframe.M30,
    "H1": MT5Timeframe.H1,
    "H4": MT5Timeframe.H4,
    "D1": MT5Timeframe.D1,
}

# Default symbols to monitor
DEFAULT_SYMBOLS = [
    "GBPJPY", "EURUSD", "GBPUSD", "USDJPY", "USDCHF",
    "USDCAD", "EURAUD", "AUDNZD", "AUDUSD",
]

# Default timeframes to collect
DEFAULT_TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]


@dataclass
class TimeframeData:
    """Data for a single timeframe."""
    timeframe: str
    bars: list[OHLCVBar]
    last_bar_time: Optional[datetime] = None
    is_complete: bool = False
    bars_available: int = 0
    validation: Optional[ValidationResult] = None


@dataclass
class MarketDataSnapshot:
    """Complete market data snapshot for a symbol."""
    symbol: str
    timestamp: datetime
    timeframes: dict[str, TimeframeData] = field(default_factory=dict)
    
    # Spread info
    current_spread_pips: float = 0.0
    average_spread_pips: float = 0.0
    spread_percentile: float = 50.0
    
    # Swap rates
    swap_long: float = 0.0
    swap_short: float = 0.0
    
    # Volume
    tick_volume_current: int = 0
    tick_volume_average: float = 0.0
    
    # Session
    current_session: str = "unknown"
    
    # Quality
    data_quality_score: float = 1.0
    missing_bars: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class MarketDataAgent(BaseAgent):
    """
    Market Data Agent - The foundation of all analysis.
    
    Responsibilities:
    - Pull OHLCV data from MT5 for all symbols and timeframes
    - Validate data quality
    - Normalize and store data
    - Compute spreads, swaps, session info
    - Produce data quality scores
    """
    
    def __init__(
        self,
        name: str = "market_data_agent",
        config: Optional[dict[str, Any]] = None,
    ):
        super().__init__(name, config)
        
        self.symbols = config.get("symbols", DEFAULT_SYMBOLS) if config else DEFAULT_SYMBOLS
        self.timeframes = config.get("timeframes", DEFAULT_TIMEFRAMES) if config else DEFAULT_TIMEFRAMES
        self.bars_to_fetch = config.get("bars_to_fetch", 500) if config else 500
        
        self._connector: Optional[MT5Connector] = None
        self._validator = DataValidator()
        self._normalizer = DataNormalizer()
        
        # Cache for recent data
        self._data_cache: dict[str, MarketDataSnapshot] = {}
    
    async def initialize(self) -> None:
        """Initialize MT5 connection."""
        self._logger.info("Initializing Market Data Agent")
        
        try:
            self._connector = get_mt5_connector()
            connected = self._connector.connect()
            
            if not connected:
                self._logger.warning(
                    "MT5 connection failed - agent will run in degraded mode",
                )
                # Agent can still work with cached/stored data
            
            self.is_initialized = True
            self.is_running = True
            self.started_at = datetime.now(timezone.utc)
            
            self._logger.info(
                "Market Data Agent initialized",
                mt5_connected=connected,
                symbols=self.symbols,
                timeframes=self.timeframes,
            )
        except Exception as e:
            self._logger.error("Failed to initialize", error=str(e))
            self.is_initialized = True  # Still mark as initialized
            self.is_running = True
    
    async def run(self, context: dict[str, Any]) -> AgentMessage:
        """
        Fetch and validate market data for all symbols.
        
        Args:
            context: Can contain:
                - symbols: Optional list of symbols to fetch
                - timeframes: Optional list of timeframes
                - symbol: Single symbol to fetch
        """
        # Determine what to fetch
        symbols = context.get("symbols", self.symbols)
        if "symbol" in context:
            symbols = [context["symbol"]]
        timeframes = context.get("timeframes", self.timeframes)
        
        snapshots = {}
        overall_quality = 1.0
        all_warnings = []
        all_errors = []
        
        for symbol in symbols:
            snapshot = await self._fetch_symbol_data(symbol, timeframes)
            snapshots[symbol] = snapshot
            
            # Track overall quality
            overall_quality = min(overall_quality, snapshot.data_quality_score)
            all_warnings.extend([f"{symbol}: {w}" for w in snapshot.warnings])
            
            # Quality threshold checks
            if snapshot.data_quality_score < 0.5:
                all_errors.append(f"{symbol}: Data quality critically low ({snapshot.data_quality_score:.2f})")
            elif snapshot.data_quality_score < 0.7:
                all_warnings.append(f"{symbol}: Data quality degraded ({snapshot.data_quality_score:.2f})")
        
        # Build response payload
        payload = {
            "snapshots": {
                symbol: self._snapshot_to_dict(snap)
                for symbol, snap in snapshots.items()
            },
            "symbols_fetched": list(snapshots.keys()),
            "timeframes": timeframes,
            "fetch_timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        return self._create_message(
            message_type="market_data_snapshot",
            payload=payload,
            confidence=overall_quality,
            data_quality=overall_quality,
            warnings=all_warnings,
            errors=all_errors,
        )
    
    async def _fetch_symbol_data(
        self,
        symbol: str,
        timeframes: list[str],
    ) -> MarketDataSnapshot:
        """Fetch all data for a single symbol."""
        snapshot = MarketDataSnapshot(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
        )
        
        if not self._connector or not self._connector.is_connected:
            snapshot.data_quality_score = 0.0
            snapshot.warnings.append("MT5 not connected")
            return snapshot
        
        # Normalize symbol name
        normalized_symbol = self._normalizer.normalize_symbol(symbol)
        
        # Get symbol info for spread/swap
        symbol_info = self._connector.get_symbol_info(symbol)
        if symbol_info:
            snapshot.current_spread_pips = float(symbol_info.spread) * float(symbol_info.pip_value)
            snapshot.swap_long = float(symbol_info.swap_long)
            snapshot.swap_short = float(symbol_info.swap_short)
        
        # Fetch each timeframe
        quality_scores = []
        
        for tf_str in timeframes:
            tf_enum = TIMEFRAME_MAP.get(tf_str)
            if not tf_enum:
                continue
            
            try:
                bars = self._connector.get_rates(symbol, tf_enum, self.bars_to_fetch)
                
                if not bars:
                    snapshot.warnings.append(f"{tf_str}: No bars returned")
                    continue
                
                # Normalize bars
                bars = self._normalizer.normalize_bars(
                    bars,
                    digits=symbol_info.digits if symbol_info else 5,
                )
                
                # Validate
                validation = self._validator.validate_bars(bars, symbol, tf_enum)
                
                # Create timeframe data
                tf_data = TimeframeData(
                    timeframe=tf_str,
                    bars=bars,
                    last_bar_time=bars[-1].timestamp if bars else None,
                    is_complete=True,
                    bars_available=len(bars),
                    validation=validation,
                )
                
                snapshot.timeframes[tf_str] = tf_data
                quality_scores.append(validation.quality_score)
                
                # Track warnings
                if validation.warnings:
                    snapshot.warnings.extend([f"{tf_str}: {w}" for w in validation.warnings])
                
                # Track missing bars
                if validation.missing_bars:
                    snapshot.missing_bars.append({
                        "timeframe": tf_str,
                        "count": len(validation.missing_bars),
                    })
                    
            except Exception as e:
                self._logger.error(
                    "Failed to fetch timeframe",
                    symbol=symbol,
                    timeframe=tf_str,
                    error=str(e),
                )
                snapshot.warnings.append(f"{tf_str}: Fetch failed - {str(e)}")
        
        # Calculate overall quality score
        if quality_scores:
            snapshot.data_quality_score = sum(quality_scores) / len(quality_scores)
        else:
            snapshot.data_quality_score = 0.0
        
        # Determine current session
        snapshot.current_session = self._determine_session()
        
        # Calculate tick volume average if we have M30 data
        if "M30" in snapshot.timeframes:
            m30_bars = snapshot.timeframes["M30"].bars
            if m30_bars:
                snapshot.tick_volume_current = m30_bars[-1].tick_volume
                volumes = [b.tick_volume for b in m30_bars[-20:]]
                snapshot.tick_volume_average = sum(volumes) / len(volumes) if volumes else 0
        
        # Cache the snapshot
        self._data_cache[symbol] = snapshot
        
        return snapshot
    
    def _determine_session(self) -> str:
        """Determine the current trading session."""
        now = datetime.now(timezone.utc)
        hour = now.hour
        
        # Simplified session detection
        if 7 <= hour < 16:
            if 12 <= hour < 16:
                return "london_new_york_overlap"
            return "london"
        elif 12 <= hour < 21:
            return "new_york"
        elif hour >= 23 or hour < 8:
            return "asian"
        else:
            return "transition"
    
    def _snapshot_to_dict(self, snapshot: MarketDataSnapshot) -> dict:
        """Convert snapshot to serializable dict."""
        return {
            "symbol": snapshot.symbol,
            "timestamp": snapshot.timestamp.isoformat(),
            "timeframes": {
                tf: {
                    "timeframe": data.timeframe,
                    "last_bar_time": data.last_bar_time.isoformat() if data.last_bar_time else None,
                    "bars_available": data.bars_available,
                    "is_complete": data.is_complete,
                    "quality_score": data.validation.quality_score if data.validation else None,
                }
                for tf, data in snapshot.timeframes.items()
            },
            "current_spread_pips": snapshot.current_spread_pips,
            "average_spread_pips": snapshot.average_spread_pips,
            "swap_long": snapshot.swap_long,
            "swap_short": snapshot.swap_short,
            "tick_volume_current": snapshot.tick_volume_current,
            "tick_volume_average": snapshot.tick_volume_average,
            "current_session": snapshot.current_session,
            "data_quality_score": snapshot.data_quality_score,
            "missing_bars": snapshot.missing_bars,
            "warnings": snapshot.warnings,
        }
    
    async def health_check(self) -> AgentHealthStatus:
        """Check agent health."""
        is_healthy = self.is_initialized
        
        # Check MT5 connection
        if self._connector:
            mt5_health = self._connector.health_check()
            is_healthy = is_healthy and mt5_health.connected
        
        return AgentHealthStatus(
            agent_name=self.name,
            is_healthy=is_healthy,
            last_run=self.last_run,
            last_success=self.last_success,
            last_error=self.last_error,
            consecutive_failures=self.consecutive_failures,
            uptime_seconds=self._get_uptime_seconds(),
        )
    
    def get_dependencies(self) -> list[str]:
        """Market Data Agent has no dependencies."""
        return []
    
    def get_cached_data(self, symbol: str) -> Optional[MarketDataSnapshot]:
        """Get cached data for a symbol."""
        return self._data_cache.get(symbol)
    
    async def shutdown(self) -> None:
        """Shutdown and disconnect from MT5."""
        if self._connector:
            self._connector.disconnect()
        await super().shutdown()
