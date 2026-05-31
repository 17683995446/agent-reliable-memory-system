#!/usr/bin/env python3
"""
配置存储 (ConfigStore) - 阶段329

职责：
- 分层配置存储：default < system < user < env < runtime
- 命名空间隔离：不同模块的配置互不干扰
- 覆盖合并：高层覆盖低层，支持深度合并
- 敏感值标记与脱敏显示
- 配置变更通知
- 持久化支持

设计原则：
- 确定性规则，无模型依赖
- 线程安全（RLock）
- 最小层级，无循环依赖
"""

import base64
import hashlib
import json
import os
import threading
import time
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


# ============================================================
# 枚举与数据结构
# ============================================================

class ConfigLayer(Enum):
    """配置层级（优先级从低到高）"""
    DEFAULT = 0     # 默认配置
    SYSTEM = 1      # 系统配置
    USER = 2        # 用户配置
    ENV = 3         # 环境变量
    RUNTIME = 4     # 运行时配置（最高优先级）


class SensitivityLevel(Enum):
    """敏感度级别"""
    PUBLIC = "public"       # 公开
    INTERNAL = "internal"   # 内部
    SENSITIVE = "sensitive" # 敏感
    SECRET = "secret"       # 机密


@dataclass
class NamespaceInfo:
    """命名空间信息"""
    name: str
    description: str = ""
    created_at: float = 0.0
    layer_count: int = 0
    key_count: int = 0

    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = time.time()


@dataclass
class ConfigEntry:
    """配置条目"""
    key: str
    value: Any
    layer: ConfigLayer
    sensitivity: SensitivityLevel = SensitivityLevel.PUBLIC
    namespace: str = "default"
    updated_at: float = 0.0
    source: str = ""

    def __post_init__(self):
        if self.updated_at == 0.0:
            self.updated_at = time.time()


@dataclass
class ChangeRecord:
    """变更记录"""
    namespace: str
    key: str
    old_value: Any
    new_value: Any
    layer: ConfigLayer
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


# ============================================================
# 配置存储
# ============================================================

class ConfigStore:
    """
    配置存储

    核心功能：
    1. 五层配置存储（DEFAULT < SYSTEM < USER < ENV < RUNTIME）
    2. 命名空间隔离
    3. 敏感值标记与脱敏
    4. 变更通知
    5. 变更历史
    6. 持久化（JSON文件）
    """

    def __init__(self):
        self._layers: Dict[ConfigLayer, Dict[str, Dict[str, ConfigEntry]]] = {
            layer: {} for layer in ConfigLayer
        }
        self._namespaces: Dict[str, NamespaceInfo] = {}
        self._sensitive_keys: Dict[str, Set[str]] = {}  # namespace -> sensitive key set
        self._change_history: List[ChangeRecord] = []
        self._change_callbacks: Dict[str, List[Callable]] = {}  # namespace -> callbacks
        self._global_callbacks: List[Callable] = []
        self._lock = threading.RLock()
        self._max_history: int = 1000

    # ---- 命名空间 ----

    def create_namespace(self, name: str, description: str = "") -> bool:
        """创建命名空间"""
        with self._lock:
            if name in self._namespaces:
                return False
            self._namespaces[name] = NamespaceInfo(name=name, description=description)
            self._sensitive_keys[name] = set()
            self._change_callbacks[name] = []
            return True

    def delete_namespace(self, name: str) -> bool:
        """删除命名空间"""
        with self._lock:
            if name not in self._namespaces:
                return False

            # 清除所有层中的数据
            for layer in ConfigLayer:
                self._layers[layer].pop(name, None)

            del self._namespaces[name]
            self._sensitive_keys.pop(name, None)
            self._change_callbacks.pop(name, None)
            return True

    def list_namespaces(self) -> List[Dict[str, Any]]:
        """列出命名空间"""
        with self._lock:
            result = []
            for name, info in self._namespaces.items():
                key_count = sum(
                    len(self._layers[layer].get(name, {}))
                    for layer in ConfigLayer
                )
                result.append({
                    "name": name,
                    "description": info.description,
                    "created_at": info.created_at,
                    "key_count": key_count,
                })
            return result

    # ---- 读写操作 ----

    def set(
        self,
        key: str,
        value: Any,
        layer: ConfigLayer = ConfigLayer.RUNTIME,
        namespace: str = "default",
        sensitivity: SensitivityLevel = SensitivityLevel.PUBLIC,
        source: str = ""
    ) -> None:
        """
        设置配置值

        Args:
            key: 配置键
            value: 配置值
            layer: 配置层级
            namespace: 命名空间
            sensitivity: 敏感度
            source: 来源
        """
        with self._lock:
            self._ensure_namespace(namespace)

            # 记录旧值
            old_value = self._get_raw(key, namespace)

            # 设置新值
            if namespace not in self._layers[layer]:
                self._layers[layer][namespace] = {}

            self._layers[layer][namespace][key] = ConfigEntry(
                key=key,
                value=value,
                layer=layer,
                sensitivity=sensitivity,
                namespace=namespace,
                source=source,
            )

            # 标记敏感键
            if sensitivity in (SensitivityLevel.SENSITIVE, SensitivityLevel.SECRET):
                self._sensitive_keys[namespace].add(key)

            # 记录变更
            self._record_change(namespace, key, old_value, value, layer)

    def get(
        self,
        key: str,
        namespace: str = "default",
        default: Any = None
    ) -> Any:
        """
        获取配置值（从最高优先级层开始查找）

        Args:
            key: 配置键
            namespace: 命名空间
            default: 默认值

        Returns:
            配置值
        """
        with self._lock:
            # 从最高优先级层向下查找
            for layer in reversed(ConfigLayer):
                ns_data = self._layers[layer].get(namespace, {})
                if key in ns_data:
                    return ns_data[key].value

            return default

    def get_from_layer(
        self,
        key: str,
        layer: ConfigLayer,
        namespace: str = "default"
    ) -> Optional[Any]:
        """从指定层获取配置值"""
        with self._lock:
            ns_data = self._layers[layer].get(namespace, {})
            entry = ns_data.get(key)
            return entry.value if entry else None

    def delete(
        self,
        key: str,
        layer: ConfigLayer = ConfigLayer.RUNTIME,
        namespace: str = "default"
    ) -> bool:
        """删除配置值"""
        with self._lock:
            ns_data = self._layers[layer].get(namespace, {})
            if key in ns_data:
                old_value = ns_data[key].value
                del ns_data[key]
                self._record_change(namespace, key, old_value, None, layer)
                return True
            return False

    def has(self, key: str, namespace: str = "default") -> bool:
        """检查配置键是否存在"""
        with self._lock:
            for layer in ConfigLayer:
                ns_data = self._layers[layer].get(namespace, {})
                if key in ns_data:
                    return True
            return False

    # ---- 批量操作 ----

    def set_many(
        self,
        data: Dict[str, Any],
        layer: ConfigLayer = ConfigLayer.RUNTIME,
        namespace: str = "default",
        source: str = ""
    ) -> int:
        """批量设置配置值"""
        count = 0
        for key, value in data.items():
            self.set(key, value, layer=layer, namespace=namespace, source=source)
            count += 1
        return count

    def get_all(self, namespace: str = "default") -> Dict[str, Any]:
        """
        获取命名空间下所有配置（合并所有层）

        Returns:
            合并后的配置字典
        """
        with self._lock:
            merged = {}
            for layer in ConfigLayer:
                ns_data = self._layers[layer].get(namespace, {})
                for key, entry in ns_data.items():
                    merged[key] = entry.value
            return merged

    def get_layer_data(self, layer: ConfigLayer, namespace: str = "default") -> Dict[str, Any]:
        """获取指定层的所有配置"""
        with self._lock:
            ns_data = self._layers[layer].get(namespace, {})
            return {key: entry.value for key, entry in ns_data.items()}

    def clear_layer(self, layer: ConfigLayer, namespace: str = "default") -> int:
        """清除指定层的所有配置"""
        with self._lock:
            ns_data = self._layers[layer].get(namespace, {})
            count = len(ns_data)
            ns_data.clear()
            return count

    def clear_namespace(self, namespace: str = "default") -> int:
        """清除命名空间下所有层的配置"""
        count = 0
        for layer in ConfigLayer:
            count += self.clear_layer(layer, namespace)
        return count

    # ---- 敏感值 ----

    def mark_sensitive(self, key: str, namespace: str = "default") -> None:
        """标记配置键为敏感"""
        with self._lock:
            if namespace in self._sensitive_keys:
                self._sensitive_keys[namespace].add(key)

    def get_masked(self, key: str, namespace: str = "default") -> Optional[str]:
        """获取脱敏后的值"""
        value = self.get(key, namespace)
        if value is None:
            return None

        with self._lock:
            if namespace in self._sensitive_keys and key in self._sensitive_keys[namespace]:
                return self._mask_value(value)

        return str(value) if not isinstance(value, str) else value

    def get_all_masked(self, namespace: str = "default") -> Dict[str, Any]:
        """获取所有配置（敏感值脱敏）"""
        with self._lock:
            sensitive = self._sensitive_keys.get(namespace, set())

        all_config = self.get_all(namespace)
        masked = {}
        for key, value in all_config.items():
            if key in sensitive:
                masked[key] = self._mask_value(value)
            else:
                masked[key] = value
        return masked

    # ---- 变更通知 ----

    def on_change(
        self,
        namespace: str,
        callback: Callable[[ChangeRecord], None]
    ) -> None:
        """添加命名空间变更回调"""
        with self._lock:
            if namespace not in self._change_callbacks:
                self._change_callbacks[namespace] = []
            self._change_callbacks[namespace].append(callback)

    def on_change_global(self, callback: Callable[[ChangeRecord], None]) -> None:
        """添加全局变更回调"""
        with self._lock:
            self._global_callbacks.append(callback)

    # ---- 持久化 ----

    def save_to_file(
        self,
        path: str,
        layer: ConfigLayer = ConfigLayer.USER,
        namespace: str = "default"
    ) -> bool:
        """保存指定层配置到文件"""
        try:
            data = self.get_layer_data(layer, namespace)
            os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            return True
        except Exception:
            return False

    def load_from_file(
        self,
        path: str,
        layer: ConfigLayer = ConfigLayer.USER,
        namespace: str = "default"
    ) -> bool:
        """从文件加载配置到指定层"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.set_many(data, layer=layer, namespace=namespace, source=path)
            return True
        except Exception:
            return False

    # ---- 历史与统计 ----

    def get_history(
        self,
        namespace: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """查询变更历史"""
        with self._lock:
            history = list(self._change_history)

        if namespace:
            history = [h for h in history if h.namespace == namespace]

        return [
            {
                "namespace": h.namespace,
                "key": h.key,
                "old_value": h.old_value,
                "new_value": h.new_value,
                "layer": h.layer.name,
                "timestamp": h.timestamp,
            }
            for h in history[-limit:]
        ]

    def get_stats(self) -> Dict[str, Any]:
        """获取存储统计"""
        with self._lock:
            layer_counts = {}
            for layer in ConfigLayer:
                count = sum(
                    len(ns_data)
                    for ns_data in self._layers[layer].values()
                )
                layer_counts[layer.name] = count

            return {
                "namespaces": len(self._namespaces),
                "layer_distribution": layer_counts,
                "total_keys": sum(layer_counts.values()),
                "change_history": len(self._change_history),
                "sensitive_keys": sum(
                    len(keys) for keys in self._sensitive_keys.values()
                ),
            }

    # ---- 内部方法 ----

    def _ensure_namespace(self, name: str) -> None:
        """确保命名空间存在"""
        if name not in self._namespaces:
            self._namespaces[name] = NamespaceInfo(name=name)
            self._sensitive_keys[name] = set()
            self._change_callbacks[name] = []

    def _get_raw(self, key: str, namespace: str) -> Optional[Any]:
        """获取原始值（不经过合并）"""
        for layer in reversed(ConfigLayer):
            ns_data = self._layers[layer].get(namespace, {})
            if key in ns_data:
                return ns_data[key].value
        return None

    def _record_change(
        self,
        namespace: str,
        key: str,
        old_value: Any,
        new_value: Any,
        layer: ConfigLayer
    ) -> None:
        """记录变更"""
        record = ChangeRecord(
            namespace=namespace,
            key=key,
            old_value=old_value,
            new_value=new_value,
            layer=layer,
        )

        with self._lock:
            self._change_history.append(record)
            if len(self._change_history) > self._max_history:
                self._change_history = self._change_history[-self._max_history:]

        # 通知回调
        for cb in self._change_callbacks.get(namespace, []):
            try:
                cb(record)
            except Exception:
                pass

        for cb in self._global_callbacks:
            try:
                cb(record)
            except Exception:
                pass

    def _mask_value(self, value: Any) -> str:
        """脱敏处理"""
        s = str(value)
        if len(s) <= 4:
            return "****"
        return s[:2] + "****" + s[-2:]


# ============================================================
# 全局单例
# ============================================================

_config_store: Optional[ConfigStore] = None
_store_lock = threading.RLock()


def get_config_store() -> ConfigStore:
    """获取全局配置存储（双重检查锁定）"""
    global _config_store
    if _config_store is None:
        with _store_lock:
            if _config_store is None:
                _config_store = ConfigStore()
    return _config_store
