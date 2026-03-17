"""
Strategy Selection Agent - Tactician
Strategy template matching, qualification, and selection
"""

import os
import sys
import json
import asyncio
import httpx
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from dataclasses import dataclass

# Add shared module to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared import (
    call_claude,
    get_agent_url,
    fetch_json,
    post_json,
    FOREX_SYMBOLS,
    ChatRequest,
)

app = FastAPI(title="Tactician - Strategy Selection Agent", version="2.0")

AGENT_NAME = "Tactician"
CURATOR_URL = get_agent_url("curator")
TECHNICAL_URL = get_agent_url("atlas")
STRUCTURE_URL = get_agent_url("architect")
MACRO_URL = get_agent_url("oracle")
NEWS_URL = get_agent_url("sentinel")
SENTIMENT_URL = get_agent_url("pulse")
REGIME_URL = get_agent_url("compass")
ORCHESTRATOR_URL = get_agent_url("orchestrator")

SYMBOLS = FOREX_SYMBOLS

# Strategy cache
strategy_data: Dict[str, dict] = {}

# Using ChatRequest from shared module

# ═══════════════════════════════════════════════════════════════
# STRATEGY TEMPLATES
# ═══════════════════════════════════════════════════════════════

STRATEGY_TEMPLATES = {
    "TREND_CONTINUATION": {
        "name": "Trend Continuation",
        "description": "Trade with established trend on pullback completion",
        "allowed_regimes": ["trending", "high_vol_expansion"],
        "invalid_regimes": ["range_bound", "mean_reverting", "unstable_noisy", "event_driven"],
        "required_confluence": ["trend_grade_b_plus", "structure_confirms", "macro_aligns", "no_news_2h"],
        "max_spread_pips": 2.0,
        "min_atr_pct": 30,
        "min_structure_quality": 60,
        "macro_compatibility": "must_align",
        "sentiment_rule": "not_overcrowded",
        "min_trend_grade": "B",
    },
    "PULLBACK_IN_TREND": {
        "name": "Pullback Entry",
        "description": "Enter on confirmed pullback in strong trend",
        "allowed_regimes": ["trending"],
        "invalid_regimes": ["range_bound", "breakout_ready", "unstable_noisy", "event_driven"],
        "required_confluence": ["trend_grade_a_b", "price_at_structure", "rsi_pullback_zone"],
        "max_spread_pips": 1.5,
        "min_atr_pct": 40,
        "min_structure_quality": 70,
        "macro_compatibility": "must_align",
        "sentiment_rule": "any",
        "min_trend_grade": "B",
    },
    "BREAKOUT": {
        "name": "Breakout Trade",
        "description": "Trade confirmed break of consolidation",
        "allowed_regimes": ["breakout_ready", "range_bound"],
        "invalid_regimes": ["trending", "mean_reverting", "unstable_noisy"],
        "required_confluence": ["consolidation_pattern", "bollinger_squeeze", "volume_expansion"],
        "max_spread_pips": 3.0,
        "min_atr_pct": 25,
        "min_structure_quality": 75,
        "macro_compatibility": "prefer_align",
        "sentiment_rule": "not_overcrowded",
        "min_trend_grade": "D",
    },
    "RANGE_FADE": {
        "name": "Range Fade",
        "description": "Fade moves to range boundaries",
        "allowed_regimes": ["range_bound", "mean_reverting"],
        "invalid_regimes": ["trending", "breakout_ready", "high_vol_expansion", "unstable_noisy"],
        "required_confluence": ["clear_range", "price_at_extreme", "rsi_divergence"],
        "max_spread_pips": 1.5,
        "min_atr_pct": 20,
        "min_structure_quality": 80,
        "macro_compatibility": "any",
        "sentiment_rule": "contrarian_preferred",
        "min_trend_grade": "F",
    },
    "FAILED_BREAKOUT_REVERSAL": {
        "name": "Failed Breakout Reversal",
        "description": "Fade false breakouts that trap traders",
        "allowed_regimes": ["range_bound", "mean_reverting", "breakout_ready"],
        "invalid_regimes": ["trending", "high_vol_expansion"],
        "required_confluence": ["breakout_attempt", "quick_rejection", "trapped_traders"],
        "max_spread_pips": 2.0,
        "min_atr_pct": 30,
        "min_structure_quality": 70,
        "macro_compatibility": "prefer_oppose",
        "sentiment_rule": "crowded_opposite",
        "min_trend_grade": "D",
    },
    "VOLATILITY_EXPANSION": {
        "name": "Volatility Expansion",
        "description": "Trade initial move when volatility expands",
        "allowed_regimes": ["high_vol_expansion", "breakout_ready"],
        "invalid_regimes": ["low_vol_drift", "unstable_noisy"],
        "required_confluence": ["atr_expanding", "clear_direction", "structure_break"],
        "max_spread_pips": 4.0,
        "min_atr_pct": 150,
        "min_structure_quality": 50,
        "macro_compatibility": "any",
        "sentiment_rule": "any",
        "min_trend_grade": "C",
    },
    "SESSION_OPEN_DRIVE": {
        "name": "Session Open Drive",
        "description": "Trade London or NY session opening momentum",
        "allowed_regimes": ["trending", "breakout_ready"],
        "invalid_regimes": ["unstable_noisy", "event_driven"],
        "required_confluence": ["session_window", "prior_session_range", "direction_aligns_htf"],
        "max_spread_pips": 2.0,
        "min_atr_pct": 40,
        "min_structure_quality": 60,
        "macro_compatibility": "prefer_align",
        "sentiment_rule": "any",
        "min_trend_grade": "C",
        "session_windows": ["london", "new_york"],
    },
    "EVENT_BREAKOUT": {
        "name": "Event Breakout",
        "description": "Trade breakout on high-impact news (EXPERTS ONLY)",
        "allowed_regimes": ["event_driven"],
        "invalid_regimes": ["all_other"],
        "required_confluence": ["high_impact_event", "pre_event_range", "risk_accepted"],
        "max_spread_pips": 5.0,
        "min_atr_pct": 50,
        "min_structure_quality": 50,
        "macro_compatibility": "event_overrides",
        "sentiment_rule": "any",
        "min_trend_grade": "F",
        "enabled": False,  # Must be explicitly enabled
    },
}

TREND_GRADES = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}

# Using fetch_json from shared module for fetch_agent_data


def check_regime_valid(strategy: dict, regime: str) -> tuple[bool, str]:
    """Check if regime is valid for strategy."""
    if regime in strategy.get("invalid_regimes", []):
        return False, f"Regime {regime} is invalid"
    if regime not in strategy.get("allowed_regimes", []):
        return False, f"Regime {regime} not in allowed list"
    return True, "Regime valid"


def check_spread(strategy: dict, spread: float, is_cross_pair: bool = False, is_exotic: bool = False) -> tuple[bool, str]:
    """
    Check spread requirement.
    
    Cross pairs (GBPJPY, EURJPY, etc.) naturally have wider spreads.
    Exotics have even wider spreads.
    """
    base_max_spread = strategy.get("max_spread_pips", 3.0)
    
    # Apply multipliers for non-major pairs
    if is_exotic:
        max_spread = base_max_spread * 4.0  # 4x for exotics
        pair_type = "exotic"
    elif is_cross_pair:
        max_spread = base_max_spread * 2.5  # 2.5x for crosses (e.g., 1.5 → 3.75 for GBPJPY)
        pair_type = "cross"
    else:
        max_spread = base_max_spread
        pair_type = "major"
    
    if spread > max_spread:
        return False, f"Spread {spread:.1f} > max {max_spread:.1f} ({pair_type})"
    return True, f"Spread {spread:.1f} ≤ {max_spread:.1f} ({pair_type})"


def check_structure_quality(strategy: dict, quality: int) -> tuple[bool, str]:
    """Check structure quality requirement."""
    min_quality = strategy.get("min_structure_quality", 50)
    if quality < min_quality:
        return False, f"Structure quality {quality}% < min {min_quality}%"
    return True, f"Structure quality {quality}% ≥ {min_quality}%"


def check_trend_grade(strategy: dict, grade: str) -> tuple[bool, str]:
    """Check trend grade requirement."""
    min_grade = strategy.get("min_trend_grade", "F")
    grade_score = TREND_GRADES.get(grade, 1)
    min_score = TREND_GRADES.get(min_grade, 1)
    if grade_score < min_score:
        return False, f"Trend grade {grade} < min {min_grade}"
    return True, f"Trend grade {grade} ≥ {min_grade}"


def check_macro_alignment(strategy: dict, macro_bias: str, direction: str) -> tuple[bool, str]:
    """Check macro compatibility."""
    rule = strategy.get("macro_compatibility", "any")
    if rule == "any":
        return True, "Macro: any allowed"
    if rule == "must_align":
        if macro_bias == direction or macro_bias == "neutral":
            return True, f"Macro aligns ({macro_bias})"
        return False, f"Macro doesn't align ({macro_bias} vs {direction})"
    if rule == "prefer_align":
        if macro_bias == direction:
            return True, f"Macro aligns ({macro_bias})"
        return True, f"Macro neutral (preferred align)"  # Not required
    return True, "Macro check passed"


def check_sentiment(strategy: dict, sentiment_class: str, retail_long: int) -> tuple[bool, str]:
    """Check sentiment compatibility."""
    rule = strategy.get("sentiment_rule", "any")
    if rule == "any":
        return True, "Sentiment: any allowed"
    if rule == "not_overcrowded":
        if sentiment_class == "overcrowded":
            return False, f"Sentiment overcrowded ({retail_long}% one-sided)"
        return True, f"Sentiment not overcrowded"
    if rule == "contrarian_preferred":
        if sentiment_class == "contrarian_opportunity":
            return True, "Contrarian opportunity detected"
        return True, "Sentiment acceptable"
    return True, "Sentiment check passed"


def check_session_window(strategy: dict, session: str) -> tuple[bool, str]:
    """Check session window for session-based strategies."""
    windows = strategy.get("session_windows", [])
    if not windows:
        return True, "No session restriction"
    session_lower = session.lower()
    for w in windows:
        if w.lower() in session_lower:
            return True, f"In {session} session window"
    return False, f"Not in session window ({session})"


def check_atr_requirement(strategy: dict, atr_pct: float) -> tuple[bool, str]:
    """Check ATR percentage requirement."""
    min_atr = strategy.get("min_atr_pct", 20)
    if atr_pct < min_atr:
        return False, f"ATR {atr_pct:.0f}% < min {min_atr}%"
    return True, f"ATR {atr_pct:.0f}% ≥ {min_atr}%"


# ═══════════════════════════════════════════════════════════════
# STRATEGY-SPECIFIC DIRECTION LOGIC
# ═══════════════════════════════════════════════════════════════

# Strategies that use contrarian/zone-based direction
CONTRARIAN_STRATEGIES = ["RANGE_FADE", "FAILED_BREAKOUT_REVERSAL"]
TREND_STRATEGIES = ["TREND_CONTINUATION", "PULLBACK_IN_TREND", "SESSION_OPEN_DRIVE"]
BREAKOUT_STRATEGIES = ["BREAKOUT", "VOLATILITY_EXPANSION", "EVENT_BREAKOUT"]


def check_price_at_zone(price: float, zones: List[dict], atr: float = 0, proximity_pct: float = 0.003) -> dict:
    """
    Check if price is near a support or resistance zone.
    
    Args:
        price: Current price
        zones: List of zones from Architect (each has: price, type, upper, lower)
        atr: ATR value for ATR-based proximity (preferred over percentage)
        proximity_pct: Fallback - how close price must be to zone (default 0.3%)
    
    Returns:
        {at_zone: bool, zone_type: str, zone_price: float, distance_pct: float, distance_atr: float}
    """
    if not zones:
        return {"at_zone": False, "zone_type": None, "zone_price": 0, "distance_pct": 999, "distance_atr": 999}
    
    closest_zone = None
    closest_distance = float('inf')
    closest_distance_atr = float('inf')
    
    for zone in zones:
        zone_price = zone.get("price", 0)
        if zone_price == 0:
            continue
        
        # Skip broken zones
        if zone.get("freshness") == "broken":
            continue
        
        distance = abs(price - zone_price)
        distance_pct = distance / price if price > 0 else 999
        distance_atr = distance / atr if atr > 0 else 999
        
        if distance < closest_distance:
            closest_distance = distance
            closest_distance_atr = distance_atr
            closest_zone = zone
    
    # Use ATR-based proximity if ATR provided, otherwise use percentage
    # "At zone" if within 0.5 ATR or within 0.3%
    at_zone = False
    if atr > 0:
        at_zone = closest_distance_atr <= 0.5  # Within 0.5 ATR of zone
    else:
        at_zone = (closest_distance / price if price > 0 else 999) <= proximity_pct
    
    if closest_zone and at_zone:
        return {
            "at_zone": True,
            "zone_type": closest_zone.get("type", "unknown"),
            "zone_price": closest_zone.get("price", 0),
            "distance_pct": round((closest_distance / price * 100) if price > 0 else 999, 3),
            "distance_atr": round(closest_distance_atr, 2),
            "freshness": closest_zone.get("freshness", "unknown"),
        }
    
    return {
        "at_zone": False, 
        "zone_type": None, 
        "zone_price": 0, 
        "distance_pct": round((closest_distance / price * 100) if price > 0 else 999, 3),
        "distance_atr": round(closest_distance_atr, 2) if closest_distance_atr != float('inf') else 999
    }


def check_rsi_divergence(rsi: float, direction: str, price_trend: str) -> tuple[bool, str]:
    """
    Check for RSI divergence that supports a fade trade.
    
    Bullish divergence: Price making lower lows, RSI making higher lows (buy signal)
    Bearish divergence: Price making higher highs, RSI making lower highs (sell signal)
    
    Simplified: If RSI is extreme AND we're fading, that's confirmation
    """
    if direction == "bullish":
        # We want to go long - RSI oversold is confirmation
        if rsi < 35:
            return True, f"RSI oversold ({rsi:.0f}) confirms long"
        elif rsi > 65:
            return False, f"RSI overbought ({rsi:.0f}) contradicts long"
        return True, f"RSI neutral ({rsi:.0f})"
    
    elif direction == "bearish":
        # We want to go short - RSI overbought is confirmation
        if rsi > 65:
            return True, f"RSI overbought ({rsi:.0f}) confirms short"
        elif rsi < 35:
            return False, f"RSI oversold ({rsi:.0f}) contradicts short"
        return True, f"RSI neutral ({rsi:.0f})"
    
    return True, "RSI check skipped"


def determine_strategy_direction(
    strategy_id: str,
    technical_direction: str,  # From Atlas Jr.
    structure_data: dict,
    price: float,
    regime: str,
    atr: float = 0,
    rsi: float = 50
) -> tuple[str, str, dict]:
    """
    Determine direction based on strategy type.
    
    Different strategies need different direction logic:
    - Trend strategies: Follow Atlas Jr.'s directional_lean
    - Range strategies: Fade the zones (contrarian)
    - Breakout strategies: Follow the break direction
    
    Returns:
        (direction: str, reason: str, zone_info: dict)
    """
    
    # Get structure info
    key_zones = structure_data.get("key_zones", []) if structure_data else []
    structural_bias = structure_data.get("structural_bias", "neutral") if structure_data else "neutral"
    empty_zone_info = {"at_zone": False, "zone_type": None, "zone_price": 0}
    
    # ═══ TREND STRATEGIES ═══
    # Use Atlas Jr.'s directional_lean
    if strategy_id in TREND_STRATEGIES:
        if technical_direction in ["bullish", "bearish"]:
            return technical_direction, f"Trend direction from Atlas Jr. ({technical_direction})", empty_zone_info
        # Fallback to structural bias
        if structural_bias in ["bullish", "bearish"]:
            return structural_bias, f"Fallback to structural bias ({structural_bias})", empty_zone_info
        return "neutral", "No clear trend direction", empty_zone_info
    
    # ═══ CONTRARIAN/RANGE STRATEGIES ═══
    # Determine direction by fading the nearest zone
    if strategy_id in CONTRARIAN_STRATEGIES:
        # Use ATR-based proximity (0.5 ATR from zone = "at zone")
        zone_check = check_price_at_zone(price, key_zones, atr=atr, proximity_pct=0.005)
        
        if zone_check["at_zone"]:
            zone_type = zone_check["zone_type"]
            zone_price = zone_check["zone_price"]
            distance_atr = zone_check.get("distance_atr", 0)
            
            if zone_type == "resistance":
                # At resistance → SHORT (fade it)
                direction = "bearish"
                # Check RSI for confirmation
                rsi_ok, rsi_msg = check_rsi_divergence(rsi, direction, "")
                if rsi_ok:
                    return direction, f"FADE: At resistance {zone_price:.5f} ({distance_atr:.1f} ATR) → SHORT | {rsi_msg}", zone_check
                else:
                    # RSI contradicts - still take the trade but note it
                    return direction, f"FADE: At resistance {zone_price:.5f} → SHORT (⚠️ {rsi_msg})", zone_check
                    
            elif zone_type == "support":
                # At support → LONG (fade it)
                direction = "bullish"
                # Check RSI for confirmation
                rsi_ok, rsi_msg = check_rsi_divergence(rsi, direction, "")
                if rsi_ok:
                    return direction, f"FADE: At support {zone_price:.5f} ({distance_atr:.1f} ATR) → LONG | {rsi_msg}", zone_check
                else:
                    return direction, f"FADE: At support {zone_price:.5f} → LONG (⚠️ {rsi_msg})", zone_check
        
        # Not at any zone - check if we're in the middle of a range
        if regime in ["range_bound", "mean_reverting"]:
            dist_atr = zone_check.get('distance_atr', 999)
            return "neutral", f"In range but not at zone ({dist_atr:.1f} ATR away, need <0.5)", empty_zone_info
        
        return "neutral", "Not at a key zone for range fade", empty_zone_info
    
    # ═══ BREAKOUT STRATEGIES ═══
    # Follow Atlas Jr. direction but require structure break confirmation
    if strategy_id in BREAKOUT_STRATEGIES:
        if technical_direction in ["bullish", "bearish"]:
            return technical_direction, f"Breakout direction from Atlas Jr. ({technical_direction})", empty_zone_info
        if structural_bias in ["bullish", "bearish"]:
            return structural_bias, f"Breakout direction from structure ({structural_bias})", empty_zone_info
        return "neutral", "No clear breakout direction", empty_zone_info
    
    # ═══ DEFAULT ═══
    if technical_direction in ["bullish", "bearish"]:
        return technical_direction, f"Default: Atlas Jr. direction ({technical_direction})", empty_zone_info
    return "neutral", "No direction available", empty_zone_info


def calculate_entry_parameters(strategy_name: str, direction: str, price: float, 
                               atr: float, structure: dict, zone_info: dict = None) -> dict:
    """
    Calculate entry, stop, and target parameters.
    
    For RANGE trades: Use zone boundaries for TP
    For TREND trades: Use ATR multiples
    For PULLBACK trades: Use EMA levels for limit orders
    """
    is_long = direction.lower() == "bullish"
    is_range_strategy = strategy_name in CONTRARIAN_STRATEGIES
    
    # Initialize defaults
    entry_type = "market"
    pullback_level = None
    entry = price
    stop = 0
    tp1 = 0
    tp2 = 0
    
    # Get key zones from structure
    key_zones = structure.get("key_zones", []) if structure else []
    fvgs = structure.get("fvgs", []) if structure else []
    
    # Separate support and resistance zones (non-broken)
    supports = [z for z in key_zones if z.get("type") == "support" and z.get("freshness") != "broken"]
    resistances = [z for z in key_zones if z.get("type") == "resistance" and z.get("freshness") != "broken"]
    
    # Sort by distance from price
    supports.sort(key=lambda z: abs(z.get("price", 0) - price))
    resistances.sort(key=lambda z: abs(z.get("price", 0) - price))
    
    # ═══ RANGE/CONTRARIAN STRATEGY TARGETS ═══
    if is_range_strategy and zone_info and zone_info.get("at_zone"):
        entry = price
        zone_type = zone_info.get("zone_type")
        entry_zone_price = zone_info.get("zone_price", price)
        
        if is_long:
            # Long at support → TP at resistance
            # Stop below the support zone
            stop = entry_zone_price - (atr * 0.5)  # Tight stop just below zone
            
            # TP1: First resistance or midpoint
            if resistances:
                tp1 = resistances[0].get("price", price + atr)
            else:
                tp1 = price + atr  # Fallback
            
            # TP2: Further resistance or FVG
            if len(resistances) > 1:
                tp2 = resistances[1].get("price", tp1 + atr)
            elif fvgs:
                bearish_fvgs = [f for f in fvgs if f.get("type") == "bearish" and f.get("upper", 0) > price]
                if bearish_fvgs:
                    tp2 = bearish_fvgs[0].get("lower", tp1 + atr * 0.5)
                else:
                    tp2 = tp1 + atr * 0.5
            else:
                tp2 = tp1 + atr * 0.5
                
        else:
            # Short at resistance → TP at support
            # Stop above the resistance zone
            stop = entry_zone_price + (atr * 0.5)  # Tight stop just above zone
            
            # TP1: First support or midpoint
            if supports:
                tp1 = supports[0].get("price", price - atr)
            else:
                tp1 = price - atr  # Fallback
            
            # TP2: Further support or FVG
            if len(supports) > 1:
                tp2 = supports[1].get("price", tp1 - atr)
            elif fvgs:
                bullish_fvgs = [f for f in fvgs if f.get("type") == "bullish" and f.get("lower", 999) < price]
                if bullish_fvgs:
                    tp2 = bullish_fvgs[0].get("upper", tp1 - atr * 0.5)
                else:
                    tp2 = tp1 - atr * 0.5
            else:
                tp2 = tp1 - atr * 0.5
    
    # ═══ TREND STRATEGY TARGETS ═══
    else:
        # Get EMA values from structure (if available)
        ema21 = structure.get("ema21", 0) if structure else 0
        ema50 = structure.get("ema50", 0) if structure else 0
        
        # Determine if this is a PULLBACK strategy
        is_pullback_strategy = strategy_name == "PULLBACK_IN_TREND"
        
        if is_pullback_strategy and (ema21 > 0 or ema50 > 0):
            # ═══ PULLBACK ENTRY LOGIC ═══
            # Entry at EMA pullback level, not current price
            
            if is_long:
                # Bullish pullback: Price should retrace DOWN to EMA, then enter LONG
                # Use EMA21 as primary pullback level
                pullback_level = ema21 if ema21 > 0 else ema50
                
                # If price is already AT or BELOW the EMA, enter now
                if price <= pullback_level * 1.002:  # Within 0.2% of EMA
                    entry = price  # Already at pullback level
                    entry_type = "market"
                else:
                    # Price is above EMA - set limit order at EMA
                    entry = pullback_level
                    entry_type = "limit"
                
                # Stop below EMA50 or structure support
                if supports and supports[0].get("price", 0) < entry:
                    stop = supports[0].get("price", entry - atr * 2)
                elif ema50 > 0 and ema50 < entry:
                    stop = ema50 - (atr * 0.3)  # Just below EMA50
                else:
                    stop = entry - (atr * 1.5)
                
                # Targets: ATR-based from entry
                tp1 = entry + (atr * 1.5)
                tp2 = entry + (atr * 3.0)
                
            else:
                # Bearish pullback: Price should retrace UP to EMA, then enter SHORT
                pullback_level = ema21 if ema21 > 0 else ema50
                
                # If price is already AT or ABOVE the EMA, enter now
                if price >= pullback_level * 0.998:  # Within 0.2% of EMA
                    entry = price
                    entry_type = "market"
                else:
                    # Price is below EMA - set limit order at EMA
                    entry = pullback_level
                    entry_type = "limit"
                
                # Stop above EMA50 or structure resistance
                if resistances and resistances[0].get("price", 0) > entry:
                    stop = resistances[0].get("price", entry + atr * 2)
                elif ema50 > 0 and ema50 > entry:
                    stop = ema50 + (atr * 0.3)  # Just above EMA50
                else:
                    stop = entry + (atr * 1.5)
                
                # Targets: ATR-based from entry
                tp1 = entry - (atr * 1.5)
                tp2 = entry - (atr * 3.0)
        
        else:
            # ═══ STANDARD TREND ENTRY (market order at current price) ═══
            entry_type = "market"
            stop_distance = atr * 1.5
            tp1_distance = atr * 1.5
            tp2_distance = atr * 3.0
            
            if is_long:
                entry = price
                stop = price - stop_distance
                tp1 = price + tp1_distance
                tp2 = price + tp2_distance
            else:
                entry = price
                stop = price + stop_distance
                tp1 = price - tp1_distance
                tp2 = price - tp2_distance
    
    risk = abs(entry - stop)
    reward1 = abs(tp1 - entry)
    rr_ratio = reward1 / risk if risk > 0 else 0
    
    # Determine pip multiplier (JPY pairs use 100, others use 10000)
    pip_mult = 100 if price > 50 else 10000
    
    return {
        "direction": "LONG" if is_long else "SHORT",
        "entry": round(entry, 5 if pip_mult == 10000 else 3),
        "stop": round(stop, 5 if pip_mult == 10000 else 3),
        "tp1": round(tp1, 5 if pip_mult == 10000 else 3),
        "tp2": round(tp2, 5 if pip_mult == 10000 else 3),
        "risk_pips": round(risk * pip_mult, 1),
        "rr_ratio": round(rr_ratio, 2),
        "target_type": "zone_based" if is_range_strategy else "atr_based",
        "entry_type": entry_type,  # "market" or "limit"
        "pullback_level": round(pullback_level, 5 if pip_mult == 10000 else 3) if pullback_level else None,
    }


async def evaluate_strategies(symbol: str) -> dict:
    """Evaluate all strategies for a symbol."""
    # Fetch data from all agents
    regime_data = await fetch_json(f"{REGIME_URL}/api/regime/{symbol}")
    technical_data = await fetch_json(f"{TECHNICAL_URL}/api/analysis/{symbol}")
    structure_data = await fetch_json(f"{STRUCTURE_URL}/api/structure/{symbol}")
    macro_data = await fetch_json(f"{MACRO_URL}/api/relative/{symbol}")
    sentiment_data = await fetch_json(f"{SENTIMENT_URL}/api/sentiment/{symbol}")
    news_data = await fetch_json(f"{NEWS_URL}/api/risk/{symbol}")
    curator_data = await fetch_json(f"{CURATOR_URL}/api/snapshot/symbol/{symbol}")
    market_data = await fetch_json(f"{CURATOR_URL}/api/market")  # For current prices
    
    # Extract key values
    regime = regime_data.get("primary_regime", "unknown") if regime_data else "unknown"
    trend_grade = technical_data.get("trend_grade", "D") if technical_data else "D"
    structure_quality = structure_data.get("confidence", 50) if structure_data else 50
    macro_bias = macro_data.get("pair_bias", "neutral") if macro_data else "neutral"
    sentiment_class = sentiment_data.get("classification", "neutral") if sentiment_data else "neutral"
    retail_long = sentiment_data.get("retail_positioning", {}).get("long_pct", 50) if sentiment_data else 50
    news_mode = news_data.get("mode", "normal") if news_data else "normal"
    
    # Get price from market data (more reliable than snapshot)
    symbol_market = market_data.get(symbol, {}) if market_data else {}
    price = symbol_market.get("price", 1.0)
    spread = symbol_market.get("spread", curator_data.get("spread_pips", 1.0) if curator_data else 1.0)
    atr = curator_data.get("atr", 0.001) if curator_data else 0.001
    session = curator_data.get("session", "London") if curator_data else "London"
    
    # Estimate ATR percentage (vs typical)
    atr_pct = 50  # Default
    if technical_data and technical_data.get("indicators", {}).get("atr"):
        atr_pct = 50  # Would calculate vs historical
    
    # Get technical direction and RSI from Atlas Jr.
    technical_direction = "neutral"
    rsi = 50.0  # Default neutral
    h1_atr = 0.001  # Default
    
    if technical_data:
        lean = technical_data.get("directional_lean", "neutral")
        if lean in ["bullish", "bearish"]:
            technical_direction = lean
        
        # Get RSI from primary timeframe (H1)
        timeframes = technical_data.get("timeframes", {})
        h1_data = timeframes.get("H1", {})
        h1_indicators = h1_data.get("indicators", {})
        rsi = h1_indicators.get("rsi", 50.0)
        h1_atr = h1_indicators.get("atr", 0.001)
        
        # Get EMA values for pullback entries (EMAs are in separate field)
        h1_emas = h1_data.get("emas", {})
        ema21 = h1_emas.get("ema21", 0)
        ema50 = h1_emas.get("ema50", 0)
    
    # Use H1 ATR for calculations (better than curator ATR)
    if h1_atr > 0:
        atr = h1_atr
    
    # Add EMAs to structure_data for pullback calculations
    if structure_data is None:
        structure_data = {}
    structure_data["ema21"] = ema21 if 'ema21' in dir() else 0
    structure_data["ema50"] = ema50 if 'ema50' in dir() else 0
    
    # Determine if this is a cross pair (for spread tolerance)
    # Cross pairs don't contain USD (e.g., EURAUD, GBPJPY, AUDNZD)
    is_cross_pair = "USD" not in symbol  # e.g., EURAUD, GBPJPY, AUDNZD, EURGBP
    is_exotic = any(x in symbol for x in ["ZAR", "TRY", "MXN", "SEK", "NOK", "PLN"])
    
    # Evaluate each strategy
    evaluated = []
    
    for strat_id, template in STRATEGY_TEMPLATES.items():
        if not template.get("enabled", True):
            evaluated.append({
                "strategy_id": strat_id,
                "name": template["name"],
                "score": 0,
                "qualified": False,
                "rejection_reason": "Strategy disabled",
                "checks": [],
            })
            continue
        
        # ═══ STRATEGY-SPECIFIC DIRECTION ═══
        # Different strategies need different direction logic!
        direction, direction_reason, zone_info = determine_strategy_direction(
            strategy_id=strat_id,
            technical_direction=technical_direction,
            structure_data=structure_data,
            price=price,
            regime=regime,
            atr=atr,
            rsi=rsi
        )
        
        checks = []
        score = 0
        max_score = 0
        
        # Direction check (critical for all strategies)
        if direction == "neutral":
            checks.append({
                "check": "direction", 
                "passed": False, 
                "message": f"No direction: {direction_reason}", 
                "weight": 25
            })
            max_score += 25
            # Don't add score - this is a critical failure
        else:
            checks.append({
                "check": "direction", 
                "passed": True, 
                "message": direction_reason, 
                "weight": 25
            })
            max_score += 25
            score += 25
        
        # Regime check (critical)
        valid, msg = check_regime_valid(template, regime)
        checks.append({"check": "regime", "passed": valid, "message": msg, "weight": 30})
        max_score += 30
        if valid:
            score += 30
        
        # Spread check (with pair type awareness)
        valid, msg = check_spread(template, spread, is_cross_pair=is_cross_pair, is_exotic=is_exotic)
        checks.append({"check": "spread", "passed": valid, "message": msg, "weight": 10})
        max_score += 10
        if valid:
            score += 10
        
        # Structure quality
        valid, msg = check_structure_quality(template, structure_quality)
        checks.append({"check": "structure", "passed": valid, "message": msg, "weight": 15})
        max_score += 15
        if valid:
            score += 15
        
        # Trend grade
        valid, msg = check_trend_grade(template, trend_grade)
        checks.append({"check": "trend_grade", "passed": valid, "message": msg, "weight": 15})
        max_score += 15
        if valid:
            score += 15
        
        # Macro alignment
        valid, msg = check_macro_alignment(template, macro_bias, direction)
        checks.append({"check": "macro", "passed": valid, "message": msg, "weight": 10})
        max_score += 10
        if valid:
            score += 10
        
        # Sentiment
        valid, msg = check_sentiment(template, sentiment_class, retail_long)
        checks.append({"check": "sentiment", "passed": valid, "message": msg, "weight": 10})
        max_score += 10
        if valid:
            score += 10
        
        # ATR
        valid, msg = check_atr_requirement(template, atr_pct)
        checks.append({"check": "atr", "passed": valid, "message": msg, "weight": 5})
        max_score += 5
        if valid:
            score += 5
        
        # Session window (if applicable)
        if template.get("session_windows"):
            valid, msg = check_session_window(template, session)
            checks.append({"check": "session", "passed": valid, "message": msg, "weight": 5})
            max_score += 5
            if valid:
                score += 5
        
        # News check
        if news_mode == "pause":
            checks.append({"check": "news", "passed": False, "message": "Trading paused for news", "weight": 0})
        elif news_mode == "reduced":
            checks.append({"check": "news", "passed": True, "message": "Reduced mode (caution)", "weight": 0})
        else:
            checks.append({"check": "news", "passed": True, "message": "No imminent news", "weight": 0})
        
        # Calculate final score
        final_score = int(score / max_score * 100) if max_score > 0 else 0
        
        # Check if qualified (all critical checks passed)
        critical_passed = all(c["passed"] for c in checks if c["check"] in ["regime", "spread"])
        qualified = critical_passed and final_score >= 60
        
        # Get rejection reason if not qualified
        rejection_reason = None
        if not qualified:
            failed = [c for c in checks if not c["passed"]]
            if failed:
                rejection_reason = failed[0]["message"]
        
        evaluated.append({
            "strategy_id": strat_id,
            "name": template["name"],
            "score": final_score,
            "qualified": qualified,
            "rejection_reason": rejection_reason,
            "checks": checks,
            "direction": direction,  # Store strategy-specific direction
            "direction_reason": direction_reason,
            "zone_info": zone_info,  # Zone info for range strategies
        })
    
    # Sort by score
    evaluated.sort(key=lambda x: x["score"], reverse=True)
    
    # ═══════════════════════════════════════════════════════════════
    # CONFLICT RESOLUTION: Regime determines which direction wins
    # ═══════════════════════════════════════════════════════════════
    
    # Determine regime-appropriate direction
    regime_direction = None
    conflict_detected = False
    
    # Check what directions qualified strategies want
    qualified_directions = set()
    for strat in evaluated:
        if strat.get("qualified") and strat.get("direction") != "neutral":
            qualified_directions.add(strat["direction"])
    
    # Detect conflict: both bullish and bearish qualified
    if "bullish" in qualified_directions and "bearish" in qualified_directions:
        conflict_detected = True
        
        # Regime decides the winner
        if regime in ["range_bound", "mean_reverting"]:
            # In ranging regime: Range strategies win
            # Find direction from range strategies
            for strat in evaluated:
                if strat.get("qualified") and strat["strategy_id"] in CONTRARIAN_STRATEGIES:
                    regime_direction = strat["direction"]
                    break
            conflict_resolution = f"Regime '{regime}' → Range strategies win"
            
        elif regime in ["trending", "high_vol_expansion"]:
            # In trending regime: Trend strategies win
            for strat in evaluated:
                if strat.get("qualified") and strat["strategy_id"] in TREND_STRATEGIES:
                    regime_direction = strat["direction"]
                    break
            conflict_resolution = f"Regime '{regime}' → Trend strategies win"
            
        elif regime in ["breakout_ready"]:
            # Breakout regime: Breakout strategies win
            for strat in evaluated:
                if strat.get("qualified") and strat["strategy_id"] in BREAKOUT_STRATEGIES:
                    regime_direction = strat["direction"]
                    break
            conflict_resolution = f"Regime '{regime}' → Breakout strategies win"
        else:
            # Unknown regime: Use highest scoring
            for strat in evaluated:
                if strat.get("qualified") and strat.get("direction") != "neutral":
                    regime_direction = strat["direction"]
                    break
            conflict_resolution = f"Unknown regime → Highest score wins"
        
        # Mark conflicting strategies as disqualified
        for strat in evaluated:
            if strat.get("qualified") and strat.get("direction") != regime_direction:
                strat["qualified"] = False
                strat["rejection_reason"] = f"Direction conflict: {strat['direction']} blocked by {conflict_resolution}"
                strat["conflict_blocked"] = True
    else:
        conflict_resolution = "No conflict"
    
    # Select best qualified strategy (after conflict resolution)
    selected = None
    for strat in evaluated:
        if strat["qualified"]:
            selected = strat
            break
    
    # Calculate entry parameters if selected
    entry_params = None
    selected_direction = selected.get("direction", "neutral") if selected else "neutral"
    selected_zone_info = selected.get("zone_info", {}) if selected else {}
    if selected and selected_direction != "neutral":
        entry_params = calculate_entry_parameters(
            selected["strategy_id"], selected_direction, price, atr, structure_data or {},
            zone_info=selected_zone_info
        )
    
    return {
        "symbol": symbol,
        "selected_strategy": selected,
        "entry_parameters": entry_params,
        "all_strategies": evaluated,
        "conflict_resolution": {
            "conflict_detected": conflict_detected,
            "resolution": conflict_resolution,
            "winning_direction": regime_direction if conflict_detected else selected_direction,
        },
        "market_context": {
            "regime": regime,
            "trend_grade": trend_grade,
            "technical_direction": technical_direction,  # From Atlas Jr.
            "direction": selected_direction,  # From selected strategy (may differ!)
            "macro_bias": macro_bias,
            "sentiment": sentiment_class,
            "session": session,
            "spread": spread,
            "news_mode": news_mode,
        },
        "timestamp": datetime.utcnow().isoformat(),
    }


async def send_to_orchestrator(symbol: str, analysis: dict):
    """Send strategy selection to Orchestrator using shared post_json."""
    if not analysis.get("selected_strategy"):
        return
    
    await post_json(
        f"{ORCHESTRATOR_URL}/api/ingest",
        {
            "agent_id": "strategy",
            "agent_name": AGENT_NAME,
            "output_type": "signal",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "symbol": symbol,
                "direction": analysis.get("entry_parameters", {}).get("direction", "NEUTRAL"),
                "confidence": analysis["selected_strategy"]["score"] / 100,
                "reason": f"{analysis['selected_strategy']['name']} ({analysis['selected_strategy']['score']}%)",
            },
        }
    )


async def background_analysis():
    """Background strategy evaluation loop."""
    global strategy_data
    
    while True:
        for symbol in SYMBOLS:
            try:
                analysis = await evaluate_strategies(symbol)
                strategy_data[symbol] = analysis
                await send_to_orchestrator(symbol, analysis)
            except Exception as e:
                print(f"[Tactician] Error analyzing {symbol}: {e}")
        
        await asyncio.sleep(60)


# Using shared call_claude - removed duplicate implementation


@app.on_event("startup")
async def startup():
    global strategy_data
    print(f"🚀 {AGENT_NAME} (Strategy Selection Agent) v2.0 starting...")
    
    # Initial analysis
    for symbol in SYMBOLS:
        try:
            strategy_data[symbol] = await evaluate_strategies(symbol)
        except:
            pass
    
    asyncio.create_task(background_analysis())


@app.get("/", response_class=HTMLResponse)
async def home():
    cards_html = ""
    
    for symbol in SYMBOLS:
        s = strategy_data.get(symbol, {})
        selected = s.get("selected_strategy")
        context = s.get("market_context", {})
        entry = s.get("entry_parameters")
        
        if selected:
            strat_name = selected["name"]
            strat_score = selected["score"]
            color = "#22c55e" if strat_score >= 75 else "#f59e0b" if strat_score >= 60 else "#888"
            status_icon = "✅"
        else:
            strat_name = "NO STRATEGY"
            strat_score = 0
            color = "#ef4444"
            status_icon = "❌"
        
        # Entry params
        entry_html = ""
        if entry:
            entry_html = f'''
            <div class="entry-params">
                <div>{entry["direction"]} @ {entry["entry"]}</div>
                <div>SL: {entry["stop"]} | TP: {entry["tp1"]}</div>
                <div>R:R {entry["rr_ratio"]}:1</div>
            </div>
            '''
        
        # Rejection reasons
        rejections = [st for st in s.get("all_strategies", []) if not st["qualified"]][:3]
        rej_html = "".join([f'<div class="rej">❌ {r["name"]}: {r["rejection_reason"]}</div>' for r in rejections])
        
        cards_html += f'''
        <div class="card" style="border-left: 4px solid {color}">
            <div class="card-header">
                <span class="symbol">{symbol}</span>
                <span class="status">{status_icon}</span>
            </div>
            <div class="strategy" style="color:{color}">{strat_name}</div>
            <div class="score">Score: {strat_score}%</div>
            <div class="context">
                Regime: {context.get("regime", "?")} | Grade: {context.get("trend_grade", "?")} | {context.get("direction", "?").upper()}
            </div>
            {entry_html}
            <div class="rejections">{rej_html}</div>
        </div>
        '''
    
    return f'''<!DOCTYPE html>
<html><head>
    <title>♟️ Tactician - Strategy Agent</title>
    <meta http-equiv="refresh" content="30">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, sans-serif; background: #0a0a0f; color: #e0e0e0; padding: 20px; }}
        .header {{ display: flex; align-items: center; gap: 15px; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid #333; }}
        .header h1 {{ color: #a855f7; }}
        .status-badge {{ background: #22c55e20; color: #22c55e; padding: 5px 12px; border-radius: 20px; font-size: 14px; }}
        .grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-bottom: 20px; }}
        .card {{ background: #1a1a24; border-radius: 10px; padding: 15px; }}
        .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
        .symbol {{ font-size: 16px; font-weight: bold; }}
        .strategy {{ font-size: 14px; font-weight: bold; margin-bottom: 5px; }}
        .score {{ font-size: 12px; color: #888; margin-bottom: 8px; }}
        .context {{ font-size: 11px; color: #666; margin-bottom: 8px; }}
        .entry-params {{ background: #0a0a0f; padding: 8px; border-radius: 6px; font-size: 11px; margin-bottom: 8px; }}
        .entry-params div {{ margin: 3px 0; }}
        .rejections {{ font-size: 10px; color: #666; }}
        .rej {{ margin: 3px 0; }}
        .chat-section {{ background: #1a1a24; border-radius: 12px; padding: 20px; }}
        .chat-section h2 {{ color: #a855f7; margin-bottom: 15px; }}
        .chat-messages {{ height: 150px; overflow-y: auto; background: #0a0a0f; border-radius: 8px; padding: 10px; margin-bottom: 10px; }}
        .chat-input {{ display: flex; gap: 10px; }}
        .chat-input input {{ flex: 1; padding: 10px; border-radius: 8px; border: 1px solid #333; background: #0a0a0f; color: #fff; }}
        .chat-input button {{ padding: 10px 20px; background: #a855f7; color: #fff; border: none; border-radius: 8px; cursor: pointer; }}
        .message {{ margin: 8px 0; padding: 8px; border-radius: 6px; font-size: 13px; }}
        .message.user {{ background: #333; margin-left: 20%; }}
        .message.agent {{ background: #3d1a4d; margin-right: 20%; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>♟️ Tactician</h1>
        <span class="status-badge">● SELECTING</span>
        <span style="color: #888; margin-left: auto;">Strategy Selection Agent v2.0</span>
    </div>
    
    <div class="grid">{cards_html}</div>
    
    <div class="chat-section">
        <h2>💬 Ask Tactician</h2>
        <div class="chat-messages" id="messages"></div>
        <div class="chat-input">
            <input type="text" id="input" placeholder="Ask about strategies..." onkeypress="if(event.key==='Enter')sendMessage()">
            <button onclick="sendMessage()">Send</button>
        </div>
    </div>
    <script>
        const CHAT_KEY = 'tactician_chat_history';
        
        function loadChatHistory() {{
            const messages = document.getElementById('messages');
            const history = localStorage.getItem(CHAT_KEY);
            if (history) {{
                messages.innerHTML = history;
                messages.scrollTop = messages.scrollHeight;
            }}
        }}
        
        function saveChatHistory() {{
            const messages = document.getElementById('messages');
            localStorage.setItem(CHAT_KEY, messages.innerHTML);
        }}
        
        function clearChat() {{
            const messages = document.getElementById('messages');
            messages.innerHTML = '';
            localStorage.removeItem(CHAT_KEY);
        }}
        
        async function sendMessage() {{
            const input = document.getElementById('input');
            const messages = document.getElementById('messages');
            const text = input.value.trim();
            if (!text) return;
            messages.innerHTML += `<div style="margin:5px 0;padding:8px 12px;background:#1a1a24;border-radius:8px;font-size:12px">${{text}}</div>`;
            input.value = '';
            messages.scrollTop = messages.scrollHeight;
            saveChatHistory();
            
            try {{
                const response = await fetch('/chat', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{message: text}})
                }});
                const data = await response.json();
                messages.innerHTML += `<div style="margin:5px 0;padding:8px 12px;background:rgba(249,115,22,0.15);border-left:3px solid #f97316;border-radius:8px;font-size:12px">${{data.response.replace(/\\n/g, '<br>')}}</div>`;
            }} catch (e) {{
                messages.innerHTML += `<div style="margin:5px 0;padding:8px 12px;background:rgba(239,68,68,0.15);border-radius:8px;font-size:12px;color:#ef4444">Error: ${{e.message}}</div>`;
            }}
            messages.scrollTop = messages.scrollHeight;
            saveChatHistory();
        }}
        
        document.addEventListener('DOMContentLoaded', loadChatHistory);
    </script>
</body>
</html>'''


@app.post("/chat")
async def chat(request: ChatRequest):
    context = f"Strategy Data:\n{json.dumps(strategy_data, indent=2, default=str)[:6000]}"
    response = await call_claude(request.message, context, agent_name=AGENT_NAME)
    return {"response": response}


@app.get("/api/strategies")
async def get_all_strategies():
    return strategy_data


@app.get("/api/strategy/{symbol}")
async def get_symbol_strategy(symbol: str):
    return strategy_data.get(symbol.upper(), {"error": "Not found"})


@app.get("/api/active")
async def get_active_strategies():
    """Get symbols with active strategy selections."""
    return {s: d for s, d in strategy_data.items() if d.get("selected_strategy")}


@app.get("/api/templates")
async def get_templates():
    """Get all strategy templates."""
    return STRATEGY_TEMPLATES


@app.get("/api/setups/{symbol}")
async def get_setups(symbol: str):
    """Get actionable trade setups with entry/stop/targets for a symbol."""
    # Get full strategy evaluation
    evaluation = await evaluate_strategies(symbol)
    
    if not evaluation or "error" in evaluation:
        return {"symbol": symbol, "setups": [], "error": evaluation.get("error", "No data")}
    
    setups = []
    market_context = evaluation.get("market_context", {})
    
    # Get price from market data and ATR from technical analysis
    market_data = await fetch_json(f"{CURATOR_URL}/api/market")
    technical_data = await fetch_json(f"{TECHNICAL_URL}/api/analysis/{symbol}")
    
    price = 1.0
    atr = 0.001
    
    if market_data and symbol in market_data:
        price = market_data[symbol].get("price", 1.0)
    
    ema21 = 0
    ema50 = 0
    
    if technical_data:
        # Get ATR from primary timeframe indicators
        primary_tf = technical_data.get("timeframes", {}).get("H1", {})
        h1_indicators = primary_tf.get("indicators", {})
        h1_emas = primary_tf.get("emas", {})  # EMAs in separate field
        atr = h1_indicators.get("atr", 0.001)
        ema21 = h1_emas.get("ema21", 0)
        ema50 = h1_emas.get("ema50", 0)
        if atr == 0 or atr is None:
            # Fallback: estimate from price
            atr = price * 0.005  # ~50 pips for majors
    
    # Get structure for invalidation levels
    structure_data = await fetch_json(f"{STRUCTURE_URL}/api/structure/{symbol}")
    
    # Add EMAs to structure_data for pullback calculations
    if structure_data is None:
        structure_data = {}
    structure_data["ema21"] = ema21
    structure_data["ema50"] = ema50
    
    for strategy in evaluation.get("all_strategies", []):
        if not strategy.get("qualified", False):
            continue
        
        # Use the strategy-specific direction we calculated during evaluation
        direction = strategy.get("direction", "neutral")
        direction_reason = strategy.get("direction_reason", "")
        zone_info = strategy.get("zone_info", {})
        
        # Skip if no direction for this strategy
        if direction == "neutral":
            continue
        
        # Calculate entry parameters (with zone info for range strategies)
        entry_params = calculate_entry_parameters(
            strategy["strategy_id"], 
            direction, 
            price, 
            atr, 
            structure_data or {},
            zone_info=zone_info
        )
        
        # Use structure-based invalidation if available
        if structure_data and structure_data.get("invalidation"):
            invalidation = structure_data["invalidation"]
            if direction == "bullish" and invalidation.get("bearish"):
                # For longs, stop below bearish invalidation
                structure_stop = invalidation["bearish"]
                # Use tighter of ATR or structure stop
                if abs(price - structure_stop) < abs(price - entry_params["stop"]):
                    entry_params["stop"] = round(structure_stop, 5)
                    entry_params["risk_pips"] = round(abs(price - structure_stop) * 10000, 1)
            elif direction == "bearish" and invalidation.get("bullish"):
                # For shorts, stop above bullish invalidation
                structure_stop = invalidation["bullish"]
                if abs(structure_stop - price) < abs(entry_params["stop"] - price):
                    entry_params["stop"] = round(structure_stop, 5)
                    entry_params["risk_pips"] = round(abs(structure_stop - price) * 10000, 1)
        
        setups.append({
            "template": strategy["strategy_id"],
            "name": strategy["name"],
            "direction": direction,
            "direction_reason": direction_reason,  # Why this direction was chosen
            "score": strategy["score"],
            "entry": entry_params["entry"],
            "entry_type": entry_params.get("entry_type", "market"),  # "market" or "limit"
            "pullback_level": entry_params.get("pullback_level"),  # EMA level for limit orders
            "stop": entry_params["stop"],
            "targets": [entry_params["tp1"], entry_params["tp2"]],
            "risk_pips": entry_params["risk_pips"],
            "rr_ratio": entry_params["rr_ratio"],
            "target_type": entry_params.get("target_type", "atr_based"),  # zone_based or atr_based
        })
    
    # Sort by score
    setups.sort(key=lambda x: x["score"], reverse=True)
    
    # Get conflict resolution info
    conflict_info = evaluation.get("conflict_resolution", {})
    
    return {
        "symbol": symbol,
        "setups": setups[:3],  # Top 3 setups (all same direction after conflict resolution)
        "conflict_resolution": conflict_info,
        "market_context": market_context,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/api/status")
async def get_status():
    active_count = sum(1 for d in strategy_data.values() if d.get("selected_strategy"))
    return {
        "agent_id": "strategy",
        "name": AGENT_NAME,
        "status": "active",
        "symbols_analyzed": len(strategy_data),
        "active_strategies": active_count,
        "templates_available": len(STRATEGY_TEMPLATES),
        "version": "2.0",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
