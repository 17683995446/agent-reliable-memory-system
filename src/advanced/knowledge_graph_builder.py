"""
知识图谱构建器 - 阶段224-226

功能：
- 阶段224: 实体抽取
- 阶段225: 关系构建
- 阶段226: 图谱推理

设计原则：
- 确定性规则，无模型依赖
- 最小层级，无循环依赖
- 线程安全，RLock保护
- 单例模式，全局唯一
"""

import threading
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Any
from collections import defaultdict
import uuid


@dataclass
class Entity:
    """实体"""
    entity_id: str
    name: str
    entity_type: str
    aliases: List[str] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)
    source_ids: List[str] = field(default_factory=list)


@dataclass
class Relation:
    """关系"""
    relation_id: str
    source_id: str
    target_id: str
    relation_type: str
    properties: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0


@dataclass
class KnowledgeGraph:
    """知识图谱"""
    graph_id: str
    name: str
    entities: Dict[str, Entity] = field(default_factory=dict)
    relations: Dict[str, Relation] = field(default_factory=dict)
    entity_index: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))


class KnowledgeGraphBuilder:
    """
    知识图谱构建器
    
    阶段224: 实体抽取
    - 基于规则的实体识别
    - 实体消歧
    - 实体链接
    
    阶段225: 关系构建
    - 关系抽取
    - 关系验证
    - 关系补全
    
    阶段226: 图谱推理
    - 路径发现
    - 相似度计算
    - 知识补全
    """
    
    _instance = None
    _lock = threading.RLock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        with self._lock:
            if self._initialized:
                return
            
            self._initialized = True
            self._graphs: Dict[str, KnowledgeGraph] = {}
            self._entity_patterns: Dict[str, re.Pattern] = {}
            self._relation_patterns: Dict[str, re.Pattern] = {}
            self._init_patterns()
    
    def _init_patterns(self):
        """初始化模式"""
        # 实体模式
        self._entity_patterns["person"] = re.compile(r"[A-Z][a-z]+ [A-Z][a-z]+")
        self._entity_patterns["organization"] = re.compile(r"[A-Z][a-z]* (Corp|Inc|Ltd|Company)")
        self._entity_patterns["location"] = re.compile(r"[A-Z][a-z]+ (City|Country|State)")
        
        # 关系模式
        self._relation_patterns["works_for"] = re.compile(r"works (for|at|in)")
        self._relation_patterns["located_in"] = re.compile(r"located (in|at)")
        self._relation_patterns["founded_by"] = re.compile(r"founded by")
    
    # ========== 阶段224: 实体抽取 ==========
    
    def extract_entities(self, text: str, source_id: str = "") -> List[Entity]:
        """从文本中抽取实体"""
        entities = []
        
        for entity_type, pattern in self._entity_patterns.items():
            for match in pattern.finditer(text):
                name = match.group()
                entity = Entity(
                    entity_id=str(uuid.uuid4()),
                    name=name,
                    entity_type=entity_type,
                    source_ids=[source_id] if source_id else []
                )
                entities.append(entity)
        
        return entities
    
    def add_entity(self, graph_id: str, name: str, entity_type: str,
                   aliases: Optional[List[str]] = None,
                   properties: Optional[Dict[str, Any]] = None) -> Optional[Entity]:
        """添加实体到图谱"""
        with self._lock:
            graph = self._graphs.get(graph_id)
            if not graph:
                return None
            
            entity = Entity(
                entity_id=str(uuid.uuid4()),
                name=name,
                entity_type=entity_type,
                aliases=aliases or [],
                properties=properties or {}
            )
            
            graph.entities[entity.entity_id] = entity
            graph.entity_index[entity_type].add(entity.entity_id)
            graph.entity_index[name.lower()].add(entity.entity_id)
            
            return entity
    
    def find_entity(self, graph_id: str, name: str) -> List[Entity]:
        """查找实体"""
        with self._lock:
            graph = self._graphs.get(graph_id)
            if not graph:
                return []
            
            entity_ids = graph.entity_index.get(name.lower(), set())
            return [graph.entities[eid] for eid in entity_ids if eid in graph.entities]
    
    # ========== 阶段225: 关系构建 ==========
    
    def add_relation(self, graph_id: str, source_id: str, target_id: str,
                    relation_type: str,
                    properties: Optional[Dict[str, Any]] = None,
                    confidence: float = 1.0) -> Optional[Relation]:
        """添加关系到图谱"""
        with self._lock:
            graph = self._graphs.get(graph_id)
            if not graph:
                return None
            
            if source_id not in graph.entities or target_id not in graph.entities:
                return None
            
            relation = Relation(
                relation_id=str(uuid.uuid4()),
                source_id=source_id,
                target_id=target_id,
                relation_type=relation_type,
                properties=properties or {},
                confidence=confidence
            )
            
            graph.relations[relation.relation_id] = relation
            return relation
    
    def extract_relations(self, text: str, entities: List[Entity]) -> List[Relation]:
        """从文本中抽取关系"""
        relations = []
        
        for relation_type, pattern in self._relation_patterns.items():
            if pattern.search(text):
                # 简化：假设相邻实体之间存在关系
                for i in range(len(entities) - 1):
                    relation = Relation(
                        relation_id=str(uuid.uuid4()),
                        source_id=entities[i].entity_id,
                        target_id=entities[i + 1].entity_id,
                        relation_type=relation_type,
                        confidence=0.7
                    )
                    relations.append(relation)
        
        return relations
    
    def get_entity_relations(self, graph_id: str, entity_id: str,
                            relation_type: Optional[str] = None) -> List[Relation]:
        """获取实体的关系"""
        with self._lock:
            graph = self._graphs.get(graph_id)
            if not graph:
                return []
            
            relations = []
            for rel in graph.relations.values():
                if rel.source_id == entity_id or rel.target_id == entity_id:
                    if relation_type is None or rel.relation_type == relation_type:
                        relations.append(rel)
            
            return relations
    
    # ========== 阶段226: 图谱推理 ==========
    
    def find_path(self, graph_id: str, source_id: str, target_id: str,
                 max_depth: int = 5) -> List[List[str]]:
        """查找实体间的路径"""
        with self._lock:
            graph = self._graphs.get(graph_id)
            if not graph:
                return []
        
        # BFS搜索
        paths = []
        visited = {source_id}
        queue = [(source_id, [source_id])]
        
        while queue and len(paths) < 10:
            current, path = queue.pop(0)
            
            if current == target_id and len(path) > 1:
                paths.append(path)
                continue
            
            if len(path) >= max_depth:
                continue
            
            # 获取相邻节点
            relations = self.get_entity_relations(graph_id, current)
            for rel in relations:
                neighbor = rel.target_id if rel.source_id == current else rel.source_id
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))
        
        return paths
    
    def calculate_similarity(self, graph_id: str, entity1_id: str,
                           entity2_id: str) -> float:
        """计算实体相似度"""
        with self._lock:
            graph = self._graphs.get(graph_id)
            if not graph:
                return 0.0
            
            entity1 = graph.entities.get(entity1_id)
            entity2 = graph.entities.get(entity2_id)
            
            if not entity1 or not entity2:
                return 0.0
            
            score = 0.0
            
            # 类型相同
            if entity1.entity_type == entity2.entity_type:
                score += 0.3
            
            # 共同关系
            rels1 = set(r.relation_type for r in self.get_entity_relations(graph_id, entity1_id))
            rels2 = set(r.relation_type for r in self.get_entity_relations(graph_id, entity2_id))
            common_rels = rels1 & rels2
            if rels1 or rels2:
                score += 0.4 * len(common_rels) / max(len(rels1), len(rels2))
            
            # 共同邻居
            neighbors1 = set()
            neighbors2 = set()
            for rel in graph.relations.values():
                if rel.source_id == entity1_id:
                    neighbors1.add(rel.target_id)
                if rel.target_id == entity1_id:
                    neighbors1.add(rel.source_id)
                if rel.source_id == entity2_id:
                    neighbors2.add(rel.target_id)
                if rel.target_id == entity2_id:
                    neighbors2.add(rel.source_id)
            
            common_neighbors = neighbors1 & neighbors2
            if neighbors1 or neighbors2:
                score += 0.3 * len(common_neighbors) / max(len(neighbors1), len(neighbors2))
            
            return score
    
    def create_graph(self, name: str) -> KnowledgeGraph:
        """创建知识图谱"""
        graph = KnowledgeGraph(
            graph_id=str(uuid.uuid4()),
            name=name
        )
        
        with self._lock:
            self._graphs[graph.graph_id] = graph
        
        return graph
    
    def get_graph(self, graph_id: str) -> Optional[KnowledgeGraph]:
        """获取知识图谱"""
        with self._lock:
            return self._graphs.get(graph_id)
    
    def get_graph_stats(self, graph_id: str) -> Dict[str, int]:
        """获取图谱统计"""
        with self._lock:
            graph = self._graphs.get(graph_id)
            if not graph:
                return {}
            
            return {
                "entities": len(graph.entities),
                "relations": len(graph.relations),
                "entity_types": len(graph.entity_index)
            }


# 全局单例
_knowledge_graph_builder_instance: Optional[KnowledgeGraphBuilder] = None
_knowledge_graph_builder_lock = threading.RLock()


def get_knowledge_graph_builder() -> KnowledgeGraphBuilder:
    """获取知识图谱构建器全局实例"""
    global _knowledge_graph_builder_instance
    if _knowledge_graph_builder_instance is None:
        with _knowledge_graph_builder_lock:
            if _knowledge_graph_builder_instance is None:
                _knowledge_graph_builder_instance = KnowledgeGraphBuilder()
    return _knowledge_graph_builder_instance
