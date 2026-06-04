"""
Distributed Lock module for the Agent Reliable Memory System.

Design Principles:
1. First Principles: deterministic rules, no model dependencies
2. Thread-safe using threading.RLock
3. Global singleton via get_distributed_lock_manager() with double-checked locking
4. Use Python dataclasses for data structures, Enum for types
5. Minimal dependencies, no circular dependencies
"""

import time
import uuid
import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional


class LockStatus(Enum):
    """Status of a distributed lock."""
    FREE = auto()
    LOCKED = auto()
    EXPIRED = auto()


class LockType(Enum):
    """Type of a distributed lock."""
    EXCLUSIVE = auto()
    SHARED = auto()


@dataclass
class LockRecord:
    """Record representing a single distributed lock."""
    lock_id: str
    resource_id: str
    owner_id: str
    lock_type: LockType
    status: LockStatus
    acquired_at: float
    expires_at: float
    metadata: Dict = field(default_factory=dict)


class DistributedLockManager:
    """Thread-safe distributed lock manager with FIFO wait queues and automatic expiration."""

    def __init__(self) -> None:
        self._locks: Dict[str, LockRecord] = {}
        self._wait_queues: Dict[str, List[str]] = {}
        self._lock = threading.RLock()

    def acquire_lock(
        self,
        resource_id: str,
        owner_id: str,
        lock_type: LockType = LockType.EXCLUSIVE,
        timeout_ms: int = 10000,
        ttl_seconds: int = 30,
    ) -> Optional[LockRecord]:
        """Acquire a lock on a resource.

        For EXCLUSIVE locks, only one owner is allowed.
        For SHARED locks, multiple readers are allowed concurrently.
        If the lock cannot be acquired immediately, the owner is placed in a FIFO wait queue.

        Args:
            resource_id: Identifier of the resource to lock.
            owner_id: Identifier of the lock owner.
            lock_type: Type of lock (EXCLUSIVE or SHARED).
            timeout_ms: Maximum time to wait for the lock in milliseconds.
            ttl_seconds: Time-to-live for the lock in seconds.

        Returns:
            LockRecord if the lock was acquired, None otherwise.
        """
        deadline = time.time() + (timeout_ms / 1000.0)
        lock_id = str(uuid.uuid4())

        with self._lock:
            # Ensure wait queue exists for this resource
            if resource_id not in self._wait_queues:
                self._wait_queues[resource_id] = []

            # Add owner to wait queue if not already present
            if owner_id not in self._wait_queues[resource_id]:
                self._wait_queues[resource_id].append(owner_id)

        while time.time() < deadline:
            with self._lock:
                now = time.time()

                # Clean up expired locks for this resource first
                self._cleanup_resource_expired(resource_id, now)

                # Check if this owner is at the front of the wait queue
                queue = self._wait_queues.get(resource_id, [])
                if queue and queue[0] != owner_id:
                    # Not our turn yet
                    pass
                else:
                    # Try to acquire
                    current_locks = [
                        lr
                        for lr in self._locks.values()
                        if lr.resource_id == resource_id and lr.status == LockStatus.LOCKED
                    ]

                    if not current_locks:
                        # No existing lock, acquire immediately
                        record = LockRecord(
                            lock_id=lock_id,
                            resource_id=resource_id,
                            owner_id=owner_id,
                            lock_type=lock_type,
                            status=LockStatus.LOCKED,
                            acquired_at=now,
                            expires_at=now + ttl_seconds,
                            metadata={},
                        )
                        self._locks[lock_id] = record
                        # Remove from wait queue
                        if owner_id in self._wait_queues[resource_id]:
                            self._wait_queues[resource_id].remove(owner_id)
                        return record

                    if lock_type == LockType.SHARED:
                        # Check if all existing locks are shared
                        all_shared = all(lr.lock_type == LockType.SHARED for lr in current_locks)
                        if all_shared:
                            record = LockRecord(
                                lock_id=lock_id,
                                resource_id=resource_id,
                                owner_id=owner_id,
                                lock_type=lock_type,
                                status=LockStatus.LOCKED,
                                acquired_at=now,
                                expires_at=now + ttl_seconds,
                                metadata={},
                            )
                            self._locks[lock_id] = record
                            if owner_id in self._wait_queues[resource_id]:
                                self._wait_queues[resource_id].remove(owner_id)
                            return record
                        # If there is an exclusive lock, must wait
                    else:
                        # EXCLUSIVE lock requested but resource is already locked
                        pass

            # Brief sleep before retrying
            time.sleep(0.01)

        # Timeout reached
        with self._lock:
            if resource_id in self._wait_queues and owner_id in self._wait_queues[resource_id]:
                self._wait_queues[resource_id].remove(owner_id)
        return None

    def release_lock(self, lock_id: str) -> bool:
        """Release a lock by its lock_id.

        Args:
            lock_id: The unique identifier of the lock.

        Returns:
            True if the lock was found and released, False otherwise.
        """
        with self._lock:
            record = self._locks.get(lock_id)
            if record is None:
                return False
            record.status = LockStatus.FREE
            del self._locks[lock_id]
            return True

    def release_by_resource(self, resource_id: str, owner_id: str) -> bool:
        """Release all locks held by an owner on a specific resource.

        Args:
            resource_id: The resource identifier.
            owner_id: The owner identifier.

        Returns:
            True if at least one lock was found and released, False otherwise.
        """
        released = False
        with self._lock:
            to_remove = [
                lid
                for lid, lr in self._locks.items()
                if lr.resource_id == resource_id and lr.owner_id == owner_id
            ]
            for lid in to_remove:
                self._locks[lid].status = LockStatus.FREE
                del self._locks[lid]
                released = True
        return released

    def get_lock(self, lock_id: str) -> Optional[LockRecord]:
        """Get a lock record by its lock_id.

        Args:
            lock_id: The unique identifier of the lock.

        Returns:
            The LockRecord if found, None otherwise.
        """
        with self._lock:
            record = self._locks.get(lock_id)
            if record is not None and record.status == LockStatus.LOCKED and time.time() > record.expires_at:
                record.status = LockStatus.EXPIRED
            return record

    def get_locks_by_owner(self, owner_id: str) -> List[LockRecord]:
        """Get all active locks owned by a specific owner.

        Args:
            owner_id: The owner identifier.

        Returns:
            List of LockRecord objects.
        """
        with self._lock:
            now = time.time()
            result = []
            for lr in self._locks.values():
                if lr.owner_id == owner_id:
                    if lr.status == LockStatus.LOCKED and now > lr.expires_at:
                        lr.status = LockStatus.EXPIRED
                    if lr.status == LockStatus.LOCKED:
                        result.append(lr)
            return result

    def get_locks_by_resource(self, resource_id: str) -> List[LockRecord]:
        """Get all active locks on a specific resource.

        Args:
            resource_id: The resource identifier.

        Returns:
            List of LockRecord objects.
        """
        with self._lock:
            now = time.time()
            result = []
            for lr in self._locks.values():
                if lr.resource_id == resource_id:
                    if lr.status == LockStatus.LOCKED and now > lr.expires_at:
                        lr.status = LockStatus.EXPIRED
                    if lr.status == LockStatus.LOCKED:
                        result.append(lr)
            return result

    def is_locked(self, resource_id: str) -> bool:
        """Check if a resource is currently locked.

        Args:
            resource_id: The resource identifier.

        Returns:
            True if the resource has at least one active lock, False otherwise.
        """
        with self._lock:
            now = time.time()
            for lr in self._locks.values():
                if lr.resource_id == resource_id:
                    if lr.status == LockStatus.LOCKED and now > lr.expires_at:
                        lr.status = LockStatus.EXPIRED
                    if lr.status == LockStatus.LOCKED:
                        return True
            return False

    def get_lock_owner(self, resource_id: str) -> Optional[str]:
        """Get the owner of an exclusive lock on a resource.

        Args:
            resource_id: The resource identifier.

        Returns:
            The owner_id if an exclusive lock exists, None otherwise.
            For shared locks, returns None.
        """
        with self._lock:
            now = time.time()
            for lr in self._locks.values():
                if lr.resource_id == resource_id and lr.lock_type == LockType.EXCLUSIVE:
                    if lr.status == LockStatus.LOCKED and now > lr.expires_at:
                        lr.status = LockStatus.EXPIRED
                    if lr.status == LockStatus.LOCKED:
                        return lr.owner_id
            return None

    def extend_lock(self, lock_id: str, additional_seconds: int) -> bool:
        """Extend the expiration time of an existing lock.

        Args:
            lock_id: The unique identifier of the lock.
            additional_seconds: Number of seconds to add to the current expiration.

        Returns:
            True if the lock was found and extended, False otherwise.
        """
        with self._lock:
            record = self._locks.get(lock_id)
            if record is None:
                return False
            if record.status != LockStatus.LOCKED:
                return False
            now = time.time()
            if now > record.expires_at:
                record.status = LockStatus.EXPIRED
                return False
            record.expires_at = record.expires_at + additional_seconds
            return True

    def get_waiting_queue(self, resource_id: str) -> List[str]:
        """Get the FIFO wait queue for a resource.

        Args:
            resource_id: The resource identifier.

        Returns:
            List of owner_ids waiting for the resource.
        """
        with self._lock:
            return list(self._wait_queues.get(resource_id, []))

    def cleanup_expired(self) -> int:
        """Remove all expired locks globally.

        Returns:
            Number of expired locks removed.
        """
        removed = 0
        with self._lock:
            now = time.time()
            to_remove = [
                lid
                for lid, lr in self._locks.items()
                if lr.status == LockStatus.LOCKED and now > lr.expires_at
            ]
            for lid in to_remove:
                self._locks[lid].status = LockStatus.EXPIRED
                del self._locks[lid]
                removed += 1
        return removed

    def get_statistics(self) -> Dict:
        """Get statistics about the current state of the lock manager.

        Returns:
            Dictionary with counts of locks, wait queues, etc.
        """
        with self._lock:
            now = time.time()
            total_locks = len(self._locks)
            expired_count = sum(
                1 for lr in self._locks.values()
                if lr.status == LockStatus.LOCKED and now > lr.expires_at
            )
            active_count = total_locks - expired_count
            exclusive_count = sum(
                1 for lr in self._locks.values()
                if lr.lock_type == LockType.EXCLUSIVE and lr.status == LockStatus.LOCKED and now <= lr.expires_at
            )
            shared_count = sum(
                1 for lr in self._locks.values()
                if lr.lock_type == LockType.SHARED and lr.status == LockStatus.LOCKED and now <= lr.expires_at
            )
            wait_queue_count = len(self._wait_queues)
            waiting_owners = sum(len(q) for q in self._wait_queues.values())
            return {
                "total_locks": total_locks,
                "active_locks": active_count,
                "expired_locks": expired_count,
                "exclusive_locks": exclusive_count,
                "shared_locks": shared_count,
                "wait_queue_resources": wait_queue_count,
                "waiting_owners": waiting_owners,
            }

    def _cleanup_resource_expired(self, resource_id: str, now: float) -> None:
        """Internal helper to clean up expired locks for a specific resource.

        Must be called while holding self._lock.
        """
        to_remove = [
            lid
            for lid, lr in self._locks.items()
            if lr.resource_id == resource_id and lr.status == LockStatus.LOCKED and now > lr.expires_at
        ]
        for lid in to_remove:
            self._locks[lid].status = LockStatus.EXPIRED
            del self._locks[lid]


# Global singleton instance and lock
_distributed_lock_manager_instance: Optional[DistributedLockManager] = None
_distributed_lock_manager_lock = threading.Lock()


def get_distributed_lock_manager() -> DistributedLockManager:
    """Get the global singleton DistributedLockManager instance.

    Uses double-checked locking for thread-safe initialization.

    Returns:
        The global DistributedLockManager instance.
    """
    global _distributed_lock_manager_instance
    if _distributed_lock_manager_instance is None:
        with _distributed_lock_manager_lock:
            if _distributed_lock_manager_instance is None:
                _distributed_lock_manager_instance = DistributedLockManager()
    return _distributed_lock_manager_instance


def reset_distributed_lock_manager() -> None:
    """Reset the global singleton instance. Intended for testing use only."""
    global _distributed_lock_manager_instance
    with _distributed_lock_manager_lock:
        _distributed_lock_manager_instance = None
