#!/usr/bin/env python3
"""
第33阶段验证测试 - 测试框架模块 (阶段366-370)

覆盖模块：
- 阶段366: TestRunner - 测试运行器
- 阶段367: AssertionEngine - 断言引擎
- 阶段368: MockFactory - 模拟工厂
- 阶段369: TestReporter - 测试报告
- 阶段370: TestFixture - 测试夹具
"""

import sys
import os
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from testing.test_runner import (
    TestRunner, TestResult, TestSuite, RunSummary,
    TestStatus, RunMode, get_test_runner,
)
from testing.assertion_engine import (
    AssertionEngine, AssertionResult, AssertionContext,
    AssertionError as TestAssertionError, AssertionType, get_assertion_engine,
)
from testing.mock_factory import (
    MockFactory, MockObject, MockConfig, CallRecord,
    CallType, VerificationMode, Mock, get_mock_factory,
)
from testing.test_reporter import (
    TestReporter, ReportConfig, ReportSummary, ReportResult,
    GeneratedReport, ReportFormat, ReportStatus, get_test_reporter,
)
from testing.test_fixture import (
    FixtureManager, DataProvider, FixtureContext,
    Fixture, FixtureValue, TestData,
    FixtureScope, FixturePhase,
    fixture, parametrize, get_fixture_manager, get_data_provider,
)


# ============================================================
# 阶段366: TestRunner 测试
# ============================================================

class TestTestRunner(unittest.TestCase):
    """测试运行器核心测试"""

    def setUp(self):
        self.runner = TestRunner()

    def test_register_test(self):
        def sample_test():
            pass
        test_id = self.runner.register_test("sample", sample_test)
        self.assertIsNotNone(test_id)
        self.assertTrue(test_id.startswith("test_"))

    def test_run_passed(self):
        def passing_test():
            pass
        test_id = self.runner.register_test("passing", passing_test)
        result = self.runner.run_test(test_id, passing_test)
        self.assertEqual(result.status, TestStatus.PASSED)

    def test_run_failed(self):
        def failing_test():
            raise AssertionError("Test failed")
        test_id = self.runner.register_test("failing", failing_test)
        result = self.runner.run_test(test_id, failing_test)
        self.assertEqual(result.status, TestStatus.FAILED)
        self.assertIn("failed", result.message)

    def test_run_error(self):
        def error_test():
            raise ValueError("Unexpected error")
        test_id = self.runner.register_test("error", error_test)
        result = self.runner.run_test(test_id, error_test)
        self.assertEqual(result.status, TestStatus.ERROR)

    def test_run_all(self):
        self.runner.register_test("t1", lambda: None)
        self.runner.register_test("t2", lambda: None)
        summary = self.runner.run_all()
        self.assertEqual(summary.total, 2)
        self.assertEqual(summary.passed, 2)

    def test_run_summary_success_rate(self):
        self.runner.register_test("t1", lambda: None)
        self.runner.register_test("t2", lambda: (_ for _ in ()).throw(AssertionError()))
        summary = self.runner.run_all()
        self.assertEqual(summary.success_rate, 0.5)

    def test_add_hook(self):
        called = []
        self.runner.add_hook("before_each", lambda: called.append("before"))
        self.runner.add_hook("after_each", lambda: called.append("after"))
        
        test_id = self.runner.register_test("hooked", lambda: called.append("test"))
        self.runner.run_test(test_id, lambda: called.append("test"))
        
        self.assertIn("before", called)
        self.assertIn("after", called)

    def test_get_stats(self):
        self.runner.register_test("t1", lambda: None)
        stats = self.runner.get_stats()
        self.assertEqual(stats["total_tests"], 1)

    def test_global_singleton(self):
        r1 = get_test_runner()
        r2 = get_test_runner()
        self.assertIs(r1, r2)


# ============================================================
# 阶段367: AssertionEngine 测试
# ============================================================

class TestAssertionEngine(unittest.TestCase):
    """断言引擎核心测试"""

    def setUp(self):
        self.engine = AssertionEngine()

    def test_equal_pass(self):
        result = self.engine.equal(42, 42)
        self.assertTrue(result.passed)

    def test_equal_fail(self):
        with self.assertRaises(TestAssertionError):
            self.engine.equal(42, 43)

    def test_not_equal_pass(self):
        result = self.engine.not_equal(42, 43)
        self.assertTrue(result.passed)

    def test_true_pass(self):
        result = self.engine.true(True)
        self.assertTrue(result.passed)

    def test_false_pass(self):
        result = self.engine.false(False)
        self.assertTrue(result.passed)

    def test_is_none_pass(self):
        result = self.engine.is_none(None)
        self.assertTrue(result.passed)

    def test_is_not_none_pass(self):
        result = self.engine.is_not_none("value")
        self.assertTrue(result.passed)

    def test_in_pass(self):
        result = self.engine.in_("a", ["a", "b", "c"])
        self.assertTrue(result.passed)

    def test_not_in_pass(self):
        result = self.engine.not_in("d", ["a", "b", "c"])
        self.assertTrue(result.passed)

    def test_is_instance_pass(self):
        result = self.engine.is_instance("text", str)
        self.assertTrue(result.passed)

    def test_greater_pass(self):
        result = self.engine.greater(10, 5)
        self.assertTrue(result.passed)

    def test_less_pass(self):
        result = self.engine.less(5, 10)
        self.assertTrue(result.passed)

    def test_between_pass(self):
        result = self.engine.between(5, 1, 10)
        self.assertTrue(result.passed)

    def test_matches_pass(self):
        result = self.engine.matches("hello world", r"hello")
        self.assertTrue(result.passed)

    def test_contains_pass(self):
        result = self.engine.contains([1, 2, 3], 2)
        self.assertTrue(result.passed)

    def test_raises_pass(self):
        def raise_error():
            raise ValueError("error")
        result = self.engine.raises(ValueError, raise_error)
        self.assertTrue(result.passed)

    def test_register_custom(self):
        def custom_assertion(value):
            return AssertionResult(
                passed=value > 0,
                assertion_type=AssertionType.GREATER,
                message="Value must be positive",
            )
        self.engine.register_custom("positive", custom_assertion)
        result = self.engine.custom("positive", 5)
        self.assertTrue(result.passed)

    def test_get_stats(self):
        self.engine.equal(1, 1)
        self.engine.true(True)
        stats = self.engine.get_stats()
        self.assertEqual(stats["total_assertions"], 2)

    def test_global_singleton(self):
        e1 = get_assertion_engine()
        e2 = get_assertion_engine()
        self.assertIs(e1, e2)


# ============================================================
# 阶段368: MockFactory 测试
# ============================================================

class TestMockFactory(unittest.TestCase):
    """模拟工厂核心测试"""

    def setUp(self):
        self.factory = MockFactory()

    def test_create_mock(self):
        mock = self.factory.create("test_mock")
        self.assertIsNotNone(mock)

    def test_mock_method_call(self):
        mock = self.factory.create("test")
        mock.some_method("arg1", "arg2")
        self.assertEqual(mock.call_count("some_method"), 1)

    def test_mock_return_value(self):
        mock = self.factory.create("test", return_value="default")
        mock.set_return_value("get_name", "MockName")
        result = mock.get_name()
        self.assertEqual(result, "MockName")

    def test_mock_side_effect(self):
        mock = self.factory.create("test")
        mock.set_side_effect("compute", lambda x: x * 2)
        result = mock.compute(5)
        self.assertEqual(result, 10)

    def test_mock_called_with(self):
        mock = self.factory.create("test")
        mock.method("a", "b", key="value")
        self.assertTrue(mock.called_with("method", "a", "b", key="value"))
        self.assertFalse(mock.called_with("method", "x", "y"))

    def test_verify_once(self):
        mock = self.factory.create("test")
        mock.method()
        self.assertTrue(self.factory.verify_called_once(mock, "method"))

    def test_verify_never(self):
        mock = self.factory.create("test")
        self.assertTrue(self.factory.verify_never(mock, "method"))

    def test_verify_at_least(self):
        mock = self.factory.create("test")
        mock.method()
        mock.method()
        self.assertTrue(self.factory.verify(mock, "method", VerificationMode.AT_LEAST, times=2))

    def test_mock_reset(self):
        mock = self.factory.create("test")
        mock.method()
        mock.reset()
        self.assertEqual(mock.call_count("method"), 0)

    def test_callable_mock(self):
        mock = Mock(return_value=42)
        result = mock()
        self.assertEqual(result, 42)

    def test_get_stats(self):
        self.factory.create("m1")
        self.factory.create("m2")
        stats = self.factory.get_stats()
        self.assertEqual(stats["total_mocks"], 2)

    def test_global_singleton(self):
        f1 = get_mock_factory()
        f2 = get_mock_factory()
        self.assertIs(f1, f2)


# ============================================================
# 阶段369: TestReporter 测试
# ============================================================

class TestTestReporter(unittest.TestCase):
    """测试报告器核心测试"""

    def setUp(self):
        self.reporter = TestReporter()

    def test_add_result(self):
        result = ReportResult(name="test1", status="passed", duration=0.1)
        self.reporter.add_result(result)
        results = self.reporter.get_results()
        self.assertEqual(len(results), 1)

    def test_add_results(self):
        results = [
            ReportResult(name="t1", status="passed", duration=0.1),
            ReportResult(name="t2", status="failed", duration=0.2),
        ]
        self.reporter.add_results(results)
        self.assertEqual(len(self.reporter.get_results()), 2)

    def test_summary(self):
        self.reporter.add_result(ReportResult(name="t1", status="passed", duration=0.1))
        self.reporter.add_result(ReportResult(name="t2", status="failed", duration=0.1))
        summary = self.reporter.get_summary()
        self.assertEqual(summary.total, 2)
        self.assertEqual(summary.passed, 1)
        self.assertEqual(summary.failed, 1)
        self.assertEqual(summary.success_rate, 0.5)

    def test_generate_json(self):
        self.reporter.add_result(ReportResult(name="t1", status="passed", duration=0.1))
        report = self.reporter.generate_json()
        self.assertEqual(report.format, ReportFormat.JSON)
        self.assertIn("t1", report.content)
        self.assertTrue(report.size > 0)

    def test_generate_html(self):
        self.reporter.add_result(ReportResult(name="t1", status="passed", duration=0.1))
        report = self.reporter.generate_html()
        self.assertEqual(report.format, ReportFormat.HTML)
        self.assertIn("<html>", report.content)
        self.assertIn("t1", report.content)

    def test_generate_junit(self):
        self.reporter.add_result(ReportResult(name="t1", status="passed", duration=0.1))
        report = self.reporter.generate_junit()
        self.assertEqual(report.format, ReportFormat.JUNIT)
        self.assertIn("<?xml", report.content)
        self.assertIn("testsuite", report.content)

    def test_generate_text(self):
        self.reporter.add_result(ReportResult(name="t1", status="passed", duration=0.1))
        report = self.reporter.generate_text()
        self.assertEqual(report.format, ReportFormat.TEXT)
        self.assertIn("t1", report.content)
        self.assertIn("Summary:", report.content)

    def test_generate_default(self):
        self.reporter.add_result(ReportResult(name="t1", status="passed", duration=0.1))
        report = self.reporter.generate()
        self.assertEqual(report.format, ReportFormat.JSON)

    def test_clear(self):
        self.reporter.add_result(ReportResult(name="t1", status="passed", duration=0.1))
        self.reporter.clear()
        self.assertEqual(len(self.reporter.get_results()), 0)

    def test_get_stats(self):
        self.reporter.add_result(ReportResult(name="t1", status="passed", duration=0.1))
        stats = self.reporter.get_stats()
        self.assertEqual(stats["total_results"], 1)

    def test_global_singleton(self):
        r1 = get_test_reporter()
        r2 = get_test_reporter()
        self.assertIs(r1, r2)


# ============================================================
# 阶段370: TestFixture 测试
# ============================================================

class TestFixtureManager(unittest.TestCase):
    """夹具管理器核心测试"""

    def setUp(self):
        self.manager = FixtureManager()

    def test_register_fixture(self):
        self.manager.register("my_fixture", lambda: "value")
        fixture = self.manager.get_fixture("my_fixture")
        self.assertIsNotNone(fixture)

    def test_get_value(self):
        self.manager.register("data", lambda: {"key": "value"})
        value = self.manager.get_value("data")
        self.assertEqual(value["key"], "value")

    def test_fixture_caching(self):
        call_count = [0]
        def create_data():
            call_count[0] += 1
            return "cached"
        
        self.manager.register("cached_data", create_data, scope=FixtureScope.SESSION)
        
        # 多次获取应该使用缓存
        v1 = self.manager.get_value("cached_data")
        v2 = self.manager.get_value("cached_data")
        
        self.assertEqual(v1, v2)
        self.assertEqual(call_count[0], 1)  # 只调用一次

    def test_cleanup(self):
        self.manager.register("temp", lambda: "temp_value", scope=FixtureScope.FUNCTION)
        self.manager.get_value("temp")
        count = self.manager.cleanup(FixtureScope.FUNCTION)
        self.assertEqual(count, 1)

    def test_autouse_fixtures(self):
        self.manager.register("auto1", lambda: "auto", autouse=True)
        self.manager.register("manual", lambda: "manual", autouse=False)
        autouse = self.manager.get_autouse_fixtures()
        self.assertIn("auto1", autouse)
        self.assertNotIn("manual", autouse)

    def test_get_stats(self):
        self.manager.register("f1", lambda: 1)
        self.manager.register("f2", lambda: 2, scope=FixtureScope.CLASS)
        stats = self.manager.get_stats()
        self.assertEqual(stats["total_fixtures"], 2)

    def test_global_singleton(self):
        m1 = get_fixture_manager()
        m2 = get_fixture_manager()
        self.assertIs(m1, m2)


class TestDataProvider(unittest.TestCase):
    """数据提供器测试"""

    def setUp(self):
        self.provider = DataProvider()

    def test_register(self):
        self.provider.register("numbers", [1, 2, 3])
        data = self.provider.get("numbers")
        self.assertEqual(len(data), 3)

    def test_register_dict(self):
        self.provider.register_dict("configs", [
            {"name": "a", "value": 1},
            {"name": "b", "value": 2},
        ])
        data = self.provider.get("configs")
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0].kwargs["name"], "a")

    def test_parametrize(self):
        data = self.provider.parametrize([1, 2, 3], ids=["one", "two", "three"])
        self.assertEqual(len(data), 3)
        self.assertEqual(data[0].id, "one")
        self.assertEqual(data[0].args, (1,))

    def test_get_stats(self):
        self.provider.register("d1", [1, 2])
        self.provider.register("d2", [3, 4, 5])
        stats = self.provider.get_stats()
        self.assertEqual(stats["total_datasets"], 2)

    def test_global_singleton(self):
        p1 = get_data_provider()
        p2 = get_data_provider()
        self.assertIs(p1, p2)


class TestFixtureContext(unittest.TestCase):
    """夹具上下文管理器测试"""

    def test_context_manager(self):
        manager = FixtureManager()
        manager.register("resource", lambda: {"data": "test"})
        
        with FixtureContext(manager, ["resource"]) as ctx:
            value = ctx.get("resource")
            self.assertEqual(value["data"], "test")


# ============================================================
# 数据结构测试
# ============================================================

class TestDataStructures(unittest.TestCase):
    """数据结构基础测试"""

    def test_test_status_enum(self):
        self.assertEqual(TestStatus.PASSED.value, "passed")
        self.assertEqual(TestStatus.FAILED.value, "failed")

    def test_run_mode_enum(self):
        self.assertEqual(RunMode.SEQUENTIAL.value, "sequential")
        self.assertEqual(RunMode.PARALLEL.value, "parallel")

    def test_assertion_type_enum(self):
        self.assertEqual(AssertionType.EQUAL.value, "equal")
        self.assertEqual(AssertionType.MATCHES.value, "matches")

    def test_call_type_enum(self):
        self.assertEqual(CallType.METHOD.value, "method")
        self.assertEqual(CallType.PROPERTY.value, "property")

    def test_verification_mode_enum(self):
        self.assertEqual(VerificationMode.ONCE.value, "once")
        self.assertEqual(VerificationMode.NEVER.value, "never")

    def test_report_format_enum(self):
        self.assertEqual(ReportFormat.JSON.value, "json")
        self.assertEqual(ReportFormat.HTML.value, "html")

    def test_fixture_scope_enum(self):
        self.assertEqual(FixtureScope.FUNCTION.value, "function")
        self.assertEqual(FixtureScope.SESSION.value, "session")

    def test_test_result_dataclass(self):
        result = TestResult(
            test_id="t1",
            test_name="test_one",
            status=TestStatus.PASSED,
            duration=0.5,
        )
        self.assertEqual(result.test_id, "t1")
        self.assertEqual(result.status, TestStatus.PASSED)

    def test_run_summary_dataclass(self):
        summary = RunSummary(total=10, passed=8, failed=2)
        self.assertEqual(summary.success_rate, 0.8)

    def test_mock_config_dataclass(self):
        config = MockConfig(name="test", return_value=42)
        self.assertEqual(config.name, "test")
        self.assertEqual(config.return_value, 42)

    def test_report_config_dataclass(self):
        config = ReportConfig(title="My Report", format=ReportFormat.HTML)
        self.assertEqual(config.title, "My Report")
        self.assertEqual(config.format, ReportFormat.HTML)


if __name__ == "__main__":
    unittest.main(verbosity=2)
