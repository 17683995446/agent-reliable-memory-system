#!/usr/bin/env python3
"""
消息代理 (MessageBroker) - 阶段338

职责：
- 消息路由：基于规则将消息路由到目标队列或主题
- 负载均衡：轮询、随机、加权、一致性哈希
- 消息确认：ACK/NACK/REQUEUE 确认机制
- 消费者管理：注册、注销、分组
- 代理统计与监控

设计原则：
- 确定性规则，无模型依赖
- 线程安全（RLock + Condition）
- 最小层级，无循环依赖
"""

import hashlib
import random
import threading
import time
from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from messaging.message_queue import (
    BaseQueue, FIFOQueue, Message, MessageStatus, QueueManager, QueueType
)
from messaging.event_bus import EventBus, DeliveryMode


# ============================================================
# 枚举与数据结构
# ============================================================

class AckStatus(Enum):
    """确认状态"""
    PENDING = "pending"
    ACK = "ack"           # 确认处理成功
    NACK = "nack"         # 拒绝，进入死信
    REQUEUE = "requeue"   # 重新入队


class RouteAction(Enum):
    """路由动作"""
    QUEUE = "queue"       # 路由到队列
    TOPIC = "topic"       # 路由到主题（发布）
    DROP = "drop"         # 丢弃
    DELAY = "delay"       # 延迟投递


class LoadBalanceStrategy(Enum):
    """负载均衡策略"""
    ROUND_ROBIN = "round_robin"       # 轮询
    RANDOM = "random"                 # 随机
    WEIGHTED = "weighted"             # 加权
    CONSISTENT_HASH = "consistent_hash"  # 一致性哈希


@dataclass
class RouteRule:
    """路由规则"""
    id: str = ""
    name: str = ""
    match_topic: str = ""           # 匹配主题（支持通配符）
    match_headers: Dict[str, str] = field(default_factory=dict)
    action: RouteAction = RouteAction.QUEUE
    target: str = ""               # 目标队列名或主题名
    priority: int = 100            # 规则优先级（越小越先匹配）
    enabled: bool = True
    delay_seconds: float = 0.0     # 延迟秒数（仅 DELAY 动作）

    def __post_init__(self):
        if not self.id:
            import uuid
            self.id = uuid.uuid4().hex[:8]


@dataclass
class Consumer:
    """消费者"""
    id: str = ""
    group: str = ""
    handler: Callable[[Message], AckStatus] = None
    weight: int = 1
    active: bool = True
    processed_count: int = 0
    error_count: int = 0
    last_active: float = 0.0

    def __post_init__(self):
        if not self.id:
            import uuid
            self.id = uuid.uuid4().hex[:8]
        if self.last_active == 0.0:
            self.last_active = time.time()


@dataclass
class InFlightMessage:
    """在途消息（已投递等待确认）"""
    message: Message
    consumer_id: str
    delivered_at: float = 0.0
    ack_status: AckStatus = AckStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3

    def __post_init__(self):
        if self.delivered_at == 0.0:
            self.delivered_at = time.time()

    @property
    def is_expired(self) -> bool:
        """是否超时（30秒未确认）"""
        return (time.time() - self.delivered_at) > 30


@dataclass
class BrokerStats:
    """代理统计"""
    total_routed: int = 0
    total_dropped: int = 0
    total_acked: int = 0
    total_nacked: int = 0
    total_requeued: int = 0
    total_timeout: int = 0
    total_delivered: int = 0
    active_consumers: int = 0
    in_flight_count: int = 0


# ============================================================
# 路由引擎
# ============================================================

class RouteEngine:
    """
    路由引擎

    核心功能：
    1. 规则优先级匹配
    2. 主题通配符匹配
    3. 头部条件过滤
    4. 默认路由（无匹配规则时）
    """

    def __init__(self):
        self._rules: List[RouteRule] = []
        self._lock = threading.RLock()
        self._default_action = RouteAction.QUEUE
        self._default_target = "default"
        self._match_count = 0

    def add_rule(self, rule: RouteRule) -> str:
        """添加路由规则"""
        with self._lock:
            self._rules.append(rule)
            self._rules.sort(key=lambda r: r.priority)
        return rule.id

    def remove_rule(self, rule_id: str) -> bool:
        """移除路由规则"""
        with self._lock:
            for i, r in enumerate(self._rules):
                if r.id == rule_id:
                    self._rules.pop(i)
                    return True
            return False

    def set_default(self, action: RouteAction, target: str = "") -> None:
        """设置默认路由"""
        with self._lock:
            self._default_action = action
            self._default_target = target

    def route(self, message: Message) -> Tuple[RouteAction, str, float]:
        """
        路由消息

        Returns:
            (action, target, delay_seconds)
        """
        with self._lock:
            for rule in self._rules:
                if not rule.enabled:
                    continue
                if self._matches(message, rule):
                    self._match_count += 1
                    return (rule.action, rule.target, rule.delay_seconds)
            self._match_count += 1
            return (self._default_action, self._default_target, 0.0)

    def _matches(self, message: Message, rule: RouteRule) -> bool:
        """检查消息是否匹配规则"""
        # 主题匹配
        if rule.match_topic and not self._topic_matches(message.topic, rule.match_topic):
            return False
        # 头部匹配
        if rule.match_headers:
            for k, v in rule.match_headers.items():
                if message.headers.get(k) != v:
                    return False
        return True

    @staticmethod
    def _topic_matches(topic: str, pattern: str) -> bool:
        """主题通配符匹配"""
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
            return all(p == "*" or p == t for p, t in zip(parts, topic_parts))
        return False

    def list_rules(self) -> List[Dict[str, Any]]:
        """列出所有规则"""
        with self._lock:
            return [
                {
                    "id": r.id, "name": r.name,
                    "match_topic": r.match_topic,
                    "action": r.action.value,
                    "target": r.target,
                    "priority": r.priority,
                    "enabled": r.enabled,
                }
                for r in self._rules
            ]

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "rules": len(self._rules),
                "match_count": self._match_count,
                "default_action": self._default_action.value,
                "default_target": self._default_target,
            }


# ============================================================
# 负载均衡器
# ============================================================

class LoadBalancer:
    """
    负载均衡器

    策略：
    1. ROUND_ROBIN: 轮询
    2. RANDOM: 随机
    3. WEIGHTED: 加权随机
    4. CONSISTENT_HASH: 一致性哈希（相同消息路由到相同消费者）
    """

    def __init__(self, strategy: LoadBalanceStrategy = LoadBalanceStrategy.ROUND_ROBIN):
        self._strategy = strategy
        self._targets: List[str] = []
        self._weights: Dict[str, int] = {}
        self._rr_index = 0
        self._lock = threading.RLock()
        self._ring: List[Tuple[int, str]] = []  # 一致性哈希环
        self._ring_keys: List[int] = []

    def set_strategy(self, strategy: LoadBalanceStrategy) -> None:
        """设置负载均衡策略"""
        with self._lock:
            self._strategy = strategy
            if strategy == LoadBalanceStrategy.CONSISTENT_HASH:
                self._build_ring()

    def register(self, target: str, weight: int = 1) -> None:
        """注册目标"""
        with self._lock:
            if target not in self._targets:
                self._targets.append(target)
            self._weights[target] = weight
            if self._strategy == LoadBalanceStrategy.CONSISTENT_HASH:
                self._build_ring()

    def unregister(self, target: str) -> None:
        """注销目标"""
        with self._lock:
            if target in self._targets:
                self._targets.remove(target)
            self._weights.pop(target, None)
            if self._strategy == LoadBalanceStrategy.CONSISTENT_HASH:
                self._build_ring()

    def select(self, key: str = "") -> Optional[str]:
        """
        选择目标

        Args:
            key: 选择键（一致性哈希用）

        Returns:
            目标名称，无可用目标时返回None
        """
        with self._lock:
            if not self._targets:
                return None

            if self._strategy == LoadBalanceStrategy.ROUND_ROBIN:
                return self._round_robin()
            elif self._strategy == LoadBalanceStrategy.RANDOM:
                return self._random()
            elif self._strategy == LoadBalanceStrategy.WEIGHTED:
                return self._weighted()
            elif self._strategy == LoadBalanceStrategy.CONSISTENT_HASH:
                return self._consistent_hash(key)
            return self._targets[0]

    def _round_robin(self) -> str:
        """轮询"""
        target = self._targets[self._rr_index % len(self._targets)]
        self._rr_index += 1
        return target

    def _random(self) -> str:
        """随机"""
        return random.choice(self._targets)

    def _weighted(self) -> str:
        """加权随机"""
        weights = [self._weights.get(t, 1) for t in self._targets]
        total = sum(weights)
        r = random.randint(1, total)
        cumulative = 0
        for target, w in zip(self._targets, weights):
            cumulative += w
            if r <= cumulative:
                return target
        return self._targets[-1]

    def _consistent_hash(self, key: str) -> str:
        """一致性哈希"""
        if not self._ring or not key:
            return self._targets[0] if self._targets else None
        h = self._hash(key)
        idx = bisect_left(self._ring_keys, h)
        if idx >= len(self._ring_keys):
            idx = 0
        return self._ring[idx][1]

    def _build_ring(self) -> None:
        """构建一致性哈希环（每个目标160个虚拟节点）"""
        self._ring = []
        self._ring_keys = []
        replicas = 160
        for target in self._targets:
            weight = self._weights.get(target, 1)
            count = max(1, replicas * weight // max(sum(self._weights.values()), 1))
            for i in range(count):
                h = self._hash(f"{target}:{i}")
                self._ring.append((h, target))
        self._ring.sort(key=lambda x: x[0])
        self._ring_keys = [r[0] for r in self._ring]

    @staticmethod
    def _hash(key: str) -> int:
        """MD5哈希取前8字节"""
        return int(hashlib.md5(key.encode()).hexdigest()[:8], 16)

    def get_targets(self) -> List[str]:
        """获取所有目标"""
        with self._lock:
            return list(self._targets)

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "strategy": self._strategy.value,
                "targets": len(self._targets),
                "weights": dict(self._weights),
                "ring_size": len(self._ring),
            }


# ============================================================
# 确认管理器
# ============================================================

class AckManager:
    """
    确认管理器

    核心功能：
    1. 跟踪在途消息
    2. ACK/NACK/REQUEUE 处理
    3. 超时自动重发
    4. 重试次数限制
    """

    def __init__(self, timeout_seconds: float = 30.0):
        self._in_flight: Dict[str, InFlightMessage] = {}
        self._lock = threading.RLock()
        self._timeout = timeout_seconds
        self._total_acked = 0
        self._total_nacked = 0
        self._total_requeued = 0
        self._total_timeout = 0

    def track(self, message: Message, consumer_id: str,
              max_retries: int = 3) -> str:
        """
        跟踪消息投递

        Returns:
            追踪ID
        """
        inflight = InFlightMessage(
            message=message,
            consumer_id=consumer_id,
            max_retries=max_retries,
        )
        with self._lock:
            self._in_flight[message.id] = inflight
        return message.id

    def ack(self, message_id: str) -> bool:
        """确认消息处理成功"""
        with self._lock:
            inflight = self._in_flight.pop(message_id, None)
            if inflight is None:
                return False
            inflight.ack_status = AckStatus.ACK
            self._total_acked += 1
            return True

    def nack(self, message_id: str) -> Optional[Message]:
        """拒绝消息（返回消息用于死信处理）"""
        with self._lock:
            inflight = self._in_flight.pop(message_id, None)
            if inflight is None:
                return None
            inflight.ack_status = AckStatus.NACK
            self._total_nacked += 1
            return inflight.message

    def requeue(self, message_id: str) -> Optional[Message]:
        """重新入队（返回消息用于重新投递）"""
        with self._lock:
            inflight = self._in_flight.get(message_id, None)
            if inflight is None:
                return None
            inflight.retry_count += 1
            if inflight.retry_count > inflight.max_retries:
                # 超过重试次数，移除并返回None表示应进入死信
                self._in_flight.pop(message_id, None)
                self._total_nacked += 1
                return None
            inflight.ack_status = AckStatus.REQUEUE
            inflight.delivered_at = time.time()
            self._total_requeued += 1
            return inflight.message

    def check_timeouts(self) -> List[Message]:
        """检查超时消息，返回需要重新投递的消息"""
        timed_out = []
        with self._lock:
            now = time.time()
            expired_ids = []
            for msg_id, inflight in self._in_flight.items():
                if (now - inflight.delivered_at) > self._timeout:
                    expired_ids.append(msg_id)

            for msg_id in expired_ids:
                inflight = self._in_flight[msg_id]
                inflight.retry_count += 1
                self._total_timeout += 1

                if inflight.retry_count > inflight.max_retries:
                    self._in_flight.pop(msg_id)
                    # 超过重试次数，标记为NACK
                    self._total_nacked += 1
                else:
                    inflight.delivered_at = now
                    timed_out.append(inflight.message)

        return timed_out

    def get_in_flight(self) -> List[Dict[str, Any]]:
        """获取在途消息列表"""
        with self._lock:
            return [
                {
                    "message_id": ifm.message.id,
                    "consumer_id": ifm.consumer_id,
                    "status": ifm.ack_status.value,
                    "retry_count": ifm.retry_count,
                    "elapsed": time.time() - ifm.delivered_at,
                }
                for ifm in self._in_flight.values()
            ]

    @property
    def in_flight_count(self) -> int:
        with self._lock:
            return len(self._in_flight)

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "in_flight": len(self._in_flight),
                "total_acked": self._total_acked,
                "total_nacked": self._total_nacked,
                "total_requeued": self._total_requeued,
                "total_timeout": self._total_timeout,
                "timeout_seconds": self._timeout,
            }


# ============================================================
# 消费者组
# ============================================================

class ConsumerGroup:
    """
    消费者组

    核心功能：
    1. 消费者注册/注销
    2. 组内负载均衡
    3. 消息分发
    4. 健康检查
    """

    def __init__(self, name: str, strategy: LoadBalanceStrategy = LoadBalanceStrategy.ROUND_ROBIN):
        self.name = name
        self._consumers: Dict[str, Consumer] = {}
        self._balancer = LoadBalancer(strategy)
        self._lock = threading.RLock()
        self._total_processed = 0

    def register(self, handler: Callable[[Message], AckStatus],
                 weight: int = 1) -> str:
        """注册消费者"""
        consumer = Consumer(
            group=self.name,
            handler=handler,
            weight=weight,
        )
        with self._lock:
            self._consumers[consumer.id] = consumer
            self._balancer.register(consumer.id, weight)
        return consumer.id

    def unregister(self, consumer_id: str) -> bool:
        """注销消费者"""
        with self._lock:
            consumer = self._consumers.pop(consumer_id, None)
            if consumer:
                self._balancer.unregister(consumer_id)
                return True
            return False

    def select_consumer(self, key: str = "") -> Optional[Consumer]:
        """选择消费者"""
        with self._lock:
            cid = self._balancer.select(key)
            if cid:
                return self._consumers.get(cid)
            return None

    def deliver(self, message: Message, key: str = "") -> Optional[str]:
        """
        投递消息给消费者

        Returns:
            消费者ID，无可用消费者返回None
        """
        consumer = self.select_consumer(key)
        if consumer is None or not consumer.active:
            return None

        try:
            consumer.handler(message)
            consumer.processed_count += 1
            consumer.last_active = time.time()
            with self._lock:
                self._total_processed += 1
            return consumer.id
        except Exception:
            consumer.error_count += 1
            return consumer.id

    def get_consumers(self) -> List[Dict[str, Any]]:
        """获取消费者列表"""
        with self._lock:
            return [
                {
                    "id": c.id,
                    "group": c.group,
                    "weight": c.weight,
                    "active": c.active,
                    "processed": c.processed_count,
                    "errors": c.error_count,
                }
                for c in self._consumers.values()
            ]

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._consumers)

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "name": self.name,
                "consumers": len(self._consumers),
                "total_processed": self._total_processed,
                "strategy": self._balancer.get_stats()["strategy"],
            }


# ============================================================
# 消息代理
# ============================================================

class MessageBroker:
    """
    消息代理

    核心功能：
    1. 消息路由：基于规则路由到队列或主题
    2. 负载均衡：多种策略分发消息
    3. 消息确认：ACK/NACK/REQUEUE 机制
    4. 消费者组管理
    5. 统计监控

    协调 QueueManager、EventBus、RouteEngine、AckManager
    """

    def __init__(self):
        self._queue_manager = QueueManager()
        self._event_bus = EventBus()
        self._route_engine = RouteEngine()
        self._ack_manager = AckManager()
        self._consumer_groups: Dict[str, ConsumerGroup] = {}
        self._lock = threading.RLock()
        self._running = False
        self._dispatch_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._stats = BrokerStats()

    # ---- 队列管理 ----

    def create_queue(self, name: str, queue_type: QueueType = QueueType.FIFO,
                     max_size: int = 0) -> BaseQueue:
        """创建队列"""
        return self._queue_manager.create_queue(name, queue_type, max_size)

    def get_queue(self, name: str) -> Optional[BaseQueue]:
        """获取队列"""
        return self._queue_manager.get_queue(name)

    # ---- 路由管理 ----

    def add_route(self, rule: RouteRule) -> str:
        """添加路由规则"""
        return self._route_engine.add_rule(rule)

    def remove_route(self, rule_id: str) -> bool:
        """移除路由规则"""
        return self._route_engine.remove_rule(rule_id)

    def set_default_route(self, action: RouteAction, target: str = "") -> None:
        """设置默认路由"""
        self._route_engine.set_default(action, target)

    # ---- 消费者组管理 ----

    def create_consumer_group(self, name: str,
                              strategy: LoadBalanceStrategy = LoadBalanceStrategy.ROUND_ROBIN) -> ConsumerGroup:
        """创建消费者组"""
        with self._lock:
            group = ConsumerGroup(name, strategy)
            self._consumer_groups[name] = group
            return group

    def get_consumer_group(self, name: str) -> Optional[ConsumerGroup]:
        """获取消费者组"""
        return self._consumer_groups.get(name)

    # ---- 消息投递 ----

    def send(self, topic: str, payload: Any = None,
             headers: Optional[Dict[str, str]] = None) -> str:
        """
        发送消息（经过路由引擎）

        Returns:
            消息ID
        """
        message = Message(
            topic=topic,
            payload=payload,
            headers=headers or {},
        )

        action, target, delay = self._route_engine.route(message)

        with self._lock:
            self._stats.total_routed += 1

        if action == RouteAction.QUEUE:
            queue = self._queue_manager.get_queue(target)
            if queue:
                queue.put(message)
                return message.id
            else:
                with self._lock:
                    self._stats.total_dropped += 1
                return message.id

        elif action == RouteAction.TOPIC:
            self._event_bus.publish(target, payload, headers)
            return message.id

        elif action == RouteAction.DELAY:
            delay_q = self._queue_manager.create_delay_queue("_delay_" + target)
            delay_q.put(message, delay_seconds=delay)
            return message.id

        elif action == RouteAction.DROP:
            with self._lock:
                self._stats.total_dropped += 1
            return message.id

        return message.id

    def receive(self, queue_name: str, block: bool = False,
                timeout: float = 0) -> Optional[Message]:
        """
        从队列接收消息

        Returns:
            消息或None
        """
        queue = self._queue_manager.get_queue(queue_name)
        if queue:
            return queue.get(block=block, timeout=timeout)
        return None

    def consume(self, queue_name: str, group_name: str = "default",
                auto_ack: bool = True, key: str = "") -> Optional[str]:
        """
        从队列消费消息并分发给消费者组

        Returns:
            消费者ID或None
        """
        message = self.receive(queue_name)
        if message is None:
            return None

        group = self._consumer_groups.get(group_name)
        if group is None:
            return None

        consumer_id = group.deliver(message, key)

        if consumer_id and auto_ack:
            self._ack_manager.ack(message.id)

        if consumer_id:
            with self._lock:
                self._stats.total_delivered += 1

        return consumer_id

    # ---- 确认管理 ----

    def ack(self, message_id: str) -> bool:
        """确认消息"""
        result = self._ack_manager.ack(message_id)
        if result:
            with self._lock:
                self._stats.total_acked += 1
        return result

    def nack(self, message_id: str) -> bool:
        """拒绝消息"""
        msg = self._ack_manager.nack(message_id)
        if msg:
            with self._lock:
                self._stats.total_nacked += 1
            return True
        return False

    def requeue(self, message_id: str, queue_name: str = "") -> bool:
        """重新入队"""
        msg = self._ack_manager.requeue(message_id)
        if msg:
            with self._lock:
                self._stats.total_requeued += 1
            if queue_name:
                queue = self._queue_manager.get_queue(queue_name)
                if queue:
                    queue.put(msg)
                    return True
            return True
        return False

    def check_timeouts(self) -> int:
        """检查超时消息"""
        timed_out = self._ack_manager.check_timeouts()
        with self._lock:
            self._stats.total_timeout += len(timed_out)
        return len(timed_out)

    # ---- 事件总线集成 ----

    def subscribe(self, topic: str, handler: Callable[[Message], None],
                  priority: int = 100) -> str:
        """订阅事件总线主题"""
        return self._event_bus.subscribe(topic, handler, priority)

    def unsubscribe(self, subscription_id: str) -> bool:
        """取消订阅"""
        return self._event_bus.unsubscribe(subscription_id)

    # ---- 统计 ----

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "routed": self._stats.total_routed,
                "dropped": self._stats.total_dropped,
                "acked": self._stats.total_acked,
                "nacked": self._stats.total_nacked,
                "requeued": self._stats.total_requeued,
                "timeout": self._stats.total_timeout,
                "delivered": self._stats.total_delivered,
                "in_flight": self._ack_manager.in_flight_count,
                "consumer_groups": len(self._consumer_groups),
                "queues": self._queue_manager.get_stats(),
                "routing": self._route_engine.get_stats(),
                "event_bus": self._event_bus.get_stats(),
                "ack": self._ack_manager.get_stats(),
            }


# ============================================================
# 全局单例
# ============================================================

_broker: Optional[MessageBroker] = None
_broker_lock = threading.RLock()


def get_broker() -> MessageBroker:
    """获取全局消息代理"""
    global _broker
    if _broker is None:
        with _broker_lock:
            if _broker is None:
                _broker = MessageBroker()
    return _broker
