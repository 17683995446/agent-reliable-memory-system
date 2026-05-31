"""
文档与知识管理模块 (阶段371-375)

提供文档解析、知识提取、全文检索、知识库管理和版本控制功能。
"""

from .document_parser import (
    DocumentParserManager,
    DocumentParserBase,
    PlainTextParser,
    MarkdownParser,
    JSONParser,
    ParsedDocument,
    DocumentMetadata,
    ParseResult,
    DocumentFormat,
    ParseStatus,
    get_document_parser_manager,
)
from .knowledge_extractor import (
    KnowledgeExtractor,
    Entity,
    Relation,
    KnowledgeTriple,
    ExtractionResult,
    EntityType,
    RelationType,
    ExtractionStatus,
    get_knowledge_extractor,
)
from .document_indexer import (
    DocumentIndexer,
    IndexEntry,
    SearchResult,
    SearchQuery,
    IndexType,
    MatchType,
    get_document_indexer,
)
from .knowledge_base import (
    KnowledgeBase,
    KnowledgeBaseManager,
    KnowledgeItem,
    KnowledgeQuery,
    KnowledgeQueryResult,
    KnowledgeType,
    QueryType,
    get_knowledge_base_manager,
)
from .document_version import (
    DocumentVersionController,
    DocumentVersion,
    VersionDiff,
    VersionHistory,
    VersionStatus,
    ChangeType,
    get_document_version_controller,
)

__all__ = [
    # document_parser
    "DocumentParserManager",
    "DocumentParserBase",
    "PlainTextParser",
    "MarkdownParser",
    "JSONParser",
    "ParsedDocument",
    "DocumentMetadata",
    "ParseResult",
    "DocumentFormat",
    "ParseStatus",
    "get_document_parser_manager",
    # knowledge_extractor
    "KnowledgeExtractor",
    "Entity",
    "Relation",
    "KnowledgeTriple",
    "ExtractionResult",
    "EntityType",
    "RelationType",
    "ExtractionStatus",
    "get_knowledge_extractor",
    # document_indexer
    "DocumentIndexer",
    "IndexEntry",
    "SearchResult",
    "SearchQuery",
    "IndexType",
    "MatchType",
    "get_document_indexer",
    # knowledge_base
    "KnowledgeBase",
    "KnowledgeBaseManager",
    "KnowledgeItem",
    "KnowledgeQuery",
    "KnowledgeQueryResult",
    "KnowledgeType",
    "QueryType",
    "get_knowledge_base_manager",
    # document_version
    "DocumentVersionController",
    "DocumentVersion",
    "VersionDiff",
    "VersionHistory",
    "VersionStatus",
    "ChangeType",
    "get_document_version_controller",
]
