"""
Volatility Indicators
=====================
ATR, Bollinger Bands, Donchian Channels, and volatility metrics.
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional


@dataclass
class ATRResult:
    """ATR calculation result."""
    atr: float
    atr_percent: float  # ATR as percentage of price
    percentile: float  # Where current ATR sits vs history (0-100)


@dataclass
class BollingerBands:
    """Bollinger Bands values."""
    upper: float
    middle: float
    lower: float
    bandwidth: float  # (upper - lower) / middle
    percent_b: float  # Where price is within bands (0-1, can exceed)


@dataclass
class DonchianChannels:
    """Donchian Channel values."""
    upper: float
    middle: float
    lower: float
    width: float


@dataclass
class VolatilityState:
    """Overall volatility assessment."""
    atr_result: ATRResult
    bollinger: BollingerBands
    donchian: DonchianChannels
    is_compressed: bool  # Squeeze detected
    is_expanding: bool  # Volatility increasing
    volatility_regime: str  # "low", "normal", "high", "extreme"


def calculate_true_range(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
) -> pd.Series:
    """
    Calculate True Range.
    
    TR = max(high - low, abs(high - prev_close), abs(low - prev_close))
    """
    prev_close = close.shift(1)
    
    tr1 = high - low
    tr2 = abs(high - prev_close)
    tr3 = abs(low - prev_close)
    
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)


def calculate_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
    history_for_percentile: int = 60,
) -> Optional[ATRResult]:
    """
    Calculate ATR with percentile ranking.
    
    Args:
        high: High prices
        low: Low prices
        close: Close prices
        period: ATR period
        history_for_percentile: Bars to use for percentile calc
        
    Returns:
        ATRResult or None if insufficient data
    """
    if len(close) < period + 1:
        return None
    
    tr = calculate_true_range(high, low, close)
    atr_series = tr.rolling(window=period).mean()
    
    current_atr = float(atr_series.iloc[-1])
    current_price = float(close.iloc[-1])
    
    # Calculate percentile
    if len(atr_series) >= history_for_percentile:
        recent_atrs = atr_series.iloc[-history_for_percentile:].dropna()
        percentile = (recent_atrs < current_atr).sum() / len(recent_atrs) * 100
    else:
        percentile = 50.0  # Default if not enough history
    
    return ATRResult(
        atr=current_atr,
        atr_percent=(current_atr / current_price) * 100 if current_price > 0 else 0,
        percentile=float(percentile),
    )


def calculate_bollinger_bands(
    close: pd.Series,
    period: int = 20,
    std_dev: float = 2.0,
) -> Optional[BollingerBands]:
    """
    Calculate Bollinger Bands.
    
    Args:
        close: Close prices
        period: Moving average period
        std_dev: Standard deviation multiplier
        
    Returns:
        BollingerBands or None if insufficient data
    """
    if len(close) < period:
        return None
    
    middle = close.rolling(window=period).mean()
    rolling_std = close.rolling(window=period).std()
    
    upper = middle + (rolling_std * std_dev)
    lower = middle - (rolling_std * std_dev)
    
    current_upper = float(upper.iloc[-1])
    current_middle = float(middle.iloc[-1])
    current_lower = float(lower.iloc[-1])
    current_close = float(close.iloc[-1])
    
    # Bandwidth = (upper - lower) / middle
    bandwidth = (current_upper - current_lower) / current_middle if current_middle > 0 else 0
    
    # Percent B = (price - lower) / (upper - lower)
    band_width = current_upper - current_lower
    percent_b = (current_close - current_lower) / band_width if band_width > 0 else 0.5
    
    return BollingerBands(
        upper=current_upper,
        middle=current_middle,
        lower=current_lower,
        bandwidth=bandwidth,
        percent_b=percent_b,
    )


def calculate_donchian_channels(
    high: pd.Series,
    low: pd.Series,
    period: int = 20,
) -> Optional[DonchianChannels]:
    """
    Calculate Donchian Channels.
    
    Args:
        high: High prices
        low: Low prices
        period: Lookback period
        
    Returns:
        DonchianChannels or None if insufficient data
    """
    if len(high) < period:
        return None
    
    upper = float(high.rolling(window=period).max().iloc[-1])
    lower = float(low.rolling(window=period).min().iloc[-1])
    middle = (upper + lower) / 2
    
    return DonchianChannels(
        upper=upper,
        middle=middle,
        lower=lower,
        width=upper - lower,
    )


def detect_squeeze(
    bollinger: BollingerBands,
    bandwidth_percentile_threshold: float = 20.0,
    recent_bandwidths: Optional[pd.Series] = None,
) -> bool:
    """
    Detect Bollinger Band squeeze (low volatility compression).
    
    Args:
        bollinger: Current Bollinger Bands
        bandwidth_percentile_threshold: Percentile below which is squeeze
        recent_bandwidths: Historical bandwidth values for percentile
        
    Returns:
        True if squeeze detected
    """
    if recent_bandwidths is not None and len(recent_bandwidths) > 20:
        percentile = (recent_bandwidths < bollinger.bandwidth).sum() / len(recent_bandwidths) * 100
        return percentile < bandwidth_percentile_threshold
    
    # Fallback: use absolute bandwidth threshold
    return bollinger.bandwidth < 0.02  # 2% bandwidth is relatively tight


def calculate_volatility_state(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    atr_period: int = 14,
    bb_period: int = 20,
    donchian_period: int = 20,
) -> Optional[VolatilityState]:
    """
    Calculate comprehensive volatility state.
    
    Returns:
        VolatilityState with all volatility metrics
    """
    atr_result = calculate_atr(high, low, close, atr_period)
    bollinger = calculate_bollinger_bands(close, bb_period)
    donchian = calculate_donchian_channels(high, low, donchian_period)
    
    if not all([atr_result, bollinger, donchian]):
        return None
    
    # Determine compression
    is_compressed = (
        atr_result.percentile < 20 or
        bollinger.bandwidth < 0.02
    )
    
    # Check if expanding (compare recent ATR to slightly older ATR)
    is_expanding = False
    if len(close) >= atr_period * 2:
        tr = calculate_true_range(high, low, close)
        atr_series = tr.rolling(window=atr_period).mean()
        recent_atr = atr_series.iloc[-1]
        older_atr = atr_series.iloc[-atr_period]
        is_expanding = recent_atr > older_atr * 1.2  # 20% increase
    
    # Determine regime
    if atr_result.percentile < 20:
        regime = "low"
    elif atr_result.percentile < 40:
        regime = "normal"
    elif atr_result.percentile < 80:
        regime = "high"
    else:
        regime = "extreme"
    
    return VolatilityState(
        atr_result=atr_result,
        bollinger=bollinger,
        donchian=donchian,
        is_compressed=is_compressed,
        is_expanding=is_expanding,
        volatility_regime=regime,
    )
