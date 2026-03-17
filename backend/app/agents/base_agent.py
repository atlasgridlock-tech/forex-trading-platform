"""
Base Agent Framework

Each agent runs as a persistent async task with:
- Own state stored in Redis
- LLM access for reasoning
- Pub/sub communication with other agents
- Queryable via API
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum
from dataclasses import dataclass, field
import redis.asyncio as redis
import httpx

logger = logging.getLogger(__name__)


class AgentHealthStatus(str, Enum):
    """Health status for agents."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class AgentMessage:
    """Message passed between agents."""
    from_agent: str
    to_agent: str
    message_type: str
    payload: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    correlation_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "message_type": self.message_type,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentMessage":
        return cls(
            from_agent=data["from_agent"],
            to_agent=data["to_agent"],
            message_type=data["message_type"],
            payload=data["payload"],
            timestamp=datetime.fromisoformat(data["timestamp"]) if isinstance(data.get("timestamp"), str) else datetime.utcnow(),
            correlation_id=data.get("correlation_id"),
        )


@dataclass
class AgentOutput:
    """Standard output format for agent analysis."""
    agent_id: str
    agent_name: str
    timestamp: datetime
    symbol: Optional[str] = None
    analysis: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    signals: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "analysis": self.analysis,
            "confidence": self.confidence,
            "signals": self.signals,
            "recommendations": self.recommendations,
            "metadata": self.metadata,
        }


class BaseAgent(ABC):
    """Base class for all AI-powered trading agents."""
    
    def __init__(
        self,
        agent_id: str,
        name: str,
        role: str,
        redis_url: str = "redis://localhost:6379",
        llm_model: str = "claude-sonnet-4-20250514",
    ):
        self.agent_id = agent_id
        self.name = name
        self.role = role
        self.redis_url = redis_url
        self.llm_model = llm_model
        
        self.redis: Optional[redis.Redis] = None
        self.pubsub: Optional[redis.client.PubSub] = None
        self.running = False
        
        # Agent state
        self.state: Dict[str, Any] = {
            "status": "initializing",
            "last_update": None,
            "last_analysis": None,
            "current_view": {},
        }
        
        # System prompt for this agent's personality
        self.system_prompt = self._build_system_prompt()
    
    def _build_system_prompt(self) -> str:
        """Build the agent's personality/system prompt."""
        return f"""You are {self.name}, a specialized AI agent in a forex trading system.

ROLE: {self.role}

PERSONALITY:
- You are focused, analytical, and concise
- You provide actionable insights, not generic advice
- You express confidence levels in your assessments
- You flag important events or risks immediately
- You communicate in a professional but conversational tone

CONTEXT:
- You are part of a multi-agent trading system
- Your analysis feeds into the Orchestrator's decisions
- You monitor: EURUSD, GBPUSD, USDJPY, GBPJPY, USDCHF, USDCAD, EURAUD, AUDNZD, AUDUSD
- Primary timeframe: M30, with H1/H4/D1 for context

When analyzing, structure your response as:
1. KEY FINDING (one line)
2. IMPACT ASSESSMENT (which pairs, direction, magnitude)
3. CONFIDENCE (low/medium/high)
4. RECOMMENDED ACTION (for the orchestrator)
"""
    
    async def connect(self):
        """Connect to Redis."""
        self.redis = redis.from_url(self.redis_url, decode_responses=True)
        self.pubsub = self.redis.pubsub()
        
        # Subscribe to agent channels
        await self.pubsub.subscribe(
            f"agent:{self.agent_id}:commands",  # Direct commands to this agent
            "agents:broadcast",  # Broadcast to all agents
            "market:updates",  # Market data updates
        )
        
        logger.info(f"[{self.name}] Connected to Redis")
    
    async def disconnect(self):
        """Disconnect from Redis."""
        if self.pubsub:
            await self.pubsub.unsubscribe()
        if self.redis:
            await self.redis.close()
    
    async def save_state(self):
        """Save agent state to Redis."""
        self.state["last_update"] = datetime.utcnow().isoformat()
        await self.redis.hset(
            f"agent:{self.agent_id}:state",
            mapping={k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) 
                     for k, v in self.state.items()}
        )
    
    async def load_state(self):
        """Load agent state from Redis."""
        data = await self.redis.hgetall(f"agent:{self.agent_id}:state")
        if data:
            for k, v in data.items():
                try:
                    self.state[k] = json.loads(v)
                except:
                    self.state[k] = v
    
    async def publish(self, channel: str, message: Dict[str, Any]):
        """Publish a message to a channel."""
        message["from_agent"] = self.agent_id
        message["timestamp"] = datetime.utcnow().isoformat()
        await self.redis.publish(channel, json.dumps(message))
    
    async def call_llm(self, prompt: str, context: str = "") -> str:
        """Call the LLM for reasoning."""
        try:
            # Use Anthropic API directly
            import os
            api_key = os.getenv("ANTHROPIC_API_KEY")
            
            if not api_key:
                logger.warning(f"[{self.name}] No API key, using mock response")
                return self._mock_llm_response(prompt)
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": self.llm_model,
                        "max_tokens": 1024,
                        "system": self.system_prompt,
                        "messages": [
                            {"role": "user", "content": f"{context}\n\n{prompt}" if context else prompt}
                        ]
                    },
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return data["content"][0]["text"]
                else:
                    logger.error(f"[{self.name}] LLM error: {response.status_code}")
                    return self._mock_llm_response(prompt)
                    
        except Exception as e:
            logger.error(f"[{self.name}] LLM call failed: {e}")
            return self._mock_llm_response(prompt)
    
    def _mock_llm_response(self, prompt: str) -> str:
        """Fallback response when LLM is unavailable."""
        return f"[{self.name}] Analysis pending - LLM unavailable. Monitoring continues."
    
    async def handle_query(self, query: str) -> str:
        """Handle a direct query to this agent."""
        context = f"Current state: {json.dumps(self.state.get('current_view', {}), indent=2)}"
        response = await self.call_llm(query, context)
        return response
    
    @abstractmethod
    async def analyze(self) -> Dict[str, Any]:
        """Run the agent's main analysis. Override in subclass."""
        pass
    
    @abstractmethod
    async def get_view(self, symbol: str = None) -> Dict[str, Any]:
        """Get the agent's current view. Override in subclass."""
        pass
    
    async def run(self):
        """Main agent loop."""
        await self.connect()
        await self.load_state()
        
        self.running = True
        self.state["status"] = "running"
        await self.save_state()
        
        logger.info(f"[{self.name}] Started")
        
        try:
            while self.running:
                # Process messages
                message = await self.pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message["type"] == "message":
                    await self._handle_message(message)
                
                # Run periodic analysis
                await self.analyze()
                await self.save_state()
                
                # Sleep between cycles
                await asyncio.sleep(30)  # Analyze every 30 seconds
                
        except asyncio.CancelledError:
            logger.info(f"[{self.name}] Shutting down")
        finally:
            self.running = False
            self.state["status"] = "stopped"
            await self.save_state()
            await self.disconnect()
    
    async def _handle_message(self, message: Dict):
        """Handle incoming pub/sub message."""
        try:
            data = json.loads(message["data"])
            channel = message["channel"]
            
            if "query" in data:
                # Someone is asking this agent a question
                response = await self.handle_query(data["query"])
                await self.publish(
                    f"agent:{data.get('reply_to', 'orchestrator')}:responses",
                    {"response": response, "query": data["query"]}
                )
            elif channel == "market:updates":
                # New market data
                await self.on_market_update(data)
                
        except Exception as e:
            logger.error(f"[{self.name}] Message handling error: {e}")
    
    async def on_market_update(self, data: Dict):
        """Handle market data update. Override for custom behavior."""
        pass
