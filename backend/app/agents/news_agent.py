"""
News/Event Agent

Aggregates news from multiple sources and uses AI to interpret
forex market impact in real-time.

Sources:
- LiveSquawk RSS
- ForexLive RSS
- FXStreet RSS
- Investing.com RSS
- Twitter/X (via Nitter or API)
"""

import asyncio
import feedparser
import httpx
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import re

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


@dataclass
class NewsItem:
    """A single news item."""
    source: str
    title: str
    summary: str
    url: str
    published: datetime
    currencies_mentioned: List[str]
    impact_assessment: Optional[str] = None
    impact_score: float = 0.0  # -1.0 to 1.0


class NewsAgent(BaseAgent):
    """
    AI-powered news aggregation and interpretation agent.
    
    Monitors multiple forex news sources and uses Claude to:
    1. Identify relevant news for monitored pairs
    2. Assess potential market impact
    3. Flag high-impact events
    4. Provide real-time sentiment shifts
    """
    
    # RSS Feed sources
    FEEDS = {
        "forexlive": "https://www.forexlive.com/feed/news",
        "fxstreet": "https://www.fxstreet.com/rss/news",
        "investing_forex": "https://www.investing.com/rss/news_14.rss",
        "investing_economic": "https://www.investing.com/rss/news_95.rss",
        "dailyfx": "https://www.dailyfx.com/feeds/market-news",
    }
    
    # Currency keywords for relevance detection
    CURRENCY_KEYWORDS = {
        "USD": ["dollar", "usd", "fed", "fomc", "powell", "us ", "united states", "american"],
        "EUR": ["euro", "eur", "ecb", "lagarde", "eurozone", "europe"],
        "GBP": ["pound", "gbp", "sterling", "boe", "bailey", "uk ", "britain", "british"],
        "JPY": ["yen", "jpy", "boj", "ueda", "japan", "japanese"],
        "CHF": ["franc", "chf", "snb", "swiss", "switzerland"],
        "CAD": ["loonie", "cad", "boc", "macklem", "canada", "canadian"],
        "AUD": ["aussie", "aud", "rba", "bullock", "australia", "australian"],
        "NZD": ["kiwi", "nzd", "rbnz", "orr", "zealand"],
    }
    
    # High-impact keywords
    HIGH_IMPACT_KEYWORDS = [
        "rate decision", "rate hike", "rate cut", "interest rate",
        "inflation", "cpi", "ppi", "nfp", "non-farm", "employment",
        "gdp", "recession", "crisis", "crash", "surge", "plunge",
        "breaking", "just in", "alert", "urgent", "hawkish", "dovish",
        "intervention", "emergency", "unexpected", "surprise"
    ]
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        super().__init__(
            agent_id="news_agent",
            name="News Agent",
            role="Monitor forex news sources and interpret market impact using AI",
            redis_url=redis_url,
        )
        
        self.news_cache: Dict[str, NewsItem] = {}  # URL -> NewsItem
        self.last_fetch: Dict[str, datetime] = {}
        self.high_impact_queue: List[NewsItem] = []
        
        # Override system prompt for news-specific personality
        self.system_prompt = """You are the News Agent, a specialized AI analyst in a forex trading system.

YOUR ROLE:
- Analyze breaking forex news and assess market impact
- Identify which currency pairs will be affected
- Determine direction (bullish/bearish) and magnitude of impact
- Flag high-priority events immediately

ANALYSIS FRAMEWORK:
1. What happened? (one sentence)
2. Which currencies are affected? (list: USD, EUR, GBP, JPY, CHF, CAD, AUD, NZD)
3. Impact direction: BULLISH or BEARISH for each currency
4. Impact magnitude: LOW / MEDIUM / HIGH / CRITICAL
5. Recommended pairs to watch (e.g., "SHORT EURUSD", "LONG GBPJPY")
6. Time sensitivity: IMMEDIATE / TODAY / THIS_WEEK

REMEMBER:
- Central bank decisions = CRITICAL impact
- Inflation data = HIGH impact
- Employment data = HIGH impact
- GDP = MEDIUM-HIGH impact
- Trade balance = MEDIUM impact
- Political news = Context-dependent

Be concise. Traders need quick, actionable intel."""
    
    async def fetch_feeds(self) -> List[NewsItem]:
        """Fetch news from all RSS feeds."""
        all_news = []
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            for source, url in self.FEEDS.items():
                try:
                    # Rate limit: don't fetch same source more than once per 2 minutes
                    last = self.last_fetch.get(source)
                    if last and datetime.utcnow() - last < timedelta(minutes=2):
                        continue
                    
                    response = await client.get(url, follow_redirects=True)
                    if response.status_code == 200:
                        feed = feedparser.parse(response.text)
                        
                        for entry in feed.entries[:10]:  # Last 10 items per source
                            news = self._parse_entry(source, entry)
                            if news and news.url not in self.news_cache:
                                all_news.append(news)
                                self.news_cache[news.url] = news
                        
                        self.last_fetch[source] = datetime.utcnow()
                        logger.debug(f"[News Agent] Fetched {len(feed.entries)} items from {source}")
                        
                except Exception as e:
                    logger.warning(f"[News Agent] Failed to fetch {source}: {e}")
        
        return all_news
    
    def _parse_entry(self, source: str, entry: dict) -> Optional[NewsItem]:
        """Parse a feed entry into a NewsItem."""
        try:
            # Get publication time
            published = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6])
            else:
                published = datetime.utcnow()
            
            # Skip old news (>6 hours)
            if datetime.utcnow() - published > timedelta(hours=6):
                return None
            
            title = entry.get('title', '')
            summary = entry.get('summary', entry.get('description', ''))[:500]
            url = entry.get('link', '')
            
            # Detect mentioned currencies
            text = f"{title} {summary}".lower()
            currencies = []
            for currency, keywords in self.CURRENCY_KEYWORDS.items():
                if any(kw in text for kw in keywords):
                    currencies.append(currency)
            
            return NewsItem(
                source=source,
                title=title,
                summary=summary,
                url=url,
                published=published,
                currencies_mentioned=currencies,
            )
            
        except Exception as e:
            logger.error(f"[News Agent] Parse error: {e}")
            return None
    
    def _is_high_impact(self, news: NewsItem) -> bool:
        """Check if news is high-impact."""
        text = f"{news.title} {news.summary}".lower()
        return any(kw in text for kw in self.HIGH_IMPACT_KEYWORDS)
    
    async def analyze_news(self, news: NewsItem) -> NewsItem:
        """Use AI to analyze a news item's market impact."""
        prompt = f"""Analyze this forex news:

HEADLINE: {news.title}

SUMMARY: {news.summary}

SOURCE: {news.source}
TIME: {news.published.strftime('%Y-%m-%d %H:%M UTC')}

Provide your impact assessment."""

        try:
            response = await self.call_llm(prompt)
            news.impact_assessment = response
            
            # Extract impact score from response
            response_lower = response.lower()
            if "critical" in response_lower:
                news.impact_score = 0.9
            elif "high" in response_lower:
                news.impact_score = 0.7
            elif "medium" in response_lower:
                news.impact_score = 0.5
            elif "low" in response_lower:
                news.impact_score = 0.3
            else:
                news.impact_score = 0.4
                
        except Exception as e:
            logger.error(f"[News Agent] Analysis error: {e}")
            news.impact_assessment = "Analysis pending"
            
        return news
    
    async def analyze(self) -> Dict[str, Any]:
        """Main analysis cycle - fetch and analyze news."""
        # Fetch new items
        new_items = await self.fetch_feeds()
        
        # Analyze high-impact items with AI
        for news in new_items:
            if self._is_high_impact(news) or len(news.currencies_mentioned) >= 2:
                news = await self.analyze_news(news)
                
                # Broadcast high-impact news
                if news.impact_score >= 0.7:
                    self.high_impact_queue.append(news)
                    await self.publish("agents:broadcast", {
                        "type": "high_impact_news",
                        "title": news.title,
                        "currencies": news.currencies_mentioned,
                        "assessment": news.impact_assessment,
                        "score": news.impact_score,
                    })
        
        # Update state
        self.state["current_view"] = {
            "total_items": len(self.news_cache),
            "recent_items": len([n for n in self.news_cache.values() 
                                if datetime.utcnow() - n.published < timedelta(hours=1)]),
            "high_impact_pending": len(self.high_impact_queue),
            "last_analysis": datetime.utcnow().isoformat(),
            "sources_active": list(self.last_fetch.keys()),
        }
        
        self.state["status"] = "active"
        self.state["last_analysis"] = datetime.utcnow().isoformat()
        
        return self.state["current_view"]
    
    async def get_view(self, symbol: str = None) -> Dict[str, Any]:
        """Get current news view, optionally filtered by symbol."""
        recent = [
            {
                "title": n.title,
                "source": n.source,
                "published": n.published.isoformat(),
                "currencies": n.currencies_mentioned,
                "impact_score": n.impact_score,
                "assessment": n.impact_assessment,
            }
            for n in sorted(self.news_cache.values(), 
                          key=lambda x: x.published, reverse=True)[:20]
        ]
        
        if symbol:
            # Filter for symbol's currencies (e.g., EURUSD -> EUR, USD)
            currencies = [symbol[:3], symbol[3:]]
            recent = [n for n in recent 
                     if any(c in n["currencies"] for c in currencies)]
        
        return {
            "recent_news": recent,
            "high_impact": [
                {
                    "title": n.title,
                    "currencies": n.currencies_mentioned,
                    "assessment": n.impact_assessment,
                }
                for n in self.high_impact_queue[-5:]
            ],
            "summary": self.state.get("current_view", {}),
        }
    
    async def get_sentiment(self, currency: str) -> Dict[str, Any]:
        """Get news sentiment for a specific currency."""
        relevant = [n for n in self.news_cache.values() 
                   if currency in n.currencies_mentioned]
        
        if not relevant:
            return {"currency": currency, "sentiment": "neutral", "news_count": 0}
        
        # Aggregate sentiment from impact assessments
        bullish_count = sum(1 for n in relevant 
                          if n.impact_assessment and "bullish" in n.impact_assessment.lower())
        bearish_count = sum(1 for n in relevant 
                          if n.impact_assessment and "bearish" in n.impact_assessment.lower())
        
        if bullish_count > bearish_count:
            sentiment = "bullish"
        elif bearish_count > bullish_count:
            sentiment = "bearish"
        else:
            sentiment = "mixed"
        
        return {
            "currency": currency,
            "sentiment": sentiment,
            "bullish_news": bullish_count,
            "bearish_news": bearish_count,
            "total_news": len(relevant),
        }
