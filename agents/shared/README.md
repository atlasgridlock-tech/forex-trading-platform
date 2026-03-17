# Shared Module Reference

**Location:** `/app/agents/shared/`  
**Version:** 2.0

The shared module provides common utilities, base classes, and performance optimizations used by all agents.

---

## Installation

The shared module is automatically available to all agents. Simply import from `shared`:

```python
from shared import (
    # Utilities
    call_claude,
    get_agent_url,
    fetch_json,
    post_json,
    pip_value,
    broker_symbol,
    FOREX_SYMBOLS,
    
    # Base Classes
    BaseAgent,
    AnalysisAgent,
    ChatRequest,
    
    # Performance
    pooled_get,
    pooled_post,
    get_pooled_client,
    batch_fetch,
    InMemoryCache,
    cached,
    cached_fetch,
    get_metrics,
)
```

---

## Core Utilities

### Claude API Calls

```python
from shared import call_claude

# Simple call
response = await call_claude(
    prompt="Analyze EUR/USD trend",
    context="Current price: 1.0855, RSI: 58",
    agent_name="Atlas Jr."
)

# With custom system prompt
response = await call_claude(
    prompt="Your analysis request",
    system_prompt="You are a forex analyst...",
    max_tokens=1024,
    model="claude-sonnet-4-20250514"
)
```

### Agent URLs

```python
from shared import get_agent_url

# Get URL for any agent
curator_url = get_agent_url("curator")      # http://localhost:3021
guardian_url = get_agent_url("guardian")    # http://localhost:3013
nexus_url = get_agent_url("orchestrator")   # http://localhost:3020
```

### HTTP Requests

```python
from shared import fetch_json, post_json

# GET request
data = await fetch_json("http://localhost:3021/api/market/EURUSD")

# POST request
result = await post_json(
    "http://localhost:3020/api/evaluate",
    {"symbol": "EURUSD", "direction": "long"}
)
```

### Symbol Utilities

```python
from shared import broker_symbol, pip_value, FOREX_SYMBOLS

# Convert to broker format (adds suffix)
broker_sym = broker_symbol("EURUSD")  # "EURUSD.s"

# Calculate pip value
pv = pip_value("EURUSD", 0.10)  # $1.00 per pip for 0.10 lots

# List of all symbols
print(FOREX_SYMBOLS)  # ['EURUSD', 'GBPUSD', ...]
```

---

## Performance Module

### Pooled HTTP Client

Instead of creating new connections per request, use the pooled client:

```python
from shared import pooled_get, pooled_post, get_pooled_client

# Simple GET
data = await pooled_get("http://localhost:3021/api/market")

# Simple POST
result = await pooled_post(
    "http://localhost:3020/api/evaluate",
    {"symbol": "EURUSD"}
)

# Get raw client for custom use
client = await get_pooled_client()
response = await client.get(url, headers=custom_headers)
```

### Batch Fetching

Fetch from multiple URLs concurrently:

```python
from shared import batch_fetch

urls = [
    "http://localhost:3021/api/market/EURUSD",
    "http://localhost:3021/api/market/GBPUSD",
    "http://localhost:3012/api/analysis/EURUSD",
]

results = await batch_fetch(urls)
# Returns list of responses in same order
```

### In-Memory Caching

```python
from shared import InMemoryCache, cached, cached_fetch

# Direct cache usage
cache = InMemoryCache(default_ttl=30)

cache.set("key", value)
cache.set("key", value, ttl=60)  # Custom TTL
result = cache.get("key")  # Returns None if expired

# Function decorator
@cached(ttl=30)
async def get_expensive_data():
    # This will be cached for 30 seconds
    return await fetch_from_api()

# Cached URL fetch
data = await cached_fetch(
    "http://localhost:3021/api/market",
    ttl=10
)
```

### Performance Metrics

```python
from shared import get_metrics

metrics = get_metrics()

print(f"HTTP Requests: {metrics.http_requests}")
print(f"Cache Hits: {metrics.cache_hits}")
print(f"Cache Misses: {metrics.cache_misses}")
print(f"Hit Rate: {metrics.cache_hits / (metrics.cache_hits + metrics.cache_misses):.1%}")
print(f"Avg Latency: {metrics.avg_latency:.2f}ms")
```

---

## Base Classes

### BaseAgent

Base class for simple agents:

```python
from shared import BaseAgent

class MyAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="MyAgent",
            port=3025,
            description="My custom agent"
        )
    
    async def analyze(self, symbol: str):
        # Your analysis logic
        pass
```

### AnalysisAgent

Extended base for analysis agents with Claude integration:

```python
from shared import AnalysisAgent

class TechnicalAgent(AnalysisAgent):
    def __init__(self):
        super().__init__(
            name="Atlas Jr.",
            port=3012,
            system_prompt="You are a technical analyst..."
        )
    
    async def get_analysis(self, symbol: str):
        # Uses built-in Claude calling
        return await self.call_claude(f"Analyze {symbol}")
```

### ChatRequest

Pydantic model for chat endpoints:

```python
from shared import ChatRequest
from fastapi import FastAPI

app = FastAPI()

@app.post("/api/chat")
async def chat(request: ChatRequest):
    return {
        "response": await call_claude(request.message),
        "context": request.context
    }
```

---

## Constants

### FOREX_SYMBOLS

```python
FOREX_SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "GBPJPY", "USDCHF",
    "USDCAD", "EURAUD", "AUDNZD", "AUDUSD"
]
```

### Agent URL Map

```python
AGENT_URLS = {
    "orchestrator": "http://localhost:3020",
    "curator": "http://localhost:3021",
    "sentinel": "http://localhost:3010",
    "oracle": "http://localhost:3011",
    "atlas": "http://localhost:3012",
    "guardian": "http://localhost:3013",
    "architect": "http://localhost:3014",
    "pulse": "http://localhost:3015",
    "compass": "http://localhost:3016",
    "tactician": "http://localhost:3017",
    "balancer": "http://localhost:3018",
    "executor": "http://localhost:3019",
    "chronicle": "http://localhost:3022",
    "insight": "http://localhost:3023",
    "arbiter": "http://localhost:3024",
}
```

---

## Module Files

```
/app/agents/shared/
├── __init__.py          # All exports
├── utils.py             # Core utilities
├── base_agent.py        # Base classes
├── agent_output.py      # Pydantic models
├── performance.py       # HTTP pooling, caching
├── pubsub.py            # Redis pub/sub (if needed)
└── REFACTORING_GUIDE.md # Migration guide
```

---

## Best Practices

### 1. Always Use Pooled Client

```python
# Don't do this
async with httpx.AsyncClient() as client:
    response = await client.get(url)

# Do this
from shared import pooled_get
data = await pooled_get(url)
```

### 2. Cache Expensive Operations

```python
from shared import InMemoryCache

# Cache agent status (changes slowly)
cache = InMemoryCache(default_ttl=30)

async def get_agent_status(agent_key):
    cached = cache.get(f"status:{agent_key}")
    if cached:
        return cached
    
    status = await fetch_status(agent_key)
    cache.set(f"status:{agent_key}", status)
    return status
```

### 3. Use get_agent_url

```python
# Don't hardcode URLs
url = "http://localhost:3021/api/market"

# Do this
from shared import get_agent_url
url = f"{get_agent_url('curator')}/api/market"
```

### 4. Handle Errors Gracefully

```python
from shared import fetch_json

data = await fetch_json(url)
if data is None:
    # Request failed - handle gracefully
    return default_value
```

---

## Migration Guide

If updating old agent code to use shared module:

1. **Replace imports:**
   ```python
   # Old
   import httpx
   import os
   CURATOR_URL = os.getenv("CURATOR_URL", "http://localhost:3021")
   
   # New
   from shared import get_agent_url, pooled_get
   ```

2. **Replace HTTP calls:**
   ```python
   # Old
   async with httpx.AsyncClient() as client:
       r = await client.get(url)
       return r.json()
   
   # New
   return await pooled_get(url)
   ```

3. **Use shared Claude call:**
   ```python
   # Old
   async def call_claude(prompt):
       async with httpx.AsyncClient() as client:
           r = await client.post(...)
   
   # New
   from shared import call_claude
   response = await call_claude(prompt, agent_name="MyAgent")
   ```

---

*Shared module - Common code for the agent swarm*
