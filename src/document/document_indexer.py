"""
文档索引器模块 (阶段373)

提供全文检索和倒排索引功能。
线程安全设计，使用 threading.RLock 保证并发安全。
确定性规则设计，无模型依赖，无循环依赖。
"""

import re
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


# ============================================================================
# 枚举定义
# ============================================================================


class IndexType(Enum):
    """索引类型枚举"""
    INVERTED = "inverted"      # 倒排索引
    FORWARD = "forward"        # 正排索引
    NGRAM = "ngram"            # N-gram索引


class MatchType(Enum):
    """匹配类型枚举"""
    EXACT = "exact"
    PREFIX = "prefix"
    FUZZY = "fuzzy"
    WILDCARD = "wildcard"


# ============================================================================
# 数据类定义
# ============================================================================


@dataclass
class IndexEntry:
    """索引条目数据类"""
    term: str
    doc_ids: Set[str] = field(default_factory=set)
    positions: Dict[str, List[int]] = field(default_factory=dict)  # doc_id -> positions
    frequency: int = 0


@dataclass
class SearchResult:
    """搜索结果数据类"""
    doc_id: str
    score: float
    highlights: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchQuery:
    """搜索查询数据类"""
    query: str
    match_type: MatchType = MatchType.EXACT
    limit: int = 10
    offset: int = 0
    filters: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# 文档索引器
# ============================================================================


class DocumentIndexer:
    """
    文档索引器
    
    构建和维护文档索引，支持全文检索。
    使用倒排索引结构，支持高效的关键词查询。
    线程安全，使用 RLock 保证并发访问安全。
    """
    
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._inverted_index: Dict[str, IndexEntry] = {}  # term -> IndexEntry
        self._doc_metadata: Dict[str, Dict[str, Any]] = {}  # doc_id -> metadata
        self._doc_count: int = 0
        self._index_count: int = 0
        
        # 停用词
        self._stopwords: Set[str] = {
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
            'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
            'would', 'could', 'should', 'may', 'might', 'must', 'shall',
            'can', 'need', 'dare', 'ought', 'used', 'to', 'of', 'in',
            'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into',
            'through', 'during', 'before', 'after', 'above', 'below',
            'between', 'under', 'and', 'but', 'or', 'yet', 'so',
            'if', 'because', 'although', 'though', 'while', 'where',
            'when', 'that', 'which', 'who', 'whom', 'whose', 'what',
            'this', 'these', 'those', 'i', 'me', 'my', 'myself', 'we',
            'our', 'ours', 'ourselves', 'you', 'your', 'yours', 'yourself',
            'yourselves', 'he', 'him', 'his', 'himself', 'she', 'her',
            'hers', 'herself', 'it', 'its', 'itself', 'they', 'them',
            'their', 'theirs', 'themselves', 'what', 'which', 'who',
            'whom', 'this', 'that', 'these', 'those', 'am', 'was',
            'were', 'being', 'have', 'has', 'had', 'having', 'do',
            'does', 'did', 'doing', 'a', 'an', 'the', 'and', 'but',
            'if', 'or', 'because', 'as', 'until', 'while', 'of', 'at',
            'by', 'for', 'with', 'about', 'against', 'between', 'into',
            'through', 'during', 'before', 'after', 'above', 'below',
            'to', 'from', 'up', 'down', 'in', 'out', 'on', 'off',
            'over', 'under', 'again', 'further', 'then', 'once',
        }
    
    def _tokenize(self, text: str) -> List[str]:
        """分词"""
        # 转换为小写，提取单词
        words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
        # 过滤停用词和短词
        return [w for w in words if w not in self._stopwords and len(w) > 2]
    
    def _extract_ngrams(self, text: str, n: int = 2) -> List[str]:
        """提取N-gram"""
        words = self._tokenize(text)
        ngrams = []
        for i in range(len(words) - n + 1):
            ngram = ' '.join(words[i:i+n])
            ngrams.append(ngram)
        return ngrams
    
    def add_document(self, doc_id: str, content: str,
                     metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        添加文档到索引
        
        Args:
            doc_id: 文档ID
            content: 文档内容
            metadata: 文档元数据
            
        Returns:
            是否成功添加
        """
        with self._lock:
            try:
                tokens = self._tokenize(content)
                
                # 构建位置映射
                positions: Dict[str, List[int]] = defaultdict(list)
                for pos, token in enumerate(tokens):
                    positions[token].append(pos)
                
                # 更新倒排索引
                for token, pos_list in positions.items():
                    if token not in self._inverted_index:
                        self._inverted_index[token] = IndexEntry(term=token)
                    
                    entry = self._inverted_index[token]
                    entry.doc_ids.add(doc_id)
                    entry.positions[doc_id] = pos_list
                    entry.frequency += len(pos_list)
                
                # 保存元数据
                self._doc_metadata[doc_id] = metadata or {}
                self._doc_metadata[doc_id]['length'] = len(tokens)
                
                self._doc_count += 1
                self._index_count += len(tokens)
                
                return True
            
            except Exception:
                return False
    
    def remove_document(self, doc_id: str) -> bool:
        """
        从索引中移除文档
        
        Args:
            doc_id: 文档ID
            
        Returns:
            是否成功移除
        """
        with self._lock:
            if doc_id not in self._doc_metadata:
                return False
            
            # 从倒排索引中移除
            terms_to_remove = []
            for term, entry in self._inverted_index.items():
                if doc_id in entry.doc_ids:
                    entry.doc_ids.discard(doc_id)
                    if doc_id in entry.positions:
                        entry.frequency -= len(entry.positions[doc_id])
                        del entry.positions[doc_id]
                    
                    # 如果没有文档包含该词，标记删除
                    if not entry.doc_ids:
                        terms_to_remove.append(term)
            
            # 删除空条目
            for term in terms_to_remove:
                del self._inverted_index[term]
            
            # 删除元数据
            del self._doc_metadata[doc_id]
            self._doc_count -= 1
            
            return True
    
    def search(self, query: str, limit: int = 10) -> List[SearchResult]:
        """
        搜索文档
        
        Args:
            query: 搜索查询
            limit: 返回结果数量限制
            
        Returns:
            搜索结果列表
        """
        with self._lock:
            query_tokens = self._tokenize(query)
            
            if not query_tokens:
                return []
            
            # 计算每个文档的得分
            doc_scores: Dict[str, float] = defaultdict(float)
            
            for token in query_tokens:
                if token in self._inverted_index:
                    entry = self._inverted_index[token]
                    
                    # TF-IDF风格的评分
                    idf = 1.0  # 简化计算
                    
                    for doc_id in entry.doc_ids:
                        tf = len(entry.positions.get(doc_id, []))
                        doc_length = self._doc_metadata.get(doc_id, {}).get('length', 1)
                        
                        # 归一化词频
                        normalized_tf = tf / doc_length if doc_length > 0 else 0
                        
                        doc_scores[doc_id] += normalized_tf * idf
            
            # 排序并返回结果
            sorted_docs = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)
            
            results = []
            for doc_id, score in sorted_docs[:limit]:
                # 生成高亮片段
                highlights = self._generate_highlights(doc_id, query_tokens)
                
                results.append(SearchResult(
                    doc_id=doc_id,
                    score=score,
                    highlights=highlights,
                    metadata=self._doc_metadata.get(doc_id, {}),
                ))
            
            return results
    
    def _generate_highlights(self, doc_id: str, query_tokens: List[str]) -> List[str]:
        """生成高亮片段"""
        highlights = []
        
        for token in query_tokens:
            if token in self._inverted_index:
                entry = self._inverted_index[token]
                if doc_id in entry.doc_ids:
                    highlights.append(token)
        
        return highlights[:5]  # 最多5个高亮词
    
    def prefix_search(self, prefix: str, limit: int = 10) -> List[str]:
        """
        前缀搜索
        
        Args:
            prefix: 前缀
            limit: 返回结果数量限制
            
        Returns:
            匹配的词条列表
        """
        with self._lock:
            prefix_lower = prefix.lower()
            matches = []
            
            for term in self._inverted_index.keys():
                if term.startswith(prefix_lower):
                    matches.append(term)
                    if len(matches) >= limit:
                        break
            
            return matches
    
    def get_document_count(self) -> int:
        """获取文档数量"""
        with self._lock:
            return self._doc_count
    
    def get_term_count(self) -> int:
        """获取词条数量"""
        with self._lock:
            return len(self._inverted_index)
    
    def get_term_info(self, term: str) -> Optional[IndexEntry]:
        """获取词条信息"""
        with self._lock:
            return self._inverted_index.get(term)
    
    def clear(self) -> None:
        """清空索引"""
        with self._lock:
            self._inverted_index.clear()
            self._doc_metadata.clear()
            self._doc_count = 0
            self._index_count = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                "document_count": self._doc_count,
                "term_count": len(self._inverted_index),
                "index_count": self._index_count,
                "avg_terms_per_doc": self._index_count / self._doc_count if self._doc_count > 0 else 0,
            }


# ============================================================================
# 全局单例
# ============================================================================

_document_indexer_instance: Optional[DocumentIndexer] = None
_document_indexer_lock = threading.Lock()


def get_document_indexer() -> DocumentIndexer:
    """获取文档索引器全局单例"""
    global _document_indexer_instance
    with _document_indexer_lock:
        if _document_indexer_instance is None:
            _document_indexer_instance = DocumentIndexer()
        return _document_indexer_instance
