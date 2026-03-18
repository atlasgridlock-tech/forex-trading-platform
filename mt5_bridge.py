#!/usr/bin/env python3
"""
MT5 File Bridge v5.0
Multi-timeframe candle data + ticks + account info from MT5 to trading platform.
Timeframes: M15, M30, H1, H4, D1 (per spec)

Features:
- Chunked candle uploads to avoid timeouts
- Account data export
- Better error handling
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
ACCOUNT_FILE = MT5_FILES_DIR / "account_data.csv"

# API endpoints - connect to data-agent (Curator)
DATA_AGENT_URL = os.getenv("CURATOR_URL", "http://localhost:3021")
TICK_URL = f"{DATA_AGENT_URL}/api/market-data/update"
CANDLE_URL = f"{DATA_AGENT_URL}/api/candles/update"
ACCOUNT_URL = f"{DATA_AGENT_URL}/api/account/update"

# Chunk size for candle uploads (to avoid timeouts)
CANDLE_CHUNK_SIZE = 1000  # Send 1000 candles per request


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


def read_account_data():
    """Read account data from MT5's CSV file."""
    if not ACCOUNT_FILE.exists():
        return None
    
    try:
        with open(ACCOUNT_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                return {
                    "balance": float(row.get('Balance', 0)),
                    "equity": float(row.get('Equity', 0)),
                    "margin": float(row.get('Margin', 0)),
                    "free_margin": float(row.get('FreeMargin', 0)),
                    "leverage": int(row.get('Leverage', 0)),
                    "currency": row.get('Currency', 'USD'),
                    "profit": float(row.get('Profit', 0)),
                    "server": row.get('Server', ''),
                    "company": row.get('Company', ''),
                }
        return None
    except Exception as e:
        print(f"Error reading account data: {e}")
        return None


def send_ticks(data):
    """Send tick data to API."""
    try:
        response = requests.post(TICK_URL, json=data, timeout=5)
        return response.status_code == 200
    except Exception as e:
        print(f"Tick send error: {e}")
        return False


def send_candles_chunked(data):
    """Send MTF candle data to API in chunks to avoid timeouts."""
    try:
        # Flatten candles for chunking
        all_candles = []
        for symbol, timeframes in data.items():
            for tf, candles in timeframes.items():
                for candle in candles:
                    all_candles.append({
                        "symbol": symbol,
                        "timeframe": tf,
                        "candle": candle
                    })
        
        total = len(all_candles)
        if total == 0:
            return True
        
        # If small enough, send all at once
        if total <= CANDLE_CHUNK_SIZE:
            response = requests.post(CANDLE_URL, json={"candles": data}, timeout=30)
            if response.status_code == 200:
                return True
            else:
                print(f"Candle API error: {response.status_code} - {response.text[:200]}")
                return False
        
        # Otherwise, send in chunks by symbol
        success_count = 0
        symbols = list(data.keys())
        
        for symbol in symbols:
            symbol_data = {symbol: data[symbol]}
            try:
                response = requests.post(CANDLE_URL, json={"candles": symbol_data}, timeout=15)
                if response.status_code == 200:
                    success_count += 1
                else:
                    print(f"  {symbol}: Failed ({response.status_code})")
            except requests.exceptions.Timeout:
                print(f"  {symbol}: Timeout")
            except Exception as e:
                print(f"  {symbol}: Error - {e}")
        
        print(f"  Uploaded candles for {success_count}/{len(symbols)} symbols")
        return success_count > 0
        
    except Exception as e:
        print(f"Candle send error: {e}")
        return False


def send_account(data):
    """Send account data to API."""
    try:
        response = requests.post(ACCOUNT_URL, json=data, timeout=5)
        return response.status_code == 200
    except Exception as e:
        print(f"Account send error: {e}")
        return False


def main():
    print("=" * 60)
    print("MT5 FILE BRIDGE v5.0 (MTF: M15/M30/H1/H4/D1 + Account)")
    print("=" * 60)
    print(f"Tick file:    {TICK_FILE}")
    print(f"Candle file:  {CANDLE_FILE}")
    print(f"Account file: {ACCOUNT_FILE}")
    print(f"Data Agent:   {DATA_AGENT_URL}")
    print("-" * 60)
    
    if not MT5_FILES_DIR.exists():
        print(f"ERROR: MT5 files directory not found!")
        print(f"Looking for: {MT5_FILES_DIR}")
        return
    
    # Check if files exist
    print(f"Tick file exists:    {TICK_FILE.exists()}")
    print(f"Candle file exists:  {CANDLE_FILE.exists()}")
    print(f"Account file exists: {ACCOUNT_FILE.exists()}")
    
    if TICK_FILE.exists():
        print(f"Tick file size: {TICK_FILE.stat().st_size} bytes")
    if CANDLE_FILE.exists():
        print(f"Candle file size: {CANDLE_FILE.stat().st_size} bytes")
    
    print("-" * 60)
    print("Starting continuous updates...")
    print("-" * 60)
    
    last_tick_mtime = 0
    last_candle_mtime = 0
    last_account_mtime = 0
    update_count = 0
    candle_update_interval = 30  # Only update candles every 30 iterations (15s)
    
    while True:
        try:
            update_count += 1
            
            # Process tick data (every iteration)
            if TICK_FILE.exists():
                mtime = TICK_FILE.stat().st_mtime
                if mtime > last_tick_mtime:
                    last_tick_mtime = mtime
                    data = read_tick_data()
                    if data and data.get("symbols"):
                        symbols = list(data["symbols"].keys())
                        if send_ticks(data):
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Ticks: {len(symbols)} symbols")
                        else:
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Tick send failed")
            
            # Process account data (every iteration)
            if ACCOUNT_FILE.exists():
                mtime = ACCOUNT_FILE.stat().st_mtime
                if mtime > last_account_mtime:
                    last_account_mtime = mtime
                    account = read_account_data()
                    if account:
                        if send_account(account):
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Account: Balance=${account.get('balance', 0):,.2f} Equity=${account.get('equity', 0):,.2f}")
                        else:
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Account send failed")
            
            # Process candle data (less frequently to avoid overwhelming the server)
            if update_count % candle_update_interval == 0 and CANDLE_FILE.exists():
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
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] 📊 Uploading {total} candles for {len(candles)} symbols...")
                        if send_candles_chunked(candles):
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Candle upload complete")
                        else:
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ Some candle uploads failed")
            
            # Print heartbeat every 20 iterations (10 seconds)
            if update_count % 20 == 0:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 💓 Bridge running... (updates: {update_count})")
            
            time.sleep(0.5)
            
        except KeyboardInterrupt:
            print("\nBridge stopped.")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(1)


if __name__ == "__main__":
    main()
