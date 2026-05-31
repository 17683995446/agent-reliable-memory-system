#!/usr/bin/env python3
"""
插件钩子系统 (PluginHook) - 阶段323

职责：
- 钩子定义：声明式定义钩子点和参数
- 事件分发：将事件广播到所有订阅者
- 拦截器链：有序执行处理器链，支持中断和短路
- 过滤器：条件过滤，按优先级/类型/来源筛选
- 异常隔离：单个处理器异常不影响整条链路

设计原则：
- 确定性规则，无模型依赖
- 线程安全（RLock）
- 最小层级，无循环依赖
"""

import threading
import time
import traceback
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


# ============================================================
# 枚举与数据结构
# ============================================================

class HookPoint(Enum):
    """系统预定义钩子点"""
    # 内存操作
    BEFORE_STORE = "before_store"
    AFTER_STORE = "after_store"
    BEFORE_RECALL = "before_recall"
    AFTER_RECALL = "after_recall"
    BEFORE_DELETE = "before_delete"
    AFTER_DELETE = "after_delete"

    # 系统生命周期
    ON_STARTUP = "on_startup"
    ON_SHUTDOWN = "on_shutdown"
    ON_RELOAD = "on_reload"

    # 插件生命周期
    PLUGIN_LOADED = "plugin_loaded"
    PLUGIN_UNLOADED = "plugin_unloaded"
    PLUGIN_ERROR = "plugin_error"

    # 数据处理
    BEFORE_TRANSFORM = "before_transform"
    AFTER_TRANSFORM = "after_transform"
    BEFORE_VALIDATE = "before_validate"
    AFTER_VALIDATE = "after_validate"

    # 自定义
    CUSTOM = "custom"


class HookAction(Enum):
    """处理器返回的动作指令"""
    CONTINUE = "continue"     # 继续执行链
    STOP = "stop"             # 停止执行链
    MODIFY = "modify"         # 修改上下文后继续
    ERROR = "error"           # 发生错误


class DispatchMode(Enum):
    """分发模式"""
    SEQUENTIAL = "sequential"   # 顺序执行
    PARALLEL = "parallel"       # 并行执行（使用线程）
    BROADCAST = "broadcast"     # 广播（不关心返回值）


@dataclass
class HookContext:
    """钩子上下文"""
    hook_point: str
    source: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0
    stopped: bool = False
    error: Optional[str] = None
    results: List[Any] = field(default_factory=list)

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    def get(self, key: str, default: Any = None) -> Any:
        """获取上下文数据"""
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """设置上下文数据"""
        self.data[key] = value

    def stop_propagation(self) -> None:
        """停止事件传播"""
        self.stopped = True


@dataclass
class HandlerConfig:
    """处理器配置"""
    name: str
    handler: Callable[[HookContext], HookAction]
    priority: int = 100
    hook_points: List[str] = field(default_factory=list)
    source_filter: Optional[str] = None
    enabled: bool = True
    max_retries: int = 0
    timeout: float = 30.0
    tags: List[str] = field(default_factory=list)


@dataclass
class DispatchResult:
    """分发结果"""
    hook_point: str
    total_handlers: int = 0
    executed: int = 0
    skipped: int = 0
    failed: int = 0
    stopped: bool = False
    duration_ms: float = 0.0
    errors: List[Dict[str, Any]] = field(default_factory=list)
    results: List[Any] = field(default_factory=list)


# ============================================================
# 钩子管理器
# ============================================================

class HookManager:
    """
    钩子管理器

    核心功能：
    1. 注册/注销处理器
    2. 按钩子点和优先级组织处理器
    3. 事件分发（顺序/并行/广播）
    4. 拦截器链执行
    5. 异常隔离与重试
    6. 性能统计
    """

    def __init__(self):
        self._handlers: Dict[str, List[HandlerConfig]] = defaultdict(list)
        self._handler_names: Set[str] = set()
        self._lock = threading.RLock()
        self._dispatch_stats: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"count": 0, "total_ms": 0.0, "errors": 0}
        )
        self._global_filters: List[Callable[[HookContext], bool]] = []
        self._before_dispatch: List[Callable[[HookContext], None]] = []
        self._after_dispatch: List[Callable[[HookContext, DispatchResult], None]] = []

    # ---- 处理器注册 ----

    def register(
        self,
        name: str,
        handler: Callable[[HookContext], HookAction],
        hook_points: List[str],
        priority: int = 100,
        source_filter: Optional[str] = None,
        tags: Optional[List[str]] = None,
        max_retries: int = 0,
        timeout: float = 30.0
    ) -> bool:
        """
        注册钩子处理器

        Args:
            name: 处理器名称（唯一）
            handler: 处理函数
            hook_points: 监听的钩子点列表
            priority: 优先级（越小越先执行）
            source_filter: 来源过滤
            tags: 标签
            max_retries: 最大重试次数
            timeout: 超时时间（秒）

        Returns:
            是否注册成功
        """
        with self._lock:
            if name in self._handler_names:
                return False

            config = HandlerConfig(
                name=name,
                handler=handler,
                priority=priority,
                hook_points=hook_points,
                source_filter=source_filter,
                max_retries=max_retries,
                timeout=timeout,
                tags=tags or [],
            )

            self._handler_names.add(name)

            for hp in hook_points:
                self._handlers[hp].append(config)
                # 按优先级排序
                self._handlers[hp].sort(key=lambda h: h.priority)

            return True

    def unregister(self, name: str) -> bool:
        """
        注销处理器

        Args:
            name: 处理器名称

        Returns:
            是否注销成功
        """
        with self._lock:
            if name not in self._handler_names:
                return False

            self._handler_names.discard(name)

            for hp in list(self._handlers.keys()):
                self._handlers[hp] = [
                    h for h in self._handlers[hp] if h.name != name
                ]
                if not self._handlers[hp]:
                    del self._handlers[hp]

            return True

    def enable(self, name: str) -> bool:
        """启用处理器"""
        with self._lock:
            for hp_handlers in self._handlers.values():
                for h in hp_handlers:
                    if h.name == name:
                        h.enabled = True
                        return True
            return False

    def disable(self, name: str) -> bool:
        """禁用处理器"""
        with self._lock:
            for hp_handlers in self._handlers.values():
                for h in hp_handlers:
                    if h.name == name:
                        h.enabled = False
                        return True
            return False

    # ---- 事件分发 ----

    def dispatch(self, context: HookContext) -> DispatchResult:
        """
        分发事件到所有匹配的处理器

        Args:
            context: 钩子上下文

        Returns:
            分发结果
        """
        start = time.monotonic()
        result = DispatchResult(hook_point=context.hook_point)

        # 前置回调
        for cb in self._before_dispatch:
            try:
                cb(context)
            except Exception:
                pass

        with self._lock:
            handlers = list(self._handlers.get(context.hook_point, []))

        result.total_handlers = len(handlers)

        for handler_config in handlers:
            if context.stopped:
                result.stopped = True
                break

            if not handler_config.enabled:
                result.skipped += 1
                continue

            # 来源过滤
            if handler_config.source_filter and context.source != handler_config.source_filter:
                result.skipped += 1
                continue

            # 全局过滤器
            if not self._apply_global_filters(context):
                result.skipped += 1
                continue

            # 执行处理器
            action, error = self._execute_handler(handler_config, context)

            if error:
                result.failed += 1
                result.errors.append({
                    "handler": handler_config.name,
                    "error": error,
                })
            else:
                result.executed += 1
                if action == HookAction.STOP:
                    context.stop_propagation()
                    result.stopped = True
                    break

        # 更新统计
        duration = (time.monotonic() - start) * 1000
        result.duration_ms = duration

        with self._lock:
            stats = self._dispatch_stats[context.hook_point]
            stats["count"] += 1
            stats["total_ms"] += duration
            stats["errors"] += result.failed

        # 后置回调
        for cb in self._after_dispatch:
            try:
                cb(context, result)
            except Exception:
                pass

        return result

    def dispatch_simple(
        self,
        hook_point: str,
        data: Optional[Dict[str, Any]] = None,
        source: str = ""
    ) -> DispatchResult:
        """
        简化分发接口

        Args:
            hook_point: 钩子点
            data: 上下文数据
            source: 事件来源

        Returns:
            分发结果
        """
        context = HookContext(
            hook_point=hook_point,
            data=data or {},
            source=source,
        )
        return self.dispatch(context)

    # ---- 过滤器 ----

    def add_global_filter(self, filter_fn: Callable[[HookContext], bool]) -> None:
        """添加全局过滤器（返回False则跳过处理器）"""
        with self._lock:
            self._global_filters.append(filter_fn)

    def clear_global_filters(self) -> None:
        """清除所有全局过滤器"""
        with self._lock:
            self._global_filters.clear()

    # ---- 生命周期回调 ----

    def on_before_dispatch(self, callback: Callable[[HookContext], None]) -> None:
        """添加分发前回调"""
        with self._lock:
            self._before_dispatch.append(callback)

    def on_after_dispatch(
        self,
        callback: Callable[[HookContext, DispatchResult], None]
    ) -> None:
        """添加分发后回调"""
        with self._lock:
            self._after_dispatch.append(callback)

    # ---- 查询 ----

    def get_handlers(self, hook_point: str) -> List[Dict[str, Any]]:
        """获取指定钩子点的处理器列表"""
        with self._lock:
            handlers = self._handlers.get(hook_point, [])
            return [
                {
                    "name": h.name,
                    "priority": h.priority,
                    "enabled": h.enabled,
                    "source_filter": h.source_filter,
                    "tags": h.tags,
                }
                for h in handlers
            ]

    def get_handler(self, name: str) -> Optional[Dict[str, Any]]:
        """获取处理器信息"""
        with self._lock:
            for hp_handlers in self._handlers.values():
                for h in hp_handlers:
                    if h.name == name:
                        return {
                            "name": h.name,
                            "priority": h.priority,
                            "hook_points": h.hook_points,
                            "enabled": h.enabled,
                            "source_filter": h.source_filter,
                            "tags": h.tags,
                            "max_retries": h.max_retries,
                            "timeout": h.timeout,
                        }
            return None

    def list_hook_points(self) -> List[str]:
        """列出所有已注册的钩子点"""
        with self._lock:
            return list(self._handlers.keys())

    def get_stats(self) -> Dict[str, Any]:
        """获取钩子系统统计信息"""
        with self._lock:
            total_handlers = len(self._handler_names)
            hook_point_count = len(self._handlers)

            top_hook_points = sorted(
                self._dispatch_stats.items(),
                key=lambda x: x[1]["count"],
                reverse=True
            )[:10]

            return {
                "total_handlers": total_handlers,
                "hook_points": hook_point_count,
                "global_filters": len(self._global_filters),
                "top_hook_points": [
                    {"point": hp, **stats}
                    for hp, stats in top_hook_points
                ],
                "total_dispatches": sum(
                    s["count"] for s in self._dispatch_stats.values()
                ),
            }

    # ---- 内部方法 ----

    def _apply_global_filters(self, context: HookContext) -> bool:
        """应用全局过滤器"""
        for f in self._global_filters:
            try:
                if not f(context):
                    return False
            except Exception:
                return False
        return True

    def _execute_handler(
        self,
        config: HandlerConfig,
        context: HookContext
    ) -> Tuple[HookAction, Optional[str]]:
        """
        执行单个处理器（含重试和超时）

        Returns:
            (动作, 错误信息)
        """
        last_error = None
        attempts = config.max_retries + 1

        for attempt in range(attempts):
            try:
                action = config.handler(context)
                return (action, None)
            except Exception as e:
                last_error = str(e)
                if attempt < attempts - 1:
                    time.sleep(0.1 * (attempt + 1))  # 指数退避

        return (HookAction.ERROR, last_error)


# ============================================================
# 拦截器链
# ============================================================

class InterceptorChain:
    """
    拦截器链

    提供链式调用模式，每个拦截器可以：
    - 在目标方法前执行前置逻辑
    - 决定是否继续传递到下一个拦截器
    - 在目标方法后执行后置逻辑
    - 修改请求和响应
    """

    def __init__(self):
        self._interceptors: List[Tuple[str, Callable, int]] = []
        self._lock = threading.RLock()

    def add(
        self,
        name: str,
        interceptor: Callable,
        priority: int = 100
    ) -> None:
        """
        添加拦截器

        拦截器签名: interceptor(context, next_fn) -> result
        - context: 调用上下文
        - next_fn: 调用下一个拦截器的函数

        Args:
            name: 拦截器名称
            interceptor: 拦截器函数
            priority: 优先级
        """
        with self._lock:
            self._interceptors.append((name, interceptor, priority))
            self._interceptors.sort(key=lambda x: x[2])

    def remove(self, name: str) -> bool:
        """移除拦截器"""
        with self._lock:
            original_len = len(self._interceptors)
            self._interceptors = [
                (n, fn, p) for n, fn, p in self._interceptors if n != name
            ]
            return len(self._interceptors) < original_len

    def execute(self, context: Dict[str, Any], target: Callable) -> Any:
        """
        执行拦截器链

        Args:
            context: 调用上下文
            target: 最终目标函数

        Returns:
            执行结果
        """
        with self._lock:
            interceptors = list(self._interceptors)

        # 构建调用链（从最后一个拦截器到第一个）
        chain = target
        for name, interceptor, _ in reversed(interceptors):
            current_interceptor = interceptor
            next_in_chain = chain
            chain = lambda ctx, ic=current_interceptor, ni=next_in_chain: ic(ctx, ni)

        return chain(context)

    def list_interceptors(self) -> List[Dict[str, Any]]:
        """列出所有拦截器"""
        with self._lock:
            return [
                {"name": n, "priority": p}
                for n, _, p in self._interceptors
            ]


# ============================================================
# 全局单例
# ============================================================

_hook_manager: Optional[HookManager] = None
_hook_lock = threading.RLock()


def get_hook_manager() -> HookManager:
    """获取全局钩子管理器（双重检查锁定）"""
    global _hook_manager
    if _hook_manager is None:
        with _hook_lock:
            if _hook_manager is None:
                _hook_manager = HookManager()
    return _hook_manager


_interceptor_chain: Optional[InterceptorChain] = None
_chain_lock = threading.RLock()


def get_interceptor_chain() -> InterceptorChain:
    """获取全局拦截器链（双重检查锁定）"""
    global _interceptor_chain
    if _interceptor_chain is None:
        with _chain_lock:
            if _interceptor_chain is None:
                _interceptor_chain = InterceptorChain()
    return _interceptor_chain
