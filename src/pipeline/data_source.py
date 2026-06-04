"""
Data Source module for the Agent Reliable Memory System (Stage 386).

Design Principles:
1. First Principles: deterministic rules, no model dependencies
2. Thread-safe using threading.RLock
3. Global singleton via get_data_source_manager() with double-checked locking
4. Use Python dataclasses for data structures, Enum for types
5. Minimal dependencies, no circular dependencies
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class SourceType(Enum):
    """Enumeration of supported data source types."""
    FILE = "file"
    DATABASE = "database"
    API = "api"
    STREAM = "stream"
    QUEUE = "queue"
    MEMORY = "memory"


class DataFormat(Enum):
    """Enumeration of supported data formats."""
    JSON = "json"
    CSV = "csv"
    XML = "xml"
    PARQUET = "parquet"
    RAW = "raw"


class ReadMode(Enum):
    """Enumeration of supported read modes."""
    BATCH = "batch"
    STREAM = "stream"
    POLL = "poll"


@dataclass
class DataSource:
    """Represents a registered data source."""
    source_id: str
    source_type: SourceType
    location: str
    format: DataFormat
    read_mode: ReadMode
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_read: Optional[datetime] = None


@dataclass
class DataRecord:
    """Represents a single record read from a data source."""
    record_id: str
    source_id: str
    data: Any
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


class DataSourceManager:
    """
    Thread-safe manager for data sources.

    Supports reading from files, memory, and simulated streams.
    """

    def __init__(self) -> None:
        self._sources: Dict[str, DataSource] = {}
        self._lock: threading.RLock = threading.RLock()
        # Internal storage for MEMORY and simulated STREAM/QUEUE sources
        self._memory_buffers: Dict[str, List[Any]] = {}
        # File handles for open FILE sources (source_id -> file object)
        self._file_handles: Dict[str, Any] = {}
        # Poll state tracking (source_id -> last_poll_timestamp)
        self._poll_state: Dict[str, datetime] = {}
        # Statistics counters
        self._stats: Dict[str, int] = {
            "total_sources_registered": 0,
            "total_sources_unregistered": 0,
            "total_records_read": 0,
            "total_batches_read": 0,
            "total_polls": 0,
            "total_stream_callbacks": 0,
        }

    def register_source(
        self,
        source_type: SourceType,
        location: str,
        format: DataFormat,
        read_mode: ReadMode,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Register a new data source.

        Args:
            source_type: The type of the data source.
            location: Path, URL, or identifier for the source.
            format: Expected data format.
            read_mode: How the source will be read.
            metadata: Optional metadata dictionary.

        Returns:
            The generated source_id.
        """
        with self._lock:
            source_id = str(uuid.uuid4())
            source = DataSource(
                source_id=source_id,
                source_type=source_type,
                location=location,
                format=format,
                read_mode=read_mode,
                metadata=metadata or {},
            )
            self._sources[source_id] = source
            # Initialize memory buffer from metadata if provided
            buffer_data = []
            if metadata and "data" in metadata:
                buffer_data = list(metadata["data"])
            self._memory_buffers[source_id] = buffer_data
            self._stats["total_sources_registered"] += 1
            return source_id

    def unregister_source(self, source_id: str) -> bool:
        """
        Unregister a data source.

        Args:
            source_id: The ID of the source to remove.

        Returns:
            True if the source was found and removed, False otherwise.
        """
        with self._lock:
            if source_id not in self._sources:
                return False
            del self._sources[source_id]
            self._memory_buffers.pop(source_id, None)
            self._poll_state.pop(source_id, None)
            # Close any open file handle
            fh = self._file_handles.pop(source_id, None)
            if fh is not None:
                try:
                    fh.close()
                except Exception:
                    pass
            self._stats["total_sources_unregistered"] += 1
            return True

    def get_source(self, source_id: str) -> Optional[DataSource]:
        """
        Retrieve a data source by ID.

        Args:
            source_id: The source ID.

        Returns:
            The DataSource if found, else None.
        """
        with self._lock:
            return self._sources.get(source_id)

    def read_batch(self, source_id: str, batch_size: int = 100) -> List[DataRecord]:
        """
        Read a batch of records from a data source.

        Supports FILE (open), MEMORY (list), and simulated STREAM/QUEUE sources.

        Args:
            source_id: The source ID.
            batch_size: Maximum number of records to read.

        Returns:
            A list of DataRecord objects.
        """
        records: List[DataRecord] = []
        with self._lock:
            source = self._sources.get(source_id)
            if source is None:
                return records

            source.last_read = datetime.utcnow()

            if source.source_type == SourceType.MEMORY:
                buffer = self._memory_buffers.get(source_id, [])
                batch_data = buffer[:batch_size]
                self._memory_buffers[source_id] = buffer[batch_size:]
                for item in batch_data:
                    record = DataRecord(
                        record_id=str(uuid.uuid4()),
                        source_id=source_id,
                        data=item,
                    )
                    records.append(record)

            elif source.source_type == SourceType.FILE:
                records = self._read_file_batch(source_id, source, batch_size)

            elif source.source_type in (SourceType.STREAM, SourceType.QUEUE):
                buffer = self._memory_buffers.get(source_id, [])
                batch_data = buffer[:batch_size]
                self._memory_buffers[source_id] = buffer[batch_size:]
                for item in batch_data:
                    record = DataRecord(
                        record_id=str(uuid.uuid4()),
                        source_id=source_id,
                        data=item,
                    )
                    records.append(record)

            elif source.source_type in (SourceType.DATABASE, SourceType.API):
                # Simulated batch read: return any buffered simulated data
                buffer = self._memory_buffers.get(source_id, [])
                batch_data = buffer[:batch_size]
                self._memory_buffers[source_id] = buffer[batch_size:]
                for item in batch_data:
                    record = DataRecord(
                        record_id=str(uuid.uuid4()),
                        source_id=source_id,
                        data=item,
                    )
                    records.append(record)

            self._stats["total_records_read"] += len(records)
            self._stats["total_batches_read"] += 1
            return records

    def _read_file_batch(
        self, source_id: str, source: DataSource, batch_size: int
    ) -> List[DataRecord]:
        """Internal helper to read a batch from a file source."""
        records: List[DataRecord] = []
        fh = self._file_handles.get(source_id)
        if fh is None:
            try:
                fh = open(source.location, "r", encoding="utf-8")
                self._file_handles[source_id] = fh
            except Exception:
                return records

        lines_read = 0
        while lines_read < batch_size:
            try:
                line = fh.readline()
            except Exception:
                break
            if not line:
                break
            line = line.rstrip("\n\r")
            if not line:
                continue
            data: Any = line
            if source.format == DataFormat.JSON:
                try:
                    data = json.loads(line)
                except Exception:
                    data = line
            record = DataRecord(
                record_id=str(uuid.uuid4()),
                source_id=source_id,
                data=data,
            )
            records.append(record)
            lines_read += 1

        return records

    def read_stream(self, source_id: str, callback: Callable[[DataRecord], None]) -> bool:
        """
        Read from a stream source using a callback.

        For simulated streams, drains the current memory buffer
        and invokes the callback for each record.

        Args:
            source_id: The source ID.
            callback: A callable that accepts a DataRecord.

        Returns:
            True if the source exists and the operation was attempted.
        """
        with self._lock:
            source = self._sources.get(source_id)
            if source is None:
                return False

            source.last_read = datetime.utcnow()
            buffer = self._memory_buffers.get(source_id, [])
            self._memory_buffers[source_id] = []

            for item in buffer:
                record = DataRecord(
                    record_id=str(uuid.uuid4()),
                    source_id=source_id,
                    data=item,
                )
                try:
                    callback(record)
                except Exception:
                    # Deterministic: swallow callback errors to keep pipeline stable
                    pass
                self._stats["total_stream_callbacks"] += 1

            self._stats["total_records_read"] += len(buffer)
            return True

    def poll_source(self, source_id: str) -> Optional[DataRecord]:
        """
        Poll a data source for a single record.

        Args:
            source_id: The source ID.

        Returns:
            A DataRecord if available, else None.
        """
        with self._lock:
            source = self._sources.get(source_id)
            if source is None:
                return None

            source.last_read = datetime.utcnow()
            self._poll_state[source_id] = datetime.utcnow()
            self._stats["total_polls"] += 1

            if source.source_type == SourceType.MEMORY:
                buffer = self._memory_buffers.get(source_id, [])
                if not buffer:
                    return None
                item = buffer.pop(0)
                self._stats["total_records_read"] += 1
                return DataRecord(
                    record_id=str(uuid.uuid4()),
                    source_id=source_id,
                    data=item,
                )

            if source.source_type == SourceType.FILE:
                records = self._read_file_batch(source_id, source, 1)
                if records:
                    self._stats["total_records_read"] += 1
                    return records[0]
                return None

            if source.source_type in (SourceType.STREAM, SourceType.QUEUE):
                buffer = self._memory_buffers.get(source_id, [])
                if not buffer:
                    return None
                item = buffer.pop(0)
                self._stats["total_records_read"] += 1
                return DataRecord(
                    record_id=str(uuid.uuid4()),
                    source_id=source_id,
                    data=item,
                )

            # DATABASE / API simulated poll
            buffer = self._memory_buffers.get(source_id, [])
            if not buffer:
                return None
            item = buffer.pop(0)
            self._stats["total_records_read"] += 1
            return DataRecord(
                record_id=str(uuid.uuid4()),
                source_id=source_id,
                data=item,
            )

    def get_all_sources(self) -> List[DataSource]:
        """
        Retrieve all registered data sources.

        Returns:
            A list of DataSource objects.
        """
        with self._lock:
            return list(self._sources.values())

    def get_sources_by_type(self, source_type: SourceType) -> List[DataSource]:
        """
        Retrieve data sources filtered by type.

        Args:
            source_type: The source type to filter by.

        Returns:
            A list of matching DataSource objects.
        """
        with self._lock:
            return [s for s in self._sources.values() if s.source_type == source_type]

    def update_source_metadata(self, source_id: str, metadata: Dict[str, Any]) -> bool:
        """
        Update metadata for a data source.

        Args:
            source_id: The source ID.
            metadata: New metadata dictionary (merged with existing).

        Returns:
            True if the source was found and updated, False otherwise.
        """
        with self._lock:
            source = self._sources.get(source_id)
            if source is None:
                return False
            source.metadata.update(metadata)
            return True

    def health_check(self, source_id: str) -> bool:
        """
        Check the health of a data source.

        For FILE sources, checks if the file is accessible.
        For MEMORY/STREAM/QUEUE, checks if the source is registered.
        For DATABASE/API, always returns True (simulated).

        Args:
            source_id: The source ID.

        Returns:
            True if the source appears healthy.
        """
        with self._lock:
            source = self._sources.get(source_id)
            if source is None:
                return False

            if source.source_type == SourceType.FILE:
                try:
                    with open(source.location, "r", encoding="utf-8"):
                        return True
                except Exception:
                    return False

            if source.source_type in (
                SourceType.MEMORY,
                SourceType.STREAM,
                SourceType.QUEUE,
                SourceType.DATABASE,
                SourceType.API,
            ):
                return True

            return False

    def get_statistics(self) -> Dict[str, Any]:
        """
        Retrieve manager statistics.

        Returns:
            A dictionary of statistics.
        """
        with self._lock:
            stats = dict(self._stats)
            stats["active_sources"] = len(self._sources)
            stats["memory_buffer_count"] = {
                sid: len(buf) for sid, buf in self._memory_buffers.items()
            }
            return stats

    # ------------------------------------------------------------------
    # Internal helpers for testing / simulation
    # ------------------------------------------------------------------

    def _inject_memory_data(self, source_id: str, data: List[Any]) -> bool:
        """
        Inject data into a MEMORY or simulated source buffer.

        This is intended for testing and simulation only.

        Args:
            source_id: The target source ID.
            data: List of data items to inject.

        Returns:
            True if injected successfully.
        """
        with self._lock:
            if source_id not in self._sources:
                return False
            self._memory_buffers.setdefault(source_id, []).extend(data)
            return True


# ------------------------------------------------------------------------------
# Global singleton with double-checked locking
# ------------------------------------------------------------------------------

_singleton_instance: Optional[DataSourceManager] = None
_singleton_lock: threading.Lock = threading.Lock()


def get_data_source_manager() -> DataSourceManager:
    """
    Return the global DataSourceManager singleton.

    Uses double-checked locking for thread-safe initialization.
    """
    global _singleton_instance
    if _singleton_instance is None:
        with _singleton_lock:
            if _singleton_instance is None:
                _singleton_instance = DataSourceManager()
    return _singleton_instance


def reset_data_source_manager() -> None:
    """
    Reset the global singleton instance.

    This is intended for testing only.
    """
    global _singleton_instance
    with _singleton_lock:
        _singleton_instance = None
