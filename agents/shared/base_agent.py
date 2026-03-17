"""
Base Agent Class
Provides common functionality for all trading agents.
"""

import os
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .utils import (
    call_claude, 
    get_agent_url, 
    fetch_json, 
    post_json,
    get_current_session,
    FOREX_SYMBOLS,
)
from .agent_output import AgentOutput, OutputType


class ChatRequest(BaseModel):
    """Standard chat request model."""
    message: str


class BaseAgent:
    """
    Base class for trading platform agents.
    
    Provides:
    - Standard status endpoint
    - Chat with Claude
    - Orchestrator communication
    - Background task management
    """
    
    def __init__(
        self,
        agent_id: str,
        agent_name: str,
        app: FastAPI,
        version: str = "2.0",
    ):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.app = app
        self.version = version
        self.workspace = Path("/app/workspace")
        self.status = "active"
        self.metrics: Dict[str, Any] = {}
        
        # Output handler for orchestrator communication
        self.output = AgentOutput(agent_id, agent_name)
        
        # Register standard endpoints
        self._register_endpoints()
    
    def _register_endpoints(self):
        """Register standard API endpoints."""
        
        @self.app.get("/api/status")
        async def get_status():
            return self.get_status()
        
        @self.app.post("/chat")
        async def chat(request: ChatRequest):
            return await self.handle_chat(request.message)
    
    def get_status(self) -> dict:
        """Get agent status. Override to add custom fields."""
        return {
            "agent_id": self.agent_id,
            "name": self.agent_name,
            "status": self.status,
            "version": self.version,
            "session": get_current_session(),
            **self.metrics,
        }
    
    async def handle_chat(self, message: str) -> dict:
        """Handle chat request. Override to customize context."""
        context = self.get_chat_context()
        response = await call_claude(
            prompt=message,
            context=context,
            agent_name=self.agent_name,
        )
        return {"response": response}
    
    def get_chat_context(self) -> str:
        """Get context for chat. Override to customize."""
        return f"Agent: {self.agent_name}\nStatus: {self.status}"
    
    async def send_to_orchestrator(self, output_type: OutputType, data: dict):
        """Send data to orchestrator."""
        await self.output.send(output_type, data)
    
    async def fetch_from_agent(self, agent: str, endpoint: str) -> Optional[dict]:
        """Fetch data from another agent."""
        url = get_agent_url(agent)
        if url:
            return await fetch_json(f"{url}{endpoint}")
        return None
    
    def update_metric(self, key: str, value: Any):
        """Update a metric for status reporting."""
        self.metrics[key] = value
    
    def set_status(self, status: str):
        """Set agent status."""
        self.status = status


class AnalysisAgent(BaseAgent):
    """
    Base class for analysis agents (technical, structure, regime, etc.)
    
    Provides:
    - Symbol iteration
    - Analysis caching
    - Background analysis loop
    """
    
    def __init__(
        self,
        agent_id: str,
        agent_name: str,
        app: FastAPI,
        symbols: List[str] = None,
        analysis_interval: int = 60,
        version: str = "2.0",
    ):
        super().__init__(agent_id, agent_name, app, version)
        self.symbols = symbols or FOREX_SYMBOLS
        self.analysis_interval = analysis_interval
        self.analysis_cache: Dict[str, dict] = {}
        self._analysis_task: Optional[asyncio.Task] = None
    
    async def start_background_analysis(self):
        """Start background analysis loop."""
        self._analysis_task = asyncio.create_task(self._analysis_loop())
    
    async def stop_background_analysis(self):
        """Stop background analysis loop."""
        if self._analysis_task:
            self._analysis_task.cancel()
            try:
                await self._analysis_task
            except asyncio.CancelledError:
                pass
    
    async def _analysis_loop(self):
        """Background loop that analyzes all symbols."""
        while True:
            for symbol in self.symbols:
                try:
                    analysis = await self.analyze(symbol)
                    if analysis and "error" not in analysis:
                        self.analysis_cache[symbol] = analysis
                        await self.on_analysis_complete(symbol, analysis)
                except Exception as e:
                    print(f"[{self.agent_name}] Error analyzing {symbol}: {e}")
            
            await asyncio.sleep(self.analysis_interval)
    
    async def analyze(self, symbol: str) -> dict:
        """
        Analyze a symbol. Must be implemented by subclass.
        
        Returns:
            Analysis dict or {"error": "message"}
        """
        raise NotImplementedError("Subclass must implement analyze()")
    
    async def on_analysis_complete(self, symbol: str, analysis: dict):
        """
        Called after analysis completes. Override to send to orchestrator.
        """
        pass
    
    def get_cached_analysis(self, symbol: str) -> Optional[dict]:
        """Get cached analysis for a symbol."""
        return self.analysis_cache.get(symbol.upper())
    
    def get_all_analysis(self) -> dict:
        """Get all cached analyses."""
        return self.analysis_cache
    
    def get_status(self) -> dict:
        """Get status with analysis metrics."""
        base = super().get_status()
        base["symbols_analyzed"] = len(self.analysis_cache)
        base["total_symbols"] = len(self.symbols)
        return base
