"""
browser_setup.py — 浏览器连接与登录辅助

从 impl.py 抽取的浏览器初始化逻辑：
- Cookie URL 解析（OSS / 本地配置）
- Cookie 注入
- 内网 SSO 预热
- 登录检测与自动登录

使用方式:
    from core.browser_setup import inject_cookies, ensure_alibaba_sso, handle_login
    cookie_injected = await inject_cookies(cdp, ctx)
    await ensure_alibaba_sso(cdp, target_url, url_pattern)
    login_ok = await handle_login(cdp, ctx, output)
"""

import asyncio
import json
import os
import sys


def get_default_cookies_url() -> str:
    """解析默认 Cookie URL：环境变量 > 本地配置文件 > 空字符串。"""
    env_url = os.environ.get("WEB_AUTO_COOKIES_URL", "")
    if env_url:
        return env_url

    emp_id = os.environ.get("WEB_AUTO_EMP_ID", "")
    # 项目根目录 = core/ 的上一级
    _root = os.path.join(os.path.dirname(__file__), "..")
    config_candidates = [
        os.path.join(_root, "..", "cloth-test", "cloth-config.json"),
        os.path.join(os.path.expanduser("~"), ".qoderwork", "cloth-test", "cloth-config.json"),
        os.path.join(_root, "..", "cloth-config.json"),
    ]
    for config_path in config_candidates:
        try:
            with open(config_path) as f:
                cfg = json.load(f)
            emp_id = emp_id or cfg.get("team", {}).get("empId", "") or cfg.get("report", {}).get("empId", "")
            if emp_id:
                break
        except (FileNotFoundError, json.JSONDecodeError):
            continue

    if emp_id:
        return f"https://test-ai-hub-testing.oss-cn-hangzhou.aliyuncs.com/cookies/{emp_id}.json"
    return ""


async def inject_cookies(cdp, ctx: dict) -> bool:
    """从 OSS 下载 cookie 并注入浏览器。

    支持三种 Cookie 来源（优先级从高到低）：
    1. ctx["cookiesJson"] — 直接传入 JSON 对象
    2. WEB_AUTO_COOKIES_JSON 环境变量 — JSON 字符串
    3. OSS URL 下载（ctx["cookiesUrl"] 或自动解析）

    返回是否注入成功。
    """
    # 1. 直接传入 Cookie JSON
    direct_cookies = ctx.get("cookiesJson")
    if direct_cookies:
        try:
            await cdp.set_cookies(direct_cookies)
            print(f"[cookie] 已注入 {len(direct_cookies)} 个 cookie（来源: ctx.cookiesJson）", file=sys.stderr)
            return True
        except Exception as e:
            print(f"[cookie] ctx.cookiesJson 注入失败: {e}", file=sys.stderr)

    # 2. 环境变量直接传入 JSON 字符串
    env_cookies_json = os.environ.get("WEB_AUTO_COOKIES_JSON", "")
    if env_cookies_json:
        try:
            cookies = json.loads(env_cookies_json)
            if cookies:
                await cdp.set_cookies(cookies)
                print(f"[cookie] 已注入 {len(cookies)} 个 cookie（来源: WEB_AUTO_COOKIES_JSON）", file=sys.stderr)
                return True
        except Exception as e:
            print(f"[cookie] WEB_AUTO_COOKIES_JSON 注入失败: {e}", file=sys.stderr)

    # 3. OSS URL 下载
    cookies_url = ctx.get("cookiesUrl", get_default_cookies_url())
    if not cookies_url:
        return False
    try:
        import urllib.request
        with urllib.request.urlopen(cookies_url, timeout=10) as resp:
            cookies = json.loads(resp.read().decode())
        if cookies:
            await cdp.set_cookies(cookies)
            print(f"[cookie] 已注入 {len(cookies)} 个 cookie（来源: {cookies_url}）", file=sys.stderr)
            return True
    except Exception as e:
        print(f"[cookie] OSS cookie 注入失败: {e}", file=sys.stderr)
    return False


async def ensure_alibaba_sso(cdp, target_url: str = "", url_pattern: str = ""):
    """内网 BUC SSO 预热：访问阿里内部站点以触发 SSO 会话。

    可通过 WEB_AUTO_SKIP_SSO_WARMUP=true 跳过（云端沙箱已有登录态时）。
    """
    # 跳过 SSO 预热
    if os.environ.get("WEB_AUTO_SKIP_SSO_WARMUP", "").lower() in ("true", "1", "yes"):
        print("[sso] 跳过 SSO 预热（WEB_AUTO_SKIP_SSO_WARMUP=true）", file=sys.stderr)
        return

    hint = f"{target_url} {url_pattern}"
    if "alibaba-inc.com" not in hint:
        return
    # 阻止 macOS Passkey 弹窗（“没有可用的通行密钥”）
    try:
        await cdp.disable_webauthn()
    except Exception:
        pass
    for warm_url in (
        "https://work.alibaba-inc.com/",
        "https://aone.alibaba-inc.com/",
    ):
        await cdp._send_cmd("navigate", {"url": warm_url})
        await asyncio.sleep(2)
    if target_url.startswith("http"):
        await cdp._send_cmd("navigate", {"url": target_url})
        await asyncio.sleep(3)


async def handle_login(cdp, ctx: dict, output: dict) -> bool:
    """
    登录检测与处理。

    返回 True 表示已通过登录检测（可以继续执行）。
    返回 False 表示需要人工登录，output 已写入 login_required 状态。
    """
    login_status = await cdp.check_login()
    is_login_page = login_status.get("isLoginPage", False)

    if not is_login_page:
        output["authType"] = login_status.get("loginType", "unknown")
        return True

    login_type = login_status.get("loginType", "unknown")
    current_url = login_status.get("currentUrl", "")
    credentials = ctx.get("loginCredentials", {})

    if login_type == "taobao" and credentials.get("type") == "taobao":
        await cdp.taobao_login(
            username=credentials["username"],
            password=credentials["password"],
        )
        await asyncio.sleep(2)
        output["authType"] = "taobao"
        return True

    # BUC 或未配置凭证 → 需要人工登录
    hint = (
        "需要人工登录 BUC（阿里员工 SSO），请在浏览器中完成登录后重试"
        if login_type == "buc"
        else "淘宝登录页未配置 loginCredentials，请在 context 中传入 username/password"
    )
    output["status"] = "login_required"
    output["error"] = {
        "stepIndex": -1,
        "loginType": login_type,
        "currentUrl": current_url,
        "message": hint,
    }
    return False
