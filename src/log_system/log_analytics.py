#!/usr/bin/env python3
"""
日志分析器 (LogAnalytics) - 阶段335

职责：
- 日志查询：按级别、模块、时间范围、关键词搜索
- 统计聚合：级别分布、模块分布、时间趋势
- 异常检测：错误率飙升、异常模式识别
- 报告生成：摘要报告、趋势分析

设计原则：
- 确定性规则，无模型依赖
- 线程安全（RLock）
- 最小层级，无循环依赖
"""

import re
import threading
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from log_system.structured_logger import (
    LogLevel, LogRecord, MemoryChannel
)
from log_system.log_aggregator import LogAggregator


# ============================================================
# 枚举与数据结构
# ============================================================

class AnomalyType(Enum):
    """异常类型"""
    ERROR_SPIKE = "error_spike"           # 错误率飙升
    UNUSUAL_MODULE = "unusual_module"     # 异常模块
    HIGH_FREQUENCY = "high_frequency"     # 高频日志
    NEW_ERROR = "new_error"               # 新错误类型


@dataclass
class QueryParams:
    """查询参数"""
    min_level: Optional[LogLevel] = None
    max_level: Optional[LogLevel] = None
    modules: Optional[List[str]] = None
    exclude_modules: Optional[List[str]] = None
    keywords: Optional[List[str]] = None
    trace_id: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    tags: Optional[List[str]] = None
    has_error: Optional[bool] = None
    limit: int = 100


@dataclass
class QueryResult:
    """查询结果"""
    records: List[LogRecord]
    total_matched: int = 0
    query_time_ms: float = 0.0


@dataclass
class LevelStats:
    """级别统计"""
    level: str
    count: int = 0
    percentage: float = 0.0


@dataclass
class AnomalyEvent:
    """异常事件"""
    anomaly_type: AnomalyType
    message: str
    timestamp: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)
    severity: str = "medium"

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


@dataclass
class AnalyticsReport:
    """分析报告"""
    total_records: int = 0
    time_range: Tuple[float, float] = (0.0, 0.0)
    level_distribution: List[LevelStats] = field(default_factory=list)
    module_distribution: Dict[str, int] = field(default_factory=dict)
    top_errors: List[Dict[str, Any]] = field(default_factory=list)
    anomalies: List[AnomalyEvent] = field(default_factory=list)
    error_rate: float = 0.0
    generated_at: float = 0.0

    def __post_init__(self):
        if self.generated_at == 0.0:
            self.generated_at = time.time()


# ============================================================
# 日志分析器
# ============================================================

class LogAnalytics:
    """
    日志分析器

    核心功能：
    1. 多维度日志查询
    2. 统计聚合（级别/模块/时间分布）
    3. 异常检测（错误率飙升、新错误类型）
    4. 分析报告生成
    5. 关键词搜索
    6. 趋势分析
    """

    def __init__(self, source: Optional[MemoryChannel] = None):
        self._source = source or MemoryChannel(max_size=10000)
        self._anomalies: deque = deque(maxlen=500)
        self._error_patterns: set = set()
        self._lock = threading.RLock()
        self._alert_callbacks: List[Callable[[AnomalyEvent], None]] = []

    # ---- 数据摄入 ----

    def ingest(self, record: LogRecord) -> None:
        """摄入日志记录"""
        self._source.write(record)

        # 异常检测
        if record.level.value >= LogLevel.ERROR.value:
            self._check_new_error(record)

    def ingest_batch(self, records: List[LogRecord]) -> int:
        """批量摄入"""
        for r in records:
            self.ingest(r)
        return len(records)

    def set_source(self, source: MemoryChannel) -> None:
        """设置数据源"""
        self._source = source

    # ---- 查询 ----

    def query(self, params: QueryParams) -> QueryResult:
        """
        查询日志

        Args:
            params: 查询参数

        Returns:
            查询结果
        """
        start = time.monotonic()
        all_records = self._source.get_records(limit=0)  # 获取全部
        matched = []

        for record in all_records:
            if not self._matches(record, params):
                continue
            matched.append(record)

            if len(matched) >= params.limit:
                break

        duration = (time.monotonic() - start) * 1000
        return QueryResult(
            records=matched,
            total_matched=len(matched),
            query_time_ms=duration,
        )

    def search(self, keyword: str, limit: int = 50) -> List[LogRecord]:
        """关键词搜索"""
        params = QueryParams(keywords=[keyword], limit=limit)
        return self.query(params).records

    def get_errors(self, limit: int = 50) -> List[LogRecord]:
        """获取所有错误日志"""
        params = QueryParams(min_level=LogLevel.ERROR, limit=limit)
        return self.query(params).records

    def get_by_trace(self, trace_id: str) -> List[LogRecord]:
        """按trace_id查询"""
        params = QueryParams(trace_id=trace_id, limit=1000)
        return self.query(params).records

    def get_by_module(self, module: str, limit: int = 50) -> List[LogRecord]:
        """按模块查询"""
        params = QueryParams(modules=[module], limit=limit)
        return self.query(params).records

    def get_by_time_range(self, start: float, end: float,
                          limit: int = 100) -> List[LogRecord]:
        """按时间范围查询"""
        params = QueryParams(start_time=start, end_time=end, limit=limit)
        return self.query(params).records

    # ---- 统计 ----

    def get_level_distribution(self) -> List[LevelStats]:
        """获取级别分布"""
        records = self._source.get_records(limit=0)
        total = len(records)
        if total == 0:
            return []

        counter = Counter(r.level.name for r in records)
        return [
            LevelStats(
                level=name,
                count=count,
                percentage=round(count / total * 100, 2),
            )
            for name, count in counter.most_common()
        ]

    def get_module_distribution(self, limit: int = 20) -> Dict[str, int]:
        """获取模块分布"""
        records = self._source.get_records(limit=0)
        counter = Counter(r.module for r in records if r.module)
        return dict(counter.most_common(limit))

    def get_error_rate(self) -> float:
        """获取错误率"""
        records = self._source.get_records(limit=0)
        if not records:
            return 0.0
        errors = sum(1 for r in records if r.level.value >= LogLevel.ERROR.value)
        return round(errors / len(records) * 100, 2)

    def get_time_series(self, bucket_seconds: int = 60) -> List[Dict[str, Any]]:
        """
        获取时间序列数据

        Args:
            bucket_seconds: 时间桶大小（秒）

        Returns:
            时间序列数据
        """
        records = self._source.get_records(limit=0)
        if not records:
            return []

        buckets: Dict[int, Dict[str, int]] = defaultdict(
            lambda: {"total": 0, "errors": 0}
        )

        for r in records:
            bucket_key = int(r.timestamp) // bucket_seconds
            buckets[bucket_key]["total"] += 1
            if r.level.value >= LogLevel.ERROR.value:
                buckets[bucket_key]["errors"] += 1

        result = []
        for key in sorted(buckets.keys()):
            data = buckets[key]
            result.append({
                "time": key * bucket_seconds,
                "total": data["total"],
                "errors": data["errors"],
            })

        return result

    # ---- 异常检测 ----

    def detect_anomalies(self) -> List[AnomalyEvent]:
        """检测异常"""
        anomalies = []

        # 错误率飙升检测
        spike = self._detect_error_spike()
        if spike:
            anomalies.append(spike)

        return anomalies

    def get_anomalies(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取异常事件"""
        with self._lock:
            return [
                {
                    "type": a.anomaly_type.value,
                    "message": a.message,
                    "timestamp": a.timestamp,
                    "severity": a.severity,
                    "details": a.details,
                }
                for a in list(self._anomalies)[-limit:]
            ]

    def on_anomaly(self, callback: Callable[[AnomalyEvent], None]) -> None:
        """添加异常回调"""
        with self._lock:
            self._alert_callbacks.append(callback)

    # ---- 报告 ----

    def generate_report(self) -> AnalyticsReport:
        """生成分析报告"""
        records = self._source.get_records(limit=0)

        if not records:
            return AnalyticsReport()

        time_range = (
            min(r.timestamp for r in records),
            max(r.timestamp for r in records),
        )

        level_dist = self.get_level_distribution()
        module_dist = self.get_module_distribution()
        top_errors = self._get_top_errors(10)
        anomalies = self.detect_anomalies()

        return AnalyticsReport(
            total_records=len(records),
            time_range=time_range,
            level_distribution=level_dist,
            module_distribution=module_dist,
            top_errors=top_errors,
            anomalies=anomalies,
            error_rate=self.get_error_rate(),
        )

    # ---- 统计 ----

    def get_stats(self) -> Dict[str, Any]:
        """获取分析器统计"""
        return {
            "stored_records": self._source.size,
            "known_error_patterns": len(self._error_patterns),
            "anomalies_detected": len(self._anomalies),
            "alert_callbacks": len(self._alert_callbacks),
        }

    def clear(self) -> int:
        """清除数据"""
        count = self._source.clear()
        with self._lock:
            self._error_patterns.clear()
            self._anomalies.clear()
        return count

    # ---- 内部方法 ----

    def _matches(self, record: LogRecord, params: QueryParams) -> bool:
        """检查记录是否匹配查询参数"""
        if params.min_level and record.level.value < params.min_level.value:
            return False
        if params.max_level and record.level.value > params.max_level.value:
            return False
        if params.modules and record.module not in params.modules:
            return False
        if params.exclude_modules and record.module in params.exclude_modules:
            return False
        if params.trace_id and record.trace_id != params.trace_id:
            return False
        if params.start_time and record.timestamp < params.start_time:
            return False
        if params.end_time and record.timestamp > params.end_time:
            return False
        if params.has_error is True and not record.error:
            return False
        if params.has_error is False and record.error:
            return False
        if params.tags and not set(record.tags) & set(params.tags):
            return False
        if params.keywords:
            text = f"{record.message} {record.error or ''} {record.module}"
            if not all(kw.lower() in text.lower() for kw in params.keywords):
                return False
        return True

    def _check_new_error(self, record: LogRecord) -> None:
        """检查新错误类型"""
        pattern = f"{record.module}:{record.error_type or ''}"
        if pattern not in self._error_patterns:
            self._error_patterns.add(pattern)
            anomaly = AnomalyEvent(
                anomaly_type=AnomalyType.NEW_ERROR,
                message=f"New error type in module '{record.module}': {record.error_type}",
                details={
                    "module": record.module,
                    "error_type": record.error_type,
                    "error": record.error,
                },
                severity="low",
            )
            with self._lock:
                self._anomalies.append(anomaly)
            for cb in self._alert_callbacks:
                try:
                    cb(anomaly)
                except Exception:
                    pass

    def _detect_error_spike(self) -> Optional[AnomalyEvent]:
        """检测错误率飙升"""
        records = self._source.get_records(limit=100)
        if len(records) < 20:
            return None

        recent = records[-20:]
        error_count = sum(1 for r in recent if r.level.value >= LogLevel.ERROR.value)
        error_rate = error_count / len(recent)

        if error_rate > 0.5:  # 超过50%错误率
            anomaly = AnomalyEvent(
                anomaly_type=AnomalyType.ERROR_SPIKE,
                message=f"Error rate spike detected: {error_rate:.0%} in last 20 records",
                details={
                    "error_rate": round(error_rate, 3),
                    "window_size": 20,
                    "error_count": error_count,
                },
                severity="high",
            )
            with self._lock:
                self._anomalies.append(anomaly)
            return anomaly
        return None

    def _get_top_errors(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最常见的错误"""
        records = self._source.get_records(limit=0)
        errors = [r for r in records if r.level.value >= LogLevel.ERROR.value]

        if not errors:
            return []

        counter = Counter(
            f"{r.module}:{r.error_type or 'unknown'}"
            for r in errors
        )

        return [
            {"pattern": pattern, "count": count}
            for pattern, count in counter.most_common(limit)
        ]


# ============================================================
# 全局单例
# ============================================================

_log_analytics: Optional[LogAnalytics] = None
_analytics_lock = threading.RLock()


def get_log_analytics() -> LogAnalytics:
    """获取全局日志分析器（双重检查锁定）"""
    global _log_analytics
    if _log_analytics is None:
        with _analytics_lock:
            if _log_analytics is None:
                _log_analytics = LogAnalytics()
    return _log_analytics
