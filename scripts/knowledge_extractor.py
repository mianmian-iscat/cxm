#!/usr/bin/env python3
"""
knowledge_extractor.py — 知识沉淀闭环引擎

从失败用例中提取模式，自动写入 knowledge/okf/learnings/。
借鉴 cloth-test-memory 的 Phase 4 (p4-learn) 机制。

设计原则:
  - 同一 pattern 失败 >= 2 次才沉淀（避免偶发错误污染知识库）
  - 提取的知识带 frontmatter，符合 OKF GOVERNANCE 规范
  - 同步更新 knowledge/okf/log.md 变更日志
"""

import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OKF_DIR = PROJECT_ROOT / "knowledge" / "okf"
LEARNINGS_DIR = OKF_DIR / "learnings"
FEATURES_DIR = OKF_DIR / "features"
LOG_FILE = OKF_DIR / "log.md"
BADCASE_DIR = PROJECT_ROOT / "artifacts"

# 反哺闭环：生产问题 feedback-loop inbox
FEEDBACK_ROOT = Path.home() / ".qoderwork" / "feedback-loop" / "inbox"

# 沉淀阈值
MIN_FAILURE_COUNT = 2


def load_badcases(artifacts_dir: Path = None) -> list:
    """从 artifacts/ 目录加载所有 badcase JSON"""
    search_dir = artifacts_dir or BADCASE_DIR
    badcases = []
    if not search_dir.exists():
        return badcases

    for json_file in search_dir.rglob("*.json"):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                # 支持 output.json 格式中的 failures 字段
                failures = data.get("failures", [])
                if isinstance(failures, list):
                    badcases.extend(failures)
                # 支持 badcases 字段
                bc = data.get("badcases", [])
                if isinstance(bc, list):
                    badcases.extend(bc)
        except (json.JSONDecodeError, OSError):
            continue
    return badcases


def classify_failures(badcases: list) -> dict:
    """
    将失败分类为:
    - self_healing: 自愈可修复（DOM 变化、超时）
    - script_fix: 脚本需修复（选择器过时、逻辑错误）
    - real_bug: 真实 Bug（功能异常、数据不一致）
    """
    classified = defaultdict(list)
    for bc in badcases:
        category = bc.get("category", "unknown")
        pattern = bc.get("pattern", bc.get("error_pattern", "unknown"))
        domain = bc.get("domain", "common")
        classified[pattern].append({
            "category": category,
            "domain": domain,
            "description": bc.get("description", bc.get("error", "")),
            "case_id": bc.get("case_id", bc.get("tcId", "")),
            "timestamp": bc.get("timestamp", ""),
        })
    return dict(classified)


def extract_learnings(classified: dict, min_count: int = MIN_FAILURE_COUNT) -> list:
    """从分类后的失败中提取需要沉淀的 learnings"""
    learnings = []
    for pattern, failures in classified.items():
        if len(failures) < min_count:
            continue

        # 提取共性
        domains = set(f["domain"] for f in failures)
        categories = set(f["category"] for f in failures)
        descriptions = [f["description"] for f in failures if f["description"]]

        learning = {
            "pattern": pattern,
            "failure_count": len(failures),
            "domains": list(domains),
            "categories": list(categories),
            "sample_descriptions": descriptions[:3],  # 最多 3 个样本
            "case_ids": [f["case_id"] for f in failures if f["case_id"]],
            "first_seen": min(f["timestamp"] for f in failures if f["timestamp"]) if any(f["timestamp"] for f in failures) else "",
        }
        learnings.append(learning)
    return learnings


def generate_learning_md(learning: dict) -> str:
    """生成符合 OKF GOVERNANCE 规范的 learning concept 文件"""
    pattern = learning["pattern"]
    safe_name = re.sub(r'[^\w\u4e00-\u9fff-]', '-', pattern)[:50]
    domain = learning["domains"][0] if learning["domains"] else "common"

    content = f"""---
title: "{pattern}"
type: learning
domain: {domain}
last_updated: "{datetime.now().strftime('%Y-%m-%d')}"
tags: [{', '.join(learning['categories'][:3])}]
auto_generated: true
failure_count: {learning['failure_count']}
---

# {pattern}

## 失败模式

- **失败次数**: {learning['failure_count']}
- **涉及域**: {', '.join(learning['domains'])}
- **分类**: {', '.join(learning['categories'])}

## 典型描述

"""
    for i, desc in enumerate(learning["sample_descriptions"], 1):
        content += f"{i}. {desc}\n"

    content += f"""
## 关联用例

{', '.join(learning['case_ids'][:5])}

## 建议规避方案

> 此条目由 knowledge_extractor.py 自动生成，请人工确认后补充规避方案。

---
*自动生成时间: {datetime.now().isoformat()}*
"""
    return safe_name, content


def update_log(new_entries: list):
    """更新 knowledge/okf/log.md"""
    if not LOG_FILE.exists():
        return

    today = datetime.now().strftime("%Y-%m-%d")
    log_content = LOG_FILE.read_text(encoding="utf-8")

    new_lines = [f"\n## {today}"]
    for entry in new_entries:
        new_lines.append(f"- [自动沉淀] learnings/{entry} — 失败模式沉淀（≥{MIN_FAILURE_COUNT}次）")

    # 插入到文件头部（第二个 ## 之前）
    lines = log_content.split("\n")
    insert_idx = 0
    for i, line in enumerate(lines):
        if line.startswith("## ") and i > 0:
            insert_idx = i
            break

    if insert_idx > 0:
        lines.insert(insert_idx, "\n".join(new_lines))
    else:
        lines.extend(new_lines)

    LOG_FILE.write_text("\n".join(lines), encoding="utf-8")


# =============================================================================
# 反哺闭环：生产问题 → knowledge/okf/ 知识沉淀
# =============================================================================

def load_feedback_candidates(route: str, status_filter: str = "promoted") -> list:
    """从 feedback-loop inbox/{route}/ 读取指定 status 的候选文件。"""
    route_dir = FEEDBACK_ROOT / route
    if not route_dir.exists() or not route_dir.is_dir():
        return []

    candidates = []
    for fpath in route_dir.glob("*.md"):
        try:
            content = fpath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        # 解析 frontmatter
        fm_match = re.match(r"^---\s*\n(.*?\n)---", content, re.DOTALL)
        if not fm_match:
            continue

        fm_text = fm_match.group(1)
        status_match = re.search(r"^status:\s*(\S+)", fm_text, re.MULTILINE)
        if not status_match or status_match.group(1) != status_filter:
            continue

        # 提取 frontmatter 字段
        fields = {"_file": str(fpath), "_fname": fpath.name}
        for key in ("id", "source", "date", "category", "priority", "related_batch", "affected_node"):
            m = re.search(rf"^{key}:\s*(.+)", fm_text, re.MULTILINE)
            if m:
                fields[key] = m.group(1).strip()

        # 提取 body
        body = re.sub(r"^---\s*\n.*?\n---\s*\n?", "", content, count=1, flags=re.DOTALL)
        fields["_body"] = body.strip()
        candidates.append(fields)

    return candidates


def merge_feedback_patterns(target_dir: Path = None, domain: str = "common") -> dict:
    """将 promoted 的 patterns 候选合并到 knowledge/okf/learnings/ 或 features/。"""
    target = target_dir or LEARNINGS_DIR
    candidates = load_feedback_candidates("patterns", status_filter="promoted")

    if not candidates:
        return {"merged": 0, "candidates": []}

    # 过滤：按 domain 或 affected_node 匹配
    relevant = []
    for c in candidates:
        c_domain = c.get("domain", "")
        c_node = c.get("affected_node", "")
        # 如果候选无 domain 限制，或 domain 匹配，或 node 匹配
        if not c_domain or c_domain == domain or not c_node:
            relevant.append(c)

    if not relevant:
        return {"merged": 0, "candidates": [], "reason": f"no candidates matching domain={domain}"}

    # 为每个候选生成 learning 文件
    merged = []
    for c in relevant:
        cid = c.get("id", "unknown")
        title = c.get("_body", "").split("\n")[0].lstrip("# ").strip() if c.get("_body") else cid
        priority = c.get("priority", "P2")
        batch = c.get("related_batch", "")
        source = c.get("source", "")
        date = c.get("date", "")
        body = c.get("_body", "")

        # 提取知识卡建议
        suggestion_match = re.search(r"## 知识卡建议\s*\n(.*?)(?=\n## |\Z)", body, re.DOTALL)
        suggestion = suggestion_match.group(1).strip() if suggestion_match else body[:300]

        # 生成文件名
        safe_name = re.sub(r'[^\w\u4e00-\u9fff-]', '-', cid)[:50]
        target_file = target / f"{safe_name}.md"

        content = f"""---
title: "{title}"
type: learning
domain: {domain}
last_updated: "{datetime.now().strftime('%Y-%m-%d')}"
tags: [production-feedback, {priority.lower()}]
source: {source}
related_batch: {batch}
promotion_date: {date}
auto_generated: true
---

# {title}

## 来源

- **来源**: {source}
- **关联批次**: {batch}
- **晋升日期**: {date}
- **优先级**: {priority}

## 问题描述

{body[:500]}

## 知识卡建议

{suggestion}

---
*此条目由反哺闭环自动晋升，来源：production feedback inbox*
"""
        target_file.write_text(content, encoding="utf-8")
        merged.append(cid)

    return {"merged": len(merged), "candidates": merged, "domain": domain}


def run(artifacts_dir: str = None, min_count: int = MIN_FAILURE_COUNT, dry_run: bool = False):
    """主执行入口"""
    print(f"[knowledge_extractor] 开始知识沉淀...")
    print(f"  artifacts 目录: {artifacts_dir or BADCASE_DIR}")
    print(f"  沉淀阈值: 失败 ≥ {min_count} 次")

    # 1. 加载 badcases
    badcases = load_badcases(Path(artifacts_dir) if artifacts_dir else None)
    print(f"  发现 {len(badcases)} 条 badcase")
    if not badcases:
        print("  无需沉淀")
        return []

    # 2. 分类
    classified = classify_failures(badcases)
    print(f"  识别 {len(classified)} 种失败模式")

    # 3. 提取 learnings
    learnings = extract_learnings(classified, min_count)
    print(f"  达到沉淀阈值的模式: {len(learnings)} 种")

    if not learnings:
        print("  无需沉淀")
        return []

    # 4. 生成文件
    generated = []
    for learning in learnings:
        safe_name, content = generate_learning_md(learning)
        target_file = LEARNINGS_DIR / f"{safe_name}.md"

        if dry_run:
            print(f"  [DRY-RUN] 将生成: {target_file}")
        else:
            target_file.write_text(content, encoding="utf-8")
            print(f"  ✅ 已生成: {target_file.name}")
        generated.append(safe_name)

    # 5. 更新日志
    if not dry_run and generated:
        update_log(generated)
        print(f"  📝 已更新 log.md")

    # 6. 反哺闭环：合并生产问题知识卡
    if not dry_run:
        print(f"\n[knowledge_extractor] 检查反哺闭环...")
        feedback_result = merge_feedback_patterns()
        if feedback_result.get("merged", 0) > 0:
            print(f"  ✅ 反哺合并: {feedback_result['merged']} 条生产问题模式")
        else:
            print(f"  无反哺候选需要合并")

    print(f"[knowledge_extractor] 完成！沉淀 {len(generated)} 条知识")
    return generated


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="知识沉淀闭环引擎")
    parser.add_argument("--artifacts-dir", help="artifacts 目录路径")
    parser.add_argument("--min-count", type=int, default=MIN_FAILURE_COUNT, help="沉淀阈值")
    parser.add_argument("--dry-run", action="store_true", help="只预览不写入")
    args = parser.parse_args()

    run(artifacts_dir=args.artifacts_dir, min_count=args.min_count, dry_run=args.dry_run)
