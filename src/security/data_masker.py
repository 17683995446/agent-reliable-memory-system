"""
数据脱敏器 - 阶段215-217

功能：
- 阶段215: 敏感数据识别
- 阶段216: 脱敏规则
- 阶段217: 动态脱敏

设计原则：
- 确定性规则，无模型依赖
- 最小层级，无循环依赖
- 线程安全，RLock保护
- 单例模式，全局唯一
"""

import threading
import re
import hashlib
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Callable, Any, Set, Union
from collections import defaultdict
import uuid


class SensitiveType(Enum):
    """敏感数据类型"""
    EMAIL = "email"
    PHONE = "phone"
    ID_CARD = "id_card"
    CREDIT_CARD = "credit_card"
    BANK_ACCOUNT = "bank_account"
    PASSWORD = "password"
    API_KEY = "api_key"
    TOKEN = "token"
    IP_ADDRESS = "ip_address"
    MAC_ADDRESS = "mac_address"
    NAME = "name"
    ADDRESS = "address"
    CUSTOM = "custom"


class MaskingMethod(Enum):
    """脱敏方法"""
    FULL = "full"           # 完全脱敏
    PARTIAL = "partial"     # 部分脱敏
    HASH = "hash"           # 哈希
    REPLACE = "replace"     # 替换
    TRUNCATE = "truncate"   # 截断
    ENCRYPT = "encrypt"     # 加密（简化实现）


@dataclass
class MaskingRule:
    """脱敏规则"""
    rule_id: str
    name: str
    sensitive_type: SensitiveType
    pattern: str
    masking_method: MaskingMethod
    preserve_chars: int = 0  # 保留前后字符数
    replacement: str = "***"
    enabled: bool = True
    compiled_pattern: Any = field(default=None, repr=False)
    
    def __post_init__(self):
        if self.compiled_pattern is None and self.pattern:
            try:
                self.compiled_pattern = re.compile(self.pattern)
            except re.error:
                self.compiled_pattern = None


@dataclass
class MaskingPolicy:
    """脱敏策略"""
    policy_id: str
    name: str
    description: str
    rules: List[str]  # rule_ids
    context: str  # 应用场景
    priority: int = 0
    enabled: bool = True


class DataMasker:
    """
    数据脱敏器
    
    阶段215: 敏感数据识别
    - 预定义敏感类型模式
    - 自定义敏感规则
    - 自动检测
    
    阶段216: 脱敏规则
    - 多种脱敏方法
    - 规则优先级
    - 条件脱敏
    
    阶段217: 动态脱敏
    - 基于上下文的脱敏
    - 角色感知脱敏
    - 字段级脱敏
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
            
            # 脱敏规则
            self._rules: Dict[str, MaskingRule] = {}
            
            # 脱敏策略
            self._policies: Dict[str, MaskingPolicy] = {}
            
            # 初始化默认规则
            self._init_default_rules()
    
    def _init_default_rules(self):
        """初始化默认脱敏规则"""
        default_rules = [
            MaskingRule(
                rule_id="rule_email",
                name="Email Masking",
                sensitive_type=SensitiveType.EMAIL,
                pattern=r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
                masking_method=MaskingMethod.PARTIAL,
                preserve_chars=2
            ),
            MaskingRule(
                rule_id="rule_phone",
                name="Phone Masking",
                sensitive_type=SensitiveType.PHONE,
                pattern=r'\b1[3-9]\d{9}\b',
                masking_method=MaskingMethod.PARTIAL,
                preserve_chars=3
            ),
            MaskingRule(
                rule_id="rule_id_card",
                name="ID Card Masking",
                sensitive_type=SensitiveType.ID_CARD,
                pattern=r'\b\d{17}[\dXx]\b',
                masking_method=MaskingMethod.PARTIAL,
                preserve_chars=4
            ),
            MaskingRule(
                rule_id="rule_credit_card",
                name="Credit Card Masking",
                sensitive_type=SensitiveType.CREDIT_CARD,
                pattern=r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',
                masking_method=MaskingMethod.PARTIAL,
                preserve_chars=4
            ),
            MaskingRule(
                rule_id="rule_password",
                name="Password Masking",
                sensitive_type=SensitiveType.PASSWORD,
                pattern=r'(?i)(password|passwd|pwd)\s*[:=]\s*\S+',
                masking_method=MaskingMethod.REPLACE,
                replacement="password=***"
            ),
            MaskingRule(
                rule_id="rule_api_key",
                name="API Key Masking",
                sensitive_type=SensitiveType.API_KEY,
                pattern=r'(?i)(api[_-]?key|apikey)\s*[:=]\s*[\w-]+',
                masking_method=MaskingMethod.REPLACE,
                replacement="api_key=***"
            ),
            MaskingRule(
                rule_id="rule_token",
                name="Token Masking",
                sensitive_type=SensitiveType.TOKEN,
                pattern=r'(?i)(token|bearer)\s+\S+',
                masking_method=MaskingMethod.REPLACE,
                replacement="token ***"
            ),
            MaskingRule(
                rule_id="rule_ip",
                name="IP Address Masking",
                sensitive_type=SensitiveType.IP_ADDRESS,
                pattern=r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
                masking_method=MaskingMethod.PARTIAL,
                preserve_chars=3
            )
        ]
        
        for rule in default_rules:
            self._rules[rule.rule_id] = rule
    
    # ========== 阶段215: 敏感数据识别 ==========
    
    def detect_sensitive(self, text: str) -> List[Dict[str, Any]]:
        """检测敏感数据"""
        findings = []
        
        with self._lock:
            rules = [r for r in self._rules.values() if r.enabled]
        
        for rule in rules:
            if not rule.compiled_pattern:
                continue
            
            for match in rule.compiled_pattern.finditer(text):
                findings.append({
                    "type": rule.sensitive_type.value,
                    "rule_id": rule.rule_id,
                    "start": match.start(),
                    "end": match.end(),
                    "value": match.group()
                })
        
        return findings
    
    def add_rule(self, name: str, sensitive_type: SensitiveType,
                pattern: str, masking_method: MaskingMethod,
                preserve_chars: int = 0,
                replacement: str = "***") -> MaskingRule:
        """添加脱敏规则"""
        rule = MaskingRule(
            rule_id=str(uuid.uuid4()),
            name=name,
            sensitive_type=sensitive_type,
            pattern=pattern,
            masking_method=masking_method,
            preserve_chars=preserve_chars,
            replacement=replacement
        )
        
        with self._lock:
            self._rules[rule.rule_id] = rule
        
        return rule
    
    def remove_rule(self, rule_id: str) -> bool:
        """移除脱敏规则"""
        with self._lock:
            if rule_id in self._rules:
                del self._rules[rule_id]
                return True
            return False
    
    # ========== 阶段216: 脱敏规则 ==========
    
    def mask(self, text: str, rule_ids: Optional[List[str]] = None) -> str:
        """脱敏文本"""
        if not text:
            return text
        
        with self._lock:
            if rule_ids:
                rules = [self._rules[rid] for rid in rule_ids if rid in self._rules]
            else:
                rules = [r for r in self._rules.values() if r.enabled]
        
        result = text
        
        for rule in rules:
            if not rule.compiled_pattern:
                continue
            
            result = rule.compiled_pattern.sub(
                lambda m: self._apply_masking(m.group(), rule),
                result
            )
        
        return result
    
    def _apply_masking(self, value: str, rule: MaskingRule) -> str:
        """应用脱敏"""
        if rule.masking_method == MaskingMethod.FULL:
            return rule.replacement
        
        elif rule.masking_method == MaskingMethod.PARTIAL:
            preserve = rule.preserve_chars
            if len(value) <= preserve * 2:
                return rule.replacement
            return value[:preserve] + "***" + value[-preserve:]
        
        elif rule.masking_method == MaskingMethod.HASH:
            return hashlib.sha256(value.encode()).hexdigest()[:16]
        
        elif rule.masking_method == MaskingMethod.REPLACE:
            return rule.replacement
        
        elif rule.masking_method == MaskingMethod.TRUNCATE:
            return value[:rule.preserve_chars] + "..."
        
        return rule.replacement
    
    def mask_dict(self, data: Dict[str, Any],
                 sensitive_fields: Optional[List[str]] = None) -> Dict[str, Any]:
        """脱敏字典"""
        result = {}
        
        for key, value in data.items():
            if sensitive_fields and key in sensitive_fields:
                result[key] = self.mask(str(value))
            elif isinstance(value, str):
                result[key] = self.mask(value)
            elif isinstance(value, dict):
                result[key] = self.mask_dict(value, sensitive_fields)
            else:
                result[key] = value
        
        return result
    
    # ========== 阶段217: 动态脱敏 ==========
    
    def mask_by_role(self, text: str, role: str) -> str:
        """基于角色脱敏"""
        # 不同角色看到不同级别的脱敏
        role_policies = {
            "admin": [],  # 管理员不脱敏
            "user": ["rule_email", "rule_phone", "rule_id_card", "rule_credit_card"],
            "guest": None  # 全部脱敏
        }
        
        rule_ids = role_policies.get(role)
        if rule_ids is None:
            return self.mask(text)
        if not rule_ids:
            return text
        
        return self.mask(text, rule_ids)
    
    def mask_field(self, field_name: str, value: Any,
                  context: str = "default") -> Any:
        """字段级脱敏"""
        sensitive_fields = {
            "email", "phone", "mobile", "tel",
            "id_card", "idcard", "identity",
            "password", "passwd", "pwd",
            "credit_card", "card_number",
            "api_key", "apikey", "token",
            "secret", "private_key"
        }
        
        if field_name.lower() in sensitive_fields:
            return self.mask(str(value))
        
        return value


# 全局单例
_data_masker_instance: Optional[DataMasker] = None
_data_masker_lock = threading.RLock()


def get_data_masker() -> DataMasker:
    """获取数据脱敏器全局实例"""
    global _data_masker_instance
    if _data_masker_instance is None:
        with _data_masker_lock:
            if _data_masker_instance is None:
                _data_masker_instance = DataMasker()
    return _data_masker_instance
