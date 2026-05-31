#!/usr/bin/env python3
"""
通知与告警模块 (notification) - 阶段356-360

模块列表：
- notification_manager: 通知管理器（创建/发送/查询/归档）
- template_engine: 模板引擎（变量替换/条件渲染/循环/嵌套）
- subscription_manager: 订阅管理器（订阅/退订/偏好/分组）
- delivery_tracker: 投递追踪器（状态追踪/重试/回执）
- alert_router: 告警路由器（规则匹配/升级/抑制/聚合）
"""

from .notification_manager import (
    NotificationManager, Notification, NotificationFilter,
    NotificationType, NotificationChannel, NotificationPriority, NotificationStatus,
    get_notification_manager,
)
from .template_engine import (
    TemplateEngine, Template, RenderContext,
    get_template_engine,
)
from .subscription_manager import (
    SubscriptionManager, Subscription, SubscriptionPreference, SubscriberGroup,
    get_subscription_manager,
)
from .delivery_tracker import (
    DeliveryTracker, DeliveryRecord, DeliveryStatus, RetryPolicy,
    get_delivery_tracker,
)
from .alert_router import (
    AlertRouter, AlertRule, AlertAction, AlertEvent,
    AlertSeverity, AlertActionType,
    get_alert_router,
)

__all__ = [
    "NotificationManager", "Notification", "NotificationFilter",
    "NotificationType", "NotificationChannel", "NotificationPriority", "NotificationStatus",
    "get_notification_manager",
    "TemplateEngine", "Template", "RenderContext",
    "get_template_engine",
    "SubscriptionManager", "Subscription", "SubscriptionPreference", "SubscriberGroup",
    "get_subscription_manager",
    "DeliveryTracker", "DeliveryRecord", "DeliveryStatus", "RetryPolicy",
    "get_delivery_tracker",
    "AlertRouter", "AlertRule", "AlertAction", "AlertEvent",
    "AlertSeverity", "AlertActionType",
    "get_alert_router",
]
