"""
资源管理器模块 (阶段287-289)
ResourceManager: 资源池、配额管理、负载均衡

功能:
- 阶段287: 资源池管理
- 阶段288: 配额管理
- 阶段289: 负载均衡
"""

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


# ==================== 枚举定义 ====================

class ResourceType(Enum):
    """资源类型枚举"""
    CPU = "cpu"
    MEMORY = "memory"
    DISK = "disk"
    NETWORK = "network"
    CUSTOM = "custom"


class AllocationStatus(Enum):
    """分配状态枚举"""
    ALLOCATED = "allocated"
    RELEASED = "released"
    EXPIRED = "expired"


# ==================== 数据类定义 ====================

@dataclass
class Resource:
    """资源数据结构"""
    resource_id: str
    resource_type: ResourceType
    capacity: float  # 总容量
    used: float = 0.0  # 已使用量
    available: float = 0.0  # 可用量
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """初始化后计算可用量"""
        self.available = self.capacity - self.used


@dataclass
class Allocation:
    """资源分配记录"""
    allocation_id: str
    resource_id: str
    amount: float
    requester: str
    status: AllocationStatus
    allocated_at: datetime
    expires_at: Optional[datetime] = None


@dataclass
class Quota:
    """配额数据结构"""
    quota_id: str
    requester: str
    resource_type: ResourceType
    limit: float  # 配额上限
    used: float = 0.0  # 已使用量


# ==================== ResourceManager 类 ====================

class ResourceManager:
    """
    资源管理器
    
    提供资源池管理、配额管理和负载均衡功能
    """
    
    _instance: Optional['ResourceManager'] = None
    _lock: threading.RLock = threading.RLock()
    
    def __new__(cls) -> 'ResourceManager':
        """单例模式实现"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        """初始化资源管理器"""
        with self._lock:
            if self._initialized:
                return
            self._initialized = True
            
            # 资源池
            self._resources: Dict[str, Resource] = {}
            
            # 配额管理
            self._quotas: Dict[str, Quota] = {}  # key: f"{requester}:{resource_type.value}"
            
            # 分配记录
            self._allocations: Dict[str, Allocation] = {}
            
            # 负载均衡 - 资源负载记录
            self._resource_loads: Dict[str, float] = {}
            
            # 轮询索引
            self._round_robin_index: Dict[ResourceType, int] = {}
            
            # 内部锁
            self._internal_lock = threading.RLock()
    
    # ==================== 阶段287: 资源池管理 ====================
    
    def register_resource(
        self,
        resource_id: str,
        resource_type: ResourceType,
        capacity: float,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        注册资源到资源池
        
        Args:
            resource_id: 资源唯一标识
            resource_type: 资源类型
            capacity: 资源总容量
            metadata: 资源元数据
            
        Returns:
            bool: 注册是否成功
        """
        with self._internal_lock:
            if resource_id in self._resources:
                return False
            
            resource = Resource(
                resource_id=resource_id,
                resource_type=resource_type,
                capacity=capacity,
                used=0.0,
                available=capacity,
                metadata=metadata or {}
            )
            
            self._resources[resource_id] = resource
            self._resource_loads[resource_id] = 0.0
            
            # 初始化轮询索引
            if resource_type not in self._round_robin_index:
                self._round_robin_index[resource_type] = 0
            
            return True
    
    def unregister_resource(self, resource_id: str) -> bool:
        """
        从资源池注销资源
        
        Args:
            resource_id: 资源唯一标识
            
        Returns:
            bool: 注销是否成功
        """
        with self._internal_lock:
            if resource_id not in self._resources:
                return False
            
            # 检查是否有未释放的分配
            active_allocations = [
                a for a in self._allocations.values()
                if a.resource_id == resource_id and a.status == AllocationStatus.ALLOCATED
            ]
            
            if active_allocations:
                return False
            
            del self._resources[resource_id]
            if resource_id in self._resource_loads:
                del self._resource_loads[resource_id]
            
            return True
    
    def get_resource(self, resource_id: str) -> Optional[Resource]:
        """
        获取资源信息
        
        Args:
            resource_id: 资源唯一标识
            
        Returns:
            Optional[Resource]: 资源对象，不存在则返回None
        """
        with self._internal_lock:
            resource = self._resources.get(resource_id)
            if resource:
                # 返回副本以避免外部修改
                return Resource(
                    resource_id=resource.resource_id,
                    resource_type=resource.resource_type,
                    capacity=resource.capacity,
                    used=resource.used,
                    available=resource.available,
                    metadata=resource.metadata.copy()
                )
            return None
    
    def list_resources(
        self,
        resource_type: Optional[ResourceType] = None
    ) -> List[Resource]:
        """
        列出资源
        
        Args:
            resource_type: 资源类型过滤，None表示所有类型
            
        Returns:
            List[Resource]: 资源列表
        """
        with self._internal_lock:
            if resource_type is None:
                resources = list(self._resources.values())
            else:
                resources = [
                    r for r in self._resources.values()
                    if r.resource_type == resource_type
                ]
            
            # 返回副本列表
            return [
                Resource(
                    resource_id=r.resource_id,
                    resource_type=r.resource_type,
                    capacity=r.capacity,
                    used=r.used,
                    available=r.available,
                    metadata=r.metadata.copy()
                )
                for r in resources
            ]
    
    def _check_availability(self, resource_id: str, amount: float) -> bool:
        """
        检查资源可用性
        
        Args:
            resource_id: 资源唯一标识
            amount: 需要的数量
            
        Returns:
            bool: 是否有足够可用资源
        """
        resource = self._resources.get(resource_id)
        if resource is None:
            return False
        
        # 清理过期分配
        self._cleanup_expired_allocations()
        
        # 重新计算可用量
        self._recalculate_available(resource_id)
        
        return resource.available >= amount
    
    def _recalculate_available(self, resource_id: str) -> None:
        """重新计算资源可用量"""
        resource = self._resources.get(resource_id)
        if resource is None:
            return
        
        # 计算活跃分配总量
        active_used = sum(
            a.amount for a in self._allocations.values()
            if a.resource_id == resource_id and a.status == AllocationStatus.ALLOCATED
        )
        
        resource.used = active_used
        resource.available = resource.capacity - resource.used
    
    def _cleanup_expired_allocations(self) -> None:
        """清理过期的分配记录"""
        now = datetime.now()
        for allocation in self._allocations.values():
            if (allocation.status == AllocationStatus.ALLOCATED and
                allocation.expires_at and allocation.expires_at <= now):
                allocation.status = AllocationStatus.EXPIRED
                self._recalculate_available(allocation.resource_id)
    
    # ==================== 阶段288: 配额管理 ====================
    
    def set_quota(
        self,
        requester: str,
        resource_type: ResourceType,
        limit: float
    ) -> str:
        """
        设置配额
        
        Args:
            requester: 请求者标识
            resource_type: 资源类型
            limit: 配额上限
            
        Returns:
            str: 配额ID
        """
        with self._internal_lock:
            quota_key = f"{requester}:{resource_type.value}"
            
            if quota_key in self._quotas:
                quota = self._quotas[quota_key]
                quota.limit = limit
                return quota.quota_id
            
            quota_id = str(uuid.uuid4())
            quota = Quota(
                quota_id=quota_id,
                requester=requester,
                resource_type=resource_type,
                limit=limit,
                used=0.0
            )
            
            self._quotas[quota_key] = quota
            return quota_id
    
    def get_quota(
        self,
        requester: str,
        resource_type: ResourceType
    ) -> Optional[Quota]:
        """
        获取配额信息
        
        Args:
            requester: 请求者标识
            resource_type: 资源类型
            
        Returns:
            Optional[Quota]: 配额对象，不存在则返回None
        """
        with self._internal_lock:
            quota_key = f"{requester}:{resource_type.value}"
            quota = self._quotas.get(quota_key)
            
            if quota:
                return Quota(
                    quota_id=quota.quota_id,
                    requester=quota.requester,
                    resource_type=quota.resource_type,
                    limit=quota.limit,
                    used=quota.used
                )
            return None
    
    def check_quota(
        self,
        requester: str,
        resource_type: ResourceType,
        amount: float
    ) -> bool:
        """
        检查配额是否足够
        
        Args:
            requester: 请求者标识
            resource_type: 资源类型
            amount: 需要的数量
            
        Returns:
            bool: 配额是否足够
        """
        with self._internal_lock:
            quota_key = f"{requester}:{resource_type.value}"
            quota = self._quotas.get(quota_key)
            
            if quota is None:
                # 没有配额限制，默认允许
                return True
            
            return (quota.used + amount) <= quota.limit
    
    def allocate(
        self,
        resource_id: str,
        amount: float,
        requester: str,
        ttl: Optional[float] = None
    ) -> Optional[Allocation]:
        """
        分配资源
        
        Args:
            resource_id: 资源唯一标识
            amount: 分配数量
            requester: 请求者标识
            ttl: 生存时间（秒），None表示永不过期
            
        Returns:
            Optional[Allocation]: 分配记录，失败返回None
        """
        with self._internal_lock:
            resource = self._resources.get(resource_id)
            if resource is None:
                return None
            
            # 检查资源可用性
            if not self._check_availability(resource_id, amount):
                return None
            
            # 检查配额
            if not self._enforce_quota(requester, resource.resource_type, amount):
                return None
            
            # 创建分配记录
            allocation_id = str(uuid.uuid4())
            now = datetime.now()
            expires_at = now + timedelta(seconds=ttl) if ttl else None
            
            allocation = Allocation(
                allocation_id=allocation_id,
                resource_id=resource_id,
                amount=amount,
                requester=requester,
                status=AllocationStatus.ALLOCATED,
                allocated_at=now,
                expires_at=expires_at
            )
            
            self._allocations[allocation_id] = allocation
            
            # 更新资源使用量
            resource.used += amount
            resource.available -= amount
            
            # 更新配额使用量
            quota_key = f"{requester}:{resource.resource_type.value}"
            if quota_key in self._quotas:
                self._quotas[quota_key].used += amount
            
            # 更新负载
            self._update_load(resource_id)
            
            return allocation
    
    def release(self, allocation_id: str) -> bool:
        """
        释放资源分配
        
        Args:
            allocation_id: 分配记录ID
            
        Returns:
            bool: 释放是否成功
        """
        with self._internal_lock:
            allocation = self._allocations.get(allocation_id)
            if allocation is None:
                return False
            
            if allocation.status != AllocationStatus.ALLOCATED:
                return False
            
            resource = self._resources.get(allocation.resource_id)
            if resource is None:
                return False
            
            # 更新分配状态
            allocation.status = AllocationStatus.RELEASED
            
            # 更新资源使用量
            resource.used -= allocation.amount
            resource.available += allocation.amount
            
            # 更新配额使用量
            quota_key = f"{allocation.requester}:{resource.resource_type.value}"
            if quota_key in self._quotas:
                self._quotas[quota_key].used -= allocation.amount
                if self._quotas[quota_key].used < 0:
                    self._quotas[quota_key].used = 0
            
            # 更新负载
            self._update_load(allocation.resource_id)
            
            return True
    
    def _enforce_quota(
        self,
        requester: str,
        resource_type: ResourceType,
        amount: float
    ) -> bool:
        """
        强制配额检查
        
        Args:
            requester: 请求者标识
            resource_type: 资源类型
            amount: 需要的数量
            
        Returns:
            bool: 是否通过配额检查
        """
        return self.check_quota(requester, resource_type, amount)
    
    # ==================== 阶段289: 负载均衡 ====================
    
    def get_load(self, resource_id: str) -> float:
        """
        获取资源负载
        
        Args:
            resource_id: 资源唯一标识
            
        Returns:
            float: 负载值 (0.0-1.0)
        """
        with self._internal_lock:
            return self._resource_loads.get(resource_id, 0.0)
    
    def select_resource(
        self,
        resource_type: ResourceType,
        strategy: str = "least_loaded"
    ) -> Optional[str]:
        """
        选择资源（负载均衡）
        
        Args:
            resource_type: 资源类型
            strategy: 选择策略 ("least_loaded" 或 "round_robin")
            
        Returns:
            Optional[str]: 选中的资源ID，无可用资源返回None
        """
        with self._internal_lock:
            resources = [
                r for r in self._resources.values()
                if r.resource_type == resource_type and r.available > 0
            ]
            
            if not resources:
                return None
            
            if strategy == "round_robin":
                return self._round_robin(resources)
            else:  # default: least_loaded
                return self._least_loaded(resources)
    
    def _update_load(self, resource_id: str) -> None:
        """
        更新资源负载
        
        Args:
            resource_id: 资源唯一标识
        """
        resource = self._resources.get(resource_id)
        if resource is None:
            return
        
        if resource.capacity > 0:
            self._resource_loads[resource_id] = resource.used / resource.capacity
        else:
            self._resource_loads[resource_id] = 0.0
    
    def _round_robin(self, resources: List[Resource]) -> str:
        """
        轮询选择策略
        
        Args:
            resources: 可用资源列表
            
        Returns:
            str: 选中的资源ID
        """
        if not resources:
            return None
        
        resource_type = resources[0].resource_type
        
        # 获取或初始化索引
        if resource_type not in self._round_robin_index:
            self._round_robin_index[resource_type] = 0
        
        index = self._round_robin_index[resource_type] % len(resources)
        self._round_robin_index[resource_type] = (index + 1) % len(resources)
        
        return resources[index].resource_id
    
    def _least_loaded(self, resources: List[Resource]) -> str:
        """
        最小负载选择策略
        
        Args:
            resources: 可用资源列表
            
        Returns:
            str: 选中的资源ID
        """
        if not resources:
            return None
        
        # 选择负载最低的资源
        min_load = float('inf')
        selected_id = None
        
        for resource in resources:
            load = self._resource_loads.get(resource.resource_id, 0.0)
            if load < min_load:
                min_load = load
                selected_id = resource.resource_id
        
        return selected_id
    
    # ==================== 辅助方法 ====================
    
    def get_allocation(self, allocation_id: str) -> Optional[Allocation]:
        """获取分配记录"""
        with self._internal_lock:
            allocation = self._allocations.get(allocation_id)
            if allocation:
                return Allocation(
                    allocation_id=allocation.allocation_id,
                    resource_id=allocation.resource_id,
                    amount=allocation.amount,
                    requester=allocation.requester,
                    status=allocation.status,
                    allocated_at=allocation.allocated_at,
                    expires_at=allocation.expires_at
                )
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._internal_lock:
            self._cleanup_expired_allocations()
            
            return {
                "total_resources": len(self._resources),
                "total_allocations": len(self._allocations),
                "active_allocations": sum(
                    1 for a in self._allocations.values()
                    if a.status == AllocationStatus.ALLOCATED
                ),
                "total_quotas": len(self._quotas),
                "resource_types": {
                    rt.value: len([r for r in self._resources.values() if r.resource_type == rt])
                    for rt in ResourceType
                }
            }


# ==================== 全局单例获取函数 ====================

def get_resource_manager() -> ResourceManager:
    """
    获取ResourceManager全局单例
    
    Returns:
        ResourceManager: 资源管理器实例
    """
    return ResourceManager()
