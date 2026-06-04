"""
Data Sink Module for Agent Reliable Memory System.

Stage 388: Data Sink - Pipeline Output Endpoint

Design Principles:
1. First Principles: deterministic rules, no model dependencies
2. Thread-safe using threading.RLock
3. Global singleton via get_data_sink_manager() with double-checked locking
4. Use Python dataclasses for data structures, Enum for types
5. Minimal dependencies, no circular dependencies
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from threading import RLock
from typing import Any, Dict, List, Optional


class SinkType(Enum):
    """Enumeration of supported data sink types."""
    FILE = "file"
    DATABASE = "database"
    API = "api"
    QUEUE = "queue"
    MEMORY = "memory"
    CONSOLE = "console"


class WriteMode(Enum):
    """Enumeration of supported write modes."""
    APPEND = "append"
    OVERWRITE = "overwrite"
    UPSERT = "upsert"


@dataclass(frozen=True)
class DataSink:
    """Immutable data structure representing a configured data sink."""
    sink_id: str
    sink_type: SinkType
    location: str
    format: str
    write_mode: WriteMode
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class WriteResult:
    """Result of a write operation."""
    success: bool
    records_written: int = 0
    errors: List[str] = field(default_factory=list)
    duration_ms: float = 0.0


class DataSinkManager:
    """
    Thread-safe manager for data sinks.

    Supports writing to files, memory buffers, and console.
    Provides batch buffering with configurable flush interval
    and per-sink error tracking.
    """

    # Default buffer size before auto-flush
    DEFAULT_BUFFER_SIZE: int = 100
    # Default flush interval in seconds
    DEFAULT_FLUSH_INTERVAL: float = 5.0

    def __init__(self) -> None:
        """Initialize the DataSinkManager."""
        self._sinks: Dict[str, DataSink] = {}
        self._buffers: Dict[str, List[Dict[str, Any]]] = {}
        self._lock: RLock = RLock()
        # Error tracking per sink: sink_id -> list of error messages
        self._error_logs: Dict[str, List[str]] = {}
        # Write statistics per sink
        self._statistics: Dict[str, Dict[str, Any]] = {}
        # Buffer configuration per sink
        self._buffer_config: Dict[str, Dict[str, Any]] = {}

    def register_sink(
        self,
        sink_type: SinkType,
        location: str,
        format: str,
        write_mode: WriteMode,
        metadata: Optional[Dict[str, Any]] = None,
        buffer_size: Optional[int] = None,
        flush_interval: Optional[float] = None,
    ) -> str:
        """
        Register a new data sink.

        Args:
            sink_type: Type of the sink.
            location: Target location (file path, URL, etc.).
            format: Data format (json, csv, etc.).
            write_mode: Write mode (append, overwrite, upsert).
            metadata: Optional metadata dictionary.
            buffer_size: Optional buffer size for batching.
            flush_interval: Optional flush interval in seconds.

        Returns:
            sink_id: Unique identifier for the registered sink.
        """
        sink_id = str(uuid.uuid4())
        if metadata is None:
            metadata = {}

        sink = DataSink(
            sink_id=sink_id,
            sink_type=sink_type,
            location=location,
            format=format,
            write_mode=write_mode,
            metadata=metadata,
        )

        with self._lock:
            self._sinks[sink_id] = sink
            self._buffers[sink_id] = []
            self._error_logs[sink_id] = []
            self._statistics[sink_id] = {
                "total_writes": 0,
                "total_records": 0,
                "total_errors": 0,
                "last_write_time": None,
                "last_flush_time": None,
            }
            self._buffer_config[sink_id] = {
                "buffer_size": buffer_size if buffer_size is not None else self.DEFAULT_BUFFER_SIZE,
                "flush_interval": flush_interval if flush_interval is not None else self.DEFAULT_FLUSH_INTERVAL,
                "last_flush_time": time.time(),
            }

        return sink_id

    def unregister_sink(self, sink_id: str) -> bool:
        """
        Unregister a data sink.

        Args:
            sink_id: Unique identifier of the sink.

        Returns:
            True if the sink was found and removed, False otherwise.
        """
        with self._lock:
            if sink_id not in self._sinks:
                return False
            # Flush remaining buffered data before removal
            self._flush_unlocked(sink_id)
            del self._sinks[sink_id]
            del self._buffers[sink_id]
            del self._error_logs[sink_id]
            del self._statistics[sink_id]
            del self._buffer_config[sink_id]
            return True

    def get_sink(self, sink_id: str) -> Optional[DataSink]:
        """
        Retrieve a data sink by ID.

        Args:
            sink_id: Unique identifier of the sink.

        Returns:
            DataSink if found, None otherwise.
        """
        with self._lock:
            return self._sinks.get(sink_id)

    def write(self, sink_id: str, data: Dict[str, Any]) -> WriteResult:
        """
        Write a single record to the specified sink.

        Args:
            sink_id: Unique identifier of the sink.
            data: Record to write.

        Returns:
            WriteResult indicating success or failure.
        """
        return self.write_batch(sink_id, [data])

    def write_batch(self, sink_id: str, records: List[Dict[str, Any]]) -> WriteResult:
        """
        Write a batch of records to the specified sink.

        Args:
            sink_id: Unique identifier of the sink.
            records: List of records to write.

        Returns:
            WriteResult indicating success or failure.
        """
        start_time = time.time()
        errors: List[str] = []
        records_written = 0

        with self._lock:
            if sink_id not in self._sinks:
                duration_ms = (time.time() - start_time) * 1000
                return WriteResult(
                    success=False,
                    records_written=0,
                    errors=[f"Sink '{sink_id}' not found."],
                    duration_ms=duration_ms,
                )

            sink = self._sinks[sink_id]
            config = self._buffer_config[sink_id]

            # For MEMORY and CONSOLE sinks, write immediately
            if sink.sink_type in (SinkType.MEMORY, SinkType.CONSOLE):
                result = self._write_immediately_unlocked(sink, records)
                self._update_statistics(sink_id, result.records_written, result.errors)
                return result

            # Buffer records for FILE, DATABASE, API, QUEUE
            self._buffers[sink_id].extend(records)
            records_written = len(records)

            # Check if buffer should be flushed
            should_flush = (
                len(self._buffers[sink_id]) >= config["buffer_size"]
                or (time.time() - config["last_flush_time"]) >= config["flush_interval"]
            )

            if should_flush:
                flush_result = self._flush_unlocked(sink_id)
                errors.extend(flush_result.errors)
                records_written = flush_result.records_written
            else:
                # Update statistics for buffered records
                self._statistics[sink_id]["total_records"] += len(records)
                self._statistics[sink_id]["total_writes"] += 1
                self._statistics[sink_id]["last_write_time"] = datetime.utcnow().isoformat()

        duration_ms = (time.time() - start_time) * 1000
        return WriteResult(
            success=len(errors) == 0,
            records_written=records_written,
            errors=errors,
            duration_ms=duration_ms,
        )

    def flush(self, sink_id: str) -> WriteResult:
        """
        Flush buffered records for the specified sink.

        Args:
            sink_id: Unique identifier of the sink.

        Returns:
            WriteResult indicating success or failure.
        """
        start_time = time.time()
        with self._lock:
            if sink_id not in self._sinks:
                duration_ms = (time.time() - start_time) * 1000
                return WriteResult(
                    success=False,
                    records_written=0,
                    errors=[f"Sink '{sink_id}' not found."],
                    duration_ms=duration_ms,
                )
            result = self._flush_unlocked(sink_id)
        return result

    def get_all_sinks(self) -> List[DataSink]:
        """
        Retrieve all registered sinks.

        Returns:
            List of all DataSink instances.
        """
        with self._lock:
            return list(self._sinks.values())

    def get_sinks_by_type(self, sink_type: SinkType) -> List[DataSink]:
        """
        Retrieve sinks filtered by type.

        Args:
            sink_type: Type of sinks to retrieve.

        Returns:
            List of DataSink instances matching the type.
        """
        with self._lock:
            return [sink for sink in self._sinks.values() if sink.sink_type == sink_type]

    def health_check(self, sink_id: str) -> bool:
        """
        Perform a health check on the specified sink.

        Args:
            sink_id: Unique identifier of the sink.

        Returns:
            True if the sink is healthy, False otherwise.
        """
        with self._lock:
            if sink_id not in self._sinks:
                return False

            sink = self._sinks[sink_id]
            error_count = len(self._error_logs[sink_id])
            stats = self._statistics[sink_id]

            # Health criteria: no recent errors and sink is registered
            # A sink is considered unhealthy if it has more than 10 errors
            if error_count > 10:
                return False

            # For FILE sinks, verify the directory exists
            if sink.sink_type == SinkType.FILE:
                dir_path = os.path.dirname(sink.location)
                if dir_path and not os.path.isdir(dir_path):
                    return False

            # For MEMORY sinks, verify buffer exists
            if sink.sink_type == SinkType.MEMORY:
                return sink_id in self._buffers

            return True

    def get_statistics(self) -> Dict[str, Any]:
        """
        Retrieve statistics for all sinks.

        Returns:
            Dictionary mapping sink_id to its statistics.
        """
        with self._lock:
            return {
                sink_id: {
                    **stats,
                    "error_count": len(self._error_logs[sink_id]),
                    "buffer_size": len(self._buffers[sink_id]),
                    "sink_type": self._sinks[sink_id].sink_type.value,
                }
                for sink_id, stats in self._statistics.items()
            }

    def _write_immediately_unlocked(
        self, sink: DataSink, records: List[Dict[str, Any]]
    ) -> WriteResult:
        """
        Write records immediately without buffering.

        Must be called while holding self._lock.

        Args:
            sink: Target DataSink.
            records: Records to write.

        Returns:
            WriteResult.
        """
        start_time = time.time()
        errors: List[str] = []
        records_written = 0

        try:
            if sink.sink_type == SinkType.CONSOLE:
                for record in records:
                    print(json.dumps(record, ensure_ascii=False, default=str))
                records_written = len(records)
            elif sink.sink_type == SinkType.MEMORY:
                # Memory sinks store data in the buffer as the persistent store
                self._buffers[sink.sink_id].extend(records)
                records_written = len(records)
            else:
                errors.append(f"Immediate write not supported for sink type '{sink.sink_type.value}'.")
        except Exception as exc:
            errors.append(str(exc))
            self._error_logs[sink.sink_id].append(str(exc))

        duration_ms = (time.time() - start_time) * 1000
        return WriteResult(
            success=len(errors) == 0,
            records_written=records_written,
            errors=errors,
            duration_ms=duration_ms,
        )

    def _flush_unlocked(self, sink_id: str) -> WriteResult:
        """
        Flush buffered records for a sink.

        Must be called while holding self._lock.

        Args:
            sink_id: Unique identifier of the sink.

        Returns:
            WriteResult.
        """
        start_time = time.time()
        errors: List[str] = []
        records_written = 0

        sink = self._sinks[sink_id]
        buffer = self._buffers[sink_id]
        config = self._buffer_config[sink_id]

        if not buffer:
            duration_ms = (time.time() - start_time) * 1000
            return WriteResult(success=True, records_written=0, errors=[], duration_ms=duration_ms)

        try:
            if sink.sink_type == SinkType.FILE:
                records_written = self._write_to_file(sink, buffer)
            elif sink.sink_type == SinkType.CONSOLE:
                for record in buffer:
                    print(json.dumps(record, ensure_ascii=False, default=str))
                records_written = len(buffer)
            elif sink.sink_type == SinkType.MEMORY:
                # Memory sink: data is already in buffer, just mark as written
                records_written = len(buffer)
            elif sink.sink_type == SinkType.DATABASE:
                # Placeholder for database write
                records_written = len(buffer)
            elif sink.sink_type == SinkType.API:
                # Placeholder for API write
                records_written = len(buffer)
            elif sink.sink_type == SinkType.QUEUE:
                # Placeholder for queue write
                records_written = len(buffer)
            else:
                errors.append(f"Unknown sink type '{sink.sink_type.value}'.")
        except Exception as exc:
            errors.append(str(exc))
            self._error_logs[sink_id].append(str(exc))

        # Clear buffer on successful flush, or keep on error
        if len(errors) == 0:
            self._buffers[sink_id] = []
            config["last_flush_time"] = time.time()
        else:
            # On error, keep unwritten records in buffer
            pass

        self._update_statistics(sink_id, records_written, errors)

        duration_ms = (time.time() - start_time) * 1000
        return WriteResult(
            success=len(errors) == 0,
            records_written=records_written,
            errors=errors,
            duration_ms=duration_ms,
        )

    def _write_to_file(self, sink: DataSink, records: List[Dict[str, Any]]) -> int:
        """
        Write records to a file sink.

        Args:
            sink: Target DataSink.
            records: Records to write.

        Returns:
            Number of records written.
        """
        if sink.write_mode == WriteMode.OVERWRITE:
            mode = "w"
        else:
            mode = "a"

        # Ensure directory exists
        dir_path = os.path.dirname(sink.location)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        lines_written = 0
        with open(sink.location, mode, encoding="utf-8") as f:
            for record in records:
                if sink.format.lower() == "json":
                    f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
                elif sink.format.lower() == "jsonl":
                    f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
                else:
                    f.write(str(record) + "\n")
                lines_written += 1

        return lines_written

    def _update_statistics(self, sink_id: str, records_written: int, errors: List[str]) -> None:
        """
        Update statistics for a sink.

        Must be called while holding self._lock.

        Args:
            sink_id: Unique identifier of the sink.
            records_written: Number of records written.
            errors: List of error messages.
        """
        self._statistics[sink_id]["total_writes"] += 1
        self._statistics[sink_id]["total_records"] += records_written
        self._statistics[sink_id]["total_errors"] += len(errors)
        self._statistics[sink_id]["last_write_time"] = datetime.utcnow().isoformat()
        if records_written > 0:
            self._statistics[sink_id]["last_flush_time"] = datetime.utcnow().isoformat()


# Global singleton instance
_data_sink_manager_instance: Optional[DataSinkManager] = None
# Lock for double-checked locking
_singleton_lock: RLock = RLock()


def get_data_sink_manager() -> DataSinkManager:
    """
    Get the global DataSinkManager singleton.

    Uses double-checked locking for thread-safe initialization.

    Returns:
        The global DataSinkManager instance.
    """
    global _data_sink_manager_instance
    if _data_sink_manager_instance is None:
        with _singleton_lock:
            if _data_sink_manager_instance is None:
                _data_sink_manager_instance = DataSinkManager()
    return _data_sink_manager_instance


def reset_data_sink_manager() -> None:
    """
    Reset the global DataSinkManager singleton.

    This is primarily intended for testing purposes.
    """
    global _data_sink_manager_instance
    with _singleton_lock:
        _data_sink_manager_instance = None
