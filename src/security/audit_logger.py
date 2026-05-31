"""
Audit Logger Module for Agent Reliable Memory System.
Phase 35 Stage 379

Design Principles:
1. First Principles: deterministic rules, no model dependencies
2. Thread-safe using threading.RLock
3. Global singleton via get_audit_logger() with double-checked locking
4. Use Python dataclasses for data structures, Enum for types
5. Minimal dependencies, no circular dependencies
"""

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union


class AuditEventType(Enum):
    """Enumeration of audit event types."""
    LOGIN = "login"
    LOGOUT = "logout"
    ACCESS_GRANTED = "access_granted"
    ACCESS_DENIED = "access_denied"
    DATA_READ = "data_read"
    DATA_WRITE = "data_write"
    DATA_DELETE = "data_delete"
    CONFIG_CHANGE = "config_change"
    ERROR = "error"
    SYSTEM = "system"


class AuditSeverity(Enum):
    """Enumeration of audit event severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """
    Data class representing a single audit event.
    
    Attributes:
        event_id: Unique identifier for the event
        event_type: Type of the audit event
        severity: Severity level of the event
        user_id: ID of the user associated with the event
        resource_type: Type of resource involved
        resource_id: ID of the resource involved
        action: Action performed
        details: Additional details about the event
        ip_address: IP address of the client
        timestamp: Time when the event occurred
        session_id: Session identifier
    """
    event_id: str
    event_type: AuditEventType
    severity: AuditSeverity
    user_id: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    action: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    session_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert the audit event to a dictionary representation."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "user_id": self.user_id,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "action": self.action,
            "details": self.details,
            "ip_address": self.ip_address,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "session_id": self.session_id
        }


@dataclass
class AuditLog:
    """
    Data class representing a collection of audit events.
    
    Attributes:
        events: List of audit events
        total_count: Total number of events
        start_time: Start time of the log period
        end_time: End time of the log period
    """
    events: List[AuditEvent] = field(default_factory=list)
    total_count: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert the audit log to a dictionary representation."""
        return {
            "events": [event.to_dict() for event in self.events],
            "total_count": self.total_count,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None
        }


class AuditLogger:
    """
    Thread-safe audit logger for recording and managing audit events.
    
    This class provides comprehensive audit logging capabilities with:
    - Thread-safe operations using RLock
    - Configurable maximum event storage
    - Multiple query and filtering options
    - Statistics generation
    - Export capabilities
    
    Attributes:
        _events: List of stored audit events
        _max_events: Maximum number of events to store
        _lock: Reentrant lock for thread safety
    """

    def __init__(self, max_events: int = 10000):
        """
        Initialize the AuditLogger.
        
        Args:
            max_events: Maximum number of events to store (default: 10000)
        """
        self._events: List[AuditEvent] = []
        self._max_events: int = max_events
        self._lock: threading.RLock = threading.RLock()

    def _generate_event_id(self) -> str:
        """Generate a unique event ID using UUID4."""
        return str(uuid.uuid4())

    def _add_event(self, event: AuditEvent) -> None:
        """
        Add an event to the internal storage with thread safety.
        
        If the maximum event count is reached, the oldest events are removed.
        
        Args:
            event: The audit event to add
        """
        with self._lock:
            if len(self._events) >= self._max_events:
                # Remove oldest events to make room
                overflow = len(self._events) - self._max_events + 1
                self._events = self._events[overflow:]
            self._events.append(event)

    def log_event(
        self,
        event_type: AuditEventType,
        severity: AuditSeverity,
        user_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        action: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> str:
        """
        Log a generic audit event.
        
        Args:
            event_type: Type of the audit event
            severity: Severity level of the event
            user_id: ID of the user associated with the event
            resource_type: Type of resource involved
            resource_id: ID of the resource involved
            action: Action performed
            details: Additional details about the event
            ip_address: IP address of the client
            session_id: Session identifier
            
        Returns:
            The unique event ID of the logged event
        """
        event_id = self._generate_event_id()
        event = AuditEvent(
            event_id=event_id,
            event_type=event_type,
            severity=severity,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            details=details,
            ip_address=ip_address,
            timestamp=datetime.now(),
            session_id=session_id
        )
        self._add_event(event)
        return event_id

    def log_login(
        self,
        user_id: str,
        success: bool,
        ip_address: Optional[str] = None
    ) -> str:
        """
        Log a login attempt.
        
        Args:
            user_id: ID of the user attempting to login
            success: Whether the login was successful
            ip_address: IP address of the client
            
        Returns:
            The unique event ID of the logged event
        """
        event_type = AuditEventType.LOGIN
        severity = AuditSeverity.INFO if success else AuditSeverity.WARNING
        details = {"success": success}
        
        return self.log_event(
            event_type=event_type,
            severity=severity,
            user_id=user_id,
            action="login",
            details=details,
            ip_address=ip_address
        )

    def log_logout(
        self,
        user_id: str,
        session_id: str
    ) -> str:
        """
        Log a logout event.
        
        Args:
            user_id: ID of the user logging out
            session_id: Session identifier being terminated
            
        Returns:
            The unique event ID of the logged event
        """
        return self.log_event(
            event_type=AuditEventType.LOGOUT,
            severity=AuditSeverity.INFO,
            user_id=user_id,
            action="logout",
            session_id=session_id
        )

    def log_access(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        action: str,
        granted: bool,
        details: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Log an access control event.
        
        Args:
            user_id: ID of the user attempting access
            resource_type: Type of resource being accessed
            resource_id: ID of the resource being accessed
            action: Action being attempted (e.g., 'read', 'write', 'delete')
            granted: Whether access was granted
            details: Additional details about the access attempt
            
        Returns:
            The unique event ID of the logged event
        """
        event_type = AuditEventType.ACCESS_GRANTED if granted else AuditEventType.ACCESS_DENIED
        severity = AuditSeverity.INFO if granted else AuditSeverity.WARNING
        
        merged_details = {"granted": granted}
        if details:
            merged_details.update(details)
        
        return self.log_event(
            event_type=event_type,
            severity=severity,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            details=merged_details
        )

    def log_data_operation(
        self,
        user_id: str,
        operation: str,
        resource_type: str,
        resource_id: str,
        details: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Log a data operation event.
        
        Args:
            user_id: ID of the user performing the operation
            operation: Type of operation ('read', 'write', 'delete')
            resource_type: Type of resource being operated on
            resource_id: ID of the resource being operated on
            details: Additional details about the operation
            
        Returns:
            The unique event ID of the logged event
        """
        operation_map = {
            "read": AuditEventType.DATA_READ,
            "write": AuditEventType.DATA_WRITE,
            "delete": AuditEventType.DATA_DELETE
        }
        
        event_type = operation_map.get(operation.lower(), AuditEventType.DATA_WRITE)
        
        return self.log_event(
            event_type=event_type,
            severity=AuditSeverity.INFO,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action=operation,
            details=details
        )

    def log_error(
        self,
        error_message: str,
        user_id: Optional[str] = None,
        severity: AuditSeverity = AuditSeverity.ERROR
    ) -> str:
        """
        Log an error event.
        
        Args:
            error_message: Description of the error
            user_id: ID of the user associated with the error (optional)
            severity: Severity level of the error (default: ERROR)
            
        Returns:
            The unique event ID of the logged event
        """
        return self.log_event(
            event_type=AuditEventType.ERROR,
            severity=severity,
            user_id=user_id,
            action="error",
            details={"error_message": error_message}
        )

    def get_events(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        user_id: Optional[str] = None,
        event_type: Optional[AuditEventType] = None,
        severity: Optional[AuditSeverity] = None,
        limit: int = 100
    ) -> List[AuditEvent]:
        """
        Retrieve audit events with optional filtering.
        
        Args:
            start_time: Filter events after this time
            end_time: Filter events before this time
            user_id: Filter by user ID
            event_type: Filter by event type
            severity: Filter by severity level
            limit: Maximum number of events to return (default: 100)
            
        Returns:
            List of matching audit events
        """
        with self._lock:
            filtered_events = []
            
            for event in reversed(self._events):  # Most recent first
                # Apply filters
                if start_time and event.timestamp < start_time:
                    continue
                if end_time and event.timestamp > end_time:
                    continue
                if user_id and event.user_id != user_id:
                    continue
                if event_type and event.event_type != event_type:
                    continue
                if severity and event.severity != severity:
                    continue
                
                filtered_events.append(event)
                
                if len(filtered_events) >= limit:
                    break
            
            return filtered_events

    def get_event_by_id(self, event_id: str) -> Optional[AuditEvent]:
        """
        Retrieve a specific audit event by its ID.
        
        Args:
            event_id: The unique identifier of the event
            
        Returns:
            The audit event if found, None otherwise
        """
        with self._lock:
            for event in self._events:
                if event.event_id == event_id:
                    return event
            return None

    def get_events_by_user(
        self,
        user_id: str,
        limit: int = 100
    ) -> List[AuditEvent]:
        """
        Retrieve all audit events for a specific user.
        
        Args:
            user_id: The user ID to filter by
            limit: Maximum number of events to return (default: 100)
            
        Returns:
            List of audit events for the specified user
        """
        return self.get_events(user_id=user_id, limit=limit)

    def get_events_by_resource(
        self,
        resource_type: str,
        resource_id: str,
        limit: int = 100
    ) -> List[AuditEvent]:
        """
        Retrieve all audit events for a specific resource.
        
        Args:
            resource_type: Type of the resource
            resource_id: ID of the resource
            limit: Maximum number of events to return (default: 100)
            
        Returns:
            List of audit events for the specified resource
        """
        with self._lock:
            filtered_events = []
            
            for event in reversed(self._events):
                if event.resource_type == resource_type and event.resource_id == resource_id:
                    filtered_events.append(event)
                    
                    if len(filtered_events) >= limit:
                        break
            
            return filtered_events

    def get_statistics(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Generate statistics about audit events.
        
        Args:
            start_time: Filter events after this time
            end_time: Filter events before this time
            
        Returns:
            Dictionary containing various statistics
        """
        with self._lock:
            # Filter events by time range
            filtered_events = []
            for event in self._events:
                if start_time and event.timestamp < start_time:
                    continue
                if end_time and event.timestamp > end_time:
                    continue
                filtered_events.append(event)
            
            # Calculate statistics
            total_count = len(filtered_events)
            
            # Count by event type
            event_type_counts: Dict[str, int] = {}
            for event in filtered_events:
                type_name = event.event_type.value
                event_type_counts[type_name] = event_type_counts.get(type_name, 0) + 1
            
            # Count by severity
            severity_counts: Dict[str, int] = {}
            for event in filtered_events:
                severity_name = event.severity.value
                severity_counts[severity_name] = severity_counts.get(severity_name, 0) + 1
            
            # Count by user
            user_counts: Dict[str, int] = {}
            for event in filtered_events:
                if event.user_id:
                    user_counts[event.user_id] = user_counts.get(event.user_id, 0) + 1
            
            # Calculate time range
            if filtered_events:
                timestamps = [event.timestamp for event in filtered_events]
                actual_start = min(timestamps)
                actual_end = max(timestamps)
            else:
                actual_start = None
                actual_end = None
            
            return {
                "total_count": total_count,
                "event_type_counts": event_type_counts,
                "severity_counts": severity_counts,
                "user_counts": user_counts,
                "time_range": {
                    "start": actual_start.isoformat() if actual_start else None,
                    "end": actual_end.isoformat() if actual_end else None
                },
                "stored_events": len(self._events),
                "max_events": self._max_events
            }

    def clear_events(self) -> int:
        """
        Clear all stored audit events.
        
        Returns:
            The number of events that were cleared
        """
        with self._lock:
            count = len(self._events)
            self._events = []
            return count

    def export_events(self, format: str = "dict") -> Union[List[Dict[str, Any]], str]:
        """
        Export all audit events in the specified format.
        
        Args:
            format: Export format ('dict', 'json')
            
        Returns:
            Exported events in the specified format
        """
        with self._lock:
            events_data = [event.to_dict() for event in self._events]
            
            if format == "json":
                import json
                return json.dumps(events_data, indent=2, default=str)
            
            return events_data


# Global singleton instance and lock
_audit_logger_instance: Optional[AuditLogger] = None
_audit_logger_lock: threading.RLock = threading.RLock()


def get_audit_logger() -> AuditLogger:
    """
    Get the global AuditLogger singleton instance.
    
    Uses double-checked locking pattern for thread-safe singleton initialization.
    
    Returns:
        The global AuditLogger instance
    """
    global _audit_logger_instance
    
    if _audit_logger_instance is None:
        with _audit_logger_lock:
            if _audit_logger_instance is None:
                _audit_logger_instance = AuditLogger()
    
    return _audit_logger_instance


def reset_audit_logger() -> None:
    """
    Reset the global AuditLogger instance (for testing).
    """
    global _audit_logger_instance
    with _audit_logger_lock:
        _audit_logger_instance = None
