"""
文档版本控制模块 (阶段375)

提供文档版本管理、历史记录和差异对比功能。
线程安全设计，使用 threading.RLock 保证并发安全。
确定性规则设计，无模型依赖，无循环依赖。
"""

import difflib
import hashlib
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ============================================================================
# 枚举定义
# ============================================================================


class VersionStatus(Enum):
    """版本状态枚举"""
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


class ChangeType(Enum):
    """变更类型枚举"""
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


# ============================================================================
# 数据类定义
# ============================================================================


@dataclass
class DocumentVersion:
    """文档版本数据类"""
    version_id: str
    doc_id: str
    content: str
    checksum: str
    author: str = ""
    message: str = ""
    timestamp: float = field(default_factory=time.time)
    parent_version: Optional[str] = None
    status: VersionStatus = VersionStatus.ACTIVE
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VersionDiff:
    """版本差异数据类"""
    old_version: str
    new_version: str
    changes: List[Dict[str, Any]] = field(default_factory=list)
    additions: int = 0
    deletions: int = 0
    modified_lines: int = 0


@dataclass
class VersionHistory:
    """版本历史数据类"""
    doc_id: str
    versions: List[DocumentVersion] = field(default_factory=list)
    current_version: Optional[str] = None


# ============================================================================
# 文档版本控制器
# ============================================================================


class DocumentVersionController:
    """
    文档版本控制器
    
    管理文档的版本历史，支持版本创建、回滚和差异对比。
    线程安全，使用 RLock 保证并发访问安全。
    """
    
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._versions: Dict[str, DocumentVersion] = {}  # version_id -> DocumentVersion
        self._doc_history: Dict[str, List[str]] = {}     # doc_id -> [version_ids]
        self._current_version: Dict[str, str] = {}       # doc_id -> current_version_id
        self._version_counter: int = 0
    
    def _generate_version_id(self) -> str:
        """生成版本ID"""
        with self._lock:
            self._version_counter += 1
            return f"v{self._version_counter}_{int(time.time())}"
    
    def _calculate_checksum(self, content: str) -> str:
        """计算内容校验和"""
        return hashlib.md5(content.encode('utf-8')).hexdigest()[:16]
    
    def create_version(self, doc_id: str, content: str,
                       author: str = "", message: str = "") -> DocumentVersion:
        """
        创建新版本
        
        Args:
            doc_id: 文档ID
            content: 文档内容
            author: 作者
            message: 版本信息
            
        Returns:
            新版本对象
        """
        with self._lock:
            version_id = self._generate_version_id()
            
            # 获取父版本
            parent_version = self._current_version.get(doc_id)
            
            version = DocumentVersion(
                version_id=version_id,
                doc_id=doc_id,
                content=content,
                checksum=self._calculate_checksum(content),
                author=author,
                message=message,
                parent_version=parent_version,
            )
            
            self._versions[version_id] = version
            
            # 更新文档历史
            if doc_id not in self._doc_history:
                self._doc_history[doc_id] = []
            self._doc_history[doc_id].append(version_id)
            
            # 更新当前版本
            self._current_version[doc_id] = version_id
            
            return version
    
    def get_version(self, version_id: str) -> Optional[DocumentVersion]:
        """
        获取指定版本
        
        Args:
            version_id: 版本ID
            
        Returns:
            版本对象或None
        """
        with self._lock:
            return self._versions.get(version_id)
    
    def get_current_version(self, doc_id: str) -> Optional[DocumentVersion]:
        """
        获取文档当前版本
        
        Args:
            doc_id: 文档ID
            
        Returns:
            当前版本对象或None
        """
        with self._lock:
            version_id = self._current_version.get(doc_id)
            if version_id:
                return self._versions.get(version_id)
            return None
    
    def get_history(self, doc_id: str) -> List[DocumentVersion]:
        """
        获取文档版本历史
        
        Args:
            doc_id: 文档ID
            
        Returns:
            版本列表
        """
        with self._lock:
            version_ids = self._doc_history.get(doc_id, [])
            return [self._versions[vid] for vid in version_ids if vid in self._versions]
    
    def rollback(self, doc_id: str, version_id: str) -> Optional[DocumentVersion]:
        """
        回滚到指定版本
        
        Args:
            doc_id: 文档ID
            version_id: 目标版本ID
            
        Returns:
            新版本对象或None
        """
        with self._lock:
            if version_id not in self._versions:
                return None
            
            target = self._versions[version_id]
            
            # 创建新版本，内容为回滚目标的内容
            return self.create_version(
                doc_id=doc_id,
                content=target.content,
                author="system",
                message=f"Rollback to {version_id}",
            )
    
    def compare_versions(self, old_version_id: str,
                         new_version_id: str) -> VersionDiff:
        """
        比较两个版本
        
        Args:
            old_version_id: 旧版本ID
            new_version_id: 新版本ID
            
        Returns:
            版本差异
        """
        with self._lock:
            old_version = self._versions.get(old_version_id)
            new_version = self._versions.get(new_version_id)
            
            if not old_version or not new_version:
                return VersionDiff(
                    old_version=old_version_id,
                    new_version=new_version_id,
                    changes=[],
                    additions=0,
                    deletions=0,
                    modified_lines=0,
                )
            
            old_lines = old_version.content.splitlines(keepends=True)
            new_lines = new_version.content.splitlines(keepends=True)
            
            diff = list(difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"v{old_version_id}",
                tofile=f"v{new_version_id}",
            ))
            
            # 统计变更
            additions = 0
            deletions = 0
            changes = []
            
            for line in diff:
                if line.startswith('+') and not line.startswith('+++'):
                    additions += 1
                    changes.append({"type": ChangeType.ADDED.value, "line": line[1:]})
                elif line.startswith('-') and not line.startswith('---'):
                    deletions += 1
                    changes.append({"type": ChangeType.DELETED.value, "line": line[1:]})
            
            return VersionDiff(
                old_version=old_version_id,
                new_version=new_version_id,
                changes=changes,
                additions=additions,
                deletions=deletions,
                modified_lines=additions + deletions,
            )
    
    def archive_version(self, version_id: str) -> bool:
        """
        归档版本
        
        Args:
            version_id: 版本ID
            
        Returns:
            是否成功归档
        """
        with self._lock:
            if version_id not in self._versions:
                return False
            
            self._versions[version_id].status = VersionStatus.ARCHIVED
            return True
    
    def delete_version(self, version_id: str, soft: bool = True) -> bool:
        """
        删除版本
        
        Args:
            version_id: 版本ID
            soft: 是否软删除
            
        Returns:
            是否成功删除
        """
        with self._lock:
            if version_id not in self._versions:
                return False
            
            if soft:
                self._versions[version_id].status = VersionStatus.DELETED
            else:
                del self._versions[version_id]
            
            return True
    
    def restore_version(self, version_id: str) -> bool:
        """
        恢复已删除/归档的版本
        
        Args:
            version_id: 版本ID
            
        Returns:
            是否成功恢复
        """
        with self._lock:
            if version_id not in self._versions:
                return False
            
            self._versions[version_id].status = VersionStatus.ACTIVE
            return True
    
    def get_version_count(self, doc_id: str) -> int:
        """获取文档版本数量"""
        with self._lock:
            return len(self._doc_history.get(doc_id, []))
    
    def get_version_lineage(self, version_id: str) -> List[str]:
        """
        获取版本血缘（从根到当前）
        
        Args:
            version_id: 版本ID
            
        Returns:
            版本ID列表
        """
        with self._lock:
            lineage = []
            current = version_id
            
            while current:
                lineage.append(current)
                version = self._versions.get(current)
                if version:
                    current = version.parent_version
                else:
                    break
            
            return list(reversed(lineage))
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            status_counts = {}
            for version in self._versions.values():
                status = version.status.value
                status_counts[status] = status_counts.get(status, 0) + 1
            
            return {
                "total_versions": len(self._versions),
                "total_documents": len(self._doc_history),
                "by_status": status_counts,
                "version_counter": self._version_counter,
            }


# ============================================================================
# 全局单例
# ============================================================================

_document_version_controller_instance: Optional[DocumentVersionController] = None
_document_version_controller_lock = threading.Lock()


def get_document_version_controller() -> DocumentVersionController:
    """获取文档版本控制器全局单例"""
    global _document_version_controller_instance
    with _document_version_controller_lock:
        if _document_version_controller_instance is None:
            _document_version_controller_instance = DocumentVersionController()
        return _document_version_controller_instance
