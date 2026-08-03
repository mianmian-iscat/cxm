"""
normalize_input.py — 输入预处理

职责：
- URL 格式校验
- 敏感信息脱敏（token、cookie、Authorization 等）
- 补充默认值
- 步骤数量限制检查

确定性逻辑，不交给模型处理。
"""

import json
import re
import sys
from typing import Any
from urllib.parse import urlparse

MAX_STEPS = 50

SENSITIVE_KEYS = {
    "token", "access_token", "authorization", "cookie", "password",
    "secret", "api_key", "apikey", "private_token",
}


def normalize(input_data: dict) -> dict:
    """
    预处理输入数据，返回标准化后的结果。
    抛出 ValueError 表示输入无效。
    """
    data = json.loads(json.dumps(input_data))  # 深拷贝

    # ── 必填字段 ──
    for field in ("id", "name", "steps"):
        if not data.get(field):
            raise ValueError(f"缺少必填字段: {field}")

    # ── ID 格式：只允许字母、数字、连字符 ──
    if not re.match(r'^[a-zA-Z0-9\-_]+$', data["id"]):
        raise ValueError(f"id 格式无效（只允许字母、数字、-、_）: {data['id']}")

    # ── 步骤数量限制 ──
    if len(data["steps"]) > MAX_STEPS:
        raise ValueError(f"steps 数量超过上限 {MAX_STEPS}，当前 {len(data['steps'])}")

    # ── context 默认值 ──
    ctx = data.setdefault("context", {})
    ctx.setdefault("waitAfterLoad", 2000)

    # URL 格式校验
    if url := ctx.get("url"):
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                raise ValueError(f"URL 协议不支持（仅 http/https）: {url}")
        except Exception as e:
            raise ValueError(f"URL 格式无效: {url}，原因: {e}")

    # ── capture 默认值 ──
    capture = data.setdefault("capture", {})
    capture.setdefault("enabled", True)
    capture.setdefault("captureBody", True)
    capture.setdefault("exportHAR", False)

    # ── screenshot 默认值 ──
    screenshot = data.setdefault("screenshot", {})
    screenshot.setdefault("onEachStep", False)
    screenshot.setdefault("onError", True)

    # ── steps 校验和默认值 ──
    for i, step in enumerate(data["steps"]):
        if "type" not in step:
            raise ValueError(f"step[{i}] 缺少 type 字段")

        valid_types = {"click", "fill", "wait", "waitForAPI", "screenshot", "assert", "navigate"}
        if step["type"] not in valid_types:
            raise ValueError(f"step[{i}] type 无效: {step['type']}，支持: {valid_types}")

        # 类型特定校验
        if step["type"] == "click" and not step.get("text") and not step.get("selector"):
            raise ValueError(f"step[{i}] click 必须提供 text 或 selector")

        if step["type"] == "fill":
            if not step.get("selector"):
                raise ValueError(f"step[{i}] fill 缺少 selector")
            if "value" not in step:
                raise ValueError(f"step[{i}] fill 缺少 value")

        if step["type"] == "wait":
            ms = step.get("ms", 0)
            if not isinstance(ms, (int, float)) or ms < 0 or ms > 30000:
                raise ValueError(f"step[{i}] wait.ms 必须在 0~30000 之间，当前: {ms}")

        if step["type"] == "waitForAPI" and not step.get("urlPattern"):
            raise ValueError(f"step[{i}] waitForAPI 缺少 urlPattern")

        if step["type"] == "assert":
            if step.get("target") not in ("page", "api"):
                raise ValueError(f"step[{i}] assert.target 必须是 page 或 api")
            if not step.get("contains"):
                raise ValueError(f"step[{i}] assert 缺少 contains")

        if step["type"] == "navigate" and not step.get("url"):
            raise ValueError(f"step[{i}] navigate 缺少 url")

        # 补充默认值
        step.setdefault("description", f"{step['type']} step {i}")
        step.setdefault("screenshot", False)

    # ── 脱敏（用于日志/存档，不影响实际执行）──
    _redact(data)

    return data


def _redact(obj: Any, parent_key: str = ""):
    """递归脱敏敏感字段"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in SENSITIVE_KEYS:
                obj[k] = "***REDACTED***"
            else:
                _redact(v, k)
    elif isinstance(obj, list):
        for item in obj:
            _redact(item, parent_key)


# CLI 使用
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python normalize_input.py input.json", file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        raw = json.load(f)

    try:
        normalized = normalize(raw)
        print(json.dumps(normalized, ensure_ascii=False, indent=2))
    except ValueError as e:
        print(f"输入校验失败: {e}", file=sys.stderr)
        sys.exit(1)
