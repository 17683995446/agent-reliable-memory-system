#!/usr/bin/env python3
"""
日志格式化器 (LogFormatter) - 阶段332

职责：
- JSON格式化：结构化JSON输出
- 文本格式化：人类可读的文本格式
- 彩色输出：ANSI颜色标记不同级别
- 模板引擎：自定义输出模板
- 字段过滤：选择输出哪些字段

设计原则：
- 确定性规则，无模型依赖
- 线程安全（RLock）
- 最小层级，无循环依赖
"""

import json
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set

from log_system.structured_logger import (
    LogLevel, LogRecord, OutputChannel
)


# ============================================================
# ANSI颜色
# ============================================================

class Color:
    """ANSI颜色代码"""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    GRAY = "\033[90m"

    @staticmethod
    def disable():
        """禁用颜色（设置环境变量）"""
        import os
        os.environ["NO_COLOR"] = "1"


# 级别颜色映射
LEVEL_COLORS = {
    LogLevel.DEBUG: Color.CYAN,
    LogLevel.INFO: Color.GREEN,
    LogLevel.WARN: Color.YELLOW,
    LogLevel.ERROR: Color.RED,
    LogLevel.FATAL: Color.BOLD + Color.RED,
}


# ============================================================
# 格式化器基类
# ============================================================

class BaseFormatter:
    """格式化器基类"""

    def __init__(self, include_fields: Optional[Set[str]] = None,
                 exclude_fields: Optional[Set[str]] = None):
        self._include = include_fields
        self._exclude = exclude_fields or set()

    def format(self, record: LogRecord) -> str:
        """格式化日志记录"""
        raise NotImplementedError

    def filter_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """过滤字段"""
        if self._include:
            return {k: v for k, v in data.items() if k in self._include}
        return {k: v for k, v in data.items() if k not in self._exclude}


# ============================================================
# JSON格式化器
# ============================================================

class JsonFormatter(BaseFormatter):
    """JSON格式化器"""

    def __init__(self, pretty: bool = False, ensure_ascii: bool = False,
                 include_fields: Optional[Set[str]] = None,
                 exclude_fields: Optional[Set[str]] = None):
        super().__init__(include_fields, exclude_fields)
        self._pretty = pretty
        self._ensure_ascii = ensure_ascii

    def format(self, record: LogRecord) -> str:
        data = record.to_dict()
        data = self.filter_fields(data)
        indent = 2 if self._pretty else None
        return json.dumps(data, indent=indent, ensure_ascii=self._ensure_ascii, default=str)


# ============================================================
# 文本格式化器
# ============================================================

class TextFormatter(BaseFormatter):
    """文本格式化器"""

    def __init__(self, template: str = "{timestamp} [{level}] {message}",
                 date_format: str = "%Y-%m-%d %H:%M:%S",
                 include_fields: Optional[Set[str]] = None,
                 exclude_fields: Optional[Set[str]] = None,
                 show_context: bool = False):
        super().__init__(include_fields, exclude_fields)
        self._template = template
        self._date_format = date_format
        self._show_context = show_context

    def format(self, record: LogRecord) -> str:
        dt = datetime.fromtimestamp(record.timestamp).strftime(self._date_format)
        values = {
            "timestamp": dt,
            "level": record.level.name,
            "message": record.message,
            "module": record.module,
            "logger": record.logger_name,
            "trace_id": record.trace_id,
            "span_id": record.span_id,
            "error": record.error or "",
            "error_type": record.error_type or "",
        }

        result = self._template.format(**values)

        if self._show_context and record.context:
            ctx_parts = [f"{k}={v}" for k, v in record.context.items()]
            if ctx_parts:
                result += " | " + " ".join(ctx_parts)

        if record.extra:
            extra_parts = [f"{k}={v}" for k, v in record.extra.items()]
            if extra_parts:
                result += " | " + " ".join(extra_parts)

        return result


# ============================================================
# 彩色格式化器
# ============================================================

class ColorFormatter(BaseFormatter):
    """彩色格式化器"""

    def __init__(self, template: str = "{timestamp} {level:>5} {module:>12} | {message}",
                 date_format: str = "%H:%M:%S",
                 include_fields: Optional[Set[str]] = None,
                 exclude_fields: Optional[Set[str]] = None,
                 color_enabled: bool = True):
        super().__init__(include_fields, exclude_fields)
        self._template = template
        self._date_format = date_format
        self._color_enabled = color_enabled and not self._is_no_color()

    def format(self, record: LogRecord) -> str:
        dt = datetime.fromtimestamp(record.timestamp).strftime(self._date_format)
        level_str = record.level.name
        color = LEVEL_COLORS.get(record.level, Color.WHITE)

        if self._color_enabled:
            level_str = f"{color}{level_str:<5}{Color.RESET}"

        values = {
            "timestamp": dt,
            "level": level_str,
            "message": record.message,
            "module": record.module or "",
            "logger": record.logger_name,
            "trace_id": record.trace_id or "",
            "span_id": record.span_id or "",
        }

        result = self._template.format(**values)

        if record.error:
            if self._color_enabled:
                result += f"\n{Color.RED}  Error: {record.error}{Color.RESET}"
            else:
                result += f"\n  Error: {record.error}"

        return result

    @staticmethod
    def _is_no_color() -> bool:
        import os
        return os.environ.get("NO_COLOR", "") != ""


# ============================================================
# 模板格式化器
# ============================================================

class TemplateFormatter(BaseFormatter):
    """模板格式化器"""

    def __init__(self, template: str, date_format: str = "%Y-%m-%d %H:%M:%S",
                 include_fields: Optional[Set[str]] = None,
                 exclude_fields: Optional[Set[str]] = None):
        super().__init__(include_fields, exclude_fields)
        self._template = template
        self._date_format = date_format

    def format(self, record: LogRecord) -> str:
        dt = datetime.fromtimestamp(record.timestamp).strftime(self._date_format)
        data = record.to_dict()
        data["timestamp"] = dt
        data = self.filter_fields(data)

        try:
            return self._template.format(**data)
        except KeyError as e:
            return f"[Template Error: missing field {e}] {record.message}"


# ============================================================
# 格式化输出通道
# ============================================================

class ConsoleChannel(OutputChannel):
    """控制台输出通道"""

    def __init__(self, formatter: Optional[BaseFormatter] = None,
                 color: bool = True, name: str = "console"):
        super().__init__(name)
        self._formatter = formatter or ColorFormatter(color_enabled=color)
        self._color = color

    def _do_write(self, record: LogRecord) -> None:
        output = self._formatter.format(record)
        print(output)

    def set_formatter(self, formatter: BaseFormatter) -> None:
        self._formatter = formatter


class FileChannel(OutputChannel):
    """文件输出通道"""

    def __init__(self, path: str, formatter: Optional[BaseFormatter] = None,
                 name: str = "file"):
        super().__init__(name)
        self._path = path
        self._formatter = formatter or JsonFormatter()
        self._file = None
        self._lock = threading.RLock()
        self._open()

    def _open(self) -> None:
        import os
        os.makedirs(os.path.dirname(self._path) if os.path.dirname(self._path) else ".", exist_ok=True)
        self._file = open(self._path, 'a', encoding='utf-8')

    def _do_write(self, record: LogRecord) -> None:
        with self._lock:
            if self._file:
                line = self._formatter.format(record)
                self._file.write(line + "\n")
                self._file.flush()

    def flush(self) -> None:
        with self._lock:
            if self._file:
                self._file.flush()

    def close(self) -> None:
        with self._lock:
            if self._file:
                self._file.close()
                self._file = None
        super().close()

    def set_formatter(self, formatter: BaseFormatter) -> None:
        self._formatter = formatter


# ============================================================
# 全局单例
# ============================================================

_log_formatter: Optional[BaseFormatter] = None
_formatter_lock = threading.RLock()


def get_default_formatter(color: bool = True) -> BaseFormatter:
    """获取默认格式化器"""
    global _log_formatter
    if _log_formatter is None:
        with _formatter_lock:
            if _log_formatter is None:
                _log_formatter = ColorFormatter(color_enabled=color)
    return _log_formatter
