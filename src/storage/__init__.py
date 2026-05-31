"""
存储与持久化模块 (阶段361-365)

提供统一的存储抽象层、文件存储、缓存层、事务管理和迁移管理功能。
"""

from .storage_backend import (
    StorageBackend,
    MemoryStorageBackend,
    StorageManager,
    StorageConfig,
    StorageRecord,
    OperationResult,
    StorageType,
    StorageStatus,
    OperationType,
    get_storage_manager,
)
from .file_storage import (
    FileStorageBackend,
    FileStorageManager,
    FileStorageConfig,
    FileInfo,
    FileFormat,
    WriteMode,
    get_file_storage_manager,
)
from .storage_cache import (
    StorageCache,
    CacheEntry,
    CacheStats,
    CacheConfig,
    CachePolicy,
    EvictionPolicy,
    cached,
    get_storage_cache,
    init_storage_cache,
)
from .transaction_manager import (
    TransactionManager,
    TransactionContext,
    Transaction,
    TransactionOperation,
    TransactionResult,
    TransactionState,
    IsolationLevel,
    get_transaction_manager,
    init_transaction_manager,
)
from .migration_manager import (
    MigrationManager,
    MigrationBuilder,
    Migration,
    MigrationRecord,
    MigrationResult,
    MigrationStatus,
    MigrationDirection,
    get_migration_manager,
    init_migration_manager,
)

__all__ = [
    # storage_backend
    "StorageBackend",
    "MemoryStorageBackend",
    "StorageManager",
    "StorageConfig",
    "StorageRecord",
    "OperationResult",
    "StorageType",
    "StorageStatus",
    "OperationType",
    "get_storage_manager",
    # file_storage
    "FileStorageBackend",
    "FileStorageManager",
    "FileStorageConfig",
    "FileInfo",
    "FileFormat",
    "WriteMode",
    "get_file_storage_manager",
    # storage_cache
    "StorageCache",
    "CacheEntry",
    "CacheStats",
    "CacheConfig",
    "CachePolicy",
    "EvictionPolicy",
    "cached",
    "get_storage_cache",
    "init_storage_cache",
    # transaction_manager
    "TransactionManager",
    "TransactionContext",
    "Transaction",
    "TransactionOperation",
    "TransactionResult",
    "TransactionState",
    "IsolationLevel",
    "get_transaction_manager",
    "init_transaction_manager",
    # migration_manager
    "MigrationManager",
    "MigrationBuilder",
    "Migration",
    "MigrationRecord",
    "MigrationResult",
    "MigrationStatus",
    "MigrationDirection",
    "get_migration_manager",
    "init_migration_manager",
]
