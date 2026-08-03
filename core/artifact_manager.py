"""
artifact_manager.py — 产物管理器

负责：
- 为每次执行创建隔离目录（按业务域 → 场景两级分组）
- 将内存事件流转换为 HAR、JSON、截图等文件
- 维护产物清单（manifest.json）
- 提供产物路径查询接口

产物目录结构（业务域 → 场景两级隔离）：
    artifacts/{domain}/{scene}/{run_id}/
    ├── manifest.json      # 产物清单（类型、路径、大小、时间）
    ├── input.json         # 原始输入（已脱敏）
    ├── output.json        # 执行结果
    ├── capture.json       # 完整抓包数据
    ├── capture.har        # HAR 格式（可导入 Chrome DevTools）
    ├── video.mp4          # 录屏（可选）
    └── screenshots/
        ├── step0-click.jpg
        ├── step2-assert.jpg
        └── error-step3.jpg

业务域划分规则：
    - f88:  F88素材生产平台（审核/策略/模版库/千牛）
    - op:   原创保护平台
    - common: 通用/冒烟测试

场景分组规则：
    - scene 参数从 input_data 的 businessType / knowledgeId / id 前缀推导
    - 未指定 scene 时回退到 artifacts/common/_default/{run_id}/
    - 旧的散落产物保留在 artifacts/_archive/
"""

import json
import os
import time
from datetime import datetime, timezone
from typing import  Optional

# 产物目录：环境变量优先，未设置时默认为 skill 目录下的 artifacts/（相对路径，支持任意机器）
ARTIFACTS_BASE = os.environ.get(
    "WEB_AUTO_ARTIFACTS_DIR",
    os.path.join(os.path.dirname(__file__), "..", "artifacts"),
)

# run_id 命名规范：{scene}-{case-slug}-{YYYYMMDD-HHMMSS}
# 示例： xiaoer-sku-offshelf-20260422-153012
#          tpp-bucket-set-20260422-160000
#          qianniu-collocation-create-20260422-170000
#          aifashion-filter-20260422-202800
#          smoke-xiaoer-search-20260422-080000
RUN_ID_FORMAT = "{scene}-{case}-{ts}"  # ts = YYYYMMDD-HHMMSS

# ── 业务域定义 ──
# 两大核心业务域 + 通用域
BUSINESS_DOMAINS = {
    "f88":    "F88素材生产平台（审核/策略/模版库/千牛）",
    "op":     "原创保护平台",
    "common": "通用/冒烟测试",
}

# 已注册场景 → (业务域, 场景目录名) 映射
# 新增业务场景时在此登记，格式：scene_key: (domain, dir_name)
SCENE_DIRECTORY_MAP = {
    # ── F88 素材生产平台 ──
    "f88-test":               ("f88", "audit"),          # 审核模块
    "f88":                    ("f88", "audit"),
    "f88-audit":              ("f88", "audit"),
    "aifashion":              ("f88", "audit"),
    "f88-strategy":           ("f88", "strategy"),       # 策略平台
    "f88-template":           ("f88", "template"),       # 模版库
    "product-management-test": ("f88", "product-mgmt"),  # 商品管理
    "qianniu-test":           ("f88", "qianniu"),        # 千牛
    "qianniu":                ("f88", "qianniu"),
    # ── 原创保护平台 ──
    "op-test":                ("op", "general"),         # 通用场景
    "original-protection":    ("op", "general"),
    # settlement 细分：计算 / 退款 / 补贴
    "op-settlement":          ("op", "settlement-calc"),       # 结算金额计算（默认）
    "op-settlement-calc":     ("op", "settlement-calc"),       # 结算金额计算
    "op-settlement-refund":   ("op", "settlement-refund"),     # 退款流程
    "op-settlement-subsidy":  ("op", "settlement-subsidy"),    # 补贴触发/首发补贴
    # application 细分：快审 / 状态流转
    "op-application":         ("op", "application-quick-audit"), # 快审（默认）
    "op-quick-audit":         ("op", "application-quick-audit"), # 快审
    "op-application-quick-audit": ("op", "application-quick-audit"),
    "op-state-flow":          ("op", "application-state-flow"),  # 状态机流转
    "op-application-state-flow": ("op", "application-state-flow"),
    # compliance 细分：首发标签 / 到期禁发期
    "op-compliance":          ("op", "compliance-first-publish"), # 首发（默认）
    "op-first-publish":       ("op", "compliance-first-publish"), # 首发标签
    "op-compliance-first-publish": ("op", "compliance-first-publish"),
    "op-expiry":              ("op", "compliance-expiry"),        # 到期/禁发期
    "op-compliance-expiry":   ("op", "compliance-expiry"),
    # 以下保持不变
    "op-enforcement":         ("op", "enforcement"),     # 维权/侵权/下架率
    "op-merchant":            ("op", "merchant"),        # 商家入驻校验
    "op-to-regular":          ("op", "to-regular"),      # 转普通申请
    "op-label":               ("op", "label"),           # 千牛标打标
    # ── 通用 ──
    "smoke":                  ("common", "_smoke"),
}

DEFAULT_DOMAIN = "common"
DEFAULT_SCENE_DIR = "_default"

# 产物文件命命名规范
# 截图： screenshots/{step_index:02d}-{label}.jpg（1458×784 JPEG medium）
# 主要 JSON： input.json / output.json / capture.json
# 清单： manifest.json  ← 必须有
# HAR： capture.har    ← 可选
ARTIFACT_FILES = {
    "input":     "input.json",
    "output":    "output.json",
    "capture":   "capture.json",
    "har":       "capture.har",
    "video":     "video.mp4",
    "manifest":  "manifest.json",
    "knowledge_update": "knowledge_update.json",  # knowledge_updater 的变更摘要
}

def resolve_scene_dir(scene: Optional[str]) -> tuple:
    """将 scene 标识解析为 (domain, scene_dir) 元组。
    未匹配时回退 (common, _default)。"""
    if not scene:
        return DEFAULT_DOMAIN, DEFAULT_SCENE_DIR
    key = scene.lower().strip()
    if key in SCENE_DIRECTORY_MAP:
        return SCENE_DIRECTORY_MAP[key]
    # 未注册场景：尝试从 key 推断业务域
    if key.startswith("f88") or key.startswith("aifashion") or key.startswith("qianniu"):
        return "f88", key
    if key.startswith("op") or key.startswith("original"):
        return "op", key
    return "common", key

class ArtifactManager:
    """
    每次执行实例化一次，管理该次执行的所有产物。
    支持两级分组：artifacts/{domain}/{scene_dir}/{run_id}/
    
    domain: f88 | op | common
    scene_dir: f88-test | product-mgmt | qianniu-test | op-test | _smoke | _default
    """

    def __init__(self, run_id: str, base_dir: str = ARTIFACTS_BASE, scene: Optional[str] = None):
        self.run_id = run_id
        self.scene = scene
        self.domain, self.scene_dir = resolve_scene_dir(scene)
        # 两级目录：artifacts/{domain}/{scene}/{run_id}/
        self.run_dir = os.path.join(base_dir, self.domain, self.scene_dir, run_id)
        self.screenshots_dir = os.path.join(self.run_dir, "screenshots")
        self._manifest = {
            "run_id": run_id,
            "domain": self.domain,
            "scene": self.scene_dir,
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "artifacts": [],
        }
        os.makedirs(self.screenshots_dir, exist_ok=True)

    # ── 路径查询 ──

    def path(self, filename: str) -> str:
        """获取产物路径（run_dir 下的文件）"""
        return os.path.join(self.run_dir, filename)

    def screenshot_path(self, label: str) -> str:
        """获取截图路径"""
        safe_label = label.replace("/", "_").replace(" ", "_")
        return os.path.join(self.screenshots_dir, f"{safe_label}.jpg")

    def video_path(self) -> str:
        return os.path.join(self.run_dir, "video.mp4")

    # ── 写入接口 ──

    def save_input(self, input_data: dict):
        """保存原始输入（已脱敏）"""
        self._write_json("input.json", input_data)

    def save_output(self, output_data: dict):
        """保存执行结果"""
        self._write_json("output.json", output_data)

    def save_screenshot(self, image_bytes: bytes, label: str) -> str:
        """保存 JPEG 截图，返回路径"""
        path = self.screenshot_path(label)
        with open(path, "wb") as f:
            f.write(image_bytes)
        self._register("screenshot", path)
        return path

    def save_capture(self, requests: list) -> str:
        """保存完整抓包 JSON"""
        path = self._write_json("capture.json", requests)
        return path

    def save_har(self, requests: list) -> str:
        """将抓包数据转换为 HAR 格式并保存"""
        entries = []
        for req in requests:
            entry = {
                "startedDateTime": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "time": req.get("duration") or 0,
                "request": {
                    "method": req.get("method", "GET"),
                    "url": req.get("url", ""),
                    "httpVersion": "HTTP/2.0",
                    "headers": [],
                    "queryString": [],
                    "cookies": [],
                    "headersSize": -1,
                    "bodySize": len(json.dumps(req.get("requestBody") or "")) if req.get("requestBody") else 0,
                    "postData": {
                        "mimeType": "application/json",
                        "text": json.dumps(req["requestBody"]) if req.get("requestBody") else "",
                    } if req.get("requestBody") else None,
                },
                "response": {
                    "status": req.get("status") or 0,
                    "statusText": "",
                    "httpVersion": "HTTP/2.0",
                    "headers": [],
                    "cookies": [],
                    "content": {
                        "size": 0,
                        "mimeType": "application/json",
                        "text": json.dumps(req["responseBody"]) if req.get("responseBody") else "",
                    },
                    "redirectURL": "",
                    "headersSize": -1,
                    "bodySize": -1,
                },
                "cache": {},
                "timings": {"send": 0, "wait": req.get("duration") or 0, "receive": 0},
            }
            entries.append(entry)

        har = {
            "log": {
                "version": "1.2",
                "creator": {"name": "web-automation", "version": "2.0.0"},
                "entries": entries,
            }
        }
        path = self.path("capture.har")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(har, f, ensure_ascii=False, indent=2)
        self._register("har", path)
        return path

    # ── 清单 ──

    def save_knowledge_update(self, summary: dict) -> str:
        """保存 knowledge_updater 的变更摘要"""
        path = self._write_json(ARTIFACT_FILES["knowledge_update"], summary)
        return path

    def finalize(self) -> dict:
        """写入产物清单，返回清单内容"""
        self._manifest["finalized_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self._manifest["artifact_count"] = len(self._manifest["artifacts"])

        path = self.path("manifest.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._manifest, f, ensure_ascii=False, indent=2)

        return self._manifest

    def get_manifest(self) -> dict:
        return self._manifest

    # ── 清理 ──

    @staticmethod
    def cleanup_old_runs(base_dir: str = ARTIFACTS_BASE, retention_days: int = 7):
        """清理超过 retention_days 天的产物目录（支持两级目录结构）"""
        if not os.path.exists(base_dir):
            return
        cutoff = time.time() - retention_days * 86400
        import shutil
        # 遍历业务域目录 → 场景目录 → run 目录
        for domain_entry in os.scandir(base_dir):
            if not domain_entry.is_dir() or domain_entry.name.startswith("_"):
                continue  # 跳过 _archive 等特殊目录
            for scene_entry in os.scandir(domain_entry.path):
                if not scene_entry.is_dir():
                    continue
                for run_entry in os.scandir(scene_entry.path):
                    if run_entry.is_dir() and run_entry.stat().st_mtime < cutoff:
                        shutil.rmtree(run_entry.path, ignore_errors=True)

    # ── 内部工具 ──

    def _write_json(self, filename: str, data) -> str:
        path = self.path(filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self._register(filename.split(".")[1], path)
        return path

    def _register(self, artifact_type: str, path: str):
        size = os.path.getsize(path) if os.path.exists(path) else 0
        self._manifest["artifacts"].append({
            "type": artifact_type,
            "path": path,
            "size_bytes": size,
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        })
