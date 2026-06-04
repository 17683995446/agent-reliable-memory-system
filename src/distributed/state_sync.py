"""
State Synchronization Module for the Agent Reliable Memory System (Stage 400).

Design Principles:
1. First Principles: deterministic rules, no model dependencies.
2. Thread-safe using threading.RLock.
3. Global singleton via get_state_sync_manager() with double-checked locking.
4. Use Python dataclasses for data structures, Enum for types.
5. Minimal dependencies, no circular dependencies.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class SyncStatus(Enum):
    """Enumeration of possible synchronization statuses for a node."""
    SYNCED = "synced"
    SYNCING = "syncing"
    CONFLICT = "conflict"
    DIVERGED = "diverged"
    ERROR = "error"


class SyncStrategy(Enum):
    """Enumeration of available synchronization strategies."""
    FULL = "full"
    INCREMENTAL = "incremental"
    DELTA = "delta"
    EVENT_BASED = "event_based"


@dataclass
class StateSnapshot:
    """Represents an immutable snapshot of a node's state at a point in time."""
    snapshot_id: str
    node_id: str
    state_data: Dict[str, Any]
    version: int
    timestamp: float
    checksum: str


@dataclass
class StateDiff:
    """Represents the difference between two versions of a node's state."""
    diff_id: str
    from_version: int
    to_version: int
    changes: Dict[str, Any]
    timestamp: float


class StateSyncManager:
    """
    Manages distributed state synchronization across registered nodes.

    Thread-safe via internal RLock. Use get_state_sync_manager() to obtain
    the global singleton instance.
    """

    def __init__(self) -> None:
        self._states: Dict[str, Dict[str, Any]] = {}
        self._snapshots: Dict[str, List[StateSnapshot]] = {}
        self._versions: Dict[str, int] = {}
        self._statuses: Dict[str, SyncStatus] = {}
        self._lock: threading.RLock = threading.RLock()

    # ------------------------------------------------------------------ #
    # Node lifecycle
    # ------------------------------------------------------------------ #

    def register_node(self, node_id: str, initial_state: Dict[str, Any]) -> bool:
        """Register a new node with an initial state."""
        with self._lock:
            if node_id in self._states:
                return False
            self._states[node_id] = dict(initial_state)
            self._versions[node_id] = 1
            self._statuses[node_id] = SyncStatus.SYNCED
            self._snapshots[node_id] = []
            self.create_snapshot(node_id)
            return True

    def unregister_node(self, node_id: str) -> bool:
        """Remove a node and all associated data."""
        with self._lock:
            if node_id not in self._states:
                return False
            del self._states[node_id]
            del self._versions[node_id]
            del self._statuses[node_id]
            del self._snapshots[node_id]
            return True

    # ------------------------------------------------------------------ #
    # State access & mutation
    # ------------------------------------------------------------------ #

    def update_state(self, node_id: str, new_state: Dict[str, Any]) -> bool:
        """Replace the state of a node, bump its version, and create a snapshot."""
        with self._lock:
            if node_id not in self._states:
                return False
            self._states[node_id] = dict(new_state)
            self._versions[node_id] = self._versions.get(node_id, 0) + 1
            self._statuses[node_id] = SyncStatus.SYNCED
            self.create_snapshot(node_id)
            return True

    def get_state(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Return a shallow copy of the current state for a node."""
        with self._lock:
            state = self._states.get(node_id)
            return dict(state) if state is not None else None

    # ------------------------------------------------------------------ #
    # Snapshots
    # ------------------------------------------------------------------ #

    def create_snapshot(self, node_id: str) -> StateSnapshot:
        """Persist a snapshot of the current node state."""
        with self._lock:
            if node_id not in self._states:
                raise ValueError(f"Node '{node_id}' is not registered.")
            state_data = dict(self._states[node_id])
            version = self._versions[node_id]
            checksum = self._compute_checksum(state_data)
            snapshot = StateSnapshot(
                snapshot_id=str(uuid.uuid4()),
                node_id=node_id,
                state_data=state_data,
                version=version,
                timestamp=time.time(),
                checksum=checksum,
            )
            self._snapshots[node_id].append(snapshot)
            return snapshot

    def get_snapshots(self, node_id: str) -> List[StateSnapshot]:
        """Return all stored snapshots for a node."""
        with self._lock:
            return list(self._snapshots.get(node_id, []))

    # ------------------------------------------------------------------ #
    # Comparison & diff
    # ------------------------------------------------------------------ #

    def compare_states(self, node_a: str, node_b: str) -> StateDiff:
        """Compare two nodes and return a diff describing changes from A to B."""
        with self._lock:
            state_a = self._states.get(node_a, {})
            state_b = self._states.get(node_b, {})
            version_a = self._versions.get(node_a, 0)
            version_b = self._versions.get(node_b, 0)

            changes: Dict[str, Any] = {}
            all_keys = set(state_a.keys()) | set(state_b.keys())
            for key in all_keys:
                if state_a.get(key) != state_b.get(key):
                    changes[key] = state_b.get(key)

            return StateDiff(
                diff_id=str(uuid.uuid4()),
                from_version=version_a,
                to_version=version_b,
                changes=changes,
                timestamp=time.time(),
            )

    # ------------------------------------------------------------------ #
    # Synchronization
    # ------------------------------------------------------------------ #

    def sync_state(
        self,
        source_node: str,
        target_node: str,
        strategy: SyncStrategy = SyncStrategy.INCREMENTAL,
    ) -> bool:
        """
        Synchronize state from source_node to target_node.

        Supports FULL, INCREMENTAL, DELTA, and EVENT_BASED strategies.
        """
        with self._lock:
            if source_node not in self._states or target_node not in self._states:
                return False

            self._statuses[target_node] = SyncStatus.SYNCING

            source_state = self._states[source_node]
            target_state = self._states[target_node]

            try:
                if strategy == SyncStrategy.FULL:
                    self._states[target_node] = dict(source_state)
                elif strategy == SyncStrategy.INCREMENTAL:
                    changed = self._incremental_changes(source_state, target_state)
                    target_state.update(changed)
                    self._states[target_node] = target_state
                elif strategy == SyncStrategy.DELTA:
                    changed = self._delta_changes(source_state, target_state)
                    target_state.update(changed)
                    self._states[target_node] = target_state
                elif strategy == SyncStrategy.EVENT_BASED:
                    # Event-based: apply only keys present in source but changed relative to target
                    changed = self._incremental_changes(source_state, target_state)
                    target_state.update(changed)
                    self._states[target_node] = target_state
                else:
                    self._statuses[target_node] = SyncStatus.ERROR
                    return False

                self._versions[target_node] = self._versions.get(target_node, 0) + 1
                self._statuses[target_node] = SyncStatus.SYNCED
                self.create_snapshot(target_node)
                return True
            except Exception:
                self._statuses[target_node] = SyncStatus.ERROR
                return False

    def _incremental_changes(
        self, source: Dict[str, Any], target: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Return only the keys from source that differ from target."""
        changes: Dict[str, Any] = {}
        for key, value in source.items():
            if target.get(key) != value:
                changes[key] = value
        return changes

    def _delta_changes(
        self, source: Dict[str, Any], target: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Return all differences (additions, modifications, deletions represented as None)."""
        changes: Dict[str, Any] = {}
        all_keys = set(source.keys()) | set(target.keys())
        for key in all_keys:
            if source.get(key) != target.get(key):
                changes[key] = source.get(key)
        # Remove keys that are explicitly deleted (None) so they disappear from target
        deletions = {k for k, v in changes.items() if v is None}
        for k in deletions:
            changes.pop(k, None)
        return changes

    # ------------------------------------------------------------------ #
    # Conflict resolution
    # ------------------------------------------------------------------ #

    def resolve_conflict(
        self,
        node_a: str,
        node_b: str,
        resolution_strategy: str = "latest",
    ) -> Dict[str, Any]:
        """
        Resolve state divergence between two nodes.

        Strategies:
          - "latest": pick the state with the higher version.
          - "merge": deep-merge both states; on key collision, higher version wins.
        """
        with self._lock:
            state_a = self._states.get(node_a, {})
            state_b = self._states.get(node_b, {})
            version_a = self._versions.get(node_a, 0)
            version_b = self._versions.get(node_b, 0)

            if resolution_strategy == "latest":
                if version_a >= version_b:
                    resolved = dict(state_a)
                    winner = node_a
                else:
                    resolved = dict(state_b)
                    winner = node_b
                self._states[node_a] = dict(resolved)
                self._states[node_b] = dict(resolved)
                self._versions[node_a] = max(version_a, version_b) + 1
                self._versions[node_b] = max(version_a, version_b) + 1
                self._statuses[node_a] = SyncStatus.SYNCED
                self._statuses[node_b] = SyncStatus.SYNCED
                self.create_snapshot(node_a)
                self.create_snapshot(node_b)
                return resolved

            if resolution_strategy == "merge":
                merged: Dict[str, Any] = {}
                all_keys = set(state_a.keys()) | set(state_b.keys())
                for key in all_keys:
                    if key in state_a and key not in state_b:
                        merged[key] = state_a[key]
                    elif key in state_b and key not in state_a:
                        merged[key] = state_b[key]
                    else:
                        # Both have the key: higher version wins; if equal prefer A
                        merged[key] = state_a[key] if version_a >= version_b else state_b[key]
                self._states[node_a] = dict(merged)
                self._states[node_b] = dict(merged)
                self._versions[node_a] = max(version_a, version_b) + 1
                self._versions[node_b] = max(version_a, version_b) + 1
                self._statuses[node_a] = SyncStatus.SYNCED
                self._statuses[node_b] = SyncStatus.SYNCED
                self.create_snapshot(node_a)
                self.create_snapshot(node_b)
                return merged

            raise ValueError(f"Unsupported resolution_strategy: {resolution_strategy}")

    # ------------------------------------------------------------------ #
    # Queries & metadata
    # ------------------------------------------------------------------ #

    def get_sync_status(self, node_id: str) -> SyncStatus:
        """Return the current synchronization status of a node."""
        with self._lock:
            return self._statuses.get(node_id, SyncStatus.ERROR)

    def get_all_nodes(self) -> List[str]:
        """Return a list of all registered node IDs."""
        with self._lock:
            return list(self._states.keys())

    def get_version(self, node_id: str) -> int:
        """Return the current version vector for a node."""
        with self._lock:
            return self._versions.get(node_id, 0)

    def get_statistics(self) -> Dict[str, Any]:
        """Return aggregate statistics about the manager's current state."""
        with self._lock:
            total_nodes = len(self._states)
            status_counts: Dict[str, int] = {}
            for status in self._statuses.values():
                status_counts[status.value] = status_counts.get(status.value, 0) + 1
            total_snapshots = sum(len(snaps) for snaps in self._snapshots.values())
            return {
                "total_nodes": total_nodes,
                "status_counts": status_counts,
                "total_snapshots": total_snapshots,
                "versions": dict(self._versions),
            }

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _compute_checksum(state_data: Dict[str, Any]) -> str:
        """Compute an MD5 checksum over a deterministic JSON serialization."""
        canonical = json.dumps(state_data, sort_keys=True, separators=(",", ":"))
        return hashlib.md5(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------- #
# Singleton machinery with double-checked locking
# ---------------------------------------------------------------------- #

_singleton_instance: Optional[StateSyncManager] = None
_singleton_lock: threading.Lock = threading.Lock()


def get_state_sync_manager() -> StateSyncManager:
    """Return the global StateSyncManager singleton (thread-safe)."""
    global _singleton_instance
    if _singleton_instance is None:
        with _singleton_lock:
            if _singleton_instance is None:
                _singleton_instance = StateSyncManager()
    return _singleton_instance


def reset_state_sync_manager() -> None:
    """Reset the global singleton (useful for testing)."""
    global _singleton_instance
    with _singleton_lock:
        _singleton_instance = None
