"""
Agent可靠记忆系统 - 记忆版本对比与合并
阶段176-178: 版本差异检测、三路合并、冲突解决

设计原则:
- 确定性规则驱动，无模型依赖
- 线程安全（RLock）
- 全局单例模式
- 基于结构化数据的差异算法
"""

import threading
import time
import difflib
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Any
from collections import defaultdict


class DiffType(Enum):
    """差异类型"""
    ADDED = "added"              # 新增
    REMOVED = "removed"          # 删除
    MODIFIED = "modified"        # 修改
    UNCHANGED = "unchanged"      # 未变化
    CONFLICT = "conflict"        # 冲突


class MergeStrategy(Enum):
    """合并策略"""
    BASE_WINS = "base_wins"      # 基准版本优先
    LOCAL_WINS = "local_wins"    # 本地版本优先
    REMOTE_WINS = "remote_wins"  # 远程版本优先
    MANUAL = "manual"            # 手动解决
    UNION = "union"              # 并集（取所有值）
    INTERSECTION = "intersection"  # 交集（取共同值）


@dataclass
class FieldDiff:
    """字段级差异"""
    field_path: str              # 字段路径（支持嵌套，如 "metadata.author"）
    diff_type: DiffType
    old_value: Any = None
    new_value: Any = None
    base_value: Any = None       # 三路合并时的基准值

    def to_dict(self) -> Dict:
        return {
            "field_path": self.field_path,
            "type": self.diff_type.value,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "base_value": self.base_value,
        }


@dataclass
class MemoryDiff:
    """记忆版本差异"""
    memory_id: str
    base_version: Optional[str] = None
    compare_version: str = ""
    diffs: List[FieldDiff] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    @property
    def has_changes(self) -> bool:
        return any(d.diff_type != DiffType.UNCHANGED for d in self.diffs)

    @property
    def change_count(self) -> int:
        return sum(1 for d in self.diffs if d.diff_type != DiffType.UNCHANGED)

    def to_dict(self) -> Dict:
        return {
            "memory_id": self.memory_id,
            "base_version": self.base_version,
            "compare_version": self.compare_version,
            "has_changes": self.has_changes,
            "change_count": self.change_count,
            "diffs": [d.to_dict() for d in self.diffs],
            "created_at": self.created_at,
        }


@dataclass
class MergeConflict:
    """合并冲突"""
    field_path: str
    base_value: Any
    local_value: Any
    remote_value: Any
    description: str = ""

    def to_dict(self) -> Dict:
        return {
            "field_path": self.field_path,
            "base_value": self.base_value,
            "local_value": self.local_value,
            "remote_value": self.remote_value,
            "description": self.description,
        }


@dataclass
class MergeResult:
    """合并结果"""
    memory_id: str
    success: bool
    merged_data: Optional[Dict] = None
    conflicts: List[MergeConflict] = field(default_factory=list)
    strategy_used: MergeStrategy = MergeStrategy.MANUAL
    applied_changes: List[str] = field(default_factory=list)

    @property
    def has_conflicts(self) -> bool:
        return len(self.conflicts) > 0

    def to_dict(self) -> Dict:
        return {
            "memory_id": self.memory_id,
            "success": self.success,
            "has_conflicts": self.has_conflicts,
            "conflict_count": len(self.conflicts),
            "strategy_used": self.strategy_used.value,
            "applied_changes": self.applied_changes,
            "conflicts": [c.to_dict() for c in self.conflicts],
        }


class VersionDiffEngine:
    """
    记忆版本对比与合并引擎

    功能:
    - 结构化数据差异检测
    - 文本内容行级差异
    - 三路合并算法
    - 冲突检测与标记
    - 多种合并策略
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._diff_history: deque = deque(maxlen=1000)
        self._merge_history: deque = deque(maxlen=1000)

    # ==================== 差异检测 ====================

    def compare_memories(self, memory_id: str,
                         base_data: Dict,
                         compare_data: Dict,
                         base_version: Optional[str] = None,
                         compare_version: str = "") -> MemoryDiff:
        """
        比较两个记忆版本

        Args:
            memory_id: 记忆ID
            base_data: 基准数据
            compare_data: 对比数据
            base_version: 基准版本号
            compare_version: 对比版本号

        Returns:
            MemoryDiff对象
        """
        with self._lock:
            diffs = []
            all_paths = self._get_all_paths(base_data) | self._get_all_paths(compare_data)

            for path in all_paths:
                base_val = self._get_nested_value(base_data, path)
                compare_val = self._get_nested_value(compare_data, path)

                diff_type = self._determine_diff_type(base_val, compare_val)
                if diff_type != DiffType.UNCHANGED:
                    diffs.append(FieldDiff(
                        field_path=path,
                        diff_type=diff_type,
                        old_value=base_val,
                        new_value=compare_val,
                    ))

            result = MemoryDiff(
                memory_id=memory_id,
                base_version=base_version,
                compare_version=compare_version,
                diffs=diffs,
            )
            self._diff_history.append(result)
            return result

    def compare_text(self, old_text: str, new_text: str,
                     context_lines: int = 3) -> List[Dict]:
        """
        文本行级差异

        Args:
            old_text: 旧文本
            new_text: 新文本
            context_lines: 上下文行数

        Returns:
            差异块列表
        """
        old_lines = old_text.splitlines(keepends=True)
        new_lines = new_text.splitlines(keepends=True)

        differ = difflib.unified_diff(
            old_lines, new_lines,
            lineterm='',
            n=context_lines
        )

        hunks = []
        current_hunk = []

        for line in differ:
            if line.startswith('@@'):
                if current_hunk:
                    hunks.append(self._parse_hunk(current_hunk))
                current_hunk = [line]
            else:
                current_hunk.append(line)

        if current_hunk:
            hunks.append(self._parse_hunk(current_hunk))

        return hunks

    def _parse_hunk(self, lines: List[str]) -> Dict:
        """解析差异块"""
        header = lines[0]
        old_start, old_count, new_start, new_count = self._parse_header(header)

        old_lines = []
        new_lines = []
        context_lines = []

        for line in lines[1:]:
            if line.startswith('-'):
                old_lines.append(line[1:])
            elif line.startswith('+'):
                new_lines.append(line[1:])
            elif line.startswith(' '):
                context_lines.append(line[1:])

        return {
            "old_start": old_start,
            "old_count": old_count,
            "new_start": new_start,
            "new_count": new_count,
            "old_lines": old_lines,
            "new_lines": new_lines,
            "context_lines": context_lines,
        }

    def _parse_header(self, header: str) -> Tuple[int, int, int, int]:
        """解析差异块头部 @@ -start,count +start,count @@"""
        import re
        match = re.search(r'@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@', header)
        if match:
            old_start = int(match.group(1))
            old_count = int(match.group(2)) if match.group(2) else 1
            new_start = int(match.group(3))
            new_count = int(match.group(4)) if match.group(4) else 1
            return old_start, old_count, new_start, new_count
        return 0, 0, 0, 0

    def _get_all_paths(self, data: Dict, prefix: str = "") -> Set[str]:
        """获取所有字段路径"""
        paths = set()
        if not isinstance(data, dict):
            return paths

        for key, value in data.items():
            path = f"{prefix}.{key}" if prefix else key
            paths.add(path)
            if isinstance(value, dict):
                paths.update(self._get_all_paths(value, path))
        return paths

    def _get_nested_value(self, data: Dict, path: str) -> Any:
        """获取嵌套字段值"""
        keys = path.split('.')
        current = data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current

    def _determine_diff_type(self, base_val: Any, compare_val: Any) -> DiffType:
        """确定差异类型"""
        if base_val is None and compare_val is not None:
            return DiffType.ADDED
        if base_val is not None and compare_val is None:
            return DiffType.REMOVED
        if base_val != compare_val:
            return DiffType.MODIFIED
        return DiffType.UNCHANGED

    # ==================== 三路合并 ====================

    def three_way_merge(self, memory_id: str,
                        base_data: Dict,
                        local_data: Dict,
                        remote_data: Dict,
                        strategy: MergeStrategy = MergeStrategy.MANUAL) -> MergeResult:
        """
        三路合并

        Args:
            memory_id: 记忆ID
            base_data: 共同祖先（基准）
            local_data: 本地修改
            remote_data: 远程修改
            strategy: 合并策略

        Returns:
            MergeResult对象
        """
        with self._lock:
            conflicts = []
            merged = dict(base_data)
            applied_changes = []

            # 获取所有字段路径
            all_paths = (
                self._get_all_paths(base_data) |
                self._get_all_paths(local_data) |
                self._get_all_paths(remote_data)
            )

            for path in all_paths:
                base_val = self._get_nested_value(base_data, path)
                local_val = self._get_nested_value(local_data, path)
                remote_val = self._get_nested_value(remote_data, path)

                result, conflict = self._merge_field(
                    path, base_val, local_val, remote_val, strategy
                )

                if conflict:
                    conflicts.append(conflict)
                elif result is not None:
                    self._set_nested_value(merged, path, result)
                    applied_changes.append(path)

            result = MergeResult(
                memory_id=memory_id,
                success=len(conflicts) == 0 or strategy != MergeStrategy.MANUAL,
                merged_data=merged if not conflicts else None,
                conflicts=conflicts,
                strategy_used=strategy,
                applied_changes=applied_changes,
            )
            self._merge_history.append(result)
            return result

    def _merge_field(self, path: str, base_val: Any, local_val: Any,
                     remote_val: Any, strategy: MergeStrategy) -> Tuple[Any, Optional[MergeConflict]]:
        """合并单个字段"""
        # 本地和远程相同，无冲突
        if local_val == remote_val:
            return local_val, None

        # 本地未修改，采用远程
        if local_val == base_val:
            return remote_val, None

        # 远程未修改，采用本地
        if remote_val == base_val:
            return local_val, None

        # 双方都修改了，产生冲突
        if strategy == MergeStrategy.BASE_WINS:
            return base_val, None
        elif strategy == MergeStrategy.LOCAL_WINS:
            return local_val, None
        elif strategy == MergeStrategy.REMOTE_WINS:
            return remote_val, None
        elif strategy == MergeStrategy.UNION:
            # 列表取并集，其他取本地
            if isinstance(local_val, list) and isinstance(remote_val, list):
                return list(set(local_val + remote_val)), None
            return local_val, None
        elif strategy == MergeStrategy.INTERSECTION:
            # 列表取交集，其他取基准
            if isinstance(local_val, list) and isinstance(remote_val, list):
                return list(set(local_val) & set(remote_val)), None
            return base_val, None
        else:  # MANUAL
            conflict = MergeConflict(
                field_path=path,
                base_value=base_val,
                local_value=local_val,
                remote_value=remote_val,
                description=f"字段 '{path}' 存在冲突",
            )
            return None, conflict

    def _set_nested_value(self, data: Dict, path: str, value: Any):
        """设置嵌套字段值"""
        keys = path.split('.')
        current = data
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value

    def resolve_conflicts(self, memory_id: str,
                          merged_data: Dict,
                          conflicts: List[MergeConflict],
                          resolutions: Dict[str, Any]) -> MergeResult:
        """
        手动解决冲突

        Args:
            memory_id: 记忆ID
            merged_data: 基础合并数据
            conflicts: 冲突列表
            resolutions: 冲突解决方案 {field_path: resolved_value}

        Returns:
            MergeResult对象
        """
        with self._lock:
            result_data = dict(merged_data)
            unresolved = []
            applied = []

            for conflict in conflicts:
                if conflict.field_path in resolutions:
                    self._set_nested_value(
                        result_data,
                        conflict.field_path,
                        resolutions[conflict.field_path]
                    )
                    applied.append(conflict.field_path)
                else:
                    unresolved.append(conflict)

            return MergeResult(
                memory_id=memory_id,
                success=len(unresolved) == 0,
                merged_data=result_data if not unresolved else None,
                conflicts=unresolved,
                strategy_used=MergeStrategy.MANUAL,
                applied_changes=applied,
            )

    # ==================== 批量操作 ====================

    def batch_compare(self, comparisons: List[Tuple[str, Dict, Dict]]) -> List[MemoryDiff]:
        """批量比较"""
        with self._lock:
            results = []
            for memory_id, base, compare in comparisons:
                result = self.compare_memories(memory_id, base, compare)
                results.append(result)
            return results

    def batch_merge(self, merges: List[Tuple[str, Dict, Dict, Dict, MergeStrategy]]) -> List[MergeResult]:
        """批量合并"""
        with self._lock:
            results = []
            for memory_id, base, local, remote, strategy in merges:
                result = self.three_way_merge(memory_id, base, local, remote, strategy)
                results.append(result)
            return results

    # ==================== 统计与历史 ====================

    def get_diff_stats(self) -> Dict:
        """获取差异统计"""
        with self._lock:
            total_diffs = len(self._diff_history)
            changes_count = sum(d.change_count for d in self._diff_history)
            return {
                "total_comparisons": total_diffs,
                "total_changes": changes_count,
                "avg_changes_per_comparison": round(changes_count / total_diffs, 2) if total_diffs > 0 else 0,
            }

    def get_merge_stats(self) -> Dict:
        """获取合并统计"""
        with self._lock:
            total_merges = len(self._merge_history)
            successful = sum(1 for m in self._merge_history if m.success)
            with_conflicts = sum(1 for m in self._merge_history if m.has_conflicts)
            return {
                "total_merges": total_merges,
                "successful": successful,
                "failed": total_merges - successful,
                "with_conflicts": with_conflicts,
                "success_rate": round(successful / total_merges * 100, 2) if total_merges > 0 else 0,
            }

    def get_summary(self) -> Dict:
        """获取引擎摘要"""
        with self._lock:
            return {
                "diff_stats": self.get_diff_stats(),
                "merge_stats": self.get_merge_stats(),
            }


# ==================== 全局单例 ====================

from collections import deque
_global_diff_engine: Optional[VersionDiffEngine] = None
_global_diff_engine_lock = threading.Lock()


def get_version_diff_engine() -> VersionDiffEngine:
    """获取全局版本对比引擎实例"""
    global _global_diff_engine
    if _global_diff_engine is None:
        with _global_diff_engine_lock:
            if _global_diff_engine is None:
                _global_diff_engine = VersionDiffEngine()
    return _global_diff_engine
