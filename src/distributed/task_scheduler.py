"""
分布式任务调度器模块 (Stage 399)

Agent Reliable Memory System - Distributed Task Scheduler
实现分布式环境下的任务调度、优先级队列、节点分配和超时处理。

设计原则:
1. First Principles: 确定性规则，无模型依赖
2. 线程安全: 使用 threading.RLock
3. 全局单例: 通过 get_task_scheduler() 双检锁实现
4. 数据结构: Python dataclass + Enum
5. 最小依赖，无循环依赖

Author: Agent Memory System
Version: 1.0.0
"""

import heapq
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ==================== 枚举定义 ====================

class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"      # 待调度
    SCHEDULED = "scheduled"  # 已调度
    RUNNING = "running"      # 执行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"        # 失败
    CANCELLED = "cancelled"  # 已取消


class TaskPriority(Enum):
    """任务优先级枚举"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


class TaskType(Enum):
    """任务类型枚举"""
    COMPUTE = "compute"   # 计算型任务
    IO = "io"             # IO型任务
    MEMORY = "memory"     # 内存型任务
    NETWORK = "network"   # 网络型任务


# ==================== 数据结构 ====================

@dataclass
class Task:
    """
    任务数据类

    Attributes:
        task_id: 唯一任务标识
        task_type: 任务类型
        priority: 任务优先级
        status: 当前状态
        payload: 任务负载数据
        assigned_node: 分配的节点ID
        created_at: 创建时间戳
        started_at: 开始执行时间戳
        completed_at: 完成时间戳
        retries: 已重试次数
        max_retries: 最大重试次数
        metadata: 额外元数据
    """
    task_id: str
    task_type: TaskType
    priority: TaskPriority
    status: TaskStatus = TaskStatus.PENDING
    payload: Any = None
    assigned_node: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    retries: int = 0
    max_retries: int = 3
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """将任务转换为字典表示"""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type.value,
            "priority": self.priority.value,
            "status": self.status.value,
            "payload": self.payload,
            "assigned_node": self.assigned_node,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "retries": self.retries,
            "max_retries": self.max_retries,
            "metadata": self.metadata,
        }


# ==================== 任务调度器 ====================

class TaskScheduler:
    """
    分布式任务调度器

    功能:
    - 任务提交与取消
    - 优先级调度 (CRITICAL > HIGH > NORMAL > LOW)
    - 轮询分配 (同优先级下轮询)
    - 指数退避重试
    - 任务超时处理
    - 节点任务追踪
    """

    # 默认任务超时时间 (秒)
    DEFAULT_TASK_TIMEOUT: float = 300.0

    def __init__(self):
        """初始化任务调度器"""
        self._lock = threading.RLock()

        # 任务存储: task_id -> Task
        self._tasks: Dict[str, Task] = {}

        # 优先级队列: 存储 (priority_value, round_robin_index, task_id)
        # 使用元组保证堆排序的稳定性
        self._queue: List[Tuple[int, int, str]] = []
        self._queue_counter: int = 0  # 轮询计数器

        # 节点任务分配: task_id -> node_id
        self._assignments: Dict[str, str] = {}

        # 节点轮询状态: node_id -> 该节点已分配任务数
        self._node_load: Dict[str, int] = {}

        # 任务超时时间 (秒)
        self._task_timeout: float = self.DEFAULT_TASK_TIMEOUT

    # ==================== 核心方法 ====================

    def submit_task(
        self,
        task_type: TaskType,
        priority: TaskPriority,
        payload: Any,
        max_retries: int = 3,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        提交新任务到调度器

        Args:
            task_type: 任务类型
            priority: 任务优先级
            payload: 任务负载数据
            max_retries: 最大重试次数 (默认3)
            metadata: 可选的元数据字典

        Returns:
            str: 生成的任务ID
        """
        with self._lock:
            task_id = f"task_{uuid.uuid4().hex}"

            task = Task(
                task_id=task_id,
                task_type=task_type,
                priority=priority,
                status=TaskStatus.PENDING,
                payload=payload,
                max_retries=max_retries,
                metadata=metadata or {},
            )

            self._tasks[task_id] = task

            # 加入优先级队列 (优先级数值大的在前，使用负值实现最大堆)
            heapq.heappush(
                self._queue,
                (-priority.value, self._queue_counter, task_id),
            )
            self._queue_counter += 1

            return task_id

    def cancel_task(self, task_id: str) -> bool:
        """
        取消任务

        Args:
            task_id: 任务ID

        Returns:
            bool: 是否取消成功 (运行中或已完成的任务无法取消)
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False

            if task.status in (TaskStatus.RUNNING, TaskStatus.COMPLETED):
                return False

            task.status = TaskStatus.CANCELLED
            task.completed_at = time.time()

            # 从队列中移除
            self._remove_from_queue(task_id)

            # 从分配记录中移除
            if task_id in self._assignments:
                node_id = self._assignments.pop(task_id)
                self._node_load[node_id] = max(0, self._node_load.get(node_id, 0) - 1)

            return True

    def assign_task(self, task_id: str, node_id: str) -> bool:
        """
        将任务分配给指定节点

        Args:
            task_id: 任务ID
            node_id: 节点ID

        Returns:
            bool: 是否分配成功
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False

            if task.status not in (TaskStatus.PENDING, TaskStatus.SCHEDULED):
                return False

            task.status = TaskStatus.SCHEDULED
            task.assigned_node = node_id
            self._assignments[task_id] = node_id
            self._node_load[node_id] = self._node_load.get(node_id, 0) + 1

            return True

    def complete_task(self, task_id: str, result: Any) -> bool:
        """
        标记任务为已完成

        Args:
            task_id: 任务ID
            result: 任务执行结果

        Returns:
            bool: 是否操作成功
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False

            if task.status != TaskStatus.RUNNING:
                return False

            task.status = TaskStatus.COMPLETED
            task.completed_at = time.time()
            task.metadata["result"] = result

            # 更新节点负载
            if task_id in self._assignments:
                node_id = self._assignments[task_id]
                self._node_load[node_id] = max(0, self._node_load.get(node_id, 0) - 1)

            return True

    def fail_task(self, task_id: str, error: str) -> bool:
        """
        标记任务为失败

        Args:
            task_id: 任务ID
            error: 错误信息

        Returns:
            bool: 是否操作成功
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False

            if task.status != TaskStatus.RUNNING:
                return False

            task.status = TaskStatus.FAILED
            task.completed_at = time.time()
            task.metadata["error"] = error

            # 更新节点负载
            if task_id in self._assignments:
                node_id = self._assignments[task_id]
                self._node_load[node_id] = max(0, self._node_load.get(node_id, 0) - 1)

            return True

    def get_task(self, task_id: str) -> Optional[Task]:
        """
        获取指定任务

        Args:
            task_id: 任务ID

        Returns:
            Optional[Task]: 任务对象，不存在则返回None
        """
        with self._lock:
            return self._tasks.get(task_id)

    def get_tasks(self, status: Optional[TaskStatus] = None) -> List[Task]:
        """
        获取任务列表

        Args:
            status: 可选的状态过滤

        Returns:
            List[Task]: 任务列表
        """
        with self._lock:
            if status is None:
                return list(self._tasks.values())
            return [task for task in self._tasks.values() if task.status == status]

    def get_pending_tasks(self) -> List[Task]:
        """
        获取所有待处理任务

        Returns:
            List[Task]: 待处理任务列表
        """
        with self._lock:
            return [
                task
                for task in self._tasks.values()
                if task.status in (TaskStatus.PENDING, TaskStatus.SCHEDULED)
            ]

    def get_tasks_by_node(self, node_id: str) -> List[Task]:
        """
        获取指定节点的所有任务

        Args:
            node_id: 节点ID

        Returns:
            List[Task]: 该节点的任务列表
        """
        with self._lock:
            return [
                task
                for task in self._tasks.values()
                if task.assigned_node == node_id
            ]

    def get_next_task(self, node_capacity: int) -> Optional[Task]:
        """
        获取下一个待分配的任务

        按优先级分配 (CRITICAL > HIGH > NORMAL > LOW)，
        同优先级下按轮询顺序分配。

        Args:
            node_capacity: 节点容量 (当前未使用，保留用于未来扩展)

        Returns:
            Optional[Task]: 下一个任务，无可用任务则返回None
        """
        with self._lock:
            # 先检查并处理超时任务
            self._handle_timeouts()

            while self._queue:
                # 弹出优先级最高的任务
                _, _, task_id = heapq.heappop(self._queue)
                task = self._tasks.get(task_id)

                if task is None:
                    continue

                if task.status not in (TaskStatus.PENDING, TaskStatus.SCHEDULED):
                    continue

                # 如果任务已被分配但仍在队列中，跳过
                if task.assigned_node is not None and task.status == TaskStatus.SCHEDULED:
                    continue

                return task

            return None

    def retry_task(self, task_id: str) -> bool:
        """
        重试失败的任务

        使用指数退避策略，重试间隔随重试次数增加而增加。

        Args:
            task_id: 任务ID

        Returns:
            bool: 是否重试成功
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False

            if task.status != TaskStatus.FAILED:
                return False

            if task.retries >= task.max_retries:
                return False

            task.retries += 1
            task.status = TaskStatus.PENDING
            task.started_at = None
            task.completed_at = None
            task.assigned_node = None

            # 指数退避: 等待 2^retries 秒
            backoff_seconds = 2 ** task.retries
            task.metadata["backoff_until"] = time.time() + backoff_seconds

            # 重新加入队列
            heapq.heappush(
                self._queue,
                (-task.priority.value, self._queue_counter, task_id),
            )
            self._queue_counter += 1

            return True

    def get_task_statistics(self) -> Dict[str, Any]:
        """
        获取任务统计信息

        Returns:
            Dict[str, Any]: 统计字典
        """
        with self._lock:
            stats = {
                "total": 0,
                "by_status": {},
                "by_priority": {},
                "by_type": {},
                "pending_count": 0,
                "running_count": 0,
                "completed_count": 0,
                "failed_count": 0,
                "cancelled_count": 0,
                "scheduled_count": 0,
                "node_load": dict(self._node_load),
                "queue_size": len(self._queue),
            }

            for status in TaskStatus:
                stats["by_status"][status.value] = 0

            for priority in TaskPriority:
                stats["by_priority"][priority.value] = 0

            for task_type in TaskType:
                stats["by_type"][task_type.value] = 0

            for task in self._tasks.values():
                stats["total"] += 1
                stats["by_status"][task.status.value] += 1
                stats["by_priority"][task.priority.value] += 1
                stats["by_type"][task.task_type.value] += 1

                if task.status == TaskStatus.PENDING:
                    stats["pending_count"] += 1
                elif task.status == TaskStatus.RUNNING:
                    stats["running_count"] += 1
                elif task.status == TaskStatus.COMPLETED:
                    stats["completed_count"] += 1
                elif task.status == TaskStatus.FAILED:
                    stats["failed_count"] += 1
                elif task.status == TaskStatus.CANCELLED:
                    stats["cancelled_count"] += 1
                elif task.status == TaskStatus.SCHEDULED:
                    stats["scheduled_count"] += 1

            return stats

    def cleanup_completed(self, max_age_seconds: float = 3600.0) -> int:
        """
        清理已完成/已取消/已失败且超过指定时间的任务

        Args:
            max_age_seconds: 最大保留时间 (秒)，默认3600秒

        Returns:
            int: 清理的任务数量
        """
        with self._lock:
            now = time.time()
            to_remove: List[str] = []

            for task_id, task in self._tasks.items():
                if task.status not in (
                    TaskStatus.COMPLETED,
                    TaskStatus.CANCELLED,
                    TaskStatus.FAILED,
                ):
                    continue

                completed_at = task.completed_at
                if completed_at is None:
                    completed_at = task.created_at

                if now - completed_at > max_age_seconds:
                    to_remove.append(task_id)

            for task_id in to_remove:
                del self._tasks[task_id]
                if task_id in self._assignments:
                    node_id = self._assignments.pop(task_id)
                    self._node_load[node_id] = max(
                        0, self._node_load.get(node_id, 0) - 1
                    )

            # 重建队列，移除已清理的任务
            self._queue = [
                (prio, idx, tid)
                for prio, idx, tid in self._queue
                if tid in self._tasks
            ]
            heapq.heapify(self._queue)

            return len(to_remove)

    # ==================== 内部方法 ====================

    def _remove_from_queue(self, task_id: str) -> None:
        """从优先级队列中移除指定任务"""
        self._queue = [
            (prio, idx, tid)
            for prio, idx, tid in self._queue
            if tid != task_id
        ]
        heapq.heapify(self._queue)

    def _handle_timeouts(self) -> None:
        """处理超时任务"""
        now = time.time()
        for task in self._tasks.values():
            if task.status != TaskStatus.RUNNING:
                continue

            started_at = task.started_at
            if started_at is None:
                continue

            if now - started_at > self._task_timeout:
                # 任务超时，标记为失败
                task.status = TaskStatus.FAILED
                task.completed_at = now
                task.metadata["error"] = "Task timed out"

                # 更新节点负载
                if task.task_id in self._assignments:
                    node_id = self._assignments[task.task_id]
                    self._node_load[node_id] = max(
                        0, self._node_load.get(node_id, 0) - 1
                    )

    def set_task_timeout(self, timeout_seconds: float) -> None:
        """
        设置任务超时时间

        Args:
            timeout_seconds: 超时时间 (秒)
        """
        with self._lock:
            self._task_timeout = timeout_seconds

    def start_task(self, task_id: str) -> bool:
        """
        标记任务开始执行

        Args:
            task_id: 任务ID

        Returns:
            bool: 是否操作成功
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False

            if task.status not in (TaskStatus.PENDING, TaskStatus.SCHEDULED):
                return False

            task.status = TaskStatus.RUNNING
            task.started_at = time.time()
            return True


# ==================== 全局单例 ====================

_task_scheduler_instance: Optional[TaskScheduler] = None
_task_scheduler_lock = threading.Lock()


def get_task_scheduler() -> TaskScheduler:
    """
    获取任务调度器全局单例 (双检锁)

    Returns:
        TaskScheduler: 任务调度器实例
    """
    global _task_scheduler_instance

    if _task_scheduler_instance is None:
        with _task_scheduler_lock:
            if _task_scheduler_instance is None:
                _task_scheduler_instance = TaskScheduler()

    return _task_scheduler_instance


def reset_task_scheduler() -> None:
    """
    重置任务调度器单例 (仅用于测试)
    """
    global _task_scheduler_instance

    with _task_scheduler_lock:
        _task_scheduler_instance = None
