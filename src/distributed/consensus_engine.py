"""
Consensus Engine Module
Agent Reliable Memory System - Stage 397

分布式共识引擎模块，用于在多个代理节点之间对提案进行投票和达成共识。

设计原则：
1. 第一性原理：确定性规则，不依赖模型
2. 使用 threading.RLock 保证线程安全
3. 通过 get_consensus_engine() 实现全局单例，采用双检锁机制
4. 使用 Python dataclasses 定义数据结构，Enum 定义类型
5. 最小依赖，无循环依赖
"""

import hashlib
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class ProposalStatus(Enum):
    """提案状态枚举"""
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    COMMITTED = "committed"
    EXPIRED = "expired"


class VoteType(Enum):
    """投票类型枚举"""
    YES = "yes"
    NO = "no"
    ABSTAIN = "abstain"


@dataclass
class Vote:
    """投票数据类"""
    vote_id: str
    proposal_id: str
    voter_id: str
    vote_type: VoteType
    timestamp: float


@dataclass
class Proposal:
    """提案数据类"""
    proposal_id: str
    term: int
    value: str
    proposer_id: str
    status: ProposalStatus
    votes: List[Vote] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 60.0)


class ConsensusEngine:
    """
    共识引擎类

    负责管理提案生命周期、收集投票、判定共识结果。
    采用简单多数制（YES 票数严格大于 NO 票数）作为接受条件。
    支持基于任期（term）的提案版本控制。
    """

    def __init__(self) -> None:
        self._proposals: Dict[str, Proposal] = {}
        self._votes: Dict[str, List[Vote]] = {}
        self._current_term: int = 0
        self._lock: threading.RLock = threading.RLock()

    def _generate_proposal_id(self, value: str, proposer_id: str, term: int, timestamp: float) -> str:
        """生成确定性提案 ID"""
        data = f"{value}:{proposer_id}:{term}:{timestamp:.6f}"
        return hashlib.sha256(data.encode("utf-8")).hexdigest()[:32]

    def _generate_vote_id(self, proposal_id: str, voter_id: str, timestamp: float) -> str:
        """生成确定性投票 ID"""
        data = f"{proposal_id}:{voter_id}:{timestamp:.6f}"
        return hashlib.sha256(data.encode("utf-8")).hexdigest()[:32]

    def propose(self, value: str, proposer_id: str, term: Optional[int] = None) -> str:
        """
        提交一个新提案

        Args:
            value: 提案内容
            proposer_id: 提案者 ID
            term: 任期号，若为 None 则使用当前任期

        Returns:
            生成的 proposal_id
        """
        with self._lock:
            use_term = term if term is not None else self._current_term
            now = time.time()
            proposal_id = self._generate_proposal_id(value, proposer_id, use_term, now)
            proposal = Proposal(
                proposal_id=proposal_id,
                term=use_term,
                value=value,
                proposer_id=proposer_id,
                status=ProposalStatus.PENDING,
                votes=[],
                created_at=now,
                expires_at=now + 60.0,
            )
            self._proposals[proposal_id] = proposal
            self._votes[proposal_id] = []
            return proposal_id

    def vote(self, proposal_id: str, voter_id: str, vote_type: VoteType) -> bool:
        """
        对指定提案投票

        每个投票者对每个提案只能投一次票（去重）。
        若提案已过期、已提交或已被拒绝，则无法投票。

        Args:
            proposal_id: 提案 ID
            voter_id: 投票者 ID
            vote_type: 投票类型

        Returns:
            投票是否成功
        """
        with self._lock:
            proposal = self._proposals.get(proposal_id)
            if proposal is None:
                return False
            if proposal.status in (ProposalStatus.COMMITTED, ProposalStatus.REJECTED, ProposalStatus.EXPIRED):
                return False
            if time.time() > proposal.expires_at:
                proposal.status = ProposalStatus.EXPIRED
                return False

            # 去重：每个投票者对每个提案只能投一次
            existing_votes = self._votes.get(proposal_id, [])
            for v in existing_votes:
                if v.voter_id == voter_id:
                    return False

            now = time.time()
            vote_id = self._generate_vote_id(proposal_id, voter_id, now)
            new_vote = Vote(
                vote_id=vote_id,
                proposal_id=proposal_id,
                voter_id=voter_id,
                vote_type=vote_type,
                timestamp=now,
            )
            existing_votes.append(new_vote)
            self._votes[proposal_id] = existing_votes
            proposal.votes = existing_votes

            # 自动判定是否达成接受条件
            if self._check_accepted(proposal_id):
                proposal.status = ProposalStatus.ACCEPTED

            return True

    def _check_accepted(self, proposal_id: str) -> bool:
        """内部方法：检查提案是否满足简单多数接受条件"""
        counts = self._get_vote_count_unsafe(proposal_id)
        yes = counts.get("yes", 0)
        no = counts.get("no", 0)
        return yes > no and yes > 0

    def _get_vote_count_unsafe(self, proposal_id: str) -> Dict[str, int]:
        """无锁方式获取投票计数（调用方必须持有锁）"""
        votes = self._votes.get(proposal_id, [])
        counts: Dict[str, int] = {"yes": 0, "no": 0, "abstain": 0}
        for v in votes:
            if v.vote_type == VoteType.YES:
                counts["yes"] += 1
            elif v.vote_type == VoteType.NO:
                counts["no"] += 1
            elif v.vote_type == VoteType.ABSTAIN:
                counts["abstain"] += 1
        return counts

    def get_proposal(self, proposal_id: str) -> Optional[Proposal]:
        """
        根据 ID 获取提案

        Args:
            proposal_id: 提案 ID

        Returns:
            Proposal 实例或 None
        """
        with self._lock:
            proposal = self._proposals.get(proposal_id)
            if proposal is None:
                return None
            # 返回副本以避免外部修改内部状态
            return Proposal(
                proposal_id=proposal.proposal_id,
                term=proposal.term,
                value=proposal.value,
                proposer_id=proposal.proposer_id,
                status=proposal.status,
                votes=list(proposal.votes),
                created_at=proposal.created_at,
                expires_at=proposal.expires_at,
            )

    def get_proposals(self, status: Optional[ProposalStatus] = None) -> List[Proposal]:
        """
        获取提案列表

        Args:
            status: 若指定则按状态过滤

        Returns:
            提案列表
        """
        with self._lock:
            result: List[Proposal] = []
            for proposal in self._proposals.values():
                if status is None or proposal.status == status:
                    result.append(
                        Proposal(
                            proposal_id=proposal.proposal_id,
                            term=proposal.term,
                            value=proposal.value,
                            proposer_id=proposal.proposer_id,
                            status=proposal.status,
                            votes=list(proposal.votes),
                            created_at=proposal.created_at,
                            expires_at=proposal.expires_at,
                        )
                    )
            return result

    def commit_proposal(self, proposal_id: str) -> bool:
        """
        提交（确认）一个已接受的提案

        Args:
            proposal_id: 提案 ID

        Returns:
            是否成功提交
        """
        with self._lock:
            proposal = self._proposals.get(proposal_id)
            if proposal is None:
                return False
            if proposal.status != ProposalStatus.ACCEPTED:
                return False
            proposal.status = ProposalStatus.COMMITTED
            return True

    def reject_proposal(self, proposal_id: str) -> bool:
        """
        拒绝一个提案

        Args:
            proposal_id: 提案 ID

        Returns:
            是否成功拒绝
        """
        with self._lock:
            proposal = self._proposals.get(proposal_id)
            if proposal is None:
                return False
            if proposal.status in (ProposalStatus.COMMITTED, ProposalStatus.EXPIRED):
                return False
            proposal.status = ProposalStatus.REJECTED
            return True

    def get_vote_count(self, proposal_id: str) -> Dict[str, int]:
        """
        获取指定提案的投票统计

        Args:
            proposal_id: 提案 ID

        Returns:
            包含 yes/no/abstain 计数的字典
        """
        with self._lock:
            return self._get_vote_count_unsafe(proposal_id)

    def is_accepted(self, proposal_id: str) -> bool:
        """
        判断提案是否已被接受

        Args:
            proposal_id: 提案 ID

        Returns:
            是否已接受
        """
        with self._lock:
            proposal = self._proposals.get(proposal_id)
            if proposal is None:
                return False
            return proposal.status == ProposalStatus.ACCEPTED

    def get_current_term(self) -> int:
        """获取当前任期号"""
        with self._lock:
            return self._current_term

    def increment_term(self) -> int:
        """递增任期号并返回新值"""
        with self._lock:
            self._current_term += 1
            return self._current_term

    def expire_old_proposals(self, max_age_seconds: float = 60.0) -> int:
        """
        将超时的待处理提案标记为过期

        Args:
            max_age_seconds: 最大存活时间（秒）

        Returns:
            过期的提案数量
        """
        with self._lock:
            now = time.time()
            expired_count = 0
            for proposal in self._proposals.values():
                if proposal.status == ProposalStatus.PENDING and (now - proposal.created_at) > max_age_seconds:
                    proposal.status = ProposalStatus.EXPIRED
                    expired_count += 1
            return expired_count

    def get_statistics(self) -> Dict:
        """
        获取共识引擎统计信息

        Returns:
            包含各类状态提案数量和总投票数的字典
        """
        with self._lock:
            stats = {
                "total_proposals": len(self._proposals),
                "total_votes": sum(len(votes) for votes in self._votes.values()),
                "current_term": self._current_term,
                "by_status": {
                    ProposalStatus.PENDING.value: 0,
                    ProposalStatus.ACCEPTED.value: 0,
                    ProposalStatus.REJECTED.value: 0,
                    ProposalStatus.COMMITTED.value: 0,
                    ProposalStatus.EXPIRED.value: 0,
                },
            }
            for proposal in self._proposals.values():
                status_key = proposal.status.value
                stats["by_status"][status_key] = stats["by_status"].get(status_key, 0) + 1
            return stats


# 全局单例实例与锁
_engine_instance: Optional[ConsensusEngine] = None
_engine_lock: threading.Lock = threading.Lock()


def get_consensus_engine() -> ConsensusEngine:
    """
    获取 ConsensusEngine 全局单例

    使用双检锁机制确保线程安全且高效。

    Returns:
        ConsensusEngine 单例实例
    """
    global _engine_instance
    if _engine_instance is None:
        with _engine_lock:
            if _engine_instance is None:
                _engine_instance = ConsensusEngine()
    return _engine_instance


def reset_consensus_engine() -> None:
    """
    重置全局单例（主要用于测试）
    """
    global _engine_instance
    with _engine_lock:
        _engine_instance = None
