# Forex Multi-Agent Trading Platform

A production-grade, multi-agent forex trading system built with 14 specialized microservices working together to analyze markets and execute trades.

## Quick Links

- [How It Works - Complete Guide](docs/HOW_IT_WORKS.md)
- [Agent Data Reference](docs/Agent_Data_Reference.md)
- [Shared Module Guide](agents/shared/REFACTORING_GUIDE.md)

---

## System Status

| Component | Status |
|-----------|--------|
| 14 Agent Swarm | Operational |
| Paper Trading | Active |
| Live Data Feed | Simulated (MT5 Bridge ready) |
| Risk Management | Enabled |
| Position Lifecycle | Full TP/SL Management |

---

## Safety Rules (Hard-Coded)

These rules **cannot be overridden**:

1. **Paper Trading is DEFAULT** - Real money requires explicit promotion
2. **Stop Loss is MANDATORY** - No trade executes without SL
3. **Guardian Has Veto** - Risk manager can block any trade
4. **Kill Switches are Immediate** - Trading halts when triggered
5. **Daily Loss Limits** - 2% max daily drawdown
6. **Position Limits** - Max 5 simultaneous positions

---

## Architecture Overview

```
                    ┌─────────────────────┐
                    │       NEXUS         │
                    │   (Orchestrator)    │
                    │     Port 3020       │
                    └──────────┬──────────┘
                               │
       ┌───────────────────────┼───────────────────────┐
       │                       │                       │
┌──────▼──────┐         ┌──────▼──────┐         ┌──────▼──────┐
│  DATA LAYER │         │  ANALYSIS   │         │   DECISION  │
├─────────────┤         ├─────────────┤         ├─────────────┤
│ Curator     │         │ Atlas Jr.   │         │ Guardian    │
│ Sentinel    │         │ Architect   │         │ Balancer    │
│ Oracle      │         │ Compass     │         │ Tactician   │
│ Pulse       │         │             │         │ Arbiter     │
└─────────────┘         └─────────────┘         └─────────────┘
                               │
                    ┌──────────▼──────────┐
                    │    EXECUTION        │
                    ├─────────────────────┤
                    │ Executor  Chronicle │
                    │ Insight             │
                    └─────────────────────┘
```

### Agent Registry

| Port | Name | Alias | Role |
|------|------|-------|------|
| 3020 | orchestrator-agent | Nexus | Central coordinator |
| 3021 | data-agent | Curator | Market data hub |
| 3010 | news-agent | Sentinel | Event risk |
| 3011 | macro-agent | Oracle | Fundamentals |
| 3012 | technical-agent | Atlas Jr. | Technical analysis |
| 3013 | risk-agent | Guardian | Risk veto |
| 3014 | structure-agent | Architect | Market structure |
| 3015 | sentiment-agent | Pulse | Positioning |
| 3016 | regime-agent | Compass | Regime detection |
| 3017 | strategy-agent | Tactician | Strategy validation |
| 3018 | portfolio-agent | Balancer | Exposure |
| 3019 | execution-agent | Executor | Trade execution |
| 3022 | journal-agent | Chronicle | Logging |
| 3023 | analytics-agent | Insight | Analytics |
| 3024 | governance-agent | Arbiter | Model governance |

---

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL (for TimescaleDB)
- Redis
- MetaTrader 5 (optional, for live data)

### 1. Setup Environment

```bash
cd /app/agents
cp .env.example .env
# Edit .env with your API keys:
# - ANTHROPIC_API_KEY
# - FRED_API_KEY (optional)
# - MYFXBOOK credentials (optional)
```

### 2. Start All Agents

```bash
./start_agents.sh
```

### 3. Start Data Feed

**Option A: Simulated Feed (Testing)**
```bash
python3 simulated_feed.py
```

**Option B: Real MT5 Bridge (Production)**
```bash
# On your Mac with MT5:
python3 /app/mt5_bridge.py
```

### 4. Verify System

```bash
# Check orchestrator
curl http://localhost:3020/api/status

# View all agents
curl http://localhost:3020/api/agents

# Open monitoring dashboard
open http://localhost:3020/monitor
```

---

## How Trading Works

### 1. Data Collection
MT5 or simulated feed sends price data every 5 seconds to Curator.

### 2. Analysis
Each agent analyzes their domain:
- **Technical**: EMAs, RSI, MACD, trend grades
- **Structure**: Swing highs/lows, S/R levels
- **Sentiment**: Retail positioning, COT data
- **Macro**: Interest rates, economic indicators
- **Events**: Economic calendar, news headlines

### 3. Confluence Scoring
Nexus calculates weighted score:
```
Score = Technical(25%) + Structure(20%) + Regime(15%) 
      + Macro(15%) + Sentiment(15%) + Events(10%)
```

### 4. Decision
- Score ≥ 75 → **EXECUTE**
- Score 60-74 → **WATCHLIST**
- Score < 60 → **NO TRADE**

### 5. Risk Check
Guardian performs final approval:
- Position sizing
- Drawdown limits
- Correlation checks
- Spread validation

### 6. Execution
Executor handles the trade with lifecycle management:
- Partial take-profits (TP1, TP2, TP3)
- Break-even stop loss
- Trailing stop

---

## API Examples

### Get System Status
```bash
curl http://localhost:3020/api/status
```

### Get Confluence Score
```bash
curl "http://localhost:3020/api/confluence/EURUSD?direction=long"
```

### Get Full Pair Analysis
```bash
curl http://localhost:3020/api/pair-analysis/EURUSD
```

### Evaluate a Trade
```bash
curl -X POST http://localhost:3020/api/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "EURUSD",
    "direction": "long",
    "entry_price": 1.0850,
    "stop_loss": 1.0820,
    "take_profit": 1.0910
  }'
```

### Execute Paper Trade
```bash
curl -X POST http://localhost:3019/api/execute \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "EURUSD",
    "direction": "long",
    "lot_size": 0.10,
    "entry_price": 1.0850,
    "stop_loss": 1.0820,
    "take_profit": 1.0880,
    "take_profit_2": 1.0910,
    "take_profit_3": 1.0940,
    "trailing_stop_pips": 20
  }'
```

---

## Configuration

### Risk Settings

```yaml
# In /app/agents/.env or risk_policy.yaml
DEFAULT_RISK_PCT=0.25      # Per trade
MAX_DAILY_LOSS=2.0         # Daily limit
MAX_POSITIONS=5            # Simultaneous
MAX_SPREAD_MAJOR=2.5       # Pips
MAX_SPREAD_CROSS=4.0       # Pips
```

### Confluence Weights

Adjust in orchestrator's SOUL.md:
```yaml
confluence_weights:
  technical: 0.25
  structure: 0.20
  macro: 0.15
  sentiment: 0.15
  regime: 0.15
  risk_execution: 0.10
```

---

## Monitoring

### Dashboard
Access the monitoring dashboard at:
```
http://localhost:3020/monitor
```

Features:
- Real-time agent health
- Message flow visualization
- Latency metrics
- Route success rates

### Performance Metrics
```bash
curl http://localhost:3020/api/performance
```

Returns HTTP pool stats and cache hit rates.

---

## Project Structure

```
/app/
├── agents/                    # All microservices
│   ├── orchestrator-agent/    # Central coordinator
│   ├── data-agent/            # Market data
│   ├── execution-agent/       # Trade execution
│   ├── risk-agent/            # Risk management
│   ├── ...                    # Other agents
│   ├── shared/                # Common code library
│   │   ├── __init__.py        # Exports
│   │   ├── utils.py           # Utilities
│   │   ├── base_agent.py      # Base classes
│   │   └── performance.py     # HTTP pooling, caching
│   ├── simulated_feed.py      # Test data feed
│   ├── start_agents.sh        # Startup script
│   └── .env                   # Configuration
├── docs/                      # Documentation
│   ├── HOW_IT_WORKS.md        # Complete guide
│   └── Agent_Data_Reference.md
├── mt5_bridge.py              # MT5 connector
└── memory/
    └── PRD.md                 # Product requirements
```

---

## Data Sources

| Source | Data | Cost |
|--------|------|------|
| MT5 | Prices, candles | Free |
| Myfxbook | Retail sentiment | Free |
| CFTC | COT positioning | Free |
| FRED | Macro data | Free |
| RSS Feeds | News | Free |
| Claude AI | News analysis | ~$0.29/day |

**Total Monthly Cost: ~$8.70**

---

## Supported Pairs

```
EURUSD  GBPUSD  USDJPY  GBPJPY  USDCHF
USDCAD  EURAUD  AUDNZD  AUDUSD
```

---

## Kill Switches

Trading halts automatically when:
- Daily loss exceeds 2%
- Weekly drawdown exceeds 4%
- Data quality degrades
- MT5 connection lost
- Manual emergency stop

---

## License

Private/Proprietary

---

## Disclaimer

This software is for educational and research purposes. Trading forex involves substantial risk of loss. **Always use paper trading mode until you fully understand the system.** The authors are not responsible for any financial losses.

---

Built with safety-first design principles.
