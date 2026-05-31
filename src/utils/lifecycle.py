"""
Agent可靠记忆系统 - 记忆生命周期状态机
阶段170-172: 记忆状态转换、生命周期管理、自动状态迁移

设计原则:
- 确定性规则驱动，无模型依赖
- 线程安全（RLock）
- 全局单例模式
- 严格的状态转换约束
- 可扩展的状态和事件定义
"""

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Callable, Any, Tuple
from collections import defaultdict


class MemoryState(Enum):
    """记忆状态"""
    DRAFT = "draft"              # 草稿（刚创建，未验证）
    ACTIVE = "active"            # 活跃（正常使用中）
    PINNED = "pinned"            # 固定（重要，不会被自动清理）
    ARCHIVED = "archived"        # 归档（不活跃但保留）
    FROZEN = "frozen"            # 冻结（只读，不可修改）
    DEPRECATED = "deprecated"    # 弃用（标记为过时）
    EXPIRED = "expired"          # 过期（超过TTL）
    PENDING_REVIEW = "pending_review"  # 待审核
    PENDING_DELETE = "pending_delete"  # 待删除
    DELETED = "deleted"          # 已删除（软删除）


class StateEvent(Enum):
    """状态转换事件"""
    CREATE = "create"                    # 创建记忆
    ACTIVATE = "activate"                # 激活
    PIN = "pin"                          # 固定
    UNPIN = "unpin"                      # 取消固定
    ARCHIVE = "archive"                  # 归档
    UNARCHIVE = "unarchive"              # 取消归档
    FREEZE = "freeze"                    # 冻结
    UNFREEZE = "unfreeze"                # 解冻
    DEPRECATE = "deprecate"              # 弃用
    RESTORE = "restore"                  # 恢复
    EXPIRE = "expire"                    # 过期
    REFRESH = "refresh"                  # 刷新（重置TTL）
    REQUEST_REVIEW = "request_review"    # 请求审核
    APPROVE = "approve"                  # 审核通过
    REJECT = "reject"                    # 审核拒绝
    REQUEST_DELETE = "request_delete"    # 请求删除
    CANCEL_DELETE = "cancel_delete"      # 取消删除
    DELETE = "delete"                    # 删除
    RECOVER = "recover"                  # 恢复删除
    PURGE = "purge"                      # 永久清除


@dataclass
class StateTransition:
    """状态转换规则"""
    from_state: MemoryState
    event: StateEvent
    to_state: MemoryState
    guard: Optional[str] = None          # 守卫条件名称
    auto: bool = False                   # 是否自动转换
    priority: int = 0                    # 优先级

    def to_dict(self) -> Dict:
        return {
            "from": self.from_state.value,
            "event": self.event.value,
            "to": self.to_state.value,
            "guard": self.guard,
            "auto": self.auto,
            "priority": self.priority,
        }


@dataclass
class StateRecord:
    """状态记录"""
    memory_id: str
    state: MemoryState
    previous_state: Optional[MemoryState] = None
    event: Optional[StateEvent] = None
    timestamp: float = field(default_factory=time.time)
    reason: str = ""
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "memory_id": self.memory_id,
            "state": self.state.value,
            "previous_state": self.previous_state.value if self.previous_state else None,
            "event": self.event.value if self.event else None,
            "timestamp": self.timestamp,
            "reason": self.reason,
            "metadata": self.metadata,
        }


@dataclass
class LifecycleConfig:
    """生命周期配置"""
    default_ttl_seconds: float = 30 * 24 * 3600   # 默认TTL: 30天
    draft_ttl_seconds: float = 24 * 3600           # 草稿TTL: 1天
    archived_ttl_seconds: float = 90 * 24 * 3600   # 归档TTL: 90天
    deprecated_ttl_seconds: float = 7 * 24 * 3600  # 弃用TTL: 7天
    pending_delete_ttl_seconds: float = 3 * 24 * 3600  # 待删除TTL: 3天
    max_access_count_threshold: int = 100           # 高访问量阈值
    min_access_count_threshold: int = 0             # 低访问量阈值
    inactive_days_threshold: int = 30              # 不活跃天数阈值
    auto_archive_enabled: bool = True               # 自动归档
    auto_expire_enabled: bool = True                # 自动过期
    auto_delete_enabled: bool = False               # 自动删除（默认关闭）
    review_required_for_delete: bool = True         # 删除需要审核

    def get_ttl(self, state: MemoryState) -> float:
        """获取指定状态的TTL"""
        ttl_map = {
            MemoryState.DRAFT: self.draft_ttl_seconds,
            MemoryState.ACTIVE: self.default_ttl_seconds,
            MemoryState.ARCHIVED: self.archived_ttl_seconds,
            MemoryState.DEPRECATED: self.deprecated_ttl_seconds,
            MemoryState.PENDING_DELETE: self.pending_delete_ttl_seconds,
            MemoryState.PINNED: float('inf'),       # 固定记忆不过期
            MemoryState.FROZEN: float('inf'),       # 冻结记忆不过期
        }
        return ttl_map.get(state, self.default_ttl_seconds)


class LifecycleStateMachine:
    """
    记忆生命周期状态机

    功能:
    - 严格的状态转换控制
    - 状态转换守卫条件
    - 自动状态迁移（基于时间和访问模式）
    - 状态历史记录
    - 生命周期统计
    - 自定义守卫条件和钩子
    """

    def __init__(self, config: Optional[LifecycleConfig] = None):
        self._lock = threading.RLock()
        self._config = config or LifecycleConfig()
        self._states: Dict[str, MemoryState] = {}           # memory_id -> current state
        self._created_at: Dict[str, float] = {}             # memory_id -> creation timestamp
        self._state_changed_at: Dict[str, float] = {}       # memory_id -> last state change time
        self._access_counts: Dict[str, int] = {}            # memory_id -> access count
        self._last_accessed: Dict[str, float] = {}          # memory_id -> last access time
        self._history: Dict[str, List[StateRecord]] = {}    # memory_id -> list of records
        self._transitions: Dict[str, StateTransition] = {}  # "from_state::event" -> transition
        self._guards: Dict[str, Callable] = {}              # guard_name -> callable
        self._hooks: Dict[str, List[Callable]] = defaultdict(list)  # event -> [callbacks]

        self._init_transitions()
        self._init_guards()

    def _init_transitions(self):
        """初始化状态转换规则"""
        rules = [
            # 创建
            StateTransition(MemoryState.DRAFT, StateEvent.CREATE, MemoryState.DRAFT),
            StateTransition(MemoryState.DRAFT, StateEvent.ACTIVATE, MemoryState.ACTIVE),
            # 活跃状态
            StateTransition(MemoryState.ACTIVE, StateEvent.PIN, MemoryState.PINNED),
            StateTransition(MemoryState.ACTIVE, StateEvent.ARCHIVE, MemoryState.ARCHIVED),
            StateTransition(MemoryState.ACTIVE, StateEvent.FREEZE, MemoryState.FROZEN),
            StateTransition(MemoryState.ACTIVE, StateEvent.DEPRECATE, MemoryState.DEPRECATED),
            StateTransition(MemoryState.ACTIVE, StateEvent.REQUEST_REVIEW, MemoryState.PENDING_REVIEW),
            StateTransition(MemoryState.ACTIVE, StateEvent.REQUEST_DELETE, MemoryState.PENDING_DELETE,
                           guard="review_required_false"),
            StateTransition(MemoryState.ACTIVE, StateEvent.EXPIRE, MemoryState.EXPIRED, auto=True),
            # 固定状态
            StateTransition(MemoryState.PINNED, StateEvent.UNPIN, MemoryState.ACTIVE),
            StateTransition(MemoryState.PINNED, StateEvent.ARCHIVE, MemoryState.ARCHIVED),
            StateTransition(MemoryState.PINNED, StateEvent.FREEZE, MemoryState.FROZEN),
            # 归档状态
            StateTransition(MemoryState.ARCHIVED, StateEvent.UNARCHIVE, MemoryState.ACTIVE),
            StateTransition(MemoryState.ARCHIVED, StateEvent.FREEZE, MemoryState.FROZEN),
            StateTransition(MemoryState.ARCHIVED, StateEvent.EXPIRE, MemoryState.EXPIRED, auto=True),
            StateTransition(MemoryState.ARCHIVED, StateEvent.REQUEST_DELETE, MemoryState.PENDING_DELETE),
            # 冻结状态
            StateTransition(MemoryState.FROZEN, StateEvent.UNFREEZE, MemoryState.ACTIVE),
            # 弃用状态
            StateTransition(MemoryState.DEPRECATED, StateEvent.RESTORE, MemoryState.ACTIVE),
            StateTransition(MemoryState.DEPRECATED, StateEvent.ARCHIVE, MemoryState.ARCHIVED),
            StateTransition(MemoryState.DEPRECATED, StateEvent.EXPIRE, MemoryState.EXPIRED, auto=True),
            # 过期状态
            StateTransition(MemoryState.EXPIRED, StateEvent.REFRESH, MemoryState.ACTIVE),
            StateTransition(MemoryState.EXPIRED, StateEvent.ARCHIVE, MemoryState.ARCHIVED),
            StateTransition(MemoryState.EXPIRED, StateEvent.REQUEST_DELETE, MemoryState.PENDING_DELETE),
            # 待审核
            StateTransition(MemoryState.PENDING_REVIEW, StateEvent.APPROVE, MemoryState.ACTIVE),
            StateTransition(MemoryState.PENDING_REVIEW, StateEvent.REJECT, MemoryState.DRAFT),
            StateTransition(MemoryState.PENDING_REVIEW, StateEvent.REQUEST_DELETE, MemoryState.PENDING_DELETE),
            # 待删除
            StateTransition(MemoryState.PENDING_DELETE, StateEvent.DELETE, MemoryState.DELETED),
            StateTransition(MemoryState.PENDING_DELETE, StateEvent.CANCEL_DELETE, MemoryState.ACTIVE),
            # 已删除
            StateTransition(MemoryState.DELETED, StateEvent.RECOVER, MemoryState.ACTIVE),
            StateTransition(MemoryState.DELETED, StateEvent.PURGE, MemoryState.DELETED),
        ]

        for rule in rules:
            key = f"{rule.from_state.value}::{rule.event.value}"
            self._transitions[key] = rule

    def _init_guards(self):
        """初始化守卫条件"""
        self._guards["review_required_false"] = (
            lambda ctx: not self._config.review_required_for_delete
        )

    # ==================== 状态操作 ====================

    def register_memory(self, memory_id: str,
                        initial_state: MemoryState = MemoryState.DRAFT) -> StateRecord:
        """
        注册记忆到状态机

        Args:
            memory_id: 记忆ID
            initial_state: 初始状态
        """
        with self._lock:
            now = time.time()
            self._states[memory_id] = initial_state
            self._created_at[memory_id] = now
            self._state_changed_at[memory_id] = now
            self._access_counts[memory_id] = 0
            self._last_accessed[memory_id] = now
            self._history[memory_id] = []

            record = StateRecord(
                memory_id=memory_id,
                state=initial_state,
                event=StateEvent.CREATE,
                timestamp=now,
                reason="记忆注册",
            )
            self._history[memory_id].append(record)
            self._fire_hooks(StateEvent.CREATE, record)
            return record

    def transition(self, memory_id: str, event: StateEvent,
                   reason: str = "", metadata: Optional[Dict] = None) -> StateRecord:
        """
        执行状态转换

        Args:
            memory_id: 记忆ID
            event: 触发事件
            reason: 转换原因
            metadata: 额外元数据

        Returns:
            状态记录

        Raises:
            ValueError: 无效的转换
            KeyError: 记忆未注册
        """
        with self._lock:
            if memory_id not in self._states:
                raise KeyError(f"记忆 '{memory_id}' 未注册到状态机")

            current_state = self._states[memory_id]
            key = f"{current_state.value}::{event.value}"

            rule = self._transitions.get(key)
            if not rule:
                raise ValueError(
                    f"无效的状态转换: {current_state.value} + {event.value}"
                )

            # 检查守卫条件
            if rule.guard and rule.guard in self._guards:
                ctx = {
                    "memory_id": memory_id,
                    "current_state": current_state,
                    "event": event,
                    "config": self._config,
                }
                if not self._guards[rule.guard](ctx):
                    raise ValueError(
                        f"守卫条件 '{rule.guard}' 不满足，"
                        f"无法从 {current_state.value} 通过 {event.value} 转换"
                    )

            # 执行转换
            previous_state = current_state
            new_state = rule.to_state
            now = time.time()

            self._states[memory_id] = new_state
            self._state_changed_at[memory_id] = now

            record = StateRecord(
                memory_id=memory_id,
                state=new_state,
                previous_state=previous_state,
                event=event,
                timestamp=now,
                reason=reason,
                metadata=metadata or {},
            )
            self._history[memory_id].append(record)
            self._fire_hooks(event, record)

            return record

    def can_transition(self, memory_id: str, event: StateEvent) -> bool:
        """检查是否可以执行状态转换"""
        with self._lock:
            if memory_id not in self._states:
                return False

            current_state = self._states[memory_id]
            key = f"{current_state.value}::{event.value}"
            return key in self._transitions

    def get_state(self, memory_id: str) -> Optional[MemoryState]:
        """获取记忆当前状态"""
        with self._lock:
            return self._states.get(memory_id)

    def get_available_events(self, memory_id: str) -> List[StateEvent]:
        """获取记忆可用的转换事件"""
        with self._lock:
            if memory_id not in self._states:
                return []

            current_state = self._states[memory_id]
            events = []

            for key, rule in self._transitions.items():
                if rule.from_state == current_state:
                    events.append(rule.event)

            return events

    def get_state_diagram(self) -> Dict:
        """获取状态转换图（用于可视化）"""
        with self._lock:
            nodes = []
            for state in MemoryState:
                nodes.append({
                    "id": state.value,
                    "label": state.value.replace("_", " ").title(),
                })

            edges = []
            for rule in self._transitions.values():
                edges.append({
                    "from": rule.from_state.value,
                    "to": rule.to_state.value,
                    "event": rule.event.value,
                    "auto": rule.auto,
                    "guard": rule.guard,
                })

            return {"nodes": nodes, "edges": edges}

    # ==================== 访问追踪 ====================

    def record_access(self, memory_id: str):
        """记录记忆访问"""
        with self._lock:
            if memory_id in self._access_counts:
                self._access_counts[memory_id] += 1
                self._last_accessed[memory_id] = time.time()

    def get_access_info(self, memory_id: str) -> Dict:
        """获取记忆访问信息"""
        with self._lock:
            return {
                "memory_id": memory_id,
                "access_count": self._access_counts.get(memory_id, 0),
                "last_accessed": self._last_accessed.get(memory_id, 0),
                "state_age_seconds": (
                    time.time() - self._state_changed_at.get(memory_id, time.time())
                    if memory_id in self._state_changed_at else 0
                ),
                "total_age_seconds": (
                    time.time() - self._created_at.get(memory_id, time.time())
                    if memory_id in self._created_at else 0
                ),
            }

    # ==================== 自动状态迁移 ====================

    def run_auto_transitions(self) -> List[StateRecord]:
        """
        运行自动状态迁移

        检查所有记忆，根据TTL和访问模式自动转换状态

        Returns:
            执行的转换记录列表
        """
        with self._lock:
            records = []
            now = time.time()

            for memory_id, state in list(self._states.items()):
                # 跳过固定和冻结的记忆
                if state in (MemoryState.PINNED, MemoryState.FROZEN, MemoryState.DELETED):
                    continue

                state_age = now - self._state_changed_at.get(memory_id, now)
                ttl = self._config.get_ttl(state)

                # TTL过期检查
                if self._config.auto_expire_enabled and ttl != float('inf'):
                    if state_age >= ttl:
                        try:
                            record = self.transition(
                                memory_id, StateEvent.EXPIRE,
                                reason=f"TTL过期 (状态: {state.value}, "
                                       f"存活: {state_age/3600:.1f}小时, "
                                       f"TTL: {ttl/3600:.1f}小时)"
                            )
                            records.append(record)
                            continue
                        except ValueError:
                            pass

                # 自动归档检查（活跃记忆长时间未访问）
                if (self._config.auto_archive_enabled and
                        state == MemoryState.ACTIVE):
                    last_access = self._last_accessed.get(memory_id, 0)
                    inactive_seconds = now - last_access
                    inactive_days = inactive_seconds / (24 * 3600)

                    if inactive_days >= self._config.inactive_days_threshold:
                        try:
                            record = self.transition(
                                memory_id, StateEvent.ARCHIVE,
                                reason=f"自动归档: {inactive_days:.1f}天未访问"
                            )
                            records.append(record)
                        except ValueError:
                            pass

                # 草稿自动过期
                if state == MemoryState.DRAFT:
                    draft_age = now - self._created_at.get(memory_id, now)
                    if draft_age >= self._config.draft_ttl_seconds:
                        try:
                            record = self.transition(
                                memory_id, StateEvent.EXPIRE,
                                reason=f"草稿自动过期 ({draft_age/3600:.1f}小时)"
                            )
                            records.append(record)
                        except ValueError:
                            pass

                # 待删除自动执行删除
                if (self._config.auto_delete_enabled and
                        state == MemoryState.PENDING_DELETE):
                    pending_age = now - self._state_changed_at.get(memory_id, now)
                    if pending_age >= self._config.pending_delete_ttl_seconds:
                        try:
                            record = self.transition(
                                memory_id, StateEvent.DELETE,
                                reason=f"待删除超时自动删除 ({pending_age/3600:.1f}小时)"
                            )
                            records.append(record)
                        except ValueError:
                            pass

            return records

    # ==================== 批量操作 ====================

    def batch_transition(self, memory_ids: List[str], event: StateEvent,
                         reason: str = "") -> Dict:
        """批量状态转换"""
        with self._lock:
            success = 0
            failed = 0
            errors = []

            for mid in memory_ids:
                try:
                    self.transition(mid, event, reason=reason)
                    success += 1
                except (ValueError, KeyError) as e:
                    failed += 1
                    errors.append({"memory_id": mid, "error": str(e)})

            return {
                "total": len(memory_ids),
                "success": success,
                "failed": failed,
                "errors": errors[:10],
            }

    def batch_register(self, memory_ids: List[str],
                       initial_state: MemoryState = MemoryState.DRAFT) -> int:
        """批量注册记忆"""
        with self._lock:
            count = 0
            for mid in memory_ids:
                if mid not in self._states:
                    self.register_memory(mid, initial_state)
                    count += 1
            return count

    # ==================== 查询与统计 ====================

    def get_history(self, memory_id: str,
                    limit: int = 50) -> List[StateRecord]:
        """获取记忆的状态历史"""
        with self._lock:
            records = self._history.get(memory_id, [])
            return records[-limit:]

    def get_memories_by_state(self, state: MemoryState) -> List[str]:
        """获取指定状态的所有记忆ID"""
        with self._lock:
            return [
                mid for mid, s in self._states.items() if s == state
            ]

    def get_state_distribution(self) -> Dict[str, int]:
        """获取状态分布"""
        with self._lock:
            distribution: Dict[str, int] = {}
            for state in self._states.values():
                sv = state.value
                distribution[sv] = distribution.get(sv, 0) + 1
            return distribution

    def get_expiring_soon(self, hours: int = 24) -> List[Dict]:
        """
        获取即将过期的记忆

        Args:
            hours: 未来N小时内将过期
        """
        with self._lock:
            now = time.time()
            result = []

            for memory_id, state in self._states.items():
                if state in (MemoryState.PINNED, MemoryState.FROZEN, MemoryState.DELETED):
                    continue

                ttl = self._config.get_ttl(state)
                if ttl == float('inf'):
                    continue

                state_age = now - self._state_changed_at.get(memory_id, now)
                remaining = ttl - state_age

                if 0 < remaining <= hours * 3600:
                    result.append({
                        "memory_id": memory_id,
                        "state": state.value,
                        "remaining_seconds": remaining,
                        "remaining_hours": round(remaining / 3600, 2),
                        "ttl_hours": round(ttl / 3600, 2),
                    })

            result.sort(key=lambda x: x["remaining_seconds"])
            return result

    def get_stats(self) -> Dict:
        """获取状态机统计"""
        with self._lock:
            distribution = self.get_state_distribution()
            total = len(self._states)

            state_ages = []
            for mid in self._states:
                age = time.time() - self._state_changed_at.get(mid, time.time())
                state_ages.append(age)

            return {
                "total_memories": total,
                "state_distribution": distribution,
                "avg_state_age_hours": round(
                    sum(state_ages) / len(state_ages) / 3600, 2
                ) if state_ages else 0,
                "max_state_age_hours": round(
                    max(state_ages) / 3600, 2
                ) if state_ages else 0,
                "total_transitions": sum(
                    len(h) for h in self._history.values()
                ),
                "config": {
                    "auto_archive": self._config.auto_archive_enabled,
                    "auto_expire": self._config.auto_expire_enabled,
                    "auto_delete": self._config.auto_delete_enabled,
                    "default_ttl_days": self._config.default_ttl_seconds / 86400,
                },
            }

    # ==================== 钩子与扩展 ====================

    def register_hook(self, event: StateEvent, callback: Callable[[StateRecord], None]):
        """
        注册状态转换钩子

        Args:
            event: 监听的事件
            callback: 回调函数，接收StateRecord参数
        """
        with self._lock:
            self._hooks[event.value].append(callback)

    def register_guard(self, name: str, guard_fn: Callable[[Dict], bool]):
        """
        注册守卫条件

        Args:
            name: 守卫名称
            guard_fn: 守卫函数，接收上下文字典，返回bool
        """
        with self._lock:
            self._guards[name] = guard_fn

    def _fire_hooks(self, event: StateEvent, record: StateRecord):
        """触发钩子"""
        for callback in self._hooks.get(event.value, []):
            try:
                callback(record)
            except Exception:
                pass  # 钩子异常不影响主流程

    # ==================== 清理 ====================

    def unregister_memory(self, memory_id: str) -> bool:
        """从状态机移除记忆"""
        with self._lock:
            if memory_id not in self._states:
                return False

            del self._states[memory_id]
            self._created_at.pop(memory_id, None)
            self._state_changed_at.pop(memory_id, None)
            self._access_counts.pop(memory_id, None)
            self._last_accessed.pop(memory_id, None)
            self._history.pop(memory_id, None)
            return True

    def purge_deleted(self, max_age_seconds: float = 30 * 24 * 3600) -> int:
        """
        清理已删除的记忆

        Args:
            max_age_seconds: 删除后超过此时长的记忆将被永久清除

        Returns:
            清除的数量
        """
        with self._lock:
            now = time.time()
            to_remove = []

            for memory_id, state in self._states.items():
                if state == MemoryState.DELETED:
                    age = now - self._state_changed_at.get(memory_id, now)
                    if age >= max_age_seconds:
                        to_remove.append(memory_id)

            for mid in to_remove:
                self.unregister_memory(mid)

            return len(to_remove)

    def get_summary(self) -> Dict:
        """获取状态机摘要"""
        with self._lock:
            return {
                "total_memories": len(self._states),
                "state_distribution": self.get_state_distribution(),
                "total_hooks": sum(len(h) for h in self._hooks.values()),
                "total_guards": len(self._guards),
                "total_transitions": len(self._transitions),
            }


# ==================== 全局单例 ====================

_global_lifecycle: Optional[LifecycleStateMachine] = None
_global_lifecycle_lock = threading.Lock()


def get_lifecycle_machine() -> LifecycleStateMachine:
    """获取全局生命周期状态机实例"""
    global _global_lifecycle
    if _global_lifecycle is None:
        with _global_lifecycle_lock:
            if _global_lifecycle is None:
                _global_lifecycle = LifecycleStateMachine()
    return _global_lifecycle
