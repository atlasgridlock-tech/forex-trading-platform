"""
Sentiment and Positioning Agent - Pulse
Market sentiment, retail positioning, contrarian analysis
"""

import os
import sys
import json
import asyncio
import httpx
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from enum import Enum
import random

# Add shared module to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared import (
    call_claude,
    get_agent_url,
    post_json,
    FOREX_SYMBOLS,
    ChatRequest,
)
from pydantic import BaseModel

app = FastAPI(title="Pulse - Sentiment & Positioning Agent", version="2.2")

import anthropic

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
AGENT_NAME = "Pulse"
ORCHESTRATOR_URL = get_agent_url("orchestrator")
MYFXBOOK_EMAIL = os.getenv("MYFXBOOK_EMAIL", "")
MYFXBOOK_PASSWORD = os.getenv("MYFXBOOK_PASSWORD", "")

# Myfxbook session management
myfxbook_session: str = ""
myfxbook_session_time: datetime = None

SYMBOLS = FOREX_SYMBOLS

# Sentiment cache with TTL
sentiment_data: Dict[str, dict] = {}
retail_positioning_cache: Dict[str, dict] = {}
retail_cache_time: datetime = None
CACHE_TTL_MINUTES = 5

# Using ChatRequest from shared module

class SentimentClassification(str, Enum):
    TREND_SUPPORTIVE = "trend_supportive"
    OVERCROWDED = "overcrowded"
    CONTRARIAN_OPPORTUNITY = "contrarian_opportunity"
    NEUTRAL_NO_EDGE = "neutral_no_edge"


# ═══════════════════════════════════════════════════════════════
# REAL SENTIMENT DATA - Fetched from Myfxbook Community Outlook
# ═══════════════════════════════════════════════════════════════

# Symbol mapping for Myfxbook
MYFXBOOK_SYMBOLS = {
    "EURUSD": "eurusd",
    "GBPUSD": "gbpusd",
    "USDJPY": "usdjpy",
    "GBPJPY": "gbpjpy",
    "USDCHF": "usdchf",
    "USDCAD": "usdcad",
    "EURAUD": "euraud",
    "AUDNZD": "audnzd",
    "AUDUSD": "audusd",
    "EURGBP": "eurgbp",
    "EURJPY": "eurjpy",
    "NZDUSD": "nzdusd",
}

# Fallback data (used only if API fails)
FALLBACK_POSITIONING = {
    "EURUSD": {"long": 50, "change_24h": 0},
    "GBPUSD": {"long": 50, "change_24h": 0},
    "USDJPY": {"long": 50, "change_24h": 0},
    "GBPJPY": {"long": 50, "change_24h": 0},
    "USDCHF": {"long": 50, "change_24h": 0},
    "USDCAD": {"long": 50, "change_24h": 0},
    "EURAUD": {"long": 50, "change_24h": 0},
    "AUDNZD": {"long": 50, "change_24h": 0},
    "AUDUSD": {"long": 50, "change_24h": 0},
}


from urllib.parse import unquote

async def fetch_myfxbook_sentiment() -> Dict[str, dict]:
    """Fetch real retail positioning data from Myfxbook API."""
    global retail_positioning_cache, retail_cache_time
    
    # Check cache
    if retail_cache_time and (datetime.utcnow() - retail_cache_time).total_seconds() < CACHE_TTL_MINUTES * 60:
        if retail_positioning_cache:
            return retail_positioning_cache
    
    if not MYFXBOOK_EMAIL or not MYFXBOOK_PASSWORD:
        print("[Pulse] ⚠️ Myfxbook credentials not configured")
        return FALLBACK_POSITIONING
    
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            # Login first
            login_url = f"https://www.myfxbook.com/api/login.json?email={MYFXBOOK_EMAIL}&password={MYFXBOOK_PASSWORD}"
            login_response = await client.get(login_url)
            
            if login_response.status_code != 200:
                print(f"[Pulse] ❌ Myfxbook login failed: HTTP {login_response.status_code}")
                return FALLBACK_POSITIONING
            
            login_data = login_response.json()
            if login_data.get("error"):
                print(f"[Pulse] ❌ Myfxbook login error: {login_data.get('message')}")
                return FALLBACK_POSITIONING
            
            session = login_data.get("session", "")
            if not session:
                print("[Pulse] ❌ No session token received")
                return FALLBACK_POSITIONING
            
            print(f"[Pulse] ✅ Myfxbook login successful")
            
            # Fetch sentiment immediately with the session
            sentiment_url = f"https://www.myfxbook.com/api/get-community-outlook.json?session={session}"
            response = await client.get(sentiment_url)
            
            if response.status_code == 200:
                data = response.json()
                
                if not data.get("error"):
                    symbols_data = data.get("symbols", [])
                    positions = {}
                    
                    for item in symbols_data:
                        name = item.get("name", "").upper().replace("/", "")
                        
                        # Map Myfxbook symbol names to our format
                        if name in SYMBOLS:
                            long_pct = int(item.get("longPercentage", 50))
                            short_pct = int(item.get("shortPercentage", 50))
                            
                            positions[name] = {
                                "long": long_pct,
                                "short": short_pct,
                                "longVolume": item.get("longVolume", 0),
                                "shortVolume": item.get("shortVolume", 0),
                                "longPositions": item.get("longPositions", 0),
                                "shortPositions": item.get("shortPositions", 0),
                                "change_24h": 0,
                                "source": "myfxbook",
                                "timestamp": datetime.utcnow().isoformat()
                            }
                    
                    if positions:
                        retail_positioning_cache = positions
                        retail_cache_time = datetime.utcnow()
                        print(f"[Pulse] ✅ Fetched REAL sentiment for {len(positions)} pairs from Myfxbook API")
                        return positions
                    else:
                        print("[Pulse] ⚠️ No matching symbols in Myfxbook response")
                else:
                    print(f"[Pulse] ❌ Myfxbook API error: {data.get('message')}")
            else:
                print(f"[Pulse] ❌ Myfxbook API failed: HTTP {response.status_code}")
                
    except Exception as e:
        print(f"[Pulse] ❌ Myfxbook API exception: {e}")
    
    # Return fallback if API fails
    print("[Pulse] ⚠️ Using fallback sentiment data")
    return FALLBACK_POSITIONING


def get_retail_positioning(symbol: str) -> dict:
    """Get retail positioning for a symbol (sync wrapper)."""
    if symbol in retail_positioning_cache:
        return retail_positioning_cache[symbol]
    return FALLBACK_POSITIONING.get(symbol, {"long": 50, "change_24h": 0})

# COT Data - Fetched from CFTC
COT_DATA: Dict[str, dict] = {}
cot_cache_time: datetime = None
COT_CACHE_HOURS = 24  # COT releases weekly, cache for 24 hours

# CFTC currency futures mapping
CFTC_CURRENCIES = {
    "CANADIAN DOLLAR": "CAD",
    "SWISS FRANC": "CHF", 
    "BRITISH POUND": "GBP",
    "JAPANESE YEN": "JPY",
    "EURO FX": "EUR",
    "AUSTRALIAN DOLLAR": "AUD",
    "NEW ZEALAND DOLLAR": "NZD",
}


async def fetch_cftc_cot_data() -> Dict[str, dict]:
    """Fetch real COT data from CFTC Legacy Report."""
    global COT_DATA, cot_cache_time
    
    # Check cache
    if cot_cache_time and (datetime.utcnow() - cot_cache_time).total_seconds() < COT_CACHE_HOURS * 3600:
        if COT_DATA:
            return COT_DATA
    
    print("[Pulse] 📊 Fetching real COT data from CFTC...")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # CFTC Legacy COT Report (Futures Only)
            response = await client.get(
                "https://www.cftc.gov/dea/newcot/deafut.txt",
                headers={"User-Agent": "Mozilla/5.0"}
            )
            
            if response.status_code == 200:
                lines = response.text.strip().split('\n')
                result = {}
                
                for line in lines:
                    parts = line.split(',')
                    if len(parts) < 15:
                        continue
                    
                    contract_name = parts[0].strip('"').upper()
                    
                    # Only process currency futures
                    for cftc_name, currency in CFTC_CURRENCIES.items():
                        if cftc_name in contract_name and "CHICAGO MERCANTILE" in contract_name:
                            try:
                                # Legacy COT format columns:
                                # [7]: Open Interest
                                # [8]: Non-Commercial Long
                                # [9]: Non-Commercial Short
                                # [10]: Non-Commercial Spreading
                                # [11]: Commercial Long
                                # [12]: Commercial Short
                                
                                open_interest = int(parts[7].strip()) if parts[7].strip().isdigit() else 0
                                nc_long = int(parts[8].strip()) if parts[8].strip().isdigit() else 0
                                nc_short = int(parts[9].strip()) if parts[9].strip().isdigit() else 0
                                comm_long = int(parts[11].strip()) if parts[11].strip().isdigit() else 0
                                comm_short = int(parts[12].strip()) if parts[12].strip().isdigit() else 0
                                
                                # Calculate net positions
                                nc_net = nc_long - nc_short  # Large Speculators
                                comm_net = comm_long - comm_short  # Commercials (hedgers)
                                
                                # Determine trend based on speculator positioning
                                if nc_net > 20000:
                                    trend = "bullish"
                                elif nc_net < -20000:
                                    trend = "bearish"
                                else:
                                    trend = "mixed"
                                
                                result[currency] = {
                                    "commercials": comm_net,
                                    "large_specs": nc_net,
                                    "small_specs": 0,
                                    "nc_long": nc_long,
                                    "nc_short": nc_short,
                                    "comm_long": comm_long,
                                    "comm_short": comm_short,
                                    "open_interest": open_interest,
                                    "trend": trend,
                                    "source": "cftc",
                                    "timestamp": datetime.utcnow().isoformat()
                                }
                                print(f"[Pulse] ✅ COT {currency}: Specs={nc_net:+,}, Comms={comm_net:+,} → {trend}")
                            except (ValueError, IndexError) as e:
                                print(f"[Pulse] Error parsing {currency}: {e}")
                            break
                
                # Add USD (inverse of major currency positions)
                if result:
                    eur_specs = result.get("EUR", {}).get("large_specs", 0)
                    result["USD"] = {
                        "commercials": 0,
                        "large_specs": -eur_specs,
                        "small_specs": 0,
                        "trend": "bullish" if eur_specs < 0 else "bearish" if eur_specs > 0 else "mixed",
                        "source": "derived",
                        "timestamp": datetime.utcnow().isoformat()
                    }
                
                if result:
                    COT_DATA = result
                    cot_cache_time = datetime.utcnow()
                    print(f"[Pulse] ✅ Loaded real COT data for {len(result)} currencies")
                    return result
                    
    except Exception as e:
        print(f"[Pulse] ❌ Error fetching CFTC COT: {e}")
    
    # Return fallback if fetch fails
    print("[Pulse] ⚠️ Using fallback COT data")
    return {
        "USD": {"commercials": 0, "large_specs": 0, "small_specs": 0, "trend": "mixed", "source": "fallback"},
        "EUR": {"commercials": 0, "large_specs": 0, "small_specs": 0, "trend": "mixed", "source": "fallback"},
        "GBP": {"commercials": 0, "large_specs": 0, "small_specs": 0, "trend": "mixed", "source": "fallback"},
        "JPY": {"commercials": 0, "large_specs": 0, "small_specs": 0, "trend": "mixed", "source": "fallback"},
        "CHF": {"commercials": 0, "large_specs": 0, "small_specs": 0, "trend": "mixed", "source": "fallback"},
        "CAD": {"commercials": 0, "large_specs": 0, "small_specs": 0, "trend": "mixed", "source": "fallback"},
        "AUD": {"commercials": 0, "large_specs": 0, "small_specs": 0, "trend": "mixed", "source": "fallback"},
        "NZD": {"commercials": 0, "large_specs": 0, "small_specs": 0, "trend": "mixed", "source": "fallback"},
    }

# News sentiment - Fetched from FXStreet + ForexLive RSS
NEWS_CACHE: Dict[str, dict] = {}
news_cache_time: datetime = None
NEWS_CACHE_MINUTES = 5  # Refresh every 5 minutes (includes AI analysis)

# RSS feed sources
NEWS_FEEDS = [
    ("FXStreet", "https://www.fxstreet.com/rss/news"),
    ("ForexLive", "https://www.forexlive.com/feed"),
]

# ═══════════════════════════════════════════════════════════════
# COMPREHENSIVE KEYWORD DICTIONARIES FOR NEWS ANALYSIS
# ═══════════════════════════════════════════════════════════════

# Forex Price Action Keywords
BULLISH_KEYWORDS = [
    # Direct bullish
    "rally", "rallies", "rallied", "surge", "surges", "surged", "soar", "soars", "soared",
    "jump", "jumps", "jumped", "spike", "spikes", "spiked", "gain", "gains", "gained",
    "rise", "rises", "rising", "risen", "climb", "climbs", "climbed", "advance", "advances",
    "bullish", "bulls", "bull run", "breakout", "breaks out", "broke out",
    # Momentum
    "higher", "highs", "high", "upside", "upward", "up", "lifted", "lifts",
    "accelerate", "accelerates", "momentum", "strength", "strengthens", "strong",
    # Support/Recovery
    "support", "supports", "supported", "bounce", "bounces", "bounced", "rebound", "rebounds",
    "recovery", "recovers", "recovered", "stabilize", "stabilizes", "steady", "steadies",
    # Buying pressure
    "buying", "buyers", "bid", "bids", "demand", "inflows", "accumulation",
    "long", "longs", "longing", "bullish sentiment", "risk-on",
    # Positive outlook
    "optimism", "optimistic", "positive", "upgrade", "upgrades", "upgraded",
    "beat", "beats", "beating", "exceed", "exceeds", "exceeded", "outperform",
    "hawkish", "hike", "hikes", "hiking", "tightening", "rate hike",
]

BEARISH_KEYWORDS = [
    # Direct bearish
    "fall", "falls", "falling", "fell", "drop", "drops", "dropped", "plunge", "plunges", "plunged",
    "sink", "sinks", "sinking", "sunk", "tumble", "tumbles", "tumbled", "crash", "crashes", "crashed",
    "decline", "declines", "declined", "slide", "slides", "sliding", "slid", "slip", "slips", "slipped",
    "bearish", "bears", "bear market", "breakdown", "breaks down", "broke down",
    # Momentum
    "lower", "lows", "low", "downside", "downward", "down", "weakens", "weakened", "weak", "weakness",
    "decelerate", "decelerates", "slowdown", "slowing", "slows",
    # Resistance/Selling
    "resistance", "rejected", "rejection", "reversal", "reverses", "reversed",
    "selling", "sellers", "sell-off", "selloff", "offer", "offers", "supply", "outflows",
    "short", "shorts", "shorting", "bearish sentiment", "risk-off",
    # Negative outlook
    "pessimism", "pessimistic", "negative", "downgrade", "downgrades", "downgraded",
    "miss", "misses", "missing", "missed", "disappoint", "disappoints", "disappointed",
    "dovish", "cut", "cuts", "cutting", "easing", "rate cut", "pause", "pauses",
    # Loss/Damage
    "loss", "losses", "losing", "lost", "damage", "damaged", "hurt", "hurts", "pressure", "pressured",
]

# Geopolitical Risk Keywords (triggers risk-off sentiment)
GEOPOLITICAL_RISK_KEYWORDS = [
    # Military/War
    "war", "wars", "warfare", "warship", "warships", "military", "troops", "soldiers",
    "attack", "attacks", "attacked", "strike", "strikes", "struck", "bomb", "bombs", "bombing",
    "missile", "missiles", "rocket", "rockets", "drone", "drones", "airstrike", "airstrikes",
    "invasion", "invade", "invades", "invaded", "occupy", "occupation",
    "combat", "battle", "battlefield", "conflict", "conflicts", "fighting",
    "pentagon", "nato", "defense", "defence", "army", "navy", "air force",
    # Tensions
    "tension", "tensions", "escalate", "escalates", "escalation", "escalating",
    "threat", "threatens", "threatening", "warn", "warns", "warning", "warnings",
    "crisis", "crises", "emergency", "urgent", "critical",
    "hostile", "hostility", "hostilities", "aggressive", "aggression",
    # Nuclear
    "nuclear", "nuke", "nukes", "atomic", "uranium", "enrichment", "warhead", "warheads",
    "icbm", "ballistic", "radioactive", "radiation",
    # Sanctions/Diplomacy breakdown
    "sanction", "sanctions", "sanctioned", "embargo", "embargoes", "blockade", "blockades",
    "retaliate", "retaliates", "retaliation", "retaliatory",
    "expel", "expels", "expelled", "diplomat", "diplomats", "diplomatic",
    "sever", "severs", "severed", "ties", "relations",
    # Terrorism
    "terror", "terrorist", "terrorists", "terrorism", "extremist", "extremists",
    "insurgent", "insurgents", "insurgency", "militia", "militias",
    # Regions
    "middle east", "taiwan", "ukraine", "russia", "china", "iran", "north korea",
    "strait of hormuz", "south china sea", "gaza", "israel", "hamas", "hezbollah",
]

# Economic Crisis Keywords
ECONOMIC_CRISIS_KEYWORDS = [
    # Banking/Financial
    "default", "defaults", "defaulted", "bankruptcy", "bankrupt", "insolvent", "insolvency",
    "collapse", "collapses", "collapsed", "failure", "fails", "failed",
    "bailout", "bailouts", "rescue", "rescues", "liquidity crisis",
    "bank run", "contagion", "systemic risk", "credit crunch",
    # Recession
    "recession", "recessions", "recessionary", "depression", "stagflation",
    "contraction", "contracts", "contracted", "shrink", "shrinks", "shrinking",
    # Inflation/Deflation
    "hyperinflation", "runaway inflation", "deflation", "deflationary",
    "price surge", "cost of living", "affordability crisis",
    # Debt
    "debt crisis", "debt ceiling", "sovereign debt", "credit downgrade",
    "junk", "junk status", "downgrade", "credit rating",
    # Market panic
    "panic", "panics", "panicked", "fear", "fears", "fearful",
    "volatility", "volatile", "turmoil", "chaos", "uncertainty",
    "flash crash", "circuit breaker", "halt", "halted", "suspended",
]

# Safe Haven Keywords (USD, JPY, CHF, Gold positive)
SAFE_HAVEN_FLOW_KEYWORDS = [
    "safe haven", "safe-haven", "flight to safety", "flight to quality",
    "risk aversion", "risk-averse", "risk off", "risk-off",
    "haven demand", "haven flows", "haven buying",
    "defensive", "protection", "hedge", "hedging",
    "gold surges", "yen strengthens", "swiss franc",
    "treasuries rally", "bond buying", "yield falls",
]

# Risk-On Keywords (AUD, NZD, EM positive)
RISK_ON_KEYWORDS = [
    "risk on", "risk-on", "risk appetite", "risk sentiment",
    "equity rally", "stocks surge", "stock market gains",
    "carry trade", "yield seeking", "high yield",
    "emerging markets", "em rally", "commodities rally",
    "growth optimism", "economic recovery", "expansion",
]

# Central Bank Keywords
CENTRAL_BANK_KEYWORDS = {
    "hawkish": ["hawkish", "hawk", "hawks", "tightening", "hike", "hikes", "hiking", 
                "raise", "raises", "raising", "restrictive", "inflation fight", "combat inflation"],
    "dovish": ["dovish", "dove", "doves", "easing", "cut", "cuts", "cutting",
               "lower", "lowers", "lowering", "accommodative", "stimulus", "support economy"],
    "neutral": ["patient", "data dependent", "wait and see", "gradual", "measured",
                "balanced", "appropriate", "monitor", "monitoring"],
}

# ═══════════════════════════════════════════════════════════════
# AI-POWERED HEADLINE ANALYSIS (Using Claude Haiku)
# ═══════════════════════════════════════════════════════════════

async def analyze_headline_with_ai(headline: str) -> dict:
    """Use Claude Haiku to interpret headline sentiment for forex markets."""
    if not ANTHROPIC_API_KEY:
        return {"sentiment": "neutral", "confidence": 0, "reason": "No API key"}
    
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            messages=[{
                "role": "user",
                "content": f"""Analyze this forex news headline for market sentiment.

Headline: "{headline}"

Classify as ONE of:
- RISK_OFF: War, conflict, crisis, tensions, sanctions, negative geopolitics → USD/JPY/CHF strengthen
- RISK_ON: Peace, de-escalation, optimism, growth, stability → AUD/NZD/risk assets strengthen  
- BULLISH_USD: Positive for US dollar specifically
- BEARISH_USD: Negative for US dollar specifically
- NEUTRAL: No clear market impact

Reply in format: SENTIMENT|confidence(1-10)|brief_reason
Example: RISK_OFF|8|military escalation in Middle East"""
            }]
        )
        
        result = response.content[0].text.strip()
        parts = result.split("|")
        
        if len(parts) >= 2:
            sentiment = parts[0].strip().upper()
            confidence = int(parts[1].strip()) if parts[1].strip().isdigit() else 5
            reason = parts[2].strip() if len(parts) > 2 else ""
            
            return {
                "sentiment": sentiment,
                "confidence": confidence,
                "reason": reason,
                "raw": result
            }
        
        return {"sentiment": "NEUTRAL", "confidence": 3, "reason": "Could not parse", "raw": result}
        
    except Exception as e:
        print(f"[Pulse] AI analysis error: {e}")
        return {"sentiment": "NEUTRAL", "confidence": 0, "reason": str(e)}


async def analyze_headlines_batch(headlines: list) -> dict:
    """Analyze multiple headlines with AI in a single call for efficiency."""
    if not ANTHROPIC_API_KEY or not headlines:
        return {}
    
    # Limit to most recent 20 headlines to control costs
    headlines_to_analyze = headlines[:20]
    
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        
        headlines_text = "\n".join([f"{i+1}. {h}" for i, h in enumerate(headlines_to_analyze)])
        
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": f"""Analyze these forex news headlines for market sentiment.

{headlines_text}

For EACH headline, classify as:
- RISK_OFF: War, conflict, crisis, negative geopolitics → Safe havens (USD/JPY/CHF) strengthen
- RISK_ON: Peace, de-escalation, optimism → Risk assets (AUD/NZD) strengthen
- NEUTRAL: No clear directional impact

Reply with just the number and sentiment, one per line:
1. RISK_OFF
2. NEUTRAL
3. RISK_ON
etc."""
            }]
        )
        
        result = response.content[0].text.strip()
        sentiments = {}
        
        for line in result.split("\n"):
            line = line.strip()
            if "." in line:
                try:
                    parts = line.split(".", 1)
                    idx = int(parts[0].strip()) - 1
                    sentiment = parts[1].strip().upper().replace(" ", "_")
                    if idx < len(headlines_to_analyze):
                        # Normalize sentiment
                        if "RISK_OFF" in sentiment or "RISKOFF" in sentiment:
                            sentiments[headlines_to_analyze[idx]] = "RISK_OFF"
                        elif "RISK_ON" in sentiment or "RISKON" in sentiment:
                            sentiments[headlines_to_analyze[idx]] = "RISK_ON"
                        else:
                            sentiments[headlines_to_analyze[idx]] = "NEUTRAL"
                except:
                    pass
        
        print(f"[Pulse] 🤖 AI analyzed {len(sentiments)} headlines: {sum(1 for s in sentiments.values() if s == 'RISK_OFF')} risk-off, {sum(1 for s in sentiments.values() if s == 'RISK_ON')} risk-on")
        return sentiments
        
    except Exception as e:
        print(f"[Pulse] AI batch analysis error: {e}")
        return {}


# ═══════════════════════════════════════════════════════════════
# DE-ESCALATION / POSITIVE GEOPOLITICAL KEYWORDS (fallback if AI fails)
# ═══════════════════════════════════════════════════════════════

DEESCALATION_KEYWORDS = [
    # Peace/Ceasefire
    "peace", "peaceful", "peace talks", "peace deal", "peace agreement", "peace treaty",
    "ceasefire", "cease-fire", "cease fire", "truce", "armistice",
    "end of war", "war ends", "conflict ends", "fighting stops", "hostilities end",
    # De-escalation
    "de-escalate", "de-escalation", "deescalate", "deescalation", "easing tensions",
    "tensions ease", "tensions cool", "tensions subside", "calming",
    "stand down", "withdrawal", "withdraws", "withdrew", "pullback", "pull back",
    "retreat", "retreats", "retreating",
    # Diplomacy success
    "diplomatic breakthrough", "breakthrough", "agreement reached", "deal reached",
    "treaty signed", "accord", "accords", "pact", "settlement", "resolution",
    "talks succeed", "talks progress", "negotiations succeed", "compromise",
    "reconciliation", "reconcile", "normalize", "normalization", "rapprochement",
    # Sanctions relief
    "sanctions lifted", "sanctions eased", "sanctions removed", "sanctions relief",
    "embargo lifted", "blockade lifted", "restrictions eased",
    # Military de-escalation
    "troops withdraw", "forces withdraw", "military withdrawal",
    "demilitarize", "demilitarization", "disarm", "disarmament",
    "no-fly zone lifted", "safe passage", "humanitarian corridor",
    # Positive diplomatic
    "dialogue", "diplomatic solution", "peaceful resolution", "olive branch",
    "goodwill", "good faith", "constructive", "productive talks",
    "summit success", "historic meeting", "landmark agreement",
]

# Oil/Energy Stability Keywords (opposite of supply shock)
ENERGY_STABILITY_KEYWORDS = [
    "oil prices fall", "oil drops", "oil declines", "crude falls",
    "strait reopens", "shipping resumes", "supply restored", "supply normalizes",
    "opec increases", "production boost", "output rises",
    "energy crisis eases", "fuel prices drop", "gas prices fall",
    "pipeline reopens", "refinery reopens", "exports resume",
]


async def fetch_news_from_feed(client: httpx.AsyncClient, name: str, url: str) -> list:
    """Fetch news items from a single RSS feed."""
    items = []
    try:
        response = await client.get(url, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True)
        if response.status_code == 200:
            from xml.etree import ElementTree as ET
            root = ET.fromstring(response.content)
            
            for item in root.findall('.//item')[:30]:
                title = item.find('title')
                desc = item.find('description')
                
                if title is not None and title.text:
                    # Clean CDATA
                    headline = title.text.replace('<![CDATA[', '').replace(']]>', '').strip()
                    description = ""
                    if desc is not None and desc.text:
                        description = desc.text.replace('<![CDATA[', '').replace(']]>', '').strip()
                    
                    items.append({
                        "headline": headline,
                        "description": description,
                        "source": name
                    })
            
            print(f"[Pulse] ✅ {name}: {len(items)} headlines")
    except Exception as e:
        print(f"[Pulse] ⚠️ {name} error: {e}")
    
    return items


async def fetch_all_news() -> Dict[str, dict]:
    """Fetch real news from multiple RSS feeds (FXStreet + ForexLive)."""
    global NEWS_CACHE, news_cache_time
    
    # Check cache
    if news_cache_time and (datetime.utcnow() - news_cache_time).total_seconds() < NEWS_CACHE_MINUTES * 60:
        if NEWS_CACHE:
            return NEWS_CACHE
    
    print("[Pulse] 📰 Fetching real news from multiple sources...")
    
    result = {sym: {"headlines": [], "narrative": "", "tone": "neutral", "tone_score": 50, "sources": []} for sym in SYMBOLS}
    
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            # Fetch from all feeds
            all_items = []
            for name, url in NEWS_FEEDS:
                items = await fetch_news_from_feed(client, name, url)
                all_items.extend(items)
            
            print(f"[Pulse] 📰 Total: {len(all_items)} headlines from {len(NEWS_FEEDS)} sources")
            
            # Safe haven currencies benefit from risk-off
            SAFE_HAVENS = ["USD", "JPY", "CHF"]
            RISK_CURRENCIES = ["AUD", "NZD", "CAD"]
            
            # === AI-POWERED HEADLINE ANALYSIS ===
            unique_headlines = list(set([item["headline"] for item in all_items]))
            ai_sentiments = await analyze_headlines_batch(unique_headlines)
            
            # Track global risk sentiment
            global_risk_off = sum(1 for s in ai_sentiments.values() if s == "RISK_OFF")
            global_risk_on = sum(1 for s in ai_sentiments.values() if s == "RISK_ON")
            
            # Process all items
            for item in all_items:
                headline = item["headline"]
                description = item.get("description", "")
                source = item["source"]
                text = f"{headline} {description}".upper()
                text_lower = f"{headline} {description}".lower()
                
                # Count keyword matches
                bullish_count = sum(1 for kw in BULLISH_KEYWORDS if kw.lower() in text_lower)
                bearish_count = sum(1 for kw in BEARISH_KEYWORDS if kw.lower() in text_lower)
                geopolitical_count = sum(1 for kw in GEOPOLITICAL_RISK_KEYWORDS if kw.lower() in text_lower)
                crisis_count = sum(1 for kw in ECONOMIC_CRISIS_KEYWORDS if kw.lower() in text_lower)
                safe_haven_count = sum(1 for kw in SAFE_HAVEN_FLOW_KEYWORDS if kw.lower() in text_lower)
                risk_on_count = sum(1 for kw in RISK_ON_KEYWORDS if kw.lower() in text_lower)
                deescalation_count = sum(1 for kw in DEESCALATION_KEYWORDS if kw.lower() in text_lower)
                energy_stability_count = sum(1 for kw in ENERGY_STABILITY_KEYWORDS if kw.lower() in text_lower)
                
                # Track global risk sentiment
                # Risk-OFF triggers
                if geopolitical_count > 0 or crisis_count > 0 or safe_haven_count > 0:
                    global_risk_off += (geopolitical_count + crisis_count + safe_haven_count)
                # Risk-ON triggers (including de-escalation!)
                if risk_on_count > 0 or deescalation_count > 0 or energy_stability_count > 0:
                    global_risk_on += (risk_on_count + deescalation_count * 2 + energy_stability_count)  # De-escalation weighted higher
                
                # Match to currency pairs
                for symbol in SYMBOLS:
                    base = symbol[:3]
                    quote = symbol[3:]
                    pair_formats = [symbol, f"{base}/{quote}", f"{base}-{quote}", base, quote]
                    
                    if any(fmt in text for fmt in pair_formats):
                        result[symbol]["headlines"].append(f"[{source}] {headline}")
                        if source not in result[symbol]["sources"]:
                            result[symbol]["sources"].append(source)
                        
                        # === AI-POWERED SENTIMENT (Primary) ===
                        ai_sentiment = ai_sentiments.get(headline, "NEUTRAL")
                        net_sentiment = 0
                        
                        if ai_sentiment == "RISK_OFF":
                            # Safe havens benefit from risk-off
                            if base in SAFE_HAVENS:
                                net_sentiment += 3  # Boost safe havens
                            elif quote in SAFE_HAVENS:
                                net_sentiment -= 3  # Pair weakens vs safe haven
                            # Risk currencies suffer in risk-off
                            if base in RISK_CURRENCIES:
                                net_sentiment -= 3
                            elif quote in RISK_CURRENCIES:
                                net_sentiment += 3
                            result[symbol]["geopolitical_risk"] = True
                            
                        elif ai_sentiment == "RISK_ON":
                            # Safe havens WEAKEN in risk-on
                            if base in SAFE_HAVENS:
                                net_sentiment -= 3
                            elif quote in SAFE_HAVENS:
                                net_sentiment += 3
                            # Risk currencies BENEFIT
                            if base in RISK_CURRENCIES:
                                net_sentiment += 3
                            elif quote in RISK_CURRENCIES:
                                net_sentiment -= 3
                            result[symbol]["risk_on"] = True
                        
                        # Also consider direct bullish/bearish keywords for pair-specific news
                        net_sentiment += (bullish_count - bearish_count)
                        
                        # Apply sentiment
                        if net_sentiment > 0:
                            result[symbol]["tone_score"] = min(result[symbol]["tone_score"] + 5, 85)
                        elif net_sentiment < 0:
                            result[symbol]["tone_score"] = max(result[symbol]["tone_score"] - 5, 15)
            
            # Log global risk sentiment
            if global_risk_off > global_risk_on * 1.5:  # Significant risk-off
                print(f"[Pulse] 🔴 RISK-OFF dominant: geopolitical/crisis={global_risk_off} vs peace/optimism={global_risk_on}")
            elif global_risk_on > global_risk_off * 1.5:  # Significant risk-on
                print(f"[Pulse] 🟢 RISK-ON dominant: peace/optimism={global_risk_on} vs geopolitical/crisis={global_risk_off}")
            else:
                print(f"[Pulse] ⚖️ MIXED sentiment: risk-off={global_risk_off}, risk-on={global_risk_on}")
            
            # Set narratives and tones
            for symbol in SYMBOLS:
                headlines = result[symbol]["headlines"]
                tone_score = result[symbol]["tone_score"]
                
                if headlines:
                    result[symbol]["narrative"] = headlines[0][:100]
                    result[symbol]["tone"] = "bullish" if tone_score > 55 else "bearish" if tone_score < 45 else "neutral"
                    sources = ", ".join(result[symbol]["sources"])
                    print(f"[Pulse] ✅ {symbol}: {len(headlines)} headlines ({sources}), tone={result[symbol]['tone']}")
                else:
                    result[symbol]["narrative"] = "No recent news"
                    result[symbol]["tone"] = "neutral"
            
            NEWS_CACHE = result
            news_cache_time = datetime.utcnow()
            pairs_with_news = len([s for s in SYMBOLS if result[s]["headlines"]])
            print(f"[Pulse] ✅ Loaded news for {pairs_with_news} pairs from {len(NEWS_FEEDS)} sources")
            return result
                
    except Exception as e:
        print(f"[Pulse] ❌ Error fetching news: {e}")
    
    # Return empty cache if fetch fails
    return {sym: {"headlines": [], "narrative": "No data", "tone": "neutral", "tone_score": 50} for sym in SYMBOLS}


# Alias for backward compatibility
async def fetch_fxstreet_news() -> Dict[str, dict]:
    return await fetch_all_news()


def get_news_sentiment(symbol: str) -> dict:
    """Get news sentiment for a symbol."""
    if symbol in NEWS_CACHE:
        return NEWS_CACHE[symbol]
    return {"headlines": [], "narrative": "No data", "tone": "neutral", "tone_score": 50}


# Fallback narratives (used if RSS fails)
NEWS_NARRATIVES = {
    "EURUSD": {
        "narrative": "Market monitoring EUR/USD",
        "keywords": {},
        "tone": "neutral",
        "tone_score": 50,
    },
    "GBPUSD": {
        "narrative": "Market monitoring GBP/USD",
        "keywords": {},
        "tone": "neutral",
        "tone_score": 50,
    },
    "USDJPY": {
        "narrative": "Market monitoring USD/JPY",
        "keywords": {},
        "tone": "neutral",
        "tone_score": 50,
    },
    "AUDUSD": {
        "narrative": "China slowdown weighing on AUD",
        "keywords": {"China": 45, "commodities": 20, "RBA": 20, "risk": 15},
        "tone": "bearish",
        "tone_score": 38,
    },
}


def calculate_sentiment_score(retail_long: int, news_tone: int) -> int:
    """Calculate overall sentiment score (0-100, >50 = bullish)."""
    # Retail sentiment (inverted - high longs = bearish contrarian)
    retail_sentiment = retail_long  # Raw retail bullishness
    
    # News sentiment
    news_sentiment = news_tone
    
    # Weighted combination
    score = int(retail_sentiment * 0.6 + news_sentiment * 0.4)
    return max(0, min(100, score))


def calculate_crowding_score(retail_long: int) -> int:
    """Calculate crowding score (0-100, higher = more crowded)."""
    # Distance from 50% (balanced)
    distance = abs(retail_long - 50)
    # Scale to 0-100
    crowding = int(distance * 2)
    return max(0, min(100, crowding))


def calculate_contrarian_score(retail_long: int, crowding: int, news_tone: int) -> int:
    """Calculate contrarian opportunity score."""
    contrarian = 0
    
    # High crowding is base for contrarian
    if crowding >= 40:
        contrarian += crowding * 0.5
    
    # If retail sentiment diverges from news tone, contrarian opportunity
    if retail_long > 60 and news_tone < 45:
        contrarian += 25  # Retail bullish, news bearish = short opportunity
    elif retail_long < 40 and news_tone > 55:
        contrarian += 25  # Retail bearish, news bullish = long opportunity
    
    # Extreme positioning adds to contrarian
    if retail_long > 75 or retail_long < 25:
        contrarian += 15
    
    return max(0, min(100, int(contrarian)))


def classify_sentiment(retail_long: int, crowding: int, contrarian: int) -> SentimentClassification:
    """Classify sentiment into one of four categories."""
    # Extreme crowding with contrarian signal
    if crowding >= 50 and contrarian >= 50:
        return SentimentClassification.CONTRARIAN_OPPORTUNITY
    
    # High crowding without strong contrarian
    if crowding >= 40:
        return SentimentClassification.OVERCROWDED
    
    # Moderate sentiment aligning with likely trend
    if 45 <= retail_long <= 65:
        return SentimentClassification.NEUTRAL_NO_EDGE
    
    # Otherwise trend supportive (sentiment has direction but not extreme)
    return SentimentClassification.TREND_SUPPORTIVE


def get_cot_analysis(base: str, quote: str) -> dict:
    """Get COT-style analysis for a pair."""
    base_cot = COT_DATA.get(base, {})
    quote_cot = COT_DATA.get(quote, {})
    
    # Compare positioning
    base_net = base_cot.get("large_specs", 0) + base_cot.get("commercials", 0)
    quote_net = quote_cot.get("large_specs", 0) + quote_cot.get("commercials", 0)
    
    if base_net > quote_net + 5000:
        cot_bias = "bullish"
    elif quote_net > base_net + 5000:
        cot_bias = "bearish"
    else:
        cot_bias = "neutral"
    
    # Check for divergence (small specs vs large specs)
    base_divergence = (base_cot.get("small_specs", 0) > 0) != (base_cot.get("large_specs", 0) > 0)
    
    return {
        "base_trend": base_cot.get("trend", "unknown"),
        "quote_trend": quote_cot.get("trend", "unknown"),
        "cot_bias": cot_bias,
        "smart_money_divergence": base_divergence,
        "commercials_net": base_cot.get("commercials", 0) - quote_cot.get("commercials", 0),
    }


def generate_narrative(symbol: str, classification: SentimentClassification, 
                       retail_long: int, crowding: int, contrarian: int,
                       cot_bias: str, news_narrative: str) -> str:
    """Generate human-readable narrative summary."""
    narratives = []
    
    # Retail positioning narrative
    if retail_long > 70:
        narratives.append(f"Retail heavily long ({retail_long}%)")
    elif retail_long < 30:
        narratives.append(f"Retail heavily short ({100-retail_long}% short)")
    else:
        narratives.append(f"Retail positioning balanced ({retail_long}% long)")
    
    # Classification-based narrative
    if classification == SentimentClassification.CONTRARIAN_OPPORTUNITY:
        direction = "shorts" if retail_long > 60 else "longs"
        narratives.append(f"Classic contrarian setup: consider {direction}")
    elif classification == SentimentClassification.OVERCROWDED:
        narratives.append("Positioning overcrowded, avoid adding to crowd")
    elif classification == SentimentClassification.TREND_SUPPORTIVE:
        narratives.append("Sentiment supports trend direction")
    else:
        narratives.append("No clear sentiment edge")
    
    # COT insight
    if cot_bias != "neutral":
        narratives.append(f"Institutional bias: {cot_bias}")
    
    # News context
    if news_narrative:
        narratives.append(f"Narrative: \"{news_narrative}\"")
    
    return ". ".join(narratives) + "."


def analyze_symbol(symbol: str) -> dict:
    """Perform full sentiment analysis for a symbol."""
    # Get retail positioning (from cache/real data)
    retail = get_retail_positioning(symbol)
    retail_long = retail.get("long", 50)
    change_24h = retail.get("change_24h", 0)
    
    # Get news sentiment (real data if available, fallback otherwise)
    news = get_news_sentiment(symbol)
    if not news.get("headlines"):
        news = NEWS_NARRATIVES.get(symbol, {
            "narrative": "",
            "tone": "neutral",
            "tone_score": 50,
        })
    news_tone = news.get("tone_score", 50)
    
    # Calculate scores
    sentiment_score = calculate_sentiment_score(retail_long, news_tone)
    crowding_score = calculate_crowding_score(retail_long)
    contrarian_score = calculate_contrarian_score(retail_long, crowding_score, news_tone)
    
    # Classify
    classification = classify_sentiment(retail_long, crowding_score, contrarian_score)
    
    # Get COT analysis
    base = symbol[:3]
    quote = symbol[3:]
    cot = get_cot_analysis(base, quote)
    
    # Determine positioning bias
    if classification == SentimentClassification.CONTRARIAN_OPPORTUNITY:
        if retail_long > 60:
            positioning_bias = "bearish"  # Fade the longs
        else:
            positioning_bias = "bullish"  # Fade the shorts
    elif retail_long > 55:
        positioning_bias = "bullish"
    elif retail_long < 45:
        positioning_bias = "bearish"
    else:
        positioning_bias = "neutral"
    
    # Generate narrative
    narrative = generate_narrative(
        symbol, classification, retail_long, crowding_score, 
        contrarian_score, cot["cot_bias"], news.get("narrative", "")
    )
    
    # Confidence based on crowding and contrarian scores
    if classification == SentimentClassification.CONTRARIAN_OPPORTUNITY:
        confidence = min(90, 50 + contrarian_score * 0.4)
    elif classification == SentimentClassification.OVERCROWDED:
        confidence = min(80, 40 + crowding_score * 0.4)
    else:
        confidence = 50
    
    return {
        "symbol": symbol,
        "classification": classification.value,
        "confidence": round(confidence, 0),
        "retail_positioning": {
            "long_pct": retail_long,
            "short_pct": 100 - retail_long,
            "change_24h": change_24h,
            "extreme": retail_long > 70 or retail_long < 30,
        },
        "cot_analysis": cot,
        "news_sentiment": {
            "narrative": news.get("narrative", ""),
            "tone": news.get("tone", "neutral"),
            "tone_score": news_tone,
        },
        "scores": {
            "sentiment": sentiment_score,
            "crowding": crowding_score,
            "contrarian": contrarian_score,
        },
        "positioning_bias": positioning_bias,
        "narrative_summary": narrative,
        "timestamp": datetime.utcnow().isoformat(),
    }


async def send_to_orchestrator(symbol: str, analysis: dict):
    """Send analysis to Orchestrator using shared post_json."""
    await post_json(
        f"{ORCHESTRATOR_URL}/api/ingest",
        {
            "agent_id": "sentiment",
            "agent_name": AGENT_NAME,
            "output_type": "signal",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "symbol": symbol,
                "direction": analysis["positioning_bias"],
                "confidence": analysis["confidence"] / 100,
                "reason": f"{analysis['classification']} - {analysis['scores']['contrarian']} contrarian",
            },
        }
    )


async def background_analysis():
    """Background sentiment analysis loop."""
    global sentiment_data
    
    while True:
        # Fetch fresh sentiment data from real sources
        try:
            await fetch_myfxbook_sentiment()
            source = retail_positioning_cache.get(list(SYMBOLS)[0], {}).get("source", "unknown")
            print(f"[Pulse] Refreshed sentiment data from {source}")
        except Exception as e:
            print(f"[Pulse] Error refreshing sentiment: {e}")
        
        # Analyze all symbols with fresh data
        for symbol in SYMBOLS:
            analysis = analyze_symbol(symbol)
            sentiment_data[symbol] = analysis
            await send_to_orchestrator(symbol, analysis)
        
        await asyncio.sleep(300)  # Update every 5 minutes


# Using shared call_claude - removed duplicate implementation


@app.on_event("startup")
async def startup():
    global sentiment_data
    print(f"🚀 {AGENT_NAME} (Sentiment & Positioning Agent) v2.1 starting...")
    
    # Fetch real sentiment data on startup
    print("[Pulse] Fetching real sentiment data...")
    await fetch_myfxbook_sentiment()
    
    if retail_positioning_cache:
        source = list(retail_positioning_cache.values())[0].get("source", "unknown")
        print(f"[Pulse] ✅ Loaded real sentiment from {source} for {len(retail_positioning_cache)} pairs")
    else:
        print("[Pulse] ⚠️ Using fallback sentiment data")
    
    # Fetch real COT data from CFTC
    print("[Pulse] Fetching real COT data from CFTC...")
    await fetch_cftc_cot_data()
    
    if COT_DATA:
        print(f"[Pulse] ✅ Loaded real COT data for {len(COT_DATA)} currencies")
    
    # Fetch real news from FXStreet
    print("[Pulse] Fetching real news from FXStreet...")
    await fetch_fxstreet_news()
    
    if NEWS_CACHE:
        pairs_with_news = len([s for s in SYMBOLS if NEWS_CACHE.get(s, {}).get("headlines")])
        print(f"[Pulse] ✅ Loaded real news for {pairs_with_news} pairs")
    
    for symbol in SYMBOLS:
        sentiment_data[symbol] = analyze_symbol(symbol)
    
    asyncio.create_task(background_analysis())


@app.get("/", response_class=HTMLResponse)
async def home():
    cards_html = ""
    for symbol in SYMBOLS:
        s = sentiment_data.get(symbol, {})
        classification = s.get("classification", "neutral")
        retail = s.get("retail_positioning", {})
        long_pct = retail.get("long_pct", 50)
        scores = s.get("scores", {})
        crowding = scores.get("crowding", 0)
        contrarian = scores.get("contrarian", 0)
        bias = s.get("positioning_bias", "neutral")
        confidence = s.get("confidence", 50)
        
        # Classification styling
        if classification == "contrarian_opportunity":
            class_color = "#f59e0b"
            class_icon = "🎯"
        elif classification == "overcrowded":
            class_color = "#ef4444"
            class_icon = "⚠️"
        elif classification == "trend_supportive":
            class_color = "#22c55e"
            class_icon = "✅"
        else:
            class_color = "#888"
            class_icon = "➖"
        
        bias_color = "#22c55e" if bias == "bullish" else "#ef4444" if bias == "bearish" else "#888"
        
        cards_html += f'''
        <div class="card">
            <div class="card-header">
                <span class="symbol">{symbol}</span>
                <span class="class-badge" style="background:{class_color}20;color:{class_color}">{class_icon} {classification.replace("_", " ").upper()}</span>
            </div>
            <div class="positioning">
                <div class="bar">
                    <div class="long" style="width:{long_pct}%"></div>
                </div>
                <div class="bar-labels">
                    <span style="color:#22c55e">{long_pct}% Long</span>
                    <span style="color:#ef4444">{100-long_pct}% Short</span>
                </div>
            </div>
            <div class="scores">
                <div class="score">
                    <span class="score-label">Crowding</span>
                    <span class="score-value">{crowding}</span>
                </div>
                <div class="score">
                    <span class="score-label">Contrarian</span>
                    <span class="score-value">{contrarian}</span>
                </div>
            </div>
            <div class="bias" style="color:{bias_color}">Bias: {bias.upper()} ({confidence:.0f}%)</div>
        </div>
        '''
    
    # Contrarian opportunities
    contrarian_html = ""
    for symbol, s in sentiment_data.items():
        if s.get("classification") == "contrarian_opportunity":
            contrarian_html += f'''
            <div class="opportunity">
                <span class="opp-symbol">{symbol}</span>
                <span class="opp-score">{s.get("scores", {}).get("contrarian", 0)}</span>
                <span class="opp-bias">{s.get("positioning_bias", "?")}</span>
            </div>
            '''
    
    if not contrarian_html:
        contrarian_html = '<div style="color:#666">No contrarian opportunities</div>'
    
    return f'''<!DOCTYPE html>
<html><head>
    <title>💓 Pulse - Sentiment Agent</title>
    <meta http-equiv="refresh" content="30">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, sans-serif; background: #0a0a0f; color: #e0e0e0; padding: 20px; }}
        .header {{ display: flex; align-items: center; gap: 15px; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid #333; }}
        .header h1 {{ color: #ec4899; }}
        .status {{ background: #22c55e20; color: #22c55e; padding: 5px 12px; border-radius: 20px; font-size: 14px; }}
        .grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-bottom: 20px; }}
        .card {{ background: #1a1a24; border-radius: 10px; padding: 15px; }}
        .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }}
        .symbol {{ font-size: 16px; font-weight: bold; }}
        .class-badge {{ padding: 3px 8px; border-radius: 4px; font-size: 10px; }}
        .positioning {{ margin-bottom: 10px; }}
        .bar {{ height: 20px; background: #ef4444; border-radius: 4px; overflow: hidden; }}
        .long {{ height: 100%; background: #22c55e; }}
        .bar-labels {{ display: flex; justify-content: space-between; font-size: 11px; margin-top: 4px; }}
        .scores {{ display: flex; gap: 15px; margin-bottom: 10px; }}
        .score {{ text-align: center; }}
        .score-label {{ font-size: 10px; color: #888; display: block; }}
        .score-value {{ font-size: 18px; font-weight: bold; color: #ec4899; }}
        .bias {{ font-size: 12px; font-weight: 600; }}
        .contrarian-section {{ background: #1a1a24; border-radius: 12px; padding: 20px; margin-bottom: 20px; }}
        .contrarian-section h2 {{ color: #f59e0b; margin-bottom: 15px; }}
        .opportunity {{ display: flex; align-items: center; gap: 15px; padding: 10px; background: #0a0a0f; border-radius: 8px; margin: 8px 0; }}
        .opp-symbol {{ font-weight: bold; }}
        .opp-score {{ color: #f59e0b; }}
        .opp-bias {{ color: #888; }}
        .chat-section {{ background: #1a1a24; border-radius: 12px; padding: 20px; }}
        .chat-section h2 {{ color: #ec4899; margin-bottom: 15px; }}
        .chat-messages {{ height: 150px; overflow-y: auto; background: #0a0a0f; border-radius: 8px; padding: 10px; margin-bottom: 10px; }}
        .chat-input {{ display: flex; gap: 10px; }}
        .chat-input input {{ flex: 1; padding: 10px; border-radius: 8px; border: 1px solid #333; background: #0a0a0f; color: #fff; }}
        .chat-input button {{ padding: 10px 20px; background: #ec4899; color: #fff; border: none; border-radius: 8px; cursor: pointer; }}
        .message {{ margin: 8px 0; padding: 8px; border-radius: 6px; font-size: 13px; }}
        .message.user {{ background: #333; margin-left: 20%; }}
        .message.agent {{ background: #4d1a3d; margin-right: 20%; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>💓 Pulse</h1>
        <span class="status">● SENSING</span>
        <span style="color: #888; margin-left: auto;">Sentiment & Positioning Agent v2.0</span>
    </div>
    
    <div class="contrarian-section">
        <h2>🎯 Contrarian Opportunities</h2>
        {contrarian_html}
    </div>
    
    <div class="grid">{cards_html}</div>
    
    <div class="chat-section">
        <h2>💬 Ask Pulse</h2>
        <div class="chat-messages" id="messages"></div>
        <div class="chat-input">
            <input type="text" id="input" placeholder="Ask about sentiment..." onkeypress="if(event.key==='Enter')sendMessage()">
            <button onclick="sendMessage()">Send</button>
        </div>
    </div>
    <script>
        const CHAT_KEY = 'pulse_chat_history';
        
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
    context = f"Sentiment Data:\n{json.dumps(sentiment_data, indent=2, default=str)[:6000]}"
    response = await call_claude(request.message, context, agent_name=AGENT_NAME)
    return {"response": response}


@app.get("/api/sentiment")
async def get_all_sentiment():
    return sentiment_data


@app.get("/api/sentiment/{symbol}")
async def get_symbol_sentiment(symbol: str):
    return sentiment_data.get(symbol.upper(), {"error": "Not found"})


@app.get("/api/contrarian")
async def get_contrarian_opportunities():
    """Get symbols with contrarian opportunities."""
    return {
        s: d for s, d in sentiment_data.items() 
        if d.get("classification") == "contrarian_opportunity"
    }


@app.get("/api/overcrowded")
async def get_overcrowded():
    """Get overcrowded symbols."""
    return {
        s: d for s, d in sentiment_data.items()
        if d.get("classification") == "overcrowded"
    }


@app.get("/api/status")
async def get_status():
    contrarian_count = sum(1 for s in sentiment_data.values() if s.get("classification") == "contrarian_opportunity")
    overcrowded_count = sum(1 for s in sentiment_data.values() if s.get("classification") == "overcrowded")
    
    # Determine data source
    data_source = "fallback"
    if retail_positioning_cache:
        sample = list(retail_positioning_cache.values())[0]
        data_source = sample.get("source", "unknown")
    
    return {
        "agent_id": "sentiment",
        "name": AGENT_NAME,
        "status": "active",
        "symbols_tracked": len(sentiment_data),
        "contrarian_opportunities": contrarian_count,
        "overcrowded_symbols": overcrowded_count,
        "data_source": data_source,
        "cache_age_seconds": (datetime.utcnow() - retail_cache_time).total_seconds() if retail_cache_time else None,
        "version": "2.1",
    }


class SentimentUpdate(BaseModel):
    symbol: str
    long_pct: int  # Percentage of retail traders long (0-100)
    source: str = "manual"


@app.post("/api/sentiment/update")
async def update_sentiment(update: SentimentUpdate):
    """Manually update sentiment for a symbol. 
    Use this to input real data from Myfxbook, OANDA, etc."""
    global retail_positioning_cache, retail_cache_time
    
    if update.symbol not in SYMBOLS:
        return {"error": f"Unknown symbol: {update.symbol}"}
    
    if not 0 <= update.long_pct <= 100:
        return {"error": "long_pct must be between 0 and 100"}
    
    retail_positioning_cache[update.symbol] = {
        "long": update.long_pct,
        "short": 100 - update.long_pct,
        "change_24h": 0,
        "source": update.source,
        "timestamp": datetime.utcnow().isoformat()
    }
    retail_cache_time = datetime.utcnow()
    
    # Re-analyze the symbol
    sentiment_data[update.symbol] = analyze_symbol(update.symbol)
    
    return {
        "status": "updated",
        "symbol": update.symbol,
        "long_pct": update.long_pct,
        "source": update.source,
        "analysis": sentiment_data[update.symbol]
    }


@app.post("/api/sentiment/bulk-update")
async def bulk_update_sentiment(updates: List[SentimentUpdate]):
    """Update sentiment for multiple symbols at once."""
    global retail_positioning_cache, retail_cache_time
    
    results = []
    for update in updates:
        if update.symbol not in SYMBOLS:
            results.append({"symbol": update.symbol, "error": "Unknown symbol"})
            continue
        
        if not 0 <= update.long_pct <= 100:
            results.append({"symbol": update.symbol, "error": "Invalid long_pct"})
            continue
        
        retail_positioning_cache[update.symbol] = {
            "long": update.long_pct,
            "short": 100 - update.long_pct,
            "change_24h": 0,
            "source": update.source,
            "timestamp": datetime.utcnow().isoformat()
        }
        sentiment_data[update.symbol] = analyze_symbol(update.symbol)
        results.append({"symbol": update.symbol, "status": "updated", "long_pct": update.long_pct})
    
    retail_cache_time = datetime.utcnow()
    return {"updated": len([r for r in results if "status" in r]), "results": results}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
