"""
Security Module for Agent Reliable Memory System.

This module provides comprehensive security capabilities including:
- Authentication management (Stage 376)
- Access control (Stage 377)
- Encryption (Stage 378)
- Audit logging (Stage 379)
- Security validation (Stage 380)
"""

from .auth_manager import (
    AuthMethod,
    AuthStatus,
    AuthCredentials,
    AuthSession,
    AuthManager,
    get_auth_manager,
    reset_auth_manager
)

from .access_control import (
    Permission,
    ResourceType,
    AccessDecision,
    PermissionRule,
    AccessContext,
    AccessController,
    get_access_controller,
    reset_access_controller
)

from .encryption import (
    EncryptionAlgorithm,
    EncryptionMode,
    EncryptedData,
    EncryptionKey,
    EncryptionManager,
    get_encryption_manager,
    reset_encryption_manager
)

from .audit_logger import (
    AuditEventType,
    AuditSeverity,
    AuditEvent,
    AuditLog,
    AuditLogger,
    get_audit_logger,
    reset_audit_logger
)

from .security_validator import (
    ValidationRule,
    ValidationSeverity,
    ValidationResult,
    ValidationReport,
    SecurityValidator,
    get_security_validator,
    reset_security_validator
)

__all__ = [
    # Auth Manager
    'AuthMethod',
    'AuthStatus',
    'AuthCredentials',
    'AuthSession',
    'AuthManager',
    'get_auth_manager',
    'reset_auth_manager',
    
    # Access Control
    'Permission',
    'ResourceType',
    'AccessDecision',
    'PermissionRule',
    'AccessContext',
    'AccessController',
    'get_access_controller',
    'reset_access_controller',
    
    # Encryption
    'EncryptionAlgorithm',
    'EncryptionMode',
    'EncryptedData',
    'EncryptionKey',
    'EncryptionManager',
    'get_encryption_manager',
    'reset_encryption_manager',
    
    # Audit Logger
    'AuditEventType',
    'AuditSeverity',
    'AuditEvent',
    'AuditLog',
    'AuditLogger',
    'get_audit_logger',
    'reset_audit_logger',
    
    # Security Validator
    'ValidationRule',
    'ValidationSeverity',
    'ValidationResult',
    'ValidationReport',
    'SecurityValidator',
    'get_security_validator',
    'reset_security_validator'
]
