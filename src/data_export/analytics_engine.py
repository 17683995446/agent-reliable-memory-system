#!/usr/bin/env python3
"""
数据分析引擎 (AnalyticsEngine) - 阶段344

职责：
- 趋势分析：时间序列数据趋势检测
- 热点发现：高频访问记忆/数据识别
- 模式挖掘：访问模式、使用规律
- 统计聚合：多维统计计算
- 异常检测：数据异常点识别

设计原则：
- 确定性规则，无模型依赖
- 线程安全（RLock）
- 最小层级，无循环依赖
"""

import math
import threading
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


# ============================================================
# 枚举与数据结构
# ============================================================

class TrendDirection(Enum):
    """趋势方向"""
    UP = "up"
    DOWN = "down"
    STABLE = "stable"
    UNKNOWN = "unknown"


class AggregationType(Enum):
    """聚合类型"""
    COUNT = "count"
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"
    MEDIAN = "median"
    STDDEV = "stddev"
    PERCENTILE = "percentile"


@dataclass
class DataPoint:
    """数据点"""
    timestamp: float
    value: float
    key: str = ""
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class TrendResult:
    """趋势分析结果"""
    key: str
    direction: TrendDirection
    slope: float = 0.0
    change_percent: float = 0.0
    start_value: float = 0.0
    end_value: float = 0.0
    data_points: int = 0


@dataclass
class HotItem:
    """热点项"""
    key: str
    count: int
    score: float = 0.0
    rank: int = 0
    category: str = ""


@dataclass
class PatternResult:
    """模式分析结果"""
    name: str
    pattern_type: str
    confidence: float = 0.0
    description: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AnomalyResult:
    """异常检测结果"""
    timestamp: float
    key: str
    value: float
    expected_range: Tuple[float, float] = (0.0, 0.0)
    deviation_score: float = 0.0
    severity: str = "low"  # low, medium, high


@dataclass
class TimeBucket:
    """时间桶"""
    start: float
    end: float
    count: int = 0
    sum_value: float = 0.0
    values: List[float] = field(default_factory=list)


# ============================================================
# 统计计算器
# ============================================================

class StatsCalculator:
    """统计计算器"""

    @staticmethod
    def mean(values: List[float]) -> float:
        if not values:
            return 0.0
        return sum(values) / len(values)

    @staticmethod
    def median(values: List[float]) -> float:
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        if n % 2 == 0:
            return (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2
        return sorted_vals[n // 2]

    @staticmethod
    def stddev(values: List[float]) -> float:
        if len(values) < 2:
            return 0.0
        m = StatsCalculator.mean(values)
        variance = sum((v - m) ** 2 for v in values) / (len(values) - 1)
        return math.sqrt(variance)

    @staticmethod
    def percentile(values: List[float], p: float) -> float:
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        k = (len(sorted_vals) - 1) * p / 100.0
        f = int(k)
        c = f + 1 if f + 1 < len(sorted_vals) else f
        return sorted_vals[f] + (k - f) * (sorted_vals[c] - sorted_vals[f])

    @staticmethod
    def correlation(x: List[float], y: List[float]) -> float:
        """皮尔逊相关系数"""
        n = min(len(x), len(y))
        if n < 2:
            return 0.0
        x, y = x[:n], y[:n]
        mx, my = sum(x) / n, sum(y) / n
        sx = math.sqrt(sum((xi - mx) ** 2 for xi in x) / (n - 1))
        sy = math.sqrt(sum((yi - my) ** 2 for yi in y) / (n - 1))
        if sx == 0 or sy == 0:
            return 0.0
        cov = sum((x[i] - mx) * (y[i] - my) for i in range(n)) / (n - 1)
        return cov / (sx * sy)

    @staticmethod
    def linear_regression(values: List[float]) -> Tuple[float, float]:
        """线性回归，返回 (slope, intercept)"""
        n = len(values)
        if n < 2:
            return (0.0, 0.0)
        x = list(range(n))
        mx = sum(x) / n
        my = sum(values) / n
        ss_xx = sum((xi - mx) ** 2 for xi in x)
        ss_xy = sum((x[i] - mx) * (values[i] - my) for i in range(n))
        if ss_xx == 0:
            return (0.0, my)
        slope = ss_xy / ss_xx
        intercept = my - slope * mx
        return (slope, intercept)


# ============================================================
# 趋势分析器
# ============================================================

class TrendAnalyzer:
    """
    趋势分析器

    核心功能：
    1. 时间序列趋势检测（上升/下降/稳定）
    2. 变化率计算
    3. 线性回归拟合
    4. 多维度趋势对比
    """

    def __init__(self):
        self._series: Dict[str, List[DataPoint]] = defaultdict(list)
        self._lock = threading.RLock()

    def add_point(self, key: str, value: float,
                  timestamp: Optional[float] = None,
                  tags: Optional[Dict[str, str]] = None) -> None:
        """添加数据点"""
        point = DataPoint(
            timestamp=timestamp or time.time(),
            value=value,
            key=key,
            tags=tags or {},
        )
        with self._lock:
            self._series[key].append(point)

    def add_points(self, key: str, points: List[Tuple[float, float]]) -> None:
        """批量添加数据点 (timestamp, value)"""
        with self._lock:
            for ts, val in points:
                self._series[key].append(
                    DataPoint(timestamp=ts, value=val, key=key)
                )

    def analyze(self, key: str) -> TrendResult:
        """分析趋势"""
        with self._lock:
            points = sorted(self._series.get(key, []),
                            key=lambda p: p.timestamp)

        if len(points) < 2:
            return TrendResult(
                key=key,
                direction=TrendDirection.UNKNOWN,
                data_points=len(points),
            )

        values = [p.value for p in points]
        slope, _ = StatsCalculator.linear_regression(values)

        start_value = values[0]
        end_value = values[-1]

        # 变化率
        if start_value != 0:
            change_percent = ((end_value - start_value) / abs(start_value)) * 100
        elif end_value != 0:
            change_percent = 100.0
        else:
            change_percent = 0.0

        # 趋势方向
        threshold = abs(start_value) * 0.05 if start_value != 0 else 0.5
        if abs(end_value - start_value) < threshold:
            direction = TrendDirection.STABLE
        elif slope > 0:
            direction = TrendDirection.UP
        else:
            direction = TrendDirection.DOWN

        return TrendResult(
            key=key,
            direction=direction,
            slope=round(slope, 6),
            change_percent=round(change_percent, 2),
            start_value=start_value,
            end_value=end_value,
            data_points=len(points),
        )

    def get_series(self, key: str) -> List[Dict[str, Any]]:
        """获取时间序列"""
        with self._lock:
            points = self._series.get(key, [])
            return [
                {"timestamp": p.timestamp, "value": p.value, "key": p.key}
                for p in sorted(points, key=lambda p: p.timestamp)
            ]

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "series_count": len(self._series),
                "total_points": sum(len(v) for v in self._series.values()),
                "keys": list(self._series.keys()),
            }


# ============================================================
# 热点发现器
# ============================================================

class HotspotDetector:
    """
    热点发现器

    核心功能：
    1. 高频项识别
    2. 热度评分（频率 + 时效性）
    3. 分类热点
    4. 热点排名
    """

    def __init__(self, time_decay: float = 0.95):
        self._counts: Counter = Counter()
        self._last_access: Dict[str, float] = {}
        self._categories: Dict[str, str] = {}
        self._time_decay = time_decay
        self._lock = threading.RLock()
        self._total_accesses = 0

    def record_access(self, key: str, category: str = "",
                      timestamp: Optional[float] = None) -> None:
        """记录访问"""
        ts = timestamp or time.time()
        with self._lock:
            self._counts[key] += 1
            self._last_access[key] = ts
            if category:
                self._categories[key] = category
            self._total_accesses += 1

    def record_batch(self, keys: List[str],
                     category: str = "") -> None:
        """批量记录访问"""
        ts = time.time()
        with self._lock:
            for key in keys:
                self._counts[key] += 1
                self._last_access[key] = ts
                if category:
                    self._categories[key] = category
                self._total_accesses += 1

    def get_hotspots(self, limit: int = 20,
                     category: str = "") -> List[HotItem]:
        """获取热点列表"""
        with self._lock:
            now = time.time()
            items = []

            for key, count in self._counts.items():
                if category and self._categories.get(key) != category:
                    continue

                # 热度评分 = 频率 * 时效性权重
                last_ts = self._last_access.get(key, 0)
                age = now - last_ts
                time_factor = self._time_decay ** (age / 3600)  # 每小时衰减
                score = count * time_factor

                items.append(HotItem(
                    key=key,
                    count=count,
                    score=round(score, 2),
                    category=self._categories.get(key, ""),
                ))

            # 按评分排序
            items.sort(key=lambda x: x.score, reverse=True)
            for i, item in enumerate(items[:limit]):
                item.rank = i + 1

            return items[:limit]

    def get_top_keys(self, limit: int = 10) -> List[str]:
        """获取最热key列表"""
        with self._lock:
            return [k for k, _ in self._counts.most_common(limit)]

    def get_category_stats(self) -> Dict[str, int]:
        """获取分类统计"""
        with self._lock:
            stats = defaultdict(int)
            for key, cat in self._categories.items():
                stats[cat] += self._counts.get(key, 0)
            return dict(stats)

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "unique_keys": len(self._counts),
                "total_accesses": self._total_accesses,
                "categories": len(set(self._categories.values())),
                "time_decay": self._time_decay,
            }


# ============================================================
# 模式挖掘器
# ============================================================

class PatternMiner:
    """
    模式挖掘器

    核心功能：
    1. 频繁项集发现
    2. 序列模式挖掘
    3. 周期性检测
    4. 关联规则
    """

    def __init__(self):
        self._sequences: List[List[str]] = []
        self._access_log: List[Tuple[float, str]] = []  # (timestamp, key)
        self._lock = threading.RLock()

    def add_sequence(self, sequence: List[str]) -> None:
        """添加访问序列"""
        with self._lock:
            self._sequences.append(sequence)

    def add_access(self, key: str,
                   timestamp: Optional[float] = None) -> None:
        """添加单次访问"""
        with self._lock:
            self._access_log.append((timestamp or time.time(), key))

    def find_frequent_items(self, min_support: float = 0.1) -> List[Tuple[str, float]]:
        """发现频繁项"""
        with self._lock:
            all_items = []
            for seq in self._sequences:
                all_items.extend(seq)
            for _, key in self._access_log:
                all_items.append(key)

        if not all_items:
            return []

        total = len(all_items)
        counts = Counter(all_items)
        min_count = total * min_support

        return [
            (item, count / total)
            for item, count in counts.most_common()
            if count >= min_count
        ]

    def find_sequential_patterns(self, min_length: int = 2,
                                  min_support: int = 2) -> List[Tuple[tuple, int]]:
        """发现序列模式"""
        with self._lock:
            sequences = list(self._sequences)

        patterns = Counter()
        for seq in sequences:
            # 生成所有长度>=min_length的子序列
            for length in range(min_length, len(seq) + 1):
                for i in range(len(seq) - length + 1):
                    subseq = tuple(seq[i:i + length])
                    patterns[subseq] += 1

        return [
            (pattern, count)
            for pattern, count in patterns.most_common()
            if count >= min_support
        ]

    def detect_periodicity(self, key: str) -> Optional[Dict[str, Any]]:
        """检测访问周期性"""
        with self._lock:
            timestamps = [ts for ts, k in self._access_log if k == key]

        if len(timestamps) < 3:
            return None

        timestamps.sort()
        intervals = [timestamps[i + 1] - timestamps[i]
                     for i in range(len(timestamps) - 1)]

        if not intervals:
            return None

        avg_interval = sum(intervals) / len(intervals)
        std_interval = StatsCalculator.stddev(intervals)

        # 变异系数
        cv = std_interval / avg_interval if avg_interval > 0 else float('inf')

        is_periodic = cv < 0.3  # 变异系数小于30%认为有周期性

        return {
            "key": key,
            "is_periodic": is_periodic,
            "avg_interval": round(avg_interval, 2),
            "std_interval": round(std_interval, 2),
            "coefficient_of_variation": round(cv, 4),
            "occurrences": len(timestamps),
        }

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "sequences": len(self._sequences),
                "access_log_size": len(self._access_log),
                "unique_keys": len(set(k for _, k in self._access_log)),
            }


# ============================================================
# 异常检测器
# ============================================================

class AnomalyDetector:
    """
    异常检测器

    核心功能：
    1. 基于统计的异常检测（Z-score）
    2. 动态阈值
    3. 异常严重度评估
    """

    def __init__(self, z_threshold: float = 2.0,
                 window_size: int = 100):
        self._z_threshold = z_threshold
        self._window_size = window_size
        self._values: Dict[str, List[float]] = defaultdict(list)
        self._anomalies: List[AnomalyResult] = []
        self._lock = threading.RLock()

    def add_value(self, key: str, value: float,
                  timestamp: Optional[float] = None) -> Optional[AnomalyResult]:
        """添加值并检测异常"""
        ts = timestamp or time.time()

        with self._lock:
            values = self._values[key]
            values.append(value)

            # 保留窗口大小
            if len(values) > self._window_size:
                self._values[key] = values[-self._window_size:]
                values = self._values[key]

            if len(values) < 3:
                return None

            mean = StatsCalculator.mean(values[:-1])  # 用历史值计算
            std = StatsCalculator.stddev(values[:-1])

            if std == 0:
                return None

            z_score = abs(value - mean) / std

            if z_score > self._z_threshold:
                anomaly = AnomalyResult(
                    timestamp=ts,
                    key=key,
                    value=value,
                    expected_range=(round(mean - 2 * std, 4),
                                    round(mean + 2 * std, 4)),
                    deviation_score=round(z_score, 4),
                    severity="high" if z_score > 3 else
                             "medium" if z_score > 2.5 else "low",
                )
                self._anomalies.append(anomaly)
                return anomaly

            return None

    def get_anomalies(self, key: str = "",
                      limit: int = 50) -> List[Dict[str, Any]]:
        """获取异常列表"""
        with self._lock:
            items = self._anomalies
            if key:
                items = [a for a in items if a.key == key]
            return [
                {
                    "timestamp": a.timestamp,
                    "key": a.key,
                    "value": a.value,
                    "expected_range": a.expected_range,
                    "deviation": a.deviation_score,
                    "severity": a.severity,
                }
                for a in reversed(items[-limit:])
            ]

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            severity_counts = Counter(a.severity for a in self._anomalies)
            return {
                "tracked_keys": len(self._values),
                "total_anomalies": len(self._anomalies),
                "by_severity": dict(severity_counts),
                "z_threshold": self._z_threshold,
                "window_size": self._window_size,
            }


# ============================================================
# 数据分析引擎
# ============================================================

class AnalyticsEngine:
    """
    数据分析引擎

    核心功能：
    1. 趋势分析
    2. 热点发现
    3. 模式挖掘
    4. 异常检测
    5. 统计聚合
    """

    def __init__(self):
        self._trend = TrendAnalyzer()
        self._hotspot = HotspotDetector()
        self._pattern = PatternMiner()
        self._anomaly = AnomalyDetector()
        self._stats = StatsCalculator()
        self._lock = threading.RLock()
        self._total_analyzed = 0

    # ---- 趋势分析 ----

    def track_metric(self, key: str, value: float,
                     timestamp: Optional[float] = None) -> Optional[AnomalyResult]:
        """跟踪指标"""
        self._trend.add_point(key, value, timestamp)
        anomaly = self._anomaly.add_value(key, value, timestamp)
        with self._lock:
            self._total_analyzed += 1
        return anomaly

    def get_trend(self, key: str) -> Dict[str, Any]:
        """获取趋势分析结果"""
        result = self._trend.analyze(key)
        return {
            "key": result.key,
            "direction": result.direction.value,
            "slope": result.slope,
            "change_percent": result.change_percent,
            "start_value": result.start_value,
            "end_value": result.end_value,
            "data_points": result.data_points,
        }

    # ---- 热点发现 ----

    def record_access(self, key: str, category: str = "") -> None:
        """记录访问"""
        self._hotspot.record_access(key, category)
        self._pattern.add_access(key)

    def get_hotspots(self, limit: int = 20,
                     category: str = "") -> List[Dict[str, Any]]:
        """获取热点"""
        items = self._hotspot.get_hotspots(limit, category)
        return [
            {"key": i.key, "count": i.count, "score": i.score,
             "rank": i.rank, "category": i.category}
            for i in items
        ]

    # ---- 模式挖掘 ----

    def add_sequence(self, sequence: List[str]) -> None:
        """添加访问序列"""
        self._pattern.add_sequence(sequence)

    def find_frequent_items(self, min_support: float = 0.1) -> List[Dict[str, Any]]:
        """发现频繁项"""
        items = self._pattern.find_frequent_items(min_support)
        return [
            {"item": item, "support": round(support, 4)}
            for item, support in items
        ]

    def find_patterns(self, min_length: int = 2,
                       min_support: int = 2) -> List[Dict[str, Any]]:
        """发现序列模式"""
        patterns = self._pattern.find_sequential_patterns(min_length, min_support)
        return [
            {"pattern": list(p), "count": c}
            for p, c in patterns
        ]

    def detect_periodicity(self, key: str) -> Optional[Dict[str, Any]]:
        """检测周期性"""
        return self._pattern.detect_periodicity(key)

    # ---- 异常检测 ----

    def get_anomalies(self, key: str = "",
                      limit: int = 50) -> List[Dict[str, Any]]:
        """获取异常"""
        return self._anomaly.get_anomalies(key, limit)

    # ---- 统计聚合 ----

    def aggregate(self, key: str,
                  agg_type: AggregationType = AggregationType.AVG) -> float:
        """聚合计算"""
        series = self._trend.get_series(key)
        values = [p["value"] for p in series]
        if not values:
            return 0.0

        if agg_type == AggregationType.COUNT:
            return float(len(values))
        elif agg_type == AggregationType.SUM:
            return sum(values)
        elif agg_type == AggregationType.AVG:
            return self._stats.mean(values)
        elif agg_type == AggregationType.MIN:
            return min(values)
        elif agg_type == AggregationType.MAX:
            return max(values)
        elif agg_type == AggregationType.MEDIAN:
            return self._stats.median(values)
        elif agg_type == AggregationType.STDDEV:
            return self._stats.stddev(values)
        elif agg_type == AggregationType.PERCENTILE:
            return self._stats.percentile(values, 95)
        return 0.0

    # ---- 统计 ----

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "total_analyzed": self._total_analyzed,
                "trend": self._trend.get_stats(),
                "hotspot": self._hotspot.get_stats(),
                "pattern": self._pattern.get_stats(),
                "anomaly": self._anomaly.get_stats(),
            }


# ============================================================
# 全局单例
# ============================================================

_analytics: Optional[AnalyticsEngine] = None
_analytics_lock = threading.RLock()


def get_analytics_engine() -> AnalyticsEngine:
    """获取全局数据分析引擎"""
    global _analytics
    if _analytics is None:
        with _analytics_lock:
            if _analytics is None:
                _analytics = AnalyticsEngine()
    return _analytics
