"""
高级功能与优化模块 - 智能化能力扩展

本模块提供高级智能化功能，包括：
- 智能推荐器: 内容推荐、协同过滤、个性化
- 知识图谱构建器: 实体抽取、关系构建、图谱推理
- 语义搜索引擎: 语义理解、查询扩展、结果排序
- 智能摘要器: 文本摘要、关键句提取、主题建模
- 预测分析器: 趋势预测、异常检测、模式识别

遵循"图难于其易，为大于其细"原则，所有组件设计简洁、确定性强。
"""

from .recommendation_engine import RecommendationEngine, get_recommendation_engine
from .knowledge_graph_builder import KnowledgeGraphBuilder, get_knowledge_graph_builder
from .semantic_search_engine import SemanticSearchEngine, get_semantic_search_engine
from .smart_summarizer import SmartSummarizer, get_smart_summarizer
from .predictive_analyzer import PredictiveAnalyzer, get_predictive_analyzer

__all__ = [
    'RecommendationEngine', 'get_recommendation_engine',
    'KnowledgeGraphBuilder', 'get_knowledge_graph_builder',
    'SemanticSearchEngine', 'get_semantic_search_engine',
    'SmartSummarizer', 'get_smart_summarizer',
    'PredictiveAnalyzer', 'get_predictive_analyzer',
]
