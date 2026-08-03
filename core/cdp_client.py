"""
cdp_client.py — CDP 连接封装

负责：
- WebSocket 握手，连接本地 Chrome CDP
- 维护 Page / Network / Runtime 三个领域的 enable 状态
- 提供统一的 send() 方法和事件订阅接口
- 最大化窗口、设置 viewport
- 支持多实例隔离（启动独立 Chrome 进程）

运行环境：
- cloudcli: CloudCLI 浏览器（动态端口，从 DevToolsActivePort 读取）
- sandbox:  OpenClaw 沙箱浏览器（固定端口 9222）
- local:    本地 Chrome（手动启动 --remote-debugging-port）
- agentbay: 云端沙箱（通过 WebSocket CDP 端点连接 BrowserTool/AgentBay）

可通过 WEB_AUTO_RUNTIME 环境变量强制指定环境。
可通过 WEB_AUTO_CDP_WS_URL 环境变量设置 WebSocket 端点（自动切换 agentbay 模式）。

多实例隔离：
    通过 WEB_AUTO_CDP_PORT 环境变量或 port 参数连接不同 Chrome 实例，
    或使用 launch_new=True 自动启动独立 Chrome 进程，实现窗口间完全隔离。

使用方式：
    # 连接已有实例
    client = CDPClient()
    await client.connect(url_pattern="xiaoer.alibaba-inc.com")

    # 启动独立实例（完全隔离）
    client = CDPClient()
    await client.connect(launch_new=True, launch_options={"port": 9223})

    await client.enable_network()
    client.on("Network.requestWillBeSent", handler)
    await client.send("Page.captureScreenshot", {"format": "jpeg", "quality": 65})
    await client.disconnect()
"""

import asyncio
import json
import os
import subprocess
import sys

# Node.js 桥接路径（Python 调用 Node CDP）
NODE_BRIDGE = os.path.join(os.path.dirname(__file__), "_node_bridge.js")

# puppeteer-core 路径（env 优先，auto 时由 _node_bridge.js 自动探测）
PUPPETEER_PATH = os.environ.get("WEB_AUTO_PUPPETEER_PATH", "auto")

# ── 运行环境检测 ──────────────────────────────────────────────────────────────

_RUNTIME_CONFIG = {
    "cloudcli": {
        "port_file": os.path.join(os.path.expanduser("~"), ".aone-cloud-cli/browser-data/DevToolsActivePort"),
        "puppeteer": os.path.join(os.path.expanduser("~"), ".aone-cloud-cli/plugins/browser/node_modules/puppeteer-core"),
        "default_port": None,
    },
    "sandbox": {
        "port_file": None,
        "puppeteer": "/usr/lib/node_modules/@agent-infra/mcp-server-browser/node_modules/puppeteer-core",
        "default_port": 9222,
    },
    "local": {
        "port_file": None,
        "puppeteer": None,
        "default_port": 9222,
    },
    "agentbay": {
        "port_file": None,
        "puppeteer": None,
        "default_port": None,
    },
}

def _detect_runtime() -> str:
    """检测当前运行环境：cloudcli / sandbox / local / agentbay"""
    explicit = os.environ.get("WEB_AUTO_RUNTIME")
    if explicit and explicit in _RUNTIME_CONFIG:
        return explicit

    # AgentBay: WebSocket CDP 端点存在
    if os.environ.get("WEB_AUTO_CDP_WS_URL"):
        return "agentbay"

    # CloudCLI: DevToolsActivePort 文件存在
    cfg = _RUNTIME_CONFIG["cloudcli"]
    if cfg["port_file"] and os.path.isfile(cfg["port_file"]):
        return "cloudcli"

    # Sandbox: OpenClaw 内置 puppeteer 存在
    cfg = _RUNTIME_CONFIG["sandbox"]
    if cfg["puppeteer"] and os.path.isdir(cfg["puppeteer"]):
        return "sandbox"

    return "local"

def _resolve_cdp_url(runtime: str, port: int = None, ws_endpoint: str = None) -> str:
    """
    根据运行环境解析 CDP 地址。
    - agentbay:  返回 WebSocket 端点（wss:// 或 ws://）
    - cloudcli: 从 DevToolsActivePort 读取动态端口（必须）
    - sandbox:  固定 9222
    - local:    尝试 DevToolsActivePort，回退 9222

    优先级：
    1. ws_endpoint 参数（WebSocket 端点，云端沙箱用）
    2. port 参数（显式指定端口号）
    3. WEB_AUTO_CDP_URL 环境变量（完整 URL）
    4. WEB_AUTO_CDP_PORT 环境变量（仅端口号）
    5. 环境自动探测
    """
    # WebSocket 端点优先（云端沙箱）
    if ws_endpoint:
        return ws_endpoint

    env_ws = os.environ.get("WEB_AUTO_CDP_WS_URL")
    if env_ws:
        return env_ws
    # 显式端口号优先
    if port:
        return f"http://127.0.0.1:{port}"

    env_url = os.environ.get("WEB_AUTO_CDP_URL")
    if env_url:
        return env_url

    # 支持仅传入端口号的环境变量
    env_port = os.environ.get("WEB_AUTO_CDP_PORT")
    if env_port and env_port.isdigit():
        return f"http://127.0.0.1:{env_port}"

    cfg = _RUNTIME_CONFIG[runtime]

    if runtime == "sandbox":
        return f"http://127.0.0.1:{cfg['default_port']}"

    # cloudcli / local: 尝试读取端口文件
    port_files = [
        cfg["port_file"],
        os.path.join(os.path.expanduser("~"), ".config/chrome-debug/DevToolsActivePort"),
        "/tmp/chrome-debug/DevToolsActivePort",
    ]
    for f in filter(None, port_files):
        try:
            p = open(f).readline().strip()
            if p.isdigit():
                return f"http://127.0.0.1:{p}"
        except OSError:
            continue

    if runtime == "cloudcli":
        raise RuntimeError(
            "CloudCLI 环境下未找到 DevToolsActivePort 文件，浏览器可能未启动。"
        )
    return "http://127.0.0.1:9222"

class CDPClient:
    """
    CDP 客户端封装。
    通过子进程调用 Node.js 执行 CDP 操作，Python 侧通过 JSON-Lines stdin/stdout 通信。

    运行环境在实例化时自动检测，也可通过 runtime 参数强制指定。

    多实例隔离：
        每个 CDPClient 可连接不同的 Chrome 实例（通过 port / cdp_url 参数），
        或使用 launch_new=True 自动启动独立的 Chrome 实例，实现窗口间完全隔离。

    环境变量：
        WEB_AUTO_CDP_URL   : 完整 CDP 地址（如 http://127.0.0.1:9223）
        WEB_AUTO_CDP_PORT  : 仅端口号（如 9223）
        WEB_AUTO_CHROME_BIN: Chrome 可执行文件路径
    """

    def __init__(self, cdp_url: str = None, runtime: str = None, port: int = None, ws_endpoint: str = None):
        self.ws_endpoint = ws_endpoint or os.environ.get("WEB_AUTO_CDP_WS_URL")
        # ws_endpoint 传入时自动切换 agentbay 运行时
        if runtime:
            self.runtime = runtime
        elif self.ws_endpoint:
            self.runtime = "agentbay"
        else:
            self.runtime = _detect_runtime()
        self.cdp_url = cdp_url or _resolve_cdp_url(self.runtime, port=port, ws_endpoint=self.ws_endpoint)
        self._proc = None
        self._handlers = {}  # event_name -> list of callables
        self._pending = {}   # cmd_id -> asyncio.Future
        self._cmd_id = 0
        self._reader_task = None
        self._isolated = False   # 是否为独立 Chrome 实例
        self._chrome_pid = None  # 独立 Chrome 进程 PID
        # 重连参数记忆
        self._last_url_pattern = None
        self._last_url = None
        self._last_launch_options = None

    async def connect(self, url_pattern: str = None, url: str = None,
                      launch_new: bool = False, launch_options: dict = None):
        """连接浏览器，定位目标 tab。

        Args:
            url_pattern: 按 URL 关键字查找已有 tab
            url: 若无匹配 tab 则导航到此 URL
            launch_new: 为 True 时启动独立 Chrome 实例（完全隔离）
            launch_options: 传给 launchChrome 的选项（port / headless / chromeBin 等）
        """
        # limit=10MB 避免截图 base64 超出 readline 默认 64KB 限制
        self._proc = await asyncio.create_subprocess_exec(
            "node", NODE_BRIDGE,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=10 * 1024 * 1024,
        )
        self._reader_task = asyncio.create_task(self._read_loop())

        # 记忆连接参数（供重连使用）
        self._last_url_pattern = url_pattern
        self._last_url = url
        self._last_launch_options = launch_options

        connect_params = {
            "cdpUrl": self.cdp_url,
            "urlPattern": url_pattern,
            "url": url,
        }
        if self.ws_endpoint:
            connect_params["wsEndpoint"] = self.ws_endpoint
        if launch_new:
            connect_params["launchNew"] = True
            connect_params["launchOptions"] = launch_options or {}

        result = await self._send_cmd("connect", connect_params)
        self._isolated = result.get("isolated", False)
        self._chrome_pid = result.get("pid")
        # 如果启动了独立实例，更新 cdp_url 为实际分配的地址
        if self._isolated and result.get("cdpUrl"):
            self.cdp_url = result["cdpUrl"]

    @property
    def is_isolated(self) -> bool:
        """当前是否连接到独立 Chrome 实例"""
        return self._isolated

    @property
    def chrome_pid(self) -> int:
        """独立 Chrome 进程 PID（非独立实例时为 None）"""
        return self._chrome_pid

    async def reconnect(self, max_retries: int = 3, backoff: list = None) -> bool:
        """断线重连：重新建立 Node 桥接进程 + CDP WebSocket 连接。

        Args:
            max_retries: 最大重试次数
            backoff: 退避秒数列表，默认 [1, 3, 5]

        Returns:
            True 表示重连成功，False 表示全部重试失败
        """
        backoff = backoff or [1, 3, 5]
        for attempt in range(max_retries):
            wait = backoff[min(attempt, len(backoff) - 1)]
            print(f"[cdp] 重连尝试 {attempt + 1}/{max_retries}，等待 {wait}s ...", file=sys.stderr)
            try:
                # 清理旧进程
                if self._proc:
                    try:
                        self._proc.terminate()
                        await self._proc.wait()
                    except Exception:
                        pass
                if self._reader_task:
                    self._reader_task.cancel()

                # 重新建立连接（保持原参数）
                self._proc = await asyncio.create_subprocess_exec(
                    "node", NODE_BRIDGE,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    limit=10 * 1024 * 1024,
                )
                self._reader_task = asyncio.create_task(self._read_loop())
                self._cmd_id = 0
                self._pending.clear()

                connect_params = {
                    "cdpUrl": self.cdp_url,
                    "urlPattern": self._last_url_pattern,
                    "url": self._last_url,
                }
                if self.ws_endpoint:
                    connect_params["wsEndpoint"] = self.ws_endpoint
                if self._isolated:
                    connect_params["launchNew"] = True
                    connect_params["launchOptions"] = self._last_launch_options or {}

                result = await asyncio.wait_for(
                    self._send_cmd("connect", connect_params), timeout=15
                )
                if result.get("connected"):
                    print(f"[cdp] 重连成功（第 {attempt + 1} 次尝试）", file=sys.stderr)
                    return True
            except Exception as e:
                print(f"[cdp] 重连失败: {e}", file=sys.stderr)

            await asyncio.sleep(wait)

        print(f"[cdp] 重连全部失败（{max_retries} 次）", file=sys.stderr)
        return False

    async def disconnect(self):
        """断开连接（不关闭浏览器）"""
        try:
            await self._send_cmd("disconnect", {})
        finally:
            if self._proc:
                self._proc.terminate()
                await self._proc.wait()
            if self._reader_task:
                self._reader_task.cancel()

    async def enable_network(self, url_filter: str = None):
        """启用 Network 域监听"""
        await self._send_cmd("enableNetwork", {"urlFilter": url_filter})

    async def enable_runtime(self):
        """启用 Runtime 域（Console 日志等）"""
        await self._send_cmd("enableRuntime", {})

    async def send(self, method: str, params: dict = None) -> dict:
        """向 CDP 发送命令，返回结果"""
        return await self._send_cmd("cdp", {"method": method, "params": params or {}})

    async def evaluate(self, expression: str) -> any:
        """在页面执行 JS 表达式"""
        result = await self._send_cmd("evaluate", {"expression": expression})
        return result.get("value")

    def on(self, event: str, handler):
        """订阅 CDP 事件"""
        self._handlers.setdefault(event, []).append(handler)

    def off(self, event: str, handler):
        """取消订阅"""
        if event in self._handlers:
            self._handlers[event] = [h for h in self._handlers[event] if h != handler]

    async def check_login(self) -> dict:
        """检测当前页面是否处于登录态。

        返回:
            {
              "isLoginPage": bool,
              "loginType": "buc" | "taobao" | "none",
              "currentUrl": str
            }
        """
        return await self._send_cmd("checkLogin", {})

    async def taobao_login(self, username: str, password: str) -> dict:
        """使用账号密码登录淘宝。仅适用于淘宝登录页。

        Args:
            username: 淘宝账号
            password: 淘宝密码

        Returns:
            {"loggedIn": True, "finalUrl": str}

        Raises:
            RuntimeError: 登录失败（账号密码错误 / 需要验证码）
        """
        return await self._send_cmd("taobaoLogin", {
            "username": username,
            "password": password,
        })

    async def set_fixed_viewport(self):
        """固定浏览器窗口与 viewport 为 1458×784"""
        await self._send_cmd("setFixedViewport", {})

    async def maximize_window(self):
        """兼容旧名：固定 viewport 1458×784（不再最大化）"""
        await self.set_fixed_viewport()

    async def dismiss_modals(self, max_rounds: int = 5) -> dict:
        """关闭常见遮挡弹窗"""
        return await self._send_cmd("dismissModals", {"maxRounds": max_rounds})

    async def disable_webauthn(self) -> dict:
        """阻止页面触发 macOS Passkey / WebAuthn 原生弹窗"""
        return await self._send_cmd("disableWebAuthn", {})

    async def screenshot(self) -> bytes:
        """截图，返回 JPEG bytes（medium 质量，已清除水印）"""
        result = await self._send_cmd("screenshot", {})
        import base64
        return base64.b64decode(result["data"])

    async def set_cookies(self, cookies: list) -> dict:
        """通过 CDP 注入 cookie 到浏览器"""
        return await self.send("Network.setCookies", {"cookies": cookies})

    async def get_response_body(self, request_id: str) -> str:
        """获取请求响应体（必须在 loadingFinished 后调用）"""
        result = await self._send_cmd("getResponseBody", {"requestId": request_id})
        return result.get("body", "")

    # ── 内部通信 ──

    async def _send_cmd(self, cmd: str, params: dict) -> dict:
        self._cmd_id += 1
        msg_id = self._cmd_id
        msg = json.dumps({"id": msg_id, "cmd": cmd, "params": params}) + "\n"
        try:
            self._proc.stdin.write(msg.encode())
            await self._proc.stdin.drain()
        except (ConnectionResetError, BrokenPipeError, OSError) as e:
            # CDP 桥接进程已死，标记需要重连
            raise ConnectionError(f"CDP 桥接进程断开: {e}") from e

        fut = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = fut
        try:
            return await asyncio.wait_for(fut, timeout=30)
        except asyncio.TimeoutError:
            raise TimeoutError(f"CDP 命令超时: {cmd}")

    async def _read_loop(self):
        while True:
            try:
                line = await self._proc.stdout.readline()
                if not line:
                    break
                msg = json.loads(line.decode().strip())

                if "id" in msg:
                    # 命令响应
                    fut = self._pending.pop(msg["id"], None)
                    if fut and not fut.done():
                        if msg.get("error"):
                            fut.set_exception(RuntimeError(msg["error"]))
                        else:
                            fut.set_result(msg.get("result", {}))
                elif "event" in msg:
                    # CDP 事件
                    event = msg["event"]
                    for handler in self._handlers.get(event, []):
                        if asyncio.iscoroutinefunction(handler):
                            asyncio.create_task(handler(msg.get("params", {})))
                        else:
                            handler(msg.get("params", {}))
            except asyncio.CancelledError:
                break
            except Exception:
                pass
