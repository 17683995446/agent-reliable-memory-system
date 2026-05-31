"""
订阅管理器模块 (阶段358)

提供订阅、取消订阅、偏好设置和订阅者分组管理功能。
线程安全设计，使用 threading.RLock 保证并发安全。
确定性规则设计，无模型依赖，无循环依赖。
"""

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


# ============================================================================
# 数据类定义
# ============================================================================


@dataclass
class SubscriptionPreference:
    """订阅偏好数据类"""
    mute: bool = False
    min_priority: str = "low"
    digest_mode: bool = False
    digest_interval: float = 3600.0  # 默认1小时（秒）


@dataclass
class Subscription:
    """订阅数据类"""
    id: str
    subscriber_id: str
    topic: str
    channels: Set[str] = field(default_factory=lambda: {"in_app"})
    preferences: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    active: bool = True


@dataclass
class SubscriberGroup:
    """订阅者分组数据类"""
    name: str
    members: Set[str] = field(default_factory=set)
    created_at: float = field(default_factory=time.time)


# ============================================================================
# 订阅管理器
# ============================================================================


class SubscriptionManager:
    """
    订阅管理器

    管理订阅者与主题之间的订阅关系，支持多渠道订阅、
    偏好设置和订阅者分组。线程安全，使用 RLock 保证并发访问安全。
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # key: (subscriber_id, topic) -> Subscription
        self._subscriptions: Dict[tuple, Subscription] = {}
        # key: group_name -> SubscriberGroup
        self._groups: Dict[str, SubscriberGroup] = {}
        self._id_counter: int = 0

    def _generate_id(self) -> str:
        """生成唯一订阅ID"""
        with self._lock:
            self._id_counter += 1
            return f"sub_{self._id_counter}_{uuid.uuid4().hex[:8]}"

    def subscribe(
        self,
        subscriber_id: str,
        topic: str,
        channels: Optional[List[str]] = None,
        preferences: Optional[Dict[str, Any]] = None,
    ) -> Subscription:
        """
        订阅主题

        Args:
            subscriber_id: 订阅者ID
            topic: 主题名称
            channels: 通知渠道列表，默认为 ["in_app"]
            preferences: 订阅偏好设置

        Returns:
            创建的 Subscription 对象
        """
        if channels is None:
            channels = ["in_app"]
        if preferences is None:
            preferences = {}

        # 设置默认偏好
        default_prefs = {
            "mute": False,
            "min_priority": "low",
            "digest_mode": False,
            "digest_interval": 3600.0,
        }
        default_prefs.update(preferences)

        subscription = Subscription(
            id=self._generate_id(),
            subscriber_id=subscriber_id,
            topic=topic,
            channels=set(channels),
            preferences=default_prefs,
            created_at=time.time(),
            active=True,
        )

        with self._lock:
            key = (subscriber_id, topic)
            self._subscriptions[key] = subscription

        return subscription

    def unsubscribe(self, subscriber_id: str, topic: str) -> bool:
        """
        取消订阅

        Args:
            subscriber_id: 订阅者ID
            topic: 主题名称

        Returns:
            是否成功取消订阅
        """
        with self._lock:
            key = (subscriber_id, topic)
            if key in self._subscriptions:
                del self._subscriptions[key]
                return True
            return False

    def get_subscriptions(self, subscriber_id: str) -> List[Subscription]:
        """
        获取订阅者的所有订阅

        Args:
            subscriber_id: 订阅者ID

        Returns:
            订阅列表
        """
        with self._lock:
            return [
                sub
                for sub in self._subscriptions.values()
                if sub.subscriber_id == subscriber_id
            ]

    def get_subscribers(self, topic: str) -> List[str]:
        """
        获取主题的所有活跃订阅者

        Args:
            topic: 主题名称

        Returns:
            订阅者ID列表
        """
        with self._lock:
            subscribers: List[str] = []
            seen: set = set()
            for sub in self._subscriptions.values():
                if sub.topic == topic and sub.active and sub.subscriber_id not in seen:
                    subscribers.append(sub.subscriber_id)
                    seen.add(sub.subscriber_id)
            return subscribers

    def set_preference(
        self,
        subscriber_id: str,
        topic: str,
        preference: Dict[str, Any],
    ) -> bool:
        """
        设置订阅偏好

        Args:
            subscriber_id: 订阅者ID
            topic: 主题名称
            preference: 偏好设置字典

        Returns:
            是否成功设置
        """
        with self._lock:
            key = (subscriber_id, topic)
            subscription = self._subscriptions.get(key)
            if subscription is None:
                return False
            subscription.preferences.update(preference)
            return True

    def create_group(
        self, name: str, members: Optional[List[str]] = None
    ) -> SubscriberGroup:
        """
        创建订阅者分组

        Args:
            name: 分组名称
            members: 初始成员列表

        Returns:
            创建的 SubscriberGroup 对象
        """
        group = SubscriberGroup(
            name=name,
            members=set(members) if members else set(),
            created_at=time.time(),
        )
        with self._lock:
            self._groups[name] = group
        return group

    def add_to_group(self, group_name: str, subscriber_id: str) -> bool:
        """
        添加成员到分组

        Args:
            group_name: 分组名称
            subscriber_id: 订阅者ID

        Returns:
            是否成功添加
        """
        with self._lock:
            group = self._groups.get(group_name)
            if group is None:
                return False
            group.members.add(subscriber_id)
            return True

    def remove_from_group(self, group_name: str, subscriber_id: str) -> bool:
        """
        从分组中移除成员

        Args:
            group_name: 分组名称
            subscriber_id: 订阅者ID

        Returns:
            是否成功移除
        """
        with self._lock:
            group = self._groups.get(group_name)
            if group is None:
                return False
            if subscriber_id in group.members:
                group.members.discard(subscriber_id)
                return True
            return False

    def get_group_members(self, group_name: str) -> List[str]:
        """
        获取分组成员列表

        Args:
            group_name: 分组名称

        Returns:
            成员ID列表
        """
        with self._lock:
            group = self._groups.get(group_name)
            if group is None:
                return []
            return list(group.members)

    def get_topic_stats(self, topic: str) -> Dict[str, Any]:
        """
        获取主题的订阅统计信息

        Args:
            topic: 主题名称

        Returns:
            统计信息字典
        """
        with self._lock:
            topic_subs = [
                sub
                for sub in self._subscriptions.values()
                if sub.topic == topic
            ]
            active_subs = [sub for sub in topic_subs if sub.active]
            muted_subs = [
                sub for sub in active_subs if sub.preferences.get("mute", False)
            ]
            digest_subs = [
                sub
                for sub in active_subs
                if sub.preferences.get("digest_mode", False)
            ]

            channel_usage: Dict[str, int] = {}
            for sub in active_subs:
                for ch in sub.channels:
                    channel_usage[ch] = channel_usage.get(ch, 0) + 1

            return {
                "topic": topic,
                "total_subscribers": len(topic_subs),
                "active_subscribers": len(active_subs),
                "muted_subscribers": len(muted_subs),
                "digest_subscribers": len(digest_subs),
                "channel_usage": channel_usage,
            }

    def is_subscribed(self, subscriber_id: str, topic: str) -> bool:
        """
        检查订阅者是否订阅了指定主题

        Args:
            subscriber_id: 订阅者ID
            topic: 主题名称

        Returns:
            是否已订阅且活跃
        """
        with self._lock:
            key = (subscriber_id, topic)
            subscription = self._subscriptions.get(key)
            if subscription is None:
                return False
            return subscription.active

    def get_stats(self) -> Dict[str, Any]:
        """
        获取订阅系统统计信息

        Returns:
            统计信息字典
        """
        with self._lock:
            total_subscriptions = len(self._subscriptions)
            active_subscriptions = sum(
                1 for sub in self._subscriptions.values() if sub.active
            )
            muted_subscriptions = sum(
                1
                for sub in self._subscriptions.values()
                if sub.active and sub.preferences.get("mute", False)
            )

            # 统计主题
            topics: set = set()
            for sub in self._subscriptions.values():
                topics.add(sub.topic)

            # 统计渠道使用
            channel_counts: Dict[str, int] = {}
            for sub in self._subscriptions.values():
                for ch in sub.channels:
                    channel_counts[ch] = channel_counts.get(ch, 0) + 1

            # 统计分组
            total_groups = len(self._groups)
            total_group_members = sum(
                len(g.members) for g in self._groups.values()
            )

            return {
                "total_subscriptions": total_subscriptions,
                "active_subscriptions": active_subscriptions,
                "muted_subscriptions": muted_subscriptions,
                "total_topics": len(topics),
                "topics": sorted(topics),
                "channel_usage": channel_counts,
                "total_groups": total_groups,
                "total_group_members": total_group_members,
                "group_names": list(self._groups.keys()),
            }


# ============================================================================
# 全局单例
# ============================================================================

_subscription_manager_instance: Optional[SubscriptionManager] = None
_subscription_manager_lock = threading.Lock()


def get_subscription_manager() -> SubscriptionManager:
    """获取订阅管理器全局单例"""
    global _subscription_manager_instance
    with _subscription_manager_lock:
        if _subscription_manager_instance is None:
            _subscription_manager_instance = SubscriptionManager()
        return _subscription_manager_instance
