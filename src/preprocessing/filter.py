"""
信息预处理模块
阶段 41-45：噪音过滤、幻觉拦截、隐私脱敏、有效性校验

核心特性：
- 所有入库数据的唯一入口
- 无状态、同步执行、高吞吐
- 100% 硬编码规则，不依赖模型概率判断
"""

import re
import hashlib
import base64
import time
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum


class RejectReason(Enum):
    """拒绝原因枚举"""
    NOISE = "noise"           # 噪音数据
    HALLUCINATION = "hallucination"  # 幻觉数据
    PRIVACY = "privacy"       # 隐私数据（需脱敏，非拒绝）
    INVALID = "invalid"       # 无效数据
    POISON = "poison"         # 投毒数据


@dataclass
class PreprocessResult:
    """预处理结果"""
    passed: bool                      # 是否通过
    content: str = ""                 # 处理后内容
    original: str = ""                # 原始内容
    reject_reason: Optional[str] = None  # 拒绝原因
    desensitized_fields: List[str] = field(default_factory=list)  # 脱敏字段
    metadata: Dict[str, Any] = field(default_factory=dict)


class NoiseFilter:
    """
    噪音过滤器（阶段 41）
    
    规则：
    - 剔除无意义闲聊（长度 < 5 字符且无实体关键词）
    - 剔除重复文本（编辑距离 < 3）
    - 剔除空白字符
    - 剔除无效指令
    """
    
    # 实体关键词（包含这些词视为有效内容）
    ENTITY_KEYWORDS = {
        "用户", "系统", "任务", "配置", "文件", "数据", "查询", "结果",
        "错误", "成功", "失败", "参数", "接口", "模块", "功能", "需求",
        "问题", "方案", "规则", "实体", "关系", "属性", "记忆", "存储",
        "召回", "更新", "删除", "创建", "修改", "优化", "测试", "部署"
    }
    
    def __init__(self, min_length: int = 5, max_edit_distance: int = 3):
        self.min_length = min_length
        self.max_edit_distance = max_edit_distance
        # 最近处理的内容缓存（用于去重）
        self._recent_contents: List[str] = []
        self._max_cache = 100
    
    def filter(self, content: str) -> Tuple[bool, str]:
        """
        过滤噪音
        
        Returns:
            Tuple[bool, str]: (是否通过, 处理后内容)
        """
        # 1. 空白检查
        stripped = content.strip()
        if not stripped:
            return False, ""
        
        # 2. 纯空白/符号检查
        if not re.search(r'[\u4e00-\u9fff\w]', stripped):
            return False, ""
        
        # 3. 最小长度检查（短内容需包含实体关键词）
        if len(stripped) < self.min_length:
            has_entity = any(kw in stripped for kw in self.ENTITY_KEYWORDS)
            if not has_entity:
                return False, ""
        
        # 4. 重复检查
        if self._is_duplicate(stripped):
            return False, ""
        
        # 5. 标准化空白
        cleaned = re.sub(r'\s+', ' ', stripped).strip()
        
        # 缓存
        self._recent_contents.append(cleaned)
        if len(self._recent_contents) > self._max_cache:
            self._recent_contents.pop(0)
        
        return True, cleaned
    
    def _is_duplicate(self, content: str) -> bool:
        """检查是否为重复内容"""
        for prev in self._recent_contents:
            if self._edit_distance(content, prev) < self.max_edit_distance:
                return True
        return False
    
    @staticmethod
    def _edit_distance(s1: str, s2: str) -> int:
        """计算编辑距离（Levenshtein）"""
        if len(s1) < len(s2):
            return NoiseFilter._edit_distance(s2, s1)
        if len(s2) == 0:
            return len(s1)
        
        prev_row = list(range(len(s2) + 1))
        for i, c1 in enumerate(s1):
            curr_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = prev_row[j + 1] + 1
                deletions = curr_row[j] + 1
                substitutions = prev_row[j] + (c1 != c2)
                curr_row.append(min(insertions, deletions, substitutions))
            prev_row = curr_row
        
        return prev_row[-1]


class HallucinationDetector:
    """
    幻觉检测器（阶段 43）
    
    规则：
    - 识别含模糊词且无数据支撑的断言
    - 检测与已有事实矛盾的陈述
    - 拦截无法验证的虚假事实
    """
    
    # 模糊词列表（含这些词且无数据支撑时判定为幻觉）
    FUZZY_KEYWORDS = [
        "可能", "大概", "也许", "似乎", "好像", "应该",
        "或许", "差不多", "估计", "猜测", "推测"
    ]
    
    # 绝对断言词（需要数据支撑）
    ABSOLUTE_KEYWORDS = [
        "一定是", "绝对是", "毫无疑问", "肯定", "必然",
        "绝对", "从来", "永远", "从不", "绝不"
    ]
    
    def __init__(self, l3_memory=None):
        self.l3_memory = l3_memory
        self.logger = logging.getLogger("preprocessing.hallucination")
    
    def detect(self, content: str) -> Tuple[bool, str]:
        """
        检测幻觉内容
        
        Returns:
            Tuple[bool, str]: (是否通过, 原因)
        """
        # 1. 模糊词 + 无数据支撑
        has_fuzzy = any(kw in content for kw in self.FUZZY_KEYWORDS)
        has_data = self._has_data_support(content)
        if has_fuzzy and not has_data:
            return False, "模糊断言且无数据支撑"
        
        # 2. 绝对断言 + 无数据支撑
        has_absolute = any(kw in content for kw in self.ABSOLUTE_KEYWORDS)
        if has_absolute and not has_data:
            return False, "绝对断言且无数据支撑"
        
        # 3. 与 L3 已有事实冲突检测
        if self.l3_memory:
            conflict = self._check_conflict(content)
            if conflict:
                return False, f"与已有事实冲突: {conflict}"
        
        return True, ""
    
    def _has_data_support(self, content: str) -> bool:
        """检查内容是否包含数据支撑"""
        # 包含数字、百分比、引用等视为有数据支撑
        if re.search(r'\d+[\.\,]?\d*[%]?', content):
            return True
        if re.search(r'根据|数据显示|统计|报告|文档|记录', content):
            return True
        if re.search(r'`[^`]+`|"[^"]+"|\'[^\']+\'', content):  # 引用
            return True
        return False
    
    def _check_conflict(self, content: str) -> Optional[str]:
        """检查与 L3 已有事实的冲突（简化实现）"""
        if not self.l3_memory:
            return None
        # 提取可能的实体名
        entities = re.findall(r'[\u4e00-\u9fff\w]{2,10}(?:是|为|等于|属于)', content)
        for entity_pattern in entities:
            entity_name = entity_pattern[:-2]  # 去掉尾部"是/为"
            existing = self.l3_memory.query_by_entity(entity_name)
            if existing:
                # 简单冲突检测：对比属性值
                for triple in existing:
                    if triple.object in content:
                        continue  # 一致
                    # 存在同名实体但值不同
                    return f"{triple.subject}.{triple.predicate}"
        return None


class PrivacyDesensitizer:
    """
    隐私脱敏器（阶段 42）
    
    规则：
    - 自动识别手机号、证件号、邮箱、地址等
    - 加密脱敏后存储，仅保留类型标签
    """
    
    # 敏感信息正则模式
    PATTERNS = {
        "phone": {
            "regex": r'1[3-9]\d{9}',
            "replacement": "[PHONE]",
            "label": "手机号"
        },
        "email": {
            "regex": r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
            "replacement": "[EMAIL]",
            "label": "邮箱"
        },
        "id_card": {
            "regex": r'[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]',
            "replacement": "[ID_CARD]",
            "label": "身份证号"
        },
        "address": {
            "regex": r'(?:北京市|上海市|广州市|深圳市|杭州市|成都市|武汉市|南京市|重庆市|天津市)[\u4e00-\u9fff\w]{3,30}(?:路|街|道|巷|号|栋|楼|室|层)',
            "replacement": "[ADDRESS]",
            "label": "地址"
        },
        "bank_card": {
            "regex": r'\b\d{16,19}\b',
            "replacement": "[BANK_CARD]",
            "label": "银行卡号"
        }
    }
    
    def __init__(self, encrypt: bool = True, encryption_key: str = ""):
        self.encrypt = encrypt
        self.encryption_key = encryption_key or "default_key_change_me"
        self.logger = logging.getLogger("preprocessing.privacy")
    
    def desensitize(self, content: str) -> Tuple[str, List[str]]:
        """
        脱敏处理
        
        Returns:
            Tuple[str, List[str]]: (脱敏后内容, 脱敏字段列表)
        """
        desensitized_fields = []
        result = content
        
        for field_name, pattern_info in self.PATTERNS.items():
            matches = re.findall(pattern_info["regex"], result)
            if matches:
                for match in matches:
                    # 加密存储原始值
                    if self.encrypt:
                        encrypted = self._encrypt(match)
                        self.logger.debug(f"隐私脱敏: {pattern_info['label']} -> {encrypted[:8]}...")
                    
                    desensitized_fields.append(f"{pattern_info['label']}")
                
                # 替换为标签
                result = re.sub(pattern_info["regex"], pattern_info["replacement"], result)
        
        return result, list(set(desensitized_fields))
    
    def _encrypt(self, value: str) -> str:
        """简单加密（生产环境应使用 AES-256）"""
        combined = f"{self.encryption_key}:{value}"
        hashed = hashlib.sha256(combined.encode()).digest()
        return base64.b64encode(hashed).decode()[:32]
    
    def contains_sensitive(self, content: str) -> bool:
        """检查是否包含敏感信息"""
        for pattern_info in self.PATTERNS.values():
            if re.search(pattern_info["regex"], content):
                return True
        return False


class ValidityChecker:
    """
    有效性校验器（阶段 44）
    
    规则：
    - 判定信息是否具备复用价值
    - 需包含实体/操作/结果三要素中至少两项
    """
    
    # 操作关键词
    ACTION_KEYWORDS = [
        "创建", "修改", "删除", "查询", "更新", "优化", "配置",
        "部署", "测试", "启动", "停止", "重启", "安装", "卸载",
        "设置", "获取", "发送", "接收", "处理", "执行", "完成",
        "失败", "成功", "错误", "异常", "警告", "跳过"
    ]
    
    # 结果关键词
    RESULT_KEYWORDS = [
        "结果", "输出", "返回", "状态", "成功", "失败", "错误",
        "完成", "超时", "中断", "异常", "数据", "信息", "记录",
        "文件", "报告", "日志", "配置", "参数"
    ]
    
    def check(self, content: str) -> Tuple[bool, str]:
        """
        校验有效性
        
        Returns:
            Tuple[bool, str]: (是否有效, 原因)
        """
        has_entity = len(re.findall(r'[\u4e00-\u9fff\w]{2,}', content)) >= 2
        has_action = any(kw in content for kw in self.ACTION_KEYWORDS)
        has_result = any(kw in content for kw in self.RESULT_KEYWORDS)
        
        score = sum([has_entity, has_action, has_result])
        
        if score >= 2:
            return True, f"有效（得分: {score}/3）"
        
        return False, f"无效（得分: {score}/3，需至少包含实体/操作/结果中两项）"


class Preprocessor:
    """
    预处理器总入口（阶段 45）
    
    串联所有过滤器，统一对外调用接口。
    所有入库数据必须经过此模块。
    """
    
    def __init__(self, config: Optional[Dict] = None, l3_memory=None):
        config = config or {}
        
        noise_config = config.get("noise_filter", {})
        self.noise_filter = NoiseFilter(
            min_length=noise_config.get("min_content_length", 5),
            max_edit_distance=noise_config.get("max_duplicate_edit_distance", 3)
        )
        
        self.hallucination_detector = HallucinationDetector(l3_memory=l3_memory)
        
        privacy_config = config.get("privacy", {})
        self.privacy_desensitizer = PrivacyDesensitizer(
            encrypt=privacy_config.get("encrypt_sensitive", True),
            encryption_key=privacy_config.get("encryption_key", "")
        )
        
        self.validity_checker = ValidityChecker()
        self.logger = logging.getLogger("preprocessing")
    
    def process(self, content: str) -> PreprocessResult:
        """
        预处理入口
        
        Args:
            content: 原始内容
            
        Returns:
            PreprocessResult: 预处理结果
        """
        result = PreprocessResult(original=content)
        
        # Step 1: 噪音过滤
        passed, cleaned = self.noise_filter.filter(content)
        if not passed:
            result.reject_reason = RejectReason.NOISE.value
            self.logger.debug(f"噪音过滤拒绝: {content[:50]}...")
            return result
        
        # Step 2: 幻觉拦截
        passed, reason = self.hallucination_detector.detect(cleaned)
        if not passed:
            result.reject_reason = RejectReason.HALLUCINATION.value
            result.metadata["hallucination_reason"] = reason
            self.logger.info(f"幻觉拦截: {reason} - {content[:50]}...")
            return result
        
        # Step 3: 隐私脱敏（不拒绝，而是脱敏后放行）
        desensitized, fields = self.privacy_desensitizer.desensitize(cleaned)
        result.desensitized_fields = fields
        result.content = desensitized
        
        # Step 4: 有效性校验
        passed, reason = self.validity_checker.check(desensitized)
        if not passed:
            result.reject_reason = RejectReason.INVALID.value
            result.metadata["invalid_reason"] = reason
            self.logger.debug(f"有效性校验拒绝: {reason} - {content[:50]}...")
            return result
        
        # 通过所有检查
        result.passed = True
        self.logger.info(f"预处理通过: {content[:50]}...")
        return result
    
    def process_batch(self, contents: List[str]) -> List[PreprocessResult]:
        """批量预处理"""
        return [self.process(content) for content in contents]
