"""
Phase 35 Validation Tests - Security Modules (Stages 376-380)

Tests for:
- auth_manager.py (Stage 376)
- access_control.py (Stage 377)
- encryption.py (Stage 378)
- audit_logger.py (Stage 379)
- security_validator.py (Stage 380)
"""

import unittest
import time
from datetime import datetime, timedelta

# Import all security modules
from src.security import (
    # Auth Manager
    AuthMethod, AuthStatus, AuthCredentials, AuthSession, AuthManager,
    get_auth_manager, reset_auth_manager,
    # Access Control
    Permission, ResourceType, AccessDecision, PermissionRule, AccessContext,
    AccessController, get_access_controller, reset_access_controller,
    # Encryption
    EncryptionAlgorithm, EncryptionMode, EncryptedData, EncryptionKey,
    EncryptionManager, get_encryption_manager, reset_encryption_manager,
    # Audit Logger
    AuditEventType, AuditSeverity, AuditEvent, AuditLog, AuditLogger,
    get_audit_logger, reset_audit_logger,
    # Security Validator
    ValidationRule, ValidationSeverity, ValidationResult, ValidationReport,
    SecurityValidator, get_security_validator, reset_security_validator
)


class TestAuthManager(unittest.TestCase):
    """Test AuthManager module (Stage 376)"""
    
    def setUp(self):
        reset_auth_manager()
        self.manager = get_auth_manager()
    
    def test_register_user(self):
        result = self.manager.register_user("testuser", "password123")
        self.assertTrue(result)
        # Duplicate registration should fail
        result2 = self.manager.register_user("testuser", "password456")
        self.assertFalse(result2)
    
    def test_authenticate_success(self):
        self.manager.register_user("testuser", "password123")
        session = self.manager.authenticate("testuser", "password123")
        self.assertIsNotNone(session)
        # user_id is internally generated, check username in credentials
        self.assertEqual(session.status, AuthStatus.AUTHENTICATED)
    
    def test_authenticate_failure(self):
        self.manager.register_user("testuser", "password123")
        session = self.manager.authenticate("testuser", "wrongpassword")
        self.assertIsNone(session)
    
    def test_validate_session(self):
        self.manager.register_user("testuser", "password123")
        session = self.manager.authenticate("testuser", "password123")
        validated = self.manager.validate_session(session.session_id)
        self.assertIsNotNone(validated)
        self.assertEqual(validated.session_id, session.session_id)
    
    def test_logout(self):
        self.manager.register_user("testuser", "password123")
        session = self.manager.authenticate("testuser", "password123")
        result = self.manager.logout(session.session_id)
        self.assertTrue(result)
        validated = self.manager.validate_session(session.session_id)
        self.assertIsNone(validated)
    
    def test_api_key(self):
        self.manager.register_user("testuser", "password123")
        api_key = self.manager.generate_api_key("testuser")
        self.assertIsNotNone(api_key)
        session = self.manager.authenticate_api_key(api_key)
        self.assertIsNotNone(session)
        # API key authentication creates a valid session
    
    def test_change_password(self):
        self.manager.register_user("testuser", "password123")
        result = self.manager.change_password("testuser", "password123", "newpassword")
        self.assertTrue(result)
        session = self.manager.authenticate("testuser", "newpassword")
        self.assertIsNotNone(session)
    
    def test_global_singleton(self):
        manager2 = get_auth_manager()
        self.assertIs(self.manager, manager2)


class TestAccessController(unittest.TestCase):
    """Test AccessController module (Stage 377)"""
    
    def setUp(self):
        reset_access_controller()
        self.controller = get_access_controller()
    
    def test_default_roles(self):
        roles = self.controller.get_roles()
        self.assertIn("admin", roles)
        self.assertIn("user", roles)
        self.assertIn("guest", roles)
    
    def test_create_role(self):
        result = self.controller.create_role("custom_role", {Permission.READ, Permission.WRITE})
        self.assertTrue(result)
        perms = self.controller.get_role_permissions("custom_role")
        self.assertIn(Permission.READ, perms)
        self.assertIn(Permission.WRITE, perms)
    
    def test_assign_role(self):
        result = self.controller.assign_role("testuser", "admin")
        self.assertTrue(result)
        perms = self.controller.get_user_permissions("testuser")
        self.assertIn(Permission.ADMIN, perms)
    
    def test_check_access_admin(self):
        self.controller.assign_role("admin_user", "admin")
        decision = self.controller.check_access(
            "admin_user", ResourceType.MEMORY, "mem123", Permission.DELETE
        )
        self.assertEqual(decision, AccessDecision.ALLOW)
    
    def test_check_access_guest(self):
        self.controller.assign_role("guest_user", "guest")
        decision = self.controller.check_access(
            "guest_user", ResourceType.MEMORY, "mem123", Permission.READ
        )
        self.assertEqual(decision, AccessDecision.ALLOW)
        decision2 = self.controller.check_access(
            "guest_user", ResourceType.MEMORY, "mem123", Permission.WRITE
        )
        self.assertEqual(decision2, AccessDecision.DENY)
    
    def test_revoke_role(self):
        self.controller.assign_role("testuser", "admin")
        result = self.controller.revoke_role("testuser", "admin")
        self.assertTrue(result)
        perms = self.controller.get_user_permissions("testuser")
        self.assertNotIn(Permission.ADMIN, perms)
    
    def test_global_singleton(self):
        controller2 = get_access_controller()
        self.assertIs(self.controller, controller2)


class TestEncryptionManager(unittest.TestCase):
    """Test EncryptionManager module (Stage 378)"""
    
    def setUp(self):
        reset_encryption_manager()
        self.manager = get_encryption_manager()
    
    def test_generate_key(self):
        key_id = self.manager.generate_key()
        self.assertIsNotNone(key_id)
        keys = self.manager.list_keys()
        self.assertIn(key_id, keys)
    
    def test_encrypt_decrypt(self):
        key_id = self.manager.generate_key()
        self.manager.set_default_key(key_id)
        plaintext = "Hello, World!"
        encrypted = self.manager.encrypt(plaintext)
        self.assertIsNotNone(encrypted)
        decrypted = self.manager.decrypt(encrypted)
        self.assertEqual(decrypted, plaintext)
    
    def test_hash_data(self):
        data = "test data"
        hash_value = self.manager.hash_data(data, EncryptionAlgorithm.SHA256)
        self.assertIsNotNone(hash_value)
        self.assertTrue(self.manager.verify_hash(data, hash_value, EncryptionAlgorithm.SHA256))
        self.assertFalse(self.manager.verify_hash("wrong data", hash_value, EncryptionAlgorithm.SHA256))
    
    def test_set_default_key(self):
        key_id = self.manager.generate_key()
        result = self.manager.set_default_key(key_id)
        self.assertTrue(result)
        default_key = self.manager.get_default_key()
        self.assertIsNotNone(default_key)
        self.assertEqual(default_key.key_id, key_id)
    
    def test_delete_key(self):
        key_id = self.manager.generate_key()
        result = self.manager.delete_key(key_id)
        self.assertTrue(result)
        keys = self.manager.list_keys()
        self.assertNotIn(key_id, keys)
    
    def test_global_singleton(self):
        manager2 = get_encryption_manager()
        self.assertIs(self.manager, manager2)


class TestAuditLogger(unittest.TestCase):
    """Test AuditLogger module (Stage 379)"""
    
    def setUp(self):
        reset_audit_logger()
        self.logger = get_audit_logger()
    
    def test_log_event(self):
        event_id = self.logger.log_event(
            AuditEventType.LOGIN, AuditSeverity.INFO, user_id="testuser"
        )
        self.assertIsNotNone(event_id)
        event = self.logger.get_event_by_id(event_id)
        self.assertIsNotNone(event)
        self.assertEqual(event.user_id, "testuser")
    
    def test_log_login(self):
        event_id = self.logger.log_login("testuser", True, "192.168.1.1")
        event = self.logger.get_event_by_id(event_id)
        self.assertEqual(event.event_type, AuditEventType.LOGIN)
        self.assertEqual(event.user_id, "testuser")
    
    def test_log_access(self):
        event_id = self.logger.log_access(
            "testuser", ResourceType.MEMORY, "mem123", "read", True
        )
        event = self.logger.get_event_by_id(event_id)
        self.assertEqual(event.event_type, AuditEventType.ACCESS_GRANTED)
    
    def test_get_events_by_user(self):
        self.logger.log_event(AuditEventType.LOGIN, AuditSeverity.INFO, user_id="user1")
        self.logger.log_event(AuditEventType.LOGIN, AuditSeverity.INFO, user_id="user2")
        events = self.logger.get_events_by_user("user1")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].user_id, "user1")
    
    def test_get_statistics(self):
        self.logger.log_event(AuditEventType.LOGIN, AuditSeverity.INFO, user_id="testuser")
        self.logger.log_event(AuditEventType.ERROR, AuditSeverity.ERROR, user_id="testuser")
        stats = self.logger.get_statistics()
        self.assertIn('total_count', stats)
        self.assertGreaterEqual(stats['total_count'], 2)
    
    def test_clear_events(self):
        self.logger.log_event(AuditEventType.LOGIN, AuditSeverity.INFO, user_id="testuser")
        count = self.logger.clear_events()
        self.assertGreaterEqual(count, 1)
        stats = self.logger.get_statistics()
        self.assertEqual(stats['total_count'], 0)
    
    def test_global_singleton(self):
        logger2 = get_audit_logger()
        self.assertIs(self.logger, logger2)


class TestSecurityValidator(unittest.TestCase):
    """Test SecurityValidator module (Stage 380)"""
    
    def setUp(self):
        reset_security_validator()
        self.validator = get_security_validator()
    
    def test_validate_password_strong(self):
        result = self.validator.validate_password("StrongP@ss123")
        self.assertTrue(result.is_valid)
    
    def test_validate_password_weak(self):
        result = self.validator.validate_password("weak")
        self.assertFalse(result.is_valid)
    
    def test_check_sql_injection(self):
        result = self.validator.check_sql_injection("SELECT * FROM users")
        self.assertFalse(result.is_valid)
        result2 = self.validator.check_sql_injection("normal input")
        self.assertTrue(result2.is_valid)
    
    def test_check_xss(self):
        result = self.validator.check_xss("<script>alert('xss')</script>")
        self.assertFalse(result.is_valid)
        result2 = self.validator.check_xss("normal text")
        self.assertTrue(result2.is_valid)
    
    def test_check_path_traversal(self):
        result = self.validator.check_path_traversal("../../../etc/passwd")
        self.assertFalse(result.is_valid)
        result2 = self.validator.check_path_traversal("normal/path/file.txt")
        self.assertTrue(result2.is_valid)
    
    def test_check_command_injection(self):
        result = self.validator.check_command_injection("ls; rm -rf /")
        self.assertFalse(result.is_valid)
        result2 = self.validator.check_command_injection("normal command")
        self.assertTrue(result2.is_valid)
    
    def test_sanitize_input(self):
        sanitized = self.validator.sanitize_input("<script>alert('xss')</script>")
        self.assertNotIn("<script>", sanitized)
    
    def test_validate_all(self):
        report = self.validator.validate_all("SELECT * FROM users; <script>alert(1)</script>")
        self.assertFalse(report.is_valid)
        self.assertGreater(report.total_issues, 0)
    
    def test_custom_rule(self):
        def custom_validator(value):
            return ValidationResult(
                is_valid=len(value) <= 10,
                rule=ValidationRule.INPUT_SANITIZATION,
                severity=ValidationSeverity.LOW,
                message="Custom validation",
                details={}
            )
        self.validator.add_custom_rule("max_length_10", custom_validator)
        rules = self.validator.get_rules()
        self.assertIn("max_length_10", rules)
    
    def test_global_singleton(self):
        validator2 = get_security_validator()
        self.assertIs(self.validator, validator2)


class TestDataStructures(unittest.TestCase):
    """Test all data structures and enums"""
    
    def test_auth_method_enum(self):
        self.assertEqual(len(AuthMethod), 5)
        self.assertIn(AuthMethod.PASSWORD, list(AuthMethod))
        self.assertIn(AuthMethod.API_KEY, list(AuthMethod))
    
    def test_auth_status_enum(self):
        self.assertEqual(len(AuthStatus), 5)
        self.assertIn(AuthStatus.AUTHENTICATED, list(AuthStatus))
    
    def test_permission_enum(self):
        self.assertEqual(len(Permission), 6)
        self.assertIn(Permission.READ, list(Permission))
        self.assertIn(Permission.ADMIN, list(Permission))
    
    def test_resource_type_enum(self):
        self.assertEqual(len(ResourceType), 7)
        self.assertIn(ResourceType.MEMORY, list(ResourceType))
    
    def test_encryption_algorithm_enum(self):
        self.assertEqual(len(EncryptionAlgorithm), 5)
        self.assertIn(EncryptionAlgorithm.FERNET, list(EncryptionAlgorithm))
    
    def test_audit_event_type_enum(self):
        self.assertEqual(len(AuditEventType), 10)
        self.assertIn(AuditEventType.LOGIN, list(AuditEventType))
    
    def test_audit_severity_enum(self):
        self.assertEqual(len(AuditSeverity), 4)
        self.assertIn(AuditSeverity.CRITICAL, list(AuditSeverity))
    
    def test_validation_rule_enum(self):
        self.assertEqual(len(ValidationRule), 6)
        self.assertIn(ValidationRule.SQL_INJECTION, list(ValidationRule))
    
    def test_validation_severity_enum(self):
        self.assertEqual(len(ValidationSeverity), 4)
        self.assertIn(ValidationSeverity.HIGH, list(ValidationSeverity))


if __name__ == '__main__':
    unittest.main()
