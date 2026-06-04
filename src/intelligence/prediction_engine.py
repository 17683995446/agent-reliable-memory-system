"""
Prediction Engine module for the Agent Reliable Memory System.

Stage 395 - Intelligence Layer

This module provides deterministic prediction capabilities with no external
model dependencies. It supports regression, classification, forecasting, and
anomaly detection using pure Python algorithms.

Design Principles:
    1. First Principles: deterministic rules, no model dependencies
    2. Thread-safe using threading.RLock
    3. Global singleton via get_prediction_engine() with double-checked locking
    4. Use Python dataclasses for data structures, Enum for types
    5. Minimal dependencies, no circular dependencies

Algorithms:
    - Linear regression for regression tasks (least-squares)
    - K-nearest neighbor for classification (Euclidean distance)
    - Moving average for forecasting (simple or weighted)
    - Z-score for anomaly detection (standard deviation based)

All implementations are pure Python with no external libraries.
"""

from __future__ import annotations

import math
import statistics
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple


class PredictionType(Enum):
    """Enumeration of supported prediction types."""

    REGRESSION = auto()
    CLASSIFICATION = auto()
    FORECASTING = auto()
    ANOMALY_DETECTION = auto()


class PredictionConfidence(Enum):
    """Enumeration of confidence levels for predictions."""

    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()


@dataclass
class TimeSeriesPoint:
    """Represents a single point in a time series.

    Attributes:
        timestamp: Unix timestamp of the observation.
        value: Numeric value at this point in time.
        metadata: Optional additional data attached to the point.
    """

    timestamp: float
    value: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PredictionResult:
    """Represents the outcome of a prediction operation.

    Attributes:
        prediction_id: Unique identifier for the prediction result.
        prediction_type: The type of prediction that was performed.
        predicted_value: The value predicted by the model.
        confidence: Confidence level of the prediction.
        actual_value: The actual observed value (if available).
        error: Prediction error (actual - predicted) if actual_value is set.
        metadata: Optional additional data attached to the result.
    """

    prediction_id: str
    prediction_type: PredictionType
    predicted_value: float
    confidence: PredictionConfidence
    actual_value: Optional[float] = None
    error: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PredictionModel:
    """Represents a registered prediction model.

    Attributes:
        model_id: Unique identifier for the model.
        prediction_type: The type of predictions this model performs.
        features: List of feature names or descriptors.
        parameters: Model-specific hyperparameters.
        trained_at: Unix timestamp when the model was created.
    """

    model_id: str
    prediction_type: PredictionType
    features: List[str]
    parameters: Dict[str, Any]
    trained_at: float


class PredictionEngine:
    """Deterministic prediction engine for multiple task types.

    Thread-safe via internal RLock. All public methods are reentrant-safe.

    Attributes:
        _models: Registered prediction models indexed by model_id.
        _predictions: Chronological list of prediction results.
        _training_data: Stored training data per model_id.
        _lock: Reentrant lock protecting internal state.
    """

    def __init__(self) -> None:
        """Initialize a new PredictionEngine instance."""
        self._models: Dict[str, PredictionModel] = {}
        self._predictions: List[PredictionResult] = []
        self._training_data: Dict[str, List[Dict[str, Any]]] = {}
        self._lock: threading.RLock = threading.RLock()

    # ------------------------------------------------------------------
    # Model management
    # ------------------------------------------------------------------

    def create_model(
        self,
        prediction_type: PredictionType,
        features: List[str],
        parameters: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Register a new prediction model.

        Args:
            prediction_type: The type of predictions this model will perform.
            features: List of feature names or descriptors.
            parameters: Optional model-specific hyperparameters.

        Returns:
            The generated unique model_id.
        """
        model_id = str(uuid.uuid4())
        with self._lock:
            self._models[model_id] = PredictionModel(
                model_id=model_id,
                prediction_type=prediction_type,
                features=list(features),
                parameters=dict(parameters) if parameters else {},
                trained_at=time.time(),
            )
            self._training_data[model_id] = []
        return model_id

    def delete_model(self, model_id: str) -> bool:
        """Remove a registered model and its training data.

        Args:
            model_id: The identifier of the model to remove.

        Returns:
            True if the model existed and was removed, False otherwise.
        """
        with self._lock:
            if model_id in self._models:
                del self._models[model_id]
                self._training_data.pop(model_id, None)
                return True
            return False

    def get_model(self, model_id: str) -> Optional[PredictionModel]:
        """Retrieve a specific model by ID.

        Args:
            model_id: The identifier of the model.

        Returns:
            The PredictionModel if found, otherwise None.
        """
        with self._lock:
            return self._models.get(model_id)

    def get_all_models(self) -> List[PredictionModel]:
        """Return a snapshot of all registered models.

        Returns:
            List of PredictionModel objects.
        """
        with self._lock:
            return list(self._models.values())

    # ------------------------------------------------------------------
    # Training data management
    # ------------------------------------------------------------------

    def add_training_data(
        self,
        model_id: str,
        data: Any,
    ) -> bool:
        """Add training sample(s) to a model.

        Args:
            model_id: The target model identifier.
            data: Single dict or list of dicts containing feature values and target.

        Returns:
            True if data was added, False if model not found.
        """
        with self._lock:
            if model_id not in self._models:
                return False
            if isinstance(data, list):
                for item in data:
                    self._training_data[model_id].append(dict(item))
            else:
                self._training_data[model_id].append(dict(data))
            return True

    def get_training_data(self, model_id: str) -> List[Dict[str, Any]]:
        """Retrieve training data for a model.

        Args:
            model_id: The target model identifier.

        Returns:
            List of training samples, empty if model not found.
        """
        with self._lock:
            return list(self._training_data.get(model_id, []))

    def clear_training_data(self, model_id: str) -> bool:
        """Clear training data for a model.

        Args:
            model_id: The target model identifier.

        Returns:
            True if cleared, False if model not found.
        """
        with self._lock:
            if model_id not in self._models:
                return False
            self._training_data[model_id].clear()
            return True

    # ------------------------------------------------------------------
    # Generic prediction dispatcher
    # ------------------------------------------------------------------

    def predict(
        self,
        model_id: str,
        input_data: Dict[str, Any],
    ) -> PredictionResult:
        """Make a prediction using the specified model.

        Dispatches to the appropriate specialized method based on the
        model's prediction_type.

        Args:
            model_id: The identifier of the model to use.
            input_data: Input features for the prediction.

        Returns:
            A PredictionResult containing the predicted value.

        Raises:
            ValueError: If the model does not exist.
        """
        model = self.get_model(model_id)
        if model is None:
            raise ValueError(f"Model {model_id} not found.")

        if model.prediction_type == PredictionType.REGRESSION:
            return self.predict_regression(model_id, input_data)
        elif model.prediction_type == PredictionType.CLASSIFICATION:
            return self.predict_classification(model_id, input_data)
        elif model.prediction_type == PredictionType.FORECASTING:
            return self.predict_forecast(model_id, input_data)
        elif model.prediction_type == PredictionType.ANOMALY_DETECTION:
            return self.predict_anomaly(model_id, input_data)
        else:
            raise ValueError(f"Unsupported prediction type: {model.prediction_type}")

    # ------------------------------------------------------------------
    # REGRESSION: Linear regression (least-squares)
    # ------------------------------------------------------------------

    def predict_regression(
        self,
        model_id: str,
        input_data: Dict[str, Any],
    ) -> PredictionResult:
        """Perform linear regression prediction.

        Uses ordinary least-squares on stored training data. If no training
        data exists, falls back to a simple weighted average of input values.

        Args:
            model_id: The regression model identifier.
            input_data: Dictionary of feature values.

        Returns:
            A PredictionResult with the predicted continuous value.
        """
        training = self.get_training_data(model_id)

        if not training:
            # Fallback: average of numeric input values
            numeric_values = [
                float(v) for v in input_data.values()
                if isinstance(v, (int, float))
            ]
            predicted = statistics.mean(numeric_values) if numeric_values else 0.0
            confidence = PredictionConfidence.LOW
            reasoning = "No training data; used input average fallback."
        else:
            predicted, confidence = self._linear_regression_predict(
                training, input_data
            )
            reasoning = "Predicted using ordinary least-squares linear regression."

        result = PredictionResult(
            prediction_id=str(uuid.uuid4()),
            prediction_type=PredictionType.REGRESSION,
            predicted_value=predicted,
            confidence=confidence,
            metadata={"reasoning": reasoning, "input_data": dict(input_data)},
        )
        with self._lock:
            self._predictions.append(result)
        return result

    def _linear_regression_predict(
        self,
        training: List[Dict[str, Any]],
        input_data: Dict[str, Any],
    ) -> Tuple[float, PredictionConfidence]:
        """Internal linear regression using a single composite feature.

        Extracts all numeric features from training samples, computes the
        mean of features per sample as X and uses the 'target' field as Y.
        Fits Y = a + b*X via least-squares, then predicts on input.

        Returns:
            Tuple of (predicted_value, confidence).
        """
        xs: List[float] = []
        ys: List[float] = []

        for sample in training:
            numeric = [
                float(v) for k, v in sample.items()
                if k != "target" and isinstance(v, (int, float))
            ]
            if numeric and "target" in sample:
                xs.append(statistics.mean(numeric))
                ys.append(float(sample["target"]))

        if len(xs) < 2:
            # Not enough data points for regression
            fallback = ys[0] if ys else 0.0
            return fallback, PredictionConfidence.LOW

        n = len(xs)
        mean_x = statistics.mean(xs)
        mean_y = statistics.mean(ys)

        numerator = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
        denominator = sum((xs[i] - mean_x) ** 2 for i in range(n))

        if denominator == 0:
            return mean_y, PredictionConfidence.LOW

        slope = numerator / denominator
        intercept = mean_y - slope * mean_x

        # Compute R-squared for confidence
        ss_res = sum((ys[i] - (intercept + slope * xs[i])) ** 2 for i in range(n))
        ss_tot = sum((ys[i] - mean_y) ** 2 for i in range(n))
        r_squared = 1.0 - (ss_res / ss_tot) if ss_tot != 0 else 1.0

        # Predict on input
        input_numeric = [
            float(v) for k, v in input_data.items()
            if k != "target" and isinstance(v, (int, float))
        ]
        input_mean = statistics.mean(input_numeric) if input_numeric else mean_x
        predicted = intercept + slope * input_mean

        if r_squared > 0.9:
            confidence = PredictionConfidence.HIGH
        elif r_squared > 0.6:
            confidence = PredictionConfidence.MEDIUM
        else:
            confidence = PredictionConfidence.LOW

        return predicted, confidence

    # ------------------------------------------------------------------
    # CLASSIFICATION: K-nearest neighbor (Euclidean distance)
    # ------------------------------------------------------------------

    def predict_classification(
        self,
        model_id: str,
        input_data: Dict[str, Any],
    ) -> PredictionResult:
        """Perform K-nearest neighbor classification.

        Uses Euclidean distance on numeric features. K defaults to 3
        or is read from model parameters.

        Args:
            model_id: The classification model identifier.
            input_data: Dictionary of feature values.

        Returns:
            A PredictionResult with the predicted class label.
        """
        model = self.get_model(model_id)
        training = self.get_training_data(model_id)
        k = int(model.parameters.get("k", 3)) if model else 3

        if not training:
            result = PredictionResult(
                prediction_id=str(uuid.uuid4()),
                prediction_type=PredictionType.CLASSIFICATION,
                predicted_value=0.0,
                confidence=PredictionConfidence.LOW,
                metadata={"reasoning": "No training data available."},
            )
            with self._lock:
                self._predictions.append(result)
            return result

        predicted_class, confidence = self._knn_predict(
            training, input_data, k
        )

        result = PredictionResult(
            prediction_id=str(uuid.uuid4()),
            prediction_type=PredictionType.CLASSIFICATION,
            predicted_value=float(predicted_class),
            confidence=confidence,
            metadata={
                "reasoning": f"K-NN classification with k={k}.",
                "input_data": dict(input_data),
            },
        )
        with self._lock:
            self._predictions.append(result)
        return result

    def _knn_predict(
        self,
        training: List[Dict[str, Any]],
        input_data: Dict[str, Any],
        k: int,
    ) -> Tuple[float, PredictionConfidence]:
        """Internal K-NN prediction.

        Computes Euclidean distance between numeric features, selects the
        k nearest neighbors, and returns the majority class.

        Returns:
            Tuple of (predicted_class, confidence).
        """
        distances: List[Tuple[float, Any]] = []

        input_numeric = {
            k: float(v) for k, v in input_data.items()
            if isinstance(v, (int, float))
        }

        for sample in training:
            sample_numeric = {
                k: float(v) for k, v in sample.items()
                if k != "target" and isinstance(v, (int, float))
            }
            # Use common keys
            common_keys = set(input_numeric.keys()) & set(sample_numeric.keys())
            if not common_keys:
                continue
            dist = math.sqrt(
                sum(
                    (input_numeric[k] - sample_numeric[k]) ** 2
                    for k in common_keys
                )
            )
            target = sample.get("target", 0)
            distances.append((dist, target))

        if not distances:
            return 0.0, PredictionConfidence.LOW

        distances.sort(key=lambda x: x[0])
        k = min(k, len(distances))
        neighbors = distances[:k]

        # Majority vote
        votes: Dict[Any, int] = {}
        for _, target in neighbors:
            votes[target] = votes.get(target, 0) + 1

        best_class = max(votes, key=votes.get)
        best_count = votes[best_class]
        vote_ratio = best_count / k

        if vote_ratio > 0.8:
            confidence = PredictionConfidence.HIGH
        elif vote_ratio > 0.5:
            confidence = PredictionConfidence.MEDIUM
        else:
            confidence = PredictionConfidence.LOW

        # Try to return numeric class label
        try:
            predicted = float(best_class)
        except (ValueError, TypeError):
            predicted = float(hash(best_class) % 1000000)

        return predicted, confidence

    # ------------------------------------------------------------------
    # FORECASTING: Moving average
    # ------------------------------------------------------------------

    def predict_forecast(
        self,
        model_id: str,
        time_series: Dict[str, Any],
    ) -> PredictionResult:
        """Perform time series forecasting using moving average.

        Expects time_series to contain either:
            - "points": List[TimeSeriesPoint]
            - "values": List[float]

        Window size defaults to 3 or is read from model parameters.

        Args:
            model_id: The forecasting model identifier.
            time_series: Dictionary containing time series data.

        Returns:
            A PredictionResult with the forecasted value.
        """
        model = self.get_model(model_id)
        window = int(model.parameters.get("window", 3)) if model else 3

        # Extract values
        values: List[float] = []
        if "points" in time_series:
            points = time_series["points"]
            if points and isinstance(points[0], TimeSeriesPoint):
                values = [p.value for p in points]
            elif points and isinstance(points[0], dict):
                values = [float(p.get("value", 0)) for p in points]
        elif "values" in time_series:
            raw = time_series["values"]
            values = [float(v) for v in raw]

        if not values:
            result = PredictionResult(
                prediction_id=str(uuid.uuid4()),
                prediction_type=PredictionType.FORECASTING,
                predicted_value=0.0,
                confidence=PredictionConfidence.LOW,
                metadata={"reasoning": "No time series data provided."},
            )
            with self._lock:
                self._predictions.append(result)
            return result

        predicted, confidence = self._moving_average_predict(values, window)

        result = PredictionResult(
            prediction_id=str(uuid.uuid4()),
            prediction_type=PredictionType.FORECASTING,
            predicted_value=predicted,
            confidence=confidence,
            metadata={
                "reasoning": f"Simple moving average with window={window}.",
                "window": window,
                "series_length": len(values),
            },
        )
        with self._lock:
            self._predictions.append(result)
        return result

    def _moving_average_predict(
        self,
        values: List[float],
        window: int,
    ) -> Tuple[float, PredictionConfidence]:
        """Internal moving average forecast.

        Uses the average of the last *window* values as the forecast.
        Confidence is based on the stability (coefficient of variation)
        of the values in the window.

        Returns:
            Tuple of (predicted_value, confidence).
        """
        window = max(1, min(window, len(values)))
        recent = values[-window:]
        predicted = statistics.mean(recent)

        if len(recent) > 1:
            stdev = statistics.stdev(recent)
            mean_abs = abs(predicted)
            cv = stdev / mean_abs if mean_abs > 0 else 0.0
            if cv < 0.1:
                confidence = PredictionConfidence.HIGH
            elif cv < 0.3:
                confidence = PredictionConfidence.MEDIUM
            else:
                confidence = PredictionConfidence.LOW
        else:
            confidence = PredictionConfidence.LOW

        return predicted, confidence

    # ------------------------------------------------------------------
    # ANOMALY DETECTION: Z-score
    # ------------------------------------------------------------------

    def predict_anomaly(
        self,
        model_id: str,
        input_data: Dict[str, Any],
    ) -> PredictionResult:
        """Perform anomaly detection using z-score.

        Expects input_data to contain either:
            - "value": single float to test
            - "values": list of floats (the last one is tested)

        Threshold defaults to 2.0 or is read from model parameters.
        Returns predicted_value = 1.0 if anomaly detected, 0.0 otherwise.

        Args:
            model_id: The anomaly detection model identifier.
            input_data: Dictionary containing value(s) to test.

        Returns:
            A PredictionResult with anomaly flag (1.0 = anomaly, 0.0 = normal).
        """
        model = self.get_model(model_id)
        threshold = float(model.parameters.get("threshold", 2.0)) if model else 2.0

        # Extract test value and context
        if "value" in input_data:
            test_value = float(input_data["value"])
            context = input_data.get("values", [test_value])
        elif "values" in input_data:
            raw = input_data["values"]
            if not raw:
                result = PredictionResult(
                    prediction_id=str(uuid.uuid4()),
                    prediction_type=PredictionType.ANOMALY_DETECTION,
                    predicted_value=0.0,
                    confidence=PredictionConfidence.LOW,
                    metadata={"reasoning": "No values provided for anomaly detection."},
                )
                with self._lock:
                    self._predictions.append(result)
                return result
            test_value = float(raw[-1])
            context = [float(v) for v in raw]
        else:
            # Try to find any numeric value
            numeric = [float(v) for v in input_data.values() if isinstance(v, (int, float))]
            if not numeric:
                result = PredictionResult(
                    prediction_id=str(uuid.uuid4()),
                    prediction_type=PredictionType.ANOMALY_DETECTION,
                    predicted_value=0.0,
                    confidence=PredictionConfidence.LOW,
                    metadata={"reasoning": "No numeric values found in input."},
                )
                with self._lock:
                    self._predictions.append(result)
                return result
            test_value = numeric[-1]
            context = numeric

        is_anomaly, z_score, confidence = self._zscore_detect(
            context, test_value, threshold
        )

        result = PredictionResult(
            prediction_id=str(uuid.uuid4()),
            prediction_type=PredictionType.ANOMALY_DETECTION,
            predicted_value=1.0 if is_anomaly else 0.0,
            confidence=confidence,
            metadata={
                "reasoning": (
                    f"Z-score={z_score:.4f} vs threshold={threshold}. "
                    f"{'Anomaly detected' if is_anomaly else 'Normal'}."
                ),
                "z_score": z_score,
                "threshold": threshold,
                "test_value": test_value,
            },
        )
        with self._lock:
            self._predictions.append(result)
        return result

    def _zscore_detect(
        self,
        values: List[float],
        test_value: float,
        threshold: float,
    ) -> Tuple[bool, float, PredictionConfidence]:
        """Internal z-score anomaly detection.

        Computes mean and standard deviation of *values* (excluding test_value
        if it is the last element and there are at least 2 values), then
        computes the z-score of test_value.

        Returns:
            Tuple of (is_anomaly, z_score, confidence).
        """
        if len(values) >= 2 and abs(values[-1] - test_value) < 1e-9:
            # Exclude test value from baseline
            baseline = values[:-1]
        else:
            baseline = values

        if not baseline:
            baseline = values

        n = len(baseline)
        if n == 0:
            return False, 0.0, PredictionConfidence.LOW

        mean = statistics.mean(baseline)
        stdev = statistics.stdev(baseline) if n > 1 else 0.0

        if stdev == 0:
            z_score = 0.0 if abs(test_value - mean) < 1e-9 else float("inf")
        else:
            z_score = (test_value - mean) / stdev

        is_anomaly = abs(z_score) > threshold

        # Confidence based on how far the z-score exceeds the threshold
        if abs(z_score) > threshold * 2:
            confidence = PredictionConfidence.HIGH
        elif abs(z_score) > threshold * 1.2:
            confidence = PredictionConfidence.MEDIUM
        else:
            confidence = PredictionConfidence.LOW

        return is_anomaly, z_score, confidence

    # ------------------------------------------------------------------
    # Evaluation and queries
    # ------------------------------------------------------------------

    def evaluate_predictions(self, model_id: str) -> Dict[str, float]:
        """Evaluate prediction accuracy for a given model.

        Computes Mean Absolute Error (MAE), Root Mean Squared Error (RMSE),
        and Mean Absolute Percentage Error (MAPE) for predictions that have
        an actual_value recorded.

        Args:
            model_id: The model to evaluate.

        Returns:
            Dictionary with evaluation metrics.
        """
        with self._lock:
            relevant = [
                p for p in self._predictions
                if p.prediction_type == self._models.get(model_id, PredictionModel(
                    model_id="", prediction_type=PredictionType.REGRESSION,
                    features=[], parameters={}, trained_at=0.0
                )).prediction_type and p.actual_value is not None
            ]

        if not relevant:
            return {"mae": 0.0, "rmse": 0.0, "mape": 0.0, "count": 0.0}

        errors = [p.error for p in relevant if p.error is not None]
        if not errors:
            errors = [p.actual_value - p.predicted_value for p in relevant if p.actual_value is not None]

        mae = statistics.mean(abs(e) for e in errors) if errors else 0.0
        rmse = math.sqrt(statistics.mean(e ** 2 for e in errors)) if errors else 0.0

        mape_values = []
        for p in relevant:
            if p.actual_value is not None and abs(p.actual_value) > 1e-9:
                mape_values.append(abs((p.actual_value - p.predicted_value) / p.actual_value))
        mape = statistics.mean(mape_values) * 100 if mape_values else 0.0

        return {
            "mae": mae,
            "rmse": rmse,
            "mape": mape,
            "count": float(len(relevant)),
        }

    def get_prediction(self, prediction_id: str) -> Optional[PredictionResult]:
        """Retrieve a specific prediction by ID.

        Args:
            prediction_id: The unique identifier of the prediction.

        Returns:
            The PredictionResult if found, otherwise None.
        """
        with self._lock:
            for p in self._predictions:
                if p.prediction_id == prediction_id:
                    return p
            return None

    def get_predictions(
        self,
        model_id: Optional[str] = None,
        prediction_type: Optional[PredictionType] = None,
    ) -> List[PredictionResult]:
        """Retrieve predictions with optional filtering.

        Args:
            model_id: If provided, filter by predictions associated with
                this model's prediction_type.
            prediction_type: If provided, filter by this type.

        Returns:
            List of matching PredictionResult objects.
        """
        with self._lock:
            results = list(self._predictions)

        if model_id is not None:
            model = self.get_model(model_id)
            if model is not None:
                target_type = model.prediction_type
                results = [p for p in results if p.prediction_type == target_type]

        if prediction_type is not None:
            results = [p for p in results if p.prediction_type == prediction_type]

        return results

    def clear_predictions(self) -> int:
        """Erase all stored prediction results.

        Returns:
            Number of records that were removed.
        """
        with self._lock:
            count = len(self._predictions)
            self._predictions.clear()
            return count

    def get_statistics(self) -> Dict[str, Any]:
        """Compute summary statistics over predictions and models.

        Returns:
            Dictionary containing counts, averages, and breakdowns by type
            and confidence.
        """
        with self._lock:
            total_models = len(self._models)
            total_predictions = len(self._predictions)

            by_type: Dict[str, int] = {}
            by_confidence: Dict[str, int] = {}
            training_counts: Dict[str, int] = {}

            for model in self._models.values():
                t = model.prediction_type.name
                by_type[t] = by_type.get(t, 0) + 1
                training_counts[model.model_id] = len(
                    self._training_data.get(model.model_id, [])
                )

            for pred in self._predictions:
                c = pred.confidence.name
                by_confidence[c] = by_confidence.get(c, 0) + 1

            return {
                "total_models": total_models,
                "total_predictions": total_predictions,
                "by_type": by_type,
                "by_confidence": by_confidence,
                "training_samples": sum(training_counts.values()),
            }


# ------------------------------------------------------------------------------
# Singleton management with double-checked locking
# ------------------------------------------------------------------------------

_prediction_engine_instance: Optional[PredictionEngine] = None
_prediction_engine_lock: threading.Lock = threading.Lock()


def get_prediction_engine() -> PredictionEngine:
    """Return the global PredictionEngine singleton.

    Uses double-checked locking for efficient, thread-safe initialisation.

    Returns:
        The singleton PredictionEngine instance.
    """
    global _prediction_engine_instance
    if _prediction_engine_instance is None:
        with _prediction_engine_lock:
            if _prediction_engine_instance is None:
                _prediction_engine_instance = PredictionEngine()
    return _prediction_engine_instance


def reset_prediction_engine() -> None:
    """Reset the global singleton instance.

    This is intended primarily for testing scenarios where a fresh engine
    with empty state is required.
    """
    global _prediction_engine_instance
    with _prediction_engine_lock:
        _prediction_engine_instance = None
