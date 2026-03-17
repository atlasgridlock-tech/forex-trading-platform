# Agent Directory - Complete Reference

This document provides a quick reference for all 14 agents in the trading platform.

---

## Data Layer Agents

### Curator (Data Agent)
**Port:** 3021 | **Status:** Core

Central data hub - ingests, validates, and serves market data.

| Endpoint | Description |
|----------|-------------|
| `GET /api/market/{symbol}` | Current price, spread |
| `GET /api/candles/{symbol}/{tf}` | OHLCV data |
| `GET /api/quality` | Quality scores |
| `POST /api/market-data/update` | Receive live data |

**Key Output:** Price data, spread, quality scores

---

### Sentinel (News Agent)
**Port:** 3010 | **Status:** Core

Monitors economic calendar and news for event risk.

| Endpoint | Description |
|----------|-------------|
| `GET /api/risk/{symbol}` | Event risk for symbol |
| `GET /api/calendar` | Upcoming events |
| `GET /api/headlines` | Recent news |
| `GET /api/mode` | Current trading mode |

**Key Output:** Event risk score, blocked windows, news sentiment

---

### Oracle (Macro Agent)
**Port:** 3011 | **Status:** Core

Analyzes macroeconomic fundamentals from FRED API.

| Endpoint | Description |
|----------|-------------|
| `GET /api/pair/{symbol}` | Macro analysis for pair |
| `GET /api/currency/{currency}` | Single currency score |
| `GET /api/rates` | Interest rate differentials |
| `GET /api/indicators` | Economic indicators |

**Key Output:** Macro bias (bullish/bearish), currency strength scores

---

### Pulse (Sentiment Agent)
**Port:** 3015 | **Status:** Core

Tracks positioning from Myfxbook, CFTC COT, and news tone.

| Endpoint | Description |
|----------|-------------|
| `GET /api/sentiment/{symbol}` | Full sentiment analysis |
| `GET /api/retail/{symbol}` | Retail positioning |
| `GET /api/cot/{currency}` | COT data |
| `GET /api/news-tone` | AI-analyzed news tone |

**Key Output:** Retail long/short %, COT positioning, crowd sentiment

---

## Analysis Layer Agents

### Atlas Jr. (Technical Agent)
**Port:** 3012 | **Status:** Core

Calculates technical indicators and trend analysis.

| Endpoint | Description |
|----------|-------------|
| `GET /api/analysis/{symbol}` | Full technical analysis |
| `GET /api/indicators/{symbol}` | Raw indicator values |
| `GET /api/signals/{symbol}` | Trading signals |
| `GET /api/mtf/{symbol}` | Multi-timeframe analysis |

**Key Output:** Trend grade (A-F), indicator values, directional bias

---

### Architect (Structure Agent)
**Port:** 3014 | **Status:** Core

Analyzes market structure - swing points, S/R, trends.

| Endpoint | Description |
|----------|-------------|
| `GET /api/structure/{symbol}` | Structure analysis |
| `GET /api/levels/{symbol}` | Key S/R levels |
| `GET /api/swings/{symbol}` | Recent swing points |

**Key Output:** Structure state (bullish/bearish/ranging), key levels

---

### Compass (Regime Agent)
**Port:** 3016 | **Status:** Core

Identifies current market regime and session context.

| Endpoint | Description |
|----------|-------------|
| `GET /api/regime/{symbol}` | Current regime |
| `GET /api/session` | Current trading session |
| `GET /api/volatility/{symbol}` | Volatility state |

**Key Output:** Regime type, session info, strategy compatibility

**Regime Types:**
- TRENDING_BULLISH
- TRENDING_BEARISH
- RANGING
- VOLATILE
- BREAKOUT
- LOW_VOLATILITY

---

### Tactician (Strategy Agent)
**Port:** 3017 | **Status:** Core

Validates if conditions meet strategy requirements.

| Endpoint | Description |
|----------|-------------|
| `GET /api/strategy/{symbol}` | Best strategy for conditions |
| `GET /api/validate` | Validate a strategy |
| `GET /api/gates/{symbol}` | Hard gate status |

**Key Output:** Recommended strategy, gate pass/fail status

---

## Decision & Risk Layer Agents

### Guardian (Risk Agent)
**Port:** 3013 | **Status:** Core (Veto Power)

Final risk approval with absolute veto authority.

| Endpoint | Description |
|----------|-------------|
| `GET /api/status` | Current risk status |
| `POST /api/evaluate` | Evaluate trade risk |
| `GET /api/position-size` | Calculate position size |
| `GET /api/exposure` | Current exposure |

**Key Output:** Approved/rejected, position size, risk warnings

**Veto Triggers:**
- Daily loss limit exceeded
- Correlation risk
- Spread too wide
- Event blackout

---

### Balancer (Portfolio Agent)
**Port:** 3018 | **Status:** Core

Manages portfolio exposure and correlation.

| Endpoint | Description |
|----------|-------------|
| `GET /api/exposure/{symbol}` | Currency exposure |
| `GET /api/correlation` | Open position correlations |
| `GET /api/positions` | Portfolio positions |
| `POST /api/position/add` | Record new position |

**Key Output:** Exposure scores, correlation warnings

---

### Arbiter (Governance Agent)
**Port:** 3024 | **Status:** Supporting

Model governance and version control.

| Endpoint | Description |
|----------|-------------|
| `GET /api/status` | Governance status |
| `GET /api/models` | Approved model versions |
| `GET /api/validate/{strategy}` | Validate strategy version |

**Key Output:** Model approval status

---

## Execution & Logging Layer Agents

### Executor (Execution Agent)
**Port:** 3019 | **Status:** Core

Executes trades and manages position lifecycle.

| Endpoint | Description |
|----------|-------------|
| `POST /api/execute` | Execute trade |
| `GET /api/positions` | Open positions |
| `POST /api/close/{id}` | Close position |
| `GET /api/lifecycle/positions` | Positions with lifecycle |

**Key Output:** Execution receipt, fill price, position state

---

### Chronicle (Journal Agent)
**Port:** 3022 | **Status:** Supporting

Trade journaling and record keeping.

| Endpoint | Description |
|----------|-------------|
| `POST /api/trade/open` | Log trade open |
| `POST /api/trade/close` | Log trade close |
| `GET /api/trades` | Trade history |
| `GET /api/trade/{id}` | Single trade details |

**Key Output:** Trade records with full context

---

### Insight (Analytics Agent)
**Port:** 3023 | **Status:** Supporting

Performance analytics and metrics.

| Endpoint | Description |
|----------|-------------|
| `GET /api/status` | Analytics status |
| `GET /api/metrics` | Performance metrics |
| `GET /api/by-symbol` | Metrics by symbol |
| `GET /api/by-strategy` | Metrics by strategy |

**Key Output:** Win rate, profit factor, drawdown stats

---

## Quick Reference

### Agent Status Check
```bash
# Check all agents
curl http://localhost:3020/api/agents

# Check specific agent
curl http://localhost:302X/api/status
```

### Common Data Flows

```
Price Data:
MT5 → Curator → All Agents

Trade Signal:
Atlas Jr. + Architect + Compass → Tactician → Nexus → Guardian → Executor

Risk Check:
Any Agent → Guardian (can veto)

Logging:
Executor → Chronicle + Portfolio
```

### Port Summary

```
3010 - Sentinel (News)
3011 - Oracle (Macro)
3012 - Atlas Jr. (Technical)
3013 - Guardian (Risk)
3014 - Architect (Structure)
3015 - Pulse (Sentiment)
3016 - Compass (Regime)
3017 - Tactician (Strategy)
3018 - Balancer (Portfolio)
3019 - Executor (Execution)
3020 - Nexus (Orchestrator)
3021 - Curator (Data)
3022 - Chronicle (Journal)
3023 - Insight (Analytics)
3024 - Arbiter (Governance)
```

---

*All agents communicate via HTTP REST APIs using the shared module.*
