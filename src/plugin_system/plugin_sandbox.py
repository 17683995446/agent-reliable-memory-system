#!/usr/bin/env python3
"""
插件沙箱 (PluginSandbox) - 阶段324

职责：
- 隔离执行：在受控环境中执行插件代码
- 资源限制：CPU时间、内存、文件系统、网络访问限制
- 安全审计：记录插件的所有操作，检测异常行为
- 权限控制：基于角色的访问控制（RBAC）
- 运行时监控：实时监控资源使用情况

设计原则：
- 确定性规则，无模型依赖
- 线程安全（RLock）
- 最小权限原则
- 失败安全（fail-safe）
"""

import threading
import time
import traceback
import resource as res_module
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


# ============================================================
# 枚举与数据结构
# ============================================================

class Permission(Enum):
    """插件权限"""
    READ_MEMORY = "read_memory"         # 读取内存
    WRITE_MEMORY = "write_memory"       # 写入内存
    DELETE_MEMORY = "delete_memory"     # 删除内存
    READ_FILE = "read_file"             # 读取文件
    WRITE_FILE = "write_file"           # 写入文件
    NETWORK_ACCESS = "network_access"   # 网络访问
    SYSTEM_CALL = "system_call"         # 系统调用
    IMPORT_MODULE = "import_module"     # 导入模块
    ENV_ACCESS = "env_access"           # 环境变量访问
    SUBPROCESS = "subprocess"           # 子进程
    ALL = "all"                         # 所有权限


class SandboxLevel(Enum):
    """沙箱安全级别"""
    TRUSTED = "trusted"       # 受信任：无限制
    STANDARD = "standard"     # 标准：基本限制
    RESTRICTED = "restricted" # 受限：严格限制
    ISOLATED = "isolated"     # 隔离：最大限制


class ViolationType(Enum):
    """违规类型"""
    PERMISSION_DENIED = "permission_denied"
    RESOURCE_EXCEEDED = "resource_exceeded"
    TIMEOUT = "timeout"
    INVALID_OPERATION = "invalid_operation"
    RATE_LIMITED = "rate_limited"


@dataclass
class ResourceLimits:
    """资源限制配置"""
    max_memory_mb: int = 256           # 最大内存（MB）
    max_cpu_time_sec: float = 30.0     # 最大CPU时间（秒）
    max_execution_time_sec: float = 60.0  # 最大执行时间（秒）
    max_file_size_mb: int = 50         # 最大文件大小（MB）
    max_open_files: int = 100          # 最大打开文件数
    max_subprocesses: int = 0          # 最大子进程数（0=禁止）
    max_network_connections: int = 0   # 最大网络连接数（0=禁止）
    max_calls_per_minute: int = 1000   # 每分钟最大调用次数
    max_output_size_kb: int = 1024     # 最大输出大小（KB）


@dataclass
class ViolationRecord:
    """违规记录"""
    plugin_name: str
    violation_type: ViolationType
    permission: Optional[Permission] = None
    message: str = ""
    timestamp: float = 0.0
    stack_trace: str = ""

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


@dataclass
class AuditEntry:
    """审计条目"""
    plugin_name: str
    action: str
    target: str = ""
    result: str = "allowed"
    timestamp: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


@dataclass
class ResourceUsage:
    """资源使用情况"""
    memory_mb: float = 0.0
    cpu_time_sec: float = 0.0
    execution_time_sec: float = 0.0
    open_files: int = 0
    calls_this_minute: int = 0
    total_calls: int = 0
    violations: int = 0


@dataclass
class SandboxResult:
    """沙箱执行结果"""
    success: bool
    plugin_name: str
    result: Any = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    memory_used_mb: float = 0.0
    was_sandboxed: bool = True
    violation: Optional[ViolationRecord] = None


# ============================================================
# 权限配置
# ============================================================

# 各安全级别对应的默认权限
LEVEL_PERMISSIONS: Dict[SandboxLevel, Set[Permission]] = {
    SandboxLevel.TRUSTED: {Permission.ALL},
    SandboxLevel.STANDARD: {
        Permission.READ_MEMORY,
        Permission.WRITE_MEMORY,
        Permission.READ_FILE,
    },
    SandboxLevel.RESTRICTED: {
        Permission.READ_MEMORY,
    },
    SandboxLevel.ISOLATED: set(),
}

# 各安全级别对应的默认资源限制
LEVEL_LIMITS: Dict[SandboxLevel, ResourceLimits] = {
    SandboxLevel.TRUSTED: ResourceLimits(
        max_memory_mb=1024,
        max_cpu_time_sec=300.0,
        max_execution_time_sec=600.0,
        max_file_size_mb=500,
        max_open_files=1000,
        max_subprocesses=10,
        max_network_connections=50,
        max_calls_per_minute=10000,
    ),
    SandboxLevel.STANDARD: ResourceLimits(
        max_memory_mb=256,
        max_cpu_time_sec=30.0,
        max_execution_time_sec=60.0,
        max_file_size_mb=50,
        max_open_files=100,
        max_subprocesses=0,
        max_network_connections=0,
        max_calls_per_minute=1000,
    ),
    SandboxLevel.RESTRICTED: ResourceLimits(
        max_memory_mb=64,
        max_cpu_time_sec=10.0,
        max_execution_time_sec=30.0,
        max_file_size_mb=10,
        max_open_files=10,
        max_subprocesses=0,
        max_network_connections=0,
        max_calls_per_minute=100,
    ),
    SandboxLevel.ISOLATED: ResourceLimits(
        max_memory_mb=16,
        max_cpu_time_sec=5.0,
        max_execution_time_sec=10.0,
        max_file_size_mb=0,
        max_open_files=0,
        max_subprocesses=0,
        max_network_connections=0,
        max_calls_per_minute=10,
    ),
}


# ============================================================
# 安全审计器
# ============================================================

class SecurityAuditor:
    """
    安全审计器

    记录所有插件操作，检测异常行为模式
    """

    def __init__(self, max_entries: int = 10000):
        self._audit_log: deque = deque(maxlen=max_entries)
        self._violations: deque = deque(maxlen=1000)
        self._lock = threading.RLock()
        self._alert_callbacks: List[Callable[[ViolationRecord], None]] = []

    def log(self, entry: AuditEntry) -> None:
        """记录审计条目"""
        with self._lock:
            self._audit_log.append(entry)

    def record_violation(self, violation: ViolationRecord) -> None:
        """记录违规"""
        with self._lock:
            self._violations.append(violation)

            # 同时记录到审计日志
            audit = AuditEntry(
                plugin_name=violation.plugin_name,
                action=f"violation:{violation.violation_type.value}",
                result="denied",
                details={"message": violation.message},
            )
            self._audit_log.append(audit)

        # 通知告警回调
        for cb in self._alert_callbacks:
            try:
                cb(violation)
            except Exception:
                pass

    def get_audit_log(
        self,
        plugin_name: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """查询审计日志"""
        with self._lock:
            entries = list(self._audit_log)

        if plugin_name:
            entries = [e for e in entries if e.plugin_name == plugin_name]
        if action:
            entries = [e for e in entries if e.action == action]

        return [
            {
                "plugin": e.plugin_name,
                "action": e.action,
                "target": e.target,
                "result": e.result,
                "timestamp": e.timestamp,
                "details": e.details,
            }
            for e in entries[-limit:]
        ]

    def get_violations(
        self,
        plugin_name: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """查询违规记录"""
        with self._lock:
            violations = list(self._violations)

        if plugin_name:
            violations = [v for v in violations if v.plugin_name == plugin_name]

        return [
            {
                "plugin": v.plugin_name,
                "type": v.violation_type.value,
                "permission": v.permission.value if v.permission else None,
                "message": v.message,
                "timestamp": v.timestamp,
            }
            for v in violations[-limit:]
        ]

    def get_plugin_summary(self, plugin_name: str) -> Dict[str, Any]:
        """获取插件安全摘要"""
        with self._lock:
            total_actions = sum(
                1 for e in self._audit_log if e.plugin_name == plugin_name
            )
            denied_actions = sum(
                1 for e in self._audit_log
                if e.plugin_name == plugin_name and e.result == "denied"
            )
            total_violations = sum(
                1 for v in self._violations if v.plugin_name == plugin_name
            )

        return {
            "plugin": plugin_name,
            "total_actions": total_actions,
            "denied_actions": denied_actions,
            "total_violations": total_violations,
            "risk_score": min(100, (denied_actions * 10 + total_violations * 25)),
        }

    def on_alert(self, callback: Callable[[ViolationRecord], None]) -> None:
        """添加违规告警回调"""
        with self._lock:
            self._alert_callbacks.append(callback)

    def clear(self) -> None:
        """清除所有记录"""
        with self._lock:
            self._audit_log.clear()
            self._violations.clear()

    def get_stats(self) -> Dict[str, Any]:
        """获取审计统计"""
        with self._lock:
            return {
                "total_audit_entries": len(self._audit_log),
                "total_violations": len(self._violations),
                "unique_plugins_audited": len(set(
                    e.plugin_name for e in self._audit_log
                )),
            }


# ============================================================
# 插件沙箱
# ============================================================

class PluginSandbox:
    """
    插件沙箱

    核心功能：
    1. 权限检查：在执行前验证权限
    2. 资源限制：监控和限制资源使用
    3. 安全执行：在受控环境中执行插件代码
    4. 违规检测：检测并记录违规行为
    5. 速率限制：防止插件过度调用
    """

    def __init__(self):
        self._permissions: Dict[str, Set[Permission]] = {}
        self._limits: Dict[str, ResourceLimits] = {}
        self._levels: Dict[str, SandboxLevel] = {}
        self._usage: Dict[str, ResourceUsage] = {}
        self._call_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self._auditor = SecurityAuditor()
        self._lock = threading.RLock()
        self._default_level = SandboxLevel.STANDARD

    # ---- 配置 ----

    def configure(
        self,
        plugin_name: str,
        level: Optional[SandboxLevel] = None,
        permissions: Optional[Set[Permission]] = None,
        limits: Optional[ResourceLimits] = None
    ) -> None:
        """
        配置插件沙箱

        Args:
            plugin_name: 插件名称
            level: 安全级别
            permissions: 自定义权限集合
            limits: 自定义资源限制
        """
        with self._lock:
            if level:
                self._levels[plugin_name] = level
                # 应用级别默认权限和限制
                if permissions is None:
                    self._permissions[plugin_name] = set(LEVEL_PERMISSIONS[level])
                if limits is None:
                    self._limits[plugin_name] = ResourceLimits(
                        **LEVEL_LIMITS[level].__dict__
                    )

            if permissions is not None:
                self._permissions[plugin_name] = permissions

            if limits is not None:
                self._limits[plugin_name] = limits

            # 初始化使用记录
            if plugin_name not in self._usage:
                self._usage[plugin_name] = ResourceUsage()

    def set_default_level(self, level: SandboxLevel) -> None:
        """设置默认安全级别"""
        with self._lock:
            self._default_level = level

    def grant_permission(self, plugin_name: str, permission: Permission) -> None:
        """授予权限"""
        with self._lock:
            if plugin_name not in self._permissions:
                level = self._levels.get(plugin_name, self._default_level)
                self._permissions[plugin_name] = set(LEVEL_PERMISSIONS[level])
            self._permissions[plugin_name].add(permission)

    def revoke_permission(self, plugin_name: str, permission: Permission) -> None:
        """撤销权限"""
        with self._lock:
            if plugin_name in self._permissions:
                self._permissions[plugin_name].discard(permission)

    # ---- 权限检查 ----

    def check_permission(
        self,
        plugin_name: str,
        permission: Permission
    ) -> bool:
        """
        检查插件是否具有指定权限

        Args:
            plugin_name: 插件名称
            permission: 所需权限

        Returns:
            是否具有权限
        """
        with self._lock:
            perms = self._permissions.get(plugin_name)
            if perms is None:
                # 未配置的插件使用默认级别
                level = self._levels.get(plugin_name, self._default_level)
                perms = LEVEL_PERMISSIONS[level]

            if Permission.ALL in perms:
                return True

            allowed = permission in perms

            # 记录审计
            self._auditor.log(AuditEntry(
                plugin_name=plugin_name,
                action=f"check:{permission.value}",
                result="allowed" if allowed else "denied",
            ))

            return allowed

    def require_permission(
        self,
        plugin_name: str,
        permission: Permission
    ) -> Optional[ViolationRecord]:
        """
        要求权限（不通过时记录违规）

        Returns:
            违规记录（如果权限不足），否则None
        """
        if self.check_permission(plugin_name, permission):
            return None

        violation = ViolationRecord(
            plugin_name=plugin_name,
            violation_type=ViolationType.PERMISSION_DENIED,
            permission=permission,
            message=f"Plugin '{plugin_name}' lacks permission '{permission.value}'",
        )
        self._auditor.record_violation(violation)

        with self._lock:
            if plugin_name in self._usage:
                self._usage[plugin_name].violations += 1

        return violation

    # ---- 资源限制 ----

    def check_rate_limit(self, plugin_name: str) -> bool:
        """
        检查速率限制

        Returns:
            是否在限制范围内（True=允许继续）
        """
        with self._lock:
            limits = self._limits.get(plugin_name)
            if limits is None:
                return True

            now = time.time()
            history = self._call_history[plugin_name]

            # 清理一分钟前的记录
            while history and history[0] < now - 60:
                history.popleft()

            current_rate = len(history)

            if plugin_name in self._usage:
                self._usage[plugin_name].calls_this_minute = current_rate

            if current_rate >= limits.max_calls_per_minute:
                violation = ViolationRecord(
                    plugin_name=plugin_name,
                    violation_type=ViolationType.RATE_LIMITED,
                    message=f"Rate limit exceeded: {current_rate}/{limits.max_calls_per_minute}",
                )
                self._auditor.record_violation(violation)
                return False

            history.append(now)
            return True

    def record_call(self, plugin_name: str) -> None:
        """记录一次调用"""
        with self._lock:
            if plugin_name in self._usage:
                self._usage[plugin_name].total_calls += 1

    def get_usage(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """获取插件资源使用情况"""
        with self._lock:
            usage = self._usage.get(plugin_name)
            if usage is None:
                return None

            return {
                "memory_mb": usage.memory_mb,
                "cpu_time_sec": usage.cpu_time_sec,
                "execution_time_sec": usage.execution_time_sec,
                "open_files": usage.open_files,
                "calls_this_minute": usage.calls_this_minute,
                "total_calls": usage.total_calls,
                "violations": usage.violations,
            }

    # ---- 安全执行 ----

    def execute(
        self,
        plugin_name: str,
        func: Callable,
        *args,
        required_permission: Optional[Permission] = None,
        timeout: Optional[float] = None,
        **kwargs
    ) -> SandboxResult:
        """
        在沙箱中安全执行函数

        Args:
            plugin_name: 插件名称
            func: 要执行的函数
            *args: 位置参数
            required_permission: 所需权限
            timeout: 超时时间（秒）
            **kwargs: 关键字参数

        Returns:
            沙箱执行结果
        """
        start = time.monotonic()

        # 权限检查
        if required_permission:
            violation = self.require_permission(plugin_name, required_permission)
            if violation:
                return SandboxResult(
                    success=False,
                    plugin_name=plugin_name,
                    error=f"Permission denied: {required_permission.value}",
                    violation=violation,
                )

        # 速率限制检查
        if not self.check_rate_limit(plugin_name):
            return SandboxResult(
                success=False,
                plugin_name=plugin_name,
                error="Rate limit exceeded",
                violation=ViolationRecord(
                    plugin_name=plugin_name,
                    violation_type=ViolationType.RATE_LIMITED,
                    message="Rate limit exceeded",
                ),
            )

        self.record_call(plugin_name)

        # 获取超时限制
        if timeout is None:
            with self._lock:
                limits = self._limits.get(plugin_name)
                if limits:
                    timeout = limits.max_execution_time_sec

        # 执行
        try:
            if timeout and timeout > 0:
                result = self._execute_with_timeout(func, timeout, *args, **kwargs)
            else:
                result = func(*args, **kwargs)

            duration = (time.monotonic() - start) * 1000

            # 更新使用统计
            with self._lock:
                if plugin_name in self._usage:
                    self._usage[plugin_name].execution_time_sec += duration / 1000

            return SandboxResult(
                success=True,
                plugin_name=plugin_name,
                result=result,
                execution_time_ms=duration,
            )

        except Exception as e:
            duration = (time.monotonic() - start) * 1000

            violation = ViolationRecord(
                plugin_name=plugin_name,
                violation_type=ViolationType.TIMEOUT if "timeout" in str(e).lower() else ViolationType.INVALID_OPERATION,
                message=str(e),
                stack_trace=traceback.format_exc(),
            )
            self._auditor.record_violation(violation)

            with self._lock:
                if plugin_name in self._usage:
                    self._usage[plugin_name].violations += 1

            return SandboxResult(
                success=False,
                plugin_name=plugin_name,
                error=str(e),
                execution_time_ms=duration,
                violation=violation,
            )

    def _execute_with_timeout(
        self,
        func: Callable,
        timeout: float,
        *args,
        **kwargs
    ) -> Any:
        """带超时的执行"""
        result = [None]
        error = [None]

        def target():
            try:
                result[0] = func(*args, **kwargs)
            except Exception as e:
                error[0] = e

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            raise TimeoutError(f"Execution timed out after {timeout}s")

        if error[0]:
            raise error[0]

        return result[0]

    # ---- 审计 ----

    def get_auditor(self) -> SecurityAuditor:
        """获取安全审计器"""
        return self._auditor

    # ---- 统计 ----

    def get_stats(self) -> Dict[str, Any]:
        """获取沙箱统计信息"""
        with self._lock:
            level_counts = {}
            for level in SandboxLevel:
                count = sum(1 for l in self._levels.values() if l == level)
                if count > 0:
                    level_counts[level.value] = count

            return {
                "configured_plugins": len(self._permissions),
                "level_distribution": level_counts,
                "default_level": self._default_level.value,
                "auditor_stats": self._auditor.get_stats(),
            }


# ============================================================
# 全局单例
# ============================================================

_plugin_sandbox: Optional[PluginSandbox] = None
_sandbox_lock = threading.RLock()


def get_plugin_sandbox() -> PluginSandbox:
    """获取全局插件沙箱（双重检查锁定）"""
    global _plugin_sandbox
    if _plugin_sandbox is None:
        with _sandbox_lock:
            if _plugin_sandbox is None:
                _plugin_sandbox = PluginSandbox()
    return _plugin_sandbox
