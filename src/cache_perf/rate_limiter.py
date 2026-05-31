#!/usr/bin/env python3
"""
速率限制器 (RateLimiter) - 阶段347

职责：
- 令牌桶算法：平滑限流
- 滑动窗口：精确时间窗口计数
- 固定窗口：简单计数限流
- 漏桶算法：匀速处理
- 多维度限流：按用户/IP/接口

设计原则：
- 确定性规则，无模型依赖
- 线程安全（RLock）
- 最小层级，无循环依赖
"""

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ============================================================
# 枚举与数据结构
# ============================================================

class LimitStrategy(Enum):
    """限流策略"""
    TOKEN_BUCKET = "token_bucket"     # 令牌桶
    SLIDING_WINDOW = "sliding_window"  # 滑动窗口
    FIXED_WINDOW = "fixed_window"      # 固定窗口
    LEAKY_BUCKET = "leaky_bucket"      # 漏桶


@dataclass
class LimitRule:
    """限流规则"""
    name: str = ""
    strategy: LimitStrategy = LimitStrategy.TOKEN_BUCKET
    rate: float = 10.0          # 速率（次/秒 或 令牌/秒）
    burst: int = 20             # 突发容量
    window_seconds: float = 1.0  # 窗口大小（秒）
    key_prefix: str = ""        # 键前缀


@dataclass
class LimitResult:
    """限流结果"""
    allowed: bool
    remaining: int = 0
    retry_after: float = 0.0   # 秒后重试
    limit: int = 0
    reset_at: float = 0.0


@dataclass
class LimitStats:
    """限流统计"""
    total_requests: int = 0
    allowed_requests: int = 0
    rejected_requests: int = 0
    buckets_created: int = 0

    @property
    def rejection_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.rejected_requests / self.total_requests


# ============================================================
# 令牌桶
# ============================================================

class TokenBucket:
    """
    令牌桶算法

    核心功能：
    1. 固定速率补充令牌
    2. 突发处理（burst容量）
    3. 平滑限流
    """

    def __init__(self, rate: float = 10.0, burst: int = 20):
        self._rate = rate          # 令牌/秒
        self._burst = burst        # 桶容量
        self._tokens = float(burst)
        self._last_refill = time.time()
        self._lock = threading.RLock()

    def consume(self, count: int = 1) -> LimitResult:
        """消费令牌"""
        with self._lock:
            self._refill()
            if self._tokens >= count:
                self._tokens -= count
                return LimitResult(
                    allowed=True,
                    remaining=int(self._tokens),
                    limit=self._burst,
                )
            else:
                retry = (count - self._tokens) / self._rate
                return LimitResult(
                    allowed=False,
                    remaining=0,
                    retry_after=round(retry, 3),
                    limit=self._burst,
                )

    def _refill(self) -> None:
        """补充令牌"""
        now = time.time()
        elapsed = now - self._last_refill
        self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
        self._last_refill = now

    @property
    def available(self) -> float:
        with self._lock:
            self._refill()
            return self._tokens


# ============================================================
# 滑动窗口
# ============================================================

class SlidingWindow:
    """
    滑动窗口算法

    核心功能：
    1. 精确时间窗口计数
    2. 平滑过渡
    3. 自动清理过期记录
    """

    def __init__(self, limit: int = 100, window_seconds: float = 1.0):
        self._limit = limit
        self._window = window_seconds
        self._timestamps: deque = deque()
        self._lock = threading.RLock()

    def consume(self, count: int = 1) -> LimitResult:
        """消费配额"""
        with self._lock:
            now = time.time()
            cutoff = now - self._window

            # 清理过期记录
            while self._timestamps and self._timestamps[0] < cutoff:
                self._timestamps.popleft()

            current = len(self._timestamps)
            remaining = max(0, self._limit - current)

            if current + count <= self._limit:
                for _ in range(count):
                    self._timestamps.append(now)
                return LimitResult(
                    allowed=True,
                    remaining=remaining - count,
                    limit=self._limit,
                    reset_at=self._timestamps[0] + self._window if self._timestamps else now,
                )
            else:
                # 计算最早记录过期时间
                retry = (self._timestamps[0] + self._window - now) if self._timestamps else 0
                return LimitResult(
                    allowed=False,
                    remaining=0,
                    retry_after=round(max(0, retry), 3),
                    limit=self._limit,
                )

    @property
    def current_count(self) -> int:
        with self._lock:
            cutoff = time.time() - self._window
            while self._timestamps and self._timestamps[0] < cutoff:
                self._timestamps.popleft()
            return len(self._timestamps)


# ============================================================
# 固定窗口
# ============================================================

class FixedWindow:
    """
    固定窗口算法

    核心功能：
    1. 简单计数
    2. 窗口重置
    3. 适合粗粒度限流
    """

    def __init__(self, limit: int = 100, window_seconds: float = 1.0):
        self._limit = limit
        self._window = window_seconds
        self._count = 0
        self._window_start = time.time()
        self._lock = threading.RLock()

    def consume(self, count: int = 1) -> LimitResult:
        """消费配额"""
        with self._lock:
            now = time.time()
            if now - self._window_start >= self._window:
                self._count = 0
                self._window_start = now

            remaining = max(0, self._limit - self._count)

            if self._count + count <= self._limit:
                self._count += count
                return LimitResult(
                    allowed=True,
                    remaining=remaining - count,
                    limit=self._limit,
                    reset_at=self._window_start + self._window,
                )
            else:
                retry = self._window_start + self._window - now
                return LimitResult(
                    allowed=False,
                    remaining=0,
                    retry_after=round(max(0, retry), 3),
                    limit=self._limit,
                )

    @property
    def current_count(self) -> int:
        with self._lock:
            now = time.time()
            if now - self._window_start >= self._window:
                return 0
            return self._count


# ============================================================
# 漏桶
# ============================================================

class LeakyBucket:
    """
    漏桶算法

    核心功能：
    1. 匀速处理请求
    2. 队列缓冲突发
    3. 溢出丢弃
    """

    def __init__(self, rate: float = 10.0, capacity: int = 20):
        self._rate = rate          # 漏出速率（次/秒）
        self._capacity = capacity  # 桶容量
        self._queue: float = 0.0   # 当前队列量
        self._last_leak = time.time()
        self._lock = threading.RLock()

    def consume(self, count: int = 1) -> LimitResult:
        """消费（入桶）"""
        with self._lock:
            self._leak()
            available = self._capacity - self._queue

            if available >= count:
                self._queue += count
                return LimitResult(
                    allowed=True,
                    remaining=int(available - count),
                    limit=self._capacity,
                )
            else:
                return LimitResult(
                    allowed=False,
                    remaining=0,
                    retry_after=round(available / self._rate, 3) if self._rate > 0 else 0,
                    limit=self._capacity,
                )

    def _leak(self) -> None:
        """漏水"""
        now = time.time()
        elapsed = now - self._last_leak
        leaked = elapsed * self._rate
        self._queue = max(0, self._queue - leaked)
        self._last_leak = now

    @property
    def queue_size(self) -> float:
        with self._lock:
            self._leak()
            return self._queue


# ============================================================
# 速率限制器
# ============================================================

class RateLimiter:
    """
    速率限制器

    核心功能：
    1. 多策略支持
    2. 多维度限流（按key）
    3. 规则管理
    4. 统一统计
    """

    def __init__(self):
        self._rules: Dict[str, LimitRule] = {}
        self._buckets: Dict[str, Any] = {}  # key → bucket实例
        self._lock = threading.RLock()
        self._stats = LimitStats()

    def add_rule(self, rule: LimitRule) -> None:
        """添加限流规则"""
        with self._lock:
            self._rules[rule.name] = rule

    def remove_rule(self, name: str) -> bool:
        """移除规则"""
        with self._lock:
            return self._rules.pop(name, None) is not None

    def _get_bucket(self, rule: LimitRule, key: str) -> Any:
        """获取或创建桶"""
        bucket_key = f"{rule.key_prefix}:{key}" if rule.key_prefix else key
        with self._lock:
            if bucket_key not in self._buckets:
                if rule.strategy == LimitStrategy.TOKEN_BUCKET:
                    self._buckets[bucket_key] = TokenBucket(rule.rate, rule.burst)
                elif rule.strategy == LimitStrategy.SLIDING_WINDOW:
                    self._buckets[bucket_key] = SlidingWindow(
                        int(rule.rate * rule.window_seconds), rule.window_seconds
                    )
                elif rule.strategy == LimitStrategy.FIXED_WINDOW:
                    self._buckets[bucket_key] = FixedWindow(
                        int(rule.rate * rule.window_seconds), rule.window_seconds
                    )
                elif rule.strategy == LimitStrategy.LEAKY_BUCKET:
                    self._buckets[bucket_key] = LeakyBucket(rule.rate, rule.burst)
                self._stats.buckets_created += 1
            return self._buckets[bucket_key]

    def allow(self, key: str, rule_name: str = "default",
               count: int = 1) -> LimitResult:
        """
        检查是否允许请求

        Args:
            key: 限流键（用户ID、IP等）
            rule_name: 规则名称
            count: 消费数量
        """
        with self._lock:
            self._stats.total_requests += 1

        rule = self._rules.get(rule_name)
        if rule is None:
            # 无规则时默认允许
            with self._lock:
                self._stats.allowed_requests += 1
            return LimitResult(allowed=True, remaining=-1)

        bucket = self._get_bucket(rule, key)
        result = bucket.consume(count)

        with self._lock:
            if result.allowed:
                self._stats.allowed_requests += 1
            else:
                self._stats.rejected_requests += 1

        return result

    def check(self, key: str, rule_name: str = "default") -> bool:
        """快速检查是否允许（不消费配额）"""
        result = self.allow(key, rule_name, count=0)
        return result.allowed

    def reset(self, key: str = "", rule_name: str = "") -> None:
        """重置限流计数"""
        with self._lock:
            if key:
                for bk in list(self._buckets.keys()):
                    if key in bk:
                        del self._buckets[bk]
            elif rule_name:
                rule = self._rules.get(rule_name)
                if rule:
                    prefix = rule.key_prefix
                    for bk in list(self._buckets.keys()):
                        if prefix and bk.startswith(prefix):
                            del self._buckets[bk]
            else:
                self._buckets.clear()

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "rules": len(self._rules),
                "active_buckets": len(self._buckets),
                "total_requests": self._stats.total_requests,
                "allowed": self._stats.allowed_requests,
                "rejected": self._stats.rejected_requests,
                "rejection_rate": round(self._stats.rejection_rate, 4),
            }

    def list_rules(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {"name": r.name, "strategy": r.strategy.value,
                 "rate": r.rate, "burst": r.burst,
                 "window": r.window_seconds}
                for r in self._rules.values()
            ]


# ============================================================
# 全局单例
# ============================================================

_rate_limiter: Optional[RateLimiter] = None
_rl_lock = threading.RLock()


def get_rate_limiter() -> RateLimiter:
    """获取全局速率限制器"""
    global _rate_limiter
    if _rate_limiter is None:
        with _rl_lock:
            if _rate_limiter is None:
                _rate_limiter = RateLimiter()
    return _rate_limiter
