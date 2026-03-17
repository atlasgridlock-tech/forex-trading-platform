"""
Fundamental Analysis Module
Practical macro analysis per currency with pair-relative logic
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
from datetime import datetime


class CentralBankStance(str, Enum):
    VERY_HAWKISH = "very_hawkish"      # Actively raising rates
    HAWKISH = "hawkish"                 # Signaling tightening
    NEUTRAL = "neutral"                 # Data dependent
    DOVISH = "dovish"                   # Signaling easing
    VERY_DOVISH = "very_dovish"        # Actively cutting rates


class TrendDirection(str, Enum):
    RISING = "rising"
    STABLE = "stable"
    FALLING = "falling"


class RiskLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    ELEVATED = "elevated"
    HIGH = "high"


@dataclass
class CurrencyFundamentals:
    """Fundamental profile for a single currency."""
    currency: str
    last_updated: datetime
    
    # Central Bank
    central_bank: str
    current_rate: float
    rate_path: CentralBankStance = CentralBankStance.NEUTRAL
    rate_differential_rank: int = 4  # 1=highest rates, 8=lowest
    next_meeting: str = ""
    meeting_risk: RiskLevel = RiskLevel.LOW
    
    # Inflation
    inflation_current: float = 0
    inflation_target: float = 2.0
    inflation_trend: TrendDirection = TrendDirection.STABLE
    inflation_surprise: float = 0  # Last print vs expectation
    
    # Employment
    unemployment_rate: float = 0
    employment_trend: TrendDirection = TrendDirection.STABLE
    nfp_or_equivalent: float = 0  # Job creation number
    
    # Growth
    gdp_growth: float = 0
    gdp_trend: TrendDirection = TrendDirection.STABLE
    pmi_manufacturing: float = 50
    pmi_services: float = 50
    
    # Risk Assessment
    policy_surprise_risk: RiskLevel = RiskLevel.LOW
    recession_risk: RiskLevel = RiskLevel.LOW
    
    # Carry
    carry_attractiveness: float = 0  # -100 to 100
    
    # Overall Scores
    macro_strength_score: float = 50  # 0-100
    hawkish_dovish_score: float = 50  # 0=very dovish, 100=very hawkish
    
    def to_dict(self) -> dict:
        return {
            "currency": self.currency,
            "last_updated": self.last_updated.isoformat(),
            "central_bank": self.central_bank,
            "current_rate": self.current_rate,
            "rate_path": self.rate_path.value,
            "rate_differential_rank": self.rate_differential_rank,
            "inflation": {
                "current": self.inflation_current,
                "target": self.inflation_target,
                "trend": self.inflation_trend.value,
                "surprise": self.inflation_surprise,
            },
            "employment": {
                "unemployment": self.unemployment_rate,
                "trend": self.employment_trend.value,
            },
            "growth": {
                "gdp": self.gdp_growth,
                "trend": self.gdp_trend.value,
                "pmi_mfg": self.pmi_manufacturing,
                "pmi_svc": self.pmi_services,
            },
            "risk": {
                "policy_surprise": self.policy_surprise_risk.value,
                "recession": self.recession_risk.value,
            },
            "carry_attractiveness": self.carry_attractiveness,
            "macro_strength_score": self.macro_strength_score,
            "hawkish_dovish_score": self.hawkish_dovish_score,
        }


@dataclass
class PairFundamentals:
    """Fundamental analysis for a currency pair."""
    symbol: str
    base_currency: str
    quote_currency: str
    timestamp: datetime
    
    base_fundamentals: Optional[CurrencyFundamentals] = None
    quote_fundamentals: Optional[CurrencyFundamentals] = None
    
    # Relative analysis
    rate_differential: float = 0
    carry_direction: str = "neutral"  # long/short/neutral
    macro_bias: str = "neutral"  # bullish/bearish/neutral
    macro_bias_strength: float = 0  # 0-100
    
    # Conflicts
    macro_technical_aligned: bool = True
    conflict_description: str = ""
    
    # Recommendations
    confidence_modifier: float = 1.0  # Multiply technical confidence by this
    time_horizon: str = "medium"  # short/medium/long
    event_risk_hours: int = 0  # Hours until next major event
    
    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "base": self.base_currency,
            "quote": self.quote_currency,
            "timestamp": self.timestamp.isoformat(),
            "base_fundamentals": self.base_fundamentals.to_dict() if self.base_fundamentals else None,
            "quote_fundamentals": self.quote_fundamentals.to_dict() if self.quote_fundamentals else None,
            "rate_differential": self.rate_differential,
            "carry_direction": self.carry_direction,
            "macro_bias": self.macro_bias,
            "macro_bias_strength": self.macro_bias_strength,
            "macro_technical_aligned": self.macro_technical_aligned,
            "conflict_description": self.conflict_description,
            "confidence_modifier": self.confidence_modifier,
            "time_horizon": self.time_horizon,
            "event_risk_hours": self.event_risk_hours,
        }


class FundamentalAnalyzer:
    """
    Practical macro analysis engine.
    
    For each currency, monitors:
    - Central bank rate path
    - Inflation trend
    - Employment trend
    - GDP/growth trend
    - Policy surprise risk
    - Recession risk
    - Carry attractiveness
    - Relative hawkish/dovish stance
    """
    
    # Currency to central bank mapping
    CENTRAL_BANKS = {
        "USD": "Federal Reserve",
        "EUR": "European Central Bank",
        "GBP": "Bank of England",
        "JPY": "Bank of Japan",
        "AUD": "Reserve Bank of Australia",
        "NZD": "Reserve Bank of New Zealand",
        "CAD": "Bank of Canada",
        "CHF": "Swiss National Bank",
    }
    
    def __init__(self):
        # Currency profiles (would be updated from data feeds in production)
        self.currency_profiles: Dict[str, CurrencyFundamentals] = {}
        self.pair_analyses: Dict[str, PairFundamentals] = {}
        
        # Initialize with baseline data
        self._initialize_baseline_profiles()
    
    def _initialize_baseline_profiles(self):
        """Initialize baseline fundamental profiles."""
        # These would be updated from real data feeds
        
        self.currency_profiles["USD"] = CurrencyFundamentals(
            currency="USD",
            last_updated=datetime.utcnow(),
            central_bank="Federal Reserve",
            current_rate=5.25,
            rate_path=CentralBankStance.HAWKISH,
            rate_differential_rank=1,
            inflation_current=3.2,
            inflation_target=2.0,
            inflation_trend=TrendDirection.FALLING,
            unemployment_rate=3.8,
            employment_trend=TrendDirection.STABLE,
            gdp_growth=2.5,
            gdp_trend=TrendDirection.STABLE,
            pmi_manufacturing=51,
            pmi_services=54,
            recession_risk=RiskLevel.LOW,
            carry_attractiveness=80,
            macro_strength_score=75,
            hawkish_dovish_score=70,
        )
        
        self.currency_profiles["EUR"] = CurrencyFundamentals(
            currency="EUR",
            last_updated=datetime.utcnow(),
            central_bank="European Central Bank",
            current_rate=4.50,
            rate_path=CentralBankStance.NEUTRAL,
            rate_differential_rank=2,
            inflation_current=2.4,
            inflation_target=2.0,
            inflation_trend=TrendDirection.FALLING,
            unemployment_rate=6.5,
            employment_trend=TrendDirection.STABLE,
            gdp_growth=0.3,
            gdp_trend=TrendDirection.FALLING,
            pmi_manufacturing=46,
            pmi_services=51,
            recession_risk=RiskLevel.MODERATE,
            carry_attractiveness=60,
            macro_strength_score=55,
            hawkish_dovish_score=50,
        )
        
        self.currency_profiles["GBP"] = CurrencyFundamentals(
            currency="GBP",
            last_updated=datetime.utcnow(),
            central_bank="Bank of England",
            current_rate=5.25,
            rate_path=CentralBankStance.HAWKISH,
            rate_differential_rank=1,
            inflation_current=4.0,
            inflation_target=2.0,
            inflation_trend=TrendDirection.FALLING,
            unemployment_rate=4.2,
            employment_trend=TrendDirection.RISING,
            gdp_growth=0.1,
            gdp_trend=TrendDirection.STABLE,
            pmi_manufacturing=47,
            pmi_services=53,
            recession_risk=RiskLevel.MODERATE,
            carry_attractiveness=70,
            macro_strength_score=60,
            hawkish_dovish_score=65,
        )
        
        self.currency_profiles["JPY"] = CurrencyFundamentals(
            currency="JPY",
            last_updated=datetime.utcnow(),
            central_bank="Bank of Japan",
            current_rate=0.10,
            rate_path=CentralBankStance.DOVISH,
            rate_differential_rank=8,
            inflation_current=2.8,
            inflation_target=2.0,
            inflation_trend=TrendDirection.STABLE,
            unemployment_rate=2.5,
            employment_trend=TrendDirection.STABLE,
            gdp_growth=1.8,
            gdp_trend=TrendDirection.RISING,
            pmi_manufacturing=49,
            pmi_services=52,
            recession_risk=RiskLevel.LOW,
            carry_attractiveness=-80,  # Funding currency
            macro_strength_score=50,
            hawkish_dovish_score=20,
        )
        
        self.currency_profiles["AUD"] = CurrencyFundamentals(
            currency="AUD",
            last_updated=datetime.utcnow(),
            central_bank="Reserve Bank of Australia",
            current_rate=4.35,
            rate_path=CentralBankStance.NEUTRAL,
            rate_differential_rank=3,
            inflation_current=3.4,
            inflation_target=2.5,
            inflation_trend=TrendDirection.FALLING,
            unemployment_rate=3.9,
            employment_trend=TrendDirection.STABLE,
            gdp_growth=1.5,
            gdp_trend=TrendDirection.STABLE,
            pmi_manufacturing=47,
            pmi_services=51,
            recession_risk=RiskLevel.LOW,
            carry_attractiveness=50,
            macro_strength_score=55,
            hawkish_dovish_score=50,
        )
        
        self.currency_profiles["NZD"] = CurrencyFundamentals(
            currency="NZD",
            last_updated=datetime.utcnow(),
            central_bank="Reserve Bank of New Zealand",
            current_rate=5.50,
            rate_path=CentralBankStance.HAWKISH,
            rate_differential_rank=1,
            inflation_current=4.7,
            inflation_target=2.0,
            inflation_trend=TrendDirection.FALLING,
            unemployment_rate=4.0,
            employment_trend=TrendDirection.STABLE,
            gdp_growth=0.8,
            gdp_trend=TrendDirection.FALLING,
            recession_risk=RiskLevel.MODERATE,
            carry_attractiveness=75,
            macro_strength_score=55,
            hawkish_dovish_score=60,
        )
        
        self.currency_profiles["CAD"] = CurrencyFundamentals(
            currency="CAD",
            last_updated=datetime.utcnow(),
            central_bank="Bank of Canada",
            current_rate=5.00,
            rate_path=CentralBankStance.NEUTRAL,
            rate_differential_rank=2,
            inflation_current=2.9,
            inflation_target=2.0,
            inflation_trend=TrendDirection.FALLING,
            unemployment_rate=5.8,
            employment_trend=TrendDirection.RISING,
            gdp_growth=1.1,
            gdp_trend=TrendDirection.FALLING,
            recession_risk=RiskLevel.MODERATE,
            carry_attractiveness=55,
            macro_strength_score=55,
            hawkish_dovish_score=50,
        )
        
        self.currency_profiles["CHF"] = CurrencyFundamentals(
            currency="CHF",
            last_updated=datetime.utcnow(),
            central_bank="Swiss National Bank",
            current_rate=1.75,
            rate_path=CentralBankStance.NEUTRAL,
            rate_differential_rank=6,
            inflation_current=1.3,
            inflation_target=2.0,
            inflation_trend=TrendDirection.FALLING,
            unemployment_rate=2.0,
            employment_trend=TrendDirection.STABLE,
            gdp_growth=1.3,
            gdp_trend=TrendDirection.STABLE,
            recession_risk=RiskLevel.LOW,
            carry_attractiveness=30,
            macro_strength_score=65,
            hawkish_dovish_score=40,
        )
    
    def update_currency_profile(self, currency: str, updates: dict):
        """Update a currency's fundamental profile."""
        if currency not in self.currency_profiles:
            return
        
        profile = self.currency_profiles[currency]
        
        for key, value in updates.items():
            if hasattr(profile, key):
                setattr(profile, key, value)
        
        profile.last_updated = datetime.utcnow()
        
        # Recalculate derived scores
        self._recalculate_scores(currency)
    
    def _recalculate_scores(self, currency: str):
        """Recalculate derived scores for a currency."""
        profile = self.currency_profiles.get(currency)
        if not profile:
            return
        
        # Macro strength score (0-100)
        score = 50
        
        # GDP contribution
        if profile.gdp_growth > 2.0:
            score += 15
        elif profile.gdp_growth > 1.0:
            score += 5
        elif profile.gdp_growth < 0:
            score -= 15
        
        # Employment contribution
        if profile.unemployment_rate < 4.0:
            score += 10
        elif profile.unemployment_rate > 6.0:
            score -= 10
        
        # PMI contribution
        if profile.pmi_manufacturing > 52:
            score += 5
        elif profile.pmi_manufacturing < 48:
            score -= 5
        
        if profile.pmi_services > 52:
            score += 5
        elif profile.pmi_services < 48:
            score -= 5
        
        # Inflation on target
        inflation_diff = abs(profile.inflation_current - profile.inflation_target)
        if inflation_diff < 0.5:
            score += 10
        elif inflation_diff > 2.0:
            score -= 10
        
        # Recession risk
        if profile.recession_risk == RiskLevel.HIGH:
            score -= 20
        elif profile.recession_risk == RiskLevel.ELEVATED:
            score -= 10
        
        profile.macro_strength_score = max(0, min(100, score))
        
        # Hawkish/Dovish score (0-100)
        hawk_score = 50
        
        if profile.rate_path == CentralBankStance.VERY_HAWKISH:
            hawk_score += 30
        elif profile.rate_path == CentralBankStance.HAWKISH:
            hawk_score += 15
        elif profile.rate_path == CentralBankStance.DOVISH:
            hawk_score -= 15
        elif profile.rate_path == CentralBankStance.VERY_DOVISH:
            hawk_score -= 30
        
        # Inflation above target = more hawkish pressure
        if profile.inflation_current > profile.inflation_target + 1:
            hawk_score += 10
        elif profile.inflation_current < profile.inflation_target:
            hawk_score -= 5
        
        profile.hawkish_dovish_score = max(0, min(100, hawk_score))
    
    def analyze_pair(self, symbol: str) -> PairFundamentals:
        """
        Analyze fundamentals for a currency pair.
        
        Implements pair-relative logic:
        - If base strengthening and quote weakening = bullish bias
        - If macro conflicts with technical = lower confidence
        - If major event imminent = stand aside or reduce size
        """
        # Parse pair
        base = symbol[:3]
        quote = symbol[3:]
        
        base_fund = self.currency_profiles.get(base)
        quote_fund = self.currency_profiles.get(quote)
        
        analysis = PairFundamentals(
            symbol=symbol,
            base_currency=base,
            quote_currency=quote,
            timestamp=datetime.utcnow(),
            base_fundamentals=base_fund,
            quote_fundamentals=quote_fund,
        )
        
        if not base_fund or not quote_fund:
            return analysis
        
        # Rate differential
        analysis.rate_differential = base_fund.current_rate - quote_fund.current_rate
        
        # Carry direction
        if analysis.rate_differential > 0.5:
            analysis.carry_direction = "long"  # Earn carry by going long
        elif analysis.rate_differential < -0.5:
            analysis.carry_direction = "short"
        else:
            analysis.carry_direction = "neutral"
        
        # Macro bias based on relative strength
        strength_diff = base_fund.macro_strength_score - quote_fund.macro_strength_score
        hawk_diff = base_fund.hawkish_dovish_score - quote_fund.hawkish_dovish_score
        
        # Combined relative score
        relative_score = (strength_diff * 0.6) + (hawk_diff * 0.4)
        
        if relative_score > 15:
            analysis.macro_bias = "bullish"
            analysis.macro_bias_strength = min(abs(relative_score), 100)
        elif relative_score < -15:
            analysis.macro_bias = "bearish"
            analysis.macro_bias_strength = min(abs(relative_score), 100)
        else:
            analysis.macro_bias = "neutral"
            analysis.macro_bias_strength = abs(relative_score)
        
        # Confidence modifier based on macro clarity
        if analysis.macro_bias_strength > 30:
            analysis.confidence_modifier = 1.1  # Boost confidence
        elif analysis.macro_bias_strength < 10:
            analysis.confidence_modifier = 0.9  # Reduce confidence
        
        # Time horizon based on rate path alignment
        if base_fund.rate_path == quote_fund.rate_path:
            analysis.time_horizon = "short"  # Less macro edge, trade shorter
        elif (base_fund.rate_path in [CentralBankStance.HAWKISH, CentralBankStance.VERY_HAWKISH] and 
              quote_fund.rate_path in [CentralBankStance.DOVISH, CentralBankStance.VERY_DOVISH]):
            analysis.time_horizon = "long"  # Strong divergence, can hold longer
        else:
            analysis.time_horizon = "medium"
        
        # Event risk (would be populated from calendar in production)
        # For now, use meeting risk levels
        if base_fund.meeting_risk == RiskLevel.HIGH or quote_fund.meeting_risk == RiskLevel.HIGH:
            analysis.event_risk_hours = 24
        elif base_fund.meeting_risk == RiskLevel.ELEVATED or quote_fund.meeting_risk == RiskLevel.ELEVATED:
            analysis.event_risk_hours = 48
        
        self.pair_analyses[symbol] = analysis
        return analysis
    
    def check_macro_technical_alignment(
        self,
        symbol: str,
        technical_direction: str  # "bullish" or "bearish"
    ) -> Tuple[bool, str, float]:
        """
        Check if macro supports technical setup.
        
        Returns:
            (aligned: bool, message: str, confidence_modifier: float)
        """
        analysis = self.pair_analyses.get(symbol)
        if not analysis:
            analysis = self.analyze_pair(symbol)
        
        if analysis.macro_bias == "neutral":
            return True, "Macro is neutral - technical can lead", 1.0
        
        if analysis.macro_bias == technical_direction:
            msg = f"Macro supports {technical_direction} ({analysis.macro_bias_strength:.0f}% strength)"
            return True, msg, analysis.confidence_modifier
        
        # Macro conflicts with technical
        if analysis.macro_bias_strength > 30:
            msg = f"Macro conflicts: {analysis.macro_bias} vs technical {technical_direction}"
            return False, msg, 0.7  # Significant penalty
        else:
            msg = f"Weak macro conflict: {analysis.macro_bias} vs technical {technical_direction}"
            return True, msg, 0.85  # Minor penalty
    
    def get_currency_strength_ranking(self) -> List[Tuple[str, float]]:
        """Get currencies ranked by macro strength."""
        rankings = []
        for currency, profile in self.currency_profiles.items():
            rankings.append((currency, profile.macro_strength_score))
        
        return sorted(rankings, key=lambda x: x[1], reverse=True)
    
    def get_carry_trade_opportunities(self) -> List[dict]:
        """Find attractive carry trade opportunities."""
        opportunities = []
        
        currencies = list(self.currency_profiles.keys())
        
        for i, base in enumerate(currencies):
            for quote in currencies[i+1:]:
                base_fund = self.currency_profiles[base]
                quote_fund = self.currency_profiles[quote]
                
                rate_diff = base_fund.current_rate - quote_fund.current_rate
                
                if abs(rate_diff) > 1.0:  # Meaningful carry
                    symbol = f"{base}{quote}" if rate_diff > 0 else f"{quote}{base}"
                    direction = "long" if rate_diff > 0 else "long"  # Always long the higher yielder
                    
                    opportunities.append({
                        "symbol": symbol,
                        "direction": direction,
                        "rate_differential": abs(rate_diff),
                        "high_yielder": base if rate_diff > 0 else quote,
                        "low_yielder": quote if rate_diff > 0 else base,
                        "risk": "elevated" if min(base_fund.recession_risk.value, quote_fund.recession_risk.value) in ["elevated", "high"] else "normal",
                    })
        
        return sorted(opportunities, key=lambda x: x["rate_differential"], reverse=True)
    
    def get_summary(self, symbol: str) -> dict:
        """Get a summary of fundamental analysis for a pair."""
        analysis = self.pair_analyses.get(symbol)
        if not analysis:
            analysis = self.analyze_pair(symbol)
        
        base_fund = analysis.base_fundamentals
        quote_fund = analysis.quote_fundamentals
        
        return {
            "symbol": symbol,
            "macro_bias": analysis.macro_bias,
            "macro_bias_strength": analysis.macro_bias_strength,
            "rate_differential": analysis.rate_differential,
            "carry_direction": analysis.carry_direction,
            "confidence_modifier": analysis.confidence_modifier,
            "time_horizon": analysis.time_horizon,
            "event_risk_hours": analysis.event_risk_hours,
            "base": {
                "currency": analysis.base_currency,
                "rate": base_fund.current_rate if base_fund else None,
                "rate_path": base_fund.rate_path.value if base_fund else None,
                "strength": base_fund.macro_strength_score if base_fund else None,
            },
            "quote": {
                "currency": analysis.quote_currency,
                "rate": quote_fund.current_rate if quote_fund else None,
                "rate_path": quote_fund.rate_path.value if quote_fund else None,
                "strength": quote_fund.macro_strength_score if quote_fund else None,
            },
            "recommendation": self._get_recommendation(analysis),
        }
    
    def _get_recommendation(self, analysis: PairFundamentals) -> str:
        """Generate a practical recommendation."""
        if not analysis.base_fundamentals or not analysis.quote_fundamentals:
            return "Insufficient data for recommendation"
        
        parts = []
        
        # Bias recommendation
        if analysis.macro_bias == "bullish" and analysis.macro_bias_strength > 20:
            parts.append(f"Macro favors longs on {analysis.symbol}")
        elif analysis.macro_bias == "bearish" and analysis.macro_bias_strength > 20:
            parts.append(f"Macro favors shorts on {analysis.symbol}")
        else:
            parts.append(f"Macro is neutral on {analysis.symbol}")
        
        # Carry consideration
        if abs(analysis.rate_differential) > 1.5:
            if analysis.carry_direction == "long":
                parts.append("Positive carry on longs")
            else:
                parts.append("Positive carry on shorts")
        
        # Event risk
        if analysis.event_risk_hours < 48:
            parts.append(f"⚠️ Event risk within {analysis.event_risk_hours}h")
        
        # Time horizon
        parts.append(f"Suggested horizon: {analysis.time_horizon}")
        
        return "; ".join(parts)
