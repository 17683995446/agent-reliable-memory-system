"""
公私记忆隔离模块
阶段 67：开发公私记忆隔离机制，保护私有用户记忆

核心特性：
- 区分公共记忆（共享）和私有记忆（用户专属）
- 私有记忆仅对所属用户可见
- 支持记忆权限控制
"""

import time
import hashlib
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from enum import Enum


class MemoryVisibility(Enum):
    """记忆可见性"""
    PUBLIC = "public"      # 公共记忆，所有用户可见
    PRIVATE = "private"    # 私有记忆，仅所属用户可见
    SHARED = "shared"      # 共享记忆，指定用户组可见


@dataclass
class AccessControlEntry:
    """访问控制条目"""
    memory_id: str
    owner_id: str
    visibility: MemoryVisibility
    allowed_users: Set[str] = field(default_factory=set)
    created_at: float = field(default_factory=time.time)


class PrivacyIsolationManager:
    """
    隐私隔离管理器
    
    管理记忆的访问权限和可见性控制。
    """
    
    def __init__(self):
        # 访问控制表：memory_id -> AccessControlEntry
        self._access_control: Dict[str, AccessControlEntry] = {}
        # 用户私有记忆索引：user_id -> Set[memory_id]
        self._user_private_memories: Dict[str, Set[str]] = {}
    
    def register_memory(self, memory_id: str, owner_id: str,
                       visibility: MemoryVisibility = MemoryVisibility.PRIVATE,
                       allowed_users: List[str] = None) -> bool:
        """
        注册记忆并设置访问权限
        
        Args:
            memory_id: 记忆ID
            owner_id: 所有者ID
            visibility: 可见性
            allowed_users: 允许访问的用户列表（SHARED模式用）
            
        Returns:
            bool: 是否成功
        """
        entry = AccessControlEntry(
            memory_id=memory_id,
            owner_id=owner_id,
            visibility=visibility,
            allowed_users=set(allowed_users) if allowed_users else set()
        )
        
        self._access_control[memory_id] = entry
        
        # 更新用户私有记忆索引
        if visibility == MemoryVisibility.PRIVATE:
            if owner_id not in self._user_private_memories:
                self._user_private_memories[owner_id] = set()
            self._user_private_memories[owner_id].add(memory_id)
        
        return True
    
    def can_access(self, memory_id: str, user_id: str) -> bool:
        """
        检查用户是否有权限访问记忆
        
        Args:
            memory_id: 记忆ID
            user_id: 用户ID
            
        Returns:
            bool: 是否有权限
        """
        if memory_id not in self._access_control:
            # 未注册的记忆默认允许访问（兼容旧数据）
            return True
        
        entry = self._access_control[memory_id]
        
        # 所有者始终有权限
        if entry.owner_id == user_id:
            return True
        
        # 根据可见性判断
        if entry.visibility == MemoryVisibility.PUBLIC:
            return True
        elif entry.visibility == MemoryVisibility.PRIVATE:
            return False
        elif entry.visibility == MemoryVisibility.SHARED:
            return user_id in entry.allowed_users
        
        return False
    
    def get_accessible_memories(self, user_id: str,
                               memory_ids: List[str]) -> List[str]:
        """
        过滤出用户有权限访问的记忆ID列表
        
        Args:
            user_id: 用户ID
            memory_ids: 候选记忆ID列表
            
        Returns:
            List[str]: 有权限访问的记忆ID列表
        """
        return [mid for mid in memory_ids if self.can_access(mid, user_id)]
    
    def share_memory(self, memory_id: str, owner_id: str,
                    target_user_id: str) -> bool:
        """
        共享私有记忆给指定用户
        
        Args:
            memory_id: 记忆ID
            owner_id: 所有者ID（需验证）
            target_user_id: 目标用户ID
            
        Returns:
            bool: 是否成功
        """
        if memory_id not in self._access_control:
            return False
        
        entry = self._access_control[memory_id]
        
        # 验证所有者
        if entry.owner_id != owner_id:
            return False
        
        # 更新为 SHARED 模式并添加允许用户
        entry.visibility = MemoryVisibility.SHARED
        entry.allowed_users.add(target_user_id)
        
        return True
    
    def make_public(self, memory_id: str, owner_id: str) -> bool:
        """
        将私有记忆转为公共记忆
        
        Args:
            memory_id: 记忆ID
            owner_id: 所有者ID
            
        Returns:
            bool: 是否成功
        """
        if memory_id not in self._access_control:
            return False
        
        entry = self._access_control[memory_id]
        
        if entry.owner_id != owner_id:
            return False
        
        # 从用户私有索引中移除
        if entry.owner_id in self._user_private_memories:
            self._user_private_memories[entry.owner_id].discard(memory_id)
        
        entry.visibility = MemoryVisibility.PUBLIC
        entry.allowed_users.clear()
        
        return True
    
    def revoke_access(self, memory_id: str, owner_id: str,
                     target_user_id: str = None) -> bool:
        """
        撤销访问权限
        
        Args:
            memory_id: 记忆ID
            owner_id: 所有者ID
            target_user_id: 目标用户ID（None表示撤销所有共享）
            
        Returns:
            bool: 是否成功
        """
        if memory_id not in self._access_control:
            return False
        
        entry = self._access_control[memory_id]
        
        if entry.owner_id != owner_id:
            return False
        
        if target_user_id:
            entry.allowed_users.discard(target_user_id)
        else:
            # 撤销所有共享，转为私有
            entry.visibility = MemoryVisibility.PRIVATE
            entry.allowed_users.clear()
            
            # 更新索引
            if owner_id not in self._user_private_memories:
                self._user_private_memories[owner_id] = set()
            self._user_private_memories[owner_id].add(memory_id)
        
        return True
    
    def get_user_private_count(self, user_id: str) -> int:
        """获取用户私有记忆数量"""
        return len(self._user_private_memories.get(user_id, set()))
    
    def get_memory_visibility(self, memory_id: str) -> Optional[MemoryVisibility]:
        """获取记忆的可见性设置"""
        entry = self._access_control.get(memory_id)
        return entry.visibility if entry else None
