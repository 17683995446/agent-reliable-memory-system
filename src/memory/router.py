"""
分层存储路由模块
阶段 46-49：智能分发、标准化格式化、统一存储接口

核心特性：
- 100% 硬编码确定性分发规则
- 自动标准化格式（文本/向量/三元组）
- 统一对外存储接口
"""

import re
import time
import uuid
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

from src.memory.l1_ephemeral import L1EphemeralMemory, get_l1_memory
from src.memory.l2_vector import L2VectorMemory, get_l2_memory
from src.memory.l3_fact import L3FactMemory, Triple, get_l3_memory


class MemoryLayer(Enum):
    """记忆层级"""
    L1 = "L1"  # 瞬时工作记忆
    L2 = "L2"  # 情景经验记忆
    L3 = "L3"  # 永久事实记忆


@dataclass
class StoreRequest:
    """存储请求"""
    content: str
    session_id: str
    task_id: str = ""
    step_index: int = 0
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    source: str = "system"


@dataclass
class StoreResult:
    """存储结果"""
    success: bool
    layer: Optional[MemoryLayer] = None
    item_id: str = ""
    message: str = ""


class MemoryClassifier:
    """
    记忆分类器（阶段 49）
    
    100% 硬编码确定性规则分发，不依赖模型概率判断。
    """
    
    # L1 判定关键词（临时性、步骤性内容）
    L1_KEYWORDS = [
        "步骤", "当前", "正在", "执行中", "处理中", "等待",
        "临时", "中间结果", "进度", "状态更新", "日志"
    ]
    
    # L3 判定关键词（永久性、事实性内容）
    L3_KEYWORDS = [
        "规则", "配置", "实体", "关系", "属性", "定义",
        "固定", "永久", "标准", "协议", "约束", "范式",
        "用户信息", "偏好设置", "业务规则", "事实"
    ]
    
    # L3 关系模式（可提取三元组的内容模式）
    L3_RELATION_PATTERNS = [
        r'(.{2,20})(?:是|为|属于|等于)(.{2,30})',  # A是B
        r'(.{2,20})(?:有|包含|具有|拥有)(.{2,30})',  # A有B
        r'(.{2,20})(?:属于|归类于|归类为)(.{2,30})',  # A属于B
        r'(.{2,20})的(.{2,10})(?:是|为)(.{2,30})',   # A的B是C
    ]
    
    def classify(self, request: StoreRequest) -> MemoryLayer:
        """
        确定性分类
        
        规则优先级：
        1. 如果有活跃任务且 step_index > 0 → L1
        2. 如果匹配 L3 关系模式 → L3
        3. 如果包含 L3 关键词 → L3
        4. 如果包含 L1 关键词 → L1
        5. 默认 → L2
        """
        content = request.content
        
        # 规则 1：活跃任务上下文 → L1
        if request.task_id and request.step_index > 0:
            return MemoryLayer.L1
        
        # 规则 2：可提取三元组 → L3
        for pattern in self.L3_RELATION_PATTERNS:
            if re.search(pattern, content):
                return MemoryLayer.L3
        
        # 规则 3：L3 关键词匹配
        l3_score = sum(1 for kw in self.L3_KEYWORDS if kw in content)
        if l3_score >= 2:
            return MemoryLayer.L3
        
        # 规则 4：L1 关键词匹配
        l1_score = sum(1 for kw in self.L1_KEYWORDS if kw in content)
        if l1_score >= 1 and request.task_id:
            return MemoryLayer.L1
        
        # 规则 5：默认 → L2
        return MemoryLayer.L2


class TripleExtractor:
    """
    三元组提取器（阶段 48）
    
    从文本中提取「实体-关系-实体/属性」三元组。
    使用硬编码正则规则，不依赖 NLP 模型。
    """
    
    # 关系映射（中文 → 标准关系名）
    RELATION_MAP = {
        "是": "IS", "为": "IS", "等于": "EQUALS",
        "有": "HAS", "包含": "CONTAINS", "具有": "HAS",
        "属于": "BELONGS_TO", "归类于": "BELONGS_TO",
        "位于": "LOCATED_IN", "关联": "RELATED_TO",
        "依赖": "DEPENDS_ON", "使用": "USES",
        "管理": "MANAGES", "控制": "CONTROLS",
    }
    
    def extract(self, content: str) -> List[Triple]:
        """从文本中提取三元组"""
        triples = []
        
        # 模式 1: A 是 B（属性）
        pattern_is = r'([\u4e00-\u9fff\w]{2,20})\s*(?:是|为)\s*([\u4e00-\u9fff\w]{2,30})'
        for match in re.finditer(pattern_is, content):
            subject, obj = match.group(1).strip(), match.group(2).strip()
            predicate = self.RELATION_MAP.get("是", "IS")
            triples.append(Triple(
                subject=subject, predicate=predicate,
                object=obj, is_attribute=True, source=content[:100]
            ))
        
        # 模式 2: A 有 B（关系）
        pattern_has = r'([\u4e00-\u9fff\w]{2,20})\s*(?:有|包含|具有|拥有)\s*([\u4e00-\u9fff\w]{2,30})'
        for match in re.finditer(pattern_has, content):
            subject, obj = match.group(1).strip(), match.group(2).strip()
            predicate = self.RELATION_MAP.get("有", "HAS")
            triples.append(Triple(
                subject=subject, predicate=predicate,
                object=obj, is_attribute=False, source=content[:100]
            ))
        
        # 模式 3: A 属于 B（关系）
        pattern_belong = r'([\u4e00-\u9fff\w]{2,20})\s*(?:属于|归类于|归类为)\s*([\u4e00-\u9fff\w]{2,30})'
        for match in re.finditer(pattern_belong, content):
            subject, obj = match.group(1).strip(), match.group(2).strip()
            predicate = self.RELATION_MAP.get("属于", "BELONGS_TO")
            triples.append(Triple(
                subject=subject, predicate=predicate,
                object=obj, is_attribute=False, source=content[:100]
            ))
        
        return triples


class MemoryRouter:
    """
    记忆路由器（阶段 49）
    
    统一存储接口，按场景自动分发数据到对应层级。
    """
    
    def __init__(self, l1: L1EphemeralMemory = None, l2: L2VectorMemory = None,
                 l3: L3FactMemory = None):
        self.l1 = l1 or get_l1_memory()
        self.l2 = l2 or get_l2_memory()
        self.l3 = l3 or get_l3_memory()
        
        self.classifier = MemoryClassifier()
        self.triple_extractor = TripleExtractor()
        self.logger = logging.getLogger("memory.router")
    
    def store(self, request: StoreRequest) -> StoreResult:
        """
        统一存储入口
        
        自动分类 → 标准化格式 → 写入对应层级
        """
        # Step 1: 分类
        layer = self.classifier.classify(request)
        
        # Step 2: 按层级存储
        if layer == MemoryLayer.L1:
            return self._store_l1(request)
        elif layer == MemoryLayer.L2:
            return self._store_l2(request)
        elif layer == MemoryLayer.L3:
            return self._store_l3(request)
    
    def _store_l1(self, request: StoreRequest) -> StoreResult:
        """存储到 L1 瞬时记忆"""
        try:
            self.l1.store(
                session_id=request.session_id,
                task_id=request.task_id,
                content=request.content,
                step_index=request.step_index,
                metadata=request.metadata
            )
            self.logger.info(f"[L1] 存储成功: session={request.session_id}")
            return StoreResult(success=True, layer=MemoryLayer.L1, message="L1存储成功")
        except Exception as e:
            self.logger.error(f"[L1] 存储失败: {e}")
            return StoreResult(success=False, layer=MemoryLayer.L1, message=str(e))
    
    def _store_l2(self, request: StoreRequest) -> StoreResult:
        """存储到 L2 向量记忆"""
        try:
            item_id = f"l2_{uuid.uuid4().hex[:12]}"
            # L2 需要 Embedding 向量（由外部调用者提供或使用默认零向量）
            # 这里使用简化实现：实际使用时由调度层传入向量
            import numpy as np
            vector = request.metadata.get("vector")
            if vector is None:
                # 使用内容哈希作为伪向量（实际应使用 Embedding 模型）
                vector = np.zeros(768, dtype=np.float32)
            
            self.l2.store(
                item_id=item_id,
                vector=vector,
                content=request.content,
                tags=request.tags,
                source_session=request.session_id
            )
            self.logger.info(f"[L2] 存储成功: id={item_id}")
            return StoreResult(success=True, layer=MemoryLayer.L2, item_id=item_id, message="L2存储成功")
        except Exception as e:
            self.logger.error(f"[L2] 存储失败: {e}")
            return StoreResult(success=False, layer=MemoryLayer.L2, message=str(e))
    
    def _store_l3(self, request: StoreRequest) -> StoreResult:
        """存储到 L3 事实记忆"""
        try:
            # 提取三元组
            triples = self.triple_extractor.extract(request.content)
            
            if not triples:
                # 无法提取三元组，降级为 L2 存储
                self.logger.info(f"[L3] 无法提取三元组，降级为L2存储")
                return self._store_l2(request)
            
            count = 0
            for triple in triples:
                triple.source = request.source
                if self.l3.store_triple(triple):
                    count += 1
            
            self.logger.info(f"[L3] 存储成功: {count}个三元组")
            return StoreResult(success=True, layer=MemoryLayer.L3, message=f"L3存储成功({count}个三元组)")
        except Exception as e:
            self.logger.error(f"[L3] 存储失败: {e}")
            return StoreResult(success=False, layer=MemoryLayer.L3, message=str(e))
    
    def store_batch(self, requests: List[StoreRequest]) -> List[StoreResult]:
        """批量存储"""
        return [self.store(req) for req in requests]
