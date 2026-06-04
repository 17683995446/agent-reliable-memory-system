"""
Phase 37 Validation Tests - Pipeline Modules (Stages 386-390)

Tests for:
- data_source.py (Stage 386)
- data_transformer.py (Stage 387)
- data_sink.py (Stage 388)
- pipeline_orchestrator.py (Stage 389)
- pipeline_monitor.py (Stage 390)
"""

import unittest
import time

from src.pipeline import (
    # Data Source
    SourceType, DataFormat, ReadMode, DataSource, DataRecord, DataSourceManager,
    get_data_source_manager, reset_data_source_manager,
    # Data Transformer
    TransformType, TransformRule, TransformResult, DataTransformer,
    get_data_transformer, reset_data_transformer,
    # Data Sink
    SinkType, WriteMode, DataSink, WriteResult, DataSinkManager,
    get_data_sink_manager, reset_data_sink_manager,
    # Pipeline Orchestrator
    PipelineStatus, StageStatus, PipelineStage, Pipeline, PipelineOrchestrator,
    get_pipeline_orchestrator, reset_pipeline_orchestrator,
    # Pipeline Monitor
    MetricType, AlertLevel, PipelineMetric, PipelineAlert, PipelineMonitor,
    get_pipeline_monitor, reset_pipeline_monitor
)


class TestDataSourceManager(unittest.TestCase):
    """Test DataSourceManager module (Stage 386)"""

    def setUp(self):
        reset_data_source_manager()
        self.manager = get_data_source_manager()

    def test_register_unregister(self):
        source_id = self.manager.register_source(
            SourceType.MEMORY, "test", DataFormat.JSON, ReadMode.BATCH
        )
        self.assertIsNotNone(source_id)
        result = self.manager.unregister_source(source_id)
        self.assertTrue(result)

    def test_get_source(self):
        source_id = self.manager.register_source(
            SourceType.MEMORY, "test", DataFormat.JSON, ReadMode.BATCH
        )
        source = self.manager.get_source(source_id)
        self.assertIsNotNone(source)
        self.assertEqual(source.source_id, source_id)

    def test_read_batch_memory(self):
        source_id = self.manager.register_source(
            SourceType.MEMORY, "test", DataFormat.JSON, ReadMode.BATCH,
            metadata={"data": [{"id": 1}, {"id": 2}, {"id": 3}]}
        )
        records = self.manager.read_batch(source_id, batch_size=2)
        self.assertEqual(len(records), 2)

    def test_poll_source(self):
        source_id = self.manager.register_source(
            SourceType.MEMORY, "test", DataFormat.JSON, ReadMode.POLL,
            metadata={"data": [{"id": 1}]}
        )
        record = self.manager.poll_source(source_id)
        self.assertIsNotNone(record)

    def test_get_all_sources(self):
        self.manager.register_source(SourceType.MEMORY, "test1", DataFormat.JSON, ReadMode.BATCH)
        self.manager.register_source(SourceType.FILE, "test2", DataFormat.CSV, ReadMode.STREAM)
        sources = self.manager.get_all_sources()
        self.assertEqual(len(sources), 2)

    def test_get_sources_by_type(self):
        self.manager.register_source(SourceType.MEMORY, "test", DataFormat.JSON, ReadMode.BATCH)
        sources = self.manager.get_sources_by_type(SourceType.MEMORY)
        self.assertEqual(len(sources), 1)

    def test_health_check(self):
        source_id = self.manager.register_source(
            SourceType.MEMORY, "test", DataFormat.JSON, ReadMode.BATCH
        )
        result = self.manager.health_check(source_id)
        self.assertIsInstance(result, bool)

    def test_global_singleton(self):
        manager2 = get_data_source_manager()
        self.assertIs(self.manager, manager2)


class TestDataTransformer(unittest.TestCase):
    """Test DataTransformer module (Stage 387)"""

    def setUp(self):
        reset_data_transformer()
        self.transformer = get_data_transformer()

    def test_add_remove_rule(self):
        rule = TransformRule(
            rule_id="filter_test",
            transform_type=TransformType.FILTER,
            condition="x > 5",
            params={},
            priority=1,
            enabled=True
        )
        result = self.transformer.add_rule(rule)
        self.assertTrue(result)
        result = self.transformer.remove_rule("filter_test")
        self.assertTrue(result)

    def test_apply_filter(self):
        rule = TransformRule(
            rule_id="filter_gt_5",
            transform_type=TransformType.FILTER,
            condition="lambda r: r['value'] > 5",
            params={"field": "value"},
            priority=1,
            enabled=True
        )
        self.transformer.add_rule(rule)
        data = [{"value": 3}, {"value": 7}, {"value": 10}]
        result = self.transformer.apply_transform(data, "filter_gt_5")
        self.assertTrue(result.success)
        self.assertEqual(len(result.data), 2)

    def test_apply_map(self):
        rule = TransformRule(
            rule_id="map_double",
            transform_type=TransformType.MAP,
            condition="",
            params={"expression": "x * 2"},
            priority=1,
            enabled=True
        )
        self.transformer.add_rule(rule)
        data = [1, 2, 3]
        result = self.transformer.apply_transform(data, "map_double")
        self.assertTrue(result.success)

    def test_create_pipeline(self):
        rule1 = TransformRule(
            rule_id="r1", transform_type=TransformType.FILTER,
            condition="x > 0", params={}, priority=1, enabled=True
        )
        rule2 = TransformRule(
            rule_id="r2", transform_type=TransformType.MAP,
            condition="", params={}, priority=2, enabled=True
        )
        self.transformer.add_rule(rule1)
        self.transformer.add_rule(rule2)
        result = self.transformer.create_pipeline("test_pipeline", ["r1", "r2"])
        self.assertTrue(result)
        pipelines = self.transformer.get_pipelines()
        self.assertIn("test_pipeline", pipelines)

    def test_enable_disable_rule(self):
        rule = TransformRule(
            rule_id="test_rule", transform_type=TransformType.FILTER,
            condition="True", params={}, priority=1, enabled=True
        )
        self.transformer.add_rule(rule)
        self.transformer.disable_rule("test_rule")
        self.transformer.enable_rule("test_rule")
        fetched = self.transformer.get_rule("test_rule")
        self.assertTrue(fetched.enabled)

    def test_global_singleton(self):
        transformer2 = get_data_transformer()
        self.assertIs(self.transformer, transformer2)


class TestDataSinkManager(unittest.TestCase):
    """Test DataSinkManager module (Stage 388)"""

    def setUp(self):
        reset_data_sink_manager()
        self.manager = get_data_sink_manager()

    def test_register_unregister(self):
        sink_id = self.manager.register_sink(
            SinkType.MEMORY, "test", DataFormat.JSON, WriteMode.APPEND
        )
        self.assertIsNotNone(sink_id)
        result = self.manager.unregister_sink(sink_id)
        self.assertTrue(result)

    def test_write(self):
        sink_id = self.manager.register_sink(
            SinkType.MEMORY, "test", DataFormat.JSON, WriteMode.APPEND
        )
        result = self.manager.write(sink_id, {"key": "value"})
        self.assertTrue(result.success)
        self.assertEqual(result.records_written, 1)

    def test_write_batch(self):
        sink_id = self.manager.register_sink(
            SinkType.MEMORY, "test", DataFormat.JSON, WriteMode.APPEND
        )
        records = [{"id": 1}, {"id": 2}, {"id": 3}]
        result = self.manager.write_batch(sink_id, records)
        self.assertTrue(result.success)
        self.assertEqual(result.records_written, 3)

    def test_flush(self):
        sink_id = self.manager.register_sink(
            SinkType.MEMORY, "test", DataFormat.JSON, WriteMode.APPEND
        )
        self.manager.write(sink_id, {"key": "value"})
        result = self.manager.flush(sink_id)
        self.assertTrue(result.success)

    def test_get_all_sinks(self):
        self.manager.register_sink(SinkType.MEMORY, "test1", DataFormat.JSON, WriteMode.APPEND)
        self.manager.register_sink(SinkType.CONSOLE, "test2", DataFormat.JSON, WriteMode.OVERWRITE)
        sinks = self.manager.get_all_sinks()
        self.assertEqual(len(sinks), 2)

    def test_health_check(self):
        sink_id = self.manager.register_sink(
            SinkType.MEMORY, "test", DataFormat.JSON, WriteMode.APPEND
        )
        result = self.manager.health_check(sink_id)
        self.assertIsInstance(result, bool)

    def test_global_singleton(self):
        manager2 = get_data_sink_manager()
        self.assertIs(self.manager, manager2)


class TestPipelineOrchestrator(unittest.TestCase):
    """Test PipelineOrchestrator module (Stage 389)"""

    def setUp(self):
        reset_pipeline_orchestrator()
        self.orchestrator = get_pipeline_orchestrator()

    def test_create_delete_pipeline(self):
        pipeline_id = self.orchestrator.create_pipeline(
            "test_pipeline", "source_1",
            [{"name": "stage1", "transform_rule_id": "rule1", "sink_id": "sink1", "dependencies": []}]
        )
        self.assertIsNotNone(pipeline_id)
        result = self.orchestrator.delete_pipeline(pipeline_id)
        self.assertTrue(result)

    def test_get_pipeline(self):
        pipeline_id = self.orchestrator.create_pipeline(
            "test_pipeline", "source_1",
            [{"name": "stage1", "transform_rule_id": "rule1", "sink_id": "sink1", "dependencies": []}]
        )
        pipeline = self.orchestrator.get_pipeline(pipeline_id)
        self.assertIsNotNone(pipeline)
        self.assertEqual(pipeline.name, "test_pipeline")

    def test_pipeline_lifecycle(self):
        pipeline_id = self.orchestrator.create_pipeline(
            "test_pipeline", "source_1",
            [{"name": "stage1", "transform_rule_id": "rule1", "sink_id": "sink1", "dependencies": []}]
        )
        self.assertEqual(self.orchestrator.get_pipeline_status(pipeline_id), PipelineStatus.CREATED)

    def test_get_all_pipelines(self):
        self.orchestrator.create_pipeline(
            "p1", "s1",
            [{"name": "stage1", "transform_rule_id": "rule1", "sink_id": "sink1", "dependencies": []}]
        )
        self.orchestrator.create_pipeline(
            "p2", "s2",
            [{"name": "stage1", "transform_rule_id": "rule2", "sink_id": "sink2", "dependencies": []}]
        )
        pipelines = self.orchestrator.get_all_pipelines()
        self.assertEqual(len(pipelines), 2)

    def test_get_pipeline_statistics(self):
        pipeline_id = self.orchestrator.create_pipeline(
            "test_pipeline", "source_1",
            [{"name": "stage1", "transform_rule_id": "rule1", "sink_id": "sink1", "dependencies": []}]
        )
        stats = self.orchestrator.get_pipeline_statistics(pipeline_id)
        self.assertIn("pipeline_id", stats)

    def test_global_singleton(self):
        orchestrator2 = get_pipeline_orchestrator()
        self.assertIs(self.orchestrator, orchestrator2)


class TestPipelineMonitor(unittest.TestCase):
    """Test PipelineMonitor module (Stage 390)"""

    def setUp(self):
        reset_pipeline_monitor()
        self.monitor = get_pipeline_monitor()

    def test_record_metric(self):
        metric_id = self.monitor.record_metric("pipeline_1", MetricType.THROUGHPUT, 100.0)
        self.assertIsNotNone(metric_id)

    def test_get_metrics(self):
        self.monitor.record_metric("pipeline_1", MetricType.THROUGHPUT, 100.0)
        self.monitor.record_metric("pipeline_1", MetricType.THROUGHPUT, 200.0)
        metrics = self.monitor.get_metrics("pipeline_1", MetricType.THROUGHPUT)
        self.assertEqual(len(metrics), 2)

    def test_get_latest_metric(self):
        self.monitor.record_metric("pipeline_1", MetricType.LATENCY, 50.0)
        latest = self.monitor.get_latest_metric("pipeline_1", MetricType.LATENCY)
        self.assertIsNotNone(latest)
        self.assertEqual(latest.value, 50.0)

    def test_set_threshold_and_alert(self):
        self.monitor.set_threshold(MetricType.ERROR_RATE, 0.05, 0.10)
        self.monitor.record_metric("pipeline_1", MetricType.ERROR_RATE, 0.15)
        alerts = self.monitor.check_alerts("pipeline_1")
        self.assertGreater(len(alerts), 0)

    def test_acknowledge_alert(self):
        self.monitor.set_threshold(MetricType.ERROR_RATE, 0.05, 0.10)
        self.monitor.record_metric("pipeline_1", MetricType.ERROR_RATE, 0.15)
        alerts = self.monitor.check_alerts("pipeline_1")
        alert_id = alerts[0].alert_id
        result = self.monitor.acknowledge_alert(alert_id)
        self.assertTrue(result)

    def test_get_health_score(self):
        self.monitor.record_metric("pipeline_1", MetricType.THROUGHPUT, 100.0)
        score = self.monitor.get_health_score("pipeline_1")
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 100.0)

    def test_get_statistics(self):
        self.monitor.record_metric("pipeline_1", MetricType.THROUGHPUT, 100.0)
        stats = self.monitor.get_statistics("pipeline_1")
        self.assertIn("total_metrics", stats)

    def test_global_singleton(self):
        monitor2 = get_pipeline_monitor()
        self.assertIs(self.monitor, monitor2)


class TestDataStructures(unittest.TestCase):
    """Test all data structures and enums"""

    def test_source_type_enum(self):
        self.assertEqual(len(SourceType), 6)
        self.assertIn(SourceType.FILE, list(SourceType))

    def test_data_format_enum(self):
        self.assertEqual(len(DataFormat), 5)
        self.assertIn(DataFormat.JSON, list(DataFormat))

    def test_read_mode_enum(self):
        self.assertEqual(len(ReadMode), 3)
        self.assertIn(ReadMode.BATCH, list(ReadMode))

    def test_transform_type_enum(self):
        self.assertEqual(len(TransformType), 8)
        self.assertIn(TransformType.FILTER, list(TransformType))

    def test_sink_type_enum(self):
        self.assertEqual(len(SinkType), 6)
        self.assertIn(SinkType.FILE, list(SinkType))

    def test_write_mode_enum(self):
        self.assertEqual(len(WriteMode), 3)
        self.assertIn(WriteMode.APPEND, list(WriteMode))

    def test_pipeline_status_enum(self):
        self.assertEqual(len(PipelineStatus), 6)
        self.assertIn(PipelineStatus.RUNNING, list(PipelineStatus))

    def test_stage_status_enum(self):
        self.assertEqual(len(StageStatus), 5)
        self.assertIn(StageStatus.COMPLETED, list(StageStatus))

    def test_metric_type_enum(self):
        self.assertEqual(len(MetricType), 5)
        self.assertIn(MetricType.THROUGHPUT, list(MetricType))

    def test_alert_level_enum(self):
        self.assertEqual(len(AlertLevel), 3)
        self.assertIn(AlertLevel.CRITICAL, list(AlertLevel))


if __name__ == '__main__':
    unittest.main()
