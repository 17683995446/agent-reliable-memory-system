"""
模拟工厂模块 (阶段368)

提供对象模拟、行为验证和调用追踪功能。
线程安全设计，使用 threading.RLock 保证并发安全。
确定性规则设计，无模型依赖，无循环依赖。
"""

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


# ============================================================================
# 枚举定义
# ============================================================================


class CallType(Enum):
    """调用类型枚举"""
    METHOD = "method"
    PROPERTY = "property"
    ATTRIBUTE = "attribute"


class VerificationMode(Enum):
    """验证模式枚举"""
    NEVER = "never"
    ONCE = "once"
    TIMES = "times"
    AT_LEAST = "at_least"
    AT_MOST = "at_most"


# ============================================================================
# 数据类定义
# ============================================================================


@dataclass
class CallRecord:
    """调用记录数据类"""
    name: str
    args: Tuple
    kwargs: Dict[str, Any]
    call_type: CallType = CallType.METHOD
    result: Any = None
    exception: Optional[Exception] = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class MockConfig:
    """模拟配置数据类"""
    spec: Optional[type] = None
    return_value: Any = None
    side_effect: Optional[Callable] = None
    name: str = ""


# ============================================================================
# 模拟对象
# ============================================================================


class MockObject:
    """
    模拟对象
    
    记录所有属性访问和方法调用，支持行为验证。
    """
    
    def __init__(self, config: Optional[MockConfig] = None) -> None:
        self._lock = threading.RLock()
        self._config = config or MockConfig()
        self._call_records: List[CallRecord] = []
        self._return_values: Dict[str, Any] = {}
        self._side_effects: Dict[str, Callable] = {}
        self._attributes: Dict[str, Any] = {}
        self._methods: Dict[str, Callable] = {}
    
    def __call__(self, *args, **kwargs) -> Any:
        """支持作为可调用对象"""
        record = CallRecord(
            name="__call__",
            args=args,
            kwargs=kwargs,
            call_type=CallType.METHOD,
        )
        
        try:
            if self._config.side_effect:
                result = self._config.side_effect(*args, **kwargs)
            else:
                result = self._config.return_value
            
            record.result = result
            with self._lock:
                self._call_records.append(record)
            return result
        
        except Exception as e:
            record.exception = e
            with self._lock:
                self._call_records.append(record)
            raise
    
    def __getattr__(self, name: str) -> Any:
        """属性访问"""
        if name.startswith("_"):
            return object.__getattribute__(self, name)
        
        with self._lock:
            if name in self._attributes:
                return self._attributes[name]
        
        # 返回一个新的 MockMethod
        def mock_method(*args, **kwargs) -> Any:
            record = CallRecord(
                name=name,
                args=args,
                kwargs=kwargs,
                call_type=CallType.METHOD,
            )
            
            try:
                with self._lock:
                    if name in self._side_effects:
                        result = self._side_effects[name](*args, **kwargs)
                    elif name in self._return_values:
                        result = self._return_values[name]
                    else:
                        result = MockObject(MockConfig(name=f"{self._config.name}.{name}"))
                
                record.result = result
                with self._lock:
                    self._call_records.append(record)
                return result
            
            except Exception as e:
                record.exception = e
                with self._lock:
                    self._call_records.append(record)
                raise
        
        return mock_method
    
    def __setattr__(self, name: str, value: Any) -> None:
        """属性设置"""
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        else:
            with self._lock:
                self._attributes[name] = value
    
    def set_return_value(self, method: str, value: Any) -> None:
        """设置方法返回值"""
        with self._lock:
            self._return_values[method] = value
    
    def set_side_effect(self, method: str, effect: Callable) -> None:
        """设置方法副作用"""
        with self._lock:
            self._side_effects[method] = effect
    
    def get_calls(self, name: Optional[str] = None) -> List[CallRecord]:
        """获取调用记录"""
        with self._lock:
            if name is None:
                return list(self._call_records)
            return [r for r in self._call_records if r.name == name]
    
    def call_count(self, name: str) -> int:
        """获取调用次数"""
        return len(self.get_calls(name))
    
    def called(self) -> bool:
        """是否被调用过"""
        with self._lock:
            return len(self._call_records) > 0
    
    def called_with(self, name: str, *args, **kwargs) -> bool:
        """是否以指定参数被调用"""
        calls = self.get_calls(name)
        for call in calls:
            if call.args == args and call.kwargs == kwargs:
                return True
        return False
    
    def reset(self) -> None:
        """重置模拟对象"""
        with self._lock:
            self._call_records.clear()
            self._return_values.clear()
            self._side_effects.clear()
            self._attributes.clear()


# ============================================================================
# 模拟工厂
# ============================================================================


class MockFactory:
    """
    模拟工厂
    
    创建和管理模拟对象，提供验证方法。
    线程安全，使用 RLock 保证并发访问安全。
    """
    
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._mocks: Dict[str, MockObject] = {}
        self._id_counter: int = 0
    
    def create(self, name: Optional[str] = None, spec: Optional[type] = None,
               return_value: Any = None) -> MockObject:
        """
        创建模拟对象
        
        Args:
            name: 模拟对象名称
            spec: 规范类
            return_value: 默认返回值
            
        Returns:
            模拟对象
        """
        with self._lock:
            self._id_counter += 1
            mock_name = name or f"mock_{self._id_counter}"
            
            config = MockConfig(
                spec=spec,
                return_value=return_value,
                name=mock_name,
            )
            
            mock = MockObject(config)
            self._mocks[mock_name] = mock
            return mock
    
    def create_callable(self, return_value: Any = None,
                        side_effect: Optional[Callable] = None) -> MockObject:
        """创建可调用的模拟对象"""
        config = MockConfig(
            return_value=return_value,
            side_effect=side_effect,
        )
        return MockObject(config)
    
    def get(self, name: str) -> Optional[MockObject]:
        """获取模拟对象"""
        with self._lock:
            return self._mocks.get(name)
    
    def remove(self, name: str) -> bool:
        """移除模拟对象"""
        with self._lock:
            if name in self._mocks:
                del self._mocks[name]
                return True
            return False
    
    def verify(self, mock: MockObject, method: str,
               mode: VerificationMode = VerificationMode.ONCE,
               times: int = 1) -> bool:
        """
        验证调用
        
        Args:
            mock: 模拟对象
            method: 方法名
            mode: 验证模式
            times: 期望次数
            
        Returns:
            是否验证通过
        """
        count = mock.call_count(method)
        
        if mode == VerificationMode.NEVER:
            return count == 0
        elif mode == VerificationMode.ONCE:
            return count == 1
        elif mode == VerificationMode.TIMES:
            return count == times
        elif mode == VerificationMode.AT_LEAST:
            return count >= times
        elif mode == VerificationMode.AT_MOST:
            return count <= times
        
        return False
    
    def verify_called(self, mock: MockObject, method: str) -> bool:
        """验证方法被调用"""
        return mock.call_count(method) > 0
    
    def verify_called_once(self, mock: MockObject, method: str) -> bool:
        """验证方法被调用一次"""
        return mock.call_count(method) == 1
    
    def verify_called_with(self, mock: MockObject, method: str,
                           *args, **kwargs) -> bool:
        """验证方法以指定参数被调用"""
        return mock.called_with(method, *args, **kwargs)
    
    def verify_never(self, mock: MockObject, method: str) -> bool:
        """验证方法从未被调用"""
        return mock.call_count(method) == 0
    
    def reset_all(self) -> None:
        """重置所有模拟对象"""
        with self._lock:
            for mock in self._mocks.values():
                mock.reset()
    
    def clear(self) -> None:
        """清空所有模拟对象"""
        with self._lock:
            self._mocks.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            mock_stats = {}
            for name, mock in self._mocks.items():
                mock_stats[name] = {
                    "call_count": len(mock._call_records),
                    "attributes": list(mock._attributes.keys()),
                }
            
            return {
                "total_mocks": len(self._mocks),
                "mocks": mock_stats,
            }


# ============================================================================
# 便捷函数
# ============================================================================


def Mock(return_value: Any = None, spec: Optional[type] = None) -> MockObject:
    """创建模拟对象的便捷函数"""
    config = MockConfig(spec=spec, return_value=return_value)
    return MockObject(config)


# ============================================================================
# 全局单例
# ============================================================================

_mock_factory_instance: Optional[MockFactory] = None
_mock_factory_lock = threading.Lock()


def get_mock_factory() -> MockFactory:
    """获取模拟工厂全局单例"""
    global _mock_factory_instance
    with _mock_factory_lock:
        if _mock_factory_instance is None:
            _mock_factory_instance = MockFactory()
        return _mock_factory_instance
