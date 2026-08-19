#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
Browser Task Runner - 基于 browser-use CLI 的 AI 任务执行引擎

核心循环：截图 + 页面状态 -> 图片上传 -> CPU Service 推理 -> ActionRouter 分流执行 -> 循环

主要模块：
  - ImageConvertClient: 截图上传至远程服务，获取可访问 URL
  - CPUServiceClient:   调用 CPU Service（异步提交+轮询），传入截图和指令，返回 AI 推理的动作序列
  - ActionRouter:       将 AI 返回的动作分流执行——索引型操作走 browser-use CLI，
                        坐标型操作（click/dblclick/drag/scroll 等）通过 JS 注入执行
  - ExternalToolRegistry: 管理 external_tools，支持内置浏览器工具和用户自定义工具（JSON 配置）
  - TaskRunner:         主循环编排，支持多步执行、tool_call 解析、轨迹记录和 HTML 可视化输出

支持 web/android/ios 平台，通过 --platform 参数切换。
"""

import os
import re
import json
import time
import base64
import uuid
import argparse
import subprocess
import datetime
import platform as platform_mod
from typing import Dict, List, Optional, Any

import requests
from PIL import Image
from dotenv import load_dotenv

load_dotenv(override=True)

import sys
from loguru import logger
logger.remove()
logger.add(sys.stdout, level=os.getenv("LOG_LEVEL", "ERROR"))


# ========================== 默认配置 ==========================
DEFAULT_IMAGE_CONVERT_URL = "http://comfy-gateway.taobao.com/infer/v1/syncPredict"
DEFAULT_IMAGE_CONVERT_BIZNAME = "gui_image_convert"
DEFAULT_IMAGE_CONVERT_BIZCHANNEL = "skill"
DEFAULT_BROWSER_TASK_USER_ID = "skill_browser_task"

DEFAULT_CPU_BASE_URL = "http://comfy-gateway.taobao.com"
DEFAULT_CPU_BIZNAME = "gui_agent"
DEFAULT_CPU_BIZCHANNEL = "skill"


# ========================== browser-use CLI helper ==========================

def bu(*args, session: str = "default", timeout: int = 30) -> subprocess.CompletedProcess:
    """调用 browser-use CLI，自动附加 --session 参数"""
    cmd = ["browser-use", "--session", session] + [str(a) for a in args]
    logger.debug(f"bu> {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0 and result.stderr:
            logger.warning(f"browser-use stderr: {result.stderr.strip()[:200]}")
        return result
    except subprocess.TimeoutExpired:
        logger.error(f"browser-use 命令超时 ({timeout}s): {' '.join(cmd)}")
        raise
    except FileNotFoundError:
        logger.error("browser-use 未安装或不在 PATH 中，请先运行: pip install browser-use")
        raise



# ========================== 远程图片转换服务 ==========================

class ImageConvertClient:
    def __init__(self):
        self.url = os.getenv("IMAGE_CONVERT_URL", DEFAULT_IMAGE_CONVERT_URL)
        self.bizname = os.getenv("IMAGE_CONVERT_BIZNAME", DEFAULT_IMAGE_CONVERT_BIZNAME)
        self.bizchannel = os.getenv("IMAGE_CONVERT_BIZCHANNEL", DEFAULT_IMAGE_CONVERT_BIZCHANNEL)

    def upload_file(self, file_path: str, oss_filename: str, max_retries: int = 2) -> Optional[str]:
        """读取本地文件，base64 编码后调用远程服务上传，返回 OSS URL"""
        with open(file_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()

        payload = {
            "bizName": self.bizname,
            "bizChannel": self.bizchannel,
            "param": {
                "base64_image": b64,
                "filename": oss_filename,
                "user_id": os.getenv("BROWSER_TASK_USER_ID", DEFAULT_BROWSER_TASK_USER_ID),
            },
        }

        for attempt in range(max_retries + 1):
            try:
                resp = requests.post(self.url, json=payload, timeout=60)
                resp.raise_for_status()
                data = resp.json()
                if data.get("errorCode") == 0:
                    return data["data"]["response"]
                logger.error(f"远程上传失败: {data.get('errorMessage')}")
            except Exception as e:
                logger.error(f"远程上传异常 (第{attempt+1}次): {e}")
                if attempt < max_retries:
                    time.sleep(1)
        return None


# ========================== CPU Service ==========================

class CPUServiceClient:
    def __init__(self, base_url: str, bizname: str, bizchannel: str):
        self.base_url = base_url
        self.bizname = bizname
        self.bizchannel = bizchannel
        logger.debug(f"CPU Service: {base_url}  {bizname}/{bizchannel}")

    def predict(self, instruction: str, screenshot_url: str, screen_size: list,
                history: list, app: str = "taobao", plat: str = "web",
                external_tools: list = None, dom_content: str = None,
                extend_info: dict = None, **kw) -> Dict[str, Any]:
        obs = {"screenshot_url": screenshot_url, "screen_size": screen_size}
        if dom_content:
            obs["dom_content"] = dom_content
        param_body = {
            "instruction": instruction,
            "obs": obs,
            "history": history, "app": app, "platform": plat,
            "mode": kw.get("mode", "fast"),
            "use_builtin_feedback": kw.get("use_builtin_feedback", "true"),
            "use_builtin_trajectory": kw.get("use_builtin_trajectory", "true"),
            "rerank_use_gemini": kw.get("rerank_use_gemini", "false"),
            "knowledge_domain": kw.get("knowledge_domain", ""),
            "planner_type": kw.get("planner_type", "planner.0.0.1"),
            "debug": "true",
        }
        if external_tools:
            param_body["external_tools"] = external_tools
        if extend_info:
            param_body["extend_info"] = extend_info
        params = {"param": param_body, "bizName": self.bizname, "bizChannel": self.bizchannel}
        max_retries = 3
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    logger.debug(f"第 {attempt} 次重试...")
                tid = self._submit(params)
                d = self._poll(tid)
                return {
                    "response": d.get("response", ""),
                    "actions": d.get("actions", []),
                    "extend_info": d.get("extend_info", {}),
                }
            except Exception as e:
                time.sleep(1)
                logger.error(f"第 {attempt+1} 次尝试失败: {e}")
                if attempt == max_retries:
                    raise

    def _submit(self, params: dict) -> str:
        url = f"{self.base_url}/infer/v1/submitTask"
        try:
            resp = requests.post(url, json=params, headers={"Content-Type": "application/json"}, timeout=30)
            resp.raise_for_status()
            r = resp.json()
            if r.get("errorCode") == 0:
                tid = r.get("data")
                logger.debug(f"taskId: {tid}")
                return tid
            raise RuntimeError(f"提交失败: {r.get('errorMessage')}")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"提交任务网络错误: {e}")

    def _poll(self, task_id: str, max_timeout: int = 300, poll_interval: int = 1) -> dict:
        start = time.time()
        last_status = None
        error_count = 0
        max_error_count = 10

        while time.time() - start < max_timeout:
            time.sleep(poll_interval)
            url = f"{self.base_url}/infer/v2/queryTask?taskId={task_id}"
            resp = requests.post(url, timeout=poll_interval + 5)
            resp.raise_for_status()
            r = resp.json()

            if r.get("errorCode") != 0:
                error_count += 1
                logger.error(f"查询失败 ({error_count}): {r.get('errorMessage')}")
                if error_count >= max_error_count:
                    raise RuntimeError(f"查询 {error_count} 次后失败: {r.get('errorMessage')}")
                continue

            status = r.get("taskStatus")
            if status != last_status:
                logger.debug(f"状态: {last_status} -> {status}")
                last_status = status

            if status in ("SUCCESS", "COMPLETED"):
                logger.debug(f"任务完成 (taskId={task_id})")
                return r.get("data", {})
            elif status in ("FAILURE", "CANCELED"):
                raise RuntimeError(f"任务失败: {r}")
            elif status in ("PENDING", "PROCESSING"):
                continue
            else:
                raise RuntimeError(f"未知状态: {status}")

        raise RuntimeError(f"轮询超时 ({max_timeout}s)")


# ========================== ActionRouter ==========================

# JS 模板：坐标型点击（完整 mouse 事件链）
JS_CLICK = """(() => {{
  const x = {x}, y = {y};
  const el = document.elementFromPoint(x, y);
  if (!el) return 'no_element';
  const opts = {{clientX: x, clientY: y, bubbles: true, cancelable: true, view: window}};
  el.dispatchEvent(new MouseEvent('mousedown', opts));
  el.dispatchEvent(new MouseEvent('mouseup', opts));
  el.dispatchEvent(new MouseEvent('click', opts));
  return 'ok';
}})()"""

JS_DBLCLICK = """(() => {{
  const x = {x}, y = {y};
  const el = document.elementFromPoint(x, y);
  if (!el) return 'no_element';
  const opts = {{clientX: x, clientY: y, bubbles: true, cancelable: true, view: window}};
  el.dispatchEvent(new MouseEvent('mousedown', opts));
  el.dispatchEvent(new MouseEvent('mouseup', opts));
  el.dispatchEvent(new MouseEvent('click', opts));
  el.dispatchEvent(new MouseEvent('mousedown', opts));
  el.dispatchEvent(new MouseEvent('mouseup', opts));
  el.dispatchEvent(new MouseEvent('click', opts));
  el.dispatchEvent(new MouseEvent('dblclick', opts));
  return 'ok';
}})()"""

JS_RIGHTCLICK = """(() => {{
  const x = {x}, y = {y};
  const el = document.elementFromPoint(x, y);
  if (!el) return 'no_element';
  const opts = {{clientX: x, clientY: y, bubbles: true, cancelable: true, view: window, button: 2}};
  el.dispatchEvent(new MouseEvent('mousedown', opts));
  el.dispatchEvent(new MouseEvent('mouseup', opts));
  el.dispatchEvent(new MouseEvent('contextmenu', opts));
  return 'ok';
}})()"""

JS_HOVER = """(() => {{
  const x = {x}, y = {y};
  const el = document.elementFromPoint(x, y);
  if (!el) return 'no_element';
  const opts = {{clientX: x, clientY: y, bubbles: true, cancelable: true, view: window}};
  el.dispatchEvent(new MouseEvent('mouseover', opts));
  el.dispatchEvent(new MouseEvent('mouseenter', {{...opts, bubbles: false}}));
  el.dispatchEvent(new MouseEvent('mousemove', opts));
  return 'ok';
}})()"""

JS_DRAG = """(() => {{
  const sx = {sx}, sy = {sy}, ex = {ex}, ey = {ey};
  const el = document.elementFromPoint(sx, sy);
  if (!el) return 'no_element';
  const mkOpts = (x, y) => ({{clientX: x, clientY: y, bubbles: true, cancelable: true, view: window}});
  el.dispatchEvent(new MouseEvent('mousedown', mkOpts(sx, sy)));
  const steps = 10;
  for (let i = 1; i <= steps; i++) {{
    const mx = sx + (ex - sx) * i / steps;
    const my = sy + (ey - sy) * i / steps;
    el.dispatchEvent(new MouseEvent('mousemove', mkOpts(mx, my)));
  }}
  el.dispatchEvent(new MouseEvent('mouseup', mkOpts(ex, ey)));
  return 'ok';
}})()"""

JS_FOCUS_CLICK = """(() => {{
  const x = {x}, y = {y};
  const el = document.elementFromPoint(x, y);
  if (!el) return 'no_element';
  const opts = {{clientX: x, clientY: y, bubbles: true, cancelable: true, view: window}};
  el.dispatchEvent(new MouseEvent('mousedown', opts));
  el.dispatchEvent(new MouseEvent('mouseup', opts));
  el.dispatchEvent(new MouseEvent('click', opts));
  if (el.focus) el.focus();
  return 'ok';
}})()"""

JS_SCROLL_AT = """(() => {{
  const x = {x}, y = {y}, dx = {delta_x}, dy = {delta_y};
  const el = document.elementFromPoint(x, y);
  if (!el) return 'no_element_at_point';

  // Phase 1: dispatch WheelEvent (triggers native listeners)
  el.dispatchEvent(new WheelEvent('wheel', {{
    clientX: x, clientY: y, deltaX: dx, deltaY: dy, deltaMode: 0,
    bubbles: true, cancelable: true, view: window
  }}));

  // Phase 2: find nearest scrollable ancestor
  let cur = el;
  while (cur && cur !== document.documentElement && cur !== document.body) {{
    const canV = cur.scrollHeight > cur.clientHeight + 2;
    const canH = cur.scrollWidth > cur.clientWidth + 2;
    if (canV || canH) {{
      const bT = cur.scrollTop, bL = cur.scrollLeft;
      if (dy && canV) cur.scrollTop += dy;
      if (dx && canH) cur.scrollLeft += dx;
      if (cur.scrollTop !== bT || cur.scrollLeft !== bL) {{
        cur.dispatchEvent(new Event('scroll', {{bubbles: true}}));
        return 'scrolled_container:' + cur.tagName + '(' + cur.className.slice(0,50) + ')';
      }}
    }}
    cur = cur.parentElement;
  }}

  // Phase 3: page-level fallback
  const bX = window.scrollX, bY = window.scrollY;
  window.scrollBy(dx, dy);
  if (window.scrollX !== bX || window.scrollY !== bY) {{
    return 'scrolled_page:dx=' + (window.scrollX - bX) + ',dy=' + (window.scrollY - bY) + 'px';
  }}
  return 'wheel_dispatched:' + el.tagName + '(' + el.className.slice(0,50) + ')';
}})()"""


class ActionRouter:
    """根据 CPU Service 返回的 action 分流到 browser-use 命令"""

    def __init__(self, session: str = "default"):
        self.session = session
        self._dpr = None
        self._scale_x: Optional[float] = None
        self._scale_y: Optional[float] = None
        self._viewport_size: Optional[tuple] = None
        self._screenshot_size: Optional[tuple] = None
        self._known_tab_count: int = 0

    @staticmethod
    def _parse_eval_output(raw: str) -> str:
        """剥离 browser-use eval 输出的 'result: ' 前缀"""
        text = raw.strip()
        if text.lower().startswith("result:"):
            text = text[len("result:"):].strip()
        return text

    def _get_dpr(self) -> float:
        if self._dpr is None:
            try:
                result = bu("eval", "window.devicePixelRatio", session=self.session)
                if result.returncode == 0:
                    self._dpr = float(self._parse_eval_output(result.stdout))
                else:
                    self._dpr = 1.0
            except Exception:
                self._dpr = 1.0
            logger.debug(f"DPR: {self._dpr}")
        return self._dpr

    def _get_viewport_size(self) -> Optional[tuple]:
        """通过 JS 获取浏览器视口的 CSS 尺寸 (innerWidth, innerHeight)"""
        try:
            w_result = bu("eval", "window.innerWidth", session=self.session)
            h_result = bu("eval", "window.innerHeight", session=self.session)
            if w_result.returncode == 0 and h_result.returncode == 0:
                w = float(self._parse_eval_output(w_result.stdout))
                h = float(self._parse_eval_output(h_result.stdout))
                return (w, h)
        except Exception as e:
            logger.warning(f"获取视口尺寸失败: {e}")
        return None

    def update_coord_mapping(self, screenshot_w: int, screenshot_h: int):
        """根据截图像素尺寸和视口 CSS 尺寸计算坐标缩放因子。

        scale_x = viewport_css_w / screenshot_px_w
        scale_y = viewport_css_h / screenshot_px_h

        若无法获取视口尺寸，回退到 1/DPR。
        """
        self._screenshot_size = (screenshot_w, screenshot_h)
        viewport = self._get_viewport_size()

        if viewport and screenshot_w > 0 and screenshot_h > 0:
            self._viewport_size = viewport
            self._scale_x = viewport[0] / screenshot_w
            self._scale_y = viewport[1] / screenshot_h
            logger.debug(f"坐标映射: 截图={screenshot_w}x{screenshot_h}, "
                         f"视口={viewport[0]}x{viewport[1]}, "
                         f"scale=({self._scale_x:.4f}, {self._scale_y:.4f})")
        else:
            dpr = self._get_dpr()
            self._scale_x = 1.0 / dpr
            self._scale_y = 1.0 / dpr
            logger.debug(f"视口尺寸不可用，回退到 DPR={dpr}, scale={self._scale_x:.4f}")

    def _get_scale(self) -> tuple:
        """返回 (scale_x, scale_y)，未设置时回退到 1/DPR"""
        if self._scale_x is not None and self._scale_y is not None:
            return (self._scale_x, self._scale_y)
        dpr = self._get_dpr()
        return (1.0 / dpr, 1.0 / dpr)

    def _to_css(self, x, y) -> tuple:
        """截图像素坐标 -> CSS 坐标"""
        sx, sy = self._get_scale()
        css_x, css_y = float(x) * sx, float(y) * sy
        logger.debug(f"坐标转换: ({x}, {y}) -> CSS ({css_x:.1f}, {css_y:.1f})  scale=({sx:.4f}, {sy:.4f})")
        return css_x, css_y

    def reset_dpr(self):
        """导航后 DPR / 视口可能变化，需重置"""
        self._dpr = None
        self._scale_x = None
        self._scale_y = None
        self._viewport_size = None
        self._screenshot_size = None

    def _get_tab_count(self) -> int:
        """通过 browser-use switch 的错误输出解析真实 tab 数量。

        browser-use switch 对无效索引返回 exit code 0，
        但 stdout 包含 'error: Invalid tab index N. Available: 0-M'，
        从中可提取 M+1 = tab 数量。
        """
        result = bu("switch", "99999", session=self.session, timeout=5)
        stdout = result.stdout.strip()
        m = re.search(r'Available:\s*0-(\d+)', stdout)
        if m:
            return int(m.group(1)) + 1
        if "switched:" in stdout:
            return 100000
        return -1

    def _get_tab_url(self, index: int) -> str:
        """切换到指定 tab 并获取其 URL，失败返回空字符串。"""
        try:
            sw = bu("switch", str(index), session=self.session, timeout=5)
            if sw.returncode != 0 or "error" in sw.stdout.lower():
                return ""
            result = bu("eval", "window.location.href", session=self.session, timeout=5)
            if result.returncode == 0:
                return self._parse_eval_output(result.stdout)
        except subprocess.TimeoutExpired:
            logger.debug(f"获取 tab {index} URL 超时")
        except Exception as e:
            logger.debug(f"获取 tab {index} URL 异常: {e}")
        return ""

    def init_tab_context(self):
        """启动时检测 tab 数量，过滤非 http(s) tab，切换到最后一个有效页面。

        使用 profile 的 real Chrome 可能包含 chrome://newtab、chrome-extension://
        等非 http 页面，对这些页面执行 CDP 截图可能会挂起。
        """
        count = self._get_tab_count()
        if count <= 0:
            logger.warning("无法检测 tab 数量，保持当前 tab")
            self._known_tab_count = 1
            return

        self._known_tab_count = count

        tabs: list[tuple[int, str]] = []
        for i in range(count):
            url = self._get_tab_url(i)
            tabs.append((i, url))

        http_tabs = [(idx, url) for idx, url in tabs
                     if url.startswith("http://") or url.startswith("https://")]

        if http_tabs:
            target_idx, target_url = http_tabs[-1]
        else:
            target_idx = count - 1
            target_url = tabs[-1][1] if tabs else "(unknown)"
            logger.warning("未找到 http(s) tab，回退到最后一个 tab")

        selected = {idx for idx, _ in http_tabs} if http_tabs else {target_idx}
        for idx, url in tabs:
            if idx == target_idx:
                logger.info(f"  tab[{idx}]: {url or '(unknown)'}  <- 选中")
            elif idx not in selected:
                logger.warning(f"  tab[{idx}]: {url or '(unknown)'}  (已跳过，非 http 页面)")
            else:
                logger.info(f"  tab[{idx}]: {url or '(unknown)'}")

        bu("switch", str(target_idx), session=self.session, timeout=5)
        self.reset_dpr()
        logger.info(f"初始化: 共 {count} 个 tab, 选中 tab[{target_idx}]: {target_url}")

    def check_and_switch_to_latest_tab(self) -> bool:
        """检查是否有新 tab 打开，如果有则切换到最新的 tab。

        通过实际 tab 数量变化来判断是否有新 tab，
        避免 browser-use switch 对不存在索引返回 0 导致误判。

        Returns:
            True 表示已切换到新 tab，False 表示无新 tab。
        """
        try:
            new_count = self._get_tab_count()
            if new_count <= 0 or new_count <= self._known_tab_count:
                return False

            last_idx = new_count - 1
            bu("switch", str(last_idx), session=self.session, timeout=5)
            self._known_tab_count = new_count
            self.reset_dpr()
            logger.info(f"检测到新 tab, 切换到 index={last_idx} (共 {new_count} 个)")
            return True
        except Exception as e:
            logger.debug(f"tab 检测/切换异常: {e}")
            return False

    def execute(self, action_type: str, action_param: dict) -> bool:
        """执行一个动作，返回 True 表示任务结束"""
        op = action_type.lower()
        param = action_param

        if op in ("stop", "finished"):
            return True

        if op == "wait":
            time.sleep(param.get("time", 2))
            return False

        has_index = "index" in param
        has_coords = (("x" in param and "y" in param)
                      or ("start_x" in param and "start_y" in param))

        if has_index:
            return self._exec_index(op, param)
        elif has_coords:
            return self._exec_coord(op, param)
        else:
            return self._exec_plain(op, param)

    def _exec_index(self, op: str, param: dict) -> bool:
        """Index 路径：直接调用 browser-use 原生命令"""
        idx = str(param["index"])
        s = self.session

        if op == "click":
            bu("click", idx, session=s)
        elif op == "left_double":
            bu("dblclick", idx, session=s)
        elif op == "right_single":
            bu("rightclick", idx, session=s)
        elif op == "hover":
            bu("hover", idx, session=s)
        elif op == "type_text_at":
            content = param.get("content", "")
            bu("input", idx, content, session=s)
        elif op == "select":
            value = param.get("value", "")
            bu("select", idx, value, session=s)
        elif op == "scroll":
            return self._scroll_at_index(idx, param)
        else:
            logger.warning(f"Index 路径不支持动作 '{op}'，降级到 plain")
            return self._exec_plain(op, param)

        time.sleep(0.5)
        return False

    def _scroll_at_index(self, idx: str, param: dict) -> bool:
        """在指定 index 元素内部滚动：获取 bbox 中心坐标后用 JS_SCROLL_AT 派发事件"""
        s = self.session
        delta_x, delta_y = self._parse_scroll_delta(param)

        try:
            bbox_result = bu("get", "bbox", idx, session=s)
            bbox_text = bbox_result.stdout.strip()
            m = re.search(
                r"'x':\s*(-?\d+).*?'y':\s*(-?\d+).*?'width':\s*(\d+).*?'height':\s*(\d+)",
                bbox_text,
            )
            if m:
                bx, by, bw, bh = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
                cx, cy = bx + bw // 2, by + bh // 2
                result = bu("eval", JS_SCROLL_AT.format(x=cx, y=cy, delta_x=delta_x, delta_y=delta_y), session=s)
                logger.debug(f"Index scroll: dx={delta_x},dy={delta_y} @ ({cx},{cy}) element={idx} -> {result.stdout.strip()[:100]}")
            else:
                logger.warning(f"无法获取元素 bbox (index={idx}): {bbox_text[:100]}，降级到 plain scroll")
                return self._exec_plain("scroll", param)
        except Exception as e:
            logger.warning(f"Index scroll 失败: {e}，降级到 plain scroll")
            return self._exec_plain("scroll", param)

        time.sleep(0.5)
        return False

    def _extract_coords(self, param: dict) -> tuple:
        """从 param 中提取起点 CSS 坐标，兼容 x/y 和 start_x/start_y 两种格式"""
        if "x" in param and "y" in param:
            return self._to_css(param["x"], param["y"])
        return self._to_css(param["start_x"], param["start_y"])

    def _extract_end_coords(self, param: dict) -> tuple:
        """从 param 中提取终点 CSS 坐标，回退到起点"""
        return self._to_css(
            param.get("end_x", param.get("start_x", param.get("x", 0))),
            param.get("end_y", param.get("start_y", param.get("y", 0))),
        )

    def _parse_scroll_delta(self, param: dict) -> tuple:
        """从 scroll 动作参数中解析滚动量（CSS 像素），返回 (delta_x, delta_y)。

        方向约定：delta_y 正值=向下/负值=向上，delta_x 正值=向右/负值=向左。

        CPU Service 返回的 scroll 动作有多种格式：
        1. delta_x / delta_y 字段直接指定
        2. start_x/end_x, start_y/end_y 坐标差值
        3. direction 字段中嵌入 amount，如 "down, amount=500, index=1051"
        需要综合这些信息得到正确的滚动方向和量。
        """
        sx, sy = self._get_scale()

        if param.get("delta_x") or param.get("delta_y"):
            dx = int(int(param.get("delta_x", 0)) * sx)
            dy = int(int(param.get("delta_y", 0)) * sy)
            return (dx, dy)

        direction_str = str(param.get("direction", "down")).strip()
        dir_lower = direction_str.split(",")[0].strip().lower()

        amount_match = re.search(r'amount\s*=\s*(\d+)', direction_str)
        if amount_match:
            raw_amount = int(amount_match.group(1))
            scale = sy if dir_lower in ("up", "down", "") else sx
            amount = int(raw_amount * scale)
        elif dir_lower in ("up", "down"):
            raw_delta = abs(int(float(param.get("start_y", 0))) - int(float(param.get("end_y", 0))))
            amount = max(int(raw_delta * sy), 300)
        elif dir_lower in ("left", "right"):
            raw_delta = abs(int(float(param.get("start_x", 0))) - int(float(param.get("end_x", 0))))
            amount = max(int(raw_delta * sx), 300)
        else:
            amount = 300

        if dir_lower == "up":
            return (0, -amount)
        elif dir_lower == "down":
            return (0, amount)
        elif dir_lower == "left":
            return (-amount, 0)
        elif dir_lower == "right":
            return (amount, 0)
        else:
            return (0, amount)

    def _exec_coord(self, op: str, param: dict) -> bool:
        """Coordinate 路径：优先使用 browser-use 原生命令（CDP trusted events），
        不支持的操作降级为 JS 注入。"""
        raw_x = param.get("x", param.get("start_x", "?"))
        raw_y = param.get("y", param.get("start_y", "?"))
        css_x, css_y = self._extract_coords(param)
        ix, iy = int(round(css_x)), int(round(css_y))
        logger.debug(f"坐标执行: {op} 原始=({raw_x}, {raw_y}) -> CSS=({css_x:.1f}, {css_y:.1f})")
        s = self.session

        if op == "click":
            bu("click", str(ix), str(iy), session=s)
        elif op == "left_double":
            bu("eval", JS_DBLCLICK.format(x=css_x, y=css_y), session=s)
        elif op == "right_single":
            bu("eval", JS_RIGHTCLICK.format(x=css_x, y=css_y), session=s)
        elif op == "hover":
            bu("eval", JS_HOVER.format(x=css_x, y=css_y), session=s)
        elif op == "type_text_at":
            bu("click", str(ix), str(iy), session=s)
            time.sleep(0.3)
            if param.get("clear", "True") == "True":
                mod = "Meta+a" if platform_mod.system() == "Darwin" else "Control+a"
                bu("keys", mod, session=s)
                bu("keys", "Backspace", session=s)
            content = param.get("content", "")
            if content:
                bu("type", content, session=s)
        elif op == "drag":
            sx, sy = css_x, css_y
            ex, ey = self._extract_end_coords(param)
            bu("eval", JS_DRAG.format(sx=sx, sy=sy, ex=ex, ey=ey), session=s)
        elif op == "scroll":
            delta_x, delta_y = self._parse_scroll_delta(param)
            result = bu("eval", JS_SCROLL_AT.format(x=css_x, y=css_y, delta_x=delta_x, delta_y=delta_y), session=s)
            logger.debug(f"智能滚动结果: dx={delta_x},dy={delta_y} @ ({css_x},{css_y}) -> {result.stdout.strip()[:100]}")
        else:
            logger.warning(f"Coordinate 路径不支持动作 '{op}'，降级到 plain")
            return self._exec_plain(op, param)

        time.sleep(0.5)
        return False

    def _exec_plain(self, op: str, param: dict) -> bool:
        """Plain 路径：无位置参数的通用动作"""
        s = self.session

        if op == "type":
            bu("type", param.get("content", ""), session=s)
        elif op == "scroll":
            dx, dy = self._parse_scroll_delta(param)
            if dy:
                direction = "down" if dy > 0 else "up"
                bu("scroll", direction, "--amount", str(abs(dy)), session=s)
            if dx:
                logger.warning(f"Plain scroll: dx={dx} not supported")
        elif op == "scroll_to_bottom":
            bu("keys", "End", session=s)
        elif op == "hotkey":
            key = param.get("key", "")
            if key:
                bu("keys", key, session=s)
        elif op == "goto":
            url = param.get("url", "")
            if url:
                bu("open", url, session=s)
                self.reset_dpr()
        elif op == "refresh":
            bu("eval", "location.reload()", session=s)
        elif op == "clear_text":
            mod = "Meta+a" if platform_mod.system() == "Darwin" else "Control+a"
            bu("keys", mod, session=s)
            bu("keys", "Backspace", session=s)
        elif op == "back":
            bu("back", session=s)
        elif op == "drag":
            sx, sy = self._to_css(param.get("start_x", 0), param.get("start_y", 0))
            ex, ey = self._to_css(param.get("end_x", 0), param.get("end_y", 0))
            bu("eval", JS_DRAG.format(sx=sx, sy=sy, ex=ex, ey=ey), session=s)
        else:
            logger.warning(f"不支持的动作: '{op}' param={param}")

        time.sleep(0.5)
        return False


# ========================== External Tool Registry ==========================

class ExternalToolRegistry:
    """管理 external_tools 定义和执行

    支持两类工具：
    1. 内置浏览器工具：click, dblclick, type 等，通过 ActionRouter 执行
    2. 用户自定义工具：从 JSON 配置加载，通过 shell 命令或默认响应执行
    """

    def __init__(self, router: ActionRouter):
        self.router = router
        self._handlers: Dict[str, Any] = {}
        self._definitions: Dict[str, dict] = {}
        self._register_browser_tools()

    def _register_browser_tools(self):
        pass

    def _register(self, name: str, description: str, parameters: dict, handler):
        self._definitions[name] = {
            "name": name,
            "description": description,
            "parameters": parameters,
        }
        self._handlers[name] = handler

    def load_user_tools(self, config_path: str):
        """从 JSON 文件加载用户自定义工具

        JSON 格式示例:
        [
            {
                "name": "open_url",
                "description": "跳转指定url",
                "parameters": {"type": "object", "properties": {...}, "required": [...]},
                "command": "adb shell am start -a android.intent.action.VIEW -d '{url}'"
            }
        ]

        如果提供 command 字段，将通过 shell 执行；否则返回默认响应。
        """
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        tools = config if isinstance(config, list) else config.get("external_tools", [])
        for tool_def in tools:
            name = tool_def["name"]
            self._definitions[name] = {
                "name": name,
                "description": tool_def["description"],
                "parameters": tool_def["parameters"],
            }
            command = tool_def.get("command")
            if command:
                self._handlers[name] = self._make_shell_handler(command)
            else:
                self._handlers[name] = self._make_default_handler(name)

        logger.debug(f"加载 {len(tools)} 个自定义工具: {[t['name'] for t in tools]}")

    @staticmethod
    def _make_shell_handler(command_template: str):
        def handler(args: dict) -> str:
            cmd = command_template
            for k, v in args.items():
                cmd = cmd.replace(f"{{{k}}}", str(v))
            try:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    return result.stdout.strip() or "执行成功"
                return f"执行失败 (exit {result.returncode}): {result.stderr.strip()[:200]}"
            except Exception as e:
                return f"执行失败: {e}"
        return handler

    @staticmethod
    def _make_default_handler(tool_name: str):
        def handler(args: dict) -> str:
            return f"工具 {tool_name} 已调用，参数: {json.dumps(args, ensure_ascii=False)}"
        return handler

    def get_definitions(self, include_browser_tools: bool = True, tool_names: list = None) -> list:
        """获取 external_tools 定义列表"""
        defs = []
        for name, defn in self._definitions.items():
            if not include_browser_tools and name.startswith("browser_"):
                continue
            if tool_names and name not in tool_names:
                continue
            defs.append(defn)
        return defs

    def execute(self, tool_name: str, arguments: dict) -> str:
        """执行工具，返回 tool_response 字符串"""
        if tool_name not in self._handlers:
            return f"未知工具: {tool_name}"
        try:
            return self._handlers[tool_name](arguments)
        except Exception as e:
            return f"执行失败: {tool_name} - {e}"

    def has_tool(self, name: str) -> bool:
        return name in self._handlers


# ========================== HTML 可视化 ==========================

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: Arial, sans-serif; height: 100vh; display: flex; flex-direction: column; }}
  iframe {{ flex: 1; width: 100%; border: none; }}
</style>
</head>
<body>
<iframe id="visIframe" src="https://1d.alibaba-inc.com/apps/02mwMFfz"></iframe>
<script>
const TRAJECTORY_DATA = {json_data};
let dataSent = false;
window.addEventListener('message', (event) => {{
  if (event.data && event.data.type === 'IFRAME_READY' && !dataSent) {{
    document.getElementById('visIframe').contentWindow.postMessage({{
      type: 'LOAD_JSON_DATA', data: TRAJECTORY_DATA
    }}, '*');
    dataSent = true;
  }}
}});
</script>
</body>
</html>"""


def generate_vis_html(trajectory: list, output_path: str, title: str = "trajectory") -> str:
    json_str = json.dumps(trajectory, ensure_ascii=False)
    html = HTML_TEMPLATE.format(title=title, json_data=json_str)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    return output_path


# ========================== TaskRunner ==========================

class TaskRunner:
    """AI 任务执行主循环，支持 external_tools（自定义工具）"""

    def __init__(self, session: str = "default", save_dir: str = "",
                 planner_type: str = ""):
        self.session = session
        self.planner_type = planner_type

        if not save_dir:
            ts_dir = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            save_dir = os.path.join("./browser_task_output", ts_dir)
        self.save_dir = os.path.abspath(save_dir)
        os.makedirs(self.save_dir, exist_ok=True)

        self.oss = ImageConvertClient()
        self.cpu = CPUServiceClient(
            base_url=os.getenv("CPU_SERVICE_BASE_URL", DEFAULT_CPU_BASE_URL),
            bizname=os.getenv("CPU_SERVICE_BIZNAME", DEFAULT_CPU_BIZNAME),
            bizchannel=os.getenv("CPU_SERVICE_BIZCHANNEL", DEFAULT_CPU_BIZCHANNEL),
        )
        self.router = ActionRouter(session=session)
        self.tool_registry = ExternalToolRegistry(self.router)

    def _take_screenshot(self, step_name: str) -> Optional[str]:
        """截图并保存到本地，返回文件路径"""
        path = os.path.join(self.save_dir, f"{step_name}.png")
        try:
            result = bu("screenshot", path, session=self.session, timeout=60)
        except subprocess.TimeoutExpired:
            logger.error("截图超时 (60s), 可能 CDP 连接异常")
            return None
        if result.returncode != 0:
            logger.error(f"截图失败: {result.stderr.strip()[:200]}")
            return None
        if os.path.isfile(path):
            return path
        logger.error(f"截图文件未生成: {path}")
        return None

    def _get_screenshot_size(self, path: str) -> list:
        """获取截图的像素尺寸"""
        try:
            img = Image.open(path)
            return [img.width, img.height]
        except Exception:
            return [1920, 1080]

    def _get_state(self) -> str:
        """获取页面状态文本（URL + title + elements）"""
        try:
            result = bu("state", session=self.session, timeout=60)
        except subprocess.TimeoutExpired:
            logger.error("获取 state 超时 (60s), 可能 CDP 连接异常")
            return "[State unavailable]"
        if result.returncode != 0:
            logger.warning(f"获取 state 失败: {result.stderr.strip()[:200]}")
            return "[State unavailable]"
        return result.stdout.strip()


    @staticmethod
    def _parse_tool_calls_from_text(text: str) -> list:
        """从 response 文本中解析 <tool_call> ... </tool_call> 标签为 action 列表"""
        actions = []
        for m in re.finditer(r'<tool_call>\s*(\{.*?\})\s*</tool_call>', text, re.DOTALL):
            try:
                payload = json.loads(m.group(1))
                tool_name = payload.get("name", "")
                arguments = payload.get("arguments", {})
                if tool_name:
                    actions.append({
                        "action_type": "tool_call",
                        "action_param": {
                            "tool_name": tool_name,
                            "arguments": arguments,
                        },
                    })
            except json.JSONDecodeError as e:
                logger.warning(f"解析 <tool_call> JSON 失败: {e}, 原文: {m.group(1)[:100]}")
        return actions

    def run(self, instruction: str, max_steps: int = 20,
            app: str = "taobao", plat: str = "web") -> list:
        """执行 AI 任务，返回 trajectory

        支持两种动作类型：
        1. 常规 GUI 动作 (click/scroll/type 等) - 通过 ActionRouter 执行
        2. tool_call 动作 - 通过 ExternalToolRegistry 执行，tool_response 回传到 history
        """
        trajectory: List[Dict] = []
        history: list = []
        done = False
        step_idx = 0
        last_extend_info: dict = {}

        tool_defs = self.tool_registry.get_definitions(include_browser_tools=True)
        if tool_defs:
            logger.debug(f"已注册 {len(tool_defs)} 个 external_tools: "
                         f"{[t['name'] for t in tool_defs]}")

        logger.info(f"开始任务: {instruction}")
        logger.debug(f"max_steps={max_steps}, session={self.session}")

        self.router.init_tab_context()

        while not done and step_idx < max_steps:
            logger.info(f"===== Step {step_idx + 1}/{max_steps} =====")

            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            uid = uuid.uuid4().hex[:8]

            # 1. 截图
            screenshot_path = self._take_screenshot(f"step_{step_idx+1}_{ts}")
            if not screenshot_path:
                logger.error("截图失败，终止")
                break
            screen_size = self._get_screenshot_size(screenshot_path)

            # 1.5 更新坐标映射（截图尺寸 -> CSS 视口尺寸）
            self.router.update_coord_mapping(screen_size[0], screen_size[1])

            # 2. 上传 OSS
            oss_filename = f"browser_task/{ts}_{uid}.jpg"
            screenshot_url = self.oss.upload_file(screenshot_path, oss_filename)
            if not screenshot_url:
                logger.error("OSS 上传失败，终止")
                break

            # 3. 获取页面状态
            state_text = self._get_state()

            logger.debug(f"截图 [{screen_size[0]}x{screen_size[1]}]")
            logger.debug(f"State: {state_text[:200]}...")

            # 4. CPU Service 推理（带 external_tools）
            try:
                result = self.cpu.predict(
                    instruction=instruction,
                    screenshot_url=screenshot_url,
                    screen_size=screen_size,
                    history=history,
                    app=app, plat=plat,
                    external_tools=tool_defs if tool_defs else None,
                    dom_content=state_text,
                    planner_type=self.planner_type,
                    extend_info=last_extend_info if last_extend_info else None,
                )
            except Exception as e:
                logger.error(f"CPU Service 推理失败: {e}")
                trajectory.append({
                    "instruction": instruction, "step_num": step_idx,
                    "observation": {"screenshot": screenshot_url, "screen_size": screen_size},
                    "planing": f"推理失败: {e}",
                    "action": "finished", "param": {"result": "fail"},
                    "action_timestamp": ts,
                })
                break

            response_text = result.get("response", "")
            actions = result.get("actions", [])
            extend_info = result.get("extend_info", {})
            last_extend_info = extend_info

            logger.debug(f"CPU Service 返回: response 长度={len(response_text)}, "
                         f"actions 数量={len(actions)}")
            for di, act in enumerate(actions):
                act_type = act.get("action_type", "?")
                act_param = act.get("action_param", {})
                logger.debug(f"  action[{di}]: type={act_type}, "
                             f"param={json.dumps(act_param, ensure_ascii=False)[:500]}")

            if not response_text and not actions:
                logger.warning("推理无结果，终止")
                break

            # 从 response 文本中解析 <tool_call> 标签（模型可能以文本形式返回工具调用）
            parsed_tool_calls = self._parse_tool_calls_from_text(response_text)
            if parsed_tool_calls:
                has_tool_call_action = any(a.get("action_type") == "tool_call" for a in actions)
                if not has_tool_call_action:
                    logger.debug(f"从 response 文本中解析到 {len(parsed_tool_calls)} 个 tool_call")
                    actions = parsed_tool_calls + actions

            logger.info(f"思考: {response_text}")
            logger.debug(f"动作数: {len(actions)}")

            # 5. 执行动作（区分 tool_call / GUI / finished）
            current_tool_response = None

            for ai, action in enumerate(actions):
                a_type = action.get("action_type", "")
                a_param = action.get("action_param", {})

                if a_type == "tool_call":
                    # ---- tool_call 路径：通过 ExternalToolRegistry 执行 ----
                    tool_name = a_param.get("tool_name", "")
                    arguments = a_param.get("arguments", {})
                    logger.info(f"  [{ai+1}] tool_call: {tool_name}"
                                f"({json.dumps(arguments, ensure_ascii=False)})")

                    current_tool_response = self.tool_registry.execute(tool_name, arguments)
                    logger.info(f"  tool_response: {current_tool_response}")

                    trajectory.append({
                        "instruction": instruction,
                        "observation": {"screenshot": screenshot_url, "screen_size": screen_size},
                        "planing": response_text,
                        "action": "tool_call", "param": a_param,
                        "tool_response": current_tool_response,
                        "step_num": step_idx, "action_timestamp": ts,
                        "route": "tool_call",
                        "extend_info": extend_info,
                    })
                    break

                elif a_type in ("stop", "finished"):
                    # ---- 任务完成 ----
                    done = True
                    finish_result = a_param.get("result", "N/A")
                    finish_content = a_param.get("content", "")
                    finish_data = a_param.get("data")
                    logger.info(f"  [{ai+1}] 任务完成 ({a_type}) result={finish_result}")
                    if finish_content:
                        logger.debug(f"  finished content ({len(finish_content)} chars): "
                                     f"{finish_content[:500]}{'...' if len(finish_content) > 500 else ''}")
                    else:
                        logger.warning(f"  finished content 为空!")
                    if finish_data:
                        data_keys = list(finish_data.keys()) if isinstance(finish_data, dict) else type(finish_data).__name__
                        logger.debug(f"  finished data keys: {data_keys}")
                    else:
                        logger.debug(f"  finished data 为空")
                    logger.debug(f"  finished 完整 param: {json.dumps(a_param, ensure_ascii=False)[:1000]}")

                    if finish_result == "fail" and "result='success'" in response_text:
                        logger.warning(
                            f"检测到矛盾: planner 文本中包含 result='success'，"
                            f"但 CPU Service 返回的 action_param.result='fail'。"
                            f"可能是 content 过长导致解析截断 "
                            f"(planner response 长度: {len(response_text)} chars)")

                    trajectory.append({
                        "instruction": instruction,
                        "observation": {"screenshot": screenshot_url, "screen_size": screen_size},
                        "planing": response_text,
                        "action": a_type, "param": a_param,
                        "step_num": step_idx, "action_timestamp": ts,
                        "route": "finished",
                        "extend_info": extend_info,
                    })
                    break

                elif self.tool_registry.has_tool(a_type):
                    # ---- 模型直接返回工具名作为 action_type（未包装为 tool_call）----
                    logger.info(f"  [{ai+1}] tool_call: {a_type}"
                                f"({json.dumps(a_param, ensure_ascii=False)})")

                    current_tool_response = self.tool_registry.execute(a_type, a_param)
                    logger.info(f"  tool_response: {current_tool_response}")

                    trajectory.append({
                        "instruction": instruction,
                        "observation": {"screenshot": screenshot_url, "screen_size": screen_size},
                        "planing": response_text,
                        "action": "tool_call", "param": {"tool_name": a_type, "arguments": a_param},
                        "tool_response": current_tool_response,
                        "step_num": step_idx, "action_timestamp": ts,
                        "route": "tool_call_from_action_type",
                        "extend_info": extend_info,
                    })
                    break

                else:
                    # ---- 常规 GUI 动作：通过 ActionRouter 执行 ----
                    route = ("index" if "index" in a_param
                             else ("coord" if ("x" in a_param and "y" in a_param) else "plain"))
                    logger.info(f"  [{ai+1}] {a_type} ({route}) "
                                f"{json.dumps(a_param, ensure_ascii=False)}")

                    trajectory.append({
                        "instruction": instruction,
                        "observation": {"screenshot": screenshot_url, "screen_size": screen_size},
                        "planing": response_text,
                        "action": a_type, "param": a_param,
                        "step_num": step_idx, "action_timestamp": ts,
                        "route": route,
                        "extend_info": extend_info,
                    })

                    try:
                        done = self.router.execute(a_type, a_param)
                    except Exception as e:
                        logger.error(f"动作执行失败: {e}")
                        trajectory.append({
                            "instruction": instruction, "step_num": step_idx,
                            "observation": {"screenshot": screenshot_url, "screen_size": screen_size},
                            "planing": f"执行报错: {e}",
                            "action": "finished", "param": {"result": "fail"},
                            "action_timestamp": ts,
                        })
                        done = True
                        break

                    if done:
                        logger.info(f"任务完成 (action={a_type})")
                        break

                    if a_type in ("click", "left_double", "right_single"):
                        time.sleep(1)
                        self.router.check_and_switch_to_latest_tab()
                    time.sleep(0.5)

            # 6. 构建 history 条目（符合 GUI Agent 文档规范）
            history_entry = {
                "obs": {"screenshot_url": screenshot_url, "screen_size": screen_size},
                "response": response_text,
                "actions": actions,
            }
            if current_tool_response is not None:
                history_entry["tool_response"] = current_tool_response
            if extend_info:
                history_entry["extend_info"] = extend_info
            history.append(history_entry)

            step_idx += 1

        # 最终截图
        final_ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        final_path = self._take_screenshot(f"final_{final_ts}")
        if final_path:
            final_uid = uuid.uuid4().hex[:8]
            final_url = self.oss.upload_file(final_path, f"browser_task/final_{final_ts}_{final_uid}.jpg")
            if final_url:
                final_size = self._get_screenshot_size(final_path)
                trajectory.append({
                    "instruction": instruction, "step_num": step_idx,
                    "observation": {"screenshot": final_url, "screen_size": final_size},
                    "planing": os.path.abspath(final_path),
                    "action": "final_screenshot", "param": {},
                    "action_timestamp": final_ts,
                })

        # 保存 trajectory
        traj_path = os.path.join(self.save_dir, "trajectory.json")
        with open(traj_path, "w", encoding="utf-8") as f:
            json.dump(trajectory, f, ensure_ascii=False, indent=2)

        html_path = os.path.join(self.save_dir, "trajectory.html")
        generate_vis_html(trajectory, html_path, title=f"task_{instruction[:30]}")

        # 报告
        print("=" * 60)
        print("BROWSER TASK REPORT")
        print("=" * 60)
        print(f"Instruction : {instruction}")
        print(f"Steps       : {step_idx}")
        print(f"Done        : {done}")
        print()
        print("--- Step History ---")
        for t in trajectory:
            sn = t.get("step_num", "?")
            act = t.get("action", "?")
            route = t.get("route", "")
            p = json.dumps(t.get("param", {}), ensure_ascii=False)[:]
            plan = t.get("planing", "")[:]
            print(f"  Step {sn}: [{act}] ({route}) {p}")
            if plan:
                print(f"    思考: {plan}")
        print()
        print("--- Output Files ---")
        if final_path:
            print(f"Final screenshot : {os.path.abspath(final_path)}")
        print(f"Trajectory JSON  : {os.path.abspath(traj_path)}")
        print(f"Trajectory HTML  : {os.path.abspath(html_path)}")
        print("=" * 60)

        return trajectory


# ========================== CLI ==========================

def main():
    p = argparse.ArgumentParser(
        description="Browser Task Runner - 基于 browser-use 的 AI 任务执行引擎",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 先用 browser-use 打开浏览器
  browser-use --browser real --profile "Default" open https://www.baidu.com

  # 执行 AI 任务（浏览器操作已内置为 external_tools）
  python browser_task.py --instruction "搜索'天气预报'并记录第一个结果"

  # 任务完成后关闭
  browser-use close
        """,
    )
    p.add_argument("--instruction", required=True, help="任务指令")
    p.add_argument("--max-steps", type=int, default=20, help="最大步数")
    p.add_argument("--session", default="default", help="browser-use session 名称")
    p.add_argument("--save-dir", default="", help="输出目录")
    p.add_argument("--planner-type", default="", help="CPU Service planner 类型")
    p.add_argument("--app", default="taobao", help="应用名")
    p.add_argument("--platform", default="web", help="平台")
    args = p.parse_args()

    runner = TaskRunner(
        session=args.session,
        save_dir=args.save_dir,
        planner_type=args.planner_type,
    )
    runner.run(
        instruction=args.instruction,
        max_steps=args.max_steps,
        app=args.app,
        plat=args.platform,
    )


if __name__ == "__main__":
    main()
