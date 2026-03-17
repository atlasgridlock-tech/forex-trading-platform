"""
Data Validator
==============
Validates market data quality and detects anomalies.

From 02_AGENT_DEFINITIONS_DATA_LAYER.txt:
- Detect missing bars (gaps in candle sequence)
- Detect duplicate candles
- Detect timestamp misalignments
- Detect feed interruptions
- Validate OHLC sanity (no negative prices, H >= L, etc.)
- Validate spread is within acceptable range
"""
import structlog
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from app.data.mt5_connector import OHLCVBar, MT5Timeframe

logger = structlog.get_logger()


@dataclass
class ValidationResult:
    """Result of data validation."""
    is_valid: bool
    quality_score: float  # 0.0 to 1.0
    missing_bars: list[datetime] = field(default_factory=list)
    duplicate_bars: list[datetime] = field(default_factory=list)
    invalid_bars: list[tuple[datetime, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# Timeframe to expected bar duration mapping
TIMEFRAME_DURATIONS = {
    MT5Timeframe.M1: timedelta(minutes=1),
    MT5Timeframe.M5: timedelta(minutes=5),
    MT5Timeframe.M15: timedelta(minutes=15),
    MT5Timeframe.M30: timedelta(minutes=30),
    MT5Timeframe.H1: timedelta(hours=1),
    MT5Timeframe.H4: timedelta(hours=4),
    MT5Timeframe.D1: timedelta(days=1),
}

# Expected spread ranges per symbol (in pips)
DEFAULT_SPREAD_LIMITS = {
    "EURUSD": 3.0,
    "GBPUSD": 4.0,
    "USDJPY": 3.0,
    "GBPJPY": 6.0,
    "USDCHF": 4.0,
    "USDCAD": 4.0,
    "EURAUD": 5.0,
    "AUDNZD": 5.0,
    "AUDUSD": 3.0,
}


class DataValidator:
    """
    Validates market data quality.
    
    Performs checks for:
    - Bar sequence continuity
    - OHLC value sanity
    - Spread normality
    - Volume patterns
    """
    
    def __init__(
        self,
        spread_limits: Optional[dict[str, float]] = None,
        min_volume_threshold: int = 0,
        max_gap_tolerance: int = 5,  # Max missing bars before critical
    ):
        self.spread_limits = spread_limits or DEFAULT_SPREAD_LIMITS
        self.min_volume_threshold = min_volume_threshold
        self.max_gap_tolerance = max_gap_tolerance
        self._logger = logger.bind(component="data_validator")
    
    def validate_bars(
        self,
        bars: list[OHLCVBar],
        symbol: str,
        timeframe: MT5Timeframe,
    ) -> ValidationResult:
        """
        Validate a sequence of OHLCV bars.
        
        Args:
            bars: List of OHLCVBar to validate
            symbol: Trading symbol
            timeframe: Timeframe of the bars
            
        Returns:
            ValidationResult with quality assessment
        """
        result = ValidationResult(is_valid=True, quality_score=1.0)
        
        if not bars:
            result.is_valid = False
            result.quality_score = 0.0
            result.errors.append("No bars provided")
            return result
        
        # Sort by timestamp
        sorted_bars = sorted(bars, key=lambda b: b.timestamp)
        
        # Validate individual bars
        for bar in sorted_bars:
            bar_issues = self._validate_single_bar(bar, symbol)
            if bar_issues:
                result.invalid_bars.append((bar.timestamp, "; ".join(bar_issues)))
        
        # Check for gaps and duplicates
        expected_duration = TIMEFRAME_DURATIONS.get(timeframe)
        if expected_duration:
            gaps, dupes = self._check_continuity(sorted_bars, expected_duration)
            result.missing_bars = gaps
            result.duplicate_bars = dupes
        
        # Calculate quality score
        total_bars = len(sorted_bars)
        issues_count = (
            len(result.missing_bars) +
            len(result.duplicate_bars) +
            len(result.invalid_bars)
        )
        
        # Deduct points for issues
        if total_bars > 0:
            issue_ratio = issues_count / total_bars
            result.quality_score = max(0.0, 1.0 - (issue_ratio * 2))  # 50% issues = 0 score
        
        # Add warnings/errors based on severity
        if result.missing_bars:
            if len(result.missing_bars) > self.max_gap_tolerance:
                result.errors.append(
                    f"Critical gap: {len(result.missing_bars)} missing bars"
                )
                result.is_valid = False
            else:
                result.warnings.append(
                    f"Minor gaps: {len(result.missing_bars)} missing bars"
                )
        
        if result.duplicate_bars:
            result.warnings.append(
                f"Duplicate timestamps: {len(result.duplicate_bars)}"
            )
        
        if result.invalid_bars:
            result.warnings.append(
                f"Invalid bars: {len(result.invalid_bars)}"
            )
        
        # Quality thresholds
        if result.quality_score < 0.5:
            result.is_valid = False
            result.errors.append(
                f"Data quality critically low: {result.quality_score:.2f}"
            )
        elif result.quality_score < 0.7:
            result.warnings.append(
                f"Data quality degraded: {result.quality_score:.2f}"
            )
        
        return result
    
    def _validate_single_bar(
        self,
        bar: OHLCVBar,
        symbol: str,
    ) -> list[str]:
        """Validate a single bar. Returns list of issues."""
        issues = []
        
        # OHLC sanity
        if not bar.is_valid():
            if bar.high < bar.low:
                issues.append("High < Low")
            if bar.open <= 0 or bar.close <= 0:
                issues.append("Invalid price (zero or negative)")
            if bar.tick_volume < 0:
                issues.append("Negative volume")
        
        # Zero volume during expected active hours
        if bar.tick_volume == 0:
            hour = bar.timestamp.hour
            # Rough check for market hours (not weekends, not dead hours)
            weekday = bar.timestamp.weekday()
            if weekday < 5 and 7 <= hour <= 21:  # Mon-Fri, approximate market hours
                issues.append("Zero volume during active hours")
        
        # Spread check
        if bar.spread is not None:
            max_spread = self.spread_limits.get(symbol, 5.0)
            spread_pips = float(bar.spread)
            if spread_pips > max_spread * 2:  # Allow some tolerance
                issues.append(f"Spread too high: {spread_pips:.1f} pips")
        
        return issues
    
    def _check_continuity(
        self,
        bars: list[OHLCVBar],
        expected_duration: timedelta,
    ) -> tuple[list[datetime], list[datetime]]:
        """
        Check for gaps and duplicates in bar sequence.
        
        Returns:
            Tuple of (missing_timestamps, duplicate_timestamps)
        """
        missing = []
        duplicates = []
        
        seen_timestamps = set()
        
        for i in range(len(bars)):
            ts = bars[i].timestamp
            
            # Check duplicates
            if ts in seen_timestamps:
                duplicates.append(ts)
            seen_timestamps.add(ts)
            
            # Check gaps (skip first bar)
            if i > 0:
                prev_ts = bars[i - 1].timestamp
                expected_ts = prev_ts + expected_duration
                
                # Allow for weekend gaps (skip Sat/Sun)
                while expected_ts.weekday() >= 5:
                    expected_ts += expected_duration
                
                # If there's a gap, record missing bars
                while expected_ts < ts:
                    # Skip weekends
                    if expected_ts.weekday() < 5:
                        missing.append(expected_ts)
                    expected_ts += expected_duration
        
        return missing, duplicates
    
    def validate_spread(
        self,
        symbol: str,
        current_spread: Decimal,
    ) -> tuple[bool, str]:
        """
        Check if spread is acceptable for trading.
        
        Returns:
            Tuple of (is_acceptable, message)
        """
        max_spread = self.spread_limits.get(symbol, 5.0)
        spread_float = float(current_spread)
        
        if spread_float > max_spread:
            return False, f"Spread {spread_float:.1f} exceeds limit {max_spread}"
        
        if spread_float > max_spread * 0.7:
            return True, f"Spread elevated: {spread_float:.1f} (limit: {max_spread})"
        
        return True, "Spread normal"


class DataNormalizer:
    """
    Normalizes market data to consistent format.
    
    Handles:
    - Timestamp normalization to UTC
    - Broker-specific symbol suffixes
    - Price precision normalization
    """
    
    # Common broker symbol suffixes to strip
    SYMBOL_SUFFIXES = [".raw", "_i", ".ecn", ".pro", "-ECN"]
    
    def __init__(self):
        self._logger = logger.bind(component="data_normalizer")
    
    def normalize_symbol(self, symbol: str) -> str:
        """
        Normalize symbol name by removing broker-specific suffixes.
        
        Args:
            symbol: Raw symbol from broker
            
        Returns:
            Normalized symbol name
        """
        result = symbol.upper()
        for suffix in self.SYMBOL_SUFFIXES:
            if result.endswith(suffix.upper()):
                result = result[:-len(suffix)]
        return result
    
    def normalize_timestamp(self, ts: datetime) -> datetime:
        """
        Ensure timestamp is in UTC.
        
        Args:
            ts: Input timestamp
            
        Returns:
            UTC timestamp
        """
        if ts.tzinfo is None:
            # Assume UTC for naive timestamps
            return ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc)
    
    def normalize_bars(
        self,
        bars: list[OHLCVBar],
        digits: int = 5,
    ) -> list[OHLCVBar]:
        """
        Normalize a list of bars.
        
        Args:
            bars: Raw bars
            digits: Price precision
            
        Returns:
            Normalized bars
        """
        normalized = []
        for bar in bars:
            normalized.append(OHLCVBar(
                timestamp=self.normalize_timestamp(bar.timestamp),
                open=round(bar.open, digits),
                high=round(bar.high, digits),
                low=round(bar.low, digits),
                close=round(bar.close, digits),
                tick_volume=bar.tick_volume,
                spread=bar.spread,
            ))
        return normalized
