#!/usr/bin/env python3
"""quality_patrol.py — F88 多群问题质量巡检脚本

基于 2026-07-23 多群问题汇总文档，覆盖6大问题领域：
  3.1 模型/算法依赖容错
  3.2 数据源有效性校验
  3.3 策略配置正确性
  3.5 数据流转完整性
  3.6 数据格式健壮性

用法：
  python3 scripts/quality_patrol.py              # 执行全部巡检
  python3 scripts/quality_patrol.py --section 3.1 # 只执行指定章节
  python3 scripts/quality_patrol.py --dry-run     # 只打印SQL不执行
"""
import json, os, subprocess, sys, time
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTIFACTS = os.path.join(BASE, "artifacts")
TODAY = datetime.now().strftime("%Y-%m-%d")

# ── 数据库配置 ──
DMS_GROUP = "stylespot"
DMS_DB_PROD = "rm-lgay0v5lor8396yka"

DRY_RUN = "--dry-run" in sys.argv
TARGET_SECTION = None
for i, arg in enumerate(sys.argv):
    if arg == "--section" and i + 1 < len(sys.argv):
        TARGET_SECTION = sys.argv[i + 1]

results = []

def run_sql(sql, label, section):
    """通过 dms-alibaba CLI 执行 SQL 并返回结果"""
    if TARGET_SECTION and section != TARGET_SECTION:
        return None
    entry = {
        "section": section,
        "label": label,
        "sql": sql.strip(),
        "status": "pending",
        "data": None,
        "error": None,
        "elapsed": 0
    }
    if DRY_RUN:
        print(f"\n[{section}] {label}")
        print(f"  SQL: {sql.strip()[:200]}...")
        entry["status"] = "dry-run"
        results.append(entry)
        return entry

    print(f"\n[{section}] 执行: {label} ...", end=" ", flush=True)
    start = time.time()
    try:
        proc = subprocess.run(
            ["dms-alibaba", "sql", "run", DMS_GROUP, "--db", DMS_DB_PROD, "--sql", sql.strip()],
            capture_output=True, text=True, timeout=60, cwd=BASE
        )
        elapsed = round(time.time() - start, 1)
        entry["elapsed"] = elapsed
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()

        if proc.returncode == 0:
            # 尝试解析 JSON 结果
            entry["data"] = stdout
            entry["status"] = "pass"
            print(f"✓ ({elapsed}s)")
            # 尝试从 _results 目录读取最新 JSON
            results_dir = os.path.join(BASE, ".dms-alibaba", "db-groups", DMS_GROUP,
                                        "sql", f"quick_{DMS_DB_PROD}", "_results", TODAY)
            if os.path.isdir(results_dir):
                files = sorted([f for f in os.listdir(results_dir) if f.endswith(".json")], reverse=True)
                if files:
                    try:
                        with open(os.path.join(results_dir, files[0])) as f:
                            entry["data"] = json.load(f)
                    except:
                        pass
        else:
            entry["error"] = stderr or stdout
            entry["status"] = "fail"
            print(f"✗ ({elapsed}s): {stderr[:100]}")
    except subprocess.TimeoutExpired:
        entry["elapsed"] = round(time.time() - start, 1)
        entry["status"] = "timeout"
        entry["error"] = "SQL执行超时(60s)"
        print(f"⏱ 超时")
    except FileNotFoundError:
        entry["status"] = "error"
        entry["error"] = "dms-alibaba CLI 未安装"
        print(f"✗ CLI未安装")

    results.append(entry)
    return entry

def analyze_model_errors(entry):
    """分析模型/算法相关错误"""
    if not entry or not entry.get("data"):
        return
    data = entry["data"]
    analysis = {
        "total_failed": 0,
        "model_related": 0,
        "algorithm_related": 0,
        "cdn_related": 0,
        "other": 0,
        "model_errors": [],
        "algorithm_errors": [],
        "findings": []
    }
    if isinstance(data, list):
        for row in data:
            analysis["total_failed"] += 1
            err = str(row.get("error_msg", "") or row.get("errorMsg", "") or "").lower()
            if any(k in err for k in ["model", "claude", "gpt", "gemini", "llm", "openai", "sonnet"]):
                analysis["model_related"] += 1
                analysis["model_errors"].append(row)
            elif any(k in err for k in ["tpp", "algorithm", "algo", "裁头"]):
                analysis["algorithm_related"] += 1
                analysis["algorithm_errors"].append(row)
            elif any(k in err for k in ["cdn", "url", "image_not_found", "404"]):
                analysis["cdn_related"] += 1
            else:
                analysis["other"] += 1
    elif isinstance(data, str):
        # 文本结果，做关键词匹配
        lower = data.lower()
        for k in ["model", "claude", "gpt", "gemini", "llm", "openai"]:
            if k in lower:
                analysis["model_related"] += lower.count(k)
                analysis["findings"].append(f"发现模型关键词 '{k}' 出现 {lower.count(k)} 次")
        for k in ["tpp", "algorithm", "裁头"]:
            if k in lower:
                analysis["algorithm_related"] += lower.count(k)
                analysis["findings"].append(f"发现算法关键词 '{k}' 出现 {lower.count(k)} 次")
    entry["analysis"] = analysis

# ═══════════════════════════════════════════════
# 3.1 模型/算法依赖容错测试
# ═══════════════════════════════════════════════
print("\n" + "=" * 60)
print("3.1 模型/算法依赖容错测试")
print("=" * 60)

# TC-3.1-1: 指定批次的模型/算法相关FAIL节点（走batch_id索引）
# 注意: workflow_record_log 只有 batch_id 有索引，必须用 IN(...) 走索引
e1 = run_sql("""
SELECT batch_id, node_type, status,
  LEFT(JSON_EXTRACT(extra_info, '$.errorMsg'), 300) as error_msg
FROM workflow_record_log
WHERE batch_id IN ('BT_7051','BT_7034','BT_6969','BT_7056',
  'BT_6982','BT_7019','BT_7058','BT_7054','BT_7060','BT_7063')
  AND status = 'FAIL'
  AND id > 4000000
ORDER BY id DESC
LIMIT 30
""", "文档提及批次的FAIL节点明细", "3.1")
analyze_model_errors(e1)

# TC-3.1-2: 驳回重生/盗图相关策略配置（用name字段，非status）
e2 = run_sql("""
SELECT id, name, is_deleted, life_cycle_code, gmt_modified,
  LEFT(JSON_EXTRACT(workflow_def, '$.innerNodes[*].modelType'), 200) as model_types
FROM g_strategy
WHERE is_deleted = 0
  AND (name LIKE '%驳回%' OR name LIKE '%重生%' OR name LIKE '%盗图%')
ORDER BY gmt_modified DESC
LIMIT 20
""", "驳回重生/盗图策略配置与模型", "3.1")

# ═══════════════════════════════════════════════
# 3.2 数据源有效性校验
# ═══════════════════════════════════════════════
print("\n" + "=" * 60)
print("3.2 数据源有效性校验")
print("=" * 60)

# TC-3.2-1: 指定批次中CDN/URL相关错误（走batch_id索引）
run_sql("""
SELECT batch_id, node_type,
  LEFT(JSON_EXTRACT(extra_info, '$.errorMsg'), 200) as error_msg
FROM workflow_record_log
WHERE batch_id IN ('BT_7019','BT_6982','BT_7056')
  AND status = 'FAIL'
  AND id > 4000000
  AND (
    JSON_EXTRACT(extra_info, '$.errorMsg') LIKE '%URL%'
    OR JSON_EXTRACT(extra_info, '$.errorMsg') LIKE '%CDN%'
    OR JSON_EXTRACT(extra_info, '$.errorMsg') LIKE '%404%'
    OR JSON_EXTRACT(extra_info, '$.errorMsg') LIKE '%expired%'
    OR JSON_EXTRACT(extra_info, '$.errorMsg') LIKE '%seed%'
  )
ORDER BY id DESC
LIMIT 20
""", "指定批次中CDN/URL相关FAIL", "3.2")

# TC-3.2-2: 近期批次状态分布（含素材相关批次）
run_sql("""
SELECT batch_id, status, gmt_create, batch_name
FROM g_workflow_batch
WHERE gmt_create > DATE_SUB(NOW(), INTERVAL 7 DAY)
ORDER BY gmt_create DESC
LIMIT 30
""", "近7天批次状态概览", "3.2")

# ═══════════════════════════════════════════════
# 3.3 策略配置正确性
# ═══════════════════════════════════════════════
print("\n" + "=" * 60)
print("3.3 策略配置正确性")
print("=" * 60)

# TC-3.3-1: 驳回重生/盗图相关策略配置（已在3.1中查询，此处补充优先级检查）
run_sql("""
SELECT id, name, life_cycle_code,
  JSON_EXTRACT(extra_info, '$.priority') as priority,
  gmt_modified
FROM g_strategy
WHERE is_deleted = 0
  AND life_cycle_code = 'mass_prod'
ORDER BY gmt_modified DESC
LIMIT 15
""", "mass_prod策略列表与优先级", "3.3")

# TC-3.3-2: 检查近7天新建策略的元数据完整性
run_sql("""
SELECT id, name, life_cycle_code, creator,
  JSON_EXTRACT(extra_info, '$.strategyName') as ext_name,
  JSON_EXTRACT(extra_info, '$.priority') as priority,
  gmt_create
FROM g_strategy
WHERE is_deleted = 0
  AND gmt_create > DATE_SUB(NOW(), INTERVAL 7 DAY)
ORDER BY gmt_create DESC
LIMIT 20
""", "近7天新建策略的元数据完整性", "3.3")

# ═══════════════════════════════════════════════
# 3.4 前端功能与权限测试（DB交叉验证）
# ═══════════════════════════════════════════════
print("\n" + "=" * 60)
print("3.4 前端功能与权限测试（DB交叉验证）")
print("=" * 60)

# TC-3.4-1: 模板包状态分布（前端筛选数值交叉验证）
run_sql("""
SELECT status, COUNT(*) as cnt
FROM afd_seller_template_package
GROUP BY status
ORDER BY status
""", "模板包状态分布(筛选数值DB校验)", "3.4")

# ═══════════════════════════════════════════════
# 3.5 数据流转完整性
# ═══════════════════════════════════════════════
print("\n" + "=" * 60)
print("3.5 数据流转完整性")
print("=" * 60)

# TC-3.5-1: 指定批次的节点状态分布（走batch_id索引）
run_sql("""
SELECT batch_id, status, COUNT(*) as cnt
FROM workflow_record_log
WHERE batch_id IN ('BT_7056','BT_7058','BT_7060','BT_7063','BT_7076','BT_6982')
  AND id > 4000000
GROUP BY batch_id, status
ORDER BY batch_id, status
""", "关键批次节点状态分布", "3.5")

# TC-3.5-2: 检查HANDLING长期卡住的任务（走batch_id索引）
run_sql("""
SELECT batch_id, node_type, COUNT(*) as cnt
FROM workflow_record_log
WHERE batch_id IN ('BT_6982','BT_7063','BT_7056')
  AND id > 4000000
  AND status = 'HANDLING'
GROUP BY batch_id, node_type
ORDER BY cnt DESC
LIMIT 20
""", "HANDLING长期卡住节点分布", "3.5")

# ═══════════════════════════════════════════════
# 3.6 数据格式健壮性
# ═══════════════════════════════════════════════
print("\n" + "=" * 60)
print("3.6 数据格式健壮性")
print("=" * 60)

# TC-3.6-1: 指定批次中error_msg含换行符（走batch_id索引）
run_sql("""
SELECT batch_id, node_type,
  LEFT(JSON_EXTRACT(extra_info, '$.errorMsg'), 200) as error_msg
FROM workflow_record_log
WHERE batch_id IN ('BT_7056','BT_7058','BT_6982','BT_7019','BT_7054')
  AND id > 4000000
  AND (
    JSON_EXTRACT(extra_info, '$.errorMsg') LIKE '%JSON%'
    OR JSON_EXTRACT(extra_info, '$.errorMsg') LIKE '%parse%'
    OR JSON_EXTRACT(extra_info, '$.errorMsg') LIKE '%\\\\n%'
  )
ORDER BY id DESC
LIMIT 15
""", "error_msg含\\n或JSON关键词(指定批次)", "3.6")

# TC-3.6-2: 检查prompt超长错误
run_sql("""
SELECT batch_id, node_type,
  LEFT(JSON_EXTRACT(extra_info, '$.errorMsg'), 200) as error_msg
FROM workflow_record_log
WHERE batch_id IN ('BT_6982','BT_7063')
  AND id > 4000000
  AND JSON_EXTRACT(extra_info, '$.errorMsg') LIKE '%too long%'
LIMIT 5
""", "prompt超长错误检查", "3.6")

# ═══════════════════════════════════════════════
# 生成报告
# ═══════════════════════════════════════════════
print("\n" + "=" * 60)
print("生成巡检报告")
print("=" * 60)

report = {
    "title": "F88 多群问题质量巡检报告",
    "date": TODAY,
    "generated_at": datetime.now().isoformat(),
    "sections": {},
    "summary": {
        "total_checks": len(results),
        "passed": sum(1 for r in results if r["status"] == "pass"),
        "failed": sum(1 for r in results if r["status"] == "fail"),
        "timeout": sum(1 for r in results if r["status"] == "timeout"),
        "skipped": sum(1 for r in results if r["status"] == "dry-run"),
    }
}

for r in results:
    sec = r["section"]
    if sec not in report["sections"]:
        report["sections"][sec] = []
    # 清理不可序列化的大数据
    entry = {
        "label": r["label"],
        "status": r["status"],
        "elapsed": r["elapsed"],
    }
    if r.get("error"):
        entry["error"] = r["error"][:500]
    if r.get("analysis"):
        entry["analysis"] = r["analysis"]
    report["sections"][sec].append(entry)

out_path = os.path.join(ARTIFACTS, f"quality-patrol-{TODAY}.json")
os.makedirs(ARTIFACTS, exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print(f"\n报告已保存到: {out_path}")

# 打印摘要
print(f"\n{'='*60}")
print(f"巡检摘要")
print(f"{'='*60}")
print(f"  总检查项: {report['summary']['total_checks']}")
print(f"  通过: {report['summary']['passed']}")
print(f"  失败: {report['summary']['failed']}")
print(f"  超时: {report['summary']['timeout']}")
print(f"  跳过: {report['summary']['skipped']}")

# 打印各节摘要
for sec, items in sorted(report["sections"].items()):
    print(f"\n  [{sec}]")
    for item in items:
        icon = {"pass": "✓", "fail": "✗", "timeout": "⏱", "dry-run": "○"}.get(item["status"], "?")
        print(f"    {icon} {item['label']} ({item['elapsed']}s)")
        if item.get("error"):
            print(f"      错误: {item['error'][:100]}")
