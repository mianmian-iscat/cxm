"""test_dom_snapshot.py — DOM 快照对比与结构变化检测单元测试"""

import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.dom_snapshot import DOMSnapshot, DOMDiff, DOMSnapshotGuard


class _FakeCDP:
    def __init__(self, eval_return=None):
        self._eval_return = eval_return

    async def evaluate(self, js):
        return self._eval_return


def _run(coro):
    # 独立事件循环 + 结束后恢复全新循环，避免污染其他测试
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(asyncio.new_event_loop())


class TestDOMSnapshotSerialization(unittest.TestCase):

    def test_to_dict_from_dict_roundtrip(self):
        snap = DOMSnapshot(
            url="http://x",
            title="T",
            tag_counts={"div": 10},
            class_prefixes={"ant-btn": 3},
            key_selectors={".ant-menu": True},
            interactive_elements=5,
        )
        restored = DOMSnapshot.from_dict(snap.to_dict())
        self.assertEqual(restored.url, "http://x")
        self.assertEqual(restored.tag_counts["div"], 10)
        self.assertEqual(restored.interactive_elements, 5)

    def test_from_dict_defaults(self):
        snap = DOMSnapshot.from_dict({})
        self.assertEqual(snap.url, "")
        self.assertEqual(snap.tag_counts, {})


class TestCompare(unittest.TestCase):

    def setUp(self):
        self.guard = DOMSnapshotGuard()

    def test_no_baseline_returns_full_similarity(self):
        diff = self.guard.compare(DOMSnapshot())
        self.assertEqual(diff.similarity, 1.0)
        self.assertIn("无基线", diff.message)

    def test_identical_snapshots_high_similarity(self):
        snap = DOMSnapshot(
            tag_counts={"div": 10, "span": 5},
            class_prefixes={"ant-btn": 3},
            key_selectors={".ant-menu": True, "nav": True},
        )
        baseline = DOMSnapshot(
            tag_counts={"div": 10, "span": 5},
            class_prefixes={"ant-btn": 3},
            key_selectors={".ant-menu": True, "nav": True},
        )
        diff = self.guard.compare(snap, baseline)
        self.assertGreaterEqual(diff.similarity, 0.99)
        self.assertIn("稳定", diff.message)

    def test_missing_selectors_detected(self):
        baseline = DOMSnapshot(key_selectors={".ant-menu": True, ".ant-table": True})
        current = DOMSnapshot(key_selectors={".ant-menu": True, ".ant-table": False})
        diff = self.guard.compare(current, baseline)
        self.assertIn(".ant-table", diff.missing_selectors)

    def test_new_selectors_detected(self):
        baseline = DOMSnapshot(key_selectors={".ant-menu": False})
        current = DOMSnapshot(key_selectors={".ant-menu": True})
        diff = self.guard.compare(current, baseline)
        self.assertIn(".ant-menu", diff.new_selectors)

    def test_major_change_low_similarity(self):
        baseline = DOMSnapshot(
            tag_counts={"div": 100},
            class_prefixes={"ant-btn": 50},
            key_selectors={".ant-menu": True, ".ant-table": True, "nav": True},
        )
        current = DOMSnapshot(
            tag_counts={"section": 5},
            class_prefixes={"custom-x": 2},
            key_selectors={".ant-menu": False, ".ant-table": False, "nav": False},
        )
        diff = self.guard.compare(current, baseline)
        self.assertLess(diff.similarity, DOMSnapshotGuard.SIMILARITY_WARN_THRESHOLD)

    def test_uses_stored_baseline(self):
        baseline = DOMSnapshot(key_selectors={"nav": True})
        self.guard.set_baseline(baseline)
        self.assertIs(self.guard.get_baseline(), baseline)
        diff = self.guard.compare(DOMSnapshot(key_selectors={"nav": True}))
        self.assertNotIn("无基线", diff.message)

    def test_diff_to_dict_caps_selectors(self):
        baseline = DOMSnapshot(key_selectors={f"sel{i}": True for i in range(20)})
        current = DOMSnapshot(key_selectors={f"sel{i}": False for i in range(20)})
        diff = self.guard.compare(current, baseline)
        self.assertLessEqual(len(diff.to_dict()["missing_selectors"]), 10)


class TestCapture(unittest.TestCase):

    def test_capture_without_cdp_returns_empty(self):
        guard = DOMSnapshotGuard(cdp=None)
        snap = _run(guard.capture())
        self.assertIsInstance(snap, DOMSnapshot)
        self.assertEqual(snap.url, "")

    def test_capture_with_cdp_data(self):
        data = {
            "url": "http://x",
            "title": "Page",
            "tag_counts": {"div": 3},
            "class_prefixes": {"ant-btn": 1},
            "key_selectors": {"nav": True},
            "interactive_elements": 7,
        }
        guard = DOMSnapshotGuard(cdp=_FakeCDP(eval_return=data))
        snap = _run(guard.capture())
        self.assertEqual(snap.url, "http://x")
        self.assertEqual(snap.interactive_elements, 7)

    def test_capture_eval_returns_none(self):
        guard = DOMSnapshotGuard(cdp=_FakeCDP(eval_return=None))
        snap = _run(guard.capture())
        self.assertEqual(snap.url, "")


if __name__ == "__main__":
    unittest.main()
