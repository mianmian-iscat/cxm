"""
mcp_server.py — 把 web-automation 框架暴露为 MCP Server（Model Context Protocol）

对标：Playwright MCP 2025 (微软官方 Agent 协议),
     Katalon MCP Server (StudioAssist Agent),
     browser-use MCP (Agent framework 标准入口)。

解决的问题：
- 2025 年 Agent 生态的标准协议是 MCP（Anthropic 提出，微软 Playwright 跟进）
- 我们框架的 impl.py 只能通过 CLI 调用，无法被其他 Agent 发现 / 集成
- 暴露为 MCP server 后，Claude / Cursor / Qoder 等 AI Agent 都能直接调用

核心能力：
  1. 标准 JSON-RPC 2.0 over stdio（零外部依赖）
  2. 暴露 4 个 tools：
     - web_auto_run_case     运行单个用例（input JSON）
     - web_auto_list_cases   列出可用用例
     - web_auto_audit_report 取最新框架审计报告
     - web_auto_ai_metrics   取 AI 内核指标聚合
  3. initialize / ping / tools.list / tools.call 全套握手
  4. 所有错误走 JSON-RPC error response（不崩溃）

启动方式：
  python3 core/mcp_server.py

注册到 AI Agent：
  在 Agent 的 mcps 目录下加配置指向该脚本，Agent 启动后自动握手。

注意：
  - stdio 模式，不支持 SSE/HTTP。需要网络暴露另起 fastapi 封装。
  - tools.call 的 web_auto_run_case 会 fork 子进程跑 impl.py（避免阻塞 server）
"""

import json
import os
import subprocess
import sys
import threading
from typing import Any, Dict, List, Optional


# ── 常量 ──

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES_DIR = os.path.join(SKILL_ROOT, "eval", "cases")
AUDIT_LATEST = os.path.join(SKILL_ROOT, "artifacts", "framework-audit", "latest.json")
METRICS_LATEST = os.path.join(SKILL_ROOT, "artifacts", "ai_metrics", "latest_summary.json")

SERVER_NAME = "web-automation"
SERVER_VERSION = "1.0.0"
PROTOCOL_VERSION = "2024-11-05"


# ── Tool 定义 ──

TOOLS = [
    {
        "name": "web_auto_run_case",
        "description": "运行一个 web-automation 用例（input JSON 文件路径），返回执行结果摘要",
        "inputSchema": {
            "type": "object",
            "properties": {
                "case_path": {
                    "type": "string",
                    "description": "用例 JSON 文件绝对路径（在 eval/cases 下）",
                },
                "cdp_url": {
                    "type": "string",
                    "description": "Chrome CDP 地址，默认 http://127.0.0.1:9222",
                },
                "timeout_s": {
                    "type": "integer",
                    "description": "超时秒数，默认 300",
                },
            },
            "required": ["case_path"],
        },
    },
    {
        "name": "web_auto_list_cases",
        "description": "列出 eval/cases 目录下所有可用用例（按 business_type 过滤）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "business_type": {
                    "type": "string",
                    "description": "业务域（f88 / op / 任意子目录名），不传=全部",
                },
                "limit": {
                    "type": "integer",
                    "description": "最多返回数量，默认 100",
                },
            },
        },
    },
    {
        "name": "web_auto_audit_report",
        "description": "取最近一次 framework-audit 报告（7 维度评分）",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "web_auto_ai_metrics",
        "description": "取最近一次 AI 内核指标聚合（自愈成功率 / LLM 裁决 / 知识检索 / 策略链）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "聚合窗口天数，默认 30",
                },
                "business_type": {
                    "type": "string",
                    "description": "业务域过滤（不传=全部）",
                },
            },
        },
    },
]


# ── Tool 实现 ──

def tool_list_cases(args: dict) -> dict:
    biz = args.get("business_type")
    limit = int(args.get("limit") or 100)
    cases = []
    if not os.path.exists(CASES_DIR):
        return {"cases": [], "total": 0}
    for root, _, files in os.walk(CASES_DIR):
        if "_atoms" in root:
            continue
        rel = os.path.relpath(root, CASES_DIR)
        domain = rel.split(os.sep)[0] if rel != "." else "_root"
        if biz and domain != biz:
            continue
        for fn in files:
            if fn.endswith(".json"):
                p = os.path.join(root, fn)
                try:
                    with open(p) as f:
                        meta = json.load(f)
                    cases.append({
                        "path": p,
                        "id": meta.get("id", fn[:-5]),
                        "name": meta.get("name", ""),
                        "priority": meta.get("priority", ""),
                        "domain": domain,
                    })
                except Exception:
                    continue
                if len(cases) >= limit:
                    break
        if len(cases) >= limit:
            break
    return {"cases": cases[:limit], "total": len(cases)}


def tool_run_case(args: dict) -> dict:
    case_path = args.get("case_path")
    if not case_path or not os.path.exists(case_path):
        return {"error": f"case_path 不存在: {case_path}"}
    cdp_url = args.get("cdp_url") or "http://127.0.0.1:9222"
    timeout_s = int(args.get("timeout_s") or 300)
    env = os.environ.copy()
    env["WEB_AUTO_CDP_URL"] = cdp_url
    try:
        r = subprocess.run(
            ["python3", "impl.py", "--input", case_path],
            cwd=SKILL_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=env,
        )
        return {
            "ok": r.returncode == 0,
            "returncode": r.returncode,
            "stdout_tail": r.stdout[-2000:],
            "stderr_tail": r.stderr[-1000:],
        }
    except subprocess.TimeoutExpired:
        return {"error": f"timeout after {timeout_s}s"}
    except Exception as e:
        return {"error": str(e)}


def tool_audit_report(args: dict) -> dict:
    if not os.path.exists(AUDIT_LATEST):
        return {"error": "no audit report yet", "path": AUDIT_LATEST}
    try:
        with open(AUDIT_LATEST) as f:
            return json.load(f)
    except Exception as e:
        return {"error": str(e)}


def tool_ai_metrics(args: dict) -> dict:
    days = int(args.get("days") or 30)
    biz = args.get("business_type")
    # 优先实时聚合
    try:
        sys.path.insert(0, SKILL_ROOT)
        from core.ai_metrics_aggregator import AiMetricsAggregator
        agg = AiMetricsAggregator()
        return agg.aggregate(days=days, business_type=biz, persist_summary=False)
    except Exception as e:
        # 降级到缓存
        if os.path.exists(METRICS_LATEST):
            try:
                with open(METRICS_LATEST) as f:
                    return json.load(f)
            except Exception:
                pass
        return {"error": str(e)}


TOOL_DISPATCH = {
    "web_auto_run_case": tool_run_case,
    "web_auto_list_cases": tool_list_cases,
    "web_auto_audit_report": tool_audit_report,
    "web_auto_ai_metrics": tool_ai_metrics,
}


# ── JSON-RPC 2.0 处理 ──

def handle_request(req: dict) -> dict:
    """处理一条 JSON-RPC 请求，返回 response（或 None 表示 notification）"""
    jrpc = {"jsonrpc": "2.0"}
    req_id = req.get("id")
    if req_id is not None:
        jrpc["id"] = req_id
    method = req.get("method", "")

    try:
        if method == "initialize":
            jrpc["result"] = {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            }
        elif method == "initialized":
            return None  # notification, no response
        elif method == "ping":
            jrpc["result"] = {}
        elif method == "tools/list":
            jrpc["result"] = {"tools": TOOLS}
        elif method == "tools/call":
            params = req.get("params") or {}
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if name not in TOOL_DISPATCH:
                jrpc["error"] = {"code": -32601, "message": f"Unknown tool: {name}"}
                return jrpc
            fn = TOOL_DISPATCH[name]
            result = fn(arguments)
            # MCP tool call 返回格式：content 数组
            jrpc["result"] = {
                "content": [
                    {"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}
                ],
                "isError": isinstance(result, dict) and "error" in result,
            }
        elif method == "notifications/cancelled":
            return None
        else:
            jrpc["error"] = {"code": -32601, "message": f"Method not found: {method}"}
    except Exception as e:
        jrpc["error"] = {"code": -32603, "message": f"Internal error: {e}"}

    return jrpc


def serve_stdio() -> None:
    """stdio 模式主循环：逐行读取 JSON-RPC 请求，逐条返回响应"""
    print(f"[{SERVER_NAME} v{SERVER_VERSION}] MCP server started (stdio)", file=sys.stderr)
    sys.stderr.flush()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {e}"},
            }
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()
            continue
        resp = handle_request(req)
        if resp is None:
            continue  # notification, no response
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    serve_stdio()
