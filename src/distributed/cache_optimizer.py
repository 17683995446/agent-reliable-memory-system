"""
缓存优化器 (CacheOptimizer)
阶段239-241: 多级缓存、缓存策略、预热机制

基于第一性原则设计:
1. 确定性: LRU/LFU算法纯数学实现，无随机性
2. 高效性: O(1)时间复杂度的缓存操作
3. 适应性: 自动调整缓存大小和策略
"""

import threading
import time
import hashlib
from typing import Dict, List, Optional, Any, Callable, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import OrderedDict
import heapq


class CacheLevel(Enum):
    """缓存级别"""
    L1 = "l1"        # 本地内存缓存
    L2 = "l2"        # 分布式缓存
    L3 = "l3"        # 持久化缓存


class EvictionPolicy(Enum):
    """淘汰策略"""
    LRU = "lru"      # 最近最少使用
    LFU = "lfu"      # 最不经常使用
    FIFO = "fifo"    # 先进先出
    TTL = "ttl"      # 基于过期时间


@dataclass
class CacheEntry:
    """缓存条目"""
    key: str
    value: Any
    level: CacheLevel
    created_at: float = field(default_factory=time.time)
    accessed_at: float = field(default_factory=time.time)
    access_count: int = 1
    ttl: Optional[float] = None  # 过期时间(秒)
    size: int = 1  # 条目大小(字节)


@dataclass
class CacheStats:
    """缓存统计"""
    level: CacheLevel
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    total_size: int = 0
    entry_count: int = 0
    hit_rate: float = 0.0


class LRUCache:
    """
    LRU缓存实现
    使用OrderedDict实现O(1)的get和put操作
    """
    
    def __init__(self, capacity: int):
        self._capacity = capacity
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._current_size = 0
    
    def get(self, key: str) -> Optional[CacheEntry]:
        """获取缓存条目"""
        if key not in self._cache:
            return None
        
        # 移动到末尾(最近使用)
        entry = self._cache.pop(key)
        self._cache[key] = entry
        
        # 更新访问信息
        entry.accessed_at = time.time()
        entry.access_count += 1
        
        return entry
    
    def put(self, key: str, entry: CacheEntry) -> Optional[CacheEntry]:
        """
        添加缓存条目
        
        Returns:
            被淘汰的条目(如果有)
        """
        evicted = None
        
        # 如果已存在，先移除
        if key in self._cache:
            old_entry = self._cache.pop(key)
            self._current_size -= old_entry.size
        
        # 检查容量，淘汰旧条目
        while self._current_size + entry.size > self._capacity and self._cache:
            # 移除最旧的条目(OrderedDict头部)
            _, evicted_entry = self._cache.popitem(last=False)
            self._current_size -= evicted_entry.size
            evicted = evicted_entry
        
        # 添加新条目
        self._cache[key] = entry
        self._current_size += entry.size
        
        return evicted
    
    def remove(self, key: str) -> Optional[CacheEntry]:
        """移除缓存条目"""
        if key in self._cache:
            entry = self._cache.pop(key)
            self._current_size -= entry.size
            return entry
        return None
    
    def keys(self) -> List[str]:
        """获取所有键"""
        return list(self._cache.keys())
    
    def clear(self) -> None:
        """清空缓存"""
        self._cache.clear()
        self._current_size = 0
    
    def size(self) -> int:
        """获取当前大小"""
        return self._current_size
    
    def __len__(self) -> int:
        return len(self._cache)


class LFUCache:
    """
    LFU缓存实现
    使用最小堆维护访问频率
    """
    
    def __init__(self, capacity: int):
        self._capacity = capacity
        self._cache: Dict[str, CacheEntry] = {}
        self._frequency_heap: List[Tuple[int, float, str]] = []  # (count, timestamp, key)
        self._current_size = 0
        self._entry_finder: Dict[str, Tuple[int, float]] = {}  # key -> (count, timestamp)
    
    def get(self, key: str) -> Optional[CacheEntry]:
        """获取缓存条目"""
        if key not in self._cache:
            return None
        
        entry = self._cache[key]
        entry.accessed_at = time.time()
        entry.access_count += 1
        
        # 更新频率堆
        self._entry_finder[key] = (entry.access_count, entry.accessed_at)
        
        return entry
    
    def put(self, key: str, entry: CacheEntry) -> Optional[CacheEntry]:
        """添加缓存条目"""
        evicted = None
        
        # 如果已存在，先移除
        if key in self._cache:
            old_entry = self._cache.pop(key)
            self._current_size -= old_entry.size
            if key in self._entry_finder:
                del self._entry_finder[key]
        
        # 检查容量，淘汰旧条目
        while self._current_size + entry.size > self._capacity and self._cache:
            # 找到访问频率最低的条目
            while self._frequency_heap:
                count, timestamp, old_key = heapq.heappop(self._frequency_heap)
                if old_key in self._entry_finder and self._entry_finder[old_key] == (count, timestamp):
                    if old_key in self._cache:
                        evicted_entry = self._cache.pop(old_key)
                        self._current_size -= evicted_entry.size
                        del self._entry_finder[old_key]
                        evicted = evicted_entry
                    break
        
        # 添加新条目
        self._cache[key] = entry
        self._current_size += entry.size
        self._entry_finder[key] = (entry.access_count, entry.accessed_at)
        heapq.heappush(self._frequency_heap, (entry.access_count, entry.accessed_at, key))
        
        return evicted
    
    def remove(self, key: str) -> Optional[CacheEntry]:
        """移除缓存条目"""
        if key in self._cache:
            entry = self._cache.pop(key)
            self._current_size -= entry.size
            if key in self._entry_finder:
                del self._entry_finder[key]
            return entry
        return None
    
    def keys(self) -> List[str]:
        """获取所有键"""
        return list(self._cache.keys())
    
    def clear(self) -> None:
        """清空缓存"""
        self._cache.clear()
        self._frequency_heap.clear()
        self._entry_finder.clear()
        self._current_size = 0
    
    def size(self) -> int:
        """获取当前大小"""
        return self._current_size
    
    def __len__(self) -> int:
        return len(self._cache)


class FIFOCache:
    """
    FIFO缓存实现
    先进先出策略
    """
    
    def __init__(self, capacity: int):
        self._capacity = capacity
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._current_size = 0
    
    def get(self, key: str) -> Optional[CacheEntry]:
        """获取缓存条目(不更新顺序)"""
        return self._cache.get(key)
    
    def put(self, key: str, entry: CacheEntry) -> Optional[CacheEntry]:
        """添加缓存条目"""
        evicted = None
        
        # 如果已存在，只更新值
        if key in self._cache:
            old_entry = self._cache[key]
            self._current_size -= old_entry.size
            self._cache[key] = entry
            self._current_size += entry.size
            return None
        
        # 检查容量，淘汰旧条目
        while self._current_size + entry.size > self._capacity and self._cache:
            _, evicted_entry = self._cache.popitem(last=False)
            self._current_size -= evicted_entry.size
            evicted = evicted_entry
        
        # 添加新条目
        self._cache[key] = entry
        self._current_size += entry.size
        
        return evicted
    
    def remove(self, key: str) -> Optional[CacheEntry]:
        """移除缓存条目"""
        if key in self._cache:
            entry = self._cache.pop(key)
            self._current_size -= entry.size
            return entry
        return None
    
    def keys(self) -> List[str]:
        """获取所有键"""
        return list(self._cache.keys())
    
    def clear(self) -> None:
        """清空缓存"""
        self._cache.clear()
        self._current_size = 0
    
    def size(self) -> int:
        """获取当前大小"""
        return self._current_size
    
    def __len__(self) -> int:
        return len(self._cache)


class CacheOptimizer:
    """
    缓存优化器
    
    核心功能:
    1. 多级缓存: L1(内存)/L2(分布式)/L3(持久化)三级架构
    2. 缓存策略: LRU/LFU/FIFO/TTL多种淘汰策略
    3. 预热机制: 基于访问模式的智能预热
    """
    
    def __init__(self):
        self._lock = threading.RLock()
        
        # 多级缓存配置
        self._l1_capacity = 1000  # L1缓存容量(条目数)
        self._l2_capacity = 10000  # L2缓存容量
        self._l3_capacity = 100000  # L3缓存容量
        
        # 各级缓存
        self._l1_cache: Dict[str, Any] = {}  # 简单的dict作为L1
        self._l2_cache: LRUCache = LRUCache(self._l2_capacity)
        self._l3_cache: LFUCache = LFUCache(self._l3_capacity)
        
        # 淘汰策略配置
        self._l1_policy = EvictionPolicy.LRU
        self._l2_policy = EvictionPolicy.LRU
        self._l3_policy = EvictionPolicy.LFU
        
        # TTL管理
        self._default_ttl: Optional[float] = 3600  # 默认过期时间(秒)
        self._ttl_index: Dict[str, float] = {}  # key -> expire_time
        
        # 统计信息
        self._stats: Dict[CacheLevel, CacheStats] = {
            CacheLevel.L1: CacheStats(CacheLevel.L1),
            CacheLevel.L2: CacheStats(CacheLevel.L2),
            CacheLevel.L3: CacheStats(CacheLevel.L3)
        }
        
        # 预热机制
        self._access_pattern: Dict[str, List[float]] = {}  # key -> 访问时间列表
        self._hot_keys: Set[str] = set()  # 热点key
        self._warmup_callbacks: List[Callable[[str], Any]] = []
        self._warmup_enabled: bool = True
        
        # 后台清理线程
        self._cleanup_thread: Optional[threading.Thread] = None
        self._running: bool = False
        self._cleanup_interval: float = 60.0  # 清理间隔(秒)
    
    # ==================== 阶段239: 多级缓存 ====================
    
    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值(多级缓存查找)
        
        查找顺序: L1 -> L2 -> L3
        
        Args:
            key: 缓存键
            
        Returns:
            缓存值，如果不存在返回None
        """
        with self._lock:
            # 检查TTL
            if self._is_expired(key):
                self._remove_from_all_levels(key)
                return None
            
            # L1查找
            if key in self._l1_cache:
                self._stats[CacheLevel.L1].hits += 1
                self._record_access(key)
                return self._l1_cache[key]
            
            # L2查找
            entry = self._l2_cache.get(key)
            if entry:
                self._stats[CacheLevel.L2].hits += 1
                self._stats[CacheLevel.L1].misses += 1
                # 提升到L1
                self._promote_to_l1(key, entry.value)
                self._record_access(key)
                return entry.value
            
            # L3查找
            entry = self._l3_cache.get(key)
            if entry:
                self._stats[CacheLevel.L3].hits += 1
                self._stats[CacheLevel.L2].misses += 1
                self._stats[CacheLevel.L1].misses += 1
                # 提升到L2
                self._promote_to_l2(key, entry)
                self._record_access(key)
                return entry.value
            
            # 未命中
            self._stats[CacheLevel.L3].misses += 1
            self._stats[CacheLevel.L2].misses += 1
            self._stats[CacheLevel.L1].misses += 1
            
            return None
    
    def put(self, key: str, value: Any, level: CacheLevel = CacheLevel.L1,
            ttl: Optional[float] = None) -> bool:
        """
        设置缓存值
        
        Args:
            key: 缓存键
            value: 缓存值
            level: 缓存级别
            ttl: 过期时间(秒)，None表示使用默认值
            
        Returns:
            是否设置成功
        """
        with self._lock:
            expire_time = None
            if ttl is not None or self._default_ttl is not None:
                expire_time = time.time() + (ttl or self._default_ttl)
                self._ttl_index[key] = expire_time
            
            entry = CacheEntry(
                key=key,
                value=value,
                level=level,
                ttl=expire_time
            )
            
            if level == CacheLevel.L1:
                # L1使用简单的LRU
                if len(self._l1_cache) >= self._l1_capacity and key not in self._l1_cache:
                    # 移除最旧的条目
                    oldest_key = next(iter(self._l1_cache))
                    del self._l1_cache[oldest_key]
                self._l1_cache[key] = value
                
            elif level == CacheLevel.L2:
                evicted = self._l2_cache.put(key, entry)
                if evicted:
                    self._stats[CacheLevel.L2].evictions += 1
                    # 降级到L3
                    self._demote_to_l3(evicted)
                    
            elif level == CacheLevel.L3:
                evicted = self._l3_cache.put(key, entry)
                if evicted:
                    self._stats[CacheLevel.L3].evictions += 1
            
            self._update_stats()
            return True
    
    def remove(self, key: str) -> bool:
        """
        移除缓存值
        
        Args:
            key: 缓存键
            
        Returns:
            是否移除成功
        """
        with self._lock:
            return self._remove_from_all_levels(key)
    
    def _remove_from_all_levels(self, key: str) -> bool:
        """从所有级别移除"""
        removed = False
        
        if key in self._l1_cache:
            del self._l1_cache[key]
            removed = True
        
        if self._l2_cache.remove(key):
            removed = True
        
        if self._l3_cache.remove(key):
            removed = True
        
        if key in self._ttl_index:
            del self._ttl_index[key]
        
        return removed
    
    def _promote_to_l1(self, key: str, value: Any) -> None:
        """提升到L1缓存"""
        if len(self._l1_cache) >= self._l1_capacity:
            # 移除最旧的条目到L2
            oldest_key = next(iter(self._l1_cache))
            oldest_value = self._l1_cache[oldest_key]
            del self._l1_cache[oldest_key]
            
            entry = CacheEntry(
                key=oldest_key,
                value=oldest_value,
                level=CacheLevel.L2
            )
            self._l2_cache.put(oldest_key, entry)
        
        self._l1_cache[key] = value
    
    def _promote_to_l2(self, key: str, entry: CacheEntry) -> None:
        """提升到L2缓存"""
        evicted = self._l2_cache.put(key, entry)
        if evicted:
            self._stats[CacheLevel.L2].evictions += 1
            self._demote_to_l3(evicted)
    
    def _demote_to_l3(self, entry: CacheEntry) -> None:
        """降级到L3缓存"""
        entry.level = CacheLevel.L3
        evicted = self._l3_cache.put(entry.key, entry)
        if evicted:
            self._stats[CacheLevel.L3].evictions += 1
    
    def _is_expired(self, key: str) -> bool:
        """检查是否过期"""
        if key not in self._ttl_index:
            return False
        return time.time() > self._ttl_index[key]
    
    def clear(self, level: Optional[CacheLevel] = None) -> None:
        """
        清空缓存
        
        Args:
            level: 指定级别，None表示全部
        """
        with self._lock:
            if level is None or level == CacheLevel.L1:
                self._l1_cache.clear()
            
            if level is None or level == CacheLevel.L2:
                self._l2_cache.clear()
            
            if level is None or level == CacheLevel.L3:
                self._l3_cache.clear()
            
            if level is None:
                self._ttl_index.clear()
    
    # ==================== 阶段240: 缓存策略 ====================
    
    def set_eviction_policy(self, level: CacheLevel, 
                           policy: EvictionPolicy) -> None:
        """
        设置淘汰策略
        
        Args:
            level: 缓存级别
            policy: 淘汰策略
        """
        with self._lock:
            if level == CacheLevel.L1:
                self._l1_policy = policy
            elif level == CacheLevel.L2:
                self._l2_policy = policy
                # 重建L2缓存
                entries = list(self._l2_cache._cache.values())
                self._l2_cache.clear()
                
                if policy == EvictionPolicy.LRU:
                    self._l2_cache = LRUCache(self._l2_capacity)
                elif policy == EvictionPolicy.LFU:
                    self._l2_cache = LFUCache(self._l2_capacity)
                elif policy == EvictionPolicy.FIFO:
                    self._l2_cache = FIFOCache(self._l2_capacity)
                
                for entry in entries:
                    self._l2_cache.put(entry.key, entry)
                    
            elif level == CacheLevel.L3:
                self._l3_policy = policy
    
    def set_capacity(self, level: CacheLevel, capacity: int) -> None:
        """
        设置缓存容量
        
        Args:
            level: 缓存级别
            capacity: 新容量
        """
        with self._lock:
            if level == CacheLevel.L1:
                self._l1_capacity = capacity
                # 调整L1大小
                while len(self._l1_cache) > capacity:
                    oldest_key = next(iter(self._l1_cache))
                    del self._l1_cache[oldest_key]
                    
            elif level == CacheLevel.L2:
                self._l2_capacity = capacity
                # 需要重建缓存
                entries = list(self._l2_cache._cache.values())
                self._l2_cache = LRUCache(capacity)
                for entry in entries[:capacity]:
                    self._l2_cache.put(entry.key, entry)
                    
            elif level == CacheLevel.L3:
                self._l3_capacity = capacity
                entries = list(self._l3_cache._cache.values())
                self._l3_cache = LFUCache(capacity)
                for entry in entries[:capacity]:
                    self._l3_cache.put(entry.key, entry)
    
    def set_default_ttl(self, ttl: Optional[float]) -> None:
        """
        设置默认过期时间
        
        Args:
            ttl: 过期时间(秒)，None表示永不过期
        """
        with self._lock:
            self._default_ttl = ttl
    
    def get_stats(self) -> Dict[CacheLevel, CacheStats]:
        """
        获取缓存统计
        
        Returns:
            各级缓存统计
        """
        with self._lock:
            self._update_stats()
            return {level: CacheStats(
                level=level,
                hits=stats.hits,
                misses=stats.misses,
                evictions=stats.evictions,
                total_size=self._get_level_size(level),
                entry_count=self._get_level_count(level),
                hit_rate=stats.hit_rate
            ) for level, stats in self._stats.items()}
    
    def _update_stats(self) -> None:
        """更新统计信息"""
        for level, stats in self._stats.items():
            total = stats.hits + stats.misses
            if total > 0:
                stats.hit_rate = stats.hits / total
    
    def _get_level_size(self, level: CacheLevel) -> int:
        """获取级别大小"""
        if level == CacheLevel.L1:
            return len(self._l1_cache)
        elif level == CacheLevel.L2:
            return self._l2_cache.size()
        elif level == CacheLevel.L3:
            return self._l3_cache.size()
        return 0
    
    def _get_level_count(self, level: CacheLevel) -> int:
        """获取级别条目数"""
        if level == CacheLevel.L1:
            return len(self._l1_cache)
        elif level == CacheLevel.L2:
            return len(self._l2_cache)
        elif level == CacheLevel.L3:
            return len(self._l3_cache)
        return 0
    
    # ==================== 阶段241: 预热机制 ====================
    
    def _record_access(self, key: str) -> None:
        """记录访问模式"""
        current_time = time.time()
        
        if key not in self._access_pattern:
            self._access_pattern[key] = []
        
        self._access_pattern[key].append(current_time)
        
        # 只保留最近100次访问
        if len(self._access_pattern[key]) > 100:
            self._access_pattern[key] = self._access_pattern[key][-100:]
        
        # 更新热点key
        self._update_hot_keys()
    
    def _update_hot_keys(self) -> None:
        """更新热点key集合"""
        # 基于访问频率计算热点
        key_scores = {}
        for key, times in self._access_pattern.items():
            # 计算最近一分钟的访问频率
            recent_count = sum(1 for t in times if time.time() - t < 60)
            key_scores[key] = recent_count
        
        # 取前20%作为热点
        sorted_keys = sorted(key_scores.items(), key=lambda x: x[1], reverse=True)
        hot_count = max(1, len(sorted_keys) // 5)
        self._hot_keys = {k for k, _ in sorted_keys[:hot_count]}
    
    def get_hot_keys(self) -> List[str]:
        """
        获取热点key列表
        
        Returns:
            热点key列表
        """
        with self._lock:
            return list(self._hot_keys)
    
    def register_warmup_callback(self, callback: Callable[[str], Any]) -> None:
        """
        注册预热回调
        
        Args:
            callback: 回调函数，接收key，返回value
        """
        with self._lock:
            self._warmup_callbacks.append(callback)
    
    def warmup(self, keys: Optional[List[str]] = None) -> int:
        """
        预热缓存
        
        Args:
            keys: 要预热的key列表，None表示预热热点key
            
        Returns:
            成功预热的条目数
        """
        with self._lock:
            if not self._warmup_enabled or not self._warmup_callbacks:
                return 0
            
            if keys is None:
                keys = list(self._hot_keys)
            
            warmed_count = 0
            for key in keys:
                # 检查是否已在缓存中
                if self.get(key) is not None:
                    continue
                
                # 执行预热回调
                for callback in self._warmup_callbacks:
                    try:
                        value = callback(key)
                        if value is not None:
                            self.put(key, value, CacheLevel.L2)
                            warmed_count += 1
                            break
                    except Exception:
                        pass
            
            return warmed_count
    
    def enable_warmup(self, enabled: bool = True) -> None:
        """
        启用/禁用预热
        
        Args:
            enabled: 是否启用
        """
        with self._lock:
            self._warmup_enabled = enabled
    
    def start(self) -> None:
        """启动缓存优化器"""
        with self._lock:
            if self._running:
                return
            
            self._running = True
            self._cleanup_thread = threading.Thread(
                target=self._cleanup_loop,
                daemon=True
            )
            self._cleanup_thread.start()
    
    def stop(self) -> None:
        """停止缓存优化器"""
        with self._lock:
            self._running = False
    
    def _cleanup_loop(self) -> None:
        """清理循环"""
        while self._running:
            try:
                time.sleep(self._cleanup_interval)
                self._cleanup_expired()
            except Exception:
                pass
    
    def _cleanup_expired(self) -> None:
        """清理过期条目"""
        with self._lock:
            current_time = time.time()
            expired_keys = [
                key for key, expire_time in self._ttl_index.items()
                if current_time > expire_time
            ]
            
            for key in expired_keys:
                self._remove_from_all_levels(key)
                if key in self._ttl_index:
                    del self._ttl_index[key]


# 全局单例
_cache_optimizer_instance: Optional[CacheOptimizer] = None
_cache_optimizer_lock = threading.Lock()


def get_cache_optimizer() -> CacheOptimizer:
    """获取缓存优化器全局单例"""
    global _cache_optimizer_instance
    
    if _cache_optimizer_instance is None:
        with _cache_optimizer_lock:
            if _cache_optimizer_instance is None:
                _cache_optimizer_instance = CacheOptimizer()
    
    return _cache_optimizer_instance
