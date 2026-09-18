"""Network readiness checks.

Before sizing a video/AI architecture, a solution engineer needs to know
whether the customer's network will actually let the design work: can the
recording/analytics box reach each camera's RTSP port, can it reach the
camera's management HTTP(S) port, is round-trip latency low enough for
control traffic, and roughly how much bandwidth is available.

This module intentionally keeps each check small and independently
testable:

- :func:`check_tcp_port` / :func:`check_common_ports` open a plain TCP
  socket with a timeout -- no external tools required, and fully testable
  against a local loopback server (see ``tests/test_network_readiness.py``).
- :func:`check_latency` shells out to the platform's ``ping`` utility
  because there is no portable, unprivileged way to send raw ICMP from
  Python (raw ICMP sockets need administrator/root privileges on most
  platforms). It degrades gracefully when ping is blocked or missing.
- :func:`estimate_bandwidth_headroom` is an explicit, documented
  placeholder formula, not a real throughput test. Measuring true
  available bandwidth needs a proper tool (iperf3, etc.) run from both
  ends of the link, which is out of scope for a lightweight discovery
  toolkit run from a single laptop.
"""

from __future__ import annotations

import platform
import re
import socket
import subprocess
from dataclasses import dataclass
from typing import Optional

# Ports that matter for a typical IP camera / VMS deployment.
DEFAULT_PORTS = {
    554: "RTSP",
    80: "HTTP",
    443: "HTTPS",
    8000: "Custom API",
}

PORT_STATUS_OPEN = "open"
PORT_STATUS_CLOSED = "closed"
PORT_STATUS_TIMEOUT = "timeout"
PORT_STATUS_ERROR = "error"


@dataclass
class PortCheckResult:
    host: str
    port: int
    label: str
    status: str
    error_message: str = ""
    connect_time_sec: Optional[float] = None

    def as_dict(self) -> dict:
        return {
            "host": self.host,
            "port": self.port,
            "label": self.label,
            "status": self.status,
            "error_message": self.error_message,
            "connect_time_sec": self.connect_time_sec,
        }


def check_tcp_port(host: str, port: int, timeout: float = 2.0, label: str = "") -> PortCheckResult:
    """Attempt a plain TCP connect to ``host:port`` with a hard timeout.

    This never raises: connection refused, timeout, DNS failure, and any
    other socket error are all captured and returned as a ``PortCheckResult``
    with an appropriate ``status``, so a whole survey can run unattended
    without one unreachable host aborting the process.
    """
    import time

    label = label or DEFAULT_PORTS.get(port, "")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    start = time.monotonic()
    try:
        sock.connect((host, port))
        elapsed = time.monotonic() - start
        return PortCheckResult(
            host=host, port=port, label=label, status=PORT_STATUS_OPEN, connect_time_sec=round(elapsed, 4)
        )
    except socket.timeout:
        return PortCheckResult(
            host=host,
            port=port,
            label=label,
            status=PORT_STATUS_TIMEOUT,
            error_message=f"No response within {timeout:.1f}s",
        )
    except ConnectionRefusedError as exc:
        return PortCheckResult(
            host=host, port=port, label=label, status=PORT_STATUS_CLOSED, error_message=str(exc)
        )
    except OSError as exc:
        return PortCheckResult(
            host=host, port=port, label=label, status=PORT_STATUS_ERROR, error_message=str(exc)
        )
    finally:
        sock.close()


def check_common_ports(
    host: str, ports: Optional[dict] = None, timeout: float = 2.0
) -> list[PortCheckResult]:
    """Run :func:`check_tcp_port` for every port in ``ports`` (default: DEFAULT_PORTS)."""
    ports = ports or DEFAULT_PORTS
    return [check_tcp_port(host, port, timeout=timeout, label=label) for port, label in ports.items()]


@dataclass
class LatencyResult:
    host: str
    reachable: bool
    packets_sent: int = 0
    packets_received: int = 0
    min_ms: Optional[float] = None
    avg_ms: Optional[float] = None
    max_ms: Optional[float] = None
    error_message: str = ""

    def as_dict(self) -> dict:
        return {
            "host": self.host,
            "reachable": self.reachable,
            "packets_sent": self.packets_sent,
            "packets_received": self.packets_received,
            "min_ms": self.min_ms,
            "avg_ms": self.avg_ms,
            "max_ms": self.max_ms,
            "error_message": self.error_message,
        }


def _build_ping_command(host: str, count: int, timeout: float) -> list:
    system = platform.system().lower()
    if system == "windows":
        # -n <count>, -w <per-packet timeout in ms>
        return ["ping", "-n", str(count), "-w", str(int(timeout * 1000)), host]
    # Linux / macOS: -c <count>, -W <per-packet timeout in seconds (Linux) or ms (macOS uses -W ms too on newer versions)>
    return ["ping", "-c", str(count), "-W", str(max(1, int(timeout))), host]


_WINDOWS_RTT_RE = re.compile(
    r"Minimum = (?P<min>\d+)ms, Maximum = (?P<max>\d+)ms, Average = (?P<avg>\d+)ms"
)
_UNIX_RTT_RE = re.compile(
    r"= (?P<min>[\d.]+)/(?P<avg>[\d.]+)/(?P<max>[\d.]+)/[\d.]+ ms"
)
_WINDOWS_COUNTS_RE = re.compile(
    r"Sent = (?P<sent>\d+), Received = (?P<received>\d+)"
)
_UNIX_COUNTS_RE = re.compile(
    r"(?P<sent>\d+) packets transmitted, (?P<received>\d+)( packets)? received"
)


def parse_ping_output(output: str, is_windows: bool) -> dict:
    """Pure parsing helper for ``ping`` command output (unit-testable).

    Returns a dict with ``packets_sent``, ``packets_received``, ``min_ms``,
    ``avg_ms``, ``max_ms``. Missing values are ``None``/``0`` if the output
    doesn't match the expected pattern (e.g. host unreachable).
    """
    result = {
        "packets_sent": 0,
        "packets_received": 0,
        "min_ms": None,
        "avg_ms": None,
        "max_ms": None,
    }

    counts_re = _WINDOWS_COUNTS_RE if is_windows else _UNIX_COUNTS_RE
    counts_match = counts_re.search(output)
    if counts_match:
        result["packets_sent"] = int(counts_match.group("sent"))
        result["packets_received"] = int(counts_match.group("received"))

    rtt_re = _WINDOWS_RTT_RE if is_windows else _UNIX_RTT_RE
    rtt_match = rtt_re.search(output)
    if rtt_match:
        result["min_ms"] = float(rtt_match.group("min"))
        result["avg_ms"] = float(rtt_match.group("avg"))
        result["max_ms"] = float(rtt_match.group("max"))

    return result


def check_latency(host: str, count: int = 4, timeout: float = 2.0) -> LatencyResult:
    """Run the platform ``ping`` utility against ``host`` and parse the result.

    Handles the Windows vs. Linux/macOS flag differences (``-n``/``-w`` vs.
    ``-c``/``-W``) and gracefully reports ``reachable=False`` with an
    explanatory message if ``ping`` is not installed, is blocked by a
    firewall/IDS, or the subprocess otherwise fails -- this is common on
    locked-down customer networks and must never crash the survey.
    """
    is_windows = platform.system().lower() == "windows"
    cmd = _build_ping_command(host, count, timeout)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout * count + 5,
        )
    except FileNotFoundError:
        return LatencyResult(host=host, reachable=False, error_message="ping utility not found on this system")
    except subprocess.TimeoutExpired:
        return LatencyResult(host=host, reachable=False, error_message="ping subprocess timed out")
    except OSError as exc:
        return LatencyResult(host=host, reachable=False, error_message=f"could not run ping: {exc}")

    output = (proc.stdout or "") + (proc.stderr or "")
    parsed = parse_ping_output(output, is_windows)

    reachable = parsed["packets_received"] > 0 and parsed["avg_ms"] is not None

    return LatencyResult(
        host=host,
        reachable=reachable,
        packets_sent=parsed["packets_sent"],
        packets_received=parsed["packets_received"],
        min_ms=parsed["min_ms"],
        avg_ms=parsed["avg_ms"],
        max_ms=parsed["max_ms"],
        error_message="" if reachable else "host did not respond to ping (may be blocked by firewall/IDS)",
    )


def estimate_bandwidth_headroom(
    num_cameras: int,
    avg_bitrate_mbps: float,
    uplink_capacity_mbps: float,
    safety_margin: float = 0.8,
) -> dict:
    """Rough, documented placeholder for a bandwidth sizing estimate.

    This is NOT a measured throughput test -- it does not send any traffic.
    A real bandwidth measurement needs a tool like iperf3 running an
    endpoint on both sides of the link, which is out of scope for a
    single-laptop discovery toolkit (and often not allowed on a customer
    network anyway). Instead, this gives a same-ballpark planning number
    from a simple formula:

        required_mbps = num_cameras * avg_bitrate_mbps
        usable_capacity_mbps = uplink_capacity_mbps * safety_margin
        headroom_mbps = usable_capacity_mbps - required_mbps

    ``safety_margin`` (default 0.8, i.e. only plan to use 80% of the stated
    link capacity) exists because real links rarely sustain their rated
    capacity once other traffic, protocol overhead, and retransmits are
    accounted for.

    Returns a dict with ``required_mbps``, ``usable_capacity_mbps``,
    ``headroom_mbps``, and ``sufficient`` (bool).
    """
    required_mbps = num_cameras * avg_bitrate_mbps
    usable_capacity_mbps = uplink_capacity_mbps * safety_margin
    headroom_mbps = usable_capacity_mbps - required_mbps

    return {
        "num_cameras": num_cameras,
        "avg_bitrate_mbps": avg_bitrate_mbps,
        "uplink_capacity_mbps": uplink_capacity_mbps,
        "safety_margin": safety_margin,
        "required_mbps": round(required_mbps, 2),
        "usable_capacity_mbps": round(usable_capacity_mbps, 2),
        "headroom_mbps": round(headroom_mbps, 2),
        "sufficient": headroom_mbps >= 0,
    }
