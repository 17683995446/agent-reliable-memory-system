#!/usr/bin/env python3
"""
批量操作模块 - 阶段134-136
支持批量存储、召回、删除
"""

import threading
from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class BatchResult:
    """批量操作结果"""
    total: int
    success: int
    failed: int
    errors: List[Dict[str, Any]]
    details: List[Dict[str, Any]]

    @property
    def success_rate(self) -> float:
        return (self.success / self.total * 100) if self.total > 0 else 0.0


class BatchOperator:
    """
    批量操作器
    
    对记忆系统提供批量操作能力，支持：
    - 批量存储
    - 批量召回
    - 批量删除
    - 操作结果汇总
    """

    def __init__(self, memory_system):
        self.memory_system = memory_system
        self._lock = threading.RLock()

    def batch_remember(
        self,
        items: List[Dict[str, str]],
        task_id: str,
        visibility: str = "private",
        owner_id: Optional[str] = None
    ) -> BatchResult:
        """
        批量存储记忆

        Args:
            items: 记忆列表，每项包含 {"content": "..."}
            task_id: 任务标识
            visibility: 可见性
            owner_id: 所有者ID

        Returns:
            批量操作结果
        """
        success = 0
        failed = 0
        errors = []
        details = []

        for i, item in enumerate(items):
            content = item.get("content", "")
            if not content:
                failed += 1
                errors.append({"index": i, "error": "内容为空"})
                details.append({"index": i, "success": False, "error": "内容为空"})
                continue

            try:
                result = self.memory_system.remember(
                    content=content,
                    task_id=task_id,
                    visibility=visibility,
                    owner_id=owner_id
                )
                if result["success"]:
                    success += 1
                    details.append({
                        "index": i,
                        "success": True,
                        "memory_id": result.get("memory_id"),
                        "layer": result.get("layer"),
                    })
                else:
                    failed += 1
                    err_msg = result.get("message", "未知错误")
                    errors.append({"index": i, "error": err_msg})
                    details.append({"index": i, "success": False, "error": err_msg})
            except Exception as e:
                failed += 1
                errors.append({"index": i, "error": str(e)})
                details.append({"index": i, "success": False, "error": str(e)})

        return BatchResult(
            total=len(items),
            success=success,
            failed=failed,
            errors=errors,
            details=details,
        )

    def batch_recall(
        self,
        queries: List[str],
        task_id: str,
        top_k: int = 5,
        user_id: Optional[str] = None,
        deduplicate: bool = True
    ) -> Dict[str, Any]:
        """
        批量召回记忆

        Args:
            queries: 查询列表
            task_id: 任务标识
            top_k: 每个查询返回数量
            user_id: 用户ID
            deduplicate: 是否跨查询去重

        Returns:
            批量召回结果
        """
        all_results = []
        seen_ids = set()

        for query in queries:
            results = self.memory_system.recall(
                query=query,
                task_id=task_id,
                top_k=top_k,
                user_id=user_id
            )

            filtered = []
            for r in results:
                mem_id = r.get("memory_id", "")
                if deduplicate and mem_id in seen_ids:
                    continue
                if deduplicate:
                    seen_ids.add(mem_id)
                filtered.append(r)

            all_results.append({
                "query": query,
                "count": len(filtered),
                "results": filtered,
            })

        return {
            "total_queries": len(queries),
            "total_results": sum(a["count"] for a in all_results),
            "unique_results": len(seen_ids) if deduplicate else sum(a["count"] for a in all_results),
            "queries": all_results,
        }

    def batch_forget(
        self,
        memory_ids: List[str],
        task_id: str
    ) -> BatchResult:
        """
        批量删除记忆

        Args:
            memory_ids: 记忆ID列表
            task_id: 任务标识

        Returns:
            批量操作结果
        """
        success = 0
        failed = 0
        errors = []
        details = []

        for i, mem_id in enumerate(memory_ids):
            try:
                result = self.memory_system.forget(mem_id, task_id)
                if result["success"]:
                    success += 1
                    details.append({"index": i, "memory_id": mem_id, "success": True})
                else:
                    failed += 1
                    err_msg = result.get("message", "删除失败")
                    errors.append({"index": i, "memory_id": mem_id, "error": err_msg})
                    details.append({"index": i, "memory_id": mem_id, "success": False, "error": err_msg})
            except Exception as e:
                failed += 1
                errors.append({"index": i, "memory_id": mem_id, "error": str(e)})
                details.append({"index": i, "memory_id": mem_id, "success": False, "error": str(e)})

        return BatchResult(
            total=len(memory_ids),
            success=success,
            failed=failed,
            errors=errors,
            details=details,
        )

    def batch_export(
        self,
        queries: List[str],
        task_id: str,
        top_k: int = 100
    ) -> List[Dict[str, Any]]:
        """
        批量导出记忆

        合并多个查询的召回结果，去重后返回
        """
        seen_ids = set()
        all_memories = []

        for query in queries:
            results = self.memory_system.recall(query, task_id, top_k)
            for r in results:
                mem_id = r.get("memory_id", "")
                if mem_id and mem_id not in seen_ids:
                    seen_ids.add(mem_id)
                    all_memories.append(r)

        return all_memories
