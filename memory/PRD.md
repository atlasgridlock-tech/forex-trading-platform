# Forex Trading Platform - Multi-Agent System

## Original Problem Statement
User requested to analyze, debug, and fix a multi-agent forex trading platform. The system is designed as a microservices swarm with approximately 15 FastAPI-based agents, each handling a specific domain of trading logic.

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
- ⚠️ Using mock MT5 data (real MT5 bridge not connected)

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
1. **P0:** Connect to real MT5 bridge for live data
2. **P1:** Code refactoring for cleaner agent isolation
3. **P2:** Documentation updates
4. **P3:** Analytics agent integration

## Test Results Summary
- **Trade Evaluation:** Working - correctly rejects trades with insufficient confluence
- **Paper Execution:** Working - successfully simulates trade fills
- **Risk Assessment:** Working - proper position sizing and risk checks
- **Agent Communication:** Working - 100% success rate, avg latency ~30ms
