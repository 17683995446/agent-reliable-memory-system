#!/usr/bin/env python3
"""
搜索增强模块 - 阶段143-145
多条件组合查询、过滤、排序
"""

import re
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum


class FilterOperator(Enum):
    """过滤操作符"""
    EQ = "eq"           # 等于
    NE = "ne"           # 不等于
    CONTAINS = "contains"   # 包含
    NOT_CONTAINS = "not_contains"  # 不包含
    STARTS_WITH = "starts_with"    # 开头是
    ENDS_WITH = "ends_with"        # 结尾是
    GT = "gt"           # 大于
    GTE = "gte"         # 大于等于
    LT = "lt"           # 小于
    LTE = "lte"         # 小于等于
    REGEX = "regex"     # 正则匹配


class SortOrder(Enum):
    """排序方向"""
    ASC = "asc"
    DESC = "desc"


@dataclass
class SearchFilter:
    """搜索过滤条件"""
    field: str
    operator: FilterOperator
    value: Any


@dataclass
class SearchQuery:
    """搜索查询"""
    text: str = ""
    filters: List[SearchFilter] = field(default_factory=list)
    sort_by: str = "score"
    sort_order: SortOrder = SortOrder.DESC
    offset: int = 0
    limit: int = 20
    task_id: str = ""
    user_id: Optional[str] = None


@dataclass
class SearchResult:
    """搜索结果"""
    items: List[Dict[str, Any]]
    total: int
    offset: int
    limit: int
    query_time_ms: float


class SearchEnhancer:
    """
    搜索增强器

    在基础召回之上提供：
    - 多条件过滤
    - 自定义排序
    - 分页
    - 结果高亮
    """

    def __init__(self, memory_system):
        self.memory_system = memory_system

    def search(self, query: SearchQuery) -> SearchResult:
        """
        执行增强搜索

        Args:
            query: 搜索查询对象

        Returns:
            搜索结果
        """
        start_time = time.time()

        # 1. 基础召回（扩大范围用于过滤）
        recall_top_k = max(query.limit * 5, 50)
        raw_results = self.memory_system.recall(
            query=query.text,
            task_id=query.task_id,
            top_k=recall_top_k,
            user_id=query.user_id
        )

        # 2. 应用过滤
        filtered = self._apply_filters(raw_results, query.filters)

        # 3. 排序
        sorted_results = self._apply_sort(filtered, query.sort_by, query.sort_order)

        # 4. 分页
        total = len(sorted_results)
        paged = sorted_results[query.offset:query.offset + query.limit]

        # 5. 高亮
        highlighted = self._highlight(paged, query.text)

        query_time = (time.time() - start_time) * 1000

        return SearchResult(
            items=highlighted,
            total=total,
            offset=query.offset,
            limit=query.limit,
            query_time_ms=round(query_time, 2),
        )

    def _apply_filters(
        self,
        items: List[Dict[str, Any]],
        filters: List[SearchFilter]
    ) -> List[Dict[str, Any]]:
        """应用过滤条件"""
        if not filters:
            return items

        result = items
        for f in filters:
            result = [item for item in result if self._match_filter(item, f)]
        return result

    def _match_filter(self, item: Dict[str, Any], f: SearchFilter) -> bool:
        """单项过滤匹配"""
        field_value = item.get(f.field, "")

        if f.operator == FilterOperator.EQ:
            return str(field_value) == str(f.value)
        elif f.operator == FilterOperator.NE:
            return str(field_value) != str(f.value)
        elif f.operator == FilterOperator.CONTAINS:
            return str(f.value).lower() in str(field_value).lower()
        elif f.operator == FilterOperator.NOT_CONTAINS:
            return str(f.value).lower() not in str(field_value).lower()
        elif f.operator == FilterOperator.STARTS_WITH:
            return str(field_value).lower().startswith(str(f.value).lower())
        elif f.operator == FilterOperator.ENDS_WITH:
            return str(field_value).lower().endswith(str(f.value).lower())
        elif f.operator == FilterOperator.GT:
            try:
                return float(field_value) > float(f.value)
            except (ValueError, TypeError):
                return False
        elif f.operator == FilterOperator.GTE:
            try:
                return float(field_value) >= float(f.value)
            except (ValueError, TypeError):
                return False
        elif f.operator == FilterOperator.LT:
            try:
                return float(field_value) < float(f.value)
            except (ValueError, TypeError):
                return False
        elif f.operator == FilterOperator.LTE:
            try:
                return float(field_value) <= float(f.value)
            except (ValueError, TypeError):
                return False
        elif f.operator == FilterOperator.REGEX:
            try:
                return bool(re.search(str(f.value), str(field_value)))
            except re.error:
                return False

        return True

    def _apply_sort(
        self,
        items: List[Dict[str, Any]],
        sort_by: str,
        sort_order: SortOrder
    ) -> List[Dict[str, Any]]:
        """应用排序"""
        if not sort_by:
            return items

        reverse = sort_order == SortOrder.DESC
        return sorted(
            items,
            key=lambda x: x.get(sort_by, 0),
            reverse=reverse
        )

    def _highlight(
        self,
        items: List[Dict[str, Any]],
        query_text: str
    ) -> List[Dict[str, Any]]:
        """搜索结果高亮"""
        if not query_text:
            return items

        keywords = query_text.split()
        highlighted = []

        for item in items:
            content = str(item.get("content", ""))
            highlighted_content = content

            for kw in keywords:
                if kw and kw in highlighted_content:
                    highlighted_content = highlighted_content.replace(
                        kw, f"**{kw}**"
                    )

            result = dict(item)
            result["content_highlighted"] = highlighted_content
            highlighted.append(result)

        return highlighted

    def quick_search(
        self,
        text: str,
        task_id: str,
        top_k: int = 10,
        user_id: Optional[str] = None
    ) -> SearchResult:
        """便捷搜索方法"""
        query = SearchQuery(
            text=text,
            task_id=task_id,
            limit=top_k,
            user_id=user_id
        )
        return self.search(query)

    def filtered_search(
        self,
        text: str,
        task_id: str,
        content_contains: Optional[str] = None,
        min_score: float = 0.0,
        top_k: int = 10
    ) -> SearchResult:
        """带常用过滤条件的便捷搜索"""
        filters = []
        if content_contains:
            filters.append(SearchFilter(
                field="content",
                operator=FilterOperator.CONTAINS,
                value=content_contains
            ))
        if min_score > 0:
            filters.append(SearchFilter(
                field="score",
                operator=FilterOperator.GTE,
                value=min_score
            ))

        query = SearchQuery(
            text=text,
            task_id=task_id,
            filters=filters,
            limit=top_k
        )
        return self.search(query)
