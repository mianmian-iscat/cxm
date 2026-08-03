<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/yc-protection-qa-workbench/skills/原创保护千牛标打标/references/browser-automation.md -->
<!-- synced-at: 2026-07-11T03:52:35.000441 -->
<!-- skill: 原创保护千牛标打标 -->

# 千牛标管理后台浏览器自动化

## 目标站点

`https://qn.alibaba-inc.com/qndev-data-app/management#/`

## 前置条件

- 浏览器需要已登录阿里 SSO（有效的 buc cookie）
- 需要有「千牛标管理」权限
- 用户当前用 Chrome（`builtin_browser` 工具基于 Chrome Extension V2）

## 5 步自动化脚本

### 步骤 1：导航到管理后台

```
mcp__builtin_browser__navigate(url="https://qn.alibaba-inc.com/qndev-data-app/management#/")
```

等待页面加载，用 `mcp__builtin_browser__read_page` 确认进入了千牛标管理页。

> 如果跳转到 SSO 登录页，引导用户：
> "千牛后台需要 SSO 登录态，请在打开的 tab 中完成登录后告诉我，我继续执行打标流程。"

### 步骤 2：点击「名单管理」

```
mcp__builtin_browser__find(query="名单管理")
mcp__builtin_browser__computer(action="click", element_index=<找到的index>)
```

或用 JS：
```
mcp__builtin_browser__javascript_tool(action="javascript_exec", text="""
const links = [...document.querySelectorAll('a, button, span, div')];
const target = links.find(el => el.textContent.trim() === '名单管理');
if (target) target.click();
""")
```

### 步骤 3：选择「名单操作 = 打标」

```
mcp__builtin_browser__find(query="名单操作")
# 在下拉/单选中选择「打标」（不是「取消打标」）
```

注意区分文案：
- ✓ 「打标」 = 给 sellerId 添加千牛标
- ✗ 「取消打标」 = 移除千牛标（不要选错）
- ✗ 「查询」 = 查名单是否已打标

### 步骤 4：选择「上传方式 = 上传TXT」

```
mcp__builtin_browser__find(query="上传TXT")
mcp__builtin_browser__computer(action="click", element_index=<index>)
```

### 步骤 5：上传 TXT 文件

```
mcp__builtin_browser__file_upload(
    file_path="/Users/caoxuemei/.qoderwork/workspace/mqolkxp8boukll2c/outputs/打标_<时间戳>.txt",
    selector="input[type='file']"
)
```

提交后从 console 或 network 抓取响应，确认是否成功。

## 关键注意事项

### 选择正确的千牛标 Code

千牛标管理后台可能有多个标，必须确认：
- **Code**：`TTYCBH`
- **名称**：原创保护商家准入千牛标 / 淘天原创保护

如果后台需要先选标再操作名单，确保选的是 `TTYCBH`。

### 浏览器扩展卡死防御

参考 MEMORY 中 `builtin_browser V2 扩展` 的踩坑：连续多次 javascript_exec（尤其是含同步 XHR 或大 payload）可能导致扩展卡死。

防御措施：
1. 优先用 `mcp__builtin_browser__find` + `computer click` 而不是 javascript_exec
2. 每次操作后等待 1-2 秒，避免连发
3. 如果扩展卡死，告知用户："浏览器扩展暂时无响应，请手动按 SOP 完成上传，文件已生成在 `<path>`"

### 失败回退

如果任一步自动化失败，立即降级为 SOP 引导：

```
我已生成符合规范的 TXT 文件：<file_path>

浏览器自动化遇到问题，请手动完成以下 5 步：
1. 打开 https://qn.alibaba-inc.com/qndev-data-app/management#/
2. 点击「名单管理」
3. 选择「名单操作 = 打标」
4. 选择「上传方式 = 上传TXT」
5. 上传 <file_path>

完成后告诉我，我帮你验证打标是否生效。
```

## 验证打标生效

打标成功提交后，等 1-2 分钟，然后引导用户：

1. 打开 `https://yuanchuang.aifashion.com/` 或对应商家端入口
2. 切换到目标 sellerId（用 `测试账号管理` skill）
3. 点击「签约」/「我同意并继续」
4. 检查能否进入「淘天服饰原创保护」首页
5. 看到 4 步引导（申请专利→等待专利受理→发布商品→发起维权）即代表打标生效

如果仍报"高原创能力"提示：
- 等 5 分钟（千牛标同步）
- 用 javascript_exec 直接调 `/api/...sellerEnter...` 看具体错误
- 必要时联系开发确认千牛标是否真的写入
