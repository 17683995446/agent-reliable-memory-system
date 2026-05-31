"""
系统清理器

第298-299阶段：资源释放、优雅关闭、清理策略
遵循"图难于其易，为大于其细"原则，实现细粒度的资源清理管理
"""

import threading
import time
import signal
import atexit
from typing import Dict, List, Set, Optional, Callable, Any, Union
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
import weakref


class CleanupPriority(Enum):
    """清理优先级（数值越小越先执行）"""
    CRITICAL = 0      # 关键资源（最先清理）
    HIGH = 1          # 高优先级
    NORMAL = 2        # 普通优先级
    LOW = 3           # 低优先级
    DEFERRED = 4      # 延迟清理（最后执行）


class ResourceType(Enum):
    """资源类型"""
    MEMORY = "memory"           # 内存资源
    FILE = "file"               # 文件句柄
    NETWORK = "network"         # 网络连接
    DATABASE = "database"       # 数据库连接
    THREAD = "thread"           # 线程/进程
    LOCK = "lock"               # 锁资源
    CACHE = "cache"             # 缓存数据
    TEMP = "temp"               # 临时文件/数据
    EXTERNAL = "external"       # 外部资源


class CleanupState(Enum):
    """清理状态"""
    PENDING = "pending"         # 等待清理
    CLEANING = "cleaning"       # 清理中
    COMPLETED = "completed"     # 已完成
    FAILED = "failed"           # 失败
    SKIPPED = "skipped"         # 已跳过


@dataclass
class CleanupTask:
    """清理任务"""
    name: str
    cleanup_func: Callable
    priority: CleanupPriority = CleanupPriority.NORMAL
    resource_type: ResourceType = ResourceType.MEMORY
    timeout: float = 30.0
    retry_count: int = 0
    max_retries: int = 3
    dependencies: Set[str] = field(default_factory=set)
    state: CleanupState = CleanupState.PENDING
    error: Optional[str] = None
    execution_time: float = 0.0


@dataclass
class ResourceTracker:
    """资源追踪器"""
    resource_id: str
    resource_type: ResourceType
    resource_ref: weakref.ref
    cleanup_callback: Optional[Callable] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)


class SystemCleaner:
    """
    系统清理器
    
    职责：
    1. 注册和管理清理任务
    2. 按优先级和依赖顺序执行清理
    3. 资源追踪和自动回收
    4. 优雅关闭处理
    
    设计原则：
    - 反向依赖顺序清理
    - 超时和重试机制
    - 信号处理和优雅关闭
    - 细粒度资源追踪
    """
    
    _instance: Optional['SystemCleaner'] = None
    _lock = threading.RLock()
    
    def __new__(cls) -> 'SystemCleaner':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        # 清理任务注册表
        self._tasks: Dict[str, CleanupTask] = {}
        # 依赖图
        self._dependency_graph: Dict[str, Set[str]] = {}
        # 资源追踪器
        self._resources: Dict[str, ResourceTracker] = {}
        # 按类型分组的资源
        self._resources_by_type: Dict[ResourceType, Set[str]] = {
            rt: set() for rt in ResourceType
        }
        
        self._lock = threading.RLock()
        self._cleanup_lock = threading.RLock()
        self._shutdown_hooks: List[Callable] = []
        self._is_shutting_down = False
        self._shutdown_timeout = 60.0
        
        # 注册信号处理
        self._register_signal_handlers()
        # 注册atexit钩子
        atexit.register(self._atexit_handler)
    
    def _register_signal_handlers(self) -> None:
        """注册信号处理器"""
        try:
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)
        except (ValueError, OSError):
            # 在某些环境中信号处理不可用
            pass
    
    def _signal_handler(self, signum, frame) -> None:
        """信号处理器"""
        self.graceful_shutdown()
    
    def _atexit_handler(self) -> None:
        """atexit处理器"""
        if not self._is_shutting_down:
            self.graceful_shutdown()
    
    def register_cleanup_task(
        self,
        name: str,
        cleanup_func: Callable,
        priority: CleanupPriority = CleanupPriority.NORMAL,
        resource_type: ResourceType = ResourceType.MEMORY,
        timeout: float = 30.0,
        max_retries: int = 3,
        dependencies: Optional[Set[str]] = None
    ) -> bool:
        """
        注册清理任务
        
        Args:
            name: 任务名称
            cleanup_func: 清理函数
            priority: 清理优先级
            resource_type: 资源类型
            timeout: 超时时间（秒）
            max_retries: 最大重试次数
            dependencies: 依赖的其他清理任务
        
        Returns:
            是否注册成功
        """
        with self._lock:
            if name in self._tasks:
                return False
            
            task = CleanupTask(
                name=name,
                cleanup_func=cleanup_func,
                priority=priority,
                resource_type=resource_type,
                timeout=timeout,
                max_retries=max_retries,
                dependencies=dependencies or set()
            )
            
            self._tasks[name] = task
            self._dependency_graph[name] = set()
            
            # 构建依赖图
            for dep in task.dependencies:
                if dep in self._tasks:
                    self._dependency_graph[dep].add(name)
            
            return True
    
    def unregister_cleanup_task(self, name: str) -> bool:
        """
        注销清理任务
        
        Args:
            name: 任务名称
        
        Returns:
            是否注销成功
        """
        with self._lock:
            if name not in self._tasks:
                return False
            
            # 检查是否有其他任务依赖此任务
            if self._dependency_graph.get(name):
                return False
            
            del self._tasks[name]
            del self._dependency_graph[name]
            return True
    
    def track_resource(
        self,
        resource_id: str,
        resource: Any,
        resource_type: ResourceType,
        cleanup_callback: Optional[Callable] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        追踪资源
        
        Args:
            resource_id: 资源ID
            resource: 资源对象
            resource_type: 资源类型
            cleanup_callback: 清理回调函数
            metadata: 元数据
        
        Returns:
            是否追踪成功
        """
        with self._lock:
            if resource_id in self._resources:
                return False
            
            tracker = ResourceTracker(
                resource_id=resource_id,
                resource_type=resource_type,
                resource_ref=weakref.ref(resource),
                cleanup_callback=cleanup_callback,
                metadata=metadata or {}
            )
            
            self._resources[resource_id] = tracker
            self._resources_by_type[resource_type].add(resource_id)
            
            # 注册弱引用回调
            weakref.finalize(resource, self._resource_finalized, resource_id)
            
            return True
    
    def _resource_finalized(self, resource_id: str) -> None:
        """资源被垃圾回收时的回调"""
        with self._lock:
            if resource_id in self._resources:
                tracker = self._resources[resource_id]
                self._resources_by_type[tracker.resource_type].discard(resource_id)
                del self._resources[resource_id]
    
    def untrack_resource(self, resource_id: str) -> bool:
        """
        取消资源追踪
        
        Args:
            resource_id: 资源ID
        
        Returns:
            是否取消成功
        """
        with self._lock:
            if resource_id not in self._resources:
                return False
            
            tracker = self._resources[resource_id]
            self._resources_by_type[tracker.resource_type].discard(resource_id)
            del self._resources[resource_id]
            return True
    
    def get_cleanup_order(self) -> List[str]:
        """
        获取清理顺序（拓扑排序，反向依赖）
        
        Returns:
            按清理顺序排序的任务名称列表
        """
        with self._lock:
            # 计算入度（依赖此任务的任务数）
            in_degree: Dict[str, int] = {}
            for name in self._tasks:
                in_degree[name] = len(self._dependency_graph.get(name, set()))
            
            # 按优先级分组
            priority_groups: Dict[int, List[str]] = {i: [] for i in range(5)}
            
            # 初始化队列（入度为0的节点，即没有其他任务依赖它）
            queue = deque()
            for name, degree in in_degree.items():
                if degree == 0:
                    priority = self._tasks[name].priority.value
                    priority_groups[priority].append(name)
            
            # 按优先级顺序加入队列（优先级数值小的先处理）
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
                
                # 更新依赖此任务的节点的入度
                for dep_name in self._tasks[name].dependencies:
                    if dep_name in in_degree:
                        in_degree[dep_name] -= 1
                        if in_degree[dep_name] == 0 and dep_name not in processed:
                            priority = self._tasks[dep_name].priority.value
                            # 插入到合适位置保持优先级顺序
                            inserted = False
                            for i, existing in enumerate(queue):
                                if self._tasks[existing].priority.value > priority:
                                    queue.insert(i, dep_name)
                                    inserted = True
                                    break
                            if not inserted:
                                queue.append(dep_name)
            
            return result
    
    def execute_cleanup_task(self, name: str) -> bool:
        """
        执行单个清理任务
        
        Args:
            name: 任务名称
        
        Returns:
            是否执行成功
        """
        with self._cleanup_lock:
            if name not in self._tasks:
                return False
            
            task = self._tasks[name]
            
            if task.state == CleanupState.COMPLETED:
                return True
            
            if task.state == CleanupState.CLEANING:
                return False
            
            task.state = CleanupState.CLEANING
            start_time = time.time()
            
            try:
                # 执行清理函数
                task.cleanup_func()
                task.execution_time = time.time() - start_time
                task.state = CleanupState.COMPLETED
                return True
                
            except Exception as e:
                task.retry_count += 1
                task.execution_time = time.time() - start_time
                
                if task.retry_count >= task.max_retries:
                    task.state = CleanupState.FAILED
                    task.error = str(e)
                    return False
                else:
                    task.state = CleanupState.PENDING
                    return self.execute_cleanup_task(name)
    
    def execute_all_cleanup(self) -> Dict[str, bool]:
        """
        执行所有清理任务
        
        Returns:
            各任务执行结果的字典
        """
        results = {}
        order = self.get_cleanup_order()
        
        for name in order:
            results[name] = self.execute_cleanup_task(name)
        
        return results
    
    def cleanup_resources_by_type(
        self,
        resource_type: ResourceType,
        force: bool = False
    ) -> Dict[str, bool]:
        """
        按类型清理资源
        
        Args:
            resource_type: 资源类型
            force: 是否强制清理
        
        Returns:
            各资源清理结果的字典
        """
        with self._lock:
            results = {}
            resource_ids = list(self._resources_by_type.get(resource_type, set()))
            
            for resource_id in resource_ids:
                results[resource_id] = self._cleanup_resource(resource_id, force)
            
            return results
    
    def _cleanup_resource(self, resource_id: str, force: bool = False) -> bool:
        """清理单个资源"""
        if resource_id not in self._resources:
            return False
        
        tracker = self._resources[resource_id]
        
        # 检查资源是否还存在
        resource = tracker.resource_ref()
        if resource is None:
            # 资源已被垃圾回收
            self.untrack_resource(resource_id)
            return True
        
        try:
            if tracker.cleanup_callback:
                tracker.cleanup_callback(resource)
            elif hasattr(resource, 'close'):
                resource.close()
            elif hasattr(resource, 'destroy'):
                resource.destroy()
            elif hasattr(resource, 'cleanup'):
                resource.cleanup()
            
            self.untrack_resource(resource_id)
            return True
            
        except Exception:
            if force:
                self.untrack_resource(resource_id)
            return False
    
    def cleanup_all_resources(self, force: bool = False) -> Dict[str, bool]:
        """
        清理所有追踪的资源
        
        Args:
            force: 是否强制清理
        
        Returns:
            各资源清理结果的字典
        """
        with self._lock:
            results = {}
            # 按优先级顺序清理资源类型
            priority_order = [
                ResourceType.THREAD,
                ResourceType.NETWORK,
                ResourceType.DATABASE,
                ResourceType.LOCK,
                ResourceType.FILE,
                ResourceType.CACHE,
                ResourceType.TEMP,
                ResourceType.MEMORY,
                ResourceType.EXTERNAL
            ]
            
            for resource_type in priority_order:
                type_results = self.cleanup_resources_by_type(resource_type, force)
                results.update(type_results)
            
            return results
    
    def graceful_shutdown(self, timeout: Optional[float] = None) -> Dict[str, Any]:
        """
        优雅关闭系统
        
        Args:
            timeout: 超时时间（秒）
        
        Returns:
            关闭结果统计
        """
        with self._cleanup_lock:
            if self._is_shutting_down:
                return {'status': 'already_shutting_down'}
            
            self._is_shutting_down = True
            timeout = timeout or self._shutdown_timeout
            
            results = {
                'status': 'success',
                'cleanup_tasks': {},
                'resources': {},
                'errors': []
            }
            
            try:
                # 1. 执行关闭钩子
                for hook in self._shutdown_hooks:
                    try:
                        hook()
                    except Exception as e:
                        results['errors'].append(f'Hook error: {str(e)}')
                
                # 2. 执行清理任务
                results['cleanup_tasks'] = self.execute_all_cleanup()
                
                # 3. 清理资源
                results['resources'] = self.cleanup_all_resources()
                
                # 4. 统计结果
                task_success = sum(1 for v in results['cleanup_tasks'].values() if v)
                task_total = len(results['cleanup_tasks'])
                resource_success = sum(1 for v in results['resources'].values() if v)
                resource_total = len(results['resources'])
                
                results['summary'] = {
                    'cleanup_tasks': f'{task_success}/{task_total}',
                    'resources': f'{resource_success}/{resource_total}',
                    'errors_count': len(results['errors'])
                }
                
            except Exception as e:
                results['status'] = 'error'
                results['errors'].append(str(e))
            
            return results
    
    def register_shutdown_hook(self, hook: Callable) -> bool:
        """
        注册关闭钩子
        
        Args:
            hook: 钩子函数
        
        Returns:
            是否注册成功
        """
        with self._lock:
            if hook in self._shutdown_hooks:
                return False
            self._shutdown_hooks.append(hook)
            return True
    
    def unregister_shutdown_hook(self, hook: Callable) -> bool:
        """
        注销关闭钩子
        
        Args:
            hook: 钩子函数
        
        Returns:
            是否注销成功
        """
        with self._lock:
            if hook not in self._shutdown_hooks:
                return False
            self._shutdown_hooks.remove(hook)
            return True
    
    def get_resource_stats(self) -> Dict[str, Any]:
        """
        获取资源统计信息
        
        Returns:
            资源统计字典
        """
        with self._lock:
            stats = {
                'total_resources': len(self._resources),
                'by_type': {},
                'cleanup_tasks': {
                    'total': len(self._tasks),
                    'pending': 0,
                    'cleaning': 0,
                    'completed': 0,
                    'failed': 0
                }
            }
            
            # 按类型统计
            for resource_type in ResourceType:
                count = len(self._resources_by_type[resource_type])
                if count > 0:
                    stats['by_type'][resource_type.value] = count
            
            # 清理任务状态统计
            for task in self._tasks.values():
                if task.state == CleanupState.PENDING:
                    stats['cleanup_tasks']['pending'] += 1
                elif task.state == CleanupState.CLEANING:
                    stats['cleanup_tasks']['cleaning'] += 1
                elif task.state == CleanupState.COMPLETED:
                    stats['cleanup_tasks']['completed'] += 1
                elif task.state == CleanupState.FAILED:
                    stats['cleanup_tasks']['failed'] += 1
            
            return stats
    
    def get_cleanup_task_status(self, name: str) -> Optional[Dict[str, Any]]:
        """
        获取清理任务状态
        
        Args:
            name: 任务名称
        
        Returns:
            任务状态字典
        """
        with self._lock:
            task = self._tasks.get(name)
            if not task:
                return None
            
            return {
                'name': task.name,
                'state': task.state.value,
                'priority': task.priority.name,
                'resource_type': task.resource_type.value,
                'retry_count': task.retry_count,
                'max_retries': task.max_retries,
                'execution_time': task.execution_time,
                'error': task.error,
                'dependencies': list(task.dependencies)
            }
    
    def reset(self) -> None:
        """重置清理器状态"""
        with self._lock:
            # 清理所有资源
            self.cleanup_all_resources(force=True)
            
            # 重置任务状态
            for task in self._tasks.values():
                task.state = CleanupState.PENDING
                task.retry_count = 0
                task.error = None
                task.execution_time = 0.0
            
            self._is_shutting_down = False
            self._shutdown_hooks.clear()


# 全局清理器实例
_system_cleaner: Optional[SystemCleaner] = None
_cleaner_lock = threading.Lock()


def get_system_cleaner() -> SystemCleaner:
    """获取全局系统清理器实例"""
    global _system_cleaner
    if _system_cleaner is None:
        with _cleaner_lock:
            if _system_cleaner is None:
                _system_cleaner = SystemCleaner()
    return _system_cleaner
