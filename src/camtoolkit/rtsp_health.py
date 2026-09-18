"""RTSP stream health checks.

Once a camera has been found (by discovery or from the manual inventory),
the next question during a site survey is: "does its actual video stream
work, and how well?" This module connects to an RTSP URL with OpenCV's
``VideoCapture`` and measures the numbers that matter when sizing an
architecture:

- time-to-first-frame (a proxy for connection / stream-startup latency)
- achieved frames-per-second over a short sample window
- the stream's actual resolution (which is sometimes different from what
  the camera's configuration page claims)
- a simple reachability status: ``success``, ``timeout``, or ``error``

RTSP connections to a dead or unreachable camera can hang for a long time
inside OpenCV/FFmpeg internals, well past any ``CAP_PROP_*TIMEOUT`` hint
you set on the ``VideoCapture`` object -- those hints are backend-dependent
and not always honored. To make sure a single bad camera can never freeze
a whole site survey, the actual probe runs in a background thread and is
bounded with a hard wall-clock timeout from the caller's side; if the
thread does not finish in time we simply give up on it and report
``timeout`` instead of blocking forever.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional

STATUS_SUCCESS = "success"
STATUS_TIMEOUT = "timeout"
STATUS_ERROR = "error"


class RtspConnectionError(RuntimeError):
    """Raised internally when a stream can't be opened or read."""


@dataclass
class RtspHealthResult:
    """Result of probing a single RTSP stream."""

    url: str
    status: str
    error_message: str = ""
    time_to_first_frame_sec: Optional[float] = None
    achieved_fps: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    frames_captured: int = 0

    @property
    def resolution(self) -> str:
        if self.width and self.height:
            return f"{self.width}x{self.height}"
        return ""

    def as_dict(self) -> dict:
        return {
            "url": self.url,
            "status": self.status,
            "error_message": self.error_message,
            "time_to_first_frame_sec": self.time_to_first_frame_sec,
            "achieved_fps": self.achieved_fps,
            "resolution": self.resolution,
            "width": self.width,
            "height": self.height,
            "frames_captured": self.frames_captured,
        }


def _probe_stream(rtsp_url: str, frame_count: int, open_timeout_msec: int) -> dict:
    """Do the actual OpenCV work. Runs inside a worker thread.

    Any failure is raised as :class:`RtspConnectionError` so the caller can
    translate it into a clean ``status="error"`` result.
    """
    import cv2  # imported lazily so importing this module never requires cv2's native deps

    cap = cv2.VideoCapture(rtsp_url)

    # These hints are honored by the FFmpeg backend on reasonably recent
    # OpenCV builds. They are a *best effort* second line of defense; the
    # authoritative timeout is the ThreadPoolExecutor deadline enforced by
    # check_rtsp_health() below, which works regardless of backend.
    try:
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, open_timeout_msec)
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, open_timeout_msec)
    except AttributeError:
        pass  # older OpenCV builds do not expose these properties

    try:
        if not cap.isOpened():
            raise RtspConnectionError(f"Could not open RTSP stream: {rtsp_url}")

        start = time.monotonic()
        ok, frame = cap.read()
        if not ok or frame is None:
            raise RtspConnectionError(f"Stream opened but no frame was returned: {rtsp_url}")
        time_to_first_frame = time.monotonic() - start

        height, width = frame.shape[0], frame.shape[1]

        frames_captured = 1
        fps_window_start = time.monotonic()
        for _ in range(max(frame_count - 1, 0)):
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            frames_captured += 1
        fps_window_elapsed = time.monotonic() - fps_window_start

        if frames_captured > 1 and fps_window_elapsed > 0:
            achieved_fps = (frames_captured - 1) / fps_window_elapsed
        else:
            achieved_fps = 0.0

        return {
            "time_to_first_frame_sec": time_to_first_frame,
            "achieved_fps": achieved_fps,
            "width": width,
            "height": height,
            "frames_captured": frames_captured,
        }
    finally:
        cap.release()


def check_rtsp_health(
    rtsp_url: str,
    frame_count: int = 30,
    timeout: float = 8.0,
) -> RtspHealthResult:
    """Connect to ``rtsp_url`` and measure its health.

    Parameters
    ----------
    rtsp_url:
        Full RTSP URL, e.g. ``rtsp://user:pass@192.168.1.50:554/stream1``.
    frame_count:
        Number of frames to sample (including the first frame) to compute
        achieved FPS. Higher values give a steadier FPS estimate but take
        longer.
    timeout:
        Hard wall-clock ceiling, in seconds, for the *entire* probe
        (connecting, reading the first frame, and sampling ``frame_count``
        frames). If this elapses, the result has ``status="timeout"`` and
        no measurements are returned. This bound is enforced from outside
        OpenCV, so it holds even if the underlying stream hangs the
        decoder thread indefinitely.

    Returns
    -------
    An :class:`RtspHealthResult` with ``status`` set to one of
    ``"success"``, ``"timeout"``, or ``"error"``.
    """
    # A plain daemon thread (rather than concurrent.futures.ThreadPoolExecutor)
    # is used deliberately. ThreadPoolExecutor's worker threads are
    # non-daemon by default, and Python's interpreter shutdown joins every
    # non-daemon thread before exiting -- so a stuck FFmpeg/RTSP connection
    # would silently make the whole CLI process hang at exit even though
    # this function itself returned a clean "timeout" result. Marking the
    # thread as a daemon means the process can exit immediately; the stuck
    # thread is abandoned to the OS to clean up whenever the underlying
    # socket eventually gives up.
    outcome: dict = {}

    def worker():
        try:
            outcome["measurements"] = _probe_stream(rtsp_url, frame_count, int(timeout * 1000))
        except Exception as exc:  # noqa: BLE001 - captured and re-raised in the caller's thread
            outcome["error"] = exc

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout)

    if thread.is_alive():
        return RtspHealthResult(
            url=rtsp_url,
            status=STATUS_TIMEOUT,
            error_message=f"No response within {timeout:.1f}s",
        )

    if "error" in outcome:
        return RtspHealthResult(url=rtsp_url, status=STATUS_ERROR, error_message=str(outcome["error"]))

    measurements = outcome["measurements"]
    return RtspHealthResult(
        url=rtsp_url,
        status=STATUS_SUCCESS,
        time_to_first_frame_sec=round(measurements["time_to_first_frame_sec"], 4),
        achieved_fps=round(measurements["achieved_fps"], 2),
        width=measurements["width"],
        height=measurements["height"],
        frames_captured=measurements["frames_captured"],
    )
