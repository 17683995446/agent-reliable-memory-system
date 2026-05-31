#!/usr/bin/env python3
"""
记忆时效性管理 - 阶段125-127
自动过期和定期清理
"""

import time
import threading
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class ExpirationRule:
    """过期规则"""
    memory_type: str  # "l1" | "l2" | "l3"
    ttl_seconds: int
    auto_extend: bool = False


class ExpirationManager:
    """
    过期管理器
    
    管理记忆的时效性，支持自动过期和清理
    """
    
    def __init__(self):
        self._expirations: Dict[str, float] = {}  # memory_id -> expire_timestamp
        self._rules: Dict[str, ExpirationRule] = {
            "l1": ExpirationRule("l1", 3600),      # 1小时
            "l2": ExpirationRule("l2", 86400 * 7), # 7天
            "l3": ExpirationRule("l3", 86400 * 30), # 30天
        }
        self._lock = threading.RLock()
        self._running = False
        self._cleanup_thread: Optional[threading.Thread] = None
    
    def set_expiration(
        self,
        memory_id: str,
        ttl_seconds: Optional[int] = None,
        memory_type: str = "l2"
    ):
        """
        设置记忆过期时间
        
        Args:
            memory_id: 记忆ID
            ttl_seconds: 生存时间（秒），None使用默认值
            memory_type: 记忆类型
        """
        with self._lock:
            if ttl_seconds is None:
                rule = self._rules.get(memory_type)
                ttl_seconds = rule.ttl_seconds if rule else 86400
            
            expire_at = time.time() + ttl_seconds
            self._expirations[memory_id] = expire_at
    
    def is_expired(self, memory_id: str) -> bool:
        """检查记忆是否已过期"""
        with self._lock:
            if memory_id not in self._expirations:
                return False
            return time.time() > self._expirations[memory_id]
    
    def get_remaining_time(self, memory_id: str) -> Optional[float]:
        """获取剩余时间（秒）"""
        with self._lock:
            if memory_id not in self._expirations:
                return None
            remaining = self._expirations[memory_id] - time.time()
            return max(0, remaining)
    
    def extend_expiration(self, memory_id: str, additional_seconds: int) -> bool:
        """延长过期时间"""
        with self._lock:
            if memory_id not in self._expirations:
                return False
            self._expirations[memory_id] += additional_seconds
            return True
    
    def remove_expiration(self, memory_id: str):
        """移除过期设置"""
        with self._lock:
            if memory_id in self._expirations:
                del self._expirations[memory_id]
    
    def get_expired_memories(self) -> List[str]:
        """获取所有已过期记忆的ID列表"""
        with self._lock:
            now = time.time()
            return [
                mem_id for mem_id, expire_at in self._expirations.items()
                if now > expire_at
            ]
    
    def start_auto_cleanup(self, interval_seconds: int = 3600):
        """
        启动自动清理线程
        
        Args:
            interval_seconds: 清理间隔（秒）
        """
        if self._running:
            return
        
        self._running = True
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            args=(interval_seconds,),
            daemon=True
        )
        self._cleanup_thread.start()
        print(f"[过期管理] 自动清理已启动，间隔: {interval_seconds}秒")
    
    def stop_auto_cleanup(self):
        """停止自动清理"""
        self._running = False
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=5)
        print("[过期管理] 自动清理已停止")
    
    def _cleanup_loop(self, interval_seconds: int):
        """清理循环"""
        while self._running:
            time.sleep(interval_seconds)
            if not self._running:
                break
            
            expired = self.get_expired_memories()
            if expired:
                print(f"[过期管理] 发现 {len(expired)} 条过期记忆")
                # 这里可以调用删除逻辑
                for mem_id in expired:
                    self.remove_expiration(mem_id)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取过期管理统计"""
        with self._lock:
            total = len(self._expirations)
            expired = len(self.get_expired_memories())
            return {
                "total_tracked": total,
                "expired": expired,
                "active": total - expired,
            }
