"""
Technical Indicators
====================
All indicator calculation modules.
"""
from app.indicators.moving_averages import (
    EMACluster,
    SMABaseline,
    calculate_ema,
    calculate_sma,
    calculate_ema_cluster,
    calculate_sma_baseline,
    price_distance_from_ema,
    calculate_linear_regression_slope,
)

from app.indicators.volatility import (
    ATRResult,
    BollingerBands,
    DonchianChannels,
    VolatilityState,
    calculate_true_range,
    calculate_atr,
    calculate_bollinger_bands,
    calculate_donchian_channels,
    detect_squeeze,
    calculate_volatility_state,
)

from app.indicators.momentum import (
    RSIResult,
    MACDResult,
    StochasticResult,
    calculate_rsi,
    calculate_macd,
    calculate_stochastic,
    calculate_roc,
    calculate_adx,
)

from app.indicators.structure import (
    SwingPoint,
    StructureZone,
    StructuralEvent,
    SwingAnalysis,
    detect_swing_points,
    identify_support_resistance_zones,
    detect_break_of_structure,
)

__all__ = [
    # Moving Averages
    "EMACluster",
    "SMABaseline",
    "calculate_ema",
    "calculate_sma",
    "calculate_ema_cluster",
    "calculate_sma_baseline",
    "price_distance_from_ema",
    "calculate_linear_regression_slope",
    # Volatility
    "ATRResult",
    "BollingerBands",
    "DonchianChannels",
    "VolatilityState",
    "calculate_true_range",
    "calculate_atr",
    "calculate_bollinger_bands",
    "calculate_donchian_channels",
    "detect_squeeze",
    "calculate_volatility_state",
    # Momentum
    "RSIResult",
    "MACDResult",
    "StochasticResult",
    "calculate_rsi",
    "calculate_macd",
    "calculate_stochastic",
    "calculate_roc",
    "calculate_adx",
    # Structure
    "SwingPoint",
    "StructureZone",
    "StructuralEvent",
    "SwingAnalysis",
    "detect_swing_points",
    "identify_support_resistance_zones",
    "detect_break_of_structure",
]
