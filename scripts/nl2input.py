"""
nl2input.py — 自然语言用例 → input JSON 转换器

流程：
  1. 从自然语言中识别目标页面
  2. 查 knowledge/index.json，命中则加载页面知识
  3. 未命中则实时探索页面 DOM，探索后写入 knowledge
  4. 构造 prompt，调用 LLM 生成 input JSON
  5. 用 input.schema.json 校验，输出结果

使用方式（CLI）：
  python scripts/nl2input.py "在品质联盟搜索买手是奕心的商品"
  python scripts/nl2input.py "在品质联盟搜索买手是奕心的商品" --run   # 生成后直接执行
  python scripts/nl2input.py "..." --url "https://xiaoer.alibaba-inc.com/..."  # 显式指定URL
"""

import asyncio
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# ── 路径常量 ──
SKILL_DIR = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = SKILL_DIR / "knowledge"
SCHEMA_PATH = SKILL_DIR / "schema" / "input.schema.json"
PUPPETEER_PATH = os.environ.get("WEB_AUTO_PUPPETEER_PATH", "auto")
CDP_URL = os.environ.get("WEB_AUTO_CDP_URL", "http://127.0.0.1:9222")

# ── LLM 配置（环境变量优先，方便移植到不同环境）──
# 对于阿里内网：WEB_AUTO_LLM_BASE_URL 默认即可用
# 对于外部环境：设置 WEB_AUTO_LLM_BASE_URL + WEB_AUTO_LLM_API_KEY 指向任意 OpenAI 兼容接口
LLM_BASE_URL = os.environ.get("WEB_AUTO_LLM_BASE_URL", "https://idealab.alibaba-inc.com/api/openai/v1")
# ⚠️  外部环境（非阿里内网）必须通过环境变量 WEB_AUTO_LLM_API_KEY 设置自己的 API Key
#     默认值仅供阿里内网使用，对外无效
LLM_API_KEY  = os.environ.get("WEB_AUTO_LLM_API_KEY",  "")
LLM_MODEL    = os.environ.get("WEB_AUTO_LLM_MODEL",    "claude-sonnet-4-6")


# ═══════════════════════════════════════════
# 1. Knowledge 查找
# ═══════════════════════════════════════════

def load_knowledge_index() -> list:
    index_path = KNOWLEDGE_DIR / "index.json"
    if not index_path.exists():
        return []
    return json.loads(index_path.read_text(encoding="utf-8")).get("entries", [])


def match_knowledge(url: str) -> dict | None:
    """根据当前页面 URL 匹配 knowledge entry。"""
    for entry in load_knowledge_index():
        env = entry.get("env", {})
        route = entry.get("route", "")
        for host in [env.get("pre", ""), env.get("prod", "")]:
            if host and host in url and route in url:
                kfile = KNOWLEDGE_DIR / entry["file"]
                if kfile.exists():
                    return json.loads(kfile.read_text(encoding="utf-8"))
    return None


def get_current_page_url() -> str:
    """获取浏览器当前页面 URL（取非空白页的第一个）。"""
    import subprocess
    result = subprocess.run(
        ["node", "-e", f"""
const p = require('{PUPPETEER_PATH}');
(async () => {{
  const b = await p.connect({{ browserURL: '{CDP_URL}', defaultViewport: null }});
  const pages = await b.pages();
  const target = pages.find(pg => pg.url().startsWith('http'));
  console.log(target ? target.url() : '');
  b.disconnect();
}})();
"""],
        capture_output=True, text=True, timeout=10
    )
    return result.stdout.strip()


# ═══════════════════════════════════════════
# 2. 页面 DOM 探索（knowledge 未命中时）
# ═══════════════════════════════════════════

async def explore_page_dom(url_pattern: str) -> dict:
    """实时探索页面结构，返回摘要供 LLM 理解。"""
    import subprocess, json as _json

    script = f"""
const p = require('{PUPPETEER_PATH}');
(async () => {{
  const b = await p.connect({{ browserURL: '{CDP_URL}', defaultViewport: null }});
  const pages = await b.pages();
  const page = pages.find(pg => pg.url().includes('{url_pattern}')) || pages[0];
  await page.evaluate(() => document.querySelectorAll('.wm_div_id').forEach(w => w.remove()));

  const summary = await page.evaluate(() => {{
    // 可见输入框
    const inputs = [...document.querySelectorAll('input, textarea')].filter(el => el.offsetParent).map(el => {{
      const r = el.getBoundingClientRect();
      return {{ tag: 'input', placeholder: el.placeholder, type: el.type, x: r.x, y: r.y }};
    }});

    // 可见按钮
    const buttons = [...document.querySelectorAll('button')].filter(el => el.offsetParent).map(el => {{
      return {{ text: el.innerText.trim(), class: el.className.slice(0, 50) }};
    }}).filter(b => b.text);

    // 下拉选择（ant-select / tbd-select）
    const selects = [...document.querySelectorAll('.tbd-select, .ant-select')].filter(el => el.offsetParent).map(el => {{
      const prefix = el.querySelector('.tbd-select-prefix, .ant-select-prefix');
      const label = (() => {{
        // 找 formily-item-label
        let p = el.parentElement;
        for (let i = 0; i < 6; i++) {{
          const l = p?.querySelector('.tbd-formily-item-label, .ant-form-item-label label');
          if (l) return l.innerText.trim();
          p = p?.parentElement;
        }}
        return prefix?.innerText.trim() || '';
      }})();
      const selected = el.querySelector('.tbd-select-selector, .ant-select-selector')?.innerText.trim();
      return {{ label, selected, class: el.className.slice(0, 40) }};
    }}).filter(s => s.label);

    // Checkbox
    const checkboxes = [...document.querySelectorAll('input[type=checkbox]')].filter(el => el.offsetParent).map(el => {{
      const wrapper = el.closest('label, .tbd-checkbox-wrapper, .ant-checkbox-wrapper') || el.parentElement;
      return {{ text: wrapper?.innerText.trim().slice(0, 30), checked: el.checked }};
    }});

    // 页面标题/面包屑
    const heading = document.querySelector('h1, h2, [class*="title"], [class*="heading"]')?.innerText.trim().slice(0, 50) || '';

    return {{ url: location.href, heading, inputs, buttons, selects, checkboxes }};
  }});

  console.log(JSON.stringify(summary));
  b.disconnect();
}})().catch(e => console.error(e.message));
"""
    proc = await asyncio.create_subprocess_exec(
        "node", "-e", script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
    try:
        return json.loads(stdout.decode().strip())
    except Exception:
        return {"error": stderr.decode().strip(), "raw": stdout.decode().strip()}


def save_new_knowledge(url: str, dom_summary: dict, generated_input: dict):
    """探索完新页面后，将结构写入 knowledge 目录。"""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    host = parsed.netloc
    route = parsed.path

    # 生成 id（简化 host + route）
    kid = re.sub(r"[^a-z0-9]", "-", host.split(".")[0] + route.replace("/", "-")).strip("-")
    kid = re.sub(r"-+", "-", kid)[:40]

    knowledge = {
        "id": kid,
        "description": dom_summary.get("heading", url),
        "uiFramework": "unknown",
        "captureFilter": "",
        "lastUpdated": datetime.now().strftime("%Y-%m-%d"),
        "notes": ["由 nl2input.py 自动探索生成，建议人工补充 apis/knownIssues"],
        "fields": {},
        "actions": {},
        "apis": {},
        "assertHints": {},
        "knownIssues": [],
        "_domSummary": dom_summary,  # 原始探索数据备用
    }

    # 从 dom_summary 初步填充
    for sel in dom_summary.get("selects", []):
        if sel["label"]:
            knowledge["fields"][sel["label"]] = {
                "type": "selectOption",
                "labelClass": "tbd-formily-item-label",
                "note": f"自动探索，selected='{sel['selected']}'"
            }
    for inp in dom_summary.get("inputs", []):
        if inp["placeholder"]:
            knowledge["fields"][inp["placeholder"]] = {
                "type": "fill",
                "selector": f"input[placeholder='{inp['placeholder']}']",
            }
    for btn in dom_summary.get("buttons", []):
        if btn["text"]:
            knowledge["actions"][btn["text"]] = {
                "type": "clickText",
                "text": btn["text"],
            }

    # 写 knowledge 文件
    kfile = KNOWLEDGE_DIR / f"{kid}.json"
    kfile.write_text(json.dumps(knowledge, ensure_ascii=False, indent=2), encoding="utf-8")

    # 更新 index
    index_path = KNOWLEDGE_DIR / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {"entries": []}
    # 去重
    index["entries"] = [e for e in index["entries"] if e["id"] != kid]
    index["entries"].append({
        "id": kid,
        "platform": host.split(".")[0],
        "description": knowledge["description"],
        "env": {"pre": host, "prod": host},
        "route": route,
        "file": f"{kid}.json",
        "_autoGenerated": True,
    })
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    return knowledge


# ═══════════════════════════════════════════
# 3. LLM 调用
# ═══════════════════════════════════════════

SYSTEM_PROMPT = """你是一个 Web 自动化测试用例生成器。
根据用户的自然语言描述和页面知识，生成符合 input schema 的 JSON 测试用例。

## 支持的 step 类型

| type | 必填字段 | 说明 |
|------|---------|------|
| click | text | 按文字点击按钮/链接 |
| clickText | text | 按文字点击任意可见元素（比 click 更灵活） |
| fill | selector, value | 填写输入框（React 表单用 native setter） |
| selectOption | label, option | 下拉选择，label 是字段标签，option 是选项文字 |
| uncheckCheckbox | firstChecked:true 或 labelText | 取消勾选 checkbox |
| wait | ms | 等待毫秒数 |
| assert | target(page/api), contains | 断言页面文字或 API 响应包含某字符串 |
| waitForAPI | urlPattern | 等待特定接口完成 |
| navigate | url | 跳转页面 |
| screenshot | label | 截图（也可在其他 step 加 "screenshot": true） |

## selectOption 的 labelClass
- tbd-formily 页面（如 xiaoer）：`tbd-formily-item-label`（默认）
- tbd-select prefix 型（如选款页）：`tbd-select-prefix`
- ant-design 页面：`ant-form-item-label`

## 输出格式
严格输出合法 JSON，不要有注释、不要有多余文字，只输出 JSON 对象。

结构：
{
  "id": "...",          // 用例ID，英文+数字+连字符
  "name": "...",        // 用例名称（中文可以）
  "context": {
    "urlPattern": "...", // URL 包含的关键词
    "waitAfterLoad": 1500
  },
  "steps": [...],
  "capture": {
    "enabled": true,
    "filter": "...",     // API 路径关键词
    "captureBody": true
  }
}
"""


def call_llm(user_message: str) -> str:
    """调用 LLM，返回生成的 JSON 字符串。"""
    from openai import OpenAI

    client = OpenAI(
        base_url=LLM_BASE_URL,
        api_key=LLM_API_KEY,
    )
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.1,
        max_tokens=4096,
    )
    return response.choices[0].message.content.strip()


def extract_json(text: str) -> dict:
    """从 LLM 输出中提取 JSON（兼容 markdown 代码块和多余文字）。"""
    # 优先匹配 ```json ... ``` 代码块
    block = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if block:
        return json.loads(block.group(1).strip())
    # 找第一个 { 到最后一个 } 之间的内容
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        return json.loads(text[start:end+1])
    raise ValueError(f"LLM 输出中未找到 JSON:\n{text[:200]}")


# ═══════════════════════════════════════════
# 4. 主转换函数
# ═══════════════════════════════════════════

async def nl_to_input(
    natural_language: str,
    explicit_url: str = None,
    run_id_suffix: str = None,
) -> dict:
    """
    将自然语言用例转换为 input JSON。

    Args:
        natural_language: 用户的自然语言描述
        explicit_url: 显式指定页面 URL（可选，默认取浏览器当前页）
        run_id_suffix: 用例 ID 后缀（可选）

    Returns:
        符合 input.schema.json 的 dict
    """
    # 1. 获取当前页面 URL
    current_url = explicit_url or get_current_page_url()
    print(f"[nl2input] 当前页面: {current_url}", file=sys.stderr)

    # 2. 查 knowledge
    knowledge = match_knowledge(current_url)
    dom_summary = None

    if knowledge:
        print(f"[nl2input] 命中 knowledge: {knowledge['id']}", file=sys.stderr)
        knowledge_text = json.dumps(knowledge, ensure_ascii=False, indent=2)
    else:
        print(f"[nl2input] 未命中 knowledge，开始探索页面...", file=sys.stderr)
        dom_summary = await explore_page_dom(current_url)
        print(f"[nl2input] 探索完成，字段数: {len(dom_summary.get('selects', []))+len(dom_summary.get('inputs', []))}", file=sys.stderr)
        knowledge_text = f"（新页面，以下是实时探索的 DOM 摘要）\n{json.dumps(dom_summary, ensure_ascii=False, indent=2)}"

    # 3. 构造 prompt
    user_prompt = f"""## 当前页面
URL: {current_url}

## 页面知识
{knowledge_text}

## 用户测试意图
{natural_language}

请根据以上信息生成 input JSON 测试用例。
- id 使用英文，描述本次操作
- 如有「重置」操作习惯，在搜索类用例开头加上重置步骤
- 如果页面知识中有 knownIssues，注意规避
- capture.filter 使用页面知识中的 captureFilter 字段值
"""

    # 4. 调用 LLM
    print(f"[nl2input] 调用 LLM ({LLM_MODEL})...", file=sys.stderr)
    raw_output = call_llm(user_prompt)

    # 5. 提取 JSON
    result = extract_json(raw_output)

    # 6. 补全缺失字段
    if "id" not in result:
        result["id"] = f"nl-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    if "name" not in result:
        result["name"] = natural_language[:50]

    # 7. 若是新页面，写入 knowledge
    if dom_summary and not knowledge:
        print(f"[nl2input] 写入新 knowledge...", file=sys.stderr)
        save_new_knowledge(current_url, dom_summary, result)
        print(f"[nl2input] knowledge 已保存", file=sys.stderr)

    return result


# ═══════════════════════════════════════════
# 5. CLI 入口
# ═══════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(description="自然语言用例 → input JSON")
    parser.add_argument("text", help="自然语言测试用例描述")
    parser.add_argument("--url", help="显式指定目标页面 URL（默认取浏览器当前页）")
    parser.add_argument("--run", action="store_true", help="生成后直接调用 impl.py 执行")
    parser.add_argument("--out", help="输出到文件（默认打印到 stdout）")
    args = parser.parse_args()

    result = asyncio.run(nl_to_input(args.text, explicit_url=args.url))

    out_json = json.dumps(result, ensure_ascii=False, indent=2)

    if args.out:
        Path(args.out).write_text(out_json, encoding="utf-8")
        print(f"[nl2input] 已写入: {args.out}", file=sys.stderr)
    else:
        print(out_json)

    if args.run:
        import subprocess
        impl_path = SKILL_DIR / "impl.py"
        print(f"\n[nl2input] 开始执行...", file=sys.stderr)
        proc = subprocess.run(
            ["python3", str(impl_path), out_json],
            capture_output=False,
        )
        sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
