#!/usr/bin/env python3
"""
访问控制增强 - 阶段152-154
细粒度权限与角色管理
"""

import threading
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict


class Permission(Enum):
    """权限类型"""
    READ = "read"           # 读取
    WRITE = "write"         # 写入
    DELETE = "delete"       # 删除
    SHARE = "share"         # 共享
    ADMIN = "admin"         # 管理员


class Role(Enum):
    """角色类型"""
    GUEST = "guest"         # 访客：只读
    USER = "user"           # 用户：读写
    EDITOR = "editor"       # 编辑者：读写删
    ADMIN = "admin"         # 管理员：全部权限


# 角色默认权限
ROLE_PERMISSIONS: Dict[Role, Set[Permission]] = {
    Role.GUEST: {Permission.READ},
    Role.USER: {Permission.READ, Permission.WRITE},
    Role.EDITOR: {Permission.READ, Permission.WRITE, Permission.DELETE, Permission.SHARE},
    Role.ADMIN: {Permission.READ, Permission.WRITE, Permission.DELETE, Permission.SHARE, Permission.ADMIN},
}


@dataclass
class UserContext:
    """用户上下文"""
    user_id: str
    role: Role = Role.USER
    groups: List[str] = field(default_factory=list)
    extra_permissions: Set[Permission] = field(default_factory=set)


class AccessController:
    """
    访问控制器

    提供细粒度的权限控制：
    - 角色管理
    - 资源级权限
    - 用户组支持
    """

    def __init__(self):
        self._users: Dict[str, UserContext] = {}
        self._resource_acl: Dict[str, Dict[str, Set[Permission]]] = defaultdict(dict)
        self._group_members: Dict[str, Set[str]] = defaultdict(set)
        self._lock = threading.RLock()

    def register_user(
        self,
        user_id: str,
        role: Role = Role.USER,
        groups: Optional[List[str]] = None
    ) -> bool:
        """注册用户"""
        with self._lock:
            if user_id in self._users:
                return False
            self._users[user_id] = UserContext(
                user_id=user_id,
                role=role,
                groups=groups or [],
            )
            # 加入用户组
            for group in (groups or []):
                self._group_members[group].add(user_id)
            return True

    def set_user_role(self, user_id: str, role: Role) -> bool:
        """设置用户角色"""
        with self._lock:
            if user_id not in self._users:
                return False
            self._users[user_id].role = role
            return True

    def grant_permission(
        self,
        user_id: str,
        resource_id: str,
        permission: Permission
    ) -> bool:
        """授予用户对资源的权限"""
        with self._lock:
            if user_id not in self._users:
                return False
            if permission not in self._resource_acl[resource_id][user_id]:
                self._resource_acl[resource_id][user_id].add(permission)
            return True

    def revoke_permission(
        self,
        user_id: str,
        resource_id: str,
        permission: Permission
    ) -> bool:
        """撤销用户对资源的权限"""
        with self._lock:
            if resource_id in self._resource_acl:
                if user_id in self._resource_acl[resource_id]:
                    self._resource_acl[resource_id][user_id].discard(permission)
            return True

    def check_permission(
        self,
        user_id: str,
        resource_id: str,
        permission: Permission
    ) -> bool:
        """
        检查用户是否有权限

        Args:
            user_id: 用户ID
            resource_id: 资源ID
            permission: 权限类型

        Returns:
            是否有权限
        """
        with self._lock:
            # 用户不存在
            if user_id not in self._users:
                return False

            user = self._users[user_id]

            # 1. 检查角色权限
            role_perms = ROLE_PERMISSIONS.get(user.role, set())
            if permission in role_perms:
                return True

            # 2. 检查额外权限
            if permission in user.extra_permissions:
                return True

            # 3. 检查资源级权限
            if resource_id in self._resource_acl:
                if user_id in self._resource_acl[resource_id]:
                    if permission in self._resource_acl[resource_id][user_id]:
                        return True

            # 4. 检查用户组权限
            for group in user.groups:
                group_key = f"group:{group}"
                if group_key in self._resource_acl.get(resource_id, {}):
                    if permission in self._resource_acl[resource_id][group_key]:
                        return True

            return False

    def get_user_permissions(
        self,
        user_id: str,
        resource_id: str
    ) -> List[str]:
        """获取用户对资源的所有权限"""
        with self._lock:
            if user_id not in self._users:
                return []

            user = self._users[user_id]
            all_perms = set()

            # 角色权限
            all_perms.update(ROLE_PERMISSIONS.get(user.role, set()))

            # 额外权限
            all_perms.update(user.extra_permissions)

            # 资源级权限
            if resource_id in self._resource_acl:
                if user_id in self._resource_acl[resource_id]:
                    all_perms.update(self._resource_acl[resource_id][user_id])

            return [p.value for p in all_perms]

    def create_group(self, group_name: str) -> bool:
        """创建用户组"""
        with self._lock:
            if group_name not in self._group_members:
                self._group_members[group_name] = set()
                return True
            return False

    def add_to_group(self, user_id: str, group_name: str) -> bool:
        """将用户加入组"""
        with self._lock:
            if user_id not in self._users:
                return False
            self._group_members[group_name].add(user_id)
            if group_name not in self._users[user_id].groups:
                self._users[user_id].groups.append(group_name)
            return True

    def get_group_members(self, group_name: str) -> List[str]:
        """获取组成员"""
        with self._lock:
            return list(self._group_members.get(group_name, set()))

    def get_stats(self) -> Dict[str, Any]:
        """获取统计"""
        with self._lock:
            return {
                "total_users": len(self._users),
                "total_groups": len(self._group_members),
                "protected_resources": len(self._resource_acl),
                "users_by_role": {
                    role.value: sum(1 for u in self._users.values() if u.role == role)
                    for role in Role
                },
            }
