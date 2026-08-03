#!/usr/bin/env python3
"""F88 用例按业务模块智能重组 — 基于 name 字段 + 文件名双重匹配"""
import json, os, shutil, glob, re
from pathlib import Path
from collections import defaultdict

BASE = Path("/Users/caoxuemei/Downloads/web-automation 2/eval/cases/f88-test")

# ── 模块目录 ──
MODULES = ["链路管理", "策略管理", "生产看板", "模版库", "审核管理", "商家管理", "全链路E2E"]
for m in MODULES:
    (BASE / m).mkdir(exist_ok=True)

# ── name 关键词 → 模块 ──
NAME_RULES = [
    (["链路详情", "链路列表", "链路创建", "链路复制", "链路搜索", "链路筛选", "链路试运行", "链路环节"], "链路管理"),
    (["策略详情", "策略列表", "策略创建", "策略复制", "策略筛选", "节点编排", "节点类型", "落库配置", "策略节点"], "策略管理"),
    (["生产看板", "看板", "生产中", "已推送", "未推送", "链路进度"], "生产看板"),
    (["模版包管理", "模版包", "模板包管理", "淘内资源池", "淘内资源", "资源池", "优质模板库", "优质模板", "模板库", "模板匹配", "模板创建", "模板导入", "模板激活", "模板停用"], "模版库"),
    (["任务管理", "任务大厅", "个人任务", "审核详情", "审核标准", "审核节点", "审核操作", "审核任务", "审核管理", "审核通过", "审核驳回", "批量审核", "图片审核", "视频审核", "素材审核", "素材生产"], "审核管理"),
    (["商家管理", "商家信息", "商家配置", "供应商"], "商家管理"),
]

# ── 文件名前缀 → 模块 (fallback) ──
FNAME_RULES = [
    # atomic_f88_ 前缀
    (["atomic_f88_ld-", "atomic_f88_ll-", "atom_cd_", "atom_cl_", "atom_f88_ld_", "atom_f88_ll_"], "链路管理"),
    (["atomic_f88_sd-", "atomic_f88_sl-", "atom_sl_", "atom_sd_", "atom_f88_sl_", "atom_f88_sd_"], "策略管理"),
    (["atomic_f88_pd-", "atom_pd_", "atom_f88_pd_"], "生产看板"),
    (["atomic_f88_tmgmt-", "atomic_f88_tl-", "atomic_f88_qt-", "atom_tpm_", "atom_f88_tpm_", "atom_f88_tl_", "atom_f88_qt_"], "模版库"),
    (["atomic_f88_tm-", "atomic_f88_ptc-", "atomic_f88_std-", "atomic_f88_node-", "atomic_f88_audit-",
      "atom_an_", "atom_as_", "atom_tm_", "atom_ptc_", "atom_f88_an_", "atom_f88_as_", "atom_f88_tm_", "atom_f88_ptc_"], "审核管理"),
    (["atomic_f88_mc-", "atom_mc_", "atom_f88_mc_"], "商家管理"),
    # normal_f88_ / e2e_f88_ / ui_f88_ 前缀
    (["normal_f88_dashboard", "ui_f88_production", "normal_f88_production"], "生产看板"),
    (["normal_f88_template_match", "normal_f88_match_app", "ui_f88_template_mgmt", "ui_f88_create_strategy",
      "normal_f88_template", "ui_f88_template", "ui_f88_quality_template", "ui_f88_create_template",
      "normal_f88_quality_template", "ui_f88_template_library"], "模版库"),
    (["normal_f88_image", "e2e_f88_image", "normal_f88_video", "e2e_f88_video",
      "ui_f88_audit", "normal_f88_audit", "normal_f88_review", "normal_f88_reject",
      "ui_f88_task", "ui_f88_personal", "ui_f88_review",
      "normal_f88_flow", "normal_f88_suite", "normal_f88_priority",
      "ui_f88_sd", "ui_f88_strategy", "ui_f88_create_strategy"], None),  # complex, handle below
    (["normal_f88_merchant", "normal_f88_shop", "ui_f88_merchant"], "商家管理"),
    (["ui_f88_link", "ui_f88_chain"], "链路管理"),
    # smoke / regression / contract / error / boundary / heal
    (["smoke_f88", "regression_f88", "contract_f88", "error_f88", "heal_f88"], None),  # keep in root or decide later
]

# 特殊: 审核相关 e2e/normal/ui 细分
AUDIT_KEYWORDS = ["image", "video", "audit", "review", "reject", "task", "personal", "flow", "suite", "priority", "sd", "strategy", "create"]

def classify_by_name(name: str) -> str | None:
    for keywords, module in NAME_RULES:
        for kw in keywords:
            if kw in name:
                return module
    return None

def classify_by_filename(fname: str) -> str | None:
    for prefixes, module in FNAME_RULES:
        if module is None:
            continue
        for pfx in prefixes:
            if fname.startswith(pfx):
                return module
    return None

def classify_special(fname: str, name: str) -> str:
    """处理需要细分的复杂情况"""
    # ui_f88_strategy* / ui_f88_sd* → 策略管理
    if fname.startswith(("ui_f88_strategy", "ui_f88_sd", "normal_f88_strategy")):
        return "策略管理"
    # ui_f88_create_strategy → 策略管理
    if "create_strategy" in fname:
        return "策略管理"
    # normal_f88_flow / suite / priority → 检查内容
    if any(kw in name for kw in ["审核", "任务", "通过", "驳回", "素材"]):
        return "审核管理"
    if any(kw in name for kw in ["策略", "节点", "链路"]):
        return "策略管理"
    # default: 审核管理 (F88大多数用例都和审核相关)
    if fname.startswith(("normal_f88_image", "e2e_f88_image", "normal_f88_video", "e2e_f88_video",
                          "ui_f88_audit", "normal_f88_audit", "ui_f88_task", "ui_f88_personal",
                          "normal_f88_flow", "normal_f88_suite", "normal_f88_priority",
                          "normal_f88_review", "normal_f88_reject")):
        return "审核管理"
    # boundary / regression / smoke / contract / error → 根据内容分
    if any(kw in name for kw in ["模板", "模版", "素材"]):
        return "模版库"
    if any(kw in name for kw in ["审核", "任务"]):
        return "审核管理"
    return "审核管理"  # default for f88

# ── 执行移动 ──
moved = defaultdict(int)
skipped = []
errors = []

# 获取根目录所有 json 文件
json_files = sorted(glob.glob(str(BASE / "*.json")))
print(f"📁 根目录 json 文件总数: {len(json_files)}")

for fpath in json_files:
    fname = os.path.basename(fpath)
    target = None
    
    # 1. 尝试读 name 字段
    try:
        with open(fpath, 'r') as f:
            data = json.load(f)
        name = data.get("name", "")
        target = classify_by_name(name)
    except Exception as e:
        name = ""
        errors.append(f"读取失败 {fname}: {e}")
    
    # 2. fallback: 文件名匹配
    if not target:
        target = classify_by_filename(fname)
    
    # 3. 复杂情况细分
    if not target:
        target = classify_special(fname, name)
    
    if target:
        dest = BASE / target / fname
        if dest.exists():
            skipped.append(f"已存在: {target}/{fname}")
        else:
            shutil.move(fpath, str(dest))
            moved[target] += 1

# ── 统计 ──
print("\n📊 移动统计:")
for m in MODULES:
    cnt = len(list((BASE / m).rglob("*.json")))
    moved_cnt = moved.get(m, 0)
    print(f"  {m}: 共 {cnt} 条 (本次移入 {moved_cnt} 条)")

if skipped:
    print(f"\n⚠️  跳过(已存在): {len(skipped)} 条")
if errors:
    print(f"\n❌ 错误: {len(errors)} 条")
    for e in errors[:5]:
        print(f"  {e}")

# 检查剩余
remaining = sorted(glob.glob(str(BASE / "*.json")))
print(f"\n📁 根目录剩余: {len(remaining)} 条")
for f in remaining[:10]:
    print(f"  {os.path.basename(f)}")
if len(remaining) > 10:
    print(f"  ... 等共 {len(remaining)} 条")
