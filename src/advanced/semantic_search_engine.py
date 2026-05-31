"""
语义搜索引擎 - 阶段227-229

功能：
- 阶段227: 语义理解
- 阶段228: 查询扩展
- 阶段229: 结果排序

设计原则：
- 确定性规则，无模型依赖
- 最小层级，无循环依赖
- 线程安全，RLock保护
- 单例模式，全局唯一
"""

import threading
import re
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Any
from collections import defaultdict, Counter
import uuid
import heapq


@dataclass
class SearchDocument:
    """搜索文档"""
    doc_id: str
    content: str
    title: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    vector: Optional[List[float]] = None


@dataclass
class SearchQuery:
    """搜索查询"""
    query_id: str
    original_query: str
    expanded_query: List[str] = field(default_factory=list)
    intent: str = ""
    entities: List[str] = field(default_factory=list)


@dataclass
class SearchResult:
    """搜索结果"""
    doc_id: str
    score: float
    semantic_score: float = 0.0
    lexical_score: float = 0.0
    highlights: List[str] = field(default_factory=list)
    explanation: str = ""


class SemanticSearchEngine:
    """
    语义搜索引擎
    
    阶段227: 语义理解
    - 查询意图识别
    - 实体提取
    - 语义向量表示
    
    阶段228: 查询扩展
    - 同义词扩展
    - 相关词扩展
    - 查询重写
    
    阶段229: 结果排序
    - 语义相似度排序
    - 混合排序策略
    - 结果重排序
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
            self._documents: Dict[str, SearchDocument] = {}
            self._inverted_index: Dict[str, Set[str]] = defaultdict(set)
            self._synonyms: Dict[str, List[str]] = defaultdict(list)
            self._document_vectors: Dict[str, List[float]] = {}
            self._init_synonyms()
    
    def _init_synonyms(self):
        """初始化同义词词典"""
        self._synonyms = {
            "search": ["find", "lookup", "query"],
            "memory": ["recall", "remember", "storage"],
            "data": ["information", "content", "records"],
            "user": ["person", "account", "profile"],
            "system": ["platform", "application", "service"]
        }
    
    # ========== 阶段227: 语义理解 ==========
    
    def add_document(self, content: str, title: str = "",
                    metadata: Optional[Dict[str, Any]] = None) -> SearchDocument:
        """添加文档"""
        doc = SearchDocument(
            doc_id=str(uuid.uuid4()),
            content=content,
            title=title,
            metadata=metadata or {}
        )
        
        with self._lock:
            self._documents[doc.doc_id] = doc
            
            # 构建倒排索引
            words = self._tokenize(content + " " + title)
            for word in words:
                self._inverted_index[word].add(doc.doc_id)
            
            # 生成简单向量（词频）
            self._document_vectors[doc.doc_id] = self._generate_vector(content)
        
        return doc
    
    def _tokenize(self, text: str) -> List[str]:
        """分词"""
        return re.findall(r'\b[a-zA-Z]+\b', text.lower())
    
    def _generate_vector(self, text: str) -> List[float]:
        """生成文本向量（简化版）"""
        words = self._tokenize(text)
        word_freq = Counter(words)
        
        # 使用简单的词频向量（取前50维）
        vector = []
        for word, count in word_freq.most_common(50):
            # 简单的TF-IDF近似
            tf = count / len(words) if words else 0
            idf = math.log(len(self._documents) + 1 / (len(self._inverted_index.get(word, set())) + 1)) + 1
            vector.append(tf * idf)
        
        # 填充到固定长度
        while len(vector) < 50:
            vector.append(0.0)
        
        return vector[:50]
    
    def parse_query(self, query: str) -> SearchQuery:
        """解析查询"""
        search_query = SearchQuery(
            query_id=str(uuid.uuid4()),
            original_query=query
        )
        
        # 提取实体（简化：大写单词）
        entities = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', query)
        search_query.entities = entities
        
        # 识别意图
        if any(w in query.lower() for w in ["how", "what", "why", "when"]):
            search_query.intent = "informational"
        elif any(w in query.lower() for w in ["find", "search", "lookup"]):
            search_query.intent = "navigational"
        else:
            search_query.intent = "general"
        
        return search_query
    
    # ========== 阶段228: 查询扩展 ==========
    
    def expand_query(self, query: SearchQuery) -> SearchQuery:
        """扩展查询"""
        words = self._tokenize(query.original_query)
        expanded = set(words)
        
        # 同义词扩展
        for word in words:
            synonyms = self._synonyms.get(word, [])
            expanded.update(synonyms)
        
        # 相关词扩展（基于共现）
        for word in words:
            related = self._find_related_words(word)
            expanded.update(related[:3])  # 取前3个相关词
        
        query.expanded_query = list(expanded)
        return query
    
    def _find_related_words(self, word: str) -> List[str]:
        """查找相关词"""
        # 基于倒排索引找共现词
        docs = self._inverted_index.get(word, set())
        if not docs:
            return []
        
        word_cooccur = Counter()
        for doc_id in docs:
            for other_word, other_docs in self._inverted_index.items():
                if other_word != word and doc_id in other_docs:
                    word_cooccur[other_word] += 1
        
        return [w for w, _ in word_cooccur.most_common(5)]
    
    # ========== 阶段229: 结果排序 ==========
    
    def search(self, query_text: str, top_k: int = 10) -> List[SearchResult]:
        """搜索"""
        # 解析查询
        query = self.parse_query(query_text)
        query = self.expand_query(query)
        
        # 计算分数
        scores = defaultdict(lambda: {"lexical": 0.0, "semantic": 0.0})
        
        # 词汇匹配
        query_words = set(self._tokenize(query.original_query))
        expanded_words = set(query.expanded_query)
        
        for word in expanded_words:
            docs = self._inverted_index.get(word, set())
            for doc_id in docs:
                if word in query_words:
                    scores[doc_id]["lexical"] += 1.0
                else:
                    scores[doc_id]["lexical"] += 0.5
        
        # 语义相似度
        query_vector = self._generate_vector(query.original_query)
        
        for doc_id, doc_vector in self._document_vectors.items():
            semantic_score = self._cosine_similarity(query_vector, doc_vector)
            scores[doc_id]["semantic"] = semantic_score
        
        # 合并分数
        results = []
        for doc_id, score_dict in scores.items():
            # 混合排序
            lexical_score = score_dict["lexical"]
            semantic_score = score_dict["semantic"]
            
            # 如果词汇匹配高，优先词汇分数
            if lexical_score > 0:
                final_score = 0.7 * lexical_score + 0.3 * semantic_score
            else:
                final_score = semantic_score * 0.5
            
            # 生成高亮
            doc = self._documents.get(doc_id)
            highlights = []
            if doc:
                highlights = self._generate_highlights(doc.content, query_words)
            
            results.append(SearchResult(
                doc_id=doc_id,
                score=final_score,
                lexical_score=lexical_score,
                semantic_score=semantic_score,
                highlights=highlights,
                explanation=f"Lexical: {lexical_score:.2f}, Semantic: {semantic_score:.2f}"
            ))
        
        # 排序并返回
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """计算余弦相似度"""
        if len(vec1) != len(vec2):
            return 0.0
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    def _generate_highlights(self, content: str, query_words: Set[str]) -> List[str]:
        """生成高亮片段"""
        highlights = []
        sentences = re.split(r'[.!?]+', content)
        
        for sentence in sentences:
            sentence_lower = sentence.lower()
            for word in query_words:
                if word in sentence_lower:
                    # 截断长句
                    snippet = sentence.strip()[:200]
                    if len(sentence) > 200:
                        snippet += "..."
                    highlights.append(snippet)
                    break
            
            if len(highlights) >= 3:
                break
        
        return highlights


# 全局单例
_semantic_search_engine_instance: Optional[SemanticSearchEngine] = None
_semantic_search_engine_lock = threading.RLock()


def get_semantic_search_engine() -> SemanticSearchEngine:
    """获取语义搜索引擎全局实例"""
    global _semantic_search_engine_instance
    if _semantic_search_engine_instance is None:
        with _semantic_search_engine_lock:
            if _semantic_search_engine_instance is None:
                _semantic_search_engine_instance = SemanticSearchEngine()
    return _semantic_search_engine_instance
