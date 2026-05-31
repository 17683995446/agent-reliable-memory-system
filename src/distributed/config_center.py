"""
配置中心 (ConfigCenter)
阶段248-250: 动态配置、版本管理、灰度发布

基于第一性原则设计:
1. 确定性: 配置变更基于版本控制，可追踪
2. 可靠性: 配置校验和回滚机制
3. 灵活性: 灰度发布支持逐步 rollout
"""

import threading
import time
import hashlib
import json
from typing import Dict, List, Optional, Any, Callable, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict


class ConfigValueType(Enum):
    """配置值类型"""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    JSON = "json"
    LIST = "list"


class ConfigStatus(Enum):
    """配置状态"""
    DRAFT = "draft"           # 草稿
    ACTIVE = "active"         # 生效
    DEPRECATED = "deprecated" # 废弃
    ROLLED_BACK = "rolled_back" # 已回滚


class RolloutStrategy(Enum):
    """灰度发布策略"""
    ALL = "all"               # 全量发布
    PERCENTAGE = "percentage" # 百分比
    CANARY = "canary"         # 金丝雀
    USER_ID = "user_id"       # 按用户ID
    IP_RANGE = "ip_range"     # 按IP范围


@dataclass
class ConfigValue:
    """配置值"""
    key: str
    value: Any
    value_type: ConfigValueType
    description: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class ConfigVersion:
    """配置版本"""
    version_id: str
    config_key: str
    value: Any
    value_type: ConfigValueType
    status: ConfigStatus
    created_by: str
    created_at: float = field(default_factory=time.time)
    change_log: str = ""
    parent_version: Optional[str] = None


@dataclass
class RolloutRule:
    """灰度规则"""
    rule_id: str
    config_key: str
    strategy: RolloutStrategy
    target_value: Any  # 目标配置值
    params: Dict[str, Any] = field(default_factory=dict)  # 策略参数
    enabled: bool = True
    created_at: float = field(default_factory=time.time)


@dataclass
class RolloutStatus:
    """灰度发布状态"""
    config_key: str
    current_version: str
    target_version: str
    progress: float  # 0-100
    status: str  # "in_progress", "completed", "paused", "rolled_back"
    affected_targets: int = 0
    total_targets: int = 0


class ConfigCenter:
    """
    配置中心
    
    核心功能:
    1. 动态配置: 运行时配置更新和推送
    2. 版本管理: 配置版本控制和历史回溯
    3. 灰度发布: 渐进式配置发布和回滚
    """
    
    def __init__(self):
        self._lock = threading.RLock()
        
        # 配置存储
        self._configs: Dict[str, ConfigValue] = {}
        self._config_versions: Dict[str, List[ConfigVersion]] = defaultdict(list)
        self._max_versions_per_key = 50
        
        # 灰度发布
        self._rollout_rules: Dict[str, List[RolloutRule]] = defaultdict(list)
        self._rollout_status: Dict[str, RolloutStatus] = {}
        
        # 变更监听
        self._change_callbacks: Dict[str, List[Callable[[str, Any, Any], None]]] = defaultdict(list)
        self._global_callbacks: List[Callable[[str, Any, Any], None]] = []
        
        # 配置校验器
        self._validators: Dict[str, Callable[[Any], Tuple[bool, str]]] = {}
        
        # 运行时状态
        self._client_targets: Dict[str, Dict[str, Any]] = {}  # client_id -> target_attributes
    
    # ==================== 阶段248: 动态配置 ====================
    
    def set_config(self, key: str, value: Any,
                   value_type: ConfigValueType = ConfigValueType.STRING,
                   description: str = "",
                   created_by: str = "system") -> bool:
        """
        设置配置值
        
        Args:
            key: 配置键
            value: 配置值
            value_type: 值类型
            description: 描述
            created_by: 创建者
            
        Returns:
            是否设置成功
        """
        with self._lock:
            # 校验值
            if key in self._validators:
                is_valid, error_msg = self._validators[key](value)
                if not is_valid:
                    return False
            
            old_value = None
            if key in self._configs:
                old_value = self._configs[key].value
            
            # 创建新版本
            version = ConfigVersion(
                version_id=self._generate_version_id(),
                config_key=key,
                value=value,
                value_type=value_type,
                status=ConfigStatus.ACTIVE,
                created_by=created_by,
                change_log=f"Set config value"
            )
            
            # 更新配置
            self._configs[key] = ConfigValue(
                key=key,
                value=value,
                value_type=value_type,
                description=description
            )
            
            # 保存版本
            self._config_versions[key].append(version)
            if len(self._config_versions[key]) > self._max_versions_per_key:
                self._config_versions[key] = self._config_versions[key][-self._max_versions_per_key:]
            
            # 触发回调
            self._notify_change(key, old_value, value)
            
            return True
    
    def get_config(self, key: str, default: Any = None,
                   client_id: Optional[str] = None) -> Any:
        """
        获取配置值
        
        Args:
            key: 配置键
            default: 默认值
            client_id: 客户端ID(用于灰度发布)
            
        Returns:
            配置值
        """
        with self._lock:
            # 检查灰度规则
            if client_id and key in self._rollout_rules:
                rollout_value = self._get_rollout_value(key, client_id)
                if rollout_value is not None:
                    return rollout_value
            
            if key in self._configs:
                return self._configs[key].value
            
            return default
    
    def get_config_object(self, key: str) -> Optional[ConfigValue]:
        """
        获取配置对象
        
        Args:
            key: 配置键
            
        Returns:
            配置对象
        """
        with self._lock:
            return self._configs.get(key)
    
    def delete_config(self, key: str, created_by: str = "system") -> bool:
        """
        删除配置
        
        Args:
            key: 配置键
            created_by: 删除者
            
        Returns:
            是否删除成功
        """
        with self._lock:
            if key not in self._configs:
                return False
            
            old_value = self._configs[key].value
            
            # 创建废弃版本
            version = ConfigVersion(
                version_id=self._generate_version_id(),
                config_key=key,
                value=None,
                value_type=ConfigValueType.STRING,
                status=ConfigStatus.DEPRECATED,
                created_by=created_by,
                change_log="Config deleted"
            )
            
            self._config_versions[key].append(version)
            
            del self._configs[key]
            
            # 触发回调
            self._notify_change(key, old_value, None)
            
            return True
    
    def list_configs(self, prefix: Optional[str] = None) -> List[str]:
        """
        列出配置键
        
        Args:
            prefix: 键前缀过滤
            
        Returns:
            配置键列表
        """
        with self._lock:
            keys = list(self._configs.keys())
            if prefix:
                keys = [k for k in keys if k.startswith(prefix)]
            return keys
    
    def register_validator(self, key: str,
                          validator: Callable[[Any], Tuple[bool, str]]) -> None:
        """
        注册配置校验器
        
        Args:
            key: 配置键
            validator: 校验函数，返回(是否通过, 错误信息)
        """
        with self._lock:
            self._validators[key] = validator
    
    def _generate_version_id(self) -> str:
        """生成版本ID"""
        timestamp = str(time.time())
        return hashlib.md5(timestamp.encode()).hexdigest()[:16]
    
    def _notify_change(self, key: str, old_value: Any, new_value: Any) -> None:
        """通知配置变更"""
        # 特定键回调
        for callback in self._change_callbacks.get(key, []):
            try:
                callback(key, old_value, new_value)
            except Exception:
                pass
        
        # 全局回调
        for callback in self._global_callbacks:
            try:
                callback(key, old_value, new_value)
            except Exception:
                pass
    
    def register_change_callback(self, key: str,
                                 callback: Callable[[str, Any, Any], None]) -> None:
        """
        注册配置变更回调
        
        Args:
            key: 配置键
            callback: 回调函数(key, old_value, new_value)
        """
        with self._lock:
            self._change_callbacks[key].append(callback)
    
    def register_global_callback(self,
                                 callback: Callable[[str, Any, Any], None]) -> None:
        """
        注册全局配置变更回调
        
        Args:
            callback: 回调函数(key, old_value, new_value)
        """
        with self._lock:
            self._global_callbacks.append(callback)
    
    # ==================== 阶段249: 版本管理 ====================
    
    def get_version_history(self, key: str,
                           limit: int = 20) -> List[ConfigVersion]:
        """
        获取版本历史
        
        Args:
            key: 配置键
            limit: 返回数量限制
            
        Returns:
            版本列表
        """
        with self._lock:
            versions = self._config_versions.get(key, [])
            return versions[-limit:]
    
    def rollback(self, key: str, version_id: str,
                created_by: str = "system") -> bool:
        """
        回滚到指定版本
        
        Args:
            key: 配置键
            version_id: 目标版本ID
            created_by: 操作者
            
        Returns:
            是否回滚成功
        """
        with self._lock:
            versions = self._config_versions.get(key, [])
            target_version = None
            
            for v in versions:
                if v.version_id == version_id:
                    target_version = v
                    break
            
            if not target_version:
                return False
            
            old_value = self._configs.get(key).value if key in self._configs else None
            
            # 创建回滚版本
            rollback_version = ConfigVersion(
                version_id=self._generate_version_id(),
                config_key=key,
                value=target_version.value,
                value_type=target_version.value_type,
                status=ConfigStatus.ROLLED_BACK,
                created_by=created_by,
                change_log=f"Rolled back to version {version_id}",
                parent_version=version_id
            )
            
            # 恢复配置
            self._configs[key] = ConfigValue(
                key=key,
                value=target_version.value,
                value_type=target_version.value_type
            )
            
            self._config_versions[key].append(rollback_version)
            
            # 触发回调
            self._notify_change(key, old_value, target_version.value)
            
            return True
    
    def compare_versions(self, key: str, version_id1: str,
                        version_id2: str) -> Optional[Dict[str, Any]]:
        """
        比较两个版本
        
        Args:
            key: 配置键
            version_id1: 版本1 ID
            version_id2: 版本2 ID
            
        Returns:
            比较结果
        """
        with self._lock:
            versions = self._config_versions.get(key, [])
            v1 = None
            v2 = None
            
            for v in versions:
                if v.version_id == version_id1:
                    v1 = v
                if v.version_id == version_id2:
                    v2 = v
            
            if not v1 or not v2:
                return None
            
            return {
                "version1": {
                    "id": v1.version_id,
                    "value": v1.value,
                    "created_at": v1.created_at,
                    "created_by": v1.created_by
                },
                "version2": {
                    "id": v2.version_id,
                    "value": v2.value,
                    "created_at": v2.created_at,
                    "created_by": v2.created_by
                },
                "is_different": v1.value != v2.value
            }
    
    def get_current_version(self, key: str) -> Optional[ConfigVersion]:
        """
        获取当前版本
        
        Args:
            key: 配置键
            
        Returns:
            当前版本
        """
        with self._lock:
            versions = self._config_versions.get(key, [])
            for v in reversed(versions):
                if v.status == ConfigStatus.ACTIVE:
                    return v
            return None
    
    # ==================== 阶段250: 灰度发布 ====================
    
    def create_rollout_rule(self, config_key: str,
                          strategy: RolloutStrategy,
                          target_value: Any,
                          params: Optional[Dict[str, Any]] = None) -> str:
        """
        创建灰度发布规则
        
        Args:
            config_key: 配置键
            strategy: 发布策略
            target_value: 目标配置值
            params: 策略参数
            
        Returns:
            规则ID
        """
        with self._lock:
            rule_id = f"rollout_{config_key}_{int(time.time())}"
            
            rule = RolloutRule(
                rule_id=rule_id,
                config_key=config_key,
                strategy=strategy,
                target_value=target_value,
                params=params or {}
            )
            
            self._rollout_rules[config_key].append(rule)
            
            # 初始化发布状态
            self._rollout_status[config_key] = RolloutStatus(
                config_key=config_key,
                current_version=self.get_current_version(config_key).version_id if self.get_current_version(config_key) else "",
                target_version=rule_id,
                progress=0.0,
                status="in_progress"
            )
            
            return rule_id
    
    def _get_rollout_value(self, config_key: str, client_id: str) -> Any:
        """
        获取灰度配置值
        
        Args:
            config_key: 配置键
            client_id: 客户端ID
            
        Returns:
            灰度配置值，如果不适用返回None
        """
        rules = self._rollout_rules.get(config_key, [])
        
        for rule in rules:
            if not rule.enabled:
                continue
            
            if self._match_rollout_rule(rule, client_id):
                return rule.target_value
        
        return None
    
    def _match_rollout_rule(self, rule: RolloutRule, client_id: str) -> bool:
        """检查客户端是否匹配灰度规则"""
        client_attrs = self._client_targets.get(client_id, {})
        
        if rule.strategy == RolloutStrategy.ALL:
            return True
        
        elif rule.strategy == RolloutStrategy.PERCENTAGE:
            percentage = rule.params.get("percentage", 0)
            # 基于client_id的哈希确定是否命中
            hash_val = int(hashlib.md5(client_id.encode()).hexdigest(), 16)
            return (hash_val % 100) < percentage
        
        elif rule.strategy == RolloutStrategy.CANARY:
            canary_list = rule.params.get("canary_list", [])
            return client_id in canary_list
        
        elif rule.strategy == RolloutStrategy.USER_ID:
            user_id_range = rule.params.get("user_id_range", [])
            user_id = client_attrs.get("user_id", client_id)
            return user_id in user_id_range
        
        elif rule.strategy == RolloutStrategy.IP_RANGE:
            client_ip = client_attrs.get("ip", "")
            ip_ranges = rule.params.get("ip_ranges", [])
            return self._ip_in_ranges(client_ip, ip_ranges)
        
        return False
    
    def _ip_in_ranges(self, ip: str, ranges: List[str]) -> bool:
        """检查IP是否在范围内"""
        # 简化的IP检查，实际应用中需要更复杂的逻辑
        for ip_range in ranges:
            if ip.startswith(ip_range.replace("*", "")):
                return True
        return False
    
    def update_rollout_progress(self, config_key: str,
                               progress: float) -> bool:
        """
        更新灰度发布进度
        
        Args:
            config_key: 配置键
            progress: 进度(0-100)
            
        Returns:
            是否更新成功
        """
        with self._lock:
            if config_key not in self._rollout_status:
                return False
            
            self._rollout_status[config_key].progress = min(100, max(0, progress))
            
            if progress >= 100:
                self._rollout_status[config_key].status = "completed"
                # 更新主配置
                rules = self._rollout_rules.get(config_key, [])
                for rule in rules:
                    if rule.enabled:
                        self.set_config(
                            key=config_key,
                            value=rule.target_value,
                            created_by="rollout"
                        )
                        rule.enabled = False
            
            return True
    
    def pause_rollout(self, config_key: str) -> bool:
        """
        暂停灰度发布
        
        Args:
            config_key: 配置键
            
        Returns:
            是否暂停成功
        """
        with self._lock:
            if config_key not in self._rollout_status:
                return False
            
            self._rollout_status[config_key].status = "paused"
            return True
    
    def resume_rollout(self, config_key: str) -> bool:
        """
        恢复灰度发布
        
        Args:
            config_key: 配置键
            
        Returns:
            是否恢复成功
        """
        with self._lock:
            if config_key not in self._rollout_status:
                return False
            
            if self._rollout_status[config_key].status == "paused":
                self._rollout_status[config_key].status = "in_progress"
            return True
    
    def rollback_rollout(self, config_key: str) -> bool:
        """
        回滚灰度发布
        
        Args:
            config_key: 配置键
            
        Returns:
            是否回滚成功
        """
        with self._lock:
            if config_key not in self._rollout_status:
                return False
            
            # 禁用所有灰度规则
            for rule in self._rollout_rules.get(config_key, []):
                rule.enabled = False
            
            self._rollout_status[config_key].status = "rolled_back"
            return True
    
    def get_rollout_status(self, config_key: str) -> Optional[RolloutStatus]:
        """
        获取灰度发布状态
        
        Args:
            config_key: 配置键
            
        Returns:
            发布状态
        """
        with self._lock:
            return self._rollout_status.get(config_key)
    
    def register_client(self, client_id: str,
                       attributes: Optional[Dict[str, Any]] = None) -> None:
        """
        注册客户端
        
        Args:
            client_id: 客户端ID
            attributes: 客户端属性(用于灰度匹配)
        """
        with self._lock:
            self._client_targets[client_id] = attributes or {}
    
    def unregister_client(self, client_id: str) -> None:
        """
        注销客户端
        
        Args:
            client_id: 客户端ID
        """
        with self._lock:
            if client_id in self._client_targets:
                del self._client_targets[client_id]
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            统计信息
        """
        with self._lock:
            total_configs = len(self._configs)
            total_versions = sum(len(v) for v in self._config_versions.values())
            active_rollouts = sum(
                1 for s in self._rollout_status.values()
                if s.status == "in_progress"
            )
            
            return {
                "total_configs": total_configs,
                "total_versions": total_versions,
                "avg_versions_per_config": total_versions / max(1, total_configs),
                "active_rollouts": active_rollouts,
                "registered_clients": len(self._client_targets),
                "registered_validators": len(self._validators)
            }


# 全局单例
_config_center_instance: Optional[ConfigCenter] = None
_config_center_lock = threading.Lock()


def get_config_center() -> ConfigCenter:
    """获取配置中心全局单例"""
    global _config_center_instance
    
    if _config_center_instance is None:
        with _config_center_lock:
            if _config_center_instance is None:
                _config_center_instance = ConfigCenter()
    
    return _config_center_instance
