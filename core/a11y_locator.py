"""
a11y_locator.py — 可访问性树定位器（Accessibility Tree Locator）

对标：Playwright 2025 的 getByRole / getByLabel / getByPlaceholder / getByText 语义定位,
     arXiv 2603.20358 "A Zero-Cost Self-Healing Approach Using DOM and Accessibility Tree",
     browser-use 的 a11y_tree 压缩。

解决的问题：
- 我们的 clickText / click(selector) 依赖具体文本或 CSS selector
- 主流趋势是用"角色 + 名称"语义定位，UI 重构时更稳定
- a11y tree 还能喂给 LLM 做决策（token 比 HTML 小 10 倍）

核心能力：
  1. getByRole(role, name=None) → CSS selector
  2. getByLabel(label) → CSS selector
  3. getByPlaceholder(placeholder) → CSS selector
  4. getByText(text, exact=False) → CSS selector
  5. snapshot(cdp) → 压缩 a11y tree（给 LLM 用）
  6. suggest_locators(cdp, element_text) → 推荐多个稳定 locator

使用方式：
    from core.a11y_locator import A11yLocator

    a11y = A11yLocator()
    selector = a11y.get_by_role("button", name="提交")
    # -> "button[aria-label='提交'], button:has-text('提交')"

    tree = await a11y.snapshot(cdp, max_depth=5)
    # -> 压缩 JSON，适合 LLM 上下文
"""

import json
import re
import sys
from typing import Any, Dict, List, Optional


# ── 常用 ARIA role → CSS 映射（简化版）──

_ROLE_CSS_MAP = {
    "button": "button, [role='button'], input[type='button'], input[type='submit']",
    "link": "a[href], [role='link']",
    "textbox": "input[type='text'], input[type='email'], input[type='password'], input:not([type]), textarea, [role='textbox']",
    "checkbox": "input[type='checkbox'], [role='checkbox']",
    "radio": "input[type='radio'], [role='radio']",
    "combobox": "select, [role='combobox'], .ant-select",
    "heading": "h1, h2, h3, h4, h5, h6, [role='heading']",
    "dialog": "dialog, [role='dialog'], .ant-modal, .ant-drawer",
    "tab": "[role='tab'], .ant-tabs-tab",
    "tabpanel": "[role='tabpanel'], .ant-tabs-tabpane",
    "list": "ul, ol, [role='list']",
    "listitem": "li, [role='listitem']",
    "menu": "nav, [role='menu']",
    "menuitem": "[role='menuitem']",
    "img": "img, [role='img']",
    "alert": "[role='alert'], .ant-alert",
    "table": "table, [role='table'], .ant-table",
    "row": "tr, [role='row']",
    "cell": "td, th, [role='cell']",
}


class A11yLocator:
    """
    可访问性树定位器。

    两种工作模式：
    - 离线模式（无需 CDP）：根据 role/label/placeholder 生成多候选 CSS selector
    - 在线模式（需要 CDP）：通过 Accessibility.getFullAXTree 拿真实 a11y 树，
      匹配到具体节点后生成唯一可解析的 CSS 路径
    """

    # ── 离线：生成多候选 CSS selector ──

    def get_by_role(self, role: str, name: Optional[str] = None) -> str:
        """按 ARIA role 生成选择器（多候选用逗号分隔）"""
        base = _ROLE_CSS_MAP.get(role, f"[role='{role}']")
        if not name:
            return base
        # 多策略：aria-label / title / 文本内容（用 :has-text 等价表达）
        escaped = self._escape(name)
        candidates = [
            f"{self._first_selector(base)}[aria-label='{escaped}']",
            f"{self._first_selector(base)}[title='{escaped}']",
            f"{self._first_selector(base)}[name='{escaped}']",
            f"{self._first_selector(base)}[data-testid='{escaped}']",
            f"{self._first_selector(base)}[placeholder='{escaped}']",
        ]
        return ", ".join(candidates) + f", {base}"

    def get_by_label(self, label: str) -> str:
        """按关联 label 文本生成选择器"""
        escaped = self._escape(label)
        return (
            f"label:has-text('{escaped}') + * input, "
            f"label:has-text('{escaped}') ~ * input, "
            f"[aria-labelledby]:has(label:has-text('{escaped}')) input, "
            f"input[aria-label='{escaped}']"
        )

    def get_by_placeholder(self, placeholder: str) -> str:
        escaped = self._escape(placeholder)
        return f"input[placeholder='{escaped}'], textarea[placeholder='{escaped}']"

    def get_by_text(self, text: str, exact: bool = False) -> str:
        """按文本内容生成选择器（CSS 无原生 :has-text，用属性 + aria-label 兜底）"""
        escaped = self._escape(text)
        if exact:
            return (
                f"[aria-label='{escaped}'], "
                f"[title='{escaped}'], "
                f"[data-testid='{escaped}']"
            )
        return (
            f"[aria-label*='{escaped}'], "
            f"[title*='{escaped}'], "
            f"[placeholder*='{escaped}']"
        )

    def get_by_test_id(self, test_id: str) -> str:
        escaped = self._escape(test_id)
        return f"[data-testid='{escaped}']"

    # ── 在线：真实 a11y tree ──

    async def snapshot(self, cdp, max_depth: int = 5, max_nodes: int = 500) -> Dict[str, Any]:
        """
        调用 Chrome CDP Accessibility.getFullAXTree 拿真实 a11y 树，
        返回压缩后的 JSON（适合 LLM 上下文）。

        Args:
            cdp: CDPClient 实例
            max_depth: 最大深度
            max_nodes: 最大节点数

        Returns:
            {"nodes": [...], "node_count": N, "truncated": bool}
        """
        try:
            tree = await cdp.send("Accessibility.getFullAXTree", {"depth": max_depth})
        except Exception as e:
            return {"error": str(e), "nodes": [], "node_count": 0}

        nodes_in = tree.get("nodes", [])
        nodes_out = []
        truncated = False
        for i, n in enumerate(nodes_in):
            if i >= max_nodes:
                truncated = True
                break
            role = (n.get("role") or {}).get("value", "")
            name = (n.get("name") or {}).get("value", "")
            desc = (n.get("description") or {}).get("value", "")
            if not role and not name:
                continue
            nodes_out.append({
                "id": n.get("nodeId"),
                "role": role,
                "name": name[:80] if name else "",
                "desc": desc[:80] if desc else "",
            })
        return {
            "nodes": nodes_out,
            "node_count": len(nodes_out),
            "truncated": truncated,
        }

    async def suggest_locators(self, cdp, element_text: str) -> List[dict]:
        """
        基于 a11y tree 给一段文本推荐多个稳定 locator（按置信度排序）。
        """
        snap = await self.snapshot(cdp, max_depth=8, max_nodes=1000)
        if snap.get("error"):
            return []
        candidates = []
        text_lower = element_text.lower().strip()
        for n in snap.get("nodes", []):
            name = n.get("name", "")
            if not name:
                continue
            if text_lower in name.lower():
                role = n.get("role", "")
                # 推荐 1：role + aria-label
                if role:
                    candidates.append({
                        "selector": self.get_by_role(role, name=name),
                        "confidence": 0.9,
                        "source": "a11y_role+name",
                        "role": role, "name": name,
                    })
                # 推荐 2：纯文本
                candidates.append({
                    "selector": self.get_by_text(name, exact=True),
                    "confidence": 0.7,
                    "source": "a11y_text",
                    "role": role, "name": name,
                })
        # 去重 + 排序
        seen = set()
        unique = []
        for c in candidates:
            if c["selector"] in seen:
                continue
            seen.add(c["selector"])
            unique.append(c)
        unique.sort(key=lambda x: -x["confidence"])
        return unique[:5]

    # ── 内部工具 ──

    @staticmethod
    def _escape(s: str) -> str:
        """转义 CSS 选择器字符串中的单引号"""
        return s.replace("'", "\\'")

    @staticmethod
    def _first_selector(combo: str) -> str:
        """从逗号分隔的选择器中取第一个（用于构造复合选择器）"""
        return combo.split(",")[0].strip()
