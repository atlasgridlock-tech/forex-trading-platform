"""
Fundamental Macro Agent

Analyzes macroeconomic factors:
- Interest rate differentials
- GDP and economic growth
- Inflation data
- Central bank policy outlook
- Risk appetite indicators
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

from app.agents.base_agent import BaseAgent, AgentOutput


class MonetaryPolicyStance(Enum):
    """Central bank policy stance."""
    VERY_HAWKISH = "very_hawkish"
    HAWKISH = "hawkish"
    SLIGHTLY_HAWKISH = "slightly_hawkish"
    NEUTRAL = "neutral"
    SLIGHTLY_DOVISH = "slightly_dovish"
    DOVISH = "dovish"
    VERY_DOVISH = "very_dovish"


class EconomicOutlook(Enum):
    """Economic outlook assessment."""
    STRONG_GROWTH = "strong_growth"
    MODERATE_GROWTH = "moderate_growth"
    SLOW_GROWTH = "slow_growth"
    STAGNATION = "stagnation"
    CONTRACTION = "contraction"
    RECESSION = "recession"


class RiskAppetite(Enum):
    """Market risk appetite."""
    RISK_ON = "risk_on"
    NEUTRAL = "neutral"
    RISK_OFF = "risk_off"


@dataclass
class CurrencyFundamentals:
    """Fundamental data for a currency."""
    currency: str
    last_updated: datetime
    
    # Interest rates
    current_rate: float = 0.0
    rate_1y_ago: float = 0.0
    expected_rate_6m: float = 0.0
    rate_trajectory: str = "stable"  # "rising", "stable", "falling"
    
    # Economic data
    gdp_growth_yoy: float = 0.0
    inflation_yoy: float = 0.0
    unemployment_rate: float = 0.0
    
    # Central bank
    central_bank: str = ""
    policy_stance: MonetaryPolicyStance = MonetaryPolicyStance.NEUTRAL
    next_meeting: Optional[datetime] = None
    
    # Outlook
    economic_outlook: EconomicOutlook = EconomicOutlook.MODERATE_GROWTH
    
    # Score
    fundamental_score: float = 0.0  # -1 (weak) to 1 (strong)


@dataclass
class PairFundamentalAnalysis:
    """Fundamental analysis for a currency pair."""
    symbol: str
    timestamp: datetime
    
    # Rate differential
    rate_differential: float = 0.0
    rate_diff_direction: str = "stable"  # "widening", "stable", "narrowing"
    carry_trade_score: float = 0.0
    
    # Growth differential
    growth_differential: float = 0.0
    
    # Policy divergence
    policy_divergence: float = 0.0
    
    # Overall bias
    fundamental_bias: str = "neutral"  # "bullish", "neutral", "bearish"
    fundamental_score: float = 0.0  # -1 to 1
    confidence: float = 0.5
    
    # Supporting data
    base_fundamentals: Optional[CurrencyFundamentals] = None
    quote_fundamentals: Optional[CurrencyFundamentals] = None


class FundamentalMacroAgent(BaseAgent):
    """Analyzes macroeconomic fundamentals."""
    
    # Central banks
    CENTRAL_BANKS = {
        "USD": ("Federal Reserve", "Fed"),
        "EUR": ("European Central Bank", "ECB"),
        "GBP": ("Bank of England", "BoE"),
        "JPY": ("Bank of Japan", "BoJ"),
        "CHF": ("Swiss National Bank", "SNB"),
        "CAD": ("Bank of Canada", "BoC"),
        "AUD": ("Reserve Bank of Australia", "RBA"),
        "NZD": ("Reserve Bank of New Zealand", "RBNZ"),
    }
    
    # Safe haven vs risk currencies
    SAFE_HAVENS = ["USD", "JPY", "CHF"]
    RISK_CURRENCIES = ["AUD", "NZD", "CAD", "GBP"]
    
    def __init__(self, db_session=None, redis_client=None):
        super().__init__(
            name="FundamentalMacroAgent",
            description="Analyzes macroeconomic fundamentals for currencies",
            dependencies=["NewsEventAgent"]
        )
        self.db = db_session
        self.redis = redis_client
        
        # Cached data
        self.fundamentals: Dict[str, CurrencyFundamentals] = {}
        self.risk_appetite: RiskAppetite = RiskAppetite.NEUTRAL
        self.last_update: Optional[datetime] = None
    
    async def analyze(self, context: Dict[str, Any]) -> AgentOutput:
        """Analyze fundamentals for requested symbols."""
        try:
            symbols = context.get("symbols", [])
            
            # Refresh data if needed
            if self._should_refresh():
                await self._fetch_fundamental_data()
            
            # Assess global risk appetite
            self._assess_risk_appetite()
            
            analyses = {}
            for symbol in symbols:
                analysis = self._analyze_pair(symbol)
                analyses[symbol] = {
                    "fundamental_bias": analysis.fundamental_bias,
                    "fundamental_score": round(analysis.fundamental_score, 3),
                    "rate_differential": round(analysis.rate_differential, 2),
                    "rate_diff_direction": analysis.rate_diff_direction,
                    "carry_trade_score": round(analysis.carry_trade_score, 3),
                    "growth_differential": round(analysis.growth_differential, 2),
                    "policy_divergence": round(analysis.policy_divergence, 3),
                    "confidence": round(analysis.confidence, 2),
                }
            
            return AgentOutput(
                agent_name=self.name,
                timestamp=datetime.utcnow(),
                data={
                    "analyses": analyses,
                    "risk_appetite": self.risk_appetite.value,
                    "currency_rankings": self._get_currency_rankings(),
                    "rate_summary": self._get_rate_summary(),
                },
                confidence=0.6,
                metadata={
                    "last_updated": self.last_update.isoformat() if self.last_update else None,
                    "symbols_analyzed": len(symbols),
                }
            )
            
        except Exception as e:
            self.logger.error(f"Fundamental analysis failed: {e}")
            return AgentOutput(
                agent_name=self.name,
                timestamp=datetime.utcnow(),
                data={},
                confidence=0.0,
                errors=[str(e)]
            )
    
    def _should_refresh(self) -> bool:
        """Check if data needs refresh (daily)."""
        if not self.last_update:
            return True
        return datetime.utcnow() - self.last_update > timedelta(hours=12)
    
    async def _fetch_fundamental_data(self):
        """Fetch fundamental data from sources."""
        # TODO: Integrate with real data sources (Trading Economics, FRED, etc.)
        
        # Placeholder data (would be real data in production)
        self.fundamentals = {
            "USD": CurrencyFundamentals(
                currency="USD",
                last_updated=datetime.utcnow(),
                current_rate=5.25,
                expected_rate_6m=5.00,
                rate_trajectory="stable",
                gdp_growth_yoy=2.4,
                inflation_yoy=3.2,
                unemployment_rate=3.7,
                central_bank="Federal Reserve",
                policy_stance=MonetaryPolicyStance.HAWKISH,
                economic_outlook=EconomicOutlook.MODERATE_GROWTH,
                fundamental_score=0.6,
            ),
            "EUR": CurrencyFundamentals(
                currency="EUR",
                last_updated=datetime.utcnow(),
                current_rate=4.50,
                expected_rate_6m=4.25,
                rate_trajectory="falling",
                gdp_growth_yoy=0.5,
                inflation_yoy=2.4,
                unemployment_rate=6.4,
                central_bank="European Central Bank",
                policy_stance=MonetaryPolicyStance.SLIGHTLY_HAWKISH,
                economic_outlook=EconomicOutlook.SLOW_GROWTH,
                fundamental_score=0.2,
            ),
            "GBP": CurrencyFundamentals(
                currency="GBP",
                last_updated=datetime.utcnow(),
                current_rate=5.25,
                expected_rate_6m=5.00,
                rate_trajectory="stable",
                gdp_growth_yoy=0.3,
                inflation_yoy=3.4,
                unemployment_rate=4.2,
                central_bank="Bank of England",
                policy_stance=MonetaryPolicyStance.HAWKISH,
                economic_outlook=EconomicOutlook.SLOW_GROWTH,
                fundamental_score=0.3,
            ),
            "JPY": CurrencyFundamentals(
                currency="JPY",
                last_updated=datetime.utcnow(),
                current_rate=0.10,
                expected_rate_6m=0.25,
                rate_trajectory="rising",
                gdp_growth_yoy=1.8,
                inflation_yoy=2.8,
                unemployment_rate=2.5,
                central_bank="Bank of Japan",
                policy_stance=MonetaryPolicyStance.SLIGHTLY_DOVISH,
                economic_outlook=EconomicOutlook.MODERATE_GROWTH,
                fundamental_score=-0.2,
            ),
            "CHF": CurrencyFundamentals(
                currency="CHF",
                last_updated=datetime.utcnow(),
                current_rate=1.75,
                expected_rate_6m=1.50,
                rate_trajectory="falling",
                gdp_growth_yoy=0.7,
                inflation_yoy=1.4,
                unemployment_rate=2.0,
                central_bank="Swiss National Bank",
                policy_stance=MonetaryPolicyStance.NEUTRAL,
                economic_outlook=EconomicOutlook.SLOW_GROWTH,
                fundamental_score=0.1,
            ),
            "CAD": CurrencyFundamentals(
                currency="CAD",
                last_updated=datetime.utcnow(),
                current_rate=5.00,
                expected_rate_6m=4.50,
                rate_trajectory="falling",
                gdp_growth_yoy=1.1,
                inflation_yoy=2.8,
                unemployment_rate=6.1,
                central_bank="Bank of Canada",
                policy_stance=MonetaryPolicyStance.NEUTRAL,
                economic_outlook=EconomicOutlook.SLOW_GROWTH,
                fundamental_score=0.2,
            ),
            "AUD": CurrencyFundamentals(
                currency="AUD",
                last_updated=datetime.utcnow(),
                current_rate=4.35,
                expected_rate_6m=4.10,
                rate_trajectory="stable",
                gdp_growth_yoy=1.5,
                inflation_yoy=3.6,
                unemployment_rate=4.1,
                central_bank="Reserve Bank of Australia",
                policy_stance=MonetaryPolicyStance.SLIGHTLY_HAWKISH,
                economic_outlook=EconomicOutlook.MODERATE_GROWTH,
                fundamental_score=0.3,
            ),
            "NZD": CurrencyFundamentals(
                currency="NZD",
                last_updated=datetime.utcnow(),
                current_rate=5.50,
                expected_rate_6m=5.25,
                rate_trajectory="stable",
                gdp_growth_yoy=0.8,
                inflation_yoy=4.0,
                unemployment_rate=4.3,
                central_bank="Reserve Bank of New Zealand",
                policy_stance=MonetaryPolicyStance.HAWKISH,
                economic_outlook=EconomicOutlook.SLOW_GROWTH,
                fundamental_score=0.25,
            ),
        }
        
        self.last_update = datetime.utcnow()
    
    def _assess_risk_appetite(self):
        """Assess global risk appetite."""
        # Would use real indicators (VIX, credit spreads, etc.)
        # Placeholder: neutral
        self.risk_appetite = RiskAppetite.NEUTRAL
    
    def _analyze_pair(self, symbol: str) -> PairFundamentalAnalysis:
        """Analyze fundamentals for a currency pair."""
        base = symbol[:3]
        quote = symbol[3:]
        
        base_fund = self.fundamentals.get(base)
        quote_fund = self.fundamentals.get(quote)
        
        analysis = PairFundamentalAnalysis(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            base_fundamentals=base_fund,
            quote_fundamentals=quote_fund,
        )
        
        if not base_fund or not quote_fund:
            return analysis
        
        # Rate differential (base - quote)
        analysis.rate_differential = base_fund.current_rate - quote_fund.current_rate
        
        # Rate trajectory
        if base_fund.rate_trajectory == "rising" and quote_fund.rate_trajectory != "rising":
            analysis.rate_diff_direction = "widening"
        elif base_fund.rate_trajectory == "falling" and quote_fund.rate_trajectory != "falling":
            analysis.rate_diff_direction = "narrowing"
        else:
            analysis.rate_diff_direction = "stable"
        
        # Carry trade score (positive = favorable carry for long)
        analysis.carry_trade_score = analysis.rate_differential / 10  # Normalize
        
        # Growth differential
        analysis.growth_differential = base_fund.gdp_growth_yoy - quote_fund.gdp_growth_yoy
        
        # Policy divergence
        policy_scores = {
            MonetaryPolicyStance.VERY_HAWKISH: 3,
            MonetaryPolicyStance.HAWKISH: 2,
            MonetaryPolicyStance.SLIGHTLY_HAWKISH: 1,
            MonetaryPolicyStance.NEUTRAL: 0,
            MonetaryPolicyStance.SLIGHTLY_DOVISH: -1,
            MonetaryPolicyStance.DOVISH: -2,
            MonetaryPolicyStance.VERY_DOVISH: -3,
        }
        base_policy = policy_scores.get(base_fund.policy_stance, 0)
        quote_policy = policy_scores.get(quote_fund.policy_stance, 0)
        analysis.policy_divergence = (base_policy - quote_policy) / 6  # Normalize
        
        # Overall fundamental score
        analysis.fundamental_score = (
            analysis.carry_trade_score * 0.3 +
            (analysis.growth_differential / 5) * 0.3 +
            analysis.policy_divergence * 0.4
        )
        
        # Apply risk appetite adjustment
        if self.risk_appetite == RiskAppetite.RISK_OFF:
            if base in self.SAFE_HAVENS:
                analysis.fundamental_score += 0.1
            if base in self.RISK_CURRENCIES:
                analysis.fundamental_score -= 0.1
        elif self.risk_appetite == RiskAppetite.RISK_ON:
            if base in self.RISK_CURRENCIES:
                analysis.fundamental_score += 0.1
            if base in self.SAFE_HAVENS:
                analysis.fundamental_score -= 0.1
        
        # Determine bias
        if analysis.fundamental_score > 0.15:
            analysis.fundamental_bias = "bullish"
        elif analysis.fundamental_score < -0.15:
            analysis.fundamental_bias = "bearish"
        else:
            analysis.fundamental_bias = "neutral"
        
        # Confidence based on data freshness and divergence clarity
        analysis.confidence = 0.5
        if abs(analysis.policy_divergence) > 0.3:
            analysis.confidence += 0.15
        if abs(analysis.rate_differential) > 1.0:
            analysis.confidence += 0.1
        
        return analysis
    
    def _get_currency_rankings(self) -> List[Dict]:
        """Rank currencies by fundamental strength."""
        rankings = []
        
        for currency, fund in self.fundamentals.items():
            rankings.append({
                "currency": currency,
                "score": fund.fundamental_score,
                "rate": fund.current_rate,
                "policy": fund.policy_stance.value,
                "outlook": fund.economic_outlook.value,
            })
        
        return sorted(rankings, key=lambda x: x["score"], reverse=True)
    
    def _get_rate_summary(self) -> Dict:
        """Get summary of interest rates."""
        return {
            currency: {
                "current": fund.current_rate,
                "expected_6m": fund.expected_rate_6m,
                "trajectory": fund.rate_trajectory,
            }
            for currency, fund in self.fundamentals.items()
        }
    
    def get_fundamental_bias(self, symbol: str) -> Dict[str, Any]:
        """Get fundamental bias for trading decision."""
        analysis = self._analyze_pair(symbol)
        
        return {
            "bias": analysis.fundamental_bias,
            "score": analysis.fundamental_score,
            "rate_differential": analysis.rate_differential,
            "carry_favorable": analysis.carry_trade_score > 0,
            "supports_long": analysis.fundamental_score > 0.1,
            "supports_short": analysis.fundamental_score < -0.1,
            "confidence": analysis.confidence,
        }
