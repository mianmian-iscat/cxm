#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
原创保护 TTYCBH 千牛标打标脚本模板（安全演练/半自动）

功能：
1. 从文件或环境变量读取 seller_id 列表。
2. 校验 seller_id 格式，过滤纯数字长整型。
3. 生成千牛标管理后台可识别的 TXT 上传模板。
4. 打印后续操作步骤（API/HSF/后台上传），不实际调用生产服务。

安全约束（硬编码）：
- 本脚本仅用于预发/测试环境。
- 禁止将生产卖家 seller_id 写入待打标列表。
- 脚本本身不发起任何网络/HSF/DB 调用；所有执行动作仅做控制台输出。

用法：
  # 默认使用内置白名单
  python3 apply_ttycbh_tag.py

  # 从文件读取 seller_id（每行一个纯数字）
  python3 apply_ttycbh_tag.py --input sellers.txt

  # 从环境变量读取（逗号分隔）
  SELLER_IDS="2213249110271,2219635657158" python3 apply_ttycbh_tag.py

输出：
  - 在 stdout 打印校验后的 seller_id 列表。
  - 在当前目录生成 {timestamp}_ttycbh_sellers.txt（千牛标后台上传模板）。
"""

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# 默认测试白名单，来源：yc-protection-qa-workbench/test-accounts.md
DEFAULT_SELLER_IDS = [2213249110271]

# 千牛标 Code
TAG_CODE = "TTYCBH"

# 业务方待确认：千牛标写入 HSF 服务接口全名（示例，需业务方校准）
# 代码中读标服务注入：com.taobao.multi.client.service.QnResourceTagService
# 写标方法名待确认，可能为 createQnTag / addResourceTag / batchAddResourceTag 等。
PENDING_API_INTERFACE = "com.taobao.multi.client.service.QnResourceTagService:1.0.0"
PENDING_API_METHOD = "待业务方确认（如 createQnTag / addResourceTag / batchAddResourceTag）"


def parse_seller_ids(source: str | None) -> list[int]:
    """从文件路径、环境变量或默认值解析 seller_id 列表。"""
    raw_ids: list[str] = []

    if source:
        path = Path(source)
        if path.is_file():
            raw_ids = path.read_text(encoding="utf-8").splitlines()
        else:
            print(f"[ERROR] 输入文件不存在: {source}", file=sys.stderr)
            sys.exit(1)
    else:
        env_ids = os.environ.get("SELLER_IDS", "")
        if env_ids.strip():
            raw_ids = env_ids.split(",")
        else:
            raw_ids = [str(sid) for sid in DEFAULT_SELLER_IDS]

    cleaned: list[int] = []
    for raw in raw_ids:
        # 去掉空格、制表符、尾部逗号、BOM、注释
        line = raw.strip().replace(",", "").replace("\ufeff", "")
        line = re.sub(r"\s+", "", line)
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        # 拒绝科学计数法/小数
        if not re.fullmatch(r"\d+", line):
            print(f"[WARN] 跳过非法格式 seller_id: {raw!r}", file=sys.stderr)
            continue
        # 拒绝明显过短/过长的 ID
        if len(line) < 10 or len(line) > 16:
            print(f"[WARN] 跳过长度异常 seller_id: {raw!r}", file=sys.stderr)
            continue
        cleaned.append(int(line))

    return cleaned


def validate_no_prod(seller_ids: list[int]) -> list[int]:
    """
    安全校验：仅允许测试/预发 seller_id。
    当前实现依赖硬编码白名单 + 简单启发式规则。
    实际流程中必须人工复核：'这些账号均为 staging 测试账号'。
    """
    allowed = set(DEFAULT_SELLER_IDS)
    safe: list[int] = []
    for sid in seller_ids:
        if sid not in allowed:
            print(
                f"[WARN] seller_id={sid} 不在默认白名单中，"
                "请人工确认其为预发测试账号后再继续。",
                file=sys.stderr,
            )
        else:
            safe.append(sid)
    return safe


def generate_txt_template(seller_ids: list[int]) -> Path:
    """生成千牛标后台上传用的 TXT 文件。"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path(f"{timestamp}_ttycbh_sellers.txt")
    content = "\n".join(str(sid) for sid in seller_ids) + "\n"
    out_path.write_text(content, encoding="utf-8")
    return out_path


def print_api_stub(seller_ids: list[int]) -> None:
    """打印 API/HSF 调用示例（仅演示，不执行）。"""
    print("\n===== API-first 路径（待业务方确认后启用） =====")
    print(f"千牛标 Code: {TAG_CODE}")
    print(f"推断 HSF 接口（需业务方确认）: {PENDING_API_INTERFACE}")
    print(f"推断写标方法（需业务方确认）: {PENDING_API_METHOD}")
    print("示例调用参数（mw CLI 模板）：")
    for sid in seller_ids:
        print(
            f"  mw hsf service invoke \"{PENDING_API_INTERFACE}\" "
            f"--method \"<method>~java.lang.Long;java.lang.String\" "
            f"--args '[{sid}, \"{TAG_CODE}\"]' "
            f"--app taobao-yc-serverless --unit pre"
        )
    print("\n[注意] 以上命令仅为占位模板，方法签名确认前禁止执行。")


def print_manual_steps(seller_ids: list[int], txt_path: Path) -> None:
    """打印半自动后台上传步骤。"""
    print("\n===== Fallback 路径：千牛标管理后台半自动上传 =====")
    print("1. 打开千牛标管理后台：")
    print("   https://qn.alibaba-inc.com/qndev-data-app/management#/")
    print("2. 进入「名单管理」→「名单操作 = 打标」→「上传TXT」")
    print(f"3. 上传生成的文件：{txt_path.absolute()}")
    print("4. 上传格式要求：")
    print("   - 必须为 .txt 纯文本文件")
    print("   - 每行一个纯数字 sellerId，无空格、无逗号、无备注")
    print("   - 文件编码建议 UTF-8")
    print("5. 待打标 seller_id 列表：")
    for sid in seller_ids:
        print(f"   {sid}")
    print("\n6. 打标成功后验证：")
    print("   - 商家重新进入「淘天服饰原创保护」商家端")
    print("   - 不再提示'高原创能力要求'拦截")
    print("   - 页面正常展示专利认证/疑似侵权/4步引导")


def print_next_step(seller_ids: list[int]) -> None:
    """打印打标后的下一步：入驻。"""
    print("\n===== 下一步：触发商家入驻 =====")
    for sid in seller_ids:
        print(
            f"  mw hsf service invoke "
            f"\"com.taobao.industry.yc.serverless.service.hsf.tool.SellerEnterToolService:1.0.0\" "
            f"--method \"enter~java.lang.Long\" "
            f"--args '[{sid}]' "
            f"--app taobao-yc-serverless --unit pre"
        )
    print("\n入驻后请通过 yc-data-factory / 原创保护执行助手继续后续申请流程。")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="原创保护 TTYCBH 千牛标打标模板脚本（仅打印，不执行）"
    )
    parser.add_argument(
        "--input",
        dest="input_file",
        help="seller_id 输入文件路径（每行一个纯数字），默认读取环境变量 SELLER_IDS 或内置白名单",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("原创保护 TTYCBH 千牛标打标 — 安全演练脚本")
    print("=" * 60)

    seller_ids = parse_seller_ids(args.input_file)
    if not seller_ids:
        print("[ERROR] 未解析到任何有效的 seller_id", file=sys.stderr)
        return 1

    safe_ids = validate_no_prod(seller_ids)
    if not safe_ids:
        print(
            "[ERROR] 所有 seller_id 均未通过安全校验，"
            "请确认使用的是预发测试账号。",
            file=sys.stderr,
        )
        return 1

    txt_path = generate_txt_template(safe_ids)

    print_api_stub(safe_ids)
    print_manual_steps(safe_ids, txt_path)
    print_next_step(safe_ids)

    print("\n" + "=" * 60)
    print(f"已生成上传模板：{txt_path.absolute()}")
    print("本脚本未执行任何真实写操作。")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
