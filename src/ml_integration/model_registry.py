"""
Model Registry module for the Agent Reliable Memory System.

Stage 402: Model Registry

Design Principles:
1. First Principles: deterministic rules, no model dependencies
2. Thread-safe using threading.RLock
3. Global singleton via get_model_registry() with double-checked locking
4. Use Python dataclasses for data structures, Enum for types
5. Minimal dependencies, no circular dependencies
"""

from __future__ import annotations

import hashlib
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ModelStatus(Enum):
    """Lifecycle status of a registered model."""
    REGISTERED = "registered"
    TRAINING = "training"
    TRAINED = "trained"
    VALIDATED = "validated"
    DEPLOYED = "deployed"
    ARCHIVED = "archived"


class ModelType(Enum):
    """Supported model types."""
    CLASSIFIER = "classifier"
    REGRESSOR = "regressor"
    CLUSTERER = "clusterer"
    EMBEDDING = "embedding"
    ENSEMBLE = "ensemble"


@dataclass
class ModelArtifact:
    """Represents a serialized model artifact."""
    artifact_id: str
    model_id: str
    version: int
    format: str
    data: bytes
    checksum: str
    created_at: float = field(default_factory=time.time)


@dataclass
class ModelMetadata:
    """Metadata for a registered model."""
    model_id: str
    name: str
    model_type: ModelType
    version: int
    status: ModelStatus = ModelStatus.REGISTERED
    metrics: Dict[str, Any] = field(default_factory=dict)
    params: Dict[str, Any] = field(default_factory=dict)
    tags: set = field(default_factory=set)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class ModelRegistry:
    """
    Thread-safe model registry for managing ML model metadata and artifacts.

    All mutating operations are protected by an RLock to allow safe concurrent
    access from multiple threads.
    """

    def __init__(self) -> None:
        self._models: Dict[str, ModelMetadata] = {}
        self._artifacts: Dict[str, List[ModelArtifact]] = {}
        self._lock: threading.RLock = threading.RLock()

    # ------------------------------------------------------------------ #
    # Core model lifecycle
    # ------------------------------------------------------------------ #

    def register_model(
        self,
        name: str,
        model_type: ModelType,
        params: Dict[str, Any],
        tags: Optional[List[str]] = None,
    ) -> str:
        """
        Register a new model and return its unique model_id.

        Version starts at 1 and is auto-incremented when new artifacts are stored.
        """
        model_id = str(uuid.uuid4())
        tag_set: set = set(tags) if tags else set()

        metadata = ModelMetadata(
            model_id=model_id,
            name=name,
            model_type=model_type,
            version=1,
            params=dict(params),
            tags=tag_set,
        )

        with self._lock:
            self._models[model_id] = metadata
            self._artifacts[model_id] = []

        return model_id

    def unregister_model(self, model_id: str) -> bool:
        """Remove a model and all its artifacts from the registry."""
        with self._lock:
            if model_id not in self._models:
                return False
            del self._models[model_id]
            del self._artifacts[model_id]
            return True

    def update_status(self, model_id: str, status: ModelStatus) -> bool:
        """Update the lifecycle status of a model."""
        with self._lock:
            metadata = self._models.get(model_id)
            if metadata is None:
                return False
            metadata.status = status
            metadata.updated_at = time.time()
            return True

    def update_metrics(self, model_id: str, metrics: Dict[str, Any]) -> bool:
        """Merge new metrics into the model's existing metrics."""
        with self._lock:
            metadata = self._models.get(model_id)
            if metadata is None:
                return False
            metadata.metrics.update(metrics)
            metadata.updated_at = time.time()
            return True

    # ------------------------------------------------------------------ #
    # Artifact management
    # ------------------------------------------------------------------ #

    def store_artifact(
        self,
        model_id: str,
        version: int,
        format: str,
        data: bytes,
    ) -> str:
        """
        Store a model artifact and return its artifact_id.

        The version supplied here is recorded in the artifact; the model's
        latest version is updated if this version is greater.
        """
        artifact_id = str(uuid.uuid4())
        checksum = hashlib.md5(data).hexdigest()

        artifact = ModelArtifact(
            artifact_id=artifact_id,
            model_id=model_id,
            version=version,
            format=format,
            data=data,
            checksum=checksum,
        )

        with self._lock:
            if model_id not in self._models:
                raise ValueError(f"Model '{model_id}' is not registered.")

            self._artifacts[model_id].append(artifact)

            # Auto-increment model version if the stored artifact is newer
            if version > self._models[model_id].version:
                self._models[model_id].version = version
                self._models[model_id].updated_at = time.time()

        return artifact_id

    def get_artifact(self, artifact_id: str) -> Optional[ModelArtifact]:
        """Retrieve an artifact by its unique artifact_id."""
        with self._lock:
            for artifact_list in self._artifacts.values():
                for artifact in artifact_list:
                    if artifact.artifact_id == artifact_id:
                        return artifact
            return None

    # ------------------------------------------------------------------ #
    # Querying
    # ------------------------------------------------------------------ #

    def get_model(self, model_id: str) -> Optional[ModelMetadata]:
        """Retrieve metadata for a single model."""
        with self._lock:
            return self._models.get(model_id)

    def get_models(
        self,
        status: Optional[ModelStatus] = None,
        model_type: Optional[ModelType] = None,
    ) -> List[ModelMetadata]:
        """List models, optionally filtered by status and/or type."""
        with self._lock:
            results = []
            for metadata in self._models.values():
                if status is not None and metadata.status != status:
                    continue
                if model_type is not None and metadata.model_type != model_type:
                    continue
                results.append(metadata)
            return results

    def get_latest_version(self, model_id: str) -> int:
        """Return the latest version number for a model."""
        with self._lock:
            metadata = self._models.get(model_id)
            if metadata is None:
                raise ValueError(f"Model '{model_id}' is not registered.")
            return metadata.version

    # ------------------------------------------------------------------ #
    # Tag management
    # ------------------------------------------------------------------ #

    def add_tag(self, model_id: str, tag: str) -> bool:
        """Add a tag to a model."""
        with self._lock:
            metadata = self._models.get(model_id)
            if metadata is None:
                return False
            metadata.tags.add(tag)
            metadata.updated_at = time.time()
            return True

    def remove_tag(self, model_id: str, tag: str) -> bool:
        """Remove a tag from a model."""
        with self._lock:
            metadata = self._models.get(model_id)
            if metadata is None:
                return False
            if tag not in metadata.tags:
                return False
            metadata.tags.discard(tag)
            metadata.updated_at = time.time()
            return True

    def search_by_tag(self, tag: str) -> List[ModelMetadata]:
        """Return all models that contain the given tag."""
        with self._lock:
            return [m for m in self._models.values() if tag in m.tags]

    # ------------------------------------------------------------------ #
    # Comparison & statistics
    # ------------------------------------------------------------------ #

    def compare_models(self, model_a: str, model_b: str) -> Dict[str, Any]:
        """
        Compare two models and return a structured diff.

        Returns a dict with keys: model_a, model_b, common_metrics,
        metric_diffs, type_diff, version_diff.
        """
        with self._lock:
            meta_a = self._models.get(model_a)
            meta_b = self._models.get(model_b)

        if meta_a is None or meta_b is None:
            raise ValueError("One or both model IDs are not registered.")

        common_metrics = set(meta_a.metrics.keys()) & set(meta_b.metrics.keys())
        metric_diffs: Dict[str, Any] = {}
        for metric in common_metrics:
            val_a = meta_a.metrics[metric]
            val_b = meta_b.metrics[metric]
            try:
                diff = float(val_a) - float(val_b)
            except (TypeError, ValueError):
                diff = None
            metric_diffs[metric] = {
                "model_a": val_a,
                "model_b": val_b,
                "diff": diff,
            }

        return {
            "model_a": {
                "model_id": meta_a.model_id,
                "name": meta_a.name,
                "version": meta_a.version,
                "status": meta_a.status.value,
                "type": meta_a.model_type.value,
                "metrics": dict(meta_a.metrics),
            },
            "model_b": {
                "model_id": meta_b.model_id,
                "name": meta_b.name,
                "version": meta_b.version,
                "status": meta_b.status.value,
                "type": meta_b.model_type.value,
                "metrics": dict(meta_b.metrics),
            },
            "common_metrics": sorted(common_metrics),
            "metric_diffs": metric_diffs,
            "type_diff": meta_a.model_type != meta_b.model_type,
            "version_diff": meta_a.version - meta_b.version,
        }

    def get_statistics(self) -> Dict[str, Any]:
        """Return aggregate statistics about the registry contents."""
        with self._lock:
            total_models = len(self._models)
            status_counts: Dict[str, int] = {s.value: 0 for s in ModelStatus}
            type_counts: Dict[str, int] = {t.value: 0 for t in ModelType}
            total_artifacts = 0

            for metadata in self._models.values():
                status_counts[metadata.status.value] += 1
                type_counts[metadata.model_type.value] += 1

            for artifact_list in self._artifacts.values():
                total_artifacts += len(artifact_list)

            return {
                "total_models": total_models,
                "total_artifacts": total_artifacts,
                "status_distribution": status_counts,
                "type_distribution": type_counts,
            }

    # ------------------------------------------------------------------ #
    # Checksum validation
    # ------------------------------------------------------------------ #

    @staticmethod
    def compute_checksum(data: bytes) -> str:
        """Compute MD5 checksum for arbitrary bytes."""
        return hashlib.md5(data).hexdigest()

    def validate_artifact(self, artifact_id: str) -> bool:
        """Validate that an artifact's data matches its stored checksum."""
        artifact = self.get_artifact(artifact_id)
        if artifact is None:
            return False
        return artifact.checksum == self.compute_checksum(artifact.data)


# ---------------------------------------------------------------------- #
# Singleton management with double-checked locking
# ---------------------------------------------------------------------- #

_model_registry_instance: Optional[ModelRegistry] = None
_model_registry_lock: threading.Lock = threading.Lock()


def get_model_registry() -> ModelRegistry:
    """
    Return the global ModelRegistry singleton.

    Uses double-checked locking for thread-safe lazy initialization.
    """
    global _model_registry_instance
    if _model_registry_instance is None:
        with _model_registry_lock:
            if _model_registry_instance is None:
                _model_registry_instance = ModelRegistry()
    return _model_registry_instance


def reset_model_registry() -> None:
    """Reset the global singleton instance. Intended for testing only."""
    global _model_registry_instance
    with _model_registry_lock:
        _model_registry_instance = None
