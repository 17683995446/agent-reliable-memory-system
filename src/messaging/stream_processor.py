#!/usr/bin/env python3
"""
流处理器 (StreamProcessor) - 阶段340

职责：
- 流处理管道：Source → Transform → Sink
- 窗口聚合：滚动窗口、滑动窗口、会话窗口
- 背压控制：速率限制、缓冲区监控
- 流拓扑管理：DAG拓扑、并行处理
- 状态管理：有状态流处理

设计原则：
- 确定性规则，无模型依赖
- 线程安全（RLock + Condition）
- 最小层级，无循环依赖
"""

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from messaging.message_queue import Message, MessageStatus


# ============================================================
# 枚举与数据结构
# ============================================================

class WindowType(Enum):
    """窗口类型"""
    TUMBLING = "tumbling"     # 滚动窗口（固定大小，不重叠）
    SLIDING = "sliding"       # 滑动窗口（固定大小，可重叠）
    SESSION = "session"       # 会话窗口（基于活动间隔）
    COUNT = "count"           # 计数窗口（按消息数量触发）


class BackPressureStrategy(Enum):
    """背压策略"""
    DROP = "drop"               # 丢弃新消息
    BUFFER = "buffer"           # 缓冲（有上限）
    BLOCK = "block"             # 阻塞等待
    NOTIFY = "notify"           # 通知上游降速


class ProcessorState(Enum):
    """处理器状态"""
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class WindowConfig:
    """窗口配置"""
    window_type: WindowType = WindowType.TUMBLING
    size_ms: float = 1000.0         # 窗口大小（毫秒）
    slide_ms: float = 500.0         # 滑动间隔（毫秒，仅滑动窗口）
    gap_ms: float = 500.0           # 会话间隔（毫秒，仅会话窗口）
    count: int = 10                 # 计数窗口大小（仅计数窗口）


@dataclass
class BackPressureConfig:
    """背压配置"""
    strategy: BackPressureStrategy = BackPressureStrategy.BUFFER
    max_buffer_size: int = 1000
    high_watermark: float = 0.8     # 高水位（缓冲区使用率）
    low_watermark: float = 0.3      # 低水位
    max_rate: float = 0.0           # 最大速率（0=不限）


@dataclass
class StreamRecord:
    """流记录"""
    key: str = ""
    value: Any = None
    timestamp: float = 0.0
    headers: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


@dataclass
class WindowResult:
    """窗口聚合结果"""
    window_start: float
    window_end: float
    key: str = ""
    count: int = 0
    result: Any = None
    records: List[StreamRecord] = field(default_factory=list)


@dataclass
class ProcessorMetric:
    """处理器指标"""
    total_received: int = 0
    total_processed: int = 0
    total_dropped: int = 0
    total_errors: int = 0
    buffer_size: int = 0
    last_processed_at: float = 0.0
    avg_latency_ms: float = 0.0


# ============================================================
# 窗口管理器
# ============================================================

class WindowManager:
    """
    窗口管理器

    核心功能：
    1. 滚动窗口：固定大小，不重叠
    2. 滑动窗口：固定大小，按间隔滑动
    3. 会话窗口：基于活动间隔
    4. 计数窗口：按消息数量触发
    """

    def __init__(self, config: WindowConfig,
                 aggregate_fn: Callable[[List[StreamRecord]], Any] = None):
        self._config = config
        self._aggregate_fn = aggregate_fn or (lambda records: len(records))
        self._windows: Dict[str, deque] = defaultdict(deque)  # key → records
        self._window_starts: Dict[str, float] = {}
        self._lock = threading.RLock()
        self._total_windows = 0
        self._total_records = 0

    def add(self, record: StreamRecord) -> List[WindowResult]:
        """
        添加记录到窗口

        Returns:
            触发的窗口结果列表
        """
        results = []
        key = record.key or "_default_"

        with self._lock:
            now = time.time() * 1000  # 转毫秒

            if self._config.window_type == WindowType.TUMBLING:
                results = self._add_tumbling(key, record, now)
            elif self._config.window_type == WindowType.SLIDING:
                results = self._add_sliding(key, record, now)
            elif self._config.window_type == WindowType.SESSION:
                results = self._add_session(key, record, now)
            elif self._config.window_type == WindowType.COUNT:
                results = self._add_count(key, record)

            self._total_records += 1

        return results

    def _add_tumbling(self, key: str, record: StreamRecord,
                      now_ms: float) -> List[WindowResult]:
        """滚动窗口"""
        results = []
        size_ms = self._config.size_ms

        # 计算当前窗口起始
        if key not in self._window_starts:
            self._window_starts[key] = now_ms

        window_start = self._window_starts[key]
        window_records = self._windows[key]

        # 检查窗口是否到期
        if now_ms - window_start >= size_ms and window_records:
            result = self._emit_window(key, window_start, window_start + size_ms,
                                       list(window_records))
            results.append(result)
            window_records.clear()
            # 新窗口从当前时间开始
            self._window_starts[key] = now_ms
            self._total_windows += 1

        window_records.append(record)
        return results

    def _add_sliding(self, key: str, record: StreamRecord,
                     now_ms: float) -> List[WindowResult]:
        """滑动窗口"""
        results = []
        size_ms = self._config.size_ms
        slide_ms = self._config.slide_ms

        if key not in self._window_starts:
            self._window_starts[key] = now_ms

        window_start = self._window_starts[key]
        window_records = self._windows[key]

        # 检查是否需要滑动
        if now_ms - window_start >= slide_ms and window_records:
            result = self._emit_window(key, window_start, window_start + size_ms,
                                       list(window_records))
            results.append(result)
            window_records.clear()
            self._window_starts[key] = now_ms
            self._total_windows += 1

        window_records.append(record)
        return results

    def _add_session(self, key: str, record: StreamRecord,
                     now_ms: float) -> List[WindowResult]:
        """会话窗口"""
        results = []
        gap_ms = self._config.gap_ms

        window_records = self._windows[key]

        if window_records:
            last_ts = window_records[-1].timestamp * 1000
            if now_ms - last_ts > gap_ms:
                # 会话间隔超时，触发窗口
                first_ts = window_records[0].timestamp * 1000
                result = self._emit_window(key, first_ts, last_ts,
                                           list(window_records))
                results.append(result)
                window_records.clear()
                self._total_windows += 1

        if key not in self._window_starts or not window_records:
            self._window_starts[key] = now_ms

        window_records.append(record)
        return results

    def _add_count(self, key: str, record: StreamRecord) -> List[WindowResult]:
        """计数窗口"""
        results = []
        count = self._config.count
        window_records = self._windows[key]

        window_records.append(record)

        if len(window_records) >= count:
            first_ts = window_records[0].timestamp * 1000
            last_ts = window_records[-1].timestamp * 1000
            result = self._emit_window(key, first_ts, last_ts,
                                       list(window_records))
            results.append(result)
            window_records.clear()
            self._total_windows += 1

        return results

    def _emit_window(self, key: str, start: float, end: float,
                      records: List[StreamRecord]) -> WindowResult:
        """触发窗口"""
        aggregated = self._aggregate_fn(records)
        return WindowResult(
            window_start=start,
            window_end=end,
            key=key,
            count=len(records),
            result=aggregated,
            records=records,
        )

    def flush(self) -> List[WindowResult]:
        """刷新所有未触发的窗口"""
        results = []
        with self._lock:
            for key, records in self._windows.items():
                if records:
                    first_ts = records[0].timestamp * 1000
                    last_ts = records[-1].timestamp * 1000
                    result = self._emit_window(key, first_ts, last_ts,
                                               list(records))
                    results.append(result)
                    records.clear()
                    self._total_windows += 1
        return results

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "window_type": self._config.window_type.value,
                "active_windows": len(self._windows),
                "total_windows_emitted": self._total_windows,
                "total_records": self._total_records,
                "buffered_records": sum(len(r) for r in self._windows.values()),
            }


# ============================================================
# 背压控制器
# ============================================================

class BackPressureController:
    """
    背压控制器

    核心功能：
    1. 缓冲区监控
    2. 高低水位检测
    3. 速率限制
    4. 降级策略执行
    """

    def __init__(self, config: BackPressureConfig = None):
        self._config = config or BackPressureConfig()
        self._buffer: deque = deque()
        self._lock = threading.RLock()
        self._is_under_pressure = False
        self._total_dropped = 0
        self._total_buffered = 0
        self._rate_tokens: float = 0.0
        self._rate_last_refill: float = 0.0
        self._callbacks: List[Callable[[bool], None]] = []

    def submit(self, record: StreamRecord) -> bool:
        """
        提交记录

        Returns:
            是否接受
        """
        with self._lock:
            # 速率限制
            if self._config.max_rate > 0:
                if not self._try_consume_token():
                    self._total_dropped += 1
                    return False

            buffer_usage = len(self._buffer) / max(self._config.max_buffer_size, 1)

            # 检查是否超过高水位
            if buffer_usage >= self._config.high_watermark:
                if not self._is_under_pressure:
                    self._is_under_pressure = True
                    self._notify_pressure(True)

                if self._config.strategy == BackPressureStrategy.DROP:
                    self._total_dropped += 1
                    return False
                elif self._config.strategy == BackPressureStrategy.BLOCK:
                    if len(self._buffer) >= self._config.max_buffer_size:
                        self._total_dropped += 1
                        return False

            # 低水位恢复
            if self._is_under_pressure and buffer_usage <= self._config.low_watermark:
                self._is_under_pressure = False
                self._notify_pressure(False)

            self._buffer.append(record)
            self._total_buffered += 1
            return True

    def consume(self, count: int = 1) -> List[StreamRecord]:
        """消费缓冲区中的记录"""
        with self._lock:
            records = []
            for _ in range(min(count, len(self._buffer))):
                if self._buffer:
                    records.append(self._buffer.popleft())
            return records

    def _try_consume_token(self) -> bool:
        """令牌桶速率限制"""
        now = time.time()
        if self._rate_last_refill == 0:
            self._rate_last_refill = now
            self._rate_tokens = self._config.max_rate

        elapsed = now - self._rate_last_refill
        self._rate_tokens = min(
            self._config.max_rate,
            self._rate_tokens + elapsed * self._config.max_rate
        )
        self._rate_last_refill = now

        if self._rate_tokens >= 1.0:
            self._rate_tokens -= 1.0
            return True
        return False

    def on_pressure_change(self, callback: Callable[[bool], None]) -> None:
        """注册背压变化回调"""
        with self._lock:
            self._callbacks.append(callback)

    def _notify_pressure(self, under_pressure: bool) -> None:
        """通知背压变化"""
        for cb in self._callbacks:
            try:
                cb(under_pressure)
            except Exception:
                pass

    @property
    def buffer_size(self) -> int:
        with self._lock:
            return len(self._buffer)

    @property
    def is_under_pressure(self) -> bool:
        return self._is_under_pressure

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "strategy": self._config.strategy.value,
                "buffer_size": len(self._buffer),
                "max_buffer": self._config.max_buffer_size,
                "under_pressure": self._is_under_pressure,
                "total_dropped": self._total_dropped,
                "total_buffered": self._total_buffered,
                "max_rate": self._config.max_rate,
            }


# ============================================================
# 流处理器
# ============================================================

class StreamProcessor:
    """
    流处理器

    核心功能：
    1. 流处理管道：Source → Transform → Sink
    2. 窗口聚合
    3. 背压控制
    4. 有状态处理
    5. 指标统计
    """

    def __init__(self, name: str = "default"):
        self.name = name
        self._transforms: List[Callable[[StreamRecord], Optional[StreamRecord]]] = []
        self._sinks: List[Callable[[StreamRecord], None]] = []
        self._window_managers: Dict[str, WindowManager] = {}
        self._back_pressure = BackPressureController()
        self._state: Dict[str, Any] = {}
        self._state_lock = threading.RLock()
        self._lock = threading.RLock()
        self._status = ProcessorState.CREATED
        self._metric = ProcessorMetric()
        self._error_handler: Optional[Callable[[Exception, StreamRecord], None]] = None

    # ---- 管道配置 ----

    def add_transform(self, fn: Callable[[StreamRecord], Optional[StreamRecord]]) -> None:
        """添加转换函数（返回None则过滤掉记录）"""
        with self._lock:
            self._transforms.append(fn)

    def add_sink(self, fn: Callable[[StreamRecord], None]) -> None:
        """添加输出函数"""
        with self._lock:
            self._sinks.append(fn)

    def set_error_handler(self, fn: Callable[[Exception, StreamRecord], None]) -> None:
        """设置错误处理函数"""
        with self._lock:
            self._error_handler = fn

    # ---- 窗口 ----

    def add_window(self, name: str, config: WindowConfig,
                   aggregate_fn: Callable[[List[StreamRecord]], Any] = None) -> None:
        """添加窗口"""
        with self._lock:
            wm = WindowManager(config, aggregate_fn)
            self._window_managers[name] = wm

    def get_window_stats(self, name: str) -> Optional[Dict[str, Any]]:
        """获取窗口统计"""
        with self._lock:
            wm = self._window_managers.get(name)
            if wm:
                return wm.get_stats()
            return None

    def flush_windows(self) -> List[WindowResult]:
        """刷新所有窗口"""
        with self._lock:
            results = []
            for wm in self._window_managers.values():
                results.extend(wm.flush())
            return results

    # ---- 背压 ----

    def set_back_pressure(self, config: BackPressureConfig) -> None:
        """设置背压配置"""
        self._back_pressure = BackPressureController(config)

    # ---- 处理 ----

    def process(self, record: StreamRecord) -> bool:
        """
        处理一条记录

        Returns:
            是否处理成功
        """
        start = time.monotonic()

        with self._lock:
            if self._status != ProcessorState.RUNNING:
                return False
            self._metric.total_received += 1

        # 背压检查
        if not self._back_pressure.submit(record):
            with self._lock:
                self._metric.total_dropped += 1
            return False

        try:
            # 转换管道
            current = record
            for transform in self._transforms:
                try:
                    result = transform(current)
                    if result is None:
                        return True  # 过滤掉
                    current = result
                except Exception as e:
                    if self._error_handler:
                        self._error_handler(e, current)
                    with self._lock:
                        self._metric.total_errors += 1
                    return False

            # 窗口聚合
            for wm in self._window_managers.values():
                wm.add(current)

            # 输出
            for sink in self._sinks:
                try:
                    sink(current)
                except Exception as e:
                    if self._error_handler:
                        self._error_handler(e, current)

            # 从背压缓冲区消费
            self._back_pressure.consume(1)

            with self._lock:
                self._metric.total_processed += 1
                self._metric.last_processed_at = time.time()
                elapsed = (time.monotonic() - start) * 1000
                # 指数移动平均
                alpha = 0.1
                self._metric.avg_latency_ms = (
                    alpha * elapsed + (1 - alpha) * self._metric.avg_latency_ms
                )

            return True

        except Exception as e:
            if self._error_handler:
                self._error_handler(e, record)
            with self._lock:
                self._metric.total_errors += 1
            return False

    def process_batch(self, records: List[StreamRecord]) -> int:
        """批量处理"""
        success = 0
        for record in records:
            if self.process(record):
                success += 1
        return success

    # ---- 状态管理 ----

    def get_state(self, key: str, default: Any = None) -> Any:
        """获取状态"""
        with self._state_lock:
            return self._state.get(key, default)

    def set_state(self, key: str, value: Any) -> None:
        """设置状态"""
        with self._state_lock:
            self._state[key] = value

    def get_all_state(self) -> Dict[str, Any]:
        """获取所有状态"""
        with self._state_lock:
            return dict(self._state)

    # ---- 生命周期 ----

    def start(self) -> None:
        """启动处理器"""
        with self._lock:
            self._status = ProcessorState.RUNNING

    def pause(self) -> None:
        """暂停处理器"""
        with self._lock:
            self._status = ProcessorState.PAUSED

    def resume(self) -> None:
        """恢复处理器"""
        with self._lock:
            if self._status == ProcessorState.PAUSED:
                self._status = ProcessorState.RUNNING

    def stop(self) -> None:
        """停止处理器"""
        with self._lock:
            self._status = ProcessorState.STOPPED

    @property
    def status(self) -> ProcessorState:
        return self._status

    # ---- 统计 ----

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "name": self.name,
                "status": self._status.value,
                "transforms": len(self._transforms),
                "sinks": len(self._sinks),
                "windows": {n: wm.get_stats() for n, wm in self._window_managers.items()},
                "back_pressure": self._back_pressure.get_stats(),
                "received": self._metric.total_received,
                "processed": self._metric.total_processed,
                "dropped": self._metric.total_dropped,
                "errors": self._metric.total_errors,
                "avg_latency_ms": round(self._metric.avg_latency_ms, 3),
                "state_keys": len(self._state),
            }


# ============================================================
# 流拓扑
# ============================================================

class StreamTopology:
    """
    流拓扑

    核心功能：
    1. 多处理器组成DAG
    2. 处理器间连接
    3. 并行处理
    4. 拓扑统计
    """

    def __init__(self, name: str = "default"):
        self.name = name
        self._processors: Dict[str, StreamProcessor] = {}
        self._edges: Dict[str, List[str]] = defaultdict(list)  # src → [dst]
        self._lock = threading.RLock()
        self._total_flowed = 0

    def add_processor(self, name: str, processor: StreamProcessor) -> None:
        """添加处理器"""
        with self._lock:
            self._processors[name] = processor

    def connect(self, source: str, target: str) -> bool:
        """连接处理器"""
        with self._lock:
            if source not in self._processors or target not in self._processors:
                return False
            if target not in self._edges[source]:
                self._edges[source].append(target)
            return True

    def submit(self, processor_name: str, record: StreamRecord) -> bool:
        """提交记录到指定处理器（沿拓扑传播）"""
        with self._lock:
            processor = self._processors.get(processor_name)
            if processor is None:
                return False

        success = processor.process(record)

        if success:
            # BFS传播到所有下游
            visited = set()
            queue = list(self._edges.get(processor_name, []))
            while queue:
                dst_name = queue.pop(0)
                if dst_name in visited:
                    continue
                visited.add(dst_name)
                dst = self._processors.get(dst_name)
                if dst:
                    dst.process(record)
                    with self._lock:
                        self._total_flowed += 1
                    # 继续向下游传播
                    for next_dst in self._edges.get(dst_name, []):
                        if next_dst not in visited:
                            queue.append(next_dst)

        return success

    def start_all(self) -> None:
        """启动所有处理器"""
        with self._lock:
            for p in self._processors.values():
                p.start()

    def stop_all(self) -> None:
        """停止所有处理器"""
        with self._lock:
            for p in self._processors.values():
                p.stop()

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "name": self.name,
                "processors": len(self._processors),
                "edges": sum(len(v) for v in self._edges.values()),
                "total_flowed": self._total_flowed,
                "processor_stats": {
                    n: p.get_stats() for n, p in self._processors.items()
                },
            }


# ============================================================
# 全局单例
# ============================================================

_topology: Optional[StreamTopology] = None
_topo_lock = threading.RLock()


def get_topology() -> StreamTopology:
    """获取全局流拓扑"""
    global _topology
    if _topology is None:
        with _topo_lock:
            if _topology is None:
                _topology = StreamTopology()
    return _topology
