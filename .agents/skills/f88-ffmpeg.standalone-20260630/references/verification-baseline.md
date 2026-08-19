---
id: f88-ffmpeg/verification-baseline
title: gen_video 输出物校验基线
version: 1.0.0
created: 2026-06-30
updated: 2026-06-30
---

# gen_video 输出物校验基线

## 策略配置到视频参数的映射

### 从 DB 获取策略配置

```sql
-- 查策略的 gen_video 节点配置
SELECT
  s.id AS strategy_id,
  s.name AS strategy_name,
  jn.type AS node_type,
  jn.imageSize AS expected_size,
  jn.outputRatio AS expected_ratio,
  jn.outputModel AS output_model
FROM g_strategy s,
JSON_TABLE(s.workflow_def, '$.innerNodes[*]' COLUMNS(
  type VARCHAR(50) PATH '$.type',
  imageSize VARCHAR(20) PATH '$.imageSize',
  outputRatio VARCHAR(20) PATH '$.outputRatio',
  outputModel VARCHAR(20) PATH '$.outputModel'
)) AS jn
WHERE s.id = {strategy_id}
  AND jn.type = 'gen_video';
```

### 参数校验基线表

| 参数 | 来源 | 校验规则 | 典型值 |
|------|------|---------|--------|
| width | ffprobe streams[video].width | == imageSize 的宽度部分 | 1280, 1920 |
| height | ffprobe streams[video].height | == imageSize 的高度部分 | 720, 1080 |
| aspect_ratio | width / height | == outputRatio，误差 ≤ 0.01 | 1.778 (16:9) |
| codec | ffprobe streams[video].codec_name | ∈ {h264, hevc, h265} | h264 |
| fps | ffprobe streams[video].r_frame_rate | 解析分数，∈ {24, 25, 30} | 30/1 |
| duration | ffprobe format.duration | ≤ 60s（默认） | 5-15s |
| file_size | ffprobe format.size | ≤ 100MB | 2-20MB |
| audio_track | ffprobe streams[audio] | 可选（gen_video 可能无音轨） | aac |
| corruption | ffprobe -v error 输出 | 无错误输出 | 空 |

### 常见 imageSize 到分辨率的映射

| imageSize 配置 | 预期 width | 预期 height | 预期 ratio |
|---------------|-----------|-------------|------------|
| 1280x720 | 1280 | 720 | 1.778 |
| 1920x1080 | 1920 | 1080 | 1.778 |
| 720x720 | 720 | 720 | 1.000 |
| 1080x1080 | 1080 | 1080 | 1.000 |
| 720x1280 | 720 | 1280 | 0.563 |
| 1080x1920 | 1080 | 1920 | 0.563 |

### 常见 outputRatio 到宽高比的映射

| outputRatio 配置 | 预期 ratio | 常见用途 |
|-----------------|-----------|---------|
| 16:9 | 1.778 | 横屏视频 |
| 9:16 | 0.563 | 竖屏视频 |
| 1:1 | 1.000 | 方形视频 |
| 4:3 | 1.333 | 传统比例 |
| 3:4 | 0.750 | 竖屏偏方 |

## 校验结果分类

| 结果 | 含义 | 后续动作 |
|------|------|---------|
| PASS | 参数完全符合基线 | 记录到校验报告 |
| WARN | 参数在容差内但接近边界 | 记录 + 标注风险 |
| FAIL | 参数超出基线范围 | 记录 + 生成 Bug 草稿 |
| ERROR | ffprobe 无法解析文件 | 记录 + 检查 OSS URL 是否过期 |

## OSS 签名 URL 处理

gen_video 输出的 URL 通常是 OSS 签名 URL，格式：
```
https://{bucket}.oss-cn-{region}.aliyuncs.com/{path}?Expires={ts}&OSSAccessKeyId={key}&Signature={sig}
```

注意事项：
- Expires 是 Unix 时间戳，过期后 curl 会返回 403
- 下载失败时先从 DB 重新查询最新 URL
- URL 中的 `&` 和 `=` 在 shell 中需要引号包裹
- 视频 URL 中可能包含 `response-content-disposition` 参数，不影响下载
