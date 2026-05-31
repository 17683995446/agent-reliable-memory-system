"""
预测分析器 - 阶段233-235

功能：
- 阶段233: 趋势预测
- 阶段234: 异常检测
- 阶段235: 模式识别

设计原则：
- 确定性规则，无模型依赖
- 最小层级，无循环依赖
- 线程安全，RLock保护
- 单例模式，全局唯一
"""

import threading
import time
import math
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Callable
from collections import deque, defaultdict
import uuid


@dataclass
class TimeSeriesPoint:
    """时间序列数据点"""
    timestamp: float
    value: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TrendPrediction:
    """趋势预测结果"""
    prediction_id: str
    metric_name: str
    current_value: float
    predicted_values: List[Tuple[float, float]]  # (timestamp, value)
    trend_direction: str  # up, down, stable
    confidence: float


@dataclass
class Anomaly:
    """异常检测结果"""
    anomaly_id: str
    metric_name: str
    timestamp: float
    value: float
    expected_range: Tuple[float, float]
    severity: str  # low, medium, high, critical
    score: float


@dataclass
class Pattern:
    """识别出的模式"""
    pattern_id: str
    pattern_type: str
    metric_name: str
    start_time: float
    end_time: float
    confidence: float
    description: str


class PredictiveAnalyzer:
    """
    预测分析器
    
    阶段233: 趋势预测
    - 时间序列分析
    - 线性回归预测
    - 趋势方向判断
    
    阶段234: 异常检测
    - 统计异常检测
    - 阈值异常检测
    - 异常评分
    
    阶段235: 模式识别
    - 周期性检测
    - 趋势模式识别
    - 变化点检测
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
            
            # 时间序列数据存储
            self._time_series: Dict[str, deque] = {}
            self._max_points = 10000
            
            # 异常检测配置
            self._anomaly_thresholds: Dict[str, Tuple[float, float]] = {}
            
            # 检测到的异常
            self._anomalies: deque = deque(maxlen=1000)
            
            # 识别出的模式
            self._patterns: deque = deque(maxlen=1000)
    
    # ========== 阶段233: 趋势预测 ==========
    
    def add_data_point(self, metric_name: str, value: float,
                      timestamp: Optional[float] = None,
                      metadata: Optional[Dict[str, Any]] = None) -> TimeSeriesPoint:
        """添加数据点"""
        point = TimeSeriesPoint(
            timestamp=timestamp or time.time(),
            value=value,
            metadata=metadata or {}
        )
        
        with self._lock:
            if metric_name not in self._time_series:
                self._time_series[metric_name] = deque(maxlen=self._max_points)
            
            self._time_series[metric_name].append(point)
        
        return point
    
    def predict_trend(self, metric_name: str,
                     horizon_points: int = 5) -> Optional[TrendPrediction]:
        """预测趋势"""
        with self._lock:
            series = self._time_series.get(metric_name)
            if not series or len(series) < 3:
                return None
            
            points = list(series)
        
        # 简单线性回归
        n = len(points)
        sum_x = sum(i for i in range(n))
        sum_y = sum(p.value for p in points)
        sum_xy = sum(i * p.value for i, p in enumerate(points))
        sum_x2 = sum(i * i for i in range(n))
        
        # 计算斜率和截距
        denominator = n * sum_x2 - sum_x * sum_x
        if denominator == 0:
            slope = 0
        else:
            slope = (n * sum_xy - sum_x * sum_y) / denominator
        
        intercept = (sum_y - slope * sum_x) / n
        
        # 预测未来值
        last_time = points[-1].timestamp
        time_interval = (points[-1].timestamp - points[0].timestamp) / (n - 1) if n > 1 else 3600
        
        predicted = []
        for i in range(1, horizon_points + 1):
            pred_x = n - 1 + i
            pred_value = slope * pred_x + intercept
            pred_time = last_time + time_interval * i
            predicted.append((pred_time, pred_value))
        
        # 判断趋势方向
        if slope > 0.01:
            direction = "up"
        elif slope < -0.01:
            direction = "down"
        else:
            direction = "stable"
        
        # 计算置信度（基于R²）
        y_mean = sum_y / n
        ss_tot = sum((p.value - y_mean) ** 2 for p in points)
        ss_res = sum((p.value - (slope * i + intercept)) ** 2 for i, p in enumerate(points))
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        confidence = max(0, min(1, r_squared))
        
        return TrendPrediction(
            prediction_id=str(uuid.uuid4()),
            metric_name=metric_name,
            current_value=points[-1].value,
            predicted_values=predicted,
            trend_direction=direction,
            confidence=confidence
        )
    
    def get_moving_average(self, metric_name: str,
                          window: int = 10) -> Optional[float]:
        """计算移动平均"""
        with self._lock:
            series = self._time_series.get(metric_name)
            if not series or len(series) < window:
                return None
            
            values = [p.value for p in list(series)[-window:]]
            return statistics.mean(values)
    
    # ========== 阶段234: 异常检测 ==========
    
    def set_anomaly_threshold(self, metric_name: str,
                             lower: float, upper: float) -> None:
        """设置异常阈值"""
        with self._lock:
            self._anomaly_thresholds[metric_name] = (lower, upper)
    
    def detect_anomalies(self, metric_name: str,
                        method: str = "statistical") -> List[Anomaly]:
        """检测异常"""
        with self._lock:
            series = self._time_series.get(metric_name)
            if not series or len(series) < 10:
                return []
            
            points = list(series)
        
        anomalies = []
        
        if method == "statistical":
            # 基于统计的异常检测
            values = [p.value for p in points[-100:]]  # 最近100个点
            mean = statistics.mean(values)
            std = statistics.stdev(values) if len(values) > 1 else 0
            
            for point in points[-10:]:  # 检查最近10个点
                z_score = abs(point.value - mean) / std if std > 0 else 0
                
                if z_score > 3:  # 3 sigma
                    severity = "critical" if z_score > 4 else "high" if z_score > 3.5 else "medium"
                    anomaly = Anomaly(
                        anomaly_id=str(uuid.uuid4()),
                        metric_name=metric_name,
                        timestamp=point.timestamp,
                        value=point.value,
                        expected_range=(mean - 2 * std, mean + 2 * std),
                        severity=severity,
                        score=z_score
                    )
                    anomalies.append(anomaly)
        
        elif method == "threshold":
            # 基于阈值的异常检测
            thresholds = self._anomaly_thresholds.get(metric_name)
            if thresholds:
                lower, upper = thresholds
                
                for point in points[-10:]:
                    if point.value < lower or point.value > upper:
                        severity = "high" if point.value < lower * 0.8 or point.value > upper * 1.2 else "medium"
                        anomaly = Anomaly(
                            anomaly_id=str(uuid.uuid4()),
                            metric_name=metric_name,
                            timestamp=point.timestamp,
                            value=point.value,
                            expected_range=thresholds,
                            severity=severity,
                            score=abs(point.value - (lower + upper) / 2) / ((upper - lower) / 2)
                        )
                        anomalies.append(anomaly)
        
        with self._lock:
            for anomaly in anomalies:
                self._anomalies.append(anomaly)
        
        return anomalies
    
    def get_recent_anomalies(self, metric_name: Optional[str] = None,
                            limit: int = 100) -> List[Anomaly]:
        """获取最近异常"""
        with self._lock:
            anomalies = list(self._anomalies)
        
        if metric_name:
            anomalies = [a for a in anomalies if a.metric_name == metric_name]
        
        return anomalies[-limit:]
    
    # ========== 阶段235: 模式识别 ==========
    
    def detect_patterns(self, metric_name: str) -> List[Pattern]:
        """检测模式"""
        with self._lock:
            series = self._time_series.get(metric_name)
            if not series or len(series) < 20:
                return []
            
            points = list(series)
        
        patterns = []
        
        # 检测周期性（简化实现）
        periodicity = self._detect_periodicity(points)
        if periodicity > 0:
            pattern = Pattern(
                pattern_id=str(uuid.uuid4()),
                pattern_type="periodic",
                metric_name=metric_name,
                start_time=points[0].timestamp,
                end_time=points[-1].timestamp,
                confidence=0.7,
                description=f"Detected periodicity with period {periodicity} points"
            )
            patterns.append(pattern)
        
        # 检测趋势变化点
        change_points = self._detect_change_points(points)
        for cp in change_points:
            pattern = Pattern(
                pattern_id=str(uuid.uuid4()),
                pattern_type="change_point",
                metric_name=metric_name,
                start_time=cp["timestamp"],
                end_time=cp["timestamp"],
                confidence=cp["confidence"],
                description=f"Trend change detected at value {cp['value']:.2f}"
            )
            patterns.append(pattern)
        
        with self._lock:
            for pattern in patterns:
                self._patterns.append(pattern)
        
        return patterns
    
    def _detect_periodicity(self, points: List[TimeSeriesPoint]) -> int:
        """检测周期性（简化版）"""
        if len(points) < 20:
            return 0
        
        values = [p.value for p in points]
        n = len(values)
        
        # 尝试不同的周期长度
        for period in range(5, min(n // 2, 100)):
            correlations = []
            for i in range(period, n):
                correlations.append(values[i] * values[i - period])
            
            avg_correlation = sum(correlations) / len(correlations) if correlations else 0
            
            if avg_correlation > 0.5:  # 简化阈值
                return period
        
        return 0
    
    def _detect_change_points(self, points: List[TimeSeriesPoint]) -> List[Dict]:
        """检测变化点"""
        change_points = []
        
        if len(points) < 10:
            return change_points
        
        # 使用滑动窗口检测均值变化
        window_size = 10
        
        for i in range(window_size, len(points) - window_size):
            before = [p.value for p in points[i - window_size:i]]
            after = [p.value for p in points[i:i + window_size]]
            
            mean_before = statistics.mean(before)
            mean_after = statistics.mean(after)
            
            std_before = statistics.stdev(before) if len(before) > 1 else 0
            
            if std_before > 0:
                change_magnitude = abs(mean_after - mean_before) / std_before
                
                if change_magnitude > 2:  # 2 sigma变化
                    change_points.append({
                        "timestamp": points[i].timestamp,
                        "value": points[i].value,
                        "confidence": min(1.0, change_magnitude / 4)
                    })
        
        return change_points[:5]  # 最多返回5个变化点
    
    def get_stats(self, metric_name: str) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            series = self._time_series.get(metric_name)
            if not series:
                return {}
            
            values = [p.value for p in series]
        
        if not values:
            return {}
        
        return {
            "count": len(values),
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "stdev": statistics.stdev(values) if len(values) > 1 else 0,
            "min": min(values),
            "max": max(values),
            "last_value": values[-1]
        }


# 全局单例
_predictive_analyzer_instance: Optional[PredictiveAnalyzer] = None
_predictive_analyzer_lock = threading.RLock()


def get_predictive_analyzer() -> PredictiveAnalyzer:
    """获取预测分析器全局实例"""
    global _predictive_analyzer_instance
    if _predictive_analyzer_instance is None:
        with _predictive_analyzer_lock:
            if _predictive_analyzer_instance is None:
                _predictive_analyzer_instance = PredictiveAnalyzer()
    return _predictive_analyzer_instance
