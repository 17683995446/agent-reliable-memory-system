#!/usr/bin/env python3
"""
数据备份与恢复 (DataBackup) - 阶段343

职责：
- 完整快照：全量数据备份
- 增量备份：仅备份变化部分
- 备份版本管理：版本号、标签、元数据
- 数据恢复：从备份恢复到指定版本
- 备份清理：过期备份自动清理

设计原则：
- 确定性规则，无模型依赖
- 线程安全（RLock）
- 最小层级，无循环依赖
"""

import hashlib
import json
import os
import shutil
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


# ============================================================
# 枚举与数据结构
# ============================================================

class BackupType(Enum):
    """备份类型"""
    FULL = "full"         # 全量备份
    INCREMENTAL = "incremental"  # 增量备份
    SNAPSHOT = "snapshot"  # 快照（内存快照）


class BackupStatus(Enum):
    """备份状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CORRUPTED = "corrupted"


class StorageBackend(Enum):
    """存储后端"""
    LOCAL = "local"       # 本地文件系统
    MEMORY = "memory"     # 内存存储


@dataclass
class BackupMeta:
    """备份元数据"""
    id: str = ""
    name: str = ""
    backup_type: BackupType = BackupType.FULL
    status: BackupStatus = BackupStatus.PENDING
    version: int = 0
    parent_id: str = ""           # 增量备份的父备份ID
    tags: List[str] = field(default_factory=list)
    created_at: float = 0.0
    completed_at: float = 0.0
    size_bytes: int = 0
    record_count: int = 0
    checksum: str = ""
    description: str = ""
    source_name: str = ""          # 数据源名称

    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = time.time()
        if not self.id:
            import uuid
            self.id = uuid.uuid4().hex[:12]


@dataclass
class BackupPolicy:
    """备份策略"""
    max_versions: int = 10            # 最大保留版本数
    max_age_seconds: float = 0.0      # 最大保留时间（0=不限）
    auto_backup: bool = False          # 是否自动备份
    backup_interval: float = 3600.0    # 自动备份间隔（秒）
    compression: bool = True           # 是否压缩
    storage_backend: StorageBackend = StorageBackend.MEMORY


@dataclass
class ChangeRecord:
    """变更记录（用于增量备份）"""
    key: str
    operation: str = "set"     # set, delete
    value: Any = None
    timestamp: float = 0.0
    checksum: str = ""

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()
        if self.value is not None:
            self.checksum = hashlib.md5(
                json.dumps(self.value, sort_keys=True, default=str).encode()
            ).hexdigest()[:12]


# ============================================================
# 变更跟踪器
# ============================================================

class ChangeTracker:
    """
    变更跟踪器

    核心功能：
    1. 跟踪数据变更（set/delete）
    2. 计算数据指纹（checksum）
    3. 变更日志管理
    4. 增量数据提取
    """

    def __init__(self):
        self._changes: List[ChangeRecord] = []
        self._fingerprints: Dict[str, str] = {}  # key → checksum
        self._lock = threading.RLock()
        self._total_changes = 0

    def record_set(self, key: str, value: Any) -> None:
        """记录set操作"""
        with self._lock:
            record = ChangeRecord(key=key, operation="set", value=value)
            self._changes.append(record)
            self._fingerprints[key] = record.checksum
            self._total_changes += 1

    def record_delete(self, key: str) -> None:
        """记录delete操作"""
        with self._lock:
            record = ChangeRecord(key=key, operation="delete")
            self._changes.append(record)
            self._fingerprints.pop(key, None)
            self._total_changes += 1

    def get_changes(self, since_timestamp: float = 0.0) -> List[ChangeRecord]:
        """获取指定时间之后的变更"""
        with self._lock:
            return [c for c in self._changes if c.timestamp > since_timestamp]

    def get_pending_changes(self) -> List[ChangeRecord]:
        """获取未备份的变更"""
        with self._lock:
            return list(self._changes)

    def clear_changes(self) -> int:
        """清除已备份的变更"""
        with self._lock:
            count = len(self._changes)
            self._changes.clear()
            return count

    def get_fingerprint(self, key: str) -> Optional[str]:
        """获取数据指纹"""
        with self._lock:
            return self._fingerprints.get(key)

    def get_all_fingerprints(self) -> Dict[str, str]:
        """获取所有指纹"""
        with self._lock:
            return dict(self._fingerprints)

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "pending_changes": len(self._changes),
                "total_changes": self._total_changes,
                "tracked_keys": len(self._fingerprints),
            }


# ============================================================
# 备份存储
# ============================================================

class BackupStorage:
    """
    备份存储

    核心功能：
    1. 内存存储
    2. 本地文件存储
    3. 备份数据读写
    4. 存储空间管理
    """

    def __init__(self, backend: StorageBackend = StorageBackend.MEMORY,
                 base_path: str = ""):
        self._backend = backend
        self._base_path = base_path
        self._memory_store: Dict[str, Dict[str, Any]] = {}  # backup_id → data
        self._lock = threading.RLock()

    def save(self, backup_id: str, data: Dict[str, Any],
             meta: BackupMeta) -> bool:
        """保存备份数据"""
        with self._lock:
            if self._backend == StorageBackend.MEMORY:
                self._memory_store[backup_id] = {
                    "data": data,
                    "meta": meta,
                }
                return True
            elif self._backend == StorageBackend.LOCAL:
                dir_path = os.path.join(self._base_path, backup_id)
                os.makedirs(dir_path, exist_ok=True)
                # 保存数据
                data_path = os.path.join(dir_path, "data.json")
                with open(data_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                # 保存元数据
                meta_path = os.path.join(dir_path, "meta.json")
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "id": meta.id,
                        "name": meta.name,
                        "backup_type": meta.backup_type.value,
                        "version": meta.version,
                        "parent_id": meta.parent_id,
                        "tags": meta.tags,
                        "created_at": meta.created_at,
                        "checksum": meta.checksum,
                        "description": meta.description,
                        "source_name": meta.source_name,
                    }, f, ensure_ascii=False, indent=2)
                return True
            return False

    def load(self, backup_id: str) -> Optional[Dict[str, Any]]:
        """加载备份数据"""
        with self._lock:
            if self._backend == StorageBackend.MEMORY:
                entry = self._memory_store.get(backup_id)
                if entry:
                    return entry["data"]
                return None
            elif self._backend == StorageBackend.LOCAL:
                data_path = os.path.join(self._base_path, backup_id, "data.json")
                if os.path.exists(data_path):
                    with open(data_path, "r", encoding="utf-8") as f:
                        return json.load(f)
                return None
            return None

    def delete(self, backup_id: str) -> bool:
        """删除备份"""
        with self._lock:
            if self._backend == StorageBackend.MEMORY:
                return self._memory_store.pop(backup_id, None) is not None
            elif self._backend == StorageBackend.LOCAL:
                dir_path = os.path.join(self._base_path, backup_id)
                if os.path.exists(dir_path):
                    shutil.rmtree(dir_path)
                    return True
                return False
            return False

    def exists(self, backup_id: str) -> bool:
        """检查备份是否存在"""
        with self._lock:
            if self._backend == StorageBackend.MEMORY:
                return backup_id in self._memory_store
            elif self._backend == StorageBackend.LOCAL:
                return os.path.exists(
                    os.path.join(self._base_path, backup_id, "data.json")
                )
            return False

    def get_size(self, backup_id: str) -> int:
        """获取备份大小"""
        with self._lock:
            if self._backend == StorageBackend.MEMORY:
                entry = self._memory_store.get(backup_id)
                if entry:
                    return len(json.dumps(entry["data"], default=str).encode())
                return 0
            elif self._backend == StorageBackend.LOCAL:
                data_path = os.path.join(self._base_path, backup_id, "data.json")
                if os.path.exists(data_path):
                    return os.path.getsize(data_path)
                return 0
            return 0

    def list_backups(self) -> List[str]:
        """列出所有备份ID"""
        with self._lock:
            if self._backend == StorageBackend.MEMORY:
                return list(self._memory_store.keys())
            elif self._backend == StorageBackend.LOCAL:
                if not os.path.exists(self._base_path):
                    return []
                return [
                    d for d in os.listdir(self._base_path)
                    if os.path.isdir(os.path.join(self._base_path, d))
                ]
            return []


# ============================================================
# 数据备份管理器
# ============================================================

class DataBackup:
    """
    数据备份管理器

    核心功能：
    1. 全量/增量/快照备份
    2. 数据恢复
    3. 版本管理
    4. 备份策略
    5. 自动清理
    """

    def __init__(self, policy: Optional[BackupPolicy] = None):
        self._policy = policy or BackupPolicy()
        self._tracker = ChangeTracker()
        self._storage = BackupStorage(self._policy.storage_backend)
        self._metas: Dict[str, BackupMeta] = {}
        self._version_counter = 0
        self._lock = threading.RLock()
        self._data_sources: Dict[str, Callable[[], Dict[str, Any]]] = {}
        self._restore_targets: Dict[str, Callable[[Dict[str, Any]], None]] = {}

    # ---- 数据源管理 ----

    def register_source(self, name: str,
                        dump_fn: Callable[[], Dict[str, Any]]) -> None:
        """注册数据源（提供全量数据）"""
        with self._lock:
            self._data_sources[name] = dump_fn

    def register_restore_target(self, name: str,
                                 restore_fn: Callable[[Dict[str, Any]], None]) -> None:
        """注册恢复目标（接收恢复数据）"""
        with self._lock:
            self._restore_targets[name] = restore_fn

    # ---- 变更跟踪 ----

    def track_change(self, key: str, value: Any = None,
                     operation: str = "set") -> None:
        """跟踪数据变更"""
        if operation == "delete":
            self._tracker.record_delete(key)
        else:
            self._tracker.record_set(key, value)

    # ---- 备份操作 ----

    def create_full_backup(self, source_name: str = "",
                           tags: Optional[List[str]] = None,
                           description: str = "") -> Optional[str]:
        """
        创建全量备份

        Returns:
            备份ID
        """
        with self._lock:
            self._version_counter += 1

        # 获取数据
        data = self._collect_source_data(source_name)
        if data is None:
            return None

        meta = BackupMeta(
            name=f"full_v{self._version_counter}",
            backup_type=BackupType.FULL,
            version=self._version_counter,
            tags=tags or [],
            description=description,
            source_name=source_name,
            record_count=len(data),
        )

        # 计算校验和
        checksum = hashlib.md5(
            json.dumps(data, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]
        meta.checksum = checksum

        # 保存
        success = self._storage.save(meta.id, data, meta)
        if success:
            meta.status = BackupStatus.COMPLETED
            meta.completed_at = time.time()
            meta.size_bytes = self._storage.get_size(meta.id)
            with self._lock:
                self._metas[meta.id] = meta
            self._tracker.clear_changes()
            return meta.id
        else:
            meta.status = BackupStatus.FAILED
            return None

    def create_incremental_backup(self, source_name: str = "",
                                  parent_id: str = "",
                                  tags: Optional[List[str]] = None,
                                  description: str = "") -> Optional[str]:
        """
        创建增量备份

        Returns:
            备份ID
        """
        changes = self._tracker.get_pending_changes()
        if not changes:
            return None

        with self._lock:
            self._version_counter += 1

        # 确定父备份
        if not parent_id:
            # 找到最新的全量备份
            parent_id = self._find_latest_backup(BackupType.FULL)
            if not parent_id:
                parent_id = self._find_latest_backup(BackupType.INCREMENTAL)

        # 构建增量数据
        incremental_data = {
            "changes": [
                {
                    "key": c.key,
                    "operation": c.operation,
                    "value": c.value,
                    "timestamp": c.timestamp,
                    "checksum": c.checksum,
                }
                for c in changes
            ],
            "parent_id": parent_id,
        }

        meta = BackupMeta(
            name=f"incr_v{self._version_counter}",
            backup_type=BackupType.INCREMENTAL,
            version=self._version_counter,
            parent_id=parent_id,
            tags=tags or [],
            description=description,
            source_name=source_name,
            record_count=len(changes),
        )

        checksum = hashlib.md5(
            json.dumps(incremental_data, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]
        meta.checksum = checksum

        success = self._storage.save(meta.id, incremental_data, meta)
        if success:
            meta.status = BackupStatus.COMPLETED
            meta.completed_at = time.time()
            meta.size_bytes = self._storage.get_size(meta.id)
            with self._lock:
                self._metas[meta.id] = meta
            self._tracker.clear_changes()
            return meta.id
        return None

    def create_snapshot(self, source_name: str = "",
                        description: str = "") -> Optional[str]:
        """创建内存快照"""
        data = self._collect_source_data(source_name)
        if data is None:
            return None

        with self._lock:
            self._version_counter += 1

        meta = BackupMeta(
            name=f"snapshot_v{self._version_counter}",
            backup_type=BackupType.SNAPSHOT,
            version=self._version_counter,
            description=description,
            source_name=source_name,
            record_count=len(data),
        )

        success = self._storage.save(meta.id, data, meta)
        if success:
            meta.status = BackupStatus.COMPLETED
            meta.completed_at = time.time()
            meta.size_bytes = self._storage.get_size(meta.id)
            with self._lock:
                self._metas[meta.id] = meta
            return meta.id
        return None

    # ---- 恢复操作 ----

    def restore(self, backup_id: str,
                target_name: str = "") -> Optional[int]:
        """
        从备份恢复数据

        Returns:
            恢复的记录数
        """
        data = self._storage.load(backup_id)
        if data is None:
            return None

        meta = self._metas.get(backup_id)
        if meta is None:
            return None

        # 如果是增量备份，需要先恢复父备份
        if meta.backup_type == BackupType.INCREMENTAL and meta.parent_id:
            base_data = self._resolve_incremental(backup_id)
            if base_data is None:
                return None
            data = base_data

        # 恢复到目标
        if target_name:
            restore_fn = self._restore_targets.get(target_name)
            if restore_fn:
                try:
                    restore_fn(data)
                    return len(data) if isinstance(data, dict) else 0
                except Exception:
                    return None

        return len(data) if isinstance(data, dict) else 0

    def _resolve_incremental(self, backup_id: str) -> Optional[Dict[str, Any]]:
        """解析增量备份链为完整数据"""
        chain = []
        current_id = backup_id
        visited = set()

        # 回溯到全量备份
        while current_id:
            if current_id in visited:
                break
            visited.add(current_id)

            meta = self._metas.get(current_id)
            if meta is None:
                break

            data = self._storage.load(current_id)
            if data is None:
                break

            chain.append((meta, data))
            current_id = meta.parent_id

        # 从最早的全量备份开始应用变更
        chain.reverse()
        result = {}

        for meta, data in chain:
            if meta.backup_type == BackupType.FULL or meta.backup_type == BackupType.SNAPSHOT:
                result = dict(data)
            elif meta.backup_type == BackupType.INCREMENTAL:
                changes = data.get("changes", [])
                for change in changes:
                    if change["operation"] == "set":
                        result[change["key"]] = change["value"]
                    elif change["operation"] == "delete":
                        result.pop(change["key"], None)

        return result

    # ---- 备份管理 ----

    def delete_backup(self, backup_id: str) -> bool:
        """删除备份"""
        with self._lock:
            meta = self._metas.pop(backup_id, None)
            if meta is None:
                return False
            return self._storage.delete(backup_id)

    def get_backup(self, backup_id: str) -> Optional[Dict[str, Any]]:
        """获取备份信息"""
        with self._lock:
            meta = self._metas.get(backup_id)
            if meta is None:
                return None
            return {
                "id": meta.id,
                "name": meta.name,
                "type": meta.backup_type.value,
                "status": meta.status.value,
                "version": meta.version,
                "parent_id": meta.parent_id,
                "tags": meta.tags,
                "created_at": meta.created_at,
                "size_bytes": meta.size_bytes,
                "record_count": meta.record_count,
                "checksum": meta.checksum,
                "description": meta.description,
            }

    def list_backups(self, backup_type: Optional[BackupType] = None,
                     tag: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出备份"""
        with self._lock:
            metas = list(self._metas.values())

        if backup_type:
            metas = [m for m in metas if m.backup_type == backup_type]
        if tag:
            metas = [m for m in metas if tag in m.tags]

        return [
            {
                "id": m.id,
                "name": m.name,
                "type": m.backup_type.value,
                "version": m.version,
                "created_at": m.created_at,
                "size_bytes": m.size_bytes,
                "record_count": m.record_count,
            }
            for m in sorted(metas, key=lambda x: x.version, reverse=True)
        ]

    def cleanup(self) -> int:
        """
        清理过期备份

        Returns:
            清理的备份数
        """
        cleaned = 0
        with self._lock:
            metas = sorted(self._metas.values(),
                           key=lambda m: m.version, reverse=True)

            # 按版本数限制
            if self._policy.max_versions > 0:
                for meta in metas[self._policy.max_versions:]:
                    self._storage.delete(meta.id)
                    del self._metas[meta.id]
                    cleaned += 1

            # 按时间限制
            if self._policy.max_age_seconds > 0:
                now = time.time()
                to_delete = []
                for meta in self._metas.values():
                    if (now - meta.created_at) > self._policy.max_age_seconds:
                        to_delete.append(meta.id)
                for bid in to_delete:
                    self._storage.delete(bid)
                    del self._metas[bid]
                    cleaned += 1

        return cleaned

    # ---- 统计 ----

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            total_size = sum(m.size_bytes for m in self._metas.values())
            type_counts = defaultdict(int)
            for m in self._metas.values():
                type_counts[m.backup_type.value] += 1

            return {
                "total_backups": len(self._metas),
                "total_size_bytes": total_size,
                "by_type": dict(type_counts),
                "latest_version": self._version_counter,
                "sources": len(self._data_sources),
                "restore_targets": len(self._restore_targets),
                "tracker": self._tracker.get_stats(),
                "policy": {
                    "max_versions": self._policy.max_versions,
                    "max_age": self._policy.max_age_seconds,
                    "auto_backup": self._policy.auto_backup,
                },
            }

    # ---- 内部方法 ----

    def _collect_source_data(self, source_name: str) -> Optional[Dict[str, Any]]:
        """收集数据源数据"""
        with self._lock:
            fn = self._data_sources.get(source_name)
        if fn:
            try:
                return fn()
            except Exception:
                return None
        return {}

    def _find_latest_backup(self, backup_type: BackupType) -> str:
        """找到指定类型的最新备份"""
        with self._lock:
            for meta in sorted(self._metas.values(),
                               key=lambda m: m.version, reverse=True):
                if meta.backup_type == backup_type:
                    return meta.id
        return ""


# ============================================================
# 全局单例
# ============================================================

_data_backup: Optional[DataBackup] = None
_db_lock = threading.RLock()


def get_data_backup() -> DataBackup:
    """获取全局数据备份管理器"""
    global _data_backup
    if _data_backup is None:
        with _db_lock:
            if _data_backup is None:
                _data_backup = DataBackup()
    return _data_backup
