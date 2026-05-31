#!/usr/bin/env python3
"""
配置管理器 (ConfigManager) - 阶段330

职责：
- 统一管理：协调Loader、Validator、Watcher、Store
- 环境感知：dev/staging/prod环境自动切换
- 快照与回滚：配置快照保存与恢复
- 便捷API：简化常用操作
- 生命周期管理：初始化、加载、验证、运行、关闭

设计原则：
- 确定性规则，无模型依赖
- 线程安全（RLock）
- 最小层级，无循环依赖
- 编排层，不包含具体实现逻辑
"""

import json
import os
import threading
import time
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from config_system.config_loader import (
    ConfigLoader, ConfigFormat, ConfigSource, MergeStrategy,
    SourceConfig, LoadResult, get_config_loader
)
from config_system.config_validator import (
    ConfigValidator, SchemaBuilder, FieldType, ValidationResult,
    get_config_validator
)
from config_system.config_watcher import (
    ConfigWatcher, WatchConfig, ChangeEvent, ChangeType,
    WatcherState, get_config_watcher
)
from config_system.config_store import (
    ConfigStore, ConfigLayer, SensitivityLevel,
    get_config_store
)

# 哨兵值，用于区分"键不存在"和"值为None"
_SENTINEL = object()


# ============================================================
# 枚举与数据结构
# ============================================================

class Environment(Enum):
    """运行环境"""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


class ManagerState(Enum):
    """管理器状态"""
    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    READY = "ready"
    RUNNING = "running"
    ERROR = "error"
    SHUTDOWN = "shutdown"


@dataclass
class Snapshot:
    """配置快照"""
    id: str
    name: str
    data: Dict[str, Any]
    timestamp: float = 0.0
    environment: str = ""
    description: str = ""

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


@dataclass
class ManagerConfig:
    """管理器配置"""
    environment: Environment = Environment.DEVELOPMENT
    config_dir: str = "./config"
    watch_files: bool = True
    watch_interval: float = 3.0
    validate_on_load: bool = True
    auto_create_namespace: bool = True
    snapshot_on_start: bool = True
    max_snapshots: int = 10


# ============================================================
# 配置管理器
# ============================================================

class ConfigManager:
    """
    配置管理器（外观模式）

    统一协调 ConfigLoader、ConfigValidator、ConfigWatcher、ConfigStore
    提供高级别的配置管理接口。

    核心功能：
    1. 初始化：加载配置文件、设置环境
    2. 读取：统一读取接口，支持默认值和类型转换
    3. 写入：统一写入接口，支持层级和命名空间
    4. 验证：基于Schema的配置验证
    5. 监听：文件变更自动重载
    6. 快照：配置快照保存与回滚
    """

    def __init__(self, config: Optional[ManagerConfig] = None):
        self._config = config or ManagerConfig()
        self._loader = get_config_loader()
        self._validator = get_config_validator()
        self._watcher = get_config_watcher()
        self._store = get_config_store()

        self._state = ManagerState.UNINITIALIZED
        self._lock = threading.RLock()
        self._snapshots: List[Snapshot] = []
        self._snapshot_counter: int = 0
        self._environment_overrides: Dict[str, Any] = {}

    # ---- 初始化 ----

    def initialize(
        self,
        config_dir: Optional[str] = None,
        environment: Optional[Environment] = None,
        config_files: Optional[List[str]] = None,
    ) -> bool:
        """
        初始化配置管理器

        Args:
            config_dir: 配置目录
            environment: 运行环境
            config_files: 配置文件列表

        Returns:
            是否初始化成功
        """
        with self._lock:
            if self._state != ManagerState.UNINITIALIZED:
                return False

            self._state = ManagerState.INITIALIZING

        try:
            # 设置环境
            if environment:
                self._config.environment = environment
            elif os.environ.get("APP_ENV"):
                env_str = os.environ.get("APP_ENV", "").lower()
                env_map = {
                    "dev": Environment.DEVELOPMENT,
                    "development": Environment.DEVELOPMENT,
                    "staging": Environment.STAGING,
                    "prod": Environment.PRODUCTION,
                    "production": Environment.PRODUCTION,
                    "test": Environment.TEST,
                }
                self._config.environment = env_map.get(env_str, Environment.DEVELOPMENT)

            # 设置配置目录
            if config_dir:
                self._config.config_dir = config_dir

            # 创建默认命名空间
            self._store.create_namespace("default", "Default configuration namespace")
            self._store.create_namespace("system", "System configuration")
            self._store.create_namespace("app", "Application configuration")

            # 加载配置文件
            if config_files:
                for f in config_files:
                    if os.path.exists(f):
                        self._loader.load_file(f)
            elif os.path.isdir(self._config.config_dir):
                self._load_config_dir(self._config.config_dir)

            # 加载环境变量
            self._loader.add_source(SourceConfig(
                name="environment",
                source_type=ConfigSource.ENVIRONMENT,
                prefix="APP_",
                priority=200,
            ))

            # 加载所有源
            self._loader.load_all()

            # 合并后的配置存入DEFAULT层
            merged = self._loader.get_merged()
            self._store.set_many(merged, layer=ConfigLayer.DEFAULT, namespace="default")

            # 加载环境特定覆盖
            self._load_environment_overrides()

            # 验证配置
            if self._config.validate_on_load:
                self._validate_default_config()

            # 保存初始快照
            if self._config.snapshot_on_start:
                self.take_snapshot("initial", "Initial configuration snapshot")

            # 启动文件监听
            if self._config.watch_files:
                self._setup_watching()

            self._state = ManagerState.READY
            return True

        except Exception as e:
            self._state = ManagerState.ERROR
            return False

    # ---- 读取 ----

    def get(
        self,
        key: str,
        default: Any = None,
        namespace: str = "default",
        as_type: Optional[type] = None
    ) -> Any:
        """
        获取配置值

        Args:
            key: 配置键（支持点号分隔的嵌套路径，如 "database.host"）
            default: 默认值
            namespace: 命名空间
            as_type: 类型转换（str/int/float/bool）

        Returns:
            配置值
        """
        # 先尝试嵌套路径查找
        if "." in key:
            nested_value = self._get_nested(key, namespace, _SENTINEL)
            if nested_value is not _SENTINEL:
                value = nested_value
            else:
                value = self._store.get(key, namespace, default)
        else:
            value = self._store.get(key, namespace, default)

        # 类型转换
        if value is not None and as_type:
            value = self._convert_type(value, as_type)

        return value

    def get_section(
        self,
        prefix: str,
        namespace: str = "default"
    ) -> Dict[str, Any]:
        """
        获取配置段（所有以prefix开头的键，或嵌套字典中prefix对应的值）

        Args:
            prefix: 前缀
            namespace: 命名空间

        Returns:
            匹配的配置字典
        """
        all_config = self._store.get_all(namespace)
        result = {}

        for key, value in all_config.items():
            if key == prefix and isinstance(value, dict):
                # 键本身就是嵌套字典
                result.update(value)
            elif key.startswith(prefix):
                suffix = key[len(prefix):]
                if suffix.startswith("."):
                    suffix = suffix[1:]
                if suffix:
                    result[suffix] = value

        return result

    def get_int(self, key: str, default: int = 0, namespace: str = "default") -> int:
        """获取整数配置"""
        value = self.get(key, default, namespace, int)
        return int(value) if value is not None else default

    def get_float(self, key: str, default: float = 0.0, namespace: str = "default") -> float:
        """获取浮点数配置"""
        value = self.get(key, default, namespace, float)
        return float(value) if value is not None else default

    def get_bool(self, key: str, default: bool = False, namespace: str = "default") -> bool:
        """获取布尔配置"""
        value = self.get(key, default, namespace, bool)
        return bool(value) if value is not None else default

    def get_str(self, key: str, default: str = "", namespace: str = "default") -> str:
        """获取字符串配置"""
        value = self.get(key, default, namespace, str)
        return str(value) if value is not None else default

    def get_list(self, key: str, default: Optional[list] = None, namespace: str = "default") -> list:
        """获取列表配置"""
        value = self.get(key, default or [], namespace)
        return value if isinstance(value, list) else (default or [])

    # ---- 写入 ----

    def set(
        self,
        key: str,
        value: Any,
        namespace: str = "default",
        layer: ConfigLayer = ConfigLayer.RUNTIME,
        source: str = "runtime"
    ) -> None:
        """
        设置配置值

        Args:
            key: 配置键
            value: 配置值
            namespace: 命名空间
            layer: 配置层级
            source: 来源
        """
        self._store.set(key, value, layer=layer, namespace=namespace, source=source)

    def set_many(
        self,
        data: Dict[str, Any],
        namespace: str = "default",
        layer: ConfigLayer = ConfigLayer.RUNTIME
    ) -> int:
        """批量设置配置值"""
        return self._store.set_many(data, layer=layer, namespace=namespace, source="batch")

    # ---- 验证 ----

    def validate(
        self,
        schema_name: Optional[str] = None,
        schema: Optional[Dict] = None,
        namespace: str = "default"
    ) -> ValidationResult:
        """
        验证当前配置

        Args:
            schema_name: 已注册的Schema名称
            schema: 直接传入的Schema
            namespace: 命名空间

        Returns:
            验证结果
        """
        config = self._store.get_all(namespace)
        return self._validator.validate(config, schema_name=schema_name, schema=schema)

    def register_schema(
        self,
        name: str,
        schema: Dict,
        namespace: str = "default"
    ) -> None:
        """注册验证Schema"""
        self._validator.register_schema(name, schema)

    # ---- 快照 ----

    def take_snapshot(self, name: str = "", description: str = "") -> Snapshot:
        """
        保存配置快照

        Args:
            name: 快照名称
            description: 描述

        Returns:
            快照对象
        """
        with self._lock:
            self._snapshot_counter += 1
            snapshot_id = f"snap_{self._snapshot_counter:04d}"

            snapshot = Snapshot(
                id=snapshot_id,
                name=name or f"snapshot_{self._snapshot_counter}",
                data=deepcopy(self._store.get_all("default")),
                environment=self._config.environment.value,
                description=description,
            )

            self._snapshots.append(snapshot)

            # 限制快照数量
            if len(self._snapshots) > self._config.max_snapshots:
                self._snapshots = self._snapshots[-self._config.max_snapshots:]

            return snapshot

    def rollback(self, snapshot_id: str) -> bool:
        """
        回滚到指定快照

        Args:
            snapshot_id: 快照ID

        Returns:
            是否回滚成功
        """
        with self._lock:
            snapshot = None
            for s in self._snapshots:
                if s.id == snapshot_id:
                    snapshot = s
                    break

            if snapshot is None:
                return False

            # 清除RUNTIME层并恢复快照数据
            self._store.clear_layer(ConfigLayer.RUNTIME, "default")
            self._store.set_many(
                snapshot.data,
                layer=ConfigLayer.RUNTIME,
                namespace="default",
                source=f"rollback:{snapshot_id}",
            )

            return True

    def list_snapshots(self) -> List[Dict[str, Any]]:
        """列出所有快照"""
        with self._lock:
            return [
                {
                    "id": s.id,
                    "name": s.name,
                    "timestamp": s.timestamp,
                    "environment": s.environment,
                    "description": s.description,
                    "keys": len(s.data),
                }
                for s in self._snapshots
            ]

    # ---- 环境管理 ----

    @property
    def environment(self) -> Environment:
        """获取当前环境"""
        return self._config.environment

    def set_environment(self, env: Environment) -> None:
        """设置运行环境"""
        with self._lock:
            old_env = self._config.environment
            self._config.environment = env

            # 加载环境特定覆盖
            self._load_environment_overrides()

    # ---- 状态与统计 ----

    @property
    def state(self) -> ManagerState:
        """获取管理器状态"""
        return self._state

    def get_status(self) -> Dict[str, Any]:
        """获取管理器状态"""
        return {
            "state": self._state.value,
            "environment": self._config.environment.value,
            "config_dir": self._config.config_dir,
            "watching": self._config.watch_files,
        }

    def get_stats(self) -> Dict[str, Any]:
        """获取综合统计"""
        return {
            "manager": self.get_status(),
            "loader": self._loader.get_stats(),
            "validator": self._validator.get_stats(),
            "watcher": self._watcher.get_stats(),
            "store": self._store.get_stats(),
            "snapshots": len(self._snapshots),
        }

    # ---- 子系统访问 ----

    @property
    def loader(self) -> ConfigLoader:
        return self._loader

    @property
    def validator(self) -> ConfigValidator:
        return self._validator

    @property
    def watcher(self) -> ConfigWatcher:
        return self._watcher

    @property
    def store(self) -> ConfigStore:
        return self._store

    # ---- 关闭 ----

    def shutdown(self) -> None:
        """关闭管理器"""
        self._watcher.stop()
        with self._lock:
            self._state = ManagerState.SHUTDOWN

    # ---- 内部方法 ----

    def _load_config_dir(self, directory: str) -> None:
        """加载配置目录中的所有配置文件"""
        if not os.path.isdir(directory):
            return

        env = self._config.environment.value
        priority = 100

        # 加载通用配置
        for fname in os.listdir(directory):
            fpath = os.path.join(directory, fname)
            if os.path.isfile(fpath) and fname.endswith(".json"):
                self._loader.load_file(fpath, name=f"dir:{fname}", priority=priority)
                priority += 10

        # 加载环境特定配置（更高优先级）
        env_dir = os.path.join(directory, env)
        if os.path.isdir(env_dir):
            for fname in os.listdir(env_dir):
                fpath = os.path.join(env_dir, fname)
                if os.path.isfile(fpath) and fname.endswith(".json"):
                    self._loader.load_file(fpath, name=f"env:{fname}", priority=priority + 100)
                    priority += 10

    def _load_environment_overrides(self) -> None:
        """加载环境特定覆盖"""
        env = self._config.environment.value
        env_overrides = {
            "debug": env == Environment.DEVELOPMENT.value,
            "log_level": "DEBUG" if env == Environment.DEVELOPMENT.value else "INFO",
        }
        self._store.set_many(env_overrides, layer=ConfigLayer.ENV, namespace="default", source="environment")

    def _validate_default_config(self) -> None:
        """验证默认配置"""
        # 基本验证：确保配置可序列化
        config = self._store.get_all("default")
        try:
            json.dumps(config, default=str)
        except Exception:
            pass

    def _setup_watching(self) -> None:
        """设置文件监听"""
        if os.path.isdir(self._config.config_dir):
            self._watcher.watch(WatchConfig(
                path=self._config.config_dir,
                recursive=True,
                interval=self._config.watch_interval,
                debounce=1.0,
                patterns=["*.json", "*.yaml", "*.yml"],
            ))

            # 设置变更回调
            def on_file_change(event: ChangeEvent):
                if event.change_type == ChangeType.MODIFIED:
                    self._loader.load_all()
                    merged = self._loader.get_merged()
                    self._store.set_many(
                        merged,
                        layer=ConfigLayer.DEFAULT,
                        namespace="default",
                        source=f"watcher:{event.path}",
                    )

            self._watcher.on_change(on_file_change)

            self._watcher.start()

    def _get_nested(self, key: str, namespace: str, default: Any) -> Any:
        """获取嵌套配置值"""
        all_config = self._store.get_all(namespace)

        # 先检查是否有精确的扁平键匹配
        if key in all_config:
            return all_config[key]

        # 再尝试嵌套路径遍历
        parts = key.split(".")
        current = all_config

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return default

        return current

    def _convert_type(self, value: Any, target_type: type) -> Any:
        """类型转换"""
        try:
            if target_type == bool:
                if isinstance(value, str):
                    return value.lower() in ("true", "yes", "1")
                return bool(value)
            return target_type(value)
        except (ValueError, TypeError):
            return value


# ============================================================
# 全局单例
# ============================================================

_config_manager: Optional[ConfigManager] = None
_manager_lock = threading.RLock()


def get_config_manager(config: Optional[ManagerConfig] = None) -> ConfigManager:
    """获取全局配置管理器（双重检查锁定）"""
    global _config_manager
    if _config_manager is None:
        with _manager_lock:
            if _config_manager is None:
                _config_manager = ConfigManager(config)
    return _config_manager
