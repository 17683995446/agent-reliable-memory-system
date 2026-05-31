"""
L3 永久事实记忆模块
阶段 28-29：部署Neo4j图数据库，搭建SQLite结构化数据库
阶段 48：开发L3三元组解析、实体关系入库逻辑
阶段 50：开发L3图谱精准关键词检索功能
阶段 58：编写事实冲突更新逻辑，留存数据版本快照

核心特性：
- Neo4j 图数据库存储实体关系
- SQLite 存储版本快照和配置
- 三元组（实体-属性-关系）标准格式
"""

import os
import json
import time
import sqlite3
import threading
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, asdict
from datetime import datetime

try:
    from neo4j import GraphDatabase, Driver, Session
except ImportError:
    GraphDatabase = None
    Driver = None
    Session = None


@dataclass
class Triple:
    """三元组：实体-关系-实体 / 实体-属性-值"""
    subject: str      # 主语/实体
    predicate: str    # 谓语/关系或属性
    object: str       # 宾语/实体或值
    is_attribute: bool = False  # True=属性, False=关系
    confidence: float = 1.0     # 置信度
    source: str = ""            # 来源
    created_at: float = 0
    
    def __post_init__(self):
        if self.created_at == 0:
            self.created_at = time.time()
    
    def to_dict(self) -> Dict:
        return {
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "is_attribute": self.is_attribute,
            "confidence": self.confidence,
            "source": self.source,
            "created_at": self.created_at
        }


@dataclass
class Entity:
    """实体"""
    name: str
    entity_type: str
    attributes: Dict[str, str] = None
    
    def __post_init__(self):
        if self.attributes is None:
            self.attributes = {}


class L3FactMemory:
    """
    L3 永久事实记忆
    
    存储结构化规则、实体关系、固定事实。
    使用 Neo4j 存储图谱，SQLite 存储版本快照。
    """
    
    def __init__(self, neo4j_uri: str = "bolt://localhost:7687",
                 neo4j_user: str = "neo4j",
                 neo4j_password: str = "password",
                 neo4j_database: str = "agent_memory",
                 sqlite_path: str = "./data/l3_graph/config.db"):
        """
        初始化 L3 事实记忆
        
        Args:
            neo4j_uri: Neo4j 连接 URI
            neo4j_user: Neo4j 用户名
            neo4j_password: Neo4j 密码
            neo4j_database: Neo4j 数据库名
            sqlite_path: SQLite 数据库路径
        """
        if GraphDatabase is None:
            raise ImportError("Neo4j driver is not installed. Run: pip install neo4j")
        
        self.neo4j_uri = neo4j_uri
        self.neo4j_user = neo4j_user
        self.neo4j_password = neo4j_password
        self.neo4j_database = neo4j_database
        self.sqlite_path = sqlite_path
        
        # 确保目录存在
        os.makedirs(os.path.dirname(sqlite_path), exist_ok=True)
        
        # Neo4j 驱动
        self._driver: Optional[Driver] = None
        
        # 线程锁
        self._lock = threading.RLock()
        
        # 统计信息
        self._stats = {
            "total_entities": 0,
            "total_relations": 0,
            "total_triples": 0,
            "total_writes": 0,
            "total_reads": 0,
            "total_updates": 0
        }
        
        # 初始化
        self._init_neo4j()
        self._init_sqlite()
    
    def _init_neo4j(self):
        """初始化 Neo4j 连接"""
        try:
            self._driver = GraphDatabase.driver(
                self.neo4j_uri,
                auth=(self.neo4j_user, self.neo4j_password)
            )
            # 测试连接
            with self._driver.session() as session:
                session.run("RETURN 1")
        except Exception as e:
            print(f"Warning: Neo4j connection failed: {e}")
            self._driver = None
    
    def _init_sqlite(self):
        """初始化 SQLite 数据库"""
        conn = sqlite3.connect(self.sqlite_path)
        cursor = conn.cursor()
        
        # 版本快照表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS version_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                triple_hash TEXT,
                subject TEXT,
                predicate TEXT,
                object TEXT,
                old_value TEXT,
                new_value TEXT,
                updated_at REAL,
                updated_by TEXT
            )
        """)
        
        # 配置表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at REAL
            )
        """)
        
        conn.commit()
        conn.close()
    
    def store_triple(self, triple: Triple, create_snapshot: bool = True) -> bool:
        """
        存储三元组
        
        Args:
            triple: 三元组
            create_snapshot: 是否创建版本快照
            
        Returns:
            bool: 是否成功
        """
        if self._driver is None:
            return False
        
        with self._lock:
            # 检查冲突（阶段 58：冲突更新）
            existing = self._get_existing_triple(triple.subject, triple.predicate)
            
            if existing and create_snapshot:
                # 创建版本快照
                self._create_snapshot(triple.subject, triple.predicate, 
                                     existing.object, triple.object)
                self._stats["total_updates"] += 1
            
            # 写入 Neo4j
            with self._driver.session() as session:
                if triple.is_attribute:
                    # 属性：MERGE 实体，SET 属性
                    session.run("""
                        MERGE (e:Entity {name: $subject})
                        SET e[$predicate] = $object,
                            e.updated_at = $timestamp
                    """, {
                        "subject": triple.subject,
                        "predicate": triple.predicate,
                        "object": triple.object,
                        "timestamp": triple.created_at
                    })
                else:
                    # 关系：MERGE 两个实体，CREATE 关系
                    session.run("""
                        MERGE (s:Entity {name: $subject})
                        MERGE (o:Entity {name: $object})
                        MERGE (s)-[r:$predicate]->(o)
                        SET r.updated_at = $timestamp
                    """.replace("$predicate", triple.predicate), {
                        "subject": triple.subject,
                        "object": triple.object,
                        "timestamp": triple.created_at
                    })
            
            self._stats["total_writes"] += 1
            self._update_stats()
        
        return True
    
    def store_triples(self, triples: List[Triple]) -> int:
        """
        批量存储三元组
        
        Args:
            triples: 三元组列表
            
        Returns:
            int: 成功存储的数量
        """
        count = 0
        for triple in triples:
            if self.store_triple(triple):
                count += 1
        return count
    
    def _get_existing_triple(self, subject: str, predicate: str) -> Optional[Triple]:
        """获取已存在的三元组"""
        if self._driver is None:
            return None
        
        with self._driver.session() as session:
            # 尝试作为属性查询
            result = session.run("""
                MATCH (e:Entity {name: $subject})
                RETURN e[$predicate] as value
            """, {"subject": subject, "predicate": predicate})
            
            record = result.single()
            if record and record["value"]:
                return Triple(
                    subject=subject,
                    predicate=predicate,
                    object=record["value"],
                    is_attribute=True
                )
            
            # 尝试作为关系查询
            result = session.run("""
                MATCH (s:Entity {name: $subject})-[r:$predicate]->(o)
                RETURN o.name as object
            """.replace("$predicate", predicate), {"subject": subject})
            
            record = result.single()
            if record and record["object"]:
                return Triple(
                    subject=subject,
                    predicate=predicate,
                    object=record["object"],
                    is_attribute=False
                )
        
        return None
    
    def _create_snapshot(self, subject: str, predicate: str, 
                        old_value: str, new_value: str):
        """创建版本快照"""
        conn = sqlite3.connect(self.sqlite_path)
        cursor = conn.cursor()
        
        triple_hash = f"{subject}:{predicate}"
        cursor.execute("""
            INSERT INTO version_snapshots 
            (triple_hash, subject, predicate, old_value, new_value, updated_at, updated_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (triple_hash, subject, predicate, old_value, new_value, time.time(), "system"))
        
        conn.commit()
        conn.close()
    
    def query_by_entity(self, entity_name: str) -> List[Triple]:
        """
        按实体查询所有相关三元组
        
        Args:
            entity_name: 实体名称
            
        Returns:
            List[Triple]: 三元组列表
        """
        if self._driver is None:
            return []
        
        triples = []
        
        with self._driver.session() as session:
            # 查询作为主体的属性
            result = session.run("""
                MATCH (e:Entity {name: $name})
                RETURN keys(e) as attrs, e
            """, {"name": entity_name})
            
            record = result.single()
            if record:
                attrs = record["attrs"]
                entity = record["e"]
                for attr in attrs:
                    if attr not in ["name", "updated_at"]:
                        triples.append(Triple(
                            subject=entity_name,
                            predicate=attr,
                            object=str(entity[attr]),
                            is_attribute=True
                        ))
            
            # 查询作为主体的关系
            result = session.run("""
                MATCH (s:Entity {name: $name})-[r]->(o)
                RETURN type(r) as rel_type, o.name as object
            """, {"name": entity_name})
            
            for record in result:
                triples.append(Triple(
                    subject=entity_name,
                    predicate=record["rel_type"],
                    object=record["object"],
                    is_attribute=False
                ))
            
            # 查询作为客体的关系
            result = session.run("""
                MATCH (s)-[r]->(o:Entity {name: $name})
                RETURN type(r) as rel_type, s.name as subject
            """, {"name": entity_name})
            
            for record in result:
                triples.append(Triple(
                    subject=record["subject"],
                    predicate=record["rel_type"],
                    object=entity_name,
                    is_attribute=False
                ))
        
        self._stats["total_reads"] += 1
        return triples
    
    def query_by_relation(self, subject: str, predicate: str) -> Optional[str]:
        """
        按关系查询
        
        Args:
            subject: 主体实体
            predicate: 关系/属性名
            
        Returns:
            Optional[str]: 客体/属性值
        """
        if self._driver is None:
            return None
        
        with self._driver.session() as session:
            # 先尝试作为属性
            result = session.run("""
                MATCH (e:Entity {name: $subject})
                RETURN e[$predicate] as value
            """, {"subject": subject, "predicate": predicate})
            
            record = result.single()
            if record and record["value"]:
                self._stats["total_reads"] += 1
                return str(record["value"])
            
            # 再尝试作为关系
            result = session.run("""
                MATCH (s:Entity {name: $subject})-[r:$predicate]->(o)
                RETURN o.name as object
            """.replace("$predicate", predicate), {"subject": subject})
            
            record = result.single()
            if record and record["object"]:
                self._stats["total_reads"] += 1
                return record["object"]
        
        return None
    
    def search_entities(self, keyword: str) -> List[str]:
        """
        搜索实体（模糊匹配）
        
        Args:
            keyword: 关键词
            
        Returns:
            List[str]: 实体名称列表
        """
        if self._driver is None:
            return []
        
        with self._driver.session() as session:
            result = session.run("""
                MATCH (e:Entity)
                WHERE e.name CONTAINS $keyword
                RETURN e.name as name
                LIMIT 20
            """, {"keyword": keyword})
            
            return [record["name"] for record in result]
    
    def get_version_history(self, subject: str, predicate: str, 
                           limit: int = 10) -> List[Dict]:
        """
        获取版本历史
        
        Args:
            subject: 主体
            predicate: 谓语
            limit: 返回条数
            
        Returns:
            List[Dict]: 版本历史
        """
        conn = sqlite3.connect(self.sqlite_path)
        cursor = conn.cursor()
        
        triple_hash = f"{subject}:{predicate}"
        cursor.execute("""
            SELECT old_value, new_value, updated_at, updated_by
            FROM version_snapshots
            WHERE triple_hash = ?
            ORDER BY updated_at DESC
            LIMIT ?
        """, (triple_hash, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                "old_value": row[0],
                "new_value": row[1],
                "updated_at": row[2],
                "updated_by": row[3]
            }
            for row in rows
        ]
    
    def _update_stats(self):
        """更新统计信息"""
        if self._driver is None:
            return
        
        with self._driver.session() as session:
            # 实体数
            result = session.run("MATCH (e:Entity) RETURN count(e) as cnt")
            self._stats["total_entities"] = result.single()["cnt"]
            
            # 关系数
            result = session.run("MATCH ()-[r]->() RETURN count(r) as cnt")
            self._stats["total_relations"] = result.single()["cnt"]
    
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
        status = "healthy"
        neo4j_connected = False
        
        if self._driver:
            try:
                with self._driver.session() as session:
                    session.run("RETURN 1")
                neo4j_connected = True
            except:
                status = "degraded"
        else:
            status = "unhealthy"
        
        return {
            "status": status,
            "neo4j_connected": neo4j_connected,
            "total_entities": self._stats["total_entities"],
            "total_relations": self._stats["total_relations"]
        }
    
    def close(self):
        """关闭连接"""
        if self._driver:
            self._driver.close()


# 全局单例实例
_l3_memory_instance: Optional[L3FactMemory] = None


def get_l3_memory(config: Optional[Dict] = None) -> L3FactMemory:
    """
    获取 L3 记忆全局实例（单例模式）
    
    Args:
        config: 配置字典
        
    Returns:
        L3FactMemory: L3 记忆实例
    """
    global _l3_memory_instance
    if _l3_memory_instance is None:
        if config:
            _l3_memory_instance = L3FactMemory(
                neo4j_uri=config.get("uri", "bolt://localhost:7687"),
                neo4j_user=config.get("user", "neo4j"),
                neo4j_password=config.get("password", "password"),
                neo4j_database=config.get("database", "agent_memory"),
                sqlite_path=config.get("db_path", "./data/l3_graph/config.db")
            )
        else:
            _l3_memory_instance = L3FactMemory()
    return _l3_memory_instance
