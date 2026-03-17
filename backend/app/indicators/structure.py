"""
Structure Indicators
====================
Swing point detection, support/resistance zones, structural events.
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List


@dataclass
class SwingPoint:
    """A swing high or swing low."""
    timestamp: datetime
    price: float
    type: str  # "swing_high" or "swing_low"
    classification: Optional[str] = None  # "HH", "LH", "HL", "LL"
    significance: float = 0.5  # 0.0 to 1.0
    index: int = 0


@dataclass
class StructureZone:
    """Support or resistance zone."""
    upper_bound: float
    lower_bound: float
    type: str  # "support" or "resistance"
    strength: float = 0.5  # 0.0 to 1.0
    touch_count: int = 1
    is_fresh: bool = True
    timeframe: str = "M30"
    
    @property
    def midpoint(self) -> float:
        return (self.upper_bound + self.lower_bound) / 2
    
    def contains_price(self, price: float) -> bool:
        """Check if price is within the zone."""
        return self.lower_bound <= price <= self.upper_bound
    
    def distance_from_price(self, price: float) -> float:
        """Distance from price to zone midpoint."""
        return abs(price - self.midpoint)


@dataclass
class StructuralEvent:
    """A significant structural event (BOS, CHOCH, etc.)."""
    event_type: str  # "bos", "choch", "failed_breakout", "liquidity_sweep"
    timestamp: datetime
    price: float
    significance: float
    description: str


@dataclass
class SwingAnalysis:
    """Complete swing point analysis."""
    swing_highs: List[SwingPoint]
    swing_lows: List[SwingPoint]
    swing_sequence: str  # "HH_HL", "LH_LL", "mixed"
    trend_direction: str  # "bullish", "bearish", "neutral"
    last_hh: Optional[SwingPoint] = None
    last_hl: Optional[SwingPoint] = None
    last_lh: Optional[SwingPoint] = None
    last_ll: Optional[SwingPoint] = None


def detect_swing_points(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    timestamps: pd.Series,
    lookback: int = 5,
) -> SwingAnalysis:
    """
    Detect swing highs and swing lows.
    
    A swing high is a bar where the high is higher than the highs
    of the N bars before and after it.
    
    Args:
        high: High prices
        low: Low prices
        close: Close prices
        timestamps: Bar timestamps
        lookback: Number of bars on each side to confirm swing
        
    Returns:
        SwingAnalysis with detected swings
    """
    swing_highs = []
    swing_lows = []
    
    # Need at least 2*lookback + 1 bars
    if len(high) < 2 * lookback + 1:
        return SwingAnalysis(
            swing_highs=[],
            swing_lows=[],
            swing_sequence="mixed",
            trend_direction="neutral",
        )
    
    # Detect swing points
    for i in range(lookback, len(high) - lookback):
        # Check for swing high
        is_swing_high = True
        for j in range(1, lookback + 1):
            if high.iloc[i] <= high.iloc[i - j] or high.iloc[i] <= high.iloc[i + j]:
                is_swing_high = False
                break
        
        if is_swing_high:
            swing_highs.append(SwingPoint(
                timestamp=timestamps.iloc[i],
                price=float(high.iloc[i]),
                type="swing_high",
                index=i,
            ))
        
        # Check for swing low
        is_swing_low = True
        for j in range(1, lookback + 1):
            if low.iloc[i] >= low.iloc[i - j] or low.iloc[i] >= low.iloc[i + j]:
                is_swing_low = False
                break
        
        if is_swing_low:
            swing_lows.append(SwingPoint(
                timestamp=timestamps.iloc[i],
                price=float(low.iloc[i]),
                type="swing_low",
                index=i,
            ))
    
    # Classify swings as HH, LH, HL, LL
    swing_highs = _classify_swing_highs(swing_highs)
    swing_lows = _classify_swing_lows(swing_lows)
    
    # Determine sequence and trend
    sequence, direction = _analyze_swing_sequence(swing_highs, swing_lows)
    
    # Find most recent classified swings
    last_hh = next((s for s in reversed(swing_highs) if s.classification == "HH"), None)
    last_lh = next((s for s in reversed(swing_highs) if s.classification == "LH"), None)
    last_hl = next((s for s in reversed(swing_lows) if s.classification == "HL"), None)
    last_ll = next((s for s in reversed(swing_lows) if s.classification == "LL"), None)
    
    return SwingAnalysis(
        swing_highs=swing_highs,
        swing_lows=swing_lows,
        swing_sequence=sequence,
        trend_direction=direction,
        last_hh=last_hh,
        last_hl=last_hl,
        last_lh=last_lh,
        last_ll=last_ll,
    )


def _classify_swing_highs(swings: List[SwingPoint]) -> List[SwingPoint]:
    """Classify swing highs as HH (higher high) or LH (lower high)."""
    for i in range(1, len(swings)):
        if swings[i].price > swings[i - 1].price:
            swings[i].classification = "HH"
        else:
            swings[i].classification = "LH"
    return swings


def _classify_swing_lows(swings: List[SwingPoint]) -> List[SwingPoint]:
    """Classify swing lows as HL (higher low) or LL (lower low)."""
    for i in range(1, len(swings)):
        if swings[i].price > swings[i - 1].price:
            swings[i].classification = "HL"
        else:
            swings[i].classification = "LL"
    return swings


def _analyze_swing_sequence(
    highs: List[SwingPoint],
    lows: List[SwingPoint],
) -> tuple[str, str]:
    """
    Analyze the swing sequence to determine trend.
    
    Returns:
        Tuple of (sequence, direction)
    """
    # Get recent classifications
    recent_high_classes = [s.classification for s in highs[-4:] if s.classification]
    recent_low_classes = [s.classification for s in lows[-4:] if s.classification]
    
    hh_count = recent_high_classes.count("HH")
    lh_count = recent_high_classes.count("LH")
    hl_count = recent_low_classes.count("HL")
    ll_count = recent_low_classes.count("LL")
    
    # Determine pattern
    if hh_count >= 2 and hl_count >= 2:
        return "HH_HL", "bullish"
    elif lh_count >= 2 and ll_count >= 2:
        return "LH_LL", "bearish"
    else:
        return "mixed", "neutral"


def identify_support_resistance_zones(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    swing_analysis: SwingAnalysis,
    atr: float,
    zone_buffer_atr: float = 0.5,
) -> List[StructureZone]:
    """
    Identify support and resistance zones from swing points.
    
    Args:
        high: High prices
        low: Low prices
        close: Close prices
        swing_analysis: Detected swing points
        atr: Current ATR for zone sizing
        zone_buffer_atr: Zone width in ATR units
        
    Returns:
        List of StructureZone
    """
    zones = []
    zone_buffer = atr * zone_buffer_atr
    current_price = float(close.iloc[-1])
    
    # Create resistance zones from swing highs
    for swing in swing_analysis.swing_highs[-10:]:  # Last 10 swings
        zone = StructureZone(
            upper_bound=swing.price + zone_buffer,
            lower_bound=swing.price - zone_buffer,
            type="resistance",
            strength=_calculate_zone_strength(swing, close, high, low),
            timeframe="M30",
            is_fresh=swing.price > current_price,
        )
        zones.append(zone)
    
    # Create support zones from swing lows
    for swing in swing_analysis.swing_lows[-10:]:
        zone = StructureZone(
            upper_bound=swing.price + zone_buffer,
            lower_bound=swing.price - zone_buffer,
            type="support",
            strength=_calculate_zone_strength(swing, close, high, low),
            timeframe="M30",
            is_fresh=swing.price < current_price,
        )
        zones.append(zone)
    
    # Merge overlapping zones and count touches
    zones = _merge_overlapping_zones(zones)
    zones = _count_zone_touches(zones, high, low)
    
    return zones


def _calculate_zone_strength(
    swing: SwingPoint,
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
) -> float:
    """Calculate zone strength based on swing characteristics."""
    # Base strength on swing classification
    strength = 0.5
    
    if swing.classification in ["HH", "LL"]:
        strength += 0.2  # Trend-confirming swings are stronger
    
    # Recency bonus
    recency = (len(close) - swing.index) / len(close)
    if recency < 0.2:  # Recent swing
        strength += 0.1
    
    return min(strength, 1.0)


def _merge_overlapping_zones(zones: List[StructureZone]) -> List[StructureZone]:
    """Merge overlapping zones of the same type."""
    if not zones:
        return zones
    
    # Sort by type and lower bound
    support_zones = sorted(
        [z for z in zones if z.type == "support"],
        key=lambda z: z.lower_bound
    )
    resistance_zones = sorted(
        [z for z in zones if z.type == "resistance"],
        key=lambda z: z.lower_bound
    )
    
    merged = []
    
    for zone_list in [support_zones, resistance_zones]:
        if not zone_list:
            continue
        
        current = zone_list[0]
        for zone in zone_list[1:]:
            if zone.lower_bound <= current.upper_bound:
                # Overlapping - merge
                current = StructureZone(
                    upper_bound=max(current.upper_bound, zone.upper_bound),
                    lower_bound=min(current.lower_bound, zone.lower_bound),
                    type=current.type,
                    strength=max(current.strength, zone.strength),
                    touch_count=current.touch_count + zone.touch_count,
                    is_fresh=current.is_fresh and zone.is_fresh,
                    timeframe=current.timeframe,
                )
            else:
                merged.append(current)
                current = zone
        merged.append(current)
    
    return merged


def _count_zone_touches(
    zones: List[StructureZone],
    high: pd.Series,
    low: pd.Series,
) -> List[StructureZone]:
    """Count how many times price has touched each zone."""
    for zone in zones:
        touches = 0
        for i in range(len(high)):
            h = float(high.iloc[i])
            l = float(low.iloc[i])
            
            # Check if bar touched the zone
            if zone.lower_bound <= h and l <= zone.upper_bound:
                touches += 1
        
        zone.touch_count = max(1, touches)
        
        # Update strength based on touches
        if touches >= 3:
            zone.strength = min(zone.strength + 0.2, 1.0)
    
    return zones


def detect_break_of_structure(
    close: pd.Series,
    swing_analysis: SwingAnalysis,
) -> Optional[StructuralEvent]:
    """
    Detect Break of Structure (BOS).
    
    BOS occurs when price breaks a significant swing point.
    """
    if not swing_analysis.swing_highs or not swing_analysis.swing_lows:
        return None
    
    current_price = float(close.iloc[-1])
    prev_price = float(close.iloc[-2])
    
    # Check for bullish BOS (break above recent swing high)
    for swing in reversed(swing_analysis.swing_highs[-3:]):
        if prev_price < swing.price and current_price > swing.price:
            return StructuralEvent(
                event_type="bos",
                timestamp=close.index[-1] if hasattr(close.index, '__getitem__') else datetime.now(),
                price=swing.price,
                significance=swing.significance,
                description=f"Bullish BOS: Price broke above swing high at {swing.price:.5f}",
            )
    
    # Check for bearish BOS (break below recent swing low)
    for swing in reversed(swing_analysis.swing_lows[-3:]):
        if prev_price > swing.price and current_price < swing.price:
            return StructuralEvent(
                event_type="bos",
                timestamp=close.index[-1] if hasattr(close.index, '__getitem__') else datetime.now(),
                price=swing.price,
                significance=swing.significance,
                description=f"Bearish BOS: Price broke below swing low at {swing.price:.5f}",
            )
    
    return None
