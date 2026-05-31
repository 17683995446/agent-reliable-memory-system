# 插件系统模块 (Plugin System)
# 阶段321-325

from plugin_system.plugin_loader import (
    PluginState, LoadStrategy, PluginSource,
    PluginMetadata, PluginInstance, LoadResult,
    PluginDiscovery, PluginLoader, get_plugin_loader
)

from plugin_system.plugin_registry import (
    RegistrationStatus, RegistrationEntry, DependencyNode, ResolveResult,
    PluginRegistry, get_plugin_registry
)

from plugin_system.plugin_hook import (
    HookPoint, HookAction, DispatchMode,
    HookContext, HandlerConfig, DispatchResult,
    HookManager, InterceptorChain,
    get_hook_manager, get_interceptor_chain
)

from plugin_system.plugin_sandbox import (
    Permission, SandboxLevel, ViolationType,
    ResourceLimits, ViolationRecord, AuditEntry,
    ResourceUsage, SandboxResult, SecurityAuditor,
    PluginSandbox, get_plugin_sandbox
)

from plugin_system.plugin_manager import (
    ManagerState, PluginConfig, HealthStatus,
    PluginManagerFacade, get_plugin_manager
)

__all__ = [
    # PluginLoader
    "PluginState", "LoadStrategy", "PluginSource",
    "PluginMetadata", "PluginInstance", "LoadResult",
    "PluginDiscovery", "PluginLoader", "get_plugin_loader",
    # PluginRegistry
    "RegistrationStatus", "RegistrationEntry", "DependencyNode", "ResolveResult",
    "PluginRegistry", "get_plugin_registry",
    # PluginHook
    "HookPoint", "HookAction", "DispatchMode",
    "HookContext", "HandlerConfig", "DispatchResult",
    "HookManager", "InterceptorChain",
    "get_hook_manager", "get_interceptor_chain",
    # PluginSandbox
    "Permission", "SandboxLevel", "ViolationType",
    "ResourceLimits", "ViolationRecord", "AuditEntry",
    "ResourceUsage", "SandboxResult", "SecurityAuditor",
    "PluginSandbox", "get_plugin_sandbox",
    # PluginManager
    "ManagerState", "PluginConfig", "HealthStatus",
    "PluginManagerFacade", "get_plugin_manager",
]
