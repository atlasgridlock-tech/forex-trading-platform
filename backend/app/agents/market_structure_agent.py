"""
Market Structure Agent
======================
Detects and maps structural landscape: swing points, S/R zones, trends, ranges,
liquidity areas, and structural shifts.

From 03_AGENT_DEFINITIONS_ANALYSIS_LAYER.txt:
- Detect swing highs/lows and classify as HH, LH, HL, LL
- Identify structural S/R zones
- Detect consolidation and range behavior
- Detect structural transitions (BOS, CHOCH, failed breakouts)
- Detect liquidity behavior
"""
import structlog
import pandas as pd
from datetime import datetime, timezone
from typing import Any, Optional
from dataclasses import dataclass, field

from app.agents.base_agent import BaseAgent, AgentMessage, AgentHealthStatus
from app.indicators.structure import (
    SwingPoint,
    StructureZone,
    StructuralEvent,
    SwingAnalysis,
    detect_swing_points,
    identify_support_resistance_zones,
    detect_break_of_structure,
)
from app.indicators.volatility import calculate_atr

logger = structlog.get_logger()


@dataclass
class MarketStructureAssessment:
    """Complete market structure assessment."""
    symbol: str
    timestamp: datetime
    primary_timeframe: str = "M30"
    
    # Structure state
    structure_state: str = "unknown"  # trending_up, trending_down, ranging, transitioning, breakout_in_progress
    structure_confidence: float = 0.0
    
    # Swing points
    recent_swing_highs: list = field(default_factory=list)
    recent_swing_lows: list = field(default_factory=list)
    swing_sequence: str = "mixed"  # HH_HL, LH_LL, mixed
    
    # Zones
    support_zones: list = field(default_factory=list)
    resistance_zones: list = field(default_factory=list)
    nearest_support: Optional[dict] = None
    nearest_resistance: Optional[dict] = None
    distance_to_support_atr: Optional[float] = None
    distance_to_resistance_atr: Optional[float] = None
    
    # Price location
    price_location: str = "mid_range"  # at_support, at_resistance, mid_range, breakout_zone, no_mans_land
    is_at_significant_level: bool = False
    risk_reward_location_quality: float = 0.5
    
    # Structural events
    recent_bos: Optional[dict] = None
    recent_choch: Optional[dict] = None
    recent_failed_breakout: Optional[dict] = None
    recent_liquidity_sweep: Optional[dict] = None
    
    # Invalidation levels
    bullish_invalidation: Optional[float] = None
    bearish_invalidation: Optional[float] = None
    
    # Scenarios
    primary_scenario: str = ""
    alternative_scenario: str = ""
    
    # Key questions answered
    are_we_trending: bool = False
    did_price_reject_major_level: bool = False
    did_price_sweep_and_reclaim: bool = False
    is_risk_definable_here: bool = False
    is_setup_asymmetric: bool = False
    
    # Scores
    confidence: float = 0.5
    data_quality: float = 1.0


class MarketStructureAgent(BaseAgent):
    """
    Market Structure Agent.
    
    Maps the structural landscape of each symbol: swing points, S/R zones,
    trends, ranges, and structural events.
    """
    
    def __init__(
        self,
        name: str = "market_structure_agent",
        config: Optional[dict[str, Any]] = None,
    ):
        super().__init__(name, config)
        
        self.primary_timeframe = config.get("primary_timeframe", "M30") if config else "M30"
        self.swing_lookback = config.get("swing_lookback", 5) if config else 5
        self.zone_buffer_atr = config.get("zone_buffer_atr", 0.5) if config else 0.5
    
    async def initialize(self) -> None:
        """Initialize the agent."""
        self.is_initialized = True
        self.is_running = True
        self.started_at = datetime.now(timezone.utc)
        self._logger.info("Market Structure Agent initialized")
    
    async def run(self, context: dict[str, Any]) -> AgentMessage:
        """
        Analyze market structure for a symbol.
        
        Args:
            context: Must contain:
                - symbol: Symbol to analyze
                - market_data: MarketDataSnapshot with OHLCV bars
        """
        symbol = context.get("symbol")
        market_data = context.get("market_data")
        
        if not symbol or not market_data:
            return self._create_message(
                message_type="error",
                payload={"error": "Missing symbol or market_data in context"},
                symbol=symbol,
                confidence=0.0,
                data_quality=0.0,
                errors=["Missing required context"],
            )
        
        # Compute assessment
        assessment = await self._analyze(symbol, market_data)
        
        warnings = []
        if not assessment.is_risk_definable_here:
            warnings.append("Risk not clearly definable at current location")
        if assessment.structure_state == "transitioning":
            warnings.append("Structure in transition - higher uncertainty")
        
        return self._create_message(
            message_type="market_structure_assessment",
            payload=self._assessment_to_dict(assessment),
            symbol=symbol,
            timeframe=self.primary_timeframe,
            confidence=assessment.confidence,
            data_quality=assessment.data_quality,
            warnings=warnings,
        )
    
    async def _analyze(
        self,
        symbol: str,
        market_data: dict,
    ) -> MarketStructureAssessment:
        """Perform full structure analysis."""
        assessment = MarketStructureAssessment(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            primary_timeframe=self.primary_timeframe,
        )
        
        # Get primary timeframe data
        timeframes_data = market_data.get("timeframes", {})
        primary_tf = timeframes_data.get(self.primary_timeframe)
        
        if not primary_tf or not primary_tf.get("bars"):
            assessment.confidence = 0.0
            assessment.data_quality = 0.0
            return assessment
        
        bars = primary_tf["bars"]
        
        # Convert to pandas for analysis
        df = self._bars_to_dataframe(bars)
        
        if len(df) < 50:
            assessment.confidence = 0.0
            assessment.data_quality = 0.5
            return assessment
        
        # Calculate ATR for zone sizing
        atr_result = calculate_atr(df["high"], df["low"], df["close"])
        atr = atr_result.atr if atr_result else 0.0
        
        current_price = float(df["close"].iloc[-1])
        
        # Detect swing points
        swing_analysis = detect_swing_points(
            df["high"],
            df["low"],
            df["close"],
            df["timestamp"],
            self.swing_lookback,
        )
        
        # Store swing points
        assessment.recent_swing_highs = [
            self._swing_to_dict(s) for s in swing_analysis.swing_highs[-10:]
        ]
        assessment.recent_swing_lows = [
            self._swing_to_dict(s) for s in swing_analysis.swing_lows[-10:]
        ]
        assessment.swing_sequence = swing_analysis.swing_sequence
        
        # Determine structure state from swing sequence
        assessment.structure_state = self._determine_structure_state(swing_analysis)
        assessment.are_we_trending = assessment.structure_state in ["trending_up", "trending_down"]
        
        # Identify S/R zones
        zones = identify_support_resistance_zones(
            df["high"],
            df["low"],
            df["close"],
            swing_analysis,
            atr,
            self.zone_buffer_atr,
        )
        
        assessment.support_zones = [
            self._zone_to_dict(z) for z in zones if z.type == "support"
        ]
        assessment.resistance_zones = [
            self._zone_to_dict(z) for z in zones if z.type == "resistance"
        ]
        
        # Find nearest zones
        support_zones = [z for z in zones if z.type == "support" and z.midpoint < current_price]
        resistance_zones = [z for z in zones if z.type == "resistance" and z.midpoint > current_price]
        
        if support_zones:
            nearest_support = max(support_zones, key=lambda z: z.midpoint)
            assessment.nearest_support = self._zone_to_dict(nearest_support)
            assessment.distance_to_support_atr = (current_price - nearest_support.midpoint) / atr if atr > 0 else None
        
        if resistance_zones:
            nearest_resistance = min(resistance_zones, key=lambda z: z.midpoint)
            assessment.nearest_resistance = self._zone_to_dict(nearest_resistance)
            assessment.distance_to_resistance_atr = (nearest_resistance.midpoint - current_price) / atr if atr > 0 else None
        
        # Determine price location
        assessment.price_location = self._determine_price_location(
            current_price, zones, atr
        )
        assessment.is_at_significant_level = assessment.price_location in ["at_support", "at_resistance"]
        
        # Calculate R:R location quality
        assessment.risk_reward_location_quality = self._calculate_location_quality(
            assessment, current_price, atr
        )
        
        # Detect structural events
        bos = detect_break_of_structure(df["close"], swing_analysis)
        if bos:
            assessment.recent_bos = {
                "event_type": bos.event_type,
                "price": bos.price,
                "description": bos.description,
                "significance": bos.significance,
            }
        
        # Set invalidation levels
        if swing_analysis.last_hl:
            assessment.bullish_invalidation = swing_analysis.last_hl.price
        if swing_analysis.last_lh:
            assessment.bearish_invalidation = swing_analysis.last_lh.price
        
        # Determine if risk is definable
        assessment.is_risk_definable_here = self._check_risk_definable(
            assessment, current_price, atr
        )
        
        # Check for asymmetric setup
        assessment.is_setup_asymmetric = self._check_asymmetric(assessment)
        
        # Generate scenarios
        assessment.primary_scenario = self._generate_primary_scenario(assessment)
        assessment.alternative_scenario = self._generate_alternative_scenario(assessment)
        
        # Calculate confidence
        assessment.structure_confidence = self._calculate_structure_confidence(swing_analysis)
        assessment.confidence = self._calculate_overall_confidence(assessment)
        assessment.data_quality = 1.0 if len(df) >= 200 else len(df) / 200
        
        return assessment
    
    def _bars_to_dataframe(self, bars: list) -> pd.DataFrame:
        """Convert bars to DataFrame."""
        return pd.DataFrame([{
            "timestamp": b.timestamp if hasattr(b, 'timestamp') else b.get('timestamp'),
            "open": float(b.open if hasattr(b, 'open') else b.get('open')),
            "high": float(b.high if hasattr(b, 'high') else b.get('high')),
            "low": float(b.low if hasattr(b, 'low') else b.get('low')),
            "close": float(b.close if hasattr(b, 'close') else b.get('close')),
        } for b in bars])
    
    def _determine_structure_state(self, swing_analysis: SwingAnalysis) -> str:
        """Determine overall structure state."""
        if swing_analysis.trend_direction == "bullish":
            return "trending_up"
        elif swing_analysis.trend_direction == "bearish":
            return "trending_down"
        elif swing_analysis.swing_sequence == "mixed":
            return "ranging"
        return "transitioning"
    
    def _determine_price_location(
        self,
        price: float,
        zones: list,
        atr: float,
    ) -> str:
        """Determine where price is relative to structure."""
        tolerance = atr * 0.5 if atr > 0 else 0
        
        for zone in zones:
            if zone.contains_price(price):
                return f"at_{zone.type}"
            if abs(price - zone.midpoint) < tolerance:
                return f"at_{zone.type}"
        
        # Check if between zones
        supports = [z for z in zones if z.type == "support" and z.midpoint < price]
        resistances = [z for z in zones if z.type == "resistance" and z.midpoint > price]
        
        if supports and resistances:
            nearest_support = max(supports, key=lambda z: z.midpoint)
            nearest_resistance = min(resistances, key=lambda z: z.midpoint)
            
            range_size = nearest_resistance.midpoint - nearest_support.midpoint
            position = (price - nearest_support.midpoint) / range_size if range_size > 0 else 0.5
            
            if 0.4 < position < 0.6:
                return "mid_range"
            elif position < 0.2:
                return "near_support"
            elif position > 0.8:
                return "near_resistance"
        
        return "no_mans_land"
    
    def _calculate_location_quality(
        self,
        assessment: MarketStructureAssessment,
        price: float,
        atr: float,
    ) -> float:
        """Calculate quality of current price location for R:R."""
        quality = 0.5
        
        # At support in uptrend = good
        if assessment.price_location == "at_support" and assessment.structure_state == "trending_up":
            quality = 0.8
        # At resistance in downtrend = good
        elif assessment.price_location == "at_resistance" and assessment.structure_state == "trending_down":
            quality = 0.8
        # Mid-range = neutral
        elif assessment.price_location == "mid_range":
            quality = 0.3
        # At support/resistance but no clear trend = moderate
        elif assessment.is_at_significant_level:
            quality = 0.6
        
        return quality
    
    def _check_risk_definable(
        self,
        assessment: MarketStructureAssessment,
        price: float,
        atr: float,
    ) -> bool:
        """Check if risk is clearly definable at current location."""
        # Need a clear invalidation level within reasonable distance
        if assessment.bullish_invalidation:
            distance = abs(price - assessment.bullish_invalidation)
            if 0.5 * atr < distance < 3 * atr:
                return True
        
        if assessment.bearish_invalidation:
            distance = abs(price - assessment.bearish_invalidation)
            if 0.5 * atr < distance < 3 * atr:
                return True
        
        # Or at a clear zone
        return assessment.is_at_significant_level
    
    def _check_asymmetric(self, assessment: MarketStructureAssessment) -> bool:
        """Check if setup offers asymmetric R:R."""
        # At support with clear resistance target
        if assessment.price_location == "at_support" and assessment.nearest_resistance:
            if assessment.distance_to_support_atr and assessment.distance_to_resistance_atr:
                # If potential reward > 2x potential risk
                return assessment.distance_to_resistance_atr > 2 * assessment.distance_to_support_atr
        
        # At resistance with clear support target
        if assessment.price_location == "at_resistance" and assessment.nearest_support:
            if assessment.distance_to_support_atr and assessment.distance_to_resistance_atr:
                return assessment.distance_to_support_atr > 2 * assessment.distance_to_resistance_atr
        
        return False
    
    def _generate_primary_scenario(self, assessment: MarketStructureAssessment) -> str:
        """Generate primary scenario description."""
        if assessment.structure_state == "trending_up":
            if assessment.price_location == "at_support":
                return "Uptrend continuation: Price at support, look for bullish confirmation to enter long"
            return "Uptrend in progress: Wait for pullback to support for better entry"
        
        elif assessment.structure_state == "trending_down":
            if assessment.price_location == "at_resistance":
                return "Downtrend continuation: Price at resistance, look for bearish confirmation to enter short"
            return "Downtrend in progress: Wait for rally to resistance for better entry"
        
        elif assessment.structure_state == "ranging":
            if assessment.price_location == "at_support":
                return "Range: Price at support, potential long to resistance"
            elif assessment.price_location == "at_resistance":
                return "Range: Price at resistance, potential short to support"
            return "Range: Wait for price to reach range boundary"
        
        return "Structure unclear: Wait for clearer setup"
    
    def _generate_alternative_scenario(self, assessment: MarketStructureAssessment) -> str:
        """Generate alternative scenario description."""
        if assessment.structure_state == "trending_up":
            return "Alternative: Trend exhaustion, break below recent HL would signal reversal"
        elif assessment.structure_state == "trending_down":
            return "Alternative: Trend exhaustion, break above recent LH would signal reversal"
        elif assessment.structure_state == "ranging":
            return "Alternative: Range breakout, prepare for momentum in direction of break"
        return "Alternative: Structure could evolve in either direction"
    
    def _calculate_structure_confidence(self, swing_analysis: SwingAnalysis) -> float:
        """Calculate confidence in structure assessment."""
        confidence = 0.5
        
        # Clear swing sequence
        if swing_analysis.swing_sequence in ["HH_HL", "LH_LL"]:
            confidence += 0.3
        
        # Recent confirmed swings
        if len(swing_analysis.swing_highs) >= 3 and len(swing_analysis.swing_lows) >= 3:
            confidence += 0.2
        
        return min(confidence, 1.0)
    
    def _calculate_overall_confidence(self, assessment: MarketStructureAssessment) -> float:
        """Calculate overall confidence."""
        confidence = assessment.structure_confidence
        
        # Location quality
        confidence += assessment.risk_reward_location_quality * 0.2
        
        # Definable risk
        if assessment.is_risk_definable_here:
            confidence += 0.1
        
        return min(confidence, 1.0)
    
    def _swing_to_dict(self, swing: SwingPoint) -> dict:
        """Convert SwingPoint to dict."""
        return {
            "timestamp": swing.timestamp.isoformat() if swing.timestamp else None,
            "price": swing.price,
            "type": swing.type,
            "classification": swing.classification,
            "significance": swing.significance,
        }
    
    def _zone_to_dict(self, zone: StructureZone) -> dict:
        """Convert StructureZone to dict."""
        return {
            "upper_bound": zone.upper_bound,
            "lower_bound": zone.lower_bound,
            "midpoint": zone.midpoint,
            "type": zone.type,
            "strength": zone.strength,
            "touch_count": zone.touch_count,
            "is_fresh": zone.is_fresh,
            "timeframe": zone.timeframe,
        }
    
    def _assessment_to_dict(self, assessment: MarketStructureAssessment) -> dict:
        """Convert assessment to serializable dict."""
        return {
            "symbol": assessment.symbol,
            "timestamp": assessment.timestamp.isoformat(),
            "primary_timeframe": assessment.primary_timeframe,
            "structure_state": assessment.structure_state,
            "structure_confidence": assessment.structure_confidence,
            "swing_sequence": assessment.swing_sequence,
            "recent_swing_highs": assessment.recent_swing_highs,
            "recent_swing_lows": assessment.recent_swing_lows,
            "support_zones": assessment.support_zones,
            "resistance_zones": assessment.resistance_zones,
            "nearest_support": assessment.nearest_support,
            "nearest_resistance": assessment.nearest_resistance,
            "distance_to_support_atr": assessment.distance_to_support_atr,
            "distance_to_resistance_atr": assessment.distance_to_resistance_atr,
            "price_location": assessment.price_location,
            "is_at_significant_level": assessment.is_at_significant_level,
            "risk_reward_location_quality": assessment.risk_reward_location_quality,
            "recent_bos": assessment.recent_bos,
            "bullish_invalidation": assessment.bullish_invalidation,
            "bearish_invalidation": assessment.bearish_invalidation,
            "primary_scenario": assessment.primary_scenario,
            "alternative_scenario": assessment.alternative_scenario,
            "are_we_trending": assessment.are_we_trending,
            "is_risk_definable_here": assessment.is_risk_definable_here,
            "is_setup_asymmetric": assessment.is_setup_asymmetric,
            "confidence": assessment.confidence,
            "data_quality": assessment.data_quality,
        }
    
    async def health_check(self) -> AgentHealthStatus:
        return AgentHealthStatus(
            agent_name=self.name,
            is_healthy=self.is_initialized,
            last_run=self.last_run,
            last_success=self.last_success,
            last_error=self.last_error,
            consecutive_failures=self.consecutive_failures,
            uptime_seconds=self._get_uptime_seconds(),
        )
    
    def get_dependencies(self) -> list[str]:
        return ["market_data_agent"]
