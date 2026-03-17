# Agent Refactoring Guide

## Shared Module Usage

All agents should import from the shared module:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared import (
    # Utilities
    call_claude,          # Claude API calls
    get_agent_url,        # Get URL for any agent
    fetch_json,           # HTTP GET with error handling
    post_json,            # HTTP POST with error handling
    get_current_session,  # Trading session detection
    
    # Symbol utilities
    broker_symbol,        # Add broker suffix
    internal_symbol,      # Remove broker suffix
    is_jpy_pair,          # Check if JPY pair
    pip_value,            # Get pip value for symbol
    
    # Constants
    FOREX_SYMBOLS,        # List of tradeable symbols
    SESSIONS,             # Trading session hours
    
    # Base classes (optional)
    ChatRequest,          # Standard chat request model
)
```

## Removed Duplications

### 1. call_claude function
- **Before**: Each agent had its own ~20 line implementation
- **After**: Use `from shared import call_claude`
- **Change**: `await call_claude(prompt, context, agent_name="MyAgent")`

### 2. fetch_json / post_json
- **Before**: Each agent used `async with httpx.AsyncClient()` blocks
- **After**: Use `await fetch_json(url)` or `await post_json(url, data)`

### 3. Agent URL configuration
- **Before**: `CURATOR_URL = os.getenv("CURATOR_URL", "http://data-agent:8000")`
- **After**: `CURATOR_URL = get_agent_url("curator")`

### 4. Symbol utilities
- **Before**: Each agent had duplicate broker_symbol/internal_symbol functions
- **After**: Import from shared module

### 5. ChatRequest model
- **Before**: Each agent defined its own `class ChatRequest(BaseModel)`
- **After**: Import from shared module

## Refactoring Checklist

For each agent:
- [ ] Add sys.path and imports from shared
- [ ] Remove duplicate `call_claude` function
- [ ] Remove duplicate `ChatRequest` class
- [ ] Replace httpx calls with `fetch_json` / `post_json`
- [ ] Use `get_agent_url()` for agent URLs
- [ ] Use shared symbol utilities
- [ ] Use `FOREX_SYMBOLS` constant

## Example: Before vs After

### Before
```python
import os
import httpx
from pydantic import BaseModel

CURATOR_URL = os.getenv("CURATOR_URL", "http://data-agent:8000")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

class ChatRequest(BaseModel):
    message: str

async def fetch_data(symbol):
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{CURATOR_URL}/api/market/{symbol}")
            if r.status_code == 200:
                return r.json()
    except:
        pass
    return None

async def call_claude(prompt, context=""):
    # 20 lines of duplicate code...
```

### After
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared import (
    get_agent_url,
    fetch_json,
    call_claude,
    ChatRequest,
)

CURATOR_URL = get_agent_url("curator")

async def fetch_data(symbol):
    return await fetch_json(f"{CURATOR_URL}/api/market/{symbol}")
```

## Lines of Code Saved

| Function | Lines per agent | x15 agents | Total saved |
|----------|-----------------|------------|-------------|
| call_claude | ~20 | 15 | ~300 lines |
| ChatRequest | ~3 | 15 | ~45 lines |
| broker_symbol | ~5 | 4 | ~20 lines |
| httpx boilerplate | ~10 | varies | ~100 lines |
| **Total** | | | **~465 lines** |

Plus improved maintainability - fix once, applies everywhere.
