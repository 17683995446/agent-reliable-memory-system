#!/usr/bin/env python3
"""
数据修复引擎 (DataRepairEngine) - 阶段355

职责：
- 自动修复：基于规则自动修复数据
- 规则引擎：可配置修复规则
- 修复策略：多种修复策略支持
- 修复追踪：记录修复历史
- 批量修复：高效批量处理

设计原则：
- 确定性规则，无模型依赖
- 线程安全（RLock）
- 最小层级，无循环依赖
"""

import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union


# ============================================================
# 枚举与数据结构
# ============================================================

class RepairAction(Enum):
    """修复动作"""
    REPLACE = "replace"       # 替换值
    REMOVE = "remove"         # 删除字段/记录
    DEFAULT = "default"       # 使用默认值
    INTERPOLATE = "interpolate"  # 插值
    TRANSFORM = "transform"   # 转换
    MERGE = "merge"           # 合并
    SPLIT = "split"           # 拆分


class RepairPriority(Enum):
    """修复优先级"""
    CRITICAL = 0    # 最高优先级
    HIGH = 1
    MEDIUM = 2
    LOW = 3


@dataclass
class RepairRule:
    """修复规则"""
    name: str
    field: str
    condition: Callable[[Any], bool]  # 触发条件
    action: RepairAction
    value: Any = None                  # 修复值
    transform: Optional[Callable[[Any], Any]] = None  # 转换函数
    priority: RepairPriority = RepairPriority.MEDIUM
    enabled: bool = True
    description: str = ""


@dataclass
class RepairRecord:
    """修复记录"""
    record_index: int
    field: str
    original_value: Any
    repaired_value: Any
    rule_name: str
    action: RepairAction
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = datetime.now().timestamp()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_index": self.record_index,
            "field": self.field,
            "original_value": str(self.original_value),
            "repaired_value": str(self.repaired_value),
            "rule_name": self.rule_name,
            "action": self.action.value,
            "timestamp": self.timestamp,
        }


@dataclass
class RepairStats:
    """修复统计"""
    total_records: int = 0
    repaired_records: int = 0
    total_repairs: int = 0
    by_rule: Dict[str, int] = field(default_factory=dict)
    by_field: Dict[str, int] = field(default_factory=dict)
    by_action: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_records": self.total_records,
            "repaired_records": self.repaired_records,
            "total_repairs": self.total_repairs,
            "by_rule": self.by_rule,
            "by_field": self.by_field,
            "by_action": self.by_action,
        }


@dataclass
class RepairResult:
    """修复结果"""
    data: Any
    stats: RepairStats
    repairs: List[RepairRecord] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stats": self.stats.to_dict(),
            "repairs": [r.to_dict() for r in self.repairs],
            "repair_count": len(self.repairs),
        }


# ============================================================
# 内置修复规则
# ============================================================

class BuiltinRules:
    """内置修复规则"""

    @staticmethod
    def null_to_default(field: str, default: Any) -> RepairRule:
        """空值替换为默认值"""
        return RepairRule(
            name=f"null_to_default_{field}",
            field=field,
            condition=lambda v: v is None or v == "",
            action=RepairAction.DEFAULT,
            value=default,
            description=f"Replace null/empty with default: {default}",
        )

    @staticmethod
    def trim_whitespace(field: str) -> RepairRule:
        """去除首尾空白"""
        return RepairRule(
            name=f"trim_{field}",
            field=field,
            condition=lambda v: isinstance(v, str) and (v != v.strip()),
            action=RepairAction.TRANSFORM,
            transform=lambda v: v.strip() if isinstance(v, str) else v,
            description="Trim leading/trailing whitespace",
        )

    @staticmethod
    def normalize_case(field: str, case: str = "lower") -> RepairRule:
        """标准化大小写"""
        def transform(v):
            if not isinstance(v, str):
                return v
            if case == "lower":
                return v.lower()
            if case == "upper":
                return v.upper()
            if case == "title":
                return v.title()
            return v

        return RepairRule(
            name=f"normalize_case_{field}",
            field=field,
            condition=lambda v: isinstance(v, str),
            action=RepairAction.TRANSFORM,
            transform=transform,
            description=f"Normalize case to {case}",
        )

    @staticmethod
    def fix_phone_format(field: str) -> RepairRule:
        """修复手机号格式"""
        def transform(v):
            if not isinstance(v, str):
                return v
            # 移除非数字字符
            digits = re.sub(r"\D", "", v)
            # 如果是11位且以1开头，保持原样
            if len(digits) == 11 and digits.startswith("1"):
                return digits
            return v

        def condition(v):
            if not isinstance(v, str):
                return False
            digits = re.sub(r"\D", "", v)
            return len(digits) == 11 and digits.startswith("1") and v != digits

        return RepairRule(
            name=f"fix_phone_{field}",
            field=field,
            condition=condition,
            action=RepairAction.TRANSFORM,
            transform=transform,
            description="Fix phone number format",
        )

    @staticmethod
    def clamp_value(field: str, min_val: float, max_val: float) -> RepairRule:
        """限制数值范围"""
        def transform(v):
            if isinstance(v, (int, float)):
                return max(min_val, min(max_val, v))
            return v

        def condition(v):
            if isinstance(v, (int, float)):
                return v < min_val or v > max_val
            return False

        return RepairRule(
            name=f"clamp_{field}",
            field=field,
            condition=condition,
            action=RepairAction.TRANSFORM,
            transform=transform,
            description=f"Clamp value to [{min_val}, {max_val}]",
        )

    @staticmethod
    def fix_date_format(field: str, from_fmt: str, to_fmt: str) -> RepairRule:
        """修复日期格式"""
        def transform(v):
            if not isinstance(v, str):
                return v
            try:
                dt = datetime.strptime(v, from_fmt)
                return dt.strftime(to_fmt)
            except ValueError:
                return v

        def condition(v):
            if not isinstance(v, str):
                return False
            try:
                datetime.strptime(v, from_fmt)
                return True
            except ValueError:
                return False

        return RepairRule(
            name=f"fix_date_{field}",
            field=field,
            condition=condition,
            action=RepairAction.TRANSFORM,
            transform=transform,
            description=f"Convert date from {from_fmt} to {to_fmt}",
        )

    @staticmethod
    def remove_invalid_chars(field: str, pattern: str) -> RepairRule:
        """移除无效字符"""
        def transform(v):
            if isinstance(v, str):
                return re.sub(pattern, "", v)
            return v

        def condition(v):
            if isinstance(v, str):
                return bool(re.search(pattern, v))
            return False

        return RepairRule(
            name=f"remove_chars_{field}",
            field=field,
            condition=condition,
            action=RepairAction.TRANSFORM,
            transform=transform,
            description=f"Remove characters matching: {pattern}",
        )


# ============================================================
# 数据修复引擎
# ============================================================

class DataRepairEngine:
    """
    数据修复引擎

    核心功能：
    1. 自动修复
    2. 规则引擎
    3. 修复策略
    4. 修复追踪
    5. 批量修复
    """

    def __init__(self):
        self._rules: Dict[str, RepairRule] = {}
        self._lock = threading.RLock()
        self._repair_history: List[RepairRecord] = []

    # ---- 规则管理 ----

    def add_rule(self, rule: RepairRule) -> None:
        """添加修复规则"""
        with self._lock:
            self._rules[rule.name] = rule

    def remove_rule(self, name: str) -> bool:
        """移除修复规则"""
        with self._lock:
            return self._rules.pop(name, None) is not None

    def get_rule(self, name: str) -> Optional[RepairRule]:
        """获取修复规则"""
        return self._rules.get(name)

    def enable_rule(self, name: str) -> bool:
        """启用规则"""
        rule = self._rules.get(name)
        if rule:
            rule.enabled = True
            return True
        return False

    def disable_rule(self, name: str) -> bool:
        """禁用规则"""
        rule = self._rules.get(name)
        if rule:
            rule.enabled = False
            return True
        return False

    def list_rules(self) -> List[Dict[str, Any]]:
        """列出所有规则"""
        with self._lock:
            return [
                {
                    "name": r.name,
                    "field": r.field,
                    "action": r.action.value,
                    "priority": r.priority.value,
                    "enabled": r.enabled,
                    "description": r.description,
                }
                for r in sorted(self._rules.values(), key=lambda x: x.priority.value)
            ]

    # ---- 单条记录修复 ----

    def repair_record(self, record: Dict[str, Any],
                      index: int = 0,
                      rules: Optional[List[RepairRule]] = None) -> Tuple[Dict[str, Any], List[RepairRecord]]:
        """
        修复单条记录

        Returns:
            (修复后的记录, 修复记录列表)
        """
        if rules is None:
            rules = sorted(
                [r for r in self._rules.values() if r.enabled],
                key=lambda x: x.priority.value
            )

        repaired = record.copy()
        repairs = []

        for rule in rules:
            field = rule.field
            if field not in repaired:
                continue

            value = repaired[field]

            # 检查条件
            try:
                if not rule.condition(value):
                    continue
            except Exception:
                continue

            # 执行修复
            original = value
            new_value = value

            if rule.action == RepairAction.REPLACE:
                new_value = rule.value

            elif rule.action == RepairAction.DEFAULT:
                new_value = rule.value

            elif rule.action == RepairAction.TRANSFORM:
                if rule.transform:
                    try:
                        new_value = rule.transform(value)
                    except Exception:
                        continue

            elif rule.action == RepairAction.REMOVE:
                if field in repaired:
                    del repaired[field]
                repairs.append(RepairRecord(
                    record_index=index,
                    field=field,
                    original_value=original,
                    repaired_value="[REMOVED]",
                    rule_name=rule.name,
                    action=rule.action,
                ))
                continue

            # 记录修复
            if new_value != original:
                repaired[field] = new_value
                repairs.append(RepairRecord(
                    record_index=index,
                    field=field,
                    original_value=original,
                    repaired_value=new_value,
                    rule_name=rule.name,
                    action=rule.action,
                ))

        return repaired, repairs

    # ---- 批量修复 ----

    def repair(self, data: List[Dict[str, Any]],
               rules: Optional[List[RepairRule]] = None) -> RepairResult:
        """
        批量修复数据

        Args:
            data: 数据列表
            rules: 指定规则列表（None则使用所有启用的规则）

        Returns:
            RepairResult
        """
        stats = RepairStats(total_records=len(data))
        all_repairs = []
        result = []

        for i, record in enumerate(data):
            if not isinstance(record, dict):
                result.append(record)
                continue

            repaired, repairs = self.repair_record(record, i, rules)
            result.append(repaired)
            all_repairs.extend(repairs)

            if repairs:
                stats.repaired_records += 1

        # 统计
        stats.total_repairs = len(all_repairs)
        for repair in all_repairs:
            stats.by_rule[repair.rule_name] = stats.by_rule.get(repair.rule_name, 0) + 1
            stats.by_field[repair.field] = stats.by_field.get(repair.field, 0) + 1
            stats.by_action[repair.action.value] = stats.by_action.get(repair.action.value, 0) + 1

        # 保存历史
        with self._lock:
            self._repair_history.extend(all_repairs)

        return RepairResult(data=result, stats=stats, repairs=all_repairs)

    # ---- 按字段修复 ----

    def repair_field(self, data: List[Dict[str, Any]],
                     field: str,
                     action: RepairAction,
                     value: Any = None,
                     condition: Optional[Callable[[Any], bool]] = None,
                     transform: Optional[Callable[[Any], Any]] = None) -> RepairResult:
        """
        修复特定字段

        Args:
            data: 数据列表
            field: 字段名
            action: 修复动作
            value: 修复值
            condition: 触发条件
            transform: 转换函数

        Returns:
            RepairResult
        """
        rule = RepairRule(
            name=f"temp_{field}",
            field=field,
            condition=condition or (lambda v: True),
            action=action,
            value=value,
            transform=transform,
        )

        return self.repair(data, [rule])

    # ---- 快捷修复方法 ----

    def fill_nulls(self, data: List[Dict[str, Any]],
                   field: str,
                   default: Any) -> RepairResult:
        """填充空值"""
        rule = BuiltinRules.null_to_default(field, default)
        return self.repair(data, [rule])

    def trim_strings(self, data: List[Dict[str, Any]],
                     fields: Optional[List[str]] = None) -> RepairResult:
        """去除字符串空白"""
        if fields is None:
            fields = set()
            for record in data:
                for k, v in record.items():
                    if isinstance(v, str):
                        fields.add(k)
            fields = list(fields)

        rules = [BuiltinRules.trim_whitespace(f) for f in fields]
        return self.repair(data, rules)

    def normalize_case(self, data: List[Dict[str, Any]],
                       field: str,
                       case: str = "lower") -> RepairResult:
        """标准化大小写"""
        rule = BuiltinRules.normalize_case(field, case)
        return self.repair(data, [rule])

    def clamp_values(self, data: List[Dict[str, Any]],
                     field: str,
                     min_val: float,
                     max_val: float) -> RepairResult:
        """限制数值范围"""
        rule = BuiltinRules.clamp_value(field, min_val, max_val)
        return self.repair(data, [rule])

    # ---- 预览修复 ----

    def preview(self, data: List[Dict[str, Any]],
                rules: Optional[List[RepairRule]] = None,
                limit: int = 10) -> List[Dict[str, Any]]:
        """
        预览修复结果（不实际修改）

        Returns:
            修复记录列表（前limit条）
        """
        result = self.repair(data[:limit], rules)
        return [r.to_dict() for r in result.repairs]

    # ---- 历史管理 ----

    def get_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取修复历史"""
        with self._lock:
            return [r.to_dict() for r in self._repair_history[-limit:]]

    def clear_history(self) -> int:
        """清空修复历史"""
        with self._lock:
            count = len(self._repair_history)
            self._repair_history.clear()
            return count

    # ---- 统计 ----

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                "rules": len(self._rules),
                "enabled_rules": sum(1 for r in self._rules.values() if r.enabled),
                "history_count": len(self._repair_history),
                "rule_names": list(self._rules.keys()),
            }


# ============================================================
# 全局单例
# ============================================================

_engine: Optional[DataRepairEngine] = None
_e_lock = threading.RLock()


def get_repair_engine() -> DataRepairEngine:
    """获取全局修复引擎"""
    global _engine
    if _engine is None:
        with _e_lock:
            if _engine is None:
                _engine = DataRepairEngine()
    return _engine
