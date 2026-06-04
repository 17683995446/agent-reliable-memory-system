"""
Pattern Recognizer module for the Agent Reliable Memory System.

Stage 391 - Intelligence Layer

Design Principles:
1. First Principles: deterministic rules, no model dependencies
2. Thread-safe using threading.RLock
3. Global singleton via get_pattern_recognizer() with double-checked locking
4. Use Python dataclasses for data structures, Enum for types
5. Minimal dependencies, no circular dependencies

Pure Python implementation using only math and statistics modules.
No ML models or external libraries.
"""

from __future__ import annotations

import math
import statistics
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, List, Optional


class PatternType(Enum):
    """Enumeration of supported pattern types."""

    SEQUENCE = auto()
    TREND = auto()
    ANOMALY = auto()
    CORRELATION = auto()
    CYCLE = auto()
    CLUSTER = auto()


class PatternConfidence(Enum):
    """Enumeration of confidence levels for detected patterns."""

    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()
    CERTAIN = auto()


@dataclass
class DetectedPattern:
    """Represents a detected pattern in data."""

    pattern_id: str
    pattern_type: PatternType
    data_points: List[float]
    confidence: PatternConfidence
    description: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    detected_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class PatternRule:
    """Represents a configurable rule for pattern detection."""

    rule_id: str
    pattern_type: PatternType
    condition: str
    threshold: float
    enabled: bool = True


class PatternRecognizer:
    """
    Thread-safe pattern recognizer using deterministic rules.

    Supports detection of sequences, trends, anomalies, correlations,
    cycles, and clusters using pure Python math/statistics.
    """

    def __init__(self) -> None:
        self._patterns: Dict[str, DetectedPattern] = {}
        self._rules: Dict[str, PatternRule] = {}
        self._lock: threading.RLock = threading.RLock()

    # ------------------------------------------------------------------
    # Rule management
    # ------------------------------------------------------------------

    def add_rule(self, rule: PatternRule) -> bool:
        """Add a detection rule. Returns True if newly added."""
        with self._lock:
            if rule.rule_id in self._rules:
                return False
            self._rules[rule.rule_id] = rule
            return True

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a detection rule by ID. Returns True if removed."""
        with self._lock:
            return self._rules.pop(rule_id, None) is not None

    # ------------------------------------------------------------------
    # Generic detection dispatcher
    # ------------------------------------------------------------------

    def detect_patterns(
        self, data: List[float], pattern_type: Optional[PatternType] = None
    ) -> List[DetectedPattern]:
        """
        Detect patterns in the provided data.

        If pattern_type is specified, only that type is attempted.
        Otherwise all supported types are evaluated.
        """
        if not data:
            return []

        results: List[DetectedPattern] = []

        dispatch = {
            PatternType.SEQUENCE: self.detect_sequence,
            PatternType.TREND: self.detect_trend,
            PatternType.ANOMALY: self.detect_anomaly,
            PatternType.CORRELATION: lambda d: [],  # requires two series
            PatternType.CYCLE: self.detect_cycle,
            PatternType.CLUSTER: self.detect_cluster,
        }

        if pattern_type is not None:
            targets = [pattern_type]
        else:
            targets = list(PatternType)

        for pt in targets:
            if pt == PatternType.CORRELATION:
                continue
            detector = dispatch.get(pt)
            if detector is None:
                continue
            found = detector(data)
            results.extend(found)

        with self._lock:
            for pat in results:
                self._patterns[pat.pattern_id] = pat

        return results

    # ------------------------------------------------------------------
    # SEQUENCE detection
    # ------------------------------------------------------------------

    def detect_sequence(self, data: List[float]) -> List[DetectedPattern]:
        """Detect monotonically increasing or decreasing sequences."""
        if len(data) < 2:
            return []

        increasing = all(data[i] <= data[i + 1] for i in range(len(data) - 1))
        decreasing = all(data[i] >= data[i + 1] for i in range(len(data) - 1))

        results: List[DetectedPattern] = []

        if increasing:
            results.append(
                DetectedPattern(
                    pattern_id=str(uuid.uuid4()),
                    pattern_type=PatternType.SEQUENCE,
                    data_points=list(data),
                    confidence=PatternConfidence.CERTAIN,
                    description="Monotonically increasing sequence detected.",
                    metadata={"direction": "increasing", "length": len(data)},
                )
            )

        if decreasing:
            results.append(
                DetectedPattern(
                    pattern_id=str(uuid.uuid4()),
                    pattern_type=PatternType.SEQUENCE,
                    data_points=list(data),
                    confidence=PatternConfidence.CERTAIN,
                    description="Monotonically decreasing sequence detected.",
                    metadata={"direction": "decreasing", "length": len(data)},
                )
            )

        with self._lock:
            for pat in results:
                self._patterns[pat.pattern_id] = pat

        return results

    # ------------------------------------------------------------------
    # TREND detection
    # ------------------------------------------------------------------

    def detect_trend(self, data: List[float]) -> List[DetectedPattern]:
        """Detect linear trend using simple least-squares regression."""
        n = len(data)
        if n < 2:
            return []

        x = list(range(n))
        mean_x = statistics.mean(x)
        mean_y = statistics.mean(data)

        numerator = sum((x[i] - mean_x) * (data[i] - mean_y) for i in range(n))
        denominator = sum((x[i] - mean_x) ** 2 for i in range(n))

        if denominator == 0:
            return []

        slope = numerator / denominator
        intercept = mean_y - slope * mean_x

        ss_res = sum(
            (data[i] - (intercept + slope * x[i])) ** 2 for i in range(n)
        )
        ss_tot = sum((data[i] - mean_y) ** 2 for i in range(n))
        r_squared = 1.0 - (ss_res / ss_tot) if ss_tot != 0 else 1.0

        if slope > 0:
            direction = "upward"
        elif slope < 0:
            direction = "downward"
        else:
            direction = "flat"

        confidence = self._r_squared_to_confidence(r_squared)

        return [
            DetectedPattern(
                pattern_id=str(uuid.uuid4()),
                pattern_type=PatternType.TREND,
                data_points=list(data),
                confidence=confidence,
                description=f"Linear {direction} trend detected (slope={slope:.4f}).",
                metadata={
                    "slope": slope,
                    "intercept": intercept,
                    "r_squared": r_squared,
                    "direction": direction,
                },
            )
        ]

    # ------------------------------------------------------------------
    # ANOMALY detection
    # ------------------------------------------------------------------

    def detect_anomaly(
        self, data: List[float], threshold: float = 2.0
    ) -> List[DetectedPattern]:
        """Detect anomalies using z-score method."""
        n = len(data)
        if n < 2:
            return []

        mean = statistics.mean(data)
        stdev = statistics.stdev(data) if n > 1 else 0.0

        if stdev == 0:
            return []

        anomalies: List[float] = []
        anomaly_indices: List[int] = []
        for i, value in enumerate(data):
            z_score = (value - mean) / stdev
            if abs(z_score) > threshold:
                anomalies.append(value)
                anomaly_indices.append(i)

        if not anomalies:
            return []

        return [
            DetectedPattern(
                pattern_id=str(uuid.uuid4()),
                pattern_type=PatternType.ANOMALY,
                data_points=anomalies,
                confidence=PatternConfidence.HIGH,
                description=f"Detected {len(anomalies)} anomaly(s) using z-score (threshold={threshold}).",
                metadata={
                    "threshold": threshold,
                    "mean": mean,
                    "stdev": stdev,
                    "indices": anomaly_indices,
                },
            )
        ]

    # ------------------------------------------------------------------
    # CORRELATION detection
    # ------------------------------------------------------------------

    def detect_correlation(
        self, data_x: List[float], data_y: List[float]
    ) -> Optional[DetectedPattern]:
        """Detect Pearson correlation between two data series."""
        n = len(data_x)
        if n != len(data_y) or n < 2:
            return None

        mean_x = statistics.mean(data_x)
        mean_y = statistics.mean(data_y)

        numerator = sum(
            (data_x[i] - mean_x) * (data_y[i] - mean_y) for i in range(n)
        )
        denom_x = sum((data_x[i] - mean_x) ** 2 for i in range(n))
        denom_y = sum((data_y[i] - mean_y) ** 2 for i in range(n))

        denominator = math.sqrt(denom_x * denom_y)
        if denominator == 0:
            return None

        pearson = numerator / denominator
        r_squared = pearson ** 2

        if abs(pearson) > 0.9:
            confidence = PatternConfidence.CERTAIN
        elif abs(pearson) > 0.7:
            confidence = PatternConfidence.HIGH
        elif abs(pearson) > 0.4:
            confidence = PatternConfidence.MEDIUM
        else:
            confidence = PatternConfidence.LOW

        direction = "positive" if pearson > 0 else "negative"

        return DetectedPattern(
            pattern_id=str(uuid.uuid4()),
            pattern_type=PatternType.CORRELATION,
            data_points=list(data_x),
            confidence=confidence,
            description=f"Pearson correlation: {pearson:.4f} ({direction}).",
            metadata={
                "pearson": pearson,
                "r_squared": r_squared,
                "direction": direction,
                "series_length": n,
            },
        )

    # ------------------------------------------------------------------
    # CYCLE detection
    # ------------------------------------------------------------------

    def detect_cycle(self, data: List[float]) -> List[DetectedPattern]:
        """Detect periodicity using autocorrelation."""
        n = len(data)
        if n < 4:
            return []

        mean = statistics.mean(data)
        c0 = sum((data[i] - mean) ** 2 for i in range(n))

        if c0 == 0:
            return []

        best_lag = 0
        best_corr = -1.0
        max_lag = n // 2

        for lag in range(1, max_lag + 1):
            c_lag = sum(
                (data[i] - mean) * (data[i + lag] - mean)
                for i in range(n - lag)
            )
            corr = c_lag / c0
            if corr > best_corr:
                best_corr = corr
                best_lag = lag

        if best_lag == 0 or best_corr < 0.3:
            return []

        confidence = (
            PatternConfidence.CERTAIN
            if best_corr > 0.9
            else PatternConfidence.HIGH
            if best_corr > 0.7
            else PatternConfidence.MEDIUM
            if best_corr > 0.5
            else PatternConfidence.LOW
        )

        return [
            DetectedPattern(
                pattern_id=str(uuid.uuid4()),
                pattern_type=PatternType.CYCLE,
                data_points=list(data),
                confidence=confidence,
                description=f"Periodic cycle detected with lag={best_lag} (autocorr={best_corr:.4f}).",
                metadata={
                    "lag": best_lag,
                    "autocorrelation": best_corr,
                    "series_length": n,
                },
            )
        ]

    # ------------------------------------------------------------------
    # CLUSTER detection
    # ------------------------------------------------------------------

    def detect_cluster(self, data: List[float]) -> List[DetectedPattern]:
        """Detect clusters using simple distance-based thresholding."""
        n = len(data)
        if n < 2:
            return []

        sorted_data = sorted(data)
        gaps: List[tuple] = []
        for i in range(n - 1):
            gap = sorted_data[i + 1] - sorted_data[i]
            gaps.append((gap, i))

        if not gaps:
            return []

        mean_gap = statistics.mean(g[0] for g in gaps)
        threshold = mean_gap * 2.0

        clusters: List[List[float]] = []
        current: List[float] = [sorted_data[0]]

        for i in range(n - 1):
            if gaps[i][0] <= threshold:
                current.append(sorted_data[i + 1])
            else:
                clusters.append(current)
                current = [sorted_data[i + 1]]
        clusters.append(current)

        if len(clusters) == 1:
            return []

        results: List[DetectedPattern] = []
        for idx, cluster in enumerate(clusters):
            if len(cluster) < 1:
                continue
            results.append(
                DetectedPattern(
                    pattern_id=str(uuid.uuid4()),
                    pattern_type=PatternType.CLUSTER,
                    data_points=cluster,
                    confidence=PatternConfidence.MEDIUM,
                    description=f"Cluster {idx + 1} with {len(cluster)} point(s).",
                    metadata={
                        "cluster_index": idx + 1,
                        "cluster_size": len(cluster),
                        "cluster_mean": statistics.mean(cluster),
                        "cluster_min": min(cluster),
                        "cluster_max": max(cluster),
                    },
                )
            )

        return results

    # ------------------------------------------------------------------
    # Pattern storage queries
    # ------------------------------------------------------------------

    def get_pattern(self, pattern_id: str) -> Optional[DetectedPattern]:
        """Retrieve a single detected pattern by ID."""
        with self._lock:
            return self._patterns.get(pattern_id)

    def get_all_patterns(self) -> List[DetectedPattern]:
        """Retrieve all stored detected patterns."""
        with self._lock:
            return list(self._patterns.values())

    def get_patterns_by_type(self, pattern_type: PatternType) -> List[DetectedPattern]:
        """Retrieve patterns filtered by type."""
        with self._lock:
            return [
                p for p in self._patterns.values() if p.pattern_type == pattern_type
            ]

    def clear_patterns(self) -> int:
        """Clear all stored patterns. Returns number removed."""
        with self._lock:
            count = len(self._patterns)
            self._patterns.clear()
            return count

    def get_statistics(self) -> Dict[str, Any]:
        """Return summary statistics of stored patterns."""
        with self._lock:
            total = len(self._patterns)
            by_type: Dict[str, int] = {}
            by_confidence: Dict[str, int] = {}
            for p in self._patterns.values():
                by_type[p.pattern_type.name] = by_type.get(p.pattern_type.name, 0) + 1
                by_confidence[p.confidence.name] = (
                    by_confidence.get(p.confidence.name, 0) + 1
                )
            return {
                "total_patterns": total,
                "by_type": by_type,
                "by_confidence": by_confidence,
                "rule_count": len(self._rules),
            }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _r_squared_to_confidence(r_squared: float) -> PatternConfidence:
        if r_squared > 0.95:
            return PatternConfidence.CERTAIN
        if r_squared > 0.80:
            return PatternConfidence.HIGH
        if r_squared > 0.50:
            return PatternConfidence.MEDIUM
        return PatternConfidence.LOW


# ----------------------------------------------------------------------
# Singleton management with double-checked locking
# ----------------------------------------------------------------------

_pattern_recognizer_instance: Optional[PatternRecognizer] = None
_pattern_recognizer_lock: threading.Lock = threading.Lock()


def get_pattern_recognizer() -> PatternRecognizer:
    """
    Return the global PatternRecognizer singleton.

    Uses double-checked locking for thread-safe lazy initialization.
    """
    global _pattern_recognizer_instance
    if _pattern_recognizer_instance is None:
        with _pattern_recognizer_lock:
            if _pattern_recognizer_instance is None:
                _pattern_recognizer_instance = PatternRecognizer()
    return _pattern_recognizer_instance


def reset_pattern_recognizer() -> None:
    """Reset the global singleton instance (intended for testing)."""
    global _pattern_recognizer_instance
    with _pattern_recognizer_lock:
        _pattern_recognizer_instance = None
