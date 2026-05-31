"""
安全验证器模块 - 阶段380 (Phase 35)

功能：
- 密码强度验证
- 输入安全验证
- SQL注入检测
- XSS攻击检测
- 路径遍历检测
- 命令注入检测
- 输入净化处理

设计原则：
- 第一性原理：确定性规则，无模型依赖
- 线程安全：使用 threading.RLock
- 全局单例：通过 get_security_validator() 获取，双重检查锁定
- 使用 Python dataclasses 定义数据结构，Enum 定义类型
- 最小依赖，无循环依赖
"""

import threading
import time
import re
import html
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Callable, Any, Set


class ValidationRule(Enum):
    """验证规则枚举"""
    PASSWORD_STRENGTH = "password_strength"
    INPUT_SANITIZATION = "input_sanitization"
    SQL_INJECTION = "sql_injection"
    XSS = "xss"
    PATH_TRAVERSAL = "path_traversal"
    COMMAND_INJECTION = "command_injection"


class ValidationSeverity(Enum):
    """验证严重程度枚举"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ValidationResult:
    """
    验证结果
    
    包含单次验证的详细结果
    """
    is_valid: bool
    rule: ValidationRule
    severity: ValidationSeverity
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class ValidationReport:
    """
    验证报告
    
    包含所有验证的综合结果
    """
    is_valid: bool
    results: List[ValidationResult] = field(default_factory=list)
    total_issues: int = 0
    critical_issues: int = 0
    timestamp: float = field(default_factory=time.time)


class SecurityValidator:
    """
    安全验证器
    
    实现多种安全验证规则，检测潜在的安全威胁
    
    功能：
    - 密码强度验证：检查长度、大小写、数字、特殊字符
    - SQL注入检测：检测SQL关键字和模式
    - XSS检测：检测脚本注入和事件处理器
    - 路径遍历检测：检测目录遍历尝试
    - 命令注入检测：检测命令执行模式
    - 输入净化：移除/转义危险字符
    
    特性：
    - 线程安全：所有操作使用 RLock 保护
    - 可扩展：支持自定义验证规则
    - 确定性：纯规则驱动，无模型依赖
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
            
            # 内置验证规则
            self._rules: Dict[ValidationRule, Callable[[str], ValidationResult]] = {}
            
            # 自定义验证规则
            self._custom_rules: Dict[str, Callable[[str], ValidationResult]] = {}
            
            # 统计信息
            self._stats = {
                "total_validations": 0,
                "failed_validations": 0,
                "sql_injection_detections": 0,
                "xss_detections": 0,
                "path_traversal_detections": 0,
                "command_injection_detections": 0,
                "password_validations": 0,
                "input_sanitizations": 0,
            }
            
            # 初始化内置规则
            self._init_builtin_rules()
            
            # 初始化检测模式
            self._init_patterns()
    
    def _init_builtin_rules(self) -> None:
        """初始化内置验证规则"""
        self._rules[ValidationRule.PASSWORD_STRENGTH] = self._validate_password_rule
        self._rules[ValidationRule.SQL_INJECTION] = self._check_sql_injection_rule
        self._rules[ValidationRule.XSS] = self._check_xss_rule
        self._rules[ValidationRule.PATH_TRAVERSAL] = self._check_path_traversal_rule
        self._rules[ValidationRule.COMMAND_INJECTION] = self._check_command_injection_rule
        self._rules[ValidationRule.INPUT_SANITIZATION] = self._validate_input_rule
    
    def _init_patterns(self) -> None:
        """初始化检测模式"""
        # SQL注入模式
        self._sql_patterns = [
            # SQL关键字
            r'\bSELECT\b',
            r'\bINSERT\b',
            r'\bUPDATE\b',
            r'\bDELETE\b',
            r'\bDROP\b',
            r'\bUNION\b',
            r'\bALTER\b',
            r'\bCREATE\b',
            r'\bTRUNCATE\b',
            r'\bEXEC\b',
            r'\bEXECUTE\b',
            r'\bDECLARE\b',
            # SQL注释
            r'--',
            r'/\*.*\*/',
            # SQL特殊字符
            r';.*--',
            r"'.*OR.*'",
            r"'.*AND.*'",
            # 函数调用
            r'\bCHAR\s*\(',
            r'\bCONCAT\s*\(',
            r'\bSUBSTRING\s*\(',
            r'\bLOAD_FILE\s*\(',
            r'\bBENCHMARK\s*\(',
            r'\bSLEEP\s*\(',
            r'\bWAITFOR\s+DELAY\b',
        ]
        
        # XSS模式
        self._xss_patterns = [
            # 脚本标签
            r'<script[^>]*>.*?</script>',
            r'<script[^>]*>',
            # JavaScript协议
            r'javascript\s*:',
            r'vbscript\s*:',
            r'data\s*:',
            # 事件处理器
            r'\bonerror\s*=',
            r'\bonload\s*=',
            r'\bonclick\s*=',
            r'\bonmouseover\s*=',
            r'\bonfocus\s*=',
            r'\bonblur\s*=',
            r'\bonsubmit\s*=',
            r'\bonchange\s*=',
            r'\bonkeyup\s*=',
            r'\bonkeydown\s*=',
            # 表达式
            r'eval\s*\(',
            r'expression\s*\(',
            r'document\.',
            r'window\.',
            r'alert\s*\(',
            r'prompt\s*\(',
            r'confirm\s*\(',
            # HTML注入
            r'<iframe[^>]*>',
            r'<object[^>]*>',
            r'<embed[^>]*>',
            r'<form[^>]*>',
        ]
        
        # 路径遍历模式
        self._path_traversal_patterns = [
            r'\.\./',
            r'\.\.\\',
            r'%2e%2e%2f',
            r'%2e%2e/',
            r'\.\.%2f',
            r'%2e%2e\\',
            r'/etc/',
            r'/passwd',
            r'/shadow',
            r'\\windows\\',
            r'\\system32\\',
            r'/proc/',
            r'/dev/',
            r'/var/log/',
        ]
        
        # 命令注入模式
        self._command_injection_patterns = [
            r'\|.*\|',           # 管道链
            r'&&',
            r'\|\|',
            r';.*;',             # 命令分隔
            r'\$\([^)]*\)',      # 命令替换 $()
            r'`[^`]*`',          # 反引号命令替换
            r'\n',               # 换行符
            r'\r',               # 回车符
            r'\bcat\s+',         # cat命令
            r'\bls\s+',          # ls命令
            r'\brm\s+',          # rm命令
            r'\bchmod\s+',       # chmod命令
            r'\bwget\s+',        # wget命令
            r'\bcurl\s+',        # curl命令
            r'\bnc\s+',          # nc命令
            r'\bsh\s+',          # sh命令
            r'\bbash\s+',        # bash命令
            r'\bpython\s+',      # python命令
            r'\bperl\s+',        # perl命令
            r'\bruby\s+',        # ruby命令
            r'>\s*/',            # 重定向到根目录
            r'>>\s*/',           # 追加重定向到根目录
        ]
        
        # 编译正则表达式（忽略大小写）
        self._compiled_sql = [re.compile(p, re.IGNORECASE) for p in self._sql_patterns]
        self._compiled_xss = [re.compile(p, re.IGNORECASE) for p in self._xss_patterns]
        self._compiled_path = [re.compile(p, re.IGNORECASE) for p in self._path_traversal_patterns]
        self._compiled_cmd = [re.compile(p, re.IGNORECASE) for p in self._command_injection_patterns]
    
    # ========== 密码强度验证 ==========
    
    def validate_password(self, password: str) -> ValidationResult:
        """
        验证密码强度
        
        检查规则：
        - 长度 >= 8
        - 包含大写字母
        - 包含小写字母
        - 包含数字
        - 包含特殊字符
        
        Args:
            password: 待验证的密码
            
        Returns:
            ValidationResult: 验证结果
        """
        with self._lock:
            self._stats["total_validations"] += 1
            self._stats["password_validations"] += 1
            
            result = self._validate_password_rule(password)
            
            if not result.is_valid:
                self._stats["failed_validations"] += 1
            
            return result
    
    def _validate_password_rule(self, password: str) -> ValidationResult:
        """密码强度验证规则实现"""
        details: Dict[str, Any] = {
            "length": len(password),
            "has_upper": False,
            "has_lower": False,
            "has_digit": False,
            "has_special": False,
        }
        
        issues: List[str] = []
        
        # 检查长度
        if len(password) < 8:
            issues.append("密码长度不足8个字符")
        else:
            details["length_ok"] = True
        
        # 检查大写字母
        if re.search(r'[A-Z]', password):
            details["has_upper"] = True
        else:
            issues.append("密码缺少大写字母")
        
        # 检查小写字母
        if re.search(r'[a-z]', password):
            details["has_lower"] = True
        else:
            issues.append("密码缺少小写字母")
        
        # 检查数字
        if re.search(r'\d', password):
            details["has_digit"] = True
        else:
            issues.append("密码缺少数字")
        
        # 检查特殊字符
        if re.search(r'[!@#$%^&*()_+\-=\[\]{};:\'",.<>/?\\|`~]', password):
            details["has_special"] = True
        else:
            issues.append("密码缺少特殊字符")
        
        is_valid = len(issues) == 0
        
        # 计算强度分数
        strength_score = sum([
            details["has_upper"],
            details["has_lower"],
            details["has_digit"],
            details["has_special"],
            len(password) >= 8,
            len(password) >= 12,  # 额外加分
        ])
        details["strength_score"] = strength_score
        
        # 确定严重程度
        if is_valid:
            severity = ValidationSeverity.LOW
        elif len(issues) >= 3:
            severity = ValidationSeverity.CRITICAL
        elif len(issues) >= 2:
            severity = ValidationSeverity.HIGH
        else:
            severity = ValidationSeverity.MEDIUM
        
        return ValidationResult(
            is_valid=is_valid,
            rule=ValidationRule.PASSWORD_STRENGTH,
            severity=severity,
            message="密码强度验证" + ("通过" if is_valid else "失败"),
            details={
                **details,
                "issues": issues,
                "strength_score": strength_score,
            }
        )
    
    # ========== 输入验证 ==========
    
    def validate_input(self, input_str: str, context: str = "general") -> ValidationResult:
        """
        验证输入安全性
        
        检查输入是否包含潜在的危险模式
        
        Args:
            input_str: 待验证的输入字符串
            context: 上下文类型 (general, sql, html, path, command)
            
        Returns:
            ValidationResult: 验证结果
        """
        with self._lock:
            self._stats["total_validations"] += 1
            
            issues: List[str] = []
            details: Dict[str, Any] = {
                "context": context,
                "input_length": len(input_str),
            }
            
            # 根据上下文选择检测规则
            if context in ("general", "sql"):
                sql_result = self.check_sql_injection(input_str)
                if not sql_result.is_valid:
                    issues.append(f"SQL注入风险: {sql_result.message}")
                    details["sql_injection"] = sql_result.details
            
            if context in ("general", "html"):
                xss_result = self.check_xss(input_str)
                if not xss_result.is_valid:
                    issues.append(f"XSS风险: {xss_result.message}")
                    details["xss"] = xss_result.details
            
            if context in ("general", "path"):
                path_result = self.check_path_traversal(input_str)
                if not path_result.is_valid:
                    issues.append(f"路径遍历风险: {path_result.message}")
                    details["path_traversal"] = path_result.details
            
            if context in ("general", "command"):
                cmd_result = self.check_command_injection(input_str)
                if not cmd_result.is_valid:
                    issues.append(f"命令注入风险: {cmd_result.message}")
                    details["command_injection"] = cmd_result.details
            
            is_valid = len(issues) == 0
            
            if not is_valid:
                self._stats["failed_validations"] += 1
            
            # 确定严重程度
            if is_valid:
                severity = ValidationSeverity.LOW
            elif len(issues) >= 3:
                severity = ValidationSeverity.CRITICAL
            elif len(issues) >= 2:
                severity = ValidationSeverity.HIGH
            else:
                severity = ValidationSeverity.MEDIUM
            
            return ValidationResult(
                is_valid=is_valid,
                rule=ValidationRule.INPUT_SANITIZATION,
                severity=severity,
                message="输入验证" + ("通过" if is_valid else "失败"),
                details={
                    **details,
                    "issues": issues,
                }
            )
    
    def _validate_input_rule(self, input_str: str) -> ValidationResult:
        """输入验证规则实现"""
        return self.validate_input(input_str, "general")
    
    # ========== SQL注入检测 ==========
    
    def check_sql_injection(self, input_str: str) -> ValidationResult:
        """
        检测SQL注入
        
        检测模式：
        - SQL关键字: SELECT, INSERT, UPDATE, DELETE, DROP, UNION
        - SQL注释: --, /* */
        - SQL特殊字符: ;, ', "
        
        Args:
            input_str: 待检测的输入字符串
            
        Returns:
            ValidationResult: 检测结果
        """
        with self._lock:
            self._stats["total_validations"] += 1
            
            result = self._check_sql_injection_rule(input_str)
            
            if not result.is_valid:
                self._stats["failed_validations"] += 1
                self._stats["sql_injection_detections"] += 1
            
            return result
    
    def _check_sql_injection_rule(self, input_str: str) -> ValidationResult:
        """SQL注入检测规则实现"""
        detected_patterns: List[str] = []
        details: Dict[str, Any] = {
            "input_length": len(input_str),
            "detected_patterns": [],
        }
        
        for i, pattern in enumerate(self._compiled_sql):
            matches = pattern.findall(input_str)
            if matches:
                detected_patterns.append(self._sql_patterns[i])
                details[f"match_{i}"] = matches
        
        is_valid = len(detected_patterns) == 0
        details["detected_patterns"] = detected_patterns
        details["pattern_count"] = len(detected_patterns)
        
        # 确定严重程度
        if is_valid:
            severity = ValidationSeverity.LOW
        elif len(detected_patterns) >= 3:
            severity = ValidationSeverity.CRITICAL
        elif len(detected_patterns) >= 2:
            severity = ValidationSeverity.HIGH
        else:
            severity = ValidationSeverity.MEDIUM
        
        return ValidationResult(
            is_valid=is_valid,
            rule=ValidationRule.SQL_INJECTION,
            severity=severity,
            message="SQL注入检测" + ("通过" if is_valid else f"发现{len(detected_patterns)}个可疑模式"),
            details=details
        )
    
    # ========== XSS检测 ==========
    
    def check_xss(self, input_str: str) -> ValidationResult:
        """
        检测XSS攻击
        
        检测模式：
        - 脚本标签: <script>
        - JavaScript协议: javascript:
        - 事件处理器: onerror, onload, onclick
        - 危险函数: eval(), document.
        
        Args:
            input_str: 待检测的输入字符串
            
        Returns:
            ValidationResult: 检测结果
        """
        with self._lock:
            self._stats["total_validations"] += 1
            
            result = self._check_xss_rule(input_str)
            
            if not result.is_valid:
                self._stats["failed_validations"] += 1
                self._stats["xss_detections"] += 1
            
            return result
    
    def _check_xss_rule(self, input_str: str) -> ValidationResult:
        """XSS检测规则实现"""
        detected_patterns: List[str] = []
        details: Dict[str, Any] = {
            "input_length": len(input_str),
            "detected_patterns": [],
        }
        
        for i, pattern in enumerate(self._compiled_xss):
            matches = pattern.findall(input_str)
            if matches:
                detected_patterns.append(self._xss_patterns[i])
                details[f"match_{i}"] = matches
        
        is_valid = len(detected_patterns) == 0
        details["detected_patterns"] = detected_patterns
        details["pattern_count"] = len(detected_patterns)
        
        # 确定严重程度
        if is_valid:
            severity = ValidationSeverity.LOW
        elif len(detected_patterns) >= 3:
            severity = ValidationSeverity.CRITICAL
        elif len(detected_patterns) >= 2:
            severity = ValidationSeverity.HIGH
        else:
            severity = ValidationSeverity.MEDIUM
        
        return ValidationResult(
            is_valid=is_valid,
            rule=ValidationRule.XSS,
            severity=severity,
            message="XSS检测" + ("通过" if is_valid else f"发现{len(detected_patterns)}个可疑模式"),
            details=details
        )
    
    # ========== 路径遍历检测 ==========
    
    def check_path_traversal(self, input_str: str) -> ValidationResult:
        """
        检测路径遍历攻击
        
        检测模式：
        - 目录遍历: ../, ..\
        - URL编码遍历: %2e%2e%2f
        - 敏感路径: /etc/, \windows\
        
        Args:
            input_str: 待检测的输入字符串
            
        Returns:
            ValidationResult: 检测结果
        """
        with self._lock:
            self._stats["total_validations"] += 1
            
            result = self._check_path_traversal_rule(input_str)
            
            if not result.is_valid:
                self._stats["failed_validations"] += 1
                self._stats["path_traversal_detections"] += 1
            
            return result
    
    def _check_path_traversal_rule(self, input_str: str) -> ValidationResult:
        """路径遍历检测规则实现"""
        detected_patterns: List[str] = []
        details: Dict[str, Any] = {
            "input_length": len(input_str),
            "detected_patterns": [],
        }
        
        for i, pattern in enumerate(self._compiled_path):
            matches = pattern.findall(input_str)
            if matches:
                detected_patterns.append(self._path_traversal_patterns[i])
                details[f"match_{i}"] = matches
        
        is_valid = len(detected_patterns) == 0
        details["detected_patterns"] = detected_patterns
        details["pattern_count"] = len(detected_patterns)
        
        # 确定严重程度
        if is_valid:
            severity = ValidationSeverity.LOW
        elif len(detected_patterns) >= 2:
            severity = ValidationSeverity.CRITICAL
        else:
            severity = ValidationSeverity.HIGH  # 路径遍历本身就是高风险
        
        return ValidationResult(
            is_valid=is_valid,
            rule=ValidationRule.PATH_TRAVERSAL,
            severity=severity,
            message="路径遍历检测" + ("通过" if is_valid else f"发现{len(detected_patterns)}个可疑模式"),
            details=details
        )
    
    # ========== 命令注入检测 ==========
    
    def check_command_injection(self, input_str: str) -> ValidationResult:
        """
        检测命令注入攻击
        
        检测模式：
        - 命令链: |, &&, ||
        - 命令分隔: ;
        - 命令替换: $(), ``
        - 换行符: \n, \r
        
        Args:
            input_str: 待检测的输入字符串
            
        Returns:
            ValidationResult: 检测结果
        """
        with self._lock:
            self._stats["total_validations"] += 1
            
            result = self._check_command_injection_rule(input_str)
            
            if not result.is_valid:
                self._stats["failed_validations"] += 1
                self._stats["command_injection_detections"] += 1
            
            return result
    
    def _check_command_injection_rule(self, input_str: str) -> ValidationResult:
        """命令注入检测规则实现"""
        detected_patterns: List[str] = []
        details: Dict[str, Any] = {
            "input_length": len(input_str),
            "detected_patterns": [],
        }
        
        for i, pattern in enumerate(self._compiled_cmd):
            matches = pattern.findall(input_str)
            if matches:
                detected_patterns.append(self._command_injection_patterns[i])
                details[f"match_{i}"] = matches
        
        is_valid = len(detected_patterns) == 0
        details["detected_patterns"] = detected_patterns
        details["pattern_count"] = len(detected_patterns)
        
        # 确定严重程度
        if is_valid:
            severity = ValidationSeverity.LOW
        elif len(detected_patterns) >= 2:
            severity = ValidationSeverity.CRITICAL
        else:
            severity = ValidationSeverity.CRITICAL  # 命令注入本身就是严重威胁
        
        return ValidationResult(
            is_valid=is_valid,
            rule=ValidationRule.COMMAND_INJECTION,
            severity=severity,
            message="命令注入检测" + ("通过" if is_valid else f"发现{len(detected_patterns)}个可疑模式"),
            details=details
        )
    
    # ========== 输入净化 ==========
    
    def sanitize_input(self, input_str: str) -> str:
        """
        净化输入字符串
        
        处理方式：
        - HTML转义: < > & " '
        - 移除危险字符: | ; $ ` \n \r
        - 移除SQL注释: -- /* */
        
        Args:
            input_str: 待净化的输入字符串
            
        Returns:
            str: 净化后的字符串
        """
        with self._lock:
            self._stats["input_sanitizations"] += 1
            
            result = input_str
            
            # HTML转义
            result = html.escape(result, quote=True)
            
            # 移除危险字符
            dangerous_chars = {
                '|': '&#124;',
                ';': '&#59;',
                '$': '&#36;',
                '`': '&#96;',
                '\n': ' ',
                '\r': ' ',
                '\t': ' ',
            }
            
            for char, replacement in dangerous_chars.items():
                result = result.replace(char, replacement)
            
            # 移除SQL注释模式
            result = re.sub(r'--', '', result)
            result = re.sub(r'/\*.*?\*/', '', result, flags=re.DOTALL)
            
            # 移除潜在的脚本标签
            result = re.sub(r'<script[^>]*>.*?</script>', '', result, flags=re.IGNORECASE | re.DOTALL)
            result = re.sub(r'<script[^>]*>', '', result, flags=re.IGNORECASE)
            result = re.sub(r'</script>', '', result, flags=re.IGNORECASE)
            
            # 移除事件处理器
            result = re.sub(r'\bon\w+\s*=', '', result, flags=re.IGNORECASE)
            
            # 移除javascript:协议
            result = re.sub(r'javascript\s*:', '', result, flags=re.IGNORECASE)
            
            return result
    
    # ========== 综合验证 ==========
    
    def validate_all(self, input_str: str) -> ValidationReport:
        """
        执行所有安全验证
        
        运行所有内置验证规则并生成综合报告
        
        Args:
            input_str: 待验证的输入字符串
            
        Returns:
            ValidationReport: 综合验证报告
        """
        with self._lock:
            results: List[ValidationResult] = []
            
            # 执行所有内置验证
            results.append(self.check_sql_injection(input_str))
            results.append(self.check_xss(input_str))
            results.append(self.check_path_traversal(input_str))
            results.append(self.check_command_injection(input_str))
            
            # 执行自定义验证
            for rule_name, validator in self._custom_rules.items():
                try:
                    custom_result = validator(input_str)
                    results.append(custom_result)
                except Exception as e:
                    results.append(ValidationResult(
                        is_valid=False,
                        rule=ValidationRule.INPUT_SANITIZATION,
                        severity=ValidationSeverity.HIGH,
                        message=f"自定义规则 '{rule_name}' 执行失败: {str(e)}",
                        details={"error": str(e), "rule_name": rule_name}
                    ))
            
            # 计算统计信息
            total_issues = sum(1 for r in results if not r.is_valid)
            critical_issues = sum(1 for r in results if not r.is_valid and r.severity == ValidationSeverity.CRITICAL)
            
            is_valid = total_issues == 0
            
            return ValidationReport(
                is_valid=is_valid,
                results=results,
                total_issues=total_issues,
                critical_issues=critical_issues,
                timestamp=time.time()
            )
    
    # ========== 自定义规则管理 ==========
    
    def add_custom_rule(self, rule_name: str, validator_func: Callable[[str], ValidationResult]) -> bool:
        """
        添加自定义验证规则
        
        Args:
            rule_name: 规则名称
            validator_func: 验证函数，接受字符串输入，返回ValidationResult
            
        Returns:
            bool: 添加成功返回True，规则已存在返回False
        """
        with self._lock:
            if rule_name in self._custom_rules:
                return False
            
            if not callable(validator_func):
                return False
            
            self._custom_rules[rule_name] = validator_func
            return True
    
    def remove_custom_rule(self, rule_name: str) -> bool:
        """
        移除自定义验证规则
        
        Args:
            rule_name: 规则名称
            
        Returns:
            bool: 移除成功返回True，规则不存在返回False
        """
        with self._lock:
            if rule_name not in self._custom_rules:
                return False
            
            del self._custom_rules[rule_name]
            return True
    
    def get_rules(self) -> List[str]:
        """
        获取所有验证规则名称
        
        Returns:
            List[str]: 规则名称列表
        """
        with self._lock:
            builtin_rules = [rule.value for rule in ValidationRule]
            custom_rules = list(self._custom_rules.keys())
            return builtin_rules + custom_rules
    
    # ========== 统计信息 ==========
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取验证统计信息
        
        Returns:
            Dict: 统计信息字典
        """
        with self._lock:
            return {
                **self._stats,
                "custom_rules_count": len(self._custom_rules),
                "builtin_rules_count": len(self._rules),
            }
    
    def reset_statistics(self) -> None:
        """重置统计信息"""
        with self._lock:
            self._stats = {
                "total_validations": 0,
                "failed_validations": 0,
                "sql_injection_detections": 0,
                "xss_detections": 0,
                "path_traversal_detections": 0,
                "command_injection_detections": 0,
                "password_validations": 0,
                "input_sanitizations": 0,
            }
    
    # ========== 辅助方法 ==========
    
    def is_safe(self, input_str: str) -> bool:
        """
        快速检查输入是否安全
        
        Args:
            input_str: 待检查的输入字符串
            
        Returns:
            bool: 安全返回True，否则返回False
        """
        report = self.validate_all(input_str)
        return report.is_valid
    
    def get_severity_level(self, severity: ValidationSeverity) -> int:
        """
        获取严重程度级别数值
        
        Args:
            severity: 严重程度枚举
            
        Returns:
            int: 级别数值（1-4）
        """
        levels = {
            ValidationSeverity.LOW: 1,
            ValidationSeverity.MEDIUM: 2,
            ValidationSeverity.HIGH: 3,
            ValidationSeverity.CRITICAL: 4,
        }
        return levels.get(severity, 0)
    
    def get_max_severity(self, results: List[ValidationResult]) -> Optional[ValidationSeverity]:
        """
        从结果列表中获取最高严重程度
        
        Args:
            results: 验证结果列表
            
        Returns:
            Optional[ValidationSeverity]: 最高严重程度，空列表返回None
        """
        if not results:
            return None
        
        max_level = 0
        max_severity = ValidationSeverity.LOW
        
        for result in results:
            level = self.get_severity_level(result.severity)
            if level > max_level:
                max_level = level
                max_severity = result.severity
        
        return max_severity


# ========== 全局单例 ==========

_security_validator_instance: Optional[SecurityValidator] = None
_security_validator_lock = threading.RLock()


def get_security_validator() -> SecurityValidator:
    """
    获取安全验证器全局实例（双重检查锁定）
    
    Returns:
        SecurityValidator: 单例实例
    """
    global _security_validator_instance
    if _security_validator_instance is None:
        with _security_validator_lock:
            if _security_validator_instance is None:
                _security_validator_instance = SecurityValidator()
    return _security_validator_instance


def reset_security_validator() -> None:
    """
    重置安全验证器全局实例（用于测试）
    """
    global _security_validator_instance
    with _security_validator_lock:
        _security_validator_instance = None
