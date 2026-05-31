"""
告警管理器 - 阶段194-196

功能：
- 阶段194: 告警规则引擎
- 阶段195: 通知渠道管理
- 阶段196: 告警抑制与聚合

设计原则：
- 确定性规则，无模型依赖
- 最小层级，无循环依赖
- 线程安全，RLock保护
- 单例模式，全局唯一
"""

import threading
import time
import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Dict, List, Optional, Callable, Any, Set, Tuple, Union
from collections import deque, defaultdict
import uuid
import hashlib


class AlertSeverity(Enum):
    """告警严重级别"""
    INFO = "info"           # 信息
    WARNING = "warning"     # 警告
    ERROR = "error"         # 错误
    CRITICAL = "critical"   # 严重
    EMERGENCY = "emergency" # 紧急


class AlertStatus(Enum):
    """告警状态"""
    FIRING = "firing"       # 触发中
    RESOLVED = "resolved"   # 已恢复
    ACKNOWLEDGED = "acknowledged"  # 已确认
    SUPPRESSED = "suppressed"      # 已抑制


class AlertConditionOperator(Enum):
    """告警条件操作符"""
    EQ = "=="      # 等于
    NE = "!="      # 不等于
    GT = ">"       # 大于
    GE = ">="      # 大于等于
    LT = "<"       # 小于
    LE = "<="      # 小于等于
    CONTAINS = "contains"      # 包含
    MATCHES = "matches"        # 正则匹配
    EXISTS = "exists"          # 存在


class NotificationChannel(Enum):
    """通知渠道"""
    CONSOLE = "console"         # 控制台
    EMAIL = "email"             # 邮件
    WEBHOOK = "webhook"         # Webhook
    SLACK = "slack"             # Slack
    DINGTALK = "dingtalk"       # 钉钉
    WECHAT = "wechat"           # 企业微信
    SMS = "sms"                 # 短信
    PAGERDUTY = "pagerduty"     # PagerDuty


@dataclass
class AlertCondition:
    """告警条件"""
    metric_name: str
    operator: AlertConditionOperator
    threshold: Union[float, str, List[str]]
    duration_seconds: float = 0  # 持续多久触发
    
    def evaluate(self, value: Any) -> bool:
        """评估条件"""
        try:
            if self.operator == AlertConditionOperator.EXISTS:
                return value is not None
            
            if value is None:
                return False
            
            if self.operator == AlertConditionOperator.EQ:
                return str(value) == str(self.threshold)
            elif self.operator == AlertConditionOperator.NE:
                return str(value) != str(self.threshold)
            elif self.operator == AlertConditionOperator.GT:
                return float(value) > float(self.threshold)
            elif self.operator == AlertConditionOperator.GE:
                return float(value) >= float(self.threshold)
            elif self.operator == AlertConditionOperator.LT:
                return float(value) < float(self.threshold)
            elif self.operator == AlertConditionOperator.LE:
                return float(value) <= float(self.threshold)
            elif self.operator == AlertConditionOperator.CONTAINS:
                return str(self.threshold) in str(value)
            elif self.operator == AlertConditionOperator.MATCHES:
                return bool(re.search(str(self.threshold), str(value)))
            
            return False
        except (ValueError, TypeError):
            return False


@dataclass
class AlertRule:
    """告警规则"""
    rule_id: str
    name: str
    description: str
    severity: AlertSeverity
    conditions: List[AlertCondition]
    condition_logic: str = "AND"  # AND/OR
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    cooldown_seconds: float = 300  # 告警冷却时间
    
    # 通知配置
    channels: List[NotificationChannel] = field(default_factory=list)
    channel_configs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class Alert:
    """告警实例"""
    alert_id: str
    rule_id: str
    rule_name: str
    severity: AlertSeverity
    status: AlertStatus
    message: str
    labels: Dict[str, str]
    annotations: Dict[str, str]
    value: Any
    starts_at: float
    ends_at: Optional[float] = None
    acknowledged_at: Optional[float] = None
    acknowledged_by: Optional[str] = None
    notification_sent: Dict[str, float] = field(default_factory=dict)
    fingerprint: str = ""  # 告警指纹，用于去重
    
    def __post_init__(self):
        if not self.fingerprint:
            self.fingerprint = self._generate_fingerprint()
    
    def _generate_fingerprint(self) -> str:
        """生成告警指纹"""
        content = f"{self.rule_id}:{json.dumps(self.labels, sort_keys=True)}"
        return hashlib.md5(content.encode()).hexdigest()[:16]


@dataclass
class NotificationMessage:
    """通知消息"""
    alert: Alert
    channel: NotificationChannel
    content: str
    formatted_content: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AlertGroup:
    """告警组（用于聚合）"""
    group_id: str
    group_key: str  # 分组键
    alerts: List[Alert] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_alert_at: float = field(default_factory=time.time)


@dataclass
class SilenceRule:
    """静默规则"""
    silence_id: str
    matchers: Dict[str, str]  # 标签匹配
    starts_at: float
    ends_at: float
    created_by: str
    comment: str


class AlertManager:
    """
    告警管理器
    
    阶段194: 告警规则引擎
    - 灵活的告警规则定义
    - 多条件组合（AND/OR）
    - 标签匹配与过滤
    
    阶段195: 通知渠道管理
    - 多渠道通知支持
    - 渠道配置管理
    - 通知模板系统
    
    阶段196: 告警抑制与聚合
    - 告警分组聚合
    - 静默规则
    - 告警抑制策略
    """
    
    _instance = None
    _lock = threading.RLock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        with self._lock:
            if self._initialized:
                return
            
            self._initialized = True
            
            # 告警规则
            self._rules: Dict[str, AlertRule] = {}
            
            # 活动告警
            self._active_alerts: Dict[str, Alert] = {}
            self._alert_history: deque = deque(maxlen=10000)
            
            # 告警指纹跟踪（用于去重）
            self._fingerprint_last_fired: Dict[str, float] = {}
            
            # 通知渠道处理器
            self._channel_handlers: Dict[NotificationChannel, Callable] = {}
            self._register_default_handlers()
            
            # 告警分组
            self._alert_groups: Dict[str, AlertGroup] = {}
            self._grouping_enabled = True
            self._group_wait_seconds = 30  # 分组等待时间
            self._group_interval_seconds = 300  # 分组间隔
            
            # 静默规则
            self._silence_rules: Dict[str, SilenceRule] = {}
            
            # 抑制规则
            self._inhibition_rules: List[Dict[str, Any]] = []
            
            # 评估循环
            self._evaluation_thread: Optional[threading.Thread] = None
            self._evaluation_running = False
            self._evaluation_interval = 15  # 15秒评估间隔
            
            # 指标回调
            self._metric_provider: Optional[Callable[[str], Any]] = None
    
    def _register_default_handlers(self):
        """注册默认通知处理器"""
        self._channel_handlers[NotificationChannel.CONSOLE] = self._send_console_notification
        self._channel_handlers[NotificationChannel.WEBHOOK] = self._send_webhook_notification
    
    # ========== 阶段194: 告警规则引擎 ==========
    
    def register_rule(self, rule: AlertRule) -> None:
        """注册告警规则"""
        with self._lock:
            self._rules[rule.rule_id] = rule
    
    def unregister_rule(self, rule_id: str) -> bool:
        """注销告警规则"""
        with self._lock:
            if rule_id in self._rules:
                del self._rules[rule_id]
                return True
            return False
    
    def get_rule(self, rule_id: str) -> Optional[AlertRule]:
        """获取告警规则"""
        with self._lock:
            return self._rules.get(rule_id)
    
    def list_rules(self, enabled_only: bool = False) -> List[AlertRule]:
        """列出所有告警规则"""
        with self._lock:
            rules = list(self._rules.values())
            if enabled_only:
                rules = [r for r in rules if r.enabled]
            return rules
    
    def update_rule(self, rule_id: str, **kwargs) -> bool:
        """更新告警规则"""
        with self._lock:
            rule = self._rules.get(rule_id)
            if not rule:
                return False
            
            for key, value in kwargs.items():
                if hasattr(rule, key):
                    setattr(rule, key, value)
            
            rule.updated_at = time.time()
            return True
    
    def enable_rule(self, rule_id: str) -> bool:
        """启用告警规则"""
        return self.update_rule(rule_id, enabled=True)
    
    def disable_rule(self, rule_id: str) -> bool:
        """禁用告警规则"""
        return self.update_rule(rule_id, enabled=False)
    
    def evaluate_rule(self, rule: AlertRule, metrics: Dict[str, Any]) -> Optional[Alert]:
        """评估单个规则"""
        if not rule.enabled:
            return None
        
        # 评估所有条件
        condition_results = []
        for condition in rule.conditions:
            value = metrics.get(condition.metric_name)
            result = condition.evaluate(value)
            condition_results.append(result)
        
        # 根据逻辑组合条件
        if rule.condition_logic == "AND":
            triggered = all(condition_results)
        else:  # OR
            triggered = any(condition_results)
        
        if not triggered:
            return None
        
        # 获取触发值
        trigger_value = None
        if rule.conditions:
            trigger_value = metrics.get(rule.conditions[0].metric_name)
        
        # 生成告警指纹
        labels = dict(rule.labels)
        labels["rule_id"] = rule.rule_id
        fingerprint_content = f"{rule.rule_id}:{json.dumps(labels, sort_keys=True)}"
        fingerprint = hashlib.md5(fingerprint_content.encode()).hexdigest()[:16]
        
        # 检查冷却期
        last_fired = self._fingerprint_last_fired.get(fingerprint, 0)
        if time.time() - last_fired < rule.cooldown_seconds:
            return None
        
        # 创建告警
        alert = Alert(
            alert_id=str(uuid.uuid4()),
            rule_id=rule.rule_id,
            rule_name=rule.name,
            severity=rule.severity,
            status=AlertStatus.FIRING,
            message=rule.annotations.get("summary", f"Alert: {rule.name}"),
            labels=labels,
            annotations=dict(rule.annotations),
            value=trigger_value,
            starts_at=time.time(),
            fingerprint=fingerprint
        )
        
        return alert
    
    def evaluate_all_rules(self, metrics: Optional[Dict[str, Any]] = None) -> List[Alert]:
        """评估所有规则"""
        if metrics is None and self._metric_provider:
            metrics = self._metric_provider()
        
        if metrics is None:
            metrics = {}
        
        triggered_alerts = []
        
        with self._lock:
            rules = list(self._rules.values())
        
        for rule in rules:
            alert = self.evaluate_rule(rule, metrics)
            if alert:
                triggered_alerts.append(alert)
        
        return triggered_alerts
    
    def set_metric_provider(self, provider: Callable[[], Dict[str, Any]]) -> None:
        """设置指标提供者"""
        self._metric_provider = provider
    
    # ========== 阶段195: 通知渠道管理 ==========
    
    def register_channel_handler(self, channel: NotificationChannel,
                                  handler: Callable[[NotificationMessage], bool]) -> None:
        """注册通知渠道处理器"""
        with self._lock:
            self._channel_handlers[channel] = handler
    
    def send_notification(self, alert: Alert,
                          channel: NotificationChannel,
                          config: Optional[Dict[str, Any]] = None) -> bool:
        """发送通知"""
        handler = self._channel_handlers.get(channel)
        if not handler:
            return False
        
        # 格式化消息
        message = self._format_notification(alert, channel)
        
        try:
            result = handler(message)
            if result:
                alert.notification_sent[channel.value] = time.time()
            return result
        except Exception:
            return False
    
    def _format_notification(self, alert: Alert,
                             channel: NotificationChannel) -> NotificationMessage:
        """格式化通知消息"""
        content = f"[{alert.severity.value.upper()}] {alert.message}"
        
        formatted = {
            "alert_id": alert.alert_id,
            "rule_name": alert.rule_name,
            "severity": alert.severity.value,
            "status": alert.status.value,
            "message": alert.message,
            "value": alert.value,
            "starts_at": datetime.fromtimestamp(alert.starts_at).isoformat(),
            "labels": alert.labels,
            "annotations": alert.annotations
        }
        
        if channel == NotificationChannel.SLACK:
            content = self._format_slack_message(alert)
        elif channel == NotificationChannel.EMAIL:
            content = self._format_email_message(alert)
        elif channel == NotificationChannel.WEBHOOK:
            content = json.dumps(formatted, ensure_ascii=False)
        
        return NotificationMessage(
            alert=alert,
            channel=channel,
            content=content,
            formatted_content=formatted
        )
    
    def _format_slack_message(self, alert: Alert) -> str:
        """格式化Slack消息"""
        severity_emoji = {
            AlertSeverity.INFO: "ℹ️",
            AlertSeverity.WARNING: "⚠️",
            AlertSeverity.ERROR: "❌",
            AlertSeverity.CRITICAL: "🚨",
            AlertSeverity.EMERGENCY: "🔥"
        }
        
        emoji = severity_emoji.get(alert.severity, "📢")
        
        return json.dumps({
            "text": f"{emoji} *{alert.severity.value.upper()}*: {alert.message}",
            "attachments": [{
                "fields": [
                    {"title": "Rule", "value": alert.rule_name, "short": True},
                    {"title": "Status", "value": alert.status.value, "short": True},
                    {"title": "Value", "value": str(alert.value), "short": True},
                    {"title": "Time", "value": datetime.fromtimestamp(alert.starts_at).isoformat(), "short": True}
                ]
            }]
        }, ensure_ascii=False)
    
    def _format_email_message(self, alert: Alert) -> str:
        """格式化邮件消息"""
        return f"""
Alert: {alert.rule_name}
Severity: {alert.severity.value.upper()}
Status: {alert.status.value}
Message: {alert.message}
Value: {alert.value}
Time: {datetime.fromtimestamp(alert.starts_at).isoformat()}

Labels:
{json.dumps(alert.labels, indent=2)}

Annotations:
{json.dumps(alert.annotations, indent=2)}
"""
    
    def _send_console_notification(self, message: NotificationMessage) -> bool:
        """发送控制台通知"""
        print(f"[ALERT][{message.channel.value}] {message.content}")
        return True
    
    def _send_webhook_notification(self, message: NotificationMessage) -> bool:
        """发送Webhook通知（简化实现）"""
        # 实际实现需要HTTP请求
        print(f"[WEBHOOK] Would send: {message.content[:200]}...")
        return True
    
    def notify_alert(self, alert: Alert) -> Dict[str, bool]:
        """向所有配置的渠道发送告警通知"""
        rule = self._rules.get(alert.rule_id)
        if not rule:
            return {}
        
        results = {}
        for channel in rule.channels:
            config = rule.channel_configs.get(channel.value, {})
            results[channel.value] = self.send_notification(alert, channel, config)
        
        return results
    
    # ========== 阶段196: 告警抑制与聚合 ==========
    
    def create_alert_group(self, group_key: str, alerts: List[Alert]) -> AlertGroup:
        """创建告警组"""
        group_id = str(uuid.uuid4())
        group = AlertGroup(
            group_id=group_id,
            group_key=group_key,
            alerts=alerts,
            last_alert_at=time.time()
        )
        
        with self._lock:
            self._alert_groups[group_id] = group
        
        return group
    
    def group_alerts(self, alerts: List[Alert],
                     group_by: List[str] = None) -> Dict[str, List[Alert]]:
        """按标签分组告警"""
        if group_by is None:
            group_by = ["severity", "rule_id"]
        
        groups: Dict[str, List[Alert]] = defaultdict(list)
        
        for alert in alerts:
            # 构建分组键
            key_parts = []
            for key in group_by:
                if key == "severity":
                    key_parts.append(alert.severity.value)
                elif key == "rule_id":
                    key_parts.append(alert.rule_id)
                else:
                    key_parts.append(alert.labels.get(key, "unknown"))
            
            group_key = "|".join(key_parts)
            groups[group_key].append(alert)
        
        return dict(groups)
    
    def create_silence(self, matchers: Dict[str, str],
                       duration_seconds: float,
                       created_by: str,
                       comment: str = "") -> SilenceRule:
        """创建静默规则"""
        silence = SilenceRule(
            silence_id=str(uuid.uuid4()),
            matchers=matchers,
            starts_at=time.time(),
            ends_at=time.time() + duration_seconds,
            created_by=created_by,
            comment=comment
        )
        
        with self._lock:
            self._silence_rules[silence.silence_id] = silence
        
        return silence
    
    def delete_silence(self, silence_id: str) -> bool:
        """删除静默规则"""
        with self._lock:
            if silence_id in self._silence_rules:
                del self._silence_rules[silence_id]
                return True
            return False
    
    def is_silenced(self, alert: Alert) -> Optional[SilenceRule]:
        """检查告警是否被静默"""
        with self._lock:
            now = time.time()
            for silence in self._silence_rules.values():
                if now > silence.ends_at:
                    continue
                
                # 检查是否匹配
                matched = True
                for key, value in silence.matchers.items():
                    if key == "rule_id":
                        if alert.rule_id != value:
                            matched = False
                            break
                    elif alert.labels.get(key) != value:
                        matched = False
                        break
                
                if matched:
                    return silence
        
        return None
    
    def add_inhibition_rule(self, source_match: Dict[str, str],
                            target_match: Dict[str, str],
                            equal_labels: List[str] = None) -> None:
        """添加抑制规则"""
        with self._lock:
            self._inhibition_rules.append({
                "source_match": source_match,
                "target_match": target_match,
                "equal_labels": equal_labels or []
            })
    
    def is_inhibited(self, alert: Alert) -> bool:
        """检查告警是否被抑制"""
        with self._lock:
            for rule in self._inhibition_rules:
                # 检查是否有源告警匹配
                source_match = self._match_alert_to_pattern(alert, rule["source_match"])
                if source_match:
                    continue
                
                # 检查目标告警
                target_match = self._match_alert_to_pattern(alert, rule["target_match"])
                if target_match:
                    # 检查是否有活动的源告警
                    for active in self._active_alerts.values():
                        if active.status != AlertStatus.FIRING:
                            continue
                        
                        source_active = self._match_alert_to_pattern(active, rule["source_match"])
                        if source_active:
                            # 检查equal_labels
                            all_equal = True
                            for label in rule["equal_labels"]:
                                if active.labels.get(label) != alert.labels.get(label):
                                    all_equal = False
                                    break
                            
                            if all_equal:
                                return True
        
        return False
    
    def _match_alert_to_pattern(self, alert: Alert,
                                 pattern: Dict[str, str]) -> bool:
        """检查告警是否匹配模式"""
        for key, value in pattern.items():
            if key == "severity":
                if alert.severity.value != value:
                    return False
            elif key == "rule_id":
                if alert.rule_id != value:
                    return False
            elif alert.labels.get(key) != value:
                return False
        
        return True
    
    def fire_alert(self, alert: Alert) -> bool:
        """触发告警"""
        # 检查静默
        if self.is_silenced(alert):
            alert.status = AlertStatus.SUPPRESSED
            return False
        
        # 检查抑制
        if self.is_inhibited(alert):
            alert.status = AlertStatus.SUPPRESSED
            return False
        
        with self._lock:
            self._active_alerts[alert.alert_id] = alert
            self._fingerprint_last_fired[alert.fingerprint] = time.time()
        
        # 发送通知
        self.notify_alert(alert)
        
        return True
    
    def resolve_alert(self, alert_id: str) -> bool:
        """解决告警"""
        with self._lock:
            alert = self._active_alerts.get(alert_id)
            if not alert:
                return False
            
            alert.status = AlertStatus.RESOLVED
            alert.ends_at = time.time()
            
            # 移到历史
            self._alert_history.append(alert)
            del self._active_alerts[alert_id]
        
        return True
    
    def acknowledge_alert(self, alert_id: str, user: str) -> bool:
        """确认告警"""
        with self._lock:
            alert = self._active_alerts.get(alert_id)
            if not alert:
                return False
            
            alert.status = AlertStatus.ACKNOWLEDGED
            alert.acknowledged_at = time.time()
            alert.acknowledged_by = user
        
        return True
    
    def get_active_alerts(self, severity: Optional[AlertSeverity] = None) -> List[Alert]:
        """获取活动告警"""
        with self._lock:
            alerts = list(self._active_alerts.values())
            if severity:
                alerts = [a for a in alerts if a.severity == severity]
            return alerts
    
    def get_alert_history(self, limit: int = 100) -> List[Alert]:
        """获取告警历史"""
        with self._lock:
            return list(self._alert_history)[-limit:]
    
    def start_evaluation_loop(self) -> None:
        """启动评估循环"""
        with self._lock:
            if self._evaluation_running:
                return
            
            self._evaluation_running = True
            self._evaluation_thread = threading.Thread(
                target=self._evaluation_loop,
                daemon=True
            )
            self._evaluation_thread.start()
    
    def stop_evaluation_loop(self) -> None:
        """停止评估循环"""
        with self._lock:
            self._evaluation_running = False
        
        if self._evaluation_thread:
            self._evaluation_thread.join(timeout=5.0)
    
    def _evaluation_loop(self) -> None:
        """评估循环"""
        while True:
            with self._lock:
                if not self._evaluation_running:
                    break
            
            try:
                alerts = self.evaluate_all_rules()
                for alert in alerts:
                    self.fire_alert(alert)
            except Exception:
                pass
            
            time.sleep(self._evaluation_interval)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            active_by_severity = defaultdict(int)
            for alert in self._active_alerts.values():
                active_by_severity[alert.severity.value] += 1
            
            return {
                "total_rules": len(self._rules),
                "enabled_rules": len([r for r in self._rules.values() if r.enabled]),
                "active_alerts": len(self._active_alerts),
                "active_by_severity": dict(active_by_severity),
                "alert_history_count": len(self._alert_history),
                "silence_rules": len(self._silence_rules),
                "inhibition_rules": len(self._inhibition_rules)
            }


# 全局单例
_alert_manager_instance: Optional[AlertManager] = None
_alert_manager_lock = threading.RLock()


def get_alert_manager() -> AlertManager:
    """获取告警管理器全局实例"""
    global _alert_manager_instance
    if _alert_manager_instance is None:
        with _alert_manager_lock:
            if _alert_manager_instance is None:
                _alert_manager_instance = AlertManager()
    return _alert_manager_instance
