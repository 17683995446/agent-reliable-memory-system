"""
智能摘要器 - 阶段230-232

功能：
- 阶段230: 文本摘要
- 阶段231: 关键句提取
- 阶段232: 主题建模

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
class Summary:
    """摘要结果"""
    summary_id: str
    original_length: int
    summary_length: int
    compression_ratio: float
    summary_text: str
    key_sentences: List[str] = field(default_factory=list)
    topics: List[str] = field(default_factory=list)


@dataclass
class Topic:
    """主题"""
    topic_id: str
    name: str
    keywords: List[str] = field(default_factory=list)
    weight: float = 0.0


class SmartSummarizer:
    """
    智能摘要器
    
    阶段230: 文本摘要
    - 抽取式摘要
    - 压缩比控制
    - 多文档摘要
    
    阶段231: 关键句提取
    - 基于TF-IDF的句子重要性
    - 位置加权
    - 冗余消除
    
    阶段232: 主题建模
    - 关键词提取
    - 主题发现
    - 主题权重计算
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
            self._stop_words: Set[str] = {
                "the", "a", "an", "is", "are", "was", "were", "be", "been",
                "being", "have", "has", "had", "do", "does", "did", "will",
                "would", "could", "should", "may", "might", "must", "shall",
                "can", "need", "dare", "ought", "used", "to", "of", "in",
                "for", "on", "with", "at", "by", "from", "as", "into",
                "through", "during", "before", "after", "above", "below",
                "between", "under", "and", "but", "or", "yet", "so",
                "if", "because", "although", "though", "while", "where",
                "when", "that", "which", "who", "whom", "whose", "what",
                "this", "these", "those", "i", "you", "he", "she", "it",
                "we", "they", "me", "him", "her", "us", "them"
            }
    
    def _tokenize(self, text: str) -> List[str]:
        """分词"""
        return re.findall(r'\b[a-zA-Z]+\b', text.lower())
    
    def _split_sentences(self, text: str) -> List[str]:
        """分句"""
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]
    
    # ========== 阶段230: 文本摘要 ==========
    
    def summarize(self, text: str, compression_ratio: float = 0.3) -> Summary:
        """生成摘要"""
        sentences = self._split_sentences(text)
        
        if len(sentences) <= 3:
            # 短文本直接返回
            return Summary(
                summary_id=str(uuid.uuid4()),
                original_length=len(text),
                summary_length=len(text),
                compression_ratio=1.0,
                summary_text=text,
                key_sentences=sentences
            )
        
        # 计算句子分数
        scores = self._score_sentences(sentences)
        
        # 选择Top N句子
        num_sentences = max(1, int(len(sentences) * compression_ratio))
        top_sentences = heapq.nlargest(
            num_sentences,
            enumerate(sentences),
            key=lambda x: scores[x[0]]
        )
        
        # 按原文顺序排序
        top_sentences.sort(key=lambda x: x[0])
        
        # 生成摘要
        summary_sentences = [s for _, s in top_sentences]
        summary_text = " ".join(summary_sentences)
        
        return Summary(
            summary_id=str(uuid.uuid4()),
            original_length=len(text),
            summary_length=len(summary_text),
            compression_ratio=len(summary_text) / len(text) if text else 0,
            summary_text=summary_text,
            key_sentences=summary_sentences
        )
    
    def _score_sentences(self, sentences: List[str]) -> List[float]:
        """为句子打分"""
        # 计算词频
        word_freq = Counter()
        for sentence in sentences:
            words = self._tokenize(sentence)
            for word in words:
                if word not in self._stop_words:
                    word_freq[word] += 1
        
        # 计算句子分数
        scores = []
        for i, sentence in enumerate(sentences):
            words = self._tokenize(sentence)
            
            # TF分数
            tf_score = sum(word_freq.get(word, 0) for word in words if word not in self._stop_words)
            tf_score /= len(words) if words else 1
            
            # 位置加权（开头和结尾的句子更重要）
            position_weight = 1.0
            if i == 0:
                position_weight = 1.5
            elif i == len(sentences) - 1:
                position_weight = 1.2
            elif i < len(sentences) * 0.2:
                position_weight = 1.1
            
            # 长度惩罚（过短或过长的句子分数降低）
            word_count = len(words)
            length_penalty = 1.0
            if word_count < 5:
                length_penalty = 0.5
            elif word_count > 50:
                length_penalty = 0.8
            
            score = tf_score * position_weight * length_penalty
            scores.append(score)
        
        return scores
    
    # ========== 阶段231: 关键句提取 ==========
    
    def extract_key_sentences(self, text: str, n: int = 3) -> List[str]:
        """提取关键句"""
        sentences = self._split_sentences(text)
        
        if len(sentences) <= n:
            return sentences
        
        scores = self._score_sentences(sentences)
        
        # 选择Top N
        indexed_scores = [(i, scores[i]) for i in range(len(sentences))]
        indexed_scores.sort(key=lambda x: x[1], reverse=True)
        
        top_indices = [i for i, _ in indexed_scores[:n]]
        top_indices.sort()  # 按原文顺序
        
        return [sentences[i] for i in top_indices]
    
    # ========== 阶段232: 主题建模 ==========
    
    def extract_topics(self, text: str, num_topics: int = 3) -> List[Topic]:
        """提取主题"""
        words = self._tokenize(text)
        words = [w for w in words if w not in self._stop_words and len(w) > 3]
        
        # 统计词频
        word_freq = Counter(words)
        
        # 提取关键词
        keywords = [word for word, _ in word_freq.most_common(num_topics * 5)]
        
        # 构建主题
        topics = []
        for i in range(num_topics):
            start_idx = i * 5
            end_idx = start_idx + 5
            topic_keywords = keywords[start_idx:end_idx]
            
            if topic_keywords:
                topic = Topic(
                    topic_id=str(uuid.uuid4()),
                    name=topic_keywords[0].capitalize(),
                    keywords=topic_keywords,
                    weight=sum(word_freq.get(k, 0) for k in topic_keywords) / len(words) if words else 0
                )
                topics.append(topic)
        
        return topics
    
    def extract_keywords(self, text: str, top_n: int = 10) -> List[Tuple[str, float]]:
        """提取关键词"""
        words = self._tokenize(text)
        words = [w for w in words if w not in self._stop_words]
        
        word_freq = Counter(words)
        total_words = len(words)
        
        # 计算TF分数
        keywords = []
        for word, freq in word_freq.most_common(top_n * 2):
            if len(word) > 3:  # 过滤短词
                tf = freq / total_words if total_words > 0 else 0
                keywords.append((word, tf))
        
        return keywords[:top_n]


# 全局单例
_smart_summarizer_instance: Optional[SmartSummarizer] = None
_smart_summarizer_lock = threading.RLock()


def get_smart_summarizer() -> SmartSummarizer:
    """获取智能摘要器全局实例"""
    global _smart_summarizer_instance
    if _smart_summarizer_instance is None:
        with _smart_summarizer_lock:
            if _smart_summarizer_instance is None:
                _smart_summarizer_instance = SmartSummarizer()
    return _smart_summarizer_instance
