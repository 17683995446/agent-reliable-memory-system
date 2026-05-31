#!/usr/bin/env python3
"""
配置调优模块 - 阶段79-80
动态调整系统参数以优化性能
"""

import os
import yaml
import json
import time
import threading
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class TuningResult:
    """调优结果"""
    parameter: str
    old_value: Any
    new_value: Any
    reason: str
    timestamp: float
    applied: bool


class ConfigTuner:
    """
    配置调优器
    
    根据系统运行状态动态调整配置参数
    """
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or os.path.join(
            os.path.dirname(__file__), "../../config/system.yaml"
        )
        self.config: Dict[str, Any] = {}
        self._lock = threading.RLock()
        self._tuning_history: List[TuningResult] = []
        self._load_config()
    
    def _load_config(self):
        """加载配置文件"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"加载配置失败: {e}")
            self.config = self._default_config()
    
    def _default_config(self) -> Dict[str, Any]:
        """默认配置"""
        return {
            "memory": {
                "l1": {"max_size": 1000, "ttl_seconds": 3600},
                "l2": {"max_size": 10000, "index_type": "Flat"},
                "l3": {"max_triples": 100000}
            },
            "recall": {
                "top_k": 5,
                "min_similarity": 0.7,
                "enable_deduplication": True
            },
            "governance": {
                "eviction_threshold": 0.3,
                "conflict_threshold": 0.8,
                "poison_threshold": 0.9
            },
            "performance": {
                "cache_ttl": 300,
                "cache_size": 1000,
                "max_concurrent_sessions": 100
            }
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值
        
        Args:
            key: 配置键，支持点号分隔（如"memory.l1.max_size"）
            default: 默认值
        
        Returns:
            配置值
        """
        with self._lock:
            keys = key.split('.')
            value = self.config
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    return default
            return value
    
    def set(self, key: str, value: Any, persist: bool = True) -> bool:
        """
        设置配置值
        
        Args:
            key: 配置键
            value: 配置值
            persist: 是否持久化到文件
        
        Returns:
            是否设置成功
        """
        with self._lock:
            keys = key.split('.')
            config = self.config
            for k in keys[:-1]:
                if k not in config:
                    config[k] = {}
                config = config[k]
            config[keys[-1]] = value
            
            if persist:
                return self._save_config()
            return True
    
    def _save_config(self) -> bool:
        """保存配置到文件"""
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self.config, f, allow_unicode=True, default_flow_style=False)
            return True
        except Exception as e:
            print(f"保存配置失败: {e}")
            return False
    
    def tune_based_on_metrics(self, metrics: Dict[str, Any]) -> List[TuningResult]:
        """
        基于性能指标自动调优
        
        Args:
            metrics: 性能指标字典
        
        Returns:
            调优结果列表
        """
        results = []
        
        # 1. 根据召回延迟调整top_k
        if 'recall_latency_ms' in metrics:
            latency = metrics['recall_latency_ms']
            current_top_k = self.get('recall.top_k', 5)
            
            if latency > 100:  # 延迟过高
                new_top_k = max(3, current_top_k - 1)
                result = self._apply_tuning(
                    'recall.top_k', new_top_k,
                    f"召回延迟过高({latency:.1f}ms)，减少top_k"
                )
                results.append(result)
            elif latency < 10 and current_top_k < 10:  # 延迟很低，可以增加
                new_top_k = current_top_k + 1
                result = self._apply_tuning(
                    'recall.top_k', new_top_k,
                    f"召回延迟很低({latency:.1f}ms)，增加top_k提升召回率"
                )
                results.append(result)
        
        # 2. 根据内存使用率调整缓存大小
        if 'memory_usage_percent' in metrics:
            mem_usage = metrics['memory_usage_percent']
            current_cache_size = self.get('performance.cache_size', 1000)
            
            if mem_usage > 80:  # 内存使用率过高
                new_size = int(current_cache_size * 0.8)
                result = self._apply_tuning(
                    'performance.cache_size', new_size,
                    f"内存使用率过高({mem_usage:.1f}%)，减少缓存大小"
                )
                results.append(result)
            elif mem_usage < 50 and current_cache_size < 5000:  # 内存充足
                new_size = int(current_cache_size * 1.2)
                result = self._apply_tuning(
                    'performance.cache_size', new_size,
                    f"内存充足({mem_usage:.1f}%)，增加缓存大小"
                )
                results.append(result)
        
        # 3. 根据命中率调整缓存TTL
        if 'cache_hit_rate' in metrics:
            hit_rate = metrics['cache_hit_rate']
            current_ttl = self.get('performance.cache_ttl', 300)
            
            if hit_rate < 0.3:  # 命中率过低
                new_ttl = int(current_ttl * 0.8)
                result = self._apply_tuning(
                    'performance.cache_ttl', new_ttl,
                    f"缓存命中率过低({hit_rate:.1%})，减少TTL"
                )
                results.append(result)
            elif hit_rate > 0.8:  # 命中率很高
                new_ttl = int(current_ttl * 1.2)
                result = self._apply_tuning(
                    'performance.cache_ttl', new_ttl,
                    f"缓存命中率很高({hit_rate:.1%})，增加TTL"
                )
                results.append(result)
        
        # 4. 根据L1内存使用率调整容量
        if 'l1_usage_percent' in metrics:
            l1_usage = metrics['l1_usage_percent']
            current_max = self.get('memory.l1.max_size', 1000)
            
            if l1_usage > 90:  # L1使用率过高
                new_max = int(current_max * 1.3)
                result = self._apply_tuning(
                    'memory.l1.max_size', new_max,
                    f"L1内存使用率过高({l1_usage:.1f}%)，扩容"
                )
                results.append(result)
        
        return results
    
    def _apply_tuning(self, parameter: str, new_value: Any, reason: str) -> TuningResult:
        """应用调优"""
        old_value = self.get(parameter)
        applied = self.set(parameter, new_value, persist=True)
        
        result = TuningResult(
            parameter=parameter,
            old_value=old_value,
            new_value=new_value,
            reason=reason,
            timestamp=time.time(),
            applied=applied
        )
        
        self._tuning_history.append(result)
        return result
    
    def get_tuning_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取调优历史"""
        history = self._tuning_history[-limit:]
        return [asdict(h) for h in history]
    
    def suggest_tuning(self, current_metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        提供调优建议（不实际应用）
        
        Args:
            current_metrics: 当前性能指标
        
        Returns:
            调优建议列表
        """
        suggestions = []
        
        # 召回性能建议
        if 'recall_latency_ms' in current_metrics:
            latency = current_metrics['recall_latency_ms']
            if latency > 100:
                suggestions.append({
                    "priority": "high",
                    "parameter": "recall.top_k",
                    "suggested_value": 3,
                    "current_value": self.get('recall.top_k'),
                    "reason": f"召回延迟过高({latency:.1f}ms)，建议减少top_k",
                    "expected_improvement": "降低30-50%召回延迟"
                })
        
        # 内存使用建议
        if 'memory_usage_percent' in current_metrics:
            mem_usage = current_metrics['memory_usage_percent']
            if mem_usage > 85:
                suggestions.append({
                    "priority": "high",
                    "parameter": "performance.cache_size",
                    "suggested_value": int(self.get('performance.cache_size', 1000) * 0.7),
                    "current_value": self.get('performance.cache_size'),
                    "reason": f"内存使用率过高({mem_usage:.1f}%)，建议减少缓存",
                    "expected_improvement": "降低10-20%内存占用"
                })
        
        # 缓存效率建议
        if 'cache_hit_rate' in current_metrics:
            hit_rate = current_metrics['cache_hit_rate']
            if hit_rate < 0.2:
                suggestions.append({
                    "priority": "medium",
                    "parameter": "performance.cache_ttl",
                    "suggested_value": 60,
                    "current_value": self.get('performance.cache_ttl'),
                    "reason": f"缓存命中率过低({hit_rate:.1%})，建议缩短TTL",
                    "expected_improvement": "提高缓存新鲜度"
                })
        
        # L1内存建议
        if 'l1_usage_percent' in current_metrics:
            l1_usage = current_metrics['l1_usage_percent']
            if l1_usage > 85:
                suggestions.append({
                    "priority": "medium",
                    "parameter": "memory.l1.max_size",
                    "suggested_value": int(self.get('memory.l1.max_size', 1000) * 1.5),
                    "current_value": self.get('memory.l1.max_size'),
                    "reason": f"L1内存使用率过高({l1_usage:.1f}%)，建议扩容",
                    "expected_improvement": "减少L1淘汰频率"
                })
        
        # 按优先级排序
        priority_order = {"high": 0, "medium": 1, "low": 2}
        suggestions.sort(key=lambda x: priority_order.get(x["priority"], 3))
        
        return suggestions
    
    def export_config(self, export_path: Optional[str] = None) -> str:
        """
        导出当前配置
        
        Args:
            export_path: 导出路径
        
        Returns:
            导出文件路径
        """
        if export_path is None:
            timestamp = int(time.time())
            export_path = f"config_backup_{timestamp}.yaml"
        
        try:
            with self._lock:
                with open(export_path, 'w', encoding='utf-8') as f:
                    yaml.dump(self.config, f, allow_unicode=True, default_flow_style=False)
            return export_path
        except Exception as e:
            print(f"导出配置失败: {e}")
            return ""
    
    def import_config(self, import_path: str, merge: bool = False) -> bool:
        """
        导入配置
        
        Args:
            import_path: 导入文件路径
            merge: 是否合并而非替换
        
        Returns:
            是否导入成功
        """
        try:
            with open(import_path, 'r', encoding='utf-8') as f:
                new_config = yaml.safe_load(f)
            
            with self._lock:
                if merge:
                    self._deep_merge(self.config, new_config)
                else:
                    self.config = new_config
            
            return self._save_config()
        except Exception as e:
            print(f"导入配置失败: {e}")
            return False
    
    def _deep_merge(self, base: Dict, update: Dict):
        """深度合并字典"""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value
    
    def reset_to_defaults(self) -> bool:
        """重置为默认配置"""
        with self._lock:
            self.config = self._default_config()
        return self._save_config()


class AdaptiveTuner:
    """
    自适应调优器
    
    持续监控系统状态并自动调整参数
    """
    
    def __init__(self, config_tuner: ConfigTuner, interval_seconds: int = 60):
        self.config_tuner = config_tuner
        self.interval = interval_seconds
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._metric_collectors: List[Callable[[], Dict[str, Any]]] = []
        self._on_tuning_callbacks: List[Callable[[List[TuningResult]], None]] = []
    
    def register_metric_collector(self, collector: Callable[[], Dict[str, Any]]):
        """注册指标收集器"""
        self._metric_collectors.append(collector)
    
    def register_tuning_callback(self, callback: Callable[[List[TuningResult]], None]):
        """注册调优回调"""
        self._on_tuning_callbacks.append(callback)
    
    def start(self):
        """启动自适应调优"""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._tuning_loop, daemon=True)
        self._thread.start()
        print(f"自适应调优已启动，间隔: {self.interval}秒")
    
    def stop(self):
        """停止自适应调优"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        print("自适应调优已停止")
    
    def _tuning_loop(self):
        """调优循环"""
        while self._running:
            try:
                # 收集所有指标
                all_metrics = {}
                for collector in self._metric_collectors:
                    try:
                        metrics = collector()
                        all_metrics.update(metrics)
                    except Exception as e:
                        print(f"指标收集失败: {e}")
                
                # 执行调优
                if all_metrics:
                    results = self.config_tuner.tune_based_on_metrics(all_metrics)
                    
                    # 触发回调
                    if results:
                        for callback in self._on_tuning_callbacks:
                            try:
                                callback(results)
                            except Exception as e:
                                print(f"调优回调失败: {e}")
                
                # 等待下一个周期
                time.sleep(self.interval)
            except Exception as e:
                print(f"调优循环错误: {e}")
                time.sleep(self.interval)


# 全局配置调优器实例
_default_tuner: Optional[ConfigTuner] = None


def get_config_tuner() -> ConfigTuner:
    """获取全局配置调优器实例"""
    global _default_tuner
    if _default_tuner is None:
        _default_tuner = ConfigTuner()
    return _default_tuner
