# Forex Multi-Agent Trading Platform PRD

## Overview
A 15-agent autonomous forex trading system that analyzes market data, generates trade setups, and executes trades based on confluence scoring.

## Critical Bug Fix - December 2025

### MT5 OrderBridge CSV Delimiter Mismatch (P0 FIXED)
**Root Cause**: Python was writing CSV with tab delimiter, but MT5's FILE_CSV reads with semicolon delimiter by default. This caused the EA to misparse order data.

**Fix Applied**:
1. `order_bridge.py`: Now writes with semicolon (`;`) delimiter
2. `order_bridge.py`: Removed header row (EA's header skip was buggy)
3. `AgentBridge_v6.mq5` (now v6.1): Explicitly uses semicolon delimiter in all FileOpen calls
4. Added extensive debug logging to trace file paths and content

**Files Changed**:
- `/app/agents/shared/order_bridge.py`
- `/app/mt5_ea/AgentBridge_v6.mq5`

**User Action Required**: 
- Recompile AgentBridge_v6.mq5 in MetaEditor
- Attach the new EA to a chart in MT5
- Verify the EA shows "v6.1" in the Experts tab

## Critical Parameters (March 2026 Update)

### Execution Thresholds
```python
EXECUTE_THRESHOLD = 68   # Lowered from 75 - March 2026
WATCHLIST_THRESHOLD = 55 # Lowered from 60 - March 2026
```

### Why Changed:
- Max achievable confluence score is ~86, not 100
- 75 threshold was too restrictive - many good setups scoring 68-74
- System was picking wrong direction (first qualified vs highest confluence)

## Key Bug Fixes (March 2026)

### 1. Direction Selection Bug
**Problem:** System picked first qualified strategy direction, even if opposite direction had higher confluence
**Example:** Range Fade (LONG) = 70, Failed Breakout (SHORT) = 79 → System picked LONG!
**Fix:** Now checks confluence for ALL qualified strategies and picks highest

### 2. Score Threshold Bug  
**Problem:** Threshold 75 was nearly impossible to reach (max ~86)
**Fix:** Lowered to 68

### 3. Silent Execution Failures
**Problem:** `post_agent` swallowed all errors with bare `except: pass`
**Fix:** Added comprehensive error logging

## Confluence Scoring (Max ~86)
| Component | Max Score |
|-----------|-----------|
| Technical | 25 |
| Structure | 15 |
| Macro | 15 |
| Sentiment | 10 |
| Regime | 10 |
| Risk/Execution | 11 |
| **TOTAL** | **~86** |

## Core Architecture
- 15+ Python FastAPI microservices
- PostgreSQL/TimescaleDB for market data
- Redis for pub/sub
- MT5 file bridge for execution
- Claude AI for headline sentiment

## Files Modified
- `/app/agents/orchestrator-agent/lifecycle.py`
  - Lowered thresholds (68/55)
  - Smart direction selection (picks highest confluence)
  - Enhanced logging

- `/app/agents/shared/order_bridge.py`
  - Fixed CSV delimiter to semicolon (;)
  - Removed header row (EA header parsing was buggy)
  - Added debug logging for file paths and content

- `/app/mt5_ea/AgentBridge_v6.mq5` (now v6.1)
  - Fixed CSV delimiter to semicolon in all FileOpen calls
  - Added logging for order processing
  - User must recompile and redeploy

## Testing Checklist
- [ ] Score 68+ → Should execute
- [ ] Multiple qualified strategies → Should pick highest confluence direction
- [ ] Score history shows green circles for executed trades

## Backlog
- P2: ATR-based trailing stops
- P2: Multi-timeframe confluence weighting
- P2: Consider raising threshold to 70 if too many trades
