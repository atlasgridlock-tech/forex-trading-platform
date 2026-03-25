# Forex Multi-Agent Trading Platform PRD

## Overview
A 15-agent autonomous forex trading system that analyzes market data, generates trade setups, and executes trades based on confluence scoring.

## Latest Fix - December 2025

### P0: Orchestrator-Executor Communication Timeouts (FIXED)
**Root Cause**: The executor agent's MT5 bridge operations (`partial-close`, `modify-sl`, `close`, etc.) used synchronous `time.sleep()` polling which blocked the entire FastAPI event loop, causing all other requests to timeout.

**Fix Applied**:
- Created `read_mt5_result_async()` - async version using `asyncio.sleep()`
- Updated `/api/partial-close`, `/api/modify-sl`, `/api/close`, `/api/place-pending`, `/api/cancel-pending` to use async version
- Increased timeout for MT5 bridge operations in lifecycle.py from 10s to 35s

**Files Modified**:
- `/app/agents/execution-agent/app.py` - Added async MT5 result polling
- `/app/agents/orchestrator-agent/lifecycle.py` - Increased timeouts for MT5 operations

### P1: Malformed order_results.csv Parsing (FIXED)
**Root Cause**: Historical malformed data in `order_results.csv` could break the CSV reader.

**Fix Applied**:
- `order_bridge.py`: Added per-row exception handling to skip malformed historical rows while finding our result

**User Action**: Delete the old `order_results.csv` file one more time for a clean state.

## Critical Bug Fixes - March 2026

### 1. MT5 OrderBridge CSV Delimiter Mismatch (P0 FIXED)
**Root Cause**: Python was writing CSV with tab delimiter, but MT5's FILE_CSV reads with semicolon delimiter by default.

**Fix Applied**:
- `order_bridge.py`: Uses semicolon (`;`) delimiter, no header row
- `AgentBridge_v6.mq5` (v6.1): Uses semicolon delimiter in all FileOpen calls

**User Action**: Recompile EA, delete old `order_results.csv`

### 2. Dashboard Not Showing Positions (FIXED)
**Root Cause**: Curator and Executor were reading `positions.json` but EA writes `positions.csv` with semicolon delimiter.

**Fix Applied**:
- `/app/agents/data-agent/app.py`: Reads `positions.csv` with semicolon delimiter
- `/app/agents/execution-agent/app.py`: Reads `positions.csv` with semicolon delimiter
- `/app/agents/orchestrator-agent/app.py`: Maps EA's `type` (BUY/SELL) to dashboard's `side` (LONG/SHORT)

### 3. Executor Shows "?? @ ?" (FIXED)
**Root Cause**: Timeout/error receipts didn't include symbol and direction.

**Fix Applied**:
- Executor now includes order details even on timeout/failure for display

### 4. Inconsistent MT5 Path Environment Variable (FIXED)
**Root Cause**: Different agents used different env vars (`MT5_DATA_PATH` vs `MT5_FILES_PATH`).

**Fix Applied**:
- Executor now checks both env vars for compatibility

## Files Modified This Session
| File | Changes |
|------|---------|
| `/app/agents/shared/order_bridge.py` | Semicolon delimiter, no header, debug logging, resilient row parsing |
| `/app/agents/data-agent/app.py` | Read positions.csv with semicolon delimiter |
| `/app/agents/execution-agent/app.py` | Read positions.csv, async MT5 result polling, include order details on timeout |
| `/app/agents/orchestrator-agent/app.py` | Map BUY/SELL to LONG/SHORT for display |
| `/app/agents/orchestrator-agent/lifecycle.py` | Increased MT5 operation timeouts to 35s |
| `/app/mt5_ea/AgentBridge_v6.mq5` | v6.1 with semicolon delimiter |

## User Action Required
1. **Delete corrupted results file**:
   ```bash
   rm "/Users/triad/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/order_results.csv"
   ```

2. **Pull latest code** (Save to Github, then git pull locally)

3. **Recompile EA** (if not already done):
   - Open AgentBridge_v6.mq5 in MetaEditor
   - Press F7 to compile
   - Attach to chart, verify "v6.1" shows

4. **Restart local agents**:
   ```bash
   pkill -f "python.*start_agents"
   python start_agents.py
   ```

## Critical Parameters

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

## Pending Issues (Backlog)
- P1: "Range Fade" strategy blocked by incorrect regime rules (needs `'trending'` added to allowed_regimes)
- P2: Rebalance Tactician vs Confluence score weights
- P2: Implement Chronicle reconciliation mechanism
- P2: ATR-based trailing stops
- P2: Multi-timeframe confluence weighting

## Testing Checklist
- [ ] Score 68+ → Should execute
- [ ] Multiple qualified strategies → Should pick highest confluence direction
- [ ] Score history shows green circles for executed trades
- [ ] Orchestrator-Executor timeouts resolved (no more "TIMEOUT calling executor/api/..." errors)
