"""
知识提取器模块 (阶段372)

提供实体识别、关系抽取和知识图谱构建功能。
线程安全设计，使用 threading.RLock 保证并发安全。
确定性规则设计，无模型依赖，无循环依赖。
"""

import re
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


# ============================================================================
# 枚举定义
# ============================================================================


class EntityType(Enum):
    """实体类型枚举"""
    PERSON = "person"
    ORGANIZATION = "organization"
    LOCATION = "location"
    DATE = "date"
    TIME = "time"
    NUMBER = "number"
    EMAIL = "email"
    URL = "url"
    KEYWORD = "keyword"
    CONCEPT = "concept"


class RelationType(Enum):
    """关系类型枚举"""
    IS_A = "is_a"
    PART_OF = "part_of"
    LOCATED_IN = "located_in"
    WORKS_FOR = "works_for"
    CREATED_BY = "created_by"
    RELATED_TO = "related_to"
    HAS_PROPERTY = "has_property"


class ExtractionStatus(Enum):
    """提取状态枚举"""
    PENDING = "pending"
    EXTRACTING = "extracting"
    SUCCESS = "success"
    FAILED = "failed"


# ============================================================================
# 数据类定义
# ============================================================================


@dataclass
class Entity:
    """实体数据类"""
    id: str
    text: str
    type: EntityType
    start: int = 0
    end: int = 0
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Relation:
    """关系数据类"""
    id: str
    source_id: str
    target_id: str
    type: RelationType
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class KnowledgeTriple:
    """知识三元组数据类"""
    subject: str
    predicate: str
    object: str
    confidence: float = 1.0


@dataclass
class ExtractionResult:
    """提取结果数据类"""
    entities: List[Entity] = field(default_factory=list)
    relations: List[Relation] = field(default_factory=list)
    triples: List[KnowledgeTriple] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    status: ExtractionStatus = ExtractionStatus.PENDING
    error: Optional[str] = None
    duration: float = 0.0


# ============================================================================
# 知识提取器
# ============================================================================


class KnowledgeExtractor:
    """
    知识提取器
    
    从文本中提取实体、关系和知识三元组。
    使用基于规则的方法，确定性提取，无模型依赖。
    线程安全，使用 RLock 保证并发访问安全。
    """
    
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._extraction_count: int = 0
        self._entity_patterns: Dict[EntityType, List[re.Pattern]] = {}
        self._relation_patterns: Dict[RelationType, List[re.Pattern]] = {}
        
        # 初始化默认模式
        self._init_default_patterns()
    
    def _init_default_patterns(self) -> None:
        """初始化默认提取模式"""
        # 邮箱模式
        self._entity_patterns[EntityType.EMAIL] = [
            re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
        ]
        
        # URL模式
        self._entity_patterns[EntityType.URL] = [
            re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+'),
        ]
        
        # 日期模式
        self._entity_patterns[EntityType.DATE] = [
            re.compile(r'\b\d{4}-\d{2}-\d{2}\b'),  # 2024-01-15
            re.compile(r'\b\d{2}/\d{2}/\d{4}\b'),  # 01/15/2024
            re.compile(r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b', re.IGNORECASE),
        ]
        
        # 时间模式
        self._entity_patterns[EntityType.TIME] = [
            re.compile(r'\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?\b', re.IGNORECASE),
        ]
        
        # 数字模式
        self._entity_patterns[EntityType.NUMBER] = [
            re.compile(r'\b\d+(?:\.\d+)?\b'),
        ]
        
        # 大写单词（可能是专有名词）
        self._entity_patterns[EntityType.CONCEPT] = [
            re.compile(r'\b[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)+\b'),
        ]
    
    def extract_entities(self, text: str) -> List[Entity]:
        """
        提取实体
        
        Args:
            text: 输入文本
            
        Returns:
            实体列表
        """
        entities = []
        entity_id = 0
        
        with self._lock:
            patterns = dict(self._entity_patterns)
        
        for entity_type, pattern_list in patterns.items():
            for pattern in pattern_list:
                for match in pattern.finditer(text):
                    entity_id += 1
                    entities.append(Entity(
                        id=f"ent_{entity_id}",
                        text=match.group(),
                        type=entity_type,
                        start=match.start(),
                        end=match.end(),
                        confidence=1.0,
                    ))
        
        # 去重（按位置）
        seen = set()
        unique_entities = []
        for e in entities:
            key = (e.start, e.end)
            if key not in seen:
                seen.add(key)
                unique_entities.append(e)
        
        return unique_entities
    
    def extract_keywords(self, text: str, top_k: int = 10) -> List[str]:
        """
        提取关键词
        
        Args:
            text: 输入文本
            top_k: 返回前K个关键词
            
        Returns:
            关键词列表
        """
        # 简单的词频统计
        words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
        
        # 停用词过滤
        stopwords = {'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had', 'her', 'was', 'one', 'our', 'out', 'day', 'get', 'has', 'him', 'his', 'how', 'its', 'may', 'new', 'now', 'old', 'see', 'two', 'who', 'boy', 'did', 'she', 'use', 'her', 'way', 'many', 'oil', 'sit', 'set', 'run', 'eat', 'far', 'sea', 'eye', 'ask', 'own', 'say', 'too', 'any', 'try', 'let', 'put', 'end', 'why', 'turn', 'here', 'show', 'every', 'good', 'me', 'give', 'our', 'under', 'name', 'very', 'through', 'just', 'form', 'sentence', 'great', 'think', 'where', 'help', 'much', 'before', 'move', 'right', 'too', 'means', 'old', 'any', 'same', 'tell', 'boy', 'follow', 'came', 'want', 'show', 'also', 'around', 'farm', 'three', 'small', 'set', 'put', 'end', 'does', 'another', 'well', 'large', 'must', 'big', 'even', 'such', 'because', 'turn', 'here', 'why', 'asked', 'went', 'men', 'read', 'need', 'land', 'different', 'home', 'us', 'move', 'try', 'kind', 'hand', 'picture', 'again', 'change', 'off', 'play', 'spell', 'air', 'away', 'animal', 'house', 'point', 'page', 'letter', 'mother', 'answer', 'found', 'study', 'still', 'learn', 'should', 'america', 'world'}
        
        word_freq = {}
        for word in words:
            if word not in stopwords:
                word_freq[word] = word_freq.get(word, 0) + 1
        
        # 按频率排序
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        return [word for word, freq in sorted_words[:top_k]]
    
    def extract_relations(self, text: str, entities: List[Entity]) -> List[Relation]:
        """
        提取实体间关系
        
        Args:
            text: 输入文本
            entities: 已提取的实体列表
            
        Returns:
            关系列表
        """
        relations = []
        relation_id = 0
        
        # 简单的共现关系
        sentences = re.split(r'[.!?]+', text)
        
        for sentence in sentences:
            sentence_entities = [e for e in entities if e.text in sentence]
            
            if len(sentence_entities) >= 2:
                for i, e1 in enumerate(sentence_entities):
                    for e2 in sentence_entities[i+1:]:
                        relation_id += 1
                        relations.append(Relation(
                            id=f"rel_{relation_id}",
                            source_id=e1.id,
                            target_id=e2.id,
                            type=RelationType.RELATED_TO,
                            confidence=0.5,
                        ))
        
        return relations
    
    def extract_triples(self, text: str) -> List[KnowledgeTriple]:
        """
        提取知识三元组
        
        Args:
            text: 输入文本
            
        Returns:
            三元组列表
        """
        triples = []
        
        # 简单的 "X is Y" 模式
        is_pattern = re.compile(r'\b([A-Z][a-zA-Z\s]+)\s+is\s+(?:a|an|the)?\s*([a-zA-Z\s]+)\b')
        
        for match in is_pattern.finditer(text):
            subject = match.group(1).strip()
            obj = match.group(2).strip()
            triples.append(KnowledgeTriple(
                subject=subject,
                predicate="is",
                object=obj,
                confidence=0.7,
            ))
        
        # "X has Y" 模式
        has_pattern = re.compile(r'\b([A-Z][a-zA-Z\s]+)\s+has\s+(?:a|an|the)?\s*([a-zA-Z\s]+)\b')
        
        for match in has_pattern.finditer(text):
            subject = match.group(1).strip()
            obj = match.group(2).strip()
            triples.append(KnowledgeTriple(
                subject=subject,
                predicate="has",
                object=obj,
                confidence=0.6,
            ))
        
        return triples
    
    def extract(self, text: str) -> ExtractionResult:
        """
        执行完整提取
        
        Args:
            text: 输入文本
            
        Returns:
            提取结果
        """
        start_time = time.time()
        
        with self._lock:
            self._extraction_count += 1
        
        try:
            entities = self.extract_entities(text)
            keywords = self.extract_keywords(text)
            relations = self.extract_relations(text, entities)
            triples = self.extract_triples(text)
            
            return ExtractionResult(
                entities=entities,
                relations=relations,
                triples=triples,
                keywords=keywords,
                status=ExtractionStatus.SUCCESS,
                duration=time.time() - start_time,
            )
        
        except Exception as e:
            return ExtractionResult(
                status=ExtractionStatus.FAILED,
                error=str(e),
                duration=time.time() - start_time,
            )
    
    def add_entity_pattern(self, entity_type: EntityType, pattern: str) -> None:
        """添加实体提取模式"""
        with self._lock:
            if entity_type not in self._entity_patterns:
                self._entity_patterns[entity_type] = []
            self._entity_patterns[entity_type].append(re.compile(pattern))
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                "extraction_count": self._extraction_count,
                "entity_patterns": {
                    t.value: len(p) for t, p in self._entity_patterns.items()
                },
            }


# ============================================================================
# 全局单例
# ============================================================================

_knowledge_extractor_instance: Optional[KnowledgeExtractor] = None
_knowledge_extractor_lock = threading.Lock()


def get_knowledge_extractor() -> KnowledgeExtractor:
    """获取知识提取器全局单例"""
    global _knowledge_extractor_instance
    with _knowledge_extractor_lock:
        if _knowledge_extractor_instance is None:
            _knowledge_extractor_instance = KnowledgeExtractor()
        return _knowledge_extractor_instance
