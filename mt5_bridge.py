#!/usr/bin/env python3
"""
MT5 File Bridge v4.1
Multi-timeframe candle data + ticks from MT5 to trading platform.
Timeframes: M30 (primary), H1, H4, D1 (per spec)

Updated for new data-agent endpoints.
"""

import csv
import time
import requests
import os
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# MT5 common files directory on Mac
MT5_FILES_DIR = Path.home() / "Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files"
TICK_FILE = MT5_FILES_DIR / "market_data.csv"
CANDLE_FILE = MT5_FILES_DIR / "candle_data.csv"

# API endpoints - connect to data-agent (Curator)
DATA_AGENT_URL = os.getenv("CURATOR_URL", "http://localhost:3021")
TICK_URL = f"{DATA_AGENT_URL}/api/market-data/update"
CANDLE_URL = f"{DATA_AGENT_URL}/api/candles/update"

def read_tick_data():
    """Read tick data from MT5's CSV file."""
    if not TICK_FILE.exists():
        return None
    
    try:
        data = {"symbols": {}}
        # MT5 exports as TAB-delimited
        with open(TICK_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                symbol = row.get('Symbol', row.get('symbol', '')).strip()
                if symbol:
                    data["symbols"][symbol] = {
                        "bid": float(row.get('Bid', row.get('bid', 0))),
                        "ask": float(row.get('Ask', row.get('ask', 0))),
                        "spread": float(row.get('Spread', row.get('spread', 0))),
                    }
        return data
    except Exception as e:
        print(f"Error reading tick data: {e}")
        return None

def read_candle_data():
    """Read MTF candle data from MT5's CSV file."""
    if not CANDLE_FILE.exists():
        return None
    
    try:
        # Structure: {symbol: {timeframe: [candles]}}
        candles = defaultdict(lambda: defaultdict(list))
        
        # MT5 exports as TAB-delimited
        with open(CANDLE_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                symbol = row.get('Symbol', row.get('symbol', '')).strip()
                tf = row.get('Timeframe', row.get('timeframe', '')).strip()
                if symbol and tf:
                    try:
                        candles[symbol][tf].append({
                            "time": row.get('DateTime', row.get('time', '')),
                            "open": float(row.get('Open', row.get('open', 0))),
                            "high": float(row.get('High', row.get('high', 0))),
                            "low": float(row.get('Low', row.get('low', 0))),
                            "close": float(row.get('Close', row.get('close', 0))),
                            "volume": int(float(row.get('Volume', row.get('volume', 0)))),
                        })
                    except (ValueError, KeyError) as e:
                        continue
        
        # Convert to regular dict
        result = {}
        for symbol in candles:
            result[symbol] = dict(candles[symbol])
        
        return result
    except Exception as e:
        print(f"Error reading candles: {e}")
        return None

def send_ticks(data):
    """Send tick data to API."""
    try:
        response = requests.post(TICK_URL, json=data, timeout=5)
        return response.status_code == 200
    except:
        return False

def send_candles(data):
    """Send MTF candle data to API."""
    try:
        response = requests.post(CANDLE_URL, json={"candles": data}, timeout=15)
        return response.status_code == 200
    except Exception as e:
        print(f"Candle send error: {e}")
        return False

def main():
    print("=" * 60)
    print("MT5 FILE BRIDGE v4.1 (MTF: M30/H1/H4/D1)")
    print("=" * 60)
    print(f"Tick file:   {TICK_FILE}")
    print(f"Candle file: {CANDLE_FILE}")
    print(f"Data Agent:  {DATA_AGENT_URL}")
    print("-" * 60)
    
    if not MT5_FILES_DIR.exists():
        print(f"ERROR: MT5 files directory not found!")
        print(f"Looking for: {MT5_FILES_DIR}")
        return
    
    # Check if files exist
    print(f"Tick file exists: {TICK_FILE.exists()}")
    print(f"Candle file exists: {CANDLE_FILE.exists()}")
    
    if TICK_FILE.exists():
        print(f"Tick file size: {TICK_FILE.stat().st_size} bytes")
    if CANDLE_FILE.exists():
        print(f"Candle file size: {CANDLE_FILE.stat().st_size} bytes")
    
    print("-" * 60)
    print("Starting continuous updates...")
    print("-" * 60)
    
    last_tick_mtime = 0
    last_candle_mtime = 0
    symbols_seen = set()
    update_count = 0
    
    while True:
        try:
            update_count += 1
            
            # Process tick data
            if TICK_FILE.exists():
                mtime = TICK_FILE.stat().st_mtime
                if mtime > last_tick_mtime:
                    last_tick_mtime = mtime
                    data = read_tick_data()
                    if data and data.get("symbols"):
                        symbols = list(data["symbols"].keys())
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] 💹 Sending {len(symbols)} symbols: {', '.join(symbols[:5])}...")
                        if send_ticks(data):
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Tick data sent successfully")
                        else:
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Failed to send tick data")
                    else:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ No symbols in tick data")
            
            # Process candle data
            if CANDLE_FILE.exists():
                mtime = CANDLE_FILE.stat().st_mtime
                if mtime > last_candle_mtime:
                    last_candle_mtime = mtime
                    candles = read_candle_data()
                    if candles:
                        # Count total candles
                        total = sum(
                            sum(len(tfs) for tfs in symbol_data.values())
                            for symbol_data in candles.values()
                        )
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] 📊 Sending {total} candles for {len(candles)} symbols...")
                        if send_candles(candles):
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Candle data sent successfully")
                        else:
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Failed to send candle data")
                    else:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ No candles read from file")
            
            # Print heartbeat every 10 iterations (5 seconds)
            if update_count % 10 == 0:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 💓 Bridge running... (tick mtime: {last_tick_mtime:.0f}, candle mtime: {last_candle_mtime:.0f})")
            
            time.sleep(0.5)
            
        except KeyboardInterrupt:
            print("\nBridge stopped.")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(1)

if __name__ == "__main__":
    main()
