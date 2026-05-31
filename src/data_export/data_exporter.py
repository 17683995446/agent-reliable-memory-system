#!/usr/bin/env python3
"""
数据导出器 (DataExporter) - 阶段341

职责：
- 统一导出接口：JSON/CSV/Excel/PDF/Markdown
- 数据源适配：字典列表、嵌套结构、统计信息
- 导出配置：字段选择、排序、过滤、分页
- 导出任务管理：异步导出、进度跟踪
- 导出历史记录

设计原则：
- 确定性规则，无模型依赖
- 线程安全（RLock）
- 最小层级，无循环依赖
"""

import csv
import io
import json
import os
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


# ============================================================
# 枚举与数据结构
# ============================================================

class ExportFormat(Enum):
    """导出格式"""
    JSON = "json"
    CSV = "csv"
    MARKDOWN = "markdown"
    HTML = "html"
    TEXT = "text"


class ExportStatus(Enum):
    """导出状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DataSourceType(Enum):
    """数据源类型"""
    DICT_LIST = "dict_list"       # 字典列表
    NESTED = "nested"             # 嵌套结构
    SINGLE = "single"             # 单个对象
    STATS = "stats"               # 统计信息


@dataclass
class ExportConfig:
    """导出配置"""
    format: ExportFormat = ExportFormat.JSON
    fields: Optional[List[str]] = None     # 字段选择（None=全部）
    exclude_fields: Optional[List[str]] = None
    sort_by: Optional[str] = None          # 排序字段
    sort_desc: bool = False
    filter_fn: Optional[Callable[[Dict], bool]] = None  # 过滤函数
    page_size: int = 0                     # 分页大小（0=不分页）
    page: int = 1                          # 页码
    include_header: bool = True            # 包含表头
    indent: int = 2                        # JSON缩进
    encoding: str = "utf-8"
    flatten_nested: bool = False           # 展平嵌套字段
    nested_separator: str = "."            # 嵌套字段分隔符


@dataclass
class ExportTask:
    """导出任务"""
    id: str = ""
    name: str = ""
    config: ExportConfig = field(default_factory=ExportConfig)
    status: ExportStatus = ExportStatus.PENDING
    data_source: Any = None
    output_path: str = ""
    created_at: float = 0.0
    started_at: float = 0.0
    completed_at: float = 0.0
    total_records: int = 0
    exported_records: int = 0
    file_size: int = 0
    error: Optional[str] = None

    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = time.time()
        if not self.id:
            import uuid
            self.id = uuid.uuid4().hex[:12]


@dataclass
class ExportHistory:
    """导出历史"""
    task_id: str
    name: str
    format: str
    status: str
    records: int
    file_size: int
    output_path: str
    created_at: float = 0.0
    duration_ms: float = 0.0


# ============================================================
# 数据预处理
# ============================================================

class DataPreprocessor:
    """
    数据预处理器

    核心功能：
    1. 字段选择与排除
    2. 排序
    3. 过滤
    4. 嵌套展平
    5. 分页
    """

    @staticmethod
    def select_fields(records: List[Dict], fields: Optional[List[str]],
                      exclude: Optional[List[str]]) -> List[Dict]:
        """字段选择"""
        if fields is None and exclude is None:
            return records
        result = []
        for record in records:
            if not isinstance(record, dict):
                result.append(record)
                continue
            if fields:
                new_record = {k: record[k] for k in fields if k in record}
            else:
                new_record = {k: v for k, v in record.items()
                              if exclude is None or k not in exclude}
            result.append(new_record)
        return result

    @staticmethod
    def sort_records(records: List[Dict], sort_by: Optional[str],
                     desc: bool = False) -> List[Dict]:
        """排序"""
        if not sort_by or not records:
            return records
        return sorted(records, key=lambda r: r.get(sort_by, ""),
                       reverse=desc)

    @staticmethod
    def filter_records(records: List[Dict],
                       filter_fn: Optional[Callable[[Dict], bool]]) -> List[Dict]:
        """过滤"""
        if filter_fn is None:
            return records
        return [r for r in records if filter_fn(r)]

    @staticmethod
    def flatten_record(record: Dict, separator: str = ".",
                       prefix: str = "") -> Dict:
        """展平嵌套字典"""
        flat = {}
        for k, v in record.items():
            key = f"{prefix}{separator}{k}" if prefix else k
            if isinstance(v, dict):
                flat.update(DataPreprocessor.flatten_record(v, separator, key))
            elif isinstance(v, list):
                # 列表转为逗号分隔字符串
                if v and isinstance(v[0], (str, int, float)):
                    flat[key] = ",".join(str(x) for x in v)
                else:
                    flat[key] = json.dumps(v, ensure_ascii=False)
            else:
                flat[key] = v
        return flat

    @staticmethod
    def paginate(records: List[Dict], page: int, page_size: int) -> List[Dict]:
        """分页"""
        if page_size <= 0:
            return records
        start = (page - 1) * page_size
        return records[start:start + page_size]

    @staticmethod
    def preprocess(records: List[Dict], config: ExportConfig) -> List[Dict]:
        """完整预处理流程"""
        result = records

        # 展平嵌套
        if config.flatten_nested:
            result = [DataPreprocessor.flatten_record(r, config.nested_separator)
                      for r in result]

        # 过滤
        result = DataPreprocessor.filter_records(result, config.filter_fn)

        # 排序
        result = DataPreprocessor.sort_records(result, config.sort_by, config.sort_desc)

        # 字段选择
        result = DataPreprocessor.select_fields(result, config.fields, config.exclude_fields)

        # 分页
        result = DataPreprocessor.paginate(result, config.page, config.page_size)

        return result


# ============================================================
# 格式化器
# ============================================================

class JsonFormatter:
    """JSON格式化器"""

    @staticmethod
    def format(records: List[Dict], config: ExportConfig) -> str:
        return json.dumps(records, ensure_ascii=False, indent=config.indent)


class CsvFormatter:
    """CSV格式化器"""

    @staticmethod
    def format(records: List[Dict], config: ExportConfig) -> str:
        if not records:
            return ""
        output = io.StringIO()
        # 收集所有字段
        all_keys = []
        for record in records:
            for k in record.keys():
                if k not in all_keys:
                    all_keys.append(k)

        writer = csv.DictWriter(output, fieldnames=all_keys,
                                extrasaction="ignore")
        if config.include_header:
            writer.writeheader()
        for record in records:
            # 处理非字符串值
            row = {}
            for k, v in record.items():
                if isinstance(v, (list, dict)):
                    row[k] = json.dumps(v, ensure_ascii=False)
                else:
                    row[k] = v
            writer.writerow(row)
        return output.getvalue()


class MarkdownFormatter:
    """Markdown格式化器"""

    @staticmethod
    def format(records: List[Dict], config: ExportConfig) -> str:
        if not records:
            return ""
        lines = []
        keys = list(records[0].keys())

        # 表头
        if config.include_header:
            header = "| " + " | ".join(str(k) for k in keys) + " |"
            separator = "| " + " | ".join("---" for _ in keys) + " |"
            lines.append(header)
            lines.append(separator)

        # 数据行
        for record in records:
            row = "| " + " | ".join(
                str(record.get(k, "")) for k in keys
            ) + " |"
            lines.append(row)

        return "\n".join(lines)


class HtmlFormatter:
    """HTML格式化器"""

    @staticmethod
    def format(records: List[Dict], config: ExportConfig) -> str:
        if not records:
            return "<table></table>"
        keys = list(records[0].keys())

        lines = ["<table>", "<thead>", "<tr>"]
        if config.include_header:
            for k in keys:
                lines.append(f"<th>{k}</th>")
        lines.append("</tr>")
        lines.append("</thead>")
        lines.append("<tbody>")

        for record in records:
            lines.append("<tr>")
            for k in keys:
                val = record.get(k, "")
                # 转义HTML特殊字符
                val = str(val).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                lines.append(f"<td>{val}</td>")
            lines.append("</tr>")

        lines.extend(["</tbody>", "</table>"])
        return "\n".join(lines)


class TextFormatter:
    """纯文本格式化器"""

    @staticmethod
    def format(records: List[Dict], config: ExportConfig) -> str:
        if not records:
            return ""
        keys = list(records[0].keys())

        # 计算列宽
        col_widths = {}
        for k in keys:
            col_widths[k] = max(len(str(k)), max(
                len(str(r.get(k, ""))) for r in records
            ))

        lines = []
        # 表头
        if config.include_header:
            header = " | ".join(
                str(k).ljust(col_widths[k]) for k in keys
            )
            lines.append(header)
            lines.append("-+-".join("-" * col_widths[k] for k in keys))

        # 数据行
        for record in records:
            row = " | ".join(
                str(record.get(k, "")).ljust(col_widths[k]) for k in keys
            )
            lines.append(row)

        return "\n".join(lines)


# ============================================================
# 数据导出器
# ============================================================

class DataExporter:
    """
    数据导出器

    核心功能：
    1. 多格式导出（JSON/CSV/Markdown/HTML/Text）
    2. 数据预处理（字段选择、排序、过滤、分页）
    3. 导出到文件或字符串
    4. 异步导出任务管理
    5. 导出历史记录
    """

    def __init__(self, output_dir: str = ""):
        self._output_dir = output_dir
        self._formatters = {
            ExportFormat.JSON: JsonFormatter,
            ExportFormat.CSV: CsvFormatter,
            ExportFormat.MARKDOWN: MarkdownFormatter,
            ExportFormat.HTML: HtmlFormatter,
            ExportFormat.TEXT: TextFormatter,
        }
        self._tasks: Dict[str, ExportTask] = {}
        self._history: List[ExportHistory] = []
        self._lock = threading.RLock()
        self._total_exports = 0
        self._total_records = 0

    # ---- 同步导出 ----

    def export(self, data: Any, config: Optional[ExportConfig] = None) -> str:
        """
        导出数据到字符串

        Args:
            data: 数据源（字典列表、单个字典等）
            config: 导出配置

        Returns:
            格式化后的字符串
        """
        config = config or ExportConfig()
        records = self._normalize_data(data)
        records = DataPreprocessor.preprocess(records, config)

        formatter = self._formatters.get(config.format)
        if formatter is None:
            raise ValueError(f"Unsupported format: {config.format}")

        result = formatter.format(records, config)

        with self._lock:
            self._total_exports += 1
            self._total_records += len(records)

        return result

    def export_to_file(self, data: Any, file_path: str,
                       config: Optional[ExportConfig] = None) -> Dict[str, Any]:
        """
        导出数据到文件

        Returns:
            导出结果信息
        """
        config = config or ExportConfig()
        content = self.export(data, config)

        # 确保目录存在
        dir_path = os.path.dirname(file_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        with open(file_path, "w", encoding=config.encoding) as f:
            f.write(content)

        file_size = os.path.getsize(file_path)

        result = {
            "file_path": file_path,
            "format": config.format.value,
            "file_size": file_size,
            "encoding": config.encoding,
        }

        # 记录历史
        with self._lock:
            self._history.append(ExportHistory(
                task_id="",
                name=os.path.basename(file_path),
                format=config.format.value,
                status="completed",
                records=len(self._normalize_data(data)),
                file_size=file_size,
                output_path=file_path,
                created_at=time.time(),
            ))

        return result

    # ---- 异步导出 ----

    def submit_task(self, name: str, data: Any, file_path: str,
                    config: Optional[ExportConfig] = None) -> str:
        """
        提交异步导出任务

        Returns:
            任务ID
        """
        task = ExportTask(
            name=name,
            config=config or ExportConfig(),
            data_source=data,
            output_path=file_path,
            status=ExportStatus.PENDING,
        )

        with self._lock:
            self._tasks[task.id] = task

        # 在后台线程中执行
        thread = threading.Thread(
            target=self._execute_task,
            args=(task.id,),
            daemon=True,
        )
        thread.start()

        return task.id

    def _execute_task(self, task_id: str) -> None:
        """执行导出任务"""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task.status = ExportStatus.RUNNING
            task.started_at = time.time()

        try:
            records = self._normalize_data(task.data_source)
            task.total_records = len(records)

            content = self.export(task.data_source, task.config)

            dir_path = os.path.dirname(task.output_path)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)

            with open(task.output_path, "w", encoding=task.config.encoding) as f:
                f.write(content)

            with self._lock:
                task.status = ExportStatus.COMPLETED
                task.completed_at = time.time()
                task.exported_records = len(records)
                task.file_size = os.path.getsize(task.output_path)
                self._total_exports += 1
                self._total_records += len(records)

                self._history.append(ExportHistory(
                    task_id=task.id,
                    name=task.name,
                    format=task.config.format.value,
                    status="completed",
                    records=len(records),
                    file_size=task.file_size,
                    output_path=task.output_path,
                    created_at=task.created_at,
                    duration_ms=(task.completed_at - task.started_at) * 1000,
                ))

        except Exception as e:
            with self._lock:
                task.status = ExportStatus.FAILED
                task.completed_at = time.time()
                task.error = str(e)

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            return {
                "id": task.id,
                "name": task.name,
                "status": task.status.value,
                "total_records": task.total_records,
                "exported_records": task.exported_records,
                "file_size": task.file_size,
                "output_path": task.output_path,
                "error": task.error,
                "created_at": task.created_at,
                "completed_at": task.completed_at,
            }

    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        with self._lock:
            task = self._tasks.get(task_id)
            if task and task.status in (ExportStatus.PENDING, ExportStatus.RUNNING):
                task.status = ExportStatus.CANCELLED
                task.completed_at = time.time()
                return True
            return False

    # ---- 历史记录 ----

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取导出历史"""
        with self._lock:
            items = self._history[-limit:]
            return [
                {
                    "task_id": h.task_id,
                    "name": h.name,
                    "format": h.format,
                    "status": h.status,
                    "records": h.records,
                    "file_size": h.file_size,
                    "output_path": h.output_path,
                    "created_at": h.created_at,
                    "duration_ms": round(h.duration_ms, 2),
                }
                for h in reversed(items)
            ]

    def clear_history(self) -> int:
        """清除历史"""
        with self._lock:
            count = len(self._history)
            self._history.clear()
            return count

    # ---- 统计 ----

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "total_exports": self._total_exports,
                "total_records": self._total_records,
                "pending_tasks": sum(
                    1 for t in self._tasks.values()
                    if t.status in (ExportStatus.PENDING, ExportStatus.RUNNING)
                ),
                "history_count": len(self._history),
                "supported_formats": [f.value for f in ExportFormat],
            }

    # ---- 内部方法 ----

    @staticmethod
    def _normalize_data(data: Any) -> List[Dict]:
        """标准化数据为字典列表"""
        if isinstance(data, list):
            return [d if isinstance(d, dict) else {"value": d} for d in data]
        elif isinstance(data, dict):
            return [data]
        elif isinstance(data, (str, int, float, bool)):
            return [{"value": data}]
        else:
            return [{"value": str(data)}]


# ============================================================
# 全局单例
# ============================================================

_exporter: Optional[DataExporter] = None
_exporter_lock = threading.RLock()


def get_exporter() -> DataExporter:
    """获取全局数据导出器"""
    global _exporter
    if _exporter is None:
        with _exporter_lock:
            if _exporter is None:
                _exporter = DataExporter()
    return _exporter
