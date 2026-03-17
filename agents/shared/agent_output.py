"""
Agent Output Module - Hub-and-Spoke Architecture
All agents send payloads ONLY to the Orchestrator (Nexus)
Agents do NOT communicate with each other to prevent bias
"""

import os
import json
import httpx
from datetime import datetime
from typing import Dict, Any, Optional
from enum import Enum

ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://orchestrator-agent:8000")


class OutputType(str, Enum):
    ANALYSIS = "analysis"       # Regular analysis update
    SIGNAL = "signal"           # Trade signal (bullish/bearish)
    ALERT = "alert"             # Important alert
    REGIME_CHANGE = "regime"    # Market regime changed
    RISK_VETO = "veto"          # Risk agent blocking trade
    EXECUTION = "execution"     # Trade executed
    HEARTBEAT = "heartbeat"     # Agent alive status


class AgentOutput:
    """
    Send agent outputs ONLY to the Orchestrator.
    
    Architecture:
    ┌─────────┐     ┌─────────┐     ┌─────────┐
    │ Sentinel│     │ Oracle  │     │Atlas Jr │
    └────┬────┘     └────┬────┘     └────┬────┘
         │               │               │
         └───────────────┼───────────────┘
                         ▼
                   ┌───────────┐
                   │   NEXUS   │  ◄── All data flows here
                   │Orchestrator│
                   └─────┬─────┘
                         │
                         ▼
                   ┌───────────┐
                   │ Decisions │
                   └───────────┘
    
    Agents NEVER talk to each other. This prevents:
    - Confirmation bias
    - Cascade errors  
    - Echo chambers
    """
    
    def __init__(self, agent_id: str, agent_name: str):
        self.agent_id = agent_id
        self.agent_name = agent_name
        
    def _build_payload(self, output_type: OutputType, data: Dict[str, Any]) -> dict:
        """Build standardized payload envelope."""
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "output_type": output_type.value,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data,
        }
    
    async def send(self, output_type: OutputType, data: Dict[str, Any]) -> bool:
        """Send payload to Orchestrator."""
        payload = self._build_payload(output_type, data)
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{ORCHESTRATOR_URL}/api/ingest",
                    json=payload,
                    timeout=5.0
                )
                return response.status_code == 200
        except Exception as e:
            print(f"[{self.agent_name}] Failed to send to Orchestrator: {e}")
            return False
    
    async def send_analysis(self, symbol: str, analysis: dict):
        """Send analysis update."""
        await self.send(OutputType.ANALYSIS, {
            "symbol": symbol,
            **analysis
        })
    
    async def send_signal(self, symbol: str, direction: str, confidence: float, 
                          reason: str, entry: float = None, stop: float = None):
        """Send trade signal."""
        await self.send(OutputType.SIGNAL, {
            "symbol": symbol,
            "direction": direction,  # bullish, bearish, neutral
            "confidence": confidence,
            "reason": reason,
            "entry": entry,
            "stop": stop,
        })
    
    async def send_alert(self, level: str, message: str, data: dict = None):
        """Send alert (info, warning, critical)."""
        await self.send(OutputType.ALERT, {
            "level": level,
            "message": message,
            "details": data or {},
        })
    
    async def send_regime_change(self, symbol: str, old_regime: str, new_regime: str):
        """Send regime change notification."""
        await self.send(OutputType.REGIME_CHANGE, {
            "symbol": symbol,
            "old_regime": old_regime,
            "new_regime": new_regime,
        })
    
    async def send_veto(self, reason: str, trade_id: str = None):
        """Risk agent: veto a proposed trade."""
        await self.send(OutputType.RISK_VETO, {
            "reason": reason,
            "trade_id": trade_id,
            "veto": True,
        })
    
    async def send_execution(self, order_id: str, symbol: str, direction: str, 
                             status: str, fill_price: float = None):
        """Execution agent: report trade execution."""
        await self.send(OutputType.EXECUTION, {
            "order_id": order_id,
            "symbol": symbol,
            "direction": direction,
            "status": status,
            "fill_price": fill_price,
        })
    
    async def heartbeat(self, status: str = "active", metrics: dict = None):
        """Send heartbeat."""
        await self.send(OutputType.HEARTBEAT, {
            "status": status,
            "metrics": metrics or {},
        })


# Payload schemas for documentation
PAYLOAD_SCHEMAS = {
    "analysis": {
        "agent_id": "technical",
        "output_type": "analysis",
        "data": {
            "symbol": "EURUSD",
            "bias": "bearish",
            "confidence": 0.72,
            "indicators": {}
        }
    },
    "signal": {
        "agent_id": "technical",
        "output_type": "signal",
        "data": {
            "symbol": "EURUSD",
            "direction": "bearish",
            "confidence": 0.75,
            "reason": "Breakdown below support",
            "entry": 1.0850,
            "stop": 1.0890
        }
    },
    "veto": {
        "agent_id": "risk",
        "output_type": "veto",
        "data": {
            "reason": "Daily loss limit reached",
            "veto": True
        }
    }
}
