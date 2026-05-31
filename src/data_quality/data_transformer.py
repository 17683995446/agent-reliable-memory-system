#!/usr/bin/env python3
"""
数据转换器 (DataTransformer) - 阶段353

职责：
- 格式转换：JSON/YAML/CSV/XML互转
- 编码转换：字符编码处理
- 字段映射：字段重命名、结构变换
- 类型转换：数据类型转换
- 批量转换：高效批量处理

设计原则：
- 确定性规则，无模型依赖
- 线程安全（RLock）
- 最小层级，无循环依赖
"""

import base64
import csv
import io
import json
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


# ============================================================
# 枚举与数据结构
# ============================================================

class FormatType(Enum):
    """数据格式"""
    JSON = "json"
    YAML = "yaml"
    CSV = "csv"
    XML = "xml"
    DICT = "dict"
    TEXT = "text"


class EncodingType(Enum):
    """编码类型"""
    UTF8 = "utf-8"
    UTF16 = "utf-16"
    GBK = "gbk"
    GB2312 = "gb2312"
    LATIN1 = "latin-1"
    ASCII = "ascii"
    BASE64 = "base64"


@dataclass
class TransformStats:
    """转换统计"""
    total_records: int = 0
    transformed_records: int = 0
    failed_records: int = 0
    fields_mapped: int = 0
    types_converted: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_records": self.total_records,
            "transformed_records": self.transformed_records,
            "failed_records": self.failed_records,
            "fields_mapped": self.fields_mapped,
            "types_converted": self.types_converted,
        }


@dataclass
class TransformResult:
    """转换结果"""
    data: Any
    stats: TransformStats
    errors: List[Tuple[int, str]] = field(default_factory=list)  # (index, error_msg)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stats": self.stats.to_dict(),
            "errors": self.errors,
            "error_count": len(self.errors),
        }


# ============================================================
# 格式转换器
# ============================================================

class FormatConverter:
    """格式转换器"""

    @staticmethod
    def to_json(data: Any, indent: int = 2, ensure_ascii: bool = False) -> str:
        """转换为JSON字符串"""
        return json.dumps(data, indent=indent, ensure_ascii=ensure_ascii, default=str)

    @staticmethod
    def from_json(text: str) -> Any:
        """从JSON解析"""
        return json.loads(text)

    @staticmethod
    def to_yaml(data: Any) -> str:
        """转换为YAML字符串"""
        if not YAML_AVAILABLE:
            raise ImportError("PyYAML not installed")
        return yaml.dump(data, allow_unicode=True, default_flow_style=False)

    @staticmethod
    def from_yaml(text: str) -> Any:
        """从YAML解析"""
        if not YAML_AVAILABLE:
            raise ImportError("PyYAML not installed")
        return yaml.safe_load(text)

    @staticmethod
    def to_csv(data: List[Dict[str, Any]],
               fields: Optional[List[str]] = None,
               delimiter: str = ",") -> str:
        """转换为CSV字符串"""
        if not data:
            return ""

        if fields is None:
            fields = list(data[0].keys())

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fields, delimiter=delimiter,
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data)

        return output.getvalue()

    @staticmethod
    def from_csv(text: str, delimiter: str = ",") -> List[Dict[str, str]]:
        """从CSV解析"""
        output = io.StringIO(text)
        reader = csv.DictReader(output, delimiter=delimiter)
        return list(reader)

    @staticmethod
    def to_xml(data: Dict[str, Any], root: str = "root") -> str:
        """转换为XML字符串（简单实现）"""
        def dict_to_xml(d: Any, parent: str) -> str:
            if isinstance(d, dict):
                elements = []
                for k, v in d.items():
                    elements.append(dict_to_xml(v, k))
                return f"<{parent}>{''.join(elements)}</{parent}>"
            elif isinstance(d, list):
                elements = [dict_to_xml(item, "item") for item in d]
                return f"<{parent}>{''.join(elements)}</{parent}>"
            else:
                escaped = str(d).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                return f"<{parent}>{escaped}</{parent}>"

        return f'<?xml version="1.0" encoding="UTF-8"?>{dict_to_xml(data, root)}'

    @staticmethod
    def to_text(data: Any, separator: str = "\n") -> str:
        """转换为文本"""
        if isinstance(data, dict):
            return separator.join(f"{k}: {v}" for k, v in data.items())
        elif isinstance(data, list):
            return separator.join(str(item) for item in data)
        return str(data)


# ============================================================
# 编码转换器
# ============================================================

class EncodingConverter:
    """编码转换器"""

    @staticmethod
    def encode(text: str, encoding: EncodingType) -> bytes:
        """编码字符串"""
        if encoding == EncodingType.BASE64:
            return base64.b64encode(text.encode("utf-8"))
        return text.encode(encoding.value)

    @staticmethod
    def decode(data: bytes, encoding: EncodingType) -> str:
        """解码字节"""
        if encoding == EncodingType.BASE64:
            return base64.b64decode(data).decode("utf-8")
        return data.decode(encoding.value)

    @staticmethod
    def convert_encoding(text: str,
                         from_encoding: EncodingType,
                         to_encoding: EncodingType) -> str:
        """转换编码"""
        if from_encoding == to_encoding:
            return text
        # 先编码再解码
        encoded = EncodingConverter.encode(text, from_encoding)
        return EncodingConverter.decode(encoded, to_encoding)

    @staticmethod
    def detect_encoding(data: bytes) -> Optional[str]:
        """检测编码（简单实现）"""
        # 尝试常见编码
        for encoding in ["utf-8", "gbk", "gb2312", "latin-1"]:
            try:
                data.decode(encoding)
                return encoding
            except (UnicodeDecodeError, LookupError):
                continue
        return None


# ============================================================
# 字段映射器
# ============================================================

class FieldMapper:
    """字段映射器"""

    @staticmethod
    def rename_fields(data: Dict[str, Any],
                      mapping: Dict[str, str]) -> Dict[str, Any]:
        """重命名字段"""
        result = {}
        for old_key, value in data.items():
            new_key = mapping.get(old_key, old_key)
            result[new_key] = value
        return result

    @staticmethod
    def select_fields(data: Dict[str, Any],
                      fields: List[str]) -> Dict[str, Any]:
        """选择字段"""
        return {k: data.get(k) for k in fields if k in data}

    @staticmethod
    def exclude_fields(data: Dict[str, Any],
                       fields: List[str]) -> Dict[str, Any]:
        """排除字段"""
        exclude_set = set(fields)
        return {k: v for k, v in data.items() if k not in exclude_set}

    @staticmethod
    def flatten(data: Dict[str, Any],
                separator: str = ".",
                prefix: str = "") -> Dict[str, Any]:
        """扁平化嵌套字典"""
        result = {}
        for key, value in data.items():
            new_key = f"{prefix}{separator}{key}" if prefix else key
            if isinstance(value, dict):
                result.update(FieldMapper.flatten(value, separator, new_key))
            else:
                result[new_key] = value
        return result

    @staticmethod
    def unflatten(data: Dict[str, Any],
                  separator: str = ".") -> Dict[str, Any]:
        """反扁平化"""
        result = {}
        for key, value in data.items():
            parts = key.split(separator)
            current = result
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = value
        return result

    @staticmethod
    def apply_mapping(data: Dict[str, Any],
                      mapping: Dict[str, Callable[[Any], Any]]) -> Dict[str, Any]:
        """应用字段映射函数"""
        result = data.copy()
        for field, func in mapping.items():
            if field in result:
                try:
                    result[field] = func(result[field])
                except Exception:
                    pass
        return result


# ============================================================
# 类型转换器
# ============================================================

class TypeConverter:
    """类型转换器"""

    @staticmethod
    def to_string(value: Any) -> str:
        """转换为字符串"""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    @staticmethod
    def to_int(value: Any, default: int = 0) -> int:
        """转换为整数"""
        try:
            if isinstance(value, str):
                return int(float(value))
            return int(value)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def to_float(value: Any, default: float = 0.0) -> float:
        """转换为浮点数"""
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def to_bool(value: Any, default: bool = False) -> bool:
        """转换为布尔值"""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lower = value.lower().strip()
            if lower in ("true", "yes", "1", "on", "t", "y"):
                return True
            if lower in ("false", "no", "0", "off", "f", "n"):
                return False
        if isinstance(value, (int, float)):
            return bool(value)
        return default

    @staticmethod
    def to_list(value: Any, separator: str = ",") -> List[Any]:
        """转换为列表"""
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            return [v.strip() for v in value.split(separator) if v.strip()]
        if isinstance(value, (set, tuple)):
            return list(value)
        return [value]

    @staticmethod
    def to_dict(value: Any) -> Dict[str, Any]:
        """转换为字典"""
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass
        return {}

    @staticmethod
    def to_date(value: Any, fmt: str = "%Y-%m-%d",
                default: Optional[date] = None) -> Optional[date]:
        """转换为日期"""
        if isinstance(value, date):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                pass
        return default

    @staticmethod
    def to_datetime(value: Any, fmt: str = "%Y-%m-%d %H:%M:%S",
                    default: Optional[datetime] = None) -> Optional[datetime]:
        """转换为日期时间"""
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                pass
        return default


# ============================================================
# 数据转换器
# ============================================================

class DataTransformer:
    """
    数据转换器

    核心功能：
    1. 格式转换
    2. 编码转换
    3. 字段映射
    4. 类型转换
    5. 批量转换
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._custom_transformers: Dict[str, Callable[[Any], Any]] = {}

    # ---- 自定义转换器 ----

    def register_transformer(self, name: str,
                             func: Callable[[Any], Any]) -> None:
        """注册自定义转换函数"""
        with self._lock:
            self._custom_transformers[name] = func

    def apply_transformer(self, value: Any, name: str) -> Any:
        """应用自定义转换函数"""
        transformer = self._custom_transformers.get(name)
        if transformer:
            return transformer(value)
        return value

    # ---- 格式转换 ----

    def convert_format(self, data: Any,
                       from_format: FormatType,
                       to_format: FormatType,
                       **kwargs) -> TransformResult:
        """格式转换"""
        stats = TransformStats(total_records=1)
        errors = []

        try:
            # 先转换为字典
            if from_format == FormatType.JSON:
                if isinstance(data, str):
                    data = FormatConverter.from_json(data)
            elif from_format == FormatType.YAML:
                if isinstance(data, str):
                    data = FormatConverter.from_yaml(data)
            elif from_format == FormatType.CSV:
                if isinstance(data, str):
                    data = FormatConverter.from_csv(data)
            elif from_format == FormatType.DICT:
                pass  # 已经是字典

            # 再转换为目标格式
            if to_format == FormatType.JSON:
                result = FormatConverter.to_json(data, **kwargs)
            elif to_format == FormatType.YAML:
                result = FormatConverter.to_yaml(data)
            elif to_format == FormatType.CSV:
                result = FormatConverter.to_csv(data, **kwargs)
            elif to_format == FormatType.XML:
                result = FormatConverter.to_xml(data, **kwargs)
            elif to_format == FormatType.TEXT:
                result = FormatConverter.to_text(data, **kwargs)
            elif to_format == FormatType.DICT:
                result = data
            else:
                result = data

            stats.transformed_records = 1
            return TransformResult(data=result, stats=stats, errors=errors)

        except Exception as e:
            errors.append((0, str(e)))
            stats.failed_records = 1
            return TransformResult(data=None, stats=stats, errors=errors)

    # ---- 编码转换 ----

    def convert_encoding(self, text: str,
                         from_encoding: EncodingType,
                         to_encoding: EncodingType) -> TransformResult:
        """编码转换"""
        stats = TransformStats(total_records=1)
        try:
            result = EncodingConverter.convert_encoding(text, from_encoding, to_encoding)
            stats.transformed_records = 1
            return TransformResult(data=result, stats=stats)
        except Exception as e:
            stats.failed_records = 1
            return TransformResult(data=None, stats=stats, errors=[(0, str(e))])

    # ---- 字段映射 ----

    def map_fields(self, data: Union[Dict[str, Any], List[Dict[str, Any]]],
                   mapping: Dict[str, str]) -> TransformResult:
        """字段映射（重命名）"""
        stats = TransformStats()
        errors = []

        if isinstance(data, dict):
            result = FieldMapper.rename_fields(data, mapping)
            stats.total_records = 1
            stats.transformed_records = 1
            stats.fields_mapped = len([k for k in mapping if k in data])
        elif isinstance(data, list):
            result = []
            stats.total_records = len(data)
            for i, record in enumerate(data):
                if isinstance(record, dict):
                    result.append(FieldMapper.rename_fields(record, mapping))
                    stats.fields_mapped += len([k for k in mapping if k in record])
                else:
                    result.append(record)
                    errors.append((i, "Not a dictionary"))
            stats.transformed_records = len(result) - len(errors)
            stats.failed_records = len(errors)
        else:
            result = data
            stats.total_records = 1

        return TransformResult(data=result, stats=stats, errors=errors)

    def select_fields(self, data: Union[Dict[str, Any], List[Dict[str, Any]]],
                      fields: List[str]) -> TransformResult:
        """选择字段"""
        stats = TransformStats()
        errors = []

        if isinstance(data, dict):
            result = FieldMapper.select_fields(data, fields)
            stats.total_records = 1
            stats.transformed_records = 1
        elif isinstance(data, list):
            result = [FieldMapper.select_fields(r, fields) if isinstance(r, dict) else r
                      for r in data]
            stats.total_records = len(data)
            stats.transformed_records = len(result)
        else:
            result = data
            stats.total_records = 1

        return TransformResult(data=result, stats=stats, errors=errors)

    def flatten_data(self, data: Dict[str, Any],
                     separator: str = ".") -> TransformResult:
        """扁平化数据"""
        stats = TransformStats(total_records=1, transformed_records=1)
        result = FieldMapper.flatten(data, separator)
        return TransformResult(data=result, stats=stats)

    def unflatten_data(self, data: Dict[str, Any],
                       separator: str = ".") -> TransformResult:
        """反扁平化数据"""
        stats = TransformStats(total_records=1, transformed_records=1)
        result = FieldMapper.unflatten(data, separator)
        return TransformResult(data=result, stats=stats)

    # ---- 类型转换 ----

    def convert_field_type(self, data: Union[Dict[str, Any], List[Dict[str, Any]]],
                           field: str,
                           target_type: str,
                           **kwargs) -> TransformResult:
        """转换字段类型"""
        stats = TransformStats()
        errors = []

        converters = {
            "string": TypeConverter.to_string,
            "int": lambda v: TypeConverter.to_int(v, kwargs.get("default", 0)),
            "float": lambda v: TypeConverter.to_float(v, kwargs.get("default", 0.0)),
            "bool": lambda v: TypeConverter.to_bool(v, kwargs.get("default", False)),
            "list": lambda v: TypeConverter.to_list(v, kwargs.get("separator", ",")),
            "dict": TypeConverter.to_dict,
            "date": lambda v: TypeConverter.to_date(v, kwargs.get("fmt", "%Y-%m-%d")),
            "datetime": lambda v: TypeConverter.to_datetime(v, kwargs.get("fmt", "%Y-%m-%d %H:%M:%S")),
        }

        converter = converters.get(target_type)
        if converter is None:
            return TransformResult(data=data, stats=stats,
                                   errors=[(0, f"Unknown type: {target_type}")])

        if isinstance(data, dict):
            result = data.copy()
            if field in result:
                result[field] = converter(result[field])
                stats.types_converted = 1
            stats.total_records = 1
            stats.transformed_records = 1
        elif isinstance(data, list):
            result = []
            stats.total_records = len(data)
            for i, record in enumerate(data):
                if isinstance(record, dict) and field in record:
                    new_record = record.copy()
                    try:
                        new_record[field] = converter(record[field])
                        stats.types_converted += 1
                    except Exception as e:
                        errors.append((i, str(e)))
                    result.append(new_record)
                else:
                    result.append(record)
            stats.transformed_records = len(result)
            stats.failed_records = len(errors)
        else:
            result = data
            stats.total_records = 1

        return TransformResult(data=result, stats=stats, errors=errors)

    # ---- 批量转换 ----

    def transform_batch(self, data: List[Dict[str, Any]],
                        operations: List[Dict[str, Any]]) -> TransformResult:
        """
        批量执行转换操作

        Args:
            data: 数据列表
            operations: 操作列表

        Returns:
            转换结果
        """
        current_data = data
        total_stats = TransformStats(total_records=len(data))
        all_errors = []

        for op in operations:
            op_type = op.get("type")

            if op_type == "map":
                result = self.map_fields(current_data, op.get("mapping", {}))
            elif op_type == "select":
                result = self.select_fields(current_data, op.get("fields", []))
            elif op_type == "convert":
                result = self.convert_field_type(
                    current_data,
                    field=op.get("field"),
                    target_type=op.get("target_type"),
                    **op.get("kwargs", {})
                )
            elif op_type == "flatten":
                if isinstance(current_data, list):
                    current_data = [FieldMapper.flatten(r, op.get("separator", "."))
                                    if isinstance(r, dict) else r for r in current_data]
                    result = TransformResult(data=current_data,
                                             stats=TransformStats(transformed_records=len(current_data)))
                else:
                    result = self.flatten_data(current_data, op.get("separator", "."))
            else:
                continue

            current_data = result.data
            all_errors.extend(result.errors)
            total_stats.fields_mapped += result.stats.fields_mapped
            total_stats.types_converted += result.stats.types_converted

        total_stats.transformed_records = len(current_data) if isinstance(current_data, list) else 1
        total_stats.failed_records = len(all_errors)

        return TransformResult(data=current_data, stats=total_stats, errors=all_errors)

    # ---- 统计 ----

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                "custom_transformers": len(self._custom_transformers),
                "transformer_names": list(self._custom_transformers.keys()),
            }


# ============================================================
# 全局单例
# ============================================================

_transformer: Optional[DataTransformer] = None
_t_lock = threading.RLock()


def get_data_transformer() -> DataTransformer:
    """获取全局数据转换器"""
    global _transformer
    if _transformer is None:
        with _t_lock:
            if _transformer is None:
                _transformer = DataTransformer()
    return _transformer
