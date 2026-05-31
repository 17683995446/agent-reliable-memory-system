"""
身份认证器 - 阶段206-208

功能：
- 阶段206: 多因素认证(MFA)
- 阶段207: 令牌管理
- 阶段208: 会话控制

设计原则：
- 确定性规则，无模型依赖
- 最小层级，无循环依赖
- 线程安全，RLock保护
- 单例模式，全局唯一
"""

import threading
import time
import hashlib
import hmac
import secrets
import base64
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Dict, List, Optional, Callable, Any, Set, Tuple
from collections import deque, defaultdict
import uuid
import re


class AuthMethod(Enum):
    """认证方式"""
    PASSWORD = "password"
    TOKEN = "token"
    API_KEY = "api_key"
    MFA_TOTP = "mfa_totp"
    MFA_SMS = "mfa_sms"
    MFA_EMAIL = "mfa_email"
    OAUTH2 = "oauth2"
    LDAP = "ldap"
    SAML = "saml"


class TokenType(Enum):
    """令牌类型"""
    ACCESS = "access"
    REFRESH = "refresh"
    TEMPORARY = "temporary"
    API_KEY = "api_key"
    RESET = "reset"


class SessionStatus(Enum):
    """会话状态"""
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    SUSPENDED = "suspended"


class MFAType(Enum):
    """MFA类型"""
    TOTP = "totp"           # 基于时间的一次性密码
    SMS = "sms"             # 短信验证码
    EMAIL = "email"         # 邮件验证码
    BACKUP_CODES = "backup" # 备用码


@dataclass
class UserCredentials:
    """用户凭证"""
    user_id: str
    username: str
    password_hash: str = ""
    salt: str = ""
    mfa_enabled: bool = False
    mfa_type: Optional[MFAType] = None
    mfa_secret: str = ""
    backup_codes: List[str] = field(default_factory=list)
    failed_attempts: int = 0
    locked_until: Optional[float] = None
    last_login: Optional[float] = None
    created_at: float = field(default_factory=time.time)


@dataclass
class AuthToken:
    """认证令牌"""
    token_id: str
    user_id: str
    token_type: TokenType
    token_hash: str
    expires_at: float
    created_at: float
    last_used: Optional[float] = None
    use_count: int = 0
    max_uses: Optional[int] = None
    revoked: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Session:
    """用户会话"""
    session_id: str
    user_id: str
    token_id: str
    status: SessionStatus
    created_at: float
    expires_at: float
    last_activity: float
    ip_address: str = ""
    user_agent: str = ""
    device_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MFAChallenge:
    """MFA挑战"""
    challenge_id: str
    user_id: str
    mfa_type: MFAType
    code: str
    expires_at: float
    used: bool = False
    attempts: int = 0
    max_attempts: int = 3


@dataclass
class AuthResult:
    """认证结果"""
    success: bool
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    token: Optional[AuthToken] = None
    mfa_required: bool = False
    mfa_challenge_id: Optional[str] = None
    message: str = ""
    error_code: Optional[str] = None


class Authenticator:
    """
    身份认证器
    
    阶段206: 多因素认证(MFA)
    - TOTP基于时间的一次性密码
    - 短信/邮件验证码
    - 备用恢复码
    
    阶段207: 令牌管理
    - 访问令牌/刷新令牌
    - API密钥管理
    - 令牌生命周期控制
    
    阶段208: 会话控制
    - 会话创建与维护
    - 会话超时与续期
    - 并发会话限制
    """
    
    _instance = None
    _lock = threading.RLock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        with self._lock:
            if self._initialized:
                return
            
            self._initialized = True
            
            # 用户凭证存储
            self._credentials: Dict[str, UserCredentials] = {}
            self._username_index: Dict[str, str] = {}  # username -> user_id
            
            # 令牌管理
            self._tokens: Dict[str, AuthToken] = {}
            self._token_hash_index: Dict[str, str] = {}  # token_hash -> token_id
            
            # 会话管理
            self._sessions: Dict[str, Session] = {}
            self._user_sessions: Dict[str, Set[str]] = defaultdict(set)
            
            # MFA挑战
            self._mfa_challenges: Dict[str, MFAChallenge] = {}
            
            # 配置
            self._config = {
                "access_token_ttl": 3600,        # 1小时
                "refresh_token_ttl": 604800,     # 7天
                "session_ttl": 86400,            # 24小时
                "max_sessions_per_user": 5,
                "max_failed_attempts": 5,
                "lockout_duration": 900,         # 15分钟
                "password_min_length": 8,
                "require_uppercase": True,
                "require_lowercase": True,
                "require_digits": True,
                "require_special": False,
            }
            
            # 清理线程
            self._cleanup_thread: Optional[threading.Thread] = None
            self._cleanup_running = False
            self._cleanup_interval = 300  # 5分钟
    
    # ========== 阶段206: 多因素认证 ==========
    
    def register_user(self, username: str, password: str,
                     user_id: Optional[str] = None) -> Optional[UserCredentials]:
        """注册用户"""
        # 验证密码强度
        if not self._validate_password_strength(password):
            return None
        
        with self._lock:
            # 检查用户名是否已存在
            if username in self._username_index:
                return None
            
            user_id = user_id or str(uuid.uuid4())
            salt = secrets.token_hex(16)
            password_hash = self._hash_password(password, salt)
            
            credentials = UserCredentials(
                user_id=user_id,
                username=username,
                password_hash=password_hash,
                salt=salt
            )
            
            self._credentials[user_id] = credentials
            self._username_index[username] = user_id
            
            return credentials
    
    def _validate_password_strength(self, password: str) -> bool:
        """验证密码强度"""
        if len(password) < self._config["password_min_length"]:
            return False
        
        if self._config["require_uppercase"] and not re.search(r'[A-Z]', password):
            return False
        
        if self._config["require_lowercase"] and not re.search(r'[a-z]', password):
            return False
        
        if self._config["require_digits"] and not re.search(r'\d', password):
            return False
        
        if self._config["require_special"] and not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            return False
        
        return True
    
    def _hash_password(self, password: str, salt: str) -> str:
        """哈希密码"""
        return hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        ).hex()
    
    def setup_mfa(self, user_id: str, mfa_type: MFAType) -> Optional[Dict[str, str]]:
        """设置MFA"""
        with self._lock:
            creds = self._credentials.get(user_id)
            if not creds:
                return None
            
            if mfa_type == MFAType.TOTP:
                # 生成TOTP密钥
                secret = base64.b32encode(secrets.token_bytes(20)).decode('utf-8')
                creds.mfa_secret = secret
                creds.mfa_type = mfa_type
                creds.mfa_enabled = True
                
                # 生成备用码
                creds.backup_codes = [
                    secrets.token_hex(4) for _ in range(10)
                ]
                
                return {
                    "secret": secret,
                    "backup_codes": creds.backup_codes
                }
            
            elif mfa_type in (MFAType.SMS, MFAType.EMAIL):
                creds.mfa_type = mfa_type
                creds.mfa_enabled = True
                return {}
            
            return None
    
    def verify_mfa(self, user_id: str, code: str,
                   challenge_id: Optional[str] = None) -> bool:
        """验证MFA码"""
        with self._lock:
            creds = self._credentials.get(user_id)
            if not creds or not creds.mfa_enabled:
                return False
            
            # 检查是否是备用码
            if code in creds.backup_codes:
                creds.backup_codes.remove(code)
                return True
            
            if creds.mfa_type == MFAType.TOTP:
                return self._verify_totp(creds.mfa_secret, code)
            
            elif challenge_id and challenge_id in self._mfa_challenges:
                challenge = self._mfa_challenges[challenge_id]
                if challenge.user_id != user_id:
                    return False
                
                if challenge.used or time.time() > challenge.expires_at:
                    return False
                
                if challenge.attempts >= challenge.max_attempts:
                    return False
                
                challenge.attempts += 1
                
                if challenge.code == code:
                    challenge.used = True
                    return True
            
            return False
    
    def _verify_totp(self, secret: str, code: str, window: int = 1) -> bool:
        """验证TOTP码"""
        import struct
        
        try:
            key = base64.b32decode(secret.upper())
            current_time = int(time.time()) // 30
            
            for offset in range(-window, window + 1):
                counter = struct.pack('>Q', current_time + offset)
                mac = hmac.new(key, counter, hashlib.sha1).digest()
                offset_byte = mac[-1] & 0x0f
                binary = struct.unpack('>I', mac[offset_byte:offset_byte + 4])[0]
                binary &= 0x7fffffff
                expected_code = binary % 1000000
                
                if f"{expected_code:06d}" == code:
                    return True
            
            return False
        except Exception:
            return False
    
    def generate_totp_code(self, secret: str) -> str:
        """生成TOTP码（用于测试）"""
        import struct
        
        key = base64.b32decode(secret.upper())
        current_time = int(time.time()) // 30
        counter = struct.pack('>Q', current_time)
        mac = hmac.new(key, counter, hashlib.sha1).digest()
        offset_byte = mac[-1] & 0x0f
        binary = struct.unpack('>I', mac[offset_byte:offset_byte + 4])[0]
        binary &= 0x7fffffff
        return f"{binary % 1000000:06d}"
    
    def create_mfa_challenge(self, user_id: str,
                            mfa_type: MFAType) -> Optional[MFAChallenge]:
        """创建MFA挑战"""
        code = secrets.token_hex(3) if mfa_type == MFAType.BACKUP_CODES else \
               f"{secrets.randbelow(1000000):06d}"
        
        challenge = MFAChallenge(
            challenge_id=str(uuid.uuid4()),
            user_id=user_id,
            mfa_type=mfa_type,
            code=code,
            expires_at=time.time() + 300  # 5分钟有效期
        )
        
        with self._lock:
            self._mfa_challenges[challenge.challenge_id] = challenge
        
        return challenge
    
    # ========== 阶段207: 令牌管理 ==========
    
    def create_token(self, user_id: str, token_type: TokenType,
                     ttl_seconds: Optional[int] = None,
                     max_uses: Optional[int] = None,
                     metadata: Optional[Dict[str, Any]] = None) -> AuthToken:
        """创建令牌"""
        token_value = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token_value.encode()).hexdigest()
        
        if ttl_seconds is None:
            if token_type == TokenType.ACCESS:
                ttl_seconds = self._config["access_token_ttl"]
            elif token_type == TokenType.REFRESH:
                ttl_seconds = self._config["refresh_token_ttl"]
            else:
                ttl_seconds = 3600
        
        token = AuthToken(
            token_id=str(uuid.uuid4()),
            user_id=user_id,
            token_type=token_type,
            token_hash=token_hash,
            expires_at=time.time() + ttl_seconds,
            created_at=time.time(),
            max_uses=max_uses,
            metadata=metadata or {}
        )
        
        with self._lock:
            self._tokens[token.token_id] = token
            self._token_hash_index[token_hash] = token.token_id
        
        # 返回包含原始值的token对象（仅这一次）
        token_with_value = AuthToken(
            token_id=token.token_id,
            user_id=token.user_id,
            token_type=token.token_type,
            token_hash=token_value,  # 原始值
            expires_at=token.expires_at,
            created_at=token.created_at,
            max_uses=token.max_uses,
            metadata=token.metadata
        )
        
        return token_with_value
    
    def verify_token(self, token_value: str) -> Optional[AuthToken]:
        """验证令牌"""
        token_hash = hashlib.sha256(token_value.encode()).hexdigest()
        
        with self._lock:
            token_id = self._token_hash_index.get(token_hash)
            if not token_id:
                return None
            
            token = self._tokens.get(token_id)
            if not token:
                return None
            
            # 检查是否过期
            if time.time() > token.expires_at:
                return None
            
            # 检查是否撤销
            if token.revoked:
                return None
            
            # 检查使用次数
            if token.max_uses and token.use_count >= token.max_uses:
                return None
            
            # 更新使用信息
            token.use_count += 1
            token.last_used = time.time()
            
            return token
    
    def revoke_token(self, token_id: str) -> bool:
        """撤销令牌"""
        with self._lock:
            token = self._tokens.get(token_id)
            if token:
                token.revoked = True
                return True
            return False
    
    def revoke_all_user_tokens(self, user_id: str, token_type: Optional[TokenType] = None) -> int:
        """撤销用户的所有令牌"""
        count = 0
        
        with self._lock:
            for token in self._tokens.values():
                if token.user_id == user_id:
                    if token_type is None or token.token_type == token_type:
                        token.revoked = True
                        count += 1
        
        return count
    
    def refresh_access_token(self, refresh_token_value: str) -> Optional[AuthToken]:
        """刷新访问令牌"""
        refresh_token = self.verify_token(refresh_token_value)
        
        if not refresh_token or refresh_token.token_type != TokenType.REFRESH:
            return None
        
        # 创建新的访问令牌
        return self.create_token(
            refresh_token.user_id,
            TokenType.ACCESS
        )
    
    def create_api_key(self, user_id: str, name: str,
                      expires_days: int = 365) -> AuthToken:
        """创建API密钥"""
        return self.create_token(
            user_id,
            TokenType.API_KEY,
            ttl_seconds=expires_days * 86400,
            metadata={"name": name}
        )
    
    # ========== 阶段208: 会话控制 ==========
    
    def authenticate(self, username: str, password: str,
                    ip_address: str = "",
                    user_agent: str = "") -> AuthResult:
        """用户认证"""
        with self._lock:
            user_id = self._username_index.get(username)
            if not user_id:
                return AuthResult(
                    success=False,
                    message="Invalid username or password",
                    error_code="INVALID_CREDENTIALS"
                )
            
            creds = self._credentials.get(user_id)
            if not creds:
                return AuthResult(
                    success=False,
                    message="Invalid username or password",
                    error_code="INVALID_CREDENTIALS"
                )
            
            # 检查账户是否锁定
            if creds.locked_until and time.time() < creds.locked_until:
                return AuthResult(
                    success=False,
                    message="Account is locked",
                    error_code="ACCOUNT_LOCKED"
                )
            
            # 验证密码
            password_hash = self._hash_password(password, creds.salt)
            if password_hash != creds.password_hash:
                creds.failed_attempts += 1
                
                # 检查是否需要锁定
                if creds.failed_attempts >= self._config["max_failed_attempts"]:
                    creds.locked_until = time.time() + self._config["lockout_duration"]
                    return AuthResult(
                        success=False,
                        message="Account locked due to too many failed attempts",
                        error_code="ACCOUNT_LOCKED"
                    )
                
                return AuthResult(
                    success=False,
                    message="Invalid username or password",
                    error_code="INVALID_CREDENTIALS"
                )
            
            # 密码正确，重置失败计数
            creds.failed_attempts = 0
            creds.last_login = time.time()
            
            # 检查是否需要MFA
            if creds.mfa_enabled:
                challenge = self.create_mfa_challenge(user_id, creds.mfa_type)
                return AuthResult(
                    success=False,  # 需要第二步验证
                    user_id=user_id,
                    mfa_required=True,
                    mfa_challenge_id=challenge.challenge_id,
                    message="MFA verification required"
                )
            
            # 创建会话
            session = self._create_session(user_id, ip_address, user_agent)
            
            # 创建令牌
            access_token = self.create_token(user_id, TokenType.ACCESS)
            refresh_token = self.create_token(user_id, TokenType.REFRESH)
            
            return AuthResult(
                success=True,
                user_id=user_id,
                session_id=session.session_id,
                token=access_token,
                message="Authentication successful"
            )
    
    def _create_session(self, user_id: str, ip_address: str,
                       user_agent: str) -> Session:
        """创建会话"""
        # 检查并发会话限制
        with self._lock:
            user_session_ids = self._user_sessions.get(user_id, set())
            
            # 如果超过限制，移除最老的会话
            while len(user_session_ids) >= self._config["max_sessions_per_user"]:
                oldest_session_id = min(
                    user_session_ids,
                    key=lambda sid: self._sessions.get(sid, Session(
                        session_id="", user_id="", token_id="",
                        status=SessionStatus.EXPIRED,
                        created_at=time.time(),
                        expires_at=time.time(),
                        last_activity=time.time()
                    )).created_at
                )
                self._remove_session(oldest_session_id)
            
            session = Session(
                session_id=str(uuid.uuid4()),
                user_id=user_id,
                token_id="",
                status=SessionStatus.ACTIVE,
                created_at=time.time(),
                expires_at=time.time() + self._config["session_ttl"],
                last_activity=time.time(),
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            self._sessions[session.session_id] = session
            self._user_sessions[user_id].add(session.session_id)
            
            return session
    
    def _remove_session(self, session_id: str) -> bool:
        """移除会话"""
        session = self._sessions.get(session_id)
        if session:
            del self._sessions[session_id]
            self._user_sessions[session.user_id].discard(session_id)
            return True
        return False
    
    def validate_session(self, session_id: str) -> Optional[Session]:
        """验证会话"""
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            
            if session.status != SessionStatus.ACTIVE:
                return None
            
            if time.time() > session.expires_at:
                session.status = SessionStatus.EXPIRED
                return None
            
            session.last_activity = time.time()
            return session
    
    def terminate_session(self, session_id: str) -> bool:
        """终止会话"""
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.status = SessionStatus.REVOKED
                return True
            return False
    
    def terminate_all_user_sessions(self, user_id: str) -> int:
        """终止用户的所有会话"""
        count = 0
        
        with self._lock:
            session_ids = list(self._user_sessions.get(user_id, set()))
            for session_id in session_ids:
                if self.terminate_session(session_id):
                    count += 1
        
        return count
    
    def complete_mfa_auth(self, user_id: str, code: str,
                         challenge_id: str,
                         ip_address: str = "",
                         user_agent: str = "") -> AuthResult:
        """完成MFA认证"""
        if not self.verify_mfa(user_id, code, challenge_id):
            return AuthResult(
                success=False,
                message="Invalid MFA code",
                error_code="INVALID_MFA"
            )
        
        # 创建会话和令牌
        session = self._create_session(user_id, ip_address, user_agent)
        access_token = self.create_token(user_id, TokenType.ACCESS)
        refresh_token = self.create_token(user_id, TokenType.REFRESH)
        
        return AuthResult(
            success=True,
            user_id=user_id,
            session_id=session.session_id,
            token=access_token,
            message="Authentication successful"
        )
    
    def change_password(self, user_id: str, old_password: str,
                       new_password: str) -> bool:
        """修改密码"""
        if not self._validate_password_strength(new_password):
            return False
        
        with self._lock:
            creds = self._credentials.get(user_id)
            if not creds:
                return False
            
            # 验证旧密码
            old_hash = self._hash_password(old_password, creds.salt)
            if old_hash != creds.password_hash:
                return False
            
            # 更新密码
            new_salt = secrets.token_hex(16)
            creds.salt = new_salt
            creds.password_hash = self._hash_password(new_password, new_salt)
            
            # 撤销所有现有令牌
            self.revoke_all_user_tokens(user_id)
            
            return True
    
    def get_user_sessions(self, user_id: str) -> List[Session]:
        """获取用户的所有会话"""
        with self._lock:
            session_ids = self._user_sessions.get(user_id, set())
            return [
                self._sessions[sid] for sid in session_ids
                if sid in self._sessions
            ]
    
    def start_cleanup_loop(self) -> None:
        """启动清理循环"""
        with self._lock:
            if self._cleanup_running:
                return
            
            self._cleanup_running = True
            self._cleanup_thread = threading.Thread(
                target=self._cleanup_loop,
                daemon=True
            )
            self._cleanup_thread.start()
    
    def stop_cleanup_loop(self) -> None:
        """停止清理循环"""
        with self._lock:
            self._cleanup_running = False
        
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=5.0)
    
    def _cleanup_loop(self) -> None:
        """清理循环"""
        while True:
            with self._lock:
                if not self._cleanup_running:
                    break
            
            try:
                self._cleanup_expired()
            except Exception:
                pass
            
            time.sleep(self._cleanup_interval)
    
    def _cleanup_expired(self) -> None:
        """清理过期数据"""
        now = time.time()
        
        with self._lock:
            # 清理过期令牌
            expired_tokens = [
                tid for tid, token in self._tokens.items()
                if token.expires_at < now or token.revoked
            ]
            for tid in expired_tokens:
                token = self._tokens.pop(tid, None)
                if token:
                    self._token_hash_index.pop(token.token_hash, None)
            
            # 清理过期会话
            expired_sessions = [
                sid for sid, session in self._sessions.items()
                if session.expires_at < now or session.status != SessionStatus.ACTIVE
            ]
            for sid in expired_sessions:
                self._remove_session(sid)
            
            # 清理过期MFA挑战
            expired_challenges = [
                cid for cid, challenge in self._mfa_challenges.items()
                if challenge.expires_at < now or challenge.used
            ]
            for cid in expired_challenges:
                self._mfa_challenges.pop(cid, None)


# 全局单例
_authenticator_instance: Optional[Authenticator] = None
_authenticator_lock = threading.RLock()


def get_authenticator() -> Authenticator:
    """获取身份认证器全局实例"""
    global _authenticator_instance
    if _authenticator_instance is None:
        with _authenticator_lock:
            if _authenticator_instance is None:
                _authenticator_instance = Authenticator()
    return _authenticator_instance
