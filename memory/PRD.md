# Forex Multi-Agent Trading Platform PRD

## Overview
A 15-agent autonomous forex trading system that analyzes market data, generates trade setups, and executes trades based on confluence scoring.

## Core Architecture
- **Orchestrator (Nexus)**: Central coordination, lifecycle management, score history tracking
- **Data Agent (Curator)**: Market data feeds from MT5
- **Technical Agent (Atlas)**: Technical analysis indicators
- **Structure Agent (Architect)**: Market structure (support/resistance, FVGs)
- **Sentiment Agent (Pulse)**: Retail sentiment from Myfxbook
- **Macro Agent (Oracle)**: Economic calendar, FRED data
- **News Agent (Sentinel)**: Headline analysis via Claude
- **Regime Agent (Compass)**: Market regime classification
- **Strategy Agent (Tactician)**: Trade setup generation
- **Risk Agent (Guardian)**: Position sizing, risk checks (12 checks total)
- **Portfolio Agent (Balancer)**: Exposure management
- **Execution Agent (Executor)**: Order execution via MT5
- **Journal Agent (Chronicle)**: Trade journaling with charts
- **Analytics Agent (Insight)**: Performance attribution
- **Governance Agent (Arbiter)**: Strategy improvement

## Confluence Scoring System
- Multi-factor scoring: Technical (25pts), Structure (15pts), Macro (15pts), Sentiment (10pts), Regime (10pts), Risk/Execution (11pts)
- Execute threshold: 75+
- Watchlist threshold: 60-74
- Blocked: <60

## Features Completed (March 2025)

### P1: Interactive Score History Charts ✅
**Replaced static matplotlib PNG with interactive Chart.js charts:**
- Real-time hover tooltips showing:
  - Score value (e.g., "79/100")
  - Direction: 📈 LONG (Buy) / 📉 SHORT (Sell) / ➡️ Neutral
  - Decision status: EXECUTED, EXEC FAILED, BLOCKED, Execute Signal, Watchlist
  - Strategy template name
  - Component breakdown (Technical, Structure, Macro, Sentiment)
- Color-coded data points:
  - 🟢 Green = Executed
  - 🔴 Red = Execution Failed
  - 🟠 Orange = Blocked (high score)
  - 🩵 Teal = Execute Signal
  - 🟡 Amber = Watchlist
  - 🔵 Blue = Regular reading
- Visual legend below chart
- Threshold lines at 75 (Execute) and 60 (Watchlist)

### P0: Trade Execution Logging ✅
- Fixed silent execution failures
- Added detailed Guardian check logging
- Added `blocked_high_score` status tracking
- Enhanced error handling throughout pipeline

## Guardian Risk Checks (12 total)
1. Kill switch status
2. Risk mode (HALTED/REDUCED/NORMAL)
3. Stop distance validation (min 2 pips)
4. Absolute max risk check
5. Mode-specific risk limits
6. Daily loss limit
7. Weekly drawdown limit
8. Position limit
9. Correlated exposure
10. Daily trades limit
11. Revenge trading check
12. Regime-based trading permission

## Files Modified (March 2025)
- `/app/agents/orchestrator-agent/dashboard.py` - Added Chart.js, interactive charts, hover tooltips
- `/app/agents/orchestrator-agent/lifecycle.py` - Decision logic, logging, error handling
- `/app/agents/orchestrator-agent/score_history.py` - Chart markers
- `/app/agents/execution-agent/app.py` - Safety check logging

## Backlog
- P1: Lower confluence threshold from 75 to ~70
- P2: ATR-based trailing stops
- P2: Multi-timeframe confluence weighting
- P2: Enhanced FVG usage (entry triggers)
