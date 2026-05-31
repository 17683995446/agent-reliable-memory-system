"""
工作流引擎模块 (阶段284-286)
实现工作流定义、状态机和分支合并功能

Author: Agent Memory System
Version: 1.0.0
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed


# ==================== 枚举定义 ====================

class WorkflowStatus(Enum):
    """工作流状态枚举"""
    PENDING = "pending"    # 待执行
    RUNNING = "running"    # 执行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"      # 失败
    PAUSED = "paused"      # 已暂停


class StepStatus(Enum):
    """步骤状态枚举"""
    PENDING = "pending"    # 待执行
    RUNNING = "running"    # 执行中
    SKIPPED = "skipped"    # 已跳过
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"      # 失败


class StepType(Enum):
    """步骤类型枚举"""
    TASK = "task"          # 普通任务
    CONDITION = "condition"  # 条件分支
    PARALLEL = "parallel"  # 并行执行
    SERIAL = "serial"      # 串行执行


# ==================== 数据类定义 ====================

@dataclass
class WorkflowStep:
    """工作流步骤数据结构"""
    step_id: str
    name: str
    step_type: StepType
    task_func: Optional[Callable] = None
    condition_func: Optional[Callable] = None
    next_steps: List[str] = field(default_factory=list)
    on_success: Optional[str] = None
    on_failure: Optional[str] = None
    sub_steps: List[str] = field(default_factory=list)  # 用于PARALLEL/SERIAL类型


@dataclass
class WorkflowInstance:
    """工作流实例数据结构"""
    instance_id: str
    workflow_id: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    context: Dict = field(default_factory=dict)
    current_step: Optional[str] = None
    step_results: Dict[str, Any] = field(default_factory=dict)
    step_statuses: Dict[str, StepStatus] = field(default_factory=dict)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


@dataclass
class WorkflowDefinition:
    """工作流定义数据结构"""
    workflow_id: str
    name: str
    steps: Dict[str, WorkflowStep] = field(default_factory=dict)
    start_step: Optional[str] = None
    on_complete: Optional[Callable] = None
    on_failure: Optional[Callable] = None


# ==================== 工作流引擎 ====================

class WorkflowEngine:
    """
    工作流引擎
    
    阶段284: 工作流定义
    阶段285: 状态机
    阶段286: 分支合并
    """
    
    def __init__(self):
        """初始化工作流引擎"""
        self._lock = threading.RLock()
        
        # 工作流定义存储
        self._workflows: Dict[str, WorkflowDefinition] = {}
        
        # 工作流实例存储
        self._instances: Dict[str, WorkflowInstance] = {}
        
        # ID计数器
        self._workflow_counter = 0
        self._instance_counter = 0
        self._step_counter = 0
        
        # 并行执行线程池
        self._executor = ThreadPoolExecutor(max_workers=4)
    
    # ==================== 阶段284: 工作流定义 ====================
    
    def _next_workflow_id(self) -> str:
        """
        生成下一个工作流ID
        
        Returns:
            str: 唯一工作流ID
        """
        with self._lock:
            self._workflow_counter += 1
            return f"workflow_{self._workflow_counter}_{uuid.uuid4().hex[:8]}"
    
    def _next_step_id(self) -> str:
        """
        生成下一个步骤ID
        
        Returns:
            str: 唯一步骤ID
        """
        with self._lock:
            self._step_counter += 1
            return f"step_{self._step_counter}_{uuid.uuid4().hex[:8]}"
    
    def _next_instance_id(self) -> str:
        """
        生成下一个实例ID
        
        Returns:
            str: 唯一实例ID
        """
        with self._lock:
            self._instance_counter += 1
            return f"instance_{self._instance_counter}_{uuid.uuid4().hex[:8]}"
    
    def define_workflow(
        self,
        name: str,
        steps: List[WorkflowStep],
        start_step: Optional[str] = None
    ) -> str:
        """
        定义工作流
        
        Args:
            name: 工作流名称
            steps: 步骤列表
            start_step: 起始步骤ID (可选，默认使用第一个步骤)
            
        Returns:
            str: 工作流ID
        """
        with self._lock:
            workflow_id = self._next_workflow_id()
            
            # 构建步骤字典
            steps_dict: Dict[str, WorkflowStep] = {}
            for step in steps:
                steps_dict[step.step_id] = step
            
            # 确定起始步骤
            actual_start = start_step
            if actual_start is None and steps:
                actual_start = steps[0].step_id
            
            workflow = WorkflowDefinition(
                workflow_id=workflow_id,
                name=name,
                steps=steps_dict,
                start_step=actual_start
            )
            
            self._workflows[workflow_id] = workflow
            return workflow_id
    
    def get_workflow(self, workflow_id: str) -> Optional[WorkflowDefinition]:
        """
        获取工作流定义
        
        Args:
            workflow_id: 工作流ID
            
        Returns:
            Optional[WorkflowDefinition]: 工作流定义
        """
        with self._lock:
            return self._workflows.get(workflow_id)
    
    def list_workflows(self) -> List[WorkflowDefinition]:
        """
        列出所有工作流
        
        Returns:
            List[WorkflowDefinition]: 工作流列表
        """
        with self._lock:
            return list(self._workflows.values())
    
    def add_step(
        self,
        workflow_id: str,
        step: WorkflowStep
    ) -> bool:
        """
        向工作流添加步骤
        
        Args:
            workflow_id: 工作流ID
            step: 步骤对象
            
        Returns:
            bool: 是否添加成功
        """
        with self._lock:
            workflow = self._workflows.get(workflow_id)
            if workflow is None:
                return False
            
            workflow.steps[step.step_id] = step
            
            # 如果是第一个步骤，设为起始步骤
            if workflow.start_step is None:
                workflow.start_step = step.step_id
            
            return True
    
    def create_step(
        self,
        name: str,
        step_type: StepType,
        task_func: Optional[Callable] = None,
        condition_func: Optional[Callable] = None,
        next_steps: Optional[List[str]] = None,
        on_success: Optional[str] = None,
        on_failure: Optional[str] = None,
        sub_steps: Optional[List[str]] = None
    ) -> WorkflowStep:
        """
        创建工作流步骤
        
        Args:
            name: 步骤名称
            step_type: 步骤类型
            task_func: 任务函数
            condition_func: 条件函数
            next_steps: 后续步骤列表
            on_success: 成功时跳转的步骤
            on_failure: 失败时跳转的步骤
            sub_steps: 子步骤列表 (用于PARALLEL/SERIAL)
            
        Returns:
            WorkflowStep: 步骤对象
        """
        step_id = self._next_step_id()
        
        return WorkflowStep(
            step_id=step_id,
            name=name,
            step_type=step_type,
            task_func=task_func,
            condition_func=condition_func,
            next_steps=next_steps or [],
            on_success=on_success,
            on_failure=on_failure,
            sub_steps=sub_steps or []
        )
    
    # ==================== 阶段285: 状态机 ====================
    
    def start_workflow(
        self,
        workflow_id: str,
        context: Optional[Dict] = None
    ) -> str:
        """
        启动工作流
        
        Args:
            workflow_id: 工作流ID
            context: 初始上下文
            
        Returns:
            str: 实例ID
        """
        with self._lock:
            workflow = self._workflows.get(workflow_id)
            if workflow is None:
                raise ValueError(f"工作流不存在: {workflow_id}")
            
            instance_id = self._next_instance_id()
            
            instance = WorkflowInstance(
                instance_id=instance_id,
                workflow_id=workflow_id,
                status=WorkflowStatus.RUNNING,
                context=context or {},
                current_step=workflow.start_step,
                started_at=datetime.now()
            )
            
            # 初始化所有步骤状态
            for step_id in workflow.steps:
                instance.step_statuses[step_id] = StepStatus.PENDING
            
            self._instances[instance_id] = instance
        
        # 开始执行
        self._run_workflow(instance_id)
        
        return instance_id
    
    def pause_workflow(self, instance_id: str) -> bool:
        """
        暂停工作流
        
        Args:
            instance_id: 实例ID
            
        Returns:
            bool: 是否暂停成功
        """
        with self._lock:
            instance = self._instances.get(instance_id)
            if instance is None:
                return False
            
            if instance.status != WorkflowStatus.RUNNING:
                return False
            
            instance.status = WorkflowStatus.PAUSED
            return True
    
    def resume_workflow(self, instance_id: str) -> bool:
        """
        恢复工作流
        
        Args:
            instance_id: 实例ID
            
        Returns:
            bool: 是否恢复成功
        """
        with self._lock:
            instance = self._instances.get(instance_id)
            if instance is None:
                return False
            
            if instance.status != WorkflowStatus.PAUSED:
                return False
            
            instance.status = WorkflowStatus.RUNNING
        
        # 继续执行
        self._run_workflow(instance_id)
        return True
    
    def cancel_workflow(self, instance_id: str) -> bool:
        """
        取消工作流
        
        Args:
            instance_id: 实例ID
            
        Returns:
            bool: 是否取消成功
        """
        with self._lock:
            instance = self._instances.get(instance_id)
            if instance is None:
                return False
            
            if instance.status in (WorkflowStatus.COMPLETED, WorkflowStatus.FAILED):
                return False
            
            instance.status = WorkflowStatus.FAILED
            instance.completed_at = datetime.now()
            instance.error = "用户取消"
            return True
    
    def get_instance(self, instance_id: str) -> Optional[WorkflowInstance]:
        """
        获取工作流实例
        
        Args:
            instance_id: 实例ID
            
        Returns:
            Optional[WorkflowInstance]: 实例对象
        """
        with self._lock:
            return self._instances.get(instance_id)
    
    def _run_workflow(self, instance_id: str) -> None:
        """
        运行工作流 (内部方法)
        
        Args:
            instance_id: 实例ID
        """
        while True:
            with self._lock:
                instance = self._instances.get(instance_id)
                if instance is None:
                    break
                
                if instance.status != WorkflowStatus.RUNNING:
                    break
                
                current_step_id = instance.current_step
                if current_step_id is None:
                    # 工作流完成
                    instance.status = WorkflowStatus.COMPLETED
                    instance.completed_at = datetime.now()
                    break
                
                workflow = self._workflows.get(instance.workflow_id)
                if workflow is None:
                    break
                
                current_step = workflow.steps.get(current_step_id)
                if current_step is None:
                    break
            
            # 执行当前步骤
            next_step_id = self._transition_step(instance_id, current_step_id)
            
            with self._lock:
                instance = self._instances.get(instance_id)
                if instance and instance.status == WorkflowStatus.RUNNING:
                    instance.current_step = next_step_id
    
    def _transition_step(
        self,
        instance_id: str,
        step_id: str
    ) -> Optional[str]:
        """
        步骤转换 (内部方法)
        
        Args:
            instance_id: 实例ID
            step_id: 当前步骤ID
            
        Returns:
            Optional[str]: 下一个步骤ID
        """
        with self._lock:
            instance = self._instances.get(instance_id)
            if instance is None:
                return None
            
            workflow = self._workflows.get(instance.workflow_id)
            if workflow is None:
                return None
            
            step = workflow.steps.get(step_id)
            if step is None:
                return None
            
            instance.step_statuses[step_id] = StepStatus.RUNNING
        
        # 执行步骤
        try:
            result = self._execute_step(instance_id, step)
            
            with self._lock:
                instance = self._instances.get(instance_id)
                if instance:
                    instance.step_statuses[step_id] = StepStatus.COMPLETED
                    instance.step_results[step_id] = result
            
            # 确定下一步
            if step.on_success:
                return step.on_success
            elif step.next_steps:
                return step.next_steps[0]
            return None
            
        except Exception as e:
            with self._lock:
                instance = self._instances.get(instance_id)
                if instance:
                    instance.step_statuses[step_id] = StepStatus.FAILED
                    instance.step_results[step_id] = str(e)
            
            if step.on_failure:
                return step.on_failure
            return None
    
    def _execute_step(
        self,
        instance_id: str,
        step: WorkflowStep
    ) -> Any:
        """
        执行步骤 (内部方法)
        
        Args:
            instance_id: 实例ID
            step: 步骤对象
            
        Returns:
            Any: 执行结果
        """
        with self._lock:
            instance = self._instances.get(instance_id)
            if instance is None:
                raise ValueError("实例不存在")
            context = instance.context.copy()
        
        if step.step_type == StepType.TASK:
            # 普通任务
            if step.task_func:
                result = step.task_func(context)
                with self._lock:
                    instance = self._instances.get(instance_id)
                    if instance:
                        instance.context.update(result if isinstance(result, dict) else {})
                return result
            return None
        
        elif step.step_type == StepType.CONDITION:
            # 条件分支
            if step.condition_func:
                branch = self._evaluate_condition(step.condition_func, context)
                return {"branch": branch}
            return None
        
        elif step.step_type == StepType.PARALLEL:
            # 并行执行
            with self._lock:
                workflow = self._workflows.get(
                    self._instances.get(instance_id).workflow_id
                )
                if workflow is None:
                    return None
                sub_steps = [
                    workflow.steps[sid] for sid in step.sub_steps
                    if sid in workflow.steps
                ]
            
            results = self._execute_parallel(sub_steps, context)
            merged = self._merge_results(results)
            
            with self._lock:
                instance = self._instances.get(instance_id)
                if instance:
                    instance.context.update(merged)
            
            return results
        
        elif step.step_type == StepType.SERIAL:
            # 串行执行
            with self._lock:
                workflow = self._workflows.get(
                    self._instances.get(instance_id).workflow_id
                )
                if workflow is None:
                    return None
                sub_steps = [
                    workflow.steps[sid] for sid in step.sub_steps
                    if sid in workflow.steps
                ]
            
            results = self._execute_serial(sub_steps, context)
            merged = self._merge_results(results)
            
            with self._lock:
                instance = self._instances.get(instance_id)
                if instance:
                    instance.context.update(merged)
            
            return results
        
        return None
    
    # ==================== 阶段286: 分支合并 ====================
    
    def _evaluate_condition(
        self,
        condition_func: Callable,
        context: Dict
    ) -> bool:
        """
        评估条件
        
        Args:
            condition_func: 条件函数
            context: 上下文
            
        Returns:
            bool: 条件结果
        """
        try:
            return bool(condition_func(context))
        except Exception:
            return False
    
    def _execute_parallel(
        self,
        steps: List[WorkflowStep],
        context: Dict
    ) -> Dict[str, Any]:
        """
        并行执行多个步骤
        
        Args:
            steps: 步骤列表
            context: 上下文
            
        Returns:
            Dict[str, Any]: 各步骤结果
        """
        results: Dict[str, Any] = {}
        
        def execute_single(step: WorkflowStep) -> Tuple[str, Any]:
            if step.task_func:
                try:
                    result = step.task_func(context.copy())
                    return (step.step_id, result)
                except Exception as e:
                    return (step.step_id, {"error": str(e)})
            return (step.step_id, None)
        
        # 使用线程池并行执行
        futures = {
            self._executor.submit(execute_single, step): step
            for step in steps
        }
        
        for future in as_completed(futures):
            try:
                step_id, result = future.result()
                results[step_id] = result
            except Exception as e:
                step = futures[future]
                results[step.step_id] = {"error": str(e)}
        
        return results
    
    def _execute_serial(
        self,
        steps: List[WorkflowStep],
        context: Dict
    ) -> Dict[str, Any]:
        """
        串行执行多个步骤
        
        Args:
            steps: 步骤列表
            context: 上下文
            
        Returns:
            Dict[str, Any]: 各步骤结果
        """
        results: Dict[str, Any] = {}
        current_context = context.copy()
        
        for step in steps:
            if step.task_func:
                try:
                    result = step.task_func(current_context)
                    results[step.step_id] = result
                    
                    # 更新上下文
                    if isinstance(result, dict):
                        current_context.update(result)
                        
                except Exception as e:
                    results[step.step_id] = {"error": str(e)}
                    # 串行执行遇到错误时停止
                    break
            else:
                results[step.step_id] = None
        
        return results
    
    def _merge_results(
        self,
        results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        合并多个步骤的结果
        
        Args:
            results: 各步骤结果
            
        Returns:
            Dict[str, Any]: 合并后的上下文
        """
        merged: Dict[str, Any] = {}
        
        for step_id, result in results.items():
            if isinstance(result, dict):
                # 过滤错误信息
                filtered = {
                    k: v for k, v in result.items()
                    if k != "error"
                }
                merged.update(filtered)
            else:
                merged[step_id] = result
        
        return merged
    
    # ==================== 辅助方法 ====================
    
    def list_instances(
        self,
        status: Optional[WorkflowStatus] = None
    ) -> List[WorkflowInstance]:
        """
        列出工作流实例
        
        Args:
            status: 可选的状态过滤
            
        Returns:
            List[WorkflowInstance]: 实例列表
        """
        with self._lock:
            if status is None:
                return list(self._instances.values())
            return [
                inst for inst in self._instances.values()
                if inst.status == status
            ]
    
    def get_workflow_stats(self) -> Dict[str, int]:
        """
        获取工作流统计信息
        
        Returns:
            Dict[str, int]: 统计信息
        """
        with self._lock:
            return {
                "workflows": len(self._workflows),
                "instances": len(self._instances),
                "running": sum(
                    1 for inst in self._instances.values()
                    if inst.status == WorkflowStatus.RUNNING
                ),
                "completed": sum(
                    1 for inst in self._instances.values()
                    if inst.status == WorkflowStatus.COMPLETED
                ),
                "failed": sum(
                    1 for inst in self._instances.values()
                    if inst.status == WorkflowStatus.FAILED
                )
            }
    
    def delete_workflow(self, workflow_id: str) -> bool:
        """
        删除工作流定义
        
        Args:
            workflow_id: 工作流ID
            
        Returns:
            bool: 是否删除成功
        """
        with self._lock:
            if workflow_id not in self._workflows:
                return False
            
            # 检查是否有运行中的实例
            for instance in self._instances.values():
                if instance.workflow_id == workflow_id:
                    if instance.status == WorkflowStatus.RUNNING:
                        return False
            
            del self._workflows[workflow_id]
            return True


# ==================== 全局单例 ====================

_workflow_engine_instance: Optional[WorkflowEngine] = None
_workflow_engine_lock = threading.Lock()


def get_workflow_engine() -> WorkflowEngine:
    """
    获取工作流引擎全局单例
    
    Returns:
        WorkflowEngine: 工作流引擎实例
    """
    global _workflow_engine_instance
    
    if _workflow_engine_instance is None:
        with _workflow_engine_lock:
            if _workflow_engine_instance is None:
                _workflow_engine_instance = WorkflowEngine()
    
    return _workflow_engine_instance
