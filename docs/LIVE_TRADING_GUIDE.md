# Live Trading with MetaTrader 5 - Complete Setup Guide

This guide covers connecting the trading platform to MetaTrader 5 for live market data and trade execution.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     YOUR MAC MINI                                │
│                                                                  │
│  ┌──────────────┐         ┌──────────────┐         ┌──────────┐ │
│  │  MetaTrader  │ ──CSV──>│  MT5 Bridge  │ ──HTTP─>│  Agents  │ │
│  │      5       │<──CMD── │   Script     │<──HTTP──│  Swarm   │ │
│  └──────────────┘         └──────────────┘         └──────────┘ │
│        ↑                                                  ↓      │
│        │                                           ┌──────────┐ │
│   Your Broker                                      │ Dashboard │ │
│   (Live/Demo)                                      └──────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

**Data Flow:**
1. MT5 Expert Advisor exports price data to CSV files
2. MT5 Bridge script reads CSV and sends to Data Agent (Curator)
3. Agents analyze and generate trade signals
4. Executor sends trade commands back through Bridge
5. Bridge writes commands to file, EA reads and executes

---

## Step 1: Install MetaTrader 5

### Download & Install

1. Download MT5 from your broker or https://www.metatrader5.com/
2. Install and log into your broker account (Demo or Live)
3. Ensure you have the pairs you want to trade in Market Watch

### Recommended Broker Settings

- Enable "Allow DLL imports" in Tools → Options → Expert Advisors
- Enable "Allow automated trading"
- Set chart to M1 timeframe for fastest updates

---

## Step 2: Install the AgentBridge Expert Advisor

### Create the EA

In MT5, go to **Tools → MetaQuotes Language Editor** (or press F4)

Create new file: `AgentBridge.mq5`

```mql5
//+------------------------------------------------------------------+
//|                                                  AgentBridge.mq5 |
//|                                    Forex Multi-Agent Platform    |
//+------------------------------------------------------------------+
#property copyright "Forex Platform"
#property version   "1.00"
#property strict

// Settings
input int UpdateInterval = 5;  // Update interval in seconds
input string DataPath = "";    // Leave empty for default Files folder

// Symbols to export
string symbols[] = {"EURUSD", "GBPUSD", "USDJPY", "GBPJPY", "USDCHF", 
                    "USDCAD", "EURAUD", "AUDNZD", "AUDUSD"};

// Timeframes to export
ENUM_TIMEFRAMES timeframes[] = {PERIOD_M5, PERIOD_M15, PERIOD_M30, 
                                 PERIOD_H1, PERIOD_H4, PERIOD_D1, PERIOD_W1};

datetime lastUpdate = 0;

//+------------------------------------------------------------------+
int OnInit()
{
    EventSetTimer(UpdateInterval);
    Print("AgentBridge initialized - exporting ", ArraySize(symbols), " symbols");
    ExportAllData();
    return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    EventKillTimer();
}

//+------------------------------------------------------------------+
void OnTimer()
{
    ExportAllData();
    CheckForCommands();
}

//+------------------------------------------------------------------+
void ExportAllData()
{
    ExportMarketData();
    ExportCandleData();
    lastUpdate = TimeCurrent();
}

//+------------------------------------------------------------------+
void ExportMarketData()
{
    int handle = FileOpen("market_data.csv", FILE_WRITE|FILE_CSV|FILE_COMMON);
    if(handle == INVALID_HANDLE) return;
    
    FileWrite(handle, "Symbol", "Bid", "Ask", "Spread", "Time");
    
    for(int i = 0; i < ArraySize(symbols); i++)
    {
        string sym = symbols[i];
        
        // Add broker suffix if needed
        string brokerSym = sym;
        if(SymbolInfoInteger(sym, SYMBOL_EXIST) == false)
        {
            // Try common suffixes
            string suffixes[] = {".s", ".pro", ".r", "_SB", ""};
            for(int s = 0; s < ArraySize(suffixes); s++)
            {
                if(SymbolInfoInteger(sym + suffixes[s], SYMBOL_EXIST))
                {
                    brokerSym = sym + suffixes[s];
                    break;
                }
            }
        }
        
        double bid = SymbolInfoDouble(brokerSym, SYMBOL_BID);
        double ask = SymbolInfoDouble(brokerSym, SYMBOL_ASK);
        int digits = (int)SymbolInfoInteger(brokerSym, SYMBOL_DIGITS);
        double point = SymbolInfoDouble(brokerSym, SYMBOL_POINT);
        double spread = (ask - bid) / point;
        
        if(bid > 0)
        {
            FileWrite(handle, sym, 
                      DoubleToString(bid, digits), 
                      DoubleToString(ask, digits),
                      DoubleToString(spread, 1),
                      TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS));
        }
    }
    
    FileClose(handle);
}

//+------------------------------------------------------------------+
void ExportCandleData()
{
    int handle = FileOpen("candle_data.csv", FILE_WRITE|FILE_CSV|FILE_COMMON);
    if(handle == INVALID_HANDLE) return;
    
    FileWrite(handle, "Symbol", "Timeframe", "DateTime", "Open", "High", "Low", "Close", "Volume");
    
    for(int i = 0; i < ArraySize(symbols); i++)
    {
        string sym = symbols[i];
        string brokerSym = GetBrokerSymbol(sym);
        
        for(int t = 0; t < ArraySize(timeframes); t++)
        {
            ENUM_TIMEFRAMES tf = timeframes[t];
            string tfName = TimeframeToString(tf);
            
            MqlRates rates[];
            int copied = CopyRates(brokerSym, tf, 0, 500, rates);
            
            for(int r = 0; r < copied; r++)
            {
                FileWrite(handle, sym, tfName,
                          TimeToString(rates[r].time, TIME_DATE|TIME_SECONDS),
                          DoubleToString(rates[r].open, 5),
                          DoubleToString(rates[r].high, 5),
                          DoubleToString(rates[r].low, 5),
                          DoubleToString(rates[r].close, 5),
                          IntegerToString(rates[r].tick_volume));
            }
        }
    }
    
    FileClose(handle);
}

//+------------------------------------------------------------------+
void CheckForCommands()
{
    if(!FileIsExist("commands.csv", FILE_COMMON)) return;
    
    int handle = FileOpen("commands.csv", FILE_READ|FILE_CSV|FILE_COMMON);
    if(handle == INVALID_HANDLE) return;
    
    while(!FileIsEnding(handle))
    {
        string cmd = FileReadString(handle);
        string sym = FileReadString(handle);
        string dir = FileReadString(handle);
        double lots = StringToDouble(FileReadString(handle));
        double sl = StringToDouble(FileReadString(handle));
        double tp = StringToDouble(FileReadString(handle));
        string orderId = FileReadString(handle);
        
        if(cmd == "OPEN")
        {
            ExecuteOrder(sym, dir, lots, sl, tp, orderId);
        }
        else if(cmd == "CLOSE")
        {
            CloseOrder(orderId);
        }
        else if(cmd == "MODIFY")
        {
            ModifyOrder(orderId, sl, tp);
        }
    }
    
    FileClose(handle);
    FileDelete("commands.csv", FILE_COMMON);
}

//+------------------------------------------------------------------+
void ExecuteOrder(string sym, string direction, double lots, double sl, double tp, string orderId)
{
    string brokerSym = GetBrokerSymbol(sym);
    
    MqlTradeRequest request = {};
    MqlTradeResult result = {};
    
    request.action = TRADE_ACTION_DEAL;
    request.symbol = brokerSym;
    request.volume = lots;
    request.type = (direction == "long") ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
    request.price = (direction == "long") ? SymbolInfoDouble(brokerSym, SYMBOL_ASK) 
                                          : SymbolInfoDouble(brokerSym, SYMBOL_BID);
    request.sl = sl;
    request.tp = tp;
    request.deviation = 10;
    request.magic = 12345;
    request.comment = orderId;
    
    if(OrderSend(request, result))
    {
        WriteResult("EXECUTED", orderId, result.price, result.order);
        Print("Order executed: ", orderId, " at ", result.price);
    }
    else
    {
        WriteResult("FAILED", orderId, 0, 0);
        Print("Order failed: ", GetLastError());
    }
}

//+------------------------------------------------------------------+
void CloseOrder(string orderId)
{
    // Find position by comment
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if(PositionGetString(POSITION_COMMENT) == orderId)
        {
            MqlTradeRequest request = {};
            MqlTradeResult result = {};
            
            request.action = TRADE_ACTION_DEAL;
            request.position = ticket;
            request.symbol = PositionGetString(POSITION_SYMBOL);
            request.volume = PositionGetDouble(POSITION_VOLUME);
            request.type = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) 
                           ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
            request.price = (request.type == ORDER_TYPE_SELL) 
                           ? SymbolInfoDouble(request.symbol, SYMBOL_BID)
                           : SymbolInfoDouble(request.symbol, SYMBOL_ASK);
            request.deviation = 10;
            
            if(OrderSend(request, result))
            {
                WriteResult("CLOSED", orderId, result.price, 0);
            }
            break;
        }
    }
}

//+------------------------------------------------------------------+
void ModifyOrder(string orderId, double newSL, double newTP)
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if(PositionGetString(POSITION_COMMENT) == orderId)
        {
            MqlTradeRequest request = {};
            MqlTradeResult result = {};
            
            request.action = TRADE_ACTION_SLTP;
            request.position = ticket;
            request.symbol = PositionGetString(POSITION_SYMBOL);
            request.sl = newSL;
            request.tp = newTP;
            
            OrderSend(request, result);
            break;
        }
    }
}

//+------------------------------------------------------------------+
void WriteResult(string status, string orderId, double price, ulong ticket)
{
    int handle = FileOpen("results.csv", FILE_WRITE|FILE_CSV|FILE_COMMON);
    if(handle != INVALID_HANDLE)
    {
        FileWrite(handle, status, orderId, DoubleToString(price, 5), IntegerToString(ticket));
        FileClose(handle);
    }
}

//+------------------------------------------------------------------+
string GetBrokerSymbol(string sym)
{
    if(SymbolInfoInteger(sym, SYMBOL_EXIST)) return sym;
    
    string suffixes[] = {".s", ".pro", ".r", "_SB", ".i", ".e", ""};
    for(int i = 0; i < ArraySize(suffixes); i++)
    {
        if(SymbolInfoInteger(sym + suffixes[i], SYMBOL_EXIST))
            return sym + suffixes[i];
    }
    return sym;
}

//+------------------------------------------------------------------+
string TimeframeToString(ENUM_TIMEFRAMES tf)
{
    switch(tf)
    {
        case PERIOD_M1:  return "M1";
        case PERIOD_M5:  return "M5";
        case PERIOD_M15: return "M15";
        case PERIOD_M30: return "M30";
        case PERIOD_H1:  return "H1";
        case PERIOD_H4:  return "H4";
        case PERIOD_D1:  return "D1";
        case PERIOD_W1:  return "W1";
        default: return "M1";
    }
}
//+------------------------------------------------------------------+
```

### Compile & Attach

1. Press **F7** to compile
2. In MT5, open any chart
3. Drag `AgentBridge` from Navigator → Expert Advisors onto the chart
4. Enable "Allow Algo Trading" in the toolbar
5. You should see "AgentBridge initialized" in the Experts tab

---

## Step 3: Configure the MT5 Bridge Script

### Find MT5 Data Path

The EA writes files to MT5's common data folder:

**Windows:**
```
C:\Users\<username>\AppData\Roaming\MetaQuotes\Terminal\Common\Files\
```

**macOS (via Wine/CrossOver):**
```
~/.wine/drive_c/users/<user>/AppData/Roaming/MetaQuotes/Terminal/Common/Files/
```

### Update Bridge Script

Edit `/path/to/forex-trading-platform/mt5_bridge.py`:

```python
#!/usr/bin/env python3
"""
MT5 Bridge - Connects MetaTrader 5 to the Agent Swarm
"""

import os
import csv
import time
import asyncio
import httpx
from datetime import datetime
from pathlib import Path

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION - UPDATE THESE FOR YOUR SETUP
# ═══════════════════════════════════════════════════════════════

# Path to MT5 Common Files folder
MT5_DATA_PATH = Path("/path/to/MetaQuotes/Terminal/Common/Files")

# Agent URLs
CURATOR_URL = "http://localhost:3021"
EXECUTOR_URL = "http://localhost:3019"

# Update interval (seconds)
UPDATE_INTERVAL = 5

# ═══════════════════════════════════════════════════════════════


class MT5Bridge:
    def __init__(self):
        self.running = True
        self.last_market_update = None
        self.last_candle_update = None
        
    async def run(self):
        """Main loop - read from MT5, send to agents."""
        print(f"[MT5 Bridge] Starting...")
        print(f"[MT5 Bridge] Data path: {MT5_DATA_PATH}")
        print(f"[MT5 Bridge] Curator URL: {CURATOR_URL}")
        
        while self.running:
            try:
                await self.process_market_data()
                await self.process_candle_data()
                await self.check_for_commands()
                await self.process_results()
            except Exception as e:
                print(f"[MT5 Bridge] Error: {e}")
            
            await asyncio.sleep(UPDATE_INTERVAL)
    
    async def process_market_data(self):
        """Read market_data.csv and send to Curator."""
        market_file = MT5_DATA_PATH / "market_data.csv"
        
        if not market_file.exists():
            return
        
        # Check if file was modified
        mtime = market_file.stat().st_mtime
        if mtime == self.last_market_update:
            return
        self.last_market_update = mtime
        
        symbols = {}
        with open(market_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    sym = row['Symbol'].replace('.s', '').replace('.pro', '')  # Remove suffix
                    symbols[sym] = {
                        "bid": float(row['Bid']),
                        "ask": float(row['Ask']),
                        "spread": float(row['Spread']),
                    }
                except (KeyError, ValueError) as e:
                    continue
        
        if symbols:
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.post(
                        f"{CURATOR_URL}/api/market-data/update",
                        json={"symbols": symbols},
                        timeout=10.0
                    )
                    if response.status_code == 200:
                        print(f"[MT5 Bridge] Sent {len(symbols)} symbols to Curator")
                except Exception as e:
                    print(f"[MT5 Bridge] Failed to send market data: {e}")
    
    async def process_candle_data(self):
        """Read candle_data.csv and send to Curator."""
        candle_file = MT5_DATA_PATH / "candle_data.csv"
        
        if not candle_file.exists():
            return
        
        mtime = candle_file.stat().st_mtime
        if mtime == self.last_candle_update:
            return
        self.last_candle_update = mtime
        
        candles = {}
        with open(candle_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    sym = row['Symbol'].replace('.s', '').replace('.pro', '')
                    tf = row['Timeframe']
                    
                    if sym not in candles:
                        candles[sym] = {}
                    if tf not in candles[sym]:
                        candles[sym][tf] = []
                    
                    candles[sym][tf].append({
                        "time": row['DateTime'],
                        "open": float(row['Open']),
                        "high": float(row['High']),
                        "low": float(row['Low']),
                        "close": float(row['Close']),
                        "volume": int(row['Volume']),
                    })
                except (KeyError, ValueError):
                    continue
        
        if candles:
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.post(
                        f"{CURATOR_URL}/api/candles/update",
                        json={"candles": candles},
                        timeout=30.0
                    )
                    if response.status_code == 200:
                        total = sum(sum(len(tfs) for tfs in sym.values()) for sym in candles.values())
                        print(f"[MT5 Bridge] Sent {total} candles to Curator")
                except Exception as e:
                    print(f"[MT5 Bridge] Failed to send candle data: {e}")
    
    async def check_for_commands(self):
        """Check if Executor has commands to send to MT5."""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{EXECUTOR_URL}/api/pending-commands",
                    timeout=5.0
                )
                if response.status_code == 200:
                    commands = response.json().get('commands', [])
                    if commands:
                        self.write_commands(commands)
            except:
                pass  # Endpoint may not exist in paper mode
    
    def write_commands(self, commands):
        """Write trade commands for MT5 EA to read."""
        commands_file = MT5_DATA_PATH / "commands.csv"
        
        with open(commands_file, 'w', newline='') as f:
            writer = csv.writer(f)
            for cmd in commands:
                writer.writerow([
                    cmd.get('action', 'OPEN'),
                    cmd.get('symbol', ''),
                    cmd.get('direction', ''),
                    cmd.get('lots', 0),
                    cmd.get('sl', 0),
                    cmd.get('tp', 0),
                    cmd.get('order_id', ''),
                ])
        
        print(f"[MT5 Bridge] Wrote {len(commands)} commands for MT5")
    
    async def process_results(self):
        """Read execution results from MT5."""
        results_file = MT5_DATA_PATH / "results.csv"
        
        if not results_file.exists():
            return
        
        with open(results_file, 'r') as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 4:
                    status, order_id, price, ticket = row[0], row[1], row[2], row[3]
                    print(f"[MT5 Bridge] Order {order_id}: {status} at {price}")
                    
                    # Notify Executor of result
                    async with httpx.AsyncClient() as client:
                        try:
                            await client.post(
                                f"{EXECUTOR_URL}/api/execution-result",
                                json={
                                    "order_id": order_id,
                                    "status": status,
                                    "fill_price": float(price) if price else 0,
                                    "ticket": ticket,
                                },
                                timeout=5.0
                            )
                        except:
                            pass
        
        # Delete processed results
        results_file.unlink()


async def main():
    bridge = MT5Bridge()
    await bridge.run()


if __name__ == "__main__":
    asyncio.run(main())
```

---

## Step 4: Configure Environment for Live Trading

### Update .env

```bash
# Change from paper to live mode
PAPER_MODE=false

# Set your broker's symbol suffix (if any)
SYMBOL_SUFFIX=.s  # or .pro, .r, etc.

# MT5 data path
MT5_DATA_PATH=/path/to/MetaQuotes/Terminal/Common/Files
```

### Risk Settings for Live Trading

```bash
# Conservative settings for live trading
DEFAULT_RISK_PCT=0.25    # 0.25% per trade
MAX_DAILY_LOSS=2.0       # 2% daily max loss
MAX_WEEKLY_DRAWDOWN=4.0  # 4% weekly max drawdown
```

---

## Step 5: Start Live Trading

### 1. Start MT5

```bash
# Open MetaTrader 5
# Ensure AgentBridge EA is attached and running
# Check Experts tab for "AgentBridge initialized"
```

### 2. Start Agent Swarm

```bash
cd /path/to/forex-trading-platform/agents
./start_agents.sh
```

### 3. Start MT5 Bridge

```bash
python3 /path/to/forex-trading-platform/mt5_bridge.py
```

### 4. Verify Connection

```bash
# Check data is flowing
curl http://localhost:3021/api/market

# Check agent status
curl http://localhost:3020/api/agents

# Open dashboard
open http://localhost:3020
```

---

## Step 6: Promote to Live Execution

By default, even with `PAPER_MODE=false`, the system requires promotion to execute real trades.

### Promotion Requirements

The system tracks these metrics before allowing live execution:

| Metric | Requirement |
|--------|-------------|
| Paper Trades | 100+ completed |
| Paper Days | 30+ days |
| Profit Factor | ≥ 1.3 |
| Max Drawdown | ≤ 5% |
| Win Rate | ≥ 40% |

### Manual Promotion (Override)

To manually enable live execution:

```bash
curl -X POST http://localhost:3019/api/promote \
  -H "Content-Type: application/json" \
  -d '{"confirm": "I_UNDERSTAND_THE_RISKS", "account_id": "YOUR_ACCOUNT"}'
```

⚠️ **WARNING**: This enables real money trading. Ensure you understand all risks.

---

## Safety Features

### Kill Switches

These automatically halt trading:

| Trigger | Action |
|---------|--------|
| Daily loss > 2% | Stop all trading for day |
| Weekly DD > 4% | Reduce position sizes |
| Hard DD > 8% | Full trading halt |
| MT5 disconnect | Pause new trades |
| Data stale > 60s | Block new entries |

### Guardian Veto

The Guardian agent can veto any trade for:
- Position size too large
- Too many correlated positions
- Spread abnormally wide
- Event blackout window

### Manual Emergency Stop

```bash
# Stop all trading immediately
curl -X POST http://localhost:3013/api/emergency-stop

# Close all positions
curl -X POST http://localhost:3019/api/close-all
```

---

## Monitoring Live Trading

### Dashboard

- **Main**: http://localhost:3020 - Overview, positions, P&L
- **Monitor**: http://localhost:3020/monitor - Agent health
- **Data**: http://localhost:3021 - Data quality

### Key API Endpoints

```bash
# Current positions
curl http://localhost:3019/api/positions

# Today's P&L
curl http://localhost:3019/api/pnl/today

# Risk status
curl http://localhost:3013/api/status

# Recent trades
curl http://localhost:3022/api/trades?limit=10
```

### Logs

```bash
# Watch all agent logs
tail -f /tmp/*.log

# Watch specific agent
tail -f /tmp/orchestrator.log
tail -f /tmp/execution.log
```

---

## Troubleshooting Live Trading

### No Data from MT5

```bash
# Check if EA is running in MT5
# Look for "AgentBridge" in Experts tab

# Check if files are being created
ls -la /path/to/MT5/Common/Files/

# Check bridge is running
ps aux | grep mt5_bridge
```

### Trades Not Executing

```bash
# Check execution mode
curl http://localhost:3019/api/status

# Check Guardian approval
curl http://localhost:3013/api/status

# Check if promoted
curl http://localhost:3019/api/promotion-status
```

### Connection Issues

```bash
# Test MT5 connection
python3 -c "from pathlib import Path; print(Path('/path/to/MT5/Files/market_data.csv').exists())"

# Test agent connection
curl http://localhost:3020/api/status
```

---

## Best Practices for Live Trading

### 1. Start with Demo Account
- Run on demo for at least 2 weeks
- Verify all systems work correctly
- Monitor for any issues

### 2. Use Conservative Settings
```bash
DEFAULT_RISK_PCT=0.1   # Start with 0.1%
MAX_DAILY_LOSS=1.0     # 1% daily max
```

### 3. Monitor Actively
- Keep dashboard open during trading hours
- Set up alerts for errors
- Check positions daily

### 4. Have a Kill Switch Ready
```bash
# Bookmark this command
curl -X POST http://localhost:3013/api/emergency-stop
```

### 5. Regular Backups
```bash
# Backup trade journal
cp -r /path/to/agents/data /path/to/backup/
```

---

## Quick Reference

### Files

| File | Location | Purpose |
|------|----------|---------|
| market_data.csv | MT5 Common/Files | Live prices |
| candle_data.csv | MT5 Common/Files | OHLCV data |
| commands.csv | MT5 Common/Files | Trade commands |
| results.csv | MT5 Common/Files | Execution results |

### Commands

```bash
# Start everything
./start_agents.sh && python3 mt5_bridge.py &

# Check status
curl http://localhost:3020/api/agents

# Emergency stop
curl -X POST http://localhost:3013/api/emergency-stop
```

---

**Remember: Always start with a demo account and small position sizes until you're confident the system is working correctly.**

*Trade safely!* 🚀
