"""
Model Monitor module for the Agent Reliable Memory System.

Stage 405: Model Monitor

Design Principles:
1. First Principles: deterministic rules, no model dependencies
2. Thread-safe using threading.RLock
3. Global singleton via get_model_monitor() with double-checked locking
4. Use Python dataclasses for data structures, Enum for types
5. Minimal dependencies, no circular dependencies
"""

from __future__ import annotations

import statistics
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class MonitorMetric(Enum):
    """Supported metric types for model monitoring."""
    ACCURACY = "accuracy"
    PRECISION = "precision"
    RECALL = "recall"
    F1 = "f1"
    LATENCY = "latency"
    THROUGHPUT = "throughput"
    DRIFT = "drift"


class AlertSeverity(Enum):
    """Severity levels for generated alerts."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class ModelMetric:
    """A single recorded metric value for a model."""
    metric_id: str
    model_id: str
    metric_type: MonitorMetric
    value: float
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelAlert:
    """An alert generated when a metric breaches its threshold or drift is detected."""
    alert_id: str
    model_id: str
    metric_type: MonitorMetric
    severity: AlertSeverity
    message: str
    threshold: float
    timestamp: float = field(default_factory=time.time)
    acknowledged: bool = False


class ModelMonitor:
    """
    Thread-safe model monitor for tracking metrics, thresholds, alerts, and drift.

    All mutating operations are protected by an RLock to allow safe concurrent
    access from multiple threads.  Metric retention is capped at 10,000 entries
    per model to prevent unbounded memory growth.
    """

    _MAX_METRICS_PER_MODEL: int = 10000

    def __init__(self) -> None:
        self._metrics: Dict[str, List[ModelMetric]] = {}
        self._alerts: List[ModelAlert] = []
        self._thresholds: Dict[str, Dict[str, float]] = {}
        self._lock: threading.RLock = threading.RLock()

    # ------------------------------------------------------------------ #
    # Metric recording
    # ------------------------------------------------------------------ #

    def record_metric(
        self,
        model_id: str,
        metric_type: MonitorMetric,
        value: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Record a metric value for a model.

        Automatically checks thresholds and generates alerts if the value
        breaches the configured threshold for the metric.

        Returns the generated metric_id.
        """
        metric_id = str(uuid.uuid4())
        metric = ModelMetric(
            metric_id=metric_id,
            model_id=model_id,
            metric_type=metric_type,
            value=float(value),
            timestamp=time.time(),
            metadata=dict(metadata) if metadata else {},
        )

        with self._lock:
            if model_id not in self._metrics:
                self._metrics[model_id] = []
            self._metrics[model_id].append(metric)

            # Enforce retention limit
            if len(self._metrics[model_id]) > self._MAX_METRICS_PER_MODEL:
                self._metrics[model_id] = self._metrics[model_id][-self._MAX_METRICS_PER_MODEL:]

            # Automatic alert generation on threshold breach
            self._maybe_generate_alert(model_id, metric_type, metric.value)

        return metric_id

    def _maybe_generate_alert(
        self,
        model_id: str,
        metric_type: MonitorMetric,
        value: float,
    ) -> None:
        """
        Internal helper to generate an alert if *value* breaches the threshold.

        Must be called while holding ``self._lock``.
        """
        thresholds = self._thresholds.get(model_id, {})
        threshold = thresholds.get(metric_type.value)
        if threshold is None:
            return

        # For accuracy-like metrics, lower is worse when below threshold.
        # For latency/drift, higher is worse when above threshold.
        if metric_type in (MonitorMetric.ACCURACY, MonitorMetric.PRECISION,
                           MonitorMetric.RECALL, MonitorMetric.F1,
                           MonitorMetric.THROUGHPUT):
            breached = value < threshold
        else:
            breached = value > threshold

        if not breached:
            return

        # Determine severity based on magnitude of breach
        if metric_type in (MonitorMetric.ACCURACY, MonitorMetric.PRECISION,
                           MonitorMetric.RECALL, MonitorMetric.F1):
            ratio = threshold / max(value, 1e-9)
        else:
            ratio = value / max(threshold, 1e-9)

        if ratio >= 2.0:
            severity = AlertSeverity.CRITICAL
        elif ratio >= 1.5:
            severity = AlertSeverity.WARNING
        else:
            severity = AlertSeverity.INFO

        alert = ModelAlert(
            alert_id=str(uuid.uuid4()),
            model_id=model_id,
            metric_type=metric_type,
            severity=severity,
            message=(
                f"{metric_type.value} breached threshold for model '{model_id}': "
                f"value={value:.6f}, threshold={threshold:.6f}"
            ),
            threshold=threshold,
        )
        self._alerts.append(alert)

    # ------------------------------------------------------------------ #
    # Metric querying
    # ------------------------------------------------------------------ #

    def get_metrics(
        self,
        model_id: str,
        metric_type: Optional[MonitorMetric] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
    ) -> List[ModelMetric]:
        """
        Retrieve metrics for a model, optionally filtered by type and time range.
        """
        with self._lock:
            metrics = self._metrics.get(model_id, [])
            results = []
            for m in metrics:
                if metric_type is not None and m.metric_type != metric_type:
                    continue
                if start_time is not None and m.timestamp < start_time:
                    continue
                if end_time is not None and m.timestamp > end_time:
                    continue
                results.append(m)
            return results

    def get_latest_metric(
        self,
        model_id: str,
        metric_type: MonitorMetric,
    ) -> Optional[ModelMetric]:
        """Return the most recent metric of the given type for a model."""
        with self._lock:
            metrics = self._metrics.get(model_id, [])
            for m in reversed(metrics):
                if m.metric_type == metric_type:
                    return m
            return None

    # ------------------------------------------------------------------ #
    # Threshold management
    # ------------------------------------------------------------------ #

    def set_threshold(
        self,
        model_id: str,
        metric_type: MonitorMetric,
        threshold: float,
    ) -> bool:
        """
        Set a threshold for a specific metric on a model.

        Returns True if the threshold was set successfully.
        """
        with self._lock:
            if model_id not in self._thresholds:
                self._thresholds[model_id] = {}
            self._thresholds[model_id][metric_type.value] = float(threshold)
            return True

    # ------------------------------------------------------------------ #
    # Alert management
    # ------------------------------------------------------------------ #

    def check_alerts(self, model_id: str) -> List[ModelAlert]:
        """Return all unacknowledged alerts for a model."""
        with self._lock:
            return [a for a in self._alerts if a.model_id == model_id and not a.acknowledged]

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert by its alert_id."""
        with self._lock:
            for alert in self._alerts:
                if alert.alert_id == alert_id:
                    alert.acknowledged = True
                    return True
            return False

    def get_alerts(
        self,
        model_id: Optional[str] = None,
        severity: Optional[AlertSeverity] = None,
        acknowledged: Optional[bool] = None,
    ) -> List[ModelAlert]:
        """
        Retrieve alerts with optional filters for model, severity, and ack status.
        """
        with self._lock:
            results = []
            for alert in self._alerts:
                if model_id is not None and alert.model_id != model_id:
                    continue
                if severity is not None and alert.severity != severity:
                    continue
                if acknowledged is not None and alert.acknowledged != acknowledged:
                    continue
                results.append(alert)
            return results

    # ------------------------------------------------------------------ #
    # Drift detection
    # ------------------------------------------------------------------ #

    def detect_drift(
        self,
        model_id: str,
        reference_window: int = 100,
    ) -> Optional[ModelAlert]:
        """
        Detect drift for a model by comparing the mean of the latest metric
        values against an earlier reference window.

        Uses mean comparison on ACCURACY metrics.  If no ACCURACY metrics are
        available, falls back to F1, then PRECISION, then RECALL.

        Returns a drift alert if drift is detected, otherwise None.
        """
        with self._lock:
            metrics = self._metrics.get(model_id, [])
            if not metrics:
                return None

            # Pick the best available metric type for drift detection
            for candidate in (
                MonitorMetric.ACCURACY,
                MonitorMetric.F1,
                MonitorMetric.PRECISION,
                MonitorMetric.RECALL,
            ):
                values = [m.value for m in metrics if m.metric_type == candidate]
                if len(values) >= reference_window * 2:
                    metric_type = candidate
                    break
            else:
                # Not enough data for any candidate
                return None

            # Split into reference (older) and current (newer) windows
            ref_values = values[-reference_window * 2:-reference_window]
            cur_values = values[-reference_window:]

            ref_mean = statistics.mean(ref_values)
            cur_mean = statistics.mean(cur_values)

            # Simple mean-comparison drift rule
            drift_ratio = abs(cur_mean - ref_mean) / max(abs(ref_mean), 1e-9)
            drift_detected = drift_ratio > 0.05  # 5% change threshold

            if not drift_detected:
                return None

            severity = AlertSeverity.CRITICAL if drift_ratio > 0.15 else AlertSeverity.WARNING

            alert = ModelAlert(
                alert_id=str(uuid.uuid4()),
                model_id=model_id,
                metric_type=MonitorMetric.DRIFT,
                severity=severity,
                message=(
                    f"Drift detected for model '{model_id}' ({metric_type.value}): "
                    f"ref_mean={ref_mean:.6f}, cur_mean={cur_mean:.6f}, "
                    f"ratio={drift_ratio:.4f}"
                ),
                threshold=0.05,
            )
            self._alerts.append(alert)
            return alert

    # ------------------------------------------------------------------ #
    # Performance summary & health score
    # ------------------------------------------------------------------ #

    def get_performance_summary(self, model_id: str) -> Dict[str, Any]:
        """
        Return a performance summary dictionary for a model.

        Includes count, mean, min, max, and latest value per metric type.
        """
        with self._lock:
            metrics = self._metrics.get(model_id, [])
            summary: Dict[str, Any] = {"model_id": model_id, "metrics": {}}
            for metric_type in MonitorMetric:
                values = [m.value for m in metrics if m.metric_type == metric_type]
                if not values:
                    continue
                summary["metrics"][metric_type.value] = {
                    "count": len(values),
                    "mean": statistics.mean(values),
                    "min": min(values),
                    "max": max(values),
                    "latest": values[-1],
                }
            return summary

    def get_health_score(self, model_id: str) -> float:
        """
        Compute a health score between 0 and 100 for a model.

        Based on accuracy and latency:
        - Accuracy contributes up to 70 points.
        - Latency contributes up to 30 points (lower latency is better).

        If no relevant metrics exist, returns 50.0 as a neutral default.
        """
        with self._lock:
            metrics = self._metrics.get(model_id, [])
            acc_values = [m.value for m in metrics if m.metric_type == MonitorMetric.ACCURACY]
            lat_values = [m.value for m in metrics if m.metric_type == MonitorMetric.LATENCY]

            if not acc_values and not lat_values:
                return 50.0

            score = 0.0

            if acc_values:
                latest_acc = acc_values[-1]
                # Scale accuracy (assumed 0-1) to 0-70
                score += min(max(latest_acc, 0.0), 1.0) * 70.0
            else:
                score += 35.0  # neutral half-score

            if lat_values:
                latest_lat = lat_values[-1]
                # Assume latency good if <= 10ms, bad if >= 1000ms
                if latest_lat <= 10.0:
                    lat_score = 30.0
                elif latest_lat >= 1000.0:
                    lat_score = 0.0
                else:
                    lat_score = 30.0 * (1.0 - (latest_lat - 10.0) / 990.0)
                score += lat_score
            else:
                score += 15.0  # neutral half-score

            return round(min(max(score, 0.0), 100.0), 2)

    # ------------------------------------------------------------------ #
    # Cleanup
    # ------------------------------------------------------------------ #

    def clear_metrics(self, model_id: Optional[str] = None) -> int:
        """
        Clear recorded metrics.

        If model_id is provided, only metrics for that model are cleared.
        Returns the number of metric entries removed.
        """
        with self._lock:
            if model_id is not None:
                removed = len(self._metrics.get(model_id, []))
                if model_id in self._metrics:
                    del self._metrics[model_id]
                return removed
            total = sum(len(v) for v in self._metrics.values())
            self._metrics.clear()
            return total

    def clear_alerts(self, model_id: Optional[str] = None) -> int:
        """
        Clear alerts.

        If model_id is provided, only alerts for that model are cleared.
        Returns the number of alerts removed.
        """
        with self._lock:
            if model_id is not None:
                original = len(self._alerts)
                self._alerts = [a for a in self._alerts if a.model_id != model_id]
                return original - len(self._alerts)
            removed = len(self._alerts)
            self._alerts.clear()
            return removed

    # ------------------------------------------------------------------ #
    # Statistics
    # ------------------------------------------------------------------ #

    def get_statistics(self) -> Dict[str, Any]:
        """Return aggregate statistics about the monitor contents."""
        with self._lock:
            total_metrics = sum(len(v) for v in self._metrics.values())
            total_alerts = len(self._alerts)
            unacknowledged = sum(1 for a in self._alerts if not a.acknowledged)
            model_count = len(self._metrics)

            severity_counts: Dict[str, int] = {s.value: 0 for s in AlertSeverity}
            for alert in self._alerts:
                severity_counts[alert.severity.value] += 1

            return {
                "model_count": model_count,
                "total_metrics": total_metrics,
                "total_alerts": total_alerts,
                "unacknowledged_alerts": unacknowledged,
                "severity_distribution": severity_counts,
                "threshold_count": sum(len(v) for v in self._thresholds.values()),
            }


# ---------------------------------------------------------------------- #
# Singleton management with double-checked locking
# ---------------------------------------------------------------------- #

_model_monitor_instance: Optional[ModelMonitor] = None
_model_monitor_lock: threading.Lock = threading.Lock()


def get_model_monitor() -> ModelMonitor:
    """
    Return the global ModelMonitor singleton.

    Uses double-checked locking for thread-safe lazy initialization.
    """
    global _model_monitor_instance
    if _model_monitor_instance is None:
        with _model_monitor_lock:
            if _model_monitor_instance is None:
                _model_monitor_instance = ModelMonitor()
    return _model_monitor_instance


def reset_model_monitor() -> None:
    """Reset the global singleton instance. Intended for testing only."""
    global _model_monitor_instance
    with _model_monitor_lock:
        _model_monitor_instance = None
