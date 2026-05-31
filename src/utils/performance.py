"""
性能优化模块
阶段 72-74：检索加速、内存精简、并发适配

核心特性：
- L3 查询缓存
- L2 向量检索优化
- L1 内存使用精简
- 并发读写锁优化
"""

import time
import threading
from typing import Dict, List, Optional, Any, Callable
from functools import wraps
from dataclasses import dataclass


class QueryCache:
    """
    查询缓存（阶段 72：L3 检索加速）
    
    缓存频繁查询的实体结果，减少 Neo4j 查询次数。
    """
    
    def __init__(self, max_size: int = 1000, ttl_seconds: int = 300):
        self.max_size = max_size
        self.ttl = ttl_seconds
        self._cache: Dict[str, Dict] = {}
        self._lock = threading.RLock()
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            
            # 检查过期
            if time.time() - entry["timestamp"] > self.ttl:
                del self._cache[key]
                return None
            
            return entry["value"]
    
    def set(self, key: str, value: Any):
        """设置缓存值"""
        with self._lock:
            # 清理过期项
            self._cleanup_expired()
            
            # 清理最旧的项（如果已满）
            if len(self._cache) >= self.max_size:
                oldest_key = min(self._cache.keys(), 
                               key=lambda k: self._cache[k]["timestamp"])
                del self._cache[oldest_key]
            
            self._cache[key] = {
                "value": value,
                "timestamp": time.time()
            }
    
    def invalidate(self, key: str):
        """使缓存项失效"""
        with self._lock:
            self._cache.pop(key, None)
    
    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()
    
    def _cleanup_expired(self):
        """清理过期项"""
        current_time = time.time()
        expired_keys = [
            k for k, v in self._cache.items()
            if current_time - v["timestamp"] > self.ttl
        ]
        for k in expired_keys:
            del self._cache[k]
    
    def get_stats(self) -> Dict[str, int]:
        """获取缓存统计"""
        with self._lock:
            return {
                "size": len(self._cache),
                "max_size": self.max_size
            }


class MemoryOptimizer:
    """
    内存优化器（阶段 74：内存精简）
    
    优化 L1 内存使用，减少无用资源占用。
    """
    
    def __init__(self, l1_memory):
        self.l1 = l1_memory
        self._cleanup_interval = 3600  # 1小时
        self._last_cleanup = time.time()
    
    def optimize(self) -> Dict[str, int]:
        """
        执行内存优化
        
        Returns:
            Dict: 优化结果统计
        """
        stats = {"cleared_sessions": 0, "freed_items": 0}
        
        # 清理超时会话
        current_time = time.time()
        timeout_threshold = current_time - 3600  # 1小时超时
        
        with self.l1._lock:
            expired_sessions = []
            for session_id, status in self.l1._task_status.items():
                if status.get("last_update", 0) < timeout_threshold:
                    expired_sessions.append(session_id)
            
            for session_id in expired_sessions:
                self.l1._clear_session(session_id)
                stats["cleared_sessions"] += 1
        
        self._last_cleanup = current_time
        return stats
    
    def should_optimize(self) -> bool:
        """检查是否应该执行优化"""
        return time.time() - self._last_cleanup > self._cleanup_interval


class ConcurrencyManager:
    """
    并发管理器（阶段 78：多任务并行适配）
    
    解决并发记忆读写冲突。
    """
    
    def __init__(self):
        # 会话级锁：session_id -> RLock
        self._session_locks: Dict[str, threading.RLock] = {}
        # 全局锁管理锁
        self._lock_manager_lock = threading.Lock()
    
    def _get_session_lock(self, session_id: str) -> threading.RLock:
        """获取会话锁"""
        with self._lock_manager_lock:
            if session_id not in self._session_locks:
                self._session_locks[session_id] = threading.RLock()
            return self._session_locks[session_id]
    
    def acquire_session(self, session_id: str):
        """获取会话锁（上下文管理器）"""
        return self._get_session_lock(session_id)
    
    def release_session(self, session_id: str):
        """释放会话锁"""
        # RLock 自动管理，无需显式释放
        pass
    
    def cleanup_session_lock(self, session_id: str):
        """清理会话锁（会话结束时调用）"""
        with self._lock_manager_lock:
            if session_id in self._session_locks:
                del self._session_locks[session_id]


def timed(func: Callable) -> Callable:
    """
    性能计时装饰器
    
    记录函数执行时间。
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = (time.time() - start) * 1000
        
        # 记录到日志
        import logging
        logger = logging.getLogger("performance")
        logger.debug(f"{func.__name__} took {elapsed:.2f}ms")
        
        return result
    return wrapper


class PerformanceMonitor:
    """
    性能监控器
    
    监控各模块性能指标。
    """
    
    def __init__(self):
        self._metrics: Dict[str, List[float]] = {
            "l1_write_latency": [],
            "l1_read_latency": [],
            "l2_search_latency": [],
            "l3_query_latency": [],
            "recall_total_latency": []
        }
        self._lock = threading.Lock()
    
    def record(self, metric_name: str, latency_ms: float):
        """记录性能指标"""
        with self._lock:
            if metric_name in self._metrics:
                self._metrics[metric_name].append(latency_ms)
                # 只保留最近 1000 条记录
                if len(self._metrics[metric_name]) > 1000:
                    self._metrics[metric_name] = self._metrics[metric_name][-1000:]
    
    def get_stats(self, metric_name: str) -> Dict[str, float]:
        """获取统计信息"""
        with self._lock:
            data = self._metrics.get(metric_name, [])
            if not data:
                return {}
            
            return {
                "count": len(data),
                "avg_ms": sum(data) / len(data),
                "min_ms": min(data),
                "max_ms": max(data),
                "p95_ms": sorted(data)[int(len(data) * 0.95)] if len(data) >= 20 else max(data)
            }
    
    def get_all_stats(self) -> Dict[str, Dict[str, float]]:
        """获取所有指标统计"""
        return {name: self.get_stats(name) for name in self._metrics.keys()}


# 全局性能监控实例
_performance_monitor: Optional[PerformanceMonitor] = None


def get_performance_monitor() -> PerformanceMonitor:
    """获取全局性能监控实例"""
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = PerformanceMonitor()
    return _performance_monitor
