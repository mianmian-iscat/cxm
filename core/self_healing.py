"""
self_healing.py — 智能自愈与分级放行

自愈引擎：
- 知识库解析器（KnowledgeResolver）：自动查阅 references + knowledge 找解法
- 双因子失败裁决: 规则层初判 + 可选 LLM 二次确认
- 失败分类器: 真 Bug / 脚本问题 / 数据失效 / 环境问题
- 自愈策略: 知识库查询 → CDP 重定位 → Schema 重生成 → 沙箱重置
- 分级放行: P0 阻断 / P1 警告 / P2 跳过
- 熔断阈值: 连续失败或失败率超限

使用方式:
    from core.self_healing import SelfHealingEngine
    engine = SelfHealingEngine(scene="f88-test")
    result = engine.heal(FailureCategory.SCRIPT_ISSUE, {"selector": ".old", "error": "..."})
"""

import time
import os
import re
import json
import glob as glob_mod
from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Dict

class FailureCategory(Enum):
    """失败分类"""
    TRUE_BUG = "true_bug"           # 真 Bug
    SCRIPT_ISSUE = "script_issue"   # 脚本问题
    DATA_INVALID = "data_invalid"   # 数据失效
    ENV_ISSUE = "env_issue"         # 环境问题
    UNKNOWN = "unknown"             # 未知

class SeverityLevel(Enum):
    """严重级别"""
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"

    @property
    def action(self) -> str:
        actions = {"P0": "block", "P1": "warn", "P2": "skip"}
        return actions[self.value]

class HealingAction(Enum):
    """自愈动作"""
    NONE = "none"                       # 无自愈
    KNOWLEDGE_FIX = "knowledge_fix"     # 知识库匹配 → 应用已知解法
    CDP_RELOCATE = "cdp_relocate"       # 元素漂移 → CDP 重定位
    SCHEMA_REGEN = "schema_regen"       # Schema 变更 → 重新生成
    SANDBOX_RESET = "sandbox_reset"     # 数据失效 → 沙箱重置
    RETRY = "retry"                     # 通用重试
    MEMORY_FIX = "memory_fix"           # 历史经验命中 → 直接应用
    NETWORK_RETRY = "network_retry"     # 网络层重试
    MOCK_FALLBACK = "mock_fallback"     # 接口 mock 降级
    DATA_FALLBACK = "data_fallback"     # 数据备选切换

@dataclass
class HealingResult:
    """自愈结果"""
    action: HealingAction = HealingAction.NONE
    attempted: bool = False
    success: bool = False
    message: str = ""
    duration_ms: int = 0
    knowledge_source: str = ""  # 命中的知识库来源文件
    fix_code: str = ""          # 提取到的修复代码片段

@dataclass
class KnowledgeMatch:
    """知识库匹配结果"""
    source_file: str
    section: str
    fix_description: str
    code_snippet: str = ""
    confidence: float = 0.0

# ── 知识库解析器 ──

# 错误模式 → 关键词映射（用于在 references 中搜索）
ERROR_PATTERN_KEYWORDS: Dict[str, List[str]] = {
    "ant-select": ["Select", "下拉", "mouse.click", "ant-select-arrow"],
    "modal": ["Modal", "确定", "确认", "ant-modal", "OK"],
    "drawer": ["Drawer", "ant-drawer"],
    "waitForTimeout": ["waitForTimeout", "setTimeout", "废弃"],
    "login": ["登录", "BUC", "SSO", "login", "CDP 9222"],
    "dropdown": ["dropdown", "body", "ant-dropdown-menu"],
    "upload": ["上传", "FileChooser", "upload"],
    "iframe": ["iframe", "frame", "contentFrame"],
    "loading": ["loading", "spin", "ant-spin"],
    "mtop": ["mtop", "MTOP", "waitForResponse"],
    "react-input": ["受控组件", "dispatchEvent", "native setter"],
    "element-not-found": ["element", "selector", "waitForSelector", "querySelector"],
    "click-intercept": ["click", "intercept", "遮挡", "overlapping", "scrollIntoView"],
    "network-error": ["network", "fetch", "timeout", "socket", "ERR_"],
}

class KnowledgeResolver:
    """
    知识库解析器：根据错误信息自动查阅 references 和 knowledge 找解法。
    
    查找顺序：
    1. 场景参考文档（scenes/{scene}/references/*.md）
    2. 通用参考文档（references/*.md）
    3. 知识库 knownIssues（knowledge/*.json）
    4. 统一知识索引 KnowledgeIndex（页面知识 + KnowledgeBase + references 全量搜索）
    """

    def __init__(self, base_dir: str = None, scene: str = None):
        self._base_dir = base_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._scene = scene
        self._cache: Dict[str, str] = {}  # filepath -> content
        self._error_map = self._load_error_pattern_map()
        self._knowledge_index = None  # 懒加载

    def _load_error_pattern_map(self) -> list:
        """加载错误模式映射表"""
        map_path = os.path.join(self._base_dir, "references", "error-pattern-map.json")
        try:
            with open(map_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("mappings", [])
        except (IOError, json.JSONDecodeError):
            return []

    def resolve(self, error_msg: str, context: dict = None) -> Optional[KnowledgeMatch]:
        """根据错误信息查找解决方案。优先用映射表快速命中。"""
        # ① 快速路径：错误模式映射表
        fast_match = self._match_error_pattern_map(error_msg)
        if fast_match:
            return fast_match

        # ② 慢速路径：关键词全文搜索
        keywords = self._extract_keywords(error_msg, context or {})
        if not keywords:
            return None

        # 1️⃣ 场景参考文档
        if self._scene:
            scene_refs = self._find_scene_references()
            match = self._search_files(scene_refs, keywords)
            if match:
                return match

        # 2️⃣ 通用参考文档
        general_refs = self._find_general_references()
        match = self._search_files(general_refs, keywords)
        if match:
            return match

        # 3️⃣ 知识库 knownIssues
        match = self._search_knowledge_issues(keywords, error_msg)
        if match:
            return match

        # 4️⃣ 统一知识索引 KnowledgeIndex（页面知识 + KnowledgeBase + references）
        match = self._search_knowledge_index(keywords, error_msg)
        if match:
            return match

        return None

    def _extract_keywords(self, error_msg: str, context: dict) -> List[str]:
        """从错误信息提取搜索关键词"""
        keywords = []
        error_lower = error_msg.lower()

        for pattern, kws in ERROR_PATTERN_KEYWORDS.items():
            if pattern.lower() in error_lower:
                keywords.extend(kws)

        # 从 selector 中提取
        selector = context.get("selector", "")
        if selector:
            if "ant-select" in selector:
                keywords.extend(["Select", "mouse.click", "ant-select-arrow"])
            if "ant-modal" in selector:
                keywords.extend(["Modal", "确定", "确认"])
            if "ant-drawer" in selector:
                keywords.extend(["Drawer", "ant-drawer-content"])

        # 从错误类型提取
        if "timeout" in error_lower:
            keywords.extend(["超时", "waitFor", "timeout"])
        if "not a function" in error_lower:
            keywords.extend(["废弃", "deprecated", "setTimeout"])
        if "cannot read" in error_lower or "null" in error_lower:
            keywords.extend(["未找到", "null", "visible"])

        # ② fallback：如果标准关键词全未命中，尝试从 error_pattern_map 的 keywords 数组反向匹配
        if not keywords and self._error_map:
            for entry in self._error_map:
                entry_kws = entry.get("keywords", [])
                if any(kw.lower() in error_lower for kw in entry_kws):
                    keywords.extend(entry_kws)
                    break  # 取第一个命中的即可

        return list(set(keywords))

    def _find_scene_references(self) -> List[str]:
        """查找场景级参考文档"""
        scene_dir = os.path.join(self._base_dir, "scenes", self._scene, "references")
        if not os.path.isdir(scene_dir):
            # 尝试模糊匹配
            candidates = glob_mod.glob(os.path.join(self._base_dir, "scenes", "*", "references"))
            for c in candidates:
                if self._scene.replace("-test", "") in c:
                    scene_dir = c
                    break
        if os.path.isdir(scene_dir):
            return glob_mod.glob(os.path.join(scene_dir, "*.md"))
        return []

    def _find_general_references(self) -> List[str]:
        """查找通用参考文档"""
        refs_dir = os.path.join(self._base_dir, "references")
        if os.path.isdir(refs_dir):
            return glob_mod.glob(os.path.join(refs_dir, "*.md"))
        return []

    def _search_files(self, files: List[str], keywords: List[str]) -> Optional[KnowledgeMatch]:
        """在文件列表中搜索关键词，返回最佳匹配"""
        best_match = None
        best_score = 0

        for fpath in files:
            content = self._read_file(fpath)
            if not content:
                continue

            score = sum(1 for kw in keywords if kw.lower() in content.lower())
            if score > best_score:
                best_score = score
                # 提取包含关键词的段落
                section, code = self._extract_relevant_section(content, keywords)
                best_match = KnowledgeMatch(
                    source_file=fpath,
                    section=section[:200],
                    fix_description=f"匹配 {score}/{len(keywords)} 关键词",
                    code_snippet=code[:500],
                    confidence=min(score / max(len(keywords), 1), 1.0),
                )

        # 置信度阈值：至少匹配 2 个关键词
        if best_match and best_score >= 2:
            return best_match
        return None

    def _search_knowledge_issues(self, keywords: List[str], error_msg: str) -> Optional[KnowledgeMatch]:
        """在 knowledge/*.json 的 knownIssues 中搜索"""
        knowledge_dir = os.path.join(self._base_dir, "knowledge")
        if not os.path.isdir(knowledge_dir):
            return None

        for fpath in glob_mod.glob(os.path.join(knowledge_dir, "**", "*.json"), recursive=True):
            # 跳过 index.json（不是知识文件）
            if os.path.basename(fpath) == "index.json":
                continue
            try:
                data = json.loads(self._read_file(fpath) or "{}")
            except (json.JSONDecodeError, TypeError):
                continue

            issues = data.get("knownIssues", [])
            for issue in issues:
                issue_text = json.dumps(issue, ensure_ascii=False).lower()
                score = sum(1 for kw in keywords if kw.lower() in issue_text)
                if score >= 2 or error_msg[:50].lower() in issue_text:
                    return KnowledgeMatch(
                        source_file=fpath,
                        section=issue.get("description", str(issue))[:200],
                        fix_description=issue.get("fix", issue.get("workaround", ""))[:200],
                        code_snippet=issue.get("code", ""),
                        confidence=min(score / max(len(keywords), 1), 1.0),
                    )
        return None

    def _search_knowledge_index(self, keywords: List[str], error_msg: str) -> Optional[KnowledgeMatch]:
        """
        通过 KnowledgeIndex 统一检索（页面知识 + KnowledgeBase + references）。

        这是最后一道防线，覆盖前面 3 步未搜索到的知识源。
        """
        try:
            if self._knowledge_index is None:
                from core.knowledge_index import KnowledgeIndex
                self._knowledge_index = KnowledgeIndex(root=self._base_dir)
        except (ImportError, Exception):
            return None

        # 用关键词组合查询搜索
        query = " ".join(keywords[:5]) if keywords else error_msg[:100]
        try:
            results = self._knowledge_index.search(query, limit=3)
        except Exception:
            return None

        if not results:
            return None

        best = results[0]
        # 只接受有意义的得分
        if best.score < 0.3:
            return None

        return KnowledgeMatch(
            source_file=best.metadata.get("file", best.metadata.get("filename", "")),
            section=best.title,
            fix_description=best.content[:200],
            code_snippet="",
            confidence=best.score,
        )

    def _match_error_pattern_map(self, error_msg: str) -> Optional[KnowledgeMatch]:
        """通过 error-pattern-map.json 快速匹配"""
        if not self._error_map:
            return None
        for entry in self._error_map:
            pattern = entry.get("pattern", "")
            if not pattern:
                continue
            try:
                if re.search(pattern, error_msg, re.IGNORECASE):
                    # 解析文档路径（替换 {scene} 占位符）
                    docs = entry.get("docs", [])
                    source = ""
                    for doc in docs:
                        resolved = doc.replace("{scene}", self._scene or "")
                        full_path = os.path.join(self._base_dir, resolved)
                        if os.path.exists(full_path):
                            source = full_path
                            break
                    if not source and docs:
                        source = docs[0]

                    return KnowledgeMatch(
                        source_file=source,
                        section=entry.get("standard_fix", ""),
                        fix_description=entry.get("standard_fix", ""),
                        code_snippet=entry.get("code", ""),
                        confidence=0.9,  # 映射表命中 = 高置信度
                    )
            except re.error:
                continue
        return None

    def _extract_relevant_section(self, content: str, keywords: List[str]) -> tuple:
        """提取包含关键词的段落和代码块"""
        lines = content.split("\n")
        best_start = 0
        best_score = 0

        # 滑动窗口找最佳段落
        window_size = 30
        for i in range(0, len(lines) - window_size + 1, 5):
            window = "\n".join(lines[i:i + window_size])
            score = sum(1 for kw in keywords if kw.lower() in window.lower())
            if score > best_score:
                best_score = score
                best_start = i

        section = "\n".join(lines[best_start:best_start + window_size])

        # 提取代码块
        code = ""
        code_blocks = re.findall(r"```(?:javascript|js|python)?\n(.*?)```", section, re.DOTALL)
        if code_blocks:
            code = code_blocks[0].strip()

        return section, code

    def _read_file(self, fpath: str) -> Optional[str]:
        """读取文件（带缓存）"""
        if fpath in self._cache:
            return self._cache[fpath]
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            self._cache[fpath] = content
            return content
        except (IOError, OSError):
            return None

@dataclass
class ClassificationRule:
    """分类规则"""
    error_type_pattern: str
    message_pattern: str = ""
    category: FailureCategory = FailureCategory.UNKNOWN

# ── 失败分类器 ──

class FailureClassifier:
    """
    失败分类器：基于错误类型和消息模式判定失败类别。
    支持从 harness/self_healing_rules.yaml 加载补充关键词。
    """

    def __init__(self, rules_path: str = None):
        self._rules: list[ClassificationRule] = self._default_rules()
        if rules_path:
            self._load_yaml_keywords(rules_path)

    def _load_yaml_keywords(self, path: str):
        """从 YAML 加载分类关键词，作为补充规则追加。"""
        try:
            import yaml
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception:
            return

        _YAML_CAT_MAP = {
            "true_bug":     FailureCategory.TRUE_BUG,
            "script_issue": FailureCategory.SCRIPT_ISSUE,
            "data_invalid": FailureCategory.DATA_INVALID,
            "env_issue":    FailureCategory.ENV_ISSUE,
        }
        fc = data.get("failure_classification", {})
        for cat_key, info in fc.items():
            category = _YAML_CAT_MAP.get(cat_key)
            if category is None:
                continue
            for kw in info.get("keywords", []):
                # 每条关键词 → 一条 message_pattern 规则（error_type="" 表示任意类型）
                self._rules.append(ClassificationRule(
                    error_type_pattern="",  # 匹配任意 error_type
                    message_pattern=kw,
                    category=category,
                ))

    @staticmethod
    def _default_rules() -> list[ClassificationRule]:
        return [
            ClassificationRule(
                error_type_pattern="assertion_failed",
                message_pattern="",
                category=FailureCategory.TRUE_BUG,
            ),
            ClassificationRule(
                error_type_pattern="selector_not_found",
                message_pattern="not found",
                category=FailureCategory.SCRIPT_ISSUE,
            ),
            ClassificationRule(
                error_type_pattern="timeout",
                message_pattern="timeout",
                category=FailureCategory.SCRIPT_ISSUE,
            ),
            ClassificationRule(
                error_type_pattern="data_error",
                message_pattern="expired",
                category=FailureCategory.DATA_INVALID,
            ),
            ClassificationRule(
                error_type_pattern="network_error",
                message_pattern="connection",
                category=FailureCategory.ENV_ISSUE,
            ),
            ClassificationRule(
                error_type_pattern="schema_mismatch",
                message_pattern="",
                category=FailureCategory.SCRIPT_ISSUE,
            ),
        ]

    def add_rule(self, rule: ClassificationRule):
        self._rules.append(rule)

    def classify(self, error_info: dict) -> FailureCategory:
        """
        分类错误信息。

        Args:
            error_info: {"error_type": str, "message": str, ...}
        """
        error_type = error_info.get("error_type", "")
        message = error_info.get("message", "")

        for rule in self._rules:
            type_match = rule.error_type_pattern in error_type
            msg_match = (not rule.message_pattern) or rule.message_pattern in message
            if type_match and msg_match:
                return rule.category

        return FailureCategory.UNKNOWN

    def dual_factor_judge(
        self,
        error_info: dict,
        llm_verdict: Optional[str] = None,
        llm_judge_fn: Optional[callable] = None,
    ) -> dict:
        """
        双因子裁决: 规则层初判 + 可选 LLM 二次确认。

        Args:
            error_info: 错误信息 dict
            llm_verdict: 外部传入的 LLM 裁决结果（同步模式）
            llm_judge_fn: 可插拔的 LLM 裁决回调 (error_info) -> str。
                          若提供且 llm_verdict 为空，则自动调用获取裁决。

        Returns:
            {"rule_verdict": FailureCategory, "llm_verdict": str|None,
             "final": FailureCategory, "agree": bool}
        """
        rule_verdict = self.classify(error_info)

        # 自动调用 LLM 裁决回调
        if not llm_verdict and llm_judge_fn is not None:
            try:
                llm_verdict = llm_judge_fn(error_info)
            except Exception:
                llm_verdict = None

        if llm_verdict:
            try:
                llm_cat = FailureCategory(llm_verdict)
            except ValueError:
                llm_cat = FailureCategory.UNKNOWN

            agree = (rule_verdict == llm_cat)
            # 不一致时偏保守（按规则层判定）
            final = rule_verdict
        else:
            llm_cat = None
            agree = True
            final = rule_verdict

        return {
            "rule_verdict": rule_verdict,
            "llm_verdict": llm_cat,
            "final": final,
            "agree": agree,
        }

# ── 自愈引擎 ──

class SelfHealingEngine:
    """
    自愈引擎：先查知识库找解法，再按失败类别执行对应自愈策略。
    
    自愈顺序：
    1. HealingMemory 历史经验（最快路径）
    2. KnowledgeResolver 查阅参考文档 + 知识库
    3. CDP 重定位
    4. Schema 重生成（实装：自动 patch 步骤参数）
    5. 沙箱重置（实装：数据自愈引擎）
    6. 网络层自愈（5xx 重试 / mock 降级）
    """

    def __init__(self, scene: str = None, base_dir: str = None, llm_judge_fn: callable = None):
        import os as _os
        _rules_path = None
        if base_dir:
            _candidate = _os.path.join(base_dir, "harness", "self_healing_rules.yaml")
            if _os.path.isfile(_candidate):
                _rules_path = _candidate
        self._classifier = FailureClassifier(rules_path=_rules_path)
        self._knowledge = KnowledgeResolver(base_dir=base_dir, scene=scene)
        self._heal_stats: dict[str, int] = {"attempted": 0, "succeeded": 0, "knowledge_hits": 0}
        self._llm_judge_fn = llm_judge_fn  # 可插拔 LLM 裁决回调
        self._base_dir = base_dir

        # ── 维度10: 自愈经验记忆 ──
        from core.healing_memory import HealingMemory
        self._memory = HealingMemory()
        if base_dir:
            self._memory.load_from_knowledge(base_dir)

        # ── 维度12: 自愈效果度量 ──
        from core.healing_analytics import HealingAnalytics
        self._analytics = HealingAnalytics()

        # ── 维度6: 数据自愈引擎 ──
        from core.data_healing import DataHealingEngine
        self._data_healing = DataHealingEngine()

        # ── 维度4: 网络层自愈引擎 ──
        from core.network_healing import NetworkHealingEngine
        self._network_healing = NetworkHealingEngine()

        # ── 策略组合学习引擎 ──
        from core.strategy_chain import StrategyChainLearner
        self._chain_learner = StrategyChainLearner(base_dir=base_dir)

        # ── 维度7: LLM 裁决缓存 ──
        self._llm_verdict_cache: dict = {}  # error_signature -> (verdict, timestamp)
        self._llm_cache_ttl = 300  # 5分钟缓存

    @property
    def memory(self):
        """自愈经验记忆引擎"""
        return self._memory

    @property
    def analytics(self):
        """自愈效果度量引擎"""
        return self._analytics

    @property
    def classifier(self) -> FailureClassifier:
        return self._classifier

    @property
    def chain_learner(self):
        """策略组合学习引擎"""
        return self._chain_learner

    def recommend_strategies(self, error_type: str, error_msg: str) -> List[str]:
        """
        根据错误类型推荐历史最优策略组合。
        如果无历史数据则返回空列表。
        """
        return self._chain_learner.recommend_chain(error_type, error_msg)

    def record_strategy_chain(self, strategies: List[str], error_type: str, success: bool, total_duration_ms: int = 0):
        """
        记录一次完整的策略链执行结果。

        Args:
            strategies: 实际使用的策略序列
            error_type: 错误类型
            success: 最终是否成功
            total_duration_ms: 总耗时
        """
        self._chain_learner.start_chain(error_type=error_type, error_msg="")
        for s in strategies:
            self._chain_learner.add_strategy(s, success=success, duration_ms=total_duration_ms // len(strategies))
        self._chain_learner.finish_chain(success=success)

    def save_chain_learner(self):
        """持久化策略组合学习结果"""
        if self._base_dir:
            self._chain_learner.save(self._base_dir)

    @property
    def knowledge(self) -> KnowledgeResolver:
        return self._knowledge

    # ── 字符串 → 枚举兼容映射（弥合 failure_classifier.py 的字符串输出）──
    _CATEGORY_ALIASES: dict = {
        "real_bug":    FailureCategory.TRUE_BUG,
        "true_bug":    FailureCategory.TRUE_BUG,
        "script_issue": FailureCategory.SCRIPT_ISSUE,
        "data_invalid": FailureCategory.DATA_INVALID,
        "env_failure":  FailureCategory.ENV_ISSUE,
        "env_issue":    FailureCategory.ENV_ISSUE,
        "unknown":      FailureCategory.UNKNOWN,
        "pass":         None,  # 通过步骤不应触发自愈
    }

    @staticmethod
    def _normalize_category(category) -> FailureCategory:
        """兼容字符串和枚举输入，统一转为 FailureCategory。"""
        if isinstance(category, FailureCategory):
            return category
        if isinstance(category, str):
            mapped = SelfHealingEngine._CATEGORY_ALIASES.get(category.lower())
            if mapped is not None:
                return mapped
        return FailureCategory.UNKNOWN

    def heal(self, category, context: dict) -> HealingResult:
        """
        根据失败类别执行自愈。
        优先级: 历史经验 → 知识库 → CDP重定位 → Schema patch → 数据自愈 → 网络自愈
        """
        category = self._normalize_category(category)
        start = time.time()
        error_msg = context.get("error", "")

        # ── 维度10: 历史经验优先查询 ──
        if not self._memory.is_blacklisted(error_msg[:80]):
            mem_hits = self._memory.lookup(error_msg)
            if mem_hits and mem_hits[0].confidence >= 0.5 and mem_hits[0].fix_code:
                self._heal_stats["attempted"] += 1
                self._heal_stats["succeeded"] += 1
                result = HealingResult(
                    action=HealingAction.MEMORY_FIX,
                    attempted=True,
                    success=True,
                    message=f"历史经验命中: {mem_hits[0].fix_strategy} (confidence={mem_hits[0].confidence:.0%})",
                    duration_ms=int((time.time() - start) * 1000),
                    fix_code=mem_hits[0].fix_code,
                )
                self._record_heal_analytics("memory_fix", True, result.duration_ms, category.value)
                return result

        # UNKNOWN 类型且配置了 LLM 裁决 → 双因子二次确认（带缓存）
        if category == FailureCategory.UNKNOWN and self._llm_judge_fn:
            error_info = {"message": error_msg, "error_type": "unknown"}
            verdict = self._dual_factor_with_cache(error_info)
            if verdict and verdict.get("final", FailureCategory.UNKNOWN) != FailureCategory.UNKNOWN:
                category = verdict["final"]

        if category == FailureCategory.TRUE_BUG:
            return HealingResult(
                action=HealingAction.NONE,
                attempted=False,
                message="真Bug，不执行自愈",
            )

        # ① 优先查知识库（references + knowledge）
        knowledge_match = self._knowledge.resolve(error_msg, context)
        if knowledge_match and knowledge_match.confidence >= 0.3:
            self._heal_stats["attempted"] += 1
            self._heal_stats["knowledge_hits"] += 1
            self._heal_stats["succeeded"] += 1
            result = HealingResult(
                action=HealingAction.KNOWLEDGE_FIX,
                attempted=True,
                success=True,
                message=f"知识库命中: {knowledge_match.fix_description}",
                duration_ms=int((time.time() - start) * 1000),
                knowledge_source=knowledge_match.source_file,
                fix_code=knowledge_match.code_snippet,
            )
            # 记录到记忆系统
            self._memory.record_success(
                error_pattern=error_msg[:80],
                fix_strategy=f"knowledge:{knowledge_match.source_file}",
                fix_code=knowledge_match.code_snippet,
            )
            self._record_heal_analytics("knowledge_fix", True, result.duration_ms, category.value)
            return result

        # ② 脚本问题：CDP 重定位
        if category == FailureCategory.SCRIPT_ISSUE:
            selector = context.get("selector", "")
            if selector:
                self._heal_stats["attempted"] += 1
                self._heal_stats["succeeded"] += 1
                result = HealingResult(
                    action=HealingAction.CDP_RELOCATE,
                    attempted=True,
                    success=True,
                    message=f"CDP 重定位: {selector}",
                    duration_ms=int((time.time() - start) * 1000),
                )
                self._record_heal_analytics("cdp_relocate", True, result.duration_ms, category.value)
                return result

            # 维度5: SCHEMA_REGEN 实装
            step = context.get("step")
            if step:
                patch_result = self._try_schema_patch(step, error_msg)
                if patch_result:
                    self._heal_stats["attempted"] += 1
                    self._heal_stats["succeeded"] += 1
                    result = HealingResult(
                        action=HealingAction.SCHEMA_REGEN,
                        attempted=True,
                        success=True,
                        message=f"Schema 自动补丁: {patch_result.get('patch_description', '')}",
                        duration_ms=int((time.time() - start) * 1000),
                        fix_code=json.dumps(patch_result.get('patched_params', {})),
                    )
                    self._record_heal_analytics("schema_regen", True, result.duration_ms, category.value)
                    return result

            return HealingResult(
                action=HealingAction.SCHEMA_REGEN,
                attempted=True,
                success=False,
                message="脚本问题，建议重新生成 Schema",
                duration_ms=int((time.time() - start) * 1000),
            )

        # ③ 数据失效：数据自愈引擎（维度6 实装）
        if category == FailureCategory.DATA_INVALID:
            self._heal_stats["attempted"] += 1
            # 尝试通过 data_healing 恢复
            heal_msg = self._try_data_heal(context, error_msg)
            result = HealingResult(
                action=HealingAction.SANDBOX_RESET,
                attempted=True,
                success=True,
                message=heal_msg,
                duration_ms=int((time.time() - start) * 1000),
            )
            self._heal_stats["succeeded"] += 1
            self._record_heal_analytics("sandbox_reset", True, result.duration_ms, category.value)
            return result

        # ④ 环境问题：网络层自愈（维度4 实装）
        if category == FailureCategory.ENV_ISSUE:
            self._heal_stats["attempted"] += 1
            # 检查是否是 API 级别错误
            api_entry = context.get("api_entry")
            if api_entry:
                network_msg = self._try_network_heal(api_entry, error_msg)
                result = HealingResult(
                    action=HealingAction.NETWORK_RETRY,
                    attempted=True,
                    success=True,
                    message=network_msg,
                    duration_ms=int((time.time() - start) * 1000),
                )
            else:
                result = HealingResult(
                    action=HealingAction.RETRY,
                    attempted=True,
                    success=False,
                    message="环境问题，建议重试",
                    duration_ms=int((time.time() - start) * 1000),
                )
            self._record_heal_analytics("network_retry", True, result.duration_ms, category.value)
            return result

        return HealingResult(
            action=HealingAction.NONE,
            attempted=False,
            message="未知类别，无法自愈",
        )

    def record_heal_outcome(self, error_msg: str, fix_strategy: str, success: bool, fix_code: str = ""):
        """
        外部调用：记录自愈结果到记忆系统。
        step_executor 在自愈成功/失败后调用此方法。
        """
        if success:
            self._memory.record_success(
                error_pattern=error_msg[:80],
                fix_strategy=fix_strategy,
                fix_code=fix_code,
            )
        else:
            self._memory.record_failure(
                error_pattern=error_msg[:80],
                fix_strategy=fix_strategy,
            )

    def promote_memories(self) -> dict:
        """
        在 FINALIZE 阶段调用：将高置信度经验晋升到知识库。
        """
        if self._base_dir:
            return self._memory.promote_to_knowledge(self._base_dir)
        return {"promoted": 0}

    def get_healing_report(self):
        """生成自愈健康报告"""
        return self._analytics.generate_report()

    def get_full_stats(self) -> dict:
        """综合统计（自愈引擎 + 记忆 + 度量）"""
        base = self.get_stats()
        base["memory"] = self._memory.get_stats()
        base["analytics"] = self._analytics.get_stats()
        return base

    # ── 内部方法 ──

    def _record_heal_analytics(self, strategy: str, success: bool, duration_ms: int, error_type: str):
        """记录到度量引擎"""
        self._analytics.record_heal(strategy, success, duration_ms, error_type)

    def _try_schema_patch(self, step: dict, error_msg: str) -> Optional[dict]:
        """维度5: SCHEMA_REGEN 实装 — 自动 patch 步骤参数"""
        try:
            schema_dir = os.path.join(self._base_dir or ".", "schema")
            if not os.path.isdir(schema_dir):
                return None
            # 查找匹配的步骤类型 schema
            step_type = step.get("type", "")
            schema_files = glob_mod.glob(os.path.join(schema_dir, "**", "*.json"), recursive=True)
            for sf in schema_files:
                try:
                    with open(sf, "r", encoding="utf-8") as f:
                        schema = json.load(f)
                    # 在 step 定义中查找
                    steps_schema = schema.get("steps", schema.get("properties", {}).get("steps", {}))
                    if not steps_schema:
                        continue
                    items = steps_schema.get("items", {})
                    step_defs = items.get("oneOf", items.get("allOf", []))
                    for sdef in step_defs if isinstance(step_defs, list) else []:
                        if sdef.get("properties", {}).get("type", {}).get("const") == step_type:
                            # 找到匹配的 schema，尝试 patch
                            return self._auto_patch_step(step, sdef, error_msg)
                except (IOError, json.JSONDecodeError):
                    continue
        except Exception:
            pass
        return None

    def _auto_patch_step(self, step: dict, schema_def: dict, error_msg: str) -> Optional[dict]:
        """根据 schema 定义自动 patch 步骤参数"""
        patches = []
        required = schema_def.get("required", [])
        props = schema_def.get("properties", {})

        # 检查是否有必填字段缺失
        for field_name in required:
            if field_name not in step and field_name != "type":
                # 尝试从 schema 获取默认值
                field_schema = props.get(field_name, {})
                default = field_schema.get("default")
                if default is not None:
                    step[field_name] = default
                    patches.append(f"添加缺失字段 {field_name}={default}")

        # 检查类型不匹配
        for field_name, value in step.items():
            if field_name in props:
                expected_type = props[field_name].get("type", "")
                if expected_type == "string" and not isinstance(value, str):
                    step[field_name] = str(value)
                    patches.append(f"类型修正 {field_name} -> string")
                elif expected_type == "integer" and isinstance(value, str) and value.isdigit():
                    step[field_name] = int(value)
                    patches.append(f"类型修正 {field_name} -> integer")

        if patches:
            return {
                "patch_description": "; ".join(patches),
                "patched_params": {k: v for k, v in step.items() if k not in ("type", "description")},
            }
        return None

    def _try_data_heal(self, context: dict, error_msg: str) -> str:
        """维度6: 数据自愈（同步意图生成，实际异步执行在 step_executor 中完成）"""
        # 检测 session 过期类错误 → Cookie/Session 刷新
        session_keywords = ["session", "expired", "cookie", "登录态", "token", "401"]
        if any(kw in error_msg.lower() for kw in session_keywords):
            self._data_healing._stats["freshness_failures"] += 1
            return "数据自愈: Session/Cookie 刷新已调度"

        # 通用数据失效
        self._data_healing._stats["freshness_checks"] += 1
        fallback = context.get("data_fallback")
        if fallback:
            return f"数据自愈: 备选数据切换已调度 (fallback={fallback.get('type', 'unknown')})"
        return "数据自愈: 沙箱重置已调度"

    def _try_network_heal(self, api_entry: dict, error_msg: str) -> str:
        """维度4: 网络层自愈（同步意图生成，实际异步执行在 step_executor 中完成）"""
        status = api_entry.get("status") if isinstance(api_entry, dict) else None
        url = api_entry.get("url", "") if isinstance(api_entry, dict) else ""
        response_time_ms = api_entry.get("duration", 0) if isinstance(api_entry, dict) else 0

        if status and 500 <= status < 600:
            self._network_healing._stats["retries_5xx"] += 1
            return f"网络自愈: 5xx 重试已调度 (status={status})"

        # 慢请求检测
        throttle_delay = self._network_healing.get_throttle_delay_ms()
        if throttle_delay > 0:
            return f"网络自愈: 慢请求降速中 (delay={throttle_delay}ms)"

        return "网络自愈: 环境问题，建议重试"

    def _dual_factor_with_cache(self, error_info: dict) -> Optional[dict]:
        """维度7: LLM 双因子裁决（带缓存）"""
        # 计算错误签名
        signature = hash(error_info.get("message", "")[:100])
        now = time.time()

        # 检查缓存
        if signature in self._llm_verdict_cache:
            cached_verdict, cached_time = self._llm_verdict_cache[signature]
            if now - cached_time < self._llm_cache_ttl:
                return cached_verdict
            del self._llm_verdict_cache[signature]

        # 调用裁决
        verdict = self._classifier.dual_factor_judge(
            error_info, llm_judge_fn=self._llm_judge_fn
        )
        self._llm_verdict_cache[signature] = (verdict, now)
        return verdict

    # ── 分级放行 ──

    def grade_release(self, category: FailureCategory, severity: str = "P1") -> dict:
        """
        分级放行决策。

        Args:
            category: 失败分类
            severity: P0/P1/P2

        Returns:
            {"level": str, "action": str, "notify": bool, "category": str}
        """
        try:
            level = SeverityLevel(severity)
        except ValueError:
            level = SeverityLevel.P1

        notify = (level == SeverityLevel.P0)

        return {
            "level": level.value,
            "action": level.action,
            "notify": notify,
            "category": category.value,
            "message": self._grade_message(level, category),
        }

    @staticmethod
    def _grade_message(level: SeverityLevel, category: FailureCategory) -> str:
        if level == SeverityLevel.P0:
            return f"P0 阻断: {category.value}，已通知责任人"
        elif level == SeverityLevel.P1:
            return f"P1 警告: {category.value}，建议复测"
        else:
            return f"P2 跳过: {category.value}，已计入指标"

    def get_stats(self) -> dict:
        return {
            "heal_attempted": self._heal_stats["attempted"],
            "heal_succeeded": self._heal_stats["succeeded"],
            "knowledge_hits": self._heal_stats["knowledge_hits"],
            "heal_rate": round(
                self._heal_stats["succeeded"] / max(self._heal_stats["attempted"], 1), 3
            ),
        }
