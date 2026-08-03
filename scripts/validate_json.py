"""
validate_json.py — 批量校验知识库和用例 JSON

用法：
    python scripts/validate_json.py --type knowledge --dir knowledge/
    python scripts/validate_json.py --type case --dir eval/cases/f88-test/
    python scripts/validate_json.py --type all          # 全量校验 knowledge/ + eval/cases/

退出码：
    0 = 全部通过
    1 = 存在校验错误
"""

import argparse
import os
import sys

# 确保能导入 core 模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.schema_validator import validate_all


# 默认目录（相对项目根）
_PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
_DEFAULT_KNOWLEDGE_DIR = os.path.join(_PROJECT_ROOT, "knowledge")
_DEFAULT_CASES_DIR = os.path.join(_PROJECT_ROOT, "eval", "cases")


def _run_validation(schema_type: str, directory: str) -> int:
    """执行校验并返回错误数量"""
    results = validate_all(directory, schema_type)

    if not results:
        file_count = sum(
            1 for r, _, files in os.walk(directory)
            for f in files if f.endswith(".json")
        ) if os.path.isdir(directory) else 0
        print(f"✓ [{schema_type}] 全部通过（{file_count} 个文件）")
        return 0

    total_errors = 0
    for filepath, errors in sorted(results.items()):
        rel_path = os.path.relpath(filepath, _PROJECT_ROOT)
        for err in errors:
            print(f"✗ {rel_path}: {err}")
            total_errors += 1

    print(f"\n✗ [{schema_type}] {len(results)} 个文件存在 {total_errors} 个错误")
    return total_errors


def main():
    parser = argparse.ArgumentParser(description="批量校验知识库和用例 JSON")
    parser.add_argument(
        "--type",
        choices=["knowledge", "case", "all"],
        default="all",
        help="校验类型: knowledge / case / all（默认 all）",
    )
    parser.add_argument(
        "--dir",
        default=None,
        help="目标目录（默认按类型自动选择）",
    )
    args = parser.parse_args()

    total = 0

    if args.type in ("knowledge", "all"):
        directory = args.dir if args.dir and args.type != "all" else _DEFAULT_KNOWLEDGE_DIR
        total += _run_validation("knowledge", directory)

    if args.type in ("case", "all"):
        directory = args.dir if args.dir and args.type != "all" else _DEFAULT_CASES_DIR
        total += _run_validation("case", directory)

    if total > 0:
        sys.exit(1)
    else:
        print("\n✓ 全部校验通过")
        sys.exit(0)


if __name__ == "__main__":
    main()
