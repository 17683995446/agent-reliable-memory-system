"""
版本管理模块
阶段 63：搭建记忆版本管理体系，支持历史数据回溯

核心特性：
- L3 事实记忆版本快照管理
- 支持历史版本回溯
- 支持版本对比
"""

import time
import json
import sqlite3
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class VersionSnapshot:
    """版本快照"""
    snapshot_id: str
    triple_hash: str
    subject: str
    predicate: str
    old_value: str
    new_value: str
    updated_at: float
    updated_by: str
    change_type: str  # CREATE / UPDATE / DELETE


class VersionManager:
    """
    版本管理器
    
    管理 L3 事实记忆的版本历史，支持回溯和对比。
    """
    
    def __init__(self, sqlite_path: str = "./data/l3_graph/config.db"):
        self.sqlite_path = sqlite_path
        self._init_tables()
    
    def _init_tables(self):
        """初始化版本表"""
        conn = sqlite3.connect(self.sqlite_path)
        cursor = conn.cursor()
        
        # 版本快照表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS version_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                triple_hash TEXT,
                subject TEXT,
                predicate TEXT,
                old_value TEXT,
                new_value TEXT,
                change_type TEXT,
                updated_at REAL,
                updated_by TEXT
            )
        """)
        
        # 创建索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_triple_hash ON version_snapshots(triple_hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_updated_at ON version_snapshots(updated_at)")
        
        conn.commit()
        conn.close()
    
    def create_snapshot(self, subject: str, predicate: str,
                       old_value: str, new_value: str,
                       change_type: str = "UPDATE",
                       updated_by: str = "system") -> str:
        """
        创建版本快照
        
        Args:
            subject: 主语
            predicate: 谓语
            old_value: 旧值
            new_value: 新值
            change_type: 变更类型
            updated_by: 更新者
            
        Returns:
            str: 快照ID
        """
        snapshot_id = f"snap_{int(time.time() * 1000)}_{hash(subject + predicate) % 10000}"
        triple_hash = f"{subject}:{predicate}"
        
        conn = sqlite3.connect(self.sqlite_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO version_snapshots
            (snapshot_id, triple_hash, subject, predicate, old_value, new_value,
             change_type, updated_at, updated_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (snapshot_id, triple_hash, subject, predicate, old_value, new_value,
              change_type, time.time(), updated_by))
        
        conn.commit()
        conn.close()
        
        return snapshot_id
    
    def get_version_history(self, subject: str, predicate: str,
                           limit: int = 10) -> List[VersionSnapshot]:
        """
        获取版本历史
        
        Args:
            subject: 主语
            predicate: 谓语
            limit: 返回条数
            
        Returns:
            List[VersionSnapshot]: 版本历史列表
        """
        triple_hash = f"{subject}:{predicate}"
        
        conn = sqlite3.connect(self.sqlite_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT snapshot_id, triple_hash, subject, predicate,
                   old_value, new_value, updated_at, updated_by, change_type
            FROM version_snapshots
            WHERE triple_hash = ?
            ORDER BY updated_at DESC
            LIMIT ?
        """, (triple_hash, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            VersionSnapshot(
                snapshot_id=row[0],
                triple_hash=row[1],
                subject=row[2],
                predicate=row[3],
                old_value=row[4],
                new_value=row[5],
                updated_at=row[6],
                updated_by=row[7],
                change_type=row[8]
            )
            for row in rows
        ]
    
    def get_version_at_time(self, subject: str, predicate: str,
                           timestamp: float) -> Optional[str]:
        """
        获取指定时间点的版本值
        
        Args:
            subject: 主语
            predicate: 谓语
            timestamp: 时间点
            
        Returns:
            Optional[str]: 该时间点的值
        """
        triple_hash = f"{subject}:{predicate}"
        
        conn = sqlite3.connect(self.sqlite_path)
        cursor = conn.cursor()
        
        # 找到最接近但不超过指定时间的版本
        cursor.execute("""
            SELECT new_value
            FROM version_snapshots
            WHERE triple_hash = ? AND updated_at <= ?
            ORDER BY updated_at DESC
            LIMIT 1
        """, (triple_hash, timestamp))
        
        row = cursor.fetchone()
        conn.close()
        
        return row[0] if row else None
    
    def compare_versions(self, subject: str, predicate: str,
                        timestamp1: float, timestamp2: float) -> Dict[str, Any]:
        """
        对比两个时间点的版本
        
        Args:
            subject: 主语
            predicate: 谓语
            timestamp1: 时间点1
            timestamp2: 时间点2
            
        Returns:
            Dict: 对比结果
        """
        value1 = self.get_version_at_time(subject, predicate, timestamp1)
        value2 = self.get_version_at_time(subject, predicate, timestamp2)
        
        return {
            "subject": subject,
            "predicate": predicate,
            "timestamp1": timestamp1,
            "timestamp2": timestamp2,
            "value1": value1,
            "value2": value2,
            "changed": value1 != value2
        }
    
    def rollback_to_version(self, subject: str, predicate: str,
                           target_timestamp: float) -> Optional[str]:
        """
        回滚到指定时间点的版本
        
        Args:
            subject: 主语
            predicate: 谓语
            target_timestamp: 目标时间点
            
        Returns:
            Optional[str]: 回滚后的值
        """
        old_value = self.get_version_at_time(subject, predicate, time.time())
        target_value = self.get_version_at_time(subject, predicate, target_timestamp)
        
        if target_value is None:
            return None
        
        # 创建回滚快照
        self.create_snapshot(
            subject=subject,
            predicate=predicate,
            old_value=old_value or "",
            new_value=target_value,
            change_type="ROLLBACK",
            updated_by="rollback_operation"
        )
        
        return target_value
    
    def get_stats(self) -> Dict[str, int]:
        """获取版本统计"""
        conn = sqlite3.connect(self.sqlite_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM version_snapshots")
        total = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT triple_hash) FROM version_snapshots")
        unique_triples = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "total_snapshots": total,
            "unique_triples": unique_triples
        }
