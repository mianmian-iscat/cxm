#!/usr/bin/env python3
"""
case_generator.py — 基于 PRD 功能点自动生成 eval 用例

输入: prd-features.json (来自 prd_parser.py 输出)
输出: eval/cases/f88-test/new-requirement-{prd_id}/ 目录下的用例 JSON 文件

用法:
  python scripts/case_generator.py --features artifacts/prd-features.json
  python scripts/case_generator.py --features artifacts/prd-features.json --out-dir eval/cases/f88-test/new-req-xxx
  python scripts/case_generator.py --features artifacts/prd-features.json --dry-run
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
CASES_DIR = WORKSPACE / "eval" / "cases" / "f88-test"
BASE_URL = "https://pre-aifashion-xiaoer.alibaba-inc.com"

# ── 页面配置 ──
PAGE_CONFIG = {
    "/review/personal-task-center": {
        "page_name": "个人任务中心",
        "prefix": "ptc",
        "business_type": "f88_material_audit",
    },
    "/review/standard-management": {
        "page_name": "审核标准管理",
        "prefix": "as",
        "business_type": "f88_material_audit",
    },
    "/review/node-management": {
        "page_name": "审核节点管理",
        "prefix": "an",
        "business_type": "f88_material_audit",
    },
    "/review/task-management": {
        "page_name": "任务管理",
        "prefix": "tm",
        "business_type": "f88_material_audit",
    },
    "/strategy/linkList": {
        "page_name": "链路列表",
        "prefix": "ll",
        "business_type": "f88_material_production",
    },
    "/strategy/list": {
        "page_name": "策略列表",
        "prefix": "sl",
        "business_type": "f88_material_production",
    },
    "/strategy/productionDashboard": {
        "page_name": "生产看板",
        "prefix": "pd",
        "business_type": "f88_material_production",
    },
    "/templateManagement": {
        "page_name": "模版包管理",
        "prefix": "tpm",
        "business_type": "f88_material",
    },
    "/templateLibrary": {
        "page_name": "淘内资源池",
        "prefix": "tl",
        "business_type": "f88_material",
    },
    "/selfTemplateLibrary_f88": {
        "page_name": "优质模板库",
        "prefix": "qt",
        "business_type": "f88_material",
    },
    "/afdMerchantManagement/shopConfig": {
        "page_name": "商家管理",
        "prefix": "mc",
        "business_type": "f88_material_audit",
    },
}


def slugify(text: str, max_len: int = 20) -> str:
    """生成文件安全 ID"""
    text = re.sub(r'[^\w\u4e00-\u9fff]', '-', text)
    text = re.sub(r'-+', '-', text).strip('-')
    return text[:max_len]


def make_case_id(prefix: str, feature_idx: int, op_idx: int, op_text: str) -> str:
    """生成用例 ID"""
    slug = slugify(op_text, 15)
    return f"nr-{prefix}-{feature_idx:02d}-{op_idx:02d}-{slug}"


def generate_page_load_case(page: str, config: dict, prd_id: str) -> dict:
    """生成页面加载验证用例"""
    case_id = f"nr-{config['prefix']}-pageload"
    return {
        "id": case_id,
        "name": f"新需求 PRD-{prd_id}: {config['page_name']}页面加载验证",
        "description": f"PRD-{prd_id} 变更后验证 {config['page_name']} 页面可正常加载",
        "businessType": config["business_type"],
        "scene": "f88-test",
        "priority": "P0",
        "category": "normal_flow",
        "context": {
            "urlPattern": "pre-aifashion-xiaoer.alibaba-inc.com",
            "url": f"{BASE_URL}{page}",
            "waitAfterLoad": 3000,
            "auth": "buc",
            "captureFilter": "bzb.api.fsyx_quality_guard"
        },
        "steps": [
            {
                "type": "navigate",
                "url": f"{BASE_URL}{page}",
                "waitUntil": "networkidle",
                "screenshot": True,
                "description": f"打开{config['page_name']}页面"
            },
            {
                "type": "wait",
                "ms": 3000,
                "description": "等待页面加载"
            },
            {
                "type": "assert",
                "target": "page",
                "contains": config["page_name"],
                "description": f"验证页面标题包含'{config['page_name']}'"
            },
            {
                "type": "screenshot",
                "label": f"nr-{config['prefix']}-pageload",
                "description": "页面加载截图"
            }
        ],
        "screenshot": {"onError": True},
        "contextOptimization": {
            "screenshotExternal": True,
            "maxResponseSizeKb": 100,
            "outputCompact": True
        },
        "_expected": {"status": "pass"},
        "_testDesign": {
            "preconditions": f"F88预发已登录；PRD-{prd_id}已部署",
            "realDomNotes": f"PRD-{prd_id}自动生成的页面加载验证",
            "riskPoints": ["页面可能因部署未完成而加载失败"]
        },
        "_promoted": {
            "from_prd": prd_id,
            "generated_at": datetime.now().isoformat(),
            "generator": "case_generator.py"
        }
    }


def generate_ui_change_case(page: str, config: dict, prd_id: str,
                            feature_idx: int, change_idx: int,
                            change_text: str) -> dict:
    """生成 UI 变更验证用例"""
    case_id = make_case_id(config["prefix"], feature_idx, change_idx, change_text)

    # 根据变更内容生成断言
    steps = [
        {
            "type": "navigate",
            "url": f"{BASE_URL}{page}",
            "waitUntil": "networkidle",
            "screenshot": True,
            "description": f"打开{config['page_name']}页面"
        },
        {
            "type": "wait",
            "ms": 3000,
            "description": "等待页面加载"
        }
    ]

    # 根据变更文本推断断言类型
    if "按钮" in change_text or "btn" in change_text.lower():
        # 按钮相关变更
        btn_name = re.search(r'[「""](.+?)[」""]', change_text)
        if btn_name:
            steps.append({
                "type": "assert",
                "target": "page",
                "contains": btn_name.group(1),
                "description": f"验证按钮'{btn_name.group(1)}'存在"
            })
    elif "列" in change_text or "表头" in change_text:
        # 表格列变更
        col_name = re.search(r'[「""](.+?)[」""]', change_text)
        if col_name:
            steps.append({
                "type": "evaluate",
                "expression": f"Array.from(document.querySelectorAll('.ant-table-thead th')).map(th => th.textContent.trim())",
                "storeAs": "tableHeaders",
                "description": "提取表头列名"
            })
    elif "筛选" in change_text or "搜索" in change_text:
        steps.append({
            "type": "evaluate",
            "expression": "Array.from(document.querySelectorAll('.ant-form-item-label label, .ant-form-item-label span')).map(el => el.textContent.trim()).filter(Boolean)",
            "storeAs": "filterLabels",
            "description": "提取筛选标签"
        })

    steps.append({
        "type": "evaluate",
        "expression": "(() => { const btns = Array.from(document.querySelectorAll('button, [role=button], a.ant-btn')).filter(b => b.offsetHeight > 0).map(b => b.textContent.trim()).filter(Boolean); return { buttonCount: btns.length, buttons: btns.slice(0, 20) }; })()",
        "storeAs": "pageButtons",
        "description": "提取所有可见按钮"
    })

    steps.append({
        "type": "screenshot",
        "label": f"nr-{case_id}",
        "description": "UI变更验证截图"
    })

    return {
        "id": case_id,
        "name": f"新需求 PRD-{prd_id}: {config['page_name']}-{change_text[:30]}",
        "description": f"PRD-{prd_id} UI变更验证: {change_text[:80]}",
        "businessType": config["business_type"],
        "scene": "f88-test",
        "priority": "P1",
        "category": "normal_flow",
        "context": {
            "urlPattern": "pre-aifashion-xiaoer.alibaba-inc.com",
            "url": f"{BASE_URL}{page}",
            "waitAfterLoad": 3000,
            "auth": "buc",
            "captureFilter": "bzb.api.fsyx_quality_guard"
        },
        "steps": steps,
        "screenshot": {"onError": True},
        "contextOptimization": {
            "screenshotExternal": True,
            "maxResponseSizeKb": 100,
            "outputCompact": True
        },
        "_expected": {"status": "pass"},
        "_testDesign": {
            "preconditions": f"F88预发已登录；PRD-{prd_id}已部署",
            "realDomNotes": f"PRD-{prd_id}自动生成的UI变更验证: {change_text[:100]}",
            "riskPoints": ["UI变更可能导致现有元素定位偏移"]
        },
        "_promoted": {
            "from_prd": prd_id,
            "generated_at": datetime.now().isoformat(),
            "generator": "case_generator.py"
        }
    }


def generate_operation_case(page: str, config: dict, prd_id: str,
                            feature_idx: int, op_idx: int,
                            operation: str) -> dict:
    """生成操作级验证用例"""
    case_id = make_case_id(config["prefix"], feature_idx, op_idx + 10, operation)

    steps = [
        {
            "type": "navigate",
            "url": f"{BASE_URL}{page}",
            "waitUntil": "networkidle",
            "screenshot": True,
            "description": f"打开{config['page_name']}页面"
        },
        {
            "type": "wait",
            "ms": 3000,
            "description": "等待页面加载"
        },
        {
            "type": "evaluate",
            "expression": "(() => { const allText = document.body.innerText; const btns = Array.from(document.querySelectorAll('button, a, [role=button]')).filter(b => b.offsetHeight > 0).map(b => b.textContent.trim()).filter(Boolean); return { bodyTextPreview: allText.substring(0, 500), buttons: btns.slice(0, 20) }; })()",
            "storeAs": "pageState",
            "description": "采集页面状态"
        },
        {
            "type": "screenshot",
            "label": f"nr-{case_id}-before",
            "description": "操作前截图"
        }
    ]

    # 根据操作类型生成步骤
    if "新增" in operation or "添加" in operation or "新建" in operation or "创建" in operation:
        btn_text = re.search(r'[「""](.+?)[」""]', operation)
        if btn_text:
            steps.append({
                "type": "clickText",
                "text": btn_text.group(1),
                "description": f"点击'{btn_text.group(1)}'按钮"
            })
            steps.append({
                "type": "wait",
                "ms": 2000,
                "description": "等待弹窗/页面加载"
            })
            steps.append({
                "type": "screenshot",
                "label": f"nr-{case_id}-after-click",
                "description": "点击后截图"
            })

    steps.append({
        "type": "screenshot",
        "label": f"nr-{case_id}-final",
        "description": "最终状态截图"
    })

    return {
        "id": case_id,
        "name": f"新需求 PRD-{prd_id}: {config['page_name']}-{operation[:30]}",
        "description": f"PRD-{prd_id} 操作验证: {operation[:80]}",
        "businessType": config["business_type"],
        "scene": "f88-test",
        "priority": "P1",
        "category": "normal_flow",
        "context": {
            "urlPattern": "pre-aifashion-xiaoer.alibaba-inc.com",
            "url": f"{BASE_URL}{page}",
            "waitAfterLoad": 3000,
            "auth": "buc",
            "captureFilter": "bzb.api.fsyx_quality_guard"
        },
        "steps": steps,
        "screenshot": {"onError": True},
        "contextOptimization": {
            "screenshotExternal": True,
            "maxResponseSizeKb": 100,
            "outputCompact": True
        },
        "_expected": {"status": "pass"},
        "_testDesign": {
            "preconditions": f"F88预发已登录；PRD-{prd_id}已部署",
            "realDomNotes": f"PRD-{prd_id}自动生成的操作验证: {operation[:100]}",
            "riskPoints": ["操作可能触发弹窗或页面跳转"]
        },
        "_promoted": {
            "from_prd": prd_id,
            "generated_at": datetime.now().isoformat(),
            "generator": "case_generator.py"
        }
    }


def generate_cases(features: dict, out_dir: Path, dry_run: bool = False) -> list:
    """根据功能点生成全部用例"""
    prd_id = features["prd_id"]
    all_cases = []
    seen_pages = set()

    for fi, feature in enumerate(features["features"]):
        page = feature.get("page", "")
        if not page:
            print(f"  [SKIP] 功能点 {fi} 无页面路由: {feature.get('section_title', '?')}", file=sys.stderr)
            continue

        config = PAGE_CONFIG.get(page)
        if not config:
            print(f"  [SKIP] 未知页面: {page}", file=sys.stderr)
            continue

        # 每个页面生成一个 page_load 用例（去重）
        if page not in seen_pages:
            seen_pages.add(page)
            case = generate_page_load_case(page, config, prd_id)
            all_cases.append(case)

        # 为每个 UI 变更生成用例
        for ci, change in enumerate(feature.get("ui_changes", [])):
            case = generate_ui_change_case(page, config, prd_id, fi, ci, change)
            all_cases.append(case)

        # 为每个操作变更生成用例
        for oi, op in enumerate(feature.get("operations", [])):
            case = generate_operation_case(page, config, prd_id, fi, oi, op)
            all_cases.append(case)

    # 写入文件
    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    for case in all_cases:
        filename = f"{case['id'].replace('-', '_')}.json"
        filepath = out_dir / filename

        if dry_run:
            print(f"  [DRY-RUN] 将生成: {filename} ({len(case['steps'])} steps)", file=sys.stderr)
        else:
            filepath.write_text(json.dumps(case, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print(f"  ✓ {filename} ({len(case['steps'])} steps)", file=sys.stderr)

    return all_cases


def main():
    parser = argparse.ArgumentParser(description='基于 PRD 功能点自动生成 eval 用例')
    parser.add_argument('--features', required=True, help='PRD 功能点 JSON 文件 (来自 prd_parser.py)')
    parser.add_argument('--out-dir', help='输出目录 (默认: eval/cases/f88-test/new-requirement-{prd_id}/)')
    parser.add_argument('--dry-run', action='store_true', help='只打印不写入')
    args = parser.parse_args()

    features = json.loads(Path(args.features).read_text(encoding='utf-8'))
    prd_id = features["prd_id"]

    out_dir = Path(args.out_dir) if args.out_dir else CASES_DIR / f"new-requirement-{prd_id}"

    print(f"[case_generator] PRD: {prd_id}", file=sys.stderr)
    print(f"[case_generator] 功能点: {features['feature_count']}", file=sys.stderr)
    print(f"[case_generator] 输出目录: {out_dir}", file=sys.stderr)

    cases = generate_cases(features, out_dir, dry_run=args.dry_run)

    print(f"\n[case_generator] 共生成 {len(cases)} 个用例", file=sys.stderr)

    # 输出汇总
    summary = {
        "prd_id": prd_id,
        "generated_at": datetime.now().isoformat(),
        "total_cases": len(cases),
        "cases": [{"id": c["id"], "name": c["name"], "steps": len(c["steps"])} for c in cases]
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
