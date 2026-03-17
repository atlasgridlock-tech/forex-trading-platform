"""
Market Data Models - OHLCV bars, data health, key levels.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import String, Integer, Boolean, Text, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class MarketDataBar(Base):
    """
    OHLCV price bars for all symbols and timeframes.
    This is the foundation data for all analysis.
    """
    __tablename__ = "market_data_bars"
    
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(5), nullable=False, index=True)
    bar_timestamp: Mapped[datetime] = mapped_column(nullable=False, index=True)
    
    open: Mapped[Decimal] = mapped_column(nullable=False)
    high: Mapped[Decimal] = mapped_column(nullable=False)
    low: Mapped[Decimal] = mapped_column(nullable=False)
    close: Mapped[Decimal] = mapped_column(nullable=False)
    tick_volume: Mapped[int] = mapped_column(Integer, default=0)
    spread: Mapped[Optional[Decimal]] = mapped_column(nullable=True)
    data_quality: Mapped[Decimal] = mapped_column(default=Decimal("1.0"))
    
    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "bar_timestamp", name="uq_bar_identity"),
        Index("ix_market_data_bars_lookup", "symbol", "timeframe", bar_timestamp.desc()),
    )


class MarketDataHealth(Base):
    """
    Data quality and feed health tracking per symbol.
    Critical for determining if trading should be allowed.
    """
    __tablename__ = "market_data_health"
    
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(nullable=False, index=True)
    
    quality_score: Mapped[Decimal] = mapped_column(nullable=False)
    spread_current: Mapped[Optional[Decimal]] = mapped_column(nullable=True)
    spread_average: Mapped[Optional[Decimal]] = mapped_column(nullable=True)
    missing_bars: Mapped[int] = mapped_column(Integer, default=0)
    feed_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    is_halted: Mapped[bool] = mapped_column(Boolean, default=False)
    halt_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    __table_args__ = (
        Index("ix_market_data_health_lookup", "symbol", timestamp.desc()),
    )


class KeyLevel(Base, TimestampMixin):
    """
    Significant support/resistance zones identified by the Market Structure Agent.
    """
    __tablename__ = "key_levels"
    
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    level_type: Mapped[str] = mapped_column(String(50), nullable=False)  # support, resistance, pivot
    
    price_upper: Mapped[Decimal] = mapped_column(nullable=False)
    price_lower: Mapped[Decimal] = mapped_column(nullable=False)
    price_mid: Mapped[Decimal] = mapped_column(nullable=False)
    
    strength: Mapped[Optional[Decimal]] = mapped_column(nullable=True)  # 0.0 to 1.0
    timeframe: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    
    is_fresh: Mapped[bool] = mapped_column(Boolean, default=True)
    touch_count: Mapped[int] = mapped_column(Integer, default=0)
    first_detected: Mapped[datetime] = mapped_column(nullable=False)
    last_tested: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    
    __table_args__ = (
        Index("ix_key_levels_symbol", "symbol", "level_type"),
    )
