#!/usr/bin/env python3
"""
配置加载器 (ConfigLoader) - 阶段326

职责：
- 多源配置加载：JSON、YAML、环境变量、Python字典
- 格式自动检测与解析
- 多源合并策略（深度合并、覆盖、追加）
- 配置引用解析（${var}、${section.key}）
- 加载优先级管理

设计原则：
- 确定性规则，无模型依赖
- 线程安全（RLock）
- 最小层级，无循环依赖
"""

import json
import os
import re
import threading
import time
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union


# ============================================================
# 枚举与数据结构
# ============================================================

class ConfigFormat(Enum):
    """配置文件格式"""
    JSON = "json"
    YAML = "yaml"
    ENV = "env"
    DICT = "dict"
    INI = "ini"
    TOML = "toml"
    AUTO = "auto"


class MergeStrategy(Enum):
    """合并策略"""
    DEEP = "deep"       # 深度合并（递归合并嵌套字典）
    SHALLOW = "shallow" # 浅合并（顶层覆盖）
    APPEND = "append"   # 追加（列表追加，字典合并）


class ConfigSource(Enum):
    """配置来源"""
    FILE = "file"           # 文件
    ENVIRONMENT = "env"     # 环境变量
    DICTIONARY = "dict"     # Python字典
    DEFAULT = "default"     # 默认值
    REMOTE = "remote"       # 远程配置


@dataclass
class LoadResult:
    """加载结果"""
    success: bool
    source: str = ""
    format: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    duration_ms: float = 0.0
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


@dataclass
class SourceConfig:
    """配置源定义"""
    name: str
    source_type: ConfigSource
    path: str = ""
    format: ConfigFormat = ConfigFormat.AUTO
    priority: int = 100
    enabled: bool = True
    prefix: str = ""          # 环境变量前缀
    encoding: str = "utf-8"
    required: bool = False    # 是否必须加载成功
    metadata: Dict[str, Any] = field(default_factory=dict)


# ============================================================
# 配置加载器
# ============================================================

class ConfigLoader:
    """
    配置加载器

    核心功能：
    1. 从多种来源加载配置（文件、环境变量、字典）
    2. 自动检测配置格式
    3. 多源配置合并
    4. 变量引用解析（${var}）
    5. 加载优先级管理
    """

    def __init__(self):
        self._sources: Dict[str, SourceConfig] = {}
        self._loaded_data: Dict[str, Dict[str, Any]] = {}
        self._merged: Dict[str, Any] = {}
        self._lock = threading.RLock()
        self._load_hooks: List[Callable[[LoadResult], None]] = []
        self._reference_pattern = re.compile(r'\$\{([^}]+)\}')

    # ---- 配置源管理 ----

    def add_source(self, config: SourceConfig) -> bool:
        """
        添加配置源

        Args:
            config: 配置源定义

        Returns:
            是否添加成功
        """
        with self._lock:
            if config.name in self._sources:
                return False
            self._sources[config.name] = config
            return True

    def remove_source(self, name: str) -> bool:
        """移除配置源"""
        with self._lock:
            if name not in self._sources:
                return False
            del self._sources[name]
            self._loaded_data.pop(name, None)
            return True

    def get_source(self, name: str) -> Optional[SourceConfig]:
        """获取配置源"""
        with self._lock:
            return self._sources.get(name)

    def list_sources(self) -> List[Dict[str, Any]]:
        """列出所有配置源"""
        with self._lock:
            return [
                {
                    "name": s.name,
                    "type": s.source_type.value,
                    "path": s.path,
                    "format": s.format.value,
                    "priority": s.priority,
                    "enabled": s.enabled,
                    "required": s.required,
                }
                for s in self._sources.values()
            ]

    # ---- 加载 ----

    def load_source(self, name: str) -> LoadResult:
        """
        加载指定配置源

        Args:
            name: 配置源名称

        Returns:
            加载结果
        """
        start = time.monotonic()

        with self._lock:
            source = self._sources.get(name)
            if source is None:
                return LoadResult(False, name, error=f"Source '{name}' not found")

            if not source.enabled:
                return LoadResult(False, name, error=f"Source '{name}' is disabled")

        try:
            if source.source_type == ConfigSource.FILE:
                data = self._load_file(source)
            elif source.source_type == ConfigSource.ENVIRONMENT:
                data = self._load_env(source)
            elif source.source_type == ConfigSource.DICTIONARY:
                data = source.metadata.get("data", {})
            elif source.source_type == ConfigSource.DEFAULT:
                data = source.metadata.get("data", {})
            else:
                data = {}

            duration = (time.monotonic() - start) * 1000

            result = LoadResult(
                success=True,
                source=name,
                format=source.format.value,
                data=data,
                duration_ms=duration,
            )

            with self._lock:
                self._loaded_data[name] = data

            # 通知钩子
            for hook in self._load_hooks:
                try:
                    hook(result)
                except Exception:
                    pass

            return result

        except Exception as e:
            duration = (time.monotonic() - start) * 1000
            result = LoadResult(
                success=False,
                source=name,
                error=str(e),
                duration_ms=duration,
            )

            if source.required:
                raise RuntimeError(f"Required config source '{name}' failed: {e}") from e

            return result

    def load_all(self) -> Dict[str, LoadResult]:
        """
        按优先级加载所有配置源

        Returns:
            各配置源的加载结果
        """
        with self._lock:
            sources = sorted(
                [s for s in self._sources.values() if s.enabled],
                key=lambda s: s.priority
            )

        results = {}
        for source in sources:
            result = self.load_source(source.name)
            results[source.name] = result

        # 合并所有配置
        self._merge_all()

        return results

    def load_file(self, path: str, name: str = "", fmt: ConfigFormat = ConfigFormat.AUTO) -> LoadResult:
        """
        便捷方法：直接加载文件

        Args:
            path: 文件路径
            name: 配置源名称
            fmt: 文件格式

        Returns:
            加载结果
        """
        if not name:
            name = os.path.basename(path)

        detected_fmt = fmt if fmt != ConfigFormat.AUTO else self._detect_format(path)

        source = SourceConfig(
            name=name,
            source_type=ConfigSource.FILE,
            path=path,
            format=detected_fmt,
        )
        self.add_source(source)
        return self.load_source(name)

    def load_dict(self, data: Dict[str, Any], name: str = "dict") -> LoadResult:
        """
        便捷方法：直接加载字典

        Args:
            data: 配置字典
            name: 配置源名称

        Returns:
            加载结果
        """
        source = SourceConfig(
            name=name,
            source_type=ConfigSource.DICTIONARY,
            metadata={"data": data},
        )
        self.add_source(source)
        return self.load_source(name)

    # ---- 合并 ----

    def merge(
        self,
        base: Dict[str, Any],
        override: Dict[str, Any],
        strategy: MergeStrategy = MergeStrategy.DEEP
    ) -> Dict[str, Any]:
        """
        合并两个配置字典

        Args:
            base: 基础配置
            override: 覆盖配置
            strategy: 合并策略

        Returns:
            合并后的配置
        """
        if strategy == MergeStrategy.DEEP:
            return self._deep_merge(base, override)
        elif strategy == MergeStrategy.SHALLOW:
            result = dict(base)
            result.update(override)
            return result
        elif strategy == MergeStrategy.APPEND:
            return self._append_merge(base, override)
        return dict(base)

    def get_merged(self) -> Dict[str, Any]:
        """获取合并后的完整配置"""
        with self._lock:
            return deepcopy(self._merged)

    # ---- 变量引用 ----

    def resolve_references(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        解析配置中的变量引用

        支持 ${var} 和 ${section.key} 格式

        Args:
            config: 配置字典

        Returns:
            解析后的配置
        """
        return self._resolve_dict(config, config)

    # ---- 事件 ----

    def on_load(self, hook: Callable[[LoadResult], None]) -> None:
        """添加加载完成钩子"""
        with self._lock:
            self._load_hooks.append(hook)

    # ---- 统计 ----

    def get_stats(self) -> Dict[str, Any]:
        """获取加载器统计"""
        with self._lock:
            return {
                "total_sources": len(self._sources),
                "loaded_sources": len(self._loaded_data),
                "merged_keys": len(self._merged),
                "load_hooks": len(self._load_hooks),
            }

    # ---- 内部方法 ----

    def _load_file(self, source: SourceConfig) -> Dict[str, Any]:
        """从文件加载配置"""
        path = source.path
        if not os.path.exists(path):
            raise FileNotFoundError(f"Config file not found: {path}")

        fmt = source.format if source.format != ConfigFormat.AUTO else self._detect_format(path)

        with open(path, 'r', encoding=source.encoding) as f:
            raw = f.read()

        if fmt == ConfigFormat.JSON:
            return json.loads(raw)
        elif fmt == ConfigFormat.YAML:
            return self._parse_yaml(raw)
        elif fmt == ConfigFormat.INI:
            return self._parse_ini(raw)
        elif fmt == ConfigFormat.TOML:
            return self._parse_toml(raw)
        else:
            raise ValueError(f"Unsupported format: {fmt}")

    def _load_env(self, source: SourceConfig) -> Dict[str, Any]:
        """从环境变量加载配置"""
        prefix = source.prefix
        result = {}

        for key, value in os.environ.items():
            if prefix and not key.startswith(prefix):
                continue

            # 去掉前缀，转换为嵌套字典
            clean_key = key[len(prefix):] if prefix else key
            parts = clean_key.lower().split("_")

            current = result
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]

            # 尝试类型转换
            current[parts[-1]] = self._auto_convert(value)

        return result

    def _detect_format(self, path: str) -> ConfigFormat:
        """根据文件扩展名检测格式"""
        ext = os.path.splitext(path)[1].lower()
        format_map = {
            ".json": ConfigFormat.JSON,
            ".yaml": ConfigFormat.YAML,
            ".yml": ConfigFormat.YAML,
            ".ini": ConfigFormat.INI,
            ".toml": ConfigFormat.TOML,
        }
        return format_map.get(ext, ConfigFormat.JSON)

    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """深度合并两个字典"""
        result = deepcopy(base)

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = deepcopy(value)

        return result

    def _append_merge(self, base: Dict, override: Dict) -> Dict:
        """追加合并"""
        result = deepcopy(base)

        for key, value in override.items():
            if key in result:
                if isinstance(result[key], list) and isinstance(value, list):
                    result[key] = result[key] + value
                elif isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = self._deep_merge(result[key], value)
                else:
                    result[key] = value
            else:
                result[key] = deepcopy(value)

        return result

    def _merge_all(self) -> None:
        """按优先级合并所有已加载的配置"""
        with self._lock:
            sources = sorted(
                [s for s in self._sources.values() if s.enabled and s.name in self._loaded_data],
                key=lambda s: s.priority
            )

            merged = {}
            for source in sources:
                data = self._loaded_data.get(source.name, {})
                merged = self._deep_merge(merged, data)

            self._merged = merged

    def _resolve_dict(self, config: Dict, root: Dict) -> Dict:
        """递归解析字典中的变量引用"""
        result = {}
        for key, value in config.items():
            if isinstance(value, str):
                result[key] = self._resolve_string(value, root)
            elif isinstance(value, dict):
                result[key] = self._resolve_dict(value, root)
            elif isinstance(value, list):
                result[key] = [
                    self._resolve_string(item, root) if isinstance(item, str) else item
                    for item in value
                ]
            else:
                result[key] = value
        return result

    def _resolve_string(self, value: str, root: Dict) -> str:
        """解析字符串中的变量引用"""
        def replacer(match):
            ref = match.group(1)
            parts = ref.split(".")
            current = root
            for part in parts:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    # 回退到环境变量
                    return os.environ.get(ref, match.group(0))
            return str(current) if not isinstance(current, dict) else match.group(0)

        return self._reference_pattern.sub(replacer, value)

    def _auto_convert(self, value: str) -> Any:
        """自动转换环境变量值类型"""
        if value.lower() in ("true", "yes", "1"):
            return True
        if value.lower() in ("false", "no", "0"):
            return False
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass
        return value

    def _parse_yaml(self, raw: str) -> Dict:
        """解析YAML（简易实现，不依赖PyYAML）"""
        result = {}
        current_section = result
        current_path = []

        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            # 计算缩进
            indent = len(line) - len(line.lstrip())
            level = indent // 2

            # 调整当前路径
            while len(current_path) > level:
                current_path.pop()
            current = result
            for p in current_path:
                current = current.setdefault(p, {})

            # 解析键值对
            if ":" in stripped:
                key, _, val = stripped.partition(":")
                key = key.strip()
                val = val.strip()

                if val:
                    current[key] = self._auto_convert(val)
                else:
                    current[key] = {}
                    current_path.append(key)

        return result

    def _parse_ini(self, raw: str) -> Dict:
        """解析INI格式"""
        result = {}
        current_section = result

        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith(";"):
                continue

            if stripped.startswith("[") and stripped.endswith("]"):
                section_name = stripped[1:-1].strip()
                result[section_name] = {}
                current_section = result[section_name]
            elif "=" in stripped:
                key, _, val = stripped.partition("=")
                current_section[key.strip()] = self._auto_convert(val.strip())
            elif ":" in stripped:
                key, _, val = stripped.partition(":")
                current_section[key.strip()] = self._auto_convert(val.strip())

        return result

    def _parse_toml(self, raw: str) -> Dict:
        """解析TOML（简易实现）"""
        result = {}
        current_section = result

        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            if stripped.startswith("[") and not stripped.startswith("[["):
                section_name = stripped[1:-1].strip()
                parts = section_name.split(".")
                current = result
                for p in parts:
                    current = current.setdefault(p, {})
                current_section = current
            elif "=" in stripped:
                key, _, val = stripped.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                current_section[key] = self._auto_convert(val)

        return result


# ============================================================
# 全局单例
# ============================================================

_config_loader: Optional[ConfigLoader] = None
_loader_lock = threading.RLock()


def get_config_loader() -> ConfigLoader:
    """获取全局配置加载器（双重检查锁定）"""
    global _config_loader
    if _config_loader is None:
        with _loader_lock:
            if _config_loader is None:
                _config_loader = ConfigLoader()
    return _config_loader
