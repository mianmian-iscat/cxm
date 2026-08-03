#!/usr/bin/env python3
"""
sync_qoderwork.py — qoderwork ↔ web-automation 双向同步引擎

功能:
  1. 扫描两边用例库 + 知识库，建立清单
  2. 按 sourceIds / 名称匹配，识别新增/删除/冲突
  3. 智能冲突解决：对比代码库、知识库、PRD 引用
  4. 无法自动解决的冲突汇总到报告，等人工确认

用法:
  python scripts/sync_qoderwork.py                    # dry-run 预览
  python scripts/sync_qoderwork.py --apply            # 执行同步
  python scripts/sync_qoderwork.py --apply --bidirectional  # 双向同步
  python scripts/sync_qoderwork.py --conflicts-only   # 只输出冲突报告
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

# ── 路径常量 ──

_WORKSPACE = Path(__file__).resolve().parent.parent
_QODERWORK = Path.home() / ".qoderwork" / "plugins-custom"

_EVAL_CASES_DIR = _WORKSPACE / "eval" / "cases"
_KNOWLEDGE_DIR = _WORKSPACE / "knowledge"
_REFERENCES_DIR = _WORKSPACE / "references"

# qoderwork 插件 → web-automation 场景映射
_PLUGIN_SCENE_MAP = {
    "qa-testing-workbench": "f88-test",
    "yc-protection-qa-workbench": "op-test",
    "产品设计-custom": None,  # 不映射
}


# ── 数据模型 ──

@dataclass
class SyncItem:
    """统一的同步条目，两边都用这个表示。"""
    uid: str                          # 唯一标识（sourceId 或文件名衍生）
    item_type: str                    # "case" | "knowledge"
    side: str                         # "qoderwork" | "web-auto" | "both"
    title: str = ""
    category: str = ""
    priority: str = ""
    content_hash: str = ""            # 内容 hash 用于快速比较
    raw_content: str = ""             # 原始内容
    file_path: str = ""               # 源文件路径
    scene: str = ""                   # f88-test / op-test / ...
    source_ids: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)


@dataclass
class ConflictRecord:
    """冲突记录：两边都有同一条但内容不同。"""
    uid: str
    title: str
    item_type: str
    qw_path: str
    wa_path: str
    qw_hash: str
    wa_hash: str
    auto_resolution: Optional[str]    # "qoderwork" | "web-auto" | None
    reason: str = ""                  # 解决理由 or "需人工确认"
    diff_summary: str = ""


@dataclass
class SyncReport:
    """同步报告。"""
    new_from_qoderwork: list = field(default_factory=list)
    new_from_webauto: list = field(default_factory=list)
    identical: int = 0
    conflicts: list = field(default_factory=list)
    applied_actions: list = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


# ── 扫描器 ──

class QoderworkScanner:
    """扫描 ~/.qoderwork/plugins-custom/ 下的用例和知识。"""

    def scan_all(self) -> list[SyncItem]:
        items = []
        if not _QODERWORK.exists():
            print("[warn] qoderwork 目录不存在", file=sys.stderr)
            return items

        for plugin_dir in _QODERWORK.iterdir():
            if not plugin_dir.is_dir() or plugin_dir.name.startswith("."):
                continue
            scene = _PLUGIN_SCENE_MAP.get(plugin_dir.name)
            if scene is None:
                continue

            skills_dir = plugin_dir / "skills"
            if not skills_dir.exists():
                continue

            for skill_dir in skills_dir.iterdir():
                if not skill_dir.is_dir() or skill_dir.name.startswith("."):
                    continue
                refs_dir = skill_dir / "references"
                if not refs_dir.exists():
                    continue

                # 扫描用例（md 格式）
                tc_dir = refs_dir / "test-cases"
                if tc_dir.exists():
                    for f in tc_dir.glob("*.md"):
                        if f.name == "README.md":
                            continue
                        items.extend(self._parse_tc_md(f, scene))
                    # 扫描 XMind 用例
                    for f in tc_dir.glob("*.xmind"):
                        xmind_items = self._parse_tc_xmind(f, scene)
                        for xi in xmind_items:
                            self._classify_page_and_scope(xi)
                        items.extend(xmind_items)

                # 扫描知识文件
                for f in refs_dir.rglob("*.md"):
                    if "test-cases" in str(f):
                        continue
                    if f.name.startswith("_") or f.name == "README.md":
                        continue
                    items.append(self._parse_knowledge_md(f, scene, skill_dir.name))

        return items

    def _parse_tc_md(self, path: Path, scene: str) -> list[SyncItem]:
        """解析 qoderwork 测试用例 markdown → 多个 SyncItem（每个 ### 一条）。"""
        items = []
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            return items

        # 按 ### 分割用例
        sections = re.split(r"^### ", text, flags=re.MULTILINE)
        header = sections[0] if sections else ""
        file_id = path.stem  # e.g. "07-专利驳回转普通申请"

        for i, sec in enumerate(sections[1:], 1):
            lines = sec.strip().split("\n")
            title_line = lines[0] if lines else f"case-{i}"
            title = title_line.strip()

            # 提取优先级 [P0/P1/P2]
            pm = re.search(r"\[P([012])\]", title)
            priority = f"P{pm.group(1)}" if pm else "P1"

            # 提取状态 PASS/FAIL
            sm = re.search(r"\b(PASS|FAIL|SKIP)\b", title)
            status = sm.group(1) if sm else ""

            # 生成 uid
            slug = re.sub(r"[^\w\u4e00-\u9fff-]", "-", title_line.strip())[:60].strip("-")
            uid = f"qw-{file_id}-M{i}-{slug}"

            # 提取所有字段
            preconditions = ""
            steps_text = ""
            expected = ""
            db_assertion = ""
            api_assertion = ""
            related_prd = ""
            risk_point = ""
            verified = ""
            for line in lines:
                if line.startswith("**前置条件**"):
                    preconditions = line.replace("**前置条件**:", "").replace("**前置条件**：", "").strip()
                elif line.startswith("**步骤**"):
                    steps_text = line.replace("**步骤**:", "").replace("**步骤**：", "").strip()
                elif line.startswith("**预期结果**"):
                    expected = line.replace("**预期结果**:", "").replace("**预期结果**：", "").strip()
                elif line.startswith("**DB断言**"):
                    db_assertion = line.replace("**DB断言**:", "").replace("**DB断言**：", "").strip()
                elif line.startswith("**API断言**"):
                    api_assertion = line.replace("**API断言**:", "").replace("**API断言**：", "").strip()
                elif line.startswith("**关联PRD**"):
                    related_prd = line.replace("**关联PRD**:", "").replace("**关联PRD**：", "").strip()
                elif line.startswith("**关联风险点**"):
                    risk_point = line.replace("**关联风险点**:", "").replace("**关联风险点**：", "").strip()
                elif line.startswith("**实测验证**"):
                    verified = line.replace("**实测验证**:", "").replace("**实测验证**：", "").strip()

            # 计算 hash
            content_hash = hashlib.md5(sec.encode()).hexdigest()[:12]

            extra = {
                "status": status,
                "preconditions": preconditions,
                "steps_text": steps_text,
                "expected": expected,
                "db_assertion": db_assertion,
                "api_assertion": api_assertion,
                "related_prd": related_prd,
                "risk_point": risk_point,
                "verified": verified,
                "file_id": file_id,
                "section_index": i,
            }
            items.append(SyncItem(
                uid=uid,
                item_type="case",
                side="qoderwork",
                title=title,
                category="normal_flow",
                priority=priority,
                content_hash=content_hash,
                raw_content=sec.strip(),
                file_path=str(path),
                scene=scene,
                extra=extra,
            ))

        return items

    # XMind XML 命名空间
    _XM_NS = {'x': 'urn:xmind:xmap:xmlns:content:2.0'}

    def _parse_tc_xmind(self, path: Path, scene: str) -> list[SyncItem]:
        """解析 qoderwork XMind 测试用例 → 多个 SyncItem。"""
        items = []
        try:
            zf = zipfile.ZipFile(str(path))
            xml_data = zf.read('content.xml').decode('utf-8')
        except Exception:
            return items

        try:
            root = ET.fromstring(xml_data)
        except ET.ParseError:
            return items

        ns = self._XM_NS
        file_id = path.stem  # e.g. "01-签约与购买"

        def _get_title(topic):
            t = topic.find('x:title', ns)
            return t.text.strip() if t is not None and t.text else ''

        def _get_children(topic):
            """获取子 topic 列表。"""
            ch = topic.find('x:children', ns)
            if ch is None:
                return []
            result = []
            for topics in ch.findall('x:topics', ns):
                for t in topics.findall('x:topic', ns):
                    result.append(t)
            return result

        def _extract_case_fields(case_topic):
            """从用例节点提取字段。"""
            fields = {}
            for child in _get_children(case_topic):
                key = _get_title(child)
                if key.startswith('优先级'):
                    fields['priority'] = key.split(':')[-1].strip() if ':' in key else key.replace('优先级', '').strip()
                elif key.startswith('前置条件'):
                    fields['preconditions'] = key.split(':', 1)[-1].strip() if ':' in key else ''
                elif key.startswith('测试步骤') or key.startswith('步骤'):
                    fields['steps'] = key.split(':', 1)[-1].strip() if ':' in key else ''
                elif key.startswith('预期结果'):
                    fields['expected'] = key.split(':', 1)[-1].strip() if ':' in key else ''
                elif key.startswith('DB断言'):
                    fields['db_assertion'] = key.split(':', 1)[-1].strip() if ':' in key else ''
                elif key.startswith('API断言'):
                    fields['api_assertion'] = key.split(':', 1)[-1].strip() if ':' in key else ''
                elif key.startswith('关联PRD'):
                    fields['prd_ref'] = key.split(':', 1)[-1].strip() if ':' in key else ''
                elif key.startswith('关联风险点'):
                    fields['risk_points'] = key.split(':', 1)[-1].strip() if ':' in key else ''
            return fields

        def _is_case_topic(topic):
            """判断是否是叶子用例节点（子节点包含"优先级"）。"""
            for child in _get_children(topic):
                title = _get_title(child)
                if '优先级' in title:
                    return True
            return False

        # 遍历 XMind 结构：root → category → [sub-category →] case
        _case_counter = [0]  # mutable counter for closure

        def _walk(topic, depth=0, category=''):
            title = _get_title(topic)
            children = _get_children(topic)

            if _is_case_topic(topic):
                _case_counter[0] += 1
                idx = _case_counter[0]
                fields = _extract_case_fields(topic)
                priority = fields.get('priority', 'P1')
                pm = re.search(r'P([012])', priority)
                priority = f'P{pm.group(1)}' if pm else 'P1'

                slug = re.sub(r'[^\w\u4e00-\u9fff-]', '-', title)[:40].strip('-')
                uid = f'xmind-{file_id}-{idx}-{slug}'

                raw = f"{title}\n{fields.get('preconditions', '')}\n{fields.get('steps', '')}\n{fields.get('expected', '')}"

                items.append(SyncItem(
                    uid=uid,
                    item_type='case',
                    side='qoderwork',
                    title=title,
                    category=category or 'normal_flow',
                    priority=priority,
                    content_hash=hashlib.md5(raw.encode()).hexdigest()[:12],
                    raw_content=raw,
                    file_path=str(path),
                    scene=scene,
                    extra={
                        'file_id': file_id,
                        'section_index': idx,
                        'preconditions': fields.get('preconditions', ''),
                        'steps_text': fields.get('steps', ''),
                        'expected': fields.get('expected', ''),
                        'db_assertion': fields.get('db_assertion', ''),
                        'api_assertion': fields.get('api_assertion', ''),
                        'prd_ref': fields.get('prd_ref', ''),
                        'risk_points': fields.get('risk_points', ''),
                        'source_type': 'xmind',
                    },
                ))
                return

            # 递归子节点
            for child in children:
                child_title = _get_title(child)
                cat = child_title if depth == 1 else category
                _walk(child, depth + 1, cat)

        for sheet in root.findall('x:sheet', ns):
            root_topic = sheet.find('x:topic', ns)
            if root_topic is not None:
                _walk(root_topic)

        return items

    # ── 页面 & 测试范围分类规则 ──
    _PAGE_RULES = [
        # (关键词列表, 页面名称)
        (['小二端', '审核人', '运营后台', '小二', '小二端'], '小二端'),
        (['千牛', 'ttycbh'], '商家端-千牛'),
        (['服务市场', 'fuwu.taobao'], '服务市场'),
        (['签约', '协议', '签约入口', 'sellerSigned'], '商家端-签约'),
        (['商品绑定', '绑定商品', 'bindproduct', '绑定弹窗', '一致性确认', '一致性审核'], '商家端-商品绑定'),
        (['维权', 'tort_record', '侵权线索', '发起维权', '维权中'], '商家端-维权'),
        (['巡检', 'inspection', '自动巡检'], '商家端-巡检'),
        (['申请', '审核', '初审', '预审', '草稿', 'saveOrApply', 'contentCheck',
          '图片上传', '产品类目', '产品名称', '身份证'], '商家端-专利申请'),
        (['首发', '上架', '保护', '存证', 'publishItem', 'firstPublish',
          '打标', 'protect_start'], '商家端-首发保护'),
        (['结算', '退款', '回转', '到期', '补贴', '订购', '开票',
          'yc_right_settle', 'yc_service_trade', '退款金额'], '商家端-结算运营'),
    ]

    def _classify_page_and_scope(self, item: SyncItem):
        """根据用例内容自动推断页面归属和测试范围。"""
        text = ' '.join([
            item.extra.get('preconditions', ''),
            item.extra.get('steps_text', ''),
            item.extra.get('expected', ''),
            item.title,
        ]).lower()
        db = item.extra.get('db_assertion', '')
        api = item.extra.get('api_assertion', '')

        # 页面分类（按优先级顺序匹配）
        page = '商家端-通用'
        for keywords, page_name in self._PAGE_RULES:
            if any(kw.lower() in text for kw in keywords):
                page = page_name
                break

        # 测试范围分类
        if db and api:
            scope = 'mixed'
        elif db:
            scope = 'db'
        elif api:
            scope = 'api'
        else:
            scope = 'ui'

        item.extra['page'] = page
        item.extra['testScope'] = scope

    def _parse_knowledge_md(self, path: Path, scene: str, skill_name: str) -> SyncItem:
        """解析 qoderwork 知识 markdown → SyncItem。"""
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            text = ""

        # 提取 YAML frontmatter
        title = path.stem
        fm_match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
        if fm_match:
            fm = fm_match.group(1)
            tm = re.search(r"^title:\s*(.+)$", fm, re.MULTILINE)
            if tm:
                title = tm.group(1).strip()

        content_hash = hashlib.md5(text.encode()).hexdigest()[:12]

        # 知识文件用路径做 uid
        rel_path = path.relative_to(_QODERWORK)
        uid = f"qw-k-{rel_path}"

        return SyncItem(
            uid=uid,
            item_type="knowledge",
            side="qoderwork",
            title=title,
            content_hash=content_hash,
            raw_content=text,
            file_path=str(path),
            scene=scene,
            extra={"skill": skill_name, "category_path": str(path.parent.name)},
        )


class WebAutoScanner:
    """扫描 web-automation 的 eval/cases/ 和 knowledge/。"""

    def scan_all(self) -> list[SyncItem]:
        items = []

        # 用例
        if _EVAL_CASES_DIR.exists():
            for f in _EVAL_CASES_DIR.rglob("*.json"):
                items.append(self._parse_case_json(f))

        # 知识
        if _KNOWLEDGE_DIR.exists():
            for f in _KNOWLEDGE_DIR.rglob("*.json"):
                if f.name == "index.json":
                    continue
                items.append(self._parse_knowledge_json(f))

        # scenes 下的知识
        for scene_dir in (_WORKSPACE / "scenes").glob("*"):
            k_dir = scene_dir / "knowledge"
            if k_dir.exists():
                for f in k_dir.glob("*.json"):
                    items.append(self._parse_knowledge_json(f, scene_dir.name))

        return items

    def _parse_case_json(self, path: Path) -> SyncItem:
        """解析 web-automation eval case → SyncItem。"""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}

        uid = data.get("id", path.stem)
        source_ids = data.get("sourceIds") or []
        scene = data.get("scene", path.parent.name)

        return SyncItem(
            uid=uid,
            item_type="case",
            side="web-auto",
            title=data.get("name", data.get("description", "")),
            category=data.get("category", ""),
            priority=data.get("priority", ""),
            content_hash=hashlib.md5(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12],
            raw_content=json.dumps(data, ensure_ascii=False),
            file_path=str(path),
            scene=scene,
            source_ids=source_ids,
            extra={"data": data},
        )

    def _parse_knowledge_json(self, path: Path, scene: str = "") -> SyncItem:
        """解析 web-automation knowledge → SyncItem。"""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}

        uid = f"wa-k-{path.relative_to(_WORKSPACE)}"
        title = data.get("description", data.get("platform", path.stem))

        return SyncItem(
            uid=uid,
            item_type="knowledge",
            side="web-auto",
            title=title,
            content_hash=hashlib.md5(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12],
            raw_content=json.dumps(data, ensure_ascii=False),
            file_path=str(path),
            scene=scene or path.parent.name,
            extra={"data": data},
        )


# ── 匹配器 ──

class Matcher:
    """匹配 qoderwork 条目与 web-automation 条目。"""

    def match(self, qw_items: list[SyncItem], wa_items: list[SyncItem]) -> tuple[
        list[tuple[SyncItem, SyncItem]],  # matched pairs
        list[SyncItem],                   # qw-only
        list[SyncItem],                   # wa-only
    ]:
        matched = []
        qw_remaining = list(qw_items)
        wa_remaining = list(wa_items)

        # 第一轮：精确匹配（sourceIds / uid）
        for qi in list(qw_remaining):
            for wi in list(wa_remaining):
                if qi.item_type != wi.item_type:
                    continue
                # case 匹配：module/section_index 同时出现在 source_ids 中
                if qi.item_type == "case" and wi.source_ids:
                    file_id = qi.extra.get("file_id", "")
                    sec_idx = qi.extra.get("section_index", 0)
                    expected_prefix = f"{file_id}/m{sec_idx}"
                    if any(expected_prefix in sid for sid in wi.source_ids):
                        matched.append((qi, wi))
                        qw_remaining.remove(qi)
                        wa_remaining.remove(wi)
                        break

        # 第二轮：名称相似度匹配（知识类）
        # 注意：用例类已经在第一轮通过 file_id+section_index 精确匹配
        for qi in list(qw_remaining):
            best_score = 0
            best_wi = None
            for wi in wa_remaining:
                if qi.item_type != wi.item_type or qi.scene != wi.scene:
                    continue
                score = self._similarity(qi.title, wi.title)
                if score > best_score and score > 0.5:
                    best_score = score
                    best_wi = wi
            if best_wi:
                matched.append((qi, best_wi))
                qw_remaining.remove(qi)
                wa_remaining.remove(best_wi)

        return matched, qw_remaining, wa_remaining

    @staticmethod
    def _similarity(a: str, b: str) -> float:
        """简单 Jaccard 字符相似度。"""
        sa = set(a)
        sb = set(b)
        if not sa or not sb:
            return 0.0
        return len(sa & sb) / len(sa | sb)


# ── 冲突解决器 ──

class ConflictResolver:
    """对冲突条目进行智能裁决。"""

    def resolve(self, qw_item: SyncItem, wa_item: SyncItem) -> ConflictRecord:
        record = ConflictRecord(
            uid=qw_item.uid,
            title=qw_item.title,
            item_type=qw_item.item_type,
            qw_path=qw_item.file_path,
            wa_path=wa_item.file_path,
            qw_hash=qw_item.content_hash,
            wa_hash=wa_item.content_hash,
            auto_resolution=None,
        )

        # 内容相同 → 无冲突
        if qw_item.content_hash == wa_item.content_hash:
            return None

        # 已同步的用例：源与目标属于同一份数据（不同格式），视为相同
        wa_source = wa_item.extra.get("data", {}).get("source") or ""
        if wa_source.startswith("qoderwork/"):
            # web-auto 侧就是从 qoderwork 同步过来的，内容等价
            return None

        # 尝试自动解决
        signals = []

        # 信号 0: 检查是否在废弃目录
        if ".legacy" in qw_item.file_path or "archive" in qw_item.file_path:
            signals.append(("web-auto", "qoderwork 侧位于 .legacy/ 或 archive/ 目录（已废弃）", 5))

        # 信号 1: git 最后修改时间（web-auto 侧）
        wa_mtime = self._git_last_modified(wa_item.file_path)
        qw_mtime = self._file_mtime(qw_item.file_path)

        if wa_mtime and qw_mtime:
            if wa_mtime > qw_mtime:
                signals.append(("web-auto", "web-auto 侧 git 修改更新", 2))
            elif qw_mtime > wa_mtime:
                signals.append(("qoderwork", "qoderwork 侧文件更新", 2))

        # 信号 2: 检查 web-auto 用例是否引用了当前存在的代码模式
        if qw_item.item_type == "case" and wa_item.item_type == "case":
            wa_data = wa_item.extra.get("data", {})
            steps = wa_data.get("steps", [])
            code_refs_found = 0
            for step in steps:
                sel = step.get("selector", "")
                if sel and self._selector_exists_in_knowledge(sel, wa_item.scene):
                    code_refs_found += 1
            if code_refs_found > 0:
                signals.append(("web-auto", f"web-auto 用例中 {code_refs_found} 个 selector 在知识库中有对应", 3))

        # 信号 3: PRD 引用检查
        wa_prd = wa_item.extra.get("data", {}).get("_testDesign", {}).get("prdRef", "")
        qw_prd = re.search(r"PRD[：:]\s*(.+)", qw_item.raw_content)
        if wa_prd and not qw_prd:
            signals.append(("web-auto", "web-auto 有 PRD 引用但 qoderwork 无", 1))

        # 综合评分
        scores = {"qoderwork": 0, "web-auto": 0}
        reasons = []
        for winner, reason, weight in signals:
            scores[winner] += weight
            reasons.append(f"  [{winner}] {reason} (权重{weight})")

        if scores["web-auto"] > scores["qoderwork"] + 2:
            record.auto_resolution = "web-auto"
            record.reason = "web-auto 侧信号更强\n" + "\n".join(reasons)
        elif scores["qoderwork"] > scores["web-auto"] + 2:
            record.auto_resolution = "qoderwork"
            record.reason = "qoderwork 侧信号更强\n" + "\n".join(reasons)
        else:
            record.auto_resolution = None
            record.reason = "信号不足，需人工确认\n" + "\n".join(reasons) if reasons else "无可用信号"

        # diff 摘要
        record.diff_summary = self._make_diff_summary(qw_item, wa_item)

        return record

    def _git_last_modified(self, path: str) -> Optional[datetime]:
        """获取文件最后一次 git 提交时间。"""
        try:
            result = subprocess.run(
                ["git", "log", "-1", "--format=%aI", "--", path],
                capture_output=True, text=True, cwd=str(_WORKSPACE), timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return datetime.fromisoformat(result.stdout.strip())
        except Exception:
            pass
        return None

    def _file_mtime(self, path: str) -> Optional[datetime]:
        """获取文件最后修改时间。"""
        try:
            return datetime.fromtimestamp(os.path.getmtime(path))
        except Exception:
            return None

    def _selector_exists_in_knowledge(self, selector: str, scene: str) -> bool:
        """检查 selector 是否在知识库中有记录。"""
        knowledge_files = list((_KNOWLEDGE_DIR).rglob("*.json"))
        for scene_dir in (_WORKSPACE / "scenes").glob(f"*{scene.split('-')[0]}*"):
            knowledge_files.extend((scene_dir / "knowledge").glob("*.json"))
        for kf in knowledge_files:
            try:
                data = json.loads(kf.read_text(encoding="utf-8"))
                content = json.dumps(data, ensure_ascii=False)
                # 简单检查 selector 的关键部分是否出现在知识库
                key_part = selector.split(">>")[0].strip().split("[")[0]
                if key_part and len(key_part) > 3 and key_part in content:
                    return True
            except Exception:
                continue
        return False

    def _make_diff_summary(self, qw: SyncItem, wa: SyncItem) -> str:
        """生成简要 diff。"""
        lines = []
        if qw.priority != wa.priority:
            lines.append(f"优先级: qw={qw.priority} vs wa={wa.priority}")
        if qw.title != wa.title:
            lines.append(f"标题: qw='{qw.title[:50]}' vs wa='{wa.title[:50]}'")
        lines.append(f"内容 hash: qw={qw.content_hash} vs wa={wa.content_hash}")
        return "\n".join(lines)


# ── 转换器 ──

class QoderworkConverter:
    """将 qoderwork 条目转换为 web-automation 格式。"""

    def case_to_wa_json(self, item: SyncItem) -> dict:
        """qoderwork 用例 md → web-automation eval case JSON。"""
        # 推断 category
        title_lower = item.title.lower()
        if "异常" in item.title or "error" in title_lower:
            category = "error_flow"
        elif "边界" in item.title or "boundary" in title_lower:
            category = "boundary"
        elif "状态" in item.title or "state" in title_lower:
            category = "state_machine"
        elif "接口" in item.title or "API" in item.title:
            category = "api_contract"
        elif "风险" in item.title:
            category = "risk_coverage"
        else:
            category = "normal_flow"

        # 模块分组目录名（如 07-专利驳回转普通申请）
        file_id = item.extra.get("file_id", "unknown")
        sec_idx = item.extra.get("section_index", 0)
        source_type = item.extra.get("source_type", "md")
        module = file_id  # 作为子目录名

        # 生成简洁 id
        clean_title = re.sub(r"\[P\d\]", "", item.title)
        clean_title = re.sub(r"\b(PASS|FAIL|SKIP)\b.*", "", clean_title)
        clean_title = re.sub(r"\s*[—\-–]\s*", "-", clean_title)
        clean_title = clean_title.strip("- ")
        slug = re.sub(r"[^\w\u4e00-\u9fff-]", "-", clean_title)[:40].strip("-")
        if source_type == "xmind":
            case_id = f"xm-{sec_idx}-{slug}" if slug else f"xm-{sec_idx}"
        else:
            case_id = f"m{sec_idx}-{slug}" if slug else f"m{sec_idx}"
        case_id = re.sub(r"-{2,}", "-", case_id).strip("-")

        # 风险点
        risk_points = []
        rp = item.extra.get("risk_points", "") or item.extra.get("risk_point", "")
        if rp:
            risk_points = [rp]

        # 关联文档
        related_docs = []
        prd = item.extra.get("prd_ref", "") or item.extra.get("related_prd", "")
        if prd:
            related_docs = [prd]

        # 页面 & 测试范围
        page = item.extra.get("page", "")
        test_scope = item.extra.get("testScope", "")

        return {
            "id": case_id,
            "name": item.title,
            "description": item.extra.get("preconditions", item.title),
            "businessType": "original_protection" if item.scene == "op-test" else "f88_material",
            "scene": item.scene,
            "module": module,
            "page": page,
            "testScope": test_scope,
            "priority": item.priority,
            "category": category,
            "source": f"qoderwork/{file_id}",
            "sourceIds": [f"{module}/{page}/{case_id}" if page else f"{module}/{case_id}"],
            "context": {"urlPattern": "", "waitAfterLoad": 3000},
            "steps": [],
            "_expected": {"status": "pass"},
            "_testDesign": {
                "preconditions": item.extra.get("preconditions", ""),
                "stepsText": item.extra.get("steps_text", ""),
                "expectedResult": item.extra.get("expected", ""),
                "dbAssertion": item.extra.get("db_assertion", ""),
                "apiAssertion": item.extra.get("api_assertion", ""),
                "riskPoints": risk_points,
                "relatedDocs": related_docs,
                "verified": item.extra.get("verified", ""),
                "sourceType": source_type,
                "syncNote": f"自动同步自 qoderwork {item.file_path}，{datetime.now().isoformat()}",
            },
        }

    def knowledge_to_wa(self, item: SyncItem) -> dict:
        """qoderwork 知识 md → web-automation knowledge JSON（简化版）。"""
        return {
            "_syncSource": item.file_path,
            "_syncTime": datetime.now().isoformat(),
            "title": item.title,
            "scene": item.scene,
            "skill": item.extra.get("skill", ""),
            "content": item.raw_content[:5000],  # 截断过长内容
        }


# ── 主引擎 ──

class SyncEngine:
    """双向同步引擎。"""

    def __init__(self, quiet: bool = False, auto_resolve: bool = False):
        self.quiet = quiet
        self.auto_resolve = auto_resolve
        self.qw_scanner = QoderworkScanner()
        self.wa_scanner = WebAutoScanner()
        self.matcher = Matcher()
        self.resolver = ConflictResolver()
        self.converter = QoderworkConverter()
        self.report = SyncReport()

    def _log(self, msg: str):
        """仅在非 quiet 模式输出。"""
        if not self.quiet:
            print(msg)

    def run(self, apply: bool = False, bidirectional: bool = False, conflicts_only: bool = False):
        # quiet 模式下将所有输出重定向到内存
        import io
        buf = io.StringIO()
        _out = buf if self.quiet else sys.stdout

        def p(msg="", end="\n"):
            _out.write(msg + end)

        p("=" * 60)
        p("  qoderwork ↔ web-automation 双向同步引擎")
        p("=" * 60)
        p()

        # 1. 扫描
        p("[1/5] 扫描 qoderwork ...")
        qw_items = self.qw_scanner.scan_all()
        qw_cases = [i for i in qw_items if i.item_type == "case"]
        qw_knowledge = [i for i in qw_items if i.item_type == "knowledge"]
        p(f"  用例: {len(qw_cases)} 条, 知识: {len(qw_knowledge)} 条")

        p("[2/5] 扫描 web-automation ...")
        wa_items = self.wa_scanner.scan_all()
        wa_cases = [i for i in wa_items if i.item_type == "case"]
        wa_knowledge = [i for i in wa_items if i.item_type == "knowledge"]
        p(f"  用例: {len(wa_cases)} 条, 知识: {len(wa_knowledge)} 条")

        # 2. 匹配
        p("[3/5] 匹配 ...")
        matched, qw_only, wa_only = self.matcher.match(qw_items, wa_items)
        p(f"  匹配: {len(matched)} 对, qoderwork独有: {len(qw_only)}, web-auto独有: {len(wa_only)}")

        # 3. 冲突检测
        p("[4/5] 冲突检测 ...")
        identical = 0
        for qw, wa in matched:
            if qw.content_hash == wa.content_hash:
                identical += 1
            else:
                conflict = self.resolver.resolve(qw, wa)
                if conflict:
                    # auto_resolve 模式：强制自动裁决所有冲突
                    if self.auto_resolve and not conflict.auto_resolution:
                        conflict.auto_resolution = "qoderwork"  # 默认以 qoderwork 为准
                        conflict.reason = "auto-resolve 模式强制裁决"
                    self.report.conflicts.append(conflict)
        self.report.identical = identical
        p(f"  相同: {identical}, 冲突: {len(self.report.conflicts)}")

        # 4. 分类独有项
        qw_only_cases = [i for i in qw_only if i.item_type == "case"]
        qw_only_knowledge = [i for i in qw_only if i.item_type == "knowledge"]
        wa_only_cases = [i for i in wa_only if i.item_type == "case"]
        wa_only_knowledge = [i for i in wa_only if i.item_type == "knowledge"]

        self.report.new_from_qoderwork = qw_only
        self.report.new_from_webauto = wa_only

        # 5. 输出报告
        p("[5/5] 生成报告 ...\n")
        self._print_report(qw_only_cases, qw_only_knowledge, wa_only_cases, wa_only_knowledge, conflicts_only, p=p)

        # 6. 执行同步（如果 --apply）
        if apply:
            p("\n" + "=" * 60)
            p("  执行同步")
            p("=" * 60)
            self._apply_sync(qw_only, wa_only, bidirectional, p=p)
            p(f"\n已执行 {len(self.report.applied_actions)} 项操作")
        else:
            p("\n[预览模式] 使用 --apply 执行同步")

        # 7. 保存报告
        report_path = _WORKSPACE / "artifacts" / "sync-report.json"
        self._save_report(report_path)
        p(f"\n报告已保存: {report_path}")

    def _print_report(self, qw_cases, qw_know, wa_cases, wa_know, conflicts_only, p=print):
        """打印同步报告。"""
        if not conflicts_only:
            if qw_cases:
                p(f"\n📥 qoderwork 新增用例（{len(qw_cases)} 条，可同步到 web-auto）:")
                for item in qw_cases[:20]:
                    p(f"  + [{item.priority}] {item.title[:60]} ({item.scene})")
                if len(qw_cases) > 20:
                    p(f"  ... 还有 {len(qw_cases) - 20} 条")

            if qw_know:
                p(f"\n📥 qoderwork 新增知识（{len(qw_know)} 条，可同步到 web-auto）:")
                for item in qw_know[:10]:
                    p(f"  + {item.title[:60]} ({item.scene})")
                if len(qw_know) > 10:
                    p(f"  ... 还有 {len(qw_know) - 10} 条")

            if wa_cases:
                p(f"\n📤 web-auto 独有用例（{len(wa_cases)} 条）:")
                for item in wa_cases[:10]:
                    p(f"  + [{item.priority}] {item.title[:60]} ({item.scene})")
                if len(wa_cases) > 10:
                    p(f"  ... 还有 {len(wa_cases) - 10} 条")

            if wa_know:
                p(f"\n📤 web-auto 独有知识（{len(wa_know)} 条）:")
                for item in wa_know[:10]:
                    p(f"  + {item.title[:60]} ({item.scene})")

        if self.report.conflicts:
            auto_resolved = [c for c in self.report.conflicts if c.auto_resolution]
            need_review = [c for c in self.report.conflicts if not c.auto_resolution]

            p(f"\n⚡ 冲突项（共 {len(self.report.conflicts)} 条）:")
            p(f"  自动解决: {len(auto_resolved)} 条")
            p(f"  需人工确认: {len(need_review)} 条")

            if auto_resolved:
                p("\n  自动解决的冲突:")
                for c in auto_resolved:
                    winner = "→ web-auto" if c.auto_resolution == "web-auto" else "→ qoderwork"
                    p(f"    {c.title[:50]} [{winner}]")

            if need_review:
                p(f"\n  ⚠️  需人工确认的冲突（{len(need_review)} 条）:")
                for c in need_review:
                    p(f"\n    ┌─ {c.title[:60]}")
                    p(f"    │ qw: {c.qw_path}")
                    p(f"    │ wa: {c.wa_path}")
                    p(f"    │ diff: {c.diff_summary}")
                    p(f"    │ 原因: {c.reason}")
                    p(f"    └─")

    def _apply_sync(self, qw_only, wa_only, bidirectional, p=print):
        """执行同步操作：用例 + 知识一起更新。"""
        converter = QoderworkConverter()

        # ── qoderwork → web-auto ──
        p("\n  📥 qoderwork → web-auto")
        cases_synced = 0
        knowledge_synced = 0

        for item in qw_only:
            if item.item_type == "case":
                wa_data = converter.case_to_wa_json(item)
                module = wa_data.get("module", "")
                page = wa_data.get("page", "")
                # 按模块 + 页面分组到子目录
                if module and page:
                    case_dir = _EVAL_CASES_DIR / item.scene / module / page
                elif module:
                    case_dir = _EVAL_CASES_DIR / item.scene / module
                else:
                    case_dir = _EVAL_CASES_DIR / item.scene
                case_dir.mkdir(parents=True, exist_ok=True)
                out_path = case_dir / f"{wa_data['id']}.json"
                if not out_path.exists():
                    out_path.write_text(json.dumps(wa_data, ensure_ascii=False, indent=2), encoding="utf-8")
                    self.report.applied_actions.append(f"CREATE {out_path.relative_to(_WORKSPACE)}")
                    p(f"    ✅ 用例: {out_path.relative_to(_WORKSPACE)}")
                    cases_synced += 1
                else:
                    p(f"    ⏭  跳过（已存在）: {out_path.relative_to(_WORKSPACE)}")

            elif item.item_type == "knowledge":
                # 知识文件同步：保存为 md 到 knowledge/synced-qoderwork/
                sync_dir = _KNOWLEDGE_DIR / "synced-qoderwork" / item.scene
                sync_dir.mkdir(parents=True, exist_ok=True)
                # 从原始文件名生成目标文件名
                src_name = Path(item.file_path).stem
                # 避免过长文件名
                if len(src_name) > 60:
                    src_name = src_name[:60]
                out_path = sync_dir / f"{src_name}.md"
                if not out_path.exists():
                    # 在头部添加同步元数据
                    header = (
                        f"<!-- synced-from: {item.file_path} -->\n"
                        f"<!-- synced-at: {datetime.now().isoformat()} -->\n"
                        f"<!-- skill: {item.extra.get('skill', '')} -->\n\n"
                    )
                    out_path.write_text(header + item.raw_content, encoding="utf-8")
                    self.report.applied_actions.append(f"CREATE {out_path.relative_to(_WORKSPACE)}")
                    p(f"    ✅ 知识: {out_path.relative_to(_WORKSPACE)}")
                    knowledge_synced += 1
                else:
                    # 文件已存在，比较内容是否更新
                    existing = out_path.read_text(encoding="utf-8")
                    # 跳过同步元数据头比较实际内容
                    existing_body = existing.split("-->\n\n", 1)[-1] if "-->" in existing else existing
                    if existing_body.strip() != item.raw_content.strip():
                        header = (
                            f"<!-- synced-from: {item.file_path} -->\n"
                            f"<!-- synced-at: {datetime.now().isoformat()} -->\n"
                            f"<!-- skill: {item.extra.get('skill', '')} -->\n\n"
                        )
                        out_path.write_text(header + item.raw_content, encoding="utf-8")
                        self.report.applied_actions.append(f"UPDATE {out_path.relative_to(_WORKSPACE)}")
                        p(f"    🔄 更新: {out_path.relative_to(_WORKSPACE)}")
                        knowledge_synced += 1
                    else:
                        pass  # 内容相同，跳过

        # 自动解决的冲突：应用解决方案
        for conflict in self.report.conflicts:
            if conflict.auto_resolution == "qoderwork":
                qw_item = next((i for i in qw_only if i.uid == conflict.uid), None)
                if qw_item and qw_item.item_type == "case":
                    wa_data = converter.case_to_wa_json(qw_item)
                    out_path = Path(conflict.wa_path)
                    out_path.write_text(json.dumps(wa_data, ensure_ascii=False, indent=2), encoding="utf-8")
                    self.report.applied_actions.append(f"UPDATE {out_path.relative_to(_WORKSPACE)} (← qoderwork)")
                    p(f"    ✅ 冲突更新: {out_path.relative_to(_WORKSPACE)} ← qoderwork")

        p(f"  📊 用例 +{cases_synced} 条，知识 +{knowledge_synced} 条")

        if not bidirectional:
            return

        # ── web-auto → qoderwork（双向模式）──
        p("\n  📤 web-auto → qoderwork")
        wa_cases_synced = 0
        wa_knowledge_synced = 0

        for item in wa_only:
            if item.item_type == "case":
                data = item.extra.get("data", {})
                md = self._wa_case_to_md(data)
                target_dir = self._find_qw_tc_dir(item.scene)
                if target_dir:
                    out_path = target_dir / f"{data.get('id', item.uid)}.md"
                    if not out_path.exists():
                        out_path.write_text(md, encoding="utf-8")
                        self.report.applied_actions.append(f"CREATE {out_path}")
                        p(f"    ✅ 用例: {out_path}")
                        wa_cases_synced += 1

            elif item.item_type == "knowledge":
                # web-auto 知识 JSON → qoderwork markdown
                data = item.extra.get("data", {})
                md = self._wa_knowledge_to_md(data, item)
                target_skill = self._find_qw_skill_dir(item.scene)
                if target_skill:
                    refs_dir = target_skill / "references" / "synced-webauto"
                    refs_dir.mkdir(parents=True, exist_ok=True)
                    out_name = re.sub(r"[^\w\u4e00-\u9fff-]", "-", item.title)[:40].strip("-")
                    out_path = refs_dir / f"{out_name}.md"
                    if not out_path.exists():
                        out_path.write_text(md, encoding="utf-8")
                        self.report.applied_actions.append(f"CREATE {out_path}")
                        p(f"    ✅ 知识: {out_path}")
                        wa_knowledge_synced += 1

        p(f"  📊 用例 +{wa_cases_synced} 条，知识 +{wa_knowledge_synced} 条")

    def _wa_case_to_md(self, data: dict) -> str:
        """web-automation case JSON → qoderwork markdown。"""
        lines = [
            f"### {data.get('name', data.get('id', ''))} [{data.get('priority', 'P1')}]",
            "",
            f"**模块**: {data.get('scene', '')}/{data.get('category', '')}",
            "",
        ]
        td = data.get("_testDesign", {})
        if td.get("preconditions"):
            lines.append(f"**前置条件**: {td['preconditions']}")
            lines.append("")
        steps = data.get("steps", [])
        if steps:
            step_texts = [f"{i+1}.{s.get('description', s.get('type', ''))}" for i, s in enumerate(steps)]
            lines.append(f"**步骤**: {' '.join(step_texts)}")
            lines.append("")
        lines.append(f"**预期结果**: {data.get('_expected', {}).get('status', 'pass')}")
        return "\n".join(lines)

    def _find_qw_tc_dir(self, scene: str) -> Optional[Path]:
        """找到 qoderwork 中对应场景的 test-cases 目录。"""
        for plugin_name, mapped_scene in _PLUGIN_SCENE_MAP.items():
            if mapped_scene == scene:
                plugin_dir = _QODERWORK / plugin_name / "skills"
                if plugin_dir.exists():
                    for skill_dir in plugin_dir.iterdir():
                        tc_dir = skill_dir / "references" / "test-cases"
                        if tc_dir.exists():
                            return tc_dir
        return None

    def _find_qw_skill_dir(self, scene: str) -> Optional[Path]:
        """找到 qoderwork 中对应场景的任意 skill 目录（用于知识同步）。"""
        for plugin_name, mapped_scene in _PLUGIN_SCENE_MAP.items():
            if mapped_scene == scene:
                plugin_dir = _QODERWORK / plugin_name / "skills"
                if plugin_dir.exists():
                    # 优先找“测试知识库”或“用例生成”类 skill
                    for skill_dir in plugin_dir.iterdir():
                        if skill_dir.is_dir() and not skill_dir.name.startswith("."):
                            return skill_dir
        return None

    def _wa_knowledge_to_md(self, data: dict, item: SyncItem) -> str:
        """web-auto 知识 JSON → qoderwork markdown。"""
        lines = [
            "---",
            f"id: synced-webauto/{item.uid}",
            f"title: {item.title}",
            f"scene: {item.scene}",
            f"synced_from: web-automation",
            f"synced_at: {datetime.now().isoformat()}",
            "---",
            "",
            f"# {item.title}",
            "",
        ]
        # 添加结构化字段摘要
        if data.get("platform"):
            lines.append(f"**平台**: {data['platform']}")
        if data.get("baseUrl"):
            lines.append(f"**基础URL**: {data['baseUrl']}")
        if data.get("description"):
            lines.append(f"\n{data['description']}")
        if data.get("pages"):
            lines.append("\n## 页面列表")
            for page_key, page_val in data["pages"].items():
                name = page_val.get("name", page_key) if isinstance(page_val, dict) else page_key
                lines.append(f"- {name}")
        if data.get("knownIssues"):
            lines.append("\n## 已知问题")
            for issue in data["knownIssues"]:
                lines.append(f"- {issue}")
        return "\n".join(lines)

    def _save_report(self, path: Path):
        """保存 JSON 报告。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "timestamp": self.report.timestamp,
            "summary": {
                "matched": len(self.report.new_from_qoderwork) + len(self.report.new_from_webauto),
                "identical": self.report.identical,
                "conflicts": len(self.report.conflicts),
                "auto_resolved": sum(1 for c in self.report.conflicts if c.auto_resolution),
                "need_review": sum(1 for c in self.report.conflicts if not c.auto_resolution),
                "applied": len(self.report.applied_actions),
            },
            "conflicts": [
                {
                    "uid": c.uid,
                    "title": c.title,
                    "type": c.item_type,
                    "auto_resolution": c.auto_resolution,
                    "reason": c.reason,
                    "diff": c.diff_summary,
                    "qw_path": c.qw_path,
                    "wa_path": c.wa_path,
                }
                for c in self.report.conflicts
            ],
            "actions": self.report.applied_actions,
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── CLI ──

def main():
    parser = argparse.ArgumentParser(description="qoderwork ↔ web-automation 双向同步")
    parser.add_argument("--apply", action="store_true", help="执行同步（默认 dry-run）")
    parser.add_argument("--bidirectional", action="store_true", help="双向同步（默认 qoderwork→web-auto）")
    parser.add_argument("--conflicts-only", action="store_true", help="只输出冲突报告")
    parser.add_argument("--quiet", "-q", action="store_true", help="静默模式（只输出摘要）")
    parser.add_argument("--auto-resolve", action="store_true", help="自动解决所有冲突（cron 模式）")
    args = parser.parse_args()

    if args.quiet:
        import io, contextlib
        buf = io.StringIO()
        engine = SyncEngine(quiet=True, auto_resolve=args.auto_resolve)
        engine.run(apply=args.apply, bidirectional=args.bidirectional, conflicts_only=args.conflicts_only)
        # 只输出摘要行
        print(f"sync: cases={len(engine.report.applied_actions)}, conflicts_need_review={sum(1 for c in engine.report.conflicts if not c.auto_resolution)}")
    else:
        engine = SyncEngine(auto_resolve=args.auto_resolve)
        engine.run(apply=args.apply, bidirectional=args.bidirectional, conflicts_only=args.conflicts_only)


if __name__ == "__main__":
    main()
