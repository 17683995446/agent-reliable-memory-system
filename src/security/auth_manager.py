"""
Authentication Manager Module for Agent Reliable Memory System.
Phase 35 Stage 376

Design Principles:
1. First Principles: deterministic rules, no model dependencies
2. Thread-safe using threading.RLock
3. Global singleton via get_auth_manager() with double-checked locking
4. Use Python dataclasses for data structures, Enum for types
5. Minimal dependencies, no circular dependencies
"""

import hashlib
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any


class AuthMethod(Enum):
    """认证方法枚举"""
    PASSWORD = "password"
    TOKEN = "token"
    API_KEY = "api_key"
    OAUTH = "oauth"
    CERTIFICATE = "certificate"


class AuthStatus(Enum):
    """认证状态枚举"""
    PENDING = "pending"
    AUTHENTICATED = "authenticated"
    FAILED = "failed"
    EXPIRED = "expired"
    REVOKED = "revoked"


@dataclass
class AuthCredentials:
    """
    认证凭据数据类
    
    Attributes:
        method: 认证方法
        username: 用户名
        password: 密码（可选，用于PASSWORD方法）
        token: 令牌（可选，用于TOKEN方法）
        metadata: 元数据字典
        created_at: 创建时间
        expires_at: 过期时间（可选）
    """
    method: AuthMethod
    username: str
    password: Optional[str] = None
    token: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    
    def is_expired(self) -> bool:
        """检查凭据是否过期"""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at


@dataclass
class AuthSession:
    """
    认证会话数据类
    
    Attributes:
        session_id: 会话ID
        user_id: 用户ID
        credentials: 认证凭据
        status: 会话状态
        created_at: 创建时间
        last_activity: 最后活动时间
        expires_at: 过期时间
        metadata: 元数据字典
    """
    session_id: str
    user_id: str
    credentials: AuthCredentials
    status: AuthStatus
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    expires_at: datetime = field(default_factory=lambda: datetime.now() + timedelta(seconds=3600))
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_expired(self) -> bool:
        """检查会话是否过期"""
        return datetime.now() > self.expires_at
    
    def is_active(self) -> bool:
        """检查会话是否活跃"""
        return self.status == AuthStatus.AUTHENTICATED and not self.is_expired()
    
    def update_activity(self) -> None:
        """更新最后活动时间"""
        self.last_activity = datetime.now()


class AuthManager:
    """
    认证管理器类
    
    提供用户注册、认证、会话管理、API密钥管理等功能。
    所有操作都是线程安全的。
    
    Attributes:
        _sessions: 会话字典（session_id -> AuthSession）
        _users: 用户字典（username -> user_info）
        _api_keys: API密钥字典（api_key -> user_id）
        _lock: 线程锁
        _session_timeout: 会话超时时间（秒）
    """
    
    # 会话超时时间：1小时
    SESSION_TIMEOUT = 3600
    
    def __init__(self):
        """初始化认证管理器"""
        self._sessions: Dict[str, AuthSession] = {}
        self._users: Dict[str, Dict[str, Any]] = {}
        self._api_keys: Dict[str, str] = {}
        self._lock = threading.RLock()
        self._session_timeout = self.SESSION_TIMEOUT
    
    def _hash_password(self, password: str) -> str:
        """
        使用SHA256哈希密码
        
        Args:
            password: 明文密码
            
        Returns:
            哈希后的密码字符串
        """
        return hashlib.sha256(password.encode('utf-8')).hexdigest()
    
    def _generate_session_id(self) -> str:
        """生成唯一的会话ID"""
        return str(uuid.uuid4())
    
    def _generate_api_key(self) -> str:
        """生成唯一的API密钥"""
        return str(uuid.uuid4())
    
    def _get_current_user_id(self, username: str) -> str:
        """
        获取用户ID（使用用户名的哈希值作为用户ID）
        
        Args:
            username: 用户名
            
        Returns:
            用户ID字符串
        """
        return hashlib.sha256(username.encode('utf-8')).hexdigest()[:16]
    
    def register_user(self, username: str, password: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        注册新用户
        
        Args:
            username: 用户名
            password: 密码
            metadata: 用户元数据（可选）
            
        Returns:
            注册成功返回True，用户已存在返回False
        """
        with self._lock:
            # 检查用户是否已存在
            if username in self._users:
                return False
            
            # 创建用户信息
            user_id = self._get_current_user_id(username)
            hashed_password = self._hash_password(password)
            
            self._users[username] = {
                'user_id': user_id,
                'username': username,
                'hashed_password': hashed_password,
                'metadata': metadata or {},
                'created_at': datetime.now(),
                'is_active': True
            }
            
            return True
    
    def authenticate(self, username: str, password: str) -> Optional[AuthSession]:
        """
        使用用户名和密码认证用户
        
        Args:
            username: 用户名
            password: 密码
            
        Returns:
            认证成功返回AuthSession，失败返回None
        """
        with self._lock:
            # 检查用户是否存在
            if username not in self._users:
                return None
            
            user_info = self._users[username]
            
            # 检查用户是否活跃
            if not user_info.get('is_active', True):
                return None
            
            # 验证密码
            hashed_password = self._hash_password(password)
            if user_info['hashed_password'] != hashed_password:
                return None
            
            # 创建认证凭据
            credentials = AuthCredentials(
                method=AuthMethod.PASSWORD,
                username=username,
                metadata=user_info.get('metadata', {})
            )
            
            # 创建会话
            session_id = self._generate_session_id()
            now = datetime.now()
            expires_at = now + timedelta(seconds=self._session_timeout)
            
            session = AuthSession(
                session_id=session_id,
                user_id=user_info['user_id'],
                credentials=credentials,
                status=AuthStatus.AUTHENTICATED,
                created_at=now,
                last_activity=now,
                expires_at=expires_at,
                metadata={'auth_method': 'password'}
            )
            
            self._sessions[session_id] = session
            return session
    
    def authenticate_api_key(self, api_key: str) -> Optional[AuthSession]:
        """
        使用API密钥认证
        
        Args:
            api_key: API密钥
            
        Returns:
            认证成功返回AuthSession，失败返回None
        """
        with self._lock:
            # 检查API密钥是否有效
            if api_key not in self._api_keys:
                return None
            
            user_id = self._api_keys[api_key]
            
            # 查找对应的用户
            username = None
            user_info = None
            for uname, info in self._users.items():
                if info['user_id'] == user_id:
                    username = uname
                    user_info = info
                    break
            
            if username is None or user_info is None:
                return None
            
            # 检查用户是否活跃
            if not user_info.get('is_active', True):
                return None
            
            # 创建认证凭据
            credentials = AuthCredentials(
                method=AuthMethod.API_KEY,
                username=username,
                token=api_key,
                metadata=user_info.get('metadata', {})
            )
            
            # 创建会话
            session_id = self._generate_session_id()
            now = datetime.now()
            expires_at = now + timedelta(seconds=self._session_timeout)
            
            session = AuthSession(
                session_id=session_id,
                user_id=user_id,
                credentials=credentials,
                status=AuthStatus.AUTHENTICATED,
                created_at=now,
                last_activity=now,
                expires_at=expires_at,
                metadata={'auth_method': 'api_key', 'api_key': api_key}
            )
            
            self._sessions[session_id] = session
            return session
    
    def validate_session(self, session_id: str) -> Optional[AuthSession]:
        """
        验证会话是否有效
        
        Args:
            session_id: 会话ID
            
        Returns:
            会话有效返回AuthSession，无效返回None
        """
        with self._lock:
            if session_id not in self._sessions:
                return None
            
            session = self._sessions[session_id]
            
            # 检查会话状态
            if session.status != AuthStatus.AUTHENTICATED:
                return None
            
            # 检查是否过期
            if session.is_expired():
                session.status = AuthStatus.EXPIRED
                return None
            
            return session
    
    def refresh_session(self, session_id: str) -> Optional[AuthSession]:
        """
        刷新会话（延长过期时间）
        
        Args:
            session_id: 会话ID
            
        Returns:
            刷新成功返回AuthSession，失败返回None
        """
        with self._lock:
            session = self.validate_session(session_id)
            if session is None:
                return None
            
            # 更新过期时间和最后活动时间
            now = datetime.now()
            session.expires_at = now + timedelta(seconds=self._session_timeout)
            session.update_activity()
            
            return session
    
    def revoke_session(self, session_id: str) -> bool:
        """
        撤销会话
        
        Args:
            session_id: 会话ID
            
        Returns:
            撤销成功返回True，会话不存在返回False
        """
        with self._lock:
            if session_id not in self._sessions:
                return False
            
            self._sessions[session_id].status = AuthStatus.REVOKED
            return True
    
    def logout(self, session_id: str) -> bool:
        """
        用户登出（删除会话）
        
        Args:
            session_id: 会话ID
            
        Returns:
            登出成功返回True，会话不存在返回False
        """
        with self._lock:
            if session_id not in self._sessions:
                return False
            
            del self._sessions[session_id]
            return True
    
    def change_password(self, username: str, old_password: str, new_password: str) -> bool:
        """
        修改密码
        
        Args:
            username: 用户名
            old_password: 旧密码
            new_password: 新密码
            
        Returns:
            修改成功返回True，失败返回False
        """
        with self._lock:
            # 检查用户是否存在
            if username not in self._users:
                return False
            
            user_info = self._users[username]
            
            # 验证旧密码
            hashed_old_password = self._hash_password(old_password)
            if user_info['hashed_password'] != hashed_old_password:
                return False
            
            # 更新密码
            user_info['hashed_password'] = self._hash_password(new_password)
            user_info['password_changed_at'] = datetime.now()
            
            return True
    
    def generate_api_key(self, username: str) -> Optional[str]:
        """
        为用户生成API密钥
        
        Args:
            username: 用户名
            
        Returns:
            生成的API密钥，用户不存在返回None
        """
        with self._lock:
            # 检查用户是否存在
            if username not in self._users:
                return None
            
            user_info = self._users[username]
            user_id = user_info['user_id']
            
            # 生成新的API密钥
            api_key = self._generate_api_key()
            self._api_keys[api_key] = user_id
            
            # 记录用户的API密钥
            if 'api_keys' not in user_info:
                user_info['api_keys'] = []
            user_info['api_keys'].append(api_key)
            user_info['api_key_created_at'] = datetime.now()
            
            return api_key
    
    def revoke_api_key(self, api_key: str) -> bool:
        """
        撤销API密钥
        
        Args:
            api_key: API密钥
            
        Returns:
            撤销成功返回True，密钥不存在返回False
        """
        with self._lock:
            if api_key not in self._api_keys:
                return False
            
            user_id = self._api_keys[api_key]
            
            # 从用户信息中移除
            for username, user_info in self._users.items():
                if user_info['user_id'] == user_id:
                    if 'api_keys' in user_info and api_key in user_info['api_keys']:
                        user_info['api_keys'].remove(api_key)
                    break
            
            # 删除API密钥
            del self._api_keys[api_key]
            return True
    
    def get_active_sessions(self) -> List[AuthSession]:
        """
        获取所有活跃会话
        
        Returns:
            活跃会话列表
        """
        with self._lock:
            active_sessions = []
            for session in self._sessions.values():
                if session.is_active():
                    active_sessions.append(session)
            return active_sessions
    
    def cleanup_expired(self) -> int:
        """
        清理过期会话
        
        Returns:
            清理的会话数量
        """
        with self._lock:
            expired_session_ids = []
            
            for session_id, session in self._sessions.items():
                if session.is_expired() or session.status in (AuthStatus.EXPIRED, AuthStatus.REVOKED):
                    expired_session_ids.append(session_id)
            
            # 删除过期会话
            for session_id in expired_session_ids:
                del self._sessions[session_id]
            
            return len(expired_session_ids)
    
    def get_user_info(self, username: str) -> Optional[Dict[str, Any]]:
        """
        获取用户信息
        
        Args:
            username: 用户名
            
        Returns:
            用户信息字典，用户不存在返回None
        """
        with self._lock:
            if username not in self._users:
                return None
            # 返回副本，避免外部修改
            user_info = self._users[username].copy()
            # 不返回密码哈希
            user_info.pop('hashed_password', None)
            return user_info
    
    def deactivate_user(self, username: str) -> bool:
        """
        停用用户
        
        Args:
            username: 用户名
            
        Returns:
            停用成功返回True，用户不存在返回False
        """
        with self._lock:
            if username not in self._users:
                return False
            self._users[username]['is_active'] = False
            return True
    
    def activate_user(self, username: str) -> bool:
        """
        激活用户
        
        Args:
            username: 用户名
            
        Returns:
            激活成功返回True，用户不存在返回False
        """
        with self._lock:
            if username not in self._users:
                return False
            self._users[username]['is_active'] = True
            return True
    
    def get_session_count(self) -> int:
        """
        获取当前会话数量
        
        Returns:
            会话数量
        """
        with self._lock:
            return len(self._sessions)
    
    def get_user_count(self) -> int:
        """
        获取注册用户数量
        
        Returns:
            用户数量
        """
        with self._lock:
            return len(self._users)
    
    def get_api_key_count(self) -> int:
        """
        获取API密钥数量
        
        Returns:
            API密钥数量
        """
        with self._lock:
            return len(self._api_keys)


# 全局单例实例和锁
_auth_manager_instance: Optional[AuthManager] = None
_auth_manager_lock = threading.Lock()


def get_auth_manager() -> AuthManager:
    """
    获取认证管理器单例实例（双重检查锁定）
    
    Returns:
        AuthManager单例实例
    """
    global _auth_manager_instance
    
    if _auth_manager_instance is None:
        with _auth_manager_lock:
            if _auth_manager_instance is None:
                _auth_manager_instance = AuthManager()
    
    return _auth_manager_instance


def reset_auth_manager() -> None:
    """
    重置认证管理器单例（仅用于测试）
    """
    global _auth_manager_instance
    
    with _auth_manager_lock:
        _auth_manager_instance = None
