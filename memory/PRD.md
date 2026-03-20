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
- **Risk Agent (Guardian)**: Position sizing, risk checks
- **Portfolio Agent (Balancer)**: Exposure management
- **Execution Agent (Executor)**: Order execution via MT5
- **Journal Agent (Chronicle)**: Trade journaling with charts
- **Analytics Agent (Insight)**: Performance attribution
- **Governance Agent (Arbiter)**: Strategy improvement

## Key Features Implemented

### Confluence Scoring System
- Multi-factor scoring: Technical (25pts), Structure (15pts), Macro (15pts), Sentiment (10pts), Regime (10pts), Risk/Execution (11pts)
- Execute threshold: 75+
- Watchlist threshold: 60-74
- Blocked: <60

### Score History Tracking (Completed: March 2025)
- Historical confluence score tracking per symbol
- Visual charts with threshold lines
- Decision markers: execute signals, actual executions, failed executions
- Multi-symbol comparison charts
- Dashboard UI integration with modal popups

### Chronicle v2.0 Trade Journaling (Completed: March 2025)
- Auto-generated trade journals on execution
- Candlestick charts with entry/SL/TP levels (mplfinance)
- Confluence breakdown summaries (matplotlib)
- JSON metadata with full trade context
- Trade-specific folder storage

### Execution Pipeline Logging (Completed: March 2025)
- Comprehensive error logging in lifecycle.py
- Detailed rejection reason tracking
- Visual markers for failed executions on score charts
- Executor agent trace logging for safety checks

## Current Issues

### P0: Trade Execution Silent Failures (IN PROGRESS)
- **Symptom**: Score hits 75+ but no trade executes
- **Root Cause**: Error logging was missing
- **Status**: Logging added, awaiting user verification

### P1: Score Chart Hover Info (NOT STARTED)
- Add buy/sell indication on chart hover tooltips

## Backlog
- P1: Lower confluence threshold from 75 to ~70
- P2: ATR-based trailing stops
- P2: Multi-timeframe confluence weighting
- P2: Enhanced FVG usage (entry triggers)

## Technical Stack
- Python FastAPI microservices
- Docker Compose orchestration
- MT5 file bridge for execution
- matplotlib/mplfinance for charting
- httpx for inter-service communication

## Files Modified (March 2025)
- `/app/agents/orchestrator-agent/lifecycle.py` - Error logging, execution tracking
- `/app/agents/orchestrator-agent/score_history.py` - exec_failed markers
- `/app/agents/execution-agent/app.py` - Safety check logging
- `/app/agents/journal-agent/chart_generator.py` - Trade chart generation
- `/app/agents/journal-agent/app.py` - Chronicle v2.0 endpoints
- `/app/agents/strategy-agent/app.py` - Regime tuning, stop calculation
- `/app/agents/risk-agent/app.py` - Min stop-loss adjustment
