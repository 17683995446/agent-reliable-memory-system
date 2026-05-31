"""
会话管理器

第307-308阶段：会话创建、验证、过期处理
遵循"图难于其易，为大于其细"原则，实现细粒度的会话管理
"""

import threading
import time
import secrets
import hashlib
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta


class SessionState(Enum):
    """会话状态"""
    ACTIVE = "active"           # 活跃
    EXPIRED = "expired"         # 已过期
    INVALID = "invalid"         # 无效
    DESTROYED = "destroyed"     # 已销毁


@dataclass
class Session:
    """会话对象"""
    session_id: str
    user_id: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    expires_at: float = 0.0
    state: SessionState = SessionState.ACTIVE
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    
    def is_expired(self) -> bool:
        """检查是否过期"""
        return time.time() > self.expires_at
    
    def is_valid(self) -> bool:
        """检查是否有效"""
        return self.state == SessionState.ACTIVE and not self.is_expired()
    
    def touch(self) -> None:
        """更新最后访问时间"""
        self.last_accessed = time.time()


@dataclass
class SessionConfig:
    """会话配置"""
    session_name: str = "session_id"
    secret_key: str = ""
    lifetime: int = 3600              # 默认1小时
    idle_timeout: int = 1800          # 空闲超时30分钟
    cookie_secure: bool = False
    cookie_http_only: bool = True
    cookie_same_site: str = "Lax"
    regenerate_id: bool = True        # 登录后重新生成ID
    max_sessions_per_user: int = 5


class SessionManager:
    """
    会话管理器
    
    职责：
    1. 创建和销毁会话
    2. 验证会话有效性
    3. 管理会话数据
    4. 处理会话过期
    
    设计原则：
    - 安全的会话ID生成
    - 细粒度状态管理
    - 自动清理过期会话
    """
    
    _instance: Optional['SessionManager'] = None
    _lock = threading.RLock()
    
    def __new__(cls) -> 'SessionManager':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        self._config = SessionConfig()
        self._sessions: Dict[str, Session] = {}
        self._user_sessions: Dict[str, List[str]] = {}
        
        self._lock = threading.RLock()
        self._cleanup_interval = 300  # 5分钟清理一次
        self._last_cleanup = time.time()
        
        # 生成默认密钥
        if not self._config.secret_key:
            self._config.secret_key = secrets.token_hex(32)
    
    def configure(self, **kwargs) -> None:
        """
        配置会话管理器
        
        Args:
            **kwargs: 配置参数
        """
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self._config, key):
                    setattr(self._config, key, value)
    
    def get_config(self) -> SessionConfig:
        """获取当前配置"""
        return self._config
    
    def _generate_session_id(self) -> str:
        """
        生成安全的会话ID
        
        Returns:
            会话ID字符串
        """
        # 使用加密安全的随机数生成器
        random_bytes = secrets.token_bytes(32)
        timestamp = str(time.time()).encode('utf-8')
        secret = self._config.secret_key.encode('utf-8')
        
        data = random_bytes + timestamp + secret
        session_id = hashlib.sha256(data).hexdigest()
        
        return session_id
    
    def create_session(
        self,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        lifetime: Optional[int] = None
    ) -> Session:
        """
        创建新会话
        
        Args:
            user_id: 用户ID
            ip_address: 客户端IP
            user_agent: 用户代理
            lifetime: 会话生命周期（秒）
        
        Returns:
            新创建的会话对象
        """
        with self._lock:
            self._cleanup_if_needed()
            
            session_id = self._generate_session_id()
            now = time.time()
            session_lifetime = lifetime or self._config.lifetime
            
            session = Session(
                session_id=session_id,
                user_id=user_id,
                created_at=now,
                last_accessed=now,
                expires_at=now + session_lifetime,
                state=SessionState.ACTIVE,
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            self._sessions[session_id] = session
            
            # 关联用户会话
            if user_id:
                if user_id not in self._user_sessions:
                    self._user_sessions[user_id] = []
                self._user_sessions[user_id].append(session_id)
                
                # 限制每用户最大会话数
                self._enforce_session_limit(user_id)
            
            return session
    
    def _enforce_session_limit(self, user_id: str) -> None:
        """强制执行会话数量限制"""
        if user_id not in self._user_sessions:
            return
        
        sessions = self._user_sessions[user_id]
        max_sessions = self._config.max_sessions_per_user
        
        while len(sessions) > max_sessions:
            oldest_id = sessions.pop(0)
            if oldest_id in self._sessions:
                self._sessions[oldest_id].state = SessionState.DESTROYED
                del self._sessions[oldest_id]
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """
        获取会话
        
        Args:
            session_id: 会话ID
        
        Returns:
            会话对象，不存在或无效返回None
        """
        with self._lock:
            session = self._sessions.get(session_id)
            
            if not session:
                return None
            
            # 检查状态
            if session.state != SessionState.ACTIVE:
                return None
            
            # 检查过期
            if session.is_expired():
                session.state = SessionState.EXPIRED
                return None
            
            # 检查空闲超时
            idle_time = time.time() - session.last_accessed
            if idle_time > self._config.idle_timeout:
                session.state = SessionState.EXPIRED
                return None
            
            # 更新访问时间
            session.touch()
            
            return session
    
    def validate_session(self, session_id: str) -> bool:
        """
        验证会话有效性
        
        Args:
            session_id: 会话ID
        
        Returns:
            是否有效
        """
        session = self.get_session(session_id)
        return session is not None and session.is_valid()
    
    def destroy_session(self, session_id: str) -> bool:
        """
        销毁会话
        
        Args:
            session_id: 会话ID
        
        Returns:
            是否销毁成功
        """
        with self._lock:
            session = self._sessions.get(session_id)
            
            if not session:
                return False
            
            session.state = SessionState.DESTROYED
            
            # 从用户会话列表移除
            if session.user_id and session.user_id in self._user_sessions:
                if session_id in self._user_sessions[session.user_id]:
                    self._user_sessions[session.user_id].remove(session_id)
            
            del self._sessions[session_id]
            return True
    
    def destroy_user_sessions(self, user_id: str, exclude: Optional[str] = None) -> int:
        """
        销毁用户的所有会话
        
        Args:
            user_id: 用户ID
            exclude: 排除的会话ID
        
        Returns:
            销毁的会话数量
        """
        with self._lock:
            if user_id not in self._user_sessions:
                return 0
            
            session_ids = list(self._user_sessions[user_id])
            count = 0
            
            for session_id in session_ids:
                if exclude and session_id == exclude:
                    continue
                
                if self.destroy_session(session_id):
                    count += 1
            
            return count
    
    def set_session_data(self, session_id: str, key: str, value: Any) -> bool:
        """
        设置会话数据
        
        Args:
            session_id: 会话ID
            key: 键
            value: 值
        
        Returns:
            是否设置成功
        """
        with self._lock:
            session = self.get_session(session_id)
            if not session:
                return False
            
            session.data[key] = value
            return True
    
    def get_session_data(self, session_id: str, key: str, default: Any = None) -> Any:
        """
        获取会话数据
        
        Args:
            session_id: 会话ID
            key: 键
            default: 默认值
        
        Returns:
            数据值
        """
        with self._lock:
            session = self.get_session(session_id)
            if not session:
                return default
            
            return session.data.get(key, default)
    
    def delete_session_data(self, session_id: str, key: str) -> bool:
        """
        删除会话数据
        
        Args:
            session_id: 会话ID
            key: 键
        
        Returns:
            是否删除成功
        """
        with self._lock:
            session = self.get_session(session_id)
            if not session:
                return False
            
            if key in session.data:
                del session.data[key]
                return True
            
            return False
    
    def regenerate_session_id(self, session_id: str) -> Optional[str]:
        """
        重新生成会话ID
        
        Args:
            session_id: 原会话ID
        
        Returns:
            新会话ID
        """
        with self._lock:
            old_session = self._sessions.get(session_id)
            if not old_session or not old_session.is_valid():
                return None
            
            # 创建新会话
            new_session = self.create_session(
                user_id=old_session.user_id,
                ip_address=old_session.ip_address,
                user_agent=old_session.user_agent
            )
            
            # 复制数据
            new_session.data = dict(old_session.data)
            
            # 销毁旧会话
            self.destroy_session(session_id)
            
            return new_session.session_id
    
    def extend_session(self, session_id: str, seconds: Optional[int] = None) -> bool:
        """
        延长会话有效期
        
        Args:
            session_id: 会话ID
            seconds: 延长秒数
        
        Returns:
            是否延长成功
        """
        with self._lock:
            session = self.get_session(session_id)
            if not session:
                return False
            
            extend_seconds = seconds or self._config.lifetime
            session.expires_at = time.time() + extend_seconds
            return True
    
    def _cleanup_if_needed(self) -> None:
        """如果需要则清理过期会话"""
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        
        self._last_cleanup = now
        self._cleanup_expired_sessions()
    
    def _cleanup_expired_sessions(self) -> int:
        """
        清理过期会话
        
        Returns:
            清理的会话数量
        """
        now = time.time()
        expired_ids = []
        
        for session_id, session in self._sessions.items():
            if session.is_expired() or session.state != SessionState.ACTIVE:
                expired_ids.append(session_id)
            elif now - session.last_accessed > self._config.idle_timeout:
                expired_ids.append(session_id)
        
        for session_id in expired_ids:
            self.destroy_session(session_id)
        
        return len(expired_ids)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取会话统计信息
        
        Returns:
            统计信息字典
        """
        with self._lock:
            active_count = 0
            expired_count = 0
            
            for session in self._sessions.values():
                if session.is_valid():
                    active_count += 1
                else:
                    expired_count += 1
            
            return {
                'total_sessions': len(self._sessions),
                'active_sessions': active_count,
                'expired_sessions': expired_count,
                'users_with_sessions': len(self._user_sessions),
                'last_cleanup': self._last_cleanup
            }
    
    def get_user_sessions(self, user_id: str) -> List[Session]:
        """
        获取用户的所有活跃会话
        
        Args:
            user_id: 用户ID
        
        Returns:
            会话列表
        """
        with self._lock:
            if user_id not in self._user_sessions:
                return []
            
            sessions = []
            for session_id in self._user_sessions[user_id]:
                session = self.get_session(session_id)
                if session:
                    sessions.append(session)
            
            return sessions


# 全局会话管理器
_session_manager: Optional[SessionManager] = None
_manager_lock = threading.Lock()


def get_session_manager() -> SessionManager:
    """获取全局会话管理器"""
    global _session_manager
    if _session_manager is None:
        with _manager_lock:
            if _session_manager is None:
                _session_manager = SessionManager()
    return _session_manager
