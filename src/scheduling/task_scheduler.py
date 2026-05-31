"""
任务调度器模块 (阶段281-283)
实现任务调度、定时任务和优先级队列功能

Author: Agent Memory System
Version: 1.0.0
"""

import threading
import heapq
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
import uuid


# ==================== 枚举定义 ====================

class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"      # 待执行
    RUNNING = "running"      # 执行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"        # 失败
    CANCELLED = "cancelled"  # 已取消


class ScheduleType(Enum):
    """调度类型枚举"""
    ONCE = "once"            # 单次执行
    RECURRING = "recurring"  # 周期执行
    CRON = "cron"            # Cron表达式


# ==================== 数据类定义 ====================

@dataclass
class Task:
    """任务数据结构"""
    task_id: str
    name: str
    func: Optional[Callable] = None
    args: Tuple = field(default_factory=tuple)
    kwargs: Dict = field(default_factory=dict)
    priority: int = 0
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Any = None
    error: Optional[str] = None


@dataclass
class Schedule:
    """定时调度数据结构"""
    schedule_id: str
    task_name: str
    schedule_type: ScheduleType
    interval_seconds: Optional[float] = None
    cron_expr: Optional[str] = None
    next_run: Optional[datetime] = None
    enabled: bool = True
    func: Optional[Callable] = None


# ==================== 任务调度器 ====================

class TaskScheduler:
    """
    任务调度器
    
    阶段281: 任务调度
    阶段282: 定时任务
    阶段283: 优先级队列
    """
    
    def __init__(self):
        """初始化任务调度器"""
        self._lock = threading.RLock()
        
        # 任务存储
        self._tasks: Dict[str, Task] = {}
        
        # 定时调度存储
        self._schedules: Dict[str, Schedule] = {}
        
        # 优先级队列 (priority, task_id)
        self._task_queue: List[Tuple[int, str]] = []
        
        # 任务ID计数器
        self._task_counter = 0
        self._schedule_counter = 0
        
        # 调度器线程控制
        self._scheduler_running = False
        self._scheduler_thread: Optional[threading.Thread] = None
        
        # 执行线程池
        self._executor_threads: List[threading.Thread] = []
        self._max_workers = 4
    
    # ==================== 阶段281: 任务调度 ====================
    
    def _next_task_id(self) -> str:
        """
        生成下一个任务ID
        
        Returns:
            str: 唯一任务ID
        """
        with self._lock:
            self._task_counter += 1
            return f"task_{self._task_counter}_{uuid.uuid4().hex[:8]}"
    
    def submit_task(
        self,
        name: str,
        func: Callable,
        args: Optional[Tuple] = None,
        kwargs: Optional[Dict] = None,
        priority: int = 0
    ) -> str:
        """
        提交任务到调度器
        
        Args:
            name: 任务名称
            func: 任务函数
            args: 位置参数
            kwargs: 关键字参数
            priority: 优先级 (数值越大优先级越高)
            
        Returns:
            str: 任务ID
        """
        with self._lock:
            task_id = self._next_task_id()
            
            task = Task(
                task_id=task_id,
                name=name,
                func=func,
                args=args or (),
                kwargs=kwargs or {},
                priority=priority,
                status=TaskStatus.PENDING,
                created_at=datetime.now()
            )
            
            self._tasks[task_id] = task
            
            # 加入优先级队列 (使用负数实现最大堆)
            heapq.heappush(self._task_queue, (-priority, task_id))
            
            return task_id
    
    def cancel_task(self, task_id: str) -> bool:
        """
        取消任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            bool: 是否取消成功
        """
        with self._lock:
            if task_id not in self._tasks:
                return False
            
            task = self._tasks[task_id]
            
            if task.status == TaskStatus.RUNNING:
                return False  # 运行中的任务不能取消
            
            task.status = TaskStatus.CANCELLED
            task.completed_at = datetime.now()
            
            # 从队列中移除
            self._task_queue = [
                (p, tid) for p, tid in self._task_queue 
                if tid != task_id
            ]
            heapq.heapify(self._task_queue)
            
            return True
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """
        获取任务信息
        
        Args:
            task_id: 任务ID
            
        Returns:
            Optional[Task]: 任务对象，不存在则返回None
        """
        with self._lock:
            return self._tasks.get(task_id)
    
    def list_tasks(
        self,
        status: Optional[TaskStatus] = None
    ) -> List[Task]:
        """
        列出任务
        
        Args:
            status: 可选的状态过滤
            
        Returns:
            List[Task]: 任务列表
        """
        with self._lock:
            if status is None:
                return list(self._tasks.values())
            return [
                task for task in self._tasks.values()
                if task.status == status
            ]
    
    def _execute_task(self, task_id: str) -> None:
        """
        执行任务 (内部方法)
        
        Args:
            task_id: 任务ID
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.status != TaskStatus.PENDING:
                return
            
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now()
            func = task.func
            args = task.args
            kwargs = task.kwargs
        
        try:
            result = func(*args, **kwargs)
            
            with self._lock:
                task = self._tasks.get(task_id)
                if task:
                    task.status = TaskStatus.COMPLETED
                    task.result = result
                    task.completed_at = datetime.now()
                    
        except Exception as e:
            with self._lock:
                task = self._tasks.get(task_id)
                if task:
                    task.status = TaskStatus.FAILED
                    task.error = str(e)
                    task.completed_at = datetime.now()
    
    # ==================== 阶段282: 定时任务 ====================
    
    def _next_schedule_id(self) -> str:
        """
        生成下一个调度ID
        
        Returns:
            str: 唯一调度ID
        """
        with self._lock:
            self._schedule_counter += 1
            return f"schedule_{self._schedule_counter}_{uuid.uuid4().hex[:8]}"
    
    def schedule_task(
        self,
        name: str,
        schedule_type: ScheduleType,
        func: Callable,
        interval_seconds: Optional[float] = None,
        cron_expr: Optional[str] = None
    ) -> str:
        """
        创建定时任务
        
        Args:
            name: 任务名称
            schedule_type: 调度类型
            func: 任务函数
            interval_seconds: 间隔秒数 (RECURRING类型使用)
            cron_expr: Cron表达式 (CRON类型使用)
            
        Returns:
            str: 调度ID
        """
        with self._lock:
            schedule_id = self._next_schedule_id()
            
            schedule = Schedule(
                schedule_id=schedule_id,
                task_name=name,
                schedule_type=schedule_type,
                interval_seconds=interval_seconds,
                cron_expr=cron_expr,
                func=func,
                enabled=True
            )
            
            # 计算下次运行时间
            schedule.next_run = self._calculate_next_run(schedule)
            
            self._schedules[schedule_id] = schedule
            
            # 启动调度器线程
            if not self._scheduler_running:
                self._start_scheduler()
            
            return schedule_id
    
    def unschedule_task(self, schedule_id: str) -> bool:
        """
        取消定时任务
        
        Args:
            schedule_id: 调度ID
            
        Returns:
            bool: 是否取消成功
        """
        with self._lock:
            if schedule_id not in self._schedules:
                return False
            
            del self._schedules[schedule_id]
            return True
    
    def _calculate_next_run(self, schedule: Schedule) -> Optional[datetime]:
        """
        计算下次运行时间
        
        Args:
            schedule: 调度对象
            
        Returns:
            Optional[datetime]: 下次运行时间
        """
        now = datetime.now()
        
        if schedule.schedule_type == ScheduleType.ONCE:
            # 单次执行，立即执行
            return now
        
        elif schedule.schedule_type == ScheduleType.RECURRING:
            # 周期执行
            if schedule.interval_seconds is None:
                return None
            return now + timedelta(seconds=schedule.interval_seconds)
        
        elif schedule.schedule_type == ScheduleType.CRON:
            # Cron表达式解析 (简化实现)
            if schedule.cron_expr is None:
                return None
            return self._parse_cron(schedule.cron_expr, now)
        
        return None
    
    def _parse_cron(self, cron_expr: str, base: datetime) -> datetime:
        """
        解析Cron表达式 (简化实现)
        
        支持格式: minute hour day month weekday
        例如: "0 8 * * *" 表示每天8点
        
        Args:
            cron_expr: Cron表达式
            base: 基准时间
            
        Returns:
            datetime: 下次运行时间
        """
        parts = cron_expr.split()
        if len(parts) != 5:
            # 默认1小时后
            return base + timedelta(hours=1)
        
        try:
            minute = int(parts[0]) if parts[0] != '*' else base.minute
            hour = int(parts[1]) if parts[1] != '*' else base.hour
            # 简化处理：忽略day, month, weekday
            
            next_run = base.replace(minute=minute, hour=hour, second=0, microsecond=0)
            
            if next_run <= base:
                next_run += timedelta(days=1)
            
            return next_run
            
        except (ValueError, TypeError):
            return base + timedelta(hours=1)
    
    def _start_scheduler(self) -> None:
        """启动调度器线程"""
        self._scheduler_running = True
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            daemon=True
        )
        self._scheduler_thread.start()
    
    def _scheduler_loop(self) -> None:
        """调度器主循环 (后台线程)"""
        while self._scheduler_running:
            try:
                self._process_schedules()
                time.sleep(1)  # 每秒检查一次
            except Exception:
                pass  # 忽略异常，继续循环
    
    def _process_schedules(self) -> None:
        """处理到期的定时任务"""
        now = datetime.now()
        
        with self._lock:
            for schedule_id, schedule in list(self._schedules.items()):
                if not schedule.enabled:
                    continue
                
                if schedule.next_run and schedule.next_run <= now:
                    # 执行任务
                    if schedule.func:
                        try:
                            # 提交到任务队列
                            self.submit_task(
                                name=schedule.task_name,
                                func=schedule.func,
                                priority=0
                            )
                        except Exception:
                            pass
                    
                    # 更新下次运行时间
                    if schedule.schedule_type == ScheduleType.ONCE:
                        schedule.enabled = False
                    else:
                        schedule.next_run = self._calculate_next_run(schedule)
    
    def stop_scheduler(self) -> None:
        """停止调度器"""
        with self._lock:
            self._scheduler_running = False
    
    # ==================== 阶段283: 优先级队列 ====================
    
    def get_next_task(self) -> Optional[Task]:
        """
        获取并移除下一个最高优先级任务
        
        Returns:
            Optional[Task]: 下一个任务，队列为空则返回None
        """
        with self._lock:
            if not self._task_queue:
                return None
            
            # 弹出最高优先级任务
            _, task_id = heapq.heappop(self._task_queue)
            task = self._tasks.get(task_id)
            
            if task and task.status == TaskStatus.PENDING:
                return task
            
            return None
    
    def peek_next_task(self) -> Optional[Task]:
        """
        查看下一个最高优先级任务 (不移除)
        
        Returns:
            Optional[Task]: 下一个任务，队列为空则返回None
        """
        with self._lock:
            if not self._task_queue:
                return None
            
            # 查看堆顶元素
            _, task_id = self._task_queue[0]
            return self._tasks.get(task_id)
    
    def queue_size(self) -> int:
        """
        获取队列大小
        
        Returns:
            int: 队列中待处理任务数量
        """
        with self._lock:
            return len(self._task_queue)
    
    def execute_next(self) -> Optional[Any]:
        """
        执行下一个任务
        
        Returns:
            Optional[Any]: 任务结果
        """
        task = self.get_next_task()
        if task is None:
            return None
        
        self._execute_task(task.task_id)
        
        with self._lock:
            completed_task = self._tasks.get(task.task_id)
            if completed_task:
                return completed_task.result
        
        return None
    
    def execute_all_pending(self) -> List[str]:
        """
        执行所有待处理任务
        
        Returns:
            List[str]: 已执行的任务ID列表
        """
        executed_ids = []
        
        while True:
            task = self.get_next_task()
            if task is None:
                break
            
            self._execute_task(task.task_id)
            executed_ids.append(task.task_id)
        
        return executed_ids
    
    def get_queue_stats(self) -> Dict[str, int]:
        """
        获取队列统计信息
        
        Returns:
            Dict[str, int]: 各状态任务数量
        """
        with self._lock:
            stats = {status.value: 0 for status in TaskStatus}
            for task in self._tasks.values():
                stats[task.status.value] += 1
            return stats


# ==================== 全局单例 ====================

_task_scheduler_instance: Optional[TaskScheduler] = None
_task_scheduler_lock = threading.Lock()


def get_task_scheduler() -> TaskScheduler:
    """
    获取任务调度器全局单例
    
    Returns:
        TaskScheduler: 任务调度器实例
    """
    global _task_scheduler_instance
    
    if _task_scheduler_instance is None:
        with _task_scheduler_lock:
            if _task_scheduler_instance is None:
                _task_scheduler_instance = TaskScheduler()
    
    return _task_scheduler_instance
