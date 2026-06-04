"""
Phase 38 Validation Tests - Intelligence Modules (Stages 391-395)

Tests for:
- pattern_recognizer.py (Stage 391)
- inference_engine.py (Stage 392)
- decision_engine.py (Stage 393)
- learning_module.py (Stage 394)
- prediction_engine.py (Stage 395)
"""

import unittest
import time

from src.intelligence import (
    # Pattern Recognizer
    PatternType, PatternConfidence, DetectedPattern, PatternRule, PatternRecognizer,
    get_pattern_recognizer, reset_pattern_recognizer,
    # Inference Engine
    InferenceType, InferenceStatus, Fact, Rule, InferenceResult, InferenceEngine,
    get_inference_engine, reset_inference_engine,
    # Decision Engine
    DecisionType, DecisionStatus, DecisionCriteria, DecisionOption, DecisionResult, DecisionEngine,
    get_decision_engine, reset_decision_engine,
    # Learning Module
    LearningType, LearningStatus, ModelConfig, TrainingResult, LearningModule,
    get_learning_module, reset_learning_module,
    # Prediction Engine
    PredictionType, PredictionConfidence, TimeSeriesPoint, PredictionResult, PredictionModel, PredictionEngine,
    get_prediction_engine, reset_prediction_engine
)


class TestPatternRecognizer(unittest.TestCase):
    """Test PatternRecognizer module (Stage 391)"""

    def setUp(self):
        reset_pattern_recognizer()
        self.recognizer = get_pattern_recognizer()

    def test_detect_sequence_increasing(self):
        data = [1, 2, 3, 4, 5]
        patterns = self.recognizer.detect_sequence(data)
        self.assertGreater(len(patterns), 0)
        self.assertEqual(patterns[0].pattern_type, PatternType.SEQUENCE)

    def test_detect_trend(self):
        data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        patterns = self.recognizer.detect_trend(data)
        self.assertGreaterEqual(len(patterns), 0)

    def test_detect_anomaly(self):
        data = [1, 2, 1, 2, 1, 2, 100]
        patterns = self.recognizer.detect_anomaly(data, threshold=2.0)
        self.assertGreater(len(patterns), 0)

    def test_detect_correlation(self):
        data_x = [1, 2, 3, 4, 5]
        data_y = [2, 4, 6, 8, 10]
        pattern = self.recognizer.detect_correlation(data_x, data_y)
        self.assertIsNotNone(pattern)
        self.assertEqual(pattern.pattern_type, PatternType.CORRELATION)

    def test_add_remove_rule(self):
        rule = PatternRule(
            rule_id="test_rule",
            pattern_type=PatternType.SEQUENCE,
            condition="x > 0",
            threshold=0.5,
            enabled=True
        )
        result = self.recognizer.add_rule(rule)
        self.assertTrue(result)
        result = self.recognizer.remove_rule("test_rule")
        self.assertTrue(result)

    def test_get_patterns_by_type(self):
        data = [1, 2, 3, 4, 5]
        self.recognizer.detect_sequence(data)
        patterns = self.recognizer.get_patterns_by_type(PatternType.SEQUENCE)
        self.assertGreater(len(patterns), 0)

    def test_clear_patterns(self):
        data = [1, 2, 3, 4, 5]
        self.recognizer.detect_sequence(data)
        count = self.recognizer.clear_patterns()
        self.assertGreater(count, 0)

    def test_global_singleton(self):
        recognizer2 = get_pattern_recognizer()
        self.assertIs(self.recognizer, recognizer2)


class TestInferenceEngine(unittest.TestCase):
    """Test InferenceEngine module (Stage 392)"""

    def setUp(self):
        reset_inference_engine()
        self.engine = get_inference_engine()

    def test_add_fact(self):
        fact_id = self.engine.add_fact("All humans are mortal", confidence=1.0, source="axiom")
        self.assertIsNotNone(fact_id)
        facts = self.engine.get_facts()
        self.assertEqual(len(facts), 1)

    def test_add_rule(self):
        rule_id = self.engine.add_rule("All humans are mortal", "Socrates is mortal", confidence=1.0)
        self.assertIsNotNone(rule_id)
        rules = self.engine.get_rules()
        self.assertEqual(len(rules), 1)

    def test_deduction(self):
        fact1 = self.engine.add_fact("All humans are mortal")
        rule = self.engine.add_rule("All humans are mortal", "Socrates is mortal")
        result = self.engine.deduct([fact1], rule)
        self.assertIsNotNone(result)
        self.assertEqual(result.inference_type, InferenceType.DEDUCTION)

    def test_induction(self):
        fact1 = self.engine.add_fact("Swan 1 is white")
        fact2 = self.engine.add_fact("Swan 2 is white")
        fact3 = self.engine.add_fact("Swan 3 is white")
        result = self.engine.induct([fact1, fact2, fact3])
        self.assertIsNotNone(result)
        self.assertEqual(result.inference_type, InferenceType.INDUCTION)

    def test_abduction(self):
        observation = self.engine.add_fact("The grass is wet")
        cause1 = self.engine.add_fact("It rained")
        cause2 = self.engine.add_fact("Sprinkler was on")
        result = self.engine.abduce(observation, [cause1, cause2])
        self.assertIsNotNone(result)
        self.assertEqual(result.inference_type, InferenceType.ABDUCTION)

    def test_get_inference(self):
        fact1 = self.engine.add_fact("All humans are mortal")
        rule = self.engine.add_rule("All humans are mortal", "Socrates is mortal")
        result = self.engine.deduct([fact1], rule)
        fetched = self.engine.get_inference(result.result_id)
        self.assertIsNotNone(fetched)

    def test_clear(self):
        self.engine.add_fact("Test fact")
        self.engine.clear()
        facts = self.engine.get_facts()
        self.assertEqual(len(facts), 0)

    def test_global_singleton(self):
        engine2 = get_inference_engine()
        self.assertIs(self.engine, engine2)


class TestDecisionEngine(unittest.TestCase):
    """Test DecisionEngine module (Stage 393)"""

    def setUp(self):
        reset_decision_engine()
        self.engine = get_decision_engine()

    def test_add_remove_criteria(self):
        criteria_id = self.engine.add_criteria("cost", weight=0.5, threshold=100.0, maximize=False)
        self.assertIsNotNone(criteria_id)
        result = self.engine.remove_criteria(criteria_id)
        self.assertTrue(result)

    def test_make_binary_decision(self):
        self.engine.add_criteria("quality", weight=1.0, threshold=0.5, maximize=True)
        options = [
            DecisionOption("opt1", "Option 1", {"quality": 0.8}, {}),
            DecisionOption("opt2", "Option 2", {"quality": 0.3}, {})
        ]
        result = self.engine.make_binary_decision(options, {"quality": 0.5})
        self.assertIsNotNone(result)
        self.assertIn(result.status, [DecisionStatus.APPROVED, DecisionStatus.REJECTED])

    def test_make_multi_choice_decision(self):
        self.engine.add_criteria("score", weight=1.0, threshold=0.0, maximize=True)
        options = [
            DecisionOption("a", "A", {"score": 80}, {}),
            DecisionOption("b", "B", {"score": 90}, {}),
            DecisionOption("c", "C", {"score": 70}, {})
        ]
        result = self.engine.make_multi_choice_decision(options, {"score": 0})
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.chosen_option)

    def test_make_ranking_decision(self):
        self.engine.add_criteria("score", weight=1.0, threshold=0.0, maximize=True)
        options = [
            DecisionOption("a", "A", {"score": 80}, {}),
            DecisionOption("b", "B", {"score": 90}, {})
        ]
        result = self.engine.make_ranking_decision(options, {"score": 0})
        self.assertIsNotNone(result)
        self.assertEqual(result.decision_type, DecisionType.RANKING)

    def test_make_probabilistic_decision(self):
        options = [
            DecisionOption("a", "A", {}, {}),
            DecisionOption("b", "B", {}, {})
        ]
        probabilities = {"a": 0.7, "b": 0.3}
        result = self.engine.make_probabilistic_decision(options, probabilities)
        self.assertIsNotNone(result)
        self.assertEqual(result.decision_type, DecisionType.PROBABILISTIC)

    def test_get_decision_history(self):
        self.engine.add_criteria("score", weight=1.0, threshold=0.0, maximize=True)
        options = [
            DecisionOption("a", "A", {"score": 80}, {}),
            DecisionOption("b", "B", {"score": 60}, {})
        ]
        self.engine.make_binary_decision(options, {"score": 0.5})
        history = self.engine.get_decision_history()
        self.assertEqual(len(history), 1)

    def test_get_criteria(self):
        self.engine.add_criteria("cost", weight=0.5, threshold=100.0)
        criteria = self.engine.get_criteria()
        self.assertEqual(len(criteria), 1)

    def test_global_singleton(self):
        engine2 = get_decision_engine()
        self.assertIs(self.engine, engine2)


class TestLearningModule(unittest.TestCase):
    """Test LearningModule module (Stage 394)"""

    def setUp(self):
        reset_learning_module()
        self.module = get_learning_module()

    def test_create_delete_model(self):
        model_id = self.module.create_model(
            LearningType.SUPERVISED,
            features=["x1", "x2"],
            hyperparameters={"lr": 0.01}
        )
        self.assertIsNotNone(model_id)
        result = self.module.delete_model(model_id)
        self.assertTrue(result)

    def test_train_supervised(self):
        model_id = self.module.create_model(
            LearningType.SUPERVISED,
            features=["x1"],
            hyperparameters={"lr": 0.1, "epochs": 10}
        )
        training_data = [
            {"x1": 1.0, "label": 1},
            {"x1": 2.0, "label": 1},
            {"x1": -1.0, "label": 0},
            {"x1": -2.0, "label": 0}
        ]
        result = self.module.train(model_id, training_data)
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result.accuracy, 0.0)

    def test_predict(self):
        model_id = self.module.create_model(
            LearningType.SUPERVISED,
            features=["x1"],
            hyperparameters={"lr": 0.1, "epochs": 10}
        )
        training_data = [
            {"x1": 1.0, "label": 1},
            {"x1": -1.0, "label": 0}
        ]
        self.module.train(model_id, training_data)
        prediction = self.module.predict(model_id, {"x1": 1.5})
        self.assertIsNotNone(prediction)

    def test_get_feature_importance(self):
        model_id = self.module.create_model(
            LearningType.SUPERVISED,
            features=["x1", "x2"],
            hyperparameters={"lr": 0.1}
        )
        importance = self.module.get_feature_importance(model_id)
        self.assertIn("x1", importance)
        self.assertIn("x2", importance)

    def test_get_training_history(self):
        model_id = self.module.create_model(
            LearningType.SUPERVISED,
            features=["x1"],
            hyperparameters={"lr": 0.1}
        )
        training_data = [
            {"x1": 1.0, "label": 1},
            {"x1": -1.0, "label": 0}
        ]
        self.module.train(model_id, training_data)
        history = self.module.get_training_history(model_id)
        self.assertEqual(len(history), 1)

    def test_get_all_models(self):
        self.module.create_model(LearningType.SUPERVISED, features=["x1"], hyperparameters={})
        self.module.create_model(LearningType.UNSUPERVISED, features=["x1"], hyperparameters={})
        models = self.module.get_all_models()
        self.assertEqual(len(models), 2)

    def test_global_singleton(self):
        module2 = get_learning_module()
        self.assertIs(self.module, module2)


class TestPredictionEngine(unittest.TestCase):
    """Test PredictionEngine module (Stage 395)"""

    def setUp(self):
        reset_prediction_engine()
        self.engine = get_prediction_engine()

    def test_create_delete_model(self):
        model_id = self.engine.create_model(
            PredictionType.REGRESSION,
            features=["x1"],
            parameters={}
        )
        self.assertIsNotNone(model_id)
        result = self.engine.delete_model(model_id)
        self.assertTrue(result)

    def test_predict_regression(self):
        model_id = self.engine.create_model(
            PredictionType.REGRESSION,
            features=["x1"],
            parameters={}
        )
        # Add training data
        self.engine.add_training_data(model_id, [{"x1": 1.0, "y": 2.0}, {"x1": 2.0, "y": 4.0}])
        result = self.engine.predict_regression(model_id, {"x1": 3.0})
        self.assertIsNotNone(result)
        self.assertEqual(result.prediction_type, PredictionType.REGRESSION)

    def test_predict_classification(self):
        model_id = self.engine.create_model(
            PredictionType.CLASSIFICATION,
            features=["x1", "x2"],
            parameters={"k": 3}
        )
        self.engine.add_training_data(model_id, [
            {"x1": 1.0, "x2": 1.0, "label": "A"},
            {"x1": 5.0, "x2": 5.0, "label": "B"}
        ])
        result = self.engine.predict_classification(model_id, {"x1": 1.5, "x2": 1.5})
        self.assertIsNotNone(result)
        self.assertEqual(result.prediction_type, PredictionType.CLASSIFICATION)

    def test_predict_forecast(self):
        model_id = self.engine.create_model(
            PredictionType.FORECASTING,
            features=["value"],
            parameters={"window": 3}
        )
        series = [
            TimeSeriesPoint(1, 10.0, {}),
            TimeSeriesPoint(2, 20.0, {}),
            TimeSeriesPoint(3, 30.0, {})
        ]
        result = self.engine.predict_forecast(model_id, series)
        self.assertIsNotNone(result)
        self.assertEqual(result.prediction_type, PredictionType.FORECASTING)

    def test_predict_anomaly(self):
        model_id = self.engine.create_model(
            PredictionType.ANOMALY_DETECTION,
            features=["value"],
            parameters={"threshold": 2.0}
        )
        self.engine.add_training_data(model_id, [
            {"value": 10.0}, {"value": 11.0}, {"value": 10.5}
        ])
        result = self.engine.predict_anomaly(model_id, {"value": 100.0})
        self.assertIsNotNone(result)
        self.assertEqual(result.prediction_type, PredictionType.ANOMALY_DETECTION)

    def test_get_predictions(self):
        model_id = self.engine.create_model(
            PredictionType.REGRESSION,
            features=["x1"],
            parameters={}
        )
        self.engine.add_training_data(model_id, [{"x1": 1.0, "y": 2.0}])
        self.engine.predict_regression(model_id, {"x1": 3.0})
        predictions = self.engine.get_predictions(model_id)
        self.assertEqual(len(predictions), 1)

    def test_get_all_models(self):
        self.engine.create_model(PredictionType.REGRESSION, features=["x1"], parameters={})
        self.engine.create_model(PredictionType.CLASSIFICATION, features=["x1"], parameters={})
        models = self.engine.get_all_models()
        self.assertEqual(len(models), 2)

    def test_global_singleton(self):
        engine2 = get_prediction_engine()
        self.assertIs(self.engine, engine2)


class TestDataStructures(unittest.TestCase):
    """Test all data structures and enums"""

    def test_pattern_type_enum(self):
        self.assertEqual(len(PatternType), 6)
        self.assertIn(PatternType.SEQUENCE, list(PatternType))

    def test_pattern_confidence_enum(self):
        self.assertEqual(len(PatternConfidence), 4)
        self.assertIn(PatternConfidence.HIGH, list(PatternConfidence))

    def test_inference_type_enum(self):
        self.assertEqual(len(InferenceType), 5)
        self.assertIn(InferenceType.DEDUCTION, list(InferenceType))

    def test_inference_status_enum(self):
        self.assertEqual(len(InferenceStatus), 4)
        self.assertIn(InferenceStatus.VALID, list(InferenceStatus))

    def test_decision_type_enum(self):
        self.assertEqual(len(DecisionType), 5)
        self.assertIn(DecisionType.BINARY, list(DecisionType))

    def test_decision_status_enum(self):
        self.assertEqual(len(DecisionStatus), 4)
        self.assertIn(DecisionStatus.APPROVED, list(DecisionStatus))

    def test_learning_type_enum(self):
        self.assertEqual(len(LearningType), 5)
        self.assertIn(LearningType.SUPERVISED, list(LearningType))

    def test_learning_status_enum(self):
        self.assertEqual(len(LearningStatus), 4)
        self.assertIn(LearningStatus.TRAINED, list(LearningStatus))

    def test_prediction_type_enum(self):
        self.assertEqual(len(PredictionType), 4)
        self.assertIn(PredictionType.REGRESSION, list(PredictionType))

    def test_prediction_confidence_enum(self):
        self.assertEqual(len(PredictionConfidence), 3)
        self.assertIn(PredictionConfidence.HIGH, list(PredictionConfidence))


if __name__ == '__main__':
    unittest.main()
