"""
消息系统 (Messaging) - 阶段336-340

模块：
- message_queue: 消息队列（FIFO/FILO/Priority/Delay）
- event_bus: 事件总线（发布订阅、主题路由）
- message_broker: 消息代理（路由、负载均衡、确认）
- dead_letter_queue: 死信队列（重试策略、归档）
- stream_processor: 流处理器（窗口聚合、背压）
"""

from messaging.message_queue import (
    Message, MessageStatus, QueueType,
    FIFOQueue, FILOQueue, PriorityQueue, DelayQueue,
    QueueManager, get_queue_manager,
)
from messaging.event_bus import (
    DeliveryMode, Subscription, PublishResult, TopicInfo,
    EventBus, get_event_bus,
)
from messaging.message_broker import (
    AckStatus, RouteAction, LoadBalanceStrategy,
    RouteRule, Consumer, InFlightMessage, BrokerStats,
    RouteEngine, LoadBalancer, AckManager, ConsumerGroup,
    MessageBroker, get_broker,
)
from messaging.dead_letter_queue import (
    RetryStrategy, DeadLetterReason, ArchivePolicy,
    RetryConfig, DeadLetterEntry, ArchiveEntry,
    RetryPolicyManager, DeadLetterQueue, get_dlq,
)
from messaging.stream_processor import (
    WindowType, BackPressureStrategy, ProcessorState,
    WindowConfig, BackPressureConfig,
    StreamRecord, WindowResult, ProcessorMetric,
    WindowManager, BackPressureController,
    StreamProcessor, StreamTopology, get_topology,
)

__all__ = [
    # message_queue
    "Message", "MessageStatus", "QueueType",
    "FIFOQueue", "FILOQueue", "PriorityQueue", "DelayQueue",
    "QueueManager", "get_queue_manager",
    # event_bus
    "DeliveryMode", "Subscription", "PublishResult", "TopicInfo",
    "EventBus", "get_event_bus",
    # message_broker
    "AckStatus", "RouteAction", "LoadBalanceStrategy",
    "RouteRule", "Consumer", "InFlightMessage", "BrokerStats",
    "RouteEngine", "LoadBalancer", "AckManager", "ConsumerGroup",
    "MessageBroker", "get_broker",
    # dead_letter_queue
    "RetryStrategy", "DeadLetterReason", "ArchivePolicy",
    "RetryConfig", "DeadLetterEntry", "ArchiveEntry",
    "RetryPolicyManager", "DeadLetterQueue", "get_dlq",
    # stream_processor
    "WindowType", "BackPressureStrategy", "ProcessorState",
    "WindowConfig", "BackPressureConfig",
    "StreamRecord", "WindowResult", "ProcessorMetric",
    "WindowManager", "BackPressureController",
    "StreamProcessor", "StreamTopology", "get_topology",
]
