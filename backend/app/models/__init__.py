"""
SQLAlchemy ORM Models
=====================
All database models for the forex trading platform.
"""
from app.models.base import Base, metadata, generate_uuid

# Market Data
from app.models.market_data import (
    MarketDataBar,
    MarketDataHealth,
    KeyLevel,
)

# Agent Outputs
from app.models.agent_output import (
    AgentOutput,
    RegimeHistory,
)

# Trades
from app.models.trade import (
    TradePlan,
    ExecutionReceipt,
    Position,
)

# Journal
from app.models.journal import (
    TradeJournal,
    RejectedTrade,
)

# Analytics
from app.models.analytics import (
    PerformanceSnapshot,
    EquityCurve,
)

# Governance
from app.models.governance import (
    StrategyVersion,
    ValidationReport,
)

# System
from app.models.system import (
    KillSwitch,
    Incident,
    SystemHealth,
    AuditLog,
)

__all__ = [
    # Base
    "Base",
    "metadata",
    "generate_uuid",
    # Market Data
    "MarketDataBar",
    "MarketDataHealth",
    "KeyLevel",
    # Agent Outputs
    "AgentOutput",
    "RegimeHistory",
    # Trades
    "TradePlan",
    "ExecutionReceipt",
    "Position",
    # Journal
    "TradeJournal",
    "RejectedTrade",
    # Analytics
    "PerformanceSnapshot",
    "EquityCurve",
    # Governance
    "StrategyVersion",
    "ValidationReport",
    # System
    "KillSwitch",
    "Incident",
    "SystemHealth",
    "AuditLog",
]
