#!/usr/bin/env python3
"""
连接池 (ConnectionPool) - 阶段349

职责：
- 连接复用：减少创建/销毁开销
- 健康检查：定期检测连接可用性
- 超时管理：获取/使用超时控制
- 连接生命周期：创建、借出、归还、销毁
- 池化统计：利用率、等待时间

设计原则：
- 确定性规则，无模型依赖
- 线程安全（RLock + Condition）
- 最小层级，无循环依赖
"""

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


# ============================================================
# 枚举与数据结构
# ============================================================

class ConnStatus(Enum):
    """连接状态"""
    IDLE = "idle"       # 空闲（在池中）
    BORROWED = "borrowed"  # 借出
    CLOSED = "closed"     # 已关闭


@dataclass
class PooledConnection:
    """池化连接"""
    id: str = ""
    conn: Any = None
    status: ConnStatus = ConnStatus.IDLE
    created_at: float = 0.0
    borrowed_at: float = 0.0
    returned_at: float = 0.0
    last_used_at: float = 0.0
    borrow_count: int = 0
    error_count: int = 0
    is_healthy: bool = True

    def __post_init__(self):
        now = time.time()
        if self.created_at == 0.0:
            self.created_at = now
        if not self.id:
            import uuid
            self.id = uuid.uuid4().hex[:8]


@dataclass
class PoolConfig:
    """连接池配置"""
    min_size: int = 2          # 最小连接数
    max_size: int = 10         # 最大连接数
    acquire_timeout: float = 5.0  # 获取超时（秒）
    max_idle_time: float = 300.0  # 最大空闲时间
    max_borrow_time: float = 60.0  # 最大借出时间
    health_check_interval: float = 30.0  # 健康检查间隔
    max_lifetime: float = 3600.0  # 连接最大生命周期


@dataclass
class PoolStats:
    """连接池统计"""
    total_created: int = 0
    total_destroyed: int = 0
    active: int = 0          # 借出中
    idle: int = 0            # 空闲
    waiting: int = 0         # 等待获取
    total_borrows: int = 0
    total_returns: int = 0
    total_timeouts: int = 0
    total_errors: int = 0
    avg_wait_time: float = 0.0
    avg_borrow_time: float = 0.0

    @property
    def utilization(self) -> float:
        total = self.active + self.idle
        return self.active / total if total > 0 else 0.0


# ============================================================
# 连接池
# ============================================================

class ConnectionPool:
    """
    连接池

    核心功能：
    1. 连接复用
    2. 自动扩缩容
    3. 健康检查
    4. 超时管理
    5. 空闲回收
    """

    def __init__(self, name: str = "default",
                 config: Optional[PoolConfig] = None,
                 factory: Optional[Callable[[], Any]] = None,
                 destroyer: Optional[Callable[[Any], None]] = None,
                 health_checker: Optional[Callable[[Any], bool]] = None):
        self.name = name
        self._config = config or PoolConfig()
        self._factory = factory or (lambda: {"connection": "mock"})
        self._destroyer = destroyer or (lambda c: None)
        self._health_checker = health_checker or (lambda c: True)

        self._idle: deque = deque()      # 空闲连接
        self._borrowed: Dict[str, PooledConnection] = {}  # 借出连接
        self._all: Dict[str, PooledConnection] = {}  # 所有连接
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._stats = PoolStats()
        self._closed = False

    def acquire(self, timeout: Optional[float] = None) -> Optional[PooledConnection]:
        """
        获取连接

        Returns:
            连接对象或None（超时）
        """
        if timeout is None:
            timeout = self._config.acquire_timeout

        deadline = time.time() + timeout

        with self._condition:
            while True:
                if self._closed:
                    return None

                # 尝试获取空闲连接
                while self._idle:
                    pc = self._idle.popleft()
                    if self._is_alive(pc):
                        pc.status = ConnStatus.BORROWED
                        pc.borrowed_at = time.time()
                        pc.last_used_at = time.time()
                        pc.borrow_count += 1
                        self._borrowed[pc.id] = pc
                        self._stats.total_borrows += 1
                        return pc
                    else:
                        self._destroy_connection(pc)

                # 创建新连接
                total = len(self._borrowed) + len(self._idle)
                if total < self._config.max_size:
                    pc = self._create_connection()
                    if pc:
                        pc.status = ConnStatus.BORROWED
                        pc.borrowed_at = time.time()
                        pc.last_used_at = time.time()
                        pc.borrow_count += 1
                        self._borrowed[pc.id] = pc
                        self._stats.total_borrows += 1
                        return pc

                # 等待空闲连接
                remaining = deadline - time.time()
                if remaining <= 0:
                    self._stats.total_timeouts += 1
                    return None

                self._stats.waiting += 1
                self._condition.wait(timeout=min(remaining, 1.0))
                self._stats.waiting -= 1

    def release(self, conn_id: str) -> bool:
        """归还连接"""
        with self._lock:
            pc = self._borrowed.pop(conn_id, None)
            if pc is None:
                return False

            pc.status = ConnStatus.IDLE
            pc.returned_at = time.time()
            self._stats.total_returns += 1

            # 检查是否超过最大生命周期
            if (time.time() - pc.created_at) > self._config.max_lifetime:
                self._destroy_connection(pc)
            else:
                self._idle.append(pc)
                self._condition.notify()

            return True

    def _create_connection(self) -> Optional[PooledConnection]:
        """创建新连接"""
        try:
            conn = self._factory()
            pc = PooledConnection(conn=conn)
            self._all[pc.id] = pc
            self._stats.total_created += 1
            return pc
        except Exception:
            self._stats.total_errors += 1
            return None

    def _destroy_connection(self, pc: PooledConnection) -> None:
        """销毁连接"""
        try:
            self._destroyer(pc.conn)
        except Exception:
            pass
        self._all.pop(pc.id, None)
        self._stats.total_destroyed += 1

    def _is_alive(self, pc: PooledConnection) -> bool:
        """检查连接是否存活"""
        if not pc.is_healthy:
            return False
        try:
            return self._health_checker(pc.conn)
        except Exception:
            return False

    def close(self) -> None:
        """关闭连接池"""
        with self._lock:
            self._closed = True
            for pc in self._borrowed.values():
                self._destroy_connection(pc)
            for pc in self._idle:
                self._destroy_connection(pc)
            self._borrowed.clear()
            self._idle.clear()
            self._condition.notify_all()

    def health_check(self) -> Dict[str, Any]:
        """执行健康检查"""
        removed = 0
        with self._lock:
            healthy = []
            unhealthy = []
            for pc in list(self._idle):
                if self._is_alive(pc):
                    healthy.append(pc.id)
                else:
                    unhealthy.append(pc.id)
                    self._idle.remove(pc)
                    self._destroy_connection(pc)
                    removed += 1
            self._condition.notify()
        return {"healthy": len(healthy), "unhealthy": len(unhealthy), "removed": removed}

    def cleanup_idle(self) -> int:
        """清理过期空闲连接"""
        removed = 0
        now = time.time()
        with self._lock:
            to_remove = []
            for pc in self._idle:
                idle_time = now - pc.returned_at if pc.returned_at > 0 else now - pc.created_at
                if idle_time > self._config.max_idle_time:
                    to_remove.append(pc)
                elif (now - pc.created_at) > self._config.max_lifetime:
                    to_remove.append(pc)
            for pc in to_remove:
                self._idle.remove(pc)
                self._destroy_connection(pc)
                removed += 1
        return removed

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            self._stats.active = len(self._borrowed)
            self._stats.idle = len(self._idle)
            return {
                "name": self.name,
                "active": self._stats.active,
                "idle": self._stats.idle,
                "total": self._stats.active + self._stats.idle,
                "max_size": self._config.max_size,
                "utilization": round(self._stats.utilization, 4),
                "total_created": self._stats.total_created,
                "total_destroyed": self._stats.total_destroyed,
                "total_borrows": self._stats.total_borrows,
                "total_returns": self._stats.total_returns,
                "total_timeouts": self._stats.total_timeouts,
                "waiting": self._stats.waiting,
            }


# ============================================================
# 连接池管理器
# ============================================================

class ConnectionPoolManager:
    """连接池管理器"""

    def __init__(self):
        self._pools: Dict[str, ConnectionPool] = {}
        self._lock = threading.RLock()

    def create_pool(self, name: str, config: Optional[PoolConfig] = None,
                    factory: Optional[Callable[[], Any]] = None,
                    destroyer: Optional[Callable[[Any], None]] = None,
                    health_checker: Optional[Callable[[Any], bool]] = None) -> ConnectionPool:
        """创建连接池"""
        with self._lock:
            pool = ConnectionPool(name, config, factory, destroyer, health_checker)
            self._pools[name] = pool
            return pool

    def get_pool(self, name: str) -> Optional[ConnectionPool]:
        """获取连接池"""
        return self._pools.get(name)

    def remove_pool(self, name: str) -> bool:
        """移除连接池"""
        with self._lock:
            pool = self._pools.pop(name, None)
            if pool:
                pool.close()
                return True
            return False

    def close_all(self) -> None:
        """关闭所有连接池"""
        with self._lock:
            for pool in self._pools.values():
                pool.close()

    def get_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取所有连接池统计"""
        return {name: pool.get_stats() for name, pool in self._pools.items()}


# ============================================================
# 全局单例
# ============================================================

_pool_manager: Optional[ConnectionPoolManager] = None
_pm_lock = threading.RLock()


def get_pool_manager() -> ConnectionPoolManager:
    """获取全局连接池管理器"""
    global _pool_manager
    if _pool_manager is None:
        with _pm_lock:
            if _pool_manager is None:
                _pool_manager = ConnectionPoolManager()
    return _pool_manager
