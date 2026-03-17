"""
Technical Analysis Agent
========================
Computes comprehensive technical indicators across multiple timeframes.

From 03_AGENT_DEFINITIONS_ANALYSIS_LAYER.txt:
- NOT a simplistic BUY/SELL signal
- Outputs directional lean, confidence, setup type, and evidence
- The BUY/SELL decision is made by the Orchestrator
"""
import structlog
import pandas as pd
from datetime import datetime, timezone
from typing import Any, Optional
from dataclasses import dataclass, field

from app.agents.base_agent import BaseAgent, AgentMessage, AgentHealthStatus
from app.indicators import (
    # Moving Averages
    calculate_ema_cluster,
    calculate_sma_baseline,
    calculate_linear_regression_slope,
    price_distance_from_ema,
    # Volatility
    calculate_atr,
    calculate_bollinger_bands,
    calculate_donchian_channels,
    calculate_volatility_state,
    detect_squeeze,
    # Momentum
    calculate_rsi,
    calculate_macd,
    calculate_stochastic,
    calculate_adx,
    calculate_roc,
)

logger = structlog.get_logger()


@dataclass
class TechnicalAssessment:
    """Complete technical assessment for a symbol."""
    symbol: str
    timestamp: datetime
    primary_timeframe: str = "M30"
    
    # Direction
    directional_lean: str = "neutral"  # bullish, bearish, neutral
    directional_strength: float = 0.0  # 0.0 to 1.0
    trend_quality: str = "unknown"  # strong_trend, weak_trend, range, transitioning
    
    # Setup
    setup_type: Optional[str] = None  # pullback, breakout, range_fade, compression, etc.
    setup_quality: float = 0.0  # 0.0 to 1.0
    
    # Conditions
    is_compressed: bool = False
    is_stretched: bool = False
    is_at_support: bool = False
    is_at_resistance: bool = False
    breakout_potential: float = 0.0
    reversion_potential: float = 0.0
    
    # Multi-timeframe
    mtf_alignment: str = "mixed"  # aligned_bullish, aligned_bearish, conflicting, mixed
    mtf_alignment_score: float = 0.0  # 0.0 to 1.0
    
    # Evidence
    supporting_factors: list = field(default_factory=list)
    contradicting_factors: list = field(default_factory=list)
    
    # Entry guidance
    preferred_entry_style: str = "wait"  # limit_at_support, stop_entry_above, market_on_confirm
    suggested_invalidation: Optional[float] = None
    suggested_target_zone: Optional[float] = None
    
    # Scores
    overall_technical_score: float = 0.0  # -1.0 to 1.0
    confidence: float = 0.0  # 0.0 to 1.0
    data_quality: float = 1.0
    
    # Raw indicators (for transparency)
    indicators: dict = field(default_factory=dict)


class TechnicalAnalysisAgent(BaseAgent):
    """
    Technical Analysis Agent.
    
    Computes all technical indicators and produces a structured assessment.
    Does NOT output BUY/SELL signals - that's the Orchestrator's job.
    """
    
    def __init__(
        self,
        name: str = "technical_analysis_agent",
        config: Optional[dict[str, Any]] = None,
    ):
        super().__init__(name, config)
        
        self.primary_timeframe = config.get("primary_timeframe", "M30") if config else "M30"
        self.analysis_timeframes = config.get(
            "analysis_timeframes",
            ["M15", "M30", "H1", "H4", "D1"]
        ) if config else ["M15", "M30", "H1", "H4", "D1"]
    
    async def initialize(self) -> None:
        """Initialize the agent."""
        self.is_initialized = True
        self.is_running = True
        self.started_at = datetime.now(timezone.utc)
        self._logger.info("Technical Analysis Agent initialized")
    
    async def run(self, context: dict[str, Any]) -> AgentMessage:
        """
        Compute technical analysis for a symbol.
        
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
        
        return self._create_message(
            message_type="technical_assessment",
            payload=self._assessment_to_dict(assessment),
            symbol=symbol,
            timeframe=self.primary_timeframe,
            confidence=assessment.confidence,
            data_quality=assessment.data_quality,
            warnings=assessment.contradicting_factors[:3] if assessment.contradicting_factors else [],
        )
    
    async def _analyze(
        self,
        symbol: str,
        market_data: dict,
    ) -> TechnicalAssessment:
        """Perform full technical analysis."""
        assessment = TechnicalAssessment(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            primary_timeframe=self.primary_timeframe,
        )
        
        # Get timeframe data
        timeframes_data = market_data.get("timeframes", {})
        
        if not timeframes_data:
            assessment.confidence = 0.0
            assessment.data_quality = 0.0
            return assessment
        
        # Analyze each timeframe
        tf_assessments = {}
        
        for tf in self.analysis_timeframes:
            tf_data = timeframes_data.get(tf)
            if not tf_data or not tf_data.get("bars"):
                continue
            
            bars = tf_data["bars"]
            tf_result = self._analyze_timeframe(bars, tf)
            tf_assessments[tf] = tf_result
            assessment.indicators[tf] = tf_result
        
        # Compute primary timeframe assessment
        primary_data = tf_assessments.get(self.primary_timeframe, {})
        
        if primary_data:
            # Directional assessment
            assessment.directional_lean = self._determine_direction(primary_data)
            assessment.directional_strength = self._calculate_direction_strength(primary_data)
            assessment.trend_quality = self._assess_trend_quality(primary_data)
            
            # Setup detection
            assessment.setup_type, assessment.setup_quality = self._detect_setup(
                primary_data, tf_assessments
            )
            
            # Condition flags
            volatility = primary_data.get("volatility", {})
            assessment.is_compressed = volatility.get("is_compressed", False)
            assessment.is_stretched = self._check_stretched(primary_data)
            
            # Potentials
            assessment.breakout_potential = self._calculate_breakout_potential(primary_data)
            assessment.reversion_potential = self._calculate_reversion_potential(primary_data)
        
        # Multi-timeframe alignment
        assessment.mtf_alignment, assessment.mtf_alignment_score = self._assess_mtf_alignment(
            tf_assessments
        )
        
        # Gather evidence
        assessment.supporting_factors = self._gather_supporting_factors(
            primary_data, tf_assessments, assessment
        )
        assessment.contradicting_factors = self._gather_contradicting_factors(
            primary_data, tf_assessments, assessment
        )
        
        # Calculate overall score
        assessment.overall_technical_score = self._calculate_overall_score(assessment)
        assessment.confidence = self._calculate_confidence(assessment, tf_assessments)
        assessment.data_quality = self._calculate_data_quality(tf_assessments)
        
        # Entry guidance
        assessment.preferred_entry_style = self._determine_entry_style(assessment)
        
        return assessment
    
    def _analyze_timeframe(self, bars: list, timeframe: str) -> dict:
        """Analyze a single timeframe."""
        if len(bars) < 200:
            return {"insufficient_data": True}
        
        # Convert to pandas
        df = pd.DataFrame([{
            "timestamp": b.timestamp if hasattr(b, 'timestamp') else b.get('timestamp'),
            "open": float(b.open if hasattr(b, 'open') else b.get('open')),
            "high": float(b.high if hasattr(b, 'high') else b.get('high')),
            "low": float(b.low if hasattr(b, 'low') else b.get('low')),
            "close": float(b.close if hasattr(b, 'close') else b.get('close')),
            "volume": int(b.tick_volume if hasattr(b, 'tick_volume') else b.get('tick_volume', 0)),
        } for b in bars])
        
        result = {}
        
        # Moving Averages
        ema_cluster = calculate_ema_cluster(df["close"])
        if ema_cluster:
            result["ema_cluster"] = {
                "ema_8": ema_cluster.ema_8,
                "ema_21": ema_cluster.ema_21,
                "ema_50": ema_cluster.ema_50,
                "ema_100": ema_cluster.ema_100,
                "ema_200": ema_cluster.ema_200,
                "is_bullish_aligned": ema_cluster.is_bullish_aligned,
                "is_bearish_aligned": ema_cluster.is_bearish_aligned,
                "alignment_score": ema_cluster.alignment_score(),
            }
        
        sma_baseline = calculate_sma_baseline(df["close"])
        if sma_baseline:
            result["sma_baseline"] = {
                "sma_20": sma_baseline.sma_20,
                "sma_50": sma_baseline.sma_50,
                "sma_200": sma_baseline.sma_200,
            }
        
        # Trend slope
        result["trend_slope"] = calculate_linear_regression_slope(df["close"], 20)
        
        # ADX
        adx_result = calculate_adx(df["high"], df["low"], df["close"])
        if adx_result:
            result["adx"] = adx_result
        
        # RSI
        rsi_result = calculate_rsi(df["close"])
        if rsi_result:
            result["rsi"] = {
                "value": rsi_result.value,
                "zone": rsi_result.zone,
                "is_overbought": rsi_result.is_overbought,
                "is_oversold": rsi_result.is_oversold,
            }
        
        # MACD
        macd_result = calculate_macd(df["close"])
        if macd_result:
            result["macd"] = {
                "macd_line": macd_result.macd_line,
                "signal_line": macd_result.signal_line,
                "histogram": macd_result.histogram,
                "is_bullish": macd_result.is_bullish,
                "histogram_direction": macd_result.histogram_direction,
                "zero_line_position": macd_result.zero_line_position,
            }
        
        # Stochastic
        stoch_result = calculate_stochastic(df["high"], df["low"], df["close"])
        if stoch_result:
            result["stochastic"] = {
                "k": stoch_result.k,
                "d": stoch_result.d,
                "is_overbought": stoch_result.is_overbought,
                "is_oversold": stoch_result.is_oversold,
                "crossover": stoch_result.crossover,
            }
        
        # Volatility
        volatility_state = calculate_volatility_state(df["high"], df["low"], df["close"])
        if volatility_state:
            result["volatility"] = {
                "atr": volatility_state.atr_result.atr,
                "atr_percent": volatility_state.atr_result.atr_percent,
                "atr_percentile": volatility_state.atr_result.percentile,
                "bb_bandwidth": volatility_state.bollinger.bandwidth,
                "bb_percent_b": volatility_state.bollinger.percent_b,
                "is_compressed": volatility_state.is_compressed,
                "is_expanding": volatility_state.is_expanding,
                "volatility_regime": volatility_state.volatility_regime,
            }
        
        # Current price info
        result["current_price"] = float(df["close"].iloc[-1])
        result["prev_day_high"] = float(df["high"].iloc[-1])
        result["prev_day_low"] = float(df["low"].iloc[-1])
        
        return result
    
    def _determine_direction(self, data: dict) -> str:
        """Determine directional lean from indicators."""
        bullish_signals = 0
        bearish_signals = 0
        
        # EMA alignment
        ema = data.get("ema_cluster", {})
        if ema.get("is_bullish_aligned"):
            bullish_signals += 2
        elif ema.get("is_bearish_aligned"):
            bearish_signals += 2
        
        # Trend slope
        slope = data.get("trend_slope", 0)
        if slope > 0:
            bullish_signals += 1
        elif slope < 0:
            bearish_signals += 1
        
        # MACD
        macd = data.get("macd", {})
        if macd.get("is_bullish") and macd.get("zero_line_position") == "above":
            bullish_signals += 1
        elif not macd.get("is_bullish") and macd.get("zero_line_position") == "below":
            bearish_signals += 1
        
        # ADX direction
        adx = data.get("adx", {})
        if adx.get("plus_di", 0) > adx.get("minus_di", 0):
            bullish_signals += 1
        elif adx.get("minus_di", 0) > adx.get("plus_di", 0):
            bearish_signals += 1
        
        if bullish_signals > bearish_signals + 1:
            return "bullish"
        elif bearish_signals > bullish_signals + 1:
            return "bearish"
        return "neutral"
    
    def _calculate_direction_strength(self, data: dict) -> float:
        """Calculate how strong the directional lean is."""
        strength = 0.0
        
        # ADX indicates trend strength
        adx = data.get("adx", {})
        adx_value = adx.get("adx", 0)
        if adx_value > 25:
            strength += 0.3
        elif adx_value > 15:
            strength += 0.15
        
        # EMA alignment
        ema = data.get("ema_cluster", {})
        alignment = abs(ema.get("alignment_score", 0))
        strength += alignment * 0.4
        
        # MACD histogram strength
        macd = data.get("macd", {})
        if macd.get("histogram_direction") == "rising":
            strength += 0.15
        
        return min(strength, 1.0)
    
    def _assess_trend_quality(self, data: dict) -> str:
        """Assess the quality of the current trend."""
        adx = data.get("adx", {})
        adx_value = adx.get("adx", 0)
        ema = data.get("ema_cluster", {})
        
        if adx_value > 25 and (ema.get("is_bullish_aligned") or ema.get("is_bearish_aligned")):
            return "strong_trend"
        elif adx_value > 15:
            return "weak_trend"
        elif adx_value < 15:
            return "range"
        return "transitioning"
    
    def _detect_setup(self, primary: dict, all_tf: dict) -> tuple[Optional[str], float]:
        """Detect the type of setup present."""
        volatility = primary.get("volatility", {})
        rsi = primary.get("rsi", {})
        adx = primary.get("adx", {})
        
        # Compression/breakout
        if volatility.get("is_compressed"):
            return "compression", 0.6
        
        # Pullback in trend
        adx_value = adx.get("adx", 0)
        if adx_value > 20:
            rsi_value = rsi.get("value", 50)
            if 40 < rsi_value < 60:
                return "pullback", 0.7
        
        # Range fade
        if adx_value < 20:
            if rsi.get("is_overbought") or rsi.get("is_oversold"):
                return "range_fade", 0.5
        
        return None, 0.0
    
    def _check_stretched(self, data: dict) -> bool:
        """Check if price is stretched from mean."""
        volatility = data.get("volatility", {})
        percent_b = volatility.get("bb_percent_b", 0.5)
        return percent_b > 0.95 or percent_b < 0.05
    
    def _calculate_breakout_potential(self, data: dict) -> float:
        """Calculate potential for breakout."""
        volatility = data.get("volatility", {})
        if volatility.get("is_compressed"):
            return 0.7
        if volatility.get("atr_percentile", 50) < 20:
            return 0.5
        return 0.2
    
    def _calculate_reversion_potential(self, data: dict) -> float:
        """Calculate potential for mean reversion."""
        rsi = data.get("rsi", {})
        volatility = data.get("volatility", {})
        
        potential = 0.0
        if rsi.get("is_overbought") or rsi.get("is_oversold"):
            potential += 0.4
        
        percent_b = volatility.get("bb_percent_b", 0.5)
        if percent_b > 0.9 or percent_b < 0.1:
            potential += 0.3
        
        return min(potential, 1.0)
    
    def _assess_mtf_alignment(self, tf_data: dict) -> tuple[str, float]:
        """Assess multi-timeframe alignment."""
        directions = []
        weights = {"D1": 3, "H4": 2, "H1": 1.5, "M30": 1, "M15": 0.5}
        
        for tf, data in tf_data.items():
            if data.get("insufficient_data"):
                continue
            ema = data.get("ema_cluster", {})
            if ema.get("is_bullish_aligned"):
                directions.append(("bullish", weights.get(tf, 1)))
            elif ema.get("is_bearish_aligned"):
                directions.append(("bearish", weights.get(tf, 1)))
            else:
                directions.append(("neutral", weights.get(tf, 1)))
        
        if not directions:
            return "mixed", 0.0
        
        bullish_weight = sum(w for d, w in directions if d == "bullish")
        bearish_weight = sum(w for d, w in directions if d == "bearish")
        total_weight = sum(w for _, w in directions)
        
        if total_weight == 0:
            return "mixed", 0.0
        
        if bullish_weight > bearish_weight * 1.5:
            score = bullish_weight / total_weight
            return "aligned_bullish", score
        elif bearish_weight > bullish_weight * 1.5:
            score = bearish_weight / total_weight
            return "aligned_bearish", score
        elif bullish_weight > 0 and bearish_weight > 0:
            return "conflicting", 0.3
        
        return "mixed", 0.5
    
    def _gather_supporting_factors(self, primary: dict, all_tf: dict, assessment) -> list:
        """Gather factors supporting the directional lean."""
        factors = []
        
        if assessment.mtf_alignment.startswith("aligned"):
            factors.append(f"MTF aligned {assessment.mtf_alignment.split('_')[1]}")
        
        adx = primary.get("adx", {})
        if adx.get("trend_strength") == "strong":
            factors.append("Strong trend (ADX > 25)")
        
        macd = primary.get("macd", {})
        if macd.get("histogram_direction") == "rising" and assessment.directional_lean == "bullish":
            factors.append("MACD histogram rising")
        elif macd.get("histogram_direction") == "falling" and assessment.directional_lean == "bearish":
            factors.append("MACD histogram falling")
        
        return factors
    
    def _gather_contradicting_factors(self, primary: dict, all_tf: dict, assessment) -> list:
        """Gather factors contradicting the directional lean."""
        factors = []
        
        if assessment.mtf_alignment == "conflicting":
            factors.append("MTF conflicting signals")
        
        rsi = primary.get("rsi", {})
        if assessment.directional_lean == "bullish" and rsi.get("is_overbought"):
            factors.append("RSI overbought")
        elif assessment.directional_lean == "bearish" and rsi.get("is_oversold"):
            factors.append("RSI oversold")
        
        if assessment.is_stretched:
            factors.append("Price stretched from mean")
        
        return factors
    
    def _calculate_overall_score(self, assessment) -> float:
        """Calculate overall technical score (-1.0 to 1.0)."""
        base_score = 0.0
        
        # Direction
        if assessment.directional_lean == "bullish":
            base_score = assessment.directional_strength
        elif assessment.directional_lean == "bearish":
            base_score = -assessment.directional_strength
        
        # MTF alignment modifier
        if assessment.mtf_alignment == "aligned_bullish":
            base_score += 0.2
        elif assessment.mtf_alignment == "aligned_bearish":
            base_score -= 0.2
        elif assessment.mtf_alignment == "conflicting":
            base_score *= 0.5  # Reduce confidence
        
        return max(-1.0, min(1.0, base_score))
    
    def _calculate_confidence(self, assessment, tf_data: dict) -> float:
        """Calculate confidence in the assessment."""
        confidence = 0.5
        
        # More aligned timeframes = more confidence
        confidence += assessment.mtf_alignment_score * 0.2
        
        # Setup quality adds confidence
        confidence += assessment.setup_quality * 0.2
        
        # Contradicting factors reduce confidence
        confidence -= len(assessment.contradicting_factors) * 0.05
        
        # Trend quality
        if assessment.trend_quality == "strong_trend":
            confidence += 0.1
        elif assessment.trend_quality == "range":
            confidence -= 0.1
        
        return max(0.0, min(1.0, confidence))
    
    def _calculate_data_quality(self, tf_data: dict) -> float:
        """Calculate data quality score."""
        valid_tfs = sum(1 for d in tf_data.values() if not d.get("insufficient_data"))
        total_tfs = len(tf_data)
        return valid_tfs / total_tfs if total_tfs > 0 else 0.0
    
    def _determine_entry_style(self, assessment) -> str:
        """Determine preferred entry style."""
        if assessment.setup_type == "pullback":
            return "limit_at_support"
        elif assessment.setup_type == "compression":
            return "stop_entry_above"
        elif assessment.is_stretched:
            return "wait"
        elif assessment.confidence > 0.7:
            return "market_on_confirm"
        return "wait"
    
    def _assessment_to_dict(self, assessment: TechnicalAssessment) -> dict:
        """Convert assessment to serializable dict."""
        return {
            "symbol": assessment.symbol,
            "timestamp": assessment.timestamp.isoformat(),
            "primary_timeframe": assessment.primary_timeframe,
            "directional_lean": assessment.directional_lean,
            "directional_strength": assessment.directional_strength,
            "trend_quality": assessment.trend_quality,
            "setup_type": assessment.setup_type,
            "setup_quality": assessment.setup_quality,
            "is_compressed": assessment.is_compressed,
            "is_stretched": assessment.is_stretched,
            "breakout_potential": assessment.breakout_potential,
            "reversion_potential": assessment.reversion_potential,
            "mtf_alignment": assessment.mtf_alignment,
            "mtf_alignment_score": assessment.mtf_alignment_score,
            "supporting_factors": assessment.supporting_factors,
            "contradicting_factors": assessment.contradicting_factors,
            "preferred_entry_style": assessment.preferred_entry_style,
            "overall_technical_score": assessment.overall_technical_score,
            "confidence": assessment.confidence,
            "data_quality": assessment.data_quality,
            "indicators": assessment.indicators,
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
