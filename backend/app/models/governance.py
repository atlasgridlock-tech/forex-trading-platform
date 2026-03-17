"""
Governance Models - Strategy versions and validation reports.
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB, TSTZRANGE
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, generate_uuid


class StrategyVersion(Base):
    """
    Version control for strategy parameters.
    No strategy can go live without proper versioning and validation.
    """
    __tablename__ = "strategy_versions"
    
    strategy_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(20), nullable=False)  # Semantic versioning
    
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False)
    
    # Status: draft -> testing -> validated -> promoted -> active -> retired
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    
    validation_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        nullable=True
    )
    
    changelog: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    promoted_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    retired_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)


class ValidationReport(Base):
    """
    Validation test results for strategy versions.
    Required before any strategy can be promoted to live.
    """
    __tablename__ = "validation_reports"
    
    validation_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        unique=True,
        nullable=False,
        default=generate_uuid
    )
    
    strategy_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    test_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)  # backtest, walkforward, monte_carlo
    
    # Date range covered by the test
    date_range_start: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    date_range_end: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    
    # Results
    metrics: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    passed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
