"""
Advanced Sentiment Analysis Engine
Avoids naive crowd-following, focuses on actionable signals
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
from datetime import datetime, timedelta


class SentimentClassification(str, Enum):
    """Primary sentiment classification."""
    TREND_SUPPORTIVE = "trend_supportive"      # Sentiment confirms price direction
    OVERCROWDED = "overcrowded"                 # Too many on same side
    CONTRARIAN_OPPORTUNITY = "contrarian"       # Extreme that may reverse
    DIVERGENT = "divergent"                     # Sentiment vs price disagreement
    NEUTRAL = "neutral"                         # No clear signal


class CrowdState(str, Enum):
    """State of crowd positioning."""
    EXTREME_LONG = "extreme_long"     # >80% long
    HEAVY_LONG = "heavy_long"         # 65-80% long
    BALANCED = "balanced"             # 35-65%
    HEAVY_SHORT = "heavy_short"       # 20-35% long
    EXTREME_SHORT = "extreme_short"   # <20% long


class NarrativeStrength(str, Enum):
    """Strength of the prevailing narrative."""
    STRONG = "strong"           # Clear, consistent narrative
    MODERATE = "moderate"       # Some narrative present
    WEAK = "weak"              # Conflicting or unclear
    ABSENT = "absent"          # No clear narrative


class ReversalRisk(str, Enum):
    """Risk of sentiment-driven reversal."""
    HIGH = "high"
    ELEVATED = "elevated"
    MODERATE = "moderate"
    LOW = "low"


@dataclass
class SentimentData:
    """Raw sentiment data from various sources."""
    # Retail positioning
    retail_long_pct: float = 50.0
    retail_short_pct: float = 50.0
    
    # COT (Commitment of Traders) style data
    commercial_net: float = 0       # Commercial hedgers
    non_commercial_net: float = 0   # Speculators
    retail_net: float = 0
    
    # Social/News sentiment
    bullish_mentions: int = 0
    bearish_mentions: int = 0
    neutral_mentions: int = 0
    sentiment_score: float = 0      # -100 to 100
    
    # Volume indicators
    volume_ratio: float = 1.0       # Current vs average
    
    # Historical
    positioning_change_24h: float = 0
    positioning_change_7d: float = 0


@dataclass
class SentimentAnalysis:
    """Complete sentiment analysis for a symbol."""
    symbol: str
    timestamp: datetime
    
    # Raw data
    data: SentimentData
    
    # Classifications
    classification: SentimentClassification = SentimentClassification.NEUTRAL
    crowd_state: CrowdState = CrowdState.BALANCED
    narrative_strength: NarrativeStrength = NarrativeStrength.WEAK
    reversal_risk: ReversalRisk = ReversalRisk.LOW
    
    # Scores (0-100)
    crowding_score: float = 50      # How crowded is the positioning
    contrarian_score: float = 50    # Contrarian opportunity strength
    divergence_score: float = 0     # Price vs sentiment divergence
    
    # Actionable signals
    supports_long: bool = False
    supports_short: bool = False
    warns_against_long: bool = False
    warns_against_short: bool = False
    
    # Narrative
    narrative_summary: str = ""
    
    # Recommendations
    confidence_modifier: float = 1.0  # Multiplier for trade confidence
    position_size_modifier: float = 1.0  # Multiplier for position size
    
    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "classification": self.classification.value,
            "crowd_state": self.crowd_state.value,
            "narrative_strength": self.narrative_strength.value,
            "reversal_risk": self.reversal_risk.value,
            "crowding_score": self.crowding_score,
            "contrarian_score": self.contrarian_score,
            "divergence_score": self.divergence_score,
            "supports_long": self.supports_long,
            "supports_short": self.supports_short,
            "warns_against_long": self.warns_against_long,
            "warns_against_short": self.warns_against_short,
            "narrative_summary": self.narrative_summary,
            "confidence_modifier": self.confidence_modifier,
            "position_size_modifier": self.position_size_modifier,
            "retail_positioning": {
                "long_pct": self.data.retail_long_pct,
                "short_pct": self.data.retail_short_pct,
            },
        }


class SentimentEngine:
    """
    Advanced Sentiment Analysis Engine
    
    Key Principles:
    - Sentiment is NEVER sole justification for a trade
    - Avoid naive crowd-following
    - Look for overcrowding and reversal risk
    - Identify price-sentiment divergences
    - Use sentiment to modify confidence, not drive entries
    """
    
    # Thresholds for crowd states
    EXTREME_THRESHOLD = 80
    HEAVY_THRESHOLD = 65
    
    # Contrarian thresholds
    CONTRARIAN_TRIGGER = 85
    
    def __init__(self):
        self.analyses: Dict[str, SentimentAnalysis] = {}
        self.historical: Dict[str, List[SentimentData]] = {}
    
    def analyze(
        self,
        symbol: str,
        data: SentimentData,
        price_direction: str = "neutral",  # bullish/bearish/neutral
        price_momentum: float = 0,  # -100 to 100
    ) -> SentimentAnalysis:
        """
        Perform comprehensive sentiment analysis.
        
        Args:
            symbol: Trading pair
            data: Raw sentiment data
            price_direction: Current price trend direction
            price_momentum: Price momentum score
        """
        analysis = SentimentAnalysis(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            data=data,
        )
        
        # 1. Determine crowd state
        analysis.crowd_state = self._determine_crowd_state(data)
        
        # 2. Calculate crowding score (how extreme is positioning)
        analysis.crowding_score = self._calculate_crowding_score(data)
        
        # 3. Detect price-sentiment divergence
        analysis.divergence_score = self._calculate_divergence(
            data, price_direction, price_momentum
        )
        
        # 4. Assess narrative strength
        analysis.narrative_strength = self._assess_narrative(data)
        
        # 5. Calculate reversal risk
        analysis.reversal_risk = self._assess_reversal_risk(
            data, analysis.crowding_score, analysis.divergence_score
        )
        
        # 6. Calculate contrarian score
        analysis.contrarian_score = self._calculate_contrarian_score(
            data, price_direction, analysis.crowd_state
        )
        
        # 7. Determine primary classification
        analysis.classification = self._classify_sentiment(
            analysis, price_direction
        )
        
        # 8. Set actionable signals
        self._set_actionable_signals(analysis, price_direction)
        
        # 9. Generate narrative summary
        analysis.narrative_summary = self._generate_narrative(analysis, price_direction)
        
        # 10. Calculate confidence/size modifiers
        self._calculate_modifiers(analysis)
        
        # Store for historical tracking
        self._store_historical(symbol, data)
        self.analyses[symbol] = analysis
        
        return analysis
    
    def _determine_crowd_state(self, data: SentimentData) -> CrowdState:
        """Determine the current crowd positioning state."""
        long_pct = data.retail_long_pct
        
        if long_pct >= self.EXTREME_THRESHOLD:
            return CrowdState.EXTREME_LONG
        elif long_pct >= self.HEAVY_THRESHOLD:
            return CrowdState.HEAVY_LONG
        elif long_pct <= (100 - self.EXTREME_THRESHOLD):
            return CrowdState.EXTREME_SHORT
        elif long_pct <= (100 - self.HEAVY_THRESHOLD):
            return CrowdState.HEAVY_SHORT
        else:
            return CrowdState.BALANCED
    
    def _calculate_crowding_score(self, data: SentimentData) -> float:
        """Calculate how crowded the positioning is (0-100)."""
        # Distance from 50% (balanced)
        distance = abs(data.retail_long_pct - 50)
        # Scale to 0-100 where 100 is extreme
        return min(distance * 2, 100)
    
    def _calculate_divergence(
        self,
        data: SentimentData,
        price_direction: str,
        price_momentum: float
    ) -> float:
        """
        Calculate price-sentiment divergence score.
        
        Divergence occurs when:
        - Price rising but sentiment bearish (or reducing longs)
        - Price falling but sentiment bullish (or reducing shorts)
        """
        score = 0
        
        # Check if positioning is against price direction
        if price_direction == "bullish":
            if data.retail_long_pct < 40:
                # Price up but retail short - bullish divergence
                score = (50 - data.retail_long_pct) * 2
            # Check if longs being reduced despite rising price
            if data.positioning_change_24h < -5:
                score += 20
        
        elif price_direction == "bearish":
            if data.retail_long_pct > 60:
                # Price down but retail long - bearish divergence
                score = (data.retail_long_pct - 50) * 2
            # Check if shorts being reduced despite falling price
            if data.positioning_change_24h > 5:
                score += 20
        
        # Factor in momentum disagreement
        if price_momentum > 30 and data.sentiment_score < -30:
            score += 15
        elif price_momentum < -30 and data.sentiment_score > 30:
            score += 15
        
        return min(score, 100)
    
    def _assess_narrative(self, data: SentimentData) -> NarrativeStrength:
        """Assess the strength of prevailing narrative."""
        total_mentions = data.bullish_mentions + data.bearish_mentions + data.neutral_mentions
        
        if total_mentions == 0:
            return NarrativeStrength.ABSENT
        
        # Calculate dominance of one narrative
        bullish_ratio = data.bullish_mentions / total_mentions if total_mentions > 0 else 0
        bearish_ratio = data.bearish_mentions / total_mentions if total_mentions > 0 else 0
        
        dominant = max(bullish_ratio, bearish_ratio)
        
        if dominant >= 0.7:
            return NarrativeStrength.STRONG
        elif dominant >= 0.5:
            return NarrativeStrength.MODERATE
        else:
            return NarrativeStrength.WEAK
    
    def _assess_reversal_risk(
        self,
        data: SentimentData,
        crowding_score: float,
        divergence_score: float
    ) -> ReversalRisk:
        """Assess risk of sentiment-driven reversal."""
        risk_score = 0
        
        # Extreme positioning = high reversal risk
        risk_score += crowding_score * 0.4
        
        # Divergence adds to reversal risk
        risk_score += divergence_score * 0.3
        
        # Rapid positioning changes suggest instability
        if abs(data.positioning_change_24h) > 10:
            risk_score += 20
        if abs(data.positioning_change_7d) > 20:
            risk_score += 15
        
        if risk_score >= 60:
            return ReversalRisk.HIGH
        elif risk_score >= 40:
            return ReversalRisk.ELEVATED
        elif risk_score >= 20:
            return ReversalRisk.MODERATE
        else:
            return ReversalRisk.LOW
    
    def _calculate_contrarian_score(
        self,
        data: SentimentData,
        price_direction: str,
        crowd_state: CrowdState
    ) -> float:
        """
        Calculate contrarian opportunity score.
        
        High score when:
        - Extreme positioning in one direction
        - Price showing signs of exhaustion
        - COT commercials positioned opposite to retail
        """
        score = 0
        
        # Extreme retail positioning is contrarian opportunity
        if crowd_state == CrowdState.EXTREME_LONG:
            score = 80  # Contrarian short opportunity
        elif crowd_state == CrowdState.EXTREME_SHORT:
            score = 80  # Contrarian long opportunity
        elif crowd_state in [CrowdState.HEAVY_LONG, CrowdState.HEAVY_SHORT]:
            score = 50
        
        # Boost if commercials positioned opposite
        if data.commercial_net > 0 and data.retail_long_pct > 70:
            score += 15  # Commercials short while retail long
        elif data.commercial_net < 0 and data.retail_long_pct < 30:
            score += 15  # Commercials long while retail short
        
        return min(score, 100)
    
    def _classify_sentiment(
        self,
        analysis: SentimentAnalysis,
        price_direction: str
    ) -> SentimentClassification:
        """Determine primary sentiment classification."""
        # Check for overcrowding first (dangerous)
        if analysis.crowd_state in [CrowdState.EXTREME_LONG, CrowdState.EXTREME_SHORT]:
            return SentimentClassification.OVERCROWDED
        
        # Check for contrarian opportunity
        if analysis.contrarian_score >= 70:
            return SentimentClassification.CONTRARIAN_OPPORTUNITY
        
        # Check for divergence
        if analysis.divergence_score >= 50:
            return SentimentClassification.DIVERGENT
        
        # Check if sentiment supports price direction
        if price_direction == "bullish" and analysis.data.retail_long_pct > 50:
            if analysis.crowding_score < 50:
                return SentimentClassification.TREND_SUPPORTIVE
        elif price_direction == "bearish" and analysis.data.retail_long_pct < 50:
            if analysis.crowding_score < 50:
                return SentimentClassification.TREND_SUPPORTIVE
        
        return SentimentClassification.NEUTRAL
    
    def _set_actionable_signals(self, analysis: SentimentAnalysis, price_direction: str):
        """Set actionable trading signals."""
        # Supports long if:
        # - Retail extreme short (contrarian)
        # - OR positioning balanced/moderately bullish with trend
        if analysis.crowd_state == CrowdState.EXTREME_SHORT:
            analysis.supports_long = True
        elif (analysis.crowd_state in [CrowdState.BALANCED, CrowdState.HEAVY_SHORT] and 
              price_direction == "bullish"):
            analysis.supports_long = True
        
        # Supports short if:
        # - Retail extreme long (contrarian)
        # - OR positioning balanced/moderately bearish with trend
        if analysis.crowd_state == CrowdState.EXTREME_LONG:
            analysis.supports_short = True
        elif (analysis.crowd_state in [CrowdState.BALANCED, CrowdState.HEAVY_LONG] and 
              price_direction == "bearish"):
            analysis.supports_short = True
        
        # Warns against long if:
        # - Already heavily long (crowded)
        # - High reversal risk with bullish positioning
        if analysis.crowd_state in [CrowdState.EXTREME_LONG, CrowdState.HEAVY_LONG]:
            analysis.warns_against_long = True
        if analysis.reversal_risk == ReversalRisk.HIGH and analysis.data.retail_long_pct > 60:
            analysis.warns_against_long = True
        
        # Warns against short if:
        # - Already heavily short (crowded)
        # - High reversal risk with bearish positioning
        if analysis.crowd_state in [CrowdState.EXTREME_SHORT, CrowdState.HEAVY_SHORT]:
            analysis.warns_against_short = True
        if analysis.reversal_risk == ReversalRisk.HIGH and analysis.data.retail_long_pct < 40:
            analysis.warns_against_short = True
    
    def _generate_narrative(self, analysis: SentimentAnalysis, price_direction: str) -> str:
        """Generate human-readable narrative summary."""
        parts = []
        
        # Positioning description
        long_pct = analysis.data.retail_long_pct
        if analysis.crowd_state == CrowdState.EXTREME_LONG:
            parts.append(f"Retail extremely long ({long_pct:.0f}%) - overcrowded")
        elif analysis.crowd_state == CrowdState.EXTREME_SHORT:
            parts.append(f"Retail extremely short ({100-long_pct:.0f}%) - contrarian long setup")
        elif analysis.crowd_state == CrowdState.HEAVY_LONG:
            parts.append(f"Retail heavily long ({long_pct:.0f}%)")
        elif analysis.crowd_state == CrowdState.HEAVY_SHORT:
            parts.append(f"Retail heavily short ({100-long_pct:.0f}%)")
        else:
            parts.append(f"Retail positioning balanced ({long_pct:.0f}% long)")
        
        # Divergence
        if analysis.divergence_score > 40:
            parts.append(f"Price-sentiment divergence detected ({analysis.divergence_score:.0f}%)")
        
        # Reversal risk
        if analysis.reversal_risk in [ReversalRisk.HIGH, ReversalRisk.ELEVATED]:
            parts.append(f"Reversal risk {analysis.reversal_risk.value}")
        
        # Classification action
        if analysis.classification == SentimentClassification.CONTRARIAN_OPPORTUNITY:
            direction = "long" if analysis.crowd_state == CrowdState.EXTREME_SHORT else "short"
            parts.append(f"Contrarian {direction} opportunity")
        elif analysis.classification == SentimentClassification.OVERCROWDED:
            parts.append("Avoid adding to crowded side")
        
        return "; ".join(parts)
    
    def _calculate_modifiers(self, analysis: SentimentAnalysis):
        """Calculate confidence and position size modifiers."""
        # Start at neutral
        conf_mod = 1.0
        size_mod = 1.0
        
        # Overcrowding penalty
        if analysis.classification == SentimentClassification.OVERCROWDED:
            conf_mod *= 0.7
            size_mod *= 0.5
        
        # Trend supportive boost
        if analysis.classification == SentimentClassification.TREND_SUPPORTIVE:
            conf_mod *= 1.1
        
        # Contrarian opportunity (careful - can be wrong)
        if analysis.classification == SentimentClassification.CONTRARIAN_OPPORTUNITY:
            conf_mod *= 0.9  # Slightly reduce - contrarian is risky
            size_mod *= 0.75  # Smaller size on contrarian
        
        # Divergence warning
        if analysis.divergence_score > 50:
            conf_mod *= 0.85
        
        # High reversal risk
        if analysis.reversal_risk == ReversalRisk.HIGH:
            conf_mod *= 0.8
            size_mod *= 0.7
        elif analysis.reversal_risk == ReversalRisk.ELEVATED:
            conf_mod *= 0.9
            size_mod *= 0.85
        
        analysis.confidence_modifier = round(conf_mod, 2)
        analysis.position_size_modifier = round(size_mod, 2)
    
    def _store_historical(self, symbol: str, data: SentimentData):
        """Store data for historical analysis."""
        if symbol not in self.historical:
            self.historical[symbol] = []
        
        self.historical[symbol].append(data)
        
        # Keep last 100 data points
        if len(self.historical[symbol]) > 100:
            self.historical[symbol] = self.historical[symbol][-100:]
    
    def get_trade_guidance(
        self,
        symbol: str,
        proposed_direction: str  # "long" or "short"
    ) -> dict:
        """
        Get sentiment guidance for a proposed trade.
        
        IMPORTANT: Sentiment is NEVER sole justification.
        This provides modification guidance only.
        """
        analysis = self.analyses.get(symbol)
        if not analysis:
            return {
                "symbol": symbol,
                "direction": proposed_direction,
                "sentiment_available": False,
                "proceed": True,
                "message": "No sentiment data - proceed with technical only",
            }
        
        guidance = {
            "symbol": symbol,
            "direction": proposed_direction,
            "sentiment_available": True,
            "classification": analysis.classification.value,
            "crowd_state": analysis.crowd_state.value,
        }
        
        # Check if sentiment supports or warns
        if proposed_direction == "long":
            guidance["sentiment_supports"] = analysis.supports_long
            guidance["sentiment_warns"] = analysis.warns_against_long
        else:
            guidance["sentiment_supports"] = analysis.supports_short
            guidance["sentiment_warns"] = analysis.warns_against_short
        
        # Make recommendation
        if guidance["sentiment_warns"]:
            if analysis.classification == SentimentClassification.OVERCROWDED:
                guidance["proceed"] = False
                guidance["message"] = f"Position overcrowded - avoid {proposed_direction}"
            else:
                guidance["proceed"] = True
                guidance["message"] = f"Sentiment caution - reduce size for {proposed_direction}"
                guidance["size_modifier"] = analysis.position_size_modifier
        elif guidance["sentiment_supports"]:
            guidance["proceed"] = True
            guidance["message"] = f"Sentiment supports {proposed_direction}"
            guidance["confidence_boost"] = analysis.confidence_modifier > 1.0
        else:
            guidance["proceed"] = True
            guidance["message"] = "Sentiment neutral - proceed with normal sizing"
        
        guidance["confidence_modifier"] = analysis.confidence_modifier
        guidance["position_size_modifier"] = analysis.position_size_modifier
        guidance["reversal_risk"] = analysis.reversal_risk.value
        
        return guidance
