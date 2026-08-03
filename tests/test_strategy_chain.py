"""test_strategy_chain.py — 策略组合学习与推荐引擎单元测试"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.strategy_chain import StrategyChainLearner, ChainStats, StrategyStep


class TestChainStats(unittest.TestCase):

    def test_success_rate_empty(self):
        self.assertEqual(ChainStats(chain=["a"]).success_rate, 0.0)

    def test_success_rate(self):
        s = ChainStats(chain=["a"], success_count=3, fail_count=1)
        self.assertEqual(s.success_rate, 0.75)

    def test_avg_duration(self):
        s = ChainStats(chain=["a"], success_count=1, fail_count=1, total_duration_ms=1000)
        self.assertEqual(s.avg_duration_ms, 500.0)

    def test_to_dict_keys(self):
        d = ChainStats(chain=["a", "b"]).to_dict()
        for key in ("chain", "success_count", "success_rate", "avg_duration_ms"):
            self.assertIn(key, d)


class TestRecordChain(unittest.TestCase):

    def setUp(self):
        self.learner = StrategyChainLearner()

    def test_full_chain_recorded(self):
        self.learner.start_chain("element_timeout", "xxx")
        self.learner.add_strategy("cdp_relocate", success=False, duration_ms=500)
        self.learner.add_strategy("smart_wait", success=True, duration_ms=1200)
        result = self.learner.finish_chain(success=True)
        self.assertEqual(result["chain"], ["cdp_relocate", "smart_wait"])
        self.assertTrue(result["success"])
        self.assertEqual(result["total_duration_ms"], 1700)

    def test_add_without_start_ignored(self):
        # 未 start_chain 时 add 无效
        self.learner.add_strategy("x", success=True)
        result = self.learner.finish_chain(success=True)
        self.assertEqual(result["chain"], [])

    def test_empty_chain_finish(self):
        self.learner.start_chain("t")
        result = self.learner.finish_chain(success=True)
        self.assertEqual(result["chain"], [])

    def test_repeated_chain_accumulates(self):
        for _ in range(3):
            self.learner.start_chain("timeout")
            self.learner.add_strategy("wait", success=True, duration_ms=100)
            self.learner.finish_chain(success=True)
        chains = self.learner.get_all_chains()
        self.assertEqual(len(chains), 1)
        self.assertEqual(chains[0]["success_count"], 3)

    def test_failure_recorded(self):
        self.learner.start_chain("timeout")
        self.learner.add_strategy("wait", success=False, duration_ms=100)
        self.learner.finish_chain(success=False)
        stats = self.learner.get_stats()
        self.assertEqual(stats["total_fail"], 1)

    def test_error_type_tracked_on_success(self):
        self.learner.start_chain("element_timeout")
        self.learner.add_strategy("relocate", success=True, duration_ms=100)
        self.learner.finish_chain(success=True)
        chains = self.learner.get_all_chains()
        self.assertIn("element_timeout", chains[0]["error_types"])


class TestRecommend(unittest.TestCase):

    def setUp(self):
        self.learner = StrategyChainLearner()

    def test_no_history_returns_empty(self):
        self.assertEqual(self.learner.recommend_chain("timeout"), [])

    def test_recommends_successful_chain(self):
        self.learner.start_chain("element_timeout")
        self.learner.add_strategy("cdp_relocate", success=True, duration_ms=100)
        self.learner.add_strategy("smart_wait", success=True, duration_ms=100)
        self.learner.finish_chain(success=True)
        rec = self.learner.recommend_chain("element_timeout")
        self.assertEqual(rec, ["cdp_relocate", "smart_wait"])

    def test_low_success_rate_not_recommended(self):
        # 1 成功 3 失败 → 25% < RECOMMEND_THRESHOLD(0.5)
        self.learner.start_chain("timeout")
        self.learner.add_strategy("bad", success=True, duration_ms=100)
        self.learner.finish_chain(success=True)
        for _ in range(3):
            self.learner.start_chain("timeout")
            self.learner.add_strategy("bad", success=False, duration_ms=100)
            self.learner.finish_chain(success=False)
        self.assertEqual(self.learner.recommend_chain("timeout"), [])

    def test_get_top_chains(self):
        self.learner.start_chain("timeout")
        self.learner.add_strategy("wait", success=True, duration_ms=100)
        self.learner.finish_chain(success=True)
        top = self.learner.get_top_chains(top_k=3)
        self.assertTrue(len(top) >= 1)
        self.assertIsInstance(top[0], ChainStats)


class TestChainKey(unittest.TestCase):

    def test_chain_key_format(self):
        self.assertEqual(StrategyChainLearner._chain_key(["a", "b"]), "a → b")

    def test_error_match_score_type_match(self):
        stats = ChainStats(chain=["relocate"], error_types=["timeout"])
        score = StrategyChainLearner._error_match_score(stats, "timeout", "")
        self.assertGreaterEqual(score, 0.6)

    def test_error_match_base_score_when_no_type(self):
        stats = ChainStats(chain=["relocate"])
        score = StrategyChainLearner._error_match_score(stats, "", "")
        self.assertEqual(score, 0.1)


class TestPersistence(unittest.TestCase):

    def setUp(self):
        self.base_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.base_dir, True)

    def test_save_and_reload(self):
        learner = StrategyChainLearner(base_dir=self.base_dir)
        learner.start_chain("timeout")
        learner.add_strategy("wait", success=True, duration_ms=100)
        learner.finish_chain(success=True)
        learner.save()

        path = os.path.join(self.base_dir, StrategyChainLearner.CHAINS_FILE)
        self.assertTrue(os.path.exists(path))

        reloaded = StrategyChainLearner(base_dir=self.base_dir)
        stats = reloaded.get_stats()
        self.assertEqual(stats["total_chains"], 1)
        self.assertEqual(stats["total_success"], 1)

    def test_save_without_base_dir_noop(self):
        learner = StrategyChainLearner()
        learner.save()  # 无 base_dir，不应抛异常

    def test_load_missing_file_no_error(self):
        # base_dir 存在但无文件
        learner = StrategyChainLearner(base_dir=self.base_dir)
        self.assertEqual(learner.get_stats()["total_chains"], 0)


if __name__ == "__main__":
    unittest.main()
