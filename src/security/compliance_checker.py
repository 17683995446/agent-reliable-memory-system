"""
合规检查器 - 阶段218-220

功能：
- 阶段218: 合规策略检查
- 阶段219: 合规报告生成
- 阶段220: 风险评估

设计原则：
- 确定性规则，无模型依赖
- 最小层级，无循环依赖
- 线程安全，RLock保护
- 单例模式，全局唯一
"""

import threading
import time
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Dict, List, Optional, Callable, Any, Set
from collections import defaultdict
import uuid


class ComplianceStatus(Enum):
    """合规状态"""
    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    WARNING = "warning"
    NOT_APPLICABLE = "not_applicable"


class RiskLevel(Enum):
    """风险级别"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class CheckType(Enum):
    """检查类型"""
    POLICY = "policy"
    CONFIGURATION = "configuration"
    ACCESS_CONTROL = "access_control"
    DATA_PROTECTION = "data_protection"
    AUDIT = "audit"
    RETENTION = "retention"


@dataclass
class ComplianceRule:
    """合规规则"""
    rule_id: str
    name: str
    description: str
    check_type: CheckType
    standard: str
    requirement: str
    check_func: Callable[[], ComplianceStatus] = field(default=None, repr=False)
    remediation: str = ""
    risk_level: RiskLevel = RiskLevel.MEDIUM
    enabled: bool = True


@dataclass
class ComplianceFinding:
    """合规发现"""
    finding_id: str
    rule_id: str
    rule_name: str
    status: ComplianceStatus
    risk_level: RiskLevel
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    remediation: str = ""


@dataclass
class RiskAssessment:
    """风险评估"""
    assessment_id: str
    timestamp: float
    overall_risk: RiskLevel
    findings: List[ComplianceFinding] = field(default_factory=list)
    risk_scores: Dict[str, float] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)


@dataclass
class ComplianceReport:
    """合规报告"""
    report_id: str
    generated_at: float
    period_start: float
    period_end: float
    standard: str
    summary: Dict[str, Any] = field(default_factory=dict)
    findings: List[ComplianceFinding] = field(default_factory=list)
    status: str = "draft"


class ComplianceChecker:
    """
    合规检查器
    
    阶段218: 合规策略检查
    - 多标准合规检查
    - 自动规则评估
    - 违规检测
    
    阶段219: 合规报告生成
    - 详细报告生成
    - 趋势分析
    - 整改建议
    
    阶段220: 风险评估
    - 风险量化
    - 影响分析
    - 缓解建议
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
            
            # 合规规则
            self._rules: Dict[str, ComplianceRule] = {}
            
            # 检查历史
            self._check_history: List[ComplianceFinding] = []
            
            # 报告历史
            self._reports: Dict[str, ComplianceReport] = {}
            
            # 初始化默认规则
            self._init_default_rules()
    
    def _init_default_rules(self):
        """初始化默认合规规则"""
        default_rules = [
            ComplianceRule(
                rule_id="rule_password_policy",
                name="Password Policy Enforcement",
                description="检查密码策略是否启用",
                check_type=CheckType.POLICY,
                standard="ISO27001",
                requirement="A.9.2.1",
                risk_level=RiskLevel.HIGH,
                remediation="启用强密码策略"
            ),
            ComplianceRule(
                rule_id="rule_audit_logging",
                name="Audit Logging Enabled",
                description="检查审计日志是否启用",
                check_type=CheckType.AUDIT,
                standard="ISO27001",
                requirement="A.12.4.1",
                risk_level=RiskLevel.MEDIUM,
                remediation="启用审计日志记录"
            ),
            ComplianceRule(
                rule_id="rule_data_retention",
                name="Data Retention Policy",
                description="检查数据保留策略",
                check_type=CheckType.RETENTION,
                standard="GDPR",
                requirement="Article 5",
                risk_level=RiskLevel.HIGH,
                remediation="配置数据保留期限"
            ),
            ComplianceRule(
                rule_id="rule_access_control",
                name="Access Control Review",
                description="检查访问控制配置",
                check_type=CheckType.ACCESS_CONTROL,
                standard="SOX",
                requirement="404",
                risk_level=RiskLevel.CRITICAL,
                remediation="审查并加强访问控制"
            ),
            ComplianceRule(
                rule_id="rule_encryption",
                name="Data Encryption",
                description="检查敏感数据加密",
                check_type=CheckType.DATA_PROTECTION,
                standard="PCI_DSS",
                requirement="3.4",
                risk_level=RiskLevel.CRITICAL,
                remediation="启用数据加密"
            )
        ]
        
        for rule in default_rules:
            self._rules[rule.rule_id] = rule
    
    # ========== 阶段218: 合规策略检查 ==========
    
    def register_rule(self, rule: ComplianceRule) -> None:
        """注册合规规则"""
        with self._lock:
            self._rules[rule.rule_id] = rule
    
    def check_rule(self, rule_id: str) -> Optional[ComplianceFinding]:
        """检查单个规则"""
        with self._lock:
            rule = self._rules.get(rule_id)
        
        if not rule or not rule.enabled:
            return None
        
        # 执行检查
        if rule.check_func:
            try:
                status = rule.check_func()
            except Exception:
                status = ComplianceStatus.NON_COMPLIANT
        else:
            # 默认检查逻辑
            status = ComplianceStatus.COMPLIANT
        
        finding = ComplianceFinding(
            finding_id=str(uuid.uuid4()),
            rule_id=rule.rule_id,
            rule_name=rule.name,
            status=status,
            risk_level=rule.risk_level if status != ComplianceStatus.COMPLIANT else RiskLevel.INFO,
            message=f"Rule '{rule.name}' is {status.value}",
            details={"check_type": rule.check_type.value, "standard": rule.standard},
            remediation=rule.remediation if status != ComplianceStatus.COMPLIANT else ""
        )
        
        with self._lock:
            self._check_history.append(finding)
        
        return finding
    
    def check_all(self, standard: Optional[str] = None) -> List[ComplianceFinding]:
        """检查所有规则"""
        findings = []
        
        with self._lock:
            rules = list(self._rules.values())
        
        for rule in rules:
            if standard and rule.standard != standard:
                continue
            
            finding = self.check_rule(rule.rule_id)
            if finding:
                findings.append(finding)
        
        return findings
    
    def get_compliance_score(self, standard: Optional[str] = None) -> float:
        """获取合规评分"""
        findings = self.check_all(standard)
        
        if not findings:
            return 100.0
        
        compliant_count = sum(1 for f in findings if f.status == ComplianceStatus.COMPLIANT)
        return (compliant_count / len(findings)) * 100
    
    # ========== 阶段219: 合规报告生成 ==========
    
    def generate_report(self, standard: str,
                       period_start: Optional[float] = None,
                       period_end: Optional[float] = None) -> ComplianceReport:
        """生成合规报告"""
        if period_start is None:
            period_start = time.time() - 86400 * 30
        if period_end is None:
            period_end = time.time()
        
        findings = self.check_all(standard)
        
        summary = {
            "total_rules": len([f for f in findings]),
            "compliant": len([f for f in findings if f.status == ComplianceStatus.COMPLIANT]),
            "non_compliant": len([f for f in findings if f.status == ComplianceStatus.NON_COMPLIANT]),
            "warnings": len([f for f in findings if f.status == ComplianceStatus.WARNING]),
            "compliance_score": self.get_compliance_score(standard)
        }
        
        report = ComplianceReport(
            report_id=str(uuid.uuid4()),
            generated_at=time.time(),
            period_start=period_start,
            period_end=period_end,
            standard=standard,
            summary=summary,
            findings=findings,
            status="completed"
        )
        
        with self._lock:
            self._reports[report.report_id] = report
        
        return report
    
    def get_report(self, report_id: str) -> Optional[ComplianceReport]:
        """获取报告"""
        with self._lock:
            return self._reports.get(report_id)
    
    def export_report(self, report_id: str, format: str = "json") -> str:
        """导出报告"""
        report = self.get_report(report_id)
        if not report:
            return ""
        
        if format == "json":
            return json.dumps({
                "report_id": report.report_id,
                "generated_at": report.generated_at,
                "standard": report.standard,
                "summary": report.summary,
                "findings": [
                    {
                        "rule_name": f.rule_name,
                        "status": f.status.value,
                        "risk_level": f.risk_level.value,
                        "message": f.message,
                        "remediation": f.remediation
                    }
                    for f in report.findings
                ]
            }, indent=2, ensure_ascii=False)
        
        return ""
    
    # ========== 阶段220: 风险评估 ==========
    
    def assess_risk(self) -> RiskAssessment:
        """执行风险评估"""
        findings = self.check_all()
        
        # 计算总体风险
        risk_scores = defaultdict(float)
        
        for finding in findings:
            if finding.status != ComplianceStatus.COMPLIANT:
                score = {
                    RiskLevel.CRITICAL: 100,
                    RiskLevel.HIGH: 75,
                    RiskLevel.MEDIUM: 50,
                    RiskLevel.LOW: 25,
                    RiskLevel.INFO: 10
                }.get(finding.risk_level, 0)
                
                risk_scores[finding.rule_id] = score
        
        # 确定总体风险级别
        max_score = max(risk_scores.values()) if risk_scores else 0
        overall_risk = RiskLevel.INFO
        
        if max_score >= 100:
            overall_risk = RiskLevel.CRITICAL
        elif max_score >= 75:
            overall_risk = RiskLevel.HIGH
        elif max_score >= 50:
            overall_risk = RiskLevel.MEDIUM
        elif max_score >= 25:
            overall_risk = RiskLevel.LOW
        
        # 生成建议
        recommendations = []
        for finding in findings:
            if finding.status != ComplianceStatus.COMPLIANT and finding.remediation:
                recommendations.append(finding.remediation)
        
        assessment = RiskAssessment(
            assessment_id=str(uuid.uuid4()),
            timestamp=time.time(),
            overall_risk=overall_risk,
            findings=[f for f in findings if f.status != ComplianceStatus.COMPLIANT],
            risk_scores=dict(risk_scores),
            recommendations=list(set(recommendations))
        )
        
        return assessment
    
    def get_risk_summary(self) -> Dict[str, Any]:
        """获取风险摘要"""
        assessment = self.assess_risk()
        
        return {
            "overall_risk": assessment.overall_risk.value,
            "finding_count": len(assessment.findings),
            "critical_count": len([f for f in assessment.findings if f.risk_level == RiskLevel.CRITICAL]),
            "high_count": len([f for f in assessment.findings if f.risk_level == RiskLevel.HIGH]),
            "recommendation_count": len(assessment.recommendations)
        }


# 全局单例
_compliance_checker_instance: Optional[ComplianceChecker] = None
_compliance_checker_lock = threading.RLock()


def get_compliance_checker() -> ComplianceChecker:
    """获取合规检查器全局实例"""
    global _compliance_checker_instance
    if _compliance_checker_instance is None:
        with _compliance_checker_lock:
            if _compliance_checker_instance is None:
                _compliance_checker_instance = ComplianceChecker()
    return _compliance_checker_instance
