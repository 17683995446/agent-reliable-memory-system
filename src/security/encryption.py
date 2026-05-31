"""
Encryption Module for Agent Reliable Memory System.

Phase 35 Stage 378 - Encryption Module

Design Principles:
1. First Principles: deterministic rules, no model dependencies
2. Thread-safe using threading.RLock
3. Global singleton via get_encryption_manager() with double-checked locking
4. Use Python dataclasses for data structures, Enum for types
5. Minimal dependencies, no circular dependencies
"""

import base64
import hashlib
import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

# Try to import cryptography library for Fernet encryption
try:
    from cryptography.fernet import Fernet, InvalidToken
    FERNET_AVAILABLE = True
except ImportError:
    FERNET_AVAILABLE = False
    InvalidToken = Exception


class EncryptionAlgorithm(Enum):
    """Enumeration of supported encryption and hashing algorithms."""
    AES256 = "aes256"
    FERNET = "fernet"
    BASE64 = "base64"
    SHA256 = "sha256"
    SHA512 = "sha512"


class EncryptionMode(Enum):
    """Enumeration of encryption operation modes."""
    ENCRYPT = "encrypt"
    DECRYPT = "decrypt"
    HASH = "hash"


@dataclass
class EncryptedData:
    """
    Data class representing encrypted data.
    
    Attributes:
        algorithm: The algorithm used for encryption
        data: The encrypted data as base64-encoded string
        iv: Initialization vector (for algorithms that require it)
        metadata: Additional metadata about the encrypted data
        created_at: Timestamp when the data was encrypted
    """
    algorithm: EncryptionAlgorithm
    data: str
    iv: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert EncryptedData to dictionary representation."""
        return {
            "algorithm": self.algorithm.value,
            "data": self.data,
            "iv": self.iv,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EncryptedData":
        """Create EncryptedData from dictionary representation."""
        return cls(
            algorithm=EncryptionAlgorithm(data["algorithm"]),
            data=data["data"],
            iv=data.get("iv"),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"])
        )


@dataclass
class EncryptionKey:
    """
    Data class representing an encryption key.
    
    Attributes:
        key_id: Unique identifier for the key
        algorithm: The algorithm this key is used with
        key_bytes: The actual key bytes (base64-encoded for storage)
        created_at: Timestamp when the key was created
        expires_at: Optional timestamp when the key expires
    """
    key_id: str
    algorithm: EncryptionAlgorithm
    key_bytes: str
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    
    def is_expired(self) -> bool:
        """Check if the key has expired."""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert EncryptionKey to dictionary representation."""
        return {
            "key_id": self.key_id,
            "algorithm": self.algorithm.value,
            "key_bytes": self.key_bytes,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EncryptionKey":
        """Create EncryptionKey from dictionary representation."""
        return cls(
            key_id=data["key_id"],
            algorithm=EncryptionAlgorithm(data["algorithm"]),
            key_bytes=data["key_bytes"],
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None
        )


class EncryptionManager:
    """
    Thread-safe encryption manager for the Agent Memory System.
    
    Provides encryption, decryption, and hashing capabilities with support
    for multiple algorithms and key management.
    """
    
    def __init__(self):
        """Initialize the EncryptionManager."""
        self._keys: Dict[str, EncryptionKey] = {}
        self._default_key_id: Optional[str] = None
        self._lock: threading.RLock = threading.RLock()
        self._fernet_instances: Dict[str, Any] = {}  # Cache Fernet instances
    
    def generate_key(
        self,
        algorithm: EncryptionAlgorithm = EncryptionAlgorithm.FERNET,
        expires_in_days: Optional[int] = None
    ) -> str:
        """
        Generate a new encryption key.
        
        Args:
            algorithm: The encryption algorithm to generate a key for
            expires_in_days: Optional number of days until the key expires
            
        Returns:
            The key_id of the generated key
        """
        with self._lock:
            # Generate unique key ID
            key_id = secrets.token_urlsafe(16)
            
            # Generate key bytes based on algorithm
            if algorithm == EncryptionAlgorithm.FERNET:
                if FERNET_AVAILABLE:
                    key_bytes = Fernet.generate_key().decode('utf-8')
                else:
                    # Fallback: generate a random key for base64 encoding
                    key_bytes = base64.urlsafe_b64encode(
                        secrets.token_bytes(32)
                    ).decode('utf-8')
            elif algorithm == EncryptionAlgorithm.AES256:
                # Generate 256-bit (32 bytes) key for AES-256
                key_bytes = base64.urlsafe_b64encode(
                    secrets.token_bytes(32)
                ).decode('utf-8')
            elif algorithm == EncryptionAlgorithm.BASE64:
                # Base64 doesn't need a real key, but we generate one for consistency
                key_bytes = base64.urlsafe_b64encode(
                    secrets.token_bytes(16)
                ).decode('utf-8')
            else:
                # For hashing algorithms, generate a salt
                key_bytes = base64.urlsafe_b64encode(
                    secrets.token_bytes(32)
                ).decode('utf-8')
            
            # Calculate expiration
            expires_at = None
            if expires_in_days is not None:
                expires_at = datetime.now() + timedelta(days=expires_in_days)
            
            # Create and store the key
            key = EncryptionKey(
                key_id=key_id,
                algorithm=algorithm,
                key_bytes=key_bytes,
                created_at=datetime.now(),
                expires_at=expires_at
            )
            self._keys[key_id] = key
            
            # Cache Fernet instance if applicable
            if algorithm == EncryptionAlgorithm.FERNET and FERNET_AVAILABLE:
                try:
                    self._fernet_instances[key_id] = Fernet(key_bytes.encode('utf-8'))
                except Exception:
                    pass  # Will be created on demand
            
            # Set as default if no default exists
            if self._default_key_id is None:
                self._default_key_id = key_id
            
            return key_id
    
    def set_default_key(self, key_id: str) -> bool:
        """
        Set the default encryption key.
        
        Args:
            key_id: The key_id to set as default
            
        Returns:
            True if successful, False if key doesn't exist
        """
        with self._lock:
            if key_id not in self._keys:
                return False
            self._default_key_id = key_id
            return True
    
    def get_default_key(self) -> Optional[EncryptionKey]:
        """
        Get the default encryption key.
        
        Returns:
            The default EncryptionKey, or None if not set
        """
        with self._lock:
            if self._default_key_id is None:
                return None
            return self._keys.get(self._default_key_id)
    
    def encrypt(
        self,
        plaintext: str,
        key_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> EncryptedData:
        """
        Encrypt plaintext data.
        
        Args:
            plaintext: The data to encrypt
            key_id: Optional key_id to use (uses default if not specified)
            metadata: Optional metadata to attach to the encrypted data
            
        Returns:
            EncryptedData containing the encrypted result
            
        Raises:
            ValueError: If no key is available or key is expired
        """
        with self._lock:
            # Determine which key to use
            actual_key_id = key_id or self._default_key_id
            if actual_key_id is None:
                raise ValueError("No encryption key available")
            
            key = self._keys.get(actual_key_id)
            if key is None:
                raise ValueError(f"Key not found: {actual_key_id}")
            
            if key.is_expired():
                raise ValueError(f"Key has expired: {actual_key_id}")
            
            algorithm = key.algorithm
            iv = None
            encrypted_bytes = b""
            
            if algorithm == EncryptionAlgorithm.FERNET:
                if FERNET_AVAILABLE:
                    # Get or create Fernet instance
                    fernet = self._fernet_instances.get(actual_key_id)
                    if fernet is None:
                        fernet = Fernet(key.key_bytes.encode('utf-8'))
                        self._fernet_instances[actual_key_id] = fernet
                    
                    encrypted_bytes = fernet.encrypt(plaintext.encode('utf-8'))
                    encrypted_data = base64.urlsafe_b64encode(encrypted_bytes).decode('utf-8')
                else:
                    # Fallback to base64 with XOR obfuscation
                    key_bytes = base64.urlsafe_b64decode(key.key_bytes.encode('utf-8'))
                    plaintext_bytes = plaintext.encode('utf-8')
                    
                    # Simple XOR with key cycling
                    result = bytearray()
                    for i, byte in enumerate(plaintext_bytes):
                        result.append(byte ^ key_bytes[i % len(key_bytes)])
                    
                    iv = secrets.token_urlsafe(16)  # Add randomness
                    encrypted_data = base64.urlsafe_b64encode(bytes(result)).decode('utf-8')
            
            elif algorithm == EncryptionAlgorithm.AES256:
                # Simplified AES-like encryption using XOR with key derivation
                # Note: For production, use proper AES implementation
                key_bytes = base64.urlsafe_b64decode(key.key_bytes.encode('utf-8'))
                plaintext_bytes = plaintext.encode('utf-8')
                
                # Generate IV
                iv_bytes = secrets.token_bytes(16)
                iv = base64.urlsafe_b64encode(iv_bytes).decode('utf-8')
                
                # Derive session key from key + IV
                session_key = hashlib.sha256(key_bytes + iv_bytes).digest()
                
                # XOR encryption with session key
                result = bytearray()
                for i, byte in enumerate(plaintext_bytes):
                    result.append(byte ^ session_key[i % len(session_key)])
                
                encrypted_data = base64.urlsafe_b64encode(bytes(result)).decode('utf-8')
            
            elif algorithm == EncryptionAlgorithm.BASE64:
                # Simple base64 encoding (not secure, for obfuscation only)
                encrypted_data = base64.urlsafe_b64encode(
                    plaintext.encode('utf-8')
                ).decode('utf-8')
            
            else:
                raise ValueError(f"Encryption not supported for algorithm: {algorithm}")
            
            return EncryptedData(
                algorithm=algorithm,
                data=encrypted_data,
                iv=iv,
                metadata=metadata or {},
                created_at=datetime.now()
            )
    
    def decrypt(
        self,
        encrypted_data: EncryptedData,
        key_id: Optional[str] = None
    ) -> str:
        """
        Decrypt encrypted data.
        
        Args:
            encrypted_data: The EncryptedData to decrypt
            key_id: Optional key_id to use (uses default if not specified)
            
        Returns:
            The decrypted plaintext string
            
        Raises:
            ValueError: If decryption fails or key is not available
        """
        with self._lock:
            # Determine which key to use
            actual_key_id = key_id or self._default_key_id
            if actual_key_id is None:
                raise ValueError("No encryption key available")
            
            key = self._keys.get(actual_key_id)
            if key is None:
                raise ValueError(f"Key not found: {actual_key_id}")
            
            if key.is_expired():
                raise ValueError(f"Key has expired: {actual_key_id}")
            
            algorithm = encrypted_data.algorithm
            
            if algorithm == EncryptionAlgorithm.FERNET:
                if FERNET_AVAILABLE:
                    # Get or create Fernet instance
                    fernet = self._fernet_instances.get(actual_key_id)
                    if fernet is None:
                        fernet = Fernet(key.key_bytes.encode('utf-8'))
                        self._fernet_instances[actual_key_id] = fernet
                    
                    try:
                        encrypted_bytes = base64.urlsafe_b64decode(
                            encrypted_data.data.encode('utf-8')
                        )
                        plaintext = fernet.decrypt(encrypted_bytes).decode('utf-8')
                        return plaintext
                    except InvalidToken:
                        raise ValueError("Invalid encrypted data or wrong key")
                else:
                    # Fallback decryption (XOR)
                    key_bytes = base64.urlsafe_b64decode(key.key_bytes.encode('utf-8'))
                    encrypted_bytes = base64.urlsafe_b64decode(
                        encrypted_data.data.encode('utf-8')
                    )
                    
                    result = bytearray()
                    for i, byte in enumerate(encrypted_bytes):
                        result.append(byte ^ key_bytes[i % len(key_bytes)])
                    
                    return bytes(result).decode('utf-8')
            
            elif algorithm == EncryptionAlgorithm.AES256:
                key_bytes = base64.urlsafe_b64decode(key.key_bytes.encode('utf-8'))
                encrypted_bytes = base64.urlsafe_b64decode(
                    encrypted_data.data.encode('utf-8')
                )
                
                # Get IV
                if encrypted_data.iv is None:
                    raise ValueError("IV is required for AES256 decryption")
                iv_bytes = base64.urlsafe_b64decode(encrypted_data.iv.encode('utf-8'))
                
                # Derive session key
                session_key = hashlib.sha256(key_bytes + iv_bytes).digest()
                
                # XOR decryption
                result = bytearray()
                for i, byte in enumerate(encrypted_bytes):
                    result.append(byte ^ session_key[i % len(session_key)])
                
                return bytes(result).decode('utf-8')
            
            elif algorithm == EncryptionAlgorithm.BASE64:
                return base64.urlsafe_b64decode(
                    encrypted_data.data.encode('utf-8')
                ).decode('utf-8')
            
            else:
                raise ValueError(f"Decryption not supported for algorithm: {algorithm}")
    
    def hash_data(
        self,
        data: str,
        algorithm: EncryptionAlgorithm = EncryptionAlgorithm.SHA256,
        salt: Optional[str] = None
    ) -> str:
        """
        Hash data using the specified algorithm.
        
        Args:
            data: The data to hash
            algorithm: The hashing algorithm to use
            salt: Optional salt to add to the data
            
        Returns:
            The hex-encoded hash value
        """
        # Prepare data with optional salt
        if salt:
            data_to_hash = (data + salt).encode('utf-8')
        else:
            data_to_hash = data.encode('utf-8')
        
        if algorithm == EncryptionAlgorithm.SHA256:
            return hashlib.sha256(data_to_hash).hexdigest()
        elif algorithm == EncryptionAlgorithm.SHA512:
            return hashlib.sha512(data_to_hash).hexdigest()
        else:
            # Default to SHA256 for unsupported algorithms
            return hashlib.sha256(data_to_hash).hexdigest()
    
    def verify_hash(
        self,
        data: str,
        hash_value: str,
        algorithm: EncryptionAlgorithm = EncryptionAlgorithm.SHA256,
        salt: Optional[str] = None
    ) -> bool:
        """
        Verify that data matches a hash value.
        
        Args:
            data: The data to verify
            hash_value: The expected hash value
            algorithm: The hashing algorithm used
            salt: Optional salt that was used
            
        Returns:
            True if the hash matches, False otherwise
        """
        computed_hash = self.hash_data(data, algorithm, salt)
        return secrets.compare_digest(computed_hash, hash_value)
    
    def rotate_key(self, old_key_id: str, new_key_id: str) -> bool:
        """
        Rotate encryption keys by setting a new default key.
        
        Args:
            old_key_id: The current key to rotate from
            new_key_id: The new key to rotate to
            
        Returns:
            True if rotation was successful, False otherwise
        """
        with self._lock:
            if old_key_id not in self._keys:
                return False
            if new_key_id not in self._keys:
                return False
            
            # Verify new key is not expired
            new_key = self._keys[new_key_id]
            if new_key.is_expired():
                return False
            
            # Set new key as default
            self._default_key_id = new_key_id
            return True
    
    def delete_key(self, key_id: str) -> bool:
        """
        Delete an encryption key.
        
        Args:
            key_id: The key_id to delete
            
        Returns:
            True if deletion was successful, False if key doesn't exist
        """
        with self._lock:
            if key_id not in self._keys:
                return False
            
            # Remove key
            del self._keys[key_id]
            
            # Remove cached Fernet instance
            if key_id in self._fernet_instances:
                del self._fernet_instances[key_id]
            
            # Update default if necessary
            if self._default_key_id == key_id:
                self._default_key_id = None
                # Set a new default if available
                if self._keys:
                    self._default_key_id = next(iter(self._keys))
            
            return True
    
    def list_keys(self) -> List[str]:
        """
        List all available key IDs.
        
        Returns:
            List of key_id strings
        """
        with self._lock:
            return list(self._keys.keys())
    
    def get_key_info(self, key_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a specific key.
        
        Args:
            key_id: The key_id to get info for
            
        Returns:
            Dictionary with key information, or None if key doesn't exist
        """
        with self._lock:
            key = self._keys.get(key_id)
            if key is None:
                return None
            
            return {
                "key_id": key.key_id,
                "algorithm": key.algorithm.value,
                "created_at": key.created_at.isoformat(),
                "expires_at": key.expires_at.isoformat() if key.expires_at else None,
                "is_expired": key.is_expired(),
                "is_default": key_id == self._default_key_id
            }
    
    def clear_all_keys(self) -> None:
        """Clear all stored keys. Use with caution!"""
        with self._lock:
            self._keys.clear()
            self._fernet_instances.clear()
            self._default_key_id = None
    
    def is_fernet_available(self) -> bool:
        """Check if Fernet encryption is available."""
        return FERNET_AVAILABLE


# Global singleton instance and lock
_encryption_manager_instance: Optional[EncryptionManager] = None
_singleton_lock = threading.Lock()


def get_encryption_manager() -> EncryptionManager:
    """
    Get the global EncryptionManager singleton instance.
    
    Uses double-checked locking for thread-safe singleton pattern.
    
    Returns:
        The global EncryptionManager instance
    """
    global _encryption_manager_instance
    
    if _encryption_manager_instance is None:
        with _singleton_lock:
            if _encryption_manager_instance is None:
                _encryption_manager_instance = EncryptionManager()
    
    return _encryption_manager_instance


def reset_encryption_manager() -> None:
    """
    Reset the global EncryptionManager singleton.
    
    This is primarily useful for testing purposes.
    """
    global _encryption_manager_instance
    
    with _singleton_lock:
        if _encryption_manager_instance is not None:
            _encryption_manager_instance.clear_all_keys()
        _encryption_manager_instance = None
