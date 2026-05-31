"""
监控模块 - 系统可观测性与告警

本模块提供完整的监控能力，包括：
- 系统监控器: 性能指标收集、健康检查、资源监控
- 告警管理器: 告警规则、通知渠道、告警抑制
- 日志聚合器: 结构化日志、日志分析、日志查询
- 性能分析器: 调用链追踪、热点分析、瓶颈检测
- 自动化运维: 自愈机制、自动扩缩容、定时任务

遵循"图难于其易，为大于其细"原则，所有组件设计简洁、确定性强。
"""

from .system_monitor import SystemMonitor, get_system_monitor
from .alert_manager import AlertManager, get_alert_manager
from .log_aggregator import LogAggregator, get_log_aggregator
from .profiler import PerformanceProfiler, get_profiler
from .auto_ops import AutoOps, get_auto_ops

__all__ = [
    'SystemMonitor', 'get_system_monitor',
    'AlertManager', 'get_alert_manager',
    'LogAggregator', 'get_log_aggregator',
    'PerformanceProfiler', 'get_profiler',
    'AutoOps', 'get_auto_ops',
]
