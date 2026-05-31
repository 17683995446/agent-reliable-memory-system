"""
存储抽象层模块 (阶段361)

提供统一的存储接口抽象，支持多种存储后端（内存、文件、数据库等）。
线程安全设计，使用 threading.RLock 保证并发安全。
确定性规则设计，无模型依赖，无循环依赖。
"""

import threading
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Iterator


# ============================================================================
# 枚举定义
# ============================================================================


class StorageType(Enum):
    """存储类型枚举"""
    MEMORY = "memory"
    FILE = "file"
    DATABASE = "database"
    REMOTE = "remote"


class StorageStatus(Enum):
    """存储状态枚举"""
    ACTIVE = "active"
    READONLY = "readonly"
    CLOSED = "closed"
    ERROR = "error"


class OperationType(Enum):
    """操作类型枚举"""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    EXISTS = "exists"
    LIST = "list"


# ============================================================================
# 数据类定义
# ============================================================================


@dataclass
class StorageConfig:
    """存储配置数据类"""
    storage_type: StorageType = StorageType.MEMORY
    namespace: str = "default"
    readonly: bool = False
    ttl: Optional[float] = None  # 生存时间（秒）
    max_size: Optional[int] = None  # 最大存储条目数
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StorageRecord:
    """存储记录数据类"""
    key: str
    value: Any
    namespace: str = "default"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OperationResult:
    """操作结果数据类"""
    success: bool
    operation: OperationType
    key: Optional[str] = None
    value: Any = None
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


# ============================================================================
# 抽象存储后端
# ============================================================================


class StorageBackend(ABC):
    """
    存储后端抽象基类
    
    定义所有存储后端必须实现的接口。支持CRUD操作、命名空间隔离、
    TTL过期和批量操作。
    """
    
    @abstractmethod
    def get(self, key: str, namespace: str = "default") -> Optional[Any]:
        """获取存储值"""
        pass
    
    @abstractmethod
    def set(self, key: str, value: Any, namespace: str = "default",
            ttl: Optional[float] = None) -> bool:
        """设置存储值"""
        pass
    
    @abstractmethod
    def delete(self, key: str, namespace: str = "default") -> bool:
        """删除存储值"""
        pass
    
    @abstractmethod
    def exists(self, key: str, namespace: str = "default") -> bool:
        """检查键是否存在"""
        pass
    
    @abstractmethod
    def keys(self, namespace: str = "default", pattern: Optional[str] = None) -> List[str]:
        """列出所有键"""
        pass
    
    @abstractmethod
    def clear(self, namespace: str = "default") -> int:
        """清空命名空间"""
        pass
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        pass


# ============================================================================
# 内存存储后端
# ============================================================================


class MemoryStorageBackend(StorageBackend):
    """
    内存存储后端
    
    使用内存字典存储数据，支持命名空间隔离和TTL过期。
    线程安全，使用 RLock 保证并发访问安全。
    """
    
    def __init__(self, config: Optional[StorageConfig] = None) -> None:
        self._lock = threading.RLock()
        self._config = config or StorageConfig()
        self._data: Dict[str, Dict[str, StorageRecord]] = {}
        self._op_count: Dict[str, int] = {
            "read": 0, "write": 0, "delete": 0, "exists": 0, "list": 0
        }
    
    def _make_key(self, key: str, namespace: str) -> str:
        """生成带命名空间的键"""
        return f"{namespace}:{key}"
    
    def _get_namespace_data(self, namespace: str) -> Dict[str, StorageRecord]:
        """获取命名空间数据"""
        if namespace not in self._data:
            self._data[namespace] = {}
        return self._data[namespace]
    
    def _is_expired(self, record: StorageRecord) -> bool:
        """检查记录是否过期"""
        if record.expires_at is None:
            return False
        return time.time() > record.expires_at
    
    def get(self, key: str, namespace: str = "default") -> Optional[Any]:
        with self._lock:
            self._op_count["read"] += 1
            ns_data = self._get_namespace_data(namespace)
            record = ns_data.get(key)
            if record is None:
                return None
            if self._is_expired(record):
                del ns_data[key]
                return None
            return record.value
    
    def set(self, key: str, value: Any, namespace: str = "default",
            ttl: Optional[float] = None) -> bool:
        with self._lock:
            self._op_count["write"] += 1
            ns_data = self._get_namespace_data(namespace)
            now = time.time()
            expires_at = now + ttl if ttl is not None else None
            
            if key in ns_data:
                record = ns_data[key]
                record.value = value
                record.updated_at = now
                record.expires_at = expires_at
            else:
                record = StorageRecord(
                    key=key,
                    value=value,
                    namespace=namespace,
                    created_at=now,
                    updated_at=now,
                    expires_at=expires_at,
                )
                ns_data[key] = record
            return True
    
    def delete(self, key: str, namespace: str = "default") -> bool:
        with self._lock:
            self._op_count["delete"] += 1
            ns_data = self._get_namespace_data(namespace)
            if key in ns_data:
                del ns_data[key]
                return True
            return False
    
    def exists(self, key: str, namespace: str = "default") -> bool:
        with self._lock:
            self._op_count["exists"] += 1
            ns_data = self._get_namespace_data(namespace)
            record = ns_data.get(key)
            if record is None:
                return False
            if self._is_expired(record):
                del ns_data[key]
                return False
            return True
    
    def keys(self, namespace: str = "default", pattern: Optional[str] = None) -> List[str]:
        with self._lock:
            self._op_count["list"] += 1
            ns_data = self._get_namespace_data(namespace)
            result = []
            expired_keys = []
            for key, record in ns_data.items():
                if self._is_expired(record):
                    expired_keys.append(key)
                    continue
                if pattern is None or pattern in key:
                    result.append(key)
            # 清理过期记录
            for key in expired_keys:
                del ns_data[key]
            return result
    
    def clear(self, namespace: str = "default") -> int:
        with self._lock:
            ns_data = self._get_namespace_data(namespace)
            count = len(ns_data)
            ns_data.clear()
            return count
    
    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            total_records = sum(len(ns) for ns in self._data.values())
            namespaces = list(self._data.keys())
            return {
                "storage_type": self._config.storage_type.value,
                "total_records": total_records,
                "namespaces": namespaces,
                "namespace_count": len(namespaces),
                "operations": dict(self._op_count),
            }
    
    def get_record(self, key: str, namespace: str = "default") -> Optional[StorageRecord]:
        """获取完整记录（含元数据）"""
        with self._lock:
            ns_data = self._get_namespace_data(namespace)
            record = ns_data.get(key)
            if record is None:
                return None
            if self._is_expired(record):
                del ns_data[key]
                return None
            return record


# ============================================================================
# 存储管理器
# ============================================================================


class StorageManager:
    """
    存储管理器
    
    管理多个存储后端，提供统一的存储访问接口。
    支持多命名空间、后端切换和操作统计。
    """
    
    def __init__(self, default_backend: Optional[StorageBackend] = None) -> None:
        self._lock = threading.RLock()
        self._backends: Dict[str, StorageBackend] = {}
        self._default_namespace = "default"
        
        if default_backend is not None:
            self._backends["default"] = default_backend
    
    def register_backend(self, name: str, backend: StorageBackend) -> None:
        """注册存储后端"""
        with self._lock:
            self._backends[name] = backend
    
    def get_backend(self, name: str = "default") -> Optional[StorageBackend]:
        """获取存储后端"""
        with self._lock:
            return self._backends.get(name)
    
    def remove_backend(self, name: str) -> bool:
        """移除存储后端"""
        with self._lock:
            if name in self._backends:
                del self._backends[name]
                return True
            return False
    
    def get(self, key: str, namespace: str = "default",
            backend: str = "default") -> Optional[Any]:
        """获取值"""
        b = self.get_backend(backend)
        if b is None:
            return None
        return b.get(key, namespace)
    
    def set(self, key: str, value: Any, namespace: str = "default",
            backend: str = "default", ttl: Optional[float] = None) -> bool:
        """设置值"""
        b = self.get_backend(backend)
        if b is None:
            return False
        return b.set(key, value, namespace, ttl)
    
    def delete(self, key: str, namespace: str = "default",
               backend: str = "default") -> bool:
        """删除值"""
        b = self.get_backend(backend)
        if b is None:
            return False
        return b.delete(key, namespace)
    
    def exists(self, key: str, namespace: str = "default",
               backend: str = "default") -> bool:
        """检查存在"""
        b = self.get_backend(backend)
        if b is None:
            return False
        return b.exists(key, namespace)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            backend_stats = {}
            for name, backend in self._backends.items():
                backend_stats[name] = backend.get_stats()
            return {
                "backends": list(self._backends.keys()),
                "backend_count": len(self._backends),
                "backend_stats": backend_stats,
            }


# ============================================================================
# 全局单例
# ============================================================================

_storage_manager_instance: Optional[StorageManager] = None
_storage_manager_lock = threading.Lock()


def get_storage_manager() -> StorageManager:
    """获取存储管理器全局单例"""
    global _storage_manager_instance
    with _storage_manager_lock:
        if _storage_manager_instance is None:
            default_backend = MemoryStorageBackend()
            _storage_manager_instance = StorageManager(default_backend)
        return _storage_manager_instance
