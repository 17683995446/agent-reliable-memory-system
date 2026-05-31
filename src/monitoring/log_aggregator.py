"""
日志聚合器 - 阶段197-199

功能：
- 阶段197: 结构化日志框架
- 阶段198: 日志分析与统计
- 阶段199: 日志查询与过滤

设计原则：
- 确定性规则，无模型依赖
- 最小层级，无循环依赖
- 线程安全，RLock保护
- 单例模式，全局唯一
"""

import threading
import time
import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Dict, List, Optional, Callable, Any, Set, Tuple, Iterator
from collections import deque, defaultdict
import uuid
import hashlib


class LogLevel(Enum):
    """日志级别"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    
    @classmethod
    def from_string(cls, level: str) -> "LogLevel":
        """从字符串创建"""
        level_map = {
            "debug": cls.DEBUG,
            "info": cls.INFO,
            "warning": cls.WARNING,
            "warn": cls.WARNING,
            "error": cls.ERROR,
            "critical": cls.CRITICAL,
            "fatal": cls.CRITICAL
        }
        return level_map.get(level.lower(), cls.INFO)
    
    @property
    def priority(self) -> int:
        """优先级数值"""
        priorities = {
            LogLevel.DEBUG: 10,
            LogLevel.INFO: 20,
            LogLevel.WARNING: 30,
            LogLevel.ERROR: 40,
            LogLevel.CRITICAL: 50
        }
        return priorities.get(self, 0)


class LogField(Enum):
    """标准日志字段"""
    TIMESTAMP = "timestamp"
    LEVEL = "level"
    MESSAGE = "message"
    LOGGER = "logger"
    MODULE = "module"
    FUNCTION = "function"
    LINE = "line"
    THREAD = "thread"
    TRACE_ID = "trace_id"
    SPAN_ID = "span_id"
    SOURCE = "source"
    HOST = "host"


@dataclass
class StructuredLogEntry:
    """结构化日志条目"""
    timestamp: float
    level: LogLevel
    message: str
    logger: str = ""
    module: str = ""
    function: str = ""
    line: int = 0
    thread_id: int = 0
    thread_name: str = ""
    trace_id: str = ""
    span_id: str = ""
    source: str = ""
    host: str = ""
    fields: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def log_id(self) -> str:
        """生成日志ID"""
        content = f"{self.timestamp}:{self.message}:{self.thread_id}"
        return hashlib.md5(content.encode()).hexdigest()[:16]
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "log_id": self.log_id,
            "timestamp": self.timestamp,
            "timestamp_iso": datetime.fromtimestamp(self.timestamp).isoformat(),
            "level": self.level.value,
            "message": self.message,
            "logger": self.logger,
            "module": self.module,
            "function": self.function,
            "line": self.line,
            "thread_id": self.thread_id,
            "thread_name": self.thread_name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "source": self.source,
            "host": self.host,
            "fields": self.fields
        }
    
    def to_json(self) -> str:
        """转换为JSON"""
        return json.dumps(self.to_dict(), ensure_ascii=False)
    
    def to_line(self, format: str = "simple") -> str:
        """转换为单行格式"""
        ts = datetime.fromtimestamp(self.timestamp).strftime("%Y-%m-%d %H:%M:%S")
        
        if format == "simple":
            return f"[{ts}] {self.level.value}: {self.message}"
        elif format == "detailed":
            location = f"{self.module}:{self.line}" if self.module else ""
            return f"[{ts}] {self.level.value} [{self.logger}] {location} - {self.message}"
        elif format == "json":
            return self.to_json()
        
        return self.message


@dataclass
class LogPattern:
    """日志模式"""
    pattern_id: str
    name: str
    regex: str
    level: Optional[LogLevel] = None
    category: str = ""
    description: str = ""
    compiled_regex: Any = field(default=None, repr=False)
    
    def __post_init__(self):
        if self.compiled_regex is None:
            try:
                self.compiled_regex = re.compile(self.regex)
            except re.error:
                self.compiled_regex = None
    
    def match(self, message: str) -> Optional[Dict[str, str]]:
        """匹配日志消息"""
        if not self.compiled_regex:
            return None
        
        match = self.compiled_regex.search(message)
        if match:
            return match.groupdict()
        return None


@dataclass
class LogStats:
    """日志统计"""
    total_count: int = 0
    level_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    source_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    logger_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    error_rate_1min: float = 0.0
    messages_per_second: float = 0.0
    unique_messages: int = 0
    time_range_start: Optional[float] = None
    time_range_end: Optional[float] = None


@dataclass
class LogQuery:
    """日志查询"""
    level_min: Optional[LogLevel] = None
    level_max: Optional[LogLevel] = None
    sources: Optional[List[str]] = None
    loggers: Optional[List[str]] = None
    modules: Optional[List[str]] = None
    message_contains: Optional[str] = None
    message_regex: Optional[str] = None
    trace_id: Optional[str] = None
    time_start: Optional[float] = None
    time_end: Optional[float] = None
    fields_match: Optional[Dict[str, Any]] = None
    limit: int = 1000


@dataclass
class LogQueryResult:
    """日志查询结果"""
    entries: List[StructuredLogEntry]
    total_matched: int
    query_time_ms: float
    has_more: bool


class LogAggregator:
    """
    日志聚合器
    
    阶段197: 结构化日志框架
    - 结构化日志条目
    - 上下文字段支持
    - 多格式输出（JSON/行格式）
    
    阶段198: 日志分析与统计
    - 日志级别统计
    - 来源分析
    - 错误率计算
    - 模式匹配
    
    阶段199: 日志查询与过滤
    - 多条件查询
    - 正则匹配
    - 时间范围过滤
    - 分页支持
    """
    
    _instance = None
    _lock = threading.RLock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        with self._lock:
            if self._initialized:
                return
            
            self._initialized = True
            
            # 日志存储
            self._logs: deque = deque(maxlen=100000)
            self._logs_by_level: Dict[LogLevel, deque] = {
                level: deque(maxlen=20000) for level in LogLevel
            }
            
            # 日志处理器
            self._handlers: List[Callable[[StructuredLogEntry], None]] = []
            
            # 日志模式
            self._patterns: Dict[str, LogPattern] = {}
            
            # 统计信息
            self._stats = LogStats()
            self._stats_window_seconds = 60
            self._message_hashes: deque = deque(maxlen=10000)
            
            # 配置
            self._min_level = LogLevel.DEBUG
            self._default_source = "application"
            self._default_host = "localhost"
            
            # 索引（用于快速查询）
            self._index_by_trace: Dict[str, List[str]] = defaultdict(list)
            self._index_by_logger: Dict[str, List[str]] = defaultdict(list)
            
            # 注册默认模式
            self._register_default_patterns()
    
    def _register_default_patterns(self):
        """注册默认日志模式"""
        patterns = [
            LogPattern(
                pattern_id="error_stacktrace",
                name="Error Stacktrace",
                regex=r"(?P<error_type>\w+Error):\s*(?P<error_message>.+)",
                level=LogLevel.ERROR,
                category="exception",
                description="Python异常堆栈"
            ),
            LogPattern(
                pattern_id="http_request",
                name="HTTP Request",
                regex=r"(?P<method>GET|POST|PUT|DELETE|PATCH)\s+(?P<path>/[^\s]*)\s+HTTP",
                category="http",
                description="HTTP请求"
            ),
            LogPattern(
                pattern_id="db_query",
                name="Database Query",
                regex=r"(?:SELECT|INSERT|UPDATE|DELETE)\s+.+",
                category="database",
                description="数据库查询"
            ),
            LogPattern(
                pattern_id="memory_warning",
                name="Memory Warning",
                regex=r"memory|MemoryError|out of memory",
                level=LogLevel.WARNING,
                category="resource",
                description="内存警告"
            )
        ]
        
        for pattern in patterns:
            self._patterns[pattern.pattern_id] = pattern
    
    # ========== 阶段197: 结构化日志框架 ==========
    
    def log(self, level: LogLevel, message: str,
            logger: str = "",
            module: str = "",
            function: str = "",
            line: int = 0,
            trace_id: str = "",
            span_id: str = "",
            source: str = "",
            host: str = "",
            **fields) -> StructuredLogEntry:
        """记录日志"""
        # 检查级别
        if level.priority < self._min_level.priority:
            return None
        
        # 获取当前线程信息
        current_thread = threading.current_thread()
        
        entry = StructuredLogEntry(
            timestamp=time.time(),
            level=level,
            message=message,
            logger=logger or self._default_source,
            module=module,
            function=function,
            line=line,
            thread_id=current_thread.ident or 0,
            thread_name=current_thread.name,
            trace_id=trace_id,
            span_id=span_id,
            source=source or self._default_source,
            host=host or self._default_host,
            fields=fields
        )
        
        with self._lock:
            # 存储日志
            self._logs.append(entry)
            self._logs_by_level[level].append(entry)
            
            # 更新索引
            if entry.trace_id:
                self._index_by_trace[entry.trace_id].append(entry.log_id)
            if entry.logger:
                self._index_by_logger[entry.logger].append(entry.log_id)
            
            # 更新统计
            self._update_stats(entry)
            
            # 调用处理器
            handlers = list(self._handlers)
        
        # 在锁外调用处理器
        for handler in handlers:
            try:
                handler(entry)
            except Exception:
                pass
        
        return entry
    
    def debug(self, message: str, **kwargs) -> StructuredLogEntry:
        """记录DEBUG日志"""
        return self.log(LogLevel.DEBUG, message, **kwargs)
    
    def info(self, message: str, **kwargs) -> StructuredLogEntry:
        """记录INFO日志"""
        return self.log(LogLevel.INFO, message, **kwargs)
    
    def warning(self, message: str, **kwargs) -> StructuredLogEntry:
        """记录WARNING日志"""
        return self.log(LogLevel.WARNING, message, **kwargs)
    
    def error(self, message: str, **kwargs) -> StructuredLogEntry:
        """记录ERROR日志"""
        return self.log(LogLevel.ERROR, message, **kwargs)
    
    def critical(self, message: str, **kwargs) -> StructuredLogEntry:
        """记录CRITICAL日志"""
        return self.log(LogLevel.CRITICAL, message, **kwargs)
    
    def exception(self, message: str, exc: Exception = None, **kwargs) -> StructuredLogEntry:
        """记录异常日志"""
        import traceback
        
        exc_info = traceback.format_exc() if exc is None else str(exc)
        kwargs["exception"] = exc_info
        kwargs["exception_type"] = type(exc).__name__ if exc else "Unknown"
        
        return self.log(LogLevel.ERROR, message, **kwargs)
    
    def add_handler(self, handler: Callable[[StructuredLogEntry], None]) -> None:
        """添加日志处理器"""
        with self._lock:
            self._handlers.append(handler)
    
    def remove_handler(self, handler: Callable[[StructuredLogEntry], None]) -> bool:
        """移除日志处理器"""
        with self._lock:
            if handler in self._handlers:
                self._handlers.remove(handler)
                return True
            return False
    
    def set_min_level(self, level: LogLevel) -> None:
        """设置最小日志级别"""
        with self._lock:
            self._min_level = level
    
    def _update_stats(self, entry: StructuredLogEntry) -> None:
        """更新统计信息"""
        self._stats.total_count += 1
        self._stats.level_counts[entry.level.value] += 1
        self._stats.source_counts[entry.source] += 1
        self._stats.logger_counts[entry.logger] += 1
        
        # 更新时间范围
        if self._stats.time_range_start is None:
            self._stats.time_range_start = entry.timestamp
        self._stats.time_range_end = entry.timestamp
        
        # 计算唯一消息数
        msg_hash = hashlib.md5(entry.message.encode()).hexdigest()[:16]
        if msg_hash not in self._message_hashes:
            self._message_hashes.append(msg_hash)
            self._stats.unique_messages = len(set(self._message_hashes))
    
    # ========== 阶段198: 日志分析与统计 ==========
    
    def get_stats(self) -> LogStats:
        """获取日志统计"""
        with self._lock:
            stats = LogStats(
                total_count=self._stats.total_count,
                level_counts=dict(self._stats.level_counts),
                source_counts=dict(self._stats.source_counts),
                logger_counts=dict(self._stats.logger_counts),
                unique_messages=self._stats.unique_messages,
                time_range_start=self._stats.time_range_start,
                time_range_end=self._stats.time_range_end
            )
        
        # 计算错误率（最近1分钟）
        now = time.time()
        one_minute_ago = now - 60
        
        error_count = 0
        total_count = 0
        
        with self._lock:
            for entry in reversed(self._logs):
                if entry.timestamp < one_minute_ago:
                    break
                total_count += 1
                if entry.level in (LogLevel.ERROR, LogLevel.CRITICAL):
                    error_count += 1
        
        if total_count > 0:
            stats.error_rate_1min = (error_count / total_count) * 100
        
        # 计算每秒消息数
        time_span = stats.time_range_end - stats.time_range_start if stats.time_range_end else 0
        if time_span > 0:
            stats.messages_per_second = stats.total_count / time_span
        
        return stats
    
    def analyze_patterns(self, entries: Optional[List[StructuredLogEntry]] = None) -> Dict[str, Any]:
        """分析日志模式"""
        if entries is None:
            with self._lock:
                entries = list(self._logs)
        
        pattern_matches = defaultdict(list)
        uncategorized = []
        
        for entry in entries:
            matched = False
            for pattern in self._patterns.values():
                match = pattern.match(entry.message)
                if match:
                    pattern_matches[pattern.name].append({
                        "entry": entry,
                        "groups": match
                    })
                    matched = True
                    break
            
            if not matched:
                uncategorized.append(entry)
        
        return {
            "pattern_matches": dict(pattern_matches),
            "uncategorized_count": len(uncategorized),
            "total_analyzed": len(entries)
        }
    
    def register_pattern(self, pattern: LogPattern) -> None:
        """注册日志模式"""
        with self._lock:
            self._patterns[pattern.pattern_id] = pattern
    
    def get_level_distribution(self, time_range_seconds: float = 3600) -> Dict[str, int]:
        """获取日志级别分布"""
        cutoff = time.time() - time_range_seconds
        
        with self._lock:
            distribution = defaultdict(int)
            for entry in self._logs:
                if entry.timestamp >= cutoff:
                    distribution[entry.level.value] += 1
            
            return dict(distribution)
    
    def get_top_loggers(self, n: int = 10) -> List[Tuple[str, int]]:
        """获取最活跃的logger"""
        with self._lock:
            return sorted(
                self._stats.logger_counts.items(),
                key=lambda x: x[1],
                reverse=True
            )[:n]
    
    def get_error_summary(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取错误摘要"""
        errors = []
        
        with self._lock:
            for entry in reversed(self._logs_by_level[LogLevel.ERROR]):
                errors.append({
                    "timestamp": entry.timestamp,
                    "message": entry.message,
                    "logger": entry.logger,
                    "module": entry.module,
                    "fields": entry.fields
                })
                if len(errors) >= limit:
                    break
        
        return errors
    
    # ========== 阶段199: 日志查询与过滤 ==========
    
    def query(self, query: LogQuery) -> LogQueryResult:
        """查询日志"""
        start_time = time.time()
        results = []
        total_matched = 0
        
        with self._lock:
            logs_to_search = list(self._logs)
        
        # 编译正则表达式
        message_regex = None
        if query.message_regex:
            try:
                message_regex = re.compile(query.message_regex)
            except re.error:
                pass
        
        for entry in reversed(logs_to_search):  # 从新到旧
            # 时间范围过滤
            if query.time_start and entry.timestamp < query.time_start:
                continue
            if query.time_end and entry.timestamp > query.time_end:
                continue
            
            # 级别过滤
            if query.level_min and entry.level.priority < query.level_min.priority:
                continue
            if query.level_max and entry.level.priority > query.level_max.priority:
                continue
            
            # 来源过滤
            if query.sources and entry.source not in query.sources:
                continue
            
            # Logger过滤
            if query.loggers and entry.logger not in query.loggers:
                continue
            
            # 模块过滤
            if query.modules and entry.module not in query.modules:
                continue
            
            # 消息内容过滤
            if query.message_contains and query.message_contains not in entry.message:
                continue
            
            # 正则匹配
            if message_regex and not message_regex.search(entry.message):
                continue
            
            # Trace ID过滤
            if query.trace_id and entry.trace_id != query.trace_id:
                continue
            
            # 字段匹配
            if query.fields_match:
                match = True
                for key, value in query.fields_match.items():
                    if entry.fields.get(key) != value:
                        match = False
                        break
                if not match:
                    continue
            
            total_matched += 1
            
            if len(results) < query.limit:
                results.append(entry)
        
        query_time = (time.time() - start_time) * 1000
        
        return LogQueryResult(
            entries=results,
            total_matched=total_matched,
            query_time_ms=query_time,
            has_more=total_matched > query.limit
        )
    
    def search(self, keyword: str, limit: int = 100) -> LogQueryResult:
        """简单关键词搜索"""
        return self.query(LogQuery(
            message_contains=keyword,
            limit=limit
        ))
    
    def get_by_trace_id(self, trace_id: str) -> List[StructuredLogEntry]:
        """通过Trace ID获取日志"""
        with self._lock:
            log_ids = self._index_by_trace.get(trace_id, [])
            
            # 从存储中查找
            entries = []
            for entry in self._logs:
                if entry.log_id in log_ids or entry.trace_id == trace_id:
                    entries.append(entry)
            
            return sorted(entries, key=lambda e: e.timestamp)
    
    def get_by_logger(self, logger: str, limit: int = 100) -> List[StructuredLogEntry]:
        """通过Logger获取日志"""
        with self._lock:
            entries = []
            for entry in reversed(self._logs):
                if entry.logger == logger:
                    entries.append(entry)
                    if len(entries) >= limit:
                        break
            return list(reversed(entries))
    
    def tail(self, n: int = 100, level: Optional[LogLevel] = None) -> List[StructuredLogEntry]:
        """获取最近的日志"""
        with self._lock:
            if level:
                logs = self._logs_by_level.get(level, deque())
            else:
                logs = self._logs
            
            return list(logs)[-n:]
    
    def export_logs(self, format: str = "json",
                    query: Optional[LogQuery] = None) -> str:
        """导出日志"""
        if query:
            result = self.query(query)
            entries = result.entries
        else:
            with self._lock:
                entries = list(self._logs)
        
        if format == "json":
            data = [entry.to_dict() for entry in entries]
            return json.dumps(data, indent=2, ensure_ascii=False)
        
        elif format == "jsonl":
            lines = [entry.to_json() for entry in entries]
            return "\n".join(lines)
        
        elif format == "csv":
            lines = ["timestamp,level,logger,message"]
            for entry in entries:
                ts = datetime.fromtimestamp(entry.timestamp).isoformat()
                msg = entry.message.replace('"', '""')
                lines.append(f'"{ts}","{entry.level.value}","{entry.logger}","{msg}"')
            return "\n".join(lines)
        
        elif format == "lines":
            return "\n".join(entry.to_line() for entry in entries)
        
        return ""
    
    def clear(self) -> None:
        """清空日志"""
        with self._lock:
            self._logs.clear()
            for level_logs in self._logs_by_level.values():
                level_logs.clear()
            self._index_by_trace.clear()
            self._index_by_logger.clear()
            self._message_hashes.clear()
            self._stats = LogStats()
    
    def get_buffer_size(self) -> int:
        """获取缓冲区大小"""
        with self._lock:
            return len(self._logs)


# 全局单例
_log_aggregator_instance: Optional[LogAggregator] = None
_log_aggregator_lock = threading.RLock()


def get_log_aggregator() -> LogAggregator:
    """获取日志聚合器全局实例"""
    global _log_aggregator_instance
    if _log_aggregator_instance is None:
        with _log_aggregator_lock:
            if _log_aggregator_instance is None:
                _log_aggregator_instance = LogAggregator()
    return _log_aggregator_instance


# 便捷函数
def debug(message: str, **kwargs):
    """记录DEBUG日志"""
    return get_log_aggregator().debug(message, **kwargs)


def info(message: str, **kwargs):
    """记录INFO日志"""
    return get_log_aggregator().info(message, **kwargs)


def warning(message: str, **kwargs):
    """记录WARNING日志"""
    return get_log_aggregator().warning(message, **kwargs)


def error(message: str, **kwargs):
    """记录ERROR日志"""
    return get_log_aggregator().error(message, **kwargs)


def critical(message: str, **kwargs):
    """记录CRITICAL日志"""
    return get_log_aggregator().critical(message, **kwargs)


def exception(message: str, exc: Exception = None, **kwargs):
    """记录异常日志"""
    return get_log_aggregator().exception(message, exc, **kwargs)
