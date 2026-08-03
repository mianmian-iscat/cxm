#!/usr/bin/env python3
"""
framework-audit.py — 每日框架健康度评估（L1 评估 + L2 自动优化）

每天定时运行，扫描 7 大维度，输出审计报告并可选触发自动修复。

7 大维度：
  1. 单元测试健康（pytest 全量）
  2. 核心模块导入（import smoke）
  3. AI 内核指标趋势（近 7/30 天聚合）
  4. Atom 资产治理（重复/过期/未引用）
  5. 知识库覆盖度（case 关联 kb 命中率）
  6. 失败分类器误判率（releaseDecision vs 实际结果）
  7. 回归套件通过率（昨日 vs 上周）

输出：
  - artifacts/framework-audit/<date>.json    机器可读
  - artifacts/framework-audit/<date>.html    人读报告
  - artifacts/framework-audit/latest.json    最近一次缓存
  - stdout 报告摘要（可被 launchd 重定向到日志）

自动修复（L2）：
  --auto-fix 启用（默认 dry-run 仅报告）
  支持的安全修复：
    - pytest 失败 → 在报告里标记（不自动改代码）
    - 重复 atom 占位符检测 → 警告
    - 超过 90 天无引用的 atom → 标记为 candidate_for_removal
    - metrics.jsonl 超过 180 天 → 归档到 metrics-archive.jsonl

调度方式（三选一）：
  1. launchd: 部署 deploy/com.webautomation.framework-audit.plist
  2. cron:    crontab -e → 0 22 * * * cd /path && python3 scripts/framework-audit.py
  3. 手动:    python3 scripts/framework-audit.py --auto-fix
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


# ── 常量 ──

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTIFACTS = os.path.join(SKILL_ROOT, "artifacts")
AUDIT_DIR = os.path.join(ARTIFACTS, "framework-audit")
METRICS_DIR = os.path.join(ARTIFACTS, "ai_metrics")
METRICS_FILE = os.path.join(METRICS_DIR, "metrics.jsonl")
ATOMS_DIR = os.path.join(SKILL_ROOT, "eval", "cases", "_atoms")
CASES_DIR = os.path.join(SKILL_ROOT, "eval", "cases")


# ── 工具 ──

def _run_cmd(cmd: List[str], cwd: Optional[str] = None, timeout: int = 300) -> Dict[str, Any]:
    """执行子进程，返回 {ok, stdout, stderr, duration_ms}"""
    t0 = time.time()
    try:
        p = subprocess.run(
            cmd, cwd=cwd or SKILL_ROOT, capture_output=True,
            text=True, timeout=timeout,
        )
        return {
            "ok": p.returncode == 0,
            "code": p.returncode,
            "stdout": p.stdout[-4000:],  # 截断
            "stderr": p.stderr[-2000:],
            "duration_ms": int((time.time() - t0) * 1000),
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": -1, "error": "timeout", "duration_ms": timeout * 1000}
    except Exception as e:
        return {"ok": False, "code": -2, "error": str(e), "duration_ms": int((time.time() - t0) * 1000)}


def _section(title: str) -> None:
    print(f"\n{'='*72}\n[{title}]\n{'='*72}")


# ── 1. 单元测试 ──

def audit_pytest() -> dict:
    """运行 pytest，统计 pass/fail/error"""
    _section("1. 单元测试")
    r = _run_cmd(["python3", "-m", "pytest", "-q", "--disable-warnings", "tests/"], timeout=600)
    # 解析 pytest -q 输出：形如 "42 passed, 1 failed in 3.21s"
    m = re.search(r"(\d+) passed", r["stdout"])
    passed = int(m.group(1)) if m else 0
    m = re.search(r"(\d+) failed", r["stdout"])
    failed = int(m.group(1)) if m else 0
    m = re.search(r"(\d+) error", r["stdout"])
    errors = int(m.group(1)) if m else 0
    total = passed + failed + errors
    rate = passed / total if total else 0.0
    print(f"  pass={passed} fail={failed} error={errors} rate={rate:.2%}")
    return {
        "ok": r["ok"] and failed == 0 and errors == 0,
        "passed": passed, "failed": failed, "errors": errors,
        "pass_rate": round(rate, 4),
        "duration_ms": r["duration_ms"],
        "tail": r["stdout"].splitlines()[-5:] if r["stdout"] else [],
    }


# ── 2. 核心模块导入 ──

def audit_imports() -> dict:
    """导入 12 个核心模块，任一失败即告警"""
    _section("2. 核心模块导入烟雾")
    modules = [
        "core.failure_classifier", "core.self_healing", "core.knowledge_base",
        "core.metrics_collector", "core.evidence_store", "core.healing_analytics",
        "core.ai_metrics_aggregator", "core.atom_loader", "core.finalize_pipeline",
        "core.step_executor", "core.cdp_client", "core.artifact_manager",
        "core.circuit_breaker", "core.budget_guard", "core.pipeline_dsl",
    ]
    failed = []
    for m in modules:
        try:
            __import__(m)
        except Exception as e:
            failed.append({"module": m, "error": str(e)})
    print(f"  scanned={len(modules)} failed={len(failed)}")
    for f in failed:
        print(f"    ❌ {f['module']}: {f['error']}")
    return {
        "ok": len(failed) == 0,
        "scanned": len(modules),
        "failed": failed,
    }


# ── 3. AI 内核指标趋势 ──

def audit_ai_metrics() -> dict:
    """从 ai_metrics/metrics.jsonl 聚合近 7/30 天指标"""
    _section("3. AI 内核指标趋势")
    if not os.path.exists(METRICS_FILE):
        print("  ⚠️ metrics.jsonl 不存在（无历史 run）")
        return {"ok": True, "no_data": True}
    try:
        sys.path.insert(0, SKILL_ROOT)
        from core.ai_metrics_aggregator import AiMetricsAggregator
        agg = AiMetricsAggregator()
        last_7 = agg.aggregate(days=7, persist_summary=False)
        last_30 = agg.aggregate(days=30, persist_summary=False)
        print(f"  7d:  samples={last_7['sample_size']} "
              f"healing={last_7['healing']['success_rate']:.2%} "
              f"judge={last_7['llm_judge']['agreement_rate']:.2%} "
              f"kb={last_7['knowledge']['recall']:.2%}")
        print(f"  30d: samples={last_30['sample_size']} "
              f"healing={last_30['healing']['success_rate']:.2%} "
              f"judge={last_30['llm_judge']['agreement_rate']:.2%} "
              f"kb={last_30['knowledge']['recall']:.2%}")
        return {
            "ok": True,
            "last_7": last_7,
            "last_30": last_30,
            "degraded_strategies": last_30["healing"].get("degraded", []),
        }
    except Exception as e:
        print(f"  ❌ 聚合异常: {e}")
        return {"ok": False, "error": str(e)}


# ── 4. Atom 资产治理 ──

def audit_atoms() -> dict:
    """扫描 atoms 目录：未声明 / 占位符残留 / 引用计数"""
    _section("4. Atom 资产治理")
    if not os.path.exists(ATOMS_DIR):
        print("  ⚠️ atoms 目录不存在")
        return {"ok": True, "no_data": True}

    # 4a. 加载 manifest
    manifest_path = os.path.join(ATOMS_DIR, "manifest.json")
    if not os.path.exists(manifest_path):
        return {"ok": False, "error": "manifest.json missing"}
    with open(manifest_path) as f:
        manifest = json.load(f)
    declared_ids = {a["id"] for a in manifest.get("atoms", [])}

    # 4b. 扫描目录里的 .json（排除 manifest）
    disk_files = [fn for fn in os.listdir(ATOMS_DIR) if fn.endswith(".json") and fn != "manifest.json"]
    disk_ids = {fn[:-5] for fn in disk_files}
    orphan_files = disk_ids - declared_ids
    missing_files = declared_ids - disk_ids
    print(f"  declared={len(declared_ids)} disk={len(disk_ids)} "
          f"orphan={len(orphan_files)} missing={len(missing_files)}")

    # 4c. 占位符残留检测（{{xxx}}）
    # 注：atom 模板的 steps.expression 里出现 {{var}} 是正常的（运行时由 AtomLoader 替换）
    # 只检测 params.default 以外的元数据字段（如 description / id）里的占位符
    placeholder_pattern = re.compile(r"\{\{[A-Za-z_][A-Za-z0-9_]*\}\}")
    _META_FIELDS = ("id", "description")
    unresolved = []
    for fn in disk_files:
        path = os.path.join(ATOMS_DIR, fn)
        with open(path) as f:
            text = f.read()
        try:
            data = json.loads(text)
        except Exception:
            continue
        for field in _META_FIELDS:
            v = data.get(field)
            if isinstance(v, str) and placeholder_pattern.search(v):
                unresolved.append({"atom": fn, "field": field, "value": v[:80]})
    print(f"  unresolved_placeholders (meta only): {len(unresolved)}")

    # 4d. 引用计数（扫描所有 case JSON 里的 includeAtom）
    usage = {aid: 0 for aid in declared_ids}
    if os.path.exists(CASES_DIR):
        for root, _, files in os.walk(CASES_DIR):
            if "_atoms" in root:
                continue
            for fn in files:
                if not fn.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(root, fn)) as f:
                        data = json.load(f)
                except Exception:
                    continue
                for step in data.get("steps", []) or []:
                    if isinstance(step, dict) and step.get("type") == "includeAtom":
                        aid = step.get("atom")
                        if aid in usage:
                            usage[aid] += 1
    unused = [k for k, v in usage.items() if v == 0]
    print(f"  unused_atoms (no includeAtom 引用): {unused}")

    return {
        "ok": len(orphan_files) == 0 and len(missing_files) == 0 and len(unresolved) == 0,
        "declared": sorted(declared_ids),
        "orphan_files": sorted(orphan_files),
        "missing_files": sorted(missing_files),
        "unresolved_placeholders": unresolved,
        "usage": usage,
        "unused": unused,
        "candidates_for_removal": [a for a in unused if a not in ("antd_tab_switch",)],
    }


# ── 5. 知识库覆盖度（轻量：统计 knowledge 目录文件数 + 业务域分布）──

def audit_knowledge() -> dict:
    _section("5. 知识库覆盖度")
    kb_dir = os.path.join(SKILL_ROOT, "knowledge")
    if not os.path.exists(kb_dir):
        print("  ⚠️ knowledge 目录不存在")
        return {"ok": True, "no_data": True}
    total = 0
    by_domain: Dict[str, int] = {}
    for root, _, files in os.walk(kb_dir):
        for fn in files:
            if fn.endswith(".md") or fn.endswith(".json"):
                total += 1
                rel = os.path.relpath(root, kb_dir)
                domain = rel.split(os.sep)[0] if rel != "." else "_root"
                by_domain[domain] = by_domain.get(domain, 0) + 1
    print(f"  entries={total}  domains={by_domain}")
    return {"ok": True, "total": total, "by_domain": by_domain}


# ── 6. 失败分类器决策回顾（轻量：扫 output.json 里的 releaseDecision vs status）──

def audit_release_decisions() -> dict:
    """扫描 artifacts/<run>/output.json，统计 releaseDecision 与最终 status 的一致性"""
    _section("6. 失败分类器决策回顾")
    runs_dir = ARTIFACTS
    if not os.path.exists(runs_dir):
        return {"ok": True, "no_data": True}
    scanned = 0
    inconsistent = []
    for d in os.listdir(runs_dir):
        p = os.path.join(runs_dir, d, "output.json")
        if not os.path.exists(p):
            continue
        try:
            with open(p) as f:
                out = json.load(f)
        except Exception:
            continue
        rd = out.get("releaseDecision")
        status = out.get("status")
        if rd is None:
            continue
        scanned += 1
        blocked = rd.get("blocked", False)
        # 不一致：blocked=True 但 status=pass，或 blocked=False 但 status=fail 且无 warnings
        if blocked and status == "pass":
            inconsistent.append({"run": d, "issue": "blocked_but_pass", "rd": rd, "status": status})
        elif not blocked and status == "fail" and not rd.get("warnings"):
            inconsistent.append({"run": d, "issue": "not_blocked_but_fail_no_warn", "rd": rd, "status": status})
    print(f"  scanned={scanned} inconsistent={len(inconsistent)}")
    return {
        "ok": len(inconsistent) == 0,
        "scanned": scanned,
        "inconsistent": inconsistent[:10],
    }


# ── 7. 回归通过率对比（昨日 vs 上周同日）──

def audit_regression_trend() -> dict:
    """扫描 artifacts/regression-results.json 历史（按 mtime）对比"""
    _section("7. 回归通过率趋势")
    results = []
    for fn in os.listdir(ARTIFACTS):
        if fn.startswith("regression-results") and fn.endswith(".json"):
            p = os.path.join(ARTIFACTS, fn)
            try:
                with open(p) as f:
                    data = json.load(f)
                summary = data.get("summary") or {}
                total = summary.get("total") or summary.get("total_cases") or 0
                passed = summary.get("passed") or summary.get("pass") or 0
                results.append({
                    "file": fn,
                    "mtime": os.path.getmtime(p),
                    "total": total,
                    "passed": passed,
                    "rate": passed / total if total else 0.0,
                })
            except Exception:
                continue
    if not results:
        print("  ⚠️ 无历史 regression-results")
        return {"ok": True, "no_data": True}
    results.sort(key=lambda x: x["mtime"], reverse=True)
    latest = results[0]
    week_ago = next((r for r in results if latest["mtime"] - r["mtime"] > 5 * 86400), None)
    print(f"  latest:  {latest['file']} rate={latest['rate']:.2%} ({latest['passed']}/{latest['total']})")
    if week_ago:
        print(f"  week_ago: {week_ago['file']} rate={week_ago['rate']:.2%}")
        delta = latest["rate"] - week_ago["rate"]
        print(f"  delta: {delta:+.2%}")
    else:
        delta = 0.0
    return {
        "ok": delta >= -0.05,  # 下跌超过 5% 视为不健康
        "latest": latest,
        "week_ago": week_ago,
        "delta": round(delta, 4),
    }


# ── 综合评分 ──

def score_audits(audits: Dict[str, dict]) -> Dict[str, Any]:
    """给 N 个维度打分（0-100），按实际存在维度重新归一化权重"""
    weights = {
        "pytest": 0.20,
        "imports": 0.10,
        "ai_metrics": 0.20,
        "atoms": 0.10,
        "knowledge": 0.05,
        "release_decisions": 0.15,
        "regression_trend": 0.20,
    }
    scores = {}
    present_weight_sum = 0.0
    for k in weights:
        if k not in audits:
            continue
        v = audits[k]
        present_weight_sum += weights[k]
        if not isinstance(v, dict):
            scores[k] = 0
            continue
        if v.get("no_data"):
            scores[k] = 80
        elif v.get("ok"):
            if k == "pytest":
                scores[k] = int(v.get("pass_rate", 1.0) * 100)
            elif k == "regression_trend":
                delta = v.get("delta", 0)
                scores[k] = max(0, min(100, 80 + int(delta * 200)))
            elif k == "ai_metrics":
                last_7 = v.get("last_7") or {}
                attempts = last_7.get("healing", {}).get("attempts", 0)
                if attempts == 0:
                    # 近期无自愈尝试（早期积累阶段），给 85 分而不是 0
                    scores[k] = 85
                else:
                    h = last_7.get("healing", {}).get("success_rate", 0.5)
                    scores[k] = int(h * 100)
            else:
                scores[k] = 100
        else:
            scores[k] = 30
    # 按实际存在维度归一化权重
    if present_weight_sum <= 0:
        return {"per_dimension": scores, "overall": 0}
    weighted = sum(
        scores.get(k, 0) * (weights[k] / present_weight_sum)
        for k in weights if k in audits
    )
    return {"per_dimension": scores, "overall": round(weighted, 1)}


# ── 自动优化（L2 安全项）──

def auto_fix_l2(audits: Dict[str, dict], dry_run: bool = True) -> List[dict]:
    """执行 L2 安全自动修复，返回动作列表"""
    actions = []

    # 修复 1: metrics.jsonl 超 180 天归档
    if os.path.exists(METRICS_FILE):
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=180)).isoformat()
            kept, archived = [], []
            with open(METRICS_FILE) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    ts = rec.get("timestamp", "")
                    if ts and ts < cutoff:
                        archived.append(line)
                    else:
                        kept.append(line)
            if archived and not dry_run:
                archive_path = os.path.join(METRICS_DIR, "metrics-archive.jsonl")
                with open(archive_path, "a") as f:
                    for ln in archived:
                        f.write(ln + "\n")
                with open(METRICS_FILE, "w") as f:
                    for ln in kept:
                        f.write(ln + "\n")
            actions.append({
                "action": "archive_old_metrics",
                "archived_count": len(archived),
                "dry_run": dry_run,
                "applied": not dry_run and bool(archived),
            })
        except Exception as e:
            actions.append({"action": "archive_old_metrics", "error": str(e)})

    # 修复 2: atom manifest 标注 candidate_for_removal（不删除）
    atoms = audits.get("atoms") or {}
    candidates = atoms.get("candidates_for_removal", [])
    if candidates and not dry_run:
        try:
            manifest_path = os.path.join(ATOMS_DIR, "manifest.json")
            with open(manifest_path) as f:
                manifest = json.load(f)
            for a in manifest.get("atoms", []):
                if a["id"] in candidates:
                    a["candidate_for_removal"] = True
                    a["candidate_since"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            with open(manifest_path, "w") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
            actions.append({
                "action": "mark_unused_atoms_as_candidate",
                "candidates": candidates,
                "applied": True,
            })
        except Exception as e:
            actions.append({"action": "mark_unused_atoms", "error": str(e)})
    elif candidates:
        actions.append({
            "action": "mark_unused_atoms_as_candidate",
            "candidates": candidates,
            "applied": False,
            "dry_run": True,
        })

    return actions


# ── 报告渲染 ──

def render_html_report(audits: Dict[str, dict], score: dict, actions: List[dict], date: str) -> str:
    """生成 HTML 报告"""
    rows = "\n".join(
        f"<tr><td>{k}</td><td>{v.get('per_dimension', {}).get(k, '-') if isinstance(v, dict) else '-'}</td>"
        f"<td>{'✅' if (audits[k].get('ok') or audits[k].get('no_data')) else '❌'}</td></tr>"
        for k, v in audits.items()
    )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Framework Audit {date}</title>
<style>
body {{ font-family: -apple-system, sans-serif; max-width: 900px; margin: 40px auto; padding: 20px; }}
h1 {{ border-bottom: 2px solid #333; }}
.score {{ font-size: 48px; font-weight: bold; color: #0a7; }}
table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; }}
th {{ background: #f0f0f0; }}
.action {{ background: #fff8dc; padding: 8px; margin: 4px 0; border-left: 4px solid #fa0; }}
</style></head>
<body>
<h1>Framework Health Audit — {date}</h1>
<div class="score">Overall Score: {score['overall']}</div>

<h2>7 Dimensions</h2>
<table>
<tr><th>Dimension</th><th>Score</th><th>OK</th></tr>
{rows}
</table>

<h2>L2 Auto-fix Actions</h2>
{"".join(f'<div class="action"><pre>{json.dumps(a, ensure_ascii=False, indent=2)}</pre></div>' for a in actions) or "<p>无自动修复动作</p>"}

<h2>Raw Data</h2>
<pre>{json.dumps(audits, ensure_ascii=False, indent=2, default=str)}</pre>
</body></html>"""


# ── 主流程 ──

def main():
    parser = argparse.ArgumentParser(description="Framework Health Audit")
    parser.add_argument("--auto-fix", action="store_true", help="Apply L2 safe fixes (default: dry-run)")
    parser.add_argument("--only", nargs="*", help="Only run specific audits")
    args = parser.parse_args()

    os.makedirs(AUDIT_DIR, exist_ok=True)
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"[framework-audit] {date}")
    print(f"skill_root = {SKILL_ROOT}")
    print(f"auto_fix   = {args.auto_fix}")

    audits = {}
    runners = {
        "pytest": audit_pytest,
        "imports": audit_imports,
        "ai_metrics": audit_ai_metrics,
        "atoms": audit_atoms,
        "knowledge": audit_knowledge,
        "release_decisions": audit_release_decisions,
        "regression_trend": audit_regression_trend,
    }
    for k, fn in runners.items():
        if args.only and k not in args.only:
            continue
        try:
            audits[k] = fn()
        except Exception as e:
            audits[k] = {"ok": False, "error": str(e)}
            print(f"  ❌ {k} crashed: {e}")

    score = score_audits(audits)
    _section("综合评分")
    print(f"  Overall: {score['overall']}")
    for k, v in score["per_dimension"].items():
        print(f"    {k:25s} {v}")

    actions = auto_fix_l2(audits, dry_run=not args.auto_fix)
    _section("L2 Auto-fix Actions")
    for a in actions:
        print(f"  {json.dumps(a, ensure_ascii=False)}")

    # 落盘
    report = {
        "date": date,
        "score": score,
        "audits": audits,
        "actions": actions,
        "auto_fix_applied": args.auto_fix,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    json_path = os.path.join(AUDIT_DIR, f"{date}.json")
    latest_path = os.path.join(AUDIT_DIR, "latest.json")
    with open(json_path, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    with open(latest_path, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    html_path = os.path.join(AUDIT_DIR, f"{date}.html")
    with open(html_path, "w") as f:
        f.write(render_html_report(audits, score, actions, date))
    print(f"\n📄 JSON:    {json_path}")
    print(f"📄 Latest: {latest_path}")
    print(f"📄 HTML:   {html_path}")

    # 退出码：评分 < 60 返回非 0
    sys.exit(0 if score["overall"] >= 60 else 1)


if __name__ == "__main__":
    sys.path.insert(0, SKILL_ROOT)
    main()
