"""
Momentum Indicators
===================
RSI, MACD, Stochastic, and momentum metrics.
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional


@dataclass
class RSIResult:
    """RSI calculation result."""
    value: float
    is_overbought: bool
    is_oversold: bool
    zone: str  # "overbought", "oversold", "neutral"


@dataclass
class MACDResult:
    """MACD calculation result."""
    macd_line: float
    signal_line: float
    histogram: float
    is_bullish: bool  # MACD above signal
    histogram_direction: str  # "rising", "falling", "flat"
    zero_line_position: str  # "above", "below"


@dataclass
class StochasticResult:
    """Stochastic oscillator result."""
    k: float  # Fast line
    d: float  # Slow line (signal)
    is_overbought: bool
    is_oversold: bool
    crossover: str  # "bullish", "bearish", "none"


def calculate_rsi(
    close: pd.Series,
    period: int = 14,
    overbought: float = 70.0,
    oversold: float = 30.0,
) -> Optional[RSIResult]:
    """
    Calculate Relative Strength Index.
    
    Args:
        close: Close prices
        period: RSI period
        overbought: Overbought threshold
        oversold: Oversold threshold
        
    Returns:
        RSIResult or None if insufficient data
    """
    if len(close) < period + 1:
        return None
    
    # Calculate price changes
    delta = close.diff()
    
    # Separate gains and losses
    gains = delta.where(delta > 0, 0)
    losses = -delta.where(delta < 0, 0)
    
    # Calculate average gains and losses (Wilder's smoothing)
    avg_gain = gains.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = losses.ewm(alpha=1/period, min_periods=period).mean()
    
    # Calculate RS and RSI
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    
    current_rsi = float(rsi.iloc[-1])
    
    is_overbought = current_rsi >= overbought
    is_oversold = current_rsi <= oversold
    
    if is_overbought:
        zone = "overbought"
    elif is_oversold:
        zone = "oversold"
    else:
        zone = "neutral"
    
    return RSIResult(
        value=current_rsi,
        is_overbought=is_overbought,
        is_oversold=is_oversold,
        zone=zone,
    )


def calculate_macd(
    close: pd.Series,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> Optional[MACDResult]:
    """
    Calculate MACD.
    
    Args:
        close: Close prices
        fast_period: Fast EMA period
        slow_period: Slow EMA period
        signal_period: Signal line period
        
    Returns:
        MACDResult or None if insufficient data
    """
    if len(close) < slow_period + signal_period:
        return None
    
    # Calculate EMAs
    ema_fast = close.ewm(span=fast_period, adjust=False).mean()
    ema_slow = close.ewm(span=slow_period, adjust=False).mean()
    
    # MACD line
    macd_line = ema_fast - ema_slow
    
    # Signal line
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    
    # Histogram
    histogram = macd_line - signal_line
    
    current_macd = float(macd_line.iloc[-1])
    current_signal = float(signal_line.iloc[-1])
    current_histogram = float(histogram.iloc[-1])
    
    # Determine histogram direction
    if len(histogram) >= 2:
        prev_histogram = float(histogram.iloc[-2])
        if current_histogram > prev_histogram:
            hist_direction = "rising"
        elif current_histogram < prev_histogram:
            hist_direction = "falling"
        else:
            hist_direction = "flat"
    else:
        hist_direction = "flat"
    
    return MACDResult(
        macd_line=current_macd,
        signal_line=current_signal,
        histogram=current_histogram,
        is_bullish=current_macd > current_signal,
        histogram_direction=hist_direction,
        zero_line_position="above" if current_macd > 0 else "below",
    )


def calculate_stochastic(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_period: int = 14,
    d_period: int = 3,
    smooth_k: int = 3,
    overbought: float = 80.0,
    oversold: float = 20.0,
) -> Optional[StochasticResult]:
    """
    Calculate Stochastic Oscillator.
    
    Args:
        high: High prices
        low: Low prices
        close: Close prices
        k_period: %K period
        d_period: %D period
        smooth_k: %K smoothing
        overbought: Overbought threshold
        oversold: Oversold threshold
        
    Returns:
        StochasticResult or None if insufficient data
    """
    if len(close) < k_period + d_period:
        return None
    
    # Calculate raw %K
    lowest_low = low.rolling(window=k_period).min()
    highest_high = high.rolling(window=k_period).max()
    
    raw_k = 100 * (close - lowest_low) / (highest_high - lowest_low)
    
    # Smooth %K
    k = raw_k.rolling(window=smooth_k).mean()
    
    # Calculate %D (signal)
    d = k.rolling(window=d_period).mean()
    
    current_k = float(k.iloc[-1])
    current_d = float(d.iloc[-1])
    
    # Detect crossover
    if len(k) >= 2 and len(d) >= 2:
        prev_k = float(k.iloc[-2])
        prev_d = float(d.iloc[-2])
        
        if prev_k <= prev_d and current_k > current_d:
            crossover = "bullish"
        elif prev_k >= prev_d and current_k < current_d:
            crossover = "bearish"
        else:
            crossover = "none"
    else:
        crossover = "none"
    
    return StochasticResult(
        k=current_k,
        d=current_d,
        is_overbought=current_k >= overbought,
        is_oversold=current_k <= oversold,
        crossover=crossover,
    )


def calculate_roc(
    close: pd.Series,
    period: int = 12,
) -> Optional[float]:
    """
    Calculate Rate of Change.
    
    Args:
        close: Close prices
        period: ROC period
        
    Returns:
        ROC percentage or None if insufficient data
    """
    if len(close) < period + 1:
        return None
    
    current = float(close.iloc[-1])
    past = float(close.iloc[-period - 1])
    
    if past == 0:
        return None
    
    return ((current - past) / past) * 100


def calculate_adx(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> Optional[dict]:
    """
    Calculate ADX with +DI and -DI.
    
    Args:
        high: High prices
        low: Low prices
        close: Close prices
        period: ADX period
        
    Returns:
        Dict with adx, plus_di, minus_di or None if insufficient data
    """
    if len(close) < period * 2:
        return None
    
    # Calculate True Range
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = abs(high - prev_close)
    tr3 = abs(low - prev_close)
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Calculate +DM and -DM
    plus_dm = high.diff()
    minus_dm = -low.diff()
    
    plus_dm = plus_dm.where(
        (plus_dm > minus_dm) & (plus_dm > 0), 
        0
    )
    minus_dm = minus_dm.where(
        (minus_dm > plus_dm) & (minus_dm > 0), 
        0
    )
    
    # Smooth with Wilder's method
    atr = tr.ewm(alpha=1/period, min_periods=period).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1/period, min_periods=period).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1/period, min_periods=period).mean() / atr)
    
    # Calculate DX and ADX
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.ewm(alpha=1/period, min_periods=period).mean()
    
    return {
        "adx": float(adx.iloc[-1]),
        "plus_di": float(plus_di.iloc[-1]),
        "minus_di": float(minus_di.iloc[-1]),
        "trend_strength": "strong" if float(adx.iloc[-1]) > 25 else "weak" if float(adx.iloc[-1]) > 15 else "absent",
    }
