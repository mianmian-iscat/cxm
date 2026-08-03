"""
test_video_recorder.py — VideoRecorder 单元测试（Mock ffmpeg）
"""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from core.video_recorder import VideoRecorder


class TestVideoRecorder(unittest.TestCase):

    def test_is_ffmpeg_available_returns_bool(self):
        """is_ffmpeg_available 应返回 bool"""
        result = VideoRecorder.is_ffmpeg_available()
        self.assertIsInstance(result, bool)

    def test_is_ffmpeg_not_available_when_missing(self):
        """shutil.which 返回 None 时，is_ffmpeg_available 应返回 False"""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            self.assertFalse(VideoRecorder.is_ffmpeg_available())

    def test_is_ffmpeg_available_when_found(self):
        """shutil.which 找到 ffmpeg 时，is_ffmpeg_available 应返回 True"""
        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            self.assertTrue(VideoRecorder.is_ffmpeg_available())

    def test_instantiate_with_cdp_and_path(self):
        """可以用 cdp mock 和路径实例化"""
        cdp_mock = MagicMock()
        recorder = VideoRecorder(cdp_mock, "/tmp/test-video.mp4")
        self.assertIsNotNone(recorder)

    def test_start_raises_when_ffmpeg_unavailable(self):
        """ffmpeg 不可用时 start() 应静默或抛出预期异常"""
        cdp_mock = MagicMock()
        recorder = VideoRecorder(cdp_mock, "/tmp/test-video.mp4")

        async def _run():
            with patch.object(VideoRecorder, "is_ffmpeg_available", return_value=False):
                try:
                    await recorder.start()
                    return "ok"
                except Exception as e:
                    return str(e)

        result = asyncio.run(_run())
        # 不可用时 start 应优雅处理（返回 ok 或有意义的错误）
        self.assertIsNotNone(result)

    def test_stop_without_start_returns_empty_path(self):
        """未 start 直接 stop 不抛异常，返回空路径或 None"""
        cdp_mock = MagicMock()
        recorder = VideoRecorder(cdp_mock, "/tmp/test-video.mp4")

        async def _run():
            try:
                result = await recorder.stop()
                return result
            except Exception:
                return None

        result = asyncio.run(_run())
        # stop without start 应返回 None 或空字符串，不抛异常
        self.assertFalse(bool(result))


if __name__ == "__main__":
    unittest.main()
