"""
路由管理器

第309-310阶段：路由注册、匹配、参数提取
遵循"图难于其易，为大于其细"原则，实现细粒度的路由管理
"""

import threading
import re
from typing import Dict, List, Optional, Callable, Any, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps


class HttpMethod(Enum):
    """HTTP方法"""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"
    ALL = "ALL"  # 匹配所有方法


@dataclass
class Route:
    """路由对象"""
    method: str
    path: str
    handler: Callable
    pattern: str = ""
    params: List[str] = field(default_factory=list)
    middlewares: List[Callable] = field(default_factory=list)
    name: Optional[str] = None
    priority: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RouteMatch:
    """路由匹配结果"""
    route: Route
    params: Dict[str, str]
    matched: bool = True


class RouteManager:
    """
    路由管理器
    
    职责：
    1. 路由注册和管理
    2. 路径模式匹配
    3. 参数提取
    4. 中间件管理
    
    设计原则：
    - 支持动态路由参数
    - 支持正则表达式路由
    - 支持路由分组
    - 细粒度路由控制
    """
    
    _instance: Optional['RouteManager'] = None
    _lock = threading.RLock()
    
    def __new__(cls) -> 'RouteManager':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        # 按方法分组的路由
        self._routes: Dict[str, List[Route]] = {
            method.value: [] for method in HttpMethod
        }
        
        # 路由名称映射
        self._named_routes: Dict[str, Route] = {}
        
        # 全局中间件
        self._global_middlewares: List[Callable] = []
        
        # 路由分组栈
        self._group_stack: List[Dict[str, Any]] = []
        
        self._lock = threading.RLock()
    
    def _parse_path_pattern(self, path: str) -> Tuple[str, List[str]]:
        """
        解析路径模式
        
        Args:
            path: 路径字符串
        
        Returns:
            (正则表达式模式, 参数名列表)
        """
        params = []
        pattern_parts = []
        
        parts = path.strip('/').split('/')
        
        for part in parts:
            if part.startswith('<') and part.endswith('>'):
                # 参数形式: <param> 或 <param:type>
                param_def = part[1:-1]
                if ':' in param_def:
                    param_name, param_type = param_def.split(':', 1)
                else:
                    param_name = param_def
                    param_type = 'str'
                
                params.append(param_name)
                
                # 根据类型选择正则
                if param_type == 'int':
                    pattern_parts.append(r'(\d+)')
                elif param_type == 'str':
                    pattern_parts.append(r'([^/]+)')
                elif param_type == 'path':
                    pattern_parts.append(r'(.+)')
                elif param_type == 'uuid':
                    pattern_parts.append(r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})')
                else:
                    pattern_parts.append(r'([^/]+)')
            
            elif part.startswith(':'):
                # 简写形式: :param
                param_name = part[1:]
                params.append(param_name)
                pattern_parts.append(r'([^/]+)')
            
            elif part == '*':
                # 通配符
                pattern_parts.append(r'(.*)')
            
            else:
                # 静态部分
                pattern_parts.append(re.escape(part))
        
        pattern = '^/' + '/'.join(pattern_parts) + '/?$'
        return pattern, params
    
    def add_route(
        self,
        method: str,
        path: str,
        handler: Callable,
        middlewares: Optional[List[Callable]] = None,
        name: Optional[str] = None,
        priority: int = 0,
        **meta
    ) -> Route:
        """
        添加路由
        
        Args:
            method: HTTP方法
            path: 路径
            handler: 处理函数
            middlewares: 中间件列表
            name: 路由名称
            priority: 优先级
            **meta: 元数据
        
        Returns:
            路由对象
        """
        with self._lock:
            method = method.upper()
            
            # 解析路径模式
            pattern, params = self._parse_path_pattern(path)
            
            # 合并分组中间件
            group_middlewares = []
            for group in self._group_stack:
                group_middlewares.extend(group.get('middlewares', []))
            
            route = Route(
                method=method,
                path=path,
                handler=handler,
                pattern=pattern,
                params=params,
                middlewares=group_middlewares + (middlewares or []),
                name=name,
                priority=priority,
                meta=meta
            )
            
            # 添加到路由表
            if method not in self._routes:
                self._routes[method] = []
            self._routes[method].append(route)
            
            # 按优先级排序
            self._routes[method].sort(key=lambda r: r.priority, reverse=True)
            
            # 添加到名称映射
            if name:
                self._named_routes[name] = route
            
            return route
    
    def remove_route(self, method: str, path: str) -> bool:
        """
        移除路由
        
        Args:
            method: HTTP方法
            path: 路径
        
        Returns:
            是否移除成功
        """
        with self._lock:
            method = method.upper()
            
            if method not in self._routes:
                return False
            
            for i, route in enumerate(self._routes[method]):
                if route.path == path:
                    del self._routes[method][i]
                    if route.name and route.name in self._named_routes:
                        del self._named_routes[route.name]
                    return True
            
            return False
    
    def match(self, method: str, path: str) -> Optional[RouteMatch]:
        """
        匹配路由
        
        Args:
            method: HTTP方法
            path: 请求路径
        
        Returns:
            匹配结果
        """
        with self._lock:
            method = method.upper()
            
            # 尝试精确方法匹配
            routes = self._routes.get(method, []) + self._routes.get(HttpMethod.ALL.value, [])
            
            for route in routes:
                match = re.match(route.pattern, path)
                if match:
                    # 提取参数
                    params = {}
                    for i, param_name in enumerate(route.params):
                        params[param_name] = match.group(i + 1)
                    
                    return RouteMatch(route=route, params=params)
            
            return None
    
    def get_route(self, name: str) -> Optional[Route]:
        """
        通过名称获取路由
        
        Args:
            name: 路由名称
        
        Returns:
            路由对象
        """
        with self._lock:
            return self._named_routes.get(name)
    
    def url_for(self, name: str, **params) -> Optional[str]:
        """
        生成URL
        
        Args:
            name: 路由名称
            **params: 路由参数
        
        Returns:
            生成的URL
        """
        with self._lock:
            route = self._named_routes.get(name)
            if not route:
                return None
            
            url = route.path
            for key, value in params.items():
                # 替换参数占位符
                url = url.replace(f'<{key}>', str(value))
                url = url.replace(f'<{key}:int>', str(value))
                url = url.replace(f'<{key}:str>', str(value))
                url = url.replace(f'<{key}:path>', str(value))
                url = url.replace(f':{key}', str(value))
            
            return url
    
    def group(
        self,
        prefix: str = "",
        middlewares: Optional[List[Callable]] = None,
        **meta
    ) -> 'RouteGroup':
        """
        创建路由分组
        
        Args:
            prefix: 路径前缀
            middlewares: 中间件列表
            **meta: 元数据
        
        Returns:
            路由分组上下文管理器
        """
        return RouteGroup(self, prefix, middlewares or [], meta)
    
    def add_global_middleware(self, middleware: Callable) -> bool:
        """
        添加全局中间件
        
        Args:
            middleware: 中间件函数
        
        Returns:
            是否添加成功
        """
        with self._lock:
            if middleware in self._global_middlewares:
                return False
            self._global_middlewares.append(middleware)
            return True
    
    def remove_global_middleware(self, middleware: Callable) -> bool:
        """
        移除全局中间件
        
        Args:
            middleware: 中间件函数
        
        Returns:
            是否移除成功
        """
        with self._lock:
            if middleware in self._global_middlewares:
                self._global_middlewares.remove(middleware)
                return True
            return False
    
    def get_all_routes(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        获取所有路由信息
        
        Returns:
            路由信息字典
        """
        with self._lock:
            result = {}
            for method, routes in self._routes.items():
                result[method] = [
                    {
                        'path': route.path,
                        'name': route.name,
                        'priority': route.priority,
                        'params': route.params,
                        'middlewares_count': len(route.middlewares)
                    }
                    for route in routes
                ]
            return result
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取路由统计信息
        
        Returns:
            统计信息
        """
        with self._lock:
            total_routes = sum(len(routes) for routes in self._routes.values())
            
            return {
                'total_routes': total_routes,
                'routes_by_method': {
                    method: len(routes)
                    for method, routes in self._routes.items()
                    if routes
                },
                'named_routes': len(self._named_routes),
                'global_middlewares': len(self._global_middlewares)
            }


class RouteGroup:
    """
    路由分组上下文管理器
    
    用于批量设置路由前缀和中间件
    """
    
    def __init__(
        self,
        manager: RouteManager,
        prefix: str = "",
        middlewares: Optional[List[Callable]] = None,
        meta: Optional[Dict[str, Any]] = None
    ):
        self._manager = manager
        self._prefix = prefix
        self._middlewares = middlewares or []
        self._meta = meta or {}
    
    def __enter__(self) -> 'RouteGroup':
        with self._manager._lock:
            self._manager._group_stack.append({
                'prefix': self._prefix,
                'middlewares': self._middlewares,
                'meta': self._meta
            })
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        with self._manager._lock:
            if self._manager._group_stack:
                self._manager._group_stack.pop()
    
    def route(
        self,
        method: str,
        path: str,
        middlewares: Optional[List[Callable]] = None,
        **kwargs
    ) -> Callable:
        """
        路由装饰器
        
        Args:
            method: HTTP方法
            path: 路径
            middlewares: 中间件列表
            **kwargs: 其他参数
        
        Returns:
            装饰器函数
        """
        def decorator(handler: Callable) -> Callable:
            full_path = self._prefix + path
            all_middlewares = self._middlewares + (middlewares or [])
            self._manager.add_route(
                method, full_path, handler,
                middlewares=all_middlewares,
                **{**self._meta, **kwargs}
            )
            return handler
        return decorator
    
    def get(self, path: str, **kwargs) -> Callable:
        """GET路由装饰器"""
        return self.route('GET', path, **kwargs)
    
    def post(self, path: str, **kwargs) -> Callable:
        """POST路由装饰器"""
        return self.route('POST', path, **kwargs)
    
    def put(self, path: str, **kwargs) -> Callable:
        """PUT路由装饰器"""
        return self.route('PUT', path, **kwargs)
    
    def delete(self, path: str, **kwargs) -> Callable:
        """DELETE路由装饰器"""
        return self.route('DELETE', path, **kwargs)


# 路由装饰器工厂函数
def route(method: str, path: str, **kwargs) -> Callable:
    """
    路由装饰器
    
    Args:
        method: HTTP方法
        path: 路径
        **kwargs: 其他参数
    
    Returns:
        装饰器函数
    """
    def decorator(handler: Callable) -> Callable:
        get_route_manager().add_route(method, path, handler, **kwargs)
        return handler
    return decorator


def get(path: str, **kwargs) -> Callable:
    """GET路由装饰器"""
    return route('GET', path, **kwargs)


def post(path: str, **kwargs) -> Callable:
    """POST路由装饰器"""
    return route('POST', path, **kwargs)


def put(path: str, **kwargs) -> Callable:
    """PUT路由装饰器"""
    return route('PUT', path, **kwargs)


def delete(path: str, **kwargs) -> Callable:
    """DELETE路由装饰器"""
    return route('DELETE', path, **kwargs)


# 全局路由管理器
_route_manager: Optional[RouteManager] = None
_manager_lock = threading.Lock()


def get_route_manager() -> RouteManager:
    """获取全局路由管理器"""
    global _route_manager
    if _route_manager is None:
        with _manager_lock:
            if _route_manager is None:
                _route_manager = RouteManager()
    return _route_manager
