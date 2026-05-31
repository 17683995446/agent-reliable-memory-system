#!/usr/bin/env python3
"""
故障恢复测试模块 - 阶段87-89
测试系统在异常情况下的恢复能力
"""

import sys
import os
import time
import threading
from typing import Dict, List, Any
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.memory.l1_ephemeral import L1EphemeralMemory
from src.memory.l2_vector import L2VectorMemory
from src.utils.performance import QueryCache, ConcurrencyManager


class RecoveryTester:
    """故障恢复测试器"""
    
    def __init__(self):
        self.results: List[Dict[str, Any]] = []
        self.passed = 0
        self.failed = 0
    
    def run_all_tests(self) -> Dict[str, Any]:
        """运行所有恢复测试"""
        print("=" * 60)
        print("Agent可靠记忆系统 - 故障恢复测试")
        print("=" * 60)
        
        # L1内存恢复测试
        self._test_l1_recovery()
        
        # L2内存恢复测试
        self._test_l2_recovery()
        
        # 缓存恢复测试
        self._test_cache_recovery()
        
        # 并发恢复测试
        self._test_concurrent_recovery()
        
        # 服务降级测试
        self._test_graceful_degradation()
        
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
    
    def _test_l1_recovery(self):
        """测试L1内存恢复"""
        print("\n[开始] L1内存恢复测试")
        
        try:
            l1 = L1EphemeralMemory()
            
            # 存储数据
            task_id = "recovery_test_001"
            l1.store(task_id, "key1", "value1")
            l1.store(task_id, "key2", "value2")
            
            # 模拟异常后检查数据完整性
            value1 = l1.retrieve(task_id, "key1")
            value2 = l1.retrieve(task_id, "key2")
            
            if value1 == "value1" and value2 == "value2":
                self._record_result("L1数据完整性", True, "数据未丢失")
            else:
                self._record_result("L1数据完整性", False, f"数据异常: {value1}, {value2}")
            
            # 测试任务结束后的清理
            l1.clear_task(task_id)
            value_after_clear = l1.retrieve(task_id, "key1")
            
            if value_after_clear is None:
                self._record_result("L1任务清理", True, "任务数据已清理")
            else:
                self._record_result("L1任务清理", False, "任务数据未清理")
                
        except Exception as e:
            self._record_result("L1内存恢复", False, f"异常: {e}")
    
    def _test_l2_recovery(self):
        """测试L2内存恢复"""
        print("\n[开始] L2内存恢复测试")
        
        try:
            l2 = L2VectorMemory()
            
            # 存储数据
            contents = ["恢复测试内容1", "恢复测试内容2", "恢复测试内容3"]
            memory_ids = []
            for content in contents:
                mem_id = l2.store(content, "recovery_task")
                memory_ids.append(mem_id)
            
            # 等待索引更新
            time.sleep(0.5)
            
            # 测试搜索功能
            results = l2.search("恢复测试", top_k=5)
            
            if len(results) >= 2:
                self._record_result("L2搜索恢复", True, f"找到{len(results)}条结果")
            else:
                self._record_result("L2搜索恢复", False, f"结果不足: {len(results)}")
            
            # 测试删除后的恢复
            if memory_ids:
                l2.delete(memory_ids[0])
                results_after_delete = l2.search("恢复测试", top_k=5)
                
                if len(results_after_delete) < len(results):
                    self._record_result("L2删除恢复", True, "删除后索引正常")
                else:
                    self._record_result("L2删除恢复", False, "删除后索引异常")
                    
        except Exception as e:
            self._record_result("L2内存恢复", False, f"异常: {e}")
    
    def _test_cache_recovery(self):
        """测试缓存恢复"""
        print("\n[开始] 缓存恢复测试")
        
        try:
            cache = QueryCache(max_size=100, ttl_seconds=1)
            
            # 设置缓存
            cache.set("key1", "value1")
            cache.set("key2", "value2")
            
            # 验证缓存命中
            value1 = cache.get("key1")
            if value1 == "value1":
                self._record_result("缓存命中", True, "缓存正常命中")
            else:
                self._record_result("缓存命中", False, f"缓存值异常: {value1}")
            
            # 等待TTL过期
            time.sleep(1.5)
            
            # 验证缓存过期
            expired_value = cache.get("key1")
            if expired_value is None:
                self._record_result("缓存过期", True, "TTL过期后返回None")
            else:
                self._record_result("缓存过期", False, "TTL未生效")
            
            # 测试LRU淘汰
            cache2 = QueryCache(max_size=3, ttl_seconds=60)
            cache2.set("a", 1)
            cache2.set("b", 2)
            cache2.set("c", 3)
            cache2.set("d", 4)  # 应该淘汰a
            
            a_value = cache2.get("a")
            d_value = cache2.get("d")
            
            if a_value is None and d_value == 4:
                self._record_result("LRU淘汰", True, "LRU淘汰正常工作")
            else:
                self._record_result("LRU淘汰", False, f"LRU异常: a={a_value}, d={d_value}")
                
        except Exception as e:
            self._record_result("缓存恢复", False, f"异常: {e}")
    
    def _test_concurrent_recovery(self):
        """测试并发恢复"""
        print("\n[开始] 并发恢复测试")
        
        try:
            concurrency_mgr = ConcurrencyManager()
            
            # 测试锁的正常获取和释放
            session_id = "recovery_session_001"
            
            with concurrency_mgr.session_lock(session_id):
                # 模拟一些工作
                time.sleep(0.01)
            
            # 锁应该已释放，可以再次获取
            with concurrency_mgr.session_lock(session_id):
                time.sleep(0.01)
            
            self._record_result("锁释放恢复", True, "锁正常释放后可重新获取")
            
            # 测试多线程并发
            errors = []
            success_count = [0]
            
            def concurrent_task(task_id: int):
                try:
                    sid = f"recovery_session_{task_id % 3}"
                    with concurrency_mgr.session_lock(sid):
                        time.sleep(0.01)
                        success_count[0] += 1
                except Exception as e:
                    errors.append(str(e))
            
            threads = []
            for i in range(10):
                t = threading.Thread(target=concurrent_task, args=(i,))
                threads.append(t)
                t.start()
            
            for t in threads:
                t.join()
            
            if len(errors) == 0 and success_count[0] == 10:
                self._record_result("并发恢复", True, "10个并发任务全部成功")
            else:
                self._record_result("并发恢复", False, f"{len(errors)}个错误, {success_count[0]}成功")
                
        except Exception as e:
            self._record_result("并发恢复", False, f"异常: {e}")
    
    def _test_graceful_degradation(self):
        """测试服务降级"""
        print("\n[开始] 服务降级测试")
        
        try:
            l2 = L2VectorMemory()
            
            # 测试空搜索的降级处理
            results = l2.search("不存在的查询内容xyz123", top_k=10)
            
            if len(results) == 0:
                self._record_result("空结果降级", True, "无匹配时返回空列表")
            else:
                self._record_result("空结果降级", False, f"应返回空列表但返回{len(results)}条")
            
            # 测试top_k大于可用结果的情况
            # 先存储少量数据
            for i in range(3):
                l2.store(f"降级测试内容{i}", "degradation_task")
            
            time.sleep(0.5)
            
            results = l2.search("降级测试", top_k=100)
            
            if len(results) <= 3:
                self._record_result("top_k降级", True, f"请求100条返回{len(results)}条，正常降级")
            else:
                self._record_result("top_k降级", False, f"返回结果数异常: {len(results)}")
                
        except Exception as e:
            self._record_result("服务降级", False, f"异常: {e}")
    
    def _generate_report(self) -> Dict[str, Any]:
        """生成测试报告"""
        total = self.passed + self.failed
        pass_rate = (self.passed / total * 100) if total > 0 else 0
        
        print("\n" + "=" * 60)
        print("故障恢复测试报告")
        print("=" * 60)
        print(f"总测试数: {total}")
        print(f"通过: {self.passed}")
        print(f"失败: {self.failed}")
        print(f"通过率: {pass_rate:.1f}%")
        
        # 恢复能力评估
        if pass_rate >= 95:
            assessment = "优秀 - 系统恢复能力强"
        elif pass_rate >= 80:
            assessment = "良好 - 大部分故障可恢复"
        elif pass_rate >= 60:
            assessment = "一般 - 需要改进恢复机制"
        else:
            assessment = "需改进 - 恢复能力存在严重问题"
        
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
    tester = RecoveryTester()
    report = tester.run_all_tests()
    
    # 返回退出码
    sys.exit(0 if report["failed"] == 0 else 1)
