"""
Inter-Agent Communication via Redis Pub/Sub
Shared module for all agents
"""

import os
import json
import asyncio
from datetime import datetime
from typing import Callable, Dict, Any, Optional
import redis.asyncio as redis

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")

# Channel names
CHANNELS = {
    "broadcast": "agents:broadcast",           # All agents
    "news": "agents:news",                     # News events
    "macro": "agents:macro",                   # Macro updates
    "technical": "agents:technical",           # Technical signals
    "risk": "agents:risk",                     # Risk alerts
    "structure": "agents:structure",           # Structure updates
    "sentiment": "agents:sentiment",           # Sentiment changes
    "regime": "agents:regime",                 # Regime changes
    "strategy": "agents:strategy",             # Strategy selections
    "portfolio": "agents:portfolio",           # Portfolio updates
    "execution": "agents:execution",           # Execution events
    "orchestrator": "agents:orchestrator",     # Orchestrator commands
}


class AgentPubSub:
    """Pub/Sub client for inter-agent communication."""
    
    def __init__(self, agent_id: str, agent_name: str):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.redis: Optional[redis.Redis] = None
        self.pubsub: Optional[redis.client.PubSub] = None
        self.handlers: Dict[str, Callable] = {}
        self._running = False
        
    async def connect(self):
        """Connect to Redis."""
        self.redis = redis.from_url(REDIS_URL)
        self.pubsub = self.redis.pubsub()
        print(f"[{self.agent_name}] Connected to Redis pub/sub")
        
    async def disconnect(self):
        """Disconnect from Redis."""
        self._running = False
        if self.pubsub:
            await self.pubsub.close()
        if self.redis:
            await self.redis.close()
            
    async def subscribe(self, channels: list[str], handler: Callable):
        """Subscribe to channels with a message handler."""
        for channel in channels:
            channel_name = CHANNELS.get(channel, channel)
            self.handlers[channel_name] = handler
            await self.pubsub.subscribe(channel_name)
            print(f"[{self.agent_name}] Subscribed to {channel_name}")
            
    async def publish(self, channel: str, message: dict):
        """Publish a message to a channel."""
        channel_name = CHANNELS.get(channel, channel)
        envelope = {
            "from_agent": self.agent_id,
            "from_name": self.agent_name,
            "channel": channel,
            "timestamp": datetime.utcnow().isoformat(),
            "payload": message,
        }
        await self.redis.publish(channel_name, json.dumps(envelope))
        
    async def broadcast(self, message: dict):
        """Broadcast to all agents."""
        await self.publish("broadcast", message)
        
    async def alert(self, level: str, message: str, data: dict = None):
        """Send an alert to the broadcast channel."""
        await self.broadcast({
            "type": "alert",
            "level": level,  # info, warning, critical
            "message": message,
            "data": data or {},
        })
        
    async def listen(self):
        """Start listening for messages."""
        self._running = True
        print(f"[{self.agent_name}] Listening for messages...")
        
        while self._running:
            try:
                message = await self.pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0
                )
                if message and message["type"] == "message":
                    channel = message["channel"].decode()
                    data = json.loads(message["data"].decode())
                    
                    # Don't process own messages
                    if data.get("from_agent") == self.agent_id:
                        continue
                        
                    # Call handler if registered
                    if channel in self.handlers:
                        try:
                            await self.handlers[channel](data)
                        except Exception as e:
                            print(f"[{self.agent_name}] Handler error: {e}")
                            
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[{self.agent_name}] Listen error: {e}")
                await asyncio.sleep(1)


# Message types for type safety
class NewsAlert:
    def __init__(self, symbol: str, headline: str, impact: str, sentiment: str):
        self.symbol = symbol
        self.headline = headline
        self.impact = impact
        self.sentiment = sentiment
        
    def to_dict(self) -> dict:
        return {
            "type": "news_alert",
            "symbol": self.symbol,
            "headline": self.headline,
            "impact": self.impact,
            "sentiment": self.sentiment,
        }


class RiskAlert:
    def __init__(self, level: str, message: str, action: str = None):
        self.level = level  # warning, critical, halt
        self.message = message
        self.action = action
        
    def to_dict(self) -> dict:
        return {
            "type": "risk_alert",
            "level": self.level,
            "message": self.message,
            "action": self.action,
        }


class TradeSignal:
    def __init__(self, symbol: str, direction: str, confidence: float, 
                 entry: float = None, stop: float = None, target: float = None):
        self.symbol = symbol
        self.direction = direction
        self.confidence = confidence
        self.entry = entry
        self.stop = stop
        self.target = target
        
    def to_dict(self) -> dict:
        return {
            "type": "trade_signal",
            "symbol": self.symbol,
            "direction": self.direction,
            "confidence": self.confidence,
            "entry": self.entry,
            "stop": self.stop,
            "target": self.target,
        }


class RegimeChange:
    def __init__(self, symbol: str, old_regime: str, new_regime: str):
        self.symbol = symbol
        self.old_regime = old_regime
        self.new_regime = new_regime
        
    def to_dict(self) -> dict:
        return {
            "type": "regime_change",
            "symbol": self.symbol,
            "old_regime": self.old_regime,
            "new_regime": self.new_regime,
        }
