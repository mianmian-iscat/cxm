#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
batch_pre_recharge.py — 原创保护 PRE 初审数据批量构造脚本

用途：
  在预发环境为指定商家批量构造初审（PRE）专利申请记录。支持：
  1. 批量 seller_id 输入（文件或命令行列表）
  2. 自动检测商家剩余服务次数
  3. 次数不足时提供「HSF 直充 → 半自动 UI 充值 → 纯人工」三级降级
  4. 通过浏览器 CDP 执行 MTOP API（必须走 lib.mtop.request，否则签名失败）
  5. 构造完成后 DB 验证并输出 cases.json 片段供 att-tf 上报

使用方式：
  # 10 条 PRE 数据（同一商家）
  python3 scripts/batch_pre_recharge.py \
    --seller 2213249110271 --count 10 \
    --cdp-port 9223 --verify-db

  # 多商家批量（JSON 文件）
  python3 scripts/batch_pre_recharge.py \
    --seller-file sellers.json --verify-db

  # 演练模式：不实际调用 MTOP，只输出执行计划
  python3 scripts/batch_pre_recharge.py --seller 2213249110271 --count 3 --dry-run

  # 仅充值指定次数（不构造数据）
  python3 scripts/batch_pre_recharge.py --seller 2213249110271 --recharge 10

退出码：
  0 — 全部成功
  1 — 参数/环境错误
  2 — 部分成功（见输出 summary）
  3 — 全部失败
"""

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Any, Optional


# ---------- 默认常量 ----------
DEFAULT_CDP_PORT = 9223
DEFAULT_SELLER_ID = 2213249110271
DEFAULT_IMG_URL = (
    "https://industry-image.oss-cn-zhangjiakou.aliyuncs.com/yc/temp/"
    "dc6cb247-7580-4a49-8b88-ca672d70749a.png"
)
DB_GROUP = "scenario"
DB_NAME = "prod"

# 服务市场商品，0.1 元/次；用于 UI 充值兜底
SERVICE_MARKET_ITEM = "FW_GOODS-1001291504"
RECHARGE_PAGE = "https://pre-fsyc.taobao.com/"

# PRE 字段模板
PRE_PAYLOAD_TEMPLATE = {
    "saveOrApply": "apply",
    "applyType": "PRE",
    "category": "服装",
    "productName": "QA测试初审_{suffix}",
    "productUsage": "用于日常穿着外套",
    "remark": "独特的剪裁设计结合经典元素，体现现代解构主义风格",
    "designers": [{
        "name": "测试设计师_{suffix}",
        "identityNumber": "330102199001011234",
        "nationality": "中国",
        "identityPictures": [DEFAULT_IMG_URL, DEFAULT_IMG_URL],
    }],
    "contacts": [{
        "name": "测试联系人",
        "address": "",
        "zipCode": "",
        "phone": "13800138000",
        "email": "",
    }],
    "designElements": ["A"],
    "designViews": ["A", "B"],
    "productImg": [
        {"type": "立体图", "urls": [DEFAULT_IMG_URL]},
        {"type": "主视图", "urls": [DEFAULT_IMG_URL]},
    ],
    "expectedOnshelfDate": "{onshelf_date}",
}


# ---------- 数据结构 ----------
@dataclass
class SellerTask:
    seller_id: str
    requested_count: int = 1
    created: list[str] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)
    recharged: int = 0
    skipped: int = 0
    remain_before: Optional[int] = None
    remain_after: Optional[int] = None


class CDPError(RuntimeError):
    pass


# ---------- CDP 工具 ----------
def discover_cdp_port(preferred: int = DEFAULT_CDP_PORT) -> int:
    """探测可用 CDP 端口，优先 9223-9230。"""
    for port in range(preferred, preferred + 8):
        try:
            urllib.request.urlopen(f"http://localhost:{port}/json", timeout=1).read()
            return port
        except urllib.error.URLError:
            continue
    raise CDPError(
        f"未找到可用 CDP 端口（尝试 {preferred}-{preferred + 7}）。"
        "请先启动 Chrome：chrome --remote-debugging-port=9223 --user-data-dir=~/.chrome-debug-9223"
    )


def list_cdp_tabs(port: int) -> list[dict]:
    with urllib.request.urlopen(f"http://localhost:{port}/json", timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def find_or_create_tab(port: int, url: str) -> str:
    """返回目标 URL 的 tab 的 webSocketDebuggerUrl；不存在则创建新标签。"""
    tabs = list_cdp_tabs(port)
    for tab in tabs:
        if tab.get("type") == "page" and url in (tab.get("url") or ""):
            return tab["webSocketDebuggerUrl"]

    # 创建新标签并导航
    create_url = f"http://localhost:{port}/json/new?{urllib.parse.quote(url, safe='')}" if False else f"http://localhost:{port}/json/new"
    req = urllib.request.Request(create_url, method="PUT")
    with urllib.request.urlopen(req, timeout=5) as resp:
        new_tab = json.loads(resp.read().decode("utf-8"))
    ws_url = new_tab.get("webSocketDebuggerUrl")
    if not ws_url:
        raise CDPError(f"创建新标签失败: {new_tab}")
    # 导航到目标 URL
    cdp_send(ws_url, "Page.navigate", {"url": url})
    time.sleep(2)
    return ws_url


def cdp_send(ws_url: str, method: str, params: Optional[dict] = None) -> dict:
    """通过 WebSocket 发送 CDP 命令。依赖 websocket-client 库。"""
    try:
        import websocket
    except ImportError as exc:
        raise CDPError(
            "缺少 websocket-client 库，请执行: pip install websocket-client"
        ) from exc

    ws = websocket.create_connection(ws_url, timeout=30)
    try:
        payload = {"id": int(time.time() * 1000), "method": method, "params": params or {}}
        ws.send(json.dumps(payload))
        # 简单循环等待对应 id 的结果
        while True:
            raw = ws.recv()
            msg = json.loads(raw)
            if msg.get("id") == payload["id"]:
                if "error" in msg:
                    raise CDPError(f"CDP {method} 失败: {msg['error']}")
                return msg.get("result", {})
    finally:
        ws.close()


def cdp_evaluate(ws_url: str, expression: str, await_promise: bool = True, user_gesture: bool = False) -> dict:
    """在目标 tab 中执行 JS 表达式，返回 Runtime.evaluate 结果。"""
    params = {
        "expression": expression,
        "returnByValue": True,
        "awaitPromise": await_promise,
        "userGesture": user_gesture,
    }
    result = cdp_send(ws_url, "Runtime.evaluate", params)
    return result.get("result", {})


# ---------- MTOP 调用封装 ----------
def mtop_request(ws_url: str, api: str, version: str, method: str, data: dict, timeout_ms: int = 30000) -> dict:
    """
    通过 CDP 在页面上下文调用 window.lib.mtop.request。
    依赖页面已加载 lib.mtop；未加载时会返回明确错误。
    """
    js = f"""
    (function() {{
      return new Promise((resolve, reject) => {{
        if (typeof window.lib === 'undefined' || !window.lib.mtop || !window.lib.mtop.request) {{
          reject({{type: 'LIB_MISSING', message: '页面未加载 lib.mtop，请先登录商家端'}});
          return;
        }}
        const start = Date.now();
        const timer = setTimeout(() => {{
          reject({{type: 'TIMEOUT', message: 'MTOP 请求超过 {timeout_ms}ms 未响应'}});
        }}, {timeout_ms});
        window.lib.mtop.request({{
          api: '{api}',
          v: '{version}',
          method: '{method}',
          data: {json.dumps(data, ensure_ascii=False)}
        }}, function(res) {{
          clearTimeout(timer);
          resolve({{type: 'SUCCESS', elapsed: Date.now() - start, data: res}});
        }}, function(err) {{
          clearTimeout(timer);
          resolve({{type: 'ERROR', elapsed: Date.now() - start, data: err}});
        }});
      }});
    }})();
    """
    value = cdp_evaluate(ws_url, js, await_promise=True)
    if value.get("type") not in ("string", "object") or value.get("value") is None:
        raise CDPError(f"MTOP {api} 返回异常: {value}")
    return value.get("value", {})


def get_service_count(ws_url: str) -> int:
    """查询商家剩余服务次数。QUICK 不消耗，PRE 消耗 1 次/条。"""
    res = mtop_request(ws_url, "taobao.industry.yc.common.statistics", "1.0", "GET", {})
    if res.get("type") != "SUCCESS":
        raise CDPError(f"查询服务次数失败: {res}")
    data = res.get("data", {}).get("data", {})
    # 兼容两种返回结构
    count = data.get("remainRightCount") if isinstance(data, dict) else None
    if count is None:
        count = res.get("data", {}).get("remainRightCount")
    try:
        return int(count) if count is not None else 0
    except (TypeError, ValueError):
        raise CDPError(f"无法解析 remainRightCount: {count}")


def create_pre_apply(ws_url: str, seller_id: str, suffix: str, onshelf_date: str, product_name: Optional[str] = None) -> str:
    """创建一条 PRE 申请，返回 apply_id（data.result）。"""
    payload = json.loads(json.dumps(PRE_PAYLOAD_TEMPLATE))
    payload["productName"] = product_name or f"QA测试初审_{suffix}"
    payload["designers"][0]["name"] = f"测试设计师_{suffix}"
    payload["expectedOnshelfDate"] = onshelf_date

    res = mtop_request(
        ws_url,
        "taobao.industry.yc.right.apply",
        "1.0",
        "POST",
        {"request": json.dumps(payload, ensure_ascii=False)},
    )

    if res.get("type") != "SUCCESS":
        err = res.get("data", {})
        raise CDPError(f"创建 PRE 失败: {err}")

    data = res.get("data", {})
    ret = data.get("ret", [])
    if not any("SUCCESS" in str(r) for r in ret):
        raise CDPError(f"MTOP 返回失败: {ret}")

    apply_id = data.get("data", {}).get("result") if isinstance(data.get("data"), dict) else None
    if apply_id is None:
        apply_id = data.get("result")
    if not apply_id:
        raise CDPError(f"创建成功但未返回 apply_id，响应: {data}")
    return str(apply_id)


# ---------- 充值流程 ----------
def recharge_via_hsf(seller_id: str, count: int) -> bool:
    """
    通过 HSF Tool 直接增加服务次数（如果配置可用）。
    TODO: 根据实际 HSF 接口填写 method/params；当前默认返回 False 走 UI 兜底。
    """
    # 示例占位：若团队提供 SellerToolService 增加次数接口，可在此实现
    # cmd = ["a1", "hsf", "invoke", "taobao-yc-serverless", "SellerToolService",
    #        "addServiceCount", f"--sellerId={seller_id}", f"--count={count}"]
    # subprocess.run(cmd, check=True, capture_output=True, text=True)
    return False


def recharge_via_ui(ws_url: str, seller_id: str, count: int, dry_run: bool = False) -> bool:
    """
    半自动 UI 充值：脚本打开充值页面并输出操作指引，用户完成订单创建后，
    脚本调用 order.pay API 获取支付二维码链接。
    返回 True 表示用户确认已完成充值；False 表示跳过。
    """
    print(f"\n[recharge] seller={seller_id} 需要充值 {count} 次服务次数")
    if dry_run:
        print("[dry-run] 将执行：打开充值页面 → 输出指引 → 调用 order.pay 获取二维码")
        return True

    # 确保页面在商家端
    cdp_send(ws_url, "Page.navigate", {"url": RECHARGE_PAGE})
    time.sleep(2)

    print(
        "请按以下步骤操作：\n"
        "1. 在页面左侧面板确认剩余服务次数；\n"
        "2. 点击「去充值」→ 选择规格 → 立即购买 → 勾选协议 → 同意并付款；\n"
        "3. 在订单确认页停止，复制 URL 中的 orderId 参数；\n"
        "4. 回到终端，粘贴 orderId。"
    )
    order_id = input("请输入 orderId（或直接回车跳过本次充值）: ").strip()
    if not order_id:
        print("[recharge] 用户跳过充值")
        return False

    try:
        res = mtop_request(
            ws_url,
            "mtop.alibaba.topservice.order.pay",
            "1.0",
            "POST",
            {
                "orderId": order_id,
                "payType": "aliPay",
                "callBackUrl": "//pre-fuwu.taobao.com/serv/new_order_callback.htm",
            },
            timeout_ms=20000,
        )
        if res.get("type") != "SUCCESS":
            print(f"[recharge] 获取支付链接失败: {res}")
            return False
        pay_url = res.get("data", {}).get("returnData")
        print(f"[recharge] 支付网关 URL: {pay_url}")
        print("请扫码支付，完成后按回车继续...")
        input()
        return True
    except CDPError as exc:
        print(f"[recharge] 充值异常: {exc}")
        return False


def ensure_service_count(ws_url: str, seller_id: str, need: int, dry_run: bool = False,
                         auto_recharge: bool = False, manual_ok: bool = False) -> bool:
    """确保商家剩余服务次数 >= need，返回是否足够。"""
    remain = get_service_count(ws_url)
    print(f"[count] seller={seller_id} 当前剩余服务次数: {remain}，需要: {need}")
    if remain >= need:
        return True

    gap = need - remain
    if dry_run:
        print(f"[dry-run] 将尝试为 seller={seller_id} 补充 {gap} 次服务次数")
        return True

    # 优先级 1：HSF 直充（需团队提供接口）
    if auto_recharge and recharge_via_hsf(seller_id, gap):
        print(f"[recharge] HSF 直充成功 {gap} 次")
        return True

    # 优先级 2：半自动 UI 充值
    if manual_ok:
        ok = recharge_via_ui(ws_url, seller_id, gap, dry_run=False)
        if ok:
            # 刷新次数
            remain_after = get_service_count(ws_url)
            print(f"[count] 充值后剩余次数: {remain_after}")
            return remain_after >= need
        return False

    print(
        f"[recharge] 次数不足且未开启充值（--manual-recharge）。"
        f"缺口 {gap} 次，请手动充值后重试。"
    )
    return False


# ---------- DB 验证 ----------
def verify_db(seller_id: str, expected_apply_ids: list[str], timeout: int = 60) -> dict:
    """查询 yc_right_apply 确认记录已创建。"""
    sql = (
        "SELECT id, status, apply_type, apply_time, expected_onshelf_date, product_name "
        f"FROM yc_right_apply WHERE seller_id = {seller_id} AND apply_type = 'PRE' "
        "ORDER BY id DESC LIMIT 50"
    )
    cmd = ["dms-alibaba", "sql", "query", DB_GROUP, "--db", DB_NAME, "--sql", sql]

    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
            stdout = result.stdout.strip()
            if not stdout:
                time.sleep(3)
                continue
            data = json.loads(stdout.splitlines()[-1])
            if not data.get("success"):
                time.sleep(3)
                continue
            rows = data.get("rows", [])
            found = [str(r.get("id")) for r in rows]
            missing = [aid for aid in expected_apply_ids if aid not in found]
            if not missing:
                return {"ok": True, "found": found, "rows": rows[:len(expected_apply_ids)]}
            last_error = f"等待中，缺失: {missing}"
            time.sleep(3)
        except Exception as exc:
            last_error = str(exc)
            time.sleep(3)

    return {"ok": False, "error": last_error or "DB 验证超时"}


# ---------- 批量任务 ----------
def load_seller_tasks(args) -> list[SellerTask]:
    if args.seller_file:
        with open(args.seller_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 支持 ["id1", "id2"] 或 [{"seller_id": "...", "count": N}]
        tasks = []
        for item in data:
            if isinstance(item, dict):
                tasks.append(SellerTask(seller_id=str(item["seller_id"]), requested_count=int(item.get("count", 1))))
            else:
                tasks.append(SellerTask(seller_id=str(item), requested_count=args.count))
        return tasks

    if args.seller:
        sellers = [s.strip() for s in str(args.seller).split(",") if s.strip()]
        return [SellerTask(seller_id=s, requested_count=args.count) for s in sellers]

    raise ValueError("必须指定 --seller 或 --seller-file")


def build_onshelf_date(days_offset: int = 7) -> str:
    return (datetime.now() + timedelta(days=days_offset)).strftime("%Y-%m-%d")


def run_batch(args) -> int:
    tasks = load_seller_tasks(args)
    if not tasks:
        print("[error] 没有有效的 seller_id")
        return 1

    total_requested = sum(t.requested_count for t in tasks)
    print(f"[batch] 共 {len(tasks)} 个商家，计划构造 {total_requested} 条 PRE 数据")

    if args.dry_run:
        print("[dry-run] 不实际调用 MTOP/DB，仅输出执行计划")
        for t in tasks:
            print(f"  seller={t.seller_id} count={t.requested_count}")
        return 0

    port = args.cdp_port or discover_cdp_port()
    print(f"[cdp] 使用端口 {port}")

    # 找或创建一个已登录商家端的 tab
    ws_url = find_or_create_tab(port, RECHARGE_PAGE)
    print(f"[cdp] 已连接 tab")

    onshelf_date = build_onshelf_date(args.onshelf_days)

    for task in tasks:
        print(f"\n[batch] 开始处理 seller={task.seller_id}，目标 {task.requested_count} 条")
        try:
            task.remain_before = get_service_count(ws_url)
            enough = ensure_service_count(
                ws_url, task.seller_id, task.requested_count,
                dry_run=False,
                auto_recharge=args.auto_recharge,
                manual_ok=args.manual_recharge,
            )
            if not enough:
                task.failed.append({"reason": "服务次数不足且充值失败/被跳过"})
                continue

            for i in range(task.requested_count):
                suffix = f"{datetime.now().strftime('%m%d%H%M%S')}_{i}"
                try:
                    apply_id = create_pre_apply(ws_url, task.seller_id, suffix, onshelf_date)
                    task.created.append(apply_id)
                    print(f"  ✅ [{i+1}/{task.requested_count}] apply_id={apply_id}")
                except CDPError as exc:
                    task.failed.append({"index": i, "reason": str(exc)})
                    print(f"  ❌ [{i+1}/{task.requested_count}] {exc}")
                    # 如果是次数不足，尝试补充后继续
                    if "可用权益数不足" in str(exc) and args.manual_recharge:
                        ok = ensure_service_count(ws_url, task.seller_id, 1, manual_ok=True)
                        if ok:
                            # 重试当前这条
                            try:
                                apply_id = create_pre_apply(ws_url, task.seller_id, suffix, onshelf_date)
                                task.created.append(apply_id)
                                task.failed.pop()
                                print(f"  ✅ retry [{i+1}/{task.requested_count}] apply_id={apply_id}")
                            except CDPError as exc2:
                                task.failed.append({"index": i, "reason": f"retry失败: {exc2}"})

            task.remain_after = get_service_count(ws_url)

            if args.verify_db and task.created:
                print(f"[verify] DB 验证 seller={task.seller_id} ...")
                result = verify_db(task.seller_id, task.created, timeout=args.verify_timeout)
                if result["ok"]:
                    print(f"[verify] ✅ 全部 {len(task.created)} 条已落库")
                else:
                    print(f"[verify] ❌ {result['error']}")
                    task.failed.append({"reason": f"DB验证失败: {result['error']}"})

        except Exception as exc:
            task.failed.append({"reason": f"处理异常: {exc}"})
            print(f"[error] seller={task.seller_id} 处理异常: {exc}")

    # 输出 summary
    summary = {
        "generated_at": datetime.now().isoformat(),
        "tasks": [asdict(t) for t in tasks],
    }
    print("\n" + "=" * 60)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    # 输出 cases.json 片段（供 att-tf 上报）
    cases = []
    for t in tasks:
        for aid in t.created:
            cases.append({
                "caseTitle": f"PRE初审造数_{aid}",
                "description": f"seller={t.seller_id} PRE初审申请构造",
                "status": 1,
                "priority": "P1",
                "groupPath": "原创保护/数据构造/PRE初审",
                "errorMessage": "",
                "execLog": f"onshelf_date={onshelf_date}; apply_id={aid}",
            })
    if cases:
        cases_path = args.output or f"pre_batch_cases_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(cases_path, "w", encoding="utf-8") as f:
            json.dump(cases, f, ensure_ascii=False, indent=2)
        print(f"\n[cases] 已输出 {len(cases)} 条 case 到 {cases_path}")

    total_created = sum(len(t.created) for t in tasks)
    total_failed = sum(len(t.failed) for t in tasks)
    if total_failed == 0:
        return 0
    if total_created == 0:
        return 3
    return 2


# ---------- CLI ----------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="原创保护 PRE 初审数据批量构造脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 同一商家构造 10 条 PRE 数据
  python3 scripts/batch_pre_recharge.py --seller 2213249110271 --count 10 --verify-db

  # 多商家 JSON 文件批量
  python3 scripts/batch_pre_recharge.py --seller-file sellers.json --verify-db

  # 开启半自动 UI 充值兜底
  python3 scripts/batch_pre_recharge.py --seller 2213249110271 --count 10 --manual-recharge --verify-db

  # 演练模式
  python3 scripts/batch_pre_recharge.py --seller 2213249110271 --count 3 --dry-run
        """,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--seller", help="商家 seller_id，支持逗号分隔多个")
    group.add_argument("--seller-file", help="商家列表 JSON 文件路径")
    parser.add_argument("--count", type=int, default=1, help="每个商家构造条数（默认 1）")
    parser.add_argument("--cdp-port", type=int, help=f"CDP 端口（默认自动探测 {DEFAULT_CDP_PORT}-{DEFAULT_CDP_PORT+7}）")
    parser.add_argument("--dry-run", action="store_true", help="演练模式，不实际调用 MTOP/DB")
    parser.add_argument("--verify-db", action="store_true", help="构造后通过 DMS 验证记录落库")
    parser.add_argument("--verify-timeout", type=int, default=60, help="DB 验证超时秒数（默认 60）")
    parser.add_argument("--manual-recharge", action="store_true", help="次数不足时允许半自动 UI 充值兜底")
    parser.add_argument("--auto-recharge", action="store_true", help="尝试 HSF 直充服务次数（需配置接口）")
    parser.add_argument("--onshelf-days", type=int, default=7, help="预计上架日期偏移天数（默认 7）")
    parser.add_argument("--output", help="cases.json 输出路径")
    parser.add_argument("--recharge", type=int, help="仅充值指定次数，不构造数据")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # 仅充值模式
    if args.recharge:
        if not args.seller:
            print("[error] --recharge 必须配合 --seller 使用")
            return 1
        port = args.cdp_port or discover_cdp_port()
        ws_url = find_or_create_tab(port, RECHARGE_PAGE)
        ok = ensure_service_count(
            ws_url, args.seller, args.recharge,
            dry_run=args.dry_run,
            auto_recharge=args.auto_recharge,
            manual_ok=args.manual_recharge,
        )
        return 0 if ok else 2

    try:
        return run_batch(args)
    except CDPError as exc:
        print(f"[fatal] {exc}")
        return 1
    except KeyboardInterrupt:
        print("\n[abort] 用户中断")
        return 130


if __name__ == "__main__":
    sys.exit(main())
