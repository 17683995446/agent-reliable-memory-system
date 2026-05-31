#!/usr/bin/env python3
"""
报表生成器 (ReportGenerator) - 阶段342

职责：
- 报表模板：日报/周报/月报/自定义
- 数据采集：从多个模块收集统计信息
- 报表渲染：Markdown/HTML/Text格式
- 报表调度：定时生成
- 报表归档：历史报表管理

设计原则：
- 确定性规则，无模型依赖
- 线程安全（RLock）
- 最小层级，无循环依赖
"""

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


# ============================================================
# 枚举与数据结构
# ============================================================

class ReportType(Enum):
    """报表类型"""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CUSTOM = "custom"


class ReportFormat(Enum):
    """报表输出格式"""
    MARKDOWN = "markdown"
    HTML = "html"
    TEXT = "text"


@dataclass
class ReportSection:
    """报表章节"""
    title: str = ""
    content: str = ""
    data: Any = None
    order: int = 0
    level: int = 2  # 标题层级


@dataclass
class ReportTemplate:
    """报表模板"""
    name: str = ""
    report_type: ReportType = ReportType.DAILY
    sections: List[str] = field(default_factory=list)  # 章节名称列表
    format: ReportFormat = ReportFormat.MARKDOWN
    header: str = ""
    footer: str = ""
    collectors: List[str] = field(default_factory=list)  # 数据采集器名称


@dataclass
class ReportData:
    """报表数据"""
    section_name: str
    title: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)
    tables: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


@dataclass
class GeneratedReport:
    """已生成报表"""
    id: str = ""
    name: str = ""
    report_type: str = ""
    format: str = ""
    generated_at: float = 0.0
    period_start: float = 0.0
    period_end: float = 0.0
    content: str = ""
    file_path: str = ""
    sections_count: int = 0
    file_size: int = 0

    def __post_init__(self):
        if self.generated_at == 0.0:
            self.generated_at = time.time()
        if not self.id:
            import uuid
            self.id = uuid.uuid4().hex[:12]


@dataclass
class MetricPoint:
    """指标数据点"""
    name: str
    value: Any
    unit: str = ""
    trend: str = ""  # "up", "down", "stable"
    change_percent: float = 0.0


# ============================================================
# 数据采集器
# ============================================================

class DataCollector:
    """
    数据采集器

    核心功能：
    1. 注册数据源
    2. 采集指定时间范围的统计数据
    3. 提供标准化的报表数据
    """

    def __init__(self):
        self._sources: Dict[str, Callable[[float, float], Dict[str, Any]]] = {}
        self._cache: Dict[str, Tuple[float, Dict]] = {}
        self._cache_ttl = 60.0  # 缓存60秒
        self._lock = threading.RLock()

    def register(self, name: str,
                 collector_fn: Callable[[float, float], Dict[str, Any]]) -> None:
        """
        注册数据源

        Args:
            name: 数据源名称
            collector_fn: 采集函数 (start_time, end_time) -> Dict
        """
        with self._lock:
            self._sources[name] = collector_fn

    def unregister(self, name: str) -> bool:
        """注销数据源"""
        with self._lock:
            return self._sources.pop(name, None) is not None

    def collect(self, name: str, start_time: float,
                end_time: float) -> Optional[Dict[str, Any]]:
        """采集单个数据源"""
        with self._lock:
            fn = self._sources.get(name)
            if fn is None:
                return None

        try:
            return fn(start_time, end_time)
        except Exception:
            return {"error": f"Collector '{name}' failed"}

    def collect_all(self, start_time: float,
                    end_time: float) -> Dict[str, Dict[str, Any]]:
        """采集所有数据源"""
        results = {}
        with self._lock:
            names = list(self._sources.keys())
        for name in names:
            data = self.collect(name, start_time, end_time)
            if data is not None:
                results[name] = data
        return results

    def list_sources(self) -> List[str]:
        """列出所有数据源"""
        with self._lock:
            return list(self._sources.keys())

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "sources": len(self._sources),
                "source_names": list(self._sources.keys()),
                "cache_ttl": self._cache_ttl,
            }


# ============================================================
# 报表渲染器
# ============================================================

class MarkdownRenderer:
    """Markdown渲染器"""

    @staticmethod
    def render(title: str, sections: List[ReportSection],
               header: str = "", footer: str = "") -> str:
        lines = []
        if header:
            lines.append(header)
            lines.append("")

        lines.append(f"# {title}")
        lines.append("")

        for section in sorted(sections, key=lambda s: s.order):
            prefix = "#" * section.level
            lines.append(f"{prefix} {section.title}")
            lines.append("")
            if section.content:
                lines.append(section.content)
                lines.append("")
            if section.data and isinstance(section.data, dict):
                for k, v in section.data.items():
                    lines.append(f"- **{k}**: {v}")
                lines.append("")

        if footer:
            lines.append("---")
            lines.append(footer)

        return "\n".join(lines)


class HtmlRenderer:
    """HTML渲染器"""

    @staticmethod
    def render(title: str, sections: List[ReportSection],
               header: str = "", footer: str = "") -> str:
        lines = [
            "<!DOCTYPE html>",
            "<html><head><meta charset='utf-8'>",
            f"<title>{title}</title>",
            "<style>",
            "body { font-family: Arial, sans-serif; margin: 40px; }",
            "h1 { color: #333; } h2 { color: #555; border-bottom: 1px solid #ddd; }",
            "ul { padding-left: 20px; }",
            "li { margin: 4px 0; }",
            "table { border-collapse: collapse; width: 100%; margin: 10px 0; }",
            "th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }",
            "th { background: #f5f5f5; }",
            ".footer { margin-top: 40px; color: #999; font-size: 12px; }",
            "</style></head><body>",
        ]

        if header:
            lines.append(f"<div class='header'>{header}</div>")

        lines.append(f"<h1>{title}</h1>")

        for section in sorted(sections, key=lambda s: s.order):
            tag = f"h{section.level}"
            lines.append(f"<{tag}>{section.title}</{tag}>")
            if section.content:
                lines.append(f"<p>{section.content}</p>")
            if section.data and isinstance(section.data, dict):
                lines.append("<ul>")
                for k, v in section.data.items():
                    lines.append(f"<li><strong>{k}:</strong> {v}</li>")
                lines.append("</ul>")

        if footer:
            lines.append(f"<div class='footer'>{footer}</div>")

        lines.append("</body></html>")
        return "\n".join(lines)


class TextRenderer:
    """纯文本渲染器"""

    @staticmethod
    def render(title: str, sections: List[ReportSection],
               header: str = "", footer: str = "") -> str:
        lines = []
        if header:
            lines.append(header)
            lines.append("=" * len(header))
            lines.append("")

        lines.append(title)
        lines.append("=" * len(title))
        lines.append("")

        for section in sorted(sections, key=lambda s: s.order):
            lines.append(section.title)
            lines.append("-" * len(section.title))
            if section.content:
                lines.append(section.content)
            if section.data and isinstance(section.data, dict):
                max_key_len = max(len(str(k)) for k in section.data.keys())
                for k, v in section.data.items():
                    lines.append(f"  {str(k).ljust(max_key_len)} : {v}")
            lines.append("")

        if footer:
            lines.append("-" * 40)
            lines.append(footer)

        return "\n".join(lines)


# ============================================================
# 报表生成器
# ============================================================

class ReportGenerator:
    """
    报表生成器

    核心功能：
    1. 模板管理
    2. 数据采集
    3. 多格式渲染
    4. 报表生成与归档
    5. 定时调度
    """

    def __init__(self, output_dir: str = ""):
        self._output_dir = output_dir
        self._collector = DataCollector()
        self._templates: Dict[str, ReportTemplate] = {}
        self._renderers = {
            ReportFormat.MARKDOWN: MarkdownRenderer,
            ReportFormat.HTML: HtmlRenderer,
            ReportFormat.TEXT: TextRenderer,
        }
        self._reports: List[GeneratedReport] = []
        self._lock = threading.RLock()
        self._total_generated = 0

    # ---- 模板管理 ----

    def add_template(self, template: ReportTemplate) -> None:
        """添加报表模板"""
        with self._lock:
            self._templates[template.name] = template

    def remove_template(self, name: str) -> bool:
        """移除模板"""
        with self._lock:
            return self._templates.pop(name, None) is not None

    def get_template(self, name: str) -> Optional[ReportTemplate]:
        """获取模板"""
        with self._lock:
            return self._templates.get(name)

    def list_templates(self) -> List[Dict[str, Any]]:
        """列出所有模板"""
        with self._lock:
            return [
                {
                    "name": t.name,
                    "type": t.report_type.value,
                    "sections": t.sections,
                    "format": t.format.value,
                }
                for t in self._templates.values()
            ]

    # ---- 数据采集 ----

    def register_collector(self, name: str,
                            fn: Callable[[float, float], Dict[str, Any]]) -> None:
        """注册数据采集器"""
        self._collector.register(name, fn)

    def collect_data(self, start_time: float,
                     end_time: float) -> Dict[str, Dict[str, Any]]:
        """采集所有数据"""
        return self._collector.collect_all(start_time, end_time)

    # ---- 报表生成 ----

    def generate(self, template_name: str,
                 start_time: Optional[float] = None,
                 end_time: Optional[float] = None,
                 extra_sections: Optional[List[ReportSection]] = None) -> Optional[GeneratedReport]:
        """
        生成报表

        Args:
            template_name: 模板名称
            start_time: 报表周期开始时间
            end_time: 报表周期结束时间
            extra_sections: 额外章节

        Returns:
            生成的报表
        """
        with self._lock:
            template = self._templates.get(template_name)
            if template is None:
                return None

        # 计算时间范围
        now = time.time()
        if end_time is None:
            end_time = now
        if start_time is None:
            start_time = self._calculate_period_start(template.report_type, end_time)

        # 采集数据
        collected = self.collect_data(start_time, end_time)

        # 构建章节
        sections = []
        for i, section_name in enumerate(template.sections):
            data = collected.get(section_name, {})
            section = ReportSection(
                title=section_name,
                data=data,
                order=i + 1,
                level=2,
            )
            sections.append(section)

        # 添加额外章节
        if extra_sections:
            offset = len(sections)
            for i, sec in enumerate(extra_sections):
                sec.order = offset + i + 1
                sections.append(sec)

        # 渲染
        renderer = self._renderers.get(template.format)
        if renderer is None:
            return None

        title = f"{template.name} ({self._format_period(template.report_type, start_time, end_time)})"
        content = renderer.render(title, sections, template.header, template.footer)

        report = GeneratedReport(
            name=template.name,
            report_type=template.report_type.value,
            format=template.format.value,
            period_start=start_time,
            period_end=end_time,
            content=content,
            sections_count=len(sections),
        )

        with self._lock:
            self._reports.append(report)
            self._total_generated += 1

        return report

    def generate_to_file(self, template_name: str, file_path: str,
                         start_time: Optional[float] = None,
                         end_time: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """生成报表并保存到文件"""
        report = self.generate(template_name, start_time, end_time)
        if report is None:
            return None

        import os
        dir_path = os.path.dirname(file_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        ext_map = {
            ReportFormat.MARKDOWN: ".md",
            ReportFormat.HTML: ".html",
            ReportFormat.TEXT: ".txt",
        }

        with self._lock:
            template = self._templates.get(template_name)
            ext = ext_map.get(template.format, ".txt") if template else ".txt"

        full_path = file_path if file_path.endswith(ext) else file_path + ext

        with open(full_path, "w", encoding="utf-8") as f:
            f.write(report.content)

        report.file_path = full_path
        report.file_size = len(report.content.encode("utf-8"))

        return {
            "file_path": full_path,
            "format": report.format,
            "sections": report.sections_count,
            "file_size": report.file_size,
        }

    # ---- 报表查询 ----

    def get_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        """获取报表"""
        with self._lock:
            for r in self._reports:
                if r.id == report_id:
                    return {
                        "id": r.id,
                        "name": r.name,
                        "type": r.report_type,
                        "format": r.format,
                        "generated_at": r.generated_at,
                        "period_start": r.period_start,
                        "period_end": r.period_end,
                        "sections": r.sections_count,
                        "file_size": r.file_size,
                    }
            return None

    def list_reports(self, limit: int = 50) -> List[Dict[str, Any]]:
        """列出报表"""
        with self._lock:
            items = self._reports[-limit:]
            return [
                {
                    "id": r.id,
                    "name": r.name,
                    "type": r.report_type,
                    "format": r.format,
                    "generated_at": r.generated_at,
                    "sections": r.sections_count,
                }
                for r in reversed(items)
            ]

    # ---- 统计 ----

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "total_generated": self._total_generated,
                "templates": len(self._templates),
                "collectors": self._collector.get_stats()["sources"],
                "reports": len(self._reports),
            }

    # ---- 内部方法 ----

    @staticmethod
    def _calculate_period_start(report_type: ReportType,
                                  end_time: float) -> float:
        """计算报表周期开始时间"""
        if report_type == ReportType.DAILY:
            return end_time - 86400  # 24小时
        elif report_type == ReportType.WEEKLY:
            return end_time - 604800  # 7天
        elif report_type == ReportType.MONTHLY:
            return end_time - 2592000  # 30天
        return end_time - 86400

    @staticmethod
    def _format_period(report_type: ReportType,
                       start: float, end: float) -> str:
        """格式式化周期描述"""
        from datetime import datetime
        fmt = "%Y-%m-%d %H:%M"
        s = datetime.fromtimestamp(start).strftime(fmt)
        e = datetime.fromtimestamp(end).strftime(fmt)
        type_name = {
            ReportType.DAILY: "日报",
            ReportType.WEEKLY: "周报",
            ReportType.MONTHLY: "月报",
            ReportType.CUSTOM: "自定义",
        }.get(report_type, "报表")
        return f"{type_name} {s} ~ {e}"


# ============================================================
# 全局单例
# ============================================================

_report_generator: Optional[ReportGenerator] = None
_rg_lock = threading.RLock()


def get_report_generator() -> ReportGenerator:
    """获取全局报表生成器"""
    global _report_generator
    if _report_generator is None:
        with _rg_lock:
            if _report_generator is None:
                _report_generator = ReportGenerator()
    return _report_generator
