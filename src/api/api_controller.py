"""
API控制器

第311阶段：REST控制器基类、请求处理、响应封装
遵循"图难于其易，为大于其细"原则，实现细粒度的API控制器管理
"""

import threading
import json
from typing import Dict, List, Optional, Any, Callable, Type, Union
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
import sys
import os

# 添加路径以导入web模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web.request_handler import ParsedRequest
from web.response_builder import Response, ResponseBuilder, json_response, error_response


class HttpMethod(Enum):
    """HTTP方法"""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"


@dataclass
class ActionConfig:
    """动作配置"""
    name: str
    method: HttpMethod
    path: str = ""
    description: str = ""
    auth_required: bool = False
    rate_limit: Optional[int] = None
    validators: List[Callable] = field(default_factory=list)
    before_hooks: List[Callable] = field(default_factory=list)
    after_hooks: List[Callable] = field(default_factory=list)


@dataclass
class ActionResult:
    """动作执行结果"""
    success: bool
    data: Any = None
    error: Optional[str] = None
    status_code: int = 200
    headers: Dict[str, str] = field(default_factory=dict)


class ApiController:
    """
    API控制器基类
    
    职责：
    1. 提供RESTful动作的基类
    2. 管理请求处理流程
    3. 封装响应构建
    4. 支持钩子和中间件
    
    设计原则：
    - 细粒度动作定义
    - 可扩展的钩子机制
    - 统一的响应格式
    """
    
    # 控制器名称
    name: str = "base"
    
    # 控制器路径前缀
    path_prefix: str = ""
    
    # 动作注册表
    _actions: Dict[str, ActionConfig] = {}
    
    # 全局钩子
    _global_before_hooks: List[Callable] = []
    _global_after_hooks: List[Callable] = []
    
    def __init__(self):
        self._lock = threading.RLock()
        self._request: Optional[ParsedRequest] = None
        self._response_builder = ResponseBuilder()
    
    @classmethod
    def register_action(cls, config: ActionConfig) -> None:
        """
        注册动作
        
        Args:
            config: 动作配置
        """
        cls._actions[config.name] = config
    
    @classmethod
    def get_actions(cls) -> Dict[str, ActionConfig]:
        """获取所有动作"""
        return dict(cls._actions)
    
    @classmethod
    def get_action(cls, name: str) -> Optional[ActionConfig]:
        """
        获取动作配置
        
        Args:
            name: 动作名称
        
        Returns:
            动作配置
        """
        return cls._actions.get(name)
    
    def set_request(self, request: ParsedRequest) -> None:
        """
        设置当前请求
        
        Args:
            request: 解析后的请求对象
        """
        with self._lock:
            self._request = request
    
    def get_request(self) -> Optional[ParsedRequest]:
        """获取当前请求"""
        return self._request
    
    def before_action(self, action: str, request: ParsedRequest) -> Optional[Response]:
        """
        动作前置钩子
        
        Args:
            action: 动作名称
            request: 请求对象
        
        Returns:
            如果返回Response则中断执行
        """
        return None
    
    def after_action(
        self,
        action: str,
        request: ParsedRequest,
        result: ActionResult
    ) -> ActionResult:
        """
        动作后置钩子
        
        Args:
            action: 动作名称
            request: 请求对象
            result: 执行结果
        
        Returns:
            处理后的结果
        """
        return result
    
    def execute_action(self, action: str, request: ParsedRequest) -> Response:
        """
        执行动作
        
        Args:
            action: 动作名称
            request: 请求对象
        
        Returns:
            HTTP响应
        """
        self.set_request(request)
        
        # 获取动作配置
        config = self.get_action(action)
        if not config:
            return error_response(f"Action '{action}' not found", 404)
        
        try:
            # 执行全局前置钩子
            for hook in self._global_before_hooks:
                result = hook(action, request)
                if result is not None:
                    return result
            
            # 执行动作前置钩子
            for hook in config.before_hooks:
                result = hook(request)
                if result is not None:
                    return result
            
            # 执行控制器前置钩子
            result = self.before_action(action, request)
            if result is not None:
                return result
            
            # 执行动作方法
            action_method = getattr(self, action, None)
            if not action_method or not callable(action_method):
                return error_response(f"Method '{action}' not implemented", 501)
            
            # 调用动作方法
            action_result = action_method(request)
            
            # 转换为ActionResult
            if isinstance(action_result, ActionResult):
                result = action_result
            elif isinstance(action_result, Response):
                return action_result
            elif isinstance(action_result, dict):
                result = ActionResult(success=True, data=action_result)
            else:
                result = ActionResult(success=True, data=action_result)
            
            # 执行控制器后置钩子
            result = self.after_action(action, request, result)
            
            # 执行动作后置钩子
            for hook in config.after_hooks:
                result = hook(request, result)
            
            # 执行全局后置钩子
            for hook in self._global_after_hooks:
                result = hook(action, request, result)
            
            # 构建响应
            return self._build_response(result)
            
        except Exception as e:
            return error_response(str(e), 500)
    
    def _build_response(self, result: ActionResult) -> Response:
        """
        构建响应
        
        Args:
            result: 动作结果
        
        Returns:
            HTTP响应
        """
        builder = ResponseBuilder().status(result.status_code)
        
        # 添加自定义头部
        for key, value in result.headers.items():
            builder.header(key, value)
        
        if result.success:
            response_data = {
                "success": True,
                "data": result.data
            }
        else:
            response_data = {
                "success": False,
                "error": result.error
            }
        
        return builder.json(response_data).build()
    
    def success(self, data: Any = None, status_code: int = 200) -> ActionResult:
        """
        创建成功结果
        
        Args:
            data: 响应数据
            status_code: 状态码
        
        Returns:
            成功的动作结果
        """
        return ActionResult(success=True, data=data, status_code=status_code)
    
    def error(
        self,
        message: str,
        status_code: int = 400,
        data: Any = None
    ) -> ActionResult:
        """
        创建错误结果
        
        Args:
            message: 错误消息
            status_code: 状态码
            data: 附加数据
        
        Returns:
            错误的动作结果
        """
        return ActionResult(
            success=False,
            error=message,
            data=data,
            status_code=status_code
        )
    
    def json_response(self, data: Any, status: int = 200) -> Response:
        """
        快速创建JSON响应
        
        Args:
            data: 数据
            status: 状态码
        
        Returns:
            JSON响应
        """
        return json_response(data, status)
    
    def get_json_body(self) -> Optional[Dict[str, Any]]:
        """
        获取JSON请求体
        
        Returns:
            JSON数据字典
        """
        if self._request and self._request.body:
            if isinstance(self._request.body, dict):
                return self._request.body
        return None
    
    def get_query_param(
        self,
        key: str,
        default: Any = None,
        required: bool = False
    ) -> Any:
        """
        获取查询参数
        
        Args:
            key: 参数名
            default: 默认值
            required: 是否必需
        
        Returns:
            参数值
        """
        if not self._request:
            if required:
                raise ValueError(f"Missing required parameter: {key}")
            return default
        
        value = self._request.query.get(key, default)
        
        if required and value is None:
            raise ValueError(f"Missing required parameter: {key}")
        
        return value
    
    def get_path_param(
        self,
        key: str,
        default: Any = None,
        required: bool = False
    ) -> Any:
        """
        获取路径参数
        
        Args:
            key: 参数名
            default: 默认值
            required: 是否必需
        
        Returns:
            参数值
        """
        if not self._request:
            if required:
                raise ValueError(f"Missing required path parameter: {key}")
            return default
        
        value = self._request.path_params.get(key, default)
        
        if required and value is None:
            raise ValueError(f"Missing required path parameter: {key}")
        
        return value
    
    @classmethod
    def add_global_before_hook(cls, hook: Callable) -> None:
        """
        添加全局前置钩子
        
        Args:
            hook: 钩子函数
        """
        cls._global_before_hooks.append(hook)
    
    @classmethod
    def add_global_after_hook(cls, hook: Callable) -> None:
        """
        添加全局后置钩子
        
        Args:
            hook: 钩子函数
        """
        cls._global_after_hooks.append(hook)


# 动作装饰器
def action(
    name: str,
    method: HttpMethod = HttpMethod.GET,
    path: str = "",
    description: str = "",
    auth_required: bool = False,
    rate_limit: Optional[int] = None
) -> Callable:
    """
    动作装饰器
    
    Args:
        name: 动作名称
        method: HTTP方法
        path: 路径
        description: 描述
        auth_required: 是否需要认证
        rate_limit: 速率限制
    
    Returns:
        装饰器函数
    """
    def decorator(func: Callable) -> Callable:
        config = ActionConfig(
            name=name,
            method=method,
            path=path,
            description=description,
            auth_required=auth_required,
            rate_limit=rate_limit
        )
        
        # 在类定义时注册
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            return func(self, *args, **kwargs)
        
        # 存储配置，稍后注册
        wrapper._action_config = config
        
        return wrapper
    
    return decorator


def before_hook(hook: Callable) -> Callable:
    """前置钩子装饰器"""
    def decorator(func: Callable) -> Callable:
        if not hasattr(func, '_before_hooks'):
            func._before_hooks = []
        func._before_hooks.append(hook)
        return func
    return decorator


def after_hook(hook: Callable) -> Callable:
    """后置钩子装饰器"""
    def decorator(func: Callable) -> Callable:
        if not hasattr(func, '_after_hooks'):
            func._after_hooks = []
        func._after_hooks.append(hook)
        return func
    return decorator


# 全局API控制器注册表
_controllers: Dict[str, Type[ApiController]] = {}
_controllers_lock = threading.Lock()


def register_controller(name: str, controller_class: Type[ApiController]) -> None:
    """
    注册控制器
    
    Args:
        name: 控制器名称
        controller_class: 控制器类
    """
    with _controllers_lock:
        _controllers[name] = controller_class


def get_controller(name: str) -> Optional[Type[ApiController]]:
    """
    获取控制器类
    
    Args:
        name: 控制器名称
    
    Returns:
        控制器类
    """
    with _controllers_lock:
        return _controllers.get(name)


def get_all_controllers() -> Dict[str, Type[ApiController]]:
    """获取所有控制器"""
    with _controllers_lock:
        return dict(_controllers)
