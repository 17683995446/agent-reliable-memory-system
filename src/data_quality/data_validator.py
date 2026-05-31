#!/usr/bin/env python3
"""
数据验证器 (DataValidator) - 阶段351

职责：
- Schema验证：结构化数据模式校验
- 类型检查：严格类型匹配与转换
- 约束验证：范围、格式、枚举、正则约束
- 自定义规则：可扩展验证规则
- 批量验证：高效批量数据校验

设计原则：
- 确定性规则，无模型依赖
- 线程安全（RLock）
- 最小层级，无循环依赖
"""

import re
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union


# ============================================================
# 枚举与数据结构
# ============================================================

class DataType(Enum):
    """数据类型"""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    LIST = "list"
    DICT = "dict"
    ANY = "any"


class ValidationLevel(Enum):
    """验证级别"""
    ERROR = "error"       # 必须通过
    WARNING = "warning"   # 警告但可通过
    INFO = "info"         # 信息提示


@dataclass
class ValidationError:
    """验证错误"""
    field: str
    message: str
    level: ValidationLevel = ValidationLevel.ERROR
    value: Any = None
    rule: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "message": self.message,
            "level": self.level.value,
            "value": str(self.value) if self.value is not None else None,
            "rule": self.rule,
        }


@dataclass
class ValidationResult:
    """验证结果"""
    valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    def add_error(self, error: ValidationError) -> None:
        if error.level == ValidationLevel.ERROR:
            self.errors.append(error)
            self.valid = False
        else:
            self.warnings.append(error)

    def merge(self, other: "ValidationResult") -> None:
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        if other.errors:
            self.valid = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
        }


# ============================================================
# 字段规则定义
# ============================================================

@dataclass
class FieldRule:
    """字段验证规则"""
    name: str
    data_type: DataType = DataType.ANY
    required: bool = True
    nullable: bool = False
    default: Any = None

    # 约束条件
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None      # 正则表达式
    enum_values: Optional[List[Any]] = None

    # 自定义验证
    custom_validator: Optional[Callable[[Any], bool]] = None
    custom_message: str = ""

    # 元数据
    description: str = ""
    example: Any = None


@dataclass
class Schema:
    """数据模式"""
    name: str
    fields: Dict[str, FieldRule] = field(default_factory=dict)
    strict: bool = False  # 是否拒绝未定义字段

    def add_field(self, rule: FieldRule) -> None:
        self.fields[rule.name] = rule

    def get_field(self, name: str) -> Optional[FieldRule]:
        return self.fields.get(name)


# ============================================================
# 类型检查器
# ============================================================

class TypeChecker:
    """类型检查器"""

    @staticmethod
    def check(value: Any, expected_type: DataType) -> bool:
        """检查值是否符合预期类型"""
        if expected_type == DataType.ANY:
            return True

        if expected_type == DataType.STRING:
            return isinstance(value, str)

        if expected_type == DataType.INTEGER:
            return isinstance(value, int) and not isinstance(value, bool)

        if expected_type == DataType.FLOAT:
            return isinstance(value, (int, float)) and not isinstance(value, bool)

        if expected_type == DataType.BOOLEAN:
            return isinstance(value, bool)

        if expected_type == DataType.DATE:
            return isinstance(value, date)

        if expected_type == DataType.DATETIME:
            return isinstance(value, datetime)

        if expected_type == DataType.LIST:
            return isinstance(value, Sequence) and not isinstance(value, str)

        if expected_type == DataType.DICT:
            return isinstance(value, Mapping)

        return False

    @staticmethod
    def try_convert(value: Any, target_type: DataType) -> Tuple[bool, Any]:
        """尝试类型转换，返回(成功, 转换后的值)"""
        try:
            if target_type == DataType.STRING:
                return True, str(value)

            if target_type == DataType.INTEGER:
                if isinstance(value, str):
                    return True, int(float(value))
                return True, int(value)

            if target_type == DataType.FLOAT:
                return True, float(value)

            if target_type == DataType.BOOLEAN:
                if isinstance(value, str):
                    lower = value.lower()
                    if lower in ("true", "yes", "1", "on"):
                        return True, True
                    if lower in ("false", "no", "0", "off"):
                        return True, False
                return True, bool(value)

            if target_type == DataType.DATE:
                if isinstance(value, str):
                    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y"):
                        try:
                            return True, datetime.strptime(value, fmt).date()
                        except ValueError:
                            continue
                return False, value

            if target_type == DataType.DATETIME:
                if isinstance(value, str):
                    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
                                "%Y/%m/%d %H:%M:%S"):
                        try:
                            return True, datetime.strptime(value, fmt)
                        except ValueError:
                            continue
                return False, value

            return False, value
        except (ValueError, TypeError):
            return False, value


# ============================================================
# 数据验证器
# ============================================================

class DataValidator:
    """
    数据验证器

    核心功能：
    1. Schema验证
    2. 类型检查
    3. 约束验证
    4. 自定义规则
    5. 批量验证
    """

    def __init__(self):
        self._schemas: Dict[str, Schema] = {}
        self._custom_rules: Dict[str, Callable[[Any, Dict[str, Any]], bool]] = {}
        self._lock = threading.RLock()

    # ---- Schema管理 ----

    def register_schema(self, schema: Schema) -> None:
        """注册数据模式"""
        with self._lock:
            self._schemas[schema.name] = schema

    def get_schema(self, name: str) -> Optional[Schema]:
        """获取数据模式"""
        return self._schemas.get(name)

    def remove_schema(self, name: str) -> bool:
        """移除数据模式"""
        with self._lock:
            return self._schemas.pop(name, None) is not None

    # ---- 自定义规则 ----

    def register_rule(self, name: str,
                      validator: Callable[[Any, Dict[str, Any]], bool]) -> None:
        """注册自定义验证规则"""
        with self._lock:
            self._custom_rules[name] = validator

    def validate_with_rule(self, value: Any, rule_name: str,
                           context: Optional[Dict[str, Any]] = None) -> bool:
        """使用自定义规则验证"""
        rule = self._custom_rules.get(rule_name)
        if rule is None:
            return True
        return rule(value, context or {})

    # ---- 核心验证 ----

    def validate(self, data: Any, schema: Schema,
                 convert: bool = False) -> ValidationResult:
        """
        验证数据

        Args:
            data: 待验证数据
            schema: 数据模式
            convert: 是否尝试类型转换

        Returns:
            ValidationResult
        """
        result = ValidationResult(valid=True)

        if not isinstance(data, Mapping):
            result.add_error(ValidationError(
                field="",
                message="Data must be a dictionary/mapping",
                rule="type",
            ))
            return result

        # 检查未定义字段
        if schema.strict:
            for key in data:
                if key not in schema.fields:
                    result.add_error(ValidationError(
                        field=key,
                        message=f"Undefined field: {key}",
                        level=ValidationLevel.WARNING,
                        rule="strict",
                    ))

        # 验证每个字段
        for field_name, rule in schema.fields.items():
            value = data.get(field_name)

            # 必填检查
            if rule.required and field_name not in data:
                result.add_error(ValidationError(
                    field=field_name,
                    message=f"Required field '{field_name}' is missing",
                    rule="required",
                ))
                continue

            # 空值检查
            if value is None:
                if not rule.nullable:
                    result.add_error(ValidationError(
                        field=field_name,
                        message=f"Field '{field_name}' cannot be null",
                        rule="nullable",
                    ))
                continue

            # 类型检查
            if rule.data_type != DataType.ANY:
                type_ok = TypeChecker.check(value, rule.data_type)
                if not type_ok and convert:
                    type_ok, value = TypeChecker.try_convert(value, rule.data_type)
                    if type_ok:
                        data[field_name] = value

                if not type_ok:
                    result.add_error(ValidationError(
                        field=field_name,
                        message=f"Field '{field_name}' must be {rule.data_type.value}, got {type(value).__name__}",
                        value=value,
                        rule="type",
                    ))
                    continue

            # 数值范围检查
            if rule.min_value is not None:
                if isinstance(value, (int, float)):
                    if value < rule.min_value:
                        result.add_error(ValidationError(
                            field=field_name,
                            message=f"Field '{field_name}' must be >= {rule.min_value}",
                            value=value,
                            rule="min_value",
                        ))

            if rule.max_value is not None:
                if isinstance(value, (int, float)):
                    if value > rule.max_value:
                        result.add_error(ValidationError(
                            field=field_name,
                            message=f"Field '{field_name}' must be <= {rule.max_value}",
                            value=value,
                            rule="max_value",
                        ))

            # 长度检查
            if rule.min_length is not None:
                if hasattr(value, "__len__"):
                    if len(value) < rule.min_length:
                        result.add_error(ValidationError(
                            field=field_name,
                            message=f"Field '{field_name}' length must be >= {rule.min_length}",
                            value=value,
                            rule="min_length",
                        ))

            if rule.max_length is not None:
                if hasattr(value, "__len__"):
                    if len(value) > rule.max_length:
                        result.add_error(ValidationError(
                            field=field_name,
                            message=f"Field '{field_name}' length must be <= {rule.max_length}",
                            value=value,
                            rule="max_length",
                        ))

            # 正则匹配
            if rule.pattern is not None:
                if isinstance(value, str):
                    if not re.match(rule.pattern, value):
                        result.add_error(ValidationError(
                            field=field_name,
                            message=f"Field '{field_name}' does not match pattern: {rule.pattern}",
                            value=value,
                            rule="pattern",
                        ))

            # 枚举值检查
            if rule.enum_values is not None:
                if value not in rule.enum_values:
                    result.add_error(ValidationError(
                        field=field_name,
                        message=f"Field '{field_name}' must be one of {rule.enum_values}",
                        value=value,
                        rule="enum",
                    ))

            # 自定义验证
            if rule.custom_validator is not None:
                try:
                    if not rule.custom_validator(value):
                        msg = rule.custom_message or f"Field '{field_name}' failed custom validation"
                        result.add_error(ValidationError(
                            field=field_name,
                            message=msg,
                            value=value,
                            rule="custom",
                        ))
                except Exception as e:
                    result.add_error(ValidationError(
                        field=field_name,
                        message=f"Custom validator error: {str(e)}",
                        value=value,
                        rule="custom",
                    ))

        return result

    def validate_with_schema_name(self, data: Any, schema_name: str,
                                   convert: bool = False) -> ValidationResult:
        """使用已注册的Schema验证"""
        schema = self.get_schema(schema_name)
        if schema is None:
            result = ValidationResult(valid=False)
            result.add_error(ValidationError(
                field="",
                message=f"Schema '{schema_name}' not found",
                rule="schema",
            ))
            return result
        return self.validate(data, schema, convert)

    # ---- 批量验证 ----

    def validate_batch(self, data_list: List[Any], schema: Schema,
                       convert: bool = False) -> List[Tuple[int, ValidationResult]]:
        """批量验证数据"""
        results = []
        for i, data in enumerate(data_list):
            result = self.validate(data, schema, convert)
            results.append((i, result))
        return results

    # ---- 快捷验证 ----

    def validate_field(self, value: Any, rule: FieldRule) -> ValidationResult:
        """验证单个字段"""
        result = ValidationResult(valid=True)

        # 类型检查
        if rule.data_type != DataType.ANY:
            if not TypeChecker.check(value, rule.data_type):
                result.add_error(ValidationError(
                    field=rule.name,
                    message=f"Must be {rule.data_type.value}",
                    value=value,
                    rule="type",
                ))

        # 其他约束检查（复用validate逻辑）
        if result.valid:
            temp_data = {rule.name: value}
            temp_schema = Schema(name="temp", fields={rule.name: rule})
            result = self.validate(temp_data, temp_schema)

        return result

    def is_valid(self, data: Any, schema: Schema) -> bool:
        """快速检查是否有效"""
        return self.validate(data, schema).valid

    # ---- 统计 ----

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                "schemas": len(self._schemas),
                "custom_rules": len(self._custom_rules),
                "schema_names": list(self._schemas.keys()),
            }


# ============================================================
# 预定义验证器
# ============================================================

class CommonValidators:
    """常用验证器"""

    @staticmethod
    def email(value: Any) -> bool:
        """邮箱验证"""
        if not isinstance(value, str):
            return False
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return bool(re.match(pattern, value))

    @staticmethod
    def phone(value: Any) -> bool:
        """手机号验证（中国）"""
        if not isinstance(value, str):
            return False
        pattern = r"^1[3-9]\d{9}$"
        return bool(re.match(pattern, value))

    @staticmethod
    def url(value: Any) -> bool:
        """URL验证"""
        if not isinstance(value, str):
            return False
        pattern = r"^https?://[^\s/$.?#].[^\s]*$"
        return bool(re.match(pattern, value))

    @staticmethod
    def ipv4(value: Any) -> bool:
        """IPv4验证"""
        if not isinstance(value, str):
            return False
        pattern = r"^(\d{1,3}\.){3}\d{1,3}$"
        if not re.match(pattern, value):
            return False
        parts = value.split(".")
        return all(0 <= int(p) <= 255 for p in parts)

    @staticmethod
    def positive_number(value: Any) -> bool:
        """正数验证"""
        if isinstance(value, (int, float)):
            return value > 0
        return False

    @staticmethod
    def non_empty_string(value: Any) -> bool:
        """非空字符串验证"""
        return isinstance(value, str) and len(value.strip()) > 0

    @staticmethod
    def date_range(value: Any, min_date: date, max_date: date) -> bool:
        """日期范围验证"""
        if isinstance(value, (date, datetime)):
            if isinstance(value, datetime):
                value = value.date()
            return min_date <= value <= max_date
        return False


# ============================================================
# 全局单例
# ============================================================

_validator: Optional[DataValidator] = None
_v_lock = threading.RLock()


def get_data_validator() -> DataValidator:
    """获取全局数据验证器"""
    global _validator
    if _validator is None:
        with _v_lock:
            if _validator is None:
                _validator = DataValidator()
    return _validator
