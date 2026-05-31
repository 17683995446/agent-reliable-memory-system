"""
复盘迭代模块
阶段 60：任务闭环复盘、经验提炼、权重优化

核心特性：
- 任务闭环后自动触发复盘
- 将零散经验提炼为结构化规则
- 增量更新 L3 事实记忆
- 优化 L2 召回权重
"""

import re
import time
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

from src.memory.l1_ephemeral import L1EphemeralMemory, get_l1_memory
from src.memory.l3_fact import L3FactMemory, Triple, get_l3_memory
from src.governance.governor import MemoryGovernor


class TaskOutcome(Enum):
    """任务结果"""
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class TaskReview:
    """任务复盘"""
    task_id: str
    session_id: str
    outcome: TaskOutcome
    steps: List[str] = field(default_factory=list)
    success_patterns: List[str] = field(default_factory=list)
    failure_reasons: List[str] = field(default_factory=list)
    extracted_rules: List[str] = field(default_factory=list)
    recall_hit_rate: float = 0.0
    reviewed_at: float = field(default_factory=time.time)


class RuleExtractor:
    """
    规则提取器
    
    从任务执行经验中提炼结构化规则（if-then 格式）。
    """
    
    # 成功模式关键词
    SUCCESS_PATTERNS = [
        r'(成功|完成|通过)(.{2,30})',
        r'(有效|正确|准确)(.{2,30})',
        r'(优化|改进|提升)(.{2,30})',
    ]
    
    # 失败模式关键词
    FAILURE_PATTERNS = [
        r'(失败|错误|异常)(.{2,30})',
        r'(超时|中断|崩溃)(.{2,30})',
        r'(不足|缺失|遗漏)(.{2,30})',
    ]
    
    def extract_rules(self, steps: List[str], outcome: TaskOutcome) -> List[str]:
        """从执行步骤中提炼规则"""
        rules = []
        
        if outcome == TaskOutcome.SUCCESS:
            # 成功任务：提炼成功范式
            for step in steps:
                for pattern in self.SUCCESS_PATTERNS:
                    match = re.search(pattern, step)
                    if match:
                        rule = f"IF 场景匹配 '{step[:20]}' THEN 采用 '{match.group(0)[:30]}' 策略"
                        rules.append(rule)
        else:
            # 失败任务：提炼避免规则
            for step in steps:
                for pattern in self.FAILURE_PATTERNS:
                    match = re.search(pattern, step)
                    if match:
                        rule = f"IF 场景匹配 '{step[:20]}' THEN 避免 '{match.group(0)[:30]}'"
                        rules.append(rule)
        
        return rules


class ReviewEngine:
    """
    复盘引擎（阶段 60）
    
    任务闭环后自动复盘 → 经验提炼 → 规则沉淀 → 权重优化
    """
    
    def __init__(self, l1=None, l3=None, governor=None):
        self.l1 = l1 or get_l1_memory()
        self.l3 = l3 or get_l3_memory()
        self.governor = governor
        self.rule_extractor = RuleExtractor()
        self.logger = logging.getLogger("review.engine")
    
    def review_task(self, session_id: str, task_id: str,
                    outcome: TaskOutcome, steps: List[str] = None,
                    recall_hit_rate: float = 0.0) -> TaskReview:
        """
        任务闭环复盘
        
        Args:
            session_id: 会话ID
            task_id: 任务ID
            outcome: 任务结果
            steps: 执行步骤列表
            recall_hit_rate: 召回命中率
            
        Returns:
            TaskReview: 复盘结果
        """
        review = TaskReview(
            task_id=task_id,
            session_id=session_id,
            outcome=outcome,
            steps=steps or [],
            recall_hit_rate=recall_hit_rate
        )
        
        # Step 1: 获取任务上下文（从 L1）
        context = self.l1.get_context(session_id, task_id)
        review.steps = [item.content for item in context]
        
        # Step 2: 提取成功/失败模式
        if outcome == TaskOutcome.SUCCESS:
            review.success_patterns = self._extract_patterns(review.steps, "success")
        else:
            review.failure_reasons = self._extract_patterns(review.steps, "failure")
        
        # Step 3: 提炼结构化规则
        review.extracted_rules = self.rule_extractor.extract_rules(
            review.steps, outcome
        )
        
        # Step 4: 沉淀规则到 L3
        self._deposit_rules(review.extracted_rules, session_id)
        
        # Step 5: 记录复盘日志
        self.logger.info(
            f"[REVIEW] task={task_id}, outcome={outcome.value}, "
            f"rules={len(review.extracted_rules)}, "
            f"recall_hit_rate={recall_hit_rate:.2%}"
        )
        
        return review
    
    def _extract_patterns(self, steps: List[str], pattern_type: str) -> List[str]:
        """提取成功/失败模式"""
        patterns = []
        patterns_list = self.rule_extractor.SUCCESS_PATTERNS if pattern_type == "success" \
            else self.rule_extractor.FAILURE_PATTERNS
        
        for step in steps:
            for pattern in patterns_list:
                match = re.search(pattern, step)
                if match:
                    patterns.append(match.group(0))
        
        return patterns
    
    def _deposit_rules(self, rules: List[str], source_session: str):
        """将提炼的规则沉淀到 L3"""
        for rule in rules:
            try:
                triple = Triple(
                    subject=f"经验规则_{rule[:10]}",
                    predicate="RULE",
                    object=rule,
                    is_attribute=True,
                    confidence=0.8,
                    source=source_session
                )
                self.l3.store_triple(triple, create_snapshot=False)
            except Exception as e:
                self.logger.error(f"[REVIEW] 规则沉淀失败: {e}")
