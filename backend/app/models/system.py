"""
System Models - Kill switches, incidents, health, audit log.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import String, Integer, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, generate_uuid


class KillSwitch(Base):
    """
    Trading kill switches at various levels.
    These are the emergency brakes of the system.
    """
    __tablename__ = "kill_switches"
    
    level: Mapped[str] = mapped_column(String(20), nullable=False)  # symbol, daily, weekly, system
    scope: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # symbol name if level=symbol
    
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    activated_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    activated_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    deactivated_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    deactivated_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)


class Incident(Base):
    """
    System incidents and anomalies.
    All incidents are logged for review and pattern detection.
    """
    __tablename__ = "incidents"
    
    incident_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        unique=True,
        nullable=False,
        default=generate_uuid
    )
    
    severity: Mapped[str] = mapped_column(String(20), nullable=False)  # low, medium, high, critical
    incident_type: Mapped[str] = mapped_column(String(50), nullable=False)  # mt5_disconnect, data_corruption, drawdown_breach, etc.
    
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    affected_symbols: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    action_taken: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)


class SystemHealth(Base):
    """
    Point-in-time system health snapshots.
    Used for monitoring and alerting.
    """
    __tablename__ = "system_health"
    
    timestamp: Mapped[datetime] = mapped_column(nullable=False, index=True)
    
    # Component status
    mt5_connected: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    mt5_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    database_healthy: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    redis_healthy: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    scheduler_healthy: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    
    # Agent status
    active_agents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    unhealthy_agents: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    # Resources
    disk_usage_pct: Mapped[Optional[Decimal]] = mapped_column(nullable=True)
    memory_usage_pct: Mapped[Optional[Decimal]] = mapped_column(nullable=True)


class AuditLog(Base):
    """
    Immutable audit trail.
    Every significant action is logged here.
    This table is APPEND-ONLY - no UPDATE or DELETE.
    """
    __tablename__ = "audit_log"
    
    timestamp: Mapped[datetime] = mapped_column(nullable=False, index=True)
    
    actor: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # user, agent, system
    action: Mapped[str] = mapped_column(String(100), nullable=False)  # what was done
    target: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # what was affected
    
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        nullable=True,
        index=True
    )
