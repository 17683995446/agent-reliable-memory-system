"""
API文档

第315阶段：OpenAPI文档生成、Swagger集成
遵循"图难于其易，为大于其细"原则，实现细粒度的API文档生成
"""

import threading
import json
from typing import Dict, List, Optional, Any, Union, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.api_validator import FieldRule
from api.api_router import ApiRoute


class DocFormat(Enum):
    """文档格式"""
    OPENAPI_3 = "openapi_3"
    SWAGGER_2 = "swagger_2"
    MARKDOWN = "markdown"
    HTML = "html"


@dataclass
class ApiInfo:
    """API信息"""
    title: str = "API Documentation"
    description: str = ""
    version: str = "1.0.0"
    contact: Optional[Dict[str, str]] = None
    license: Optional[Dict[str, str]] = None
    terms_of_service: Optional[str] = None


@dataclass
class ServerInfo:
    """服务器信息"""
    url: str
    description: str = ""
    variables: Optional[Dict[str, Any]] = None


@dataclass
class EndpointDoc:
    """端点文档"""
    path: str
    method: str
    summary: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)
    parameters: List[Dict[str, Any]] = field(default_factory=list)
    request_body: Optional[Dict[str, Any]] = None
    responses: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    deprecated: bool = False
    security: Optional[List[Dict[str, List[str]]]] = None


class ApiDocs:
    """
    API文档生成器
    
    职责：
    1. OpenAPI 3.0文档生成
    2. Swagger UI集成
    3. 端点文档管理
    4. 多格式导出
    
    设计原则：
    - 细粒度文档控制
    - 标准OpenAPI格式
    - 可扩展的文档生成
    """
    
    _instance: Optional['ApiDocs'] = None
    _lock = threading.RLock()
    
    def __new__(cls) -> 'ApiDocs':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        self._info = ApiInfo()
        self._servers: List[ServerInfo] = []
        self._endpoints: Dict[str, EndpointDoc] = {}
        self._tags: Dict[str, Dict[str, str]] = {}
        self._components: Dict[str, Any] = {
            'schemas': {},
            'securitySchemes': {}
        }
        
        self._lock = threading.RLock()
    
    def set_info(self, **kwargs) -> None:
        """
        设置API信息
        
        Args:
            **kwargs: API信息参数
        """
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self._info, key):
                    setattr(self._info, key, value)
    
    def add_server(
        self,
        url: str,
        description: str = "",
        variables: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        添加服务器
        
        Args:
            url: 服务器URL
            description: 描述
            variables: 变量
        """
        with self._lock:
            self._servers.append(ServerInfo(
                url=url,
                description=description,
                variables=variables
            ))
    
    def add_tag(
        self,
        name: str,
        description: str = "",
        external_docs: Optional[Dict[str, str]] = None
    ) -> None:
        """
        添加标签
        
        Args:
            name: 标签名称
            description: 描述
            external_docs: 外部文档
        """
        with self._lock:
            self._tags[name] = {
                'name': name,
                'description': description
            }
            if external_docs:
                self._tags[name]['externalDocs'] = external_docs
    
    def add_endpoint(self, doc: EndpointDoc) -> None:
        """
        添加端点文档
        
        Args:
            doc: 端点文档
        """
        with self._lock:
            key = f"{doc.method}:{doc.path}"
            self._endpoints[key] = doc
    
    def document_endpoint(
        self,
        method: str,
        path: str,
        summary: str = "",
        description: str = "",
        tags: Optional[List[str]] = None,
        parameters: Optional[List[Dict[str, Any]]] = None,
        request_body: Optional[Dict[str, Any]] = None,
        responses: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> None:
        """
        文档化端点
        
        Args:
            method: HTTP方法
            path: 路径
            summary: 摘要
            description: 描述
            tags: 标签
            parameters: 参数
            request_body: 请求体
            responses: 响应
        """
        doc = EndpointDoc(
            path=path,
            method=method.upper(),
            summary=summary,
            description=description,
            tags=tags or [],
            parameters=parameters or [],
            request_body=request_body,
            responses=responses or {'200': {'description': 'Success'}}
        )
        self.add_endpoint(doc)
    
    def add_schema(
        self,
        name: str,
        schema: Dict[str, Any]
    ) -> None:
        """
        添加组件模式
        
        Args:
            name: 模式名称
            schema: 模式定义
        """
        with self._lock:
            self._components['schemas'][name] = schema
    
    def add_security_scheme(
        self,
        name: str,
        scheme: Dict[str, Any]
    ) -> None:
        """
        添加安全方案
        
        Args:
            name: 方案名称
            scheme: 方案定义
        """
        with self._lock:
            self._components['securitySchemes'][name] = scheme
    
    def field_to_schema(self, rule: FieldRule) -> Dict[str, Any]:
        """
        将字段规则转换为OpenAPI模式
        
        Args:
            rule: 字段规则
        
        Returns:
            OpenAPI模式
        """
        schema: Dict[str, Any] = {}
        
        # 类型映射
        type_map = {
            str: 'string',
            int: 'integer',
            float: 'number',
            bool: 'boolean',
            list: 'array',
            dict: 'object'
        }
        
        schema['type'] = type_map.get(rule.type, 'string')
        
        # 描述
        if rule.description:
            schema['description'] = rule.description
        
        # 字符串约束
        if schema['type'] == 'string':
            if rule.min_length is not None:
                schema['minLength'] = rule.min_length
            if rule.max_length is not None:
                schema['maxLength'] = rule.max_length
            if rule.pattern:
                schema['pattern'] = rule.pattern
        
        # 数值约束
        if schema['type'] in ('integer', 'number'):
            if rule.min_value is not None:
                schema['minimum'] = rule.min_value
            if rule.max_value is not None:
                schema['maximum'] = rule.max_value
        
        # 枚举值
        if rule.choices:
            schema['enum'] = rule.choices
        
        # 数组项
        if schema['type'] == 'array' and rule.item_rule:
            schema['items'] = self.field_to_schema(rule.item_rule)
        
        return schema
    
    def generate_openapi(self) -> Dict[str, Any]:
        """
        生成OpenAPI 3.0文档
        
        Returns:
            OpenAPI文档字典
        """
        with self._lock:
            doc: Dict[str, Any] = {
                'openapi': '3.0.0',
                'info': {
                    'title': self._info.title,
                    'version': self._info.version
                },
                'paths': {}
            }
            
            # 添加描述
            if self._info.description:
                doc['info']['description'] = self._info.description
            
            # 添加联系信息
            if self._info.contact:
                doc['info']['contact'] = self._info.contact
            
            # 添加许可证
            if self._info.license:
                doc['info']['license'] = self._info.license
            
            # 添加服务器
            if self._servers:
                doc['servers'] = [
                    {
                        'url': server.url,
                        'description': server.description
                    }
                    for server in self._servers
                ]
            
            # 添加标签
            if self._tags:
                doc['tags'] = list(self._tags.values())
            
            # 添加路径
            for key, endpoint in self._endpoints.items():
                if endpoint.path not in doc['paths']:
                    doc['paths'][endpoint.path] = {}
                
                method_lower = endpoint.method.lower()
                operation: Dict[str, Any] = {}
                
                if endpoint.summary:
                    operation['summary'] = endpoint.summary
                
                if endpoint.description:
                    operation['description'] = endpoint.description
                
                if endpoint.tags:
                    operation['tags'] = endpoint.tags
                
                if endpoint.parameters:
                    operation['parameters'] = endpoint.parameters
                
                if endpoint.request_body:
                    operation['requestBody'] = endpoint.request_body
                
                if endpoint.responses:
                    operation['responses'] = endpoint.responses
                
                if endpoint.deprecated:
                    operation['deprecated'] = True
                
                if endpoint.security:
                    operation['security'] = endpoint.security
                
                doc['paths'][endpoint.path][method_lower] = operation
            
            # 添加组件
            if self._components['schemas'] or self._components['securitySchemes']:
                doc['components'] = self._components
            
            return doc
    
    def generate_swagger(self) -> Dict[str, Any]:
        """
        生成Swagger 2.0文档
        
        Returns:
            Swagger文档字典
        """
        openapi = self.generate_openapi()
        
        swagger: Dict[str, Any] = {
            'swagger': '2.0',
            'info': openapi['info'],
            'paths': {}
        }
        
        # 转换路径
        for path, methods in openapi.get('paths', {}).items():
            swagger['paths'][path] = {}
            for method, operation in methods.items():
                swagger_op = dict(operation)
                
                # 转换requestBody为parameters
                if 'requestBody' in swagger_op:
                    body = swagger_op.pop('requestBody')
                    if 'parameters' not in swagger_op:
                        swagger_op['parameters'] = []
                    swagger_op['parameters'].append({
                        'name': 'body',
                        'in': 'body',
                        'schema': body.get('content', {}).get('application/json', {}).get('schema', {})
                    })
                
                swagger['paths'][path][method] = swagger_op
        
        return swagger
    
    def generate_markdown(self) -> str:
        """
        生成Markdown文档
        
        Returns:
            Markdown字符串
        """
        lines = [
            f"# {self._info.title}",
            "",
            f"Version: {self._info.version}",
            ""
        ]
        
        if self._info.description:
            lines.extend([
                self._info.description,
                ""
            ])
        
        # 按标签分组
        by_tag: Dict[str, List[EndpointDoc]] = {}
        for endpoint in self._endpoints.values():
            tags = endpoint.tags or ['default']
            for tag in tags:
                if tag not in by_tag:
                    by_tag[tag] = []
                by_tag[tag].append(endpoint)
        
        # 生成文档
        for tag, endpoints in by_tag.items():
            tag_info = self._tags.get(tag, {})
            lines.extend([
                f"## {tag}",
                "",
                tag_info.get('description', ''),
                ""
            ])
            
            for endpoint in endpoints:
                lines.extend([
                    f"### {endpoint.method} {endpoint.path}",
                    "",
                    endpoint.summary,
                    ""
                ])
                
                if endpoint.description:
                    lines.extend([
                        endpoint.description,
                        ""
                    ])
                
                if endpoint.parameters:
                    lines.extend([
                        "**Parameters:**",
                        "",
                        "| Name | In | Type | Required | Description |",
                        "|------|-----|------|----------|-------------|"
                    ])
                    for param in endpoint.parameters:
                        lines.append(
                            f"| {param.get('name', '')} | {param.get('in', '')} | "
                            f"{param.get('schema', {}).get('type', '')} | "
                            f"{'Yes' if param.get('required') else 'No'} | "
                            f"{param.get('description', '')} |"
                        )
                    lines.append("")
                
                if endpoint.responses:
                    lines.extend([
                        "**Responses:**",
                        "",
                        "| Status | Description |",
                        "|--------|-------------|"
                    ])
                    for status, resp in endpoint.responses.items():
                        lines.append(f"| {status} | {resp.get('description', '')} |")
                    lines.append("")
        
        return "\n".join(lines)
    
    def to_json(self, format: DocFormat = DocFormat.OPENAPI_3) -> str:
        """
        导出为JSON
        
        Args:
            format: 文档格式
        
        Returns:
            JSON字符串
        """
        if format == DocFormat.OPENAPI_3:
            doc = self.generate_openapi()
        elif format == DocFormat.SWAGGER_2:
            doc = self.generate_swagger()
        else:
            doc = self.generate_openapi()
        
        return json.dumps(doc, ensure_ascii=False, indent=2)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取文档统计信息
        
        Returns:
            统计信息
        """
        with self._lock:
            methods_count: Dict[str, int] = {}
            for endpoint in self._endpoints.values():
                method = endpoint.method
                methods_count[method] = methods_count.get(method, 0) + 1
            
            return {
                'title': self._info.title,
                'version': self._info.version,
                'endpoints': len(self._endpoints),
                'methods': methods_count,
                'tags': len(self._tags),
                'schemas': len(self._components['schemas']),
                'servers': len(self._servers)
            }


# 文档装饰器
def document(
    summary: str = "",
    description: str = "",
    tags: Optional[List[str]] = None,
    responses: Optional[Dict[str, Dict[str, Any]]] = None
) -> Callable:
    """
    文档装饰器
    
    Args:
        summary: 摘要
        description: 描述
        tags: 标签
        responses: 响应
    
    Returns:
        装饰器函数
    """
    def decorator(func: Callable) -> Callable:
        func._doc_summary = summary
        func._doc_description = description
        func._doc_tags = tags or []
        func._doc_responses = responses or {}
        return func
    return decorator


def parameter(
    name: str,
    param_in: str = "query",
    type: str = "string",
    required: bool = False,
    description: str = ""
) -> Callable:
    """
    参数装饰器
    
    Args:
        name: 参数名
        param_in: 参数位置
        type: 类型
        required: 是否必需
        description: 描述
    
    Returns:
        装饰器函数
    """
    def decorator(func: Callable) -> Callable:
        if not hasattr(func, '_doc_parameters'):
            func._doc_parameters = []
        func._doc_parameters.append({
            'name': name,
            'in': param_in,
            'required': required,
            'description': description,
            'schema': {'type': type}
        })
        return func
    return decorator


# 全局API文档实例
_api_docs: Optional[ApiDocs] = None
_docs_lock = threading.Lock()


def get_api_docs() -> ApiDocs:
    """获取全局API文档实例"""
    global _api_docs
    if _api_docs is None:
        with _docs_lock:
            if _api_docs is None:
                _api_docs = ApiDocs()
    return _api_docs
