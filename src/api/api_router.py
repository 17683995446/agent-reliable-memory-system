"""
API路由器

第312阶段：RESTful路由、资源路由、版本控制
遵循"图难于其易，为大于其细"原则，实现细粒度的API路由管理
"""

import threading
import re
from typing import Dict, List, Optional, Any, Callable, Type, Tuple
from dataclasses import dataclass, field
from enum import Enum
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web.request_handler import ParsedRequest
from web.response_builder import Response, json_response, error_response
from api.api_controller import ApiController, ActionConfig


class ApiVersion(Enum):
    """API版本策略"""
    URL = "url"           # URL中包含版本 /v1/resource
    HEADER = "header"     # 请求头中指定版本
    QUERY = "query"       # 查询参数中指定版本


@dataclass
class ApiRoute:
    """API路由"""
    method: str
    path: str
    controller: str
    action: str
    version: Optional[str] = None
    pattern: str = ""
    params: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResourceConfig:
    """资源路由配置"""
    name: str
    controller: str
    only: Optional[List[str]] = None      # 仅包含的动作
    except_actions: Optional[List[str]] = None  # 排除的动作
    path: Optional[str] = None            # 自定义路径
    version: Optional[str] = None         # 版本


class ApiRouter:
    """
    API路由器
    
    职责：
    1. RESTful路由管理
    2. 资源路由自动生成
    3. API版本控制
    4. 路由匹配和分发
    
    设计原则：
    - 支持标准RESTful路由
    - 细粒度版本控制
    - 灵活的资源路由配置
    """
    
    _instance: Optional['ApiRouter'] = None
    _lock = threading.RLock()
    
    def __new__(cls) -> 'ApiRouter':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        self._routes: Dict[str, List[ApiRoute]] = {}
        self._controllers: Dict[str, ApiController] = {}
        self._versions: Dict[str, List[str]] = {}
        self._current_version: Optional[str] = None
        self._version_strategy: ApiVersion = ApiVersion.URL
        self._version_header: str = "X-API-Version"
        self._version_query: str = "version"
        self._base_path: str = "/api"
        
        self._lock = threading.RLock()
    
    def set_base_path(self, path: str) -> None:
        """
        设置API基础路径
        
        Args:
            path: 基础路径
        """
        with self._lock:
            self._base_path = path.rstrip('/')
    
    def set_version_strategy(
        self,
        strategy: ApiVersion,
        header: Optional[str] = None,
        query: Optional[str] = None
    ) -> None:
        """
        设置版本策略
        
        Args:
            strategy: 版本策略
            header: 版本头名称
            query: 版本查询参数名称
        """
        with self._lock:
            self._version_strategy = strategy
            if header:
                self._version_header = header
            if query:
                self._version_query = query
    
    def register_controller(
        self,
        name: str,
        controller: ApiController
    ) -> None:
        """
        注册控制器实例
        
        Args:
            name: 控制器名称
            controller: 控制器实例
        """
        with self._lock:
            self._controllers[name] = controller
    
    def get_controller(self, name: str) -> Optional[ApiController]:
        """
        获取控制器实例
        
        Args:
            name: 控制器名称
        
        Returns:
            控制器实例
        """
        with self._lock:
            return self._controllers.get(name)
    
    def _parse_path(self, path: str) -> Tuple[str, List[str]]:
        """
        解析路径模式
        
        Args:
            path: 路径字符串
        
        Returns:
            (正则模式, 参数列表)
        """
        params = []
        pattern_parts = []
        
        parts = path.strip('/').split('/')
        
        for part in parts:
            if part.startswith('<') and part.endswith('>'):
                param_name = part[1:-1]
                params.append(param_name)
                pattern_parts.append(r'([^/]+)')
            elif part.startswith(':'):
                param_name = part[1:]
                params.append(param_name)
                pattern_parts.append(r'([^/]+)')
            else:
                pattern_parts.append(re.escape(part))
        
        pattern = '^/' + '/'.join(pattern_parts) + '/?$'
        return pattern, params
    
    def add_route(
        self,
        method: str,
        path: str,
        controller: str,
        action: str,
        version: Optional[str] = None,
        **meta
    ) -> ApiRoute:
        """
        添加路由
        
        Args:
            method: HTTP方法
            path: 路径
            controller: 控制器名称
            action: 动作名称
            version: API版本
            **meta: 元数据
        
        Returns:
            路由对象
        """
        with self._lock:
            method = method.upper()
            
            # 构建完整路径
            full_path = self._base_path
            if version and self._version_strategy == ApiVersion.URL:
                full_path += f"/{version}"
            full_path += "/" + path.strip('/')
            
            # 解析路径模式
            pattern, params = self._parse_path(full_path)
            
            route = ApiRoute(
                method=method,
                path=full_path,
                controller=controller,
                action=action,
                version=version,
                pattern=pattern,
                params=params,
                meta=meta
            )
            
            if method not in self._routes:
                self._routes[method] = []
            self._routes[method].append(route)
            
            # 记录版本
            if version:
                if version not in self._versions:
                    self._versions[version] = []
                route_key = f"{method}:{full_path}"
                if route_key not in self._versions[version]:
                    self._versions[version].append(route_key)
            
            return route
    
    def resource(self, config: ResourceConfig) -> List[ApiRoute]:
        """
        注册资源路由
        
        自动生成标准RESTful路由：
        - GET    /resource       -> index
        - GET    /resource/:id   -> show
        - POST   /resource       -> create
        - PUT    /resource/:id   -> update
        - DELETE /resource/:id   -> destroy
        
        Args:
            config: 资源配置
        
        Returns:
            生成的路由列表
        """
        routes = []
        
        # 标准REST动作
        standard_actions = {
            'index': ('GET', ''),
            'show': ('GET', '/<id>'),
            'create': ('POST', ''),
            'update': ('PUT', '/<id>'),
            'destroy': ('DELETE', '/<id>'),
            'patch': ('PATCH', '/<id>')
        }
        
        # 确定要生成的动作
        if config.only:
            actions_to_create = {
                k: v for k, v in standard_actions.items()
                if k in config.only
            }
        elif config.except_actions:
            actions_to_create = {
                k: v for k, v in standard_actions.items()
                if k not in config.except_actions
            }
        else:
            actions_to_create = standard_actions
        
        # 生成路由
        path = config.path or config.name
        
        for action, (method, suffix) in actions_to_create.items():
            route = self.add_route(
                method=method,
                path=path + suffix,
                controller=config.controller,
                action=action,
                version=config.version,
                resource=config.name
            )
            routes.append(route)
        
        return routes
    
    def match(
        self,
        method: str,
        path: str,
        version: Optional[str] = None
    ) -> Optional[Tuple[ApiRoute, Dict[str, str]]]:
        """
        匹配路由
        
        Args:
            method: HTTP方法
            path: 请求路径
            version: API版本
        
        Returns:
            (路由对象, 参数字典) 或 None
        """
        with self._lock:
            method = method.upper()
            
            routes = self._routes.get(method, [])
            
            for route in routes:
                # 版本检查
                if version and route.version and route.version != version:
                    continue
                
                match = re.match(route.pattern, path)
                if match:
                    params = {}
                    for i, param_name in enumerate(route.params):
                        params[param_name] = match.group(i + 1)
                    return (route, params)
            
            return None
    
    def dispatch(
        self,
        method: str,
        path: str,
        request: ParsedRequest
    ) -> Response:
        """
        分发请求
        
        Args:
            method: HTTP方法
            path: 请求路径
            request: 请求对象
        
        Returns:
            HTTP响应
        """
        # 确定版本
        version = None
        if self._version_strategy == ApiVersion.HEADER:
            version = request.headers.get(self._version_header.lower())
        elif self._version_strategy == ApiVersion.QUERY:
            version = request.query.get(self._version_query)
        
        # 匹配路由
        match_result = self.match(method, path, version)
        
        if not match_result:
            return error_response("Route not found", 404)
        
        route, params = match_result
        
        # 更新路径参数
        request.path_params = params
        
        # 获取控制器
        controller = self.get_controller(route.controller)
        if not controller:
            return error_response(f"Controller '{route.controller}' not found", 500)
        
        # 执行动作
        return controller.execute_action(route.action, request)
    
    def get_routes(self) -> Dict[str, List[Dict[str, Any]]]:
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
                        'controller': route.controller,
                        'action': route.action,
                        'version': route.version
                    }
                    for route in routes
                ]
            return result
    
    def get_versions(self) -> Dict[str, List[str]]:
        """
        获取所有版本
        
        Returns:
            版本字典
        """
        with self._lock:
            return dict(self._versions)
    
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
                'controllers': len(self._controllers),
                'versions': list(self._versions.keys()),
                'base_path': self._base_path,
                'version_strategy': self._version_strategy.value
            }


# 路由装饰器
def api_route(
    method: str,
    path: str,
    controller: str,
    action: str,
    version: Optional[str] = None
) -> Callable:
    """
    API路由装饰器
    
    Args:
        method: HTTP方法
        path: 路径
        controller: 控制器名称
        action: 动作名称
        version: 版本
    
    Returns:
        装饰器函数
    """
    def decorator(func: Callable) -> Callable:
        get_api_router().add_route(method, path, controller, action, version)
        return func
    return decorator


# 全局API路由器
_api_router: Optional[ApiRouter] = None
_router_lock = threading.Lock()


def get_api_router() -> ApiRouter:
    """获取全局API路由器"""
    global _api_router
    if _api_router is None:
        with _router_lock:
            if _api_router is None:
                _api_router = ApiRouter()
    return _api_router
