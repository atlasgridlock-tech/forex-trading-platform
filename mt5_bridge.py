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
        # Try different encodings
        for encoding in ['utf-8', 'utf-16', 'utf-16-le', 'latin-1']:
            try:
                with open(TICK_FILE, 'r', encoding=encoding) as f:
                    content = f.read()
                    if 'Symbol' in content or 'symbol' in content:
                        break
            except:
                continue
        
        with open(TICK_FILE, 'r', encoding=encoding) as f:
            reader = csv.DictReader(f)
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
        
        # Try different encodings - EA now uses ANSI
        encoding = 'utf-8'
        for enc in ['utf-8', 'latin-1', 'utf-16', 'utf-16-le']:
            try:
                with open(CANDLE_FILE, 'r', encoding=enc) as f:
                    first_line = f.readline()
                    if 'Symbol' in first_line or 'symbol' in first_line:
                        encoding = enc
                        break
            except:
                continue
        
        with open(CANDLE_FILE, 'r', encoding=encoding) as f:
            reader = csv.DictReader(f)
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
        return
    
    print("Waiting for MT5 data...")
    print("Make sure EA v4.0 is compiled and attached!")
    print("-" * 60)
    
    last_tick_mtime = 0
    last_candle_mtime = 0
    symbols_seen = set()
    
    while True:
        try:
            # Process tick data
            if TICK_FILE.exists():
                mtime = TICK_FILE.stat().st_mtime
                if mtime > last_tick_mtime:
                    last_tick_mtime = mtime
                    data = read_tick_data()
                    if data and data.get("symbols"):
                        symbols = list(data["symbols"].keys())
                        new_symbols = set(symbols) - symbols_seen
                        if new_symbols:
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] Symbols: {', '.join(symbols)}")
                            symbols_seen.update(new_symbols)
                        send_ticks(data)
            
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
                        # Get timeframes from first symbol
                        first_symbol = list(candles.keys())[0] if candles else None
                        tfs = list(candles[first_symbol].keys()) if first_symbol else []
                        
                        if send_candles(candles):
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] 📊 Sent {total} candles | TFs: {', '.join(tfs)} | {len(candles)} symbols")
                        else:
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  Candle endpoint not ready")
            
            time.sleep(0.5)
            
        except KeyboardInterrupt:
            print("\nBridge stopped.")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(1)

if __name__ == "__main__":
    main()
