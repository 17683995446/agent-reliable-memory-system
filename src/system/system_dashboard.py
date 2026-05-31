"""
系统监控面板

第300阶段：状态汇总、性能指标、系统概览
遵循"图难于其易，为大于其细"原则，实现细粒度的系统监控与可视化

这是Agent Reliable Memory System第100个阶段的最终实现。
"""

import threading
import time
import psutil
from typing import Dict, List, Optional, Callable, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
from datetime import datetime


class MetricType(Enum):
    """指标类型"""
    COUNTER = "counter"         # 计数器
    GAUGE = "gauge"             # 仪表盘
    HISTOGRAM = "histogram"     # 直方图
    SUMMARY = "summary"         # 摘要


class HealthStatus(Enum):
    """健康状态"""
    HEALTHY = "healthy"         # 健康
    WARNING = "warning"         # 警告
    CRITICAL = "critical"       # 严重
    UNKNOWN = "unknown"         # 未知


@dataclass
class MetricValue:
    """指标值"""
    name: str
    value: float
    metric_type: MetricType
    timestamp: float = field(default_factory=time.time)
    labels: Dict[str, str] = field(default_factory=dict)
    unit: str = ""


@dataclass
class HealthCheck:
    """健康检查"""
    name: str
    check_func: Callable[[], Tuple[bool, str]]
    status: HealthStatus = HealthStatus.UNKNOWN
    message: str = ""
    last_check: float = 0.0
    check_interval: float = 60.0
    enabled: bool = True


@dataclass
class SystemMetrics:
    """系统指标"""
    timestamp: float = field(default_factory=time.time)
    
    # CPU指标
    cpu_percent: float = 0.0
    cpu_count: int = 0
    cpu_freq_mhz: float = 0.0
    
    # 内存指标
    memory_total: int = 0
    memory_available: int = 0
    memory_percent: float = 0.0
    memory_used: int = 0
    
    # 磁盘指标
    disk_total: int = 0
    disk_used: int = 0
    disk_free: int = 0
    disk_percent: float = 0.0
    
    # 网络指标
    net_bytes_sent: int = 0
    net_bytes_recv: int = 0
    net_packets_sent: int = 0
    net_packets_recv: int = 0
    
    # 进程指标
    process_count: int = 0
    thread_count: int = 0
    
    # 自定义指标
    custom_metrics: Dict[str, Any] = field(default_factory=dict)


class SystemDashboard:
    """
    系统监控面板
    
    职责：
    1. 收集和汇总系统指标
    2. 健康状态检查
    3. 性能监控和告警
    4. 系统概览展示
    
    设计原则：
    - 实时性与准确性平衡
    - 可扩展的指标收集
    - 多层次健康检查
    - 细粒度的状态追踪
    
    这是第100阶段的最终模块，标志着Agent Reliable Memory System
    100个阶段的完整实现。
    """
    
    _instance: Optional['SystemDashboard'] = None
    _lock = threading.RLock()
    
    def __new__(cls) -> 'SystemDashboard':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        # 指标存储
        self._metrics: Dict[str, MetricValue] = {}
        self._metric_history: Dict[str, deque] = {}
        self._history_size = 1000
        
        # 健康检查
        self._health_checks: Dict[str, HealthCheck] = {}
        
        # 系统指标历史
        self._system_metrics_history: deque = deque(maxlen=self._history_size)
        
        # 告警配置
        self._alert_thresholds: Dict[str, Tuple[float, float]] = {}
        self._alert_handlers: List[Callable] = []
        
        # 模块状态缓存
        self._module_status: Dict[str, Dict[str, Any]] = {}
        
        self._lock = threading.RLock()
        self._collection_interval = 5.0
        self._last_collection = 0.0
        
        # 启动时间
        self._start_time = time.time()
    
    def record_metric(
        self,
        name: str,
        value: float,
        metric_type: MetricType = MetricType.GAUGE,
        labels: Optional[Dict[str, str]] = None,
        unit: str = ""
    ) -> None:
        """
        记录指标
        
        Args:
            name: 指标名称
            value: 指标值
            metric_type: 指标类型
            labels: 标签
            unit: 单位
        """
        with self._lock:
            metric = MetricValue(
                name=name,
                value=value,
                metric_type=metric_type,
                labels=labels or {},
                unit=unit
            )
            
            self._metrics[name] = metric
            
            # 添加到历史
            if name not in self._metric_history:
                self._metric_history[name] = deque(maxlen=self._history_size)
            self._metric_history[name].append(metric)
            
            # 检查告警阈值
            self._check_alert_threshold(name, value)
    
    def increment_counter(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        """
        增加计数器
        
        Args:
            name: 计数器名称
            value: 增加值
            labels: 标签
        """
        with self._lock:
            current = self._metrics.get(name)
            if current and current.metric_type == MetricType.COUNTER:
                new_value = current.value + value
            else:
                new_value = value
            
            self.record_metric(name, new_value, MetricType.COUNTER, labels)
    
    def get_metric(self, name: str) -> Optional[MetricValue]:
        """
        获取指标
        
        Args:
            name: 指标名称
        
        Returns:
            指标值
        """
        with self._lock:
            return self._metrics.get(name)
    
    def get_metric_history(self, name: str, limit: int = 100) -> List[MetricValue]:
        """
        获取指标历史
        
        Args:
            name: 指标名称
            limit: 返回数量限制
        
        Returns:
            指标历史列表
        """
        with self._lock:
            history = self._metric_history.get(name, deque())
            return list(history)[-limit:]
    
    def get_all_metrics(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有指标
        
        Returns:
            所有指标的字典
        """
        with self._lock:
            return {
                name: {
                    'value': metric.value,
                    'type': metric.metric_type.value,
                    'timestamp': metric.timestamp,
                    'labels': metric.labels,
                    'unit': metric.unit
                }
                for name, metric in self._metrics.items()
            }
    
    def register_health_check(
        self,
        name: str,
        check_func: Callable[[], Tuple[bool, str]],
        interval: float = 60.0
    ) -> bool:
        """
        注册健康检查
        
        Args:
            name: 检查名称
            check_func: 检查函数，返回(是否健康, 消息)
            interval: 检查间隔（秒）
        
        Returns:
            是否注册成功
        """
        with self._lock:
            if name in self._health_checks:
                return False
            
            self._health_checks[name] = HealthCheck(
                name=name,
                check_func=check_func,
                check_interval=interval
            )
            return True
    
    def run_health_check(self, name: str) -> Optional[HealthCheck]:
        """
        执行健康检查
        
        Args:
            name: 检查名称
        
        Returns:
            健康检查结果
        """
        with self._lock:
            check = self._health_checks.get(name)
            if not check or not check.enabled:
                return None
            
            try:
                is_healthy, message = check.check_func()
                check.status = HealthStatus.HEALTHY if is_healthy else HealthStatus.CRITICAL
                check.message = message
                check.last_check = time.time()
            except Exception as e:
                check.status = HealthStatus.CRITICAL
                check.message = f"检查异常: {str(e)}"
                check.last_check = time.time()
            
            return check
    
    def run_all_health_checks(self) -> Dict[str, Dict[str, Any]]:
        """
        执行所有健康检查
        
        Returns:
            所有检查结果的字典
        """
        results = {}
        with self._lock:
            for name in self._health_checks:
                check = self.run_health_check(name)
                if check:
                    results[name] = {
                        'status': check.status.value,
                        'message': check.message,
                        'last_check': check.last_check
                    }
        return results
    
    def get_overall_health(self) -> HealthStatus:
        """
        获取整体健康状态
        
        Returns:
            整体健康状态
        """
        with self._lock:
            checks = self.run_all_health_checks()
            
            statuses = [c['status'] for c in checks.values()]
            
            if HealthStatus.CRITICAL.value in statuses:
                return HealthStatus.CRITICAL
            elif HealthStatus.WARNING.value in statuses:
                return HealthStatus.WARNING
            elif HealthStatus.HEALTHY.value in statuses:
                return HealthStatus.HEALTHY
            else:
                return HealthStatus.UNKNOWN
    
    def collect_system_metrics(self) -> SystemMetrics:
        """
        收集系统指标
        
        Returns:
            系统指标对象
        """
        metrics = SystemMetrics()
        
        try:
            # CPU
            metrics.cpu_percent = psutil.cpu_percent(interval=0.1)
            metrics.cpu_count = psutil.cpu_count()
            cpu_freq = psutil.cpu_freq()
            if cpu_freq:
                metrics.cpu_freq_mhz = cpu_freq.current
            
            # 内存
            memory = psutil.virtual_memory()
            metrics.memory_total = memory.total
            metrics.memory_available = memory.available
            metrics.memory_percent = memory.percent
            metrics.memory_used = memory.used
            
            # 磁盘
            disk = psutil.disk_usage('/')
            metrics.disk_total = disk.total
            metrics.disk_used = disk.used
            metrics.disk_free = disk.free
            metrics.disk_percent = disk.percent
            
            # 网络
            net = psutil.net_io_counters()
            if net:
                metrics.net_bytes_sent = net.bytes_sent
                metrics.net_bytes_recv = net.bytes_recv
                metrics.net_packets_sent = net.packets_sent
                metrics.net_packets_recv = net.packets_recv
            
            # 进程
            metrics.process_count = len(psutil.pids())
            metrics.thread_count = threading.active_count()
            
        except Exception:
            pass
        
        with self._lock:
            self._system_metrics_history.append(metrics)
            self._last_collection = time.time()
        
        return metrics
    
    def get_system_metrics(self) -> Optional[SystemMetrics]:
        """
        获取当前系统指标
        
        Returns:
            系统指标对象
        """
        # 如果距离上次收集超过间隔，重新收集
        if time.time() - self._last_collection > self._collection_interval:
            return self.collect_system_metrics()
        
        with self._lock:
            if self._system_metrics_history:
                return self._system_metrics_history[-1]
            return None
    
    def get_system_metrics_history(self, limit: int = 100) -> List[SystemMetrics]:
        """
        获取系统指标历史
        
        Args:
            limit: 返回数量限制
        
        Returns:
            系统指标历史列表
        """
        with self._lock:
            return list(self._system_metrics_history)[-limit:]
    
    def set_alert_threshold(
        self,
        metric_name: str,
        warning_threshold: float,
        critical_threshold: float
    ) -> None:
        """
        设置告警阈值
        
        Args:
            metric_name: 指标名称
            warning_threshold: 警告阈值
            critical_threshold: 严重阈值
        """
        with self._lock:
            self._alert_thresholds[metric_name] = (warning_threshold, critical_threshold)
    
    def _check_alert_threshold(self, metric_name: str, value: float) -> None:
        """检查告警阈值"""
        if metric_name not in self._alert_thresholds:
            return
        
        warning, critical = self._alert_thresholds[metric_name]
        
        if value >= critical:
            self._trigger_alert(metric_name, value, HealthStatus.CRITICAL)
        elif value >= warning:
            self._trigger_alert(metric_name, value, HealthStatus.WARNING)
    
    def _trigger_alert(self, metric_name: str, value: float, severity: HealthStatus) -> None:
        """触发告警"""
        alert = {
            'metric': metric_name,
            'value': value,
            'severity': severity.value,
            'timestamp': time.time()
        }
        
        for handler in self._alert_handlers:
            try:
                handler(alert)
            except Exception:
                pass
    
    def register_alert_handler(self, handler: Callable[[Dict[str, Any]], None]) -> bool:
        """
        注册告警处理器
        
        Args:
            handler: 告警处理函数
        
        Returns:
            是否注册成功
        """
        with self._lock:
            if handler in self._alert_handlers:
                return False
            self._alert_handlers.append(handler)
            return True
    
    def update_module_status(self, module_name: str, status: Dict[str, Any]) -> None:
        """
        更新模块状态
        
        Args:
            module_name: 模块名称
            status: 状态信息
        """
        with self._lock:
            status['last_update'] = time.time()
            self._module_status[module_name] = status
    
    def get_module_status(self, module_name: str) -> Optional[Dict[str, Any]]:
        """
        获取模块状态
        
        Args:
            module_name: 模块名称
        
        Returns:
            模块状态
        """
        with self._lock:
            return self._module_status.get(module_name)
    
    def get_all_module_status(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有模块状态
        
        Returns:
            所有模块状态的字典
        """
        with self._lock:
            return dict(self._module_status)
    
    def get_system_overview(self) -> Dict[str, Any]:
        """
        获取系统概览
        
        Returns:
            系统概览字典
        """
        # 确保有最新的系统指标
        self.collect_system_metrics()
        
        with self._lock:
            uptime = time.time() - self._start_time
            
            # 格式化运行时间
            days = int(uptime // 86400)
            hours = int((uptime % 86400) // 3600)
            minutes = int((uptime % 3600) // 60)
            seconds = int(uptime % 60)
            
            uptime_str = ""
            if days > 0:
                uptime_str += f"{days}天"
            if hours > 0 or days > 0:
                uptime_str += f"{hours}小时"
            if minutes > 0 or hours > 0 or days > 0:
                uptime_str += f"{minutes}分"
            uptime_str += f"{seconds}秒"
            
            # 获取最新系统指标
            latest_metrics = None
            if self._system_metrics_history:
                latest_metrics = self._system_metrics_history[-1]
            
            # 统计模块状态
            module_stats = {
                'total': len(self._module_status),
                'healthy': 0,
                'warning': 0,
                'critical': 0
            }
            
            for status in self._module_status.values():
                health = status.get('health', 'unknown')
                if health == 'healthy':
                    module_stats['healthy'] += 1
                elif health == 'warning':
                    module_stats['warning'] += 1
                elif health == 'critical':
                    module_stats['critical'] += 1
            
            overview = {
                'system_name': 'Agent Reliable Memory System',
                'version': '1.0.0',
                'phase': 'Phase 20/20 (Complete)',
                'stage': 'Stage 300/300 (Complete)',
                'status': 'OPERATIONAL',
                'uptime': {
                    'seconds': uptime,
                    'formatted': uptime_str
                },
                'timestamp': time.time(),
                'datetime': datetime.now().isoformat(),
                'health': self.get_overall_health().value,
                'modules': module_stats,
                'metrics': {
                    'total': len(self._metrics),
                    'health_checks': len(self._health_checks)
                }
            }
            
            # 添加系统资源信息
            if latest_metrics:
                overview['resources'] = {
                    'cpu': {
                        'percent': latest_metrics.cpu_percent,
                        'count': latest_metrics.cpu_count
                    },
                    'memory': {
                        'total_gb': round(latest_metrics.memory_total / (1024**3), 2),
                        'used_gb': round(latest_metrics.memory_used / (1024**3), 2),
                        'percent': latest_metrics.memory_percent
                    },
                    'disk': {
                        'total_gb': round(latest_metrics.disk_total / (1024**3), 2),
                        'used_gb': round(latest_metrics.disk_used / (1024**3), 2),
                        'percent': latest_metrics.disk_percent
                    }
                }
            
            return overview
    
    def generate_report(self) -> Dict[str, Any]:
        """
        生成系统报告
        
        Returns:
            系统报告字典
        """
        return {
            'overview': self.get_system_overview(),
            'health_checks': self.run_all_health_checks(),
            'metrics': self.get_all_metrics(),
            'module_status': self.get_all_module_status()
        }
    
    def reset(self) -> None:
        """重置监控面板"""
        with self._lock:
            self._metrics.clear()
            self._metric_history.clear()
            self._health_checks.clear()
            self._system_metrics_history.clear()
            self._module_status.clear()
            self._alert_thresholds.clear()
            self._alert_handlers.clear()
            self._start_time = time.time()


# 全局监控面板实例
_system_dashboard: Optional[SystemDashboard] = None
_dashboard_lock = threading.Lock()


def get_system_dashboard() -> SystemDashboard:
    """获取全局系统监控面板实例"""
    global _system_dashboard
    if _system_dashboard is None:
        with _dashboard_lock:
            if _system_dashboard is None:
                _system_dashboard = SystemDashboard()
    return _system_dashboard
