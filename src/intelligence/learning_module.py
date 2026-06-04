"""
Learning Module for the Agent Reliable Memory System.

Stage 394 - Intelligence Layer

This module provides deterministic machine learning capabilities with no external
model dependencies. It supports supervised, unsupervised, reinforcement, transfer,
and active learning types using pure Python implementations.

Design Principles:
    1. First Principles: deterministic rules, no model dependencies
    2. Thread-safe using threading.RLock
    3. Global singleton via get_learning_module() with double-checked locking
    4. Use Python dataclasses for data structures, Enum for types
    5. Minimal dependencies, no circular dependencies

Algorithms:
    - Supervised: simple perceptron-like online learning
    - Unsupervised: K-means-like clustering
    - Reinforcement: Q-table based learning
    - Transfer: weighted voting ensemble
    - Active: uncertainty sampling for query selection

No external ML libraries are used. All implementations are deterministic
and self-contained.
"""

from __future__ import annotations

import math
import random
import statistics
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple


class LearningType(Enum):
    """Enumeration of supported learning types."""

    SUPERVISED = auto()
    UNSUPERVISED = auto()
    REINFORCEMENT = auto()
    TRANSFER = auto()
    ACTIVE = auto()


class LearningStatus(Enum):
    """Enumeration of possible model training statuses."""

    TRAINING = auto()
    TRAINED = auto()
    EVALUATING = auto()
    FAILED = auto()


@dataclass
class ModelConfig:
    """Configuration for a registered learning model.

    Attributes:
        model_id: Unique identifier for the model.
        learning_type: The type of learning algorithm used.
        features: List of feature names expected by the model.
        hyperparameters: Dictionary of algorithm-specific hyperparameters.
        metadata: Optional additional data attached to the model.
    """

    model_id: str
    learning_type: LearningType
    features: List[str]
    hyperparameters: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TrainingResult:
    """Result of a model training operation.

    Attributes:
        result_id: Unique identifier for the training result.
        model_id: The model that was trained.
        accuracy: Training accuracy in range [0.0, 1.0].
        loss: Final loss value (lower is better).
        epochs: Number of training epochs completed.
        duration_ms: Training duration in milliseconds.
        metadata: Optional additional data about the training run.
    """

    result_id: str
    model_id: str
    accuracy: float
    loss: float
    epochs: int
    duration_ms: int
    metadata: Dict[str, Any] = field(default_factory=dict)


class LearningModule:
    """Deterministic learning module for multiple learning paradigms.

    Thread-safe via internal RLock. All public methods are reentrant-safe.

    Attributes:
        _models: Registered model configurations indexed by model_id.
        _training_history: Chronological list of TrainingResult objects.
        _weights: Learned feature weights indexed by model_id.
        _model_state: Opaque algorithm-specific state indexed by model_id.
        _lock: Reentrant lock protecting internal state.
    """

    def __init__(self) -> None:
        """Initialize a new LearningModule instance."""
        self._models: Dict[str, ModelConfig] = {}
        self._training_history: List[TrainingResult] = []
        self._weights: Dict[str, Dict[str, float]] = {}
        self._model_state: Dict[str, Any] = {}
        self._lock: threading.RLock = threading.RLock()

    # ------------------------------------------------------------------
    # Model lifecycle
    # ------------------------------------------------------------------

    def create_model(
        self,
        learning_type: LearningType,
        features: List[str],
        hyperparameters: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Register a new model configuration.

        Args:
            learning_type: The learning algorithm to use.
            features: List of feature names for input data.
            hyperparameters: Optional algorithm-specific settings.

        Returns:
            The generated unique model_id.
        """
        model_id = str(uuid.uuid4())
        hyperparameters = hyperparameters or {}

        with self._lock:
            self._models[model_id] = ModelConfig(
                model_id=model_id,
                learning_type=learning_type,
                features=list(features),
                hyperparameters=dict(hyperparameters),
                metadata={"created_at": time.time(), "status": LearningStatus.TRAINING.name},
            )
            # Initialize weights to zero for all features
            self._weights[model_id] = {f: 0.0 for f in features}
            # Initialize algorithm-specific state
            self._model_state[model_id] = self._init_state(learning_type, hyperparameters)

        return model_id

    def delete_model(self, model_id: str) -> bool:
        """Remove a registered model and all associated state.

        Args:
            model_id: The identifier of the model to remove.

        Returns:
            True if the model existed and was removed, False otherwise.
        """
        with self._lock:
            if model_id not in self._models:
                return False
            del self._models[model_id]
            del self._weights[model_id]
            del self._model_state[model_id]
            # Clean training history for this model
            self._training_history = [
                r for r in self._training_history if r.model_id != model_id
            ]
            return True

    def get_model(self, model_id: str) -> Optional[ModelConfig]:
        """Retrieve a specific model configuration.

        Args:
            model_id: The identifier of the model.

        Returns:
            The ModelConfig if found, otherwise None.
        """
        with self._lock:
            return self._models.get(model_id)

    def get_all_models(self) -> List[ModelConfig]:
        """Return a snapshot of all registered models.

        Returns:
            List of ModelConfig objects.
        """
        with self._lock:
            return list(self._models.values())

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train(
        self,
        model_id: str,
        training_data: List[Dict[str, Any]],
    ) -> TrainingResult:
        """Train a model on the provided dataset.

        Args:
            model_id: The model to train.
            training_data: List of data records. For supervised learning,
                each record should contain a 'label' key with value 0 or 1.
                For reinforcement learning, each record should contain
                'state', 'action', 'reward', and optionally 'next_state'.

        Returns:
            TrainingResult summarising the training outcome.
        """
        start_time = time.time()
        result_id = str(uuid.uuid4())

        with self._lock:
            model = self._models.get(model_id)
            if model is None:
                return TrainingResult(
                    result_id=result_id,
                    model_id=model_id,
                    accuracy=0.0,
                    loss=float("inf"),
                    epochs=0,
                    duration_ms=0,
                    metadata={"error": "Model not found"},
                )

            model.metadata["status"] = LearningStatus.TRAINING.name
            learning_type = model.learning_type
            features = model.features
            hyperparameters = model.hyperparameters
            state = self._model_state[model_id]
            weights = self._weights[model_id]

            accuracy = 0.0
            loss = float("inf")
            epochs = 0

            try:
                if learning_type == LearningType.SUPERVISED:
                    accuracy, loss, epochs = self._train_supervised(
                        training_data, features, weights, hyperparameters
                    )
                elif learning_type == LearningType.UNSUPERVISED:
                    accuracy, loss, epochs = self._train_unsupervised(
                        training_data, features, state, hyperparameters
                    )
                elif learning_type == LearningType.REINFORCEMENT:
                    accuracy, loss, epochs = self._train_reinforcement(
                        training_data, features, state, hyperparameters
                    )
                elif learning_type == LearningType.TRANSFER:
                    accuracy, loss, epochs = self._train_transfer(
                        training_data, features, weights, state, hyperparameters
                    )
                elif learning_type == LearningType.ACTIVE:
                    accuracy, loss, epochs = self._train_active(
                        training_data, features, weights, state, hyperparameters
                    )
                else:
                    raise ValueError(f"Unsupported learning type: {learning_type}")

                model.metadata["status"] = LearningStatus.TRAINED.name
                model.metadata["last_trained_at"] = time.time()

            except Exception as exc:
                model.metadata["status"] = LearningStatus.FAILED.name
                model.metadata["last_error"] = str(exc)
                loss = float("inf")
                accuracy = 0.0

            duration_ms = int((time.time() - start_time) * 1000)

            result = TrainingResult(
                result_id=result_id,
                model_id=model_id,
                accuracy=accuracy,
                loss=loss,
                epochs=epochs,
                duration_ms=duration_ms,
                metadata={"learning_type": learning_type.name},
            )
            self._training_history.append(result)
            return result

    # ------------------------------------------------------------------
    # Prediction & evaluation
    # ------------------------------------------------------------------

    def predict(self, model_id: str, input_data: Dict[str, float]) -> Dict[str, float]:
        """Generate predictions from a trained model.

        Args:
            model_id: The model to use for prediction.
            input_data: Mapping from feature names to numeric values.

        Returns:
            Dictionary of prediction outputs. For supervised learning this
            contains 'score' and 'label'. For unsupervised it contains
            'cluster'. For reinforcement it contains 'best_action' and
            'q_values'. For transfer it contains ensemble 'vote' and
            'confidence'. For active it contains 'uncertainty'.
        """
        with self._lock:
            model = self._models.get(model_id)
            if model is None:
                return {"error": "Model not found"}

            learning_type = model.learning_type
            weights = self._weights.get(model_id, {})
            state = self._model_state.get(model_id, {})
            features = model.features

            # Normalise input to only include known features
            x = {f: float(input_data.get(f, 0.0)) for f in features}

            if learning_type == LearningType.SUPERVISED:
                return self._predict_supervised(x, weights)
            elif learning_type == LearningType.UNSUPERVISED:
                return self._predict_unsupervised(x, state)
            elif learning_type == LearningType.REINFORCEMENT:
                return self._predict_reinforcement(x, state)
            elif learning_type == LearningType.TRANSFER:
                return self._predict_transfer(x, weights, state)
            elif learning_type == LearningType.ACTIVE:
                return self._predict_active(x, weights)
            else:
                return {"error": f"Unsupported learning type: {learning_type.name}"}

    def evaluate(
        self,
        model_id: str,
        test_data: List[Dict[str, Any]],
    ) -> Dict[str, float]:
        """Evaluate a trained model on test data.

        Args:
            model_id: The model to evaluate.
            test_data: List of data records with the same structure as
                training data. For supervised learning, 'label' is required.

        Returns:
            Dictionary of evaluation metrics.
        """
        with self._lock:
            model = self._models.get(model_id)
            if model is None:
                return {"error": 1.0}

            learning_type = model.learning_type
            model.metadata["status"] = LearningStatus.EVALUATING.name

            if learning_type == LearningType.SUPERVISED:
                metrics = self._evaluate_supervised(model_id, test_data)
            elif learning_type == LearningType.UNSUPERVISED:
                metrics = self._evaluate_unsupervised(model_id, test_data)
            elif learning_type == LearningType.REINFORCEMENT:
                metrics = self._evaluate_reinforcement(model_id, test_data)
            elif learning_type == LearningType.TRANSFER:
                metrics = self._evaluate_transfer(model_id, test_data)
            elif learning_type == LearningType.ACTIVE:
                metrics = self._evaluate_active(model_id, test_data)
            else:
                metrics = {"error": 1.0}

            model.metadata["status"] = LearningStatus.TRAINED.name
            return metrics

    # ------------------------------------------------------------------
    # Weight management
    # ------------------------------------------------------------------

    def update_weights(
        self,
        model_id: str,
        feature: str,
        delta: float,
    ) -> bool:
        """Update a single feature weight by a delta value.

        Args:
            model_id: The model whose weight should be updated.
            feature: The feature name.
            delta: The amount to add to the current weight.

        Returns:
            True if the update was applied, False if model or feature
            was not found.
        """
        with self._lock:
            weights = self._weights.get(model_id)
            if weights is None or feature not in weights:
                return False
            weights[feature] += float(delta)
            return True

    def get_feature_importance(self, model_id: str) -> Dict[str, float]:
        """Return the absolute importance of each feature.

        Importance is defined as the absolute value of the learned weight
        normalised to sum to 1.0.

        Args:
            model_id: The model to query.

        Returns:
            Dictionary mapping feature names to importance scores.
        """
        with self._lock:
            weights = self._weights.get(model_id)
            if weights is None:
                return {}

            total = sum(abs(w) for w in weights.values())
            if total == 0.0:
                return {f: 0.0 for f in weights}
            return {f: abs(w) / total for f, w in weights.items()}

    # ------------------------------------------------------------------
    # History & statistics
    # ------------------------------------------------------------------

    def get_training_history(self, model_id: str) -> List[TrainingResult]:
        """Return training results for a specific model.

        Args:
            model_id: The model to query.

        Returns:
            List of TrainingResult objects in chronological order.
        """
        with self._lock:
            return [r for r in self._training_history if r.model_id == model_id]

    def clear_history(self) -> int:
        """Erase all stored training history.

        Returns:
            Number of records that were removed.
        """
        with self._lock:
            count = len(self._training_history)
            self._training_history.clear()
            return count

    def get_statistics(self) -> Dict[str, Any]:
        """Compute summary statistics over all models and training history.

        Returns:
            Dictionary containing model counts, training aggregates, and
            breakdowns by learning type and status.
        """
        with self._lock:
            total_models = len(self._models)
            total_history = len(self._training_history)

            by_type: Dict[str, int] = {}
            by_status: Dict[str, int] = {}
            accuracy_sum = 0.0
            loss_sum = 0.0
            epoch_sum = 0

            for model in self._models.values():
                t = model.learning_type.name
                by_type[t] = by_type.get(t, 0) + 1
                s = model.metadata.get("status", "UNKNOWN")
                by_status[s] = by_status.get(s, 0) + 1

            for result in self._training_history:
                accuracy_sum += result.accuracy
                loss_sum += result.loss
                epoch_sum += result.epochs

            return {
                "total_models": total_models,
                "total_training_runs": total_history,
                "by_type": by_type,
                "by_status": by_status,
                "average_accuracy": accuracy_sum / total_history if total_history else 0.0,
                "average_loss": loss_sum / total_history if total_history else 0.0,
                "average_epochs": epoch_sum / total_history if total_history else 0.0,
            }

    # ------------------------------------------------------------------
    # Algorithm-specific initialisation
    # ------------------------------------------------------------------

    @staticmethod
    def _init_state(learning_type: LearningType, hyperparameters: Dict[str, Any]) -> Any:
        """Create algorithm-specific initial state."""
        if learning_type == LearningType.SUPERVISED:
            return {}
        elif learning_type == LearningType.UNSUPERVISED:
            k = int(hyperparameters.get("clusters", 3))
            return {"centroids": [], "k": k, "assignments": []}
        elif learning_type == LearningType.REINFORCEMENT:
            actions = hyperparameters.get("actions", ["a0", "a1"])
            return {"q_table": {}, "actions": list(actions), "epsilon": 0.1}
        elif learning_type == LearningType.TRANSFER:
            return {"source_models": hyperparameters.get("source_models", [])}
        elif learning_type == LearningType.ACTIVE:
            return {"queried": set(), "pool": []}
        return {}

    # ------------------------------------------------------------------
    # Supervised: perceptron-like learning
    # ------------------------------------------------------------------

    def _train_supervised(
        self,
        training_data: List[Dict[str, Any]],
        features: List[str],
        weights: Dict[str, float],
        hyperparameters: Dict[str, Any],
    ) -> Tuple[float, float, int]:
        """Online perceptron training.

        Returns:
            Tuple of (accuracy, loss, epochs).
        """
        lr = float(hyperparameters.get("learning_rate", 0.01))
        max_epochs = int(hyperparameters.get("max_epochs", 100))
        threshold = float(hyperparameters.get("threshold", 0.0))

        epochs = 0
        for epoch in range(max_epochs):
            correct = 0
            total_loss = 0.0
            for record in training_data:
                x = {f: float(record.get(f, 0.0)) for f in features}
                label = int(record.get("label", 0))
                if label not in (0, 1):
                    continue

                activation = sum(weights[f] * x[f] for f in features) + threshold
                prediction = 1 if activation >= 0 else 0
                error = label - prediction

                if error == 0:
                    correct += 1
                total_loss += float(error) ** 2

                # Update weights
                for f in features:
                    weights[f] += lr * error * x[f]
                threshold += lr * error

            epochs += 1
            accuracy = correct / len(training_data) if training_data else 0.0
            loss = total_loss / len(training_data) if training_data else 0.0

            # Early stopping if perfect accuracy
            if accuracy >= 1.0:
                break

        return accuracy, loss, epochs

    def _predict_supervised(
        self,
        x: Dict[str, float],
        weights: Dict[str, float],
    ) -> Dict[str, float]:
        """Perceptron prediction."""
        activation = sum(weights[f] * x[f] for f in weights)
        score = 1.0 / (1.0 + math.exp(-activation)) if activation != 0 else 0.5
        label = 1 if activation >= 0 else 0
        return {"score": score, "label": float(label), "activation": activation}

    def _evaluate_supervised(
        self,
        model_id: str,
        test_data: List[Dict[str, Any]],
    ) -> Dict[str, float]:
        """Evaluate supervised model with accuracy and F1-like score."""
        weights = self._weights[model_id]
        features = self._models[model_id].features
        correct = 0
        tp = fp = fn = 0

        for record in test_data:
            x = {f: float(record.get(f, 0.0)) for f in features}
            label = int(record.get("label", 0))
            activation = sum(weights[f] * x[f] for f in features)
            prediction = 1 if activation >= 0 else 0

            if prediction == label:
                correct += 1
            if prediction == 1 and label == 1:
                tp += 1
            elif prediction == 1 and label == 0:
                fp += 1
            elif prediction == 0 and label == 1:
                fn += 1

        total = len(test_data)
        accuracy = correct / total if total else 0.0
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

        return {
            "accuracy": accuracy,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }

    # ------------------------------------------------------------------
    # Unsupervised: K-means-like clustering
    # ------------------------------------------------------------------

    def _train_unsupervised(
        self,
        training_data: List[Dict[str, Any]],
        features: List[str],
        state: Dict[str, Any],
        hyperparameters: Dict[str, Any],
    ) -> Tuple[float, float, int]:
        """K-means clustering.

        Returns:
            Tuple of (accuracy, loss, epochs). Accuracy is pseudo-accuracy
            based on silhouette-like cohesion.
        """
        k = state["k"]
        max_epochs = int(hyperparameters.get("max_epochs", 50))

        # Extract vectors
        vectors = []
        for record in training_data:
            vec = [float(record.get(f, 0.0)) for f in features]
            vectors.append(vec)

        n = len(vectors)
        if n == 0:
            return 0.0, float("inf"), 0
        if k > n:
            k = n
            state["k"] = k

        # Initialise centroids randomly from data points (deterministic seed)
        rng = random.Random(42)
        centroids = [list(v) for v in rng.sample(vectors, k)]

        epochs = 0
        assignments = [0] * n
        for epoch in range(max_epochs):
            changed = False
            # Assignment step
            for i, vec in enumerate(vectors):
                best_dist = float("inf")
                best_j = 0
                for j, centroid in enumerate(centroids):
                    dist = sum((vec[d] - centroid[d]) ** 2 for d in range(len(features)))
                    if dist < best_dist:
                        best_dist = dist
                        best_j = j
                if assignments[i] != best_j:
                    assignments[i] = best_j
                    changed = True

            # Update step
            for j in range(k):
                cluster_points = [vectors[i] for i in range(n) if assignments[i] == j]
                if cluster_points:
                    for d in range(len(features)):
                        centroids[j][d] = statistics.mean(p[d] for p in cluster_points)

            epochs += 1
            if not changed:
                break

        state["centroids"] = centroids
        state["assignments"] = assignments

        # Compute inertia (sum of squared distances to nearest centroid)
        inertia = 0.0
        for i, vec in enumerate(vectors):
            c = centroids[assignments[i]]
            inertia += sum((vec[d] - c[d]) ** 2 for d in range(len(features)))

        # Pseudo-accuracy: higher cohesion (lower inertia relative to data variance) is better
        total_variance = 0.0
        for d in range(len(features)):
            col = [v[d] for v in vectors]
            if len(col) > 1:
                total_variance += statistics.variance(col)
        accuracy = 1.0 / (1.0 + inertia / (total_variance + 1e-9))
        loss = inertia / n if n else float("inf")

        return accuracy, loss, epochs

    def _predict_unsupervised(
        self,
        x: Dict[str, float],
        state: Dict[str, Any],
    ) -> Dict[str, float]:
        """Predict cluster assignment for a data point."""
        centroids = state.get("centroids", [])
        if not centroids:
            return {"cluster": -1.0, "distance": float("inf")}

        vec = list(x.values())
        best_dist = float("inf")
        best_j = 0
        for j, centroid in enumerate(centroids):
            dist = sum((vec[d] - centroid[d]) ** 2 for d in range(len(vec)))
            if dist < best_dist:
                best_dist = dist
                best_j = j

        return {"cluster": float(best_j), "distance": math.sqrt(best_dist)}

    def _evaluate_unsupervised(
        self,
        model_id: str,
        test_data: List[Dict[str, Any]],
    ) -> Dict[str, float]:
        """Evaluate clustering with inertia and silhouette-like score."""
        state = self._model_state[model_id]
        features = self._models[model_id].features
        centroids = state.get("centroids", [])
        k = len(centroids)

        if k == 0:
            return {"inertia": float("inf"), "silhouette": -1.0}

        vectors = [[float(record.get(f, 0.0)) for f in features] for record in test_data]
        n = len(vectors)
        if n == 0:
            return {"inertia": 0.0, "silhouette": 0.0}

        # Assign to clusters
        assignments = []
        inertia = 0.0
        for vec in vectors:
            best_dist = float("inf")
            best_j = 0
            for j, centroid in enumerate(centroids):
                dist = sum((vec[d] - centroid[d]) ** 2 for d in range(len(features)))
                if dist < best_dist:
                    best_dist = dist
                    best_j = j
            assignments.append(best_j)
            inertia += best_dist

        # Simple silhouette-like score: (b - a) / max(a, b)
        # where a = distance to own centroid, b = distance to nearest other centroid
        silhouette_scores = []
        for i, vec in enumerate(vectors):
            a = math.sqrt(
                sum(
                    (vec[d] - centroids[assignments[i]][d]) ** 2
                    for d in range(len(features))
                )
            )
            b = float("inf")
            for j, centroid in enumerate(centroids):
                if j == assignments[i]:
                    continue
                dist = math.sqrt(
                    sum((vec[d] - centroid[d]) ** 2 for d in range(len(features)))
                )
                if dist < b:
                    b = dist
            if max(a, b) > 0:
                silhouette_scores.append((b - a) / max(a, b))
            else:
                silhouette_scores.append(0.0)

        avg_silhouette = statistics.mean(silhouette_scores) if silhouette_scores else 0.0
        return {
            "inertia": inertia / n if n else 0.0,
            "silhouette": avg_silhouette,
        }

    # ------------------------------------------------------------------
    # Reinforcement: Q-table learning
    # ------------------------------------------------------------------

    def _train_reinforcement(
        self,
        training_data: List[Dict[str, Any]],
        features: List[str],
        state: Dict[str, Any],
        hyperparameters: Dict[str, Any],
    ) -> Tuple[float, float, int]:
        """Q-learning with a tabular Q-function.

        Returns:
            Tuple of (accuracy, loss, epochs). Accuracy is the average
            reward ratio; loss is negative average Q-value change.
        """
        q_table = state["q_table"]
        actions = state["actions"]
        alpha = float(hyperparameters.get("alpha", 0.1))
        gamma = float(hyperparameters.get("gamma", 0.9))
        max_epochs = int(hyperparameters.get("max_epochs", 100))

        epochs = 0
        total_reward = 0.0
        prev_q_sum = sum(sum(q.values()) for q in q_table.values()) if q_table else 0.0

        for epoch in range(max_epochs):
            epoch_reward = 0.0
            for record in training_data:
                state_key = tuple(round(float(record.get(f, 0.0)), 3) for f in features)
                action = str(record.get("action", actions[0]))
                reward = float(record.get("reward", 0.0))
                next_state_key = tuple(
                    round(float(record.get("next_state", {}).get(f, 0.0)), 3)
                    if isinstance(record.get("next_state"), dict)
                    else state_key
                    for f in features
                )

                if state_key not in q_table:
                    q_table[state_key] = {a: 0.0 for a in actions}
                if next_state_key not in q_table:
                    q_table[next_state_key] = {a: 0.0 for a in actions}

                current_q = q_table[state_key][action]
                max_next_q = max(q_table[next_state_key].values())
                new_q = current_q + alpha * (reward + gamma * max_next_q - current_q)
                q_table[state_key][action] = new_q
                epoch_reward += reward

            epochs += 1
            total_reward += epoch_reward

        new_q_sum = sum(sum(q.values()) for q in q_table.values()) if q_table else 0.0
        q_change = abs(new_q_sum - prev_q_sum)

        # Accuracy: normalised average reward per record per epoch
        num_records = len(training_data) if training_data else 1
        avg_reward = total_reward / (epochs * num_records) if epochs else 0.0
        accuracy = (math.tanh(avg_reward) + 1.0) / 2.0
        loss = 1.0 / (1.0 + q_change) if q_change > 0 else 1.0

        return accuracy, loss, epochs

    def _predict_reinforcement(
        self,
        x: Dict[str, float],
        state: Dict[str, Any],
    ) -> Dict[str, float]:
        """Predict best action for a state using Q-table."""
        q_table = state.get("q_table", {})
        actions = state.get("actions", [])
        state_key = tuple(round(v, 3) for v in x.values())

        if state_key not in q_table:
            # Return uniform Q-values for unseen states
            return {
                "best_action": actions[0] if actions else "",
                "q_values": {a: 0.0 for a in actions},
                "exploration": True,
            }

        q_values = q_table[state_key]
        best_action = max(q_values, key=q_values.get)
        return {
            "best_action": best_action,
            "q_values": dict(q_values),
            "exploration": False,
        }

    def _evaluate_reinforcement(
        self,
        model_id: str,
        test_data: List[Dict[str, Any]],
    ) -> Dict[str, float]:
        """Evaluate RL model with policy accuracy and average Q-value."""
        state = self._model_state[model_id]
        features = self._models[model_id].features
        q_table = state.get("q_table", {})
        actions = state.get("actions", [])

        correct = 0
        total_q = 0.0
        count = 0

        for record in test_data:
            state_key = tuple(round(float(record.get(f, 0.0)), 3) for f in features)
            expected_action = str(record.get("action", ""))
            reward = float(record.get("reward", 0.0))

            if state_key in q_table:
                best_action = max(q_table[state_key], key=q_table[state_key].get)
                total_q += sum(q_table[state_key].values()) / len(actions)
                if best_action == expected_action:
                    correct += 1
                count += 1

        accuracy = correct / count if count else 0.0
        avg_q = total_q / count if count else 0.0
        return {"accuracy": accuracy, "average_q": avg_q}

    # ------------------------------------------------------------------
    # Transfer: weighted voting ensemble
    # ------------------------------------------------------------------

    def _train_transfer(
        self,
        training_data: List[Dict[str, Any]],
        features: List[str],
        weights: Dict[str, float],
        state: Dict[str, Any],
        hyperparameters: Dict[str, Any],
    ) -> Tuple[float, float, int]:
        """Transfer learning via weighted ensemble of perceptrons.

        Each source model contributes a perceptron that is fine-tuned on
        the target data. The final prediction uses weighted voting.

        Returns:
            Tuple of (accuracy, loss, epochs).
        """
        source_models = state.get("source_models", [])
        lr = float(hyperparameters.get("learning_rate", 0.01))
        max_epochs = int(hyperparameters.get("max_epochs", 50))

        # Build ensemble: one perceptron per source model (or one default)
        ensemble_size = max(1, len(source_models))
        ensemble_weights = [
            {f: 0.0 for f in features} for _ in range(ensemble_size)
        ]
        ensemble_votes = [1.0 / ensemble_size] * ensemble_size

        epochs = 0
        for epoch in range(max_epochs):
            correct = 0
            total_loss = 0.0
            for record in training_data:
                x = {f: float(record.get(f, 0.0)) for f in features}
                label = int(record.get("label", 0))

                # Weighted vote
                vote_sum = 0.0
                for j in range(ensemble_size):
                    activation = sum(ensemble_weights[j][f] * x[f] for f in features)
                    vote = 1.0 / (1.0 + math.exp(-activation)) if activation != 0 else 0.5
                    vote_sum += ensemble_votes[j] * vote

                prediction = 1 if vote_sum >= 0.5 else 0
                error = label - prediction

                if error == 0:
                    correct += 1
                total_loss += float(error) ** 2

                # Update each perceptron
                for j in range(ensemble_size):
                    for f in features:
                        ensemble_weights[j][f] += lr * error * x[f]

            epochs += 1
            accuracy = correct / len(training_data) if training_data else 0.0
            loss = total_loss / len(training_data) if training_data else 0.0
            if accuracy >= 1.0:
                break

        state["ensemble_weights"] = ensemble_weights
        state["ensemble_votes"] = ensemble_votes

        # Store averaged weights in the main weights dict for inspection
        for f in features:
            weights[f] = statistics.mean(ew[f] for ew in ensemble_weights)

        return accuracy, loss, epochs

    def _predict_transfer(
        self,
        x: Dict[str, float],
        weights: Dict[str, float],
        state: Dict[str, Any],
    ) -> Dict[str, float]:
        """Ensemble prediction via weighted voting."""
        ensemble_weights = state.get("ensemble_weights", [])
        ensemble_votes = state.get("ensemble_votes", [])

        if not ensemble_weights:
            # Fallback to simple perceptron using main weights
            activation = sum(weights[f] * x[f] for f in weights)
            score = 1.0 / (1.0 + math.exp(-activation)) if activation != 0 else 0.5
            return {"vote": score, "confidence": 0.5, "ensemble_size": 0}

        vote_sum = 0.0
        for j, ew in enumerate(ensemble_weights):
            activation = sum(ew[f] * x[f] for f in x)
            vote = 1.0 / (1.0 + math.exp(-activation)) if activation != 0 else 0.5
            vote_sum += ensemble_votes[j] * vote

        # Confidence based on vote dispersion
        individual_votes = []
        for j, ew in enumerate(ensemble_weights):
            activation = sum(ew[f] * x[f] for f in x)
            vote = 1.0 / (1.0 + math.exp(-activation)) if activation != 0 else 0.5
            individual_votes.append(vote)

        dispersion = statistics.stdev(individual_votes) if len(individual_votes) > 1 else 0.0
        confidence = 1.0 - min(1.0, dispersion * 2.0)

        return {
            "vote": vote_sum,
            "confidence": confidence,
            "ensemble_size": len(ensemble_weights),
        }

    def _evaluate_transfer(
        self,
        model_id: str,
        test_data: List[Dict[str, Any]],
    ) -> Dict[str, float]:
        """Evaluate transfer ensemble with accuracy and vote confidence."""
        state = self._model_state[model_id]
        features = self._models[model_id].features
        ensemble_weights = state.get("ensemble_weights", [])
        ensemble_votes = state.get("ensemble_votes", [])

        correct = 0
        confidences = []
        for record in test_data:
            x = {f: float(record.get(f, 0.0)) for f in features}
            label = int(record.get("label", 0))

            vote_sum = 0.0
            individual_votes = []
            for j, ew in enumerate(ensemble_weights):
                activation = sum(ew[f] * x[f] for f in features)
                vote = 1.0 / (1.0 + math.exp(-activation)) if activation != 0 else 0.5
                vote_sum += ensemble_votes[j] * vote
                individual_votes.append(vote)

            prediction = 1 if vote_sum >= 0.5 else 0
            if prediction == label:
                correct += 1

            dispersion = statistics.stdev(individual_votes) if len(individual_votes) > 1 else 0.0
            confidences.append(1.0 - min(1.0, dispersion * 2.0))

        total = len(test_data)
        accuracy = correct / total if total else 0.0
        avg_confidence = statistics.mean(confidences) if confidences else 0.0
        return {"accuracy": accuracy, "average_confidence": avg_confidence}

    # ------------------------------------------------------------------
    # Active: uncertainty sampling
    # ------------------------------------------------------------------

    def _train_active(
        self,
        training_data: List[Dict[str, Any]],
        features: List[str],
        weights: Dict[str, float],
        state: Dict[str, Any],
        hyperparameters: Dict[str, Any],
    ) -> Tuple[float, float, int]:
        """Active learning with uncertainty sampling.

        The model trains on labelled data and maintains an unlabelled pool.
        Records with highest prediction uncertainty are flagged for labelling.

        Returns:
            Tuple of (accuracy, loss, epochs).
        """
        lr = float(hyperparameters.get("learning_rate", 0.01))
        max_epochs = int(hyperparameters.get("max_epochs", 100))
        query_budget = int(hyperparameters.get("query_budget", 10))

        # Separate labelled and unlabelled data
        labelled = [r for r in training_data if "label" in r]
        unlabelled = [r for r in training_data if "label" not in r]
        state["pool"] = unlabelled

        epochs = 0
        for epoch in range(max_epochs):
            correct = 0
            total_loss = 0.0
            for record in labelled:
                x = {f: float(record.get(f, 0.0)) for f in features}
                label = int(record.get("label", 0))

                activation = sum(weights[f] * x[f] for f in features)
                prediction = 1 if activation >= 0 else 0
                error = label - prediction

                if error == 0:
                    correct += 1
                total_loss += float(error) ** 2

                for f in features:
                    weights[f] += lr * error * x[f]

            epochs += 1
            if not labelled:
                break
            accuracy = correct / len(labelled)
            if accuracy >= 1.0:
                break

        # Identify most uncertain unlabelled samples
        uncertainties = []
        for record in unlabelled:
            x = {f: float(record.get(f, 0.0)) for f in features}
            activation = sum(weights[f] * x[f] for f in features)
            score = 1.0 / (1.0 + math.exp(-activation)) if activation != 0 else 0.5
            uncertainty = 1.0 - abs(score - 0.5) * 2.0
            uncertainties.append((record, uncertainty))

        uncertainties.sort(key=lambda x: x[1], reverse=True)
        state["query_candidates"] = [
            {"record": u[0], "uncertainty": u[1]} for u in uncertainties[:query_budget]
        ]

        loss = total_loss / len(labelled) if labelled else float("inf")
        accuracy = correct / len(labelled) if labelled else 0.0
        return accuracy, loss, epochs

    def _predict_active(
        self,
        x: Dict[str, float],
        weights: Dict[str, float],
    ) -> Dict[str, float]:
        """Predict with uncertainty estimate."""
        activation = sum(weights[f] * x[f] for f in weights)
        score = 1.0 / (1.0 + math.exp(-activation)) if activation != 0 else 0.5
        uncertainty = 1.0 - abs(score - 0.5) * 2.0
        label = 1 if activation >= 0 else 0
        return {"score": score, "label": float(label), "uncertainty": uncertainty}

    def _evaluate_active(
        self,
        model_id: str,
        test_data: List[Dict[str, Any]],
    ) -> Dict[str, float]:
        """Evaluate active learner with accuracy and average uncertainty."""
        weights = self._weights[model_id]
        features = self._models[model_id].features
        correct = 0
        uncertainties = []

        for record in test_data:
            x = {f: float(record.get(f, 0.0)) for f in features}
            label = int(record.get("label", 0)) if "label" in record else -1
            activation = sum(weights[f] * x[f] for f in features)
            score = 1.0 / (1.0 + math.exp(-activation)) if activation != 0 else 0.5
            prediction = 1 if activation >= 0 else 0

            if "label" in record and prediction == label:
                correct += 1
            uncertainties.append(1.0 - abs(score - 0.5) * 2.0)

        total = len([r for r in test_data if "label" in r])
        accuracy = correct / total if total else 0.0
        avg_uncertainty = statistics.mean(uncertainties) if uncertainties else 0.0
        return {"accuracy": accuracy, "average_uncertainty": avg_uncertainty}


# ------------------------------------------------------------------------------
# Singleton management with double-checked locking
# ------------------------------------------------------------------------------

_learning_module_instance: Optional[LearningModule] = None
_learning_module_lock: threading.Lock = threading.Lock()


def get_learning_module() -> LearningModule:
    """Return the global LearningModule singleton.

    Uses double-checked locking for efficient, thread-safe initialisation.

    Returns:
        The singleton LearningModule instance.
    """
    global _learning_module_instance
    if _learning_module_instance is None:
        with _learning_module_lock:
            if _learning_module_instance is None:
                _learning_module_instance = LearningModule()
    return _learning_module_instance


def reset_learning_module() -> None:
    """Reset the global singleton instance.

    This is intended primarily for testing scenarios where a fresh module
    with empty state is required.
    """
    global _learning_module_instance
    with _learning_module_lock:
        _learning_module_instance = None
