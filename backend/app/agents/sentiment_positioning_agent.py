"""
Sentiment & Positioning Agent

Analyzes market sentiment and positioning data:
- COT (Commitment of Traders) data
- Retail sentiment indicators
- Options-derived sentiment
- Social media sentiment (optional)
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

from app.agents.base_agent import BaseAgent, AgentOutput


class SentimentBias(Enum):
    """Overall sentiment bias."""
    EXTREMELY_BULLISH = "extremely_bullish"
    BULLISH = "bullish"
    SLIGHTLY_BULLISH = "slightly_bullish"
    NEUTRAL = "neutral"
    SLIGHTLY_BEARISH = "slightly_bearish"
    BEARISH = "bearish"
    EXTREMELY_BEARISH = "extremely_bearish"


class PositioningSignal(Enum):
    """Positioning-based signal."""
    STRONG_CONTRARIAN_LONG = "strong_contrarian_long"  # Retail extremely short
    CONTRARIAN_LONG = "contrarian_long"
    NEUTRAL = "neutral"
    CONTRARIAN_SHORT = "contrarian_short"
    STRONG_CONTRARIAN_SHORT = "strong_contrarian_short"  # Retail extremely long


@dataclass
class COTData:
    """Commitment of Traders data."""
    currency: str
    report_date: datetime
    
    # Commercial positions
    commercial_long: int = 0
    commercial_short: int = 0
    commercial_net: int = 0
    
    # Non-commercial (speculators)
    non_commercial_long: int = 0
    non_commercial_short: int = 0
    non_commercial_net: int = 0
    
    # Changes
    commercial_change: int = 0
    non_commercial_change: int = 0
    
    # Derived metrics
    net_positioning_percentile: float = 0.5  # 0-1, historical percentile


@dataclass
class RetailSentiment:
    """Retail trader sentiment."""
    symbol: str
    timestamp: datetime
    
    # Percentage of retail traders
    long_pct: float = 50.0
    short_pct: float = 50.0
    
    # Ratio
    long_short_ratio: float = 1.0
    
    # Historical context
    percentile_3m: float = 0.5  # Position vs last 3 months


@dataclass
class SentimentAnalysis:
    """Complete sentiment analysis for a symbol."""
    symbol: str
    timestamp: datetime
    
    # Overall assessment
    overall_bias: SentimentBias = SentimentBias.NEUTRAL
    overall_score: float = 0.0  # -1.0 (bearish) to 1.0 (bullish)
    
    # Positioning signal
    positioning_signal: PositioningSignal = PositioningSignal.NEUTRAL
    
    # Component scores
    cot_score: float = 0.0
    retail_score: float = 0.0
    options_score: float = 0.0
    
    # Confidence
    confidence: float = 0.5
    data_freshness: str = "stale"  # "fresh", "recent", "stale"
    
    # Warnings
    warnings: List[str] = field(default_factory=list)


class SentimentPositioningAgent(BaseAgent):
    """Analyzes market sentiment and positioning."""
    
    # Extreme thresholds for contrarian signals
    EXTREME_RETAIL_LONG = 75.0  # Retail > 75% long = contrarian short
    EXTREME_RETAIL_SHORT = 25.0  # Retail < 25% long = contrarian long
    
    COT_EXTREME_PERCENTILE = 0.9  # Top/bottom 10%
    
    def __init__(self, db_session=None, redis_client=None):
        super().__init__(
            name="SentimentPositioningAgent",
            description="Analyzes market sentiment and trader positioning",
            dependencies=["MarketDataAgent"]
        )
        self.db = db_session
        self.redis = redis_client
        
        # Cached data
        self.cot_data: Dict[str, COTData] = {}
        self.retail_sentiment: Dict[str, RetailSentiment] = {}
        self.last_cot_update: Optional[datetime] = None
    
    async def analyze(self, context: Dict[str, Any]) -> AgentOutput:
        """Analyze sentiment for requested symbols."""
        try:
            symbols = context.get("symbols", [])
            
            # Refresh data if needed
            if self._should_refresh_cot():
                await self._fetch_cot_data()
            
            await self._fetch_retail_sentiment(symbols)
            
            analyses = {}
            for symbol in symbols:
                analysis = self._analyze_symbol(symbol)
                analyses[symbol] = {
                    "overall_bias": analysis.overall_bias.value,
                    "overall_score": round(analysis.overall_score, 3),
                    "positioning_signal": analysis.positioning_signal.value,
                    "cot_score": round(analysis.cot_score, 3),
                    "retail_score": round(analysis.retail_score, 3),
                    "confidence": round(analysis.confidence, 2),
                    "data_freshness": analysis.data_freshness,
                    "warnings": analysis.warnings,
                }
            
            return AgentOutput(
                agent_name=self.name,
                timestamp=datetime.utcnow(),
                data={
                    "analyses": analyses,
                    "cot_summary": self._get_cot_summary(),
                    "retail_summary": self._get_retail_summary(),
                },
                confidence=0.7,
                metadata={
                    "cot_last_updated": self.last_cot_update.isoformat() if self.last_cot_update else None,
                    "symbols_analyzed": len(symbols),
                }
            )
            
        except Exception as e:
            self.logger.error(f"Sentiment analysis failed: {e}")
            return AgentOutput(
                agent_name=self.name,
                timestamp=datetime.utcnow(),
                data={},
                confidence=0.0,
                errors=[str(e)]
            )
    
    def _should_refresh_cot(self) -> bool:
        """COT data updates weekly (Friday release)."""
        if not self.last_cot_update:
            return True
        
        # Refresh daily to catch updates
        return datetime.utcnow() - self.last_cot_update > timedelta(days=1)
    
    async def _fetch_cot_data(self):
        """Fetch COT data from source."""
        # TODO: Integrate with actual COT data source (CFTC, Quandl, etc.)
        
        # Placeholder data
        currencies = ["USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD"]
        
        for currency in currencies:
            self.cot_data[currency] = COTData(
                currency=currency,
                report_date=datetime.utcnow() - timedelta(days=3),
                non_commercial_net=0,  # Would be actual data
                net_positioning_percentile=0.5,
            )
        
        self.last_cot_update = datetime.utcnow()
    
    async def _fetch_retail_sentiment(self, symbols: List[str]):
        """Fetch retail sentiment data."""
        # TODO: Integrate with broker sentiment data (OANDA, IG, etc.)
        
        for symbol in symbols:
            # Placeholder - would fetch real data
            self.retail_sentiment[symbol] = RetailSentiment(
                symbol=symbol,
                timestamp=datetime.utcnow(),
                long_pct=52.0,  # Slightly long biased retail
                short_pct=48.0,
                long_short_ratio=1.08,
                percentile_3m=0.55,
            )
    
    def _analyze_symbol(self, symbol: str) -> SentimentAnalysis:
        """Analyze sentiment for a single symbol."""
        analysis = SentimentAnalysis(
            symbol=symbol,
            timestamp=datetime.utcnow(),
        )
        
        # Extract currencies from pair
        base_currency = symbol[:3]
        quote_currency = symbol[3:]
        
        # Analyze COT data
        cot_score = self._analyze_cot(base_currency, quote_currency)
        analysis.cot_score = cot_score
        
        # Analyze retail sentiment
        retail_score, positioning_signal = self._analyze_retail(symbol)
        analysis.retail_score = retail_score
        analysis.positioning_signal = positioning_signal
        
        # Combine scores (COT weighted higher)
        if abs(cot_score) > 0:
            analysis.overall_score = (cot_score * 0.6) + (retail_score * 0.4)
        else:
            analysis.overall_score = retail_score
            analysis.warnings.append("COT data unavailable or stale")
        
        # Determine bias
        analysis.overall_bias = self._score_to_bias(analysis.overall_score)
        
        # Assess data freshness
        analysis.data_freshness = self._assess_freshness(symbol, base_currency)
        
        # Calculate confidence
        analysis.confidence = self._calculate_confidence(analysis)
        
        return analysis
    
    def _analyze_cot(self, base: str, quote: str) -> float:
        """Analyze COT positioning for currency pair."""
        base_cot = self.cot_data.get(base)
        quote_cot = self.cot_data.get(quote)
        
        if not base_cot and not quote_cot:
            return 0.0
        
        base_score = 0.0
        quote_score = 0.0
        
        if base_cot:
            # Convert percentile to score (-1 to 1)
            base_score = (base_cot.net_positioning_percentile - 0.5) * 2
        
        if quote_cot:
            quote_score = (quote_cot.net_positioning_percentile - 0.5) * 2
        
        # Net score (base positive = bullish for pair)
        return base_score - quote_score
    
    def _analyze_retail(self, symbol: str) -> tuple:
        """Analyze retail sentiment (contrarian approach)."""
        sentiment = self.retail_sentiment.get(symbol)
        
        if not sentiment:
            return 0.0, PositioningSignal.NEUTRAL
        
        # Contrarian: when retail is extremely long, we're bearish
        # Score from -1 (retail extremely long = bearish) to 1 (retail extremely short = bullish)
        
        retail_long = sentiment.long_pct
        
        if retail_long >= self.EXTREME_RETAIL_LONG:
            score = -1.0 * ((retail_long - 50) / 50)
            signal = PositioningSignal.STRONG_CONTRARIAN_SHORT
        elif retail_long >= 60:
            score = -0.5 * ((retail_long - 50) / 50)
            signal = PositioningSignal.CONTRARIAN_SHORT
        elif retail_long <= self.EXTREME_RETAIL_SHORT:
            score = 1.0 * ((50 - retail_long) / 50)
            signal = PositioningSignal.STRONG_CONTRARIAN_LONG
        elif retail_long <= 40:
            score = 0.5 * ((50 - retail_long) / 50)
            signal = PositioningSignal.CONTRARIAN_LONG
        else:
            score = 0.0
            signal = PositioningSignal.NEUTRAL
        
        return score, signal
    
    def _score_to_bias(self, score: float) -> SentimentBias:
        """Convert numeric score to sentiment bias."""
        if score >= 0.7:
            return SentimentBias.EXTREMELY_BULLISH
        elif score >= 0.4:
            return SentimentBias.BULLISH
        elif score >= 0.15:
            return SentimentBias.SLIGHTLY_BULLISH
        elif score <= -0.7:
            return SentimentBias.EXTREMELY_BEARISH
        elif score <= -0.4:
            return SentimentBias.BEARISH
        elif score <= -0.15:
            return SentimentBias.SLIGHTLY_BEARISH
        else:
            return SentimentBias.NEUTRAL
    
    def _assess_freshness(self, symbol: str, base: str) -> str:
        """Assess how fresh the sentiment data is."""
        now = datetime.utcnow()
        
        retail = self.retail_sentiment.get(symbol)
        cot = self.cot_data.get(base)
        
        retail_age = (now - retail.timestamp).total_seconds() / 3600 if retail else float('inf')
        cot_age = (now - cot.report_date).days if cot else float('inf')
        
        if retail_age < 1 and cot_age < 4:
            return "fresh"
        elif retail_age < 6 and cot_age < 7:
            return "recent"
        else:
            return "stale"
    
    def _calculate_confidence(self, analysis: SentimentAnalysis) -> float:
        """Calculate confidence in the sentiment analysis."""
        confidence = 0.5
        
        # Higher confidence when signals agree
        if abs(analysis.cot_score) > 0.3 and abs(analysis.retail_score) > 0.3:
            if (analysis.cot_score > 0) == (analysis.retail_score > 0):
                confidence += 0.2  # Agreement
            else:
                confidence -= 0.1  # Disagreement
        
        # Extreme readings = higher confidence
        if abs(analysis.overall_score) > 0.5:
            confidence += 0.1
        
        # Fresh data = higher confidence
        if analysis.data_freshness == "fresh":
            confidence += 0.1
        elif analysis.data_freshness == "stale":
            confidence -= 0.15
        
        return max(0.1, min(0.95, confidence))
    
    def _get_cot_summary(self) -> Dict:
        """Get summary of COT data."""
        return {
            currency: {
                "net_position": data.non_commercial_net,
                "percentile": data.net_positioning_percentile,
                "report_date": data.report_date.isoformat(),
            }
            for currency, data in self.cot_data.items()
        }
    
    def _get_retail_summary(self) -> Dict:
        """Get summary of retail sentiment."""
        return {
            symbol: {
                "long_pct": data.long_pct,
                "short_pct": data.short_pct,
                "ratio": data.long_short_ratio,
            }
            for symbol, data in self.retail_sentiment.items()
        }
    
    def get_positioning_bias(self, symbol: str) -> Dict[str, Any]:
        """Get positioning bias for trading decision."""
        analysis = self._analyze_symbol(symbol)
        
        return {
            "bias": analysis.overall_bias.value,
            "score": analysis.overall_score,
            "signal": analysis.positioning_signal.value,
            "confidence": analysis.confidence,
            "supports_long": analysis.overall_score > 0.1,
            "supports_short": analysis.overall_score < -0.1,
        }
