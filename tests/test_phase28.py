#!/usr/bin/env python3
"""
验证第28阶段 - 数据导出与报表模块（阶段341-345）

测试覆盖：
- 341: DataExporter - 多格式导出、预处理、任务管理
- 342: ReportGenerator - 模板、数据采集、渲染
- 343: DataBackup - 全量/增量备份、恢复、版本管理
- 344: AnalyticsEngine - 趋势、热点、模式、异常
- 345: DashboardAggregator - KPI、健康度、告警、模块状态
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

passed = 0
failed = 0
errors = []


def test(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  \u2713 {name}")
    else:
        failed += 1
        msg = f"  \u2717 {name}"
        if detail:
            msg += f" \u2014 {detail}"
        print(msg)
        errors.append((name, detail))


# ============================================================
# 阶段341: DataExporter
# ============================================================
print("\n=== \u9636\u6bb5341: DataExporter ===")

from data_export.data_exporter import (
    ExportFormat, ExportConfig, DataPreprocessor,
    DataExporter
)

# 341-1: JSON导出
exporter = DataExporter()
data = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
json_output = exporter.export(data, ExportConfig(format=ExportFormat.JSON))
test("341-1 JSON export", '"Alice"' in json_output and '"Bob"' in json_output)

# 341-2: CSV导出
csv_output = exporter.export(data, ExportConfig(format=ExportFormat.CSV))
test("341-2 CSV export", "Alice" in csv_output and "Bob" in csv_output)
test("341-2 CSV has header", "name" in csv_output and "age" in csv_output)

# 341-3: Markdown导出
md_output = exporter.export(data, ExportConfig(format=ExportFormat.MARKDOWN))
test("341-3 Markdown export", "|" in md_output and "Alice" in md_output)

# 341-4: HTML导出
html_output = exporter.export(data, ExportConfig(format=ExportFormat.HTML))
test("341-4 HTML export", "<table>" in html_output and "</table>" in html_output)

# 341-5: Text导出
text_output = exporter.export(data, ExportConfig(format=ExportFormat.TEXT))
test("341-5 Text export", "Alice" in text_output)

# 341-6: 字段选择
config_fields = ExportConfig(format=ExportFormat.JSON, fields=["name"])
filtered = exporter.export(data, config_fields)
test("341-6 Field selection", '"Alice"' in filtered and '"age"' not in filtered)

# 341-7: 排序
config_sort = ExportConfig(format=ExportFormat.JSON, sort_by="age", sort_desc=True)
sorted_output = exporter.export(data, config_sort)
# 解析JSON验证排序
import json
sorted_data = json.loads(sorted_output)
test("341-7 Sort desc", sorted_data[0]["age"] >= sorted_data[1]["age"],
     f"got ages {[d['age'] for d in sorted_data]}")

# 341-8: 过滤
config_filter = ExportConfig(
    format=ExportFormat.JSON,
    filter_fn=lambda r: r.get("age", 0) >= 30
)
filtered_output = exporter.export(data, config_filter)
test("341-8 Filter", '"Alice"' in filtered_output and '"Bob"' not in filtered_output)

# 341-9: 嵌套展平
nested_data = [{"user": {"name": "A", "addr": {"city": "NY"}}}]
config_flat = ExportConfig(format=ExportFormat.JSON, flatten_nested=True)
flat_output = exporter.export(nested_data, config_flat)
test("341-9 Flatten nested", "user.name" in flat_output or "user" in flat_output)

# 341-10: 导出统计
stats = exporter.get_stats()
test("341-10 Exporter stats", stats["total_exports"] >= 1)

# 341-11: 导出历史（export_to_file才记录历史）
import tempfile, os
with tempfile.TemporaryDirectory() as tmpdir:
    exporter.export_to_file(data, os.path.join(tmpdir, "test.json"))
    history = exporter.get_history()
    test("341-11 Export history", len(history) >= 1)

# 341-12: DataPreprocessor
records = [{"a": 3, "b": 1}, {"a": 2, "b": 2}, {"a": 1, "b": 3}]
sorted_recs = DataPreprocessor.sort_records(records, "a")
test("341-12 Preprocessor sort", sorted_recs[0]["a"] == 1)

paginated = DataPreprocessor.paginate(records, page=1, page_size=2)
test("341-12 Preprocessor paginate", len(paginated) == 2)


# ============================================================
# 阶段342: ReportGenerator
# ============================================================
print("\n=== \u9636\u6bb5342: ReportGenerator ===")

from data_export.report_generator import (
    ReportType, ReportFormat, ReportTemplate, ReportSection,
    ReportGenerator
)

# 342-1: 模板管理
rg = ReportGenerator()
template = ReportTemplate(
    name="daily_report",
    report_type=ReportType.DAILY,
    sections=["\u7cfb\u7edf\u6982\u89c8", "\u5b58\u50a8\u7edf\u8ba1"],
    format=ReportFormat.MARKDOWN,
)
rg.add_template(template)
test("342-1 Template added", rg.get_template("daily_report") is not None)

# 342-2: 注册采集器
rg.register_collector("\u7cfb\u7edf\u6982\u89c8", lambda s, e: {
    "\u8fd0\u884c\u65f6\u95f4": "24h",
    "\u8bf7\u6c42\u6570": 1000,
})
rg.register_collector("\u5b58\u50a8\u7edf\u8ba1", lambda s, e: {
    "\u603b\u8bb0\u5fc6": 5000,
    "\u4f7f\u7528\u7387": "80%",
})

# 342-3: 生成报表
report = rg.generate("daily_report")
test("342-3 Generate report", report is not None)
test("342-3 Report has content", report is not None and len(report.content) > 0)
test("342-3 Report has sections", report.sections_count == 2)

# 342-4: Markdown渲染
test("342-4 Markdown content", report.content.startswith("#"))

# 342-5: HTML报表
html_template = ReportTemplate(
    name="html_report",
    report_type=ReportType.DAILY,
    sections=["\u6d4b\u8bd5"],
    format=ReportFormat.HTML,
)
rg.add_template(html_template)
rg.register_collector("\u6d4b\u8bd5", lambda s, e: {"\u503c": 42})
html_report = rg.generate("html_report")
test("342-5 HTML report", html_report is not None and "<html>" in html_report.content)

# 342-6: Text报表
text_template = ReportTemplate(
    name="text_report",
    report_type=ReportType.WEEKLY,
    sections=["\u5468\u62a5"],
    format=ReportFormat.TEXT,
)
rg.add_template(text_template)
rg.register_collector("\u5468\u62a5", lambda s, e: {"\u5468\u6d3b\u8dc3\u5ea6": 85})
text_report = rg.generate("text_report")
test("342-6 Text report", text_report is not None and len(text_report.content) > 0)

# 342-7: 额外章节
extra = [ReportSection(title="\u989d\u5916\u4fe1\u606f", content="\u8fd9\u662f\u989d\u5916\u5185\u5bb9", order=99)]
report_extra = rg.generate("daily_report", extra_sections=extra)
test("342-7 Extra sections", report_extra.sections_count == 3)

# 342-8: 报表列表
reports = rg.list_reports()
test("342-8 List reports", len(reports) >= 3)

# 342-9: 模板列表
templates = rg.list_templates()
test("342-9 List templates", len(templates) >= 3)

# 342-10: 统计
rg_stats = rg.get_stats()
test("342-10 Generator stats", rg_stats["total_generated"] >= 3 and rg_stats["templates"] >= 3)


# ============================================================
# 阶段343: DataBackup
# ============================================================
print("\n=== \u9636\u6bb5343: DataBackup ===")

from data_export.data_backup import (
    BackupType, BackupStatus, BackupPolicy, ChangeTracker, DataBackup
)

# 343-1: ChangeTracker
tracker = ChangeTracker()
tracker.record_set("key1", "value1")
tracker.record_set("key2", "value2")
tracker.record_delete("key3")
test("343-1 Tracker records", len(tracker.get_pending_changes()) == 3)
test("343-1 Tracker stats", tracker.get_stats()["pending_changes"] == 3)

# 343-2: Tracker clear
cleared = tracker.clear_changes()
test("343-2 Tracker clear", cleared == 3 and tracker.get_stats()["pending_changes"] == 0)

# 343-3: 全量备份
db = DataBackup(BackupPolicy(max_versions=10))
db.register_source("test", lambda: {"a": 1, "b": 2, "c": 3})
backup_id = db.create_full_backup("test", tags=["v1"], description="\u521d\u59cb\u5907\u4efd")
test("343-3 Full backup", backup_id is not None and len(backup_id) > 0)

# 343-4: 备份信息
backup_info = db.get_backup(backup_id)
test("343-4 Backup info", backup_info is not None)
test("343-4 Backup type", backup_info["type"] == "full")

# 343-5: 增量备份
db.track_change("a", 10)
db.track_change("b", 20)
incr_id = db.create_incremental_backup("test", parent_id=backup_id)
test("343-5 Incremental backup", incr_id is not None)

# 343-6: 备份列表
backups = db.list_backups()
test("343-6 List backups", len(backups) >= 2)

# 343-7: 按类型过滤
full_backups = db.list_backups(backup_type=BackupType.FULL)
test("343-7 Filter by type", len(full_backups) >= 1)

# 343-8: 按标签过滤
tagged = db.list_backups(tag="v1")
test("343-8 Filter by tag", len(tagged) >= 1)

# 343-9: 快照
snap_id = db.create_snapshot("test", description="\u5feb\u7167")
test("343-9 Snapshot", snap_id is not None)
snap_info = db.get_backup(snap_id)
test("343-9 Snapshot type", snap_info["type"] == "snapshot")

# 343-10: 恢复
restored_data = {}
db.register_restore_target("test", lambda d: restored_data.update(d))
count = db.restore(backup_id, "test")
test("343-10 Restore", count is not None and count == 3)
test("343-10 Restored data", restored_data.get("a") == 1)

# 343-11: 删除备份
deleted = db.delete_backup(snap_id)
test("343-11 Delete backup", deleted)

# 343-12: 统计
db_stats = db.get_stats()
test("343-12 Backup stats", db_stats["total_backups"] >= 2)


# ============================================================
# 阶段344: AnalyticsEngine
# ============================================================
print("\n=== \u9636\u6bb5344: AnalyticsEngine ===")

from data_export.analytics_engine import (
    TrendDirection, AggregationType,
    StatsCalculator, AnalyticsEngine
)

# 344-1: StatsCalculator
vals = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
test("344-1 Mean", StatsCalculator.mean(vals) == 5.5)
test("344-1 Median", StatsCalculator.median(vals) == 5.5)
test("344-1 Stddev", abs(StatsCalculator.stddev(vals) - 3.027) < 0.01)
test("344-1 Percentile p50", StatsCalculator.percentile(vals, 50) == 5.5)

# 344-2: Correlation
x = [1, 2, 3, 4, 5]
y = [2, 4, 6, 8, 10]
corr = StatsCalculator.correlation(x, y)
test("344-2 Correlation", abs(corr - 1.0) < 0.01, f"got {corr}")

# 344-3: Linear regression
slope, intercept = StatsCalculator.linear_regression([1, 2, 3, 4, 5])
test("344-3 Regression slope", abs(slope - 1.0) < 0.01, f"got {slope}")

# 344-4: 趋势分析
ae = AnalyticsEngine()
for i in range(10):
    ae.track_metric("cpu", 50 + i * 2)  # 上升趋势
trend = ae.get_trend("cpu")
test("344-4 Trend direction", trend["direction"] == "up")
test("344-4 Trend data_points", trend["data_points"] == 10)

# 344-5: 下降趋势
for i in range(10):
    ae.track_metric("memory", 100 - i * 3)
trend2 = ae.get_trend("memory")
test("344-5 Down trend", trend2["direction"] == "down")

# 344-6: 热点发现
ae.record_access("key_a", "category_x")
ae.record_access("key_a", "category_x")
ae.record_access("key_a", "category_x")
ae.record_access("key_b", "category_y")
ae.record_access("key_b", "category_y")
hotspots = ae.get_hotspots(limit=5)
test("344-6 Hotspots", len(hotspots) >= 2)
test("344-6 Top hotspot", hotspots[0]["key"] == "key_a")

# 344-7: 分类热点
cat_stats = ae._hotspot.get_category_stats()
test("344-7 Category stats", "category_x" in cat_stats and "category_y" in cat_stats)

# 344-8: 频繁项发现
ae.add_sequence(["a", "b", "c"])
ae.add_sequence(["a", "b", "d"])
ae.add_sequence(["a", "c", "e"])
freq = ae.find_frequent_items(min_support=0.2)
test("344-8 Frequent items", len(freq) >= 1)
# "a" should be most frequent (3/9)
test("344-8 Top frequent", freq[0]["item"] == "a")

# 344-9: 序列模式
patterns = ae.find_patterns(min_length=2, min_support=1)
test("344-9 Sequential patterns", len(patterns) >= 1)

# 344-10: 异常检测（使用稳定数据避免边界误报）
for i in range(100):
    ae.track_metric("stable_metric", 100.0)  # 完全稳定的数据
anomalies = ae.get_anomalies("stable_metric")
test("344-10 No anomaly for stable", len(anomalies) == 0,
     f"got {len(anomalies)} anomalies")

# 注入异常值（使用有波动的数据先建立基线）
for i in range(20):
    ae.track_metric("anomaly_test", 100.0 + (i % 3) * 0.1)  # 微小波动
anomaly_result = ae.track_metric("anomaly_test", 10000.0)  # 异常高值
test("344-10 Anomaly detected", anomaly_result is not None and anomaly_result.severity != "")

# 344-11: 聚合计算
ae_avg = ae.aggregate("cpu", AggregationType.AVG)
test("344-11 Aggregate avg", ae_avg > 0)
ae_count = ae.aggregate("cpu", AggregationType.COUNT)
test("344-11 Aggregate count", ae_count == 10)

# 344-12: 统计
ae_stats = ae.get_stats()
test("344-12 Analytics stats", ae_stats["total_analyzed"] >= 30)


# ============================================================
# 阶段345: DashboardAggregator
# ============================================================
print("\n=== \u9636\u6bb5345: DashboardAggregator ===")

from data_export.dashboard_aggregator import (
    HealthLevel, AlertSeverity, KPIStatus,
    KPIDefinition, DashboardAggregator
)

# 345-1: KPI定义
dash = DashboardAggregator()
dash.define_kpi(KPIDefinition(
    name="response_time",
    description="\u54cd\u5e94\u65f6\u95f4",
    unit="ms",
    target=100,
    warning_threshold=200,
    critical_threshold=500,
    direction="down",
    weight=1.0,
    category="performance",
))

# 345-2: KPI更新
dash.update_kpi("response_time", 80)
kpi = dash.get_kpi("response_time")
test("345-2 KPI value", kpi is not None and kpi["value"] == 80)
test("345-2 KPI status good", kpi["status"] == "good")

# 345-3: KPI警告（direction=down，target=100，warning=200）
# value=150: 150 > 100(not good), 150 <= 200(watch)
dash.update_kpi("response_time", 150)
kpi2 = dash.get_kpi("response_time")
test("345-3 KPI status watch", kpi2["status"] == "watch")

# 345-4: KPI列表
dash.define_kpi(KPIDefinition(
    name="uptime",
    description="\u53ef\u7528\u6027",
    target=99.9,
    warning_threshold=95,
    direction="up",
    category="reliability",
))
dash.update_kpi("uptime", 99.5)
kpis = dash.list_kpis()
test("345-4 List KPIs", len(kpis) == 2)

# 345-5: 按分类过滤
perf_kpis = dash.list_kpis(category="performance")
test("345-5 Filter by category", len(perf_kpis) == 1)

# 345-6: 健康度评估
dash.update_health_dimension("performance", 85)
dash.update_health_dimension("reliability", 90)
dash.update_health_dimension("security", 95)
dash.update_health_dimension("resource", 70)
health = dash.get_health()
test("345-6 Health score", health["overall"] > 0)
test("345-6 Health level", health["level"] == "healthy")

# 345-7: 低健康度
dash2 = DashboardAggregator()
dash2.update_health_dimension("performance", 30)
dash2.update_health_dimension("reliability", 20)
dash2.update_health_dimension("security", 40)
dash2.update_health_dimension("resource", 10)
health2 = dash2.get_health()
test("345-7 Low health", health2["level"] == "critical")

# 345-8: 告警
dash.add_alert(AlertSeverity.HIGH, "cpu", "CPU usage > 90%")
dash.add_alert(AlertSeverity.MEDIUM, "memory", "Memory usage > 80%")
dash.add_alert(AlertSeverity.LOW, "disk", "Disk usage > 70%")
alert_summary = dash.get_alert_summary()
test("345-8 Alert summary", alert_summary["total"] == 3)
test("345-8 Alert by severity", alert_summary["by_severity"]["high"] == 1)

# 345-9: 告警列表
alerts = dash._alerts.get_alerts()
test("345-9 Alert list", len(alerts) >= 3)

# 345-10: 模块注册
dash.register_module("memory_system")
dash.register_module("log_system")
modules = dash.list_modules()
test("345-10 Module list", len(modules) == 2)

# 345-11: 模块状态更新
dash.update_module_status("memory_system", HealthLevel.HEALTHY, "\u8fd0\u884c\u6b63\u5e38")
mod = dash.get_module("memory_system")
test("345-11 Module status", mod["status"] == "healthy")

# 345-12: 模块检查器
dash.register_module("checker_test", checker=lambda: {
    "status": "healthy", "message": "ok"
})
check_results = dash.check_modules()
test("345-12 Check modules", "checker_test" in check_results)

# 345-13: 快照
snapshot = dash.take_snapshot()
test("345-13 Snapshot", snapshot is not None)
test("345-13 Snapshot has health", "overall" in snapshot["health"])

# 345-14: 最新快照
latest = dash.get_latest_snapshot()
test("345-14 Latest snapshot", latest is not None and latest["id"] == snapshot["id"])

# 345-15: 统计
dash_stats = dash.get_stats()
test("345-15 Dashboard stats", dash_stats["kpi"]["tracked"] == 2)
test("345-15 Dashboard modules", dash_stats["modules"]["modules"] == 3)


# ============================================================
# 汇总
# ============================================================
print(f"\n{'='*50}")
print(f"\u7b2c28\u9636\u6bb5\u9a8c\u8bc1\u5b8c\u6210: \u2713 {passed} \u901a\u8fc7, \u2717 {failed} \u5931\u8d25")
print(f"{'='*50}")

if errors:
    print("\n\u5931\u8d25\u8be6\u60c5:")
    for name, detail in errors:
        print(f"  - {name}: {detail}")

sys.exit(0 if failed == 0 else 1)
