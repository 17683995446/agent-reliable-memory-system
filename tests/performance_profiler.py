#!/usr/bin/env python3
"""
性能分析器 - 阶段93-95
性能瓶颈分析与优化建议
"""

import sys
import os
import time
import cProfile
import pstats
from io import StringIO
from typing import Dict, List, Any
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.preprocessing.filter import Preprocessor
from src.memory.router import MemoryRouter
from src.recall.engine import RecallEngine


class PerformanceProfiler:
    """性能分析器"""
    
    def __init__(self):
        self.results: Dict[str, Any] = {}
        self.bottlenecks: List[str] = []
    
    def run_all_tests(self) -> Dict[str, Any]:
        """运行所有性能分析"""
        print("=" * 60)
        print("Agent可靠记忆系统 - 性能分析")
        print("=" * 60)
        
        # 预处理性能分析
        self._profile_preprocessing()
        
        # 存储性能分析
        self._profile_storage()
        
        # 召回性能分析
        self._profile_recall()
        
        # 端到端性能分析
        self._profile_end_to_end()
        
        return self._generate_report()
    
    def _profile_preprocessing(self):
        """分析预处理性能"""
        print("\n[开始] 预处理性能分析")
        
        preprocessor = Preprocessor()
        
        # 测试不同长度内容的处理时间
        test_lengths = [10, 50, 100, 500, 1000]
        results = []
        
        for length in test_lengths:
            content = "测试内容" * (length // 4)
            
            # 预热
            for _ in range(3):
                preprocessor.process(content, "profile_task")
            
            # 正式测试
            times = []
            for _ in range(10):
                start = time.perf_counter()
                preprocessor.process(content, "profile_task")
                elapsed = time.perf_counter() - start
                times.append(elapsed)
            
            avg_time = sum(times) / len(times)
            results.append({
                "length": length,
                "avg_time_ms": avg_time * 1000,
                "min_time_ms": min(times) * 1000,
                "max_time_ms": max(times) * 1000
            })
            
            print(f"  长度{length}: 平均{avg_time*1000:.2f}ms")
        
        self.results["preprocessing"] = results
        
        # 检查是否存在性能问题
        slow_threshold = 10  # 10ms
        slow_cases = [r for r in results if r["avg_time_ms"] > slow_threshold]
        if slow_cases:
            self.bottlenecks.append(f"预处理: {len(slow_cases)}种长度超过{slow_threshold}ms")
    
    def _profile_storage(self):
        """分析存储性能"""
        print("\n[开始] 存储性能分析")
        
        router = MemoryRouter()
        
        # 测试批量存储性能
        batch_sizes = [10, 50, 100]
        results = []
        
        for batch_size in batch_sizes:
            start = time.perf_counter()
            for i in range(batch_size):
                router.route_memory(f"性能测试内容{i}", "profile_storage")
            elapsed = time.perf_counter() - start
            
            throughput = batch_size / elapsed if elapsed > 0 else 0
            results.append({
                "batch_size": batch_size,
                "total_time_ms": elapsed * 1000,
                "throughput": throughput
            })
            
            print(f"  批量{batch_size}: {elapsed*1000:.2f}ms ({throughput:.1f}条/秒)")
        
        self.results["storage"] = results
        
        # 检查性能
        min_throughput = 50  # 50条/秒
        slow_cases = [r for r in results if r["throughput"] < min_throughput]
        if slow_cases:
            self.bottlenecks.append(f"存储: 吞吐量低于{min_throughput}条/秒")
    
    def _profile_recall(self):
        """分析召回性能"""
        print("\n[开始] 召回性能分析")
        
        recall_engine = RecallEngine()
        router = MemoryRouter()
        
        # 先准备数据
        task_id = "profile_recall"
        for i in range(100):
            router.route_memory(f"召回性能测试数据{i}", task_id)
        
        time.sleep(0.5)  # 等待索引
        
        # 测试不同top_k的召回时间
        top_k_values = [3, 5, 10, 20]
        results = []
        
        for top_k in top_k_values:
            times = []
            for _ in range(10):
                start = time.perf_counter()
                recall_engine.recall("测试", task_id, top_k=top_k)
                elapsed = time.perf_counter() - start
                times.append(elapsed)
            
            avg_time = sum(times) / len(times)
            results.append({
                "top_k": top_k,
                "avg_time_ms": avg_time * 1000,
                "min_time_ms": min(times) * 1000,
                "max_time_ms": max(times) * 1000
            })
            
            print(f"  top_k={top_k}: 平均{avg_time*1000:.2f}ms")
        
        self.results["recall"] = results
        
        # 检查性能
        slow_threshold = 50  # 50ms
        slow_cases = [r for r in results if r["avg_time_ms"] > slow_threshold]
        if slow_cases:
            self.bottlenecks.append(f"召回: {len(slow_cases)}种配置超过{slow_threshold}ms")
    
    def _profile_end_to_end(self):
        """分析端到端性能"""
        print("\n[开始] 端到端性能分析")
        
        preprocessor = Preprocessor()
        router = MemoryRouter()
        recall_engine = RecallEngine()
        
        # 端到端流程：预处理 -> 存储 -> 召回
        times = []
        
        for i in range(20):
            start = time.perf_counter()
            
            # 预处理
            content = f"端到端测试内容{i}"
            processed = preprocessor.process(content, "e2e_profile")
            
            # 存储
            if processed["is_valid"]:
                router.route_memory(processed["content"], "e2e_profile")
            
            # 召回（每5次执行一次）
            if i % 5 == 0:
                recall_engine.recall("测试", "e2e_profile", top_k=5)
            
            elapsed = time.perf_counter() - start
            times.append(elapsed)
        
        avg_time = sum(times) / len(times)
        total_time = sum(times)
        
        self.results["end_to_end"] = {
            "iterations": len(times),
            "avg_time_ms": avg_time * 1000,
            "total_time_ms": total_time * 1000,
            "min_time_ms": min(times) * 1000,
            "max_time_ms": max(times) * 1000
        }
        
        print(f"  平均: {avg_time*1000:.2f}ms/次")
        print(f"  总计: {total_time*1000:.2f}ms ({len(times)}次)")
        
        # 检查性能
        if avg_time * 1000 > 100:  # 100ms
            self.bottlenecks.append("端到端: 平均耗时超过100ms")
    
    def _generate_report(self) -> Dict[str, Any]:
        """生成性能分析报告"""
        print("\n" + "=" * 60)
        print("性能分析报告")
        print("=" * 60)
        
        # 汇总结果
        print("\n性能概况:")
        
        if "preprocessing" in self.results:
            pre = self.results["preprocessing"]
            avg_times = [r["avg_time_ms"] for r in pre]
            print(f"  预处理: 平均{sum(avg_times)/len(avg_times):.2f}ms")
        
        if "storage" in self.results:
            st = self.results["storage"]
            throughputs = [r["throughput"] for r in st]
            print(f"  存储: 最大{max(throughputs):.1f}条/秒")
        
        if "recall" in self.results:
            rec = self.results["recall"]
            avg_times = [r["avg_time_ms"] for r in rec]
            print(f"  召回: 平均{sum(avg_times)/len(avg_times):.2f}ms")
        
        if "end_to_end" in self.results:
            e2e = self.results["end_to_end"]
            print(f"  端到端: 平均{e2e['avg_time_ms']:.2f}ms")
        
        # 瓶颈分析
        print("\n瓶颈分析:")
        if self.bottlenecks:
            for i, bottleneck in enumerate(self.bottlenecks, 1):
                print(f"  {i}. {bottleneck}")
        else:
            print("  未发现明显性能瓶颈")
        
        # 优化建议
        print("\n优化建议:")
        recommendations = self._generate_recommendations()
        for i, rec in enumerate(recommendations, 1):
            print(f"  {i}. {rec}")
        
        print("=" * 60)
        
        return {
            "results": self.results,
            "bottlenecks": self.bottlenecks,
            "recommendations": recommendations,
            "timestamp": datetime.now().isoformat()
        }
    
    def _generate_recommendations(self) -> List[str]:
        """生成优化建议"""
        recommendations = []
        
        # 基于瓶颈生成建议
        for bottleneck in self.bottlenecks:
            if "预处理" in bottleneck:
                recommendations.append("预处理: 考虑使用更轻量的正则表达式，或添加缓存")
            elif "存储" in bottleneck:
                recommendations.append("存储: 考虑批量写入，减少I/O操作")
            elif "召回" in bottleneck:
                recommendations.append("召回: 考虑优化FAISS索引参数，或使用近似搜索")
            elif "端到端" in bottleneck:
                recommendations.append("端到端: 考虑异步处理，或添加更多缓存层")
        
        # 通用建议
        if not recommendations:
            recommendations.append("当前性能良好，建议定期监控")
        
        recommendations.append("建议定期进行性能回归测试")
        
        return recommendations


if __name__ == "__main__":
    profiler = PerformanceProfiler()
    report = profiler.run_all_tests()
    
    # 返回退出码
    sys.exit(0)
