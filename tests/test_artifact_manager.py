"""
test_artifact_manager.py — ArtifactManager 单元测试
"""
import json
import os
import tempfile
import unittest

from core.artifact_manager import ArtifactManager, resolve_scene_dir, SCENE_DIRECTORY_MAP, DEFAULT_SCENE_DIR, DEFAULT_DOMAIN


class TestArtifactManager(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["WEB_AUTO_ARTIFACTS_DIR"] = self.tmp
        self.am = ArtifactManager("test-run-001", base_dir=self.tmp)

    def tearDown(self):
        os.environ.pop("WEB_AUTO_ARTIFACTS_DIR", None)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_run_dir_created(self):
        """初始化后 run_dir 应存在"""
        self.assertTrue(os.path.isdir(self.am.run_dir))

    def test_save_and_read_input(self):
        """save_input 应写入 input.json"""
        self.am.save_input({"id": "tc1", "steps": []})
        path = os.path.join(self.am.run_dir, "input.json")
        self.assertTrue(os.path.exists(path))
        data = json.loads(open(path).read())
        self.assertEqual(data["id"], "tc1")

    def test_save_screenshot(self):
        """save_screenshot 应写入 screenshots/ 目录"""
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        path = self.am.save_screenshot(fake_png, "step0-click")
        self.assertTrue(os.path.exists(path))
        self.assertIn("step0-click", path)

    def test_save_capture(self):
        """save_capture 应写入 capture.json"""
        requests = [{"url": "https://example.com", "status": 200}]
        path = self.am.save_capture(requests)
        self.assertTrue(os.path.exists(path))
        saved = json.loads(open(path).read())
        self.assertEqual(saved[0]["status"], 200)

    def test_save_output(self):
        """save_output 应写入 output.json"""
        self.am.save_output({"status": "pass", "steps": []})
        path = os.path.join(self.am.run_dir, "output.json")
        self.assertTrue(os.path.exists(path))

    def test_finalize_returns_manifest(self):
        """finalize 应返回包含 run_id 和 created_at 的清单"""
        self.am.save_input({"id": "tc1"})
        manifest = self.am.finalize()
        self.assertIn("run_id", manifest)
        self.assertEqual(manifest["run_id"], "test-run-001")

    def test_path_helper(self):
        """path() 应返回 run_dir 下的正确路径"""
        p = self.am.path("custom.json")
        self.assertTrue(p.endswith("custom.json"))
        self.assertIn(self.am.run_dir, p)

    def test_save_har(self):
        """save_har 应生成 .har 文件"""
        requests = [{"url": "https://a.com", "status": 200, "method": "GET",
                     "duration": 100, "requestBody": None, "responseBody": {}}]
        path = self.am.save_har(requests)
        self.assertTrue(path.endswith(".har"))
        har = json.loads(open(path).read())
        self.assertIn("log", har)

    def test_save_knowledge_update(self):
        """save_knowledge_update 应写入 knowledge_update.json"""
        summary = {"changes": 2, "knowledgePath": "x.json"}
        path = self.am.save_knowledge_update(summary)
        self.assertTrue(os.path.exists(path))

    def test_get_manifest_before_finalize(self):
        """finalize 前 get_manifest 返回空或初始状态"""
        manifest = self.am.get_manifest()
        self.assertIsInstance(manifest, dict)


class TestSceneIsolation(unittest.TestCase):
    """产物目录场景隔离测试"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_resolve_known_scene(self):
        """已注册场景应解析为对应 (domain, scene_dir) 元组"""
        self.assertEqual(resolve_scene_dir("f88"), ("f88", "audit"))
        self.assertEqual(resolve_scene_dir("op-test"), ("op", "general"))
        self.assertEqual(resolve_scene_dir("smoke"), ("common", "_smoke"))

    def test_resolve_unknown_scene(self):
        """未注册场景应使用推断或回退"""
        self.assertEqual(resolve_scene_dir("new-biz"), ("common", "new-biz"))

    def test_resolve_none_scene(self):
        """未指定 scene 回退 (DEFAULT_DOMAIN, DEFAULT_SCENE_DIR)"""
        self.assertEqual(resolve_scene_dir(None), (DEFAULT_DOMAIN, DEFAULT_SCENE_DIR))
        self.assertEqual(resolve_scene_dir(""), (DEFAULT_DOMAIN, DEFAULT_SCENE_DIR))

    def test_scene_creates_correct_dir(self):
        """传入 scene 参数后产物目录应包含 domain/scene_dir"""
        am = ArtifactManager("run-001", base_dir=self.tmp, scene="f88")
        self.assertIn("f88", am.run_dir)  # domain
        self.assertIn("audit", am.run_dir)  # scene_dir
        self.assertTrue(os.path.isdir(am.run_dir))

    def test_no_scene_uses_default(self):
        """不传 scene 时使用 _default 目录"""
        am = ArtifactManager("run-002", base_dir=self.tmp)
        self.assertIn("_default", am.run_dir)

    def test_manifest_includes_scene(self):
        """清单中应包含 scene 字段"""
        am = ArtifactManager("run-003", base_dir=self.tmp, scene="op-test")
        am.save_input({"id": "tc1"})
        manifest = am.finalize()
        self.assertEqual(manifest["scene"], "general")
        self.assertEqual(manifest["domain"], "op")


if __name__ == "__main__":
    unittest.main()
