#!/usr/bin/env python3
"""
API网关 - 阶段269-271

功能：
- 阶段269: 路由管理 - 路由注册、删除、匹配、列表
- 阶段270: 限流熔断 - 固定窗口限流、熔断器状态管理
- 阶段271: 认证鉴权 - 认证处理器注册、请求认证、权限校验

设计原则：
- 确定性规则，无模型依赖
- 线程安全，RLock保护
- 单例模式，全局唯一
"""

import threading
import time
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Callable, Any, Optional, Tuple, Set


# ============================================================
# 枚举定义
# ============================================================

class HttpMethod(Enum):
    """HTTP请求方法"""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"


class CircuitState(Enum):
    """熔断器状态"""
    CLOSED = "closed"        # 关闭状态：正常放行
    OPEN = "open"            # 打开状态：拒绝请求
    HALF_OPEN = "half_open"  # 半开状态：试探性放行


class RateLimitStrategy(Enum):
    """限流策略"""
    FIXED_WINDOW = "fixed_window"          # 固定窗口
    SLIDING_WINDOW = "sliding_window"      # 滑动窗口
    TOKEN_BUCKET = "token_bucket"          # 令牌桶


# ============================================================
# 数据结构定义
# ============================================================

@dataclass
class Route:
    """路由定义"""
    path: str = ""
    method: HttpMethod = HttpMethod.GET
    handler: Callable[["APIRequest"], "APIResponse"] = None
    auth_required: bool = False
    rate_limit: Optional[int] = None  # 每窗口最大请求数，None表示不限流


@dataclass
class APIRequest:
    """API请求对象"""
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    path: str = ""
    method: HttpMethod = HttpMethod.GET
    headers: Dict[str, str] = field(default_factory=dict)
    body: Any = None
    query_params: Dict[str, str] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class APIResponse:
    """API响应对象"""
    request_id: str = ""
    status_code: int = 200
    body: Any = None
    headers: Dict[str, str] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class CircuitBreaker:
    """熔断器"""
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_threshold: int = 3       # 半开状态下连续成功次数阈值
    failure_threshold: int = 5       # 触发熔断的连续失败次数阈值
    timeout: float = 30.0            # 熔断超时时间（秒），超时后转为半开
    last_failure_time: float = 0.0   # 上次失败的时间戳
    half_open_requests: int = 0      # 半开状态下的试探请求数


@dataclass
class FixedWindowCounter:
    """固定窗口计数器（用于限流）"""
    count: int = 0
    window_start: float = 0.0
    window_size: float = 60.0  # 窗口大小（秒），默认60秒
    limit: int = 100           # 窗口内最大请求数


@dataclass
class SlidingWindowCounter:
    """滑动窗口计数器（用于限流）"""
    request_times: List[float] = field(default_factory=list)
    window_size: float = 60.0  # 窗口大小（秒）
    limit: int = 100           # 窗口内最大请求数


@dataclass
class TokenBucket:
    """令牌桶（用于限流）"""
    tokens: float = 0.0
    max_tokens: float = 100.0
    refill_rate: float = 1.0   # 每秒补充的令牌数
    last_refill: float = 0.0


# ============================================================
# API网关核心实现
# ============================================================

class APIGateway:
    """
    API网关

    实现：
    - 路由管理（注册、删除、匹配）
    - 限流与熔断保护
    - 认证与鉴权
    """

    def __init__(
        self,
        default_rate_limit: int = 100,
        default_window_size: float = 60.0,
        default_failure_threshold: int = 5,
        default_circuit_timeout: float = 30.0,
    ):
        self._lock = threading.RLock()
        # 阶段269: 路由存储
        self._routes: List[Route] = []
        # 阶段270: 限流与熔断
        self._rate_limiters: Dict[str, FixedWindowCounter] = {}
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._default_rate_limit = default_rate_limit
        self._default_window_size = default_window_size
        self._default_failure_threshold = default_failure_threshold
        self._default_circuit_timeout = default_circuit_timeout
        # 阶段271: 认证鉴权
        self._auth_handlers: Dict[str, Callable[[APIRequest], Tuple[bool, dict]]] = {}
        # 统计信息
        self._stats = {
            "total_requests": 0,
            "accepted": 0,
            "rate_limited": 0,
            "circuit_opened": 0,
            "auth_failed": 0,
            "auth_success": 0,
        }

    # ========================================================
    # 阶段269: 路由管理
    # ========================================================

    def add_route(self, route: Route) -> bool:
        """
        注册路由

        将路由规则添加到网关中。如果已存在相同路径和方法的路由，则覆盖。

        Args:
            route: 路由定义

        Returns:
            bool: 是否注册成功
        """
        with self._lock:
            # 检查是否已存在相同路由
            for i, existing in enumerate(self._routes):
                if existing.path == route.path and existing.method == route.method:
                    self._routes[i] = route
                    return True
            self._routes.append(route)
            return True

    def remove_route(self, path: str, method: HttpMethod) -> bool:
        """
        删除路由

        Args:
            path: 路由路径
            method: HTTP方法

        Returns:
            bool: 是否成功删除
        """
        with self._lock:
            for i, route in enumerate(self._routes):
                if route.path == path and route.method == method:
                    self._routes.pop(i)
                    # 同时清理关联的限流器和熔断器
                    route_key = self._make_route_key(path, method)
                    self._rate_limiters.pop(route_key, None)
                    self._circuit_breakers.pop(route_key, None)
                    return True
            return False

    def match_route(self, path: str, method: HttpMethod) -> Optional[Route]:
        """
        匹配路由

        支持路径参数匹配，如 "/users/{id}" 可以匹配 "/users/123"。
        优先匹配精确路径，再匹配参数化路径。

        Args:
            path: 请求路径
            method: HTTP方法

        Returns:
            Optional[Route]: 匹配到的路由，未匹配返回None
        """
        with self._lock:
            # 第一轮：精确匹配
            for route in self._routes:
                if route.method == method and route.path == path:
                    return route

            # 第二轮：参数化路径匹配
            for route in self._routes:
                if route.method == method and self._path_matches(path, route.path):
                    return route

            return None

    def list_routes(self) -> List[Dict[str, Any]]:
        """
        列出所有已注册的路由

        Returns:
            List[Dict]: 路由信息列表
        """
        with self._lock:
            return [
                {
                    "path": route.path,
                    "method": route.method.value,
                    "auth_required": route.auth_required,
                    "rate_limit": route.rate_limit,
                }
                for route in self._routes
            ]

    @staticmethod
    def _path_matches(request_path: str, route_path: str) -> bool:
        """
        路径参数匹配

        将路由路径中的 {param} 转换为正则表达式，与请求路径进行匹配。
        例如 "/users/{id}" 转为正则 "^/users/[^/]+$"。

        Args:
            request_path: 请求的实际路径
            route_path: 路由定义的路径（可能含参数）

        Returns:
            bool: 是否匹配
        """
        # 将 {param} 替换为正则捕获组
        pattern = re.sub(r'\{[^}]+\}', r'[^/]+', route_path)
        # 锚定首尾
        pattern = f'^{pattern}$'
        return re.match(pattern, request_path) is not None

    @staticmethod
    def _make_route_key(path: str, method: HttpMethod) -> str:
        """
        生成路由唯一键

        Args:
            path: 路由路径
            method: HTTP方法

        Returns:
            str: 路由键
        """
        return f"{method.value}:{path}"

    # ========================================================
    # 阶段270: 限流熔断
    # ========================================================

    def check_rate_limit(self, route_key: str) -> bool:
        """
        检查限流

        使用固定窗口算法检查请求是否超过速率限制。
        如果当前窗口内的请求数未达到限制，则允许通过并递增计数。

        算法说明（固定窗口）：
        1. 检查当前时间是否已超出窗口范围
        2. 若超出，重置窗口起始时间和计数器
        3. 检查计数器是否达到限制
        4. 未达到则递增计数器并放行

        Args:
            route_key: 路由键

        Returns:
            bool: True表示允许通过，False表示被限流
        """
        with self._lock:
            if route_key not in self._rate_limiters:
                # 首次访问，创建限流器
                self._rate_limiters[route_key] = FixedWindowCounter(
                    window_start=time.time(),
                    limit=self._default_rate_limit,
                    window_size=self._default_window_size,
                )

            limiter = self._rate_limiters[route_key]
            now = time.time()

            # 检查窗口是否过期
            if now - limiter.window_start >= limiter.window_size:
                # 重置窗口
                limiter.window_start = now
                limiter.count = 0

            # 检查是否超过限制
            if limiter.count >= limiter.limit:
                return False

            # 递增计数
            limiter.count += 1
            return True

    def check_circuit(self, route_key: str) -> bool:
        """
        检查熔断器状态

        根据熔断器当前状态决定是否放行请求：
        - CLOSED: 正常放行
        - OPEN: 检查是否超时，超时则转为HALF_OPEN并放行一个试探请求
        - HALF_OPEN: 限制并发试探请求数

        Args:
            route_key: 路由键

        Returns:
            bool: True表示允许通过，False表示被熔断拒绝
        """
        with self._lock:
            if route_key not in self._circuit_breakers:
                # 首次访问，创建熔断器
                self._circuit_breakers[route_key] = CircuitBreaker(
                    failure_threshold=self._default_failure_threshold,
                    timeout=self._default_circuit_timeout,
                )

            cb = self._circuit_breakers[route_key]

            if cb.state == CircuitState.CLOSED:
                return True

            elif cb.state == CircuitState.OPEN:
                now = time.time()
                if now - cb.last_failure_time >= cb.timeout:
                    # 超时，转为半开状态
                    cb.state = CircuitState.HALF_OPEN
                    cb.half_open_requests = 1
                    return True
                else:
                    # 仍在熔断中
                    return False

            elif cb.state == CircuitState.HALF_OPEN:
                # 半开状态下限制试探请求数为1
                if cb.half_open_requests >= 1:
                    return False
                cb.half_open_requests += 1
                return True

            return False

    def record_success(self, route_key: str) -> None:
        """
        记录成功请求

        在半开状态下，连续成功达到阈值则关闭熔断器。
        在关闭状态下，重置失败计数。

        Args:
            route_key: 路由键
        """
        with self._lock:
            if route_key not in self._circuit_breakers:
                return

            cb = self._circuit_breakers[route_key]

            if cb.state == CircuitState.HALF_OPEN:
                cb.failure_count = 0
                cb.half_open_requests = 0
                cb.state = CircuitState.CLOSED
            elif cb.state == CircuitState.CLOSED:
                cb.failure_count = 0

    def record_failure(self, route_key: str) -> None:
        """
        记录失败请求

        在关闭状态下，连续失败达到阈值则打开熔断器。
        在半开状态下，任何失败都重新打开熔断器。

        Args:
            route_key: 路由键
        """
        with self._lock:
            if route_key not in self._circuit_breakers:
                self._circuit_breakers[route_key] = CircuitBreaker(
                    failure_threshold=self._default_failure_threshold,
                    timeout=self._default_circuit_timeout,
                )

            cb = self._circuit_breakers[route_key]
            cb.failure_count += 1
            cb.last_failure_time = time.time()

            if cb.state == CircuitState.HALF_OPEN:
                # 半开状态下失败，重新打开熔断器
                cb.state = CircuitState.OPEN
                cb.half_open_requests = 0
            elif cb.state == CircuitState.CLOSED:
                if cb.failure_count >= cb.failure_threshold:
                    # 达到失败阈值，打开熔断器
                    cb.state = CircuitState.OPEN

    def get_circuit_state(self, route_key: str) -> Optional[CircuitState]:
        """
        获取熔断器状态

        Args:
            route_key: 路由键

        Returns:
            Optional[CircuitState]: 熔断器状态，不存在返回None
        """
        with self._lock:
            cb = self._circuit_breakers.get(route_key)
            if cb is None:
                return None
            # 检查是否需要自动转换状态
            if cb.state == CircuitState.OPEN:
                if time.time() - cb.last_failure_time >= cb.timeout:
                    cb.state = CircuitState.HALF_OPEN
            return cb.state

    def reset_circuit(self, route_key: str) -> bool:
        """
        手动重置熔断器

        Args:
            route_key: 路由键

        Returns:
            bool: 是否成功重置
        """
        with self._lock:
            if route_key in self._circuit_breakers:
                self._circuit_breakers[route_key] = CircuitBreaker(
                    failure_threshold=self._default_failure_threshold,
                    timeout=self._default_circuit_timeout,
                )
                return True
            return False

    # ========================================================
    # 阶段271: 认证鉴权
    # ========================================================

    def register_auth_handler(
        self,
        name: str,
        handler: Callable[[APIRequest], Tuple[bool, dict]]
    ) -> bool:
        """
        注册认证处理器

        Args:
            name: 认证处理器名称
            handler: 认证处理函数，接收APIRequest，返回 (是否成功, 上下文信息字典)

        Returns:
            bool: 是否注册成功
        """
        with self._lock:
            self._auth_handlers[name] = handler
            return True

    def unregister_auth_handler(self, name: str) -> bool:
        """
        注销认证处理器

        Args:
            name: 认证处理器名称

        Returns:
            bool: 是否成功注销
        """
        with self._lock:
            if name in self._auth_handlers:
                del self._auth_handlers[name]
                return True
            return False

    def authenticate(self, request: APIRequest) -> Tuple[bool, dict]:
        """
        认证请求

        按注册顺序依次调用认证处理器，任一处理器认证成功即通过。
        所有处理器都失败则认证不通过。

        Args:
            request: API请求对象

        Returns:
            Tuple[bool, dict]: (是否认证成功, 认证上下文信息)
        """
        with self._lock:
            handlers = list(self._auth_handlers.values())

        if not handlers:
            # 没有注册认证处理器，默认放行
            return True, {}

        context = {}
        for handler in handlers:
            try:
                success, ctx = handler(request)
                if success:
                    context.update(ctx)
                    return True, context
            except Exception:
                # 单个处理器异常，继续尝试下一个
                continue

        return False, context

    def authorize(
        self,
        request: APIRequest,
        required_permissions: Optional[Set[str]] = None
    ) -> bool:
        """
        鉴权请求

        检查请求是否具有所需的权限。
        权限信息从请求头中提取（Authorization 或 X-Permissions）。

        权限检查规则：
        1. 如果不需要权限（required_permissions为空），直接放行
        2. 从请求头中解析权限列表
        3. 检查请求方是否拥有所有必需的权限

        Args:
            request: API请求对象
            required_permissions: 需要的权限集合

        Returns:
            bool: 是否具有所需权限
        """
        if not required_permissions:
            return True

        # 从请求头中提取权限
        request_permissions = self._extract_permissions(request)

        # 检查是否拥有所有必需权限
        return required_permissions.issubset(request_permissions)

    @staticmethod
    def _extract_permissions(request: APIRequest) -> Set[str]:
        """
        从请求中提取权限列表

        支持从以下位置提取：
        1. headers["X-Permissions"]: 逗号分隔的权限列表
        2. headers["Authorization"]: Bearer token中的权限（简化处理）

        Args:
            request: API请求对象

        Returns:
            Set[str]: 权限集合
        """
        permissions = set()

        # 从 X-Permissions 头提取
        perms_header = request.headers.get("X-Permissions", "")
        if perms_header:
            for perm in perms_header.split(","):
                perm = perm.strip()
                if perm:
                    permissions.add(perm)

        # 从 Authorization 头提取（简化：Bearer token 后的 scopes）
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            # 简化处理：假设 token 中可能包含权限信息
            # 实际场景中应解析JWT等
            token = auth_header[7:]
            # 尝试从 query_params 中的 scopes 提取
            scopes = request.query_params.get("scopes", "")
            if scopes:
                for scope in scopes.split(","):
                    scope = scope.strip()
                    if scope:
                        permissions.add(scope)

        return permissions

    # ========================================================
    # 请求处理（整合路由、限流、熔断、认证鉴权）
    # ========================================================

    def handle_request(self, request: APIRequest) -> APIResponse:
        """
        处理API请求（完整流程）

        执行顺序：
        1. 路由匹配
        2. 限流检查
        3. 熔断检查
        4. 认证检查（如路由要求）
        5. 调用处理器
        6. 记录成功/失败

        Args:
            request: API请求对象

        Returns:
            APIResponse: API响应对象
        """
        with self._lock:
            self._stats["total_requests"] += 1

        # 步骤1: 路由匹配
        route = self.match_route(request.path, request.method)
        if route is None:
            return APIResponse(
                request_id=request.request_id,
                status_code=404,
                body={"error": "Route not found"},
            )

        route_key = self._make_route_key(route.path, route.method)

        # 步骤2: 限流检查
        if not self.check_rate_limit(route_key):
            with self._lock:
                self._stats["rate_limited"] += 1
            return APIResponse(
                request_id=request.request_id,
                status_code=429,
                body={"error": "Rate limit exceeded"},
            )

        # 步骤3: 熔断检查
        if not self.check_circuit(route_key):
            with self._lock:
                self._stats["circuit_opened"] += 1
            return APIResponse(
                request_id=request.request_id,
                status_code=503,
                body={"error": "Service unavailable (circuit open)"},
            )

        # 步骤4: 认证检查
        if route.auth_required:
            auth_success, auth_context = self.authenticate(request)
            if not auth_success:
                with self._lock:
                    self._stats["auth_failed"] += 1
                return APIResponse(
                    request_id=request.request_id,
                    status_code=401,
                    body={"error": "Authentication failed"},
                )
            with self._lock:
                self._stats["auth_success"] += 1

        # 步骤5: 调用处理器
        try:
            response = route.handler(request)
            # 确保响应关联请求ID
            if not response.request_id:
                response.request_id = request.request_id
            # 步骤6: 记录成功
            self.record_success(route_key)
            with self._lock:
                self._stats["accepted"] += 1
            return response
        except Exception as e:
            # 步骤6: 记录失败
            self.record_failure(route_key)
            return APIResponse(
                request_id=request.request_id,
                status_code=500,
                body={"error": f"Internal server error: {str(e)}"},
            )

    def get_stats(self) -> Dict[str, Any]:
        """
        获取网关统计信息

        Returns:
            Dict[str, Any]: 统计数据
        """
        with self._lock:
            stats = dict(self._stats)
            stats["route_count"] = len(self._routes)
            stats["rate_limiter_count"] = len(self._rate_limiters)
            stats["circuit_breaker_count"] = len(self._circuit_breakers)
            stats["auth_handler_count"] = len(self._auth_handlers)

            # 熔断器状态摘要
            circuit_summary = {}
            for key, cb in self._circuit_breakers.items():
                circuit_summary[key] = {
                    "state": cb.state.value,
                    "failure_count": cb.failure_count,
                    "failure_threshold": cb.failure_threshold,
                }
            stats["circuits"] = circuit_summary

            return stats


# ============================================================
# 全局单例
# ============================================================

_api_gateway_instance: Optional[APIGateway] = None
_api_gateway_lock = threading.RLock()


def get_api_gateway() -> APIGateway:
    """
    获取API网关全局单例

    Returns:
        APIGateway: API网关实例
    """
    global _api_gateway_instance
    with _api_gateway_lock:
        if _api_gateway_instance is None:
            _api_gateway_instance = APIGateway()
        return _api_gateway_instance
