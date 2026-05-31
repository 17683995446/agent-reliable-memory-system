"""
智能推荐器 - 阶段221-223

功能：
- 阶段221: 内容推荐
- 阶段222: 协同过滤
- 阶段223: 个性化

设计原则：
- 确定性规则，无模型依赖
- 最小层级，无循环依赖
- 线程安全，RLock保护
- 单例模式，全局唯一
"""

import threading
import time
import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Dict, List, Optional, Callable, Any, Set, Tuple
from collections import defaultdict, deque
import uuid
import heapq


class RecommendationType(Enum):
    """推荐类型"""
    CONTENT_BASED = "content_based"
    COLLABORATIVE = "collaborative"
    POPULAR = "popular"
    TRENDING = "trending"
    HYBRID = "hybrid"


class InteractionType(Enum):
    """交互类型"""
    VIEW = "view"
    LIKE = "like"
    DISLIKE = "dislike"
    SAVE = "save"
    SHARE = "share"
    CLICK = "click"
    RATING = "rating"


@dataclass
class UserProfile:
    """用户画像"""
    user_id: str
    preferences: Dict[str, float] = field(default_factory=dict)
    interaction_history: List[Dict[str, Any]] = field(default_factory=list)
    category_weights: Dict[str, float] = field(default_factory=dict)
    last_updated: float = field(default_factory=time.time)


@dataclass
class Item:
    """推荐项"""
    item_id: str
    item_type: str
    content: str
    features: Dict[str, Any] = field(default_factory=dict)
    categories: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    popularity_score: float = 0.0
    created_at: float = field(default_factory=time.time)


@dataclass
class Interaction:
    """用户交互"""
    interaction_id: str
    user_id: str
    item_id: str
    interaction_type: InteractionType
    timestamp: float
    value: float = 1.0  # 交互强度
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Recommendation:
    """推荐结果"""
    item_id: str
    score: float
    recommendation_type: RecommendationType
    reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class RecommendationEngine:
    """
    智能推荐器
    
    阶段221: 内容推荐
    - 基于内容的相似度计算
    - 标签匹配
    - 特征向量相似度
    
    阶段222: 协同过滤
    - 用户相似度计算
    - 物品相似度计算
    - 隐式反馈处理
    
    阶段223: 个性化
    - 用户画像构建
    - 偏好学习
    - 多策略融合
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
            
            # 数据存储
            self._users: Dict[str, UserProfile] = {}
            self._items: Dict[str, Item] = {}
            self._interactions: deque = deque(maxlen=100000)
            
            # 相似度缓存
            self._item_similarity: Dict[str, Dict[str, float]] = defaultdict(dict)
            self._user_similarity: Dict[str, Dict[str, float]] = defaultdict(dict)
            
            # 统计
            self._item_popularity: Dict[str, int] = defaultdict(int)
            self._category_stats: Dict[str, int] = defaultdict(int)
            
            # 配置
            self._config = {
                "content_weight": 0.4,
                "collaborative_weight": 0.4,
                "popular_weight": 0.2,
                "similarity_threshold": 0.1,
                "max_recommendations": 20,
                "recency_decay": 0.95
            }
    
    # ========== 阶段221: 内容推荐 ==========
    
    def add_item(self, item_id: str, item_type: str, content: str,
                 features: Optional[Dict[str, Any]] = None,
                 categories: Optional[List[str]] = None,
                 tags: Optional[List[str]] = None) -> Item:
        """添加推荐项"""
        item = Item(
            item_id=item_id,
            item_type=item_type,
            content=content,
            features=features or {},
            categories=categories or [],
            tags=tags or []
        )
        
        with self._lock:
            self._items[item_id] = item
            
            # 更新类别统计
            for cat in item.categories:
                self._category_stats[cat] += 1
        
        return item
    
    def _calculate_content_similarity(self, item1: Item, item2: Item) -> float:
        """计算内容相似度"""
        score = 0.0
        total_weight = 0.0
        
        # 标签相似度 (Jaccard)
        if item1.tags and item2.tags:
            set1 = set(item1.tags)
            set2 = set(item2.tags)
            intersection = len(set1 & set2)
            union = len(set1 | set2)
            if union > 0:
                score += 0.4 * (intersection / union)
                total_weight += 0.4
        
        # 类别相似度
        if item1.categories and item2.categories:
            set1 = set(item1.categories)
            set2 = set(item2.categories)
            intersection = len(set1 & set2)
            union = len(set1 | set2)
            if union > 0:
                score += 0.3 * (intersection / union)
                total_weight += 0.3
        
        # 类型相同加分
        if item1.item_type == item2.item_type:
            score += 0.3
            total_weight += 0.3
        
        return score / total_weight if total_weight > 0 else 0.0
    
    def get_content_based_recommendations(self, user_id: str,
                                         n: int = 10) -> List[Recommendation]:
        """基于内容的推荐"""
        with self._lock:
            user = self._users.get(user_id)
            if not user:
                return []
            
            # 获取用户历史交互的物品
            user_items = set()
            for interaction in self._interactions:
                if interaction.user_id == user_id:
                    user_items.add(interaction.item_id)
            
            # 计算候选物品相似度
            scores = defaultdict(float)
            
            for user_item_id in user_items:
                user_item = self._items.get(user_item_id)
                if not user_item:
                    continue
                
                for item_id, item in self._items.items():
                    if item_id in user_items:
                        continue
                    
                    similarity = self._calculate_content_similarity(user_item, item)
                    scores[item_id] += similarity
            
            # 归一化并排序
            recommendations = []
            for item_id, score in heapq.nlargest(n, scores.items(), key=lambda x: x[1]):
                if score > self._config["similarity_threshold"]:
                    recommendations.append(Recommendation(
                        item_id=item_id,
                        score=score,
                        recommendation_type=RecommendationType.CONTENT_BASED,
                        reason="Similar to items you've interacted with"
                    ))
            
            return recommendations
    
    # ========== 阶段222: 协同过滤 ==========
    
    def record_interaction(self, user_id: str, item_id: str,
                          interaction_type: InteractionType,
                          value: float = 1.0,
                          context: Optional[Dict[str, Any]] = None) -> Interaction:
        """记录用户交互"""
        interaction = Interaction(
            interaction_id=str(uuid.uuid4()),
            user_id=user_id,
            item_id=item_id,
            interaction_type=interaction_type,
            timestamp=time.time(),
            value=value,
            context=context or {}
        )
        
        with self._lock:
            self._interactions.append(interaction)
            self._item_popularity[item_id] += 1
            
            # 更新用户画像
            if user_id not in self._users:
                self._users[user_id] = UserProfile(user_id=user_id)
            
            user = self._users[user_id]
            user.interaction_history.append({
                "item_id": item_id,
                "type": interaction_type.value,
                "value": value,
                "timestamp": interaction.timestamp
            })
            
            # 更新类别权重
            item = self._items.get(item_id)
            if item:
                for cat in item.categories:
                    user.category_weights[cat] = user.category_weights.get(cat, 0) + value
        
        return interaction
    
    def _calculate_user_similarity(self, user1: UserProfile, user2: UserProfile) -> float:
        """计算用户相似度"""
        # 基于类别偏好计算相似度
        categories = set(user1.category_weights.keys()) | set(user2.category_weights.keys())
        
        if not categories:
            return 0.0
        
        # 计算余弦相似度
        dot_product = 0.0
        norm1 = 0.0
        norm2 = 0.0
        
        for cat in categories:
            w1 = user1.category_weights.get(cat, 0)
            w2 = user2.category_weights.get(cat, 0)
            dot_product += w1 * w2
            norm1 += w1 * w1
            norm2 += w2 * w2
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (math.sqrt(norm1) * math.sqrt(norm2))
    
    def get_collaborative_recommendations(self, user_id: str,
                                         n: int = 10) -> List[Recommendation]:
        """协同过滤推荐"""
        with self._lock:
            target_user = self._users.get(user_id)
            if not target_user:
                return []
            
            # 获取目标用户的物品
            target_items = set()
            for interaction in self._interactions:
                if interaction.user_id == user_id:
                    target_items.add(interaction.item_id)
            
            # 计算相似用户
            similar_users = []
            for other_id, other_user in self._users.items():
                if other_id == user_id:
                    continue
                
                similarity = self._calculate_user_similarity(target_user, other_user)
                if similarity > 0:
                    similar_users.append((other_id, similarity))
            
            # 取最相似的K个用户
            similar_users.sort(key=lambda x: x[1], reverse=True)
            similar_users = similar_users[:20]
            
            # 收集推荐
            scores = defaultdict(float)
            
            for similar_id, similarity in similar_users:
                for interaction in self._interactions:
                    if interaction.user_id == similar_id:
                        if interaction.item_id not in target_items:
                            scores[interaction.item_id] += similarity * interaction.value
            
            # 生成推荐
            recommendations = []
            for item_id, score in heapq.nlargest(n, scores.items(), key=lambda x: x[1]):
                recommendations.append(Recommendation(
                    item_id=item_id,
                    score=score,
                    recommendation_type=RecommendationType.COLLABORATIVE,
                    reason="Users similar to you liked this"
                ))
            
            return recommendations
    
    # ========== 阶段223: 个性化 ==========
    
    def get_popular_recommendations(self, n: int = 10,
                                   category: Optional[str] = None) -> List[Recommendation]:
        """热门推荐"""
        with self._lock:
            items_with_scores = []
            
            for item_id, popularity in self._item_popularity.items():
                item = self._items.get(item_id)
                if item:
                    if category is None or category in item.categories:
                        # 时间衰减
                        age_hours = (time.time() - item.created_at) / 3600
                        decayed_score = popularity * (self._config["recency_decay"] ** age_hours)
                        items_with_scores.append((item_id, decayed_score))
            
            items_with_scores.sort(key=lambda x: x[1], reverse=True)
            
            recommendations = []
            for item_id, score in items_with_scores[:n]:
                recommendations.append(Recommendation(
                    item_id=item_id,
                    score=score,
                    recommendation_type=RecommendationType.POPULAR,
                    reason="Popular among users"
                ))
            
            return recommendations
    
    def get_personalized_recommendations(self, user_id: str,
                                        n: int = 10) -> List[Recommendation]:
        """个性化推荐（混合策略）"""
        content_recs = self.get_content_based_recommendations(user_id, n)
        collab_recs = self.get_collaborative_recommendations(user_id, n)
        popular_recs = self.get_popular_recommendations(n)
        
        # 合并并加权
        scores = defaultdict(lambda: {"score": 0.0, "reasons": [], "types": []})
        
        for rec in content_recs:
            scores[rec.item_id]["score"] += rec.score * self._config["content_weight"]
            scores[rec.item_id]["reasons"].append(rec.reason)
            scores[rec.item_id]["types"].append("content")
        
        for rec in collab_recs:
            scores[rec.item_id]["score"] += rec.score * self._config["collaborative_weight"]
            scores[rec.item_id]["reasons"].append(rec.reason)
            scores[rec.item_id]["types"].append("collaborative")
        
        for rec in popular_recs:
            scores[rec.item_id]["score"] += rec.score * self._config["popular_weight"]
            scores[rec.item_id]["reasons"].append(rec.reason)
            scores[rec.item_id]["types"].append("popular")
        
        # 生成最终推荐
        recommendations = []
        for item_id, data in heapq.nlargest(n, scores.items(), key=lambda x: x[1]["score"]):
            # 确定推荐类型
            types = data["types"]
            if len(types) > 1:
                rec_type = RecommendationType.HYBRID
            elif types:
                rec_type = RecommendationType(types[0])
            else:
                rec_type = RecommendationType.POPULAR
            
            recommendations.append(Recommendation(
                item_id=item_id,
                score=data["score"],
                recommendation_type=rec_type,
                reason="; ".join(set(data["reasons"]))
            ))
        
        return recommendations
    
    def update_user_preferences(self, user_id: str,
                                preferences: Dict[str, float]) -> bool:
        """更新用户偏好"""
        with self._lock:
            if user_id not in self._users:
                self._users[user_id] = UserProfile(user_id=user_id)
            
            user = self._users[user_id]
            user.preferences.update(preferences)
            user.last_updated = time.time()
            
            return True
    
    def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        """获取用户画像"""
        with self._lock:
            return self._users.get(user_id)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                "users": len(self._users),
                "items": len(self._items),
                "interactions": len(self._interactions),
                "categories": len(self._category_stats)
            }


# 全局单例
_recommendation_engine_instance: Optional[RecommendationEngine] = None
_recommendation_engine_lock = threading.RLock()


def get_recommendation_engine() -> RecommendationEngine:
    """获取智能推荐器全局实例"""
    global _recommendation_engine_instance
    if _recommendation_engine_instance is None:
        with _recommendation_engine_lock:
            if _recommendation_engine_instance is None:
                _recommendation_engine_instance = RecommendationEngine()
    return _recommendation_engine_instance
