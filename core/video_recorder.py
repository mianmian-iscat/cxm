"""
video_recorder.py — 视频录制引擎

利用 CDP Page.startScreencast / Page.screencastFrame 实现实时录屏，
将帧序列合成为 MP4 文件。

依赖：ffmpeg（系统安装）

使用方式：
    recorder = VideoRecorder(cdp_client, output_path="/path/to/output.mp4")
    await recorder.start()
    # ... 执行测试步骤 ...
    await recorder.stop()   # 自动合成 MP4
"""

import asyncio
import base64
import os
import subprocess
import tempfile
import time

class VideoRecorder:
    """
    基于 CDP screencast 的视频录制器。
    帧率：5fps（CDP screencast 的合理上限，降低对页面性能的影响）
    格式：PNG 帧 → ffmpeg → MP4 (H.264)
    """

    FRAME_RATE = 5          # fps
    JPEG_QUALITY = 75       # screencast 帧质量（0-100）
    MAX_WIDTH = 1280        # 帧宽度上限（降低带宽）

    def __init__(self, cdp_client, output_path: str):
        self._client = cdp_client
        self._output_path = output_path
        self._frames_dir = None
        self._frame_count = 0
        self._recording = False
        self._frame_times = []

    async def start(self):
        """开始录制"""
        self._frames_dir = tempfile.mkdtemp(prefix="screencast_")
        self._frame_count = 0
        self._frame_times = []
        self._recording = True

        # 注册帧接收器
        self._client.on("Page.screencastFrame", self._on_frame)

        # 启动 CDP screencast
        await self._client.send("Page.startScreencast", {
            "format": "jpeg",
            "quality": self.JPEG_QUALITY,
            "maxWidth": self.MAX_WIDTH,
            "everyNthFrame": 1,
        })

    async def stop(self) -> str:
        """停止录制，合成 MP4，返回文件路径"""
        if not self._recording:
            return None

        self._recording = False
        self._client.off("Page.screencastFrame", self._on_frame)

        await self._client.send("Page.stopScreencast", {})
        await asyncio.sleep(0.5)  # 等待最后几帧写入

        if self._frame_count == 0:
            return None

        output = await self._compose_video()
        self._cleanup_frames()
        return output

    async def _on_frame(self, params: dict):
        """接收 screencast 帧，写入临时目录"""
        if not self._recording:
            return

        # 确认帧接收
        session_id = params.get("sessionId")
        if session_id is not None:
            try:
                await self._client.send("Page.screencastFrameAck", {"sessionId": session_id})
            except Exception:
                pass

        # 写帧文件
        data = params.get("data", "")
        if data:
            self._frame_count += 1
            self._frame_times.append(time.time())
            frame_path = os.path.join(self._frames_dir, f"frame_{self._frame_count:06d}.jpg")
            with open(frame_path, "wb") as f:
                f.write(base64.b64decode(data))

    async def _compose_video(self) -> str:
        """用 ffmpeg 将帧序列合成为 MP4"""
        os.makedirs(os.path.dirname(self._output_path), exist_ok=True)

        # 计算实际帧率（基于录制时长和帧数）
        if len(self._frame_times) >= 2:
            duration = self._frame_times[-1] - self._frame_times[0]
            actual_fps = max(1, int(self._frame_count / max(duration, 1)))
        else:
            actual_fps = self.FRAME_RATE

        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(actual_fps),
            "-pattern_type", "glob",
            "-i", os.path.join(self._frames_dir, "frame_*.jpg"),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "fast",
            "-crf", "23",
            self._output_path
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg 合成失败: {stderr.decode()}")

        return self._output_path

    def _cleanup_frames(self):
        """清理临时帧文件"""
        if self._frames_dir and os.path.exists(self._frames_dir):
            import shutil
            shutil.rmtree(self._frames_dir, ignore_errors=True)

    @property
    def frame_count(self) -> int:
        return self._frame_count

    @staticmethod
    def is_ffmpeg_available() -> bool:
        """检查 ffmpeg 是否可用"""
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
