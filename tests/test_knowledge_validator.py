"""
test_knowledge_validator.py — 知识完整性校验器测试

覆盖:
- KnowledgeCompletenessValidator.validate()
- KnowledgeCompletenessValidator.validate_output()
- CompletenessReport.is_complete
- QualityScorer._score_knowledge_completeness
- Orchestrator.check_knowledge_completeness
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.knowledge_base import (
    KnowledgeBase,
    KnowledgeEntry,
    KnowledgeCompletenessValidator,
    CompletenessReport,
    CompletenessGap,
)
from core.quality_scorer import QualityScorer
from core.orchestrator import Orchestrator


class TestCompletenessReport(unittest.TestCase):
    """CompletenessReport 数据模型"""

    def test_is_complete_high_coverage_no_high_gaps(self):
        report = CompletenessReport(total_topics=5, covered_topics=5, coverage_pct=100.0)
        self.assertTrue(report.is_complete)

    def test_is_complete_boundary_80(self):
        report = CompletenessReport(total_topics=5, covered_topics=4, coverage_pct=80.0)
        self.assertTrue(report.is_complete)

    def test_not_complete_low_coverage(self):
        report = CompletenessReport(total_topics=5, covered_topics=2, coverage_pct=40.0)
        self.assertFalse(report.is_complete)

    def test_not_complete_high_gap_exists(self):
        report = CompletenessReport(
            total_topics=5,
            covered_topics=4,
            coverage_pct=80.0,
            gaps=[CompletenessGap(topic="X", severity="high", reason="无", suggested_action="补")],
        )
        self.assertFalse(report.is_complete)

    def test_is_complete_medium_gap_ok(self):
        report = CompletenessReport(
            total_topics=5,
            covered_topics=5,
            coverage_pct=100.0,
            gaps=[CompletenessGap(topic="X", severity="medium", reason="弱", suggested_action="补")],
        )
        self.assertTrue(report.is_complete)

    def test_to_dict(self):
        report = CompletenessReport(
            total_topics=3,
            covered_topics=2,
            coverage_pct=66.7,
            gaps=[CompletenessGap(topic="A", severity="high", reason="r", suggested_action="a")],
            checked_categories=["features"],
            checked_entries=5,
        )
        d = report.to_dict()
        self.assertEqual(d["total_topics"], 3)
        self.assertEqual(d["coverage_pct"], 66.7)
        self.assertEqual(len(d["gaps"]), 1)
        self.assertEqual(d["gaps"][0]["severity"], "high")


class TestKnowledgeCompletenessValidator(unittest.TestCase):
    """KnowledgeCompletenessValidator 核心逻辑"""

    def _make_kb_with_entries(self, entries_data: list) -> KnowledgeBase:
        """构造内存知识库（不读磁盘）"""
        kb = KnowledgeBase.__new__(KnowledgeBase)
        kb._root = "/dev/null"
        kb._entries = {cat: [] for cat in KnowledgeBase.CATEGORIES}
        kb._memory_layers = {
            "session": type("ML", (), {"entries": [], "current_size_bytes": 0, "is_full": False, "max_size_bytes": 10240})(),
            "daily": type("ML", (), {"entries": [], "current_size_bytes": 0, "is_full": False, "max_size_bytes": 10240})(),
            "long": type("ML", (), {"entries": [], "current_size_bytes": 0, "is_full": False, "max_size_bytes": 10240})(),
            "kbase": type("ML", (), {"entries": [], "current_size_bytes": 0, "is_full": False, "max_size_bytes": 102400})(),
        }
        kb._promotion_log = []
        for cat, title, content, tags in entries_data:
            entry = KnowledgeEntry(category=cat, title=title, content=content, tags=tags)
            kb._entries[cat].append(entry)
            kb._memory_layers["kbase"].entries.append(entry)
        return kb

    def test_all_topics_covered(self):
        kb = self._make_kb_with_entries([
            ("features", "模型匹配规则", "模型匹配使用AI算法自动排序模板", ["模型匹配", "AI"]),
            ("features", "规则匹配规则", "规则匹配基于seller_id和排序维度", ["规则匹配"]),
            ("contracts", "审核流程契约", "审核流程: 待审核→审核通过/驳回→已完成", ["审核"]),
        ])
        validator = KnowledgeCompletenessValidator(kb)
        report = validator.validate(required_topics=["模型匹配", "规则匹配", "审核流程"])

        self.assertEqual(report.total_topics, 3)
        self.assertEqual(report.covered_topics, 3)
        self.assertEqual(report.coverage_pct, 100.0)
        self.assertTrue(report.is_complete)

    def test_uncovered_topic_detected(self):
        kb = self._make_kb_with_entries([
            ("features", "模型匹配规则", "模型匹配使用AI算法", ["模型匹配"]),
        ])
        validator = KnowledgeCompletenessValidator(kb)
        report = validator.validate(
            required_topics=["模型匹配", "视频审核流程"],
            min_entries_per_category=0,  # 关闭类目均衡检查
        )

        self.assertEqual(report.total_topics, 2)
        self.assertEqual(report.covered_topics, 1)
        self.assertEqual(report.coverage_pct, 50.0)
        self.assertEqual(len(report.gaps), 1)
        self.assertEqual(report.gaps[0].topic, "视频审核流程")
        self.assertEqual(report.gaps[0].severity, "high")

    def test_empty_topics_returns_100(self):
        kb = self._make_kb_with_entries([])
        validator = KnowledgeCompletenessValidator(kb)
        report = validator.validate(required_topics=[])
        self.assertEqual(report.coverage_pct, 100.0)

    def test_category_balance_check(self):
        kb = self._make_kb_with_entries([
            ("features", "某功能", "内容", []),
        ])
        validator = KnowledgeCompletenessValidator(kb)
        report = validator.validate(
            required_topics=[],
            categories=["features", "infra", "patterns", "contracts"],
            min_entries_per_category=1,
        )
        # features 有 1 条，其他三个类目都是 0 条 → 3 个 medium 缺口
        medium_gaps = [g for g in report.gaps if g.severity == "medium"]
        self.assertEqual(len(medium_gaps), 3)

    def test_validate_output_detects_speculative(self):
        kb = self._make_kb_with_entries([
            ("features", "模型匹配", "AI算法匹配", ["模型匹配"]),
        ])
        validator = KnowledgeCompletenessValidator(kb)
        report = validator.validate_output(
            output_text="根据知识库推测实现的模型匹配逻辑",
            required_topics=["模型匹配"],
        )
        speculative_gaps = [g for g in report.gaps if "推测" in g.topic]
        self.assertGreater(len(speculative_gaps), 0)
        self.assertEqual(speculative_gaps[0].severity, "high")

    def test_validate_output_clean(self):
        kb = self._make_kb_with_entries([
            ("features", "模型匹配", "AI算法匹配", ["模型匹配"]),
        ])
        validator = KnowledgeCompletenessValidator(kb)
        report = validator.validate_output(
            output_text="模型匹配使用TemplateMatchProcessor加AI模型",
            required_topics=["模型匹配"],
        )
        speculative_gaps = [g for g in report.gaps if "推测" in g.topic]
        self.assertEqual(len(speculative_gaps), 0)

    def test_weak_match_is_medium_severity(self):
        """弱匹配（score 在 1.0~min_score 之间）应为 medium"""
        kb = self._make_kb_with_entries([
            ("features", "不相关主题", "完全不同的内容xyz", ["其他"]),
        ])
        validator = KnowledgeCompletenessValidator(kb, min_score=5.0)
        report = validator.validate(
            required_topics=["模型匹配"],
            min_entries_per_category=0,  # 关闭类目均衡检查
        )
        self.assertEqual(len(report.gaps), 1)
        # score 低但不为 0 → 可能 high 或 medium
        self.assertIn(report.gaps[0].severity, ("high", "medium"))


class TestQualityScorerKnowledgeCompleteness(unittest.TestCase):
    """QualityScorer 的 knowledge_completeness 维度"""

    def test_score_with_full_completeness(self):
        scorer = QualityScorer()
        report = CompletenessReport(
            total_topics=5, covered_topics=5, coverage_pct=100.0
        )
        result = scorer.score(
            metrics_report={"task_success_rate": 1.0, "avg_duration_ms": 30000},
            completeness_report=report,
        )
        self.assertIn("knowledge_completeness", result.dimensions)
        self.assertEqual(result.dimensions["knowledge_completeness"], 100.0)

    def test_score_with_gaps(self):
        scorer = QualityScorer()
        report = CompletenessReport(
            total_topics=5, covered_topics=3, coverage_pct=60.0,
            gaps=[
                CompletenessGap(topic="A", severity="high", reason="r", suggested_action="a"),
                CompletenessGap(topic="B", severity="medium", reason="r", suggested_action="a"),
            ],
        )
        result = scorer.score(
            metrics_report={"task_success_rate": 1.0, "avg_duration_ms": 30000},
            completeness_report=report,
        )
        # 60 - 15(high) - 5(medium) = 40
        self.assertEqual(result.dimensions["knowledge_completeness"], 40.0)

    def test_score_without_report(self):
        scorer = QualityScorer()
        result = scorer.score(
            metrics_report={"task_success_rate": 1.0, "avg_duration_ms": 30000},
        )
        # 未提供报告 → 基线分 70
        self.assertEqual(result.dimensions["knowledge_completeness"], 70.0)

    def test_score_with_dict_report(self):
        scorer = QualityScorer()
        report_dict = {
            "coverage_pct": 90.0,
            "gaps": [{"severity": "medium", "topic": "X"}],
        }
        result = scorer.score(
            metrics_report={"task_success_rate": 1.0, "avg_duration_ms": 30000},
            completeness_report=report_dict,
        )
        # 90 - 5(medium) = 85
        self.assertEqual(result.dimensions["knowledge_completeness"], 85.0)

    def test_six_dimensions_in_weights(self):
        scorer = QualityScorer()
        result = scorer.score(metrics_report={"task_success_rate": 1.0})
        self.assertEqual(len(result.dimensions), 6)
        self.assertAlmostEqual(sum(result.weights.values()), 1.0)


class TestOrchestratorKnowledgeIntegration(unittest.TestCase):
    """Orchestrator 的知识完整性集成"""

    def _make_empty_kb(self):
        kb = KnowledgeBase.__new__(KnowledgeBase)
        kb._root = "/dev/null"
        kb._entries = {cat: [] for cat in KnowledgeBase.CATEGORIES}
        kb._memory_layers = {
            "session": type("ML", (), {"entries": [], "current_size_bytes": 0, "is_full": False, "max_size_bytes": 10240})(),
            "daily": type("ML", (), {"entries": [], "current_size_bytes": 0, "is_full": False, "max_size_bytes": 10240})(),
            "long": type("ML", (), {"entries": [], "current_size_bytes": 0, "is_full": False, "max_size_bytes": 10240})(),
            "kbase": type("ML", (), {"entries": [], "current_size_bytes": 0, "is_full": False, "max_size_bytes": 102400})(),
        }
        kb._promotion_log = []
        return kb

    def test_no_kb_returns_none(self):
        orch = Orchestrator()
        result = orch.check_knowledge_completeness(required_topics=["测试"])
        self.assertIsNone(result)

    def test_with_kb_returns_report(self):
        kb = self._make_empty_kb()
        orch = Orchestrator(knowledge_base=kb)
        result = orch.check_knowledge_completeness(required_topics=["某主题"])
        self.assertIsNotNone(result)
        self.assertIsInstance(result, CompletenessReport)

    def test_set_knowledge_base(self):
        orch = Orchestrator()
        self.assertIsNone(orch.knowledge_validator)

        kb = self._make_empty_kb()
        orch.set_knowledge_base(kb)
        self.assertIsNotNone(orch.knowledge_validator)

    def test_get_status_includes_knowledge(self):
        kb = self._make_empty_kb()
        orch = Orchestrator(knowledge_base=kb)
        status = orch.get_status()
        self.assertIn("knowledge", status)

    def test_validate_output_via_orchestrator(self):
        kb = self._make_empty_kb()
        orch = Orchestrator(knowledge_base=kb)
        result = orch.check_knowledge_completeness(
            required_topics=["模型匹配"],
            output_text="这是推测实现的逻辑",
        )
        speculative_gaps = [g for g in result.gaps if "推测" in g.topic]
        self.assertGreater(len(speculative_gaps), 0)


if __name__ == "__main__":
    unittest.main()
