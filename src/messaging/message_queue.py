#!/usr/bin/env python3
"""
消息队列 (MessageQueue) - 阶段336

职责：
- 基础队列：FIFO先进先出、FILO先进后出
- 优先级队列：按优先级排序出队
- 延迟消息：定时投递
- 阻塞/非阻塞操作
- 队列容量限制与背压

设计原则：
- 确定性规则，无模型依赖
- 线程安全（RLock + Condition）
- 最小层级，无循环依赖
"""

import heapq
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


# ============================================================
# 枚举与数据结构
# ============================================================

class QueueType(Enum):
    """队列类型"""
    FIFO = "fifo"       # 先进先出
    FILO = "filo"       # 先进后出（栈）
    PRIORITY = "priority" # 优先级队列


class MessageStatus(Enum):
    """消息状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass(order=True)
class Message:
    """消息"""
    id: str = ""
    payload: Any = None
    priority: int = 100
    topic: str = ""
    status: MessageStatus = MessageStatus.PENDING
    created_at: float = 0.0
    deliver_at: float = 0.0       # 延迟投递时间
    expire_at: float = 0.0         # 过期时间
    retry_count: int = 0
    max_retries: int = 3
    headers: Dict[str, str] = field(default_factory=dict)
    error: Optional[str] = None

    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = time.time()
        if self.deliver_at == 0.0:
            self.deliver_at = self.created_at
        if not self.id:
            import uuid
            self.id = uuid.uuid4().hex[:12]

    @property
    def is_expired(self) -> bool:
        if self.expire_at == 0.0:
            return False
        return time.time() > self.expire_at

    @property
    def is_delayed(self) -> bool:
        return time.time() < self.deliver_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "priority": self.priority,
            "topic": self.topic,
            "status": self.status.value,
            "created_at": self.created_at,
            "retry_count": self.retry_count,
            "headers": self.headers,
        }


# ============================================================
# FIFO / FILO 队列
# ============================================================

class BaseQueue:
    """基础队列"""

    def __init__(self, name: str = "default", max_size: int = 0):
        self.name = name
        self._max_size = max_size
        self._lock = threading.RLock()
        self._not_empty = threading.Condition(self._lock)
        self._not_full = threading.Condition(self._lock)
        self._total_enqueued = 0
        self._total_dequeued = 0
        self._total_dropped = 0

    @property
    def size(self) -> int:
        raise NotImplementedError

    @property
    def is_empty(self) -> bool:
        return self.size == 0

    @property
    def is_full(self) -> bool:
        if self._max_size <= 0:
            return False
        return self.size >= self._max_size

    def put(self, message: Message, block: bool = False, timeout: float = 0) -> bool:
        raise NotImplementedError

    def get(self, block: bool = False, timeout: float = 0) -> Optional[Message]:
        raise NotImplementedError

    def peek(self) -> Optional[Message]:
        raise NotImplementedError

    def clear(self) -> int:
        raise NotImplementedError

    def get_stats(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "size": self.size,
            "max_size": self._max_size or "unlimited",
            "total_enqueued": self._total_enqueued,
            "total_dequeued": self._total_dequeued,
            "total_dropped": self._total_dropped,
        }


class FIFOQueue(BaseQueue):
    """先进先出队列"""

    def __init__(self, name: str = "fifo", max_size: int = 0):
        super().__init__(name, max_size)
        self._queue: deque = deque()

    @property
    def size(self) -> int:
        return len(self._queue)

    def put(self, message: Message, block: bool = False, timeout: float = 0) -> bool:
        with self._not_full:
            if self.is_full and not block:
                self._total_dropped += 1
                return False
            if self.is_full and block:
                if not self._not_full.wait(timeout=timeout if timeout > 0 else None):
                    self._total_dropped += 1
                    return False
            self._queue.append(message)
            self._total_enqueued += 1
            self._not_empty.notify()
            return True

    def get(self, block: bool = False, timeout: float = 0) -> Optional[Message]:
        with self._not_empty:
            if self.is_empty and not block:
                return None
            if self.is_empty and block:
                if not self._not_empty.wait(timeout=timeout if timeout > 0 else None):
                    return None
            msg = self._queue.popleft()
            self._total_dequeued += 1
            self._not_full.notify()
            return msg

    def peek(self) -> Optional[Message]:
        with self._lock:
            return self._queue[0] if self._queue else None

    def clear(self) -> int:
        with self._lock:
            count = len(self._queue)
            self._queue.clear()
            return count


class FILOQueue(BaseQueue):
    """先进后出队列（栈）"""

    def __init__(self, name: str = "filo", max_size: int = 0):
        super().__init__(name, max_size)
        self._stack: deque = deque()

    @property
    def size(self) -> int:
        return len(self._stack)

    def put(self, message: Message, block: bool = False, timeout: float = 0) -> bool:
        with self._not_full:
            if self.is_full and not block:
                self._total_dropped += 1
                return False
            if self.is_full and block:
                if not self._not_full.wait(timeout=timeout if timeout > 0 else None):
                    self._total_dropped += 1
                    return False
            self._stack.append(message)
            self._total_enqueued += 1
            self._not_empty.notify()
            return True

    def get(self, block: bool = False, timeout: float = 0) -> Optional[Message]:
        with self._not_empty:
            if self.is_empty and not block:
                return None
            if self.is_empty and block:
                if not self._not_empty.wait(timeout=timeout if timeout > 0 else None):
                    return None
            msg = self._stack.pop()
            self._total_dequeued += 1
            self._not_full.notify()
            return msg

    def peek(self) -> Optional[Message]:
        with self._lock:
            return self._stack[-1] if self._stack else None

    def clear(self) -> int:
        with self._lock:
            count = len(self._stack)
            self._stack.clear()
            return count


class PriorityQueue(BaseQueue):
    """优先级队列（数值越小优先级越高）"""

    def __init__(self, name: str = "priority", max_size: int = 0):
        super().__init__(name, max_size)
        self._heap: List[Tuple[int, float, Message]] = []
        self._counter = 0

    @property
    def size(self) -> int:
        return len(self._heap)

    def put(self, message: Message, block: bool = False, timeout: float = 0) -> bool:
        with self._not_full:
            if self.is_full and not block:
                self._total_dropped += 1
                return False
            if self.is_full and block:
                if not self._not_full.wait(timeout=timeout if timeout > 0 else None):
                    self._total_dropped += 1
                    return False
            self._counter += 1
            heapq.heappush(self._heap, (message.priority, self._counter, message))
            self._total_enqueued += 1
            self._not_empty.notify()
            return True

    def get(self, block: bool = False, timeout: float = 0) -> Optional[Message]:
        with self._not_empty:
            if self.is_empty and not block:
                return None
            if self.is_empty and block:
                if not self._not_empty.wait(timeout=timeout if timeout > 0 else None):
                    return None
            _, _, msg = heapq.heappop(self._heap)
            self._total_dequeued += 1
            self._not_full.notify()
            return msg

    def peek(self) -> Optional[Message]:
        with self._lock:
            if self._heap:
                return self._heap[0][2]
            return None

    def clear(self) -> int:
        with self._lock:
            count = len(self._heap)
            self._heap.clear()
            return count


# ============================================================
# 延迟队列
# ============================================================

class DelayQueue:
    """延迟队列"""

    def __init__(self, name: str = "delay", max_size: int = 0):
        self.name = name
        self._heap: List[Tuple[float, int, Message]] = []
        self._counter = 0
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._max_size = max_size
        self._total_enqueued = 0
        self._total_delivered = 0
        self._total_expired = 0

    def put(self, message: Message, delay_seconds: float = 0) -> bool:
        """投递延迟消息"""
        with self._lock:
            if self._max_size > 0 and len(self._heap) >= self._max_size:
                return False
            self._counter += 1
            deliver_at = time.time() + delay_seconds
            message.deliver_at = deliver_at
            heapq.heappush(self._heap, (deliver_at, self._counter, message))
            self._total_enqueued += 1
            self._condition.notify()
            return True

    def get(self, block: bool = False, timeout: float = 0) -> Optional[Message]:
        """获取到期的消息"""
        with self._condition:
            while True:
                # 清理过期消息
                self._purge_expired()

                # 检查是否有到期消息
                now = time.time()
                if self._heap and self._heap[0][0] <= now:
                    _, _, msg = heapq.heappop(self._heap)
                    self._total_delivered += 1
                    return msg

                if not block:
                    return None

                # 计算等待时间
                if self._heap:
                    wait_time = self._heap[0][0] - now
                else:
                    wait_time = timeout if timeout > 0 else None

                if wait_time is not None and timeout > 0:
                    wait_time = min(wait_time, timeout)

                if not self._condition.wait(timeout=wait_time):
                    return None

    def peek(self) -> Optional[Message]:
        with self._lock:
            if self._heap:
                return self._heap[0][2]
            return None

    def _purge_expired(self) -> int:
        """清理过期消息"""
        purged = 0
        while self._heap and self._heap[0][2].is_expired:
            heapq.heappop(self._heap)
            self._total_expired += 1
            purged += 1
        return purged

    @property
    def size(self) -> int:
        return len(self._heap)

    def clear(self) -> int:
        with self._lock:
            count = len(self._heap)
            self._heap.clear()
            return count

    def get_stats(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "size": self.size,
            "total_enqueued": self._total_enqueued,
            "total_delivered": self._total_delivered,
            "total_expired": self._total_expired,
        }


# ============================================================
# 队列管理器
# ============================================================

class QueueManager:
    """队列管理器"""

    def __init__(self):
        self._queues: Dict[str, BaseQueue] = {}
        self._delay_queues: Dict[str, DelayQueue] = {}
        self._lock = threading.RLock()

    def create_queue(self, name: str, queue_type: QueueType = QueueType.FIFO,
                     max_size: int = 0) -> BaseQueue:
        """创建队列"""
        with self._lock:
            if queue_type == QueueType.FIFO:
                q = FIFOQueue(name, max_size)
            elif queue_type == QueueType.FILO:
                q = FILOQueue(name, max_size)
            elif queue_type == QueueType.PRIORITY:
                q = PriorityQueue(name, max_size)
            else:
                q = FIFOQueue(name, max_size)
            self._queues[name] = q
            return q

    def create_delay_queue(self, name: str, max_size: int = 0) -> DelayQueue:
        """创建延迟队列"""
        with self._lock:
            dq = DelayQueue(name, max_size)
            self._delay_queues[name] = dq
            return dq

    def get_queue(self, name: str) -> Optional[BaseQueue]:
        with self._lock:
            return self._queues.get(name)

    def get_delay_queue(self, name: str) -> Optional[DelayQueue]:
        with self._lock:
            return self._delay_queues.get(name)

    def remove_queue(self, name: str) -> bool:
        with self._lock:
            return self._queues.pop(name, None) is not None

    def list_queues(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [q.get_stats() for q in self._queues.values()]

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "queues": len(self._queues),
                "delay_queues": len(self._delay_queues),
                "total_size": sum(q.size for q in self._queues.values()),
            }


# ============================================================
# 全局单例
# ============================================================

_queue_manager: Optional[QueueManager] = None
_qm_lock = threading.RLock()


def get_queue_manager() -> QueueManager:
    """获取全局队列管理器"""
    global _queue_manager
    if _queue_manager is None:
        with _qm_lock:
            if _queue_manager is None:
                _queue_manager = QueueManager()
    return _queue_manager
