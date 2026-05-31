#!/usr/bin/env python3
"""
压力测试模块 - 阶段81-83
测试系统在高负载下的表现，确定容量上限
"""

import sys
import os
import time
import threading
import random
import string
from typing import Dict, List, Any, Tuple
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.preprocessing.filter import Preprocessor
from src.memory.router import MemoryRouter
from src.recall.engine import RecallEngine
from src.governance.governor import MemoryGovernor


class StressTester:
    """压力测试器"""
    
    def __init__(self):
        self.results: Dict[str, Any] = {}
        self.errors: List[str] = []
        
    def run_all_tests(self) -> Dict[str, Any]:
        """运行所有压力测试"""
        print("=" * 60)
        print("Agent可靠记忆系统 - 压力测试")
        print("=" * 60)
        
        # 测试1: 存储容量测试
        self._test_storage_capacity()
        
        # 测试2: 并发写入测试
        self._test_concurrent_writes()
        
        # 测试3: 并发召回测试
        self._test_concurrent_recalls()
        
        # 测试4: 混合负载测试
        self._test_mixed_workload()
        
        # 测试5: 长时间稳定性测试
        self._test_long_term_stability()
        
        return self._generate_report()
    
    def _generate_random_content(self, length: int = 50) -> str:
        """生成随机内容"""
        chars = string.ascii_letters + string.digits + " "
        return ''.join(random.choice(chars) for _ in range(length))
    
    def _test_storage_capacity(self):
        """测试存储容量上限"""
        test_name = "存储容量测试"
        print(f"\n[开始] {test_name}")
        
        router = MemoryRouter()
        start_time = time.time()
        
        # 测试不同数据量的存储
        test_counts = [100, 500, 1000, 2000]
        results = []
        
        for count in test_counts:
            task_id = f"capacity_test_{count}"
            start = time.time()
            
            try:
                for i in range(count):
                    content = self._generate_random_content(30)
                    router.route_memory(content, task_id)
                
                elapsed = time.time() - start
                throughput = count / elapsed if elapsed > 0 else 0
                
                results.append({
                    "count": count,
                    "elapsed": elapsed,
                    "throughput": throughput
                })
                
                print(f"  存储{count}条: {elapsed:.2f}s ({throughput:.1f}条/秒)")
                
            except Exception as e:
                print(f"  存储{count}条失败: {e}")
                self.errors.append(f"{test_name} - {count}: {e}")
        
        self.results[test_name] = {
            "data": results,
            "total_time": time.time() - start_time
        }
    
    def _test_concurrent_writes(self):
        """测试并发写入性能"""
        test_name = "并发写入测试"
        print(f"\n[开始] {test_name}")
        
        router = MemoryRouter()
        
        def write_task(task_id: int, count: int) -> Tuple[int, float]:
            """写入任务"""
            start = time.time()
            for i in range(count):
                content = f"并发写入测试内容-{task_id}-{i}"
                router.route_memory(content, f"concurrent_write_{task_id}")
            return count, time.time() - start
        
        # 测试不同并发度
        concurrency_levels = [5, 10, 20]
        results = []
        
        for concurrency in concurrency_levels:
            writes_per_thread = 50
            start = time.time()
            
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = [
                    executor.submit(write_task, i, writes_per_thread)
                    for i in range(concurrency)
                ]
                
                total_writes = 0
                for future in as_completed(futures):
                    count, elapsed = future.result()
                    total_writes += count
            
            total_time = time.time() - start
            throughput = total_writes / total_time if total_time > 0 else 0
            
            results.append({
                "concurrency": concurrency,
                "total_writes": total_writes,
                "total_time": total_time,
                "throughput": throughput
            })
            
            print(f"  并发{concurrency}: {total_writes}条/{total_time:.2f}s ({throughput:.1f}条/秒)")
        
        self.results[test_name] = results
    
    def _test_concurrent_recalls(self):
        """测试并发召回性能"""
        test_name = "并发召回测试"
        print(f"\n[开始] {test_name}")
        
        recall_engine = RecallEngine()
        
        # 先存储一些数据
        router = MemoryRouter()
        task_id = "recall_stress_test"
        for i in range(100):
            router.route_memory(f"召回测试数据{i} - 关键词A B C", task_id)
        
        time.sleep(0.5)  # 等待索引
        
        def recall_task(task_id: int, count: int) -> Tuple[int, float]:
            """召回任务"""
            start = time.time()
            for i in range(count):
                recall_engine.recall("关键词A", task_id, top_k=5)
            return count, time.time() - start
        
        # 测试不同并发度
        concurrency_levels = [5, 10, 20]
        results = []
        
        for concurrency in concurrency_levels:
            recalls_per_thread = 20
            start = time.time()
            
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = [
                    executor.submit(recall_task, i, recalls_per_thread)
                    for i in range(concurrency)
                ]
                
                total_recalls = 0
                for future in as_completed(futures):
                    count, elapsed = future.result()
                    total_recalls += count
            
            total_time = time.time() - start
            throughput = total_recalls / total_time if total_time > 0 else 0
            
            results.append({
                "concurrency": concurrency,
                "total_recalls": total_recalls,
                "total_time": total_time,
                "throughput": throughput
            })
            
            print(f"  并发{concurrency}: {total_recalls}次/{total_time:.2f}s ({throughput:.1f}次/秒)")
        
        self.results[test_name] = results
    
    def _test_mixed_workload(self):
        """测试混合负载"""
        test_name = "混合负载测试"
        print(f"\n[开始] {test_name}")
        
        router = MemoryRouter()
        recall_engine = RecallEngine()
        preprocessor = Preprocessor()
        
        def mixed_task(task_id: int) -> Dict[str, int]:
            """混合任务：写入+召回"""
            write_count = 0
            recall_count = 0
            
            for i in range(20):
                # 写入
                content = f"混合负载测试-{task_id}-{i}"
                processed = preprocessor.process(content, f"mixed_{task_id}")
                if processed["is_valid"]:
                    router.route_memory(processed["content"], f"mixed_{task_id}")
                    write_count += 1
                
                # 召回
                if i % 3 == 0:  # 每3次写入后召回
                    recall_engine.recall("测试", f"mixed_{task_id}", top_k=3)
                    recall_count += 1
            
            return {"writes": write_count, "recalls": recall_count}
        
        # 测试不同并发度
        concurrency_levels = [5, 10]
        results = []
        
        for concurrency in concurrency_levels:
            start = time.time()
            
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = [executor.submit(mixed_task, i) for i in range(concurrency)]
                
                total_writes = 0
                total_recalls = 0
                for future in as_completed(futures):
                    result = future.result()
                    total_writes += result["writes"]
                    total_recalls += result["recalls"]
            
            total_time = time.time() - start
            
            results.append({
                "concurrency": concurrency,
                "total_writes": total_writes,
                "total_recalls": total_recalls,
                "total_time": total_time,
                "ops_per_sec": (total_writes + total_recalls) / total_time
            })
            
            print(f"  并发{concurrency}: 写入{total_writes}, 召回{total_recalls}, "
                  f"耗时{total_time:.2f}s ({(total_writes+total_recalls)/total_time:.1f}操作/秒)")
        
        self.results[test_name] = results
    
    def _test_long_term_stability(self):
        """长时间稳定性测试"""
        test_name = "长时间稳定性测试"
        print(f"\n[开始] {test_name} (30秒)")
        
        router = MemoryRouter()
        recall_engine = RecallEngine()
        
        start_time = time.time()
        duration = 30  # 30秒
        
        write_count = 0
        recall_count = 0
        error_count = 0
        
        while time.time() - start_time < duration:
            try:
                # 随机选择操作
                if random.random() < 0.6:  # 60%写入
                    content = self._generate_random_content(20)
                    router.route_memory(content, "stability_test")
                    write_count += 1
                else:  # 40%召回
                    recall_engine.recall("测试", "stability_test", top_k=5)
                    recall_count += 1
                
                # 短暂休息，避免过度占用CPU
                time.sleep(0.01)
                
            except Exception as e:
                error_count += 1
                if error_count <= 3:  # 只记录前3个错误
                    print(f"  错误: {e}")
        
        elapsed = time.time() - start_time
        
        result = {
            "duration": elapsed,
            "writes": write_count,
            "recalls": recall_count,
            "errors": error_count,
            "write_rate": write_count / elapsed,
            "recall_rate": recall_count / elapsed
        }
        
        print(f"  运行{elapsed:.1f}秒: 写入{write_count}条, 召回{recall_count}次, 错误{error_count}个")
        print(f"  平均: {result['write_rate']:.1f}条/秒写入, {result['recall_rate']:.1f}次/秒召回")
        
        self.results[test_name] = result
    
    def _generate_report(self) -> Dict[str, Any]:
        """生成测试报告"""
        print("\n" + "=" * 60)
        print("压力测试报告")
        print("=" * 60)
        
        # 计算推荐容量
        recommendations = self._calculate_capacity()
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "results": self.results,
            "recommendations": recommendations,
            "errors": self.errors
        }
        
        print("\n容量建议:")
        for key, value in recommendations.items():
            print(f"  {key}: {value}")
        
        if self.errors:
            print(f"\n错误记录 ({len(self.errors)}个):")
            for error in self.errors[:5]:  # 只显示前5个
                print(f"  - {error}")
        
        print("=" * 60)
        
        return report
    
    def _calculate_capacity(self) -> Dict[str, Any]:
        """计算推荐容量"""
        recommendations = {}
        
        # 基于存储容量测试
        if "存储容量测试" in self.results:
            data = self.results["存储容量测试"]["data"]
            if data:
                # 找到吞吐量开始明显下降的点
                max_throughput = max(d["throughput"] for d in data)
                threshold = max_throughput * 0.7  # 70%阈值
                
                recommended_count = 1000
                for d in data:
                    if d["throughput"] >= threshold:
                        recommended_count = d["count"]
                
                recommendations["单任务存储上限"] = f"{recommended_count}条"
        
        # 基于并发测试
        if "并发写入测试" in self.results:
            data = self.results["并发写入测试"]
            if data:
                best = max(data, key=lambda x: x["throughput"])
                recommendations["最佳写入并发度"] = f"{best['concurrency']}线程"
                recommendations["最大写入吞吐量"] = f"{best['throughput']:.1f}条/秒"
        
        if "并发召回测试" in self.results:
            data = self.results["并发召回测试"]
            if data:
                best = max(data, key=lambda x: x["throughput"])
                recommendations["最佳召回并发度"] = f"{best['concurrency']}线程"
                recommendations["最大召回吞吐量"] = f"{best['throughput']:.1f}次/秒"
        
        # 基于稳定性测试
        if "长时间稳定性测试" in self.results:
            data = self.results["长时间稳定性测试"]
            if data["errors"] == 0:
                recommendations["稳定性评估"] = "良好"
            else:
                recommendations["稳定性评估"] = f"需改进 ({data['errors']}个错误)"
        
        return recommendations


class CapacityPlanner:
    """容量规划器"""
    
    def __init__(self, stress_results: Dict[str, Any]):
        self.results = stress_results
    
    def generate_plan(self) -> Dict[str, Any]:
        """生成容量规划建议"""
        plan = {
            "当前容量": {},
            "扩展建议": {},
            "风险预警": []
        }
        
        # 分析当前容量
        if "存储容量测试" in self.results:
            storage_data = self.results["存储容量测试"]["data"]
            if storage_data:
                max_tested = max(d["count"] for d in storage_data)
                plan["当前容量"]["已测试存储量"] = f"{max_tested}条"
        
        # 扩展建议
        plan["扩展建议"] = {
            "水平扩展": "可通过增加存储节点扩展容量",
            "垂直扩展": "增加单机内存可提升L1容量",
            "索引优化": "定期重建FAISS索引以保持查询性能"
        }
        
        # 风险预警
        if "长时间稳定性测试" in self.results:
            stability = self.results["长时间稳定性测试"]
            if stability.get("errors", 0) > 0:
                plan["风险预警"].append("长时间运行存在错误，建议排查稳定性问题")
        
        return plan


if __name__ == "__main__":
    tester = StressTester()
    report = tester.run_all_tests()
    
    # 生成容量规划
    planner = CapacityPlanner(report["results"])
    capacity_plan = planner.generate_plan()
    
    print("\n" + "=" * 60)
    print("容量规划")
    print("=" * 60)
    for category, items in capacity_plan.items():
        print(f"\n{category}:")
        if isinstance(items, dict):
            for key, value in items.items():
                print(f"  {key}: {value}")
        elif isinstance(items, list):
            for item in items:
                print(f"  - {item}")
    
    print("\n" + "=" * 60)
