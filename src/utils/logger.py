"""
日志模块
阶段 34-35：设计全局日志体系，记录读写、召回、治理行为

核心特性：
- 结构化日志输出
- 文件轮转
- 性能统计
"""

import logging
import logging.handlers
import os
import json
import time
from typing import Dict, Any, Optional
from datetime import datetime


class MemoryLogger:
    """记忆系统日志器"""
    
    def __init__(self, name: str = "agent_memory", level: str = "INFO",
                 log_file: str = "./data/logs/agent_memory.log",
                 max_bytes: int = 10*1024*1024, backup_count: int = 5):
        """
        初始化日志器
        
        Args:
            name: 日志器名称
            level: 日志级别
            log_file: 日志文件路径
            max_bytes: 单个日志文件最大字节数
            backup_count: 备份文件数量
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, level.upper()))
        
        # 避免重复添加处理器
        if self.logger.handlers:
            return
        
        # 确保目录存在
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        # 文件处理器（带轮转）
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        
        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # 格式化器
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
    
    def log_memory_operation(self, operation: str, layer: str, 
                            session_id: str, details: Dict[str, Any]):
        """
        记录记忆操作日志
        
        Args:
            operation: 操作类型 (write/read/recall/govern)
            layer: 记忆层级 (L1/L2/L3)
            session_id: 会话ID
            details: 详细信息
        """
        log_entry = {
            "timestamp": time.time(),
            "operation": operation,
            "layer": layer,
            "session_id": session_id,
            "details": details
        }
        self.logger.info(f"[MEMORY] {json.dumps(log_entry, ensure_ascii=False)}")
    
    def log_recall(self, session_id: str, query: str, 
                   results_count: int, latency_ms: float):
        """
        记录召回操作
        
        Args:
            session_id: 会话ID
            query: 查询内容
            results_count: 返回结果数
            latency_ms: 延迟（毫秒）
        """
        self.logger.info(
            f"[RECALL] session={session_id}, query={query[:50]}..., "
            f"results={results_count}, latency={latency_ms:.2f}ms"
        )
    
    def log_governance(self, action: str, details: Dict[str, Any]):
        """
        记录治理操作
        
        Args:
            action: 治理动作 (evict/update/poison_detect)
            details: 详细信息
        """
        self.logger.info(f"[GOVERN] action={action}, details={details}")
    
    def log_error(self, error_type: str, message: str, 
                  session_id: str = None, exception: Exception = None):
        """
        记录错误
        
        Args:
            error_type: 错误类型
            message: 错误消息
            session_id: 会话ID
            exception: 异常对象
        """
        extra = {"session_id": session_id} if session_id else {}
        if exception:
            self.logger.exception(f"[ERROR] type={error_type}, msg={message}")
        else:
            self.logger.error(f"[ERROR] type={error_type}, msg={message}", extra=extra)


# 全局日志实例
_logger_instance: Optional[MemoryLogger] = None


def get_logger(config: Optional[Dict] = None) -> MemoryLogger:
    """
    获取全局日志实例
    
    Args:
        config: 配置字典
        
    Returns:
        MemoryLogger: 日志实例
    """
    global _logger_instance
    if _logger_instance is None:
        if config:
            _logger_instance = MemoryLogger(
                level=config.get("level", "INFO"),
                log_file=config.get("file", "./data/logs/agent_memory.log"),
                max_bytes=config.get("max_bytes", 10*1024*1024),
                backup_count=config.get("backup_count", 5)
            )
        else:
            _logger_instance = MemoryLogger()
    return _logger_instance
