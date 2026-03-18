"""
Shared Agent Utilities
Common functions and configurations used across all agents.
"""

import os
import httpx
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any


# ═══════════════════════════════════════════════════════════════
# SYMBOL UTILITIES
# ═══════════════════════════════════════════════════════════════

SYMBOL_SUFFIX = os.getenv("SYMBOL_SUFFIX", "")

def broker_symbol(symbol: str) -> str:
    """Convert internal symbol to broker symbol (add suffix)."""
    if SYMBOL_SUFFIX and not symbol.endswith(SYMBOL_SUFFIX):
        return symbol + SYMBOL_SUFFIX
    return symbol


def internal_symbol(broker_sym: str) -> str:
    """Convert broker symbol to internal symbol (strip suffix)."""
    if SYMBOL_SUFFIX and broker_sym.endswith(SYMBOL_SUFFIX):
        return broker_sym[:-len(SYMBOL_SUFFIX)]
    return broker_sym


def is_jpy_pair(symbol: str) -> bool:
    """Check if symbol is a JPY pair (affects pip calculation)."""
    return "JPY" in symbol.upper()


def pip_value(symbol: str) -> float:
    """Get pip value for a symbol."""
    return 0.01 if is_jpy_pair(symbol) else 0.0001


def pip_value_per_lot(symbol: str, account_currency: str = "USD") -> float:
    """
    Get approximate pip value per standard lot (100,000 units) in account currency.
    
    For pairs where USD is quote currency (EURUSD, GBPUSD): ~$10 per pip per lot
    For pairs where USD is base currency (USDJPY, USDCHF): ~$10 per pip per lot (approximate)
    For cross pairs (GBPJPY, EURAUD): varies based on exchange rates
    
    This is a simplified calculation - MT5 provides exact values.
    """
    symbol = symbol.upper().replace(".S", "").replace(".ECN", "")
    
    # USD is quote currency - direct calculation
    if symbol.endswith("USD"):
        return 10.0  # $10 per pip per standard lot
    
    # USD is base currency
    if symbol.startswith("USD"):
        return 10.0  # Approximate (varies with exchange rate)
    
    # JPY pairs (pip = 0.01)
    if "JPY" in symbol:
        return 8.0  # Approximate for JPY crosses
    
    # Other crosses - approximate
    return 10.0


def calculate_lot_size(
    account_balance: float,
    risk_percent: float,
    stop_loss_pips: float,
    symbol: str,
    min_lot: float = 0.01,
    max_lot: float = 1.0,
) -> float:
    """
    Calculate position size based on risk percentage.
    
    Formula: Lot Size = (Account Balance × Risk %) / (Stop Loss Pips × Pip Value per Lot)
    
    Args:
        account_balance: Account balance in USD
        risk_percent: Risk per trade (e.g., 1.0 for 1%)
        stop_loss_pips: Distance from entry to stop loss in pips
        symbol: Trading symbol
        min_lot: Minimum lot size (default 0.01)
        max_lot: Maximum lot size (default 1.0)
    
    Returns:
        Calculated lot size, clamped between min_lot and max_lot
    """
    if stop_loss_pips <= 0 or account_balance <= 0 or risk_percent <= 0:
        return min_lot
    
    # Calculate risk amount in account currency
    risk_amount = account_balance * (risk_percent / 100)
    
    # Get pip value per lot
    pip_val = pip_value_per_lot(symbol)
    
    # Calculate lot size
    # Risk Amount = Lot Size × Stop Loss Pips × Pip Value per Lot
    # Lot Size = Risk Amount / (Stop Loss Pips × Pip Value per Lot)
    lot_size = risk_amount / (stop_loss_pips * pip_val)
    
    # Round to 2 decimal places (standard lot precision)
    lot_size = round(lot_size, 2)
    
    # Clamp between min and max
    lot_size = max(min_lot, min(lot_size, max_lot))
    
    return lot_size


def calculate_stop_loss_pips(entry_price: float, stop_loss: float, symbol: str) -> float:
    """Calculate stop loss distance in pips."""
    pip_size = pip_value(symbol)
    distance = abs(entry_price - stop_loss)
    return distance / pip_size


def format_price(price: float, symbol: str) -> str:
    """Format price with correct decimals for symbol."""
    decimals = 3 if is_jpy_pair(symbol) else 5
    return f"{price:.{decimals}f}"


# ═══════════════════════════════════════════════════════════════
# TRADING SESSIONS
# ═══════════════════════════════════════════════════════════════

SESSIONS = {
    "Sydney": (21, 6),
    "Tokyo": (0, 9),
    "London": (7, 16),
    "NewYork": (12, 21),
}


def get_current_session() -> str:
    """Determine current trading session based on UTC time."""
    utc_hour = datetime.utcnow().hour
    for session, (start, end) in SESSIONS.items():
        if start <= end:
            if start <= utc_hour < end:
                return session
        else:  # Crosses midnight
            if utc_hour >= start or utc_hour < end:
                return session
    return "Off-hours"


def is_market_open() -> bool:
    """Check if forex market is open (excludes weekend)."""
    now = datetime.utcnow()
    # Forex closed from Friday 21:00 UTC to Sunday 21:00 UTC
    if now.weekday() == 5:  # Saturday
        return False
    if now.weekday() == 4 and now.hour >= 21:  # Friday after 21:00
        return False
    if now.weekday() == 6 and now.hour < 21:  # Sunday before 21:00
        return False
    return True


# ═══════════════════════════════════════════════════════════════
# SYMBOLS LIST
# ═══════════════════════════════════════════════════════════════

FOREX_SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "GBPJPY", 
    "USDCHF", "USDCAD", "EURAUD", "AUDNZD", "AUDUSD"
]


# ═══════════════════════════════════════════════════════════════
# CLAUDE API CLIENT
# ═══════════════════════════════════════════════════════════════

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
DEFAULT_MODEL = "claude-sonnet-4-20250514"


async def call_claude(
    prompt: str,
    context: str = "",
    system_prompt: str = "",
    agent_name: str = "Agent",
    max_tokens: int = 2048,
    model: str = DEFAULT_MODEL,
) -> str:
    """
    Call Claude API with standard error handling.
    Uses pooled HTTP client for efficiency.
    
    Args:
        prompt: The user message/prompt
        context: Additional context to prepend
        system_prompt: System prompt (defaults to agent SOUL if available)
        agent_name: Name for logging
        max_tokens: Maximum response tokens
        model: Claude model to use
    
    Returns:
        Claude's response text or error message
    """
    if not ANTHROPIC_API_KEY:
        return f"[{agent_name}] No API key configured"
    
    # Build system prompt
    if not system_prompt:
        soul_path = Path("/app/workspace/SOUL.md")
        if soul_path.exists():
            try:
                system_prompt = soul_path.read_text()
            except:
                system_prompt = ""
    
    # Build user message
    user_message = f"{context}\n\n{prompt}" if context else prompt
    
    try:
        # Use pooled client for better performance
        from .performance import get_pooled_client
        client = await get_pooled_client()
        
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_message}],
            },
            timeout=60.0,
        )
        
        if response.status_code == 200:
            return response.json()["content"][0]["text"]
        else:
            return f"[{agent_name}] API error: {response.status_code}"
                
    except httpx.TimeoutException:
        return f"[{agent_name}] Request timed out"
    except ImportError:
        # Fallback if performance module not available
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": ANTHROPIC_API_KEY,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": model,
                        "max_tokens": max_tokens,
                        "system": system_prompt,
                        "messages": [{"role": "user", "content": user_message}],
                    },
                    timeout=60.0,
                )
                if response.status_code == 200:
                    return response.json()["content"][0]["text"]
                return f"[{agent_name}] API error: {response.status_code}"
        except Exception as e:
            return f"[{agent_name}] Error: {str(e)}"
    except Exception as e:
        return f"[{agent_name}] Error: {str(e)}"


# ═══════════════════════════════════════════════════════════════
# HTTP CLIENT HELPERS (Uses pooled connections)
# ═══════════════════════════════════════════════════════════════

async def fetch_json(url: str, timeout: float = 5.0) -> Optional[dict]:
    """Fetch JSON from URL with error handling using pooled client."""
    try:
        from .performance import pooled_get
        result = await pooled_get(url, timeout=timeout)
        if result is not None:
            return result
    except ImportError:
        pass
    except Exception as e:
        from .performance import DEBUG_HTTP
        if DEBUG_HTTP:
            print(f"[fetch_json] Pooled fetch error: {e}")
    
    # Fallback to direct client
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=timeout)
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        from .performance import DEBUG_HTTP
        if DEBUG_HTTP:
            print(f"[fetch_json] Direct fetch error: {e}")
    
    return None


async def post_json(url: str, data: dict, timeout: float = 10.0) -> Optional[dict]:
    """Post JSON to URL with error handling using pooled client."""
    try:
        from .performance import pooled_post
        return await pooled_post(url, data, timeout=timeout)
    except ImportError:
        # Fallback if performance module not available
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=data, timeout=timeout)
                if response.status_code == 200:
                    return response.json()
        except:
            pass
    except Exception:
        pass
    return None


# ═══════════════════════════════════════════════════════════════
# AGENT URLS (from environment)
# ═══════════════════════════════════════════════════════════════

def get_agent_url(agent_name: str) -> str:
    """Get URL for an agent from environment."""
    url_map = {
        "curator": os.getenv("CURATOR_URL", "http://localhost:3021"),
        "data": os.getenv("CURATOR_URL", "http://localhost:3021"),
        "sentinel": os.getenv("SENTINEL_URL", "http://localhost:3010"),
        "news": os.getenv("SENTINEL_URL", "http://localhost:3010"),
        "oracle": os.getenv("ORACLE_URL", "http://localhost:3011"),
        "macro": os.getenv("ORACLE_URL", "http://localhost:3011"),
        "atlas": os.getenv("ATLAS_URL", "http://localhost:3012"),
        "technical": os.getenv("ATLAS_URL", "http://localhost:3012"),
        "guardian": os.getenv("GUARDIAN_URL", "http://localhost:3013"),
        "risk": os.getenv("GUARDIAN_URL", "http://localhost:3013"),
        "architect": os.getenv("ARCHITECT_URL", "http://localhost:3014"),
        "structure": os.getenv("ARCHITECT_URL", "http://localhost:3014"),
        "pulse": os.getenv("PULSE_URL", "http://localhost:3015"),
        "sentiment": os.getenv("PULSE_URL", "http://localhost:3015"),
        "compass": os.getenv("COMPASS_URL", "http://localhost:3016"),
        "regime": os.getenv("COMPASS_URL", "http://localhost:3016"),
        "tactician": os.getenv("TACTICIAN_URL", "http://localhost:3017"),
        "strategy": os.getenv("TACTICIAN_URL", "http://localhost:3017"),
        "balancer": os.getenv("BALANCER_URL", "http://localhost:3018"),
        "portfolio": os.getenv("BALANCER_URL", "http://localhost:3018"),
        "executor": os.getenv("EXECUTOR_URL", "http://localhost:3019"),
        "execution": os.getenv("EXECUTOR_URL", "http://localhost:3019"),
        "nexus": os.getenv("ORCHESTRATOR_URL", "http://localhost:3020"),
        "orchestrator": os.getenv("ORCHESTRATOR_URL", "http://localhost:3020"),
        "chronicle": os.getenv("CHRONICLE_URL", "http://localhost:3022"),
        "journal": os.getenv("CHRONICLE_URL", "http://localhost:3022"),
        "arbiter": os.getenv("ARBITER_URL", "http://localhost:3024"),
        "governance": os.getenv("ARBITER_URL", "http://localhost:3024"),
    }
    return url_map.get(agent_name.lower(), "")


# ═══════════════════════════════════════════════════════════════
# TIMESTAMP PARSING
# ═══════════════════════════════════════════════════════════════

def parse_mt5_timestamp(ts_str: str) -> Optional[datetime]:
    """Parse MT5 timestamp formats."""
    formats = [
        "%Y.%m.%d %H:%M:%S",
        "%Y.%m.%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(ts_str.strip(), fmt)
        except:
            continue
    return None
