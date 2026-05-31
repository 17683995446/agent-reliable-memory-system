#!/usr/bin/env python3
"""
集成测试模块 - 阶段75-78
验证所有模块的协同工作
"""

import sys
import os
import time
import threading
from typing import Dict, List, Any
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.preprocessing.filter import Preprocessor
from src.memory.router import MemoryRouter
from src.recall.engine import RecallEngine
from src.governance.governor import MemoryGovernor
from src.governance.version_manager import VersionManager
from src.governance.privacy_isolation import PrivacyIsolationManager
from src.review.engine import ReviewEngine
from src.utils.performance import QueryCache, MemoryOptimizer, ConcurrencyManager, PerformanceMonitor


class IntegrationTester:
    """集成测试器 - 验证全系统协同"""
    
    def __init__(self):
        self.results: List[Dict[str, Any]] = []
        self.passed = 0
        self.failed = 0
        
    def run_all_tests(self) -> Dict[str, Any]:
        """运行所有集成测试"""
        print("=" * 60)
        print("Agent可靠记忆系统 - 集成测试")
        print("=" * 60)
        
        # 测试各模块集成
        self._test_preprocessing_to_storage()
        self._test_storage_to_recall()
        self._test_recall_to_governance()
        self._test_governance_to_version()
        self._test_privacy_isolation()
        self._test_performance_optimization()
        self._test_concurrent_access()
        self._test_end_to_end_workflow()
        
        return self._generate_report()
    
    def _test_preprocessing_to_storage(self):
        """测试预处理到存储的集成"""
        test_name = "预处理→存储集成"
        try:
            # 初始化模块
            preprocessor = Preprocessor()
            router = MemoryRouter()
            
            # 测试数据
            test_memories = [
                {"content": "用户喜欢Python编程", "task_id": "task_001"},
                {"content": "系统配置参数: timeout=30", "task_id": "task_001"},
                {"content": "这是一个幻觉内容", "task_id": "task_001"},  # 应该被过滤
            ]
            
            processed_count = 0
            for mem in test_memories:
                # 预处理
                processed = preprocessor.process(mem["content"], mem["task_id"])
                if processed["is_valid"]:
                    # 路由到存储
                    route_result = router.route_memory(
                        content=processed["content"],
                        task_id=mem["task_id"]
                    )
                    if route_result["success"]:
                        processed_count += 1
            
            # 验证结果
            assert processed_count >= 2, f"预期至少2条有效记忆，实际{processed_count}"
            
            self._record_result(test_name, True, f"成功处理{processed_count}条记忆")
        except Exception as e:
            self._record_result(test_name, False, str(e))
    
    def _test_storage_to_recall(self):
        """测试存储到召回的集成"""
        test_name = "存储→召回集成"
        try:
            router = MemoryRouter()
            recall_engine = RecallEngine()
            
            # 存储测试记忆
            test_content = [
                "Python是一种高级编程语言",
                "机器学习需要大量数据",
                "深度学习是机器学习的子集",
            ]
            
            task_id = "recall_test_001"
            for content in test_content:
                router.route_memory(content, task_id)
            
            # 等待索引更新
            time.sleep(0.5)
            
            # 召回测试
            query = "编程语言"
            results = recall_engine.recall(
                query=query,
                task_id=task_id,
                top_k=5
            )
            
            assert len(results) > 0, "召回结果为空"
            assert any("Python" in str(r) for r in results), "未召回相关内容"
            
            self._record_result(test_name, True, f"召回{len(results)}条相关记忆")
        except Exception as e:
            self._record_result(test_name, False, str(e))
    
    def _test_recall_to_governance(self):
        """测试召回到治理的集成"""
        test_name = "召回→治理集成"
        try:
            governor = MemoryGovernor(
                eviction_threshold=0.3,
                conflict_threshold=0.8
            )
            
            # 模拟召回结果
            recalled_memories = [
                {"memory_id": "mem_001", "content": "测试内容1", "confidence": 0.9},
                {"memory_id": "mem_002", "content": "测试内容2", "confidence": 0.2},  # 低置信度
            ]
            
            # 应用治理
            governed = governor.govern_recall_results(recalled_memories)
            
            # 低置信度记忆应该被过滤
            assert len(governed) < len(recalled_memories), "治理未过滤低置信度记忆"
            
            self._record_result(test_name, True, f"治理后剩余{len(governed)}条记忆")
        except Exception as e:
            self._record_result(test_name, False, str(e))
    
    def _test_governance_to_version(self):
        """测试治理到版本管理的集成"""
        test_name = "治理→版本管理集成"
        try:
            governor = MemoryGovernor()
            version_manager = VersionManager()
            
            # 模拟冲突检测
            old_fact = {"subject": "系统", "predicate": "版本", "object": "1.0"}
            new_fact = {"subject": "系统", "predicate": "版本", "object": "2.0"}
            
            # 检测冲突
            is_conflict, _ = governor._detect_conflict(old_fact, new_fact)
            assert is_conflict, "冲突检测失败"
            
            # 创建版本快照
            triple_hash = "test_hash_001"
            snapshot = version_manager.create_snapshot(
                triple_hash=triple_hash,
                subject=old_fact["subject"],
                predicate=old_fact["predicate"],
                old_value=old_fact["object"],
                new_value=new_fact["object"],
                updated_by="test_user"
            )
            
            assert snapshot is not None, "版本快照创建失败"
            
            # 获取版本历史
            history = version_manager.get_version_history(triple_hash)
            assert len(history) > 0, "版本历史为空"
            
            self._record_result(test_name, True, f"成功创建版本快照，历史记录{len(history)}条")
        except Exception as e:
            self._record_result(test_name, False, str(e))
    
    def _test_privacy_isolation(self):
        """测试隐私隔离功能"""
        test_name = "隐私隔离"
        try:
            privacy_manager = PrivacyIsolationManager()
            
            # 注册不同可见性的记忆
            memory_id_public = "mem_public_001"
            memory_id_private = "mem_private_001"
            memory_id_shared = "mem_shared_001"
            
            owner_id = "user_001"
            other_user = "user_002"
            allowed_user = "user_003"
            
            # 注册公开记忆
            privacy_manager.register_memory(
                memory_id=memory_id_public,
                owner_id=owner_id,
                visibility="public"
            )
            
            # 注册私有记忆
            privacy_manager.register_memory(
                memory_id=memory_id_private,
                owner_id=owner_id,
                visibility="private"
            )
            
            # 注册共享记忆
            privacy_manager.register_memory(
                memory_id=memory_id_shared,
                owner_id=owner_id,
                visibility="shared",
                allowed_users=[allowed_user]
            )
            
            # 验证访问控制
            assert privacy_manager.can_access(memory_id_public, other_user), "公开记忆访问失败"
            assert not privacy_manager.can_access(memory_id_private, other_user), "私有记忆应被拒绝"
            assert privacy_manager.can_access(memory_id_shared, allowed_user), "共享记忆访问失败"
            assert not privacy_manager.can_access(memory_id_shared, other_user), "未授权用户应被拒绝"
            
            self._record_result(test_name, True, "隐私隔离访问控制正常")
        except Exception as e:
            self._record_result(test_name, False, str(e))
    
    def _test_performance_optimization(self):
        """测试性能优化功能"""
        test_name = "性能优化"
        try:
            # 测试查询缓存
            cache = QueryCache(max_size=100, ttl_seconds=10)
            
            test_key = "test_query"
            test_value = {"results": ["item1", "item2"]}
            
            # 设置缓存
            cache.set(test_key, test_value)
            
            # 读取缓存
            cached = cache.get(test_key)
            assert cached == test_value, "缓存读取失败"
            
            # 测试性能监控
            monitor = PerformanceMonitor()
            
            @monitor.timed("test_operation")
            def test_operation():
                time.sleep(0.01)
                return "done"
            
            result = test_operation()
            metrics = monitor.get_metrics()
            
            assert result == "done", "监控装饰器执行失败"
            assert "test_operation" in metrics, "性能指标未记录"
            
            # 测试内存优化器
            optimizer = MemoryOptimizer()
            # 内存优化器初始化正常即可
            
            self._record_result(test_name, True, "性能优化模块工作正常")
        except Exception as e:
            self._record_result(test_name, False, str(e))
    
    def _test_concurrent_access(self):
        """测试并发访问"""
        test_name = "并发访问"
        try:
            concurrency_manager = ConcurrencyManager()
            results = []
            errors = []
            
            def concurrent_task(task_id: int):
                try:
                    session_id = f"session_{task_id % 3}"  # 3个会话
                    with concurrency_manager.session_lock(session_id):
                        # 模拟一些工作
                        time.sleep(0.01)
                        results.append(task_id)
                except Exception as e:
                    errors.append((task_id, str(e)))
            
            # 启动多个线程
            threads = []
            for i in range(10):
                t = threading.Thread(target=concurrent_task, args=(i,))
                threads.append(t)
                t.start()
            
            # 等待所有线程完成
            for t in threads:
                t.join()
            
            assert len(errors) == 0, f"并发访问出现错误: {errors}"
            assert len(results) == 10, f"预期10个结果，实际{len(results)}"
            
            self._record_result(test_name, True, f"10个并发任务全部成功")
        except Exception as e:
            self._record_result(test_name, False, str(e))
    
    def _test_end_to_end_workflow(self):
        """测试端到端工作流"""
        test_name = "端到端工作流"
        try:
            # 初始化所有模块
            preprocessor = Preprocessor()
            router = MemoryRouter()
            recall_engine = RecallEngine()
            governor = MemoryGovernor()
            privacy_manager = PrivacyIsolationManager()
            
            # 模拟完整工作流
            task_id = "e2e_test_001"
            user_id = "user_e2e_001"
            
            # 1. 存储记忆
            memories = [
                "用户偏好使用深色主题",
                "系统默认语言是中文",
                "数据备份每天凌晨2点执行",
            ]
            
            memory_ids = []
            for content in memories:
                # 预处理
                processed = preprocessor.process(content, task_id)
                if processed["is_valid"]:
                    # 路由存储
                    result = router.route_memory(processed["content"], task_id)
                    if result["success"]:
                        memory_id = result.get("memory_id", f"mem_{len(memory_ids)}")
                        memory_ids.append(memory_id)
                        
                        # 设置隐私
                        privacy_manager.register_memory(
                            memory_id=memory_id,
                            owner_id=user_id,
                            visibility="private"
                        )
            
            # 2. 召回记忆
            time.sleep(0.5)  # 等待索引
            query = "用户偏好设置"
            recall_results = recall_engine.recall(query, task_id, top_k=5)
            
            # 3. 应用治理
            governed_results = governor.govern_recall_results(recall_results)
            
            # 4. 验证隐私
            accessible_results = [
                r for r in governed_results
                if privacy_manager.can_access(r.get("memory_id", ""), user_id)
            ]
            
            assert len(memory_ids) > 0, "记忆存储失败"
            assert len(recall_results) > 0, "记忆召回失败"
            
            self._record_result(
                test_name, 
                True, 
                f"存储{len(memory_ids)}条，召回{len(recall_results)}条，治理后{len(governed_results)}条"
            )
        except Exception as e:
            self._record_result(test_name, False, str(e))
    
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
    
    def _generate_report(self) -> Dict[str, Any]:
        """生成测试报告"""
        total = self.passed + self.failed
        pass_rate = (self.passed / total * 100) if total > 0 else 0
        
        report = {
            "total_tests": total,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": f"{pass_rate:.1f}%",
            "results": self.results,
            "timestamp": datetime.now().isoformat()
        }
        
        print("\n" + "=" * 60)
        print("测试结果汇总")
        print("=" * 60)
        print(f"总测试数: {total}")
        print(f"通过: {self.passed}")
        print(f"失败: {self.failed}")
        print(f"通过率: {pass_rate:.1f}%")
        print("=" * 60)
        
        return report


def run_performance_benchmark():
    """运行性能基准测试"""
    print("\n" + "=" * 60)
    print("性能基准测试")
    print("=" * 60)
    
    # 初始化模块
    preprocessor = Preprocessor()
    router = MemoryRouter()
    recall_engine = RecallEngine()
    
    # 测试1: 预处理性能
    start = time.time()
    for i in range(100):
        preprocessor.process(f"测试内容{i}", f"task_{i}")
    preprocess_time = time.time() - start
    print(f"预处理性能: 100条/{preprocess_time:.2f}s ({100/preprocess_time:.0f}条/秒)")
    
    # 测试2: 存储性能
    start = time.time()
    for i in range(50):
        router.route_memory(f"存储测试内容{i}", "perf_test")
    storage_time = time.time() - start
    print(f"存储性能: 50条/{storage_time:.2f}s ({50/storage_time:.0f}条/秒)")
    
    # 测试3: 召回性能
    time.sleep(0.5)  # 等待索引
    start = time.time()
    for i in range(20):
        recall_engine.recall("测试查询", "perf_test", top_k=5)
    recall_time = time.time() - start
    print(f"召回性能: 20次/{recall_time:.2f}s ({20/recall_time:.0f}次/秒)")
    
    print("=" * 60)


if __name__ == "__main__":
    # 运行集成测试
    tester = IntegrationTester()
    report = tester.run_all_tests()
    
    # 运行性能基准测试
    run_performance_benchmark()
    
    # 返回退出码
    sys.exit(0 if report["failed"] == 0 else 1)
