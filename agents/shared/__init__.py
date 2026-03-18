"""
Shared Agent Modules

This package provides common utilities and base classes for all trading agents.

Usage:
    from shared import (
        # Utilities
        broker_symbol,
        internal_symbol,
        call_claude,
        get_agent_url,
        get_current_session,
        FOREX_SYMBOLS,
        
        # Base classes
        BaseAgent,
        AnalysisAgent,
        ChatRequest,
        
        # Output
        AgentOutput,
        OutputType,
        
        # Pub/Sub
        AgentPubSub,
    )
"""

from .utils import (
    # Symbol utilities
    broker_symbol,
    internal_symbol,
    is_jpy_pair,
    pip_value,
    pip_value_per_lot,
    calculate_lot_size,
    calculate_stop_loss_pips,
    format_price,
    SYMBOL_SUFFIX,
    
    # Sessions
    get_current_session,
    is_market_open,
    SESSIONS,
    
    # Symbols
    FOREX_SYMBOLS,
    
    # Claude API
    call_claude,
    ANTHROPIC_API_KEY,
    
    # HTTP helpers
    fetch_json,
    post_json,
    
    # Agent URLs
    get_agent_url,
    
    # Timestamps
    parse_mt5_timestamp,
)

from .agent_output import (
    AgentOutput,
    OutputType,
)

from .pubsub import (
    AgentPubSub,
    CHANNELS,
    NewsAlert,
    RiskAlert,
    TradeSignal,
    RegimeChange,
)

from .base_agent import (
    BaseAgent,
    AnalysisAgent,
    ChatRequest,
)

from .performance import (
    # HTTP Client Pool
    get_pooled_client,
    pooled_get,
    pooled_post,
    batch_fetch,
    
    # Caching
    InMemoryCache,
    RedisCache,
    cached,
    cached_fetch,
    cache_key,
    get_cache,
    
    # Metrics
    PerformanceMetrics,
    get_metrics,
)

__all__ = [
    # Utils
    "broker_symbol",
    "internal_symbol",
    "is_jpy_pair",
    "pip_value",
    "pip_value_per_lot",
    "calculate_lot_size",
    "calculate_stop_loss_pips",
    "format_price",
    "SYMBOL_SUFFIX",
    "get_current_session",
    "is_market_open",
    "SESSIONS",
    "FOREX_SYMBOLS",
    "call_claude",
    "ANTHROPIC_API_KEY",
    "fetch_json",
    "post_json",
    "get_agent_url",
    "parse_mt5_timestamp",
    
    # Output
    "AgentOutput",
    "OutputType",
    
    # PubSub
    "AgentPubSub",
    "CHANNELS",
    "NewsAlert",
    "RiskAlert",
    "TradeSignal",
    "RegimeChange",
    
    # Base classes
    "BaseAgent",
    "AnalysisAgent",
    "ChatRequest",
    
    # Performance
    "get_pooled_client",
    "pooled_get",
    "pooled_post",
    "batch_fetch",
    "InMemoryCache",
    "RedisCache",
    "cached",
    "cached_fetch",
    "cache_key",
    "get_cache",
    "PerformanceMetrics",
    "get_metrics",
]
