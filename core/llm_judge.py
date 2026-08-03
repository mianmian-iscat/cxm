"""llm_judge.py — LLM 多因子裁决引擎

为自愈引擎提供 LLM 裁决能力：
- 双因子裁决：规则层 + LLM 层合并取最终判定
- 置信度输出：每次裁决附带 confidence 和 reasoning
- 裁决日志：记录每次裁决的输入/输出，支持准确率统计
- TTL 缓存：相同错误在 TTL 内复用裁决结果，节省 token
- 双模型对抗（DualLLMJudge）：两个模型独立裁决，一致性校验

支持的 Provider：
- openai: 兼容 OpenAI Chat Completions API（含 DashScope 通义千问）
- mock: 纯本地规则引擎（不调用任何 LLM，用于无 LLM 接入时兜底）

使用方式：
    from core.llm_judge import create_llm_judge, JudgmentResult

    judge_fn = create_llm_judge(config={...})
    result: JudgmentResult = judge_fn({"message": "element not interactable"})
    print(result.category, result.confidence)  # script_issue 0.92
"""

import json
import os
import re
import time
import hashlib
import threading
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List


# ── 常量 ──

_FAILURE_CATEGORIES = [
    "script_issue",
    "env_failure",
    "data_invalid",
    "true_bug",
    "unknown",
]


# ── 裁决结果数据模型 ──

@dataclass
class JudgmentResult:
    """裁决结果：类别 + 置信度 + 推理说明"""
    category: str = "unknown"
    confidence: float = 0.0      # 0.0~1.0，越高越可信
    reasoning: str = ""          # 裁决依据简述
    provider: str = "mock"       # 裁决来源 provider 名称
    cached: bool = False         # 是否命中缓存
    latency_ms: int = 0          # 裁决耗时

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "confidence": round(self.confidence, 3),
            "reasoning": self.reasoning,
            "provider": self.provider,
            "cached": self.cached,
            "latency_ms": self.latency_ms,
        }

    def __str__(self) -> str:
        """向后兼容：直接当字符串用时返回 category"""
        return self.category

    # 让 JudgmentResult 可以和字符串直接比较（向后兼容）
    def __eq__(self, other):
        if isinstance(other, str):
            return self.category == other
        if isinstance(other, JudgmentResult):
            return self.category == other.category and self.confidence == other.confidence
        return NotImplemented

    def __hash__(self):
        return hash(self.category)


@dataclass
class JudgmentLogEntry:
    """裁决日志条目"""
    error_hash: str = ""
    error_message: str = ""
    result: JudgmentResult = field(default_factory=JudgmentResult)
    human_label: str = ""        # 人工标注的正确类别（用于计算准确率）
    timestamp: float = field(default_factory=time.time)


class JudgmentLog:
    """
    裁决日志：记录每次裁决，支持人工标注反馈和准确率统计。
    """

    def __init__(self, persist_path: str = ""):
        self._entries: list[JudgmentLogEntry] = []
        self._persist_path = persist_path
        self._lock = threading.Lock()
        if persist_path and os.path.isfile(persist_path):
            self._load()

    def record(self, error_info: dict, result: JudgmentResult) -> JudgmentLogEntry:
        entry = JudgmentLogEntry(
            error_hash=_hash_error(error_info.get("message", "")),
            error_message=error_info.get("message", "")[:200],
            result=result,
        )
        with self._lock:
            self._entries.append(entry)
            if self._persist_path:
                self._save()
        return entry

    def label(self, error_hash: str, correct_category: str) -> bool:
        """人工标注某次裁决的正确类别"""
        with self._lock:
            for entry in reversed(self._entries):
                if entry.error_hash == error_hash and not entry.human_label:
                    entry.human_label = correct_category
                    if self._persist_path:
                        self._save()
                    return True
        return False

    def accuracy(self, min_confidence: float = 0.0) -> dict:
        """统计裁决准确率（仅统计已标注的条目）"""
        labeled = [e for e in self._entries if e.human_label and e.result.confidence >= min_confidence]
        if not labeled:
            return {"total_labeled": 0, "correct": 0, "accuracy": 0.0}
        correct = sum(1 for e in labeled if e.result.category == e.human_label)
        return {
            "total_labeled": len(labeled),
            "correct": correct,
            "accuracy": round(correct / len(labeled) * 100, 1),
            "by_provider": self._accuracy_by_provider(labeled),
        }

    def _accuracy_by_provider(self, labeled: list) -> dict:
        by_prov = {}
        for e in labeled:
            prov = e.result.provider
            if prov not in by_prov:
                by_prov[prov] = {"total": 0, "correct": 0}
            by_prov[prov]["total"] += 1
            if e.result.category == e.human_label:
                by_prov[prov]["correct"] += 1
        return {
            p: {"total": v["total"], "correct": v["correct"],
                "accuracy": round(v["correct"] / v["total"] * 100, 1)}
            for p, v in by_prov.items()
        }

    def get_entries(self, limit: int = 50) -> list[dict]:
        return [
            {"hash": e.error_hash, "message": e.error_message,
             "category": e.result.category, "confidence": e.result.confidence,
             "provider": e.result.provider, "human_label": e.human_label,
             "timestamp": e.timestamp}
            for e in self._entries[-limit:]
        ]

    def _save(self):
        try:
            data = [
                {"error_hash": e.error_hash, "error_message": e.error_message,
                 "category": e.result.category, "confidence": e.result.confidence,
                 "reasoning": e.result.reasoning, "provider": e.result.provider,
                 "human_label": e.human_label, "timestamp": e.timestamp}
                for e in self._entries
            ]
            with open(self._persist_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load(self):
        try:
            with open(self._persist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                entry = JudgmentLogEntry(
                    error_hash=item.get("error_hash", ""),
                    error_message=item.get("error_message", ""),
                    result=JudgmentResult(
                        category=item.get("category", "unknown"),
                        confidence=item.get("confidence", 0.0),
                        reasoning=item.get("reasoning", ""),
                        provider=item.get("provider", "mock"),
                    ),
                    human_label=item.get("human_label", ""),
                    timestamp=item.get("timestamp", 0.0),
                )
                self._entries.append(entry)
        except Exception:
            pass


# ── 裁决缓存（TTL） ──

class JudgmentCache:
    """内存级裁决缓存，相同错误在 TTL 内复用结果"""

    def __init__(self, ttl_seconds: int = 300):
        self._ttl = ttl_seconds
        self._cache: dict[str, tuple[JudgmentResult, float]] = {}
        self._lock = threading.Lock()

    def get(self, error_hash: str) -> Optional[JudgmentResult]:
        with self._lock:
            item = self._cache.get(error_hash)
            if item and (time.time() - item[1]) < self._ttl:
                result = JudgmentResult(
                    category=item[0].category,
                    confidence=item[0].confidence,
                    reasoning=item[0].reasoning,
                    provider=item[0].provider,
                    cached=True,
                )
                return result
            return None

    def put(self, error_hash: str, result: JudgmentResult):
        with self._lock:
            self._cache[error_hash] = (result, time.time())

    def clear(self):
        with self._lock:
            self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)


def _hash_error(message: str) -> str:
    """对错误消息做归一化哈希（去除动态ID/hash/路径后取MD5）"""
    normalized = re.sub(r'\b\d{4,}\b', '<ID>', message)
    normalized = re.sub(r'\b[0-9a-f]{8,}\b', '<HASH>', normalized, flags=re.I)
    normalized = re.sub(r'//[\S]+', '<URL>', normalized)
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()[:12]

_SYSTEM_PROMPT = """你是一个 Web 自动化测试的错误分类专家。
你的任务是根据错误信息，判断该错误属于以下哪一类：

- script_issue: 脚本问题（元素定位失败、选择器失效、页面结构变更）
- env_failure: 环境问题（网络超时、服务不可用、CDP断连、登录态过期）
- data_invalid: 数据问题（表单校验失败、必填字段缺失、数据格式错误）
- true_bug: 真实Bug（功能逻辑错误、UI异常、数据不一致——需要人工修复）
- unknown: 无法判断

请只返回类别名称（上面5个之一），不要返回其他内容。"""

_USER_PROMPT_TEMPLATE = """错误信息：
{error_message}

错误上下文：
- 步骤类型：{step_type}
- 选择器：{selector}
- 页面URL：{page_url}

请判断这个错误属于哪一类？"""


# ── Provider 抽象 ──

class LLMProvider:
    """LLM Provider 基类"""

    def classify(self, error_info: dict) -> str:
        """对错误进行分类，返回类别字符串"""
        raise NotImplementedError


class MockLLMProvider(LLMProvider):
    """Mock Provider: 纯规则引擎，不调用任何 LLM"""

    # 关键词 -> (类别, 基准置信度)
    _KEYWORD_RULES: list[tuple[str, str, float]] = [
        ("script_issue", "element", 0.85),
        ("script_issue", "selector", 0.85),
        ("script_issue", "find", 0.75),
        ("script_issue", "queryselector", 0.90),
        ("script_issue", "xpath", 0.90),
        ("script_issue", "offsetparent", 0.85),
        ("script_issue", "not interactable", 0.90),
        ("script_issue", "not visible", 0.88),
        ("script_issue", "stale", 0.85),
        ("script_issue", "detached", 0.85),
        ("script_issue", "no such element", 0.92),
        ("env_failure", "timeout", 0.82),
        ("env_failure", "econnrefused", 0.90),
        ("env_failure", "econnreset", 0.90),
        ("env_failure", "navigation", 0.78),
        ("env_failure", "net::", 0.88),
        ("env_failure", "connection", 0.80),
        ("env_failure", "cdp", 0.85),
        ("env_failure", "websocket", 0.85),
        ("env_failure", "disconnected", 0.88),
        ("env_failure", "session", 0.75),
        ("env_failure", "cookie", 0.72),
        ("env_failure", "401", 0.90),
        ("env_failure", "403", 0.88),
        ("env_failure", "expired", 0.80),
        ("data_invalid", "required", 0.82),
        ("data_invalid", "validation", 0.80),
        ("data_invalid", "schema", 0.85),
        ("data_invalid", "format", 0.75),
        ("data_invalid", "invalid", 0.72),
        ("data_invalid", "必填", 0.90),
        ("data_invalid", "校验失败", 0.90),
        ("data_invalid", "格式错误", 0.88),
    ]

    def classify(self, error_info: dict) -> str:
        result = self.classify_full(error_info)
        return result.category

    def classify_full(self, error_info: dict) -> JudgmentResult:
        """完整裁决：返回类别 + 置信度 + 推理"""
        msg = error_info.get("message", "").lower()
        best_cat = "unknown"
        best_conf = 0.0
        matched_kws: list[str] = []

        for cat, kw, conf in self._KEYWORD_RULES:
            if kw in msg:
                matched_kws.append(kw)
                if conf > best_conf:
                    best_cat = cat
                    best_conf = conf

        # 多关键词命中提升置信度
        if len(matched_kws) >= 2:
            best_conf = min(best_conf + 0.05, 1.0)

        reasoning = f"规则匹配关键词: {', '.join(matched_kws[:5])}" if matched_kws else "无匹配关键词"
        return JudgmentResult(
            category=best_cat, confidence=best_conf, reasoning=reasoning, provider="mock"
        )


class OpenAICompatibleProvider(LLMProvider):
    """兼容 OpenAI Chat Completions API 的 Provider（含 DashScope 通义千问）"""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        timeout: int = 10,
        temperature: float = 0.0,
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._temperature = temperature
        self._stats = {"calls": 0, "success": 0, "fail": 0, "total_ms": 0}

    def classify(self, error_info: dict) -> str:
        result = self.classify_full(error_info)
        return result.category

    def classify_full(self, error_info: dict) -> JudgmentResult:
        """完整裁决：返回类别 + 置信度 + 推理"""
        start = time.time()
        self._stats["calls"] += 1

        try:
            prompt = self._build_prompt(error_info)
            raw = self._call_api(prompt)
            category, confidence, reasoning = self._parse_response_full(raw)
            latency = int((time.time() - start) * 1000)
            self._stats["success"] += 1
            self._stats["total_ms"] += latency
            return JudgmentResult(
                category=category, confidence=confidence,
                reasoning=reasoning, provider=f"llm:{self._model}",
                latency_ms=latency,
            )
        except Exception as e:
            latency = int((time.time() - start) * 1000)
            self._stats["fail"] += 1
            self._stats["total_ms"] += latency
            return JudgmentResult(
                category="unknown", confidence=0.0,
                reasoning=f"LLM 调用失败: {e}", provider=f"llm:{self._model}",
                latency_ms=latency,
            )

    def get_stats(self) -> dict:
        return dict(self._stats)

    def _build_prompt(self, error_info: dict) -> str:
        return _USER_PROMPT_TEMPLATE.format(
            error_message=error_info.get("message", "")[:500],
            step_type=error_info.get("step_type", "unknown"),
            selector=error_info.get("selector", "")[:200],
            page_url=error_info.get("page_url", "")[:300],
        )

    def _call_api(self, user_prompt: str) -> str:
        """调用 OpenAI-compatible API"""
        url = f"{self._base_url}/chat/completions"
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self._temperature,
            "max_tokens": 20,  # 只需返回类别名
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))

        choices = body.get("choices", [])
        if not choices:
            raise ValueError("LLM API returned no choices")

        content = choices[0].get("message", {}).get("content", "")
        return content.strip()

    @staticmethod
    def _parse_response(response: str) -> str:
        """解析 LLM 响应，提取类别（向后兼容）"""
        cat, _, _ = OpenAICompatibleProvider._parse_response_full(response)
        return cat

    @staticmethod
    def _parse_response_full(response: str) -> tuple[str, float, str]:
        """解析 LLM 响应，提取类别 + 置信度 + 推理

        支持两种响应格式：
        - 简洁格式：只返回类别名 → 置信度默认 0.75
        - 完整格式：`类别名|置信度|推理` 或 JSON {"category", "confidence", "reasoning"}
        """
        response = response.strip()
        response_lower = response.lower()

        # 尝试 JSON 格式解析
        if response.startswith("{"):
            try:
                data = json.loads(response)
                cat = data.get("category", "unknown")
                conf = float(data.get("confidence", 0.75))
                reason = data.get("reasoning", "LLM JSON 响应")
                if cat in _FAILURE_CATEGORIES:
                    return cat, conf, reason
            except (json.JSONDecodeError, ValueError):
                pass

        # 尝试 pipe 分隔格式：category|confidence|reasoning
        if "|" in response:
            parts = response.split("|", 2)
            cat_candidate = parts[0].strip().lower()
            for cat in _FAILURE_CATEGORIES:
                if cat in cat_candidate:
                    conf = 0.75
                    try:
                        conf = float(parts[1].strip()) if len(parts) > 1 else 0.75
                    except ValueError:
                        pass
                    reason = parts[2].strip() if len(parts) > 2 else "LLM pipe 格式"
                    return cat, conf, reason

        # 简洁格式：直接匹配类别名
        for cat in _FAILURE_CATEGORIES:
            if cat in response_lower:
                return cat, 0.75, f"LLM 返回: {response[:80]}"

        # 模糊别名匹配
        aliases = {
            "script": "script_issue", "selector": "script_issue",
            "element": "script_issue", "env": "env_failure",
            "network": "env_failure", "timeout": "env_failure",
            "connection": "env_failure", "data": "data_invalid",
            "validation": "data_invalid", "bug": "true_bug",
            "real bug": "true_bug", "真": "true_bug",
        }
        for alias, category in aliases.items():
            if alias in response_lower:
                return category, 0.65, f"LLM 模糊匹配 '{alias}'"

        return "unknown", 0.3, f"LLM 无法解析: {response[:80]}"


# ── 双模型对抗裁决 ──

class DualLLMJudge:
    """
    双模型对抗裁决器：两个 Provider 独立裁决，一致性校验。

    - 两模型一致 → 采信，置信度取均值+加成
    - 两模型不一致 → 取置信度更高的，标注 uncertain=True
    - 可选第三模型仲裁（disagree_provider）
    """

    def __init__(
        self,
        provider_a: LLMProvider,
        provider_b: LLMProvider,
        disagree_provider: Optional[LLMProvider] = None,
    ):
        self._a = provider_a
        self._b = provider_b
        self._disagree = disagree_provider

    def classify(self, error_info: dict) -> str:
        result = self.classify_full(error_info)
        return result.category

    def classify_full(self, error_info: dict) -> JudgmentResult:
        ra = self._a.classify_full(error_info) if hasattr(self._a, "classify_full") else \
            JudgmentResult(category=self._a.classify(error_info), confidence=0.7, provider="a")
        rb = self._b.classify_full(error_info) if hasattr(self._b, "classify_full") else \
            JudgmentResult(category=self._b.classify(error_info), confidence=0.7, provider="b")

        if ra.category == rb.category:
            # 一致：采信，置信度加成
            conf = min((ra.confidence + rb.confidence) / 2 + 0.08, 1.0)
            return JudgmentResult(
                category=ra.category, confidence=conf,
                reasoning=f"双模型一致 [{ra.provider}={ra.category}, {rb.provider}={rb.category}]",
                provider="dual_agree",
            )
        else:
            # 不一致
            if self._disagree:
                rc = self._disagree.classify_full(error_info) if hasattr(self._disagree, "classify_full") else \
                    JudgmentResult(category=self._disagree.classify(error_info), confidence=0.6, provider="arbiter")
                # 仲裁结果与谁一致就采信谁
                if rc.category == ra.category:
                    return JudgmentResult(
                        category=ra.category, confidence=ra.confidence * 0.9,
                        reasoning=f"仲裁采信 A({ra.provider})", provider="dual_arbiter",
                    )
                elif rc.category == rb.category:
                    return JudgmentResult(
                        category=rb.category, confidence=rb.confidence * 0.9,
                        reasoning=f"仲裁采信 B({rb.provider})", provider="dual_arbiter",
                    )
                else:
                    return JudgmentResult(
                        category=rc.category, confidence=rc.confidence * 0.7,
                        reasoning=f"仲裁独立判定({rc.provider})", provider="dual_arbiter",
                    )
            # 无仲裁：取置信度更高的
            winner = ra if ra.confidence >= rb.confidence else rb
            return JudgmentResult(
                category=winner.category, confidence=winner.confidence * 0.8,
                reasoning=f"双模型不一致，取高置信度 [{ra.provider}={ra.category}@{ra.confidence:.2f}, "
                          f"{rb.provider}={rb.category}@{rb.confidence:.2f}]",
                provider="dual_disagree",
            )


# ── 工厂函数 ──

# 全局裁决日志和缓存（进程级单例）
_global_judgment_log: Optional[JudgmentLog] = None
_global_judgment_cache: Optional[JudgmentCache] = None


def get_judgment_log() -> Optional[JudgmentLog]:
    return _global_judgment_log


def get_judgment_cache() -> Optional[JudgmentCache]:
    return _global_judgment_cache


def create_llm_judge(config: Optional[dict] = None) -> Optional[callable]:
    """
    根据配置创建 LLM 裁决函数。

    返回的函数签名为 (error_info: dict) -> JudgmentResult，
    JudgmentResult 可直接与字符串比较（向后兼容）。

    Args:
        config: LLM 配置 dict，支持字段:
            - provider: "mock" | "openai" | "dashscope" | "qwen"
            - api_key / base_url / model / timeout / temperature
            - cache_ttl_seconds: 缓存 TTL（默认 300s）
            - judgment_log_path: 裁决日志持久化路径
            - dual_model: 是否启用双模型对抗（默认 False）

    Returns:
        可调用的裁决函数 (error_info: dict) -> JudgmentResult，或 None
    """
    global _global_judgment_log, _global_judgment_cache

    if config is None:
        config = {}

    provider_name = config.get("provider", "mock")
    enabled = config.get("enabled", True)

    if not enabled:
        return None

    # 初始化裁决日志
    log_path = config.get("judgment_log_path", "")
    _global_judgment_log = JudgmentLog(persist_path=log_path)

    # 初始化缓存
    cache_ttl = config.get("cache_ttl_seconds", 300)
    _global_judgment_cache = JudgmentCache(ttl_seconds=cache_ttl)

    # 环境变量覆盖
    api_key = config.get("api_key") or os.environ.get("LLM_JUDGE_API_KEY", "")
    base_url = config.get("base_url") or os.environ.get("LLM_JUDGE_BASE_URL", "")
    model = config.get("model") or os.environ.get("LLM_JUDGE_MODEL", "")

    if provider_name == "mock":
        provider: LLMProvider = MockLLMProvider()
    elif provider_name in ("openai", "dashscope", "qwen"):
        if not api_key:
            print("[llm_judge] 未配置 api_key，降级为 mock provider", flush=True)
            provider = MockLLMProvider()
        else:
            provider = OpenAICompatibleProvider(
                api_key=api_key,
                base_url=base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1",
                model=model or "qwen-plus",
                timeout=config.get("timeout", 10),
                temperature=config.get("temperature", 0.0),
            )
    else:
        print(f"[llm_judge] 未知 provider '{provider_name}'，降级为 mock", flush=True)
        provider = MockLLMProvider()

    # 双模型对抗模式
    if config.get("dual_model") and isinstance(config.get("dual_model"), dict):
        dual_cfg = config["dual_model"]
        provider_b = OpenAICompatibleProvider(
            api_key=dual_cfg.get("api_key", api_key),
            base_url=dual_cfg.get("base_url", base_url),
            model=dual_cfg.get("model", "qwen-turbo"),
            timeout=dual_cfg.get("timeout", 10),
        )
        judge = DualLLMJudge(provider_a=provider, provider_b=provider_b)
    else:
        judge = None

    def judge_fn(error_info: dict) -> JudgmentResult:
        """LLM 裁决函数：接收错误信息，返回 JudgmentResult"""
        msg = error_info.get("message", "")
        error_hash = _hash_error(msg)

        # 1. 缓存命中
        if _global_judgment_cache:
            cached = _global_judgment_cache.get(error_hash)
            if cached:
                return cached

        # 2. 执行裁决
        if judge:
            result = judge.classify_full(error_info)
        elif hasattr(provider, "classify_full"):
            result = provider.classify_full(error_info)
        else:
            result = JudgmentResult(
                category=provider.classify(error_info),
                confidence=0.7, provider=provider_name,
            )

        # 3. 写入缓存
        if _global_judgment_cache and result.category != "unknown":
            _global_judgment_cache.put(error_hash, result)

        # 4. 写入日志
        if _global_judgment_log:
            _global_judgment_log.record(error_info, result)

        return result

    # 附加元数据
    judge_fn._provider = provider
    judge_fn._provider_name = provider_name
    judge_fn._judge = judge  # DualLLMJudge 实例（如有）
    return judge_fn


def load_llm_config_from_yaml(base_dir: str) -> Optional[dict]:
    """
    从 self_healing_rules.yaml 读取 LLM 配置。

    Args:
        base_dir: web-automation 根目录

    Returns:
        LLM 配置 dict，或 None（未配置时）
    """
    yaml_path = os.path.join(base_dir, "harness", "self_healing_rules.yaml")
    if not os.path.isfile(yaml_path):
        return None

    try:
        import yaml
        with open(yaml_path, "r", encoding="utf-8") as f:
            rules = yaml.safe_load(f) or {}
    except ImportError:
        # yaml 不可用，尝试简易解析
        rules = _simple_yaml_parse(yaml_path)
    except Exception:
        return None

    # 提取 dual_factor.llm_layer 配置
    dual_factor = rules.get("dual_factor", {})
    llm_layer = dual_factor.get("llm_layer", {})

    if not llm_layer.get("enabled", False):
        return None

    # 合并 llm_provider 配置
    llm_provider = rules.get("llm_provider", {})
    config = {
        "enabled": True,
        "provider": llm_provider.get("provider", "mock"),
        "api_key": llm_provider.get("api_key", ""),
        "base_url": llm_provider.get("base_url", ""),
        "model": llm_provider.get("model", ""),
        "timeout": llm_provider.get("timeout", 10),
        "cache_ttl_seconds": llm_layer.get("cache_ttl_seconds", 300),
        "confidence_threshold": llm_layer.get("confidence_threshold", 0.5),
    }
    return config


def _simple_yaml_parse(path: str) -> dict:
    """简易 YAML 解析（仅处理 key: value 和缩进层级）"""
    result = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if ":" in stripped:
                    key, _, val = stripped.partition(":")
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if val:
                        # 尝试类型转换
                        if val.lower() == "true":
                            val = True
                        elif val.lower() == "false":
                            val = False
                        elif val.isdigit():
                            val = int(val)
                        result[key] = val
    except Exception:
        pass
    return result
