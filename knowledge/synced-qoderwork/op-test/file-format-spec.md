<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/yc-protection-qa-workbench/skills/原创保护千牛标打标/references/file-format-spec.md -->
<!-- synced-at: 2026-07-11T03:52:35.000308 -->
<!-- skill: 原创保护千牛标打标 -->

# 千牛标打标 TXT 文件格式规范

参考钉钉文档：https://alidocs.dingtalk.com/i/nodes/XPwkYGxZV347LdvpH6ZEyr1xJAgozOKL?utm_scene=team_space

## 正确格式

```
2213249110271
2219635657158
```

要求：
- 文件后缀 `.txt`
- 编码 UTF-8（无 BOM）
- 每行一个 sellerId
- sellerId 必须是纯数字（10-16 位，淘宝 sellerId 通常 13 位）
- 行尾不能有空格、逗号、分号、句点
- 不能有空行（行间无空白行）
- 不能有注释、备注、表头

## 生成 TXT 的 Python 脚本

```python
import re
from datetime import datetime
from pathlib import Path

def normalize_seller_ids(raw_input: str) -> list[str]:
    """清洗用户输入的 sellerId 列表，返回去重保序的纯数字列表"""
    # 1. 按 \n / , / ; 分割
    parts = re.split(r'[\n,;]+', raw_input)
    seller_ids = []
    seen = set()
    for p in parts:
        p = p.strip().rstrip(',;.')
        if not p:
            continue
        # 2. 校验纯数字
        if not re.fullmatch(r'\d{10,16}', p):
            raise ValueError(f"非法 sellerId: {p!r}（必须是 10-16 位纯数字）")
        # 3. 检查科学计数法（用户从 Excel 复制的常见错误）
        if 'E' in p.upper() or '.' in p:
            raise ValueError(f"检测到科学计数法: {p!r}，请用纯文本格式重新导出")
        if p not in seen:
            seller_ids.append(p)
            seen.add(p)
    return seller_ids

def write_tag_txt(seller_ids: list[str], output_dir: str = "/Users/caoxuemei/.qoderwork/workspace/mqolkxp8boukll2c/outputs") -> str:
    """生成符合千牛标管理后台规范的 TXT 文件"""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = Path(output_dir) / f"打标_{ts}.txt"
    # 使用 \n 换行，UTF-8 无 BOM
    content = "\n".join(seller_ids) + "\n"
    file_path.write_text(content, encoding="utf-8")
    return str(file_path)

# 用例
if __name__ == "__main__":
    raw = "2213249110271, 2219635657158"
    ids = normalize_seller_ids(raw)
    path = write_tag_txt(ids)
    print(f"生成文件: {path}")
    print(f"包含 {len(ids)} 个 sellerId")
```

## 校验生成的文件

```bash
# 检查格式
file 打标.txt                          # 应输出 ASCII text
hexdump -C 打标.txt | head -2         # 检查无 BOM (前3字节不是 ef bb bf)
cat -A 打标.txt                        # 检查行尾无空格、无 \r（Windows 换行）
wc -l 打标.txt                        # 行数 = sellerId 数量
grep -E '[^0-9\n]' 打标.txt && echo "❌ 包含非数字字符" || echo "✓ 全部为数字"
```

## 五种错误场景与防御

| 场景 | 用户输入 | 防御措施 |
|------|---------|---------|
| 1. 文档格式错误 | `.docx` / `.csv` / `.xlsx` | 本 skill 直接产出 `.txt`，不接受其他格式 |
| 2. 科学计数法 | `2.21925E+12` | normalize 时检测 `E` 或 `.` 直接报错 |
| 3. 末尾空格 | `2219635657158 ` | strip 自动处理 |
| 4. 末尾逗号 | `2219635657158,` | rstrip(',;.') 自动处理 |
| 5. 非数字信息 | `2219635657158 // 测试号` | 正则 `^\d{10,16}$` 严格校验，不匹配则拒绝 |
