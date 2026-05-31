#!/usr/bin/env python3
"""
自然语言查询接口 - 阶段116-118
支持自然语言形式的记忆查询，无需精确关键词
"""

import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class QueryIntent(Enum):
    """查询意图类型"""
    SEARCH = "search"           # 搜索记忆
    RECALL = "recall"           # 召回相关记忆
    LIST = "list"               # 列出记忆
    WHEN = "when"               # 时间查询
    WHO = "who"                 # 主体查询
    WHAT = "what"               # 内容查询
    UNKNOWN = "unknown"         # 未知意图


@dataclass
class ParsedQuery:
    """解析后的查询"""
    intent: QueryIntent
    keywords: List[str]
    time_constraint: Optional[str] = None
    subject: Optional[str] = None
    original: str = ""


class NaturalLanguageQueryParser:
    """
    自然语言查询解析器
    
    将自然语言查询转换为结构化查询，无需用户记忆精确关键词
    """
    
    # 意图识别模式
    INTENT_PATTERNS = {
        QueryIntent.WHEN: [
            r"什么时候.*",
            r"何时.*",
            r".*是在.*时候",
            r".*的时间",
        ],
        QueryIntent.WHO: [
            r"谁.*",
            r".*是谁",
            r".*的人",
        ],
        QueryIntent.WHAT: [
            r"什么.*",
            r".*是什么",
            r".*的内容",
        ],
        QueryIntent.LIST: [
            r"列出.*",
            r"显示.*",
            r"查看.*",
            r"有哪些.*",
        ],
        QueryIntent.RECALL: [
            r"记得.*",
            r"回忆.*",
            r"关于.*",
            r".*相关的",
        ],
    }
    
    # 时间约束模式
    TIME_PATTERNS = {
        "today": r"今天|今日",
        "yesterday": r"昨天|昨日",
        "recent": r"最近|近期|前不久",
        "last_week": r"上周|上星期",
        "last_month": r"上个月|上月",
    }
    
    def __init__(self):
        self._compile_patterns()
    
    def _compile_patterns(self):
        """编译正则表达式"""
        self._intent_patterns = {
            intent: [re.compile(p) for p in patterns]
            for intent, patterns in self.INTENT_PATTERNS.items()
        }
        self._time_patterns = {
            key: re.compile(p) for key, p in self.TIME_PATTERNS.items()
        }
    
    def parse(self, query: str) -> ParsedQuery:
        """
        解析自然语言查询
        
        Args:
            query: 自然语言查询字符串
        
        Returns:
            解析后的结构化查询
        """
        query = query.strip()
        
        # 识别意图
        intent = self._detect_intent(query)
        
        # 提取时间约束
        time_constraint = self._extract_time(query)
        
        # 提取主体
        subject = self._extract_subject(query)
        
        # 提取关键词
        keywords = self._extract_keywords(query)
        
        return ParsedQuery(
            intent=intent,
            keywords=keywords,
            time_constraint=time_constraint,
            subject=subject,
            original=query
        )
    
    def _detect_intent(self, query: str) -> QueryIntent:
        """检测查询意图"""
        for intent, patterns in self._intent_patterns.items():
            for pattern in patterns:
                if pattern.match(query):
                    return intent
        return QueryIntent.SEARCH
    
    def _extract_time(self, query: str) -> Optional[str]:
        """提取时间约束"""
        for time_key, pattern in self._time_patterns.items():
            if pattern.search(query):
                return time_key
        return None
    
    def _extract_subject(self, query: str) -> Optional[str]:
        """提取主体（谁/什么）"""
        # 提取"关于XXX"、"XXX相关的"中的XXX
        patterns = [
            r"关于(.+?)的",
            r"(.+?)相关的",
            r"(.+?)的内容",
            r"(.+?)是什么",
        ]
        for pattern in patterns:
            match = re.search(pattern, query)
            if match:
                return match.group(1).strip()
        return None
    
    def _extract_keywords(self, query: str) -> List[str]:
        """提取关键词"""
        # 移除常见停用词
        stopwords = {"的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好", "自己", "这"}
        
        # 分词（简化版，按字符和常见词分割）
        words = []
        current = ""
        for char in query:
            if char in stopwords or char in "。？！，、；：""''（）【】":
                if current and len(current) > 1:
                    words.append(current)
                current = ""
            else:
                current += char
        if current and len(current) > 1:
            words.append(current)
        
        # 过滤并去重
        keywords = [w for w in words if w not in stopwords and len(w) >= 2]
        return list(dict.fromkeys(keywords))  # 保持顺序去重


class NaturalLanguageQueryEngine:
    """
    自然语言查询引擎
    
    整合解析器和召回引擎，提供自然语言查询能力
    """
    
    def __init__(self, memory_system):
        self.parser = NaturalLanguageQueryParser()
        self.memory_system = memory_system
    
    def query(self, nl_query: str, task_id: str, top_k: int = 5) -> Dict[str, Any]:
        """
        执行自然语言查询
        
        Args:
            nl_query: 自然语言查询
            task_id: 任务标识
            top_k: 返回结果数量
        
        Returns:
            查询结果，包含解析信息和召回结果
        """
        # 解析查询
        parsed = self.parser.parse(nl_query)
        
        # 根据意图选择查询策略
        if parsed.intent == QueryIntent.LIST:
            # 列出所有记忆
            results = self.memory_system.recall("", task_id=task_id, top_k=top_k)
        elif parsed.intent == QueryIntent.WHEN and parsed.subject:
            # 时间查询：搜索主体相关记忆
            results = self.memory_system.recall(parsed.subject, task_id=task_id, top_k=top_k)
        elif parsed.keywords:
            # 使用关键词召回
            query_str = " ".join(parsed.keywords[:3])  # 使用前3个关键词
            results = self.memory_system.recall(query_str, task_id=task_id, top_k=top_k)
        else:
            # 默认召回
            results = self.memory_system.recall(nl_query, task_id=task_id, top_k=top_k)
        
        return {
            "parsed": {
                "intent": parsed.intent.value,
                "keywords": parsed.keywords,
                "time_constraint": parsed.time_constraint,
                "subject": parsed.subject,
            },
            "results": results,
            "count": len(results),
        }
    
    def suggest_queries(self, partial: str) -> List[str]:
        """
        查询建议
        
        根据部分输入提供查询建议
        """
        suggestions = []
        
        # 常见查询模板
        templates = [
            "关于{keyword}的记忆",
            "{keyword}相关的内容",
            "列出所有{keyword}",
            "什么时候{keyword}",
            "{keyword}是什么",
        ]
        
        if partial:
            for template in templates:
                suggestion = template.format(keyword=partial)
                suggestions.append(suggestion)
        
        return suggestions[:5]


# 便捷函数
def create_nl_query_engine(memory_system):
    """创建自然语言查询引擎"""
    return NaturalLanguageQueryEngine(memory_system)
