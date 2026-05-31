"""
测试框架模块 (阶段366-370)

提供测试运行、断言、模拟、报告和夹具管理功能。
"""

from .test_runner import (
    TestRunner,
    TestResult,
    TestSuite,
    RunSummary,
    TestStatus,
    RunMode,
    get_test_runner,
)
from .assertion_engine import (
    AssertionEngine,
    AssertionResult,
    AssertionContext,
    AssertionError,
    AssertionType,
    get_assertion_engine,
)
from .mock_factory import (
    MockFactory,
    MockObject,
    MockConfig,
    CallRecord,
    CallType,
    VerificationMode,
    Mock,
    get_mock_factory,
)
from .test_reporter import (
    TestReporter,
    ReportConfig,
    ReportSummary,
    ReportResult,
    GeneratedReport,
    ReportFormat,
    ReportStatus,
    get_test_reporter,
)
from .test_fixture import (
    FixtureManager,
    DataProvider,
    FixtureContext,
    Fixture,
    FixtureValue,
    TestData,
    FixtureScope,
    FixturePhase,
    fixture,
    parametrize,
    get_fixture_manager,
    get_data_provider,
)

__all__ = [
    # test_runner
    "TestRunner",
    "TestResult",
    "TestSuite",
    "RunSummary",
    "TestStatus",
    "RunMode",
    "get_test_runner",
    # assertion_engine
    "AssertionEngine",
    "AssertionResult",
    "AssertionContext",
    "AssertionError",
    "AssertionType",
    "get_assertion_engine",
    # mock_factory
    "MockFactory",
    "MockObject",
    "MockConfig",
    "CallRecord",
    "CallType",
    "VerificationMode",
    "Mock",
    "get_mock_factory",
    # test_reporter
    "TestReporter",
    "ReportConfig",
    "ReportSummary",
    "ReportResult",
    "GeneratedReport",
    "ReportFormat",
    "ReportStatus",
    "get_test_reporter",
    # test_fixture
    "FixtureManager",
    "DataProvider",
    "FixtureContext",
    "Fixture",
    "FixtureValue",
    "TestData",
    "FixtureScope",
    "FixturePhase",
    "fixture",
    "parametrize",
    "get_fixture_manager",
    "get_data_provider",
]
