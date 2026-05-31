#!/usr/bin/env python3
"""
边界条件测试模块 - 阶段84-86
测试系统在极端输入和边界条件下的表现
"""

import sys
import os
import time
from typing import Dict, List, Any
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.preprocessing.filter import Preprocessor
from src.memory.router import MemoryRouter
from src.recall.engine import RecallEngine
from src.governance.governor import MemoryGovernor
from src.governance.version_manager import VersionManager
from src.governance.privacy_isolation import PrivacyIsolationManager


class BoundaryTester:
    """边界条件测试器"""
    
    def __init__(self):
        self.results: List[Dict[str, Any]] = []
        self.passed = 0
        self.failed = 0
    
    def run_all_tests(self) -> Dict[str, Any]:
        """运行所有边界测试"""
        print("=" * 60)
        print("Agent可靠记忆系统 - 边界条件测试")
        print("=" * 60)
        
        # 空值和None测试
        self._test_empty_inputs()
        
        # 超长内容测试
        self._test_very_long_content()
        
        # 特殊字符测试
        self._test_special_characters()
        
        # 极限数值测试
        self._test_extreme_numbers()
        
        # 并发边界测试
        self._test_concurrent_boundaries()
        
        # 隐私边界测试
        self._test_privacy_boundaries()
        
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
        
        print(f"  [{status}] {test_name}: {message}")
    
    def _test_empty_inputs(self):
        """测试空值输入"""
        print("\n[开始] 空值输入测试")
        
        preprocessor = Preprocessor()
        router = MemoryRouter()
        
        # 测试空字符串
        try:
            result = preprocessor.process("", "test_task")
            self._record_result("空字符串预处理", result["is_valid"] == False, 
                              f"is_valid={result['is_valid']}")
        except Exception as e:
            self._record_result("空字符串预处理", False, f"异常: {e}")
        
        # 测试None输入（应该被捕获）
        try:
            result = preprocessor.process("test content", None)
            self._record_result("None任务ID", True, "正常处理")
        except Exception as e:
            self._record_result("None任务ID", False, f"异常: {e}")
        
        # 测试仅空白字符
        try:
            result = preprocessor.process("   \t\n  ", "test_task")
            self._record_result("仅空白字符", result["is_valid"] == False,
                              f"is_valid={result['is_valid']}")
        except Exception as e:
            self._record_result("仅空白字符", False, f"异常: {e}")
    
    def _test_very_long_content(self):
        """测试超长内容"""
        print("\n[开始] 超长内容测试")
        
        preprocessor = Preprocessor()
        router = MemoryRouter()
        
        # 测试1KB内容
        try:
            content = "A" * 1024
            result = preprocessor.process(content, "test_task")
            self._record_result("1KB内容", result["is_valid"], 
                              f"长度={len(content)}, is_valid={result['is_valid']}")
        except Exception as e:
            self._record_result("1KB内容", False, f"异常: {e}")
        
        # 测试10KB内容
        try:
            content = "B" * 10240
            result = preprocessor.process(content, "test_task")
            self._record_result("10KB内容", result["is_valid"],
                              f"长度={len(content)}, is_valid={result['is_valid']}")
        except Exception as e:
            self._record_result("10KB内容", False, f"异常: {e}")
        
        # 测试100KB内容
        try:
            content = "C" * 102400
            start = time.time()
            result = preprocessor.process(content, "test_task")
            elapsed = time.time() - start
            self._record_result("100KB内容", elapsed < 5.0,
                              f"长度={len(content)}, 耗时={elapsed:.2f}s")
        except Exception as e:
            self._record_result("100KB内容", False, f"异常: {e}")
    
    def _test_special_characters(self):
        """测试特殊字符"""
        print("\n[开始] 特殊字符测试")
        
        preprocessor = Preprocessor()
        
        # 测试Unicode字符
        try:
            content = "中文测试🎉🚀ñöü"
            result = preprocessor.process(content, "test_task")
            self._record_result("Unicode字符", result["is_valid"],
                              "支持多语言和emoji")
        except Exception as e:
            self._record_result("Unicode字符", False, f"异常: {e}")
        
        # 测试HTML标签
        try:
            content = "<script>alert('xss')</script>"
            result = preprocessor.process(content, "test_task")
            self._record_result("HTML标签", result["is_valid"],
                              "HTML标签被正确处理")
        except Exception as e:
            self._record_result("HTML标签", False, f"异常: {e}")
        
        # 测试SQL注入尝试
        try:
            content = "'; DROP TABLE memories; --"
            result = preprocessor.process(content, "test_task")
            self._record_result("SQL注入尝试", result["is_valid"],
                              "潜在SQL注入被处理")
        except Exception as e:
            self._record_result("SQL注入尝试", False, f"异常: {e}")
        
        # 测试控制字符
        try:
            content = "test\x00\x01\x02content"
            result = preprocessor.process(content, "test_task")
            self._record_result("控制字符", True,
                              "控制字符被过滤或接受")
        except Exception as e:
            self._record_result("控制字符", False, f"异常: {e}")
    
    def _test_extreme_numbers(self):
        """测试极限数值"""
        print("\n[开始] 极限数值测试")
        
        recall_engine = RecallEngine()
        
        # 测试top_k=0
        try:
            results = recall_engine.recall("测试", "test_task", top_k=0)
            self._record_result("top_k=0", len(results) == 0,
                              f"返回{len(results)}条结果")
        except Exception as e:
            self._record_result("top_k=0", False, f"异常: {e}")
        
        # 测试超大top_k
        try:
            results = recall_engine.recall("测试", "test_task", top_k=10000)
            self._record_result("top_k=10000", True,
                              f"返回{len(results)}条结果")
        except Exception as e:
            self._record_result("top_k=10000", False, f"异常: {e}")
        
        # 测试负数top_k
        try:
            results = recall_engine.recall("测试", "test_task", top_k=-1)
            self._record_result("top_k=-1", False,
                              "应该拒绝负数")
        except Exception as e:
            self._record_result("top_k=-1", True, f"正确拒绝: {e}")
    
    def _test_concurrent_boundaries(self):
        """测试并发边界"""
        print("\n[开始] 并发边界测试")
        
        import threading
        
        privacy_manager = PrivacyIsolationManager()
        
        # 测试同一内存ID并发注册
        errors = []
        
        def register_task():
            try:
                privacy_manager.register_memory(
                    "concurrent_mem_001",
                    "user_001",
                    "public"
                )
            except Exception as e:
                errors.append(str(e))
        
        threads = []
        for i in range(10):
            t = threading.Thread(target=register_task)
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        self._record_result("并发注册同一内存", len(errors) == 0,
                          f"{len(errors)}个错误")
        
        # 测试大量并发访问检查
        try:
            check_count = 1000
            start = time.time()
            for i in range(check_count):
                privacy_manager.can_access("concurrent_mem_001", f"user_{i}")
            elapsed = time.time() - start
            self._record_result("大量访问检查", elapsed < 1.0,
                              f"{check_count}次检查耗时{elapsed:.3f}s")
        except Exception as e:
            self._record_result("大量访问检查", False, f"异常: {e}")
    
    def _test_privacy_boundaries(self):
        """测试隐私边界"""
        print("\n[开始] 隐私边界测试")
        
        privacy_manager = PrivacyIsolationManager()
        
        # 测试空allowed_users列表
        try:
            privacy_manager.register_memory(
                "test_mem_001",
                "owner_001",
                "shared",
                allowed_users=[]
            )
            can_access = privacy_manager.can_access("test_mem_001", "other_user")
            self._record_result("空共享列表", not can_access,
                              "空列表时其他用户无法访问")
        except Exception as e:
            self._record_result("空共享列表", False, f"异常: {e}")
        
        # 测试超大allowed_users列表
        try:
            large_list = [f"user_{i}" for i in range(1000)]
            privacy_manager.register_memory(
                "test_mem_002",
                "owner_002",
                "shared",
                allowed_users=large_list
            )
            can_access = privacy_manager.can_access("test_mem_002", "user_500")
            self._record_result("大共享列表(1000)", can_access,
                              "大列表性能可接受")
        except Exception as e:
            self._record_result("大共享列表(1000)", False, f"异常: {e}")
        
        # 测试访问不存在的内存
        try:
            can_access = privacy_manager.can_access("non_existent_mem", "user_001")
            self._record_result("访问不存在内存", not can_access,
                              "返回False而非异常")
        except Exception as e:
            self._record_result("访问不存在内存", False, f"异常: {e}")
    
    def _generate_report(self) -> Dict[str, Any]:
        """生成测试报告"""
        total = self.passed + self.failed
        pass_rate = (self.passed / total * 100) if total > 0 else 0
        
        print("\n" + "=" * 60)
        print("边界条件测试报告")
        print("=" * 60)
        print(f"总测试数: {total}")
        print(f"通过: {self.passed}")
        print(f"失败: {self.failed}")
        print(f"通过率: {pass_rate:.1f}%")
        
        # 边界条件评估
        if pass_rate >= 95:
            assessment = "优秀 - 系统对边界条件处理良好"
        elif pass_rate >= 80:
            assessment = "良好 - 大部分边界条件已处理"
        elif pass_rate >= 60:
            assessment = "一般 - 需要改进边界条件处理"
        else:
            assessment = "需改进 - 边界条件处理存在严重问题"
        
        print(f"\n评估: {assessment}")
        print("=" * 60)
        
        return {
            "total": total,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": f"{pass_rate:.1f}%",
            "assessment": assessment,
            "results": self.results,
            "timestamp": datetime.now().isoformat()
        }


if __name__ == "__main__":
    tester = BoundaryTester()
    report = tester.run_all_tests()
    
    # 返回退出码
    sys.exit(0 if report["failed"] == 0 else 1)
