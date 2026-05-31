"""
API验证器

第313阶段：请求数据验证、类型检查、约束验证
遵循"图难于其易，为大于其细"原则，实现细粒度的数据验证
"""

import threading
import re
from typing import Dict, List, Optional, Any, Callable, Union, Type
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class ValidationType(Enum):
    """验证类型"""
    REQUIRED = "required"
    TYPE = "type"
    MIN = "min"
    MAX = "max"
    MIN_LENGTH = "min_length"
    MAX_LENGTH = "max_length"
    PATTERN = "pattern"
    CHOICE = "choice"
    RANGE = "range"
    EMAIL = "email"
    URL = "url"
    DATE = "date"
    CUSTOM = "custom"


@dataclass
class ValidationError:
    """验证错误"""
    field: str
    type: ValidationType
    message: str
    value: Any = None


@dataclass
class ValidationResult:
    """验证结果"""
    valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)
    
    def add_error(self, error: ValidationError) -> None:
        """添加错误"""
        self.errors.append(error)
        self.valid = False
    
    def get_error_messages(self) -> Dict[str, List[str]]:
        """获取错误消息字典"""
        result = {}
        for error in self.errors:
            if error.field not in result:
                result[error.field] = []
            result[error.field].append(error.message)
        return result


@dataclass
class FieldRule:
    """字段验证规则"""
    name: str
    type: Type = str
    required: bool = True
    default: Any = None
    min_value: Optional[Union[int, float]] = None
    max_value: Optional[Union[int, float]] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None
    choices: Optional[List[Any]] = None
    custom_validator: Optional[Callable] = None
    description: str = ""
    
    # 嵌套字段
    nested: Optional[Dict[str, 'FieldRule']] = None
    item_rule: Optional['FieldRule'] = None  # 数组元素规则


class ApiValidator:
    """
    API验证器
    
    职责：
    1. 请求数据验证
    2. 类型检查
    3. 约束验证
    4. 自定义验证规则
    
    设计原则：
    - 细粒度验证规则
    - 可扩展的验证器
    - 详细的错误信息
    """
    
    def __init__(self):
        self._rules: Dict[str, FieldRule] = {}
        self._custom_validators: Dict[str, Callable] = {}
        self._lock = threading.RLock()
        
        # 注册内置验证器
        self._register_builtin_validators()
    
    def _register_builtin_validators(self) -> None:
        """注册内置验证器"""
        self._custom_validators['email'] = self._validate_email
        self._custom_validators['url'] = self._validate_url
        self._custom_validators['date'] = self._validate_date
        self._custom_validators['uuid'] = self._validate_uuid
    
    def add_rule(self, rule: FieldRule) -> None:
        """
        添加验证规则
        
        Args:
            rule: 字段规则
        """
        with self._lock:
            self._rules[rule.name] = rule
    
    def add_rules(self, rules: List[FieldRule]) -> None:
        """
        批量添加验证规则
        
        Args:
            rules: 规则列表
        """
        with self._lock:
            for rule in rules:
                self._rules[rule.name] = rule
    
    def remove_rule(self, name: str) -> bool:
        """
        移除验证规则
        
        Args:
            name: 字段名称
        
        Returns:
            是否移除成功
        """
        with self._lock:
            if name in self._rules:
                del self._rules[name]
                return True
            return False
    
    def get_rules(self) -> Dict[str, FieldRule]:
        """获取所有规则"""
        with self._lock:
            return dict(self._rules)
    
    def validate(
        self,
        data: Dict[str, Any],
        rules: Optional[Dict[str, FieldRule]] = None
    ) -> ValidationResult:
        """
        验证数据
        
        Args:
            data: 待验证数据
            rules: 验证规则（可选，默认使用已注册的规则）
        
        Returns:
            验证结果
        """
        validation_rules = rules or self._rules
        result = ValidationResult(valid=True, data={})
        
        for field_name, rule in validation_rules.items():
            value = data.get(field_name)
            
            # 检查必需字段
            if rule.required and value is None:
                if rule.default is not None:
                    value = rule.default
                else:
                    result.add_error(ValidationError(
                        field=field_name,
                        type=ValidationType.REQUIRED,
                        message=f"Field '{field_name}' is required"
                    ))
                    continue
            
            # 跳过可选且未提供的字段
            if value is None:
                if rule.default is not None:
                    result.data[field_name] = rule.default
                continue
            
            # 类型检查
            type_error = self._check_type(field_name, value, rule)
            if type_error:
                result.add_error(type_error)
                continue
            
            # 约束验证
            constraint_errors = self._check_constraints(field_name, value, rule)
            for error in constraint_errors:
                result.add_error(error)
            
            if not constraint_errors:
                result.data[field_name] = value
        
        return result
    
    def _check_type(
        self,
        field_name: str,
        value: Any,
        rule: FieldRule
    ) -> Optional[ValidationError]:
        """
        检查类型
        
        Args:
            field_name: 字段名
            value: 值
            rule: 规则
        
        Returns:
            验证错误或None
        """
        expected_type = rule.type
        
        # 特殊处理list类型
        if expected_type == list:
            if not isinstance(value, (list, tuple)):
                return ValidationError(
                    field=field_name,
                    type=ValidationType.TYPE,
                    message=f"Field '{field_name}' must be a list",
                    value=value
                )
        # 特殊处理dict类型
        elif expected_type == dict:
            if not isinstance(value, dict):
                return ValidationError(
                    field=field_name,
                    type=ValidationType.TYPE,
                    message=f"Field '{field_name}' must be a dict",
                    value=value
                )
        # 基本类型检查
        elif not isinstance(value, expected_type):
            # 尝试类型转换
            try:
                if expected_type == int:
                    int(value)
                elif expected_type == float:
                    float(value)
                elif expected_type == bool:
                    if isinstance(value, str):
                        value.lower() in ('true', '1', 'yes')
                elif expected_type == str:
                    str(value)
                else:
                    raise ValueError()
            except (ValueError, TypeError):
                return ValidationError(
                    field=field_name,
                    type=ValidationType.TYPE,
                    message=f"Field '{field_name}' must be of type {expected_type.__name__}",
                    value=value
                )
        
        return None
    
    def _check_constraints(
        self,
        field_name: str,
        value: Any,
        rule: FieldRule
    ) -> List[ValidationError]:
        """
        检查约束
        
        Args:
            field_name: 字段名
            value: 值
            rule: 规则
        
        Returns:
            错误列表
        """
        errors = []
        
        # 数值约束
        if isinstance(value, (int, float)):
            if rule.min_value is not None and value < rule.min_value:
                errors.append(ValidationError(
                    field=field_name,
                    type=ValidationType.MIN,
                    message=f"Field '{field_name}' must be >= {rule.min_value}",
                    value=value
                ))
            
            if rule.max_value is not None and value > rule.max_value:
                errors.append(ValidationError(
                    field=field_name,
                    type=ValidationType.MAX,
                    message=f"Field '{field_name}' must be <= {rule.max_value}",
                    value=value
                ))
        
        # 字符串长度约束
        if isinstance(value, (str, list)):
            length = len(value)
            
            if rule.min_length is not None and length < rule.min_length:
                errors.append(ValidationError(
                    field=field_name,
                    type=ValidationType.MIN_LENGTH,
                    message=f"Field '{field_name}' length must be >= {rule.min_length}",
                    value=value
                ))
            
            if rule.max_length is not None and length > rule.max_length:
                errors.append(ValidationError(
                    field=field_name,
                    type=ValidationType.MAX_LENGTH,
                    message=f"Field '{field_name}' length must be <= {rule.max_length}",
                    value=value
                ))
        
        # 正则模式
        if rule.pattern and isinstance(value, str):
            if not re.match(rule.pattern, value):
                errors.append(ValidationError(
                    field=field_name,
                    type=ValidationType.PATTERN,
                    message=f"Field '{field_name}' does not match pattern {rule.pattern}",
                    value=value
                ))
        
        # 选择约束
        if rule.choices and value not in rule.choices:
            errors.append(ValidationError(
                field=field_name,
                type=ValidationType.CHOICE,
                message=f"Field '{field_name}' must be one of {rule.choices}",
                value=value
            ))
        
        # 自定义验证器
        if rule.custom_validator:
            try:
                custom_result = rule.custom_validator(value)
                if custom_result is not True:
                    message = custom_result if isinstance(custom_result, str) else "Validation failed"
                    errors.append(ValidationError(
                        field=field_name,
                        type=ValidationType.CUSTOM,
                        message=message,
                        value=value
                    ))
            except Exception as e:
                errors.append(ValidationError(
                    field=field_name,
                    type=ValidationType.CUSTOM,
                    message=str(e),
                    value=value
                ))
        
        # 嵌套对象验证
        if rule.nested and isinstance(value, dict):
            nested_validator = ApiValidator()
            nested_validator._rules = rule.nested
            nested_result = nested_validator.validate(value)
            if not nested_result.valid:
                for error in nested_result.errors:
                    errors.append(ValidationError(
                        field=f"{field_name}.{error.field}",
                        type=error.type,
                        message=error.message,
                        value=error.value
                    ))
        
        # 数组元素验证
        if rule.item_rule and isinstance(value, list):
            for i, item in enumerate(value):
                item_validator = ApiValidator()
                item_validator._rules = {'item': rule.item_rule}
                item_result = item_validator.validate({'item': item})
                if not item_result.valid:
                    for error in item_result.errors:
                        errors.append(ValidationError(
                            field=f"{field_name}[{i}]",
                            type=error.type,
                            message=error.message,
                            value=error.value
                        ))
        
        return errors
    
    @staticmethod
    def _validate_email(value: str) -> Union[bool, str]:
        """验证邮箱"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if re.match(pattern, value):
            return True
        return "Invalid email format"
    
    @staticmethod
    def _validate_url(value: str) -> Union[bool, str]:
        """验证URL"""
        pattern = r'^https?://[^\s/$.?#].[^\s]*$'
        if re.match(pattern, value):
            return True
        return "Invalid URL format"
    
    @staticmethod
    def _validate_date(value: str) -> Union[bool, str]:
        """验证日期"""
        try:
            datetime.fromisoformat(value.replace('Z', '+00:00'))
            return True
        except ValueError:
            return "Invalid date format (expected ISO 8601)"
    
    @staticmethod
    def _validate_uuid(value: str) -> Union[bool, str]:
        """验证UUID"""
        pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        if re.match(pattern, value.lower()):
            return True
        return "Invalid UUID format"
    
    def register_custom_validator(
        self,
        name: str,
        validator: Callable
    ) -> None:
        """
        注册自定义验证器
        
        Args:
            name: 验证器名称
            validator: 验证函数
        """
        with self._lock:
            self._custom_validators[name] = validator


# 规则构建器
class RuleBuilder:
    """
    规则构建器
    
    提供流式API构建验证规则
    """
    
    def __init__(self, name: str):
        self._rule = FieldRule(name=name)
    
    def type(self, type_class: Type) -> 'RuleBuilder':
        """设置类型"""
        self._rule.type = type_class
        return self
    
    def required(self, required: bool = True) -> 'RuleBuilder':
        """设置是否必需"""
        self._rule.required = required
        return self
    
    def optional(self) -> 'RuleBuilder':
        """设置为可选"""
        self._rule.required = False
        return self
    
    def default(self, value: Any) -> 'RuleBuilder':
        """设置默认值"""
        self._rule.default = value
        return self
    
    def min(self, value: Union[int, float]) -> 'RuleBuilder':
        """设置最小值"""
        self._rule.min_value = value
        return self
    
    def max(self, value: Union[int, float]) -> 'RuleBuilder':
        """设置最大值"""
        self._rule.max_value = value
        return self
    
    def min_length(self, length: int) -> 'RuleBuilder':
        """设置最小长度"""
        self._rule.min_length = length
        return self
    
    def max_length(self, length: int) -> 'RuleBuilder':
        """设置最大长度"""
        self._rule.max_length = length
        return self
    
    def pattern(self, regex: str) -> 'RuleBuilder':
        """设置正则模式"""
        self._rule.pattern = regex
        return self
    
    def choices(self, choices: List[Any]) -> 'RuleBuilder':
        """设置可选值"""
        self._rule.choices = choices
        return self
    
    def custom(self, validator: Callable) -> 'RuleBuilder':
        """设置自定义验证器"""
        self._rule.custom_validator = validator
        return self
    
    def email(self) -> 'RuleBuilder':
        """设置为邮箱验证"""
        self._rule.custom_validator = ApiValidator._validate_email
        return self
    
    def url(self) -> 'RuleBuilder':
        """设置为URL验证"""
        self._rule.custom_validator = ApiValidator._validate_url
        return self
    
    def description(self, desc: str) -> 'RuleBuilder':
        """设置描述"""
        self._rule.description = desc
        return self
    
    def nested(self, rules: Dict[str, FieldRule]) -> 'RuleBuilder':
        """设置嵌套规则"""
        self._rule.nested = rules
        return self
    
    def items(self, rule: FieldRule) -> 'RuleBuilder':
        """设置数组元素规则"""
        self._rule.item_rule = rule
        return self
    
    def build(self) -> FieldRule:
        """构建规则"""
        return self._rule


def field(name: str) -> RuleBuilder:
    """
    创建字段规则构建器
    
    Args:
        name: 字段名称
    
    Returns:
        规则构建器
    """
    return RuleBuilder(name)


# 全局验证器
_api_validator: Optional[ApiValidator] = None
_validator_lock = threading.Lock()


def get_api_validator() -> ApiValidator:
    """获取全局验证器"""
    global _api_validator
    if _api_validator is None:
        with _validator_lock:
            if _api_validator is None:
                _api_validator = ApiValidator()
    return _api_validator
