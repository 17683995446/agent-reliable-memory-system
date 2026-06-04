"""
Intelligence Module for Agent Reliable Memory System.

This module provides intelligent analysis and reasoning capabilities including:
- Pattern recognition (Stage 391)
- Inference engine (Stage 392)
- Decision engine (Stage 393)
- Learning module (Stage 394)
- Prediction engine (Stage 395)
"""

from .pattern_recognizer import (
    PatternType,
    PatternConfidence,
    DetectedPattern,
    PatternRule,
    PatternRecognizer,
    get_pattern_recognizer,
    reset_pattern_recognizer
)

from .inference_engine import (
    InferenceType,
    InferenceStatus,
    Fact,
    Rule,
    InferenceResult,
    InferenceEngine,
    get_inference_engine,
    reset_inference_engine
)

from .decision_engine import (
    DecisionType,
    DecisionStatus,
    DecisionCriteria,
    DecisionOption,
    DecisionResult,
    DecisionEngine,
    get_decision_engine,
    reset_decision_engine
)

from .learning_module import (
    LearningType,
    LearningStatus,
    ModelConfig,
    TrainingResult,
    LearningModule,
    get_learning_module,
    reset_learning_module
)

from .prediction_engine import (
    PredictionType,
    PredictionConfidence,
    TimeSeriesPoint,
    PredictionResult,
    PredictionModel,
    PredictionEngine,
    get_prediction_engine,
    reset_prediction_engine
)

__all__ = [
    # Pattern Recognizer
    'PatternType',
    'PatternConfidence',
    'DetectedPattern',
    'PatternRule',
    'PatternRecognizer',
    'get_pattern_recognizer',
    'reset_pattern_recognizer',
    
    # Inference Engine
    'InferenceType',
    'InferenceStatus',
    'Fact',
    'Rule',
    'InferenceResult',
    'InferenceEngine',
    'get_inference_engine',
    'reset_inference_engine',
    
    # Decision Engine
    'DecisionType',
    'DecisionStatus',
    'DecisionCriteria',
    'DecisionOption',
    'DecisionResult',
    'DecisionEngine',
    'get_decision_engine',
    'reset_decision_engine',
    
    # Learning Module
    'LearningType',
    'LearningStatus',
    'ModelConfig',
    'TrainingResult',
    'LearningModule',
    'get_learning_module',
    'reset_learning_module',
    
    # Prediction Engine
    'PredictionType',
    'PredictionConfidence',
    'TimeSeriesPoint',
    'PredictionResult',
    'PredictionModel',
    'PredictionEngine',
    'get_prediction_engine',
    'reset_prediction_engine'
]
