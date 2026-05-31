"""
Web服务模块

第21阶段（阶段301-310）Web服务与API
- 阶段301-302: Web服务器 (WebServer)
- 阶段303-304: 请求处理器 (RequestHandler)
- 阶段305-306: 响应构建器 (ResponseBuilder)
- 阶段307-308: 会话管理器 (SessionManager)
- 阶段309-310: 路由管理器 (RouteManager)
"""

from .web_server import WebServer, get_web_server
from .web_server import ServerState, ServerConfig, RequestInfo, ResponseInfo

from .request_handler import RequestParser, get_request_parser
from .request_handler import MiddlewareChain, MiddlewareContext, ParsedRequest
from .request_handler import cors_middleware, auth_middleware, logging_middleware, rate_limit_middleware

from .response_builder import ResponseBuilder, get_response_builder, Response
from .response_builder import HttpStatus, ResponseType
from .response_builder import (
    json_response, text_response, html_response, error_response,
    redirect_response, not_found_response, bad_request_response,
    unauthorized_response, forbidden_response
)

from .session_manager import SessionManager, get_session_manager
from .session_manager import Session, SessionConfig, SessionState

from .route_manager import RouteManager, get_route_manager, RouteGroup
from .route_manager import Route, RouteMatch, HttpMethod
from .route_manager import route, get, post, put, delete

__all__ = [
    # WebServer
    'WebServer', 'get_web_server', 'ServerState', 'ServerConfig', 'RequestInfo', 'ResponseInfo',
    # RequestHandler
    'RequestParser', 'get_request_parser', 'MiddlewareChain', 'MiddlewareContext', 'ParsedRequest',
    'cors_middleware', 'auth_middleware', 'logging_middleware', 'rate_limit_middleware',
    # ResponseBuilder
    'ResponseBuilder', 'get_response_builder', 'Response', 'HttpStatus', 'ResponseType',
    'json_response', 'text_response', 'html_response', 'error_response',
    'redirect_response', 'not_found_response', 'bad_request_response',
    'unauthorized_response', 'forbidden_response',
    # SessionManager
    'SessionManager', 'get_session_manager', 'Session', 'SessionConfig', 'SessionState',
    # RouteManager
    'RouteManager', 'get_route_manager', 'RouteGroup', 'Route', 'RouteMatch', 'HttpMethod',
    'route', 'get', 'post', 'put', 'delete',
]
