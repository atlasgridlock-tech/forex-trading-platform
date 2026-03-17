# Executor - Execution Agent

**Port:** 3019  
**Role:** Trade Execution & Lifecycle Management  
**Status:** Core Agent

---

## Overview

Executor handles all trade execution for the platform. It performs final safety checks, executes trades in paper or live mode, and manages position lifecycle including partial take-profits and trailing stops.

## Key Responsibilities

1. **Execute Trades** - Paper or live execution via MT5 bridge
2. **Safety Checks** - Verify SL, check duplicates, rate limits
3. **Position Management** - Track open positions, P&L
4. **Lifecycle Management** - Partial TPs, break-even, trailing stops
5. **Notify Downstream** - Alert Portfolio and Chronicle

## API Endpoints

### Execution

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/execute` | Execute a trade |
| POST | `/api/close/{order_id}` | Close a position |
| POST | `/api/close-all` | Emergency close all |
| GET | `/api/status` | Agent status |

### Position Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/positions` | All open positions |
| GET | `/api/position/{order_id}` | Single position |
| PUT | `/api/position/{order_id}/sl` | Update stop loss |
| PUT | `/api/position/{order_id}/tp` | Update take profit |

### Lifecycle Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/lifecycle/update-price` | Update position with current price |
| GET | `/api/lifecycle/positions` | Positions with lifecycle state |
| GET | `/api/lifecycle/position/{order_id}` | Single position lifecycle |
| POST | `/api/lifecycle/simulate` | Simulate price movement (testing) |

## Execution Modes

| Mode | Description | Real Money |
|------|-------------|------------|
| **paper** | Simulated fills, tracks P&L | No |
| **shadow** | Logs signals, paper execution | No |
| **guarded_live** | Real MT5 execution with all checks | Yes |

## Safety Checks

Before every execution:

```
Pre-Execution Checks:
├─ 1. Stop loss defined? (MANDATORY)
├─ 2. Duplicate check (reject same signal)
├─ 3. Martingale check (reject size increase after loss)
├─ 4. Averaging down check (reject adding to loser)
├─ 5. Rate limit check (max 3/hour/pair)
├─ 6. Guardian approval (final risk check)
└─ 7. Portfolio exposure check
```

## Position Lifecycle

### States

```
OPEN
  │
  ├─ 10 pips profit ──────────> BREAKEVEN
  │                             (SL moved to entry + 1 pip)
  │                                │
  │                                ▼
  ├─ Price hits TP1 ──────────> TP1_HIT
  │                             (Close 33% of position)
  │                                │
  │                                ▼
  ├─ Price hits TP2 ──────────> TP2_HIT
  │                             (Close 50% of remaining)
  │                                │
  │                                ▼
  └─ Price hits TP3/SL ───────> CLOSED
                                (Close 100%)
```

### Features

- **Partial Take-Profits**: Close 33% at TP1, 50% at TP2, 100% at TP3
- **Break-Even**: Move SL to entry + 1 pip after 10 pips profit
- **Trailing Stop**: Trail SL 15 pips behind after 20 pips profit

## Usage Examples

### Execute Paper Trade

```bash
curl -X POST http://localhost:3019/api/execute \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "EURUSD",
    "direction": "long",
    "lot_size": 0.10,
    "entry_price": 1.0850,
    "stop_loss": 1.0820,
    "take_profit": 1.0880,
    "take_profit_2": 1.0910,
    "take_profit_3": 1.0940,
    "trailing_stop_pips": 20
  }'
```

Response:
```json
{
  "status": "EXECUTED",
  "order_id": "PAPER-1702684200-EURUSD",
  "symbol": "EURUSD",
  "direction": "long",
  "lot_size": 0.10,
  "fill_price": 1.0850,
  "stop_loss": 1.0820,
  "take_profit": 1.0880,
  "mode": "paper",
  "health_score": 85
}
```

### Get Positions with Lifecycle

```bash
curl http://localhost:3019/api/lifecycle/positions
```

Response:
```json
{
  "positions": [
    {
      "order_id": "PAPER-1702684200-EURUSD",
      "symbol": "EURUSD",
      "direction": "long",
      "entry_price": 1.0850,
      "current_price": 1.0875,
      "unrealized_pnl_pips": 25,
      "lifecycle_state": "BREAKEVEN",
      "stop_loss": 1.0851,
      "original_lot_size": 0.10,
      "current_lot_size": 0.10,
      "trailing_active": true
    }
  ]
}
```

### Simulate Price Movement (Testing)

```bash
curl -X POST http://localhost:3019/api/lifecycle/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "PAPER-1702684200-EURUSD",
    "prices": [1.0860, 1.0880, 1.0910, 1.0940]
  }'
```

### Close Position

```bash
curl -X POST http://localhost:3019/api/close/PAPER-1702684200-EURUSD \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "Manual close",
    "close_price": 1.0875
  }'
```

## Order Request Schema

```json
{
  "symbol": "EURUSD",           // Required
  "direction": "long",          // Required: "long" or "short"
  "lot_size": 0.10,             // Required
  "entry_price": 1.0850,        // Optional: market if not set
  "stop_loss": 1.0820,          // REQUIRED: Mandatory
  "take_profit": 1.0880,        // Optional: TP1
  "take_profit_2": 1.0910,      // Optional: TP2
  "take_profit_3": 1.0940,      // Optional: TP3
  "trailing_stop_pips": 20,     // Optional: Trailing activation
  "strategy_id": "PULLBACK_TREND", // Optional: For logging
  "confidence": 0.78            // Optional: From Nexus
}
```

## Integration Points

### Receives From

- **Nexus (3020)** - Approved trade orders
- **Guardian (3013)** - Risk parameters, position sizing

### Notifies

- **Portfolio (3018)** - New positions, closures
- **Chronicle (3022)** - Execution logs
- **Nexus (3020)** - Execution status

## Configuration

```yaml
# Execution settings
default_mode: paper
live_mode_enabled: false
max_orders_per_hour: 10
max_orders_per_pair_per_hour: 3

# Lifecycle settings
breakeven_trigger_pips: 10
breakeven_offset_pips: 1
trailing_activation_pips: 20
trailing_distance_pips: 15
tp1_close_percent: 0.33
tp2_close_percent: 0.50
```

## Paper vs Live Mode

### Paper Mode (Default)

- Fills at requested price instantly
- Tracks P&L in memory
- Full lifecycle management
- No real money risk

### Live Mode (Requires Promotion)

- Writes commands to MT5 bridge
- Waits for real fills
- Handles partial fills
- Real money at risk

To enable live mode, all promotion gates must pass:
- 100+ paper trades
- 30+ days paper trading
- Profit factor ≥ 1.3
- Max drawdown ≤ 5%
- Manual approval

---

*Executor - Where decisions become trades*
