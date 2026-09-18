"""Manual camera inventory: the primary, fully-supported discovery path.

Many customer networks either block UDP multicast between VLANs, disable
it on camera switch ports for security reasons, or simply do not allow an
unfamiliar laptop to run any kind of active scan. In all of those cases
(which, in practice, are common) ONVIF WS-Discovery in :mod:`camtoolkit.discovery`
will not find anything, even though the cameras are alive and reachable.

The manual inventory mode covers that gap: the customer (or the engineer,
from a walkthrough) supplies a plain YAML file listing every camera they
know about, and this module loads, validates, and normalizes it into the
same shape the rest of the toolkit expects from automatic discovery.

Because this path needs no network and no hardware, it is the most
thoroughly unit-tested part of the toolkit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REQUIRED_FIELDS = ("name", "ip")


class InventoryValidationError(ValueError):
    """Raised when a camera entry (or the file as a whole) is invalid."""


@dataclass
class CameraEntry:
    """A single camera as described in the manual inventory YAML file."""

    name: str
    ip: str
    rtsp_url: str = ""
    username: str = ""
    password: str = ""
    onvif_port: int = 80
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ip": self.ip,
            "rtsp_url": self.rtsp_url,
            "username": self.username,
            "password": self.password,
            "onvif_port": self.onvif_port,
            "notes": self.notes,
        }

    def redacted_dict(self) -> dict[str, Any]:
        """Same as :meth:`as_dict` but with the password masked.

        Use this whenever camera data might end up in a report, log file,
        or anything else that could be shared with someone who should not
        see plaintext credentials.
        """
        data = self.as_dict()
        data["password"] = "********" if data["password"] else ""
        return data


def _validate_raw_entry(raw: dict, index: int) -> None:
    if not isinstance(raw, dict):
        raise InventoryValidationError(f"Camera entry #{index} is not a mapping: {raw!r}")
    missing = [f for f in REQUIRED_FIELDS if not raw.get(f)]
    if missing:
        raise InventoryValidationError(
            f"Camera entry #{index} ({raw.get('name', '<unnamed>')}) is missing "
            f"required field(s): {', '.join(missing)}"
        )


def _coerce_entry(raw: dict) -> CameraEntry:
    onvif_port = raw.get("onvif_port", 80)
    try:
        onvif_port = int(onvif_port)
    except (TypeError, ValueError) as exc:
        raise InventoryValidationError(
            f"Camera entry {raw.get('name')!r} has a non-integer onvif_port: {onvif_port!r}"
        ) from exc

    return CameraEntry(
        name=str(raw["name"]),
        ip=str(raw["ip"]),
        rtsp_url=str(raw.get("rtsp_url", "")),
        username=str(raw.get("username", "")),
        password=str(raw.get("password", "")),
        onvif_port=onvif_port,
        notes=str(raw.get("notes", "")),
    )


def parse_inventory(raw_data: Any) -> list[CameraEntry]:
    """Validate and convert already-parsed YAML data into ``CameraEntry`` objects.

    ``raw_data`` is expected to be a dict with a top-level ``cameras`` key
    holding a list of camera mappings (see ``examples/cameras.yaml``), or a
    bare list of camera mappings.

    Raises :class:`InventoryValidationError` on any structural problem, so
    a bad file fails loudly and early rather than surfacing as a confusing
    error deep inside the report generator.
    """
    if isinstance(raw_data, dict):
        cameras_raw = raw_data.get("cameras")
        if cameras_raw is None:
            raise InventoryValidationError(
                "Inventory file must have a top-level 'cameras' list."
            )
    elif isinstance(raw_data, list):
        cameras_raw = raw_data
    else:
        raise InventoryValidationError(
            "Inventory file must contain a mapping with a 'cameras' list, or a bare list."
        )

    if not isinstance(cameras_raw, list):
        raise InventoryValidationError("'cameras' must be a list of camera entries.")

    if len(cameras_raw) == 0:
        raise InventoryValidationError("Inventory file contains zero cameras.")

    entries: list[CameraEntry] = []
    seen_ips: set[str] = set()
    for index, raw in enumerate(cameras_raw, start=1):
        _validate_raw_entry(raw, index)
        entry = _coerce_entry(raw)
        if entry.ip in seen_ips:
            raise InventoryValidationError(f"Duplicate IP address in inventory: {entry.ip}")
        seen_ips.add(entry.ip)
        entries.append(entry)

    return entries


def load_inventory(path: str | Path) -> list[CameraEntry]:
    """Load and validate a manual camera inventory YAML file from disk."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Inventory file not found: {path}")

    with path.open("r", encoding="utf-8") as fh:
        raw_data = yaml.safe_load(fh)

    if raw_data is None:
        raise InventoryValidationError(f"Inventory file is empty: {path}")

    return parse_inventory(raw_data)


@dataclass
class InventoryLoadResult:
    """Convenience wrapper bundling entries with the source file path."""

    source_path: str
    entries: list[CameraEntry] = field(default_factory=list)

    def as_dicts(self, redacted: bool = True) -> list[dict[str, Any]]:
        if redacted:
            return [entry.redacted_dict() for entry in self.entries]
        return [entry.as_dict() for entry in self.entries]


def load_inventory_result(path: str | Path) -> InventoryLoadResult:
    """Same as :func:`load_inventory`, wrapped with the source path for reporting."""
    entries = load_inventory(path)
    return InventoryLoadResult(source_path=str(path), entries=entries)
