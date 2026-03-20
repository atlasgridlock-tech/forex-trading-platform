# Forex Multi-Agent Trading Platform PRD

## Original Problem Statement
Build and debug a complex 15-agent forex trading platform, making the system fully functional for live trading. Initial issues included broken inter-agent API calls preventing trade signal generation.

## Architecture
- **System**: 15 microservices (agents) running as FastAPI applications
- **Location**: `/app/agents/` - each agent in its own directory
- **Shared Code**: `/app/agents/shared/` - common utilities
- **Startup**: `/app/agents/start_agents.sh` - launches all agents

## Key Agents
| Agent | Purpose | Port |
|-------|---------|------|
| orchestrator-agent | Central coordination, trade execution | 8000 |
| strategy-agent | Strategy analysis, confluence scoring | 8001 |
| macro-agent (Oracle) | Fundamental/macro analysis, "Ask Oracle" feature | 8002 |
| sentiment-agent (Pulse) | Retail positioning, COT data, sentiment | 8003 |
| news-agent (Sentinel) | News headlines, economic calendar | 8004 |
| ... | 10 more specialized agents | 8005+ |

## 3rd Party Integrations
- **MetaTrader 5 (MT5)**: Live data source and trade execution
- **Myfxbook**: Retail sentiment data (rate-limited)
- **Forex Factory**: Economic calendar
- **FRED API**: Macroeconomic data (CPI, GDP, unemployment)
- **Anthropic Claude**: AI analysis (Sonnet for narratives, Haiku for classification)

## What's Been Implemented

### December 2024 - Session 1
**Core Bug Fixes:**
- ✅ Fixed 404 errors in orchestrator-agent and strategy-agent API endpoints
- ✅ Resolved NoneType crashes with robust null-checking
- ✅ Fixed all inter-agent communication issues

**Dynamic "Ask Oracle" Feature:**
- ✅ FRED API integration for live economic data
- ✅ Dynamic CPI/GDP/employment trend calculation from historical data
- ✅ Live news headline integration from news-agent
- ✅ Claude AI headline classification and narrative generation
- ✅ Central bank tone assessment

**UX Improvements:**
- ✅ Suppressed noisy uvicorn/httpx logs across all agents
- ✅ Added "Clear Chat" button to all agent UIs with chat

**Cost Optimization:**
- ✅ Claude Haiku model for classification tasks (cheaper)
- ✅ Reduced dynamic narrative update from 1hr → 2hrs

**Rate Limiting Fix (P1):**
- ✅ Increased Myfxbook cache TTL from 10 → 60 minutes
- ✅ Added 2-hour rate-limit backoff mechanism
- ✅ Smarter cache logging

**Code Quality (P2):**
- ✅ Fixed 7 bare `except` clauses in shared/performance.py
- ✅ Added specific exception handling with debug logging

## Data Sources Status
| Source | Status | Notes |
|--------|--------|-------|
| FRED API | ✅ Live | Economic trends calculated from historical data |
| Forex Factory | ✅ Live | Calendar events with static backup |
| News Headlines | ✅ Live | RSS feeds via news-agent |
| Claude AI | ✅ Live | Narratives and analysis |
| Myfxbook | ⚠️ Rate-limited | 60-min cache + 2hr backoff implemented |
| CFTC COT | ✅ Live | 24-hour cache |

### March 2025 - Session 2
**Critical Bug Fixes:**
- ✅ Fixed spread calculation bug in `data-agent` (points treated as pips → 10x inflation)
- ✅ Fixed `qualified: True` not being returned from strategy-agent API
- ✅ Loosened overly restrictive spread limits in strategy templates
- ✅ Fixed orchestrator calling wrong port (8000 → 3020) for confluence score

**Score Discrepancy Diagnostic Feature:**
- ✅ Added `GET /api/confluence/{symbol}/debug` endpoint
- ✅ Returns raw agent input data alongside calculated score
- ✅ Timestamps on all confluence responses for timing comparison
- ✅ Detailed breakdown logging in lifecycle for troubleshooting

**Strategy Regime Template Updates (Reduces "regime invalid" rejections):**
- ✅ TREND_CONTINUATION: Added `breakout_ready` to allowed (breakouts often become trends)
- ✅ PULLBACK_IN_TREND: Added `breakout_ready` to allowed, removed from invalid
- ✅ BREAKOUT: Added `trending` to allowed, removed from invalid
- ✅ VOLATILITY_EXPANSION: Added `trending` to allowed (vol expands in strong trends)

**Guardian Risk Agent Updates:**
- ✅ Lowered minimum stop distance from 5 pips to 2 pips (allows tighter scalping entries)

**Strategy Agent Stop Calculation Fixes:**
- ✅ Increased default ATR from 0.001 to 0.01 (~10 pips) - prevents tiny stop calculations
- ✅ Added minimum stop distance enforcement: 8 pips (majors), 10 pips (JPY pairs)
- Root cause: When ATR data was missing, fallback of 0.001 caused sub-pip stops

**Chronicle v2.0 - Trade Journal Revamp:**
- ✅ Complete rewrite of `/app/agents/journal-agent/app.py`
- ✅ New chart generator: `/app/agents/journal-agent/chart_generator.py`
- ✅ Generates candlestick charts (mplfinance) with entry/SL/TP markers
- ✅ Creates confluence summary infographics
- ✅ Saves trade metadata, thesis, and agent verdicts as JSON
- ✅ Journal folder structure: `/mt5files/trade_journal/{timestamp}_{symbol}_{direction}/`
- ✅ Updated lifecycle.py to call new Chronicle API on trade execution

**Score History Tracking:**
- ✅ New module: `/app/agents/orchestrator-agent/score_history.py`
- ✅ Records confluence scores over time during lifecycle scans
- ✅ Generates line charts showing score evolution with thresholds
- ✅ Multi-symbol comparison charts
- ✅ New API endpoints:
  - `GET /api/score-history/{symbol}` - Get score history JSON
  - `GET /api/score-history/{symbol}/chart` - Get score evolution chart (PNG)
  - `GET /api/score-history` - Summary of all symbols
  - `GET /api/score-history/compare/chart?symbols=USDJPY,GBPUSD` - Multi-symbol comparison
- ✅ Stores history in `/mt5files/score_history/`

**Status:**
- System is working end-to-end: pairs being added to watchlist (60-74 score)
- Regime restrictions loosened - many more strategies now qualify
- Stop distance issues fixed - realistic stops will now be generated
- Chronicle v2.0 ready to capture trades with charts and full context
- Score history tracking active - can visualize confluence evolution
- Waiting for confluence ≥75 to verify trade execution

## Pending/Backlog
- P0: Verify trade execution when confluence ≥75 (USER VERIFICATION PENDING)
- P1: Consider lowering execution threshold from 75 → 70 if scores remain in 70-74 range
- P2: ATR-based trailing stops
- P2: Multi-timeframe confluence weighting

## Key Files
- `/app/agents/orchestrator-agent/lifecycle.py` - Core trade lifecycle logic
- `/app/agents/orchestrator-agent/app.py` - Dashboard, confluence API
- `/app/agents/orchestrator-agent/score_history.py` - Confluence score history tracker
- `/app/agents/data-agent/app.py` - Market data, spread calculation
- `/app/agents/strategy-agent/app.py` - Strategy qualification, templates
- `/app/agents/journal-agent/app.py` - Chronicle v2.0 trade journaling
- `/app/agents/journal-agent/chart_generator.py` - Trade chart generation (mplfinance)
- `/app/agents/risk-agent/app.py` - Guardian risk management
- `/app/agents/macro-agent/app.py` - Oracle agent, dynamic narratives
- `/app/agents/sentiment-agent/app.py` - Pulse agent, rate limiting fix
- `/app/agents/shared/utils.py` - Claude helper function
- `/app/agents/shared/performance.py` - HTTP pooling, caching
- `/app/agents/start_agents.sh` - Startup script
