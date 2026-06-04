"""
Protocol Handler module for the Agent Reliable Memory System.

Stage 382: Network Protocol Handling

Design Principles:
1. First Principles: deterministic rules, no model dependencies
2. Thread-safe using threading.RLock
3. Global singleton via get_protocol_handler() with double-checked locking
4. Use Python dataclasses for data structures, Enum for types
5. Minimal dependencies, no circular dependencies
"""

import json
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional


class ProtocolType(Enum):
    """Supported protocol types for message encoding/decoding."""
    JSON = auto()
    XML = auto()
    PROTOBUF = auto()
    MESSAGEPACK = auto()
    RAW_BINARY = auto()


class MessageDirection(Enum):
    """Direction of message flow."""
    REQUEST = auto()
    RESPONSE = auto()
    NOTIFICATION = auto()


@dataclass
class ProtocolMessage:
    """Represents a structured protocol message."""
    message_id: str
    protocol: ProtocolType
    direction: MessageDirection
    headers: Dict[str, Any] = field(default_factory=dict)
    payload: Any = None
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParseResult:
    """Result of parsing raw data into a structured format."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    raw_bytes: bytes = b""


class ProtocolHandler:
    """
    Thread-safe protocol handler supporting multiple serialization formats.

    Provides parsing, serialization, validation, and conversion between
    supported protocol types. Uses a registry pattern for extensibility.
    """

    def __init__(self) -> None:
        """Initialize the protocol handler with built-in parsers and serializers."""
        self._parsers: Dict[ProtocolType, Callable[[bytes], ParseResult]] = {}
        self._serializers: Dict[ProtocolType, Callable[[Any], bytes]] = {}
        self._lock: threading.RLock = threading.RLock()

        self._register_builtin_parsers()
        self._register_builtin_serializers()

    def _register_builtin_parsers(self) -> None:
        """Register built-in parsers for JSON, XML, and raw binary."""
        self._parsers[ProtocolType.JSON] = self._parse_json
        self._parsers[ProtocolType.XML] = self._parse_xml
        self._parsers[ProtocolType.RAW_BINARY] = self._parse_raw_binary

    def _register_builtin_serializers(self) -> None:
        """Register built-in serializers for JSON, XML, and raw binary."""
        self._serializers[ProtocolType.JSON] = self._serialize_json
        self._serializers[ProtocolType.XML] = self._serialize_xml
        self._serializers[ProtocolType.RAW_BINARY] = self._serialize_raw_binary

    @staticmethod
    def _parse_json(data: bytes) -> ParseResult:
        """Parse JSON bytes into a Python object."""
        try:
            parsed = json.loads(data.decode("utf-8"))
            return ParseResult(success=True, data=parsed, raw_bytes=data)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return ParseResult(
                success=False,
                error=f"JSON parse error: {exc}",
                raw_bytes=data,
            )

    @staticmethod
    def _serialize_json(data: Any) -> bytes:
        """Serialize a Python object into JSON bytes."""
        return json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")

    @staticmethod
    def _parse_xml(data: bytes) -> ParseResult:
        """Parse XML bytes into an ElementTree Element."""
        try:
            root = ET.fromstring(data.decode("utf-8"))
            return ParseResult(success=True, data=root, raw_bytes=data)
        except (ET.ParseError, UnicodeDecodeError) as exc:
            return ParseResult(
                success=False,
                error=f"XML parse error: {exc}",
                raw_bytes=data,
            )

    @staticmethod
    def _serialize_xml(data: Any) -> bytes:
        """Serialize an ElementTree Element into XML bytes."""
        if isinstance(data, ET.Element):
            return ET.tostring(data, encoding="unicode").encode("utf-8")
        # Fallback: wrap plain data in a generic root element
        root = ET.Element("data")
        root.text = str(data)
        return ET.tostring(root, encoding="unicode").encode("utf-8")

    @staticmethod
    def _parse_raw_binary(data: bytes) -> ParseResult:
        """Pass through raw binary data without transformation."""
        return ParseResult(success=True, data=data, raw_bytes=data)

    @staticmethod
    def _serialize_raw_binary(data: Any) -> bytes:
        """Serialize data to raw binary bytes."""
        if isinstance(data, bytes):
            return data
        if isinstance(data, str):
            return data.encode("utf-8")
        return str(data).encode("utf-8")

    def parse(self, data: bytes, protocol: ProtocolType) -> ParseResult:
        """
        Parse raw bytes using the registered parser for the given protocol.

        Args:
            data: Raw byte string to parse.
            protocol: Target protocol type.

        Returns:
            ParseResult containing success status, parsed data, and any error.
        """
        with self._lock:
            parser = self._parsers.get(protocol)
            if parser is None:
                return ParseResult(
                    success=False,
                    error=f"No parser registered for protocol: {protocol.name}",
                    raw_bytes=data,
                )
            return parser(data)

    def serialize(self, data: Any, protocol: ProtocolType) -> bytes:
        """
        Serialize data into bytes using the registered serializer.

        Args:
            data: Data to serialize.
            protocol: Target protocol type.

        Returns:
            Serialized byte string.

        Raises:
            ValueError: If no serializer is registered for the protocol.
        """
        with self._lock:
            serializer = self._serializers.get(protocol)
            if serializer is None:
                raise ValueError(
                    f"No serializer registered for protocol: {protocol.name}"
                )
            return serializer(data)

    def create_message(
        self,
        data: Any,
        protocol: ProtocolType,
        direction: MessageDirection,
    ) -> ProtocolMessage:
        """
        Create a ProtocolMessage from raw data.

        Args:
            data: Payload data.
            protocol: Protocol type for the message.
            direction: Message direction.

        Returns:
            A fully constructed ProtocolMessage.
        """
        message_id = str(uuid.uuid4())
        return ProtocolMessage(
            message_id=message_id,
            protocol=protocol,
            direction=direction,
            payload=data,
            timestamp=time.time(),
        )

    def validate_message(self, message: ProtocolMessage) -> bool:
        """
        Validate a ProtocolMessage for structural correctness.

        Args:
            message: The message to validate.

        Returns:
            True if valid, False otherwise.
        """
        if not isinstance(message, ProtocolMessage):
            return False
        if not message.message_id:
            return False
        if not isinstance(message.protocol, ProtocolType):
            return False
        if not isinstance(message.direction, MessageDirection):
            return False
        if not isinstance(message.headers, dict):
            return False
        return True

    def get_supported_protocols(self) -> List[ProtocolType]:
        """
        Return a list of protocols with registered parsers and serializers.

        Returns:
            List of supported ProtocolType values.
        """
        with self._lock:
            supported = set(self._parsers.keys()) & set(self._serializers.keys())
            return list(supported)

    def register_parser(
        self,
        protocol: ProtocolType,
        parser_func: Callable[[bytes], ParseResult],
    ) -> bool:
        """
        Register a custom parser for a protocol.

        Args:
            protocol: Protocol type to register.
            parser_func: Callable that accepts bytes and returns ParseResult.

        Returns:
            True if registration succeeded, False if protocol already registered.
        """
        with self._lock:
            if protocol in self._parsers:
                return False
            self._parsers[protocol] = parser_func
            return True

    def register_serializer(
        self,
        protocol: ProtocolType,
        serializer_func: Callable[[Any], bytes],
    ) -> bool:
        """
        Register a custom serializer for a protocol.

        Args:
            protocol: Protocol type to register.
            serializer_func: Callable that accepts data and returns bytes.

        Returns:
            True if registration succeeded, False if protocol already registered.
        """
        with self._lock:
            if protocol in self._serializers:
                return False
            self._serializers[protocol] = serializer_func
            return True

    def convert(
        self,
        data: bytes,
        from_protocol: ProtocolType,
        to_protocol: ProtocolType,
    ) -> ParseResult:
        """
        Convert data from one protocol to another.

        Args:
            data: Raw bytes in the source protocol.
            from_protocol: Source protocol type.
            to_protocol: Target protocol type.

        Returns:
            ParseResult containing serialized bytes in the target protocol.
        """
        parse_result = self.parse(data, from_protocol)
        if not parse_result.success:
            return parse_result

        try:
            serialized = self.serialize(parse_result.data, to_protocol)
            return ParseResult(success=True, data=serialized, raw_bytes=serialized)
        except ValueError as exc:
            return ParseResult(
                success=False,
                error=f"Conversion serialize error: {exc}",
                raw_bytes=data,
            )

    def get_message_size(self, message: ProtocolMessage) -> int:
        """
        Calculate the serialized size of a ProtocolMessage in bytes.

        Args:
            message: The message to measure.

        Returns:
            Size in bytes of the serialized payload.
        """
        try:
            payload_bytes = self.serialize(message.payload, message.protocol)
            return len(payload_bytes)
        except ValueError:
            return 0

    def encode_headers(self, headers: Dict[str, Any]) -> bytes:
        """
        Encode a headers dictionary into bytes.

        Args:
            headers: Dictionary of header key-value pairs.

        Returns:
            UTF-8 encoded JSON representation of headers.
        """
        return json.dumps(headers, ensure_ascii=False, default=str).encode("utf-8")

    def decode_headers(self, data: bytes) -> Dict[str, Any]:
        """
        Decode bytes into a headers dictionary.

        Args:
            data: UTF-8 encoded JSON bytes.

        Returns:
            Dictionary of header key-value pairs.
        """
        try:
            return json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}


# Singleton instance and lock for double-checked locking
_protocol_handler_instance: Optional[ProtocolHandler] = None
_protocol_handler_lock: threading.Lock = threading.Lock()


def get_protocol_handler() -> ProtocolHandler:
    """
    Return the global ProtocolHandler singleton using double-checked locking.

    Returns:
        The singleton ProtocolHandler instance.
    """
    global _protocol_handler_instance
    if _protocol_handler_instance is None:
        with _protocol_handler_lock:
            if _protocol_handler_instance is None:
                _protocol_handler_instance = ProtocolHandler()
    return _protocol_handler_instance


def reset_protocol_handler() -> None:
    """
    Reset the global singleton instance.

    Intended for testing purposes to ensure a clean state.
    """
    global _protocol_handler_instance
    with _protocol_handler_lock:
        _protocol_handler_instance = None
