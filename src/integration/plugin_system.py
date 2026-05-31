#!/usr/bin/env python3
"""
插件系统 - 阶段272-274

功能：
- 阶段272: 插件加载 - 注册、注销、加载插件，拓扑排序解析依赖
- 阶段273: 生命周期 - 初始化、启动、停止、清理，状态转换校验
- 阶段274: 依赖管理 - 依赖图构建、依赖检查、依赖链查询、拓扑排序

设计原则：
- 确定性算法，无模型依赖
- 线程安全，RLock保护
- 单例模式，全局唯一
"""

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Callable, Any, Optional, Set, Tuple


# ============================================================
# 枚举定义
# ============================================================

class PluginState(Enum):
    """插件状态枚举"""
    LOADED = "loaded"          # 已加载：插件信息已注册
    INITIALIZED = "initialized"  # 已初始化：init_fn已执行
    STARTED = "started"        # 已启动：start_fn已执行，可正常工作
    STOPPED = "stopped"        # 已停止：stop_fn已执行
    UNLOADED = "unloaded"      # 已卸载：cleanup_fn已执行
    ERROR = "error"            # 错误状态：生命周期函数执行异常


# ============================================================
# 数据结构定义
# ============================================================

@dataclass
class PluginInfo:
    """插件元信息"""
    plugin_id: str = ""
    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    dependencies: List[str] = field(default_factory=list)
    state: PluginState = PluginState.LOADED
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PluginHook:
    """插件钩子定义"""
    hook_name: str = ""
    handler: Callable[[Any], Any] = None
    priority: int = 0  # 优先级，数值越大优先级越高


@dataclass
class PluginContext:
    """插件运行上下文"""
    plugin_id: str = ""
    config: Dict[str, Any] = field(default_factory=dict)
    data_store: Dict[str, Any] = field(default_factory=dict)


# ============================================================
# 内部注册条目（存储生命周期函数）
# ============================================================

@dataclass
class _PluginEntry:
    """插件注册条目（内部使用）"""
    info: PluginInfo = None
    init_fn: Optional[Callable[[PluginContext], None]] = None
    start_fn: Optional[Callable[[PluginContext], None]] = None
    stop_fn: Optional[Callable[[PluginContext], None]] = None
    cleanup_fn: Optional[Callable[[PluginContext], None]] = None
    context: PluginContext = field(default_factory=PluginContext)


# ============================================================
# 阶段272: 插件加载
# ============================================================

class PluginSystem:
    """
    插件系统

    职责：
    - 阶段272: 插件注册、注销、加载，依赖解析（拓扑排序）
    - 阶段273: 插件生命周期管理（初始化、启动、停止、清理）
    - 阶段274: 依赖图管理、依赖检查、依赖链查询
    """

    def __init__(self):
        self._lock = threading.RLock()
        # 已注册的插件条目 {plugin_id: _PluginEntry}
        self._plugins: Dict[str, _PluginEntry] = {}
        # 阶段274: 依赖图 {plugin_id: set(dependency_ids)}
        self._dependency_graph: Dict[str, Set[str]] = {}
        # 反向依赖图 {plugin_id: set(dependent_ids)}
        self._reverse_dependency_graph: Dict[str, Set[str]] = {}
        # 钩子注册表 {hook_name: List[PluginHook]}
        self._hooks: Dict[str, List[PluginHook]] = {}

    # --------------------------------------------------------
    # 阶段272: 插件注册与注销
    # --------------------------------------------------------

    def register_plugin(
        self,
        info: PluginInfo,
        init_fn: Optional[Callable[[PluginContext], None]] = None,
        start_fn: Optional[Callable[[PluginContext], None]] = None,
        stop_fn: Optional[Callable[[PluginContext], None]] = None,
        cleanup_fn: Optional[Callable[[PluginContext], None]] = None,
    ) -> bool:
        """
        注册插件

        将插件信息及生命周期函数注册到系统中，初始状态为 LOADED。
        同时构建依赖图。

        Args:
            info: 插件元信息
            init_fn: 初始化函数
            start_fn: 启动函数
            stop_fn: 停止函数
            cleanup_fn: 清理函数

        Returns:
            bool: 注册是否成功
        """
        with self._lock:
            plugin_id = info.plugin_id
            if not plugin_id:
                return False
            # 不允许重复注册
            if plugin_id in self._plugins:
                return False
            # 校验依赖中的插件是否已注册（仅警告，不阻止）
            for dep_id in info.dependencies:
                if dep_id not in self._plugins:
                    pass  # 依赖尚未注册，加载时再校验

            # 创建注册条目
            entry = _PluginEntry(
                info=info,
                init_fn=init_fn,
                start_fn=start_fn,
                stop_fn=stop_fn,
                cleanup_fn=cleanup_fn,
                context=PluginContext(
                    plugin_id=plugin_id,
                    config=info.config,
                ),
            )
            self._plugins[plugin_id] = entry
            # 阶段274: 构建依赖图
            self._dependency_graph[plugin_id] = set(info.dependencies)
            # 构建反向依赖图
            for dep_id in info.dependencies:
                if dep_id not in self._reverse_dependency_graph:
                    self._reverse_dependency_graph[dep_id] = set()
                self._reverse_dependency_graph[dep_id].add(plugin_id)
            return True

    def unregister_plugin(self, plugin_id: str) -> bool:
        """
        注销插件

        仅允许在 LOADED 或 ERROR 状态下注销。
        注销后清理依赖图。

        Args:
            plugin_id: 插件标识

        Returns:
            bool: 注销是否成功
        """
        with self._lock:
            entry = self._plugins.get(plugin_id)
            if entry is None:
                return False
            # 仅允许在 LOADED 或 ERROR 状态下注销
            if entry.info.state not in (PluginState.LOADED, PluginState.ERROR):
                return False
            # 检查是否有其他插件依赖此插件
            dependents = self._reverse_dependency_graph.get(plugin_id, set())
            active_dependents = [
                d for d in dependents
                if d in self._plugins and self._plugins[d].info.state not in (PluginState.UNLOADED,)
            ]
            if active_dependents:
                return False
            # 清理依赖图
            deps = self._dependency_graph.pop(plugin_id, set())
            for dep_id in deps:
                rev_deps = self._reverse_dependency_graph.get(dep_id, set())
                rev_deps.discard(plugin_id)
            self._reverse_dependency_graph.pop(plugin_id, None)
            # 移除插件条目
            del self._plugins[plugin_id]
            return True

    def load_plugin(self, plugin_id: str) -> bool:
        """
        加载插件

        执行依赖解析，确保所有依赖已就绪后，
        自动执行 initialize -> start 完整生命周期。

        Args:
            plugin_id: 插件标识

        Returns:
            bool: 加载是否成功
        """
        with self._lock:
            entry = self._plugins.get(plugin_id)
            if entry is None:
                return False
            if entry.info.state != PluginState.LOADED:
                return False
            # 解析依赖，获取加载顺序
            load_order = self._resolve_dependencies(plugin_id)
            if load_order is None:
                # 存在循环依赖或缺失依赖
                entry.info.state = PluginState.ERROR
                return False
            # 按拓扑顺序依次初始化和启动
            for pid in load_order:
                p_entry = self._plugins.get(pid)
                if p_entry is None:
                    return False
                if p_entry.info.state == PluginState.LOADED:
                    if not self._do_initialize(pid):
                        return False
                if p_entry.info.state == PluginState.INITIALIZED:
                    if not self._do_start(pid):
                        return False
            return True

    def _resolve_dependencies(self, plugin_id: str) -> Optional[List[str]]:
        """
        解析插件依赖（拓扑排序）

        从目标插件出发，收集所有传递依赖，
        返回拓扑排序后的加载顺序（依赖在前）。

        Args:
            plugin_id: 插件标识

        Returns:
            Optional[List[str]]: 拓扑排序后的插件ID列表，失败返回None
        """
        with self._lock:
            # 收集所有相关插件（目标插件 + 所有传递依赖）
            visited: Set[str] = set()
            order: List[str] = []
            # 检测循环依赖
            in_stack: Set[str] = set()

            def _dfs(pid: str) -> bool:
                """深度优先搜索拓扑排序"""
                if pid in in_stack:
                    return False  # 循环依赖
                if pid in visited:
                    return True
                in_stack.add(pid)
                visited.add(pid)
                # 检查依赖是否存在
                entry = self._plugins.get(pid)
                if entry is None:
                    return False  # 依赖缺失
                for dep_id in entry.info.dependencies:
                    if not _dfs(dep_id):
                        return False
                in_stack.remove(pid)
                order.append(pid)
                return True

            if not _dfs(plugin_id):
                return None
            return order

    # --------------------------------------------------------
    # 阶段273: 生命周期管理
    # --------------------------------------------------------

    def initialize_plugin(self, plugin_id: str) -> bool:
        """
        初始化插件

        执行插件的 init_fn，状态从 LOADED -> INITIALIZED。

        Args:
            plugin_id: 插件标识

        Returns:
            bool: 初始化是否成功
        """
        with self._lock:
            entry = self._plugins.get(plugin_id)
            if entry is None:
                return False
            if entry.info.state != PluginState.LOADED:
                return False
            return self._do_initialize(plugin_id)

    def start_plugin(self, plugin_id: str) -> bool:
        """
        启动插件

        执行插件的 start_fn，状态从 INITIALIZED -> STARTED。

        Args:
            plugin_id: 插件标识

        Returns:
            bool: 启动是否成功
        """
        with self._lock:
            entry = self._plugins.get(plugin_id)
            if entry is None:
                return False
            if entry.info.state != PluginState.INITIALIZED:
                return False
            return self._do_start(plugin_id)

    def stop_plugin(self, plugin_id: str) -> bool:
        """
        停止插件

        执行插件的 stop_fn，状态从 STARTED -> STOPPED。
        同时停止所有依赖此插件的插件。

        Args:
            plugin_id: 插件标识

        Returns:
            bool: 停止是否成功
        """
        with self._lock:
            entry = self._plugins.get(plugin_id)
            if entry is None:
                return False
            if entry.info.state != PluginState.STARTED:
                return False
            return self._do_stop(plugin_id)

    def cleanup_plugin(self, plugin_id: str) -> bool:
        """
        清理插件

        执行插件的 cleanup_fn，状态从 STOPPED -> UNLOADED。

        Args:
            plugin_id: 插件标识

        Returns:
            bool: 清理是否成功
        """
        with self._lock:
            entry = self._plugins.get(plugin_id)
            if entry is None:
                return False
            if entry.info.state != PluginState.STOPPED:
                return False
            return self._do_cleanup(plugin_id)

    def get_plugin_state(self, plugin_id: str) -> Optional[PluginState]:
        """
        获取插件当前状态

        Args:
            plugin_id: 插件标识

        Returns:
            Optional[PluginState]: 插件状态，不存在返回None
        """
        with self._lock:
            entry = self._plugins.get(plugin_id)
            if entry is None:
                return None
            return entry.info.state

    def _transition_state(
        self,
        plugin_id: str,
        new_state: PluginState,
    ) -> bool:
        """
        状态转换校验

        合法转换路径：
        - LOADED -> INITIALIZED
        - INITIALIZED -> STARTED
        - STARTED -> STOPPED
        - STOPPED -> UNLOADED
        - 任意非UNLOADED状态 -> ERROR

        Args:
            plugin_id: 插件标识
            new_state: 目标状态

        Returns:
            bool: 转换是否合法
        """
        # 合法转换映射
        valid_transitions: Dict[PluginState, Set[PluginState]] = {
            PluginState.LOADED: {PluginState.INITIALIZED, PluginState.ERROR},
            PluginState.INITIALIZED: {PluginState.STARTED, PluginState.ERROR},
            PluginState.STARTED: {PluginState.STOPPED, PluginState.ERROR},
            PluginState.STOPPED: {PluginState.UNLOADED, PluginState.INITIALIZED, PluginState.ERROR},
            PluginState.UNLOADED: set(),
            PluginState.ERROR: set(),
        }
        entry = self._plugins.get(plugin_id)
        if entry is None:
            return False
        current_state = entry.info.state
        allowed = valid_transitions.get(current_state, set())
        if new_state not in allowed:
            return False
        entry.info.state = new_state
        return True

    # --------------------------------------------------------
    # 内部生命周期执行（不加锁，由外部方法在锁内调用）
    # --------------------------------------------------------

    def _do_initialize(self, plugin_id: str) -> bool:
        """执行初始化（内部方法，需在锁内调用）"""
        entry = self._plugins.get(plugin_id)
        if entry is None:
            return False
        if entry.init_fn is not None:
            try:
                entry.init_fn(entry.context)
            except Exception:
                self._transition_state(plugin_id, PluginState.ERROR)
                return False
        return self._transition_state(plugin_id, PluginState.INITIALIZED)

    def _do_start(self, plugin_id: str) -> bool:
        """执行启动（内部方法，需在锁内调用）"""
        entry = self._plugins.get(plugin_id)
        if entry is None:
            return False
        if entry.start_fn is not None:
            try:
                entry.start_fn(entry.context)
            except Exception:
                self._transition_state(plugin_id, PluginState.ERROR)
                return False
        return self._transition_state(plugin_id, PluginState.STARTED)

    def _do_stop(self, plugin_id: str) -> bool:
        """执行停止（内部方法，需在锁内调用）"""
        entry = self._plugins.get(plugin_id)
        if entry is None:
            return False
        # 先停止所有依赖此插件的插件
        dependents = self.get_dependents(plugin_id)
        for dep_pid in dependents:
            dep_entry = self._plugins.get(dep_pid)
            if dep_entry and dep_entry.info.state == PluginState.STARTED:
                if not self._do_stop(dep_pid):
                    # 依赖插件停止失败，标记当前插件为错误
                    self._transition_state(plugin_id, PluginState.ERROR)
                    return False
        if entry.stop_fn is not None:
            try:
                entry.stop_fn(entry.context)
            except Exception:
                self._transition_state(plugin_id, PluginState.ERROR)
                return False
        return self._transition_state(plugin_id, PluginState.STOPPED)

    def _do_cleanup(self, plugin_id: str) -> bool:
        """执行清理（内部方法，需在锁内调用）"""
        entry = self._plugins.get(plugin_id)
        if entry is None:
            return False
        if entry.cleanup_fn is not None:
            try:
                entry.cleanup_fn(entry.context)
            except Exception:
                self._transition_state(plugin_id, PluginState.ERROR)
                return False
        return self._transition_state(plugin_id, PluginState.UNLOADED)

    # --------------------------------------------------------
    # 阶段274: 依赖管理
    # --------------------------------------------------------

    def check_dependencies(self, plugin_id: str) -> bool:
        """
        检查插件的所有依赖是否满足

        所有依赖插件必须已注册且状态不为 UNLOADED。

        Args:
            plugin_id: 插件标识

        Returns:
            bool: 依赖是否全部满足
        """
        with self._lock:
            entry = self._plugins.get(plugin_id)
            if entry is None:
                return False
            for dep_id in entry.info.dependencies:
                dep_entry = self._plugins.get(dep_id)
                if dep_entry is None:
                    return False
                if dep_entry.info.state == PluginState.UNLOADED:
                    return False
            return True

    def get_dependents(self, plugin_id: str) -> List[str]:
        """
        获取直接依赖此插件的所有插件

        Args:
            plugin_id: 插件标识

        Returns:
            List[str]: 依赖此插件的插件ID列表
        """
        with self._lock:
            dependents = self._reverse_dependency_graph.get(plugin_id, set())
            return sorted(dependents)

    def get_dependency_chain(self, plugin_id: str) -> List[str]:
        """
        获取插件的完整依赖链

        返回从目标插件到所有叶子依赖的广度优先遍历结果，
        依赖项在前，目标插件在后。

        Args:
            plugin_id: 插件标识

        Returns:
            List[str]: 依赖链中的插件ID列表
        """
        with self._lock:
            entry = self._plugins.get(plugin_id)
            if entry is None:
                return []
            # 使用拓扑排序获取完整依赖链
            load_order = self._resolve_dependencies(plugin_id)
            if load_order is None:
                return []
            return load_order

    def _topological_sort(self) -> List[str]:
        """
        对所有已注册插件执行拓扑排序

        使用 Kahn 算法进行确定性拓扑排序。
        当存在多个可选节点时，按 plugin_id 字典序选择以保证确定性。

        Returns:
            List[str]: 拓扑排序后的插件ID列表
        """
        with self._lock:
            # 计算每个节点的入度
            in_degree: Dict[str, int] = {}
            for pid in self._plugins:
                in_degree[pid] = 0

            for pid, deps in self._dependency_graph.items():
                if pid not in self._plugins:
                    continue
                for dep_id in deps:
                    if dep_id in self._plugins:
                        in_degree[pid] += 1

            # 使用有序队列保证确定性（按字典序）
            queue: List[str] = sorted(
                [pid for pid, deg in in_degree.items() if deg == 0]
            )
            result: List[str] = []

            while queue:
                # 取字典序最小的节点
                current = queue.pop(0)
                result.append(current)
                # 遍历依赖当前节点的插件
                for dependent in sorted(self._reverse_dependency_graph.get(current, set())):
                    if dependent in in_degree:
                        in_degree[dependent] -= 1
                        if in_degree[dependent] == 0:
                            queue.append(dependent)
                            queue.sort()

            return result

    # --------------------------------------------------------
    # 查询方法
    # --------------------------------------------------------

    def get_plugin_info(self, plugin_id: str) -> Optional[PluginInfo]:
        """
        获取插件信息

        Args:
            plugin_id: 插件标识

        Returns:
            Optional[PluginInfo]: 插件信息，不存在返回None
        """
        with self._lock:
            entry = self._plugins.get(plugin_id)
            if entry is None:
                return None
            return entry.info

    def get_plugin_context(self, plugin_id: str) -> Optional[PluginContext]:
        """
        获取插件运行上下文

        Args:
            plugin_id: 插件标识

        Returns:
            Optional[PluginContext]: 插件上下文，不存在返回None
        """
        with self._lock:
            entry = self._plugins.get(plugin_id)
            if entry is None:
                return None
            return entry.context

    def list_plugins(self) -> List[PluginInfo]:
        """
        列出所有已注册的插件

        Returns:
            List[PluginInfo]: 插件信息列表
        """
        with self._lock:
            return [entry.info for entry in self._plugins.values()]

    def list_plugins_by_state(self, state: PluginState) -> List[PluginInfo]:
        """
        按状态列出插件

        Args:
            state: 插件状态

        Returns:
            List[PluginInfo]: 指定状态的插件信息列表
        """
        with self._lock:
            return [
                entry.info
                for entry in self._plugins.values()
                if entry.info.state == state
            ]

    def register_hook(self, hook: PluginHook) -> bool:
        """
        注册插件钩子

        Args:
            hook: 钩子定义

        Returns:
            bool: 注册是否成功
        """
        with self._lock:
            if not hook.hook_name or hook.handler is None:
                return False
            if hook.hook_name not in self._hooks:
                self._hooks[hook.hook_name] = []
            self._hooks[hook.hook_name].append(hook)
            # 按优先级降序排列
            self._hooks[hook.hook_name].sort(
                key=lambda h: h.priority, reverse=True
            )
            return True

    def unregister_hook(self, hook_name: str, handler: Callable) -> bool:
        """
        注销插件钩子

        Args:
            hook_name: 钩子名称
            handler: 处理函数

        Returns:
            bool: 注销是否成功
        """
        with self._lock:
            hooks = self._hooks.get(hook_name, [])
            original_len = len(hooks)
            self._hooks[hook_name] = [
                h for h in hooks if h.handler is not handler
            ]
            return len(self._hooks[hook_name]) < original_len

    def get_hooks(self, hook_name: str) -> List[PluginHook]:
        """
        获取指定钩子的所有处理器

        Args:
            hook_name: 钩子名称

        Returns:
            List[PluginHook]: 钩子处理器列表（按优先级降序）
        """
        with self._lock:
            return list(self._hooks.get(hook_name, []))


# ============================================================
# 全局单例
# ============================================================

_plugin_system_instance: Optional[PluginSystem] = None
_plugin_system_lock = threading.RLock()


def get_plugin_system() -> PluginSystem:
    """
    获取插件系统全局单例

    Returns:
        PluginSystem: 插件系统实例
    """
    global _plugin_system_instance
    with _plugin_system_lock:
        if _plugin_system_instance is None:
            _plugin_system_instance = PluginSystem()
        return _plugin_system_instance
