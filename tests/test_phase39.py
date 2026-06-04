"""
Phase 39 Validation Tests - Distributed Modules (Stages 396-400)

Tests for:
- node_manager.py (Stage 396)
- consensus_engine.py (Stage 397)
- distributed_lock.py (Stage 398)
- task_scheduler.py (Stage 399)
- state_sync.py (Stage 400)
"""

import unittest
import time

from src.distributed import (
    # Node Manager
    NodeStatus, NodeRole, NodeInfo, ClusterConfig, NodeManager,
    get_node_manager, reset_node_manager,
    # Consensus Engine
    ProposalStatus, VoteType, Proposal, Vote, ConsensusEngine,
    get_consensus_engine, reset_consensus_engine,
    # Distributed Lock
    LockStatus, LockType, LockRecord, DistributedLockManager,
    get_distributed_lock_manager, reset_distributed_lock_manager,
    # Task Scheduler
    TaskStatus, TaskPriority, TaskType, Task, TaskScheduler,
    get_task_scheduler, reset_task_scheduler,
    # State Sync
    SyncStatus, SyncStrategy, StateSnapshot, StateDiff, StateSyncManager,
    get_state_sync_manager, reset_state_sync_manager
)


class TestNodeManager(unittest.TestCase):
    """Test NodeManager module (Stage 396)"""

    def setUp(self):
        reset_node_manager()
        self.manager = get_node_manager()

    def test_register_unregister(self):
        result = self.manager.register_node("node1", "localhost", 8080, NodeRole.FOLLOWER, 100)
        self.assertTrue(result)
        result = self.manager.unregister_node("node1")
        self.assertTrue(result)

    def test_get_node(self):
        self.manager.register_node("node1", "localhost", 8080, NodeRole.FOLLOWER, 100)
        node = self.manager.get_node("node1")
        self.assertIsNotNone(node)
        self.assertEqual(node.node_id, "node1")

    def test_get_all_nodes(self):
        self.manager.register_node("node1", "localhost", 8080, NodeRole.FOLLOWER, 100)
        self.manager.register_node("node2", "localhost", 8081, NodeRole.FOLLOWER, 100)
        nodes = self.manager.get_all_nodes()
        self.assertEqual(len(nodes), 2)

    def test_get_nodes_by_status(self):
        self.manager.register_node("node1", "localhost", 8080, NodeRole.FOLLOWER, 100)
        nodes = self.manager.get_nodes_by_status(NodeStatus.ONLINE)
        self.assertEqual(len(nodes), 1)

    def test_get_nodes_by_role(self):
        self.manager.register_node("node1", "localhost", 8080, NodeRole.LEADER, 100)
        self.manager.register_node("node2", "localhost", 8081, NodeRole.FOLLOWER, 100)
        nodes = self.manager.get_nodes_by_role(NodeRole.LEADER)
        self.assertEqual(len(nodes), 1)

    def test_update_node_status(self):
        self.manager.register_node("node1", "localhost", 8080, NodeRole.FOLLOWER, 100)
        result = self.manager.update_node_status("node1", NodeStatus.BUSY)
        self.assertTrue(result)
        node = self.manager.get_node("node1")
        self.assertEqual(node.status, NodeStatus.BUSY)

    def test_elect_leader(self):
        self.manager.register_node("node1", "localhost", 8080, NodeRole.FOLLOWER, 100)
        self.manager.register_node("node2", "localhost", 8081, NodeRole.FOLLOWER, 100)
        leader_id = self.manager.elect_leader()
        self.assertIsNotNone(leader_id)

    def test_get_leader(self):
        self.manager.register_node("node1", "localhost", 8080, NodeRole.FOLLOWER, 100)
        self.manager.elect_leader()
        leader = self.manager.get_leader()
        self.assertIsNotNone(leader)

    def test_is_quorum_available(self):
        self.manager.register_node("node1", "localhost", 8080, NodeRole.FOLLOWER, 100)
        self.manager.register_node("node2", "localhost", 8081, NodeRole.FOLLOWER, 100)
        self.manager.register_node("node3", "localhost", 8082, NodeRole.FOLLOWER, 100)
        self.assertTrue(self.manager.is_quorum_available())

    def test_heartbeat(self):
        self.manager.register_node("node1", "localhost", 8080, NodeRole.FOLLOWER, 100)
        result = self.manager.heartbeat("node1")
        self.assertTrue(result)

    def test_global_singleton(self):
        manager2 = get_node_manager()
        self.assertIs(self.manager, manager2)


class TestConsensusEngine(unittest.TestCase):
    """Test ConsensusEngine module (Stage 397)"""

    def setUp(self):
        reset_consensus_engine()
        self.engine = get_consensus_engine()

    def test_propose(self):
        proposal_id = self.engine.propose("value1", "node1")
        self.assertIsNotNone(proposal_id)
        proposal = self.engine.get_proposal(proposal_id)
        self.assertIsNotNone(proposal)

    def test_vote_and_accept(self):
        proposal_id = self.engine.propose("value1", "node1")
        self.engine.vote(proposal_id, "node1", VoteType.YES)
        self.engine.vote(proposal_id, "node2", VoteType.YES)
        self.engine.vote(proposal_id, "node3", VoteType.NO)
        self.assertTrue(self.engine.is_accepted(proposal_id))

    def test_commit_proposal(self):
        proposal_id = self.engine.propose("value1", "node1")
        self.engine.vote(proposal_id, "node1", VoteType.YES)
        self.engine.vote(proposal_id, "node2", VoteType.YES)
        result = self.engine.commit_proposal(proposal_id)
        self.assertTrue(result)
        proposal = self.engine.get_proposal(proposal_id)
        self.assertEqual(proposal.status, ProposalStatus.COMMITTED)

    def test_reject_proposal(self):
        proposal_id = self.engine.propose("value1", "node1")
        result = self.engine.reject_proposal(proposal_id)
        self.assertTrue(result)
        proposal = self.engine.get_proposal(proposal_id)
        self.assertEqual(proposal.status, ProposalStatus.REJECTED)

    def test_get_vote_count(self):
        proposal_id = self.engine.propose("value1", "node1")
        self.engine.vote(proposal_id, "node1", VoteType.YES)
        self.engine.vote(proposal_id, "node2", VoteType.NO)
        counts = self.engine.get_vote_count(proposal_id)
        self.assertEqual(counts["yes"], 1)
        self.assertEqual(counts["no"], 1)

    def test_vote_deduplication(self):
        proposal_id = self.engine.propose("value1", "node1")
        self.engine.vote(proposal_id, "node1", VoteType.YES)
        self.engine.vote(proposal_id, "node1", VoteType.NO)
        counts = self.engine.get_vote_count(proposal_id)
        self.assertEqual(counts["yes"] + counts["no"], 1)

    def test_term_management(self):
        term = self.engine.get_current_term()
        self.assertEqual(term, 0)
        new_term = self.engine.increment_term()
        self.assertEqual(new_term, 1)

    def test_get_proposals(self):
        self.engine.propose("value1", "node1")
        self.engine.propose("value2", "node2")
        proposals = self.engine.get_proposals()
        self.assertEqual(len(proposals), 2)

    def test_global_singleton(self):
        engine2 = get_consensus_engine()
        self.assertIs(self.engine, engine2)


class TestDistributedLockManager(unittest.TestCase):
    """Test DistributedLockManager module (Stage 398)"""

    def setUp(self):
        reset_distributed_lock_manager()
        self.manager = get_distributed_lock_manager()

    def test_acquire_release_lock(self):
        lock = self.manager.acquire_lock("resource1", "owner1", LockType.EXCLUSIVE)
        self.assertIsNotNone(lock)
        self.assertEqual(lock.status, LockStatus.LOCKED)
        result = self.manager.release_lock(lock.lock_id)
        self.assertTrue(result)

    def test_acquire_shared_lock(self):
        lock1 = self.manager.acquire_lock("resource1", "owner1", LockType.SHARED)
        lock2 = self.manager.acquire_lock("resource1", "owner2", LockType.SHARED)
        self.assertIsNotNone(lock1)
        self.assertIsNotNone(lock2)

    def test_is_locked(self):
        self.manager.acquire_lock("resource1", "owner1", LockType.EXCLUSIVE)
        self.assertTrue(self.manager.is_locked("resource1"))

    def test_get_lock_owner(self):
        self.manager.acquire_lock("resource1", "owner1", LockType.EXCLUSIVE)
        owner = self.manager.get_lock_owner("resource1")
        self.assertEqual(owner, "owner1")

    def test_extend_lock(self):
        lock = self.manager.acquire_lock("resource1", "owner1", LockType.EXCLUSIVE, ttl_seconds=10)
        result = self.manager.extend_lock(lock.lock_id, 20)
        self.assertTrue(result)

    def test_get_locks_by_owner(self):
        self.manager.acquire_lock("resource1", "owner1", LockType.EXCLUSIVE)
        self.manager.acquire_lock("resource2", "owner1", LockType.EXCLUSIVE)
        locks = self.manager.get_locks_by_owner("owner1")
        self.assertEqual(len(locks), 2)

    def test_cleanup_expired(self):
        self.manager.acquire_lock("resource1", "owner1", LockType.EXCLUSIVE, ttl_seconds=0)
        time.sleep(0.1)
        count = self.manager.cleanup_expired()
        self.assertGreaterEqual(count, 1)

    def test_global_singleton(self):
        manager2 = get_distributed_lock_manager()
        self.assertIs(self.manager, manager2)


class TestTaskScheduler(unittest.TestCase):
    """Test TaskScheduler module (Stage 399)"""

    def setUp(self):
        reset_task_scheduler()
        self.scheduler = get_task_scheduler()

    def test_submit_task(self):
        task_id = self.scheduler.submit_task(TaskType.COMPUTE, TaskPriority.NORMAL, {"job": "test"})
        self.assertIsNotNone(task_id)
        task = self.scheduler.get_task(task_id)
        self.assertIsNotNone(task)

    def test_cancel_task(self):
        task_id = self.scheduler.submit_task(TaskType.COMPUTE, TaskPriority.NORMAL, {"job": "test"})
        result = self.scheduler.cancel_task(task_id)
        self.assertTrue(result)
        task = self.scheduler.get_task(task_id)
        self.assertEqual(task.status, TaskStatus.CANCELLED)

    def test_assign_task(self):
        task_id = self.scheduler.submit_task(TaskType.COMPUTE, TaskPriority.NORMAL, {"job": "test"})
        result = self.scheduler.assign_task(task_id, "node1")
        self.assertTrue(result)
        task = self.scheduler.get_task(task_id)
        self.assertEqual(task.assigned_node, "node1")

    def test_complete_task(self):
        task_id = self.scheduler.submit_task(TaskType.COMPUTE, TaskPriority.NORMAL, {"job": "test"})
        self.scheduler.assign_task(task_id, "node1")
        self.scheduler.start_task(task_id)
        result = self.scheduler.complete_task(task_id, "success")
        self.assertTrue(result)
        task = self.scheduler.get_task(task_id)
        self.assertEqual(task.status, TaskStatus.COMPLETED)

    def test_fail_task(self):
        task_id = self.scheduler.submit_task(TaskType.COMPUTE, TaskPriority.NORMAL, {"job": "test"})
        self.scheduler.assign_task(task_id, "node1")
        self.scheduler.start_task(task_id)
        result = self.scheduler.fail_task(task_id, "error")
        self.assertTrue(result)
        task = self.scheduler.get_task(task_id)
        self.assertEqual(task.status, TaskStatus.FAILED)

    def test_get_pending_tasks(self):
        self.scheduler.submit_task(TaskType.COMPUTE, TaskPriority.NORMAL, {"job": "test1"})
        self.scheduler.submit_task(TaskType.IO, TaskPriority.HIGH, {"job": "test2"})
        pending = self.scheduler.get_pending_tasks()
        self.assertEqual(len(pending), 2)

    def test_get_tasks_by_node(self):
        task_id = self.scheduler.submit_task(TaskType.COMPUTE, TaskPriority.NORMAL, {"job": "test"})
        self.scheduler.assign_task(task_id, "node1")
        tasks = self.scheduler.get_tasks_by_node("node1")
        self.assertEqual(len(tasks), 1)

    def test_priority_ordering(self):
        self.scheduler.submit_task(TaskType.COMPUTE, TaskPriority.LOW, {"job": "low"})
        self.scheduler.submit_task(TaskType.COMPUTE, TaskPriority.CRITICAL, {"job": "critical"})
        self.scheduler.submit_task(TaskType.COMPUTE, TaskPriority.HIGH, {"job": "high"})
        # get_next_task should return highest priority task
        next_task = self.scheduler.get_next_task({"node1": 10})
        self.assertIsNotNone(next_task)
        self.assertEqual(next_task.priority, TaskPriority.CRITICAL)

    def test_global_singleton(self):
        scheduler2 = get_task_scheduler()
        self.assertIs(self.scheduler, scheduler2)


class TestStateSyncManager(unittest.TestCase):
    """Test StateSyncManager module (Stage 400)"""

    def setUp(self):
        reset_state_sync_manager()
        self.manager = get_state_sync_manager()

    def test_register_unregister(self):
        result = self.manager.register_node("node1", {"key": "value1"})
        self.assertTrue(result)
        result = self.manager.unregister_node("node1")
        self.assertTrue(result)

    def test_update_get_state(self):
        self.manager.register_node("node1", {"key": "value1"})
        result = self.manager.update_state("node1", {"key": "value2"})
        self.assertTrue(result)
        state = self.manager.get_state("node1")
        self.assertEqual(state["key"], "value2")

    def test_create_snapshot(self):
        self.manager.register_node("node1", {"key": "value1"})
        snapshot = self.manager.create_snapshot("node1")
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.node_id, "node1")

    def test_compare_states(self):
        self.manager.register_node("node1", {"key": "value1"})
        self.manager.register_node("node2", {"key": "value2"})
        diff = self.manager.compare_states("node1", "node2")
        self.assertIsNotNone(diff)

    def test_sync_state(self):
        self.manager.register_node("node1", {"key": "value1", "shared": "x"})
        self.manager.register_node("node2", {"key": "value2", "shared": "x"})
        result = self.manager.sync_state("node1", "node2", SyncStrategy.INCREMENTAL)
        self.assertTrue(result)

    def test_resolve_conflict_latest(self):
        self.manager.register_node("node1", {"key": "value1"})
        self.manager.register_node("node2", {"key": "value2"})
        result = self.manager.resolve_conflict("node1", "node2", "latest")
        self.assertIsNotNone(result)

    def test_get_sync_status(self):
        self.manager.register_node("node1", {"key": "value1"})
        status = self.manager.get_sync_status("node1")
        self.assertEqual(status, SyncStatus.SYNCED)

    def test_get_version(self):
        self.manager.register_node("node1", {"key": "value1"})
        version = self.manager.get_version("node1")
        self.assertEqual(version, 1)
        self.manager.update_state("node1", {"key": "value2"})
        version = self.manager.get_version("node1")
        self.assertEqual(version, 2)

    def test_get_all_nodes(self):
        self.manager.register_node("node1", {"key": "value1"})
        self.manager.register_node("node2", {"key": "value2"})
        nodes = self.manager.get_all_nodes()
        self.assertEqual(len(nodes), 2)

    def test_global_singleton(self):
        manager2 = get_state_sync_manager()
        self.assertIs(self.manager, manager2)


class TestDataStructures(unittest.TestCase):
    """Test all data structures and enums"""

    def test_node_status_enum(self):
        self.assertEqual(len(NodeStatus), 5)
        self.assertIn(NodeStatus.ONLINE, list(NodeStatus))

    def test_node_role_enum(self):
        self.assertEqual(len(NodeRole), 4)
        self.assertIn(NodeRole.LEADER, list(NodeRole))

    def test_proposal_status_enum(self):
        self.assertEqual(len(ProposalStatus), 5)
        self.assertIn(ProposalStatus.ACCEPTED, list(ProposalStatus))

    def test_vote_type_enum(self):
        self.assertEqual(len(VoteType), 3)
        self.assertIn(VoteType.YES, list(VoteType))

    def test_lock_status_enum(self):
        self.assertEqual(len(LockStatus), 3)
        self.assertIn(LockStatus.LOCKED, list(LockStatus))

    def test_lock_type_enum(self):
        self.assertEqual(len(LockType), 2)
        self.assertIn(LockType.EXCLUSIVE, list(LockType))

    def test_task_status_enum(self):
        self.assertEqual(len(TaskStatus), 6)
        self.assertIn(TaskStatus.RUNNING, list(TaskStatus))

    def test_task_priority_enum(self):
        self.assertEqual(len(TaskPriority), 4)
        self.assertIn(TaskPriority.HIGH, list(TaskPriority))

    def test_task_type_enum(self):
        self.assertEqual(len(TaskType), 4)
        self.assertIn(TaskType.COMPUTE, list(TaskType))

    def test_sync_status_enum(self):
        self.assertEqual(len(SyncStatus), 5)
        self.assertIn(SyncStatus.SYNCED, list(SyncStatus))

    def test_sync_strategy_enum(self):
        self.assertEqual(len(SyncStrategy), 4)
        self.assertIn(SyncStrategy.INCREMENTAL, list(SyncStrategy))


if __name__ == '__main__':
    unittest.main()
