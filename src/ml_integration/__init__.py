"""
ML Integration Module for Agent Reliable Memory System.

This module provides machine learning integration capabilities including:
- Feature engineering (Stage 401)
- Model registry (Stage 402)
- Training orchestrator (Stage 403)
- Inference server (Stage 404)
- Model monitor (Stage 405)
"""

from .feature_engineering import (
    TransformType,
    FeatureType,
    FeatureSpec,
    TransformedFeature,
    FeatureEngineer,
    get_feature_engineer,
    reset_feature_engineer
)

from .model_registry import (
    ModelStatus,
    ModelType,
    ModelArtifact,
    ModelMetadata,
    ModelRegistry,
    get_model_registry,
    reset_model_registry
)

from .training_orchestrator import (
    TrainingStatus,
    TrainingConfig,
    TrainingJob,
    TrainingOrchestrator,
    get_training_orchestrator,
    reset_training_orchestrator
)

from .inference_server import (
    InferenceStatus,
    BatchStrategy,
    InferenceRequest,
    InferenceResponse,
    InferenceServer,
    get_inference_server,
    reset_inference_server
)

from .model_monitor import (
    MonitorMetric,
    AlertSeverity,
    ModelMetric,
    ModelAlert,
    ModelMonitor,
    get_model_monitor,
    reset_model_monitor
)

__all__ = [
    # Feature Engineering
    'TransformType',
    'FeatureType',
    'FeatureSpec',
    'TransformedFeature',
    'FeatureEngineer',
    'get_feature_engineer',
    'reset_feature_engineer',
    
    # Model Registry
    'ModelStatus',
    'ModelType',
    'ModelArtifact',
    'ModelMetadata',
    'ModelRegistry',
    'get_model_registry',
    'reset_model_registry',
    
    # Training Orchestrator
    'TrainingStatus',
    'TrainingConfig',
    'TrainingJob',
    'TrainingOrchestrator',
    'get_training_orchestrator',
    'reset_training_orchestrator',
    
    # Inference Server
    'InferenceStatus',
    'BatchStrategy',
    'InferenceRequest',
    'InferenceResponse',
    'InferenceServer',
    'get_inference_server',
    'reset_inference_server',
    
    # Model Monitor
    'MonitorMetric',
    'AlertSeverity',
    'ModelMetric',
    'ModelAlert',
    'ModelMonitor',
    'get_model_monitor',
    'reset_model_monitor'
]
