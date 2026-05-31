"""
REST API框架模块

第22阶段（阶段311-315）REST API框架
- 阶段311: API控制器 (ApiController)
- 阶段312: API路由器 (ApiRouter)
- 阶段313: API验证器 (ApiValidator)
- 阶段314: API序列化器 (ApiSerializer)
- 阶段315: API文档 (ApiDocs)
"""

from .api_controller import (
    ApiController, ActionConfig, ActionResult,
    action, before_hook, after_hook,
    register_controller, get_controller, get_all_controllers
)

from .api_router import (
    ApiRouter, ApiRoute, ResourceConfig, ApiVersion,
    api_route, get_api_router
)

from .api_validator import (
    ApiValidator, FieldRule, ValidationResult, ValidationError, ValidationType,
    RuleBuilder, field,
    get_api_validator
)

from .api_serializer import (
    ApiSerializer, ModelSerializer, FieldConfig, SerializeFormat,
    FieldBuilder, field_config,
    serialize_datetime, serialize_timestamp, serialize_boolean,
    serialize_integer, serialize_float, serialize_string,
    register_serializer, get_serializer, get_all_serializers
)

from .api_docs import (
    ApiDocs, ApiInfo, ServerInfo, EndpointDoc, DocFormat,
    document, parameter,
    get_api_docs
)

__all__ = [
    # ApiController
    'ApiController', 'ActionConfig', 'ActionResult',
    'action', 'before_hook', 'after_hook',
    'register_controller', 'get_controller', 'get_all_controllers',
    # ApiRouter
    'ApiRouter', 'ApiRoute', 'ResourceConfig', 'ApiVersion',
    'api_route', 'get_api_router',
    # ApiValidator
    'ApiValidator', 'FieldRule', 'ValidationResult', 'ValidationError', 'ValidationType',
    'RuleBuilder', 'field', 'get_api_validator',
    # ApiSerializer
    'ApiSerializer', 'ModelSerializer', 'FieldConfig', 'SerializeFormat',
    'FieldBuilder', 'field_config',
    'serialize_datetime', 'serialize_timestamp', 'serialize_boolean',
    'serialize_integer', 'serialize_float', 'serialize_string',
    'register_serializer', 'get_serializer', 'get_all_serializers',
    # ApiDocs
    'ApiDocs', 'ApiInfo', 'ServerInfo', 'EndpointDoc', 'DocFormat',
    'document', 'parameter', 'get_api_docs',
]
