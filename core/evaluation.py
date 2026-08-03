"""
evaluation.py — 五维评估与上线评级

差距 2.6 补齐。职责：
- 五维量化模型:
  - 功能正确性 30%（通过率、断言覆盖率）
  - 业务价值性 30%（提效比、覆盖域、交付时长）
  - 执行稳定性 20%（重试率、自愈率、波动率）
  - 性能效率 10%（平均耗时、P95 耗时）
  - 可扩展性 10%（模块复用率、配置化程度）
- 上线评级: A(全部达标) / B(灰度) / C(限场景) / D(拒绝)
- 雷达图数据生成: 输出 JSON 供可视化消费

使用方式:
    from core.evaluation import EvaluationEngine
    engine = EvaluationEngine()
    report = engine.evaluate(metrics)
    print(report.total_score, report.rating)
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import  Dict, List, Optional

# ── 数据模型 ──

@dataclass
class DimensionScore:
    """单维度评分"""
    name: str
    weight: float
    value: float  # 0-100 分

    @property
    def weighted_value(self) -> float:
        """加权分值"""
        return round(self.weight * self.value, 2)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "weight": self.weight,
            "value": self.value,
            "weighted_value": self.weighted_value,
        }

class RatingLevel(Enum):
    """上线评级等级"""
    A = "A"  # 全部达标，直接上线
    B = "B"  # 灰度上线
    C = "C"  # 限场景上线
    D = "D"  # 拒绝上线

@dataclass
class LaunchRating:
    """上线评级结果"""
    level: RatingLevel
    score: float
    details: str = ""

    def to_dict(self) -> dict:
        return {
            "level": self.level.value,
            "score": self.score,
            "details": self.details,
        }

    @classmethod
    def from_report(cls, report: "EvaluationReport") -> "LaunchRating":
        """从评估报告生成评级"""
        score = report.total_score

        if score >= 85:
            level = RatingLevel.A
            details = "全部达标，建议直接上线"
        elif score >= 70:
            level = RatingLevel.B
            details = "基本达标，建议灰度上线"
        elif score >= 50:
            level = RatingLevel.C
            details = "部分达标，限场景上线"
        else:
            level = RatingLevel.D
            details = "未达标，建议修复后重新评估"

        return cls(level=level, score=score, details=details)

@dataclass
class EvaluationReport:
    """五维评估报告"""
    dimensions: List[DimensionScore] = field(default_factory=list)
    total_score: float = 0.0
    rating: Optional[LaunchRating] = None
    evaluated_at: float = field(default_factory=time.time)
    metrics_raw: dict = field(default_factory=dict)

    def to_radar_data(self) -> dict:
        """生成雷达图数据"""
        # 确保始终有 5 个维度
        dim_names = ["功能正确性", "业务价值性", "执行稳定性", "性能效率", "可扩展性"]
        dim_map = {d.name: d for d in self.dimensions}

        radar_dims = []
        for name in dim_names:
            dim = dim_map.get(name)
            if dim:
                radar_dims.append(dim.to_dict())
            else:
                radar_dims.append({"name": name, "weight": 0, "value": 0, "weighted_value": 0})

        return {
            "dimensions": radar_dims,
            "total_score": self.total_score,
            "rating": self.rating.to_dict() if self.rating else None,
        }

    def to_dict(self) -> dict:
        return {
            "dimensions": [d.to_dict() for d in self.dimensions],
            "total_score": self.total_score,
            "rating": self.rating.to_dict() if self.rating else None,
            "evaluated_at": self.evaluated_at,
        }

# ── 评估引擎 ──

class EvaluationEngine:
    """
    五维评估引擎。

    基于输入指标计算五个维度的评分，生成评估报告和上线评级。
    """

    # 默认权重
    DEFAULT_WEIGHTS = {
        "功能正确性": 0.30,
        "业务价值性": 0.30,
        "执行稳定性": 0.20,
        "性能效率": 0.10,
        "可扩展性": 0.10,
    }

    # 评分阈值（各维度满分标准）
    THRESHOLDS = {
        "pass_rate": 0.95,              # 通过率满分线
        "assertion_coverage": 0.90,     # 断言覆盖率满分线
        "efficiency_ratio": 5.0,        # 提效比满分线（AI vs 人工）
        "coverage_domain": 1.0,         # 覆盖域满分线
        "delivery_hours": 4,            # 交付时长满分线（<=4h）
        "retry_rate": 0.05,             # 重试率满分线（<=5%）
        "self_heal_rate": 0.80,         # 自愈率满分线
        "fluctuation_rate": 0.02,       # 波动率满分线（<=2%）
        "avg_duration_ms": 2000,        # 平均耗时满分线（<=2s）
        "p95_duration_ms": 5000,        # P95 耗时满分线（<=5s）
        "module_reuse_rate": 0.80,      # 模块复用率满分线
        "config_ratio": 0.90,           # 配置化程度满分线
    }

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self._weights = weights or dict(self.DEFAULT_WEIGHTS)

    def evaluate(self, metrics: dict) -> EvaluationReport:
        """
        执行五维评估。

        Args:
            metrics: 指标字典，包含各类原始指标

        Returns:
            EvaluationReport
        """
        dimensions = []

        # 功能正确性 (pass_rate + assertion_coverage)
        correctness = self._calc_correctness(metrics)
        dimensions.append(DimensionScore(
            name="功能正确性",
            weight=self._weights.get("功能正确性", 0.3),
            value=correctness,
        ))

        # 业务价值性 (efficiency_ratio + coverage_domain + delivery_hours)
        business_value = self._calc_business_value(metrics)
        dimensions.append(DimensionScore(
            name="业务价值性",
            weight=self._weights.get("业务价值性", 0.3),
            value=business_value,
        ))

        # 执行稳定性 (retry_rate + self_heal_rate + fluctuation_rate)
        stability = self._calc_stability(metrics)
        dimensions.append(DimensionScore(
            name="执行稳定性",
            weight=self._weights.get("执行稳定性", 0.2),
            value=stability,
        ))

        # 性能效率 (avg_duration_ms + p95_duration_ms)
        performance = self._calc_performance(metrics)
        dimensions.append(DimensionScore(
            name="性能效率",
            weight=self._weights.get("性能效率", 0.1),
            value=performance,
        ))

        # 可扩展性 (module_reuse_rate + config_ratio)
        scalability = self._calc_scalability(metrics)
        dimensions.append(DimensionScore(
            name="可扩展性",
            weight=self._weights.get("可扩展性", 0.1),
            value=scalability,
        ))

        total_score = sum(d.weighted_value for d in dimensions)

        report = EvaluationReport(
            dimensions=dimensions,
            total_score=round(total_score, 2),
            metrics_raw=metrics,
        )
        report.rating = LaunchRating.from_report(report)

        return report

    def _calc_correctness(self, metrics: dict) -> float:
        """计算功能正确性分值 (0-100)"""
        pass_rate = metrics.get("pass_rate", 0)
        assertion_coverage = metrics.get("assertion_coverage", 0)

        pass_score = min(pass_rate / self.THRESHOLDS["pass_rate"], 1.0) * 100
        assertion_score = min(assertion_coverage / self.THRESHOLDS["assertion_coverage"], 1.0) * 100

        return round((pass_score * 0.6 + assertion_score * 0.4), 2)

    def _calc_business_value(self, metrics: dict) -> float:
        """计算业务价值性分值 (0-100)"""
        efficiency = metrics.get("efficiency_ratio", 1.0)
        coverage = metrics.get("coverage_domain", 0)
        delivery = metrics.get("delivery_hours", 100)

        eff_score = min(efficiency / self.THRESHOLDS["efficiency_ratio"], 1.0) * 100
        cov_score = min(coverage / self.THRESHOLDS["coverage_domain"], 1.0) * 100
        # 交付时长越短越好
        del_score = max(0, min(1.0, self.THRESHOLDS["delivery_hours"] / max(delivery, 1))) * 100

        return round((eff_score * 0.4 + cov_score * 0.3 + del_score * 0.3), 2)

    def _calc_stability(self, metrics: dict) -> float:
        """计算执行稳定性分值 (0-100)"""
        retry_rate = metrics.get("retry_rate", 1.0)
        self_heal_rate = metrics.get("self_heal_rate", 0)
        fluctuation = metrics.get("fluctuation_rate", 1.0)

        # 重试率越低越好
        retry_score = max(0, min(1.0, self.THRESHOLDS["retry_rate"] / max(retry_rate, 0.001))) * 100
        heal_score = min(self_heal_rate / self.THRESHOLDS["self_heal_rate"], 1.0) * 100
        # 波动率越低越好
        fluct_score = max(0, min(1.0, self.THRESHOLDS["fluctuation_rate"] / max(fluctuation, 0.001))) * 100

        return round((retry_score * 0.3 + heal_score * 0.4 + fluct_score * 0.3), 2)

    def _calc_performance(self, metrics: dict) -> float:
        """计算性能效率分值 (0-100)"""
        avg_ms = metrics.get("avg_duration_ms", 99999)
        p95_ms = metrics.get("p95_duration_ms", 99999)

        avg_score = max(0, min(1.0, self.THRESHOLDS["avg_duration_ms"] / max(avg_ms, 1))) * 100
        p95_score = max(0, min(1.0, self.THRESHOLDS["p95_duration_ms"] / max(p95_ms, 1))) * 100

        return round((avg_score * 0.5 + p95_score * 0.5), 2)

    def _calc_scalability(self, metrics: dict) -> float:
        """计算可扩展性分值 (0-100)"""
        reuse = metrics.get("module_reuse_rate", 0)
        config = metrics.get("config_ratio", 0)

        reuse_score = min(reuse / self.THRESHOLDS["module_reuse_rate"], 1.0) * 100
        config_score = min(config / self.THRESHOLDS["config_ratio"], 1.0) * 100

        return round((reuse_score * 0.5 + config_score * 0.5), 2)

    def get_weights(self) -> Dict[str, float]:
        """获取当前权重配置"""
        return dict(self._weights)

    def set_weights(self, weights: Dict[str, float]):
        """更新权重配置"""
        self._weights.update(weights)

    @classmethod
    def from_config(cls, config_path: str) -> "EvaluationEngine":
        """从配置文件加载"""
        try:
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            weights = data.get("weights", {})
            return cls(weights=weights)
        except (ImportError, FileNotFoundError):
            return cls()
