"""
L1 瞬时工作记忆模块
阶段 24-25：搭建L1瞬时内存缓存架构，实现字典+队列容器
阶段 46：开发L1瞬时记忆存储逻辑，绑定临时任务场景
阶段 56：开发L1任务结束自动清空遗忘功能

核心特性：
- 基于 Python dict + deque 实现，零外部依赖
- 纳秒级读写延迟
- 任务结束自动清空
- 会话隔离
"""

import time
import threading
from collections import deque, defaultdict
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class L1MemoryItem:
    """L1 记忆条目"""
    session_id: str
    task_id: str
    step_index: int
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


class L1EphemeralMemory:
    """
    L1 瞬时工作记忆
    
    存储单任务实时运行上下文，生命周期为单次任务周期。
    使用内存字典 + 队列实现，保证低延迟、易销毁。
    """
    
    def __init__(self, max_items: int = 100, max_content_length: int = 4096):
        """
        初始化 L1 瞬时记忆
        
        Args:
            max_items: 单个会话上下文最大条目数
            max_content_length: 单条内容最大字符数
        """
        self.max_items = max_items
        self.max_content_length = max_content_length
        
        # 核心数据结构：session_id -> deque of L1MemoryItem
        self._storage: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_items))
        
        # 任务状态跟踪：session_id -> {task_id, status, start_time}
        self._task_status: Dict[str, Dict] = {}
        
        # 线程锁（保证并发安全）
        self._lock = threading.RLock()
        
        # 统计信息
        self._stats = {
            "total_writes": 0,
            "total_reads": 0,
            "total_evictions": 0,
            "active_sessions": 0
        }
    
    def store(self, session_id: str, task_id: str, content: str, 
              step_index: int = 0, metadata: Optional[Dict] = None) -> bool:
        """
        存储记忆条目
        
        Args:
            session_id: 会话ID
            task_id: 任务ID
            content: 记忆内容
            step_index: 步骤索引
            metadata: 元数据
            
        Returns:
            bool: 是否存储成功
        """
        # 内容截断
        if len(content) > self.max_content_length:
            content = content[:self.max_content_length]
        
        item = L1MemoryItem(
            session_id=session_id,
            task_id=task_id,
            step_index=step_index,
            content=content,
            metadata=metadata or {}
        )
        
        with self._lock:
            # 检查是否为新会话
            if session_id not in self._storage:
                self._stats["active_sessions"] += 1
            
            # 存储到队列
            self._storage[session_id].append(item)
            
            # 更新任务状态
            self._task_status[session_id] = {
                "task_id": task_id,
                "status": "in_progress",
                "start_time": time.time(),
                "last_update": time.time()
            }
            
            self._stats["total_writes"] += 1
            
        return True
    
    def get_context(self, session_id: str, task_id: Optional[str] = None,
                    limit: Optional[int] = None) -> List[L1MemoryItem]:
        """
        获取当前上下文
        
        Args:
            session_id: 会话ID
            task_id: 任务ID（可选，用于过滤）
            limit: 返回条数限制
            
        Returns:
            List[L1MemoryItem]: 记忆条目列表
        """
        with self._lock:
            if session_id not in self._storage:
                return []
            
            items = list(self._storage[session_id])
            
            # 按任务ID过滤
            if task_id:
                items = [item for item in items if item.task_id == task_id]
            
            # 限制条数
            if limit:
                items = items[-limit:]
            
            self._stats["total_reads"] += 1
            
        return items
    
    def get_current_task(self, session_id: str) -> Optional[Dict]:
        """
        获取当前进行中的任务
        
        Args:
            session_id: 会话ID
            
        Returns:
            Optional[Dict]: 任务信息
        """
        with self._lock:
            status = self._task_status.get(session_id)
            if status and status["status"] == "in_progress":
                return status
            return None
    
    def complete_task(self, session_id: str, task_id: str) -> bool:
        """
        标记任务完成，触发自动清空
        
        Args:
            session_id: 会话ID
            task_id: 任务ID
            
        Returns:
            bool: 是否成功
        """
        with self._lock:
            status = self._task_status.get(session_id)
            if not status or status["task_id"] != task_id:
                return False
            
            # 标记完成
            status["status"] = "completed"
            status["end_time"] = time.time()
            
            # 自动清空 L1 记忆（阶段 56：动态遗忘）
            self._clear_session(session_id)
            
        return True
    
    def fail_task(self, session_id: str, task_id: str) -> bool:
        """
        标记任务失败，触发自动清空
        
        Args:
            session_id: 会话ID
            task_id: 任务ID
            
        Returns:
            bool: 是否成功
        """
        with self._lock:
            status = self._task_status.get(session_id)
            if not status or status["task_id"] != task_id:
                return False
            
            # 标记失败
            status["status"] = "failed"
            status["end_time"] = time.time()
            
            # 自动清空 L1 记忆
            self._clear_session(session_id)
            
        return True
    
    def _clear_session(self, session_id: str):
        """清空会话记忆（内部方法）"""
        if session_id in self._storage:
            evicted_count = len(self._storage[session_id])
            del self._storage[session_id]
            self._stats["total_evictions"] += evicted_count
            self._stats["active_sessions"] -= 1
    
    def delete(self, session_id: str, index: Optional[int] = None) -> bool:
        """
        删除记忆条目
        
        Args:
            session_id: 会话ID
            index: 条目索引（None表示全部删除）
            
        Returns:
            bool: 是否成功
        """
        with self._lock:
            if session_id not in self._storage:
                return False
            
            if index is None:
                # 删除全部
                self._clear_session(session_id)
            else:
                # 删除指定索引（deque 不支持按索引删除，转换为列表操作）
                items = list(self._storage[session_id])
                if 0 <= index < len(items):
                    items.pop(index)
                    self._storage[session_id] = deque(items, maxlen=self.max_items)
                    self._stats["total_evictions"] += 1
                else:
                    return False
            
        return True
    
    def get_stats(self) -> Dict[str, int]:
        """
        获取统计信息
        
        Returns:
            Dict[str, int]: 统计信息
        """
        with self._lock:
            return self._stats.copy()
    
    def health_check(self) -> Dict[str, Any]:
        """
        健康检查
        
        Returns:
            Dict[str, Any]: 健康状态
        """
        with self._lock:
            return {
                "status": "healthy",
                "active_sessions": self._stats["active_sessions"],
                "total_items": sum(len(q) for q in self._storage.values()),
                "memory_usage_mb": self._estimate_memory(),
                "latency_ms": "<1"  # 纳秒级，小于1ms
            }
    
    def _estimate_memory(self) -> float:
        """估算内存使用（MB）"""
        total_chars = 0
        for queue in self._storage.values():
            for item in queue:
                total_chars += len(item.content)
        # 粗略估算：每个字符 2 bytes + 对象开销
        return round(total_chars * 2 / 1024 / 1024, 2)


# 全局单例实例
_l1_memory_instance: Optional[L1EphemeralMemory] = None


def get_l1_memory(config: Optional[Dict] = None) -> L1EphemeralMemory:
    """
    获取 L1 记忆全局实例（单例模式）
    
    Args:
        config: 配置字典
        
    Returns:
        L1EphemeralMemory: L1 记忆实例
    """
    global _l1_memory_instance
    if _l1_memory_instance is None:
        if config:
            _l1_memory_instance = L1EphemeralMemory(
                max_items=config.get("max_context_items", 100),
                max_content_length=config.get("max_content_length", 4096)
            )
        else:
            _l1_memory_instance = L1EphemeralMemory()
    return _l1_memory_instance
