# Nexus - Orchestrator Agent

**Port:** 3020  
**Role:** Central Coordinator & Chief Investment Officer  
**Status:** Core Agent

---

## Overview

Nexus is the central orchestrator of the trading platform. It coordinates all other agents, gathers their inputs, calculates confluence scores, and makes final trading decisions. Every trade recommendation passes through Nexus.

## Key Responsibilities

1. **Gather Agent Inputs** - Poll all analysis agents for their assessments
2. **Calculate Confluence** - Weighted scoring across all dimensions
3. **Enforce Hard Gates** - 8 gates that must all pass
4. **Make Decisions** - BUY, SELL, WATCHLIST, or NO_TRADE
5. **Route Executions** - Send approved trades to Executor
6. **Monitor Health** - Track all agent status and performance

## API Endpoints

### Core Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/status` | Agent health and configuration |
| GET | `/api/agents` | Status of all connected agents |
| GET | `/api/confluence/{symbol}` | Confluence score with breakdown |
| GET | `/api/pair-analysis/{symbol}` | Full analysis from all agents |
| POST | `/api/evaluate` | Evaluate a potential trade |
| POST | `/api/ingest` | Receive data from other agents |

### Monitoring Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/monitor` | HTML monitoring dashboard |
| GET | `/api/monitor/stats` | JSON monitoring statistics |
| GET | `/api/performance` | HTTP pool and cache metrics |

### Trading Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/opportunities` | Current trade opportunities |
| POST | `/api/trade/propose` | Propose a trade for evaluation |
| GET | `/api/watchlist` | Current watchlist items |

## Confluence Scoring

```
Category              Weight    Source Agent
──────────────────────────────────────────────
Technical Alignment    25%      Atlas Jr. (3012)
Market Structure       20%      Architect (3014)
Regime Suitability     15%      Compass (3016)
Macro Alignment        15%      Oracle (3011)
Sentiment/Positioning  15%      Pulse (3015)
Event Risk             10%      Sentinel (3010)
```

### Decision Thresholds

```
Score ≥ 75  →  EXECUTE (BUY or SELL)
Score 60-74 →  WATCHLIST
Score < 60  →  NO_TRADE
```

## Hard Gates

All 8 gates must pass for a trade to be approved:

| Gate | Source | Requirement |
|------|--------|-------------|
| Event Risk | Sentinel | No HIGH impact event within 30 min |
| Spread | Curator | Current spread ≤ max allowed |
| Stop Defined | Request | Valid stop loss must be set |
| Regime Match | Compass | Current regime allows strategy |
| Data Quality | Curator | Quality score ≥ 60% |
| Portfolio Exposure | Balancer | Not overexposed |
| Guardian Approval | Guardian | Risk manager approves |
| Model Version | Arbiter | Strategy version approved |

## Veto Hierarchy

These agents have absolute veto power:

| Priority | Agent | Reason |
|----------|-------|--------|
| 1 | Guardian | Risk breach |
| 2 | Executor | Cannot execute |
| 3 | Arbiter | Unapproved strategy |
| 4 | Balancer | Overconcentration |
| 5 | Sentinel | High-risk event |

## Usage Examples

### Get Confluence Score

```bash
curl "http://localhost:3020/api/confluence/EURUSD?direction=long"
```

Response:
```json
{
  "symbol": "EURUSD",
  "direction": "long",
  "score": 78,
  "decision": "EXECUTE",
  "breakdown": {
    "technical": 22,
    "structure": 18,
    "regime": 13,
    "macro": 12,
    "sentiment": 8,
    "events": 5
  },
  "gates_passed": 8,
  "gates_total": 8
}
```

### Evaluate a Trade

```bash
curl -X POST http://localhost:3020/api/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "EURUSD",
    "direction": "long",
    "strategy": "pullback_trend",
    "entry_price": 1.0850,
    "stop_loss": 1.0820,
    "take_profit": 1.0910
  }'
```

### Get Full Pair Analysis

```bash
curl http://localhost:3020/api/pair-analysis/EURUSD | jq
```

## Integration Points

### Reads From

- **Curator (3021)** - Data quality, spread, market data
- **Sentinel (3010)** - Event risk, blocked windows
- **Oracle (3011)** - Macro alignment, currency strength
- **Atlas Jr. (3012)** - Technical signals, trend grade
- **Architect (3014)** - Structure, S/R zones
- **Pulse (3015)** - Sentiment, positioning
- **Compass (3016)** - Regime, strategy compatibility
- **Tactician (3017)** - Strategy validation
- **Guardian (3013)** - Risk approval
- **Balancer (3018)** - Portfolio exposure
- **Arbiter (3024)** - Model governance

### Writes To

- **Executor (3019)** - Approved trades
- **Chronicle (3022)** - All decisions for logging
- **Insight (3023)** - Performance tracking

## Configuration

Key settings in `workspace/SOUL.md`:

```yaml
confluence_weights:
  technical: 0.25
  structure: 0.20
  regime: 0.15
  macro: 0.15
  sentiment: 0.15
  events: 0.10

decision_thresholds:
  execute: 75
  watchlist: 60
  no_trade: 40

hard_gates:
  max_spread_major: 2.5
  max_spread_cross: 4.0
  min_data_quality: 60
  event_block_minutes: 30
```

## Monitoring Dashboard

Access at: `http://localhost:3020/monitor`

Features:
- Real-time agent health grid
- Message flow visualization
- Latency statistics
- Route success rates
- Auto-refresh every 10 seconds

---

*Nexus - The brain of the trading platform*
