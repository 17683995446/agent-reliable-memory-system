"""
实验追踪 (ExperimentTracker)
阶段257-259: 实验记录、参数追踪、结果比较

基于第一性原则设计:
1. 确定性: 实验结果确定性记录，无随机性
2. 可追溯性: 完整的参数和结果历史
3. 可比较性: 支持多实验对比分析
"""

import threading
import time
import hashlib
import json
from typing import Dict, List, Optional, Any, Callable, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict


class ExperimentStatus(Enum):
    """实验状态"""
    CREATED = "created"          # 已创建
    RUNNING = "running"          # 运行中
    COMPLETED = "completed"      # 已完成
    FAILED = "failed"            # 失败
    CANCELLED = "cancelled"      # 已取消
    PAUSED = "paused"            # 已暂停


class MetricAggregation(Enum):
    """指标聚合方式"""
    LAST = "last"                # 最后值
    MIN = "min"                  # 最小值
    MAX = "max"                  # 最大值
    AVG = "avg"                  # 平均值
    SUM = "sum"                  # 求和


@dataclass
class Experiment:
    """实验"""
    experiment_id: str
    name: str
    description: str = ""
    status: ExperimentStatus = ExperimentStatus.CREATED
    parameters: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    ended_at: Optional[float] = None
    created_by: str = "system"
    parent_id: Optional[str] = None  # 父实验ID，用于实验继承


@dataclass
class MetricRecord:
    """指标记录"""
    experiment_id: str
    metric_name: str
    value: float
    step: int = 0
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ArtifactRecord:
    """产物记录"""
    artifact_id: str
    experiment_id: str
    name: str
    artifact_type: str  # "model", "dataset", "plot", "log", "other"
    path: Optional[str] = None
    data: Optional[bytes] = None
    size: int = 0
    created_at: float = field(default_factory=time.time)


class ExperimentTracker:
    """
    实验追踪器
    
    核心功能:
    1. 实验记录: 实验创建、状态管理、生命周期跟踪
    2. 参数追踪: 参数记录、变更追踪、参数继承
    3. 结果比较: 多实验对比、指标排名、最佳参数识别
    """
    
    def __init__(self):
        self._lock = threading.RLock()
        
        # 实验存储
        self._experiments: Dict[str, Experiment] = {}
        self._active_experiment: Optional[str] = None
        
        # 指标存储
        self._metrics: Dict[str, List[MetricRecord]] = defaultdict(list)
        self._max_metrics_per_experiment = 10000
        
        # 产物存储
        self._artifacts: Dict[str, List[ArtifactRecord]] = defaultdict(list)
        
        # 参数历史
        self._parameter_history: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        
        # 比较结果缓存
        self._comparison_cache: Dict[str, Dict[str, Any]] = {}
    
    # ==================== 阶段257: 实验记录 ====================
    
    def create_experiment(self, name: str,
                         description: str = "",
                         parameters: Optional[Dict[str, Any]] = None,
                         tags: Optional[List[str]] = None,
                         created_by: str = "system",
                         parent_id: Optional[str] = None) -> str:
        """
        创建实验
        
        Args:
            name: 实验名称
            description: 描述
            parameters: 参数
            tags: 标签
            created_by: 创建者
            parent_id: 父实验ID
            
        Returns:
            实验ID
        """
        with self._lock:
            experiment_id = self._generate_experiment_id(name)
            
            # 继承父实验参数
            final_params = {}
            if parent_id and parent_id in self._experiments:
                final_params.update(self._experiments[parent_id].parameters)
            if parameters:
                final_params.update(parameters)
            
            experiment = Experiment(
                experiment_id=experiment_id,
                name=name,
                description=description,
                parameters=final_params,
                tags=tags or [],
                created_by=created_by,
                parent_id=parent_id
            )
            
            self._experiments[experiment_id] = experiment
            
            # 记录参数历史
            self._parameter_history[experiment_id].append({
                "parameters": final_params.copy(),
                "timestamp": time.time(),
                "action": "created"
            })
            
            return experiment_id
    
    def _generate_experiment_id(self, name: str) -> str:
        """生成实验ID"""
        timestamp = str(time.time())
        data = f"{name}_{timestamp}"
        return hashlib.md5(data.encode()).hexdigest()[:16]
    
    def get_experiment(self, experiment_id: str) -> Optional[Experiment]:
        """
        获取实验
        
        Args:
            experiment_id: 实验ID
            
        Returns:
            实验信息
        """
        with self._lock:
            return self._experiments.get(experiment_id)
    
    def start_experiment(self, experiment_id: str) -> bool:
        """
        开始实验
        
        Args:
            experiment_id: 实验ID
            
        Returns:
            是否开始成功
        """
        with self._lock:
            if experiment_id not in self._experiments:
                return False
            
            experiment = self._experiments[experiment_id]
            if experiment.status != ExperimentStatus.CREATED:
                return False
            
            experiment.status = ExperimentStatus.RUNNING
            experiment.started_at = time.time()
            self._active_experiment = experiment_id
            
            return True
    
    def end_experiment(self, experiment_id: str,
                      status: ExperimentStatus = ExperimentStatus.COMPLETED) -> bool:
        """
        结束实验
        
        Args:
            experiment_id: 实验ID
            status: 结束状态
            
        Returns:
            是否结束成功
        """
        with self._lock:
            if experiment_id not in self._experiments:
                return False
            
            experiment = self._experiments[experiment_id]
            experiment.status = status
            experiment.ended_at = time.time()
            
            if self._active_experiment == experiment_id:
                self._active_experiment = None
            
            return True
    
    def get_active_experiment(self) -> Optional[Experiment]:
        """获取当前活跃实验"""
        with self._lock:
            if self._active_experiment:
                return self._experiments.get(self._active_experiment)
            return None
    
    def list_experiments(self, status: Optional[ExperimentStatus] = None,
                        tags: Optional[List[str]] = None,
                        limit: int = 100) -> List[Experiment]:
        """
        列出实验
        
        Args:
            status: 状态过滤
            tags: 标签过滤
            limit: 数量限制
            
        Returns:
            实验列表
        """
        with self._lock:
            experiments = list(self._experiments.values())
            
            if status:
                experiments = [e for e in experiments if e.status == status]
            
            if tags:
                experiments = [e for e in experiments 
                             if any(t in e.tags for t in tags)]
            
            # 按创建时间降序
            experiments.sort(key=lambda x: x.created_at, reverse=True)
            return experiments[:limit]
    
    def delete_experiment(self, experiment_id: str) -> bool:
        """
        删除实验
        
        Args:
            experiment_id: 实验ID
            
        Returns:
            是否删除成功
        """
        with self._lock:
            if experiment_id not in self._experiments:
                return False
            
            del self._experiments[experiment_id]
            
            if experiment_id in self._metrics:
                del self._metrics[experiment_id]
            
            if experiment_id in self._artifacts:
                del self._artifacts[experiment_id]
            
            if experiment_id in self._parameter_history:
                del self._parameter_history[experiment_id]
            
            return True
    
    # ==================== 阶段258: 参数追踪 ====================
    
    def log_parameter(self, experiment_id: str, key: str, value: Any) -> bool:
        """
        记录参数
        
        Args:
            experiment_id: 实验ID
            key: 参数名
            value: 参数值
            
        Returns:
            是否记录成功
        """
        with self._lock:
            if experiment_id not in self._experiments:
                return False
            
            experiment = self._experiments[experiment_id]
            old_value = experiment.parameters.get(key)
            experiment.parameters[key] = value
            
            # 记录变更历史
            self._parameter_history[experiment_id].append({
                "key": key,
                "old_value": old_value,
                "new_value": value,
                "timestamp": time.time(),
                "action": "update"
            })
            
            return True
    
    def log_parameters(self, experiment_id: str,
                      parameters: Dict[str, Any]) -> int:
        """
        批量记录参数
        
        Args:
            experiment_id: 实验ID
            parameters: 参数字典
            
        Returns:
            记录成功的参数数量
        """
        with self._lock:
            count = 0
            for key, value in parameters.items():
                if self.log_parameter(experiment_id, key, value):
                    count += 1
            return count
    
    def get_parameters(self, experiment_id: str) -> Optional[Dict[str, Any]]:
        """
        获取实验参数
        
        Args:
            experiment_id: 实验ID
            
        Returns:
            参数字典
        """
        with self._lock:
            if experiment_id not in self._experiments:
                return None
            return self._experiments[experiment_id].parameters.copy()
    
    def get_parameter_history(self, experiment_id: str,
                             key: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取参数变更历史
        
        Args:
            experiment_id: 实验ID
            key: 参数名过滤
            
        Returns:
            变更历史列表
        """
        with self._lock:
            history = self._parameter_history.get(experiment_id, [])
            
            if key:
                history = [h for h in history if h.get("key") == key]
            
            return history.copy()
    
    def log_metric(self, experiment_id: str, metric_name: str,
                  value: float, step: int = 0,
                  metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        记录指标
        
        Args:
            experiment_id: 实验ID
            metric_name: 指标名
            value: 指标值
            step: 步数
            metadata: 元数据
            
        Returns:
            是否记录成功
        """
        with self._lock:
            if experiment_id not in self._experiments:
                return False
            
            record = MetricRecord(
                experiment_id=experiment_id,
                metric_name=metric_name,
                value=value,
                step=step,
                metadata=metadata or {}
            )
            
            self._metrics[experiment_id].append(record)
            
            # 限制记录数量
            if len(self._metrics[experiment_id]) > self._max_metrics_per_experiment:
                self._metrics[experiment_id] = self._metrics[experiment_id][-self._max_metrics_per_experiment:]
            
            return True
    
    def get_metrics(self, experiment_id: str,
                   metric_name: Optional[str] = None) -> List[MetricRecord]:
        """
        获取指标记录
        
        Args:
            experiment_id: 实验ID
            metric_name: 指标名过滤
            
        Returns:
            指标记录列表
        """
        with self._lock:
            metrics = self._metrics.get(experiment_id, [])
            
            if metric_name:
                metrics = [m for m in metrics if m.metric_name == metric_name]
            
            return metrics.copy()
    
    def get_aggregated_metric(self, experiment_id: str, metric_name: str,
                             aggregation: MetricAggregation = MetricAggregation.LAST) -> Optional[float]:
        """
        获取聚合指标
        
        Args:
            experiment_id: 实验ID
            metric_name: 指标名
            aggregation: 聚合方式
            
        Returns:
            聚合值
        """
        with self._lock:
            metrics = self._metrics.get(experiment_id, [])
            values = [m.value for m in metrics if m.metric_name == metric_name]
            
            if not values:
                return None
            
            if aggregation == MetricAggregation.LAST:
                return values[-1]
            elif aggregation == MetricAggregation.MIN:
                return min(values)
            elif aggregation == MetricAggregation.MAX:
                return max(values)
            elif aggregation == MetricAggregation.AVG:
                return sum(values) / len(values)
            elif aggregation == MetricAggregation.SUM:
                return sum(values)
            
            return None
    
    def log_artifact(self, experiment_id: str, name: str,
                    artifact_type: str,
                    path: Optional[str] = None,
                    data: Optional[bytes] = None) -> Optional[str]:
        """
        记录产物
        
        Args:
            experiment_id: 实验ID
            name: 产物名
            artifact_type: 产物类型
            path: 文件路径
            data: 数据内容
            
        Returns:
            产物ID
        """
        with self._lock:
            if experiment_id not in self._experiments:
                return None
            
            artifact_id = hashlib.md5(
                f"{experiment_id}_{name}_{time.time()}".encode()
            ).hexdigest()[:16]
            
            artifact = ArtifactRecord(
                artifact_id=artifact_id,
                experiment_id=experiment_id,
                name=name,
                artifact_type=artifact_type,
                path=path,
                data=data,
                size=len(data) if data else 0
            )
            
            self._artifacts[experiment_id].append(artifact)
            return artifact_id
    
    # ==================== 阶段259: 结果比较 ====================
    
    def compare_experiments(self, experiment_ids: List[str],
                           metrics: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        比较多个实验
        
        Args:
            experiment_ids: 实验ID列表
            metrics: 比较的指标列表
            
        Returns:
            比较结果
        """
        with self._lock:
            comparison = {
                "experiment_ids": experiment_ids,
                "experiments": {},
                "metrics": {},
                "rankings": {},
                "timestamp": time.time()
            }
            
            # 收集实验信息
            for exp_id in experiment_ids:
                exp = self._experiments.get(exp_id)
                if exp:
                    comparison["experiments"][exp_id] = {
                        "name": exp.name,
                        "status": exp.status.value,
                        "parameters": exp.parameters,
                        "duration": (exp.ended_at - exp.started_at) 
                                   if exp.ended_at and exp.started_at else None
                    }
            
            # 收集指标
            all_metrics = set()
            for exp_id in experiment_ids:
                for record in self._metrics.get(exp_id, []):
                    all_metrics.add(record.metric_name)
            
            if metrics:
                all_metrics = all_metrics & set(metrics)
            
            # 计算每个实验的指标值
            for metric in all_metrics:
                comparison["metrics"][metric] = {}
                for exp_id in experiment_ids:
                    value = self.get_aggregated_metric(exp_id, metric)
                    comparison["metrics"][metric][exp_id] = value
            
            # 计算排名
            for metric in all_metrics:
                values = [(exp_id, comparison["metrics"][metric][exp_id])
                         for exp_id in experiment_ids
                         if comparison["metrics"][metric][exp_id] is not None]
                
                # 假设越高越好
                values.sort(key=lambda x: x[1], reverse=True)
                
                comparison["rankings"][metric] = [
                    {"rank": i + 1, "experiment_id": exp_id, "value": value}
                    for i, (exp_id, value) in enumerate(values)
                ]
            
            # 缓存结果
            cache_key = hashlib.md5(
                json.dumps(experiment_ids, sort_keys=True).encode()
            ).hexdigest()
            self._comparison_cache[cache_key] = comparison
            
            return comparison
    
    def get_best_experiment(self, metric: str,
                           higher_is_better: bool = True,
                           tags: Optional[List[str]] = None) -> Optional[Tuple[str, float]]:
        """
        获取最佳实验
        
        Args:
            metric: 指标名
            higher_is_better: 是否越高越好
            tags: 标签过滤
            
        Returns:
            (实验ID, 指标值)
        """
        with self._lock:
            best_exp_id = None
            best_value = None
            
            for exp_id, exp in self._experiments.items():
                if tags and not any(t in exp.tags for t in tags):
                    continue
                
                value = self.get_aggregated_metric(exp_id, metric)
                if value is None:
                    continue
                
                if best_value is None:
                    best_exp_id = exp_id
                    best_value = value
                elif higher_is_better and value > best_value:
                    best_exp_id = exp_id
                    best_value = value
                elif not higher_is_better and value < best_value:
                    best_exp_id = exp_id
                    best_value = value
            
            if best_exp_id:
                return (best_exp_id, best_value)
            return None
    
    def find_similar_experiments(self, experiment_id: str,
                                threshold: float = 0.8) -> List[Tuple[str, float]]:
        """
        查找相似实验（基于参数相似度）
        
        Args:
            experiment_id: 实验ID
            threshold: 相似度阈值
            
        Returns:
            相似实验列表 [(实验ID, 相似度)]
        """
        with self._lock:
            target_exp = self._experiments.get(experiment_id)
            if not target_exp:
                return []
            
            target_params = target_exp.parameters
            similar = []
            
            for other_id, other_exp in self._experiments.items():
                if other_id == experiment_id:
                    continue
                
                other_params = other_exp.parameters
                
                # 计算Jaccard相似度
                all_keys = set(target_params.keys()) | set(other_params.keys())
                if not all_keys:
                    continue
                
                matches = sum(
                    1 for k in all_keys
                    if target_params.get(k) == other_params.get(k)
                )
                
                similarity = matches / len(all_keys)
                
                if similarity >= threshold:
                    similar.append((other_id, similarity))
            
            similar.sort(key=lambda x: x[1], reverse=True)
            return similar
    
    def get_experiment_summary(self, experiment_id: str) -> Dict[str, Any]:
        """
        获取实验摘要
        
        Args:
            experiment_id: 实验ID
            
        Returns:
            实验摘要
        """
        with self._lock:
            exp = self._experiments.get(experiment_id)
            if not exp:
                return {}
            
            # 收集所有指标的最后值
            metrics_summary = {}
            for record in self._metrics.get(experiment_id, []):
                metrics_summary[record.metric_name] = record.value
            
            return {
                "experiment_id": experiment_id,
                "name": exp.name,
                "status": exp.status.value,
                "parameters": exp.parameters,
                "tags": exp.tags,
                "metrics": metrics_summary,
                "duration": (exp.ended_at - exp.started_at) 
                           if exp.ended_at and exp.started_at else None,
                "artifact_count": len(self._artifacts.get(experiment_id, [])),
                "metric_count": len(self._metrics.get(experiment_id, []))
            }


# 全局单例
_experiment_tracker_instance: Optional[ExperimentTracker] = None
_experiment_tracker_lock = threading.Lock()


def get_experiment_tracker() -> ExperimentTracker:
    """获取实验追踪器全局单例"""
    global _experiment_tracker_instance
    
    if _experiment_tracker_instance is None:
        with _experiment_tracker_lock:
            if _experiment_tracker_instance is None:
                _experiment_tracker_instance = ExperimentTracker()
    
    return _experiment_tracker_instance
