"""ONVIF WS-Discovery over UDP multicast.

ONVIF cameras (and other ONVIF-compliant devices) announce themselves on the
local network using WS-Discovery: a client sends a small SOAP ``Probe``
message to the well-known multicast group ``239.255.255.250:3702``, and any
ONVIF device listening on that group replies directly (unicast) with a
``ProbeMatches`` SOAP message that contains, among other things, the URL of
its device management service (the "XAddr").

This module is split into two halves on purpose:

1. ``build_probe_message`` / ``parse_probe_matches`` are pure functions with
   no I/O at all. They can be exercised in unit tests with a canned XML
   string, no network or real camera required.
2. ``discover`` does the actual socket work: it opens a UDP socket, joins
   the multicast conversation, sends the probe, and collects replies until
   a timeout expires. It is deliberately thin -- it just wires the pure
   functions above to a raw socket.

Only the pure parsing/formatting functions are covered by the automated
test suite; ``discover`` needs a real network and real (or simulated)
ONVIF devices to do anything interesting.
"""

from __future__ import annotations

import socket
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

WS_DISCOVERY_MULTICAST_ADDR = "239.255.255.250"
WS_DISCOVERY_MULTICAST_PORT = 3702

# WS-Discovery / ONVIF probe asking specifically for network video
# transmitters (i.e. cameras / encoders), not the full universe of ONVIF
# device classes. A generic probe (no <d:Types>) would also work but tends
# to bring back printers, NVRs, and other unrelated ONVIF-speaking gear.
_PROBE_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"
            xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing"
            xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
            xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
  <e:Header>
    <w:MessageID>uuid:{message_id}</w:MessageID>
    <w:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>
    <w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>
  </e:Header>
  <e:Body>
    <d:Probe>
      <d:Types>dn:NetworkVideoTransmitter</d:Types>
    </d:Probe>
  </e:Body>
</e:Envelope>"""

# WS-Discovery / WS-Addressing namespaces used when walking the parsed XML
# tree. We match on local tag name (see ``_localname``) rather than fully
# qualified names so that a device using a different namespace *prefix*
# (but the same URI) still parses correctly.
_NS = {
    "e": "http://www.w3.org/2003/05/soap-envelope",
    "w": "http://schemas.xmlsoap.org/ws/2004/08/addressing",
    "d": "http://schemas.xmlsoap.org/ws/2005/04/discovery",
}


@dataclass
class ProbeMatch:
    """A single device that answered a WS-Discovery probe."""

    endpoint_reference: str = ""
    types: list[str] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)
    xaddrs: list[str] = field(default_factory=list)
    metadata_version: str = ""

    @property
    def primary_xaddr(self) -> str:
        """The first advertised service address, or '' if none."""
        return self.xaddrs[0] if self.xaddrs else ""

    def as_dict(self) -> dict:
        return {
            "endpoint_reference": self.endpoint_reference,
            "types": self.types,
            "scopes": self.scopes,
            "xaddrs": self.xaddrs,
            "metadata_version": self.metadata_version,
        }


def build_probe_message(message_id: str | None = None) -> bytes:
    """Build the WS-Discovery Probe SOAP message as UTF-8 encoded bytes.

    ``message_id`` can be injected for deterministic tests; a random UUID4
    is generated when it is not supplied (the normal runtime path).
    """
    message_id = message_id or str(uuid.uuid4())
    xml_str = _PROBE_TEMPLATE.format(message_id=message_id)
    return xml_str.encode("utf-8")


def _localname(tag: str) -> str:
    """Strip the ``{namespace}`` prefix ElementTree adds to tag names."""
    return tag.rsplit("}", 1)[-1]


def _find_all_by_localname(elem: ET.Element, name: str):
    for child in elem.iter():
        if _localname(child.tag) == name:
            yield child


def parse_probe_matches(xml_bytes: bytes | str) -> list[dict]:
    """Parse a WS-Discovery ``ProbeMatches`` SOAP message.

    Returns a list of dicts (one per ``ProbeMatch``) with keys:
    ``endpoint_reference``, ``types``, ``scopes``, ``xaddrs`` and
    ``metadata_version``. ``types``, ``scopes`` and ``xaddrs`` are lists of
    strings since WS-Discovery allows several space-separated values in
    each of those elements.

    This function does no I/O and never raises on malformed input that
    simply lacks matches -- it returns an empty list instead. It raises
    ``xml.etree.ElementTree.ParseError`` only if the input is not
    well-formed XML at all, which lets callers distinguish "no cameras
    responded" from "got garbage back".
    """
    if isinstance(xml_bytes, bytes):
        xml_text = xml_bytes.decode("utf-8", errors="replace")
    else:
        xml_text = xml_bytes

    root = ET.fromstring(xml_text)

    matches: list[dict] = []
    for probe_match in _find_all_by_localname(root, "ProbeMatch"):
        endpoint_ref = ""
        for addr in _find_all_by_localname(probe_match, "Address"):
            endpoint_ref = (addr.text or "").strip()
            break

        types_text = ""
        for types_el in _find_all_by_localname(probe_match, "Types"):
            types_text = types_el.text or ""
            break

        scopes_text = ""
        for scopes_el in _find_all_by_localname(probe_match, "Scopes"):
            scopes_text = scopes_el.text or ""
            break

        xaddrs_text = ""
        for xaddrs_el in _find_all_by_localname(probe_match, "XAddrs"):
            xaddrs_text = xaddrs_el.text or ""
            break

        metadata_version = ""
        for mv_el in _find_all_by_localname(probe_match, "MetadataVersion"):
            metadata_version = (mv_el.text or "").strip()
            break

        matches.append(
            {
                "endpoint_reference": endpoint_ref,
                "types": types_text.split(),
                "scopes": scopes_text.split(),
                "xaddrs": xaddrs_text.split(),
                "metadata_version": metadata_version,
            }
        )

    return matches


def discover(
    timeout: float = 4.0,
    subnet: str | None = None,
    interface_ip: str | None = None,
) -> list[dict]:
    """Send a WS-Discovery probe and collect ONVIF ``ProbeMatches`` replies.

    This performs real network I/O: it opens a UDP socket, sends one
    multicast Probe message to 239.255.255.250:3702, and listens for reply
    datagrams until ``timeout`` seconds elapse. Each distinct reply is
    parsed with :func:`parse_probe_matches`.

    Parameters
    ----------
    timeout:
        How long to keep listening for replies after sending the probe.
        Devices reply at a randomized delay (per the WS-Discovery spec) to
        avoid all devices on a large network answering at once, so a very
        short timeout will under-count cameras.
    subnet:
        Optional CIDR string (e.g. ``"192.168.1.0/24"``). When given, only
        matches whose XAddr host falls inside this subnet are returned.
        Multicast discovery does not actually need to know the subnet (the
        probe reaches every device in the multicast group regardless of
        subnet), but customer sites are frequently multi-segment, and
        filtering keeps the report focused on the segment being surveyed.
    interface_ip:
        Optional local interface address to bind the socket to, for hosts
        with multiple NICs.

    Returns
    -------
    A list of dicts as produced by :func:`parse_probe_matches`, deduplicated
    by endpoint reference.
    """
    import ipaddress

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # A TTL of 1 keeps the probe on the local segment, which matches how
    # WS-Discovery is used in practice (it is not meant to cross routers).
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
    sock.settimeout(timeout)

    bind_addr = (interface_ip or "0.0.0.0", 0)
    sock.bind(bind_addr)

    probe = build_probe_message()

    results: dict[str, dict] = {}
    try:
        sock.sendto(probe, (WS_DISCOVERY_MULTICAST_ADDR, WS_DISCOVERY_MULTICAST_PORT))

        import time

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            sock.settimeout(remaining)
            try:
                data, addr = sock.recvfrom(65535)
            except socket.timeout:
                break
            except OSError:
                break

            try:
                matches = parse_probe_matches(data)
            except ET.ParseError:
                continue

            for match in matches:
                match["source_ip"] = addr[0]
                key = match.get("endpoint_reference") or f"{addr[0]}:{len(results)}"
                results.setdefault(key, match)
    finally:
        sock.close()

    matches_list = list(results.values())

    if subnet:
        network = ipaddress.ip_network(subnet, strict=False)
        filtered = []
        for match in matches_list:
            host_ips = _extract_hosts(match.get("xaddrs", [])) or [match.get("source_ip", "")]
            if any(_ip_in_network(ip, network) for ip in host_ips if ip):
                filtered.append(match)
        matches_list = filtered

    return matches_list


def _extract_hosts(xaddrs: list[str]) -> list[str]:
    from urllib.parse import urlparse

    hosts = []
    for xaddr in xaddrs:
        try:
            hosts.append(urlparse(xaddr).hostname or "")
        except ValueError:
            continue
    return [h for h in hosts if h]


def _ip_in_network(ip: str, network) -> bool:
    import ipaddress

    try:
        return ipaddress.ip_address(ip) in network
    except ValueError:
        return False
