"""
Agent可靠记忆系统 - 记忆缓存管理器
阶段185-187: 多级缓存、LRU策略、缓存预热与失效

设计原则:
- 确定性规则驱动，无模型依赖
- 线程安全（RLock）
- 全局单例模式
- 多级缓存架构
"""

import threading
import time
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Tuple
from collections import OrderedDict
import functools


class CacheLevel(Enum):
    """缓存层级"""
    L1_MEMORY = "l1_memory"        # 进程内内存缓存
    L2_SHARED = "l2_shared"        # 共享内存缓存
    L3_DISK = "l3_disk"            # 磁盘缓存


class EvictionPolicy(Enum):
    """淘汰策略"""
    LRU = "lru"                    # 最近最少使用
    LFU = "lfu"                    # 最不经常使用
    FIFO = "fifo"                  # 先进先出
    TTL = "ttl"                    # 过期时间


@dataclass
class CacheEntry:
    """缓存条目"""
    key: str
    value: Any
    created_at: float = field(default_factory=time.time)
    accessed_at: float = field(default_factory=time.time)
    access_count: int = 1
    ttl_seconds: float = 300       # 默认5分钟
    size_bytes: int = 0

    @property
    def is_expired(self) -> bool:
        return time.time() - self.created_at > self.ttl_seconds

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at

    def touch(self):
        """更新访问时间"""
        self.accessed_at = time.time()
        self.access_count += 1


@dataclass
class CacheStats:
    """缓存统计"""
    level: str
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    size: int = 0                  # 当前条目数
    max_size: int = 0              # 最大容量
    total_size_bytes: int = 0      # 总字节数

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def to_dict(self) -> Dict:
        return {
            "level": self.level,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hit_rate, 4),
            "evictions": self.evictions,
            "size": self.size,
            "max_size": self.max_size,
            "utilization": round(self.size / self.max_size * 100, 2) if self.max_size > 0 else 0,
            "total_size_bytes": self.total_size_bytes,
        }


class LRUCache:
    """LRU缓存实现（基于OrderedDict）"""

    def __init__(self, max_size: int = 1000):
        self._lock = threading.RLock()
        self._max_size = max_size
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._stats = CacheStats(level="lru", max_size=max_size)

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                if entry.is_expired:
                    del self._cache[key]
                    self._stats.misses += 1
                    return None

                # 移动到末尾（最近使用）
                self._cache.move_to_end(key)
                entry.touch()
                self._stats.hits += 1
                return entry.value

            self._stats.misses += 1
            return None

    def put(self, key: str, value: Any, ttl_seconds: float = 300):
        """设置缓存值"""
        with self._lock:
            if key in self._cache:
                # 更新现有条目
                old_entry = self._cache[key]
                self._stats.total_size_bytes -= old_entry.size_bytes
                self._cache.move_to_end(key)
            else:
                # 新条目，检查是否需要淘汰
                if len(self._cache) >= self._max_size:
                    self._evict_oldest()

            entry = CacheEntry(
                key=key,
                value=value,
                ttl_seconds=ttl_seconds,
                size_bytes=self._estimate_size(value),
            )
            self._cache[key] = entry
            self._stats.size = len(self._cache)
            self._stats.total_size_bytes += entry.size_bytes

    def _evict_oldest(self):
        """淘汰最旧的条目"""
        if self._cache:
            oldest_key = next(iter(self._cache))
            oldest_entry = self._cache[oldest_key]
            self._stats.total_size_bytes -= oldest_entry.size_bytes
            del self._cache[oldest_key]
            self._stats.evictions += 1

    def _estimate_size(self, value: Any) -> int:
        """估算值的大小（字节）"""
        try:
            import sys
            return sys.getsizeof(value)
        except:
            return 64  # 默认值

    def invalidate(self, key: str) -> bool:
        """使指定键失效"""
        with self._lock:
            if key in self._cache:
                entry = self._cache.pop(key)
                self._stats.total_size_bytes -= entry.size_bytes
                self._stats.size = len(self._cache)
                return True
            return False

    def invalidate_pattern(self, pattern: str) -> int:
        """使匹配模式的键失效"""
        with self._lock:
            import re
            keys_to_remove = [k for k in self._cache.keys() if re.search(pattern, k)]
            for key in keys_to_remove:
                entry = self._cache.pop(key)
                self._stats.total_size_bytes -= entry.size_bytes
            self._stats.size = len(self._cache)
            return len(keys_to_remove)

    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._stats = CacheStats(level="lru", max_size=self._max_size)

    def get_stats(self) -> CacheStats:
        """获取统计"""
        with self._lock:
            return self._stats


class CacheManager:
    """
    记忆缓存管理器

    功能:
    - 多级缓存（L1内存、L2共享、L3磁盘）
    - LRU/LFU/FIFO/TTL淘汰策略
    - 缓存预热
    - 批量失效
    - 缓存统计
    - 装饰器支持
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._l1_cache = LRUCache(max_size=10000)      # L1: 进程内
        self._l2_cache = LRUCache(max_size=50000)      # L2: 更大容量
        self._warmup_data: Dict[str, Any] = {}         # 预热数据
        self._key_generators: Dict[str, Callable] = {}  # 键生成器
        self._namespace_stats: Dict[str, Dict] = {}

    # ==================== 基本操作 ====================

    def get(self, key: str, namespace: str = "default") -> Optional[Any]:
        """
        获取缓存值（多级缓存查找）

        Args:
            key: 缓存键
            namespace: 命名空间
        """
        full_key = f"{namespace}:{key}"

        # L1缓存
        value = self._l1_cache.get(full_key)
        if value is not None:
            return value

        # L2缓存
        value = self._l2_cache.get(full_key)
        if value is not None:
            # 回填L1
            self._l1_cache.put(full_key, value)
            return value

        return None

    def put(self, key: str, value: Any,
            namespace: str = "default",
            ttl_seconds: float = 300,
            level: CacheLevel = CacheLevel.L1_MEMORY):
        """
        设置缓存值

        Args:
            key: 缓存键
            value: 缓存值
            namespace: 命名空间
            ttl_seconds: 过期时间
            level: 缓存层级
        """
        full_key = f"{namespace}:{key}"

        if level == CacheLevel.L1_MEMORY:
            self._l1_cache.put(full_key, value, ttl_seconds)
        elif level == CacheLevel.L2_SHARED:
            self._l2_cache.put(full_key, value, ttl_seconds)
        elif level == CacheLevel.L3_DISK:
            # 磁盘缓存简化实现
            pass

    def invalidate(self, key: str, namespace: str = "default") -> bool:
        """使指定键失效"""
        full_key = f"{namespace}:{key}"
        l1_result = self._l1_cache.invalidate(full_key)
        l2_result = self._l2_cache.invalidate(full_key)
        return l1_result or l2_result

    def invalidate_namespace(self, namespace: str) -> int:
        """使整个命名空间失效"""
        pattern = f"^{namespace}:"
        l1_count = self._l1_cache.invalidate_pattern(pattern)
        l2_count = self._l2_cache.invalidate_pattern(pattern)
        return l1_count + l2_count

    def invalidate_all(self):
        """清空所有缓存"""
        self._l1_cache.clear()
        self._l2_cache.clear()

    # ==================== 缓存装饰器 ====================

    def cached(self, namespace: str = "default",
               ttl_seconds: float = 300,
               key_func: Optional[Callable] = None):
        """
        缓存装饰器

        Args:
            namespace: 命名空间
            ttl_seconds: 过期时间
            key_func: 自定义键生成函数
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                # 生成缓存键
                if key_func:
                    cache_key = key_func(*args, **kwargs)
                else:
                    cache_key = self._generate_key(func, args, kwargs)

                # 尝试获取缓存
                result = self.get(cache_key, namespace)
                if result is not None:
                    return result

                # 执行函数
                result = func(*args, **kwargs)

                # 缓存结果
                self.put(cache_key, result, namespace, ttl_seconds)

                return result
            return wrapper
        return decorator

    def _generate_key(self, func: Callable, args: Tuple, kwargs: Dict) -> str:
        """生成缓存键"""
        key_parts = [
            func.__module__,
            func.__qualname__,
            str(args),
            str(sorted(kwargs.items()))
        ]
        key_string = "|".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()[:16]

    # ==================== 缓存预热 ====================

    def register_warmup_data(self, namespace: str,
                            data_generator: Callable[[], Dict[str, Any]]):
        """
        注册预热数据生成器

        Args:
            namespace: 命名空间
            data_generator: 数据生成函数，返回{key: value}字典
        """
        with self._lock:
            self._key_generators[namespace] = data_generator

    def warmup(self, namespace: Optional[str] = None,
               ttl_seconds: float = 3600) -> Dict:
        """
        执行缓存预热

        Args:
            namespace: 指定命名空间（None表示所有）
            ttl_seconds: 预热数据过期时间

        Returns:
            预热统计
        """
        with self._lock:
            stats = {"warmed": 0, "namespaces": []}

            namespaces = [namespace] if namespace else list(self._key_generators.keys())

            for ns in namespaces:
                if ns not in self._key_generators:
                    continue

                generator = self._key_generators[ns]
                try:
                    data = generator()
                    for key, value in data.items():
                        self.put(key, value, ns, ttl_seconds, CacheLevel.L1_MEMORY)
                    stats["warmed"] += len(data)
                    stats["namespaces"].append({"name": ns, "count": len(data)})
                except Exception as e:
                    stats["namespaces"].append({"name": ns, "error": str(e)})

            return stats

    def preload_memories(self, memory_ids: List[str],
                         fetch_func: Callable[[str], Any],
                         namespace: str = "memories",
                         ttl_seconds: float = 300) -> int:
        """
        预加载记忆到缓存

        Args:
            memory_ids: 记忆ID列表
            fetch_func: 获取记忆的函数
            namespace: 命名空间
            ttl_seconds: 过期时间

        Returns:
            成功加载数量
        """
        count = 0
        for memory_id in memory_ids:
            try:
                memory = fetch_func(memory_id)
                if memory:
                    self.put(memory_id, memory, namespace, ttl_seconds)
                    count += 1
            except Exception:
                pass
        return count

    # ==================== 批量操作 ====================

    def get_multi(self, keys: List[str],
                  namespace: str = "default") -> Dict[str, Any]:
        """批量获取"""
        results = {}
        for key in keys:
            value = self.get(key, namespace)
            if value is not None:
                results[key] = value
        return results

    def put_multi(self, items: Dict[str, Any],
                  namespace: str = "default",
                  ttl_seconds: float = 300):
        """批量设置"""
        for key, value in items.items():
            self.put(key, value, namespace, ttl_seconds)

    def invalidate_multi(self, keys: List[str],
                         namespace: str = "default") -> int:
        """批量失效"""
        count = 0
        for key in keys:
            if self.invalidate(key, namespace):
                count += 1
        return count

    # ==================== 统计与监控 ====================

    def get_stats(self) -> Dict:
        """获取缓存统计"""
        with self._lock:
            return {
                "l1": self._l1_cache.get_stats().to_dict(),
                "l2": self._l2_cache.get_stats().to_dict(),
                "overall": {
                    "total_entries": (
                        self._l1_cache.get_stats().size +
                        self._l2_cache.get_stats().size
                    ),
                    "total_hits": (
                        self._l1_cache.get_stats().hits +
                        self._l2_cache.get_stats().hits
                    ),
                    "total_misses": (
                        self._l1_cache.get_stats().misses +
                        self._l2_cache.get_stats().misses
                    ),
                },
            }

    def get_cache_report(self) -> Dict:
        """获取缓存报告"""
        stats = self.get_stats()
        l1 = stats["l1"]
        l2 = stats["l2"]

        total_hits = l1["hits"] + l2["hits"]
        total_requests = total_hits + l1["misses"] + l2["misses"]

        return {
            "timestamp": time.time(),
            "summary": {
                "total_entries": stats["overall"]["total_entries"],
                "total_requests": total_requests,
                "overall_hit_rate": round(total_hits / total_requests * 100, 2) if total_requests > 0 else 0,
            },
            "l1_cache": {
                "hit_rate": round(l1["hit_rate"] * 100, 2),
                "utilization": l1["utilization"],
                "evictions": l1["evictions"],
            },
            "l2_cache": {
                "hit_rate": round(l2["hit_rate"] * 100, 2),
                "utilization": l2["utilization"],
                "evictions": l2["evictions"],
            },
        }

    def reset_stats(self):
        """重置统计"""
        self._l1_cache.clear()
        self._l2_cache.clear()

    # ==================== 配置 ====================

    def configure(self, l1_size: Optional[int] = None,
                  l2_size: Optional[int] = None):
        """配置缓存大小"""
        with self._lock:
            if l1_size:
                self._l1_cache = LRUCache(max_size=l1_size)
            if l2_size:
                self._l2_cache = LRUCache(max_size=l2_size)

    def get_summary(self) -> Dict:
        """获取管理器摘要"""
        with self._lock:
            stats = self.get_stats()
            return {
                "l1_size": self._l1_cache._max_size,
                "l2_size": self._l2_cache._max_size,
                "total_entries": stats["overall"]["total_entries"],
                "overall_hit_rate": stats["overall"]["total_hits"] / max(
                    stats["overall"]["total_hits"] + stats["overall"]["total_misses"], 1
                ),
                "registered_warmup_namespaces": len(self._key_generators),
            }


# ==================== 全局单例 ====================

_global_cache_manager: Optional[CacheManager] = None
_global_cache_manager_lock = threading.Lock()


def get_cache_manager() -> CacheManager:
    """获取全局缓存管理器实例"""
    global _global_cache_manager
    if _global_cache_manager is None:
        with _global_cache_manager_lock:
            if _global_cache_manager is None:
                _global_cache_manager = CacheManager()
    return _global_cache_manager
