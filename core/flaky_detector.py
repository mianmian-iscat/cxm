"""
flaky_detector.py — 不稳定用例（Flaky Test）识别器

对标：Cypress Cloud Flake Detection 2025 (auto flag + track + quarantine),
     BrowserStack Percy (false-positive filtering),
     Google 内部 flakiness scoring (1.5% of tests are flaky)。

解决的问题：
- 同一用例跑 N 次结果不一致（时而 pass 时而 fail），但人工难以识别
- 失败堆栈、耗时、网络请求每次都不同 → 大概率 flaky 而非真 bug
- 主流工具都已内置 flaky quarantine，我们缺这一环

核心能力：
  1. 每次 run 后追加一条历史记录到 flaky-history.jsonl
  2. 滑窗内统计 pass/fail 混合情况，识别 flaky 用例
  3. 对比失败堆栈相似度（低相似度 = 非稳定 bug）
  4. 对比耗时方差（高方差 = 环境敏感型 flaky）
  5. 输出报告：flaky_score + 建议（quarantine / investigate / ignore）

使用方式：
    from core.flaky_detector import FlakyDetector

    fd = FlakyDetector()
    fd.record(case_id="f88-tc01", status="pass", duration_ms=1200,
              error_signature="")
    fd.record(case_id="f88-tc01", status="fail", duration_ms=8000,
              error_signature="TimeoutError: selector not found")
    report = fd.detect("f88-tc01", window=10)
    print(report.is_flaky, report.flaky_score, report.recommendation)
"""

import hashlib
import json
import math
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


def _default_history_dir() -> str:
    skill_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(skill_root, "artifacts", "flaky-history")


@dataclass
class FlakyReport:
    """单个用例的 flaky 诊断报告"""
    case_id: str
    is_flaky: bool
    flaky_score: float            # 0.0~1.0, 越高越 flaky
    sample_size: int
    pass_count: int
    fail_count: int
    pass_rate: float
    duration_stddev_ms: float     # 耗时标准差
    error_signature_diversity: int  # 失败堆栈去重后的数量
    recommendation: str           # quarantine | investigate | stable | no_data
    unique_error_signatures: List[str] = field(default_factory=list)
    window_days: int = 30
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "is_flaky": self.is_flaky,
            "flaky_score": round(self.flaky_score, 4),
            "sample_size": self.sample_size,
            "pass_count": self.pass_count,
            "fail_count": self.fail_count,
            "pass_rate": round(self.pass_rate, 4),
            "duration_stddev_ms": round(self.duration_stddev_ms, 1),
            "error_signature_diversity": self.error_signature_diversity,
            "recommendation": self.recommendation,
            "unique_error_signatures": self.unique_error_signatures,
            "window_days": self.window_days,
            "timestamp": self.timestamp,
        }


class FlakyDetector:
    """
    不稳定用例识别器。

    存储：
    {artifacts}/flaky-history/history.jsonl — append-only
    {artifacts}/flaky-history/latest_flaky_report.json — 最近一次扫描结果

    设计原则：
    - record 只追一条记录，零负担
    - detect 按需计算，支持按时间窗口过滤
    - score 综合 3 个信号：混合度 + 失败堆栈多样性 + 耗时方差
    """

    def __init__(self, history_dir: Optional[str] = None):
        self.history_dir = history_dir or _default_history_dir()
        self.history_file = os.path.join(self.history_dir, "history.jsonl")
        self.report_file = os.path.join(self.history_dir, "latest_flaky_report.json")
        os.makedirs(self.history_dir, exist_ok=True)

    # ── 错误签名（去噪）──

    @staticmethod
    def _normalize_error(raw: str) -> str:
        """把错误字符串去噪成 signature（去掉动态 token / 时间戳 / 路径）"""
        if not raw:
            return ""
        s = raw
        # 去掉时间戳
        s = re.sub(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[^ ]*", "<TS>", s)
        # 去掉 URL
        s = re.sub(r"https?://[^\s\"']+", "<URL>", s)
        # 去掉 hex / UUID / 长数字
        s = re.sub(r"\b[0-9a-f]{8,}\b", "<HEX>", s, flags=re.IGNORECASE)
        s = re.sub(r"\b\d{6,}\b", "<NUM>", s)
        # 去掉行号
        s = re.sub(r":\d+:\d+", ":<L>:<C>", s)
        return s.strip()[:200]

    @staticmethod
    def _signature_hash(sig: str) -> str:
        if not sig:
            return ""
        return hashlib.md5(sig.encode("utf-8")).hexdigest()[:8]

    # ── record ──

    def record(
        self,
        case_id: str,
        status: str,
        duration_ms: int = 0,
        error_signature: str = "",
        run_id: str = "",
        business_type: str = "unknown",
    ) -> dict:
        """追加一条历史记录"""
        sig = self._normalize_error(error_signature)
        rec = {
            "case_id": case_id,
            "status": status,
            "duration_ms": int(duration_ms),
            "error_signature": sig,
            "error_hash": self._signature_hash(sig),
            "run_id": run_id,
            "business_type": business_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            with open(self.history_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError as e:
            print(f"[flaky] 写入失败: {e}", file=sys.stderr)
        return rec

    # ── read ──

    def _read_history(
        self,
        case_id: Optional[str] = None,
        days: int = 30,
        limit: Optional[int] = None,
    ) -> List[dict]:
        if not os.path.exists(self.history_file):
            return []
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        out = []
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if rec.get("timestamp", "") < cutoff:
                        continue
                    if case_id and rec.get("case_id") != case_id:
                        continue
                    out.append(rec)
                    if limit and len(out) >= limit:
                        break
        except OSError as e:
            print(f"[flaky] 读取失败: {e}", file=sys.stderr)
        return out

    # ── detect 单条 ──

    def detect(self, case_id: str, window: int = 30, min_samples: int = 3) -> FlakyReport:
        """识别单个用例的 flaky 程度"""
        records = self._read_history(case_id=case_id, days=window)
        now = datetime.now(timezone.utc).isoformat()

        if len(records) < min_samples:
            return FlakyReport(
                case_id=case_id, is_flaky=False, flaky_score=0.0,
                sample_size=len(records), pass_count=0, fail_count=0,
                pass_rate=0.0, duration_stddev_ms=0.0,
                error_signature_diversity=0, recommendation="no_data",
                window_days=window, timestamp=now,
            )

        pass_count = sum(1 for r in records if r.get("status") == "pass")
        fail_count = len(records) - pass_count
        pass_rate = pass_count / len(records)

        # 信号 1：混合度（pass/fail 各占 50% 时最高）
        if len(records) == 0:
            mix = 0.0
        else:
            p = pass_rate
            mix = 1.0 - abs(2 * p - 1)  # p=0.5 时 mix=1; p=0 或 1 时 mix=0

        # 信号 2：失败堆栈多样性（多种不同 error_hash 视为 flaky 信号）
        error_hashes = set()
        for r in records:
            h = r.get("error_hash")
            if h:
                error_hashes.add(h)
        unique_errs = len(error_hashes)
        err_diversity = min(1.0, unique_errs / 3.0) if fail_count > 0 else 0.0

        # 信号 3：耗时方差（用标准差 / 均值，即变异系数）
        durations = [r.get("duration_ms", 0) for r in records if r.get("duration_ms", 0) > 0]
        if len(durations) >= 2:
            mean_d = sum(durations) / len(durations)
            var_d = sum((d - mean_d) ** 2 for d in durations) / len(durations)
            std_d = math.sqrt(var_d)
            cv = std_d / mean_d if mean_d > 0 else 0.0
            dur_signal = min(1.0, cv)  # cv=1 时信号=1
        else:
            std_d = 0.0
            dur_signal = 0.0

        # 综合 flaky_score：0.5 * 混合度 + 0.3 * 堆栈多样性 + 0.2 * 耗时方差
        score = 0.5 * mix + 0.3 * err_diversity + 0.2 * dur_signal

        # 推荐
        if score < 0.15:
            rec = "stable"
        elif score < 0.4:
            rec = "investigate"
        else:
            rec = "quarantine"

        unique_sigs = sorted(error_hashes)
        return FlakyReport(
            case_id=case_id,
            is_flaky=score >= 0.3,
            flaky_score=score,
            sample_size=len(records),
            pass_count=pass_count,
            fail_count=fail_count,
            pass_rate=pass_rate,
            duration_stddev_ms=std_d,
            error_signature_diversity=unique_errs,
            recommendation=rec,
            unique_error_signatures=unique_sigs,
            window_days=window,
            timestamp=now,
        )

    # ── scan_all ──

    def scan_all(self, window: int = 30) -> List[FlakyReport]:
        """扫描所有用例，返回按 flaky_score 倒序的报告列表"""
        records = self._read_history(days=window)
        case_ids = sorted({r.get("case_id") for r in records if r.get("case_id")})
        reports = [self.detect(cid, window=window) for cid in case_ids]
        reports.sort(key=lambda r: -r.flaky_score)
        # 落盘
        try:
            with open(self.report_file, "w", encoding="utf-8") as f:
                json.dump([r.to_dict() for r in reports], f, ensure_ascii=False, indent=2)
        except OSError:
            pass
        return reports
