#!/usr/bin/env python3
"""
数据质量模块 (data_quality) - 阶段351-355

模块列表：
- data_validator: 数据验证器（Schema验证/类型检查/约束验证）
- data_cleaner: 数据清洗器（去空/标准化/去重/修复）
- data_transformer: 数据转换器（格式转换/编码转换/映射）
- data_quality_assessor: 数据质量评估器（完整性/一致性/准确性评估）
- data_repair_engine: 数据修复引擎（自动修复/规则引擎）
"""

from .data_validator import (
    DataValidator,
    Schema,
    FieldRule,
    DataType,
    ValidationLevel,
    ValidationError,
    ValidationResult,
    TypeChecker,
    CommonValidators,
    get_data_validator,
)

from .data_cleaner import (
    DataCleaner,
    NullHandler,
    NullAction,
    DedupStrategy,
    CaseAction,
    StringNormalizer,
    Deduplicator,
    OutlierDetector,
    CleaningStats,
    CleaningResult,
    get_data_cleaner,
)

from .data_transformer import (
    DataTransformer,
    FormatConverter,
    EncodingConverter,
    FieldMapper,
    TypeConverter,
    FormatType,
    EncodingType,
    TransformStats,
    TransformResult,
    get_data_transformer,
)

from .data_quality_assessor import (
    DataQualityAssessor,
    CompletenessAssessor,
    ConsistencyAssessor,
    AccuracyAssessor,
    TimelinessAssessor,
    UniquenessAssessor,
    QualityDimension,
    QualityLevel,
    DimensionScore,
    QualityReport,
    get_quality_assessor,
)

from .data_repair_engine import (
    DataRepairEngine,
    RepairRule,
    RepairAction,
    RepairPriority,
    RepairRecord,
    RepairStats,
    RepairResult,
    BuiltinRules,
    get_repair_engine,
)

__all__ = [
    # Validator
    "DataValidator",
    "Schema",
    "FieldRule",
    "DataType",
    "ValidationLevel",
    "ValidationError",
    "ValidationResult",
    "TypeChecker",
    "CommonValidators",
    "get_data_validator",
    # Cleaner
    "DataCleaner",
    "NullHandler",
    "NullAction",
    "DedupStrategy",
    "CaseAction",
    "StringNormalizer",
    "Deduplicator",
    "OutlierDetector",
    "CleaningStats",
    "CleaningResult",
    "get_data_cleaner",
    # Transformer
    "DataTransformer",
    "FormatConverter",
    "EncodingConverter",
    "FieldMapper",
    "TypeConverter",
    "FormatType",
    "EncodingType",
    "TransformStats",
    "TransformResult",
    "get_data_transformer",
    # Assessor
    "DataQualityAssessor",
    "CompletenessAssessor",
    "ConsistencyAssessor",
    "AccuracyAssessor",
    "TimelinessAssessor",
    "UniquenessAssessor",
    "QualityDimension",
    "QualityLevel",
    "DimensionScore",
    "QualityReport",
    "get_quality_assessor",
    # Repair
    "DataRepairEngine",
    "RepairRule",
    "RepairAction",
    "RepairPriority",
    "RepairRecord",
    "RepairStats",
    "RepairResult",
    "BuiltinRules",
    "get_repair_engine",
]
