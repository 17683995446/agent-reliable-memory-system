#!/usr/bin/env python3
"""
数据清洗器 (DataCleaner) - 阶段352

职责：
- 空值处理：去除/填充空值
- 标准化：字符串规范化、大小写统一
- 去重：记录去重、字段去重
- 异常值处理：离群值检测与处理
- 批量清洗：高效批量处理

设计原则：
- 确定性规则，无模型依赖
- 线程安全（RLock）
- 最小层级，无循环依赖
"""

import re
import threading
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union


# ============================================================
# 枚举与数据结构
# ============================================================

class NullAction(Enum):
    """空值处理策略"""
    REMOVE = "remove"       # 删除
    FILL_DEFAULT = "fill"   # 填充默认值
    FILL_MEAN = "mean"      # 填充均值
    FILL_MEDIAN = "median"  # 填充中位数
    FILL_MODE = "mode"      # 填充众数
    KEEP = "keep"           # 保留


class DedupStrategy(Enum):
    """去重策略"""
    EXACT = "exact"         # 精确匹配
    FUZZY = "fuzzy"         # 模糊匹配
    KEY_BASED = "key"       # 基于键


class CaseAction(Enum):
    """大小写处理"""
    UPPER = "upper"
    LOWER = "lower"
    TITLE = "title"
    CAPITALIZE = "capitalize"
    KEEP = "keep"


@dataclass
class CleaningStats:
    """清洗统计"""
    total_records: int = 0
    cleaned_records: int = 0
    removed_records: int = 0
    nulls_filled: int = 0
    nulls_removed: int = 0
    duplicates_removed: int = 0
    values_normalized: int = 0
    outliers_handled: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_records": self.total_records,
            "cleaned_records": self.cleaned_records,
            "removed_records": self.removed_records,
            "nulls_filled": self.nulls_filled,
            "nulls_removed": self.nulls_removed,
            "duplicates_removed": self.duplicates_removed,
            "values_normalized": self.values_normalized,
            "outliers_handled": self.outliers_handled,
        }


@dataclass
class CleaningResult:
    """清洗结果"""
    data: Any
    stats: CleaningStats
    changes: List[Tuple[str, Any, Any]] = field(default_factory=list)  # (field, old, new)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "data": self.data,
            "stats": self.stats.to_dict(),
            "changes_count": len(self.changes),
        }


# ============================================================
# 空值处理器
# ============================================================

class NullHandler:
    """空值处理器"""

    NULL_VALUES = {None, "", "null", "NULL", "None", "none", "NaN", "nan", "NA", "na", "N/A", "n/a"}

    @classmethod
    def is_null(cls, value: Any) -> bool:
        """判断是否为空值"""
        if value is None:
            return True
        if isinstance(value, str) and value.strip() == "":
            return True
        if value in cls.NULL_VALUES:
            return True
        try:
            import math
            if isinstance(value, float) and math.isnan(value):
                return True
        except (TypeError, ValueError):
            pass
        return False

    @classmethod
    def fill_value(cls, values: List[Any], action: NullAction,
                   default: Any = None) -> Any:
        """计算填充值"""
        if action == NullAction.FILL_DEFAULT:
            return default

        numeric_values = [v for v in values if isinstance(v, (int, float)) and not cls.is_null(v)]

        if not numeric_values:
            return default

        if action == NullAction.FILL_MEAN:
            return sum(numeric_values) / len(numeric_values)

        if action == NullAction.FILL_MEDIAN:
            sorted_vals = sorted(numeric_values)
            n = len(sorted_vals)
            if n % 2 == 0:
                return (sorted_vals[n//2-1] + sorted_vals[n//2]) / 2
            return sorted_vals[n//2]

        if action == NullAction.FILL_MODE:
            counter = Counter(numeric_values)
            return counter.most_common(1)[0][0]

        return default


# ============================================================
# 字符串标准化器
# ============================================================

class StringNormalizer:
    """字符串标准化器"""

    @staticmethod
    def normalize(text: str) -> str:
        """基础标准化：去除首尾空白、规范化Unicode"""
        if not isinstance(text, str):
            return text
        # Unicode规范化（NFKC：兼容性分解后组合）
        text = unicodedata.normalize("NFKC", text)
        # 去除首尾空白
        text = text.strip()
        return text

    @staticmethod
    def case_convert(text: str, action: CaseAction) -> str:
        """大小写转换"""
        if not isinstance(text, str):
            return text
        if action == CaseAction.UPPER:
            return text.upper()
        if action == CaseAction.LOWER:
            return text.lower()
        if action == CaseAction.TITLE:
            return text.title()
        if action == CaseAction.CAPITALIZE:
            return text.capitalize()
        return text

    @staticmethod
    def remove_extra_whitespace(text: str) -> str:
        """移除多余空白字符"""
        if not isinstance(text, str):
            return text
        return re.sub(r"\s+", " ", text)

    @staticmethod
    def remove_special_chars(text: str, keep: str = "") -> str:
        """移除特殊字符"""
        if not isinstance(text, str):
            return text
        pattern = f"[^a-zA-Z0-9\u4e00-\u9fff{re.escape(keep)}]"
        return re.sub(pattern, "", text)

    @staticmethod
    def trim_punctuation(text: str) -> str:
        """去除首尾标点"""
        if not isinstance(text, str):
            return text
        return text.strip(".,!?;:\"'()[]{}<>-_")


# ============================================================
# 去重处理器
# ============================================================

class Deduplicator:
    """去重处理器"""

    @staticmethod
    def dedup_exact(records: List[Any]) -> Tuple[List[Any], int]:
        """精确去重"""
        seen = set()
        result = []
        for record in records:
            key = str(record) if not isinstance(record, (str, int, float, bool)) else record
            if key not in seen:
                seen.add(key)
                result.append(record)
        return result, len(records) - len(result)

    @staticmethod
    def dedup_by_key(records: List[Dict[str, Any]],
                     keys: List[str]) -> Tuple[List[Dict[str, Any]], int]:
        """基于键去重"""
        seen = set()
        result = []
        for record in records:
            if not isinstance(record, dict):
                result.append(record)
                continue
            key_values = tuple(record.get(k) for k in keys)
            if key_values not in seen:
                seen.add(key_values)
                result.append(record)
        return result, len(records) - len(result)

    @staticmethod
    def dedup_list(values: List[Any], preserve_order: bool = True) -> Tuple[List[Any], int]:
        """列表去重"""
        if preserve_order:
            seen = set()
            result = []
            for v in values:
                if v not in seen:
                    seen.add(v)
                    result.append(v)
            return result, len(values) - len(result)
        else:
            result = list(set(values))
            return result, len(values) - len(result)


# ============================================================
# 异常值检测器
# ============================================================

class OutlierDetector:
    """异常值检测器"""

    @staticmethod
    def detect_iqr(values: List[float],
                   factor: float = 1.5) -> Tuple[List[int], float, float]:
        """IQR方法检测异常值，返回(异常索引列表, 下界, 上界)"""
        if not values:
            return [], 0, 0

        sorted_vals = sorted(values)
        n = len(sorted_vals)

        q1_idx = n // 4
        q3_idx = n * 3 // 4
        q1 = sorted_vals[q1_idx]
        q3 = sorted_vals[q3_idx]
        iqr = q3 - q1

        lower = q1 - factor * iqr
        upper = q3 + factor * iqr

        outliers = [i for i, v in enumerate(values) if v < lower or v > upper]
        return outliers, lower, upper

    @staticmethod
    def detect_zscore(values: List[float],
                      threshold: float = 3.0) -> List[int]:
        """Z-score方法检测异常值"""
        if len(values) < 2:
            return []

        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std = variance ** 0.5

        if std == 0:
            return []

        outliers = [i for i, v in enumerate(values)
                    if abs((v - mean) / std) > threshold]
        return outliers


# ============================================================
# 数据清洗器
# ============================================================

class DataCleaner:
    """
    数据清洗器

    核心功能：
    1. 空值处理
    2. 字符串标准化
    3. 去重
    4. 异常值处理
    5. 批量清洗
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._custom_cleaners: Dict[str, Callable[[Any], Any]] = {}

    # ---- 自定义清洗器 ----

    def register_cleaner(self, name: str, func: Callable[[Any], Any]) -> None:
        """注册自定义清洗函数"""
        with self._lock:
            self._custom_cleaners[name] = func

    def apply_cleaner(self, value: Any, name: str) -> Any:
        """应用自定义清洗函数"""
        cleaner = self._custom_cleaners.get(name)
        if cleaner:
            return cleaner(value)
        return value

    # ---- 空值处理 ----

    def clean_nulls(self, data: List[Dict[str, Any]],
                    field: str,
                    action: NullAction = NullAction.REMOVE,
                    default: Any = None) -> CleaningResult:
        """清洗空值"""
        stats = CleaningStats(total_records=len(data))
        changes = []
        result = []

        # 获取所有非空值用于计算填充值
        all_values = [r.get(field) for r in data]
        fill_val = NullHandler.fill_value(all_values, action, default)

        for record in data:
            value = record.get(field)
            if NullHandler.is_null(value):
                if action == NullAction.REMOVE:
                    stats.removed_records += 1
                    stats.nulls_removed += 1
                    continue
                elif action in (NullAction.FILL_DEFAULT, NullAction.FILL_MEAN,
                               NullAction.FILL_MEDIAN, NullAction.FILL_MODE):
                    new_record = record.copy()
                    new_record[field] = fill_val
                    result.append(new_record)
                    stats.nulls_filled += 1
                    changes.append((field, value, fill_val))
                else:
                    result.append(record)
            else:
                result.append(record)

        stats.cleaned_records = len(result)
        return CleaningResult(data=result, stats=stats, changes=changes)

    # ---- 字符串标准化 ----

    def normalize_string(self, data: List[Dict[str, Any]],
                         field: str,
                         case: CaseAction = CaseAction.KEEP,
                         trim: bool = True,
                         remove_extra_space: bool = True,
                         remove_special: bool = False) -> CleaningResult:
        """标准化字符串字段"""
        stats = CleaningStats(total_records=len(data))
        changes = []
        result = []

        for record in data:
            new_record = record.copy()
            value = record.get(field)

            if isinstance(value, str):
                original = value

                if trim:
                    value = StringNormalizer.normalize(value)

                if case != CaseAction.KEEP:
                    value = StringNormalizer.case_convert(value, case)

                if remove_extra_space:
                    value = StringNormalizer.remove_extra_whitespace(value)

                if remove_special:
                    value = StringNormalizer.remove_special_chars(value)

                if value != original:
                    new_record[field] = value
                    stats.values_normalized += 1
                    changes.append((field, original, value))

            result.append(new_record)

        stats.cleaned_records = len(result)
        return CleaningResult(data=result, stats=stats, changes=changes)

    # ---- 去重 ----

    def deduplicate(self, data: List[Dict[str, Any]],
                    strategy: DedupStrategy = DedupStrategy.KEY_BASED,
                    keys: Optional[List[str]] = None) -> CleaningResult:
        """去重"""
        stats = CleaningStats(total_records=len(data))

        if strategy == DedupStrategy.EXACT:
            result, removed = Deduplicator.dedup_exact(data)
        elif strategy == DedupStrategy.KEY_BASED and keys:
            result, removed = Deduplicator.dedup_by_key(data, keys)
        else:
            result = data
            removed = 0

        stats.duplicates_removed = removed
        stats.cleaned_records = len(result)
        stats.removed_records = removed

        return CleaningResult(data=result, stats=stats)

    def deduplicate_field(self, values: List[Any],
                          preserve_order: bool = True) -> CleaningResult:
        """字段值去重"""
        stats = CleaningStats(total_records=len(values))
        result, removed = Deduplicator.dedup_list(values, preserve_order)
        stats.duplicates_removed = removed
        stats.cleaned_records = len(result)
        return CleaningResult(data=result, stats=stats)

    # ---- 异常值处理 ----

    def handle_outliers(self, data: List[Dict[str, Any]],
                        field: str,
                        method: str = "iqr",
                        action: str = "remove",
                        factor: float = 1.5,
                        replacement: Optional[float] = None) -> CleaningResult:
        """处理异常值"""
        stats = CleaningStats(total_records=len(data))
        changes = []
        result = []

        values = [r.get(field) for r in data if isinstance(r.get(field), (int, float))]

        if method == "iqr":
            outliers, lower, upper = OutlierDetector.detect_iqr(values, factor)
        else:
            outliers = OutlierDetector.detect_zscore(values)
            lower, upper = None, None

        outlier_set = set(outliers)

        valid_idx = 0
        for i, record in enumerate(data):
            value = record.get(field)
            if isinstance(value, (int, float)) and valid_idx in outlier_set:
                stats.outliers_handled += 1
                if action == "remove":
                    stats.removed_records += 1
                    valid_idx += 1
                    continue
                elif action == "replace" and replacement is not None:
                    new_record = record.copy()
                    new_record[field] = replacement
                    result.append(new_record)
                    changes.append((field, value, replacement))
                elif action == "clip":
                    new_record = record.copy()
                    clipped = max(lower, min(upper, value)) if lower is not None else value
                    new_record[field] = clipped
                    result.append(new_record)
                    changes.append((field, value, clipped))
                else:
                    result.append(record)
                valid_idx += 1
            else:
                result.append(record)
                if isinstance(value, (int, float)):
                    valid_idx += 1

        stats.cleaned_records = len(result)
        return CleaningResult(data=result, stats=stats, changes=changes)

    # ---- 批量清洗 ----

    def clean_batch(self, data: List[Dict[str, Any]],
                    operations: List[Dict[str, Any]]) -> CleaningResult:
        """
        批量执行清洗操作

        Args:
            data: 数据列表
            operations: 操作列表，每个操作是 {"type": "...", "field": "...", ...}

        Returns:
            清洗结果
        """
        current_data = data
        total_stats = CleaningStats(total_records=len(data))
        all_changes = []

        for op in operations:
            op_type = op.get("type")

            if op_type == "null":
                result = self.clean_nulls(
                    current_data,
                    field=op.get("field"),
                    action=NullAction(op.get("action", "remove")),
                    default=op.get("default"),
                )
            elif op_type == "normalize":
                result = self.normalize_string(
                    current_data,
                    field=op.get("field"),
                    case=CaseAction(op.get("case", "keep")),
                    trim=op.get("trim", True),
                    remove_extra_space=op.get("remove_extra_space", True),
                )
            elif op_type == "dedup":
                result = self.deduplicate(
                    current_data,
                    strategy=DedupStrategy(op.get("strategy", "key")),
                    keys=op.get("keys"),
                )
            elif op_type == "outlier":
                result = self.handle_outliers(
                    current_data,
                    field=op.get("field"),
                    method=op.get("method", "iqr"),
                    action=op.get("outlier_action", "remove"),
                    factor=op.get("factor", 1.5),
                )
            else:
                continue

            current_data = result.data
            all_changes.extend(result.changes)

            # 合并统计
            total_stats.nulls_filled += result.stats.nulls_filled
            total_stats.nulls_removed += result.stats.nulls_removed
            total_stats.duplicates_removed += result.stats.duplicates_removed
            total_stats.values_normalized += result.stats.values_normalized
            total_stats.outliers_handled += result.stats.outliers_handled

        total_stats.cleaned_records = len(current_data)
        total_stats.removed_records = len(data) - len(current_data)

        return CleaningResult(data=current_data, stats=total_stats, changes=all_changes)

    # ---- 统计 ----

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                "custom_cleaners": len(self._custom_cleaners),
                "cleaner_names": list(self._custom_cleaners.keys()),
            }


# ============================================================
# 全局单例
# ============================================================

_cleaner: Optional[DataCleaner] = None
_c_lock = threading.RLock()


def get_data_cleaner() -> DataCleaner:
    """获取全局数据清洗器"""
    global _cleaner
    if _cleaner is None:
        with _c_lock:
            if _cleaner is None:
                _cleaner = DataCleaner()
    return _cleaner
