"""
schema_validator.py — 轻量 JSON Schema 校验器

不引入 jsonschema 第三方依赖，仅做：
1. required 字段存在性检查
2. 字段类型检查（string/integer/number/boolean/array/object）
3. enum 枚举值校验

覆盖 90% 常见格式错误，保持框架零运行时第三方依赖特性。

使用方式：
    from core.schema_validator import validate_knowledge_json, validate_case_json, validate_all

    errors = validate_knowledge_json("knowledge/f88/f88-material-production.json")
    if errors:
        print(f"校验失败: {errors}")
"""

import json
import os
from typing import List, Dict

# ── Schema 路径 ──

_SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "..", "schema")
_KNOWLEDGE_SCHEMA_PATH = os.path.join(_SCHEMA_DIR, "knowledge.schema.json")
_CASE_SCHEMA_PATH = os.path.join(_SCHEMA_DIR, "input.schema.json")


def _load_schema(path: str) -> dict:
    """加载 JSON Schema 文件"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── JSON 类型映射 ──

_JSON_TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _check_type(value, expected_type: str) -> bool:
    """检查值是否符合 JSON Schema 类型"""
    py_type = _JSON_TYPE_MAP.get(expected_type)
    if py_type is None:
        return True  # 未知类型跳过检查
    # integer 在 JSON 中不允许 float（如 1.0 不是 integer）
    if expected_type == "integer" and isinstance(value, float):
        return False
    # boolean 不应匹配 int（JSON true/false 在 Python 中是 bool，但 bool 是 int 子类）
    if expected_type == "number" and isinstance(value, bool):
        return False
    if expected_type == "integer" and isinstance(value, bool):
        return False
    return isinstance(value, py_type)


def _validate_against_schema(data: dict, schema: dict) -> List[str]:
    """根据 Schema 校验 data，返回错误列表（空=通过）"""
    errors = []

    # 1. 顶层类型检查
    if schema.get("type") == "object" and not isinstance(data, dict):
        return [f"期望 object，实际类型: {type(data).__name__}"]

    # 2. required 字段检查
    required_fields = schema.get("required", [])
    for field in required_fields:
        if field not in data:
            errors.append(f"缺少必填字段: '{field}'")

    # 3. properties 类型检查
    properties = schema.get("properties", {})
    for key, prop_schema in properties.items():
        if key not in data:
            continue

        value = data[key]

        # 类型检查
        expected_type = prop_schema.get("type")
        one_of = prop_schema.get("oneOf")

        if expected_type and value is not None:
            if not _check_type(value, expected_type):
                errors.append(
                    f"字段 '{key}' 类型错误: 期望 {expected_type}，"
                    f"实际 {type(value).__name__}"
                )
        elif one_of and value is not None:
            # oneOf: 至少匹配其中一个子 Schema 类型
            matched = any(
                _check_type(value, sub.get("type", ""))
                for sub in one_of if sub.get("type")
            )
            if not matched:
                allowed = [sub.get("type") for sub in one_of if sub.get("type")]
                errors.append(
                    f"字段 '{key}' 类型错误: 期望 {allowed} 之一，"
                    f"实际 {type(value).__name__}"
                )

        # enum 检查
        enum_values = prop_schema.get("enum")
        if enum_values and value is not None and value not in enum_values:
            errors.append(
                f"字段 '{key}' 值 '{value}' 不在枚举范围 {enum_values}"
            )

        # items 类型检查（数组元素）
        if expected_type == "array" and isinstance(value, list):
            items_schema = prop_schema.get("items", {})
            item_type = items_schema.get("type")
            if item_type:
                for i, item in enumerate(value):
                    if item is not None and not _check_type(item, item_type):
                        errors.append(
                            f"字段 '{key}[{i}]' 类型错误: "
                            f"期望 {item_type}，实际 {type(item).__name__}"
                        )
                        if i >= 2:  # 最多报 3 个，避免刷屏
                            remaining = len(value) - 3
                            if remaining > 0:
                                errors.append(
                                    f"字段 '{key}' 还有 {remaining} 个类型错误（省略）"
                                )
                            break

    return errors


# ── 公共接口 ──

def validate_knowledge_json(filepath: str) -> List[str]:
    """校验单个知识库 JSON 文件，返回错误列表（空=通过）

    Args:
        filepath: 知识库 JSON 文件路径

    Returns:
        错误描述列表，空列表表示校验通过
    """
    errors = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return [f"JSON 解析失败: {e}"]
    except FileNotFoundError:
        return [f"文件不存在: {filepath}"]

    schema = _load_schema(_KNOWLEDGE_SCHEMA_PATH)
    errors.extend(_validate_against_schema(data, schema))
    return errors


def validate_case_json(filepath: str) -> List[str]:
    """校验单个用例 JSON 文件，返回错误列表（空=通过）

    Args:
        filepath: 用例 JSON 文件路径

    Returns:
        错误描述列表，空列表表示校验通过
    """
    errors = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return [f"JSON 解析失败: {e}"]
    except FileNotFoundError:
        return [f"文件不存在: {filepath}"]

    schema = _load_schema(_CASE_SCHEMA_PATH)
    errors.extend(_validate_against_schema(data, schema))
    return errors


def validate_all(directory: str, schema_type: str = "knowledge") -> Dict[str, List[str]]:
    """批量校验目录下所有 JSON 文件

    Args:
        directory: 目标目录路径
        schema_type: "knowledge" 或 "case"

    Returns:
        {文件路径: 错误列表} 字典，仅包含有错误的文件
    """
    validator = validate_knowledge_json if schema_type == "knowledge" else validate_case_json
    results = {}

    if not os.path.isdir(directory):
        return {directory: [f"目录不存在: {directory}"]}

    for root, _dirs, files in os.walk(directory):
        for filename in sorted(files):
            if not filename.endswith(".json"):
                continue
            # 知识库目录中的 index.json 有独立 Schema，跳过
            if schema_type == "knowledge" and filename == "index.json":
                continue
            filepath = os.path.join(root, filename)
            errs = validator(filepath)
            if errs:
                results[filepath] = errs

    return results
