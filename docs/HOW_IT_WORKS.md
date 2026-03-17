# How the Forex Trading Platform Works - Complete Guide

**Version:** 2.0  
**Last Updated:** December 2025  
**System Status:** Fully Operational

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [System Overview](#system-overview)
3. [The Trading Flow - From Data to Trade](#the-trading-flow---from-data-to-trade)
4. [Agent Swarm Architecture](#agent-swarm-architecture)
5. [Data Pipeline](#data-pipeline)
6. [Decision Making Process](#decision-making-process)
7. [Trade Execution & Lifecycle](#trade-execution--lifecycle)
8. [Risk Management](#risk-management)
9. [Performance Optimization](#performance-optimization)
10. [Running the System](#running-the-system)
11. [Monitoring & Debugging](#monitoring--debugging)
12. [Configuration Reference](#configuration-reference)

---

## Executive Summary

This is a **multi-agent forex trading platform** that uses a swarm of 14 specialized microservices to analyze markets and execute trades. Each agent is an expert in one domain (technical analysis, sentiment, risk, etc.), and they communicate through HTTP APIs to reach consensus on trading decisions.

**Key Characteristics:**
- **14 FastAPI Microservices** running independently
- **Paper Trading by Default** (safety-first design)
- **Real-Time Data** from MT5, RSS feeds, and public APIs
- **AI-Powered Analysis** using Claude for news interpretation
- **Multi-Level Risk Controls** including hard gates and vetoes

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         EXTERNAL DATA SOURCES                        │
│   MT5 Bridge │ Myfxbook │ FRED API │ CFTC │ RSS Feeds │ Claude AI   │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          DATA LAYER                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │   Curator   │  │  Sentinel   │  │   Oracle    │  │    Pulse    │ │
│  │  (Data Hub) │  │(News/Events)│  │   (Macro)   │  │ (Sentiment) │ │
│  │  Port 3021  │  │  Port 3010  │  │  Port 3011  │  │  Port 3015  │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘ │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         ANALYSIS LAYER                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │  Atlas Jr.  │  │  Architect  │  │   Compass   │  │  Tactician  │ │
│  │ (Technical) │  │ (Structure) │  │  (Regime)   │  │ (Strategy)  │ │
│  │  Port 3012  │  │  Port 3014  │  │  Port 3016  │  │  Port 3017  │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘ │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     DECISION & RISK LAYER                            │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                      NEXUS (Orchestrator)                     │  │
│  │                         Port 3020                             │  │
│  │   Gathers all inputs → Calculates confluence → Makes decision │  │
│  └───────────────────────────────────────────────────────────────┘  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │
│  │  Guardian   │  │  Balancer   │  │   Arbiter   │                  │
│  │   (Risk)    │  │ (Portfolio) │  │(Governance) │                  │
│  │  Port 3013  │  │  Port 3018  │  │  Port 3024  │                  │
│  └─────────────┘  └─────────────┘  └─────────────┘                  │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      EXECUTION & LOGGING LAYER                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │
│  │  Executor   │  │  Chronicle  │  │   Insight   │                  │
│  │   (Trade)   │  │  (Journal)  │  │ (Analytics) │                  │
│  │  Port 3019  │  │  Port 3022  │  │  Port 3023  │                  │
│  └─────────────┘  └─────────────┘  └─────────────┘                  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## The Trading Flow - From Data to Trade

Here's exactly what happens when the system evaluates a potential trade:

### Step 1: Data Collection (Every 5 seconds)

```
MT5 Terminal on your Mac
        │
        ▼ (AgentBridge EA writes files)
    candle_data.csv    ← 9 pairs × 7 timeframes × 500 candles
    market_data.csv    ← Real-time tick data
        │
        ▼ (MT5 Bridge or Simulated Feed)
    HTTP POST to Curator
        │
        ▼
    Curator validates and stores data
    Calculates quality scores
```

### Step 2: Market Analysis (Continuous)

Each analysis agent independently evaluates the market:

| Agent | What It Analyzes | Output |
|-------|------------------|--------|
| **Atlas Jr.** | EMAs, RSI, MACD, ADX across M15/H1/H4/D1 | Trend grade (A-F), bias |
| **Architect** | Swing highs/lows, structure breaks, key levels | Structure state, S/R zones |
| **Compass** | Volatility, trend strength, session | Regime type, tradability |
| **Oracle** | Interest rates, inflation, employment from FRED | Macro bias per currency |
| **Pulse** | Myfxbook retail, CFTC COT, news tone | Positioning, crowd sentiment |
| **Sentinel** | Economic calendar, news headlines | Event risk score, blackouts |

### Step 3: Strategy Validation

The **Tactician** checks if conditions meet strategy requirements:

```
8 HARD GATES (All must pass):
├─ 1. Event Risk     → No HIGH impact event within 30 min
├─ 2. Spread         → Current spread ≤ max allowed
├─ 3. Stop Defined   → Valid stop loss must be set
├─ 4. Regime Match   → Current regime allows this strategy
├─ 5. Data Quality   → Quality score ≥ 60%
├─ 6. Portfolio Exp  → Not overexposed to this currency
├─ 7. Guardian Mode  → Risk manager not in defensive mode
└─ 8. Model Version  → Using approved strategy version
```

### Step 4: Confluence Scoring

The **Nexus** (Orchestrator) combines all inputs:

```python
Confluence Score = (
    Technical_Score × 0.25 +    # From Atlas Jr.
    Structure_Score × 0.20 +    # From Architect  
    Regime_Score × 0.15 +       # From Compass
    Macro_Score × 0.15 +        # From Oracle
    Sentiment_Score × 0.15 +    # From Pulse
    Event_Risk_Score × 0.10     # From Sentinel
)

Score ≥ 75 → EXECUTE
Score 60-74 → WATCHLIST  
Score < 60 → NO TRADE
```

### Step 5: Risk Approval

The **Guardian** performs final risk checks:

```
Risk Checks:
├─ Position size ≤ 0.25% account risk (default)
├─ Daily drawdown < 2%
├─ No correlated pairs already open
├─ Total exposure < limit
├─ Spread not abnormally wide
└─ Not end of session
```

### Step 6: Execution

If approved, the **Executor** handles the trade:

```
Paper Mode (Default):
├─ Simulates fill at current price
├─ Tracks position with SL/TP levels
├─ Applies lifecycle management
└─ Logs to Chronicle

Live Mode (Requires Promotion):
├─ Writes command to MT5 bridge
├─ Waits for fill confirmation
├─ Monitors execution quality
└─ Handles partial fills
```

### Step 7: Position Lifecycle Management

The Executor manages open positions:

```
Position States:
OPEN → BREAKEVEN → TP1_HIT → TP2_HIT → TP3_HIT → CLOSED

Lifecycle Features:
├─ Partial Take Profits: 33% at TP1, 50% at TP2, 100% at TP3
├─ Break-Even: Move SL to entry + 1 pip after 10 pips profit
├─ Trailing Stop: Trail SL 15 pips behind after 20 pips profit
└─ Automatic state tracking and updates
```

---

## Agent Swarm Architecture

### Communication Pattern

All agents communicate via HTTP REST APIs:

```
┌─────────┐    GET /api/market/EURUSD    ┌─────────┐
│  Nexus  │ ────────────────────────────> │ Curator │
│         │ <────────────────────────────  │         │
└─────────┘    {"price": 1.0855, ...}     └─────────┘
```

### Shared Infrastructure

All agents share a common codebase in `/app/agents/shared/`:

```python
from shared import (
    # HTTP Client (Pooled for performance)
    pooled_get, pooled_post, get_pooled_client,
    
    # Caching
    InMemoryCache, cached, cached_fetch,
    
    # Claude AI calls
    call_claude,
    
    # Utilities
    get_agent_url, pip_value, broker_symbol,
    FOREX_SYMBOLS,
)
```

### Agent Registry

| Port | Agent | Alias | Role |
|------|-------|-------|------|
| 3020 | orchestrator-agent | Nexus | Central coordinator, decision engine |
| 3021 | data-agent | Curator | Market data hub, quality scoring |
| 3010 | news-agent | Sentinel | Event risk, news monitoring |
| 3011 | macro-agent | Oracle | Fundamental analysis |
| 3012 | technical-agent | Atlas Jr. | Technical indicators |
| 3013 | risk-agent | Guardian | Risk management, veto power |
| 3014 | structure-agent | Architect | Market structure analysis |
| 3015 | sentiment-agent | Pulse | Positioning, COT, retail sentiment |
| 3016 | regime-agent | Compass | Regime detection |
| 3017 | strategy-agent | Tactician | Strategy validation |
| 3018 | portfolio-agent | Balancer | Exposure management |
| 3019 | execution-agent | Executor | Trade execution |
| 3022 | journal-agent | Chronicle | Trade logging |
| 3023 | analytics-agent | Insight | Performance analytics |
| 3024 | governance-agent | Arbiter | Model governance |

---

## Data Pipeline

### External Data Sources

| Source | Data Type | Refresh Rate | Cost |
|--------|-----------|--------------|------|
| MT5 Bridge | Price/Candles | 5 seconds | Free |
| Myfxbook API | Retail Sentiment | 5 minutes | Free |
| CFTC | COT Positioning | Weekly | Free |
| FRED API | Macro Data | 1 hour | Free |
| FXStreet RSS | News Headlines | 5 minutes | Free |
| ForexLive RSS | News Headlines | 5 minutes | Free |
| Claude API | News Analysis | 5 minutes | ~$0.29/day |

### Data Flow Example: Price Data

```
1. MT5 Terminal (on your Mac)
   └─ AgentBridge EA exports candle_data.csv every 5 sec
   
2. MT5 Bridge Script
   └─ Reads CSV, sends HTTP POST to Curator
   
3. Curator (Data Agent)
   ├─ Parses OHLCV data
   ├─ Validates (no gaps, valid relationships)
   ├─ Calculates quality score
   └─ Stores in memory by symbol/timeframe
   
4. Analysis Agents
   └─ Request data via GET /api/candles/{symbol}/{timeframe}
```

### Data Quality Scoring

Curator calculates quality scores for each symbol:

```python
Quality Score = (
    Completeness × 0.30 +    # % of expected candles present
    Freshness × 0.40 +       # Time since last update
    Consistency × 0.30       # No gaps, valid OHLC
)

Score > 80: Excellent (green)
Score 60-80: Good (yellow)
Score < 60: Poor (red) - May block trading
```

---

## Decision Making Process

### Confluence Scoring Deep Dive

Each category contributes to the final score:

#### Technical Alignment (25%)

```
Full Score Requirements:
├─ Trend grade A or B (from Atlas Jr.)
├─ Multi-timeframe alignment (H4 + D1 agree)
├─ Indicator confluence (EMA + RSI + MACD agree)
└─ Clear invalidation level defined

Deductions:
├─ C grade trend: -5 points
├─ MTF conflict: -8 points
├─ Single indicator only: -10 points
└─ No invalidation: -5 points
```

#### Market Structure (20%)

```
Full Score Requirements:
├─ Trading with structure (HH/HL for long, LH/LL for short)
├─ Entry at fresh S/R zone
├─ No immediate resistance in path
└─ Liquidity sweep confirms direction

Deductions:
├─ Counter-structure: -10 points
├─ Stale zone (tested 3+ times): -5 points
├─ Resistance within 1R: -8 points
└─ No structural confirmation: -5 points
```

### Veto Hierarchy

Some agents have absolute veto power:

```
Priority    Agent       Effect
────────────────────────────────────────
1 (highest) Guardian    Blocks all trading (risk breach)
2           Executor    Blocks execution (can't fill)
3           Arbiter     Blocks unapproved strategies
4           Balancer    Blocks overconcentration
5           Sentinel    Blocks during high-risk events
```

---

## Trade Execution & Lifecycle

### Execution Modes

| Mode | Description | Real Money |
|------|-------------|------------|
| **paper** | Simulated execution, tracks P&L | No |
| **shadow** | Real signals logged, paper execution | No |
| **guarded_live** | Real execution with all safety checks | Yes |

### Position Lifecycle States

```
OPEN
  │
  ├─ 10 pips profit ────────────────────┐
  │                                     ▼
  │                               BREAKEVEN
  │                               (SL → Entry + 1 pip)
  │                                     │
  │                                     ▼
  ├─ Price hits TP1 ──────────────> TP1_HIT
  │                                (Close 33%)
  │                                     │
  │                                     ▼
  ├─ Price hits TP2 ──────────────> TP2_HIT
  │                                (Close 50%)
  │                                     │
  │                                     ▼
  └─ Price hits TP3/SL ───────────> CLOSED
                                   (Close 100%)
```

### Trailing Stop Logic

```python
if profit_pips >= trailing_activation (default 20):
    new_sl = current_price - trailing_distance (default 15 pips)
    if new_sl > current_sl:
        update_sl(new_sl)
```

---

## Risk Management

### Hard Limits (Cannot Be Overridden)

```yaml
risk:
  default_risk_pct: 0.25      # Risk per trade
  max_risk_pct: 0.50          # Absolute max per trade
  max_daily_loss_pct: 2.0     # Stop trading for day
  max_weekly_drawdown: 4.0    # Reduce position sizes
  hard_pause_drawdown: 8.0    # Full trading halt

positions:
  max_simultaneous: 5
  max_per_symbol: 1
  max_same_direction: 3

spreads:
  max_major: 2.5              # EURUSD, GBPUSD, etc.
  max_cross: 4.0              # GBPJPY, EURAUD, etc.
```

### Kill Switches

Trading halts immediately when:

- Daily loss limit reached
- Weekly drawdown limit reached
- Data quality degrades below threshold
- MT5 connection lost (in live mode)
- Manual emergency stop triggered

---

## Performance Optimization

### HTTP Client Pooling

Instead of creating new connections per request:

```python
# OLD (Inefficient)
async with httpx.AsyncClient() as client:
    response = await client.get(url)

# NEW (Optimized)
from shared import pooled_get
response = await pooled_get(url)
```

Benefits:
- Connection reuse across all requests
- Reduced TCP handshake overhead
- Lower memory footprint
- Better performance under load

### In-Memory Caching

Frequently accessed data is cached:

```python
from shared import InMemoryCache, cached

cache = InMemoryCache(default_ttl=30)

# Cache agent status for 30 seconds
@cached(ttl=30)
async def get_agent_status():
    return await fetch_status()
```

### Performance Metrics

Monitor via: `GET /api/performance` on orchestrator

```json
{
  "http_pool": {
    "total_requests": 1542,
    "cache_hits": 892,
    "cache_misses": 650,
    "cache_hit_rate": "57.8%",
    "avg_latency_ms": "12.45"
  }
}
```

---

## Running the System

### Prerequisites

- Python 3.11+
- PostgreSQL (for TimescaleDB)
- Redis
- MetaTrader 5 (for live data)

### Quick Start

```bash
# 1. Navigate to agents directory
cd /app/agents

# 2. Set up environment
cp .env.example .env
# Edit .env with your API keys

# 3. Start infrastructure (PostgreSQL + Redis)
# These should be running already

# 4. Start all agents
./start_agents.sh

# 5. Start data feed (choose one)
# Option A: Simulated feed (for testing)
python3 simulated_feed.py

# Option B: Real MT5 bridge (run on your Mac)
python3 /app/mt5_bridge.py
```

### Verify System Health

```bash
# Check if orchestrator is running
curl http://localhost:3020/api/status

# Check all agent status
curl http://localhost:3020/api/agents

# View monitoring dashboard
open http://localhost:3020/monitor
```

---

## Monitoring & Debugging

### Log Locations

```
/app/agents/logs/
├─ orchestrator.log
├─ data-agent.log
├─ execution-agent.log
└─ ...
```

### Key API Endpoints for Debugging

| Endpoint | Purpose |
|----------|---------|
| `GET /api/status` | Agent health status |
| `GET /api/agents` | All agent statuses |
| `GET /api/confluence/{symbol}?direction=long` | Confluence breakdown |
| `GET /api/pair-analysis/{symbol}` | Full analysis from all agents |
| `GET /api/performance` | HTTP pool and cache metrics |
| `GET /monitor` | HTML monitoring dashboard |

### Common Issues

**Agent won't start:**
```bash
# Check for port conflicts
lsof -i :3020

# Check Python syntax
python3 -c "import app"
```

**No data flowing:**
```bash
# Check if simulated feed is running
ps aux | grep simulated_feed

# Test Curator directly
curl http://localhost:3021/api/market
```

**Low confluence scores:**
```bash
# Get detailed breakdown
curl "http://localhost:3020/api/pair-analysis/EURUSD" | jq
```

---

## Configuration Reference

### Environment Variables (/app/agents/.env)

```bash
# API Keys
ANTHROPIC_API_KEY=your_key_here
FRED_API_KEY=your_key_here
MYFXBOOK_EMAIL=your_email
MYFXBOOK_PASSWORD=your_password

# Data Paths
MT5_DATA_PATH=/app/mt5_data
SYMBOL_SUFFIX=.s

# Agent URLs (localhost for non-Docker)
ORCHESTRATOR_URL=http://localhost:3020
CURATOR_URL=http://localhost:3021
SENTINEL_URL=http://localhost:3010
# ... etc

# Trading Settings
DEFAULT_RISK_PCT=0.25
MAX_DAILY_LOSS=2.0
PAPER_MODE=true
```

### Confluence Weights (in Nexus SOUL.md)

```yaml
confluence_weights:
  technical: 0.25
  structure: 0.20
  macro: 0.15
  sentiment: 0.15
  regime: 0.15
  risk_execution: 0.10

decision_thresholds:
  execute: 75
  watchlist: 60
  no_trade: 40
```

---

## Summary

The forex trading platform is a sophisticated multi-agent system that:

1. **Collects** real-time market data from multiple sources
2. **Analyzes** markets across technical, fundamental, sentiment, and structural dimensions
3. **Validates** trades against strict strategy rules and hard gates
4. **Calculates** confluence scores using weighted inputs from all agents
5. **Manages risk** through multiple layers of checks and absolute vetoes
6. **Executes** trades with full lifecycle management (partial TPs, trailing stops)
7. **Logs** everything for analysis and continuous improvement

The system is designed with safety as the top priority - paper trading by default, conservative decision-making, and multiple kill switches to protect capital.

---

*Built with safety-first design principles.*
