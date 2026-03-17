"""
Shared HTTP Client Pool and Caching Layer
Provides connection pooling and response caching for inter-agent communication.
"""

import os
import asyncio
import httpx
import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable
from functools import wraps
import redis.asyncio as redis


# ═══════════════════════════════════════════════════════════════
# HTTP CLIENT POOL
# ═══════════════════════════════════════════════════════════════

class HTTPClientPool:
    """
    Singleton HTTP client pool with connection reuse.
    Much more efficient than creating new clients for each request.
    """
    _instance: Optional["HTTPClientPool"] = None
    _client: Optional[httpx.AsyncClient] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def get_client(self) -> httpx.AsyncClient:
        """Get or create the shared HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0, connect=5.0),
                limits=httpx.Limits(
                    max_connections=100,
                    max_keepalive_connections=20,
                    keepalive_expiry=30.0,
                ),
                http2=False,  # Disable HTTP/2 for compatibility
            )
        return self._client
    
    async def close(self):
        """Close the client pool."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None


# Global client pool instance
_client_pool = HTTPClientPool()


async def get_pooled_client() -> httpx.AsyncClient:
    """Get the shared HTTP client."""
    return await _client_pool.get_client()


async def pooled_get(url: str, timeout: float = 5.0) -> Optional[dict]:
    """
    GET request using pooled connection.
    Returns JSON response or None on error.
    """
    try:
        client = await get_pooled_client()
        response = await client.get(url, timeout=timeout)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"[HTTPPool] GET error {url}: {e}")
    return None


async def pooled_post(url: str, data: dict, timeout: float = 10.0) -> Optional[dict]:
    """
    POST request using pooled connection.
    Returns JSON response or None on error.
    """
    try:
        client = await get_pooled_client()
        response = await client.post(url, json=data, timeout=timeout)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"[HTTPPool] POST error {url}: {e}")
    return None


# ═══════════════════════════════════════════════════════════════
# IN-MEMORY CACHE
# ═══════════════════════════════════════════════════════════════

class InMemoryCache:
    """
    Simple in-memory cache with TTL support.
    Used when Redis is not available.
    """
    
    def __init__(self, default_ttl: int = 60):
        self._cache: Dict[str, tuple] = {}  # key -> (value, expiry_time)
        self._default_ttl = default_ttl
    
    def get(self, key: str) -> Optional[Any]:
        """Get value if exists and not expired."""
        if key in self._cache:
            value, expiry = self._cache[key]
            if datetime.utcnow() < expiry:
                return value
            else:
                del self._cache[key]
        return None
    
    def set(self, key: str, value: Any, ttl: int = None):
        """Set value with TTL."""
        ttl = ttl or self._default_ttl
        expiry = datetime.utcnow() + timedelta(seconds=ttl)
        self._cache[key] = (value, expiry)
    
    def delete(self, key: str):
        """Delete a key."""
        self._cache.pop(key, None)
    
    def clear(self):
        """Clear all cache."""
        self._cache.clear()
    
    def cleanup(self):
        """Remove expired entries."""
        now = datetime.utcnow()
        expired = [k for k, (_, exp) in self._cache.items() if now >= exp]
        for k in expired:
            del self._cache[k]
    
    def stats(self) -> dict:
        """Get cache statistics."""
        self.cleanup()
        return {
            "entries": len(self._cache),
            "keys": list(self._cache.keys())[:20],
        }


# ═══════════════════════════════════════════════════════════════
# REDIS CACHE (Optional)
# ═══════════════════════════════════════════════════════════════

class RedisCache:
    """
    Redis-based cache for distributed caching across agents.
    Falls back to in-memory if Redis unavailable.
    """
    
    def __init__(self, redis_url: str = None, default_ttl: int = 60):
        self._redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self._default_ttl = default_ttl
        self._redis: Optional[redis.Redis] = None
        self._fallback = InMemoryCache(default_ttl)
        self._connected = False
    
    async def connect(self):
        """Connect to Redis."""
        if self._redis is None:
            try:
                self._redis = redis.from_url(
                    self._redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                await self._redis.ping()
                self._connected = True
                print(f"[RedisCache] Connected to {self._redis_url}")
            except Exception as e:
                print(f"[RedisCache] Connection failed, using in-memory: {e}")
                self._connected = False
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if self._connected:
            try:
                value = await self._redis.get(key)
                if value:
                    return json.loads(value)
            except:
                pass
        return self._fallback.get(key)
    
    async def set(self, key: str, value: Any, ttl: int = None):
        """Set value in cache."""
        ttl = ttl or self._default_ttl
        if self._connected:
            try:
                await self._redis.setex(key, ttl, json.dumps(value, default=str))
                return
            except:
                pass
        self._fallback.set(key, value, ttl)
    
    async def delete(self, key: str):
        """Delete from cache."""
        if self._connected:
            try:
                await self._redis.delete(key)
            except:
                pass
        self._fallback.delete(key)
    
    async def close(self):
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()


# ═══════════════════════════════════════════════════════════════
# CACHED FETCH DECORATOR
# ═══════════════════════════════════════════════════════════════

# Global cache instance
_cache = InMemoryCache(default_ttl=30)


def cache_key(prefix: str, *args, **kwargs) -> str:
    """Generate a cache key from arguments."""
    key_data = f"{prefix}:{args}:{sorted(kwargs.items())}"
    return hashlib.md5(key_data.encode()).hexdigest()[:16]


def cached(ttl: int = 30, prefix: str = ""):
    """
    Decorator to cache async function results.
    
    Usage:
        @cached(ttl=60, prefix="market")
        async def get_market_data(symbol):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            key = cache_key(prefix or func.__name__, *args, **kwargs)
            
            # Try cache first
            cached_value = _cache.get(key)
            if cached_value is not None:
                return cached_value
            
            # Call function and cache result
            result = await func(*args, **kwargs)
            if result is not None:
                _cache.set(key, result, ttl)
            
            return result
        return wrapper
    return decorator


async def cached_fetch(url: str, ttl: int = 30) -> Optional[dict]:
    """
    Fetch with caching - combines pooled HTTP and caching.
    """
    key = cache_key("fetch", url)
    
    # Check cache
    cached = _cache.get(key)
    if cached is not None:
        return cached
    
    # Fetch and cache
    result = await pooled_get(url)
    if result is not None:
        _cache.set(key, result, ttl)
    
    return result


# ═══════════════════════════════════════════════════════════════
# BATCH REQUESTS
# ═══════════════════════════════════════════════════════════════

async def batch_fetch(urls: list, max_concurrent: int = 10) -> Dict[str, Optional[dict]]:
    """
    Fetch multiple URLs concurrently with rate limiting.
    Returns dict mapping URL to response.
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def fetch_one(url: str):
        async with semaphore:
            return url, await pooled_get(url)
    
    tasks = [fetch_one(url) for url in urls]
    results = await asyncio.gather(*tasks)
    
    return dict(results)


# ═══════════════════════════════════════════════════════════════
# PERFORMANCE METRICS
# ═══════════════════════════════════════════════════════════════

class PerformanceMetrics:
    """Track performance metrics for monitoring."""
    
    def __init__(self):
        self.request_count = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.total_latency_ms = 0.0
        self.errors = 0
    
    def record_request(self, latency_ms: float, cached: bool):
        """Record a request."""
        self.request_count += 1
        self.total_latency_ms += latency_ms
        if cached:
            self.cache_hits += 1
        else:
            self.cache_misses += 1
    
    def record_error(self):
        """Record an error."""
        self.errors += 1
    
    def get_stats(self) -> dict:
        """Get performance statistics."""
        cache_rate = (self.cache_hits / max(1, self.request_count)) * 100
        avg_latency = self.total_latency_ms / max(1, self.request_count)
        
        return {
            "total_requests": self.request_count,
            "cache_hit_rate": f"{cache_rate:.1f}%",
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "avg_latency_ms": round(avg_latency, 2),
            "errors": self.errors,
        }


# Global metrics instance
metrics = PerformanceMetrics()


def get_cache() -> InMemoryCache:
    """Get the global cache instance."""
    return _cache


def get_metrics() -> PerformanceMetrics:
    """Get the global metrics instance."""
    return metrics
