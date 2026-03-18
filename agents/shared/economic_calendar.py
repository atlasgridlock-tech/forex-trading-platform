"""
Economic Calendar Integration
Fetches real forex economic events from multiple sources.
"""

import os
import json
import httpx
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from pathlib import Path
import xml.etree.ElementTree as ET

# Cache settings
CACHE_FILE = Path("/tmp/economic_calendar_cache.json")
CACHE_DURATION = timedelta(hours=1)


async def fetch_forex_factory_calendar() -> List[dict]:
    """
    Fetch events from Forex Factory XML feed.
    Returns list of economic events.
    """
    events = []
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Forex Factory provides an XML feed
            url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
            response = await client.get(url)
            
            if response.status_code == 200:
                root = ET.fromstring(response.text)
                
                for event in root.findall('.//event'):
                    title = event.find('title')
                    country = event.find('country')
                    date_elem = event.find('date')
                    time_elem = event.find('time')
                    impact = event.find('impact')
                    forecast = event.find('forecast')
                    previous = event.find('previous')
                    
                    if title is not None and date_elem is not None:
                        # Parse date and time
                        date_str = date_elem.text if date_elem.text else ""
                        time_str = time_elem.text if time_elem is not None and time_elem.text else "All Day"
                        
                        # Convert impact to our format
                        impact_text = impact.text if impact is not None else ""
                        if impact_text == "High":
                            impact_level = "HIGH"
                        elif impact_text == "Medium":
                            impact_level = "MEDIUM"
                        else:
                            impact_level = "LOW"
                        
                        events.append({
                            'title': title.text,
                            'country': country.text if country is not None else "",
                            'currency': get_currency_from_country(country.text if country is not None else ""),
                            'date': date_str,
                            'time': time_str,
                            'impact': impact_level,
                            'forecast': forecast.text if forecast is not None else "",
                            'previous': previous.text if previous is not None else "",
                            'source': 'forex_factory'
                        })
                
                print(f"[Calendar] Fetched {len(events)} events from Forex Factory")
    except Exception as e:
        print(f"[Calendar] Forex Factory fetch error: {e}")
    
    return events


async def fetch_investing_calendar() -> List[dict]:
    """
    Fetch events from Investing.com RSS.
    """
    events = []
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Try the economic calendar RSS
            url = "https://www.investing.com/rss/economic_calendar.rss"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = await client.get(url, headers=headers)
            
            if response.status_code == 200:
                root = ET.fromstring(response.text)
                
                for item in root.findall('.//item'):
                    title = item.find('title')
                    pub_date = item.find('pubDate')
                    description = item.find('description')
                    
                    if title is not None:
                        # Parse currency from title
                        title_text = title.text or ""
                        currency = ""
                        for curr in ['USD', 'EUR', 'GBP', 'JPY', 'CHF', 'CAD', 'AUD', 'NZD']:
                            if curr in title_text:
                                currency = curr
                                break
                        
                        events.append({
                            'title': title_text,
                            'currency': currency,
                            'date': pub_date.text if pub_date is not None else "",
                            'time': "",
                            'impact': 'MEDIUM',  # RSS doesn't include impact
                            'source': 'investing'
                        })
                
                print(f"[Calendar] Fetched {len(events)} events from Investing.com")
    except Exception as e:
        print(f"[Calendar] Investing.com fetch error: {e}")
    
    return events


def get_currency_from_country(country: str) -> str:
    """Map country to currency code."""
    mapping = {
        'United States': 'USD',
        'US': 'USD',
        'USA': 'USD',
        'European Union': 'EUR',
        'EU': 'EUR',
        'Eurozone': 'EUR',
        'Germany': 'EUR',
        'France': 'EUR',
        'Italy': 'EUR',
        'Spain': 'EUR',
        'United Kingdom': 'GBP',
        'UK': 'GBP',
        'Britain': 'GBP',
        'Japan': 'JPY',
        'Switzerland': 'CHF',
        'Canada': 'CAD',
        'Australia': 'AUD',
        'New Zealand': 'NZD',
        'China': 'CNY',
    }
    return mapping.get(country, country[:3].upper() if country else "")


def get_static_high_impact_events() -> List[dict]:
    """
    Return known recurring high-impact events.
    These are supplementary to live data.
    """
    # Get current week dates
    today = datetime.utcnow()
    
    # Static high-impact events that occur regularly
    recurring_events = [
        # US Events
        {"title": "US Non-Farm Payrolls", "currency": "USD", "impact": "HIGH", "day": 4, "time": "08:30"},  # First Friday
        {"title": "US Core CPI", "currency": "USD", "impact": "HIGH", "day": 2, "time": "08:30"},
        {"title": "FOMC Statement", "currency": "USD", "impact": "HIGH", "day": 2, "time": "14:00"},
        {"title": "Fed Chair Powell Speech", "currency": "USD", "impact": "HIGH", "day": 3, "time": "10:00"},
        {"title": "US Retail Sales", "currency": "USD", "impact": "HIGH", "day": 1, "time": "08:30"},
        {"title": "US GDP", "currency": "USD", "impact": "HIGH", "day": 3, "time": "08:30"},
        
        # UK Events
        {"title": "UK GDP", "currency": "GBP", "impact": "HIGH", "day": 2, "time": "07:00"},
        {"title": "BOE Rate Decision", "currency": "GBP", "impact": "HIGH", "day": 3, "time": "12:00"},
        {"title": "UK CPI", "currency": "GBP", "impact": "HIGH", "day": 2, "time": "07:00"},
        
        # EUR Events
        {"title": "ECB Rate Decision", "currency": "EUR", "impact": "HIGH", "day": 3, "time": "13:45"},
        {"title": "German ZEW Sentiment", "currency": "EUR", "impact": "MEDIUM", "day": 1, "time": "10:00"},
        {"title": "Eurozone CPI", "currency": "EUR", "impact": "HIGH", "day": 0, "time": "10:00"},
        
        # JPY Events
        {"title": "BOJ Rate Decision", "currency": "JPY", "impact": "HIGH", "day": 2, "time": "03:00"},
        {"title": "Japan GDP", "currency": "JPY", "impact": "HIGH", "day": 0, "time": "23:50"},
        
        # AUD Events
        {"title": "RBA Rate Decision", "currency": "AUD", "impact": "HIGH", "day": 1, "time": "04:30"},
        {"title": "Australia Employment", "currency": "AUD", "impact": "HIGH", "day": 3, "time": "00:30"},
        
        # CAD Events
        {"title": "BOC Rate Decision", "currency": "CAD", "impact": "HIGH", "day": 2, "time": "15:00"},
        {"title": "Canada Employment", "currency": "CAD", "impact": "HIGH", "day": 4, "time": "08:30"},
        
        # NZD Events
        {"title": "RBNZ Rate Decision", "currency": "NZD", "impact": "HIGH", "day": 2, "time": "02:00"},
        
        # CHF Events
        {"title": "SNB Rate Decision", "currency": "CHF", "impact": "HIGH", "day": 3, "time": "08:30"},
    ]
    
    events = []
    for event in recurring_events:
        # Calculate the date for this week
        days_until = (event['day'] - today.weekday()) % 7
        event_date = today + timedelta(days=days_until)
        
        events.append({
            'title': event['title'],
            'currency': event['currency'],
            'date': event_date.strftime('%Y-%m-%d'),
            'time': event['time'],
            'impact': event['impact'],
            'source': 'static'
        })
    
    return events


async def get_economic_calendar(force_refresh: bool = False) -> List[dict]:
    """
    Get economic calendar events.
    Combines multiple sources and caches results.
    """
    # Check cache
    if not force_refresh and CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, 'r') as f:
                cache = json.load(f)
                cache_time = datetime.fromisoformat(cache.get('timestamp', '2000-01-01'))
                if datetime.utcnow() - cache_time < CACHE_DURATION:
                    return cache.get('events', [])
        except Exception:
            pass
    
    # Fetch from sources
    all_events = []
    
    # Try Forex Factory first (most reliable)
    ff_events = await fetch_forex_factory_calendar()
    all_events.extend(ff_events)
    
    # Add static high-impact events as backup
    static_events = get_static_high_impact_events()
    
    # Merge: prefer live events, add static if not already present
    existing_titles = {e['title'].lower() for e in all_events}
    for event in static_events:
        if event['title'].lower() not in existing_titles:
            all_events.append(event)
    
    # Sort by date and time
    def sort_key(e):
        date_str = e.get('date', '')
        time_str = e.get('time', '00:00')
        try:
            if 'T' in date_str:
                return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        except:
            return datetime.max
    
    all_events.sort(key=sort_key)
    
    # Cache results
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump({
                'timestamp': datetime.utcnow().isoformat(),
                'events': all_events
            }, f)
    except Exception:
        pass
    
    return all_events


async def get_upcoming_events(hours: int = 24, currencies: List[str] = None) -> List[dict]:
    """
    Get events happening in the next N hours.
    Optionally filter by currencies.
    """
    events = await get_economic_calendar()
    
    now = datetime.utcnow()
    cutoff = now + timedelta(hours=hours)
    
    upcoming = []
    for event in events:
        # Parse event datetime
        try:
            date_str = event.get('date', '')
            time_str = event.get('time', '00:00')
            
            if time_str in ['All Day', 'Tentative', '']:
                time_str = '12:00'
            
            if 'T' in date_str:
                event_dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            else:
                event_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            
            # Check if within window
            if now <= event_dt <= cutoff:
                # Filter by currency if specified
                if currencies is None or event.get('currency', '') in currencies:
                    event['datetime'] = event_dt.isoformat()
                    upcoming.append(event)
        except Exception:
            continue
    
    return upcoming


async def get_high_impact_events(hours: int = 24) -> List[dict]:
    """Get only HIGH impact events in the next N hours."""
    events = await get_upcoming_events(hours)
    return [e for e in events if e.get('impact') == 'HIGH']


def format_event_for_display(event: dict) -> dict:
    """Format event for dashboard display."""
    return {
        'time': event.get('time', ''),
        'currency': event.get('currency', ''),
        'title': event.get('title', ''),
        'impact': event.get('impact', 'LOW'),
        'forecast': event.get('forecast', ''),
        'previous': event.get('previous', ''),
    }


if __name__ == "__main__":
    # Test
    async def test():
        print("Fetching economic calendar...")
        events = await get_economic_calendar(force_refresh=True)
        print(f"Total events: {len(events)}")
        
        print("\nHigh impact events next 24h:")
        high_impact = await get_high_impact_events(24)
        for e in high_impact[:10]:
            print(f"  {e.get('time', 'TBD')} {e.get('currency', '')} - {e.get('title', '')}")
    
    asyncio.run(test())
