"""
Analytics Models - Performance snapshots and equity curves.
"""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional
from sqlalchemy import String, Integer, Date
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PerformanceSnapshot(Base):
    """
    Performance metrics computed at various intervals.
    Allows slicing by symbol, regime, strategy, session, etc.
    """
    __tablename__ = "performance_snapshots"
    
    snapshot_type: Mapped[str] = mapped_column(String(20), nullable=False)  # daily, weekly, monthly, all_time
    
    period_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    
    # Segmentation (which slice this snapshot represents)
    segment_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # symbol, regime, strategy, session
    segment_value: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # All metrics stored as JSON for flexibility
    # Contains: total_trades, win_rate, profit_factor, expectancy, drawdown, etc.
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)


class EquityCurve(Base):
    """
    Point-in-time equity tracking.
    Used for drawdown calculation and visualization.
    """
    __tablename__ = "equity_curve"
    
    timestamp: Mapped[datetime] = mapped_column(nullable=False, index=True)
    
    equity: Mapped[Decimal] = mapped_column(nullable=False)
    balance: Mapped[Decimal] = mapped_column(nullable=False)
    unrealized_pnl: Mapped[Optional[Decimal]] = mapped_column(nullable=True)
    
    drawdown_pct: Mapped[Optional[Decimal]] = mapped_column(nullable=True)
    peak_equity: Mapped[Optional[Decimal]] = mapped_column(nullable=True)
    
    risk_mode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    open_positions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
