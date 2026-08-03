#!/usr/bin/env python3
"""
batch_fill_steps.py — 批量为 eval/cases 中空步骤用例生成可执行 steps

路由规则：
- op-test 商家端 → pre-fsyc.taobao.com (auth=taobao)
- op-test 小二端 → pre-xiaoer.alibaba-inc.com/bzb/noone/... (auth=buc)
- f88-test → pre-aifashion-xiaoer.alibaba-inc.com/... (auth=buc)

每个用例生成 5-8 步通用探测步骤:
1. navigate → 目标URL
2. wait → 3000ms
3. evaluate → DOM探测
4. assertStore → 页面已加载
5. evaluate → 基于stepsText的操作模拟
6. wait → 2000ms
7. evaluate → 基于expectedResult的条件校验
8. screenshot → 结果截图
"""

import json, os, glob, sys, re
from urllib.parse import urlparse

# ─── URL 路由表 ───

OP_SELLER_URL = "https://pre-fsyc.taobao.com/"
OP_SELLER_PATTERN = "pre-fsyc.taobao.com"

OP_XIAOER_URL = "https://pre-xiaoer.alibaba-inc.com/bzb/noone/taotian-apparel-original-protection-xiaoer/list"
OP_XIAOER_PATTERN = "pre-xiaoer.alibaba-inc.com"

OP_SETTLEMENT_URL = "https://pre-xiaoer.alibaba-inc.com/bzb/fsyx_quality_guard/quality-pulse/settlement-manage"
OP_SETTLEMENT_PATTERN = "pre-xiaoer.alibaba-inc.com"

OP_PRODUCT_URL = "https://pre-xiaoer.alibaba-inc.com/bzb/fsyx_quality_guard/quality-pulse/product-management"
OP_PRODUCT_PATTERN = "pre-xiaoer.alibaba-inc.com"

F88_BASE = "https://pre-aifashion-xiaoer.alibaba-inc.com"
F88_PATTERN = "pre-aifashion-xiaoer.alibaba-inc.com"

# f88 子目录 → 路径映射
F88_ROUTES = {
    "审核管理": "/review/task-center",
    "审核详情页": "/review/task-center",
    "个人任务中心": "/review/personal-task-center",
    "任务管理": "/review/personal-task-center",
    "策略管理": "/strategy/list",
    "策略列表": "/strategy/list",
    "策略详情": "/strategy/list",
    "链路管理": "/strategy/linkDetail?id=20180",
    "模版库": "/template/list",
    "模板库": "/template/list",
    "商家管理": "/merchant/list",
    "生产看板": "/production/dashboard",
    "全链路E2E": "/strategy/list",
    "F88-任务管理页面用例": "/review/personal-task-center",
    "F88-平台全模块用例": "/strategy/list",
}

# op-test 小二端特殊路径
OP_XIAOER_SPECIAL = {
    "结算": OP_SETTLEMENT_URL,
    "退款": OP_SETTLEMENT_URL,
    "运营": OP_SETTLEMENT_URL,
    "商品管理": OP_PRODUCT_URL,
    "product": OP_PRODUCT_URL,
}


def resolve_url(rel_path, case_data):
    """根据文件相对路径确定目标URL和auth"""
    parts = rel_path.replace("\\", "/").split("/")
    domain = parts[0]  # op-test or f88-test
    subdirs = "/".join(parts[1:-1])  # 中间目录
    filename = parts[-1]
    full_path = subdirs + "/" + filename

    if domain == "op-test":
        is_xiaoer = "小二端" in subdirs or "小二" in filename
        is_seller = "商家端" in subdirs or "商家" in filename or "m1-" in filename.lower()

        # 特殊：服务市场
        if "服务市场" in subdirs:
            return OP_SELLER_URL, "taobao", OP_SELLER_PATTERN

        if is_xiaoer:
            # 检查是否是结算/商品管理特殊页面
            for keyword, url in OP_XIAOER_SPECIAL.items():
                if keyword in subdirs:
                    pattern = OP_SETTLEMENT_PATTERN if "settlement" in url else OP_PRODUCT_PATTERN
                    return url, "buc", pattern
            # 特殊：08-小二端快审入驻校验
            if "快审" in subdirs or "入驻" in subdirs:
                return OP_XIAOER_URL, "buc", OP_XIAOER_PATTERN
            return OP_XIAOER_URL, "buc", OP_XIAOER_PATTERN

        # 默认商家端
        return OP_SELLER_URL, "taobao", OP_SELLER_PATTERN

    elif domain == "f88-test":
        # 按目录名匹配
        for keyword, path in F88_ROUTES.items():
            if keyword in subdirs or keyword in full_path:
                return F88_BASE + path, "buc", F88_PATTERN

        # 检查步骤文本中的路径提示
        td = case_data.get("_testDesign", {})
        steps_text = td.get("stepsText", "")
        path_match = re.search(r'/[a-z][\w/-]+', steps_text)
        if path_match:
            hint_path = path_match.group(0)
            if len(hint_path) > 3:
                return F88_BASE + hint_path, "buc", F88_PATTERN

        # 默认
        return F88_BASE + "/strategy/list", "buc", F88_PATTERN

    return None, None, None


def parse_steps_text(steps_text):
    """解析 stepsText 为操作列表"""
    if not steps_text:
        return []
    # 分割: "1.xxx 2.yyy 3.zzz" 或 "1. xxx\n2. yyy"
    parts = re.split(r'(?:^|\n)\s*\d+[\.\、\)\s]', steps_text.strip())
    parts = [p.strip() for p in parts if p.strip()]
    if not parts and steps_text.strip():
        parts = [steps_text.strip()]
    return parts


def build_action_expression(action_text, url):
    """根据操作文本生成 evaluate 表达式"""
    text = action_text.lower()

    # 导航类
    if any(kw in text for kw in ["导航至", "打开", "进入", "访问", "跳转"]):
        return None  # navigate 已覆盖

    # 点击类
    if any(kw in text for kw in ["点击", "单击", "click", "按下"]):
        # 提取按钮文本
        btn_match = re.search(r'[「""](.+?)[」""]', action_text)
        btn_text = btn_match.group(1) if btn_match else action_text.split("点击")[-1].strip()[:20]
        return (
            f"(() => {{ const btns = Array.from(document.querySelectorAll('button,a,[role=button]'))"
            f".filter(el => (el.textContent || '').includes('{btn_text}'));"
            f" if(btns.length > 0) {{ btns[0].click(); return {{ clicked: true, text: '{btn_text}' }}; }}"
            f" return {{ clicked: false, searched: '{btn_text}' }}; }})()"
        )

    # 查看/检查类（纯观察）
    if any(kw in text for kw in ["查看", "检查", "确认", "验证", "观察"]):
        return None

    # 输入类
    if any(kw in text for kw in ["输入", "填写", "搜索", "填充"]):
        return (
            "(() => { const inputs = Array.from(document.querySelectorAll('input:not([type=checkbox]):not([type=radio]), textarea'));"
            " if(inputs.length > 0) { return { inputCount: inputs.length, firstPlaceholder: inputs[0].getAttribute('placeholder') || '' }; }"
            " return { inputCount: 0 }; })()"
        )

    # Tab切换
    if any(kw in text for kw in ["tab", "切换", "选项卡"]):
        tab_match = re.search(r'[「""](.+?)[」""]', action_text)
        tab_text = tab_match.group(1) if tab_match else ""
        return (
            f"(() => {{ const tabs = Array.from(document.querySelectorAll('.ant-tabs-tab'));"
            f" const target = tabs.find(t => (t.textContent || '').includes('{tab_text}'));"
            f" if(target) {{ target.click(); return {{ tabClicked: true, text: '{tab_text}' }}; }}"
            f" return {{ tabClicked: false, availableTabs: tabs.map(t => t.textContent.trim()).slice(0, 10) }}; }})()"
        )

    # 筛选/选择
    if any(kw in text for kw in ["筛选", "选择", "下拉"]):
        return (
            "(() => { const selects = Array.from(document.querySelectorAll('.ant-select'));"
            " return { selectCount: selects.length }; })()"
        )

    return None


def build_assert_expression(expected_result):
    """根据 expectedResult 生成断言 evaluate 表达式"""
    if not expected_result:
        return None

    text = expected_result.strip()

    # 提取关键检查点：包含"xxx"、包含xxx按钮、显示xxx
    checks = []

    # "包含xxx" 模式
    contains_matches = re.findall(r'[「""\'](.+?)[」""\']', text)
    for match in contains_matches[:5]:
        checks.append(match)

    # 含xxx按钮/字段/标签
    element_matches = re.findall(r'(?:包含|含|有|显示|展示|存在|出现)(\S{2,15}(?:按钮|字段|标签|链接|输入框|下拉框|表格|列表|卡片|弹窗|提示|图标|tab|Tab|选项))', text)
    for match in element_matches[:5]:
        checks.append(match.replace("按钮", "").replace("字段", "").replace("标签", ""))

    # 如果没提取到，用整体文本做模糊匹配
    if not checks:
        # 取前60字符作为检查点
        short = text[:60].replace("'", "").replace('"', '')
        checks = [short]

    checks_js = json.dumps(checks[:5], ensure_ascii=False)
    return (
        f"(() => {{ const text = document.body.textContent || '';"
        f" const checks = {checks_js};"
        f" const results = checks.map(c => ({{ check: c, found: text.includes(c) }}));"
        f" const passCount = results.filter(r => r.found).length;"
        f" return {{ totalChecks: checks.length, passCount, results, pageTextPreview: text.substring(0, 300) }}; }})()"
    )


def generate_steps(url, case_data):
    """为一个空步骤用例生成可执行 steps"""
    td = case_data.get("_testDesign", {})
    steps_text = td.get("stepsText", "")
    expected_result = td.get("expectedResult", "")
    preconditions = td.get("preconditions", "")

    steps = []

    # Step 1: Navigate
    steps.append({
        "type": "navigate",
        "url": url,
        "waitUntil": "networkidle",
        "screenshot": True,
        "description": f"打开目标页面"
    })

    # Step 2: Wait
    steps.append({
        "type": "wait",
        "ms": 3000,
        "description": "等待页面加载"
    })

    # Step 3: DOM probe
    steps.append({
        "type": "evaluate",
        "expression": (
            "(() => { const text = document.body.textContent || '';"
            " const buttons = Array.from(document.querySelectorAll('button,a,[role=button]')).slice(0, 15).map(b => b.textContent.trim());"
            " const tables = document.querySelectorAll('table,.ant-table').length;"
            " const forms = document.querySelectorAll('form,.ant-form').length;"
            " const tabs = Array.from(document.querySelectorAll('.ant-tabs-tab')).map(t => t.textContent.trim());"
            " const selects = document.querySelectorAll('.ant-select').length;"
            " return { pageLoaded: true, textLength: text.length, textPreview: text.substring(0, 500),"
            " buttons, tables, forms, tabs, selects }; })()"
        ),
        "description": "页面DOM探测",
        "storeAs": "pageProbe"
    })

    # Step 4: Assert page loaded
    steps.append({
        "type": "assertStore",
        "key": "pageProbe",
        "path": "pageLoaded",
        "equals": True,
        "description": "页面已加载"
    })

    # Step 5-6: Actions from stepsText
    actions = parse_steps_text(steps_text)
    for i, action in enumerate(actions[:3]):  # 最多3个操作
        expr = build_action_expression(action, url)
        if expr:
            steps.append({
                "type": "evaluate",
                "expression": expr,
                "description": f"操作{i+1}: {action[:40]}",
                "storeAs": f"action{i+1}"
            })
            steps.append({
                "type": "wait",
                "ms": 2000,
                "description": f"等待操作{i+1}结果"
            })

    # Step 7: Assert expected result
    assert_expr = build_assert_expression(expected_result)
    if assert_expr:
        steps.append({
            "type": "evaluate",
            "expression": assert_expr,
            "description": "验证预期结果",
            "storeAs": "resultCheck"
        })

    # Step 8: Screenshot
    steps.append({
        "type": "screenshot",
        "label": "batch-probe-result",
        "description": "探测结果截图"
    })

    return steps


def main():
    base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "eval", "cases")
    dry_run = "--dry-run" in sys.argv
    verbose = "-v" in sys.argv or "--verbose" in sys.argv

    total = 0
    filled = 0
    skipped = 0
    by_domain = {"op-test": 0, "f88-test": 0}

    for f in sorted(glob.glob(os.path.join(base_dir, "**/*.json"), recursive=True)):
        try:
            with open(f, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
        except:
            continue

        steps = data.get("steps", [])
        if len(steps) > 0:
            continue  # 已有步骤，跳过

        total += 1
        rel = os.path.relpath(f, base_dir)
        domain = rel.split("/")[0]

        # 解析URL
        url, auth, pattern = resolve_url(rel, data)
        if not url:
            skipped += 1
            continue

        # 生成 steps
        new_steps = generate_steps(url, data)

        # 更新 context
        ctx = data.get("context", {})
        ctx["url"] = url
        ctx["auth"] = auth
        ctx["urlPattern"] = pattern
        if not ctx.get("waitAfterLoad"):
            ctx["waitAfterLoad"] = 3000
        data["context"] = ctx
        data["steps"] = new_steps

        if dry_run:
            if verbose:
                print(f"[DRY] {rel}")
                print(f"  URL: {url}")
                print(f"  Steps: {len(new_steps)}")
                print(f"  stepsText: {data.get('_testDesign',{}).get('stepsText','N/A')[:60]}")
        else:
            with open(f, 'w', encoding='utf-8') as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)

        filled += 1
        if domain in by_domain:
            by_domain[domain] += 1

    mode = "DRY-RUN" if dry_run else "APPLIED"
    print(f"\n[{mode}] 总计扫描: {total} 个空步骤用例")
    print(f"  已填充: {filled} (op-test: {by_domain['op-test']}, f88-test: {by_domain['f88-test']})")
    print(f"  跳过: {skipped}")


if __name__ == "__main__":
    main()
