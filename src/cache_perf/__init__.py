"""
缓存与性能优化模块 (CachePerf) - 阶段346-350
"""

from cache_perf.cache_manager import (
    EvictionPolicy, CacheLevel, CacheEntry, CacheStats,
    LRUCache, TieredCache, CacheManager, get_cache_manager,
)
from cache_perf.rate_limiter import (
    LimitStrategy, LimitRule, LimitResult, LimitStats,
    TokenBucket, SlidingWindow, FixedWindow, LeakyBucket,
    RateLimiter, get_rate_limiter,
)
from cache_perf.circuit_breaker import (
    CircuitState, CircuitConfig, CircuitEvent, CircuitStats,
    CircuitBreaker, CircuitBreakerManager, CircuitOpenError,
    get_circuit_manager,
)
from cache_perf.connection_pool import (
    ConnStatus, PooledConnection, PoolConfig, PoolStats,
    ConnectionPool, ConnectionPoolManager, get_pool_manager,
)
from cache_perf.performance_monitor import (
    MetricType, TimerRecord, LatencySnapshot, ThroughputSnapshot,
    ResourceSnapshot, PerformanceBaseline, BaselineDeviation,
    LatencyTracker, ThroughputTracker, ResourceMonitor,
    PerformanceMonitor, get_performance_monitor,
)

__all__ = [
    "EvictionPolicy", "CacheLevel", "CacheEntry", "CacheStats",
    "LRUCache", "TieredCache", "CacheManager", "get_cache_manager",
    "LimitStrategy", "LimitRule", "LimitResult", "LimitStats",
    "TokenBucket", "SlidingWindow", "FixedWindow", "LeakyBucket",
    "RateLimiter", "get_rate_limiter",
    "CircuitState", "CircuitConfig", "CircuitEvent", "CircuitStats",
    "CircuitBreaker", "CircuitBreakerManager", "CircuitOpenError",
    "get_circuit_manager",
    "ConnStatus", "PooledConnection", "PoolConfig", "PoolStats",
    "ConnectionPool", "ConnectionPoolManager", "get_pool_manager",
    "MetricType", "TimerRecord", "LatencySnapshot", "ThroughputSnapshot",
    "ResourceSnapshot", "PerformanceBaseline", "BaselineDeviation",
    "LatencyTracker", "ThroughputTracker", "ResourceMonitor",
    "PerformanceMonitor", "get_performance_monitor",
]
