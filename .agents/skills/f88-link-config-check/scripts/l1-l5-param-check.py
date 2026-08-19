#!/usr/bin/env python3
"""
L1 参数双向引用完整性 + L5 跨策略参数流转一致性 检查脚本

三层递进判断逻辑：
  第一层 — 节点类型固有需求（硬规则，无需基线）
  第二层 — 节点内部配置声明（正向/反向兜底）
  第三层 — 同业务链路基线对比（统计偏差告警）

用法：
  python3 l1-l5-param-check.py <LINK_ID> [--baseline] [--json]

  --baseline  同时执行第三层基线对比（拉取同 env 全量链路做参照）
  --json      输出 JSON 格式（默认 Markdown 表格）
"""

import json
import re
import subprocess
import sys
import os
import argparse
from collections import defaultdict
from typing import Any

# ─── 常量 ────────────────────────────────────────────────────────────────────

DMS_CLI = os.path.expanduser("~/dms-alibaba/bin/dms-alibaba")
# 权威来源：F88测试知识库/references/shared/db-connections.md
DB_ALIAS = "rm-lgay0v5lor8396yka"
DB_NAME = "stylespot"

# 第一层硬规则：节点类型 → 必须能拿到的参数
NODE_TYPE_REQUIRED_PARAMS = {
    "approve": {"item_id", "seller_id", "tao_cate"},
    "image_text_upload": {"item_id", "seller_id"},
}

# 参数别名映射（同一业务含义可能有不同命名）
PARAM_ALIASES = {
    "item_id": {"item_id", "itemId", "item_Id"},
    "seller_id": {"seller_id", "sellerId", "seller_Id"},
    "tao_cate": {"tao_cate", "taoCate", "tao_cate_id", "cate_id", "categoryId"},
}


# ─── 数据获取 ─────────────────────────────────────────────────────────────────

def run_sql(sql: str) -> list[dict]:
    """通过 dms-alibaba CLI 执行 SELECT 查询，返回 JSON 列表"""
    cmd = [
        DMS_CLI, "sql", "query", DB_NAME,
        "--db", DB_ALIAS,
        "--sql", sql,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        print(f"[ERROR] SQL 执行失败: {result.stderr.strip()}", file=sys.stderr)
        return []

    raw_output = result.stdout.strip()
    if not raw_output:
        print(f"[ERROR] SQL 返回为空", file=sys.stderr)
        return []

    # dms-alibaba 可能在 JSON 前输出 WARN / INFO 行，需提取 JSON 部分
    json_start = -1
    for i, ch in enumerate(raw_output):
        if ch in ('[', '{'):
            json_start = i
            break

    if json_start < 0:
        print(f"[ERROR] 返回结果中未找到 JSON: {raw_output[:200]}", file=sys.stderr)
        return []

    json_str = raw_output[json_start:]

    # ── 策略 1：直接解析完整 JSON（dms-alibaba wrapper 格式） ──
    try:
        data = json.loads(json_str)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # dms-alibaba 返回 {"success":true, "rows":[...], ...}
            if "rows" in data:
                rows = data["rows"]
                if not data.get("success", True):
                    print(f"[ERROR] SQL 返回 success=false: {data.get('message', '')}", file=sys.stderr)
                    return []
                return rows if isinstance(rows, list) else [rows]
            return [data]
    except json.JSONDecodeError:
        pass  # 进入策略 2

    # ── 策略 2：嵌套 JSON 导致解析失败时，用括号计数定位 "rows":[...] ──
    rows_key_pos = json_str.find('"rows"')
    if rows_key_pos >= 0:
        # 找到 "rows" 后面的 [
        bracket_start = json_str.find('[', rows_key_pos + 6)
        if bracket_start >= 0:
            depth = 0
            in_string = False
            escape_next = False
            for i in range(bracket_start, len(json_str)):
                ch = json_str[i]
                if escape_next:
                    escape_next = False
                    continue
                if ch == '\\' and in_string:
                    escape_next = True
                    continue
                if ch == '"' and not escape_next:
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == '[':
                    depth += 1
                elif ch == ']':
                    depth -= 1
                    if depth == 0:
                        rows_str = json_str[bracket_start:i + 1]
                        try:
                            rows_data = json.loads(rows_str)
                            return rows_data if isinstance(rows_data, list) else [rows_data]
                        except json.JSONDecodeError as e:
                            print(f"[ERROR] rows 数组解析失败: {e}", file=sys.stderr)
                        break

    # ── 策略 3：最后兜底——找第一个顶层 JSON 数组 ──
    arr_start = json_str.find('[')
    if arr_start >= 0:
        depth = 0
        in_string = False
        escape_next = False
        for i in range(arr_start, len(json_str)):
            ch = json_str[i]
            if escape_next:
                escape_next = False
                continue
            if ch == '\\' and in_string:
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    arr_str = json_str[arr_start:i + 1]
                    try:
                        arr_data = json.loads(arr_str)
                        return arr_data if isinstance(arr_data, list) else [arr_data]
                    except json.JSONDecodeError as e:
                        print(f"[ERROR] 顶层数组解析失败: {e}", file=sys.stderr)
                    break

    print(f"[ERROR] 所有 JSON 解析策略均失败", file=sys.stderr)
    print(f"[ERROR] 原始输出前 500 字符: {raw_output[:500]}", file=sys.stderr)
    return []


def fetch_link_info(link_id: int) -> dict | None:
    """获取链路基本信息 + struct"""
    sql = f"""
        SELECT id, name, env, life_cycle, submitter_name, gmt_modified, struct
        FROM g_link
        WHERE id = {link_id} AND is_deleted = 0
    """
    rows = run_sql(sql)
    return rows[0] if rows else None


def fetch_strategies(strategy_ids: list[int]) -> list[dict]:
    """批量获取策略 workflow_def"""
    if not strategy_ids:
        return []
    ids_str = ",".join(str(i) for i in strategy_ids)
    sql = f"""
        SELECT id, name, workflow_def
        FROM g_strategy
        WHERE id IN ({ids_str})
    """
    return run_sql(sql)


def fetch_all_prod_strategies() -> list[dict]:
    """获取全量生产策略（基线对比用，数据量大，慎用）"""
    sql = """
        SELECT id, name, workflow_def
        FROM g_strategy
        WHERE is_deleted = 0
    """
    return run_sql(sql)


# ─── 解析 ─────────────────────────────────────────────────────────────────────

def parse_struct(struct_json: str) -> list[dict]:
    """解析 g_link.struct JSON，提取 stages"""
    try:
        struct = json.loads(struct_json) if isinstance(struct_json, str) else struct_json
        return struct.get("stages", [])
    except (json.JSONDecodeError, TypeError):
        return []


def extract_strategy_ids(stage: dict) -> list[int]:
    """从 stage 的 strategys 字段提取整数 ID 列表。
    strategys 可能是 [123, 456] 或 [{"id": 123, ...}, ...] 或混合。
    """
    raw = stage.get("strategys", [])
    ids = []
    for item in raw:
        if isinstance(item, int):
            ids.append(item)
        elif isinstance(item, dict):
            sid = item.get("id") or item.get("strategyId") or item.get("strategy_id")
            if isinstance(sid, int):
                ids.append(sid)
        # 跳过无法识别的项
    return ids


def parse_workflow_def(wf_def_json: str) -> dict:
    """解析 g_strategy.workflow_def JSON"""
    try:
        wf = json.loads(wf_def_json) if isinstance(wf_def_json, str) else wf_def_json
        return wf if isinstance(wf, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def extract_strategy_params(strategy: dict) -> dict:
    """
    从策略中提取参数信息：
    - inputParams: 策略级输入参数列表
    - outputParams: 策略级输出参数列表
    - node_refs: 各节点引用的参数集合（按节点类型分组）
    """
    wf = parse_workflow_def(strategy.get("workflow_def", "{}"))
    inner_nodes = wf.get("innerNodes", [])

    # 策略级参数
    input_params = set()
    for p in wf.get("inputParams", []):
        code = p.get("code", "")
        if code:
            input_params.add(code)

    output_params = set()
    for p in wf.get("outputParams", []):
        code = p.get("code", "")
        if code:
            output_params.add(code)

    # 节点级参数引用（按节点类型分组）
    node_refs = defaultdict(list)  # node_type -> [param_info, ...]
    node_details = []  # 详细节点信息

    for node in inner_nodes:
        node_type = node.get("nodeType", "unknown")
        node_name = node.get("name", "")
        node_uid = node.get("uid", "")

        refs_for_node = []

        # 检查节点自身的 inputParams
        for param in node.get("inputParams", []):
            ds_type = param.get("dataSourceType", "")
            ds_config = param.get("dataSourceConfig", {})
            param_code = param.get("code", "")

            if ds_type == "WORKFLOW_INPUT_PARAM":
                wf_param_code = ds_config.get("workflowInputParamCode", "")
                refs_for_node.append({
                    "param_code": param_code,
                    "source": "WORKFLOW_INPUT_PARAM",
                    "workflowInputParamCode": wf_param_code,
                })
            elif ds_type == "PARENT_NODE":
                parent_field = ds_config.get("fieldCode", "")
                parent_node = ds_config.get("nodeId", "")
                refs_for_node.append({
                    "param_code": param_code,
                    "source": "PARENT_NODE",
                    "parentNodeId": parent_node,
                    "parentFieldCode": parent_field,
                })
            elif ds_type == "STAGE_OUTPUT":
                refs_for_node.append({
                    "param_code": param_code,
                    "source": "STAGE_OUTPUT",
                    "stageUid": ds_config.get("stageUid", ""),
                    "fieldCode": ds_config.get("fieldCode", ""),
                })

        # 检查 llm_text 的 {{variable}} 引用
        if node_type == "llm_text":
            for prompt_field in ["systemPrompt", "userPrompt"]:
                prompt_text = node.get(prompt_field, "")
                if isinstance(prompt_text, str):
                    variables = re.findall(r"\{\{(\w+)\}\}", prompt_text)
                    for var in variables:
                        refs_for_node.append({
                            "param_code": var,
                            "source": "LLM_VARIABLE",
                            "variable": var,
                        })

        node_refs[node_type].extend(refs_for_node)
        node_details.append({
            "node_type": node_type,
            "node_name": node_name,
            "node_uid": node_uid,
            "refs": refs_for_node,
        })

    return {
        "strategy_id": strategy.get("id"),
        "strategy_name": strategy.get("name", ""),
        "inputParams": input_params,
        "outputParams": output_params,
        "node_refs": dict(node_refs),
        "node_details": node_details,
    }


def get_all_referenced_params(parsed: dict) -> set[str]:
    """获取策略中所有被引用的 WORKFLOW_INPUT_PARAM 参数名"""
    referenced = set()
    for node_type, refs in parsed["node_refs"].items():
        for ref in refs:
            if ref["source"] == "WORKFLOW_INPUT_PARAM":
                wf_code = ref.get("workflowInputParamCode", "")
                if wf_code:
                    referenced.add(wf_code)
    return referenced


def get_node_type_params(parsed: dict, node_type: str) -> set[str]:
    """获取指定节点类型引用的所有 WORKFLOW_INPUT_PARAM 参数"""
    params = set()
    for ref in parsed["node_refs"].get(node_type, []):
        if ref["source"] == "WORKFLOW_INPUT_PARAM":
            wf_code = ref.get("workflowInputParamCode", "")
            if wf_code:
                params.add(wf_code)
    return params


# ─── 别名匹配 ─────────────────────────────────────────────────────────────────

def resolve_alias(param_name: str) -> str:
    """将参数名解析为标准化名称（如有别名映射），否则返回原名"""
    for canonical, aliases in PARAM_ALIASES.items():
        if param_name in aliases:
            return canonical
    return param_name


def has_param(param_set: set[str], target: str) -> bool:
    """检查参数集合中是否包含目标参数（含别名匹配）"""
    canonical = resolve_alias(target)
    aliases = PARAM_ALIASES.get(canonical, {target})
    return bool(param_set & aliases)


# ─── 第一层：节点类型固有需求 ──────────────────────────────────────────────────

def check_layer1_node_type(parsed: dict) -> list[dict]:
    """
    第一层：硬规则
    approve 节点必须能拿到 item_id / seller_id / tao_cate
    image_text_upload 节点必须能拿到 item_id / seller_id
    """
    findings = []

    for node_type, required_params in NODE_TYPE_REQUIRED_PARAMS.items():
        # 该策略是否有此类型节点
        node_details = [n for n in parsed["node_details"] if n["node_type"] == node_type]
        if not node_details:
            continue  # 没有此类节点，跳过

        # 收集该策略所有能提供给此类节点的参数
        # 来源 1: 策略 inputParams（全局可用）
        # 来源 2: 节点自身 WORKFLOW_INPUT_PARAM 引用
        # 来源 3: PARENT_NODE 输出（上游节点传递）
        available_from_input_params = parsed["inputParams"]
        available_from_node_refs = get_node_type_params(parsed, node_type)
        all_available = available_from_input_params | available_from_node_refs

        for required in required_params:
            if not has_param(all_available, required):
                # 检查是否通过 PARENT_NODE 传递
                parent_refs = [
                    ref for ref in parsed["node_refs"].get(node_type, [])
                    if ref["source"] == "PARENT_NODE"
                ]
                # PARENT_NODE 传递的参数名无法静态确认，标记为告警而非严重
                if parent_refs:
                    findings.append({
                        "layer": 1,
                        "severity": "warn",
                        "node_type": node_type,
                        "missing_param": required,
                        "message": (
                            f"{node_type} 节点未直接引用 `{required}`，"
                            f"但存在 PARENT_NODE 引用，可能通过上游传递（需人工确认）"
                        ),
                    })
                else:
                    findings.append({
                        "layer": 1,
                        "severity": "critical",
                        "node_type": node_type,
                        "missing_param": required,
                        "message": (
                            f"{node_type} 节点必须能拿到 `{required}` "
                            f"（{'审核平台展示+路由刚需' if node_type == 'approve' else '上传关联商品+店铺刚需'}），"
                            f"但策略 inputParams 和节点引用中均未找到"
                        ),
                    })

    return findings


# ─── 第二层：节点内部配置声明 ──────────────────────────────────────────────────

def check_layer2_config_declaration(parsed: dict) -> list[dict]:
    """
    第二层：节点 inputParams 中 dataSourceType=WORKFLOW_INPUT_PARAM 的引用，
    若 workflowInputParamCode 指向的参数在策略 inputParams 中不存在 = 严重
    （此层与正向检查等价，双重兜底）
    """
    findings = []

    for node_detail in parsed["node_details"]:
        for ref in node_detail["refs"]:
            if ref["source"] == "WORKFLOW_INPUT_PARAM":
                wf_code = ref.get("workflowInputParamCode", "")
                if wf_code and not has_param(parsed["inputParams"], wf_code):
                    findings.append({
                        "layer": 2,
                        "severity": "critical",
                        "node_type": node_detail["node_type"],
                        "node_name": node_detail["node_name"],
                        "missing_param": wf_code,
                        "message": (
                            f"节点 `{node_detail['node_name']}` ({node_detail['node_type']}) "
                            f"通过 WORKFLOW_INPUT_PARAM 引用了 `{wf_code}`，"
                            f"但该参数不存在于策略 inputParams 中"
                        ),
                    })

    return findings


# ─── 正向检查（与第二层配合） ──────────────────────────────────────────────────

def check_forward_reference(parsed: dict) -> list[dict]:
    """
    正向检查：任意节点通过 WORKFLOW_INPUT_PARAM 引用某参数时，
    该参数必须存在于策略 inputParams 中
    （与第二层逻辑等价，此处独立输出便于报告分类）
    """
    findings = []
    all_referenced = get_all_referenced_params(parsed)

    for ref_param in all_referenced:
        if not has_param(parsed["inputParams"], ref_param):
            findings.append({
                "layer": "forward",
                "severity": "critical",
                "missing_param": ref_param,
                "message": (
                    f"策略 inputParams 中缺少 `{ref_param}`，"
                    f"但有节点通过 WORKFLOW_INPUT_PARAM 引用了它"
                ),
            })

    return findings


# ─── 第三层：同业务链路基线对比 ────────────────────────────────────────────────

def check_layer3_baseline(current_parsed: dict, baseline_strategies: list[dict]) -> list[dict]:
    """
    第三层：对比同业务场景的其他链路
    若多数链路的某类节点引用了某参数而当前链路未引用 = 告警
    """
    findings = []
    if not baseline_strategies:
        return findings

    # 构建基线：按节点类型统计参数引用频率
    baseline_node_param_count = defaultdict(lambda: defaultdict(int))
    baseline_total = 0

    for strategy in baseline_strategies:
        bp = extract_strategy_params(strategy)
        baseline_total += 1
        for node_type, refs in bp["node_refs"].items():
            for ref in refs:
                if ref["source"] == "WORKFLOW_INPUT_PARAM":
                    wf_code = ref.get("workflowInputParamCode", "")
                    if wf_code:
                        baseline_node_param_count[node_type][wf_code] += 1

    if baseline_total == 0:
        return findings

    # 对比：当前策略的每个节点类型，看哪些参数被多数基线引用但当前未引用
    THRESHOLD = 0.5  # 超过 50% 的基线策略引用了的参数，当前也应有

    for node_type in NODE_TYPE_REQUIRED_PARAMS:
        current_params = get_node_type_params(current_parsed, node_type)
        current_nodes = [n for n in current_parsed["node_details"] if n["node_type"] == node_type]
        if not current_nodes:
            continue

        for param, count in baseline_node_param_count.get(node_type, {}).items():
            ratio = count / baseline_total
            if ratio >= THRESHOLD and not has_param(current_params, param):
                findings.append({
                    "layer": 3,
                    "severity": "warn",
                    "node_type": node_type,
                    "missing_param": param,
                    "baseline_ratio": f"{count}/{baseline_total} ({ratio:.0%})",
                    "message": (
                        f"{node_type} 节点未引用 `{param}`，"
                        f"但 {count}/{baseline_total} ({ratio:.0%}) 的基线策略中"
                        f"同类节点均引用了此参数"
                    ),
                })

    return findings


# ─── L5 跨策略参数流转一致性 ──────────────────────────────────────────────────

def check_l5_cross_strategy(all_parsed: list[dict], stages: list[dict]) -> list[dict]:
    """
    L5 跨策略参数流转一致性
    正向：上游策略 outputParams 声明输出的参数，下游策略通过 STAGE_OUTPUT 引用时必须存在
    反向：上游策略 inputParams 新增必填参数后，下游消费策略是否同步适配
    """
    findings = []
    parsed_map = {p["strategy_id"]: p for p in all_parsed}

    # 构建策略顺序（按 stages 中的排列）
    stage_strategy_order = []
    for stage in stages:
        strategy_ids = extract_strategy_ids(stage)
        stage_strategy_order.append({
            "stage_uid": stage.get("uid", ""),
            "stage_name": stage.get("name", ""),
            "strategy_ids": strategy_ids,
            "inputParams": {p.get("code", "") for p in stage.get("inputParams", [])},
            "outputParams": {p.get("code", "") for p in stage.get("outputParams", [])},
        })

    # 正向检查：跨策略 STAGE_OUTPUT 引用
    for i, stage_info in enumerate(stage_strategy_order):
        for sid in stage_info["strategy_ids"]:
            parsed = parsed_map.get(sid)
            if not parsed:
                continue

            for node_detail in parsed["node_details"]:
                for ref in node_detail["refs"]:
                    if ref["source"] == "STAGE_OUTPUT":
                        ref_stage_uid = ref.get("stageUid", "")
                        ref_field = ref.get("fieldCode", "")

                        # 找到引用的上游阶段
                        upstream_stage = None
                        for s in stage_strategy_order:
                            if s["stage_uid"] == ref_stage_uid:
                                upstream_stage = s
                                break

                        if upstream_stage and ref_field:
                            # 检查上游阶段的 outputParams 是否包含该字段
                            if ref_field not in upstream_stage["outputParams"]:
                                # 也检查上游策略的 outputParams
                                upstream_has_it = False
                                for up_sid in upstream_stage["strategy_ids"]:
                                    up_parsed = parsed_map.get(up_sid)
                                    if up_parsed and ref_field in up_parsed["outputParams"]:
                                        upstream_has_it = True
                                        break

                                if not upstream_has_it:
                                    findings.append({
                                        "check": "L5_forward",
                                        "severity": "critical",
                                        "strategy_id": sid,
                                        "strategy_name": parsed["strategy_name"],
                                        "node_type": node_detail["node_type"],
                                        "missing_param": ref_field,
                                        "message": (
                                            f"策略 `{parsed['strategy_name']}` (ID:{sid}) 的"
                                            f" {node_detail['node_type']} 节点通过 STAGE_OUTPUT "
                                            f"引用了 `{ref_field}`，但上游阶段 "
                                            f"`{upstream_stage['stage_name']}` 的 outputParams "
                                            f"中不存在此参数"
                                        ),
                                    })

    # 反向检查：上游新增必填参数，下游是否同步
    for i in range(len(stage_strategy_order) - 1):
        upstream_stage = stage_strategy_order[i]
        downstream_stages = stage_strategy_order[i + 1:]

        for up_sid in upstream_stage["strategy_ids"]:
            up_parsed = parsed_map.get(up_sid)
            if not up_parsed:
                continue

            # 获取上游策略的 inputParams（作为"需要被消费"的参数集）
            upstream_input = up_parsed["inputParams"]

            for ds_stage in downstream_stages:
                for ds_sid in ds_stage["strategy_ids"]:
                    ds_parsed = parsed_map.get(ds_sid)
                    if not ds_parsed:
                        continue

                    # 检查下游策略中 approve / image_text_upload 节点
                    for node_detail in ds_parsed["node_details"]:
                        if node_detail["node_type"] not in NODE_TYPE_REQUIRED_PARAMS:
                            continue

                        required = NODE_TYPE_REQUIRED_PARAMS[node_detail["node_type"]]
                        for req_param in required:
                            if has_param(upstream_input, req_param):
                                # 上游有这个参数，检查下游是否引用
                                ds_node_params = set()
                                for ref in node_detail["refs"]:
                                    if ref["source"] == "WORKFLOW_INPUT_PARAM":
                                        ds_node_params.add(ref.get("workflowInputParamCode", ""))

                                if not has_param(ds_node_params, req_param) and \
                                   not has_param(ds_parsed["inputParams"], req_param):
                                    findings.append({
                                        "check": "L5_reverse",
                                        "severity": "critical",
                                        "upstream_strategy_id": up_sid,
                                        "upstream_strategy_name": up_parsed["strategy_name"],
                                        "downstream_strategy_id": ds_sid,
                                        "downstream_strategy_name": ds_parsed["strategy_name"],
                                        "node_type": node_detail["node_type"],
                                        "missing_param": req_param,
                                        "message": (
                                            f"上游策略 `{up_parsed['strategy_name']}` (ID:{up_sid}) "
                                            f"的 inputParams 包含 `{req_param}`，"
                                            f"但下游策略 `{ds_parsed['strategy_name']}` (ID:{ds_sid}) "
                                            f"的 {node_detail['node_type']} 节点未引用此参数。"
                                            f"（首图多选多策略新增 item_id 但审批未同步 同类问题）"
                                        ),
                                    })

    return findings


# ─── 报告输出 ─────────────────────────────────────────────────────────────────

def format_findings_md(findings: list[dict], link_info: dict) -> str:
    """格式化为 Markdown 表格"""
    lines = []
    link_id = link_info.get("id", "?")
    link_name = link_info.get("name", "?")

    lines.append(f"## L1/L5 参数引用完整性检查报告")
    lines.append(f"")
    lines.append(f"**链路**: {link_name} (ID: {link_id})")
    lines.append(f"**环境**: {link_info.get('env', '?')} | **生命周期**: {link_info.get('life_cycle', '?')}")
    lines.append(f"")

    if not findings:
        lines.append("✅ **全部通过** — 未发现参数引用异常")
        return "\n".join(lines)

    # 按严重度排序
    severity_order = {"critical": 0, "warn": 1, "info": 2}
    findings.sort(key=lambda f: severity_order.get(f.get("severity", "info"), 9))

    critical_count = sum(1 for f in findings if f.get("severity") == "critical")
    warn_count = sum(1 for f in findings if f.get("severity") == "warn")

    lines.append(f"**发现 {len(findings)} 项问题**: ❌ 严重 {critical_count} / ⚠️ 告警 {warn_count}")
    lines.append("")

    # 分层展示
    layer_names = {
        1: "第一层 — 节点类型固有需求（硬规则）",
        2: "第二层 — 节点内部配置声明",
        "forward": "正向检查 — WORKFLOW_INPUT_PARAM 引用验证",
        3: "第三层 — 同业务链路基线对比",
        "L5_forward": "L5 正向 — 跨策略 STAGE_OUTPUT 引用",
        "L5_reverse": "L5 反向 — 跨策略参数同步",
    }

    grouped = defaultdict(list)
    for f in findings:
        grouped[f.get("layer", f.get("check", "unknown"))].append(f)

    for layer_key in [1, 2, "forward", 3, "L5_forward", "L5_reverse"]:
        layer_findings = grouped.get(layer_key, [])
        if not layer_findings:
            continue

        layer_label = layer_names.get(layer_key, str(layer_key))
        lines.append(f"### {layer_label}")
        lines.append("")
        lines.append("| 状态 | 节点类型 | 缺失参数 | 说明 |")
        lines.append("|------|----------|----------|------|")

        for f in layer_findings:
            icon = "❌" if f.get("severity") == "critical" else "⚠️"
            node_type = f.get("node_type", "-")
            param = f"`{f.get('missing_param', '?')}`"
            msg = f.get("message", "")
            extra = ""
            if "baseline_ratio" in f:
                extra = f" (基线: {f['baseline_ratio']})"
            lines.append(f"| {icon} | {node_type} | {param} | {msg}{extra} |")

        lines.append("")

    # 修复建议
    lines.append("### 修复优先级")
    lines.append("")
    critical_findings = [f for f in findings if f.get("severity") == "critical"]
    if critical_findings:
        lines.append("**P0 — 立即修复**:")
        for f in critical_findings:
            param = f.get("missing_param", "?")
            node_type = f.get("node_type", "?")
            layer = f.get("layer", f.get("check", ""))
            if layer in (1, "L5_reverse"):
                lines.append(
                    f"- 在 {node_type} 节点的 inputParams 中补充 `{param}` 引用，"
                    f"dataSourceType=WORKFLOW_INPUT_PARAM，workflowInputParamCode={param}"
                )
            elif layer == 2 or layer == "forward":
                lines.append(
                    f"- 在策略 inputParams 中添加 `{param}`，"
                    f"或修正节点引用指向正确的参数名"
                )
            elif layer == "L5_forward":
                lines.append(
                    f"- 检查上游阶段 outputParams 是否遗漏 `{param}` 的声明，"
                    f"或修正下游 STAGE_OUTPUT 引用"
                )
            else:
                lines.append(f"- {f.get('message', '')}")
        lines.append("")

    warn_findings = [f for f in findings if f.get("severity") == "warn"]
    if warn_findings:
        lines.append("**P1 — 人工确认**:")
        for f in warn_findings:
            param = f.get("missing_param", "?")
            node_type = f.get("node_type", "?")
            layer = f.get("layer", "")
            if layer == 1:
                lines.append(
                    f"- 确认 {node_type} 节点是否通过 PARENT_NODE 间接获取了 `{param}`，"
                    f"若是则忽略，否则建议补充引用"
                )
            elif layer == 3:
                lines.append(
                    f"- {node_type} 节点未引用 `{param}`（基线多数策略均有引用），"
                    f"确认是有意省略还是漏配"
                )
            else:
                lines.append(f"- {f.get('message', '')}")

    return "\n".join(lines)


def format_findings_json(findings: list[dict], link_info: dict) -> str:
    """输出 JSON 格式"""
    result = {
        "link_id": link_info.get("id"),
        "link_name": link_info.get("name"),
        "env": link_info.get("env"),
        "life_cycle": link_info.get("life_cycle"),
        "total_findings": len(findings),
        "critical": sum(1 for f in findings if f.get("severity") == "critical"),
        "warn": sum(1 for f in findings if f.get("severity") == "warn"),
        "findings": findings,
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


# ─── 主流程 ───────────────────────────────────────────────────────────────────

def run_self_test(test_link_id: int) -> bool:
    """
    自检模式：对已知链路执行完整检查流程，验证脚本各模块工作正常。
    返回 True 表示自检通过，False 表示存在问题。
    """
    print("=" * 60, file=sys.stderr)
    print("🔍 自检模式启动", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    errors = []
    warnings = []

    # ─── 检查 1: CLI 可用性 ──────────────────────────────────────────────
    print("\n[1/6] 检查 dms-alibaba CLI...", file=sys.stderr)
    if not os.path.isfile(DMS_CLI):
        errors.append(f"CLI 不存在: {DMS_CLI}")
    elif not os.access(DMS_CLI, os.X_OK):
        errors.append(f"CLI 不可执行: {DMS_CLI}")
    else:
        print("  ✅ CLI 存在且可执行", file=sys.stderr)

    # ─── 检查 2: 数据库连接 + 链路查询 ─────────────────────────────────────
    print(f"\n[2/6] 查询测试链路 {test_link_id}...", file=sys.stderr)
    link_info = fetch_link_info(test_link_id)
    if not link_info:
        errors.append(f"链路 {test_link_id} 查询失败或不存在")
        print(f"  ❌ 查询失败", file=sys.stderr)
    else:
        print(f"  ✅ 获取到链路: {link_info.get('name', '?')} (env={link_info.get('env', '?')})", file=sys.stderr)

    # ─── 检查 3: struct 解析 ──────────────────────────────────────────────
    print("\n[3/6] 解析 struct JSON...", file=sys.stderr)
    if link_info:
        stages = parse_struct(link_info.get("struct", "{}"))
        if not stages:
            errors.append("struct 解析失败或无 stages")
            print("  ❌ 解析失败", file=sys.stderr)
        else:
            strategy_ids = []
            for stage in stages:
                strategy_ids.extend(extract_strategy_ids(stage))
            strategy_ids = list(set(strategy_ids))
            print(f"  ✅ 解析成功: {len(stages)} 个阶段, {len(strategy_ids)} 个策略", file=sys.stderr)

            # ─── 检查 4: 策略查询 + 解析 ──────────────────────────────────
            print(f"\n[4/6] 查询并解析 {len(strategy_ids)} 个策略...", file=sys.stderr)
            strategies = fetch_strategies(strategy_ids)
            if not strategies:
                errors.append("策略查询失败")
                print("  ❌ 查询失败", file=sys.stderr)
            else:
                print(f"  ✅ 获取到 {len(strategies)} 个策略", file=sys.stderr)

                all_parsed = []
                for s in strategies:
                    parsed = extract_strategy_params(s)
                    all_parsed.append(parsed)

                total_nodes = sum(len(p["node_details"]) for p in all_parsed)
                print(f"  ✅ 共解析 {total_nodes} 个节点", file=sys.stderr)

                # ─── 检查 5: 各检查函数执行 ──────────────────────────────────
                print("\n[5/6] 执行各检查函数...", file=sys.stderr)

                # 第一层
                try:
                    l1 = check_layer1_node_type(all_parsed[0])
                    print(f"  ✅ 第一层（节点类型固有需求）: {len(l1)} 项发现", file=sys.stderr)
                except Exception as e:
                    errors.append(f"第一层检查异常: {e}")
                    print(f"  ❌ 第一层检查异常: {e}", file=sys.stderr)

                # 第二层
                try:
                    l2 = check_layer2_config_declaration(all_parsed[0])
                    print(f"  ✅ 第二层（配置声明）: {len(l2)} 项发现", file=sys.stderr)
                except Exception as e:
                    errors.append(f"第二层检查异常: {e}")
                    print(f"  ❌ 第二层检查异常: {e}", file=sys.stderr)

                # L5 跨策略
                try:
                    l5 = check_l5_cross_strategy(all_parsed, stages)
                    print(f"  ✅ L5（跨策略流转）: {len(l5)} 项发现", file=sys.stderr)
                except Exception as e:
                    errors.append(f"L5 检查异常: {e}")
                    print(f"  ❌ L5 检查异常: {e}", file=sys.stderr)

                # ─── 检查 6: 输出格式验证 ──────────────────────────────────
                print("\n[6/6] 验证输出格式...", file=sys.stderr)

                # JSON 格式
                try:
                    all_findings = l1 + l2 + l5
                    json_out = format_findings_json(all_findings, link_info)
                    json_data = json.loads(json_out)
                    assert "link_id" in json_data
                    assert "findings" in json_data
                    assert "total_findings" in json_data
                    print("  ✅ JSON 输出格式正确", file=sys.stderr)
                except Exception as e:
                    errors.append(f"JSON 输出格式异常: {e}")
                    print(f"  ❌ JSON 输出格式异常: {e}", file=sys.stderr)

                # Markdown 格式
                try:
                    md_out = format_findings_md(all_findings, link_info)
                    assert "## L1/L5" in md_out
                    assert link_info.get("name", "?") in md_out
                    print("  ✅ Markdown 输出格式正确", file=sys.stderr)
                except Exception as e:
                    errors.append(f"Markdown 输出格式异常: {e}")
                    print(f"  ❌ Markdown 输出格式异常: {e}", file=sys.stderr)

    # ─── 汇总 ────────────────────────────────────────────────────────────
    print("\n" + "=" * 60, file=sys.stderr)
    if errors:
        print(f"❌ 自检失败: {len(errors)} 个错误", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        return False
    else:
        print("✅ 自检全部通过", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        return True


def main():
    parser = argparse.ArgumentParser(description="L1/L5 参数引用完整性检查")
    parser.add_argument("link_id", type=int, nargs="?", help="链路 ID（自检模式下可省略）")
    parser.add_argument("--baseline", action="store_true",
                        help="启用第三层基线对比（拉取全量策略，耗时较长）")
    parser.add_argument("--json", action="store_true",
                        help="输出 JSON 格式")
    parser.add_argument("--self-test", action="store_true",
                        help="自检模式：对已知链路执行完整检查，验证脚本各模块工作正常")
    parser.add_argument("--test-link-id", type=int, default=20272,
                        help="自检使用的测试链路 ID（默认 20272）")
    args = parser.parse_args()

    # ─── 自检模式 ─────────────────────────────────────────────────────────
    if args.self_test:
        success = run_self_test(args.test_link_id)
        sys.exit(0 if success else 1)

    # ─── 正常模式 ─────────────────────────────────────────────────────────
    if args.link_id is None:
        parser.error("正常模式需要提供链路 ID，或使用 --self-test 进入自检模式")

    link_id = args.link_id

    # Step 1: 获取链路信息
    print(f"[1/4] 获取链路 {link_id} 基本信息...", file=sys.stderr)
    link_info = fetch_link_info(link_id)
    if not link_info:
        print(f"[ERROR] 链路 {link_id} 不存在或已删除", file=sys.stderr)
        sys.exit(1)

    # Step 2: 解析 struct，提取策略 ID
    stages = parse_struct(link_info.get("struct", "{}"))
    if not stages:
        print(f"[ERROR] 链路 {link_id} 的 struct 解析失败或无 stages", file=sys.stderr)
        sys.exit(1)

    strategy_ids = []
    for stage in stages:
        strategy_ids.extend(extract_strategy_ids(stage))
    strategy_ids = list(set(strategy_ids))

    print(f"[2/4] 获取 {len(strategy_ids)} 个策略的 workflow_def...", file=sys.stderr)
    strategies = fetch_strategies(strategy_ids)
    if not strategies:
        print(f"[ERROR] 未获取到策略数据", file=sys.stderr)
        sys.exit(1)

    # Step 3: 解析并执行检查
    print(f"[3/4] 执行三层递进检查...", file=sys.stderr)
    all_findings = []

    for strategy in strategies:
        parsed = extract_strategy_params(strategy)

        # 第一层：节点类型固有需求
        l1_findings = check_layer1_node_type(parsed)
        all_findings.extend(l1_findings)

        # 第二层：节点内部配置声明
        l2_findings = check_layer2_config_declaration(parsed)
        all_findings.extend(l2_findings)

    # L5 跨策略检查
    all_parsed = [extract_strategy_params(s) for s in strategies]
    l5_findings = check_l5_cross_strategy(all_parsed, stages)
    all_findings.extend(l5_findings)

    # 第三层：基线对比（可选）
    if args.baseline:
        print(f"[3.5/4] 拉取基线数据（全量策略）...", file=sys.stderr)
        baseline = fetch_all_prod_strategies()
        if baseline:
            # 对每个策略做基线对比
            for strategy in strategies:
                parsed = extract_strategy_params(strategy)
                l3_findings = check_layer3_baseline(parsed, baseline)
                all_findings.extend(l3_findings)

    # Step 4: 输出报告
    print(f"[4/4] 生成报告...", file=sys.stderr)
    if args.json:
        print(format_findings_json(all_findings, link_info))
    else:
        print(format_findings_md(all_findings, link_info))


if __name__ == "__main__":
    main()
