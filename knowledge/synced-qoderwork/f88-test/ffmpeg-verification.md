<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/qa-testing-workbench/skills/F88测试知识库/references/infra/ffmpeg-verification.md -->
<!-- synced-at: 2026-07-11T03:52:35.004665 -->
<!-- skill: F88测试知识库 -->

---
id: infra/ffmpeg-verification
title: FFmpeg/FFprobe 视频输出物校验基础设施
tags: [ffmpeg, ffprobe, 视频校验, gen_video, 输出物验证, WASM, 客户端视频工具]
owner: 目民
version: 1.2.0
created: 2026-06-30
updated: 2026-07-02
source_sessions: []
promotion_count: 0
---

# FFmpeg/FFprobe 视频输出物校验基础设施

## 安装方式

当前环境无法使用 Homebrew（需 sudo 权限），采用 pip `static-ffmpeg` 方案：

```bash
pip3 install --user static-ffmpeg
```

安装后二进制位置：
- ffmpeg: `~/.local/bin/ffmpeg` → symlink 到 `static_ffmpeg` 包内 `darwin_arm64/ffmpeg`
- ffprobe: `~/.local/bin/ffprobe` → symlink 到 `static_ffmpeg` 包内 `darwin_arm64/ffprobe`

**验证安装**：
```bash
~/.local/bin/ffmpeg -version | head -1   # 应输出 ffmpeg version 7.0
~/.local/bin/ffprobe -version | head -1  # 应输出 ffprobe version 7.0
```

## 校验流程

### Step 1: 从 DB 提取视频 URL

```sql
SELECT
  id,
  JSON_EXTRACT(output_json, '$.outputVideo') AS video_url,
  JSON_EXTRACT(output_json, '$.outputCover') AS cover_url,
  JSON_EXTRACT(extra_info, '$.strategyName') AS strategy_name
FROM workflow_record_log
WHERE batch_id = '{batch_id}'
  AND node_type = 'gen_video'
  AND status = 'SUCCESS'
ORDER BY gmt_create DESC
LIMIT 10;
```

### Step 2: 下载视频

```bash
curl -sL "{video_url}" -o /tmp/f88_video_{id}.mp4
```

**注意**：scene-ossgw.taobao.com 直链无签名，可直接下载。如有 `?Expires=` 参数，过期后从 DB 重新查询。

### Step 3: ffprobe 提取参数

```bash
~/.local/bin/ffprobe -v quiet -print_format json -show_format -show_streams /tmp/f88_video_{id}.mp4
```

### Step 4: 解析关键参数

```bash
~/.local/bin/ffprobe -v quiet -print_format json -show_streams -show_format /tmp/f88_video_{id}.mp4 | \
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

### Step 5: 对比策略配置

从 `g_strategy.workflow_def` 中 gen_video 节点读取预期值：
- `imageSize` → 预期分辨率（如 `1280x720`）
- `outputRatio` → 预期宽高比（如 `16:9` → 1.778）

## 视频 URL 格式与来源

F88 视频 URL 有两种来源，下载和校验时需区别对待：

| 来源 | URL 格式示例 | 签名 | 时效性 | `isVideoUrl()` 兼容性 |
|------|-------------|------|--------|----------------------|
| scene-ossgw.taobao.com | `https://scene-ossgw.taobao.com/costume_project/resource/sd/seedance_video_{id}_{ts}.mp4` | 无签名 | 长期有效 | 正常（以 `.mp4` 结尾） |
| OSS 签名 URL | `https://{bucket}.oss-cn-{region}.aliyuncs.com/{path}?Expires={ts}&OSSAccessKeyId={key}&Signature={sig}` | 有签名 | Expires 过期后 403 | **失败**（不以 `.mp4` 结尾） |

**`isVideoUrl()` 缺陷影响**：
- `VideoPushTaskBuilder.isVideoUrl()` 使用 `endsWith(".mp4")` 判断 URL 是否为视频
- 对 scene-ossgw URL 正常（URL 以 `.mp4` 结尾）
- 对 OSS 签名 URL 失败（URL 以 `&Signature=xxx` 结尾），导致视频被误判为非视频，推送时静默丢弃
- 详见 `patterns/video-push-code-defects.md`

**下载失败处理**：
- scene-ossgw URL：直接 `curl -sL` 下载，无需额外参数
- OSS 签名 URL 返回 403：从 DB 重新查询最新 URL（签名已过期），不可缓存 URL

## 多视频场景基线

`VideoPushTaskBuilder` 已知缺陷：只取 `videoUrls.get(0)`，多视频输入时丢弃后续视频。

**测试数据构造**：
```bash
# 3 个不同内容的视频
ffmpeg -f lavfi -i testsrc=duration=3:size=720x720:rate=24 -c:v libx264 -y /tmp/test_multi_v1.mp4
ffmpeg -f lavfi -i color=c=red:duration=3:size=720x720:rate=24 -c:v libx264 -y /tmp/test_multi_v2.mp4
ffmpeg -f lavfi -i color=c=blue:duration=3:size=720x720:rate=24 -c:v libx264 -y /tmp/test_multi_v3.mp4

# 不同格式的多视频
ffmpeg -f lavfi -i testsrc=duration=3:size=720x720:rate=24 -c:v libx264 -y /tmp/test_multi_a.mp4
ffmpeg -f lavfi -i testsrc=duration=3:size=720x720:rate=24 -c:v libvpx-vp9 -y /tmp/test_multi_b.webm
ffmpeg -f lavfi -i testsrc=duration=3:size=720x720:rate=24 -y /tmp/test_multi_c.avi
```

**验证步骤**：
1. 将 3 个视频 URL 作为 `videoUrls` 数组输入
2. 检查 `VideoPushTaskBuilder` 输出的 `output_json` 中视频 URL 数量
3. 如只推送第一个 → 确认已知缺陷仍在，记录为 SKIP（已知问题）
4. 如推送了全部 → 缺陷已修复，更新 `patterns/video-push-code-defects.md`

**推送完整性 SQL**：
```sql
SELECT
  node_type, status, COUNT(*) AS cnt,
  JSON_EXTRACT(extra_info, '$.errorMsg') AS error_msg
FROM workflow_record_log
WHERE batch_id = '{batch_id}'
  AND node_type IN ('gen_video', 'video_push')
  AND id > {last_id}
GROUP BY node_type, status, JSON_EXTRACT(extra_info, '$.errorMsg');
```

## 校验基线

| 参数 | 校验规则 | 容差 |
|------|---------|------|
| 分辨率 | width/height vs imageSize | 精确匹配 |
| 宽高比 | width/height vs outputRatio | 误差 ≤ 0.01 |
| 编码 | codec_name | ∈ {h264, hevc, h265} |
| 帧率 | r_frame_rate 解析为数值 | ∈ {24, 25, 30} |
| 时长 | format.duration | ≤ 60s |
| 完整性 | `ffprobe -v error` | 无输出 |
| 封面 | outputCover URL 可访问 | HTTP 200 |

## 实测基线（2026-06-30）

预发环境 taskId=1206238（mmtest视频审核-BT_5926）实测值：

| 参数 | 实测值 |
|------|--------|
| 分辨率 | 1248x1664 |
| 编码 | h264 (High profile) |
| 帧率 | 24fps |
| 时长 | 5.04s |
| 文件大小 | 4.4MB |
| 码率 | 6.88Mbps (视频) + 132kbps (音频) |
| 音轨 | AAC LC 44.1kHz 立体声 |
| 宽高比 | 0.75 (3:4 竖屏) |

## 与 opencv-python-headless 的对比

| 维度 | opencv | ffprobe |
|------|--------|---------|
| 安装 | `pip install opencv-python-headless` | `pip install --user static-ffmpeg` |
| 二进制大小 | ~30MB | ~50MB |
| 提取参数 | 仅 width/height（需 `cv2.VideoCapture`） | 全量（编码/帧率/码率/时长/音轨/完整性） |
| 完整性校验 | 不支持 | `ffprobe -v error` |
| 音频信息 | 不支持 | 支持 |
| 性能 | 需加载 OpenCV 运行时 | 直接二进制调用，更快 |

**结论**：ffprobe 全面优于 opencv，新测试统一用 ffprobe。

## 客户端 FFmpeg WASM 引擎加载验证

F88 平台提供浏览器端"视频剪辑"工具，其 FFmpeg 引擎以 WASM 形式从自有 CDN（`dev.g.alicdn.com/f-mod/alibaba-puhuiti/0.0.4/`）加载。当客户端网络异常或 CDN 不可达时，引擎加载失败，编辑器功能完全降级。

### 故障链路

```
客户端 DNS 解析失败
  → CDN 域名（dev.g.alicdn.com / img.alicdn.com）ERR_NAME_NOT_RESOLVED
    → FFmpeg WASM 二进制 fetch 失败（ffmpeg-core.js / ffmpeg-core.wasm.gz / 814.ffmpeg.js）
      → Console: "FFmpeg 引擎加载失败: TypeError: Failed to fetch"
        → 视频编辑器功能不可用
```

### 关键 CDN 域名

| 域名 | 用途 | 影响范围 |
|------|------|---------|
| `dev.g.alicdn.com` | 托管 FFmpeg WASM 二进制（ffmpeg-core.js / ffmpeg-core.wasm.gz / 814.ffmpeg.js），路径 `/f-mod/alibaba-puhuiti/0.0.4/` | FFmpeg 引擎加载 |
| `img.alicdn.com` | 页面图片资源、UI 素材 | 页面渲染完整性 |
| `scene-ossgw.taobao.com` | 视频/图片产出物 | 视频预览和下载 |

### CDN 可达性检查脚本

```bash
# DNS 解析
for domain in dev.g.alicdn.com img.alicdn.com scene-ossgw.taobao.com; do
  echo "=== $domain ==="
  nslookup "$domain" 2>&1 | head -5
done

# HTTP 可达性（HEAD 请求）
for url in \
  "https://dev.g.alicdn.com/f-mod/alibaba-puhuiti/0.0.4/ffmpeg-core.js" \
  "https://dev.g.alicdn.com/f-mod/alibaba-puhuiti/0.0.4/ffmpeg-core.wasm.gz" \
  "https://dev.g.alicdn.com/f-mod/alibaba-puhuiti/0.0.4/814.ffmpeg.js"; do
  code=$(curl -sI -o /dev/null -w "%{http_code}" --connect-timeout 5 "$url" 2>/dev/null)
  echo "$url → HTTP $code"
done
```

### Console 日志识别

| 日志模式 | 含义 | 严重度 |
|---------|------|--------|
| `FFmpeg 引擎加载失败: TypeError: Failed to fetch` | WASM 无法下载 | ERROR |
| `ERR_NAME_NOT_RESOLVED` + `dev.g.alicdn.com` | FFmpeg WASM CDN DNS 失败 | ERROR（根因） |
| `ERR_NAME_NOT_RESOLVED` + `img.alicdn.com` | 图片 CDN 也挂 | ERROR |
| `[APLUS] → APLUS INIT SUCCESS` | 埋点 SDK 正常 | INFO（对比参考） |

### 前端降级缺陷（2026-07-02 发现）

| 缺陷 | 现状 | 期望 |
|------|------|------|
| 无用户可见错误提示 | 仅 Console 报错 | 显示"视频工具加载失败，请检查网络" |
| 功能按钮未禁用 | 可点击但无响应 | 置灰或隐藏 |
| 无重试入口 | 只能刷新整页 | 提供"重新加载引擎"按钮 |
| 无超时控制 | 依赖浏览器默认超时 | fetch 设 30s 超时 |

### 多网络环境预期

| 网络环境 | CDN 可达性 | 预期结果 |
|---------|-----------|---------|
| 公司内网（无 VPN） | 可达 | 正常加载 |
| 家庭宽带 | 可达 | 正常加载 |
| 断网 / DNS 异常 | 不可达 | 应展示降级提示 |

## 关联技能

- `f88-ffmpeg`：F88 QA 套件的视频校验子技能（`plugins-custom/qa-testing-workbench/skills/f88-ffmpeg/`）
- `F88失败分析`：失败分析时调用 ffprobe 验证输出物
- `strategy-platform`：批次监控时可选校验视频产出
