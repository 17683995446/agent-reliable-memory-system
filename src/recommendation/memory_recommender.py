#!/usr/bin/env python3
"""
智能记忆推荐系统 - 阶段122-124
基于上下文推荐相关记忆
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class Recommendation:
    """推荐项"""
    memory_id: str
    content: str
    score: float
    reason: str


class MemoryRecommender:
    """
    记忆推荐器
    
    根据当前上下文推荐相关记忆
    """
    
    def __init__(self, memory_system):
        self.memory_system = memory_system
    
    def recommend(
        self,
        context: str,
        task_id: str,
        top_k: int = 3,
        user_id: Optional[str] = None
    ) -> List[Recommendation]:
        """
        推荐相关记忆
        
        Args:
            context: 当前上下文
            task_id: 任务标识
            top_k: 推荐数量
            user_id: 用户ID
        
        Returns:
            推荐列表
        """
        # 基于上下文召回相关记忆
        candidates = self.memory_system.recall(
            query=context,
            task_id=task_id,
            top_k=top_k * 2,  # 召回更多用于排序
            user_id=user_id
        )
        
        recommendations = []
        for mem in candidates[:top_k]:
            rec = Recommendation(
                memory_id=mem.get("memory_id", ""),
                content=mem.get("content", "")[:100],
                score=mem.get("score", 0.5),
                reason="基于上下文相似度"
            )
            recommendations.append(rec)
        
        return recommendations
    
    def recommend_for_query(
        self,
        query: str,
        task_id: str,
        top_k: int = 3
    ) -> List[Recommendation]:
        """
        为查询推荐相关记忆
        """
        return self.recommend(query, task_id, top_k)
