"""Tests for RTSP health checks using a fake cv2.VideoCapture (no real camera).

These monkeypatch ``cv2.VideoCapture`` itself, so no network connection or
physical camera is ever involved -- just a fake object that behaves like
OpenCV's capture for a known-good and a known-bad stream.
"""

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from camtoolkit.rtsp_health import check_rtsp_health  # noqa: E402


class _FakeGoodCapture:
    def __init__(self, url):
        self.url = url
        self._reads = 0

    def isOpened(self):
        return True

    def set(self, prop, value):
        return True

    def read(self):
        self._reads += 1
        frame = np.zeros((480, 640, 3), dtype="uint8")
        return True, frame

    def release(self):
        pass


class _FakeUnopenableCapture:
    def __init__(self, url):
        self.url = url

    def isOpened(self):
        return False

    def set(self, prop, value):
        return True

    def read(self):
        return False, None

    def release(self):
        pass


def test_check_rtsp_health_success(monkeypatch):
    monkeypatch.setattr(cv2, "VideoCapture", _FakeGoodCapture)
    result = check_rtsp_health("rtsp://example.invalid/stream1", frame_count=5, timeout=5.0)

    assert result.status == "success"
    assert result.width == 640
    assert result.height == 480
    assert result.resolution == "640x480"
    assert result.frames_captured == 5
    assert result.time_to_first_frame_sec is not None
    assert result.achieved_fps is not None


def test_check_rtsp_health_error_when_stream_cannot_open(monkeypatch):
    monkeypatch.setattr(cv2, "VideoCapture", _FakeUnopenableCapture)
    result = check_rtsp_health("rtsp://example.invalid/stream1", frame_count=5, timeout=5.0)

    assert result.status == "error"
    assert "Could not open" in result.error_message


def test_check_rtsp_health_timeout(monkeypatch):
    import time

    class _FakeSlowCapture(_FakeGoodCapture):
        def read(self):
            time.sleep(2)
            return super().read()

    monkeypatch.setattr(cv2, "VideoCapture", _FakeSlowCapture)
    result = check_rtsp_health("rtsp://example.invalid/stream1", frame_count=5, timeout=0.2)

    assert result.status == "timeout"
