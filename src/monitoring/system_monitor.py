"""
系统监控器 - 阶段191-193

功能：
- 阶段191: 性能指标收集框架
- 阶段192: 健康检查系统
- 阶段193: 资源监控与阈值告警

设计原则：
- 确定性规则，无模型依赖
- 最小层级，无循环依赖
- 线程安全，RLock保护
- 单例模式，全局唯一
"""

import threading
import time
import os
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Dict, List, Optional, Callable, Any, Set, Tuple
from collections import deque, defaultdict
import functools


class MetricType(Enum):
    """指标类型"""
    COUNTER = auto()      # 计数器（单调递增）
    GAUGE = auto()        # 仪表盘（可增可减）
    HISTOGRAM = auto()    # 直方图（分布统计）
    TIMER = auto()        # 计时器（耗时统计）


class HealthStatus(Enum):
    """健康状态"""
    HEALTHY = "healthy"       # 健康
    DEGRADED = "degraded"     # 降级
    UNHEALTHY = "unhealthy"   # 不健康
    UNKNOWN = "unknown"       # 未知


class ResourceType(Enum):
    """资源类型"""
    CPU = "cpu"
    MEMORY = "memory"
    DISK = "disk"
    NETWORK = "network"
    CONNECTIONS = "connections"


@dataclass
class MetricValue:
    """指标值"""
    name: str
    value: float
    metric_type: MetricType
    timestamp: float
    labels: Dict[str, str] = field(default_factory=dict)
    unit: str = ""


@dataclass
class MetricSnapshot:
    """指标快照"""
    timestamp: float
    metrics: Dict[str, MetricValue]
    duration_ms: float


@dataclass
class HealthCheck:
    """健康检查项"""
    name: str
    check_func: Callable[[], Tuple[HealthStatus, str]]
    interval_seconds: float
    timeout_seconds: float
    last_check: Optional[float] = None
    last_status: HealthStatus = HealthStatus.UNKNOWN
    last_message: str = ""
    consecutive_failures: int = 0


@dataclass
class HealthReport:
    """健康报告"""
    timestamp: float
    overall_status: HealthStatus
    checks: Dict[str, Dict[str, Any]]
    failed_checks: List[str]
    degraded_checks: List[str]


@dataclass
class ResourceThreshold:
    """资源阈值"""
    resource_type: ResourceType
    warning_threshold: float      # 警告阈值
    critical_threshold: float     # 严重阈值
    current_value: float = 0.0
    current_usage_percent: float = 0.0


@dataclass
class ResourceAlert:
    """资源告警"""
    alert_id: str
    resource_type: ResourceType
    severity: str  # warning, critical
    threshold: float
    current_value: float
    message: str
    timestamp: float
    acknowledged: bool = False


class SystemMonitor:
    """
    系统监控器
    
    阶段191: 性能指标收集框架
    - 支持多种指标类型（Counter/Gauge/Histogram/Timer）
    - 指标标签系统
    - 指标聚合与查询
    
    阶段192: 健康检查系统
    - 可注册自定义健康检查
    - 定期检查与状态跟踪
    - 健康报告生成
    
    阶段193: 资源监控与阈值告警
    - CPU/内存/磁盘/网络监控
    - 可配置阈值
    - 告警触发与抑制
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
            self._metrics: Dict[str, MetricValue] = {}
            self._metric_history: Dict[str, deque] = defaultdict(
                lambda: deque(maxlen=10000)
            )
            self._counters: Dict[str, float] = defaultdict(float)
            self._histograms: Dict[str, List[float]] = defaultdict(list)
            
            self._health_checks: Dict[str, HealthCheck] = {}
            self._health_check_thread: Optional[threading.Thread] = None
            self._health_check_running = False
            
            self._resource_thresholds: Dict[ResourceType, ResourceThreshold] = {}
            self._resource_alerts: List[ResourceAlert] = []
            self._alert_handlers: List[Callable[[ResourceAlert], None]] = []
            self._alert_cooldown: Dict[str, float] = {}
            self._alert_cooldown_seconds = 300  # 5分钟告警冷却
            
            self._monitoring_thread: Optional[threading.Thread] = None
            self._monitoring_running = False
            self._monitoring_interval = 30  # 30秒监控间隔
            
            self._start_time = time.time()
            self._init_default_thresholds()
    
    def _init_default_thresholds(self):
        """初始化默认阈值"""
        self._resource_thresholds[ResourceType.CPU] = ResourceThreshold(
            resource_type=ResourceType.CPU,
            warning_threshold=70.0,
            critical_threshold=90.0
        )
        self._resource_thresholds[ResourceType.MEMORY] = ResourceThreshold(
            resource_type=ResourceType.MEMORY,
            warning_threshold=80.0,
            critical_threshold=95.0
        )
        self._resource_thresholds[ResourceType.DISK] = ResourceThreshold(
            resource_type=ResourceType.DISK,
            warning_threshold=80.0,
            critical_threshold=95.0
        )
    
    # ========== 阶段191: 性能指标收集框架 ==========
    
    def record_counter(self, name: str, value: float = 1.0,
                       labels: Optional[Dict[str, str]] = None,
                       unit: str = "") -> None:
        """记录计数器指标"""
        with self._lock:
            key = self._make_metric_key(name, labels)
            self._counters[key] += value
            
            metric = MetricValue(
                name=name,
                value=self._counters[key],
                metric_type=MetricType.COUNTER,
                timestamp=time.time(),
                labels=labels or {},
                unit=unit
            )
            self._metrics[key] = metric
            self._metric_history[name].append(metric)
    
    def record_gauge(self, name: str, value: float,
                     labels: Optional[Dict[str, str]] = None,
                     unit: str = "") -> None:
        """记录仪表盘指标"""
        with self._lock:
            key = self._make_metric_key(name, labels)
            
            metric = MetricValue(
                name=name,
                value=value,
                metric_type=MetricType.GAUGE,
                timestamp=time.time(),
                labels=labels or {},
                unit=unit
            )
            self._metrics[key] = metric
            self._metric_history[name].append(metric)
    
    def record_histogram(self, name: str, value: float,
                         labels: Optional[Dict[str, str]] = None,
                         unit: str = "") -> None:
        """记录直方图指标"""
        with self._lock:
            key = self._make_metric_key(name, labels)
            self._histograms[key].append(value)
            
            # 只保留最近1000个样本
            if len(self._histograms[key]) > 1000:
                self._histograms[key] = self._histograms[key][-1000:]
            
            metric = MetricValue(
                name=name,
                value=value,
                metric_type=MetricType.HISTOGRAM,
                timestamp=time.time(),
                labels=labels or {},
                unit=unit
            )
            self._metrics[key] = metric
            self._metric_history[name].append(metric)
    
    def record_timer(self, name: str, duration_seconds: float,
                     labels: Optional[Dict[str, str]] = None) -> None:
        """记录计时器指标（毫秒）"""
        self.record_histogram(name, duration_seconds * 1000, labels, "ms")
    
    def timer(self, name: str, labels: Optional[Dict[str, str]] = None):
        """计时器装饰器/上下文管理器"""
        class TimerContext:
            def __init__(ctx_self, monitor, name, labels):
                ctx_self.monitor = monitor
                ctx_self.name = name
                ctx_self.labels = labels
                ctx_self.start_time = None
            
            def __enter__(ctx_self):
                ctx_self.start_time = time.time()
                return ctx_self
            
            def __exit__(ctx_self, exc_type, exc_val, exc_tb):
                duration = time.time() - ctx_self.start_time
                ctx_self.monitor.record_timer(ctx_self.name, duration, ctx_self.labels)
        
        return TimerContext(self, name, labels)
    
    def timed(self, name: str, labels: Optional[Dict[str, str]] = None):
        """函数执行时间装饰器"""
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                with self.timer(name, labels):
                    return func(*args, **kwargs)
            return wrapper
        return decorator
    
    def _make_metric_key(self, name: str, labels: Optional[Dict[str, str]]) -> str:
        """生成指标键"""
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"
    
    def get_metric(self, name: str,
                   labels: Optional[Dict[str, str]] = None) -> Optional[MetricValue]:
        """获取指标值"""
        with self._lock:
            key = self._make_metric_key(name, labels)
            return self._metrics.get(key)
    
    def get_metrics_by_prefix(self, prefix: str) -> List[MetricValue]:
        """获取指定前缀的所有指标"""
        with self._lock:
            return [
                metric for key, metric in self._metrics.items()
                if key.startswith(prefix) or metric.name.startswith(prefix)
            ]
    
    def get_histogram_stats(self, name: str,
                            labels: Optional[Dict[str, str]] = None) -> Dict[str, float]:
        """获取直方图统计信息"""
        with self._lock:
            key = self._make_metric_key(name, labels)
            values = self._histograms.get(key, [])
            
            if not values:
                return {"count": 0, "sum": 0, "avg": 0, "min": 0, "max": 0}
            
            sorted_values = sorted(values)
            count = len(sorted_values)
            total = sum(sorted_values)
            
            return {
                "count": count,
                "sum": total,
                "avg": total / count,
                "min": sorted_values[0],
                "max": sorted_values[-1],
                "p50": sorted_values[int(count * 0.5)],
                "p90": sorted_values[int(count * 0.9)],
                "p95": sorted_values[int(count * 0.95)],
                "p99": sorted_values[int(count * 0.99)] if count >= 100 else sorted_values[-1]
            }
    
    def get_metric_history(self, name: str,
                           since: Optional[float] = None) -> List[MetricValue]:
        """获取指标历史"""
        with self._lock:
            history = list(self._metric_history.get(name, []))
            if since:
                history = [m for m in history if m.timestamp >= since]
            return history
    
    def take_snapshot(self) -> MetricSnapshot:
        """获取指标快照"""
        with self._lock:
            start = time.time()
            snapshot = {
                k: MetricValue(
                    name=v.name,
                    value=v.value,
                    metric_type=v.metric_type,
                    timestamp=v.timestamp,
                    labels=dict(v.labels),
                    unit=v.unit
                )
                for k, v in self._metrics.items()
            }
            return MetricSnapshot(
                timestamp=time.time(),
                metrics=snapshot,
                duration_ms=(time.time() - start) * 1000
            )
    
    def export_metrics(self, format: str = "json") -> str:
        """导出指标数据"""
        snapshot = self.take_snapshot()
        
        if format == "json":
            data = {
                "timestamp": snapshot.timestamp,
                "duration_ms": snapshot.duration_ms,
                "metrics": {
                    k: {
                        "name": v.name,
                        "value": v.value,
                        "type": v.metric_type.name,
                        "labels": v.labels,
                        "unit": v.unit,
                        "timestamp": v.timestamp
                    }
                    for k, v in snapshot.metrics.items()
                }
            }
            return json.dumps(data, indent=2, ensure_ascii=False)
        
        elif format == "prometheus":
            lines = []
            for key, metric in snapshot.metrics.items():
                labels_str = ",".join(f'{k}="{v}"' for k, v in metric.labels.items())
                if labels_str:
                    lines.append(f"{metric.name}{{{labels_str}}} {metric.value}")
                else:
                    lines.append(f"{metric.name} {metric.value}")
            return "\n".join(lines)
        
        return ""
    
    # ========== 阶段192: 健康检查系统 ==========
    
    def register_health_check(self, name: str,
                              check_func: Callable[[], Tuple[HealthStatus, str]],
                              interval_seconds: float = 60.0,
                              timeout_seconds: float = 10.0) -> None:
        """注册健康检查"""
        with self._lock:
            self._health_checks[name] = HealthCheck(
                name=name,
                check_func=check_func,
                interval_seconds=interval_seconds,
                timeout_seconds=timeout_seconds
            )
    
    def unregister_health_check(self, name: str) -> bool:
        """注销健康检查"""
        with self._lock:
            if name in self._health_checks:
                del self._health_checks[name]
                return True
            return False
    
    def run_health_check(self, name: str) -> Optional[Tuple[HealthStatus, str]]:
        """执行单个健康检查"""
        with self._lock:
            check = self._health_checks.get(name)
            if not check:
                return None
        
        try:
            status, message = check.check_func()
            
            with self._lock:
                check.last_check = time.time()
                check.last_status = status
                check.last_message = message
                
                if status == HealthStatus.UNHEALTHY:
                    check.consecutive_failures += 1
                else:
                    check.consecutive_failures = 0
            
            return status, message
        except Exception as e:
            with self._lock:
                check.last_check = time.time()
                check.last_status = HealthStatus.UNHEALTHY
                check.last_message = f"Check failed: {str(e)}"
                check.consecutive_failures += 1
            
            return HealthStatus.UNHEALTHY, f"Check failed: {str(e)}"
    
    def run_all_health_checks(self) -> HealthReport:
        """执行所有健康检查"""
        with self._lock:
            checks = dict(self._health_checks)
        
        results = {}
        failed = []
        degraded = []
        
        for name, check in checks.items():
            result = self.run_health_check(name)
            if result:
                status, message = result
                results[name] = {
                    "status": status.value,
                    "message": message,
                    "timestamp": check.last_check,
                    "consecutive_failures": check.consecutive_failures
                }
                
                if status == HealthStatus.UNHEALTHY:
                    failed.append(name)
                elif status == HealthStatus.DEGRADED:
                    degraded.append(name)
        
        # 确定整体状态
        if failed:
            overall = HealthStatus.UNHEALTHY
        elif degraded:
            overall = HealthStatus.DEGRADED
        elif results:
            overall = HealthStatus.HEALTHY
        else:
            overall = HealthStatus.UNKNOWN
        
        return HealthReport(
            timestamp=time.time(),
            overall_status=overall,
            checks=results,
            failed_checks=failed,
            degraded_checks=degraded
        )
    
    def get_health_report(self) -> HealthReport:
        """获取最新健康报告（不执行检查）"""
        with self._lock:
            results = {}
            failed = []
            degraded = []
            
            for name, check in self._health_checks.items():
                results[name] = {
                    "status": check.last_status.value,
                    "message": check.last_message,
                    "timestamp": check.last_check,
                    "consecutive_failures": check.consecutive_failures
                }
                
                if check.last_status == HealthStatus.UNHEALTHY:
                    failed.append(name)
                elif check.last_status == HealthStatus.DEGRADED:
                    degraded.append(name)
            
            if failed:
                overall = HealthStatus.UNHEALTHY
            elif degraded:
                overall = HealthStatus.DEGRADED
            elif results:
                overall = HealthStatus.HEALTHY
            else:
                overall = HealthStatus.UNKNOWN
            
            return HealthReport(
                timestamp=time.time(),
                overall_status=overall,
                checks=results,
                failed_checks=failed,
                degraded_checks=degraded
            )
    
    def start_health_check_loop(self) -> None:
        """启动健康检查循环"""
        with self._lock:
            if self._health_check_running:
                return
            
            self._health_check_running = True
            self._health_check_thread = threading.Thread(
                target=self._health_check_loop,
                daemon=True
            )
            self._health_check_thread.start()
    
    def stop_health_check_loop(self) -> None:
        """停止健康检查循环"""
        with self._lock:
            self._health_check_running = False
        
        if self._health_check_thread:
            self._health_check_thread.join(timeout=5.0)
    
    def _health_check_loop(self) -> None:
        """健康检查循环"""
        while True:
            with self._lock:
                if not self._health_check_running:
                    break
                checks = dict(self._health_checks)
            
            now = time.time()
            for name, check in checks.items():
                if check.last_check is None or \
                   (now - check.last_check) >= check.interval_seconds:
                    self.run_health_check(name)
            
            time.sleep(1.0)
    
    # ========== 阶段193: 资源监控与阈值告警 ==========
    
    def set_resource_threshold(self, resource_type: ResourceType,
                               warning: float,
                               critical: float) -> None:
        """设置资源阈值"""
        with self._lock:
            self._resource_thresholds[resource_type] = ResourceThreshold(
                resource_type=resource_type,
                warning_threshold=warning,
                critical_threshold=critical
            )
    
    def get_resource_threshold(self, resource_type: ResourceType) -> Optional[ResourceThreshold]:
        """获取资源阈值"""
        with self._lock:
            return self._resource_thresholds.get(resource_type)
    
    def _check_resource_alert(self, resource_type: ResourceType,
                              current_value: float,
                              usage_percent: float) -> Optional[ResourceAlert]:
        """检查资源是否需要告警"""
        threshold = self._resource_thresholds.get(resource_type)
        if not threshold:
            return None
        
        threshold.current_value = current_value
        threshold.current_usage_percent = usage_percent
        
        # 检查冷却期
        cooldown_key = f"{resource_type.value}_{'critical' if usage_percent >= threshold.critical_threshold else 'warning'}"
        last_alert = self._alert_cooldown.get(cooldown_key, 0)
        if time.time() - last_alert < self._alert_cooldown_seconds:
            return None
        
        if usage_percent >= threshold.critical_threshold:
            severity = "critical"
            message = f"{resource_type.value} usage critical: {usage_percent:.1f}%"
        elif usage_percent >= threshold.warning_threshold:
            severity = "warning"
            message = f"{resource_type.value} usage warning: {usage_percent:.1f}%"
        else:
            return None
        
        alert = ResourceAlert(
            alert_id=f"{resource_type.value}_{int(time.time())}",
            resource_type=resource_type,
            severity=severity,
            threshold=threshold.critical_threshold if severity == "critical" else threshold.warning_threshold,
            current_value=current_value,
            message=message,
            timestamp=time.time()
        )
        
        self._alert_cooldown[cooldown_key] = time.time()
        return alert
    
    def register_alert_handler(self, handler: Callable[[ResourceAlert], None]) -> None:
        """注册告警处理器"""
        with self._lock:
            self._alert_handlers.append(handler)
    
    def _trigger_alert(self, alert: ResourceAlert) -> None:
        """触发告警"""
        with self._lock:
            self._resource_alerts.append(alert)
            handlers = list(self._alert_handlers)
        
        for handler in handlers:
            try:
                handler(alert)
            except Exception:
                pass
    
    def get_resource_usage(self) -> Dict[ResourceType, Dict[str, float]]:
        """获取资源使用情况"""
        usage = {}
        
        # CPU使用率（简化实现）
        try:
            import psutil
            usage[ResourceType.CPU] = {
                "percent": psutil.cpu_percent(interval=0.1),
                "count": psutil.cpu_count()
            }
            
            # 内存使用率
            mem = psutil.virtual_memory()
            usage[ResourceType.MEMORY] = {
                "percent": mem.percent,
                "used_gb": mem.used / (1024**3),
                "total_gb": mem.total / (1024**3)
            }
            
            # 磁盘使用率
            disk = psutil.disk_usage('/')
            usage[ResourceType.DISK] = {
                "percent": (disk.used / disk.total) * 100,
                "used_gb": disk.used / (1024**3),
                "total_gb": disk.total / (1024**3)
            }
        except ImportError:
            # 如果没有psutil，返回模拟数据
            usage[ResourceType.CPU] = {"percent": 0.0, "count": 1}
            usage[ResourceType.MEMORY] = {"percent": 0.0, "used_gb": 0.0, "total_gb": 0.0}
            usage[ResourceType.DISK] = {"percent": 0.0, "used_gb": 0.0, "total_gb": 0.0}
        
        return usage
    
    def start_monitoring(self) -> None:
        """启动资源监控"""
        with self._lock:
            if self._monitoring_running:
                return
            
            self._monitoring_running = True
            self._monitoring_thread = threading.Thread(
                target=self._monitoring_loop,
                daemon=True
            )
            self._monitoring_thread.start()
    
    def stop_monitoring(self) -> None:
        """停止资源监控"""
        with self._lock:
            self._monitoring_running = False
        
        if self._monitoring_thread:
            self._monitoring_thread.join(timeout=5.0)
    
    def _monitoring_loop(self) -> None:
        """资源监控循环"""
        while True:
            with self._lock:
                if not self._monitoring_running:
                    break
            
            try:
                usage = self.get_resource_usage()
                
                for resource_type, data in usage.items():
                    percent = data.get("percent", 0)
                    current = data.get("used_gb", percent)
                    
                    # 记录指标
                    self.record_gauge(
                        f"resource_{resource_type.value}_usage_percent",
                        percent,
                        unit="%"
                    )
                    
                    # 检查告警
                    alert = self._check_resource_alert(resource_type, current, percent)
                    if alert:
                        self._trigger_alert(alert)
                
            except Exception:
                pass
            
            time.sleep(self._monitoring_interval)
    
    def get_active_alerts(self) -> List[ResourceAlert]:
        """获取活动告警"""
        with self._lock:
            return [
                alert for alert in self._resource_alerts
                if not alert.acknowledged
            ]
    
    def acknowledge_alert(self, alert_id: str) -> bool:
        """确认告警"""
        with self._lock:
            for alert in self._resource_alerts:
                if alert.alert_id == alert_id:
                    alert.acknowledged = True
                    return True
            return False
    
    def get_uptime_seconds(self) -> float:
        """获取系统运行时间"""
        return time.time() - self._start_time


# 全局单例
_system_monitor_instance: Optional[SystemMonitor] = None
_system_monitor_lock = threading.RLock()


def get_system_monitor() -> SystemMonitor:
    """获取系统监控器全局实例"""
    global _system_monitor_instance
    if _system_monitor_instance is None:
        with _system_monitor_lock:
            if _system_monitor_instance is None:
                _system_monitor_instance = SystemMonitor()
    return _system_monitor_instance
