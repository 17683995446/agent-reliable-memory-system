"""
迁移管理模块 (阶段365)

提供数据迁移和版本演进支持，支持迁移脚本管理和执行。
线程安全设计，使用 threading.RLock 保证并发安全。
确定性规则设计，无模型依赖，无循环依赖。
"""

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from .storage_backend import StorageBackend


# ============================================================================
# 枚举定义
# ============================================================================


class MigrationStatus(Enum):
    """迁移状态枚举"""
    PENDING = "pending"      # 待执行
    RUNNING = "running"      # 执行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"        # 失败
    ROLLED_BACK = "rolled_back"  # 已回滚


class MigrationDirection(Enum):
    """迁移方向枚举"""
    UP = "up"      # 升级
    DOWN = "down"  # 降级


# ============================================================================
# 数据类定义
# ============================================================================


@dataclass
class Migration:
    """迁移数据类"""
    version: str
    name: str
    up_func: Callable[[StorageBackend], bool]
    down_func: Optional[Callable[[StorageBackend], bool]] = None
    description: str = ""
    dependencies: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


@dataclass
class MigrationRecord:
    """迁移记录数据类"""
    version: str
    name: str
    status: MigrationStatus
    direction: MigrationDirection
    started_at: float
    completed_at: Optional[float] = None
    duration: float = 0.0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MigrationResult:
    """迁移结果数据类"""
    success: bool
    version: str
    direction: MigrationDirection
    duration: float = 0.0
    error: Optional[str] = None


# ============================================================================
# 迁移管理器
# ============================================================================


class MigrationManager:
    """
    迁移管理器
    
    管理数据迁移脚本，支持版本演进、依赖检查和回滚。
    线程安全，使用 RLock 保证并发访问安全。
    """
    
    def __init__(self, backend: StorageBackend) -> None:
        self._lock = threading.RLock()
        self._backend = backend
        self._migrations: Dict[str, Migration] = {}
        self._history: List[MigrationRecord] = []
        self._current_version: Optional[str] = None
    
    def register(self, migration: Migration) -> bool:
        """
        注册迁移
        
        Args:
            migration: 迁移对象
            
        Returns:
            是否成功注册
        """
        with self._lock:
            if migration.version in self._migrations:
                return False
            self._migrations[migration.version] = migration
            return True
    
    def unregister(self, version: str) -> bool:
        """
        注销迁移
        
        Args:
            version: 迁移版本
            
        Returns:
            是否成功注销
        """
        with self._lock:
            if version in self._migrations:
                del self._migrations[version]
                return True
            return False
    
    def get_migration(self, version: str) -> Optional[Migration]:
        """获取迁移"""
        with self._lock:
            return self._migrations.get(version)
    
    def list_migrations(self) -> List[Migration]:
        """列出所有迁移"""
        with self._lock:
            return list(self._migrations.values())
    
    def get_current_version(self) -> Optional[str]:
        """获取当前版本"""
        with self._lock:
            # 从存储读取当前版本
            version = self._backend.get("__migration_version__", "__system__")
            if version is not None:
                self._current_version = version
            return self._current_version
    
    def _set_current_version(self, version: Optional[str]) -> None:
        """设置当前版本"""
        with self._lock:
            self._current_version = version
            if version is not None:
                self._backend.set("__migration_version__", version, "__system__")
            else:
                self._backend.delete("__migration_version__", "__system__")
    
    def _check_dependencies(self, migration: Migration) -> bool:
        """检查依赖是否满足"""
        for dep_version in migration.dependencies:
            dep_record = self._get_completed_record(dep_version)
            if dep_record is None:
                return False
        return True
    
    def _get_completed_record(self, version: str) -> Optional[MigrationRecord]:
        """获取已完成的迁移记录"""
        for record in reversed(self._history):
            if record.version == version and record.status == MigrationStatus.COMPLETED:
                return record
        return None
    
    def migrate_up(self, version: str) -> MigrationResult:
        """
        执行升级迁移
        
        Args:
            version: 目标版本
            
        Returns:
            迁移结果
        """
        with self._lock:
            migration = self._migrations.get(version)
            if migration is None:
                return MigrationResult(
                    success=False,
                    version=version,
                    direction=MigrationDirection.UP,
                    error="Migration not found",
                )
            
            # 检查是否已执行
            if self._get_completed_record(version) is not None:
                return MigrationResult(
                    success=True,
                    version=version,
                    direction=MigrationDirection.UP,
                )
            
            # 检查依赖
            if not self._check_dependencies(migration):
                return MigrationResult(
                    success=False,
                    version=version,
                    direction=MigrationDirection.UP,
                    error="Dependencies not satisfied",
                )
            
            # 执行迁移
            start_time = time.time()
            record = MigrationRecord(
                version=version,
                name=migration.name,
                status=MigrationStatus.RUNNING,
                direction=MigrationDirection.UP,
                started_at=start_time,
            )
            self._history.append(record)
            
            try:
                success = migration.up_func(self._backend)
                
                if success:
                    record.status = MigrationStatus.COMPLETED
                    record.completed_at = time.time()
                    record.duration = record.completed_at - start_time
                    self._set_current_version(version)
                    
                    return MigrationResult(
                        success=True,
                        version=version,
                        direction=MigrationDirection.UP,
                        duration=record.duration,
                    )
                else:
                    record.status = MigrationStatus.FAILED
                    record.completed_at = time.time()
                    record.duration = record.completed_at - start_time
                    record.error = "Migration returned False"
                    
                    return MigrationResult(
                        success=False,
                        version=version,
                        direction=MigrationDirection.UP,
                        duration=record.duration,
                        error=record.error,
                    )
            
            except Exception as e:
                record.status = MigrationStatus.FAILED
                record.completed_at = time.time()
                record.duration = record.completed_at - start_time
                record.error = str(e)
                
                return MigrationResult(
                    success=False,
                    version=version,
                    direction=MigrationDirection.UP,
                    duration=record.duration,
                    error=record.error,
                )
    
    def migrate_down(self, version: str) -> MigrationResult:
        """
        执行降级迁移（回滚）
        
        Args:
            version: 目标版本
            
        Returns:
            迁移结果
        """
        with self._lock:
            migration = self._migrations.get(version)
            if migration is None:
                return MigrationResult(
                    success=False,
                    version=version,
                    direction=MigrationDirection.DOWN,
                    error="Migration not found",
                )
            
            if migration.down_func is None:
                return MigrationResult(
                    success=False,
                    version=version,
                    direction=MigrationDirection.DOWN,
                    error="No rollback function defined",
                )
            
            # 检查是否已执行
            completed = self._get_completed_record(version)
            if completed is None:
                return MigrationResult(
                    success=False,
                    version=version,
                    direction=MigrationDirection.DOWN,
                    error="Migration was not applied",
                )
            
            # 执行回滚
            start_time = time.time()
            record = MigrationRecord(
                version=version,
                name=migration.name,
                status=MigrationStatus.RUNNING,
                direction=MigrationDirection.DOWN,
                started_at=start_time,
            )
            self._history.append(record)
            
            try:
                success = migration.down_func(self._backend)
                
                if success:
                    record.status = MigrationStatus.ROLLED_BACK
                    record.completed_at = time.time()
                    record.duration = record.completed_at - start_time
                    
                    # 找到前一个版本
                    prev_version = None
                    for r in reversed(self._history):
                        if (r.version != version and 
                            r.status == MigrationStatus.COMPLETED and
                            r.direction == MigrationDirection.UP):
                            prev_version = r.version
                            break
                    self._set_current_version(prev_version)
                    
                    return MigrationResult(
                        success=True,
                        version=version,
                        direction=MigrationDirection.DOWN,
                        duration=record.duration,
                    )
                else:
                    record.status = MigrationStatus.FAILED
                    record.completed_at = time.time()
                    record.duration = record.completed_at - start_time
                    record.error = "Rollback returned False"
                    
                    return MigrationResult(
                        success=False,
                        version=version,
                        direction=MigrationDirection.DOWN,
                        duration=record.duration,
                        error=record.error,
                    )
            
            except Exception as e:
                record.status = MigrationStatus.FAILED
                record.completed_at = time.time()
                record.duration = record.completed_at - start_time
                record.error = str(e)
                
                return MigrationResult(
                    success=False,
                    version=version,
                    direction=MigrationDirection.DOWN,
                    duration=record.duration,
                    error=record.error,
                )
    
    def migrate_to(self, target_version: str) -> List[MigrationResult]:
        """
        迁移到目标版本
        
        Args:
            target_version: 目标版本
            
        Returns:
            迁移结果列表
        """
        results = []
        current = self.get_current_version()
        
        # 获取所有版本并排序
        versions = sorted(self._migrations.keys())
        
        if current is None:
            # 从头开始迁移
            for v in versions:
                if v <= target_version:
                    result = self.migrate_up(v)
                    results.append(result)
                    if not result.success:
                        break
        elif current < target_version:
            # 升级
            for v in versions:
                if current < v <= target_version:
                    result = self.migrate_up(v)
                    results.append(result)
                    if not result.success:
                        break
        elif current > target_version:
            # 降级
            for v in reversed(versions):
                if target_version < v <= current:
                    result = self.migrate_down(v)
                    results.append(result)
                    if not result.success:
                        break
        
        return results
    
    def get_history(self, limit: int = 100) -> List[MigrationRecord]:
        """获取迁移历史"""
        with self._lock:
            return list(reversed(self._history[-limit:]))
    
    def get_status(self, version: str) -> Optional[MigrationStatus]:
        """获取迁移状态"""
        with self._lock:
            record = self._get_completed_record(version)
            if record is not None:
                return record.status
            
            for r in reversed(self._history):
                if r.version == version:
                    return r.status
            
            return MigrationStatus.PENDING
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            status_counts = {}
            for record in self._history:
                status = record.status.value
                status_counts[status] = status_counts.get(status, 0) + 1
            
            return {
                "total_migrations": len(self._migrations),
                "current_version": self._current_version,
                "history_count": len(self._history),
                "by_status": status_counts,
                "registered_versions": list(self._migrations.keys()),
            }


# ============================================================================
# 迁移构建器
# ============================================================================


class MigrationBuilder:
    """
    迁移构建器
    
    提供流畅的API来构建迁移对象。
    """
    
    def __init__(self, version: str, name: str):
        self._version = version
        self._name = name
        self._up_func: Optional[Callable[[StorageBackend], bool]] = None
        self._down_func: Optional[Callable[[StorageBackend], bool]] = None
        self._description = ""
        self._dependencies: List[str] = []
    
    def up(self, func: Callable[[StorageBackend], bool]) -> "MigrationBuilder":
        """设置升级函数"""
        self._up_func = func
        return self
    
    def down(self, func: Callable[[StorageBackend], bool]) -> "MigrationBuilder":
        """设置降级函数"""
        self._down_func = func
        return self
    
    def description(self, desc: str) -> "MigrationBuilder":
        """设置描述"""
        self._description = desc
        return self
    
    def depends_on(self, *versions: str) -> "MigrationBuilder":
        """设置依赖"""
        self._dependencies.extend(versions)
        return self
    
    def build(self) -> Migration:
        """构建迁移对象"""
        if self._up_func is None:
            raise ValueError("Up function is required")
        
        return Migration(
            version=self._version,
            name=self._name,
            up_func=self._up_func,
            down_func=self._down_func,
            description=self._description,
            dependencies=self._dependencies,
        )


# ============================================================================
# 全局单例
# ============================================================================

_migration_manager_instance: Optional[MigrationManager] = None
_migration_manager_lock = threading.Lock()


def get_migration_manager() -> MigrationManager:
    """获取迁移管理器全局单例"""
    global _migration_manager_instance
    with _migration_manager_lock:
        return _migration_manager_instance


def init_migration_manager(backend: StorageBackend) -> MigrationManager:
    """初始化迁移管理器全局单例"""
    global _migration_manager_instance
    with _migration_manager_lock:
        if _migration_manager_instance is None:
            _migration_manager_instance = MigrationManager(backend)
        return _migration_manager_instance
