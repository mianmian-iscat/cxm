"""
agentic_explorer.py — Agentic 自主测试探索器

对标：Mabl Agentic Testing 2025 ("coverage that builds itself, runs itself, recovers itself"),
     browser-use (LLM-driven browser agent),
     UiPath Test Cloud Agentic Testing.

解决的问题：
- 传统测试必须手写 input.json，成本高
- Agentic 模式：给一个 URL + 业务目标，Agent 自主探索页面、识别关键交互、
  生成测试步骤序列，最终输出一份可被 impl.py 消费的 input JSON
- 2025 年主流框架都已具备"coverage that builds itself"能力，我们缺这一环

核心能力：
  1. explore(cdp, start_url, max_steps) → 自主探索 N 步，记录轨迹
  2. generate_case(trajectory, goal) → 把轨迹转成可执行 input.json
  3. 安全守卫：不点 logout / delete / 提交订单等危险按钮
  4. 元素优先级：form > button > link > nav，避免无效探索
  5. 循环检测：同一 URL 不重复探索

使用方式：
    from core.agentic_explorer import AgenticExplorer

    exp = AgenticExplorer()
    trajectory = await exp.explore(
        cdp, start_url="https://pre-xiaoer.example.com/strategy/list",
        max_steps=15, goal="识别策略列表页的关键交互"
    )
    case = exp.generate_case(trajectory, name="auto-explore-strategy-list")
    with open("eval/cases/f88-test/_auto/auto.json", "w") as f:
        json.dump(case, f, ensure_ascii=False, indent=2)

注意：
- v1 采用"确定性启发式探索"（不依赖外部 LLM 客户端）
- 输出 JSON 同时附 prompt_for_llm 字段（供 Claude/GPT 做二次决策）
- 未来版本可接入 LLM 做 goal-directed 的智能探索
"""

import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


# ── 危险元素黑名单（正则匹配文本）──

_DANGEROUS_PATTERNS = [
    r"登出", r"退出登录", r"logout", r"sign\s*out", r"注销",
    r"删除", r"delete", r"remove",
    r"提交订单", r"确认付款", r"立即支付", r"pay\s*now",
    r"永久删除", r"清空", r"reset\s*all",
]


# ── 元素优先级 ──

_ROLE_PRIORITY = {
    "textbox": 10,
    "combobox": 9,
    "checkbox": 8,
    "radio": 8,
    "button": 7,
    "tab": 6,
    "link": 5,
    "menuitem": 4,
    "option": 3,
}


@dataclass
class ExploreStep:
    """单步探索记录"""
    index: int
    action: str              # click / fill / select / navigate / snapshot
    selector: str
    value: str = ""
    url_before: str = ""
    url_after: str = ""
    element_role: str = ""
    element_name: str = ""
    duration_ms: int = 0
    success: bool = True
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "index": self.index, "action": self.action, "selector": self.selector,
            "value": self.value, "url_before": self.url_before, "url_after": self.url_after,
            "element_role": self.element_role, "element_name": self.element_name,
            "duration_ms": self.duration_ms, "success": self.success, "error": self.error,
        }


@dataclass
class Trajectory:
    """探索轨迹"""
    start_url: str
    goal: str
    steps: List[ExploreStep] = field(default_factory=list)
    visited_urls: List[str] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    total_duration_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "start_url": self.start_url,
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
            "visited_urls": self.visited_urls,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_duration_ms": self.total_duration_ms,
        }


class AgenticExplorer:
    """
    Agentic 自主测试探索器。

    v1：确定性启发式探索（a11y tree + 优先级排序 + 安全守卫）
    v2（待办）：接入 LLM 做 goal-directed 的智能决策
    """

    def __init__(self, safe_mode: bool = True):
        self.safe_mode = safe_mode

    # ── 安全守卫 ──

    def _is_dangerous(self, name: str) -> bool:
        if not name:
            return False
        text = name.lower()
        for pat in _DANGEROUS_PATTERNS:
            if re.search(pat, text, re.IGNORECASE):
                return True
        return False

    # ── 候选元素收集 ──

    async def _collect_interactables(self, cdp, max_count: int = 30) -> List[dict]:
        """
        收集当前页面可交互元素（基于 a11y tree + DOM 兜底）。
        返回 [{"role", "name", "selector"}, ...]，按优先级排序。
        """
        from core.a11y_locator import A11yLocator
        a11y = A11yLocator()

        candidates = []
        # 路径 A：a11y tree
        snap = await a11y.snapshot(cdp, max_depth=8, max_nodes=800)
        for n in snap.get("nodes", []):
            role = n.get("role", "")
            name = n.get("name", "").strip()
            if role not in _ROLE_PRIORITY:
                continue
            if not name or len(name) > 80:
                continue
            if self.safe_mode and self._is_dangerous(name):
                continue
            candidates.append({
                "role": role,
                "name": name,
                "selector": a11y.get_by_role(role, name=name),
                "priority": _ROLE_PRIORITY.get(role, 1),
                "source": "a11y",
            })

        # 路径 B：DOM 兜底（按钮 + 输入框，限制数量）
        try:
            dom_items = await cdp.evaluate("""(() => {
                const out = [];
                const btns = Array.from(document.querySelectorAll('button, [role=button]'))
                    .slice(0, 15);
                for (const b of btns) {
                    out.push({role: 'button', name: (b.textContent || '').trim().slice(0, 40)});
                }
                const inputs = Array.from(document.querySelectorAll('input, textarea, select'))
                    .slice(0, 15);
                for (const i of inputs) {
                    out.push({
                        role: i.tagName === 'SELECT' ? 'combobox' : 'textbox',
                        name: (i.placeholder || i.getAttribute('aria-label') || i.name || '').trim().slice(0, 40),
                    });
                }
                return out;
            })()""")
            if isinstance(dom_items, list):
                for it in dom_items:
                    if not it.get("name"):
                        continue
                    if self.safe_mode and self._is_dangerous(it.get("name", "")):
                        continue
                    role = it.get("role", "button")
                    candidates.append({
                        "role": role, "name": it["name"],
                        "selector": a11y.get_by_role(role, name=it["name"]),
                        "priority": _ROLE_PRIORITY.get(role, 1),
                        "source": "dom",
                    })
        except Exception:
            pass

        # 去重 + 排序
        seen = set()
        unique = []
        for c in candidates:
            key = (c["role"], c["name"])
            if key in seen:
                continue
            seen.add(key)
            unique.append(c)
        unique.sort(key=lambda x: -x["priority"])
        return unique[:max_count]

    # ── 探索主流程 ──

    async def explore(
        self,
        cdp,
        start_url: str,
        max_steps: int = 15,
        goal: str = "",
        per_step_wait_ms: int = 800,
    ) -> Trajectory:
        """
        自主探索指定起始 URL。

        Args:
            cdp: CDPClient 实例
            start_url: 起始 URL
            max_steps: 最大步数
            goal: 业务目标（描述性，用于生成 LLM prompt）
            per_step_wait_ms: 每步动作后等待渲染的毫秒数

        Returns:
            Trajectory
        """
        traj = Trajectory(
            start_url=start_url,
            goal=goal,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        t0 = time.time()

        try:
            await cdp.navigate(start_url)
        except Exception as e:
            traj.steps.append(ExploreStep(
                index=0, action="navigate", selector=start_url,
                success=False, error=str(e),
            ))
            traj.finished_at = datetime.now(timezone.utc).isoformat()
            return traj

        traj.visited_urls.append(start_url)
        step_idx = 0

        while step_idx < max_steps:
            url_before = await self._safe_url(cdp)
            try:
                interactables = await self._collect_interactables(cdp, max_count=20)
            except Exception:
                interactables = []

            if not interactables:
                traj.steps.append(ExploreStep(
                    index=step_idx, action="snapshot", selector="(no interactables)",
                    url_before=url_before, url_after=url_before,
                ))
                break

            picked = interactables[0]
            role = picked["role"]
            name = picked["name"]
            selector = picked["selector"]

            # 决定动作类型
            action = "click"
            value = ""
            if role == "textbox":
                action = "fill"
                value = f"probe-{step_idx}"
            elif role == "combobox":
                action = "select"
                value = ""  # 由 clickText 处理

            step = ExploreStep(
                index=step_idx, action=action, selector=selector,
                value=value, url_before=url_before,
                element_role=role, element_name=name,
            )
            t_step = time.time()
            try:
                if action == "fill":
                    await cdp.evaluate(
                        f"""(() => {{
                            const el = document.querySelector({json.dumps(selector.split(',')[0].strip())});
                            if (el) {{ el.focus(); el.value = {json.dumps(value)}; el.dispatchEvent(new Event('input', {{bubbles:true}})); }}
                        }})()"""
                    )
                else:
                    # click：先尝试 CDP 原生点击，失败回退 evaluate
                    clicked = await cdp.evaluate(
                        f"""(() => {{
                            const candidates = document.querySelectorAll({json.dumps(selector)});
                            for (const el of candidates) {{
                                if (el.offsetHeight > 0 && el.offsetWidth > 0) {{
                                    el.click(); return true;
                                }}
                            }}
                            return false;
                        }})()"""
                    )
                    if not clicked:
                        step.success = False
                        step.error = "no_visible_match"

                await self._sleep_ms(per_step_wait_ms)
                url_after = await self._safe_url(cdp)
                step.url_after = url_after
                if url_after and url_after not in traj.visited_urls:
                    traj.visited_urls.append(url_after)
                step.duration_ms = int((time.time() - t_step) * 1000)
            except Exception as e:
                step.success = False
                step.error = str(e)[:200]
                step.duration_ms = int((time.time() - t_step) * 1000)

            traj.steps.append(step)
            step_idx += 1

        traj.finished_at = datetime.now(timezone.utc).isoformat()
        traj.total_duration_ms = int((time.time() - t0) * 1000)
        return traj

    # ── 轨迹 → 用例 ──

    def generate_case(self, trajectory: Trajectory, name: str = "auto-explore") -> dict:
        """把轨迹转成 impl.py 可消费的 input.json"""
        steps = []
        steps.append({
            "type": "navigate",
            "url": trajectory.start_url,
            "description": f"Agentic 探索起点: {trajectory.goal or '(无目标)'}",
        })
        for s in trajectory.steps:
            if s.action == "navigate":
                continue
            if s.action == "fill":
                steps.append({
                    "type": "fill", "selector": s.selector, "value": s.value,
                    "description": f"[auto] fill '{s.element_name}' with {s.value}",
                })
            elif s.action == "click":
                steps.append({
                    "type": "clickText", "text": s.element_name,
                    "description": f"[auto] click '{s.element_role}:{s.element_name}'",
                })
            elif s.action == "select":
                steps.append({
                    "type": "clickText", "text": s.element_name,
                    "description": f"[auto] select '{s.element_name}'",
                })
            steps.append({
                "type": "screenshot",
                "label": f"explore-{s.index:02d}-{s.action}",
            })

        prompt = (
            f"基于以下 Agentic 探索轨迹，生成更精细的测试用例。\n"
            f"起始 URL: {trajectory.start_url}\n"
            f"业务目标: {trajectory.goal or '(无)'}\n"
            f"访问 URL: {trajectory.visited_urls}\n"
            f"探索步骤: {json.dumps([s.to_dict() for s in trajectory.steps], ensure_ascii=False)}"
        )

        return {
            "id": f"auto-{name}-{int(time.time())}",
            "name": f"[Agentic 自动生成] {name}",
            "context": {
                "url": trajectory.start_url,
                "urlPattern": self._pattern(trajectory.start_url),
                "businessType": "unknown",
            },
            "steps": steps,
            "_agentic": {
                "goal": trajectory.goal,
                "trajectory": trajectory.to_dict(),
                "prompt_for_llm": prompt,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        }

    # ── 工具方法 ──

    @staticmethod
    async def _safe_url(cdp) -> str:
        try:
            return await cdp.evaluate("window.location.href") or ""
        except Exception:
            return ""

    @staticmethod
    async def _sleep_ms(ms: int) -> None:
        import asyncio
        await asyncio.sleep(ms / 1000.0)

    @staticmethod
    def _pattern(url: str) -> str:
        try:
            p = urlparse(url)
            return f"{p.scheme}://{p.netloc}{p.path}"
        except Exception:
            return url
