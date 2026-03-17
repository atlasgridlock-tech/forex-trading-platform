"""
Journal Models - Trade journal entries and rejected trade records.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import String, Boolean, Text, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, generate_uuid


class TradeJournal(Base):
    """
    Comprehensive journal entry for every trade.
    Contains pre-trade thesis, execution details, and post-trade review.
    """
    __tablename__ = "trade_journal"
    
    journal_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        unique=True,
        nullable=False,
        default=generate_uuid
    )
    
    # Links
    plan_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("trade_plans.plan_id"),
        nullable=True
    )
    position_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("positions.position_id"),
        nullable=True
    )
    receipt_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("execution_receipts.receipt_id"),
        nullable=True
    )
    
    # Trade details
    symbol: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    direction: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    
    # Context
    strategy_family: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    regime: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    session: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    day_of_week: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    
    # Market context at time of trade
    macro_context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sentiment_context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    event_context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Decision
    entry_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    supporting_signals: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    conflicting_signals: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    confluence_score: Mapped[Optional[Decimal]] = mapped_column(nullable=True)
    score_breakdown: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    # Results
    result_r: Mapped[Optional[Decimal]] = mapped_column(nullable=True)
    result_pips: Mapped[Optional[Decimal]] = mapped_column(nullable=True)
    result_currency: Mapped[Optional[Decimal]] = mapped_column(nullable=True)
    exit_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    
    # Post-trade review
    pre_trade_expectation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    post_trade_reality: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    what_went_right: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    what_went_wrong: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    lessons: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    tags: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    # Quality assessment
    trade_quality_rating: Mapped[Optional[Decimal]] = mapped_column(nullable=True)
    thesis_correct: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    execution_good: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    exit_optimal: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    
    __table_args__ = (
        Index("ix_trade_journal_lookup", "symbol", text("created_at DESC")),
    )


class RejectedTrade(Base):
    """
    Record of rejected trade ideas.
    Understanding rejections is essential for system improvement.
    """
    __tablename__ = "rejected_trades"
    
    rejection_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        unique=True,
        nullable=False,
        default=generate_uuid
    )
    
    timestamp: Mapped[datetime] = mapped_column(nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    
    proposed_direction: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    proposed_strategy: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    confluence_score: Mapped[Optional[Decimal]] = mapped_column(nullable=True)
    
    rejection_reasons: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    agent_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    # Filled in later: would this trade have been profitable?
    would_have_been_profitable: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    
    __table_args__ = (
        Index("ix_rejected_trades_lookup", "symbol", text("timestamp DESC")),
    )
