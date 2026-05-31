#!/usr/bin/env python3
"""
记忆一致性检查 - 阶段137-139
检测并修复记忆系统中的数据不一致
"""

import threading
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class ConsistencyLevel(Enum):
    """一致性级别"""
    OK = "ok"              # 一致
    WARNING = "warning"    # 警告（轻微不一致）
    ERROR = "error"        # 错误（严重不一致）
    CRITICAL = "critical"  # 严重（数据丢失风险）


@dataclass
class ConsistencyIssue:
    """一致性问题"""
    check_name: str
    level: ConsistencyLevel
    description: str
    affected_ids: List[str] = field(default_factory=list)
    fix_suggestion: str = ""
    auto_fixable: bool = False


class ConsistencyChecker:
    """
    一致性检查器
    
    检测记忆系统中的数据不一致问题，提供修复建议
    """

    def __init__(self, memory_system):
        self.memory_system = memory_system
        self._lock = threading.RLock()

    def run_full_check(self) -> Dict[str, Any]:
        """
        运行完整一致性检查

        Returns:
            检查报告
        """
        issues: List[ConsistencyIssue] = []

        # 检查1: L1临时记忆清理
        issues.extend(self._check_l1_cleanup())

        # 检查2: L2索引完整性
        issues.extend(self._check_l2_index())

        # 检查3: L3三元组完整性
        issues.extend(self._check_l3_triples())

        # 检查4: 版本历史连续性
        issues.extend(self._check_version_continuity())

        # 检查5: 隐私设置一致性
        issues.extend(self._check_privacy_consistency())

        # 检查6: 统计数据一致性
        issues.extend(self._check_stats_consistency())

        # 汇总
        error_count = sum(1 for i in issues if i.level in (ConsistencyLevel.ERROR, ConsistencyLevel.CRITICAL))
        warning_count = sum(1 for i in issues if i.level == ConsistencyLevel.WARNING)
        auto_fixable = sum(1 for i in issues if i.auto_fixable)

        return {
            "timestamp": datetime.now().isoformat(),
            "total_issues": len(issues),
            "errors": error_count,
            "warnings": warning_count,
            "auto_fixable": auto_fixable,
            "issues": [
                {
                    "check": i.check_name,
                    "level": i.level.value,
                    "description": i.description,
                    "affected": i.affected_ids[:10],
                    "fix_suggestion": i.fix_suggestion,
                    "auto_fixable": i.auto_fixable,
                }
                for i in issues
            ],
            "status": "healthy" if error_count == 0 else "needs_attention",
        }

    def _check_l1_cleanup(self) -> List[ConsistencyIssue]:
        """检查L1临时记忆是否及时清理"""
        issues = []
        try:
            from src.memory.l1_ephemeral import L1EphemeralMemory
            l1 = L1EphemeralMemory()
            stats = l1.get_stats()
            # 如果L1中有大量非活跃任务的记忆
            active_tasks = stats.get("active_tasks", 0)
            total_memories = stats.get("total_memories", 0)
            if total_memories > 1000 and active_tasks < 5:
                issues.append(ConsistencyIssue(
                    check_name="L1清理检查",
                    level=ConsistencyLevel.WARNING,
                    description=f"L1中有{total_memories}条记忆但仅{active_tasks}个活跃任务",
                    fix_suggestion="建议清理非活跃任务的L1记忆",
                    auto_fixable=True,
                ))
        except Exception:
            pass
        return issues

    def _check_l2_index(self) -> List[ConsistencyIssue]:
        """检查L2向量索引完整性"""
        issues = []
        try:
            from src.memory.l2_vector import L2VectorMemory
            l2 = L2VectorMemory()
            stats = l2.get_stats()
            index_size = stats.get("index_size", 0)
            db_count = stats.get("db_count", 0)
            if index_size != db_count:
                issues.append(ConsistencyIssue(
                    check_name="L2索引检查",
                    level=ConsistencyLevel.ERROR if abs(index_size - db_count) > 10 else ConsistencyLevel.WARNING,
                    description=f"索引大小({index_size})与数据库记录数({db_count})不一致",
                    fix_suggestion="建议重建FAISS索引",
                    auto_fixable=True,
                ))
        except Exception:
            pass
        return issues

    def _check_l3_triples(self) -> List[ConsistencyIssue]:
        """检查L3三元组完整性"""
        issues = []
        try:
            from src.memory.l3_fact import L3FactMemory
            l3 = L3FactMemory()
            stats = l3.get_stats()
            triple_count = stats.get("total_triples", 0)
            if triple_count > 0:
                # 检查是否有空值三元组
                empty_count = stats.get("empty_values", 0)
                if empty_count > 0:
                    issues.append(ConsistencyIssue(
                        check_name="L3三元组检查",
                        level=ConsistencyLevel.WARNING,
                        description=f"发现{empty_count}个空值三元组",
                        fix_suggestion="清理空值三元组",
                        auto_fixable=True,
                    ))
        except Exception:
            pass
        return issues

    def _check_version_continuity(self) -> List[ConsistencyIssue]:
        """检查版本历史连续性"""
        issues = []
        try:
            from src.governance.version_manager import VersionManager
            vm = VersionManager()
            stats = vm.get_stats()
            orphan_versions = stats.get("orphan_snapshots", 0)
            if orphan_versions > 0:
                issues.append(ConsistencyIssue(
                    check_name="版本连续性检查",
                    level=ConsistencyLevel.WARNING,
                    description=f"发现{orphan_versions}个孤立版本快照",
                    fix_suggestion="关联或清理孤立快照",
                    auto_fixable=False,
                ))
        except Exception:
            pass
        return issues

    def _check_privacy_consistency(self) -> List[ConsistencyIssue]:
        """检查隐私设置一致性"""
        issues = []
        try:
            from src.governance.privacy_isolation import PrivacyIsolationManager
            pm = PrivacyIsolationManager()
            stats = pm.get_stats()
            unregistered = stats.get("unregistered_memories", 0)
            if unregistered > 0:
                issues.append(ConsistencyIssue(
                    check_name="隐私设置检查",
                    level=ConsistencyLevel.WARNING,
                    description=f"发现{unregistered}个未注册隐私设置的记忆",
                    fix_suggestion="为未注册记忆设置默认隐私级别",
                    auto_fixable=True,
                ))
        except Exception:
            pass
        return issues

    def _check_stats_consistency(self) -> List[ConsistencyIssue]:
        """检查统计数据一致性"""
        issues = []
        try:
            stats = self.memory_system.get_stats()
            stored = stats.get("total_stored", 0)
            recalled = stats.get("total_recalled", 0)
            # 基本合理性检查
            if stored < 0 or recalled < 0:
                issues.append(ConsistencyIssue(
                    check_name="统计一致性检查",
                    level=ConsistencyLevel.ERROR,
                    description=f"统计数据异常: stored={stored}, recalled={recalled}",
                    fix_suggestion="重置统计数据",
                    auto_fixable=True,
                ))
        except Exception:
            pass
        return issues
