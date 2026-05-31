#!/usr/bin/env python3
"""
插件注册表 (PluginRegistry) - 阶段322

职责：
- 插件注册：注册/注销插件条目
- 依赖解析：拓扑排序，检测循环依赖
- 优先级排序：按优先级确定执行顺序
- 分类管理：按类型、标签、状态分组
- 查询检索：名称搜索、模糊匹配、过滤

设计原则：
- 确定性规则，无模型依赖
- 线程安全（RLock）
- 最小层级，无循环依赖
"""

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


# ============================================================
# 数据结构
# ============================================================

class RegistrationStatus(Enum):
    """注册状态"""
    PENDING = "pending"       # 待审核
    REGISTERED = "registered" # 已注册
    SUSPENDED = "suspended"   # 已暂停
    REJECTED = "rejected"     # 已拒绝


@dataclass
class RegistrationEntry:
    """注册条目"""
    name: str
    plugin_type: str
    version: str
    priority: int = 100
    dependencies: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    description: str = ""
    author: str = ""
    status: RegistrationStatus = RegistrationStatus.REGISTERED
    registered_at: float = 0.0
    updated_at: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    instance: Any = None


@dataclass
class DependencyNode:
    """依赖图节点"""
    name: str
    dependencies: Set[str] = field(default_factory=set)
    dependents: Set[str] = field(default_factory=set)


@dataclass
class ResolveResult:
    """依赖解析结果"""
    success: bool
    order: List[str] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)
    cycles: List[List[str]] = field(default_factory=list)
    message: str = ""


# ============================================================
# 插件注册表
# ============================================================

class PluginRegistry:
    """
    插件注册表

    核心功能：
    1. 插件注册与注销
    2. 依赖图构建与拓扑排序
    3. 循环依赖检测
    4. 优先级排序
    5. 分类查询与过滤
    6. 注册事件通知
    """

    def __init__(self):
        self._entries: Dict[str, RegistrationEntry] = {}
        self._dep_graph: Dict[str, DependencyNode] = {}
        self._type_index: Dict[str, Set[str]] = defaultdict(set)
        self._tag_index: Dict[str, Set[str]] = defaultdict(set)
        self._lock = threading.RLock()
        self._register_callbacks: List[Callable[[RegistrationEntry], None]] = []
        self._unregister_callbacks: List[Callable[[str], None]] = []

    # ---- 注册/注销 ----

    def register(
        self,
        name: str,
        plugin_type: str,
        version: str = "1.0.0",
        priority: int = 100,
        dependencies: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        description: str = "",
        author: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        instance: Any = None,
        status: RegistrationStatus = RegistrationStatus.REGISTERED
    ) -> bool:
        """
        注册插件

        Args:
            name: 插件名称（唯一标识）
            plugin_type: 插件类型
            version: 版本号
            priority: 优先级（越小越先执行）
            dependencies: 依赖的插件名称列表
            tags: 标签列表
            description: 描述
            author: 作者
            metadata: 额外元数据
            instance: 插件实例引用
            status: 注册状态

        Returns:
            是否注册成功
        """
        with self._lock:
            if name in self._entries:
                return False

            now = time.time()
            entry = RegistrationEntry(
                name=name,
                plugin_type=plugin_type,
                version=version,
                priority=priority,
                dependencies=dependencies or [],
                tags=tags or [],
                description=description,
                author=author,
                status=status,
                registered_at=now,
                updated_at=now,
                metadata=metadata or {},
                instance=instance,
            )

            self._entries[name] = entry

            # 更新索引
            self._type_index[plugin_type].add(name)
            for tag in entry.tags:
                self._tag_index[tag].add(name)

            # 更新依赖图
            self._update_dep_graph(name, entry.dependencies)

            # 通知回调
            for cb in self._register_callbacks:
                try:
                    cb(entry)
                except Exception:
                    pass

            return True

    def unregister(self, name: str) -> bool:
        """
        注销插件

        Args:
            name: 插件名称

        Returns:
            是否注销成功
        """
        with self._lock:
            entry = self._entries.pop(name, None)
            if entry is None:
                return False

            # 更新索引
            self._type_index[entry.plugin_type].discard(name)
            for tag in entry.tags:
                self._tag_index[tag].discard(name)

            # 更新依赖图
            self._remove_from_dep_graph(name)

            # 通知回调
            for cb in self._unregister_callbacks:
                try:
                    cb(name)
                except Exception:
                    pass

            return True

    def update(self, name: str, **kwargs) -> bool:
        """
        更新插件注册信息

        Args:
            name: 插件名称
            **kwargs: 要更新的字段

        Returns:
            是否更新成功
        """
        with self._lock:
            entry = self._entries.get(name)
            if entry is None:
                return False

            for key, value in kwargs.items():
                if hasattr(entry, key):
                    setattr(entry, key, value)

            entry.updated_at = time.time()

            # 如果更新了依赖，重建依赖图
            if 'dependencies' in kwargs:
                self._remove_from_dep_graph(name)
                self._update_dep_graph(name, entry.dependencies)

            # 如果更新了标签，重建标签索引
            if 'tags' in kwargs:
                for tag in entry.tags:
                    self._tag_index[tag].discard(name)
                for tag in entry.tags:
                    self._tag_index[tag].add(name)

            return True

    # ---- 查询 ----

    def get(self, name: str) -> Optional[RegistrationEntry]:
        """获取注册条目"""
        with self._lock:
            return self._entries.get(name)

    def get_instance(self, name: str) -> Optional[Any]:
        """获取插件实例"""
        with self._lock:
            entry = self._entries.get(name)
            return entry.instance if entry else None

    def contains(self, name: str) -> bool:
        """检查插件是否已注册"""
        with self._lock:
            return name in self._entries

    def list_all(self) -> List[Dict[str, Any]]:
        """列出所有注册插件"""
        with self._lock:
            return [
                {
                    "name": e.name,
                    "type": e.plugin_type,
                    "version": e.version,
                    "priority": e.priority,
                    "status": e.status.value,
                    "dependencies": e.dependencies,
                    "tags": e.tags,
                    "registered_at": e.registered_at,
                }
                for e in self._entries.values()
            ]

    def list_by_type(self, plugin_type: str) -> List[str]:
        """按类型列出插件名称"""
        with self._lock:
            return list(self._type_index.get(plugin_type, set()))

    def list_by_tag(self, tag: str) -> List[str]:
        """按标签列出插件名称"""
        with self._lock:
            return list(self._tag_index.get(tag, set()))

    def list_by_status(self, status: RegistrationStatus) -> List[str]:
        """按状态列出插件名称"""
        with self._lock:
            return [e.name for e in self._entries.values() if e.status == status]

    def search(self, prefix: str, limit: int = 20) -> List[str]:
        """
        搜索插件（前缀匹配）

        Args:
            prefix: 名称前缀
            limit: 最大返回数量

        Returns:
            匹配的插件名称列表
        """
        with self._lock:
            results = [
                name for name in self._entries
                if name.startswith(prefix) or prefix.lower() in name.lower()
            ]
            return results[:limit]

    def filter_plugins(
        self,
        plugin_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        status: Optional[RegistrationStatus] = None,
        min_priority: Optional[int] = None,
        max_priority: Optional[int] = None
    ) -> List[str]:
        """
        多条件过滤插件

        Args:
            plugin_type: 按类型过滤
            tags: 按标签过滤（AND关系）
            status: 按状态过滤
            min_priority: 最小优先级
            max_priority: 最大优先级

        Returns:
            匹配的插件名称列表
        """
        with self._lock:
            results = []

            for name, entry in self._entries.items():
                if plugin_type and entry.plugin_type != plugin_type:
                    continue
                if tags and not all(t in entry.tags for t in tags):
                    continue
                if status and entry.status != status:
                    continue
                if min_priority is not None and entry.priority < min_priority:
                    continue
                if max_priority is not None and entry.priority > max_priority:
                    continue
                results.append(name)

            return results

    # ---- 依赖解析 ----

    def resolve_dependencies(self, target: Optional[str] = None) -> ResolveResult:
        """
        解析依赖关系，返回拓扑排序结果

        Args:
            target: 目标插件（None表示解析全部）

        Returns:
            解析结果
        """
        with self._lock:
            if target:
                if target not in self._entries:
                    return ResolveResult(False, missing=[target], message=f"Plugin '{target}' not found")
                # 只解析目标及其依赖
                needed = self._collect_dependencies(target)
            else:
                needed = set(self._entries.keys())

            # 检查缺失依赖
            missing = []
            for name in needed:
                entry = self._entries.get(name)
                if entry:
                    for dep in entry.dependencies:
                        if dep not in self._entries:
                            missing.append(dep)

            if missing:
                return ResolveResult(
                    False,
                    missing=list(set(missing)),
                    message=f"Missing dependencies: {missing}"
                )

            # 拓扑排序
            order, cycles = self._topological_sort(needed)

            if cycles:
                return ResolveResult(
                    False,
                    cycles=cycles,
                    message=f"Circular dependencies detected: {cycles}"
                )

            return ResolveResult(True, order=order, message="Dependencies resolved")

    def get_dependencies(self, name: str) -> List[str]:
        """获取插件的直接依赖"""
        with self._lock:
            entry = self._entries.get(name)
            return list(entry.dependencies) if entry else []

    def get_dependents(self, name: str) -> List[str]:
        """获取依赖此插件的其他插件"""
        with self._lock:
            node = self._dep_graph.get(name)
            return list(node.dependents) if node else []

    def has_circular_dependency(self) -> Tuple[bool, List[List[str]]]:
        """
        检测循环依赖

        Returns:
            (是否存在循环, 循环路径列表)
        """
        with self._lock:
            _, cycles = self._topological_sort(set(self._entries.keys()))
            return (len(cycles) > 0, cycles)

    # ---- 优先级排序 ----

    def get_sorted_by_priority(
        self,
        plugin_type: Optional[str] = None,
        ascending: bool = True
    ) -> List[str]:
        """
        按优先级排序获取插件列表

        Args:
            plugin_type: 按类型过滤
            ascending: 是否升序（True=优先级小的先执行）

        Returns:
            排序后的插件名称列表
        """
        with self._lock:
            plugins = list(self._entries.values())

            if plugin_type:
                plugins = [p for p in plugins if p.plugin_type == plugin_type]

            plugins.sort(key=lambda e: e.priority, reverse=not ascending)
            return [p.name for p in plugins]

    # ---- 事件回调 ----

    def on_register(self, callback: Callable[[RegistrationEntry], None]) -> None:
        """注册注册事件回调"""
        with self._lock:
            self._register_callbacks.append(callback)

    def on_unregister(self, callback: Callable[[str], None]) -> None:
        """注册注销事件回调"""
        with self._lock:
            self._unregister_callbacks.append(callback)

    # ---- 统计 ----

    def get_stats(self) -> Dict[str, Any]:
        """获取注册表统计信息"""
        with self._lock:
            type_counts = {}
            for t, names in self._type_index.items():
                type_counts[t] = len(names)

            status_counts = {}
            for entry in self._entries.values():
                s = entry.status.value
                status_counts[s] = status_counts.get(s, 0) + 1

            return {
                "total_registered": len(self._entries),
                "type_distribution": type_counts,
                "status_distribution": status_counts,
                "total_tags": len(self._tag_index),
                "dependency_edges": sum(
                    len(node.dependencies) for node in self._dep_graph.values()
                ),
            }

    # ---- 内部方法 ----

    def _update_dep_graph(self, name: str, dependencies: List[str]) -> None:
        """更新依赖图"""
        if name not in self._dep_graph:
            self._dep_graph[name] = DependencyNode(name=name)

        node = self._dep_graph[name]
        node.dependencies = set(dependencies)

        for dep in dependencies:
            if dep not in self._dep_graph:
                self._dep_graph[dep] = DependencyNode(name=dep)
            self._dep_graph[dep].dependents.add(name)

    def _remove_from_dep_graph(self, name: str) -> None:
        """从依赖图中移除节点"""
        node = self._dep_graph.pop(name, None)
        if node:
            for dep in node.dependencies:
                dep_node = self._dep_graph.get(dep)
                if dep_node:
                    dep_node.dependents.discard(name)
            for dependent in node.dependents:
                dep_node = self._dep_graph.get(dependent)
                if dep_node:
                    dep_node.dependencies.discard(name)

    def _collect_dependencies(self, target: str) -> Set[str]:
        """收集目标及其所有传递依赖"""
        needed = set()
        queue = deque([target])

        while queue:
            name = queue.popleft()
            if name in needed:
                continue
            needed.add(name)

            entry = self._entries.get(name)
            if entry:
                for dep in entry.dependencies:
                    if dep not in needed:
                        queue.append(dep)

        return needed

    def _topological_sort(self, nodes: Set[str]) -> Tuple[List[str], List[List[str]]]:
        """
        拓扑排序（Kahn算法）

        Returns:
            (排序结果, 检测到的循环路径)
        """
        # 计算入度
        in_degree = {n: 0 for n in nodes}
        adj = {n: [] for n in nodes}

        for name in nodes:
            entry = self._entries.get(name)
            if entry:
                for dep in entry.dependencies:
                    if dep in nodes:
                        in_degree[name] = in_degree.get(name, 0) + 1
                        adj[dep].append(name)

        # 从入度为0的节点开始
        queue = deque()
        for n in nodes:
            if in_degree.get(n, 0) == 0:
                queue.append(n)

        order = []
        while queue:
            node = queue.popleft()
            order.append(node)

            for neighbor in adj.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # 检测循环
        cycles = []
        if len(order) != len(nodes):
            remaining = nodes - set(order)
            cycle = self._find_cycle(remaining)
            if cycle:
                cycles.append(cycle)

        return order, cycles

    def _find_cycle(self, nodes: Set[str]) -> List[str]:
        """在给定节点中查找循环"""
        visited = set()
        path = []
        path_set = set()

        def dfs(node: str) -> Optional[List[str]]:
            if node in path_set:
                idx = path.index(node)
                return path[idx:] + [node]
            if node in visited:
                return None

            visited.add(node)
            path.append(node)
            path_set.add(node)

            entry = self._entries.get(node)
            if entry:
                for dep in entry.dependencies:
                    if dep in nodes:
                        result = dfs(dep)
                        if result:
                            return result

            path.pop()
            path_set.discard(node)
            return None

        for node in nodes:
            result = dfs(node)
            if result:
                return result

        return []


# ============================================================
# 全局单例
# ============================================================

_plugin_registry: Optional[PluginRegistry] = None
_registry_lock = threading.RLock()


def get_plugin_registry() -> PluginRegistry:
    """获取全局插件注册表（双重检查锁定）"""
    global _plugin_registry
    if _plugin_registry is None:
        with _registry_lock:
            if _plugin_registry is None:
                _plugin_registry = PluginRegistry()
    return _plugin_registry
