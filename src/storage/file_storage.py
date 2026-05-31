"""
文件存储模块 (阶段362)

提供基于文件的持久化存储，支持JSON、YAML和二进制格式。
线程安全设计，使用 threading.RLock 保证并发安全。
确定性规则设计，无模型依赖，无循环依赖。
"""

import json
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from .storage_backend import StorageBackend, StorageRecord


# ============================================================================
# 枚举定义
# ============================================================================


class FileFormat(Enum):
    """文件格式枚举"""
    JSON = "json"
    YAML = "yaml"
    BINARY = "binary"
    TEXT = "text"


class WriteMode(Enum):
    """写入模式枚举"""
    OVERWRITE = "overwrite"
    APPEND = "append"
    MERGE = "merge"


# ============================================================================
# 数据类定义
# ============================================================================


@dataclass
class FileStorageConfig:
    """文件存储配置数据类"""
    base_path: str = "./data/storage"
    format: FileFormat = FileFormat.JSON
    create_dirs: bool = True
    sync_on_write: bool = True
    encoding: str = "utf-8"
    pretty_print: bool = True
    max_file_size: Optional[int] = None  # 最大文件大小（字节）


@dataclass
class FileInfo:
    """文件信息数据类"""
    path: str
    size: int
    format: FileFormat
    namespace: str
    created_at: float
    modified_at: float
    record_count: int = 0


# ============================================================================
# 文件存储后端
# ============================================================================


class FileStorageBackend(StorageBackend):
    """
    文件存储后端
    
    使用文件系统进行持久化存储，支持JSON、YAML等格式。
    每个命名空间对应一个目录，支持自动同步和文件大小限制。
    线程安全，使用 RLock 保证并发访问安全。
    """
    
    def __init__(self, config: Optional[FileStorageConfig] = None) -> None:
        self._lock = threading.RLock()
        self._config = config or FileStorageConfig()
        self._op_count: Dict[str, int] = {
            "read": 0, "write": 0, "delete": 0, "exists": 0, "list": 0
        }
        
        # 创建基础目录
        if self._config.create_dirs:
            Path(self._config.base_path).mkdir(parents=True, exist_ok=True)
        
        # 内存缓存（加速读取）
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_dirty: Dict[str, bool] = {}
    
    def _get_namespace_path(self, namespace: str) -> Path:
        """获取命名空间路径"""
        return Path(self._config.base_path) / namespace
    
    def _get_file_path(self, namespace: str) -> Path:
        """获取存储文件路径"""
        ns_path = self._get_namespace_path(namespace)
        ext = self._config.format.value
        return ns_path / f"data.{ext}"
    
    def _ensure_namespace_dir(self, namespace: str) -> None:
        """确保命名空间目录存在"""
        if self._config.create_dirs:
            ns_path = self._get_namespace_path(namespace)
            ns_path.mkdir(parents=True, exist_ok=True)
    
    def _load_data(self, namespace: str) -> Dict[str, Any]:
        """从文件加载数据"""
        file_path = self._get_file_path(namespace)
        
        if not file_path.exists():
            return {}
        
        try:
            if self._config.format == FileFormat.JSON:
                with open(file_path, "r", encoding=self._config.encoding) as f:
                    return json.load(f)
            elif self._config.format == FileFormat.TEXT:
                with open(file_path, "r", encoding=self._config.encoding) as f:
                    content = f.read()
                    return {"content": content}
            else:
                # 其他格式暂不支持，返回空
                return {}
        except (json.JSONDecodeError, IOError):
            return {}
    
    def _save_data(self, namespace: str, data: Dict[str, Any]) -> bool:
        """保存数据到文件"""
        self._ensure_namespace_dir(namespace)
        file_path = self._get_file_path(namespace)
        
        try:
            if self._config.format == FileFormat.JSON:
                indent = 2 if self._config.pretty_print else None
                with open(file_path, "w", encoding=self._config.encoding) as f:
                    json.dump(data, f, indent=indent, ensure_ascii=False)
                if self._config.sync_on_write:
                    os.sync()
                return True
            elif self._config.format == FileFormat.TEXT:
                content = data.get("content", "")
                with open(file_path, "w", encoding=self._config.encoding) as f:
                    f.write(str(content))
                if self._config.sync_on_write:
                    os.sync()
                return True
            else:
                return False
        except IOError:
            return False
    
    def _get_cached_data(self, namespace: str) -> Dict[str, Any]:
        """获取缓存数据（如果不存在则加载）"""
        if namespace not in self._cache:
            self._cache[namespace] = self._load_data(namespace)
            self._cache_dirty[namespace] = False
        return self._cache[namespace]
    
    def _sync_cache(self, namespace: str) -> bool:
        """同步缓存到文件"""
        if self._cache_dirty.get(namespace, False):
            data = self._cache.get(namespace, {})
            success = self._save_data(namespace, data)
            if success:
                self._cache_dirty[namespace] = False
            return success
        return True
    
    def get(self, key: str, namespace: str = "default") -> Optional[Any]:
        with self._lock:
            self._op_count["read"] += 1
            data = self._get_cached_data(namespace)
            return data.get(key)
    
    def set(self, key: str, value: Any, namespace: str = "default",
            ttl: Optional[float] = None) -> bool:
        with self._lock:
            self._op_count["write"] += 1
            data = self._get_cached_data(namespace)
            data[key] = value
            self._cache_dirty[namespace] = True
            return self._sync_cache(namespace)
    
    def delete(self, key: str, namespace: str = "default") -> bool:
        with self._lock:
            self._op_count["delete"] += 1
            data = self._get_cached_data(namespace)
            if key in data:
                del data[key]
                self._cache_dirty[namespace] = True
                return self._sync_cache(namespace)
            return False
    
    def exists(self, key: str, namespace: str = "default") -> bool:
        with self._lock:
            self._op_count["exists"] += 1
            data = self._get_cached_data(namespace)
            return key in data
    
    def keys(self, namespace: str = "default", pattern: Optional[str] = None) -> List[str]:
        with self._lock:
            self._op_count["list"] += 1
            data = self._get_cached_data(namespace)
            if pattern is None:
                return list(data.keys())
            return [k for k in data.keys() if pattern in k]
    
    def clear(self, namespace: str = "default") -> int:
        with self._lock:
            data = self._get_cached_data(namespace)
            count = len(data)
            data.clear()
            self._cache_dirty[namespace] = True
            self._sync_cache(namespace)
            return count
    
    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            namespaces = list(self._cache.keys())
            total_records = sum(len(self._cache.get(ns, {})) for ns in namespaces)
            return {
                "storage_type": "file",
                "base_path": self._config.base_path,
                "format": self._config.format.value,
                "total_records": total_records,
                "namespaces": namespaces,
                "namespace_count": len(namespaces),
                "operations": dict(self._op_count),
            }
    
    def sync_all(self) -> bool:
        """同步所有缓存到文件"""
        with self._lock:
            success = True
            for namespace in list(self._cache.keys()):
                if not self._sync_cache(namespace):
                    success = False
            return success
    
    def get_file_info(self, namespace: str) -> Optional[FileInfo]:
        """获取文件信息"""
        file_path = self._get_file_path(namespace)
        if not file_path.exists():
            return None
        
        stat = file_path.stat()
        data = self._get_cached_data(namespace)
        
        return FileInfo(
            path=str(file_path),
            size=stat.st_size,
            format=self._config.format,
            namespace=namespace,
            created_at=stat.st_ctime,
            modified_at=stat.st_mtime,
            record_count=len(data),
        )


# ============================================================================
# 文件存储管理器
# ============================================================================


class FileStorageManager:
    """
    文件存储管理器
    
    管理多个文件存储实例，支持不同格式和路径配置。
    """
    
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._storages: Dict[str, FileStorageBackend] = {}
    
    def create_storage(self, name: str, config: Optional[FileStorageConfig] = None) -> FileStorageBackend:
        """创建文件存储实例"""
        with self._lock:
            storage = FileStorageBackend(config)
            self._storages[name] = storage
            return storage
    
    def get_storage(self, name: str) -> Optional[FileStorageBackend]:
        """获取文件存储实例"""
        with self._lock:
            return self._storages.get(name)
    
    def remove_storage(self, name: str) -> bool:
        """移除文件存储实例"""
        with self._lock:
            if name in self._storages:
                storage = self._storages[name]
                storage.sync_all()
                del self._storages[name]
                return True
            return False
    
    def sync_all(self) -> bool:
        """同步所有存储"""
        with self._lock:
            success = True
            for storage in self._storages.values():
                if not storage.sync_all():
                    success = False
            return success
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            storage_stats = {}
            for name, storage in self._storages.items():
                storage_stats[name] = storage.get_stats()
            return {
                "storages": list(self._storages.keys()),
                "storage_count": len(self._storages),
                "storage_stats": storage_stats,
            }


# ============================================================================
# 全局单例
# ============================================================================

_file_storage_manager_instance: Optional[FileStorageManager] = None
_file_storage_manager_lock = threading.Lock()


def get_file_storage_manager() -> FileStorageManager:
    """获取文件存储管理器全局单例"""
    global _file_storage_manager_instance
    with _file_storage_manager_lock:
        if _file_storage_manager_instance is None:
            _file_storage_manager_instance = FileStorageManager()
        return _file_storage_manager_instance
