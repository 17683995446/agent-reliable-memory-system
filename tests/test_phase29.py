#!/usr/bin/env python3
"""
第29阶段验证测试 - 缓存与性能优化模块 (阶段346-350)

覆盖模块：
- 阶段346: CacheManager - LRU缓存/分层缓存/多命名空间
- 阶段347: RateLimiter - 令牌桶/滑动窗口/固定窗口/漏桶
- 阶段348: CircuitBreaker - 三态状态机/半开探测/降级回退
- 阶段349: ConnectionPool - 阻塞获取/健康检查/生命周期
- 阶段350: PerformanceMonitor - 延迟/吞吐/资源追踪
"""

import sys
import os
import time
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from cache_perf.cache_manager import (
    LRUCache, TieredCache, CacheManager, CacheEntry,
    CacheStats, EvictionPolicy, CacheLevel, get_cache_manager,
)
from cache_perf.rate_limiter import (
    TokenBucket, SlidingWindow, FixedWindow, LeakyBucket,
    RateLimiter, LimitRule, LimitResult, LimitStrategy,
    LimitStats, get_rate_limiter,
)
from cache_perf.circuit_breaker import (
    CircuitBreaker, CircuitBreakerManager, CircuitState,
    CircuitConfig, CircuitEvent, CircuitStats, CircuitOpenError,
    get_circuit_manager,
)
from cache_perf.connection_pool import (
    ConnectionPool, ConnectionPoolManager, PooledConnection,
    PoolConfig, PoolStats, ConnStatus, get_pool_manager,
)
from cache_perf.performance_monitor import (
    PerformanceMonitor, LatencyTracker, ThroughputTracker,
    ResourceMonitor, PerformanceBaseline, BaselineDeviation,
    LatencySnapshot, ThroughputSnapshot, ResourceSnapshot,
    TimerRecord, MetricType, get_performance_monitor,
)


# ============================================================
# 阶段346: CacheManager 测试
# ============================================================

class TestCacheEntry(unittest.TestCase):
    """CacheEntry 数据结构测试"""

    def test_basic_properties(self):
        entry = CacheEntry(key="k1", value="v1")
        self.assertEqual(entry.key, "k1")
        self.assertEqual(entry.value, "v1")
        self.assertTrue(entry.created_at > 0)
        self.assertTrue(entry.accessed_at > 0)
        self.assertEqual(entry.access_count, 0)
        self.assertEqual(entry.ttl, 0.0)
        self.assertFalse(entry.is_expired)
        self.assertEqual(entry.remaining_ttl, float('inf'))

    def test_ttl_expiration(self):
        entry = CacheEntry(key="k1", value="v1", ttl=0.01)
        time.sleep(0.02)
        self.assertTrue(entry.is_expired)
        self.assertEqual(entry.remaining_ttl, 0)

    def test_no_expiration_with_zero_ttl(self):
        entry = CacheEntry(key="k1", value="v1", ttl=0)
        time.sleep(0.01)
        self.assertFalse(entry.is_expired)
        self.assertEqual(entry.remaining_ttl, float('inf'))

    def test_tags(self):
        entry = CacheEntry(key="k1", value="v1", tags={"tag1", "tag2"})
        self.assertIn("tag1", entry.tags)
        self.assertIn("tag2", entry.tags)


class TestCacheStats(unittest.TestCase):
    """CacheStats 统计测试"""

    def test_hit_rate(self):
        stats = CacheStats(hits=80, misses=20)
        self.assertEqual(stats.hit_rate, 0.8)
        self.assertEqual(stats.miss_rate, 0.2)

    def test_zero_division(self):
        stats = CacheStats()
        self.assertEqual(stats.hit_rate, 0.0)
        self.assertEqual(stats.miss_rate, 0.0)


class TestLRUCache(unittest.TestCase):
    """LRU缓存核心测试"""

    def test_basic_set_get(self):
        cache = LRUCache(max_size=10)
        cache.set("key1", "value1")
        self.assertEqual(cache.get("key1"), "value1")

    def test_get_miss(self):
        cache = LRUCache(max_size=10)
        self.assertIsNone(cache.get("nonexistent"))

    def test_has_key(self):
        cache = LRUCache(max_size=10)
        cache.set("key1", "value1")
        self.assertTrue(cache.has("key1"))
        self.assertFalse(cache.has("nonexistent"))

    def test_delete(self):
        cache = LRUCache(max_size=10)
        cache.set("key1", "value1")
        self.assertTrue(cache.delete("key1"))
        self.assertFalse(cache.has("key1"))
        self.assertFalse(cache.delete("nonexistent"))

    def test_clear(self):
        cache = LRUCache(max_size=10)
        for i in range(5):
            cache.set(f"key{i}", f"value{i}")
        count = cache.clear()
        self.assertEqual(count, 5)
        self.assertEqual(len(cache.keys()), 0)

    def test_eviction(self):
        cache = LRUCache(max_size=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache.set("d", 4)  # 应淘汰 "a"
        self.assertIsNone(cache.get("a"))
        self.assertEqual(cache.get("d"), 4)

    def test_lru_order(self):
        cache = LRUCache(max_size=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache.get("a")  # 访问a，使其变为最近使用
        cache.set("d", 4)  # 应淘汰 "b"（最久未使用）
        self.assertIsNone(cache.get("b"))
        self.assertEqual(cache.get("a"), 1)
        self.assertEqual(cache.get("d"), 4)

    def test_ttl_expiration(self):
        cache = LRUCache(max_size=10)
        cache.set("key1", "value1", ttl=0.05)
        time.sleep(0.1)
        self.assertIsNone(cache.get("key1"))

    def test_default_ttl(self):
        cache = LRUCache(max_size=10, default_ttl=0.05)
        cache.set("key1", "value1")
        time.sleep(0.1)
        self.assertIsNone(cache.get("key1"))

    def test_get_or_set(self):
        cache = LRUCache(max_size=10)
        call_count = [0]
        def factory():
            call_count[0] += 1
            return "computed"
        # 第一次调用应触发factory
        result = cache.get_or_set("key1", factory)
        self.assertEqual(result, "computed")
        self.assertEqual(call_count[0], 1)
        # 第二次应命中缓存
        result = cache.get_or_set("key1", factory)
        self.assertEqual(result, "computed")
        self.assertEqual(call_count[0], 1)

    def test_invalidate_by_prefix(self):
        cache = LRUCache(max_size=100)
        cache.set("user:1", "a")
        cache.set("user:2", "b")
        cache.set("item:1", "c")
        count = cache.invalidate(pattern="user:")
        self.assertEqual(count, 2)
        self.assertIsNone(cache.get("user:1"))
        self.assertIsNone(cache.get("user:2"))
        self.assertEqual(cache.get("item:1"), "c")

    def test_invalidate_by_tags(self):
        cache = LRUCache(max_size=100)
        cache.set("k1", "v1", tags={"important"})
        cache.set("k2", "v2", tags={"important"})
        cache.set("k3", "v3", tags={"other"})
        count = cache.invalidate(tags={"important"})
        self.assertEqual(count, 2)
        self.assertIsNone(cache.get("k1"))
        self.assertEqual(cache.get("k3"), "v3")

    def test_cleanup_expired(self):
        cache = LRUCache(max_size=100)
        cache.set("exp1", "v1", ttl=0.05)
        cache.set("exp2", "v2", ttl=0.05)
        cache.set("perm", "v3")
        time.sleep(0.1)
        count = cache.cleanup_expired()
        self.assertEqual(count, 2)
        self.assertEqual(cache.get("perm"), "v3")

    def test_keys_values_items(self):
        cache = LRUCache(max_size=10)
        cache.set("a", 1)
        cache.set("b", 2)
        self.assertEqual(sorted(cache.keys()), ["a", "b"])
        self.assertEqual(sorted(cache.values()), [1, 2])
        items = dict(cache.items())
        self.assertEqual(items, {"a": 1, "b": 2})

    def test_stats(self):
        cache = LRUCache(max_size=10)
        cache.set("a", 1)
        cache.get("a")  # hit
        cache.get("miss")  # miss
        stats = cache.get_stats()
        self.assertEqual(stats["hits"], 1)
        self.assertEqual(stats["misses"], 1)
        self.assertEqual(stats["sets"], 1)
        self.assertEqual(stats["size"], 1)
        self.assertEqual(stats["max_size"], 10)
        self.assertAlmostEqual(stats["hit_rate"], 0.5, places=4)

    def test_reset_stats(self):
        cache = LRUCache(max_size=10)
        cache.set("a", 1)
        cache.get("a")
        cache.get("miss")
        cache.reset_stats()
        stats = cache.get_stats()
        self.assertEqual(stats["hits"], 0)
        self.assertEqual(stats["misses"], 0)

    def test_overwrite_existing_key(self):
        cache = LRUCache(max_size=10)
        cache.set("key1", "old")
        cache.set("key1", "new")
        self.assertEqual(cache.get("key1"), "new")
        stats = cache.get_stats()
        self.assertEqual(stats["size"], 1)

    def test_thread_safety(self):
        cache = LRUCache(max_size=100)
        errors = []

        def writer(start):
            try:
                for i in range(50):
                    cache.set(f"key_{start}_{i}", f"value_{i}")
            except Exception as e:
                errors.append(e)

        def reader(start):
            try:
                for i in range(50):
                    cache.get(f"key_{start}_{i}")
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(4):
            threads.append(threading.Thread(target=writer, args=(i,)))
            threads.append(threading.Thread(target=reader, args=(i,)))
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(errors), 0)


class TestTieredCache(unittest.TestCase):
    """分层缓存测试"""

    def test_basic_set_get(self):
        tc = TieredCache(l1_size=10, l2_size=100)
        tc.set("key1", "value1")
        self.assertEqual(tc.get("key1"), "value1")

    def test_l1_miss_l2_hit(self):
        tc = TieredCache(l1_size=10, l2_size=100)
        tc.set("key1", "value1")
        # 清除L1
        tc.l1.clear()
        # L2应仍存在，且自动回填L1
        value = tc.get("key1")
        self.assertEqual(value, "value1")
        # 回填后L1也有
        self.assertEqual(tc.l1.get("key1"), "value1")

    def test_miss_handler(self):
        tc = TieredCache(l1_size=10, l2_size=100)
        tc.set_miss_handler(lambda key: f"loaded_{key}")
        result = tc.get("new_key")
        self.assertEqual(result, "loaded_new_key")
        # 回填后应命中缓存
        result = tc.get("new_key")
        self.assertEqual(result, "loaded_new_key")

    def test_delete_both_levels(self):
        tc = TieredCache(l1_size=10, l2_size=100)
        tc.set("key1", "value1")
        self.assertTrue(tc.delete("key1"))
        self.assertIsNone(tc.get("key1"))

    def test_invalidate_both_levels(self):
        tc = TieredCache(l1_size=10, l2_size=100)
        tc.set("user:1", "a")
        tc.set("user:2", "b")
        count = tc.invalidate(pattern="user:")
        self.assertEqual(count, 4)  # L1 2个 + L2 2个

    def test_cleanup(self):
        tc = TieredCache(l1_size=10, l2_size=100, l1_ttl=0.05, l2_ttl=0.05)
        tc.set("exp", "v", l1_ttl=0.05, l2_ttl=0.05)
        time.sleep(0.1)
        count = tc.cleanup()
        self.assertGreater(count, 0)

    def test_stats(self):
        tc = TieredCache(l1_size=10, l2_size=100)
        tc.set("k1", "v1")
        tc.get("k1")  # L1 hit
        stats = tc.get_stats()
        self.assertIn("l1", stats)
        self.assertIn("l2", stats)
        self.assertIn("combined_hit_rate", stats)

    def test_l1_l2_properties(self):
        tc = TieredCache(l1_size=10, l2_size=100)
        self.assertIsInstance(tc.l1, LRUCache)
        self.assertIsInstance(tc.l2, LRUCache)


class TestCacheManager(unittest.TestCase):
    """缓存管理器测试"""

    def test_default_namespace(self):
        cm = CacheManager()
        cm.set("key1", "value1")
        self.assertEqual(cm.get("key1"), "value1")

    def test_multiple_namespaces(self):
        cm = CacheManager()
        cm.set("key1", "ns1_val", namespace="ns1")
        cm.set("key1", "ns2_val", namespace="ns2")
        self.assertEqual(cm.get("key1", namespace="ns1"), "ns1_val")
        self.assertEqual(cm.get("key1", namespace="ns2"), "ns2_val")

    def test_get_cache_auto_create(self):
        cm = CacheManager()
        cache = cm.get_cache("new_ns")
        self.assertIsInstance(cache, LRUCache)
        # 再次获取应为同一实例
        cache2 = cm.get_cache("new_ns")
        self.assertIs(cache, cache2)

    def test_get_tiered_auto_create(self):
        cm = CacheManager()
        tc = cm.get_tiered("tiered_ns")
        self.assertIsInstance(tc, TieredCache)
        tc2 = cm.get_tiered("tiered_ns")
        self.assertIs(tc, tc2)

    def test_invalidate_namespace(self):
        cm = CacheManager()
        cm.set("k1", "v1", namespace="temp")
        count = cm.invalidate_namespace("temp")
        self.assertEqual(count, 1)
        self.assertIsNone(cm.get("k1", namespace="temp"))

    def test_stats(self):
        cm = CacheManager()
        cm.set("k1", "v1")
        cm.set("k2", "v2", namespace="ns2")
        stats = cm.get_stats()
        self.assertEqual(stats["namespaces"], 2)
        self.assertIn("caches", stats)
        self.assertIn("default", stats["caches"])

    def test_global_singleton(self):
        cm1 = get_cache_manager()
        cm2 = get_cache_manager()
        self.assertIs(cm1, cm2)


# ============================================================
# 阶段347: RateLimiter 测试
# ============================================================

class TestTokenBucket(unittest.TestCase):
    """令牌桶测试"""

    def test_initial_burst(self):
        bucket = TokenBucket(rate=10, burst=5)
        # 初始应有burst个令牌
        for _ in range(5):
            result = bucket.consume()
            self.assertTrue(result.allowed)
        # 第6个应被拒绝
        result = bucket.consume()
        self.assertFalse(result.allowed)
        self.assertGreater(result.retry_after, 0)

    def test_refill(self):
        bucket = TokenBucket(rate=1000, burst=3)  # 高速率便于测试
        for _ in range(3):
            bucket.consume()
        time.sleep(0.05)  # 等待补充
        result = bucket.consume()
        self.assertTrue(result.allowed)

    def test_remaining(self):
        bucket = TokenBucket(rate=10, burst=5)
        result = bucket.consume()
        self.assertTrue(result.allowed)
        self.assertLessEqual(result.remaining, 4)
        self.assertEqual(result.limit, 5)

    def test_available_property(self):
        bucket = TokenBucket(rate=10, burst=5)
        avail = bucket.available
        self.assertGreaterEqual(avail, 0)
        self.assertLessEqual(avail, 5)

    def test_batch_consume(self):
        bucket = TokenBucket(rate=10, burst=10)
        result = bucket.consume(count=5)
        self.assertTrue(result.allowed)
        result = bucket.consume(count=10)
        self.assertFalse(result.allowed)


class TestSlidingWindow(unittest.TestCase):
    """滑动窗口测试"""

    def test_within_limit(self):
        sw = SlidingWindow(limit=5, window_seconds=1.0)
        for _ in range(5):
            result = sw.consume()
            self.assertTrue(result.allowed)

    def test_exceed_limit(self):
        sw = SlidingWindow(limit=3, window_seconds=1.0)
        for _ in range(3):
            sw.consume()
        result = sw.consume()
        self.assertFalse(result.allowed)

    def test_window_reset(self):
        sw = SlidingWindow(limit=3, window_seconds=0.1)
        for _ in range(3):
            sw.consume()
        time.sleep(0.15)
        result = sw.consume()
        self.assertTrue(result.allowed)

    def test_current_count(self):
        sw = SlidingWindow(limit=10, window_seconds=1.0)
        for _ in range(3):
            sw.consume()
        self.assertEqual(sw.current_count, 3)

    def test_reset_at_field(self):
        sw = SlidingWindow(limit=5, window_seconds=1.0)
        result = sw.consume()
        self.assertTrue(result.allowed)
        self.assertGreater(result.reset_at, 0)


class TestFixedWindow(unittest.TestCase):
    """固定窗口测试"""

    def test_within_limit(self):
        fw = FixedWindow(limit=5, window_seconds=1.0)
        for _ in range(5):
            result = fw.consume()
            self.assertTrue(result.allowed)

    def test_exceed_limit(self):
        fw = FixedWindow(limit=3, window_seconds=1.0)
        for _ in range(3):
            fw.consume()
        result = fw.consume()
        self.assertFalse(result.allowed)

    def test_window_reset(self):
        fw = FixedWindow(limit=3, window_seconds=0.1)
        for _ in range(3):
            fw.consume()
        time.sleep(0.15)
        result = fw.consume()
        self.assertTrue(result.allowed)

    def test_current_count(self):
        fw = FixedWindow(limit=10, window_seconds=1.0)
        for _ in range(4):
            fw.consume()
        self.assertEqual(fw.current_count, 4)


class TestLeakyBucket(unittest.TestCase):
    """漏桶测试"""

    def test_within_capacity(self):
        lb = LeakyBucket(rate=10, capacity=5)
        for _ in range(5):
            result = lb.consume()
            self.assertTrue(result.allowed)

    def test_overflow(self):
        lb = LeakyBucket(rate=10, capacity=3)
        for _ in range(3):
            lb.consume()
        result = lb.consume()
        self.assertFalse(result.allowed)

    def test_leak_allows_new(self):
        lb = LeakyBucket(rate=1000, capacity=3)  # 高速率
        for _ in range(3):
            lb.consume()
        time.sleep(0.05)
        result = lb.consume()
        self.assertTrue(result.allowed)

    def test_queue_size(self):
        lb = LeakyBucket(rate=10, capacity=5)
        for _ in range(3):
            lb.consume()
        qs = lb.queue_size
        self.assertGreaterEqual(qs, 0)


class TestRateLimiter(unittest.TestCase):
    """速率限制器集成测试"""

    def test_add_remove_rule(self):
        rl = RateLimiter()
        rule = LimitRule(name="api_limit", strategy=LimitStrategy.TOKEN_BUCKET,
                         rate=10, burst=5)
        rl.add_rule(rule)
        self.assertTrue(rl.remove_rule("api_limit"))
        self.assertFalse(rl.remove_rule("nonexistent"))

    def test_allow_without_rule(self):
        rl = RateLimiter()
        result = rl.allow("user1")
        self.assertTrue(result.allowed)
        self.assertEqual(result.remaining, -1)

    def test_allow_with_token_bucket_rule(self):
        rl = RateLimiter()
        rule = LimitRule(name="tb", strategy=LimitStrategy.TOKEN_BUCKET,
                         rate=10, burst=3)
        rl.add_rule(rule)
        for _ in range(3):
            result = rl.allow("user1", rule_name="tb")
            self.assertTrue(result.allowed)
        result = rl.allow("user1", rule_name="tb")
        self.assertFalse(result.allowed)

    def test_allow_with_sliding_window_rule(self):
        rl = RateLimiter()
        # limit = rate * window_seconds = 3 * 1.0 = 3
        rule = LimitRule(name="sw", strategy=LimitStrategy.SLIDING_WINDOW,
                         rate=3, burst=3, window_seconds=1.0)
        rl.add_rule(rule)
        for _ in range(3):
            result = rl.allow("user1", rule_name="sw")
            self.assertTrue(result.allowed)
        result = rl.allow("user1", rule_name="sw")
        self.assertFalse(result.allowed)

    def test_allow_with_fixed_window_rule(self):
        rl = RateLimiter()
        # limit = rate * window_seconds = 3 * 1.0 = 3
        rule = LimitRule(name="fw", strategy=LimitStrategy.FIXED_WINDOW,
                         rate=3, burst=3, window_seconds=1.0)
        rl.add_rule(rule)
        for _ in range(3):
            result = rl.allow("user1", rule_name="fw")
            self.assertTrue(result.allowed)
        result = rl.allow("user1", rule_name="fw")
        self.assertFalse(result.allowed)

    def test_allow_with_leaky_bucket_rule(self):
        rl = RateLimiter()
        rule = LimitRule(name="lb", strategy=LimitStrategy.LEAKY_BUCKET,
                         rate=10, burst=3)
        rl.add_rule(rule)
        for _ in range(3):
            result = rl.allow("user1", rule_name="lb")
            self.assertTrue(result.allowed)
        result = rl.allow("user1", rule_name="lb")
        self.assertFalse(result.allowed)

    def test_multi_key_isolation(self):
        rl = RateLimiter()
        rule = LimitRule(name="tb", strategy=LimitStrategy.TOKEN_BUCKET,
                         rate=10, burst=2)
        rl.add_rule(rule)
        # user1消耗2个
        rl.allow("user1", rule_name="tb")
        rl.allow("user1", rule_name="tb")
        result = rl.allow("user1", rule_name="tb")
        self.assertFalse(result.allowed)
        # user2应不受影响
        result = rl.allow("user2", rule_name="tb")
        self.assertTrue(result.allowed)

    def test_check_without_consume(self):
        rl = RateLimiter()
        rule = LimitRule(name="tb", strategy=LimitStrategy.TOKEN_BUCKET,
                         rate=10, burst=1)
        rl.add_rule(rule)
        self.assertTrue(rl.check("user1", rule_name="tb"))
        # check不消费配额
        self.assertTrue(rl.check("user1", rule_name="tb"))

    def test_stats(self):
        rl = RateLimiter()
        rule = LimitRule(name="tb", strategy=LimitStrategy.TOKEN_BUCKET,
                         rate=10, burst=2)
        rl.add_rule(rule)
        rl.allow("u1", rule_name="tb")
        rl.allow("u1", rule_name="tb")
        rl.allow("u1", rule_name="tb")  # rejected
        stats = rl.get_stats()
        self.assertEqual(stats["rules"], 1)
        self.assertEqual(stats["total_requests"], 3)
        self.assertEqual(stats["allowed"], 2)
        self.assertEqual(stats["rejected"], 1)
        self.assertAlmostEqual(stats["rejection_rate"], 1/3, places=4)

    def test_list_rules(self):
        rl = RateLimiter()
        rl.add_rule(LimitRule(name="r1", strategy=LimitStrategy.TOKEN_BUCKET))
        rl.add_rule(LimitRule(name="r2", strategy=LimitStrategy.SLIDING_WINDOW))
        rules = rl.list_rules()
        self.assertEqual(len(rules), 2)
        names = [r["name"] for r in rules]
        self.assertIn("r1", names)
        self.assertIn("r2", names)

    def test_reset(self):
        rl = RateLimiter()
        rule = LimitRule(name="tb", strategy=LimitStrategy.TOKEN_BUCKET,
                         rate=10, burst=2)
        rl.add_rule(rule)
        rl.allow("u1", rule_name="tb")
        rl.allow("u1", rule_name="tb")
        rl.reset()
        # 重置后桶被清空，应重新有burst个令牌
        result = rl.allow("u1", rule_name="tb")
        self.assertTrue(result.allowed)

    def test_global_singleton(self):
        rl1 = get_rate_limiter()
        rl2 = get_rate_limiter()
        self.assertIs(rl1, rl2)


class TestLimitStats(unittest.TestCase):
    """LimitStats 测试"""

    def test_rejection_rate(self):
        stats = LimitStats(total_requests=100, rejected_requests=10)
        self.assertAlmostEqual(stats.rejection_rate, 0.1)

    def test_zero_division(self):
        stats = LimitStats()
        self.assertEqual(stats.rejection_rate, 0.0)


# ============================================================
# 阶段348: CircuitBreaker 测试
# ============================================================

class TestCircuitBreaker(unittest.TestCase):
    """熔断器核心测试"""

    def test_initial_state_closed(self):
        cb = CircuitBreaker("test")
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertTrue(cb.is_closed)
        self.assertFalse(cb.is_open)

    def test_successful_call(self):
        cb = CircuitBreaker("test")
        result = cb.call(lambda: 42)
        self.assertEqual(result, 42)
        stats = cb.get_stats()
        self.assertEqual(stats["total_calls"], 1)
        self.assertEqual(stats["success"], 1)

    def test_failed_call(self):
        cb = CircuitBreaker("test")
        with self.assertRaises(ZeroDivisionError):
            cb.call(lambda: 1/0)
        stats = cb.get_stats()
        self.assertEqual(stats["failure"], 1)

    def test_opens_after_threshold(self):
        config = CircuitConfig(failure_threshold=3, timeout_seconds=0.1)
        cb = CircuitBreaker("test", config)
        for _ in range(3):
            with self.assertRaises(ZeroDivisionError):
                cb.call(lambda: 1/0)
        self.assertEqual(cb.state, CircuitState.OPEN)

    def test_open_rejects_calls(self):
        config = CircuitConfig(failure_threshold=2, timeout_seconds=60)
        cb = CircuitBreaker("test", config)
        for _ in range(2):
            with self.assertRaises(ZeroDivisionError):
                cb.call(lambda: 1/0)
        # 熔断后应抛出CircuitOpenError
        with self.assertRaises(CircuitOpenError):
            cb.call(lambda: "should not run")

    def test_fallback_on_open(self):
        config = CircuitConfig(failure_threshold=2, timeout_seconds=60)
        cb = CircuitBreaker("test", config)
        cb.set_fallback(lambda: "fallback_value")
        # 触发熔断 - fallback会捕获异常并返回降级值
        result1 = cb.call(lambda: 1/0)
        self.assertEqual(result1, "fallback_value")
        result2 = cb.call(lambda: 1/0)
        self.assertEqual(result2, "fallback_value")
        # 熔断后应返回降级值（不再调用原始函数）
        result3 = cb.call(lambda: "should not run")
        self.assertEqual(result3, "fallback_value")

    def test_fallback_on_failure(self):
        cb = CircuitBreaker("test")
        cb.set_fallback(lambda: "fallback")
        result = cb.call(lambda: (_ for _ in ()).throw(ZeroDivisionError("err")))
        self.assertEqual(result, "fallback")

    def test_half_open_transition(self):
        config = CircuitConfig(failure_threshold=2, timeout_seconds=0.1,
                               success_threshold=2)
        cb = CircuitBreaker("test", config)
        # 触发熔断
        for _ in range(2):
            with self.assertRaises(ZeroDivisionError):
                cb.call(lambda: 1/0)
        self.assertEqual(cb.state, CircuitState.OPEN)
        # 等待超时进入半开
        time.sleep(0.15)
        # 半开状态下成功调用
        result = cb.call(lambda: "ok")
        self.assertEqual(result, "ok")
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)
        # 再成功一次达到success_threshold
        result = cb.call(lambda: "ok")
        self.assertEqual(result, "ok")
        self.assertEqual(cb.state, CircuitState.CLOSED)

    def test_half_open_failure_reopens(self):
        config = CircuitConfig(failure_threshold=2, timeout_seconds=0.1)
        cb = CircuitBreaker("test", config)
        for _ in range(2):
            with self.assertRaises(ZeroDivisionError):
                cb.call(lambda: 1/0)
        self.assertEqual(cb.state, CircuitState.OPEN)
        time.sleep(0.15)
        # 半开状态下失败应重新打开
        with self.assertRaises(ZeroDivisionError):
            cb.call(lambda: 1/0)
        self.assertEqual(cb.state, CircuitState.OPEN)

    def test_state_change_listener(self):
        cb = CircuitBreaker("test")
        events = []
        cb.add_listener(lambda e: events.append(e))
        config = CircuitConfig(failure_threshold=1, timeout_seconds=0.1)
        cb._config = config
        with self.assertRaises(ZeroDivisionError):
            cb.call(lambda: 1/0)
        self.assertEqual(cb.state, CircuitState.OPEN)
        self.assertTrue(len(events) > 0)
        self.assertEqual(events[0].state, CircuitState.OPEN)

    def test_force_open_close(self):
        cb = CircuitBreaker("test")
        cb.force_open()
        self.assertEqual(cb.state, CircuitState.OPEN)
        cb.force_close()
        self.assertEqual(cb.state, CircuitState.CLOSED)

    def test_reset(self):
        config = CircuitConfig(failure_threshold=2, timeout_seconds=0.1)
        cb = CircuitBreaker("test", config)
        for _ in range(2):
            with self.assertRaises(ZeroDivisionError):
                cb.call(lambda: 1/0)
        cb.reset()
        self.assertEqual(cb.state, CircuitState.CLOSED)
        stats = cb.get_stats()
        self.assertEqual(stats["total_calls"], 0)
        self.assertEqual(stats["failure"], 0)

    def test_stats(self):
        cb = CircuitBreaker("test")
        cb.call(lambda: "ok")
        with self.assertRaises(ZeroDivisionError):
            cb.call(lambda: 1/0)
        stats = cb.get_stats()
        self.assertEqual(stats["name"], "test")
        self.assertEqual(stats["total_calls"], 2)
        self.assertEqual(stats["success"], 1)
        self.assertEqual(stats["failure"], 1)
        self.assertEqual(stats["state"], "closed")
        self.assertIn("config", stats)

    def test_failure_rate(self):
        cs = CircuitStats(total_calls=100, failure_calls=25)
        self.assertAlmostEqual(cs.failure_rate, 0.25)

    def test_circuit_open_error(self):
        with self.assertRaises(CircuitOpenError):
            raise CircuitOpenError("test")


class TestCircuitBreakerManager(unittest.TestCase):
    """熔断器管理器测试"""

    def test_create_get_remove(self):
        mgr = CircuitBreakerManager()
        cb = mgr.create("api_cb")
        self.assertIsInstance(cb, CircuitBreaker)
        self.assertIs(mgr.get("api_cb"), cb)
        self.assertTrue(mgr.remove("api_cb"))
        self.assertIsNone(mgr.get("api_cb"))
        self.assertFalse(mgr.remove("nonexistent"))

    def test_get_all_stats(self):
        mgr = CircuitBreakerManager()
        mgr.create("cb1")
        mgr.create("cb2")
        stats = mgr.get_all_stats()
        self.assertIn("cb1", stats)
        self.assertIn("cb2", stats)

    def test_force_open_close_all(self):
        mgr = CircuitBreakerManager()
        mgr.create("cb1")
        mgr.create("cb2")
        mgr.force_open_all()
        self.assertEqual(mgr.get("cb1").state, CircuitState.OPEN)
        self.assertEqual(mgr.get("cb2").state, CircuitState.OPEN)
        mgr.force_close_all()
        self.assertEqual(mgr.get("cb1").state, CircuitState.CLOSED)
        self.assertEqual(mgr.get("cb2").state, CircuitState.CLOSED)

    def test_stats(self):
        mgr = CircuitBreakerManager()
        mgr.create("cb1")
        mgr.create("cb2")
        stats = mgr.get_stats()
        self.assertEqual(stats["total"], 2)
        self.assertIn("by_state", stats)

    def test_global_singleton(self):
        mgr1 = get_circuit_manager()
        mgr2 = get_circuit_manager()
        self.assertIs(mgr1, mgr2)


# ============================================================
# 阶段349: ConnectionPool 测试
# ============================================================

class TestConnectionPool(unittest.TestCase):
    """连接池核心测试"""

    def test_acquire_and_release(self):
        pool = ConnectionPool(name="test",
                              config=PoolConfig(max_size=5),
                              factory=lambda: {"conn": "mock"})
        pc = pool.acquire(timeout=1.0)
        self.assertIsNotNone(pc)
        self.assertIsInstance(pc, PooledConnection)
        self.assertEqual(pc.status, ConnStatus.BORROWED)
        self.assertTrue(pool.release(pc.id))

    def test_connection_reuse(self):
        created = [0]
        def factory():
            created[0] += 1
            return {"conn_id": created[0]}

        pool = ConnectionPool(name="test",
                              config=PoolConfig(max_size=5),
                              factory=factory)
        pc1 = pool.acquire(timeout=1.0)
        pool.release(pc1.id)
        pc2 = pool.acquire(timeout=1.0)
        # 应复用同一连接
        self.assertEqual(pc1.id, pc2.id)
        self.assertEqual(created[0], 1)  # 只创建了一次

    def test_max_size_limit(self):
        pool = ConnectionPool(name="test",
                              config=PoolConfig(max_size=2, acquire_timeout=0.1),
                              factory=lambda: {"conn": "mock"})
        pc1 = pool.acquire(timeout=1.0)
        pc2 = pool.acquire(timeout=1.0)
        # 池已满，应超时
        pc3 = pool.acquire(timeout=0.1)
        self.assertIsNone(pc3)
        pool.release(pc1.id)
        pool.release(pc2.id)

    def test_acquire_timeout(self):
        pool = ConnectionPool(name="test",
                              config=PoolConfig(max_size=1, acquire_timeout=0.05),
                              factory=lambda: {"conn": "mock"})
        pc1 = pool.acquire(timeout=1.0)
        pc2 = pool.acquire(timeout=0.05)
        self.assertIsNone(pc2)
        stats = pool.get_stats()
        self.assertEqual(stats["total_timeouts"], 1)
        pool.release(pc1.id)

    def test_release_nonexistent(self):
        pool = ConnectionPool(name="test")
        self.assertFalse(pool.release("nonexistent"))

    def test_health_check(self):
        healthy_flag = [True]
        def checker(conn):
            return healthy_flag[0]

        pool = ConnectionPool(name="test",
                              config=PoolConfig(max_size=5),
                              factory=lambda: {"conn": "mock"},
                              health_checker=checker)
        pc = pool.acquire(timeout=1.0)
        pool.release(pc.id)
        # 健康检查应通过
        result = pool.health_check()
        self.assertEqual(result["healthy"], 1)
        self.assertEqual(result["unhealthy"], 0)

        # 标记不健康
        healthy_flag[0] = False
        result = pool.health_check()
        self.assertEqual(result["removed"], 1)

    def test_factory_error(self):
        def bad_factory():
            raise RuntimeError("create failed")

        pool = ConnectionPool(name="test",
                              config=PoolConfig(max_size=5),
                              factory=bad_factory)
        pc = pool.acquire(timeout=0.1)
        self.assertIsNone(pc)

    def test_close_pool(self):
        pool = ConnectionPool(name="test",
                              config=PoolConfig(max_size=5),
                              factory=lambda: {"conn": "mock"})
        pc = pool.acquire(timeout=1.0)
        pool.close()
        # 关闭后acquire应返回None
        pc2 = pool.acquire(timeout=0.1)
        self.assertIsNone(pc2)

    def test_stats(self):
        pool = ConnectionPool(name="test",
                              config=PoolConfig(max_size=5),
                              factory=lambda: {"conn": "mock"})
        pc = pool.acquire(timeout=1.0)
        stats = pool.get_stats()
        self.assertEqual(stats["name"], "test")
        self.assertEqual(stats["active"], 1)
        self.assertEqual(stats["idle"], 0)
        self.assertEqual(stats["total_borrows"], 1)
        self.assertEqual(stats["max_size"], 5)
        pool.release(pc.id)
        stats = pool.get_stats()
        self.assertEqual(stats["active"], 0)
        self.assertEqual(stats["idle"], 1)
        self.assertEqual(stats["total_returns"], 1)

    def test_borrow_count(self):
        pool = ConnectionPool(name="test",
                              config=PoolConfig(max_size=5),
                              factory=lambda: {"conn": "mock"})
        pc = pool.acquire(timeout=1.0)
        self.assertEqual(pc.borrow_count, 1)
        pool.release(pc.id)
        pc = pool.acquire(timeout=1.0)
        self.assertEqual(pc.borrow_count, 2)
        pool.release(pc.id)

    def test_pooled_connection_auto_id(self):
        pc = PooledConnection(conn={"data": "test"})
        self.assertTrue(len(pc.id) > 0)
        self.assertTrue(pc.created_at > 0)


class TestConnectionPoolManager(unittest.TestCase):
    """连接池管理器测试"""

    def test_create_get_remove(self):
        mgr = ConnectionPoolManager()
        pool = mgr.create_pool("db", factory=lambda: {"conn": "db"})
        self.assertIsInstance(pool, ConnectionPool)
        self.assertIs(mgr.get_pool("db"), pool)
        self.assertTrue(mgr.remove_pool("db"))
        self.assertIsNone(mgr.get_pool("db"))

    def test_remove_closes_pool(self):
        mgr = ConnectionPoolManager()
        pool = mgr.create_pool("db", factory=lambda: {"conn": "db"})
        mgr.remove_pool("db")
        # 关闭后acquire应返回None
        pc = pool.acquire(timeout=0.1)
        self.assertIsNone(pc)

    def test_close_all(self):
        mgr = ConnectionPoolManager()
        mgr.create_pool("db1", factory=lambda: {"conn": "db1"})
        mgr.create_pool("db2", factory=lambda: {"conn": "db2"})
        mgr.close_all()
        pool1 = mgr.get_pool("db1")
        pc = pool1.acquire(timeout=0.1)
        self.assertIsNone(pc)

    def test_get_stats(self):
        mgr = ConnectionPoolManager()
        mgr.create_pool("db", factory=lambda: {"conn": "db"})
        stats = mgr.get_stats()
        self.assertIn("db", stats)

    def test_global_singleton(self):
        mgr1 = get_pool_manager()
        mgr2 = get_pool_manager()
        self.assertIs(mgr1, mgr2)


class TestPoolStats(unittest.TestCase):
    """PoolStats 测试"""

    def test_utilization(self):
        ps = PoolStats(active=3, idle=7)
        self.assertAlmostEqual(ps.utilization, 0.3)

    def test_zero_utilization(self):
        ps = PoolStats()
        self.assertEqual(ps.utilization, 0.0)


# ============================================================
# 阶段350: PerformanceMonitor 测试
# ============================================================

class TestLatencyTracker(unittest.TestCase):
    """延迟追踪器测试"""

    def test_start_stop(self):
        lt = LatencyTracker()
        lt.start("op1")
        time.sleep(0.01)
        duration = lt.stop("op1")
        self.assertIsNotNone(duration)
        self.assertGreaterEqual(duration, 5)  # 至少5ms

    def test_stop_without_start(self):
        lt = LatencyTracker()
        result = lt.stop("nonexistent")
        self.assertIsNone(result)

    def test_record_direct(self):
        lt = LatencyTracker()
        lt.record("op1", 10.5)
        lt.record("op1", 20.0)
        lt.record("op1", 30.0)
        snap = lt.get_snapshot("op1")
        self.assertEqual(snap.count, 3)
        self.assertAlmostEqual(snap.avg_ms, 20.167, places=1)
        self.assertAlmostEqual(snap.min_ms, 10.5, places=1)
        self.assertAlmostEqual(snap.max_ms, 30.0, places=1)

    def test_percentiles(self):
        lt = LatencyTracker()
        for i in range(100):
            lt.record("op1", float(i + 1))  # 1ms ~ 100ms
        snap = lt.get_snapshot("op1")
        self.assertEqual(snap.count, 100)
        self.assertAlmostEqual(snap.p50_ms, 50.5, places=0)
        self.assertGreater(snap.p95_ms, 90)
        self.assertGreater(snap.p99_ms, 95)

    def test_empty_snapshot(self):
        lt = LatencyTracker()
        snap = lt.get_snapshot("nonexistent")
        self.assertEqual(snap.count, 0)
        self.assertEqual(snap.avg_ms, 0.0)

    def test_stddev(self):
        lt = LatencyTracker()
        lt.record("op1", 10.0)
        lt.record("op1", 20.0)
        lt.record("op1", 30.0)
        snap = lt.get_snapshot("op1")
        self.assertGreater(snap.stddev_ms, 0)

    def test_get_all_names(self):
        lt = LatencyTracker()
        lt.record("op1", 10.0)
        lt.record("op2", 20.0)
        names = lt.get_all_names()
        self.assertIn("op1", names)
        self.assertIn("op2", names)

    def test_stats(self):
        lt = LatencyTracker()
        lt.start("active_op")
        stats = lt.get_stats()
        self.assertEqual(stats["active"], 1)
        self.assertEqual(stats["timers"], 0)
        lt.stop("active_op")
        stats = lt.get_stats()
        self.assertEqual(stats["active"], 0)
        self.assertEqual(stats["timers"], 1)

    def test_window_size_limit(self):
        lt = LatencyTracker(window_size=5)
        for i in range(10):
            lt.record("op1", float(i))
        snap = lt.get_snapshot("op1")
        self.assertEqual(snap.count, 5)  # 只保留最近5个


class TestThroughputTracker(unittest.TestCase):
    """吞吐量追踪器测试"""

    def test_record_and_get(self):
        tt = ThroughputTracker()
        for _ in range(10):
            tt.record("api_calls")
        snap = tt.get_throughput("api_calls", window_seconds=60.0)
        self.assertEqual(snap.count, 10)
        self.assertGreater(snap.rate_per_second, 0)

    def test_empty_throughput(self):
        tt = ThroughputTracker()
        snap = tt.get_throughput("nonexistent")
        self.assertEqual(snap.count, 0)
        self.assertEqual(snap.rate_per_second, 0.0)

    def test_window_filtering(self):
        tt = ThroughputTracker()
        # 记录一些操作
        for _ in range(5):
            tt.record("ops")
        snap = tt.get_throughput("ops", window_seconds=60.0)
        self.assertEqual(snap.count, 5)

    def test_get_all_names(self):
        tt = ThroughputTracker()
        tt.record("op1")
        tt.record("op2")
        names = tt.get_all_names()
        self.assertIn("op1", names)
        self.assertIn("op2", names)

    def test_stats(self):
        tt = ThroughputTracker()
        tt.record("op1")
        tt.record("op1")
        stats = tt.get_stats()
        self.assertEqual(stats["tracked"], 1)
        self.assertEqual(stats["total_records"], 2)


class TestResourceMonitor(unittest.TestCase):
    """资源监控器测试"""

    def test_snapshot(self):
        rm = ResourceMonitor()
        snap = rm.get_snapshot()
        self.assertIsInstance(snap, ResourceSnapshot)
        self.assertGreater(snap.thread_count, 0)
        self.assertGreater(snap.timestamp, 0)

    def test_custom_metric(self):
        rm = ResourceMonitor()
        rm.register_metric("custom_qps", lambda: 42.5)
        val = rm.get_custom("custom_qps")
        self.assertAlmostEqual(val, 42.5)

    def test_nonexistent_custom_metric(self):
        rm = ResourceMonitor()
        self.assertIsNone(rm.get_custom("nonexistent"))

    def test_custom_metric_error_handling(self):
        rm = ResourceMonitor()
        rm.register_metric("bad", lambda: 1/0)
        val = rm.get_custom("bad")
        self.assertIsNone(val)

    def test_get_all_custom(self):
        rm = ResourceMonitor()
        rm.register_metric("m1", lambda: 1.0)
        rm.register_metric("m2", lambda: 2.0)
        all_metrics = rm.get_all_custom()
        self.assertAlmostEqual(all_metrics["m1"], 1.0)
        self.assertAlmostEqual(all_metrics["m2"], 2.0)

    def test_stats(self):
        rm = ResourceMonitor()
        rm.register_metric("m1", lambda: 1.0)
        stats = rm.get_stats()
        self.assertEqual(stats["custom_metrics"], 1)


class TestPerformanceMonitor(unittest.TestCase):
    """性能监控器集成测试"""

    def test_timer_operations(self):
        pm = PerformanceMonitor()
        pm.timer_start("db_query")
        time.sleep(0.01)
        duration = pm.timer_stop("db_query")
        self.assertIsNotNone(duration)
        self.assertGreaterEqual(duration, 5)

    def test_record_latency(self):
        pm = PerformanceMonitor()
        pm.record_latency("api", 15.0)
        pm.record_latency("api", 25.0)
        snap = pm.get_latency("api")
        self.assertEqual(snap.count, 2)
        self.assertAlmostEqual(snap.avg_ms, 20.0, places=1)

    def test_throughput_operations(self):
        pm = PerformanceMonitor()
        for _ in range(10):
            pm.record_operation("requests")
        snap = pm.get_throughput("requests")
        self.assertEqual(snap.count, 10)

    def test_resource_operations(self):
        pm = PerformanceMonitor()
        pm.register_metric("queue_size", lambda: 5.0)
        res = pm.get_resources()
        self.assertIsInstance(res, ResourceSnapshot)

    def test_baseline_and_deviation(self):
        pm = PerformanceMonitor()
        pm.set_baseline(PerformanceBaseline(
            name="api",
            avg_ms=100.0,
            p95_ms=120.0,   # 接近实际值，偏差 < 50%
            p99_ms=150.0,
            qps=0.2,
        ))
        # 记录正常数据
        for _ in range(10):
            pm.record_latency("api", 100.0)
            pm.record_operation("api")

        dev = pm.check_baseline("api")
        self.assertIsNotNone(dev)
        self.assertEqual(dev.name, "api")
        self.assertEqual(dev.status, "ok")

    def test_baseline_critical_deviation(self):
        pm = PerformanceMonitor()
        pm.set_baseline(PerformanceBaseline(
            name="slow_api",
            avg_ms=10.0,
            p95_ms=20.0,
            p99_ms=30.0,
            qps=1000.0,
        ))
        # 记录远超基线的数据
        for _ in range(10):
            pm.record_latency("slow_api", 500.0)
            pm.record_operation("slow_api")

        dev = pm.check_baseline("slow_api")
        self.assertIsNotNone(dev)
        self.assertEqual(dev.status, "critical")

    def test_nonexistent_baseline(self):
        pm = PerformanceMonitor()
        self.assertIsNone(pm.check_baseline("nonexistent"))

    def test_comprehensive_report(self):
        pm = PerformanceMonitor()
        pm.record_latency("op1", 10.0)
        pm.record_operation("op1")
        pm.register_metric("m1", lambda: 1.0)
        pm.set_baseline(PerformanceBaseline(name="op1", avg_ms=10.0))

        report = pm.get_report()
        self.assertIn("timestamp", report)
        self.assertIn("latency", report)
        self.assertIn("throughput", report)
        self.assertIn("resources", report)
        self.assertIn("baselines", report)
        self.assertIn("op1", report["latency"])

    def test_stats(self):
        pm = PerformanceMonitor()
        pm.record_latency("op", 10.0)
        pm.record_operation("op")
        stats = pm.get_stats()
        self.assertIn("latency", stats)
        self.assertIn("throughput", stats)
        self.assertIn("resources", stats)
        self.assertEqual(stats["baselines"], 0)

    def test_global_singleton(self):
        pm1 = get_performance_monitor()
        pm2 = get_performance_monitor()
        self.assertIs(pm1, pm2)


class TestDataStructures(unittest.TestCase):
    """数据结构测试"""

    def test_timer_record(self):
        tr = TimerRecord(name="test", duration=10.5, success=True)
        self.assertEqual(tr.name, "test")
        self.assertEqual(tr.duration, 10.5)
        self.assertTrue(tr.success)

    def test_latency_snapshot(self):
        ls = LatencySnapshot(name="test", count=10, avg_ms=5.0)
        self.assertEqual(ls.name, "test")
        self.assertEqual(ls.count, 10)

    def test_throughput_snapshot(self):
        ts = ThroughputSnapshot(name="test", count=100, rate_per_second=10.0)
        self.assertEqual(ts.name, "test")
        self.assertEqual(ts.rate_per_second, 10.0)

    def test_resource_snapshot(self):
        rs = ResourceSnapshot(thread_count=5, memory_mb=100.0)
        self.assertEqual(rs.thread_count, 5)

    def test_performance_baseline(self):
        pb = PerformanceBaseline(name="api", avg_ms=50.0, qps=1000.0)
        self.assertEqual(pb.name, "api")
        self.assertEqual(pb.avg_ms, 50.0)

    def test_baseline_deviation(self):
        bd = BaselineDeviation(name="api", avg_deviation=10.0, status="warning")
        self.assertEqual(bd.name, "api")
        self.assertEqual(bd.status, "warning")

    def test_circuit_event(self):
        ce = CircuitEvent(name="test", state=CircuitState.OPEN, message="test")
        self.assertGreater(ce.timestamp, 0)
        self.assertEqual(ce.state, CircuitState.OPEN)

    def test_limit_result(self):
        lr = LimitResult(allowed=True, remaining=5, limit=10)
        self.assertTrue(lr.allowed)
        self.assertEqual(lr.remaining, 5)

    def test_limit_rule(self):
        rule = LimitRule(name="test", strategy=LimitStrategy.TOKEN_BUCKET)
        self.assertEqual(rule.name, "test")
        self.assertEqual(rule.strategy, LimitStrategy.TOKEN_BUCKET)

    def test_pool_config(self):
        pc = PoolConfig(min_size=2, max_size=10)
        self.assertEqual(pc.min_size, 2)
        self.assertEqual(pc.max_size, 10)

    def test_circuit_config(self):
        cc = CircuitConfig(failure_threshold=5, timeout_seconds=30.0)
        self.assertEqual(cc.failure_threshold, 5)
        self.assertEqual(cc.timeout_seconds, 30.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
