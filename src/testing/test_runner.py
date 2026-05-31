"""
测试运行器模块 (阶段366)

提供测试发现、执行、并行运行和结果收集功能。
线程安全设计，使用 threading.RLock 保证并发安全。
确定性规则设计，无模型依赖，无循环依赖。
"""

import inspect
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type


# ============================================================================
# 枚举定义
# ============================================================================


class TestStatus(Enum):
    """测试状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


class RunMode(Enum):
    """运行模式枚举"""
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    ISOLATED = "isolated"


# ============================================================================
# 数据类定义
# ============================================================================


@dataclass
class TestResult:
    """测试结果数据类"""
    test_id: str
    test_name: str
    status: TestStatus
    duration: float = 0.0
    message: Optional[str] = None
    traceback: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TestSuite:
    """测试套件数据类"""
    name: str
    tests: List[Callable] = field(default_factory=list)
    setup: Optional[Callable] = None
    teardown: Optional[Callable] = None
    setup_class: Optional[Callable] = None
    teardown_class: Optional[Callable] = None


@dataclass
class RunSummary:
    """运行摘要数据类"""
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    error: int = 0
    duration: float = 0.0
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None

    @property
    def success_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.passed / self.total


# ============================================================================
# 测试运行器
# ============================================================================


class TestRunner:
    """
    测试运行器

    发现并执行测试用例，收集结果并生成摘要。
    支持顺序执行、并行执行和隔离执行模式。
    线程安全，使用 RLock 保证并发访问安全。
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._test_registry: Dict[str, Callable] = {}
        self._suites: Dict[str, TestSuite] = {}
        self._results: List[TestResult] = []
        self._id_counter: int = 0
        self._hooks: Dict[str, List[Callable]] = {
            "before_all": [],
            "after_all": [],
            "before_each": [],
            "after_each": [],
        }

    def _generate_id(self) -> str:
        """生成唯一测试ID"""
        with self._lock:
            self._id_counter += 1
            return f"test_{self._id_counter}_{uuid.uuid4().hex[:8]}"

    def register_test(self, name: str, test_func: Callable) -> str:
        """
        注册测试用例

        Args:
            name: 测试名称
            test_func: 测试函数

        Returns:
            测试ID
        """
        with self._lock:
            test_id = self._generate_id()
            self._test_registry[test_id] = test_func
            return test_id

    def register_suite(self, suite: TestSuite) -> None:
        """注册测试套件"""
        with self._lock:
            self._suites[suite.name] = suite

    def discover_tests(self, module_or_class: Any) -> List[str]:
        """
        发现测试用例

        Args:
            module_or_class: 模块或类对象

        Returns:
            发现的测试ID列表
        """
        discovered = []

        if inspect.isclass(module_or_class):
            # 从类中发现测试方法
            for name, method in inspect.getmembers(module_or_class, predicate=inspect.isfunction):
                if name.startswith("test_"):
                    test_id = self.register_test(
                        f"{module_or_class.__name__}.{name}",
                        method
                    )
                    discovered.append(test_id)
        elif inspect.ismodule(module_or_class):
            # 从模块中发现测试函数和类
            for name, obj in inspect.getmembers(module_or_class):
                if name.startswith("test_") and callable(obj):
                    test_id = self.register_test(name, obj)
                    discovered.append(test_id)
                elif inspect.isclass(obj) and name.startswith("Test"):
                    discovered.extend(self.discover_tests(obj))

        return discovered

    def add_hook(self, hook_type: str, hook_func: Callable) -> None:
        """
        添加钩子函数

        Args:
            hook_type: 钩子类型 (before_all, after_all, before_each, after_each)
            hook_func: 钩子函数
        """
        with self._lock:
            if hook_type in self._hooks:
                self._hooks[hook_type].append(hook_func)

    def _run_hooks(self, hook_type: str) -> bool:
        """运行指定类型的钩子"""
        hooks = self._hooks.get(hook_type, [])
        for hook in hooks:
            try:
                hook()
            except Exception:
                return False
        return True

    def run_test(self, test_id: str, test_func: Callable) -> TestResult:
        """
        执行单个测试

        Args:
            test_id: 测试ID
            test_func: 测试函数

        Returns:
            测试结果
        """
        result = TestResult(
            test_id=test_id,
            test_name=getattr(test_func, "__name__", str(test_func)),
            status=TestStatus.RUNNING,
        )

        # 运行 before_each 钩子
        if not self._run_hooks("before_each"):
            result.status = TestStatus.ERROR
            result.message = "before_each hook failed"
            return result

        start_time = time.time()

        try:
            test_func()
            result.status = TestStatus.PASSED
        except AssertionError as e:
            result.status = TestStatus.FAILED
            result.message = str(e) if str(e) else "Assertion failed"
            result.traceback = traceback.format_exc()
        except Exception as e:
            result.status = TestStatus.ERROR
            result.message = str(e)
            result.traceback = traceback.format_exc()

        result.duration = time.time() - start_time
        result.completed_at = time.time()

        # 运行 after_each 钩子
        self._run_hooks("after_each")

        return result

    def run_all(self, mode: RunMode = RunMode.SEQUENTIAL) -> RunSummary:
        """
        运行所有注册的测试

        Args:
            mode: 运行模式

        Returns:
            运行摘要
        """
        summary = RunSummary()
        summary.started_at = time.time()

        # 运行 before_all 钩子
        if not self._run_hooks("before_all"):
            summary.error = len(self._test_registry)
            summary.total = len(self._test_registry)
            return summary

        with self._lock:
            test_items = list(self._test_registry.items())

        if mode == RunMode.SEQUENTIAL:
            for test_id, test_func in test_items:
                result = self.run_test(test_id, test_func)
                with self._lock:
                    self._results.append(result)
                self._update_summary(summary, result)

        elif mode == RunMode.PARALLEL:
            results = []
            threads = []

            def run_and_collect(test_id, test_func):
                result = self.run_test(test_id, test_func)
                results.append(result)

            for test_id, test_func in test_items:
                thread = threading.Thread(target=run_and_collect, args=(test_id, test_func))
                threads.append(thread)
                thread.start()

            for thread in threads:
                thread.join()

            for result in results:
                with self._lock:
                    self._results.append(result)
                self._update_summary(summary, result)

        # 运行 after_all 钩子
        self._run_hooks("after_all")

        summary.completed_at = time.time()
        summary.duration = summary.completed_at - summary.started_at

        return summary

    def _update_summary(self, summary: RunSummary, result: TestResult) -> None:
        """更新运行摘要"""
        summary.total += 1
        if result.status == TestStatus.PASSED:
            summary.passed += 1
        elif result.status == TestStatus.FAILED:
            summary.failed += 1
        elif result.status == TestStatus.SKIPPED:
            summary.skipped += 1
        elif result.status == TestStatus.ERROR:
            summary.error += 1

    def run_suite(self, suite_name: str) -> RunSummary:
        """
        运行指定测试套件

        Args:
            suite_name: 套件名称

        Returns:
            运行摘要
        """
        summary = RunSummary()
        summary.started_at = time.time()

        with self._lock:
            suite = self._suites.get(suite_name)

        if suite is None:
            return summary

        # 运行 setup_class
        if suite.setup_class:
            try:
                suite.setup_class()
            except Exception:
                summary.error = len(suite.tests)
                summary.total = len(suite.tests)
                return summary

        for test_func in suite.tests:
            # 运行 setup
            if suite.setup:
                try:
                    suite.setup()
                except Exception:
                    result = TestResult(
                        test_id=self._generate_id(),
                        test_name=getattr(test_func, "__name__", str(test_func)),
                        status=TestStatus.ERROR,
                        message="setup failed",
                    )
                    with self._lock:
                        self._results.append(result)
                    self._update_summary(summary, result)
                    continue

            # 运行测试
            test_id = self._generate_id()
            result = self.run_test(test_id, test_func)
            with self._lock:
                self._results.append(result)
            self._update_summary(summary, result)

            # 运行 teardown
            if suite.teardown:
                try:
                    suite.teardown()
                except Exception:
                    pass

        # 运行 teardown_class
        if suite.teardown_class:
            try:
                suite.teardown_class()
            except Exception:
                pass

        summary.completed_at = time.time()
        summary.duration = summary.completed_at - summary.started_at

        return summary

    def get_results(self) -> List[TestResult]:
        """获取所有测试结果"""
        with self._lock:
            return list(self._results)

    def clear_results(self) -> None:
        """清空测试结果"""
        with self._lock:
            self._results.clear()

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            status_counts = {}
            for result in self._results:
                status = result.status.value
                status_counts[status] = status_counts.get(status, 0) + 1

            return {
                "total_tests": len(self._test_registry),
                "total_suites": len(self._suites),
                "results_count": len(self._results),
                "by_status": status_counts,
            }


# ============================================================================
# 全局单例
# ============================================================================

_test_runner_instance: Optional[TestRunner] = None
_test_runner_lock = threading.Lock()


def get_test_runner() -> TestRunner:
    """获取测试运行器全局单例"""
    global _test_runner_instance
    with _test_runner_lock:
        if _test_runner_instance is None:
            _test_runner_instance = TestRunner()
        return _test_runner_instance
