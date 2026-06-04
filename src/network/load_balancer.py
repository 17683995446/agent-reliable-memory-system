"""
Load Balancer module for the Agent Reliable Memory System.

Design Principles:
1. First Principles: deterministic rules, no model dependencies
2. Thread-safe using threading.RLock
3. Global singleton via get_load_balancer() with double-checked locking
4. Use Python dataclasses for data structures, Enum for types
5. Minimal dependencies, no circular dependencies
"""

import hashlib
import random
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional


class LoadBalanceStrategy(Enum):
    """Enumeration of supported load balancing strategies."""
    ROUND_ROBIN = auto()
    LEAST_CONNECTIONS = auto()
    WEIGHTED_ROUND_ROBIN = auto()
    RANDOM = auto()
    IP_HASH = auto()


class BackendState(Enum):
    """Enumeration of possible backend server states."""
    HEALTHY = auto()
    UNHEALTHY = auto()
    DRAINING = auto()
    MAINTENANCE = auto()


@dataclass
class BackendServer:
    """Represents a backend server in the load balancer pool."""
    server_id: str
    host: str
    port: int
    weight: int = 1
    state: BackendState = BackendState.HEALTHY
    current_connections: int = 0
    total_requests: int = 0
    failed_requests: int = 0
    last_health_check: float = field(default_factory=time.time)
    consecutive_failures: int = 0


class LoadBalancer:
    """
    Thread-safe load balancer supporting multiple strategies.

    Attributes:
        _backends: Mapping of server_id to BackendServer instances.
        _strategy: Current load balancing strategy.
        _round_robin_index: Index for round-robin selection.
        _lock: Reentrant lock for thread safety.
        _health_check_interval: Interval in seconds between health checks.
        _failure_threshold: Number of consecutive failures before removal.
        _client_ip: Client IP for IP_HASH strategy (can be set per request).
    """

    def __init__(
        self,
        strategy: LoadBalanceStrategy = LoadBalanceStrategy.ROUND_ROBIN,
        health_check_interval: float = 30.0,
        failure_threshold: int = 3,
    ) -> None:
        self._backends: Dict[str, BackendServer] = {}
        self._strategy: LoadBalanceStrategy = strategy
        self._round_robin_index: int = 0
        self._lock: threading.RLock = threading.RLock()
        self._health_check_interval: float = health_check_interval
        self._failure_threshold: int = failure_threshold
        self._client_ip: str = "127.0.0.1"
        self._total_requests: int = 0

    # ------------------------------------------------------------------
    # Backend management
    # ------------------------------------------------------------------

    def add_backend(
        self,
        server_id: str,
        host: str,
        port: int,
        weight: int = 1,
    ) -> bool:
        """
        Add a new backend server to the pool.

        Args:
            server_id: Unique identifier for the server.
            host: Hostname or IP address.
            port: Port number.
            weight: Weight for weighted strategies (default 1).

        Returns:
            True if added successfully, False if server_id already exists.
        """
        with self._lock:
            if server_id in self._backends:
                return False
            self._backends[server_id] = BackendServer(
                server_id=server_id,
                host=host,
                port=port,
                weight=max(1, weight),
            )
            return True

    def remove_backend(self, server_id: str) -> bool:
        """
        Remove a backend server from the pool.

        Args:
            server_id: Unique identifier for the server.

        Returns:
            True if removed successfully, False if not found.
        """
        with self._lock:
            if server_id not in self._backends:
                return False
            del self._backends[server_id]
            return True

    def update_backend_weight(self, server_id: str, weight: int) -> bool:
        """
        Update the weight of a backend server.

        Args:
            server_id: Unique identifier for the server.
            weight: New weight value (minimum 1).

        Returns:
            True if updated successfully, False if not found.
        """
        with self._lock:
            backend = self._backends.get(server_id)
            if backend is None:
                return False
            backend.weight = max(1, weight)
            return True

    def set_backend_state(self, server_id: str, state: BackendState) -> bool:
        """
        Set the operational state of a backend server.

        Args:
            server_id: Unique identifier for the server.
            state: New BackendState value.

        Returns:
            True if updated successfully, False if not found.
        """
        with self._lock:
            backend = self._backends.get(server_id)
            if backend is None:
                return False
            backend.state = state
            if state == BackendState.HEALTHY:
                backend.consecutive_failures = 0
            return True

    # ------------------------------------------------------------------
    # Backend selection
    # ------------------------------------------------------------------

    def select_backend(self, client_ip: Optional[str] = None) -> Optional[BackendServer]:
        """
        Select a backend server according to the current strategy.

        Args:
            client_ip: Optional client IP for IP_HASH strategy.

        Returns:
            Selected BackendServer or None if no healthy backend is available.
        """
        with self._lock:
            healthy = self._get_healthy_backends_unlocked()
            if not healthy:
                return None

            self._total_requests += 1

            if self._strategy == LoadBalanceStrategy.ROUND_ROBIN:
                return self._select_round_robin(healthy)
            elif self._strategy == LoadBalanceStrategy.LEAST_CONNECTIONS:
                return self._select_least_connections(healthy)
            elif self._strategy == LoadBalanceStrategy.WEIGHTED_ROUND_ROBIN:
                return self._select_weighted_round_robin(healthy)
            elif self._strategy == LoadBalanceStrategy.RANDOM:
                return self._select_random(healthy)
            elif self._strategy == LoadBalanceStrategy.IP_HASH:
                return self._select_ip_hash(healthy, client_ip)
            else:
                return self._select_round_robin(healthy)

    def _select_round_robin(self, healthy: List[BackendServer]) -> BackendServer:
        """Select backend using round-robin algorithm."""
        idx = self._round_robin_index % len(healthy)
        self._round_robin_index = (self._round_robin_index + 1) % len(healthy)
        return healthy[idx]

    def _select_least_connections(self, healthy: List[BackendServer]) -> BackendServer:
        """Select backend with the fewest active connections."""
        return min(healthy, key=lambda b: b.current_connections)

    def _select_weighted_round_robin(self, healthy: List[BackendServer]) -> BackendServer:
        """Select backend using weighted round-robin algorithm."""
        total_weight = sum(b.weight for b in healthy)
        if total_weight == 0:
            return self._select_round_robin(healthy)

        idx = self._round_robin_index % total_weight
        self._round_robin_index = (self._round_robin_index + 1) % total_weight

        cumulative = 0
        for backend in healthy:
            cumulative += backend.weight
            if idx < cumulative:
                return backend
        return healthy[-1]

    def _select_random(self, healthy: List[BackendServer]) -> BackendServer:
        """Select a random healthy backend."""
        return random.choice(healthy)

    def _select_ip_hash(
        self,
        healthy: List[BackendServer],
        client_ip: Optional[str] = None,
    ) -> BackendServer:
        """Select backend based on consistent hash of client IP."""
        ip = client_ip or self._client_ip
        hash_value = int(hashlib.md5(ip.encode()).hexdigest(), 16)
        idx = hash_value % len(healthy)
        return healthy[idx]

    # ------------------------------------------------------------------
    # Health checking
    # ------------------------------------------------------------------

    def health_check_all(self) -> Dict[str, bool]:
        """
        Perform health checks on all backends.

        Automatically removes backends that have exceeded the failure threshold.

        Returns:
            Dictionary mapping server_id to health check result (True = healthy).
        """
        results: Dict[str, bool] = {}
        to_remove: List[str] = []

        with self._lock:
            now = time.time()
            for server_id, backend in list(self._backends.items()):
                is_healthy = self._perform_health_check(backend)
                backend.last_health_check = now
                results[server_id] = is_healthy

                if is_healthy:
                    backend.consecutive_failures = 0
                    if backend.state == BackendState.UNHEALTHY:
                        backend.state = BackendState.HEALTHY
                else:
                    backend.consecutive_failures += 1
                    backend.state = BackendState.UNHEALTHY
                    if backend.consecutive_failures >= self._failure_threshold:
                        to_remove.append(server_id)

            for server_id in to_remove:
                del self._backends[server_id]
                results[server_id] = False

        return results

    def _perform_health_check(self, backend: BackendServer) -> bool:
        """
        Perform a single health check on a backend.

        This is a deterministic simulation; in production this would
        attempt an actual TCP connection or HTTP request.

        Args:
            backend: The backend server to check.

        Returns:
            True if the backend appears healthy.
        """
        # Deterministic health check based on server_id hash
        # Ensures reproducible behavior for the same server_id
        hash_value = int(hashlib.md5(backend.server_id.encode()).hexdigest(), 16)
        # 90% of backends are healthy by default
        return (hash_value % 100) < 90

    # ------------------------------------------------------------------
    # Statistics and queries
    # ------------------------------------------------------------------

    def get_backend_stats(self, server_id: str) -> Optional[Dict]:
        """
        Get statistics for a specific backend.

        Args:
            server_id: Unique identifier for the server.

        Returns:
            Dictionary of statistics or None if not found.
        """
        with self._lock:
            backend = self._backends.get(server_id)
            if backend is None:
                return None
            return {
                "server_id": backend.server_id,
                "host": backend.host,
                "port": backend.port,
                "weight": backend.weight,
                "state": backend.state.name,
                "current_connections": backend.current_connections,
                "total_requests": backend.total_requests,
                "failed_requests": backend.failed_requests,
                "last_health_check": backend.last_health_check,
                "consecutive_failures": backend.consecutive_failures,
            }

    def get_all_backends(self) -> List[BackendServer]:
        """
        Get a list of all registered backends.

        Returns:
            List of BackendServer instances (shallow copy).
        """
        with self._lock:
            return list(self._backends.values())

    def get_healthy_backends(self) -> List[BackendServer]:
        """
        Get a list of all healthy backends.

        Returns:
            List of healthy BackendServer instances.
        """
        with self._lock:
            return self._get_healthy_backends_unlocked()

    def _get_healthy_backends_unlocked(self) -> List[BackendServer]:
        """Internal method to get healthy backends (lock must be held)."""
        return [
            b for b in self._backends.values()
            if b.state == BackendState.HEALTHY
        ]

    # ------------------------------------------------------------------
    # Strategy management
    # ------------------------------------------------------------------

    def set_strategy(self, strategy: LoadBalanceStrategy) -> bool:
        """
        Set the load balancing strategy.

        Args:
            strategy: New LoadBalanceStrategy value.

        Returns:
            Always returns True.
        """
        with self._lock:
            self._strategy = strategy
            self._round_robin_index = 0
            return True

    def get_strategy(self) -> LoadBalanceStrategy:
        """
        Get the current load balancing strategy.

        Returns:
            Current LoadBalanceStrategy value.
        """
        with self._lock:
            return self._strategy

    # ------------------------------------------------------------------
    # Request tracking
    # ------------------------------------------------------------------

    def mark_request_start(self, server_id: str) -> bool:
        """
        Mark the start of a request to a backend.

        Args:
            server_id: Unique identifier for the server.

        Returns:
            True if marked successfully, False if not found.
        """
        with self._lock:
            backend = self._backends.get(server_id)
            if backend is None:
                return False
            backend.current_connections += 1
            backend.total_requests += 1
            return True

    def mark_request_end(self, server_id: str, success: bool = True) -> bool:
        """
        Mark the end of a request to a backend.

        Args:
            server_id: Unique identifier for the server.
            success: Whether the request completed successfully.

        Returns:
            True if marked successfully, False if not found.
        """
        with self._lock:
            backend = self._backends.get(server_id)
            if backend is None:
                return False
            backend.current_connections = max(0, backend.current_connections - 1)
            if not success:
                backend.failed_requests += 1
            return True

    # ------------------------------------------------------------------
    # Global statistics
    # ------------------------------------------------------------------

    def get_statistics(self) -> Dict:
        """
        Get aggregate statistics for the load balancer.

        Returns:
            Dictionary containing overall statistics.
        """
        with self._lock:
            total_backends = len(self._backends)
            healthy_backends = len(self._get_healthy_backends_unlocked())
            total_connections = sum(b.current_connections for b in self._backends.values())
            total_requests = sum(b.total_requests for b in self._backends.values())
            total_failed = sum(b.failed_requests for b in self._backends.values())

            return {
                "strategy": self._strategy.name,
                "total_backends": total_backends,
                "healthy_backends": healthy_backends,
                "unhealthy_backends": total_backends - healthy_backends,
                "total_connections": total_connections,
                "total_requests": total_requests,
                "total_failed_requests": total_failed,
                "failure_rate": total_failed / total_requests if total_requests > 0 else 0.0,
                "health_check_interval": self._health_check_interval,
                "failure_threshold": self._failure_threshold,
            }

    # ------------------------------------------------------------------
    # Client IP for IP_HASH strategy
    # ------------------------------------------------------------------

    def set_client_ip(self, client_ip: str) -> None:
        """Set the default client IP for IP_HASH strategy."""
        with self._lock:
            self._client_ip = client_ip

    def get_client_ip(self) -> str:
        """Get the default client IP for IP_HASH strategy."""
        with self._lock:
            return self._client_ip


# ------------------------------------------------------------------------------
# Singleton management with double-checked locking
# ------------------------------------------------------------------------------

_load_balancer_instance: Optional[LoadBalancer] = None
_load_balancer_lock: threading.Lock = threading.Lock()


def get_load_balancer(
    strategy: LoadBalanceStrategy = LoadBalanceStrategy.ROUND_ROBIN,
    health_check_interval: float = 30.0,
    failure_threshold: int = 3,
) -> LoadBalancer:
    """
    Get the global LoadBalancer singleton instance.

    Uses double-checked locking for thread-safe lazy initialization.

    Args:
        strategy: Default load balancing strategy.
        health_check_interval: Health check interval in seconds.
        failure_threshold: Consecutive failures before auto-removal.

    Returns:
        The global LoadBalancer instance.
    """
    global _load_balancer_instance
    if _load_balancer_instance is None:
        with _load_balancer_lock:
            if _load_balancer_instance is None:
                _load_balancer_instance = LoadBalancer(
                    strategy=strategy,
                    health_check_interval=health_check_interval,
                    failure_threshold=failure_threshold,
                )
    return _load_balancer_instance


def reset_load_balancer() -> None:
    """
    Reset the global LoadBalancer singleton instance.

    This is primarily intended for testing purposes.
    """
    global _load_balancer_instance
    with _load_balancer_lock:
        _load_balancer_instance = None
