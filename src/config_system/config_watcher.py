#!/usr/bin/env python3
"""
配置监听器 (ConfigWatcher) - 阶段328

职责：
- 文件系统监听：基于轮询的文件变更检测
- 变更检测：mtime/size/hash比对
- 热重载回调：文件变更时自动触发重载
- 防抖处理：避免频繁触发
- 变更历史记录

设计原则：
- 确定性规则，无模型依赖
- 线程安全（RLock）
- 最小层级，无循环依赖
- 不依赖inotify/watchdog等第三方库
"""

import hashlib
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


# ============================================================
# 枚举与数据结构
# ============================================================

class ChangeType(Enum):
    """变更类型"""
    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


class WatcherState(Enum):
    """监听器状态"""
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"


@dataclass
class FileSnapshot:
    """文件快照"""
    path: str
    mtime: float = 0.0
    size: int = 0
    md5: str = ""
    exists: bool = False
    last_checked: float = 0.0


@dataclass
class ChangeEvent:
    """变更事件"""
    path: str
    change_type: ChangeType
    timestamp: float = 0.0
    old_snapshot: Optional[FileSnapshot] = None
    new_snapshot: Optional[FileSnapshot] = None

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


@dataclass
class WatchConfig:
    """监听配置"""
    path: str
    recursive: bool = False
    interval: float = 2.0          # 轮询间隔（秒）
    debounce: float = 1.0          # 防抖时间（秒）
    checksum: bool = False         # 是否使用MD5校验
    patterns: List[str] = field(default_factory=lambda: ["*"])  # 文件匹配模式
    ignore_patterns: List[str] = field(default_factory=list)    # 忽略模式


# ============================================================
# 配置监听器
# ============================================================

class ConfigWatcher:
    """
    配置监听器

    核心功能：
    1. 文件系统轮询监听
    2. 多种变更检测策略（mtime/size/md5）
    3. 防抖处理
    4. 变更事件回调
    5. 变更历史记录
    6. 批量监听管理
    """

    def __init__(self):
        self._watches: Dict[str, WatchConfig] = {}
        self._snapshots: Dict[str, FileSnapshot] = {}
        self._callbacks: List[Callable[[ChangeEvent], None]] = []
        self._history: deque = deque(maxlen=500)
        self._lock = threading.RLock()
        self._state = WatcherState.STOPPED
        self._watch_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._pending_changes: Dict[str, float] = {}  # path -> last_change_time
        self._total_changes: int = 0
        self._total_scans: int = 0

    # ---- 监听管理 ----

    def watch(self, config: WatchConfig) -> bool:
        """
        添加文件监听

        Args:
            config: 监听配置

        Returns:
            是否添加成功
        """
        with self._lock:
            if config.path in self._watches:
                return False

            self._watches[config.path] = config
            self._snapshots[config.path] = self._take_snapshot(config.path, config.checksum)

            return True

    def unwatch(self, path: str) -> bool:
        """移除文件监听"""
        with self._lock:
            if path not in self._watches:
                return False
            del self._watches[path]
            self._snapshots.pop(path, None)
            self._pending_changes.pop(path, None)
            return True

    def list_watches(self) -> List[Dict[str, Any]]:
        """列出所有监听"""
        with self._lock:
            return [
                {
                    "path": w.path,
                    "recursive": w.recursive,
                    "interval": w.interval,
                    "debounce": w.debounce,
                    "checksum": w.checksum,
                    "patterns": w.patterns,
                }
                for w in self._watches.values()
            ]

    # ---- 事件回调 ----

    def on_change(self, callback: Callable[[ChangeEvent], None]) -> None:
        """添加变更回调"""
        with self._lock:
            self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[ChangeEvent], None]) -> bool:
        """移除变更回调"""
        with self._lock:
            try:
                self._callbacks.remove(callback)
                return True
            except ValueError:
                return False

    # ---- 启停控制 ----

    def start(self) -> bool:
        """启动监听"""
        with self._lock:
            if self._state == WatcherState.RUNNING:
                return False

            if not self._watches:
                return False

            self._state = WatcherState.RUNNING
            self._stop_event.clear()
            self._watch_thread = threading.Thread(
                target=self._watch_loop,
                daemon=True,
                name="config_watcher"
            )
            self._watch_thread.start()
            return True

    def stop(self) -> None:
        """停止监听"""
        with self._lock:
            if self._state != WatcherState.RUNNING:
                return
            self._state = WatcherState.STOPPED

        self._stop_event.set()
        if self._watch_thread:
            self._watch_thread.join(timeout=5.0)
            self._watch_thread = None

    def pause(self) -> None:
        """暂停监听"""
        with self._lock:
            if self._state == WatcherState.RUNNING:
                self._state = WatcherState.PAUSED

    def resume(self) -> None:
        """恢复监听"""
        with self._lock:
            if self._state == WatcherState.PAUSED:
                self._state = WatcherState.RUNNING

    @property
    def state(self) -> WatcherState:
        """获取当前状态"""
        with self._lock:
            return self._state

    # ---- 手动检查 ----

    def check_once(self) -> List[ChangeEvent]:
        """
        手动执行一次检查（不启动后台线程）

        Returns:
            检测到的变更事件列表
        """
        events = []
        with self._lock:
            watches = dict(self._watches)
            snapshots = dict(self._snapshots)

        for path, config in watches.items():
            old_snapshot = snapshots.get(path)
            new_snapshot = self._take_snapshot(path, config.checksum)

            with self._lock:
                self._snapshots[path] = new_snapshot

            event = self._detect_change(path, old_snapshot, new_snapshot)
            if event:
                events.append(event)
                self._dispatch_event(event)

        return events

    # ---- 历史查询 ----

    def get_history(self, limit: int = 50, path: Optional[str] = None) -> List[Dict[str, Any]]:
        """查询变更历史"""
        with self._lock:
            history = list(self._history)

        if path:
            history = [e for e in history if e.path == path]

        return [
            {
                "path": e.path,
                "type": e.change_type.value,
                "timestamp": e.timestamp,
            }
            for e in history[-limit:]
        ]

    def get_stats(self) -> Dict[str, Any]:
        """获取监听器统计"""
        with self._lock:
            return {
                "state": self._state.value,
                "watched_paths": len(self._watches),
                "total_changes": self._total_changes,
                "total_scans": self._total_scans,
                "callbacks": len(self._callbacks),
                "pending_changes": len(self._pending_changes),
                "history_size": len(self._history),
            }

    # ---- 内部方法 ----

    def _watch_loop(self) -> None:
        """监听循环"""
        while not self._stop_event.is_set():
            # 检查暂停
            with self._lock:
                if self._state == WatcherState.PAUSED:
                    self._stop_event.wait(1.0)
                    continue

            self._scan_all()
            self._stop_event.wait(self._get_min_interval())

    def _scan_all(self) -> None:
        """扫描所有监听文件"""
        with self._lock:
            watches = dict(self._watches)
            snapshots = dict(self._snapshots)

        now = time.time()
        events = []

        for path, config in watches.items():
            # 检查是否到了扫描时间
            last = snapshots.get(path, FileSnapshot(path=path))
            if now - last.last_checked < config.interval:
                continue

            old_snapshot = snapshots.get(path)
            new_snapshot = self._take_snapshot(path, config.checksum)

            with self._lock:
                self._snapshots[path] = new_snapshot
                self._total_scans += 1

            event = self._detect_change(path, old_snapshot, new_snapshot)
            if event:
                events.append(event)

        # 防抖处理
        for event in events:
            self._handle_debounced(event)

    def _handle_debounced(self, event: ChangeEvent) -> None:
        """防抖处理"""
        path = event.path
        now = time.time()

        with self._lock:
            config = self._watches.get(path)
            if config is None:
                return

            debounce = config.debounce

        last_change = self._pending_changes.get(path, 0)

        if now - last_change >= debounce:
            # 超过防抖时间，触发回调
            with self._lock:
                self._pending_changes.pop(path, None)

            self._dispatch_event(event)
        else:
            # 在防抖窗口内，更新时间
            with self._lock:
                self._pending_changes[path] = now

    def _dispatch_event(self, event: ChangeEvent) -> None:
        """分发变更事件"""
        self._record_event(event)

        with self._lock:
            callbacks = list(self._callbacks)

        for callback in callbacks:
            try:
                callback(event)
            except Exception:
                pass

    def _record_event(self, event: ChangeEvent) -> None:
        """记录变更事件"""
        with self._lock:
            self._history.append(event)
            self._total_changes += 1

    def _detect_change(
        self,
        path: str,
        old: Optional[FileSnapshot],
        new: FileSnapshot
    ) -> Optional[ChangeEvent]:
        """检测变更"""
        if old is None:
            return None

        if not old.exists and new.exists:
            return ChangeEvent(
                path=path,
                change_type=ChangeType.CREATED,
                old_snapshot=old,
                new_snapshot=new,
            )
        elif old.exists and not new.exists:
            return ChangeEvent(
                path=path,
                change_type=ChangeType.DELETED,
                old_snapshot=old,
                new_snapshot=new,
            )
        elif old.exists and new.exists:
            if old.mtime != new.mtime or old.size != new.size:
                # 进一步检查MD5（如果启用）
                if old.md5 and new.md5 and old.md5 == new.md5:
                    return None  # 内容未变
                return ChangeEvent(
                    path=path,
                    change_type=ChangeType.MODIFIED,
                    old_snapshot=old,
                    new_snapshot=new,
                )

        return None

    def _take_snapshot(self, path: str, use_checksum: bool = False) -> FileSnapshot:
        """获取文件快照"""
        snapshot = FileSnapshot(path=path, last_checked=time.time())

        try:
            if os.path.isfile(path):
                stat = os.stat(path)
                snapshot.exists = True
                snapshot.mtime = stat.st_mtime
                snapshot.size = stat.st_size

                if use_checksum:
                    snapshot.md5 = self._compute_md5(path)
            elif os.path.isdir(path):
                snapshot.exists = True
                snapshot.mtime = os.stat(path).st_mtime
        except (OSError, IOError):
            snapshot.exists = False

        return snapshot

    def _compute_md5(self, path: str) -> str:
        """计算文件MD5"""
        try:
            h = hashlib.md5()
            with open(path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            return ""

    def _get_min_interval(self) -> float:
        """获取最小轮询间隔"""
        with self._lock:
            if not self._watches:
                return 2.0
            return min(w.interval for w in self._watches.values())


# ============================================================
# 全局单例
# ============================================================

_config_watcher: Optional[ConfigWatcher] = None
_watcher_lock = threading.RLock()


def get_config_watcher() -> ConfigWatcher:
    """获取全局配置监听器（双重检查锁定）"""
    global _config_watcher
    if _config_watcher is None:
        with _watcher_lock:
            if _config_watcher is None:
                _config_watcher = ConfigWatcher()
    return _config_watcher
