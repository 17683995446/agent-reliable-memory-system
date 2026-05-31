"""
智能召回模块
阶段 50-55：三路并行召回、权重排序、限流熔断、冲突去重

核心特性：
- L3 精准召回 + L2 语义召回 + L1 实时召回
- 固定权重排序算法，结果可复现
- 限流熔断，杜绝上下文超载
- 冲突去重，保留最新有效信息
"""

import time
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

from src.memory.l1_ephemeral import L1EphemeralMemory, get_l1_memory
from src.memory.l2_vector import L2VectorMemory, get_l2_memory
from src.memory.l3_fact import L3FactMemory, get_l3_memory


@dataclass
class RecallItem:
    """召回结果条目"""
    content: str
    layer: str              # L1/L2/L3
    source_id: str          # 来源ID
    score: float = 0.0      # 综合得分
    task_match_score: float = 0.0
    recency_score: float = 0.0
    frequency_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RecallRequest:
    """召回请求"""
    query: str                          # 查询内容
    session_id: str                     # 会话ID
    task_id: str = ""                   # 任务ID
    entities: List[str] = field(default_factory=list)  # 实体列表
    keywords: List[str] = field(default_factory=list)   # 关键词列表
    query_vector: Any = None            # 查询向量（L2语义召回用）
    top_k: int = 10                     # 最大返回数


@dataclass
class RecallResult:
    """召回结果"""
    items: List[RecallItem] = field(default_factory=list)
    total_latency_ms: float = 0.0
    l3_count: int = 0
    l2_count: int = 0
    l1_count: int = 0
    truncated: bool = False


class RecencyScorer:
    """
    时效性评分器
    
    规则（固定）：
    - 7天内 = 1.0
    - 30天内 = 0.7
    - 90天内 = 0.4
    - 90天以上 = 0.1
    """
    
    SCORES = {7: 1.0, 30: 0.7, 90: 0.4}
    DEFAULT = 0.1
    
    def score(self, timestamp: float) -> float:
        """计算时效性得分"""
        age_days = (time.time() - timestamp) / 86400
        
        for threshold, score in sorted(self.SCORES.items()):
            if age_days <= threshold:
                return score
        
        return self.DEFAULT


class FrequencyScorer:
    """
    使用频次评分器
    
    规则（固定）：
    - 近30天调用 > 10次 = 1.0
    - 5-10次 = 0.6
    - 1-5次 = 0.3
    - 0次 = 0.0
    """
    
    def score(self, access_count: int) -> float:
        """计算频次得分"""
        if access_count > 10:
            return 1.0
        elif access_count >= 5:
            return 0.6
        elif access_count >= 1:
            return 0.3
        else:
            return 0.0


class RecallEngine:
    """
    智能召回引擎（阶段 55）
    
    三路并行召回 → 权重排序 → 限流熔断 → 冲突去重
    """
    
    def __init__(self, l1=None, l2=None, l3=None, config=None):
        self.l1 = l1 or get_l1_memory()
        self.l2 = l2 or get_l2_memory()
        self.l3 = l3 or get_l3_memory()
        
        config = config or {}
        weights = config.get("weights", {})
        limits = config.get("limits", {})
        
        # 权重配置
        self.w_task = weights.get("task_match", 0.5)
        self.w_recency = weights.get("recency", 0.3)
        self.w_frequency = weights.get("frequency", 0.2)
        
        # 限流配置
        self.l3_max = limits.get("l3_max", 5)
        self.l2_max = limits.get("l2_max", 10)
        
        self.recency_scorer = RecencyScorer()
        self.frequency_scorer = FrequencyScorer()
        self.logger = logging.getLogger("recall.engine")
    
    def recall(self, request: RecallRequest) -> RecallResult:
        """
        执行召回
        
        流程：三路并行 → 合并 → 去重 → 排序 → 截断
        """
        start_time = time.time()
        result = RecallResult()
        
        # Step 1: 三路并行召回
        l3_items = self._recall_l3(request)
        l2_items = self._recall_l2(request)
        l1_items = self._recall_l1(request)
        
        result.l3_count = len(l3_items)
        result.l2_count = len(l2_items)
        result.l1_count = len(l1_items)
        
        # Step 2: 合并所有结果
        all_items = l3_items + l2_items + l1_items
        
        # Step 3: 冲突去重
        deduped = self._deduplicate(all_items)
        
        # Step 4: 权重排序
        sorted_items = self._rank(deduped)
        
        # Step 5: 限流截断
        final_items = sorted_items[:request.top_k]
        if len(sorted_items) > request.top_k:
            result.truncated = True
        
        result.items = final_items
        result.total_latency_ms = (time.time() - start_time) * 1000
        
        self.logger.info(
            f"[RECALL] session={request.session_id}, "
            f"L3={result.l3_count}, L2={result.l2_count}, L1={result.l1_count}, "
            f"final={len(final_items)}, latency={result.total_latency_ms:.2f}ms"
        )
        
        return result
    
    def _recall_l3(self, request: RecallRequest) -> List[RecallItem]:
        """L3 精准召回：实体 + 关键词匹配"""
        items = []
        
        # 按实体查询
        for entity in request.entities:
            triples = self.l3.query_by_entity(entity)
            for triple in triples:
                score = 1.0  # L3 精准命中，最高匹配度
                items.append(RecallItem(
                    content=f"{triple.subject} {triple.predicate} {triple.object}",
                    layer="L3",
                    source_id=f"L3:{triple.subject}:{triple.predicate}",
                    task_match_score=score,
                    recency_score=self.recency_scorer.score(triple.created_at),
                    frequency_score=0.5,  # L3 事实记忆频次固定中等
                    metadata={"triple": triple.to_dict()}
                ))
        
        # 按关键词搜索实体
        for keyword in request.keywords:
            entities = self.l3.search_entities(keyword)
            for entity_name in entities[:3]:  # 限制每个关键词返回3个
                triples = self.l3.query_by_entity(entity_name)
                for triple in triples:
                    items.append(RecallItem(
                        content=f"{triple.subject} {triple.predicate} {triple.object}",
                        layer="L3",
                        source_id=f"L3:{triple.subject}:{triple.predicate}",
                        task_match_score=0.9,  # 关键词匹配略低于精准命中
                        recency_score=self.recency_scorer.score(triple.created_at),
                        frequency_score=0.5,
                        metadata={"triple": triple.to_dict()}
                    ))
        
        # 限流
        return items[:self.l3_max]
    
    def _recall_l2(self, request: RecallRequest) -> List[RecallItem]:
        """L2 语义召回：向量相似度搜索"""
        items = []
        
        if request.query_vector is None:
            return items
        
        try:
            results = self.l2.search(request.query_vector, top_k=self.l2_max)
            
            for l2_item, similarity in results:
                items.append(RecallItem(
                    content=l2_item.content,
                    layer="L2",
                    source_id=l2_item.id,
                    task_match_score=similarity * 0.8,  # 语义匹配度映射
                    recency_score=self.recency_scorer.score(l2_item.last_access),
                    frequency_score=self.frequency_scorer.score(l2_item.access_count),
                    metadata={"tags": l2_item.tags, "source_session": l2_item.source_session}
                ))
        except Exception as e:
            self.logger.error(f"[RECALL] L2搜索失败: {e}")
        
        return items
    
    def _recall_l1(self, request: RecallRequest) -> List[RecallItem]:
        """L1 实时召回：当前任务上下文"""
        items = []
        
        context = self.l1.get_context(
            session_id=request.session_id,
            task_id=request.task_id or None
        )
        
        for l1_item in context:
            items.append(RecallItem(
                content=l1_item.content,
                layer="L1",
                source_id=f"L1:{l1_item.session_id}:{l1_item.step_index}",
                task_match_score=0.7,  # L1 实时上下文
                recency_score=1.0,     # L1 始终最新
                frequency_score=0.0,   # L1 不计频次
                metadata={"step_index": l1_item.step_index, "task_id": l1_item.task_id}
            ))
        
        return items
    
    def _rank(self, items: List[RecallItem]) -> List[RecallItem]:
        """权重排序"""
        for item in items:
            item.score = (
                self.w_task * item.task_match_score +
                self.w_recency * item.recency_score +
                self.w_frequency * item.frequency_score
            )
        
        return sorted(items, key=lambda x: x.score, reverse=True)
    
    def _deduplicate(self, items: List[RecallItem]) -> List[RecallItem]:
        """冲突去重：同一来源仅保留得分最高的一条"""
        seen = {}
        for item in items:
            # 使用内容前50字符作为去重键
            key = item.content[:50]
            if key not in seen or item.score > seen[key].score:
                seen[key] = item
        
        return list(seen.values())
