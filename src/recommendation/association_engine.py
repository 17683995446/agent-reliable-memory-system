"""
Agent可靠记忆系统 - 记忆关联推荐引擎
阶段167-169: 基于确定性规则的记忆关联发现与推荐

设计原则:
- 确定性规则驱动，无模型依赖
- 线程安全（RLock）
- 全局单例模式
- 多维度关联：标签、内容、时间、层级、引用
"""

import threading
import time
import re
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Any
from collections import defaultdict


class AssociationType(Enum):
    """关联类型"""
    TAG_SHARED = "tag_shared"              # 共享标签
    CONTENT_SIMILAR = "content_similar"    # 内容相似
    TEMPORAL_CLOSE = "temporal_close"      # 时间相近
    LAYER_SAME = "layer_same"              # 同层级
    NAMESPACE_SAME = "namespace_same"      # 同命名空间
    REFERENCE = "reference"                # 引用关系
    SEQUENCE = "sequence"                  # 序列关系
    CO_OCCURRENCE = "co_occurrence"        # 共现关系
    HIERARCHY = "hierarchy"                # 层级关系
    CUSTOM = "custom"                      # 自定义关联


class AssociationStrength(Enum):
    """关联强度"""
    WEAK = 0.2
    MODERATE = 0.5
    STRONG = 0.8
    VERY_STRONG = 1.0


@dataclass
class Association:
    """记忆关联数据结构"""
    source_id: str                         # 源记忆ID
    target_id: str                         # 目标记忆ID
    association_type: AssociationType
    strength: float = 0.5                  # 关联强度 [0, 1]
    metadata: Dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    access_count: int = 0                  # 被访问次数
    last_accessed: float = 0               # 最后访问时间

    @property
    def key(self) -> str:
        """关联的唯一键（排序后确保方向无关）"""
        ids = sorted([self.source_id, self.target_id])
        return f"{ids[0]}::{ids[1]}::{self.association_type.value}"

    def to_dict(self) -> Dict:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "type": self.association_type.value,
            "strength": round(self.strength, 4),
            "metadata": self.metadata,
            "created_at": self.created_at,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed,
        }


@dataclass
class Recommendation:
    """推荐结果"""
    memory_id: str
    score: float                           # 推荐分数 [0, 1]
    reasons: List[str] = field(default_factory=list)  # 推荐理由
    associations: List[Association] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "memory_id": self.memory_id,
            "score": round(self.score, 4),
            "reasons": self.reasons,
            "association_types": [
                a.association_type.value for a in self.associations
            ],
        }


@dataclass
class MemoryProfile:
    """记忆画像（用于关联计算）"""
    memory_id: str
    content: str = ""
    layer: str = ""
    namespace: str = ""
    tags: Set[str] = field(default_factory=set)
    keywords: Set[str] = field(default_factory=set)
    entities: Set[str] = field(default_factory=set)
    created_at: float = 0
    updated_at: float = 0
    access_count: int = 0
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "memory_id": self.memory_id,
            "layer": self.layer,
            "namespace": self.namespace,
            "tags": list(self.tags),
            "keywords": list(self.keywords),
            "entities": list(self.entities),
            "created_at": self.created_at,
            "access_count": self.access_count,
        }


class AssociationEngine:
    """
    记忆关联推荐引擎

    功能:
    - 多维度关联发现（标签、内容、时间、层级等）
    - 关联强度计算
    - 记忆推荐
    - 关联图分析
    - 关联规则管理
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._profiles: Dict[str, MemoryProfile] = {}        # memory_id -> profile
        self._associations: Dict[str, Association] = {}      # key -> Association
        self._memory_associations: Dict[str, Set[str]] = {}  # memory_id -> set of association keys
        self._co_occurrence: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._access_history: List[Tuple[str, float]] = []   # (memory_id, timestamp)

        # 配置
        self._config = {
            "content_similarity_threshold": 0.3,
            "temporal_window_hours": 24,
            "max_recommendations": 20,
            "min_strength": 0.1,
            "tag_weight": 0.3,
            "content_weight": 0.25,
            "temporal_weight": 0.15,
            "co_occurrence_weight": 0.2,
            "access_pattern_weight": 0.1,
        }

    # ==================== 记忆画像管理 ====================

    def update_profile(self, memory_id: str, content: str = "",
                       layer: str = "", namespace: str = "",
                       tags: Optional[List[str]] = None,
                       metadata: Optional[Dict] = None,
                       created_at: Optional[float] = None,
                       updated_at: Optional[float] = None) -> MemoryProfile:
        """
        更新记忆画像

        Args:
            memory_id: 记忆ID
            content: 记忆内容
            layer: 记忆层级
            namespace: 命名空间
            tags: 标签列表
            metadata: 元数据
            created_at: 创建时间
            updated_at: 更新时间
        """
        with self._lock:
            profile = self._profiles.get(memory_id)
            if profile:
                if content:
                    profile.content = content
                if layer:
                    profile.layer = layer
                if namespace:
                    profile.namespace = namespace
                if tags is not None:
                    profile.tags = set(tags)
                if metadata:
                    profile.metadata.update(metadata)
                if created_at:
                    profile.created_at = created_at
                if updated_at:
                    profile.updated_at = updated_at
            else:
                profile = MemoryProfile(
                    memory_id=memory_id,
                    content=content,
                    layer=layer,
                    namespace=namespace,
                    tags=set(tags or []),
                    metadata=metadata or {},
                    created_at=created_at or time.time(),
                    updated_at=updated_at or time.time(),
                )

            # 提取关键词和实体
            if content:
                profile.keywords = self._extract_keywords(content)
                profile.entities = self._extract_entities(content)

            self._profiles[memory_id] = profile
            return profile

    def remove_profile(self, memory_id: str) -> bool:
        """移除记忆画像及相关关联"""
        with self._lock:
            if memory_id not in self._profiles:
                return False

            # 移除相关关联
            assoc_keys = list(self._memory_associations.get(memory_id, set()))
            for key in assoc_keys:
                self._associations.pop(key, None)
            self._memory_associations.pop(memory_id, None)

            # 移除共现记录
            self._co_occurrence.pop(memory_id, None)
            for mid in self._co_occurrence:
                self._co_occurrence[mid].pop(memory_id, None)

            del self._profiles[memory_id]
            return True

    def get_profile(self, memory_id: str) -> Optional[MemoryProfile]:
        """获取记忆画像"""
        with self._lock:
            return self._profiles.get(memory_id)

    def record_access(self, memory_id: str, timestamp: Optional[float] = None):
        """记录记忆访问"""
        with self._lock:
            ts = timestamp or time.time()
            self._access_history.append((memory_id, ts))
            # 保留最近10000条记录
            if len(self._access_history) > 10000:
                self._access_history = self._access_history[-5000:]

            if memory_id in self._profiles:
                self._profiles[memory_id].access_count += 1

    def record_co_occurrence(self, memory_ids: List[str]):
        """
        记忆记忆共现（同时被访问/召回）

        Args:
            memory_ids: 同时出现的记忆ID列表
        """
        with self._lock:
            ids = list(set(memory_ids))
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    self._co_occurrence[ids[i]][ids[j]] += 1
                    self._co_occurrence[ids[j]][ids[i]] += 1

    # ==================== 关联发现 ====================

    def discover_associations(self, memory_id: str) -> List[Association]:
        """
        发现指定记忆的所有关联

        Args:
            memory_id: 目标记忆ID

        Returns:
            发现的关联列表
        """
        with self._lock:
            profile = self._profiles.get(memory_id)
            if not profile:
                return []

            new_associations = []

            for other_id, other_profile in self._profiles.items():
                if other_id == memory_id:
                    continue

                # 检查是否已存在关联
                existing_key = self._find_association_key(memory_id, other_id)
                if existing_key:
                    continue

                # 多维度关联发现
                associations = self._compute_associations(profile, other_profile)
                new_associations.extend(associations)

            # 保存新关联
            for assoc in new_associations:
                if assoc.strength >= self._config["min_strength"]:
                    key = assoc.key
                    if key not in self._associations:
                        self._associations[key] = assoc
                        if memory_id not in self._memory_associations:
                            self._memory_associations[memory_id] = set()
                        if other_id(assoc) not in self._memory_associations:
                            self._memory_associations[other_id(assoc)] = set()
                        self._memory_associations[memory_id].add(key)
                        self._memory_associations[other_id(assoc)].add(key)

            return new_associations

    def _find_association_key(self, id1: str, id2: str) -> Optional[str]:
        """查找两个记忆之间是否已有关联"""
        ids = sorted([id1, id2])
        for atype in AssociationType:
            key = f"{ids[0]}::{ids[1]}::{atype.value}"
            if key in self._associations:
                return key
        return None

    def _compute_associations(self, p1: MemoryProfile,
                              p2: MemoryProfile) -> List[Association]:
        """计算两个记忆之间的关联"""
        associations = []

        # 1. 标签共享
        shared_tags = p1.tags & p2.tags
        if shared_tags:
            strength = min(len(shared_tags) / max(len(p1.tags), len(p2.tags), 1), 1.0)
            strength = strength * self._config["tag_weight"] / self._config["tag_weight"]
            associations.append(Association(
                source_id=p1.memory_id,
                target_id=p2.memory_id,
                association_type=AssociationType.TAG_SHARED,
                strength=strength,
                metadata={"shared_tags": list(shared_tags)},
            ))

        # 2. 内容相似
        content_sim = self._content_similarity(p1, p2)
        if content_sim >= self._config["content_similarity_threshold"]:
            associations.append(Association(
                source_id=p1.memory_id,
                target_id=p2.memory_id,
                association_type=AssociationType.CONTENT_SIMILAR,
                strength=content_sim,
                metadata={"similarity": round(content_sim, 4)},
            ))

        # 3. 时间相近
        if p1.created_at > 0 and p2.created_at > 0:
            time_diff_hours = abs(p1.created_at - p2.created_at) / 3600
            window = self._config["temporal_window_hours"]
            if time_diff_hours <= window:
                strength = 1.0 - (time_diff_hours / window)
                associations.append(Association(
                    source_id=p1.memory_id,
                    target_id=p2.memory_id,
                    association_type=AssociationType.TEMPORAL_CLOSE,
                    strength=strength * 0.5,
                    metadata={"time_diff_hours": round(time_diff_hours, 2)},
                ))

        # 4. 同层级
        if p1.layer and p2.layer and p1.layer == p2.layer:
            associations.append(Association(
                source_id=p1.memory_id,
                target_id=p2.memory_id,
                association_type=AssociationType.LAYER_SAME,
                strength=0.3,
            ))

        # 5. 同命名空间
        if p1.namespace and p2.namespace and p1.namespace == p2.namespace:
            associations.append(Association(
                source_id=p1.memory_id,
                target_id=p2.memory_id,
                association_type=AssociationType.NAMESPACE_SAME,
                strength=0.2,
            ))

        # 6. 共现关系
        co_count = self._co_occurrence.get(p1.memory_id, {}).get(p2.memory_id, 0)
        if co_count > 0:
            strength = min(co_count / 10.0, 1.0)
            associations.append(Association(
                source_id=p1.memory_id,
                target_id=p2.memory_id,
                association_type=AssociationType.CO_OCCURRENCE,
                strength=strength,
                metadata={"co_occurrence_count": co_count},
            ))

        # 7. 实体共享
        shared_entities = p1.entities & p2.entities
        if shared_entities:
            strength = min(len(shared_entities) / 5.0, 1.0)
            associations.append(Association(
                source_id=p1.memory_id,
                target_id=p2.memory_id,
                association_type=AssociationType.HIERARCHY,
                strength=strength * 0.4,
                metadata={"shared_entities": list(shared_entities)},
            ))

        return associations

    def _content_similarity(self, p1: MemoryProfile, p2: MemoryProfile) -> float:
        """计算内容相似度（基于关键词Jaccard系数）"""
        if not p1.keywords or not p2.keywords:
            return 0.0

        intersection = p1.keywords & p2.keywords
        union = p1.keywords | p2.keywords

        if not union:
            return 0.0

        jaccard = len(intersection) / len(union)

        # 加入实体匹配加成
        entity_overlap = len(p1.entities & p2.entities)
        entity_bonus = min(entity_overlap * 0.1, 0.3)

        return min(jaccard + entity_bonus, 1.0)

    def _extract_keywords(self, text: str) -> Set[str]:
        """从文本中提取关键词（确定性规则）"""
        if not text:
            return set()

        # 分词：按空格、标点分割
        words = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]{2,}', text.lower())

        # 中文停用词
        cn_stopwords = {
            '的', '了', '在', '是', '我', '有', '和', '就', '不', '人',
            '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去',
            '你', '会', '着', '没有', '看', '好', '自己', '这', '他', '她',
            '它', '们', '那', '些', '什么', '如何', '怎么', '为什么', '可以',
            '能', '这个', '那个', '但是', '因为', '所以', '如果', '虽然',
            '已经', '正在', '将要', '应该', '需要', '能够', '可能',
        }

        keywords = set()
        for word in words:
            # 跳过单字（中文）和停用词
            if len(word) == 1 and '\u4e00' <= word <= '\u9fff':
                continue
            if word in cn_stopwords:
                continue
            if len(word) < 2:
                continue
            keywords.add(word)

        return keywords

    def _extract_entities(self, text: str) -> Set[str]:
        """从文本中提取实体（确定性规则）"""
        if not text:
            return set()

        entities = set()

        # 提取数字+单位
        number_units = re.findall(
            r'\d+[\.\d]*\s*(?:个|条|次|天|小时|分钟|秒|年|月|周|元|美元|%'
            r'|MB|GB|TB|KB|px|cm|mm|m|km|kg|g|mg)',
            text
        )
        entities.update(number_units)

        # 提取邮箱
        emails = re.findall(r'[\w.+-]+@[\w-]+\.[\w.-]+', text)
        entities.update(emails)

        # 提取URL
        urls = re.findall(r'https?://\S+', text)
        entities.update(urls)

        # 提取路径
        paths = re.findall(r'/[\w/.-]+', text)
        entities.update(paths)

        # 提取引号内容
        quoted = re.findall(r'["\u201c]([^"\u201d]+)["\u201d]', text)
        entities.update(quoted)

        return entities

    # ==================== 推荐引擎 ====================

    def recommend(self, memory_id: str,
                  limit: Optional[int] = None,
                  association_types: Optional[List[AssociationType]] = None,
                  min_strength: Optional[float] = None) -> List[Recommendation]:
        """
        推荐与指定记忆相关的记忆

        Args:
            memory_id: 目标记忆ID
            limit: 推荐数量限制
            association_types: 关联类型过滤
            min_strength: 最低关联强度
        """
        with self._lock:
            limit = limit or self._config["max_recommendations"]
            min_str = min_strength or self._config["min_strength"]

            # 收集所有关联记忆
            scored: Dict[str, Recommendation] = {}

            assoc_keys = self._memory_associations.get(memory_id, set())
            for key in assoc_keys:
                assoc = self._associations.get(key)
                if not assoc:
                    continue

                # 类型过滤
                if association_types and assoc.association_type not in association_types:
                    continue

                # 强度过滤
                if assoc.strength < min_str:
                    continue

                target_id = assoc.target_id if assoc.source_id == memory_id else assoc.source_id

                if target_id not in scored:
                    scored[target_id] = Recommendation(
                        memory_id=target_id,
                        score=0,
                        reasons=[],
                        associations=[],
                    )

                rec = scored[target_id]
                rec.score += assoc.strength
                rec.associations.append(assoc)

                # 生成推荐理由
                reason = self._generate_reason(assoc)
                if reason and reason not in rec.reasons:
                    rec.reasons.append(reason)

            # 访问模式加成
            self._apply_access_pattern_bonus(memory_id, scored)

            # 排序
            recommendations = sorted(
                scored.values(),
                key=lambda r: r.score,
                reverse=True
            )

            return recommendations[:limit]

    def recommend_for_query(self, query: str,
                            limit: Optional[int] = None) -> List[Recommendation]:
        """
        基于查询文本推荐记忆

        Args:
            query: 查询文本
            limit: 推荐数量限制
        """
        with self._lock:
            limit = limit or self._config["max_recommendations"]
            query_keywords = self._extract_keywords(query)
            query_entities = self._extract_entities(query)

            if not query_keywords and not query_entities:
                return []

            scored: Dict[str, float] = {}

            for mid, profile in self._profiles.items():
                score = 0.0

                # 关键词匹配
                if query_keywords and profile.keywords:
                    overlap = query_keywords & profile.keywords
                    if overlap:
                        score += len(overlap) / len(query_keywords) * 0.5

                # 实体匹配
                if query_entities and profile.entities:
                    overlap = query_entities & profile.entities
                    if overlap:
                        score += len(overlap) / max(len(query_entities), 1) * 0.3

                # 标签匹配
                if query_keywords and profile.tags:
                    tag_overlap = query_keywords & set(t.lower() for t in profile.tags)
                    if tag_overlap:
                        score += len(tag_overlap) / len(query_keywords) * 0.2

                if score > 0:
                    scored[mid] = score

            # 排序
            sorted_ids = sorted(scored.items(), key=lambda x: x[1], reverse=True)

            recommendations = []
            for mid, score in sorted_ids[:limit]:
                reasons = []
                profile = self._profiles.get(mid)
                if profile:
                    overlap_kw = query_keywords & profile.keywords
                    if overlap_kw:
                        reasons.append(f"关键词匹配: {', '.join(list(overlap_kw)[:3])}")
                    overlap_ent = query_entities & profile.entities
                    if overlap_ent:
                        reasons.append(f"实体匹配: {', '.join(list(overlap_ent)[:3])}")

                recommendations.append(Recommendation(
                    memory_id=mid,
                    score=score,
                    reasons=reasons,
                ))

            return recommendations

    def _generate_reason(self, assoc: Association) -> str:
        """生成推荐理由"""
        type_reasons = {
            AssociationType.TAG_SHARED: "共享标签",
            AssociationType.CONTENT_SIMILAR: "内容相似",
            AssociationType.TEMPORAL_CLOSE: "创建时间相近",
            AssociationType.LAYER_SAME: "同一记忆层级",
            AssociationType.NAMESPACE_SAME: "同一命名空间",
            AssociationType.REFERENCE: "存在引用关系",
            AssociationType.SEQUENCE: "存在序列关系",
            AssociationType.CO_OCCURRENCE: "经常一起出现",
            AssociationType.HIERARCHY: "共享实体",
            AssociationType.CUSTOM: "自定义关联",
        }

        base_reason = type_reasons.get(assoc.association_type, "关联")

        if assoc.association_type == AssociationType.TAG_SHARED:
            tags = assoc.metadata.get("shared_tags", [])
            if tags:
                base_reason += f": {', '.join(tags[:3])}"
        elif assoc.association_type == AssociationType.CO_OCCURRENCE:
            count = assoc.metadata.get("co_occurrence_count", 0)
            base_reason += f" ({count}次)"

        return base_reason

    def _apply_access_pattern_bonus(self, memory_id: str,
                                    scored: Dict[str, Recommendation]):
        """应用访问模式加成（经常一起访问的记忆加分）"""
        # 找到与memory_id经常一起访问的记忆
        co_counts: Dict[str, int] = defaultdict(int)

        for mid, ts in self._access_history:
            if mid == memory_id:
                # 查找时间窗口内的其他访问
                window = 300  # 5分钟窗口
                for mid2, ts2 in self._access_history:
                    if mid2 != memory_id and abs(ts - ts2) <= window:
                        co_counts[mid2] += 1

        max_co = max(co_counts.values()) if co_counts else 0
        if max_co == 0:
            return

        for mid, count in co_counts.items():
            if mid in scored:
                bonus = (count / max_co) * self._config["access_pattern_weight"]
                scored[mid].score += bonus
                reason = f"访问模式关联 (共现{count}次)"
                if reason not in scored[mid].reasons:
                    scored[mid].reasons.append(reason)

    # ==================== 关联管理 ====================

    def add_association(self, source_id: str, target_id: str,
                        association_type: AssociationType,
                        strength: float = 0.5,
                        metadata: Optional[Dict] = None) -> Association:
        """手动添加关联"""
        with self._lock:
            assoc = Association(
                source_id=source_id,
                target_id=target_id,
                association_type=association_type,
                strength=strength,
                metadata=metadata or {},
            )
            key = assoc.key
            self._associations[key] = assoc

            for mid in [source_id, target_id]:
                if mid not in self._memory_associations:
                    self._memory_associations[mid] = set()
                self._memory_associations[mid].add(key)

            return assoc

    def remove_association(self, source_id: str, target_id: str,
                           association_type: Optional[AssociationType] = None) -> int:
        """移除关联"""
        with self._lock:
            removed = 0
            ids = sorted([source_id, target_id])

            types_to_remove = [association_type] if association_type else list(AssociationType)
            for atype in types_to_remove:
                key = f"{ids[0]}::{ids[1]}::{atype.value}"
                if key in self._associations:
                    del self._associations[key]
                    for mid in [source_id, target_id]:
                        if mid in self._memory_associations:
                            self._memory_associations[mid].discard(key)
                    removed += 1

            return removed

    def get_associations(self, memory_id: str,
                         association_type: Optional[AssociationType] = None,
                         min_strength: float = 0) -> List[Association]:
        """获取记忆的所有关联"""
        with self._lock:
            assoc_keys = self._memory_associations.get(memory_id, set())
            result = []

            for key in assoc_keys:
                assoc = self._associations.get(key)
                if not assoc:
                    continue
                if association_type and assoc.association_type != association_type:
                    continue
                if assoc.strength < min_strength:
                    continue
                result.append(assoc)

            result.sort(key=lambda a: a.strength, reverse=True)
            return result

    # ==================== 关联图分析 ====================

    def get_association_graph(self, memory_id: str,
                              max_depth: int = 1) -> Dict:
        """
        获取以指定记忆为中心的关联图

        Args:
            memory_id: 中心记忆ID
            max_depth: 最大深度

        Returns:
            图结构字典
        """
        with self._lock:
            nodes = {}
            edges = []
            visited = {memory_id}

            self._build_graph_bfs(memory_id, max_depth, 0, visited, nodes, edges)

            return {
                "center": memory_id,
                "nodes": nodes,
                "edges": edges,
                "total_nodes": len(nodes),
                "total_edges": len(edges),
            }

    def _build_graph_bfs(self, current_id: str, max_depth: int,
                         current_depth: int, visited: Set[str],
                         nodes: Dict, edges: List):
        """BFS构建关联图"""
        if current_depth > max_depth:
            return

        profile = self._profiles.get(current_id)
        if profile:
            nodes[current_id] = {
                "layer": profile.layer,
                "namespace": profile.namespace,
                "tags": list(profile.tags)[:5],
                "depth": current_depth,
            }
        else:
            nodes[current_id] = {"depth": current_depth}

        assoc_keys = self._memory_associations.get(current_id, set())
        for key in assoc_keys:
            assoc = self._associations.get(key)
            if not assoc:
                continue

            neighbor = assoc.target_id if assoc.source_id == current_id else assoc.source_id

            edges.append({
                "source": current_id,
                "target": neighbor,
                "type": assoc.association_type.value,
                "strength": round(assoc.strength, 4),
            })

            if neighbor not in visited:
                visited.add(neighbor)
                self._build_graph_bfs(
                    neighbor, max_depth, current_depth + 1,
                    visited, nodes, edges
                )

    def find_clusters(self, min_size: int = 3,
                      min_strength: float = 0.3) -> List[Dict]:
        """
        发现记忆聚类（基于关联强度的连通分量）

        Args:
            min_size: 最小聚类大小
            min_strength: 最小关联强度
        """
        with self._lock:
            # 构建邻接表
            adj: Dict[str, Set[str]] = defaultdict(set)
            for key, assoc in self._associations.items():
                if assoc.strength >= min_strength:
                    adj[assoc.source_id].add(assoc.target_id)
                    adj[assoc.target_id].add(assoc.source_id)

            # BFS找连通分量
            visited = set()
            clusters = []

            for mid in list(adj.keys()):
                if mid in visited:
                    continue

                cluster = set()
                queue = [mid]
                while queue:
                    node = queue.pop(0)
                    if node in visited:
                        continue
                    visited.add(node)
                    cluster.add(node)
                    for neighbor in adj[node]:
                        if neighbor not in visited:
                            queue.append(neighbor)

                if len(cluster) >= min_size:
                    clusters.append({
                        "size": len(cluster),
                        "memory_ids": list(cluster),
                        "avg_connections": sum(
                            len(adj[mid]) for mid in cluster
                        ) / len(cluster),
                    })

            clusters.sort(key=lambda c: c["size"], reverse=True)
            return clusters

    # ==================== 配置 ====================

    def configure(self, **kwargs):
        """更新配置"""
        with self._lock:
            for key, value in kwargs.items():
                if key in self._config:
                    self._config[key] = value

    def get_config(self) -> Dict:
        """获取当前配置"""
        return dict(self._config)

    # ==================== 统计与导出 ====================

    def get_stats(self) -> Dict:
        """获取关联引擎统计"""
        with self._lock:
            type_counts: Dict[str, int] = {}
            for assoc in self._associations.values():
                at = assoc.association_type.value
                type_counts[at] = type_counts.get(at, 0) + 1

            strengths = [a.strength for a in self._associations.values()]

            return {
                "total_profiles": len(self._profiles),
                "total_associations": len(self._associations),
                "association_types": type_counts,
                "avg_strength": round(sum(strengths) / len(strengths), 4) if strengths else 0,
                "max_strength": round(max(strengths), 4) if strengths else 0,
                "total_co_occurrence_records": sum(
                    sum(counts.values()) for counts in self._co_occurrence.values()
                ),
                "access_history_size": len(self._access_history),
            }

    def export_associations(self) -> Dict:
        """导出关联数据"""
        with self._lock:
            return {
                "profiles": {
                    mid: p.to_dict() for mid, p in self._profiles.items()
                },
                "associations": {
                    key: a.to_dict() for key, a in self._associations.items()
                },
                "statistics": self.get_stats(),
            }

    def get_summary(self) -> Dict:
        """获取关联引擎摘要"""
        with self._lock:
            return {
                "profiles": len(self._profiles),
                "associations": len(self._associations),
                "co_occurrence_pairs": len(self._co_occurrence),
                "access_records": len(self._access_history),
            }


# ==================== 全局单例 ====================

_global_association_engine: Optional[AssociationEngine] = None
_global_association_engine_lock = threading.Lock()


def get_association_engine() -> AssociationEngine:
    """获取全局关联引擎实例"""
    global _global_association_engine
    if _global_association_engine is None:
        with _global_association_engine_lock:
            if _global_association_engine is None:
                _global_association_engine = AssociationEngine()
    return _global_association_engine
