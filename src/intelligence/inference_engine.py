"""
Inference Engine module for the Agent Reliable Memory System.

This module provides deterministic logical inference capabilities with no external
model dependencies. It supports deductive, inductive, abductive, analogical, and
causal inference types.

Design Principles:
    1. First Principles: deterministic rules, no model dependencies
    2. Thread-safe using threading.RLock
    3. Global singleton via get_inference_engine() with double-checked locking
    4. Use Python dataclasses for data structures, Enum for types
    5. Minimal dependencies, no circular dependencies
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional


class InferenceType(Enum):
    """Enumeration of supported inference types."""

    DEDUCTION = auto()
    INDUCTION = auto()
    ABDUCTION = auto()
    ANALOGY = auto()
    CAUSAL = auto()


class InferenceStatus(Enum):
    """Enumeration of possible inference statuses."""

    PENDING = auto()
    VALID = auto()
    INVALID = auto()
    INCONCLUSIVE = auto()


@dataclass
class Fact:
    """Represents a known fact in the knowledge base.

    Attributes:
        fact_id: Unique identifier for the fact.
        statement: Human-readable statement of the fact.
        confidence: Confidence score in range [0.0, 1.0].
        source: Origin or source of the fact.
        timestamp: Unix timestamp when the fact was recorded.
    """

    fact_id: str
    statement: str
    confidence: float
    source: str
    timestamp: float


@dataclass
class Rule:
    """Represents a logical rule for inference.

    Attributes:
        rule_id: Unique identifier for the rule.
        premise: The antecedent / condition of the rule.
        conclusion: The consequent / result of the rule.
        confidence: Confidence score in range [0.0, 1.0].
        rule_type: Classification or category of the rule.
    """

    rule_id: str
    premise: str
    conclusion: str
    confidence: float
    rule_type: str


@dataclass
class InferenceResult:
    """Represents the outcome of an inference operation.

    Attributes:
        result_id: Unique identifier for the inference result.
        inference_type: The type of inference that was performed.
        premises: List of premise fact IDs or statements used.
        conclusion: The derived conclusion statement.
        confidence: Confidence score in range [0.0, 1.0].
        status: Final status of the inference.
        reasoning_chain: Human-readable explanation of the reasoning steps.
    """

    result_id: str
    inference_type: InferenceType
    premises: List[str]
    conclusion: str
    confidence: float
    status: InferenceStatus
    reasoning_chain: str


class InferenceEngine:
    """Deterministic inference engine for logical reasoning.

    Thread-safe via internal RLock. All public methods are reentrant-safe.

    Attributes:
        _facts: Registered facts indexed by fact_id.
        _rules: Registered rules indexed by rule_id.
        _inferences: Recorded inference results indexed by result_id.
        _lock: Reentrant lock protecting internal state.
    """

    def __init__(self) -> None:
        """Initialize a new InferenceEngine instance."""
        self._facts: Dict[str, Fact] = {}
        self._rules: Dict[str, Rule] = {}
        self._inferences: Dict[str, InferenceResult] = {}
        self._lock: threading.RLock = threading.RLock()

    # ------------------------------------------------------------------
    # Fact management
    # ------------------------------------------------------------------

    def add_fact(
        self,
        statement: str,
        confidence: float = 1.0,
        source: str = "",
    ) -> str:
        """Register a new fact.

        Args:
            statement: Human-readable statement of the fact.
            confidence: Confidence score (clamped to [0.0, 1.0]).
            source: Origin or source of the fact.

        Returns:
            The generated unique fact_id.
        """
        fact_id = str(uuid.uuid4())
        with self._lock:
            self._facts[fact_id] = Fact(
                fact_id=fact_id,
                statement=str(statement),
                confidence=max(0.0, min(1.0, float(confidence))),
                source=str(source),
                timestamp=time.time(),
            )
        return fact_id

    def get_facts(self) -> List[Fact]:
        """Return a snapshot of all registered facts.

        Returns:
            List of Fact objects.
        """
        with self._lock:
            return list(self._facts.values())

    # ------------------------------------------------------------------
    # Rule management
    # ------------------------------------------------------------------

    def add_rule(
        self,
        premise: str,
        conclusion: str,
        confidence: float = 1.0,
    ) -> str:
        """Register a new logical rule.

        Args:
            premise: The antecedent / condition of the rule.
            conclusion: The consequent / result of the rule.
            confidence: Confidence score (clamped to [0.0, 1.0]).

        Returns:
            The generated unique rule_id.
        """
        rule_id = str(uuid.uuid4())
        with self._lock:
            self._rules[rule_id] = Rule(
                rule_id=rule_id,
                premise=str(premise),
                conclusion=str(conclusion),
                confidence=max(0.0, min(1.0, float(confidence))),
                rule_type="conditional",
            )
        return rule_id

    def get_rules(self) -> List[Rule]:
        """Return a snapshot of all registered rules.

        Returns:
            List of Rule objects.
        """
        with self._lock:
            return list(self._rules.values())

    # ------------------------------------------------------------------
    # Core inference operations
    # ------------------------------------------------------------------

    def deduct(
        self,
        fact_ids: List[str],
        rule_id: str,
    ) -> InferenceResult:
        """Perform deductive inference: If A then B, A is true, therefore B.

        Args:
            fact_ids: List of fact IDs representing known truths.
            rule_id: The rule ID to apply.

        Returns:
            InferenceResult containing the derived conclusion.
        """
        result_id = str(uuid.uuid4())
        with self._lock:
            rule = self._rules.get(rule_id)
            if rule is None:
                return InferenceResult(
                    result_id=result_id,
                    inference_type=InferenceType.DEDUCTION,
                    premises=fact_ids,
                    conclusion="",
                    confidence=0.0,
                    status=InferenceStatus.INVALID,
                    reasoning_chain=f"Rule {rule_id} not found.",
                )

            matched_facts = []
            for fid in fact_ids:
                fact = self._facts.get(fid)
                if fact is not None:
                    matched_facts.append(fact)

            # Check whether any fact matches the rule premise
            premise_matched = any(
                rule.premise.lower() in f.statement.lower()
                or f.statement.lower() in rule.premise.lower()
                for f in matched_facts
            )

            if premise_matched:
                confidence = min(
                    rule.confidence,
                    min((f.confidence for f in matched_facts), default=1.0),
                )
                reasoning = (
                    f"Deductive step: premise '{rule.premise}' satisfied by "
                    f"provided facts. Applying rule {rule_id} yields conclusion "
                    f"'{rule.conclusion}' with confidence {confidence:.4f}."
                )
                result = InferenceResult(
                    result_id=result_id,
                    inference_type=InferenceType.DEDUCTION,
                    premises=fact_ids,
                    conclusion=rule.conclusion,
                    confidence=confidence,
                    status=InferenceStatus.VALID,
                    reasoning_chain=reasoning,
                )
            else:
                reasoning = (
                    f"Deductive step failed: no provided fact matches premise "
                    f"'{rule.premise}'."
                )
                result = InferenceResult(
                    result_id=result_id,
                    inference_type=InferenceType.DEDUCTION,
                    premises=fact_ids,
                    conclusion="",
                    confidence=0.0,
                    status=InferenceStatus.INVALID,
                    reasoning_chain=reasoning,
                )

            self._inferences[result_id] = result
            return result

    def induct(self, fact_ids: List[str]) -> InferenceResult:
        """Perform inductive inference: generalize from specific facts.

        A1, A2, A3 are true, therefore all A are true.

        Args:
            fact_ids: List of fact IDs representing specific observations.

        Returns:
            InferenceResult containing the generalized conclusion.
        """
        result_id = str(uuid.uuid4())
        with self._lock:
            facts = []
            for fid in fact_ids:
                fact = self._facts.get(fid)
                if fact is not None:
                    facts.append(fact)

            if len(facts) < 2:
                reasoning = (
                    "Inductive generalization requires at least 2 facts; "
                    f"only {len(facts)} provided."
                )
                result = InferenceResult(
                    result_id=result_id,
                    inference_type=InferenceType.INDUCTION,
                    premises=fact_ids,
                    conclusion="",
                    confidence=0.0,
                    status=InferenceStatus.INCONCLUSIVE,
                    reasoning_chain=reasoning,
                )
                self._inferences[result_id] = result
                return result

            # Simple deterministic generalization: extract common prefix words
            statements = [f.statement for f in facts]
            common_prefix = self._longest_common_prefix(statements)
            if common_prefix:
                generalized = common_prefix.rstrip() + " in general"
            else:
                generalized = "Observed pattern holds in general"

            confidence = min(f.confidence for f in facts) * min(1.0, len(facts) / 10.0)
            reasoning = (
                f"Inductive generalization from {len(facts)} facts. "
                f"Common pattern: '{common_prefix}'. Generalized conclusion: "
                f"'{generalized}' with confidence {confidence:.4f}."
            )
            result = InferenceResult(
                result_id=result_id,
                inference_type=InferenceType.INDUCTION,
                premises=fact_ids,
                conclusion=generalized,
                confidence=confidence,
                status=InferenceStatus.VALID,
                reasoning_chain=reasoning,
            )
            self._inferences[result_id] = result
            return result

    def abduce(
        self,
        observation: str,
        possible_causes: List[str],
    ) -> InferenceResult:
        """Perform abductive inference: find the best explanation.

        B is true, if A then B, therefore A is likely.

        Args:
            observation: The observed effect or phenomenon.
            possible_causes: List of candidate cause statements.

        Returns:
            InferenceResult containing the most probable cause.
        """
        result_id = str(uuid.uuid4())
        with self._lock:
            if not possible_causes:
                result = InferenceResult(
                    result_id=result_id,
                    inference_type=InferenceType.ABDUCTION,
                    premises=[observation],
                    conclusion="",
                    confidence=0.0,
                    status=InferenceStatus.INCONCLUSIVE,
                    reasoning_chain="No possible causes provided for abduction.",
                )
                self._inferences[result_id] = result
                return result

            # Deterministic selection: choose the cause with highest lexical overlap
            best_cause = possible_causes[0]
            best_score = 0.0
            obs_words = set(observation.lower().split())

            for cause in possible_causes:
                cause_words = set(cause.lower().split())
                if not cause_words:
                    continue
                overlap = len(obs_words & cause_words) / len(cause_words)
                if overlap > best_score:
                    best_score = overlap
                    best_cause = cause

            confidence = min(1.0, best_score + 0.3)
            status = InferenceStatus.VALID if confidence > 0.5 else InferenceStatus.INCONCLUSIVE
            reasoning = (
                f"Abductive inference: observation '{observation}'. "
                f"Evaluated {len(possible_causes)} possible causes. Best match: "
                f"'{best_cause}' with overlap score {best_score:.4f}."
            )
            result = InferenceResult(
                result_id=result_id,
                inference_type=InferenceType.ABDUCTION,
                premises=[observation],
                conclusion=best_cause,
                confidence=confidence,
                status=status,
                reasoning_chain=reasoning,
            )
            self._inferences[result_id] = result
            return result

    def analogize(
        self,
        source_fact_id: str,
        target_domain: str,
    ) -> InferenceResult:
        """Perform analogical inference: map knowledge from source to target.

        Args:
            source_fact_id: The fact ID in the source domain.
            target_domain: The target domain to map the fact into.

        Returns:
            InferenceResult containing the analogical conclusion.
        """
        result_id = str(uuid.uuid4())
        with self._lock:
            source_fact = self._facts.get(source_fact_id)
            if source_fact is None:
                result = InferenceResult(
                    result_id=result_id,
                    inference_type=InferenceType.ANALOGY,
                    premises=[source_fact_id],
                    conclusion="",
                    confidence=0.0,
                    status=InferenceStatus.INVALID,
                    reasoning_chain=f"Source fact {source_fact_id} not found.",
                )
                self._inferences[result_id] = result
                return result

            conclusion = (
                f"In {target_domain}, an analogous situation to "
                f"'{source_fact.statement}' may hold"
            )
            confidence = source_fact.confidence * 0.8
            reasoning = (
                f"Analogical mapping: source fact '{source_fact.statement}' "
                f"mapped to target domain '{target_domain}'. Conclusion: "
                f"'{conclusion}' with confidence {confidence:.4f}."
            )
            result = InferenceResult(
                result_id=result_id,
                inference_type=InferenceType.ANALOGY,
                premises=[source_fact_id],
                conclusion=conclusion,
                confidence=confidence,
                status=InferenceStatus.VALID,
                reasoning_chain=reasoning,
            )
            self._inferences[result_id] = result
            return result

    def causal_inference(
        self,
        cause_id: str,
        effect_id: str,
    ) -> InferenceResult:
        """Perform causal inference: assess causal link between two facts.

        Args:
            cause_id: The fact ID of the proposed cause.
            effect_id: The fact ID of the proposed effect.

        Returns:
            InferenceResult containing the causal assessment.
        """
        result_id = str(uuid.uuid4())
        with self._lock:
            cause_fact = self._facts.get(cause_id)
            effect_fact = self._facts.get(effect_id)

            if cause_fact is None or effect_fact is None:
                missing = []
                if cause_fact is None:
                    missing.append(cause_id)
                if effect_fact is None:
                    missing.append(effect_id)
                result = InferenceResult(
                    result_id=result_id,
                    inference_type=InferenceType.CAUSAL,
                    premises=[cause_id, effect_id],
                    conclusion="",
                    confidence=0.0,
                    status=InferenceStatus.INVALID,
                    reasoning_chain=f"Missing fact(s): {', '.join(missing)}.",
                )
                self._inferences[result_id] = result
                return result

            # Deterministic causal assessment based on lexical overlap
            cause_words = set(cause_fact.statement.lower().split())
            effect_words = set(effect_fact.statement.lower().split())
            if cause_words:
                overlap = len(cause_words & effect_words) / len(cause_words)
            else:
                overlap = 0.0

            confidence = min(1.0, overlap + 0.2) * min(
                cause_fact.confidence, effect_fact.confidence
            )
            status = InferenceStatus.VALID if confidence > 0.5 else InferenceStatus.INCONCLUSIVE
            conclusion = (
                f"'{cause_fact.statement}' may cause '{effect_fact.statement}'"
            )
            reasoning = (
                f"Causal inference: proposed cause '{cause_fact.statement}' and "
                f"effect '{effect_fact.statement}'. Lexical overlap: {overlap:.4f}. "
                f"Derived causal link confidence: {confidence:.4f}."
            )
            result = InferenceResult(
                result_id=result_id,
                inference_type=InferenceType.CAUSAL,
                premises=[cause_id, effect_id],
                conclusion=conclusion,
                confidence=confidence,
                status=status,
                reasoning_chain=reasoning,
            )
            self._inferences[result_id] = result
            return result

    # ------------------------------------------------------------------
    # Validation and queries
    # ------------------------------------------------------------------

    def validate_inference(self, inference_id: str) -> InferenceStatus:
        """Validate an existing inference by its ID.

        Args:
            inference_id: The identifier of the inference to validate.

        Returns:
            The current InferenceStatus, or INCONCLUSIVE if not found.
        """
        with self._lock:
            inference = self._inferences.get(inference_id)
            if inference is None:
                return InferenceStatus.INCONCLUSIVE
            return inference.status

    def get_inference(self, inference_id: str) -> Optional[InferenceResult]:
        """Retrieve a specific inference result.

        Args:
            inference_id: The identifier of the inference.

        Returns:
            The InferenceResult if found, otherwise None.
        """
        with self._lock:
            return self._inferences.get(inference_id)

    def get_all_inferences(self) -> List[InferenceResult]:
        """Return a snapshot of all recorded inferences.

        Returns:
            List of InferenceResult objects.
        """
        with self._lock:
            return list(self._inferences.values())

    def clear(self) -> None:
        """Clear all facts, rules, and inferences."""
        with self._lock:
            self._facts.clear()
            self._rules.clear()
            self._inferences.clear()

    def get_statistics(self) -> Dict:
        """Return current engine statistics.

        Returns:
            Dictionary with counts of facts, rules, and inferences.
        """
        with self._lock:
            return {
                "fact_count": len(self._facts),
                "rule_count": len(self._rules),
                "inference_count": len(self._inferences),
            }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _longest_common_prefix(strings: List[str]) -> str:
        """Return the longest common prefix of a list of strings.

        Args:
            strings: Non-empty list of strings.

        Returns:
            The longest common prefix (may be empty).
        """
        if not strings:
            return ""
        prefix = strings[0]
        for s in strings[1:]:
            while not s.startswith(prefix):
                prefix = prefix[:-1]
                if not prefix:
                    return ""
        return prefix


# ----------------------------------------------------------------------
# Singleton management
# ----------------------------------------------------------------------

_inference_engine_instance: Optional[InferenceEngine] = None
_inference_engine_lock = threading.Lock()


def get_inference_engine() -> InferenceEngine:
    """Return the global InferenceEngine singleton.

    Uses double-checked locking for thread-safe lazy initialization.

    Returns:
        The shared InferenceEngine instance.
    """
    global _inference_engine_instance
    if _inference_engine_instance is None:
        with _inference_engine_lock:
            if _inference_engine_instance is None:
                _inference_engine_instance = InferenceEngine()
    return _inference_engine_instance


def reset_inference_engine() -> None:
    """Reset the global singleton instance (primarily for testing).

    After calling this function, the next call to get_inference_engine()
    will create a fresh InferenceEngine instance.
    """
    global _inference_engine_instance
    with _inference_engine_lock:
        _inference_engine_instance = None
