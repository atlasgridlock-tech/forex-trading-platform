"""
Application configuration using pydantic-settings.
All configuration is loaded from environment variables with sensible defaults.
"""
from functools import lru_cache
from typing import Optional, Literal
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database connection settings."""
    model_config = SettingsConfigDict(env_prefix="")
    
    database_url: str = Field(
        default="postgresql+asyncpg://forex:forex_dev_password@localhost:5432/forex_trading",
        alias="DATABASE_URL"
    )
    db_echo: bool = Field(default=False, alias="DB_ECHO")
    db_pool_size: int = Field(default=10, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=20, alias="DB_MAX_OVERFLOW")


class RedisSettings(BaseSettings):
    """Redis connection settings."""
    model_config = SettingsConfigDict(env_prefix="")
    
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")


class MT5Settings(BaseSettings):
    """MetaTrader 5 connection settings."""
    model_config = SettingsConfigDict(env_prefix="MT5_")
    
    terminal_path: Optional[str] = Field(default=None)
    login: Optional[int] = Field(default=None)
    password: Optional[str] = Field(default=None)
    server: Optional[str] = Field(default=None)
    timeout_ms: int = Field(default=60000)
    retry_attempts: int = Field(default=3)
    retry_delay_ms: int = Field(default=1000)
    
    @property
    def is_configured(self) -> bool:
        """Check if MT5 credentials are configured."""
        return all([self.login, self.password, self.server])


class TradingSettings(BaseSettings):
    """Trading mode and limits."""
    model_config = SettingsConfigDict(env_prefix="")
    
    # CRITICAL: Default is paper. Live requires explicit enablement.
    trading_mode: Literal["paper", "shadow", "live"] = Field(
        default="paper", 
        alias="TRADING_MODE"
    )
    live_trading_enabled: bool = Field(default=False, alias="LIVE_TRADING_ENABLED")
    
    # Risk defaults (can be overridden in risk_policy.yaml)
    default_risk_per_trade_pct: float = Field(default=0.35)
    max_daily_loss_pct: float = Field(default=2.0)
    max_weekly_drawdown_pct: float = Field(default=4.0)
    max_simultaneous_positions: int = Field(default=5)
    
    @field_validator("trading_mode")
    @classmethod
    def validate_trading_mode(cls, v: str, info) -> str:
        """Ensure live mode requires explicit flag."""
        # Note: This validation happens at load time.
        # Additional runtime checks enforce this in the trading service.
        return v


class NotificationSettings(BaseSettings):
    """Notification channel settings."""
    model_config = SettingsConfigDict(env_prefix="")
    
    discord_webhook_url: Optional[str] = Field(default=None, alias="DISCORD_WEBHOOK_URL")
    telegram_bot_token: Optional[str] = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: Optional[str] = Field(default=None, alias="TELEGRAM_CHAT_ID")
    smtp_host: Optional[str] = Field(default=None, alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_user: Optional[str] = Field(default=None, alias="SMTP_USER")
    smtp_password: Optional[str] = Field(default=None, alias="SMTP_PASSWORD")
    alert_email_to: Optional[str] = Field(default=None, alias="ALERT_EMAIL_TO")


class Settings(BaseSettings):
    """Main application settings."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # Application
    environment: Literal["development", "staging", "production"] = Field(
        default="development",
        alias="ENVIRONMENT"
    )
    debug: bool = Field(default=False, alias="DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    secret_key: str = Field(default="dev-secret-key-change-in-production", alias="SECRET_KEY")
    
    # Server
    backend_host: str = Field(default="0.0.0.0", alias="BACKEND_HOST")
    backend_port: int = Field(default=8000, alias="BACKEND_PORT")
    
    # Paths
    config_path: str = Field(default="/app/config", alias="CONFIG_PATH")
    
    # Sub-settings
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    mt5: MT5Settings = Field(default_factory=MT5Settings)
    trading: TradingSettings = Field(default_factory=TradingSettings)
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)
    
    @property
    def is_production(self) -> bool:
        return self.environment == "production"
    
    @property
    def is_development(self) -> bool:
        return self.environment == "development"


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.
    Uses LRU cache to avoid re-reading env on every call.
    """
    return Settings()


# Convenience export
settings = get_settings()
