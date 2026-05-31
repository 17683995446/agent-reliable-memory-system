#!/usr/bin/env python3
"""
日志聚合器 (LogAggregator) - 阶段334

职责：
- 日志聚合：从多个来源收集日志
- 缓冲写入：批量写入，减少IO操作
- 文件轮转：按大小/时间自动轮转日志文件
- 归档管理：压缩旧日志、自动清理
- 多通道输出：同时输出到多个目标

设计原则：
- 确定性规则，无模型依赖
- 线程安全（RLock）
- 最小层级，无循环依赖
"""

import gzip
import os
import shutil
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from log_system.structured_logger import (
    LogLevel, LogRecord, OutputChannel, MemoryChannel
)
from log_system.log_formatter import BaseFormatter, JsonFormatter, TextFormatter


# ============================================================
# 枚举与数据结构
# ============================================================

class RotationPolicy(Enum):
    """轮转策略"""
    SIZE = "size"       # 按文件大小
    TIME = "time"       # 按时间间隔
    DAILY = "daily"     # 每天轮转
    NEVER = "never"     # 不轮转


class ArchiveFormat(Enum):
    """归档格式"""
    NONE = "none"       # 不压缩
    GZIP = "gzip"       # gzip压缩


@dataclass
class RotationConfig:
    """轮转配置"""
    policy: RotationPolicy = RotationPolicy.SIZE
    max_size_mb: float = 100.0      # 最大文件大小（MB）
    max_files: int = 10             # 最大保留文件数
    rotation_interval: float = 3600  # 时间轮转间隔（秒）
    archive_format: ArchiveFormat = ArchiveFormat.GZIP
    archive_dir: str = ""            # 归档目录


@dataclass
class BufferConfig:
    """缓冲配置"""
    enabled: bool = True
    max_size: int = 1000             # 最大缓冲条数
    flush_interval: float = 5.0     # 刷新间隔（秒）
    flush_on_level: LogLevel = LogLevel.ERROR  # 触发立即刷新的级别


@dataclass
class AggregatorStats:
    """聚合器统计"""
    total_received: int = 0
    total_written: int = 0
    total_dropped: int = 0
    total_rotations: int = 0
    total_archives: int = 0
    buffer_size: int = 0
    current_file_size: int = 0


# ============================================================
# 轮转文件通道
# ============================================================

class RotatingFileChannel(OutputChannel):
    """轮转文件输出通道"""

    def __init__(self, path: str, config: Optional[RotationConfig] = None,
                 formatter: Optional[BaseFormatter] = None,
                 name: str = "rotating_file"):
        super().__init__(name)
        self._path = path
        self._config = config or RotationConfig()
        self._formatter = formatter or JsonFormatter()
        self._lock = threading.RLock()
        self._file = None
        self._current_size = 0
        self._rotation_count = 0
        self._last_rotation = time.time()
        self._open()

    def _open(self) -> None:
        import os
        dir_path = os.path.dirname(self._path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        self._file = open(self._path, 'a', encoding='utf-8')
        self._update_size()

    def _do_write(self, record: LogRecord) -> None:
        with self._lock:
            if not self._file:
                return

            line = self._formatter.format(record)
            data = (line + "\n").encode('utf-8')

            # 检查轮转
            if self._should_rotate(len(data)):
                self._rotate()

            self._file.write(line + "\n")
            self._current_size += len(data)
            self._file.flush()

    def _should_rotate(self, additional_bytes: int) -> bool:
        """检查是否需要轮转"""
        config = self._config
        now = time.time()

        if config.policy == RotationPolicy.SIZE:
            return self._current_size + additional_bytes >= config.max_size_mb * 1024 * 1024
        elif config.policy == RotationPolicy.TIME:
            return now - self._last_rotation >= config.rotation_interval
        elif config.policy == RotationPolicy.DAILY:
            from datetime import datetime
            last = datetime.fromtimestamp(self._last_rotation).date()
            current = datetime.fromtimestamp(now).date()
            return current > last
        return False

    def _rotate(self) -> None:
        """执行轮转"""
        if not self._file:
            return

        self._file.close()

        # 生成归档文件名
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        base, ext = os.path.splitext(self._path)
        archive_name = f"{base}_{timestamp}{ext}"

        # 移动当前文件
        if os.path.exists(self._path):
            shutil.move(self._path, archive_name)

        # 压缩归档
        if self._config.archive_format == ArchiveFormat.GZIP:
            self._compress(archive_name)
            archive_name += ".gz"

        # 清理旧文件
        self._cleanup()

        # 重新打开
        self._file = open(self._path, 'a', encoding='utf-8')
        self._current_size = 0
        self._last_rotation = time.time()
        self._rotation_count += 1

    def _compress(self, filepath: str) -> None:
        """压缩文件"""
        try:
            with open(filepath, 'rb') as f_in:
                with gzip.open(filepath + ".gz", 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            os.remove(filepath)
        except Exception:
            pass

    def _cleanup(self) -> None:
        """清理旧文件"""
        config = self._config
        if config.max_files <= 0:
            return

        import glob
        base, ext = os.path.splitext(self._path)
        pattern = f"{base}_*{ext}*"
        files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)

        while len(files) > config.max_files:
            old_file = files.pop()
            try:
                os.remove(old_file)
            except Exception:
                pass

    def _update_size(self) -> None:
        """更新当前文件大小"""
        try:
            if os.path.exists(self._path):
                self._current_size = os.path.getsize(self._path)
        except Exception:
            self._current_size = 0

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

    @property
    def rotation_count(self) -> int:
        return self._rotation_count

    @property
    def current_size(self) -> int:
        return self._current_size


# ============================================================
# 日志聚合器
# ============================================================

class LogAggregator:
    """
    日志聚合器

    核心功能：
    1. 从多个来源收集日志
    2. 缓冲写入（批量刷新）
    3. 文件轮转
    4. 归档管理
    5. 多通道路由
    6. 统计监控
    """

    def __init__(self, buffer_config: Optional[BufferConfig] = None):
        self._buffer_config = buffer_config or BufferConfig()
        self._buffer: deque = deque(maxlen=self._buffer_config.max_size)
        self._channels: List[OutputChannel] = []
        self._lock = threading.RLock()
        self._stats = AggregatorStats()
        self._flush_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False

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

    def list_channels(self) -> List[str]:
        """列出通道"""
        with self._lock:
            return [ch.name for ch in self._channels]

    # ---- 写入 ----

    def write(self, record: LogRecord) -> None:
        """
        写入日志记录

        Args:
            record: 日志记录
        """
        with self._lock:
            self._stats.total_received += 1

            if self._buffer_config.enabled:
                self._buffer.append(record)
                self._stats.buffer_size = len(self._buffer)

                # 高级别日志立即刷新
                if record.level.value >= self._buffer_config.flush_on_level.value:
                    self._flush_buffer()
            else:
                self._write_to_channels(record)

    def write_batch(self, records: List[LogRecord]) -> int:
        """批量写入"""
        count = 0
        for record in records:
            self.write(record)
            count += 1
        return count

    # ---- 缓冲控制 ----

    def flush(self) -> int:
        """手动刷新缓冲"""
        with self._lock:
            return self._flush_buffer()

    def start_auto_flush(self) -> bool:
        """启动自动刷新"""
        with self._lock:
            if self._running:
                return False
            self._running = True
            self._stop_event.clear()
            self._flush_thread = threading.Thread(
                target=self._auto_flush_loop,
                daemon=True,
                name="log_aggregator_flush"
            )
            self._flush_thread.start()
            return True

    def stop_auto_flush(self) -> None:
        """停止自动刷新"""
        with self._lock:
            self._running = False
        self._stop_event.set()
        if self._flush_thread:
            self._flush_thread.join(timeout=5.0)
            self._flush_thread = None
        # 最后一次刷新
        self.flush()

    # ---- 统计 ----

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                "total_received": self._stats.total_received,
                "total_written": self._stats.total_written,
                "total_dropped": self._stats.total_dropped,
                "total_rotations": self._stats.total_rotations,
                "buffer_size": self._stats.buffer_size,
                "channels": len(self._channels),
                "auto_flush": self._running,
            }

    def reset_stats(self) -> None:
        """重置统计"""
        with self._lock:
            self._stats = AggregatorStats()

    # ---- 内部方法 ----

    def _flush_buffer(self) -> int:
        """刷新缓冲区"""
        flushed = 0
        while self._buffer:
            record = self._buffer.popleft()
            self._write_to_channels(record)
            flushed += 1

        with self._lock:
            self._stats.buffer_size = len(self._buffer)
        return flushed

    def _write_to_channels(self, record: LogRecord) -> None:
        """写入到所有通道"""
        channels = list(self._channels)
        for channel in channels:
            try:
                channel.write(record)
                with self._lock:
                    self._stats.total_written += 1
            except Exception:
                with self._lock:
                    self._stats.total_dropped += 1

    def _auto_flush_loop(self) -> None:
        """自动刷新循环"""
        while not self._stop_event.is_set():
            self._stop_event.wait(self._buffer_config.flush_interval)
            if not self._stop_event.is_set():
                with self._lock:
                    if self._buffer:
                        self._flush_buffer()


# ============================================================
# 全局单例
# ============================================================

_log_aggregator: Optional[LogAggregator] = None
_agg_lock = threading.RLock()


def get_log_aggregator() -> LogAggregator:
    """获取全局日志聚合器（双重检查锁定）"""
    global _log_aggregator
    if _log_aggregator is None:
        with _agg_lock:
            if _log_aggregator is None:
                _log_aggregator = LogAggregator()
    return _log_aggregator
