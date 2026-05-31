"""
存储缓存模块 (阶段363)

提供存储层的缓存装饰器，支持读穿透、写穿透和缓存失效策略。
线程安全设计，使用 threading.RLock 保证并发安全。
确定性规则设计，无模型依赖，无循环依赖。
"""

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from .storage_backend import StorageBackend


# ============================================================================
# 枚举定义
# ============================================================================


class CachePolicy(Enum):
    """缓存策略枚举"""
    READ_THROUGH = "read_through"      # 读穿透：缓存未命中时从存储读取
    WRITE_THROUGH = "write_through"    # 写穿透：同时写入缓存和存储
    WRITE_BEHIND = "write_behind"      # 写后：先写缓存，异步写存储
    CACHE_ASIDE = "cache_aside"        # 旁路缓存：应用层管理缓存


class EvictionPolicy(Enum):
    """淘汰策略枚举"""
    LRU = "lru"    # 最近最少使用
    LFU = "lfu"    # 最不经常使用
    FIFO = "fifo"  # 先进先出
    TTL = "ttl"    # 基于时间过期


# ============================================================================
# 数据类定义
# ============================================================================


@dataclass
class CacheEntry:
    """缓存条目数据类"""
    key: str
    value: Any
    namespace: str = "default"
    created_at: float = field(default_factory=time.time)
    accessed_at: float = field(default_factory=time.time)
    access_count: int = 0
    ttl: Optional[float] = None  # 生存时间（秒）


@dataclass
class CacheStats:
    """缓存统计数据类"""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    updates: int = 0
    invalidations: int = 0
    
    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return self.hits / total


@dataclass
class CacheConfig:
    """缓存配置数据类"""
    max_size: int = 1000
    default_ttl: Optional[float] = None
    policy: CachePolicy = CachePolicy.READ_THROUGH
    eviction: EvictionPolicy = EvictionPolicy.LRU
    enabled: bool = True


# ============================================================================
# 存储缓存
# ============================================================================


class StorageCache:
    """
    存储缓存
    
    为存储后端提供缓存层，支持多种缓存策略和淘汰策略。
    线程安全，使用 RLock 保证并发访问安全。
    """
    
    def __init__(self, backend: StorageBackend, config: Optional[CacheConfig] = None) -> None:
        self._lock = threading.RLock()
        self._backend = backend
        self._config = config or CacheConfig()
        self._cache: Dict[str, OrderedDict] = {}  # namespace -> {key: CacheEntry}
        self._stats = CacheStats()
    
    def _get_namespace_cache(self, namespace: str) -> OrderedDict:
        """获取命名空间缓存"""
        if namespace not in self._cache:
            self._cache[namespace] = OrderedDict()
        return self._cache[namespace]
    
    def _make_cache_key(self, key: str, namespace: str) -> str:
        """生成缓存键"""
        return f"{namespace}:{key}"
    
    def _is_expired(self, entry: CacheEntry) -> bool:
        """检查条目是否过期"""
        if entry.ttl is None:
            return False
        return time.time() > entry.created_at + entry.ttl
    
    def _evict_if_needed(self, namespace: str) -> None:
        """如果需要则执行淘汰"""
        ns_cache = self._get_namespace_cache(namespace)
        
        while len(ns_cache) >= self._config.max_size:
            if self._config.eviction == EvictionPolicy.LRU:
                # 移除最久未访问的
                oldest_key = min(ns_cache.keys(), key=lambda k: ns_cache[k].accessed_at)
                del ns_cache[oldest_key]
            elif self._config.eviction == EvictionPolicy.LFU:
                # 移除访问次数最少的
                least_key = min(ns_cache.keys(), key=lambda k: ns_cache[k].access_count)
                del ns_cache[least_key]
            elif self._config.eviction == EvictionPolicy.FIFO:
                # 移除最早创建的
                first_key = next(iter(ns_cache))
                del ns_cache[first_key]
            else:
                # TTL: 移除过期的
                expired_keys = [k for k, v in ns_cache.items() if self._is_expired(v)]
                if expired_keys:
                    for k in expired_keys:
                        del ns_cache[k]
                else:
                    # 没有过期的，用LRU
                    oldest_key = min(ns_cache.keys(), key=lambda k: ns_cache[k].accessed_at)
                    del ns_cache[oldest_key]
            
            self._stats.evictions += 1
    
    def get(self, key: str, namespace: str = "default") -> Optional[Any]:
        """获取值（带缓存）"""
        if not self._config.enabled:
            return self._backend.get(key, namespace)
        
        with self._lock:
            ns_cache = self._get_namespace_cache(namespace)
            cache_key = self._make_cache_key(key, namespace)
            
            # 检查缓存
            if cache_key in ns_cache:
                entry = ns_cache[cache_key]
                if not self._is_expired(entry):
                    entry.accessed_at = time.time()
                    entry.access_count += 1
                    self._stats.hits += 1
                    return entry.value
                else:
                    # 过期，移除
                    del ns_cache[cache_key]
            
            self._stats.misses += 1
            
            # 读穿透：从后端读取
            if self._config.policy in (CachePolicy.READ_THROUGH, CachePolicy.WRITE_THROUGH, CachePolicy.CACHE_ASIDE):
                value = self._backend.get(key, namespace)
                if value is not None:
                    self._evict_if_needed(namespace)
                    entry = CacheEntry(
                        key=key,
                        value=value,
                        namespace=namespace,
                        ttl=self._config.default_ttl,
                    )
                    ns_cache[cache_key] = entry
                return value
            
            return None
    
    def set(self, key: str, value: Any, namespace: str = "default",
            ttl: Optional[float] = None) -> bool:
        """设置值（带缓存）"""
        if not self._config.enabled:
            return self._backend.set(key, value, namespace, ttl)
        
        with self._lock:
            ns_cache = self._get_namespace_cache(namespace)
            cache_key = self._make_cache_key(key, namespace)
            
            # 更新缓存
            self._evict_if_needed(namespace)
            entry = CacheEntry(
                key=key,
                value=value,
                namespace=namespace,
                ttl=ttl or self._config.default_ttl,
            )
            ns_cache[cache_key] = entry
            self._stats.updates += 1
            
            # 写穿透：同时写入后端
            if self._config.policy == CachePolicy.WRITE_THROUGH:
                return self._backend.set(key, value, namespace, ttl)
            
            return True
    
    def delete(self, key: str, namespace: str = "default") -> bool:
        """删除值（使缓存失效）"""
        with self._lock:
            ns_cache = self._get_namespace_cache(namespace)
            cache_key = self._make_cache_key(key, namespace)
            
            # 从缓存移除
            if cache_key in ns_cache:
                del ns_cache[cache_key]
                self._stats.invalidations += 1
            
            # 从后端删除
            return self._backend.delete(key, namespace)
    
    def invalidate(self, key: str, namespace: str = "default") -> bool:
        """使缓存失效"""
        with self._lock:
            ns_cache = self._get_namespace_cache(namespace)
            cache_key = self._make_cache_key(key, namespace)
            
            if cache_key in ns_cache:
                del ns_cache[cache_key]
                self._stats.invalidations += 1
                return True
            return False
    
    def invalidate_all(self, namespace: str = "default") -> int:
        """使命名空间所有缓存失效"""
        with self._lock:
            ns_cache = self._get_namespace_cache(namespace)
            count = len(ns_cache)
            ns_cache.clear()
            self._stats.invalidations += count
            return count
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        with self._lock:
            total_entries = sum(len(ns) for ns in self._cache.values())
            namespaces = list(self._cache.keys())
            return {
                "enabled": self._config.enabled,
                "policy": self._config.policy.value,
                "eviction": self._config.eviction.value,
                "max_size": self._config.max_size,
                "total_entries": total_entries,
                "namespaces": namespaces,
                "hits": self._stats.hits,
                "misses": self._stats.misses,
                "hit_rate": self._stats.hit_rate,
                "evictions": self._stats.evictions,
                "updates": self._stats.updates,
                "invalidations": self._stats.invalidations,
            }
    
    def clear(self) -> int:
        """清空所有缓存"""
        with self._lock:
            total = sum(len(ns) for ns in self._cache.values())
            self._cache.clear()
            return total


# ============================================================================
# 缓存装饰器
# ============================================================================


def cached(storage_cache: StorageCache, namespace: str = "default",
           ttl: Optional[float] = None) -> Callable:
    """
    缓存装饰器
    
    用于装饰函数，自动缓存其返回值。
    """
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs) -> Any:
            # 生成缓存键
            cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # 尝试从缓存获取
            cached_value = storage_cache.get(cache_key, namespace)
            if cached_value is not None:
                return cached_value
            
            # 计算并缓存
            result = func(*args, **kwargs)
            storage_cache.set(cache_key, result, namespace, ttl)
            return result
        
        return wrapper
    return decorator


# ============================================================================
# 全局单例
# ============================================================================

_storage_cache_instance: Optional[StorageCache] = None
_storage_cache_lock = threading.Lock()


def get_storage_cache() -> StorageCache:
    """获取存储缓存全局单例"""
    global _storage_cache_instance
    with _storage_cache_lock:
        return _storage_cache_instance


def init_storage_cache(backend: StorageBackend, config: Optional[CacheConfig] = None) -> StorageCache:
    """初始化存储缓存全局单例"""
    global _storage_cache_instance
    with _storage_cache_lock:
        if _storage_cache_instance is None:
            _storage_cache_instance = StorageCache(backend, config)
        return _storage_cache_instance
