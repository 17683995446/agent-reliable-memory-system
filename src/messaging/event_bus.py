#!/usr/bin/env python3
"""
事件总线 (EventBus) - 阶段337

职责：
- 发布订阅模式：一对多消息分发
- 主题路由：层级主题（a.b.c）、通配符（*、#）
- 同步/异步分发
- 订阅者管理：注册、注销、优先级
- 事件拦截与转换

设计原则：
- 确定性规则，无模型依赖
- 线程安全（RLock）
- 最小层级，无循环依赖
"""

import fnmatch
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from messaging.message_queue import Message, MessageStatus


# ============================================================
# 数据结构
# ============================================================

class DeliveryMode(Enum):
    """分发模式"""
    SYNC = "sync"       # 同步（发布者等待所有订阅者处理完）
    ASYNC = "async"     # 异步（在新线程中分发）
    FANOUT = "fanout"   # 扇出（异步，不等待）


@dataclass
class Subscription:
    """订阅"""
    id: str = ""
    topic: str = ""
    handler: Callable[[Message], None] = None
    priority: int = 100
    filter_headers: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    created_at: float = 0.0
    delivered_count: int = 0
    error_count: int = 0

    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = time.time()
        if not self.id:
            import uuid
            self.id = uuid.uuid4().hex[:8]


@dataclass
class PublishResult:
    """发布结果"""
    topic: str
    message_id: str
    delivered_count: int = 0
    failed_count: int = 0
    duration_ms: float = 0.0


@dataclass
class TopicInfo:
    """主题信息"""
    name: str
    subscriber_count: int = 0
    total_published: int = 0
    total_delivered: int = 0
    created_at: float = 0.0

    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = time.time()


# ============================================================
# 事件总线
# ============================================================

class EventBus:
    """
    事件总线

    核心功能：
    1. 发布订阅模式
    2. 层级主题路由（a.b.c 匹配 a.b.* 和 a.#）
    3. 通配符匹配（* = 一层，# = 多层）
    4. 同步/异步分发
    5. 订阅者优先级排序
    6. 订阅者过滤
    """

    def __init__(self, delivery_mode: DeliveryMode = DeliveryMode.SYNC):
        self._subscriptions: Dict[str, List[Subscription]] = defaultdict(list)
        self._topics: Dict[str, TopicInfo] = {}
        self._lock = threading.RLock()
        self._delivery_mode = delivery_mode
        self._interceptors: List[Callable[[Message], Optional[Message]]] = []
        self._total_published = 0
        self._total_delivered = 0
        self._total_failed = 0

    # ---- 订阅管理 ----

    def subscribe(
        self,
        topic: str,
        handler: Callable[[Message], None],
        priority: int = 100,
        filter_headers: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        订阅主题

        Args:
            topic: 主题（支持通配符）
            handler: 处理函数
            priority: 优先级（越小越先执行）
            filter_headers: 头部过滤条件

        Returns:
            订阅ID
        """
        sub = Subscription(
            topic=topic,
            handler=handler,
            priority=priority,
            filter_headers=filter_headers or {},
        )

        with self._lock:
            self._subscriptions[topic].append(sub)
            self._subscriptions[topic].sort(key=lambda s: s.priority)
            self._ensure_topic(topic)

        return sub.id

    def unsubscribe(self, subscription_id: str) -> bool:
        """取消订阅"""
        with self._lock:
            for topic, subs in self._subscriptions.items():
                for i, sub in enumerate(subs):
                    if sub.id == subscription_id:
                        subs.pop(i)
                        return True
            return False

    def unsubscribe_by_topic(self, topic: str) -> int:
        """取消主题下所有订阅"""
        with self._lock:
            subs = self._subscriptions.pop(topic, [])
            return len(subs)

    def get_subscribers(self, topic: str) -> List[Dict[str, Any]]:
        """获取主题的订阅者列表"""
        with self._lock:
            subs = self._subscriptions.get(topic, [])
            return [
                {"id": s.id, "topic": s.topic, "priority": s.priority,
                 "delivered": s.delivered_count, "errors": s.error_count}
                for s in subs
            ]

    def list_topics(self) -> List[Dict[str, Any]]:
        """列出所有主题"""
        with self._lock:
            return [
                {"name": t.name, "subscribers": t.subscriber_count,
                 "published": t.total_published, "delivered": t.total_delivered}
                for t in self._topics.values()
            ]

    # ---- 发布 ----

    def publish(self, topic: str, payload: Any = None,
                 headers: Optional[Dict[str, str]] = None) -> PublishResult:
        """
        发布事件

        Args:
            topic: 主题
            payload: 消息载荷
            headers: 消息头部

        Returns:
            发布结果
        """
        start = time.monotonic()

        message = Message(
            topic=topic,
            payload=payload,
            headers=headers or {},
        )

        # 拦截器
        for interceptor in self._interceptors:
            try:
                result = interceptor(message)
                if result is None:
                    return PublishResult(topic, message.id, 0, 0, 0)
                message = result
            except Exception:
                pass

        # 匹配订阅者
        subscribers = self._match_subscribers(topic, message)

        delivered = 0
        failed = 0

        for sub in subscribers:
            if not sub.enabled:
                continue

            try:
                if self._delivery_mode == DeliveryMode.SYNC:
                    sub.handler(message)
                elif self._delivery_mode == DeliveryMode.ASYNC:
                    t = threading.Thread(target=sub.handler, args=(message,), daemon=True)
                    t.start()
                elif self._delivery_mode == DeliveryMode.FANOUT:
                    t = threading.Thread(target=sub.handler, args=(message,), daemon=True)
                    t.start()
                sub.delivered_count += 1
                delivered += 1
            except Exception:
                sub.error_count += 1
                failed += 1

        # 更新统计
        duration = (time.monotonic() - start) * 1000
        with self._lock:
            self._total_published += 1
            self._total_delivered += delivered
            self._total_failed += failed
            if topic in self._topics:
                self._topics[topic].total_published += 1
                self._topics[topic].total_delivered += delivered

        return PublishResult(
            topic=topic,
            message_id=message.id,
            delivered_count=delivered,
            failed_count=failed,
            duration_ms=duration,
        )

    # ---- 拦截器 ----

    def add_interceptor(self, interceptor: Callable[[Message], Optional[Message]]) -> None:
        """添加拦截器（返回None则丢弃消息）"""
        with self._lock:
            self._interceptors.append(interceptor)

    def clear_interceptors(self) -> None:
        """清除所有拦截器"""
        with self._lock:
            self._interceptors.clear()

    # ---- 统计 ----

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "total_topics": len(self._topics),
                "total_subscriptions": sum(len(s) for s in self._subscriptions.values()),
                "total_published": self._total_published,
                "total_delivered": self._total_delivered,
                "total_failed": self._total_failed,
                "delivery_mode": self._delivery_mode.value,
                "interceptors": len(self._interceptors),
            }

    # ---- 内部方法 ----

    def _match_subscribers(self, topic: str, message: Message) -> List[Subscription]:
        """匹配主题的订阅者"""
        with self._lock:
            matched = []
            for pattern, subs in self._subscriptions.items():
                if self._topic_matches(topic, pattern):
                    for sub in subs:
                        # 头部过滤
                        if sub.filter_headers:
                            match = True
                            for k, v in sub.filter_headers.items():
                                if message.headers.get(k) != v:
                                    match = False
                                    break
                            if not match:
                                continue
                        matched.append(sub)
            matched.sort(key=lambda s: s.priority)
            return matched

    @staticmethod
    def _topic_matches(topic: str, pattern: str) -> bool:
        """主题匹配（支持 * 和 # 通配符）"""
        if pattern == topic:
            return True
        if "#" in pattern:
            prefix = pattern.split("#")[0]
            return topic.startswith(prefix.rstrip("."))
        if "*" in pattern:
            parts = pattern.split(".")
            topic_parts = topic.split(".")
            if len(parts) != len(topic_parts):
                return False
            return all(
                p == "*" or p == t
                for p, t in zip(parts, topic_parts)
            )
        return False

    def _ensure_topic(self, topic: str) -> None:
        """确保主题信息存在"""
        if topic not in self._topics:
            self._topics[topic] = TopicInfo(name=topic)
        self._topics[topic].subscriber_count = len(self._subscriptions.get(topic, []))


# ============================================================
# 全局单例
# ============================================================

_event_bus: Optional[EventBus] = None
_eb_lock = threading.RLock()


def get_event_bus() -> EventBus:
    """获取全局事件总线"""
    global _event_bus
    if _event_bus is None:
        with _eb_lock:
            if _event_bus is None:
                _event_bus = EventBus()
    return _event_bus
