"""
Regime Detection Agent
======================
Classifies the current market regime per symbol to ensure strategies only fire
in conditions where they have edge.

From 03_AGENT_DEFINITIONS_ANALYSIS_LAYER.txt:
This is one of the most critical agents.

REGIME CATEGORIES:
- TRENDING_STRONG: Clear, strong trend
- TRENDING_WEAK: Trend present but fading
- MEAN_REVERTING: Price oscillating around mean
- RANGE_BOUND: Clear support/resistance range
- BREAKOUT_READY: Compression before expansion
- EVENT_DRIVEN: Dominated by news/events
- UNSTABLE_NOISY: No clear pattern, choppy (DO NOT TRADE)
- LOW_VOLATILITY_DRIFT: Slow grind, low ATR
- HIGH_VOLATILITY_EXPANSION: Explosive moves
"""
import structlog
from datetime import datetime, timezone
from typing import Any, Optional
from dataclasses import dataclass, field
from enum import Enum

from app.agents.base_agent import BaseAgent, AgentMessage, AgentHealthStatus

logger = structlog.get_logger()


class RegimeType(str, Enum):
    """Market regime classifications."""
    TRENDING_STRONG = "trending_strong"
    TRENDING_WEAK = "trending_weak"
    MEAN_REVERTING = "mean_reverting"
    RANGE_BOUND = "range_bound"
    BREAKOUT_READY = "breakout_ready"
    EVENT_DRIVEN = "event_driven"
    UNSTABLE_NOISY = "unstable_noisy"
    LOW_VOLATILITY_DRIFT = "low_volatility_drift"
    HIGH_VOLATILITY_EXPANSION = "high_volatility_expansion"
    UNKNOWN = "unknown"


# Risk multipliers per regime
REGIME_RISK_MULTIPLIERS = {
    RegimeType.TRENDING_STRONG: 1.0,
    RegimeType.TRENDING_WEAK: 0.75,
    RegimeType.MEAN_REVERTING: 0.6,
    RegimeType.RANGE_BOUND: 0.5,
    RegimeType.BREAKOUT_READY: 0.7,  # Apply after confirmation
    RegimeType.EVENT_DRIVEN: 0.25,
    RegimeType.UNSTABLE_NOISY: 0.0,  # DO NOT TRADE
    RegimeType.LOW_VOLATILITY_DRIFT: 0.3,
    RegimeType.HIGH_VOLATILITY_EXPANSION: 0.5,
    RegimeType.UNKNOWN: 0.0,
}

# Strategy families compatible with each regime
REGIME_STRATEGY_FAMILIES = {
    RegimeType.TRENDING_STRONG: ["trend_continuation", "pullback_in_trend", "breakout"],
    RegimeType.TRENDING_WEAK: ["trend_continuation", "pullback_in_trend"],
    RegimeType.MEAN_REVERTING: ["range_fade", "mean_reversion"],
    RegimeType.RANGE_BOUND: ["range_fade", "failed_breakout_reversal"],
    RegimeType.BREAKOUT_READY: ["breakout", "volatility_expansion"],
    RegimeType.EVENT_DRIVEN: [],  # No strategies
    RegimeType.UNSTABLE_NOISY: [],  # No strategies
    RegimeType.LOW_VOLATILITY_DRIFT: ["volatility_expansion"],
    RegimeType.HIGH_VOLATILITY_EXPANSION: ["trend_continuation"],
    RegimeType.UNKNOWN: [],
}


@dataclass
class RegimeAssessment:
    """Complete regime assessment for a symbol."""
    symbol: str
    timestamp: datetime
    primary_timeframe: str = "M30"
    
    # Classification
    current_regime: RegimeType = RegimeType.UNKNOWN
    regime_confidence: float = 0.0  # 0.0 to 1.0
    regime_duration_bars: int = 0  # How long in current regime
    regime_stability: float = 0.0  # 0.0 to 1.0, likelihood to persist
    
    # Transition
    transition_probability: float = 0.0
    most_likely_next_regime: Optional[RegimeType] = None
    
    # Strategy guidance
    recommended_strategy_families: list = field(default_factory=list)
    incompatible_strategy_families: list = field(default_factory=list)
    
    # Risk
    regime_risk_multiplier: float = 0.0  # Applied to position sizing
    
    # Reasoning
    reasoning: str = ""
    classification_factors: dict = field(default_factory=dict)
    
    # Data
    confidence: float = 0.5
    data_quality: float = 1.0


class RegimeDetectionAgent(BaseAgent):
    """
    Regime Detection Agent.
    
    Classifies market regime to ensure strategies only run in favorable conditions.
    
    CRITICAL: If regime is UNSTABLE_NOISY, risk_multiplier = 0.0, blocking trading.
    """
    
    def __init__(
        self,
        name: str = "regime_detection_agent",
        config: Optional[dict[str, Any]] = None,
    ):
        super().__init__(name, config)
        
        self.primary_timeframe = config.get("primary_timeframe", "M30") if config else "M30"
        
        # Regime history for tracking duration
        self._regime_history: dict[str, list[tuple[datetime, RegimeType]]] = {}
    
    async def initialize(self) -> None:
        """Initialize the agent."""
        self.is_initialized = True
        self.is_running = True
        self.started_at = datetime.now(timezone.utc)
        self._logger.info("Regime Detection Agent initialized")
    
    async def run(self, context: dict[str, Any]) -> AgentMessage:
        """
        Detect market regime for a symbol.
        
        Args:
            context: Must contain:
                - symbol: Symbol to analyze
                - technical: TechnicalAssessment from Technical Analysis Agent
                - structure: MarketStructureAssessment from Market Structure Agent
                - event_risk (optional): Event risk assessment
        """
        symbol = context.get("symbol")
        technical = context.get("technical")
        structure = context.get("structure")
        event_risk = context.get("event_risk")
        
        if not symbol or not technical:
            return self._create_message(
                message_type="error",
                payload={"error": "Missing symbol or technical data in context"},
                symbol=symbol,
                confidence=0.0,
                data_quality=0.0,
                errors=["Missing required context"],
            )
        
        # Detect regime
        assessment = await self._detect_regime(symbol, technical, structure, event_risk)
        
        # Track warnings
        warnings = []
        if assessment.current_regime == RegimeType.UNSTABLE_NOISY:
            warnings.append("REGIME BLOCKED: Unstable/noisy conditions - DO NOT TRADE")
        elif assessment.regime_risk_multiplier < 0.5:
            warnings.append(f"Reduced risk: {assessment.regime_risk_multiplier:.0%} multiplier")
        if assessment.transition_probability > 0.5:
            warnings.append(f"Regime may be transitioning ({assessment.transition_probability:.0%})")
        
        return self._create_message(
            message_type="regime_assessment",
            payload=self._assessment_to_dict(assessment),
            symbol=symbol,
            timeframe=self.primary_timeframe,
            confidence=assessment.confidence,
            data_quality=assessment.data_quality,
            warnings=warnings,
        )
    
    async def _detect_regime(
        self,
        symbol: str,
        technical: dict,
        structure: Optional[dict],
        event_risk: Optional[dict],
    ) -> RegimeAssessment:
        """Perform regime detection."""
        assessment = RegimeAssessment(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            primary_timeframe=self.primary_timeframe,
        )
        
        # Extract indicators
        indicators = technical.get("indicators", {}).get(self.primary_timeframe, {})
        
        if not indicators or indicators.get("insufficient_data"):
            assessment.current_regime = RegimeType.UNKNOWN
            assessment.regime_risk_multiplier = 0.0
            assessment.reasoning = "Insufficient data for regime classification"
            return assessment
        
        # Get key metrics
        adx_data = indicators.get("adx", {})
        adx = adx_data.get("adx", 0)
        
        volatility = indicators.get("volatility", {})
        atr_percentile = volatility.get("atr_percentile", 50)
        is_compressed = volatility.get("is_compressed", False)
        is_expanding = volatility.get("is_expanding", False)
        
        ema_cluster = indicators.get("ema_cluster", {})
        ema_aligned_bull = ema_cluster.get("is_bullish_aligned", False)
        ema_aligned_bear = ema_cluster.get("is_bearish_aligned", False)
        ema_alignment_score = abs(ema_cluster.get("alignment_score", 0))
        
        structure_state = structure.get("structure_state", "unknown") if structure else "unknown"
        swing_sequence = structure.get("swing_sequence", "mixed") if structure else "mixed"
        
        # Check for event-driven regime first
        if event_risk and event_risk.get("is_blocked"):
            assessment.current_regime = RegimeType.EVENT_DRIVEN
            assessment.reasoning = "High-impact event window active"
            assessment.classification_factors = {"event_blocked": True}
        
        # Classify based on indicators
        else:
            regime, confidence, factors, reasoning = self._classify_regime(
                adx=adx,
                atr_percentile=atr_percentile,
                is_compressed=is_compressed,
                is_expanding=is_expanding,
                ema_aligned_bull=ema_aligned_bull,
                ema_aligned_bear=ema_aligned_bear,
                ema_alignment_score=ema_alignment_score,
                structure_state=structure_state,
                swing_sequence=swing_sequence,
            )
            
            assessment.current_regime = regime
            assessment.regime_confidence = confidence
            assessment.classification_factors = factors
            assessment.reasoning = reasoning
        
        # Set risk multiplier
        assessment.regime_risk_multiplier = REGIME_RISK_MULTIPLIERS.get(
            assessment.current_regime, 0.0
        )
        
        # Adjust for low confidence
        if assessment.regime_confidence < 0.5:
            assessment.regime_risk_multiplier *= 0.5
        
        # Set strategy families
        assessment.recommended_strategy_families = REGIME_STRATEGY_FAMILIES.get(
            assessment.current_regime, []
        )
        
        # Determine incompatible strategies
        all_strategies = {
            "trend_continuation", "pullback_in_trend", "breakout",
            "range_fade", "failed_breakout_reversal", "mean_reversion",
            "volatility_expansion"
        }
        assessment.incompatible_strategy_families = list(
            all_strategies - set(assessment.recommended_strategy_families)
        )
        
        # Track regime duration
        assessment.regime_duration_bars = self._get_regime_duration(
            symbol, assessment.current_regime
        )
        
        # Estimate transition probability
        assessment.transition_probability = self._estimate_transition_probability(
            assessment, adx, atr_percentile
        )
        
        # Estimate stability
        assessment.regime_stability = 1.0 - assessment.transition_probability
        
        # Calculate overall confidence
        assessment.confidence = assessment.regime_confidence
        assessment.data_quality = technical.get("data_quality", 1.0)
        
        # Update history
        self._update_regime_history(symbol, assessment.current_regime)
        
        return assessment
    
    def _classify_regime(
        self,
        adx: float,
        atr_percentile: float,
        is_compressed: bool,
        is_expanding: bool,
        ema_aligned_bull: bool,
        ema_aligned_bear: bool,
        ema_alignment_score: float,
        structure_state: str,
        swing_sequence: str,
    ) -> tuple[RegimeType, float, dict, str]:
        """
        Classify regime based on indicators.
        
        Returns:
            Tuple of (regime, confidence, factors, reasoning)
        """
        factors = {
            "adx": adx,
            "atr_percentile": atr_percentile,
            "is_compressed": is_compressed,
            "is_expanding": is_expanding,
            "ema_alignment": ema_alignment_score,
            "structure_state": structure_state,
            "swing_sequence": swing_sequence,
        }
        
        # TRENDING_STRONG
        if adx > 30 and (ema_aligned_bull or ema_aligned_bear) and swing_sequence in ["HH_HL", "LH_LL"]:
            return (
                RegimeType.TRENDING_STRONG,
                0.85,
                factors,
                f"Strong trend: ADX={adx:.1f}, EMAs aligned, structure confirms"
            )
        
        # TRENDING_WEAK
        if 20 < adx <= 30 and ema_alignment_score > 0.5:
            return (
                RegimeType.TRENDING_WEAK,
                0.7,
                factors,
                f"Weak trend: ADX={adx:.1f}, partial EMA alignment"
            )
        
        # BREAKOUT_READY
        if is_compressed and atr_percentile < 20:
            return (
                RegimeType.BREAKOUT_READY,
                0.75,
                factors,
                f"Breakout setup: Compressed volatility (ATR percentile={atr_percentile:.0f})"
            )
        
        # HIGH_VOLATILITY_EXPANSION
        if is_expanding and atr_percentile > 80:
            return (
                RegimeType.HIGH_VOLATILITY_EXPANSION,
                0.7,
                factors,
                f"High volatility: ATR percentile={atr_percentile:.0f}, expanding"
            )
        
        # LOW_VOLATILITY_DRIFT
        if atr_percentile < 15 and adx < 15:
            return (
                RegimeType.LOW_VOLATILITY_DRIFT,
                0.65,
                factors,
                f"Low volatility drift: ATR percentile={atr_percentile:.0f}, ADX={adx:.1f}"
            )
        
        # RANGE_BOUND
        if structure_state == "ranging" and adx < 20:
            return (
                RegimeType.RANGE_BOUND,
                0.7,
                factors,
                f"Range-bound: Structure ranging, ADX={adx:.1f}"
            )
        
        # MEAN_REVERTING
        if adx < 20 and 30 < atr_percentile < 70 and swing_sequence == "mixed":
            return (
                RegimeType.MEAN_REVERTING,
                0.6,
                factors,
                f"Mean-reverting: ADX={adx:.1f}, mixed swings"
            )
        
        # UNSTABLE_NOISY - catch-all for unclear conditions
        if adx < 15 and swing_sequence == "mixed" and ema_alignment_score < 0.3:
            return (
                RegimeType.UNSTABLE_NOISY,
                0.55,
                factors,
                f"Unstable/noisy: No clear pattern, ADX={adx:.1f}, EMAs intertwined"
            )
        
        # Default to weak trend if some directional signal exists
        if 15 < adx < 25:
            return (
                RegimeType.TRENDING_WEAK,
                0.5,
                factors,
                f"Weak trend (default): ADX={adx:.1f}"
            )
        
        # Truly unknown
        return (
            RegimeType.UNKNOWN,
            0.3,
            factors,
            "Cannot confidently classify regime"
        )
    
    def _get_regime_duration(self, symbol: str, current_regime: RegimeType) -> int:
        """Get how long we've been in the current regime."""
        history = self._regime_history.get(symbol, [])
        
        if not history:
            return 0
        
        duration = 0
        for _, regime in reversed(history):
            if regime == current_regime:
                duration += 1
            else:
                break
        
        return duration
    
    def _estimate_transition_probability(
        self,
        assessment: RegimeAssessment,
        adx: float,
        atr_percentile: float,
    ) -> float:
        """Estimate probability of regime transition."""
        prob = 0.1  # Base probability
        
        # Compression often leads to expansion
        if assessment.current_regime == RegimeType.BREAKOUT_READY:
            prob = 0.6
        
        # Trends weaken over time
        if assessment.current_regime == RegimeType.TRENDING_STRONG:
            if assessment.regime_duration_bars > 20:
                prob = 0.3
        
        # Expansion typically cools down
        if assessment.current_regime == RegimeType.HIGH_VOLATILITY_EXPANSION:
            prob = 0.5
        
        # ADX changing direction suggests transition
        if 20 < adx < 25:
            prob += 0.15
        
        return min(prob, 0.9)
    
    def _update_regime_history(self, symbol: str, regime: RegimeType) -> None:
        """Update regime history for a symbol."""
        if symbol not in self._regime_history:
            self._regime_history[symbol] = []
        
        self._regime_history[symbol].append((datetime.now(timezone.utc), regime))
        
        # Keep only last 100 entries
        if len(self._regime_history[symbol]) > 100:
            self._regime_history[symbol] = self._regime_history[symbol][-100:]
    
    def _assessment_to_dict(self, assessment: RegimeAssessment) -> dict:
        """Convert assessment to serializable dict."""
        return {
            "symbol": assessment.symbol,
            "timestamp": assessment.timestamp.isoformat(),
            "primary_timeframe": assessment.primary_timeframe,
            "current_regime": assessment.current_regime.value,
            "regime_confidence": assessment.regime_confidence,
            "regime_duration_bars": assessment.regime_duration_bars,
            "regime_stability": assessment.regime_stability,
            "transition_probability": assessment.transition_probability,
            "most_likely_next_regime": assessment.most_likely_next_regime.value if assessment.most_likely_next_regime else None,
            "recommended_strategy_families": assessment.recommended_strategy_families,
            "incompatible_strategy_families": assessment.incompatible_strategy_families,
            "regime_risk_multiplier": assessment.regime_risk_multiplier,
            "reasoning": assessment.reasoning,
            "classification_factors": assessment.classification_factors,
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
        return ["market_data_agent", "technical_analysis_agent", "market_structure_agent"]
