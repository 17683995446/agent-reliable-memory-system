"""
流处理器 (StreamProcessor)
阶段242-244: 实时处理、窗口计算、背压控制

基于第一性原则设计:
1. 确定性: 事件时间处理，无随机性
2. 可靠性: 背压机制防止内存溢出
3. 实时性: 滑动窗口和会话窗口计算
"""

import threading
import time
import hashlib
from typing import Dict, List, Optional, Any, Callable, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque
from queue import Queue, Full as QueueFull


class WindowType(Enum):
    """窗口类型"""
    TUMBLING = "tumbling"      # 滚动窗口
    SLIDING = "sliding"        # 滑动窗口
    SESSION = "session"        # 会话窗口
    GLOBAL = "global"          # 全局窗口


class ProcessingMode(Enum):
    """处理模式"""
    AT_MOST_ONCE = "at_most_once"      # 最多一次
    AT_LEAST_ONCE = "at_least_once"    # 至少一次
    EXACTLY_ONCE = "exactly_once"      # 精确一次


@dataclass
class StreamEvent:
    """流事件"""
    event_id: str
    stream_key: str
    data: Any
    timestamp: float = field(default_factory=time.time)
    event_time: Optional[float] = None
    watermark: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WindowResult:
    """窗口计算结果"""
    window_id: str
    window_type: WindowType
    start_time: float
    end_time: float
    stream_key: str
    events: List[StreamEvent]
    result: Any
    event_count: int


@dataclass
class BackpressureMetrics:
    """背压指标"""
    queue_size: int
    queue_capacity: int
    processing_rate: float      # 处理速率(事件/秒)
    ingestion_rate: float       # 摄入速率(事件/秒)
    backpressure_level: float   # 背压级别(0-1)
    is_throttled: bool


class WindowOperator:
    """窗口算子基类"""
    
    def __init__(self, window_type: WindowType, stream_key: str):
        self._window_type = window_type
        self._stream_key = stream_key
        self._events: List[StreamEvent] = []
        self._lock = threading.RLock()
    
    def add_event(self, event: StreamEvent) -> bool:
        """添加事件到窗口"""
        with self._lock:
            if event.stream_key != self._stream_key:
                return False
            self._events.append(event)
            return True
    
    def get_events(self) -> List[StreamEvent]:
        """获取窗口内所有事件"""
        with self._lock:
            return self._events.copy()
    
    def clear(self) -> None:
        """清空窗口"""
        with self._lock:
            self._events.clear()
    
    def should_trigger(self, current_time: float) -> bool:
        """是否应该触发窗口计算"""
        return False
    
    def compute(self, aggregator: Callable[[List[StreamEvent]], Any]) -> Optional[WindowResult]:
        """执行窗口计算"""
        return None


class TumblingWindow(WindowOperator):
    """滚动窗口"""
    
    def __init__(self, stream_key: str, window_size_ms: int):
        super().__init__(WindowType.TUMBLING, stream_key)
        self._window_size_ms = window_size_ms
        self._current_window_start: Optional[float] = None
    
    def add_event(self, event: StreamEvent) -> bool:
        with self._lock:
            if not super().add_event(event):
                return False
            
            if self._current_window_start is None:
                self._current_window_start = event.timestamp
            
            return True
    
    def should_trigger(self, current_time: float) -> bool:
        with self._lock:
            if self._current_window_start is None:
                return False
            elapsed = (current_time - self._current_window_start) * 1000
            return elapsed >= self._window_size_ms
    
    def compute(self, aggregator: Callable[[List[StreamEvent]], Any]) -> Optional[WindowResult]:
        with self._lock:
            if not self._events or self._current_window_start is None:
                return None
            
            result = aggregator(self._events)
            
            window_result = WindowResult(
                window_id=f"tumbling_{self._stream_key}_{self._current_window_start}",
                window_type=WindowType.TUMBLING,
                start_time=self._current_window_start,
                end_time=self._current_window_start + self._window_size_ms / 1000,
                stream_key=self._stream_key,
                events=self._events.copy(),
                result=result,
                event_count=len(self._events)
            )
            
            # 重置窗口
            self._events.clear()
            self._current_window_start = None
            
            return window_result


class SlidingWindow(WindowOperator):
    """滑动窗口"""
    
    def __init__(self, stream_key: str, window_size_ms: int, slide_interval_ms: int):
        super().__init__(WindowType.SLIDING, stream_key)
        self._window_size_ms = window_size_ms
        self._slide_interval_ms = slide_interval_ms
        self._window_start_times: List[float] = []
    
    def add_event(self, event: StreamEvent) -> bool:
        with self._lock:
            if not super().add_event(event):
                return False
            
            # 检查是否需要创建新窗口
            current_time = event.timestamp
            if not self._window_start_times:
                self._window_start_times.append(current_time)
            else:
                last_start = self._window_start_times[-1]
                elapsed = (current_time - last_start) * 1000
                if elapsed >= self._slide_interval_ms:
                    self._window_start_times.append(current_time)
            
            return True
    
    def should_trigger(self, current_time: float) -> bool:
        with self._lock:
            if not self._window_start_times:
                return False
            
            # 检查最早的窗口是否应该触发
            earliest_start = self._window_start_times[0]
            elapsed = (current_time - earliest_start) * 1000
            return elapsed >= self._window_size_ms
    
    def compute(self, aggregator: Callable[[List[StreamEvent]], Any]) -> Optional[WindowResult]:
        with self._lock:
            if not self._window_start_times or not self._events:
                return None
            
            window_start = self._window_start_times.pop(0)
            window_end = window_start + self._window_size_ms / 1000
            
            # 筛选窗口内的事件
            window_events = [
                e for e in self._events
                if window_start <= e.timestamp < window_end
            ]
            
            if not window_events:
                return None
            
            result = aggregator(window_events)
            
            return WindowResult(
                window_id=f"sliding_{self._stream_key}_{window_start}",
                window_type=WindowType.SLIDING,
                start_time=window_start,
                end_time=window_end,
                stream_key=self._stream_key,
                events=window_events,
                result=result,
                event_count=len(window_events)
            )


class SessionWindow(WindowOperator):
    """会话窗口"""
    
    def __init__(self, stream_key: str, gap_ms: int):
        super().__init__(WindowType.SESSION, stream_key)
        self._gap_ms = gap_ms
        self._session_start: Optional[float] = None
        self._last_event_time: Optional[float] = None
    
    def add_event(self, event: StreamEvent) -> bool:
        with self._lock:
            if not super().add_event(event):
                return False
            
            current_time = event.timestamp
            
            if self._session_start is None:
                self._session_start = current_time
            
            self._last_event_time = current_time
            return True
    
    def should_trigger(self, current_time: float) -> bool:
        with self._lock:
            if self._last_event_time is None:
                return False
            
            gap = (current_time - self._last_event_time) * 1000
            return gap >= self._gap_ms
    
    def compute(self, aggregator: Callable[[List[StreamEvent]], Any]) -> Optional[WindowResult]:
        with self._lock:
            if not self._events or self._session_start is None:
                return None
            
            result = aggregator(self._events)
            
            window_result = WindowResult(
                window_id=f"session_{self._stream_key}_{self._session_start}",
                window_type=WindowType.SESSION,
                start_time=self._session_start,
                end_time=self._last_event_time or time.time(),
                stream_key=self._stream_key,
                events=self._events.copy(),
                result=result,
                event_count=len(self._events)
            )
            
            # 重置会话
            self._events.clear()
            self._session_start = None
            self._last_event_time = None
            
            return window_result


class StreamProcessor:
    """
    流处理器
    
    核心功能:
    1. 实时处理: 事件驱动的流处理
    2. 窗口计算: 滚动/滑动/会话窗口聚合
    3. 背压控制: 动态速率限制防止内存溢出
    """
    
    def __init__(self):
        self._lock = threading.RLock()
        
        # 事件队列(带背压控制)
        self._queue_capacity = 10000
        self._event_queue: Queue = Queue(maxsize=self._queue_capacity)
        
        # 流处理配置
        self._processing_mode = ProcessingMode.AT_LEAST_ONCE
        self._parallelism = 4
        
        # 窗口管理
        self._windows: Dict[str, WindowOperator] = {}
        self._window_results: List[WindowResult] = []
        self._max_results = 1000
        
        # 处理器注册
        self._processors: Dict[str, Callable[[StreamEvent], Any]] = {}
        self._aggregators: Dict[str, Callable[[List[StreamEvent]], Any]] = {}
        
        # 背压控制
        self._backpressure_enabled = True
        self._target_queue_ratio = 0.8
        self._throttle_delay_ms = 10
        self._metrics = BackpressureMetrics(
            queue_size=0,
            queue_capacity=self._queue_capacity,
            processing_rate=0.0,
            ingestion_rate=0.0,
            backpressure_level=0.0,
            is_throttled=False
        )
        
        # 性能统计
        self._processed_count = 0
        self._dropped_count = 0
        self._last_stats_time = time.time()
        self._stats_window_seconds = 1.0
        
        # 运行状态
        self._running = False
        self._processing_threads: List[threading.Thread] = []
        self._window_thread: Optional[threading.Thread] = None
    
    # ==================== 阶段242: 实时处理 ====================
    
    def submit_event(self, stream_key: str, data: Any,
                     event_time: Optional[float] = None,
                     metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        提交事件到流处理器
        
        Args:
            stream_key: 流标识
            data: 事件数据
            event_time: 事件时间(可选)
            metadata: 元数据(可选)
            
        Returns:
            是否提交成功
        """
        # 背压检查
        if self._backpressure_enabled:
            if not self._check_backpressure():
                with self._lock:
                    self._dropped_count += 1
                return False
        
        event = StreamEvent(
            event_id=self._generate_event_id(),
            stream_key=stream_key,
            data=data,
            event_time=event_time,
            metadata=metadata or {}
        )
        
        try:
            self._event_queue.put(event, block=False)
            return True
        except QueueFull:
            with self._lock:
                self._dropped_count += 1
            return False
    
    def _generate_event_id(self) -> str:
        """生成事件ID"""
        timestamp = str(time.time())
        counter = self._processed_count + self._dropped_count
        return hashlib.md5(f"{timestamp}{counter}".encode()).hexdigest()[:16]
    
    def register_processor(self, stream_key: str,
                          processor: Callable[[StreamEvent], Any]) -> None:
        """
        注册流处理器
        
        Args:
            stream_key: 流标识
            processor: 处理函数
        """
        with self._lock:
            self._processors[stream_key] = processor
    
    def _process_event(self, event: StreamEvent) -> Optional[Any]:
        """处理单个事件"""
        with self._lock:
            processor = self._processors.get(event.stream_key)
            if processor:
                try:
                    return processor(event)
                except Exception:
                    return None
            return None
    
    def _processing_loop(self) -> None:
        """处理循环"""
        while self._running:
            try:
                event = self._event_queue.get(timeout=1.0)
                
                # 处理事件
                result = self._process_event(event)
                
                # 添加到窗口
                self._add_to_windows(event)
                
                with self._lock:
                    self._processed_count += 1
                    
            except Exception:
                pass
    
    # ==================== 阶段243: 窗口计算 ====================
    
    def create_tumbling_window(self, stream_key: str,
                               window_size_ms: int) -> str:
        """
        创建滚动窗口
        
        Args:
            stream_key: 流标识
            window_size_ms: 窗口大小(毫秒)
            
        Returns:
            窗口ID
        """
        with self._lock:
            window_id = f"tumbling_{stream_key}_{window_size_ms}"
            self._windows[window_id] = TumblingWindow(stream_key, window_size_ms)
            return window_id
    
    def create_sliding_window(self, stream_key: str,
                             window_size_ms: int,
                             slide_interval_ms: int) -> str:
        """
        创建滑动窗口
        
        Args:
            stream_key: 流标识
            window_size_ms: 窗口大小(毫秒)
            slide_interval_ms: 滑动间隔(毫秒)
            
        Returns:
            窗口ID
        """
        with self._lock:
            window_id = f"sliding_{stream_key}_{window_size_ms}_{slide_interval_ms}"
            self._windows[window_id] = SlidingWindow(
                stream_key, window_size_ms, slide_interval_ms
            )
            return window_id
    
    def create_session_window(self, stream_key: str, gap_ms: int) -> str:
        """
        创建会话窗口
        
        Args:
            stream_key: 流标识
            gap_ms: 会话间隔(毫秒)
            
        Returns:
            窗口ID
        """
        with self._lock:
            window_id = f"session_{stream_key}_{gap_ms}"
            self._windows[window_id] = SessionWindow(stream_key, gap_ms)
            return window_id
    
    def register_aggregator(self, window_id: str,
                           aggregator: Callable[[List[StreamEvent]], Any]) -> None:
        """
        注册窗口聚合器
        
        Args:
            window_id: 窗口ID
            aggregator: 聚合函数
        """
        with self._lock:
            self._aggregators[window_id] = aggregator
    
    def _add_to_windows(self, event: StreamEvent) -> None:
        """添加事件到相关窗口"""
        with self._lock:
            for window in self._windows.values():
                window.add_event(event)
    
    def _window_loop(self) -> None:
        """窗口计算循环"""
        while self._running:
            try:
                current_time = time.time()
                
                with self._lock:
                    for window_id, window in self._windows.items():
                        if window.should_trigger(current_time):
                            aggregator = self._aggregators.get(window_id)
                            if aggregator:
                                result = window.compute(aggregator)
                                if result:
                                    self._window_results.append(result)
                                    
                                    # 限制结果数量
                                    if len(self._window_results) > self._max_results:
                                        self._window_results = self._window_results[-self._max_results:]
                
                time.sleep(0.1)  # 100ms检查一次
                
            except Exception:
                pass
    
    def get_window_results(self, limit: int = 100) -> List[WindowResult]:
        """
        获取窗口计算结果
        
        Args:
            limit: 结果数量限制
            
        Returns:
            窗口结果列表
        """
        with self._lock:
            return self._window_results[-limit:]
    
    # ==================== 阶段244: 背压控制 ====================
    
    def _check_backpressure(self) -> bool:
        """
        检查背压状态
        
        Returns:
            是否可以继续接收事件
        """
        with self._lock:
            queue_size = self._event_queue.qsize()
            queue_ratio = queue_size / self._queue_capacity
            
            self._metrics.queue_size = queue_size
            self._metrics.backpressure_level = queue_ratio
            
            # 更新速率统计
            current_time = time.time()
            elapsed = current_time - self._last_stats_time
            
            if elapsed >= self._stats_window_seconds:
                self._metrics.processing_rate = self._processed_count / elapsed
                self._metrics.ingestion_rate = (
                    self._processed_count + self._dropped_count
                ) / elapsed
                
                self._processed_count = 0
                self._dropped_count = 0
                self._last_stats_time = current_time
            
            # 背压判断
            if queue_ratio > self._target_queue_ratio:
                self._metrics.is_throttled = True
                
                # 应用节流延迟
                if queue_ratio > 0.9:
                    time.sleep(self._throttle_delay_ms / 1000 * 2)
                elif queue_ratio > 0.8:
                    time.sleep(self._throttle_delay_ms / 1000)
                
                return queue_ratio < 0.95  # 超过95%开始丢弃
            
            self._metrics.is_throttled = False
            return True
    
    def get_backpressure_metrics(self) -> BackpressureMetrics:
        """
        获取背压指标
        
        Returns:
            背压指标
        """
        with self._lock:
            return BackpressureMetrics(
                queue_size=self._metrics.queue_size,
                queue_capacity=self._metrics.queue_capacity,
                processing_rate=self._metrics.processing_rate,
                ingestion_rate=self._metrics.ingestion_rate,
                backpressure_level=self._metrics.backpressure_level,
                is_throttled=self._metrics.is_throttled
            )
    
    def set_backpressure_config(self, target_ratio: float = 0.8,
                                throttle_delay_ms: int = 10) -> None:
        """
        设置背压配置
        
        Args:
            target_ratio: 目标队列比例
            throttle_delay_ms: 节流延迟(毫秒)
        """
        with self._lock:
            self._target_queue_ratio = target_ratio
            self._throttle_delay_ms = throttle_delay_ms
    
    def enable_backpressure(self, enabled: bool = True) -> None:
        """
        启用/禁用背压控制
        
        Args:
            enabled: 是否启用
        """
        with self._lock:
            self._backpressure_enabled = enabled
    
    def start(self) -> None:
        """启动流处理器"""
        with self._lock:
            if self._running:
                return
            
            self._running = True
            
            # 启动处理线程
            for _ in range(self._parallelism):
                thread = threading.Thread(target=self._processing_loop, daemon=True)
                thread.start()
                self._processing_threads.append(thread)
            
            # 启动窗口线程
            self._window_thread = threading.Thread(target=self._window_loop, daemon=True)
            self._window_thread.start()
    
    def stop(self) -> None:
        """停止流处理器"""
        with self._lock:
            self._running = False


# 全局单例
_stream_processor_instance: Optional[StreamProcessor] = None
_stream_processor_lock = threading.Lock()


def get_stream_processor() -> StreamProcessor:
    """获取流处理器全局单例"""
    global _stream_processor_instance
    
    if _stream_processor_instance is None:
        with _stream_processor_lock:
            if _stream_processor_instance is None:
                _stream_processor_instance = StreamProcessor()
    
    return _stream_processor_instance
