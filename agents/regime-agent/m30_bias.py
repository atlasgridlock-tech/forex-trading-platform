"""
M30-Centric Bias Framework
Primary execution decision frame with pluggable level architecture
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any, Protocol
from enum import Enum
from datetime import datetime, time, timedelta
from abc import ABC, abstractmethod


class SessionType(str, Enum):
    SYDNEY = "sydney"
    TOKYO = "tokyo"
    LONDON = "london"
    NEW_YORK = "new_york"
    OVERLAP_LONDON_NY = "overlap_london_ny"
    CLOSED = "closed"


class BiasDirection(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class ZoneType(str, Enum):
    PREMIUM = "premium"      # Above equilibrium, look for sells
    DISCOUNT = "discount"    # Below equilibrium, look for buys
    EQUILIBRIUM = "equilibrium"  # Middle zone, wait


class BoundaryEngagement(str, Enum):
    UPPER_ENGAGED = "upper_engaged"
    LOWER_ENGAGED = "lower_engaged"
    NEITHER = "neither"
    BOTH_TESTED = "both_tested"


# ═══════════════════════════════════════════════════════════════════════════
# LEVEL ARCHITECTURE PROTOCOL (Pluggable Interface)
# ═══════════════════════════════════════════════════════════════════════════

class LevelArchitecture(Protocol):
    """
    Protocol for pluggable level frameworks.
    Implement this interface to create custom level systems.
    """
    
    def calculate_levels(self, candles: List[dict], params: dict) -> dict:
        """Calculate levels from price data."""
        ...
    
    def get_current_zone(self, price: float, levels: dict) -> ZoneType:
        """Determine which zone price is currently in."""
        ...
    
    def get_boundary_engagement(self, candles: List[dict], levels: dict) -> BoundaryEngagement:
        """Determine which boundary was engaged first."""
        ...


# ═══════════════════════════════════════════════════════════════════════════
# BUILT-IN LEVEL FRAMEWORKS
# ═══════════════════════════════════════════════════════════════════════════

class SessionRangeLevels:
    """
    Session-based level architecture.
    Uses Asian session range as structure.
    """
    
    def calculate_levels(self, candles: List[dict], params: dict = None) -> dict:
        """Calculate session range levels."""
        # Find Asian session candles (0:00-8:00 UTC approximately)
        asian_candles = []
        for c in candles:
            ts = c.get("timestamp", "")
            if ts:
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if 0 <= dt.hour < 8:
                        asian_candles.append(c)
                except:
                    pass
        
        if not asian_candles:
            # Fallback to last 16 candles (8 hours of M30)
            asian_candles = candles[-16:] if len(candles) >= 16 else candles
        
        highs = [c.get("high", 0) for c in asian_candles]
        lows = [c.get("low", 0) for c in asian_candles]
        
        session_high = max(highs) if highs else 0
        session_low = min(lows) if lows else 0
        equilibrium = (session_high + session_low) / 2
        
        return {
            "type": "session_range",
            "upper": session_high,
            "lower": session_low,
            "equilibrium": equilibrium,
            "range": session_high - session_low,
            "premium_zone": (equilibrium, session_high),
            "discount_zone": (session_low, equilibrium),
        }
    
    def get_current_zone(self, price: float, levels: dict) -> ZoneType:
        if not levels:
            return ZoneType.EQUILIBRIUM
        
        eq = levels.get("equilibrium", 0)
        upper = levels.get("upper", 0)
        lower = levels.get("lower", 0)
        
        if price > eq + (upper - eq) * 0.2:
            return ZoneType.PREMIUM
        elif price < eq - (eq - lower) * 0.2:
            return ZoneType.DISCOUNT
        else:
            return ZoneType.EQUILIBRIUM
    
    def get_boundary_engagement(self, candles: List[dict], levels: dict) -> BoundaryEngagement:
        if not candles or not levels:
            return BoundaryEngagement.NEITHER
        
        upper = levels.get("upper", 0)
        lower = levels.get("lower", 0)
        
        upper_touched = False
        lower_touched = False
        first_touch = None
        
        for c in candles:
            high = c.get("high", 0)
            low = c.get("low", 0)
            
            if high >= upper * 0.9998 and not upper_touched:  # Within 0.02%
                upper_touched = True
                if first_touch is None:
                    first_touch = "upper"
            
            if low <= lower * 1.0002 and not lower_touched:
                lower_touched = True
                if first_touch is None:
                    first_touch = "lower"
        
        if upper_touched and lower_touched:
            return BoundaryEngagement.BOTH_TESTED
        elif first_touch == "upper":
            return BoundaryEngagement.UPPER_ENGAGED
        elif first_touch == "lower":
            return BoundaryEngagement.LOWER_ENGAGED
        else:
            return BoundaryEngagement.NEITHER


class DailyOpenLevels:
    """
    Daily open-based level architecture.
    Uses daily open as equilibrium with ATR-based bands.
    """
    
    def calculate_levels(self, candles: List[dict], params: dict = None) -> dict:
        # Find daily open (first M30 candle of the day)
        if not candles:
            return {}
        
        # Get today's first candle
        today_candles = []
        current_date = None
        
        for c in reversed(candles):
            ts = c.get("timestamp", "")
            if ts:
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if current_date is None:
                        current_date = dt.date()
                    if dt.date() == current_date:
                        today_candles.insert(0, c)
                    else:
                        break
                except:
                    pass
        
        if not today_candles:
            today_candles = candles[-48:]  # Last 24 hours
        
        daily_open = today_candles[0].get("open", 0) if today_candles else 0
        
        # Calculate ATR for bands
        atr = self._calculate_atr(candles, 14)
        
        return {
            "type": "daily_open",
            "equilibrium": daily_open,
            "upper": daily_open + atr * 1.5,
            "lower": daily_open - atr * 1.5,
            "extreme_upper": daily_open + atr * 2.5,
            "extreme_lower": daily_open - atr * 2.5,
            "atr": atr,
        }
    
    def _calculate_atr(self, candles: List[dict], period: int = 14) -> float:
        if len(candles) < period + 1:
            return 0
        
        trs = []
        for i in range(1, len(candles)):
            high = candles[i].get("high", 0)
            low = candles[i].get("low", 0)
            prev_close = candles[i-1].get("close", 0)
            
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            trs.append(tr)
        
        if len(trs) >= period:
            return sum(trs[-period:]) / period
        return sum(trs) / len(trs) if trs else 0
    
    def get_current_zone(self, price: float, levels: dict) -> ZoneType:
        eq = levels.get("equilibrium", 0)
        upper = levels.get("upper", 0)
        lower = levels.get("lower", 0)
        
        if price > eq + (upper - eq) * 0.3:
            return ZoneType.PREMIUM
        elif price < eq - (eq - lower) * 0.3:
            return ZoneType.DISCOUNT
        else:
            return ZoneType.EQUILIBRIUM
    
    def get_boundary_engagement(self, candles: List[dict], levels: dict) -> BoundaryEngagement:
        # Similar logic to session range
        upper = levels.get("upper", 0)
        lower = levels.get("lower", 0)
        
        for c in candles:
            if c.get("high", 0) >= upper:
                return BoundaryEngagement.UPPER_ENGAGED
            if c.get("low", 0) <= lower:
                return BoundaryEngagement.LOWER_ENGAGED
        
        return BoundaryEngagement.NEITHER


class FibonacciLevels:
    """
    Fibonacci-based level architecture.
    Uses swing high/low with Fib retracements.
    """
    
    FIB_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
    
    def calculate_levels(self, candles: List[dict], params: dict = None) -> dict:
        if not candles:
            return {}
        
        lookback = params.get("lookback", 100) if params else 100
        recent = candles[-lookback:] if len(candles) >= lookback else candles
        
        highs = [c.get("high", 0) for c in recent]
        lows = [c.get("low", 0) for c in recent]
        
        swing_high = max(highs)
        swing_low = min(lows)
        range_size = swing_high - swing_low
        
        # Determine trend direction (is current price closer to high or low?)
        current_price = candles[-1].get("close", 0)
        is_uptrend = current_price > (swing_high + swing_low) / 2
        
        levels = {"type": "fibonacci", "swing_high": swing_high, "swing_low": swing_low}
        
        if is_uptrend:
            # In uptrend, fibs from low to high (retracement levels)
            for fib in self.FIB_LEVELS:
                level = swing_high - (range_size * fib)
                levels[f"fib_{fib}"] = level
        else:
            # In downtrend, fibs from high to low
            for fib in self.FIB_LEVELS:
                level = swing_low + (range_size * fib)
                levels[f"fib_{fib}"] = level
        
        levels["equilibrium"] = levels.get("fib_0.5", (swing_high + swing_low) / 2)
        levels["upper"] = swing_high
        levels["lower"] = swing_low
        
        return levels
    
    def get_current_zone(self, price: float, levels: dict) -> ZoneType:
        fib_618 = levels.get("fib_0.618", 0)
        fib_382 = levels.get("fib_0.382", 0)
        
        if price > fib_382:
            return ZoneType.PREMIUM
        elif price < fib_618:
            return ZoneType.DISCOUNT
        else:
            return ZoneType.EQUILIBRIUM
    
    def get_boundary_engagement(self, candles: List[dict], levels: dict) -> BoundaryEngagement:
        upper = levels.get("upper", 0)
        lower = levels.get("lower", 0)
        
        for c in candles:
            if c.get("high", 0) >= upper * 0.999:
                return BoundaryEngagement.UPPER_ENGAGED
            if c.get("low", 0) <= lower * 1.001:
                return BoundaryEngagement.LOWER_ENGAGED
        
        return BoundaryEngagement.NEITHER


# ═══════════════════════════════════════════════════════════════════════════
# M30 BIAS MODULE
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class M30BiasState:
    """Current M30 bias state."""
    symbol: str
    timestamp: datetime
    
    # Session context
    current_session: SessionType
    session_open_price: float = 0
    daily_open_price: float = 0
    
    # Level architecture
    level_framework: str = "session_range"
    levels: Dict[str, float] = field(default_factory=dict)
    
    # Zone analysis
    current_zone: ZoneType = ZoneType.EQUILIBRIUM
    boundary_engaged: BoundaryEngagement = BoundaryEngagement.NEITHER
    
    # Bias determination
    directional_bias: BiasDirection = BiasDirection.NEUTRAL
    bias_confidence: float = 0  # 0-100
    bias_reason: str = ""
    
    # Trade guidance
    preferred_direction: str = "none"  # long/short/none
    stand_aside: bool = False
    stand_aside_reason: str = ""
    
    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "current_session": self.current_session.value,
            "session_open_price": self.session_open_price,
            "daily_open_price": self.daily_open_price,
            "level_framework": self.level_framework,
            "levels": self.levels,
            "current_zone": self.current_zone.value,
            "boundary_engaged": self.boundary_engaged.value,
            "directional_bias": self.directional_bias.value,
            "bias_confidence": self.bias_confidence,
            "bias_reason": self.bias_reason,
            "preferred_direction": self.preferred_direction,
            "stand_aside": self.stand_aside,
            "stand_aside_reason": self.stand_aside_reason,
        }


class M30BiasModule:
    """
    M30-Centric Bias Framework
    
    Primary execution decision frame that:
    - Defines directional state after key session/daily opening
    - Maps price relative to structural bands
    - Measures which boundary is engaged first
    - Provides bias input for trading decisions
    
    Does NOT:
    - Trade blindly from bias alone
    - Override higher timeframe structure
    - Ignore regime and risk filters
    """
    
    # Session times (UTC)
    SESSION_TIMES = {
        SessionType.SYDNEY: (time(21, 0), time(6, 0)),
        SessionType.TOKYO: (time(0, 0), time(9, 0)),
        SessionType.LONDON: (time(7, 0), time(16, 0)),
        SessionType.NEW_YORK: (time(12, 0), time(21, 0)),
        SessionType.OVERLAP_LONDON_NY: (time(12, 0), time(16, 0)),
    }
    
    def __init__(self):
        # Available level frameworks (pluggable)
        self.level_frameworks: Dict[str, Any] = {
            "session_range": SessionRangeLevels(),
            "daily_open": DailyOpenLevels(),
            "fibonacci": FibonacciLevels(),
        }
        self.active_framework = "session_range"
        self.bias_states: Dict[str, M30BiasState] = {}
    
    def register_level_framework(self, name: str, framework: LevelArchitecture):
        """Register a custom level framework."""
        self.level_frameworks[name] = framework
    
    def set_active_framework(self, name: str):
        """Set the active level framework."""
        if name in self.level_frameworks:
            self.active_framework = name
    
    def get_current_session(self, dt: datetime = None) -> SessionType:
        """Determine current trading session."""
        if dt is None:
            dt = datetime.utcnow()
        
        current_time = dt.time()
        
        # Check overlap first (most specific)
        overlap_start, overlap_end = self.SESSION_TIMES[SessionType.OVERLAP_LONDON_NY]
        if overlap_start <= current_time <= overlap_end:
            return SessionType.OVERLAP_LONDON_NY
        
        # Check other sessions
        for session, (start, end) in self.SESSION_TIMES.items():
            if session == SessionType.OVERLAP_LONDON_NY:
                continue
            
            if start <= end:
                if start <= current_time <= end:
                    return session
            else:  # Wraps around midnight
                if current_time >= start or current_time <= end:
                    return session
        
        return SessionType.CLOSED
    
    def calculate_bias(
        self,
        symbol: str,
        m30_candles: List[dict],
        params: dict = None
    ) -> M30BiasState:
        """
        Calculate M30 bias state.
        
        Args:
            symbol: Trading pair
            m30_candles: M30 candle data
            params: Optional parameters for level calculation
        """
        now = datetime.utcnow()
        
        # Initialize state
        state = M30BiasState(
            symbol=symbol,
            timestamp=now,
            current_session=self.get_current_session(now),
            level_framework=self.active_framework,
        )
        
        if not m30_candles:
            state.stand_aside = True
            state.stand_aside_reason = "No M30 data available"
            self.bias_states[symbol] = state
            return state
        
        current_price = m30_candles[-1].get("close", 0)
        
        # Get session and daily opens
        state.session_open_price = self._get_session_open(m30_candles, state.current_session)
        state.daily_open_price = self._get_daily_open(m30_candles)
        
        # Calculate levels using active framework
        framework = self.level_frameworks.get(self.active_framework)
        if framework:
            state.levels = framework.calculate_levels(m30_candles, params)
            state.current_zone = framework.get_current_zone(current_price, state.levels)
            state.boundary_engaged = framework.get_boundary_engagement(m30_candles[-16:], state.levels)
        
        # Determine directional bias
        state.directional_bias, state.bias_confidence, state.bias_reason = \
            self._determine_bias(current_price, state)
        
        # Set preferred direction
        if state.directional_bias == BiasDirection.BULLISH:
            state.preferred_direction = "long"
        elif state.directional_bias == BiasDirection.BEARISH:
            state.preferred_direction = "short"
        else:
            state.preferred_direction = "none"
        
        # Check for stand-aside conditions
        state.stand_aside, state.stand_aside_reason = self._check_stand_aside(state)
        
        self.bias_states[symbol] = state
        return state
    
    def _get_session_open(self, candles: List[dict], session: SessionType) -> float:
        """Get the opening price for the current session."""
        session_start, _ = self.SESSION_TIMES.get(session, (time(0, 0), time(23, 59)))
        
        for c in candles:
            ts = c.get("timestamp", "")
            if ts:
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if dt.time() >= session_start:
                        return c.get("open", 0)
                except:
                    pass
        
        return candles[0].get("open", 0) if candles else 0
    
    def _get_daily_open(self, candles: List[dict]) -> float:
        """Get the daily opening price."""
        today = datetime.utcnow().date()
        
        for c in candles:
            ts = c.get("timestamp", "")
            if ts:
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if dt.date() == today and dt.hour == 0:
                        return c.get("open", 0)
                except:
                    pass
        
        # Fallback to first candle of available data
        return candles[0].get("open", 0) if candles else 0
    
    def _determine_bias(
        self,
        current_price: float,
        state: M30BiasState
    ) -> tuple:
        """Determine directional bias based on zone, boundary engagement, and price action."""
        bias = BiasDirection.NEUTRAL
        confidence = 0
        reasons = []
        
        # Factor 1: Zone position (40% weight)
        if state.current_zone == ZoneType.DISCOUNT:
            bias = BiasDirection.BULLISH
            confidence += 40
            reasons.append("Price in discount zone")
        elif state.current_zone == ZoneType.PREMIUM:
            bias = BiasDirection.BEARISH
            confidence += 40
            reasons.append("Price in premium zone")
        
        # Factor 2: Boundary engagement (30% weight)
        if state.boundary_engaged == BoundaryEngagement.LOWER_ENGAGED:
            # Lower boundary touched first, bias bullish
            if bias != BiasDirection.BEARISH:
                bias = BiasDirection.BULLISH
                confidence += 30
                reasons.append("Lower boundary engaged first")
        elif state.boundary_engaged == BoundaryEngagement.UPPER_ENGAGED:
            # Upper boundary touched first, bias bearish
            if bias != BiasDirection.BULLISH:
                bias = BiasDirection.BEARISH
                confidence += 30
                reasons.append("Upper boundary engaged first")
        
        # Factor 3: Position relative to session/daily open (30% weight)
        if state.session_open_price > 0:
            if current_price > state.session_open_price * 1.001:  # >0.1% above
                if bias != BiasDirection.BEARISH:
                    bias = BiasDirection.BULLISH if bias == BiasDirection.BULLISH else BiasDirection.NEUTRAL
                    confidence += 15
                    reasons.append("Above session open")
            elif current_price < state.session_open_price * 0.999:
                if bias != BiasDirection.BULLISH:
                    bias = BiasDirection.BEARISH if bias == BiasDirection.BEARISH else BiasDirection.NEUTRAL
                    confidence += 15
                    reasons.append("Below session open")
        
        if state.daily_open_price > 0:
            if current_price > state.daily_open_price * 1.002:
                confidence += 15
                reasons.append("Above daily open")
            elif current_price < state.daily_open_price * 0.998:
                confidence += 15
                reasons.append("Below daily open")
        
        # Cap confidence at 100
        confidence = min(confidence, 100)
        
        # If conflicting signals, reduce confidence
        if len(reasons) >= 3 and bias == BiasDirection.NEUTRAL:
            confidence = max(confidence - 20, 0)
        
        reason = "; ".join(reasons) if reasons else "No clear bias factors"
        
        return bias, confidence, reason
    
    def _check_stand_aside(self, state: M30BiasState) -> tuple:
        """Check if we should stand aside (not trade)."""
        # Stand aside in equilibrium zone with low confidence
        if state.current_zone == ZoneType.EQUILIBRIUM and state.bias_confidence < 50:
            return True, "Price in equilibrium with low confidence"
        
        # Stand aside if boundary engagement conflicts with zone
        if state.current_zone == ZoneType.DISCOUNT and state.boundary_engaged == BoundaryEngagement.UPPER_ENGAGED:
            return True, "Conflicting signals: discount zone but upper boundary engaged"
        
        if state.current_zone == ZoneType.PREMIUM and state.boundary_engaged == BoundaryEngagement.LOWER_ENGAGED:
            return True, "Conflicting signals: premium zone but lower boundary engaged"
        
        # Stand aside outside main sessions
        if state.current_session == SessionType.CLOSED:
            return True, "Markets closed"
        
        return False, ""
    
    def get_trade_guidance(self, symbol: str) -> dict:
        """Get trading guidance based on M30 bias."""
        state = self.bias_states.get(symbol)
        if not state:
            return {
                "symbol": symbol,
                "guidance": "no_data",
                "message": "No M30 bias analysis available",
            }
        
        if state.stand_aside:
            return {
                "symbol": symbol,
                "guidance": "stand_aside",
                "reason": state.stand_aside_reason,
                "session": state.current_session.value,
            }
        
        return {
            "symbol": symbol,
            "guidance": "tradeable",
            "preferred_direction": state.preferred_direction,
            "bias": state.directional_bias.value,
            "confidence": state.bias_confidence,
            "reason": state.bias_reason,
            "zone": state.current_zone.value,
            "session": state.current_session.value,
            "levels": state.levels,
            "note": "Requires confirmation from regime, structure, and risk filters",
        }
