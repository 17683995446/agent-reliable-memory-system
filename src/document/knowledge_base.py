"""
知识库管理模块 (阶段374)

提供知识存储、查询和管理功能。
线程安全设计，使用 threading.RLock 保证并发安全。
确定性规则设计，无模型依赖，无循环依赖。
"""

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


# ============================================================================
# 枚举定义
# ============================================================================


class KnowledgeType(Enum):
    """知识类型枚举"""
    FACT = "fact"
    CONCEPT = "concept"
    RULE = "rule"
    RELATION = "relation"


class QueryType(Enum):
    """查询类型枚举"""
    EXACT = "exact"
    FUZZY = "fuzzy"
    SEMANTIC = "semantic"


# ============================================================================
# 数据类定义
# ============================================================================


@dataclass
class KnowledgeItem:
    """知识条目数据类"""
    id: str
    content: str
    type: KnowledgeType
    entities: List[str] = field(default_factory=list)
    relations: List[str] = field(default_factory=list)
    source: str = ""
    confidence: float = 1.0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class KnowledgeQuery:
    """知识查询数据类"""
    query: str
    query_type: QueryType = QueryType.EXACT
    filters: Dict[str, Any] = field(default_factory=dict)
    limit: int = 10


@dataclass
class KnowledgeQueryResult:
    """知识查询结果数据类"""
    items: List[KnowledgeItem] = field(default_factory=list)
    total: int = 0
    query_time: float = 0.0


# ============================================================================
# 知识库
# ============================================================================


class KnowledgeBase:
    """
    知识库
    
    存储和管理知识条目，支持多种查询方式。
    线程安全，使用 RLock 保证并发访问安全。
    """
    
    def __init__(self, name: str = "default") -> None:
        self._lock = threading.RLock()
        self._name = name
        self._items: Dict[str, KnowledgeItem] = {}
        self._entity_index: Dict[str, Set[str]] = {}  # entity -> item_ids
        self._type_index: Dict[str, Set[str]] = {}    # type -> item_ids
        self._source_index: Dict[str, Set[str]] = {}  # source -> item_ids
    
    def add(self, item: KnowledgeItem) -> bool:
        """
        添加知识条目
        
        Args:
            item: 知识条目
            
        Returns:
            是否成功添加
        """
        with self._lock:
            if item.id in self._items:
                return False
            
            self._items[item.id] = item
            
            # 更新实体索引
            for entity in item.entities:
                if entity not in self._entity_index:
                    self._entity_index[entity] = set()
                self._entity_index[entity].add(item.id)
            
            # 更新类型索引
            type_key = item.type.value
            if type_key not in self._type_index:
                self._type_index[type_key] = set()
            self._type_index[type_key].add(item.id)
            
            # 更新来源索引
            if item.source:
                if item.source not in self._source_index:
                    self._source_index[item.source] = set()
                self._source_index[item.source].add(item.id)
            
            return True
    
    def get(self, item_id: str) -> Optional[KnowledgeItem]:
        """
        获取知识条目
        
        Args:
            item_id: 条目ID
            
        Returns:
            知识条目或None
        """
        with self._lock:
            return self._items.get(item_id)
    
    def update(self, item_id: str, **kwargs) -> bool:
        """
        更新知识条目
        
        Args:
            item_id: 条目ID
            **kwargs: 要更新的字段
            
        Returns:
            是否成功更新
        """
        with self._lock:
            if item_id not in self._items:
                return False
            
            item = self._items[item_id]
            
            for key, value in kwargs.items():
                if hasattr(item, key):
                    setattr(item, key, value)
            
            item.updated_at = time.time()
            return True
    
    def delete(self, item_id: str) -> bool:
        """
        删除知识条目
        
        Args:
            item_id: 条目ID
            
        Returns:
            是否成功删除
        """
        with self._lock:
            if item_id not in self._items:
                return False
            
            item = self._items[item_id]
            
            # 从索引中移除
            for entity in item.entities:
                if entity in self._entity_index:
                    self._entity_index[entity].discard(item_id)
                    if not self._entity_index[entity]:
                        del self._entity_index[entity]
            
            type_key = item.type.value
            if type_key in self._type_index:
                self._type_index[type_key].discard(item_id)
                if not self._type_index[type_key]:
                    del self._type_index[type_key]
            
            if item.source in self._source_index:
                self._source_index[item.source].discard(item_id)
                if not self._source_index[item.source]:
                    del self._source_index[item.source]
            
            del self._items[item_id]
            return True
    
    def query(self, query: KnowledgeQuery) -> KnowledgeQueryResult:
        """
        查询知识
        
        Args:
            query: 查询对象
            
        Returns:
            查询结果
        """
        start_time = time.time()
        
        with self._lock:
            candidates = set(self._items.keys())
            
            # 应用过滤器
            if 'type' in query.filters:
                type_key = query.filters['type']
                if isinstance(type_key, KnowledgeType):
                    type_key = type_key.value
                type_items = self._type_index.get(type_key, set())
                candidates &= type_items
            
            if 'entity' in query.filters:
                entity = query.filters['entity']
                entity_items = self._entity_index.get(entity, set())
                candidates &= entity_items
            
            if 'source' in query.filters:
                source = query.filters['source']
                source_items = self._source_index.get(source, set())
                candidates &= source_items
            
            # 内容匹配
            query_lower = query.query.lower()
            results = []
            
            for item_id in candidates:
                item = self._items[item_id]
                
                if query.query_type == QueryType.EXACT:
                    if query_lower in item.content.lower():
                        results.append(item)
                elif query.query_type == QueryType.FUZZY:
                    # 简单的模糊匹配
                    if any(term in item.content.lower() for term in query_lower.split()):
                        results.append(item)
                else:  # SEMANTIC - 简化处理
                    results.append(item)
            
            # 限制结果数量
            results = results[:query.limit]
            
            return KnowledgeQueryResult(
                items=results,
                total=len(results),
                query_time=time.time() - start_time,
            )
    
    def search_by_entity(self, entity: str, limit: int = 10) -> List[KnowledgeItem]:
        """
        按实体搜索
        
        Args:
            entity: 实体名称
            limit: 结果数量限制
            
        Returns:
            知识条目列表
        """
        with self._lock:
            item_ids = self._entity_index.get(entity, set())
            return [self._items[iid] for iid in list(item_ids)[:limit]]
    
    def search_by_type(self, knowledge_type: KnowledgeType, limit: int = 10) -> List[KnowledgeItem]:
        """
        按类型搜索
        
        Args:
            knowledge_type: 知识类型
            limit: 结果数量限制
            
        Returns:
            知识条目列表
        """
        with self._lock:
            item_ids = self._type_index.get(knowledge_type.value, set())
            return [self._items[iid] for iid in list(item_ids)[:limit]]
    
    def get_all_entities(self) -> List[str]:
        """获取所有实体"""
        with self._lock:
            return list(self._entity_index.keys())
    
    def get_related_items(self, item_id: str) -> List[KnowledgeItem]:
        """
        获取相关条目（基于共享实体）
        
        Args:
            item_id: 条目ID
            
        Returns:
            相关知识条目列表
        """
        with self._lock:
            if item_id not in self._items:
                return []
            
            item = self._items[item_id]
            related_ids: Set[str] = set()
            
            for entity in item.entities:
                related_ids.update(self._entity_index.get(entity, set()))
            
            related_ids.discard(item_id)
            
            return [self._items[iid] for iid in related_ids]
    
    def merge_items(self, source_id: str, target_id: str) -> bool:
        """
        合并知识条目
        
        Args:
            source_id: 源条目ID
            target_id: 目标条目ID
            
        Returns:
            是否成功合并
        """
        with self._lock:
            if source_id not in self._items or target_id not in self._items:
                return False
            
            source = self._items[source_id]
            target = self._items[target_id]
            
            # 合并实体
            target.entities = list(set(target.entities + source.entities))
            
            # 合并关系
            target.relations = list(set(target.relations + source.relations))
            
            # 更新内容
            target.content += f"\n{source.content}"
            target.updated_at = time.time()
            
            # 删除源条目
            self.delete(source_id)
            
            return True
    
    def export_to_dict(self) -> Dict[str, Any]:
        """导出为字典"""
        with self._lock:
            return {
                "name": self._name,
                "items": {
                    k: {
                        "id": v.id,
                        "content": v.content,
                        "type": v.type.value,
                        "entities": v.entities,
                        "relations": v.relations,
                        "source": v.source,
                        "confidence": v.confidence,
                        "created_at": v.created_at,
                        "updated_at": v.updated_at,
                    }
                    for k, v in self._items.items()
                },
            }
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            type_counts = {}
            for item in self._items.values():
                t = item.type.value
                type_counts[t] = type_counts.get(t, 0) + 1
            
            return {
                "name": self._name,
                "total_items": len(self._items),
                "total_entities": len(self._entity_index),
                "type_distribution": type_counts,
                "sources": list(self._source_index.keys()),
            }


# ============================================================================
# 知识库管理器
# ============================================================================


class KnowledgeBaseManager:
    """
    知识库管理器
    
    管理多个知识库实例。
    线程安全，使用 RLock 保证并发访问安全。
    """
    
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._bases: Dict[str, KnowledgeBase] = {}
    
    def create(self, name: str) -> KnowledgeBase:
        """创建知识库"""
        with self._lock:
            if name not in self._bases:
                self._bases[name] = KnowledgeBase(name)
            return self._bases[name]
    
    def get(self, name: str) -> Optional[KnowledgeBase]:
        """获取知识库"""
        with self._lock:
            return self._bases.get(name)
    
    def delete(self, name: str) -> bool:
        """删除知识库"""
        with self._lock:
            if name in self._bases:
                del self._bases[name]
                return True
            return False
    
    def list_bases(self) -> List[str]:
        """列出所有知识库"""
        with self._lock:
            return list(self._bases.keys())
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                "total_bases": len(self._bases),
                "bases": list(self._bases.keys()),
            }


# ============================================================================
# 全局单例
# ============================================================================

_knowledge_base_manager_instance: Optional[KnowledgeBaseManager] = None
_knowledge_base_manager_lock = threading.Lock()


def get_knowledge_base_manager() -> KnowledgeBaseManager:
    """获取知识库管理器全局单例"""
    global _knowledge_base_manager_instance
    with _knowledge_base_manager_lock:
        if _knowledge_base_manager_instance is None:
            _knowledge_base_manager_instance = KnowledgeBaseManager()
        return _knowledge_base_manager_instance
