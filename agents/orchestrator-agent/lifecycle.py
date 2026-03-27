"""
Trade Lifecycle Manager - Core Module for Nexus
Implements the 14-step trade lifecycle
"""

import asyncio
import httpx
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from dataclasses import dataclass, field
from pydantic import BaseModel


class LifecycleStage(str, Enum):
    DATA_REFRESH = "data_refresh"
    REGIME_CLASSIFICATION = "regime_classification"
    MULTI_AGENT_ANALYSIS = "multi_agent_analysis"
    SETUP_GENERATION = "setup_generation"
    RISK_SCREENING = "risk_screening"
    PORTFOLIO_SCREENING = "portfolio_screening"
    EXECUTION_SCREENING = "execution_screening"
    TRADE_DECISION = "trade_decision"
    ORDER_ROUTING = "order_routing"
    ACTIVE_MONITORING = "active_monitoring"
    EXIT_MANAGEMENT = "exit_management"
    POST_TRADE_REVIEW = "post_trade_review"
    PERFORMANCE_ATTRIBUTION = "performance_attribution"
    STRATEGY_IMPROVEMENT = "strategy_improvement"


class TradeStatus(str, Enum):
    SCANNING = "scanning"
    SETUP_IDENTIFIED = "setup_identified"
    SCREENING = "screening"
    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING_ENTRY = "pending_entry"
    ACTIVE = "active"
    MONITORING = "monitoring"
    EXIT_PENDING = "exit_pending"
    CLOSED = "closed"
    REVIEWED = "reviewed"


class ExitReason(str, Enum):
    TP1_HIT = "tp1_hit"
    TP2_HIT = "tp2_hit"
    FULL_TARGET = "full_target"
    STOP_LOSS = "stop_loss"
    TRAILING_STOP = "trailing_stop"
    TIME_STOP = "time_stop"
    EVENT_RISK = "event_risk"
    THESIS_INVALIDATION = "thesis_invalidation"
    MANUAL = "manual"
    SYSTEM_HALT = "system_halt"


@dataclass
class ExitFramework:
    """Exit strategy configuration."""
    style: str  # fixed_r, structure_based, atr_trailing, partial_tp, time_stop, event_risk, thesis_invalidation
    tp1_r: float = 1.5
    tp1_pct: float = 0.5  # Take 50% at TP1
    tp2_r: float = 2.5
    tp2_pct: float = 0.3  # Take 30% at TP2
    runner_pct: float = 0.2  # 20% runner
    trail_atr_multiple: float = 2.0
    time_stop_bars: int = 12
    move_to_be_at_r: float = 1.0  # Move stop to breakeven at 1R


@dataclass
class TradeSetup:
    """Complete trade setup from Tactician."""
    setup_id: str
    symbol: str
    direction: str  # long/short
    template: str
    template_version: str
    
    # Entry
    entry_price: float
    entry_trigger: str
    
    # Stop/Target
    stop_loss: float
    take_profit_1: float
    take_profit_2: Optional[float] = None
    runner_target: Optional[float] = None
    
    # Thesis
    why_here: str = ""
    why_now: str = ""
    why_direction: str = ""
    invalidation: str = ""
    asymmetry: str = ""
    stand_aside_if: str = ""
    
    # Scores
    confidence: float = 0
    location_score: float = 0
    direction_score: float = 0
    trigger_score: float = 0
    filter_score: float = 0
    
    # Exit
    exit_framework: ExitFramework = field(default_factory=lambda: ExitFramework(style="partial_tp"))
    max_hold_bars: int = 20
    
    # Entry type (for limit orders)
    entry_type: str = "market"  # "market" or "limit"
    pullback_level: Optional[float] = None  # EMA level for limit orders
    
    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)
    valid_until: datetime = field(default_factory=lambda: datetime.utcnow() + timedelta(hours=4))


@dataclass
class ActiveTrade:
    """A trade that has been executed and is being monitored."""
    trade_id: str
    setup: TradeSetup
    status: TradeStatus
    
    # Execution
    entry_price_actual: float = 0
    entry_time: Optional[datetime] = None
    slippage_pips: float = 0
    position_size: float = 0
    broker_ticket: str = ""
    
    # Current state
    current_price: float = 0
    current_pnl_pips: float = 0
    current_pnl_r: float = 0
    bars_in_trade: int = 0
    max_favorable_excursion: float = 0
    max_adverse_excursion: float = 0
    
    # Partial exits
    tp1_hit: bool = False
    tp1_exit_price: float = 0
    tp2_hit: bool = False
    tp2_exit_price: float = 0
    stop_moved_to_be: bool = False
    
    # Exit
    exit_price: float = 0
    exit_time: Optional[datetime] = None
    exit_reason: Optional[ExitReason] = None
    
    # Review
    reviewed: bool = False
    review_notes: str = ""


@dataclass
class PendingOrder:
    """Tracks a pending (limit) order."""
    order_id: str
    ticket: int
    symbol: str
    direction: str  # buy_limit, sell_limit
    entry_price: float
    lots: float
    stop_loss: float
    take_profit: float
    created_at: datetime
    expiration_hours: int
    status: str = "pending"  # pending, filled, cancelled, expired


class LifecycleManager:
    """
    Manages the complete 14-step trade lifecycle.
    """
    
    def __init__(self, agent_urls: Dict[str, str]):
        self.agent_urls = agent_urls
        self.active_trades: Dict[str, ActiveTrade] = {}
        self.pending_setups: Dict[str, TradeSetup] = {}
        self.pending_orders: Dict[str, PendingOrder] = {}  # Track limit orders
        self.completed_trades: List[ActiveTrade] = []
        self.lifecycle_log: List[dict] = []
        self.pending_order_expiration_hours: int = 24  # Default expiration
        self.watchlist_callback = None  # Callback to add items to app's watchlist
    
    def set_watchlist_callback(self, callback):
        """Set callback function to add items to watchlist."""
        self.watchlist_callback = callback
    
    async def fetch_agent(self, agent: str, endpoint: str, timeout: float = 5.0) -> Optional[dict]:
        """Fetch data from an agent."""
        url = self.agent_urls.get(agent)
        if not url:
            return None
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(f"{url}{endpoint}", timeout=timeout)
                if r.status_code == 200:
                    return r.json()
                else:
                    print(f"[Lifecycle] ⚠️ GET {agent}{endpoint} returned {r.status_code}")
        except httpx.TimeoutException:
            print(f"[Lifecycle] ⚠️ Timeout fetching {agent}{endpoint}")
        except Exception as e:
            print(f"[Lifecycle] ⚠️ Error fetching {agent}{endpoint}: {e}")
        return None
    
    async def post_agent(self, agent: str, endpoint: str, data: dict, timeout: float = 10.0) -> Optional[dict]:
        """Post data to an agent."""
        url = self.agent_urls.get(agent)
        if not url:
            print(f"[Lifecycle] ❌ Agent '{agent}' URL not found")
            return None
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(f"{url}{endpoint}", json=data, timeout=timeout)
                response_data = r.json()
                if r.status_code == 200:
                    return response_data
                else:
                    print(f"[Lifecycle] ⚠️ {agent}{endpoint} returned status {r.status_code}: {response_data}")
                    return response_data  # Return response even if not 200 so caller can see rejection reason
        except httpx.TimeoutException:
            print(f"[Lifecycle] ❌ TIMEOUT calling {agent}{endpoint} (>{timeout}s)")
            return {"error": "timeout", "agent": agent, "endpoint": endpoint}
        except Exception as e:
            print(f"[Lifecycle] ❌ Error calling {agent}{endpoint}: {type(e).__name__}: {e}")
            return {"error": str(e), "agent": agent, "endpoint": endpoint}
        return None
    
    def log_stage(self, stage: LifecycleStage, symbol: str, data: dict):
        """Log a lifecycle stage event."""
        self.lifecycle_log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "stage": stage.value,
            "symbol": symbol,
            "data": data,
        })
    
    async def sync_with_mt5(self):
        """Sync active_trades with actual MT5 positions."""
        try:
            # Fetch positions from executor
            result = await self.fetch_agent("executor", "/api/positions")
            if not result:
                return
            
            # Handle both list format and dict format
            if isinstance(result, list):
                positions = result
            else:
                positions = result.get("positions", [])
            
            if not positions:
                return
            
            mt5_tickets = set()
            for pos in positions:
                ticket = pos.get("ticket")
                mt5_tickets.add(ticket)
                
                # Check if we're tracking this position
                tracked = False
                for trade_id, trade in self.active_trades.items():
                    if trade.broker_ticket == ticket:
                        tracked = True
                        # Update current price from MT5
                        trade.current_price = pos.get("current_price", trade.current_price)
                        break
                
                if not tracked:
                    # Add missing position to lifecycle tracking
                    symbol = pos.get("symbol", "").replace(".s", "").replace(".S", "").replace(".ecn", "").replace(".ECN", "")
                    pos_type = pos.get("type", "").upper()
                    direction = "long" if pos_type == "BUY" else "short" if pos_type == "SELL" else pos.get("direction", "long")
                    entry = pos.get("open_price", 0)
                    sl = pos.get("sl", 0)
                    tp = pos.get("tp", 0)
                    volume = pos.get("volume", 0.01)
                    profit = pos.get("profit", 0)
                    
                    # JPY pairs have 2 decimal places, others have 4
                    pip_multiplier = 100 if "JPY" in symbol else 10000
                    
                    # Calculate risk in pips for R calculation
                    risk_pips = abs(entry - sl) * pip_multiplier if sl else 1
                    
                    # Create a minimal setup
                    setup = TradeSetup(
                        setup_id=f"SYNC-{symbol}-{ticket}",
                        symbol=symbol,
                        direction=direction,
                        template="SYNCED",
                        template_version="1.0",
                        entry_price=entry,
                        entry_trigger="Synced from MT5",
                        stop_loss=sl,
                        take_profit_1=tp,
                    )
                    
                    trade = ActiveTrade(
                        trade_id=f"TRD-SYNC-{ticket}",
                        setup=setup,
                        entry_price_actual=entry,
                        entry_time=datetime.utcnow(),
                        broker_ticket=ticket,
                        position_size=volume,
                        status=TradeStatus.ACTIVE,
                        current_price=pos.get("current_price", entry),
                        current_pnl_pips=0,
                        current_pnl_r=0,
                    )
                    self.active_trades[trade.trade_id] = trade
                    print(f"🔄 Synced MT5 position: {symbol} {direction} (ticket: {ticket})")
                    
                    # Log synced position to Chronicle for visibility
                    await self.post_agent("chronicle", "/api/trade/execute", {
                        "trade_id": trade.trade_id,
                        "symbol": symbol,
                        "direction": direction,
                        "entry_price": entry,
                        "stop_loss": sl,
                        "take_profit": tp,
                        "lot_size": volume,
                        "strategy": "SYNCED_FROM_MT5",
                        "strategy_score": 0,
                        "confluence_score": 0,
                        "confluence_breakdown": {},
                        "thesis": {
                            "why_here": "Position synced from MT5",
                            "why_now": f"Existing position (ticket: {ticket})",
                            "why_direction": f"{direction.upper()} position",
                            "invalidation": f"SL at {sl}" if sl else "No SL set",
                        },
                        "agent_verdicts": {},
                        "broker_ticket": int(ticket) if ticket else 0,
                        "entry_type": "synced",
                        "timeframe": "H1",
                        "current_pnl": profit,
                    })
            
            # Remove trades that no longer exist in MT5
            to_remove = []
            for trade_id, trade in self.active_trades.items():
                if trade.broker_ticket not in mt5_tickets:
                    to_remove.append(trade_id)
                    trade.status = TradeStatus.CLOSED
                    self.completed_trades.append(trade)
            
            for trade_id in to_remove:
                del self.active_trades[trade_id]
                print(f"🔄 Removed closed trade: {trade_id}")
                
        except Exception as e:
            print(f"[Lifecycle] Error syncing with MT5: {e}")
    
    # ═══════════════════════════════════════════════════════════════
    # PENDING ORDER MANAGEMENT
    # ═══════════════════════════════════════════════════════════════
    
    async def place_pending_order(self, symbol: str, direction: str, lots: float,
                                   entry_price: float, stop_loss: float, take_profit: float = 0,
                                   expiration_hours: int = 24) -> Optional[PendingOrder]:
        """Place a pending (limit) order via Executor."""
        result = await self.post_agent("executor", "/api/place-pending", {
            "symbol": symbol,
            "direction": direction,
            "lots": lots,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "expiration_hours": expiration_hours,
        })
        
        if result and result.get("status") == "PENDING_PLACED":
            order_id = f"PENDING-{symbol}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
            order = PendingOrder(
                order_id=order_id,
                ticket=result.get("ticket", 0),
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                lots=lots,
                stop_loss=stop_loss,
                take_profit=take_profit,
                created_at=datetime.utcnow(),
                expiration_hours=expiration_hours,
                status="pending",
            )
            self.pending_orders[order_id] = order
            print(f"📋 Pending order placed: {symbol} {direction} @ {entry_price}")
            return order
        
        return None
    
    async def cancel_pending_order(self, order_id: str) -> bool:
        """Cancel a pending order."""
        if order_id not in self.pending_orders:
            return False
        
        order = self.pending_orders[order_id]
        result = await self.post_agent("executor", "/api/cancel-pending", {
            "ticket": order.ticket,
        })
        
        if result and result.get("status") == "PENDING_CANCELLED":
            order.status = "cancelled"
            del self.pending_orders[order_id]
            print(f"🗑️ Pending order cancelled: {order_id}")
            return True
        
        return False
    
    async def check_pending_orders(self):
        """Check all pending orders for expiration or fill."""
        now = datetime.utcnow()
        
        # Get MT5 pending orders
        mt5_orders = await self.fetch_agent("executor", "/api/pending-orders")
        mt5_tickets = set()
        if mt5_orders:
            for order in mt5_orders.get("pending_orders", []):
                mt5_tickets.add(order.get("ticket"))
        
        for order_id, order in list(self.pending_orders.items()):
            # Check expiration
            age_hours = (now - order.created_at).total_seconds() / 3600
            if age_hours >= order.expiration_hours:
                print(f"⏰ Pending order expired: {order_id} (age: {age_hours:.1f}h)")
                await self.cancel_pending_order(order_id)
                continue
            
            # Check if filled (no longer in MT5 pending orders)
            if order.ticket and order.ticket not in mt5_tickets:
                # Check if position exists (order was filled)
                positions = await self.fetch_agent("executor", "/api/positions")
                filled = False
                if positions:
                    for pos in positions.get("positions", []):
                        if pos.get("symbol", "").replace(".s", "") == order.symbol.replace(".s", ""):
                            # Order was likely filled
                            order.status = "filled"
                            del self.pending_orders[order_id]
                            print(f"✅ Pending order FILLED: {order_id}")
                            filled = True
                            break
                
                if not filled:
                    # Order disappeared without fill - expired or cancelled externally
                    order.status = "expired"
                    del self.pending_orders[order_id]
                    print(f"❓ Pending order removed externally: {order_id}")
    
    async def sync_pending_orders_from_mt5(self):
        """Sync pending orders from MT5 to internal tracking."""
        mt5_orders = await self.fetch_agent("executor", "/api/pending-orders")
        if not mt5_orders:
            return
        
        for order in mt5_orders.get("pending_orders", []):
            ticket = order.get("ticket")
            # Check if we're already tracking this order
            tracking = False
            for pending in self.pending_orders.values():
                if pending.ticket == ticket:
                    tracking = True
                    break
            
            if not tracking:
                # New order from MT5 we don't know about - start tracking
                order_id = f"MT5-{ticket}"
                self.pending_orders[order_id] = PendingOrder(
                    order_id=order_id,
                    ticket=ticket,
                    symbol=order.get("symbol", ""),
                    direction=order.get("direction", ""),
                    entry_price=order.get("entry_price", 0),
                    lots=order.get("volume", 0),
                    stop_loss=order.get("sl", 0),
                    take_profit=order.get("tp", 0),
                    created_at=datetime.utcnow(),  # Approximate
                    expiration_hours=24,  # Default
                    status="pending",
                )
    
    # ═══════════════════════════════════════════════════════════════
    # STAGE 1: DATA REFRESH
    # ═══════════════════════════════════════════════════════════════
    
    async def stage_data_refresh(self, symbols: List[str]) -> Dict[str, dict]:
        """Refresh market data for all symbols."""
        results = {}
        
        for symbol in symbols:
            data = await self.fetch_agent("curator", f"/api/snapshot/symbol/{symbol}")
            quality = await self.fetch_agent("curator", f"/api/quality/{symbol}")
            
            results[symbol] = {
                "data": data,
                "quality": quality.get("overall", 0) if quality else 0,
                "tradeable": quality.get("tradeable", False) if quality else False,
            }
            
            self.log_stage(LifecycleStage.DATA_REFRESH, symbol, {
                "quality": results[symbol]["quality"],
                "tradeable": results[symbol]["tradeable"],
            })
        
        return results
    
    # ═══════════════════════════════════════════════════════════════
    # STAGE 2: REGIME CLASSIFICATION
    # ═══════════════════════════════════════════════════════════════
    
    async def stage_regime_classification(self, symbols: List[str]) -> Dict[str, dict]:
        """Classify market regime for each symbol."""
        results = {}
        
        for symbol in symbols:
            regime = await self.fetch_agent("compass", f"/api/regime/{symbol}")
            
            if regime:
                results[symbol] = {
                    "regime": regime.get("regime", "unknown"),
                    "confidence": regime.get("confidence", 0),
                    "transition_prob": regime.get("transition_probability", 0.5),
                    "compatible_strategies": regime.get("strategy_families", []),
                    "risk_multiplier": regime.get("risk_multiplier", 1.0),
                }
            else:
                results[symbol] = {"regime": "unknown", "confidence": 0}
            
            self.log_stage(LifecycleStage.REGIME_CLASSIFICATION, symbol, results[symbol])
        
        return results
    
    # ═══════════════════════════════════════════════════════════════
    # STAGE 3: MULTI-AGENT ANALYSIS
    # ═══════════════════════════════════════════════════════════════
    
    async def stage_multi_agent_analysis(self, symbol: str) -> dict:
        """Gather analysis from all specialist agents."""
        analysis = {}
        
        # Technical (Atlas Jr.)
        technical = await self.fetch_agent("atlas", f"/api/analysis/{symbol}")
        analysis["technical"] = technical or {}
        
        # Structure (Architect)
        structure = await self.fetch_agent("architect", f"/api/structure/{symbol}")
        analysis["structure"] = structure or {}
        
        # Macro (Oracle) - uses /api/pair not /api/outlook
        macro = await self.fetch_agent("oracle", f"/api/pair/{symbol}")
        analysis["macro"] = macro or {}
        
        # Sentiment (Pulse)
        sentiment = await self.fetch_agent("pulse", f"/api/sentiment/{symbol}")
        analysis["sentiment"] = sentiment or {}
        
        # Event Risk (Sentinel)
        events = await self.fetch_agent("sentinel", f"/api/risk/{symbol}")
        analysis["events"] = events or {}
        
        self.log_stage(LifecycleStage.MULTI_AGENT_ANALYSIS, symbol, {
            "agents_responded": len([a for a in analysis.values() if a]),
        })
        
        return analysis
    
    # ═══════════════════════════════════════════════════════════════
    # STAGE 4: SETUP GENERATION
    # ═══════════════════════════════════════════════════════════════
    
    async def stage_setup_generation(self, symbol: str, regime: dict, analysis: dict) -> Optional[TradeSetup]:
        """Request setup generation from Tactician."""
        # Use GET /api/setups/{symbol} endpoint
        result = await self.fetch_agent("tactician", f"/api/setups/{symbol}")
        
        if result and result.get("setups"):
            setups = result["setups"]
            qualified_setups = []
            
            # Collect ALL qualified setups first
            for setup_data in setups:
                tactician_score = setup_data.get("score", 0)
                qualified = setup_data.get("qualified", False)
                
                # Log ALL setups for debugging
                print(f"   [{symbol}] Strategy: {setup_data.get('name', 'Unknown')}, Score: {tactician_score}, Qualified: {qualified}, Direction: {setup_data.get('direction', '?')}")
                
                # Allow setups with score >= 55 if qualified (lowered from 70)
                # The real decision is made by confluence score later
                if tactician_score < 55:
                    continue
                
                if not qualified:
                    continue
                
                qualified_setups.append(setup_data)
            
            # If we have qualified setups, pick the one with the HIGHEST CONFLUENCE score
            # (not just the first one by Tactician score)
            best_setup = None
            best_confluence = 0
            
            for setup_data in qualified_setups:
                direction = setup_data.get("direction", "long")
                # Normalize direction
                if direction in ["bearish", "short", "sell"]:
                    direction = "short"
                else:
                    direction = "long"
                
                # Get confluence score for this direction
                confluence_score, _ = await self.get_confluence_score(symbol, direction)
                
                print(f"   [{symbol}] Checking {setup_data.get('name')}: Tactician={setup_data.get('score')}, Confluence({direction})={confluence_score}")
                
                if confluence_score > best_confluence:
                    best_confluence = confluence_score
                    best_setup = setup_data
            
            if best_setup:
                setup_data = best_setup
                targets = setup_data.get("targets", [])
                direction = setup_data.get("direction", "long")
                # Normalize direction
                if direction in ["bearish", "short", "sell"]:
                    direction = "short"
                else:
                    direction = "long"
                
                print(f"   [{symbol}] 🎯 Selected best setup: {setup_data.get('name')}, Direction: {direction}, Confluence: {best_confluence}")
                
                setup = TradeSetup(
                    setup_id=f"SETUP-{symbol}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                    symbol=symbol,
                    direction=direction,
                    template=setup_data.get("template", "generic"),
                    template_version="1.0",
                    entry_price=setup_data.get("entry", 0),
                    entry_trigger=setup_data.get("direction_reason", ""),
                    entry_type=setup_data.get("entry_type", "market"),
                    stop_loss=setup_data.get("stop", 0),
                    take_profit_1=targets[0] if targets else 0,
                    take_profit_2=targets[1] if len(targets) > 1 else None,
                    why_here=f"Strategy: {setup_data.get('name', 'Unknown')}",
                    why_now=f"Score: {setup_data.get('score', 0)}/100",
                    why_direction=setup_data.get("direction_reason", ""),
                    invalidation=f"Stop at {setup_data.get('stop', 0)}",
                    confidence=setup_data.get("score", 0),
                )
                
                self.pending_setups[setup.setup_id] = setup
                self.log_stage(LifecycleStage.SETUP_GENERATION, symbol, {
                    "setup_id": setup.setup_id,
                    "template": setup.template,
                    "confidence": setup.confidence,
                    "direction": setup.direction,
                    "entry": setup.entry_price,
                    "stop": setup.stop_loss,
                })
                
                return setup
        
        return None
    
    # ═══════════════════════════════════════════════════════════════
    # STAGE 5: RISK SCREENING
    # ═══════════════════════════════════════════════════════════════
    
    async def stage_risk_screening(self, setup: TradeSetup) -> Tuple[bool, dict]:
        """Screen setup through Guardian."""
        # Guardian uses /api/evaluate with 'entry' and 'stop' field names
        result = await self.post_agent("guardian", "/api/evaluate", {
            "symbol": setup.symbol,
            "direction": setup.direction,
            "entry": setup.entry_price,
            "stop": setup.stop_loss,
            "lot_size": 0.1,  # Initial estimate, Guardian will size properly
        })
        
        if result:
            approved = result.get("approved", False)
            sizing = result.get("sizing", {})
            screening = {
                "approved": approved,
                "reason": result.get("reason", ""),
                "position_size": sizing.get("lot_size", 0),
                "risk_pct": sizing.get("risk_pct", 0),
                "risk_amount": sizing.get("risk_amount", 0),
                "checks": result.get("checks", []),
                "risk_mode": result.get("current_state", {}).get("risk_mode", "normal"),
            }
        else:
            approved = False
            screening = {"approved": False, "reason": "Guardian unavailable"}
        
        self.log_stage(LifecycleStage.RISK_SCREENING, setup.symbol, screening)
        return approved, screening
    
    # ═══════════════════════════════════════════════════════════════
    # STAGE 6: PORTFOLIO SCREENING
    # ═══════════════════════════════════════════════════════════════
    
    async def stage_portfolio_screening(self, setup: TradeSetup) -> Tuple[bool, dict]:
        """Screen setup through Balancer."""
        # Use /api/evaluate endpoint (not /api/check)
        result = await self.post_agent("balancer", "/api/evaluate", {
            "symbol": setup.symbol,
            "direction": setup.direction,
            "size": 1.0,  # Normalized
        })
        
        if result:
            exposure_ok = result.get("exposure_score", 0) < 80
            screening = {
                "approved": exposure_ok,
                "exposure_score": result.get("exposure_score", 0),
                "currency_exposures": result.get("currency_exposures", {}),
                "warnings": result.get("warnings", []),
            }
        else:
            exposure_ok = True  # Default to pass if unavailable
            screening = {"approved": True, "exposure_score": 0, "warnings": ["Balancer unavailable"]}
        
        self.log_stage(LifecycleStage.PORTFOLIO_SCREENING, setup.symbol, screening)
        return exposure_ok, screening
    
    # ═══════════════════════════════════════════════════════════════
    # STAGE 7: EXECUTION FEASIBILITY SCREENING
    # ═══════════════════════════════════════════════════════════════
    
    async def stage_execution_screening(self, setup: TradeSetup) -> Tuple[bool, dict]:
        """Screen execution feasibility through Executor."""
        result = await self.fetch_agent("executor", "/api/status")
        spread = await self.fetch_agent("curator", f"/api/snapshot/spread/{setup.symbol}")
        
        screening = {
            "approved": True,
            "bridge_status": "unknown",
            "spread_ok": True,
            "liquidity_ok": True,
        }
        
        if result:
            screening["bridge_status"] = result.get("bridge_status", "unknown")
            if result.get("bridge_status") not in ["READY", "UNKNOWN"]:
                screening["approved"] = False
                screening["block_reason"] = "Bridge not ready"
        
        if spread:
            current_spread = spread.get("spread_pips", 0)
            max_spread = 2.5 if "JPY" not in setup.symbol else 4.0
            if current_spread > max_spread:
                screening["approved"] = False
                screening["spread_ok"] = False
                screening["spread_pips"] = current_spread
        
        self.log_stage(LifecycleStage.EXECUTION_SCREENING, setup.symbol, screening)
        return screening["approved"], screening
    
    # ═══════════════════════════════════════════════════════════════
    # STAGE 8: TRADE DECISION
    # ═══════════════════════════════════════════════════════════════
    
    async def get_confluence_score(self, symbol: str, direction: str) -> Tuple[int, dict]:
        """
        Get confluence score from the orchestrator's API.
        
        This uses the SAME calculation as the dashboard, ensuring consistency.
        
        Rule: Score ≥75 = EXECUTE, 60-74 = WATCHLIST, <60 = NO_TRADE
        """
        # Call the orchestrator's own confluence endpoint
        # The orchestrator runs on port 3020
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"http://localhost:3020/api/confluence/{symbol}",
                    params={"direction": direction},
                    timeout=10.0
                )
                if resp.status_code == 200:
                    data = resp.json()
                    score = data.get("confluence_score", 0)
                    breakdown = data.get("score_breakdown", {})
                    # Simplify breakdown for logging
                    simple_breakdown = {k: v.get("score", 0) for k, v in breakdown.items()}
                    
                    # Diagnostic: log component scores for debugging score discrepancies
                    print(f"   [{symbol}] 🔍 Confluence breakdown: {simple_breakdown}")
                    
                    return score, simple_breakdown
        except Exception as e:
            print(f"[Lifecycle] Confluence fetch error: {e}")
        
        # Fallback: return 0 if we can't get the score
        return 0, {}
    
    def _record_score_history(self, symbol: str, score: int, breakdown: dict, 
                               direction: str, strategy: str, decision: str):
        """Record confluence score to history tracker."""
        try:
            from score_history import get_tracker
            tracker = get_tracker()
            tracker.record_score(
                symbol=symbol,
                total_score=score,
                breakdown=breakdown,
                direction=direction,
                strategy=strategy,
                decision=decision,
            )
        except Exception as e:
            # Don't let history tracking break the main flow
            print(f"[Lifecycle] Score history error (non-fatal): {e}")
    
    async def stage_trade_decision(self, setup: TradeSetup, risk: dict, portfolio: dict, execution: dict, analysis: dict = None) -> Tuple[str, dict]:
        """Make final trade decision based on CONFLUENCE SCORE (not Tactician's score)."""
        decision = "NO_TRADE"
        reasons = []
        
        # Get the REAL confluence score from orchestrator API (same as dashboard)
        confluence_score, score_breakdown = await self.get_confluence_score(
            setup.symbol, 
            setup.direction
        )
        
        # Check all screenings and collect reasons
        screening_failed = False
        
        if not risk.get("approved"):
            reasons.append(f"Guardian: {risk.get('reason', 'denied')}")
            screening_failed = True
        
        if not portfolio.get("approved"):
            reasons.append("Portfolio: exposure too high")
            screening_failed = True
        
        if not execution.get("approved"):
            reasons.append(f"Executor: {execution.get('block_reason', 'denied')}")
            screening_failed = True
        
        # Make decision based on CONFLUENCE SCORE
        print(f"   [{setup.symbol}] 📊 Confluence: {confluence_score}/100, Tactician: {setup.confidence}/100")
        
        # Get thresholds from CONFIG (can be changed via Nexus settings)
        # Fetch from orchestrator's config endpoint
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get("http://localhost:3020/api/config", timeout=5.0)
                if resp.status_code == 200:
                    config = resp.json()
                    thresholds = config.get("decision_thresholds", {})
                    EXECUTE_THRESHOLD = thresholds.get("execute", 75)
                    WATCHLIST_THRESHOLD = thresholds.get("watchlist", 60)
                else:
                    EXECUTE_THRESHOLD = 75
                    WATCHLIST_THRESHOLD = 60
        except:
            EXECUTE_THRESHOLD = 75
            WATCHLIST_THRESHOLD = 60
        
        # Determine decision type based on score
        score_decision = "NO_TRADE"
        if confluence_score >= EXECUTE_THRESHOLD:
            score_decision = "BUY" if setup.direction == "long" else "SELL"
        elif confluence_score >= WATCHLIST_THRESHOLD:
            score_decision = "WATCHLIST"
        
        # If screenings passed AND score is high enough, execute
        if not screening_failed and score_decision in ["BUY", "SELL"]:
            decision = score_decision
            print(f"   [{setup.symbol}] ✅ APPROVED: {decision} (score={confluence_score})")
        elif not screening_failed and score_decision == "WATCHLIST":
            decision = "WATCHLIST"
            reasons.append(f"Watchlist range ({confluence_score}/100)")
            print(f"   [{setup.symbol}] 👀 WATCHLIST: {confluence_score}/100")
        elif screening_failed and score_decision in ["BUY", "SELL"]:
            # HIGH CONFLUENCE BUT SCREENING BLOCKED - this is critical to log!
            decision = "BLOCKED"
            print(f"   [{setup.symbol}] ⚠️ BLOCKED despite high score ({confluence_score}): {', '.join(reasons)}")
        else:
            if confluence_score < 60:
                reasons.append(f"Confluence too low ({confluence_score}/100)")
            print(f"   [{setup.symbol}] ❌ NO_TRADE: {confluence_score}/100 - {', '.join(reasons)}")
        
        result = {
            "decision": decision,
            "setup_id": setup.setup_id,
            "confluence_score": confluence_score,  # THE REAL SCORE
            "tactician_score": setup.confidence,   # Tactician's score (for reference)
            "score_breakdown": score_breakdown,
            "reasons": reasons,
            "position_size": risk.get("position_size", 0),
            "risk_pct": risk.get("risk_pct", 0),
        }
        
        # Record score to history - use accurate decision type
        if decision in ["BUY", "SELL"]:
            decision_type = "execute"
        elif decision == "BLOCKED" and confluence_score >= 75:
            decision_type = "blocked_high_score"  # New! Shows score was high but blocked
        elif decision == "WATCHLIST":
            decision_type = "watchlist"
        else:
            decision_type = "blocked"
        
        self._record_score_history(
            symbol=setup.symbol,
            score=confluence_score,
            breakdown=score_breakdown,
            direction=setup.direction,
            strategy=setup.template,
            decision=decision_type,
        )
        
        # Add to watchlist if decision is WATCHLIST
        if decision == "WATCHLIST" and self.watchlist_callback:
            self.watchlist_callback(
                symbol=setup.symbol,
                direction=setup.direction,
                score=confluence_score,
                setup_id=setup.setup_id
            )
        
        self.log_stage(LifecycleStage.TRADE_DECISION, setup.symbol, result)
        return decision, result
    
    # ═══════════════════════════════════════════════════════════════
    # STAGE 9: ORDER ROUTING
    # ═══════════════════════════════════════════════════════════════
    
    async def stage_order_routing(self, setup: TradeSetup, decision: dict) -> Optional[ActiveTrade]:
        """Route approved trade to execution."""
        if decision["decision"] not in ["BUY", "SELL"]:
            return None
        
        # Check if this is a limit order
        entry_type = getattr(setup, 'entry_type', 'market')
        
        if entry_type == "limit":
            # Place pending (limit) order
            direction = "buy_limit" if setup.direction == "long" else "sell_limit"
            pending = await self.place_pending_order(
                symbol=setup.symbol,
                direction=direction,
                lots=decision.get("position_size", 0.01),
                entry_price=setup.entry_price,
                stop_loss=setup.stop_loss,
                take_profit=setup.take_profit_1 or 0,
                expiration_hours=self.pending_order_expiration_hours,
            )
            
            if pending:
                # Return None for now - trade will be created when order fills
                print(f"📋 LIMIT order placed: {setup.symbol} {direction} @ {setup.entry_price}")
                self.log_stage(LifecycleStage.ORDER_ROUTING, setup.symbol, {
                    "type": "LIMIT",
                    "order_id": pending.order_id,
                    "entry_price": setup.entry_price,
                })
                return None
            
            return None
        
        # Execute market order via Executor
        execution_payload = {
            "symbol": setup.symbol,
            "direction": setup.direction,  # "long" or "short"
            "entry_price": setup.entry_price,
            "stop_loss": setup.stop_loss,
            "take_profit": setup.take_profit_1,
            "lot_size": decision.get("position_size", 0.01),
        }
        print(f"[Lifecycle] 🚀 EXECUTING TRADE: {setup.symbol} {setup.direction.upper()}")
        print(f"[Lifecycle]    Payload: {execution_payload}")
        
        # Use longer timeout for execution (MT5 bridge waits up to 30s)
        result = await self.post_agent("executor", "/api/execute", execution_payload, timeout=45.0)
        
        # Log the full response for debugging
        print(f"[Lifecycle]    Executor Response: {result}")
        
        if result and result.get("status") in ["EXECUTED", "filled"]:
            trade = ActiveTrade(
                trade_id=result.get("receipt_id", f"TRD-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"),
                setup=setup,
                status=TradeStatus.ACTIVE,
                entry_price_actual=result.get("fill_price", setup.entry_price),
                entry_time=datetime.utcnow(),
                slippage_pips=result.get("slippage_pips", 0),
                position_size=decision.get("position_size", 0.01),
                broker_ticket=result.get("ticket", ""),
            )
            
            self.active_trades[trade.trade_id] = trade
            
            # Update score history to mark as actually executed
            self._record_score_history(
                symbol=setup.symbol,
                score=decision.get("confluence_score", 0),
                breakdown=decision.get("score_breakdown", {}),
                direction=setup.direction,
                strategy=setup.template,
                decision="executed",  # Actually executed, not just approved
            )
            
            # Log to Chronicle v2.0 with full context for chart generation and journaling
            await self.post_agent("chronicle", "/api/trade/execute", {
                "trade_id": trade.trade_id,
                "symbol": setup.symbol,
                "direction": setup.direction,
                "entry_price": trade.entry_price_actual,
                "stop_loss": setup.stop_loss,
                "take_profit": setup.take_profit_1 or 0,
                "lot_size": decision.get("position_size", 0.01),
                
                # Strategy context
                "strategy": setup.template,
                "strategy_score": setup.confidence or 0,
                
                # Confluence at entry
                "confluence_score": decision.get("confluence_score", 0),
                "confluence_breakdown": decision.get("score_breakdown", {}),
                
                # Trade thesis (why we took this trade)
                "thesis": {
                    "why_here": setup.why_here or "",
                    "why_now": setup.why_now or "",
                    "why_direction": setup.why_direction or "",
                    "invalidation": setup.invalidation or "",
                },
                
                # Agent verdicts at entry
                "agent_verdicts": decision.get("agent_verdicts", {}),
                
                # Execution details
                "broker_ticket": int(trade.broker_ticket) if trade.broker_ticket else 0,
                "entry_type": getattr(setup, 'entry_type', 'market'),
                "timeframe": "H1",
            })
            
            print(f"[Lifecycle] Trade journaled to Chronicle: {trade.trade_id}")
            
            self.log_stage(LifecycleStage.ORDER_ROUTING, setup.symbol, {
                "trade_id": trade.trade_id,
                "fill_price": trade.entry_price_actual,
                "slippage": trade.slippage_pips,
            })
            
            return trade
        
        # EXECUTION FAILED - Log why!
        error_reason = "No response from Executor"
        if result:
            error_reason = result.get("reason") or result.get("error") or f"Status: {result.get('status', 'unknown')}"
        
        print(f"[Lifecycle] ❌ EXECUTION FAILED for {setup.symbol}: {error_reason}")
        print(f"[Lifecycle]    Full response: {result}")
        
        # Record the failed execution attempt in score history
        self._record_score_history(
            symbol=setup.symbol,
            score=decision.get("confluence_score", 0),
            breakdown=decision.get("score_breakdown", {}),
            direction=setup.direction,
            strategy=setup.template,
            decision="exec_failed",  # Mark as execution failed, not just approved
        )
        
        self.log_stage(LifecycleStage.ORDER_ROUTING, setup.symbol, {
            "status": "FAILED",
            "reason": error_reason,
            "executor_response": result,
        })
        
        return None
    
    # ═══════════════════════════════════════════════════════════════
    # STAGE 10: ACTIVE MONITORING
    # ═══════════════════════════════════════════════════════════════
    
    async def stage_active_monitoring(self, trade: ActiveTrade) -> dict:
        """Monitor an active trade."""
        # Get current price
        price_data = await self.fetch_agent("curator", f"/api/snapshot/symbol/{trade.setup.symbol}")
        
        if price_data:
            is_long = trade.setup.direction.lower() in ["long", "buy", "bullish"]
            current_price = price_data.get("bid", 0) if is_long else price_data.get("ask", 0)
            trade.current_price = current_price
            
            # JPY pairs have 2 decimal places, others have 4
            pip_multiplier = 100 if "JPY" in trade.setup.symbol else 10000
            
            # Calculate P&L
            if is_long:
                pnl_pips = (current_price - trade.entry_price_actual) * pip_multiplier
            else:
                pnl_pips = (trade.entry_price_actual - current_price) * pip_multiplier
            
            trade.current_pnl_pips = pnl_pips
            
            # Calculate R
            risk_pips = abs(trade.entry_price_actual - trade.setup.stop_loss) * pip_multiplier
            trade.current_pnl_r = pnl_pips / risk_pips if risk_pips > 0 else 0
            
            # Track excursions
            if pnl_pips > trade.max_favorable_excursion:
                trade.max_favorable_excursion = pnl_pips
            if pnl_pips < -trade.max_adverse_excursion:
                trade.max_adverse_excursion = abs(pnl_pips)
            
            trade.bars_in_trade += 1
        
        # Check for thesis invalidation
        analysis = await self.stage_multi_agent_analysis(trade.setup.symbol)
        
        monitoring_result = {
            "trade_id": trade.trade_id,
            "current_price": trade.current_price,
            "pnl_pips": trade.current_pnl_pips,
            "pnl_r": trade.current_pnl_r,
            "bars": trade.bars_in_trade,
            "mfe": trade.max_favorable_excursion,
            "mae": trade.max_adverse_excursion,
        }
        
        self.log_stage(LifecycleStage.ACTIVE_MONITORING, trade.setup.symbol, monitoring_result)
        return monitoring_result
    
    # ═══════════════════════════════════════════════════════════════
    # STAGE 11: EXIT MANAGEMENT
    # ═══════════════════════════════════════════════════════════════
    
    async def stage_exit_management(self, trade: ActiveTrade) -> Optional[ExitReason]:
        """Manage exits based on exit framework."""
        exit_reason = None
        framework = trade.setup.exit_framework
        
        # Check stop loss
        if trade.current_pnl_r <= -1.0:
            exit_reason = ExitReason.STOP_LOSS
        
        # Check TP1 - Partial close 50%
        elif not trade.tp1_hit and trade.current_pnl_r >= framework.tp1_r:
            trade.tp1_hit = True
            trade.tp1_exit_price = trade.current_price
            
            # Execute partial close (50%) - use longer timeout for MT5 bridge operations
            close_pct = framework.tp1_pct * 100  # 0.5 -> 50%
            partial_result = await self.post_agent("executor", "/api/partial-close", {
                "ticket": trade.broker_ticket,
                "close_percent": close_pct,
            }, timeout=35.0)  # MT5 bridge can take up to 30s
            self.log_stage(LifecycleStage.EXIT_MANAGEMENT, trade.setup.symbol, {
                "action": "PARTIAL_CLOSE_TP1",
                "percent": close_pct,
                "price": trade.current_price,
                "result": partial_result,
            })
            
            # Move stop to breakeven
            if not trade.stop_moved_to_be:
                trade.stop_moved_to_be = True
                be_price = trade.setup.entry_price
                modify_result = await self.post_agent("executor", "/api/modify-sl", {
                    "ticket": trade.broker_ticket,
                    "new_sl": be_price,
                    "new_tp": 0,  # No TP - we manage exits manually
                }, timeout=35.0)  # MT5 bridge can take up to 30s
                self.log_stage(LifecycleStage.EXIT_MANAGEMENT, trade.setup.symbol, {
                    "action": "MOVE_SL_TO_BE",
                    "new_sl": be_price,
                    "result": modify_result,
                })
        
        # Check TP2 - Partial close 60% of remaining (30% of original)
        elif trade.tp1_hit and not trade.tp2_hit and trade.current_pnl_r >= framework.tp2_r:
            trade.tp2_hit = True
            trade.tp2_exit_price = trade.current_price
            
            # Close 60% of what's left (which is ~30% of original) - use longer timeout for MT5
            close_pct = 60.0  # 60% of remaining after TP1
            partial_result = await self.post_agent("executor", "/api/partial-close", {
                "ticket": trade.broker_ticket,
                "close_percent": close_pct,
            }, timeout=35.0)  # MT5 bridge can take up to 30s
            self.log_stage(LifecycleStage.EXIT_MANAGEMENT, trade.setup.symbol, {
                "action": "PARTIAL_CLOSE_TP2",
                "percent": close_pct,
                "price": trade.current_price,
                "result": partial_result,
            })
        
        # Check time stop
        elif trade.bars_in_trade >= framework.time_stop_bars and trade.current_pnl_r < 1.0:
            exit_reason = ExitReason.TIME_STOP
        
        # Check event risk
        events = await self.fetch_agent("sentinel", f"/api/risk/{trade.setup.symbol}")
        if events and events.get("trading_mode") == "PAUSE":
            if trade.current_pnl_r < 1.0:
                exit_reason = ExitReason.EVENT_RISK
        
        # Check trailing stop (if in profit)
        if trade.current_pnl_r >= 2.0 and framework.style == "atr_trailing":
            # ATR trailing logic would go here
            pass
        
        if exit_reason:
            trade.exit_reason = exit_reason
            trade.exit_price = trade.current_price
            trade.exit_time = datetime.utcnow()
            trade.status = TradeStatus.CLOSED
            
            # Close via executor - use longer timeout for MT5 bridge
            await self.post_agent("executor", "/api/close", {
                "ticket": trade.broker_ticket,
                "reason": exit_reason.value,
            }, timeout=35.0)  # MT5 bridge can take up to 30s
            
            # Log to chronicle - use correct field names
            await self.post_agent("chronicle", "/api/trade/close", {
                "trade_id": trade.setup.setup_id,
                "exit_price": trade.exit_price,
                "exit_reason": exit_reason.value,
            })
            
            self.log_stage(LifecycleStage.EXIT_MANAGEMENT, trade.setup.symbol, {
                "trade_id": trade.trade_id,
                "exit_reason": exit_reason.value,
                "exit_price": trade.exit_price,
                "final_pnl_r": trade.current_pnl_r,
            })
            
            # Move to completed
            self.completed_trades.append(trade)
            del self.active_trades[trade.trade_id]
        
        return exit_reason
    
    # ═══════════════════════════════════════════════════════════════
    # STAGE 12: POST-TRADE REVIEW
    # ═══════════════════════════════════════════════════════════════
    
    async def stage_post_trade_review(self, trade: ActiveTrade) -> dict:
        """Generate post-trade review."""
        review = {
            "trade_id": trade.trade_id,
            "symbol": trade.setup.symbol,
            "template": trade.setup.template,
            "direction": trade.setup.direction,
            "entry": trade.entry_price_actual,
            "exit": trade.exit_price,
            "pnl_r": trade.current_pnl_r,
            "pnl_pips": trade.current_pnl_pips,
            "exit_reason": trade.exit_reason.value if trade.exit_reason else "unknown",
            "bars_held": trade.bars_in_trade,
            "mfe": trade.max_favorable_excursion,
            "mae": trade.max_adverse_excursion,
            "slippage": trade.slippage_pips,
            "thesis_valid": trade.exit_reason != ExitReason.THESIS_INVALIDATION,
        }
        
        # Calculate efficiency
        if trade.max_favorable_excursion > 0:
            review["exit_efficiency"] = trade.current_pnl_pips / trade.max_favorable_excursion
        
        # Did we give back too much?
        if trade.current_pnl_r > 0 and trade.max_favorable_excursion > trade.current_pnl_pips * 1.5:
            review["gave_back_warning"] = True
        
        trade.reviewed = True
        
        self.log_stage(LifecycleStage.POST_TRADE_REVIEW, trade.setup.symbol, review)
        return review
    
    # ═══════════════════════════════════════════════════════════════
    # STAGE 13: PERFORMANCE ATTRIBUTION
    # ═══════════════════════════════════════════════════════════════
    
    async def stage_performance_attribution(self, trade: ActiveTrade) -> dict:
        """Attribute performance to factors."""
        attribution = {
            "trade_id": trade.trade_id,
            "template": trade.setup.template,
            "result_r": trade.current_pnl_r,
            "factors": {},
        }
        
        # Attribute by category
        if trade.current_pnl_r > 0:
            attribution["factors"]["template_selection"] = "positive"
            attribution["factors"]["entry_timing"] = "good" if trade.max_adverse_excursion < 10 else "could_improve"
            attribution["factors"]["exit_timing"] = "optimal" if trade.current_pnl_pips > trade.max_favorable_excursion * 0.8 else "suboptimal"
        else:
            # Loss attribution
            if trade.exit_reason == ExitReason.STOP_LOSS:
                attribution["factors"]["stop_placement"] = "review_needed"
            elif trade.exit_reason == ExitReason.THESIS_INVALIDATION:
                attribution["factors"]["thesis_quality"] = "incorrect"
            elif trade.exit_reason == ExitReason.TIME_STOP:
                attribution["factors"]["timing"] = "too_early_or_wrong_setup"
        
        # Send to Insight
        await self.post_agent("insight", "/api/attribution", attribution)
        
        self.log_stage(LifecycleStage.PERFORMANCE_ATTRIBUTION, trade.setup.symbol, attribution)
        return attribution
    
    # ═══════════════════════════════════════════════════════════════
    # STAGE 14: STRATEGY IMPROVEMENT RECOMMENDATIONS
    # ═══════════════════════════════════════════════════════════════
    
    async def stage_strategy_improvement(self, trades: List[ActiveTrade]) -> dict:
        """Generate strategy improvement recommendations."""
        if not trades:
            return {"recommendations": []}
        
        # Group by template
        by_template = {}
        for trade in trades:
            template = trade.setup.template
            if template not in by_template:
                by_template[template] = []
            by_template[template].append(trade)
        
        recommendations = []
        
        for template, template_trades in by_template.items():
            wins = [t for t in template_trades if t.current_pnl_r > 0]
            losses = [t for t in template_trades if t.current_pnl_r <= 0]
            
            win_rate = len(wins) / len(template_trades) if template_trades else 0
            avg_r = sum(t.current_pnl_r for t in template_trades) / len(template_trades) if template_trades else 0
            
            # Generate recommendations
            if win_rate < 0.45 and len(template_trades) >= 10:
                recommendations.append({
                    "template": template,
                    "issue": "low_win_rate",
                    "value": win_rate,
                    "suggestion": "Review entry criteria - may be too loose",
                })
            
            avg_mae = sum(t.max_adverse_excursion for t in template_trades) / len(template_trades) if template_trades else 0
            if avg_mae > 20:
                recommendations.append({
                    "template": template,
                    "issue": "high_mae",
                    "value": avg_mae,
                    "suggestion": "Entry timing may be early - wait for better trigger",
                })
            
            # Check exit efficiency
            efficiencies = []
            for t in template_trades:
                if t.max_favorable_excursion > 0:
                    efficiencies.append(t.current_pnl_pips / t.max_favorable_excursion)
            
            if efficiencies:
                avg_efficiency = sum(efficiencies) / len(efficiencies)
                if avg_efficiency < 0.5:
                    recommendations.append({
                        "template": template,
                        "issue": "poor_exit_efficiency",
                        "value": avg_efficiency,
                        "suggestion": "Giving back too much profit - review exit framework",
                    })
        
        # Submit to Arbiter for consideration
        if recommendations:
            await self.post_agent("arbiter", "/api/recommendations", {
                "recommendations": recommendations,
                "trade_count": len(trades),
            })
        
        result = {"recommendations": recommendations}
        self.log_stage(LifecycleStage.STRATEGY_IMPROVEMENT, "system", result)
        return result
    
    # ═══════════════════════════════════════════════════════════════
    # FULL LIFECYCLE RUNNER
    # ═══════════════════════════════════════════════════════════════
    
    async def run_full_cycle(self, symbols: List[str]) -> dict:
        """Run complete lifecycle for a list of symbols."""
        cycle_result = {
            "timestamp": datetime.utcnow().isoformat(),
            "symbols_scanned": len(symbols),
            "setups_generated": 0,
            "trades_approved": 0,
            "trades_rejected": 0,
        }
        
        # Stage 1: Data refresh
        data = await self.stage_data_refresh(symbols)
        tradeable = [s for s, d in data.items() if d.get("tradeable")]
        
        # Stage 2: Regime classification
        regimes = await self.stage_regime_classification(tradeable)
        
        for symbol in tradeable:
            regime = regimes.get(symbol, {})
            
            # Stage 3: Multi-agent analysis
            analysis = await self.stage_multi_agent_analysis(symbol)
            
            # Include regime in analysis for confluence scoring
            analysis["regime"] = regime
            
            # Stage 4: Setup generation
            setup = await self.stage_setup_generation(symbol, regime, analysis)
            
            if setup:
                cycle_result["setups_generated"] += 1
                print(f"   [{symbol}] 🎯 Setup generated: {setup.template}, Direction: {setup.direction}")
                
                # Stage 5: Risk screening
                risk_ok, risk_result = await self.stage_risk_screening(setup)
                if risk_ok:
                    print(f"   [{symbol}] Guardian: ✓ Approved")
                else:
                    # Show failed checks from Guardian
                    failed_checks = [c.get("message") for c in risk_result.get("checks", []) if not c.get("passed")]
                    print(f"   [{symbol}] Guardian: ✗ {risk_result.get('reason', 'denied')}")
                    if failed_checks:
                        print(f"   [{symbol}]    Failed checks: {', '.join(failed_checks)}")
                
                # Stage 6: Portfolio screening
                portfolio_ok, portfolio_result = await self.stage_portfolio_screening(setup)
                print(f"   [{symbol}] Balancer: {'✓' if portfolio_ok else '✗'} (exposure: {portfolio_result.get('exposure_score', 'N/A')})")
                
                # Stage 7: Execution screening
                exec_ok, exec_result = await self.stage_execution_screening(setup)
                print(f"   [{symbol}] Executor: {'✓' if exec_ok else '✗'} {exec_result.get('block_reason', 'OK')}")
                
                # Stage 8: Trade decision (pass analysis for CONFLUENCE scoring)
                decision, decision_result = await self.stage_trade_decision(
                    setup, risk_result, portfolio_result, exec_result, analysis
                )
                
                if decision in ["BUY", "SELL"]:
                    # Stage 9: Order routing
                    try:
                        print(f"   [{symbol}] 🚀 Calling order routing for {decision}...")
                        trade = await self.stage_order_routing(setup, decision_result)
                        if trade:
                            cycle_result["trades_approved"] += 1
                            print(f"   [{symbol}] ✅ Trade created: {trade.trade_id}")
                        else:
                            print(f"   [{symbol}] ❌ Order routing returned None")
                    except Exception as e:
                        print(f"   [{symbol}] ❌ Order routing EXCEPTION: {type(e).__name__}: {e}")
                        import traceback
                        traceback.print_exc()
                else:
                    cycle_result["trades_rejected"] += 1
                    print(f"   [{symbol}] Decision: {decision} - not executing")
            else:
                # No setup generated - still record score history for tracking
                # This helps visualize why a symbol isn't generating trades
                try:
                    # Get confluence score anyway for history tracking
                    score, breakdown = await self.get_confluence_score(symbol, "long")
                    self._record_score_history(
                        symbol=symbol,
                        score=score,
                        breakdown=breakdown,
                        direction="neutral",
                        strategy="none_qualified",
                        decision="no_setup",
                    )
                except Exception as e:
                    pass  # Don't let score history break the main flow
        
        # Monitor active trades (Stage 10-11)
        for trade_id, trade in list(self.active_trades.items()):
            await self.stage_active_monitoring(trade)
            await self.stage_exit_management(trade)
        
        # Review completed trades (Stage 12-13)
        for trade in self.completed_trades:
            if not trade.reviewed:
                await self.stage_post_trade_review(trade)
                await self.stage_performance_attribution(trade)
        
        # Stage 14: Strategy improvement (periodic)
        if len(self.completed_trades) >= 10:
            await self.stage_strategy_improvement(self.completed_trades[-50:])
        
        return cycle_result
    
    async def monitor_active_trades_loop(self):
        """Background loop to monitor active trades every 1 second."""
        print("🔄 Lifecycle monitor started (1s interval)")
        print("📊 Auto-scan enabled: every 5 minutes")
        
        pending_check_counter = 0  # Check pending orders every 10 seconds
        sync_counter = 0  # Sync with MT5 every 30 seconds
        scan_counter = 0  # Full lifecycle scan every 300 seconds (5 minutes)
        
        while True:
            try:
                # Full lifecycle scan every 5 minutes
                scan_counter += 1
                if scan_counter >= 300:
                    scan_counter = 0
                    print("📊 Running scheduled lifecycle scan...")
                    try:
                        # Default symbols to scan
                        symbols = ["EURUSD", "GBPUSD", "USDJPY", "GBPJPY", "USDCHF", "USDCAD", "EURAUD", "AUDNZD", "AUDUSD"]
                        result = await self.run_full_cycle(symbols)
                        print(f"📊 Scan complete: {result.get('setups_generated', 0)} setups, {result.get('trades_approved', 0)} approved")
                    except Exception as e:
                        print(f"📊 Scan error: {e}")
                
                # Sync with MT5 every 30 seconds
                sync_counter += 1
                if sync_counter >= 30:
                    sync_counter = 0
                    await self.sync_with_mt5()
                
                # Monitor active trades
                if self.active_trades:
                    # Get latest prices from Curator
                    prices = await self.fetch_agent("curator", "/api/market")
                    
                    if not prices:
                        print(f"⚠️ No price data from Curator - cannot update trade P&L")
                    
                    for trade_id, trade in list(self.active_trades.items()):
                        symbol = trade.setup.symbol.replace(".s", "").replace(".S", "").replace(".ecn", "").replace(".ECN", "")
                        
                        # Update current price
                        if prices and symbol in prices:
                            trade.current_price = prices[symbol].get("price", trade.current_price)
                            
                            # JPY pairs have 2 decimal places, others have 4
                            pip_multiplier = 100 if "JPY" in symbol else 10000
                            
                            # Calculate current P/L in R
                            if trade.setup.direction.lower() in ["long", "buy", "bullish"]:
                                pnl_pips = (trade.current_price - trade.setup.entry_price) * pip_multiplier
                            else:
                                pnl_pips = (trade.setup.entry_price - trade.current_price) * pip_multiplier
                            
                            risk_pips = abs(trade.setup.entry_price - trade.setup.stop_loss) * pip_multiplier
                            trade.current_pnl_r = pnl_pips / risk_pips if risk_pips > 0 else 0
                            trade.current_pnl_pips = pnl_pips
                            
                            # Log when at significant R levels
                            if trade.current_pnl_r >= 1.0 and not trade.tp1_hit:
                                print(f"   [{symbol}] 📈 {trade.current_pnl_r:.2f}R | Entry: {trade.setup.entry_price:.5f}, SL: {trade.setup.stop_loss:.5f}, Current: {trade.current_price:.5f}")
                                print(f"   [{symbol}] TP1 threshold: {trade.setup.exit_framework.tp1_r}R | Direction: {trade.setup.direction}")
                        else:
                            if prices:
                                print(f"⚠️ No price data for {symbol} (have: {list(prices.keys())})")
                        
                        # Run exit management (checks TP1, TP2, SL)
                        await self.stage_exit_management(trade)
                        
                        # Remove closed trades
                        if trade.status == TradeStatus.CLOSED:
                            self.completed_trades.append(trade)
                            del self.active_trades[trade_id]
                            print(f"✅ Trade {trade_id} closed: {trade.exit_reason.value if trade.exit_reason else 'unknown'}")
                
                # Check pending orders every 10 seconds
                pending_check_counter += 1
                if pending_check_counter >= 10:
                    pending_check_counter = 0
                    if self.pending_orders:
                        await self.check_pending_orders()
                    # Also sync any new pending orders from MT5
                    await self.sync_pending_orders_from_mt5()
                
            except Exception as e:
                print(f"⚠️ Monitor loop error: {e}")
            
            await asyncio.sleep(1)  # Every 1 second
    
    def start_monitoring(self):
        """Start the background monitoring loop."""
        asyncio.create_task(self.monitor_active_trades_loop())
