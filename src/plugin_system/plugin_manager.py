#!/usr/bin/env python3
"""
插件管理器 (PluginManager) - 阶段325

职责：
- 统一管理：协调加载器、注册表、钩子、沙箱
- 配置管理：插件配置的加载、保存、验证
- 热更新：运行时重载插件，无需重启
- 健康检查：监控插件状态，自动恢复
- 生命周期编排：按依赖顺序启动/停止

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
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from plugin_system.plugin_loader import (
    PluginLoader, PluginMetadata, PluginState, LoadStrategy,
    LoadResult, get_plugin_loader
)
from plugin_system.plugin_registry import (
    PluginRegistry, RegistrationStatus, ResolveResult,
    get_plugin_registry
)
from plugin_system.plugin_hook import (
    HookManager, HookContext, HookPoint, HookAction,
    InterceptorChain, get_hook_manager, get_interceptor_chain
)
from plugin_system.plugin_sandbox import (
    PluginSandbox, SandboxLevel, Permission, ResourceLimits,
    get_plugin_sandbox
)


# ============================================================
# 数据结构
# ============================================================

class ManagerState(Enum):
    """管理器状态"""
    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    SHUTTING_DOWN = "shutting_down"
    STOPPED = "stopped"


@dataclass
class PluginConfig:
    """插件配置"""
    name: str
    enabled: bool = True
    priority: int = 100
    sandbox_level: str = "standard"
    permissions: List[str] = field(default_factory=list)
    resource_limits: Dict[str, Any] = field(default_factory=dict)
    config_data: Dict[str, Any] = field(default_factory=dict)
    auto_start: bool = True
    dependencies: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)


@dataclass
class HealthStatus:
    """健康状态"""
    name: str
    healthy: bool = True
    state: str = "unknown"
    last_check: float = 0.0
    error: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.last_check == 0.0:
            self.last_check = time.time()


@dataclass
class ManagerStats:
    """管理器统计"""
    total_plugins: int = 0
    active_plugins: int = 0
    failed_plugins: int = 0
    disabled_plugins: int = 0
    total_hook_points: int = 0
    total_handlers: int = 0
    total_violations: int = 0
    uptime_seconds: float = 0.0
    hot_reloads: int = 0


# ============================================================
# 插件管理器
# ============================================================

class PluginManagerFacade:
    """
    插件管理器（外观模式）

    统一协调 PluginLoader、PluginRegistry、HookManager、PluginSandbox
    提供高级别的插件管理接口。

    核心功能：
    1. 初始化与启动：按依赖顺序加载和激活插件
    2. 配置管理：加载/保存插件配置
    3. 热更新：运行时重载插件
    4. 健康检查：定期检查插件状态
    5. 统一查询：跨子系统的信息聚合
    """

    def __init__(self):
        self._loader = get_plugin_loader()
        self._registry = get_plugin_registry()
        self._hooks = get_hook_manager()
        self._sandbox = get_plugin_sandbox()
        self._chain = get_interceptor_chain()

        self._state = ManagerState.UNINITIALIZED
        self._lock = threading.RLock()
        self._configs: Dict[str, PluginConfig] = {}
        self._health_status: Dict[str, HealthStatus] = {}
        self._start_time: float = 0.0
        self._hot_reload_count: int = 0
        self._health_check_interval: float = 60.0
        self._health_check_callbacks: List[Callable[[HealthStatus], None]] = []

    # ---- 初始化与启动 ----

    def initialize(
        self,
        plugin_dirs: Optional[List[str]] = None,
        config_path: Optional[str] = None,
        default_sandbox_level: SandboxLevel = SandboxLevel.STANDARD
    ) -> bool:
        """
        初始化插件管理器

        Args:
            plugin_dirs: 插件搜索目录列表
            config_path: 配置文件路径
            default_sandbox_level: 默认沙箱安全级别

        Returns:
            是否初始化成功
        """
        with self._lock:
            if self._state != ManagerState.UNINITIALIZED:
                return False

            self._state = ManagerState.INITIALIZING
            self._start_time = time.time()

            try:
                # 设置默认沙箱级别
                self._sandbox.set_default_level(default_sandbox_level)

                # 加载配置
                if config_path and os.path.exists(config_path):
                    self._load_config(config_path)

                # 扫描插件目录
                if plugin_dirs:
                    for directory in plugin_dirs:
                        if os.path.isdir(directory):
                            self._loader.add_plugin_dir(directory)

                self._state = ManagerState.RUNNING
                return True

            except Exception as e:
                self._state = ManagerState.STOPPED
                return False

    def startup(self) -> Dict[str, Any]:
        """
        启动所有自动启动的插件

        按依赖顺序加载，跳过禁用的插件

        Returns:
            启动结果摘要
        """
        with self._lock:
            if self._state != ManagerState.RUNNING:
                return {"success": False, "error": "Manager not running"}

        # 解析依赖
        resolve_result = self._registry.resolve_dependencies()
        if not resolve_result.success:
            return {
                "success": False,
                "error": f"Dependency resolution failed: {resolve_result.message}",
                "missing": resolve_result.missing,
                "cycles": resolve_result.cycles,
            }

        # 按拓扑顺序加载
        results = []
        for plugin_name in resolve_result.order:
            config = self._configs.get(plugin_name)

            # 跳过禁用的插件
            if config and not config.enabled:
                results.append(LoadResult(
                    False, plugin_name, message="Disabled by config"
                ))
                continue

            # 配置沙箱
            if config:
                level = SandboxLevel(config.sandbox_level)
                permissions = {
                    Permission(p) for p in config.permissions
                } if config.permissions else None
                limits = None
                if config.resource_limits:
                    limits = ResourceLimits(**config.resource_limits)
                self._sandbox.configure(
                    plugin_name,
                    level=level,
                    permissions=permissions,
                    limits=limits,
                )

            # 加载插件
            load_config = config.config_data if config else None
            result = self._loader.load(plugin_name, load_config)
            results.append(result)

            # 注册到注册表
            if result.success:
                info = self._loader.get_plugin_info(plugin_name)
                if info:
                    self._registry.register(
                        name=plugin_name,
                        plugin_type=info.get("type", "custom"),
                        version=info.get("version", "1.0.0"),
                        priority=info.get("priority", 100),
                        dependencies=info.get("dependencies", []),
                        tags=info.get("tags", []),
                        description=info.get("description", ""),
                        instance=self._loader.get_instance(plugin_name),
                    )

                    # 分发插件加载事件
                    self._hooks.dispatch_simple(
                        HookPoint.PLUGIN_LOADED.value,
                        {"plugin_name": plugin_name},
                        source="plugin_manager",
                    )

        success_count = sum(1 for r in results if r.success)
        fail_count = sum(1 for r in results if not r.success)

        return {
            "success": True,
            "loaded": success_count,
            "failed": fail_count,
            "total": len(results),
            "results": [
                {"name": r.plugin_name, "success": r.success, "error": r.error}
                for r in results
            ],
        }

    def shutdown(self) -> Dict[str, Any]:
        """
        关闭所有插件

        按依赖的逆序卸载

        Returns:
            关闭结果摘要
        """
        with self._lock:
            if self._state != ManagerState.RUNNING:
                return {"success": False, "error": "Manager not running"}

            self._state = ManagerState.SHUTTING_DOWN

        # 逆序卸载
        resolve_result = self._registry.resolve_dependencies()
        order = list(reversed(resolve_result.order)) if resolve_result.success else []

        results = []
        for plugin_name in order:
            # 分发插件卸载事件
            self._hooks.dispatch_simple(
                HookPoint.PLUGIN_UNLOADED.value,
                {"plugin_name": plugin_name},
                source="plugin_manager",
            )

            result = self._loader.unload(plugin_name)
            results.append(result)
            self._registry.unregister(plugin_name)

        self._state = ManagerState.STOPPED

        success_count = sum(1 for r in results if r.success)
        return {
            "success": True,
            "unloaded": success_count,
            "total": len(results),
        }

    # ---- 热更新 ----

    def hot_reload(self, plugin_name: str) -> Dict[str, Any]:
        """
        热重载单个插件

        Args:
            plugin_name: 插件名称

        Returns:
            重载结果
        """
        with self._lock:
            self._hot_reload_count += 1

        # 分发重载事件
        self._hooks.dispatch_simple(
            HookPoint.ON_RELOAD.value,
            {"plugin_name": plugin_name},
            source="plugin_manager",
        )

        result = self._loader.reload(plugin_name)

        return {
            "success": result.success,
            "plugin": plugin_name,
            "message": result.message,
            "error": result.error,
            "duration_ms": result.duration_ms,
        }

    def hot_reload_all(self) -> Dict[str, Any]:
        """热重载所有已激活的插件"""
        plugins = self._loader.list_plugins(state=PluginState.ACTIVATED)
        results = []

        for plugin_info in plugins:
            name = plugin_info["name"]
            result = self.hot_reload(name)
            results.append(result)

        success_count = sum(1 for r in results if r["success"])
        return {
            "success": True,
            "reloaded": success_count,
            "total": len(results),
            "results": results,
        }

    # ---- 配置管理 ----

    def save_config(self, config_path: str) -> bool:
        """
        保存配置到文件

        Args:
            config_path: 配置文件路径

        Returns:
            是否保存成功
        """
        try:
            config_data = {
                name: {
                    "enabled": cfg.enabled,
                    "priority": cfg.priority,
                    "sandbox_level": cfg.sandbox_level,
                    "permissions": cfg.permissions,
                    "resource_limits": cfg.resource_limits,
                    "config_data": cfg.config_data,
                    "auto_start": cfg.auto_start,
                    "dependencies": cfg.dependencies,
                    "tags": cfg.tags,
                }
                for name, cfg in self._configs.items()
            }

            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)

            return True
        except Exception:
            return False

    def update_plugin_config(self, plugin_name: str, **kwargs) -> bool:
        """
        更新插件配置

        Args:
            plugin_name: 插件名称
            **kwargs: 要更新的配置字段

        Returns:
            是否更新成功
        """
        with self._lock:
            if plugin_name not in self._configs:
                self._configs[plugin_name] = PluginConfig(name=plugin_name)

            config = self._configs[plugin_name]
            for key, value in kwargs.items():
                if hasattr(config, key):
                    setattr(config, key, value)

            # 如果更新了沙箱级别，同步到沙箱
            if "sandbox_level" in kwargs:
                level = SandboxLevel(kwargs["sandbox_level"])
                self._sandbox.configure(plugin_name, level=level)

            return True

    def get_plugin_config(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """获取插件配置"""
        with self._lock:
            config = self._configs.get(plugin_name)
            if config is None:
                return None

            return {
                "name": config.name,
                "enabled": config.enabled,
                "priority": config.priority,
                "sandbox_level": config.sandbox_level,
                "permissions": config.permissions,
                "resource_limits": config.resource_limits,
                "config_data": config.config_data,
                "auto_start": config.auto_start,
                "dependencies": config.dependencies,
                "tags": config.tags,
            }

    # ---- 健康检查 ----

    def check_health(self, plugin_name: str) -> HealthStatus:
        """
        检查插件健康状态

        Args:
            plugin_name: 插件名称

        Returns:
            健康状态
        """
        info = self._loader.get_plugin_info(plugin_name)
        usage = self._sandbox.get_usage(plugin_name)
        violations = self._sandbox.get_auditor().get_violations(plugin_name, limit=5)

        healthy = True
        error = None

        if info is None:
            healthy = False
            error = "Plugin not found"
        elif info.get("state") == PluginState.FAILED.value:
            healthy = False
            error = info.get("error", "Unknown error")
        elif info.get("state") != PluginState.ACTIVATED.value:
            healthy = False
            error = f"Plugin in state: {info.get('state')}"

        status = HealthStatus(
            name=plugin_name,
            healthy=healthy,
            state=info.get("state", "unknown") if info else "not_found",
            error=error,
            metrics={
                "usage": usage,
                "recent_violations": len(violations),
            },
        )

        with self._lock:
            self._health_status[plugin_name] = status

        # 通知回调
        for cb in self._health_check_callbacks:
            try:
                cb(status)
            except Exception:
                pass

        return status

    def check_all_health(self) -> Dict[str, HealthStatus]:
        """检查所有插件健康状态"""
        plugins = self._loader.list_plugins()
        results = {}

        for plugin_info in plugins:
            name = plugin_info["name"]
            results[name] = self.check_health(name)

        return results

    def on_health_check(self, callback: Callable[[HealthStatus], None]) -> None:
        """添加健康检查回调"""
        with self._lock:
            self._health_check_callbacks.append(callback)

    # ---- 统一查询 ----

    def get_status(self) -> Dict[str, Any]:
        """获取管理器状态"""
        with self._lock:
            uptime = 0.0
            if self._start_time > 0:
                uptime = time.time() - self._start_time

            return {
                "state": self._state.value,
                "uptime_seconds": round(uptime, 2),
                "hot_reloads": self._hot_reload_count,
            }

    def get_stats(self) -> Dict[str, Any]:
        """获取综合统计信息"""
        loader_stats = self._loader.get_stats()
        registry_stats = self._registry.get_stats()
        hook_stats = self._hooks.get_stats()
        sandbox_stats = self._sandbox.get_stats()

        with self._lock:
            uptime = 0.0
            if self._start_time > 0:
                uptime = time.time() - self._start_time

        return {
            "manager": {
                "state": self._state.value,
                "uptime_seconds": round(uptime, 2),
                "hot_reloads": self._hot_reload_count,
                "configured_plugins": len(self._configs),
            },
            "loader": loader_stats,
            "registry": registry_stats,
            "hooks": hook_stats,
            "sandbox": sandbox_stats,
        }

    def get_plugin_detail(self, plugin_name: str) -> Dict[str, Any]:
        """获取插件完整详情"""
        info = self._loader.get_plugin_info(plugin_name)
        config = self.get_plugin_config(plugin_name)
        usage = self._sandbox.get_usage(plugin_name)
        health = self._health_status.get(plugin_name)

        return {
            "info": info,
            "config": config,
            "usage": usage,
            "health": {
                "healthy": health.healthy if health else None,
                "state": health.state if health else None,
                "error": health.error if health else None,
            } if health else None,
        }

    # ---- 子系统访问 ----

    @property
    def loader(self) -> PluginLoader:
        """访问插件加载器"""
        return self._loader

    @property
    def registry(self) -> PluginRegistry:
        """访问插件注册表"""
        return self._registry

    @property
    def hooks(self) -> HookManager:
        """访问钩子管理器"""
        return self._hooks

    @property
    def sandbox(self) -> PluginSandbox:
        """访问插件沙箱"""
        return self._sandbox

    @property
    def interceptor_chain(self) -> InterceptorChain:
        """访问拦截器链"""
        return self._chain

    # ---- 内部方法 ----

    def _load_config(self, config_path: str) -> None:
        """从文件加载配置"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for name, cfg_data in data.items():
                self._configs[name] = PluginConfig(
                    name=name,
                    enabled=cfg_data.get("enabled", True),
                    priority=cfg_data.get("priority", 100),
                    sandbox_level=cfg_data.get("sandbox_level", "standard"),
                    permissions=cfg_data.get("permissions", []),
                    resource_limits=cfg_data.get("resource_limits", {}),
                    config_data=cfg_data.get("config_data", {}),
                    auto_start=cfg_data.get("auto_start", True),
                    dependencies=cfg_data.get("dependencies", []),
                    tags=cfg_data.get("tags", []),
                )
        except Exception:
            pass


# ============================================================
# 全局单例
# ============================================================

_plugin_manager: Optional[PluginManagerFacade] = None
_manager_lock = threading.RLock()


def get_plugin_manager() -> PluginManagerFacade:
    """获取全局插件管理器（双重检查锁定）"""
    global _plugin_manager
    if _plugin_manager is None:
        with _manager_lock:
            if _plugin_manager is None:
                _plugin_manager = PluginManagerFacade()
    return _plugin_manager
