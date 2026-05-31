"""
健康检查器 (HealthChecker)
阶段293-295: 健康检查、自愈机制、告警触发

基于第一性原则设计:
1. 确定性: 健康状态基于确定性检查
2. 可靠性: 自愈机制保证服务恢复
3. 及时性: 定期检查和告警触发
"""

import threading
import time
import hashlib
from typing import Dict, List, Optional, Any, Callable, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict


class HealthStatus(Enum):
    """健康状态"""
    HEALTHY = "healthy"        # 健康
    DEGRADED = "degraded"      # 降级
    UNHEALTHY = "unhealthy"    # 不健康
    UNKNOWN = "unknown"        # 未知


class AlertSeverity(Enum):
    """告警级别"""
    INFO = "info"              # 信息
    WARNING = "warning"        # 警告
    ERROR = "error"            # 错误
    CRITICAL = "critical"      # 严重


class RecoveryAction(Enum):
    """恢复动作"""
    RESTART = "restart"        # 重启
    RECONNECT = "reconnect"    # 重连
    FAILOVER = "failover"      # 故障转移
    SCALE = "scale"            # 扩缩容
    CUSTOM = "custom"          # 自定义


@dataclass
class HealthCheck:
    """健康检查定义"""
    check_id: str
    name: str
    check_func: Callable[[], Tuple[bool, str]]
    interval: float = 30.0     # 检查间隔(秒)
    timeout: float = 10.0      # 超时时间(秒)
    enabled: bool = True
    last_check: Optional[float] = None
    last_status: HealthStatus = HealthStatus.UNKNOWN
    last_message: str = ""


@dataclass
class HealthRecord:
    """健康记录"""
    check_id: str
    status: HealthStatus
    message: str
    timestamp: float = field(default_factory=time.time)
    response_time: float = 0.0


@dataclass
class Alert:
    """告警"""
    alert_id: str
    check_id: str
    severity: AlertSeverity
    message: str
    timestamp: float = field(default_factory=time.time)
    acknowledged: bool = False
    resolved: bool = False
    resolved_at: Optional[float] = None


@dataclass
class RecoveryRule:
    """恢复规则"""
    rule_id: str
    check_id: str
    action: RecoveryAction
    action_func: Optional[Callable[[], bool]] = None
    max_attempts: int = 3
    cooldown: float = 60.0     # 冷却时间(秒)
    enabled: bool = True


class HealthChecker:
    """
    健康检查器

    核心功能:
    1. 健康检查: 定期检查服务健康状态
    2. 自愈机制: 自动恢复故障服务
    3. 告警触发: 健康状态变化时触发告警
    """

    def __init__(self):
        self._lock = threading.RLock()

        # 健康检查定义
        self._checks: Dict[str, HealthCheck] = {}

        # 健康记录历史
        self._records: Dict[str, List[HealthRecord]] = defaultdict(list)
        self._max_records = 1000

        # 告警
        self._alerts: List[Alert] = []
        self._max_alerts = 500
        self._alert_handlers: List[Callable[[Alert], None]] = []

        # 恢复规则
        self._recovery_rules: Dict[str, List[RecoveryRule]] = defaultdict(list)
        self._recovery_attempts: Dict[str, int] = defaultdict(int)
        self._last_recovery: Dict[str, float] = {}

        # 运行状态
        self._running: bool = False
        self._check_thread: Optional[threading.Thread] = None
        self._check_interval: float = 5.0  # 检查循环间隔

        # 整体状态
        self._overall_status: HealthStatus = HealthStatus.UNKNOWN

    # ==================== 阶段293: 健康检查 ====================

    def register_check(self, name: str,
                      check_func: Callable[[], Tuple[bool, str]],
                      interval: float = 30.0,
                      timeout: float = 10.0) -> str:
        """
        注册健康检查

        Args:
            name: 检查名称
            check_func: 检查函数，返回(是否健康, 消息)
            interval: 检查间隔(秒)
            timeout: 超时时间(秒)

        Returns:
            检查ID
        """
        with self._lock:
            check_id = self._generate_check_id(name)

            check = HealthCheck(
                check_id=check_id,
                name=name,
                check_func=check_func,
                interval=interval,
                timeout=timeout
            )

            self._checks[check_id] = check
            return check_id

    def _generate_check_id(self, name: str) -> str:
        """生成检查ID"""
        timestamp = str(time.time())
        data = f"{name}_{timestamp}"
        return hashlib.md5(data.encode()).hexdigest()[:16]

    def unregister_check(self, check_id: str) -> bool:
        """
        注销健康检查

        Args:
            check_id: 检查ID

        Returns:
            是否注销成功
        """
        with self._lock:
            if check_id not in self._checks:
                return False

            del self._checks[check_id]

            if check_id in self._records:
                del self._records[check_id]

            if check_id in self._recovery_rules:
                del self._recovery_rules[check_id]

            return True

    def get_check(self, check_id: str) -> Optional[HealthCheck]:
        """获取健康检查定义"""
        with self._lock:
            return self._checks.get(check_id)

    def list_checks(self, enabled_only: bool = False) -> List[HealthCheck]:
        """列出健康检查"""
        with self._lock:
            checks = list(self._checks.values())
            if enabled_only:
                checks = [c for c in checks if c.enabled]
            return checks

    def run_check(self, check_id: str) -> Optional[HealthRecord]:
        """
        执行单次健康检查

        Args:
            check_id: 检查ID

        Returns:
            健康记录
        """
        with self._lock:
            check = self._checks.get(check_id)
            if not check or not check.enabled:
                return None

        start_time = time.time()

        try:
            is_healthy, message = check.check_func()
            response_time = time.time() - start_time

            status = HealthStatus.HEALTHY if is_healthy else HealthStatus.UNHEALTHY

        except Exception as e:
            message = f"Check failed: {str(e)}"
            status = HealthStatus.UNHEALTHY
            response_time = time.time() - start_time

        record = HealthRecord(
            check_id=check_id,
            status=status,
            message=message,
            response_time=response_time
        )

        with self._lock:
            # 更新检查状态
            check = self._checks.get(check_id)
            if check:
                check.last_check = time.time()
                check.last_status = status
                check.last_message = message

            # 记录历史
            self._records[check_id].append(record)
            if len(self._records[check_id]) > self._max_records:
                self._records[check_id] = self._records[check_id][-self._max_records:]

            # 检查状态变化，触发告警
            old_status = check.last_status if check else HealthStatus.UNKNOWN
            if status != old_status:
                self._trigger_alert(check_id, status, message)

        return record

    def get_health_status(self, check_id: str) -> Optional[HealthStatus]:
        """获取健康状态"""
        with self._lock:
            check = self._checks.get(check_id)
            return check.last_status if check else None

    def get_overall_status(self) -> HealthStatus:
        """获取整体健康状态"""
        with self._lock:
            if not self._checks:
                return HealthStatus.UNKNOWN

            statuses = [c.last_status for c in self._checks.values() if c.enabled]

            if not statuses:
                return HealthStatus.UNKNOWN

            if all(s == HealthStatus.HEALTHY for s in statuses):
                return HealthStatus.HEALTHY
            elif any(s == HealthStatus.UNHEALTHY for s in statuses):
                return HealthStatus.UNHEALTHY
            else:
                return HealthStatus.DEGRADED

    def get_records(self, check_id: str, limit: int = 100) -> List[HealthRecord]:
        """获取健康记录历史"""
        with self._lock:
            records = self._records.get(check_id, [])
            return records[-limit:]

    # ==================== 阶段294: 自愈机制 ====================

    def add_recovery_rule(self, check_id: str,
                         action: RecoveryAction,
                         action_func: Optional[Callable[[], bool]] = None,
                         max_attempts: int = 3,
                         cooldown: float = 60.0) -> str:
        """
        添加恢复规则

        Args:
            check_id: 检查ID
            action: 恢复动作
            action_func: 自定义恢复函数
            max_attempts: 最大尝试次数
            cooldown: 冷却时间(秒)

        Returns:
            规则ID
        """
        with self._lock:
            rule_id = hashlib.md5(
                f"{check_id}_{action.value}_{time.time()}".encode()
            ).hexdigest()[:16]

            rule = RecoveryRule(
                rule_id=rule_id,
                check_id=check_id,
                action=action,
                action_func=action_func,
                max_attempts=max_attempts,
                cooldown=cooldown
            )

            self._recovery_rules[check_id].append(rule)
            return rule_id

    def remove_recovery_rule(self, rule_id: str) -> bool:
        """移除恢复规则"""
        with self._lock:
            for check_id, rules in self._recovery_rules.items():
                for i, rule in enumerate(rules):
                    if rule.rule_id == rule_id:
                        rules.pop(i)
                        return True
            return False

    def attempt_recovery(self, check_id: str) -> bool:
        """
        尝试恢复

        Args:
            check_id: 检查ID

        Returns:
            是否尝试恢复
        """
        with self._lock:
            rules = self._recovery_rules.get(check_id, [])
            if not rules:
                return False

            # 检查冷却时间
            last_recovery = self._last_recovery.get(check_id, 0)
            cooldown = max(r.cooldown for r in rules if r.enabled)

            if time.time() - last_recovery < cooldown:
                return False

            # 检查尝试次数
            attempts = self._recovery_attempts.get(check_id, 0)
            max_attempts = max(r.max_attempts for r in rules if r.enabled)

            if attempts >= max_attempts:
                return False

            # 执行恢复动作
            for rule in rules:
                if not rule.enabled:
                    continue

                try:
                    if rule.action == RecoveryAction.CUSTOM and rule.action_func:
                        success = rule.action_func()
                    else:
                        # 内置动作的模拟实现
                        success = self._execute_builtin_recovery(rule)

                    if success:
                        self._recovery_attempts[check_id] = 0
                        self._last_recovery[check_id] = time.time()
                        return True

                except Exception:
                    pass

            # 记录失败尝试
            self._recovery_attempts[check_id] = attempts + 1
            self._last_recovery[check_id] = time.time()
            return False

    def _execute_builtin_recovery(self, rule: RecoveryRule) -> bool:
        """执行内置恢复动作"""
        # 内置动作的模拟实现
        if rule.action == RecoveryAction.RESTART:
            return True  # 模拟重启成功
        elif rule.action == RecoveryAction.RECONNECT:
            return True  # 模拟重连成功
        elif rule.action == RecoveryAction.FAILOVER:
            return True  # 模拟故障转移成功
        elif rule.action == RecoveryAction.SCALE:
            return True  # 模拟扩缩容成功
        return False

    def reset_recovery_attempts(self, check_id: str) -> None:
        """重置恢复尝试次数"""
        with self._lock:
            self._recovery_attempts[check_id] = 0

    def get_recovery_status(self, check_id: str) -> Dict[str, Any]:
        """获取恢复状态"""
        with self._lock:
            return {
                "check_id": check_id,
                "attempts": self._recovery_attempts.get(check_id, 0),
                "last_recovery": self._last_recovery.get(check_id),
                "rules": [
                    {
                        "rule_id": r.rule_id,
                        "action": r.action.value,
                        "enabled": r.enabled
                    }
                    for r in self._recovery_rules.get(check_id, [])
                ]
            }

    # ==================== 阶段295: 告警触发 ====================

    def _trigger_alert(self, check_id: str, status: HealthStatus,
                      message: str) -> str:
        """
        触发告警

        Args:
            check_id: 检查ID
            status: 状态
            message: 消息

        Returns:
            告警ID
        """
        # 确定告警级别
        if status == HealthStatus.UNHEALTHY:
            severity = AlertSeverity.ERROR
        elif status == HealthStatus.DEGRADED:
            severity = AlertSeverity.WARNING
        else:
            severity = AlertSeverity.INFO

        alert_id = hashlib.md5(
            f"{check_id}_{status.value}_{time.time()}".encode()
        ).hexdigest()[:16]

        alert = Alert(
            alert_id=alert_id,
            check_id=check_id,
            severity=severity,
            message=f"Health check '{check_id}' status changed to {status.value}: {message}"
        )

        self._alerts.append(alert)

        # 限制告警数量
        if len(self._alerts) > self._max_alerts:
            self._alerts = self._alerts[-self._max_alerts:]

        # 调用告警处理器
        for handler in self._alert_handlers:
            try:
                handler(alert)
            except Exception:
                pass

        return alert_id

    def register_alert_handler(self,
                              handler: Callable[[Alert], None]) -> None:
        """注册告警处理器"""
        with self._lock:
            self._alert_handlers.append(handler)

    def get_alerts(self, severity: Optional[AlertSeverity] = None,
                  acknowledged: Optional[bool] = None,
                  limit: int = 100) -> List[Alert]:
        """
        获取告警列表

        Args:
            severity: 级别过滤
            acknowledged: 确认状态过滤
            limit: 数量限制

        Returns:
            告警列表
        """
        with self._lock:
            alerts = list(self._alerts)

            if severity:
                alerts = [a for a in alerts if a.severity == severity]

            if acknowledged is not None:
                alerts = [a for a in alerts if a.acknowledged == acknowledged]

            return alerts[-limit:]

    def acknowledge_alert(self, alert_id: str) -> bool:
        """
        确认告警

        Args:
            alert_id: 告警ID

        Returns:
            是否确认成功
        """
        with self._lock:
            for alert in self._alerts:
                if alert.alert_id == alert_id:
                    alert.acknowledged = True
                    return True
            return False

    def resolve_alert(self, alert_id: str) -> bool:
        """
        解决告警

        Args:
            alert_id: 告警ID

        Returns:
            是否解决成功
        """
        with self._lock:
            for alert in self._alerts:
                if alert.alert_id == alert_id:
                    alert.resolved = True
                    alert.resolved_at = time.time()
                    return True
            return False

    def get_active_alerts(self) -> List[Alert]:
        """获取活跃告警"""
        with self._lock:
            return [a for a in self._alerts if not a.resolved]

    def get_alert_statistics(self) -> Dict[str, Any]:
        """获取告警统计"""
        with self._lock:
            total = len(self._alerts)
            by_severity = defaultdict(int)
            for alert in self._alerts:
                by_severity[alert.severity.value] += 1

            return {
                "total": total,
                "active": len([a for a in self._alerts if not a.resolved]),
                "acknowledged": len([a for a in self._alerts if a.acknowledged]),
                "by_severity": dict(by_severity)
            }

    def start(self) -> None:
        """启动健康检查器"""
        with self._lock:
            if self._running:
                return

            self._running = True
            self._check_thread = threading.Thread(
                target=self._check_loop,
                daemon=True
            )
            self._check_thread.start()

    def stop(self) -> None:
        """停止健康检查器"""
        with self._lock:
            self._running = False

    def _check_loop(self) -> None:
        """检查循环"""
        while self._running:
            try:
                current_time = time.time()

                with self._lock:
                    checks_to_run = [
                        c for c in self._checks.values()
                        if c.enabled and (
                            c.last_check is None or
                            current_time - c.last_check >= c.interval
                        )
                    ]

                for check in checks_to_run:
                    record = self.run_check(check.check_id)

                    # 如果不健康，尝试恢复
                    if record and record.status == HealthStatus.UNHEALTHY:
                        self.attempt_recovery(check.check_id)

                time.sleep(self._check_interval)

            except Exception:
                pass


# 全局单例
_health_checker_instance: Optional[HealthChecker] = None
_health_checker_lock = threading.Lock()


def get_health_checker() -> HealthChecker:
    """获取健康检查器全局单例"""
    global _health_checker_instance

    if _health_checker_instance is None:
        with _health_checker_lock:
            if _health_checker_instance is None:
                _health_checker_instance = HealthChecker()

    return _health_checker_instance
