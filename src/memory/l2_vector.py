"""
L2 情景经验记忆模块
阶段 26-27：部署FAISS向量数据库，完成环境适配调试
阶段 47：开发L2向量入库、切片编码存储功能
阶段 51：开发L2向量相似度语义召回功能
阶段 57：开发L2低频过期数据自动清理归档功能

核心特性：
- 基于 FAISS 实现高效向量检索
- 支持语义相似度搜索
- 元数据与向量分离存储
"""

import os
import json
import time
import sqlite3
import threading
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict

try:
    import faiss
except ImportError:
    faiss = None


@dataclass
class L2MemoryItem:
    """L2 记忆条目"""
    id: str
    vector: np.ndarray
    content: str
    tags: List[str]
    source_session: str
    access_count: int = 0
    last_access: float = 0
    created_at: float = 0
    
    def to_dict(self) -> Dict:
        """转换为字典（用于 JSON 序列化）"""
        return {
            "id": self.id,
            "vector": self.vector.tolist(),
            "content": self.content,
            "tags": self.tags,
            "source_session": self.source_session,
            "access_count": self.access_count,
            "last_access": self.last_access,
            "created_at": self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "L2MemoryItem":
        """从字典创建实例"""
        return cls(
            id=data["id"],
            vector=np.array(data["vector"], dtype=np.float32),
            content=data["content"],
            tags=data["tags"],
            source_session=data["source_session"],
            access_count=data["access_count"],
            last_access=data["last_access"],
            created_at=data["created_at"]
        )


class L2VectorMemory:
    """
    L2 情景经验记忆
    
    存储非结构化场景经验、用户偏好、历史交互。
    使用 FAISS 进行向量索引，SQLite 存储元数据。
    """
    
    def __init__(self, vector_dim: int = 768, index_type: str = "Flat",
                 index_path: str = "./data/l2_vectors/faiss.index",
                 metadata_path: str = "./data/l2_vectors/metadata.db",
                 similarity_threshold: float = 0.75):
        """
        初始化 L2 向量记忆
        
        Args:
            vector_dim: 向量维度
            index_type: FAISS 索引类型 (Flat, IVF, HNSW)
            index_path: FAISS 索引文件路径
            metadata_path: 元数据 SQLite 数据库路径
            similarity_threshold: 相似度阈值
        """
        if faiss is None:
            raise ImportError("FAISS is not installed. Run: pip install faiss-cpu")
        
        self.vector_dim = vector_dim
        self.index_type = index_type
        self.index_path = index_path
        self.metadata_path = metadata_path
        self.similarity_threshold = similarity_threshold
        
        # 确保目录存在
        os.makedirs(os.path.dirname(index_path), exist_ok=True)
        os.makedirs(os.path.dirname(metadata_path), exist_ok=True)
        
        # FAISS 索引
        self._index: Optional[faiss.Index] = None
        
        # 元数据存储（id -> L2MemoryItem）
        self._metadata: Dict[str, L2MemoryItem] = {}
        
        # ID 映射（FAISS 内部索引 -> 外部 ID）
        self._id_map: List[str] = []
        
        # 线程锁
        self._lock = threading.RLock()
        
        # 统计信息
        self._stats = {
            "total_vectors": 0,
            "total_writes": 0,
            "total_searches": 0,
            "total_evictions": 0
        }
        
        # 初始化
        self._init_index()
        self._init_metadata_db()
    
    def _init_index(self):
        """初始化 FAISS 索引"""
        if os.path.exists(self.index_path):
            # 加载已有索引
            self._index = faiss.read_index(self.index_path)
            # 加载 ID 映射
            id_map_path = self.index_path + ".ids"
            if os.path.exists(id_map_path):
                with open(id_map_path, "r") as f:
                    self._id_map = json.load(f)
        else:
            # 创建新索引
            if self.index_type == "Flat":
                self._index = faiss.IndexFlatIP(self.vector_dim)  # 内积（余弦相似度）
            elif self.index_type == "IVF":
                quantizer = faiss.IndexFlatIP(self.vector_dim)
                self._index = faiss.IndexIVFFlat(quantizer, self.vector_dim, 100)
                self._index.train(np.random.random((1000, self.vector_dim)).astype(np.float32))
            elif self.index_type == "HNSW":
                self._index = faiss.IndexHNSWFlat(self.vector_dim, 32)
            else:
                raise ValueError(f"Unknown index type: {self.index_type}")
    
    def _init_metadata_db(self):
        """初始化元数据数据库"""
        conn = sqlite3.connect(self.metadata_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                id TEXT PRIMARY KEY,
                content TEXT,
                tags TEXT,
                source_session TEXT,
                access_count INTEGER DEFAULT 0,
                last_access REAL,
                created_at REAL
            )
        """)
        conn.commit()
        conn.close()
        
        # 加载已有元数据
        self._load_metadata()
    
    def _load_metadata(self):
        """从 SQLite 加载元数据"""
        conn = sqlite3.connect(self.metadata_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM metadata")
        rows = cursor.fetchall()
        
        for row in rows:
            item = L2MemoryItem(
                id=row[0],
                vector=np.array([]),  # 向量存储在 FAISS 中
                content=row[1],
                tags=json.loads(row[2]) if row[2] else [],
                source_session=row[3],
                access_count=row[4],
                last_access=row[5],
                created_at=row[6]
            )
            self._metadata[item.id] = item
        
        conn.close()
        self._stats["total_vectors"] = len(self._metadata)
    
    def store(self, item_id: str, vector: np.ndarray, content: str,
              tags: List[str] = None, source_session: str = "") -> bool:
        """
        存储向量记忆
        
        Args:
            item_id: 条目ID
            vector: 向量（需已归一化）
            content: 原始内容
            tags: 标签列表
            source_session: 来源会话ID
            
        Returns:
            bool: 是否成功
        """
        if vector.shape[0] != self.vector_dim:
            raise ValueError(f"Vector dimension mismatch: {vector.shape[0]} != {self.vector_dim}")
        
        # 确保向量是 float32 类型
        vector = vector.astype(np.float32)
        
        with self._lock:
            # 添加到 FAISS 索引
            self._index.add(vector.reshape(1, -1))
            
            # 创建元数据
            item = L2MemoryItem(
                id=item_id,
                vector=vector,
                content=content,
                tags=tags or [],
                source_session=source_session,
                access_count=0,
                last_access=time.time(),
                created_at=time.time()
            )
            
            # 保存元数据
            self._metadata[item_id] = item
            self._id_map.append(item_id)
            
            # 持久化到 SQLite
            self._save_metadata(item)
            
            # 更新统计
            self._stats["total_vectors"] = len(self._metadata)
            self._stats["total_writes"] += 1
        
        return True
    
    def _save_metadata(self, item: L2MemoryItem):
        """保存元数据到 SQLite"""
        conn = sqlite3.connect(self.metadata_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO metadata 
            (id, content, tags, source_session, access_count, last_access, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            item.id, item.content, json.dumps(item.tags),
            item.source_session, item.access_count, item.last_access, item.created_at
        ))
        conn.commit()
        conn.close()
    
    def search(self, query_vector: np.ndarray, top_k: int = 10,
               min_score: float = None) -> List[Tuple[L2MemoryItem, float]]:
        """
        语义相似度搜索
        
        Args:
            query_vector: 查询向量（需已归一化）
            top_k: 返回结果数
            min_score: 最小相似度阈值
            
        Returns:
            List[Tuple[L2MemoryItem, float]]: (记忆条目, 相似度分数) 列表
        """
        if min_score is None:
            min_score = self.similarity_threshold
        
        if query_vector.shape[0] != self.vector_dim:
            raise ValueError(f"Query vector dimension mismatch: {query_vector.shape[0]} != {self.vector_dim}")
        
        query_vector = query_vector.astype(np.float32).reshape(1, -1)
        
        with self._lock:
            if self._index.ntotal == 0:
                return []
            
            # FAISS 搜索
            scores, indices = self._index.search(query_vector, min(top_k, self._index.ntotal))
            
            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx < 0 or idx >= len(self._id_map):
                    continue
                
                item_id = self._id_map[idx]
                item = self._metadata.get(item_id)
                
                if item is None:
                    continue
                
                # 过滤低相似度
                if score < min_score:
                    continue
                
                # 更新访问统计
                item.access_count += 1
                item.last_access = time.time()
                self._save_metadata(item)
                
                results.append((item, float(score)))
            
            self._stats["total_searches"] += 1
        
        return results
    
    def get(self, item_id: str) -> Optional[L2MemoryItem]:
        """
        获取指定条目
        
        Args:
            item_id: 条目ID
            
        Returns:
            Optional[L2MemoryItem]: 记忆条目
        """
        return self._metadata.get(item_id)
    
    def delete(self, item_id: str) -> bool:
        """
        删除条目
        
        Args:
            item_id: 条目ID
            
        Returns:
            bool: 是否成功
        """
        with self._lock:
            if item_id not in self._metadata:
                return False
            
            # 从元数据中删除
            del self._metadata[item_id]
            
            # 从 ID 映射中删除
            if item_id in self._id_map:
                self._id_map.remove(item_id)
            
            # 从 SQLite 中删除
            conn = sqlite3.connect(self.metadata_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM metadata WHERE id = ?", (item_id,))
            conn.commit()
            conn.close()
            
            # FAISS 不支持直接删除，需要重建索引
            self._rebuild_index()
            
            self._stats["total_evictions"] += 1
            self._stats["total_vectors"] = len(self._metadata)
        
        return True
    
    def _rebuild_index(self):
        """重建 FAISS 索引（用于删除后）"""
        # 创建新索引
        if self.index_type == "Flat":
            new_index = faiss.IndexFlatIP(self.vector_dim)
        elif self.index_type == "IVF":
            quantizer = faiss.IndexFlatIP(self.vector_dim)
            new_index = faiss.IndexIVFFlat(quantizer, self.vector_dim, 100)
        elif self.index_type == "HNSW":
            new_index = faiss.IndexHNSWFlat(self.vector_dim, 32)
        else:
            return
        
        # 重新添加所有向量
        if self._metadata:
            vectors = np.array([item.vector for item in self._metadata.values()], dtype=np.float32)
            if self.index_type == "IVF":
                new_index.train(vectors)
            new_index.add(vectors)
        
        self._index = new_index
        self._id_map = list(self._metadata.keys())
    
    def evict_expired(self, inactive_days: int = 90, min_access: int = 1) -> int:
        """
        清理过期数据（阶段 57：动态遗忘）
        
        Args:
            inactive_days: 不活跃天数阈值
            min_access: 最小访问次数
            
        Returns:
            int: 清理的条目数
        """
        current_time = time.time()
        threshold = current_time - (inactive_days * 24 * 3600)
        
        to_delete = []
        for item_id, item in self._metadata.items():
            if item.last_access < threshold and item.access_count < min_access:
                to_delete.append(item_id)
        
        for item_id in to_delete:
            self.delete(item_id)
        
        return len(to_delete)
    
    def save(self):
        """持久化索引到磁盘"""
        with self._lock:
            faiss.write_index(self._index, self.index_path)
            # 保存 ID 映射
            with open(self.index_path + ".ids", "w") as f:
                json.dump(self._id_map, f)
    
    def get_stats(self) -> Dict[str, int]:
        """
        获取统计信息
        
        Returns:
            Dict[str, int]: 统计信息
        """
        return self._stats.copy()
    
    def health_check(self) -> Dict[str, Any]:
        """
        健康检查
        
        Returns:
            Dict[str, Any]: 健康状态
        """
        return {
            "status": "healthy" if self._index is not None else "unhealthy",
            "total_vectors": self._stats["total_vectors"],
            "index_type": self.index_type,
            "vector_dim": self.vector_dim,
            "index_size_mb": round(os.path.getsize(self.index_path) / 1024 / 1024, 2) if os.path.exists(self.index_path) else 0
        }


# 全局单例实例
_l2_memory_instance: Optional[L2VectorMemory] = None


def get_l2_memory(config: Optional[Dict] = None) -> L2VectorMemory:
    """
    获取 L2 记忆全局实例（单例模式）
    
    Args:
        config: 配置字典
        
    Returns:
        L2VectorMemory: L2 记忆实例
    """
    global _l2_memory_instance
    if _l2_memory_instance is None:
        if config:
            _l2_memory_instance = L2VectorMemory(
                vector_dim=config.get("vector_dim", 768),
                index_type=config.get("index_type", "Flat"),
                index_path=config.get("index_path", "./data/l2_vectors/faiss.index"),
                metadata_path=config.get("metadata_path", "./data/l2_vectors/metadata.db"),
                similarity_threshold=config.get("similarity_threshold", 0.75)
            )
        else:
            _l2_memory_instance = L2VectorMemory()
    return _l2_memory_instance
