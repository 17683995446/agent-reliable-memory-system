"""
Agent可靠记忆系统 - 系统仪表盘
阶段173-175: 系统全局监控、健康检查、数据聚合与可视化

设计原则:
- 确定性规则驱动，无模型依赖
- 线程安全（RLock）
- 全局单例模式
- 聚合所有子系统数据
- 支持时间窗口统计和趋势分析
"""

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
from collections import defaultdict, deque


class HealthStatus(Enum):
    """健康状态"""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class AlertLevel(Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class HealthCheckResult:
    """健康检查结果"""
    component: str
    status: HealthStatus
    message: str = ""
    details: Dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    response_time_ms: float = 0

    def to_dict(self) -> Dict:
        return {
            "component": self.component,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp,
            "response_time_ms": round(self.response_time_ms, 2),
        }


@dataclass
class Alert:
    """告警信息"""
    alert_id: str
    level: AlertLevel
    component: str
    message: str
    details: Dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    resolved: bool = False
    resolved_at: Optional[float] = None

    def to_dict(self) -> Dict:
        return {
            "alert_id": self.alert_id,
            "level": self.level.value,
            "component": self.component,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp,
            "resolved": self.resolved,
            "resolved_at": self.resolved_at,
        }


@dataclass
class MetricPoint:
    """指标数据点"""
    name: str
    value: float
    timestamp: float = field(default_factory=time.time)
    tags: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "value": self.value,
            "timestamp": self.timestamp,
            "tags": self.tags,
        }


@dataclass
class TimeSeriesBucket:
    """时间序列聚合桶"""
    bucket_start: float
    bucket_end: float
    count: int = 0
    sum_value: float = 0
    min_value: float = float('inf')
    max_value: float = float('-inf')
    avg_value: float = 0

    def add(self, value: float):
        self.count += 1
        self.sum_value += value
        self.min_value = min(self.min_value, value)
        self.max_value = max(self.max_value, value)
        self.avg_value = self.sum_value / self.count

    def to_dict(self) -> Dict:
        return {
            "bucket_start": self.bucket_start,
            "bucket_end": self.bucket_end,
            "count": self.count,
            "sum": round(self.sum_value, 4),
            "min": round(self.min_value, 4) if self.min_value != float('inf') else None,
            "max": round(self.max_value, 4) if self.max_value != float('-inf') else None,
            "avg": round(self.avg_value, 4),
        }


class SystemDashboard:
    """
    系统仪表盘

    功能:
    - 全局健康检查
    - 子系统状态聚合
    - 指标收集与时间序列
    - 告警管理
    - 趋势分析
    - 系统快照
    """

    def __init__(self, max_metric_points: int = 10000,
                 max_alerts: int = 1000):
        self._lock = threading.RLock()
        self._max_metric_points = max_metric_points
        self._max_alerts = max_alerts

        # 指标存储
        self._metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_metric_points))
        self._current_values: Dict[str, float] = {}

        # 告警存储
        self._alerts: deque = deque(maxlen=max_alerts)
        self._alert_counter: int = 0

        # 健康检查注册
        self._health_checks: Dict[str, Callable] = {}

        # 子系统数据收集器
        self._data_collectors: Dict[str, Callable] = {}

        # 启动时间
        self._started_at = time.time()

        # 告警规则
        self._alert_rules: List[Dict] = []

    # ==================== 指标收集 ====================

    def record_metric(self, name: str, value: float,
                      tags: Optional[Dict] = None):
        """
        记录指标数据点

        Args:
            name: 指标名称
            value: 指标值
            tags: 标签
        """
        with self._lock:
            point = MetricPoint(
                name=name,
                value=value,
                tags=tags or {},
            )
            self._metrics[name].append(point)
            self._current_values[name] = value

    def record_counter(self, name: str, increment: float = 1):
        """记录计数器增量"""
        with self._lock:
            current = self._current_values.get(name, 0)
            new_value = current + increment
            self._current_values[name] = new_value
            self._metrics[name].append(MetricPoint(name=name, value=new_value))

    def record_gauge(self, name: str, value: float):
        """记录仪表值"""
        with self._lock:
            self._current_values[name] = value
            self._metrics[name].append(MetricPoint(name=name, value=value))

    def get_metric(self, name: str) -> Optional[float]:
        """获取指标当前值"""
        with self._lock:
            return self._current_values.get(name)

    def get_metric_history(self, name: str,
                           since: Optional[float] = None,
                           limit: int = 100) -> List[MetricPoint]:
        """获取指标历史"""
        with self._lock:
            points = list(self._metrics.get(name, []))
            if since:
                points = [p for p in points if p.timestamp >= since]
            return points[-limit:]

    def get_all_current_metrics(self) -> Dict[str, float]:
        """获取所有当前指标值"""
        with self._lock:
            return dict(self._current_values)

    # ==================== 时间序列聚合 ====================

    def aggregate_metric(self, name: str,
                         bucket_seconds: int = 3600,
                         since: Optional[float] = None,
                         limit: int = 24) -> List[TimeSeriesBucket]:
        """
        聚合指标为时间桶

        Args:
            name: 指标名称
            bucket_seconds: 桶大小（秒）
            since: 起始时间
            limit: 最大桶数
        """
        with self._lock:
            points = list(self._metrics.get(name, []))
            if not points:
                return []

            if since:
                points = [p for p in points if p.timestamp >= since]

            if not points:
                return []

            # 创建桶
            min_ts = min(p.timestamp for p in points)
            max_ts = max(p.timestamp for p in points)

            buckets: Dict[int, TimeSeriesBucket] = {}
            current_bucket = int(min_ts / bucket_seconds) * bucket_seconds

            while current_bucket <= max_ts:
                buckets[current_bucket] = TimeSeriesBucket(
                    bucket_start=current_bucket,
                    bucket_end=current_bucket + bucket_seconds,
                )
                current_bucket += bucket_seconds

            # 填充数据
            for point in points:
                bucket_key = int(point.timestamp / bucket_seconds) * bucket_seconds
                if bucket_key in buckets:
                    buckets[bucket_key].add(point.value)

            # 排序并限制
            result = sorted(buckets.values(), key=lambda b: b.bucket_start)
            return result[-limit:]

    def get_trend(self, name: str,
                  periods: int = 5,
                  bucket_seconds: int = 3600) -> Dict:
        """
        获取指标趋势分析

        Args:
            name: 指标名称
            periods: 比较的周期数
            bucket_seconds: 每个周期的时间

        Returns:
            趋势分析结果
        """
        with self._lock:
            buckets = self.aggregate_metric(
                name, bucket_seconds=bucket_seconds, limit=periods
            )

            if len(buckets) < 2:
                return {"trend": "unknown", "change_percent": 0, "data": []}

            values = [b.avg_value for b in buckets]
            first_half = sum(values[:len(values)//2]) / max(len(values)//2, 1)
            second_half = sum(values[len(values)//2:]) / max(len(values) - len(values)//2, 1)

            if first_half == 0:
                change_percent = 100 if second_half > 0 else 0
            else:
                change_percent = ((second_half - first_half) / first_half) * 100

            if change_percent > 10:
                trend = "increasing"
            elif change_percent < -10:
                trend = "decreasing"
            else:
                trend = "stable"

            return {
                "metric_name": name,
                "trend": trend,
                "change_percent": round(change_percent, 2),
                "latest_avg": round(values[-1], 4),
                "data": [b.to_dict() for b in buckets],
            }

    # ==================== 健康检查 ====================

    def register_health_check(self, component: str,
                              check_fn: Callable[[], HealthCheckResult]):
        """
        注册健康检查

        Args:
            component: 组件名称
            check_fn: 检查函数，返回HealthCheckResult
        """
        with self._lock:
            self._health_checks[component] = check_fn

    def unregister_health_check(self, component: str) -> bool:
        """注销健康检查"""
        with self._lock:
            return self._health_checks.pop(component, None) is not None

    def run_health_checks(self) -> Dict:
        """
        运行所有健康检查

        Returns:
            {"overall": HealthStatus, "checks": [HealthCheckResult], "summary": {...}}
        """
        with self._lock:
            results = []
            worst_status = HealthStatus.HEALTHY

            for component, check_fn in self._health_checks.items():
                try:
                    start = time.time()
                    result = check_fn()
                    result.response_time_ms = (time.time() - start) * 1000
                    result.component = component
                except Exception as e:
                    result = HealthCheckResult(
                        component=component,
                        status=HealthStatus.CRITICAL,
                        message=f"健康检查异常: {str(e)}",
                    )

                results.append(result)

                # 确定最差状态
                status_order = {
                    HealthStatus.HEALTHY: 0,
                    HealthStatus.UNKNOWN: 1,
                    HealthStatus.WARNING: 2,
                    HealthStatus.CRITICAL: 3,
                }
                if status_order.get(result.status, 0) > status_order.get(worst_status, 0):
                    worst_status = result.status

            # 汇总
            status_counts = defaultdict(int)
            for r in results:
                status_counts[r.status.value] += 1

            return {
                "overall": worst_status.value,
                "checks": [r.to_dict() for r in results],
                "summary": {
                    "total": len(results),
                    "healthy": status_counts.get("healthy", 0),
                    "warning": status_counts.get("warning", 0),
                    "critical": status_counts.get("critical", 0),
                    "unknown": status_counts.get("unknown", 0),
                },
                "timestamp": time.time(),
            }

    # ==================== 告警管理 ====================

    def add_alert_rule(self, metric_name: str,
                       condition: str,  # "gt", "lt", "eq", "gte", "lte"
                       threshold: float,
                       level: AlertLevel = AlertLevel.WARNING,
                       component: str = "",
                       message_template: str = "",
                       cooldown_seconds: float = 300):
        """
        添加告警规则

        Args:
            metric_name: 监控的指标名称
            condition: 条件 (gt/lt/gte/lte/eq)
            threshold: 阈值
            level: 告警级别
            component: 组件名称
            message_template: 消息模板（{metric}, {value}, {threshold}）
            cooldown_seconds: 冷却时间
        """
        with self._lock:
            rule = {
                "metric_name": metric_name,
                "condition": condition,
                "threshold": threshold,
                "level": level,
                "component": component,
                "message_template": message_template,
                "cooldown_seconds": cooldown_seconds,
                "last_triggered": 0,
            }
            self._alert_rules.append(rule)

    def evaluate_alert_rules(self) -> List[Alert]:
        """评估所有告警规则"""
        with self._lock:
            triggered = []
            now = time.time()

            for rule in self._alert_rules:
                # 冷却检查
                if now - rule["last_triggered"] < rule["cooldown_seconds"]:
                    continue

                value = self._current_values.get(rule["metric_name"])
                if value is None:
                    continue

                is_triggered = False
                condition = rule["condition"]

                if condition == "gt" and value > rule["threshold"]:
                    is_triggered = True
                elif condition == "lt" and value < rule["threshold"]:
                    is_triggered = True
                elif condition == "gte" and value >= rule["threshold"]:
                    is_triggered = True
                elif condition == "lte" and value <= rule["threshold"]:
                    is_triggered = True
                elif condition == "eq" and value == rule["threshold"]:
                    is_triggered = True

                if is_triggered:
                    template = rule["message_template"] or (
                        "{metric} = {value} ({condition} {threshold})"
                    )
                    message = template.format(
                        metric=rule["metric_name"],
                        value=round(value, 4),
                        condition=condition,
                        threshold=rule["threshold"],
                    )

                    alert = self._create_alert(
                        level=rule["level"],
                        component=rule["component"] or rule["metric_name"],
                        message=message,
                        details={
                            "metric": rule["metric_name"],
                            "value": value,
                            "threshold": rule["threshold"],
                            "condition": condition,
                        },
                    )
                    triggered.append(alert)
                    rule["last_triggered"] = now

            return triggered

    def _create_alert(self, level: AlertLevel, component: str,
                      message: str, details: Optional[Dict] = None) -> Alert:
        """创建告警"""
        self._alert_counter += 1
        alert = Alert(
            alert_id=f"alert_{self._alert_counter:06d}",
            level=level,
            component=component,
            message=message,
            details=details or {},
        )
        self._alerts.append(alert)
        return alert

    def create_manual_alert(self, level: AlertLevel, component: str,
                            message: str,
                            details: Optional[Dict] = None) -> Alert:
        """手动创建告警"""
        with self._lock:
            return self._create_alert(level, component, message, details)

    def resolve_alert(self, alert_id: str) -> bool:
        """解决告警"""
        with self._lock:
            for alert in self._alerts:
                if alert.alert_id == alert_id and not alert.resolved:
                    alert.resolved = True
                    alert.resolved_at = time.time()
                    return True
            return False

    def get_alerts(self, level: Optional[AlertLevel] = None,
                   resolved: Optional[bool] = None,
                   component: Optional[str] = None,
                   limit: int = 50) -> List[Alert]:
        """获取告警列表"""
        with self._lock:
            alerts = list(self._alerts)

            if level:
                alerts = [a for a in alerts if a.level == level]
            if resolved is not None:
                alerts = [a for a in alerts if a.resolved == resolved]
            if component:
                alerts = [a for a in alerts if a.component == component]

            alerts.sort(key=lambda a: a.timestamp, reverse=True)
            return alerts[:limit]

    def get_unresolved_alerts(self) -> List[Alert]:
        """获取未解决的告警"""
        return self.get_alerts(resolved=False)

    # ==================== 子系统数据收集 ====================

    def register_data_collector(self, name: str,
                                collector_fn: Callable[[], Dict]):
        """
        注册子系统数据收集器

        Args:
            name: 收集器名称
            collector_fn: 收集函数，返回数据字典
        """
        with self._lock:
            self._data_collectors[name] = collector_fn

    def collect_all_data(self) -> Dict:
        """收集所有子系统数据"""
        with self._lock:
            data = {}
            for name, collector_fn in self._data_collectors.items():
                try:
                    data[name] = collector_fn()
                except Exception as e:
                    data[name] = {"error": str(e)}
            return data

    # ==================== 系统快照 ====================

    def get_snapshot(self) -> Dict:
        """
        获取系统完整快照

        Returns:
            包含所有系统信息的完整快照
        """
        with self._lock:
            now = time.time()
            uptime = now - self._started_at

            # 健康检查
            health = self.run_health_checks()

            # 子系统数据
            subsystem_data = self.collect_all_data()

            # 告警统计
            unresolved = self.get_unresolved_alerts()
            alert_summary = {
                "total": len(self._alerts),
                "unresolved": len(unresolved),
                "by_level": defaultdict(int),
            }
            for alert in self._alerts:
                if not alert.resolved:
                    alert_summary["by_level"][alert.level.value] += 1

            # 指标概览
            metrics_overview = {}
            for name, value in self._current_values.items():
                metrics_overview[name] = round(value, 4)

            return {
                "timestamp": now,
                "uptime_seconds": round(uptime, 2),
                "uptime_human": self._format_uptime(uptime),
                "health": health,
                "metrics": metrics_overview,
                "metrics_count": len(self._current_values),
                "alerts": alert_summary,
                "recent_alerts": [a.to_dict() for a in unresolved[:5]],
                "subsystems": subsystem_data,
                "dashboard_info": {
                    "total_metric_points": sum(
                        len(d) for d in self._metrics.values()
                    ),
                    "total_alert_rules": len(self._alert_rules),
                    "health_checks": len(self._health_checks),
                    "data_collectors": len(self._data_collectors),
                },
            }

    def get_quick_summary(self) -> Dict:
        """获取快速摘要（轻量级）"""
        with self._lock:
            now = time.time()
            uptime = now - self._started_at
            unresolved = len(self.get_unresolved_alerts())

            return {
                "status": "healthy" if unresolved == 0 else "degraded",
                "uptime_seconds": round(uptime, 2),
                "metrics_count": len(self._current_values),
                "unresolved_alerts": unresolved,
                "timestamp": now,
            }

    # ==================== 内置指标 ====================

    def record_operation(self, operation: str, duration_ms: float = 0,
                         success: bool = True):
        """
        记录操作指标

        自动生成以下指标:
        - operations.{operation}.total
        - operations.{operation}.success
        - operations.{operation}.failure
        - operations.{operation}.duration_ms
        """
        with self._lock:
            self.record_counter(f"operations.{operation}.total")
            if success:
                self.record_counter(f"operations.{operation}.success")
            else:
                self.record_counter(f"operations.{operation}.failure")
            if duration_ms > 0:
                self.record_metric(f"operations.{operation}.duration_ms", duration_ms)

    # ==================== 工具方法 ====================

    @staticmethod
    def _format_uptime(seconds: float) -> str:
        """格式化运行时间"""
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        parts = []
        if days > 0:
            parts.append(f"{days}天")
        if hours > 0:
            parts.append(f"{hours}小时")
        if minutes > 0:
            parts.append(f"{minutes}分钟")
        parts.append(f"{secs}秒")

        return "".join(parts)

    def get_stats(self) -> Dict:
        """获取仪表盘统计"""
        with self._lock:
            return {
                "uptime_seconds": round(time.time() - self._started_at, 2),
                "total_metrics": len(self._current_values),
                "total_metric_points": sum(
                    len(d) for d in self._metrics.values()
                ),
                "total_alerts": len(self._alerts),
                "unresolved_alerts": len(self.get_unresolved_alerts()),
                "alert_rules": len(self._alert_rules),
                "health_checks": len(self._health_checks),
                "data_collectors": len(self._data_collectors),
            }

    def get_summary(self) -> Dict:
        """获取仪表盘摘要"""
        return self.get_quick_summary()


# ==================== 全局单例 ====================

_global_dashboard: Optional[SystemDashboard] = None
_global_dashboard_lock = threading.Lock()


def get_dashboard() -> SystemDashboard:
    """获取全局仪表盘实例"""
    global _global_dashboard
    if _global_dashboard is None:
        with _global_dashboard_lock:
            if _global_dashboard is None:
                _global_dashboard = SystemDashboard()
    return _global_dashboard
