# Forex Trading Platform - Agent Data Reference
## Complete Guide to Data Sources, Processing, and Interpretation

**Version:** 1.0  
**Generated:** March 13, 2026  
**System Status:** 100% Real Data

---

# Table of Contents

1. [System Architecture Overview](#system-architecture-overview)
2. [Data Flow Diagram](#data-flow-diagram)
3. [Agent Reference](#agent-reference)
   - [Curator (Data Agent)](#1-curator---data-agent)
   - [Sentinel (News/Event Agent)](#2-sentinel---newsevent-agent)
   - [Oracle (Macro Agent)](#3-oracle---macro-agent)
   - [Pulse (Sentiment Agent)](#4-pulse---sentiment-agent)
   - [Atlas Jr. (Technical Agent)](#5-atlas-jr---technical-agent)
   - [Architect (Structure Agent)](#6-architect---structure-agent)
   - [Compass (Regime Agent)](#7-compass---regime-agent)
   - [Tactician (Strategy Agent)](#8-tactician---strategy-agent)
   - [Guardian (Risk Agent)](#9-guardian---risk-agent)
   - [Balancer (Portfolio Agent)](#10-balancer---portfolio-agent)
   - [Executor (Execution Agent)](#11-executor---execution-agent)
   - [Chronicle (Journal Agent)](#12-chronicle---journal-agent)
   - [Insight (Analytics Agent)](#13-insight---analytics-agent)
   - [Arbiter (Governance Agent)](#14-arbiter---governance-agent)
   - [Nexus (Orchestrator)](#15-nexus---orchestrator)
4. [Data Sources Summary](#data-sources-summary)
5. [Refresh Rates](#refresh-rates)
6. [Cost Analysis](#cost-analysis)

---

# System Architecture Overview

The trading platform consists of 15 specialized agents, each responsible for a specific domain of analysis. Data flows from external sources (MT5, APIs, RSS feeds) through the agents, culminating in trading decisions made by the Orchestrator (Nexus).

```
┌─────────────────────────────────────────────────────────────────┐
│                     EXTERNAL DATA SOURCES                        │
├─────────────┬─────────────┬─────────────┬─────────────┬─────────┤
│    MT5      │  Myfxbook   │    FRED     │    CFTC     │   RSS   │
│  (Prices)   │ (Sentiment) │  (Macro)    │   (COT)     │ (News)  │
└──────┬──────┴──────┬──────┴──────┬──────┴──────┬──────┴────┬────┘
       │             │             │             │           │
       ▼             ▼             ▼             ▼           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      DATA COLLECTION LAYER                       │
├─────────────┬─────────────┬─────────────┬─────────────┬─────────┤
│  Curator    │   Pulse     │   Oracle    │   Pulse     │Sentinel │
│  Port 3021  │  Port 3015  │  Port 3011  │  Port 3015  │Port 3010│
└──────┬──────┴──────┬──────┴──────┬──────┴──────┬──────┴────┬────┘
       │             │             │             │           │
       ▼             ▼             ▼             ▼           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      ANALYSIS LAYER                              │
├─────────────┬─────────────┬─────────────┬─────────────┬─────────┤
│  Atlas Jr.  │  Architect  │   Compass   │  Tactician  │Guardian │
│  Port 3012  │  Port 3014  │  Port 3016  │  Port 3017  │Port 3013│
└──────┬──────┴──────┬──────┴──────┬──────┴──────┬──────┴────┬────┘
       │             │             │             │           │
       └─────────────┴──────┬──────┴─────────────┴───────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    DECISION & EXECUTION LAYER                    │
├───────────────────┬───────────────────┬─────────────────────────┤
│       Nexus       │     Balancer      │       Executor          │
│    Port 3020      │    Port 3018      │      Port 3019          │
│   (Orchestrator)  │   (Portfolio)     │    (Order Exec)         │
└───────────────────┴───────────────────┴─────────────────────────┘
```

---

# Agent Reference

## 1. Curator - Data Agent

**Port:** 3021  
**Role:** Central data hub - ingests, validates, and distributes market data

### Data Sources
| Source | File/API | Refresh Rate |
|--------|----------|--------------|
| MT5 Price Data | `candle_data.csv` | 5 seconds |
| MT5 Market Data | `market_data.csv` | 5 seconds |
| MT5 Bridge Status | `bridge_status.json` | 5 seconds |
| MT5 Account Info | `account_data.json` | 5 seconds |

### Data Processing
```
MT5 AgentBridge EA
        │
        ▼ (writes every 5 sec)
┌─────────────────────┐
│  candle_data.csv    │ ← 237,655 lines, 31,500 candles
│  (18MB)             │   9 pairs × 7 timeframes × 500 bars
└─────────┬───────────┘
          │
          ▼ (parsed)
┌─────────────────────┐
│  Curator Memory     │
│  - OHLCV by symbol  │
│  - By timeframe     │
│  - Quality scores   │
└─────────┬───────────┘
          │
          ▼ (API)
    /api/candles/{symbol}/{timeframe}
    /api/market
    /api/quality
```

### Quality Metrics Calculated
- **Completeness:** % of expected candles present
- **Freshness:** Time since last update (< 60s = good)
- **Consistency:** No gaps, valid OHLC relationships
- **Overall Score:** Weighted average (0-100)

### Output Format
```json
{
  "symbol": "EURUSD",
  "timeframe": "H1",
  "candles": [
    {"time": "2026-03-13T22:00:00", "open": 1.0855, "high": 1.0862, "low": 1.0848, "close": 1.0858, "volume": 4521}
  ],
  "quality": {"score": 95, "freshness": "2s ago", "completeness": 100}
}
```

---

## 2. Sentinel - News/Event Agent

**Port:** 3010  
**Role:** Monitors economic calendar and news headlines for event risk

### Data Sources
| Source | API/Feed | Refresh Rate |
|--------|----------|--------------|
| Economic Calendar | MT5 MQL5 Calendar | 5 minutes |
| News Headlines | FXStreet RSS | 5 minutes |
| News Headlines | ForexLive RSS | 5 minutes |

### Data Processing

#### Economic Calendar
```
MT5 MQL5 Calendar API
        │
        ▼ (EA exports)
┌─────────────────────┐
│  calendar_data.json │ ← 50 events, next 7 days
│  (14KB)             │   Filtered: USD,EUR,GBP,JPY,CHF,CAD,AUD,NZD
└─────────┬───────────┘
          │
          ▼ (parsed)
┌─────────────────────┐
│  Event Analysis     │
│  - Impact level     │ ← HIGH/MEDIUM/LOW
│  - Time to event    │
│  - Currency affected│
│  - Blocked windows  │ ← No trading 30min before/after HIGH
└─────────────────────┘
```

#### News Headlines (AI-Powered)
```
RSS Feeds (FXStreet + ForexLive)
        │
        ▼ (fetch every 5 min)
┌─────────────────────┐
│  50+ Headlines      │
│  - Title            │
│  - Timestamp        │
│  - Source           │
└─────────┬───────────┘
          │
          ▼ (Claude Sonnet 4)
┌─────────────────────┐
│  AI Classification  │
│  - RISK_OFF (6)     │ ← War, crisis, tensions
│  - RISK_ON (3)      │ ← Peace, optimism
│  - NEUTRAL (11)     │ ← No directional impact
└─────────────────────┘
```

### Risk Assessment Output
```json
{
  "event_risk": "MEDIUM",
  "next_high_impact": {"event": "US CPI", "currency": "USD", "in_minutes": 180},
  "blocked_windows": [{"start": "14:00", "end": "15:00", "event": "FOMC"}],
  "news_sentiment": {"risk_off_count": 6, "risk_on_count": 3},
  "tradeable": true
}
```

---

## 3. Oracle - Macro Agent

**Port:** 3011  
**Role:** Analyzes macroeconomic fundamentals for currency bias

### Data Sources
| Source | API | Refresh Rate |
|--------|-----|--------------|
| US Data | FRED API | 1 hour |
| EU Data | FRED API | 1 hour |
| UK Data | FRED API | 1 hour |
| JP Data | FRED API | 1 hour |

### FRED Series Used
```
┌──────────────────────────────────────────────────────────────┐
│  UNITED STATES                                                │
│  - FEDFUNDS: Federal Funds Rate (3.64%)                      │
│  - CPIAUCSL: CPI All Urban Consumers                         │
│  - CPILFESL: Core CPI (ex Food & Energy)                     │
│  - GDP: Gross Domestic Product                               │
│  - UNRATE: Unemployment Rate (4.4%)                          │
│  - CES0500000003: Average Hourly Earnings                    │
├──────────────────────────────────────────────────────────────┤
│  EUROZONE                                                     │
│  - ECBMRRFR: ECB Main Refinancing Rate                       │
│  - CP0000EZ19M086NEST: Eurozone HICP                         │
│  - LRHUTTTTEZM156S: Eurozone Unemployment                    │
├──────────────────────────────────────────────────────────────┤
│  UNITED KINGDOM                                               │
│  - BOERUKM: Bank of England Rate                             │
│  - GBRCPIALLMINMEI: UK CPI                                   │
│  - LMUNRRTTGBM156S: UK Unemployment                          │
├──────────────────────────────────────────────────────────────┤
│  JAPAN                                                        │
│  - IRSTCI01JPM156N: BoJ Policy Rate                          │
│  - JPNCPIALLMINMEI: Japan CPI                                │
│  - LRUNTTTTJPM156S: Japan Unemployment                       │
└──────────────────────────────────────────────────────────────┘
```

### Interpretation Logic
```
For each currency pair (e.g., EURUSD):
        │
        ▼
┌─────────────────────┐
│  Compare:           │
│  - Interest rates   │ ← Higher rate = currency strength
│  - Inflation trends │ ← Rising = hawkish central bank
│  - Employment       │ ← Strong = currency support
│  - GDP growth       │ ← Growing = currency demand
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Generate Bias:     │
│  - BULLISH (USD)    │ ← If US data stronger
│  - BEARISH (USD)    │ ← If counter data stronger
│  - NEUTRAL          │ ← Mixed signals
└─────────────────────┘
```

### Output Format
```json
{
  "EURUSD": {
    "bias": "bearish",
    "score": 35,
    "reasoning": "Fed funds 3.64% vs ECB 2.50%, US employment stronger",
    "rate_differential": 1.14,
    "inflation_trend": "USD hawkish, EUR dovish"
  }
}
```

---

## 4. Pulse - Sentiment Agent

**Port:** 3015  
**Role:** Tracks market positioning and crowd sentiment

### Data Sources
| Source | API | Refresh Rate |
|--------|-----|--------------|
| Retail Sentiment | Myfxbook API | 5 minutes |
| COT Positioning | CFTC Weekly Report | 24 hours |
| News Tone | RSS + Claude AI | 5 minutes |

### Retail Sentiment (Myfxbook)
```
Myfxbook API Login
        │
        ▼
┌─────────────────────┐
│  Community Outlook  │
│  - Long %           │
│  - Short %          │
│  - Long/Short ratio │
└─────────┬───────────┘
          │
          ▼ (interpret)
┌─────────────────────┐
│  Contrarian Signal: │
│  > 70% one side     │ ← OVERCROWDED (fade)
│  60-70%             │ ← ELEVATED (caution)
│  40-60%             │ ← BALANCED (neutral)
│  < 40%              │ ← OPPOSITE CROWD (confirm)
└─────────────────────┘
```

### COT Data (CFTC)
```
CFTC Weekly Report (deafut.txt)
        │
        ▼ (parse)
┌─────────────────────┐
│  Commitment of      │
│  Traders:           │
│  - Speculators      │ ← "Smart money" direction
│  - Commercials      │ ← Hedgers (contrarian)
│  - Net position     │
└─────────┬───────────┘
          │
          ▼ (interpret)
┌─────────────────────┐
│  EUR: Specs +105K   │ ← Large long = BULLISH EUR
│  GBP: Specs -84K    │ ← Large short = BEARISH GBP
│  JPY: Specs -41K    │ ← Short = BEARISH JPY
└─────────────────────┘
```

### News Tone Analysis (AI)
```
Headlines (50+)
        │
        ▼ (Claude Sonnet 4)
┌─────────────────────┐
│  Batch Analysis     │
│  Top 20 headlines   │
│  $0.001 per batch   │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Classifications:   │
│  - RISK_OFF: 6      │ ← Safe havens bid
│  - RISK_ON: 3       │ ← Risk currencies bid
│  - NEUTRAL: 11      │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Currency Impact:   │
│  RISK_OFF →         │
│    USD ↑ JPY ↑ CHF ↑│
│    AUD ↓ NZD ↓ CAD ↓│
│  RISK_ON →          │
│    USD ↓ JPY ↓ CHF ↓│
│    AUD ↑ NZD ↑ CAD ↑│
└─────────────────────┘
```

### Output Format
```json
{
  "EURUSD": {
    "retail": {"long_pct": 72, "short_pct": 28, "signal": "OVERCROWDED_LONG"},
    "cot": {"specs_net": 105144, "signal": "BULLISH"},
    "news_tone": "bearish",
    "overall_sentiment": 45
  }
}
```

---

## 5. Atlas Jr. - Technical Agent

**Port:** 3012  
**Role:** Calculates technical indicators and identifies patterns

### Data Sources
| Source | Via | Data Used |
|--------|-----|-----------|
| Price Data | Curator API | OHLCV candles |

### Indicators Calculated
```
┌──────────────────────────────────────────────────────────────┐
│  TREND INDICATORS                                             │
│  - EMA 8, 21, 50, 200                                        │
│  - SMA 20, 50, 200                                           │
│  - ADX (trend strength)                                      │
├──────────────────────────────────────────────────────────────┤
│  MOMENTUM INDICATORS                                          │
│  - RSI (14)                                                  │
│  - MACD (12, 26, 9)                                          │
│  - Stochastic (14, 3, 3)                                     │
├──────────────────────────────────────────────────────────────┤
│  VOLATILITY INDICATORS                                        │
│  - ATR (14)                                                  │
│  - Bollinger Bands (20, 2)                                   │
├──────────────────────────────────────────────────────────────┤
│  VOLUME INDICATORS                                            │
│  - Volume SMA                                                │
│  - Volume relative to average                                │
└──────────────────────────────────────────────────────────────┘
```

### Multi-Timeframe Analysis
```
For each pair, analyze:
        │
        ├── M15 (Entry timing)
        ├── H1 (Intraday direction)
        ├── H4 (Swing direction)
        └── D1 (Major trend)
        │
        ▼
┌─────────────────────┐
│  Trend Alignment:   │
│  A = All aligned    │
│  B = 3/4 aligned    │
│  C = 2/4 aligned    │
│  D = Mixed          │
│  F = Counter-trend  │
└─────────────────────┘
```

### Output Format
```json
{
  "EURUSD": {
    "trend_grade": "B",
    "indicators": {
      "ema_8": 1.0855, "ema_21": 1.0842, "ema_50": 1.0825,
      "rsi_14": 58.5,
      "macd": {"line": 0.0012, "signal": 0.0008, "histogram": 0.0004},
      "atr_14": 0.0045
    },
    "signals": ["EMA_BULLISH_CROSS", "RSI_NEUTRAL", "MACD_BULLISH"],
    "bias": "bullish",
    "strength": 65
  }
}
```

---

## 6. Architect - Structure Agent

**Port:** 3014  
**Role:** Analyzes market structure - swing highs/lows, trends, key levels

### Data Processing
```
H1/H4 Candle Data (from Curator)
        │
        ▼
┌─────────────────────┐
│  Swing Detection    │
│  - Lookback: 3 bars │
│  - Find HH, HL, LH, │
│    LL patterns      │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Structure State:   │
│  - BULLISH: HH + HL │
│  - BEARISH: LH + LL │
│  - RANGING: Mixed   │
│  - BREAKOUT: Break  │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Key Levels:        │
│  - Recent swing H   │
│  - Recent swing L   │
│  - Structure break  │
└─────────────────────┘
```

### Structure Quality Score
```
Quality = f(
    clarity,      # How clear is the structure?
    recency,      # How recent are the swings?
    respect,      # Are levels being respected?
    alignment     # Does MTF structure agree?
)
```

### Output Format
```json
{
  "EURUSD": {
    "structure": "BULLISH",
    "quality": 85,
    "last_swing_high": {"price": 1.0892, "time": "2026-03-13T18:00"},
    "last_swing_low": {"price": 1.0825, "time": "2026-03-12T14:00"},
    "key_levels": [1.0900, 1.0850, 1.0800],
    "bias": "bullish"
  }
}
```

---

## 7. Compass - Regime Agent

**Port:** 3016  
**Role:** Identifies current market regime and session context

### Regime Classification
```
┌──────────────────────────────────────────────────────────────┐
│  REGIME TYPES                                                 │
├──────────────────────────────────────────────────────────────┤
│  TRENDING_BULLISH  │ Strong uptrend, clear HH/HL             │
│  TRENDING_BEARISH  │ Strong downtrend, clear LH/LL           │
│  RANGING           │ Sideways, between support/resistance    │
│  VOLATILE          │ High ATR, erratic moves                 │
│  BREAKOUT          │ Breaking out of range                   │
│  LOW_VOLATILITY    │ Compressed, expecting expansion         │
└──────────────────────────────────────────────────────────────┘
```

### Session Analysis
```
┌──────────────────────────────────────────────────────────────┐
│  TRADING SESSIONS (UTC)                                       │
├──────────────────────────────────────────────────────────────┤
│  ASIAN    │ 00:00 - 08:00 │ JPY, AUD, NZD active             │
│  LONDON   │ 08:00 - 16:00 │ EUR, GBP active, highest volume  │
│  NEW_YORK │ 13:00 - 21:00 │ USD active, overlaps London      │
│  OVERLAP  │ 13:00 - 16:00 │ Best liquidity                   │
└──────────────────────────────────────────────────────────────┘
```

### Output Format
```json
{
  "EURUSD": {
    "regime": "TRENDING_BULLISH",
    "confidence": 75,
    "session": "NEW_YORK",
    "session_bias": "neutral",
    "volatility": "normal",
    "tradeable": true
  }
}
```

---

## 8. Tactician - Strategy Agent

**Port:** 3017  
**Role:** Validates if conditions meet strategy rules

### Strategy Checks (8 Hard Gates)
```
┌──────────────────────────────────────────────────────────────┐
│  GATE              │  CHECK                    │ REQUIREMENT │
├──────────────────────────────────────────────────────────────┤
│  1. Event Risk     │  No HIGH impact < 30min   │  PASS       │
│  2. Spread         │  Current ≤ max allowed    │  ≤ 2.0 pips │
│  3. Stop Defined   │  Valid stop loss set      │  MANDATORY  │
│  4. Regime Match   │  Regime allows strategy   │  PASS       │
│  5. Data Quality   │  Curator quality score    │  ≥ 60%      │
│  6. Portfolio Exp  │  Not over-exposed         │  PASS       │
│  7. Guardian Mode  │  Guardian not blocking    │  PASS       │
│  8. Model Version  │  Using approved model     │  PASS       │
└──────────────────────────────────────────────────────────────┘
```

### Strategy Validation
```
For each trade signal:
        │
        ▼
┌─────────────────────┐
│  Run all 8 gates    │
│  ALL must pass      │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Check soft rules:  │
│  - Trend grade ≥ B  │
│  - Structure clear  │
│  - Sentiment ok     │
│  - Macro aligned    │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Strategy Score:    │
│  0-100 based on     │
│  rule compliance    │
└─────────────────────┘
```

### Output Format
```json
{
  "EURUSD": {
    "gates_passed": 6,
    "gates_total": 8,
    "gates": {
      "event_risk": {"passed": true, "message": "No high impact events"},
      "spread": {"passed": true, "message": "Spread 1.0 ≤ 2.0"},
      "stop_defined": {"passed": false, "message": "No stop loss defined"},
      "regime_match": {"passed": true, "message": "Regime allows trend"}
    },
    "strategy_score": 72,
    "approved": false,
    "reason": "Stop loss required"
  }
}
```

---

## 9. Guardian - Risk Agent

**Port:** 3013  
**Role:** Final risk approval gate - has ABSOLUTE VETO power

### Risk Checks
```
┌──────────────────────────────────────────────────────────────┐
│  GUARDIAN RISK CHECKS                                         │
├──────────────────────────────────────────────────────────────┤
│  Position Size      │  ≤ 0.25% default, 0.50% max per trade  │
│  Daily Drawdown     │  Stop if > 2% daily loss               │
│  Correlation        │  No correlated pairs (EUR/GBP + EUR/USD)│
│  Exposure Limit     │  Max 3 positions same direction        │
│  News Blackout      │  No trades during HIGH events          │
│  Spread Check       │  Reject if spread > 3x normal          │
│  Time Check         │  No trades in last hour of session     │
│  Weekend Risk       │  No new positions Friday after 4pm     │
└──────────────────────────────────────────────────────────────┘
```

### Position Sizing Calculation
```
Account Balance: $10,000
Risk Per Trade: 0.25% = $25

Stop Loss: 50 pips
Pip Value (EURUSD): $10/lot

Position Size = $25 / (50 pips × $10)
             = $25 / $500
             = 0.05 lots
```

### Output Format
```json
{
  "approved": true,
  "position_size": 0.05,
  "risk_amount": 25.00,
  "risk_percent": 0.25,
  "stop_distance_pips": 50,
  "checks": {
    "position_size": "PASS",
    "daily_drawdown": "PASS",
    "correlation": "PASS",
    "exposure": "PASS"
  },
  "warnings": []
}
```

---

## 10. Balancer - Portfolio Agent

**Port:** 3018  
**Role:** Manages overall portfolio exposure and correlation

### Portfolio Analysis
```
┌──────────────────────────────────────────────────────────────┐
│  CURRENT POSITIONS                                            │
├──────────────────────────────────────────────────────────────┤
│  Symbol   │ Direction │ Size  │ P/L    │ Risk  │ Duration   │
│  EURUSD   │ LONG      │ 0.05  │ +$12   │ $25   │ 4h 23m     │
│  GBPUSD   │ LONG      │ 0.03  │ -$8    │ $15   │ 2h 10m     │
└──────────────────────────────────────────────────────────────┘
│
▼
┌─────────────────────┐
│  Exposure Check:    │
│  - USD exposure: 2  │ ← Both pairs short USD
│  - Correlation: HIGH│ ← EUR/GBP correlated
│  - Total risk: $40  │
│  - Max risk: $50    │
└─────────────────────┘
```

### Correlation Matrix
```
         EUR   GBP   JPY   CHF   AUD   CAD
    EUR   1    0.8   0.3  -0.2   0.5   0.4
    GBP  0.8    1    0.2  -0.3   0.6   0.5
    JPY  0.3   0.2    1    0.7  -0.4  -0.3
    CHF -0.2  -0.3   0.7    1   -0.5  -0.4
    AUD  0.5   0.6  -0.4  -0.5    1    0.8
    CAD  0.4   0.5  -0.3  -0.4   0.8    1
```

### Output Format
```json
{
  "total_exposure": 0.08,
  "open_positions": 2,
  "total_risk": 40.00,
  "available_risk": 10.00,
  "correlations": [{"pair1": "EURUSD", "pair2": "GBPUSD", "correlation": 0.82}],
  "warnings": ["High correlation between open positions"]
}
```

---

## 11. Executor - Execution Agent

**Port:** 3019  
**Role:** Executes trades via MT5 bridge with safety checks

### Execution Flow
```
Order Request
      │
      ▼
┌─────────────────────┐
│  SAFETY CHECKS      │
│  1. Stop loss set?  │ ← MANDATORY
│  2. Duplicate?      │ ← Reject if same signal
│  3. Martingale?     │ ← Reject size increase
│  4. Averaging down? │ ← Reject adding to loser
│  5. Rate limits?    │ ← Max 3/hour/pair
│  6. Guardian ok?    │ ← Final approval
└─────────┬───────────┘
          │ All pass
          ▼
┌─────────────────────┐
│  EXECUTION MODE     │
│  ├─ paper: simulate │
│  ├─ shadow: log only│
│  └─ guarded_live:   │
│       Execute real  │
└─────────┬───────────┘
          │ guarded_live
          ▼
┌─────────────────────┐
│  MT5 FILE BRIDGE    │
│  Write: command.json│
│  Read: result.json  │
│  Timeout: 30 sec    │
└─────────────────────┘
```

### Output Format
```json
{
  "status": "EXECUTED",
  "ticket": 12345678,
  "symbol": "EURUSD",
  "direction": "LONG",
  "size": 0.05,
  "entry_price": 1.0855,
  "stop_loss": 1.0805,
  "take_profit": 1.0955,
  "mode": "guarded_live"
}
```

---

## 12. Chronicle - Journal Agent

**Port:** 3022  
**Role:** Records all trades with context for later analysis

### Trade Record
```json
{
  "trade_id": "TRD-20260313-001",
  "timestamp": "2026-03-13T22:30:00Z",
  "symbol": "EURUSD",
  "direction": "LONG",
  "entry": 1.0855,
  "exit": 1.0892,
  "pnl": 37.00,
  "pnl_pips": 37,
  "context": {
    "confluence_score": 78,
    "regime": "TRENDING_BULLISH",
    "sentiment": "contrarian_long",
    "macro_bias": "neutral",
    "news_tone": "risk_on"
  },
  "agents_consulted": ["Tactician", "Guardian", "Pulse", "Oracle"]
}
```

---

## 13. Insight - Analytics Agent

**Port:** 3023  
**Role:** Analyzes trading performance and identifies patterns

### Metrics Tracked
- Win rate by pair, session, regime
- Average R:R achieved
- Drawdown analysis
- Best/worst performing conditions

---

## 14. Arbiter - Governance Agent

**Port:** 3024  
**Role:** Version control, model validation, system governance

### Governance Checks
- Model version tracking
- Strategy parameter validation
- Backtest requirement enforcement

---

## 15. Nexus - Orchestrator

**Port:** 3020  
**Role:** Central coordinator - combines all agent inputs into decisions

### Confluence Calculation
```
┌──────────────────────────────────────────────────────────────┐
│  CONFLUENCE SCORE (Weighted Average)                          │
├──────────────────────────────────────────────────────────────┤
│  Category         │ Weight │ Source Agent                    │
├──────────────────────────────────────────────────────────────┤
│  Technical        │  25%   │ Atlas Jr.                       │
│  Structure        │  20%   │ Architect                       │
│  Regime           │  15%   │ Compass                         │
│  Sentiment        │  15%   │ Pulse                           │
│  Macro            │  15%   │ Oracle                          │
│  Event Risk       │  10%   │ Sentinel                        │
└──────────────────────────────────────────────────────────────┘
│
▼
CONFLUENCE SCORE = Σ(category_score × weight)

Score ≥ 75: EXECUTE
Score 60-74: WATCHLIST
Score < 60: NO TRADE
```

### Decision Flow
```
Every 5 minutes (Intraday Scan):
        │
        ▼
┌─────────────────────┐
│  Poll all agents    │
│  for each pair      │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Calculate          │
│  confluence score   │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Score ≥ 75?        │
│  ├─ YES: Alert +    │
│  │       Execute    │
│  └─ NO: Log only    │
└─────────────────────┘
```

---

# Data Sources Summary

| Data Type | Source | API/File | Cost | Refresh |
|-----------|--------|----------|------|---------|
| Price/Candles | MT5 | candle_data.csv | Free | 5 sec |
| Market Data | MT5 | market_data.csv | Free | 5 sec |
| Account Info | MT5 | account_data.json | Free | 5 sec |
| Calendar | MT5 | calendar_data.json | Free | 5 min |
| Retail Sentiment | Myfxbook | REST API | Free | 5 min |
| COT Positioning | CFTC | deafut.txt | Free | Weekly |
| Macro Data | FRED | REST API | Free | 1 hour |
| News Headlines | FXStreet | RSS | Free | 5 min |
| News Headlines | ForexLive | RSS | Free | 5 min |
| News Analysis | Claude | Anthropic API | $0.29/day | 5 min |

---

# Refresh Rates

| Component | Interval | Reason |
|-----------|----------|--------|
| MT5 Bridge | 5 seconds | Real-time price tracking |
| Intraday Scan | 5 minutes | Trade opportunity detection |
| Sentiment | 5 minutes | Crowd positioning changes |
| News + AI | 5 minutes | Event detection |
| Macro (FRED) | 1 hour | Slow-changing data |
| COT | 24 hours | Weekly release |

---

# Cost Analysis

## Daily Operating Costs

| Service | Usage | Cost/Day |
|---------|-------|----------|
| News AI (Sonnet 4) | 288 batches | $0.29 |
| MT5 | Unlimited | $0.00 |
| Myfxbook | Unlimited | $0.00 |
| FRED | Unlimited | $0.00 |
| CFTC | Unlimited | $0.00 |
| RSS Feeds | Unlimited | $0.00 |
| **Total** | | **$0.29/day** |

## Monthly Cost: ~$8.70

---

*Document generated by Atlas Gridlock Trading System*
*All data sources verified as REAL (no simulated data)*
