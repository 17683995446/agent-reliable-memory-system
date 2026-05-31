#!/usr/bin/env python3
"""
熔断器 (CircuitBreaker) - 阶段348

职责：
- 状态机：CLOSED → OPEN → HALF_OPEN → CLOSED
- 故障检测：错误率阈值触发熔断
- 半开探测：允许少量请求探测恢复
- 降级策略：熔断时返回降级数据
- 熔断事件通知

设计原则：
- 确定性规则，无模型依赖
- 线程安全（RLock）
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

class CircuitState(Enum):
    """熔断器状态"""
    CLOSED = "closed"       # 正常（关闭熔断）
    OPEN = "open"           # 熔断（打开）
    HALF_OPEN = "half_open"  # 半开（探测中）


@dataclass
class CircuitConfig:
    """熔断器配置"""
    failure_threshold: int = 5        # 触发熔断的失败次数
    success_threshold: int = 3        # 半开→关闭的成功次数
    timeout_seconds: float = 30.0     # 熔断超时（多久后进入半开）
    half_open_max_calls: int = 3      # 半开状态最大探测请求数
    window_seconds: float = 60.0      # 统计窗口大小
    slow_call_threshold: float = 5.0  # 慢调用阈值（秒）
    slow_call_rate_threshold: float = 0.5  # 慢调用率阈值


@dataclass
class CircuitEvent:
    """熔断事件"""
    name: str
    state: CircuitState
    timestamp: float = 0.0
    message: str = ""
    error_count: int = 0
    success_count: int = 0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


@dataclass
class CircuitStats:
    """熔断器统计"""
    state: str = "closed"
    total_calls: int = 0
    success_calls: int = 0
    failure_calls: int = 0
    slow_calls: int = 0
    state_changes: int = 0
    last_failure_at: float = 0.0
    last_state_change: float = 0.0
    opened_at: float = 0.0

    @property
    def failure_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.failure_calls / self.total_calls


# ============================================================
# 熔断器
# ============================================================

class CircuitBreaker:
    """
    熔断器

    核心功能：
    1. 三态状态机（CLOSED/OPEN/HALF_OPEN）
    2. 滑动窗口统计
    3. 半开探测
    4. 降级回调
    5. 事件通知
    """

    def __init__(self, name: str, config: Optional[CircuitConfig] = None):
        self.name = name
        self._config = config or CircuitConfig()
        self._state = CircuitState.CLOSED
        self._lock = threading.RLock()

        # 滑动窗口
        self._successes: deque = deque()
        self._failures: deque = deque()
        self._slow_calls: deque = deque()

        # 半开探测计数
        self._half_open_calls = 0
        self._half_open_successes = 0

        # 统计
        self._stats = CircuitStats()
        self._stats.last_state_change = time.time()

        # 回调
        self._fallback: Optional[Callable[[], Any]] = None
        self._listeners: List[Callable[[CircuitEvent], None]] = []

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def is_open(self) -> bool:
        return self._state == CircuitState.OPEN

    @property
    def is_closed(self) -> bool:
        return self._state == CircuitState.CLOSED

    def set_fallback(self, fn: Callable[[], Any]) -> None:
        """设置降级回调"""
        self._fallback = fn

    def add_listener(self, fn: Callable[[CircuitEvent], None]) -> None:
        """添加状态变更监听器"""
        self._listeners.append(fn)

    def call(self, fn: Callable[[], Any]) -> Any:
        """
        通过熔断器调用函数

        Returns:
            函数结果或降级结果
        """
        with self._lock:
            if self._state == CircuitState.OPEN:
                if self._should_transition_to_half_open():
                    self._transition(CircuitState.HALF_OPEN)
                else:
                    self._stats.total_calls += 1
                    if self._fallback:
                        return self._fallback()
                    raise CircuitOpenError(f"Circuit '{self.name}' is open")

        # 执行调用
        start = time.time()
        try:
            result = fn()
            elapsed = time.time() - start

            with self._lock:
                self._stats.total_calls += 1
                self._stats.success_calls += 1

                if elapsed > self._config.slow_call_threshold:
                    self._stats.slow_calls += 1
                    self._record_slow(elapsed)

                self._record_success()

                if self._state == CircuitState.HALF_OPEN:
                    self._half_open_successes += 1
                    if self._half_open_successes >= self._config.success_threshold:
                        self._transition(CircuitState.CLOSED)

            return result

        except Exception as e:
            elapsed = time.time() - start
            with self._lock:
                self._stats.total_calls += 1
                self._stats.failure_calls += 1
                self._stats.last_failure_at = time.time()

                self._record_failure()

                if self._state == CircuitState.HALF_OPEN:
                    self._transition(CircuitState.OPEN)

                # 检查是否需要熔断
                if self._state == CircuitState.CLOSED:
                    if self._should_open():
                        self._transition(CircuitState.OPEN)

            if self._fallback:
                return self._fallback()
            raise

    def _should_open(self) -> bool:
        """判断是否应该熔断"""
        window = self._config.window_seconds
        cutoff = time.time() - window

        # 清理过期记录
        while self._failures and self._failures[0] < cutoff:
            self._failures.popleft()

        return len(self._failures) >= self._config.failure_threshold

    def _should_transition_to_half_open(self) -> bool:
        """判断是否应该进入半开状态"""
        return (time.time() - self._stats.opened_at) >= self._config.timeout_seconds

    def _transition(self, new_state: CircuitState) -> None:
        """状态转换"""
        old_state = self._state
        self._state = new_state
        self._stats.state = new_state.value
        self._stats.state_changes += 1
        self._stats.last_state_change = time.time()

        if new_state == CircuitState.OPEN:
            self._stats.opened_at = time.time()
        elif new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
            self._half_open_successes = 0
        elif new_state == CircuitState.CLOSED:
            self._successes.clear()
            self._failures.clear()
            self._slow_calls.clear()

        # 通知监听器
        event = CircuitEvent(
            name=self.name,
            state=new_state,
            message=f"{old_state.value} -> {new_state.value}",
            error_count=self._stats.failure_calls,
            success_count=self._stats.success_calls,
        )
        for listener in self._listeners:
            try:
                listener(event)
            except Exception:
                pass

    def _record_success(self) -> None:
        now = time.time()
        self._successes.append(now)
        self._cleanup_window(self._successes)

    def _record_failure(self) -> None:
        now = time.time()
        self._failures.append(now)
        self._cleanup_window(self._failures)

    def _record_slow(self, elapsed: float) -> None:
        now = time.time()
        self._slow_calls.append(now)
        self._cleanup_window(self._slow_calls)

    def _cleanup_window(self, dq: deque) -> None:
        cutoff = time.time() - self._config.window_seconds
        while dq and dq[0] < cutoff:
            dq.popleft()

    def force_open(self) -> None:
        """强制熔断"""
        with self._lock:
            self._transition(CircuitState.OPEN)

    def force_close(self) -> None:
        """强制关闭"""
        with self._lock:
            self._transition(CircuitState.CLOSED)

    def reset(self) -> None:
        """重置熔断器"""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._successes.clear()
            self._failures.clear()
            self._slow_calls.clear()
            self._half_open_calls = 0
            self._half_open_successes = 0
            self._stats = CircuitStats()
            self._stats.last_state_change = time.time()

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "total_calls": self._stats.total_calls,
                "success": self._stats.success_calls,
                "failure": self._stats.failure_calls,
                "slow_calls": self._stats.slow_calls,
                "failure_rate": round(self._stats.failure_rate, 4),
                "state_changes": self._stats.state_changes,
                "last_failure": self._stats.last_failure_at,
                "config": {
                    "failure_threshold": self._config.failure_threshold,
                    "success_threshold": self._config.success_threshold,
                    "timeout": self._config.timeout_seconds,
                    "window": self._config.window_seconds,
                },
            }


# ============================================================
# 熔断器管理器
# ============================================================

class CircuitBreakerManager:
    """熔断器管理器"""

    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = threading.RLock()

    def create(self, name: str,
                config: Optional[CircuitConfig] = None) -> CircuitBreaker:
        """创建熔断器"""
        with self._lock:
            cb = CircuitBreaker(name, config)
            self._breakers[name] = cb
            return cb

    def get(self, name: str) -> Optional[CircuitBreaker]:
        """获取熔断器"""
        return self._breakers.get(name)

    def remove(self, name: str) -> bool:
        """移除熔断器"""
        with self._lock:
            return self._breakers.pop(name, None) is not None

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取所有熔断器统计"""
        return {name: cb.get_stats() for name, cb in self._breakers.items()}

    def force_open_all(self) -> None:
        """强制全部熔断"""
        for cb in self._breakers.values():
            cb.force_open()

    def force_close_all(self) -> None:
        """强制全部关闭"""
        for cb in self._breakers.values():
            cb.force_close()

    def get_stats(self) -> Dict[str, Any]:
        state_counts = {}
        for cb in self._breakers.values():
            s = cb.state.value
            state_counts[s] = state_counts.get(s, 0) + 1
        return {
            "total": len(self._breakers),
            "by_state": state_counts,
        }


class CircuitOpenError(Exception):
    """熔断器打开异常"""
    pass


# ============================================================
# 全局单例
# ============================================================

_cb_manager: Optional[CircuitBreakerManager] = None
_cb_lock = threading.RLock()


def get_circuit_manager() -> CircuitBreakerManager:
    """获取全局熔断器管理器"""
    global _cb_manager
    if _cb_manager is None:
        with _cb_lock:
            if _cb_manager is None:
                _cb_manager = CircuitBreakerManager()
    return _cb_manager
