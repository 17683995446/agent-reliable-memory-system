"""
模型管理器 (ModelManager)
阶段251-253: 模型注册、版本管理、模型评估

基于第一性原则设计:
1. 确定性: 模型版本基于哈希和版本号，无随机性
2. 可靠性: 模型评估指标确定性计算
3. 可追溯性: 完整的模型生命周期管理
"""

import threading
import time
import hashlib
from typing import Dict, List, Optional, Any, Callable, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict


class ModelStatus(Enum):
    """模型状态"""
    REGISTERED = "registered"      # 已注册
    TRAINING = "training"          # 训练中
    TRAINED = "trained"            # 已训练
    EVALUATING = "evaluating"      # 评估中
    DEPLOYED = "deployed"          # 已部署
    DEPRECATED = "deprecated"      # 已废弃
    ARCHIVED = "archived"          # 已归档


class ModelType(Enum):
    """模型类型"""
    CLASSIFIER = "classifier"      # 分类器
    REGRESSOR = "regressor"        # 回归器
    CLUSTERER = "clusterer"        # 聚类器
    EMBEDDER = "embedder"          # 嵌入器
    GENERATOR = "generator"        # 生成器


class MetricType(Enum):
    """评估指标类型"""
    ACCURACY = "accuracy"          # 准确率
    PRECISION = "precision"        # 精确率
    RECALL = "recall"              # 召回率
    F1 = "f1"                      # F1分数
    AUC = "auc"                    # AUC
    MSE = "mse"                    # 均方误差
    MAE = "mae"                    # 平均绝对误差
    R2 = "r2"                      # R²决定系数


@dataclass
class ModelMetadata:
    """模型元数据"""
    model_id: str
    name: str
    model_type: ModelType
    version: str
    status: ModelStatus = ModelStatus.REGISTERED
    description: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    created_by: str = "system"
    parent_version: Optional[str] = None
    framework: str = "custom"
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelVersion:
    """模型版本"""
    version_id: str
    model_id: str
    version_number: str
    model_path: Optional[str] = None
    model_data: Optional[bytes] = None
    checksum: str = ""
    created_at: float = field(default_factory=time.time)
    metrics: Dict[str, float] = field(default_factory=dict)
    hyperparameters: Dict[str, Any] = field(default_factory=dict)
    training_config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluationResult:
    """评估结果"""
    evaluation_id: str
    model_id: str
    version_id: str
    metrics: Dict[str, float]
    dataset_info: Dict[str, Any] = field(default_factory=dict)
    evaluation_time: float = 0.0
    created_at: float = field(default_factory=time.time)
    notes: str = ""


class ModelManager:
    """
    模型管理器
    
    核心功能:
    1. 模型注册: 模型元数据管理和生命周期跟踪
    2. 版本管理: 模型版本控制和历史回溯
    3. 模型评估: 标准化评估指标计算
    """
    
    def __init__(self):
        self._lock = threading.RLock()
        
        # 模型存储
        self._models: Dict[str, ModelMetadata] = {}
        self._versions: Dict[str, List[ModelVersion]] = defaultdict(list)
        self._active_versions: Dict[str, str] = {}  # model_id -> active_version_id
        
        # 评估结果
        self._evaluations: Dict[str, List[EvaluationResult]] = defaultdict(list)
        self._max_evaluations = 1000
        
        # 模型比较
        self._comparisons: List[Dict[str, Any]] = []
        
        # 回调
        self._status_change_callbacks: List[Callable[[str, ModelStatus, ModelStatus], None]] = []
    
    # ==================== 阶段251: 模型注册 ====================
    
    def register_model(self, name: str, model_type: ModelType,
                      description: str = "",
                      tags: Optional[List[str]] = None,
                      created_by: str = "system",
                      framework: str = "custom",
                      input_schema: Optional[Dict[str, Any]] = None,
                      output_schema: Optional[Dict[str, Any]] = None) -> str:
        """
        注册新模型
        
        Args:
            name: 模型名称
            model_type: 模型类型
            description: 描述
            tags: 标签
            created_by: 创建者
            framework: 框架
            input_schema: 输入模式
            output_schema: 输出模式
            
        Returns:
            模型ID
        """
        with self._lock:
            model_id = self._generate_model_id(name, model_type)
            
            model = ModelMetadata(
                model_id=model_id,
                name=name,
                model_type=model_type,
                version="0.0.0",
                status=ModelStatus.REGISTERED,
                description=description,
                tags=tags or [],
                created_by=created_by,
                framework=framework,
                input_schema=input_schema or {},
                output_schema=output_schema or {}
            )
            
            self._models[model_id] = model
            return model_id
    
    def _generate_model_id(self, name: str, model_type: ModelType) -> str:
        """生成模型ID"""
        timestamp = str(time.time())
        data = f"{name}_{model_type.value}_{timestamp}"
        return hashlib.md5(data.encode()).hexdigest()[:16]
    
    def get_model(self, model_id: str) -> Optional[ModelMetadata]:
        """
        获取模型元数据
        
        Args:
            model_id: 模型ID
            
        Returns:
            模型元数据
        """
        with self._lock:
            return self._models.get(model_id)
    
    def get_model_by_name(self, name: str) -> List[ModelMetadata]:
        """
        按名称获取模型
        
        Args:
            name: 模型名称
            
        Returns:
            模型列表
        """
        with self._lock:
            return [m for m in self._models.values() if m.name == name]
    
    def list_models(self, model_type: Optional[ModelType] = None,
                   status: Optional[ModelStatus] = None,
                   tags: Optional[List[str]] = None) -> List[ModelMetadata]:
        """
        列出模型
        
        Args:
            model_type: 类型过滤
            status: 状态过滤
            tags: 标签过滤
            
        Returns:
            模型列表
        """
        with self._lock:
            models = list(self._models.values())
            
            if model_type:
                models = [m for m in models if m.model_type == model_type]
            
            if status:
                models = [m for m in models if m.status == status]
            
            if tags:
                models = [m for m in models if any(t in m.tags for t in tags)]
            
            return models
    
    def update_model_status(self, model_id: str, new_status: ModelStatus) -> bool:
        """
        更新模型状态
        
        Args:
            model_id: 模型ID
            new_status: 新状态
            
        Returns:
            是否更新成功
        """
        with self._lock:
            if model_id not in self._models:
                return False
            
            model = self._models[model_id]
            old_status = model.status
            model.status = new_status
            model.updated_at = time.time()
            
            # 触发回调
            for callback in self._status_change_callbacks:
                try:
                    callback(model_id, old_status, new_status)
                except Exception:
                    pass
            
            return True
    
    def add_tags(self, model_id: str, tags: List[str]) -> bool:
        """
        添加标签
        
        Args:
            model_id: 模型ID
            tags: 标签列表
            
        Returns:
            是否添加成功
        """
        with self._lock:
            if model_id not in self._models:
                return False
            
            model = self._models[model_id]
            for tag in tags:
                if tag not in model.tags:
                    model.tags.append(tag)
            
            model.updated_at = time.time()
            return True
    
    def register_status_callback(self, 
                                 callback: Callable[[str, ModelStatus, ModelStatus], None]) -> None:
        """注册状态变更回调"""
        with self._lock:
            self._status_change_callbacks.append(callback)
    
    # ==================== 阶段252: 版本管理 ====================
    
    def create_version(self, model_id: str,
                      version_number: str,
                      model_path: Optional[str] = None,
                      model_data: Optional[bytes] = None,
                      hyperparameters: Optional[Dict[str, Any]] = None,
                      training_config: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        创建模型版本
        
        Args:
            model_id: 模型ID
            version_number: 版本号
            model_path: 模型路径
            model_data: 模型数据
            hyperparameters: 超参数
            training_config: 训练配置
            
        Returns:
            版本ID
        """
        with self._lock:
            if model_id not in self._models:
                return None
            
            # 计算校验和
            checksum = ""
            if model_data:
                checksum = hashlib.md5(model_data).hexdigest()
            
            version_id = self._generate_version_id(model_id, version_number)
            
            version = ModelVersion(
                version_id=version_id,
                model_id=model_id,
                version_number=version_number,
                model_path=model_path,
                model_data=model_data,
                checksum=checksum,
                hyperparameters=hyperparameters or {},
                training_config=training_config or {}
            )
            
            self._versions[model_id].append(version)
            
            # 更新模型版本号
            self._models[model_id].version = version_number
            self._models[model_id].updated_at = time.time()
            
            return version_id
    
    def _generate_version_id(self, model_id: str, version_number: str) -> str:
        """生成版本ID"""
        timestamp = str(time.time())
        data = f"{model_id}_{version_number}_{timestamp}"
        return hashlib.md5(data.encode()).hexdigest()[:16]
    
    def get_version(self, model_id: str, version_id: str) -> Optional[ModelVersion]:
        """
        获取模型版本
        
        Args:
            model_id: 模型ID
            version_id: 版本ID
            
        Returns:
            版本信息
        """
        with self._lock:
            versions = self._versions.get(model_id, [])
            for v in versions:
                if v.version_id == version_id:
                    return v
            return None
    
    def get_version_by_number(self, model_id: str, 
                              version_number: str) -> Optional[ModelVersion]:
        """
        按版本号获取版本
        
        Args:
            model_id: 模型ID
            version_number: 版本号
            
        Returns:
            版本信息
        """
        with self._lock:
            versions = self._versions.get(model_id, [])
            for v in versions:
                if v.version_number == version_number:
                    return v
            return None
    
    def list_versions(self, model_id: str) -> List[ModelVersion]:
        """
        列出模型所有版本
        
        Args:
            model_id: 模型ID
            
        Returns:
            版本列表
        """
        with self._lock:
            return self._versions.get(model_id, []).copy()
    
    def set_active_version(self, model_id: str, version_id: str) -> bool:
        """
        设置活跃版本
        
        Args:
            model_id: 模型ID
            version_id: 版本ID
            
        Returns:
            是否设置成功
        """
        with self._lock:
            version = self.get_version(model_id, version_id)
            if not version:
                return False
            
            self._active_versions[model_id] = version_id
            return True
    
    def get_active_version(self, model_id: str) -> Optional[ModelVersion]:
        """
        获取活跃版本
        
        Args:
            model_id: 模型ID
            
        Returns:
            活跃版本
        """
        with self._lock:
            version_id = self._active_versions.get(model_id)
            if version_id:
                return self.get_version(model_id, version_id)
            return None
    
    def compare_versions(self, model_id: str, version_id1: str,
                        version_id2: str) -> Optional[Dict[str, Any]]:
        """
        比较两个版本
        
        Args:
            model_id: 模型ID
            version_id1: 版本1 ID
            version_id2: 版本2 ID
            
        Returns:
            比较结果
        """
        with self._lock:
            v1 = self.get_version(model_id, version_id1)
            v2 = self.get_version(model_id, version_id2)
            
            if not v1 or not v2:
                return None
            
            # 比较指标
            metric_diff = {}
            all_metrics = set(v1.metrics.keys()) | set(v2.metrics.keys())
            for metric in all_metrics:
                val1 = v1.metrics.get(metric, 0)
                val2 = v2.metrics.get(metric, 0)
                metric_diff[metric] = {
                    "v1": val1,
                    "v2": val2,
                    "diff": val1 - val2,
                    "improved": val1 > val2 if metric in ["accuracy", "f1", "auc", "r2"] else val1 < val2
                }
            
            return {
                "version1": {
                    "id": v1.version_id,
                    "number": v1.version_number,
                    "metrics": v1.metrics
                },
                "version2": {
                    "id": v2.version_id,
                    "number": v2.version_number,
                    "metrics": v2.metrics
                },
                "metric_comparison": metric_diff
            }
    
    # ==================== 阶段253: 模型评估 ====================
    
    def evaluate_model(self, model_id: str, version_id: str,
                      metrics: Dict[str, float],
                      dataset_info: Optional[Dict[str, Any]] = None,
                      notes: str = "") -> Optional[str]:
        """
        评估模型
        
        Args:
            model_id: 模型ID
            version_id: 版本ID
            metrics: 评估指标
            dataset_info: 数据集信息
            notes: 备注
            
        Returns:
            评估ID
        """
        with self._lock:
            version = self.get_version(model_id, version_id)
            if not version:
                return None
            
            evaluation_id = self._generate_evaluation_id(model_id, version_id)
            
            evaluation = EvaluationResult(
                evaluation_id=evaluation_id,
                model_id=model_id,
                version_id=version_id,
                metrics=metrics,
                dataset_info=dataset_info or {},
                notes=notes
            )
            
            self._evaluations[model_id].append(evaluation)
            
            # 限制评估记录数量
            if len(self._evaluations[model_id]) > self._max_evaluations:
                self._evaluations[model_id] = self._evaluations[model_id][-self._max_evaluations:]
            
            # 更新版本的指标
            version.metrics.update(metrics)
            
            return evaluation_id
    
    def _generate_evaluation_id(self, model_id: str, version_id: str) -> str:
        """生成评估ID"""
        timestamp = str(time.time())
        data = f"{model_id}_{version_id}_{timestamp}"
        return hashlib.md5(data.encode()).hexdigest()[:16]
    
    def get_evaluation(self, model_id: str, 
                       evaluation_id: str) -> Optional[EvaluationResult]:
        """
        获取评估结果
        
        Args:
            model_id: 模型ID
            evaluation_id: 评估ID
            
        Returns:
            评估结果
        """
        with self._lock:
            evaluations = self._evaluations.get(model_id, [])
            for e in evaluations:
                if e.evaluation_id == evaluation_id:
                    return e
            return None
    
    def list_evaluations(self, model_id: str,
                        version_id: Optional[str] = None,
                        limit: int = 100) -> List[EvaluationResult]:
        """
        列出评估结果
        
        Args:
            model_id: 模型ID
            version_id: 版本ID过滤
            limit: 数量限制
            
        Returns:
            评估结果列表
        """
        with self._lock:
            evaluations = self._evaluations.get(model_id, [])
            
            if version_id:
                evaluations = [e for e in evaluations if e.version_id == version_id]
            
            return evaluations[-limit:]
    
    def get_best_version(self, model_id: str,
                        metric: str = "accuracy",
                        higher_is_better: bool = True) -> Optional[ModelVersion]:
        """
        获取最佳版本
        
        Args:
            model_id: 模型ID
            metric: 指标名称
            higher_is_better: 是否越高越好
            
        Returns:
            最佳版本
        """
        with self._lock:
            versions = self._versions.get(model_id, [])
            if not versions:
                return None
            
            best_version = None
            best_value = float('-inf') if higher_is_better else float('inf')
            
            for v in versions:
                if metric in v.metrics:
                    value = v.metrics[metric]
                    if higher_is_better:
                        if value > best_value:
                            best_value = value
                            best_version = v
                    else:
                        if value < best_value:
                            best_value = value
                            best_version = v
            
            return best_version
    
    def compare_models(self, model_ids: List[str],
                      metric: str = "accuracy") -> Dict[str, Any]:
        """
        比较多个模型
        
        Args:
            model_ids: 模型ID列表
            metric: 比较指标
            
        Returns:
            比较结果
        """
        with self._lock:
            results = {}
            
            for model_id in model_ids:
                model = self._models.get(model_id)
                if not model:
                    continue
                
                active_version = self.get_active_version(model_id)
                if active_version and metric in active_version.metrics:
                    results[model_id] = {
                        "name": model.name,
                        "version": active_version.version_number,
                        "metric_value": active_version.metrics[metric]
                    }
            
            # 排序
            sorted_results = sorted(
                results.items(),
                key=lambda x: x[1]["metric_value"],
                reverse=True
            )
            
            comparison = {
                "metric": metric,
                "rankings": [
                    {
                        "rank": i + 1,
                        "model_id": model_id,
                        **info
                    }
                    for i, (model_id, info) in enumerate(sorted_results)
                ],
                "timestamp": time.time()
            }
            
            self._comparisons.append(comparison)
            
            return comparison
    
    def get_model_statistics(self, model_id: str) -> Dict[str, Any]:
        """
        获取模型统计信息
        
        Args:
            model_id: 模型ID
            
        Returns:
            统计信息
        """
        with self._lock:
            model = self._models.get(model_id)
            if not model:
                return {}
            
            versions = self._versions.get(model_id, [])
            evaluations = self._evaluations.get(model_id, [])
            
            # 计算指标统计
            metric_stats = defaultdict(list)
            for e in evaluations:
                for metric, value in e.metrics.items():
                    metric_stats[metric].append(value)
            
            stats_summary = {}
            for metric, values in metric_stats.items():
                if values:
                    stats_summary[metric] = {
                        "min": min(values),
                        "max": max(values),
                        "avg": sum(values) / len(values),
                        "count": len(values)
                    }
            
            return {
                "model_id": model_id,
                "name": model.name,
                "status": model.status.value,
                "version_count": len(versions),
                "evaluation_count": len(evaluations),
                "metric_statistics": stats_summary
            }


# 全局单例
_model_manager_instance: Optional[ModelManager] = None
_model_manager_lock = threading.Lock()


def get_model_manager() -> ModelManager:
    """获取模型管理器全局单例"""
    global _model_manager_instance
    
    if _model_manager_instance is None:
        with _model_manager_lock:
            if _model_manager_instance is None:
                _model_manager_instance = ModelManager()
    
    return _model_manager_instance
