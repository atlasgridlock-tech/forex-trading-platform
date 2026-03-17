"""
Agent Output Models - Storage for all agent analysis results.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import String, Integer, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, generate_uuid


class AgentOutput(Base):
    """
    Storage for all agent outputs.
    Every agent produces typed messages that are stored here for auditability.
    """
    __tablename__ = "agent_outputs"
    
    message_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), 
        unique=True, 
        nullable=False,
        default=generate_uuid
    )
    correlation_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), 
        nullable=True,
        index=True
    )
    
    agent_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    symbol: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    timeframe: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    
    message_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    
    confidence: Mapped[Optional[Decimal]] = mapped_column(nullable=True)
    data_quality: Mapped[Optional[Decimal]] = mapped_column(nullable=True)
    
    warnings: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    errors: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    __table_args__ = (
        Index("ix_agent_outputs_lookup", "agent_name", "symbol", created_at.desc()),
        Index("ix_agent_outputs_gin_payload", "payload", postgresql_using="gin"),
    )


class RegimeHistory(Base):
    """
    Historical regime classifications for each symbol.
    Critical for understanding when strategies have edge.
    """
    __tablename__ = "regime_history"
    
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(5), nullable=False)
    
    regime: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[Optional[Decimal]] = mapped_column(nullable=True)
    risk_multiplier: Mapped[Optional[Decimal]] = mapped_column(nullable=True)
    
    detected_at: Mapped[datetime] = mapped_column(nullable=False, index=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    duration_bars: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    __table_args__ = (
        Index("ix_regime_history_lookup", "symbol", detected_at.desc()),
    )
