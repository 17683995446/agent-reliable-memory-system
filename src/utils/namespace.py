#!/usr/bin/env python3
"""
命名空间管理模块 - 阶段107-109
多租户隔离支持
"""

import threading
from typing import Dict, Set, Optional


class NamespaceManager:
    """
    命名空间管理器
    
    实现多租户隔离，每个租户拥有独立的命名空间
    """
    
    def __init__(self):
        self._namespaces: Dict[str, Set[str]] = {}  # namespace -> set of memory_ids
        self._memory_to_namespace: Dict[str, str] = {}  # memory_id -> namespace
        self._lock = threading.RLock()
    
    def register_memory(self, memory_id: str, namespace: str = "default") -> bool:
        """
        将记忆注册到指定命名空间
        
        Args:
            memory_id: 记忆ID
            namespace: 命名空间标识
        """
        with self._lock:
            if namespace not in self._namespaces:
                self._namespaces[namespace] = set()
            
            self._namespaces[namespace].add(memory_id)
            self._memory_to_namespace[memory_id] = namespace
            return True
    
    def get_namespace(self, memory_id: str) -> Optional[str]:
        """获取记忆所属的命名空间"""
        with self._lock:
            return self._memory_to_namespace.get(memory_id)
    
    def list_namespaces(self) -> list:
        """列出所有命名空间"""
        with self._lock:
            return list(self._namespaces.keys())
    
    def get_memories_in_namespace(self, namespace: str) -> Set[str]:
        """获取命名空间中的所有记忆"""
        with self._lock:
            return self._namespaces.get(namespace, set()).copy()
    
    def delete_memory(self, memory_id: str) -> bool:
        """从命名空间中删除记忆"""
        with self._lock:
            if memory_id in self._memory_to_namespace:
                namespace = self._memory_to_namespace[memory_id]
                if namespace in self._namespaces:
                    self._namespaces[namespace].discard(memory_id)
                del self._memory_to_namespace[memory_id]
                return True
            return False
    
    def clear_namespace(self, namespace: str) -> int:
        """清空命名空间，返回删除的记忆数量"""
        with self._lock:
            if namespace not in self._namespaces:
                return 0
            
            count = len(self._namespaces[namespace])
            for memory_id in list(self._namespaces[namespace]):
                del self._memory_to_namespace[memory_id]
            
            self._namespaces[namespace].clear()
            return count
    
    def get_stats(self) -> Dict[str, int]:
        """获取命名空间统计"""
        with self._lock:
            return {
                "total_namespaces": len(self._namespaces),
                "total_memories": len(self._memory_to_namespace),
                "namespace_sizes": {
                    ns: len(mems) for ns, mems in self._namespaces.items()
                }
            }


# 全局命名空间管理器
_namespace_manager: Optional[NamespaceManager] = None


def get_namespace_manager() -> NamespaceManager:
    """获取全局命名空间管理器"""
    global _namespace_manager
    if _namespace_manager is None:
        _namespace_manager = NamespaceManager()
    return _namespace_manager
