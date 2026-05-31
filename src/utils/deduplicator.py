#!/usr/bin/env python3
"""
记忆去重与合并 - 阶段146-148
检测重复记忆并智能合并
"""

import hashlib
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict


@dataclass
class DuplicateGroup:
    """重复组"""
    canonical_id: str  # 代表性记忆ID
    duplicate_ids: List[str]  # 重复记忆ID列表
    similarity: float  # 相似度
    content_preview: str  # 内容预览


class MemoryDeduplicator:
    """
    记忆去重器
    
    检测并处理重复记忆：
    - 精确匹配（内容完全相同）
    - 相似匹配（内容高度相似）
    - 智能合并（保留最完整版本）
    """

    def __init__(self, similarity_threshold: float = 0.8):
        self.similarity_threshold = similarity_threshold
        self._content_hashes: Dict[str, str] = {}  # hash -> memory_id

    def compute_hash(self, content: str) -> str:
        """计算内容哈希"""
        normalized = content.strip().lower()
        return hashlib.md5(normalized.encode()).hexdigest()

    def compute_similarity(self, text1: str, text2: str) -> float:
        """
        计算文本相似度（Jaccard系数）
        
        Args:
            text1: 文本1
            text2: 文本2
        
        Returns:
            相似度 [0, 1]
        """
        # 字符级Jaccard
        set1 = set(text1)
        set2 = set(text2)
        if not set1 or not set2:
            return 0.0
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return intersection / union if union > 0 else 0.0

    def find_exact_duplicates(
        self,
        memories: List[Dict[str, Any]]
    ) -> List[DuplicateGroup]:
        """
        查找精确重复
        
        Args:
            memories: 记忆列表
        
        Returns:
            重复组列表
        """
        hash_groups: Dict[str, List[str]] = defaultdict(list)
        content_map: Dict[str, str] = {}  # memory_id -> content

        for mem in memories:
            mem_id = mem.get("memory_id", "")
            content = mem.get("content", "")
            content_hash = self.compute_hash(content)
            hash_groups[content_hash].append(mem_id)
            content_map[mem_id] = content

        duplicates = []
        for content_hash, mem_ids in hash_groups.items():
            if len(mem_ids) > 1:
                # 找到重复组
                duplicates.append(DuplicateGroup(
                    canonical_id=mem_ids[0],
                    duplicate_ids=mem_ids[1:],
                    similarity=1.0,
                    content_preview=content_map[mem_ids[0]][:50]
                ))

        return duplicates

    def find_similar_duplicates(
        self,
        memories: List[Dict[str, Any]]
    ) -> List[DuplicateGroup]:
        """
        查找相似重复
        
        Args:
            memories: 记忆列表
        
        Returns:
            相似重复组列表
        """
        duplicates = []
        processed = set()

        for i, mem1 in enumerate(memories):
            mem1_id = mem1.get("memory_id", "")
            if mem1_id in processed:
                continue

            content1 = mem1.get("content", "")
            similar_ids = []

            for j, mem2 in enumerate(memories[i+1:], i+1):
                mem2_id = mem2.get("memory_id", "")
                if mem2_id in processed:
                    continue

                content2 = mem2.get("content", "")
                similarity = self.compute_similarity(content1, content2)

                if similarity >= self.similarity_threshold:
                    similar_ids.append((mem2_id, similarity))

            if similar_ids:
                # 找到相似组
                processed.add(mem1_id)
                for mem2_id, _ in similar_ids:
                    processed.add(mem2_id)

                duplicates.append(DuplicateGroup(
                    canonical_id=mem1_id,
                    duplicate_ids=[mid for mid, _ in similar_ids],
                    similarity=max(s for _, s in similar_ids),
                    content_preview=content1[:50]
                ))

        return duplicates

    def merge_duplicates(
        self,
        memories: List[Dict[str, Any]],
        duplicate_group: DuplicateGroup,
        strategy: str = "keep_longest"
    ) -> Dict[str, Any]:
        """
        合并重复记忆
        
        Args:
            memories: 记忆列表
            duplicate_group: 重复组
            strategy: 合并策略
                - keep_longest: 保留最长内容
                - keep_first: 保留第一条
                - keep_latest: 保留最新
        
        Returns:
            合并结果
        """
        all_ids = [duplicate_group.canonical_id] + duplicate_group.duplicate_ids
        candidates = [m for m in memories if m.get("memory_id") in all_ids]

        if not candidates:
            return {"success": False, "message": "未找到候选记忆"}

        if strategy == "keep_longest":
            selected = max(candidates, key=lambda m: len(m.get("content", "")))
        elif strategy == "keep_latest":
            selected = max(candidates, key=lambda m: m.get("created_at", ""))
        else:  # keep_first
            selected = candidates[0]

        removed_ids = [m.get("memory_id") for m in candidates if m.get("memory_id") != selected.get("memory_id")]

        return {
            "success": True,
            "kept_id": selected.get("memory_id"),
            "removed_ids": removed_ids,
            "strategy": strategy,
            "message": f"保留 {selected.get('memory_id')}，移除 {len(removed_ids)} 条重复"
        }

    def deduplicate(
        self,
        memories: List[Dict[str, Any]],
        auto_merge: bool = False,
        strategy: str = "keep_longest"
    ) -> Dict[str, Any]:
        """
        完整去重流程
        
        Args:
            memories: 记忆列表
            auto_merge: 是否自动合并
            strategy: 合并策略
        
        Returns:
            去重结果
        """
        # 查找精确重复
        exact_dups = self.find_exact_duplicates(memories)

        # 查找相似重复
        similar_dups = self.find_similar_duplicates(memories)

        # 统计
        exact_count = sum(len(d.duplicate_ids) for d in exact_dups)
        similar_count = sum(len(d.duplicate_ids) for d in similar_dups)

        result = {
            "exact_duplicates": len(exact_dups),
            "exact_duplicate_count": exact_count,
            "similar_duplicates": len(similar_dups),
            "similar_duplicate_count": similar_count,
            "total_duplicates": exact_count + similar_count,
            "exact_groups": [
                {
                    "canonical": d.canonical_id,
                    "duplicates": d.duplicate_ids,
                    "preview": d.content_preview
                }
                for d in exact_dups
            ],
            "similar_groups": [
                {
                    "canonical": d.canonical_id,
                    "duplicates": d.duplicate_ids,
                    "similarity": round(d.similarity, 2),
                    "preview": d.content_preview
                }
                for d in similar_dups
            ],
        }

        # 自动合并
        if auto_merge:
            merge_results = []
            for group in exact_dups + similar_dups:
                merge_result = self.merge_duplicates(memories, group, strategy)
                merge_results.append(merge_result)
            result["merge_results"] = merge_results

        return result
