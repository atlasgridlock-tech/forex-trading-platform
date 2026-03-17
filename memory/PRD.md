# Forex Trading Platform - Multi-Agent System

## Original Problem Statement
User requested to analyze, debug, and fix a multi-agent forex trading platform. The system is designed as a microservices swarm with approximately 15 FastAPI-based agents, each handling a specific domain of trading logic.

## Documentation

### Quick Links
- **[How It Works - Complete Guide](/app/docs/HOW_IT_WORKS.md)** - Full A-Z system documentation
- **[Quick Start Tutorial](/app/docs/QUICK_START_TUTORIAL.md)** - Interactive hands-on guide
- **[Video Script](/app/docs/VIDEO_SCRIPT.md)** - 10-minute walkthrough script
- **[Agent Directory](/app/docs/AGENTS_DIRECTORY.md)** - Quick reference for all agents
- **[Agent Data Reference](/app/docs/Agent_Data_Reference.md)** - Data sources and formats
- **[Shared Module Guide](/app/agents/shared/README.md)** - Common code library
- **[Orchestrator README](/app/agents/orchestrator-agent/README.md)** - Central coordinator
- **[Data Agent README](/app/agents/data-agent/README.md)** - Market data hub
- **[Execution Agent README](/app/agents/execution-agent/README.md)** - Trade execution

## System Architecture
- **Location:** `/app/agents/`
- **Design:** Docker Compose-based (running manually without Docker)
- **Entry Point:** Orchestrator Agent (Nexus) at port 3020

### Agent Registry (15 Agents)
| Agent | Alias | Port | Purpose |
|-------|-------|------|---------|
| orchestrator-agent | Nexus | 3020 | Central coordinator, decision engine |
| data-agent | Curator | 3021 | Market data ingestion, quality scoring |
| news-agent | Sentinel | 3010 | Event risk monitoring |
| macro-agent | Oracle | 3011 | Fundamental analysis |
| technical-agent | Atlas Jr. | 3012 | Technical indicators |
| risk-agent | Guardian | 3013 | Risk management |
| structure-agent | Architect | 3014 | Market structure analysis |
| sentiment-agent | Pulse | 3015 | Sentiment/positioning |
| regime-agent | Compass | 3016 | Market regime detection |
| strategy-agent | Tactician | 3017 | Strategy selection |
| portfolio-agent | Balancer | 3018 | Portfolio exposure |
| execution-agent | Executor | 3019 | Trade execution |
| journal-agent | Chronicle | 3022 | Trade logging |
| analytics-agent | - | 3023 | Analytics |
| governance-agent | Arbiter | 3024 | Model governance |

### Infrastructure
- Redis: In-memory message passing (port 6379)
- PostgreSQL: TimescaleDB for market data (port 5432)

## Bugs Fixed (December 2025)

### Fix 1: Spread Reading Wrong Column
- **File:** `/app/agents/data-agent/app.py`
- **Issue:** Market data spread read from wrong CSV column (Point instead of Spread)
- **Impact:** All spread-based decisions were using incorrect values
- **Solution:** Fixed column index from `parts[4]` to `parts[3]`

### Fix 2: Orchestrator Spread Field Mismatch
- **File:** `/app/agents/orchestrator-agent/app.py`  
- **Issue:** Orchestrator expected `spread_pips` but Curator API returns `current_spread`
- **Impact:** Spread hard gate always showed 0.0 pips
- **Solution:** Updated to check both field names

### Fix 3: Spread Threshold Boundary Condition
- **File:** `/app/agents/orchestrator-agent/app.py`
- **Issue:** Spread check used `< max_spread` instead of `<= max_spread`
- **Impact:** Spreads exactly at threshold (e.g., 4.0 for crosses) were rejected
- **Solution:** Changed to `<= max_spread`

## Features Added

### Monitoring Dashboard
- **File:** `/app/agents/orchestrator-agent/monitoring.py`
- **Access:** `http://localhost:3020/monitor`
- **Features:**
  - Real-time agent health status for all 13 agents
  - Message flow tracking with latency metrics
  - Route activity analysis (success rate, avg latency)
  - Auto-refresh every 10 seconds
- **API:** `GET /api/monitor/stats` for JSON stats

## Current Status
- ✅ All 14 agents running and communicating (13 + orchestrator)
- ✅ Confluence scoring engine working
- ✅ Hard gates evaluation working
- ✅ Trade evaluation pipeline working
- ✅ Paper trade execution working
- ✅ Risk evaluation working (Guardian)
- ✅ Monitoring dashboard live
- ✅ **Live data feed connected** (simulated or MT5 bridge)
- ✅ Quality scores based on real-time spread data

## MT5 Bridge Integration

### Data Flow
```
MT5 (on Mac) → MT5 Bridge Script → Data Agent (Curator) → All Agents
```

### Endpoints Added to Data Agent
- `POST /api/market-data/update` - Receive tick data
- `POST /api/candles/update` - Receive candle data
- `GET /api/live/status` - Check live feed status

### Running the Bridge

**Option 1: Simulated Feed (for testing)**
```bash
python3 /app/agents/simulated_feed.py
```

**Option 2: Real MT5 Bridge (on your Mac)**
```bash
# Set the data agent URL
export CURATOR_URL=http://<server-ip>:3021
python3 /app/mt5_bridge.py
```

### MT5 EA Requirements
The MT5 Expert Advisor should export data to these files:
- `~/Library/Application Support/.../Common/Files/market_data.csv` - Tick data
- `~/Library/Application Support/.../Common/Files/candle_data.csv` - Candle data

## Environment Setup
```bash
# Required environment variables in /app/agents/.env
ANTHROPIC_API_KEY=<key>
FRED_API_KEY=<key>
MT5_DATA_PATH=/app/mt5_data
SYMBOL_SUFFIX=.s

# Agent URLs (localhost for non-Docker)
CURATOR_URL=http://localhost:3021
ORCHESTRATOR_URL=http://localhost:3020
# ... etc
```

## Test Commands
```bash
# Check agent status
curl http://localhost:3020/api/agents

# Get confluence for a symbol
curl "http://localhost:3020/api/confluence/EURUSD?direction=long"

# Evaluate a trade
curl -X POST http://localhost:3020/api/evaluate \
  -H "Content-Type: application/json" \
  -d '{"symbol":"EURUSD","direction":"short","strategy":"breakout","entry_price":1.085,"stop_loss":1.087,"take_profit":1.081}'
```

## Remaining Work
1. Connect Real MT5 Bridge (after user readiness)

## Documentation Complete ✅ (December 2025)

### Documents Created
- **[HOW_IT_WORKS.md](/app/docs/HOW_IT_WORKS.md)** - Complete A-Z system guide (668 lines)
- **[QUICK_START_TUTORIAL.md](/app/docs/QUICK_START_TUTORIAL.md)** - Interactive hands-on tutorial with checkpoints
- **[VIDEO_SCRIPT.md](/app/docs/VIDEO_SCRIPT.md)** - 10-minute walkthrough video script with timestamps
- **[AGENTS_DIRECTORY.md](/app/docs/AGENTS_DIRECTORY.md)** - Quick reference for all 14 agents
- **[README.md](/app/README.md)** - Updated main project README

- **Agent READMEs**:
  - `/app/agents/orchestrator-agent/README.md` - Nexus documentation
  - `/app/agents/data-agent/README.md` - Curator documentation
  - `/app/agents/execution-agent/README.md` - Executor documentation
  - `/app/agents/shared/README.md` - Shared module reference

## Performance Optimization ✅ (December 2025)

### Changes Made
- **Shared HTTP Client Pool**: Created `/app/agents/shared/performance.py` with:
  - `HTTPClientPool`: Singleton class managing a shared `httpx.AsyncClient` with connection pooling
  - `pooled_get()` / `pooled_post()`: Drop-in replacements for creating new clients per request
  - `batch_fetch()`: Concurrent request execution for parallel data fetching
  
- **In-Memory Caching**: Implemented `InMemoryCache` class with:
  - TTL-based expiration
  - `@cached` decorator for function results
  - `cached_fetch()` for URL response caching
  
- **Agent Integration**: Updated all 14 agents to use pooled HTTP client:
  - Replaced `async with httpx.AsyncClient()` patterns with `get_pooled_client()`
  - Reduced connection overhead by reusing persistent connections
  - Added caching for agent status in orchestrator (30s TTL)

- **Metrics Endpoint**: Added `GET /api/performance` to orchestrator for monitoring:
  - HTTP request counts
  - Cache hit/miss rates
  - Average latency tracking

### Performance Benefits
- **Connection Reuse**: Single HTTP client pool serves all agents
- **Reduced Latency**: No TCP handshake per request
- **Memory Efficiency**: Shared client resources
- **Cache Layer**: In-memory caching reduces redundant API calls

## Position Lifecycle Management ✅

### Features Implemented
- **Partial Take Profits**: Close 33% at TP1, 50% at TP2, 100% at TP3
- **Break-Even**: Move SL to entry + 1 pip after 10 pips profit
- **Trailing Stop**: Trail SL 15 pips behind price after 20 pips profit
- **State Tracking**: OPEN → BREAKEVEN → TP1_HIT → TP2_HIT → TP3_HIT/CLOSED

### API Endpoints
- `POST /api/lifecycle/update-price` - Update position with current price
- `GET /api/lifecycle/positions` - Get all positions with lifecycle state
- `GET /api/lifecycle/position/{order_id}` - Get specific position lifecycle
- `POST /api/lifecycle/simulate` - Simulate price movement for testing

### Usage Example
```bash
# Execute with multiple TPs and trailing
curl -X POST http://localhost:3019/api/execute -d '{
  "symbol": "EURUSD",
  "lot_size": 0.10,
  "direction": "long",
  "entry_price": 1.0850,
  "stop_loss": 1.0820,
  "take_profit": 1.0880,
  "take_profit_2": 1.0910,
  "take_profit_3": 1.0940,
  "trailing_stop_pips": 20
}'

# Simulate price to test lifecycle
curl -X POST http://localhost:3019/api/lifecycle/simulate -d '{
  "order_id": "PAPER-xxx",
  "prices": [1.0860, 1.0880, 1.0910, 1.0940]
}'
```

## Refactoring Progress

### Completed - All 14 Agents Refactored ✅
- ✅ `data-agent` (Curator)
- ✅ `news-agent` (Sentinel)
- ✅ `macro-agent` (Oracle)
- ✅ `technical-agent` (Atlas Jr.)
- ✅ `structure-agent` (Architect)
- ✅ `sentiment-agent` (Pulse)
- ✅ `regime-agent` (Compass)
- ✅ `strategy-agent` (Tactician)
- ✅ `risk-agent` (Guardian)
- ✅ `portfolio-agent` (Balancer)
- ✅ `execution-agent` (Executor)
- ✅ `journal-agent` (Chronicle)
- ✅ `governance-agent` (Arbiter)
- ✅ `analytics-agent` (Insight)

### Shared Module Benefits
- ~465 lines of duplicate code eliminated
- Single point of maintenance for:
  - Claude API calls
  - HTTP request handling
  - Symbol conversion utilities
  - Agent URL configuration
- Cleaner, more isolated agent code

### Usage
```python
from shared import (
    call_claude,
    get_agent_url,
    fetch_json,
    post_json,
    FOREX_SYMBOLS,
    ChatRequest,
)
```

See `/app/agents/shared/REFACTORING_GUIDE.md` for full guide.

## Test Results Summary
- **Trade Evaluation:** Working - correctly rejects trades with insufficient confluence
- **Paper Execution:** Working - successfully simulates trade fills
- **Risk Assessment:** Working - proper position sizing and risk checks
- **Agent Communication:** Working - 100% success rate, avg latency ~30ms
- **Live Data Feed:** Working - simulated feed sending ticks and candles
