"""
Decision Engine module for the Agent Reliable Memory System.

This module provides deterministic, multi-criteria decision making capabilities
with no external model dependencies. It supports binary, multi-choice, ranking,
threshold, and probabilistic decision types.

Design Principles:
    1. First Principles: deterministic rules, no model dependencies
    2. Thread-safe using threading.RLock
    3. Global singleton via get_decision_engine() with double-checked locking
    4. Use Python dataclasses for data structures, Enum for types
    5. Minimal dependencies, no circular dependencies
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional


class DecisionType(Enum):
    """Enumeration of supported decision types."""

    BINARY = auto()
    MULTI_CHOICE = auto()
    RANKING = auto()
    THRESHOLD = auto()
    PROBABILISTIC = auto()


class DecisionStatus(Enum):
    """Enumeration of possible decision statuses."""

    PENDING = auto()
    APPROVED = auto()
    REJECTED = auto()
    DEFERRED = auto()


@dataclass
class DecisionCriteria:
    """Represents a single criterion used for decision evaluation.

    Attributes:
        criteria_id: Unique identifier for the criterion.
        name: Human-readable name of the criterion.
        weight: Relative importance weight (should be non-negative).
        threshold: Minimum or maximum acceptable value.
        maximize: If True, higher scores are better; otherwise lower is better.
    """

    criteria_id: str
    name: str
    weight: float
    threshold: float
    maximize: bool = True


@dataclass
class DecisionOption:
    """Represents an option available for a decision.

    Attributes:
        option_id: Unique identifier for the option.
        name: Human-readable name of the option.
        scores: Mapping from criteria_id to raw score value.
        metadata: Optional additional data attached to the option.
    """

    option_id: str
    name: str
    scores: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DecisionResult:
    """Represents the outcome of a decision operation.

    Attributes:
        decision_id: Unique identifier for the decision result.
        decision_type: The type of decision that was made.
        options: List of all options that were considered.
        chosen_option: The selected option, or None if no option was chosen.
        confidence: Confidence score in range [0.0, 1.0].
        status: Final status of the decision.
        reasoning: Human-readable explanation of the decision.
    """

    decision_id: str
    decision_type: DecisionType
    options: List[DecisionOption]
    chosen_option: Optional[DecisionOption]
    confidence: float
    status: DecisionStatus
    reasoning: str


class DecisionEngine:
    """Deterministic decision engine for multi-criteria evaluation.

    Thread-safe via internal RLock. All public methods are reentrant-safe.

    Attributes:
        _criteria: Registered decision criteria indexed by criteria_id.
        _history: Chronological list of past DecisionResult objects.
        _lock: Reentrant lock protecting internal state.
    """

    def __init__(self) -> None:
        """Initialize a new DecisionEngine instance."""
        self._criteria: Dict[str, DecisionCriteria] = {}
        self._history: List[DecisionResult] = []
        self._lock: threading.RLock = threading.RLock()

    # ------------------------------------------------------------------
    # Criteria management
    # ------------------------------------------------------------------

    def add_criteria(
        self,
        name: str,
        weight: float,
        threshold: float,
        maximize: bool = True,
    ) -> str:
        """Register a new decision criterion.

        Args:
            name: Human-readable name for the criterion.
            weight: Importance weight (must be non-negative).
            threshold: Boundary value for acceptability.
            maximize: Whether higher values are preferred.

        Returns:
            The generated unique criteria_id.
        """
        criteria_id = str(uuid.uuid4())
        with self._lock:
            self._criteria[criteria_id] = DecisionCriteria(
                criteria_id=criteria_id,
                name=name,
                weight=max(0.0, float(weight)),
                threshold=float(threshold),
                maximize=bool(maximize),
            )
        return criteria_id

    def remove_criteria(self, criteria_id: str) -> bool:
        """Remove a registered criterion.

        Args:
            criteria_id: The identifier of the criterion to remove.

        Returns:
            True if the criterion existed and was removed, False otherwise.
        """
        with self._lock:
            if criteria_id in self._criteria:
                del self._criteria[criteria_id]
                return True
            return False

    def get_criteria(self) -> List[DecisionCriteria]:
        """Return a snapshot of all registered criteria.

        Returns:
            List of DecisionCriteria objects.
        """
        with self._lock:
            return list(self._criteria.values())

    # ------------------------------------------------------------------
    # Core evaluation
    # ------------------------------------------------------------------

    def evaluate_option(
        self,
        option: DecisionOption,
        criteria_values: Optional[Dict[str, float]] = None,
    ) -> float:
        """Compute a weighted score for a single option.

        If *criteria_values* is provided, it overrides the scores stored in
        *option.scores*.  Missing criteria receive a score of 0.0.  When
        ``maximize`` is False the raw score is inverted relative to the
        threshold so that a higher *result* always means "better".

        Args:
            option: The option to evaluate.
            criteria_values: Optional mapping of criteria_id -> score.

        Returns:
            The computed weighted score (non-negative).
        """
        scores = criteria_values if criteria_values is not None else option.scores
        total_score = 0.0
        total_weight = 0.0

        with self._lock:
            for cid, criterion in self._criteria.items():
                raw = float(scores.get(cid, 0.0))
                weight = criterion.weight
                if not criterion.maximize:
                    # Invert so that lower raw values become higher scores
                    raw = 2 * criterion.threshold - raw
                total_score += raw * weight
                total_weight += weight

        if total_weight == 0.0:
            return 0.0
        return max(0.0, total_score / total_weight)

    # ------------------------------------------------------------------
    # Decision makers
    # ------------------------------------------------------------------

    def make_binary_decision(
        self,
        options: List[DecisionOption],
        criteria_values: Optional[Dict[str, float]] = None,
    ) -> DecisionResult:
        """Make a binary approve/reject decision.

        The option with the highest weighted score is chosen.  If its score
        meets or exceeds the average threshold (weighted by criteria weights)
        the decision is APPROVED, otherwise REJECTED.

        Args:
            options: Exactly two options (binary choice).
            criteria_values: Optional override scores.

        Returns:
            A DecisionResult describing the outcome.
        """
        if len(options) != 2:
            raise ValueError("Binary decision requires exactly two options.")

        scores = [
            (opt, self.evaluate_option(opt, criteria_values)) for opt in options
        ]
        scores.sort(key=lambda x: x[1], reverse=True)
        best_option, best_score = scores[0]

        # Compute weighted average threshold
        with self._lock:
            total_weight = sum(c.weight for c in self._criteria.values())
            weighted_threshold = (
                sum(c.weight * c.threshold for c in self._criteria.values())
                / total_weight
                if total_weight > 0
                else 0.0
            )

        if best_score >= weighted_threshold:
            status = DecisionStatus.APPROVED
            reasoning = (
                f"Option '{best_option.name}' approved with score "
                f"{best_score:.4f} >= threshold {weighted_threshold:.4f}."
            )
        else:
            status = DecisionStatus.REJECTED
            reasoning = (
                f"Option '{best_option.name}' rejected: score "
                f"{best_score:.4f} < threshold {weighted_threshold:.4f}."
            )

        confidence = self._compute_confidence(best_score, scores[1][1])
        result = DecisionResult(
            decision_id=str(uuid.uuid4()),
            decision_type=DecisionType.BINARY,
            options=list(options),
            chosen_option=best_option,
            confidence=confidence,
            status=status,
            reasoning=reasoning,
        )
        with self._lock:
            self._history.append(result)
        return result

    def make_multi_choice_decision(
        self,
        options: List[DecisionOption],
        criteria_values: Optional[Dict[str, float]] = None,
    ) -> DecisionResult:
        """Select the single best option from many.

        Args:
            options: List of candidate options (at least one).
            criteria_values: Optional override scores.

        Returns:
            A DecisionResult with status APPROVED if the best score meets the
            weighted average threshold, otherwise DEFERRED.
        """
        if not options:
            raise ValueError("Multi-choice decision requires at least one option.")

        scores = [
            (opt, self.evaluate_option(opt, criteria_values)) for opt in options
        ]
        scores.sort(key=lambda x: x[1], reverse=True)
        best_option, best_score = scores[0]

        with self._lock:
            total_weight = sum(c.weight for c in self._criteria.values())
            weighted_threshold = (
                sum(c.weight * c.threshold for c in self._criteria.values())
                / total_weight
                if total_weight > 0
                else 0.0
            )

        if best_score >= weighted_threshold:
            status = DecisionStatus.APPROVED
            reasoning = (
                f"Selected '{best_option.name}' with highest score "
                f"{best_score:.4f} among {len(options)} options."
            )
        else:
            status = DecisionStatus.DEFERRED
            reasoning = (
                f"Best option '{best_option.name}' score {best_score:.4f} "
                f"below threshold {weighted_threshold:.4f}; decision deferred."
            )

        runner_up = scores[1][1] if len(scores) > 1 else 0.0
        confidence = self._compute_confidence(best_score, runner_up)
        result = DecisionResult(
            decision_id=str(uuid.uuid4()),
            decision_type=DecisionType.MULTI_CHOICE,
            options=list(options),
            chosen_option=best_option,
            confidence=confidence,
            status=status,
            reasoning=reasoning,
        )
        with self._lock:
            self._history.append(result)
        return result

    def make_ranking_decision(
        self,
        options: List[DecisionOption],
        criteria_values: Optional[Dict[str, float]] = None,
    ) -> DecisionResult:
        """Rank all options by weighted score.

        The ``chosen_option`` of the returned result is the top-ranked option.

        Args:
            options: List of options to rank.
            criteria_values: Optional override scores.

        Returns:
            A DecisionResult with status APPROVED.
        """
        if not options:
            raise ValueError("Ranking decision requires at least one option.")

        scores = [
            (opt, self.evaluate_option(opt, criteria_values)) for opt in options
        ]
        scores.sort(key=lambda x: x[1], reverse=True)
        best_option, best_score = scores[0]

        ranked_names = [f"{i + 1}. {opt.name} ({score:.4f})" for i, (opt, score) in enumerate(scores)]
        reasoning = "Ranking:\n" + "\n".join(ranked_names)

        runner_up = scores[1][1] if len(scores) > 1 else 0.0
        confidence = self._compute_confidence(best_score, runner_up)
        result = DecisionResult(
            decision_id=str(uuid.uuid4()),
            decision_type=DecisionType.RANKING,
            options=[opt for opt, _ in scores],
            chosen_option=best_option,
            confidence=confidence,
            status=DecisionStatus.APPROVED,
            reasoning=reasoning,
        )
        with self._lock:
            self._history.append(result)
        return result

    def make_threshold_decision(
        self,
        options: List[DecisionOption],
        criteria_values: Optional[Dict[str, float]] = None,
    ) -> DecisionResult:
        """Filter options that meet every criterion's threshold.

        An option passes if, for every registered criterion, its (possibly
        inverted) score meets or exceeds the criterion threshold.

        Args:
            options: List of options to evaluate.
            criteria_values: Optional override scores.

        Returns:
            A DecisionResult.  If at least one option passes, the one with the
            highest surplus above thresholds is chosen (APPROVED).  Otherwise
            the result is REJECTED with ``chosen_option`` set to None.
        """
        if not options:
            raise ValueError("Threshold decision requires at least one option.")

        passing: List[tuple[DecisionOption, float]] = []
        with self._lock:
            for opt in options:
                scores = criteria_values if criteria_values is not None else opt.scores
                passes = True
                surplus = 0.0
                for cid, criterion in self._criteria.items():
                    raw = float(scores.get(cid, 0.0))
                    if not criterion.maximize:
                        raw = 2 * criterion.threshold - raw
                    if raw < criterion.threshold:
                        passes = False
                        break
                    surplus += raw - criterion.threshold
                if passes:
                    passing.append((opt, surplus))

        if passing:
            passing.sort(key=lambda x: x[1], reverse=True)
            best_option, best_surplus = passing[0]
            status = DecisionStatus.APPROVED
            reasoning = (
                f"Option '{best_option.name}' passed all thresholds with "
                f"surplus {best_surplus:.4f}."
            )
            confidence = min(1.0, max(0.0, 1.0 - 1.0 / (1.0 + best_surplus)))
        else:
            best_option = None
            status = DecisionStatus.REJECTED
            reasoning = "No option met all registered criteria thresholds."
            confidence = 0.0

        result = DecisionResult(
            decision_id=str(uuid.uuid4()),
            decision_type=DecisionType.THRESHOLD,
            options=list(options),
            chosen_option=best_option,
            confidence=confidence,
            status=status,
            reasoning=reasoning,
        )
        with self._lock:
            self._history.append(result)
        return result

    def make_probabilistic_decision(
        self,
        options: List[DecisionOption],
        probabilities: Dict[str, float],
    ) -> DecisionResult:
        """Make a decision based on supplied probabilities.

        Probabilities are normalised to sum to 1.0.  The option with the
        highest normalised probability is chosen.

        Args:
            options: List of candidate options.
            probabilities: Mapping from option_id to raw probability weight.

        Returns:
            A DecisionResult with status APPROVED.
        """
        if not options:
            raise ValueError("Probabilistic decision requires at least one option.")

        # Normalise probabilities
        total = sum(max(0.0, float(probabilities.get(opt.option_id, 0.0))) for opt in options)
        if total == 0.0:
            # Fallback to uniform distribution
            norm = {opt.option_id: 1.0 / len(options) for opt in options}
        else:
            norm = {
                opt.option_id: max(0.0, float(probabilities.get(opt.option_id, 0.0))) / total
                for opt in options
            }

        scored = [(opt, norm[opt.option_id]) for opt in options]
        scored.sort(key=lambda x: x[1], reverse=True)
        best_option, best_prob = scored[0]

        reasoning = (
            f"Probabilistic selection: '{best_option.name}' with "
            f"normalised probability {best_prob:.4f}."
        )
        runner_up = scored[1][1] if len(scored) > 1 else 0.0
        confidence = self._compute_confidence(best_prob, runner_up)
        result = DecisionResult(
            decision_id=str(uuid.uuid4()),
            decision_type=DecisionType.PROBABILISTIC,
            options=list(options),
            chosen_option=best_option,
            confidence=confidence,
            status=DecisionStatus.APPROVED,
            reasoning=reasoning,
        )
        with self._lock:
            self._history.append(result)
        return result

    # ------------------------------------------------------------------
    # History & statistics
    # ------------------------------------------------------------------

    def get_decision_history(self) -> List[DecisionResult]:
        """Return a copy of the full decision history.

        Returns:
            List of DecisionResult objects in chronological order.
        """
        with self._lock:
            return list(self._history)

    def get_decision(self, decision_id: str) -> Optional[DecisionResult]:
        """Retrieve a specific decision from history.

        Args:
            decision_id: The unique identifier of the decision.

        Returns:
            The matching DecisionResult, or None if not found.
        """
        with self._lock:
            for result in self._history:
                if result.decision_id == decision_id:
                    return result
            return None

    def clear_history(self) -> int:
        """Erase all stored decision history.

        Returns:
            Number of records that were removed.
        """
        with self._lock:
            count = len(self._history)
            self._history.clear()
            return count

    def get_statistics(self) -> Dict[str, Any]:
        """Compute summary statistics over the decision history.

        Returns:
            Dictionary containing counts, averages, and breakdowns by type
            and status.
        """
        with self._lock:
            total = len(self._history)
            if total == 0:
                return {
                    "total_decisions": 0,
                    "by_type": {},
                    "by_status": {},
                    "average_confidence": 0.0,
                    "approval_rate": 0.0,
                }

            by_type: Dict[str, int] = {}
            by_status: Dict[str, int] = {}
            conf_sum = 0.0
            approved = 0

            for result in self._history:
                t = result.decision_type.name
                s = result.status.name
                by_type[t] = by_type.get(t, 0) + 1
                by_status[s] = by_status.get(s, 0) + 1
                conf_sum += result.confidence
                if result.status == DecisionStatus.APPROVED:
                    approved += 1

            return {
                "total_decisions": total,
                "by_type": by_type,
                "by_status": by_status,
                "average_confidence": conf_sum / total,
                "approval_rate": approved / total,
            }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_confidence(best: float, runner_up: float) -> float:
        """Compute a confidence score in [0.0, 1.0] from top two scores.

        The margin between best and runner-up is normalised using a soft
        sigmoid-like transform so that large margins yield confidence near 1.0.

        Args:
            best: Score of the winning option.
            runner_up: Score of the second-best option.

        Returns:
            Confidence value clamped to [0.0, 1.0].
        """
        margin = best - runner_up
        # Use a smooth saturating function: tanh(margin) maps R -> (-1, 1)
        import math

        confidence = (math.tanh(margin) + 1.0) / 2.0
        return float(confidence)


# ------------------------------------------------------------------------------
# Singleton management with double-checked locking
# ------------------------------------------------------------------------------

_decision_engine_instance: Optional[DecisionEngine] = None
_decision_engine_lock: threading.Lock = threading.Lock()


def get_decision_engine() -> DecisionEngine:
    """Return the global DecisionEngine singleton.

    Uses double-checked locking for efficient, thread-safe initialisation.

    Returns:
        The singleton DecisionEngine instance.
    """
    global _decision_engine_instance
    if _decision_engine_instance is None:
        with _decision_engine_lock:
            if _decision_engine_instance is None:
                _decision_engine_instance = DecisionEngine()
    return _decision_engine_instance


def reset_decision_engine() -> None:
    """Reset the global singleton instance.

    This is intended primarily for testing scenarios where a fresh engine
    with empty state is required.
    """
    global _decision_engine_instance
    with _decision_engine_lock:
        _decision_engine_instance = None
