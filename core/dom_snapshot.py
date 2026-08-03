"""
dom_snapshot.py — DOM 快照对比与结构变化检测 (维度2)

在步骤执行前检测页面结构变化，实现"全局感知"而非逐步骤失败：
- DOM 结构摘要采集（tag/class 统计）
- 与历史成功快照对比，计算相似度
- 相似度低于阈值时提前告警

使用方式：
    from core.dom_snapshot import DOMSnapshotGuard
    guard = DOMSnapshotGuard(cdp=cdp)
    snapshot = await guard.capture()
    diff = guard.compare(snapshot, baseline_snapshot)
    if diff.similarity < 0.6:
        # 页面结构大幅变化，可能需要全局选择器刷新
"""

import json
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, List


@dataclass
class DOMSnapshot:
    """DOM 结构摘要"""
    url: str = ""
    title: str = ""
    tag_counts: dict = field(default_factory=dict)        # tag -> count
    class_prefixes: dict = field(default_factory=dict)     # prefix -> count
    key_selectors: dict = field(default_factory=dict)      # selector -> exists(bool)
    interactive_elements: int = 0                          # 可交互元素总数
    captured_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "tag_counts": self.tag_counts,
            "class_prefixes": self.class_prefixes,
            "key_selectors": self.key_selectors,
            "interactive_elements": self.interactive_elements,
            "captured_at": self.captured_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DOMSnapshot":
        return cls(
            url=data.get("url", ""),
            title=data.get("title", ""),
            tag_counts=data.get("tag_counts", {}),
            class_prefixes=data.get("class_prefixes", {}),
            key_selectors=data.get("key_selectors", {}),
            interactive_elements=data.get("interactive_elements", 0),
            captured_at=data.get("captured_at", 0),
        )


@dataclass
class DOMDiff:
    """DOM 快照差异"""
    similarity: float = 1.0         # 0.0~1.0 相似度
    tag_changes: dict = field(default_factory=dict)
    class_changes: dict = field(default_factory=dict)
    missing_selectors: list = field(default_factory=list)
    new_selectors: list = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "similarity": round(self.similarity, 3),
            "tag_changes": self.tag_changes,
            "missing_selectors": self.missing_selectors[:10],
            "new_selectors": self.new_selectors[:10],
            "message": self.message,
        }


class DOMSnapshotGuard:
    """
    DOM 快照对比守卫：检测页面结构变化并提前告警。

    核心能力：
    1. 采集 DOM 结构摘要（轻量，不保存完整 DOM）
    2. 与历史成功快照对比，计算相似度
    3. 相似度低于阈值时建议全局选择器刷新
    """

    # 相似度告警阈值
    SIMILARITY_WARN_THRESHOLD = 0.6
    SIMILARITY_BLOCK_THRESHOLD = 0.3

    def __init__(self, cdp=None):
        self._cdp = cdp
        self._baseline: Optional[DOMSnapshot] = None

    async def capture(self) -> DOMSnapshot:
        """
        采集当前页面的 DOM 结构摘要。
        """
        if not self._cdp:
            return DOMSnapshot()

        try:
            snapshot_js = """(() => {
                const result = {
                    url: window.location.href,
                    title: document.title,
                    tag_counts: {},
                    class_prefixes: {},
                    key_selectors: {},
                    interactive_elements: 0,
                };

                // 1. 标签统计（只统计前 2 级，避免深度遍历）
                const allElements = document.querySelectorAll('*');
                for (const el of allElements) {
                    const tag = el.tagName.toLowerCase();
                    result.tag_counts[tag] = (result.tag_counts[tag] || 0) + 1;

                    // 2. class 前缀统计（取第一个 class 的前缀，如 ant-btn-xxx → ant-btn）
                    if (el.className && typeof el.className === 'string') {
                        const classes = el.className.split(/\\s+/);
                        for (const cls of classes) {
                            // 提取前缀（到第二个 - 之前）
                            const parts = cls.split('-');
                            const prefix = parts.length >= 2 ? parts.slice(0, 2).join('-') : parts[0];
                            if (prefix.length > 2) {
                                result.class_prefixes[prefix] = (result.class_prefixes[prefix] || 0) + 1;
                            }
                        }
                    }
                }

                // 3. 关键选择器存在性检测
                const keySelectors = [
                    '.ant-layout', '.ant-menu', '.ant-table',
                    '.ant-form', '.ant-modal', '.ant-drawer',
                    '.ant-select', '.ant-btn', 'nav', 'header',
                    'main', 'footer', '.ant-tabs',
                ];
                for (const sel of keySelectors) {
                    result.key_selectors[sel] = !!document.querySelector(sel);
                }

                // 4. 可交互元素计数
                result.interactive_elements = document.querySelectorAll(
                    'button, a, input, select, textarea, [role="button"], [onclick]'
                ).length;

                return result;
            })()"""
            data = await self._cdp.evaluate(snapshot_js)
            if data:
                return DOMSnapshot(
                    url=data.get("url", ""),
                    title=data.get("title", ""),
                    tag_counts=data.get("tag_counts", {}),
                    class_prefixes=data.get("class_prefixes", {}),
                    key_selectors=data.get("key_selectors", {}),
                    interactive_elements=data.get("interactive_elements", 0),
                )
        except Exception:
            pass

        return DOMSnapshot()

    def compare(self, current: DOMSnapshot, baseline: Optional[DOMSnapshot] = None) -> DOMDiff:
        """
        对比当前快照与基线快照，返回差异报告。
        """
        baseline = baseline or self._baseline
        if not baseline:
            return DOMDiff(similarity=1.0, message="无基线快照，跳过对比")

        diff = DOMDiff()

        # 1. 标签变化
        all_tags = set(list(current.tag_counts.keys()) + list(baseline.tag_counts.keys()))
        tag_scores = []
        for tag in all_tags:
            curr = current.tag_counts.get(tag, 0)
            base = baseline.tag_counts.get(tag, 0)
            if base > 0:
                ratio = min(curr, base) / max(curr, base)
                tag_scores.append(ratio)
            elif curr > 0:
                tag_scores.append(0.5)  # 新增标签，半相似
        if tag_scores:
            tag_sim = sum(tag_scores) / len(tag_scores)
        else:
            tag_sim = 1.0

        diff.tag_changes = {
            tag: {
                "baseline": baseline.tag_counts.get(tag, 0),
                "current": current.tag_counts.get(tag, 0),
            }
            for tag in all_tags
            if abs(current.tag_counts.get(tag, 0) - baseline.tag_counts.get(tag, 0)) > 2
        }

        # 2. class 前缀变化
        all_prefixes = set(list(current.class_prefixes.keys()) + list(baseline.class_prefixes.keys()))
        class_scores = []
        for prefix in all_prefixes:
            curr = current.class_prefixes.get(prefix, 0)
            base = baseline.class_prefixes.get(prefix, 0)
            if base > 0 and curr > 0:
                class_scores.append(min(curr, base) / max(curr, base))
            elif base > 0 and curr == 0:
                class_scores.append(0.0)
            elif curr > 0 and base == 0:
                class_scores.append(0.5)
        if class_scores:
            class_sim = sum(class_scores) / len(class_scores)
        else:
            class_sim = 1.0

        # 3. 关键选择器变化
        for sel, base_exists in baseline.key_selectors.items():
            curr_exists = current.key_selectors.get(sel, False)
            if base_exists and not curr_exists:
                diff.missing_selectors.append(sel)
            elif not base_exists and curr_exists:
                diff.new_selectors.append(sel)

        selector_sim = 1.0
        total_selectors = len(baseline.key_selectors)
        if total_selectors > 0:
            matching = sum(
                1 for sel, base_exists in baseline.key_selectors.items()
                if current.key_selectors.get(sel, False) == base_exists
            )
            selector_sim = matching / total_selectors

        # 4. 综合相似度（加权平均）
        diff.similarity = (tag_sim * 0.3 + class_sim * 0.4 + selector_sim * 0.3)

        # 5. 生成消息
        if diff.similarity < self.SIMILARITY_BLOCK_THRESHOLD:
            diff.message = (
                f"页面结构严重变化 (相似度 {diff.similarity:.1%})："
                f"缺失选择器 {len(diff.missing_selectors)} 个，"
                f"建议全局选择器刷新或人工检查"
            )
        elif diff.similarity < self.SIMILARITY_WARN_THRESHOLD:
            diff.message = (
                f"页面结构显著变化 (相似度 {diff.similarity:.1%})："
                f"缺失选择器 {len(diff.missing_selectors)} 个"
            )
        else:
            diff.message = f"页面结构稳定 (相似度 {diff.similarity:.1%})"

        return diff

    def set_baseline(self, snapshot: DOMSnapshot):
        """设置基线快照（通常在首次成功执行时调用）"""
        self._baseline = snapshot

    def get_baseline(self) -> Optional[DOMSnapshot]:
        return self._baseline
