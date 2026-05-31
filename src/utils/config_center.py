"""
Agent可靠记忆系统 - 系统配置中心
阶段188-190: 统一配置管理、配置验证、配置版本控制

设计原则:
- 确定性规则驱动，无模型依赖
- 线程安全（RLock）
- 全局单例模式
- 分层配置架构
"""

import threading
import time
import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Union
from collections import defaultdict


class ConfigScope(Enum):
    """配置作用域"""
    SYSTEM = "system"            # 系统级
    MODULE = "module"            # 模块级
    USER = "user"                # 用户级
    SESSION = "session"          # 会话级


class ConfigType(Enum):
    """配置类型"""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    LIST = "list"
    DICT = "dict"
    JSON = "json"


@dataclass
class ConfigItem:
    """配置项"""
    key: str
    value: Any
    default_value: Any = None
    config_type: ConfigType = ConfigType.STRING
    scope: ConfigScope = ConfigScope.SYSTEM
    description: str = ""
    validator: Optional[Callable] = None
    mutable: bool = True
    secret: bool = False         # 敏感配置（不显示值）
    updated_at: float = field(default_factory=time.time)
    updated_by: str = ""

    def to_dict(self, hide_secrets: bool = True) -> Dict:
        result = {
            "key": self.key,
            "type": self.config_type.value,
            "scope": self.scope.value,
            "description": self.description,
            "mutable": self.mutable,
            "updated_at": self.updated_at,
            "updated_by": self.updated_by,
        }

        if self.secret and hide_secrets:
            result["value"] = "********"
            result["default_value"] = "********"
        else:
            result["value"] = self.value
            result["default_value"] = self.default_value

        return result


@dataclass
class ConfigVersion:
    """配置版本"""
    version_id: str
    timestamp: float
    changes: Dict[str, Any]      # 变更的配置
    author: str = ""
    comment: str = ""

    def to_dict(self) -> Dict:
        return {
            "version_id": self.version_id,
            "timestamp": self.timestamp,
            "changes": self.changes,
            "author": self.author,
            "comment": self.comment,
        }


class ConfigCenter:
    """
    系统配置中心

    功能:
    - 分层配置管理（系统/模块/用户/会话）
    - 配置类型验证
    - 配置变更历史
    - 配置热加载
    - 配置继承与覆盖
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._configs: Dict[str, ConfigItem] = {}  # key -> ConfigItem
        self._versions: List[ConfigVersion] = []   # 变更历史
        self._version_counter: int = 0
        self._change_listeners: Dict[str, List[Callable]] = defaultdict(list)
        self._schema: Dict[str, Dict] = {}         # 配置模式

        # 初始化默认配置
        self._init_defaults()

    def _init_defaults(self):
        """初始化默认配置"""
        defaults = [
            # 系统级配置
            ("system.debug", False, ConfigType.BOOLEAN, "调试模式"),
            ("system.log_level", "INFO", ConfigType.STRING, "日志级别"),
            ("system.max_memory_mb", 1024, ConfigType.INTEGER, "最大内存限制(MB)"),

            # 存储配置
            ("storage.l1_max_items", 10000, ConfigType.INTEGER, "L1最大条目数"),
            ("storage.l2_max_items", 50000, ConfigType.INTEGER, "L2最大条目数"),
            ("storage.l3_path", "./data/l3", ConfigType.STRING, "L3存储路径"),

            # 召回配置
            ("recall.default_top_k", 10, ConfigType.INTEGER, "默认召回数量"),
            ("recall.similarity_threshold", 0.7, ConfigType.FLOAT, "相似度阈值"),
            ("recall.enable_cache", True, ConfigType.BOOLEAN, "启用召回缓存"),

            # 隐私配置
            ("privacy.default_level", "internal", ConfigType.STRING, "默认隐私级别"),
            ("privacy.auto_expire_days", 30, ConfigType.INTEGER, "自动过期天数"),

            # 安全配置
            ("security.max_login_attempts", 5, ConfigType.INTEGER, "最大登录尝试次数"),
            ("security.session_timeout_minutes", 30, ConfigType.INTEGER, "会话超时时间(分钟)"),
        ]

        for key, value, config_type, description in defaults:
            self._configs[key] = ConfigItem(
                key=key,
                value=value,
                default_value=value,
                config_type=config_type,
                scope=ConfigScope.SYSTEM,
                description=description,
            )

    # ==================== 配置读写 ====================

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        with self._lock:
            item = self._configs.get(key)
            return item.value if item else default

    def get_typed(self, key: str, config_type: ConfigType,
                  default: Any = None) -> Any:
        """获取指定类型的配置值"""
        value = self.get(key, default)
        return self._convert_type(value, config_type)

    def get_all(self, scope: Optional[ConfigScope] = None,
                prefix: Optional[str] = None) -> Dict[str, Any]:
        """
        获取所有配置

        Args:
            scope: 按作用域过滤
            prefix: 按前缀过滤
        """
        with self._lock:
            result = {}
            for key, item in self._configs.items():
                if scope and item.scope != scope:
                    continue
                if prefix and not key.startswith(prefix):
                    continue
                result[key] = item.value
            return result

    def set(self, key: str, value: Any,
            author: str = "",
            comment: str = "") -> bool:
        """
        设置配置值

        Args:
            key: 配置键
            value: 配置值
            author: 修改者
            comment: 修改说明

        Returns:
            是否设置成功
        """
        with self._lock:
            if key in self._configs:
                item = self._configs[key]
                if not item.mutable:
                    return False

                # 类型验证
                if not self._validate_value(value, item.config_type):
                    return False

                # 自定义验证
                if item.validator and not item.validator(value):
                    return False

                old_value = item.value
                item.value = value
                item.updated_at = time.time()
                item.updated_by = author

                # 记录版本
                self._record_version(key, old_value, value, author, comment)

                # 触发监听器
                self._notify_change(key, old_value, value)

                return True
            else:
                # 新配置项
                self._configs[key] = ConfigItem(
                    key=key,
                    value=value,
                    default_value=value,
                    updated_by=author,
                )
                self._record_version(key, None, value, author, comment)
                return True

    def set_multi(self, items: Dict[str, Any],
                  author: str = "",
                  comment: str = "") -> Dict[str, bool]:
        """批量设置配置"""
        results = {}
        for key, value in items.items():
            results[key] = self.set(key, value, author, comment)
        return results

    def reset(self, key: str, author: str = "") -> bool:
        """重置配置为默认值"""
        with self._lock:
            item = self._configs.get(key)
            if not item or not item.mutable:
                return False

            return self.set(key, item.default_value, author, f"Reset {key} to default")

    def reset_all(self, scope: Optional[ConfigScope] = None,
                  author: str = "") -> int:
        """批量重置配置"""
        with self._lock:
            count = 0
            for key, item in self._configs.items():
                if scope and item.scope != scope:
                    continue
                if item.mutable and item.value != item.default_value:
                    if self.reset(key, author):
                        count += 1
            return count

    # ==================== 配置注册与模式 ====================

    def register(self, key: str,
                 default_value: Any,
                 config_type: ConfigType = ConfigType.STRING,
                 scope: ConfigScope = ConfigScope.SYSTEM,
                 description: str = "",
                 validator: Optional[Callable] = None,
                 mutable: bool = True,
                 secret: bool = False):
        """
        注册配置项

        Args:
            key: 配置键
            default_value: 默认值
            config_type: 配置类型
            scope: 作用域
            description: 描述
            validator: 验证函数
            mutable: 是否可修改
            secret: 是否敏感
        """
        with self._lock:
            if key not in self._configs:
                self._configs[key] = ConfigItem(
                    key=key,
                    value=default_value,
                    default_value=default_value,
                    config_type=config_type,
                    scope=scope,
                    description=description,
                    validator=validator,
                    mutable=mutable,
                    secret=secret,
                )

    def register_schema(self, key: str, schema: Dict):
        """
        注册配置模式

        schema格式:
        {
            "type": "integer",
            "min": 0,
            "max": 100,
            "enum": ["a", "b", "c"],
            "pattern": "regex",
        }
        """
        with self._lock:
            self._schema[key] = schema

    def _validate_value(self, value: Any, config_type: ConfigType) -> bool:
        """验证值类型"""
        try:
            if config_type == ConfigType.STRING:
                str(value)
            elif config_type == ConfigType.INTEGER:
                int(value)
            elif config_type == ConfigType.FLOAT:
                float(value)
            elif config_type == ConfigType.BOOLEAN:
                if not isinstance(value, bool):
                    return str(value).lower() in ("true", "false", "1", "0", "yes", "no")
            elif config_type == ConfigType.LIST:
                if not isinstance(value, (list, tuple)):
                    return False
            elif config_type == ConfigType.DICT:
                if not isinstance(value, dict):
                    return False
            return True
        except (ValueError, TypeError):
            return False

    def _convert_type(self, value: Any, config_type: ConfigType) -> Any:
        """转换值类型"""
        try:
            if config_type == ConfigType.STRING:
                return str(value)
            elif config_type == ConfigType.INTEGER:
                return int(value)
            elif config_type == ConfigType.FLOAT:
                return float(value)
            elif config_type == ConfigType.BOOLEAN:
                if isinstance(value, bool):
                    return value
                return str(value).lower() in ("true", "1", "yes")
            elif config_type == ConfigType.LIST:
                return list(value) if value else []
            elif config_type == ConfigType.DICT:
                return dict(value) if value else {}
            return value
        except (ValueError, TypeError):
            return value

    # ==================== 配置变更监听 ====================

    def add_change_listener(self, key_pattern: str, callback: Callable):
        """
        添加配置变更监听器

        Args:
            key_pattern: 键匹配模式（支持*通配符）
            callback: 回调函数(old_value, new_value)
        """
        with self._lock:
            self._change_listeners[key_pattern].append(callback)

    def remove_change_listener(self, key_pattern: str,
                               callback: Optional[Callable] = None):
        """移除配置变更监听器"""
        with self._lock:
            if callback:
                if key_pattern in self._change_listeners:
                    self._change_listeners[key_pattern] = [
                        cb for cb in self._change_listeners[key_pattern]
                        if cb != callback
                    ]
            else:
                self._change_listeners.pop(key_pattern, None)

    def _notify_change(self, key: str, old_value: Any, new_value: Any):
        """通知配置变更"""
        import fnmatch
        for pattern, callbacks in self._change_listeners.items():
            if fnmatch.fnmatch(key, pattern):
                for callback in callbacks:
                    try:
                        callback(key, old_value, new_value)
                    except Exception:
                        pass

    # ==================== 版本控制 ====================

    def _record_version(self, key: str, old_value: Any, new_value: Any,
                        author: str, comment: str):
        """记录配置版本"""
        self._version_counter += 1
        version = ConfigVersion(
            version_id=f"v{self._version_counter:06d}",
            timestamp=time.time(),
            changes={key: {"old": old_value, "new": new_value}},
            author=author,
            comment=comment,
        )
        self._versions.append(version)

        # 限制历史数量
        if len(self._versions) > 1000:
            self._versions = self._versions[-800:]

    def get_version_history(self, key: Optional[str] = None,
                            limit: int = 50) -> List[ConfigVersion]:
        """获取版本历史"""
        with self._lock:
            versions = self._versions
            if key:
                versions = [v for v in versions if key in v.changes]
            return versions[-limit:]

    def rollback(self, version_id: str, author: str = "") -> bool:
        """回滚到指定版本"""
        with self._lock:
            for version in reversed(self._versions):
                if version.version_id == version_id:
                    for key, change in version.changes.items():
                        self.set(key, change["old"], author,
                                f"Rollback to {version_id}")
                    return True
            return False

    # ==================== 配置导入导出 ====================

    def export_config(self, scope: Optional[ConfigScope] = None,
                      include_defaults: bool = False) -> Dict:
        """导出配置"""
        with self._lock:
            result = {"configs": {}, "metadata": {}}

            for key, item in self._configs.items():
                if scope and item.scope != scope:
                    continue

                if include_defaults or item.value != item.default_value:
                    result["configs"][key] = item.to_dict(hide_secrets=True)

            result["metadata"] = {
                "export_time": time.time(),
                "total_configs": len(result["configs"]),
            }

            return result

    def import_config(self, data: Dict,
                      author: str = "",
                      overwrite: bool = False) -> Dict:
        """
        导入配置

        Args:
            data: 配置数据
            author: 导入者
            overwrite: 是否覆盖现有配置
        """
        with self._lock:
            results = {"imported": 0, "skipped": 0, "errors": []}

            configs = data.get("configs", {})
            for key, config_data in configs.items():
                try:
                    if key in self._configs and not overwrite:
                        results["skipped"] += 1
                        continue

                    value = config_data.get("value")
                    self.set(key, value, author, "Import config")
                    results["imported"] += 1
                except Exception as e:
                    results["errors"].append({"key": key, "error": str(e)})

            return results

    # ==================== 配置分析 ====================

    def get_config_stats(self) -> Dict:
        """获取配置统计"""
        with self._lock:
            scope_counts = defaultdict(int)
            type_counts = defaultdict(int)
            modified_count = 0

            for item in self._configs.values():
                scope_counts[item.scope.value] += 1
                type_counts[item.config_type.value] += 1
                if item.value != item.default_value:
                    modified_count += 1

            return {
                "total_configs": len(self._configs),
                "modified_configs": modified_count,
                "by_scope": dict(scope_counts),
                "by_type": dict(type_counts),
                "version_history_size": len(self._versions),
            }

    def validate_all(self) -> Dict:
        """验证所有配置"""
        with self._lock:
            errors = []
            for key, item in self._configs.items():
                if not self._validate_value(item.value, item.config_type):
                    errors.append({
                        "key": key,
                        "value": item.value,
                        "expected_type": item.config_type.value,
                    })
            return {
                "valid": len(errors) == 0,
                "error_count": len(errors),
                "errors": errors[:20],
            }

    def get_summary(self) -> Dict:
        """获取配置中心摘要"""
        with self._lock:
            return {
                "total_configs": len(self._configs),
                "version_count": len(self._versions),
                "listener_patterns": len(self._change_listeners),
                "stats": self.get_config_stats(),
            }


# ==================== 全局单例 ====================

_global_config_center: Optional[ConfigCenter] = None
_global_config_center_lock = threading.Lock()


def get_config_center() -> ConfigCenter:
    """获取全局配置中心实例"""
    global _global_config_center
    if _global_config_center is None:
        with _global_config_center_lock:
            if _global_config_center is None:
                _global_config_center = ConfigCenter()
    return _global_config_center
