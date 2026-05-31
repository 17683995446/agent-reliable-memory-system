"""
Web服务器

第301-302阶段：HTTP服务器基础、端口监听、请求分发
遵循"图难于其易，为大于其细"原则，实现细粒度的Web服务器管理
"""

import threading
import socket
import time
from typing import Dict, List, Optional, Callable, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import json


class ServerState(Enum):
    """服务器状态"""
    STOPPED = "stopped"         # 已停止
    STARTING = "starting"       # 启动中
    RUNNING = "running"         # 运行中
    STOPPING = "stopping"       # 停止中
    ERROR = "error"             # 错误


class HttpMethod(Enum):
    """HTTP方法"""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


@dataclass
class ServerConfig:
    """服务器配置"""
    host: str = "0.0.0.0"
    port: int = 8080
    backlog: int = 5
    timeout: float = 30.0
    max_connections: int = 1000
    buffer_size: int = 8192
    keep_alive: bool = True
    keep_alive_timeout: float = 5.0
    enable_ssl: bool = False
    ssl_cert: Optional[str] = None
    ssl_key: Optional[str] = None


@dataclass
class RequestInfo:
    """请求信息"""
    method: str
    path: str
    headers: Dict[str, str]
    body: Optional[bytes] = None
    query_params: Dict[str, str] = field(default_factory=dict)
    path_params: Dict[str, str] = field(default_factory=dict)
    client_addr: Tuple[str, int] = ("", 0)
    timestamp: float = field(default_factory=time.time)


@dataclass
class ResponseInfo:
    """响应信息"""
    status_code: int = 200
    headers: Dict[str, str] = field(default_factory=dict)
    body: Optional[bytes] = None
    content_type: str = "application/json"


class WebServer:
    """
    Web服务器
    
    职责：
    1. HTTP服务器基础管理
    2. 端口监听和连接管理
    3. 请求分发和路由
    4. 中间件链处理
    
    设计原则：
    - 多线程处理请求
    - 细粒度状态管理
    - 可扩展的中间件架构
    """
    
    _instance: Optional['WebServer'] = None
    _lock = threading.RLock()
    
    def __new__(cls) -> 'WebServer':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        self._config = ServerConfig()
        self._state = ServerState.STOPPED
        self._server: Optional[HTTPServer] = None
        self._routes: Dict[str, Dict[str, Callable]] = {}
        self._middlewares: List[Callable] = []
        self._error_handlers: Dict[int, Callable] = {}
        self._request_count = 0
        self._active_connections = 0
        
        self._lock = threading.RLock()
        self._server_thread: Optional[threading.Thread] = None
    
    def configure(self, **kwargs) -> None:
        """
        配置服务器
        
        Args:
            **kwargs: 配置参数
        """
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self._config, key):
                    setattr(self._config, key, value)
    
    def get_config(self) -> ServerConfig:
        """获取当前配置"""
        return self._config
    
    def register_route(
        self,
        method: str,
        path: str,
        handler: Callable,
        middlewares: Optional[List[Callable]] = None
    ) -> bool:
        """
        注册路由
        
        Args:
            method: HTTP方法
            path: 路径
            handler: 处理函数
            middlewares: 中间件列表
        
        Returns:
            是否注册成功
        """
        with self._lock:
            method = method.upper()
            if method not in self._routes:
                self._routes[method] = {}
            
            if path in self._routes[method]:
                return False
            
            self._routes[method][path] = {
                'handler': handler,
                'middlewares': middlewares or []
            }
            return True
    
    def unregister_route(self, method: str, path: str) -> bool:
        """
        注销路由
        
        Args:
            method: HTTP方法
            path: 路径
        
        Returns:
            是否注销成功
        """
        with self._lock:
            method = method.upper()
            if method in self._routes and path in self._routes[method]:
                del self._routes[method][path]
                return True
            return False
    
    def get_routes(self) -> Dict[str, List[str]]:
        """获取所有路由"""
        with self._lock:
            return {
                method: list(paths.keys())
                for method, paths in self._routes.items()
            }
    
    def add_middleware(self, middleware: Callable) -> bool:
        """
        添加全局中间件
        
        Args:
            middleware: 中间件函数
        
        Returns:
            是否添加成功
        """
        with self._lock:
            if middleware in self._middlewares:
                return False
            self._middlewares.append(middleware)
            return True
    
    def remove_middleware(self, middleware: Callable) -> bool:
        """
        移除中间件
        
        Args:
            middleware: 中间件函数
        
        Returns:
            是否移除成功
        """
        with self._lock:
            if middleware in self._middlewares:
                self._middlewares.remove(middleware)
                return True
            return False
    
    def set_error_handler(self, status_code: int, handler: Callable) -> None:
        """
        设置错误处理器
        
        Args:
            status_code: 状态码
            handler: 处理函数
        """
        with self._lock:
            self._error_handlers[status_code] = handler
    
    def _create_handler_class(self) -> type:
        """创建请求处理器类"""
        server = self
        
        class RequestHandler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            
            def log_message(self, format, *args):
                pass  # 禁用默认日志
            
            def handle_one_request(self):
                server._active_connections += 1
                try:
                    super().handle_one_request()
                finally:
                    server._active_connections -= 1
            
            def do_GET(self):
                self._handle_request(HttpMethod.GET.value)
            
            def do_POST(self):
                self._handle_request(HttpMethod.POST.value)
            
            def do_PUT(self):
                self._handle_request(HttpMethod.PUT.value)
            
            def do_DELETE(self):
                self._handle_request(HttpMethod.DELETE.value)
            
            def do_PATCH(self):
                self._handle_request(HttpMethod.PATCH.value)
            
            def do_HEAD(self):
                self._handle_request(HttpMethod.HEAD.value)
            
            def do_OPTIONS(self):
                self._handle_request(HttpMethod.OPTIONS.value)
            
            def _handle_request(self, method: str):
                server._request_count += 1
                
                # 解析路径和查询参数
                path = self.path.split('?')[0]
                query_params = {}
                if '?' in self.path:
                    query_string = self.path.split('?')[1]
                    for param in query_string.split('&'):
                        if '=' in param:
                            key, value = param.split('=', 1)
                            query_params[key] = value
                
                # 读取请求体
                body = None
                if 'Content-Length' in self.headers:
                    length = int(self.headers['Content-Length'])
                    body = self.rfile.read(length)
                
                # 构建请求信息
                request = RequestInfo(
                    method=method,
                    path=path,
                    headers=dict(self.headers),
                    body=body,
                    query_params=query_params,
                    client_addr=self.client_address
                )
                
                # 查找路由
                with server._lock:
                    routes = server._routes.get(method, {})
                    route_info = routes.get(path)
                    middlewares = list(server._middlewares)
                
                if route_info:
                    handler = route_info['handler']
                    route_middlewares = route_info.get('middlewares', [])
                    all_middlewares = middlewares + route_middlewares
                    
                    # 执行中间件链
                    for mw in all_middlewares:
                        try:
                            result = mw(request)
                            if result is not None:
                                request = result
                        except Exception:
                            pass
                    
                    # 执行处理器
                    try:
                        response = handler(request)
                        self._send_response(response)
                    except Exception as e:
                        self._send_error(500, str(e))
                else:
                    self._send_error(404, "Not Found")
            
            def _send_response(self, response: ResponseInfo):
                self.send_response(response.status_code)
                for key, value in response.headers.items():
                    self.send_header(key, value)
                if response.body:
                    self.send_header('Content-Length', len(response.body))
                self.end_headers()
                if response.body:
                    self.wfile.write(response.body)
            
            def _send_error(self, code: int, message: str):
                with server._lock:
                    handler = server._error_handlers.get(code)
                
                if handler:
                    try:
                        response = handler(message)
                        self._send_response(response)
                        return
                    except Exception:
                        pass
                
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                body = json.dumps({'error': message}).encode('utf-8')
                self.send_header('Content-Length', len(body))
                self.end_headers()
                self.wfile.write(body)
        
        return RequestHandler
    
    def start(self, blocking: bool = False) -> bool:
        """
        启动服务器
        
        Args:
            blocking: 是否阻塞
        
        Returns:
            是否启动成功
        """
        with self._lock:
            if self._state != ServerState.STOPPED:
                return False
            
            self._state = ServerState.STARTING
        
        try:
            handler_class = self._create_handler_class()
            
            class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
                daemon_threads = True
                allow_reuse_address = True
            
            self._server = ThreadedHTTPServer(
                (self._config.host, self._config.port),
                handler_class
            )
            self._server.timeout = self._config.timeout
            
            with self._lock:
                self._state = ServerState.RUNNING
            
            if blocking:
                self._server.serve_forever()
            else:
                self._server_thread = threading.Thread(
                    target=self._server.serve_forever,
                    daemon=True
                )
                self._server_thread.start()
            
            return True
            
        except Exception as e:
            with self._lock:
                self._state = ServerState.ERROR
            return False
    
    def stop(self) -> bool:
        """
        停止服务器
        
        Returns:
            是否停止成功
        """
        with self._lock:
            if self._state != ServerState.RUNNING:
                return False
            
            self._state = ServerState.STOPPING
        
        try:
            if self._server:
                self._server.shutdown()
                self._server = None
            
            with self._lock:
                self._state = ServerState.STOPPED
            
            return True
            
        except Exception:
            with self._lock:
                self._state = ServerState.ERROR
            return False
    
    def get_state(self) -> ServerState:
        """获取服务器状态"""
        return self._state
    
    def get_stats(self) -> Dict[str, Any]:
        """获取服务器统计信息"""
        with self._lock:
            return {
                'state': self._state.value,
                'host': self._config.host,
                'port': self._config.port,
                'request_count': self._request_count,
                'active_connections': self._active_connections,
                'routes_count': sum(len(paths) for paths in self._routes.values()),
                'middlewares_count': len(self._middlewares)
            }
    
    def is_running(self) -> bool:
        """检查服务器是否运行"""
        return self._state == ServerState.RUNNING


# 全局Web服务器实例
_web_server: Optional[WebServer] = None
_server_lock = threading.Lock()


def get_web_server() -> WebServer:
    """获取全局Web服务器实例"""
    global _web_server
    if _web_server is None:
        with _server_lock:
            if _web_server is None:
                _web_server = WebServer()
    return _web_server
