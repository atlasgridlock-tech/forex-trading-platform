"""
Foundation tests - verify basic setup is correct.
"""
import pytest


def test_imports():
    """Verify all core imports work."""
    from app.config import settings
    from app.agents.base_agent import BaseAgent, AgentMessage, AgentHealthStatus
    from app.models import Base, metadata
    
    assert settings is not None
    assert BaseAgent is not None
    assert AgentMessage is not None
    assert Base is not None


def test_settings_defaults():
    """Verify settings have safe defaults."""
    from app.config import settings
    
    # CRITICAL: Verify safe defaults
    assert settings.trading.trading_mode == "paper", "Default must be paper trading"
    assert settings.trading.live_trading_enabled == False, "Live trading must be disabled by default"


def test_agent_message_creation():
    """Verify AgentMessage can be created."""
    from app.agents.base_agent import AgentMessage
    
    msg = AgentMessage(
        sender="test_agent",
        message_type="test",
        payload={"key": "value"},
        confidence=0.8,
        data_quality=0.9,
    )
    
    assert msg.sender == "test_agent"
    assert msg.confidence == 0.8
    assert msg.message_id is not None  # Auto-generated


def test_all_models_importable():
    """Verify all models can be imported."""
    from app.models import (
        MarketDataBar,
        MarketDataHealth,
        KeyLevel,
        AgentOutput,
        RegimeHistory,
        TradePlan,
        ExecutionReceipt,
        Position,
        TradeJournal,
        RejectedTrade,
        PerformanceSnapshot,
        EquityCurve,
        StrategyVersion,
        ValidationReport,
        KillSwitch,
        Incident,
        SystemHealth,
        AuditLog,
    )
    
    # Just verify imports don't crash
    assert MarketDataBar is not None
    assert TradePlan is not None
    assert KillSwitch is not None
