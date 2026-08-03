#!/usr/bin/env python3
"""
prd_parser.py — PRD 文档解析引擎

从钉钉文档获取 PRD 内容，提取结构化功能点列表。
支持钉钉文档 MCP 获取和本地 Markdown 文件两种输入方式。

用法:
  # 从钉钉文档链接解析
  python scripts/prd_parser.py --url "https://alidocs.dingtalk.com/i/nodes/xxx"

  # 从本地 Markdown 文件解析
  python scripts/prd_parser.py --file prd.md

  # 从标准输入解析
  cat prd.md | python scripts/prd_parser.py --stdin

  # 输出到文件
  python scripts/prd_parser.py --url "xxx" --out artifacts/prd-features.json
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = WORKSPACE / "artifacts"

# ── F88 页面路由映射（用于匹配 PRD 中提到的页面）──
F88_PAGE_ROUTES = {
    "个人任务中心": "/review/personal-task-center",
    "审核标准管理": "/review/standard-management",
    "审核节点管理": "/review/node-management",
    "任务管理": "/review/task-management",
    "任务大厅": "/review/task-management",
    "链路列表": "/strategy/linkList",
    "策略列表": "/strategy/list",
    "生产看板": "/strategy/productionDashboard",
    "数据看板": "/strategy/productionDashboard",
    "模版包管理": "/templateManagement",
    "模板包管理": "/templateManagement",
    "淘内资源池": "/templateLibrary",
    "模版资源池": "/templateLibrary",
    "优质模板库": "/selfTemplateLibrary_f88",
    "优质模版库": "/selfTemplateLibrary_f88",
    "商家管理": "/afdMerchantManagement/shopConfig",
    "店铺信息配置": "/afdMerchantManagement/shopConfig",
}

# ── 功能点关键词提取模式 ──
PRIORITY_PATTERN = re.compile(r'(P[0-3]|紧急|高优|必须|重要)', re.IGNORECASE)
PAGE_PATTERN = re.compile(r'(页面|模块|功能|tab|标签页|入口|弹窗|抽屉|列表|详情|配置)', re.IGNORECASE)
ACTION_PATTERN = re.compile(r'(新增|添加|删除|修改|编辑|优化|调整|重构|支持|兼容|移除|替换|变更|增加|去掉)', re.IGNORECASE)
UI_PATTERN = re.compile(r'(按钮|输入框|下拉|选择|表格|列|筛选|搜索|排序|分页|弹窗|抽屉|标签|图标|文案|提示|toast|modal|drawer|tab)', re.IGNORECASE)
API_PATTERN = re.compile(r'(接口|api|请求|响应|参数|字段|返回|调用|mtop|hsf|http)', re.IGNORECASE)


def extract_prd_id(url_or_file: str) -> str:
    """从 URL 或文件名提取 PRD ID"""
    # 钉钉文档 URL: https://alidocs.dingtalk.com/i/nodes/{uuid}
    m = re.search(r'/nodes/([a-zA-Z0-9]+)', url_or_file)
    if m:
        return m.group(1)[:12]
    # 文件名: prd-xxx.md
    m = re.search(r'prd[_-](\w+)', os.path.basename(url_or_file))
    if m:
        return m.group(1)
    return datetime.now().strftime("%Y%m%d%H%M")


def parse_sections(markdown: str) -> list[dict]:
    """将 Markdown 按标题拆分为段落"""
    sections = []
    current_section = {"title": "", "content": "", "level": 0}

    for line in markdown.split('\n'):
        heading = re.match(r'^(#{1,4})\s+(.+)', line)
        if heading:
            if current_section["content"].strip():
                sections.append(current_section)
            current_section = {
                "title": heading.group(2).strip(),
                "content": "",
                "level": len(heading.group(1))
            }
        else:
            current_section["content"] += line + '\n'

    if current_section["content"].strip():
        sections.append(current_section)

    return sections


def extract_features_from_markdown(markdown: str, prd_id: str) -> dict:
    """
    从 Markdown 格式的 PRD 中提取结构化功能点。
    使用规则匹配（不依赖 LLM），适合标准化的 PRD 格式。
    """
    sections = parse_sections(markdown)
    features = []
    title = ""

    for sec in sections:
        sec_title = sec["title"]
        sec_content = sec["content"]
        sec_full = sec_title + '\n' + sec_content

        # 提取文档标题（第一个 H1）
        if sec["level"] == 1 and not title:
            title = sec_title

        # 检测是否为功能描述段落
        has_action = ACTION_PATTERN.search(sec_title) or ACTION_PATTERN.search(sec_content[:200])
        has_page = PAGE_PATTERN.search(sec_title)
        has_ui = UI_PATTERN.search(sec_content)

        if not (has_action or has_page or has_ui):
            continue

        # 匹配页面路由
        matched_page = ""
        matched_page_name = ""
        for name, route in F88_PAGE_ROUTES.items():
            if name in sec_full:
                matched_page = route
                matched_page_name = name
                break

        # 提取操作变更
        operations = []
        for line in sec_content.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            # 列表项或含操作关键词的行
            if (line.startswith('-') or line.startswith('*') or line.startswith('1.') or
                ACTION_PATTERN.search(line)):
                clean = re.sub(r'^[-*\d.)]+\s*', '', line).strip()
                if clean and len(clean) > 3:
                    operations.append(clean[:100])

        # 提取 UI 变更
        ui_changes = []
        ui_matches = UI_PATTERN.findall(sec_content)
        if ui_matches:
            for line in sec_content.split('\n'):
                if UI_PATTERN.search(line):
                    clean = line.strip().lstrip('-* ').strip()
                    if clean and len(clean) > 5:
                        ui_changes.append(clean[:100])

        # 提取 API 变更
        api_changes = []
        for line in sec_content.split('\n'):
            if API_PATTERN.search(line):
                clean = line.strip().lstrip('-* ').strip()
                if clean and len(clean) > 5:
                    api_changes.append(clean[:100])

        # 推断优先级
        priority_match = PRIORITY_PATTERN.search(sec_title + sec_content[:200])
        priority = "P1"
        if priority_match:
            p = priority_match.group(0).upper()
            if p in ('P0', '紧急', '必须'):
                priority = "P0"
            elif p in ('P1', '高优', '重要'):
                priority = "P1"
            elif p in ('P2',):
                priority = "P2"
            else:
                priority = "P3"

        features.append({
            "page": matched_page,
            "page_name": matched_page_name or sec_title[:20],
            "section_title": sec_title,
            "operations": operations[:10],
            "ui_changes": ui_changes[:10],
            "api_changes": api_changes[:10],
            "test_priority": priority,
            "raw_excerpt": sec_content[:500].strip()
        })

    return {
        "prd_id": prd_id,
        "title": title or "未命名需求",
        "parsed_at": datetime.now().isoformat(),
        "total_sections": len(sections),
        "features": features,
        "feature_count": len(features)
    }


def read_markdown_from_file(filepath: str) -> str:
    """读取本地 Markdown 文件"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()


def read_markdown_from_stdin() -> str:
    """从标准输入读取"""
    return sys.stdin.read()


def main():
    parser = argparse.ArgumentParser(description='PRD 文档解析引擎')
    parser.add_argument('--url', help='钉钉文档链接 URL')
    parser.add_argument('--file', help='本地 Markdown 文件路径')
    parser.add_argument('--stdin', action='store_true', help='从标准输入读取')
    parser.add_argument('--out', help='输出 JSON 文件路径')
    parser.add_argument('--prd-id', help='手动指定 PRD ID')
    args = parser.parse_args()

    markdown = ""
    source = ""

    if args.url:
        # 钉钉文档需要通过 MCP 获取，这里提示用户
        print(f"[prd_parser] 钉钉文档链接: {args.url}", file=sys.stderr)
        print(f"[prd_parser] 请先通过钉钉文档 MCP 获取内容，或使用 --file 参数", file=sys.stderr)

        # 尝试通过 HTTP 获取（备用方案）
        try:
            import urllib.request
            req = urllib.request.Request(args.url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                markdown = resp.read().decode('utf-8')
                source = args.url
        except Exception as e:
            print(f"[prd_parser] HTTP 获取失败: {e}", file=sys.stderr)
            print(f"[prd_parser] 请使用钉钉文档 MCP 的 get_document_content 工具获取内容后传入 --stdin", file=sys.stderr)
            sys.exit(1)

    elif args.file:
        markdown = read_markdown_from_file(args.file)
        source = args.file

    elif args.stdin:
        markdown = read_markdown_from_stdin()
        source = "stdin"

    else:
        parser.print_help()
        sys.exit(1)

    if not markdown.strip():
        print("[prd_parser] 错误: 内容为空", file=sys.stderr)
        sys.exit(1)

    prd_id = args.prd_id or extract_prd_id(source)
    print(f"[prd_parser] 解析 PRD: {prd_id} (来源: {source})", file=sys.stderr)

    result = extract_features_from_markdown(markdown, prd_id)

    output = json.dumps(result, ensure_ascii=False, indent=2)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding='utf-8')
        print(f"[prd_parser] 已写入: {args.out}", file=sys.stderr)
    else:
        print(output)

    print(f"[prd_parser] 解析完成: {result['feature_count']} 个功能点", file=sys.stderr)


if __name__ == "__main__":
    main()
