#!/usr/bin/env python3
"""
追踪收集器 (TraceCollector) - 阶段333

职责：
- 分布式追踪：生成/传播trace_id
- Span管理：创建、开始、结束、嵌套Span
- 调用链关联：parent-child关系
- 采样策略：全量/概率/自适应采样
- 追踪上下文：线程本地存储

设计原则：
- 确定性规则，无模型依赖
- 线程安全（RLock + threading.local）
- 最小层级，无循环依赖
"""

import random
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


# ============================================================
# 枚举与数据结构
# ============================================================

class SpanStatus(Enum):
    """Span状态"""
    STARTED = "started"
    FINISHED = "finished"
    ERROR = "error"


class SamplingStrategy(Enum):
    """采样策略"""
    ALWAYS = "always"         # 全量采样
    NEVER = "never"           # 不采样
    PROBABILITY = "probability" # 概率采样
    ADAPTIVE = "adaptive"     # 自适应采样


@dataclass
class Span:
    """追踪Span"""
    trace_id: str
    span_id: str = ""
    name: str = ""
    parent_id: str = ""
    service: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    duration_ms: float = 0.0
    status: SpanStatus = SpanStatus.STARTED
    tags: Dict[str, str] = field(default_factory=dict)
    logs: List[Dict[str, Any]] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.start_time == 0.0:
            self.start_time = time.time()
        if not self.span_id:
            self.span_id = self._generate_id()

    def finish(self, status: SpanStatus = SpanStatus.FINISHED) -> None:
        """结束Span"""
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        self.status = status

    def add_tag(self, key: str, value: str) -> None:
        """添加标签"""
        self.tags[key] = value

    def add_log(self, message: str, **kwargs) -> None:
        """添加日志"""
        self.logs.append({
            "timestamp": time.time(),
            "message": message,
            **kwargs,
        })

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "name": self.name,
            "parent_id": self.parent_id,
            "service": self.service,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": round(self.duration_ms, 3),
            "status": self.status.value,
            "tags": self.tags,
            "logs_count": len(self.logs),
        }

    @staticmethod
    def _generate_id() -> str:
        return uuid.uuid4().hex[:16]


@dataclass
class TraceSummary:
    """追踪摘要"""
    trace_id: str
    span_count: int = 0
    duration_ms: float = 0.0
    root_span: str = ""
    service: str = ""
    status: SpanStatus = SpanStatus.FINISHED
    error_count: int = 0


# ============================================================
# 追踪上下文（线程本地存储）
# ============================================================

class TraceContext:
    """追踪上下文（线程安全）"""

    def __init__(self):
        self._local = threading.local()

    def set(self, trace_id: str, span_id: str = "") -> None:
        """设置当前追踪上下文"""
        self._local.trace_id = trace_id
        self._local.span_id = span_id

    def get_trace_id(self) -> str:
        """获取当前trace_id"""
        return getattr(self._local, 'trace_id', '')

    def get_span_id(self) -> str:
        """获取当前span_id"""
        return getattr(self._local, 'span_id', '')

    def clear(self) -> None:
        """清除上下文"""
        self._local.trace_id = ""
        self._local.span_id = ""

    def is_active(self) -> bool:
        """是否有活跃追踪"""
        return bool(self.get_trace_id())


# ============================================================
# 追踪收集器
# ============================================================

class TraceCollector:
    """
    追踪收集器

    核心功能：
    1. 生成/传播trace_id
    2. 创建和管理Span
    3. Span嵌套（parent-child关系）
    4. 采样策略
    5. 追踪存储与查询
    6. 追踪摘要统计
    """

    def __init__(self):
        self._spans: Dict[str, Span] = {}  # span_id -> Span
        self._traces: Dict[str, List[str]] = defaultdict(list)  # trace_id -> [span_ids]
        self._context = TraceContext()
        self._lock = threading.RLock()
        self._sampling_strategy = SamplingStrategy.ALWAYS
        self._sampling_rate = 1.0  # 概率采样率
        self._adaptive_threshold_ms = 100.0  # 自适应阈值
        self._total_traces = 0
        self._total_spans = 0
        self._max_traces = 10000
        self._callbacks: List[Callable[[Span], None]] = []

    # ---- Trace管理 ----

    def start_trace(self, name: str = "root", service: str = "",
                    trace_id: str = "") -> Span:
        """
        开始新的追踪

        Args:
            name: 根Span名称
            service: 服务名称
            trace_id: 可选，指定trace_id

        Returns:
            根Span
        """
        if not trace_id:
            trace_id = uuid.uuid4().hex[:16]

        # 采样检查
        if not self._should_sample(trace_id):
            span = Span(trace_id=trace_id, span_id="", name=name, service=service)
            span.span_id = span._generate_id()
            self._context.set(trace_id, span.span_id)
            return span

        span = Span(
            trace_id=trace_id,
            name=name,
            service=service,
        )

        with self._lock:
            self._spans[span.span_id] = span
            self._traces[trace_id].append(span.span_id)
            self._total_traces += 1
            self._total_spans += 1

        self._context.set(trace_id, span.span_id)
        return span

    def end_trace(self, trace_id: str = "") -> Optional[TraceSummary]:
        """
        结束追踪

        Args:
            trace_id: 追踪ID

        Returns:
            追踪摘要
        """
        tid = trace_id or self._context.get_trace_id()
        if not tid:
            return None

        with self._lock:
            span_ids = self._traces.get(tid, [])

        # 结束所有未完成的Span
        for sid in span_ids:
            span = self._spans.get(sid)
            if span and span.status == SpanStatus.STARTED:
                span.finish()

        self._context.clear()

        return self.get_trace_summary(tid)

    def create_span(self, name: str, parent_id: str = "",
                     service: str = "") -> Optional[Span]:
        """
        创建子Span

        Args:
            name: Span名称
            parent_id: 父Span ID
            service: 服务名称

        Returns:
            新Span
        """
        trace_id = self._context.get_trace_id()
        if not trace_id:
            return None

        if not parent_id:
            parent_id = self._context.get_span_id()

        span = Span(
            trace_id=trace_id,
            name=name,
            parent_id=parent_id,
            service=service,
        )

        with self._lock:
            self._spans[span.span_id] = span
            if trace_id in self._traces:
                self._traces[trace_id].append(span.span_id)
            self._total_spans += 1

        self._context.set(trace_id, span.span_id)
        return span

    def finish_span(self, span_id: str = "",
                     status: SpanStatus = SpanStatus.FINISHED) -> None:
        """结束Span"""
        sid = span_id or self._context.get_span_id()
        if not sid:
            return

        with self._lock:
            span = self._spans.get(sid)
            if span:
                span.finish(status)

        # 通知回调
        if span:
            for cb in self._callbacks:
                try:
                    cb(span)
                except Exception:
                    pass

    # ---- 上下文 ----

    @property
    def context(self) -> TraceContext:
        """获取追踪上下文"""
        return self._context

    def get_current_trace_id(self) -> str:
        """获取当前trace_id"""
        return self._context.get_trace_id()

    def get_current_span_id(self) -> str:
        """获取当前span_id"""
        return self._context.get_span_id()

    # ---- 采样 ----

    def set_sampling_strategy(self, strategy: SamplingStrategy,
                              rate: float = 1.0) -> None:
        """设置采样策略"""
        self._sampling_strategy = strategy
        self._sampling_rate = rate

    def _should_sample(self, trace_id: str) -> bool:
        """判断是否采样"""
        if self._sampling_strategy == SamplingStrategy.ALWAYS:
            return True
        elif self._sampling_strategy == SamplingStrategy.NEVER:
            return False
        elif self._sampling_strategy == SamplingStrategy.PROBABILITY:
            return random.random() < self._sampling_rate
        elif self._sampling_strategy == SamplingStrategy.ADAPTIVE:
            # 简单自适应：基于trace_id哈希
            hash_val = int(trace_id[:8], 16) % 100
            return hash_val < (self._sampling_rate * 100)
        return True

    # ---- 查询 ----

    def get_span(self, span_id: str) -> Optional[Span]:
        """获取Span"""
        with self._lock:
            return self._spans.get(span_id)

    def get_trace_spans(self, trace_id: str) -> List[Span]:
        """获取追踪的所有Span"""
        with self._lock:
            span_ids = self._traces.get(trace_id, [])
            return [self._spans[sid] for sid in span_ids if sid in self._spans]

    def get_trace_summary(self, trace_id: str) -> Optional[TraceSummary]:
        """获取追踪摘要"""
        spans = self.get_trace_spans(trace_id)
        if not spans:
            return None

        root_span = next((s for s in spans if not s.parent_id), spans[0])
        error_count = sum(1 for s in spans if s.status == SpanStatus.ERROR)
        total_duration = max(s.end_time for s in spans) - min(s.start_time for s in spans)

        return TraceSummary(
            trace_id=trace_id,
            span_count=len(spans),
            duration_ms=total_duration * 1000,
            root_span=root_span.name,
            service=root_span.service,
            status=SpanStatus.ERROR if error_count > 0 else SpanStatus.FINISHED,
            error_count=error_count,
        )

    def list_traces(self, limit: int = 50) -> List[Dict[str, Any]]:
        """列出追踪"""
        with self._lock:
            trace_ids = list(self._traces.keys())[-limit:]

        results = []
        for tid in trace_ids:
            summary = self.get_trace_summary(tid)
            if summary:
                results.append({
                    "trace_id": tid,
                    "span_count": summary.span_count,
                    "duration_ms": round(summary.duration_ms, 2),
                    "root_span": summary.root_span,
                    "status": summary.status.value,
                    "error_count": summary.error_count,
                })
        return results

    # ---- 回调 ----

    def on_span_finish(self, callback: Callable[[Span], None]) -> None:
        """添加Span结束回调"""
        self._callbacks.append(callback)

    # ---- 统计 ----

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                "total_traces": self._total_traces,
                "total_spans": self._total_spans,
                "stored_spans": len(self._spans),
                "stored_traces": len(self._traces),
                "sampling_strategy": self._sampling_strategy.value,
                "sampling_rate": self._sampling_rate,
                "callbacks": len(self._callbacks),
            }

    def clear(self) -> int:
        """清除所有追踪数据"""
        with self._lock:
            count = len(self._spans)
            self._spans.clear()
            self._traces.clear()
            return count


# ============================================================
# 全局单例
# ============================================================

_trace_collector: Optional[TraceCollector] = None
_trace_lock = threading.RLock()


def get_trace_collector() -> TraceCollector:
    """获取全局追踪收集器（双重检查锁定）"""
    global _trace_collector
    if _trace_collector is None:
        with _trace_lock:
            if _trace_collector is None:
                _trace_collector = TraceCollector()
    return _trace_collector
