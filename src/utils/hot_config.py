#!/usr/bin/env python3
"""
配置热更新 - 阶段158-160
运行时配置修改，无需重启
"""

import json
import threading
import time
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass, field
from datetime import datetime
from copy import deepcopy


@dataclass
class ConfigChange:
    """配置变更记录"""
    key: str
    old_value: Any
    new_value: Any
    timestamp: str
    changed_by: str


class HotConfigManager:
    """
    热配置管理器

    支持运行时配置修改：
    - 配置读写
    - 变更通知
    - 配置回滚
    - 配置验证
    """

    def __init__(self, initial_config: Optional[Dict[str, Any]] = None):
        self._config: Dict[str, Any] = initial_config or {}
        self._defaults: Dict[str, Any] = deepcopy(self._config)
        self._history: List[ConfigChange] = []
        self._watchers: Dict[str, List[Callable[[str, Any, Any], None]]] = {}
        self._validators: Dict[str, Callable[[Any], bool]] = {}
        self._lock = threading.RLock()
        self._max_history = 1000

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值

        支持点分隔的嵌套键，如 "recall.top_k"
        """
        with self._lock:
            keys = key.split(".")
            value = self._config
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    return default
            return value

    def set(
        self,
        key: str,
        value: Any,
        changed_by: str = "system",
        validate: bool = True
    ) -> bool:
        """
        设置配置值

        Args:
            key: 配置键
            value: 新值
            changed_by: 变更者
            validate: 是否验证

        Returns:
            是否设置成功
        """
        with self._lock:
            # 验证
            if validate and key in self._validators:
                if not self._validators[key](value):
                    return False

            # 获取旧值
            old_value = self.get(key)

            # 设置新值
            keys = key.split(".")
            config = self._config
            for k in keys[:-1]:
                if k not in config:
                    config[k] = {}
                config = config[k]
            config[keys[-1]] = value

            # 记录变更
            change = ConfigChange(
                key=key,
                old_value=old_value,
                new_value=value,
                timestamp=datetime.now().isoformat(),
                changed_by=changed_by,
            )
            self._history.append(change)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

        # 触发监听器
        self._notify_watchers(key, old_value, value)

        return True

    def watch(
        self,
        key: str,
        callback: Callable[[str, Any, Any], None]
    ) -> str:
        """
        监听配置变更

        Args:
            key: 配置键（支持通配符 *）
            callback: 回调函数 (key, old_value, new_value)

        Returns:
            监听器ID
        """
        with self._lock:
            if key not in self._watchers:
                self._watchers[key] = []
            self._watchers[key].append(callback)
            return f"{key}:{len(self._watchers[key])}"

    def unwatch(self, key: str, callback: Callable) -> bool:
        """移除监听器"""
        with self._lock:
            if key in self._watchers and callback in self._watchers[key]:
                self._watchers[key].remove(callback)
                return True
            return False

    def _notify_watchers(self, key: str, old_value: Any, new_value: Any):
        """通知监听器"""
        # 精确匹配
        callbacks = self._watchers.get(key, [])
        for cb in callbacks:
            try:
                cb(key, old_value, new_value)
            except Exception:
                pass

        # 通配符匹配
        for watch_key, cbs in self._watchers.items():
            if watch_key == "*":
                for cb in cbs:
                    try:
                        cb(key, old_value, new_value)
                    except Exception:
                        pass

    def register_validator(
        self,
        key: str,
        validator: Callable[[Any], bool]
    ):
        """
        注册配置验证器

        Args:
            key: 配置键
            validator: 验证函数，返回True表示有效
        """
        with self._lock:
            self._validators[key] = validator

    def rollback(self, key: str, steps: int = 1) -> bool:
        """
        回滚配置

        Args:
            key: 配置键
            steps: 回滚步数

        Returns:
            是否回滚成功
        """
        with self._lock:
            # 查找历史变更
            changes = [c for c in reversed(self._history) if c.key == key]
            if len(changes) < steps:
                return False

            target_change = changes[steps - 1]
            return self.set(key, target_change.old_value, changed_by="rollback")

    def reset_to_default(self, key: Optional[str] = None) -> bool:
        """
        重置为默认值

        Args:
            key: 配置键（None重置全部）
        """
        with self._lock:
            if key:
                if key in self._defaults:
                    return self.set(key, self._defaults[key], changed_by="reset")
                return False
            else:
                self._config = deepcopy(self._defaults)
                return True

    def get_history(
        self,
        key: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """获取变更历史"""
        with self._lock:
            history = list(reversed(self._history))
            if key:
                history = [h for h in history if h.key == key]
            return [
                {
                    "key": h.key,
                    "old_value": h.old_value,
                    "new_value": h.new_value,
                    "timestamp": h.timestamp,
                    "changed_by": h.changed_by,
                }
                for h in history[:limit]
            ]

    def export_config(self) -> str:
        """导出配置为JSON"""
        with self._lock:
            return json.dumps(self._config, ensure_ascii=False, indent=2)

    def import_config(
        self,
        config_json: str,
        changed_by: str = "import"
    ) -> bool:
        """从JSON导入配置"""
        try:
            new_config = json.loads(config_json)
            with self._lock:
                for key, value in self._flatten(new_config).items():
                    self.set(key, value, changed_by=changed_by, validate=False)
            return True
        except Exception:
            return False

    def _flatten(self, config: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
        """扁平化配置字典"""
        result = {}
        for key, value in config.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                result.update(self._flatten(value, full_key))
            else:
                result[full_key] = value
        return result

    def get_all(self) -> Dict[str, Any]:
        """获取全部配置"""
        with self._lock:
            return deepcopy(self._config)

    def get_stats(self) -> Dict[str, Any]:
        """获取统计"""
        with self._lock:
            return {
                "total_keys": len(self._flatten(self._config)),
                "history_size": len(self._history),
                "watchers": sum(len(v) for v in self._watchers.values()),
                "validators": len(self._validators),
            }


# 全局配置管理器
_config_manager: Optional[HotConfigManager] = None


def get_config_manager() -> HotConfigManager:
    """获取全局配置管理器"""
    global _config_manager
    if _config_manager is None:
        _config_manager = HotConfigManager()
    return _config_manager
