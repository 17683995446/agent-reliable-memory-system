"""
API序列化器

第314阶段：响应序列化、字段映射、嵌套对象
遵循"图难于其易，为大于其细"原则，实现细粒度的数据序列化
"""

import threading
from typing import Dict, List, Optional, Any, Callable, Type, Union
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import json


class SerializeFormat(Enum):
    """序列化格式"""
    JSON = "json"
    DICT = "dict"
    XML = "xml"


@dataclass
class FieldConfig:
    """字段配置"""
    source: str                           # 源字段名
    target: Optional[str] = None          # 目标字段名
    required: bool = False
    default: Any = None
    serializer: Optional[Callable] = None  # 自定义序列化函数
    exclude: bool = False                  # 是否排除
    many: bool = False                     # 是否是列表
    nested: Optional[str] = None           # 嵌套序列化器名称


class ApiSerializer:
    """
    API序列化器基类
    
    职责：
    1. 响应数据序列化
    2. 字段映射和转换
    3. 嵌套对象处理
    4. 数据过滤
    
    设计原则：
    - 细粒度字段控制
    - 可扩展的序列化器
    - 支持嵌套和列表
    """
    
    # 序列化器名称
    name: str = "base"
    
    # 字段配置
    fields: Dict[str, FieldConfig] = {}
    
    # 排除的字段
    exclude_fields: List[str] = []
    
    # 只包含的字段
    only_fields: Optional[List[str]] = None
    
    def __init__(self):
        self._lock = threading.RLock()
        self._nested_serializers: Dict[str, 'ApiSerializer'] = {}
    
    def register_nested(
        self,
        name: str,
        serializer: 'ApiSerializer'
    ) -> None:
        """
        注册嵌套序列化器
        
        Args:
            name: 序列化器名称
            serializer: 序列化器实例
        """
        with self._lock:
            self._nested_serializers[name] = serializer
    
    def get_field_config(self, field_name: str) -> Optional[FieldConfig]:
        """
        获取字段配置
        
        Args:
            field_name: 字段名
        
        Returns:
            字段配置
        """
        return self.fields.get(field_name)
    
    def serialize_field(
        self,
        field_name: str,
        value: Any,
        config: Optional[FieldConfig] = None
    ) -> Any:
        """
        序列化单个字段
        
        Args:
            field_name: 字段名
            value: 值
            config: 字段配置
        
        Returns:
            序列化后的值
        """
        config = config or self.get_field_config(field_name)
        
        # 处理None值
        if value is None:
            if config and config.default is not None:
                return config.default
            return None
        
        # 自定义序列化器
        if config and config.serializer:
            return config.serializer(value)
        
        # 嵌套序列化器
        if config and config.nested:
            nested_serializer = self._nested_serializers.get(config.nested)
            if nested_serializer:
                if config.many and isinstance(value, list):
                    return [nested_serializer.serialize(item) for item in value]
                return nested_serializer.serialize(value)
        
        # 默认处理
        return self._default_serialize(value)
    
    def _default_serialize(self, value: Any) -> Any:
        """
        默认序列化处理
        
        Args:
            value: 值
        
        Returns:
            序列化后的值
        """
        if isinstance(value, datetime):
            return value.isoformat()
        
        if hasattr(value, '__dict__'):
            return {
                k: self._default_serialize(v)
                for k, v in value.__dict__.items()
                if not k.startswith('_')
            }
        
        if isinstance(value, (list, tuple)):
            return [self._default_serialize(item) for item in value]
        
        if isinstance(value, dict):
            return {
                k: self._default_serialize(v)
                for k, v in value.items()
            }
        
        return value
    
    def serialize(
        self,
        data: Any,
        many: bool = False,
        context: Optional[Dict[str, Any]] = None
    ) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """
        序列化数据
        
        Args:
            data: 待序列化数据
            many: 是否是列表
            context: 上下文数据
        
        Returns:
            序列化后的数据
        """
        if many:
            if not isinstance(data, (list, tuple)):
                data = [data] if data else []
            return [self._serialize_single(item, context) for item in data]
        
        return self._serialize_single(data, context)
    
    def _serialize_single(
        self,
        data: Any,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        序列化单个对象
        
        Args:
            data: 数据对象
            context: 上下文
        
        Returns:
            序列化后的字典
        """
        result = {}
        context = context or {}
        
        # 获取源数据字典
        if isinstance(data, dict):
            source_data = data
        elif hasattr(data, '__dict__'):
            source_data = data.__dict__
        else:
            source_data = {'value': data}
        
        # 确定要序列化的字段
        if self.only_fields:
            fields_to_serialize = {
                k: v for k, v in self.fields.items()
                if k in self.only_fields
            }
        else:
            fields_to_serialize = self.fields
        
        # 序列化每个字段
        for target_name, config in fields_to_serialize.items():
            if config.exclude or target_name in self.exclude_fields:
                continue
            
            source_name = config.source
            value = source_data.get(source_name)
            
            # 检查必需字段
            if config.required and value is None:
                if config.default is not None:
                    value = config.default
                else:
                    continue
            
            # 序列化字段
            serialized_value = self.serialize_field(source_name, value, config)
            
            # 使用目标名称
            output_name = config.target or target_name
            result[output_name] = serialized_value
        
        # 如果没有字段配置，返回所有字段
        if not self.fields:
            for key, value in source_data.items():
                if key.startswith('_') or key in self.exclude_fields:
                    continue
                result[key] = self._default_serialize(value)
        
        return result
    
    def to_json(
        self,
        data: Any,
        many: bool = False,
        indent: Optional[int] = None
    ) -> str:
        """
        转换为JSON字符串
        
        Args:
            data: 数据
            many: 是否是列表
            indent: 缩进
        
        Returns:
            JSON字符串
        """
        serialized = self.serialize(data, many)
        return json.dumps(serialized, ensure_ascii=False, indent=indent, default=str)


class ModelSerializer(ApiSerializer):
    """
    模型序列化器
    
    用于序列化数据库模型或数据类
    """
    
    # 模型类
    model: Optional[Type] = None
    
    def serialize(
        self,
        data: Any,
        many: bool = False,
        context: Optional[Dict[str, Any]] = None
    ) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """
        序列化模型数据
        
        Args:
            data: 模型实例或查询结果
            many: 是否是列表
            context: 上下文
        
        Returns:
            序列化后的数据
        """
        # 处理查询结果
        if hasattr(data, '__iter__') and not isinstance(data, (dict, str)):
            if not many:
                # 可能是查询结果集
                data_list = list(data)
                if len(data_list) == 1:
                    data = data_list[0]
                else:
                    many = True
                    data = data_list
        
        return super().serialize(data, many, context)


# 序列化器注册表
_serializers: Dict[str, Type[ApiSerializer]] = {}
_serializers_lock = threading.Lock()


def register_serializer(name: str, serializer_class: Type[ApiSerializer]) -> None:
    """
    注册序列化器
    
    Args:
        name: 序列化器名称
        serializer_class: 序列化器类
    """
    with _serializers_lock:
        _serializers[name] = serializer_class


def get_serializer(name: str) -> Optional[Type[ApiSerializer]]:
    """
    获取序列化器类
    
    Args:
        name: 序列化器名称
    
    Returns:
        序列化器类
    """
    with _serializers_lock:
        return _serializers.get(name)


def get_all_serializers() -> Dict[str, Type[ApiSerializer]]:
    """获取所有序列化器"""
    with _serializers_lock:
        return dict(_serializers)


# 字段配置构建器
class FieldBuilder:
    """
    字段配置构建器
    
    提供流式API构建字段配置
    """
    
    def __init__(self, source: str):
        self._config = FieldConfig(source=source)
    
    def target(self, name: str) -> 'FieldBuilder':
        """设置目标字段名"""
        self._config.target = name
        return self
    
    def required(self, required: bool = True) -> 'FieldBuilder':
        """设置是否必需"""
        self._config.required = required
        return self
    
    def default(self, value: Any) -> 'FieldBuilder':
        """设置默认值"""
        self._config.default = value
        return self
    
    def serialize(self, func: Callable) -> 'FieldBuilder':
        """设置序列化函数"""
        self._config.serializer = func
        return self
    
    def exclude(self, exclude: bool = True) -> 'FieldBuilder':
        """设置是否排除"""
        self._config.exclude = exclude
        return self
    
    def many(self, many: bool = True) -> 'FieldBuilder':
        """设置是否是列表"""
        self._config.many = many
        return self
    
    def nested(self, serializer_name: str) -> 'FieldBuilder':
        """设置嵌套序列化器"""
        self._config.nested = serializer_name
        return self
    
    def build(self) -> FieldConfig:
        """构建字段配置"""
        return self._config


def field_config(source: str) -> FieldBuilder:
    """
    创建字段配置构建器
    
    Args:
        source: 源字段名
    
    Returns:
        字段配置构建器
    """
    return FieldBuilder(source)


# 常用序列化函数
def serialize_datetime(value: datetime) -> str:
    """序列化日期时间"""
    return value.isoformat()


def serialize_timestamp(value: Union[int, float]) -> str:
    """序列化时间戳"""
    return datetime.fromtimestamp(value).isoformat()


def serialize_boolean(value: Any) -> bool:
    """序列化布尔值"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ('true', '1', 'yes')
    return bool(value)


def serialize_integer(value: Any) -> int:
    """序列化整数"""
    return int(value)


def serialize_float(value: Any) -> float:
    """序列化浮点数"""
    return float(value)


def serialize_string(value: Any) -> str:
    """序列化字符串"""
    return str(value)
