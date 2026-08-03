<!-- synced-from: /Users/caoxuemei/.qoderwork/plugins-custom/qa-testing-workbench/skills/f88-ffmpeg/references/test-data-catalog.md -->
<!-- synced-at: 2026-07-11T03:52:35.008291 -->
<!-- skill: f88-ffmpeg -->

---
id: f88-ffmpeg/test-data-catalog
title: F88 视频测试数据目录
version: 1.0.0
created: 2026-06-30
updated: 2026-06-30
---

# F88 视频测试数据目录

## 分类说明

测试数据按用途分为三类：
- **正常数据**: 用于基线验证，确认系统处理标准文件的能力
- **边界数据**: 用于边界值测试，验证系统在极限参数下的行为
- **异常数据**: 用于容错测试，验证系统对损坏/非法文件的处理

## 一、正常格式（基线验证）

| 编号 | 文件名 | 编码 | 分辨率 | 帧率 | 时长 | 用途 |
|------|--------|------|--------|------|------|------|
| N01 | test_normal.mp4 | H.264+AAC | 1280x720 | 30fps | 5s | 标准基准对照 |
| N02 | test_640x360.mp4 | H.264 | 640x360 | 24fps | 3s | 低分辨率 |
| N03 | test_1280x720.mp4 | H.264 | 1280x720 | 24fps | 3s | 标准HD |
| N04 | test_1920x1080.mp4 | H.264 | 1920x1080 | 24fps | 3s | 全HD |
| N05 | test_hevc.mp4 | H.265 | 720x720 | 24fps | 3s | HEVC编码 |
| N06 | test_vp9.webm | VP9 | 720x720 | 24fps | 3s | VP9编码 |
| N07 | test_format.avi | 默认 | 720x720 | 24fps | 3s | AVI容器 |
| N08 | test_format.mov | 默认 | 720x720 | 24fps | 3s | MOV容器 |
| N09 | test_format.mkv | 默认 | 720x720 | 24fps | 3s | MKV容器 |
| N10 | test_format.webm | 默认 | 720x720 | 24fps | 3s | WebM容器 |
| N11 | test_format.flv | 默认 | 720x720 | 24fps | 3s | FLV容器 |
| N12 | test_format.wmv | 默认 | 720x720 | 24fps | 3s | WMV容器 |

## 二、边界数据（极限测试）

| 编号 | 文件名 | 特征 | 测试目的 |
|------|--------|------|---------|
| B01 | test_tiny.mp4 | 1x1分辨率 | 极小分辨率容错 |
| B02 | test_4k.mp4 | 3840x2160 | 4K超大分辨率 |
| B03 | test_square.mp4 | 720x720 1:1 | 非标准宽高比 |
| B04 | test_1fps.mp4 | 1fps | 极低帧率 |
| B05 | test_60fps.mp4 | 60fps | 高帧率 |
| B06 | test_short.mp4 | 0.5秒 | 极短时长 |
| B07 | test_no_audio.mp4 | 无音轨 | 纯视频流 |
| B08 | test_large.mp4 | >50MB | 大文件处理 |

## 三、异常数据（容错测试）

| 编号 | 文件名 | 构造方式 | 测试目的 |
|------|--------|---------|---------|
| E01 | test_corrupted.mp4 | dd截断至10KB | 损坏文件容错 |
| E02 | test_empty.mp4 | touch创建空文件 | 空文件容错 |
| E03 | test_fake.mp4 | echo文本写入 | 伪装文件检测 |

## 四、输入图片数据（gen_video 输入）

| 编号 | 文件名 | 格式 | 分辨率 | 测试目的 |
|------|--------|------|--------|---------|
| I01 | test_input.jpg | JPEG | 1280x720 | 标准输入 |
| I02 | test_input.png | PNG | 720x720 | PNG格式 |
| I03 | test_input.bmp | BMP | 720x720 | BMP格式 |
| I04 | test_input.tiff | TIFF | 720x720 | TIFF格式 |
| I05 | test_input.webp | WebP | 720x720 | WebP格式 |
| I06 | test_huge_input.jpg | JPEG | 4096x4096 | 超大输入 |

## 构造脚本

### 一键构造全部正常数据

```bash
#!/bin/bash
set -e
OUT=/tmp/f88_test_data
mkdir -p $OUT

# 标准 MP4
ffmpeg -f lavfi -i testsrc=duration=5:size=1280x720:rate=30 \
       -f lavfi -i sine=frequency=440:duration=5 \
       -c:v libx264 -c:a aac -y $OUT/test_normal.mp4

# 多分辨率
for res in 640x360 1280x720 1920x1080; do
  ffmpeg -f lavfi -i testsrc=duration=3:size=${res}:rate=24 \
         -c:v libx264 -y $OUT/test_${res/x/_}.mp4
done

# 多编码
ffmpeg -f lavfi -i testsrc=duration=3:size=720x720:rate=24 -c:v libx265 -y $OUT/test_hevc.mp4
ffmpeg -f lavfi -i testsrc=duration=3:size=720x720:rate=24 -c:v libvpx-vp9 -y $OUT/test_vp9.webm

# 多容器
for fmt in avi mov mkv webm flv wmv; do
  ffmpeg -f lavfi -i testsrc=duration=3:size=720x720:rate=24 -y $OUT/test_format.${fmt}
done

echo "正常数据构造完成: $(ls $OUT/ | wc -l) 个文件"
```

### 一键构造全部边界 + 异常数据

```bash
#!/bin/bash
set -e
OUT=/tmp/f88_test_data_edge
mkdir -p $OUT

# 边界
ffmpeg -f lavfi -i testsrc=duration=2:size=1x1:rate=1 -c:v libx264 -y $OUT/test_tiny.mp4
ffmpeg -f lavfi -i testsrc=duration=2:size=3840x2160:rate=15 -c:v libx264 -y $OUT/test_4k.mp4
ffmpeg -f lavfi -i testsrc=duration=3:size=720x720:rate=24 -c:v libx264 -y $OUT/test_square.mp4
ffmpeg -f lavfi -i testsrc=duration=5:size=720x720:rate=1 -c:v libx264 -y $OUT/test_1fps.mp4
ffmpeg -f lavfi -i testsrc=duration=3:size=720x720:rate=60 -c:v libx264 -y $OUT/test_60fps.mp4
ffmpeg -f lavfi -i testsrc=duration=0.5:size=720x720:rate=24 -c:v libx264 -y $OUT/test_short.mp4
ffmpeg -f lavfi -i testsrc=duration=3:size=720x720:rate=24 -c:v libx264 -an -y $OUT/test_no_audio.mp4
ffmpeg -f lavfi -i testsrc=duration=30:size=1920x1080:rate=30 -c:v libx264 -b:v 15M -y $OUT/test_large.mp4

# 异常
dd if=$OUT/test_normal.mp4 of=$OUT/test_corrupted.mp4 bs=1024 count=10 2>/dev/null || \
  dd if=/tmp/f88_test_data/test_normal.mp4 of=$OUT/test_corrupted.mp4 bs=1024 count=10
touch $OUT/test_empty.mp4
echo "not a video" > $OUT/test_fake.mp4

echo "边界+异常数据构造完成: $(ls $OUT/ | wc -l) 个文件"
```

## 已知限制

- WMV 容器在 macOS FFmpeg 默认配置下可能不支持，需要额外编译参数
- FLV 容器仅支持 H.264 + MP3/AAC 编码组合
- 1x1 分辨率的视频某些播放器可能无法显示，但 ffprobe 可正常解析
- 4K 视频构造耗时较长（约 10-30 秒），视机器性能而定
