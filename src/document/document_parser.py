"""
文档解析器模块 (阶段371)

提供多格式文档解析功能，支持文本、Markdown、JSON、YAML等格式。
线程安全设计，使用 threading.RLock 保证并发安全。
确定性规则设计，无模型依赖，无循环依赖。
"""

import json
import re
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


# ============================================================================
# 枚举定义
# ============================================================================


class DocumentFormat(Enum):
    """文档格式枚举"""
    PLAIN = "plain"
    MARKDOWN = "markdown"
    JSON = "json"
    YAML = "yaml"
    HTML = "html"
    XML = "xml"
    CSV = "csv"


class ParseStatus(Enum):
    """解析状态枚举"""
    PENDING = "pending"
    PARSING = "parsing"
    SUCCESS = "success"
    FAILED = "failed"


# ============================================================================
# 数据类定义
# ============================================================================


@dataclass
class DocumentMetadata:
    """文档元数据数据类"""
    title: str = ""
    author: str = ""
    created_at: float = field(default_factory=time.time)
    modified_at: float = field(default_factory=time.time)
    format: DocumentFormat = DocumentFormat.PLAIN
    encoding: str = "utf-8"
    size: int = 0
    tags: List[str] = field(default_factory=list)
    custom: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedDocument:
    """解析后的文档数据类"""
    content: str = ""
    metadata: DocumentMetadata = field(default_factory=DocumentMetadata)
    sections: List[Dict[str, Any]] = field(default_factory=list)
    links: List[str] = field(default_factory=list)
    headings: List[Dict[str, Any]] = field(default_factory=list)
    status: ParseStatus = ParseStatus.PENDING
    error: Optional[str] = None


@dataclass
class ParseResult:
    """解析结果数据类"""
    success: bool
    document: Optional[ParsedDocument] = None
    error: Optional[str] = None
    duration: float = 0.0


# ============================================================================
# 解析器基类
# ============================================================================


class DocumentParserBase(ABC):
    """文档解析器基类"""
    
    @abstractmethod
    def parse(self, content: str) -> ParsedDocument:
        """解析文档内容"""
        pass
    
    @abstractmethod
    def supports(self, format: DocumentFormat) -> bool:
        """是否支持指定格式"""
        pass


# ============================================================================
# 具体解析器实现
# ============================================================================


class PlainTextParser(DocumentParserBase):
    """纯文本解析器"""
    
    def parse(self, content: str) -> ParsedDocument:
        doc = ParsedDocument(
            content=content,
            metadata=DocumentMetadata(format=DocumentFormat.PLAIN),
            status=ParseStatus.SUCCESS,
        )
        
        # 简单分节（按空行）
        sections = []
        current_section = []
        
        for line in content.split('\n'):
            if line.strip() == '':
                if current_section:
                    sections.append({
                        'type': 'paragraph',
                        'content': '\n'.join(current_section),
                    })
                    current_section = []
            else:
                current_section.append(line)
        
        if current_section:
            sections.append({
                'type': 'paragraph',
                'content': '\n'.join(current_section),
            })
        
        doc.sections = sections
        return doc
    
    def supports(self, format: DocumentFormat) -> bool:
        return format == DocumentFormat.PLAIN


class MarkdownParser(DocumentParserBase):
    """Markdown解析器"""
    
    # 标题正则
    HEADING_PATTERN = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
    # 链接正则
    LINK_PATTERN = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
    # 代码块正则
    CODE_BLOCK_PATTERN = re.compile(r'```(\w+)?\n(.*?)```', re.DOTALL)
    
    def parse(self, content: str) -> ParsedDocument:
        doc = ParsedDocument(
            content=content,
            metadata=DocumentMetadata(format=DocumentFormat.MARKDOWN),
            status=ParseStatus.SUCCESS,
        )
        
        # 提取标题
        headings = []
        for match in self.HEADING_PATTERN.finditer(content):
            level = len(match.group(1))
            text = match.group(2).strip()
            headings.append({
                'level': level,
                'text': text,
            })
        doc.headings = headings
        
        # 提取链接
        links = []
        for match in self.LINK_PATTERN.finditer(content):
            links.append(match.group(2))
        doc.links = list(set(links))
        
        # 提取代码块
        sections = []
        for match in self.CODE_BLOCK_PATTERN.finditer(content):
            language = match.group(1) or "text"
            code = match.group(2)
            sections.append({
                'type': 'code',
                'language': language,
                'content': code,
            })
        
        doc.sections = sections
        
        # 提取第一个H1作为标题
        if headings:
            h1 = [h for h in headings if h['level'] == 1]
            if h1:
                doc.metadata.title = h1[0]['text']
        
        return doc
    
    def supports(self, format: DocumentFormat) -> bool:
        return format == DocumentFormat.MARKDOWN


class JSONParser(DocumentParserBase):
    """JSON解析器"""
    
    def parse(self, content: str) -> ParsedDocument:
        doc = ParsedDocument(
            metadata=DocumentMetadata(format=DocumentFormat.JSON),
            status=ParseStatus.PARSING,
        )
        
        try:
            data = json.loads(content)
            doc.content = json.dumps(data, indent=2, ensure_ascii=False)
            doc.sections = self._extract_sections(data)
            doc.status = ParseStatus.SUCCESS
        except json.JSONDecodeError as e:
            doc.status = ParseStatus.FAILED
            doc.error = str(e)
        
        return doc
    
    def _extract_sections(self, data: Any, path: str = "") -> List[Dict[str, Any]]:
        """递归提取JSON结构"""
        sections = []
        
        if isinstance(data, dict):
            for key, value in data.items():
                current_path = f"{path}.{key}" if path else key
                if isinstance(value, (dict, list)):
                    sections.extend(self._extract_sections(value, current_path))
                else:
                    sections.append({
                        'type': 'field',
                        'path': current_path,
                        'key': key,
                        'value': value,
                    })
        elif isinstance(data, list):
            for i, item in enumerate(data):
                current_path = f"{path}[{i}]"
                sections.extend(self._extract_sections(item, current_path))
        
        return sections
    
    def supports(self, format: DocumentFormat) -> bool:
        return format == DocumentFormat.JSON


# ============================================================================
# 文档解析管理器
# ============================================================================


class DocumentParserManager:
    """
    文档解析管理器
    
    管理多个解析器，提供统一的文档解析接口。
    线程安全，使用 RLock 保证并发访问安全。
    """
    
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._parsers: Dict[DocumentFormat, DocumentParserBase] = {}
        self._parse_count: int = 0
        self._error_count: int = 0
        
        # 注册默认解析器
        self._register_default_parsers()
    
    def _register_default_parsers(self) -> None:
        """注册默认解析器"""
        self.register_parser(DocumentFormat.PLAIN, PlainTextParser())
        self.register_parser(DocumentFormat.MARKDOWN, MarkdownParser())
        self.register_parser(DocumentFormat.JSON, JSONParser())
    
    def register_parser(self, format: DocumentFormat, parser: DocumentParserBase) -> None:
        """注册解析器"""
        with self._lock:
            self._parsers[format] = parser
    
    def get_parser(self, format: DocumentFormat) -> Optional[DocumentParserBase]:
        """获取解析器"""
        with self._lock:
            return self._parsers.get(format)
    
    def parse(self, content: str, format: DocumentFormat) -> ParseResult:
        """
        解析文档
        
        Args:
            content: 文档内容
            format: 文档格式
            
        Returns:
            解析结果
        """
        start_time = time.time()
        
        with self._lock:
            self._parse_count += 1
            parser = self._parsers.get(format)
        
        if parser is None:
            self._error_count += 1
            return ParseResult(
                success=False,
                error=f"No parser available for format: {format.value}",
                duration=time.time() - start_time,
            )
        
        try:
            document = parser.parse(content)
            duration = time.time() - start_time
            
            if document.status == ParseStatus.SUCCESS:
                return ParseResult(
                    success=True,
                    document=document,
                    duration=duration,
                )
            else:
                self._error_count += 1
                return ParseResult(
                    success=False,
                    document=document,
                    error=document.error,
                    duration=duration,
                )
        
        except Exception as e:
            self._error_count += 1
            return ParseResult(
                success=False,
                error=str(e),
                duration=time.time() - start_time,
            )
    
    def parse_file(self, file_path: Union[str, Path]) -> ParseResult:
        """
        解析文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            解析结果
        """
        path = Path(file_path)
        
        # 根据扩展名推断格式
        ext = path.suffix.lower()
        format_map = {
            '.txt': DocumentFormat.PLAIN,
            '.md': DocumentFormat.MARKDOWN,
            '.json': DocumentFormat.JSON,
            '.yaml': DocumentFormat.YAML,
            '.yml': DocumentFormat.YAML,
            '.html': DocumentFormat.HTML,
            '.xml': DocumentFormat.XML,
            '.csv': DocumentFormat.CSV,
        }
        
        format = format_map.get(ext, DocumentFormat.PLAIN)
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            return self.parse(content, format)
        except IOError as e:
            return ParseResult(
                success=False,
                error=str(e),
            )
    
    def get_supported_formats(self) -> List[DocumentFormat]:
        """获取支持的格式列表"""
        with self._lock:
            return list(self._parsers.keys())
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                "total_parses": self._parse_count,
                "error_count": self._error_count,
                "supported_formats": [f.value for f in self._parsers.keys()],
                "parser_count": len(self._parsers),
            }


# ============================================================================
# 全局单例
# ============================================================================

_document_parser_manager_instance: Optional[DocumentParserManager] = None
_document_parser_manager_lock = threading.Lock()


def get_document_parser_manager() -> DocumentParserManager:
    """获取文档解析管理器全局单例"""
    global _document_parser_manager_instance
    with _document_parser_manager_lock:
        if _document_parser_manager_instance is None:
            _document_parser_manager_instance = DocumentParserManager()
        return _document_parser_manager_instance
