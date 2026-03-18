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

## Known Issues
- [FIXED] News-agent showing fallback data instead of live calendar
- [P1] Inter-agent communication errors (sporadic connection failures)

## Prioritized Backlog

### P0 - Critical
- End-to-end trading loop verification

### P1 - High
- Add retry logic/health checks for inter-agent communication
- Robust error handling in start_agents.sh

### P2 - Medium
- ATR-based trailing stop enhancements
- Clean up bare `except` clauses in performance.py

### P3 - Low/Future
- Advanced trailing strategies
- Performance optimization
- Documentation updates
