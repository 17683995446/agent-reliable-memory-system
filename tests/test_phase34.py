#!/usr/bin/env python3
"""
第34阶段验证测试 - 文档与知识管理模块 (阶段371-375)

覆盖模块：
- 阶段371: DocumentParser - 文档解析器
- 阶段372: KnowledgeExtractor - 知识提取器
- 阶段373: DocumentIndexer - 文档索引器
- 阶段374: KnowledgeBase - 知识库管理
- 阶段375: DocumentVersion - 文档版本控制
"""

import sys
import os
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from document.document_parser import (
    DocumentParserManager, DocumentParserBase, PlainTextParser, MarkdownParser, JSONParser,
    ParsedDocument, DocumentMetadata, ParseResult,
    DocumentFormat, ParseStatus, get_document_parser_manager,
)
from document.knowledge_extractor import (
    KnowledgeExtractor, Entity, Relation, KnowledgeTriple, ExtractionResult,
    EntityType, RelationType, ExtractionStatus, get_knowledge_extractor,
)
from document.document_indexer import (
    DocumentIndexer, IndexEntry, SearchResult, SearchQuery,
    IndexType, MatchType, get_document_indexer,
)
from document.knowledge_base import (
    KnowledgeBase, KnowledgeBaseManager, KnowledgeItem, KnowledgeQuery, KnowledgeQueryResult,
    KnowledgeType, QueryType, get_knowledge_base_manager,
)
from document.document_version import (
    DocumentVersionController, DocumentVersion, VersionDiff, VersionHistory,
    VersionStatus, ChangeType, get_document_version_controller,
)


# ============================================================
# 阶段371: DocumentParser 测试
# ============================================================

class TestPlainTextParser(unittest.TestCase):
    """纯文本解析器测试"""

    def test_parse_simple(self):
        parser = PlainTextParser()
        doc = parser.parse("Hello world\n\nThis is a test.")
        self.assertEqual(doc.status, ParseStatus.SUCCESS)
        self.assertEqual(len(doc.sections), 2)

    def test_supports(self):
        parser = PlainTextParser()
        self.assertTrue(parser.supports(DocumentFormat.PLAIN))
        self.assertFalse(parser.supports(DocumentFormat.MARKDOWN))


class TestMarkdownParser(unittest.TestCase):
    """Markdown解析器测试"""

    def test_parse_headings(self):
        parser = MarkdownParser()
        doc = parser.parse("# Title\n## Section\nContent")
        self.assertEqual(len(doc.headings), 2)
        self.assertEqual(doc.headings[0]['text'], 'Title')

    def test_parse_links(self):
        parser = MarkdownParser()
        doc = parser.parse("[link](http://example.com)")
        self.assertIn('http://example.com', doc.links)

    def test_parse_code_blocks(self):
        parser = MarkdownParser()
        doc = parser.parse("```python\nprint('hello')\n```")
        self.assertEqual(len(doc.sections), 1)
        self.assertEqual(doc.sections[0]['type'], 'code')


class TestJSONParser(unittest.TestCase):
    """JSON解析器测试"""

    def test_parse_valid(self):
        parser = JSONParser()
        doc = parser.parse('{"name": "test", "value": 123}')
        self.assertEqual(doc.status, ParseStatus.SUCCESS)
        self.assertTrue(len(doc.sections) > 0)

    def test_parse_invalid(self):
        parser = JSONParser()
        doc = parser.parse('{"invalid json')
        self.assertEqual(doc.status, ParseStatus.FAILED)


class TestDocumentParserManager(unittest.TestCase):
    """文档解析管理器测试"""

    def setUp(self):
        self.manager = DocumentParserManager()

    def test_parse_plain(self):
        result = self.manager.parse("Hello world", DocumentFormat.PLAIN)
        self.assertTrue(result.success)

    def test_parse_markdown(self):
        result = self.manager.parse("# Title", DocumentFormat.MARKDOWN)
        self.assertTrue(result.success)

    def test_parse_json(self):
        result = self.manager.parse('{"key": "value"}', DocumentFormat.JSON)
        self.assertTrue(result.success)

    def test_get_supported_formats(self):
        formats = self.manager.get_supported_formats()
        self.assertIn(DocumentFormat.PLAIN, formats)

    def test_get_stats(self):
        self.manager.parse("test", DocumentFormat.PLAIN)
        stats = self.manager.get_stats()
        self.assertGreater(stats["total_parses"], 0)

    def test_global_singleton(self):
        m1 = get_document_parser_manager()
        m2 = get_document_parser_manager()
        self.assertIs(m1, m2)


# ============================================================
# 阶段372: KnowledgeExtractor 测试
# ============================================================

class TestKnowledgeExtractor(unittest.TestCase):
    """知识提取器测试"""

    def setUp(self):
        self.extractor = KnowledgeExtractor()

    def test_extract_entities(self):
        text = "Contact us at test@example.com or visit https://example.com"
        entities = self.extractor.extract_entities(text)
        self.assertTrue(any(e.type == EntityType.EMAIL for e in entities))
        self.assertTrue(any(e.type == EntityType.URL for e in entities))

    def test_extract_keywords(self):
        text = "Python is a programming language. Python is popular."
        keywords = self.extractor.extract_keywords(text, top_k=3)
        self.assertIn('python', keywords)

    def test_extract_triples(self):
        text = "Python is a programming language. It has many libraries."
        triples = self.extractor.extract_triples(text)
        self.assertTrue(len(triples) > 0)

    def test_extract(self):
        result = self.extractor.extract("Python is great. Contact: test@example.com")
        self.assertEqual(result.status, ExtractionStatus.SUCCESS)
        self.assertTrue(len(result.entities) > 0)

    def test_add_entity_pattern(self):
        self.extractor.add_entity_pattern(EntityType.KEYWORD, r'\bPython\b')
        entities = self.extractor.extract_entities("I love Python")
        self.assertTrue(any(e.text == 'Python' for e in entities))

    def test_get_stats(self):
        self.extractor.extract("test")
        stats = self.extractor.get_stats()
        self.assertEqual(stats["extraction_count"], 1)

    def test_global_singleton(self):
        e1 = get_knowledge_extractor()
        e2 = get_knowledge_extractor()
        self.assertIs(e1, e2)


# ============================================================
# 阶段373: DocumentIndexer 测试
# ============================================================

class TestDocumentIndexer(unittest.TestCase):
    """文档索引器测试"""

    def setUp(self):
        self.indexer = DocumentIndexer()

    def test_add_document(self):
        result = self.indexer.add_document("doc1", "Hello world this is a test")
        self.assertTrue(result)
        self.assertEqual(self.indexer.get_document_count(), 1)

    def test_search(self):
        self.indexer.add_document("doc1", "Python programming language")
        self.indexer.add_document("doc2", "Java programming language")
        results = self.indexer.search("python")
        self.assertTrue(len(results) > 0)

    def test_prefix_search(self):
        self.indexer.add_document("doc1", "programming")
        matches = self.indexer.prefix_search("prog")
        self.assertIn("programming", matches)

    def test_remove_document(self):
        self.indexer.add_document("doc1", "test content")
        result = self.indexer.remove_document("doc1")
        self.assertTrue(result)
        self.assertEqual(self.indexer.get_document_count(), 0)

    def test_get_term_info(self):
        self.indexer.add_document("doc1", "hello world")
        info = self.indexer.get_term_info("hello")
        self.assertIsNotNone(info)

    def test_clear(self):
        self.indexer.add_document("doc1", "test")
        self.indexer.clear()
        self.assertEqual(self.indexer.get_document_count(), 0)

    def test_get_stats(self):
        self.indexer.add_document("doc1", "hello world")
        stats = self.indexer.get_stats()
        self.assertEqual(stats["document_count"], 1)

    def test_global_singleton(self):
        i1 = get_document_indexer()
        i2 = get_document_indexer()
        self.assertIs(i1, i2)


# ============================================================
# 阶段374: KnowledgeBase 测试
# ============================================================

class TestKnowledgeBase(unittest.TestCase):
    """知识库测试"""

    def setUp(self):
        self.kb = KnowledgeBase("test")

    def test_add_and_get(self):
        item = KnowledgeItem(
            id="item1",
            content="Python is a language",
            type=KnowledgeType.CONCEPT,
            entities=["Python"],
        )
        result = self.kb.add(item)
        self.assertTrue(result)
        
        retrieved = self.kb.get("item1")
        self.assertEqual(retrieved.content, "Python is a language")

    def test_update(self):
        item = KnowledgeItem(id="item1", content="old", type=KnowledgeType.FACT)
        self.kb.add(item)
        result = self.kb.update("item1", content="new")
        self.assertTrue(result)
        self.assertEqual(self.kb.get("item1").content, "new")

    def test_delete(self):
        item = KnowledgeItem(id="item1", content="test", type=KnowledgeType.FACT)
        self.kb.add(item)
        result = self.kb.delete("item1")
        self.assertTrue(result)
        self.assertIsNone(self.kb.get("item1"))

    def test_query(self):
        item = KnowledgeItem(
            id="item1",
            content="Python programming",
            type=KnowledgeType.CONCEPT,
        )
        self.kb.add(item)
        
        query = KnowledgeQuery(query="Python", query_type=QueryType.EXACT)
        result = self.kb.query(query)
        self.assertTrue(len(result.items) > 0)

    def test_search_by_entity(self):
        item = KnowledgeItem(
            id="item1",
            content="test",
            type=KnowledgeType.FACT,
            entities=["Python"],
        )
        self.kb.add(item)
        results = self.kb.search_by_entity("Python")
        self.assertEqual(len(results), 1)

    def test_get_related_items(self):
        item1 = KnowledgeItem(id="item1", content="a", type=KnowledgeType.FACT, entities=["Python"])
        item2 = KnowledgeItem(id="item2", content="b", type=KnowledgeType.FACT, entities=["Python"])
        self.kb.add(item1)
        self.kb.add(item2)
        
        related = self.kb.get_related_items("item1")
        self.assertEqual(len(related), 1)

    def test_merge_items(self):
        item1 = KnowledgeItem(id="item1", content="source", type=KnowledgeType.FACT)
        item2 = KnowledgeItem(id="item2", content="target", type=KnowledgeType.FACT)
        self.kb.add(item1)
        self.kb.add(item2)
        
        result = self.kb.merge_items("item1", "item2")
        self.assertTrue(result)
        self.assertIsNone(self.kb.get("item1"))

    def test_get_stats(self):
        item = KnowledgeItem(id="item1", content="test", type=KnowledgeType.FACT)
        self.kb.add(item)
        stats = self.kb.get_stats()
        self.assertEqual(stats["total_items"], 1)


class TestKnowledgeBaseManager(unittest.TestCase):
    """知识库管理器测试"""

    def setUp(self):
        self.manager = KnowledgeBaseManager()

    def test_create_and_get(self):
        kb = self.manager.create("mykb")
        self.assertIsNotNone(kb)
        self.assertIs(self.manager.get("mykb"), kb)

    def test_delete(self):
        self.manager.create("mykb")
        result = self.manager.delete("mykb")
        self.assertTrue(result)
        self.assertIsNone(self.manager.get("mykb"))

    def test_list_bases(self):
        self.manager.create("kb1")
        self.manager.create("kb2")
        bases = self.manager.list_bases()
        self.assertEqual(len(bases), 2)

    def test_global_singleton(self):
        m1 = get_knowledge_base_manager()
        m2 = get_knowledge_base_manager()
        self.assertIs(m1, m2)


# ============================================================
# 阶段375: DocumentVersion 测试
# ============================================================

class TestDocumentVersionController(unittest.TestCase):
    """文档版本控制器测试"""

    def setUp(self):
        self.controller = DocumentVersionController()

    def test_create_version(self):
        version = self.controller.create_version("doc1", "Hello world", "user1", "Initial")
        self.assertIsNotNone(version.version_id)
        self.assertEqual(version.doc_id, "doc1")

    def test_get_version(self):
        version = self.controller.create_version("doc1", "content", "user", "msg")
        retrieved = self.controller.get_version(version.version_id)
        self.assertEqual(retrieved.content, "content")

    def test_get_current_version(self):
        v1 = self.controller.create_version("doc1", "v1", "user", "first")
        v2 = self.controller.create_version("doc1", "v2", "user", "second")
        current = self.controller.get_current_version("doc1")
        self.assertEqual(current.content, "v2")

    def test_get_history(self):
        self.controller.create_version("doc1", "v1", "user", "first")
        self.controller.create_version("doc1", "v2", "user", "second")
        history = self.controller.get_history("doc1")
        self.assertEqual(len(history), 2)

    def test_rollback(self):
        v1 = self.controller.create_version("doc1", "original", "user", "first")
        self.controller.create_version("doc1", "modified", "user", "second")
        
        rolled = self.controller.rollback("doc1", v1.version_id)
        self.assertIsNotNone(rolled)
        self.assertEqual(rolled.content, "original")

    def test_compare_versions(self):
        v1 = self.controller.create_version("doc1", "line1\nline2", "user", "first")
        v2 = self.controller.create_version("doc1", "line1\nmodified", "user", "second")
        
        diff = self.controller.compare_versions(v1.version_id, v2.version_id)
        self.assertTrue(diff.modified_lines > 0)

    def test_archive_version(self):
        version = self.controller.create_version("doc1", "content", "user", "msg")
        result = self.controller.archive_version(version.version_id)
        self.assertTrue(result)
        self.assertEqual(version.status, VersionStatus.ARCHIVED)

    def test_delete_version(self):
        version = self.controller.create_version("doc1", "content", "user", "msg")
        result = self.controller.delete_version(version.version_id)
        self.assertTrue(result)
        self.assertEqual(version.status, VersionStatus.DELETED)

    def test_restore_version(self):
        version = self.controller.create_version("doc1", "content", "user", "msg")
        self.controller.delete_version(version.version_id)
        result = self.controller.restore_version(version.version_id)
        self.assertTrue(result)
        self.assertEqual(version.status, VersionStatus.ACTIVE)

    def test_get_version_lineage(self):
        v1 = self.controller.create_version("doc1", "v1", "user", "first")
        v2 = self.controller.create_version("doc1", "v2", "user", "second")
        
        lineage = self.controller.get_version_lineage(v2.version_id)
        self.assertEqual(len(lineage), 2)
        self.assertEqual(lineage[0], v1.version_id)

    def test_get_stats(self):
        self.controller.create_version("doc1", "content", "user", "msg")
        stats = self.controller.get_stats()
        self.assertEqual(stats["total_versions"], 1)

    def test_global_singleton(self):
        c1 = get_document_version_controller()
        c2 = get_document_version_controller()
        self.assertIs(c1, c2)


# ============================================================
# 数据结构测试
# ============================================================

class TestDataStructures(unittest.TestCase):
    """数据结构基础测试"""

    def test_document_format_enum(self):
        self.assertEqual(DocumentFormat.MARKDOWN.value, "markdown")
        self.assertEqual(DocumentFormat.JSON.value, "json")

    def test_parse_status_enum(self):
        self.assertEqual(ParseStatus.SUCCESS.value, "success")
        self.assertEqual(ParseStatus.FAILED.value, "failed")

    def test_entity_type_enum(self):
        self.assertEqual(EntityType.EMAIL.value, "email")
        self.assertEqual(EntityType.URL.value, "url")

    def test_knowledge_type_enum(self):
        self.assertEqual(KnowledgeType.FACT.value, "fact")
        self.assertEqual(KnowledgeType.CONCEPT.value, "concept")

    def test_version_status_enum(self):
        self.assertEqual(VersionStatus.ACTIVE.value, "active")
        self.assertEqual(VersionStatus.ARCHIVED.value, "archived")

    def test_change_type_enum(self):
        self.assertEqual(ChangeType.ADDED.value, "added")
        self.assertEqual(ChangeType.DELETED.value, "deleted")

    def test_document_metadata(self):
        meta = DocumentMetadata(title="Test", author="User")
        self.assertEqual(meta.title, "Test")
        self.assertEqual(meta.author, "User")

    def test_knowledge_item(self):
        item = KnowledgeItem(
            id="item1",
            content="test content",
            type=KnowledgeType.FACT,
        )
        self.assertEqual(item.id, "item1")

    def test_document_version(self):
        version = DocumentVersion(
            version_id="v1",
            doc_id="doc1",
            content="test",
            checksum="abc123",
        )
        self.assertEqual(version.version_id, "v1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
