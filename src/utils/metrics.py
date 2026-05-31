#!/usr/bin/env python3
"""
监控指标模块 - 阶段104-106
Prometheus格式的性能指标收集
"""

import time
import threading
from typing import Dict, Any, Optional
from collections import defaultdict


class MetricsCollector:
    """指标收集器"""
    
    def __init__(self):
        self._counters: Dict[str, int] = defaultdict(int)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, list] = defaultdict(list)
        self._lock = threading.RLock()
    
    def increment(self, name: str, value: int = 1, labels: Optional[Dict[str, str]] = None):
        """增加计数器"""
        with self._lock:
            key = self._format_key(name, labels)
            self._counters[key] += value
    
    def gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """设置仪表盘值"""
        with self._lock:
            key = self._format_key(name, labels)
            self._gauges[key] = value
    
    def observe(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """记录直方图观测值"""
        with self._lock:
            key = self._format_key(name, labels)
            self._histograms[key].append(value)
            # 保留最近1000个值
            if len(self._histograms[key]) > 1000:
                self._histograms[key] = self._histograms[key][-1000:]
    
    def _format_key(self, name: str, labels: Optional[Dict[str, str]]) -> str:
        """格式化指标键"""
        if labels:
            label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
            return f"{name}{{{label_str}}}"
        return name
    
    def get_prometheus_format(self) -> str:
        """获取Prometheus格式的指标"""
        lines = []
        
        with self._lock:
            # 计数器
            for key, value in self._counters.items():
                lines.append(f"# TYPE {key.split('{')[0]} counter")
                lines.append(f"{key} {value}")
            
            # 仪表盘
            for key, value in self._gauges.items():
                lines.append(f"# TYPE {key.split('{')[0]} gauge")
                lines.append(f"{key} {value}")
            
            # 直方图统计
            for key, values in self._histograms.items():
                if values:
                    name = key.split('{')[0]
                    lines.append(f"# TYPE {name} histogram")
                    lines.append(f"{key}_count {len(values)}")
                    lines.append(f"{key}_sum {sum(values)}")
                    lines.append(f"{key}_avg {sum(values)/len(values):.6f}")
        
        return "\n".join(lines)
    
    def get_json_metrics(self) -> Dict[str, Any]:
        """获取JSON格式的指标"""
        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": {
                    k: {"count": len(v), "sum": sum(v), "avg": sum(v)/len(v) if v else 0}
                    for k, v in self._histograms.items()
                }
            }


# 全局指标收集器
_metrics: Optional[MetricsCollector] = None


def get_metrics() -> MetricsCollector:
    """获取全局指标收集器"""
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics
