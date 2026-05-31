"""
授权引擎 - 阶段209-211

功能：
- 阶段209: RBAC权限模型
- 阶段210: 资源授权
- 阶段211: 策略评估

设计原则：
- 确定性规则，无模型依赖
- 最小层级，无循环依赖
- 线程安全，RLock保护
- 单例模式，全局唯一
"""

import threading
import time
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Dict, List, Optional, Callable, Any, Set, Tuple, Union
from collections import defaultdict
import uuid
import fnmatch


class Permission(Enum):
    """权限枚举"""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    LIST = "list"
    EXECUTE = "execute"
    ADMIN = "admin"


class RoleType(Enum):
    """角色类型"""
    SYSTEM = "system"
    CUSTOM = "custom"
    INHERITED = "inherited"


class PolicyEffect(Enum):
    """策略效果"""
    ALLOW = "allow"
    DENY = "deny"


@dataclass
class Role:
    """角色定义"""
    role_id: str
    name: str
    description: str
    role_type: RoleType
    permissions: Dict[str, Set[Permission]] = field(default_factory=dict)
    parent_roles: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


@dataclass
class Resource:
    """资源定义"""
    resource_id: str
    resource_type: str
    resource_path: str
    owner_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


@dataclass
class Policy:
    """策略定义"""
    policy_id: str
    name: str
    description: str
    effect: PolicyEffect
    subjects: List[str]  # 用户/角色匹配
    resources: List[str]  # 资源匹配
    actions: List[str]   # 操作匹配
    conditions: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    enabled: bool = True


@dataclass
class UserRoleAssignment:
    """用户角色分配"""
    assignment_id: str
    user_id: str
    role_id: str
    granted_by: str
    granted_at: float
    expires_at: Optional[float] = None


@dataclass
class AuthzRequest:
    """授权请求"""
    subject: str  # 用户ID
    resource: str  # 资源路径
    action: Permission
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AuthzResult:
    """授权结果"""
    allowed: bool
    reason: str
    matched_policy: Optional[str] = None
    evaluated_policies: List[str] = field(default_factory=list)


class Authorizer:
    """
    授权引擎
    
    阶段209: RBAC权限模型
    - 角色定义与管理
    - 权限继承
    - 用户角色分配
    
    阶段210: 资源授权
    - 资源注册与管理
    - 资源路径匹配
    - 所有权验证
    
    阶段211: 策略评估
    - ABAC策略支持
    - 条件评估
    - 策略优先级
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
            
            # 角色存储
            self._roles: Dict[str, Role] = {}
            
            # 资源存储
            self._resources: Dict[str, Resource] = {}
            
            # 策略存储
            self._policies: Dict[str, Policy] = {}
            
            # 用户角色分配
            self._user_roles: Dict[str, Set[str]] = defaultdict(set)
            self._assignments: Dict[str, UserRoleAssignment] = {}
            
            # 初始化默认角色
            self._init_default_roles()
    
    def _init_default_roles(self):
        """初始化默认角色"""
        default_roles = [
            Role(
                role_id="role_admin",
                name="admin",
                description="系统管理员",
                role_type=RoleType.SYSTEM,
                permissions={"*": {Permission.ADMIN}}
            ),
            Role(
                role_id="role_user",
                name="user",
                description="普通用户",
                role_type=RoleType.SYSTEM,
                permissions={
                    "memory": {Permission.CREATE, Permission.READ, Permission.UPDATE, Permission.DELETE, Permission.LIST},
                    "tag": {Permission.CREATE, Permission.READ, Permission.UPDATE, Permission.DELETE, Permission.LIST}
                }
            ),
            Role(
                role_id="role_reader",
                name="reader",
                description="只读用户",
                role_type=RoleType.SYSTEM,
                permissions={
                    "memory": {Permission.READ, Permission.LIST},
                    "tag": {Permission.READ, Permission.LIST}
                }
            ),
            Role(
                role_id="role_guest",
                name="guest",
                description="访客",
                role_type=RoleType.SYSTEM,
                permissions={
                    "memory": {Permission.READ}
                }
            )
        ]
        
        for role in default_roles:
            self._roles[role.role_id] = role
    
    # ========== 阶段209: RBAC权限模型 ==========
    
    def create_role(self, name: str, description: str,
                   permissions: Dict[str, Set[Permission]],
                   parent_roles: Optional[List[str]] = None) -> Role:
        """创建角色"""
        role = Role(
            role_id=str(uuid.uuid4()),
            name=name,
            description=description,
            role_type=RoleType.CUSTOM,
            permissions=permissions,
            parent_roles=parent_roles or []
        )
        
        with self._lock:
            self._roles[role.role_id] = role
        
        return role
    
    def get_role(self, role_id: str) -> Optional[Role]:
        """获取角色"""
        with self._lock:
            return self._roles.get(role_id)
    
    def assign_role_to_user(self, user_id: str, role_id: str,
                           granted_by: str = "system",
                           expires_at: Optional[float] = None) -> bool:
        """分配角色给用户"""
        with self._lock:
            if role_id not in self._roles:
                return False
            
            assignment = UserRoleAssignment(
                assignment_id=str(uuid.uuid4()),
                user_id=user_id,
                role_id=role_id,
                granted_by=granted_by,
                granted_at=time.time(),
                expires_at=expires_at
            )
            
            self._assignments[assignment.assignment_id] = assignment
            self._user_roles[user_id].add(role_id)
            
            return True
    
    def revoke_role_from_user(self, user_id: str, role_id: str) -> bool:
        """撤销用户角色"""
        with self._lock:
            if role_id in self._user_roles.get(user_id, set()):
                self._user_roles[user_id].discard(role_id)
                
                # 删除相关分配记录
                to_remove = [
                    aid for aid, assign in self._assignments.items()
                    if assign.user_id == user_id and assign.role_id == role_id
                ]
                for aid in to_remove:
                    del self._assignments[aid]
                
                return True
            return False
    
    def get_user_roles(self, user_id: str) -> List[Role]:
        """获取用户的所有角色"""
        with self._lock:
            role_ids = self._user_roles.get(user_id, set())
            return [self._roles[rid] for rid in role_ids if rid in self._roles]
    
    def get_user_permissions(self, user_id: str) -> Dict[str, Set[Permission]]:
        """获取用户的所有权限（包含继承）"""
        permissions: Dict[str, Set[Permission]] = defaultdict(set)
        
        roles = self.get_user_roles(user_id)
        
        for role in roles:
            self._collect_permissions(role, permissions, set())
        
        return dict(permissions)
    
    def _collect_permissions(self, role: Role,
                            permissions: Dict[str, Set[Permission]],
                            visited: Set[str]):
        """收集角色权限（递归处理继承）"""
        if role.role_id in visited:
            return
        
        visited.add(role.role_id)
        
        # 添加当前角色权限
        for resource, perms in role.permissions.items():
            permissions[resource].update(perms)
        
        # 递归处理父角色
        with self._lock:
            for parent_id in role.parent_roles:
                parent = self._roles.get(parent_id)
                if parent:
                    self._collect_permissions(parent, permissions, visited)
    
    # ========== 阶段210: 资源授权 ==========
    
    def register_resource(self, resource_type: str, resource_path: str,
                         owner_id: str,
                         resource_id: Optional[str] = None,
                         metadata: Optional[Dict[str, Any]] = None) -> Resource:
        """注册资源"""
        resource = Resource(
            resource_id=resource_id or str(uuid.uuid4()),
            resource_type=resource_type,
            resource_path=resource_path,
            owner_id=owner_id,
            metadata=metadata or {}
        )
        
        with self._lock:
            self._resources[resource.resource_id] = resource
        
        return resource
    
    def get_resource(self, resource_id: str) -> Optional[Resource]:
        """获取资源"""
        with self._lock:
            return self._resources.get(resource_id)
    
    def check_ownership(self, user_id: str, resource_id: str) -> bool:
        """检查资源所有权"""
        with self._lock:
            resource = self._resources.get(resource_id)
            if resource:
                return resource.owner_id == user_id
            return False
    
    def list_user_resources(self, user_id: str,
                           resource_type: Optional[str] = None) -> List[Resource]:
        """列出用户的资源"""
        with self._lock:
            resources = [
                r for r in self._resources.values()
                if r.owner_id == user_id
            ]
            
            if resource_type:
                resources = [r for r in resources if r.resource_type == resource_type]
            
            return resources
    
    # ========== 阶段211: 策略评估 ==========
    
    def create_policy(self, name: str, description: str,
                     effect: PolicyEffect,
                     subjects: List[str],
                     resources: List[str],
                     actions: List[str],
                     conditions: Optional[Dict[str, Any]] = None,
                     priority: int = 0) -> Policy:
        """创建策略"""
        policy = Policy(
            policy_id=str(uuid.uuid4()),
            name=name,
            description=description,
            effect=effect,
            subjects=subjects,
            resources=resources,
            actions=actions,
            conditions=conditions or {},
            priority=priority
        )
        
        with self._lock:
            self._policies[policy.policy_id] = policy
        
        return policy
    
    def evaluate(self, request: AuthzRequest) -> AuthzResult:
        """评估授权请求"""
        evaluated_policies = []
        
        # 首先检查RBAC权限
        user_perms = self.get_user_permissions(request.subject)
        
        # 检查是否有ADMIN权限
        if Permission.ADMIN in user_perms.get("*", set()):
            return AuthzResult(
                allowed=True,
                reason="User has admin permission",
                evaluated_policies=["rbac_admin"]
            )
        
        # 检查具体权限
        resource_type = self._get_resource_type(request.resource)
        if request.action in user_perms.get(resource_type, set()) or \
           request.action in user_perms.get("*", set()):
            # 继续检查策略
            pass
        else:
            return AuthzResult(
                allowed=False,
                reason="Permission denied by RBAC",
                evaluated_policies=["rbac_check"]
            )
        
        # 评估ABAC策略
        with self._lock:
            policies = sorted(
                self._policies.values(),
                key=lambda p: p.priority,
                reverse=True
            )
        
        for policy in policies:
            if not policy.enabled:
                continue
            
            evaluated_policies.append(policy.policy_id)
            
            # 检查主体匹配
            if not self._match_subject(request.subject, policy.subjects):
                continue
            
            # 检查资源匹配
            if not self._match_resource(request.resource, policy.resources):
                continue
            
            # 检查操作匹配
            if not self._match_action(request.action, policy.actions):
                continue
            
            # 检查条件
            if policy.conditions:
                if not self._evaluate_conditions(policy.conditions, request.context):
                    continue
            
            # 策略匹配，返回结果
            if policy.effect == PolicyEffect.ALLOW:
                return AuthzResult(
                    allowed=True,
                    reason=f"Allowed by policy: {policy.name}",
                    matched_policy=policy.policy_id,
                    evaluated_policies=evaluated_policies
                )
            else:
                return AuthzResult(
                    allowed=False,
                    reason=f"Denied by policy: {policy.name}",
                    matched_policy=policy.policy_id,
                    evaluated_policies=evaluated_policies
                )
        
        # 默认拒绝
        return AuthzResult(
            allowed=False,
            reason="No matching policy found",
            evaluated_policies=evaluated_policies
        )
    
    def authorize(self, user_id: str, resource: str,
                 action: Permission,
                 context: Optional[Dict[str, Any]] = None) -> bool:
        """简化授权检查"""
        request = AuthzRequest(
            subject=user_id,
            resource=resource,
            action=action,
            context=context or {}
        )
        result = self.evaluate(request)
        return result.allowed
    
    def _get_resource_type(self, resource_path: str) -> str:
        """从资源路径获取资源类型"""
        parts = resource_path.strip("/").split("/")
        return parts[0] if parts else "*"
    
    def _match_subject(self, subject: str, patterns: List[str]) -> bool:
        """匹配主体"""
        for pattern in patterns:
            if pattern == "*" or pattern == subject:
                return True
            if pattern.startswith("role:"):
                role_name = pattern[5:]
                # 检查用户是否有该角色
                user_roles = self.get_user_roles(subject)
                if any(r.name == role_name for r in user_roles):
                    return True
        return False
    
    def _match_resource(self, resource: str, patterns: List[str]) -> bool:
        """匹配资源"""
        for pattern in patterns:
            if pattern == "*":
                return True
            if fnmatch.fnmatch(resource, pattern):
                return True
        return False
    
    def _match_action(self, action: Permission, patterns: List[str]) -> bool:
        """匹配操作"""
        for pattern in patterns:
            if pattern == "*" or pattern == action.value:
                return True
        return False
    
    def _evaluate_conditions(self, conditions: Dict[str, Any],
                            context: Dict[str, Any]) -> bool:
        """评估条件"""
        for key, expected_value in conditions.items():
            actual_value = context.get(key)
            
            if isinstance(expected_value, dict):
                # 复杂条件
                op = expected_value.get("op")
                value = expected_value.get("value")
                
                if op == "eq" and actual_value != value:
                    return False
                elif op == "ne" and actual_value == value:
                    return False
                elif op == "gt" and not (actual_value and actual_value > value):
                    return False
                elif op == "lt" and not (actual_value and actual_value < value):
                    return False
                elif op == "in" and actual_value not in value:
                    return False
            else:
                # 简单相等
                if actual_value != expected_value:
                    return False
        
        return True


# 全局单例
_authorizer_instance: Optional[Authorizer] = None
_authorizer_lock = threading.RLock()


def get_authorizer() -> Authorizer:
    """获取授权引擎全局实例"""
    global _authorizer_instance
    if _authorizer_instance is None:
        with _authorizer_lock:
            if _authorizer_instance is None:
                _authorizer_instance = Authorizer()
    return _authorizer_instance
