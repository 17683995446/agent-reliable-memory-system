#!/usr/bin/env python3
"""
死信队列 (DeadLetterQueue) - 阶段339

职责：
- 死信收集：接收处理失败的消息
- 重试策略：固定间隔、指数退避、自定义策略
- 消息归档：过期死信归档存储
- 死信检查：周期性检查与重新投递
- 统计分析：失败原因、频率统计

设计原则：
- 确定性规则，无模型依赖
- 线程安全（RLock）
- 最小层级，无循环依赖
"""

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from messaging.message_queue import Message, MessageStatus


# ============================================================
# 枚举与数据结构
# ============================================================

class RetryStrategy(Enum):
    """重试策略类型"""
    FIXED = "fixed"               # 固定间隔
    EXPONENTIAL = "exponential"   # 指数退避
    CUSTOM = "custom"             # 自定义函数


class DeadLetterReason(Enum):
    """死信原因"""
    MAX_RETRIES = "max_retries"       # 超过最大重试次数
    EXPIRED = "expired"               # 消息过期
    NACK = "nack"                     # 消费者拒绝
    TIMEOUT = "timeout"               # 处理超时
    ERROR = "error"                   # 处理异常
    MANUAL = "manual"                 # 手动标记


class ArchivePolicy(Enum):
    """归档策略"""
    NONE = "none"           # 不归档
    SIZE = "size"           # 按数量归档
    TIME = "time"           # 按时间归档
    BOTH = "both"           # 同时按数量和时间


@dataclass
class RetryConfig:
    """重试配置"""
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    max_retries: int = 3
    initial_delay: float = 1.0       # 初始延迟秒数
    max_delay: float = 60.0          # 最大延迟秒数
    multiplier: float = 2.0          # 指数退避乘数
    custom_delays: List[float] = field(default_factory=list)  # 自定义延迟序列

    def get_delay(self, attempt: int) -> float:
        """计算第attempt次重试的延迟"""
        if self.strategy == RetryStrategy.FIXED:
            return self.initial_delay

        elif self.strategy == RetryStrategy.EXPONENTIAL:
            delay = self.initial_delay * (self.multiplier ** attempt)
            return min(delay, self.max_delay)

        elif self.strategy == RetryStrategy.CUSTOM:
            if attempt < len(self.custom_delays):
                return self.custom_delays[attempt]
            return self.custom_delays[-1] if self.custom_delays else self.initial_delay

        return self.initial_delay


@dataclass
class DeadLetterEntry:
    """死信条目"""
    message: Message
    reason: DeadLetterReason
    original_queue: str = ""
    error_detail: str = ""
    retry_count: int = 0
    max_retries: int = 3
    next_retry_at: float = 0.0
    dead_at: float = 0.0
    resolved: bool = False
    resolved_at: float = 0.0

    def __post_init__(self):
        if self.dead_at == 0.0:
            self.dead_at = time.time()

    @property
    def is_ready_for_retry(self) -> bool:
        if self.resolved:
            return False
        if self.retry_count >= self.max_retries:
            return False
        if self.next_retry_at == 0.0:
            return True
        return time.time() >= self.next_retry_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message.id,
            "topic": self.message.topic,
            "reason": self.reason.value,
            "original_queue": self.original_queue,
            "error": self.error_detail,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "resolved": self.resolved,
            "dead_at": self.dead_at,
        }


@dataclass
class ArchiveEntry:
    """归档条目"""
    entries: List[DeadLetterEntry]
    archived_at: float = 0.0
    reason: str = ""

    def __post_init__(self):
        if self.archived_at == 0.0:
            self.archived_at = time.time()


# ============================================================
# 重试策略管理器
# ============================================================

class RetryPolicyManager:
    """
    重试策略管理器

    核心功能：
    1. 多策略支持：固定间隔、指数退避、自定义
    2. 按队列配置不同策略
    3. 重试延迟计算
    4. 重试预算控制
    """

    def __init__(self):
        self._policies: Dict[str, RetryConfig] = {}
        self._default_policy = RetryConfig()
        self._lock = threading.RLock()
        self._total_retries = 0

    def set_policy(self, queue_name: str, config: RetryConfig) -> None:
        """设置队列的重试策略"""
        with self._lock:
            self._policies[queue_name] = config

    def set_default(self, config: RetryConfig) -> None:
        """设置默认策略"""
        with self._lock:
            self._default_policy = config

    def get_policy(self, queue_name: str) -> RetryConfig:
        """获取队列的重试策略"""
        with self._lock:
            return self._policies.get(queue_name, self._default_policy)

    def compute_delay(self, queue_name: str, attempt: int) -> float:
        """计算重试延迟"""
        policy = self.get_policy(queue_name)
        return policy.get_delay(attempt)

    def record_retry(self) -> None:
        """记录一次重试"""
        with self._lock:
            self._total_retries += 1

    def remove_policy(self, queue_name: str) -> bool:
        """移除策略"""
        with self._lock:
            return self._policies.pop(queue_name, None) is not None

    def list_policies(self) -> Dict[str, Dict[str, Any]]:
        """列出所有策略"""
        with self._lock:
            result = {}
            for name, config in self._policies.items():
                result[name] = {
                    "strategy": config.strategy.value,
                    "max_retries": config.max_retries,
                    "initial_delay": config.initial_delay,
                    "max_delay": config.max_delay,
                }
            return result

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "policies": len(self._policies),
                "total_retries": self._total_retries,
                "default_strategy": self._default_policy.strategy.value,
            }


# ============================================================
# 死信队列
# ============================================================

class DeadLetterQueue:
    """
    死信队列

    核心功能：
    1. 收集处理失败的消息
    2. 按原因分类存储
    3. 重试调度
    4. 归档管理
    5. 统计分析
    """

    def __init__(self, max_size: int = 10000):
        self._entries: List[DeadLetterEntry] = []
        self._by_message_id: Dict[str, DeadLetterEntry] = {}
        self._by_reason: Dict[DeadLetterReason, List[DeadLetterEntry]] = defaultdict(list)
        self._by_queue: Dict[str, List[DeadLetterEntry]] = defaultdict(list)
        self._archives: List[ArchiveEntry] = []
        self._retry_manager = RetryPolicyManager()
        self._lock = threading.RLock()
        self._max_size = max_size
        self._archive_policy = ArchivePolicy.SIZE
        self._archive_threshold = 1000
        self._archive_max_age = 3600.0  # 1小时
        self._total_enqueued = 0
        self._total_retried = 0
        self._total_resolved = 0
        self._total_archived = 0

    # ---- 死信操作 ----

    def enqueue(self, message: Message, reason: DeadLetterReason,
                original_queue: str = "", error_detail: str = "") -> str:
        """
        入队死信

        Returns:
            消息ID
        """
        policy = self._retry_manager.get_policy(original_queue)

        entry = DeadLetterEntry(
            message=message,
            reason=reason,
            original_queue=original_queue,
            error_detail=error_detail,
            max_retries=policy.max_retries,
        )

        with self._lock:
            # 容量检查
            if len(self._entries) >= self._max_size:
                self._archive_oldest(1)

            self._entries.append(entry)
            self._by_message_id[message.id] = entry
            self._by_reason[reason].append(entry)
            if original_queue:
                self._by_queue[original_queue].append(entry)
            self._total_enqueued += 1

        return message.id

    def retry(self, message_id: str) -> Optional[Message]:
        """
        重试消息

        Returns:
            可重试的消息，或None
        """
        with self._lock:
            entry = self._by_message_id.get(message_id)
            if entry is None or entry.resolved:
                return None

            if not entry.is_ready_for_retry:
                return None

            entry.retry_count += 1
            self._total_retried += 1
            self._retry_manager.record_retry()

            # 计算下次重试时间
            delay = self._retry_manager.compute_delay(
                entry.original_queue, entry.retry_count
            )
            entry.next_retry_at = time.time() + delay

            return entry.message

    def resolve(self, message_id: str) -> bool:
        """标记消息已解决"""
        with self._lock:
            entry = self._by_message_id.get(message_id)
            if entry is None:
                return False
            entry.resolved = True
            entry.resolved_at = time.time()
            self._total_resolved += 1
            return True

    def remove(self, message_id: str) -> Optional[DeadLetterEntry]:
        """移除死信条目"""
        with self._lock:
            entry = self._by_message_id.pop(message_id, None)
            if entry is None:
                return None
            self._entries.remove(entry)
            if entry in self._by_reason[entry.reason]:
                self._by_reason[entry.reason].remove(entry)
            if entry.original_queue and entry in self._by_queue[entry.original_queue]:
                self._by_queue[entry.original_queue].remove(entry)
            return entry

    # ---- 查询 ----

    def get(self, message_id: str) -> Optional[DeadLetterEntry]:
        """获取死信条目"""
        with self._lock:
            return self._by_message_id.get(message_id)

    def get_retryable(self, limit: int = 100) -> List[DeadLetterEntry]:
        """获取可重试的条目"""
        with self._lock:
            result = []
            for entry in self._entries:
                if entry.is_ready_for_retry and not entry.resolved:
                    result.append(entry)
                    if len(result) >= limit:
                        break
            return result

    def get_by_reason(self, reason: DeadLetterReason) -> List[Dict[str, Any]]:
        """按原因查询"""
        with self._lock:
            entries = self._by_reason.get(reason, [])
            return [e.to_dict() for e in entries if not e.resolved]

    def get_by_queue(self, queue_name: str) -> List[Dict[str, Any]]:
        """按原始队列查询"""
        with self._lock:
            entries = self._by_queue.get(queue_name, [])
            return [e.to_dict() for e in entries if not e.resolved]

    def list_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """列出所有未解决死信"""
        with self._lock:
            unresolved = [e for e in self._entries if not e.resolved]
            page = unresolved[offset:offset + limit]
            return [e.to_dict() for e in page]

    # ---- 归档 ----

    def set_archive_policy(self, policy: ArchivePolicy,
                           size_threshold: int = 1000,
                           max_age: float = 3600.0) -> None:
        """设置归档策略"""
        with self._lock:
            self._archive_policy = policy
            self._archive_threshold = size_threshold
            self._archive_max_age = max_age

    def archive(self) -> int:
        """
        执行归档

        Returns:
            归档条目数
        """
        with self._lock:
            to_archive = []

            if self._archive_policy in (ArchivePolicy.SIZE, ArchivePolicy.BOTH):
                unresolved = [e for e in self._entries if not e.resolved]
                if len(unresolved) > self._archive_threshold:
                    excess = len(unresolved) - self._archive_threshold
                    # 归档最旧的
                    to_archive.extend(unresolved[:excess])

            if self._archive_policy in (ArchivePolicy.TIME, ArchivePolicy.BOTH):
                now = time.time()
                for entry in self._entries:
                    if entry.resolved and (now - entry.resolved_at) > self._archive_max_age:
                        if entry not in to_archive:
                            to_archive.append(entry)

            if not to_archive:
                return 0

            archive = ArchiveEntry(
                entries=list(to_archive),
                reason=f"policy={self._archive_policy.value}, count={len(to_archive)}"
            )
            self._archives.append(archive)

            for entry in to_archive:
                self._entries.remove(entry)
                self._by_message_id.pop(entry.message.id, None)
                if entry in self._by_reason[entry.reason]:
                    self._by_reason[entry.reason].remove(entry)
                if entry.original_queue and entry in self._by_queue[entry.original_queue]:
                    self._by_queue[entry.original_queue].remove(entry)

            self._total_archived += len(to_archive)
            return len(to_archive)

    def _archive_oldest(self, count: int) -> None:
        """归档最旧的条目（内部使用）"""
        if not self._entries:
            return
        to_archive = self._entries[:count]
        archive = ArchiveEntry(
            entries=list(to_archive),
            reason="capacity_limit"
        )
        self._archives.append(archive)
        for entry in to_archive:
            self._entries.remove(entry)
            self._by_message_id.pop(entry.message.id, None)
        self._total_archived += count

    def get_archives(self) -> List[Dict[str, Any]]:
        """获取归档列表"""
        with self._lock:
            return [
                {
                    "archived_at": a.archived_at,
                    "reason": a.reason,
                    "count": len(a.entries),
                }
                for a in self._archives
            ]

    # ---- 重试策略 ----

    def set_retry_policy(self, queue_name: str, config: RetryConfig) -> None:
        """设置队列重试策略"""
        self._retry_manager.set_policy(queue_name, config)

    def set_default_retry_policy(self, config: RetryConfig) -> None:
        """设置默认重试策略"""
        self._retry_manager.set_default(config)

    # ---- 统计 ----

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            unresolved = [e for e in self._entries if not e.resolved]
            reason_counts = {}
            for reason, entries in self._by_reason.items():
                unresolved_count = sum(1 for e in entries if not e.resolved)
                if unresolved_count > 0:
                    reason_counts[reason.value] = unresolved_count

            return {
                "total_entries": len(self._entries),
                "unresolved": len(unresolved),
                "total_enqueued": self._total_enqueued,
                "total_retried": self._total_retried,
                "total_resolved": self._total_resolved,
                "total_archived": self._total_archived,
                "archives": len(self._archives),
                "by_reason": reason_counts,
                "retry_policy": self._retry_manager.get_stats(),
            }


# ============================================================
# 全局单例
# ============================================================

_dlq: Optional[DeadLetterQueue] = None
_dlq_lock = threading.RLock()


def get_dlq() -> DeadLetterQueue:
    """获取全局死信队列"""
    global _dlq
    if _dlq is None:
        with _dlq_lock:
            if _dlq is None:
                _dlq = DeadLetterQueue()
    return _dlq
