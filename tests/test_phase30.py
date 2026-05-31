#!/usr/bin/env python3
"""
第30阶段验证测试 - 数据验证与清洗模块 (阶段351-355)

覆盖模块：
- 阶段351: DataValidator - Schema验证/类型检查/约束验证
- 阶段352: DataCleaner - 去空/标准化/去重/修复
- 阶段353: DataTransformer - 格式转换/编码转换/映射
- 阶段354: DataQualityAssessor - 完整性/一致性/准确性评估
- 阶段355: DataRepairEngine - 自动修复/规则引擎
"""

import sys
import os
import time
import unittest
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from data_quality.data_validator import (
    DataValidator, Schema, FieldRule, DataType, ValidationLevel,
    ValidationError, ValidationResult, TypeChecker, CommonValidators,
    get_data_validator,
)
from data_quality.data_cleaner import (
    DataCleaner, NullHandler, NullAction, DedupStrategy, CaseAction,
    StringNormalizer, Deduplicator, OutlierDetector,
    CleaningStats, CleaningResult, get_data_cleaner,
)
from data_quality.data_transformer import (
    DataTransformer, FormatConverter, EncodingConverter, FieldMapper,
    TypeConverter, FormatType, EncodingType,
    TransformStats, TransformResult, get_data_transformer,
)
from data_quality.data_quality_assessor import (
    DataQualityAssessor, CompletenessAssessor, ConsistencyAssessor,
    AccuracyAssessor, TimelinessAssessor, UniquenessAssessor,
    QualityDimension, QualityLevel, DimensionScore, QualityReport,
    get_quality_assessor,
)
from data_quality.data_repair_engine import (
    DataRepairEngine, RepairRule, RepairAction, RepairPriority,
    RepairRecord, RepairStats, RepairResult, BuiltinRules,
    get_repair_engine,
)


# ============================================================
# 阶段351: DataValidator 测试
# ============================================================

class TestDataType(unittest.TestCase):
    """DataType 枚举测试"""

    def test_all_types(self):
        types = [DataType.STRING, DataType.INTEGER, DataType.FLOAT,
                 DataType.BOOLEAN, DataType.DATE, DataType.DATETIME,
                 DataType.LIST, DataType.DICT, DataType.ANY]
        for t in types:
            self.assertIsInstance(t.value, str)


class TestValidationError(unittest.TestCase):
    """ValidationError 测试"""

    def test_to_dict(self):
        err = ValidationError(
            field="name",
            message="Required field",
            level=ValidationLevel.ERROR,
            value="test",
            rule="required",
        )
        d = err.to_dict()
        self.assertEqual(d["field"], "name")
        self.assertEqual(d["message"], "Required field")
        self.assertEqual(d["level"], "error")
        self.assertEqual(d["rule"], "required")


class TestValidationResult(unittest.TestCase):
    """ValidationResult 测试"""

    def test_initial_state(self):
        result = ValidationResult(valid=True)
        self.assertTrue(result.valid)
        self.assertFalse(result.has_errors)
        self.assertFalse(result.has_warnings)

    def test_add_error(self):
        result = ValidationResult(valid=True)
        result.add_error(ValidationError("f1", "error", ValidationLevel.ERROR))
        self.assertFalse(result.valid)
        self.assertTrue(result.has_errors)
        self.assertEqual(len(result.errors), 1)

    def test_add_warning(self):
        result = ValidationResult(valid=True)
        result.add_error(ValidationError("f1", "warn", ValidationLevel.WARNING))
        self.assertTrue(result.valid)
        self.assertTrue(result.has_warnings)
        self.assertEqual(len(result.warnings), 1)

    def test_merge(self):
        r1 = ValidationResult(valid=True)
        r2 = ValidationResult(valid=False)
        r2.add_error(ValidationError("f1", "error", ValidationLevel.ERROR))
        r1.merge(r2)
        self.assertFalse(r1.valid)
        self.assertEqual(len(r1.errors), 1)


class TestTypeChecker(unittest.TestCase):
    """TypeChecker 测试"""

    def test_string(self):
        self.assertTrue(TypeChecker.check("hello", DataType.STRING))
        self.assertFalse(TypeChecker.check(123, DataType.STRING))

    def test_integer(self):
        self.assertTrue(TypeChecker.check(123, DataType.INTEGER))
        self.assertFalse(TypeChecker.check(123.5, DataType.INTEGER))
        self.assertFalse(TypeChecker.check(True, DataType.INTEGER))

    def test_float(self):
        self.assertTrue(TypeChecker.check(123.5, DataType.FLOAT))
        self.assertTrue(TypeChecker.check(123, DataType.FLOAT))

    def test_boolean(self):
        self.assertTrue(TypeChecker.check(True, DataType.BOOLEAN))
        self.assertTrue(TypeChecker.check(False, DataType.BOOLEAN))
        self.assertFalse(TypeChecker.check(1, DataType.BOOLEAN))

    def test_list(self):
        self.assertTrue(TypeChecker.check([1, 2, 3], DataType.LIST))
        self.assertFalse(TypeChecker.check("abc", DataType.LIST))

    def test_dict(self):
        self.assertTrue(TypeChecker.check({"a": 1}, DataType.DICT))
        self.assertFalse(TypeChecker.check([1, 2], DataType.DICT))

    def test_any(self):
        self.assertTrue(TypeChecker.check("x", DataType.ANY))
        self.assertTrue(TypeChecker.check(123, DataType.ANY))

    def test_try_convert_string(self):
        ok, val = TypeChecker.try_convert(123, DataType.STRING)
        self.assertTrue(ok)
        self.assertEqual(val, "123")

    def test_try_convert_int(self):
        ok, val = TypeChecker.try_convert("123", DataType.INTEGER)
        self.assertTrue(ok)
        self.assertEqual(val, 123)

    def test_try_convert_float(self):
        ok, val = TypeChecker.try_convert("123.5", DataType.FLOAT)
        self.assertTrue(ok)
        self.assertEqual(val, 123.5)

    def test_try_convert_bool(self):
        ok, val = TypeChecker.try_convert("true", DataType.BOOLEAN)
        self.assertTrue(ok)
        self.assertTrue(val)
        ok, val = TypeChecker.try_convert("false", DataType.BOOLEAN)
        self.assertTrue(ok)
        self.assertFalse(val)


class TestFieldRule(unittest.TestCase):
    """FieldRule 测试"""

    def test_basic_rule(self):
        rule = FieldRule(name="age", data_type=DataType.INTEGER,
                         min_value=0, max_value=150)
        self.assertEqual(rule.name, "age")
        self.assertEqual(rule.data_type, DataType.INTEGER)
        self.assertEqual(rule.min_value, 0)
        self.assertEqual(rule.max_value, 150)


class TestSchema(unittest.TestCase):
    """Schema 测试"""

    def test_add_field(self):
        schema = Schema(name="user")
        schema.add_field(FieldRule(name="name", data_type=DataType.STRING))
        self.assertIn("name", schema.fields)

    def test_get_field(self):
        schema = Schema(name="user")
        schema.add_field(FieldRule(name="name"))
        rule = schema.get_field("name")
        self.assertEqual(rule.name, "name")
        self.assertIsNone(schema.get_field("nonexistent"))


class TestDataValidator(unittest.TestCase):
    """DataValidator 核心测试"""

    def test_validate_required_field(self):
        validator = DataValidator()
        schema = Schema(name="test")
        schema.add_field(FieldRule(name="name", required=True))

        result = validator.validate({}, schema)
        self.assertFalse(result.valid)
        self.assertTrue(result.has_errors)

    def test_validate_type(self):
        validator = DataValidator()
        schema = Schema(name="test")
        schema.add_field(FieldRule(name="age", data_type=DataType.INTEGER))

        result = validator.validate({"age": "not_int"}, schema)
        self.assertFalse(result.valid)

        result = validator.validate({"age": 25}, schema)
        self.assertTrue(result.valid)

    def test_validate_min_max(self):
        validator = DataValidator()
        schema = Schema(name="test")
        schema.add_field(FieldRule(name="age", data_type=DataType.INTEGER,
                                   min_value=0, max_value=150))

        result = validator.validate({"age": -1}, schema)
        self.assertFalse(result.valid)

        result = validator.validate({"age": 200}, schema)
        self.assertFalse(result.valid)

        result = validator.validate({"age": 25}, schema)
        self.assertTrue(result.valid)

    def test_validate_length(self):
        validator = DataValidator()
        schema = Schema(name="test")
        schema.add_field(FieldRule(name="name", data_type=DataType.STRING,
                                   min_length=2, max_length=10))

        result = validator.validate({"name": "a"}, schema)
        self.assertFalse(result.valid)

        result = validator.validate({"name": "abc"}, schema)
        self.assertTrue(result.valid)

    def test_validate_pattern(self):
        validator = DataValidator()
        schema = Schema(name="test")
        schema.add_field(FieldRule(name="email", data_type=DataType.STRING,
                                   pattern=r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"))

        result = validator.validate({"email": "invalid"}, schema)
        self.assertFalse(result.valid)

        result = validator.validate({"email": "test@example.com"}, schema)
        self.assertTrue(result.valid)

    def test_validate_enum(self):
        validator = DataValidator()
        schema = Schema(name="test")
        schema.add_field(FieldRule(name="status", enum_values=["active", "inactive"]))

        result = validator.validate({"status": "unknown"}, schema)
        self.assertFalse(result.valid)

        result = validator.validate({"status": "active"}, schema)
        self.assertTrue(result.valid)

    def test_validate_nullable(self):
        validator = DataValidator()
        schema = Schema(name="test")
        schema.add_field(FieldRule(name="optional", required=False, nullable=True))

        result = validator.validate({"optional": None}, schema)
        self.assertTrue(result.valid)

    def test_validate_custom(self):
        validator = DataValidator()
        schema = Schema(name="test")
        schema.add_field(FieldRule(
            name="even",
            custom_validator=lambda v: v % 2 == 0,
            custom_message="Must be even",
        ))

        result = validator.validate({"even": 3}, schema)
        self.assertFalse(result.valid)

        result = validator.validate({"even": 4}, schema)
        self.assertTrue(result.valid)

    def test_validate_strict(self):
        validator = DataValidator()
        schema = Schema(name="test", strict=True)
        schema.add_field(FieldRule(name="name"))

        result = validator.validate({"name": "test", "extra": "field"}, schema)
        self.assertTrue(result.has_warnings)

    def test_schema_registration(self):
        validator = DataValidator()
        schema = Schema(name="user")
        schema.add_field(FieldRule(name="name", required=True))
        validator.register_schema(schema)

        result = validator.validate_with_schema_name({"name": "test"}, "user")
        self.assertTrue(result.valid)

        result = validator.validate_with_schema_name({}, "user")
        self.assertFalse(result.valid)

    def test_batch_validation(self):
        validator = DataValidator()
        schema = Schema(name="test")
        schema.add_field(FieldRule(name="age", data_type=DataType.INTEGER))

        data = [{"age": 25}, {"age": "invalid"}, {"age": 30}]
        results = validator.validate_batch(data, schema)

        self.assertEqual(len(results), 3)
        self.assertTrue(results[0][1].valid)
        self.assertFalse(results[1][1].valid)
        self.assertTrue(results[2][1].valid)

    def test_is_valid(self):
        validator = DataValidator()
        schema = Schema(name="test")
        schema.add_field(FieldRule(name="name", required=True))

        self.assertTrue(validator.is_valid({"name": "test"}, schema))
        self.assertFalse(validator.is_valid({}, schema))

    def test_stats(self):
        validator = DataValidator()
        validator.register_schema(Schema(name="s1"))
        validator.register_schema(Schema(name="s2"))
        stats = validator.get_stats()
        self.assertEqual(stats["schemas"], 2)

    def test_global_singleton(self):
        v1 = get_data_validator()
        v2 = get_data_validator()
        self.assertIs(v1, v2)


class TestCommonValidators(unittest.TestCase):
    """CommonValidators 测试"""

    def test_email(self):
        self.assertTrue(CommonValidators.email("test@example.com"))
        self.assertFalse(CommonValidators.email("invalid"))

    def test_phone(self):
        self.assertTrue(CommonValidators.phone("13812345678"))
        self.assertFalse(CommonValidators.phone("12345678901"))

    def test_url(self):
        self.assertTrue(CommonValidators.url("http://example.com"))
        self.assertFalse(CommonValidators.url("not-a-url"))

    def test_ipv4(self):
        self.assertTrue(CommonValidators.ipv4("192.168.1.1"))
        self.assertFalse(CommonValidators.ipv4("256.1.1.1"))

    def test_positive_number(self):
        self.assertTrue(CommonValidators.positive_number(5))
        self.assertFalse(CommonValidators.positive_number(-1))

    def test_non_empty_string(self):
        self.assertTrue(CommonValidators.non_empty_string("hello"))
        self.assertFalse(CommonValidators.non_empty_string(""))


# ============================================================
# 阶段352: DataCleaner 测试
# ============================================================

class TestNullHandler(unittest.TestCase):
    """NullHandler 测试"""

    def test_is_null(self):
        self.assertTrue(NullHandler.is_null(None))
        self.assertTrue(NullHandler.is_null(""))
        self.assertTrue(NullHandler.is_null("null"))
        self.assertTrue(NullHandler.is_null("NULL"))
        self.assertFalse(NullHandler.is_null("value"))
        self.assertFalse(NullHandler.is_null(0))

    def test_fill_value_mean(self):
        values = [1, 2, 3, 4, 5, None]
        fill = NullHandler.fill_value(values, NullAction.FILL_MEAN)
        self.assertEqual(fill, 3.0)

    def test_fill_value_median(self):
        values = [1, 2, 3, 4, 5, None]
        fill = NullHandler.fill_value(values, NullAction.FILL_MEDIAN)
        self.assertEqual(fill, 3)

    def test_fill_value_mode(self):
        values = [1, 2, 2, 3, None]
        fill = NullHandler.fill_value(values, NullAction.FILL_MODE)
        self.assertEqual(fill, 2)


class TestStringNormalizer(unittest.TestCase):
    """StringNormalizer 测试"""

    def test_normalize(self):
        self.assertEqual(StringNormalizer.normalize("  hello  "), "hello")

    def test_case_convert(self):
        self.assertEqual(StringNormalizer.case_convert("hello", CaseAction.UPPER), "HELLO")
        self.assertEqual(StringNormalizer.case_convert("HELLO", CaseAction.LOWER), "hello")
        self.assertEqual(StringNormalizer.case_convert("hello world", CaseAction.TITLE), "Hello World")

    def test_remove_extra_whitespace(self):
        self.assertEqual(StringNormalizer.remove_extra_whitespace("a   b  c"), "a b c")

    def test_remove_special_chars(self):
        result = StringNormalizer.remove_special_chars("hello@world!")
        self.assertNotIn("@", result)
        self.assertNotIn("!", result)


class TestDeduplicator(unittest.TestCase):
    """Deduplicator 测试"""

    def test_dedup_exact(self):
        data = [1, 2, 2, 3, 3, 3]
        result, removed = Deduplicator.dedup_exact(data)
        self.assertEqual(result, [1, 2, 3])
        self.assertEqual(removed, 3)

    def test_dedup_by_key(self):
        data = [{"id": 1, "v": "a"}, {"id": 1, "v": "b"}, {"id": 2, "v": "c"}]
        result, removed = Deduplicator.dedup_by_key(data, ["id"])
        self.assertEqual(len(result), 2)
        self.assertEqual(removed, 1)

    def test_dedup_list(self):
        values = [1, 2, 2, 3]
        result, removed = Deduplicator.dedup_list(values)
        self.assertEqual(result, [1, 2, 3])
        self.assertEqual(removed, 1)


class TestOutlierDetector(unittest.TestCase):
    """OutlierDetector 测试"""

    def test_detect_iqr(self):
        values = [1, 2, 3, 4, 5, 100]  # 100 is outlier
        outliers, lower, upper = OutlierDetector.detect_iqr(values)
        self.assertTrue(len(outliers) > 0)

    def test_detect_zscore(self):
        values = [1, 2, 3, 4, 5, 10000]  # 10000 is extreme outlier
        outliers = OutlierDetector.detect_zscore(values, threshold=2.0)
        self.assertTrue(len(outliers) > 0)


class TestDataCleaner(unittest.TestCase):
    """DataCleaner 核心测试"""

    def test_clean_nulls_remove(self):
        cleaner = DataCleaner()
        data = [{"name": "a"}, {"name": None}, {"name": "b"}]
        result = cleaner.clean_nulls(data, "name", NullAction.REMOVE)
        self.assertEqual(len(result.data), 2)
        self.assertEqual(result.stats.nulls_removed, 1)

    def test_clean_nulls_fill(self):
        cleaner = DataCleaner()
        data = [{"name": "a"}, {"name": None}, {"name": "b"}]
        result = cleaner.clean_nulls(data, "name", NullAction.FILL_DEFAULT, default="unknown")
        self.assertEqual(len(result.data), 3)
        self.assertEqual(result.data[1]["name"], "unknown")

    def test_normalize_string(self):
        cleaner = DataCleaner()
        data = [{"name": "  HELLO  "}]
        result = cleaner.normalize_string(data, "name", case=CaseAction.LOWER)
        self.assertEqual(result.data[0]["name"], "hello")

    def test_deduplicate(self):
        cleaner = DataCleaner()
        data = [{"id": 1}, {"id": 1}, {"id": 2}]
        result = cleaner.deduplicate(data, DedupStrategy.KEY_BASED, keys=["id"])
        self.assertEqual(len(result.data), 2)
        self.assertEqual(result.stats.duplicates_removed, 1)

    def test_handle_outliers(self):
        cleaner = DataCleaner()
        # Use more data points for reliable IQR detection
        data = [{"value": 10}, {"value": 11}, {"value": 12}, {"value": 13},
                {"value": 14}, {"value": 15}, {"value": 1000}]  # 1000 is extreme outlier
        result = cleaner.handle_outliers(data, "value", method="iqr", action="remove", factor=1.5)
        # 1000 should be detected as outlier
        self.assertLess(len(result.data), len(data))

    def test_clean_batch(self):
        cleaner = DataCleaner()
        data = [{"name": None}, {"name": "  test  "}]
        operations = [
            {"type": "null", "field": "name", "action": "fill", "default": "unknown"},
            {"type": "normalize", "field": "name", "case": "lower"},
        ]
        result = cleaner.clean_batch(data, operations)
        self.assertEqual(result.data[0]["name"], "unknown")
        self.assertEqual(result.data[1]["name"], "test")

    def test_stats(self):
        cleaner = DataCleaner()
        cleaner.register_cleaner("custom", lambda x: x)
        stats = cleaner.get_stats()
        self.assertEqual(stats["custom_cleaners"], 1)

    def test_global_singleton(self):
        c1 = get_data_cleaner()
        c2 = get_data_cleaner()
        self.assertIs(c1, c2)


# ============================================================
# 阶段353: DataTransformer 测试
# ============================================================

class TestFormatConverter(unittest.TestCase):
    """FormatConverter 测试"""

    def test_to_from_json(self):
        data = {"name": "test", "value": 123}
        json_str = FormatConverter.to_json(data)
        parsed = FormatConverter.from_json(json_str)
        self.assertEqual(parsed, data)

    def test_to_from_csv(self):
        data = [{"name": "a", "value": 1}, {"name": "b", "value": 2}]
        csv_str = FormatConverter.to_csv(data)
        parsed = FormatConverter.from_csv(csv_str)
        self.assertEqual(len(parsed), 2)

    def test_to_xml(self):
        data = {"name": "test"}
        xml = FormatConverter.to_xml(data)
        self.assertIn("<name>test</name>", xml)

    def test_to_text(self):
        data = {"name": "test", "value": 123}
        text = FormatConverter.to_text(data)
        self.assertIn("name: test", text)


class TestEncodingConverter(unittest.TestCase):
    """EncodingConverter 测试"""

    def test_encode_decode(self):
        text = "hello"
        encoded = EncodingConverter.encode(text, EncodingType.UTF8)
        decoded = EncodingConverter.decode(encoded, EncodingType.UTF8)
        self.assertEqual(decoded, text)

    def test_base64(self):
        text = "hello"
        encoded = EncodingConverter.encode(text, EncodingType.BASE64)
        decoded = EncodingConverter.decode(encoded, EncodingType.BASE64)
        self.assertEqual(decoded, text)

    def test_detect_encoding(self):
        data = "hello".encode("utf-8")
        encoding = EncodingConverter.detect_encoding(data)
        self.assertEqual(encoding, "utf-8")


class TestFieldMapper(unittest.TestCase):
    """FieldMapper 测试"""

    def test_rename_fields(self):
        data = {"old_name": "test"}
        result = FieldMapper.rename_fields(data, {"old_name": "new_name"})
        self.assertIn("new_name", result)
        self.assertNotIn("old_name", result)

    def test_select_fields(self):
        data = {"a": 1, "b": 2, "c": 3}
        result = FieldMapper.select_fields(data, ["a", "c"])
        self.assertEqual(result, {"a": 1, "c": 3})

    def test_exclude_fields(self):
        data = {"a": 1, "b": 2, "c": 3}
        result = FieldMapper.exclude_fields(data, ["b"])
        self.assertEqual(result, {"a": 1, "c": 3})

    def test_flatten(self):
        data = {"a": {"b": {"c": 1}}}
        result = FieldMapper.flatten(data)
        self.assertEqual(result, {"a.b.c": 1})

    def test_unflatten(self):
        data = {"a.b.c": 1}
        result = FieldMapper.unflatten(data)
        self.assertEqual(result, {"a": {"b": {"c": 1}}})


class TestTypeConverter(unittest.TestCase):
    """TypeConverter 测试"""

    def test_to_string(self):
        self.assertEqual(TypeConverter.to_string(123), "123")
        self.assertEqual(TypeConverter.to_string([1, 2]), "[1, 2]")

    def test_to_int(self):
        self.assertEqual(TypeConverter.to_int("123"), 123)
        self.assertEqual(TypeConverter.to_int("invalid", default=0), 0)

    def test_to_float(self):
        self.assertEqual(TypeConverter.to_float("123.5"), 123.5)

    def test_to_bool(self):
        self.assertTrue(TypeConverter.to_bool("true"))
        self.assertTrue(TypeConverter.to_bool("yes"))
        self.assertFalse(TypeConverter.to_bool("false"))

    def test_to_list(self):
        self.assertEqual(TypeConverter.to_list("a,b,c"), ["a", "b", "c"])
        self.assertEqual(TypeConverter.to_list([1, 2]), [1, 2])

    def test_to_date(self):
        result = TypeConverter.to_date("2024-01-15")
        self.assertEqual(result, date(2024, 1, 15))


class TestDataTransformer(unittest.TestCase):
    """DataTransformer 核心测试"""

    def test_convert_format_json(self):
        transformer = DataTransformer()
        data = {"name": "test"}
        result = transformer.convert_format(data, FormatType.DICT, FormatType.JSON)
        self.assertTrue(result.stats.transformed_records > 0)
        self.assertIn("name", result.data)

    def test_map_fields(self):
        transformer = DataTransformer()
        data = {"old": "value"}
        result = transformer.map_fields(data, {"old": "new"})
        self.assertIn("new", result.data)

    def test_select_fields(self):
        transformer = DataTransformer()
        data = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
        result = transformer.select_fields(data, ["a"])
        self.assertEqual(result.data, [{"a": 1}, {"a": 3}])

    def test_flatten_data(self):
        transformer = DataTransformer()
        data = {"a": {"b": 1}}
        result = transformer.flatten_data(data)
        self.assertEqual(result.data, {"a.b": 1})

    def test_convert_field_type(self):
        transformer = DataTransformer()
        data = [{"value": "123"}, {"value": "456"}]
        result = transformer.convert_field_type(data, "value", "int")
        self.assertEqual(result.data[0]["value"], 123)

    def test_transform_batch(self):
        transformer = DataTransformer()
        data = [{"old": "1"}, {"old": "2"}]
        operations = [
            {"type": "map", "mapping": {"old": "new"}},
            {"type": "convert", "field": "new", "target_type": "int"},
        ]
        result = transformer.transform_batch(data, operations)
        self.assertEqual(result.data[0]["new"], 1)

    def test_stats(self):
        transformer = DataTransformer()
        transformer.register_transformer("custom", lambda x: x)
        stats = transformer.get_stats()
        self.assertEqual(stats["custom_transformers"], 1)

    def test_global_singleton(self):
        t1 = get_data_transformer()
        t2 = get_data_transformer()
        self.assertIs(t1, t2)


# ============================================================
# 阶段354: DataQualityAssessor 测试
# ============================================================

class TestCompletenessAssessor(unittest.TestCase):
    """CompletenessAssessor 测试"""

    def test_assess_field_completeness(self):
        data = [{"name": "a"}, {"name": None}, {"name": "b"}]
        rate, non_null, total = CompletenessAssessor.assess_field_completeness(data, "name")
        self.assertAlmostEqual(rate, 100 * 2 / 3, places=4)
        self.assertEqual(non_null, 2)
        self.assertEqual(total, 3)

    def test_assess_record_completeness(self):
        data = [{"a": 1, "b": 2}, {"a": 1}, {"a": 1, "b": 2}]
        rate, complete, total = CompletenessAssessor.assess_record_completeness(data, ["a", "b"])
        self.assertEqual(complete, 2)


class TestConsistencyAssessor(unittest.TestCase):
    """ConsistencyAssessor 测试"""

    def test_assess_type_consistency(self):
        data = [{"v": 1}, {"v": 2}, {"v": "str"}]
        rate, types = ConsistencyAssessor.assess_type_consistency(data, "v")
        self.assertLess(rate, 100)
        self.assertIn("int", types)
        self.assertIn("str", types)

    def test_assess_format_consistency(self):
        import re
        data = [{"email": "a@b.com"}, {"email": "invalid"}]
        rate, matched, total = ConsistencyAssessor.assess_format_consistency(
            data, "email", r"^[^@]+@[^@]+\.[^@]+$"
        )
        self.assertEqual(matched, 1)


class TestAccuracyAssessor(unittest.TestCase):
    """AccuracyAssessor 测试"""

    def test_assess_range_accuracy(self):
        data = [{"age": 25}, {"age": 200}, {"age": 30}]
        rate, accurate, total = AccuracyAssessor.assess_range_accuracy(data, "age", 0, 100)
        self.assertEqual(accurate, 2)

    def test_assess_custom_accuracy(self):
        data = [{"v": 2}, {"v": 4}, {"v": 5}]
        rate, passed, total = AccuracyAssessor.assess_custom_accuracy(
            data, lambda r: r["v"] % 2 == 0
        )
        self.assertEqual(passed, 2)


class TestTimelinessAssessor(unittest.TestCase):
    """TimelinessAssessor 测试"""

    def test_assess_freshness(self):
        now = datetime.now()
        data = [
            {"ts": (now - timedelta(days=1)).isoformat()},
            {"ts": (now - timedelta(days=10)).isoformat()},
        ]
        rate, fresh, total = TimelinessAssessor.assess_freshness(
            data, "ts", timedelta(days=5)
        )
        self.assertEqual(fresh, 1)


class TestUniquenessAssessor(unittest.TestCase):
    """UniquenessAssessor 测试"""

    def test_assess_field_uniqueness(self):
        data = [{"id": 1}, {"id": 1}, {"id": 2}]
        rate, unique, total = UniquenessAssessor.assess_field_uniqueness(data, "id")
        self.assertEqual(unique, 2)


class TestDataQualityAssessor(unittest.TestCase):
    """DataQualityAssessor 核心测试"""

    def test_assess_completeness(self):
        assessor = DataQualityAssessor()
        data = [{"name": "a"}, {"name": None}, {"name": "b"}]
        score = assessor.assess_completeness(data)
        self.assertLess(score.score, 100)
        self.assertEqual(score.dimension, QualityDimension.COMPLETENESS)

    def test_assess_consistency(self):
        assessor = DataQualityAssessor()
        data = [{"v": 1}, {"v": "str"}]
        score = assessor.assess_consistency(data)
        self.assertLess(score.score, 100)

    def test_assess_accuracy(self):
        assessor = DataQualityAssessor()
        data = [{"age": 25}, {"age": 200}]
        score = assessor.assess_accuracy(data, range_rules={"age": (0, 100)})
        self.assertLess(score.score, 100)

    def test_assess_timeliness(self):
        assessor = DataQualityAssessor()
        now = datetime.now()
        data = [{"ts": (now - timedelta(days=1)).isoformat()}]
        score = assessor.assess_timeliness(data, "ts", timedelta(days=5))
        self.assertGreater(score.score, 50)

    def test_assess_uniqueness(self):
        assessor = DataQualityAssessor()
        data = [{"id": 1}, {"id": 1}]
        score = assessor.assess_uniqueness(data, unique_fields=["id"])
        self.assertLess(score.score, 100)

    def test_assess_comprehensive(self):
        assessor = DataQualityAssessor()
        data = [
            {"id": 1, "name": "a", "age": 25},
            {"id": 2, "name": "b", "age": 30},
        ]
        report = assessor.assess(data, {
            "required_fields": ["id", "name"],
            "unique_fields": ["id"],
        })
        self.assertEqual(report.total_records, 2)
        self.assertGreater(report.overall_score, 80)
        self.assertIn("completeness", report.dimension_scores)

    def test_set_weights(self):
        assessor = DataQualityAssessor()
        assessor.set_weights({
            QualityDimension.COMPLETENESS: 0.5,
            QualityDimension.ACCURACY: 0.5,
        })
        weights = assessor.get_weights()
        self.assertAlmostEqual(weights[QualityDimension.COMPLETENESS], 0.5)

    def test_global_singleton(self):
        a1 = get_quality_assessor()
        a2 = get_quality_assessor()
        self.assertIs(a1, a2)


class TestQualityLevel(unittest.TestCase):
    """QualityLevel 测试"""

    def test_dimension_score_level(self):
        score = DimensionScore(dimension=QualityDimension.COMPLETENESS, score=95)
        self.assertEqual(score.level, QualityLevel.EXCELLENT)

        score = DimensionScore(dimension=QualityDimension.COMPLETENESS, score=85)
        self.assertEqual(score.level, QualityLevel.GOOD)

        score = DimensionScore(dimension=QualityDimension.COMPLETENESS, score=70)
        self.assertEqual(score.level, QualityLevel.FAIR)

        score = DimensionScore(dimension=QualityDimension.COMPLETENESS, score=50)
        self.assertEqual(score.level, QualityLevel.POOR)

        score = DimensionScore(dimension=QualityDimension.COMPLETENESS, score=30)
        self.assertEqual(score.level, QualityLevel.CRITICAL)


# ============================================================
# 阶段355: DataRepairEngine 测试
# ============================================================

class TestRepairRule(unittest.TestCase):
    """RepairRule 测试"""

    def test_basic_rule(self):
        rule = RepairRule(
            name="test",
            field="value",
            condition=lambda v: v is None,
            action=RepairAction.DEFAULT,
            value=0,
        )
        self.assertEqual(rule.name, "test")
        self.assertTrue(rule.enabled)


class TestBuiltinRules(unittest.TestCase):
    """BuiltinRules 测试"""

    def test_null_to_default(self):
        rule = BuiltinRules.null_to_default("name", "unknown")
        self.assertTrue(rule.condition(None))
        self.assertFalse(rule.condition("value"))

    def test_trim_whitespace(self):
        rule = BuiltinRules.trim_whitespace("name")
        self.assertTrue(rule.condition("  hello  "))
        self.assertFalse(rule.condition("hello"))

    def test_normalize_case(self):
        rule = BuiltinRules.normalize_case("name", "lower")
        result = rule.transform("HELLO")
        self.assertEqual(result, "hello")

    def test_clamp_value(self):
        rule = BuiltinRules.clamp_value("value", 0, 100)
        self.assertTrue(rule.condition(150))
        self.assertEqual(rule.transform(150), 100)


class TestDataRepairEngine(unittest.TestCase):
    """DataRepairEngine 核心测试"""

    def test_add_remove_rule(self):
        engine = DataRepairEngine()
        rule = RepairRule(
            name="test",
            field="value",
            condition=lambda v: v is None,
            action=RepairAction.DEFAULT,
            value=0,
        )
        engine.add_rule(rule)
        self.assertIsNotNone(engine.get_rule("test"))
        self.assertTrue(engine.remove_rule("test"))
        self.assertFalse(engine.remove_rule("nonexistent"))

    def test_enable_disable_rule(self):
        engine = DataRepairEngine()
        engine.add_rule(RepairRule(
            name="test",
            field="value",
            condition=lambda v: True,
            action=RepairAction.DEFAULT,
        ))
        self.assertTrue(engine.disable_rule("test"))
        self.assertTrue(engine.enable_rule("test"))

    def test_repair_record(self):
        engine = DataRepairEngine()
        rule = BuiltinRules.null_to_default("name", "unknown")
        record = {"name": None}
        repaired, repairs = engine.repair_record(record, 0, [rule])
        self.assertEqual(repaired["name"], "unknown")
        self.assertEqual(len(repairs), 1)

    def test_repair_batch(self):
        engine = DataRepairEngine()
        engine.add_rule(BuiltinRules.null_to_default("name", "unknown"))
        data = [{"name": None}, {"name": "test"}]
        result = engine.repair(data)
        self.assertEqual(result.data[0]["name"], "unknown")
        self.assertEqual(result.stats.total_repairs, 1)

    def test_repair_field(self):
        engine = DataRepairEngine()
        data = [{"value": None}, {"value": 10}]
        result = engine.repair_field(
            data, "value", RepairAction.DEFAULT, value=0,
            condition=lambda v: v is None,
        )
        self.assertEqual(result.data[0]["value"], 0)

    def test_fill_nulls(self):
        engine = DataRepairEngine()
        data = [{"name": None}, {"name": "test"}]
        result = engine.fill_nulls(data, "name", "unknown")
        self.assertEqual(result.data[0]["name"], "unknown")

    def test_trim_strings(self):
        engine = DataRepairEngine()
        data = [{"name": "  hello  "}]
        result = engine.trim_strings(data)
        self.assertEqual(result.data[0]["name"], "hello")

    def test_normalize_case(self):
        engine = DataRepairEngine()
        data = [{"name": "HELLO"}]
        result = engine.normalize_case(data, "name", "lower")
        self.assertEqual(result.data[0]["name"], "hello")

    def test_clamp_values(self):
        engine = DataRepairEngine()
        data = [{"value": 150}]
        result = engine.clamp_values(data, "value", 0, 100)
        self.assertEqual(result.data[0]["value"], 100)

    def test_preview(self):
        engine = DataRepairEngine()
        engine.add_rule(BuiltinRules.null_to_default("name", "unknown"))
        data = [{"name": None}]
        preview = engine.preview(data)
        self.assertEqual(len(preview), 1)

    def test_history(self):
        engine = DataRepairEngine()
        engine.add_rule(BuiltinRules.null_to_default("name", "unknown"))
        data = [{"name": None}]
        engine.repair(data)
        history = engine.get_history()
        self.assertEqual(len(history), 1)
        count = engine.clear_history()
        self.assertEqual(count, 1)

    def test_list_rules(self):
        engine = DataRepairEngine()
        engine.add_rule(BuiltinRules.null_to_default("name", "unknown"))
        rules = engine.list_rules()
        self.assertEqual(len(rules), 1)

    def test_stats(self):
        engine = DataRepairEngine()
        engine.add_rule(RepairRule(
            name="test",
            field="value",
            condition=lambda v: True,
            action=RepairAction.DEFAULT,
        ))
        stats = engine.get_stats()
        self.assertEqual(stats["rules"], 1)

    def test_global_singleton(self):
        e1 = get_repair_engine()
        e2 = get_repair_engine()
        self.assertIs(e1, e2)


class TestRepairStats(unittest.TestCase):
    """RepairStats 测试"""

    def test_to_dict(self):
        stats = RepairStats(
            total_records=10,
            repaired_records=5,
            total_repairs=7,
            by_rule={"rule1": 3, "rule2": 4},
        )
        d = stats.to_dict()
        self.assertEqual(d["total_records"], 10)
        self.assertEqual(d["repaired_records"], 5)
        self.assertEqual(d["total_repairs"], 7)


if __name__ == "__main__":
    unittest.main(verbosity=2)
