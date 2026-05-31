#!/usr/bin/env python3
"""
配置验证器 (ConfigValidator) - 阶段327

职责：
- Schema定义与验证
- 类型检查（str/int/float/bool/list/dict/enum）
- 约束规则（范围、长度、正则、必填）
- 默认值填充
- 验证错误收集与报告

设计原则：
- 确定性规则，无模型依赖
- 线程安全（RLock）
- 最小层级，无循环依赖
"""

import re
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union


# ============================================================
# 枚举与数据结构
# ============================================================

class FieldType(Enum):
    """字段类型"""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    LIST = "list"
    DICT = "dict"
    ANY = "any"
    ENUM = "enum"


class Severity(Enum):
    """错误严重程度"""
    ERROR = "error"       # 阻断性错误
    WARNING = "warning"   # 警告
    INFO = "info"         # 信息


@dataclass
class FieldSchema:
    """字段Schema定义"""
    name: str
    field_type: FieldType = FieldType.ANY
    required: bool = False
    default: Any = None
    description: str = ""
    enum_values: Optional[List[Any]] = None
    min_value: Optional[Union[int, float]] = None
    max_value: Optional[Union[int, float]] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None          # 正则表达式
    item_type: Optional[FieldType] = None # 列表元素类型
    item_schema: Optional['FieldSchema'] = None  # 列表元素Schema
    nested_schema: Optional[Dict[str, 'FieldSchema']] = None  # 嵌套字典Schema
    transform: Optional[Callable[[Any], Any]] = None  # 值转换函数
    deprecated: bool = False
    deprecated_message: str = ""


@dataclass
class ValidationError:
    """验证错误"""
    field: str
    message: str
    severity: Severity = Severity.ERROR
    value: Any = None
    expected: str = ""


@dataclass
class ValidationResult:
    """验证结果"""
    valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)
    validated_data: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)


# ============================================================
# Schema构建器（流式API）
# ============================================================

class SchemaBuilder:
    """
    Schema构建器

    提供流式API用于定义配置Schema

    用法:
        schema = SchemaBuilder() \\
            .add_field("host", FieldType.STRING, required=True, default="localhost") \\
            .add_field("port", FieldType.INTEGER, required=True, min_value=1, max_value=65535) \\
            .add_field("debug", FieldType.BOOLEAN, default=False) \\
            .build()
    """

    def __init__(self):
        self._fields: Dict[str, FieldSchema] = {}

    def add_field(
        self,
        name: str,
        field_type: FieldType = FieldType.ANY,
        required: bool = False,
        default: Any = None,
        description: str = "",
        enum_values: Optional[List[Any]] = None,
        min_value: Optional[Union[int, float]] = None,
        max_value: Optional[Union[int, float]] = None,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
        pattern: Optional[str] = None,
        item_type: Optional[FieldType] = None,
        item_schema: Optional[FieldSchema] = None,
        nested_schema: Optional[Dict[str, 'FieldSchema']] = None,
        transform: Optional[Callable[[Any], Any]] = None,
        deprecated: bool = False,
        deprecated_message: str = "",
    ) -> 'SchemaBuilder':
        """添加字段定义"""
        self._fields[name] = FieldSchema(
            name=name,
            field_type=field_type,
            required=required,
            default=default,
            description=description,
            enum_values=enum_values,
            min_value=min_value,
            max_value=max_value,
            min_length=min_length,
            max_length=max_length,
            pattern=pattern,
            item_type=item_type,
            item_schema=item_schema,
            nested_schema=nested_schema,
            transform=transform,
            deprecated=deprecated,
            deprecated_message=deprecated_message,
        )
        return self

    def add_nested(
        self,
        name: str,
        nested_builder_or_schema,
        required: bool = False,
        description: str = ""
    ) -> 'SchemaBuilder':
        """添加嵌套Schema（接受SchemaBuilder或dict）"""
        if isinstance(nested_builder_or_schema, SchemaBuilder):
            nested_schema = nested_builder_or_schema._fields
        else:
            nested_schema = nested_builder_or_schema
        self._fields[name] = FieldSchema(
            name=name,
            field_type=FieldType.DICT,
            required=required,
            description=description,
            nested_schema=nested_schema,
        )
        return self

    def add_list(
        self,
        name: str,
        item_type: FieldType = FieldType.ANY,
        item_schema: Optional[FieldSchema] = None,
        required: bool = False,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
        description: str = ""
    ) -> 'SchemaBuilder':
        """添加列表字段"""
        self._fields[name] = FieldSchema(
            name=name,
            field_type=FieldType.LIST,
            required=required,
            min_length=min_length,
            max_length=max_length,
            item_type=item_type,
            item_schema=item_schema,
            description=description,
        )
        return self

    def remove_field(self, name: str) -> 'SchemaBuilder':
        """移除字段"""
        self._fields.pop(name, None)
        return self

    def build(self) -> Dict[str, FieldSchema]:
        """构建Schema"""
        return dict(self._fields)


# ============================================================
# 配置验证器
# ============================================================

class ConfigValidator:
    """
    配置验证器

    核心功能：
    1. 基于Schema验证配置
    2. 类型检查与自动转换
    3. 约束验证（范围、长度、正则）
    4. 默认值填充
    5. 废弃字段警告
    6. 未知字段检测
    """

    def __init__(self):
        self._schemas: Dict[str, Dict[str, FieldSchema]] = {}
        self._lock = threading.RLock()
        self._strict_mode: bool = False  # 严格模式：拒绝未知字段

    # ---- Schema管理 ----

    def register_schema(self, name: str, schema: Dict[str, FieldSchema]) -> None:
        """注册Schema"""
        with self._lock:
            self._schemas[name] = schema

    def register_schema_from_builder(self, name: str, builder: SchemaBuilder) -> None:
        """从构建器注册Schema"""
        self.register_schema(name, builder.build())

    def get_schema(self, name: str) -> Optional[Dict[str, FieldSchema]]:
        """获取Schema"""
        with self._lock:
            return self._schemas.get(name)

    def remove_schema(self, name: str) -> bool:
        """移除Schema"""
        with self._lock:
            if name in self._schemas:
                del self._schemas[name]
                return True
            return False

    def set_strict_mode(self, strict: bool) -> None:
        """设置严格模式"""
        self._strict_mode = strict

    # ---- 验证 ----

    def validate(
        self,
        config: Dict[str, Any],
        schema_name: Optional[str] = None,
        schema: Optional[Dict[str, FieldSchema]] = None
    ) -> ValidationResult:
        """
        验证配置

        Args:
            config: 配置字典
            schema_name: 已注册的Schema名称
            schema: 直接传入的Schema

        Returns:
            验证结果
        """
        start = time.monotonic()

        if schema is None and schema_name:
            schema = self.get_schema(schema_name)

        if schema is None:
            return ValidationResult(
                valid=False,
                errors=[ValidationError("", "Schema not found")],
            )

        errors = []
        warnings = []
        validated = {}

        # 验证每个Schema字段
        for field_name, field_schema in schema.items():
            value = config.get(field_name)

            # 检查必填
            if value is None and field_schema.required:
                if field_schema.default is not None:
                    value = field_schema.default
                else:
                    errors.append(ValidationError(
                        field=field_name,
                        message=f"Required field '{field_name}' is missing",
                        severity=Severity.ERROR,
                    ))
                    continue

            # 使用默认值
            if value is None and field_schema.default is not None:
                value = field_schema.default

            # 跳过None值（非必填且无默认值）
            if value is None:
                continue

            # 废弃警告
            if field_schema.deprecated:
                warnings.append(ValidationError(
                    field=field_name,
                    message=f"Field '{field_name}' is deprecated. {field_schema.deprecated_message}",
                    severity=Severity.WARNING,
                    value=value,
                ))

            # 类型检查
            type_error = self._check_type(field_name, value, field_schema)
            if type_error:
                errors.append(type_error)
                continue

            # 约束检查
            constraint_errors = self._check_constraints(field_name, value, field_schema)
            errors.extend(constraint_errors)
            if constraint_errors:
                continue

            # 值转换
            if field_schema.transform:
                try:
                    value = field_schema.transform(value)
                except Exception as e:
                    errors.append(ValidationError(
                        field=field_name,
                        message=f"Transform failed: {e}",
                        severity=Severity.ERROR,
                        value=value,
                    ))
                    continue

            # 嵌套验证
            if field_schema.field_type == FieldType.DICT and field_schema.nested_schema:
                if isinstance(value, dict):
                    nested_result = self.validate(value, schema=field_schema.nested_schema)
                    if nested_result.errors:
                        for err in nested_result.errors:
                            errors.append(ValidationError(
                                field=f"{field_name}.{err.field}",
                                message=err.message,
                                severity=err.severity,
                                value=err.value,
                            ))
                    value = nested_result.validated_data

            # 列表元素验证
            if field_schema.field_type == FieldType.LIST and isinstance(value, list):
                validated_list = []
                for i, item in enumerate(value):
                    if field_schema.item_schema:
                        if isinstance(item, dict):
                            item_result = self.validate(item, schema={field_schema.item_schema.name: field_schema.item_schema})
                            if item_result.errors:
                                for err in item_result.errors:
                                    errors.append(ValidationError(
                                        field=f"{field_name}[{i}].{err.field}",
                                        message=err.message,
                                        severity=err.severity,
                                    ))
                            validated_list.append(item_result.validated_data)
                        else:
                            validated_list.append(item)
                    elif field_schema.item_type:
                        type_err = self._check_type(f"{field_name}[{i}]", item,
                            FieldSchema(name=f"{field_name}[{i}]", field_type=field_schema.item_type))
                        if type_err:
                            errors.append(type_err)
                        validated_list.append(item)
                    else:
                        validated_list.append(item)
                value = validated_list

            validated[field_name] = value

        # 检测未知字段
        if self._strict_mode:
            for key in config:
                if key not in schema:
                    warnings.append(ValidationError(
                        field=key,
                        message=f"Unknown field '{key}'",
                        severity=Severity.WARNING,
                        value=config[key],
                    ))

        duration = (time.monotonic() - start) * 1000

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            validated_data=validated,
            duration_ms=duration,
        )

    def validate_and_fill(
        self,
        config: Dict[str, Any],
        schema: Dict[str, FieldSchema]
    ) -> Tuple[bool, Dict[str, Any], List[ValidationError]]:
        """
        验证并填充默认值

        Returns:
            (是否有效, 填充后的配置, 错误列表)
        """
        result = self.validate(config, schema=schema)
        return result.valid, result.validated_data, result.errors

    # ---- 内部方法 ----

    def _check_type(
        self,
        field_name: str,
        value: Any,
        schema: FieldSchema
    ) -> Optional[ValidationError]:
        """检查类型"""
        expected_type = {
            FieldType.STRING: str,
            FieldType.INTEGER: int,
            FieldType.FLOAT: (int, float),
            FieldType.BOOLEAN: bool,
            FieldType.LIST: list,
            FieldType.DICT: dict,
            FieldType.ANY: object,
        }

        if schema.field_type == FieldType.ENUM:
            if schema.enum_values and value not in schema.enum_values:
                return ValidationError(
                    field=field_name,
                    message=f"Value '{value}' not in enum {schema.enum_values}",
                    severity=Severity.ERROR,
                    value=value,
                    expected=f"one of {schema.enum_values}",
                )
            return None

        type_cls = expected_type.get(schema.field_type)
        if type_cls and not isinstance(value, type_cls):
            # 尝试自动转换
            converted = self._try_convert(value, schema.field_type)
            if converted is not None:
                return None  # 转换成功，不报错
            return ValidationError(
                field=field_name,
                message=f"Expected {schema.field_type.value}, got {type(value).__name__}",
                severity=Severity.ERROR,
                value=value,
                expected=schema.field_type.value,
            )

        return None

    def _try_convert(self, value: Any, target_type: FieldType) -> Any:
        """尝试类型转换"""
        try:
            if target_type == FieldType.INTEGER and isinstance(value, str):
                return int(value)
            elif target_type == FieldType.FLOAT and isinstance(value, (str, int)):
                return float(value)
            elif target_type == FieldType.BOOLEAN and isinstance(value, str):
                return value.lower() in ("true", "yes", "1")
            elif target_type == FieldType.STRING and not isinstance(value, str):
                return str(value)
        except (ValueError, TypeError):
            pass
        return None

    def _check_constraints(
        self,
        field_name: str,
        value: Any,
        schema: FieldSchema
    ) -> List[ValidationError]:
        """检查约束"""
        errors = []

        # 数值范围
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if schema.min_value is not None and value < schema.min_value:
                errors.append(ValidationError(
                    field=field_name,
                    message=f"Value {value} < minimum {schema.min_value}",
                    severity=Severity.ERROR,
                    value=value,
                    expected=f">= {schema.min_value}",
                ))
            if schema.max_value is not None and value > schema.max_value:
                errors.append(ValidationError(
                    field=field_name,
                    message=f"Value {value} > maximum {schema.max_value}",
                    severity=Severity.ERROR,
                    value=value,
                    expected=f"<= {schema.max_value}",
                ))

        # 字符串长度
        if isinstance(value, str):
            if schema.min_length is not None and len(value) < schema.min_length:
                errors.append(ValidationError(
                    field=field_name,
                    message=f"Length {len(value)} < minimum {schema.min_length}",
                    severity=Severity.ERROR,
                    value=value,
                ))
            if schema.max_length is not None and len(value) > schema.max_length:
                errors.append(ValidationError(
                    field=field_name,
                    message=f"Length {len(value)} > maximum {schema.max_length}",
                    severity=Severity.ERROR,
                    value=value,
                ))

            # 正则匹配
            if schema.pattern:
                if not re.match(schema.pattern, value):
                    errors.append(ValidationError(
                        field=field_name,
                        message=f"Value '{value}' does not match pattern '{schema.pattern}'",
                        severity=Severity.ERROR,
                        value=value,
                        expected=f"pattern: {schema.pattern}",
                    ))

        # 列表长度
        if isinstance(value, list):
            if schema.min_length is not None and len(value) < schema.min_length:
                errors.append(ValidationError(
                    field=field_name,
                    message=f"List length {len(value)} < minimum {schema.min_length}",
                    severity=Severity.ERROR,
                    value=value,
                ))
            if schema.max_length is not None and len(value) > schema.max_length:
                errors.append(ValidationError(
                    field=field_name,
                    message=f"List length {len(value)} > maximum {schema.max_length}",
                    severity=Severity.ERROR,
                    value=value,
                ))

        return errors

    def get_stats(self) -> Dict[str, Any]:
        """获取验证器统计"""
        with self._lock:
            return {
                "registered_schemas": len(self._schemas),
                "strict_mode": self._strict_mode,
            }


# ============================================================
# 全局单例
# ============================================================

_config_validator: Optional[ConfigValidator] = None
_validator_lock = threading.RLock()


def get_config_validator() -> ConfigValidator:
    """获取全局配置验证器（双重检查锁定）"""
    global _config_validator
    if _config_validator is None:
        with _validator_lock:
            if _config_validator is None:
                _config_validator = ConfigValidator()
    return _config_validator
