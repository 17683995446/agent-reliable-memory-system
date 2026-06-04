"""
Request Dispatcher module for the Agent Reliable Memory System.

Stage 383: Network request dispatching with priority queue, rate limiting,
timeout handling, and retry logic.

Design Principles:
1. First Principles: deterministic rules, no model dependencies
2. Thread-safe using threading.RLock
3. Global singleton via get_request_dispatcher() with double-checked locking
4. Use Python dataclasses for data structures, Enum for types
5. Minimal dependencies, no circular dependencies
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from queue import PriorityQueue, Empty
from typing import Any, Callable, Dict, Optional


class RequestMethod(Enum):
    """Supported HTTP request methods."""
    GET = auto()
    POST = auto()
    PUT = auto()
    DELETE = auto()
    PATCH = auto()
    HEAD = auto()
    OPTIONS = auto()


class RequestPriority(Enum):
    """Priority levels for network requests."""
    LOW = 4
    NORMAL = 3
    HIGH = 2
    CRITICAL = 1


class RequestStatus(Enum):
    """Lifecycle states of a network request."""
    PENDING = auto()
    PROCESSING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()


@dataclass
class NetworkRequest:
    """Represents an outgoing network request."""
    request_id: str
    method: RequestMethod
    url: str
    headers: Dict[str, str] = field(default_factory=dict)
    body: Optional[bytes] = None
    priority: RequestPriority = RequestPriority.NORMAL
    status: RequestStatus = RequestStatus.PENDING
    created_at: float = field(default_factory=time.time)
    timeout: float = 30.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __lt__(self, other: NetworkRequest) -> bool:
        """Compare requests by priority for the priority queue."""
        if not isinstance(other, NetworkRequest):
            return NotImplemented
        return self.priority.value < other.priority.value


@dataclass
class NetworkResponse:
    """Represents the result of a network request."""
    request_id: str
    status_code: int = 0
    headers: Dict[str, str] = field(default_factory=dict)
    body: Optional[bytes] = None
    duration_ms: float = 0.0
    error: Optional[str] = None


class _TokenBucket:
    """Token bucket for rate limiting."""

    def __init__(self, rate: float, capacity: Optional[float] = None) -> None:
        self._rate = max(rate, 0.0)
        self._capacity = capacity if capacity is not None else max(rate, 1.0)
        self._tokens = self._capacity
        self._last_update = time.monotonic()
        self._lock = threading.Lock()

    def set_rate(self, rate: float) -> None:
        with self._lock:
            self._rate = max(rate, 0.0)
            self._capacity = max(self._capacity, self._rate)

    def consume(self, tokens: float = 1.0) -> bool:
        if self._rate <= 0.0:
            return True
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_update
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            self._last_update = now
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    def wait_time(self, tokens: float = 1.0) -> float:
        if self._rate <= 0.0:
            return 0.0
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_update
            current = min(self._capacity, self._tokens + elapsed * self._rate)
            deficit = tokens - current
            if deficit <= 0.0:
                return 0.0
            return deficit / self._rate


class RequestDispatcher:
    """Thread-safe request dispatcher with priority queue and rate limiting."""

    _MAX_RETRIES = 3
    _BACKOFF_BASE_MS = 100.0

    def __init__(self) -> None:
        self._queue: PriorityQueue[NetworkRequest] = PriorityQueue()
        self._handlers: Dict[RequestMethod, Callable[[NetworkRequest], NetworkResponse]] = {}
        self._results: Dict[str, NetworkResponse] = {}
        self._lock = threading.RLock()
        self._rate_limiter = _TokenBucket(rate=0.0)
        self._statistics: Dict[str, Any] = {
            "dispatched": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0,
            "retried": 0,
            "total_duration_ms": 0.0,
        }

    def dispatch(self, request: NetworkRequest) -> str:
        """Enqueue a request for asynchronous processing.

        Returns the request_id assigned to the request.
        """
        with self._lock:
            if not request.request_id:
                request.request_id = str(uuid.uuid4())
            request.status = RequestStatus.PENDING
            self._queue.put(request)
            self._statistics["dispatched"] += 1
            return request.request_id

    def dispatch_sync(self, request: NetworkRequest) -> NetworkResponse:
        """Execute a request synchronously, respecting rate limits and retries."""
        if not request.request_id:
            request.request_id = str(uuid.uuid4())

        self._wait_for_rate_limit()

        start = time.monotonic()
        last_error: Optional[str] = None

        for attempt in range(self._MAX_RETRIES + 1):
            request.status = RequestStatus.PROCESSING
            try:
                handler = self._get_handler(request.method)
                response = handler(request)
                elapsed_ms = (time.monotonic() - start) * 1000.0
                response.duration_ms = elapsed_ms
                response.request_id = request.request_id
                request.status = RequestStatus.COMPLETED

                with self._lock:
                    self._results[request.request_id] = response
                    self._statistics["completed"] += 1
                    self._statistics["total_duration_ms"] += elapsed_ms

                return response
            except Exception as exc:
                last_error = str(exc)
                if attempt < self._MAX_RETRIES:
                    backoff_ms = self._BACKOFF_BASE_MS * (2 ** attempt)
                    time.sleep(backoff_ms / 1000.0)
                    with self._lock:
                        self._statistics["retried"] += 1
                else:
                    break

        elapsed_ms = (time.monotonic() - start) * 1000.0
        response = NetworkResponse(
            request_id=request.request_id,
            error=last_error,
            duration_ms=elapsed_ms,
        )
        request.status = RequestStatus.FAILED

        with self._lock:
            self._results[request.request_id] = response
            self._statistics["failed"] += 1
            self._statistics["total_duration_ms"] += elapsed_ms

        return response

    def cancel(self, request_id: str) -> bool:
        """Attempt to cancel a pending request.

        Returns True if the request was found and cancelled.
        """
        with self._lock:
            # Rebuild the queue without the target request
            temp_queue: PriorityQueue[NetworkRequest] = PriorityQueue()
            cancelled = False
            while not self._queue.empty():
                try:
                    req = self._queue.get_nowait()
                except Empty:
                    break
                if req.request_id == request_id and req.status == RequestStatus.PENDING:
                    req.status = RequestStatus.CANCELLED
                    self._results[request_id] = NetworkResponse(
                        request_id=request_id,
                        error="Cancelled by user",
                    )
                    self._statistics["cancelled"] += 1
                    cancelled = True
                else:
                    temp_queue.put(req)
            self._queue = temp_queue
            return cancelled

    def get_status(self, request_id: str) -> RequestStatus:
        """Return the current status of a request."""
        with self._lock:
            # Check queued items
            for req in list(self._queue.queue):
                if req.request_id == request_id:
                    return req.status
            # Check results
            if request_id in self._results:
                resp = self._results[request_id]
                if resp.error == "Cancelled by user":
                    return RequestStatus.CANCELLED
                if resp.error:
                    return RequestStatus.FAILED
                return RequestStatus.COMPLETED
            return RequestStatus.PENDING

    def get_result(self, request_id: str) -> Optional[NetworkResponse]:
        """Retrieve the result for a completed or failed request."""
        with self._lock:
            return self._results.get(request_id)

    def register_handler(
        self,
        method: RequestMethod,
        handler: Callable[[NetworkRequest], NetworkResponse],
    ) -> bool:
        """Register a handler for a specific HTTP method.

        Returns True if registration succeeded.
        """
        with self._lock:
            if not callable(handler):
                return False
            self._handlers[method] = handler
            return True

    def get_queue_size(self) -> int:
        """Return the number of pending requests in the queue."""
        with self._lock:
            return self._queue.qsize()

    def clear_queue(self) -> int:
        """Remove all pending requests from the queue.

        Returns the number of requests cleared.
        """
        with self._lock:
            count = 0
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                    count += 1
                except Empty:
                    break
            return count

    def set_rate_limit(self, requests_per_second: float) -> bool:
        """Configure the token bucket rate limiter.

        Returns True if the rate was updated.
        """
        with self._lock:
            if requests_per_second < 0:
                return False
            self._rate_limiter.set_rate(requests_per_second)
            return True

    def get_statistics(self) -> Dict[str, Any]:
        """Return a snapshot of dispatcher statistics."""
        with self._lock:
            stats = dict(self._statistics)
            stats["queue_size"] = self._queue.qsize()
            stats["handlers_registered"] = list(self._handlers.keys())
            completed = stats.get("completed", 0)
            total_dur = stats.get("total_duration_ms", 0.0)
            stats["average_duration_ms"] = total_dur / completed if completed > 0 else 0.0
            return stats

    def _get_handler(
        self, method: RequestMethod
    ) -> Callable[[NetworkRequest], NetworkResponse]:
        with self._lock:
            handler = self._handlers.get(method)
            if handler is None:
                raise RuntimeError(f"No handler registered for method {method.name}")
            return handler

    def _wait_for_rate_limit(self) -> None:
        while not self._rate_limiter.consume():
            wait_time = self._rate_limiter.wait_time()
            if wait_time > 0:
                time.sleep(wait_time)


# Global singleton instance and lock
_dispatcher_instance: Optional[RequestDispatcher] = None
_dispatcher_lock = threading.Lock()


def get_request_dispatcher() -> RequestDispatcher:
    """Return the global RequestDispatcher singleton.

    Uses double-checked locking for thread-safe initialization.
    """
    global _dispatcher_instance
    if _dispatcher_instance is None:
        with _dispatcher_lock:
            if _dispatcher_instance is None:
                _dispatcher_instance = RequestDispatcher()
    return _dispatcher_instance


def reset_request_dispatcher() -> None:
    """Reset the global singleton instance.

    Intended for testing purposes only.
    """
    global _dispatcher_instance
    with _dispatcher_lock:
        _dispatcher_instance = None
