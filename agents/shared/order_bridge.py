"""
MT5 Order Execution Bridge
Writes orders to file for EA to execute, reads results back.
"""

import os
import csv
import time
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List
import threading

# MT5 common files directory
MT5_FILES_DIR = Path(os.getenv("MT5_DATA_PATH", "/app/mt5_data"))
ORDERS_FILE = MT5_FILES_DIR / "pending_orders.csv"
RESULTS_FILE = MT5_FILES_DIR / "order_results.csv"
POSITIONS_FILE = MT5_FILES_DIR / "positions.csv"

# Order tracking
pending_orders: Dict[str, dict] = {}
completed_orders: Dict[str, dict] = {}
order_lock = threading.Lock()


def generate_order_id() -> str:
    """Generate unique order ID."""
    return f"ORD_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"


def submit_order(
    symbol: str,
    action: str,  # BUY, SELL, CLOSE, MODIFY
    volume: float = 0.01,
    sl: float = 0,
    tp: float = 0,
    comment: str = ""
) -> str:
    """
    Submit an order to be executed by MT5 EA.
    Returns order_id for tracking.
    """
    order_id = generate_order_id()
    
    with order_lock:
        # Write to pending orders file
        file_exists = ORDERS_FILE.exists()
        
        with open(ORDERS_FILE, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f, delimiter='\t')
            
            # Write header if new file
            if not file_exists:
                writer.writerow(['OrderId', 'Symbol', 'Action', 'Volume', 'SL', 'TP', 'Comment'])
            
            writer.writerow([order_id, symbol, action, volume, sl, tp, comment])
        
        # Track pending order
        pending_orders[order_id] = {
            'order_id': order_id,
            'symbol': symbol,
            'action': action,
            'volume': volume,
            'sl': sl,
            'tp': tp,
            'comment': comment,
            'submitted_at': datetime.now().isoformat(),
            'status': 'PENDING'
        }
    
    print(f"[OrderBridge] Submitted {action} {symbol} {volume} lots - ID: {order_id}")
    return order_id


def check_order_result(order_id: str, timeout: float = 30.0) -> Optional[dict]:
    """
    Check if an order has been executed.
    Returns result dict or None if still pending/timeout.
    """
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        # Check results file
        if RESULTS_FILE.exists():
            with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter='\t')
                for row in reader:
                    if row.get('OrderId') == order_id:
                        result = {
                            'order_id': order_id,
                            'status': row.get('Status', 'UNKNOWN'),
                            'message': row.get('Message', ''),
                            'ticket': row.get('Ticket', ''),
                            'time': row.get('Time', ''),
                        }
                        
                        with order_lock:
                            if order_id in pending_orders:
                                del pending_orders[order_id]
                            completed_orders[order_id] = result
                        
                        return result
        
        time.sleep(0.5)
    
    return None


def get_pending_orders() -> List[dict]:
    """Get list of pending orders."""
    with order_lock:
        return list(pending_orders.values())


def get_completed_orders() -> List[dict]:
    """Get list of completed orders."""
    with order_lock:
        return list(completed_orders.values())


def get_open_positions() -> List[dict]:
    """Read open positions from MT5."""
    positions = []
    
    if POSITIONS_FILE.exists():
        try:
            with open(POSITIONS_FILE, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter='\t')
                for row in reader:
                    positions.append({
                        'ticket': row.get('Ticket', ''),
                        'symbol': row.get('Symbol', ''),
                        'type': row.get('Type', ''),
                        'volume': float(row.get('Volume', 0)),
                        'open_price': float(row.get('OpenPrice', 0)),
                        'sl': float(row.get('SL', 0)),
                        'tp': float(row.get('TP', 0)),
                        'profit': float(row.get('Profit', 0)),
                        'open_time': row.get('OpenTime', ''),
                        'magic': row.get('Magic', ''),
                        'comment': row.get('Comment', ''),
                    })
        except Exception as e:
            print(f"[OrderBridge] Error reading positions: {e}")
    
    return positions


def close_position(symbol: str, volume: float = 0) -> str:
    """Close a position (full or partial)."""
    return submit_order(symbol, "CLOSE", volume)


def modify_position(symbol: str, sl: float = 0, tp: float = 0) -> str:
    """Modify SL/TP of a position."""
    return submit_order(symbol, "MODIFY", 0, sl, tp)


# Convenience functions
def buy(symbol: str, volume: float, sl: float = 0, tp: float = 0, comment: str = "") -> str:
    """Place a BUY order."""
    return submit_order(symbol, "BUY", volume, sl, tp, comment)


def sell(symbol: str, volume: float, sl: float = 0, tp: float = 0, comment: str = "") -> str:
    """Place a SELL order."""
    return submit_order(symbol, "SELL", volume, sl, tp, comment)


def execute_and_wait(
    symbol: str,
    action: str,
    volume: float = 0.01,
    sl: float = 0,
    tp: float = 0,
    comment: str = "",
    timeout: float = 30.0
) -> dict:
    """
    Submit order and wait for result.
    Returns result dict with status.
    """
    order_id = submit_order(symbol, action, volume, sl, tp, comment)
    result = check_order_result(order_id, timeout)
    
    if result is None:
        return {
            'order_id': order_id,
            'status': 'TIMEOUT',
            'message': f'No response from MT5 within {timeout}s',
        }
    
    return result


if __name__ == "__main__":
    # Test
    print("MT5 Order Bridge Test")
    print(f"Orders file: {ORDERS_FILE}")
    print(f"Results file: {RESULTS_FILE}")
    
    # Show current positions
    positions = get_open_positions()
    print(f"\nOpen positions: {len(positions)}")
    for p in positions:
        print(f"  {p['symbol']} {p['type']} {p['volume']} @ {p['open_price']} P/L: {p['profit']}")
