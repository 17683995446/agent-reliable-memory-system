"""
数据导出与报表模块 (DataExport) - 阶段341-345

模块：
- data_exporter: 数据导出器（JSON/CSV/Markdown/HTML/Text）
- report_generator: 报表生成器（日报/周报/月报）
- data_backup: 数据备份与恢复（快照/增量/版本）
- analytics_engine: 数据分析引擎（趋势/热点/模式/异常）
- dashboard_aggregator: 仪表盘聚合器（KPI/健康度/告警）
"""

from data_export.data_exporter import (
    ExportFormat, ExportStatus, DataSourceType,
    ExportConfig, ExportTask, ExportHistory,
    DataPreprocessor,
    JsonFormatter, CsvFormatter, MarkdownFormatter, HtmlFormatter, TextFormatter,
    DataExporter, get_exporter,
)
from data_export.report_generator import (
    ReportType, ReportFormat,
    ReportSection, ReportTemplate, ReportData, GeneratedReport, MetricPoint,
    DataCollector,
    MarkdownRenderer, HtmlRenderer, TextRenderer,
    ReportGenerator, get_report_generator,
)
from data_export.data_backup import (
    BackupType, BackupStatus, StorageBackend,
    BackupMeta, BackupPolicy, ChangeRecord,
    ChangeTracker, BackupStorage, DataBackup, get_data_backup,
)
from data_export.analytics_engine import (
    TrendDirection, AggregationType,
    DataPoint, TrendResult, HotItem, PatternResult, AnomalyResult, TimeBucket,
    StatsCalculator,
    TrendAnalyzer, HotspotDetector, PatternMiner, AnomalyDetector,
    AnalyticsEngine, get_analytics_engine,
)
from data_export.dashboard_aggregator import (
    HealthLevel, AlertSeverity, KPIStatus,
    KPIDefinition, KPIValue, ModuleStatus, AlertSummary, HealthScore, DashboardSnapshot,
    KPIManager, HealthEvaluator, AlertAggregator, ModuleStatusManager,
    DashboardAggregator, get_dashboard,
)

__all__ = [
    # data_exporter
    "ExportFormat", "ExportStatus", "DataSourceType",
    "ExportConfig", "ExportTask", "ExportHistory",
    "DataPreprocessor",
    "JsonFormatter", "CsvFormatter", "MarkdownFormatter", "HtmlFormatter", "TextFormatter",
    "DataExporter", "get_exporter",
    # report_generator
    "ReportType", "ReportFormat",
    "ReportSection", "ReportTemplate", "ReportData", "GeneratedReport", "MetricPoint",
    "DataCollector",
    "MarkdownRenderer", "HtmlRenderer", "TextRenderer",
    "ReportGenerator", "get_report_generator",
    # data_backup
    "BackupType", "BackupStatus", "StorageBackend",
    "BackupMeta", "BackupPolicy", "ChangeRecord",
    "ChangeTracker", "BackupStorage", "DataBackup", "get_data_backup",
    # analytics_engine
    "TrendDirection", "AggregationType",
    "DataPoint", "TrendResult", "HotItem", "PatternResult", "AnomalyResult", "TimeBucket",
    "StatsCalculator",
    "TrendAnalyzer", "HotspotDetector", "PatternMiner", "AnomalyDetector",
    "AnalyticsEngine", "get_analytics_engine",
    # dashboard_aggregator
    "HealthLevel", "AlertSeverity", "KPIStatus",
    "KPIDefinition", "KPIValue", "ModuleStatus", "AlertSummary", "HealthScore", "DashboardSnapshot",
    "KPIManager", "HealthEvaluator", "AlertAggregator", "ModuleStatusManager",
    "DashboardAggregator", "get_dashboard",
]
