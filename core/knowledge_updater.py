"""
knowledge_updater.py — Knowledge 自动更新组件

在每次执行的 FINALIZE 阶段被 impl.py 调用，把执行结果反哺回 knowledge 文件：

1. lastVerified 更新  — 执行全部通过时，更新对应 knowledge 的验证时间
2. 坑点沉淀          — 步骤失败且原因可识别时，追加到 knownIssues（去重）
3. staleFields 标记  — selector 找不到元素时，标记该字段为 stale
4. CHANGELOG 追加    — 有变更时写一行到 history/CHANGELOG.md

调用方式（在 impl.py FINALIZE 段）：
    from core.knowledge_updater import KnowledgeUpdater
    updater = KnowledgeUpdater(page_url=ctx_url)
    updater.apply(output=output, input_data=input_data)
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# SKILLS_DIR: 相对于本文件（core/knowledge_updater.py）向上两级即为 web-automation/，再上一级为 skills/
# 支持通过环境变量 WEB_AUTO_SKILLS_DIR 覆盖（移植到非标准路径时使用）
_THIS_DIR  = Path(__file__).parent          # core/
_SKILL_DIR = _THIS_DIR.parent               # web-automation/
SKILLS_DIR = Path(os.environ.get("WEB_AUTO_SKILLS_DIR", str(_SKILL_DIR.parent)))
INDEX_PATH  = _SKILL_DIR / "knowledge/index.json"
CHANGELOG   = _SKILL_DIR / "history/CHANGELOG.md"

# 只在这些条件下写 knownIssues，避免偶发错误污染 knowledge
_IGNORABLE_ERRORS = {
    "TimeoutError",
    "asyncio.TimeoutError",
    "NavigationError",
}

# 已知的、不需要重复记录的通用错误模式
_GENERIC_PATTERNS = [
    r"等待接口超时",
    r"networkidle",
    r"connect ECONNREFUSED",
]


class KnowledgeUpdater:
    """
    根据执行结果更新对应页面的 knowledge 文件。
    一次执行实例化一次，调用 apply() 完成全部更新。
    """

    def __init__(self, page_url: str = ""):
        self.page_url = page_url
        self._index = self._load_index()
        self._entry = self._match_entry(page_url)
        self._knowledge_path: Optional[Path] = None
        self._knowledge: Optional[dict] = None
        self._changed = False

        if self._entry:
            rel = self._entry.get("file", "")
            self._knowledge_path = SKILLS_DIR / rel if rel else None
            if self._knowledge_path and self._knowledge_path.exists():
                with open(self._knowledge_path, encoding="utf-8") as f:
                    self._knowledge = json.load(f)

    # ── 主入口 ──

    def apply(self, output: dict, input_data: dict) -> dict:
        """
        分析 output，更新 knowledge。
        返回本次变更摘要 dict（无论是否有变更）。
        """
        summary = {
            "knowledgeId": self._entry["id"] if self._entry else None,
            "knowledgePath": str(self._knowledge_path) if self._knowledge_path else None,
            "changes": [],
            "skipped": not bool(self._entry and self._knowledge),
        }

        if summary["skipped"]:
            reason = "未匹配到 knowledge 条目" if not self._entry else "knowledge 文件不存在"
            summary["skipReason"] = reason
            return summary

        status   = output.get("status", "error")
        steps    = output.get("steps", [])
        run_id   = output.get("artifacts", {}).get("runId", "unknown")
        today    = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # 1. lastVerified
        if status == "pass":
            change = self._update_last_verified(today, run_id)
            if change:
                summary["changes"].append(change)

        # 2. 坑点沉淀 + staleFields
        for step in steps:
            if step.get("status") in ("error", "fail"):
                err_msg = step.get("error", "")

                # stale 检测
                stale_change = self._detect_stale(step, input_data)
                if stale_change:
                    summary["changes"].append(stale_change)

                # 坑点沉淀（过滤通用/偶发错误）
                if self._should_record_issue(err_msg):
                    issue_change = self._append_known_issue(
                        issue=err_msg,
                        stepDesc=step.get("description", ""),
                        stepType=step.get("type", ""),
                        today=today,
                        run_id=run_id,
                    )
                    if issue_change:
                        summary["changes"].append(issue_change)

        # 3. 写回文件 + CHANGELOG
        if self._changed:
            self._save_knowledge()
            for change in summary["changes"]:
                self._append_changelog(change, run_id, today)

        return summary

    # ── lastVerified ──

    def _update_last_verified(self, today: str, run_id: str) -> Optional[dict]:
        meta = self._knowledge.setdefault("_meta", {})
        if meta.get("lastVerified") == today:
            return None  # 今天已更新，跳过
        meta["lastVerified"] = today
        meta["verifiedByRun"] = run_id
        # draft → verified
        if meta.get("initStatus") == "draft":
            meta["initStatus"] = "verified"
        self._changed = True
        return {
            "type": "lastVerified",
            "value": today,
            "runId": run_id,
            "msg": f"lastVerified 更新为 {today}",
        }

    # ── staleFields ──

    def _detect_stale(self, step: dict, input_data: dict) -> Optional[dict]:
        """
        判断步骤失败是否因为 selector 找不到元素，
        如果是，把对应字段标记为 stale。
        """
        err = step.get("error", "")
        # 检测 selector 失效特征
        stale_signals = [
            "find error",
            "找不到",
            "未找到",
            "querySelector",
            "offsetParent",
        ]
        if not any(sig in err for sig in stale_signals):
            return None

        # 找到关联的 selector
        step_selector = (
            step.get("selector")
            or _extract_selector_from_error(err)
        )
        if not step_selector:
            return None

        meta = self._knowledge.setdefault("_meta", {})
        stale = meta.setdefault("staleFields", [])
        if step_selector not in stale:
            stale.append(step_selector)
            self._changed = True
            return {
                "type": "staleField",
                "selector": step_selector,
                "stepDesc": step.get("description", ""),
                "msg": f"selector 疑似失效（找不到元素）: {step_selector}",
            }
        return None

    # ── knownIssues ──

    def _append_known_issue(
        self, issue: str, stepDesc: str, stepType: str, today: str, run_id: str
    ) -> Optional[dict]:
        """
        追加坑点到 knownIssues[]，已存在的不重复写。
        """
        issues = self._knowledge.setdefault("knownIssues", [])

        # 结构化坑点（list of dict）和字符串坑点兼容
        existing_texts = set()
        for item in issues:
            if isinstance(item, dict):
                existing_texts.add(item.get("issue", ""))
            elif isinstance(item, str):
                existing_texts.add(item)

        # 去重：相似的错误消息不重复记录（截取前80字符比对）
        issue_key = issue[:80]
        if any(issue_key in t for t in existing_texts):
            return None

        new_issue = {
            "issue": issue,
            "stepDesc": stepDesc,
            "stepType": stepType,
            "discoveredAt": today,
            "runId": run_id,
            "status": "active",
            "root_cause_category": self._classify_root_cause(issue),
        }
        issues.append(new_issue)
        self._changed = True
        return {
            "type": "knownIssue",
            "issue": issue[:60] + ("..." if len(issue) > 60 else ""),
            "msg": f"新坑点已沉淀: {issue[:60]}",
        }

    # ── 文件写入 ──

    def _save_knowledge(self):
        if not self._knowledge_path:
            return
        self._knowledge_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._knowledge_path, "w", encoding="utf-8") as f:
            json.dump(self._knowledge, f, ensure_ascii=False, indent=2)

    def _append_changelog(self, change: dict, run_id: str, today: str):
        if not CHANGELOG.exists():
            return
        line = (
            f"\n- [{today}] [{run_id}] "
            f"[{change['type']}] {change['msg']}"
        )
        with open(CHANGELOG, "a", encoding="utf-8") as f:
            f.write(line)

    # ── 工具 ──

    def _should_record_issue(self, err_msg: str) -> bool:
        """过滤不值得记录的偶发/通用错误"""
        if not err_msg:
            return False
        # 偶发性错误类型
        for ig in _IGNORABLE_ERRORS:
            if ig in err_msg:
                return False
        # 通用模式
        for pat in _GENERIC_PATTERNS:
            if re.search(pat, err_msg):
                return False
        return True

    @staticmethod
    def _load_index() -> dict:
        if INDEX_PATH.exists():
            with open(INDEX_PATH, encoding="utf-8") as f:
                return json.load(f)
        return {"entries": []}

    @staticmethod
    def _classify_root_cause(error_msg: str) -> str:
        """基于错误消息的启发式根因分类"""
        env_pats = ["TimeoutError", "ECONNREFUSED", "ECONNRESET", "timeout", "connection"]
        script_pats = ["find error", "querySelector", "offsetParent", "selector"]
        data_pats = ["required", "validation", "schema", "format"]
        for p in env_pats:
            if p.lower() in error_msg.lower():
                return "env_failure"
        for p in script_pats:
            if p.lower() in error_msg.lower():
                return "script_issue"
        for p in data_pats:
            if p.lower() in error_msg.lower():
                return "data_invalid"
        return "unknown"

    @staticmethod
    def _match_entry(url: str) -> Optional[dict]:
        """根据 URL 匹配 index 中的 entry（host + route 都要包含）"""
        if not url:
            return None
        index = KnowledgeUpdater._load_index()
        for entry in index.get("entries", []):
            host  = entry.get("host", "")
            route = entry.get("route", "")
            if host and route and host in url and route in url:
                return entry
        return None


# ── 工具函数 ──

def _extract_selector_from_error(err: str) -> Optional[str]:
    """从错误消息中提取 selector 字符串"""
    # 匹配 selector='xxx' 或 querySelector('xxx') 等
    patterns = [
        r"selector='([^']+)'",
        r'selector="([^"]+)"',
        r"querySelector\('([^']+)'\)",
        r'querySelector\("([^"]+)"\)',
    ]
    for pat in patterns:
        m = re.search(pat, err)
        if m:
            return m.group(1)
    return None
