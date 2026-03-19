"""
Fundamental Macro Agent - Oracle
Currency profiling and macro-fundamental analysis
"""

import os
import sys
import json
import asyncio
import httpx
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from enum import Enum

# Add shared module to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared import (
    call_claude,
    get_agent_url,
    post_json,
    ChatRequest,
)

app = FastAPI(title="Oracle - Fundamental Macro Agent", version="2.1")

AGENT_NAME = "Oracle"
ORCHESTRATOR_URL = get_agent_url("orchestrator")
FRED_API_KEY = os.getenv("FRED_API_KEY", "")

# FRED API Series IDs for each indicator
FRED_SERIES = {
    "USD": {
        "rate": "FEDFUNDS",           # Federal Funds Rate
        "cpi": "CPIAUCSL",            # CPI All Urban Consumers
        "core_cpi": "CPILFESL",       # Core CPI (Less Food & Energy)
        "gdp": "GDP",                  # Gross Domestic Product
        "unemployment": "UNRATE",      # Unemployment Rate
        "wage_growth": "CES0500000003" # Average Hourly Earnings
    },
    "EUR": {
        "rate": "ECBMRRFR",           # ECB Main Refinancing Rate (proxy)
        "cpi": "CP0000EZ19M086NEST",  # Euro Area HICP
        "unemployment": "LRHUTTTTEZM156S"  # Euro Area Unemployment
    },
    "GBP": {
        "rate": "BOERUKM",            # BOE Official Bank Rate (proxy)
        "cpi": "GBRCPIALLMINMEI",     # UK CPI
        "unemployment": "LMUNRRTTGBM156S"  # UK Unemployment
    },
    "JPY": {
        "rate": "IRSTCI01JPM156N",    # Japan Interest Rate
        "cpi": "JPNCPIALLMINMEI",     # Japan CPI
        "unemployment": "LRUNTTTTJPM156S"  # Japan Unemployment
    }
}

# Cache for FRED data
fred_data_cache: Dict[str, dict] = {}
fred_cache_time: datetime = None
FRED_CACHE_HOURS = 1  # Refresh every 1 hour

# Currency and pair definitions
CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD"]
PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "GBPJPY", "USDCHF", "USDCAD", "EURAUD", "AUDNZD", "AUDUSD"]

# Analysis cache
currency_profiles: Dict[str, dict] = {}
pair_analysis: Dict[str, dict] = {}

# Using ChatRequest from shared module

class Stance(str, Enum):
    VERY_HAWKISH = "very_hawkish"
    HAWKISH = "hawkish"
    NEUTRAL = "neutral"
    DOVISH = "dovish"
    VERY_DOVISH = "very_dovish"


class Trend(str, Enum):
    IMPROVING = "improving"
    STABLE = "stable"
    DETERIORATING = "deteriorating"


# ═══════════════════════════════════════════════════════════════
# FRED API Functions - Real Economic Data
# ═══════════════════════════════════════════════════════════════

async def fetch_fred_series(series_id: str) -> Optional[float]:
    """Fetch latest value from FRED API using pooled client."""
    if not FRED_API_KEY:
        return None
    
    try:
        # Use pooled HTTP client
        from shared import get_pooled_client
        client = await get_pooled_client()
        
        response = await client.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={
                "series_id": series_id,
                "api_key": FRED_API_KEY,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 5
            },
            timeout=10.0
        )
        
        if response.status_code == 200:
            data = response.json()
            observations = data.get("observations", [])
            for obs in observations:
                value = obs.get("value", ".")
                if value != ".":
                    return float(value)
    except Exception as e:
        print(f"[Oracle] Error fetching FRED {series_id}: {e}")
    
    return None


async def fetch_all_fred_data() -> Dict[str, dict]:
    """Fetch all economic indicators from FRED."""
    global fred_data_cache, fred_cache_time
    
    # Check cache
    if fred_cache_time and (datetime.utcnow() - fred_cache_time).total_seconds() < FRED_CACHE_HOURS * 3600:
        if fred_data_cache:
            return fred_data_cache
    
    print("[Oracle] 📊 Fetching real macro data from FRED...")
    
    result = {}
    
    for currency, series_map in FRED_SERIES.items():
        result[currency] = {}
        for indicator, series_id in series_map.items():
            value = await fetch_fred_series(series_id)
            if value is not None:
                result[currency][indicator] = value
                print(f"[Oracle] ✅ {currency} {indicator}: {value}")
    
    if result:
        fred_data_cache = result
        fred_cache_time = datetime.utcnow()
        print(f"[Oracle] ✅ Loaded real FRED data for {len(result)} currencies")
    
    return result


def get_rate_trend(current: float, currency: str) -> str:
    """Determine rate trend based on historical context."""
    # Simplified logic - in production would compare to historical values
    if currency == "USD" and current > 5.0:
        return "peaked"
    elif currency == "JPY" and current < 0.5:
        return "bottomed"
    elif current > 4.0:
        return "elevated"
    else:
        return "stable"


def update_macro_data_from_fred(fred_data: Dict[str, dict]):
    """Update MACRO_DATA with real FRED values."""
    global MACRO_DATA
    
    for currency, indicators in fred_data.items():
        if currency in MACRO_DATA:
            if "rate" in indicators:
                MACRO_DATA[currency]["rate"] = round(indicators["rate"], 2)
                MACRO_DATA[currency]["rate_trend"] = get_rate_trend(indicators["rate"], currency)
            if "cpi" in indicators:
                # FRED CPI is index, need to calculate YoY change
                # For now, use a reasonable approximation
                MACRO_DATA[currency]["cpi"] = round(indicators["cpi"] / 100 * 3.5, 1) if indicators["cpi"] > 100 else indicators["cpi"]
            if "core_cpi" in indicators:
                MACRO_DATA[currency]["core_cpi"] = round(indicators["core_cpi"] / 100 * 3.8, 1) if indicators["core_cpi"] > 100 else indicators["core_cpi"]
            if "unemployment" in indicators:
                MACRO_DATA[currency]["unemployment"] = round(indicators["unemployment"], 1)
            if "gdp" in indicators:
                MACRO_DATA[currency]["gdp"] = round(indicators["gdp"] / 1000, 1)  # Convert to trillions
            if "wage_growth" in indicators:
                MACRO_DATA[currency]["wage_growth"] = round(indicators["wage_growth"], 1)


# ═══════════════════════════════════════════════════════════════
# DYNAMIC DATA - Live Events, Trends & Narratives
# ═══════════════════════════════════════════════════════════════

# Cache for dynamic narratives
dynamic_narratives: Dict[str, dict] = {}
narrative_cache_time: datetime = None
NARRATIVE_CACHE_HOURS = 1  # Refresh narratives every hour

# Agent URLs
SENTINEL_URL = get_agent_url("news")  # News agent has economic calendar AND headlines


async def fetch_upcoming_events_from_sentinel() -> Dict[str, List[dict]]:
    """Fetch upcoming economic events from Sentinel (News Agent)."""
    events_by_currency = {curr: [] for curr in CURRENCIES}
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Fetch calendar from Sentinel
            response = await client.get(f"{SENTINEL_URL}/api/calendar")
            if response.status_code == 200:
                calendar = response.json()
                events = calendar.get("events", calendar.get("upcoming", []))
                
                now = datetime.utcnow()
                for event in events:
                    # Parse event date
                    event_date_str = event.get("date") or event.get("datetime", "")
                    try:
                        if "T" in event_date_str:
                            event_date = datetime.fromisoformat(event_date_str.replace("Z", ""))
                        else:
                            event_date = datetime.strptime(event_date_str, "%Y-%m-%d")
                    except:
                        continue
                    
                    # Only include events in next 14 days
                    days_until = (event_date - now).days
                    if 0 <= days_until <= 14:
                        currency = event.get("currency", "").upper()
                        if currency in events_by_currency:
                            events_by_currency[currency].append({
                                "event": event.get("title") or event.get("event", "Unknown"),
                                "days": days_until,
                                "impact": event.get("impact", "medium"),
                                "date": event_date.strftime("%Y-%m-%d")
                            })
                
                print(f"[Oracle] 📅 Loaded {sum(len(v) for v in events_by_currency.values())} upcoming events from Sentinel")
    except Exception as e:
        print(f"[Oracle] ⚠️ Could not fetch events from Sentinel: {e}")
    
    return events_by_currency


async def fetch_news_headlines() -> Dict[str, List[str]]:
    """Fetch recent news headlines from Sentinel (News Agent)."""
    headlines_by_currency = {curr: [] for curr in CURRENCIES}
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Fetch headlines from Sentinel
            response = await client.get(f"{SENTINEL_URL}/api/headlines")
            if response.status_code == 200:
                news_data = response.json()
                
                # Process headlines - they may be in different formats
                headlines_list = news_data if isinstance(news_data, list) else news_data.get("headlines", [])
                
                for item in headlines_list:
                    # Handle both string headlines and dict objects
                    if isinstance(item, str):
                        headline = item
                    else:
                        headline = item.get("title") or item.get("headline", "")
                    
                    if not headline:
                        continue
                    
                    # Map to currencies mentioned
                    headline_upper = headline.upper()
                    for curr in CURRENCIES:
                        # Check for currency mentions
                        currency_keywords = {
                            "USD": ["FED", "FEDERAL RESERVE", "DOLLAR", "US ", "U.S.", "POWELL", "FOMC"],
                            "EUR": ["ECB", "EURO", "EUROZONE", "LAGARDE", "GERMANY", "EUROPE", "FRANCE"],
                            "GBP": ["BOE", "BANK OF ENGLAND", "POUND", "STERLING", "UK ", "BAILEY", "BRITAIN"],
                            "JPY": ["BOJ", "BANK OF JAPAN", "YEN", "JAPAN", "UEDA", "TOKYO"],
                            "CHF": ["SNB", "SWISS", "FRANC", "SWITZERLAND"],
                            "CAD": ["BOC", "CANADA", "LOONIE", "MACKLEM", "OTTAWA"],
                            "AUD": ["RBA", "AUSTRALIA", "AUSSIE", "SYDNEY"],
                            "NZD": ["RBNZ", "NEW ZEALAND", "KIWI", "WELLINGTON"]
                        }
                        if any(kw in headline_upper for kw in currency_keywords.get(curr, [])):
                            if headline not in headlines_by_currency[curr]:
                                headlines_by_currency[curr].append(headline)
                
                total = sum(len(v) for v in headlines_by_currency.values())
                print(f"[Oracle] 📰 Mapped {total} headlines to currencies from Sentinel")
    except Exception as e:
        print(f"[Oracle] ⚠️ Could not fetch headlines from Sentinel: {e}")
    
    return headlines_by_currency


async def analyze_cb_tone_from_news(currency: str, headlines: List[str]) -> dict:
    """Use Claude to analyze central bank tone from recent headlines."""
    if not headlines:
        return {"cb_tone": "neutral", "confidence": 30}
    
    cb_names = {
        "USD": "Federal Reserve (Fed)",
        "EUR": "European Central Bank (ECB)",
        "GBP": "Bank of England (BoE)",
        "JPY": "Bank of Japan (BoJ)",
        "CHF": "Swiss National Bank (SNB)",
        "CAD": "Bank of Canada (BoC)",
        "AUD": "Reserve Bank of Australia (RBA)",
        "NZD": "Reserve Bank of New Zealand (RBNZ)"
    }
    
    prompt = f"""Analyze these recent headlines about {currency} and the {cb_names.get(currency, 'central bank')}:

{chr(10).join(f'- {h}' for h in headlines[:10])}

Based on these headlines, determine the current central bank tone/stance.
Respond in this exact JSON format only:
{{"cb_tone": "hawkish|slightly_hawkish|neutral|slightly_dovish|dovish", "rate_trend": "hiking|peaked|cutting|bottomed", "confidence": 0-100, "key_point": "one sentence summary"}}"""
    
    try:
        response = await call_claude(prompt, "You are a central bank policy analyst. Respond only with valid JSON.", agent_name="Oracle")
        # Parse JSON from response
        import re
        json_match = re.search(r'\{[^}]+\}', response)
        if json_match:
            return json.loads(json_match.group())
    except Exception as e:
        print(f"[Oracle] ⚠️ CB tone analysis error for {currency}: {e}")
    
    return {"cb_tone": "neutral", "confidence": 30}


async def generate_dynamic_narrative(currency: str, headlines: List[str], events: List[dict], fred_data: dict) -> str:
    """Use Claude to generate a dynamic narrative based on current data."""
    if not headlines and not events:
        return MACRO_DATA.get(currency, {}).get("key_narrative", "No recent data")
    
    # Build context
    context_parts = []
    
    if headlines:
        context_parts.append(f"Recent headlines:\n" + "\n".join(f"- {h}" for h in headlines[:8]))
    
    if events:
        context_parts.append(f"Upcoming events:\n" + "\n".join(f"- {e['event']} in {e['days']} days ({e['impact']} impact)" for e in events[:5]))
    
    if fred_data:
        context_parts.append(f"Current data: Rate={fred_data.get('rate', 'N/A')}%, Unemployment={fred_data.get('unemployment', 'N/A')}%")
    
    prompt = f"""Based on this information about {currency}:

{chr(10).join(context_parts)}

Write a brief key narrative (max 10 words) summarizing the current macro situation for {currency}.
Examples: "Fed patient, soft landing narrative intact" or "ECB pivoting dovish on growth concerns"
Respond with just the narrative text, nothing else."""
    
    try:
        response = await call_claude(prompt, "You are a macro analyst. Be concise.", agent_name="Oracle")
        # Clean up response
        narrative = response.strip().strip('"').strip("'")
        if len(narrative) > 60:
            narrative = narrative[:57] + "..."
        return narrative
    except Exception as e:
        print(f"[Oracle] ⚠️ Narrative generation error for {currency}: {e}")
    
    return MACRO_DATA.get(currency, {}).get("key_narrative", "Analysis pending")


async def update_dynamic_data():
    """Fetch and update all dynamic data (events, narratives, cb_tone)."""
    global dynamic_narratives, narrative_cache_time, MACRO_DATA
    
    # Check cache
    if narrative_cache_time and (datetime.utcnow() - narrative_cache_time).total_seconds() < NARRATIVE_CACHE_HOURS * 3600:
        return
    
    print("[Oracle] 🔄 Updating dynamic narratives and events...")
    
    # Fetch data in parallel
    events_task = fetch_upcoming_events_from_sentinel()
    headlines_task = fetch_news_headlines()
    
    events_by_currency, headlines_by_currency = await asyncio.gather(events_task, headlines_task)
    
    # Update each currency
    for currency in CURRENCIES:
        headlines = headlines_by_currency.get(currency, [])
        events = events_by_currency.get(currency, [])
        fred_data = fred_data_cache.get(currency, {})
        
        # Analyze CB tone if we have headlines
        if headlines:
            tone_analysis = await analyze_cb_tone_from_news(currency, headlines)
            if tone_analysis.get("confidence", 0) > 50:
                MACRO_DATA[currency]["cb_tone"] = tone_analysis.get("cb_tone", MACRO_DATA[currency].get("cb_tone", "neutral"))
                if tone_analysis.get("rate_trend"):
                    MACRO_DATA[currency]["rate_trend"] = tone_analysis.get("rate_trend")
        
        # Generate narrative
        if headlines or events:
            narrative = await generate_dynamic_narrative(currency, headlines, events, fred_data)
            MACRO_DATA[currency]["key_narrative"] = narrative
        
        # Update upcoming events
        if events:
            MACRO_DATA[currency]["upcoming_events"] = events[:5]  # Top 5 events
    
    narrative_cache_time = datetime.utcnow()
    print("[Oracle] ✅ Dynamic data updated for all currencies")


# ═══════════════════════════════════════════════════════════════
# BASE MACRO DATA (Updated with real data on startup)
# ═══════════════════════════════════════════════════════════════

MACRO_DATA = {
    "USD": {
        "rate": 5.25,
        "rate_trend": "peaked",
        "rate_expectations": -0.75,  # Expected change YE
        "cpi": 3.2,
        "cpi_trend": "declining",
        "core_cpi": 3.8,
        "gdp": 2.1,
        "gdp_trend": "stable",
        "unemployment": 3.9,
        "employment_trend": "softening",
        "wage_growth": 4.1,
        "cb_tone": "data_dependent",
        "last_change": "+25bps Jul 2023",
        "next_expected": "-25bps Mar 2024",
        "key_narrative": "Soft landing in progress, Fed patient",
    },
    "EUR": {
        "rate": 4.50,
        "rate_trend": "peaked",
        "rate_expectations": -1.00,
        "cpi": 2.8,
        "cpi_trend": "declining",
        "core_cpi": 3.4,
        "gdp": 0.1,
        "gdp_trend": "stagnant",
        "unemployment": 6.4,
        "employment_trend": "stable",
        "wage_growth": 3.5,
        "cb_tone": "turning_dovish",
        "last_change": "+25bps Sep 2023",
        "next_expected": "-25bps Apr 2024",
        "key_narrative": "Growth concerns, Germany weak, ECB pivoting",
    },
    "GBP": {
        "rate": 5.25,
        "rate_trend": "peaked",
        "rate_expectations": -0.50,
        "cpi": 4.0,
        "cpi_trend": "declining_slowly",
        "core_cpi": 5.1,
        "gdp": 0.3,
        "gdp_trend": "weak",
        "unemployment": 4.2,
        "employment_trend": "stable",
        "wage_growth": 5.8,
        "cb_tone": "cautious_hawkish",
        "last_change": "+25bps Aug 2023",
        "next_expected": "-25bps May 2024",
        "key_narrative": "Sticky inflation vs weak growth dilemma",
    },
    "JPY": {
        "rate": 0.10,
        "rate_trend": "normalizing",
        "rate_expectations": +0.15,
        "cpi": 2.8,
        "cpi_trend": "elevated",
        "core_cpi": 2.5,
        "gdp": 1.2,
        "gdp_trend": "improving",
        "unemployment": 2.5,
        "employment_trend": "tight",
        "wage_growth": 2.0,
        "cb_tone": "shifting_hawkish",
        "last_change": "Exit NIRP Jan 2024",
        "next_expected": "+10bps Q2 2024",
        "key_narrative": "BOJ normalizing, yen strength expected",
    },
    "CHF": {
        "rate": 1.75,
        "rate_trend": "peaked",
        "rate_expectations": -0.25,
        "cpi": 1.3,
        "cpi_trend": "low_stable",
        "core_cpi": 1.5,
        "gdp": 0.8,
        "gdp_trend": "stable",
        "unemployment": 2.0,
        "employment_trend": "strong",
        "wage_growth": 1.5,
        "cb_tone": "neutral",
        "last_change": "+25bps Jun 2023",
        "next_expected": "Hold",
        "key_narrative": "Safe haven, low inflation, SNB comfortable",
    },
    "CAD": {
        "rate": 5.00,
        "rate_trend": "peaked",
        "rate_expectations": -0.75,
        "cpi": 2.9,
        "cpi_trend": "declining",
        "core_cpi": 3.2,
        "gdp": 1.1,
        "gdp_trend": "slowing",
        "unemployment": 5.8,
        "employment_trend": "weakening",
        "wage_growth": 4.5,
        "cb_tone": "turning_dovish",
        "last_change": "+25bps Jul 2023",
        "next_expected": "-25bps Apr 2024",
        "key_narrative": "Housing weakness, rate-sensitive economy",
    },
    "AUD": {
        "rate": 4.35,
        "rate_trend": "peaked",
        "rate_expectations": -0.25,
        "cpi": 3.4,
        "cpi_trend": "sticky",
        "core_cpi": 3.8,
        "gdp": 1.5,
        "gdp_trend": "slowing",
        "unemployment": 3.9,
        "employment_trend": "stable",
        "wage_growth": 4.2,
        "cb_tone": "hawkish_hold",
        "last_change": "+25bps Nov 2023",
        "next_expected": "Hold",
        "key_narrative": "China exposure, RBA cautious on cuts",
    },
    "NZD": {
        "rate": 5.50,
        "rate_trend": "peaked",
        "rate_expectations": -0.50,
        "cpi": 4.7,
        "cpi_trend": "sticky",
        "core_cpi": 4.3,
        "gdp": 0.6,
        "gdp_trend": "weak",
        "unemployment": 4.0,
        "employment_trend": "rising",
        "wage_growth": 4.3,
        "cb_tone": "hawkish_but_watching",
        "last_change": "+25bps May 2023",
        "next_expected": "-25bps Aug 2024",
        "key_narrative": "High rates, but economy slowing sharply",
    },
}

# Upcoming events that affect currencies
UPCOMING_EVENTS = {
    "USD": [
        {"event": "CPI", "days": 3, "impact": "high"},
        {"event": "NFP", "days": 8, "impact": "high"},
        {"event": "FOMC", "days": 15, "impact": "high"},
    ],
    "EUR": [
        {"event": "ECB Meeting", "days": 10, "impact": "high"},
        {"event": "German PMI", "days": 5, "impact": "medium"},
    ],
    "GBP": [
        {"event": "BOE Meeting", "days": 12, "impact": "high"},
        {"event": "UK CPI", "days": 6, "impact": "high"},
    ],
    "JPY": [
        {"event": "BOJ Meeting", "days": 18, "impact": "high"},
        {"event": "Japan CPI", "days": 4, "impact": "medium"},
    ],
}


def calculate_currency_score(data: dict) -> dict:
    """Calculate comprehensive macro score for a currency."""
    scores = {}
    
    # Interest rate stance score (0-100)
    # Higher rates = higher score (generally)
    rate = data.get("rate", 0)
    rate_trend = data.get("rate_trend", "stable")
    rate_exp = data.get("rate_expectations", 0)
    
    rate_score = min(rate * 12, 70)  # Base score from rate level
    if rate_trend == "rising":
        rate_score += 15
    elif rate_trend == "peaked":
        rate_score += 5
    elif rate_trend == "cutting":
        rate_score -= 10
    
    if rate_exp > 0:
        rate_score += 10
    elif rate_exp < -0.5:
        rate_score -= 10
    
    scores["interest_rate"] = min(max(rate_score, 0), 100)
    
    # Inflation score (0-100)
    # Target is ~2%, deviation is negative
    cpi = data.get("cpi", 2)
    cpi_trend = data.get("cpi_trend", "stable")
    
    if cpi < 1:
        inflation_score = 40  # Too low (deflation risk)
    elif 1 <= cpi <= 2.5:
        inflation_score = 80  # Target range
    elif 2.5 < cpi <= 4:
        inflation_score = 60  # Elevated but manageable
    else:
        inflation_score = 40  # Too high
    
    if cpi_trend == "declining":
        inflation_score += 10
    elif cpi_trend == "rising":
        inflation_score -= 15
    
    scores["inflation"] = min(max(inflation_score, 0), 100)
    
    # Growth score (0-100)
    gdp = data.get("gdp", 0)
    gdp_trend = data.get("gdp_trend", "stable")
    
    if gdp < 0:
        growth_score = 20  # Recession
    elif 0 <= gdp < 1:
        growth_score = 40  # Stagnant
    elif 1 <= gdp < 2:
        growth_score = 60  # Moderate
    elif 2 <= gdp < 3:
        growth_score = 75  # Solid
    else:
        growth_score = 85  # Strong
    
    if gdp_trend == "improving":
        growth_score += 10
    elif gdp_trend == "slowing" or gdp_trend == "weak":
        growth_score -= 10
    
    scores["growth"] = min(max(growth_score, 0), 100)
    
    # Employment score (0-100)
    unemployment = data.get("unemployment", 5)
    emp_trend = data.get("employment_trend", "stable")
    
    if unemployment < 4:
        employment_score = 80  # Very tight
    elif 4 <= unemployment < 5:
        employment_score = 70  # Healthy
    elif 5 <= unemployment < 6:
        employment_score = 55  # Normal
    else:
        employment_score = 40  # Weak
    
    if emp_trend == "improving" or emp_trend == "strong":
        employment_score += 10
    elif emp_trend == "weakening" or emp_trend == "rising":
        employment_score -= 10
    
    scores["employment"] = min(max(employment_score, 0), 100)
    
    # CB tone score (0-100)
    tone = data.get("cb_tone", "neutral")
    tone_map = {
        "very_hawkish": 85,
        "hawkish": 70,
        "hawkish_hold": 65,
        "cautious_hawkish": 60,
        "hawkish_but_watching": 58,
        "data_dependent": 55,
        "neutral": 50,
        "turning_dovish": 40,
        "dovish": 30,
        "shifting_hawkish": 60,  # For JPY
    }
    scores["cb_tone"] = tone_map.get(tone, 50)
    
    # Macro momentum (based on trends)
    momentum_factors = [
        1 if rate_trend in ["rising", "normalizing"] else -1 if rate_trend in ["cutting"] else 0,
        1 if cpi_trend in ["declining", "low_stable"] else -1 if cpi_trend in ["rising", "sticky"] else 0,
        1 if gdp_trend in ["improving", "stable"] else -1 if gdp_trend in ["slowing", "weak", "stagnant"] else 0,
        1 if emp_trend in ["improving", "strong", "tight"] else -1 if emp_trend in ["weakening", "rising"] else 0,
    ]
    momentum = 50 + sum(momentum_factors) * 10
    scores["momentum"] = min(max(momentum, 0), 100)
    
    # Overall score (weighted average)
    weights = {
        "interest_rate": 0.25,
        "inflation": 0.15,
        "growth": 0.20,
        "employment": 0.15,
        "cb_tone": 0.15,
        "momentum": 0.10,
    }
    overall = sum(scores[k] * weights[k] for k in weights)
    scores["overall"] = round(overall, 1)
    
    # Determine stance
    if overall >= 70:
        stance = "bullish"
    elif overall >= 55:
        stance = "slightly_bullish"
    elif overall >= 45:
        stance = "neutral"
    elif overall >= 35:
        stance = "slightly_bearish"
    else:
        stance = "bearish"
    
    # Medium-term bias
    if scores["momentum"] >= 60 and overall >= 55:
        medium_term = "bullish"
    elif scores["momentum"] <= 40 or overall <= 45:
        medium_term = "bearish"
    else:
        medium_term = "neutral"
    
    # Event uncertainty
    events = UPCOMING_EVENTS.get(data.get("currency", ""), [])
    high_impact_soon = sum(1 for e in events if e["impact"] == "high" and e["days"] <= 7)
    event_uncertainty = 30 + high_impact_soon * 20
    
    return {
        "scores": scores,
        "overall_score": scores["overall"],
        "stance": stance,
        "medium_term_bias": medium_term,
        "event_uncertainty": min(event_uncertainty, 100),
        "key_narrative": data.get("key_narrative", ""),
        "current_rate": data.get("rate", 0),
        "rate_expectations": data.get("rate_expectations", 0),
    }


def analyze_pair(base: str, quote: str) -> dict:
    """Analyze a currency pair in relative terms."""
    base_profile = currency_profiles.get(base, {})
    quote_profile = currency_profiles.get(quote, {})
    
    if not base_profile or not quote_profile:
        return {"error": "Missing currency profiles"}
    
    base_score = base_profile.get("overall_score", 50)
    quote_score = quote_profile.get("overall_score", 50)
    
    # Score differential
    differential = base_score - quote_score
    
    # Rate differential
    base_rate = base_profile.get("current_rate", 0)
    quote_rate = quote_profile.get("current_rate", 0)
    rate_diff = base_rate - quote_rate
    
    # Determine bias
    if differential >= 10:
        bias = "bullish"
        confidence = min(60 + abs(differential), 90)
    elif differential >= 5:
        bias = "slightly_bullish"
        confidence = 55 + abs(differential)
    elif differential <= -10:
        bias = "bearish"
        confidence = min(60 + abs(differential), 90)
    elif differential <= -5:
        bias = "slightly_bearish"
        confidence = 55 + abs(differential)
    else:
        bias = "neutral"
        confidence = 40
    
    # Time horizon based on macro momentum alignment
    base_momentum = base_profile.get("scores", {}).get("momentum", 50)
    quote_momentum = quote_profile.get("scores", {}).get("momentum", 50)
    
    if abs(base_momentum - quote_momentum) > 20:
        time_horizon = "short_to_medium"  # 2-6 weeks
    else:
        time_horizon = "medium_term"  # 4-12 weeks
    
    # Event sensitivity
    base_uncertainty = base_profile.get("event_uncertainty", 30)
    quote_uncertainty = quote_profile.get("event_uncertainty", 30)
    event_sensitivity = max(base_uncertainty, quote_uncertainty)
    
    # Build reasoning
    reasons = []
    
    if differential > 0:
        reasons.append(f"{base} fundamentally stronger (score {base_score:.0f} vs {quote_score:.0f})")
    else:
        reasons.append(f"{quote} fundamentally stronger (score {quote_score:.0f} vs {base_score:.0f})")
    
    if abs(rate_diff) > 0.5:
        if rate_diff > 0:
            reasons.append(f"Carry favors {base} ({rate_diff:+.2f}% rate diff)")
        else:
            reasons.append(f"Carry favors {quote} ({rate_diff:+.2f}% rate diff)")
    
    reasons.append(f"{base}: {base_profile.get('key_narrative', 'N/A')}")
    reasons.append(f"{quote}: {quote_profile.get('key_narrative', 'N/A')}")
    
    return {
        "pair": f"{base}{quote}",
        "base": {
            "currency": base,
            "score": base_score,
            "stance": base_profile.get("stance", "neutral"),
            "momentum": base_profile.get("scores", {}).get("momentum", 50),
        },
        "quote": {
            "currency": quote,
            "score": quote_score,
            "stance": quote_profile.get("stance", "neutral"),
            "momentum": quote_profile.get("scores", {}).get("momentum", 50),
        },
        "macro_differential": round(differential, 1),
        "rate_differential": round(rate_diff, 2),
        "pair_bias": bias,
        "confidence": round(confidence, 0),
        "time_horizon": time_horizon,
        "event_sensitivity": event_sensitivity,
        "reasoning": reasons,
        "timestamp": datetime.utcnow().isoformat(),
    }


def build_currency_profiles():
    """Build profiles for all currencies."""
    global currency_profiles
    
    for currency, data in MACRO_DATA.items():
        data["currency"] = currency
        profile = calculate_currency_score(data)
        profile["currency"] = currency
        profile["raw_data"] = data
        # Include upcoming events if available
        if "upcoming_events" in data:
            profile["upcoming_events"] = data["upcoming_events"]
        currency_profiles[currency] = profile


def build_pair_analyses():
    """Build analysis for all pairs."""
    global pair_analysis
    
    pair_currencies = {
        "EURUSD": ("EUR", "USD"),
        "GBPUSD": ("GBP", "USD"),
        "USDJPY": ("USD", "JPY"),
        "GBPJPY": ("GBP", "JPY"),
        "USDCHF": ("USD", "CHF"),
        "USDCAD": ("USD", "CAD"),
        "EURAUD": ("EUR", "AUD"),
        "AUDNZD": ("AUD", "NZD"),
        "AUDUSD": ("AUD", "USD"),
    }
    
    for pair, (base, quote) in pair_currencies.items():
        pair_analysis[pair] = analyze_pair(base, quote)


async def send_to_orchestrator(pair: str, analysis: dict):
    """Send analysis to Orchestrator using shared post_json."""
    await post_json(
        f"{ORCHESTRATOR_URL}/api/ingest",
        {
            "agent_id": "macro",
            "agent_name": AGENT_NAME,
            "output_type": "signal",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "symbol": pair,
                "direction": analysis["pair_bias"],
                "confidence": analysis["confidence"] / 100,
                "reason": f"Macro diff {analysis['macro_differential']:+.1f}, {analysis['time_horizon']}",
            },
        }
    )


async def background_analysis():
    """Background analysis loop."""
    while True:
        build_currency_profiles()
        build_pair_analyses()
        
        for pair, analysis in pair_analysis.items():
            await send_to_orchestrator(pair, analysis)
        
        await asyncio.sleep(300)  # Update every 5 minutes (macro is slower)


async def background_dynamic_update():
    """Background loop to update dynamic narratives and events."""
    # Wait a bit for other agents to start
    await asyncio.sleep(30)
    
    while True:
        try:
            await update_dynamic_data()
            # Rebuild profiles with new data
            build_currency_profiles()
            build_pair_analyses()
        except Exception as e:
            print(f"[Oracle] ⚠️ Dynamic update error: {e}")
        
        await asyncio.sleep(NARRATIVE_CACHE_HOURS * 3600)  # Update every hour


# Using shared call_claude - removed duplicate implementation


@app.on_event("startup")
async def startup():
    print(f"🚀 {AGENT_NAME} (Fundamental Macro Agent) v2.1 starting...")
    
    # Fetch real macro data from FRED
    if FRED_API_KEY:
        print("[Oracle] FRED API key configured, fetching real data...")
        fred_data = await fetch_all_fred_data()
        if fred_data:
            update_macro_data_from_fred(fred_data)
            print("[Oracle] ✅ Macro data updated with real FRED values")
        else:
            print("[Oracle] ⚠️ Could not fetch FRED data, using defaults")
    else:
        print("[Oracle] ⚠️ No FRED API key, using default macro data")
    
    build_currency_profiles()
    build_pair_analyses()
    
    # Start background tasks
    asyncio.create_task(background_analysis())
    asyncio.create_task(background_dynamic_update())


@app.get("/", response_class=HTMLResponse)
async def home():
    # Currency profiles section
    currency_html = ""
    for currency in CURRENCIES:
        p = currency_profiles.get(currency, {})
        score = p.get("overall_score", 0)
        stance = p.get("stance", "neutral")
        momentum = p.get("scores", {}).get("momentum", 50)
        rate = p.get("current_rate", 0)
        
        stance_color = "#22c55e" if "bullish" in stance else "#ef4444" if "bearish" in stance else "#888"
        
        currency_html += f'''
        <div class="currency-card">
            <div class="currency-header">
                <span class="currency-name">{currency}</span>
                <span class="currency-score">{score:.0f}</span>
            </div>
            <div class="currency-stance" style="color:{stance_color}">{stance.replace("_", " ").upper()}</div>
            <div class="currency-detail">Rate: {rate}% | Mom: {momentum:.0f}</div>
        </div>
        '''
    
    # Pair analysis section
    pairs_html = ""
    for pair in PAIRS:
        a = pair_analysis.get(pair, {})
        bias = a.get("pair_bias", "neutral")
        conf = a.get("confidence", 0)
        diff = a.get("macro_differential", 0)
        rate_diff = a.get("rate_differential", 0)
        time_h = a.get("time_horizon", "?")
        event_sens = a.get("event_sensitivity", 0)
        
        bias_color = "#22c55e" if "bullish" in bias else "#ef4444" if "bearish" in bias else "#888"
        
        base_info = a.get("base", {})
        quote_info = a.get("quote", {})
        
        pairs_html += f'''
        <div class="pair-card">
            <div class="pair-header">
                <span class="pair-name">{pair}</span>
                <span class="pair-conf">{conf:.0f}%</span>
            </div>
            <div class="pair-bias" style="color:{bias_color}">{bias.upper()}</div>
            <div class="pair-scores">
                <span>{base_info.get("currency", "?")}: {base_info.get("score", 0):.0f}</span>
                <span>vs</span>
                <span>{quote_info.get("currency", "?")}: {quote_info.get("score", 0):.0f}</span>
            </div>
            <div class="pair-detail">Diff: {diff:+.1f} | Rate: {rate_diff:+.2f}%</div>
            <div class="pair-meta">Horizon: {time_h} | Events: {event_sens}%</div>
        </div>
        '''
    
    return f'''<!DOCTYPE html>
<html><head>
    <title>🏛️ Oracle - Macro Agent</title>
    <meta http-equiv="refresh" content="60">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, sans-serif; background: #0a0a0f; color: #e0e0e0; padding: 20px; }}
        .header {{ display: flex; align-items: center; gap: 15px; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid #333; }}
        .header h1 {{ color: #8b5cf6; }}
        .status {{ background: #22c55e20; color: #22c55e; padding: 5px 12px; border-radius: 20px; font-size: 14px; }}
        .section-title {{ color: #8b5cf6; font-size: 16px; margin: 20px 0 15px 0; }}
        .currency-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; }}
        .currency-card {{ background: #1a1a24; border-radius: 8px; padding: 12px; }}
        .currency-header {{ display: flex; justify-content: space-between; margin-bottom: 5px; }}
        .currency-name {{ font-weight: bold; }}
        .currency-score {{ color: #8b5cf6; font-weight: bold; }}
        .currency-stance {{ font-size: 12px; margin-bottom: 5px; }}
        .currency-detail {{ font-size: 11px; color: #666; }}
        .pairs-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-bottom: 20px; }}
        .pair-card {{ background: #1a1a24; border-radius: 10px; padding: 15px; }}
        .pair-header {{ display: flex; justify-content: space-between; margin-bottom: 8px; }}
        .pair-name {{ font-size: 16px; font-weight: bold; }}
        .pair-conf {{ color: #8b5cf6; }}
        .pair-bias {{ font-size: 16px; font-weight: bold; margin-bottom: 8px; }}
        .pair-scores {{ display: flex; gap: 10px; font-size: 12px; color: #888; margin-bottom: 5px; }}
        .pair-detail {{ font-size: 12px; color: #aaa; margin-bottom: 3px; }}
        .pair-meta {{ font-size: 11px; color: #666; }}
        .chat-section {{ background: #1a1a24; border-radius: 12px; padding: 20px; }}
        .chat-section h2 {{ color: #8b5cf6; margin-bottom: 15px; }}
        .chat-messages {{ height: 150px; overflow-y: auto; background: #0a0a0f; border-radius: 8px; padding: 10px; margin-bottom: 10px; }}
        .chat-input {{ display: flex; gap: 10px; }}
        .chat-input input {{ flex: 1; padding: 10px; border-radius: 8px; border: 1px solid #333; background: #0a0a0f; color: #fff; }}
        .chat-input button {{ padding: 10px 20px; background: #8b5cf6; color: #fff; border: none; border-radius: 8px; cursor: pointer; }}
        .message {{ margin: 8px 0; padding: 8px; border-radius: 6px; font-size: 13px; }}
        .message.user {{ background: #333; margin-left: 20%; }}
        .message.agent {{ background: #2d1a4d; margin-right: 20%; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🏛️ Oracle</h1>
        <span class="status">● ANALYZING</span>
        <span style="color: #888; margin-left: auto;">Fundamental Macro Agent v2.0</span>
    </div>
    
    <div class="section-title">📊 Currency Macro Profiles</div>
    <div class="currency-grid">{currency_html}</div>
    
    <div class="section-title">💱 Pair-Relative Analysis</div>
    <div class="pairs-grid">{pairs_html}</div>
    
    <div class="chat-section">
        <h2>💬 Ask Oracle</h2>
        <div class="chat-messages" id="messages"></div>
        <div class="chat-input">
            <input type="text" id="input" placeholder="Ask about macro..." onkeypress="if(event.key==='Enter')sendMessage()">
            <button onclick="sendMessage()">Send</button>
            <button onclick="clearChat()" style="background: #666;">Clear</button>
        </div>
    </div>
    <script>
        const CHAT_KEY = 'oracle_chat_history';
        
        function loadChatHistory() {{
            const messages = document.getElementById('messages');
            const history = localStorage.getItem(CHAT_KEY);
            if (history) {{
                messages.innerHTML = history;
                messages.scrollTop = messages.scrollHeight;
            }}
        }}
        
        function saveChatHistory() {{
            const messages = document.getElementById('messages');
            localStorage.setItem(CHAT_KEY, messages.innerHTML);
        }}
        
        function clearChat() {{
            const messages = document.getElementById('messages');
            messages.innerHTML = '';
            localStorage.removeItem(CHAT_KEY);
        }}
        
        async function sendMessage() {{
            const input = document.getElementById('input');
            const messages = document.getElementById('messages');
            const text = input.value.trim();
            if (!text) return;
            messages.innerHTML += `<div style="margin:5px 0;padding:8px 12px;background:#1a1a24;border-radius:8px;font-size:12px">${{text}}</div>`;
            input.value = '';
            messages.scrollTop = messages.scrollHeight;
            saveChatHistory();
            
            try {{
                const response = await fetch('/chat', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{message: text}})
                }});
                const data = await response.json();
                messages.innerHTML += `<div style="margin:5px 0;padding:8px 12px;background:rgba(249,115,22,0.15);border-left:3px solid #f97316;border-radius:8px;font-size:12px">${{data.response.replace(/\\n/g, '<br>')}}</div>`;
            }} catch (e) {{
                messages.innerHTML += `<div style="margin:5px 0;padding:8px 12px;background:rgba(239,68,68,0.15);border-radius:8px;font-size:12px;color:#ef4444">Error: ${{e.message}}</div>`;
            }}
            messages.scrollTop = messages.scrollHeight;
            saveChatHistory();
        }}
        
        document.addEventListener('DOMContentLoaded', loadChatHistory);
    </script>
</body>
</html>'''


@app.post("/chat")
async def chat(request: ChatRequest):
    # Build a complete context for Claude with all currencies and pairs
    # Currency profiles - include detailed scores
    currency_summary = {}
    for curr, data in currency_profiles.items():
        scores = data.get("scores", {})
        currency_summary[curr] = {
            "overall_score": data.get("overall_score", 50),
            "stance": data.get("stance", "neutral"),
            "current_rate": data.get("current_rate", 0),
            "scores": {
                "interest_rate": scores.get("interest_rate", 50),
                "inflation": scores.get("inflation", 50),
                "growth": scores.get("growth", 50),
                "employment": scores.get("employment", 50),
                "cb_tone": scores.get("cb_tone", 50),
                "momentum": scores.get("momentum", 50)
            },
            "medium_term_bias": data.get("medium_term_bias", "neutral"),
            "key_narrative": data.get("key_narrative", "")
        }
    
    # Pair analysis - key fields
    pair_summary = {}
    for pair, data in pair_analysis.items():
        pair_summary[pair] = {
            "bias": data.get("pair_bias", "neutral"),
            "confidence": data.get("confidence", 50),
            "base_score": data.get("base_score", 50),
            "quote_score": data.get("quote_score", 50),
            "macro_differential": data.get("macro_differential", 0),
            "rate_differential": data.get("rate_differential", 0),
            "time_horizon": data.get("time_horizon", "medium_term")
        }
    
    context = f"""You are Oracle, the fundamental macro analysis agent for a forex trading system.

## Currency Profile Components
Each currency profile score (0-100) is calculated from:
- **Interest Rate (25%)**: Current rate level + trend (rising/cutting) + expectations
- **Inflation (15%)**: CPI level vs 2% target + trend (declining is good)
- **Growth (20%)**: GDP level + trend (improving/slowing)
- **Employment (15%)**: Unemployment rate + trend
- **CB Tone (15%)**: Central bank stance (hawkish=bullish, dovish=bearish)
- **Momentum (10%)**: Combined trend direction of all factors

Stance thresholds: >60 bullish, 55-60 slightly_bullish, 45-55 neutral, 40-45 slightly_bearish, <40 bearish

## Currency Macro Profiles (8 currencies):
{json.dumps(currency_summary, indent=2)}

## Pair-Relative Analysis (9 pairs):
{json.dumps(pair_summary, indent=2)}

Answer questions about macro fundamentals, currency strength, pair biases, and explain WHY based on the component scores."""
    
    response = await call_claude(request.message, context, agent_name=AGENT_NAME)
    return {"response": response}


@app.get("/api/currencies")
async def get_currencies():
    return currency_profiles


@app.get("/api/currency/{currency}")
async def get_currency(currency: str):
    return currency_profiles.get(currency.upper(), {"error": "Not found"})


@app.get("/api/pairs")
async def get_pairs():
    return pair_analysis


@app.get("/api/pair/{pair}")
async def get_pair(pair: str):
    return pair_analysis.get(pair.upper(), {"error": "Not found"})


@app.get("/api/events")
async def get_events():
    """Get upcoming economic events for all currencies."""
    events = {}
    for currency, data in MACRO_DATA.items():
        events[currency] = data.get("upcoming_events", [])
    return {
        "events": events,
        "last_updated": narrative_cache_time.isoformat() if narrative_cache_time else None
    }


@app.post("/api/refresh-narratives")
async def refresh_narratives():
    """Manually trigger a refresh of dynamic narratives and events."""
    global narrative_cache_time
    narrative_cache_time = None  # Force refresh
    await update_dynamic_data()
    build_currency_profiles()
    build_pair_analyses()
    return {"status": "refreshed", "timestamp": datetime.utcnow().isoformat()}


@app.get("/api/status")
async def get_status():
    return {
        "agent_id": "macro",
        "name": AGENT_NAME,
        "status": "active",
        "currencies_tracked": len(currency_profiles),
        "pairs_analyzed": len(pair_analysis),
        "narrative_last_updated": narrative_cache_time.isoformat() if narrative_cache_time else "never",
        "version": "2.1",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, access_log=False)
