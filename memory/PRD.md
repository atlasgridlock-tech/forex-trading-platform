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

## Critical Issues Fixed (March 2025)

### P0: Trade Execution Silent Failures
**Problem**: Score hit 79 but no trade executed. Teal "execute" markers appeared but no execution attempted.

**Root Cause**: The `stage_trade_decision` logic checked screening results BEFORE allowing score-based execution. If ANY screening failed (e.g., Guardian denied), the high score was ignored.

**Fix Applied**:
1. Rewrote decision logic to properly separate score decisions from screening blocks
2. Added `blocked_high_score` status when score >= 75 but screenings failed
3. Added detailed Guardian check logging (shows which of 12 checks failed)
4. Added exception handling around order routing
5. Added orange diamond marker (◆) on charts for blocked high-score setups

## Chart Markers
- Green circle (●) = Trade successfully executed
- Red X (✗) = Execution FAILED
- Orange diamond (◆) = Blocked despite high score (NEW!)
- Teal triangle (▲) = Execute signal generated
- Orange square (■) = Watchlist

## Files Modified (March 2025)
- `/app/agents/orchestrator-agent/lifecycle.py` - Decision logic, logging, error handling
- `/app/agents/orchestrator-agent/score_history.py` - Chart markers
- `/app/agents/execution-agent/app.py` - Safety check logging

## Testing Checklist
- [ ] High confluence score (75+) with ALL screenings passing → Should execute
- [ ] High confluence score (75+) with Guardian denial → Should show orange diamond + detailed reason
- [ ] Order routing failure → Should show red X + error details
- [ ] Successful execution → Should show green circle

## Backlog
- P1: Add hover info to score charts (buy/sell indication)
- P1: Lower confluence threshold from 75 to ~70
- P2: ATR-based trailing stops
- P2: Multi-timeframe confluence weighting
