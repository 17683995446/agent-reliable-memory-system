"""
Agent可靠记忆系统 - 记忆搜索历史与建议
阶段179-181: 搜索历史记录、搜索建议、热门搜索

设计原则:
- 确定性规则驱动，无模型依赖
- 线程安全（RLock）
- 全局单例模式
- 基于统计的搜索建议
"""

import threading
import time
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict, Counter


class SearchType(Enum):
    """搜索类型"""
    KEYWORD = "keyword"          # 关键词搜索
    SEMANTIC = "semantic"        # 语义搜索
    FILTER = "filter"            # 过滤搜索
    ADVANCED = "advanced"        # 高级搜索
    NL_QUERY = "nl_query"        # 自然语言查询


@dataclass
class SearchRecord:
    """搜索记录"""
    query_id: str
    query_text: str
    search_type: SearchType
    filters: Dict = field(default_factory=dict)
    results_count: int = 0
    clicked_results: List[str] = field(default_factory=list)
    search_time_ms: float = 0
    timestamp: float = field(default_factory=time.time)
    user_id: str = ""
    session_id: str = ""

    def to_dict(self) -> Dict:
        return {
            "query_id": self.query_id,
            "query_text": self.query_text,
            "search_type": self.search_type.value,
            "filters": self.filters,
            "results_count": self.results_count,
            "clicked_results": self.clicked_results,
            "search_time_ms": self.search_time_ms,
            "timestamp": self.timestamp,
            "user_id": self.user_id,
            "session_id": self.session_id,
        }


@dataclass
class SearchSuggestion:
    """搜索建议"""
    text: str
    suggestion_type: str           # "history", "popular", "related", "completion"
    score: float = 0.0
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "text": self.text,
            "type": self.suggestion_type,
            "score": round(self.score, 4),
            "metadata": self.metadata,
        }


class SearchHistoryManager:
    """
    搜索历史与建议管理器

    功能:
    - 搜索历史记录与查询
    - 基于历史的搜索建议
    - 热门搜索统计
    - 搜索自动补全
    - 相关搜索推荐
    """

    def __init__(self, max_history: int = 10000):
        self._lock = threading.RLock()
        self._max_history = max_history
        self._records: Dict[str, SearchRecord] = {}  # query_id -> record
        self._user_history: Dict[str, List[str]] = defaultdict(list)  # user_id -> [query_ids]
        self._query_counter: int = 0
        self._query_freq: Counter = Counter()        # query_text -> count
        self._word_freq: Counter = Counter()         # word -> count
        self._bigram_freq: Counter = Counter()       # bigram -> count
        self._prefix_index: Dict[str, Set[str]] = defaultdict(set)  # prefix -> queries

    # ==================== 搜索记录 ====================

    def record_search(self, query_text: str,
                      search_type: SearchType = SearchType.KEYWORD,
                      filters: Optional[Dict] = None,
                      results_count: int = 0,
                      search_time_ms: float = 0,
                      user_id: str = "",
                      session_id: str = "") -> SearchRecord:
        """
        记录一次搜索

        Args:
            query_text: 查询文本
            search_type: 搜索类型
            filters: 过滤条件
            results_count: 结果数量
            search_time_ms: 搜索耗时（毫秒）
            user_id: 用户ID
            session_id: 会话ID
        """
        with self._lock:
            self._query_counter += 1
            query_id = f"search_{self._query_counter:08d}"

            record = SearchRecord(
                query_id=query_id,
                query_text=query_text.strip(),
                search_type=search_type,
                filters=filters or {},
                results_count=results_count,
                search_time_ms=search_time_ms,
                user_id=user_id,
                session_id=session_id,
            )

            self._records[query_id] = record

            # 更新用户历史
            if user_id:
                self._user_history[user_id].append(query_id)
                if len(self._user_history[user_id]) > 1000:
                    self._user_history[user_id] = self._user_history[user_id][-1000:]

            # 更新统计
            normalized_query = self._normalize_query(query_text)
            self._query_freq[normalized_query] += 1

            # 分词并更新词频
            words = self._extract_words(query_text)
            for word in words:
                self._word_freq[word] += 1

            # 更新二元组
            for i in range(len(words) - 1):
                bigram = f"{words[i]} {words[i+1]}"
                self._bigram_freq[bigram] += 1

            # 更新前缀索引
            for i in range(1, min(len(normalized_query) + 1, 20)):
                prefix = normalized_query[:i]
                self._prefix_index[prefix].add(normalized_query)

            # 清理旧记录
            if len(self._records) > self._max_history:
                self._cleanup_old_records()

            return record

    def record_click(self, query_id: str, memory_id: str):
        """记录点击结果"""
        with self._lock:
            if query_id in self._records:
                self._records[query_id].clicked_results.append(memory_id)

    def get_history(self, user_id: str = "",
                    limit: int = 50,
                    search_type: Optional[SearchType] = None) -> List[SearchRecord]:
        """
        获取搜索历史

        Args:
            user_id: 用户ID（空表示所有用户）
            limit: 返回数量
            search_type: 按类型过滤
        """
        with self._lock:
            if user_id:
                query_ids = self._user_history.get(user_id, [])
                records = [self._records[qid] for qid in query_ids if qid in self._records]
            else:
                records = list(self._records.values())

            if search_type:
                records = [r for r in records if r.search_type == search_type]

            records.sort(key=lambda r: r.timestamp, reverse=True)
            return records[:limit]

    def get_popular_queries(self, limit: int = 20,
                           since_hours: Optional[int] = None) -> List[Dict]:
        """
        获取热门搜索

        Args:
            limit: 返回数量
            since_hours: 最近N小时（None表示全部）
        """
        with self._lock:
            if since_hours:
                cutoff = time.time() - since_hours * 3600
                recent_queries = [
                    r.query_text for r in self._records.values()
                    if r.timestamp >= cutoff
                ]
                freq = Counter(recent_queries)
            else:
                freq = self._query_freq

            return [
                {"query": query, "count": count}
                for query, count in freq.most_common(limit)
            ]

    # ==================== 搜索建议 ====================

    def get_suggestions(self, partial_query: str,
                        user_id: str = "",
                        limit: int = 10) -> List[SearchSuggestion]:
        """
        获取搜索建议

        Args:
            partial_query: 部分输入
            user_id: 用户ID（用于个性化）
            limit: 返回数量
        """
        with self._lock:
            suggestions = []
            normalized = self._normalize_query(partial_query)

            # 1. 历史建议（用户自己的搜索历史）
            if user_id:
                history_suggestions = self._get_history_suggestions(
                    normalized, user_id, limit // 3
                )
                suggestions.extend(history_suggestions)

            # 2. 热门建议
            popular_suggestions = self._get_popular_suggestions(
                normalized, limit // 3
            )
            suggestions.extend(popular_suggestions)

            # 3. 自动补全
            completion_suggestions = self._get_completion_suggestions(
                normalized, limit // 3
            )
            suggestions.extend(completion_suggestions)

            # 去重并排序
            seen = set()
            unique_suggestions = []
            for s in suggestions:
                if s.text.lower() not in seen:
                    seen.add(s.text.lower())
                    unique_suggestions.append(s)

            unique_suggestions.sort(key=lambda s: s.score, reverse=True)
            return unique_suggestions[:limit]

    def _get_history_suggestions(self, partial: str, user_id: str,
                                  limit: int) -> List[SearchSuggestion]:
        """基于用户历史的建议"""
        suggestions = []
        query_ids = self._user_history.get(user_id, [])

        for qid in reversed(query_ids[-100:]):  # 最近100条
            record = self._records.get(qid)
            if not record:
                continue

            if partial in self._normalize_query(record.query_text):
                suggestions.append(SearchSuggestion(
                    text=record.query_text,
                    suggestion_type="history",
                    score=0.9,  # 历史查询高分
                    metadata={"timestamp": record.timestamp},
                ))

            if len(suggestions) >= limit:
                break

        return suggestions

    def _get_popular_suggestions(self, partial: str, limit: int) -> List[SearchSuggestion]:
        """基于热门搜索的建议"""
        suggestions = []

        for query, count in self._query_freq.most_common(100):
            if partial in query:
                suggestions.append(SearchSuggestion(
                    text=query,
                    suggestion_type="popular",
                    score=min(count / 10, 0.8),  # 根据频率评分，最高0.8
                    metadata={"search_count": count},
                ))

            if len(suggestions) >= limit:
                break

        return suggestions

    def _get_completion_suggestions(self, partial: str, limit: int) -> List[SearchSuggestion]:
        """基于前缀索引的自动补全"""
        suggestions = []

        if partial in self._prefix_index:
            matches = self._prefix_index[partial]
            for query in matches:
                count = self._query_freq.get(query, 1)
                suggestions.append(SearchSuggestion(
                    text=query,
                    suggestion_type="completion",
                    score=min(count / 5, 0.7),
                    metadata={"search_count": count},
                ))

        suggestions.sort(key=lambda s: s.score, reverse=True)
        return suggestions[:limit]

    def get_related_queries(self, query_text: str, limit: int = 10) -> List[SearchSuggestion]:
        """
        获取相关搜索

        基于共同词汇和搜索模式发现相关查询
        """
        with self._lock:
            suggestions = []
            words = self._extract_words(query_text)

            if not words:
                return suggestions

            # 找到包含相同词汇的其他查询
            query_scores: Dict[str, float] = defaultdict(float)

            for record in self._records.values():
                other_words = self._extract_words(record.query_text)
                if not other_words:
                    continue

                # 计算词汇重叠度
                common_words = set(words) & set(other_words)
                if common_words:
                    score = len(common_words) / max(len(words), len(other_words))
                    query_scores[record.query_text] += score

            # 排序并返回
            sorted_queries = sorted(
                query_scores.items(),
                key=lambda x: x[1],
                reverse=True
            )

            for query, score in sorted_queries[:limit]:
                if query != query_text:  # 排除自身
                    suggestions.append(SearchSuggestion(
                        text=query,
                        suggestion_type="related",
                        score=score,
                    ))

            return suggestions

    # ==================== 搜索分析 ====================

    def get_search_stats(self, user_id: str = "") -> Dict:
        """获取搜索统计"""
        with self._lock:
            if user_id:
                records = [
                    self._records[qid]
                    for qid in self._user_history.get(user_id, [])
                    if qid in self._records
                ]
            else:
                records = list(self._records.values())

            if not records:
                return {"total_searches": 0}

            total_time = sum(r.search_time_ms for r in records)
            total_results = sum(r.results_count for r in records)
            total_clicks = sum(len(r.clicked_results) for r in records)

            # 类型分布
            type_dist = defaultdict(int)
            for r in records:
                type_dist[r.search_type.value] += 1

            return {
                "total_searches": len(records),
                "avg_search_time_ms": round(total_time / len(records), 2),
                "avg_results_count": round(total_results / len(records), 2),
                "total_clicks": total_clicks,
                "click_through_rate": round(
                    sum(1 for r in records if r.clicked_results) / len(records) * 100, 2
                ),
                "search_type_distribution": dict(type_dist),
                "unique_queries": len(set(r.query_text for r in records)),
            }

    def get_trending_queries(self, hours: int = 24, limit: int = 10) -> List[Dict]:
        """
        获取趋势搜索（最近增长最快的）

        对比最近N小时和前N小时的搜索频率
        """
        with self._lock:
            now = time.time()
            recent_start = now - hours * 3600
            older_start = recent_start - hours * 3600

            recent_freq = Counter()
            older_freq = Counter()

            for record in self._records.values():
                if record.timestamp >= recent_start:
                    recent_freq[record.query_text] += 1
                elif record.timestamp >= older_start:
                    older_freq[record.query_text] += 1

            # 计算增长率
            trending = []
            for query, recent_count in recent_freq.most_common(50):
                older_count = older_freq.get(query, 0)
                if older_count == 0:
                    growth = float('inf') if recent_count > 1 else 0
                else:
                    growth = (recent_count - older_count) / older_count

                if growth > 0.5 or (older_count == 0 and recent_count > 2):
                    trending.append({
                        "query": query,
                        "recent_count": recent_count,
                        "older_count": older_count,
                        "growth_rate": round(growth, 2) if growth != float('inf') else "new",
                    })

            trending.sort(key=lambda x: x["recent_count"], reverse=True)
            return trending[:limit]

    # ==================== 工具方法 ====================

    def _normalize_query(self, query: str) -> str:
        """标准化查询"""
        return query.strip().lower()

    def _extract_words(self, text: str) -> List[str]:
        """提取词汇"""
        # 简单分词：按非字母数字分割
        words = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z0-9]{2,}', text.lower())
        # 过滤停用词
        stopwords = {'的', '了', '在', '是', '我', '有', '和', '就', '不', '人',
                     '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去',
                     '你', '会', '着', '没有', '看', '好', '自己', '这', 'the',
                     'is', 'and', 'to', 'of', 'a', 'in', 'for', 'with'}
        return [w for w in words if w not in stopwords and len(w) >= 2]

    def _cleanup_old_records(self):
        """清理旧记录"""
        if len(self._records) <= self._max_history:
            return

        # 按时间排序，保留最新的
        sorted_records = sorted(
            self._records.items(),
            key=lambda x: x[1].timestamp,
            reverse=True
        )

        keep_count = int(self._max_history * 0.8)  # 保留80%
        to_keep = set(qid for qid, _ in sorted_records[:keep_count])

        # 删除旧记录
        for qid in list(self._records.keys()):
            if qid not in to_keep:
                del self._records[qid]

        # 清理用户历史中的无效引用
        for user_id in self._user_history:
            self._user_history[user_id] = [
                qid for qid in self._user_history[user_id]
                if qid in self._records
            ]

    # ==================== 数据导出 ====================

    def export_history(self, user_id: str = "") -> Dict:
        """导出搜索历史"""
        with self._lock:
            records = self.get_history(user_id=user_id, limit=self._max_history)
            return {
                "records": [r.to_dict() for r in records],
                "stats": self.get_search_stats(user_id),
                "popular": self.get_popular_queries(limit=100),
            }

    def clear_history(self, user_id: str = "") -> int:
        """清空搜索历史"""
        with self._lock:
            if user_id:
                count = len(self._user_history.get(user_id, []))
                for qid in self._user_history[user_id]:
                    self._records.pop(qid, None)
                self._user_history[user_id] = []
                return count
            else:
                count = len(self._records)
                self._records.clear()
                self._user_history.clear()
                self._query_freq.clear()
                self._word_freq.clear()
                self._bigram_freq.clear()
                self._prefix_index.clear()
                return count

    def get_summary(self) -> Dict:
        """获取管理器摘要"""
        with self._lock:
            return {
                "total_records": len(self._records),
                "unique_users": len(self._user_history),
                "unique_queries": len(self._query_freq),
                "total_vocab": len(self._word_freq),
            }


# ==================== 全局单例 ====================

_global_search_history: Optional[SearchHistoryManager] = None
_global_search_history_lock = threading.Lock()


def get_search_history() -> SearchHistoryManager:
    """获取全局搜索历史管理器实例"""
    global _global_search_history
    if _global_search_history is None:
        with _global_search_history_lock:
            if _global_search_history is None:
                _global_search_history = SearchHistoryManager()
    return _global_search_history
