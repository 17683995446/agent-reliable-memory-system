"""
Distributed Module for Agent Reliable Memory System.

This module provides distributed system coordination capabilities including:
- Node management (Stage 396)
- Consensus engine (Stage 397)
- Distributed locking (Stage 398)
- Task scheduling (Stage 399)
- State synchronization (Stage 400)
"""

from .node_manager import (
    NodeStatus,
    NodeRole,
    NodeInfo,
    ClusterConfig,
    NodeManager,
    get_node_manager,
    reset_node_manager
)

from .consensus_engine import (
    ProposalStatus,
    VoteType,
    Proposal,
    Vote,
    ConsensusEngine,
    get_consensus_engine,
    reset_consensus_engine
)

from .distributed_lock import (
    LockStatus,
    LockType,
    LockRecord,
    DistributedLockManager,
    get_distributed_lock_manager,
    reset_distributed_lock_manager
)

from .task_scheduler import (
    TaskStatus,
    TaskPriority,
    TaskType,
    Task,
    TaskScheduler,
    get_task_scheduler,
    reset_task_scheduler
)

from .state_sync import (
    SyncStatus,
    SyncStrategy,
    StateSnapshot,
    StateDiff,
    StateSyncManager,
    get_state_sync_manager,
    reset_state_sync_manager
)

__all__ = [
    # Node Manager
    'NodeStatus',
    'NodeRole',
    'NodeInfo',
    'ClusterConfig',
    'NodeManager',
    'get_node_manager',
    'reset_node_manager',
    
    # Consensus Engine
    'ProposalStatus',
    'VoteType',
    'Proposal',
    'Vote',
    'ConsensusEngine',
    'get_consensus_engine',
    'reset_consensus_engine',
    
    # Distributed Lock
    'LockStatus',
    'LockType',
    'LockRecord',
    'DistributedLockManager',
    'get_distributed_lock_manager',
    'reset_distributed_lock_manager',
    
    # Task Scheduler
    'TaskStatus',
    'TaskPriority',
    'TaskType',
    'Task',
    'TaskScheduler',
    'get_task_scheduler',
    'reset_task_scheduler',
    
    # State Sync
    'SyncStatus',
    'SyncStrategy',
    'StateSnapshot',
    'StateDiff',
    'StateSyncManager',
    'get_state_sync_manager',
    'reset_state_sync_manager'
]
