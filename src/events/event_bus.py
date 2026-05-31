#!/usr/bin/env python3
"""
事件总线 - 阶段131-133
实现发布/订阅模式的事件驱动架构
"""

import threading
from typing import Dict, List, Callable, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
from datetime import datetime


class EventType(Enum):
    """系统事件类型"""
    MEMORY_CREATED = "memory.created"
    MEMORY_RECALLED = "memory.recalled"
    MEMORY_DELETED = "memory.deleted"
    MEMORY_UPDATED = "memory.updated"
    MEMORY_EXPIRED = "memory.expired"
    MEMORY_SHARED = "memory.shared"
    MEMORY_IMPORTED = "memory.imported"
    MEMORY_EXPORTED = "memory.exported"
    TASK_STARTED = "task.started"
    TASK_ENDED = "task.ended"
    TASK_REVIEWED = "task.reviewed"
    SYSTEM_ERROR = "system.error"
    SYSTEM_HEALTH = "system.health"
    CONFIG_CHANGED = "config.changed"
    CUSTOM = "custom"


@dataclass
class Event:
    """事件对象"""
    type: EventType
    data: Dict[str, Any] = field(default_factory=dict)
    source: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    event_id: str = ""

    def __post_init__(self):
        if not self.event_id:
            import uuid
            self.event_id = str(uuid.uuid4())[:8]


@dataclass
class Subscription:
    """订阅信息"""
    callback: Callable[[Event], None]
    event_type: EventType
    subscriber_id: str
    filter_fn: Optional[Callable[[Event], bool]] = None
    once: bool = False  # 是否只触发一次


class EventBus:
    """
    事件总线
    
    实现发布/订阅模式，支持：
    - 多订阅者
    - 事件过滤
    - 一次性订阅
    - 异步分发
    - 事件历史
    """

    def __init__(self, max_history: int = 1000):
        self._subscriptions: Dict[EventType, List[Subscription]] = defaultdict(list)
        self._lock = threading.RLock()
        self._event_history: List[Event] = []
        self._max_history = max_history
        self._stats = {
            "published": 0,
            "delivered": 0,
            "failed": 0,
        }

    def subscribe(
        self,
        event_type: EventType,
        callback: Callable[[Event], None],
        subscriber_id: str = "default",
        filter_fn: Optional[Callable[[Event], bool]] = None,
        once: bool = False
    ) -> str:
        """
        订阅事件

        Args:
            event_type: 事件类型
            callback: 回调函数
            subscriber_id: 订阅者标识
            filter_fn: 过滤函数，返回True才触发
            once: 是否只触发一次

        Returns:
            订阅ID
        """
        sub = Subscription(
            callback=callback,
            event_type=event_type,
            subscriber_id=subscriber_id,
            filter_fn=filter_fn,
            once=once,
        )
        with self._lock:
            self._subscriptions[event_type].append(sub)
        return f"{subscriber_id}:{event_type.value}"

    def unsubscribe(self, subscriber_id: str, event_type: Optional[EventType] = None):
        """
        取消订阅

        Args:
            subscriber_id: 订阅者标识
            event_type: 事件类型（None取消所有）
        """
        with self._lock:
            if event_type:
                subs = self._subscriptions.get(event_type, [])
                self._subscriptions[event_type] = [
                    s for s in subs if s.subscriber_id != subscriber_id
                ]
            else:
                for et in self._subscriptions:
                    self._subscriptions[et] = [
                        s for s in self._subscriptions[et]
                        if s.subscriber_id != subscriber_id
                    ]

    def publish(self, event: Event):
        """
        发布事件

        Args:
            event: 事件对象
        """
        with self._lock:
            self._stats["published"] += 1
            # 记录历史
            self._event_history.append(event)
            if len(self._event_history) > self._max_history:
                self._event_history = self._event_history[-self._max_history:]

        # 获取订阅者
        with self._lock:
            subs = list(self._subscriptions.get(event.type, []))
            # 同时通知 CUSTOM 类型的订阅者
            if event.type != EventType.CUSTOM:
                subs.extend(self._subscriptions.get(EventType.CUSTOM, []))

        # 分发事件
        to_remove = []
        for sub in subs:
            try:
                # 过滤检查
                if sub.filter_fn and not sub.filter_fn(event):
                    continue
                sub.callback(event)
                self._stats["delivered"] += 1
                if sub.once:
                    to_remove.append(sub)
            except Exception as e:
                self._stats["failed"] += 1

        # 移除一次性订阅
        if to_remove:
            with self._lock:
                for sub in to_remove:
                    if sub in self._subscriptions.get(event.type, []):
                        self._subscriptions[event.type].remove(sub)

    def publish_simple(self, event_type: EventType, data: Dict[str, Any] = None, source: str = ""):
        """便捷发布方法"""
        event = Event(type=event_type, data=data or {}, source=source)
        self.publish(event)

    def get_history(
        self,
        event_type: Optional[EventType] = None,
        limit: int = 50
    ) -> List[Event]:
        """
        获取事件历史

        Args:
            event_type: 事件类型过滤
            limit: 返回数量
        """
        with self._lock:
            events = self._event_history
            if event_type:
                events = [e for e in events if e.type == event_type]
            return list(reversed(events[-limit:]))

    def get_subscribers(self, event_type: EventType) -> List[str]:
        """获取指定事件类型的订阅者列表"""
        with self._lock:
            subs = self._subscriptions.get(event_type, [])
            return [s.subscriber_id for s in subs]

    def get_stats(self) -> Dict[str, Any]:
        """获取事件总线统计"""
        with self._lock:
            return {
                **self._stats,
                "active_subscriptions": sum(
                    len(subs) for subs in self._subscriptions.values()
                ),
                "event_types": len(self._subscriptions),
                "history_size": len(self._event_history),
            }

    def clear_history(self):
        """清空事件历史"""
        with self._lock:
            self._event_history.clear()


# 全局事件总线
_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """获取全局事件总线"""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus
