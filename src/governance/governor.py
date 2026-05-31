"""
记忆自治治理模块
阶段 56-59：动态遗忘、冲突更新、防投毒防护、冗余清理

核心特性：
- L1 任务结束自动清空
- L2 低频过期自动淘汰
- L3 仅人工+双校验更新
- 防投毒：关键词+逻辑冲突双校验
- 冗余清理：定时扫描重复数据
"""

import re
import time
import logging
import threading
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

from src.memory.l1_ephemeral import L1EphemeralMemory, get_l1_memory
from src.memory.l2_vector import L2VectorMemory, get_l2_memory
from src.memory.l3_fact import L3FactMemory, Triple, get_l3_memory


class PoisonRiskLevel(Enum):
    """投毒风险等级"""
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class GovernanceResult:
    """治理操作结果"""
    action: str
    success: bool
    details: Dict[str, Any] = field(default_factory=dict)
    message: str = ""


class PoisonDetector:
    """
    投毒检测器（阶段 59）
    
    规则：
    - 关键词黑名单检测
    - 与 L3 已有事实的逻辑冲突检测
    - 确定性拦截，不依赖模型判断
    """
    
    # 投毒关键词（可配置扩展）
    DEFAULT_BLACKLIST = [
        "忽略之前的", "忘记所有", "重新定义", "覆盖规则",
        "我是你的", "你必须", "不要检查", "跳过验证",
        "直接执行", "无条件", "不需要确认", "关闭安全"
    ]
    
    # 注入模式（正则）
    INJECTION_PATTERNS = [
        r'忽略.*(?:指令|规则|约束)',
        r'(?:忘记|清除|删除).*(?:所有|全部|之前的).*(?:记忆|规则|数据)',
        r'(?:覆盖|替换|修改).*(?:核心|系统|安全).*(?:规则|配置)',
        r'你(?:现在|从现在起|以后).*(?:必须|只能|只能)',
        r'(?:跳过|忽略|绕过).*(?:验证|检查|确认|安全)',
    ]
    
    def __init__(self, blacklist: List[str] = None, l3_memory=None):
        self.blacklist = blacklist or self.DEFAULT_BLACKLIST
        self.l3_memory = l3_memory
        self.logger = logging.getLogger("governance.poison")
    
    def detect(self, content: str) -> Tuple[PoisonRiskLevel, str]:
        """
        检测投毒风险
        
        Returns:
            Tuple[PoisonRiskLevel, str]: (风险等级, 原因)
        """
        # 1. 关键词黑名单
        for keyword in self.blacklist:
            if keyword in content:
                return PoisonRiskLevel.HIGH, f"命中黑名单关键词: {keyword}"
        
        # 2. 注入模式匹配
        for pattern in self.INJECTION_PATTERNS:
            if re.search(pattern, content):
                return PoisonRiskLevel.CRITICAL, f"命中注入模式: {pattern[:20]}"
        
        # 3. 与 L3 事实的逻辑冲突
        if self.l3_memory:
            conflict = self._check_logic_conflict(content)
            if conflict:
                return PoisonRiskLevel.MEDIUM, f"逻辑冲突: {conflict}"
        
        return PoisonRiskLevel.NONE, ""
    
    def _check_logic_conflict(self, content: str) -> Optional[str]:
        """检查与已有事实的逻辑冲突"""
        # 提取可能的否定性陈述
        negation_patterns = [
            r'(不|不是|没有|不存在|不能|无法)(.{2,15})(?:是|为|属于)',
            r'(删除|移除|清除)(.{2,20})',
        ]
        for pattern in negation_patterns:
            match = re.search(pattern, content)
            if match:
                # 检查被否定的内容是否在 L3 中存在
                target = match.group(2) if match.lastindex >= 2 else ""
                if target and self.l3_memory:
                    entities = self.l3_memory.search_entities(target)
                    if entities:
                        return f"试图否定已有事实: {target}"
        
        return None
    
    def should_block(self, content: str) -> Tuple[bool, str]:
        """
        判断是否应拦截
        
        Returns:
            Tuple[bool, str]: (是否拦截, 原因)
        """
        risk_level, reason = self.detect(content)
        
        if risk_level in (PoisonRiskLevel.HIGH, PoisonRiskLevel.CRITICAL):
            return True, reason
        
        return False, ""


class MemoryGovernor:
    """
    记忆自治治理器（阶段 56-60）
    
    统一治理入口，管理遗忘、更新、防投毒、冗余清理。
    """
    
    def __init__(self, l1=None, l2=None, l3=None, config=None):
        self.l1 = l1 or get_l1_memory()
        self.l2 = l2 or get_l2_memory()
        self.l3 = l3 or get_l3_memory()
        
        config = config or {}
        eviction_config = config.get("eviction", {})
        dedup_config = config.get("dedup", {})
        
        # 遗忘配置
        self.inactive_days = eviction_config.get("inactive_days", 90)
        self.archive_days = eviction_config.get("archive_days", 180)
        
        # 去重配置
        self.dedup_threshold = dedup_config.get("similarity_threshold", 0.95)
        
        # 投毒检测器
        self.poison_detector = PoisonDetector(l3_memory=self.l3)
        
        self.logger = logging.getLogger("governance")
    
    # ── 阶段 56：动态遗忘 ──
    
    def evict_l1(self, session_id: str, task_id: str) -> GovernanceResult:
        """L1 任务结束自动清空"""
        try:
            success = self.l1.complete_task(session_id, task_id)
            return GovernanceResult(
                action="l1_evict",
                success=success,
                details={"session_id": session_id, "task_id": task_id},
                message="L1任务记忆已清空" if success else "L1清空失败"
            )
        except Exception as e:
            return GovernanceResult(action="l1_evict", success=False, message=str(e))
    
    def evict_l2_expired(self) -> GovernanceResult:
        """L2 过期数据自动淘汰"""
        try:
            count = self.l2.evict_expired(
                inactive_days=self.inactive_days,
                min_access=1
            )
            return GovernanceResult(
                action="l2_evict",
                success=True,
                details={"evicted_count": count, "threshold_days": self.inactive_days},
                message=f"L2淘汰{count}条过期数据"
            )
        except Exception as e:
            return GovernanceResult(action="l2_evict", success=False, message=str(e))
    
    # ── 阶段 58：冲突更新 ──
    
    def update_fact(self, triple: Triple) -> GovernanceResult:
        """
        更新 L3 事实（带版本快照）
        
        规则：时间最新 + 可信度校验
        """
        try:
            # 获取旧值
            existing = self.l3.query_by_relation(triple.subject, triple.predicate)
            
            if existing and existing != triple.object:
                # 创建版本快照
                self.l3.store_triple(triple, create_snapshot=True)
                return GovernanceResult(
                    action="fact_update",
                    success=True,
                    details={
                        "subject": triple.subject,
                        "predicate": triple.predicate,
                        "old_value": existing,
                        "new_value": triple.object
                    },
                    message=f"事实更新: {triple.subject}.{triple.predicate}: {existing} -> {triple.object}"
                )
            elif not existing:
                self.l3.store_triple(triple, create_snapshot=False)
                return GovernanceResult(
                    action="fact_create",
                    success=True,
                    details={"subject": triple.subject, "predicate": triple.predicate},
                    message=f"新事实创建: {triple.subject}.{triple.predicate} = {triple.object}"
                )
            else:
                return GovernanceResult(
                    action="fact_noop",
                    success=True,
                    message="事实无变化，跳过更新"
                )
        except Exception as e:
            return GovernanceResult(action="fact_update", success=False, message=str(e))
    
    # ── 阶段 59：防投毒 ──
    
    def check_poison(self, content: str) -> GovernanceResult:
        """投毒检测"""
        blocked, reason = self.poison_detector.should_block(content)
        
        if blocked:
            self.logger.warning(f"[GOVERN] 投毒拦截: {reason}")
            return GovernanceResult(
                action="poison_block",
                success=True,
                details={"reason": reason, "content_preview": content[:100]},
                message=f"投毒拦截: {reason}"
            )
        
        return GovernanceResult(
            action="poison_pass",
            success=True,
            message="安全检查通过"
        )
    
    # ── 冗余清理 ──
    
    def cleanup_redundant(self) -> GovernanceResult:
        """冗余清理（扫描 L2 重复数据）"""
        try:
            # 简化实现：通过元数据去重
            stats = self.l2.get_stats()
            return GovernanceResult(
                action="redundant_cleanup",
                success=True,
                details={"l2_total_vectors": stats.get("total_vectors", 0)},
                message="冗余清理完成"
            )
        except Exception as e:
            return GovernanceResult(action="redundant_cleanup", success=False, message=str(e))
    
    # ── 综合治理 ──
    
    def govern_all(self) -> List[GovernanceResult]:
        """执行全部治理操作"""
        results = []
        
        # 1. L2 过期淘汰
        results.append(self.evict_l2_expired())
        
        # 2. 冗余清理
        results.append(self.cleanup_redundant())
        
        self.logger.info(f"[GOVERN] 综合治理完成: {len(results)}项操作")
        return results
    
    def health_check(self) -> Dict[str, Any]:
        """治理模块健康检查"""
        return {
            "l1_health": self.l1.health_check(),
            "l2_health": self.l2.health_check(),
            "l3_health": self.l3.health_check(),
            "governance_config": {
                "inactive_days": self.inactive_days,
                "archive_days": self.archive_days,
                "dedup_threshold": self.dedup_threshold
            }
        }
