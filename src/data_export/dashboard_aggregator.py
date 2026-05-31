#!/usr/bin/env python3
"""
仪表盘聚合器 (DashboardAggregator) - 阶段345

职责：
- KPI管理：关键指标定义、阈值、目标
- 健康度评分：多维度系统健康评估
- 告警摘要：聚合告警信息
- 模块状态：聚合各子系统状态
- 仪表盘快照：定时生成系统快照

设计原则：
- 确定性规则，无模型依赖
- 线程安全（RLock）
- 最小层级，无循环依赖
"""

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


# ============================================================
# 枚举与数据结构
# ============================================================

class HealthLevel(Enum):
    """健康等级"""
    HEALTHY = "healthy"       # 健康
    WARNING = "warning"       # 警告
    CRITICAL = "critical"     # 严重
    UNKNOWN = "unknown"       # 未知


class AlertSeverity(Enum):
    """告警级别"""
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class KPIStatus(Enum):
    """KPI状态"""
    GOOD = "good"           # 达标
    WATCH = "watch"         # 需关注
    BAD = "bad"             # 不达标
    UNKNOWN = "unknown"     # 未知


@dataclass
class KPIDefinition:
    """KPI定义"""
    name: str
    description: str = ""
    unit: str = ""
    target: float = 0.0           # 目标值
    warning_threshold: float = 0.0  # 警告阈值
    critical_threshold: float = 0.0  # 严重阈值
    direction: str = "up"         # up=越高越好, down=越低越好
    weight: float = 1.0            # 权重
    category: str = "general"      # 分类
    collector: Optional[Callable[[], float]] = None  # 采集函数


@dataclass
class KPIValue:
    """KPI当前值"""
    name: str
    value: float = 0.0
    status: KPIStatus = KPIStatus.UNKNOWN
    change: float = 0.0          # 变化量
    change_percent: float = 0.0   # 变化百分比
    last_updated: float = 0.0
    history: List[float] = field(default_factory=list)


@dataclass
class ModuleStatus:
    """模块状态"""
    name: str
    status: HealthLevel = HealthLevel.UNKNOWN
    message: str = ""
    last_check: float = 0.0
    metrics: Dict[str, Any] = field(default_factory=dict)
    uptime: float = 0.0


@dataclass
class AlertSummary:
    """告警摘要"""
    severity: AlertSeverity
    count: int = 0
    latest: float = 0.0
    source: str = ""
    message: str = ""


@dataclass
class HealthScore:
    """健康度评分"""
    overall: float = 0.0           # 总分 0-100
    performance: float = 0.0       # 性能分
    reliability: float = 0.0       # 可靠性分
    security: float = 0.0          # 安全分
    resource: float = 0.0          # 资源分
    level: HealthLevel = HealthLevel.UNKNOWN
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DashboardSnapshot:
    """仪表盘快照"""
    id: str = ""
    timestamp: float = 0.0
    health_score: Dict[str, Any] = field(default_factory=dict)
    kpis: Dict[str, Any] = field(default_factory=dict)
    modules: Dict[str, Any] = field(default_factory=dict)
    alerts: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()
        if not self.id:
            import uuid
            self.id = uuid.uuid4().hex[:12]


# ============================================================
# KPI管理器
# ============================================================

class KPIManager:
    """
    KPI管理器

    核心功能：
    1. KPI定义与注册
    2. KPI值采集与更新
    3. KPI状态评估
    4. KPI历史记录
    """

    def __init__(self, history_size: int = 100):
        self._definitions: Dict[str, KPIDefinition] = {}
        self._values: Dict[str, KPIValue] = {}
        self._history_size = history_size
        self._lock = threading.RLock()

    def define(self, definition: KPIDefinition) -> None:
        """定义KPI"""
        with self._lock:
            self._definitions[definition.name] = definition
            if definition.name not in self._values:
                self._values[definition.name] = KPIValue(name=definition.name)

    def update(self, name: str, value: float) -> None:
        """更新KPI值"""
        with self._lock:
            kpi_val = self._values.get(name)
            if kpi_val is None:
                kpi_val = KPIValue(name=name)
                self._values[name] = kpi_val

            old_value = kpi_val.value
            kpi_val.value = value
            kpi_val.last_updated = time.time()
            kpi_val.change = value - old_value
            if old_value != 0:
                kpi_val.change_percent = ((value - old_value) / abs(old_value)) * 100

            # 保存历史
            kpi_val.history.append(value)
            if len(kpi_val.history) > self._history_size:
                kpi_val.history = kpi_val.history[-self._history_size:]

            # 评估状态
            definition = self._definitions.get(name)
            if definition:
                kpi_val.status = self._evaluate_status(
                    value, definition
                )

    def collect_all(self) -> None:
        """采集所有KPI"""
        with self._lock:
            definitions = list(self._definitions.values())
        for defn in definitions:
            if defn.collector:
                try:
                    value = defn.collector()
                    self.update(defn.name, value)
                except Exception:
                    pass

    def _evaluate_status(self, value: float,
                         definition: KPIDefinition) -> KPIStatus:
        """评估KPI状态"""
        if definition.direction == "up":
            if value >= definition.target:
                return KPIStatus.GOOD
            elif value >= definition.warning_threshold:
                return KPIStatus.WATCH
            else:
                return KPIStatus.BAD
        else:  # down
            if value <= definition.target:
                return KPIStatus.GOOD
            elif value <= definition.warning_threshold:
                return KPIStatus.WATCH
            else:
                return KPIStatus.BAD

    def get_kpi(self, name: str) -> Optional[Dict[str, Any]]:
        """获取KPI"""
        with self._lock:
            val = self._values.get(name)
            defn = self._definitions.get(name)
            if val is None:
                return None
            return {
                "name": val.name,
                "value": val.value,
                "status": val.status.value,
                "change": val.change,
                "change_percent": round(val.change_percent, 2),
                "last_updated": val.last_updated,
                "definition": {
                    "target": defn.target,
                    "unit": defn.unit,
                    "category": defn.category,
                    "direction": defn.direction,
                } if defn else None,
            }

    def list_kpis(self, category: str = "") -> List[Dict[str, Any]]:
        """列出所有KPI"""
        with self._lock:
            items = []
            for name, val in self._values.items():
                defn = self._definitions.get(name)
                if category and defn and defn.category != category:
                    continue
                items.append({
                    "name": val.name,
                    "value": val.value,
                    "status": val.status.value,
                    "category": defn.category if defn else "",
                })
            return items

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            status_counts = defaultdict(int)
            for val in self._values.values():
                status_counts[val.status.value] += 1
            return {
                "total_kpis": len(self._definitions),
                "tracked": len(self._values),
                "by_status": dict(status_counts),
            }


# ============================================================
# 健康度评估器
# ============================================================

class HealthEvaluator:
    """
    健康度评估器

    核心功能：
    1. 多维度健康评估
    2. 加权评分
    3. 健康等级判定
    """

    def __init__(self):
        self._dimensions: Dict[str, Dict[str, Any]] = {
            "performance": {"weight": 0.3, "score": 100.0},
            "reliability": {"weight": 0.3, "score": 100.0},
            "security": {"weight": 0.2, "score": 100.0},
            "resource": {"weight": 0.2, "score": 100.0},
        }
        self._lock = threading.RLock()

    def update_dimension(self, name: str, score: float) -> None:
        """更新维度分数"""
        with self._lock:
            if name in self._dimensions:
                self._dimensions[name]["score"] = max(0, min(100, score))

    def evaluate(self) -> HealthScore:
        """评估整体健康度"""
        with self._lock:
            dims = dict(self._dimensions)

        scores = {}
        total_weight = 0
        weighted_sum = 0

        for name, info in dims.items():
            scores[name] = info["score"]
            weighted_sum += info["score"] * info["weight"]
            total_weight += info["weight"]

        overall = weighted_sum / total_weight if total_weight > 0 else 0

        # 健康等级
        if overall >= 80:
            level = HealthLevel.HEALTHY
        elif overall >= 60:
            level = HealthLevel.WARNING
        elif overall >= 30:
            level = HealthLevel.CRITICAL
        else:
            level = HealthLevel.CRITICAL

        return HealthScore(
            overall=round(overall, 2),
            performance=round(scores.get("performance", 0), 2),
            reliability=round(scores.get("reliability", 0), 2),
            security=round(scores.get("security", 0), 2),
            resource=round(scores.get("resource", 0), 2),
            level=level,
            details=dict(scores),
        )

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "dimensions": {
                    k: {"weight": v["weight"], "score": v["score"]}
                    for k, v in self._dimensions.items()
                }
            }


# ============================================================
# 告警聚合器
# ============================================================

class AlertAggregator:
    """
    告警聚合器

    核心功能：
    1. 告警记录
    2. 按级别聚合
    3. 告警统计
    4. 告警清除
    """

    def __init__(self, max_alerts: int = 1000):
        self._alerts: List[AlertSummary] = []
        self._max_alerts = max_alerts
        self._lock = threading.RLock()

    def add_alert(self, severity: AlertSeverity, source: str = "",
                  message: str = "") -> None:
        """添加告警"""
        alert = AlertSummary(
            severity=severity,
            count=1,
            latest=time.time(),
            source=source,
            message=message,
        )
        with self._lock:
            self._alerts.append(alert)
            if len(self._alerts) > self._max_alerts:
                self._alerts = self._alerts[-self._max_alerts:]

    def get_summary(self) -> Dict[str, Any]:
        """获取告警摘要"""
        with self._lock:
            severity_counts = defaultdict(int)
            latest_by_severity = {}
            for alert in self._alerts:
                severity_counts[alert.severity.value] += 1
                key = alert.severity.value
                if key not in latest_by_severity or alert.latest > latest_by_severity[key]["latest"]:
                    latest_by_severity[key] = {
                        "source": alert.source,
                        "message": alert.message,
                        "latest": alert.latest,
                    }

            return {
                "total": len(self._alerts),
                "by_severity": dict(severity_counts),
                "latest": latest_by_severity,
            }

    def get_alerts(self, severity: Optional[AlertSeverity] = None,
                   limit: int = 50) -> List[Dict[str, Any]]:
        """获取告警列表"""
        with self._lock:
            items = self._alerts
            if severity:
                items = [a for a in items if a.severity == severity]
            return [
                {
                    "severity": a.severity.value,
                    "count": a.count,
                    "source": a.source,
                    "message": a.message,
                    "latest": a.latest,
                }
                for a in reversed(items[-limit:])
            ]

    def clear(self, severity: Optional[AlertSeverity] = None) -> int:
        """清除告警"""
        with self._lock:
            if severity:
                before = len(self._alerts)
                self._alerts = [a for a in self._alerts
                                if a.severity != severity]
                return before - len(self._alerts)
            else:
                count = len(self._alerts)
                self._alerts.clear()
                return count

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            severity_counts = defaultdict(int)
            for a in self._alerts:
                severity_counts[a.severity.value] += 1
            return {
                "total_alerts": len(self._alerts),
                "by_severity": dict(severity_counts),
                "max_alerts": self._max_alerts,
            }


# ============================================================
# 模块状态管理器
# ============================================================

class ModuleStatusManager:
    """
    模块状态管理器

    核心功能：
    1. 注册模块
    2. 更新模块状态
    3. 聚合模块信息
    """

    def __init__(self):
        self._modules: Dict[str, ModuleStatus] = {}
        self._checkers: Dict[str, Callable[[], Dict[str, Any]]] = {}
        self._lock = threading.RLock()

    def register(self, name: str,
                 checker: Optional[Callable[[], Dict[str, Any]]] = None) -> None:
        """注册模块"""
        with self._lock:
            self._modules[name] = ModuleStatus(
                name=name,
                last_check=time.time(),
            )
            if checker:
                self._checkers[name] = checker

    def update_status(self, name: str, status: HealthLevel,
                      message: str = "",
                      metrics: Optional[Dict[str, Any]] = None) -> None:
        """更新模块状态"""
        with self._lock:
            module = self._modules.get(name)
            if module:
                module.status = status
                module.message = message
                module.last_check = time.time()
                if metrics:
                    module.metrics.update(metrics)

    def check_all(self) -> Dict[str, Any]:
        """检查所有模块"""
        results = {}
        with self._lock:
            checkers = dict(self._checkers)

        for name, checker in checkers.items():
            try:
                info = checker()
                status = HealthLevel.HEALTHY
                message = ""
                if isinstance(info, dict):
                    status_str = info.get("status", "healthy")
                    status = HealthLevel(status_str) if isinstance(status_str, str) else HealthLevel.HEALTHY
                    message = info.get("message", "")
                self.update_status(name, status, message, info if isinstance(info, dict) else {})
                results[name] = {"status": status.value, "message": message}
            except Exception as e:
                self.update_status(name, HealthLevel.CRITICAL, str(e))
                results[name] = {"status": "critical", "message": str(e)}

        return results

    def get_module(self, name: str) -> Optional[Dict[str, Any]]:
        """获取模块状态"""
        with self._lock:
            m = self._modules.get(name)
            if m is None:
                return None
            return {
                "name": m.name,
                "status": m.status.value,
                "message": m.message,
                "last_check": m.last_check,
                "metrics": m.metrics,
            }

    def list_modules(self) -> List[Dict[str, Any]]:
        """列出所有模块"""
        with self._lock:
            return [
                {
                    "name": m.name,
                    "status": m.status.value,
                    "message": m.message,
                    "last_check": m.last_check,
                }
                for m in self._modules.values()
            ]

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            status_counts = defaultdict(int)
            for m in self._modules.values():
                status_counts[m.status.value] += 1
            return {
                "modules": len(self._modules),
                "by_status": dict(status_counts),
            }


# ============================================================
# 仪表盘聚合器
# ============================================================

class DashboardAggregator:
    """
    仪表盘聚合器

    核心功能：
    1. KPI管理
    2. 健康度评估
    3. 告警聚合
    4. 模块状态
    5. 仪表盘快照
    """

    def __init__(self):
        self._kpi = KPIManager()
        self._health = HealthEvaluator()
        self._alerts = AlertAggregator()
        self._modules = ModuleStatusManager()
        self._snapshots: List[DashboardSnapshot] = []
        self._lock = threading.RLock()
        self._snapshot_interval = 300.0  # 5分钟
        self._last_snapshot: float = 0.0

    # ---- KPI ----

    def define_kpi(self, definition: KPIDefinition) -> None:
        """定义KPI"""
        self._kpi.define(definition)

    def update_kpi(self, name: str, value: float) -> None:
        """更新KPI值"""
        self._kpi.update(name, value)

    def get_kpi(self, name: str) -> Optional[Dict[str, Any]]:
        return self._kpi.get_kpi(name)

    def list_kpis(self, category: str = "") -> List[Dict[str, Any]]:
        return self._kpi.list_kpis(category)

    # ---- 健康度 ----

    def update_health_dimension(self, name: str, score: float) -> None:
        """更新健康维度"""
        self._health.update_dimension(name, score)

    def get_health(self) -> Dict[str, Any]:
        """获取健康度"""
        score = self._health.evaluate()
        return {
            "overall": score.overall,
            "level": score.level.value,
            "performance": score.performance,
            "reliability": score.reliability,
            "security": score.security,
            "resource": score.resource,
        }

    # ---- 告警 ----

    def add_alert(self, severity: AlertSeverity, source: str = "",
                  message: str = "") -> None:
        """添加告警"""
        self._alerts.add_alert(severity, source, message)

    def get_alert_summary(self) -> Dict[str, Any]:
        """获取告警摘要"""
        return self._alerts.get_summary()

    # ---- 模块状态 ----

    def register_module(self, name: str,
                        checker: Optional[Callable[[], Dict[str, Any]]] = None) -> None:
        """注册模块"""
        self._modules.register(name, checker)

    def update_module_status(self, name: str, status: HealthLevel,
                             message: str = "") -> None:
        """更新模块状态"""
        self._modules.update_status(name, status, message)

    def check_modules(self) -> Dict[str, Any]:
        """检查所有模块"""
        return self._modules.check_all()

    def get_module(self, name: str) -> Optional[Dict[str, Any]]:
        """获取模块状态"""
        return self._modules.get_module(name)

    def list_modules(self) -> List[Dict[str, Any]]:
        """列出模块"""
        return self._modules.list_modules()

    # ---- 快照 ----

    def take_snapshot(self) -> Dict[str, Any]:
        """生成仪表盘快照"""
        snapshot = DashboardSnapshot(
            health_score=self.get_health(),
            kpis={
                "total": len(self._kpi.list_kpis()),
                "items": self._kpi.list_kpis(),
            },
            modules={
                "total": len(self._modules.list_modules()),
                "items": self._modules.list_modules(),
            },
            alerts=self._alerts.get_summary(),
        )

        with self._lock:
            self._snapshots.append(snapshot)
            self._last_snapshot = time.time()

        return {
            "id": snapshot.id,
            "timestamp": snapshot.timestamp,
            "health": snapshot.health_score,
            "kpis": snapshot.kpis,
            "modules": snapshot.modules,
            "alerts": snapshot.alerts,
        }

    def get_latest_snapshot(self) -> Optional[Dict[str, Any]]:
        """获取最新快照"""
        with self._lock:
            if not self._snapshots:
                return None
            s = self._snapshots[-1]
            return {
                "id": s.id,
                "timestamp": s.timestamp,
                "health": s.health_score,
                "kpis": s.kpis,
                "modules": s.modules,
                "alerts": s.alerts,
            }

    def auto_snapshot(self) -> Optional[Dict[str, Any]]:
        """自动快照（按间隔）"""
        now = time.time()
        with self._lock:
            if now - self._last_snapshot < self._snapshot_interval:
                return None
        return self.take_snapshot()

    # ---- 统计 ----

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "kpi": self._kpi.get_stats(),
                "health": self._health.get_stats(),
                "alerts": self._alerts.get_stats(),
                "modules": self._modules.get_stats(),
                "snapshots": len(self._snapshots),
                "snapshot_interval": self._snapshot_interval,
            }


# ============================================================
# 全局单例
# ============================================================

_dashboard: Optional[DashboardAggregator] = None
_dash_lock = threading.RLock()


def get_dashboard() -> DashboardAggregator:
    """获取全局仪表盘聚合器"""
    global _dashboard
    if _dashboard is None:
        with _dash_lock:
            if _dashboard is None:
                _dashboard = DashboardAggregator()
    return _dashboard
