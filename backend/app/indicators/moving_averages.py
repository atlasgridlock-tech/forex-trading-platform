"""
Moving Average Indicators
=========================
EMA, SMA, and alignment calculations.
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional


@dataclass
class EMACluster:
    """EMA cluster values."""
    ema_8: float
    ema_21: float
    ema_50: float
    ema_100: float
    ema_200: float
    
    @property
    def is_bullish_aligned(self) -> bool:
        """Check if EMAs are in bullish alignment (shorter > longer)."""
        return (
            self.ema_8 > self.ema_21 > self.ema_50 > self.ema_100 > self.ema_200
        )
    
    @property
    def is_bearish_aligned(self) -> bool:
        """Check if EMAs are in bearish alignment (shorter < longer)."""
        return (
            self.ema_8 < self.ema_21 < self.ema_50 < self.ema_100 < self.ema_200
        )
    
    def alignment_score(self) -> float:
        """
        Calculate EMA alignment score.
        
        Returns:
            -1.0 (bearish) to 1.0 (bullish), 0.0 (mixed)
        """
        emas = [self.ema_8, self.ema_21, self.ema_50, self.ema_100, self.ema_200]
        
        # Count bullish pairs (shorter > longer)
        bullish_pairs = 0
        total_pairs = 0
        
        for i in range(len(emas) - 1):
            for j in range(i + 1, len(emas)):
                total_pairs += 1
                if emas[i] > emas[j]:
                    bullish_pairs += 1
        
        # Convert to -1 to 1 scale
        if total_pairs == 0:
            return 0.0
        
        ratio = bullish_pairs / total_pairs
        return (ratio * 2) - 1  # 0->-1, 0.5->0, 1->1


@dataclass
class SMABaseline:
    """SMA baseline values."""
    sma_20: float
    sma_50: float
    sma_200: float


def calculate_ema(prices: pd.Series, period: int) -> pd.Series:
    """
    Calculate Exponential Moving Average.
    
    Args:
        prices: Price series (typically close)
        period: EMA period
        
    Returns:
        EMA series
    """
    return prices.ewm(span=period, adjust=False).mean()


def calculate_sma(prices: pd.Series, period: int) -> pd.Series:
    """
    Calculate Simple Moving Average.
    
    Args:
        prices: Price series
        period: SMA period
        
    Returns:
        SMA series
    """
    return prices.rolling(window=period).mean()


def calculate_ema_cluster(closes: pd.Series) -> Optional[EMACluster]:
    """
    Calculate full EMA cluster.
    
    Args:
        closes: Close price series (needs at least 200 bars)
        
    Returns:
        EMACluster or None if insufficient data
    """
    if len(closes) < 200:
        return None
    
    return EMACluster(
        ema_8=float(calculate_ema(closes, 8).iloc[-1]),
        ema_21=float(calculate_ema(closes, 21).iloc[-1]),
        ema_50=float(calculate_ema(closes, 50).iloc[-1]),
        ema_100=float(calculate_ema(closes, 100).iloc[-1]),
        ema_200=float(calculate_ema(closes, 200).iloc[-1]),
    )


def calculate_sma_baseline(closes: pd.Series) -> Optional[SMABaseline]:
    """
    Calculate SMA baseline values.
    
    Args:
        closes: Close price series
        
    Returns:
        SMABaseline or None if insufficient data
    """
    if len(closes) < 200:
        return None
    
    return SMABaseline(
        sma_20=float(calculate_sma(closes, 20).iloc[-1]),
        sma_50=float(calculate_sma(closes, 50).iloc[-1]),
        sma_200=float(calculate_sma(closes, 200).iloc[-1]),
    )


def price_distance_from_ema(
    price: float,
    ema_value: float,
    atr: float,
) -> float:
    """
    Calculate price distance from EMA in ATR units.
    
    Args:
        price: Current price
        ema_value: EMA value
        atr: Current ATR value
        
    Returns:
        Distance in ATR units (positive = above, negative = below)
    """
    if atr == 0:
        return 0.0
    return (price - ema_value) / atr


def calculate_linear_regression_slope(
    prices: pd.Series,
    period: int = 20,
) -> float:
    """
    Calculate linear regression slope of prices.
    
    Args:
        prices: Price series
        period: Lookback period
        
    Returns:
        Slope value (positive = uptrend, negative = downtrend)
    """
    if len(prices) < period:
        return 0.0
    
    recent = prices.iloc[-period:]
    x = np.arange(period)
    y = recent.values
    
    # Linear regression: y = mx + b
    slope, _ = np.polyfit(x, y, 1)
    
    return float(slope)
