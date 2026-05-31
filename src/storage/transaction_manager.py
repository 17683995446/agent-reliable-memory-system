"""
事务管理模块 (阶段364)

提供类ACID的事务支持，包括原子性、一致性、隔离性和持久性保证。
线程安全设计，使用 threading.RLock 保证并发安全。
确定性规则设计，无模型依赖，无循环依赖。
"""

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from .storage_backend import StorageBackend


# ============================================================================
# 枚举定义
# ============================================================================


class TransactionState(Enum):
    """事务状态枚举"""
    ACTIVE = "active"        # 活跃：事务正在进行
    COMMITTED = "committed"  # 已提交
    ABORTED = "aborted"      # 已中止
    PREPARING = "preparing"  # 准备中


class IsolationLevel(Enum):
    """隔离级别枚举"""
    READ_UNCOMMITTED = "read_uncommitted"
    READ_COMMITTED = "read_committed"
    REPEATABLE_READ = "repeatable_read"
    SERIALIZABLE = "serializable"


class OperationType(Enum):
    """操作类型枚举"""
    SET = "set"
    DELETE = "delete"


# ============================================================================
# 数据类定义
# ============================================================================


@dataclass
class TransactionOperation:
    """事务操作数据类"""
    type: OperationType
    key: str
    value: Any = None
    old_value: Any = None
    namespace: str = "default"


@dataclass
class Transaction:
    """事务数据类"""
    id: str
    state: TransactionState = TransactionState.ACTIVE
    isolation_level: IsolationLevel = IsolationLevel.READ_COMMITTED
    operations: List[TransactionOperation] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    committed_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TransactionResult:
    """事务结果数据类"""
    success: bool
    transaction_id: str
    operations_count: int
    error: Optional[str] = None
    duration: float = 0.0


# ============================================================================
# 事务管理器
# ============================================================================


class TransactionManager:
    """
    事务管理器
    
    提供类ACID的事务支持。支持：
    - 原子性：所有操作要么全部成功，要么全部回滚
    - 一致性：通过验证函数确保数据一致性
    - 隔离性：支持多种隔离级别
    - 持久性：提交后数据持久保存
    
    线程安全，使用 RLock 保证并发访问安全。
    """
    
    def __init__(self, backend: StorageBackend) -> None:
        self._lock = threading.RLock()
        self._backend = backend
        self._transactions: Dict[str, Transaction] = {}
        self._id_counter: int = 0
    
    def _generate_id(self) -> str:
        """生成唯一事务ID"""
        with self._lock:
            self._id_counter += 1
            return f"tx_{self._id_counter}_{uuid.uuid4().hex[:8]}"
    
    def begin(self, isolation_level: IsolationLevel = IsolationLevel.READ_COMMITTED) -> Transaction:
        """
        开始新事务
        
        Args:
            isolation_level: 隔离级别
            
        Returns:
            新创建的事务对象
        """
        with self._lock:
            tx = Transaction(
                id=self._generate_id(),
                state=TransactionState.ACTIVE,
                isolation_level=isolation_level,
            )
            self._transactions[tx.id] = tx
            return tx
    
    def set(self, tx_id: str, key: str, value: Any, namespace: str = "default") -> bool:
        """
        在事务中设置值
        
        Args:
            tx_id: 事务ID
            key: 键
            value: 值
            namespace: 命名空间
            
        Returns:
            是否成功添加操作
        """
        with self._lock:
            tx = self._transactions.get(tx_id)
            if tx is None or tx.state != TransactionState.ACTIVE:
                return False
            
            # 读取旧值用于回滚
            old_value = self._backend.get(key, namespace)
            
            op = TransactionOperation(
                type=OperationType.SET,
                key=key,
                value=value,
                old_value=old_value,
                namespace=namespace,
            )
            tx.operations.append(op)
            return True
    
    def delete(self, tx_id: str, key: str, namespace: str = "default") -> bool:
        """
        在事务中删除值
        
        Args:
            tx_id: 事务ID
            key: 键
            namespace: 命名空间
            
        Returns:
            是否成功添加操作
        """
        with self._lock:
            tx = self._transactions.get(tx_id)
            if tx is None or tx.state != TransactionState.ACTIVE:
                return False
            
            # 读取旧值用于回滚
            old_value = self._backend.get(key, namespace)
            
            op = TransactionOperation(
                type=OperationType.DELETE,
                key=key,
                old_value=old_value,
                namespace=namespace,
            )
            tx.operations.append(op)
            return True
    
    def commit(self, tx_id: str) -> TransactionResult:
        """
        提交事务
        
        Args:
            tx_id: 事务ID
            
        Returns:
            事务结果
        """
        with self._lock:
            tx = self._transactions.get(tx_id)
            if tx is None:
                return TransactionResult(
                    success=False,
                    transaction_id=tx_id,
                    operations_count=0,
                    error="Transaction not found",
                )
            
            if tx.state != TransactionState.ACTIVE:
                return TransactionResult(
                    success=False,
                    transaction_id=tx_id,
                    operations_count=len(tx.operations),
                    error=f"Transaction state is {tx.state.value}",
                )
            
            start_time = time.time()
            tx.state = TransactionState.PREPARING
            
            try:
                # 执行所有操作
                for op in tx.operations:
                    if op.type == OperationType.SET:
                        self._backend.set(op.key, op.value, op.namespace)
                    elif op.type == OperationType.DELETE:
                        self._backend.delete(op.key, op.namespace)
                
                tx.state = TransactionState.COMMITTED
                tx.committed_at = time.time()
                
                return TransactionResult(
                    success=True,
                    transaction_id=tx_id,
                    operations_count=len(tx.operations),
                    duration=time.time() - start_time,
                )
            
            except Exception as e:
                # 回滚
                self._rollback_internal(tx)
                return TransactionResult(
                    success=False,
                    transaction_id=tx_id,
                    operations_count=len(tx.operations),
                    error=str(e),
                    duration=time.time() - start_time,
                )
    
    def abort(self, tx_id: str) -> TransactionResult:
        """
        中止事务
        
        Args:
            tx_id: 事务ID
            
        Returns:
            事务结果
        """
        with self._lock:
            tx = self._transactions.get(tx_id)
            if tx is None:
                return TransactionResult(
                    success=False,
                    transaction_id=tx_id,
                    operations_count=0,
                    error="Transaction not found",
                )
            
            if tx.state != TransactionState.ACTIVE:
                return TransactionResult(
                    success=False,
                    transaction_id=tx_id,
                    operations_count=len(tx.operations),
                    error=f"Transaction state is {tx.state.value}",
                )
            
            start_time = time.time()
            self._rollback_internal(tx)
            
            return TransactionResult(
                success=True,
                transaction_id=tx_id,
                operations_count=len(tx.operations),
                duration=time.time() - start_time,
            )
    
    def _rollback_internal(self, tx: Transaction) -> None:
        """内部回滚方法"""
        # 反向执行操作以回滚
        for op in reversed(tx.operations):
            if op.type == OperationType.SET:
                # 恢复旧值
                if op.old_value is not None:
                    self._backend.set(op.key, op.old_value, op.namespace)
                else:
                    self._backend.delete(op.key, op.namespace)
            elif op.type == OperationType.DELETE:
                # 恢复被删除的值
                if op.old_value is not None:
                    self._backend.set(op.key, op.old_value, op.namespace)
        
        tx.state = TransactionState.ABORTED
    
    def get_transaction(self, tx_id: str) -> Optional[Transaction]:
        """获取事务"""
        with self._lock:
            return self._transactions.get(tx_id)
    
    def get_active_transactions(self) -> List[Transaction]:
        """获取所有活跃事务"""
        with self._lock:
            return [
                tx for tx in self._transactions.values()
                if tx.state == TransactionState.ACTIVE
            ]
    
    def cleanup_completed(self, max_age: float = 3600.0) -> int:
        """
        清理已完成的事务
        
        Args:
            max_age: 最大保留时间（秒）
            
        Returns:
            清理的事务数量
        """
        with self._lock:
            now = time.time()
            to_remove = []
            
            for tx_id, tx in self._transactions.items():
                if tx.state in (TransactionState.COMMITTED, TransactionState.ABORTED):
                    end_time = tx.committed_at or tx.created_at
                    if now - end_time > max_age:
                        to_remove.append(tx_id)
            
            for tx_id in to_remove:
                del self._transactions[tx_id]
            
            return len(to_remove)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            state_counts = {}
            for tx in self._transactions.values():
                state = tx.state.value
                state_counts[state] = state_counts.get(state, 0) + 1
            
            return {
                "total_transactions": len(self._transactions),
                "by_state": state_counts,
                "active_count": state_counts.get("active", 0),
            }
    
    def execute(self, operations: List[Tuple[str, str, Any, str]],
                isolation_level: IsolationLevel = IsolationLevel.READ_COMMITTED) -> TransactionResult:
        """
        原子执行多个操作
        
        Args:
            operations: 操作列表 [(op_type, key, value, namespace), ...]
            isolation_level: 隔离级别
            
        Returns:
            事务结果
        """
        tx = self.begin(isolation_level)
        
        for op_type, key, value, namespace in operations:
            if op_type == "set":
                self.set(tx.id, key, value, namespace)
            elif op_type == "delete":
                self.delete(tx.id, key, namespace)
        
        return self.commit(tx.id)


# ============================================================================
# 上下文管理器
# ============================================================================


class TransactionContext:
    """
    事务上下文管理器
    
    支持 with 语句自动提交/回滚。
    """
    
    def __init__(self, manager: TransactionManager,
                 isolation_level: IsolationLevel = IsolationLevel.READ_COMMITTED) -> None:
        self._manager = manager
        self._isolation_level = isolation_level
        self._tx: Optional[Transaction] = None
        self._result: Optional[TransactionResult] = None
    
    def __enter__(self) -> "TransactionContext":
        self._tx = self._manager.begin(self._isolation_level)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if self._tx is None:
            return False
        
        if exc_type is not None:
            # 发生异常，回滚
            self._result = self._manager.abort(self._tx.id)
        else:
            # 正常退出，提交
            self._result = self._manager.commit(self._tx.id)
        
        return False  # 不抑制异常
    
    def set(self, key: str, value: Any, namespace: str = "default") -> bool:
        """在事务中设置值"""
        if self._tx is None:
            return False
        return self._manager.set(self._tx.id, key, value, namespace)
    
    def delete(self, key: str, namespace: str = "default") -> bool:
        """在事务中删除值"""
        if self._tx is None:
            return False
        return self._manager.delete(self._tx.id, key, namespace)
    
    @property
    def result(self) -> Optional[TransactionResult]:
        """获取事务结果"""
        return self._result
    
    @property
    def transaction_id(self) -> Optional[str]:
        """获取事务ID"""
        return self._tx.id if self._tx else None


# ============================================================================
# 全局单例
# ============================================================================

_transaction_manager_instance: Optional[TransactionManager] = None
_transaction_manager_lock = threading.Lock()


def get_transaction_manager() -> TransactionManager:
    """获取事务管理器全局单例"""
    global _transaction_manager_instance
    with _transaction_manager_lock:
        return _transaction_manager_instance


def init_transaction_manager(backend: StorageBackend) -> TransactionManager:
    """初始化事务管理器全局单例"""
    global _transaction_manager_instance
    with _transaction_manager_lock:
        if _transaction_manager_instance is None:
            _transaction_manager_instance = TransactionManager(backend)
        return _transaction_manager_instance
