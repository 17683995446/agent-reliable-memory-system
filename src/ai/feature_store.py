"""
特征存储 (FeatureStore)
阶段254-256: 特征存储、特征计算、特征选择

基于第一性原则设计:
1. 确定性: 特征计算基于确定性函数，无随机性
2. 高效性: 支持增量计算和缓存
3. 可扩展性: 插件式特征计算器
"""

import threading
import time
import hashlib
import math
from typing import Dict, List, Optional, Any, Callable, Tuple, Set, Union
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict


class FeatureType(Enum):
    """特征类型"""
    NUMERICAL = "numerical"      # 数值型
    CATEGORICAL = "categorical"  # 类别型
    BINARY = "binary"            # 二值型
    TEXT = "text"                # 文本型
    VECTOR = "vector"            # 向量型
    DATETIME = "datetime"        # 时间型


class TransformType(Enum):
    """转换类型"""
    NORMALIZE = "normalize"      # 归一化
    STANDARDIZE = "standardize"  # 标准化
    LOG = "log"                  # 对数转换
    BIN = "bin"                  # 分箱
    ONE_HOT = "one_hot"          # 独热编码
    EMBED = "embed"              # 嵌入


@dataclass
class FeatureDefinition:
    """特征定义"""
    feature_id: str
    name: str
    feature_type: FeatureType
    description: str = ""
    dependencies: List[str] = field(default_factory=list)
    transform: Optional[TransformType] = None
    transform_params: Dict[str, Any] = field(default_factory=dict)
    is_computed: bool = False
    created_at: float = field(default_factory=time.time)


@dataclass
class FeatureValue:
    """特征值"""
    feature_id: str
    entity_id: str
    value: Any
    timestamp: float = field(default_factory=time.time)
    version: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FeatureStatistics:
    """特征统计"""
    feature_id: str
    count: int = 0
    mean: float = 0.0
    std: float = 0.0
    min_val: float = 0.0
    max_val: float = 0.0
    null_count: int = 0
    unique_count: int = 0
    computed_at: float = field(default_factory=time.time)


class FeatureStore:
    """
    特征存储
    
    核心功能:
    1. 特征存储: 特征定义和值的存储管理
    2. 特征计算: 基于定义的自动特征计算
    3. 特征选择: 基于统计的特征重要性评估
    """
    
    def __init__(self):
        self._lock = threading.RLock()
        
        # 特征定义
        self._definitions: Dict[str, FeatureDefinition] = {}
        
        # 特征值存储
        self._values: Dict[str, Dict[str, FeatureValue]] = defaultdict(dict)  # feature_id -> entity_id -> value
        self._entity_features: Dict[str, Dict[str, FeatureValue]] = defaultdict(dict)  # entity_id -> feature_id -> value
        
        # 特征计算器
        self._computers: Dict[str, Callable[[Dict[str, Any]], Any]] = {}
        
        # 特征统计
        self._statistics: Dict[str, FeatureStatistics] = {}
        
        # 特征选择结果
        self._feature_importance: Dict[str, float] = {}
        self._selected_features: List[str] = []
    
    # ==================== 阶段254: 特征存储 ====================
    
    def define_feature(self, name: str, feature_type: FeatureType,
                      description: str = "",
                      dependencies: Optional[List[str]] = None,
                      transform: Optional[TransformType] = None,
                      transform_params: Optional[Dict[str, Any]] = None) -> str:
        """
        定义特征
        
        Args:
            name: 特征名称
            feature_type: 特征类型
            description: 描述
            dependencies: 依赖特征
            transform: 转换类型
            transform_params: 转换参数
            
        Returns:
            特征ID
        """
        with self._lock:
            feature_id = self._generate_feature_id(name)
            
            definition = FeatureDefinition(
                feature_id=feature_id,
                name=name,
                feature_type=feature_type,
                description=description,
                dependencies=dependencies or [],
                transform=transform,
                transform_params=transform_params or {}
            )
            
            self._definitions[feature_id] = definition
            return feature_id
    
    def _generate_feature_id(self, name: str) -> str:
        """生成特征ID"""
        timestamp = str(time.time())
        data = f"{name}_{timestamp}"
        return hashlib.md5(data.encode()).hexdigest()[:16]
    
    def get_definition(self, feature_id: str) -> Optional[FeatureDefinition]:
        """
        获取特征定义
        
        Args:
            feature_id: 特征ID
            
        Returns:
            特征定义
        """
        with self._lock:
            return self._definitions.get(feature_id)
    
    def get_definition_by_name(self, name: str) -> Optional[FeatureDefinition]:
        """
        按名称获取特征定义
        
        Args:
            name: 特征名称
            
        Returns:
            特征定义
        """
        with self._lock:
            for definition in self._definitions.values():
                if definition.name == name:
                    return definition
            return None
    
    def list_definitions(self, feature_type: Optional[FeatureType] = None) -> List[FeatureDefinition]:
        """
        列出特征定义
        
        Args:
            feature_type: 类型过滤
            
        Returns:
            特征定义列表
        """
        with self._lock:
            definitions = list(self._definitions.values())
            if feature_type:
                definitions = [d for d in definitions if d.feature_type == feature_type]
            return definitions
    
    def set_feature_value(self, feature_id: str, entity_id: str,
                         value: Any,
                         metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        设置特征值
        
        Args:
            feature_id: 特征ID
            entity_id: 实体ID
            value: 特征值
            metadata: 元数据
            
        Returns:
            是否设置成功
        """
        with self._lock:
            if feature_id not in self._definitions:
                return False
            
            feature_value = FeatureValue(
                feature_id=feature_id,
                entity_id=entity_id,
                value=value,
                metadata=metadata or {}
            )
            
            self._values[feature_id][entity_id] = feature_value
            self._entity_features[entity_id][feature_id] = feature_value
            
            # 使统计失效
            if feature_id in self._statistics:
                del self._statistics[feature_id]
            
            return True
    
    def get_feature_value(self, feature_id: str, entity_id: str) -> Optional[FeatureValue]:
        """
        获取特征值
        
        Args:
            feature_id: 特征ID
            entity_id: 实体ID
            
        Returns:
            特征值
        """
        with self._lock:
            return self._values.get(feature_id, {}).get(entity_id)
    
    def get_entity_features(self, entity_id: str,
                           feature_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        获取实体的所有特征
        
        Args:
            entity_id: 实体ID
            feature_ids: 特征ID列表，None表示全部
            
        Returns:
            特征字典 {feature_name: value}
        """
        with self._lock:
            entity_values = self._entity_features.get(entity_id, {})
            
            if feature_ids:
                result = {}
                for fid in feature_ids:
                    if fid in entity_values:
                        definition = self._definitions.get(fid)
                        if definition:
                            result[definition.name] = entity_values[fid].value
                return result
            
            result = {}
            for fid, fv in entity_values.items():
                definition = self._definitions.get(fid)
                if definition:
                    result[definition.name] = fv.value
            return result
    
    def batch_set_features(self, entity_id: str,
                          features: Dict[str, Any]) -> int:
        """
        批量设置特征
        
        Args:
            entity_id: 实体ID
            features: 特征字典 {feature_name: value}
            
        Returns:
            设置成功的特征数量
        """
        with self._lock:
            count = 0
            for name, value in features.items():
                definition = self.get_definition_by_name(name)
                if definition:
                    if self.set_feature_value(definition.feature_id, entity_id, value):
                        count += 1
            return count
    
    def delete_entity(self, entity_id: str) -> bool:
        """
        删除实体的所有特征
        
        Args:
            entity_id: 实体ID
            
        Returns:
            是否删除成功
        """
        with self._lock:
            if entity_id not in self._entity_features:
                return False
            
            # 从特征索引中删除
            for feature_id in self._entity_features[entity_id]:
                if entity_id in self._values[feature_id]:
                    del self._values[feature_id][entity_id]
            
            del self._entity_features[entity_id]
            return True
    
    # ==================== 阶段255: 特征计算 ====================
    
    def register_computer(self, feature_id: str,
                         computer: Callable[[Dict[str, Any]], Any]) -> None:
        """
        注册特征计算器
        
        Args:
            feature_id: 特征ID
            computer: 计算函数，输入依赖特征值，输出计算结果
        """
        with self._lock:
            self._computers[feature_id] = computer
            if feature_id in self._definitions:
                self._definitions[feature_id].is_computed = True
    
    def compute_feature(self, feature_id: str, entity_id: str) -> Optional[Any]:
        """
        计算特征值
        
        Args:
            feature_id: 特征ID
            entity_id: 实体ID
            
        Returns:
            计算结果
        """
        with self._lock:
            definition = self._definitions.get(feature_id)
            if not definition or not definition.is_computed:
                return None
            
            computer = self._computers.get(feature_id)
            if not computer:
                return None
            
            # 收集依赖特征值
            dep_values = {}
            for dep_id in definition.dependencies:
                dep_value = self.get_feature_value(dep_id, entity_id)
                if dep_value:
                    dep_def = self._definitions.get(dep_id)
                    if dep_def:
                        dep_values[dep_def.name] = dep_value.value
            
            try:
                result = computer(dep_values)
                
                # 应用转换
                if definition.transform:
                    result = self._apply_transform(result, definition)
                
                # 存储结果
                self.set_feature_value(feature_id, entity_id, result)
                return result
            except Exception:
                return None
    
    def _apply_transform(self, value: Any, 
                        definition: FeatureDefinition) -> Any:
        """应用特征转换"""
        if value is None:
            return None
        
        transform = definition.transform
        params = definition.transform_params
        
        if transform == TransformType.NORMALIZE:
            min_val = params.get("min", 0)
            max_val = params.get("max", 1)
            if max_val != min_val:
                return (value - min_val) / (max_val - min_val)
            return 0.0
        
        elif transform == TransformType.STANDARDIZE:
            mean = params.get("mean", 0)
            std = params.get("std", 1)
            if std > 0:
                return (value - mean) / std
            return 0.0
        
        elif transform == TransformType.LOG:
            if value > 0:
                return math.log(value + params.get("offset", 1))
            return 0.0
        
        elif transform == TransformType.BIN:
            bins = params.get("bins", [0, 0.5, 1.0])
            for i, threshold in enumerate(bins[:-1]):
                if value < threshold:
                    return i
            return len(bins) - 1
        
        return value
    
    def compute_all_features(self, entity_id: str) -> Dict[str, Any]:
        """
        计算实体的所有计算特征
        
        Args:
            entity_id: 实体ID
            
        Returns:
            计算结果
        """
        with self._lock:
            results = {}
            
            # 按依赖顺序计算
            computed = set()
            remaining = {fid for fid, d in self._definitions.items() if d.is_computed}
            
            max_iterations = len(remaining) * 2  # 防止无限循环
            iterations = 0
            
            while remaining and iterations < max_iterations:
                iterations += 1
                for feature_id in list(remaining):
                    definition = self._definitions[feature_id]
                    
                    # 检查依赖是否满足
                    if all(dep in computed or dep not in self._definitions 
                           for dep in definition.dependencies):
                        result = self.compute_feature(feature_id, entity_id)
                        if result is not None:
                            results[definition.name] = result
                        computed.add(feature_id)
                        remaining.discard(feature_id)
            
            return results
    
    # ==================== 阶段256: 特征选择 ====================
    
    def compute_statistics(self, feature_id: str) -> Optional[FeatureStatistics]:
        """
        计算特征统计
        
        Args:
            feature_id: 特征ID
            
        Returns:
            特征统计
        """
        with self._lock:
            if feature_id not in self._definitions:
                return None
            
            values = self._values.get(feature_id, {})
            if not values:
                return None
            
            numeric_values = []
            null_count = 0
            unique_values = set()
            
            for fv in values.values():
                if fv.value is None:
                    null_count += 1
                else:
                    try:
                        numeric_values.append(float(fv.value))
                        unique_values.add(fv.value)
                    except (ValueError, TypeError):
                        unique_values.add(str(fv.value))
            
            stats = FeatureStatistics(
                feature_id=feature_id,
                count=len(values),
                null_count=null_count,
                unique_count=len(unique_values)
            )
            
            if numeric_values:
                stats.mean = sum(numeric_values) / len(numeric_values)
                variance = sum((v - stats.mean) ** 2 for v in numeric_values) / len(numeric_values)
                stats.std = math.sqrt(variance)
                stats.min_val = min(numeric_values)
                stats.max_val = max(numeric_values)
            
            self._statistics[feature_id] = stats
            return stats
    
    def get_statistics(self, feature_id: str) -> Optional[FeatureStatistics]:
        """
        获取特征统计
        
        Args:
            feature_id: 特征ID
            
        Returns:
            特征统计
        """
        with self._lock:
            if feature_id in self._statistics:
                return self._statistics[feature_id]
            return self.compute_statistics(feature_id)
    
    def calculate_importance(self, target_feature_id: str,
                            method: str = "correlation") -> Dict[str, float]:
        """
        计算特征重要性
        
        Args:
            target_feature_id: 目标特征ID
            method: 计算方法 (correlation, variance, unique_ratio)
            
        Returns:
            特征重要性字典 {feature_id: importance}
        """
        with self._lock:
            importance = {}
            
            target_values = self._values.get(target_feature_id, {})
            if not target_values:
                return importance
            
            # 收集目标值
            target_numeric = {}
            for entity_id, fv in target_values.items():
                try:
                    target_numeric[entity_id] = float(fv.value)
                except (ValueError, TypeError):
                    pass
            
            if not target_numeric:
                return importance
            
            target_mean = sum(target_numeric.values()) / len(target_numeric)
            target_var = sum((v - target_mean) ** 2 for v in target_numeric.values()) / len(target_numeric)
            
            if target_var == 0:
                return importance
            
            # 计算每个特征的重要性
            for feature_id in self._definitions:
                if feature_id == target_feature_id:
                    continue
                
                feature_values = self._values.get(feature_id, {})
                if not feature_values:
                    continue
                
                if method == "correlation":
                    # 皮尔逊相关系数
                    pairs = []
                    for entity_id in target_numeric:
                        if entity_id in feature_values:
                            try:
                                pairs.append((target_numeric[entity_id], 
                                            float(feature_values[entity_id].value)))
                            except (ValueError, TypeError):
                                pass
                    
                    if len(pairs) > 1:
                        x_vals = [p[0] for p in pairs]
                        y_vals = [p[1] for p in pairs]
                        
                        x_mean = sum(x_vals) / len(x_vals)
                        y_mean = sum(y_vals) / len(y_vals)
                        
                        numerator = sum((x - x_mean) * (y - y_mean) for x, y in pairs)
                        x_std = math.sqrt(sum((x - x_mean) ** 2 for x in x_vals))
                        y_std = math.sqrt(sum((y - y_mean) ** 2 for y in y_vals))
                        
                        if x_std > 0 and y_std > 0:
                            importance[feature_id] = abs(numerator / (x_std * y_std))
                
                elif method == "variance":
                    stats = self.get_statistics(feature_id)
                    if stats and stats.std > 0:
                        importance[feature_id] = stats.std
                
                elif method == "unique_ratio":
                    stats = self.get_statistics(feature_id)
                    if stats and stats.count > 0:
                        importance[feature_id] = stats.unique_count / stats.count
            
            self._feature_importance = importance
            return importance
    
    def select_features(self, top_k: int = 10,
                       min_importance: float = 0.0) -> List[str]:
        """
        选择特征
        
        Args:
            top_k: 选择数量
            min_importance: 最小重要性阈值
            
        Returns:
            选择的特征ID列表
        """
        with self._lock:
            if not self._feature_importance:
                return []
            
            sorted_features = sorted(
                self._feature_importance.items(),
                key=lambda x: x[1],
                reverse=True
            )
            
            selected = []
            for feature_id, importance in sorted_features:
                if importance >= min_importance and len(selected) < top_k:
                    selected.append(feature_id)
            
            self._selected_features = selected
            return selected
    
    def get_feature_importance(self) -> Dict[str, float]:
        """获取特征重要性"""
        with self._lock:
            return self._feature_importance.copy()
    
    def get_selected_features(self) -> List[str]:
        """获取选择的特征"""
        with self._lock:
            return self._selected_features.copy()


# 全局单例
_feature_store_instance: Optional[FeatureStore] = None
_feature_store_lock = threading.Lock()


def get_feature_store() -> FeatureStore:
    """获取特征存储全局单例"""
    global _feature_store_instance
    
    if _feature_store_instance is None:
        with _feature_store_lock:
            if _feature_store_instance is None:
                _feature_store_instance = FeatureStore()
    
    return _feature_store_instance
