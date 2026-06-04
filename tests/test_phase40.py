"""
Phase 40 Validation Tests - ML Integration Modules (Stages 401-405)

Tests for:
- feature_engineering.py (Stage 401)
- model_registry.py (Stage 402)
- training_orchestrator.py (Stage 403)
- inference_server.py (Stage 404)
- model_monitor.py (Stage 405)
"""

import unittest
import time

from src.ml_integration import (
    # Feature Engineering
    TransformType, FeatureType, FeatureSpec, TransformedFeature, FeatureEngineer,
    get_feature_engineer, reset_feature_engineer,
    # Model Registry
    ModelStatus, ModelType, ModelArtifact, ModelMetadata, ModelRegistry,
    get_model_registry, reset_model_registry,
    # Training Orchestrator
    TrainingStatus, TrainingConfig, TrainingJob, TrainingOrchestrator,
    get_training_orchestrator, reset_training_orchestrator,
    # Inference Server
    InferenceStatus, BatchStrategy, InferenceRequest, InferenceResponse, InferenceServer,
    get_inference_server, reset_inference_server,
    # Model Monitor
    MonitorMetric, AlertSeverity, ModelMetric, ModelAlert, ModelMonitor,
    get_model_monitor, reset_model_monitor
)


class TestFeatureEngineer(unittest.TestCase):
    """Test FeatureEngineer module (Stage 401)"""

    def setUp(self):
        reset_feature_engineer()
        self.engineer = get_feature_engineer()

    def test_register_unregister_feature(self):
        result = self.engineer.register_feature("age", FeatureType.NUMERIC, {"min": 0, "max": 100})
        self.assertTrue(result)
        result = self.engineer.unregister_feature("age")
        self.assertTrue(result)

    def test_scale_minmax(self):
        data = [10, 20, 30, 40, 50]
        scaled = self.engineer.scale(data, method="minmax")
        self.assertEqual(len(scaled), len(data))
        self.assertAlmostEqual(min(scaled), 0.0, places=5)
        self.assertAlmostEqual(max(scaled), 1.0, places=5)

    def test_scale_zscore(self):
        data = [10, 20, 30, 40, 50]
        scaled = self.engineer.scale(data, method="zscore")
        self.assertEqual(len(scaled), len(data))
        self.assertAlmostEqual(sum(scaled) / len(scaled), 0.0, places=5)

    def test_normalize(self):
        data = [3, 4]
        normalized = self.engineer.normalize(data)
        self.assertEqual(len(normalized), len(data))
        self.assertAlmostEqual(normalized[0], 0.6, places=5)
        self.assertAlmostEqual(normalized[1], 0.8, places=5)

    def test_encode_categorical(self):
        data = ["A", "B", "A", "C"]
        encoded = self.engineer.encode_categorical(data, method="onehot")
        self.assertIn("A", encoded)
        self.assertIn("B", encoded)
        self.assertIn("C", encoded)

    def test_bin_numeric(self):
        data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        binned = self.engineer.bin_numeric(data, bins=5)
        self.assertEqual(len(binned), len(data))
        self.assertTrue(all(isinstance(b, int) for b in binned))

    def test_polynomial_features(self):
        data = [1, 2, 3]
        poly = self.engineer.polynomial_features(data, degree=2)
        self.assertEqual(len(poly), len(data))

    def test_interaction_features(self):
        data_a = [1, 2, 3]
        data_b = [4, 5, 6]
        interaction = self.engineer.interaction_features(data_a, data_b)
        self.assertEqual(len(interaction), len(data_a))
        self.assertEqual(interaction[0], 4)

    def test_get_all_features(self):
        self.engineer.register_feature("f1", FeatureType.NUMERIC)
        self.engineer.register_feature("f2", FeatureType.CATEGORICAL)
        features = self.engineer.get_all_features()
        self.assertEqual(len(features), 2)

    def test_global_singleton(self):
        engineer2 = get_feature_engineer()
        self.assertIs(self.engineer, engineer2)


class TestModelRegistry(unittest.TestCase):
    """Test ModelRegistry module (Stage 402)"""

    def setUp(self):
        reset_model_registry()
        self.registry = get_model_registry()

    def test_register_unregister(self):
        model_id = self.registry.register_model("model1", ModelType.CLASSIFIER, {"lr": 0.01})
        self.assertIsNotNone(model_id)
        result = self.registry.unregister_model(model_id)
        self.assertTrue(result)

    def test_get_model(self):
        model_id = self.registry.register_model("model1", ModelType.CLASSIFIER, {"lr": 0.01})
        model = self.registry.get_model(model_id)
        self.assertIsNotNone(model)
        self.assertEqual(model.name, "model1")

    def test_update_status(self):
        model_id = self.registry.register_model("model1", ModelType.CLASSIFIER, {"lr": 0.01})
        result = self.registry.update_status(model_id, ModelStatus.TRAINED)
        self.assertTrue(result)
        model = self.registry.get_model(model_id)
        self.assertEqual(model.status, ModelStatus.TRAINED)

    def test_update_metrics(self):
        model_id = self.registry.register_model("model1", ModelType.CLASSIFIER, {"lr": 0.01})
        result = self.registry.update_metrics(model_id, {"accuracy": 0.95})
        self.assertTrue(result)
        model = self.registry.get_model(model_id)
        self.assertEqual(model.metrics["accuracy"], 0.95)

    def test_store_artifact(self):
        model_id = self.registry.register_model("model1", ModelType.CLASSIFIER, {"lr": 0.01})
        artifact_id = self.registry.store_artifact(model_id, 1, "pickle", b"model_data")
        self.assertIsNotNone(artifact_id)
        artifact = self.registry.get_artifact(artifact_id)
        self.assertIsNotNone(artifact)

    def test_add_remove_tag(self):
        model_id = self.registry.register_model("model1", ModelType.CLASSIFIER, {"lr": 0.01})
        self.registry.add_tag(model_id, "production")
        models = self.registry.search_by_tag("production")
        self.assertEqual(len(models), 1)
        self.registry.remove_tag(model_id, "production")
        models = self.registry.search_by_tag("production")
        self.assertEqual(len(models), 0)

    def test_get_models_by_status(self):
        model_id = self.registry.register_model("model1", ModelType.CLASSIFIER, {"lr": 0.01})
        self.registry.update_status(model_id, ModelStatus.TRAINED)
        models = self.registry.get_models(status=ModelStatus.TRAINED)
        self.assertEqual(len(models), 1)

    def test_get_models_by_type(self):
        self.registry.register_model("model1", ModelType.CLASSIFIER, {})
        self.registry.register_model("model2", ModelType.REGRESSOR, {})
        models = self.registry.get_models(model_type=ModelType.CLASSIFIER)
        self.assertEqual(len(models), 1)

    def test_global_singleton(self):
        registry2 = get_model_registry()
        self.assertIs(self.registry, registry2)


class TestTrainingOrchestrator(unittest.TestCase):
    """Test TrainingOrchestrator module (Stage 403)"""

    def setUp(self):
        reset_training_orchestrator()
        self.orchestrator = get_training_orchestrator()

    def test_create_delete_config(self):
        config_id = self.orchestrator.create_config("model1", "sgd", {"lr": 0.01})
        self.assertIsNotNone(config_id)
        result = self.orchestrator.delete_config(config_id)
        self.assertTrue(result)

    def test_start_training(self):
        config_id = self.orchestrator.create_config("model1", "sgd", {"lr": 0.01})
        job_id = self.orchestrator.start_training(config_id)
        self.assertIsNotNone(job_id)
        job = self.orchestrator.get_job(job_id)
        self.assertIsNotNone(job)

    def test_cancel_training(self):
        config_id = self.orchestrator.create_config("model1", "sgd", {"lr": 0.01})
        job_id = self.orchestrator.start_training(config_id)
        result = self.orchestrator.cancel_training(job_id)
        self.assertTrue(result)
        job = self.orchestrator.get_job(job_id)
        self.assertEqual(job.status, TrainingStatus.CANCELLED)

    def test_update_progress(self):
        config_id = self.orchestrator.create_config("model1", "sgd", {"lr": 0.01})
        job_id = self.orchestrator.start_training(config_id)
        result = self.orchestrator.update_progress(job_id, 0.5, {"loss": 0.3})
        self.assertTrue(result)
        job = self.orchestrator.get_job(job_id)
        self.assertEqual(job.progress, 0.5)

    def test_complete_training(self):
        config_id = self.orchestrator.create_config("model1", "sgd", {"lr": 0.01})
        job_id = self.orchestrator.start_training(config_id)
        result = self.orchestrator.complete_training(job_id, {"accuracy": 0.95})
        self.assertTrue(result)
        job = self.orchestrator.get_job(job_id)
        self.assertEqual(job.status, TrainingStatus.COMPLETED)

    def test_fail_training(self):
        config_id = self.orchestrator.create_config("model1", "sgd", {"lr": 0.01})
        job_id = self.orchestrator.start_training(config_id)
        result = self.orchestrator.fail_training(job_id, "Out of memory")
        self.assertTrue(result)
        job = self.orchestrator.get_job(job_id)
        self.assertEqual(job.status, TrainingStatus.FAILED)

    def test_get_active_jobs(self):
        config_id = self.orchestrator.create_config("model1", "sgd", {"lr": 0.01})
        self.orchestrator.start_training(config_id)
        active = self.orchestrator.get_active_jobs()
        self.assertEqual(len(active), 1)

    def test_get_training_history(self):
        config_id = self.orchestrator.create_config("model1", "sgd", {"lr": 0.01})
        job_id = self.orchestrator.start_training(config_id)
        self.orchestrator.complete_training(job_id, {"accuracy": 0.95})
        history = self.orchestrator.get_training_history("model1")
        self.assertEqual(len(history), 1)

    def test_global_singleton(self):
        orchestrator2 = get_training_orchestrator()
        self.assertIs(self.orchestrator, orchestrator2)


class TestInferenceServer(unittest.TestCase):
    """Test InferenceServer module (Stage 404)"""

    def setUp(self):
        reset_inference_server()
        self.server = get_inference_server()

    def test_load_unload_model(self):
        result = self.server.load_model("model1", {"latency_ms": 10})
        self.assertTrue(result)
        status = self.server.get_model_status("model1")
        self.assertEqual(status, InferenceStatus.READY)
        result = self.server.unload_model("model1")
        self.assertTrue(result)

    def test_predict(self):
        self.server.load_model("model1", {"latency_ms": 10})
        response = self.server.predict("model1", {"input": [1, 2, 3]})
        self.assertIsNotNone(response)
        self.assertEqual(response.model_id, "model1")

    def test_predict_batch(self):
        self.server.load_model("model1", {"latency_ms": 10})
        inputs = [{"input": [1]}, {"input": [2]}, {"input": [3]}]
        responses = self.server.predict_batch("model1", inputs, BatchStrategy.DYNAMIC)
        self.assertEqual(len(responses), 3)

    def test_get_loaded_models(self):
        self.server.load_model("model1", {})
        self.server.load_model("model2", {})
        models = self.server.get_loaded_models()
        self.assertEqual(len(models), 2)

    def test_get_latency_stats(self):
        self.server.load_model("model1", {"latency_ms": 10})
        self.server.predict("model1", {"input": [1]})
        stats = self.server.get_latency_stats("model1")
        self.assertIn("mean_ms", stats)

    def test_warmup(self):
        self.server.load_model("model1", {"latency_ms": 10})
        result = self.server.warmup("model1", {"input": [1, 2, 3]})
        self.assertTrue(result)

    def test_get_statistics(self):
        self.server.load_model("model1", {"latency_ms": 10})
        self.server.predict("model1", {"input": [1]})
        stats = self.server.get_statistics()
        self.assertIn("total_models", stats)

    def test_global_singleton(self):
        server2 = get_inference_server()
        self.assertIs(self.server, server2)


class TestModelMonitor(unittest.TestCase):
    """Test ModelMonitor module (Stage 405)"""

    def setUp(self):
        reset_model_monitor()
        self.monitor = get_model_monitor()

    def test_record_metric(self):
        metric_id = self.monitor.record_metric("model1", MonitorMetric.ACCURACY, 0.95)
        self.assertIsNotNone(metric_id)

    def test_get_metrics(self):
        self.monitor.record_metric("model1", MonitorMetric.ACCURACY, 0.95)
        self.monitor.record_metric("model1", MonitorMetric.ACCURACY, 0.96)
        metrics = self.monitor.get_metrics("model1", MonitorMetric.ACCURACY)
        self.assertEqual(len(metrics), 2)

    def test_get_latest_metric(self):
        self.monitor.record_metric("model1", MonitorMetric.LATENCY, 50.0)
        latest = self.monitor.get_latest_metric("model1", MonitorMetric.LATENCY)
        self.assertIsNotNone(latest)
        self.assertEqual(latest.value, 50.0)

    def test_set_threshold_and_alert(self):
        self.monitor.set_threshold("model1", MonitorMetric.ACCURACY, 0.90)
        self.monitor.record_metric("model1", MonitorMetric.ACCURACY, 0.85)
        alerts = self.monitor.check_alerts("model1")
        self.assertGreater(len(alerts), 0)

    def test_acknowledge_alert(self):
        self.monitor.set_threshold("model1", MonitorMetric.ACCURACY, 0.90)
        self.monitor.record_metric("model1", MonitorMetric.ACCURACY, 0.85)
        alerts = self.monitor.check_alerts("model1")
        alert_id = alerts[0].alert_id
        result = self.monitor.acknowledge_alert(alert_id)
        self.assertTrue(result)

    def test_get_health_score(self):
        self.monitor.record_metric("model1", MonitorMetric.ACCURACY, 0.95)
        score = self.monitor.get_health_score("model1")
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 100.0)

    def test_get_performance_summary(self):
        self.monitor.record_metric("model1", MonitorMetric.ACCURACY, 0.95)
        summary = self.monitor.get_performance_summary("model1")
        self.assertIn("metrics", summary)
        self.assertIn("accuracy", summary["metrics"])

    def test_global_singleton(self):
        monitor2 = get_model_monitor()
        self.assertIs(self.monitor, monitor2)


class TestDataStructures(unittest.TestCase):
    """Test all data structures and enums"""

    def test_transform_type_enum(self):
        self.assertEqual(len(TransformType), 7)
        self.assertIn(TransformType.SCALING, list(TransformType))

    def test_feature_type_enum(self):
        self.assertEqual(len(FeatureType), 5)
        self.assertIn(FeatureType.NUMERIC, list(FeatureType))

    def test_model_status_enum(self):
        self.assertEqual(len(ModelStatus), 6)
        self.assertIn(ModelStatus.TRAINED, list(ModelStatus))

    def test_model_type_enum(self):
        self.assertEqual(len(ModelType), 5)
        self.assertIn(ModelType.CLASSIFIER, list(ModelType))

    def test_training_status_enum(self):
        self.assertEqual(len(TrainingStatus), 7)
        self.assertIn(TrainingStatus.COMPLETED, list(TrainingStatus))

    def test_inference_status_enum(self):
        self.assertEqual(len(InferenceStatus), 5)
        self.assertIn(InferenceStatus.READY, list(InferenceStatus))

    def test_batch_strategy_enum(self):
        self.assertEqual(len(BatchStrategy), 3)
        self.assertIn(BatchStrategy.DYNAMIC, list(BatchStrategy))

    def test_monitor_metric_enum(self):
        self.assertEqual(len(MonitorMetric), 7)
        self.assertIn(MonitorMetric.ACCURACY, list(MonitorMetric))

    def test_alert_severity_enum(self):
        self.assertEqual(len(AlertSeverity), 3)
        self.assertIn(AlertSeverity.CRITICAL, list(AlertSeverity))


if __name__ == '__main__':
    unittest.main()
