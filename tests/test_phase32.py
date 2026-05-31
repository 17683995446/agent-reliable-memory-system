#!/usr/bin/env python3
"""
第32阶段验证测试 - 存储与持久化模块 (阶段361-365)

覆盖模块：
- 阶段361: StorageBackend - 存储抽象层/内存存储
- 阶段362: FileStorage - 文件存储（JSON/YAML/Binary）
- 阶段363: StorageCache - 存储缓存层（读写穿透）
- 阶段364: TransactionManager - 事务管理（ACID-like）
- 阶段365: MigrationManager - 迁移管理（版本演进）
"""

import sys
import os
import time
import shutil
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from storage.storage_backend import (
    StorageBackend, MemoryStorageBackend, StorageManager,
    StorageConfig, StorageRecord, OperationResult,
    StorageType, StorageStatus, OperationType,
    get_storage_manager,
)
from storage.file_storage import (
    FileStorageBackend, FileStorageManager, FileStorageConfig, FileInfo,
    FileFormat, WriteMode, get_file_storage_manager,
)
from storage.storage_cache import (
    StorageCache, CacheEntry, CacheStats, CacheConfig,
    CachePolicy, EvictionPolicy, cached,
    get_storage_cache, init_storage_cache,
)
from storage.transaction_manager import (
    TransactionManager, TransactionContext, Transaction, TransactionOperation,
    TransactionResult, TransactionState, IsolationLevel,
    get_transaction_manager, init_transaction_manager,
)
from storage.migration_manager import (
    MigrationManager, MigrationBuilder, Migration, MigrationRecord,
    MigrationResult, MigrationStatus, MigrationDirection,
    get_migration_manager, init_migration_manager,
)


# ============================================================
# 阶段361: StorageBackend 测试
# ============================================================

class TestMemoryStorageBackend(unittest.TestCase):
    """内存存储后端核心测试"""

    def setUp(self):
        self.storage = MemoryStorageBackend()

    def test_set_and_get(self):
        self.storage.set("key1", "value1")
        result = self.storage.get("key1")
        self.assertEqual(result, "value1")

    def test_get_nonexistent(self):
        result = self.storage.get("nonexistent")
        self.assertIsNone(result)

    def test_delete(self):
        self.storage.set("key1", "value1")
        self.assertTrue(self.storage.delete("key1"))
        self.assertIsNone(self.storage.get("key1"))
        self.assertFalse(self.storage.delete("nonexistent"))

    def test_exists(self):
        self.storage.set("key1", "value1")
        self.assertTrue(self.storage.exists("key1"))
        self.assertFalse(self.storage.exists("nonexistent"))

    def test_keys(self):
        self.storage.set("a", 1)
        self.storage.set("b", 2)
        self.storage.set("c", 3)
        keys = self.storage.keys()
        self.assertEqual(len(keys), 3)
        self.assertIn("a", keys)

    def test_keys_with_pattern(self):
        self.storage.set("user_1", "a")
        self.storage.set("user_2", "b")
        self.storage.set("item_1", "c")
        keys = self.storage.keys(pattern="user_")
        self.assertEqual(len(keys), 2)

    def test_clear(self):
        self.storage.set("a", 1)
        self.storage.set("b", 2)
        count = self.storage.clear()
        self.assertEqual(count, 2)
        self.assertEqual(len(self.storage.keys()), 0)

    def test_namespace_isolation(self):
        self.storage.set("key1", "ns1_value", namespace="ns1")
        self.storage.set("key1", "ns2_value", namespace="ns2")
        self.assertEqual(self.storage.get("key1", namespace="ns1"), "ns1_value")
        self.assertEqual(self.storage.get("key1", namespace="ns2"), "ns2_value")

    def test_ttl_expiration(self):
        self.storage.set("key1", "value1", ttl=0.1)
        self.assertEqual(self.storage.get("key1"), "value1")
        time.sleep(0.15)
        self.assertIsNone(self.storage.get("key1"))

    def test_stats(self):
        self.storage.set("a", 1)
        self.storage.get("a")
        stats = self.storage.get_stats()
        self.assertEqual(stats["total_records"], 1)
        self.assertEqual(stats["operations"]["write"], 1)
        self.assertEqual(stats["operations"]["read"], 1)

    def test_get_record(self):
        self.storage.set("key1", "value1")
        record = self.storage.get_record("key1")
        self.assertIsNotNone(record)
        self.assertEqual(record.key, "key1")
        self.assertEqual(record.value, "value1")


class TestStorageManager(unittest.TestCase):
    """存储管理器测试"""

    def setUp(self):
        self.manager = StorageManager()

    def test_register_backend(self):
        backend = MemoryStorageBackend()
        self.manager.register_backend("test", backend)
        retrieved = self.manager.get_backend("test")
        self.assertIs(retrieved, backend)

    def test_remove_backend(self):
        backend = MemoryStorageBackend()
        self.manager.register_backend("test", backend)
        self.assertTrue(self.manager.remove_backend("test"))
        self.assertFalse(self.manager.remove_backend("nonexistent"))

    def test_operations(self):
        backend = MemoryStorageBackend()
        self.manager.register_backend("default", backend)
        self.manager.set("key1", "value1")
        self.assertEqual(self.manager.get("key1"), "value1")
        self.assertTrue(self.manager.exists("key1"))
        self.assertTrue(self.manager.delete("key1"))

    def test_stats(self):
        backend = MemoryStorageBackend()
        self.manager.register_backend("default", backend)
        stats = self.manager.get_stats()
        self.assertEqual(stats["backend_count"], 1)


# ============================================================
# 阶段362: FileStorage 测试
# ============================================================

class TestFileStorageBackend(unittest.TestCase):
    """文件存储后端核心测试"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        config = FileStorageConfig(base_path=self.temp_dir, format=FileFormat.JSON)
        self.storage = FileStorageBackend(config)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_set_and_get(self):
        self.storage.set("key1", {"name": "test", "value": 123})
        result = self.storage.get("key1")
        self.assertEqual(result["name"], "test")
        self.assertEqual(result["value"], 123)

    def test_delete(self):
        self.storage.set("key1", "value1")
        self.assertTrue(self.storage.delete("key1"))
        self.assertIsNone(self.storage.get("key1"))

    def test_exists(self):
        self.storage.set("key1", "value1")
        self.assertTrue(self.storage.exists("key1"))
        self.assertFalse(self.storage.exists("nonexistent"))

    def test_keys(self):
        self.storage.set("a", 1)
        self.storage.set("b", 2)
        keys = self.storage.keys()
        self.assertEqual(len(keys), 2)

    def test_namespace_isolation(self):
        self.storage.set("key1", "ns1", namespace="ns1")
        self.storage.set("key1", "ns2", namespace="ns2")
        self.assertEqual(self.storage.get("key1", namespace="ns1"), "ns1")
        self.assertEqual(self.storage.get("key1", namespace="ns2"), "ns2")

    def test_clear(self):
        self.storage.set("a", 1)
        self.storage.set("b", 2)
        count = self.storage.clear()
        self.assertEqual(count, 2)

    def test_stats(self):
        self.storage.set("a", 1)
        stats = self.storage.get_stats()
        self.assertEqual(stats["total_records"], 1)
        self.assertEqual(stats["format"], "json")

    def test_file_info(self):
        self.storage.set("key1", "value1")
        info = self.storage.get_file_info("default")
        self.assertIsNotNone(info)
        self.assertEqual(info.format, FileFormat.JSON)
        self.assertEqual(info.record_count, 1)


class TestFileStorageManager(unittest.TestCase):
    """文件存储管理器测试"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.manager = FileStorageManager()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_storage(self):
        config = FileStorageConfig(base_path=self.temp_dir)
        storage = self.manager.create_storage("test", config)
        self.assertIsNotNone(storage)
        retrieved = self.manager.get_storage("test")
        self.assertIs(retrieved, storage)

    def test_remove_storage(self):
        config = FileStorageConfig(base_path=self.temp_dir)
        self.manager.create_storage("test", config)
        self.assertTrue(self.manager.remove_storage("test"))
        self.assertFalse(self.manager.remove_storage("nonexistent"))

    def test_stats(self):
        config = FileStorageConfig(base_path=self.temp_dir)
        self.manager.create_storage("test", config)
        stats = self.manager.get_stats()
        self.assertEqual(stats["storage_count"], 1)


# ============================================================
# 阶段363: StorageCache 测试
# ============================================================

class TestStorageCache(unittest.TestCase):
    """存储缓存核心测试"""

    def setUp(self):
        self.backend = MemoryStorageBackend()
        self.cache = StorageCache(self.backend, CacheConfig(max_size=100))

    def test_get_cache_hit(self):
        self.cache.set("key1", "value1")
        result = self.cache.get("key1")
        self.assertEqual(result, "value1")
        stats = self.cache.get_stats()
        self.assertEqual(stats["hits"], 1)

    def test_get_cache_miss(self):
        self.backend.set("key1", "value1")
        result = self.cache.get("key1")
        self.assertEqual(result, "value1")
        stats = self.cache.get_stats()
        self.assertEqual(stats["misses"], 1)

    def test_set_updates_cache(self):
        self.cache.set("key1", "value1")
        # 应该在缓存中
        self.assertEqual(self.cache.get("key1"), "value1")

    def test_delete_invalidates_cache(self):
        self.cache.set("key1", "value1")
        self.cache.delete("key1")
        self.assertIsNone(self.cache.get("key1"))

    def test_invalidate(self):
        # 先写入后端
        self.backend.set("key1", "value1")
        # 通过缓存读取（会缓存）
        self.cache.get("key1")
        # 使缓存失效
        self.cache.invalidate("key1")
        # 后端仍有数据
        self.assertEqual(self.backend.get("key1"), "value1")
        # 缓存已失效
        stats = self.cache.get_stats()
        self.assertEqual(stats["invalidations"], 1)

    def test_invalidate_all(self):
        self.cache.set("a", 1)
        self.cache.set("b", 2)
        count = self.cache.invalidate_all()
        self.assertEqual(count, 2)

    def test_eviction_lru(self):
        config = CacheConfig(max_size=3, eviction=EvictionPolicy.LRU)
        cache = StorageCache(self.backend, config)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache.set("d", 4)  # 应该淘汰 a
        stats = cache.get_stats()
        self.assertEqual(stats["evictions"], 1)

    def test_ttl_expiration(self):
        config = CacheConfig(default_ttl=0.1)
        cache = StorageCache(self.backend, config)
        cache.set("key1", "value1")
        self.assertEqual(cache.get("key1"), "value1")
        time.sleep(0.15)
        self.assertIsNone(cache.get("key1"))

    def test_clear(self):
        self.cache.set("a", 1)
        self.cache.set("b", 2)
        count = self.cache.clear()
        self.assertEqual(count, 2)

    def test_stats(self):
        self.cache.set("a", 1)
        self.cache.get("a")
        stats = self.cache.get_stats()
        self.assertEqual(stats["total_entries"], 1)
        self.assertEqual(stats["hits"], 1)


# ============================================================
# 阶段364: TransactionManager 测试
# ============================================================

class TestTransactionManager(unittest.TestCase):
    """事务管理器核心测试"""

    def setUp(self):
        self.backend = MemoryStorageBackend()
        self.manager = TransactionManager(self.backend)

    def test_begin_transaction(self):
        tx = self.manager.begin()
        self.assertIsNotNone(tx.id)
        self.assertEqual(tx.state, TransactionState.ACTIVE)

    def test_commit(self):
        tx = self.manager.begin()
        self.manager.set(tx.id, "key1", "value1")
        result = self.manager.commit(tx.id)
        self.assertTrue(result.success)
        self.assertEqual(self.backend.get("key1"), "value1")

    def test_abort(self):
        tx = self.manager.begin()
        self.manager.set(tx.id, "key1", "value1")
        result = self.manager.abort(tx.id)
        self.assertTrue(result.success)
        self.assertIsNone(self.backend.get("key1"))

    def test_multiple_operations(self):
        tx = self.manager.begin()
        self.manager.set(tx.id, "a", 1)
        self.manager.set(tx.id, "b", 2)
        self.manager.set(tx.id, "c", 3)
        result = self.manager.commit(tx.id)
        self.assertTrue(result.success)
        self.assertEqual(result.operations_count, 3)
        self.assertEqual(self.backend.get("a"), 1)
        self.assertEqual(self.backend.get("b"), 2)
        self.assertEqual(self.backend.get("c"), 3)

    def test_delete_in_transaction(self):
        self.backend.set("key1", "value1")
        tx = self.manager.begin()
        self.manager.delete(tx.id, "key1")
        result = self.manager.commit(tx.id)
        self.assertTrue(result.success)
        self.assertIsNone(self.backend.get("key1"))

    def test_rollback_on_failure(self):
        self.backend.set("key1", "original")
        tx = self.manager.begin()
        self.manager.set(tx.id, "key1", "modified")
        self.manager.abort(tx.id)
        # 应该回滚到原始值
        self.assertEqual(self.backend.get("key1"), "original")

    def test_get_transaction(self):
        tx = self.manager.begin()
        retrieved = self.manager.get_transaction(tx.id)
        self.assertEqual(retrieved.id, tx.id)

    def test_get_active_transactions(self):
        tx1 = self.manager.begin()
        tx2 = self.manager.begin()
        active = self.manager.get_active_transactions()
        self.assertEqual(len(active), 2)

    def test_stats(self):
        self.manager.begin()
        stats = self.manager.get_stats()
        self.assertEqual(stats["active_count"], 1)

    def test_execute_atomic(self):
        operations = [
            ("set", "a", 1, "default"),
            ("set", "b", 2, "default"),
            ("set", "c", 3, "default"),
        ]
        result = self.manager.execute(operations)
        self.assertTrue(result.success)
        self.assertEqual(result.operations_count, 3)


class TestTransactionContext(unittest.TestCase):
    """事务上下文管理器测试"""

    def setUp(self):
        self.backend = MemoryStorageBackend()
        self.manager = TransactionManager(self.backend)

    def test_context_commit(self):
        with TransactionContext(self.manager) as ctx:
            ctx.set("key1", "value1")
            ctx.set("key2", "value2")
        
        self.assertEqual(self.backend.get("key1"), "value1")
        self.assertEqual(self.backend.get("key2"), "value2")

    def test_context_rollback_on_exception(self):
        self.backend.set("key1", "original")
        
        try:
            with TransactionContext(self.manager) as ctx:
                ctx.set("key1", "modified")
                raise ValueError("Test error")
        except ValueError:
            pass
        
        # 应该回滚
        self.assertEqual(self.backend.get("key1"), "original")


# ============================================================
# 阶段365: MigrationManager 测试
# ============================================================

class TestMigrationManager(unittest.TestCase):
    """迁移管理器核心测试"""

    def setUp(self):
        self.backend = MemoryStorageBackend()
        self.manager = MigrationManager(self.backend)

    def test_register_migration(self):
        migration = Migration(
            version="v1.0",
            name="initial",
            up_func=lambda b: True,
        )
        self.assertTrue(self.manager.register(migration))
        self.assertFalse(self.manager.register(migration))  # 重复注册失败

    def test_unregister_migration(self):
        migration = Migration(
            version="v1.0",
            name="initial",
            up_func=lambda b: True,
        )
        self.manager.register(migration)
        self.assertTrue(self.manager.unregister("v1.0"))
        self.assertFalse(self.manager.unregister("v1.0"))

    def test_migrate_up(self):
        def up_func(backend):
            backend.set("key1", "value1")
            return True
        
        migration = Migration(
            version="v1.0",
            name="initial",
            up_func=up_func,
        )
        self.manager.register(migration)
        result = self.manager.migrate_up("v1.0")
        self.assertTrue(result.success)
        self.assertEqual(self.backend.get("key1"), "value1")

    def test_migrate_down(self):
        def up_func(backend):
            backend.set("key1", "value1")
            return True
        
        def down_func(backend):
            backend.delete("key1")
            return True
        
        migration = Migration(
            version="v1.0",
            name="initial",
            up_func=up_func,
            down_func=down_func,
        )
        self.manager.register(migration)
        self.manager.migrate_up("v1.0")
        result = self.manager.migrate_down("v1.0")
        self.assertTrue(result.success)
        self.assertIsNone(self.backend.get("key1"))

    def test_dependencies(self):
        migration1 = Migration(
            version="v1.0",
            name="first",
            up_func=lambda b: True,
        )
        migration2 = Migration(
            version="v1.1",
            name="second",
            up_func=lambda b: True,
            dependencies=["v1.0"],
        )
        self.manager.register(migration1)
        self.manager.register(migration2)
        
        # 先执行 v1.0
        result1 = self.manager.migrate_up("v1.0")
        self.assertTrue(result1.success)
        
        # 然后可以执行 v1.1
        result2 = self.manager.migrate_up("v1.1")
        self.assertTrue(result2.success)

    def test_dependency_not_satisfied(self):
        migration = Migration(
            version="v1.1",
            name="second",
            up_func=lambda b: True,
            dependencies=["v1.0"],
        )
        self.manager.register(migration)
        result = self.manager.migrate_up("v1.1")
        self.assertFalse(result.success)
        self.assertIn("Dependencies", result.error)

    def test_get_current_version(self):
        migration = Migration(
            version="v1.0",
            name="initial",
            up_func=lambda b: True,
        )
        self.manager.register(migration)
        self.manager.migrate_up("v1.0")
        version = self.manager.get_current_version()
        self.assertEqual(version, "v1.0")

    def test_get_history(self):
        migration = Migration(
            version="v1.0",
            name="initial",
            up_func=lambda b: True,
        )
        self.manager.register(migration)
        self.manager.migrate_up("v1.0")
        history = self.manager.get_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].version, "v1.0")

    def test_get_status(self):
        migration = Migration(
            version="v1.0",
            name="initial",
            up_func=lambda b: True,
        )
        self.manager.register(migration)
        status = self.manager.get_status("v1.0")
        self.assertEqual(status, MigrationStatus.PENDING)
        self.manager.migrate_up("v1.0")
        status = self.manager.get_status("v1.0")
        self.assertEqual(status, MigrationStatus.COMPLETED)

    def test_stats(self):
        migration = Migration(
            version="v1.0",
            name="initial",
            up_func=lambda b: True,
        )
        self.manager.register(migration)
        stats = self.manager.get_stats()
        self.assertEqual(stats["total_migrations"], 1)


class TestMigrationBuilder(unittest.TestCase):
    """迁移构建器测试"""

    def test_build_migration(self):
        migration = (
            MigrationBuilder("v1.0", "initial")
            .up(lambda b: True)
            .down(lambda b: True)
            .description("Initial migration")
            .depends_on("v0.9")
            .build()
        )
        self.assertEqual(migration.version, "v1.0")
        self.assertEqual(migration.name, "initial")
        self.assertEqual(migration.description, "Initial migration")
        self.assertEqual(migration.dependencies, ["v0.9"])

    def test_build_without_up(self):
        with self.assertRaises(ValueError):
            MigrationBuilder("v1.0", "initial").build()


# ============================================================
# 数据结构测试
# ============================================================

class TestDataStructures(unittest.TestCase):
    """数据结构基础测试"""

    def test_storage_enums(self):
        self.assertEqual(StorageType.MEMORY.value, "memory")
        self.assertEqual(StorageStatus.ACTIVE.value, "active")
        self.assertEqual(OperationType.READ.value, "read")

    def test_file_format_enum(self):
        self.assertEqual(FileFormat.JSON.value, "json")
        self.assertEqual(FileFormat.YAML.value, "yaml")

    def test_cache_policy_enum(self):
        self.assertEqual(CachePolicy.READ_THROUGH.value, "read_through")
        self.assertEqual(EvictionPolicy.LRU.value, "lru")

    def test_transaction_state_enum(self):
        self.assertEqual(TransactionState.ACTIVE.value, "active")
        self.assertEqual(IsolationLevel.READ_COMMITTED.value, "read_committed")

    def test_migration_status_enum(self):
        self.assertEqual(MigrationStatus.COMPLETED.value, "completed")
        self.assertEqual(MigrationDirection.UP.value, "up")

    def test_storage_config(self):
        config = StorageConfig(
            storage_type=StorageType.FILE,
            namespace="test",
            ttl=3600.0,
        )
        self.assertEqual(config.storage_type, StorageType.FILE)
        self.assertEqual(config.namespace, "test")
        self.assertEqual(config.ttl, 3600.0)

    def test_cache_config(self):
        config = CacheConfig(
            max_size=500,
            policy=CachePolicy.WRITE_THROUGH,
            eviction=EvictionPolicy.LFU,
        )
        self.assertEqual(config.max_size, 500)
        self.assertEqual(config.policy, CachePolicy.WRITE_THROUGH)

    def test_cache_stats(self):
        stats = CacheStats(hits=80, misses=20)
        self.assertEqual(stats.hit_rate, 0.8)

    def test_transaction_result(self):
        result = TransactionResult(
            success=True,
            transaction_id="tx_1",
            operations_count=5,
        )
        self.assertTrue(result.success)
        self.assertEqual(result.operations_count, 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
