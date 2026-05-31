"""
审计追踪器 - 阶段212-214

功能：
- 阶段212: 操作审计
- 阶段213: 变更追踪
- 阶段214: 合规报告

设计原则：
- 确定性规则，无模型依赖
- 最小层级，无循环依赖
- 线程安全，RLock保护
- 单例模式，全局唯一
"""

import threading
import time
import json
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum, auto
from typing import Dict, List, Optional, Callable, Any, Set, Tuple
from collections import deque, defaultdict
import uuid
import difflib


class AuditLevel(Enum):
    """审计级别"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AuditAction(Enum):
    """审计动作类型"""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGOUT = "logout"
    EXPORT = "export"
    IMPORT = "import"
    CONFIG_CHANGE = "config_change"
    PERMISSION_CHANGE = "permission_change"


class ComplianceStandard(Enum):
    """合规标准"""
    GDPR = "gdpr"
    HIPAA = "hipaa"
    SOX = "sox"
    PCI_DSS = "pci_dss"
    ISO27001 = "iso27001"


@dataclass
class AuditRecord:
    """审计记录"""
    record_id: str
    timestamp: float
    level: AuditLevel
    action: AuditAction
    subject: str  # 用户ID
    resource_type: str
    resource_id: str
    operation: str
    status: str  # success, failure
    details: Dict[str, Any] = field(default_factory=dict)
    ip_address: str = ""
    user_agent: str = ""
    session_id: str = ""
    request_id: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "timestamp": self.timestamp,
            "timestamp_iso": datetime.fromtimestamp(self.timestamp).isoformat(),
            "level": self.level.value,
            "action": self.action.value,
            "subject": self.subject,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "operation": self.operation,
            "status": self.status,
            "details": self.details,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "session_id": self.session_id,
            "request_id": self.request_id
        }


@dataclass
class ChangeRecord:
    """变更记录"""
    change_id: str
    timestamp: float
    subject: str
    resource_type: str
    resource_id: str
    field_name: str
    old_value: Any
    new_value: Any
    change_type: str  # modified, added, removed
    audit_record_id: str = ""


@dataclass
class ComplianceReport:
    """合规报告"""
    report_id: str
    standard: ComplianceStandard
    generated_at: float
    period_start: float
    period_end: float
    summary: Dict[str, Any] = field(default_factory=dict)
    findings: List[Dict[str, Any]] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    status: str = "pending"  # pending, completed, failed


class AuditTracer:
    """
    审计追踪器
    
    阶段212: 操作审计
    - 全面的操作日志记录
    - 多维度查询
    - 审计级别控制
    
    阶段213: 变更追踪
    - 字段级变更记录
    - 差异对比
    - 变更历史
    
    阶段214: 合规报告
    - 多标准合规检查
    - 自动报告生成
    - 违规检测
    """
    
    _instance = None
    _lock = threading.RLock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        with self._lock:
            if self._initialized:
                return
            
            self._initialized = True
            
            # 审计记录存储
            self._audit_records: deque = deque(maxlen=100000)
            self._change_records: deque = deque(maxlen=50000)
            
            # 索引
            self._index_by_subject: Dict[str, Set[str]] = defaultdict(set)
            self._index_by_resource: Dict[str, Set[str]] = defaultdict(set)
            self._index_by_action: Dict[str, Set[str]] = defaultdict(set)
            
            # 处理器
            self._handlers: List[Callable[[AuditRecord], None]] = []
            
            # 配置
            self._min_level = AuditLevel.INFO
            self._enabled_actions: Set[AuditAction] = set(AuditAction)
            
            # 合规配置
            self._compliance_rules: Dict[ComplianceStandard, List[Dict]] = {
                ComplianceStandard.GDPR: [
                    {"name": "data_access_logging", "description": "记录所有数据访问"},
                    {"name": "export_tracking", "description": "追踪数据导出"}
                ],
                ComplianceStandard.ISO27001: [
                    {"name": "access_control", "description": "访问控制审计"},
                    {"name": "change_management", "description": "变更管理审计"}
                ]
            }
    
    # ========== 阶段212: 操作审计 ==========
    
    def log(self, level: AuditLevel, action: AuditAction,
            subject: str, resource_type: str, resource_id: str,
            operation: str, status: str = "success",
            details: Optional[Dict[str, Any]] = None,
            ip_address: str = "", user_agent: str = "",
            session_id: str = "", request_id: str = "") -> AuditRecord:
        """记录审计日志"""
        # 检查级别
        if level not in self._get_levels_to_log():
            return None
        
        # 检查动作是否启用
        if action not in self._enabled_actions:
            return None
        
        record = AuditRecord(
            record_id=str(uuid.uuid4()),
            timestamp=time.time(),
            level=level,
            action=action,
            subject=subject,
            resource_type=resource_type,
            resource_id=resource_id,
            operation=operation,
            status=status,
            details=details or {},
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=session_id,
            request_id=request_id
        )
        
        with self._lock:
            self._audit_records.append(record)
            
            # 更新索引
            self._index_by_subject[subject].add(record.record_id)
            self._index_by_resource[f"{resource_type}:{resource_id}"].add(record.record_id)
            self._index_by_action[action.value].add(record.record_id)
            
            handlers = list(self._handlers)
        
        # 调用处理器
        for handler in handlers:
            try:
                handler(record)
            except Exception:
                pass
        
        return record
    
    def _get_levels_to_log(self) -> Set[AuditLevel]:
        """获取需要记录的级别"""
        levels = {
            AuditLevel.CRITICAL: {AuditLevel.CRITICAL, AuditLevel.ERROR, AuditLevel.WARNING, AuditLevel.INFO, AuditLevel.DEBUG},
            AuditLevel.ERROR: {AuditLevel.ERROR, AuditLevel.WARNING, AuditLevel.INFO, AuditLevel.DEBUG},
            AuditLevel.WARNING: {AuditLevel.WARNING, AuditLevel.INFO, AuditLevel.DEBUG},
            AuditLevel.INFO: {AuditLevel.INFO, AuditLevel.DEBUG},
            AuditLevel.DEBUG: {AuditLevel.DEBUG}
        }
        return levels.get(self._min_level, set())
    
    def query(self, subject: Optional[str] = None,
             action: Optional[AuditAction] = None,
             resource_type: Optional[str] = None,
             resource_id: Optional[str] = None,
             time_start: Optional[float] = None,
             time_end: Optional[float] = None,
             limit: int = 1000) -> List[AuditRecord]:
        """查询审计记录"""
        results = []
        
        with self._lock:
            records = list(self._audit_records)
        
        for record in reversed(records):
            if subject and record.subject != subject:
                continue
            if action and record.action != action:
                continue
            if resource_type and record.resource_type != resource_type:
                continue
            if resource_id and record.resource_id != resource_id:
                continue
            if time_start and record.timestamp < time_start:
                continue
            if time_end and record.timestamp > time_end:
                continue
            
            results.append(record)
            
            if len(results) >= limit:
                break
        
        return results
    
    def get_user_activity(self, subject: str,
                         time_range_seconds: float = 86400) -> List[AuditRecord]:
        """获取用户活动"""
        cutoff = time.time() - time_range_seconds
        return self.query(subject=subject, time_start=cutoff)
    
    def get_resource_history(self, resource_type: str,
                            resource_id: str) -> List[AuditRecord]:
        """获取资源历史"""
        return self.query(resource_type=resource_type, resource_id=resource_id)
    
    # ========== 阶段213: 变更追踪 ==========
    
    def track_change(self, subject: str, resource_type: str,
                    resource_id: str, field_name: str,
                    old_value: Any, new_value: Any,
                    audit_record_id: str = "") -> ChangeRecord:
        """追踪变更"""
        # 如果值相同，不记录
        if old_value == new_value:
            return None
        
        change = ChangeRecord(
            change_id=str(uuid.uuid4()),
            timestamp=time.time(),
            subject=subject,
            resource_type=resource_type,
            resource_id=resource_id,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            change_type="modified" if old_value is not None and new_value is not None else \
                       "added" if old_value is None else "removed",
            audit_record_id=audit_record_id
        )
        
        with self._lock:
            self._change_records.append(change)
        
        return change
    
    def track_object_changes(self, subject: str, resource_type: str,
                            resource_id: str,
                            old_obj: Dict[str, Any],
                            new_obj: Dict[str, Any],
                            audit_record_id: str = "") -> List[ChangeRecord]:
        """追踪对象变更"""
        changes = []
        
        all_keys = set(old_obj.keys()) | set(new_obj.keys())
        
        for key in all_keys:
            old_val = old_obj.get(key)
            new_val = new_obj.get(key)
            
            change = self.track_change(
                subject, resource_type, resource_id,
                key, old_val, new_val, audit_record_id
            )
            
            if change:
                changes.append(change)
        
        return changes
    
    def get_change_history(self, resource_type: str,
                          resource_id: str,
                          field_name: Optional[str] = None) -> List[ChangeRecord]:
        """获取变更历史"""
        with self._lock:
            changes = list(self._change_records)
        
        results = []
        for change in reversed(changes):
            if change.resource_type != resource_type:
                continue
            if change.resource_id != resource_id:
                continue
            if field_name and change.field_name != field_name:
                continue
            results.append(change)
        
        return results
    
    def generate_diff(self, old_text: str, new_text: str) -> str:
        """生成文本差异"""
        diff = difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile="old", tofile="new"
        )
        return "".join(diff)
    
    # ========== 阶段214: 合规报告 ==========
    
    def generate_compliance_report(self, standard: ComplianceStandard,
                                  period_start: Optional[float] = None,
                                  period_end: Optional[float] = None) -> ComplianceReport:
        """生成合规报告"""
        if period_start is None:
            period_start = time.time() - 86400 * 30  # 默认30天
        if period_end is None:
            period_end = time.time()
        
        report = ComplianceReport(
            report_id=str(uuid.uuid4()),
            standard=standard,
            generated_at=time.time(),
            period_start=period_start,
            period_end=period_end
        )
        
        # 获取规则
        rules = self._compliance_rules.get(standard, [])
        
        findings = []
        for rule in rules:
            finding = self._check_compliance_rule(rule, period_start, period_end)
            if finding:
                findings.append(finding)
        
        report.findings = findings
        report.summary = {
            "total_rules_checked": len(rules),
            "violations_found": len([f for f in findings if f.get("severity") == "violation"]),
            "warnings": len([f for f in findings if f.get("severity") == "warning"]),
            "passed": len([f for f in findings if f.get("severity") == "pass"])
        }
        report.status = "completed"
        
        return report
    
    def _check_compliance_rule(self, rule: Dict,
                              period_start: float,
                              period_end: float) -> Optional[Dict]:
        """检查合规规则"""
        rule_name = rule.get("name")
        
        if rule_name == "data_access_logging":
            # 检查是否有数据访问记录
            records = self.query(
                action=AuditAction.READ,
                time_start=period_start,
                time_end=period_end,
                limit=1
            )
            return {
                "rule": rule_name,
                "description": rule.get("description"),
                "severity": "pass" if records else "warning",
                "details": "Data access logging is active" if records else "No data access records found"
            }
        
        elif rule_name == "export_tracking":
            records = self.query(
                action=AuditAction.EXPORT,
                time_start=period_start,
                time_end=period_end
            )
            return {
                "rule": rule_name,
                "description": rule.get("description"),
                "severity": "pass",
                "details": f"{len(records)} export operations tracked"
            }
        
        return None
    
    def export_audit_log(self, format: str = "json",
                        time_start: Optional[float] = None,
                        time_end: Optional[float] = None) -> str:
        """导出审计日志"""
        records = self.query(time_start=time_start, time_end=time_end, limit=10000)
        
        if format == "json":
            data = [r.to_dict() for r in records]
            return json.dumps(data, indent=2, ensure_ascii=False)
        
        elif format == "csv":
            lines = ["timestamp,level,action,subject,resource_type,resource_id,operation,status"]
            for r in records:
                ts = datetime.fromtimestamp(r.timestamp).isoformat()
                lines.append(f'"{ts}","{r.level.value}","{r.action.value}","{r.subject}","{r.resource_type}","{r.resource_id}","{r.operation}","{r.status}"')
            return "\n".join(lines)
        
        return ""


# 全局单例
_audit_tracer_instance: Optional[AuditTracer] = None
_audit_tracer_lock = threading.RLock()


def get_audit_tracer() -> AuditTracer:
    """获取审计追踪器全局实例"""
    global _audit_tracer_instance
    if _audit_tracer_instance is None:
        with _audit_tracer_lock:
            if _audit_tracer_instance is None:
                _audit_tracer_instance = AuditTracer()
    return _audit_tracer_instance
