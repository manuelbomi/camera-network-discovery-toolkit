"""Tests for TCP port checks, ping-output parsing, and the bandwidth formula.

The port-check tests spin up a real (but local, loopback-only) TCP server
with the standard library's ``socketserver`` -- no external network access
and no real cameras required.
"""

import socket
import socketserver
import threading

import pytest

from camtoolkit.network_readiness import (
    PORT_STATUS_CLOSED,
    PORT_STATUS_OPEN,
    check_common_ports,
    check_tcp_port,
    estimate_bandwidth_headroom,
    parse_ping_output,
)


class _EchoHandler(socketserver.BaseRequestHandler):
    def handle(self):
        # Accept the connection and immediately close -- we only care
        # about connect() succeeding, not any actual protocol exchange.
        pass


@pytest.fixture
def loopback_server():
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _EchoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def closed_port():
    """Bind a socket, note the free port, then close it so nothing listens there."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def test_check_tcp_port_open_against_loopback_server(loopback_server):
    host, port = loopback_server
    result = check_tcp_port(host, port, timeout=2.0, label="test")
    assert result.status == PORT_STATUS_OPEN
    assert result.connect_time_sec is not None
    assert result.port == port
    assert result.label == "test"


def test_check_tcp_port_closed_when_nothing_listens(closed_port):
    result = check_tcp_port("127.0.0.1", closed_port, timeout=1.0)
    # Most platforms answer immediately with a TCP RST (status "closed"),
    # but some Windows configurations silently drop the SYN to a
    # just-released loopback port instead of resetting it, which surfaces
    # here as a timeout. Both are a correct "nothing is listening" signal.
    assert result.status in (PORT_STATUS_CLOSED, "timeout")


def test_check_tcp_port_uses_default_label_for_known_ports():
    result = check_tcp_port("127.0.0.1", 554, timeout=0.2)
    assert result.label == "RTSP"


def test_check_common_ports_returns_one_result_per_port(loopback_server):
    host, port = loopback_server
    ports = {port: "loopback-echo", 1: "reserved-unlikely-open"}
    results = check_common_ports(host, ports=ports, timeout=1.0)
    assert len(results) == 2
    statuses = {r.port: r.status for r in results}
    assert statuses[port] == PORT_STATUS_OPEN


def test_check_tcp_port_never_raises_on_bad_host():
    # A hostname that should not resolve; the function must return an
    # error result rather than propagate the exception.
    result = check_tcp_port("this-host-does-not-exist.invalid", 554, timeout=1.0)
    assert result.status in ("error", "timeout")


# --- ping output parsing (pure function, no subprocess involved) ---


WINDOWS_PING_SAMPLE = """
Pinging 192.168.1.50 with 32 bytes of data:
Reply from 192.168.1.50: bytes=32 time=4ms TTL=64
Reply from 192.168.1.50: bytes=32 time=3ms TTL=64
Reply from 192.168.1.50: bytes=32 time=5ms TTL=64
Reply from 192.168.1.50: bytes=32 time=4ms TTL=64

Ping statistics for 192.168.1.50:
    Packets: Sent = 4, Received = 4, Lost = 0 (0% loss),
Approximate round trip times in milli-seconds:
    Minimum = 3ms, Maximum = 5ms, Average = 4ms
"""

LINUX_PING_SAMPLE = """
PING 192.168.1.50 (192.168.1.50) 56(84) bytes of data.
64 bytes from 192.168.1.50: icmp_seq=1 ttl=64 time=3.21 ms
64 bytes from 192.168.1.50: icmp_seq=2 ttl=64 time=4.05 ms

--- 192.168.1.50 ping statistics ---
2 packets transmitted, 2 received, 0% packet loss, time 1001ms
rtt min/avg/max/mdev = 3.210/3.630/4.050/0.420 ms
"""

UNREACHABLE_LINUX_PING_SAMPLE = """
PING 192.168.1.99 (192.168.1.99) 56(84) bytes of data.

--- 192.168.1.99 ping statistics ---
4 packets transmitted, 0 received, 100% packet loss, time 3057ms
"""


def test_parse_ping_output_windows_success():
    parsed = parse_ping_output(WINDOWS_PING_SAMPLE, is_windows=True)
    assert parsed["packets_sent"] == 4
    assert parsed["packets_received"] == 4
    assert parsed["avg_ms"] == 4.0
    assert parsed["min_ms"] == 3.0
    assert parsed["max_ms"] == 5.0


def test_parse_ping_output_linux_success():
    parsed = parse_ping_output(LINUX_PING_SAMPLE, is_windows=False)
    assert parsed["packets_sent"] == 2
    assert parsed["packets_received"] == 2
    assert parsed["avg_ms"] == pytest.approx(3.63)


def test_parse_ping_output_linux_unreachable():
    parsed = parse_ping_output(UNREACHABLE_LINUX_PING_SAMPLE, is_windows=False)
    assert parsed["packets_sent"] == 4
    assert parsed["packets_received"] == 0
    assert parsed["avg_ms"] is None


# --- bandwidth placeholder formula ---


def test_estimate_bandwidth_headroom_sufficient():
    result = estimate_bandwidth_headroom(
        num_cameras=10, avg_bitrate_mbps=4.0, uplink_capacity_mbps=100.0, safety_margin=0.8
    )
    # usable = 80, required = 40, headroom = 40
    assert result["required_mbps"] == 40.0
    assert result["usable_capacity_mbps"] == 80.0
    assert result["headroom_mbps"] == 40.0
    assert result["sufficient"] is True


def test_estimate_bandwidth_headroom_insufficient():
    result = estimate_bandwidth_headroom(
        num_cameras=50, avg_bitrate_mbps=4.0, uplink_capacity_mbps=100.0, safety_margin=0.8
    )
    # usable = 80, required = 200 -> negative headroom
    assert result["required_mbps"] == 200.0
    assert result["headroom_mbps"] == -120.0
    assert result["sufficient"] is False
