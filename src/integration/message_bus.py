#!/usr/bin/env python3
"""
消息总线 - 阶段266-268

功能：
- 阶段266: 发布订阅 - 主题订阅、取消订阅、消息发布
- 阶段267: 消息路由 - DIRECT/FANOUT/TOPIC 模式路由，支持通配符匹配
- 阶段268: 死信队列 - 消息重试、死信存储、死信重发

设计原则：
- 确定性规则，无模型依赖
- 线程安全，RLock保护
- 单例模式，全局唯一
"""

import threading
import uuid
import time
import fnmatch
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Callable, Any, Optional, Tuple


# ============================================================
# 枚举定义
# ============================================================

class DeliveryMode(Enum):
    """消息投递模式"""
    DIRECT = "direct"    # 直连模式：精确匹配主题
    FANOUT = "fanout"    # 扇出模式：广播到所有订阅者
    TOPIC = "topic"      # 主题模式：支持通配符匹配（*）


class MessageStatus(Enum):
    """消息状态"""
    PENDING = "pending"      # 待投递
    DELIVERED = "delivered"  # 已投递
    FAILED = "failed"        # 投递失败
    DEAD = "dead"            # 死信


# ============================================================
# 数据结构定义
# ============================================================

@dataclass
class Message:
    """消息对象"""
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    topic: str = ""
    payload: Any = None
    headers: Dict[str, str] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    delivery_mode: DeliveryMode = DeliveryMode.DIRECT
    status: MessageStatus = MessageStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3


@dataclass
class Subscription:
    """订阅信息"""
    sub_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    topic: str = ""
    handler: Callable[[Message], None] = None
    filter_fn: Optional[Callable[[Message], bool]] = None


@dataclass
class DeadLetterEntry:
    """死信条目"""
    message: Message = None
    reason: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


# ============================================================
# 消息总线核心实现
# ============================================================

class MessageBus:
    """
    消息总线

    实现发布/订阅模式，支持：
    - 多种投递模式（DIRECT/FANOUT/TOPIC）
    - 消息过滤
    - 死信队列与自动重试
    - 线程安全的并发访问
    """

    def __init__(self, max_retries: int = 3):
        self._lock = threading.RLock()
        # 阶段266: 订阅存储
        self._subscriptions: Dict[str, List[Subscription]] = {}
        self._all_subscriptions: List[Subscription] = []  # FANOUT 模式订阅者
        # 阶段267: 路由相关
        self._topic_subscriptions: List[Subscription] = []  # TOPIC 模式订阅者（含通配符）
        # 阶段268: 死信队列
        self._dead_letter_queue: List[DeadLetterEntry] = []
        self._max_retries = max_retries
        # 统计信息
        self._stats = {
            "published": 0,
            "delivered": 0,
            "failed": 0,
            "dead_lettered": 0,
            "retried": 0,
        }

    # ========================================================
    # 阶段266: 发布订阅
    # ========================================================

    def subscribe(
        self,
        topic: str,
        handler: Callable[[Message], None],
        filter_fn: Optional[Callable[[Message], bool]] = None
    ) -> str:
        """
        订阅主题

        Args:
            topic: 订阅的主题名称
            handler: 消息处理回调函数
            filter_fn: 可选的消息过滤函数，返回True则处理

        Returns:
            sub_id: 订阅ID，用于取消订阅
        """
        with self._lock:
            sub = Subscription(
                topic=topic,
                handler=handler,
                filter_fn=filter_fn,
            )
            if topic not in self._subscriptions:
                self._subscriptions[topic] = []
            self._subscriptions[topic].append(sub)
            return sub.sub_id

    def subscribe_topic(
        self,
        topic_pattern: str,
        handler: Callable[[Message], None],
        filter_fn: Optional[Callable[[Message], bool]] = None
    ) -> str:
        """
        订阅主题模式（支持通配符 *）

        Args:
            topic_pattern: 主题模式，支持 * 通配符（如 "order.*"）
            handler: 消息处理回调函数
            filter_fn: 可选的消息过滤函数

        Returns:
            sub_id: 订阅ID
        """
        with self._lock:
            sub = Subscription(
                topic=topic_pattern,
                handler=handler,
                filter_fn=filter_fn,
            )
            self._topic_subscriptions.append(sub)
            return sub.sub_id

    def unsubscribe(self, sub_id: str) -> bool:
        """
        取消订阅

        Args:
            sub_id: 订阅ID

        Returns:
            bool: 是否成功取消
        """
        with self._lock:
            # 在精确匹配订阅中查找
            for topic, subs in self._subscriptions.items():
                for i, sub in enumerate(subs):
                    if sub.sub_id == sub_id:
                        subs.pop(i)
                        if not subs:
                            del self._subscriptions[topic]
                        return True
            # 在通配符主题订阅中查找
            for i, sub in enumerate(self._topic_subscriptions):
                if sub.sub_id == sub_id:
                    self._topic_subscriptions.pop(i)
                    return True
            # 在扇出订阅中查找
            for i, sub in enumerate(self._all_subscriptions):
                if sub.sub_id == sub_id:
                    self._all_subscriptions.pop(i)
                    return True
            return False

    def publish(
        self,
        topic: str,
        payload: Any,
        headers: Optional[Dict[str, str]] = None,
        delivery_mode: DeliveryMode = DeliveryMode.DIRECT
    ) -> str:
        """
        发布消息

        Args:
            topic: 消息主题
            payload: 消息内容
            headers: 消息头信息
            delivery_mode: 投递模式

        Returns:
            message_id: 消息ID
        """
        message = Message(
            topic=topic,
            payload=payload,
            headers=headers or {},
            delivery_mode=delivery_mode,
            max_retries=self._max_retries,
        )
        with self._lock:
            self._stats["published"] += 1
        self.route_message(message)
        return message.message_id

    # ========================================================
    # 阶段267: 消息路由
    # ========================================================

    def route_message(self, message: Message) -> None:
        """
        路由消息到匹配的订阅者（内部方法）

        根据消息的投递模式选择不同的路由策略：
        - DIRECT: 精确匹配主题的订阅者
        - FANOUT: 广播到所有扇出订阅者
        - TOPIC: 通配符匹配主题模式的订阅者

        Args:
            message: 待路由的消息
        """
        if message.delivery_mode == DeliveryMode.DIRECT:
            self._route_direct(message)
        elif message.delivery_mode == DeliveryMode.FANOUT:
            self._route_fanout(message)
        elif message.delivery_mode == DeliveryMode.TOPIC:
            self._route_topic(message)
        else:
            # 未知模式，按DIRECT处理
            self._route_direct(message)

    def _route_direct(self, message: Message) -> None:
        """
        直连路由：精确匹配主题

        将消息投递到订阅了相同主题的所有订阅者。
        """
        with self._lock:
            subscribers = self._subscriptions.get(message.topic, [])
            # 复制列表以避免迭代中修改
            targets = list(subscribers)

        if not targets:
            # 无订阅者，不进入死信队列（消息被静默丢弃）
            return

        for sub in targets:
            self._deliver_to_subscriber(message, sub)

    def _route_fanout(self, message: Message) -> None:
        """
        扇出路由：广播到所有扇出订阅者

        忽略主题匹配，将消息发送给所有注册了扇出模式的订阅者。
        """
        with self._lock:
            targets = list(self._all_subscriptions)

        if not targets:
            return

        for sub in targets:
            self._deliver_to_subscriber(message, sub)

    def _route_topic(self, message: Message) -> None:
        """
        主题路由：通配符匹配

        使用通配符模式匹配主题，支持 '*' 作为单层通配符。
        例如 "order.*" 可以匹配 "order.created"、"order.cancelled" 等。
        同时也会匹配精确订阅。
        """
        delivered = False

        # 先匹配精确订阅
        with self._lock:
            exact_subs = list(self._subscriptions.get(message.topic, []))

        for sub in exact_subs:
            self._deliver_to_subscriber(message, sub)
            delivered = True

        # 再匹配通配符主题订阅
        with self._lock:
            topic_subs = list(self._topic_subscriptions)

        for sub in topic_subs:
            if self._topic_matches(message.topic, sub.topic):
                self._deliver_to_subscriber(message, sub)
                delivered = True

        if not delivered:
            # 无匹配的订阅者
            return

    @staticmethod
    def _topic_matches(message_topic: str, pattern: str) -> bool:
        """
        主题通配符匹配

        使用 fnmatch 进行模式匹配，支持 '*' 通配符。
        '*' 匹配任意数量的非分隔符字符。

        Args:
            message_topic: 消息的实际主题
            pattern: 订阅的主题模式

        Returns:
            bool: 是否匹配
        """
        return fnmatch.fnmatch(message_topic, pattern)

    def _deliver_to_subscriber(self, message: Message, sub: Subscription) -> None:
        """
        投递消息到单个订阅者

        执行过滤检查，调用处理函数，处理失败时进行重试或移入死信队列。

        Args:
            message: 待投递的消息
            sub: 目标订阅者
        """
        # 过滤检查
        if sub.filter_fn is not None:
            try:
                if not sub.filter_fn(message):
                    return  # 过滤掉，不投递
            except Exception:
                return  # 过滤函数异常，跳过此订阅者

        # 投递消息
        try:
            sub.handler(message)
            with self._lock:
                message.status = MessageStatus.DELIVERED
                self._stats["delivered"] += 1
        except Exception as e:
            with self._lock:
                message.retry_count += 1
                self._stats["failed"] += 1

            if message.retry_count >= message.max_retries:
                # 超过最大重试次数，移入死信队列
                self._move_to_dead_letter(message, str(e))
            else:
                # 重试投递
                with self._lock:
                    self._stats["retried"] += 1
                self._deliver_to_subscriber(message, sub)

    # ========================================================
    # 阶段268: 死信队列
    # ========================================================

    def _move_to_dead_letter(self, message: Message, reason: str) -> None:
        """
        将消息移入死信队列

        当消息投递失败次数达到上限时，将消息及其失败原因记录到死信队列中。

        Args:
            message: 投递失败的消息
            reason: 失败原因
        """
        with self._lock:
            message.status = MessageStatus.DEAD
            entry = DeadLetterEntry(
                message=message,
                reason=reason,
            )
            self._dead_letter_queue.append(entry)
            self._stats["dead_lettered"] += 1

    def get_dead_letters(self, limit: int = 100) -> List[DeadLetterEntry]:
        """
        获取死信队列中的消息

        Args:
            limit: 返回的最大条目数

        Returns:
            List[DeadLetterEntry]: 死信条目列表
        """
        with self._lock:
            return list(self._dead_letter_queue[-limit:])

    def retry_dead_letter(self, message_id: str) -> bool:
        """
        重试死信队列中的消息

        从死信队列中取出指定消息，重置其重试计数和状态，
        然后重新路由投递。

        Args:
            message_id: 消息ID

        Returns:
            bool: 是否成功找到并重试
        """
        with self._lock:
            entry = None
            entry_index = -1
            for i, e in enumerate(self._dead_letter_queue):
                if e.message.message_id == message_id:
                    entry = e
                    entry_index = i
                    break

            if entry is None:
                return False

            # 从死信队列中移除
            self._dead_letter_queue.pop(entry_index)

        # 重置消息状态
        message = entry.message
        message.status = MessageStatus.PENDING
        message.retry_count = 0

        # 重新路由
        self.route_message(message)
        return True

    def purge_dead_letters(self) -> int:
        """
        清空死信队列

        Returns:
            int: 清除的死信条目数量
        """
        with self._lock:
            count = len(self._dead_letter_queue)
            self._dead_letter_queue.clear()
            return count

    def get_stats(self) -> Dict[str, int]:
        """
        获取消息总线统计信息

        Returns:
            Dict[str, int]: 统计数据字典
        """
        with self._lock:
            stats = dict(self._stats)
            stats["dead_letter_count"] = len(self._dead_letter_queue)
            stats["subscription_count"] = sum(
                len(subs) for subs in self._subscriptions.values()
            )
            stats["topic_subscription_count"] = len(self._topic_subscriptions)
            stats["fanout_subscription_count"] = len(self._all_subscriptions)
            return stats


# ============================================================
# 全局单例
# ============================================================

_message_bus_instance: Optional[MessageBus] = None
_message_bus_lock = threading.RLock()


def get_message_bus() -> MessageBus:
    """
    获取消息总线全局单例

    Returns:
        MessageBus: 消息总线实例
    """
    global _message_bus_instance
    with _message_bus_lock:
        if _message_bus_instance is None:
            _message_bus_instance = MessageBus()
        return _message_bus_instance
