"""
Inference Server module for the Agent Reliable Memory System.

Stage 404: ML Integration - Inference Server

Design Principles:
1. First Principles: deterministic rules, no model dependencies
2. Thread-safe using threading.RLock
3. Global singleton via get_inference_server() with double-checked locking
4. Use Python dataclasses for data structures, Enum for types
5. Minimal dependencies, no circular dependencies
"""

import time
import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class InferenceStatus(Enum):
    """Status of a model or inference operation."""
    READY = "ready"
    LOADING = "loading"
    PROCESSING = "processing"
    ERROR = "error"
    UNLOADED = "unloaded"


class BatchStrategy(Enum):
    """Strategy for batching inference requests."""
    SINGLE = "single"
    DYNAMIC = "dynamic"
    FIXED = "fixed"


@dataclass
class InferenceRequest:
    """Represents an inference request."""
    request_id: str
    model_id: str
    input_data: Any
    batch_size: int = 1
    priority: int = 0
    timestamp: float = field(default_factory=time.time)


@dataclass
class InferenceResponse:
    """Represents an inference response."""
    response_id: str
    request_id: str
    model_id: str
    output_data: Any
    latency_ms: float
    status: InferenceStatus
    error: Optional[str] = None


class InferenceServer:
    """
    Thread-safe inference server with simulated model loading,
    prediction, batch processing, and performance metrics.
    """

    def __init__(self) -> None:
        self._models: Dict[str, Dict[str, Any]] = {}
        self._requests: Dict[str, InferenceRequest] = {}
        self._responses: Dict[str, InferenceResponse] = {}
        self._lock: threading.RLock = threading.RLock()
        self._latency_history: Dict[str, List[float]] = {}
        self._request_counts: Dict[str, int] = {}
        self._error_counts: Dict[str, int] = {}

    def load_model(self, model_id: str, model_config: Dict[str, Any]) -> bool:
        """
        Load a model with the given configuration.

        Args:
            model_id: Unique identifier for the model.
            model_config: Configuration dictionary for the model.

        Returns:
            True if the model was loaded successfully, False otherwise.
        """
        with self._lock:
            if model_id in self._models:
                return False

            self._models[model_id] = {
                "config": model_config,
                "status": InferenceStatus.LOADING,
                "loaded_at": time.time(),
            }

            # Simulate loading latency
            load_latency_ms = model_config.get("load_latency_ms", 100)
            time.sleep(load_latency_ms / 1000.0)

            self._models[model_id]["status"] = InferenceStatus.READY
            self._latency_history[model_id] = []
            self._request_counts[model_id] = 0
            self._error_counts[model_id] = 0
            return True

    def unload_model(self, model_id: str) -> bool:
        """
        Unload a model.

        Args:
            model_id: Unique identifier for the model.

        Returns:
            True if the model was unloaded successfully, False otherwise.
        """
        with self._lock:
            if model_id not in self._models:
                return False

            self._models[model_id]["status"] = InferenceStatus.UNLOADED
            del self._models[model_id]
            self._latency_history.pop(model_id, None)
            self._request_counts.pop(model_id, None)
            self._error_counts.pop(model_id, None)
            return True

    def predict(self, model_id: str, input_data: Any) -> InferenceResponse:
        """
        Run a single inference request.

        Args:
            model_id: Unique identifier for the model.
            input_data: Input data for the model.

        Returns:
            InferenceResponse containing the result.
        """
        request_id = str(uuid.uuid4())
        request = InferenceRequest(
            request_id=request_id,
            model_id=model_id,
            input_data=input_data,
            batch_size=1,
        )

        with self._lock:
            self._requests[request_id] = request

            if model_id not in self._models:
                response = InferenceResponse(
                    response_id=str(uuid.uuid4()),
                    request_id=request_id,
                    model_id=model_id,
                    output_data=None,
                    latency_ms=0.0,
                    status=InferenceStatus.ERROR,
                    error=f"Model '{model_id}' not found",
                )
                self._responses[response.response_id] = response
                self._error_counts[model_id] = self._error_counts.get(model_id, 0) + 1
                return response

            model = self._models[model_id]
            if model["status"] != InferenceStatus.READY:
                response = InferenceResponse(
                    response_id=str(uuid.uuid4()),
                    request_id=request_id,
                    model_id=model_id,
                    output_data=None,
                    latency_ms=0.0,
                    status=InferenceStatus.ERROR,
                    error=f"Model '{model_id}' is not ready (status: {model['status'].value})",
                )
                self._responses[response.response_id] = response
                self._error_counts[model_id] = self._error_counts.get(model_id, 0) + 1
                return response

            model["status"] = InferenceStatus.PROCESSING

        start_time = time.time()

        # Simulate inference latency
        config = model["config"]
        inference_latency_ms = config.get("inference_latency_ms", 10)
        time.sleep(inference_latency_ms / 1000.0)

        # Simulated output
        output_data = {"result": f"processed_{input_data}", "model_id": model_id}

        elapsed_ms = (time.time() - start_time) * 1000.0

        with self._lock:
            model["status"] = InferenceStatus.READY
            self._latency_history.setdefault(model_id, []).append(elapsed_ms)
            self._request_counts[model_id] = self._request_counts.get(model_id, 0) + 1

            response = InferenceResponse(
                response_id=str(uuid.uuid4()),
                request_id=request_id,
                model_id=model_id,
                output_data=output_data,
                latency_ms=elapsed_ms,
                status=InferenceStatus.READY,
            )
            self._responses[response.response_id] = response
            return response

    def predict_batch(
        self,
        model_id: str,
        inputs: List[Any],
        batch_strategy: BatchStrategy = BatchStrategy.DYNAMIC,
    ) -> List[InferenceResponse]:
        """
        Run a batch of inference requests.

        Args:
            model_id: Unique identifier for the model.
            inputs: List of input data items.
            batch_strategy: Strategy for batching requests.

        Returns:
            List of InferenceResponse objects.
        """
        with self._lock:
            if model_id not in self._models:
                error_responses = []
                for inp in inputs:
                    req_id = str(uuid.uuid4())
                    self._requests[req_id] = InferenceRequest(
                        request_id=req_id,
                        model_id=model_id,
                        input_data=inp,
                    )
                    resp = InferenceResponse(
                        response_id=str(uuid.uuid4()),
                        request_id=req_id,
                        model_id=model_id,
                        output_data=None,
                        latency_ms=0.0,
                        status=InferenceStatus.ERROR,
                        error=f"Model '{model_id}' not found",
                    )
                    self._responses[resp.response_id] = resp
                    error_responses.append(resp)
                self._error_counts[model_id] = self._error_counts.get(model_id, 0) + len(inputs)
                return error_responses

            config = self._models[model_id]["config"]
            max_batch_size = config.get("max_batch_size", 32)

        if batch_strategy == BatchStrategy.SINGLE:
            batch_sizes = [1] * len(inputs)
        elif batch_strategy == BatchStrategy.FIXED:
            batch_sizes = []
            remaining = len(inputs)
            while remaining > 0:
                size = min(max_batch_size, remaining)
                batch_sizes.append(size)
                remaining -= size
        else:  # DYNAMIC
            batch_sizes = [min(len(inputs), max_batch_size)] if inputs else []

        responses: List[InferenceResponse] = []
        idx = 0
        for batch_size in batch_sizes:
            batch_inputs = inputs[idx: idx + batch_size]
            idx += batch_size

            request_ids = [str(uuid.uuid4()) for _ in batch_inputs]
            with self._lock:
                for req_id, inp in zip(request_ids, batch_inputs):
                    self._requests[req_id] = InferenceRequest(
                        request_id=req_id,
                        model_id=model_id,
                        input_data=inp,
                        batch_size=batch_size,
                    )

            start_time = time.time()

            # Simulate batch inference latency (sub-linear scaling)
            base_latency = config.get("inference_latency_ms", 10)
            batch_latency = base_latency * (1 + 0.5 * (batch_size - 1) / max(1, max_batch_size))
            time.sleep(batch_latency / 1000.0)

            elapsed_ms = (time.time() - start_time) * 1000.0
            per_item_latency = elapsed_ms / batch_size

            with self._lock:
                self._request_counts[model_id] = self._request_counts.get(model_id, 0) + batch_size
                self._latency_history.setdefault(model_id, []).append(per_item_latency)

                for req_id, inp in zip(request_ids, batch_inputs):
                    output_data = {"result": f"processed_{inp}", "model_id": model_id}
                    resp = InferenceResponse(
                        response_id=str(uuid.uuid4()),
                        request_id=req_id,
                        model_id=model_id,
                        output_data=output_data,
                        latency_ms=per_item_latency,
                        status=InferenceStatus.READY,
                    )
                    self._responses[resp.response_id] = resp
                    responses.append(resp)

        return responses

    def get_model_status(self, model_id: str) -> InferenceStatus:
        """
        Get the status of a model.

        Args:
            model_id: Unique identifier for the model.

        Returns:
            InferenceStatus of the model, or UNLOADED if not found.
        """
        with self._lock:
            if model_id not in self._models:
                return InferenceStatus.UNLOADED
            return self._models[model_id]["status"]

    def get_loaded_models(self) -> List[str]:
        """
        Get a list of loaded model IDs.

        Returns:
            List of model IDs that are currently loaded.
        """
        with self._lock:
            return [
                model_id
                for model_id, model in self._models.items()
                if model["status"] != InferenceStatus.UNLOADED
            ]

    def get_request(self, request_id: str) -> Optional[InferenceRequest]:
        """
        Retrieve a request by ID.

        Args:
            request_id: Unique identifier for the request.

        Returns:
            The InferenceRequest if found, None otherwise.
        """
        with self._lock:
            return self._requests.get(request_id)

    def get_response(self, response_id: str) -> Optional[InferenceResponse]:
        """
        Retrieve a response by ID.

        Args:
            response_id: Unique identifier for the response.

        Returns:
            The InferenceResponse if found, None otherwise.
        """
        with self._lock:
            return self._responses.get(response_id)

    def get_latency_stats(self, model_id: str) -> Dict[str, Any]:
        """
        Get latency statistics for a model.

        Args:
            model_id: Unique identifier for the model.

        Returns:
            Dictionary with latency statistics.
        """
        with self._lock:
            history = self._latency_history.get(model_id, [])
            if not history:
                return {
                    "model_id": model_id,
                    "count": 0,
                    "mean_ms": 0.0,
                    "min_ms": 0.0,
                    "max_ms": 0.0,
                    "p50_ms": 0.0,
                    "p95_ms": 0.0,
                    "p99_ms": 0.0,
                }

            sorted_history = sorted(history)
            count = len(sorted_history)
            mean_val = sum(sorted_history) / count
            min_val = sorted_history[0]
            max_val = sorted_history[-1]
            p50 = sorted_history[int(count * 0.50)]
            p95 = sorted_history[min(int(count * 0.95), count - 1)]
            p99 = sorted_history[min(int(count * 0.99), count - 1)]

            return {
                "model_id": model_id,
                "count": count,
                "mean_ms": round(mean_val, 3),
                "min_ms": round(min_val, 3),
                "max_ms": round(max_val, 3),
                "p50_ms": round(p50, 3),
                "p95_ms": round(p95, 3),
                "p99_ms": round(p99, 3),
            }

    def get_throughput(self, model_id: str) -> float:
        """
        Calculate throughput for a model in requests per second.

        Args:
            model_id: Unique identifier for the model.

        Returns:
            Throughput as requests per second.
        """
        with self._lock:
            if model_id not in self._models:
                return 0.0

            model = self._models[model_id]
            loaded_at = model.get("loaded_at", time.time())
            elapsed_seconds = time.time() - loaded_at
            if elapsed_seconds <= 0:
                return 0.0

            request_count = self._request_counts.get(model_id, 0)
            return round(request_count / elapsed_seconds, 3)

    def warmup(self, model_id: str, sample_data: Any) -> bool:
        """
        Warm up a model with sample data.

        Args:
            model_id: Unique identifier for the model.
            sample_data: Sample input data for warmup.

        Returns:
            True if warmup was successful, False otherwise.
        """
        with self._lock:
            if model_id not in self._models:
                return False

            model = self._models[model_id]
            if model["status"] != InferenceStatus.READY:
                return False

            model["status"] = InferenceStatus.PROCESSING

        # Simulate warmup inference
        config = self._models[model_id]["config"]
        warmup_latency_ms = config.get("warmup_latency_ms", 50)
        time.sleep(warmup_latency_ms / 1000.0)

        with self._lock:
            model["status"] = InferenceStatus.READY
            return True

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get overall server statistics.

        Returns:
            Dictionary with server-wide statistics.
        """
        with self._lock:
            total_requests = sum(self._request_counts.values())
            total_errors = sum(self._error_counts.values())
            model_stats = {}
            for model_id in self._models:
                model_stats[model_id] = {
                    "status": self._models[model_id]["status"].value,
                    "request_count": self._request_counts.get(model_id, 0),
                    "error_count": self._error_counts.get(model_id, 0),
                    "throughput_rps": self.get_throughput(model_id),
                    "latency": self.get_latency_stats(model_id),
                }

            return {
                "total_models": len(self._models),
                "total_requests": total_requests,
                "total_errors": total_errors,
                "error_rate": round(total_errors / max(total_requests, 1), 4),
                "models": model_stats,
            }


# Global singleton instance and lock
_inference_server_instance: Optional[InferenceServer] = None
_inference_server_lock: threading.Lock = threading.Lock()


def get_inference_server() -> InferenceServer:
    """
    Get the global InferenceServer singleton instance.

    Uses double-checked locking for thread-safe initialization.

    Returns:
        The global InferenceServer instance.
    """
    global _inference_server_instance
    if _inference_server_instance is None:
        with _inference_server_lock:
            if _inference_server_instance is None:
                _inference_server_instance = InferenceServer()
    return _inference_server_instance


def reset_inference_server() -> None:
    """
    Reset the global InferenceServer singleton instance.

    This is intended for testing purposes.
    """
    global _inference_server_instance
    with _inference_server_lock:
        _inference_server_instance = None
