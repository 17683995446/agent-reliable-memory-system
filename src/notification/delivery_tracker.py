"""
投递追踪器模块 (阶段359)

提供通知投递记录的追踪、状态更新和重试管理功能。
线程安全设计，使用 threading.RLock 保证并发安全。
确定性规则设计，无模型依赖，无循环依赖。
"""

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ============================================================================
# 枚举定义
# ============================================================================


class DeliveryStatus(Enum):
    """投递状态枚举"""
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRIED = "retried"


# ============================================================================
# 数据类定义
# ============================================================================


@dataclass
class RetryPolicy:
    """重试策略数据类"""
    max_retries: int = 3
    backoff_multiplier: float = 2.0
    initial_delay: float = 1.0
    max_delay: float = 60.0


@dataclass
class DeliveryRecord:
    """投递记录数据类"""
    id: str
    notification_id: str
    channel: str
    recipient: str
    status: DeliveryStatus = DeliveryStatus.PENDING
    attempts: int = 0
    last_attempt_at: Optional[float] = None
    next_retry_at: Optional[float] = None
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    error_message: Optional[str] = None


# ============================================================================
# 投递追踪器
# ============================================================================


class DeliveryTracker:
    """
    投递追踪器

    追踪通知的投递状态，管理重试逻辑。支持指数退避重试策略，
    可查询失败记录和待重试记录。线程安全，使用 RLock 保证并发访问安全。
    """

    def __init__(self, retry_policy: Optional[RetryPolicy] = None) -> None:
        self._lock = threading.RLock()
        self._records: Dict[str, DeliveryRecord] = {}
        self._retry_policy = retry_policy or RetryPolicy()
        self._id_counter: int = 0

    def _generate_id(self) -> str:
        """生成唯一投递记录ID"""
        with self._lock:
            self._id_counter += 1
            return f"delivery_{self._id_counter}_{uuid.uuid4().hex[:8]}"

    def track(
        self,
        notification_id: str,
        channel: str,
        recipient: str,
    ) -> DeliveryRecord:
        """
        创建投递追踪记录

        Args:
            notification_id: 关联的通知ID
            channel: 投递渠道
            recipient: 接收者

        Returns:
            创建的 DeliveryRecord 对象
        """
        record = DeliveryRecord(
            id=self._generate_id(),
            notification_id=notification_id,
            channel=channel,
            recipient=recipient,
            status=DeliveryStatus.PENDING,
            attempts=0,
            created_at=time.time(),
        )
        with self._lock:
            self._records[record.id] = record
        return record

    def update_status(
        self,
        record_id: str,
        status: DeliveryStatus,
        error_message: Optional[str] = None,
    ) -> bool:
        """
        更新投递记录状态

        Args:
            record_id: 投递记录ID
            status: 新状态
            error_message: 错误信息（可选）

        Returns:
            是否成功更新
        """
        with self._lock:
            record = self._records.get(record_id)
            if record is None:
                return False

            # 验证状态转换的合法性
            valid_transitions = {
                DeliveryStatus.PENDING: {DeliveryStatus.SENT, DeliveryStatus.FAILED},
                DeliveryStatus.SENT: {DeliveryStatus.DELIVERED, DeliveryStatus.FAILED},
                DeliveryStatus.RETRIED: {DeliveryStatus.DELIVERED, DeliveryStatus.FAILED, DeliveryStatus.SENT},
                DeliveryStatus.FAILED: {DeliveryStatus.RETRIED},
            }

            allowed = valid_transitions.get(record.status, set())
            if status not in allowed:
                return False

            record.status = status
            record.last_attempt_at = time.time()
            record.attempts += 1

            if error_message is not None:
                record.error_message = error_message

            if status == DeliveryStatus.DELIVERED:
                record.completed_at = time.time()

            return True

    def get_record(self, record_id: str) -> Optional[DeliveryRecord]:
        """
        获取投递记录

        Args:
            record_id: 投递记录ID

        Returns:
            DeliveryRecord 对象或 None
        """
        with self._lock:
            return self._records.get(record_id)

    def get_by_notification(self, notification_id: str) -> List[DeliveryRecord]:
        """
        获取通知的所有投递记录

        Args:
            notification_id: 通知ID

        Returns:
            投递记录列表
        """
        with self._lock:
            results = [
                r
                for r in self._records.values()
                if r.notification_id == notification_id
            ]
            results.sort(key=lambda r: r.created_at, reverse=True)
            return results

    def get_by_recipient(
        self, recipient: str, limit: int = 50
    ) -> List[DeliveryRecord]:
        """
        获取接收者的投递记录

        Args:
            recipient: 接收者标识
            limit: 返回数量上限

        Returns:
            投递记录列表
        """
        with self._lock:
            results = [
                r
                for r in self._records.values()
                if r.recipient == recipient
            ]
            results.sort(key=lambda r: r.created_at, reverse=True)
            return results[:limit]

    def get_failed(self, limit: int = 50) -> List[DeliveryRecord]:
        """
        获取需要重试的失败记录

        返回状态为 FAILED 且重试次数未达上限的记录。

        Args:
            limit: 返回数量上限

        Returns:
            失败的投递记录列表
        """
        with self._lock:
            results = [
                r
                for r in self._records.values()
                if r.status == DeliveryStatus.FAILED
                and r.attempts < self._retry_policy.max_retries
            ]
            results.sort(key=lambda r: r.last_attempt_at or r.created_at, reverse=True)
            return results[:limit]

    def mark_retry(self, record_id: str) -> bool:
        """
        标记记录为待重试，并计算下次重试时间

        使用指数退避策略计算重试延迟：
        delay = min(initial_delay * (backoff_multiplier ^ attempts), max_delay)

        Args:
            record_id: 投递记录ID

        Returns:
            是否成功标记
        """
        with self._lock:
            record = self._records.get(record_id)
            if record is None:
                return False
            if record.status != DeliveryStatus.FAILED:
                return False
            if record.attempts >= self._retry_policy.max_retries:
                return False

            # 计算指数退避延迟
            delay = self._retry_policy.initial_delay * (
                self._retry_policy.backoff_multiplier ** record.attempts
            )
            delay = min(delay, self._retry_policy.max_delay)

            record.status = DeliveryStatus.RETRIED
            record.next_retry_at = time.time() + delay
            return True

    def get_pending_retries(self) -> List[DeliveryRecord]:
        """
        获取所有待重试的记录（next_retry_at <= 当前时间）

        Returns:
            待重试的投递记录列表
        """
        now = time.time()
        with self._lock:
            results = [
                r
                for r in self._records.values()
                if r.status == DeliveryStatus.RETRIED
                and r.next_retry_at is not None
                and r.next_retry_at <= now
            ]
            results.sort(key=lambda r: r.next_retry_at or 0)
            return results

    def get_stats(self) -> Dict[str, Any]:
        """
        获取投递追踪统计信息

        Returns:
            统计信息字典
        """
        with self._lock:
            total = len(self._records)
            sent = 0
            delivered = 0
            failed = 0
            pending_retry = 0
            pending = 0

            now = time.time()
            for record in self._records.values():
                if record.status == DeliveryStatus.SENT:
                    sent += 1
                elif record.status == DeliveryStatus.DELIVERED:
                    delivered += 1
                elif record.status == DeliveryStatus.FAILED:
                    failed += 1
                elif record.status == DeliveryStatus.RETRIED:
                    if (
                        record.next_retry_at is not None
                        and record.next_retry_at <= now
                    ):
                        pending_retry += 1
                    else:
                        pending += 1
                elif record.status == DeliveryStatus.PENDING:
                    pending += 1

            # 按渠道统计
            channel_stats: Dict[str, int] = {}
            for record in self._records.values():
                ch = record.channel
                channel_stats[ch] = channel_stats.get(ch, 0) + 1

            return {
                "total": total,
                "sent": sent,
                "delivered": delivered,
                "failed": failed,
                "pending_retry": pending_retry,
                "pending": pending,
                "delivery_rate": (
                    round(delivered / total * 100, 2) if total > 0 else 0.0
                ),
                "failure_rate": (
                    round(failed / total * 100, 2) if total > 0 else 0.0
                ),
                "by_channel": channel_stats,
                "retry_policy": {
                    "max_retries": self._retry_policy.max_retries,
                    "backoff_multiplier": self._retry_policy.backoff_multiplier,
                    "initial_delay": self._retry_policy.initial_delay,
                    "max_delay": self._retry_policy.max_delay,
                },
            }


# ============================================================================
# 全局单例
# ============================================================================

_delivery_tracker_instance: Optional[DeliveryTracker] = None
_delivery_tracker_lock = threading.Lock()


def get_delivery_tracker() -> DeliveryTracker:
    """获取投递追踪器全局单例"""
    global _delivery_tracker_instance
    with _delivery_tracker_lock:
        if _delivery_tracker_instance is None:
            _delivery_tracker_instance = DeliveryTracker()
        return _delivery_tracker_instance
