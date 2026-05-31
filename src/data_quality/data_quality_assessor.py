#!/usr/bin/env python3
"""
数据质量评估器 (DataQualityAssessor) - 阶段354

职责：
- 完整性评估：字段完整度、记录完整度
- 一致性评估：数据一致性检查
- 准确性评估：数据准确性验证
- 及时性评估：数据时效性检查
- 综合质量评分：多维度质量打分

设计原则：
- 确定性规则，无模型依赖
- 线程安全（RLock）
- 最小层级，无循环依赖
"""

import threading
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union


# ============================================================
# 枚举与数据结构
# ============================================================

class QualityDimension(Enum):
    """质量维度"""
    COMPLETENESS = "completeness"   # 完整性
    CONSISTENCY = "consistency"     # 一致性
    ACCURACY = "accuracy"           # 准确性
    TIMELINESS = "timeliness"       # 及时性
    UNIQUENESS = "uniqueness"       # 唯一性
    VALIDITY = "validity"           # 有效性


class QualityLevel(Enum):
    """质量等级"""
    EXCELLENT = "excellent"   # 优秀 >= 95%
    GOOD = "good"             # 良好 >= 85%
    FAIR = "fair"             # 一般 >= 70%
    POOR = "poor"             # 较差 >= 50%
    CRITICAL = "critical"     # 严重 < 50%


@dataclass
class DimensionScore:
    """维度评分"""
    dimension: QualityDimension
    score: float           # 0-100
    issues: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def level(self) -> QualityLevel:
        if self.score >= 95:
            return QualityLevel.EXCELLENT
        if self.score >= 85:
            return QualityLevel.GOOD
        if self.score >= 70:
            return QualityLevel.FAIR
        if self.score >= 50:
            return QualityLevel.POOR
        return QualityLevel.CRITICAL

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dimension": self.dimension.value,
            "score": round(self.score, 2),
            "level": self.level.value,
            "issues": self.issues,
            "details": self.details,
        }


@dataclass
class QualityReport:
    """质量报告"""
    total_records: int = 0
    total_fields: int = 0
    dimension_scores: Dict[str, DimensionScore] = field(default_factory=dict)
    overall_score: float = 0.0
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = datetime.now().timestamp()

    @property
    def overall_level(self) -> QualityLevel:
        if self.overall_score >= 95:
            return QualityLevel.EXCELLENT
        if self.overall_score >= 85:
            return QualityLevel.GOOD
        if self.overall_score >= 70:
            return QualityLevel.FAIR
        if self.overall_score >= 50:
            return QualityLevel.POOR
        return QualityLevel.CRITICAL

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_records": self.total_records,
            "total_fields": self.total_fields,
            "overall_score": round(self.overall_score, 2),
            "overall_level": self.overall_level.value,
            "dimensions": {k: v.to_dict() for k, v in self.dimension_scores.items()},
            "timestamp": self.timestamp,
        }


# ============================================================
# 完整性评估器
# ============================================================

class CompletenessAssessor:
    """完整性评估器"""

    @staticmethod
    def assess_field_completeness(data: List[Dict[str, Any]],
                                  field: str) -> Tuple[float, int, int]:
        """
        评估字段完整性

        Returns:
            (完整率, 非空数量, 总数量)
        """
        if not data:
            return 100.0, 0, 0

        non_null = sum(1 for r in data
                       if field in r and r[field] is not None and r[field] != "")
        total = len(data)
        rate = (non_null / total) * 100 if total > 0 else 100.0

        return rate, non_null, total

    @staticmethod
    def assess_record_completeness(data: List[Dict[str, Any]],
                                   required_fields: List[str]) -> Tuple[float, int, int]:
        """
        评估记录完整性

        Returns:
            (完整率, 完整记录数, 总记录数)
        """
        if not data:
            return 100.0, 0, 0

        complete = 0
        for record in data:
            if all(f in record and record[f] is not None and record[f] != ""
                   for f in required_fields):
                complete += 1

        total = len(data)
        rate = (complete / total) * 100 if total > 0 else 100.0

        return rate, complete, total

    @staticmethod
    def assess_all_fields(data: List[Dict[str, Any]]) -> Dict[str, Tuple[float, int, int]]:
        """评估所有字段的完整性"""
        if not data:
            return {}

        all_fields = set()
        for record in data:
            all_fields.update(record.keys())

        result = {}
        for field in all_fields:
            result[field] = CompletenessAssessor.assess_field_completeness(data, field)

        return result


# ============================================================
# 一致性评估器
# ============================================================

class ConsistencyAssessor:
    """一致性评估器"""

    @staticmethod
    def assess_format_consistency(data: List[Dict[str, Any]],
                                  field: str,
                                  pattern: str) -> Tuple[float, int, int]:
        """
        评估格式一致性

        Args:
            pattern: 正则表达式模式

        Returns:
            (一致率, 匹配数, 总数)
        """
        import re

        if not data:
            return 100.0, 0, 0

        matched = 0
        total = 0

        for record in data:
            value = record.get(field)
            if value is not None and value != "":
                total += 1
                if isinstance(value, str) and re.match(pattern, value):
                    matched += 1

        rate = (matched / total) * 100 if total > 0 else 100.0
        return rate, matched, total

    @staticmethod
    def assess_type_consistency(data: List[Dict[str, Any]],
                                field: str) -> Tuple[float, Dict[str, int]]:
        """
        评估类型一致性

        Returns:
            (一致率, 类型分布)
        """
        if not data:
            return 100.0, {}

        type_counts = Counter()
        total = 0

        for record in data:
            value = record.get(field)
            if value is not None:
                type_name = type(value).__name__
                type_counts[type_name] += 1
                total += 1

        if total == 0:
            return 100.0, {}

        # 一致率 = 最常见类型占比
        most_common = type_counts.most_common(1)
        rate = (most_common[0][1] / total) * 100 if most_common else 100.0

        return rate, dict(type_counts)

    @staticmethod
    def assess_value_consistency(data: List[Dict[str, Any]],
                                 field: str,
                                 allowed_values: Set[Any]) -> Tuple[float, int, int]:
        """
        评估值一致性

        Returns:
            (一致率, 合法值数, 总数)
        """
        if not data:
            return 100.0, 0, 0

        valid = 0
        total = 0

        for record in data:
            value = record.get(field)
            if value is not None:
                total += 1
                if value in allowed_values:
                    valid += 1

        rate = (valid / total) * 100 if total > 0 else 100.0
        return rate, valid, total


# ============================================================
# 准确性评估器
# ============================================================

class AccuracyAssessor:
    """准确性评估器"""

    @staticmethod
    def assess_range_accuracy(data: List[Dict[str, Any]],
                              field: str,
                              min_val: float,
                              max_val: float) -> Tuple[float, int, int]:
        """
        评估范围准确性

        Returns:
            (准确率, 合法数, 总数)
        """
        if not data:
            return 100.0, 0, 0

        accurate = 0
        total = 0

        for record in data:
            value = record.get(field)
            if isinstance(value, (int, float)):
                total += 1
                if min_val <= value <= max_val:
                    accurate += 1

        rate = (accurate / total) * 100 if total > 0 else 100.0
        return rate, accurate, total

    @staticmethod
    def assess_reference_accuracy(data: List[Dict[str, Any]],
                                  field: str,
                                  reference: Dict[Any, Any],
                                  tolerance: float = 0.0) -> Tuple[float, int, int]:
        """
        评估参照准确性

        Args:
            reference: 参照值字典 {id: expected_value}
            tolerance: 容差（用于数值比较）

        Returns:
            (准确率, 匹配数, 总数)
        """
        if not data:
            return 100.0, 0, 0

        accurate = 0
        total = 0

        for record in data:
            key = record.get("id") or record.get("key")
            value = record.get(field)

            if key in reference:
                total += 1
                expected = reference[key]

                if isinstance(value, (int, float)) and isinstance(expected, (int, float)):
                    if abs(value - expected) <= tolerance:
                        accurate += 1
                elif value == expected:
                    accurate += 1

        rate = (accurate / total) * 100 if total > 0 else 100.0
        return rate, accurate, total

    @staticmethod
    def assess_custom_accuracy(data: List[Dict[str, Any]],
                               validator: Callable[[Dict[str, Any]], bool]) -> Tuple[float, int, int]:
        """
        评估自定义准确性

        Returns:
            (准确率, 通过数, 总数)
        """
        if not data:
            return 100.0, 0, 0

        accurate = sum(1 for r in data if validator(r))
        total = len(data)
        rate = (accurate / total) * 100 if total > 0 else 100.0

        return rate, accurate, total


# ============================================================
# 及时性评估器
# ============================================================

class TimelinessAssessor:
    """及时性评估器"""

    @staticmethod
    def assess_freshness(data: List[Dict[str, Any]],
                         timestamp_field: str,
                         max_age: timedelta) -> Tuple[float, int, int]:
        """
        评估数据新鲜度

        Returns:
            (及时率, 新鲜数, 总数)
        """
        if not data:
            return 100.0, 0, 0

        now = datetime.now()
        fresh = 0
        total = 0

        for record in data:
            ts = record.get(timestamp_field)
            if ts is not None:
                total += 1
                if isinstance(ts, str):
                    try:
                        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    except ValueError:
                        continue
                if isinstance(ts, datetime):
                    age = now - ts
                    if age <= max_age:
                        fresh += 1

        rate = (fresh / total) * 100 if total > 0 else 100.0
        return rate, fresh, total

    @staticmethod
    def assess_update_frequency(data: List[Dict[str, Any]],
                                timestamp_field: str,
                                expected_interval: timedelta) -> Tuple[float, List[float]]:
        """
        评估更新频率

        Returns:
            (符合率, 间隔列表)
        """
        if len(data) < 2:
            return 100.0, []

        timestamps = []
        for record in data:
            ts = record.get(timestamp_field)
            if ts is not None:
                if isinstance(ts, str):
                    try:
                        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    except ValueError:
                        continue
                if isinstance(ts, datetime):
                    timestamps.append(ts)

        if len(timestamps) < 2:
            return 100.0, []

        timestamps.sort()
        intervals = []
        compliant = 0

        for i in range(1, len(timestamps)):
            interval = timestamps[i] - timestamps[i-1]
            interval_seconds = interval.total_seconds()
            intervals.append(interval_seconds)
            if interval <= expected_interval:
                compliant += 1

        rate = (compliant / len(intervals)) * 100 if intervals else 100.0
        return rate, intervals


# ============================================================
# 唯一性评估器
# ============================================================

class UniquenessAssessor:
    """唯一性评估器"""

    @staticmethod
    def assess_field_uniqueness(data: List[Dict[str, Any]],
                                field: str) -> Tuple[float, int, int]:
        """
        评估字段唯一性

        Returns:
            (唯一率, 唯一值数, 总数)
        """
        if not data:
            return 100.0, 0, 0

        values = [r.get(field) for r in data if field in r]
        unique = len(set(values))
        total = len(values)

        rate = (unique / total) * 100 if total > 0 else 100.0
        return rate, unique, total

    @staticmethod
    def assess_composite_uniqueness(data: List[Dict[str, Any]],
                                    fields: List[str]) -> Tuple[float, int, int]:
        """
        评估组合字段唯一性

        Returns:
            (唯一率, 唯一组合数, 总数)
        """
        if not data:
            return 100.0, 0, 0

        combinations = set()
        total = 0

        for record in data:
            combo = tuple(record.get(f) for f in fields)
            combinations.add(combo)
            total += 1

        unique = len(combinations)
        rate = (unique / total) * 100 if total > 0 else 100.0

        return rate, unique, total


# ============================================================
# 数据质量评估器
# ============================================================

class DataQualityAssessor:
    """
    数据质量评估器

    核心功能：
    1. 完整性评估
    2. 一致性评估
    3. 准确性评估
    4. 及时性评估
    5. 综合质量报告
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._weights: Dict[QualityDimension, float] = {
            QualityDimension.COMPLETENESS: 0.25,
            QualityDimension.CONSISTENCY: 0.20,
            QualityDimension.ACCURACY: 0.25,
            QualityDimension.TIMELINESS: 0.15,
            QualityDimension.UNIQUENESS: 0.15,
        }

    # ---- 权重配置 ----

    def set_weights(self, weights: Dict[QualityDimension, float]) -> None:
        """设置维度权重"""
        with self._lock:
            total = sum(weights.values())
            if total > 0:
                self._weights = {k: v / total for k, v in weights.items()}

    def get_weights(self) -> Dict[QualityDimension, float]:
        """获取维度权重"""
        return self._weights.copy()

    # ---- 完整性评估 ----

    def assess_completeness(self, data: List[Dict[str, Any]],
                            required_fields: Optional[List[str]] = None) -> DimensionScore:
        """评估完整性"""
        if not data:
            return DimensionScore(
                dimension=QualityDimension.COMPLETENESS,
                score=100.0,
                issues=["No data to assess"],
            )

        issues = []
        details = {}

        # 字段完整性
        field_scores = CompletenessAssessor.assess_all_fields(data)
        field_avg = sum(s[0] for s in field_scores.values()) / len(field_scores) if field_scores else 100.0
        details["field_scores"] = {k: v[0] for k, v in field_scores.items()}

        # 记录完整性
        if required_fields:
            record_score, complete, total = CompletenessAssessor.assess_record_completeness(
                data, required_fields
            )
            details["record_completeness"] = record_score
            details["complete_records"] = complete
            details["total_records"] = total

            if record_score < 100:
                issues.append(f"{total - complete} records missing required fields")

            overall = (field_avg + record_score) / 2
        else:
            overall = field_avg

        # 识别问题字段
        for field, (score, _, _) in field_scores.items():
            if score < 80:
                issues.append(f"Field '{field}' completeness: {score:.1f}%")

        return DimensionScore(
            dimension=QualityDimension.COMPLETENESS,
            score=overall,
            issues=issues[:10],  # 限制问题数量
            details=details,
        )

    # ---- 一致性评估 ----

    def assess_consistency(self, data: List[Dict[str, Any]],
                           format_rules: Optional[Dict[str, str]] = None) -> DimensionScore:
        """评估一致性"""
        if not data:
            return DimensionScore(
                dimension=QualityDimension.CONSISTENCY,
                score=100.0,
            )

        issues = []
        details = {}
        scores = []

        # 类型一致性
        all_fields = set()
        for record in data:
            all_fields.update(record.keys())

        for field in all_fields:
            type_score, type_dist = ConsistencyAssessor.assess_type_consistency(data, field)
            scores.append(type_score)

            if type_score < 90 and len(type_dist) > 1:
                issues.append(f"Field '{field}' has mixed types: {type_dist}")

        # 格式一致性
        if format_rules:
            for field, pattern in format_rules.items():
                format_score, matched, total = ConsistencyAssessor.assess_format_consistency(
                    data, field, pattern
                )
                scores.append(format_score)
                details[f"{field}_format_score"] = format_score

                if format_score < 90:
                    issues.append(f"Field '{field}' format consistency: {format_score:.1f}%")

        overall = sum(scores) / len(scores) if scores else 100.0

        return DimensionScore(
            dimension=QualityDimension.CONSISTENCY,
            score=overall,
            issues=issues[:10],
            details=details,
        )

    # ---- 准确性评估 ----

    def assess_accuracy(self, data: List[Dict[str, Any]],
                        range_rules: Optional[Dict[str, Tuple[float, float]]] = None,
                        custom_validator: Optional[Callable[[Dict[str, Any]], bool]] = None) -> DimensionScore:
        """评估准确性"""
        if not data:
            return DimensionScore(
                dimension=QualityDimension.ACCURACY,
                score=100.0,
            )

        issues = []
        details = {}
        scores = []

        # 范围准确性
        if range_rules:
            for field, (min_val, max_val) in range_rules.items():
                score, accurate, total = AccuracyAssessor.assess_range_accuracy(
                    data, field, min_val, max_val
                )
                scores.append(score)
                details[f"{field}_range_score"] = score

                if score < 90:
                    issues.append(f"Field '{field}' out of range: {total - accurate} records")

        # 自定义准确性
        if custom_validator:
            custom_score, passed, total = AccuracyAssessor.assess_custom_accuracy(
                data, custom_validator
            )
            scores.append(custom_score)
            details["custom_score"] = custom_score

            if custom_score < 90:
                issues.append(f"Custom validation failed: {total - passed} records")

        overall = sum(scores) / len(scores) if scores else 100.0

        return DimensionScore(
            dimension=QualityDimension.ACCURACY,
            score=overall,
            issues=issues[:10],
            details=details,
        )

    # ---- 及时性评估 ----

    def assess_timeliness(self, data: List[Dict[str, Any]],
                          timestamp_field: str,
                          max_age: timedelta) -> DimensionScore:
        """评估及时性"""
        if not data:
            return DimensionScore(
                dimension=QualityDimension.TIMELINESS,
                score=100.0,
            )

        issues = []
        details = {}

        score, fresh, total = TimelinessAssessor.assess_freshness(
            data, timestamp_field, max_age
        )

        details["fresh_count"] = fresh
        details["total_count"] = total
        details["max_age_hours"] = max_age.total_seconds() / 3600

        if score < 90:
            issues.append(f"{total - fresh} records exceed max age")

        return DimensionScore(
            dimension=QualityDimension.TIMELINESS,
            score=score,
            issues=issues,
            details=details,
        )

    # ---- 唯一性评估 ----

    def assess_uniqueness(self, data: List[Dict[str, Any]],
                          unique_fields: Optional[List[str]] = None) -> DimensionScore:
        """评估唯一性"""
        if not data:
            return DimensionScore(
                dimension=QualityDimension.UNIQUENESS,
                score=100.0,
            )

        issues = []
        details = {}
        scores = []

        if unique_fields:
            for field in unique_fields:
                score, unique, total = UniquenessAssessor.assess_field_uniqueness(data, field)
                scores.append(score)
                details[f"{field}_unique_count"] = unique
                details[f"{field}_total_count"] = total

                if score < 100:
                    issues.append(f"Field '{field}' has {total - unique} duplicates")

        overall = sum(scores) / len(scores) if scores else 100.0

        return DimensionScore(
            dimension=QualityDimension.UNIQUENESS,
            score=overall,
            issues=issues[:10],
            details=details,
        )

    # ---- 综合评估 ----

    def assess(self, data: List[Dict[str, Any]],
               config: Optional[Dict[str, Any]] = None) -> QualityReport:
        """
        综合质量评估

        Args:
            data: 数据列表
            config: 评估配置

        Returns:
            QualityReport
        """
        config = config or {}
        report = QualityReport(total_records=len(data))

        if not data:
            report.overall_score = 100.0
            return report

        # 计算字段数
        all_fields = set()
        for record in data:
            all_fields.update(record.keys())
        report.total_fields = len(all_fields)

        # 完整性
        completeness = self.assess_completeness(
            data, config.get("required_fields")
        )
        report.dimension_scores["completeness"] = completeness

        # 一致性
        consistency = self.assess_consistency(
            data, config.get("format_rules")
        )
        report.dimension_scores["consistency"] = consistency

        # 准确性
        accuracy = self.assess_accuracy(
            data,
            config.get("range_rules"),
            config.get("custom_validator"),
        )
        report.dimension_scores["accuracy"] = accuracy

        # 及时性
        ts_field = config.get("timestamp_field")
        max_age = config.get("max_age", timedelta(days=30))
        if ts_field:
            timeliness = self.assess_timeliness(data, ts_field, max_age)
            report.dimension_scores["timeliness"] = timeliness

        # 唯一性
        unique_fields = config.get("unique_fields")
        if unique_fields:
            uniqueness = self.assess_uniqueness(data, unique_fields)
            report.dimension_scores["uniqueness"] = uniqueness

        # 计算综合分数
        total_weight = 0.0
        weighted_score = 0.0

        for dim_name, score in report.dimension_scores.items():
            dim = QualityDimension(dim_name)
            weight = self._weights.get(dim, 0.0)
            weighted_score += score.score * weight
            total_weight += weight

        report.overall_score = weighted_score / total_weight if total_weight > 0 else 100.0

        return report

    # ---- 统计 ----

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                "weights": {k.value: v for k, v in self._weights.items()},
            }


# ============================================================
# 全局单例
# ============================================================

_assessor: Optional[DataQualityAssessor] = None
_a_lock = threading.RLock()


def get_quality_assessor() -> DataQualityAssessor:
    """获取全局质量评估器"""
    global _assessor
    if _assessor is None:
        with _a_lock:
            if _assessor is None:
                _assessor = DataQualityAssessor()
    return _assessor
