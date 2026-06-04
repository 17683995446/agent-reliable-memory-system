"""
Service Discovery module for the Agent Reliable Memory System.

Stage: 385

Design Principles:
1. First Principles: deterministic rules, no model dependencies
2. Thread-safe using threading.RLock
3. Global singleton via get_service_discovery() with double-checked locking
4. Use Python dataclasses for data structures, Enum for types
5. Minimal dependencies, no circular dependencies

This module provides service registration, discovery, health checking,
heartbeat TTL, service watching with callbacks, and automatic cleanup
of stale instances.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional


class ServiceStatus(Enum):
    """Enumeration of possible service instance statuses."""

    REGISTERED = auto()
    UNREGISTERED = auto()
    UNHEALTHY = auto()
    UNKNOWN = auto()


class ServiceType(Enum):
    """Enumeration of supported service types."""

    API = auto()
    DATABASE = auto()
    CACHE = auto()
    MESSAGE_QUEUE = auto()
    STORAGE = auto()
    COMPUTE = auto()


@dataclass
class ServiceInstance:
    """Represents a single registered service instance."""

    instance_id: str
    service_name: str
    service_type: ServiceType
    host: str
    port: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: ServiceStatus = ServiceStatus.REGISTERED
    registered_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    health_check_url: Optional[str] = None


@dataclass
class ServiceRegistry:
    """Represents the registry entry for a named service."""

    service_name: str
    service_type: ServiceType
    instances: List[str] = field(default_factory=list)
    version: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class ServiceDiscovery:
    """Thread-safe service discovery with heartbeat, watch, and cleanup.

    Attributes:
        _services: Mapping from service_name to ServiceRegistry.
        _instances: Mapping from instance_id to ServiceInstance.
        _lock: Reentrant lock for thread safety.
        _watches: Mapping from watch_id to (service_name, callback).
        _watch_counter: Monotonically increasing counter for watch IDs.
    """

    def __init__(self) -> None:
        """Initialize a new ServiceDiscovery instance."""
        self._services: Dict[str, ServiceRegistry] = {}
        self._instances: Dict[str, ServiceInstance] = {}
        self._lock: threading.RLock = threading.RLock()
        self._watches: Dict[str, tuple] = {}
        self._watch_counter: int = 0

    def register_service(
        self,
        service_name: str,
        service_type: ServiceType,
        host: str,
        port: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Register a new service instance.

        Args:
            service_name: Logical name of the service.
            service_type: Type of the service.
            host: Host address of the instance.
            port: Port number of the instance.
            metadata: Optional metadata dictionary.

        Returns:
            The generated instance_id for the registered service.
        """
        instance_id = str(uuid.uuid4())
        now = time.time()
        instance = ServiceInstance(
            instance_id=instance_id,
            service_name=service_name,
            service_type=service_type,
            host=host,
            port=port,
            metadata=metadata if metadata is not None else {},
            status=ServiceStatus.REGISTERED,
            registered_at=now,
            last_heartbeat=now,
            health_check_url=None,
        )

        with self._lock:
            self._instances[instance_id] = instance

            if service_name not in self._services:
                self._services[service_name] = ServiceRegistry(
                    service_name=service_name,
                    service_type=service_type,
                    instances=[instance_id],
                    version=1,
                )
            else:
                registry = self._services[service_name]
                if instance_id not in registry.instances:
                    registry.instances.append(instance_id)
                registry.version += 1

            self._notify_watchers(service_name)

        return instance_id

    def unregister_service(self, instance_id: str) -> bool:
        """Unregister a service instance by its ID.

        Args:
            instance_id: The instance ID to unregister.

        Returns:
            True if the instance was found and removed, False otherwise.
        """
        with self._lock:
            instance = self._instances.pop(instance_id, None)
            if instance is None:
                return False

            service_name = instance.service_name
            registry = self._services.get(service_name)
            if registry is not None:
                if instance_id in registry.instances:
                    registry.instances.remove(instance_id)
                registry.version += 1
                if not registry.instances:
                    del self._services[service_name]

            instance.status = ServiceStatus.UNREGISTERED
            self._notify_watchers(service_name)

        return True

    def discover(self, service_name: str) -> List[ServiceInstance]:
        """Discover all healthy instances of a named service.

        Args:
            service_name: The service name to look up.

        Returns:
            List of active ServiceInstance objects.
        """
        with self._lock:
            registry = self._services.get(service_name)
            if registry is None:
                return []

            result: List[ServiceInstance] = []
            for iid in list(registry.instances):
                instance = self._instances.get(iid)
                if instance is not None and instance.status in (
                    ServiceStatus.REGISTERED,
                    ServiceStatus.UNKNOWN,
                ):
                    result.append(instance)
            return result

    def discover_by_type(self, service_type: ServiceType) -> List[ServiceInstance]:
        """Discover all healthy instances of a given service type.

        Args:
            service_type: The service type to look up.

        Returns:
            List of active ServiceInstance objects.
        """
        with self._lock:
            result: List[ServiceInstance] = []
            for instance in self._instances.values():
                if (
                    instance.service_type == service_type
                    and instance.status
                    in (ServiceStatus.REGISTERED, ServiceStatus.UNKNOWN)
                ):
                    result.append(instance)
            return result

    def get_service(self, instance_id: str) -> Optional[ServiceInstance]:
        """Retrieve a specific service instance by ID.

        Args:
            instance_id: The instance ID to look up.

        Returns:
            The ServiceInstance if found, otherwise None.
        """
        with self._lock:
            return self._instances.get(instance_id)

    def heartbeat(self, instance_id: str) -> bool:
        """Record a heartbeat for a service instance.

        Args:
            instance_id: The instance ID to update.

        Returns:
            True if the instance exists and was updated, False otherwise.
        """
        with self._lock:
            instance = self._instances.get(instance_id)
            if instance is None:
                return False
            instance.last_heartbeat = time.time()
            if instance.status == ServiceStatus.UNHEALTHY:
                instance.status = ServiceStatus.REGISTERED
            return True

    def health_check(self, instance_id: str) -> bool:
        """Perform a health check on a service instance.

        Currently this updates the heartbeat and marks the instance as
        REGISTERED if it was UNHEALTHY. In a real deployment this could
        perform an HTTP probe against health_check_url.

        Args:
            instance_id: The instance ID to check.

        Returns:
            True if the instance is considered healthy, False otherwise.
        """
        with self._lock:
            instance = self._instances.get(instance_id)
            if instance is None:
                return False
            instance.last_heartbeat = time.time()
            if instance.status == ServiceStatus.UNHEALTHY:
                instance.status = ServiceStatus.REGISTERED
            return instance.status in (
                ServiceStatus.REGISTERED,
                ServiceStatus.UNKNOWN,
            )

    def get_all_services(self) -> List[str]:
        """Return a list of all registered service names.

        Returns:
            List of service name strings.
        """
        with self._lock:
            return list(self._services.keys())

    def get_service_registry(self, service_name: str) -> Optional[ServiceRegistry]:
        """Retrieve the registry entry for a service.

        Args:
            service_name: The service name to look up.

        Returns:
            The ServiceRegistry if found, otherwise None.
        """
        with self._lock:
            return self._services.get(service_name)

    def update_metadata(self, instance_id: str, metadata: Dict[str, Any]) -> bool:
        """Update metadata for a service instance.

        Args:
            instance_id: The instance ID to update.
            metadata: New metadata dictionary (merged with existing).

        Returns:
            True if the instance exists and was updated, False otherwise.
        """
        with self._lock:
            instance = self._instances.get(instance_id)
            if instance is None:
                return False
            instance.metadata.update(metadata)
            self._notify_watchers(instance.service_name)
            return True

    def watch(self, service_name: str, callback: Callable[[ServiceRegistry], None]) -> str:
        """Register a callback to be invoked when a service changes.

        Args:
            service_name: The service name to watch.
            callback: Callable accepting a ServiceRegistry argument.

        Returns:
            A watch_id that can be used to unwatch later.
        """
        with self._lock:
            self._watch_counter += 1
            watch_id = f"watch-{self._watch_counter}"
            self._watches[watch_id] = (service_name, callback)
            return watch_id

    def unwatch(self, watch_id: str) -> bool:
        """Remove a previously registered watch.

        Args:
            watch_id: The watch ID to remove.

        Returns:
            True if the watch existed and was removed, False otherwise.
        """
        with self._lock:
            return self._watches.pop(watch_id, None) is not None

    def cleanup_stale(self, timeout_seconds: int = 60) -> int:
        """Remove instances that have not sent a heartbeat within the timeout.

        Args:
            timeout_seconds: Maximum allowed age of the last heartbeat.

        Returns:
            Number of stale instances removed.
        """
        now = time.time()
        removed = 0
        with self._lock:
            stale_ids = [
                iid
                for iid, inst in self._instances.items()
                if (now - inst.last_heartbeat) > timeout_seconds
            ]
            for iid in stale_ids:
                instance = self._instances.pop(iid, None)
                if instance is not None:
                    service_name = instance.service_name
                    registry = self._services.get(service_name)
                    if registry is not None:
                        if iid in registry.instances:
                            registry.instances.remove(iid)
                        registry.version += 1
                        if not registry.instances:
                            del self._services[service_name]
                    instance.status = ServiceStatus.UNHEALTHY
                    self._notify_watchers(service_name)
                    removed += 1
        return removed

    def get_statistics(self) -> Dict[str, Any]:
        """Return runtime statistics about the discovery state.

        Returns:
            Dictionary with counts and summary information.
        """
        with self._lock:
            total_instances = len(self._instances)
            total_services = len(self._services)
            status_counts: Dict[str, int] = {}
            type_counts: Dict[str, int] = {}
            for inst in self._instances.values():
                status_key = inst.status.name
                status_counts[status_key] = status_counts.get(status_key, 0) + 1
                type_key = inst.service_type.name
                type_counts[type_key] = type_counts.get(type_key, 0) + 1
            return {
                "total_instances": total_instances,
                "total_services": total_services,
                "total_watches": len(self._watches),
                "status_counts": status_counts,
                "type_counts": type_counts,
            }

    def _notify_watchers(self, service_name: str) -> None:
        """Invoke callbacks for watchers of the given service name.

        This method must be called while holding self._lock.

        Args:
            service_name: The service that changed.
        """
        registry = self._services.get(service_name)
        if registry is None:
            registry = ServiceRegistry(
                service_name=service_name,
                service_type=ServiceType.API,
                instances=[],
                version=0,
            )
        for watch_id, (watched_name, callback) in list(self._watches.items()):
            if watched_name == service_name:
                try:
                    callback(registry)
                except Exception:
                    pass


# Global singleton instance and lock for double-checked locking
_service_discovery_instance: Optional[ServiceDiscovery] = None
_service_discovery_lock: threading.Lock = threading.Lock()


def get_service_discovery() -> ServiceDiscovery:
    """Return the global ServiceDiscovery singleton.

    Uses double-checked locking for thread-safe lazy initialization.

    Returns:
        The global ServiceDiscovery instance.
    """
    global _service_discovery_instance
    if _service_discovery_instance is None:
        with _service_discovery_lock:
            if _service_discovery_instance is None:
                _service_discovery_instance = ServiceDiscovery()
    return _service_discovery_instance


def reset_service_discovery() -> None:
    """Reset the global singleton instance.

    This is intended for testing purposes only.
    """
    global _service_discovery_instance
    with _service_discovery_lock:
        _service_discovery_instance = None
