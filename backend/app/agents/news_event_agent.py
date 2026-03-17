"""
News & Event Agent

Monitors economic calendar and news events:
- Economic calendar integration
- Event impact assessment
- Trading blackout enforcement
- Event-based risk adjustments
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

from app.agents.base_agent import BaseAgent, AgentOutput


class EventImpact(Enum):
    """Economic event impact level."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    HOLIDAY = "holiday"


class EventStatus(Enum):
    """Event timing status."""
    UPCOMING = "upcoming"
    IMMINENT = "imminent"  # Within blackout window
    ACTIVE = "active"  # Currently happening
    RECENT = "recent"  # Just passed
    PASSED = "passed"


@dataclass
class EconomicEvent:
    """Economic calendar event."""
    event_id: str
    title: str
    country: str
    currency: str
    impact: EventImpact
    scheduled_time: datetime
    
    # Forecast vs actual
    previous: Optional[float] = None
    forecast: Optional[float] = None
    actual: Optional[float] = None
    
    # Status
    status: EventStatus = EventStatus.UPCOMING
    
    # Related pairs
    affected_pairs: List[str] = field(default_factory=list)


@dataclass
class EventRiskAssessment:
    """Risk assessment for current event landscape."""
    # Overall risk level
    risk_level: str  # "normal", "elevated", "high", "extreme"
    risk_score: float  # 0.0 - 1.0
    
    # Recommendations
    should_trade: bool
    position_size_multiplier: float  # 0.0 - 1.0
    
    # Active concerns
    upcoming_high_impact: List[EconomicEvent]
    blackout_symbols: List[str]
    
    # Reasoning
    reasons: List[str]


class NewsEventAgent(BaseAgent):
    """Monitors news and economic events for trading decisions."""
    
    # Blackout windows (minutes before/after high-impact events)
    BLACKOUT_BEFORE_HIGH = 30
    BLACKOUT_AFTER_HIGH = 15
    BLACKOUT_BEFORE_MEDIUM = 15
    BLACKOUT_AFTER_MEDIUM = 5
    
    # Currency to pair mapping
    CURRENCY_PAIRS = {
        "USD": ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD"],
        "EUR": ["EURUSD", "EURAUD"],
        "GBP": ["GBPUSD", "GBPJPY"],
        "JPY": ["USDJPY", "GBPJPY"],
        "CHF": ["USDCHF"],
        "CAD": ["USDCAD"],
        "AUD": ["AUDUSD", "EURAUD", "AUDNZD"],
        "NZD": ["AUDNZD"],
    }
    
    def __init__(self, db_session=None, redis_client=None):
        super().__init__(
            name="NewsEventAgent",
            description="Monitors economic calendar and news events",
            dependencies=[]
        )
        self.db = db_session
        self.redis = redis_client
        
        self.events: List[EconomicEvent] = []
        self.last_calendar_update: Optional[datetime] = None
    
    async def analyze(self, context: Dict[str, Any]) -> AgentOutput:
        """Analyze current event landscape."""
        try:
            # Refresh calendar if stale
            if self._should_refresh_calendar():
                await self._fetch_calendar()
            
            # Update event statuses
            self._update_event_statuses()
            
            # Assess risk
            assessment = self._assess_event_risk()
            
            # Get upcoming events summary
            upcoming = self._get_upcoming_events(hours=24)
            
            return AgentOutput(
                agent_name=self.name,
                timestamp=datetime.utcnow(),
                data={
                    "assessment": {
                        "risk_level": assessment.risk_level,
                        "risk_score": assessment.risk_score,
                        "should_trade": assessment.should_trade,
                        "position_size_multiplier": assessment.position_size_multiplier,
                        "blackout_symbols": assessment.blackout_symbols,
                        "reasons": assessment.reasons,
                    },
                    "upcoming_events": [self._event_to_dict(e) for e in upcoming],
                    "high_impact_next_24h": [
                        self._event_to_dict(e) for e in upcoming 
                        if e.impact == EventImpact.HIGH
                    ],
                    "imminent_events": [
                        self._event_to_dict(e) for e in self.events
                        if e.status == EventStatus.IMMINENT
                    ],
                },
                confidence=0.9,
                metadata={
                    "total_events_tracked": len(self.events),
                    "calendar_last_updated": self.last_calendar_update.isoformat() if self.last_calendar_update else None,
                }
            )
            
        except Exception as e:
            self.logger.error(f"News event analysis failed: {e}")
            return AgentOutput(
                agent_name=self.name,
                timestamp=datetime.utcnow(),
                data={"assessment": {"should_trade": True, "position_size_multiplier": 1.0}},
                confidence=0.5,
                errors=[str(e)]
            )
    
    def _should_refresh_calendar(self) -> bool:
        """Check if calendar needs refresh."""
        if not self.last_calendar_update:
            return True
        
        # Refresh every hour
        return datetime.utcnow() - self.last_calendar_update > timedelta(hours=1)
    
    async def _fetch_calendar(self):
        """Fetch economic calendar from data source."""
        # TODO: Integrate with actual economic calendar API
        # Options: Forex Factory, Investing.com, TradingView, MetaTrader
        
        # For now, use placeholder events
        self.events = self._get_placeholder_events()
        self.last_calendar_update = datetime.utcnow()
        
        self.logger.info(f"Calendar refreshed: {len(self.events)} events loaded")
    
    def _get_placeholder_events(self) -> List[EconomicEvent]:
        """Generate placeholder events for testing."""
        now = datetime.utcnow()
        
        return [
            EconomicEvent(
                event_id="nfp_1",
                title="Non-Farm Payrolls",
                country="US",
                currency="USD",
                impact=EventImpact.HIGH,
                scheduled_time=now + timedelta(hours=8),
                previous=236.0,
                forecast=180.0,
                affected_pairs=self.CURRENCY_PAIRS["USD"],
            ),
            EconomicEvent(
                event_id="ecb_1",
                title="ECB Interest Rate Decision",
                country="EU",
                currency="EUR",
                impact=EventImpact.HIGH,
                scheduled_time=now + timedelta(hours=4),
                affected_pairs=self.CURRENCY_PAIRS["EUR"],
            ),
            EconomicEvent(
                event_id="uk_cpi",
                title="UK CPI y/y",
                country="UK",
                currency="GBP",
                impact=EventImpact.MEDIUM,
                scheduled_time=now + timedelta(hours=2),
                previous=3.2,
                forecast=3.0,
                affected_pairs=self.CURRENCY_PAIRS["GBP"],
            ),
        ]
    
    def _update_event_statuses(self):
        """Update status of all events based on current time."""
        now = datetime.utcnow()
        
        for event in self.events:
            minutes_until = (event.scheduled_time - now).total_seconds() / 60
            
            if minutes_until < -60:
                event.status = EventStatus.PASSED
            elif minutes_until < -5:
                event.status = EventStatus.RECENT
            elif minutes_until < 5:
                event.status = EventStatus.ACTIVE
            elif event.impact == EventImpact.HIGH and minutes_until < self.BLACKOUT_BEFORE_HIGH:
                event.status = EventStatus.IMMINENT
            elif event.impact == EventImpact.MEDIUM and minutes_until < self.BLACKOUT_BEFORE_MEDIUM:
                event.status = EventStatus.IMMINENT
            else:
                event.status = EventStatus.UPCOMING
    
    def _assess_event_risk(self) -> EventRiskAssessment:
        """Assess overall event risk for trading."""
        now = datetime.utcnow()
        
        blackout_symbols = set()
        upcoming_high = []
        reasons = []
        
        for event in self.events:
            if event.status == EventStatus.PASSED:
                continue
            
            minutes_until = (event.scheduled_time - now).total_seconds() / 60
            
            # Check if in blackout window
            if event.impact == EventImpact.HIGH:
                if -self.BLACKOUT_AFTER_HIGH < minutes_until < self.BLACKOUT_BEFORE_HIGH:
                    blackout_symbols.update(event.affected_pairs)
                    reasons.append(f"HIGH IMPACT: {event.title} ({event.currency}) in {int(minutes_until)} min")
                
                if 0 < minutes_until < 120:
                    upcoming_high.append(event)
            
            elif event.impact == EventImpact.MEDIUM:
                if -self.BLACKOUT_AFTER_MEDIUM < minutes_until < self.BLACKOUT_BEFORE_MEDIUM:
                    blackout_symbols.update(event.affected_pairs)
                    reasons.append(f"MEDIUM IMPACT: {event.title} ({event.currency}) in {int(minutes_until)} min")
            
            elif event.impact == EventImpact.HOLIDAY:
                blackout_symbols.update(event.affected_pairs)
                reasons.append(f"HOLIDAY: {event.country}")
        
        # Calculate risk level
        if len(blackout_symbols) >= 6:
            risk_level = "extreme"
            risk_score = 0.9
            should_trade = False
            size_mult = 0.0
        elif len(blackout_symbols) >= 3 or len(upcoming_high) >= 2:
            risk_level = "high"
            risk_score = 0.7
            should_trade = True
            size_mult = 0.5
        elif len(blackout_symbols) > 0 or len(upcoming_high) >= 1:
            risk_level = "elevated"
            risk_score = 0.4
            should_trade = True
            size_mult = 0.75
        else:
            risk_level = "normal"
            risk_score = 0.1
            should_trade = True
            size_mult = 1.0
        
        return EventRiskAssessment(
            risk_level=risk_level,
            risk_score=risk_score,
            should_trade=should_trade,
            position_size_multiplier=size_mult,
            upcoming_high_impact=upcoming_high,
            blackout_symbols=list(blackout_symbols),
            reasons=reasons,
        )
    
    def _get_upcoming_events(self, hours: int = 24) -> List[EconomicEvent]:
        """Get events in the next N hours."""
        now = datetime.utcnow()
        cutoff = now + timedelta(hours=hours)
        
        return [
            e for e in self.events
            if now < e.scheduled_time < cutoff
        ]
    
    def _event_to_dict(self, event: EconomicEvent) -> Dict:
        """Convert event to dictionary."""
        return {
            "event_id": event.event_id,
            "title": event.title,
            "country": event.country,
            "currency": event.currency,
            "impact": event.impact.value,
            "scheduled_time": event.scheduled_time.isoformat(),
            "status": event.status.value,
            "previous": event.previous,
            "forecast": event.forecast,
            "actual": event.actual,
            "affected_pairs": event.affected_pairs,
        }
    
    def is_symbol_in_blackout(self, symbol: str) -> bool:
        """Check if a symbol is currently in event blackout."""
        assessment = self._assess_event_risk()
        return symbol in assessment.blackout_symbols
    
    def get_next_event_for_symbol(self, symbol: str) -> Optional[EconomicEvent]:
        """Get the next upcoming event affecting a symbol."""
        now = datetime.utcnow()
        
        relevant = [
            e for e in self.events
            if symbol in e.affected_pairs and e.scheduled_time > now
        ]
        
        if not relevant:
            return None
        
        return min(relevant, key=lambda e: e.scheduled_time)
