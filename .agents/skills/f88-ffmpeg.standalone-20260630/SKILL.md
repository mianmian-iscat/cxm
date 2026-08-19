---
name: f88-ffmpeg
version: 1.5.3
description: F88 素材生产链路视频校验与测试数据构造。当测试用例涉及视频生产(gen_video)、视频审核、视频格式验证、视频参数校验、测试视频文件构造、客户端视频剪辑工具、FFmpeg WASM 引擎加载验证时自动触发。支持 ffprobe 输出物校验（分辨率/编码/码率/帧率/时长对比策略配置）、测试数据批量构造（正常/异常/边界格式）、帧提取截图对比、客户端视频工具 CDN 依赖与降级验证、SharedArrayBuffer/COOP/COEP 跨域隔离环境检查。
description_zh: F88 视频全链路 FFmpeg 工具——从 gen_video 产出校验到测试数据构造到帧提取截图到客户端 WASM 引擎加载验证到 SharedArrayBuffer 跨域隔离检查。
user-invocable: false
---

# F88 视频校验与测试数据构造

> 本 Skill 是 hfz-test-workflow 编排器的视频专项子技能，非用户直接调用。当 hfz-test-workflow 检测到用例涉及 gen_video / 视频审核 / 视频参数校验时自动路由到本 Skill。

## 触发条件

满足以下任一条件即触发：
- 测试用例包含 gen_video / 视频生产 / 视频审核 相关步骤
- 用户要求校验视频参数（分辨率、编码、码率、帧率、时长）
- 用户要求构造测试视频文件（异常格式、边界尺寸、损坏文件）
- 用户要求从视频中提取帧 / 截图
- 用户提到 ffmpeg / ffprobe / 视频转码 / 视频压缩
- 用户提到视频剪辑工具 / Web 视频编辑器 / 客户端视频工具
- 用户提到 FFmpeg WASM / 引擎加载失败 / CDN 资源加载失败 / alicdn

## 前置依赖

### 安装检查

```bash
which ffmpeg && ffmpeg -version | head -1
```

未安装时：

```bash
# macOS（需要 Homebrew）
brew install ffmpeg

# 或从 evermeet.cx 下载 arm64 预编译包（无 brew 时）
# 解压后将 ffmpeg/ffprobe 放入 /usr/local/bin/ 或 ~/bin/
```

## 与 F88 知识库联动

执行校验前，先加载 F88 测试知识库中视频生产相关知识卡：

```bash
# 读取视频生产模块知识卡，获取 GenVideoProcessor 参数规格
cat ~/.qoderwork/plugins-custom/qa-testing-workbench/skills/F88测试知识库/references/features/08-视频生产.md
```

关键信息：
- **GenVideoProcessor**：使用千牛视频 SDK（`QN_VIDEO_SDK`），最多 3 张输入图片，自动上传非 alicdn 图片
- **输出**：`outputVideo`（视频 URL）+ `outputCover`（封面 URL）
- **视频理解模型**：gemini-3-flash-preview / gemini-3.5-flash，后端最多 10 个视频
- **支持格式**：.mp4 / .avi / .mov / .mkv / .webm / .flv / .wmv
- **代码缺陷**（来自 patterns/production-pipeline/video-push-code-defects.md）：
  - `isVideoUrl()` 用 `endsWith(".mp4")` 判断，OSS 签名 URL 带 query 参数时会失败
  - `VideoPushTaskBuilder` 只取 `videoUrls.get(0)`，多视频场景丢失
  - `tryRun()` 抛 `BizException`，无 dry-run 支持

## 能力一：gen_video 输出物校验

### 流程

```
DB 取视频 URL → curl 下载 → ffprobe 提取参数 → 对比策略配置基线 → 输出校验报告
```

### Step 1: 从 DB 获取视频 URL

```sql
-- 查指定批次的 gen_video 成功记录
SELECT
  id,
  JSON_EXTRACT(output_json, '$.outputVideo') AS video_url,
  JSON_EXTRACT(output_json, '$.outputCover') AS cover_url,
  JSON_EXTRACT(extra_info, '$.strategyName') AS strategy_name,
  gmt_create
FROM workflow_record_log
WHERE batch_id = '{batch_id}'
  AND node_type = 'gen_video'
  AND status = 'SUCCESS'
  AND id > 4000000
ORDER BY gmt_create DESC
LIMIT 10;
```

**注意**：
- 视频字段是 `$.outputVideo`（不是 `$.videoUrl`）
- 封面字段是 `$.outputCover`
- 输出 URL 通常是 OSS 签名 URL（带 `?Expires=`），有时效性

### Step 2: 下载视频

```bash
curl -sL "{video_url}" -o /tmp/f88_video_{id}.mp4
```

下载失败（403）时，说明签名 URL 已过期，从 DB 重新查询最新 URL。

### Step 3: ffprobe 提取全量参数

```bash
ffprobe -v quiet -print_format json -show_format -show_streams /tmp/f88_video_{id}.mp4
```

### Step 4: 解析为可读格式

```bash
ffprobe -v quiet -print_format json -show_streams -show_format /tmp/f88_video_{id}.mp4 | \
  python3 -c "
import json, sys
d = json.load(sys.stdin)
vs = [s for s in d['streams'] if s['codec_type']=='video'][0]
fmt = d['format']
print(f\"分辨率: {vs['width']}x{vs['height']}\")
print(f\"编码: {vs['codec_name']}\")
print(f\"帧率: {vs.get('r_frame_rate','N/A')}\")
print(f\"时长: {float(fmt.get('duration',0)):.1f}s\")
print(f\"文件大小: {int(fmt.get('size',0))/1024/1024:.1f}MB\")
print(f\"总码率: {int(fmt.get('bit_rate',0))/1000:.0f}kbps\")
"
```

### Step 5: 对比策略配置基线

从 `g_strategy.workflow_def` 获取 gen_video 节点的预期参数：

```sql
SELECT
  s.name AS strategy_name,
  JSON_EXTRACT(s.workflow_def, '$.innerNodes') AS inner_nodes
FROM g_strategy s
WHERE s.id = {strategy_id};
```

在 `innerNodes` JSON 数组中找到 `type = 'gen_video'` 的节点，读取：
- `imageSize` → 预期分辨率（如 `1280x720`）
- `outputRatio` → 预期宽高比（如 `16:9` → 1.778）
- `modelType` → 使用的 SDK 模型

**校验规则**：

| 参数 | 校验方式 | 容差 |
|------|---------|------|
| 分辨率 | 实际 width/height vs 策略 imageSize | 精确匹配 |
| 宽高比 | width/height vs outputRatio | 误差 ≤ 0.01 |
| 编码 | codec_name | ∈ {h264, hevc, h265} |
| 帧率 | r_frame_rate | 解析分数，∈ {24, 25, 30} |
| 时长 | format.duration | ≤ 60s（默认，策略可覆盖） |
| 文件完整性 | ffprobe -v error | 无错误输出 |
| 封面 | outputCover URL 可访问 | HTTP 200 |

### 校验报告格式

```markdown
## gen_video 输出物校验报告

**批次**: {batch_id} | **策略**: {strategy_name} | **记录ID**: {record_id}

| 参数 | 策略预期 | 实际值 | 结果 |
|------|---------|--------|------|
| 分辨率 | 1280x720 | 1280x720 | PASS |
| 编码 | h264/hevc | h264 | PASS |
| 帧率 | 24-30fps | 30/1 | PASS |
| 时长 | ≤60s | 15.3s | PASS |
| 文件完整性 | 无corrupt | OK | PASS |
| 宽高比 | 16:9 (1.778) | 1.778 | PASS |
| 封面可访问 | HTTP 200 | 200 | PASS |

**结论**: 7/7 PASS，视频输出符合策略配置预期。
```

## 能力二：测试数据批量构造

### 正常格式

```bash
# 标准 MP4 (H.264 + AAC)
ffmpeg -f lavfi -i testsrc=duration=5:size=1280x720:rate=30 \
       -f lavfi -i sine=frequency=440:duration=5 \
       -c:v libx264 -c:a aac -y /tmp/test_normal.mp4

# 多分辨率
for res in 640x360 1280x720 1920x1080; do
  ffmpeg -f lavfi -i testsrc=duration=3:size=${res}:rate=24 \
         -c:v libx264 -y /tmp/test_${res/x/_}.mp4
done

# 多编码
ffmpeg -f lavfi -i testsrc=duration=3:size=720x720:rate=24 -c:v libx265 -y /tmp/test_hevc.mp4
ffmpeg -f lavfi -i testsrc=duration=3:size=720x720:rate=24 -c:v libvpx-vp9 -y /tmp/test_vp9.webm

# 多容器（验证格式兼容性，覆盖 .mp4/.avi/.mov/.mkv/.webm/.flv/.wmv）
for fmt in avi mov mkv webm flv wmv; do
  ffmpeg -f lavfi -i testsrc=duration=3:size=720x720:rate=24 -y /tmp/test_format.${fmt}
done
```

### 异常 / 边界

```bash
# 极小分辨率（1x1）
ffmpeg -f lavfi -i testsrc=duration=2:size=1x1:rate=1 -c:v libx264 -y /tmp/test_tiny.mp4

# 4K 超大
ffmpeg -f lavfi -i testsrc=duration=2:size=3840x2160:rate=15 -c:v libx264 -y /tmp/test_4k.mp4

# 1:1 正方形
ffmpeg -f lavfi -i testsrc=duration=3:size=720x720:rate=24 -c:v libx264 -y /tmp/test_square.mp4

# 极低帧率 / 极高帧率
ffmpeg -f lavfi -i testsrc=duration=5:size=720x720:rate=1 -c:v libx264 -y /tmp/test_1fps.mp4
ffmpeg -f lavfi -i testsrc=duration=3:size=720x720:rate=60 -c:v libx264 -y /tmp/test_60fps.mp4

# 极短视频
ffmpeg -f lavfi -i testsrc=duration=0.5:size=720x720:rate=24 -c:v libx264 -y /tmp/test_short.mp4

# 无音轨
ffmpeg -f lavfi -i testsrc=duration=3:size=720x720:rate=24 -c:v libx264 -an -y /tmp/test_no_audio.mp4

# 损坏文件（截断）
dd if=/tmp/test_normal.mp4 of=/tmp/test_corrupted.mp4 bs=1024 count=10

# 空文件 / 伪装文件
touch /tmp/test_empty.mp4
echo "not a video" > /tmp/test_fake.mp4
```

### 输入图片（gen_video 输入）

```bash
# 多种图片格式（gen_video 最多 3 张输入）
for ext in jpg png bmp tiff webp; do
  ffmpeg -f lavfi -i testsrc=duration=1:size=720x720:rate=1 -frames:v 1 -y /tmp/test_input.${ext}
done

# 超大图片
ffmpeg -f lavfi -i testsrc=duration=1:size=4096x4096:rate=1 -frames:v 1 -q:v 1 -y /tmp/test_huge_input.jpg
```

## 能力三：帧提取与截图对比

### 提取关键帧

```bash
# 首帧
ffmpeg -i /tmp/f88_video_{id}.mp4 -frames:v 1 -y /tmp/frame_first.jpg

# 指定时间点
ffmpeg -ss 00:00:03 -i /tmp/f88_video_{id}.mp4 -frames:v 1 -y /tmp/frame_3s.jpg

# 每隔 N 秒一帧（全视频质量抽检）
ffmpeg -i /tmp/f88_video_{id}.mp4 -vf "fps=1/5" /tmp/frame_%03d.jpg

# 最后一帧
ffmpeg -sseof -0.1 -i /tmp/f88_video_{id}.mp4 -frames:v 1 -y /tmp/frame_last.jpg
```

### 截图对比

```bash
# 并排对比
ffmpeg -i frame_a.jpg -i frame_b.jpg \
       -filter_complex "[0:v][1:v]hstack=inputs=2" \
       -y /tmp/compare_side_by_side.jpg

# 差异图（像素级差异高亮）
ffmpeg -i frame_a.jpg -i frame_b.jpg \
       -filter_complex "[0:v][1:v]blend=all_mode=difference" \
       -y /tmp/compare_diff.jpg
```

## 能力四：视频推送结果验证

视频生成后由 `VideoPushTaskBuilder` 推送到下游（审核/展示）。推送环节有 3 个已知代码缺陷（见 `patterns/production-pipeline/video-push-code-defects.md`），需专项验证。

### 推送完整性校验

```sql
-- 查同一批次中 gen_video 和 video_push 的衔接情况
SELECT
  node_type,
  status,
  COUNT(*) AS cnt,
  JSON_EXTRACT(extra_info, '$.errorMsg') AS error_msg
FROM workflow_record_log
WHERE batch_id = '{batch_id}'
  AND node_type IN ('gen_video', 'video_push')
  AND id > {last_id}
GROUP BY node_type, status, JSON_EXTRACT(extra_info, '$.errorMsg');
```

**校验点**：
- gen_video SUCCESS 数量应等于 video_push 被触发数量
- video_push 不应出现因 URL 格式导致的静默丢弃（`isVideoUrl()` 缺陷）

### 多视频场景验证

`VideoPushTaskBuilder` 只取 `videoUrls.get(0)`，多视频输入时会丢弃后续视频。验证方法：

1. **构造多视频输入**：同一策略节点输入 2-3 个视频 URL
2. **检查推送结果**：video_push 的 `output_json` 中是否只包含第一个视频
3. **预期结果**：当前行为 = 只推送第一个视频（已知缺陷），如业务要求多视频则标记为 BUG

### 视频 URL 格式说明

F88 视频 URL 有两种来源，格式不同：

| 来源 | URL 格式 | 签名 | 时效性 |
|------|---------|------|--------|
| scene-ossgw.taobao.com | `https://scene-ossgw.taobao.com/costume_project/resource/sd/seedance_video_{id}_{ts}.mp4` | 无签名 | 长期有效 |
| OSS 签名 URL | `https://{bucket}.oss-cn-{region}.aliyuncs.com/{path}?Expires={ts}&OSSAccessKeyId={key}&Signature={sig}` | 有签名 | Expires 过期后 403 |

**`isVideoUrl()` 缺陷影响**：
- `endsWith(".mp4")` 对 scene-ossgw URL 正常（以 `.mp4` 结尾）
- 对 OSS 签名 URL 失败（URL 以 `&Signature=xxx` 结尾，不以 `.mp4` 结尾）
- 结果：签名 URL 的视频被误判为非视频，推送时静默丢弃

**下载失败处理**：
- scene-ossgw URL：直接 `curl -sL` 下载
- OSS 签名 URL 返回 403：从 DB 重新查询最新 URL（签名已过期）

## 能力五：多视频测试数据构造

针对 `VideoPushTaskBuilder` 只取 `videoUrls.get(0)` 的缺陷，构造多视频测试数据：

```bash
# 构造 3 个不同内容的视频（用于多视频输入场景）
ffmpeg -f lavfi -i testsrc=duration=3:size=720x720:rate=24 -c:v libx264 -y /tmp/test_multi_v1.mp4
ffmpeg -f lavfi -i color=c=red:duration=3:size=720x720:rate=24 -c:v libx264 -y /tmp/test_multi_v2.mp4
ffmpeg -f lavfi -i color=c=blue:duration=3:size=720x720:rate=24 -c:v libx264 -y /tmp/test_multi_v3.mp4

# 构造不同格式的多视频（验证格式混合场景）
ffmpeg -f lavfi -i testsrc=duration=3:size=720x720:rate=24 -c:v libx264 -y /tmp/test_multi_a.mp4
ffmpeg -f lavfi -i testsrc=duration=3:size=720x720:rate=24 -c:v libvpx-vp9 -y /tmp/test_multi_b.webm
ffmpeg -f lavfi -i testsrc=duration=3:size=720x720:rate=24 -y /tmp/test_multi_c.avi
```

**验证步骤**：
1. 将 3 个视频 URL 作为 `videoUrls` 数组输入
2. 检查 `VideoPushTaskBuilder` 输出是否只包含 `videoUrls[0]`
3. 如只推送第一个 → 确认已知缺陷仍在，记录为 SKIP（已知问题）
4. 如推送了全部 → 缺陷已修复，更新 `patterns/production-pipeline/video-push-code-defects.md`

## 能力六：客户端视频工具依赖加载验证

F88 平台提供浏览器端"视频剪辑"工具（Web Video Editor），其 FFmpeg 引擎以 WASM 形式从自有 CDN 加载（`dev.g.alicdn.com/f-mod/alibaba-puhuiti/0.0.4/`）。当客户端网络异常或 CDN 不可达时，引擎加载失败，视频编辑器功能完全降级。本能力验证该故障链路。

### 故障链路

```
客户端 DNS 解析失败
  → CDN 域名（dev.g.alicdn.com / img.alicdn.com）ERR_NAME_NOT_RESOLVED
    → FFmpeg WASM 二进制 fetch 失败（ffmpeg-core.js / ffmpeg-core.wasm.gz / 814.ffmpeg.js）
      → "FFmpeg 引擎加载失败: TypeError: Failed to fetch"
        → 视频编辑器功能不可用（无法剪辑、转码、预览）
```

### Step 1: CDN 域名可达性检查

在验证前先确认客户端网络环境是否支持 CDN 资源访问：

```bash
# DNS 解析检查（核心 CDN 域名）
for domain in dev.g.alicdn.com img.alicdn.com scene-ossgw.taobao.com; do
  echo "=== $domain ==="
  nslookup "$domain" 2>&1 | head -5
done

# HTTP 可达性检查（HEAD 请求，不下载完整资源）
for url in \
  "https://dev.g.alicdn.com/f-mod/alibaba-puhuiti/0.0.4/ffmpeg-core.js" \
  "https://dev.g.alicdn.com/f-mod/alibaba-puhuiti/0.0.4/ffmpeg-core.wasm.gz" \
  "https://dev.g.alicdn.com/f-mod/alibaba-puhuiti/0.0.4/814.ffmpeg.js"; do
  code=$(curl -sI -o /dev/null -w "%{http_code}" --connect-timeout 5 "$url" 2>/dev/null)
  echo "$url → HTTP $code"
done
```

**判定标准**：

| 结果 | 含义 | 后续动作 |
|------|------|---------|
| DNS 正常 + HTTP 200 | CDN 可达 | 进入 Step 2 验证 WASM 加载 |
| DNS 正常 + HTTP 403/404 | CDN 可达但资源路径变更 | 检查前端代码中 FFmpeg 版本是否已更新 |
| DNS 失败 | 客户端网络问题 | 检查 VPN/代理/DNS 配置 |
| DNS 正常 + HTTP 超时 | 网络策略拦截 | 检查防火墙/安全组规则 |

### Step 2: FFmpeg WASM 引擎加载验证

通过浏览器自动化（alijk-agent-browser）在目标页面验证 FFmpeg 引擎是否成功初始化：

```bash
# 打开视频剪辑页面后，检查 Console 中是否有 FFmpeg 相关错误
# 使用 read_console_messages 获取控制台日志
```

**关键 Console 日志识别**：

| 日志模式 | 含义 | 严重度 |
|---------|------|--------|
| `FFmpeg 引擎加载失败: TypeError: Failed to fetch` | WASM 二进制无法下载 | ERROR — 编辑器完全不可用 |
| `Failed to load resource: net::ERR_NAME_NOT_RESOLVED` + `dev.g.alicdn.com` | FFmpeg WASM CDN 域名 DNS 失败 | ERROR — 根因 |
| `Failed to load resource: net::ERR_NAME_NOT_RESOLVED` + `img.alicdn.com` | 图片 CDN 也失败 | ERROR — 资源加载也受影响 |
| `[APLUS] → APLUS INIT SUCCESS` | 埋点 SDK 正常（对比参考） | INFO — 说明不是所有 CDN 都挂 |
| `false '测试环境review'` | 环境标识 | INFO — 可忽略 |

### Step 3: 降级表现验证

当 FFmpeg 引擎加载失败时，验证前端是否有合理的降级处理：

**检查项**：

| 检查点 | 期望行为 | 当前缺陷 |
|--------|---------|---------|
| 错误提示 | 用户看到明确的错误信息（如"视频工具加载失败，请检查网络"） | 仅在 Console 输出，前端无用户可见提示 |
| 功能禁用 | 视频剪辑按钮置灰或隐藏 | 按钮仍可点击，点击后无响应或白屏 |
| 重试机制 | 提供"重新加载"按钮 | 无重试入口，只能刷新整页 |
| 网络检测 | 先检测网络状态再加载 WASM | 直接 fetch，失败后无友好处理 |
| 超时控制 | fetch 有合理超时时间（如 30s） | 依赖浏览器默认超时，可能长时间挂起 |

### Step 4: 多网络环境验证

不同网络环境下重复 Step 1-3，覆盖典型场景：

| 网络环境 | 预期结果 |
|---------|---------|
| 公司内网（无 VPN） | CDN 可达，FFmpeg 正常加载 |
| 公司内网 + VPN | CDN 可达（VPN 路由不影响） |
| 家庭宽带 | CDN 可达（公网 CDN） |
| 断网 / DNS 异常 | CDN 不可达，应展示降级提示 |

### Step 5: SharedArrayBuffer/COOP/COEP 跨域隔离检查（v1.4 新增）

FFmpeg WASM 依赖 `SharedArrayBuffer`，而浏览器要求页面响应头包含 COOP/COEP 才能启用该特性。预发环境 Nginx 配置可能与生产不一致，导致 FFmpeg WASM 在预发加载失败但生产正常。

```bash
# 检查目标页面的响应头是否包含 COOP/COEP
curl -sI "https://pre-aifashion-xiaoer.alibaba-inc.com/video-editor" | \
  grep -iE "cross-origin-opener-policy|cross-origin-embedder-policy|cross-origin-resource-policy"

# 预期正常输出：
# Cross-Origin-Opener-Policy: same-origin
# Cross-Origin-Embedder-Policy: require-corp
# Cross-Origin-Resource-Policy: cross-origin
```

**判定标准**：

| 响应头 | 期望值 | 缺失后果 |
|--------|--------|---------|
| `Cross-Origin-Opener-Policy` | `same-origin` | SharedArrayBuffer 不可用，ffmpeg-wasm 初始化失败 |
| `Cross-Origin-Embedder-Policy` | `require-corp` 或 `credentialless` | 跨域资源无法加载，WASM 二进制 fetch 失败 |
| `Cross-Origin-Resource-Policy` | `cross-origin` | CDN 资源（alicdn）被浏览器拦截 |

**预发 vs 生产对比**：

```bash
# 对比预发和生产的响应头差异
for env_url in \
  "https://pre-aifashion-xiaoer.alibaba-inc.com/video-editor" \
  "https://aifashion-xiaoer.alibaba-inc.com/video-editor"; do
  echo "=== $env_url ==="
  curl -sI "$env_url" | grep -iE "cross-origin|coop|coep" || echo "(无 COOP/COEP 头)"
done
```

**常见问题**：
- 预发 Nginx 未配置 COOP/COEP → 联系运维添加响应头
- 仅部分路径配置了 → 检查 Nginx location 块是否覆盖视频编辑器路径
- 生产有但预发没有 → 预发 Nginx 配置未同步生产（BT_6149 类问题）

### 验证报告格式

```markdown
## 客户端视频工具依赖加载验证报告

**页面**: {url} | **网络环境**: {内网/VPN/家庭宽带}

| 检查项 | 结果 | 详情 |
|--------|------|------|
| dev.g.alicdn.com DNS | PASS/FAIL | 解析到 x.x.x.x / NXDOMAIN |
| ffmpeg-core.js HTTP | PASS/FAIL | HTTP 200 / ERR_NAME_NOT_RESOLVED |
| ffmpeg-core.wasm.gz HTTP | PASS/FAIL | HTTP 200 / ERR_NAME_NOT_RESOLVED |
| 814.ffmpeg.js HTTP | PASS/FAIL | HTTP 200 / ERR_NAME_NOT_RESOLVED |
| Console FFmpeg 错误 | 无/有 | 无错误 / "FFmpeg 引擎加载失败" |
| 用户可见错误提示 | 有/无 | 有明确提示 / 仅 Console 报错 |
| 功能降级处理 | 合理/不合理 | 按钮禁用+重试入口 / 无响应 |

**结论**: {PASS — 依赖加载正常 / WARN — 可加载但降级不完善 / FAIL — 加载失败}
```



| 场景 | 命令 |
|------|------|
| 全量信息 | `ffprobe -v quiet -print_format json -show_format -show_streams {file}` |
| 视频流参数 | `ffprobe -v quiet -select_streams v:0 -show_entries stream=width,height,codec_name,r_frame_rate,bit_rate -of csv=p=0 {file}` |
| 音频流参数 | `ffprobe -v quiet -select_streams a:0 -show_entries stream=codec_name,sample_rate,channels -of csv=p=0 {file}` |
| 完整性校验 | `ffprobe -v error {file}` — 无输出=文件完整 |
| 格式转换 | `ffmpeg -i input.avi -c:v libx264 -c:a aac output.mp4` |
| 不重编码转封装 | `ffmpeg -i input.avi -c copy output.mp4` |
| 截取片段 | `ffmpeg -ss 00:00:05 -to 00:00:15 -i input.mp4 -c copy clip.mp4` |
| 提取封面 | `ffmpeg -i input.mp4 -an -vframes 1 cover.jpg` |

## 执行红线

1. **不直接修改生产视频文件** — 所有下载的视频只读分析，不写回 OSS
2. **测试数据只在临时目录构造** — `/tmp/test_*`，不污染项目目录
3. **OSS 签名 URL 有时效性** — 下载失败时重新从 DB 查询新 URL，不缓存
4. **损坏文件必须标注** — 构造的 corrupted/empty/fake 文件名含 `test_` 前缀，避免误用
5. **客户端验证只读不写** — 浏览器 Console 检查和 CDN 可达性检查均为只读操作，不修改页面状态或提交数据
6. **不主动触发 WASM 下载** — CDN 可达性检查用 curl HEAD 请求验证，不在浏览器中反复触发大体积 WASM 文件下载

## 与 hfz-test-workflow 编排器的协作

| 编排阶段 | 本技能角色 |
|---------|-----------|
| Stage 0 需求加载 | 读取 features/08-视频生产.md，识别视频相关测试点 |
| Stage 1 用例设计 | 提供视频参数校验点（分辨率/编码/帧率/时长/封面）作为断言 |
| Stage 2 客户端工具验证 | 验证 Web 视频编辑器的 CDN 依赖可达性和 FFmpeg WASM 引擎加载状态 |
| Stage 3 执行 pytest | gen_video 产出后自动调用本技能做 ffprobe 校验 |
| Stage 4 失败分析 | 视频校验失败时，分类是参数不匹配还是文件损坏；客户端工具失败时，分类是 CDN 不可达还是 WASM 版本问题 |
| Stage 9 Bug 草稿 | 视频参数偏离基线时，生成含具体偏离数据的 Bug 草稿；客户端降级不完善时，生成前端体验缺陷草稿 |

## 与 F88失败分析 的协作

当 gen_video FAIL 或视频链路出现已知故障模式时，本技能与 `f88-failure-analysis` 联动：

### gen_video 通用失败辅助
- 验证输入图片是否符合要求（分辨率/格式/大小）
- 检查输出视频 URL 是否过期（`isVideoUrl()` 的 `endsWith(".mp4")` 缺陷）
- 对比同策略不同批次的视频参数一致性

### BT_6149 — 客户端视频编辑器/FFmpeg WASM 加载失败
- `f88-failure-analysis` 将 SharedArrayBuffer/COOP/COEP 报错归类为环境问题后，转交本技能做 CDN 可达性、WASM 引擎加载、降级表现验证
- 本能力六（客户端视频工具依赖加载验证）提供完整的 DNS/HTTP/Console/降级检查清单

### BT_5976 — 视频素材 subJobId 追踪断裂
- 当 `g_afd_material` 中视频/封面操作缺少 `subJobId` 时，链路无法追踪到具体素材操作
- 本技能协助核对：输出视频 URL 与 material 记录、review_job 快照之间的对应关系，定位是哪一次 replaceImage/replaceVideo 操作导致 URL 变更

### BT_6148 — replaceImage 后 BATCH 模式拿到过期视频 URL
- 当批次的 `execMode=BATCH` 时，approve 节点读取 `g_afd_review_job.info` 中的视频快照；replaceImage/replaceVideo 只更新 `g_afd_material.url`，BATCH 模式下下游会拿到旧视频 URL
- 本技能通过 ffprobe 校验实际产出视频，并与 `g_afd_material.url`、`g_afd_review_job.info` 中的 URL 做交叉比对，判断是 URL 传递问题还是视频本身参数问题

### BATCH/STREAM 执行模式差异
- **BATCH**：审核/下游从 `g_afd_review_job.info` 快照读视频 URL，replaceImage 后需同步回写快照，否则下游拿到旧视频
- **STREAM**：审核/下游实时读 `g_afd_material.url`，replaceImage 后立即生效，但需确认本技能下载的视频 URL 来源与 execMode 一致
- 视频校验前应先查 `g_workflow_batch.exec_mode`，避免把 BATCH 快照问题误判为视频生成参数问题

### 查询 `workflow_record_log` 时的 id 过滤约定
- 通用阈值与 `f88-failure-analysis` 保持一致：超大表查询必须加 `id > 4000000`，否则 20s 超时；验证类场景可用更高阈值 `id > 6400000`（如 f88-approve-verify-sql，比通用阈值更严格）
- DB 连接信息见 F88测试知识库/references/shared/db-connections.md（stylespot 生产库 dbId=5335708）

## 参考文档

- `references/verification-baseline.md` — 校验基线参数表 + 策略配置映射
- `references/test-data-catalog.md` — 测试数据完整目录 + 一键构造脚本
- `~/.qoderwork/plugins-custom/qa-testing-workbench/skills/F88测试知识库/references/infra/ffmpeg-verification.md` — FFmpeg 视频校验基础设施（含客户端 WASM 验证章节）
