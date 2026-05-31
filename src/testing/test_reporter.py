"""
测试报告模块 (阶段369)

提供测试结果报告生成，支持JSON、HTML和JUnit格式。
线程安全设计，使用 threading.RLock 保证并发安全。
确定性规则设计，无模型依赖，无循环依赖。
"""

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, TextIO


# ============================================================================
# 枚举定义
# ============================================================================


class ReportFormat(Enum):
    """报告格式枚举"""
    JSON = "json"
    HTML = "html"
    JUNIT = "junit"
    TEXT = "text"


class ReportStatus(Enum):
    """报告状态枚举"""
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


# ============================================================================
# 数据类定义
# ============================================================================


@dataclass
class ReportConfig:
    """报告配置数据类"""
    format: ReportFormat = ReportFormat.JSON
    title: str = "Test Report"
    include_traceback: bool = True
    include_timestamp: bool = True
    output_path: Optional[str] = None


@dataclass
class ReportSummary:
    """报告摘要数据类"""
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    error: int = 0
    duration: float = 0.0
    success_rate: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ReportResult:
    """报告结果数据类"""
    name: str
    status: str
    duration: float = 0.0
    message: Optional[str] = None
    traceback: Optional[str] = None


@dataclass
class GeneratedReport:
    """生成的报告数据类"""
    format: ReportFormat
    content: str
    summary: ReportSummary
    status: ReportStatus = ReportStatus.COMPLETED
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    size: int = 0


# ============================================================================
# 测试报告器
# ============================================================================


class TestReporter:
    """
    测试报告器
    
    收集测试结果并生成多种格式的报告。
    线程安全，使用 RLock 保证并发访问安全。
    """
    
    def __init__(self, config: Optional[ReportConfig] = None) -> None:
        self._lock = threading.RLock()
        self._config = config or ReportConfig()
        self._results: List[ReportResult] = []
        self._summary = ReportSummary()
    
    def add_result(self, result: ReportResult) -> None:
        """添加测试结果"""
        with self._lock:
            self._results.append(result)
            self._update_summary(result)
    
    def add_results(self, results: List[ReportResult]) -> None:
        """批量添加测试结果"""
        with self._lock:
            for result in results:
                self._results.append(result)
                self._update_summary(result)
    
    def _update_summary(self, result: ReportResult) -> None:
        """更新摘要"""
        self._summary.total += 1
        self._summary.duration += result.duration
        
        if result.status == "passed":
            self._summary.passed += 1
        elif result.status == "failed":
            self._summary.failed += 1
        elif result.status == "skipped":
            self._summary.skipped += 1
        elif result.status == "error":
            self._summary.error += 1
        
        if self._summary.total > 0:
            self._summary.success_rate = self._summary.passed / self._summary.total
    
    def generate_json(self) -> GeneratedReport:
        """生成JSON格式报告"""
        with self._lock:
            data = {
                "title": self._config.title,
                "summary": {
                    "total": self._summary.total,
                    "passed": self._summary.passed,
                    "failed": self._summary.failed,
                    "skipped": self._summary.skipped,
                    "error": self._summary.error,
                    "duration": self._summary.duration,
                    "success_rate": self._summary.success_rate,
                    "timestamp": self._summary.timestamp,
                },
                "results": [
                    {
                        "name": r.name,
                        "status": r.status,
                        "duration": r.duration,
                        "message": r.message,
                        "traceback": r.traceback if self._config.include_traceback else None,
                    }
                    for r in self._results
                ],
            }
            
            content = json.dumps(data, indent=2, ensure_ascii=False)
            
            return GeneratedReport(
                format=ReportFormat.JSON,
                content=content,
                summary=self._summary,
                size=len(content),
            )
    
    def generate_html(self) -> GeneratedReport:
        """生成HTML格式报告"""
        with self._lock:
            # 计算状态颜色
            status_colors = {
                "passed": "#28a745",
                "failed": "#dc3545",
                "skipped": "#ffc107",
                "error": "#6c757d",
            }
            
            # 生成结果行
            result_rows = ""
            for r in self._results:
                color = status_colors.get(r.status, "#6c757d")
                traceback_html = ""
                if self._config.include_traceback and r.traceback:
                    traceback_html = f"<pre class=\"traceback\">{r.traceback}</pre>"
                
                result_rows += f"""
                <tr class=\"{r.status}\">
                    <td>{r.name}</td>
                    <td style=\"color: {color}\">{r.status.upper()}</td>
                    <td>{r.duration:.4f}s</td>
                    <td>{r.message or ''}</td>
                </tr>
                {traceback_html}
                """
            
            # 生成完整HTML
            html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset=\"utf-8\">
    <title>{self._config.title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #333; }}
        .summary {{ background: #f5f5f5; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
        .summary span {{ margin-right: 20px; }}
        .passed {{ color: #28a745; }}
        .failed {{ color: #dc3545; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background: #f5f5f5; }}
        .traceback {{ background: #f8f8f8; padding: 10px; margin: 5px 0; font-size: 12px; overflow-x: auto; }}
    </style>
</head>
<body>
    <h1>{self._config.title}</h1>
    <div class=\"summary\">
        <span>Total: <strong>{self._summary.total}</strong></span>
        <span class=\"passed\">Passed: <strong>{self._summary.passed}</strong></span>
        <span class=\"failed\">Failed: <strong>{self._summary.failed}</strong></span>
        <span>Skipped: {self._summary.skipped}</span>
        <span>Error: {self._summary.error}</span>
        <span>Duration: {self._summary.duration:.2f}s</span>
        <span>Success Rate: {self._summary.success_rate:.1%}</span>
    </div>
    <table>
        <tr>
            <th>Test Name</th>
            <th>Status</th>
            <th>Duration</th>
            <th>Message</th>
        </tr>
        {result_rows}
    </table>
    <p style=\"color: #999; font-size: 12px; margin-top: 20px;\">Generated at: {self._summary.timestamp}</p>
</body>
</html>"""
            
            return GeneratedReport(
                format=ReportFormat.HTML,
                content=html,
                summary=self._summary,
                size=len(html),
            )
    
    def generate_junit(self) -> GeneratedReport:
        """生成JUnit XML格式报告"""
        with self._lock:
            testcases = ""
            for r in self._results:
                if r.status == "passed":
                    testcases += f"""        <testcase name=\"{r.name}\" time=\"{r.duration}\"/>\n"""
                elif r.status in ("failed", "error"):
                    failure_type = "failure" if r.status == "failed" else "error"
                    message = r.message or ""
                    testcases += f"""        <testcase name=\"{r.name}\" time=\"{r.duration}\">
            <{failure_type} message=\"{message}\">{message}</{failure_type}>
        </testcase>\n"""
                elif r.status == "skipped":
                    testcases += f"""        <testcase name=\"{r.name}\" time=\"{r.duration}\">
            <skipped/>
        </testcase>\n"""
            
            xml = f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<testsuite name=\"{self._config.title}\" tests=\"{self._summary.total}\" failures=\"{self._summary.failed}\" errors=\"{self._summary.error}\" skipped=\"{self._summary.skipped}\" time=\"{self._summary.duration}\">
{testcases}</testsuite>"""
            
            return GeneratedReport(
                format=ReportFormat.JUNIT,
                content=xml,
                summary=self._summary,
                size=len(xml),
            )
    
    def generate_text(self) -> GeneratedReport:
        """生成文本格式报告"""
        with self._lock:
            lines = [
                f"{'=' * 60}",
                f"{self._config.title}",
                f"{'=' * 60}",
                "",
                "Summary:",
                f"  Total:      {self._summary.total}",
                f"  Passed:     {self._summary.passed}",
                f"  Failed:     {self._summary.failed}",
                f"  Skipped:    {self._summary.skipped}",
                f"  Error:      {self._summary.error}",
                f"  Duration:   {self._summary.duration:.2f}s",
                f"  Success:    {self._summary.success_rate:.1%}",
                "",
                "Results:",
                "-" * 60,
            ]
            
            for r in self._results:
                status_mark = "✓" if r.status == "passed" else "✗"
                lines.append(f"{status_mark} {r.name} [{r.status}] ({r.duration:.4f}s)")
                if r.message:
                    lines.append(f"    Message: {r.message}")
                if self._config.include_traceback and r.traceback:
                    lines.append(f"    Traceback:\n{r.traceback}")
            
            lines.extend([
                "-" * 60,
                f"Generated at: {self._summary.timestamp}",
            ])
            
            content = "\n".join(lines)
            
            return GeneratedReport(
                format=ReportFormat.TEXT,
                content=content,
                summary=self._summary,
                size=len(content),
            )
    
    def generate(self, format: Optional[ReportFormat] = None) -> GeneratedReport:
        """
        生成报告
        
        Args:
            format: 报告格式，默认使用配置中的格式
            
        Returns:
            生成的报告
        """
        fmt = format or self._config.format
        
        if fmt == ReportFormat.JSON:
            return self.generate_json()
        elif fmt == ReportFormat.HTML:
            return self.generate_html()
        elif fmt == ReportFormat.JUNIT:
            return self.generate_junit()
        elif fmt == ReportFormat.TEXT:
            return self.generate_text()
        
        return self.generate_json()
    
    def save(self, report: GeneratedReport, path: Optional[str] = None) -> bool:
        """
        保存报告到文件
        
        Args:
            report: 生成的报告
            path: 文件路径，默认使用配置中的路径
            
        Returns:
            是否成功保存
        """
        file_path = path or self._config.output_path
        if file_path is None:
            return False
        
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(report.content)
            return True
        except IOError:
            return False
    
    def get_summary(self) -> ReportSummary:
        """获取报告摘要"""
        with self._lock:
            return self._summary
    
    def get_results(self) -> List[ReportResult]:
        """获取所有结果"""
        with self._lock:
            return list(self._results)
    
    def clear(self) -> None:
        """清空结果"""
        with self._lock:
            self._results.clear()
            self._summary = ReportSummary()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                "total_results": len(self._results),
                "summary": {
                    "total": self._summary.total,
                    "passed": self._summary.passed,
                    "failed": self._summary.failed,
                    "success_rate": self._summary.success_rate,
                },
            }


# ============================================================================
# 全局单例
# ============================================================================

_test_reporter_instance: Optional[TestReporter] = None
_test_reporter_lock = threading.Lock()


def get_test_reporter() -> TestReporter:
    """获取测试报告器全局单例"""
    global _test_reporter_instance
    with _test_reporter_lock:
        if _test_reporter_instance is None:
            _test_reporter_instance = TestReporter()
        return _test_reporter_instance
