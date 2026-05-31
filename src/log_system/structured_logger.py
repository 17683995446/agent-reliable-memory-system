#!/usr/bin/env python3
"""
结构化日志记录器 (StructuredLogger) - 阶段331

职责：
- 多级别日志：DEBUG/INFO/WARN/ERROR/FATAL
- 结构化记录：每条日志为字典，支持任意字段
- 上下文注入：自动附加trace_id、module、timestamp等
- 输出路由：支持多个输出通道（console/file/callback）
- 日志过滤：按级别、模块、标签过滤

设计原则：
- 确定性规则，无模型依赖
- 线程安全（RLock）
- 最小层级，无循环依赖
"""

import threading
import time
import traceback
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set


# ============================================================
# 枚举与数据结构
# ============================================================

class LogLevel(Enum):
    """日志级别"""
    DEBUG = 0
    INFO = 1
    WARN = 2
    ERROR = 3
    FATAL = 4


@dataclass
class LogRecord:
    """结构化日志记录"""
    timestamp: float = 0.0
    level: LogLevel = LogLevel.INFO
    message: str = ""
    module: str = ""
    logger_name: str = "root"
    trace_id: str = ""
    span_id: str = ""
    tags: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    error_type: Optional[str] = None
    stack_trace: Optional[str] = None
    source_file: str = ""
    source_line: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "timestamp": self.timestamp,
            "level": self.level.name,
            "message": self.message,
            "module": self.module,
            "logger": self.logger_name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "tags": self.tags,
            "context": self.context,
            "error": self.error,
            "error_type": self.error_type,
            "source": f"{self.source_file}:{self.source_line}" if self.source_file else "",
            **self.extra,
        }


@dataclass
class LogFilter:
    """日志过滤器"""
    min_level: Optional[LogLevel] = None
    modules: Optional[Set[str]] = None
    tags: Optional[Set[str]] = None
    exclude_modules: Optional[Set[str]] = None
    custom: Optional[Callable[[LogRecord], bool]] = None


# ============================================================
# 输出通道
# ============================================================

class OutputChannel:
    """输出通道基类"""

    def __init__(self, name: str = "default"):
        self.name = name
        self._enabled = True

    def write(self, record: LogRecord) -> None:
        """写入日志记录"""
        if not self._enabled:
            return
        self._do_write(record)

    def _do_write(self, record: LogRecord) -> None:
        raise NotImplementedError

    def flush(self) -> None:
        """刷新缓冲"""
        pass

    def close(self) -> None:
        """关闭通道"""
        self._enabled = False

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False


class CallbackChannel(OutputChannel):
    """回调输出通道"""

    def __init__(self, callback: Callable[[LogRecord], None], name: str = "callback"):
        super().__init__(name)
        self._callback = callback

    def _do_write(self, record: LogRecord) -> None:
        try:
            self._callback(record)
        except Exception:
            pass


class MemoryChannel(OutputChannel):
    """内存输出通道（用于测试和查询）"""

    def __init__(self, max_size: int = 1000, name: str = "memory"):
        super().__init__(name)
        self._records: deque = deque(maxlen=max_size)

    def _do_write(self, record: LogRecord) -> None:
        self._records.append(record)

    def get_records(self, limit: int = 100) -> List[LogRecord]:
        return list(self._records)[-limit:]

    def clear(self) -> int:
        count = len(self._records)
        self._records.clear()
        return count

    @property
    def size(self) -> int:
        return len(self._records)


# ============================================================
# 结构化日志记录器
# ============================================================

class StructuredLogger:
    """
    结构化日志记录器

    核心功能：
    1. 多级别日志记录（DEBUG/INFO/WARN/ERROR/FATAL）
    2. 结构化日志字段（字典形式）
    3. 自动上下文注入（trace_id、module、timestamp）
    4. 多输出通道路由
    5. 日志过滤
    6. 全局/局部上下文管理
    """

    def __init__(self, name: str = "root"):
        self.name = name
        self._channels: List[OutputChannel] = []
        self._filters: List[LogFilter] = []
        self._global_context: Dict[str, Any] = {}
        self._local_context: Dict[str, Any] = {}
        self._lock = threading.RLock()
        self._min_level = LogLevel.DEBUG
        self._total_logged = 0
        self._level_counts: Dict[LogLevel, int] = {l: 0 for l in LogLevel}

    # ---- 日志记录 ----

    def debug(self, message: str, **kwargs) -> None:
        self._log(LogLevel.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs) -> None:
        self._log(LogLevel.INFO, message, **kwargs)

    def warn(self, message: str, **kwargs) -> None:
        self._log(LogLevel.WARN, message, **kwargs)

    def error(self, message: str, error: Any = None, **kwargs) -> None:
        self._log(LogLevel.ERROR, message, error=error, **kwargs)

    def fatal(self, message: str, error: Any = None, **kwargs) -> None:
        self._log(LogLevel.FATAL, message, error=error, **kwargs)

    def log(self, level: LogLevel, message: str, **kwargs) -> None:
        """通用日志方法"""
        self._log(level, message, **kwargs)

    # ---- 上下文管理 ----

    def set_global_context(self, **kwargs) -> None:
        """设置全局上下文"""
        with self._lock:
            self._global_context.update(kwargs)

    def clear_global_context(self, keys: Optional[List[str]] = None) -> None:
        """清除全局上下文"""
        with self._lock:
            if keys:
                for k in keys:
                    self._global_context.pop(k, None)
            else:
                self._global_context.clear()

    def set_local_context(self, **kwargs) -> None:
        """设置局部上下文"""
        with self._lock:
            self._local_context.update(kwargs)

    def clear_local_context(self) -> None:
        """清除局部上下文"""
        with self._lock:
            self._local_context.clear()

    # ---- 通道管理 ----

    def add_channel(self, channel: OutputChannel) -> None:
        """添加输出通道"""
        with self._lock:
            self._channels.append(channel)

    def remove_channel(self, name: str) -> bool:
        """移除输出通道"""
        with self._lock:
            for i, ch in enumerate(self._channels):
                if ch.name == name:
                    self._channels.pop(i)
                    return True
            return False

    def get_channel(self, name: str) -> Optional[OutputChannel]:
        """获取输出通道"""
        with self._lock:
            for ch in self._channels:
                if ch.name == name:
                    return ch
            return None

    def list_channels(self) -> List[str]:
        """列出所有通道名称"""
        with self._lock:
            return [ch.name for ch in self._channels]

    # ---- 过滤器 ----

    def add_filter(self, f: LogFilter) -> None:
        """添加过滤器"""
        with self._lock:
            self._filters.append(f)

    def clear_filters(self) -> None:
        """清除所有过滤器"""
        with self._lock:
            self._filters.clear()

    def set_min_level(self, level: LogLevel) -> None:
        """设置最低日志级别"""
        self._min_level = level

    # ---- 统计 ----

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                "logger_name": self.name,
                "total_logged": self._total_logged,
                "level_counts": {l.name: c for l, c in self._level_counts.items()},
                "channels": len(self._channels),
                "filters": len(self._filters),
                "global_context_keys": list(self._global_context.keys()),
            }

    def reset_stats(self) -> None:
        """重置统计"""
        with self._lock:
            self._total_logged = 0
            self._level_counts = {l: 0 for l in LogLevel}

    # ---- 内部方法 ----

    def _log(self, level: LogLevel, message: str, **kwargs) -> None:
        """内部日志记录方法"""
        if level.value < self._min_level.value:
            return

        # 构建日志记录
        record = LogRecord(
            level=level,
            message=message,
            logger_name=self.name,
            module=kwargs.pop("module", ""),
            trace_id=kwargs.pop("trace_id", self._global_context.get("trace_id", "")),
            span_id=kwargs.pop("span_id", self._global_context.get("span_id", "")),
            tags=kwargs.pop("tags", []),
            context=dict(self._global_context),
            extra=kwargs,
        )

        # 错误处理
        error = kwargs.pop("error", None)
        if error is not None:
            record.error = str(error)
            record.error_type = type(error).__name__
            record.stack_trace = traceback.format_exc() if isinstance(error, Exception) else None

        # 合并局部上下文
        with self._lock:
            record.context.update(self._local_context)
            channels = list(self._channels)
            filters = list(self._filters)

        # 过滤
        for f in filters:
            if not self._matches_filter(record, f):
                return

        # 更新统计
        with self._lock:
            self._total_logged += 1
            self._level_counts[level] = self._level_counts.get(level, 0) + 1

        # 输出到所有通道
        for channel in channels:
            channel.write(record)

    def _matches_filter(self, record: LogRecord, f: LogFilter) -> bool:
        """检查记录是否匹配过滤器"""
        if f.min_level and record.level.value < f.min_level.value:
            return False
        if f.modules and record.module not in f.modules:
            return False
        if f.exclude_modules and record.module in f.exclude_modules:
            return False
        if f.tags and not (set(record.tags) & f.tags):
            return False
        if f.custom and not f.custom(record):
            return False
        return True


# ============================================================
# 日志管理器（多Logger管理）
# ============================================================

class LogManager:
    """日志管理器"""

    def __init__(self):
        self._loggers: Dict[str, StructuredLogger] = {}
        self._lock = threading.RLock()
        self._root_logger: Optional[StructuredLogger] = None

    def get_logger(self, name: str = "root") -> StructuredLogger:
        """获取或创建日志记录器"""
        with self._lock:
            if name not in self._loggers:
                self._loggers[name] = StructuredLogger(name)
            if name == "root" and self._root_logger is None:
                self._root_logger = self._loggers[name]
            return self._loggers[name]

    @property
    def root(self) -> StructuredLogger:
        """获取根日志记录器"""
        return self.get_logger("root")

    def list_loggers(self) -> List[str]:
        """列出所有日志记录器"""
        with self._lock:
            return list(self._loggers.keys())

    def get_stats(self) -> Dict[str, Any]:
        """获取所有日志记录器的统计"""
        with self._lock:
            return {
                "total_loggers": len(self._loggers),
                "loggers": {name: lg.get_stats() for name, lg in self._loggers.items()},
            }


# ============================================================
# 全局单例
# ============================================================

_log_manager: Optional[LogManager] = None
_mgr_lock = threading.RLock()


def get_log_manager() -> LogManager:
    """获取全局日志管理器（双重检查锁定）"""
    global _log_manager
    if _log_manager is None:
        with _mgr_lock:
            if _log_manager is None:
                _log_manager = LogManager()
    return _log_manager


def get_logger(name: str = "root") -> StructuredLogger:
    """便捷方法：获取日志记录器"""
    return get_log_manager().get_logger(name)
