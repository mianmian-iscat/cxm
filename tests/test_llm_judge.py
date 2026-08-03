"""test_llm_judge.py — LLM 双因子裁决引擎单元测试"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.llm_judge import (
    MockLLMProvider,
    OpenAICompatibleProvider,
    create_llm_judge,
    load_llm_config_from_yaml,
    _simple_yaml_parse,
    _FAILURE_CATEGORIES,
)


class TestMockProvider(unittest.TestCase):

    def setUp(self):
        self.provider = MockLLMProvider()

    def test_script_issue(self):
        self.assertEqual(
            self.provider.classify({"message": "element not interactable"}), "script_issue"
        )
        self.assertEqual(
            self.provider.classify({"message": "no such element"}), "script_issue"
        )

    def test_env_failure(self):
        self.assertEqual(
            self.provider.classify({"message": "navigation timeout"}), "env_failure"
        )
        self.assertEqual(
            self.provider.classify({"message": "session expired"}), "env_failure"
        )

    def test_data_invalid(self):
        self.assertEqual(
            self.provider.classify({"message": "必填字段校验失败"}), "data_invalid"
        )
        self.assertEqual(
            self.provider.classify({"message": "required field missing"}), "data_invalid"
        )

    def test_unknown(self):
        self.assertEqual(self.provider.classify({"message": "weird stuff"}), "unknown")

    def test_empty_message(self):
        self.assertEqual(self.provider.classify({}), "unknown")

    def test_priority_script_before_env(self):
        # "element" 命中 script，即使也含 timeout
        self.assertEqual(
            self.provider.classify({"message": "element timeout"}), "script_issue"
        )


class TestParseResponse(unittest.TestCase):

    def test_direct_category_match(self):
        self.assertEqual(
            OpenAICompatibleProvider._parse_response("script_issue"), "script_issue"
        )

    def test_case_insensitive(self):
        self.assertEqual(
            OpenAICompatibleProvider._parse_response("ENV_FAILURE"), "env_failure"
        )

    def test_alias_match(self):
        self.assertEqual(OpenAICompatibleProvider._parse_response("selector"), "script_issue")
        self.assertEqual(OpenAICompatibleProvider._parse_response("network error"), "env_failure")
        self.assertEqual(OpenAICompatibleProvider._parse_response("this is a real bug"), "true_bug")

    def test_no_match_unknown(self):
        self.assertEqual(OpenAICompatibleProvider._parse_response("gibberish"), "unknown")

    def test_all_categories_parse(self):
        for cat in _FAILURE_CATEGORIES:
            self.assertEqual(OpenAICompatibleProvider._parse_response(cat), cat)


class TestOpenAIProviderPrompt(unittest.TestCase):

    def test_build_prompt_truncates(self):
        provider = OpenAICompatibleProvider(api_key="k")
        prompt = provider._build_prompt({
            "message": "x" * 1000,
            "step_type": "click",
            "selector": "#a",
            "page_url": "http://x",
        })
        self.assertIn("click", prompt)
        self.assertIn("#a", prompt)

    def test_stats_initialized(self):
        provider = OpenAICompatibleProvider(api_key="k")
        self.assertEqual(provider.get_stats()["calls"], 0)


class TestCreateLlmJudge(unittest.TestCase):

    def setUp(self):
        # 清理可能干扰的环境变量
        self._saved = {k: os.environ.get(k) for k in
                       ("LLM_JUDGE_API_KEY", "LLM_JUDGE_BASE_URL", "LLM_JUDGE_MODEL")}
        for k in self._saved:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_none_config_returns_mock(self):
        judge = create_llm_judge(None)
        self.assertIsNotNone(judge)
        self.assertEqual(judge._provider_name, "mock")
        self.assertIsInstance(judge._provider, MockLLMProvider)

    def test_disabled_returns_none(self):
        self.assertIsNone(create_llm_judge({"enabled": False}))

    def test_openai_without_key_downgrades_to_mock(self):
        judge = create_llm_judge({"provider": "openai"})
        self.assertIsInstance(judge._provider, MockLLMProvider)

    def test_openai_with_key_uses_openai_provider(self):
        judge = create_llm_judge({"provider": "openai", "api_key": "sk-test"})
        self.assertIsInstance(judge._provider, OpenAICompatibleProvider)

    def test_unknown_provider_downgrades_to_mock(self):
        judge = create_llm_judge({"provider": "nonsense"})
        self.assertIsInstance(judge._provider, MockLLMProvider)

    def test_judge_fn_callable(self):
        judge = create_llm_judge({"provider": "mock"})
        self.assertEqual(judge({"message": "element not found"}), "script_issue")

    def test_env_var_key_used(self):
        os.environ["LLM_JUDGE_API_KEY"] = "sk-env"
        judge = create_llm_judge({"provider": "openai"})
        self.assertIsInstance(judge._provider, OpenAICompatibleProvider)


class TestSimpleYamlParse(unittest.TestCase):

    def _write(self, content):
        fd, path = tempfile.mkstemp(suffix=".yaml")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        self.addCleanup(os.remove, path)
        return path

    def test_parses_key_value(self):
        path = self._write("provider: openai\ntimeout: 15\nenabled: true\n")
        result = _simple_yaml_parse(path)
        self.assertEqual(result["provider"], "openai")
        self.assertEqual(result["timeout"], 15)
        self.assertIs(result["enabled"], True)

    def test_skips_comments(self):
        path = self._write("# comment\nmodel: qwen-plus\n")
        result = _simple_yaml_parse(path)
        self.assertEqual(result["model"], "qwen-plus")

    def test_false_parsed(self):
        path = self._write("enabled: false\n")
        self.assertIs(_simple_yaml_parse(path)["enabled"], False)


class TestLoadConfigFromYaml(unittest.TestCase):

    def setUp(self):
        self.base_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.base_dir, True)
        os.makedirs(os.path.join(self.base_dir, "harness"), exist_ok=True)

    def _write_rules(self, content):
        with open(os.path.join(self.base_dir, "harness", "self_healing_rules.yaml"),
                  "w", encoding="utf-8") as f:
            f.write(content)

    def test_missing_file_returns_none(self):
        self.assertIsNone(load_llm_config_from_yaml(self.base_dir))

    def test_llm_layer_disabled_returns_none(self):
        self._write_rules(
            "dual_factor:\n  llm_layer:\n    enabled: false\n"
        )
        self.assertIsNone(load_llm_config_from_yaml(self.base_dir))

    def test_llm_layer_enabled_returns_config(self):
        self._write_rules(
            "dual_factor:\n"
            "  llm_layer:\n"
            "    enabled: true\n"
            "    confidence_threshold: 0.6\n"
            "llm_provider:\n"
            "  provider: mock\n"
            "  timeout: 8\n"
        )
        config = load_llm_config_from_yaml(self.base_dir)
        self.assertIsNotNone(config)
        self.assertTrue(config["enabled"])
        self.assertEqual(config["provider"], "mock")


if __name__ == "__main__":
    unittest.main()
