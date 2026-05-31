#!/usr/bin/env python3
"""
最终验收测试 - 阶段99
验证系统完整性和交付就绪状态
"""

import sys
import os
import time
from typing import Dict, List, Any
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class FinalAcceptanceTester:
    """最终验收测试器"""
    
    def __init__(self):
        self.results: List[Dict[str, Any]] = []
        self.passed = 0
        self.failed = 0
    
    def run_all(self) -> Dict[str, Any]:
        """运行全部验收测试"""
        print("=" * 60)
        print("Agent可靠记忆系统 - 最终验收测试")
        print("=" * 60)
        
        # 1. 项目结构完整性
        self._check_project_structure()
        
        # 2. 模块导入测试
        self._check_module_imports()
        
        # 3. API接口完整性
        self._check_api_completeness()
        
        # 4. 核心功能端到端验证
        self._check_core_functionality()
        
        # 5. 部署文件完整性
        self._check_deployment_files()
        
        # 6. 文档完整性
        self._check_documentation()
        
        return self._generate_report()
    
    def _record(self, name: str, passed: bool, detail: str):
        self.results.append({"test": name, "passed": passed, "detail": detail})
        if passed:
            self.passed += 1
            print(f"  [通过] {name}: {detail}")
        else:
            self.failed += 1
            print(f"  [失败] {name}: {detail}")
    
    def _check_project_structure(self):
        """验收项1: 项目结构完整性"""
        print("\n[验收] 项目结构完整性")
        
        base = os.path.join(os.path.dirname(__file__), '..')
        required = [
            "api/memory_system.py",
            "src/preprocessing/filter.py",
            "src/memory/router.py",
            "src/memory/l1_ephemeral.py",
            "src/memory/l2_vector.py",
            "src/memory/l3_fact.py",
            "src/recall/engine.py",
            "src/governance/governor.py",
            "src/governance/version_manager.py",
            "src/governance/privacy_isolation.py",
            "src/review/engine.py",
            "src/utils/logger.py",
            "src/utils/performance.py",
            "src/utils/config_tuner.py",
            "config/system.yaml",
            "requirements.txt",
        ]
        
        found = 0
        for f in required:
            if os.path.exists(os.path.join(base, f)):
                found += 1
        
        total = len(required)
        self._record("项目结构", found == total, f"{found}/{total}个必要文件存在")
    
    def _check_module_imports(self):
        """验收项2: 模块导入测试"""
        print("\n[验收] 模块导入")
        
        modules = [
            ("api.memory_system", "AgentMemorySystem"),
            ("src.preprocessing.filter", "Preprocessor"),
            ("src.memory.router", "MemoryRouter"),
            ("src.memory.l1_ephemeral", "L1EphemeralMemory"),
            ("src.memory.l2_vector", "L2VectorMemory"),
            ("src.recall.engine", "RecallEngine"),
            ("src.governance.governor", "MemoryGovernor"),
            ("src.governance.version_manager", "VersionManager"),
            ("src.governance.privacy_isolation", "PrivacyIsolationManager"),
            ("src.review.engine", "ReviewEngine"),
            ("src.utils.performance", "QueryCache"),
            ("src.utils.config_tuner", "ConfigTuner"),
        ]
        
        ok = 0
        for module_name, class_name in modules:
            try:
                mod = __import__(module_name, fromlist=[class_name])
                getattr(mod, class_name)
                ok += 1
            except Exception as e:
                print(f"    [导入失败] {module_name}.{class_name}: {e}")
        
        self._record("模块导入", ok == len(modules), f"{ok}/{len(modules)}个模块可导入")
    
    def _check_api_completeness(self):
        """验收项3: API接口完整性"""
        print("\n[验收] API接口完整性")
        
        try:
            from api.memory_system import AgentMemorySystem
            system = AgentMemorySystem()
            
            required_methods = [
                "remember", "recall", "forget", "review_task",
                "get_version_history", "rollback",
                "share_memory", "revoke_access",
                "get_stats", "get_config", "set_config",
                "health_check", "shutdown"
            ]
            
            found = 0
            for method in required_methods:
                if hasattr(system, method) and callable(getattr(system, method)):
                    found += 1
            
            self._record("API接口", found == len(required_methods),
                        f"{found}/{len(required_methods)}个接口可用")
        except Exception as e:
            self._record("API接口", False, str(e))
    
    def _check_core_functionality(self):
        """验收项4: 核心功能端到端验证"""
        print("\n[验收] 核心功能端到端")
        
        try:
            from api.memory_system import AgentMemorySystem
            system = AgentMemorySystem()
            task_id = "acceptance_test"
            
            # 存储
            r = system.remember("验收测试：Python是一种编程语言", task_id=task_id)
            store_ok = r["success"]
            
            # 召回
            time.sleep(0.3)
            results = system.recall("编程语言", task_id=task_id)
            recall_ok = isinstance(results, list)
            
            # 健康检查
            health = system.health_check()
            health_ok = health["status"] in ("healthy", "degraded")
            
            # 统计
            stats = system.get_stats()
            stats_ok = "total_stored" in stats
            
            all_ok = store_ok and recall_ok and health_ok and stats_ok
            self._record("核心功能", all_ok,
                        f"存储={store_ok}, 召回={recall_ok}, 健康={health_ok}, 统计={stats_ok}")
        except Exception as e:
            self._record("核心功能", False, str(e))
    
    def _check_deployment_files(self):
        """验收项5: 部署文件完整性"""
        print("\n[验收] 部署文件")
        
        base = os.path.join(os.path.dirname(__file__), '..')
        deploy_files = [
            "deploy.py",
            "Dockerfile",
            "docker-compose.yml",
            "requirements.txt",
        ]
        
        found = sum(1 for f in deploy_files if os.path.exists(os.path.join(base, f)))
        self._record("部署文件", found == len(deploy_files),
                    f"{found}/{len(deploy_files)}个部署文件存在")
    
    def _check_documentation(self):
        """验收项6: 文档完整性"""
        print("\n[验收] 文档完整性")
        
        base = os.path.join(os.path.dirname(__file__), '..')
        doc_files = [
            "examples/usage_examples.py",
        ]
        
        found = sum(1 for f in doc_files if os.path.exists(os.path.join(base, f)))
        self._record("文档与示例", found == len(doc_files),
                    f"{found}/{len(doc_files)}个文档文件存在")
    
    def _generate_report(self) -> Dict[str, Any]:
        """生成验收报告"""
        total = self.passed + self.failed
        rate = (self.passed / total * 100) if total > 0 else 0
        
        verdict = "验收通过" if self.failed == 0 else "需要整改"
        
        print("\n" + "=" * 60)
        print("最终验收报告")
        print("=" * 60)
        print(f"  验收项: {total}")
        print(f"  通过: {self.passed}")
        print(f"  失败: {self.failed}")
        print(f"  通过率: {rate:.0f}%")
        print(f"  结论: {verdict}")
        print("=" * 60)
        
        return {
            "total": total,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": f"{rate:.0f}%",
            "verdict": verdict,
            "results": self.results,
            "timestamp": datetime.now().isoformat()
        }


if __name__ == "__main__":
    tester = FinalAcceptanceTester()
    report = tester.run_all()
    sys.exit(0 if report["failed"] == 0 else 1)
