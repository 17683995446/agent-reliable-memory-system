#!/usr/bin/env python3
"""
插件系统 - 阶段140-142
可扩展的插件架构
"""

import importlib
import inspect
import threading
from typing import Dict, List, Any, Optional, Type
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod


class PluginType(Enum):
    """插件类型"""
    PREPROCESSOR = "preprocessor"       # 预处理插件
    STORAGE = "storage"                 # 存储插件
    RECALL = "recall"                   # 召回插件
    GOVERNANCE = "governance"           # 治理插件
    REVIEW = "review"                   # 审查插件
    EXPORTER = "exporter"               # 导出插件
    NOTIFICATION = "notification"       # 通知插件
    CUSTOM = "custom"                   # 自定义插件


class PluginHook(Enum):
    """插件钩子点"""
    BEFORE_STORE = "before_store"       # 存储前
    AFTER_STORE = "after_store"         # 存储后
    BEFORE_RECALL = "before_recall"     # 召回前
    AFTER_RECALL = "after_recall"       # 召回后
    BEFORE_DELETE = "before_delete"     # 删除前
    AFTER_DELETE = "after_delete"       # 删除后
    ON_ERROR = "on_error"               # 错误时
    ON_SCHEDULE = "on_schedule"         # 定时触发


class BasePlugin(ABC):
    """插件基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """插件名称"""
        pass

    @property
    @abstractmethod
    def plugin_type(self) -> PluginType:
        """插件类型"""
        pass

    @property
    def version(self) -> str:
        """插件版本"""
        return "1.0.0"

    @property
    def description(self) -> str:
        """插件描述"""
        return ""

    def on_load(self):
        """插件加载时调用"""
        pass

    def on_unload(self):
        """插件卸载时调用"""
        pass

    def execute(self, hook: PluginHook, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行插件逻辑

        Args:
            hook: 钩子点
            context: 上下文数据

        Returns:
            修改后的上下文
        """
        return context


@dataclass
class PluginInfo:
    """插件信息"""
    name: str
    plugin_type: PluginType
    version: str
    description: str
    instance: BasePlugin
    hooks: List[PluginHook] = field(default_factory=list)
    enabled: bool = True
    priority: int = 100  # 优先级，越小越先执行


class PluginManager:
    """
    插件管理器

    管理插件的生命周期：注册、加载、执行、卸载
    """

    def __init__(self):
        self._plugins: Dict[str, PluginInfo] = {}
        self._hook_registry: Dict[PluginHook, List[str]] = {}
        self._lock = threading.RLock()

    def register(
        self,
        plugin: BasePlugin,
        hooks: Optional[List[PluginHook]] = None,
        priority: int = 100
    ) -> bool:
        """
        注册插件

        Args:
            plugin: 插件实例
            hooks: 监听的钩子列表
            priority: 执行优先级

        Returns:
            是否注册成功
        """
        with self._lock:
            name = plugin.name
            if name in self._plugins:
                return False

            info = PluginInfo(
                name=name,
                plugin_type=plugin.plugin_type,
                version=plugin.version,
                description=plugin.description,
                instance=plugin,
                hooks=hooks or [],
                priority=priority,
            )
            self._plugins[name] = info

            # 注册钩子
            for hook in (hooks or []):
                if hook not in self._hook_registry:
                    self._hook_registry[hook] = []
                self._hook_registry[hook].append(name)

            # 按优先级排序
            for hook in self._hook_registry:
                self._hook_registry[hook].sort(
                    key=lambda n: self._plugins[n].priority
                )

            # 调用加载钩子
            plugin.on_load()
            return True

    def unregister(self, name: str) -> bool:
        """卸载插件"""
        with self._lock:
            if name not in self._plugins:
                return False

            info = self._plugins[name]
            info.instance.on_unload()

            # 移除钩子注册
            for hook in list(self._hook_registry.keys()):
                if name in self._hook_registry[hook]:
                    self._hook_registry[hook].remove(name)

            del self._plugins[name]
            return True

    def execute_hook(self, hook: PluginHook, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行指定钩子的所有插件

        Args:
            hook: 钩子点
            context: 上下文数据

        Returns:
            经过所有插件处理后的上下文
        """
        with self._lock:
            plugin_names = list(self._hook_registry.get(hook, []))

        for name in plugin_names:
            info = self._plugins.get(name)
            if info and info.enabled:
                try:
                    context = info.instance.execute(hook, context)
                except Exception as e:
                    # 插件错误不应中断链路
                    context.setdefault("_plugin_errors", []).append({
                        "plugin": name,
                        "error": str(e)
                    })

        return context

    def load_plugin_from_module(
        self,
        module_path: str,
        class_name: str,
        hooks: Optional[List[PluginHook]] = None,
        config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        从模块路径加载插件

        Args:
            module_path: 模块路径 (如 "plugins.my_plugin.MyPlugin")
            class_name: 类名
            hooks: 钩子列表
            config: 配置参数
        """
        try:
            module_name, cls_attr = module_path.rsplit(".", 1)
            module = importlib.import_module(module_name)
            plugin_class = getattr(module, cls_attr)

            if not issubclass(plugin_class, BasePlugin):
                return False

            instance = plugin_class(config or {})
            return self.register(instance, hooks=hooks)
        except Exception as e:
            print(f"加载插件失败: {e}")
            return False

    def get_plugin(self, name: str) -> Optional[PluginInfo]:
        """获取插件信息"""
        return self._plugins.get(name)

    def list_plugins(self, plugin_type: Optional[PluginType] = None) -> List[Dict[str, Any]]:
        """列出插件"""
        with self._lock:
            plugins = list(self._plugins.values())
            if plugin_type:
                plugins = [p for p in plugins if p.plugin_type == plugin_type]
            return [
                {
                    "name": p.name,
                    "type": p.plugin_type.value,
                    "version": p.version,
                    "description": p.description,
                    "enabled": p.enabled,
                    "hooks": [h.value for h in p.hooks],
                }
                for p in plugins
            ]

    def enable_plugin(self, name: str) -> bool:
        """启用插件"""
        if name in self._plugins:
            self._plugins[name].enabled = True
            return True
        return False

    def disable_plugin(self, name: str) -> bool:
        """禁用插件"""
        if name in self._plugins:
            self._plugins[name].enabled = False
            return True
        return False

    def get_stats(self) -> Dict[str, Any]:
        """获取插件统计"""
        with self._lock:
            return {
                "total_plugins": len(self._plugins),
                "enabled": sum(1 for p in self._plugins.values() if p.enabled),
                "disabled": sum(1 for p in self._plugins.values() if not p.enabled),
                "registered_hooks": len(self._hook_registry),
            }


# 全局插件管理器
_plugin_manager: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    """获取全局插件管理器"""
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
    return _plugin_manager
