#!/usr/bin/env python3
"""
数据迁移模块 - 阶段110-112
记忆导入导出与跨实例迁移
"""

import json
import pickle
from typing import Dict, List, Any, Optional
from datetime import datetime


class MemoryExporter:
    """记忆导出器"""
    
    def export_to_json(self, memories: List[Dict[str, Any]], filepath: str) -> bool:
        """
        导出记忆到JSON文件
        
        Args:
            memories: 记忆列表
            filepath: 输出文件路径
        """
        try:
            data = {
                "version": "1.0",
                "exported_at": datetime.now().isoformat(),
                "count": len(memories),
                "memories": memories
            }
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"导出失败: {e}")
            return False
    
    def export_to_pickle(self, memories: List[Dict[str, Any]], filepath: str) -> bool:
        """导出记忆到Pickle文件（保留完整对象）"""
        try:
            data = {
                "version": "1.0",
                "exported_at": datetime.now().isoformat(),
                "memories": memories
            }
            with open(filepath, 'wb') as f:
                pickle.dump(data, f)
            return True
        except Exception as e:
            print(f"导出失败: {e}")
            return False


class MemoryImporter:
    """记忆导入器"""
    
    def import_from_json(self, filepath: str) -> Optional[List[Dict[str, Any]]]:
        """
        从JSON文件导入记忆
        
        Args:
            filepath: JSON文件路径
        
        Returns:
            记忆列表，失败返回None
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get("memories", [])
        except Exception as e:
            print(f"导入失败: {e}")
            return None
    
    def import_from_pickle(self, filepath: str) -> Optional[List[Dict[str, Any]]]:
        """从Pickle文件导入记忆"""
        try:
            with open(filepath, 'rb') as f:
                data = pickle.load(f)
            return data.get("memories", [])
        except Exception as e:
            print(f"导入失败: {e}")
            return None
    
    def validate_import(self, memories: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        验证导入数据的完整性
        
        Returns:
            验证结果字典
        """
        valid_count = 0
        invalid_count = 0
        errors = []
        
        for i, mem in enumerate(memories):
            if not isinstance(mem, dict):
                invalid_count += 1
                errors.append(f"第{i}项不是字典")
                continue
            
            if "content" not in mem:
                invalid_count += 1
                errors.append(f"第{i}项缺少content字段")
                continue
            
            valid_count += 1
        
        return {
            "valid": valid_count,
            "invalid": invalid_count,
            "total": len(memories),
            "errors": errors[:10]  # 只返回前10个错误
        }


class MigrationManager:
    """迁移管理器"""
    
    def __init__(self):
        self.exporter = MemoryExporter()
        self.importer = MemoryImporter()
    
    def migrate_task(
        self,
        source_system,
        target_system,
        task_id: str
    ) -> Dict[str, Any]:
        """
        迁移单个任务的记忆
        
        Args:
            source_system: 源记忆系统
            target_system: 目标记忆系统
            task_id: 任务标识
        
        Returns:
            迁移结果
        """
        # 从源系统召回该任务的所有记忆
        results = source_system.recall("", task_id=task_id, top_k=1000)
        
        migrated = 0
        failed = 0
        
        for mem in results:
            try:
                result = target_system.remember(
                    content=mem.get("content", ""),
                    task_id=task_id
                )
                if result["success"]:
                    migrated += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
        
        return {
            "migrated": migrated,
            "failed": failed,
            "total": len(results)
        }
