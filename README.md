# Forex Trading Platform

A production-grade multi-agent forex trading system with comprehensive risk management.

## ⚠️ CRITICAL SAFETY RULES

These rules are **HARD-CODED** and cannot be overridden:

1. **Paper Trading is DEFAULT** - Real money trading requires explicit promotion
2. **Stop Loss is MANDATORY** - No trade executes without a stop loss
3. **Risk Manager Has Absolute Veto** - Cannot be overridden by any agent
4. **Kill Switches Are Immediate** - Trading halts instantly when triggered
5. **Promotion Gates Must Pass** - 100+ trades, 30+ days, profit factor ≥1.3
6. **Manual Approval Required** - A human must explicitly approve live trading
7. **Daily Loss Limits** - Trading halts when daily loss limit is reached
8. **Position Limits Enforced** - Cannot exceed max simultaneous positions
9. **Spread Limits Checked** - Trades blocked when spreads are abnormal
10. **Data Quality Required** - No trading on degraded or missing data

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR (Atlas)                      │
│              Central Decision Maker / CIO                    │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│   Data Layer  │     │Analysis Layer │     │Decision Layer │
├───────────────┤     ├───────────────┤     ├───────────────┤
│ Market Data   │     │ Technical     │     │ Risk Manager  │
│ MT5 Connector │     │ Structure     │     │ Portfolio     │
│ Data Validator│     │ Regime        │     │ Strategy      │
│               │     │ Sentiment     │     │               │
│               │     │ Fundamental   │     │               │
│               │     │ News/Events   │     │               │
└───────────────┘     └───────────────┘     └───────────────┘
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    EXECUTION LAYER                           │
├─────────────────────────────────────────────────────────────┤
│  Execution Agent │ Paper Trading │ Live Trading Service     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    POST-TRADE LAYER                          │
├─────────────────────────────────────────────────────────────┤
│  Journal Agent │ Performance Analytics │ Model Governance   │
└─────────────────────────────────────────────────────────────┘
```

## Trading Modes

| Mode | Description | Risk |
|------|-------------|------|
| **PAPER** | Simulated trading, no real money | None |
| **SHADOW** | Real signals logged, paper execution | None |
| **LIVE** | Real money execution | Full |

## Promotion Gates

To enable live trading, ALL gates must pass:

| Gate | Requirement |
|------|-------------|
| Minimum Trades | ≥100 paper trades |
| Minimum Days | ≥30 days of paper trading |
| Profit Factor | ≥1.3 |
| Max Drawdown | ≤5.0% |
| Win Rate | ≥40% |
| Avg R:R | ≥1.5 |
| Manual Approval | Human approval required |

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.11+
- Node.js 18+
- MetaTrader 5 (for live trading)

### Setup

```bash
# Clone and setup
cd forex-trading-platform

# Copy environment file
cp .env.example .env
# Edit .env with your settings

# Start infrastructure
docker-compose up -d

# Backend setup
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Start backend
uvicorn app.main:app --reload

# Frontend setup (new terminal)
cd frontend
npm install
npm run dev
```

### Access

- **Dashboard**: http://localhost:3000
- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

## Configuration

### Risk Settings (`config/risk_policy.yaml`)

```yaml
risk:
  default_risk_pct: 0.35
  max_daily_loss_pct: 2.0
  max_weekly_drawdown_pct: 4.0
  max_monthly_drawdown_pct: 6.0
  hard_pause_drawdown_pct: 8.0

positions:
  max_simultaneous: 5
  max_per_symbol: 1
  max_same_direction: 3
```

### Trading Config (`config/trading_config.yaml`)

```yaml
symbols:
  - EURUSD
  - GBPUSD
  - USDJPY
  - GBPJPY
  - USDCHF
  - USDCAD
  - EURAUD
  - AUDNZD
  - AUDUSD

timeframes:
  primary: M30
  analysis: [M5, M15, M30, H1, H4, D1]

sessions:
  asian: "23:00-08:00"
  london: "07:00-16:00"
  new_york: "12:00-21:00"
```

## API Endpoints

### System Status
- `GET /health` - Health check
- `GET /status` - System status
- `GET /api/account` - Account info

### Trading
- `POST /api/trading/execute` - Execute trade
- `POST /api/trading/close` - Close position
- `POST /api/trading/emergency-close-all` - Emergency close

### Promotion
- `GET /api/trading/promotion/status` - Gate status
- `POST /api/trading/promotion/request-live` - Request live mode
- `POST /api/trading/promotion/approve` - Approve live mode

### Analytics
- `GET /api/analytics` - Performance metrics
- `GET /api/analytics/by-symbol` - By symbol breakdown
- `GET /api/analytics/by-strategy` - By strategy breakdown

## Agents

| Agent | Purpose |
|-------|---------|
| **Orchestrator** | Central decision maker, coordinates all agents |
| **Market Data** | Fetches and validates market data |
| **Technical Analysis** | Indicators and technical signals |
| **Market Structure** | S/R zones, swing points, structure |
| **Regime Detection** | Market regime classification |
| **Sentiment** | COT data, retail positioning |
| **Fundamental** | Macro analysis, interest rates |
| **News/Events** | Economic calendar, blackouts |
| **Risk Manager** | Position sizing, risk limits |
| **Portfolio** | Correlation, exposure management |
| **Strategy Selection** | Strategy matching for conditions |
| **Execution** | Trade execution with safety checks |
| **Journal** | Trade documentation |
| **Performance** | Analytics and metrics |
| **Model Governance** | Strategy lifecycle management |

## Strategies

1. **Trend Following** - Trade with established trends
2. **Mean Reversion** - Fade overextended moves
3. **Breakout** - Trade structure breaks
4. **Range Trading** - Trade within ranges
5. **Momentum** - Trade momentum spikes
6. **Session Open** - Trade session opens

## Kill Switches

Trading halts immediately when:

- Daily loss limit reached
- Weekly drawdown limit reached
- Monthly drawdown limit reached
- Manual emergency stop triggered
- Data quality degradation detected
- MT5 connection lost (live mode)

## Project Structure

```
forex-trading-platform/
├── backend/
│   ├── app/
│   │   ├── agents/           # Trading agents
│   │   ├── api/              # REST API
│   │   ├── data/             # Data layer
│   │   ├── indicators/       # Technical indicators
│   │   ├── models/           # Database models
│   │   ├── services/         # Core services
│   │   └── workflows/        # Trading workflows
│   ├── alembic/              # Migrations
│   └── tests/                # Backend tests
├── frontend/
│   └── src/
│       ├── components/       # React components
│       ├── pages/            # Page components
│       ├── hooks/            # React hooks
│       └── api/              # API client
├── config/                   # Configuration files
└── docker-compose.yml        # Infrastructure
```

## Development

```bash
# Run tests
cd backend
pytest

# Format code
black app/
isort app/

# Type checking
mypy app/
```

## Monitoring

The dashboard provides real-time monitoring of:

- Account equity and P&L
- Open positions and exposure
- System health and agent status
- Kill switch status
- Workflow execution
- Performance metrics

## License

Private/Proprietary

## ⚠️ Disclaimer

This software is for educational and research purposes. Trading forex involves substantial risk of loss. Past performance does not guarantee future results. Always use paper trading mode until you fully understand the system's behavior. The authors are not responsible for any financial losses incurred through the use of this software.

---

Built with 🔒 safety-first design principles.
