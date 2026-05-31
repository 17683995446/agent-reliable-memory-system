"""
自动化运维 - 阶段203-205

功能：
- 阶段203: 自愈机制
- 阶段204: 自动扩缩容
- 阶段205: 定时任务调度

设计原则：
- 确定性规则，无模型依赖
- 最小层级，无循环依赖
- 线程安全，RLock保护
- 单例模式，全局唯一
"""

import threading
import time
import json
import functools
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Dict, List, Optional, Callable, Any, Set, Tuple
from collections import deque, defaultdict
import uuid
import hashlib
import schedule


class HealingActionType(Enum):
    """自愈动作类型"""
    RESTART = "restart"           # 重启服务
    CLEAR_CACHE = "clear_cache"   # 清理缓存
    RELOAD_CONFIG = "reload_config"  # 重载配置
    RECONNECT = "reconnect"       # 重新连接
    GC = "gc"                     # 垃圾回收
    SCALE_UP = "scale_up"         # 扩容
    SCALE_DOWN = "scale_down"     # 缩容
    ALERT = "alert"               # 仅告警
    CUSTOM = "custom"             # 自定义


class HealingStatus(Enum):
    """自愈状态"""
    PENDING = "pending"       # 待执行
    RUNNING = "running"       # 执行中
    SUCCESS = "success"       # 成功
    FAILED = "failed"         # 失败
    CANCELLED = "cancelled"   # 已取消


class ScalingDirection(Enum):
    """扩缩容方向"""
    UP = "up"       # 扩容
    DOWN = "down"   # 缩容


class ScalingMetric(Enum):
    """扩缩容指标"""
    CPU = "cpu"
    MEMORY = "memory"
    REQUESTS_PER_SEC = "requests_per_sec"
    QUEUE_LENGTH = "queue_length"
    LATENCY = "latency"
    ERROR_RATE = "error_rate"


class TaskStatus(Enum):
    """任务状态"""
    SCHEDULED = "scheduled"   # 已调度
    RUNNING = "running"       # 运行中
    COMPLETED = "completed"   # 已完成
    FAILED = "failed"         # 失败
    CANCELLED = "cancelled"   # 已取消


@dataclass
class HealingRule:
    """自愈规则"""
    rule_id: str
    name: str
    condition: Callable[[], bool]
    action_type: HealingActionType
    action: Callable[[], bool]
    cooldown_seconds: float = 300
    max_attempts: int = 3
    enabled: bool = True
    description: str = ""
    
    # 执行记录
    last_triggered: Optional[float] = None
    last_executed: Optional[float] = None
    execution_count: int = 0
    success_count: int = 0


@dataclass
class HealingRecord:
    """自愈执行记录"""
    record_id: str
    rule_id: str
    rule_name: str
    action_type: HealingActionType
    status: HealingStatus
    triggered_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    duration_ms: float = 0.0
    error_message: str = ""
    result: Any = None


@dataclass
class ScalingPolicy:
    """扩缩容策略"""
    policy_id: str
    name: str
    metric: ScalingMetric
    scale_up_threshold: float
    scale_down_threshold: float
    scale_up_step: int = 1
    scale_down_step: int = 1
    min_instances: int = 1
    max_instances: int = 10
    cooldown_seconds: float = 300
    enabled: bool = True
    
    # 当前状态
    current_instances: int = 1
    last_scaled_at: Optional[float] = None


@dataclass
class ScalingRecord:
    """扩缩容记录"""
    record_id: str
    policy_id: str
    direction: ScalingDirection
    from_instances: int
    to_instances: int
    metric_value: float
    triggered_at: float
    completed_at: Optional[float] = None
    status: str = "pending"


@dataclass
class ScheduledTask:
    """定时任务"""
    task_id: str
    name: str
    schedule_type: str  # cron, interval, once
    schedule_config: Dict[str, Any]
    task_func: Callable[[], Any]
    enabled: bool = True
    description: str = ""
    
    # 执行统计
    last_run: Optional[float] = None
    next_run: Optional[float] = None
    run_count: int = 0
    success_count: int = 0
    fail_count: int = 0
    
    # 运行时状态
    status: TaskStatus = TaskStatus.SCHEDULED
    current_job: Any = None


@dataclass
class TaskExecution:
    """任务执行记录"""
    execution_id: str
    task_id: str
    task_name: str
    status: TaskStatus
    scheduled_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    duration_ms: float = 0.0
    result: Any = None
    error_message: str = ""


class AutoOps:
    """
    自动化运维
    
    阶段203: 自愈机制
    - 自愈规则引擎
    - 自动故障恢复
    - 执行历史记录
    
    阶段204: 自动扩缩容
    - 基于指标的扩缩容
    - 扩缩容策略管理
    - 冷却期控制
    
    阶段205: 定时任务调度
    - Cron表达式支持
    - 任务执行管理
    - 执行历史追踪
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
            
            # 自愈系统
            self._healing_rules: Dict[str, HealingRule] = {}
            self._healing_records: deque = deque(maxlen=1000)
            self._healing_thread: Optional[threading.Thread] = None
            self._healing_running = False
            self._healing_interval = 30  # 30秒检查间隔
            
            # 扩缩容系统
            self._scaling_policies: Dict[str, ScalingPolicy] = {}
            self._scaling_records: deque = deque(maxlen=1000)
            self._scaling_thread: Optional[threading.Thread] = None
            self._scaling_running = False
            self._scaling_interval = 60  # 60秒检查间隔
            self._metric_provider: Optional[Callable[[ScalingMetric], float]] = None
            
            # 定时任务系统
            self._scheduled_tasks: Dict[str, ScheduledTask] = {}
            self._task_executions: deque = deque(maxlen=1000)
            self._scheduler_thread: Optional[threading.Thread] = None
            self._scheduler_running = False
            
            # 指标回调
            self._metrics_callback: Optional[Callable[[str], float]] = None
    
    # ========== 阶段203: 自愈机制 ==========
    
    def register_healing_rule(self, rule: HealingRule) -> None:
        """注册自愈规则"""
        with self._lock:
            self._healing_rules[rule.rule_id] = rule
    
    def unregister_healing_rule(self, rule_id: str) -> bool:
        """注销自愈规则"""
        with self._lock:
            if rule_id in self._healing_rules:
                del self._healing_rules[rule_id]
                return True
            return False
    
    def enable_healing_rule(self, rule_id: str) -> bool:
        """启用自愈规则"""
        with self._lock:
            rule = self._healing_rules.get(rule_id)
            if rule:
                rule.enabled = True
                return True
            return False
    
    def disable_healing_rule(self, rule_id: str) -> bool:
        """禁用自愈规则"""
        with self._lock:
            rule = self._healing_rules.get(rule_id)
            if rule:
                rule.enabled = False
                return True
            return False
    
    def evaluate_healing_rules(self) -> List[HealingRecord]:
        """评估所有自愈规则"""
        records = []
        now = time.time()
        
        with self._lock:
            rules = list(self._healing_rules.values())
        
        for rule in rules:
            if not rule.enabled:
                continue
            
            # 检查冷却期
            if rule.last_executed and \
               (now - rule.last_executed) < rule.cooldown_seconds:
                continue
            
            # 检查最大尝试次数
            if rule.execution_count >= rule.max_attempts:
                continue
            
            # 评估条件
            try:
                should_trigger = rule.condition()
            except Exception as e:
                continue
            
            if should_trigger:
                record = self._execute_healing_action(rule)
                records.append(record)
        
        return records
    
    def _execute_healing_action(self, rule: HealingRule) -> HealingRecord:
        """执行自愈动作"""
        record_id = str(uuid.uuid4())
        now = time.time()
        
        record = HealingRecord(
            record_id=record_id,
            rule_id=rule.rule_id,
            rule_name=rule.name,
            action_type=rule.action_type,
            status=HealingStatus.RUNNING,
            triggered_at=now,
            started_at=now
        )
        
        with self._lock:
            self._healing_records.append(record)
            rule.last_triggered = now
            rule.execution_count += 1
        
        try:
            result = rule.action()
            
            record.status = HealingStatus.SUCCESS
            record.result = result
            record.completed_at = time.time()
            record.duration_ms = (record.completed_at - record.started_at) * 1000
            
            with self._lock:
                rule.last_executed = record.completed_at
                rule.success_count += 1
        
        except Exception as e:
            record.status = HealingStatus.FAILED
            record.error_message = str(e)
            record.completed_at = time.time()
            record.duration_ms = (record.completed_at - record.started_at) * 1000
        
        return record
    
    def manual_heal(self, rule_id: str) -> Optional[HealingRecord]:
        """手动执行自愈"""
        with self._lock:
            rule = self._healing_rules.get(rule_id)
        
        if not rule:
            return None
        
        return self._execute_healing_action(rule)
    
    def get_healing_records(self, rule_id: Optional[str] = None,
                           limit: int = 100) -> List[HealingRecord]:
        """获取自愈记录"""
        with self._lock:
            records = list(self._healing_records)
        
        if rule_id:
            records = [r for r in records if r.rule_id == rule_id]
        
        return records[-limit:]
    
    def get_healing_stats(self) -> Dict[str, Any]:
        """获取自愈统计"""
        with self._lock:
            total_rules = len(self._healing_rules)
            enabled_rules = len([r for r in self._healing_rules.values() if r.enabled])
            
            records = list(self._healing_records)
            success_count = len([r for r in records if r.status == HealingStatus.SUCCESS])
            failed_count = len([r for r in records if r.status == HealingStatus.FAILED])
        
        return {
            "total_rules": total_rules,
            "enabled_rules": enabled_rules,
            "total_executions": len(records),
            "success_count": success_count,
            "failed_count": failed_count,
            "success_rate": (success_count / len(records) * 100) if records else 0
        }
    
    def start_healing_loop(self) -> None:
        """启动自愈循环"""
        with self._lock:
            if self._healing_running:
                return
            
            self._healing_running = True
            self._healing_thread = threading.Thread(
                target=self._healing_loop,
                daemon=True
            )
            self._healing_thread.start()
    
    def stop_healing_loop(self) -> None:
        """停止自愈循环"""
        with self._lock:
            self._healing_running = False
        
        if self._healing_thread:
            self._healing_thread.join(timeout=5.0)
    
    def _healing_loop(self) -> None:
        """自愈循环"""
        while True:
            with self._lock:
                if not self._healing_running:
                    break
            
            try:
                self.evaluate_healing_rules()
            except Exception:
                pass
            
            time.sleep(self._healing_interval)
    
    # ========== 阶段204: 自动扩缩容 ==========
    
    def register_scaling_policy(self, policy: ScalingPolicy) -> None:
        """注册扩缩容策略"""
        with self._lock:
            self._scaling_policies[policy.policy_id] = policy
    
    def unregister_scaling_policy(self, policy_id: str) -> bool:
        """注销扩缩容策略"""
        with self._lock:
            if policy_id in self._scaling_policies:
                del self._scaling_policies[policy_id]
                return True
            return False
    
    def set_metric_provider(self, provider: Callable[[ScalingMetric], float]) -> None:
        """设置指标提供者"""
        self._metric_provider = provider
    
    def evaluate_scaling_policies(self) -> List[ScalingRecord]:
        """评估所有扩缩容策略"""
        records = []
        now = time.time()
        
        with self._lock:
            policies = list(self._scaling_policies.values())
        
        for policy in policies:
            if not policy.enabled:
                continue
            
            # 检查冷却期
            if policy.last_scaled_at and \
               (now - policy.last_scaled_at) < policy.cooldown_seconds:
                continue
            
            # 获取指标值
            if self._metric_provider:
                metric_value = self._metric_provider(policy.metric)
            else:
                continue
            
            # 决定扩缩容方向
            direction = None
            if metric_value >= policy.scale_up_threshold:
                if policy.current_instances < policy.max_instances:
                    direction = ScalingDirection.UP
            elif metric_value <= policy.scale_down_threshold:
                if policy.current_instances > policy.min_instances:
                    direction = ScalingDirection.DOWN
            
            if direction:
                record = self._execute_scaling(policy, direction, metric_value)
                records.append(record)
        
        return records
    
    def _execute_scaling(self, policy: ScalingPolicy,
                         direction: ScalingDirection,
                         metric_value: float) -> ScalingRecord:
        """执行扩缩容"""
        record_id = str(uuid.uuid4())
        now = time.time()
        
        # 计算目标实例数
        from_instances = policy.current_instances
        if direction == ScalingDirection.UP:
            to_instances = min(
                from_instances + policy.scale_up_step,
                policy.max_instances
            )
        else:
            to_instances = max(
                from_instances - policy.scale_down_step,
                policy.min_instances
            )
        
        record = ScalingRecord(
            record_id=record_id,
            policy_id=policy.policy_id,
            direction=direction,
            from_instances=from_instances,
            to_instances=to_instances,
            metric_value=metric_value,
            triggered_at=now,
            status="executing"
        )
        
        with self._lock:
            self._scaling_records.append(record)
        
        # 执行扩缩容（这里只是记录，实际扩缩容需要外部实现）
        try:
            # 更新策略状态
            policy.current_instances = to_instances
            policy.last_scaled_at = time.time()
            
            record.completed_at = time.time()
            record.status = "completed"
        
        except Exception as e:
            record.status = "failed"
        
        return record
    
    def manual_scale(self, policy_id: str,
                     direction: ScalingDirection,
                     step: int = 1) -> Optional[ScalingRecord]:
        """手动扩缩容"""
        with self._lock:
            policy = self._scaling_policies.get(policy_id)
        
        if not policy:
            return None
        
        return self._execute_scaling(policy, direction, 0)
    
    def get_scaling_records(self, policy_id: Optional[str] = None,
                           limit: int = 100) -> List[ScalingRecord]:
        """获取扩缩容记录"""
        with self._lock:
            records = list(self._scaling_records)
        
        if policy_id:
            records = [r for r in records if r.policy_id == policy_id]
        
        return records[-limit:]
    
    def get_scaling_stats(self) -> Dict[str, Any]:
        """获取扩缩容统计"""
        with self._lock:
            total_policies = len(self._scaling_policies)
            enabled_policies = len([p for p in self._scaling_policies.values() if p.enabled])
            
            records = list(self._scaling_records)
            scale_up_count = len([r for r in records if r.direction == ScalingDirection.UP])
            scale_down_count = len([r for r in records if r.direction == ScalingDirection.DOWN])
        
        return {
            "total_policies": total_policies,
            "enabled_policies": enabled_policies,
            "total_scaling_operations": len(records),
            "scale_up_count": scale_up_count,
            "scale_down_count": scale_down_count
        }
    
    def start_scaling_loop(self) -> None:
        """启动扩缩容循环"""
        with self._lock:
            if self._scaling_running:
                return
            
            self._scaling_running = True
            self._scaling_thread = threading.Thread(
                target=self._scaling_loop,
                daemon=True
            )
            self._scaling_thread.start()
    
    def stop_scaling_loop(self) -> None:
        """停止扩缩容循环"""
        with self._lock:
            self._scaling_running = False
        
        if self._scaling_thread:
            self._scaling_thread.join(timeout=5.0)
    
    def _scaling_loop(self) -> None:
        """扩缩容循环"""
        while True:
            with self._lock:
                if not self._scaling_running:
                    break
            
            try:
                self.evaluate_scaling_policies()
            except Exception:
                pass
            
            time.sleep(self._scaling_interval)
    
    # ========== 阶段205: 定时任务调度 ==========
    
    def schedule_task(self, task: ScheduledTask) -> None:
        """调度任务"""
        with self._lock:
            self._scheduled_tasks[task.task_id] = task
        
        # 设置调度
        if task.schedule_type == "interval":
            interval = task.schedule_config.get("seconds", 60)
            task.current_job = schedule.every(interval).seconds.do(
                self._execute_scheduled_task, task
            )
        
        elif task.schedule_type == "cron":
            # 简化实现，只支持分钟级别
            minutes = task.schedule_config.get("minutes")
            if minutes:
                task.current_job = schedule.every(minutes).minutes.do(
                    self._execute_scheduled_task, task
                )
        
        elif task.schedule_type == "daily":
            at_time = task.schedule_config.get("at", "00:00")
            task.current_job = schedule.every().day.at(at_time).do(
                self._execute_scheduled_task, task
            )
    
    def _execute_scheduled_task(self, task: ScheduledTask) -> Any:
        """执行定时任务"""
        if not task.enabled:
            return None
        
        execution_id = str(uuid.uuid4())
        now = time.time()
        
        execution = TaskExecution(
            execution_id=execution_id,
            task_id=task.task_id,
            task_name=task.name,
            status=TaskStatus.RUNNING,
            scheduled_at=now,
            started_at=now
        )
        
        with self._lock:
            task.status = TaskStatus.RUNNING
            task.run_count += 1
            task.last_run = now
        
        try:
            result = task.task_func()
            
            execution.status = TaskStatus.COMPLETED
            execution.result = result
            execution.completed_at = time.time()
            execution.duration_ms = (execution.completed_at - execution.started_at) * 1000
            
            with self._lock:
                task.success_count += 1
                task.status = TaskStatus.SCHEDULED
        
        except Exception as e:
            execution.status = TaskStatus.FAILED
            execution.error_message = str(e)
            execution.completed_at = time.time()
            execution.duration_ms = (execution.completed_at - execution.started_at) * 1000
            
            with self._lock:
                task.fail_count += 1
                task.status = TaskStatus.SCHEDULED
        
        with self._lock:
            self._task_executions.append(execution)
        
        return execution.result
    
    def unschedule_task(self, task_id: str) -> bool:
        """取消任务调度"""
        with self._lock:
            task = self._scheduled_tasks.get(task_id)
            if not task:
                return False
            
            if task.current_job:
                schedule.cancel_job(task.current_job)
            
            del self._scheduled_tasks[task_id]
            return True
    
    def enable_task(self, task_id: str) -> bool:
        """启用任务"""
        with self._lock:
            task = self._scheduled_tasks.get(task_id)
            if task:
                task.enabled = True
                return True
            return False
    
    def disable_task(self, task_id: str) -> bool:
        """禁用任务"""
        with self._lock:
            task = self._scheduled_tasks.get(task_id)
            if task:
                task.enabled = False
                return True
            return False
    
    def run_task_now(self, task_id: str) -> Optional[TaskExecution]:
        """立即执行任务"""
        with self._lock:
            task = self._scheduled_tasks.get(task_id)
        
        if not task:
            return None
        
        self._execute_scheduled_task(task)
        
        # 返回最新的执行记录
        with self._lock:
            for execution in reversed(self._task_executions):
                if execution.task_id == task_id:
                    return execution
        
        return None
    
    def get_task_executions(self, task_id: Optional[str] = None,
                           limit: int = 100) -> List[TaskExecution]:
        """获取任务执行记录"""
        with self._lock:
            executions = list(self._task_executions)
        
        if task_id:
            executions = [e for e in executions if e.task_id == task_id]
        
        return executions[-limit:]
    
    def get_scheduled_tasks(self) -> List[ScheduledTask]:
        """获取所有定时任务"""
        with self._lock:
            return list(self._scheduled_tasks.values())
    
    def get_scheduler_stats(self) -> Dict[str, Any]:
        """获取调度器统计"""
        with self._lock:
            total_tasks = len(self._scheduled_tasks)
            enabled_tasks = len([t for t in self._scheduled_tasks.values() if t.enabled])
            
            executions = list(self._task_executions)
            success_count = len([e for e in executions if e.status == TaskStatus.COMPLETED])
            failed_count = len([e for e in executions if e.status == TaskStatus.FAILED])
        
        return {
            "total_tasks": total_tasks,
            "enabled_tasks": enabled_tasks,
            "total_executions": len(executions),
            "success_count": success_count,
            "failed_count": failed_count
        }
    
    def start_scheduler(self) -> None:
        """启动调度器"""
        with self._lock:
            if self._scheduler_running:
                return
            
            self._scheduler_running = True
            self._scheduler_thread = threading.Thread(
                target=self._scheduler_loop,
                daemon=True
            )
            self._scheduler_thread.start()
    
    def stop_scheduler(self) -> None:
        """停止调度器"""
        with self._lock:
            self._scheduler_running = False
        
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=5.0)
    
    def _scheduler_loop(self) -> None:
        """调度器循环"""
        while True:
            with self._lock:
                if not self._scheduler_running:
                    break
            
            try:
                schedule.run_pending()
            except Exception:
                pass
            
            time.sleep(1)
    
    def start_all(self) -> None:
        """启动所有自动化运维功能"""
        self.start_healing_loop()
        self.start_scaling_loop()
        self.start_scheduler()
    
    def stop_all(self) -> None:
        """停止所有自动化运维功能"""
        self.stop_healing_loop()
        self.stop_scaling_loop()
        self.stop_scheduler()
    
    def get_all_stats(self) -> Dict[str, Any]:
        """获取所有统计信息"""
        return {
            "healing": self.get_healing_stats(),
            "scaling": self.get_scaling_stats(),
            "scheduler": self.get_scheduler_stats()
        }


# 全局单例
_auto_ops_instance: Optional[AutoOps] = None
_auto_ops_lock = threading.RLock()


def get_auto_ops() -> AutoOps:
    """获取自动化运维全局实例"""
    global _auto_ops_instance
    if _auto_ops_instance is None:
        with _auto_ops_lock:
            if _auto_ops_instance is None:
                _auto_ops_instance = AutoOps()
    return _auto_ops_instance
