#!/usr/bin/env python3
"""
插件加载器 (PluginLoader) - 阶段321

职责：
- 插件发现：扫描目录、解析元数据、识别插件类
- 插件加载：动态导入、实例化、依赖注入
- 生命周期管理：加载、激活、停用、卸载
- 加载策略：延迟加载、预加载、按需加载

设计原则：
- 确定性规则，无模型依赖
- 线程安全（RLock）
- 最小层级，无循环依赖
"""

import importlib
import importlib.util
import inspect
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Type


# ============================================================
# 枚举与数据结构
# ============================================================

class PluginState(Enum):
    """插件生命周期状态"""
    DISCOVERED = "discovered"     # 已发现，未加载
    LOADED = "loaded"             # 已加载（模块已导入）
    INSTANTIATED = "instantiated" # 已实例化
    ACTIVATED = "activated"       # 已激活（可执行）
    DEACTIVATED = "deactivated"   # 已停用
    UNLOADED = "unloaded"         # 已卸载
    FAILED = "failed"             # 加载/激活失败


class LoadStrategy(Enum):
    """加载策略"""
    EAGER = "eager"       # 预加载：启动时全部加载
    LAZY = "lazy"         # 延迟加载：首次使用时加载
    ON_DEMAND = "on_demand"  # 按需加载：显式请求时加载


class PluginSource(Enum):
    """插件来源"""
    FILESYSTEM = "filesystem"   # 文件系统目录
    MODULE = "module"           # Python模块路径
    ENTRY_POINT = "entry_point" # 入口点（如setuptools）
    BUILTIN = "builtin"         # 内置插件


@dataclass
class PluginMetadata:
    """插件元数据（从模块属性或配置文件中提取）"""
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    plugin_type: str = "custom"
    dependencies: List[str] = field(default_factory=list)
    load_strategy: LoadStrategy = LoadStrategy.EAGER
    priority: int = 100
    source: PluginSource = PluginSource.FILESYSTEM
    module_path: str = ""
    class_name: str = ""
    config_schema: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)


@dataclass
class PluginInstance:
    """插件实例记录"""
    metadata: PluginMetadata
    state: PluginState = PluginState.DISCOVERED
    instance: Any = None
    module: Any = None
    error: Optional[str] = None
    loaded_at: Optional[float] = None
    activated_at: Optional[float] = None
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LoadResult:
    """加载结果"""
    success: bool
    plugin_name: str
    message: str = ""
    error: Optional[str] = None
    duration_ms: float = 0.0


# ============================================================
# 插件发现器
# ============================================================

class PluginDiscovery:
    """
    插件发现器

    扫描指定目录，识别包含插件类的Python模块。
    通过约定优于配置的方式识别插件：
    - 模块中定义了继承自 BasePlugin 的类
    - 或模块包含 __plugin_metadata__ 属性
    """

    def __init__(self):
        self._discovered: Dict[str, PluginMetadata] = {}
        self._lock = threading.RLock()

    def scan_directory(
        self,
        directory: str,
        recursive: bool = True,
        pattern: str = "*.py"
    ) -> List[PluginMetadata]:
        """
        扫描目录发现插件

        Args:
            directory: 要扫描的目录路径
            recursive: 是否递归扫描子目录
            pattern: 文件匹配模式

        Returns:
            发现的插件元数据列表
        """
        if not os.path.isdir(directory):
            return []

        results = []
        with self._lock:
            if recursive:
                for root, dirs, files in os.walk(directory):
                    # 跳过 __pycache__ 和隐藏目录
                    dirs[:] = [d for d in dirs if not d.startswith('_') and not d.startswith('.')]
                    for fname in files:
                        if self._match_pattern(fname, pattern):
                            meta = self._inspect_file(os.path.join(root, fname))
                            if meta:
                                results.append(meta)
                                self._discovered[meta.name] = meta
            else:
                for fname in os.listdir(directory):
                    fpath = os.path.join(directory, fname)
                    if os.path.isfile(fpath) and self._match_pattern(fname, pattern):
                        meta = self._inspect_file(fpath)
                        if meta:
                            results.append(meta)
                            self._discovered[meta.name] = meta

        return results

    def inspect_module_path(self, module_path: str, class_name: str = "") -> Optional[PluginMetadata]:
        """
        检查模块路径中的插件

        Args:
            module_path: 完整模块路径 (如 "package.module.ClassName")
            class_name: 可选，显式指定类名

        Returns:
            插件元数据或None
        """
        try:
            parts = module_path.rsplit(".", 1)
            if len(parts) == 2:
                mod_path, cls_name = parts
            else:
                return None

            if class_name:
                cls_name = class_name

            return PluginMetadata(
                name=cls_name,
                module_path=mod_path,
                class_name=cls_name,
                source=PluginSource.MODULE
            )
        except Exception:
            return None

    def get_discovered(self) -> Dict[str, PluginMetadata]:
        """获取所有已发现的插件"""
        with self._lock:
            return dict(self._discovered)

    def clear(self):
        """清除发现缓存"""
        with self._lock:
            self._discovered.clear()

    def _match_pattern(self, filename: str, pattern: str) -> bool:
        """匹配文件名模式"""
        if pattern == "*.py":
            return filename.endswith(".py") and filename != "__init__.py"
        import fnmatch
        return fnmatch.fnmatch(filename, pattern)

    def _inspect_file(self, filepath: str) -> Optional[PluginMetadata]:
        """
        检查文件是否包含插件定义

        通过读取源码中的 __plugin_metadata__ 或分析类定义
        """
        try:
            basename = os.path.basename(filepath)
            if basename.startswith("_") or not basename.endswith(".py"):
                return None

            module_name = basename[:-3]

            # 尝试从文件中提取元数据
            metadata = self._extract_metadata(filepath, module_name)
            return metadata
        except Exception:
            return None

    def _extract_metadata(self, filepath: str, module_name: str) -> Optional[PluginMetadata]:
        """从文件中提取插件元数据"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                source = f.read()

            # 检查是否包含 __plugin_metadata__
            if '__plugin_metadata__' in source:
                return self._parse_metadata_from_source(source, filepath, module_name)

            # 检查是否包含 BasePlugin 子类
            if 'BasePlugin' in source or 'Plugin' in source:
                return PluginMetadata(
                    name=module_name,
                    module_path=filepath,
                    class_name="",
                    source=PluginSource.FILESYSTEM
                )

            return None
        except Exception:
            return None

    def _parse_metadata_from_source(
        self,
        source: str,
        filepath: str,
        module_name: str
    ) -> Optional[PluginMetadata]:
        """从源码中解析 __plugin_metadata__ 字典"""
        try:
            # 安全地提取元数据字典
            import ast
            tree = ast.parse(source)

            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == '__plugin_metadata__':
                            if isinstance(node.value, ast.Dict):
                                meta_dict = self._ast_dict_to_python(node.value)
                                return PluginMetadata(
                                    name=meta_dict.get('name', module_name),
                                    version=meta_dict.get('version', '1.0.0'),
                                    description=meta_dict.get('description', ''),
                                    author=meta_dict.get('author', ''),
                                    plugin_type=meta_dict.get('type', 'custom'),
                                    dependencies=meta_dict.get('dependencies', []),
                                    priority=meta_dict.get('priority', 100),
                                    tags=meta_dict.get('tags', []),
                                    module_path=filepath,
                                    class_name=meta_dict.get('class', ''),
                                    source=PluginSource.FILESYSTEM
                                )
            return None
        except Exception:
            return None

    def _ast_dict_to_python(self, dict_node: 'ast.Dict') -> Dict[str, Any]:
        """将AST字典节点转换为Python字典"""
        result = {}
        keys = dict_node.keys
        values = dict_node.values

        for k, v in zip(keys, values):
            key = self._ast_value_to_python(k)
            val = self._ast_value_to_python(v)
            if key is not None:
                result[str(key)] = val

        return result

    def _ast_value_to_python(self, node: 'ast.AST') -> Any:
        """将AST值节点转换为Python值"""
        import ast
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Str):
            return node.s
        elif isinstance(node, ast.Num):
            return node.n
        elif isinstance(node, ast.List):
            return [self._ast_value_to_python(e) for e in node.elts]
        elif isinstance(node, ast.NameConstant):
            return node.value
        return None


# ============================================================
# 插件加载器
# ============================================================

class PluginLoader:
    """
    插件加载器

    核心职责：
    1. 插件发现与元数据提取
    2. 动态模块导入与类实例化
    3. 生命周期状态转换
    4. 加载超时与错误隔离
    5. 依赖感知加载顺序

    状态机：
    DISCOVERED -> LOADED -> INSTANTIATED -> ACTIVATED
                                              |
                                              v
                                          DEACTIVATED -> UNLOADED
    """

    def __init__(self):
        self._instances: Dict[str, PluginInstance] = {}
        self._discovery = PluginDiscovery()
        self._lock = threading.RLock()
        self._load_hooks: List[Callable[[str, PluginInstance], None]] = []
        self._unload_hooks: List[Callable[[str, PluginInstance], None]] = []
        self._base_class: Optional[type] = None
        self._plugin_dirs: List[str] = []
        self._load_timeout: float = 30.0  # 加载超时（秒）

    def set_base_class(self, base_class: type) -> None:
        """设置插件基类（用于识别插件）"""
        self._base_class = base_class

    def add_plugin_dir(self, directory: str) -> int:
        """
        添加插件搜索目录

        Args:
            directory: 目录路径

        Returns:
            发现的插件数量
        """
        with self._lock:
            if directory not in self._plugin_dirs:
                self._plugin_dirs.append(directory)
            metas = self._discovery.scan_directory(directory)
            for meta in metas:
                if meta.name not in self._instances:
                    self._instances[meta.name] = PluginInstance(metadata=meta)
            return len(metas)

    def discover(self, directory: str, recursive: bool = True) -> List[PluginMetadata]:
        """发现插件（不加载）"""
        return self._discovery.scan_directory(directory, recursive)

    def load(self, plugin_name: str, config: Optional[Dict[str, Any]] = None) -> LoadResult:
        """
        加载插件

        执行完整加载流程：导入模块 -> 实例化类 -> 调用on_load

        Args:
            plugin_name: 插件名称
            config: 可选配置

        Returns:
            加载结果
        """
        start = time.monotonic()

        with self._lock:
            inst = self._instances.get(plugin_name)
            if inst is None:
                return LoadResult(False, plugin_name, error=f"Plugin '{plugin_name}' not found")

            if inst.state == PluginState.FAILED:
                return LoadResult(False, plugin_name, error=f"Plugin '{plugin_name}' in FAILED state: {inst.error}")

            if inst.state in (PluginState.ACTIVATED, PluginState.INSTANTIATED):
                return LoadResult(True, plugin_name, message="Already loaded", duration_ms=0)

            try:
                # Step 1: 导入模块
                if inst.state == PluginState.DISCOVERED:
                    self._load_module(inst)
                    inst.state = PluginState.LOADED

                # Step 2: 实例化
                if inst.state == PluginState.LOADED:
                    self._instantiate(inst, config or {})
                    inst.state = PluginState.INSTANTIATED
                    inst.loaded_at = time.time()

                # Step 3: 激活
                if inst.state == PluginState.INSTANTIATED:
                    self._activate(inst)
                    inst.state = PluginState.ACTIVATED
                    inst.activated_at = time.time()

                # 通知加载钩子
                for hook in self._load_hooks:
                    try:
                        hook(plugin_name, inst)
                    except Exception:
                        pass

                duration = (time.monotonic() - start) * 1000
                return LoadResult(True, plugin_name, message="Loaded successfully", duration_ms=duration)

            except Exception as e:
                inst.state = PluginState.FAILED
                inst.error = str(e)
                duration = (time.monotonic() - start) * 1000
                return LoadResult(False, plugin_name, error=str(e), duration_ms=duration)

    def load_all(self, strategy: LoadStrategy = LoadStrategy.EAGER) -> List[LoadResult]:
        """
        批量加载所有已发现的插件

        Args:
            strategy: 加载策略

        Returns:
            加载结果列表
        """
        results = []

        with self._lock:
            names = list(self._instances.keys())

        for name in names:
            inst = self._instances.get(name)
            if inst is None:
                continue

            if strategy == LoadStrategy.LAZY and inst.metadata.load_strategy == LoadStrategy.LAZY:
                continue

            result = self.load(name)
            results.append(result)

        return results

    def unload(self, plugin_name: str) -> LoadResult:
        """
        卸载插件

        执行卸载流程：停用 -> 调用on_unload -> 清理引用

        Args:
            plugin_name: 插件名称

        Returns:
            卸载结果
        """
        start = time.monotonic()

        with self._lock:
            inst = self._instances.get(plugin_name)
            if inst is None:
                return LoadResult(False, plugin_name, error=f"Plugin '{plugin_name}' not found")

            try:
                # 停用
                if inst.state == PluginState.ACTIVATED:
                    self._deactivate(inst)
                    inst.state = PluginState.DEACTIVATED

                # 卸载
                if inst.state == PluginState.DEACTIVATED:
                    if inst.instance and hasattr(inst.instance, 'on_unload'):
                        try:
                            inst.instance.on_unload()
                        except Exception:
                            pass
                    inst.instance = None
                    inst.module = None
                    inst.state = PluginState.UNLOADED

                # 通知卸载钩子
                for hook in self._unload_hooks:
                    try:
                        hook(plugin_name, inst)
                    except Exception:
                        pass

                duration = (time.monotonic() - start) * 1000
                return LoadResult(True, plugin_name, message="Unloaded successfully", duration_ms=duration)

            except Exception as e:
                inst.state = PluginState.FAILED
                inst.error = str(e)
                duration = (time.monotonic() - start) * 1000
                return LoadResult(False, plugin_name, error=str(e), duration_ms=duration)

    def reload(self, plugin_name: str) -> LoadResult:
        """
        热重载插件

        先卸载再重新加载

        Args:
            plugin_name: 插件名称

        Returns:
            重载结果
        """
        unload_result = self.unload(plugin_name)
        if not unload_result.success:
            return LoadResult(False, plugin_name, error=f"Unload failed: {unload_result.error}")

        # 重置状态为 DISCOVERED
        with self._lock:
            inst = self._instances.get(plugin_name)
            if inst:
                inst.state = PluginState.DISCOVERED
                inst.error = None

        return self.load(plugin_name)

    def get_instance(self, plugin_name: str) -> Optional[Any]:
        """获取插件实例"""
        with self._lock:
            inst = self._instances.get(plugin_name)
            if inst and inst.state == PluginState.ACTIVATED:
                return inst.instance
            return None

    def get_plugin_info(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """获取插件详细信息"""
        with self._lock:
            inst = self._instances.get(plugin_name)
            if inst is None:
                return None

            return {
                "name": inst.metadata.name,
                "version": inst.metadata.version,
                "description": inst.metadata.description,
                "author": inst.metadata.author,
                "type": inst.metadata.plugin_type,
                "state": inst.state.value,
                "source": inst.metadata.source.value,
                "priority": inst.metadata.priority,
                "dependencies": inst.metadata.dependencies,
                "tags": inst.metadata.tags,
                "loaded_at": inst.loaded_at,
                "activated_at": inst.activated_at,
                "error": inst.error,
            }

    def list_plugins(
        self,
        state: Optional[PluginState] = None,
        plugin_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        列出插件

        Args:
            state: 按状态过滤
            plugin_type: 按类型过滤

        Returns:
            插件信息列表
        """
        with self._lock:
            results = []
            for name, inst in self._instances.items():
                if state and inst.state != state:
                    continue
                if plugin_type and inst.metadata.plugin_type != plugin_type:
                    continue
                results.append({
                    "name": inst.metadata.name,
                    "version": inst.metadata.version,
                    "type": inst.metadata.plugin_type,
                    "state": inst.state.value,
                    "priority": inst.metadata.priority,
                })
            return results

    def add_load_hook(self, hook: Callable[[str, PluginInstance], None]) -> None:
        """添加加载完成钩子"""
        with self._lock:
            self._load_hooks.append(hook)

    def add_unload_hook(self, hook: Callable[[str, PluginInstance], None]) -> None:
        """添加卸载完成钩子"""
        with self._lock:
            self._unload_hooks.append(hook)

    def get_stats(self) -> Dict[str, Any]:
        """获取加载器统计信息"""
        with self._lock:
            state_counts = {}
            for inst in self._instances.values():
                s = inst.state.value
                state_counts[s] = state_counts.get(s, 0) + 1

            return {
                "total_discovered": len(self._instances),
                "state_distribution": state_counts,
                "plugin_dirs": len(self._plugin_dirs),
                "load_hooks": len(self._load_hooks),
                "unload_hooks": len(self._unload_hooks),
            }

    # ---- 内部方法 ----

    def _load_module(self, inst: PluginInstance) -> None:
        """加载插件模块"""
        meta = inst.metadata

        if meta.source == PluginSource.MODULE and meta.module_path:
            # 从模块路径导入
            module = importlib.import_module(meta.module_path)
            inst.module = module
        elif meta.source == PluginSource.FILESYSTEM and meta.module_path:
            # 从文件路径导入
            spec = importlib.util.spec_from_file_location(
                f"_plugin_{meta.name}",
                meta.module_path
            )
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[f"_plugin_{meta.name}"] = module
                spec.loader.exec_module(module)
                inst.module = module
        else:
            raise RuntimeError(f"Cannot load plugin '{meta.name}': no valid source")

    def _instantiate(self, inst: PluginInstance, config: Dict[str, Any]) -> None:
        """实例化插件类"""
        module = inst.module
        meta = inst.metadata

        if module is None:
            raise RuntimeError(f"Module not loaded for '{meta.name}'")

        # 确定要实例化的类
        plugin_class = None

        if meta.class_name:
            plugin_class = getattr(module, meta.class_name, None)
        else:
            # 自动发现：查找 BasePlugin 子类
            plugin_class = self._find_plugin_class(module)

        if plugin_class is None:
            raise RuntimeError(f"No plugin class found in '{meta.name}'")

        # 实例化
        try:
            instance = plugin_class(**config) if config else plugin_class()
        except TypeError:
            instance = plugin_class()

        inst.instance = instance
        inst.config = config

    def _activate(self, inst: PluginInstance) -> None:
        """激活插件"""
        instance = inst.instance
        if instance and hasattr(instance, 'on_load'):
            instance.on_load()

    def _deactivate(self, inst: PluginInstance) -> None:
        """停用插件"""
        instance = inst.instance
        if instance and hasattr(instance, 'on_deactivate'):
            try:
                instance.on_deactivate()
            except Exception:
                pass

    def _find_plugin_class(self, module: Any) -> Optional[type]:
        """在模块中查找插件类"""
        if self._base_class is not None:
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, self._base_class) and obj is not self._base_class:
                    return obj

        # 回退：查找包含 "Plugin" 的类
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if 'Plugin' in name and obj.__module__ == module.__name__:
                return obj

        return None


# ============================================================
# 全局单例
# ============================================================

_plugin_loader: Optional[PluginLoader] = None
_loader_lock = threading.RLock()


def get_plugin_loader() -> PluginLoader:
    """获取全局插件加载器（双重检查锁定）"""
    global _plugin_loader
    if _plugin_loader is None:
        with _loader_lock:
            if _plugin_loader is None:
                _plugin_loader = PluginLoader()
    return _plugin_loader
