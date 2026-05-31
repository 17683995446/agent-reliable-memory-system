"""
请求处理器

第303-304阶段：请求解析、参数提取、中间件
遵循"图难于其易，为大于其细"原则，实现细粒度的请求处理
"""

import threading
import json
import re
from typing import Dict, List, Optional, Callable, Any, Union
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import parse_qs, unquote
from time import time


class ContentType(Enum):
    """内容类型"""
    JSON = "application/json"
    FORM = "application/x-www-form-urlencoded"
    MULTIPART = "multipart/form-data"
    TEXT = "text/plain"
    HTML = "text/html"
    XML = "application/xml"
    BINARY = "application/octet-stream"


class ParseError(Exception):
    """解析错误"""
    pass


@dataclass
class ParsedRequest:
    """解析后的请求"""
    method: str
    path: str
    query: Dict[str, Union[str, List[str]]]
    headers: Dict[str, str]
    body: Any
    raw_body: bytes
    content_type: Optional[ContentType]
    cookies: Dict[str, str]
    path_params: Dict[str, str]
    client_ip: str
    timestamp: float = field(default_factory=time)


@dataclass
class MiddlewareContext:
    """中间件上下文"""
    request: ParsedRequest
    response: Optional[Any] = None
    state: Dict[str, Any] = field(default_factory=dict)
    stopped: bool = False


class RequestParser:
    """
    请求解析器
    
    职责：
    1. 解析HTTP请求
    2. 提取查询参数
    3. 解析请求体
    4. 处理Cookie
    """
    
    def __init__(self):
        self._lock = threading.RLock()
        self._max_body_size = 10 * 1024 * 1024  # 10MB
        self._encoding = 'utf-8'
    
    def set_max_body_size(self, size: int) -> None:
        """设置最大请求体大小"""
        with self._lock:
            self._max_body_size = size
    
    def parse_query_string(self, query_string: str) -> Dict[str, Union[str, List[str]]]:
        """
        解析查询字符串
        
        Args:
            query_string: 查询字符串
        
        Returns:
            参数字典
        """
        if not query_string:
            return {}
        
        result = {}
        parsed = parse_qs(query_string, keep_blank_values=True)
        
        for key, values in parsed.items():
            if len(values) == 1:
                result[key] = values[0]
            else:
                result[key] = values
        
        return result
    
    def parse_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """
        规范化头部名称
        
        Args:
            headers: 原始头部
        
        Returns:
            规范化后的头部
        """
        normalized = {}
        for key, value in headers.items():
            # 转换为小写，便于查找
            normalized[key.lower()] = value
            normalized[key] = value
        return normalized
    
    def parse_cookies(self, headers: Dict[str, str]) -> Dict[str, str]:
        """
        解析Cookie
        
        Args:
            headers: 请求头
        
        Returns:
            Cookie字典
        """
        cookies = {}
        cookie_header = headers.get('Cookie') or headers.get('cookie', '')
        
        if cookie_header:
            for cookie in cookie_header.split(';'):
                cookie = cookie.strip()
                if '=' in cookie:
                    name, value = cookie.split('=', 1)
                    cookies[name.strip()] = unquote(value.strip())
        
        return cookies
    
    def detect_content_type(self, headers: Dict[str, str]) -> Optional[ContentType]:
        """
        检测内容类型
        
        Args:
            headers: 请求头
        
        Returns:
            内容类型枚举
        """
        content_type = headers.get('Content-Type') or headers.get('content-type', '')
        
        if not content_type:
            return None
        
        # 移除charset等参数
        content_type = content_type.split(';')[0].strip().lower()
        
        for ct in ContentType:
            if ct.value.lower() in content_type:
                return ct
        
        return None
    
    def parse_json_body(self, body: bytes) -> Any:
        """
        解析JSON请求体
        
        Args:
            body: 原始请求体
        
        Returns:
            解析后的数据
        """
        try:
            return json.loads(body.decode(self._encoding))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ParseError(f"JSON解析失败: {str(e)}")
    
    def parse_form_body(self, body: bytes) -> Dict[str, Union[str, List[str]]]:
        """
        解析表单请求体
        
        Args:
            body: 原始请求体
        
        Returns:
            表单数据字典
        """
        try:
            body_str = body.decode(self._encoding)
            return self.parse_query_string(body_str)
        except UnicodeDecodeError as e:
            raise ParseError(f"表单解析失败: {str(e)}")
    
    def parse_multipart_body(self, body: bytes, boundary: str) -> Dict[str, Any]:
        """
        解析multipart请求体
        
        Args:
            body: 原始请求体
            boundary: 边界字符串
        
        Returns:
            multipart数据字典
        """
        result = {}
        try:
            body_str = body.decode(self._encoding)
            parts = body_str.split(f'--{boundary}')
            
            for part in parts:
                if not part.strip() or part.strip() == '--':
                    continue
                
                # 解析每个part
                if '\r\n\r\n' in part:
                    headers_section, content = part.split('\r\n\r\n', 1)
                    content = content.rstrip('\r\n')
                    
                    # 提取字段名
                    name_match = re.search(r'name="([^"]+)"', headers_section)
                    if name_match:
                        name = name_match.group(1)
                        
                        # 检查是否是文件
                        filename_match = re.search(r'filename="([^"]+)"', headers_section)
                        if filename_match:
                            result[name] = {
                                'filename': filename_match.group(1),
                                'content': content.encode(self._encoding)
                            }
                        else:
                            result[name] = content
        except Exception as e:
            raise ParseError(f"Multipart解析失败: {str(e)}")
        
        return result
    
    def parse_body(
        self,
        body: bytes,
        content_type: Optional[ContentType],
        headers: Dict[str, str]
    ) -> Any:
        """
        解析请求体
        
        Args:
            body: 原始请求体
            content_type: 内容类型
            headers: 请求头
        
        Returns:
            解析后的数据
        """
        if not body:
            return None
        
        if len(body) > self._max_body_size:
            raise ParseError(f"请求体超过最大限制: {len(body)} > {self._max_body_size}")
        
        if content_type == ContentType.JSON:
            return self.parse_json_body(body)
        
        elif content_type == ContentType.FORM:
            return self.parse_form_body(body)
        
        elif content_type == ContentType.MULTIPART:
            content_type_header = headers.get('Content-Type', '')
            boundary_match = re.search(r'boundary=([^;]+)', content_type_header)
            if boundary_match:
                boundary = boundary_match.group(1).strip()
                return self.parse_multipart_body(body, boundary)
        
        # 默认返回原始字节
        return body
    
    def parse(
        self,
        method: str,
        path: str,
        headers: Dict[str, str],
        body: bytes = b'',
        client_ip: str = ''
    ) -> ParsedRequest:
        """
        完整解析请求
        
        Args:
            method: HTTP方法
            path: 请求路径
            headers: 请求头
            body: 请求体
            client_ip: 客户端IP
        
        Returns:
            解析后的请求对象
        """
        # 分离路径和查询字符串
        if '?' in path:
            path_part, query_string = path.split('?', 1)
        else:
            path_part = path
            query_string = ''
        
        # 解析各部分
        normalized_headers = self.parse_headers(headers)
        content_type = self.detect_content_type(normalized_headers)
        
        return ParsedRequest(
            method=method.upper(),
            path=unquote(path_part),
            query=self.parse_query_string(query_string),
            headers=normalized_headers,
            body=self.parse_body(body, content_type, normalized_headers),
            raw_body=body,
            content_type=content_type,
            cookies=self.parse_cookies(normalized_headers),
            path_params={},
            client_ip=client_ip
        )


class MiddlewareChain:
    """
    中间件链
    
    职责：
    1. 管理中间件顺序
    2. 执行中间件链
    3. 支持短路和修改请求/响应
    """
    
    def __init__(self):
        self._middlewares: List[Callable] = []
        self._lock = threading.RLock()
    
    def add(self, middleware: Callable, position: int = -1) -> bool:
        """
        添加中间件
        
        Args:
            middleware: 中间件函数
            position: 插入位置，-1表示末尾
        
        Returns:
            是否添加成功
        """
        with self._lock:
            if middleware in self._middlewares:
                return False
            
            if position == -1:
                self._middlewares.append(middleware)
            else:
                self._middlewares.insert(position, middleware)
            
            return True
    
    def remove(self, middleware: Callable) -> bool:
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
    
    def clear(self) -> None:
        """清空中间件"""
        with self._lock:
            self._middlewares.clear()
    
    def execute(self, context: MiddlewareContext) -> MiddlewareContext:
        """
        执行中间件链
        
        Args:
            context: 中间件上下文
        
        Returns:
            处理后的上下文
        """
        with self._lock:
            middlewares = list(self._middlewares)
        
        for middleware in middlewares:
            if context.stopped:
                break
            
            try:
                result = middleware(context)
                if result is not None:
                    context = result
            except Exception:
                # 中间件异常不中断链
                pass
        
        return context
    
    def get_count(self) -> int:
        """获取中间件数量"""
        with self._lock:
            return len(self._middlewares)


# 常用中间件工厂函数
def cors_middleware(
    allow_origins: str = "*",
    allow_methods: str = "GET,POST,PUT,DELETE,OPTIONS",
    allow_headers: str = "Content-Type,Authorization"
) -> Callable:
    """
    CORS中间件工厂
    
    Args:
        allow_origins: 允许的源
        allow_methods: 允许的方法
        allow_headers: 允许的头部
    
    Returns:
        中间件函数
    """
    def middleware(context: MiddlewareContext) -> MiddlewareContext:
        if context.request.method == "OPTIONS":
            context.state['cors_headers'] = {
                'Access-Control-Allow-Origin': allow_origins,
                'Access-Control-Allow-Methods': allow_methods,
                'Access-Control-Allow-Headers': allow_headers
            }
        return context
    
    return middleware


def auth_middleware(
    auth_func: Callable[[ParsedRequest], bool],
    on_fail: Optional[Callable] = None
) -> Callable:
    """
    认证中间件工厂
    
    Args:
        auth_func: 认证函数
        on_fail: 失败回调
    
    Returns:
        中间件函数
    """
    def middleware(context: MiddlewareContext) -> MiddlewareContext:
        if not auth_func(context.request):
            context.stopped = True
            if on_fail:
                context.response = on_fail()
        return context
    
    return middleware


def logging_middleware(logger: Optional[Callable] = None) -> Callable:
    """
    日志中间件工厂
    
    Args:
        logger: 日志函数
    
    Returns:
        中间件函数
    """
    def middleware(context: MiddlewareContext) -> MiddlewareContext:
        log_func = logger or print
        log_func(f"[{context.request.timestamp}] {context.request.method} {context.request.path}")
        return context
    
    return middleware


def rate_limit_middleware(
    max_requests: int = 100,
    window_seconds: float = 60.0
) -> Callable:
    """
    限流中间件工厂
    
    Args:
        max_requests: 最大请求数
        window_seconds: 时间窗口
    
    Returns:
        中间件函数
    """
    request_counts: Dict[str, List[float]] = {}
    lock = threading.Lock()
    
    def middleware(context: MiddlewareContext) -> MiddlewareContext:
        ip = context.request.client_ip
        now = time()
        
        with lock:
            if ip not in request_counts:
                request_counts[ip] = []
            
            # 清理过期记录
            request_counts[ip] = [
                t for t in request_counts[ip]
                if now - t < window_seconds
            ]
            
            if len(request_counts[ip]) >= max_requests:
                context.stopped = True
                context.state['rate_limited'] = True
            else:
                request_counts[ip].append(now)
        
        return context
    
    return middleware


# 全局请求解析器
_request_parser: Optional[RequestParser] = None
_parser_lock = threading.Lock()


def get_request_parser() -> RequestParser:
    """获取全局请求解析器"""
    global _request_parser
    if _request_parser is None:
        with _parser_lock:
            if _request_parser is None:
                _request_parser = RequestParser()
    return _request_parser
