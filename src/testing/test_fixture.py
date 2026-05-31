"""
测试夹具模块 (阶段370)

提供测试夹具管理、setup/teardown支持和数据驱动测试功能。
线程安全设计，使用 threading.RLock 保证并发安全。
确定性规则设计，无模型依赖，无循环依赖。
"""

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple


# ============================================================================
# 枚举定义
# ============================================================================


class FixtureScope(Enum):
    """夹具作用域枚举"""
    FUNCTION = "function"    # 每个测试函数
    CLASS = "class"          # 每个测试类
    MODULE = "module"        # 每个模块
    SESSION = "session"      # 整个会话


class FixturePhase(Enum):
    """夹具阶段枚举"""
    SETUP = "setup"
    TEARDOWN = "teardown"


# ============================================================================
# 数据类定义
# ============================================================================


@dataclass
class Fixture:
    """夹具数据类"""
    name: str
    func: Callable
    scope: FixtureScope = FixtureScope.FUNCTION
    autouse: bool = False
    params: List[Any] = field(default_factory=list)
    ids: List[str] = field(default_factory=list)


@dataclass
class FixtureValue:
    """夹具值数据类"""
    name: str
    value: Any
    scope: FixtureScope
    created_at: float = field(default_factory=time.time)


@dataclass
class TestData:
    """测试数据数据类"""
    id: str
    args: Tuple
    kwargs: Dict[str, Any]
    description: str = ""


# ============================================================================
# 夹具管理器
# ============================================================================


class FixtureManager:
    """
    夹具管理器
    
    管理测试夹具的注册、创建和清理。
    支持多种作用域和自动使用夹具。
    线程安全，使用 RLock 保证并发访问安全。
    """
    
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._fixtures: Dict[str, Fixture] = {}
        self._cache: Dict[str, FixtureValue] = {}
        self._stack: List[str] = []  # 用于追踪需要清理的夹具
    
    def register(self, name: str, func: Callable,
                 scope: FixtureScope = FixtureScope.FUNCTION,
                 autouse: bool = False,
                 params: Optional[List[Any]] = None) -> None:
        """
        注册夹具
        
        Args:
            name: 夹具名称
            func: 夹具函数
            scope: 作用域
            autouse: 是否自动使用
            params: 参数化数据
        """
        with self._lock:
            fixture = Fixture(
                name=name,
                func=func,
                scope=scope,
                autouse=autouse,
                params=params or [],
            )
            self._fixtures[name] = fixture
    
    def get_fixture(self, name: str) -> Optional[Fixture]:
        """获取夹具定义"""
        with self._lock:
            return self._fixtures.get(name)
    
    def get_value(self, name: str) -> Any:
        """
        获取夹具值
        
        Args:
            name: 夹具名称
            
        Returns:
            夹具值
        """
        with self._lock:
            # 检查缓存
            if name in self._cache:
                return self._cache[name].value
            
            # 获取夹具定义
            fixture = self._fixtures.get(name)
            if fixture is None:
                raise ValueError(f"Fixture '{name}' not found")
            
            # 调用夹具函数
            value = fixture.func()
            
            # 缓存值
            fixture_value = FixtureValue(
                name=name,
                value=value,
                scope=fixture.scope,
            )
            self._cache[name] = fixture_value
            
            # 追踪需要清理的夹具
            if fixture.scope != FixtureScope.FUNCTION:
                self._stack.append(name)
            
            return value
    
    def cleanup(self, scope: Optional[FixtureScope] = None) -> int:
        """
        清理夹具
        
        Args:
            scope: 清理指定作用域的夹具，None表示清理所有
            
        Returns:
            清理的夹具数量
        """
        with self._lock:
            count = 0
            
            if scope is None:
                # 清理所有
                count = len(self._cache)
                self._cache.clear()
                self._stack.clear()
            else:
                # 清理指定作用域
                to_remove = []
                for name, value in self._cache.items():
                    if value.scope == scope:
                        to_remove.append(name)
                        count += 1
                
                for name in to_remove:
                    del self._cache[name]
                    if name in self._stack:
                        self._stack.remove(name)
            
            return count
    
    def get_autouse_fixtures(self) -> List[str]:
        """获取自动使用的夹具列表"""
        with self._lock:
            return [
                name for name, fixture in self._fixtures.items()
                if fixture.autouse
            ]
    
    def get_fixtures_by_scope(self, scope: FixtureScope) -> List[str]:
        """获取指定作用域的夹具列表"""
        with self._lock:
            return [
                name for name, fixture in self._fixtures.items()
                if fixture.scope == scope
            ]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            scope_counts = {}
            for fixture in self._fixtures.values():
                scope = fixture.scope.value
                scope_counts[scope] = scope_counts.get(scope, 0) + 1
            
            return {
                "total_fixtures": len(self._fixtures),
                "cached_values": len(self._cache),
                "by_scope": scope_counts,
                "autouse_count": len(self.get_autouse_fixtures()),
            }


# ============================================================================
# 数据驱动测试
# ============================================================================


class DataProvider:
    """
    数据提供器
    
    为数据驱动测试提供测试数据。
    """
    
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._datasets: Dict[str, List[TestData]] = {}
    
    def register(self, name: str, data: List[Tuple]) -> None:
        """
        注册数据集
        
        Args:
            name: 数据集名称
            data: 参数元组列表
        """
        with self._lock:
            test_data = [
                TestData(
                    id=f"{name}_{i}",
                    args=item if isinstance(item, tuple) else (item,),
                    kwargs={},
                )
                for i, item in enumerate(data)
            ]
            self._datasets[name] = test_data
    
    def register_dict(self, name: str, data: List[Dict[str, Any]]) -> None:
        """注册字典数据集"""
        with self._lock:
            test_data = [
                TestData(
                    id=f"{name}_{i}",
                    args=(),
                    kwargs=item,
                )
                for i, item in enumerate(data)
            ]
            self._datasets[name] = test_data
    
    def get(self, name: str) -> List[TestData]:
        """获取数据集"""
        with self._lock:
            return list(self._datasets.get(name, []))
    
    def parametrize(self, params: List[Any], ids: Optional[List[str]] = None) -> List[TestData]:
        """
        参数化
        
        Args:
            params: 参数列表
            ids: 测试ID列表
            
        Returns:
            测试数据列表
        """
        test_data = []
        for i, param in enumerate(params):
            test_id = ids[i] if ids and i < len(ids) else f"param_{i}"
            test_data.append(TestData(
                id=test_id,
                args=param if isinstance(param, tuple) else (param,),
                kwargs={},
            ))
        return test_data
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                "total_datasets": len(self._datasets),
                "datasets": {
                    name: len(data) for name, data in self._datasets.items()
                },
            }


# ============================================================================
# 夹具装饰器
# ============================================================================


def fixture(func: Optional[Callable] = None, *,
            scope: FixtureScope = FixtureScope.FUNCTION,
            autouse: bool = False,
            params: Optional[List[Any]] = None) -> Callable:
    """
    夹具装饰器
    
    用法:
        @fixture
        def my_fixture():
            return "value"
        
        @fixture(scope=FixtureScope.CLASS)
        def class_fixture():
            return {}
    """
    def decorator(f: Callable) -> Callable:
        f._fixture_scope = scope
        f._fixture_autouse = autouse
        f._fixture_params = params or []
        return f
    
    if func is not None:
        return decorator(func)
    return decorator


def parametrize(argnames: str, argvalues: List[Any],
                ids: Optional[List[str]] = None) -> Callable:
    """
    参数化装饰器
    
    用法:
        @parametrize("a,b", [(1, 2), (3, 4)])
        def test_add(a, b):
            ...
    """
    def decorator(func: Callable) -> Callable:
        func._parametrize_argnames = argnames
        func._parametrize_argvalues = argvalues
        func._parametrize_ids = ids
        return func
    return decorator


# ============================================================================
# 上下文管理器
# ============================================================================


class FixtureContext:
    """
    夹具上下文管理器
    
    支持 with 语句自动清理。
    """
    
    def __init__(self, manager: FixtureManager, fixture_names: List[str]) -> None:
        self._manager = manager
        self._fixture_names = fixture_names
        self._values: Dict[str, Any] = {}
    
    def __enter__(self) -> "FixtureContext":
        for name in self._fixture_names:
            self._values[name] = self._manager.get_value(name)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self._manager.cleanup(FixtureScope.FUNCTION)
        return False
    
    def get(self, name: str) -> Any:
        """获取夹具值"""
        return self._values.get(name)
    
    def __getitem__(self, name: str) -> Any:
        """通过索引获取夹具值"""
        return self._values[name]


# ============================================================================
# 全局单例
# ============================================================================

_fixture_manager_instance: Optional[FixtureManager] = None
_fixture_manager_lock = threading.Lock()

_data_provider_instance: Optional[DataProvider] = None
_data_provider_lock = threading.Lock()


def get_fixture_manager() -> FixtureManager:
    """获取夹具管理器全局单例"""
    global _fixture_manager_instance
    with _fixture_manager_lock:
        if _fixture_manager_instance is None:
            _fixture_manager_instance = FixtureManager()
        return _fixture_manager_instance


def get_data_provider() -> DataProvider:
    """获取数据提供器全局单例"""
    global _data_provider_instance
    with _data_provider_lock:
        if _data_provider_instance is None:
            _data_provider_instance = DataProvider()
        return _data_provider_instance
