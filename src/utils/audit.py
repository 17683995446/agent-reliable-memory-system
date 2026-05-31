#!/usr/bin/env python3
"""
审计日志 - 阶段155-157
操作日志与访问追踪
"""

import json
import threading
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum


class AuditAction(Enum):
    """审计动作"""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    SHARE = "share"
    EXPORT = "export"
    IMPORT = "import"
    LOGIN = "login"
    LOGOUT = "logout"
    CONFIG_CHANGE = "config_change"
    ACCESS_DENIED = "access_denied"


@dataclass
class AuditEntry:
    """审计条目"""
    timestamp: str
    action: str
    user_id: str
    resource_type: str
    resource_id: str
    details: Dict[str, Any] = field(default_factory=dict)
    ip_address: str = ""
    user_agent: str = ""
    success: bool = True
    duration_ms: float = 0.0


class AuditLogger:
    """
    审计日志器

    记录系统操作：
    - 操作日志
    - 访问追踪
    - 安全审计
    """

    def __init__(self, max_entries: int = 10000, log_file: Optional[str] = None):
        self.max_entries = max_entries
        self.log_file = log_file
        self._entries: List[AuditEntry] = []
        self._lock = threading.RLock()
        self._stats = {
            "total_entries": 0,
            "by_action": {},
            "by_user": {},
        }

    def log(
        self,
        action: AuditAction,
        user_id: str,
        resource_type: str,
        resource_id: str,
        details: Optional[Dict[str, Any]] = None,
        ip_address: str = "",
        user_agent: str = "",
        success: bool = True,
        duration_ms: float = 0.0
    ) -> AuditEntry:
        """
        记录审计日志

        Args:
            action: 动作类型
            user_id: 用户ID
            resource_type: 资源类型
            resource_id: 资源ID
            details: 详细信息
            ip_address: IP地址
            user_agent: 用户代理
            success: 是否成功
            duration_ms: 耗时（毫秒）

        Returns:
            审计条目
        """
        entry = AuditEntry(
            timestamp=datetime.now().isoformat(),
            action=action.value,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            ip_address=ip_address,
            user_agent=user_agent,
            success=success,
            duration_ms=duration_ms,
        )

        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self.max_entries:
                self._entries = self._entries[-self.max_entries:]

            # 更新统计
            self._stats["total_entries"] += 1
            self._stats["by_action"][action.value] = (
                self._stats["by_action"].get(action.value, 0) + 1
            )
            self._stats["by_user"][user_id] = (
                self._stats["by_user"].get(user_id, 0) + 1
            )

        # 写入文件
        if self.log_file:
            self._write_to_file(entry)

        return entry

    def _write_to_file(self, entry: AuditEntry):
        """写入日志文件"""
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
        except Exception:
            pass

    def query(
        self,
        user_id: Optional[str] = None,
        action: Optional[AuditAction] = None,
        resource_id: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        success: Optional[bool] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        查询审计日志

        Args:
            user_id: 用户ID过滤
            action: 动作过滤
            resource_id: 资源ID过滤
            start_time: 开始时间
            end_time: 结束时间
            success: 成功状态过滤
            limit: 返回数量

        Returns:
            匹配的审计条目列表
        """
        with self._lock:
            entries = list(reversed(self._entries))

        result = []
        for entry in entries:
            # 过滤条件
            if user_id and entry.user_id != user_id:
                continue
            if action and entry.action != action.value:
                continue
            if resource_id and entry.resource_id != resource_id:
                continue
            if start_time and entry.timestamp < start_time:
                continue
            if end_time and entry.timestamp > end_time:
                continue
            if success is not None and entry.success != success:
                continue

            result.append(asdict(entry))
            if len(result) >= limit:
                break

        return result

    def get_user_activity(
        self,
        user_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """获取用户活动记录"""
        return self.query(user_id=user_id, limit=limit)

    def get_resource_history(
        self,
        resource_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """获取资源操作历史"""
        return self.query(resource_id=resource_id, limit=limit)

    def get_failed_operations(
        self,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取失败操作"""
        return self.query(success=False, limit=limit)

    def get_security_events(
        self,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取安全相关事件"""
        with self._lock:
            entries = list(reversed(self._entries))

        security_actions = {
            AuditAction.LOGIN.value,
            AuditAction.LOGOUT.value,
            AuditAction.ACCESS_DENIED.value,
            AuditAction.CONFIG_CHANGE.value,
        }

        result = []
        for entry in entries:
            if entry.action in security_actions:
                result.append(asdict(entry))
                if len(result) >= limit:
                    break

        return result

    def get_stats(self) -> Dict[str, Any]:
        """获取审计统计"""
        with self._lock:
            return {
                **self._stats,
                "entries_in_memory": len(self._entries),
                "max_entries": self.max_entries,
            }

    def clear(self):
        """清空内存中的日志"""
        with self._lock:
            self._entries.clear()


# 全局审计日志器
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """获取全局审计日志器"""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger
