"""
节点管理器模块 (Node Manager)

第396阶段: 分布式节点管理
- 节点注册与发现
- 领导者选举
- 心跳检测
- 法定人数管理

设计原则:
1. 第一性原理: 确定性规则, 不依赖模型
2. 使用 threading.RLock 保证线程安全
3. 通过 get_node_manager() 实现全局单例, 采用双检锁
4. 使用 Python dataclasses 定义数据结构, Enum 定义类型
5. 最小依赖, 无循环依赖
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any


class NodeStatus(Enum):
    """节点状态枚举"""
    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"
    DEGRADED = "degraded"
    MAINTENANCE = "maintenance"


class NodeRole(Enum):
    """节点角色枚举"""
    LEADER = "leader"
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    OBSERVER = "observer"


@dataclass
class NodeInfo:
    """节点信息数据类"""
    node_id: str
    host: str
    port: int
    role: NodeRole
    status: NodeStatus
    capacity: int
    load: float = 0.0
    last_heartbeat: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if isinstance(self.role, str):
            self.role = NodeRole(self.role)
        if isinstance(self.status, str):
            self.status = NodeStatus(self.status)


@dataclass
class ClusterConfig:
    """集群配置数据类"""
    cluster_id: str
    nodes: List[str] = field(default_factory=list)
    quorum_size: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class NodeManager:
    """
    节点管理器

    管理分布式集群中的节点注册、状态维护、领导者选举和法定人数检查。
    所有操作均线程安全。
    """

    def __init__(self) -> None:
        self._nodes: Dict[str, NodeInfo] = {}
        self._leader_id: Optional[str] = None
        self._lock: threading.RLock = threading.RLock()

    def register_node(
        self,
        node_id: str,
        host: str,
        port: int,
        role: NodeRole,
        capacity: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        注册新节点

        Args:
            node_id: 节点唯一标识
            host: 主机地址
            port: 端口号
            role: 节点角色
            capacity: 节点容量
            metadata: 可选元数据

        Returns:
            注册成功返回 True, 节点已存在返回 False
        """
        with self._lock:
            if node_id in self._nodes:
                return False
            self._nodes[node_id] = NodeInfo(
                node_id=node_id,
                host=host,
                port=port,
                role=role,
                status=NodeStatus.ONLINE,
                capacity=capacity,
                load=0.0,
                last_heartbeat=time.time(),
                metadata=metadata or {},
            )
            # 如果注册的是领导者且当前无领导者, 更新领导者
            if role == NodeRole.LEADER and self._leader_id is None:
                self._leader_id = node_id
            return True

    def unregister_node(self, node_id: str) -> bool:
        """
        注销节点

        Args:
            node_id: 节点唯一标识

        Returns:
            注销成功返回 True, 节点不存在返回 False
        """
        with self._lock:
            if node_id not in self._nodes:
                return False
            del self._nodes[node_id]
            if self._leader_id == node_id:
                self._leader_id = None
            return True

    def get_node(self, node_id: str) -> Optional[NodeInfo]:
        """
        获取指定节点信息

        Args:
            node_id: 节点唯一标识

        Returns:
            节点信息, 不存在返回 None
        """
        with self._lock:
            return self._nodes.get(node_id)

    def get_all_nodes(self) -> List[NodeInfo]:
        """
        获取所有节点信息

        Returns:
            所有节点信息列表
        """
        with self._lock:
            return list(self._nodes.values())

    def get_nodes_by_status(self, status: NodeStatus) -> List[NodeInfo]:
        """
        按状态获取节点

        Args:
            status: 节点状态

        Returns:
            符合状态的节点列表
        """
        with self._lock:
            return [node for node in self._nodes.values() if node.status == status]

    def get_nodes_by_role(self, role: NodeRole) -> List[NodeInfo]:
        """
        按角色获取节点

        Args:
            role: 节点角色

        Returns:
            符合角色的节点列表
        """
        with self._lock:
            return [node for node in self._nodes.values() if node.role == role]

    def update_node_status(self, node_id: str, status: NodeStatus) -> bool:
        """
        更新节点状态

        Args:
            node_id: 节点唯一标识
            status: 新状态

        Returns:
            更新成功返回 True, 节点不存在返回 False
        """
        with self._lock:
            node = self._nodes.get(node_id)
            if node is None:
                return False
            node.status = status
            # 如果节点变为离线或维护状态, 且是领导者, 清除领导者
            if status in (NodeStatus.OFFLINE, NodeStatus.MAINTENANCE) and self._leader_id == node_id:
                self._leader_id = None
            return True

    def update_node_load(self, node_id: str, load: float) -> bool:
        """
        更新节点负载

        Args:
            node_id: 节点唯一标识
            load: 新负载值

        Returns:
            更新成功返回 True, 节点不存在返回 False
        """
        with self._lock:
            node = self._nodes.get(node_id)
            if node is None:
                return False
            node.load = load
            return True

    def heartbeat(self, node_id: str) -> bool:
        """
        处理节点心跳

        Args:
            node_id: 节点唯一标识

        Returns:
            心跳处理成功返回 True, 节点不存在返回 False
        """
        with self._lock:
            node = self._nodes.get(node_id)
            if node is None:
                return False
            node.last_heartbeat = time.time()
            # 如果节点之前离线, 恢复为在线
            if node.status == NodeStatus.OFFLINE:
                node.status = NodeStatus.ONLINE
            return True

    def elect_leader(self) -> Optional[str]:
        """
        选举领导者

        按节点标识字典序升序选择第一个在线节点作为领导者。
        确定性规则, 不依赖模型。

        Returns:
            选举出的领导者节点标识, 无可选节点返回 None
        """
        with self._lock:
            candidates = [
                node_id
                for node_id, node in self._nodes.items()
                if node.status == NodeStatus.ONLINE and node.role != NodeRole.OBSERVER
            ]
            if not candidates:
                self._leader_id = None
                return None
            candidates.sort()
            self._leader_id = candidates[0]
            # 更新节点角色
            for node_id in candidates:
                self._nodes[node_id].role = NodeRole.FOLLOWER
            self._nodes[self._leader_id].role = NodeRole.LEADER
            return self._leader_id

    def get_leader(self) -> Optional[NodeInfo]:
        """
        获取当前领导者节点信息

        Returns:
            领导者节点信息, 无领导者返回 None
        """
        with self._lock:
            if self._leader_id is None:
                return None
            return self._nodes.get(self._leader_id)

    def get_quorum_size(self) -> int:
        """
        获取法定人数大小

        法定人数为节点总数的多数 ( majority ):
        quorum = floor(n / 2) + 1

        Returns:
            法定人数大小
        """
        with self._lock:
            total = len(self._nodes)
            return (total // 2) + 1

    def is_quorum_available(self) -> bool:
        """
        检查法定人数是否可用

        Returns:
            在线节点数达到法定人数返回 True
        """
        with self._lock:
            online_count = sum(
                1 for node in self._nodes.values() if node.status == NodeStatus.ONLINE
            )
            return online_count >= self.get_quorum_size()

    def get_cluster_stats(self) -> Dict[str, Any]:
        """
        获取集群统计信息

        Returns:
            包含集群各项统计的字典
        """
        with self._lock:
            total_nodes = len(self._nodes)
            online_nodes = sum(
                1 for node in self._nodes.values() if node.status == NodeStatus.ONLINE
            )
            status_counts: Dict[str, int] = {}
            role_counts: Dict[str, int] = {}
            total_capacity = 0
            total_load = 0.0

            for node in self._nodes.values():
                status_counts[node.status.value] = status_counts.get(node.status.value, 0) + 1
                role_counts[node.role.value] = role_counts.get(node.role.value, 0) + 1
                total_capacity += node.capacity
                total_load += node.load

            return {
                "total_nodes": total_nodes,
                "online_nodes": online_nodes,
                "quorum_size": self.get_quorum_size(),
                "quorum_available": self.is_quorum_available(),
                "leader_id": self._leader_id,
                "status_counts": status_counts,
                "role_counts": role_counts,
                "total_capacity": total_capacity,
                "average_load": total_load / total_nodes if total_nodes > 0 else 0.0,
            }

    def cleanup_stale(self, timeout_seconds: int = 30) -> int:
        """
        清理超时未心跳的节点

        Args:
            timeout_seconds: 心跳超时秒数

        Returns:
            清理的节点数量
        """
        with self._lock:
            now = time.time()
            stale_nodes = [
                node_id
                for node_id, node in self._nodes.items()
                if now - node.last_heartbeat > timeout_seconds
            ]
            for node_id in stale_nodes:
                self._nodes[node_id].status = NodeStatus.OFFLINE
                if self._leader_id == node_id:
                    self._leader_id = None
            return len(stale_nodes)


# 全局单例实例与锁
_node_manager_instance: Optional[NodeManager] = None
_node_manager_lock: threading.Lock = threading.Lock()


def get_node_manager() -> NodeManager:
    """
    获取 NodeManager 全局单例

    使用双检锁 (double-checked locking) 实现线程安全的延迟初始化。

    Returns:
        NodeManager 单例实例
    """
    global _node_manager_instance
    if _node_manager_instance is None:
        with _node_manager_lock:
            if _node_manager_instance is None:
                _node_manager_instance = NodeManager()
    return _node_manager_instance


def reset_node_manager() -> None:
    """
    重置 NodeManager 单例

    主要用于测试场景, 清除当前单例实例以便重新初始化。
    """
    global _node_manager_instance
    with _node_manager_lock:
        _node_manager_instance = None
