"""
badcase_collector.py — BadCase 自动采集与分类 (Gap 2.3)

闭环机制子系统。职责：
- 从执行结果中自动提取失败模式
- 基于错误消息关键词的启发式根因分类
- 写入 patterns/ 目录，去重合并

使用方式：
    from core.badcase_collector import BadCaseCollector
    collector = BadCaseCollector()
    badcases = collector.collect(output, evidence)
    collector.save_to_patterns(badcases, patterns_dir="patterns/")
"""

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import  Dict, List

# ── 根因分类规则 ──

_ENV_FAILURE_PATTERNS = [
    r"TimeoutError", r"asyncio\.TimeoutError", r"ECONNREFUSED",
    r"ECONNRESET", r"ENOTFOUND", r"ETIMEDOUT",
    r"网络", r"超时", r"timeout", r"connection refused",
    r"DNS", r"SSL", r"certificate",
]

_SCRIPT_ISSUE_PATTERNS = [
    r"find error", r"querySelector", r"offsetParent",
    r"找不到", r"未找到", r"selector",
    r"element.*not found", r"no such element",
    r"stale element", r"invalid selector",
]

_DATA_INVALID_PATTERNS = [
    r"data.*invalid", r"数据.*无效", r"参数.*错误",
    r"required.*missing", r"必填", r"格式错误",
    r"validation.*fail", r"schema.*error",
]

@dataclass
class BadCase:
    """失败模式"""
    id: str
    title: str
    error_pattern: str  # 错误消息前 80 字符
    step_type: str
    error_message: str
    root_cause_category: str  # real_bug / script_issue / data_invalid / env_failure / unknown
    severity: str  # P0 / P1 / P2
    evidence_refs: List[str] = field(default_factory=list)
    created_at: str = ""
    hit_count: int = 1

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "error_pattern": self.error_pattern,
            "step_type": self.step_type,
            "error_message": self.error_message,
            "root_cause_category": self.root_cause_category,
            "severity": self.severity,
            "evidence_refs": self.evidence_refs,
            "created_at": self.created_at,
            "hit_count": self.hit_count,
        }

class BadCaseCollector:
    """
    从执行结果中自动采集 BadCase 并分类。
    """

    def collect(self, output: dict, evidence) -> List[BadCase]:
        """
        从 output + evidence 中提取失败模式。

        Args:
            output: impl.py 的 output dict
            evidence: EvidenceStore 实例

        Returns:
            BadCase 列表
        """
        badcases = []
        steps = output.get("steps", [])
        run_id = output.get("artifacts", {}).get("runId", "unknown")
        evidence_steps = evidence.get_steps() if hasattr(evidence, "get_steps") else []

        # 建立 evidence_steps 索引
        evidence_map = {}
        for es in evidence_steps:
            sid = es.get("step_id", "")
            if sid:
                evidence_map[sid] = es

        for step in steps:
            if step.get("status") not in ("error", "fail"):
                continue

            step_id = f"step{step.get('index', '?')}"
            step_type = step.get("type", "unknown")
            error_msg = step.get("error", "")
            step_desc = step.get("description", "")

            # 获取对应 evidence
            ev_entry = evidence_map.get(step.get("id", step_id), {})

            # 分类
            category = self._classify_error(step, ev_entry)

            # 严重级别
            severity = self._assess_severity(category, step_type)

            # 生成 ID
            error_key = error_msg[:40].replace(" ", "_").replace("/", "_")
            case_id = f"bc_{run_id}_{step_type}_{error_key}"

            badcases.append(BadCase(
                id=case_id,
                title=f"{step_type}: {error_msg[:60]}",
                error_pattern=error_msg[:80],
                step_type=step_type,
                error_message=error_msg,
                root_cause_category=category,
                severity=severity,
                evidence_refs=[step_id],
                created_at=datetime.now(timezone.utc).isoformat(),
            ))

        return badcases

    def _classify_error(self, step_result: dict, evidence_entry: dict) -> str:
        """
        基于错误消息关键词的启发式分类。

        Returns:
            "real_bug" / "script_issue" / "data_invalid" / "env_failure" / "unknown"
        """
        error_msg = step_result.get("error", "")
        status = step_result.get("status", "")
        step_type = step_result.get("type", "")

        # 1. 环境问题
        for pat in _ENV_FAILURE_PATTERNS:
            if re.search(pat, error_msg, re.I):
                return "env_failure"

        # 2. 脚本问题（selector 失效）
        for pat in _SCRIPT_ISSUE_PATTERNS:
            if re.search(pat, error_msg, re.I):
                return "script_issue"

        # 3. 数据问题
        for pat in _DATA_INVALID_PATTERNS:
            if re.search(pat, error_msg, re.I):
                return "data_invalid"

        # 4. assert 失败 = 可能是真 Bug
        if step_type == "assert" and status == "fail":
            return "real_bug"

        return "unknown"

    def _assess_severity(self, category: str, step_type: str) -> str:
        """根据分类评估严重级别"""
        if category == "real_bug":
            return "P1"
        if category == "script_issue":
            return "P1"
        if category == "env_failure":
            return "P2"
        if category == "data_invalid":
            return "P2"
        return "P2"

    def save_to_patterns(self, badcases: List[BadCase], patterns_dir: str = ""):
        """
        将 BadCase 写入 patterns/ 目录，去重合并。

        Args:
            badcases: BadCase 列表
            patterns_dir: patterns 目录路径
        """
        if not patterns_dir:
            patterns_dir = os.path.join(os.path.dirname(__file__), "..", "patterns")
        os.makedirs(patterns_dir, exist_ok=True)

        # 加载已有 patterns 用于去重
        existing = self._load_existing_patterns(patterns_dir)

        for bc in badcases:
            # 去重：相同 error_pattern 的合并 hit_count
            matched = False
            for eid, data in existing.items():
                if self._is_similar(data.get("error_pattern", ""), bc.error_pattern):
                    data["hit_count"] = data.get("hit_count", 0) + 1
                    data["last_seen"] = bc.created_at
                    # 回写文件
                    fpath = os.path.join(patterns_dir, f"{eid}.json")
                    with open(fpath, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    matched = True
                    break

            if not matched:
                # 新 pattern
                fpath = os.path.join(patterns_dir, f"{bc.id}.json")
                with open(fpath, "w", encoding="utf-8") as f:
                    json.dump(bc.to_dict(), f, ensure_ascii=False, indent=2)

    def _load_existing_patterns(self, patterns_dir: str) -> Dict[str, dict]:
        """加载已有 patterns"""
        result = {}
        if not os.path.isdir(patterns_dir):
            return result
        for fname in os.listdir(patterns_dir):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(patterns_dir, fname)
            try:
                with open(fpath, encoding="utf-8") as f:
                    data = json.load(f)
                eid = fname.replace(".json", "")
                result[eid] = data
            except (json.JSONDecodeError, IOError):
                continue
        return result

    @staticmethod
    def _is_similar(a: str, b: str) -> bool:
        """判断两个 error_pattern 是否相似（前 40 字符匹配）"""
        return a[:40].strip() == b[:40].strip() if a and b else False
