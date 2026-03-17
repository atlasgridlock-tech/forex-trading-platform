#!/usr/bin/env python3
"""
Simulated Live Feed for Testing
Generates realistic forex tick and candle data without MT5.
"""

import requests
import time
import random
import math
from datetime import datetime, timedelta
from collections import defaultdict

DATA_AGENT_URL = "http://localhost:3021"

# Base prices for simulation
BASE_PRICES = {
    "EURUSD": 1.0850,
    "GBPUSD": 1.2670,
    "USDJPY": 149.80,
    "GBPJPY": 189.90,
    "USDCHF": 0.8845,
    "USDCAD": 1.3580,
    "EURAUD": 1.6540,
    "AUDNZD": 1.1025,
    "AUDUSD": 0.6568,
}

# Volatility per symbol (pip movement per tick)
VOLATILITY = {
    "EURUSD": 0.00003,
    "GBPUSD": 0.00004,
    "USDJPY": 0.02,
    "GBPJPY": 0.03,
    "USDCHF": 0.00003,
    "USDCAD": 0.00003,
    "EURAUD": 0.00005,
    "AUDNZD": 0.00003,
    "AUDUSD": 0.00003,
}

# Spreads per symbol (in pips)
SPREADS = {
    "EURUSD": 1.2,
    "GBPUSD": 1.5,
    "USDJPY": 1.5,
    "GBPJPY": 3.5,
    "USDCHF": 1.8,
    "USDCAD": 2.0,
    "EURAUD": 3.0,
    "AUDNZD": 2.5,
    "AUDUSD": 1.5,
}

# Current prices (will drift)
current_prices = dict(BASE_PRICES)

# Candle builders
candle_builders = defaultdict(lambda: defaultdict(dict))


def get_pip_value(symbol):
    """Get pip value for a symbol."""
    return 0.01 if "JPY" in symbol else 0.0001


def generate_tick():
    """Generate a realistic tick for each symbol."""
    ticks = {}
    
    for symbol in current_prices:
        # Random walk with mean reversion
        volatility = VOLATILITY[symbol]
        base = BASE_PRICES[symbol]
        current = current_prices[symbol]
        
        # Mean reversion force (stronger when far from base)
        reversion = (base - current) * 0.001
        
        # Random movement
        movement = random.gauss(0, volatility) + reversion
        current_prices[symbol] = current + movement
        
        # Calculate bid/ask with spread
        spread_pips = SPREADS[symbol] + random.uniform(-0.3, 0.3)  # Spread variation
        pip_value = get_pip_value(symbol)
        spread = spread_pips * pip_value
        
        mid = current_prices[symbol]
        bid = mid - spread / 2
        ask = mid + spread / 2
        
        ticks[symbol] = {
            "bid": round(bid, 5 if "JPY" not in symbol else 3),
            "ask": round(ask, 5 if "JPY" not in symbol else 3),
            "spread": round(spread_pips, 1),
            "volume": random.randint(10, 100),
            "time": int(datetime.utcnow().timestamp()),
        }
    
    return ticks


def update_candle_builder(symbol, price, timestamp):
    """Update candle builders for different timeframes."""
    timeframes = {
        "M30": 30,
        "H1": 60,
        "H4": 240,
        "D1": 1440,
    }
    
    for tf, minutes in timeframes.items():
        # Calculate candle open time
        dt = datetime.fromtimestamp(timestamp)
        minutes_since_midnight = dt.hour * 60 + dt.minute
        candle_start_minutes = (minutes_since_midnight // minutes) * minutes
        candle_dt = dt.replace(hour=candle_start_minutes // 60, minute=candle_start_minutes % 60, second=0, microsecond=0)
        candle_time = int(candle_dt.timestamp())
        
        builder = candle_builders[symbol][tf]
        
        if builder.get("time") != candle_time:
            # New candle
            builder["time"] = candle_time
            builder["open"] = price
            builder["high"] = price
            builder["low"] = price
            builder["close"] = price
            builder["volume"] = 1
        else:
            # Update existing candle
            builder["high"] = max(builder["high"], price)
            builder["low"] = min(builder["low"], price)
            builder["close"] = price
            builder["volume"] += 1


def get_completed_candles():
    """Get candles that are ready to send."""
    candles = defaultdict(lambda: defaultdict(list))
    
    for symbol, timeframes in candle_builders.items():
        for tf, builder in timeframes.items():
            if builder:
                decimals = 3 if "JPY" in symbol else 5
                candles[symbol][tf].append({
                    "time": builder["time"],
                    "open": round(builder["open"], decimals),
                    "high": round(builder["high"], decimals),
                    "low": round(builder["low"], decimals),
                    "close": round(builder["close"], decimals),
                    "volume": builder["volume"],
                    "spread": int(SPREADS[symbol] * 10),
                })
    
    return dict(candles)


def send_ticks(ticks):
    """Send tick data to data agent."""
    try:
        response = requests.post(
            f"{DATA_AGENT_URL}/api/market-data/update",
            json={"symbols": ticks},
            timeout=5
        )
        return response.status_code == 200
    except Exception as e:
        print(f"Tick send error: {e}")
        return False


def send_candles(candles):
    """Send candle data to data agent."""
    try:
        response = requests.post(
            f"{DATA_AGENT_URL}/api/candles/update",
            json={"candles": candles},
            timeout=5
        )
        return response.status_code == 200
    except Exception as e:
        print(f"Candle send error: {e}")
        return False


def main():
    print("=" * 60)
    print("SIMULATED LIVE FEED v1.0")
    print("=" * 60)
    print(f"Data Agent: {DATA_AGENT_URL}")
    print(f"Symbols: {', '.join(BASE_PRICES.keys())}")
    print("-" * 60)
    print("Sending simulated ticks and candles...")
    print("Press Ctrl+C to stop")
    print("-" * 60)
    
    tick_count = 0
    candle_count = 0
    last_candle_send = time.time()
    
    while True:
        try:
            # Generate and send ticks
            ticks = generate_tick()
            timestamp = int(datetime.utcnow().timestamp())
            
            # Update candle builders
            for symbol, tick in ticks.items():
                price = (tick["bid"] + tick["ask"]) / 2
                update_candle_builder(symbol, price, timestamp)
            
            if send_ticks(ticks):
                tick_count += 1
                if tick_count % 10 == 0:
                    prices_str = " | ".join([f"{s}: {current_prices[s]:.5f}" if "JPY" not in s else f"{s}: {current_prices[s]:.3f}" for s in list(current_prices.keys())[:3]])
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Tick #{tick_count} | {prices_str}")
            
            # Send candles every 5 seconds
            if time.time() - last_candle_send > 5:
                candles = get_completed_candles()
                if send_candles(candles):
                    candle_count += 1
                    total = sum(sum(len(tfs) for tfs in s.values()) for s in candles.values())
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 📊 Sent {total} candle updates")
                last_candle_send = time.time()
            
            # Simulate market tick rate (2-5 ticks per second)
            time.sleep(random.uniform(0.2, 0.5))
            
        except KeyboardInterrupt:
            print("\n" + "=" * 60)
            print(f"Feed stopped. Total ticks: {tick_count}, Candle batches: {candle_count}")
            print("=" * 60)
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(1)


if __name__ == "__main__":
    main()
