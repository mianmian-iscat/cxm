"""test_failure_clustering.py — 失败模式聚类与根因分析单元测试"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.failure_clustering import FailureClusterer, ClusterReport


def _fail(error, index=0, step_type="click", selector=""):
    return {"error": error, "index": index, "type": step_type, "selector": selector}


class TestErrorClassification(unittest.TestCase):

    def test_selector_issue(self):
        self.assertEqual(
            FailureClusterer._classify_error_type("element not found"), "selector_issue"
        )
        self.assertEqual(
            FailureClusterer._classify_error_type("选择器未找到"), "selector_issue"
        )

    def test_timeout_issue(self):
        self.assertEqual(
            FailureClusterer._classify_error_type("TimeoutError: 超时"), "timeout_issue"
        )

    def test_auth_issue(self):
        self.assertEqual(
            FailureClusterer._classify_error_type("401 unauthorized"), "auth_issue"
        )
        self.assertEqual(
            FailureClusterer._classify_error_type("需要重新登录"), "auth_issue"
        )

    def test_network_issue(self):
        self.assertEqual(
            FailureClusterer._classify_error_type("connection refused"), "network_issue"
        )

    def test_network_issue_uppercase_econnrefused(self):
        # 源码对消息做 lower()，关键词已统一为小写 "econnrefused"，可正常命中
        self.assertEqual(
            FailureClusterer._classify_error_type("ECONNREFUSED"), "network_issue"
        )

    def test_assertion_issue(self):
        self.assertEqual(
            FailureClusterer._classify_error_type("断言失败"), "assertion_issue"
        )

    def test_unknown(self):
        self.assertEqual(FailureClusterer._classify_error_type("weird"), "unknown")

    def test_empty_error_unknown(self):
        self.assertEqual(FailureClusterer._classify_error_type(""), "unknown")


class TestCommonPrefix(unittest.TestCase):

    def test_shared_prefix(self):
        self.assertEqual(FailureClusterer._common_prefix("hello world", "hello there"), "hello ")

    def test_no_shared_prefix(self):
        self.assertEqual(FailureClusterer._common_prefix("abc", "xyz"), "")

    def test_identical(self):
        self.assertEqual(FailureClusterer._common_prefix("same", "same"), "same")

    def test_empty(self):
        self.assertEqual(FailureClusterer._common_prefix("", "abc"), "")


class TestRecordAndAnalyze(unittest.TestCase):

    def setUp(self):
        self.clusterer = FailureClusterer()

    def test_empty_analyze(self):
        report = self.clusterer.analyze()
        self.assertIsInstance(report, ClusterReport)
        self.assertEqual(report.total_failures, 0)
        self.assertFalse(report.systemic_issue)

    def test_single_failure_no_systemic(self):
        self.clusterer.record_failure(_fail("not found", selector="#a"))
        report = self.clusterer.analyze()
        self.assertEqual(report.total_failures, 1)
        self.assertFalse(report.systemic_issue)

    def test_systemic_selector_issue(self):
        for i in range(3):
            self.clusterer.record_failure(
                _fail("element not found", index=i, selector="#btn")
            )
        report = self.clusterer.analyze()
        self.assertTrue(report.systemic_issue)
        self.assertIn("选择器", report.suggestion)

    def test_systemic_network_issue_suggestion(self):
        for i in range(3):
            self.clusterer.record_failure(
                _fail("ECONNREFUSED network", index=i, step_type="navigate")
            )
        report = self.clusterer.analyze()
        self.assertTrue(report.systemic_issue)
        self.assertIn("网络", report.suggestion)

    def test_systemic_auth_issue_suggestion(self):
        for i in range(3):
            self.clusterer.record_failure(
                _fail("401 unauthorized", index=i, step_type="navigate")
            )
        report = self.clusterer.analyze()
        self.assertTrue(report.systemic_issue)
        self.assertIn("登录", report.suggestion)

    def test_dominant_cluster_set(self):
        for i in range(4):
            self.clusterer.record_failure(_fail("timeout", index=i, step_type="wait"))
        report = self.clusterer.analyze()
        self.assertIsNotNone(report.dominant_cluster)

    def test_scattered_failures_suggestion(self):
        self.clusterer.record_failure(_fail("not found", index=0, selector="#a"))
        self.clusterer.record_failure(_fail("timeout", index=1, step_type="wait"))
        self.clusterer.record_failure(_fail("401", index=2, step_type="navigate"))
        report = self.clusterer.analyze()
        self.assertFalse(report.systemic_issue)
        self.assertIn("分散性失败", report.suggestion)

    def test_max_clusters_cap(self):
        for i in range(FailureClusterer.MAX_CLUSTERS + 5):
            self.clusterer.record_failure(
                _fail(f"weird error {i}", index=i, step_type=f"type{i}")
            )
        stats = self.clusterer.get_stats()
        self.assertLessEqual(stats["cluster_count"], FailureClusterer.MAX_CLUSTERS)


class TestSmartCircuitBreak(unittest.TestCase):

    def setUp(self):
        self.clusterer = FailureClusterer()

    def test_should_skip_after_threshold(self):
        for i in range(3):
            self.clusterer.record_failure(
                _fail("element not found", index=i, step_type="click", selector="#btn")
            )
        self.assertTrue(self.clusterer.should_skip_step_type("click", "#btn"))

    def test_should_not_skip_below_threshold(self):
        self.clusterer.record_failure(
            _fail("element not found", index=0, step_type="click", selector="#btn")
        )
        self.assertFalse(self.clusterer.should_skip_step_type("click", "#btn"))

    def test_get_skippable_step_types(self):
        for i in range(3):
            self.clusterer.record_failure(
                _fail("timeout", index=i, step_type="wait")
            )
        self.assertIn("wait", self.clusterer.get_skippable_step_types())


class TestReportSerialization(unittest.TestCase):

    def test_report_to_dict_keys(self):
        clusterer = FailureClusterer()
        clusterer.record_failure(_fail("not found", selector="#a"))
        d = clusterer.analyze().to_dict()
        for key in ("total_failures", "cluster_count", "systemic_issue", "clusters"):
            self.assertIn(key, d)

    def test_cluster_to_dict_caps_lists(self):
        clusterer = FailureClusterer()
        for i in range(8):
            clusterer.record_failure(
                _fail("element not found", index=i, selector=f"#sel{i}")
            )
        cluster = clusterer.analyze().clusters[0]
        d = cluster.to_dict()
        self.assertLessEqual(len(d["selectors"]), 5)


if __name__ == "__main__":
    unittest.main()
