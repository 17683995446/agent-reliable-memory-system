#!/usr/bin/env python3
"""
事件溯源 - 阶段275-277

功能：
- 阶段275: 事件存储 - 追加事件、查询事件、获取事件流
- 阶段276: 事件回放 - 重放事件、回放到指定版本、事件投影
- 阶段277: 快照管理 - 创建快照、获取最新快照、从快照恢复

设计原则：
- 确定性算法，无模型依赖
- 线程安全，RLock保护
- 单例模式，全局唯一
"""

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Callable, Any, Optional


# ============================================================
# 枚举定义
# ============================================================

class EventType(Enum):
    """事件类型枚举"""
    CREATED = "created"      # 创建事件
    UPDATED = "updated"      # 更新事件
    DELETED = "deleted"      # 删除事件
    SNAPSHOT = "snapshot"    # 快照事件
    CUSTOM = "custom"        # 自定义事件


# ============================================================
# 数据结构定义
# ============================================================

@dataclass
class DomainEvent:
    """领域事件"""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    aggregate_id: str = ""
    event_type: EventType = EventType.CUSTOM
    version: int = 0
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Snapshot:
    """聚合快照"""
    aggregate_id: str = ""
    version: int = 0
    state_data: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class EventStream:
    """事件流"""
    aggregate_id: str = ""
    events: List[DomainEvent] = field(default_factory=list)
    current_version: int = 0
    snapshot_version: int = 0


# ============================================================
# 阶段275: 事件存储
# ============================================================

class EventSourcing:
    """
    事件溯源系统

    职责：
    - 阶段275: 事件追加、查询、事件流获取
    - 阶段276: 事件回放、版本回放、事件投影
    - 阶段277: 快照创建、快照查询、快照恢复
    """

    def __init__(self, snapshot_interval: int = 10):
        self._lock = threading.RLock()
        # 事件存储 {aggregate_id: List[DomainEvent]}
        self._event_store: Dict[str, List[DomainEvent]] = {}
        # 快照存储 {aggregate_id: List[Snapshot]}
        self._snapshot_store: Dict[str, List[Snapshot]] = {}
        # 版本计数器 {aggregate_id: current_version}
        self._version_counter: Dict[str, int] = {}
        # 阶段277: 快照间隔
        self._snapshot_interval = snapshot_interval

    # --------------------------------------------------------
    # 阶段275: 事件存储
    # --------------------------------------------------------

    def append_event(
        self,
        aggregate_id: str,
        event_type: EventType,
        data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        追加事件

        为指定聚合根追加一个领域事件，自动递增版本号。

        Args:
            aggregate_id: 聚合根标识
            event_type: 事件类型
            data: 事件数据
            metadata: 事件元数据

        Returns:
            str: 事件ID
        """
        with self._lock:
            # 递增版本号
            current_version = self._version_counter.get(aggregate_id, 0)
            new_version = current_version + 1
            self._version_counter[aggregate_id] = new_version

            # 创建领域事件
            event = DomainEvent(
                event_id=str(uuid.uuid4()),
                aggregate_id=aggregate_id,
                event_type=event_type,
                version=new_version,
                data=data if data is not None else {},
                metadata=metadata if metadata is not None else {},
                timestamp=datetime.now().isoformat(),
            )

            # 存储事件
            if aggregate_id not in self._event_store:
                self._event_store[aggregate_id] = []
            self._event_store[aggregate_id].append(event)

            # 阶段277: 检查是否需要自动创建快照
            if new_version % self._snapshot_interval == 0:
                self._auto_snapshot(aggregate_id, new_version)

            return event.event_id

    def get_events(
        self,
        aggregate_id: str,
        from_version: int = 0,
        to_version: Optional[int] = None,
    ) -> List[DomainEvent]:
        """
        查询事件

        获取指定聚合根在版本范围内的事件列表。

        Args:
            aggregate_id: 聚合根标识
            from_version: 起始版本（包含），0表示从第一个事件开始
            to_version: 结束版本（包含），None表示到最新版本

        Returns:
            List[DomainEvent]: 事件列表
        """
        with self._lock:
            events = self._event_store.get(aggregate_id, [])
            if not events:
                return []
            # 确定结束版本
            if to_version is None:
                to_version = self._version_counter.get(aggregate_id, 0)
            # 按版本范围过滤
            result = [
                e for e in events
                if from_version <= e.version <= to_version
            ]
            return result

    def get_event_stream(self, aggregate_id: str) -> EventStream:
        """
        获取事件流

        返回指定聚合根的完整事件流信息。

        Args:
            aggregate_id: 聚合根标识

        Returns:
            EventStream: 事件流对象
        """
        with self._lock:
            events = self._event_store.get(aggregate_id, [])
            current_version = self._version_counter.get(aggregate_id, 0)
            # 获取最新快照版本
            snapshot_version = 0
            snapshots = self._snapshot_store.get(aggregate_id, [])
            if snapshots:
                snapshot_version = snapshots[-1].version

            return EventStream(
                aggregate_id=aggregate_id,
                events=list(events),
                current_version=current_version,
                snapshot_version=snapshot_version,
            )

    # --------------------------------------------------------
    # 阶段276: 事件回放
    # --------------------------------------------------------

    def replay_events(
        self,
        aggregate_id: str,
        from_version: int = 0,
        handler: Optional[Callable[[DomainEvent], None]] = None,
    ) -> int:
        """
        回放事件

        从指定版本开始回放所有事件，依次调用处理函数。

        Args:
            aggregate_id: 聚合根标识
            from_version: 起始版本（包含）
            handler: 事件处理函数

        Returns:
            int: 回放的事件数量
        """
        with self._lock:
            events = self.get_events(aggregate_id, from_version=from_version)
            count = 0
            for event in events:
                if handler is not None:
                    try:
                        handler(event)
                    except Exception:
                        # 回放过程中异常不中断，继续处理后续事件
                        pass
                count += 1
            return count

    def replay_to_version(
        self,
        aggregate_id: str,
        target_version: int,
        handler: Optional[Callable[[DomainEvent], None]] = None,
    ) -> int:
        """
        回放到指定版本

        从第一个事件开始回放，直到达到目标版本。

        Args:
            aggregate_id: 聚合根标识
            target_version: 目标版本（包含）
            handler: 事件处理函数

        Returns:
            int: 回放的事件数量
        """
        with self._lock:
            events = self.get_events(
                aggregate_id,
                from_version=0,
                to_version=target_version,
            )
            count = 0
            for event in events:
                if handler is not None:
                    try:
                        handler(event)
                    except Exception:
                        pass
                count += 1
            return count

    def project_events(
        self,
        aggregate_id: str,
        projection_fn: Callable[[List[DomainEvent]], Any],
    ) -> Any:
        """
        事件投影

        将聚合根的所有事件应用投影函数，生成投影结果。
        投影函数接收完整事件列表，返回任意类型的投影结果。

        Args:
            aggregate_id: 聚合根标识
            projection_fn: 投影函数

        Returns:
            Any: 投影结果
        """
        with self._lock:
            events = self._event_store.get(aggregate_id, [])
            if not events:
                return projection_fn([])
            try:
                return projection_fn(list(events))
            except Exception:
                return None

    # --------------------------------------------------------
    # 阶段277: 快照管理
    # --------------------------------------------------------

    def create_snapshot(
        self,
        aggregate_id: str,
        state_data: Dict[str, Any],
    ) -> Snapshot:
        """
        创建快照

        为指定聚合根在当前版本创建快照。

        Args:
            aggregate_id: 聚合根标识
            state_data: 状态数据

        Returns:
            Snapshot: 创建的快照对象
        """
        with self._lock:
            current_version = self._version_counter.get(aggregate_id, 0)
            snapshot = Snapshot(
                aggregate_id=aggregate_id,
                version=current_version,
                state_data=state_data if state_data is not None else {},
                timestamp=datetime.now().isoformat(),
            )
            if aggregate_id not in self._snapshot_store:
                self._snapshot_store[aggregate_id] = []
            self._snapshot_store[aggregate_id].append(snapshot)
            return snapshot

    def get_latest_snapshot(self, aggregate_id: str) -> Optional[Snapshot]:
        """
        获取最新快照

        Args:
            aggregate_id: 聚合根标识

        Returns:
            Optional[Snapshot]: 最新快照，不存在返回None
        """
        with self._lock:
            snapshots = self._snapshot_store.get(aggregate_id, [])
            if not snapshots:
                return None
            return snapshots[-1]

    def restore_from_snapshot(self, aggregate_id: str) -> EventStream:
        """
        从最新快照恢复事件流

        返回从最新快照版本之后的所有事件构成的事件流。
        如果没有快照，返回完整事件流。

        Args:
            aggregate_id: 聚合根标识

        Returns:
            EventStream: 从快照恢复的事件流
        """
        with self._lock:
            snapshot = self.get_latest_snapshot(aggregate_id)
            current_version = self._version_counter.get(aggregate_id, 0)

            if snapshot is None:
                # 无快照，返回完整事件流
                return self.get_event_stream(aggregate_id)

            # 获取快照版本之后的所有事件
            events = self.get_events(
                aggregate_id,
                from_version=snapshot.version + 1,
            )

            return EventStream(
                aggregate_id=aggregate_id,
                events=events,
                current_version=current_version,
                snapshot_version=snapshot.version,
            )

    def _auto_snapshot(self, aggregate_id: str, version: int) -> Optional[Snapshot]:
        """
        自动创建快照（内部方法）

        当事件版本达到快照间隔时自动触发。
        通过回放事件重建状态数据作为快照内容。
        注意：自动快照的状态数据为空字典，需要外部配合投影使用。

        Args:
            aggregate_id: 聚合根标识
            version: 当前版本

        Returns:
            Optional[Snapshot]: 创建的快照
        """
        # 自动快照存储空状态，实际场景中可通过 project_events 获取状态
        snapshot = Snapshot(
            aggregate_id=aggregate_id,
            version=version,
            state_data={},
            timestamp=datetime.now().isoformat(),
        )
        if aggregate_id not in self._snapshot_store:
            self._snapshot_store[aggregate_id] = []
        self._snapshot_store[aggregate_id].append(snapshot)
        return snapshot

    # --------------------------------------------------------
    # 查询与管理方法
    # --------------------------------------------------------

    def get_aggregate_version(self, aggregate_id: str) -> int:
        """
        获取聚合根当前版本

        Args:
            aggregate_id: 聚合根标识

        Returns:
            int: 当前版本号，不存在返回0
        """
        with self._lock:
            return self._version_counter.get(aggregate_id, 0)

    def list_aggregates(self) -> List[str]:
        """
        列出所有聚合根ID

        Returns:
            List[str]: 聚合根ID列表
        """
        with self._lock:
            return sorted(self._event_store.keys())

    def get_event_count(self, aggregate_id: str) -> int:
        """
        获取聚合根的事件总数

        Args:
            aggregate_id: 聚合根标识

        Returns:
            int: 事件数量
        """
        with self._lock:
            events = self._event_store.get(aggregate_id, [])
            return len(events)

    def get_snapshot_count(self, aggregate_id: str) -> int:
        """
        获取聚合根的快照总数

        Args:
            aggregate_id: 聚合根标识

        Returns:
            int: 快照数量
        """
        with self._lock:
            snapshots = self._snapshot_store.get(aggregate_id, [])
            return len(snapshots)

    def delete_aggregate(self, aggregate_id: str) -> bool:
        """
        删除聚合根的所有事件和快照

        Args:
            aggregate_id: 聚合根标识

        Returns:
            bool: 是否删除成功
        """
        with self._lock:
            if aggregate_id not in self._event_store:
                return False
            del self._event_store[aggregate_id]
            self._snapshot_store.pop(aggregate_id, None)
            self._version_counter.pop(aggregate_id, None)
            return True


# ============================================================
# 全局单例
# ============================================================

_event_sourcing_instance: Optional[EventSourcing] = None
_event_sourcing_lock = threading.RLock()


def get_event_sourcing() -> EventSourcing:
    """
    获取事件溯源系统全局单例

    Returns:
        EventSourcing: 事件溯源系统实例
    """
    global _event_sourcing_instance
    with _event_sourcing_lock:
        if _event_sourcing_instance is None:
            _event_sourcing_instance = EventSourcing()
        return _event_sourcing_instance
