"""
report_uploader.py — 验收报告云端上传（钉钉知识库）

将 Markdown 验收报告上传到钉钉在线文档知识库，不留存本地文件。
支持两种上传通道：
    1. DingTalk Open API（生产环境，需配置 access_token）
    2. MCP 代理模式（Agent 执行环境，由调用方通过钉钉文档 MCP 完成）

使用方式：
    from core.report_uploader import upload_to_dingtalk

    url = upload_to_dingtalk(
        title="验收报告-run-20260725-001",
        markdown="# 质量验收报告\n...",
        workspace_id="nb9XJRV7Q8BdPXyA",  # 专项建设知识库
    )

配置（环境变量或 input_data）：
    DINGTALK_APP_KEY / DINGTALK_APP_SECRET — 应用凭证（Open API 模式）
    DINGTALK_WORKSPACE_ID — 默认知识库 ID
    DINGTALK_REPORT_FOLDER_ID — 报告存放文件夹 ID（可选）
"""

import os
import json
import time
from typing import Optional


# ── 默认配置 ──

# F88 产物知识库（https://alidocs.dingtalk.com/i/spaces/nb9XJ9V6ErBnlzyA/overview）
F88_WORKSPACE_ID = "nb9XJ9V6ErBnlzyA"
F88_REPORT_FOLDER_ID = "QG53mjyd800agdlKHwBMne9d86zbX04v"  # "测试报告" 文件夹

# 原创保护知识库（https://alidocs.dingtalk.com/i/spaces/nb9XJ9YdaYkZLzyA/overview）
OP_WORKSPACE_ID = "nb9XJ9YdaYkZLzyA"
OP_REPORT_FOLDER_ID = "vy20BglGWOxjGpq0CgbPzxg6VA7depqY"  # "测试报告" 文件夹

DEFAULT_WORKSPACE_ID = os.environ.get("DINGTALK_WORKSPACE_ID", F88_WORKSPACE_ID)
DEFAULT_FOLDER_ID = os.environ.get("DINGTALK_REPORT_FOLDER_ID", F88_REPORT_FOLDER_ID)

# 去重注册表路径（记录已上传文档，避免同一次运行重复创建）
_UPLOAD_REGISTRY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "artifacts", "_upload_registry.json"
)

# 钉钉 Open API 端点
_DINGTALK_TOKEN_URL = "https://oapi.dingtalk.com/gettoken"
_DINGTALK_CREATE_DOC_URL = "https://api.dingtalk.com/v1.0/doc/workspaces/{workspaceId}/docs"


def upload_to_dingtalk(
    title: str,
    markdown: str,
    workspace_id: str = "",
    folder_id: str = "",
    force: bool = False,
) -> str:
    """上传验收报告到钉钉知识库（带幂等去重）。

    Args:
        title: 文档标题
        markdown: Markdown 内容
        workspace_id: 知识库 ID（默认从环境变量读取）
        folder_id: 目标文件夹 ID（可选，不传则放知识库根目录）
        force: 强制上传，跳过去重检查

    Returns:
        文档 URL（如 https://alidocs.dingtalk.com/i/nodes/xxx）

    Raises:
        RuntimeError: 上传失败时抛出
    """
    ws_id = workspace_id or DEFAULT_WORKSPACE_ID
    fld_id = folder_id or DEFAULT_FOLDER_ID

    # ── 幂等去重：同 title + workspace + folder 只上传一次 ──
    if not force:
        existing_url = _check_dedup(title, ws_id, fld_id)
        if existing_url:
            return existing_url

    # 尝试 Open API 模式
    app_key = os.environ.get("DINGTALK_APP_KEY", "")
    app_secret = os.environ.get("DINGTALK_APP_SECRET", "")

    if app_key and app_secret:
        url = _upload_via_open_api(title, markdown, ws_id, fld_id, app_key, app_secret)
    else:
        # 无凭证时：写入临时文件供 Agent MCP 通道消费
        url = _upload_via_mcp_proxy(title, markdown, ws_id, fld_id)

    # 记录到去重注册表
    _record_dedup(title, ws_id, fld_id, url)
    return url


def _upload_via_open_api(
    title: str,
    markdown: str,
    workspace_id: str,
    folder_id: str,
    app_key: str,
    app_secret: str,
) -> str:
    """通过钉钉 Open API 创建文档"""
    import urllib.request
    import urllib.error

    # 1. 获取 access_token
    token_url = f"{_DINGTALK_TOKEN_URL}?appkey={app_key}&appsecret={app_secret}"
    try:
        with urllib.request.urlopen(token_url, timeout=10) as resp:
            token_data = json.loads(resp.read().decode())
        access_token = token_data.get("access_token", "")
        if not access_token:
            raise RuntimeError(f"获取 token 失败: {token_data}")
    except Exception as e:
        raise RuntimeError(f"钉钉 token 获取失败: {e}")

    # 2. 创建文档
    create_url = _DINGTALK_CREATE_DOC_URL.format(workspaceId=workspace_id)
    payload = {
        "name": title,
        "docType": "alidoc",
        "content": markdown[:10000],  # API 限制 10000 字符
    }
    if folder_id:
        payload["parentDentryUuid"] = folder_id

    req = urllib.request.Request(
        create_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-acs-dingtalk-access-token": access_token,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
        doc_url = result.get("url", "")
        node_id = result.get("dentryUuid", "")
        if doc_url:
            return doc_url
        if node_id:
            return f"https://alidocs.dingtalk.com/i/nodes/{node_id}"
        raise RuntimeError(f"创建文档返回异常: {result}")
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        raise RuntimeError(f"钉钉创建文档失败 HTTP {e.code}: {body}")


def _upload_via_mcp_proxy(
    title: str,
    markdown: str,
    workspace_id: str,
    folder_id: str,
) -> str:
    """MCP 代理模式：写入待上传队列文件，由 Agent 侧通过钉钉文档 MCP 完成实际上传。

    返回队列文件路径（Agent 读取后调用 MCP create_document）。
    """
    queue_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "artifacts", "_upload_queue")
    os.makedirs(queue_dir, exist_ok=True)

    queue_file = os.path.join(queue_dir, f"{int(time.time())}_{title[:30].replace(' ', '_')}.json")
    payload = {
        "action": "create_document",
        "title": title,
        "markdown": markdown,
        "workspace_id": workspace_id,
        "folder_id": folder_id,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "status": "pending",
    }
    with open(queue_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return f"pending://{queue_file}"


def process_upload_queue() -> list:
    """处理待上传队列（供 Agent 侧调用）。

    读取 artifacts/_upload_queue/ 下的 pending 文件，
    返回需要上传的文档列表（由调用方通过 MCP 完成实际创建）。
    """
    queue_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "artifacts", "_upload_queue")
    if not os.path.exists(queue_dir):
        return []

    pending = []
    for fname in sorted(os.listdir(queue_dir)):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(queue_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                item = json.load(f)
            if item.get("status") == "pending":
                item["_queue_file"] = fpath
                pending.append(item)
        except (json.JSONDecodeError, IOError):
            continue
    return pending


def mark_uploaded(queue_file: str, doc_url: str):
    """标记队列项为已上传"""
    try:
        with open(queue_file, "r", encoding="utf-8") as f:
            item = json.load(f)
        item["status"] = "uploaded"
        item["doc_url"] = doc_url
        item["uploaded_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        with open(queue_file, "w", encoding="utf-8") as f:
            json.dump(item, f, ensure_ascii=False, indent=2)
        # 同步写入去重注册表
        _record_dedup(
            item.get("title", ""),
            item.get("workspace_id", ""),
            item.get("folder_id", ""),
            doc_url,
        )
    except (IOError, json.JSONDecodeError):
        pass


# ── 去重注册表（防止同一 run 内双路径重复上传）──

def _dedup_key(title: str, workspace_id: str, folder_id: str) -> str:
    """生成去重键：title + workspace + folder"""
    return f"{workspace_id}:{folder_id}:{title}"


def _load_registry() -> dict:
    """加载去重注册表"""
    try:
        if os.path.exists(_UPLOAD_REGISTRY_PATH):
            with open(_UPLOAD_REGISTRY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except (IOError, json.JSONDecodeError):
        pass
    return {}


def _save_registry(registry: dict):
    """持久化去重注册表"""
    os.makedirs(os.path.dirname(_UPLOAD_REGISTRY_PATH), exist_ok=True)
    try:
        with open(_UPLOAD_REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(registry, f, ensure_ascii=False, indent=2)
    except IOError:
        pass


def _check_dedup(title: str, workspace_id: str, folder_id: str) -> str:
    """检查是否已上传过，返回已有 URL 或空字符串"""
    key = _dedup_key(title, workspace_id, folder_id)
    registry = _load_registry()
    entry = registry.get(key)
    if entry and entry.get("url"):
        return entry["url"]
    return ""


def _record_dedup(title: str, workspace_id: str, folder_id: str, url: str):
    """记录已上传文档到注册表"""
    if not title or not url:
        return
    key = _dedup_key(title, workspace_id, folder_id)
    registry = _load_registry()
    registry[key] = {
        "url": url,
        "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    _save_registry(registry)
