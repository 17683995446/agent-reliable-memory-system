"""
通知管理器模块 (阶段356)

提供通知的创建、发送、投递追踪和生命周期管理功能。
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


class NotificationType(Enum):
    """通知类型枚举"""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class NotificationChannel(Enum):
    """通知渠道枚举"""
    EMAIL = "email"
    SMS = "sms"
    WEBHOOK = "webhook"
    IN_APP = "in_app"


class NotificationPriority(Enum):
    """通知优先级枚举"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class NotificationStatus(Enum):
    """通知状态枚举"""
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    ARCHIVED = "archived"


# ============================================================================
# 数据类定义
# ============================================================================


@dataclass
class Notification:
    """通知数据类"""
    id: str
    type: NotificationType
    title: str
    content: str
    recipient: str
    channel: NotificationChannel
    priority: NotificationPriority
    status: NotificationStatus = NotificationStatus.PENDING
    created_at: float = field(default_factory=time.time)
    sent_at: Optional[float] = None
    read_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NotificationFilter:
    """通知过滤器数据类"""
    type: Optional[NotificationType] = None
    channel: Optional[NotificationChannel] = None
    priority: Optional[NotificationPriority] = None
    status: Optional[NotificationStatus] = None
    recipient: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None


# ============================================================================
# 通知管理器
# ============================================================================


class NotificationManager:
    """
    通知管理器

    管理通知的完整生命周期：创建、发送、投递确认、已读标记、
    失败标记和归档。线程安全，使用 RLock 保证并发访问安全。
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._notifications: Dict[str, Notification] = {}
        self._id_counter: int = 0

    def _generate_id(self) -> str:
        """生成唯一通知ID"""
        with self._lock:
            self._id_counter += 1
            return f"notif_{self._id_counter}_{uuid.uuid4().hex[:8]}"

    def create(
        self,
        type: NotificationType,
        title: str,
        content: str,
        recipient: str,
        channel: NotificationChannel,
        priority: NotificationPriority = NotificationPriority.NORMAL,
    ) -> Notification:
        """
        创建一条新通知

        Args:
            type: 通知类型
            title: 通知标题
            content: 通知内容
            recipient: 接收者标识
            channel: 投递渠道
            priority: 优先级，默认为 NORMAL

        Returns:
            创建的 Notification 对象
        """
        notification = Notification(
            id=self._generate_id(),
            type=type,
            title=title,
            content=content,
            recipient=recipient,
            channel=channel,
            priority=priority,
            status=NotificationStatus.PENDING,
            created_at=time.time(),
        )
        with self._lock:
            self._notifications[notification.id] = notification
        return notification

    def send(self, notification_id: str) -> bool:
        """
        发送通知，将状态更新为 SENT

        Args:
            notification_id: 通知ID

        Returns:
            是否成功发送
        """
        with self._lock:
            notification = self._notifications.get(notification_id)
            if notification is None:
                return False
            if notification.status not in (
                NotificationStatus.PENDING,
                NotificationStatus.FAILED,
            ):
                return False
            notification.status = NotificationStatus.SENT
            notification.sent_at = time.time()
            return True

    def mark_delivered(self, notification_id: str) -> bool:
        """
        标记通知为已投递

        Args:
            notification_id: 通知ID

        Returns:
            是否成功标记
        """
        with self._lock:
            notification = self._notifications.get(notification_id)
            if notification is None:
                return False
            if notification.status != NotificationStatus.SENT:
                return False
            notification.status = NotificationStatus.DELIVERED
            return True

    def mark_read(self, notification_id: str) -> bool:
        """
        标记通知为已读

        Args:
            notification_id: 通知ID

        Returns:
            是否成功标记
        """
        with self._lock:
            notification = self._notifications.get(notification_id)
            if notification is None:
                return False
            if notification.status not in (
                NotificationStatus.SENT,
                NotificationStatus.DELIVERED,
            ):
                return False
            notification.status = NotificationStatus.DELIVERED
            notification.read_at = time.time()
            return True

    def mark_failed(self, notification_id: str, reason: str = "") -> bool:
        """
        标记通知为失败

        Args:
            notification_id: 通知ID
            reason: 失败原因

        Returns:
            是否成功标记
        """
        with self._lock:
            notification = self._notifications.get(notification_id)
            if notification is None:
                return False
            if notification.status in (
                NotificationStatus.DELIVERED,
                NotificationStatus.ARCHIVED,
            ):
                return False
            notification.status = NotificationStatus.FAILED
            notification.metadata["failure_reason"] = reason
            return True

    def archive(self, notification_id: str) -> bool:
        """
        归档通知

        Args:
            notification_id: 通知ID

        Returns:
            是否成功归档
        """
        with self._lock:
            notification = self._notifications.get(notification_id)
            if notification is None:
                return False
            notification.status = NotificationStatus.ARCHIVED
            return True

    def get(self, notification_id: str) -> Optional[Notification]:
        """
        获取通知详情

        Args:
            notification_id: 通知ID

        Returns:
            Notification 对象或 None
        """
        with self._lock:
            return self._notifications.get(notification_id)

    def query(
        self,
        filter: Optional[NotificationFilter] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Notification]:
        """
        按条件查询通知

        Args:
            filter: 过滤条件
            limit: 返回数量上限
            offset: 偏移量

        Returns:
            符合条件的通知列表
        """
        with self._lock:
            results: List[Notification] = []
            for notification in self._notifications.values():
                if filter is not None:
                    if filter.type is not None and notification.type != filter.type:
                        continue
                    if filter.channel is not None and notification.channel != filter.channel:
                        continue
                    if filter.priority is not None and notification.priority != filter.priority:
                        continue
                    if filter.status is not None and notification.status != filter.status:
                        continue
                    if filter.recipient is not None and notification.recipient != filter.recipient:
                        continue
                    if filter.start_time is not None and notification.created_at < filter.start_time:
                        continue
                    if filter.end_time is not None and notification.created_at > filter.end_time:
                        continue
                results.append(notification)
            results.sort(key=lambda n: n.created_at, reverse=True)
            return results[offset: offset + limit]

    def get_by_recipient(
        self, recipient: str, limit: int = 50
    ) -> List[Notification]:
        """
        获取指定接收者的通知列表

        Args:
            recipient: 接收者标识
            limit: 返回数量上限

        Returns:
            通知列表
        """
        with self._lock:
            results = [
                n
                for n in self._notifications.values()
                if n.recipient == recipient
            ]
            results.sort(key=lambda n: n.created_at, reverse=True)
            return results[:limit]

    def count_by_status(self) -> Dict[str, int]:
        """
        按状态统计通知数量

        Returns:
            各状态的通知数量字典
        """
        with self._lock:
            counts: Dict[str, int] = {}
            for notification in self._notifications.values():
                status_name = notification.status.value
                counts[status_name] = counts.get(status_name, 0) + 1
            return counts

    def delete(self, notification_id: str) -> bool:
        """
        删除通知

        Args:
            notification_id: 通知ID

        Returns:
            是否成功删除
        """
        with self._lock:
            if notification_id in self._notifications:
                del self._notifications[notification_id]
                return True
            return False

    def get_stats(self) -> Dict[str, Any]:
        """
        获取通知系统统计信息

        Returns:
            统计信息字典
        """
        with self._lock:
            total = len(self._notifications)
            status_counts = self.count_by_status()
            type_counts: Dict[str, int] = {}
            channel_counts: Dict[str, int] = {}
            priority_counts: Dict[str, int] = {}

            for notification in self._notifications.values():
                t = notification.type.value
                type_counts[t] = type_counts.get(t, 0) + 1

                c = notification.channel.value
                channel_counts[c] = channel_counts.get(c, 0) + 1

                p = notification.priority.value
                priority_counts[p] = priority_counts.get(p, 0) + 1

            return {
                "total": total,
                "by_status": status_counts,
                "by_type": type_counts,
                "by_channel": channel_counts,
                "by_priority": priority_counts,
            }


# ============================================================================
# 全局单例
# ============================================================================

_notification_manager_instance: Optional[NotificationManager] = None
_notification_manager_lock = threading.Lock()


def get_notification_manager() -> NotificationManager:
    """获取通知管理器全局单例"""
    global _notification_manager_instance
    with _notification_manager_lock:
        if _notification_manager_instance is None:
            _notification_manager_instance = NotificationManager()
        return _notification_manager_instance
