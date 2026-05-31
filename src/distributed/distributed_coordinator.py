"""
分布式协调器 (DistributedCoordinator)
阶段236-238: 节点管理、一致性协议、故障转移

基于第一性原则设计:
1. 确定性: 使用版本向量(Vector Clock)实现一致性，无随机性
2. 独立性: 不依赖外部协调服务(ZooKeeper/etcd)
3. 可靠性: 心跳检测+超时机制实现故障检测
"""

import threading
import time
import hashlib
from typing import Dict, List, Set, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict


class NodeStatus(Enum):
    """节点状态"""
    HEALTHY = "healthy"      # 健康
    SUSPECT = "suspect"      # 可疑
    FAILED = "failed"        # 故障
    LEAVING = "leaving"      # 正在离开
    LEFT = "left"            # 已离开


class ConsistencyLevel(Enum):
    """一致性级别"""
    ONE = "one"              # 一个节点确认
    QUORUM = "quorum"        # 多数派确认
    ALL = "all"              # 所有节点确认


@dataclass
class Node:
    """节点信息"""
    node_id: str
    address: str
    port: int
    status: NodeStatus = NodeStatus.HEALTHY
    last_heartbeat: float = field(default_factory=time.time)
    version_vector: Dict[str, int] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    joined_at: float = field(default_factory=time.time)


@dataclass
class DistributedOperation:
    """分布式操作"""
    operation_id: str
    node_id: str
    operation_type: str
    key: str
    value: Any
    timestamp: float
    version_vector: Dict[str, int]


@dataclass
class FailoverRecord:
    """故障转移记录"""
    failed_node: str
    failover_time: float
    new_primary: Optional[str]
    affected_shards: List[str]
    status: str  # "in_progress", "completed", "failed"


class DistributedCoordinator:
    """
    分布式协调器
    
    核心功能:
    1. 节点管理: 节点发现、心跳检测、状态维护
    2. 一致性协议: 版本向量(Vector Clock)、读写仲裁
    3. 故障转移: 自动故障检测、主从切换、数据重平衡
    """
    
    def __init__(self):
        self._lock = threading.RLock()
        self._node_id: str = self._generate_node_id()
        self._nodes: Dict[str, Node] = {}
        self._local_vector_clock: Dict[str, int] = {self._node_id: 0}
        
        # 故障检测配置
        self._heartbeat_interval: float = 5.0      # 心跳间隔(秒)
        self._suspect_timeout: float = 15.0        # 可疑超时(秒)
        self._fail_timeout: float = 30.0           # 故障超时(秒)
        
        # 故障转移
        self._failover_records: List[FailoverRecord] = []
        self._shard_assignments: Dict[str, str] = {}  # shard -> primary_node
        self._replication_factor: int = 3
        
        # 回调函数
        self._node_join_callbacks: List[Callable[[Node], None]] = []
        self._node_leave_callbacks: List[Callable[[Node], None]] = []
        self._failover_callbacks: List[Callable[[FailoverRecord], None]] = []
        
        # 运行状态
        self._running: bool = False
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._failure_detector_thread: Optional[threading.Thread] = None
        
        # 操作日志(用于一致性)
        self._operation_log: List[DistributedOperation] = []
        self._max_log_size: int = 10000
    
    def _generate_node_id(self) -> str:
        """生成唯一节点ID"""
        timestamp = str(time.time())
        hostname = str(threading.current_thread().ident)
        return hashlib.md5(f"{timestamp}{hostname}".encode()).hexdigest()[:16]
    
    # ==================== 阶段236: 节点管理 ====================
    
    def get_node_id(self) -> str:
        """获取本节点ID"""
        with self._lock:
            return self._node_id
    
    def join_cluster(self, node_id: str, address: str, port: int,
                     metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        节点加入集群
        
        Args:
            node_id: 节点ID
            address: 节点地址
            port: 节点端口
            metadata: 节点元数据
            
        Returns:
            是否加入成功
        """
        with self._lock:
            if node_id in self._nodes:
                # 更新现有节点
                node = self._nodes[node_id]
                node.address = address
                node.port = port
                node.status = NodeStatus.HEALTHY
                node.last_heartbeat = time.time()
                if metadata:
                    node.metadata.update(metadata)
                return True
            
            # 创建新节点
            node = Node(
                node_id=node_id,
                address=address,
                port=port,
                status=NodeStatus.HEALTHY,
                last_heartbeat=time.time(),
                metadata=metadata or {},
                version_vector={node_id: 0}
            )
            self._nodes[node_id] = node
            
            # 触发加入回调
            for callback in self._node_join_callbacks:
                try:
                    callback(node)
                except Exception:
                    pass
            
            # 重新分配分片
            self._rebalance_shards()
            
            return True
    
    def leave_cluster(self, node_id: str) -> bool:
        """
        节点离开集群
        
        Args:
            node_id: 节点ID
            
        Returns:
            是否离开成功
        """
        with self._lock:
            if node_id not in self._nodes:
                return False
            
            node = self._nodes[node_id]
            node.status = NodeStatus.LEAVING
            
            # 触发数据迁移
            self._migrate_data_from_node(node_id)
            
            node.status = NodeStatus.LEFT
            
            # 触发离开回调
            for callback in self._node_leave_callbacks:
                try:
                    callback(node)
                except Exception:
                    pass
            
            # 从集群移除
            if node_id != self._node_id:
                del self._nodes[node_id]
            
            # 重新分配分片
            self._rebalance_shards()
            
            return True
    
    def heartbeat(self, node_id: str, version_vector: Optional[Dict[str, int]] = None) -> bool:
        """
        处理心跳
        
        Args:
            node_id: 发送心跳的节点ID
            version_vector: 节点的版本向量
            
        Returns:
            是否处理成功
        """
        with self._lock:
            if node_id not in self._nodes:
                return False
            
            node = self._nodes[node_id]
            node.last_heartbeat = time.time()
            
            if node.status in (NodeStatus.SUSPECT, NodeStatus.FAILED):
                node.status = NodeStatus.HEALTHY
            
            if version_vector:
                node.version_vector.update(version_vector)
            
            return True
    
    def get_cluster_nodes(self, include_failed: bool = False) -> List[Node]:
        """
        获取集群节点列表
        
        Args:
            include_failed: 是否包含故障节点
            
        Returns:
            节点列表
        """
        with self._lock:
            nodes = []
            for node in self._nodes.values():
                if include_failed or node.status not in (NodeStatus.FAILED, NodeStatus.LEFT):
                    nodes.append(node)
            return nodes
    
    def get_healthy_nodes(self) -> List[Node]:
        """获取健康节点列表"""
        with self._lock:
            return [n for n in self._nodes.values() if n.status == NodeStatus.HEALTHY]
    
    def get_node_count(self) -> int:
        """获取节点数量"""
        with self._lock:
            return len([n for n in self._nodes.values() 
                       if n.status not in (NodeStatus.FAILED, NodeStatus.LEFT)])
    
    def _rebalance_shards(self) -> None:
        """重新平衡分片分配"""
        healthy_nodes = [n.node_id for n in self._nodes.values() 
                        if n.status == NodeStatus.HEALTHY]
        
        if not healthy_nodes:
            return
        
        # 简单的哈希分配策略
        new_assignments = {}
        for shard_id in list(self._shard_assignments.keys()):
            # 一致性哈希
            hash_val = int(hashlib.md5(shard_id.encode()).hexdigest(), 16)
            node_idx = hash_val % len(healthy_nodes)
            new_assignments[shard_id] = healthy_nodes[node_idx]
        
        self._shard_assignments = new_assignments
    
    def _migrate_data_from_node(self, node_id: str) -> None:
        """从节点迁移数据"""
        # 标记该节点上的分片需要重新分配
        shards_to_migrate = [
            shard for shard, primary in self._shard_assignments.items()
            if primary == node_id
        ]
        
        for shard in shards_to_migrate:
            if shard in self._shard_assignments:
                del self._shard_assignments[shard]
    
    # ==================== 阶段237: 一致性协议 ====================
    
    def increment_vector_clock(self) -> Dict[str, int]:
        """
        递增本地版本向量
        
        Returns:
            更新后的版本向量
        """
        with self._lock:
            self._local_vector_clock[self._node_id] = \
                self._local_vector_clock.get(self._node_id, 0) + 1
            return self._local_vector_clock.copy()
    
    def merge_vector_clocks(self, remote_clock: Dict[str, int]) -> Dict[str, int]:
        """
        合并版本向量
        
        Args:
            remote_clock: 远程版本向量
            
        Returns:
            合并后的版本向量
        """
        with self._lock:
            for node_id, timestamp in remote_clock.items():
                self._local_vector_clock[node_id] = max(
                    self._local_vector_clock.get(node_id, 0),
                    timestamp
                )
            return self._local_vector_clock.copy()
    
    def compare_vector_clocks(self, clock1: Dict[str, int], 
                              clock2: Dict[str, int]) -> str:
        """
        比较两个版本向量
        
        Args:
            clock1: 版本向量1
            clock2: 版本向量2
            
        Returns:
            "before": clock1 在 clock2 之前
            "after": clock1 在 clock2 之后
            "concurrent": 并发(冲突)
            "equal": 相等
        """
        # 检查所有节点
        all_nodes = set(clock1.keys()) | set(clock2.keys())
        
        dominates1 = False  # clock1 是否支配 clock2
        dominates2 = False  # clock2 是否支配 clock1
        
        for node_id in all_nodes:
            val1 = clock1.get(node_id, 0)
            val2 = clock2.get(node_id, 0)
            
            if val1 > val2:
                dominates1 = True
            elif val2 > val1:
                dominates2 = True
        
        if dominates1 and dominates2:
            return "concurrent"
        elif dominates1:
            return "after"
        elif dominates2:
            return "before"
        else:
            return "equal"
    
    def record_operation(self, operation_type: str, key: str, 
                         value: Any) -> DistributedOperation:
        """
        记录分布式操作
        
        Args:
            operation_type: 操作类型
            key: 键
            value: 值
            
        Returns:
            操作记录
        """
        with self._lock:
            # 递增版本向量
            self.increment_vector_clock()
            
            operation = DistributedOperation(
                operation_id=self._generate_operation_id(),
                node_id=self._node_id,
                operation_type=operation_type,
                key=key,
                value=value,
                timestamp=time.time(),
                version_vector=self._local_vector_clock.copy()
            )
            
            self._operation_log.append(operation)
            
            # 限制日志大小
            if len(self._operation_log) > self._max_log_size:
                self._operation_log = self._operation_log[-self._max_log_size:]
            
            return operation
    
    def _generate_operation_id(self) -> str:
        """生成操作ID"""
        timestamp = str(time.time())
        counter = len(self._operation_log)
        return hashlib.md5(f"{self._node_id}{timestamp}{counter}".encode()).hexdigest()[:16]
    
    def check_quorum(self, level: ConsistencyLevel, 
                     acks: int) -> Tuple[bool, int]:
        """
        检查是否达到仲裁
        
        Args:
            level: 一致性级别
            acks: 已确认数量
            
        Returns:
            (是否达到仲裁, 所需数量)
        """
        with self._lock:
            healthy_count = len(self.get_healthy_nodes())
            
            if level == ConsistencyLevel.ONE:
                required = 1
            elif level == ConsistencyLevel.QUORUM:
                required = (healthy_count // 2) + 1
            elif level == ConsistencyLevel.ALL:
                required = healthy_count
            else:
                required = 1
            
            return acks >= required, required
    
    def resolve_conflict(self, values: List[Tuple[Any, Dict[str, int]]]) -> Any:
        """
        解决并发冲突
        
        使用Last-Write-Wins策略，基于版本向量选择最新值
        
        Args:
            values: (值, 版本向量) 列表
            
        Returns:
            冲突解决后的值
        """
        if not values:
            return None
        
        if len(values) == 1:
            return values[0][0]
        
        # 找到最新的值
        latest_value = values[0][0]
        latest_clock = values[0][1]
        
        for value, clock in values[1:]:
            comparison = self.compare_vector_clocks(clock, latest_clock)
            if comparison == "after":
                latest_value = value
                latest_clock = clock
            elif comparison == "concurrent":
                # 并发冲突，使用时间戳作为决胜规则
                if sum(clock.values()) > sum(latest_clock.values()):
                    latest_value = value
                    latest_clock = clock
        
        return latest_value
    
    # ==================== 阶段238: 故障转移 ====================
    
    def start(self) -> None:
        """启动协调器"""
        with self._lock:
            if self._running:
                return
            
            self._running = True
            
            # 启动心跳线程
            self._heartbeat_thread = threading.Thread(
                target=self._heartbeat_loop,
                daemon=True
            )
            self._heartbeat_thread.start()
            
            # 启动故障检测线程
            self._failure_detector_thread = threading.Thread(
                target=self._failure_detector_loop,
                daemon=True
            )
            self._failure_detector_thread.start()
    
    def stop(self) -> None:
        """停止协调器"""
        with self._lock:
            self._running = False
    
    def _heartbeat_loop(self) -> None:
        """心跳循环"""
        while self._running:
            try:
                # 发送心跳给所有节点
                self._send_heartbeat_to_all()
                time.sleep(self._heartbeat_interval)
            except Exception:
                pass
    
    def _send_heartbeat_to_all(self) -> None:
        """向所有节点发送心跳"""
        with self._lock:
            for node_id, node in self._nodes.items():
                if node_id != self._node_id and node.status == NodeStatus.HEALTHY:
                    # 模拟发送心跳
                    pass
    
    def _failure_detector_loop(self) -> None:
        """故障检测循环"""
        while self._running:
            try:
                self._detect_failures()
                time.sleep(self._heartbeat_interval)
            except Exception:
                pass
    
    def _detect_failures(self) -> None:
        """检测故障节点"""
        with self._lock:
            current_time = time.time()
            
            for node_id, node in self._nodes.items():
                if node_id == self._node_id:
                    continue
                
                elapsed = current_time - node.last_heartbeat
                
                if node.status == NodeStatus.HEALTHY and elapsed > self._suspect_timeout:
                    # 标记为可疑
                    node.status = NodeStatus.SUSPECT
                    
                elif node.status == NodeStatus.SUSPECT and elapsed > self._fail_timeout:
                    # 标记为故障
                    node.status = NodeStatus.FAILED
                    
                    # 触发故障转移
                    self._trigger_failover(node_id)
    
    def _trigger_failover(self, failed_node_id: str) -> None:
        """
        触发故障转移
        
        Args:
            failed_node_id: 故障节点ID
        """
        # 创建故障转移记录
        record = FailoverRecord(
            failed_node=failed_node_id,
            failover_time=time.time(),
            new_primary=None,
            affected_shards=[],
            status="in_progress"
        )
        
        # 找到该节点作为主节点的分片
        affected_shards = [
            shard for shard, primary in self._shard_assignments.items()
            if primary == failed_node_id
        ]
        record.affected_shards = affected_shards
        
        # 重新分配这些分片
        healthy_nodes = [n.node_id for n in self._nodes.values() 
                        if n.status == NodeStatus.HEALTHY and n.node_id != failed_node_id]
        
        if healthy_nodes and affected_shards:
            # 选择第一个健康节点作为新的主节点
            record.new_primary = healthy_nodes[0]
            
            for shard in affected_shards:
                self._shard_assignments[shard] = record.new_primary
        
        record.status = "completed"
        self._failover_records.append(record)
        
        # 触发回调
        for callback in self._failover_callbacks:
            try:
                callback(record)
            except Exception:
                pass
    
    def get_shard_primary(self, shard_id: str) -> Optional[str]:
        """
        获取分片的主节点
        
        Args:
            shard_id: 分片ID
            
        Returns:
            主节点ID
        """
        with self._lock:
            return self._shard_assignments.get(shard_id)
    
    def assign_shard(self, shard_id: str, node_id: str) -> bool:
        """
        分配分片到节点
        
        Args:
            shard_id: 分片ID
            node_id: 节点ID
            
        Returns:
            是否分配成功
        """
        with self._lock:
            if node_id not in self._nodes:
                return False
            
            self._shard_assignments[shard_id] = node_id
            return True
    
    def get_failover_history(self, limit: int = 100) -> List[FailoverRecord]:
        """
        获取故障转移历史
        
        Args:
            limit: 返回记录数量限制
            
        Returns:
            故障转移记录列表
        """
        with self._lock:
            return self._failover_records[-limit:]
    
    def register_node_join_callback(self, callback: Callable[[Node], None]) -> None:
        """注册节点加入回调"""
        with self._lock:
            self._node_join_callbacks.append(callback)
    
    def register_node_leave_callback(self, callback: Callable[[Node], None]) -> None:
        """注册节点离开回调"""
        with self._lock:
            self._node_leave_callbacks.append(callback)
    
    def register_failover_callback(self, callback: Callable[[FailoverRecord], None]) -> None:
        """注册故障转移回调"""
        with self._lock:
            self._failover_callbacks.append(callback)


# 全局单例
_distributed_coordinator_instance: Optional[DistributedCoordinator] = None
_distributed_coordinator_lock = threading.Lock()


def get_distributed_coordinator() -> DistributedCoordinator:
    """获取分布式协调器全局单例"""
    global _distributed_coordinator_instance
    
    if _distributed_coordinator_instance is None:
        with _distributed_coordinator_lock:
            if _distributed_coordinator_instance is None:
                _distributed_coordinator_instance = DistributedCoordinator()
    
    return _distributed_coordinator_instance
