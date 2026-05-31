"""
智能优化器 (IntelligentOptimizer)
阶段263-265: 超参优化、自动调优、性能监控

基于第一性原则设计:
1. 确定性: 优化过程基于确定性搜索策略
2. 高效性: 贝叶斯优化和网格搜索
3. 可监控性: 完整的性能指标追踪
"""

import threading
import time
import hashlib
import math
from typing import Dict, List, Optional, Any, Callable, Tuple, Set, Union
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import heapq


class OptimizationStrategy(Enum):
    """优化策略"""
    GRID_SEARCH = "grid_search"      # 网格搜索
    RANDOM_SEARCH = "random_search"  # 随机搜索
    BAYESIAN = "bayesian"            # 贝叶斯优化
    GRADIENT = "gradient"            # 梯度下降
    EVOLUTIONARY = "evolutionary"    # 进化算法


class ParameterType(Enum):
    """参数类型"""
    INT = "int"                      # 整数
    FLOAT = "float"                  # 浮点数
    CATEGORICAL = "categorical"      # 类别
    BOOLEAN = "boolean"              # 布尔


class OptimizationStatus(Enum):
    """优化状态"""
    PENDING = "pending"              # 待开始
    RUNNING = "running"              # 运行中
    COMPLETED = "completed"          # 已完成
    FAILED = "failed"                # 失败
    CANCELLED = "cancelled"          # 已取消


@dataclass
class ParameterSpace:
    """参数空间"""
    name: str
    param_type: ParameterType
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    choices: Optional[List[Any]] = None
    step: Optional[float] = None


@dataclass
class OptimizationTrial:
    """优化试验"""
    trial_id: str
    optimization_id: str
    parameters: Dict[str, Any]
    metric_value: Optional[float] = None
    status: str = "pending"
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: str = ""


@dataclass
class OptimizationResult:
    """优化结果"""
    optimization_id: str
    best_parameters: Dict[str, Any]
    best_metric: float
    total_trials: int
    completed_trials: int
    status: OptimizationStatus
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None


@dataclass
class PerformanceMetric:
    """性能指标"""
    metric_name: str
    value: float
    timestamp: float = field(default_factory=time.time)
    tags: Dict[str, str] = field(default_factory=dict)


class IntelligentOptimizer:
    """
    智能优化器
    
    核心功能:
    1. 超参优化: 网格搜索、贝叶斯优化等策略
    2. 自动调优: 基于历史结果的智能调参
    3. 性能监控: 实时性能指标收集和分析
    """
    
    def __init__(self):
        self._lock = threading.RLock()
        
        # 优化任务
        self._optimizations: Dict[str, OptimizationResult] = {}
        self._trials: Dict[str, List[OptimizationTrial]] = defaultdict(list)
        self._parameter_spaces: Dict[str, List[ParameterSpace]] = {}
        
        # 性能监控
        self._metrics: Dict[str, List[PerformanceMetric]] = defaultdict(list)
        self._max_metrics = 10000
        self._metric_aggregations: Dict[str, Dict[str, float]] = defaultdict(dict)
        
        # 优化历史
        self._optimization_history: List[Dict[str, Any]] = []
        
        # 运行状态
        self._running_optimizations: Set[str] = set()
    
    # ==================== 阶段263: 超参优化 ====================
    
    def define_parameter_space(self, optimization_id: str,
                              spaces: List[ParameterSpace]) -> None:
        """
        定义参数空间
        
        Args:
            optimization_id: 优化任务ID
            spaces: 参数空间列表
        """
        with self._lock:
            self._parameter_spaces[optimization_id] = spaces
    
    def create_optimization(self, strategy: OptimizationStrategy,
                           parameter_spaces: List[ParameterSpace],
                           objective: Callable[[Dict[str, Any]], float],
                           maximize: bool = True,
                           max_trials: int = 100) -> str:
        """
        创建优化任务
        
        Args:
            strategy: 优化策略
            parameter_spaces: 参数空间
            objective: 目标函数
            maximize: 是否最大化
            max_trials: 最大试验次数
            
        Returns:
            优化任务ID
        """
        with self._lock:
            optimization_id = self._generate_optimization_id()
            
            self._parameter_spaces[optimization_id] = parameter_spaces
            
            result = OptimizationResult(
                optimization_id=optimization_id,
                best_parameters={},
                best_metric=float('-inf') if maximize else float('inf'),
                total_trials=max_trials,
                completed_trials=0,
                status=OptimizationStatus.PENDING
            )
            
            self._optimizations[optimization_id] = result
            
            return optimization_id
    
    def _generate_optimization_id(self) -> str:
        """生成优化任务ID"""
        timestamp = str(time.time())
        return hashlib.md5(timestamp.encode()).hexdigest()[:16]
    
    def run_optimization(self, optimization_id: str,
                        objective: Callable[[Dict[str, Any]], float],
                        strategy: OptimizationStrategy = OptimizationStrategy.GRID_SEARCH,
                        maximize: bool = True) -> Optional[OptimizationResult]:
        """
        运行优化
        
        Args:
            optimization_id: 优化任务ID
            objective: 目标函数
            strategy: 优化策略
            maximize: 是否最大化
            
        Returns:
            优化结果
        """
        with self._lock:
            if optimization_id not in self._optimizations:
                return None
            
            result = self._optimizations[optimization_id]
            result.status = OptimizationStatus.RUNNING
            self._running_optimizations.add(optimization_id)
        
        spaces = self._parameter_spaces.get(optimization_id, [])
        
        try:
            if strategy == OptimizationStrategy.GRID_SEARCH:
                self._run_grid_search(optimization_id, objective, spaces, maximize)
            elif strategy == OptimizationStrategy.RANDOM_SEARCH:
                self._run_random_search(optimization_id, objective, spaces, maximize)
            elif strategy == OptimizationStrategy.BAYESIAN:
                self._run_bayesian_optimization(optimization_id, objective, spaces, maximize)
            else:
                self._run_grid_search(optimization_id, objective, spaces, maximize)
            
            with self._lock:
                result = self._optimizations[optimization_id]
                result.status = OptimizationStatus.COMPLETED
                result.completed_at = time.time()
                self._running_optimizations.discard(optimization_id)
                
                # 记录历史
                self._optimization_history.append({
                    "optimization_id": optimization_id,
                    "strategy": strategy.value,
                    "best_parameters": result.best_parameters,
                    "best_metric": result.best_metric,
                    "trials": result.completed_trials,
                    "timestamp": time.time()
                })
                
                return result
        except Exception as e:
            with self._lock:
                result = self._optimizations[optimization_id]
                result.status = OptimizationStatus.FAILED
                self._running_optimizations.discard(optimization_id)
            return None
    
    def _run_grid_search(self, optimization_id: str,
                        objective: Callable[[Dict[str, Any]], float],
                        spaces: List[ParameterSpace],
                        maximize: bool) -> None:
        """网格搜索"""
        # 生成参数组合
        param_combinations = self._generate_grid_combinations(spaces)
        
        for params in param_combinations:
            trial_id = self._generate_trial_id(optimization_id)
            
            trial = OptimizationTrial(
                trial_id=trial_id,
                optimization_id=optimization_id,
                parameters=params,
                status="running",
                started_at=time.time()
            )
            
            try:
                metric_value = objective(params)
                trial.metric_value = metric_value
                trial.status = "completed"
                trial.completed_at = time.time()
                
                # 更新最佳结果
                with self._lock:
                    result = self._optimizations[optimization_id]
                    result.completed_trials += 1
                    
                    if maximize:
                        if metric_value > result.best_metric:
                            result.best_metric = metric_value
                            result.best_parameters = params.copy()
                    else:
                        if metric_value < result.best_metric:
                            result.best_metric = metric_value
                            result.best_parameters = params.copy()
                
            except Exception as e:
                trial.status = "failed"
                trial.error = str(e)
                trial.completed_at = time.time()
            
            with self._lock:
                self._trials[optimization_id].append(trial)
    
    def _generate_grid_combinations(self, spaces: List[ParameterSpace]) -> List[Dict[str, Any]]:
        """生成网格搜索参数组合"""
        if not spaces:
            return [{}]
        
        combinations = [{}]
        
        for space in spaces:
            new_combinations = []
            
            if space.param_type == ParameterType.INT:
                step = int(space.step or 1)
                values = list(range(int(space.min_val), int(space.max_val) + 1, step))
            elif space.param_type == ParameterType.FLOAT:
                step = space.step or (space.max_val - space.min_val) / 10
                num_steps = int((space.max_val - space.min_val) / step) + 1
                values = [space.min_val + i * step for i in range(num_steps)]
            elif space.param_type == ParameterType.CATEGORICAL:
                values = space.choices or []
            elif space.param_type == ParameterType.BOOLEAN:
                values = [True, False]
            else:
                values = []
            
            for combo in combinations:
                for value in values:
                    new_combo = combo.copy()
                    new_combo[space.name] = value
                    new_combinations.append(new_combo)
            
            combinations = new_combinations
        
        return combinations
    
    def _run_random_search(self, optimization_id: str,
                          objective: Callable[[Dict[str, Any]], float],
                          spaces: List[ParameterSpace],
                          maximize: bool,
                          n_trials: int = 50) -> None:
        """随机搜索"""
        for _ in range(n_trials):
            params = {}
            
            for space in spaces:
                if space.param_type == ParameterType.INT:
                    params[space.name] = int(
                        self._deterministic_random(
                            optimization_id, space.name, _
                        ) * (space.max_val - space.min_val) + space.min_val
                    )
                elif space.param_type == ParameterType.FLOAT:
                    params[space.name] = (
                        self._deterministic_random(
                            optimization_id, space.name, _
                        ) * (space.max_val - space.min_val) + space.min_val
                    )
                elif space.param_type == ParameterType.CATEGORICAL:
                    idx = int(
                        self._deterministic_random(
                            optimization_id, space.name, _
                        ) * len(space.choices or [])
                    )
                    params[space.name] = (space.choices or [])[idx]
                elif space.param_type == ParameterType.BOOLEAN:
                    params[space.name] = self._deterministic_random(
                        optimization_id, space.name, _
                    ) > 0.5
            
            # 执行试验
            self._execute_trial(optimization_id, params, objective, maximize)
    
    def _deterministic_random(self, *args) -> float:
        """确定性伪随机数生成"""
        data = "_".join(str(a) for a in args)
        hash_val = int(hashlib.md5(data.encode()).hexdigest(), 16)
        return (hash_val % 10000) / 10000.0
    
    def _run_bayesian_optimization(self, optimization_id: str,
                                   objective: Callable[[Dict[str, Any]], float],
                                   spaces: List[ParameterSpace],
                                   maximize: bool,
                                   n_trials: int = 50) -> None:
        """贝叶斯优化（简化实现）"""
        # 初始随机探索
        n_initial = min(10, n_trials // 2)
        
        for i in range(n_initial):
            params = self._sample_random_params(spaces, optimization_id, i)
            self._execute_trial(optimization_id, params, objective, maximize)
        
        # 基于模型的采样
        for i in range(n_initial, n_trials):
            # 简化：使用历史最佳点附近的采样
            with self._lock:
                result = self._optimizations[optimization_id]
                best_params = result.best_parameters.copy()
            
            # 在最佳点附近扰动
            params = {}
            for space in spaces:
                if space.name in best_params:
                    base_val = best_params[space.name]
                    if space.param_type == ParameterType.FLOAT:
                        noise = (self._deterministic_random(optimization_id, i, space.name) - 0.5) * 0.2
                        new_val = base_val + noise * (space.max_val - space.min_val)
                        new_val = max(space.min_val, min(space.max_val, new_val))
                        params[space.name] = new_val
                    else:
                        params[space.name] = base_val
                else:
                    params[space.name] = self._sample_random_params([space], optimization_id, i).get(space.name)
            
            self._execute_trial(optimization_id, params, objective, maximize)
    
    def _sample_random_params(self, spaces: List[ParameterSpace],
                             optimization_id: str,
                             seed: int) -> Dict[str, Any]:
        """随机采样参数"""
        params = {}
        for space in spaces:
            if space.param_type == ParameterType.FLOAT:
                r = self._deterministic_random(optimization_id, seed, space.name)
                params[space.name] = r * (space.max_val - space.min_val) + space.min_val
            elif space.param_type == ParameterType.INT:
                r = self._deterministic_random(optimization_id, seed, space.name)
                params[space.name] = int(r * (space.max_val - space.min_val) + space.min_val)
            elif space.param_type == ParameterType.CATEGORICAL:
                r = self._deterministic_random(optimization_id, seed, space.name)
                idx = int(r * len(space.choices or []))
                params[space.name] = (space.choices or [])[idx]
            elif space.param_type == ParameterType.BOOLEAN:
                params[space.name] = self._deterministic_random(optimization_id, seed, space.name) > 0.5
        return params
    
    def _execute_trial(self, optimization_id: str, params: Dict[str, Any],
                      objective: Callable[[Dict[str, Any]], float],
                      maximize: bool) -> None:
        """执行单次试验"""
        trial_id = self._generate_trial_id(optimization_id)
        
        trial = OptimizationTrial(
            trial_id=trial_id,
            optimization_id=optimization_id,
            parameters=params,
            status="running",
            started_at=time.time()
        )
        
        try:
            metric_value = objective(params)
            trial.metric_value = metric_value
            trial.status = "completed"
            trial.completed_at = time.time()
            
            with self._lock:
                result = self._optimizations[optimization_id]
                result.completed_trials += 1
                
                if maximize:
                    if metric_value > result.best_metric:
                        result.best_metric = metric_value
                        result.best_parameters = params.copy()
                else:
                    if metric_value < result.best_metric:
                        result.best_metric = metric_value
                        result.best_parameters = params.copy()
        except Exception as e:
            trial.status = "failed"
            trial.error = str(e)
            trial.completed_at = time.time()
        
        with self._lock:
            self._trials[optimization_id].append(trial)
    
    def _generate_trial_id(self, optimization_id: str) -> str:
        """生成试验ID"""
        timestamp = str(time.time())
        return hashlib.md5(f"{optimization_id}_{timestamp}".encode()).hexdigest()[:16]
    
    def get_optimization_result(self, optimization_id: str) -> Optional[OptimizationResult]:
        """
        获取优化结果
        
        Args:
            optimization_id: 优化任务ID
            
        Returns:
            优化结果
        """
        with self._lock:
            return self._optimizations.get(optimization_id)
    
    def get_trials(self, optimization_id: str) -> List[OptimizationTrial]:
        """
        获取试验记录
        
        Args:
            optimization_id: 优化任务ID
            
        Returns:
            试验记录列表
        """
        with self._lock:
            return self._trials.get(optimization_id, []).copy()
    
    # ==================== 阶段264: 自动调优 ====================
    
    def suggest_parameters(self, optimization_id: str,
                          n_suggestions: int = 5) -> List[Dict[str, Any]]:
        """
        基于历史结果建议参数
        
        Args:
            optimization_id: 优化任务ID
            n_suggestions: 建议数量
            
        Returns:
            建议参数列表
        """
        with self._lock:
            trials = self._trials.get(optimization_id, [])
            spaces = self._parameter_spaces.get(optimization_id, [])
            
            if not trials or not spaces:
                return []
            
            # 找到表现最好的试验
            sorted_trials = sorted(
                [t for t in trials if t.metric_value is not None],
                key=lambda x: x.metric_value,
                reverse=True
            )
            
            suggestions = []
            
            # 使用最佳参数作为基础
            if sorted_trials:
                best_params = sorted_trials[0].parameters.copy()
                suggestions.append(best_params)
                
                # 在最佳参数附近生成变体
                for i in range(n_suggestions - 1):
                    variant = {}
                    for space in spaces:
                        if space.name in best_params:
                            base_val = best_params[space.name]
                            if space.param_type == ParameterType.FLOAT:
                                noise = (self._deterministic_random(optimization_id, i, space.name) - 0.5) * 0.1
                                new_val = base_val + noise * (space.max_val - space.min_val)
                                new_val = max(space.min_val, min(space.max_val, new_val))
                                variant[space.name] = new_val
                            else:
                                variant[space.name] = base_val
                    suggestions.append(variant)
            
            return suggestions[:n_suggestions]
    
    def auto_tune(self, optimization_id: str,
                 objective: Callable[[Dict[str, Any]], float],
                 n_iterations: int = 10,
                 maximize: bool = True) -> Optional[OptimizationResult]:
        """
        自动调优
        
        Args:
            optimization_id: 优化任务ID
            objective: 目标函数
            n_iterations: 迭代次数
            maximize: 是否最大化
            
        Returns:
            优化结果
        """
        for iteration in range(n_iterations):
            suggestions = self.suggest_parameters(optimization_id, n_suggestions=1)
            
            if suggestions:
                params = suggestions[0]
            else:
                # 没有历史，随机采样
                spaces = self._parameter_spaces.get(optimization_id, [])
                params = self._sample_random_params(spaces, optimization_id, iteration)
            
            self._execute_trial(optimization_id, params, objective, maximize)
        
        return self.get_optimization_result(optimization_id)
    
    # ==================== 阶段265: 性能监控 ====================
    
    def record_metric(self, metric_name: str, value: float,
                     tags: Optional[Dict[str, str]] = None) -> None:
        """
        记录性能指标
        
        Args:
            metric_name: 指标名
            value: 指标值
            tags: 标签
        """
        with self._lock:
            metric = PerformanceMetric(
                metric_name=metric_name,
                value=value,
                tags=tags or {}
            )
            
            self._metrics[metric_name].append(metric)
            
            # 限制记录数量
            if len(self._metrics[metric_name]) > self._max_metrics:
                self._metrics[metric_name] = self._metrics[metric_name][-self._max_metrics:]
            
            # 更新聚合值
            self._update_aggregations(metric_name)
    
    def _update_aggregations(self, metric_name: str) -> None:
        """更新聚合值"""
        metrics = self._metrics.get(metric_name, [])
        if not metrics:
            return
        
        values = [m.value for m in metrics]
        
        self._metric_aggregations[metric_name] = {
            "count": len(values),
            "sum": sum(values),
            "avg": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
            "last": values[-1]
        }
    
    def get_metric_aggregations(self, metric_name: str) -> Dict[str, float]:
        """
        获取指标聚合值
        
        Args:
            metric_name: 指标名
            
        Returns:
            聚合值
        """
        with self._lock:
            return self._metric_aggregations.get(metric_name, {}).copy()
    
    def get_metric_history(self, metric_name: str,
                          limit: int = 100) -> List[PerformanceMetric]:
        """
        获取指标历史
        
        Args:
            metric_name: 指标名
            limit: 数量限制
            
        Returns:
            指标历史列表
        """
        with self._lock:
            metrics = self._metrics.get(metric_name, [])
            return metrics[-limit:]
    
    def get_all_metrics(self) -> Dict[str, Dict[str, float]]:
        """
        获取所有指标聚合值
        
        Returns:
            所有指标聚合值
        """
        with self._lock:
            return {name: agg.copy() for name, agg in self._metric_aggregations.items()}
    
    def detect_performance_anomaly(self, metric_name: str,
                                  threshold: float = 3.0) -> List[PerformanceMetric]:
        """
        检测性能异常（基于3-sigma规则）
        
        Args:
            metric_name: 指标名
            threshold: 阈值（标准差倍数）
            
        Returns:
            异常指标列表
        """
        with self._lock:
            agg = self._metric_aggregations.get(metric_name, {})
            metrics = self._metrics.get(metric_name, [])
            
            if not agg or "avg" not in agg:
                return []
            
            mean = agg["avg"]
            values = [m.value for m in metrics]
            
            if len(values) < 2:
                return []
            
            std = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))
            
            if std == 0:
                return []
            
            anomalies = []
            for metric in metrics:
                z_score = abs(metric.value - mean) / std
                if z_score > threshold:
                    anomalies.append(metric)
            
            return anomalies
    
    def get_optimization_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取优化历史
        
        Args:
            limit: 数量限制
            
        Returns:
            优化历史列表
        """
        with self._lock:
            return self._optimization_history[-limit:]


# 全局单例
_intelligent_optimizer_instance: Optional[IntelligentOptimizer] = None
_intelligent_optimizer_lock = threading.Lock()


def get_intelligent_optimizer() -> IntelligentOptimizer:
    """获取智能优化器全局单例"""
    global _intelligent_optimizer_instance
    
    if _intelligent_optimizer_instance is None:
        with _intelligent_optimizer_lock:
            if _intelligent_optimizer_instance is None:
                _intelligent_optimizer_instance = IntelligentOptimizer()
    
    return _intelligent_optimizer_instance
