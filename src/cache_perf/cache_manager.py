#!/usr/bin/env python3
"""
缓存管理器 (CacheManager) - 阶段346

职责：
- LRU缓存：最近最少使用淘汰策略
- TTL缓存：基于过期时间的缓存
- 分层缓存：L1(内存)/L2(持久)多级缓存
- 缓存统计：命中率、淘汰率、容量监控
- 批量操作：批量读写、批量失效

设计原则：
- 确定性规则，无模型依赖
- 线程安全（RLock）
- 最小层级，无循环依赖
"""

import hashlib
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


# ============================================================
# 枚举与数据结构
# ============================================================

class EvictionPolicy(Enum):
    """淘汰策略"""
    LRU = "lru"           # 最近最少使用
    LFU = "lfu"           # 最少使用频率
    FIFO = "fifo"         # 先进先出
    TTL = "ttl"           # 基于过期时间


class CacheLevel(Enum):
    """缓存层级"""
    L1_MEMORY = "l1"      # 内存缓存（最快）
    L2_PERSIST = "l2"     # 持久缓存


@dataclass
class CacheEntry:
    """缓存条目"""
    key: str
    value: Any
    created_at: float = 0.0
    accessed_at: float = 0.0
    access_count: int = 0
    ttl: float = 0.0       # 0=永不过期
    size_bytes: int = 0
    tags: Set[str] = field(default_factory=set)

    def __post_init__(self):
        now = time.time()
        if self.created_at == 0.0:
            self.created_at = now
        if self.accessed_at == 0.0:
            self.accessed_at = now

    @property
    def is_expired(self) -> bool:
        if self.ttl <= 0:
            return False
        return (time.time() - self.created_at) > self.ttl

    @property
    def remaining_ttl(self) -> float:
        if self.ttl <= 0:
            return float('inf')
        remaining = self.ttl - (time.time() - self.created_at)
        return max(0, remaining)


@dataclass
class CacheStats:
    """缓存统计"""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    expirations: int = 0
    sets: int = 0
    deletes: int = 0
    size: int = 0
    max_size: int = 0
    total_bytes: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    @property
    def miss_rate(self) -> float:
        total = self.hits + self.misses
        return self.misses / total if total > 0 else 0.0


# ============================================================
# LRU缓存
# ============================================================

class LRUCache:
    """
    LRU缓存

    核心功能：
    1. 基于OrderedDict的O(1)操作
    2. 自动淘汰最久未使用的条目
    3. TTL过期检查
    4. 命中率统计
    """

    def __init__(self, max_size: int = 1000, default_ttl: float = 0.0):
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        self._stats = CacheStats(max_size=max_size)

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._stats.misses += 1
                return None

            if entry.is_expired:
                del self._cache[key]
                self._stats.expirations += 1
                self._stats.misses += 1
                return None

            # 移动到末尾（最近使用）
            self._cache.move_to_end(key)
            entry.accessed_at = time.time()
            entry.access_count += 1
            self._stats.hits += 1
            return entry.value

    def set(self, key: str, value: Any, ttl: float = 0.0,
            tags: Optional[Set[str]] = None) -> bool:
        """设置缓存值"""
        if ttl <= 0:
            ttl = self._default_ttl

        entry = CacheEntry(
            key=key,
            value=value,
            ttl=ttl,
            tags=tags or set(),
        )

        with self._lock:
            # 如果已存在，先删除旧条目
            if key in self._cache:
                del self._cache[key]

            # 淘汰超容量的条目
            while len(self._cache) >= self._max_size:
                evicted_key, evicted_entry = self._cache.popitem(last=False)
                self._stats.evictions += 1

            self._cache[key] = entry
            self._stats.sets += 1
            self._stats.size = len(self._cache)
            self._stats.total_bytes += self._estimate_size(value)

        return True

    def delete(self, key: str) -> bool:
        """删除缓存值"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._stats.deletes += 1
                self._stats.size = len(self._cache)
                return True
            return False

    def has(self, key: str) -> bool:
        """检查键是否存在且未过期"""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return False
            if entry.is_expired:
                del self._cache[key]
                return False
            return True

    def clear(self) -> int:
        """清空缓存"""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._stats.size = 0
            return count

    def get_or_set(self, key: str, factory: Callable[[], Any],
                   ttl: float = 0.0) -> Any:
        """获取或设置（缓存穿透保护）"""
        value = self.get(key)
        if value is not None:
            return value
        value = factory()
        self.set(key, value, ttl)
        return value

    def invalidate(self, pattern: str = "", tags: Optional[Set[str]] = None) -> int:
        """批量失效"""
        count = 0
        with self._lock:
            keys_to_delete = []
            for key, entry in self._cache.items():
                # 按标签匹配
                if tags and entry.tags and entry.tags & tags:
                    keys_to_delete.append(key)
                    continue
                # 按前缀匹配
                if pattern and key.startswith(pattern):
                    keys_to_delete.append(key)
            for key in keys_to_delete:
                del self._cache[key]
                count += 1
            self._stats.size = len(self._cache)
        return count

    def cleanup_expired(self) -> int:
        """清理过期条目"""
        count = 0
        with self._lock:
            expired = [k for k, v in self._cache.items() if v.is_expired]
            for key in expired:
                del self._cache[key]
                count += 1
            self._stats.expirations += count
            self._stats.size = len(self._cache)
        return count

    def keys(self) -> List[str]:
        """获取所有有效键"""
        with self._lock:
            return [k for k, v in self._cache.items() if not v.is_expired]

    def values(self) -> List[Any]:
        """获取所有有效值"""
        with self._lock:
            return [v.value for v in self._cache.values() if not v.is_expired]

    def items(self) -> List[Tuple[str, Any]]:
        """获取所有有效键值对"""
        with self._lock:
            return [(k, v.value) for k, v in self._cache.items() if not v.is_expired]

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._stats.hits,
                "misses": self._stats.misses,
                "hit_rate": round(self._stats.hit_rate, 4),
                "evictions": self._stats.evictions,
                "expirations": self._stats.expirations,
                "sets": self._stats.sets,
                "deletes": self._stats.deletes,
            }

    def reset_stats(self) -> None:
        with self._lock:
            self._stats = CacheStats(max_size=self._max_size)

    @staticmethod
    def _estimate_size(value: Any) -> int:
        """估算值大小（字节）"""
        try:
            return len(str(value).encode('utf-8'))
        except Exception:
            return 0


# ============================================================
# 分层缓存
# ============================================================

class TieredCache:
    """
    分层缓存

    核心功能：
    1. L1内存缓存（快速访问）
    2. L2持久缓存（大容量）
    3. 自动回源
    4. 统一统计
    """

    def __init__(self, l1_size: int = 1000, l2_size: int = 10000,
                 l1_ttl: float = 60.0, l2_ttl: float = 300.0):
        self._l1 = LRUCache(max_size=l1_size, default_ttl=l1_ttl)
        self._l2 = LRUCache(max_size=l2_size, default_ttl=l2_ttl)
        self._lock = threading.RLock()
        self._miss_handler: Optional[Callable[[str], Any]] = None

    def get(self, key: str) -> Optional[Any]:
        """获取值（L1 → L2 → miss_handler）"""
        # 先查L1
        value = self._l1.get(key)
        if value is not None:
            return value

        # 再查L2
        value = self._l2.get(key)
        if value is not None:
            # 回填L1
            self._l1.set(key, value)
            return value

        # 调用miss handler
        if self._miss_handler:
            value = self._miss_handler(key)
            if value is not None:
                self._l1.set(key, value)
                self._l2.set(key, value)
            return value

        return None

    def set(self, key: str, value: Any, l1_ttl: float = 0.0,
            l2_ttl: float = 0.0) -> None:
        """设置值（同时写入L1和L2）"""
        self._l1.set(key, value, l1_ttl)
        self._l2.set(key, value, l2_ttl)

    def delete(self, key: str) -> bool:
        """删除值（同时从L1和L2删除）"""
        r1 = self._l1.delete(key)
        r2 = self._l2.delete(key)
        return r1 or r2

    def invalidate(self, pattern: str = "",
                    tags: Optional[Set[str]] = None) -> int:
        """批量失效"""
        return self._l1.invalidate(pattern, tags) + self._l2.invalidate(pattern, tags)

    def set_miss_handler(self, handler: Callable[[str], Any]) -> None:
        """设置缓存未命中时的回源函数"""
        self._miss_handler = handler

    def cleanup(self) -> int:
        """清理过期条目"""
        return self._l1.cleanup_expired() + self._l2.cleanup_expired()

    def get_stats(self) -> Dict[str, Any]:
        return {
            "l1": self._l1.get_stats(),
            "l2": self._l2.get_stats(),
            "combined_hit_rate": round(
                (self._l1.get_stats()["hits"] + self._l2.get_stats()["hits"]) /
                max(self._l1.get_stats()["hits"] + self._l1.get_stats()["misses"] +
                    self._l2.get_stats()["hits"] + self._l2.get_stats()["misses"], 1),
                4
            ) if (self._l1.get_stats()["hits"] + self._l1.get_stats()["misses"] +
                  self._l2.get_stats()["hits"] + self._l2.get_stats()["misses"]) > 0 else 0.0,
        }

    @property
    def l1(self) -> LRUCache:
        return self._l1

    @property
    def l2(self) -> LRUCache:
        return self._l2


# ============================================================
# 缓存管理器
# ============================================================

class CacheManager:
    """
    缓存管理器

    核心功能：
    1. 多命名空间缓存
    2. 分层缓存支持
    3. 全局缓存操作
    4. 统一统计
    """

    def __init__(self, default_max_size: int = 1000,
                 default_ttl: float = 300.0):
        self._default_max_size = default_max_size
        self._default_ttl = default_ttl
        self._namespaces: Dict[str, LRUCache] = {}
        self._tiered: Dict[str, TieredCache] = {}
        self._lock = threading.RLock()

    def get_cache(self, namespace: str = "default") -> LRUCache:
        """获取或创建命名空间缓存"""
        with self._lock:
            if namespace not in self._namespaces:
                self._namespaces[namespace] = LRUCache(
                    max_size=self._default_max_size,
                    default_ttl=self._default_ttl,
                )
            return self._namespaces[namespace]

    def get_tiered(self, namespace: str = "default") -> TieredCache:
        """获取或创建分层缓存"""
        with self._lock:
            if namespace not in self._tiered:
                self._tiered[namespace] = TieredCache(
                    l1_size=self._default_max_size,
                    l2_size=self._default_max_size * 10,
                    l1_ttl=self._default_ttl / 5,
                    l2_ttl=self._default_ttl,
                )
            return self._tiered[namespace]

    def get(self, key: str, namespace: str = "default") -> Optional[Any]:
        """获取缓存值"""
        return self.get_cache(namespace).get(key)

    def set(self, key: str, value: Any, namespace: str = "default",
            ttl: float = 0.0) -> bool:
        """设置缓存值"""
        return self.get_cache(namespace).set(key, value, ttl)

    def delete(self, key: str, namespace: str = "default") -> bool:
        """删除缓存值"""
        return self.get_cache(namespace).delete(key)

    def invalidate_namespace(self, namespace: str) -> int:
        """清空命名空间"""
        with self._lock:
            cache = self._namespaces.pop(namespace, None)
            if cache:
                return cache.clear()
            return 0

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            result = {
                "namespaces": len(self._namespaces),
                "tiered": len(self._tiered),
                "caches": {},
            }
            for name, cache in self._namespaces.items():
                result["caches"][name] = cache.get_stats()
            return result


# ============================================================
# 全局单例
# ============================================================

_cache_manager: Optional[CacheManager] = None
_cm_lock = threading.RLock()


def get_cache_manager() -> CacheManager:
    """获取全局缓存管理器"""
    global _cache_manager
    if _cache_manager is None:
        with _cm_lock:
            if _cache_manager is None:
                _cache_manager = CacheManager()
    return _cache_manager
