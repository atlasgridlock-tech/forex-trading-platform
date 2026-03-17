# Curator - Data Agent

**Port:** 3021  
**Role:** Central Data Hub & Quality Control  
**Status:** Core Agent

---

## Overview

Curator is the central data hub for the trading platform. It ingests, validates, and distributes market data from MT5 or simulated feeds. All other agents rely on Curator for price data, spreads, and quality metrics.

## Key Responsibilities

1. **Ingest Data** - Receive tick and candle data from MT5 bridge
2. **Validate Quality** - Check completeness, freshness, consistency
3. **Store & Serve** - Maintain in-memory cache of market data
4. **Calculate Quality Scores** - Per-symbol tradability assessment
5. **Alert on Issues** - Notify when data quality degrades

## API Endpoints

### Market Data

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/market` | All symbols current prices |
| GET | `/api/market/{symbol}` | Single symbol price data |
| GET | `/api/candles/{symbol}/{timeframe}` | OHLCV candle data |
| GET | `/api/spread/{symbol}` | Current spread |

### Quality Metrics

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/quality` | Quality scores all symbols |
| GET | `/api/quality/{symbol}` | Single symbol quality |
| GET | `/api/status` | Agent status and health |

### Live Data Ingestion

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/market-data/update` | Receive tick data |
| POST | `/api/candles/update` | Receive candle data |
| GET | `/api/live/status` | Live feed connection status |

## Data Quality Scoring

Quality score is calculated per symbol:

```
Quality Score = (
    Completeness × 0.30 +    # % expected candles present
    Freshness × 0.40 +       # Time since last update
    Consistency × 0.30       # Valid OHLC relationships
)

Score > 80: Excellent - Full trading allowed
Score 60-80: Good - Trading with caution
Score < 60: Poor - May block trading
```

## Data Sources

### From MT5 Bridge

| File | Contents | Refresh |
|------|----------|---------|
| `market_data.csv` | Bid, Ask, Spread | 5 seconds |
| `candle_data.csv` | OHLCV by timeframe | 5 seconds |

### File Format (candle_data.csv)

```
Symbol,Timeframe,DateTime,Open,High,Low,Close,Volume
EURUSD.s,M30,2025.12.15 22:00:00,1.0855,1.0862,1.0848,1.0858,4521
```

## Usage Examples

### Get All Market Data

```bash
curl http://localhost:3021/api/market
```

Response:
```json
{
  "EURUSD": {
    "symbol": "EURUSD",
    "bid": 1.0855,
    "ask": 1.0856,
    "spread": 1.0,
    "timestamp": "2025-12-15T22:30:00Z"
  },
  "GBPUSD": { ... }
}
```

### Get Candles

```bash
curl http://localhost:3021/api/candles/EURUSD/H1
```

Response:
```json
{
  "symbol": "EURUSD",
  "timeframe": "H1",
  "count": 500,
  "candles": [
    {
      "time": "2025-12-15T22:00:00",
      "open": 1.0855,
      "high": 1.0862,
      "low": 1.0848,
      "close": 1.0858,
      "volume": 4521
    }
  ]
}
```

### Get Quality Scores

```bash
curl http://localhost:3021/api/quality
```

Response:
```json
{
  "EURUSD": {
    "overall": 94,
    "completeness": 100,
    "freshness": 98,
    "consistency": 85,
    "tradeable": true,
    "status": "excellent"
  }
}
```

### Send Live Data (from bridge)

```bash
curl -X POST http://localhost:3021/api/market-data/update \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "EURUSD",
    "bid": 1.0855,
    "ask": 1.0856,
    "timestamp": "2025-12-15T22:30:00Z"
  }'
```

## Supported Symbols

```
EURUSD  GBPUSD  USDJPY  GBPJPY  USDCHF
USDCAD  EURAUD  AUDNZD  AUDUSD
```

## Supported Timeframes

```
M5   M15  M30  H1   H4   D1   W1
```

## Integration Points

### Data Sources

- **MT5 Bridge** - Real-time price data
- **Simulated Feed** - Test data (simulated_feed.py)

### Consumers

- **All Analysis Agents** - Request candle data
- **Nexus** - Requests spread for gate checks
- **Executor** - Verifies prices before execution

## Configuration

Environment variables in `/app/agents/.env`:

```bash
MT5_DATA_PATH=/app/mt5_data
SYMBOL_SUFFIX=.s
DATA_STALE_THRESHOLD=60  # seconds
MIN_QUALITY_SCORE=60
```

## Alerts

Curator sends alerts to Nexus when:

- Data becomes stale (> 60 seconds old)
- Quality score drops below threshold
- Connection to data source lost
- Spread exceeds normal range

---

*Curator - The data foundation of the platform*
