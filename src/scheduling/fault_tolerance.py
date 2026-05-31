"""
容错处理模块 (阶段290-292)
FaultTolerance: 重试策略、断路器、降级处理

功能:
- 阶段290: 重试策略
- 阶段291: 断路器
- 阶段292: 降级处理
"""

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, Union


# ==================== 枚举定义 ====================

class RetryPolicy(Enum):
    """重试策略枚举"""
    FIXED = "fixed"  # 固定间隔
    EXPONENTIAL = "exponential"  # 指数退避
    LINEAR = "linear"  # 线性增长


class CircuitState(Enum):
    """断路器状态枚举"""
    CLOSED = "closed"  # 关闭状态（正常）
    OPEN = "open"  # 打开状态（熔断）
    HALF_OPEN = "half_open"  # 半开状态（试探）


class FallbackStrategy(Enum):
    """降级策略枚举"""
    RETURN_DEFAULT = "return_default"  # 返回默认值
    RETURN_CACHED = "return_cached"  # 返回缓存值
    CALL_FALLBACK = "call_fallback"  # 调用降级函数


# ==================== 数据类定义 ====================

@dataclass
class RetryConfig:
    """重试配置"""
    max_retries: int  # 最大重试次数
    policy: RetryPolicy  # 重试策略
    base_delay: float  # 基础延迟（秒）
    max_delay: float  # 最大延迟（秒）
    retry_on: Tuple[Type[Exception], ...]  # 触发重试的异常类型


@dataclass
class CircuitBreaker:
    """断路器数据结构"""
    name: str  # 断路器名称
    state: CircuitState  # 当前状态
    failure_count: int  # 失败计数
    success_count: int  # 成功计数
    failure_threshold: int  # 失败阈值
    success_threshold: int  # 成功阈值（半开状态下需要连续成功次数）
    timeout: float  # 超时时间（秒）
    last_failure_time: Optional[datetime] = None  # 最后一次失败时间


@dataclass
class FallbackConfig:
    """降级配置"""
    strategy: FallbackStrategy  # 降级策略
    default_value: Any = None  # 默认值
    fallback_func: Optional[Callable] = None  # 降级函数
    cache_key: Optional[str] = None  # 缓存键


# ==================== FaultTolerance 类 ====================

class FaultTolerance:
    """
    容错处理器
    
    提供重试策略、断路器和降级处理功能
    """
    
    _instance: Optional['FaultTolerance'] = None
    _lock: threading.RLock = threading.RLock()
    
    def __new__(cls) -> 'FaultTolerance':
        """单例模式实现"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        """初始化容错处理器"""
        with self._lock:
            if self._initialized:
                return
            self._initialized = True
            
            # 重试配置
            self._retry_configs: Dict[str, RetryConfig] = {}
            
            # 断路器
            self._circuit_breakers: Dict[str, CircuitBreaker] = {}
            
            # 降级配置
            self._fallback_configs: Dict[str, FallbackConfig] = {}
            
            # 结果缓存
            self._result_cache: Dict[str, Tuple[Any, datetime]] = {}
            
            # 缓存过期时间（秒）
            self._cache_ttl: float = 300.0  # 默认5分钟
            
            # 内部锁
            self._internal_lock = threading.RLock()
    
    # ==================== 阶段290: 重试策略 ====================
    
    def configure_retry(self, operation_name: str, config: RetryConfig) -> None:
        """
        配置重试策略
        
        Args:
            operation_name: 操作名称
            config: 重试配置
        """
        with self._internal_lock:
            self._retry_configs[operation_name] = config
    
    def execute_with_retry(
        self,
        operation_name: str,
        func: Callable,
        args: Tuple = (),
        kwargs: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        使用重试策略执行操作
        
        Args:
            operation_name: 操作名称
            func: 要执行的函数
            args: 位置参数
            kwargs: 关键字参数
            
        Returns:
            Any: 函数执行结果
            
        Raises:
            Exception: 重试耗尽后抛出最后一次异常
        """
        kwargs = kwargs or {}
        config = self._retry_configs.get(operation_name)
        
        if config is None:
            # 没有配置重试，直接执行
            return func(*args, **kwargs)
        
        last_error = None
        for retry_count in range(config.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                
                # 检查是否应该重试
                if retry_count < config.max_retries and self._should_retry(e, config):
                    delay = self._calculate_delay(retry_count, config)
                    time.sleep(delay)
                else:
                    break
        
        raise last_error
    
    def _calculate_delay(self, retry_count: int, config: RetryConfig) -> float:
        """
        计算重试延迟
        
        Args:
            retry_count: 当前重试次数
            config: 重试配置
            
        Returns:
            float: 延迟时间（秒）
        """
        if config.policy == RetryPolicy.FIXED:
            delay = config.base_delay
        
        elif config.policy == RetryPolicy.EXPONENTIAL:
            delay = config.base_delay * (2 ** retry_count)
        
        elif config.policy == RetryPolicy.LINEAR:
            delay = config.base_delay * (retry_count + 1)
        
        else:
            delay = config.base_delay
        
        # 限制最大延迟
        return min(delay, config.max_delay)
    
    def _should_retry(self, error: Exception, config: RetryConfig) -> bool:
        """
        判断是否应该重试
        
        Args:
            error: 发生的异常
            config: 重试配置
            
        Returns:
            bool: 是否应该重试
        """
        if not config.retry_on:
            return True
        
        return isinstance(error, config.retry_on)
    
    # ==================== 阶段291: 断路器 ====================
    
    def configure_circuit(
        self,
        name: str,
        failure_threshold: int = 5,
        success_threshold: int = 3,
        timeout: float = 60.0
    ) -> None:
        """
        配置断路器
        
        Args:
            name: 断路器名称
            failure_threshold: 失败阈值
            success_threshold: 成功阈值
            timeout: 超时时间（秒）
        """
        with self._internal_lock:
            circuit = CircuitBreaker(
                name=name,
                state=CircuitState.CLOSED,
                failure_count=0,
                success_count=0,
                failure_threshold=failure_threshold,
                success_threshold=success_threshold,
                timeout=timeout,
                last_failure_time=None
            )
            self._circuit_breakers[name] = circuit
    
    def execute_with_circuit(
        self,
        name: str,
        func: Callable,
        args: Tuple = (),
        kwargs: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        使用断路器执行操作
        
        Args:
            name: 断路器名称
            func: 要执行的函数
            args: 位置参数
            kwargs: 关键字参数
            
        Returns:
            Any: 函数执行结果
            
        Raises:
            Exception: 断路器打开时抛出CircuitOpenError
        """
        kwargs = kwargs or {}
        
        with self._internal_lock:
            if name not in self._circuit_breakers:
                # 自动创建默认配置的断路器
                self.configure_circuit(name)
            
            circuit = self._circuit_breakers[name]
            
            # 检查断路器状态
            if self._is_circuit_open(name):
                raise CircuitOpenError(f"Circuit '{name}' is open")
        
        try:
            result = func(*args, **kwargs)
            self._record_success(name)
            return result
        except Exception as e:
            self._record_failure(name)
            raise e
    
    def _is_circuit_open(self, name: str) -> bool:
        """
        检查断路器是否打开
        
        Args:
            name: 断路器名称
            
        Returns:
            bool: 断路器是否打开
        """
        circuit = self._circuit_breakers.get(name)
        if circuit is None:
            return False
        
        if circuit.state == CircuitState.OPEN:
            # 检查是否应该转为半开状态
            if circuit.last_failure_time:
                elapsed = (datetime.now() - circuit.last_failure_time).total_seconds()
                if elapsed >= circuit.timeout:
                    self._transition_state(name, CircuitState.HALF_OPEN)
                    return False
            return True
        
        return False
    
    def _record_success(self, name: str) -> None:
        """
        记录成功
        
        Args:
            name: 断路器名称
        """
        with self._internal_lock:
            circuit = self._circuit_breakers.get(name)
            if circuit is None:
                return
            
            circuit.success_count += 1
            circuit.failure_count = 0  # 重置失败计数
            
            if circuit.state == CircuitState.HALF_OPEN:
                if circuit.success_count >= circuit.success_threshold:
                    self._transition_state(name, CircuitState.CLOSED)
    
    def _record_failure(self, name: str) -> None:
        """
        记录失败
        
        Args:
            name: 断路器名称
        """
        with self._internal_lock:
            circuit = self._circuit_breakers.get(name)
            if circuit is None:
                return
            
            circuit.failure_count += 1
            circuit.success_count = 0  # 重置成功计数
            circuit.last_failure_time = datetime.now()
            
            if circuit.state == CircuitState.HALF_OPEN:
                # 半开状态下任何失败都转为打开
                self._transition_state(name, CircuitState.OPEN)
            elif circuit.state == CircuitState.CLOSED:
                if circuit.failure_count >= circuit.failure_threshold:
                    self._transition_state(name, CircuitState.OPEN)
    
    def _transition_state(self, name: str, new_state: CircuitState) -> None:
        """
        转换断路器状态
        
        Args:
            name: 断路器名称
            new_state: 新状态
        """
        circuit = self._circuit_breakers.get(name)
        if circuit is None:
            return
        
        old_state = circuit.state
        circuit.state = new_state
        
        # 状态转换时重置计数器
        if new_state == CircuitState.CLOSED:
            circuit.failure_count = 0
            circuit.success_count = 0
        elif new_state == CircuitState.HALF_OPEN:
            circuit.success_count = 0
    
    def get_circuit_state(self, name: str) -> Optional[CircuitState]:
        """获取断路器状态"""
        with self._internal_lock:
            circuit = self._circuit_breakers.get(name)
            return circuit.state if circuit else None
    
    # ==================== 阶段292: 降级处理 ====================
    
    def configure_fallback(self, operation_name: str, config: FallbackConfig) -> None:
        """
        配置降级策略
        
        Args:
            operation_name: 操作名称
            config: 降级配置
        """
        with self._internal_lock:
            self._fallback_configs[operation_name] = config
    
    def execute_with_fallback(
        self,
        operation_name: str,
        func: Callable,
        args: Tuple = (),
        kwargs: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        使用降级策略执行操作
        
        Args:
            operation_name: 操作名称
            func: 要执行的函数
            args: 位置参数
            kwargs: 关键字参数
            
        Returns:
            Any: 函数执行结果或降级结果
        """
        kwargs = kwargs or {}
        config = self._fallback_configs.get(operation_name)
        
        try:
            result = func(*args, **kwargs)
            
            # 成功时缓存结果
            if config and config.cache_key:
                self._store_cache(config.cache_key, result)
            
            return result
        
        except Exception as e:
            if config is None:
                raise e
            
            return self._apply_fallback(config, e)
    
    def _apply_fallback(self, config: FallbackConfig, error: Exception) -> Any:
        """
        应用降级策略
        
        Args:
            config: 降级配置
            error: 发生的异常
            
        Returns:
            Any: 降级结果
        """
        if config.strategy == FallbackStrategy.RETURN_DEFAULT:
            return config.default_value
        
        elif config.strategy == FallbackStrategy.RETURN_CACHED:
            if config.cache_key:
                cached = self._get_cached_result(config.cache_key)
                if cached is not None:
                    return cached
            return config.default_value
        
        elif config.strategy == FallbackStrategy.CALL_FALLBACK:
            return self._call_fallback(config, error)
        
        return config.default_value
    
    def _get_cached_result(self, cache_key: str) -> Optional[Any]:
        """
        获取缓存结果
        
        Args:
            cache_key: 缓存键
            
        Returns:
            Optional[Any]: 缓存结果，不存在或过期返回None
        """
        with self._internal_lock:
            cached = self._result_cache.get(cache_key)
            
            if cached is None:
                return None
            
            result, timestamp = cached
            elapsed = (datetime.now() - timestamp).total_seconds()
            
            if elapsed > self._cache_ttl:
                del self._result_cache[cache_key]
                return None
            
            return result
    
    def _store_cache(self, cache_key: str, result: Any) -> None:
        """
        存储缓存结果
        
        Args:
            cache_key: 缓存键
            result: 结果值
        """
        with self._internal_lock:
            self._result_cache[cache_key] = (result, datetime.now())
    
    def _call_fallback(self, config: FallbackConfig, error: Exception) -> Any:
        """
        调用降级函数
        
        Args:
            config: 降级配置
            error: 发生的异常
            
        Returns:
            Any: 降级函数返回结果
        """
        if config.fallback_func is None:
            return config.default_value
        
        try:
            return config.fallback_func(error)
        except Exception:
            return config.default_value
    
    # ==================== 辅助方法 ====================
    
    def set_cache_ttl(self, ttl: float) -> None:
        """设置缓存过期时间"""
        with self._internal_lock:
            self._cache_ttl = ttl
    
    def clear_cache(self, cache_key: Optional[str] = None) -> None:
        """清除缓存"""
        with self._internal_lock:
            if cache_key:
                self._result_cache.pop(cache_key, None)
            else:
                self._result_cache.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._internal_lock:
            return {
                "retry_configs": len(self._retry_configs),
                "circuit_breakers": {
                    name: {
                        "state": circuit.state.value,
                        "failure_count": circuit.failure_count,
                        "success_count": circuit.success_count
                    }
                    for name, circuit in self._circuit_breakers.items()
                },
                "fallback_configs": len(self._fallback_configs),
                "cached_results": len(self._result_cache)
            }
    
    # ==================== 组合方法 ====================
    
    def execute_resilient(
        self,
        operation_name: str,
        func: Callable,
        args: Tuple = (),
        kwargs: Optional[Dict[str, Any]] = None,
        use_retry: bool = True,
        use_circuit: bool = True,
        use_fallback: bool = True
    ) -> Any:
        """
        弹性执行（组合重试、断路器、降级）
        
        Args:
            operation_name: 操作名称
            func: 要执行的函数
            args: 位置参数
            kwargs: 关键字参数
            use_retry: 是否使用重试
            use_circuit: 是否使用断路器
            use_fallback: 是否使用降级
            
        Returns:
            Any: 执行结果
        """
        kwargs = kwargs or {}
        
        def wrapped_func(*a, **kw):
            if use_retry:
                return self.execute_with_retry(operation_name, func, a, kw)
            return func(*a, **kw)
        
        try:
            if use_circuit:
                return self.execute_with_circuit(operation_name, wrapped_func, args, kwargs)
            return wrapped_func(*args, **kwargs)
        except Exception as e:
            if use_fallback:
                config = self._fallback_configs.get(operation_name)
                if config:
                    return self._apply_fallback(config, e)
            raise e


# ==================== 自定义异常 ====================

class CircuitOpenError(Exception):
    """断路器打开异常"""
    pass


# ==================== 全局单例获取函数 ====================

def get_fault_tolerance() -> FaultTolerance:
    """
    获取FaultTolerance全局单例
    
    Returns:
        FaultTolerance: 容错处理器实例
    """
    return FaultTolerance()
