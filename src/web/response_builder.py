"""
响应构建器

第305-306阶段：响应格式化、状态码、头部管理
遵循"图难于其易，为大于其细"原则，实现细粒度的响应构建
"""

import json
import threading
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone


class HttpStatus(Enum):
    """HTTP状态码"""
    # 2xx 成功
    OK = 200
    CREATED = 201
    ACCEPTED = 202
    NO_CONTENT = 204
    
    # 3xx 重定向
    MOVED_PERMANENTLY = 301
    FOUND = 302
    SEE_OTHER = 303
    NOT_MODIFIED = 304
    TEMPORARY_REDIRECT = 307
    PERMANENT_REDIRECT = 308
    
    # 4xx 客户端错误
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    METHOD_NOT_ALLOWED = 405
    NOT_ACCEPTABLE = 406
    REQUEST_TIMEOUT = 408
    CONFLICT = 409
    GONE = 410
    PAYLOAD_TOO_LARGE = 413
    UNPROCESSABLE_ENTITY = 422
    TOO_MANY_REQUESTS = 429
    
    # 5xx 服务器错误
    INTERNAL_SERVER_ERROR = 500
    NOT_IMPLEMENTED = 501
    BAD_GATEWAY = 502
    SERVICE_UNAVAILABLE = 503
    GATEWAY_TIMEOUT = 504


class ResponseType(Enum):
    """响应类型"""
    JSON = "json"
    HTML = "html"
    TEXT = "text"
    XML = "xml"
    BINARY = "binary"
    STREAM = "stream"
    FILE = "file"


@dataclass
class Response:
    """响应对象"""
    status_code: int = 200
    headers: Dict[str, str] = field(default_factory=dict)
    body: Optional[bytes] = None
    content_type: str = "application/json"
    charset: str = "utf-8"


class ResponseBuilder:
    """
    响应构建器
    
    职责：
    1. 构建各种类型的响应
    2. 管理响应头
    3. 设置状态码
    4. 格式化响应体
    
    设计原则：
    - 流式API设计
    - 细粒度控制
    - 类型安全
    """
    
    def __init__(self):
        self._status_code: int = 200
        self._headers: Dict[str, str] = {}
        self._body: Optional[bytes] = None
        self._content_type: str = "application/json"
        self._charset: str = "utf-8"
        self._lock = threading.RLock()
    
    def status(self, code: Union[int, HttpStatus]) -> 'ResponseBuilder':
        """
        设置状态码
        
        Args:
            code: 状态码
        
        Returns:
            self（支持链式调用）
        """
        with self._lock:
            if isinstance(code, HttpStatus):
                self._status_code = code.value
            else:
                self._status_code = code
        return self
    
    def header(self, name: str, value: str) -> 'ResponseBuilder':
        """
        设置响应头
        
        Args:
            name: 头部名称
            value: 头部值
        
        Returns:
            self
        """
        with self._lock:
            self._headers[name] = value
        return self
    
    def headers(self, headers: Dict[str, str]) -> 'ResponseBuilder':
        """
        批量设置响应头
        
        Args:
            headers: 头部字典
        
        Returns:
            self
        """
        with self._lock:
            self._headers.update(headers)
        return self
    
    def content_type(self, content_type: str, charset: str = "utf-8") -> 'ResponseBuilder':
        """
        设置内容类型
        
        Args:
            content_type: 内容类型
            charset: 字符编码
        
        Returns:
            self
        """
        with self._lock:
            self._content_type = content_type
            self._charset = charset
        return self
    
    def json(self, data: Any, indent: Optional[int] = None) -> 'ResponseBuilder':
        """
        设置JSON响应体
        
        Args:
            data: 数据对象
            indent: 缩进
        
        Returns:
            self
        """
        with self._lock:
            self._content_type = "application/json"
            self._body = json.dumps(
                data,
                ensure_ascii=False,
                indent=indent,
                default=self._json_serializer
            ).encode(self._charset)
        return self
    
    def text(self, content: str) -> 'ResponseBuilder':
        """
        设置文本响应体
        
        Args:
            content: 文本内容
        
        Returns:
            self
        """
        with self._lock:
            self._content_type = "text/plain"
            self._body = content.encode(self._charset)
        return self
    
    def html(self, content: str) -> 'ResponseBuilder':
        """
        设置HTML响应体
        
        Args:
            content: HTML内容
        
        Returns:
            self
        """
        with self._lock:
            self._content_type = "text/html"
            self._body = content.encode(self._charset)
        return self
    
    def xml(self, content: str) -> 'ResponseBuilder':
        """
        设置XML响应体
        
        Args:
            content: XML内容
        
        Returns:
            self
        """
        with self._lock:
            self._content_type = "application/xml"
            self._body = content.encode(self._charset)
        return self
    
    def binary(self, data: bytes, content_type: str = "application/octet-stream") -> 'ResponseBuilder':
        """
        设置二进制响应体
        
        Args:
            data: 二进制数据
            content_type: 内容类型
        
        Returns:
            self
        """
        with self._lock:
            self._content_type = content_type
            self._body = data
        return self
    
    def body(self, data: bytes) -> 'ResponseBuilder':
        """
        设置原始响应体
        
        Args:
            data: 原始数据
        
        Returns:
            self
        """
        with self._lock:
            self._body = data
        return self
    
    def no_content(self) -> 'ResponseBuilder':
        """
        无内容响应
        
        Returns:
            self
        """
        with self._lock:
            self._status_code = 204
            self._body = None
        return self
    
    def redirect(
        self,
        url: str,
        permanent: bool = False,
        allow_external: bool = False
    ) -> 'ResponseBuilder':
        """
        重定向响应
        
        Args:
            url: 目标URL
            permanent: 是否永久重定向
            allow_external: 是否允许外部重定向
        
        Returns:
            self
        """
        with self._lock:
            self._status_code = 301 if permanent else 302
            self._headers['Location'] = url
            self._body = None
        return self
    
    def cookie(
        self,
        name: str,
        value: str,
        max_age: Optional[int] = None,
        expires: Optional[datetime] = None,
        path: str = "/",
        domain: Optional[str] = None,
        secure: bool = False,
        http_only: bool = False,
        same_site: Optional[str] = None
    ) -> 'ResponseBuilder':
        """
        设置Cookie
        
        Args:
            name: Cookie名称
            value: Cookie值
            max_age: 最大存活时间（秒）
            expires: 过期时间
            path: 路径
            domain: 域名
            secure: 仅HTTPS
            http_only: 仅HTTP
            same_site: SameSite策略
        
        Returns:
            self
        """
        with self._lock:
            parts = [f"{name}={value}"]
            
            if max_age is not None:
                parts.append(f"Max-Age={max_age}")
            
            if expires is not None:
                expires_str = expires.strftime("%a, %d %b %Y %H:%M:%S GMT")
                parts.append(f"Expires={expires_str}")
            
            if path:
                parts.append(f"Path={path}")
            
            if domain:
                parts.append(f"Domain={domain}")
            
            if secure:
                parts.append("Secure")
            
            if http_only:
                parts.append("HttpOnly")
            
            if same_site:
                parts.append(f"SameSite={same_site}")
            
            cookie_value = "; ".join(parts)
            
            # 添加到Set-Cookie头部
            if 'Set-Cookie' in self._headers:
                self._headers['Set-Cookie'] += f", {cookie_value}"
            else:
                self._headers['Set-Cookie'] = cookie_value
        
        return self
    
    def cache_control(
        self,
        max_age: Optional[int] = None,
        no_cache: bool = False,
        no_store: bool = False,
        public: bool = True,
        must_revalidate: bool = False
    ) -> 'ResponseBuilder':
        """
        设置缓存控制
        
        Args:
            max_age: 最大缓存时间（秒）
            no_cache: 禁止缓存
            no_store: 禁止存储
            public: 公共缓存
            must_revalidate: 必须重新验证
        
        Returns:
            self
        """
        with self._lock:
            parts = []
            
            if no_store:
                parts.append("no-store")
            elif no_cache:
                parts.append("no-cache")
            elif public:
                parts.append("public")
            else:
                parts.append("private")
            
            if max_age is not None:
                parts.append(f"max-age={max_age}")
            
            if must_revalidate:
                parts.append("must-revalidate")
            
            self._headers['Cache-Control'] = ", ".join(parts)
        
        return self
    
    def cors(
        self,
        allow_origin: str = "*",
        allow_methods: str = "GET,POST,PUT,DELETE,OPTIONS",
        allow_headers: str = "Content-Type,Authorization",
        allow_credentials: bool = False,
        max_age: int = 86400
    ) -> 'ResponseBuilder':
        """
        设置CORS头部
        
        Args:
            allow_origin: 允许的源
            allow_methods: 允许的方法
            allow_headers: 允许的头部
            allow_credentials: 允许凭证
            max_age: 预检缓存时间
        
        Returns:
            self
        """
        with self._lock:
            self._headers['Access-Control-Allow-Origin'] = allow_origin
            self._headers['Access-Control-Allow-Methods'] = allow_methods
            self._headers['Access-Control-Allow-Headers'] = allow_headers
            self._headers['Access-Control-Max-Age'] = str(max_age)
            
            if allow_credentials:
                self._headers['Access-Control-Allow-Credentials'] = "true"
        
        return self
    
    def build(self) -> Response:
        """
        构建响应对象
        
        Returns:
            Response对象
        """
        with self._lock:
            headers = dict(self._headers)
            
            # 自动设置Content-Type
            if 'Content-Type' not in headers:
                if self._charset and 'text' in self._content_type:
                    headers['Content-Type'] = f"{self._content_type}; charset={self._charset}"
                else:
                    headers['Content-Type'] = self._content_type
            
            # 自动设置Content-Length
            if self._body and 'Content-Length' not in headers:
                headers['Content-Length'] = str(len(self._body))
            
            return Response(
                status_code=self._status_code,
                headers=headers,
                body=self._body,
                content_type=self._content_type,
                charset=self._charset
            )
    
    def reset(self) -> 'ResponseBuilder':
        """
        重置构建器
        
        Returns:
            self
        """
        with self._lock:
            self._status_code = 200
            self._headers.clear()
            self._body = None
            self._content_type = "application/json"
            self._charset = "utf-8"
        return self
    
    @staticmethod
    def _json_serializer(obj: Any) -> Any:
        """JSON序列化器"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        if hasattr(obj, '__dict__'):
            return obj.__dict__
        return str(obj)


# 快捷工厂函数
def json_response(data: Any, status: int = 200) -> Response:
    """创建JSON响应"""
    return ResponseBuilder().status(status).json(data).build()


def text_response(content: str, status: int = 200) -> Response:
    """创建文本响应"""
    return ResponseBuilder().status(status).text(content).build()


def html_response(content: str, status: int = 200) -> Response:
    """创建HTML响应"""
    return ResponseBuilder().status(status).html(content).build()


def error_response(
    message: str,
    status: int = 500,
    code: Optional[str] = None
) -> Response:
    """创建错误响应"""
    data = {"error": message}
    if code:
        data["code"] = code
    return ResponseBuilder().status(status).json(data).build()


def redirect_response(url: str, permanent: bool = False) -> Response:
    """创建重定向响应"""
    return ResponseBuilder().redirect(url, permanent).build()


def not_found_response(message: str = "Not Found") -> Response:
    """创建404响应"""
    return error_response(message, 404)


def bad_request_response(message: str = "Bad Request") -> Response:
    """创建400响应"""
    return error_response(message, 400)


def unauthorized_response(message: str = "Unauthorized") -> Response:
    """创建401响应"""
    return error_response(message, 401)


def forbidden_response(message: str = "Forbidden") -> Response:
    """创建403响应"""
    return error_response(message, 403)


# 全局响应构建器
_response_builder: Optional[ResponseBuilder] = None
_builder_lock = threading.Lock()


def get_response_builder() -> ResponseBuilder:
    """获取全局响应构建器"""
    global _response_builder
    if _response_builder is None:
        with _builder_lock:
            if _response_builder is None:
                _response_builder = ResponseBuilder()
    return _response_builder
