"""
Training Orchestrator module for the Agent Reliable Memory System.

This module provides deterministic, thread-safe training job management
with no external model dependencies. It follows first-principles design
using only Python standard library constructs.

Stage: 403
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional


class TrainingStatus(Enum):
    """Enumeration of possible training job statuses."""

    IDLE = auto()
    PREPARING = auto()
    TRAINING = auto()
    VALIDATING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()


@dataclass
class TrainingConfig:
    """Immutable configuration for a training run."""

    config_id: str
    model_id: str
    algorithm: str
    hyperparameters: Dict[str, Any] = field(default_factory=dict)
    epochs: int = 10
    batch_size: int = 32
    validation_split: float = 0.2


@dataclass
class TrainingJob:
    """Mutable state container for an active or historical training job."""

    job_id: str
    config_id: str
    model_id: str
    status: TrainingStatus = TrainingStatus.IDLE
    progress: float = 0.0
    metrics: Dict[str, Any] = field(default_factory=dict)
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    error: Optional[str] = None


class TrainingOrchestrator:
    """
    Thread-safe orchestrator for ML training jobs.

    Design principles:
    - Deterministic rules, no model dependencies.
    - All public methods are protected by an internal RLock.
    - Minimal surface area; no circular dependencies.
    """

    def __init__(self) -> None:
        self._configs: Dict[str, TrainingConfig] = {}
        self._jobs: Dict[str, TrainingJob] = {}
        self._lock: threading.RLock = threading.RLock()

    # ------------------------------------------------------------------
    # Configuration management
    # ------------------------------------------------------------------

    def create_config(
        self,
        model_id: str,
        algorithm: str,
        hyperparameters: Optional[Dict[str, Any]] = None,
        epochs: int = 10,
        batch_size: int = 32,
        validation_split: float = 0.2,
    ) -> str:
        """
        Register a new training configuration after validating hyperparameters.

        Returns:
            The generated config_id.
        """
        if hyperparameters is None:
            hyperparameters = {}

        self._validate_hyperparameters(hyperparameters)

        config_id = str(uuid.uuid4())
        config = TrainingConfig(
            config_id=config_id,
            model_id=model_id,
            algorithm=algorithm,
            hyperparameters=hyperparameters,
            epochs=epochs,
            batch_size=batch_size,
            validation_split=validation_split,
        )

        with self._lock:
            self._configs[config_id] = config

        return config_id

    def delete_config(self, config_id: str) -> bool:
        """
        Remove a configuration if it exists and is not referenced by an active job.

        Returns:
            True if the configuration was removed, False otherwise.
        """
        with self._lock:
            if config_id not in self._configs:
                return False

            for job in self._jobs.values():
                if job.config_id == config_id and job.status in {
                    TrainingStatus.PREPARING,
                    TrainingStatus.TRAINING,
                    TrainingStatus.VALIDATING,
                }:
                    return False

            del self._configs[config_id]
            return True

    # ------------------------------------------------------------------
    # Training lifecycle
    # ------------------------------------------------------------------

    def start_training(self, config_id: str) -> str:
        """
        Begin a new training job from a registered configuration.

        Simulates training preparation and immediately transitions to TRAINING.

        Returns:
            The generated job_id.

        Raises:
            KeyError: If the configuration does not exist.
        """
        with self._lock:
            if config_id not in self._configs:
                raise KeyError(f"Configuration '{config_id}' not found.")

            config = self._configs[config_id]
            job_id = str(uuid.uuid4())
            now = time.time()

            job = TrainingJob(
                job_id=job_id,
                config_id=config_id,
                model_id=config.model_id,
                status=TrainingStatus.PREPARING,
                progress=0.0,
                metrics={},
                start_time=now,
            )
            self._jobs[job_id] = job

            # Simulated transition: PREPARING -> TRAINING
            job.status = TrainingStatus.TRAINING

        return job_id

    def cancel_training(self, job_id: str) -> bool:
        """
        Cancel an active training job.

        Returns:
            True if the job was cancelled, False if it was already terminal.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False

            if job.status in {
                TrainingStatus.COMPLETED,
                TrainingStatus.FAILED,
                TrainingStatus.CANCELLED,
            }:
                return False

            job.status = TrainingStatus.CANCELLED
            job.end_time = time.time()
            return True

    def get_job(self, job_id: str) -> Optional[TrainingJob]:
        """Retrieve a single job by its identifier."""
        with self._lock:
            job = self._jobs.get(job_id)
            return None if job is None else self._copy_job(job)

    def get_jobs(self, status: Optional[TrainingStatus] = None) -> List[TrainingJob]:
        """
        Retrieve all jobs, optionally filtered by status.

        Returns:
            A list of copied TrainingJob instances.
        """
        with self._lock:
            jobs = self._jobs.values()
            if status is not None:
                jobs = [j for j in jobs if j.status == status]
            return [self._copy_job(j) for j in jobs]

    def get_active_jobs(self) -> List[TrainingJob]:
        """Return all jobs that are not in a terminal state."""
        terminal = {
            TrainingStatus.COMPLETED,
            TrainingStatus.FAILED,
            TrainingStatus.CANCELLED,
        }
        with self._lock:
            return [
                self._copy_job(j)
                for j in self._jobs.values()
                if j.status not in terminal
            ]

    def update_progress(
        self, job_id: str, progress: float, metrics: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Update the progress and optional metrics for an active training job.

        Progress is clamped to the range [0.0, 1.0].

        Returns:
            True if the update was applied, False otherwise.
        """
        if metrics is None:
            metrics = {}

        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False

            if job.status not in {
                TrainingStatus.PREPARING,
                TrainingStatus.TRAINING,
                TrainingStatus.VALIDATING,
            }:
                return False

            job.progress = max(0.0, min(1.0, progress))
            job.metrics.update(metrics)

            # Simulated transition: TRAINING -> VALIDATING at 100 %
            if job.progress >= 1.0 and job.status == TrainingStatus.TRAINING:
                job.status = TrainingStatus.VALIDATING

            return True

    def complete_training(self, job_id: str, final_metrics: Optional[Dict[str, Any]] = None) -> bool:
        """
        Mark a training job as successfully completed.

        Returns:
            True if the job was completed, False if it was already terminal.
        """
        if final_metrics is None:
            final_metrics = {}

        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False

            if job.status in {
                TrainingStatus.COMPLETED,
                TrainingStatus.FAILED,
                TrainingStatus.CANCELLED,
            }:
                return False

            job.status = TrainingStatus.COMPLETED
            job.progress = 1.0
            job.metrics.update(final_metrics)
            job.end_time = time.time()
            return True

    def fail_training(self, job_id: str, error: str) -> bool:
        """
        Mark a training job as failed with an error message.

        Returns:
            True if the job was marked failed, False if it was already terminal.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False

            if job.status in {
                TrainingStatus.COMPLETED,
                TrainingStatus.FAILED,
                TrainingStatus.CANCELLED,
            }:
                return False

            job.status = TrainingStatus.FAILED
            job.error = error
            job.end_time = time.time()
            return True

    # ------------------------------------------------------------------
    # Analytics / history
    # ------------------------------------------------------------------

    def get_best_job(self, model_id: str) -> Optional[TrainingJob]:
        """
        Return the completed job with the highest 'accuracy' metric for a model.

        If 'accuracy' is absent, falls back to the most recently completed job.
        """
        with self._lock:
            candidates = [
                j
                for j in self._jobs.values()
                if j.model_id == model_id and j.status == TrainingStatus.COMPLETED
            ]

            if not candidates:
                return None

            def _score(j: TrainingJob) -> float:
                return float(j.metrics.get("accuracy", -1.0))

            best = max(candidates, key=_score)
            return self._copy_job(best)

    def get_training_history(self, model_id: str) -> List[TrainingJob]:
        """Return all jobs (any status) associated with a given model, sorted by start time."""
        with self._lock:
            jobs = [
                self._copy_job(j)
                for j in self._jobs.values()
                if j.model_id == model_id
            ]

        jobs.sort(key=lambda j: j.start_time or 0.0)
        return jobs

    def get_statistics(self) -> Dict[str, Any]:
        """
        Compute aggregate statistics across all jobs.

        Returns:
            A dictionary with counts, averages, and best metrics.
        """
        with self._lock:
            total = len(self._jobs)
            counts = {s.name: 0 for s in TrainingStatus}
            for j in self._jobs.values():
                counts[j.status.name] += 1

            completed = [
                j for j in self._jobs.values() if j.status == TrainingStatus.COMPLETED
            ]
            avg_duration = 0.0
            if completed:
                durations = [
                    (j.end_time or j.start_time or 0.0) - (j.start_time or 0.0)
                    for j in completed
                ]
                avg_duration = sum(durations) / len(durations)

            best_accuracy = None
            for j in completed:
                acc = j.metrics.get("accuracy")
                if acc is not None:
                    if best_accuracy is None or acc > best_accuracy:
                        best_accuracy = acc

            return {
                "total_jobs": total,
                "status_counts": counts,
                "completed_jobs": len(completed),
                "average_duration": avg_duration,
                "best_accuracy": best_accuracy,
            }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_hyperparameters(hyperparameters: Dict[str, Any]) -> None:
        """
        Validate that hyperparameters contain only primitive, serialisable values.

        Raises:
            TypeError: If a value is not int, float, str, bool, or None.
        """
        allowed = (int, float, str, bool, type(None))
        for key, value in hyperparameters.items():
            if not isinstance(value, allowed):
                raise TypeError(
                    f"Hyperparameter '{key}' has unsupported type {type(value).__name__}. "
                    f"Allowed types: int, float, str, bool, None."
                )

    @staticmethod
    def _copy_job(job: TrainingJob) -> TrainingJob:
        """Return a shallow copy of a TrainingJob to prevent external mutation."""
        return TrainingJob(
            job_id=job.job_id,
            config_id=job.config_id,
            model_id=job.model_id,
            status=job.status,
            progress=job.progress,
            metrics=dict(job.metrics),
            start_time=job.start_time,
            end_time=job.end_time,
            error=job.error,
        )


# ----------------------------------------------------------------------
# Global singleton with double-checked locking
# ----------------------------------------------------------------------

_orchestrator_instance: Optional[TrainingOrchestrator] = None
_orchestrator_lock: threading.Lock = threading.Lock()


def get_training_orchestrator() -> TrainingOrchestrator:
    """
    Return the global TrainingOrchestrator singleton.

    Uses double-checked locking for thread-safe lazy initialisation.
    """
    global _orchestrator_instance

    if _orchestrator_instance is None:
        with _orchestrator_lock:
            if _orchestrator_instance is None:
                _orchestrator_instance = TrainingOrchestrator()

    return _orchestrator_instance


def reset_training_orchestrator() -> None:
    """
    Reset the global singleton to a fresh instance.

    Intended for testing only.
    """
    global _orchestrator_instance

    with _orchestrator_lock:
        _orchestrator_instance = TrainingOrchestrator()
