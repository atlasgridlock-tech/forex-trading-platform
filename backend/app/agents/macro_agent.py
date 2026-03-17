"""
Fundamental/Macro Agent

Analyzes macroeconomic data and central bank policies using AI.

Data Sources:
- Economic calendar (Forex Factory, Investing.com)
- Central bank statements
- Key economic indicators
"""

import asyncio
import httpx
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
import re

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


@dataclass
class EconomicEvent:
    """An economic calendar event."""
    currency: str
    event: str
    impact: str  # low, medium, high
    time: datetime
    forecast: Optional[str] = None
    previous: Optional[str] = None
    actual: Optional[str] = None


@dataclass 
class CurrencyFundamentals:
    """Fundamental assessment for a currency."""
    currency: str
    central_bank: str
    current_rate: float
    rate_bias: str  # hawkish, neutral, dovish
    economic_outlook: str
    key_themes: List[str] = field(default_factory=list)
    ai_assessment: Optional[str] = None


class MacroAgent(BaseAgent):
    """
    AI-powered macroeconomic analysis agent.
    
    Responsibilities:
    1. Track economic calendars for high-impact events
    2. Maintain fundamental bias for each currency
    3. Interpret central bank communications
    4. Provide macro context for trade decisions
    """
    
    # Current central bank rates and stance (updated periodically)
    CENTRAL_BANKS = {
        "USD": {"bank": "Federal Reserve", "rate": 5.25, "bias": "hawkish"},
        "EUR": {"bank": "ECB", "rate": 4.50, "bias": "hawkish"},
        "GBP": {"bank": "Bank of England", "rate": 5.25, "bias": "hawkish"},
        "JPY": {"bank": "Bank of Japan", "rate": 0.10, "bias": "dovish"},
        "CHF": {"bank": "SNB", "rate": 1.75, "bias": "neutral"},
        "CAD": {"bank": "Bank of Canada", "rate": 5.00, "bias": "neutral"},
        "AUD": {"bank": "RBA", "rate": 4.35, "bias": "neutral"},
        "NZD": {"bank": "RBNZ", "rate": 5.50, "bias": "hawkish"},
    }
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        super().__init__(
            agent_id="macro_agent",
            name="Macro Agent",
            role="Analyze macroeconomic fundamentals and central bank policy for currency bias",
            redis_url=redis_url,
        )
        
        self.upcoming_events: List[EconomicEvent] = []
        self.currency_fundamentals: Dict[str, CurrencyFundamentals] = {}
        self.last_calendar_fetch = None
        
        # Initialize fundamentals
        self._init_fundamentals()
        
        # Override system prompt
        self.system_prompt = """You are the Macro Agent, a specialized AI economist in a forex trading system.

YOUR ROLE:
- Analyze macroeconomic data and central bank policy
- Maintain fundamental bias (bullish/bearish/neutral) for each major currency
- Interpret economic releases and their market implications
- Provide context for how fundamentals support or oppose technical setups

KEY FUNDAMENTALS TO TRACK:
- Interest rate differentials (most important for forex)
- Inflation trajectories (CPI, Core CPI)
- Employment (NFP, Unemployment Rate)
- Growth (GDP, PMIs)
- Central bank rhetoric (hawkish vs dovish)

ANALYSIS FRAMEWORK:
1. CURRENT STANCE: What is the central bank's current bias?
2. DATA TREND: Is recent data supporting or challenging that stance?
3. RATE EXPECTATIONS: Market pricing for future rate moves
4. RELATIVE VALUE: How does this currency compare to others?
5. KEY RISKS: What could change the outlook?

REMEMBER:
- Forex is about RELATIVE value - always compare currencies
- Interest rate differentials drive long-term trends
- Surprise data moves markets more than expected data
- Central bank forward guidance matters as much as actions

Be concise and actionable. Focus on what matters for trading decisions."""
    
    def _init_fundamentals(self):
        """Initialize currency fundamentals."""
        for currency, cb_data in self.CENTRAL_BANKS.items():
            self.currency_fundamentals[currency] = CurrencyFundamentals(
                currency=currency,
                central_bank=cb_data["bank"],
                current_rate=cb_data["rate"],
                rate_bias=cb_data["bias"],
                economic_outlook="stable",
                key_themes=[],
            )
    
    async def fetch_calendar(self) -> List[EconomicEvent]:
        """Fetch economic calendar (simplified - would use real API in production)."""
        # In production, this would fetch from:
        # - Forex Factory API
        # - Investing.com calendar
        # - TradingEconomics API
        
        # For now, generate some sample upcoming events
        now = datetime.utcnow()
        
        sample_events = [
            EconomicEvent("USD", "Fed Interest Rate Decision", "high", 
                         now + timedelta(days=5), "5.50%", "5.25%"),
            EconomicEvent("USD", "Non-Farm Payrolls", "high",
                         now + timedelta(days=3), "180K", "216K"),
            EconomicEvent("EUR", "ECB Rate Decision", "high",
                         now + timedelta(days=7), "4.50%", "4.50%"),
            EconomicEvent("GBP", "UK CPI", "high",
                         now + timedelta(days=2), "4.0%", "4.2%"),
            EconomicEvent("JPY", "BoJ Policy Statement", "high",
                         now + timedelta(days=4), None, None),
        ]
        
        self.upcoming_events = sample_events
        self.last_calendar_fetch = now
        
        return sample_events
    
    async def analyze_fundamentals(self, currency: str) -> str:
        """Use AI to analyze fundamentals for a currency."""
        fundamentals = self.currency_fundamentals.get(currency)
        if not fundamentals:
            return "Currency not tracked"
        
        # Get relevant upcoming events
        events = [e for e in self.upcoming_events if e.currency == currency]
        events_text = "\n".join([
            f"- {e.event} on {e.time.strftime('%Y-%m-%d')}: Forecast {e.forecast}, Previous {e.previous}"
            for e in events[:5]
        ]) if events else "No major events scheduled"
        
        prompt = f"""Analyze the fundamental outlook for {currency}:

CENTRAL BANK: {fundamentals.central_bank}
CURRENT RATE: {fundamentals.current_rate}%
CURRENT BIAS: {fundamentals.rate_bias}

UPCOMING EVENTS:
{events_text}

Provide your fundamental assessment for {currency}. 
Focus on: rate trajectory, economic health, key risks, and trading bias."""

        response = await self.call_llm(prompt)
        
        # Update fundamentals with AI assessment
        fundamentals.ai_assessment = response
        
        return response
    
    async def get_rate_differential(self, symbol: str) -> Dict[str, Any]:
        """Calculate interest rate differential for a pair."""
        base = symbol[:3]
        quote = symbol[3:]
        
        base_rate = self.CENTRAL_BANKS.get(base, {}).get("rate", 0)
        quote_rate = self.CENTRAL_BANKS.get(quote, {}).get("rate", 0)
        
        differential = base_rate - quote_rate
        
        # Positive differential = bullish for base currency
        bias = "bullish" if differential > 0.5 else "bearish" if differential < -0.5 else "neutral"
        
        return {
            "symbol": symbol,
            "base_currency": base,
            "quote_currency": quote,
            "base_rate": base_rate,
            "quote_rate": quote_rate,
            "differential": differential,
            "carry_bias": bias,
            "explanation": f"{base} yields {base_rate}% vs {quote} at {quote_rate}% = {differential:+.2f}% differential"
        }
    
    async def analyze(self) -> Dict[str, Any]:
        """Main analysis cycle."""
        # Fetch calendar if stale
        if not self.last_calendar_fetch or \
           datetime.utcnow() - self.last_calendar_fetch > timedelta(hours=1):
            await self.fetch_calendar()
        
        # Count high-impact events by currency
        event_counts = {}
        for event in self.upcoming_events:
            if event.impact == "high":
                event_counts[event.currency] = event_counts.get(event.currency, 0) + 1
        
        # Update state
        self.state["current_view"] = {
            "upcoming_high_impact": len([e for e in self.upcoming_events if e.impact == "high"]),
            "events_by_currency": event_counts,
            "rate_differentials": {
                "EURUSD": (await self.get_rate_differential("EURUSD"))["differential"],
                "GBPUSD": (await self.get_rate_differential("GBPUSD"))["differential"],
                "USDJPY": (await self.get_rate_differential("USDJPY"))["differential"],
            },
            "central_bank_biases": {
                currency: data["bias"] 
                for currency, data in self.CENTRAL_BANKS.items()
            },
            "last_update": datetime.utcnow().isoformat(),
        }
        
        self.state["status"] = "active"
        
        return self.state["current_view"]
    
    async def get_view(self, symbol: str = None) -> Dict[str, Any]:
        """Get macro view, optionally for a specific pair."""
        if symbol:
            rate_diff = await self.get_rate_differential(symbol)
            base_fundamentals = self.currency_fundamentals.get(symbol[:3])
            quote_fundamentals = self.currency_fundamentals.get(symbol[3:])
            
            return {
                "symbol": symbol,
                "rate_differential": rate_diff,
                "base_currency": {
                    "currency": symbol[:3],
                    "rate": base_fundamentals.current_rate if base_fundamentals else None,
                    "bias": base_fundamentals.rate_bias if base_fundamentals else None,
                    "assessment": base_fundamentals.ai_assessment if base_fundamentals else None,
                },
                "quote_currency": {
                    "currency": symbol[3:],
                    "rate": quote_fundamentals.current_rate if quote_fundamentals else None,
                    "bias": quote_fundamentals.rate_bias if quote_fundamentals else None,
                    "assessment": quote_fundamentals.ai_assessment if quote_fundamentals else None,
                },
                "upcoming_events": [
                    {
                        "currency": e.currency,
                        "event": e.event,
                        "time": e.time.isoformat(),
                        "impact": e.impact,
                    }
                    for e in self.upcoming_events
                    if e.currency in [symbol[:3], symbol[3:]]
                ][:5],
            }
        
        return {
            "fundamentals": {
                currency: {
                    "rate": f.current_rate,
                    "bias": f.rate_bias,
                    "bank": f.central_bank,
                }
                for currency, f in self.currency_fundamentals.items()
            },
            "upcoming_events": [
                {
                    "currency": e.currency,
                    "event": e.event,
                    "time": e.time.isoformat(),
                    "impact": e.impact,
                }
                for e in sorted(self.upcoming_events, key=lambda x: x.time)[:10]
            ],
            "summary": self.state.get("current_view", {}),
        }
