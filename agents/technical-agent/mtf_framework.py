"""
Multi-Timeframe Framework
Clear responsibilities for each timeframe with strict hierarchy
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
from datetime import datetime


class TimeframeRole(str, Enum):
    """Role each timeframe plays in the hierarchy."""
    MACRO_STRUCTURE = "macro_structure"      # D1
    SWING_BIAS = "swing_bias"                # H4
    INTERMEDIATE = "intermediate"            # H1
    DECISION = "decision"                    # M30 (primary)
    PRECISION = "precision"                  # M15/M5


class DirectionalBias(str, Enum):
    STRONGLY_BULLISH = "strongly_bullish"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    STRONGLY_BEARISH = "strongly_bearish"


@dataclass
class TimeframeAnalysis:
    """Analysis for a single timeframe."""
    timeframe: str
    role: TimeframeRole
    bias: DirectionalBias
    confidence: float  # 0-100
    
    # Structure
    trend_direction: str  # bullish/bearish/neutral
    key_high: float = 0
    key_low: float = 0
    current_price: float = 0
    
    # Zones
    nearest_resistance: float = 0
    nearest_support: float = 0
    in_zone: bool = False
    zone_type: str = ""  # demand/supply/none
    
    # Momentum
    momentum: str = "neutral"  # expanding/contracting/neutral
    rsi: float = 50
    
    # Signals
    signal: str = "none"  # buy/sell/none
    signal_strength: float = 0
    
    def to_dict(self) -> dict:
        return {
            "timeframe": self.timeframe,
            "role": self.role.value,
            "bias": self.bias.value,
            "confidence": self.confidence,
            "trend_direction": self.trend_direction,
            "key_high": self.key_high,
            "key_low": self.key_low,
            "nearest_resistance": self.nearest_resistance,
            "nearest_support": self.nearest_support,
            "in_zone": self.in_zone,
            "zone_type": self.zone_type,
            "momentum": self.momentum,
            "signal": self.signal,
        }


@dataclass 
class MTFAlignment:
    """Multi-timeframe alignment assessment."""
    symbol: str
    timestamp: datetime
    
    # Individual TF analyses
    d1: Optional[TimeframeAnalysis] = None
    h4: Optional[TimeframeAnalysis] = None
    h1: Optional[TimeframeAnalysis] = None
    m30: Optional[TimeframeAnalysis] = None  # PRIMARY
    m15: Optional[TimeframeAnalysis] = None
    m5: Optional[TimeframeAnalysis] = None
    
    # Alignment scores
    full_alignment: bool = False
    alignment_score: float = 0  # 0-100
    alignment_direction: str = "neutral"
    
    # Conflicts
    conflicts: List[str] = field(default_factory=list)
    
    # Tradeable assessment
    tradeable: bool = False
    trade_direction: str = "none"
    confidence: float = 0
    
    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "d1": self.d1.to_dict() if self.d1 else None,
            "h4": self.h4.to_dict() if self.h4 else None,
            "h1": self.h1.to_dict() if self.h1 else None,
            "m30": self.m30.to_dict() if self.m30 else None,
            "m15": self.m15.to_dict() if self.m15 else None,
            "m5": self.m5.to_dict() if self.m5 else None,
            "full_alignment": self.full_alignment,
            "alignment_score": self.alignment_score,
            "alignment_direction": self.alignment_direction,
            "conflicts": self.conflicts,
            "tradeable": self.tradeable,
            "trade_direction": self.trade_direction,
            "confidence": self.confidence,
        }


class MTFFramework:
    """
    Multi-Timeframe Analysis Framework
    
    Hierarchy:
    - D1: Macro structure, broad directional map
    - H4: Swing bias, major zones
    - H1: Intermediate alignment  
    - M30: PRIMARY decision frame
    - M15/M5: Precision entry timing
    
    Rules:
    - Lower TF cannot override higher TF structure without explicit logic
    - M30 is the primary execution decision frame
    - All TFs must be considered before entry
    """
    
    # Timeframe weights for alignment scoring
    TF_WEIGHTS = {
        "D1": 0.25,   # 25% - Macro direction
        "H4": 0.25,   # 25% - Swing bias
        "H1": 0.15,   # 15% - Intermediate
        "M30": 0.25,  # 25% - Decision frame (primary)
        "M15": 0.05,  # 5%  - Precision
        "M5": 0.05,   # 5%  - Precision
    }
    
    # Role assignments
    TF_ROLES = {
        "D1": TimeframeRole.MACRO_STRUCTURE,
        "H4": TimeframeRole.SWING_BIAS,
        "H1": TimeframeRole.INTERMEDIATE,
        "M30": TimeframeRole.DECISION,
        "M15": TimeframeRole.PRECISION,
        "M5": TimeframeRole.PRECISION,
    }
    
    def __init__(self):
        self.analyses: Dict[str, MTFAlignment] = {}
    
    def analyze_timeframe(
        self,
        timeframe: str,
        candles: List[dict],
        indicators: dict
    ) -> TimeframeAnalysis:
        """Analyze a single timeframe."""
        if not candles:
            return TimeframeAnalysis(
                timeframe=timeframe,
                role=self.TF_ROLES.get(timeframe, TimeframeRole.PRECISION),
                bias=DirectionalBias.NEUTRAL,
                confidence=0,
                trend_direction="neutral",
            )
        
        # Basic calculations
        current = candles[-1]
        current_price = current.get("close", 0)
        
        # Find swing high/low (last 50 candles)
        recent = candles[-50:] if len(candles) >= 50 else candles
        highs = [c.get("high", 0) for c in recent]
        lows = [c.get("low", 0) for c in recent]
        key_high = max(highs)
        key_low = min(lows)
        
        # Determine trend direction
        if current_price > (key_high + key_low) / 2:
            trend_direction = "bullish"
        elif current_price < (key_high + key_low) / 2:
            trend_direction = "bearish"
        else:
            trend_direction = "neutral"
        
        # Get RSI from indicators
        rsi = indicators.get("rsi", 50)
        
        # Determine momentum
        if rsi > 60:
            momentum = "expanding_bullish"
        elif rsi < 40:
            momentum = "expanding_bearish"
        elif 45 < rsi < 55:
            momentum = "neutral"
        else:
            momentum = "contracting"
        
        # Calculate bias
        bias_score = 0
        if trend_direction == "bullish":
            bias_score += 40
        elif trend_direction == "bearish":
            bias_score -= 40
        
        if rsi > 50:
            bias_score += (rsi - 50)
        else:
            bias_score -= (50 - rsi)
        
        # EMA alignment from indicators
        ema_bullish = indicators.get("ema_bullish", False)
        ema_bearish = indicators.get("ema_bearish", False)
        if ema_bullish:
            bias_score += 20
        elif ema_bearish:
            bias_score -= 20
        
        # Convert score to bias
        if bias_score >= 50:
            bias = DirectionalBias.STRONGLY_BULLISH
        elif bias_score >= 20:
            bias = DirectionalBias.BULLISH
        elif bias_score <= -50:
            bias = DirectionalBias.STRONGLY_BEARISH
        elif bias_score <= -20:
            bias = DirectionalBias.BEARISH
        else:
            bias = DirectionalBias.NEUTRAL
        
        # Confidence based on clarity
        confidence = min(abs(bias_score), 100)
        
        # Signal determination
        signal = "none"
        signal_strength = 0
        if bias in [DirectionalBias.STRONGLY_BULLISH, DirectionalBias.BULLISH] and rsi < 70:
            signal = "buy"
            signal_strength = confidence
        elif bias in [DirectionalBias.STRONGLY_BEARISH, DirectionalBias.BEARISH] and rsi > 30:
            signal = "sell"
            signal_strength = confidence
        
        return TimeframeAnalysis(
            timeframe=timeframe,
            role=self.TF_ROLES.get(timeframe, TimeframeRole.PRECISION),
            bias=bias,
            confidence=confidence,
            trend_direction=trend_direction,
            key_high=key_high,
            key_low=key_low,
            current_price=current_price,
            momentum=momentum,
            rsi=rsi,
            signal=signal,
            signal_strength=signal_strength,
        )
    
    def calculate_alignment(
        self,
        symbol: str,
        d1: TimeframeAnalysis,
        h4: TimeframeAnalysis,
        h1: TimeframeAnalysis,
        m30: TimeframeAnalysis,
        m15: Optional[TimeframeAnalysis] = None,
        m5: Optional[TimeframeAnalysis] = None,
    ) -> MTFAlignment:
        """Calculate multi-timeframe alignment."""
        alignment = MTFAlignment(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            d1=d1,
            h4=h4,
            h1=h1,
            m30=m30,
            m15=m15,
            m5=m5,
        )
        
        # Collect biases
        biases = {
            "D1": d1.bias if d1 else DirectionalBias.NEUTRAL,
            "H4": h4.bias if h4 else DirectionalBias.NEUTRAL,
            "H1": h1.bias if h1 else DirectionalBias.NEUTRAL,
            "M30": m30.bias if m30 else DirectionalBias.NEUTRAL,
        }
        if m15:
            biases["M15"] = m15.bias
        if m5:
            biases["M5"] = m5.bias
        
        # Check for conflicts
        conflicts = []
        
        # Rule: Lower TF cannot override higher TF without explicit logic
        if d1 and m30:
            d1_bullish = d1.bias in [DirectionalBias.BULLISH, DirectionalBias.STRONGLY_BULLISH]
            m30_bullish = m30.bias in [DirectionalBias.BULLISH, DirectionalBias.STRONGLY_BULLISH]
            d1_bearish = d1.bias in [DirectionalBias.BEARISH, DirectionalBias.STRONGLY_BEARISH]
            m30_bearish = m30.bias in [DirectionalBias.BEARISH, DirectionalBias.STRONGLY_BEARISH]
            
            if (d1_bullish and m30_bearish) or (d1_bearish and m30_bullish):
                conflicts.append("D1 vs M30 directional conflict")
        
        if h4 and m30:
            h4_bullish = h4.bias in [DirectionalBias.BULLISH, DirectionalBias.STRONGLY_BULLISH]
            m30_bullish = m30.bias in [DirectionalBias.BULLISH, DirectionalBias.STRONGLY_BULLISH]
            h4_bearish = h4.bias in [DirectionalBias.BEARISH, DirectionalBias.STRONGLY_BEARISH]
            m30_bearish = m30.bias in [DirectionalBias.BEARISH, DirectionalBias.STRONGLY_BEARISH]
            
            if (h4_bullish and m30_bearish) or (h4_bearish and m30_bullish):
                conflicts.append("H4 vs M30 directional conflict")
        
        alignment.conflicts = conflicts
        
        # Calculate alignment score
        bullish_score = 0
        bearish_score = 0
        total_weight = 0
        
        for tf, bias in biases.items():
            weight = self.TF_WEIGHTS.get(tf, 0.05)
            total_weight += weight
            
            if bias in [DirectionalBias.STRONGLY_BULLISH]:
                bullish_score += weight * 100
            elif bias in [DirectionalBias.BULLISH]:
                bullish_score += weight * 60
            elif bias in [DirectionalBias.STRONGLY_BEARISH]:
                bearish_score += weight * 100
            elif bias in [DirectionalBias.BEARISH]:
                bearish_score += weight * 60
        
        # Normalize
        bullish_score = bullish_score / total_weight if total_weight > 0 else 0
        bearish_score = bearish_score / total_weight if total_weight > 0 else 0
        
        # Determine overall alignment
        if bullish_score > bearish_score + 20:
            alignment.alignment_direction = "bullish"
            alignment.alignment_score = bullish_score
        elif bearish_score > bullish_score + 20:
            alignment.alignment_direction = "bearish"
            alignment.alignment_score = bearish_score
        else:
            alignment.alignment_direction = "neutral"
            alignment.alignment_score = max(bullish_score, bearish_score)
        
        # Check full alignment (all TFs agree)
        bullish_tfs = sum(1 for b in biases.values() 
                         if b in [DirectionalBias.BULLISH, DirectionalBias.STRONGLY_BULLISH])
        bearish_tfs = sum(1 for b in biases.values() 
                         if b in [DirectionalBias.BEARISH, DirectionalBias.STRONGLY_BEARISH])
        
        alignment.full_alignment = (bullish_tfs >= 4 or bearish_tfs >= 4) and len(conflicts) == 0
        
        # Determine if tradeable
        # Primary decision frame is M30, but needs higher TF support
        if m30 and h4 and d1:
            m30_direction = "bullish" if m30.bias in [DirectionalBias.BULLISH, DirectionalBias.STRONGLY_BULLISH] else \
                           "bearish" if m30.bias in [DirectionalBias.BEARISH, DirectionalBias.STRONGLY_BEARISH] else "neutral"
            
            h4_supports = (m30_direction == "bullish" and h4.bias in [DirectionalBias.BULLISH, DirectionalBias.STRONGLY_BULLISH, DirectionalBias.NEUTRAL]) or \
                         (m30_direction == "bearish" and h4.bias in [DirectionalBias.BEARISH, DirectionalBias.STRONGLY_BEARISH, DirectionalBias.NEUTRAL])
            
            d1_not_against = (m30_direction == "bullish" and d1.bias not in [DirectionalBias.STRONGLY_BEARISH]) or \
                            (m30_direction == "bearish" and d1.bias not in [DirectionalBias.STRONGLY_BULLISH])
            
            if m30_direction != "neutral" and h4_supports and d1_not_against and len(conflicts) == 0:
                alignment.tradeable = True
                alignment.trade_direction = m30_direction
                alignment.confidence = m30.confidence * (alignment.alignment_score / 100)
        
        self.analyses[symbol] = alignment
        return alignment
    
    def get_trade_permission(self, symbol: str, direction: str) -> Tuple[bool, str]:
        """
        Check if a trade in given direction is permitted by MTF framework.
        
        Returns:
            (permitted: bool, reason: str)
        """
        alignment = self.analyses.get(symbol)
        if not alignment:
            return False, "No MTF analysis available"
        
        if alignment.conflicts:
            return False, f"MTF conflicts: {', '.join(alignment.conflicts)}"
        
        if not alignment.tradeable:
            return False, "MTF alignment insufficient"
        
        if alignment.trade_direction != direction:
            return False, f"MTF supports {alignment.trade_direction}, not {direction}"
        
        if alignment.confidence < 50:
            return False, f"MTF confidence too low ({alignment.confidence:.0f}%)"
        
        return True, f"MTF aligned {direction} with {alignment.confidence:.0f}% confidence"
    
    def get_hierarchy_summary(self, symbol: str) -> dict:
        """Get a summary of the MTF hierarchy for a symbol."""
        alignment = self.analyses.get(symbol)
        if not alignment:
            return {"error": "No analysis available"}
        
        return {
            "symbol": symbol,
            "hierarchy": {
                "D1_macro": {
                    "bias": alignment.d1.bias.value if alignment.d1 else "unknown",
                    "role": "Macro structure & directional map",
                    "weight": "25%",
                },
                "H4_swing": {
                    "bias": alignment.h4.bias.value if alignment.h4 else "unknown",
                    "role": "Swing bias & major zones",
                    "weight": "25%",
                },
                "H1_intermediate": {
                    "bias": alignment.h1.bias.value if alignment.h1 else "unknown",
                    "role": "Intermediate alignment",
                    "weight": "15%",
                },
                "M30_decision": {
                    "bias": alignment.m30.bias.value if alignment.m30 else "unknown",
                    "role": "PRIMARY decision frame",
                    "weight": "25%",
                },
                "M15_precision": {
                    "bias": alignment.m15.bias.value if alignment.m15 else "not_analyzed",
                    "role": "Precision entry timing",
                    "weight": "5%",
                },
                "M5_precision": {
                    "bias": alignment.m5.bias.value if alignment.m5 else "not_analyzed",
                    "role": "Precision entry timing",
                    "weight": "5%",
                },
            },
            "alignment": {
                "direction": alignment.alignment_direction,
                "score": alignment.alignment_score,
                "full_alignment": alignment.full_alignment,
                "conflicts": alignment.conflicts,
            },
            "tradeable": alignment.tradeable,
            "trade_direction": alignment.trade_direction,
            "confidence": alignment.confidence,
        }
