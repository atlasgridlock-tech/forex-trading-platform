"""
TimescaleDB Storage for Market Data (Curator)
Handles persistent storage of candle data, ticks, and market snapshots.
"""

import os
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)

TIMESCALE_URL = os.getenv("TIMESCALE_URL", "")


class TimescaleStore:
    """TimescaleDB storage for market data."""
    
    def __init__(self):
        self.conn = None
        self.enabled = bool(TIMESCALE_URL)
        
        if self.enabled:
            self._connect()
            self._init_schema()
    
    def _connect(self):
        """Connect to TimescaleDB."""
        try:
            self.conn = psycopg2.connect(TIMESCALE_URL)
            self.conn.autocommit = True
            logger.info("✅ Connected to TimescaleDB")
        except Exception as e:
            logger.error(f"❌ TimescaleDB connection failed: {e}")
            self.enabled = False
    
    def _init_schema(self):
        """Initialize database schema with hypertables."""
        if not self.conn:
            return
            
        try:
            with self.conn.cursor() as cur:
                # Create candles table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS candles (
                        time TIMESTAMPTZ NOT NULL,
                        symbol VARCHAR(20) NOT NULL,
                        timeframe VARCHAR(10) NOT NULL,
                        open DOUBLE PRECISION NOT NULL,
                        high DOUBLE PRECISION NOT NULL,
                        low DOUBLE PRECISION NOT NULL,
                        close DOUBLE PRECISION NOT NULL,
                        volume BIGINT,
                        spread INTEGER,
                        PRIMARY KEY (time, symbol, timeframe)
                    );
                """)
                
                # Convert to hypertable (TimescaleDB magic)
                cur.execute("""
                    SELECT create_hypertable('candles', 'time', 
                        if_not_exists => TRUE,
                        migrate_data => TRUE
                    );
                """)
                
                # Create market_ticks table for real-time data
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS market_ticks (
                        time TIMESTAMPTZ NOT NULL,
                        symbol VARCHAR(20) NOT NULL,
                        bid DOUBLE PRECISION NOT NULL,
                        ask DOUBLE PRECISION NOT NULL,
                        spread DOUBLE PRECISION,
                        PRIMARY KEY (time, symbol)
                    );
                """)
                
                cur.execute("""
                    SELECT create_hypertable('market_ticks', 'time',
                        if_not_exists => TRUE,
                        migrate_data => TRUE
                    );
                """)
                
                # Create indexes for common queries
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_candles_symbol_tf 
                    ON candles (symbol, timeframe, time DESC);
                """)
                
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ticks_symbol 
                    ON market_ticks (symbol, time DESC);
                """)
                
                # Create data quality snapshots table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS data_quality (
                        time TIMESTAMPTZ NOT NULL,
                        symbol VARCHAR(20) NOT NULL,
                        quality_score DOUBLE PRECISION,
                        freshness_score DOUBLE PRECISION,
                        completeness_score DOUBLE PRECISION,
                        consistency_score DOUBLE PRECISION,
                        tradeable BOOLEAN,
                        PRIMARY KEY (time, symbol)
                    );
                """)
                
                cur.execute("""
                    SELECT create_hypertable('data_quality', 'time',
                        if_not_exists => TRUE,
                        migrate_data => TRUE
                    );
                """)
                
                logger.info("✅ TimescaleDB schema initialized")
                
        except Exception as e:
            logger.error(f"❌ Schema initialization failed: {e}")
    
    def store_candles(self, candles: List[Dict[str, Any]]) -> int:
        """
        Store candle data in TimescaleDB.
        
        Args:
            candles: List of candle dicts with keys:
                     symbol, timeframe, time, open, high, low, close, volume, spread
        
        Returns:
            Number of candles stored
        """
        if not self.enabled or not candles:
            return 0
        
        try:
            with self.conn.cursor() as cur:
                values = [
                    (
                        c['time'],
                        c['symbol'],
                        c['timeframe'],
                        c['open'],
                        c['high'],
                        c['low'],
                        c['close'],
                        c.get('volume', 0),
                        c.get('spread', 0)
                    )
                    for c in candles
                ]
                
                execute_values(
                    cur,
                    """
                    INSERT INTO candles (time, symbol, timeframe, open, high, low, close, volume, spread)
                    VALUES %s
                    ON CONFLICT (time, symbol, timeframe) DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume,
                        spread = EXCLUDED.spread
                    """,
                    values
                )
                
                return len(values)
                
        except Exception as e:
            logger.error(f"❌ Failed to store candles: {e}")
            return 0
    
    def store_tick(self, symbol: str, bid: float, ask: float, spread: float = None):
        """Store a market tick."""
        if not self.enabled:
            return
        
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO market_ticks (time, symbol, bid, ask, spread)
                    VALUES (NOW(), %s, %s, %s, %s)
                    """,
                    (symbol, bid, ask, spread or (ask - bid))
                )
        except Exception as e:
            logger.error(f"❌ Failed to store tick: {e}")
    
    def store_quality(self, symbol: str, quality_data: Dict[str, Any]):
        """Store data quality snapshot."""
        if not self.enabled:
            return
        
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO data_quality (time, symbol, quality_score, freshness_score, 
                                              completeness_score, consistency_score, tradeable)
                    VALUES (NOW(), %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        symbol,
                        quality_data.get('overall', 0),
                        quality_data.get('freshness', 0),
                        quality_data.get('completeness', 0),
                        quality_data.get('consistency', 0),
                        quality_data.get('tradeable', False)
                    )
                )
        except Exception as e:
            logger.error(f"❌ Failed to store quality: {e}")
    
    def get_candles(self, symbol: str, timeframe: str, 
                    start: datetime = None, end: datetime = None,
                    limit: int = 500) -> List[Dict[str, Any]]:
        """
        Retrieve candles from TimescaleDB.
        
        Args:
            symbol: Trading symbol
            timeframe: Candle timeframe (M1, M5, H1, H4, D1, etc.)
            start: Start time (default: 30 days ago)
            end: End time (default: now)
            limit: Maximum candles to return
        
        Returns:
            List of candle dicts
        """
        if not self.enabled:
            return []
        
        if not start:
            start = datetime.utcnow() - timedelta(days=30)
        if not end:
            end = datetime.utcnow()
        
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT time, symbol, timeframe, open, high, low, close, volume, spread
                    FROM candles
                    WHERE symbol = %s AND timeframe = %s
                      AND time >= %s AND time <= %s
                    ORDER BY time DESC
                    LIMIT %s
                    """,
                    (symbol, timeframe, start, end, limit)
                )
                
                rows = cur.fetchall()
                return [
                    {
                        'time': row[0],
                        'symbol': row[1],
                        'timeframe': row[2],
                        'open': row[3],
                        'high': row[4],
                        'low': row[5],
                        'close': row[6],
                        'volume': row[7],
                        'spread': row[8]
                    }
                    for row in rows
                ]
                
        except Exception as e:
            logger.error(f"❌ Failed to get candles: {e}")
            return []
    
    def get_latest_candle(self, symbol: str, timeframe: str) -> Optional[Dict[str, Any]]:
        """Get the most recent candle for a symbol/timeframe."""
        candles = self.get_candles(symbol, timeframe, limit=1)
        return candles[0] if candles else None
    
    def get_symbols_with_data(self) -> List[str]:
        """Get list of symbols that have stored data."""
        if not self.enabled:
            return []
        
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT DISTINCT symbol FROM candles ORDER BY symbol")
                return [row[0] for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"❌ Failed to get symbols: {e}")
            return []
    
    def get_data_stats(self) -> Dict[str, Any]:
        """Get statistics about stored data."""
        if not self.enabled:
            return {"enabled": False}
        
        try:
            with self.conn.cursor() as cur:
                # Total candles
                cur.execute("SELECT COUNT(*) FROM candles")
                total_candles = cur.fetchone()[0]
                
                # Unique symbols
                cur.execute("SELECT COUNT(DISTINCT symbol) FROM candles")
                unique_symbols = cur.fetchone()[0]
                
                # Date range
                cur.execute("SELECT MIN(time), MAX(time) FROM candles")
                min_time, max_time = cur.fetchone()
                
                # Total ticks
                cur.execute("SELECT COUNT(*) FROM market_ticks")
                total_ticks = cur.fetchone()[0]
                
                return {
                    "enabled": True,
                    "total_candles": total_candles,
                    "unique_symbols": unique_symbols,
                    "total_ticks": total_ticks,
                    "date_range": {
                        "start": min_time.isoformat() if min_time else None,
                        "end": max_time.isoformat() if max_time else None
                    }
                }
                
        except Exception as e:
            logger.error(f"❌ Failed to get stats: {e}")
            return {"enabled": True, "error": str(e)}
    
    def cleanup_old_data(self, days_to_keep: int = 365):
        """Remove data older than specified days."""
        if not self.enabled:
            return
        
        try:
            with self.conn.cursor() as cur:
                cutoff = datetime.utcnow() - timedelta(days=days_to_keep)
                
                cur.execute("DELETE FROM candles WHERE time < %s", (cutoff,))
                candles_deleted = cur.rowcount
                
                cur.execute("DELETE FROM market_ticks WHERE time < %s", (cutoff,))
                ticks_deleted = cur.rowcount
                
                logger.info(f"🧹 Cleaned up {candles_deleted} candles, {ticks_deleted} ticks older than {days_to_keep} days")
                
        except Exception as e:
            logger.error(f"❌ Cleanup failed: {e}")
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("TimescaleDB connection closed")


# Singleton instance
_store = None

def get_store() -> TimescaleStore:
    """Get the TimescaleDB store singleton."""
    global _store
    if _store is None:
        _store = TimescaleStore()
    return _store
