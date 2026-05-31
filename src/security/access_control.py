"""
访问控制模块 - 阶段377 (Phase 35)

功能：
- 基于角色的访问控制 (RBAC)
- 资源级别的权限管理
- 规则驱动的访问决策

设计原则：
- 第一性原理：确定性规则，无模型依赖
- 线程安全：使用 threading.RLock
- 全局单例：通过 get_access_controller() 获取，双重检查锁定
- 使用 Python dataclasses 定义数据结构，Enum 定义类型
- 最小依赖，无循环依赖
"""

import threading
import time
import re
import fnmatch
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Any


class Permission(Enum):
    """权限枚举"""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    ADMIN = "admin"
    EXECUTE = "execute"
    CREATE = "create"


class ResourceType(Enum):
    """资源类型枚举"""
    MEMORY = "memory"
    SESSION = "session"
    CONFIG = "config"
    LOG = "log"
    DOCUMENT = "document"
    KNOWLEDGE = "knowledge"
    SYSTEM = "system"


class AccessDecision(Enum):
    """访问决策枚举"""
    ALLOW = "allow"
    DENY = "deny"
    NOT_APPLICABLE = "not_applicable"


@dataclass
class PermissionRule:
    """
    权限规则
    
    定义对特定资源类型的访问规则
    """
    rule_id: str
    resource_type: ResourceType
    resource_id_pattern: str  # 资源ID匹配模式，支持通配符
    permissions: Set[Permission]
    conditions: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0  # 优先级，数值越高优先级越高
    enabled: bool = True
    created_at: float = field(default_factory=time.time)

    def __hash__(self):
        return hash(self.rule_id)

    def __eq__(self, other):
        if isinstance(other, PermissionRule):
            return self.rule_id == other.rule_id
        return False


@dataclass
class AccessContext:
    """
    访问上下文
    
    包含访问请求的上下文信息
    """
    user_id: str
    roles: Set[str] = field(default_factory=set)
    groups: Set[str] = field(default_factory=set)
    attributes: Dict[str, Any] = field(default_factory=dict)
    session_id: str = ""
    ip_address: str = ""
    timestamp: float = field(default_factory=time.time)


class AccessController:
    """
    访问控制器
    
    实现基于角色的访问控制 (RBAC) 和基于规则的访问控制
    
    功能：
    - 角色管理：创建、删除角色，分配权限
    - 用户角色管理：为用户分配/撤销角色
    - 资源规则管理：添加/移除资源访问规则
    - 访问检查：检查用户对特定资源的访问权限
    
    默认角色：
    - admin: 拥有所有权限
    - user: 拥有 READ, WRITE 权限
    - guest: 拥有 READ 权限
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
            
            # 角色权限映射: role_name -> permissions
            self._roles: Dict[str, Set[Permission]] = {}
            
            # 用户角色映射: user_id -> role_names
            self._user_roles: Dict[str, Set[str]] = {}
            
            # 资源规则映射: resource_type -> list of rules
            self._resource_rules: Dict[ResourceType, List[PermissionRule]] = {}
            
            # 规则索引: rule_id -> rule
            self._rules_index: Dict[str, PermissionRule] = {}
            
            # 初始化默认角色
            self._init_default_roles()
    
    def _init_default_roles(self) -> None:
        """初始化默认角色"""
        # admin 角色：拥有所有权限
        self._roles["admin"] = {
            Permission.READ,
            Permission.WRITE,
            Permission.DELETE,
            Permission.ADMIN,
            Permission.EXECUTE,
            Permission.CREATE
        }
        
        # user 角色：拥有 READ, WRITE, CREATE 权限
        self._roles["user"] = {
            Permission.READ,
            Permission.WRITE,
            Permission.CREATE
        }
        
        # guest 角色：只拥有 READ 权限
        self._roles["guest"] = {
            Permission.READ
        }
    
    # ========== 角色管理 ==========
    
    def create_role(self, role_name: str, permissions: Set[Permission]) -> bool:
        """
        创建角色
        
        Args:
            role_name: 角色名称
            permissions: 权限集合
            
        Returns:
            创建成功返回 True，角色已存在返回 False
        """
        with self._lock:
            if role_name in self._roles:
                return False
            
            self._roles[role_name] = permissions.copy()
            return True
    
    def delete_role(self, role_name: str) -> bool:
        """
        删除角色
        
        Args:
            role_name: 角色名称
            
        Returns:
            删除成功返回 True，角色不存在返回 False
        """
        with self._lock:
            if role_name not in self._roles:
                return False
            
            # 删除角色
            del self._roles[role_name]
            
            # 从所有用户中移除该角色
            for user_id in self._user_roles:
                self._user_roles[user_id].discard(role_name)
            
            return True
    
    def get_roles(self) -> List[str]:
        """
        获取所有角色名称
        
        Returns:
            角色名称列表
        """
        with self._lock:
            return list(self._roles.keys())
    
    def get_role_permissions(self, role_name: str) -> Set[Permission]:
        """
        获取角色的权限
        
        Args:
            role_name: 角色名称
            
        Returns:
            权限集合，角色不存在返回空集合
        """
        with self._lock:
            return self._roles.get(role_name, set()).copy()
    
    # ========== 用户角色管理 ==========
    
    def assign_role(self, user_id: str, role_name: str) -> bool:
        """
        为用户分配角色
        
        Args:
            user_id: 用户ID
            role_name: 角色名称
            
        Returns:
            分配成功返回 True，角色不存在返回 False
        """
        with self._lock:
            if role_name not in self._roles:
                return False
            
            if user_id not in self._user_roles:
                self._user_roles[user_id] = set()
            
            self._user_roles[user_id].add(role_name)
            return True
    
    def revoke_role(self, user_id: str, role_name: str) -> bool:
        """
        撤销用户的角色
        
        Args:
            user_id: 用户ID
            role_name: 角色名称
            
        Returns:
            撤销成功返回 True，用户没有该角色返回 False
        """
        with self._lock:
            if user_id not in self._user_roles:
                return False
            
            if role_name not in self._user_roles[user_id]:
                return False
            
            self._user_roles[user_id].discard(role_name)
            return True
    
    def get_user_permissions(self, user_id: str) -> Set[Permission]:
        """
        获取用户的所有权限（聚合所有角色的权限）
        
        Args:
            user_id: 用户ID
            
        Returns:
            权限集合
        """
        with self._lock:
            permissions: Set[Permission] = set()
            
            user_roles = self._user_roles.get(user_id, set())
            for role_name in user_roles:
                role_perms = self._roles.get(role_name, set())
                permissions.update(role_perms)
            
            return permissions
    
    def get_users_with_role(self, role_name: str) -> List[str]:
        """
        获取拥有指定角色的所有用户
        
        Args:
            role_name: 角色名称
            
        Returns:
            用户ID列表
        """
        with self._lock:
            users = []
            for user_id, roles in self._user_roles.items():
                if role_name in roles:
                    users.append(user_id)
            return users
    
    # ========== 资源规则管理 ==========
    
    def add_resource_rule(self, resource_type: ResourceType, rule: PermissionRule) -> bool:
        """
        添加资源访问规则
        
        Args:
            resource_type: 资源类型
            rule: 权限规则
            
        Returns:
            添加成功返回 True，规则ID已存在返回 False
        """
        with self._lock:
            if rule.rule_id in self._rules_index:
                return False
            
            if resource_type not in self._resource_rules:
                self._resource_rules[resource_type] = []
            
            self._resource_rules[resource_type].append(rule)
            self._rules_index[rule.rule_id] = rule
            
            # 按优先级排序（高优先级在前）
            self._resource_rules[resource_type].sort(
                key=lambda r: r.priority,
                reverse=True
            )
            
            return True
    
    def remove_resource_rule(self, resource_type: ResourceType, rule_id: str) -> bool:
        """
        移除资源访问规则
        
        Args:
            resource_type: 资源类型
            rule_id: 规则ID
            
        Returns:
            移除成功返回 True，规则不存在返回 False
        """
        with self._lock:
            if rule_id not in self._rules_index:
                return False
            
            rule = self._rules_index.pop(rule_id)
            
            if resource_type in self._resource_rules:
                try:
                    self._resource_rules[resource_type].remove(rule)
                except ValueError:
                    pass
            
            return True
    
    # ========== 访问检查 ==========
    
    def check_access(
        self,
        user_id: str,
        resource_type: ResourceType,
        resource_id: str,
        permission: Permission,
        context: Optional[AccessContext] = None
    ) -> AccessDecision:
        """
        检查用户对指定资源的访问权限
        
        决策流程：
        1. 检查用户是否有 ADMIN 权限（直接允许）
        2. 检查用户的角色权限
        3. 检查资源规则
        4. 默认拒绝
        
        Args:
            user_id: 用户ID
            resource_type: 资源类型
            resource_id: 资源ID
            permission: 请求的权限
            context: 访问上下文（可选）
            
        Returns:
            AccessDecision.ALLOW: 允许访问
            AccessDecision.DENY: 拒绝访问
            AccessDecision.NOT_APPLICABLE: 规则不适用
        """
        with self._lock:
            # 1. 检查 ADMIN 权限
            user_permissions = self.get_user_permissions(user_id)
            if Permission.ADMIN in user_permissions:
                return AccessDecision.ALLOW
            
            # 2. 检查角色权限
            if permission in user_permissions:
                # 继续检查资源规则以确认
                pass
            else:
                # 用户没有该权限，直接拒绝
                return AccessDecision.DENY
            
            # 3. 检查资源规则
            rules = self._resource_rules.get(resource_type, [])
            
            for rule in rules:
                if not rule.enabled:
                    continue
                
                # 检查资源ID是否匹配
                if not self._match_resource_id(resource_id, rule.resource_id_pattern):
                    continue
                
                # 检查权限是否在规则中
                if permission not in rule.permissions:
                    continue
                
                # 检查条件
                if rule.conditions:
                    if not self._evaluate_conditions(rule.conditions, context):
                        continue
                
                # 规则匹配，允许访问
                return AccessDecision.ALLOW
            
            # 4. 如果有角色权限但没有匹配的资源规则，默认允许
            if permission in user_permissions:
                return AccessDecision.ALLOW
            
            # 5. 默认拒绝
            return AccessDecision.DENY
    
    def _match_resource_id(self, resource_id: str, pattern: str) -> bool:
        """
        匹配资源ID
        
        支持通配符匹配：
        - *: 匹配任意字符
        - ?: 匹配单个字符
        
        Args:
            resource_id: 资源ID
            pattern: 匹配模式
            
        Returns:
            匹配成功返回 True
        """
        if pattern == "*":
            return True
        
        if pattern == resource_id:
            return True
        
        # 使用 fnmatch 进行通配符匹配
        return fnmatch.fnmatch(resource_id, pattern)
    
    def _evaluate_conditions(
        self,
        conditions: Dict[str, Any],
        context: Optional[AccessContext]
    ) -> bool:
        """
        评估访问条件
        
        支持的条件类型：
        - 简单条件: {"key": value} - 检查上下文属性是否等于指定值
        - 复杂条件: {"key": {"op": "eq/ne/gt/lt/in", "value": ...}}
        
        Args:
            conditions: 条件字典
            context: 访问上下文
            
        Returns:
            所有条件满足返回 True
        """
        if not context:
            return False
        
        for key, expected in conditions.items():
            # 从上下文获取实际值
            actual = self._get_context_value(context, key)
            
            if isinstance(expected, dict):
                # 复杂条件
                op = expected.get("op")
                value = expected.get("value")
                
                if op == "eq":
                    if actual != value:
                        return False
                elif op == "ne":
                    if actual == value:
                        return False
                elif op == "gt":
                    if actual is None or actual <= value:
                        return False
                elif op == "lt":
                    if actual is None or actual >= value:
                        return False
                elif op == "in":
                    if actual not in value:
                        return False
                elif op == "contains":
                    if value not in actual:
                        return False
            else:
                # 简单相等条件
                if actual != expected:
                    return False
        
        return True
    
    def _get_context_value(self, context: AccessContext, key: str) -> Any:
        """
        从上下文获取值
        
        支持的键：
        - user_id: 用户ID
        - session_id: 会话ID
        - ip_address: IP地址
        - roles: 角色集合
        - groups: 组集合
        - attr.xxx: 属性值
        
        Args:
            context: 访问上下文
            key: 键名
            
        Returns:
            对应的值
        """
        if key == "user_id":
            return context.user_id
        elif key == "session_id":
            return context.session_id
        elif key == "ip_address":
            return context.ip_address
        elif key == "roles":
            return context.roles
        elif key == "groups":
            return context.groups
        elif key.startswith("attr."):
            attr_key = key[5:]
            return context.attributes.get(attr_key)
        else:
            return context.attributes.get(key)
    
    # ========== 辅助方法 ==========
    
    def create_rule(
        self,
        resource_type: ResourceType,
        resource_id_pattern: str,
        permissions: Set[Permission],
        conditions: Optional[Dict[str, Any]] = None,
        priority: int = 0
    ) -> PermissionRule:
        """
        创建权限规则（辅助方法）
        
        Args:
            resource_type: 资源类型
            resource_id_pattern: 资源ID匹配模式
            permissions: 权限集合
            conditions: 条件字典（可选）
            priority: 优先级
            
        Returns:
            创建的权限规则
        """
        return PermissionRule(
            rule_id=str(uuid.uuid4()),
            resource_type=resource_type,
            resource_id_pattern=resource_id_pattern,
            permissions=permissions,
            conditions=conditions or {},
            priority=priority
        )
    
    def has_permission(self, user_id: str, permission: Permission) -> bool:
        """
        检查用户是否拥有指定权限
        
        Args:
            user_id: 用户ID
            permission: 权限
            
        Returns:
            拥有权限返回 True
        """
        user_permissions = self.get_user_permissions(user_id)
        return permission in user_permissions or Permission.ADMIN in user_permissions
    
    def has_role(self, user_id: str, role_name: str) -> bool:
        """
        检查用户是否拥有指定角色
        
        Args:
            user_id: 用户ID
            role_name: 角色名称
            
        Returns:
            拥有角色返回 True
        """
        with self._lock:
            user_roles = self._user_roles.get(user_id, set())
            return role_name in user_roles
    
    def clear_user_roles(self, user_id: str) -> int:
        """
        清除用户的所有角色
        
        Args:
            user_id: 用户ID
            
        Returns:
            清除的角色数量
        """
        with self._lock:
            if user_id not in self._user_roles:
                return 0
            
            count = len(self._user_roles[user_id])
            del self._user_roles[user_id]
            return count
    
    def get_resource_rules(self, resource_type: ResourceType) -> List[PermissionRule]:
        """
        获取指定资源类型的所有规则
        
        Args:
            resource_type: 资源类型
            
        Returns:
            规则列表
        """
        with self._lock:
            return list(self._resource_rules.get(resource_type, []))


# ========== 全局单例 ==========

_access_controller_instance: Optional[AccessController] = None
_access_controller_lock = threading.RLock()


def get_access_controller() -> AccessController:
    """
    获取访问控制器全局实例（双重检查锁定）
    
    Returns:
        AccessController 单例实例
    """
    global _access_controller_instance
    if _access_controller_instance is None:
        with _access_controller_lock:
            if _access_controller_instance is None:
                _access_controller_instance = AccessController()
    return _access_controller_instance


def reset_access_controller() -> None:
    """
    重置访问控制器全局实例（用于测试）
    """
    global _access_controller_instance
    with _access_controller_lock:
        _access_controller_instance = None
