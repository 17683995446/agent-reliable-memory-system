"""
Data Transformer module for the Agent Reliable Memory System (Stage 387).

Design Principles:
1. First Principles: deterministic rules, no model dependencies.
2. Thread-safe using threading.RLock.
3. Global singleton via get_data_transformer() with double-checked locking.
4. Use Python dataclasses for data structures, Enum for types.
5. Minimal dependencies, no circular dependencies.
"""

from __future__ import annotations

import copy
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional


class TransformType(Enum):
    """Supported transformation types."""

    FILTER = auto()
    MAP = auto()
    REDUCE = auto()
    AGGREGATE = auto()
    SORT = auto()
    JOIN = auto()
    SPLIT = auto()
    ENRICH = auto()


@dataclass
class TransformRule:
    """A single transformation rule."""

    rule_id: str
    transform_type: TransformType
    condition: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    enabled: bool = True


@dataclass
class TransformResult:
    """Result of applying a transformation or pipeline."""

    success: bool
    data: Any = None
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class DataTransformer:
    """Thread-safe data transformer with rule and pipeline management."""

    def __init__(self) -> None:
        self._rules: Dict[str, TransformRule] = {}
        self._pipelines: Dict[str, List[str]] = {}
        self._lock = threading.RLock()
        self._stats: Dict[str, Any] = {
            "transform_count": 0,
            "pipeline_count": 0,
            "error_count": 0,
            "start_time": time.time(),
        }

    # ------------------------------------------------------------------
    # Rule management
    # ------------------------------------------------------------------

    def add_rule(self, rule: TransformRule) -> bool:
        """Register a new rule. Returns True on success."""
        with self._lock:
            if rule.rule_id in self._rules:
                return False
            self._rules[rule.rule_id] = rule
            return True

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a rule by ID. Returns True if removed."""
        with self._lock:
            if rule_id not in self._rules:
                return False
            del self._rules[rule_id]
            # Clean up pipelines referencing this rule
            for pname, rids in self._pipelines.items():
                if rule_id in rids:
                    self._pipelines[pname] = [r for r in rids if r != rule_id]
            return True

    def get_rule(self, rule_id: str) -> Optional[TransformRule]:
        """Retrieve a rule by ID."""
        with self._lock:
            return copy.deepcopy(self._rules.get(rule_id))

    def enable_rule(self, rule_id: str) -> bool:
        """Enable a rule."""
        with self._lock:
            rule = self._rules.get(rule_id)
            if rule is None:
                return False
            rule.enabled = True
            return True

    def disable_rule(self, rule_id: str) -> bool:
        """Disable a rule."""
        with self._lock:
            rule = self._rules.get(rule_id)
            if rule is None:
                return False
            rule.enabled = False
            return True

    # ------------------------------------------------------------------
    # Pipeline management
    # ------------------------------------------------------------------

    def create_pipeline(self, name: str, rule_ids: List[str]) -> bool:
        """Create a named pipeline from an ordered list of rule IDs."""
        with self._lock:
            if name in self._pipelines:
                return False
            # Validate that all rules exist
            for rid in rule_ids:
                if rid not in self._rules:
                    return False
            self._pipelines[name] = list(rule_ids)
            return True

    def delete_pipeline(self, name: str) -> bool:
        """Delete a pipeline by name."""
        with self._lock:
            if name not in self._pipelines:
                return False
            del self._pipelines[name]
            return True

    def get_pipelines(self) -> List[str]:
        """Return a list of all pipeline names."""
        with self._lock:
            return list(self._pipelines.keys())

    # ------------------------------------------------------------------
    # Transformation execution
    # ------------------------------------------------------------------

    def apply_transform(self, data: Any, rule_id: str) -> TransformResult:
        """Apply a single rule to data and return the result."""
        with self._lock:
            rule = self._rules.get(rule_id)
            if rule is None:
                self._stats["error_count"] += 1
                return TransformResult(
                    success=False,
                    errors=[f"Rule '{rule_id}' not found."],
                )
            if not rule.enabled:
                self._stats["error_count"] += 1
                return TransformResult(
                    success=False,
                    errors=[f"Rule '{rule_id}' is disabled."],
                )

        # Execute outside the lock to avoid holding it during long transforms
        try:
            result_data = self._execute_transform(data, rule)
            with self._lock:
                self._stats["transform_count"] += 1
            return TransformResult(
                success=True,
                data=result_data,
                metadata={"rule_id": rule_id, "type": rule.transform_type.name},
            )
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._stats["error_count"] += 1
            return TransformResult(
                success=False,
                data=data,
                errors=[str(exc)],
                metadata={"rule_id": rule_id, "type": rule.transform_type.name},
            )

    def apply_pipeline(self, data: Any, pipeline_name: str) -> TransformResult:
        """Execute a pipeline sequentially on the data."""
        with self._lock:
            rule_ids = self._pipelines.get(pipeline_name)
            if rule_ids is None:
                self._stats["error_count"] += 1
                return TransformResult(
                    success=False,
                    errors=[f"Pipeline '{pipeline_name}' not found."],
                )

        current_data = data
        all_errors: List[str] = []
        applied_rules: List[str] = []

        for rid in rule_ids:
            result = self.apply_transform(current_data, rid)
            applied_rules.append(rid)
            if not result.success:
                all_errors.extend(result.errors)
                return TransformResult(
                    success=False,
                    data=current_data,
                    errors=all_errors,
                    metadata={
                        "pipeline": pipeline_name,
                        "applied_rules": applied_rules,
                    },
                )
            current_data = result.data

        with self._lock:
            self._stats["pipeline_count"] += 1

        return TransformResult(
            success=True,
            data=current_data,
            metadata={
                "pipeline": pipeline_name,
                "applied_rules": applied_rules,
            },
        )

    # ------------------------------------------------------------------
    # Built-in transform implementations
    # ------------------------------------------------------------------

    def _execute_transform(self, data: Any, rule: TransformRule) -> Any:
        """Dispatch to the correct built-in transform handler."""
        handler: Dict[TransformType, Callable[[Any, TransformRule], Any]] = {
            TransformType.FILTER: self._transform_filter,
            TransformType.MAP: self._transform_map,
            TransformType.REDUCE: self._transform_reduce,
            TransformType.AGGREGATE: self._transform_aggregate,
            TransformType.SORT: self._transform_sort,
            TransformType.JOIN: self._transform_join,
            TransformType.SPLIT: self._transform_split,
            TransformType.ENRICH: self._transform_enrich,
        }
        func = handler.get(rule.transform_type)
        if func is None:
            raise ValueError(f"Unsupported transform type: {rule.transform_type}")
        return func(data, rule)

    @staticmethod
    def _transform_filter(data: Any, rule: TransformRule) -> Any:
        """Filter records by evaluating condition as a lambda string."""
        if not isinstance(data, list):
            raise TypeError("FILTER expects a list of records.")
        condition = rule.condition
        if condition is None or condition == "":
            return data
        # condition is expected to be a string like "lambda x: x['age'] > 18"
        func = eval(condition)  # noqa: S307
        return [record for record in data if func(record)]

    @staticmethod
    def _transform_map(data: Any, rule: TransformRule) -> Any:
        """Transform each record using a lambda string or expression."""
        if not isinstance(data, list):
            raise TypeError("MAP expects a list of records.")
        func_str = rule.params.get("func")
        if func_str is None:
            # Try expression like "x * 2"
            expr = rule.params.get("expression")
            if expr is None:
                return data
            func = eval(f"lambda x: {expr}")  # noqa: S307
            return [func(record) for record in data]
        func = eval(func_str)  # noqa: S307
        return [func(record) for record in data]

    @staticmethod
    def _transform_reduce(data: Any, rule: TransformRule) -> Any:
        """Aggregate a list to a single value."""
        if not isinstance(data, list):
            raise TypeError("REDUCE expects a list of records.")
        func_str = rule.params.get("func")
        initial = rule.params.get("initial")
        if func_str is None:
            return data
        func = eval(func_str)  # noqa: S307
        import functools

        if initial is not None:
            return functools.reduce(func, data, initial)
        return functools.reduce(func, data)

    @staticmethod
    def _transform_aggregate(data: Any, rule: TransformRule) -> Any:
        """Group records by a key and apply an aggregation function."""
        if not isinstance(data, list):
            raise TypeError("AGGREGATE expects a list of records.")
        key_func_str = rule.params.get("key_func")
        agg_func_str = rule.params.get("agg_func")
        if key_func_str is None or agg_func_str is None:
            return data
        key_func = eval(key_func_str)  # noqa: S307
        agg_func = eval(agg_func_str)  # noqa: S307
        groups: Dict[Any, List[Any]] = {}
        for record in data:
            k = key_func(record)
            groups.setdefault(k, []).append(record)
        return {k: agg_func(v) for k, v in groups.items()}

    @staticmethod
    def _transform_sort(data: Any, rule: TransformRule) -> Any:
        """Sort records by a key function."""
        if not isinstance(data, list):
            raise TypeError("SORT expects a list of records.")
        key_func_str = rule.params.get("key_func")
        reverse = rule.params.get("reverse", False)
        if key_func_str is None:
            return sorted(data, reverse=reverse)
        key_func = eval(key_func_str)  # noqa: S307
        return sorted(data, key=key_func, reverse=reverse)

    @staticmethod
    def _transform_join(data: Any, rule: TransformRule) -> Any:
        """Join two datasets on a common key."""
        if (
            not isinstance(data, dict)
            or "left" not in data
            or "right" not in data
        ):
            raise TypeError(
                "JOIN expects data as {'left': [...], 'right': [...]}."
            )
        left = data["left"]
        right = data["right"]
        left_key_str = rule.params.get("left_key")
        right_key_str = rule.params.get("right_key")
        join_type = rule.params.get("join_type", "inner")
        if left_key_str is None or right_key_str is None:
            raise ValueError("JOIN requires 'left_key' and 'right_key' params.")
        left_key = eval(left_key_str)  # noqa: S307
        right_key = eval(right_key_str)  # noqa: S307

        right_index: Dict[Any, List[Any]] = {}
        for r in right:
            k = right_key(r)
            right_index.setdefault(k, []).append(r)

        result: List[Dict[str, Any]] = []
        for lrec in left:
            lk = left_key(lrec)
            matches = right_index.get(lk, [])
            if matches:
                for rrec in matches:
                    merged = copy.deepcopy(lrec)
                    if isinstance(rrec, dict):
                        merged.update(rrec)
                    else:
                        merged["__right__"] = rrec
                    result.append(merged)
            elif join_type in ("left", "outer"):
                result.append(copy.deepcopy(lrec))

        if join_type in ("right", "outer"):
            matched_left_keys = {left_key(lrec) for lrec in left}
            for rrec in right:
                rk = right_key(rrec)
                if rk not in matched_left_keys:
                    result.append(copy.deepcopy(rrec))

        return result

    @staticmethod
    def _transform_split(data: Any, rule: TransformRule) -> Any:
        """Split a dataset into multiple datasets by a condition."""
        if not isinstance(data, list):
            raise TypeError("SPLIT expects a list of records.")
        condition_str = rule.params.get("condition")
        if condition_str is None:
            return {"match": data, "no_match": []}
        condition = eval(condition_str)  # noqa: S307
        match = [r for r in data if condition(r)]
        no_match = [r for r in data if not condition(r)]
        return {"match": match, "no_match": no_match}

    @staticmethod
    def _transform_enrich(data: Any, rule: TransformRule) -> Any:
        """Add computed fields to each record."""
        if not isinstance(data, list):
            raise TypeError("ENRICH expects a list of records.")
        fields = rule.params.get("fields", {})
        result = []
        for record in data:
            new_rec = copy.deepcopy(record)
            if not isinstance(new_rec, dict):
                new_rec = {"__value__": new_rec}
            for fname, fexpr in fields.items():
                new_rec[fname] = eval(fexpr, {"__builtins__": {}}, {"r": record})  # noqa: S307
            result.append(new_rec)
        return result

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def get_statistics(self) -> Dict[str, Any]:
        """Return operational statistics."""
        with self._lock:
            stats = copy.deepcopy(self._stats)
            stats["rule_count"] = len(self._rules)
            stats["pipeline_count_registered"] = len(self._pipelines)
            stats["uptime"] = time.time() - stats["start_time"]
            return stats


# ----------------------------------------------------------------------
# Singleton management with double-checked locking
# ----------------------------------------------------------------------

_singleton_instance: Optional[DataTransformer] = None
_singleton_lock = threading.Lock()


def get_data_transformer() -> DataTransformer:
    """Return the global DataTransformer singleton (thread-safe)."""
    global _singleton_instance  # noqa: PLW0603
    if _singleton_instance is None:
        with _singleton_lock:
            if _singleton_instance is None:
                _singleton_instance = DataTransformer()
    return _singleton_instance


def reset_data_transformer() -> None:
    """Reset the singleton instance (intended for testing)."""
    global _singleton_instance  # noqa: PLW0603
    with _singleton_lock:
        _singleton_instance = None
