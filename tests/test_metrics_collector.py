"""
test_metrics_collector.py — MetricsCollector 单元测试

验证：
- 五大核心指标计算（task_success_rate / avg_task_duration / cost_per_task / false_positive_rate / change_frequency）
- 业务差异化指标计算（llm_confidence_avg / self_heal_success_rate / compliance_intercept_count / visual_evidence_score）
- MetricsReport 序列化（to_dict / to_summary_dict）
- 边界情况（空日志、无 LLM 调用、无 assert 步骤）
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.metrics_logger import MetricLogEntry, MetricsLogger, ErrorCode
from core.metrics_collector import MetricsCollector, MetricsReport, CoreMetrics, BusinessMetrics


def _make_entry(**kwargs) -> MetricLogEntry:
    """快速构造测试用 MetricLogEntry"""
    defaults = {
        "task_id": "test-001",
        "business_type": "f88_material",
        "step": "click",
        "action": "test",
        "result": "success",
        "duration_ms": 100,
    }
    defaults.update(kwargs)
    return MetricLogEntry(**defaults)


class TestCoreMetrics(unittest.TestCase):
    """核心统一指标计算测试"""

    def test_task_success_rate_pass(self):
        collector = MetricsCollector(
            task_id="t1", business_type="f88_material",
            overall_status="pass", task_duration_ms=5000,
        )
        entries = [_make_entry()]
        report = collector.compute(entries)
        self.assertEqual(report.core_metrics.task_success_rate, 1.0)

    def test_task_success_rate_fail(self):
        collector = MetricsCollector(
            task_id="t2", business_type="f88_material",
            overall_status="fail", task_duration_ms=5000,
        )
        entries = [_make_entry(result="failed")]
        report = collector.compute(entries)
        self.assertEqual(report.core_metrics.task_success_rate, 0.0)

    def test_avg_task_duration(self):
        collector = MetricsCollector(
            task_id="t3", business_type="f88_material",
            overall_status="pass", task_duration_ms=12345,
        )
        entries = [_make_entry(duration_ms=100), _make_entry(duration_ms=200)]
        report = collector.compute(entries)
        # avg_task_duration 使用 task_duration_ms（任务级耗时）
        self.assertEqual(report.core_metrics.avg_task_duration_ms, 12345)

    def test_cost_per_task_with_llm(self):
        collector = MetricsCollector(
            task_id="t4", business_type="f88_material",
            overall_status="pass", task_duration_ms=5000,
        )
        entries = [
            _make_entry(step="click", duration_ms=100),
            _make_entry(step="llm_plan", token_used=500, confidence=0.9),
            _make_entry(step="llm_assert", token_used=300, confidence=0.85),
        ]
        report = collector.compute(entries)
        self.assertEqual(report.core_metrics.cost_per_task, 800)

    def test_cost_per_task_no_llm(self):
        collector = MetricsCollector(
            task_id="t5", business_type="xiaoer",
            overall_status="pass", task_duration_ms=3000,
        )
        entries = [_make_entry(step="click"), _make_entry(step="fill")]
        report = collector.compute(entries)
        self.assertEqual(report.core_metrics.cost_per_task, 0)

    def test_false_positive_rate_with_asserts(self):
        collector = MetricsCollector(
            task_id="t6", business_type="f88_material",
            overall_status="pass", task_duration_ms=5000,
        )
        entries = [
            _make_entry(step="assert", action="断言1", is_false_positive=False),
            _make_entry(step="assert", action="断言2", is_false_positive=True),
            _make_entry(step="assert", action="断言3", is_false_positive=False),
            _make_entry(step="assert", action="断言4"),  # None = 非误报
        ]
        report = collector.compute(entries)
        # 4 个 assert 步骤，1 个误报 → 0.25
        self.assertAlmostEqual(report.core_metrics.false_positive_rate, 0.25)

    def test_false_positive_rate_no_asserts(self):
        collector = MetricsCollector(
            task_id="t7", business_type="xiaoer",
            overall_status="pass", task_duration_ms=3000,
        )
        entries = [_make_entry(step="click"), _make_entry(step="fill")]
        report = collector.compute(entries)
        self.assertEqual(report.core_metrics.false_positive_rate, 0.0)

    def test_empty_entries(self):
        collector = MetricsCollector(
            task_id="t8", business_type="smoke",
            overall_status="error", task_duration_ms=0,
        )
        report = collector.compute([])
        self.assertEqual(report.core_metrics.task_success_rate, 0.0)
        self.assertEqual(report.core_metrics.cost_per_task, 0)
        self.assertEqual(report.raw_log_count, 0)


class TestBusinessMetrics(unittest.TestCase):
    """业务差异化指标计算测试"""

    def test_llm_confidence_avg(self):
        collector = MetricsCollector(
            task_id="t10", business_type="original_protection",
            overall_status="pass", task_duration_ms=5000,
        )
        entries = [
            _make_entry(step="llm_plan", token_used=500, confidence=0.9),
            _make_entry(step="llm_assert", token_used=300, confidence=0.8),
            _make_entry(step="llm_heal", token_used=200, confidence=0.6),
        ]
        report = collector.compute(entries)
        # (0.9 + 0.8 + 0.6) / 3 = 0.7667
        self.assertAlmostEqual(report.business_metrics.llm_confidence_avg, 0.7667, places=3)

    def test_llm_confidence_none_when_no_llm(self):
        collector = MetricsCollector(
            task_id="t11", business_type="xiaoer",
            overall_status="pass", task_duration_ms=3000,
        )
        entries = [_make_entry(step="click"), _make_entry(step="fill")]
        report = collector.compute(entries)
        self.assertIsNone(report.business_metrics.llm_confidence_avg)

    def test_self_heal_success_rate(self):
        collector = MetricsCollector(
            task_id="t12", business_type="original_protection",
            overall_status="pass", task_duration_ms=5000,
        )
        entries = [
            # 组1: retrying → success (成功自愈)
            _make_entry(step="click", action="点击搜索", result="retrying"),
            _make_entry(step="click", action="点击搜索", result="success"),
            # 组2: retrying → failed (自愈失败)
            _make_entry(step="fill", action="填写表单", result="retrying"),
            _make_entry(step="fill", action="填写表单", result="failed"),
            # 组3: retrying → retrying → success (多次重试后成功)
            _make_entry(step="navigate", action="导航", result="retrying"),
            _make_entry(step="navigate", action="导航", result="retrying"),
            _make_entry(step="navigate", action="导航", result="success"),
        ]
        report = collector.compute(entries)
        # 4 次 retrying（组1:1次, 组2:1次, 组3:2次），3 次后续成功 → 3/4
        self.assertAlmostEqual(report.business_metrics.self_heal_success_rate, 0.75)

    def test_self_heal_none_when_no_retries(self):
        collector = MetricsCollector(
            task_id="t13", business_type="xiaoer",
            overall_status="pass", task_duration_ms=3000,
        )
        entries = [_make_entry(result="success"), _make_entry(result="success")]
        report = collector.compute(entries)
        self.assertIsNone(report.business_metrics.self_heal_success_rate)

    def test_compliance_intercept_count(self):
        collector = MetricsCollector(
            task_id="t14", business_type="original_protection",
            overall_status="pass", task_duration_ms=5000,
        )
        entries = [
            _make_entry(error_code=ErrorCode.COMPLIANCE_BLOCKED),
            _make_entry(error_code=ErrorCode.COMPLIANCE_BLOCKED),
            _make_entry(error_code=ErrorCode.TIMEOUT),
            _make_entry(),  # 无错误码
        ]
        report = collector.compute(entries)
        self.assertEqual(report.business_metrics.compliance_intercept_count, 2)

    def test_visual_evidence_score_with_screenshots(self):
        collector = MetricsCollector(
            task_id="t15", business_type="original_protection",
            overall_status="pass", task_duration_ms=5000,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建一个真实截图文件
            shot_path = os.path.join(tmpdir, "step0-click.jpg")
            with open(shot_path, "wb") as f:
                f.write(b"\x00" * 100)

            entries = [
                _make_entry(step="click", result="success", screenshot_path=shot_path),
                _make_entry(step="fill", result="success", screenshot_path=shot_path),
                _make_entry(step="assert", result="success", screenshot_path="/nonexistent.jpg"),
                _make_entry(step="screenshot", result="success", screenshot_path=shot_path),
            ]
            report = collector.compute(entries)
            # 4 个步骤期望截图，3 个有效 → 0.75
            self.assertAlmostEqual(report.business_metrics.visual_evidence_score, 0.75)


class TestMetricsReport(unittest.TestCase):
    """MetricsReport 序列化测试"""

    def test_to_dict(self):
        report = MetricsReport(
            task_id="t20",
            business_type="f88_material",
            core_metrics=CoreMetrics(
                task_success_rate=1.0,
                avg_task_duration_ms=5000,
                cost_per_task=800,
                false_positive_rate=0.0,
                change_frequency=3,
            ),
            business_metrics=BusinessMetrics(
                llm_confidence_avg=0.92,
                compliance_intercept_count=0,
                visual_evidence_score=1.0,
            ),
            raw_log_count=10,
        )
        d = report.to_dict()
        self.assertEqual(d["task_id"], "t20")
        self.assertEqual(d["business_type"], "f88_material")
        self.assertIn("core_metrics", d)
        self.assertIn("business_metrics", d)
        self.assertEqual(d["raw_log_count"], 10)
        # business_metrics 中 self_heal_success_rate 为 None → 被过滤
        self.assertNotIn("self_heal_success_rate", d["business_metrics"])

    def test_to_summary_dict(self):
        report = MetricsReport(
            task_id="t21",
            business_type="original_protection",
            core_metrics=CoreMetrics(
                task_success_rate=0.9,
                avg_task_duration_ms=8000,
                cost_per_task=1200,
                false_positive_rate=0.05,
            ),
            business_metrics=BusinessMetrics(
                llm_confidence_avg=0.85,
                self_heal_success_rate=0.6,
                compliance_intercept_count=1,
                visual_evidence_score=0.95,
            ),
            raw_log_count=20,
        )
        summary = report.to_summary_dict()
        self.assertEqual(summary["businessType"], "original_protection")
        self.assertEqual(summary["taskSuccessRate"], 0.9)
        self.assertEqual(summary["avgDurationMs"], 8000)
        self.assertEqual(summary["totalTokenUsed"], 1200)
        self.assertEqual(summary["llmConfidenceAvg"], 0.85)
        self.assertEqual(summary["selfHealSuccessRate"], 0.6)
        self.assertEqual(summary["visualEvidenceScore"], 0.95)

    def test_save_report(self):
        report = MetricsReport(
            task_id="t22",
            business_type="smoke",
            raw_log_count=5,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = MetricsCollector.save_report(report, tmpdir)
            self.assertTrue(os.path.isfile(path))
            with open(path) as f:
                data = json.load(f)
            self.assertEqual(data["task_id"], "t22")
            self.assertEqual(data["raw_log_count"], 5)


if __name__ == "__main__":
    unittest.main()
