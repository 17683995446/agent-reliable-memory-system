"""
Network Connector module for the Agent Reliable Memory System.

Stage 381: Network Connector

Design Principles:
1. First Principles: deterministic rules, no model dependencies
2. Thread-safe using threading.RLock
3. Global singleton via get_network_connector() with double-checked locking
4. Use Python dataclasses for data structures, Enum for types
5. Minimal dependencies, no circular dependencies
"""

import socket
import http.client
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional


class ConnectionState(Enum):
    """Connection lifecycle states."""
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    RECONNECTING = auto()
    ERROR = auto()


class ConnectionType(Enum):
    """Supported network connection types."""
    TCP = auto()
    UDP = auto()
    HTTP = auto()
    WEBSOCKET = auto()
    GRPC = auto()


@dataclass
class NetworkEndpoint:
    """Represents a network endpoint configuration."""
    host: str
    port: int
    protocol: ConnectionType = ConnectionType.TCP
    timeout: float = 30.0
    retry_count: int = 3


@dataclass
class Connection:
    """Represents an active or inactive network connection."""
    connection_id: str
    endpoint: NetworkEndpoint
    state: ConnectionState = ConnectionState.DISCONNECTED
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    metadata: Dict[str, str] = field(default_factory=dict)


class NetworkConnector:
    """
    Thread-safe network connector with connection pooling.

    Supports TCP, UDP, HTTP, WebSocket, and gRPC connections.
    Uses socket for TCP/UDP and http.client for HTTP.
    Maintains a connection pool with a maximum of 100 connections.
    """

    _MAX_CONNECTIONS: int = 100

    def __init__(self, mock_mode: bool = False) -> None:
        """Initialize the NetworkConnector.
        
        Args:
            mock_mode: If True, connections are simulated without real network I/O.
        """
        self._connections: Dict[str, Connection] = {}
        self._lock: threading.RLock = threading.RLock()
        # Underlying socket/http objects stored separately to keep Connection dataclass simple
        self._sockets: Dict[str, socket.socket] = {}
        self._http_connections: Dict[str, http.client.HTTPConnection] = {}
        self._mock_mode: bool = mock_mode

    def connect(self, endpoint: NetworkEndpoint) -> Connection:
        """
        Create a new connection to the specified endpoint.

        Args:
            endpoint: The network endpoint to connect to.

        Returns:
            The created Connection object.

        Raises:
            RuntimeError: If the connection pool is full.
        """
        with self._lock:
            if len(self._connections) >= self._MAX_CONNECTIONS:
                raise RuntimeError(
                    f"Connection pool full (max {self._MAX_CONNECTIONS} connections)"
                )

            connection_id = str(uuid.uuid4())
            connection = Connection(
                connection_id=connection_id,
                endpoint=endpoint,
                state=ConnectionState.CONNECTING,
            )
            self._connections[connection_id] = connection

            try:
                if not self._mock_mode:
                    if endpoint.protocol in (ConnectionType.TCP, ConnectionType.GRPC):
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.settimeout(endpoint.timeout)
                        sock.connect((endpoint.host, endpoint.port))
                        self._sockets[connection_id] = sock
                    elif endpoint.protocol == ConnectionType.UDP:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                        sock.settimeout(endpoint.timeout)
                        self._sockets[connection_id] = sock
                    elif endpoint.protocol == ConnectionType.HTTP:
                        conn = http.client.HTTPConnection(
                            endpoint.host, endpoint.port, timeout=endpoint.timeout
                        )
                        conn.connect()
                        self._http_connections[connection_id] = conn
                    elif endpoint.protocol == ConnectionType.WEBSOCKET:
                        # WebSocket uses TCP socket as underlying transport
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.settimeout(endpoint.timeout)
                        sock.connect((endpoint.host, endpoint.port))
                        self._sockets[connection_id] = sock

                connection.state = ConnectionState.CONNECTED
                connection.last_activity = time.time()
            except Exception:
                connection.state = ConnectionState.ERROR
                raise

            return connection

    def disconnect(self, connection_id: str) -> bool:
        """
        Disconnect and remove a connection.

        Args:
            connection_id: The ID of the connection to disconnect.

        Returns:
            True if the connection was found and disconnected, False otherwise.
        """
        with self._lock:
            connection = self._connections.get(connection_id)
            if connection is None:
                return False

            self._close_underlying(connection_id)
            connection.state = ConnectionState.DISCONNECTED
            del self._connections[connection_id]
            return True

    def get_connection(self, connection_id: str) -> Optional[Connection]:
        """
        Retrieve a connection by ID.

        Args:
            connection_id: The ID of the connection.

        Returns:
            The Connection if found, None otherwise.
        """
        with self._lock:
            conn = self._connections.get(connection_id)
            if conn is not None:
                # Return a copy to avoid external mutation
                return Connection(
                    connection_id=conn.connection_id,
                    endpoint=conn.endpoint,
                    state=conn.state,
                    created_at=conn.created_at,
                    last_activity=conn.last_activity,
                    metadata=dict(conn.metadata),
                )
            return None

    def get_all_connections(self) -> List[Connection]:
        """
        Get all tracked connections.

        Returns:
            A list of all connections.
        """
        with self._lock:
            return [
                Connection(
                    connection_id=conn.connection_id,
                    endpoint=conn.endpoint,
                    state=conn.state,
                    created_at=conn.created_at,
                    last_activity=conn.last_activity,
                    metadata=dict(conn.metadata),
                )
                for conn in self._connections.values()
            ]

    def get_active_connections(self) -> List[Connection]:
        """
        Get all connections in CONNECTED state.

        Returns:
            A list of active connections.
        """
        with self._lock:
            return [
                Connection(
                    connection_id=conn.connection_id,
                    endpoint=conn.endpoint,
                    state=conn.state,
                    created_at=conn.created_at,
                    last_activity=conn.last_activity,
                    metadata=dict(conn.metadata),
                )
                for conn in self._connections.values()
                if conn.state == ConnectionState.CONNECTED
            ]

    def reconnect(self, connection_id: str) -> bool:
        """
        Reconnect an existing connection.

        Args:
            connection_id: The ID of the connection to reconnect.

        Returns:
            True if reconnection was successful, False otherwise.
        """
        with self._lock:
            connection = self._connections.get(connection_id)
            if connection is None:
                return False

            self._close_underlying(connection_id)
            connection.state = ConnectionState.RECONNECTING

            endpoint = connection.endpoint
            for attempt in range(endpoint.retry_count):
                try:
                    if endpoint.protocol in (ConnectionType.TCP, ConnectionType.GRPC):
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.settimeout(endpoint.timeout)
                        sock.connect((endpoint.host, endpoint.port))
                        self._sockets[connection_id] = sock
                    elif endpoint.protocol == ConnectionType.UDP:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                        sock.settimeout(endpoint.timeout)
                        self._sockets[connection_id] = sock
                    elif endpoint.protocol == ConnectionType.HTTP:
                        conn = http.client.HTTPConnection(
                            endpoint.host, endpoint.port, timeout=endpoint.timeout
                        )
                        conn.connect()
                        self._http_connections[connection_id] = conn
                    elif endpoint.protocol == ConnectionType.WEBSOCKET:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.settimeout(endpoint.timeout)
                        sock.connect((endpoint.host, endpoint.port))
                        self._sockets[connection_id] = sock

                    connection.state = ConnectionState.CONNECTED
                    connection.last_activity = time.time()
                    return True
                except Exception:
                    if attempt == endpoint.retry_count - 1:
                        connection.state = ConnectionState.ERROR
                        return False
                    time.sleep(0.5 * (attempt + 1))
            return False

    def send(self, connection_id: str, data: bytes) -> bool:
        """
        Send data over a connection.

        Args:
            connection_id: The ID of the connection.
            data: The raw bytes to send.

        Returns:
            True if data was sent successfully, False otherwise.
        """
        with self._lock:
            connection = self._connections.get(connection_id)
            if connection is None or connection.state != ConnectionState.CONNECTED:
                return False

            endpoint = connection.endpoint
            try:
                if endpoint.protocol in (
                    ConnectionType.TCP,
                    ConnectionType.WEBSOCKET,
                    ConnectionType.GRPC,
                ):
                    sock = self._sockets.get(connection_id)
                    if sock is None:
                        return False
                    sock.sendall(data)
                elif endpoint.protocol == ConnectionType.UDP:
                    sock = self._sockets.get(connection_id)
                    if sock is None:
                        return False
                    sock.sendto(data, (endpoint.host, endpoint.port))
                elif endpoint.protocol == ConnectionType.HTTP:
                    conn = self._http_connections.get(connection_id)
                    if conn is None:
                        return False
                    conn.request("POST", "/", body=data)
                    # Consume response to keep connection alive
                    conn.getresponse()

                connection.last_activity = time.time()
                return True
            except Exception:
                connection.state = ConnectionState.ERROR
                return False

    def receive(self, connection_id: str) -> Optional[bytes]:
        """
        Receive data from a connection.

        Args:
            connection_id: The ID of the connection.

        Returns:
            Received bytes, or None if the connection is unavailable.
        """
        with self._lock:
            connection = self._connections.get(connection_id)
            if connection is None or connection.state != ConnectionState.CONNECTED:
                return None

            endpoint = connection.endpoint
            try:
                data: Optional[bytes] = None
                if endpoint.protocol in (
                    ConnectionType.TCP,
                    ConnectionType.WEBSOCKET,
                    ConnectionType.GRPC,
                ):
                    sock = self._sockets.get(connection_id)
                    if sock is None:
                        return None
                    data = sock.recv(65536)
                elif endpoint.protocol == ConnectionType.UDP:
                    sock = self._sockets.get(connection_id)
                    if sock is None:
                        return None
                    data, _ = sock.recvfrom(65536)
                elif endpoint.protocol == ConnectionType.HTTP:
                    conn = self._http_connections.get(connection_id)
                    if conn is None:
                        return None
                    conn.request("GET", "/")
                    response = conn.getresponse()
                    data = response.read()

                if data is not None:
                    connection.last_activity = time.time()
                return data
            except Exception:
                connection.state = ConnectionState.ERROR
                return None

    def health_check(self, connection_id: str) -> bool:
        """
        Check if a connection is healthy.

        Args:
            connection_id: The ID of the connection.

        Returns:
            True if the connection is healthy, False otherwise.
        """
        with self._lock:
            connection = self._connections.get(connection_id)
            if connection is None:
                return False
            if connection.state != ConnectionState.CONNECTED:
                return False

            endpoint = connection.endpoint
            try:
                if endpoint.protocol in (
                    ConnectionType.TCP,
                    ConnectionType.WEBSOCKET,
                    ConnectionType.GRPC,
                ):
                    sock = self._sockets.get(connection_id)
                    if sock is None:
                        return False
                    # Use MSG_PEEK to check readability without consuming data
                    sock.recv(1, socket.MSG_PEEK)
                elif endpoint.protocol == ConnectionType.UDP:
                    sock = self._sockets.get(connection_id)
                    if sock is None:
                        return False
                    # UDP is connectionless; send empty packet as probe
                    sock.sendto(b"", (endpoint.host, endpoint.port))
                elif endpoint.protocol == ConnectionType.HTTP:
                    conn = self._http_connections.get(connection_id)
                    if conn is None:
                        return False
                    conn.request("HEAD", "/")
                    response = conn.getresponse()
                    if response.status >= 400:
                        return False

                connection.last_activity = time.time()
                return True
            except Exception:
                connection.state = ConnectionState.ERROR
                return False

    def cleanup_inactive(self, timeout_seconds: float = 300) -> int:
        """
        Remove connections that have been inactive longer than the timeout.

        Args:
            timeout_seconds: Inactivity threshold in seconds.

        Returns:
            Number of connections removed.
        """
        now = time.time()
        removed = 0
        with self._lock:
            to_remove = [
                cid
                for cid, conn in self._connections.items()
                if now - conn.last_activity > timeout_seconds
            ]
            for cid in to_remove:
                self._close_underlying(cid)
                del self._connections[cid]
                removed += 1
        return removed

    def _close_underlying(self, connection_id: str) -> None:
        """Close the underlying socket or HTTP connection."""
        sock = self._sockets.pop(connection_id, None)
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass

        http_conn = self._http_connections.pop(connection_id, None)
        if http_conn is not None:
            try:
                http_conn.close()
            except Exception:
                pass


# Singleton instance and lock
_network_connector_instance: Optional[NetworkConnector] = None
_network_connector_lock: threading.Lock = threading.Lock()


def get_network_connector(mock_mode: bool = False) -> NetworkConnector:
    """
    Get the global NetworkConnector singleton.

    Uses double-checked locking for thread-safe initialization.

    Args:
        mock_mode: If True, create a mock connector for testing.

    Returns:
        The global NetworkConnector instance.
    """
    global _network_connector_instance
    if _network_connector_instance is None:
        with _network_connector_lock:
            if _network_connector_instance is None:
                _network_connector_instance = NetworkConnector(mock_mode=mock_mode)
    return _network_connector_instance


def reset_network_connector() -> None:
    """
    Reset the global singleton instance.

    Primarily intended for testing purposes.
    """
    global _network_connector_instance
    with _network_connector_lock:
        if _network_connector_instance is not None:
            # Clean up any open connections
            with _network_connector_instance._lock:
                for cid in list(_network_connector_instance._connections.keys()):
                    _network_connector_instance._close_underlying(cid)
                _network_connector_instance._connections.clear()
        _network_connector_instance = None
