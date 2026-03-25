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

### P1: Range Fade Strategy Regime Rules (FIXED)
**Root Cause**: The "Range Fade" strategy had `trending` in its `invalid_regimes` list, preventing it from working in trending markets where fading pullbacks is valid.

**Fix Applied**:
- `/app/agents/strategy-agent/app.py`: Added `'trending'` to `allowed_regimes` and removed from `invalid_regimes`

### P1: Chronicle Not Showing Trades (FIXED)
**Root Cause**: MT5 positions synced by the lifecycle manager weren't being logged to Chronicle.

**Fix Applied**:
- `/app/agents/orchestrator-agent/lifecycle.py`: Now logs synced positions to Chronicle via `/api/trade/execute`
- `/app/agents/orchestrator-agent/app.py`: Added `/api/lifecycle/log-to-chronicle` endpoint to force re-log active trades

**User Action**: After pulling latest code, call `POST http://localhost:3020/api/lifecycle/log-to-chronicle` to log existing positions.

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
EXECUTE_THRESHOLD = 75   # Raised back (now achievable with strategy in confluence)
WATCHLIST_THRESHOLD = 60 
```

### Why Changed (December 2025):
- Max achievable confluence score is now 100 (was ~86)
- Strategy score from Tactician is now 25% of confluence (fixes score imbalance)
- 75 threshold ensures only high-conviction trades execute

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

## Confluence Scoring (Max 100 - NOW INCLUDES STRATEGY!)
| Component | Weight | Max Score |
|-----------|--------|-----------|
| **Strategy (NEW)** | **25%** | **25** |
| Technical | 20% | 20 |
| Structure | 15% | 15 |
| Macro | 12% | 12 |
| Sentiment | 8% | 8 |
| Regime | 10% | 10 |
| Risk/Execution | 10% | 10 |
| **TOTAL** | **100%** | **100** |

**Key Change**: Strategy score from Tactician is now the largest component (25%), fixing the imbalance where a Tactician score of 100 could result in confluence of only 54.

## Core Architecture
- 15+ Python FastAPI microservices
- PostgreSQL/TimescaleDB for market data
- Redis for pub/sub
- MT5 file bridge for execution
- Claude AI for headline sentiment

## Pending Issues (Backlog)
- P2: ATR-based trailing stops
- P2: Multi-timeframe confluence weighting
- P2: Implement Chronicle reconciliation mechanism

## Testing Checklist
- [ ] Score 68+ → Should execute
- [ ] Multiple qualified strategies → Should pick highest confluence direction
- [ ] Score history shows green circles for executed trades
- [ ] Orchestrator-Executor timeouts resolved (no more "TIMEOUT calling executor/api/..." errors)
