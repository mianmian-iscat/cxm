"""
atom_loader.py — 跨业务域公共原子步骤加载器

把 eval/cases/_atoms/<name>.json 解析为可执行步骤，支持：
- 参数默认值填充
- 必填参数校验
- {{var}} 占位符递归替换
- includeAtom 嵌套展开
- manifest 查询

使用方式：
    from core.atom_loader import AtomLoader

    loader = AtomLoader()
    steps = loader.load("page_snapshot", params={"storeAs": "snap1"})
    # -> [{"type": "evaluate", "expression": "...", "storeAs": "snap1"}]

    # 在用例步骤数组里用 includeAtom 引用
    expanded = loader.expand([
        {"type": "includeAtom", "atom": "page_snapshot", "params": {"storeAs": "snap1"}},
        {"type": "screenshot", "label": "after-load"},
    ])

注意：
    本模块不直接执行步骤（那是 StepExecutor 的职责），只负责"展开"。
    StepExecutor 在遇到 includeAtom 步骤时，应调用 loader.expand() 把
    它就地替换为原子内部步骤列表后再执行。
"""

import json
import os
import re
from typing import Any, Dict, List, Optional, Union


# 默认 atoms 目录：{skill_root}/eval/cases/_atoms/
_DEFAULT_ATOMS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "eval", "cases", "_atoms",
)

# 占位符格式 {{varName}}
_VAR_PATTERN = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


class AtomLoader:
    """
    原子步骤模板加载器。

    职责：
    - 从 eval/cases/_atoms/<name>.json 加载模板
    - 按 params + 默认值解析参数
    - 把模板 steps 中的 {{var}} 占位符替换为实际值
    - 递归展开嵌套的 includeAtom

    不负责执行步骤，只返回展开后的 steps 列表。
    """

    def __init__(self, atoms_dir: Optional[str] = None):
        self.atoms_dir = atoms_dir or _DEFAULT_ATOMS_DIR
        self._manifest_cache: Optional[Dict[str, Any]] = None
        self._template_cache: Dict[str, dict] = {}

    # ── manifest ──

    def manifest(self) -> Dict[str, Any]:
        """加载 manifest.json（带缓存）"""
        if self._manifest_cache is not None:
            return self._manifest_cache
        path = os.path.join(self.atoms_dir, "manifest.json")
        if not os.path.exists(path):
            self._manifest_cache = {"version": "0.0.0", "atoms": []}
            return self._manifest_cache
        with open(path, "r", encoding="utf-8") as f:
            self._manifest_cache = json.load(f)
        return self._manifest_cache

    def list_atoms(self) -> List[dict]:
        """返回所有原子摘要（id / description / file / usage_count）"""
        m = self.manifest()
        return [
            {
                "id": a["id"],
                "description": a.get("description", ""),
                "file": a.get("file", f"{a['id']}.json"),
                "usage_count": a.get("usage_count", 0),
            }
            for a in m.get("atoms", [])
        ]

    def get_atom_meta(self, name: str) -> Optional[dict]:
        """按 id 查 manifest 条目"""
        m = self.manifest()
        for a in m.get("atoms", []):
            if a.get("id") == name:
                return a
        return None

    # ── 模板加载 ──

    def _load_template(self, name: str) -> dict:
        """从磁盘加载模板（带缓存），不校验结构"""
        if name in self._template_cache:
            return self._template_cache[name]

        meta = self.get_atom_meta(name)
        if meta:
            filename = meta.get("file", f"{name}.json")
        else:
            filename = f"{name}.json"
        path = os.path.join(self.atoms_dir, filename)

        if not os.path.exists(path):
            raise FileNotFoundError(f"Atom template not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            tpl = json.load(f)

        if "steps" not in tpl or not isinstance(tpl["steps"], list):
            raise ValueError(f"Atom '{name}' missing or invalid 'steps' array")

        self._template_cache[name] = tpl
        return tpl

    # ── 参数解析 ──

    def _resolve_params(self, name: str, tpl: dict, params: Dict[str, Any]) -> Dict[str, str]:
        """
        用 params 覆盖声明的默认值；必填项缺失则抛 ValueError。
        返回 str 化的映射表，便于后续占位符替换。
        """
        declared = tpl.get("params", []) or []
        resolved: Dict[str, str] = {}
        for p in declared:
            pname = p.get("name")
            if not pname:
                continue
            if pname in params:
                resolved[pname] = str(params[pname])
            elif "default" in p:
                resolved[pname] = str(p["default"])
            elif p.get("required"):
                raise ValueError(
                    f"Atom '{name}' 缺少必填参数 '{pname}'，"
                    f"声明的 params: {[d.get('name') for d in declared]}"
                )
        # 允许调用方传额外参数（便于灵活覆盖）
        for k, v in params.items():
            if k not in resolved:
                resolved[k] = str(v)
        return resolved

    # ── 占位符替换 ──

    @staticmethod
    def _substitute(value: Any, params: Dict[str, str]) -> Any:
        """递归替换 dict / list / str 中的 {{var}}"""
        if isinstance(value, str):
            def _repl(m: "re.Match") -> str:
                key = m.group(1)
                return params.get(key, m.group(0))
            return _VAR_PATTERN.sub(_repl, value)
        if isinstance(value, list):
            return [AtomLoader._substitute(item, params) for item in value]
        if isinstance(value, dict):
            return {k: AtomLoader._substitute(v, params) for k, v in value.items()}
        return value

    # ── 对外 API ──

    def load(self, name: str, params: Optional[Dict[str, Any]] = None) -> List[dict]:
        """
        加载原子模板 + 参数替换，返回展开后的 steps 列表。

        Args:
            name: 原子 id（对应 manifest.json 中的 atoms[].id）
            params: 调用方传入的参数（覆盖默认值）

        Returns:
            List[dict]: 展开后的步骤列表

        Raises:
            FileNotFoundError: 模板不存在
            ValueError: 必填参数缺失或结构不合法
        """
        tpl = self._load_template(name)
        resolved = self._resolve_params(name, tpl, params or {})
        steps = tpl.get("steps", [])
        return [self._substitute(step, resolved) for step in steps]

    def expand(self, steps: List[dict], max_depth: int = 8) -> List[dict]:
        """
        把 steps 数组中的 includeAtom 就地展开为内部步骤。

        支持嵌套（原子内部再次 includeAtom），最多 max_depth 层防死循环。

        Args:
            steps: 原始步骤数组（可能包含 includeAtom 类型）
            max_depth: 最大展开深度

        Returns:
            完全展开后的步骤数组
        """
        if max_depth < 0:
            raise RecursionError(f"includeAtom 展开超过最大深度 {max_depth}")

        expanded: List[dict] = []
        for step in steps:
            if not isinstance(step, dict):
                expanded.append(step)
                continue
            if step.get("type") == "includeAtom":
                atom_name = step.get("atom")
                if not atom_name:
                    raise ValueError("includeAtom 步骤缺少 'atom' 字段")
                params = step.get("params") or {}
                inner = self.load(atom_name, params)
                # 递归展开嵌套 includeAtom
                expanded.extend(self.expand(inner, max_depth - 1))
            else:
                expanded.append(step)
        return expanded
