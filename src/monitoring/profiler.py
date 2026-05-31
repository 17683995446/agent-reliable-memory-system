"""
性能分析器 - 阶段200-202

功能：
- 阶段200: 调用链追踪
- 阶段201: 热点分析
- 阶段202: 瓶颈检测

设计原则：
- 确定性规则，无模型依赖
- 最小层级，无循环依赖
- 线程安全，RLock保护
- 单例模式，全局唯一
"""

import threading
import time
import json
import functools
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Dict, List, Optional, Callable, Any, Set, Tuple
from collections import deque, defaultdict
import uuid
import hashlib
import inspect


class SpanStatus(Enum):
    """Span状态"""
    OK = "ok"
    ERROR = "error"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class ProfileType(Enum):
    """分析类型"""
    CPU = "cpu"
    MEMORY = "memory"
    TIME = "time"
    IO = "io"
    CALL = "call"


@dataclass
class Span:
    """调用链Span"""
    span_id: str
    trace_id: str
    parent_id: Optional[str]
    name: str
    start_time: float
    end_time: Optional[float] = None
    duration_ms: float = 0.0
    status: SpanStatus = SpanStatus.OK
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    children: List["Span"] = field(default_factory=list)
    
    def finish(self, status: SpanStatus = SpanStatus.OK,
               attributes: Optional[Dict[str, Any]] = None):
        """结束Span"""
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        self.status = status
        
        if attributes:
            self.attributes.update(attributes)
    
    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        """添加事件"""
        self.events.append({
            "name": name,
            "timestamp": time.time(),
            "attributes": attributes or {}
        })
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_id": self.parent_id,
            "name": self.name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "status": self.status.value,
            "attributes": self.attributes,
            "events": self.events,
            "children": [c.to_dict() for c in self.children]
        }


@dataclass
class Trace:
    """调用链Trace"""
    trace_id: str
    root_span: Optional[Span] = None
    spans: List[Span] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    
    def finish(self):
        """结束Trace"""
        self.end_time = time.time()
    
    def get_span(self, span_id: str) -> Optional[Span]:
        """获取Span"""
        for span in self.spans:
            if span.span_id == span_id:
                return span
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "trace_id": self.trace_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": (self.end_time - self.start_time) * 1000 if self.end_time else None,
            "attributes": self.attributes,
            "span_count": len(self.spans),
            "root_span": self.root_span.to_dict() if self.root_span else None
        }


@dataclass
class HotSpot:
    """热点"""
    name: str
    type: str  # function, query, io, etc.
    total_time_ms: float
    call_count: int
    avg_time_ms: float
    max_time_ms: float
    min_time_ms: float
    percentage: float  # 占总时间的百分比


@dataclass
class Bottleneck:
    """瓶颈"""
    bottleneck_id: str
    name: str
    type: str  # cpu, memory, io, lock, network
    severity: str  # low, medium, high, critical
    description: str
    location: str
    recommendation: str
    detected_at: float
    metrics: Dict[str, float] = field(default_factory=dict)


@dataclass
class FunctionProfile:
    """函数性能画像"""
    function_name: str
    module_name: str
    call_count: int = 0
    total_time_ms: float = 0.0
    avg_time_ms: float = 0.0
    max_time_ms: float = 0.0
    min_time_ms: float = float('inf')
    last_called: Optional[float] = None


class PerformanceProfiler:
    """
    性能分析器
    
    阶段200: 调用链追踪
    - 分布式追踪支持
    - Span上下文管理
    - Trace构建与查询
    
    阶段201: 热点分析
    - 函数调用统计
    - 耗时分析
    - 调用频率分析
    
    阶段202: 瓶颈检测
    - 自动瓶颈识别
    - 性能退化检测
    - 优化建议生成
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
            
            # 调用链存储
            self._traces: Dict[str, Trace] = {}
            self._traces_history: deque = deque(maxlen=10000)
            self._active_spans: Dict[str, Span] = {}
            
            # 线程本地存储当前Trace/Span
            self._local = threading.local()
            
            # 热点分析
            self._function_profiles: Dict[str, FunctionProfile] = {}
            self._hotspots: List[HotSpot] = []
            
            # 瓶颈检测
            self._bottlenecks: List[Bottleneck] = []
            self._bottleneck_thresholds = {
                "slow_function_ms": 1000,
                "high_cpu_percent": 80,
                "high_memory_percent": 85,
                "high_error_rate": 5.0
            }
            
            # 性能基线
            self._performance_baselines: Dict[str, Dict[str, float]] = {}
            
            # 采样配置
            self._sampling_rate = 1.0  # 100%采样
            self._max_spans_per_trace = 1000
            
            # 分析循环
            self._analysis_thread: Optional[threading.Thread] = None
            self._analysis_running = False
            self._analysis_interval = 60  # 60秒分析间隔
    
    # ========== 阶段200: 调用链追踪 ==========
    
    def start_trace(self, name: str,
                    attributes: Optional[Dict[str, Any]] = None) -> Trace:
        """开始Trace"""
        trace_id = str(uuid.uuid4()).replace("-", "")
        
        trace = Trace(
            trace_id=trace_id,
            attributes=attributes or {}
        )
        
        with self._lock:
            self._traces[trace_id] = trace
        
        # 设置线程本地变量
        self._local.current_trace = trace
        
        return trace
    
    def start_span(self, name: str,
                   parent: Optional[Span] = None,
                   attributes: Optional[Dict[str, Any]] = None) -> Span:
        """开始Span"""
        # 获取当前Trace
        trace = getattr(self._local, 'current_trace', None)
        
        if trace is None:
            # 自动创建Trace
            trace = self.start_trace(name)
        
        # 确定父Span
        if parent is None:
            parent = getattr(self._local, 'current_span', None)
        
        span_id = str(uuid.uuid4()).replace("-", "")[:16]
        
        span = Span(
            span_id=span_id,
            trace_id=trace.trace_id,
            parent_id=parent.span_id if parent else None,
            name=name,
            start_time=time.time(),
            attributes=attributes or {}
        )
        
        with self._lock:
            trace.spans.append(span)
            self._active_spans[span_id] = span
            
            if parent:
                parent.children.append(span)
            elif not trace.root_span:
                trace.root_span = span
        
        # 更新线程本地变量
        self._local.current_span = span
        
        return span
    
    def finish_span(self, span: Optional[Span] = None,
                    status: SpanStatus = SpanStatus.OK) -> None:
        """结束Span"""
        if span is None:
            span = getattr(self._local, 'current_span', None)
        
        if span is None:
            return
        
        span.finish(status)
        
        with self._lock:
            if span.span_id in self._active_spans:
                del self._active_spans[span.span_id]
        
        # 恢复父Span到线程本地
        if span.parent_id:
            trace = self._traces.get(span.trace_id)
            if trace:
                parent = trace.get_span(span.parent_id)
                self._local.current_span = parent
        else:
            self._local.current_span = None
    
    def finish_trace(self, trace: Optional[Trace] = None) -> None:
        """结束Trace"""
        if trace is None:
            trace = getattr(self._local, 'current_trace', None)
        
        if trace is None:
            return
        
        trace.finish()
        
        with self._lock:
            if trace.trace_id in self._traces:
                # 移到历史
                self._traces_history.append(self._traces.pop(trace.trace_id))
        
        # 清除线程本地变量
        self._local.current_trace = None
        self._local.current_span = None
    
    def get_current_trace(self) -> Optional[Trace]:
        """获取当前Trace"""
        return getattr(self._local, 'current_trace', None)
    
    def get_current_span(self) -> Optional[Span]:
        """获取当前Span"""
        return getattr(self._local, 'current_span', None)
    
    def trace(self, name: str):
        """Trace装饰器"""
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                trace = self.start_trace(name)
                span = self.start_span(func.__name__)
                
                try:
                    result = func(*args, **kwargs)
                    span.finish(SpanStatus.OK)
                    return result
                except Exception as e:
                    span.finish(SpanStatus.ERROR)
                    span.add_event("exception", {"error": str(e)})
                    raise
                finally:
                    self.finish_span(span)
                    self.finish_trace(trace)
            
            return wrapper
        return decorator
    
    def span(self, name: str):
        """Span装饰器"""
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                span = self.start_span(name or func.__name__)
                
                try:
                    result = func(*args, **kwargs)
                    span.finish(SpanStatus.OK)
                    return result
                except Exception as e:
                    span.finish(SpanStatus.ERROR)
                    span.add_event("exception", {"error": str(e)})
                    raise
                finally:
                    self.finish_span(span)
            
            return wrapper
        return decorator
    
    def get_trace(self, trace_id: str) -> Optional[Trace]:
        """获取Trace"""
        with self._lock:
            return self._traces.get(trace_id)
    
    def get_recent_traces(self, limit: int = 100) -> List[Trace]:
        """获取最近的Trace"""
        with self._lock:
            active = list(self._traces.values())
            history = list(self._traces_history)
            
            all_traces = active + history
            return sorted(all_traces, key=lambda t: t.start_time, reverse=True)[:limit]
    
    def get_slow_traces(self, min_duration_ms: float,
                        limit: int = 100) -> List[Trace]:
        """获取慢Trace"""
        with self._lock:
            slow_traces = []
            for trace in list(self._traces.values()) + list(self._traces_history):
                if trace.end_time:
                    duration = (trace.end_time - trace.start_time) * 1000
                    if duration >= min_duration_ms:
                        slow_traces.append(trace)
            
            return sorted(slow_traces,
                         key=lambda t: t.end_time - t.start_time if t.end_time else 0,
                         reverse=True)[:limit]
    
    # ========== 阶段201: 热点分析 ==========
    
    def record_function_call(self, function_name: str,
                             module_name: str,
                             duration_ms: float) -> None:
        """记录函数调用"""
        key = f"{module_name}.{function_name}"
        
        with self._lock:
            if key not in self._function_profiles:
                self._function_profiles[key] = FunctionProfile(
                    function_name=function_name,
                    module_name=module_name
                )
            
            profile = self._function_profiles[key]
            profile.call_count += 1
            profile.total_time_ms += duration_ms
            profile.avg_time_ms = profile.total_time_ms / profile.call_count
            profile.max_time_ms = max(profile.max_time_ms, duration_ms)
            profile.min_time_ms = min(profile.min_time_ms, duration_ms)
            profile.last_called = time.time()
    
    def profile_function(self, func: Callable = None, *, name: str = None):
        """函数性能分析装饰器"""
        def decorator(f: Callable) -> Callable:
            func_name = name or f.__name__
            module_name = f.__module__
            
            @functools.wraps(f)
            def wrapper(*args, **kwargs):
                start = time.time()
                try:
                    return f(*args, **kwargs)
                finally:
                    duration = (time.time() - start) * 1000
                    self.record_function_call(func_name, module_name, duration)
            
            return wrapper
        
        if func is None:
            return decorator
        return decorator(func)
    
    def analyze_hotspots(self, top_n: int = 10) -> List[HotSpot]:
        """分析热点"""
        with self._lock:
            profiles = list(self._function_profiles.values())
        
        if not profiles:
            return []
        
        # 计算总时间
        total_time = sum(p.total_time_ms for p in profiles)
        
        hotspots = []
        for profile in profiles:
            hotspot = HotSpot(
                name=f"{profile.module_name}.{profile.function_name}",
                type="function",
                total_time_ms=profile.total_time_ms,
                call_count=profile.call_count,
                avg_time_ms=profile.avg_time_ms,
                max_time_ms=profile.max_time_ms,
                min_time_ms=profile.min_time_ms if profile.min_time_ms != float('inf') else 0,
                percentage=(profile.total_time_ms / total_time * 100) if total_time > 0 else 0
            )
            hotspots.append(hotspot)
        
        # 按总时间排序
        hotspots.sort(key=lambda h: h.total_time_ms, reverse=True)
        
        with self._lock:
            self._hotspots = hotspots[:top_n]
        
        return self._hotspots
    
    def get_hotspots(self) -> List[HotSpot]:
        """获取热点列表"""
        with self._lock:
            return list(self._hotspots)
    
    def get_function_profile(self, function_name: str,
                             module_name: str = "") -> Optional[FunctionProfile]:
        """获取函数画像"""
        key = f"{module_name}.{function_name}" if module_name else function_name
        
        with self._lock:
            return self._function_profiles.get(key)
    
    def get_all_profiles(self) -> List[FunctionProfile]:
        """获取所有函数画像"""
        with self._lock:
            return list(self._function_profiles.values())
    
    # ========== 阶段202: 瓶颈检测 ==========
    
    def detect_bottlenecks(self) -> List[Bottleneck]:
        """检测瓶颈"""
        bottlenecks = []
        
        # 检测慢函数
        with self._lock:
            profiles = list(self._function_profiles.values())
        
        for profile in profiles:
            if profile.avg_time_ms > self._bottleneck_thresholds["slow_function_ms"]:
                bottleneck = Bottleneck(
                    bottleneck_id=str(uuid.uuid4()),
                    name=f"Slow Function: {profile.function_name}",
                    type="cpu",
                    severity="high" if profile.avg_time_ms > 5000 else "medium",
                    description=f"Function {profile.function_name} averages {profile.avg_time_ms:.2f}ms per call",
                    location=f"{profile.module_name}:{profile.function_name}",
                    recommendation="Consider optimizing this function or implementing caching",
                    detected_at=time.time(),
                    metrics={
                        "avg_time_ms": profile.avg_time_ms,
                        "max_time_ms": profile.max_time_ms,
                        "call_count": profile.call_count
                    }
                )
                bottlenecks.append(bottleneck)
        
        # 检测高频调用函数
        for profile in profiles:
            if profile.call_count > 10000 and profile.avg_time_ms > 10:
                bottleneck = Bottleneck(
                    bottleneck_id=str(uuid.uuid4()),
                    name=f"High Frequency Function: {profile.function_name}",
                    type="cpu",
                    severity="medium",
                    description=f"Function {profile.function_name} called {profile.call_count} times",
                    location=f"{profile.module_name}:{profile.function_name}",
                    recommendation="Consider batching or caching results",
                    detected_at=time.time(),
                    metrics={
                        "call_count": profile.call_count,
                        "total_time_ms": profile.total_time_ms
                    }
                )
                bottlenecks.append(bottleneck)
        
        # 检测慢Trace
        slow_traces = self.get_slow_traces(5000)  # 超过5秒的Trace
        for trace in slow_traces[:5]:  # 只取前5个
            bottleneck = Bottleneck(
                bottleneck_id=str(uuid.uuid4()),
                name=f"Slow Trace: {trace.trace_id[:8]}",
                type="io",
                severity="high",
                description=f"Trace took {(trace.end_time - trace.start_time) * 1000:.2f}ms to complete",
                location=trace.root_span.name if trace.root_span else "unknown",
                recommendation="Review trace spans to identify slow operations",
                detected_at=time.time(),
                metrics={
                    "duration_ms": (trace.end_time - trace.start_time) * 1000,
                    "span_count": len(trace.spans)
                }
            )
            bottlenecks.append(bottleneck)
        
        with self._lock:
            self._bottlenecks = bottlenecks
        
        return bottlenecks
    
    def get_bottlenecks(self, severity: Optional[str] = None) -> List[Bottleneck]:
        """获取瓶颈列表"""
        with self._lock:
            if severity:
                return [b for b in self._bottlenecks if b.severity == severity]
            return list(self._bottlenecks)
    
    def set_baseline(self, metric_name: str,
                     avg_value: float,
                     max_value: float) -> None:
        """设置性能基线"""
        with self._lock:
            self._performance_baselines[metric_name] = {
                "avg": avg_value,
                "max": max_value,
                "set_at": time.time()
            }
    
    def check_performance_regression(self, metric_name: str,
                                     current_value: float) -> Optional[Bottleneck]:
        """检查性能退化"""
        with self._lock:
            baseline = self._performance_baselines.get(metric_name)
        
        if not baseline:
            return None
        
        # 检查是否超过基线
        if current_value > baseline["max"] * 1.5:  # 超过50%
            return Bottleneck(
                bottleneck_id=str(uuid.uuid4()),
                name=f"Performance Regression: {metric_name}",
                type="performance",
                severity="critical",
                description=f"Metric {metric_name} degraded from {baseline['avg']:.2f} to {current_value:.2f}",
                location=metric_name,
                recommendation="Review recent changes and investigate performance degradation",
                detected_at=time.time(),
                metrics={
                    "baseline_avg": baseline["avg"],
                    "baseline_max": baseline["max"],
                    "current_value": current_value,
                    "degradation_percent": ((current_value - baseline["avg"]) / baseline["avg"] * 100)
                }
            )
        
        return None
    
    def generate_report(self) -> Dict[str, Any]:
        """生成性能报告"""
        hotspots = self.analyze_hotspots(top_n=10)
        bottlenecks = self.detect_bottlenecks()
        
        # 统计Trace
        with self._lock:
            total_traces = len(self._traces) + len(self._traces_history)
            active_spans = len(self._active_spans)
        
        recent_traces = self.get_recent_traces(100)
        avg_trace_duration = 0
        if recent_traces:
            durations = [
                (t.end_time - t.start_time) * 1000
                for t in recent_traces if t.end_time
            ]
            if durations:
                avg_trace_duration = sum(durations) / len(durations)
        
        return {
            "timestamp": time.time(),
            "summary": {
                "total_traces": total_traces,
                "active_spans": active_spans,
                "avg_trace_duration_ms": avg_trace_duration,
                "hotspot_count": len(hotspots),
                "bottleneck_count": len(bottlenecks)
            },
            "hotspots": [
                {
                    "name": h.name,
                    "type": h.type,
                    "total_time_ms": h.total_time_ms,
                    "call_count": h.call_count,
                    "avg_time_ms": h.avg_time_ms,
                    "percentage": h.percentage
                }
                for h in hotspots
            ],
            "bottlenecks": [
                {
                    "id": b.bottleneck_id,
                    "name": b.name,
                    "type": b.type,
                    "severity": b.severity,
                    "description": b.description,
                    "recommendation": b.recommendation
                }
                for b in bottlenecks
            ]
        }
    
    def start_analysis_loop(self) -> None:
        """启动分析循环"""
        with self._lock:
            if self._analysis_running:
                return
            
            self._analysis_running = True
            self._analysis_thread = threading.Thread(
                target=self._analysis_loop,
                daemon=True
            )
            self._analysis_thread.start()
    
    def stop_analysis_loop(self) -> None:
        """停止分析循环"""
        with self._lock:
            self._analysis_running = False
        
        if self._analysis_thread:
            self._analysis_thread.join(timeout=5.0)
    
    def _analysis_loop(self) -> None:
        """分析循环"""
        while True:
            with self._lock:
                if not self._analysis_running:
                    break
            
            try:
                self.analyze_hotspots()
                self.detect_bottlenecks()
            except Exception:
                pass
            
            time.sleep(self._analysis_interval)
    
    def export_traces(self, format: str = "json") -> str:
        """导出Trace数据"""
        traces = self.get_recent_traces(1000)
        
        if format == "json":
            data = [t.to_dict() for t in traces]
            return json.dumps(data, indent=2, ensure_ascii=False)
        
        elif format == "jaeger":
            # Jaeger格式（简化）
            jaeger_data = {
                "data": [
                    {
                        "traceID": t.trace_id,
                        "spans": [
                            {
                                "spanID": s.span_id,
                                "operationName": s.name,
                                "startTime": int(s.start_time * 1000000),
                                "duration": int(s.duration_ms * 1000),
                                "tags": [{"key": k, "value": v} for k, v in s.attributes.items()]
                            }
                            for s in t.spans
                        ]
                    }
                    for t in traces
                ]
            }
            return json.dumps(jaeger_data, indent=2, ensure_ascii=False)
        
        return ""
    
    def reset(self) -> None:
        """重置所有数据"""
        with self._lock:
            self._traces.clear()
            self._traces_history.clear()
            self._active_spans.clear()
            self._function_profiles.clear()
            self._hotspots.clear()
            self._bottlenecks.clear()


# 全局单例
_profiler_instance: Optional[PerformanceProfiler] = None
_profiler_lock = threading.RLock()


def get_profiler() -> PerformanceProfiler:
    """获取性能分析器全局实例"""
    global _profiler_instance
    if _profiler_instance is None:
        with _profiler_lock:
            if _profiler_instance is None:
                _profiler_instance = PerformanceProfiler()
    return _profiler_instance
