# Forex Multi-Agent Trading Platform - PRD

## Original Problem Statement
Build a 15-agent forex trading platform running on user's local Mac mini with:
- Full agent orchestration for technical analysis, sentiment, news, risk management
- Two-way order execution bridge with MetaTrader 5 (MT5)
- Live economic calendar from Forex Factory
- Live sentiment data from Myfxbook
- Automated trade execution via file-based IPC (`orders.json`)

## User Personas
- **Primary User**: Active forex trader running platform on Mac mini
- Requires real-time data feeds, automated analysis, and trade execution

## Core Requirements
1. All 15 agents starting and running correctly ✅
2. Live price data from MT5 ✅
3. Live economic calendar from Forex Factory ✅ (bug fixed this session)
4. Live sentiment from Myfxbook ✅
5. Account balance display ✅
6. Automated trade execution via MT5 EA ✅

## Architecture
- **Root**: `/app/`
- **Agents Directory**: `/app/agents/` (15 microservices)
- **Shared Library**: `/app/agents/shared/` (performance.py, order_bridge.py, economic_calendar.py)
- **MT5 Expert Advisor**: `/app/mt5_ea/AgentBridge_v6.mq5`
- **Configuration**: `/app/agents/.env`
- **Startup Script**: `/app/agents/start_agents.sh`

## 3rd Party Integrations
- MetaTrader 5 (MT5) - Live data & trade execution
- Myfxbook - Retail sentiment (API key required)
- Forex Factory - Economic calendar (XML feed)
- FRED - Macroeconomic data (API key required)
- PostgreSQL - Market data storage
- Redis - Caching
- Anthropic Claude - AI features

## Implemented Features (December 2025)
- [x] Live Order Execution Bridge (AgentBridge_v6.mq5 + orders.json)
- [x] Live Economic Calendar (economic_calendar.py parsing FF XML)
- [x] Live Sentiment Data (Myfxbook credentials integration)
- [x] Full Agent Startup (start_agents.sh tiered launch)
- [x] Account Balance Integration
- [x] Local Environment Debugging (configurable paths)
- [x] **FIX**: News-agent calendar race condition (background_monitoring now uses async live data)
- [x] **P1**: Inter-agent retry logic with exponential backoff (0.5s, 1s, 2s)
- [x] **P2**: Health checks in start_agents.sh (waits for `/api/status` before next tier)
- [x] **AUTO-TRADING**: Full auto-execution pipeline (Orchestrator → Executor → MT5)
- [x] **FIX (Dec 17)**: Fixed broken API endpoints in inter-agent communication:
  - `orchestrator-agent`: `/api/analyze/{sym}` → `/api/analysis/{sym}` (technical-agent)
  - `strategy-agent`: `/api/relative/{symbol}` → `/api/pair/{symbol}` (macro-agent)
- [x] **FIX (Dec 17)**: Improved Myfxbook API caching in sentiment-agent:
  - Increased cache TTL from 5 to 10 minutes
  - Added session reuse (30-minute session TTL)
  - Better fallback behavior when rate-limited

## Auto-Trading Configuration
- `AUTO_TRADE_ENABLED=true` - Enable/disable auto-execution (default: true)
- `USE_RISK_BASED_SIZING=true` - Enable risk-based lot sizing (default: true)
- `RISK_PERCENT=1.0` - Risk per trade as % of account (default: 1%)
- `MIN_LOT_SIZE=0.01` - Minimum position size
- `MAX_LOT_SIZE=0.5` - Maximum position size (safety cap)
- `DEFAULT_LOT_SIZE=0.01` - Fallback if risk calc fails
- Signal cooldown: 60 minutes (prevents duplicate executions)
- Thresholds: Score >= 75 executes, Score >= 60 adds to watchlist

## Position Sizing Formula
```
Lot Size = (Account Balance × Risk %) / (Stop Loss Pips × Pip Value per Lot)
```
Example: $10,000 account, 1% risk, 30 pip SL on EURUSD
- Risk Amount = $10,000 × 1% = $100
- Lot Size = $100 / (30 pips × $10/pip) = 0.33 lots

## Auto-Trading API Endpoints
- `GET /api/auto-trade` - Check status, risk settings, recent executions
- `POST /api/auto-trade/toggle?enabled=true` - Enable/disable auto-trading
- `POST /api/auto-trade/risk-percent?risk_percent=1.5` - Set risk % per trade
- `POST /api/auto-trade/toggle-risk-sizing?enabled=true` - Toggle risk-based sizing
- `POST /api/auto-trade/lot-size?lot_size=0.02` - Set fallback lot size
- `POST /api/auto-trade/clear-cooldowns` - Reset signal cooldowns
- `GET /api/auto-trade/calculate-size?symbol=EURUSD&entry_price=1.0850&stop_loss=1.0820` - Preview sizing

## Known Issues
- [FIXED] News-agent showing fallback data instead of live calendar
- [FIXED] Inter-agent communication errors (added retry logic)
- [FIXED] API endpoint mismatches causing 404 errors in trading pipeline

## Prioritized Backlog

### P0 - Critical
- End-to-end trading loop verification (user needs to restart agents and verify trades generate)

### P1 - High
- None (API fixes completed)

### P2 - Medium
- ATR-based trailing stop enhancements
- Clean up bare `except` clauses in performance.py (7 instances)

### P3 - Low/Future
- Advanced trailing strategies
- Performance optimization
- Multi-timeframe confluence weighting
- Documentation updates
