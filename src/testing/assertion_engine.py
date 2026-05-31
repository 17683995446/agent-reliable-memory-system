"""
断言引擎模块 (阶段367)

提供丰富的断言方法和自定义断言支持。
线程安全设计，使用 threading.RLock 保证并发安全。
确定性规则设计，无模型依赖，无循环依赖。
"""

import difflib
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Pattern, Union
import re


# ============================================================================
# 枚举定义
# ============================================================================


class AssertionType(Enum):
    """断言类型枚举"""
    EQUAL = "equal"
    NOT_EQUAL = "not_equal"
    TRUE = "true"
    FALSE = "false"
    IS_NONE = "is_none"
    IS_NOT_NONE = "is_not_none"
    IN = "in"
    NOT_IN = "not_in"
    IS_INSTANCE = "is_instance"
    GREATER = "greater"
    LESS = "less"
    BETWEEN = "between"
    MATCHES = "matches"
    CONTAINS = "contains"
    RAISES = "raises"


# ============================================================================
# 数据类定义
# ============================================================================


@dataclass
class AssertionResult:
    """断言结果数据类"""
    passed: bool
    assertion_type: AssertionType
    message: str = ""
    expected: Any = None
    actual: Any = None
    diff: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class AssertionContext:
    """断言上下文数据类"""
    test_name: str = ""
    assertions: List[AssertionResult] = field(default_factory=list)
    passed_count: int = 0
    failed_count: int = 0


# ============================================================================
# 断言错误
# ============================================================================


class AssertionError(Exception):
    """断言错误"""
    
    def __init__(self, message: str, expected: Any = None, actual: Any = None):
        super().__init__(message)
        self.expected = expected
        self.actual = actual


# ============================================================================
# 断言引擎
# ============================================================================


class AssertionEngine:
    """
    断言引擎
    
    提供丰富的断言方法，支持自定义断言和详细错误信息。
    线程安全，使用 RLock 保证并发访问安全。
    """
    
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._custom_assertions: Dict[str, Callable] = {}
        self._context: AssertionContext = AssertionContext()
    
    def _record(self, result: AssertionResult) -> None:
        """记录断言结果"""
        with self._lock:
            self._context.assertions.append(result)
            if result.passed:
                self._context.passed_count += 1
            else:
                self._context.failed_count += 1
    
    def _generate_diff(self, expected: Any, actual: Any) -> Optional[str]:
        """生成差异对比"""
        if isinstance(expected, str) and isinstance(actual, str):
            diff = difflib.unified_diff(
                expected.splitlines(keepends=True),
                actual.splitlines(keepends=True),
                fromfile="expected",
                tofile="actual",
            )
            return "".join(diff)
        return None
    
    def equal(self, actual: Any, expected: Any, message: str = "") -> AssertionResult:
        """断言相等"""
        passed = actual == expected
        diff = self._generate_diff(expected, actual) if not passed else None
        
        result = AssertionResult(
            passed=passed,
            assertion_type=AssertionType.EQUAL,
            message=message or f"Expected {expected!r}, got {actual!r}",
            expected=expected,
            actual=actual,
            diff=diff,
        )
        self._record(result)
        
        if not passed:
            raise AssertionError(result.message, expected, actual)
        
        return result
    
    def not_equal(self, actual: Any, unexpected: Any, message: str = "") -> AssertionResult:
        """断言不相等"""
        passed = actual != unexpected
        
        result = AssertionResult(
            passed=passed,
            assertion_type=AssertionType.NOT_EQUAL,
            message=message or f"Expected not {unexpected!r}, got {actual!r}",
            expected=unexpected,
            actual=actual,
        )
        self._record(result)
        
        if not passed:
            raise AssertionError(result.message, unexpected, actual)
        
        return result
    
    def true(self, condition: bool, message: str = "") -> AssertionResult:
        """断言为真"""
        passed = condition is True
        
        result = AssertionResult(
            passed=passed,
            assertion_type=AssertionType.TRUE,
            message=message or f"Expected True, got {condition!r}",
            expected=True,
            actual=condition,
        )
        self._record(result)
        
        if not passed:
            raise AssertionError(result.message, True, condition)
        
        return result
    
    def false(self, condition: bool, message: str = "") -> AssertionResult:
        """断言为假"""
        passed = condition is False
        
        result = AssertionResult(
            passed=passed,
            assertion_type=AssertionType.FALSE,
            message=message or f"Expected False, got {condition!r}",
            expected=False,
            actual=condition,
        )
        self._record(result)
        
        if not passed:
            raise AssertionError(result.message, False, condition)
        
        return result
    
    def is_none(self, value: Any, message: str = "") -> AssertionResult:
        """断言为None"""
        passed = value is None
        
        result = AssertionResult(
            passed=passed,
            assertion_type=AssertionType.IS_NONE,
            message=message or f"Expected None, got {value!r}",
            expected=None,
            actual=value,
        )
        self._record(result)
        
        if not passed:
            raise AssertionError(result.message, None, value)
        
        return result
    
    def is_not_none(self, value: Any, message: str = "") -> AssertionResult:
        """断言不为None"""
        passed = value is not None
        
        result = AssertionResult(
            passed=passed,
            assertion_type=AssertionType.IS_NOT_NONE,
            message=message or "Expected not None",
            actual=value,
        )
        self._record(result)
        
        if not passed:
            raise AssertionError(result.message, "not None", value)
        
        return result
    
    def in_(self, member: Any, container: Any, message: str = "") -> AssertionResult:
        """断言成员在容器中"""
        passed = member in container
        
        result = AssertionResult(
            passed=passed,
            assertion_type=AssertionType.IN,
            message=message or f"{member!r} not in {container!r}",
            expected=container,
            actual=member,
        )
        self._record(result)
        
        if not passed:
            raise AssertionError(result.message, container, member)
        
        return result
    
    def not_in(self, member: Any, container: Any, message: str = "") -> AssertionResult:
        """断言成员不在容器中"""
        passed = member not in container
        
        result = AssertionResult(
            passed=passed,
            assertion_type=AssertionType.NOT_IN,
            message=message or f"{member!r} should not be in {container!r}",
            expected=container,
            actual=member,
        )
        self._record(result)
        
        if not passed:
            raise AssertionError(result.message, container, member)
        
        return result
    
    def is_instance(self, obj: Any, cls: type, message: str = "") -> AssertionResult:
        """断言是某类型的实例"""
        passed = isinstance(obj, cls)
        
        result = AssertionResult(
            passed=passed,
            assertion_type=AssertionType.IS_INSTANCE,
            message=message or f"Expected instance of {cls.__name__}, got {type(obj).__name__}",
            expected=cls,
            actual=type(obj),
        )
        self._record(result)
        
        if not passed:
            raise AssertionError(result.message, cls, type(obj))
        
        return result
    
    def greater(self, actual: Any, threshold: Any, message: str = "") -> AssertionResult:
        """断言大于"""
        passed = actual > threshold
        
        result = AssertionResult(
            passed=passed,
            assertion_type=AssertionType.GREATER,
            message=message or f"Expected > {threshold}, got {actual}",
            expected=threshold,
            actual=actual,
        )
        self._record(result)
        
        if not passed:
            raise AssertionError(result.message, threshold, actual)
        
        return result
    
    def less(self, actual: Any, threshold: Any, message: str = "") -> AssertionResult:
        """断言小于"""
        passed = actual < threshold
        
        result = AssertionResult(
            passed=passed,
            assertion_type=AssertionType.LESS,
            message=message or f"Expected < {threshold}, got {actual}",
            expected=threshold,
            actual=actual,
        )
        self._record(result)
        
        if not passed:
            raise AssertionError(result.message, threshold, actual)
        
        return result
    
    def between(self, actual: Any, low: Any, high: Any, message: str = "") -> AssertionResult:
        """断言在范围内"""
        passed = low <= actual <= high
        
        result = AssertionResult(
            passed=passed,
            assertion_type=AssertionType.BETWEEN,
            message=message or f"Expected between {low} and {high}, got {actual}",
            expected=(low, high),
            actual=actual,
        )
        self._record(result)
        
        if not passed:
            raise AssertionError(result.message, (low, high), actual)
        
        return result
    
    def matches(self, text: str, pattern: Union[str, Pattern], message: str = "") -> AssertionResult:
        """断言匹配正则表达式"""
        if isinstance(pattern, str):
            pattern = re.compile(pattern)
        
        passed = bool(pattern.search(text))
        
        result = AssertionResult(
            passed=passed,
            assertion_type=AssertionType.MATCHES,
            message=message or f"Text does not match pattern {pattern.pattern}",
            expected=pattern.pattern,
            actual=text,
        )
        self._record(result)
        
        if not passed:
            raise AssertionError(result.message, pattern.pattern, text)
        
        return result
    
    def contains(self, container: Any, member: Any, message: str = "") -> AssertionResult:
        """断言容器包含成员"""
        passed = member in container
        
        result = AssertionResult(
            passed=passed,
            assertion_type=AssertionType.CONTAINS,
            message=message or f"{container!r} does not contain {member!r}",
            expected=member,
            actual=container,
        )
        self._record(result)
        
        if not passed:
            raise AssertionError(result.message, member, container)
        
        return result
    
    def raises(self, exception_type: type, func: Callable, *args, **kwargs) -> AssertionResult:
        """断言抛出异常"""
        try:
            func(*args, **kwargs)
            passed = False
            message = f"Expected {exception_type.__name__} to be raised"
        except exception_type:
            passed = True
            message = f"{exception_type.__name__} was raised as expected"
        except Exception as e:
            passed = False
            message = f"Expected {exception_type.__name__}, got {type(e).__name__}"
        
        result = AssertionResult(
            passed=passed,
            assertion_type=AssertionType.RAISES,
            message=message,
            expected=exception_type,
        )
        self._record(result)
        
        if not passed:
            raise AssertionError(message, exception_type, None)
        
        return result
    
    def register_custom(self, name: str, assertion_func: Callable) -> None:
        """注册自定义断言"""
        with self._lock:
            self._custom_assertions[name] = assertion_func
    
    def custom(self, name: str, *args, **kwargs) -> AssertionResult:
        """执行自定义断言"""
        with self._lock:
            assertion_func = self._custom_assertions.get(name)
        
        if assertion_func is None:
            raise ValueError(f"Custom assertion '{name}' not found")
        
        return assertion_func(*args, **kwargs)
    
    def get_context(self) -> AssertionContext:
        """获取断言上下文"""
        with self._lock:
            return self._context
    
    def reset_context(self) -> None:
        """重置断言上下文"""
        with self._lock:
            self._context = AssertionContext()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                "total_assertions": len(self._context.assertions),
                "passed": self._context.passed_count,
                "failed": self._context.failed_count,
                "custom_assertions": list(self._custom_assertions.keys()),
            }


# ============================================================================
# 全局单例
# ============================================================================

_assertion_engine_instance: Optional[AssertionEngine] = None
_assertion_engine_lock = threading.Lock()


def get_assertion_engine() -> AssertionEngine:
    """获取断言引擎全局单例"""
    global _assertion_engine_instance
    with _assertion_engine_lock:
        if _assertion_engine_instance is None:
            _assertion_engine_instance = AssertionEngine()
        return _assertion_engine_instance
