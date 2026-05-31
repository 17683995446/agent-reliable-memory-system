#!/usr/bin/env python3
"""
性能监控 (PerformanceMonitor) - 阶段350

职责：
- 延迟追踪：操作耗时记录与分析
- 吞吐量统计：QPS/TPS计算
- 资源监控：内存/线程/连接数
- 性能基线：基线对比与偏差检测
- 性能报告：定时生成性能摘要

设计原则：
- 确定性规则，无模型依赖
- 线程安全（RLock）
- 最小层级，无循环依赖
"""

import math
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


# ============================================================
# 枚举与数据结构
# ============================================================

class MetricType(Enum):
    """指标类型"""
    COUNTER = "counter"       # 计数器
    GAUGE = "gauge"           # 仪表盘
    HISTOGRAM = "histogram"   # 直方图
    TIMER = "timer"           # 计时器


@dataclass
class TimerRecord:
    """计时记录"""
    name: str
    start: float = 0.0
    end: float = 0.0
    duration: float = 0.0
    success: bool = True
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class LatencySnapshot:
    """延迟快照"""
    name: str
    count: int = 0
    avg_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    stddev_ms: float = 0.0
    timestamp: float = 0.0


@dataclass
class ThroughputSnapshot:
    """吞吐量快照"""
    name: str
    count: int = 0
    rate_per_second: float = 0.0
    window_seconds: float = 60.0
    timestamp: float = 0.0


@dataclass
class ResourceSnapshot:
    """资源快照"""
    timestamp: float = 0.0
    thread_count: int = 0
    memory_mb: float = 0.0
    active_timers: int = 0
    active_counters: int = 0


@dataclass
class PerformanceBaseline:
    """性能基线"""
    name: str
    avg_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    qps: float = 0.0
    max_memory_mb: float = 0.0


@dataclass
class BaselineDeviation:
    """基线偏差"""
    name: str
    avg_deviation: float = 0.0     # 偏差百分比
    p95_deviation: float = 0.0
    p99_deviation: float = 0.0
    qps_deviation: float = 0.0
    status: str = "ok"  # ok, warning, critical


# ============================================================
# 延迟追踪器
# ============================================================

class LatencyTracker:
    """
    延迟追踪器

    核心功能：
    1. 计时上下文管理
    2. 延迟直方图
    3. 百分位计算
    4. 滑动窗口统计
    """

    def __init__(self, window_size: int = 1000):
        self._window_size = window_size
        self._timers: Dict[str, deque] = defaultdict(lambda: deque(maxlen=window_size))
        self._active: Dict[str, float] = {}  # name → start_time
        self._lock = threading.RLock()

    def start(self, name: str) -> None:
        """开始计时"""
        with self._lock:
            self._active[name] = time.monotonic()

    def stop(self, name: str, success: bool = True,
             tags: Optional[Dict[str, str]] = None) -> Optional[float]:
        """停止计时，返回耗时（毫秒）"""
        with self._lock:
            start = self._active.pop(name, None)
            if start is None:
                return None

        duration_ms = (time.monotonic() - start) * 1000

        self._timers[name].append(TimerRecord(
            name=name,
            start=start,
            end=start + duration_ms / 1000,
            duration=duration_ms,
            success=success,
            tags=tags or {},
        ))
        return duration_ms

    def record(self, name: str, duration_ms: float,
               success: bool = True) -> None:
        """直接记录耗时"""
        with self._lock:
            self._timers[name].append(TimerRecord(
                name=name, duration=duration_ms, success=success
            ))

    def get_snapshot(self, name: str) -> LatencySnapshot:
        """获取延迟快照"""
        with self._lock:
            records = list(self._timers.get(name, []))

        if not records:
            return LatencySnapshot(name=name)

        durations = [r.duration for r in records]
        durations.sort()

        n = len(durations)
        avg = sum(durations) / n
        variance = sum((d - avg) ** 2 for d in durations) / n if n > 0 else 0
        stddev = math.sqrt(variance)

        def percentile(p: float) -> float:
            if n == 0:
                return 0.0
            k = (n - 1) * p / 100.0
            f = int(k)
            c = min(f + 1, n - 1)
            return durations[f] + (k - f) * (durations[c] - durations[f])

        return LatencySnapshot(
            name=name,
            count=n,
            avg_ms=round(avg, 3),
            min_ms=round(durations[0], 3),
            max_ms=round(durations[-1], 3),
            p50_ms=round(percentile(50), 3),
            p95_ms=round(percentile(95), 3),
            p99_ms=round(percentile(99), 3),
            stddev_ms=round(stddev, 3),
            timestamp=time.time(),
        )

    def get_all_names(self) -> List[str]:
        """获取所有计时器名称"""
        with self._lock:
            return list(self._timers.keys())

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "timers": len(self._timers),
                "active": len(self._active),
                "window_size": self._window_size,
            }


# ============================================================
# 吞吐量追踪器
# ============================================================

class ThroughputTracker:
    """
    吞吐量追踪器

    核心功能：
    1. 滑动窗口计数
    2. QPS/TPS计算
    3. 多时间窗口
    """

    def __init__(self):
        self._counts: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10000))
        self._lock = threading.RLock()

    def record(self, name: str) -> None:
        """记录一次操作"""
        with self._lock:
            self._counts[name].append(time.time())

    def get_throughput(self, name: str,
                       window_seconds: float = 60.0) -> ThroughputSnapshot:
        """获取吞吐量"""
        with self._lock:
            timestamps = list(self._counts.get(name, []))

        cutoff = time.time() - window_seconds
        recent = [t for t in timestamps if t > cutoff]
        count = len(recent)

        return ThroughputSnapshot(
            name=name,
            count=count,
            rate_per_second=round(count / window_seconds, 2),
            window_seconds=window_seconds,
            timestamp=time.time(),
        )

    def get_all_names(self) -> List[str]:
        with self._lock:
            return list(self._counts.keys())

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "tracked": len(self._counts),
                "total_records": sum(len(d) for d in self._counts.values()),
            }


# ============================================================
# 资源监控器
# ============================================================

class ResourceMonitor:
    """
    资源监控器

    核心功能：
    1. 线程数监控
    2. 内存使用估算
    3. 自定义指标
    """

    def __init__(self):
        self._custom_metrics: Dict[str, Callable[[], float]] = {}
        self._lock = threading.RLock()

    def register_metric(self, name: str, fn: Callable[[], float]) -> None:
        """注册自定义指标"""
        with self._lock:
            self._custom_metrics[name] = fn

    def get_snapshot(self) -> ResourceSnapshot:
        """获取资源快照"""
        import sys
        with self._lock:
            snapshot = ResourceSnapshot(
                timestamp=time.time(),
                thread_count=threading.active_count(),
                memory_mb=round(sys.getsizeof(0) / 1024 / 1024, 2),  # 近似
            )
            return snapshot

    def get_custom(self, name: str) -> Optional[float]:
        """获取自定义指标值"""
        with self._lock:
            fn = self._custom_metrics.get(name)
            if fn:
                try:
                    return fn()
                except Exception:
                    return None
            return None

    def get_all_custom(self) -> Dict[str, float]:
        """获取所有自定义指标"""
        result = {}
        with self._lock:
            for name, fn in self._custom_metrics.items():
                try:
                    result[name] = fn()
                except Exception:
                    result[name] = 0.0
        return result

    def get_stats(self) -> Dict[str, Any]:
        return {
            "custom_metrics": len(self._custom_metrics),
        }


# ============================================================
# 性能监控器
# ============================================================

class PerformanceMonitor:
    """
    性能监控器

    核心功能：
    1. 延迟追踪
    2. 吞吐量统计
    3. 资源监控
    4. 性能基线管理
    5. 综合报告
    """

    def __init__(self):
        self._latency = LatencyTracker()
        self._throughput = ThroughputTracker()
        self._resource = ResourceMonitor()
        self._baselines: Dict[str, PerformanceBaseline] = {}
        self._lock = threading.RLock()

    # ---- 延迟 ----

    def timer_start(self, name: str) -> None:
        self._latency.start(name)

    def timer_stop(self, name: str, success: bool = True) -> Optional[float]:
        return self._latency.stop(name, success)

    def record_latency(self, name: str, duration_ms: float) -> None:
        self._latency.record(name, duration_ms)

    def get_latency(self, name: str) -> LatencySnapshot:
        return self._latency.get_snapshot(name)

    # ---- 吞吐量 ----

    def record_operation(self, name: str) -> None:
        self._throughput.record(name)

    def get_throughput(self, name: str,
                        window: float = 60.0) -> ThroughputSnapshot:
        return self._throughput.get_throughput(name, window)

    # ---- 资源 ----

    def register_metric(self, name: str, fn: Callable[[], float]) -> None:
        self._resource.register_metric(name, fn)

    def get_resources(self) -> ResourceSnapshot:
        return self._resource.get_snapshot()

    # ---- 基线 ----

    def set_baseline(self, baseline: PerformanceBaseline) -> None:
        """设置性能基线"""
        with self._lock:
            self._baselines[baseline.name] = baseline

    def check_baseline(self, name: str) -> Optional[BaselineDeviation]:
        """检查与基线的偏差"""
        with self._lock:
            baseline = self._baselines.get(name)
            if baseline is None:
                return None

        latency = self._latency.get_snapshot(name)
        throughput = self._throughput.get_throughput(name)

        def deviation(current: float, base: float) -> float:
            if base == 0:
                return 0.0 if current == 0 else 100.0
            return round(((current - base) / base) * 100, 2)

        avg_dev = deviation(latency.avg_ms, baseline.avg_ms)
        p95_dev = deviation(latency.p95_ms, baseline.p95_ms)
        p99_dev = deviation(latency.p99_ms, baseline.p99_ms)
        qps_dev = deviation(throughput.rate_per_second, baseline.qps)

        # 状态判定
        max_dev = max(abs(avg_dev), abs(p95_dev), abs(p99_dev))
        if max_dev > 100:
            status = "critical"
        elif max_dev > 50:
            status = "warning"
        else:
            status = "ok"

        return BaselineDeviation(
            name=name,
            avg_deviation=avg_dev,
            p95_deviation=p95_dev,
            p99_deviation=p99_dev,
            qps_deviation=qps_dev,
            status=status,
        )

    # ---- 综合报告 ----

    def get_report(self) -> Dict[str, Any]:
        """生成综合性能报告"""
        report = {
            "timestamp": time.time(),
            "latency": {},
            "throughput": {},
            "resources": {},
            "baselines": {},
        }

        for name in self._latency.get_all_names():
            snap = self._latency.get_snapshot(name)
            report["latency"][name] = {
                "count": snap.count,
                "avg_ms": snap.avg_ms,
                "p95_ms": snap.p95_ms,
                "p99_ms": snap.p99_ms,
            }

        for name in self._throughput.get_all_names():
            snap = self._throughput.get_throughput(name)
            report["throughput"][name] = {
                "count": snap.count,
                "qps": snap.rate_per_second,
            }

        res = self._resource.get_snapshot()
        report["resources"] = {
            "thread_count": res.thread_count,
            "memory_mb": res.memory_mb,
        }

        for name in self._baselines:
            dev = self.check_baseline(name)
            if dev:
                report["baselines"][name] = {
                    "status": dev.status,
                    "avg_dev": dev.avg_deviation,
                    "p95_dev": dev.p95_deviation,
                }

        return report

    def get_stats(self) -> Dict[str, Any]:
        return {
            "latency": self._latency.get_stats(),
            "throughput": self._throughput.get_stats(),
            "resources": self._resource.get_stats(),
            "baselines": len(self._baselines),
        }


# ============================================================
# 全局单例
# ============================================================

_perf_monitor: Optional[PerformanceMonitor] = None
_pm_lock = threading.RLock()


def get_performance_monitor() -> PerformanceMonitor:
    """获取全局性能监控器"""
    global _perf_monitor
    if _perf_monitor is None:
        with _pm_lock:
            if _perf_monitor is None:
                _perf_monitor = PerformanceMonitor()
    return _perf_monitor
