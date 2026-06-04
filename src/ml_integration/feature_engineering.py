"""
Feature Engineering module for the Agent Reliable Memory System.

Stage 401 - ML Integration

Design Principles:
1. First Principles: deterministic rules, no model dependencies
2. Thread-safe using threading.RLock
3. Global singleton via get_feature_engineer() with double-checked locking
4. Use Python dataclasses for data structures, Enum for types
5. Minimal dependencies, no circular dependencies

Pure Python implementation. No sklearn or external ML libraries.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


class TransformType(Enum):
    """Enumeration of supported transformation types."""
    SCALING = "scaling"
    NORMALIZATION = "normalization"
    ENCODING = "encoding"
    BINNING = "binning"
    POLYNOMIAL = "polynomial"
    INTERACTION = "interaction"
    SELECTION = "selection"


class FeatureType(Enum):
    """Enumeration of supported feature types."""
    NUMERIC = "numeric"
    CATEGORICAL = "categorical"
    BINARY = "binary"
    TEXT = "text"
    DATETIME = "datetime"


@dataclass
class FeatureSpec:
    """Specification for a registered feature."""
    name: str
    feature_type: FeatureType
    params: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TransformedFeature:
    """Represents a feature after transformation."""
    name: str
    original_name: str
    transform_type: TransformType
    values: Any
    metadata: Dict[str, Any] = field(default_factory=dict)


class FeatureEngineer:
    """
    Thread-safe feature engineering engine.

    Provides deterministic, pure-Python transformations for
    numeric, categorical, binary, text, and datetime features.
    """

    def __init__(self) -> None:
        self._features: Dict[str, FeatureSpec] = {}
        self._transformers: Dict[TransformType, Callable] = {
            TransformType.SCALING: self.scale,
            TransformType.NORMALIZATION: self.normalize,
            TransformType.ENCODING: self.encode_categorical,
            TransformType.BINNING: self.bin_numeric,
            TransformType.POLYNOMIAL: self.polynomial_features,
            TransformType.INTERACTION: self.interaction_features,
            TransformType.SELECTION: self.select_features,
        }
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    # Feature registry
    # ------------------------------------------------------------------ #

    def register_feature(
        self,
        name: str,
        feature_type: FeatureType,
        params: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Register a feature specification.

        Args:
            name: Unique feature name.
            feature_type: Type of the feature.
            params: Optional parameters for the feature.

        Returns:
            True if registered successfully, False if already exists.
        """
        with self._lock:
            if name in self._features:
                return False
            self._features[name] = FeatureSpec(
                name=name,
                feature_type=feature_type,
                params=params or {},
            )
            return True

    def unregister_feature(self, name: str) -> bool:
        """
        Unregister a feature specification.

        Args:
            name: Feature name to remove.

        Returns:
            True if removed, False if not found.
        """
        with self._lock:
            if name not in self._features:
                return False
            del self._features[name]
            return True

    def get_feature(self, name: str) -> Optional[FeatureSpec]:
        """Retrieve a registered feature spec by name."""
        with self._lock:
            return self._features.get(name)

    def get_all_features(self) -> List[FeatureSpec]:
        """Return a list of all registered feature specs."""
        with self._lock:
            return list(self._features.values())

    # ------------------------------------------------------------------ #
    # Transformations
    # ------------------------------------------------------------------ #

    @staticmethod
    def scale(data: List[float], method: str = "minmax") -> List[float]:
        """
        Scale numeric data.

        Supports:
            - "minmax": min-max scaling to [0, 1]
            - "zscore": zero-mean, unit-variance scaling

        Args:
            data: List of numeric values.
            method: Scaling method.

        Returns:
            Scaled values.
        """
        if not data:
            return []

        n = len(data)
        if n == 1:
            return [0.0] if method == "zscore" else [0.5]

        min_val = min(data)
        max_val = max(data)
        mean_val = sum(data) / n

        if method == "minmax":
            range_val = max_val - min_val
            if range_val == 0:
                return [0.5] * n
            return [(x - min_val) / range_val for x in data]

        if method == "zscore":
            variance = sum((x - mean_val) ** 2 for x in data) / n
            std_dev = math.sqrt(variance) if variance > 0 else 0.0
            if std_dev == 0:
                return [0.0] * n
            return [(x - mean_val) / std_dev for x in data]

        raise ValueError(f"Unsupported scaling method: {method}")

    @staticmethod
    def normalize(data: List[float]) -> List[float]:
        """
        L2-normalize a vector.

        Args:
            data: List of numeric values.

        Returns:
            L2-normalized values.
        """
        if not data:
            return []

        norm = math.sqrt(sum(x * x for x in data))
        if norm == 0:
            return [0.0] * len(data)
        return [x / norm for x in data]

    @staticmethod
    def encode_categorical(
        data: List[str], method: str = "onehot"
    ) -> Dict[str, Any]:
        """
        Encode categorical data.

        Supports:
            - "onehot": one-hot encoding returning a dict of category -> list

        Args:
            data: List of categorical values.
            method: Encoding method.

        Returns:
            Dictionary mapping categories to binary vectors.
        """
        if not data:
            return {}

        if method != "onehot":
            raise ValueError(f"Unsupported encoding method: {method}")

        categories = sorted(set(data))
        n = len(data)
        result: Dict[str, Any] = {}

        for cat in categories:
            result[cat] = [1.0 if x == cat else 0.0 for x in data]

        result["_categories"] = categories
        result["_length"] = n
        return result

    @staticmethod
    def bin_numeric(data: List[float], bins: int = 5) -> List[int]:
        """
        Equal-width binning for numeric data.

        Args:
            data: List of numeric values.
            bins: Number of bins.

        Returns:
            List of bin indices (0-based).
        """
        if not data or bins <= 0:
            return []

        min_val = min(data)
        max_val = max(data)
        range_val = max_val - min_val

        if range_val == 0:
            return [0] * len(data)

        bin_width = range_val / bins
        result: List[int] = []

        for x in data:
            idx = int((x - min_val) / bin_width)
            # Clamp to last bin for the maximum value
            if idx >= bins:
                idx = bins - 1
            result.append(idx)

        return result

    @staticmethod
    def polynomial_features(data: List[float], degree: int = 2) -> List[List[float]]:
        """
        Generate polynomial features.

        Args:
            data: List of numeric values.
            degree: Maximum polynomial degree.

        Returns:
            List of feature vectors, one per input element.
        """
        if not data or degree < 1:
            return []

        result: List[List[float]] = []
        for x in data:
            row = [x**d for d in range(1, degree + 1)]
            result.append(row)
        return result

    @staticmethod
    def interaction_features(data_a: List[float], data_b: List[float]) -> List[float]:
        """
        Compute element-wise interaction features (product).

        Args:
            data_a: First feature vector.
            data_b: Second feature vector.

        Returns:
            Element-wise product.
        """
        if len(data_a) != len(data_b):
            raise ValueError(
                f"Input lengths must match: {len(data_a)} vs {len(data_b)}"
            )
        return [a * b for a, b in zip(data_a, data_b)]

    @staticmethod
    def select_features(
        data: Dict[str, List[float]], labels: List[float], k: int = 5
    ) -> List[str]:
        """
        Variance-based feature selection.

        Selects the top-k features with highest variance.

        Args:
            data: Dictionary mapping feature names to value lists.
            labels: Target labels (reserved for future use).
            k: Number of features to select.

        Returns:
            List of selected feature names.
        """
        if not data:
            return []

        variances: List[Tuple[str, float]] = []
        for name, values in data.items():
            if not values:
                variances.append((name, 0.0))
                continue
            n = len(values)
            mean_val = sum(values) / n
            variance = sum((x - mean_val) ** 2 for x in values) / n
            variances.append((name, variance))

        # Sort by variance descending
        variances.sort(key=lambda x: x[1], reverse=True)
        k = min(k, len(variances))
        return [name for name, _ in variances[:k]]

    # ------------------------------------------------------------------ #
    # Batch transform
    # ------------------------------------------------------------------ #

    def transform(
        self, data: Dict[str, List[Any]], feature_specs: List[FeatureSpec]
    ) -> Dict[str, Any]:
        """
        Apply transformations to a batch of features.

        Args:
            data: Dictionary mapping feature names to raw value lists.
            feature_specs: List of FeatureSpec defining transformations.

        Returns:
            Dictionary mapping output feature names to transformed values.
        """
        result: Dict[str, Any] = {}

        for spec in feature_specs:
            name = spec.name
            raw = data.get(name, [])

            if spec.feature_type == FeatureType.NUMERIC:
                method = spec.params.get("scale_method", "minmax")
                result[name] = self.scale(raw, method=method)

            elif spec.feature_type == FeatureType.CATEGORICAL:
                method = spec.params.get("encode_method", "onehot")
                result[name] = self.encode_categorical(raw, method=method)

            elif spec.feature_type == FeatureType.BINARY:
                # Binary features are passed through as floats
                result[name] = [float(x) for x in raw]

            elif spec.feature_type == FeatureType.TEXT:
                # Text features: simple length-based numeric encoding
                result[name] = [float(len(str(x))) for x in raw]

            elif spec.feature_type == FeatureType.DATETIME:
                # Datetime features: convert to timestamp (float)
                result[name] = [
                    float(x.timestamp()) if hasattr(x, "timestamp") else float(x)
                    for x in raw
                ]

            else:
                result[name] = raw

        return result

    # ------------------------------------------------------------------ #
    # Statistics
    # ------------------------------------------------------------------ #

    def get_statistics(self) -> Dict[str, Any]:
        """
        Return current engine statistics.

        Returns:
            Dictionary with feature counts and transformer info.
        """
        with self._lock:
            type_counts: Dict[str, int] = {}
            for spec in self._features.values():
                ft = spec.feature_type.value
                type_counts[ft] = type_counts.get(ft, 0) + 1

            return {
                "total_features": len(self._features),
                "feature_type_counts": type_counts,
                "registered_transformers": [
                    t.value for t in self._transformers.keys()
                ],
            }


# ---------------------------------------------------------------------- #
# Singleton management
# ---------------------------------------------------------------------- #

_feature_engineer_instance: Optional[FeatureEngineer] = None
_instance_lock = threading.Lock()


def get_feature_engineer() -> FeatureEngineer:
    """
    Return the global FeatureEngineer singleton.

    Uses double-checked locking for thread-safe lazy initialization.
    """
    global _feature_engineer_instance
    if _feature_engineer_instance is None:
        with _instance_lock:
            if _feature_engineer_instance is None:
                _feature_engineer_instance = FeatureEngineer()
    return _feature_engineer_instance


def reset_feature_engineer() -> None:
    """
    Reset the global singleton instance.

    Intended for testing purposes only.
    """
    global _feature_engineer_instance
    with _instance_lock:
        _feature_engineer_instance = None
