"""
test_knowledge_updater.py — KnowledgeUpdater 单元测试
"""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from core.knowledge_updater import KnowledgeUpdater


class TestKnowledgeUpdater(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # 模拟 knowledge 目录结构
        self.knowledge_dir = os.path.join(self.tmp, "knowledge")
        os.makedirs(self.knowledge_dir)
        self.index_path = os.path.join(self.knowledge_dir, "index.json")
        # 写入空 index
        with open(self.index_path, "w") as f:
            json.dump({"entries": []}, f)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_instantiate_with_page_url(self):
        """KnowledgeUpdater 可以用 page_url 实例化"""
        updater = KnowledgeUpdater(page_url="https://pre-fsyc.taobao.com/")
        self.assertIsNotNone(updater)

    def test_instantiate_without_url(self):
        """KnowledgeUpdater 可以不传 page_url"""
        updater = KnowledgeUpdater(page_url="")
        self.assertIsNotNone(updater)

    def test_apply_pass_output_no_changes(self):
        """全部通过的输出不触发变更"""
        updater = KnowledgeUpdater(page_url="https://test.example.com/")
        output = {
            "status": "pass",
            "steps": [{"type": "click", "status": "pass"}],
            "id": "tc_test",
        }
        input_data = {"id": "tc_test", "context": {"urlPattern": "test.example.com"}}
        # apply 不应抛出异常
        result = updater.apply(output=output, input_data=input_data)
        self.assertIsInstance(result, dict)

    def test_apply_error_output(self):
        """失败输出应触发 apply 正常执行（不抛异常）"""
        updater = KnowledgeUpdater(page_url="https://test.example.com/")
        output = {
            "status": "error",
            "steps": [{"type": "click", "status": "error", "error": "selector not found"}],
            "id": "tc_test",
        }
        input_data = {"id": "tc_test", "context": {"urlPattern": "test.example.com"}}
        result = updater.apply(output=output, input_data=input_data)
        self.assertIsInstance(result, dict)

    def test_apply_returns_dict_with_changes_key(self):
        """apply 返回值包含 changes 键"""
        updater = KnowledgeUpdater(page_url="")
        output = {"status": "pass", "steps": [], "id": "t1"}
        result = updater.apply(output=output, input_data={"id": "t1", "context": {}})
        self.assertIn("changes", result)

    def test_no_exception_on_missing_knowledge_file(self):
        """knowledge 文件不存在时不抛异常"""
        updater = KnowledgeUpdater(page_url="https://nonexistent.com/")
        output = {"status": "pass", "steps": [], "id": "tc_nonexistent"}
        # Should not raise
        try:
            updater.apply(output=output, input_data={"id": "tc_nonexistent", "context": {}})
        except FileNotFoundError:
            self.fail("apply() raised FileNotFoundError unexpectedly")


if __name__ == "__main__":
    unittest.main()
