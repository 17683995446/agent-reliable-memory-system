"""
通信与集成模块

第18阶段（阶段266-280）通信与集成
- 阶段266-268: 消息总线 (MessageBus)
- 阶段269-271: API网关 (APIGateway)
- 阶段272-274: 插件系统 (PluginSystem)
- 阶段275-277: 事件溯源 (EventSourcing)
- 阶段278-280: SDK生成器 (SDKGenerator)
"""

from .message_bus import MessageBus, get_message_bus
from .api_gateway import APIGateway, get_api_gateway
from .plugin_system import PluginSystem, get_plugin_system
from .event_sourcing import EventSourcing, get_event_sourcing
from .sdk_generator import SDKGenerator, get_sdk_generator

__all__ = [
    'MessageBus', 'get_message_bus',
    'APIGateway', 'get_api_gateway',
    'PluginSystem', 'get_plugin_system',
    'EventSourcing', 'get_event_sourcing',
    'SDKGenerator', 'get_sdk_generator',
]
