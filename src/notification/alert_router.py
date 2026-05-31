"""
告警路由器模块 (阶段360)

提供告警规则管理、条件评估、事件处理和告警抑制功能。
线程安全设计，使用 threading.RLock 保证并发安全。
确定性规则设计，无模型依赖，无循环依赖。
"""

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


# ============================================================================
# 枚举定义
# ============================================================================


class AlertSeverity(Enum):
    """告警严重级别枚举"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertActionType(Enum):
    """告警动作类型枚举"""
    NOTIFY = "notify"
    LOG = "log"
    ESCALATE = "escalate"
    SUPPRESS = "suppress"


# ============================================================================
# 数据类定义
# ============================================================================


@dataclass
class AlertRule:
    """告警规则数据类"""
    name: str
    condition: Callable[[Dict], bool]
    severity: AlertSeverity = AlertSeverity.WARNING
    channels: List[str] = field(default_factory=lambda: ["in_app"])
    cooldown: float = 60.0  # 冷却时间（秒）
    throttle_max: int = 10  # 节流上限
    enabled: bool = True
    match_count: int = 0
    last_triggered: float = 0.0


@dataclass
class AlertAction:
    """告警动作数据类"""
    type: AlertActionType
    target: Optional[str] = None
    message: str = ""


@dataclass
class AlertEvent:
    """告警事件数据类"""
    id: str
    rule_name: str
    severity: AlertSeverity
    source: str
    data: Dict[str, Any] = field(default_factory=dict)
    actions: List[AlertAction] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    processed: bool = False


# ============================================================================
# 告警路由器
# ============================================================================


class AlertRouter:
    """
    告警路由器

    管理告警规则，评估数据是否触发告警，生成告警事件并决定处理动作。
    支持冷却机制、节流控制和来源抑制。线程安全，使用 RLock 保证并发访问安全。
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._rules: Dict[str, AlertRule] = {}
        self._history: List[AlertEvent] = []
        self._suppressions: Dict[str, float] = {}  # source -> suppress_until
        self._id_counter: int = 0

    def _generate_id(self) -> str:
        """生成唯一告警事件ID"""
        with self._lock:
            self._id_counter += 1
            return f"alert_{self._id_counter}_{uuid.uuid4().hex[:8]}"

    def add_rule(self, rule: AlertRule) -> None:
        """
        添加告警规则

        Args:
            rule: AlertRule 对象
        """
        with self._lock:
            self._rules[rule.name] = rule

    def remove_rule(self, name: str) -> bool:
        """
        移除告警规则

        Args:
            name: 规则名称

        Returns:
            是否成功移除
        """
        with self._lock:
            if name in self._rules:
                del self._rules[name]
                return True
            return False

    def enable_rule(self, name: str) -> bool:
        """
        启用告警规则

        Args:
            name: 规则名称

        Returns:
            是否成功启用
        """
        with self._lock:
            rule = self._rules.get(name)
            if rule is None:
                return False
            rule.enabled = True
            return True

    def disable_rule(self, name: str) -> bool:
        """
        禁用告警规则

        Args:
            name: 规则名称

        Returns:
            是否成功禁用
        """
        with self._lock:
            rule = self._rules.get(name)
            if rule is None:
                return False
            rule.enabled = False
            return True

    def evaluate(self, data: Dict[str, Any]) -> List[AlertEvent]:
        """
        评估数据是否触发告警规则

        遍历所有已启用的规则，检查数据是否满足条件。
        考虑冷却时间和节流限制。

        Args:
            data: 待评估的数据字典

        Returns:
            触发的告警事件列表
        """
        now = time.time()
        source = data.get("source", "unknown")
        events: List[AlertEvent] = []

        with self._lock:
            # 检查来源是否被抑制
            suppress_until = self._suppressions.get(source)
            if suppress_until is not None and now < suppress_until:
                return events

            for rule in self._rules.values():
                if not rule.enabled:
                    continue

                # 检查冷却时间
                if now - rule.last_triggered < rule.cooldown:
                    continue

                # 检查节流上限
                if rule.match_count >= rule.throttle_max:
                    continue

                # 评估条件
                try:
                    matched = rule.condition(data)
                except Exception:
                    matched = False

                if matched:
                    rule.match_count += 1
                    rule.last_triggered = now

                    event = AlertEvent(
                        id=self._generate_id(),
                        rule_name=rule.name,
                        severity=rule.severity,
                        source=source,
                        data=dict(data),
                        actions=[],
                        created_at=now,
                        processed=False,
                    )
                    events.append(event)
                    self._history.append(event)

        return events

    def process_event(self, event: AlertEvent) -> List[AlertAction]:
        """
        处理告警事件，根据严重级别决定处理动作

        动作策略：
        - INFO: 记录日志
        - WARNING: 通知 + 记录日志
        - ERROR: 通知 + 记录日志 + 升级
        - CRITICAL: 通知 + 记录日志 + 升级 + 紧急通知

        Args:
            event: 告警事件

        Returns:
            处理动作列表
        """
        actions: List[AlertAction] = []

        with self._lock:
            rule = self._rules.get(event.rule_name)
            channels = rule.channels if rule else ["in_app"]
            severity = event.severity

            # 根据严重级别决定动作
            if severity == AlertSeverity.INFO:
                actions.append(
                    AlertAction(
                        type=AlertActionType.LOG,
                        message=f"[INFO] {event.rule_name}: {event.data}",
                    )
                )

            elif severity == AlertSeverity.WARNING:
                actions.append(
                    AlertAction(
                        type=AlertActionType.NOTIFY,
                        target=", ".join(channels),
                        message=f"[WARNING] {event.rule_name}: {event.data}",
                    )
                )
                actions.append(
                    AlertAction(
                        type=AlertActionType.LOG,
                        message=f"[WARNING] {event.rule_name}: {event.data}",
                    )
                )

            elif severity == AlertSeverity.ERROR:
                actions.append(
                    AlertAction(
                        type=AlertActionType.NOTIFY,
                        target=", ".join(channels),
                        message=f"[ERROR] {event.rule_name}: {event.data}",
                    )
                )
                actions.append(
                    AlertAction(
                        type=AlertActionType.LOG,
                        message=f"[ERROR] {event.rule_name}: {event.data}",
                    )
                )
                actions.append(
                    AlertAction(
                        type=AlertActionType.ESCALATE,
                        target="admin",
                        message=f"Alert escalated: {event.rule_name}",
                    )
                )

            elif severity == AlertSeverity.CRITICAL:
                actions.append(
                    AlertAction(
                        type=AlertActionType.NOTIFY,
                        target=", ".join(channels),
                        message=f"[CRITICAL] {event.rule_name}: {event.data}",
                    )
                )
                actions.append(
                    AlertAction(
                        type=AlertActionType.LOG,
                        message=f"[CRITICAL] {event.rule_name}: {event.data}",
                    )
                )
                actions.append(
                    AlertAction(
                        type=AlertActionType.ESCALATE,
                        target="admin",
                        message=f"Critical alert escalated: {event.rule_name}",
                    )
                )
                actions.append(
                    AlertAction(
                        type=AlertActionType.SUPPRESS,
                        target=event.source,
                        message=f"Source {event.source} suppressed after critical alert",
                    )
                )

            # 更新事件
            event.actions = actions
            event.processed = True

        return actions

    def suppress(self, source: str, duration: float = 300.0) -> None:
        """
        抑制指定来源的告警

        Args:
            source: 来源标识
            duration: 抑制持续时间（秒），默认5分钟
        """
        with self._lock:
            self._suppressions[source] = time.time() + duration

    def is_suppressed(self, source: str) -> bool:
        """
        检查来源是否被抑制

        Args:
            source: 来源标识

        Returns:
            是否被抑制
        """
        with self._lock:
            suppress_until = self._suppressions.get(source)
            if suppress_until is None:
                return False
            if time.time() >= suppress_until:
                # 抑制已过期，自动清除
                del self._suppressions[source]
                return False
            return True

    def get_history(self, limit: int = 100) -> List[AlertEvent]:
        """
        获取告警历史记录

        Args:
            limit: 返回数量上限

        Returns:
            告警事件列表（按时间倒序）
        """
        with self._lock:
            sorted_history = sorted(
                self._history, key=lambda e: e.created_at, reverse=True
            )
            return sorted_history[:limit]

    def get_rules(self) -> List[Dict[str, Any]]:
        """
        获取所有告警规则的信息

        Returns:
            规则信息字典列表
        """
        with self._lock:
            result = []
            for rule in self._rules.values():
                result.append({
                    "name": rule.name,
                    "severity": rule.severity.value,
                    "channels": list(rule.channels),
                    "cooldown": rule.cooldown,
                    "throttle_max": rule.throttle_max,
                    "enabled": rule.enabled,
                    "match_count": rule.match_count,
                    "last_triggered": rule.last_triggered,
                })
            return result

    def get_stats(self) -> Dict[str, Any]:
        """
        获取告警路由器统计信息

        Returns:
            统计信息字典
        """
        with self._lock:
            total_rules = len(self._rules)
            enabled_rules = sum(
                1 for r in self._rules.values() if r.enabled
            )
            total_events = len(self._history)
            processed_events = sum(
                1 for e in self._history if e.processed
            )
            unprocessed_events = total_events - processed_events

            # 按严重级别统计事件
            severity_counts: Dict[str, int] = {}
            for event in self._history:
                s = event.severity.value
                severity_counts[s] = severity_counts.get(s, 0) + 1

            # 按来源统计
            source_counts: Dict[str, int] = {}
            for event in self._history:
                src = event.source
                source_counts[src] = source_counts.get(src, 0) + 1

            # 规则匹配统计
            rule_match_counts: Dict[str, int] = {}
            for rule in self._rules.values():
                rule_match_counts[rule.name] = rule.match_count

            # 抑制统计
            now = time.time()
            active_suppressions = sum(
                1 for t in self._suppressions.values() if t > now
            )

            return {
                "total_rules": total_rules,
                "enabled_rules": enabled_rules,
                "disabled_rules": total_rules - enabled_rules,
                "total_events": total_events,
                "processed_events": processed_events,
                "unprocessed_events": unprocessed_events,
                "by_severity": severity_counts,
                "by_source": source_counts,
                "rule_match_counts": rule_match_counts,
                "active_suppressions": active_suppressions,
            }


# ============================================================================
# 全局单例
# ============================================================================

_alert_router_instance: Optional[AlertRouter] = None
_alert_router_lock = threading.Lock()


def get_alert_router() -> AlertRouter:
    """获取告警路由器全局单例"""
    global _alert_router_instance
    with _alert_router_lock:
        if _alert_router_instance is None:
            _alert_router_instance = AlertRouter()
        return _alert_router_instance
