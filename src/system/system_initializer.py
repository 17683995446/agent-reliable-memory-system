"""
系统初始化器

第296-297阶段：组件初始化、依赖注入、启动顺序
遵循"图难于其易，为大于其细"原则，实现细粒度的系统初始化管理
"""

import threading
from typing import Dict, List, Set, Optional, Callable, Any, Type
from dataclasses import dataclass, field
from enum import Enum
from collections import deque


class InitializationState(Enum):
    """初始化状态"""
    UNINITIALIZED = "uninitialized"      # 未初始化
    INITIALIZING = "initializing"        # 初始化中
    INITIALIZED = "initialized"          # 已初始化
    FAILED = "failed"                    # 初始化失败
    DESTROYED = "destroyed"              # 已销毁


class ComponentPriority(Enum):
    """组件优先级"""
    CRITICAL = 0      # 关键组件（最先初始化）
    HIGH = 1          # 高优先级
    NORMAL = 2        # 普通优先级
    LOW = 3           # 低优先级
    OPTIONAL = 4      # 可选组件（最后初始化）


@dataclass
class ComponentInfo:
    """组件信息"""
    name: str
    component_class: Type
    instance: Optional[Any] = None
    state: InitializationState = InitializationState.UNINITIALIZED
    priority: ComponentPriority = ComponentPriority.NORMAL
    dependencies: Set[str] = field(default_factory=set)
    init_func: Optional[Callable] = None
    destroy_func: Optional[Callable] = None
    config: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    init_order: int = -1


@dataclass
class DependencyInfo:
    """依赖信息"""
    name: str
    required_type: Optional[Type] = None
    required: bool = True
    lazy: bool = False
    factory: Optional[Callable] = None


class SystemInitializer:
    """
    系统初始化器
    
    职责：
    1. 组件注册与管理
    2. 依赖注入
    3. 按依赖顺序初始化
    4. 优雅销毁
    
    设计原则：
    - 拓扑排序确保依赖顺序
    - 支持循环依赖检测
    - 细粒度状态管理
    """
    
    _instance: Optional['SystemInitializer'] = None
    _lock = threading.RLock()
    
    def __new__(cls) -> 'SystemInitializer':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        # 组件注册表
        self._components: Dict[str, ComponentInfo] = {}
        # 依赖图：组件 -> 依赖它的组件列表
        self._dependency_graph: Dict[str, Set[str]] = {}
        # 反向依赖图：组件 -> 它依赖的组件列表
        self._reverse_graph: Dict[str, Set[str]] = {}
        # 依赖注入注册表
        self._dependencies: Dict[str, DependencyInfo] = {}
        # 注入点注册表：组件名 -> {(属性名, 依赖名)}
        self._injection_points: Dict[str, Set[tuple]] = {}
        
        self._lock = threading.RLock()
        self._init_lock = threading.RLock()
        self._initialized_components: Set[str] = set()
    
    def register_component(
        self,
        name: str,
        component_class: Type,
        priority: ComponentPriority = ComponentPriority.NORMAL,
        dependencies: Optional[Set[str]] = None,
        init_func: Optional[Callable] = None,
        destroy_func: Optional[Callable] = None,
        config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        注册组件
        
        Args:
            name: 组件名称
            component_class: 组件类
            priority: 初始化优先级
            dependencies: 依赖的组件名称集合
            init_func: 自定义初始化函数
            destroy_func: 自定义销毁函数
            config: 组件配置
        
        Returns:
            是否注册成功
        """
        with self._lock:
            if name in self._components:
                return False
            
            component = ComponentInfo(
                name=name,
                component_class=component_class,
                priority=priority,
                dependencies=dependencies or set(),
                init_func=init_func,
                destroy_func=destroy_func,
                config=config or {}
            )
            
            self._components[name] = component
            self._dependency_graph[name] = set()
            self._reverse_graph[name] = set()
            
            # 构建依赖图
            for dep in component.dependencies:
                if dep not in self._dependency_graph:
                    self._dependency_graph[dep] = set()
                self._dependency_graph[dep].add(name)
                self._reverse_graph[name].add(dep)
            
            return True
    
    def unregister_component(self, name: str) -> bool:
        """
        注销组件
        
        Args:
            name: 组件名称
        
        Returns:
            是否注销成功
        """
        with self._lock:
            if name not in self._components:
                return False
            
            # 检查是否有其他组件依赖此组件
            if self._dependency_graph.get(name):
                dependent = self._dependency_graph[name].pop()
                self._dependency_graph[name].add(dependent)
                return False
            
            # 销毁组件
            self._destroy_component(name)
            
            # 从依赖图中移除
            for dep in self._reverse_graph.get(name, set()):
                if name in self._dependency_graph.get(dep, set()):
                    self._dependency_graph[dep].remove(name)
            
            del self._components[name]
            del self._dependency_graph[name]
            del self._reverse_graph[name]
            
            return True
    
    def get_initialization_order(self) -> List[str]:
        """
        获取初始化顺序（拓扑排序）
        
        Returns:
            按依赖顺序排序的组件名称列表
        
        Raises:
            ValueError: 检测到循环依赖
        """
        with self._lock:
            # 计算入度
            in_degree: Dict[str, int] = {}
            for name in self._components:
                in_degree[name] = len(self._reverse_graph.get(name, set()))
            
            # 按优先级分组
            priority_groups: Dict[int, List[str]] = {
                0: [], 1: [], 2: [], 3: [], 4: []
            }
            
            # 初始化队列（入度为0的节点）
            queue = deque()
            for name, degree in in_degree.items():
                if degree == 0:
                    priority = self._components[name].priority.value
                    priority_groups[priority].append(name)
            
            # 按优先级顺序加入队列
            for priority in range(5):
                for name in priority_groups[priority]:
                    queue.append(name)
            
            result = []
            processed = set()
            
            while queue:
                name = queue.popleft()
                if name in processed:
                    continue
                
                result.append(name)
                processed.add(name)
                
                # 更新依赖此组件的节点的入度
                for dependent in self._dependency_graph.get(name, set()):
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0 and dependent not in processed:
                        priority = self._components[dependent].priority.value
                        # 插入到合适位置保持优先级顺序
                        inserted = False
                        for i, existing in enumerate(queue):
                            if self._components[existing].priority.value > priority:
                                queue.insert(i, dependent)
                                inserted = True
                                break
                        if not inserted:
                            queue.append(dependent)
            
            # 检查是否有未处理的节点（循环依赖）
            if len(result) != len(self._components):
                unprocessed = set(self._components.keys()) - processed
                raise ValueError(f"检测到循环依赖，无法初始化的组件: {unprocessed}")
            
            # 设置初始化顺序
            for i, name in enumerate(result):
                self._components[name].init_order = i
            
            return result
    
    def initialize_component(self, name: str, force: bool = False) -> bool:
        """
        初始化单个组件
        
        Args:
            name: 组件名称
            force: 是否强制重新初始化
        
        Returns:
            是否初始化成功
        """
        with self._init_lock:
            if name not in self._components:
                return False
            
            component = self._components[name]
            
            # 检查是否已初始化
            if component.state == InitializationState.INITIALIZED and not force:
                return True
            
            # 检查状态
            if component.state == InitializationState.INITIALIZING:
                return False
            
            # 先初始化依赖
            for dep_name in component.dependencies:
                if dep_name not in self._initialized_components:
                    if not self.initialize_component(dep_name):
                        component.state = InitializationState.FAILED
                        component.error = f"依赖组件 '{dep_name}' 初始化失败"
                        return False
            
            # 执行注入
            self._inject_dependencies(name)
            
            # 初始化组件
            component.state = InitializationState.INITIALIZING
            try:
                if component.init_func:
                    component.instance = component.init_func(**component.config)
                else:
                    component.instance = component.component_class(**component.config)
                
                component.state = InitializationState.INITIALIZED
                self._initialized_components.add(name)
                return True
                
            except Exception as e:
                component.state = InitializationState.FAILED
                component.error = str(e)
                return False
    
    def initialize_all(self) -> Dict[str, bool]:
        """
        按顺序初始化所有组件
        
        Returns:
            各组件初始化结果的字典
        """
        results = {}
        
        try:
            order = self.get_initialization_order()
        except ValueError as e:
            for name in self._components:
                results[name] = False
                self._components[name].state = InitializationState.FAILED
                self._components[name].error = str(e)
            return results
        
        for name in order:
            results[name] = self.initialize_component(name)
        
        return results
    
    def register_dependency(
        self,
        name: str,
        required_type: Optional[Type] = None,
        required: bool = True,
        lazy: bool = False,
        factory: Optional[Callable] = None
    ) -> bool:
        """
        注册依赖
        
        Args:
            name: 依赖名称
            required_type: 要求的类型
            required: 是否必需
            lazy: 是否延迟加载
            factory: 工厂函数
        
        Returns:
            是否注册成功
        """
        with self._lock:
            if name in self._dependencies:
                return False
            
            self._dependencies[name] = DependencyInfo(
                name=name,
                required_type=required_type,
                required=required,
                lazy=lazy,
                factory=factory
            )
            return True
    
    def register_injection_point(
        self,
        component_name: str,
        attribute_name: str,
        dependency_name: str
    ) -> bool:
        """
        注册依赖注入点
        
        Args:
            component_name: 组件名称
            attribute_name: 属性名称
            dependency_name: 依赖名称
        
        Returns:
            是否注册成功
        """
        with self._lock:
            if component_name not in self._components:
                return False
            
            if component_name not in self._injection_points:
                self._injection_points[component_name] = set()
            
            self._injection_points[component_name].add((attribute_name, dependency_name))
            return True
    
    def resolve_dependencies(self, component_name: str) -> Dict[str, Any]:
        """
        解析组件的依赖
        
        Args:
            component_name: 组件名称
        
        Returns:
            依赖名称到实例的映射
        """
        with self._lock:
            if component_name not in self._injection_points:
                return {}
            
            resolved = {}
            for attr_name, dep_name in self._injection_points[component_name]:
                # 从已注册的组件中查找
                if dep_name in self._components:
                    component = self._components[dep_name]
                    if component.state == InitializationState.INITIALIZED:
                        resolved[attr_name] = component.instance
                    elif component.state == InitializationState.UNINITIALIZED:
                        # 尝试初始化
                        if self.initialize_component(dep_name):
                            resolved[attr_name] = self._components[dep_name].instance
                
                # 从依赖注册表中查找
                elif dep_name in self._dependencies:
                    dep_info = self._dependencies[dep_name]
                    if dep_info.factory:
                        resolved[attr_name] = dep_info.factory()
            
            return resolved
    
    def inject_dependencies(self, component_name: str) -> bool:
        """
        向组件注入依赖（公开接口）
        
        Args:
            component_name: 组件名称
        
        Returns:
            是否注入成功
        """
        with self._lock:
            return self._inject_dependencies(component_name)
    
    def _inject_dependencies(self, component_name: str) -> bool:
        """内部依赖注入实现"""
        if component_name not in self._components:
            return False
        
        component = self._components[component_name]
        if component.state != InitializationState.INITIALIZING:
            return False
        
        dependencies = self.resolve_dependencies(component_name)
        
        # 注入到组件实例
        if component.instance:
            for attr_name, value in dependencies.items():
                setattr(component.instance, attr_name, value)
        
        return True
    
    def get_component(self, name: str) -> Optional[Any]:
        """
        获取组件实例
        
        Args:
            name: 组件名称
        
        Returns:
            组件实例，未初始化返回None
        """
        with self._lock:
            component = self._components.get(name)
            if component and component.state == InitializationState.INITIALIZED:
                return component.instance
            return None
    
    def get_component_state(self, name: str) -> Optional[InitializationState]:
        """
        获取组件状态
        
        Args:
            name: 组件名称
        
        Returns:
            组件状态
        """
        with self._lock:
            component = self._components.get(name)
            return component.state if component else None
    
    def get_all_states(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有组件状态
        
        Returns:
            组件状态信息字典
        """
        with self._lock:
            return {
                name: {
                    'state': component.state.value,
                    'priority': component.priority.name,
                    'dependencies': list(component.dependencies),
                    'init_order': component.init_order,
                    'error': component.error
                }
                for name, component in self._components.items()
            }
    
    def _destroy_component(self, name: str) -> bool:
        """销毁组件"""
        with self._init_lock:
            if name not in self._components:
                return False
            
            component = self._components[name]
            
            if component.state == InitializationState.DESTROYED:
                return True
            
            try:
                if component.destroy_func and component.instance:
                    component.destroy_func(component.instance)
                elif hasattr(component.instance, 'destroy'):
                    component.instance.destroy()
                elif hasattr(component.instance, 'close'):
                    component.instance.close()
                
                component.instance = None
                component.state = InitializationState.DESTROYED
                self._initialized_components.discard(name)
                return True
                
            except Exception:
                return False
    
    def destroy_all(self) -> Dict[str, bool]:
        """
        按反向顺序销毁所有组件
        
        Returns:
            各组件销毁结果的字典
        """
        with self._lock:
            results = {}
            
            # 按初始化顺序的反向销毁
            sorted_components = sorted(
                self._components.items(),
                key=lambda x: x[1].init_order,
                reverse=True
            )
            
            for name, _ in sorted_components:
                results[name] = self._destroy_component(name)
            
            return results
    
    def reset(self) -> None:
        """重置初始化器状态"""
        with self._lock:
            self.destroy_all()
            self._components.clear()
            self._dependency_graph.clear()
            self._reverse_graph.clear()
            self._dependencies.clear()
            self._injection_points.clear()
            self._initialized_components.clear()


# 全局初始化器实例
_system_initializer: Optional[SystemInitializer] = None
_init_lock = threading.Lock()


def get_system_initializer() -> SystemInitializer:
    """获取全局系统初始化器实例"""
    global _system_initializer
    if _system_initializer is None:
        with _init_lock:
            if _system_initializer is None:
                _system_initializer = SystemInitializer()
    return _system_initializer
