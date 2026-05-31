#!/usr/bin/env python3
"""
Agent可靠记忆系统 - 统一API封装层（阶段96）
提供简洁的对外接口，隐藏内部实现细节
"""

import sys
import os
from typing import Dict, List, Any, Optional
from datetime import datetime

# 确保项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.preprocessing.filter import Preprocessor
from src.memory.router import MemoryRouter
from src.recall.engine import RecallEngine
from src.governance.governor import MemoryGovernor
from src.governance.version_manager import VersionManager
from src.governance.privacy_isolation import PrivacyIsolationManager
from src.review.engine import ReviewEngine
from src.utils.performance import QueryCache, PerformanceMonitor
from src.utils.config_tuner import ConfigTuner


class AgentMemorySystem:
    """
    Agent可靠记忆系统 - 统一API
    
    基于第一性原理设计的Agent记忆系统，提供三层记忆架构：
    - L1 临时记忆：纳秒级延迟，任务结束自动清理
    - L2 向量记忆：语义相似度检索
    - L3 事实记忆：三元组结构化存储
    
    使用示例：
        system = AgentMemorySystem()
        system.remember("用户喜欢Python编程", task_id="chat_001")
        results = system.recall("编程语言", task_id="chat_001")
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化记忆系统
        
        Args:
            config_path: 配置文件路径（可选，使用默认配置）
        """
        self._preprocessor = Preprocessor()
        self._router = MemoryRouter()
        self._recall_engine = RecallEngine()
        self._governor = MemoryGovernor()
        self._review_engine = ReviewEngine()
        self._version_manager = VersionManager()
        self._privacy_manager = PrivacyIsolationManager()
        self._config_tuner = ConfigTuner(config_path)
        self._monitor = PerformanceMonitor()
        
        self._initialized_at = datetime.now().isoformat()
        self._stats = {
            "total_stored": 0,
            "total_recalled": 0,
            "total_tasks": 0
        }
    
    # ========== 核心API ==========
    
    def remember(
        self,
        content: str,
        task_id: str,
        visibility: str = "private",
        owner_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        存储记忆
        
        Args:
            content: 记忆内容
            task_id: 任务标识
            visibility: 可见性（public/private/shared）
            owner_id: 所有者ID（用于隐私控制）
        
        Returns:
            操作结果字典，包含：
            - success: 是否成功
            - memory_id: 记忆ID
            - layer: 存储层级（L1/L2/L3）
            - message: 描述信息
        
        示例：
            result = system.remember("用户偏好深色主题", task_id="chat_001")
            # {'success': True, 'memory_id': 'mem_xxx', 'layer': 'L2'}
        """
        with self._monitor.timed("remember"):
            # 1. 预处理
            processed = self._preprocessor.process(content, task_id)
            if not processed["is_valid"]:
                return {
                    "success": False,
                    "memory_id": None,
                    "layer": None,
                    "message": processed.get("reason", "内容无效")
                }
            
            # 2. 路由存储
            route_result = self._router.route_memory(
                content=processed["content"],
                task_id=task_id
            )
            
            if route_result["success"]:
                memory_id = route_result.get("memory_id", "")
                
                # 3. 设置隐私
                if owner_id:
                    self._privacy_manager.register_memory(
                        memory_id=memory_id,
                        owner_id=owner_id,
                        visibility=visibility
                    )
                
                # 4. 更新统计
                self._stats["total_stored"] += 1
                
                return {
                    "success": True,
                    "memory_id": memory_id,
                    "layer": route_result.get("layer", "unknown"),
                    "message": "记忆存储成功"
                }
            else:
                return {
                    "success": False,
                    "memory_id": None,
                    "layer": None,
                    "message": route_result.get("error", "存储失败")
                }
    
    def recall(
        self,
        query: str,
        task_id: str,
        top_k: int = 5,
        user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        召回记忆
        
        Args:
            query: 查询内容
            task_id: 任务标识
            top_k: 返回数量上限
            user_id: 用户ID（用于隐私过滤）
        
        Returns:
            记忆列表，每条包含：
            - memory_id: 记忆ID
            - content: 记忆内容
            - score: 相关性分数
            - layer: 来源层级
        
        示例：
            results = system.recall("编程语言", task_id="chat_001", top_k=3)
        """
        with self._monitor.timed("recall"):
            # 1. 三路召回
            raw_results = self._recall_engine.recall(
                query=query,
                task_id=task_id,
                top_k=top_k
            )
            
            # 2. 治理过滤
            governed_results = self._governor.govern_recall_results(raw_results)
            
            # 3. 隐私过滤
            if user_id:
                governed_results = [
                    r for r in governed_results
                    if self._privacy_manager.can_access(
                        r.get("memory_id", ""), user_id
                    )
                ]
            
            # 4. 更新统计
            self._stats["total_recalled"] += len(governed_results)
            
            return governed_results
    
    def forget(self, memory_id: str, task_id: str) -> Dict[str, Any]:
        """
        删除记忆
        
        Args:
            memory_id: 记忆ID
            task_id: 任务标识
        
        Returns:
            操作结果字典
        """
        with self._monitor.timed("forget"):
            try:
                # 从路由器删除
                self._router.delete_memory(memory_id, task_id)
                return {"success": True, "message": "记忆已删除"}
            except Exception as e:
                return {"success": False, "message": f"删除失败: {e}"}
    
    def review_task(self, task_id: str) -> Dict[str, Any]:
        """
        任务回顾
        
        Args:
            task_id: 任务标识
        
        Returns:
            回顾结果，包含任务记忆摘要和提取的规则
        """
        with self._monitor.timed("review"):
            return self._review_engine.review_task(task_id)
    
    # ========== 版本管理API ==========
    
    def get_version_history(self, triple_hash: str) -> List[Dict[str, Any]]:
        """获取事实记忆的版本历史"""
        return self._version_manager.get_version_history(triple_hash)
    
    def rollback(self, triple_hash: str, snapshot_id: str) -> Dict[str, Any]:
        """回滚到指定版本"""
        return self._version_manager.rollback_to_version(triple_hash, snapshot_id)
    
    # ========== 隐私管理API ==========
    
    def share_memory(
        self,
        memory_id: str,
        owner_id: str,
        target_user_id: str
    ) -> Dict[str, Any]:
        """
        共享记忆给指定用户
        
        Args:
            memory_id: 记忆ID
            owner_id: 所有者ID
            target_user_id: 目标用户ID
        """
        return self._privacy_manager.share_memory(
            memory_id, owner_id, target_user_id
        )
    
    def revoke_access(
        self,
        memory_id: str,
        owner_id: str,
        target_user_id: str
    ) -> Dict[str, Any]:
        """撤销用户对记忆的访问权限"""
        return self._privacy_manager.revoke_access(
            memory_id, owner_id, target_user_id
        )
    
    # ========== 系统管理API ==========
    
    def get_stats(self) -> Dict[str, Any]:
        """获取系统统计信息"""
        return {
            "initialized_at": self._initialized_at,
            "total_stored": self._stats["total_stored"],
            "total_recalled": self._stats["total_recalled"],
            "total_tasks": self._stats["total_tasks"],
            "performance": self._monitor.get_metrics()
        }
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        return self._config_tuner.get(key, default)
    
    def set_config(self, key: str, value: Any) -> bool:
        """设置配置值"""
        return self._config_tuner.set(key, value)
    
    def health_check(self) -> Dict[str, Any]:
        """
        系统健康检查
        
        Returns:
            健康状态字典，包含各模块状态
        """
        checks = {}
        
        # 检查各模块
        try:
            self._preprocessor.process("健康检查", "health_check")
            checks["preprocessor"] = "healthy"
        except Exception:
            checks["preprocessor"] = "unhealthy"
        
        try:
            self._router.route_memory("健康检查", "health_check")
            checks["router"] = "healthy"
        except Exception:
            checks["router"] = "unhealthy"
        
        try:
            self._recall_engine.recall("测试", "health_check", top_k=1)
            checks["recall"] = "healthy"
        except Exception:
            checks["recall"] = "unhealthy"
        
        all_healthy = all(v == "healthy" for v in checks.values())
        
        return {
            "status": "healthy" if all_healthy else "degraded",
            "checks": checks,
            "timestamp": datetime.now().isoformat()
        }
    
    def shutdown(self):
        """优雅关闭系统"""
        # 清理资源
        self._config_tuner._save_config()
        print("AgentMemorySystem 已优雅关闭")


# 便捷函数
_default_system: Optional[AgentMemorySystem] = None


def get_memory_system() -> AgentMemorySystem:
    """获取全局记忆系统实例"""
    global _default_system
    if _default_system is None:
        _default_system = AgentMemorySystem()
    return _default_system
