"""
visual_regression.py — 视觉回归测试（Visual Regression Testing, VRT）

对标：BrowserStack Percy 2025 (AI Review Agent, false-positive filtering),
     Applitools Eyes (AI visual validation), Testim Visual Validation.

解决的问题：
- 我们虽然有 screenshot 步骤，但没有"像素级 baseline 对比 + 差异报告"
- 主流框架的视觉对比已经进化到"忽略动态区域 + 容差阈值 + 智能标注"

核心能力：
  1. capture_baseline / compare_with_baseline 双向 API
  2. 支持全图对比 + 指定 DOM 元素截图对比
  3. 忽略区域 (ignore regions)：动态内容（头像、广告、时间戳）
  4. 容差阈值：像素差 / 结构相似度 / 颜色漂移
  5. 差异报告：JSON + 可视化标注（差异像素红色高亮）

使用方式：
    from core.visual_regression import VisualRegression

    vrt = VisualRegression(baseline_dir="artifacts/visual-baselines")
    # 首次跑：保存基线
    vrt.save_baseline("home-page", screenshot_bytes)
    # 后续跑：对比 + 报告
    report = vrt.compare("home-page", new_screenshot_bytes,
                         ignore_regions=[{"x":100,"y":50,"w":80,"h":20}],
                         threshold_px=50,
                         threshold_pct=0.01)
    print(report.passed, report.diff_percent, report.diff_image_path)
"""

import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


# ── 默认目录 ──

def _default_baseline_dir() -> str:
    skill_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(skill_root, "artifacts", "visual-baselines")


@dataclass
class IgnoreRegion:
    """忽略区域（像素坐标）"""
    x: int
    y: int
    w: int
    h: int

    def to_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}


@dataclass
class VisualDiffReport:
    """视觉对比报告"""
    baseline_name: str
    passed: bool
    diff_pixel_count: int = 0
    diff_percent: float = 0.0
    baseline_hash: str = ""
    actual_hash: str = ""
    baseline_path: str = ""
    actual_path: str = ""
    diff_image_path: str = ""
    ignored_regions: List[dict] = field(default_factory=list)
    threshold_px: int = 0
    threshold_pct: float = 0.0
    timestamp: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "baseline_name": self.baseline_name,
            "passed": self.passed,
            "diff_pixel_count": self.diff_pixel_count,
            "diff_percent": round(self.diff_percent, 6),
            "baseline_hash": self.baseline_hash,
            "actual_hash": self.actual_hash,
            "baseline_path": self.baseline_path,
            "actual_path": self.actual_path,
            "diff_image_path": self.diff_image_path,
            "ignored_regions": self.ignored_regions,
            "threshold_px": self.threshold_px,
            "threshold_pct": self.threshold_pct,
            "timestamp": self.timestamp,
            "reason": self.reason,
        }


class VisualRegression:
    """
    视觉回归测试引擎。

    依赖 Pillow（仅在需要时才导入，避免强制安装）。

    设计原则：
    - 基线按 <name>.png + <name>.meta.json 双文件存储
    - 对比时若 Pillow 不可用，回退到 hash 对比（粗粒度）
    - 差异图输出 <name>.diff.png，差异像素红色高亮
    """

    def __init__(self, baseline_dir: Optional[str] = None):
        self.baseline_dir = baseline_dir or _default_baseline_dir()
        os.makedirs(self.baseline_dir, exist_ok=True)
        self._pil_available = False
        try:
            from PIL import Image, ImageDraw  # noqa: F401
            self._pil_available = True
        except ImportError:
            print(
                "[vrt] Pillow 未安装，降级到 hash-only 对比（pip install Pillow）",
                file=sys.stderr,
            )

    # ── 路径 ──

    def _baseline_path(self, name: str) -> str:
        return os.path.join(self.baseline_dir, f"{name}.png")

    def _meta_path(self, name: str) -> str:
        return os.path.join(self.baseline_dir, f"{name}.meta.json")

    def _actual_path(self, name: str) -> str:
        return os.path.join(self.baseline_dir, f"{name}.actual.png")

    def _diff_path(self, name: str) -> str:
        return os.path.join(self.baseline_dir, f"{name}.diff.png")

    # ── hash ──

    @staticmethod
    def _hash(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()[:16]

    # ── 基线管理 ──

    def save_baseline(
        self,
        name: str,
        image_bytes: bytes,
        metadata: Optional[dict] = None,
    ) -> VisualDiffReport:
        """保存/更新基线"""
        path = self._baseline_path(name)
        with open(path, "wb") as f:
            f.write(image_bytes)
        meta = {
            "name": name,
            "hash": self._hash(image_bytes),
            "size_bytes": len(image_bytes),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }
        with open(self._meta_path(name), "w") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        return VisualDiffReport(
            baseline_name=name,
            passed=True,
            baseline_hash=meta["hash"],
            actual_hash=meta["hash"],
            baseline_path=path,
            actual_path=path,
            timestamp=meta["created_at"],
            reason="baseline_saved",
        )

    def list_baselines(self) -> List[dict]:
        """列出所有基线"""
        result = []
        for fn in os.listdir(self.baseline_dir):
            if fn.endswith(".meta.json"):
                with open(os.path.join(self.baseline_dir, fn)) as f:
                    try:
                        result.append(json.load(f))
                    except Exception:
                        continue
        return result

    # ── 对比 ──

    def compare(
        self,
        name: str,
        actual_bytes: bytes,
        ignore_regions: Optional[List[dict]] = None,
        threshold_px: int = 50,
        threshold_pct: float = 0.01,
        write_diff_image: bool = True,
    ) -> VisualDiffReport:
        """
        对比 actual vs baseline。

        Args:
            name: 基线名称
            actual_bytes: 新截图字节
            ignore_regions: 忽略区域 [{x, y, w, h}, ...]
            threshold_px: 单像素容差（RGB 欧氏距离 < 该值视为相同）
            threshold_pct: 全图差异占比阈值（0.01 = 1%）
            write_diff_image: 是否生成差异图（<name>.diff.png）

        Returns:
            VisualDiffReport
        """
        baseline_path = self._baseline_path(name)
        if not os.path.exists(baseline_path):
            return VisualDiffReport(
                baseline_name=name,
                passed=False,
                actual_hash=self._hash(actual_bytes),
                timestamp=datetime.now(timezone.utc).isoformat(),
                reason="baseline_missing",
            )

        with open(baseline_path, "rb") as f:
            baseline_bytes = f.read()

        actual_hash = self._hash(actual_bytes)
        baseline_hash = self._hash(baseline_bytes)

        # 快速路径：字节完全相同
        if actual_hash == baseline_hash:
            return VisualDiffReport(
                baseline_name=name,
                passed=True,
                baseline_hash=baseline_hash,
                actual_hash=actual_hash,
                baseline_path=baseline_path,
                timestamp=datetime.now(timezone.utc).isoformat(),
                reason="identical",
            )

        # 保存 actual 用于后续排查
        actual_path = self._actual_path(name)
        try:
            with open(actual_path, "wb") as f:
                f.write(actual_bytes)
        except Exception:
            actual_path = ""

        # 降级：hash-only（无法做像素级对比）
        if not self._pil_available:
            return VisualDiffReport(
                baseline_name=name,
                passed=False,
                baseline_hash=baseline_hash,
                actual_hash=actual_hash,
                baseline_path=baseline_path,
                actual_path=actual_path,
                threshold_px=threshold_px,
                threshold_pct=threshold_pct,
                timestamp=datetime.now(timezone.utc).isoformat(),
                reason="pillow_unavailable_hash_diff_only",
            )

        # Pillow 像素级对比
        from PIL import Image, ImageDraw
        import io

        try:
            base_img = Image.open(io.BytesIO(baseline_bytes)).convert("RGB")
            actual_img = Image.open(io.BytesIO(actual_bytes)).convert("RGB")
        except Exception as e:
            return VisualDiffReport(
                baseline_name=name, passed=False,
                baseline_hash=baseline_hash, actual_hash=actual_hash,
                baseline_path=baseline_path, actual_path=actual_path,
                timestamp=datetime.now(timezone.utc).isoformat(),
                reason=f"image_decode_error: {e}",
            )

        if base_img.size != actual_img.size:
            return VisualDiffReport(
                baseline_name=name, passed=False,
                baseline_hash=baseline_hash, actual_hash=actual_hash,
                baseline_path=baseline_path, actual_path=actual_path,
                timestamp=datetime.now(timezone.utc).isoformat(),
                reason=f"size_mismatch: baseline={base_img.size} actual={actual_img.size}",
            )

        w, h = base_img.size
        total_pixels = w * h
        base_px = base_img.load()
        actual_px = actual_img.load()

        # 构建忽略掩码
        ignore_mask = [[False] * w for _ in range(h)]
        normalized_regions = []
        for r in ignore_regions or []:
            rx = max(0, int(r.get("x", 0)))
            ry = max(0, int(r.get("y", 0)))
            rw = max(0, int(r.get("w", 0)))
            rh = max(0, int(r.get("h", 0)))
            normalized_regions.append({"x": rx, "y": ry, "w": rw, "h": rh})
            for yy in range(ry, min(ry + rh, h)):
                for xx in range(rx, min(rx + rw, w)):
                    ignore_mask[yy][xx] = True

        # 像素级差异扫描
        diff_count = 0
        diff_img = Image.new("RGB", (w, h), (255, 255, 255))
        diff_px = diff_img.load()
        thr2 = threshold_px * threshold_px * 3  # 平方欧氏距离阈值

        for yy in range(h):
            for xx in range(w):
                if ignore_mask[yy][xx]:
                    diff_px[xx, yy] = base_px[xx, yy]
                    continue
                r1, g1, b1 = base_px[xx, yy]
                r2, g2, b2 = actual_px[xx, yy]
                d2 = (r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2
                if d2 > thr2:
                    diff_count += 1
                    diff_px[xx, yy] = (255, 0, 0)  # 差异红色高亮
                else:
                    diff_px[xx, yy] = base_px[xx, yy]

        diff_pct = diff_count / total_pixels if total_pixels else 0.0
        passed = diff_pct <= threshold_pct

        diff_path = ""
        if write_diff_image:
            try:
                draw = ImageDraw.Draw(diff_img)
                for r in normalized_regions:
                    draw.rectangle(
                        [r["x"], r["y"], r["x"] + r["w"], r["y"] + r["h"]],
                        outline=(0, 0, 255), width=2,
                    )
                diff_path = self._diff_path(name)
                diff_img.save(diff_path, "PNG")
            except Exception:
                diff_path = ""

        return VisualDiffReport(
            baseline_name=name,
            passed=passed,
            diff_pixel_count=diff_count,
            diff_percent=diff_pct,
            baseline_hash=baseline_hash,
            actual_hash=actual_hash,
            baseline_path=baseline_path,
            actual_path=actual_path,
            diff_image_path=diff_path,
            ignored_regions=normalized_regions,
            threshold_px=threshold_px,
            threshold_pct=threshold_pct,
            timestamp=datetime.now(timezone.utc).isoformat(),
            reason="pixel_diff" if passed else "pixel_diff_exceeds_threshold",
        )
