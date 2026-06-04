"""
Pipeline Orchestrator module for the Agent Reliable Memory System (Stage 389).

Design Principles:
1. First Principles: deterministic rules, no model dependencies
2. Thread-safe using threading.RLock
3. Global singleton via get_pipeline_orchestrator() with double-checked locking
4. Use Python dataclasses for data structures, Enum for types
5. Minimal dependencies, no circular dependencies
"""

from __future__ import annotations

import copy
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PipelineStatus(Enum):
    """Lifecycle states of a pipeline."""

    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StageStatus(Enum):
    """Lifecycle states of a pipeline stage."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PipelineStage:
    """Represents a single stage within a pipeline."""

    stage_id: str
    name: str
    transform_rule_id: str
    sink_id: str
    dependencies: List[str] = field(default_factory=list)
    status: StageStatus = StageStatus.PENDING
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Pipeline:
    """Represents a data processing pipeline."""

    pipeline_id: str
    name: str
    source_id: str
    stages: List[PipelineStage] = field(default_factory=list)
    status: PipelineStatus = PipelineStatus.CREATED
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class PipelineOrchestrator:
    """
    Thread-safe pipeline orchestrator with dependency resolution and parallel execution.

    Features:
    - Topological sort for stage ordering
    - Parallel stage execution where dependencies allow
    - Configurable retry (max 3 attempts)
    - In-memory pipeline state persistence
    """

    MAX_RETRIES: int = 3

    def __init__(self) -> None:
        self._pipelines: Dict[str, Pipeline] = {}
        self._stage_results: Dict[str, Dict[str, Any]] = {}
        self._lock: threading.RLock = threading.RLock()
        self._executor: ThreadPoolExecutor = ThreadPoolExecutor(
            max_workers=8, thread_name_prefix="pipeline_stage_"
        )
        # Track paused state per pipeline
        self._paused_flags: Dict[str, bool] = {}
        # Track cancelled state per pipeline
        self._cancelled_flags: Dict[str, bool] = {}

    # ------------------------------------------------------------------
    # Pipeline CRUD
    # ------------------------------------------------------------------

    def create_pipeline(
        self,
        name: str,
        source_id: str,
        stages_config: List[Dict[str, Any]],
    ) -> str:
        """
        Create a new pipeline from a stage configuration list.

        Args:
            name: Human-readable pipeline name.
            source_id: ID of the data source.
            stages_config: List of dicts with keys:
                - name (str)
                - transform_rule_id (str)
                - sink_id (str)
                - dependencies (List[str], optional)
                - metadata (Dict, optional)

        Returns:
            The generated pipeline_id.
        """
        pipeline_id = str(uuid.uuid4())
        stages: List[PipelineStage] = []

        for cfg in stages_config:
            stage = PipelineStage(
                stage_id=str(uuid.uuid4()),
                name=cfg["name"],
                transform_rule_id=cfg["transform_rule_id"],
                sink_id=cfg["sink_id"],
                dependencies=list(cfg.get("dependencies", [])),
                status=StageStatus.PENDING,
                metadata=dict(cfg.get("metadata", {})),
            )
            stages.append(stage)

        pipeline = Pipeline(
            pipeline_id=pipeline_id,
            name=name,
            source_id=source_id,
            stages=stages,
            status=PipelineStatus.CREATED,
        )

        with self._lock:
            self._pipelines[pipeline_id] = pipeline
            self._stage_results[pipeline_id] = {}
            self._paused_flags[pipeline_id] = False
            self._cancelled_flags[pipeline_id] = False

        return pipeline_id

    def delete_pipeline(self, pipeline_id: str) -> bool:
        """
        Delete a pipeline by ID.

        Returns:
            True if deleted, False if not found.
        """
        with self._lock:
            if pipeline_id not in self._pipelines:
                return False
            del self._pipelines[pipeline_id]
            self._stage_results.pop(pipeline_id, None)
            self._paused_flags.pop(pipeline_id, None)
            self._cancelled_flags.pop(pipeline_id, None)
            return True

    def get_pipeline(self, pipeline_id: str) -> Optional[Pipeline]:
        """
        Retrieve a pipeline by ID.

        Returns:
            Deep-copied Pipeline if found, else None.
        """
        with self._lock:
            pipeline = self._pipelines.get(pipeline_id)
            if pipeline is None:
                return None
            return copy.deepcopy(pipeline)

    def get_all_pipelines(self) -> List[Pipeline]:
        """Return a deep-copied list of all pipelines."""
        with self._lock:
            return [copy.deepcopy(p) for p in self._pipelines.values()]

    def get_running_pipelines(self) -> List[Pipeline]:
        """Return all pipelines with RUNNING status."""
        with self._lock:
            return [
                copy.deepcopy(p)
                for p in self._pipelines.values()
                if p.status == PipelineStatus.RUNNING
            ]

    # ------------------------------------------------------------------
    # Lifecycle controls
    # ------------------------------------------------------------------

    def start_pipeline(self, pipeline_id: str) -> bool:
        """
        Start executing a pipeline.

        Returns:
            True if started successfully.
        """
        with self._lock:
            pipeline = self._pipelines.get(pipeline_id)
            if pipeline is None:
                return False
            if pipeline.status not in (
                PipelineStatus.CREATED,
                PipelineStatus.PAUSED,
                PipelineStatus.FAILED,
            ):
                return False

            pipeline.status = PipelineStatus.RUNNING
            pipeline.started_at = datetime.utcnow()
            pipeline.completed_at = None
            self._paused_flags[pipeline_id] = False
            self._cancelled_flags[pipeline_id] = False

            # Reset stage statuses for a fresh run
            for stage in pipeline.stages:
                stage.status = StageStatus.PENDING
            self._stage_results[pipeline_id] = {}

        # Execute outside the lock to avoid holding it during long-running work
        self._execute_pipeline(pipeline_id)
        return True

    def pause_pipeline(self, pipeline_id: str) -> bool:
        """
        Pause a running pipeline.

        Returns:
            True if the pipeline was running and is now paused.
        """
        with self._lock:
            pipeline = self._pipelines.get(pipeline_id)
            if pipeline is None or pipeline.status != PipelineStatus.RUNNING:
                return False
            pipeline.status = PipelineStatus.PAUSED
            self._paused_flags[pipeline_id] = True
            return True

    def resume_pipeline(self, pipeline_id: str) -> bool:
        """
        Resume a paused pipeline.

        Returns:
            True if the pipeline was paused and is now running.
        """
        with self._lock:
            pipeline = self._pipelines.get(pipeline_id)
            if pipeline is None or pipeline.status != PipelineStatus.PAUSED:
                return False
            pipeline.status = PipelineStatus.RUNNING
            self._paused_flags[pipeline_id] = False

        self._execute_pipeline(pipeline_id)
        return True

    def cancel_pipeline(self, pipeline_id: str) -> bool:
        """
        Cancel a pipeline.

        Returns:
            True if the pipeline exists and was not already completed.
        """
        with self._lock:
            pipeline = self._pipelines.get(pipeline_id)
            if pipeline is None:
                return False
            if pipeline.status in (
                PipelineStatus.COMPLETED,
                PipelineStatus.CANCELLED,
            ):
                return False
            pipeline.status = PipelineStatus.CANCELLED
            self._cancelled_flags[pipeline_id] = True
            return True

    # ------------------------------------------------------------------
    # Status queries
    # ------------------------------------------------------------------

    def get_pipeline_status(self, pipeline_id: str) -> Optional[PipelineStatus]:
        """Return the current status of a pipeline."""
        with self._lock:
            pipeline = self._pipelines.get(pipeline_id)
            if pipeline is None:
                return None
            return pipeline.status

    def get_stage_status(self, pipeline_id: str, stage_id: str) -> Optional[StageStatus]:
        """Return the current status of a specific stage."""
        with self._lock:
            pipeline = self._pipelines.get(pipeline_id)
            if pipeline is None:
                return None
            for stage in pipeline.stages:
                if stage.stage_id == stage_id:
                    return stage.status
            return None

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def get_pipeline_statistics(self, pipeline_id: str) -> Dict[str, Any]:
        """
        Retrieve statistics for a single pipeline.

        Returns:
            Dict with pipeline metrics, or empty dict if not found.
        """
        with self._lock:
            pipeline = self._pipelines.get(pipeline_id)
            if pipeline is None:
                return {}

            stage_stats = []
            for stage in pipeline.stages:
                result = self._stage_results.get(pipeline_id, {}).get(stage.stage_id)
                stage_stats.append(
                    {
                        "stage_id": stage.stage_id,
                        "name": stage.name,
                        "status": stage.status.value,
                        "result": result,
                    }
                )

            return {
                "pipeline_id": pipeline_id,
                "name": pipeline.name,
                "status": pipeline.status.value,
                "source_id": pipeline.source_id,
                "stage_count": len(pipeline.stages),
                "stages": stage_stats,
                "created_at": pipeline.created_at.isoformat() if pipeline.created_at else None,
                "started_at": pipeline.started_at.isoformat() if pipeline.started_at else None,
                "completed_at": pipeline.completed_at.isoformat() if pipeline.completed_at else None,
            }

    def get_all_statistics(self) -> Dict[str, Any]:
        """
        Retrieve statistics for all pipelines.

        Returns:
            Dict with global metrics and per-pipeline details.
        """
        with self._lock:
            pipelines = list(self._pipelines.values())

        total_stages = sum(len(p.stages) for p in pipelines)
        status_counts: Dict[str, int] = {}
        for p in pipelines:
            status_counts[p.status.value] = status_counts.get(p.status.value, 0) + 1

        per_pipeline = {
            p.pipeline_id: self.get_pipeline_statistics(p.pipeline_id)
            for p in pipelines
        }

        return {
            "total_pipelines": len(pipelines),
            "total_stages": total_stages,
            "status_counts": status_counts,
            "pipelines": per_pipeline,
        }

    # ------------------------------------------------------------------
    # Execution engine
    # ------------------------------------------------------------------

    def _execute_pipeline(self, pipeline_id: str) -> None:
        """
        Execute pipeline stages respecting dependencies.

        This method runs the topological ordering and submits ready stages
        to the thread pool. It blocks until the pipeline completes, fails,
        is paused, or is cancelled.
        """
        with self._lock:
            pipeline = self._pipelines.get(pipeline_id)
            if pipeline is None:
                return

        # Build dependency graph
        stage_map: Dict[str, PipelineStage] = {}
        adjacency: Dict[str, Set[str]] = {}
        in_degree: Dict[str, int] = {}

        with self._lock:
            for stage in pipeline.stages:
                stage_map[stage.stage_id] = stage
                adjacency[stage.stage_id] = set()
                in_degree[stage.stage_id] = 0

            for stage in pipeline.stages:
                for dep in stage.dependencies:
                    if dep in adjacency:
                        adjacency[dep].add(stage.stage_id)
                        in_degree[stage.stage_id] += 1

        # Track completed / failed stages
        completed_stages: Set[str] = set()
        failed_stages: Set[str] = set()

        # Identify initially ready stages
        ready: List[str] = [
            sid for sid, deg in in_degree.items() if deg == 0
        ]

        # Set ready stages to RUNNING
        with self._lock:
            for sid in ready:
                stage = stage_map[sid]
                if stage.status == StageStatus.PENDING:
                    stage.status = StageStatus.RUNNING

        futures: Dict[str, Future[Any]] = {}

        while ready or futures:
            # Check cancellation
            with self._lock:
                if self._cancelled_flags.get(pipeline_id, False):
                    for sid, fut in futures.items():
                        if not fut.done():
                            fut.cancel()
                    pipeline.status = PipelineStatus.CANCELLED
                    pipeline.completed_at = datetime.utcnow()
                    return

                # Check pause
                if self._paused_flags.get(pipeline_id, False):
                    pipeline.status = PipelineStatus.PAUSED
                    for sid, fut in list(futures.items()):
                        if not fut.done():
                            fut.cancel()
                    return

            # Submit ready stages
            for sid in ready:
                if sid not in futures:
                    stage = stage_map[sid]
                    fut = self._executor.submit(
                        self._run_stage_with_retry, pipeline_id, stage
                    )
                    futures[sid] = fut
            ready.clear()

            # Gather completed futures
            done_sids: List[str] = []
            for sid, fut in list(futures.items()):
                if fut.done():
                    done_sids.append(sid)
                    try:
                        result = fut.result()
                    except Exception as exc:
                        result = {"success": False, "error": str(exc)}

                    with self._lock:
                        stage = stage_map[sid]
                        self._stage_results.setdefault(pipeline_id, {})[sid] = result
                        if result.get("success"):
                            stage.status = StageStatus.COMPLETED
                            completed_stages.add(sid)
                        else:
                            stage.status = StageStatus.FAILED
                            failed_stages.add(sid)
                            pipeline.status = PipelineStatus.FAILED
                            pipeline.completed_at = datetime.utcnow()
                            # Cancel remaining futures
                            for other_sid, other_fut in futures.items():
                                if other_sid != sid and not other_fut.done():
                                    other_fut.cancel()
                            return

            for sid in done_sids:
                futures.pop(sid, None)
                # Update in-degrees and discover newly ready stages
                for dependent in adjacency.get(sid, set()):
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0 and dependent not in completed_stages:
                        ready.append(dependent)
                        with self._lock:
                            stage_map[dependent].status = StageStatus.RUNNING

            if not ready and not futures:
                break

            # Small sleep to prevent tight spinning when waiting on futures
            if futures and not done_sids:
                time.sleep(0.01)

        # Finalize pipeline status
        with self._lock:
            pipeline = self._pipelines.get(pipeline_id)
            if pipeline is None:
                return
            if pipeline.status == PipelineStatus.RUNNING:
                if failed_stages:
                    pipeline.status = PipelineStatus.FAILED
                else:
                    pipeline.status = PipelineStatus.COMPLETED
            pipeline.completed_at = datetime.utcnow()

    def _run_stage_with_retry(
        self, pipeline_id: str, stage: PipelineStage
    ) -> Dict[str, Any]:
        """
        Execute a single stage with up to MAX_RETRIES attempts.

        Returns:
            Dict with keys: success (bool), stage_id, attempts, error (optional).
        """
        last_error: Optional[str] = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            # Check cancellation / pause before each attempt
            with self._lock:
                if self._cancelled_flags.get(pipeline_id, False):
                    return {
                        "success": False,
                        "stage_id": stage.stage_id,
                        "attempts": attempt,
                        "error": "Pipeline cancelled.",
                    }
                if self._paused_flags.get(pipeline_id, False):
                    return {
                        "success": False,
                        "stage_id": stage.stage_id,
                        "attempts": attempt,
                        "error": "Pipeline paused.",
                    }

            try:
                result = self._execute_stage_logic(pipeline_id, stage)
                if result.get("success"):
                    result["attempts"] = attempt
                    return result
                last_error = result.get("error")
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)

        return {
            "success": False,
            "stage_id": stage.stage_id,
            "attempts": self.MAX_RETRIES,
            "error": last_error or "Unknown error after max retries.",
        }

    def _execute_stage_logic(
        self, pipeline_id: str, stage: PipelineStage
    ) -> Dict[str, Any]:
        """
        Deterministic stage execution logic.

        This is a placeholder that simulates stage execution. In a real
        deployment it would invoke the data transformer and sink modules.

        Returns:
            Dict with success flag and metadata.
        """
        # Simulate deterministic work
        # (In production, integrate with DataTransformer and DataSinkManager)
        return {
            "success": True,
            "stage_id": stage.stage_id,
            "pipeline_id": pipeline_id,
            "transform_rule_id": stage.transform_rule_id,
            "sink_id": stage.sink_id,
            "timestamp": datetime.utcnow().isoformat(),
        }

    # ------------------------------------------------------------------
    # Topological sort (public utility)
    # ------------------------------------------------------------------

    @staticmethod
    def topological_sort(stages: List[PipelineStage]) -> List[str]:
        """
        Return stage IDs in topologically sorted order.

        Raises:
            ValueError: If a circular dependency is detected.
        """
        stage_ids = {s.stage_id for s in stages}
        adjacency: Dict[str, Set[str]] = {s.stage_id: set() for s in stages}
        in_degree: Dict[str, int] = {s.stage_id: 0 for s in stages}

        for stage in stages:
            for dep in stage.dependencies:
                if dep in stage_ids:
                    adjacency[dep].add(stage.stage_id)
                    in_degree[stage.stage_id] += 1
                else:
                    raise ValueError(
                        f"Stage '{stage.stage_id}' depends on unknown stage '{dep}'."
                    )

        queue = [sid for sid, deg in in_degree.items() if deg == 0]
        result: List[str] = []

        while queue:
            current = queue.pop(0)
            result.append(current)
            for dependent in adjacency[current]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if len(result) != len(stages):
            raise ValueError("Circular dependency detected among pipeline stages.")

        return result

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Gracefully shut down the thread pool executor."""
        self._executor.shutdown(wait=True)


# ---------------------------------------------------------------------------
# Singleton management with double-checked locking
# ---------------------------------------------------------------------------

_singleton_instance: Optional[PipelineOrchestrator] = None
_singleton_lock = threading.Lock()


def get_pipeline_orchestrator() -> PipelineOrchestrator:
    """Return the global PipelineOrchestrator singleton (thread-safe)."""
    global _singleton_instance  # noqa: PLW0603
    if _singleton_instance is None:
        with _singleton_lock:
            if _singleton_instance is None:
                _singleton_instance = PipelineOrchestrator()
    return _singleton_instance


def reset_pipeline_orchestrator() -> None:
    """Reset the singleton instance (intended for testing)."""
    global _singleton_instance  # noqa: PLW0603
    with _singleton_lock:
        if _singleton_instance is not None:
            _singleton_instance.shutdown()
        _singleton_instance = None
