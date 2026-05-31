"""
数据管道 (DataPipeline)
阶段245-247: ETL流程、数据转换、质量检查

基于第一性原则设计:
1. 确定性: 纯函数式数据转换，无副作用
2. 可靠性: 数据质量检查和错误处理
3. 可扩展性: 插件式架构，易于扩展
"""

import threading
import time
import hashlib
import re
from typing import Dict, List, Optional, Any, Callable, Tuple, Set, Union
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict


class PipelineStage(Enum):
    """管道阶段"""
    EXTRACT = "extract"      # 抽取
    TRANSFORM = "transform"  # 转换
    LOAD = "load"            # 加载


class DataType(Enum):
    """数据类型"""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    JSON = "json"
    LIST = "list"
    DICT = "dict"


class QualityRuleType(Enum):
    """数据质量规则类型"""
    NOT_NULL = "not_null"           # 非空检查
    UNIQUE = "unique"               # 唯一性检查
    RANGE = "range"                 # 范围检查
    PATTERN = "pattern"             # 模式匹配
    TYPE_CHECK = "type_check"       # 类型检查
    LENGTH = "length"               # 长度检查
    REFERENTIAL = "referential"     # 引用完整性
    CUSTOM = "custom"               # 自定义规则


@dataclass
class DataRecord:
    """数据记录"""
    record_id: str
    data: Dict[str, Any]
    source: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QualityRule:
    """数据质量规则"""
    rule_id: str
    rule_type: QualityRuleType
    field: str
    params: Dict[str, Any] = field(default_factory=dict)
    error_message: str = ""
    is_critical: bool = False


@dataclass
class QualityIssue:
    """数据质量问题"""
    record_id: str
    rule_id: str
    field: str
    issue_type: str
    message: str
    is_critical: bool
    timestamp: float = field(default_factory=time.time)


@dataclass
class PipelineResult:
    """管道处理结果"""
    pipeline_id: str
    success: bool
    input_count: int
    output_count: int
    error_count: int
    processing_time_ms: float
    issues: List[QualityIssue] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class TransformRule:
    """转换规则"""
    rule_id: str
    source_field: Optional[str]
    target_field: str
    transform_func: Callable[[Any], Any]
    condition: Optional[Callable[[Dict[str, Any]], bool]] = None


class DataPipeline:
    """
    数据管道
    
    核心功能:
    1. ETL流程: 抽取、转换、加载的标准化流程
    2. 数据转换: 字段映射、类型转换、数据清洗
    3. 质量检查: 多维度数据质量验证
    """
    
    def __init__(self):
        self._lock = threading.RLock()
        
        # ETL组件
        self._extractors: Dict[str, Callable[[], List[DataRecord]]] = {}
        self._transformers: Dict[str, List[TransformRule]] = defaultdict(list)
        self._loaders: Dict[str, Callable[[List[DataRecord]], bool]] = {}
        
        # 数据质量
        self._quality_rules: Dict[str, List[QualityRule]] = defaultdict(list)
        self._quality_issues: List[QualityIssue] = []
        self._max_issues = 10000
        
        # 管道执行历史
        self._execution_history: List[PipelineResult] = []
        self._max_history = 1000
        
        # 统计信息
        self._total_processed = 0
        self._total_errors = 0
    
    # ==================== 阶段245: ETL流程 ====================
    
    def register_extractor(self, source_name: str,
                          extractor: Callable[[], List[DataRecord]]) -> None:
        """
        注册数据抽取器
        
        Args:
            source_name: 数据源名称
            extractor: 抽取函数
        """
        with self._lock:
            self._extractors[source_name] = extractor
    
    def register_loader(self, target_name: str,
                       loader: Callable[[List[DataRecord]], bool]) -> None:
        """
        注册数据加载器
        
        Args:
            target_name: 目标名称
            loader: 加载函数
        """
        with self._lock:
            self._loaders[target_name] = loader
    
    def execute_etl(self, source_name: str, target_name: str,
                   transform_pipeline: Optional[str] = None,
                   quality_check: bool = True) -> PipelineResult:
        """
        执行ETL流程
        
        Args:
            source_name: 数据源名称
            target_name: 数据目标名称
            transform_pipeline: 转换管道名称
            quality_check: 是否执行质量检查
            
        Returns:
            处理结果
        """
        start_time = time.time()
        pipeline_id = self._generate_pipeline_id()
        
        with self._lock:
            errors = []
            issues = []
            
            # 1. Extract
            if source_name not in self._extractors:
                result = PipelineResult(
                    pipeline_id=pipeline_id,
                    success=False,
                    input_count=0,
                    output_count=0,
                    error_count=1,
                    processing_time_ms=0,
                    errors=[f"Extractor not found: {source_name}"]
                )
                self._execution_history.append(result)
                return result
            
            try:
                records = self._extractors[source_name]()
            except Exception as e:
                result = PipelineResult(
                    pipeline_id=pipeline_id,
                    success=False,
                    input_count=0,
                    output_count=0,
                    error_count=1,
                    processing_time_ms=(time.time() - start_time) * 1000,
                    errors=[f"Extraction failed: {str(e)}"]
                )
                self._execution_history.append(result)
                return result
            
            input_count = len(records)
            
            # 2. Transform
            if transform_pipeline:
                records = self._transform_records(records, transform_pipeline)
            
            # 3. Quality Check
            if quality_check:
                issues = self._check_quality(records, source_name)
                # 过滤掉有严重问题的记录
                critical_issue_records = {
                    issue.record_id for issue in issues if issue.is_critical
                }
                records = [r for r in records if r.record_id not in critical_issue_records]
            
            # 4. Load
            if target_name not in self._loaders:
                result = PipelineResult(
                    pipeline_id=pipeline_id,
                    success=False,
                    input_count=input_count,
                    output_count=0,
                    error_count=1,
                    processing_time_ms=(time.time() - start_time) * 1000,
                    errors=[f"Loader not found: {target_name}"]
                )
                self._execution_history.append(result)
                return result
            
            try:
                load_success = self._loaders[target_name](records)
                if not load_success:
                    errors.append("Loading failed")
            except Exception as e:
                errors.append(f"Loading error: {str(e)}")
                load_success = False
            
            output_count = len(records)
            error_count = len(errors) + len(critical_issue_records) if quality_check else len(errors)
            
            result = PipelineResult(
                pipeline_id=pipeline_id,
                success=load_success and len(errors) == 0,
                input_count=input_count,
                output_count=output_count,
                error_count=error_count,
                processing_time_ms=(time.time() - start_time) * 1000,
                issues=issues,
                errors=errors
            )
            
            self._execution_history.append(result)
            if len(self._execution_history) > self._max_history:
                self._execution_history = self._execution_history[-self._max_history:]
            
            self._total_processed += input_count
            self._total_errors += error_count
            
            return result
    
    def _generate_pipeline_id(self) -> str:
        """生成管道ID"""
        timestamp = str(time.time())
        return hashlib.md5(timestamp.encode()).hexdigest()[:16]
    
    # ==================== 阶段246: 数据转换 ====================
    
    def add_transform_rule(self, pipeline_name: str, rule: TransformRule) -> None:
        """
        添加转换规则
        
        Args:
            pipeline_name: 管道名称
            rule: 转换规则
        """
        with self._lock:
            self._transformers[pipeline_name].append(rule)
    
    def create_mapping_rule(self, pipeline_name: str, source_field: str,
                           target_field: str) -> str:
        """
        创建字段映射规则
        
        Args:
            pipeline_name: 管道名称
            source_field: 源字段
            target_field: 目标字段
            
        Returns:
            规则ID
        """
        rule_id = f"map_{source_field}_{target_field}"
        rule = TransformRule(
            rule_id=rule_id,
            source_field=source_field,
            target_field=target_field,
            transform_func=lambda x: x
        )
        self.add_transform_rule(pipeline_name, rule)
        return rule_id
    
    def create_type_conversion_rule(self, pipeline_name: str, field: str,
                                    target_type: DataType,
                                    default_value: Any = None) -> str:
        """
        创建类型转换规则
        
        Args:
            pipeline_name: 管道名称
            field: 字段名
            target_type: 目标类型
            default_value: 默认值
            
        Returns:
            规则ID
        """
        rule_id = f"type_{field}_{target_type.value}"
        
        def convert_type(value: Any) -> Any:
            if value is None:
                return default_value
            
            try:
                if target_type == DataType.STRING:
                    return str(value)
                elif target_type == DataType.INTEGER:
                    return int(value)
                elif target_type == DataType.FLOAT:
                    return float(value)
                elif target_type == DataType.BOOLEAN:
                    return bool(value)
                elif target_type == DataType.DATETIME:
                    return float(value) if isinstance(value, (int, float)) else str(value)
                else:
                    return value
            except (ValueError, TypeError):
                return default_value
        
        rule = TransformRule(
            rule_id=rule_id,
            source_field=field,
            target_field=field,
            transform_func=convert_type
        )
        self.add_transform_rule(pipeline_name, rule)
        return rule_id
    
    def create_filter_rule(self, pipeline_name: str,
                          condition: Callable[[Dict[str, Any]], bool]) -> str:
        """
        创建过滤规则
        
        Args:
            pipeline_name: 管道名称
            condition: 过滤条件函数
            
        Returns:
            规则ID
        """
        rule_id = f"filter_{hashlib.md5(str(time.time()).encode()).hexdigest()[:8]}"
        
        rule = TransformRule(
            rule_id=rule_id,
            source_field=None,
            target_field="",
            transform_func=lambda x: x,
            condition=condition
        )
        self.add_transform_rule(pipeline_name, rule)
        return rule_id
    
    def _transform_records(self, records: List[DataRecord],
                          pipeline_name: str) -> List[DataRecord]:
        """
        转换数据记录
        
        Args:
            records: 数据记录列表
            pipeline_name: 管道名称
            
        Returns:
            转换后的记录列表
        """
        rules = self._transformers.get(pipeline_name, [])
        transformed_records = []
        
        for record in records:
            new_data = dict(record.data)
            should_include = True
            
            for rule in rules:
                # 检查条件
                if rule.condition and not rule.condition(new_data):
                    if rule.target_field == "":  # 过滤规则
                        should_include = False
                        break
                    continue
                
                # 应用转换
                if rule.source_field:
                    value = new_data.get(rule.source_field)
                    new_value = rule.transform_func(value)
                    new_data[rule.target_field] = new_value
                
                # 如果是映射到不同字段，删除原字段
                if (rule.source_field and rule.target_field and 
                    rule.source_field != rule.target_field):
                    if rule.source_field in new_data:
                        del new_data[rule.source_field]
            
            if should_include:
                transformed_record = DataRecord(
                    record_id=record.record_id,
                    data=new_data,
                    source=record.source,
                    timestamp=record.timestamp,
                    metadata=record.metadata
                )
                transformed_records.append(transformed_record)
        
        return transformed_records
    
    # ==================== 阶段247: 质量检查 ====================
    
    def add_quality_rule(self, source_name: str, rule: QualityRule) -> None:
        """
        添加质量规则
        
        Args:
            source_name: 数据源名称
            rule: 质量规则
        """
        with self._lock:
            self._quality_rules[source_name].append(rule)
    
    def create_not_null_rule(self, source_name: str, field: str,
                            is_critical: bool = True) -> str:
        """
        创建非空规则
        
        Args:
            source_name: 数据源名称
            field: 字段名
            is_critical: 是否严重
            
        Returns:
            规则ID
        """
        rule_id = f"nn_{field}"
        rule = QualityRule(
            rule_id=rule_id,
            rule_type=QualityRuleType.NOT_NULL,
            field=field,
            error_message=f"Field '{field}' cannot be null",
            is_critical=is_critical
        )
        self.add_quality_rule(source_name, rule)
        return rule_id
    
    def create_range_rule(self, source_name: str, field: str,
                         min_value: Optional[float] = None,
                         max_value: Optional[float] = None,
                         is_critical: bool = True) -> str:
        """
        创建范围规则
        
        Args:
            source_name: 数据源名称
            field: 字段名
            min_value: 最小值
            max_value: 最大值
            is_critical: 是否严重
            
        Returns:
            规则ID
        """
        rule_id = f"range_{field}"
        rule = QualityRule(
            rule_id=rule_id,
            rule_type=QualityRuleType.RANGE,
            field=field,
            params={"min": min_value, "max": max_value},
            error_message=f"Field '{field}' out of range",
            is_critical=is_critical
        )
        self.add_quality_rule(source_name, rule)
        return rule_id
    
    def create_pattern_rule(self, source_name: str, field: str,
                           pattern: str,
                           is_critical: bool = True) -> str:
        """
        创建模式匹配规则
        
        Args:
            source_name: 数据源名称
            field: 字段名
            pattern: 正则表达式
            is_critical: 是否严重
            
        Returns:
            规则ID
        """
        rule_id = f"pattern_{field}"
        rule = QualityRule(
            rule_id=rule_id,
            rule_type=QualityRuleType.PATTERN,
            field=field,
            params={"pattern": pattern},
            error_message=f"Field '{field}' does not match pattern",
            is_critical=is_critical
        )
        self.add_quality_rule(source_name, rule)
        return rule_id
    
    def create_type_rule(self, source_name: str, field: str,
                        expected_type: DataType,
                        is_critical: bool = True) -> str:
        """
        创建类型检查规则
        
        Args:
            source_name: 数据源名称
            field: 字段名
            expected_type: 期望类型
            is_critical: 是否严重
            
        Returns:
            规则ID
        """
        rule_id = f"type_{field}"
        rule = QualityRule(
            rule_id=rule_id,
            rule_type=QualityRuleType.TYPE_CHECK,
            field=field,
            params={"expected_type": expected_type},
            error_message=f"Field '{field}' type mismatch",
            is_critical=is_critical
        )
        self.add_quality_rule(source_name, rule)
        return rule_id
    
    def _check_quality(self, records: List[DataRecord],
                      source_name: str) -> List[QualityIssue]:
        """
        检查数据质量
        
        Args:
            records: 数据记录列表
            source_name: 数据源名称
            
        Returns:
            质量问题列表
        """
        rules = self._quality_rules.get(source_name, [])
        issues = []
        
        for record in records:
            for rule in rules:
                issue = self._check_rule(record, rule)
                if issue:
                    issues.append(issue)
                    
                    with self._lock:
                        self._quality_issues.append(issue)
                        if len(self._quality_issues) > self._max_issues:
                            self._quality_issues = self._quality_issues[-self._max_issues:]
        
        return issues
    
    def _check_rule(self, record: DataRecord, rule: QualityRule) -> Optional[QualityIssue]:
        """检查单条规则"""
        value = record.data.get(rule.field)
        
        if rule.rule_type == QualityRuleType.NOT_NULL:
            if value is None or value == "":
                return QualityIssue(
                    record_id=record.record_id,
                    rule_id=rule.rule_id,
                    field=rule.field,
                    issue_type="null_value",
                    message=rule.error_message,
                    is_critical=rule.is_critical
                )
        
        elif rule.rule_type == QualityRuleType.RANGE:
            if value is not None:
                try:
                    num_value = float(value)
                    min_val = rule.params.get("min")
                    max_val = rule.params.get("max")
                    
                    if min_val is not None and num_value < min_val:
                        return QualityIssue(
                            record_id=record.record_id,
                            rule_id=rule.rule_id,
                            field=rule.field,
                            issue_type="out_of_range",
                            message=f"Value {num_value} < min {min_val}",
                            is_critical=rule.is_critical
                        )
                    
                    if max_val is not None and num_value > max_val:
                        return QualityIssue(
                            record_id=record.record_id,
                            rule_id=rule.rule_id,
                            field=rule.field,
                            issue_type="out_of_range",
                            message=f"Value {num_value} > max {max_val}",
                            is_critical=rule.is_critical
                        )
                except (ValueError, TypeError):
                    pass
        
        elif rule.rule_type == QualityRuleType.PATTERN:
            if value is not None:
                pattern = rule.params.get("pattern", "")
                if not re.match(pattern, str(value)):
                    return QualityIssue(
                        record_id=record.record_id,
                        rule_id=rule.rule_id,
                        field=rule.field,
                        issue_type="pattern_mismatch",
                        message=rule.error_message,
                        is_critical=rule.is_critical
                    )
        
        elif rule.rule_type == QualityRuleType.TYPE_CHECK:
            if value is not None:
                expected = rule.params.get("expected_type")
                type_valid = False
                
                if expected == DataType.STRING:
                    type_valid = isinstance(value, str)
                elif expected == DataType.INTEGER:
                    type_valid = isinstance(value, int) and not isinstance(value, bool)
                elif expected == DataType.FLOAT:
                    type_valid = isinstance(value, (int, float)) and not isinstance(value, bool)
                elif expected == DataType.BOOLEAN:
                    type_valid = isinstance(value, bool)
                
                if not type_valid:
                    return QualityIssue(
                        record_id=record.record_id,
                        rule_id=rule.rule_id,
                        field=rule.field,
                        issue_type="type_mismatch",
                        message=f"Expected {expected.value}, got {type(value).__name__}",
                        is_critical=rule.is_critical
                    )
        
        return None
    
    def get_quality_report(self, source_name: Optional[str] = None) -> Dict[str, Any]:
        """
        获取质量报告
        
        Args:
            source_name: 数据源名称，None表示全部
            
        Returns:
            质量报告
        """
        with self._lock:
            issues = self._quality_issues
            if source_name:
                issues = [i for i in issues if i.field == source_name]
            
            total_issues = len(issues)
            critical_issues = len([i for i in issues if i.is_critical])
            
            issue_types = defaultdict(int)
            for issue in issues:
                issue_types[issue.issue_type] += 1
            
            return {
                "total_issues": total_issues,
                "critical_issues": critical_issues,
                "warning_issues": total_issues - critical_issues,
                "issue_types": dict(issue_types),
                "recent_issues": [
                    {
                        "record_id": i.record_id,
                        "field": i.field,
                        "type": i.issue_type,
                        "message": i.message,
                        "is_critical": i.is_critical
                    }
                    for i in issues[-10:]
                ]
            }
    
    def get_execution_history(self, limit: int = 100) -> List[PipelineResult]:
        """
        获取执行历史
        
        Args:
            limit: 返回记录数量限制
            
        Returns:
            执行历史列表
        """
        with self._lock:
            return self._execution_history[-limit:]
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            统计信息
        """
        with self._lock:
            return {
                "total_processed": self._total_processed,
                "total_errors": self._total_errors,
                "success_rate": (self._total_processed - self._total_errors) / max(1, self._total_processed),
                "extractor_count": len(self._extractors),
                "loader_count": len(self._loaders),
                "transform_pipeline_count": len(self._transformers),
                "quality_rule_count": sum(len(rules) for rules in self._quality_rules.values())
            }


# 全局单例
_data_pipeline_instance: Optional[DataPipeline] = None
_data_pipeline_lock = threading.Lock()


def get_data_pipeline() -> DataPipeline:
    """获取数据管道全局单例"""
    global _data_pipeline_instance
    
    if _data_pipeline_instance is None:
        with _data_pipeline_lock:
            if _data_pipeline_instance is None:
                _data_pipeline_instance = DataPipeline()
    
    return _data_pipeline_instance
