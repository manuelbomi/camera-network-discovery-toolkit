"""Tests for manual inventory loading/validation -- the primary code path."""

from pathlib import Path

import pytest
import yaml

from camtoolkit.manual_inventory import (
    CameraEntry,
    InventoryValidationError,
    load_inventory,
    load_inventory_result,
    parse_inventory,
)

EXAMPLE_YAML_PATH = Path(__file__).resolve().parents[1] / "examples" / "cameras.yaml"


def test_example_yaml_file_exists():
    assert EXAMPLE_YAML_PATH.exists()


def test_load_inventory_from_example_file():
    entries = load_inventory(EXAMPLE_YAML_PATH)
    assert len(entries) == 4
    assert all(isinstance(e, CameraEntry) for e in entries)
    names = {e.name for e in entries}
    assert "lobby-entrance-cam" in names


def test_example_entries_have_required_fields_populated():
    entries = load_inventory(EXAMPLE_YAML_PATH)
    for entry in entries:
        assert entry.name
        assert entry.ip
        assert entry.rtsp_url.startswith("rtsp://")
        assert isinstance(entry.onvif_port, int)


def test_example_entries_use_placeholder_credentials_only():
    entries = load_inventory(EXAMPLE_YAML_PATH)
    for entry in entries:
        assert entry.password == "REPLACE_ME"


def test_load_inventory_result_wraps_source_path():
    result = load_inventory_result(EXAMPLE_YAML_PATH)
    assert result.source_path == str(EXAMPLE_YAML_PATH)
    assert len(result.entries) == 4
    dicts = result.as_dicts(redacted=True)
    assert dicts[0]["password"] == "********"


def test_load_inventory_missing_file_raises(tmp_path):
    missing = tmp_path / "does-not-exist.yaml"
    with pytest.raises(FileNotFoundError):
        load_inventory(missing)


def test_parse_inventory_accepts_bare_list():
    raw = [{"name": "cam1", "ip": "10.0.0.5"}]
    entries = parse_inventory(raw)
    assert len(entries) == 1
    assert entries[0].onvif_port == 80  # default


def test_parse_inventory_rejects_missing_required_field():
    raw = {"cameras": [{"name": "cam1"}]}  # no ip
    with pytest.raises(InventoryValidationError):
        parse_inventory(raw)


def test_parse_inventory_rejects_empty_camera_list():
    with pytest.raises(InventoryValidationError):
        parse_inventory({"cameras": []})


def test_parse_inventory_rejects_missing_cameras_key():
    with pytest.raises(InventoryValidationError):
        parse_inventory({"not_cameras": []})


def test_parse_inventory_rejects_non_integer_onvif_port():
    raw = {"cameras": [{"name": "cam1", "ip": "10.0.0.5", "onvif_port": "not-a-number"}]}
    with pytest.raises(InventoryValidationError):
        parse_inventory(raw)


def test_parse_inventory_rejects_duplicate_ips():
    raw = {
        "cameras": [
            {"name": "cam1", "ip": "10.0.0.5"},
            {"name": "cam2", "ip": "10.0.0.5"},
        ]
    }
    with pytest.raises(InventoryValidationError):
        parse_inventory(raw)


def test_load_inventory_empty_file_raises(tmp_path):
    empty_file = tmp_path / "empty.yaml"
    empty_file.write_text("", encoding="utf-8")
    with pytest.raises(InventoryValidationError):
        load_inventory(empty_file)


def test_camera_entry_redacted_dict_masks_password():
    entry = CameraEntry(name="cam1", ip="10.0.0.5", password="supersecret")
    redacted = entry.redacted_dict()
    assert redacted["password"] == "********"
    assert entry.as_dict()["password"] == "supersecret"


def test_load_inventory_roundtrips_through_yaml(tmp_path):
    data = {
        "cameras": [
            {"name": "cam-a", "ip": "10.0.0.5", "rtsp_url": "rtsp://10.0.0.5/stream1"},
        ]
    }
    path = tmp_path / "custom.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    entries = load_inventory(path)
    assert entries[0].name == "cam-a"
    assert entries[0].rtsp_url == "rtsp://10.0.0.5/stream1"
