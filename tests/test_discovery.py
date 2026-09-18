"""Tests for the pure WS-Discovery XML parsing logic.

No network, no sockets, no real cameras -- just a canned SOAP response
string, matching how camera vendors' ONVIF stacks reply on the wire.
"""

from camtoolkit.discovery import build_probe_message, parse_probe_matches

SAMPLE_PROBE_MATCHES_XML = """<?xml version="1.0" encoding="UTF-8"?>
<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"
            xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing"
            xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
            xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
  <e:Header>
    <w:MessageID>uuid:11111111-1111-1111-1111-111111111111</w:MessageID>
    <w:RelatesTo>uuid:00000000-0000-0000-0000-000000000000</w:RelatesTo>
    <w:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>
    <w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/ProbeMatches</w:Action>
  </e:Header>
  <e:Body>
    <d:ProbeMatches>
      <d:ProbeMatch>
        <w:EndpointReference>
          <w:Address>urn:uuid:aaaaaaaa-0000-0000-0000-aaaaaaaaaaaa</w:Address>
        </w:EndpointReference>
        <d:Types>dn:NetworkVideoTransmitter</d:Types>
        <d:Scopes>onvif://www.onvif.org/type/video_encoder onvif://www.onvif.org/location/lobby</d:Scopes>
        <d:XAddrs>http://192.168.1.50/onvif/device_service</d:XAddrs>
        <d:MetadataVersion>1</d:MetadataVersion>
      </d:ProbeMatch>
      <d:ProbeMatch>
        <w:EndpointReference>
          <w:Address>urn:uuid:bbbbbbbb-0000-0000-0000-bbbbbbbbbbbb</w:Address>
        </w:EndpointReference>
        <d:Types>dn:NetworkVideoTransmitter</d:Types>
        <d:Scopes>onvif://www.onvif.org/location/dock</d:Scopes>
        <d:XAddrs>http://192.168.1.51/onvif/device_service http://[fe80::1]/onvif/device_service</d:XAddrs>
        <d:MetadataVersion>3</d:MetadataVersion>
      </d:ProbeMatch>
    </d:ProbeMatches>
  </e:Body>
</e:Envelope>
"""

EMPTY_PROBE_MATCHES_XML = """<?xml version="1.0" encoding="UTF-8"?>
<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"
            xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery">
  <e:Body>
    <d:ProbeMatches/>
  </e:Body>
</e:Envelope>
"""


def test_parse_probe_matches_extracts_two_devices():
    matches = parse_probe_matches(SAMPLE_PROBE_MATCHES_XML)
    assert len(matches) == 2


def test_parse_probe_matches_extracts_endpoint_reference():
    matches = parse_probe_matches(SAMPLE_PROBE_MATCHES_XML)
    assert matches[0]["endpoint_reference"] == "urn:uuid:aaaaaaaa-0000-0000-0000-aaaaaaaaaaaa"
    assert matches[1]["endpoint_reference"] == "urn:uuid:bbbbbbbb-0000-0000-0000-bbbbbbbbbbbb"


def test_parse_probe_matches_extracts_xaddrs():
    matches = parse_probe_matches(SAMPLE_PROBE_MATCHES_XML)
    assert matches[0]["xaddrs"] == ["http://192.168.1.50/onvif/device_service"]
    assert matches[1]["xaddrs"] == [
        "http://192.168.1.51/onvif/device_service",
        "http://[fe80::1]/onvif/device_service",
    ]


def test_parse_probe_matches_extracts_types_and_scopes():
    matches = parse_probe_matches(SAMPLE_PROBE_MATCHES_XML)
    assert matches[0]["types"] == ["dn:NetworkVideoTransmitter"]
    assert "onvif://www.onvif.org/location/lobby" in matches[0]["scopes"]


def test_parse_probe_matches_extracts_metadata_version():
    matches = parse_probe_matches(SAMPLE_PROBE_MATCHES_XML)
    assert matches[0]["metadata_version"] == "1"
    assert matches[1]["metadata_version"] == "3"


def test_parse_probe_matches_handles_bytes_input():
    matches = parse_probe_matches(SAMPLE_PROBE_MATCHES_XML.encode("utf-8"))
    assert len(matches) == 2


def test_parse_probe_matches_returns_empty_list_when_no_matches():
    matches = parse_probe_matches(EMPTY_PROBE_MATCHES_XML)
    assert matches == []


def test_build_probe_message_contains_probe_action_and_message_id():
    message = build_probe_message(message_id="fixed-id-1234")
    text = message.decode("utf-8")
    assert "fixed-id-1234" in text
    assert "Probe" in text
    assert "NetworkVideoTransmitter" in text


def test_build_probe_message_generates_unique_ids_by_default():
    first = build_probe_message()
    second = build_probe_message()
    assert first != second
