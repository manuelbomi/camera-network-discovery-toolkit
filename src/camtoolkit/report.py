"""Aggregate discovery / inventory / health / readiness data into one report.

The other modules each answer a narrow question (what cameras exist, is
the RTSP stream healthy, are the right ports open). This module stitches
their outputs into a single "camera inventory report" -- one row per
camera, with every column a stakeholder would want when deciding how to
size the eventual recording/analytics architecture -- and exports that
report as CSV, JSON, or a self-contained HTML page suitable for handing to
a customer or an internal team.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

# CSV column order. Keeping this explicit (rather than "whatever keys the
# first row happens to have") means the exported CSV has a stable,
# predictable schema even if some rows are missing optional data.
CSV_FIELDS = [
    "name",
    "ip",
    "source",
    "rtsp_url",
    "onvif_port",
    "rtsp_status",
    "rtsp_latency_sec",
    "rtsp_fps",
    "rtsp_resolution",
    "rtsp_error",
    "port_summary",
    "latency_avg_ms",
    "latency_reachable",
    "notes",
]


@dataclass
class CameraReportRow:
    """One camera's worth of combined survey data."""

    name: str
    ip: str
    source: str = "manual"  # "manual" or "discovery"
    rtsp_url: str = ""
    onvif_port: Optional[int] = None
    rtsp_status: str = ""
    rtsp_latency_sec: Optional[float] = None
    rtsp_fps: Optional[float] = None
    rtsp_resolution: str = ""
    rtsp_error: str = ""
    port_checks: list[dict] = field(default_factory=list)
    latency_avg_ms: Optional[float] = None
    latency_reachable: Optional[bool] = None
    notes: str = ""

    @property
    def port_summary(self) -> str:
        if not self.port_checks:
            return ""
        parts = []
        for check in self.port_checks:
            parts.append(f"{check.get('label') or check.get('port')}:{check.get('status')}")
        return ", ".join(parts)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ip": self.ip,
            "source": self.source,
            "rtsp_url": self.rtsp_url,
            "onvif_port": self.onvif_port,
            "rtsp_status": self.rtsp_status,
            "rtsp_latency_sec": self.rtsp_latency_sec,
            "rtsp_fps": self.rtsp_fps,
            "rtsp_resolution": self.rtsp_resolution,
            "rtsp_error": self.rtsp_error,
            "port_checks": self.port_checks,
            "port_summary": self.port_summary,
            "latency_avg_ms": self.latency_avg_ms,
            "latency_reachable": self.latency_reachable,
            "notes": self.notes,
        }


def build_row_from_camera(
    camera: dict,
    rtsp_result: Optional[dict] = None,
    port_results: Optional[list[dict]] = None,
    latency_result: Optional[dict] = None,
    source: str = "manual",
) -> CameraReportRow:
    """Combine one camera's inventory entry with its health/readiness results.

    ``camera`` is a plain dict as produced by ``CameraEntry.as_dict()`` /
    ``redacted_dict()`` (manual inventory) or a WS-Discovery match dict
    (from ``discovery.parse_probe_matches``, normalized to have at least
    ``name``/``ip``). ``rtsp_result``, ``port_results`` and
    ``latency_result`` are the ``as_dict()`` outputs of the corresponding
    health/readiness checks, or ``None`` if that check was not run.
    """
    row = CameraReportRow(
        name=camera.get("name", ""),
        ip=camera.get("ip", ""),
        source=source,
        rtsp_url=camera.get("rtsp_url", ""),
        onvif_port=camera.get("onvif_port"),
        notes=camera.get("notes", ""),
    )

    if rtsp_result:
        row.rtsp_status = rtsp_result.get("status", "")
        row.rtsp_latency_sec = rtsp_result.get("time_to_first_frame_sec")
        row.rtsp_fps = rtsp_result.get("achieved_fps")
        row.rtsp_resolution = rtsp_result.get("resolution", "")
        row.rtsp_error = rtsp_result.get("error_message", "")

    if port_results:
        row.port_checks = list(port_results)

    if latency_result:
        row.latency_avg_ms = latency_result.get("avg_ms")
        row.latency_reachable = latency_result.get("reachable")

    return row


@dataclass
class InventoryReport:
    """The full report: metadata plus every camera row."""

    rows: list[CameraReportRow] = field(default_factory=list)
    survey_name: str = "Camera Network Discovery Survey"
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    def as_dict(self) -> dict[str, Any]:
        return {
            "survey_name": self.survey_name,
            "generated_at": self.generated_at,
            "camera_count": len(self.rows),
            "cameras": [row.as_dict() for row in self.rows],
        }


def build_report(
    rows: list[CameraReportRow], survey_name: str = "Camera Network Discovery Survey"
) -> InventoryReport:
    """Build an :class:`InventoryReport` from a list of camera rows."""
    return InventoryReport(rows=rows, survey_name=survey_name)


def export_json(report: InventoryReport, path: str | Path) -> Path:
    """Write the report as pretty-printed JSON. Returns the path written."""
    path = Path(path)
    path.write_text(json.dumps(report.as_dict(), indent=2), encoding="utf-8")
    return path


def export_csv(report: InventoryReport, path: str | Path) -> Path:
    """Write the report as CSV with a stable column order. Returns the path written."""
    path = Path(path)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in report.rows:
            writer.writerow(row.as_dict())
    return path


def _default_template_dir() -> Path:
    """Locate the ``templates/`` directory that ships with this repo.

    Resolution order:
    1. ``CAMTOOLKIT_TEMPLATE_DIR`` environment variable, if set.
    2. ``<repo_root>/templates`` (this file lives at
       ``<repo_root>/src/camtoolkit/report.py``, so the repo root is two
       directories up).
    3. A ``templates`` directory bundled next to this file, for the case
       where the package is installed standalone without the rest of the
       repo checkout (e.g. from a wheel).
    """
    import os

    env_override = os.environ.get("CAMTOOLKIT_TEMPLATE_DIR")
    if env_override:
        return Path(env_override)

    repo_root_templates = Path(__file__).resolve().parents[2] / "templates"
    if repo_root_templates.exists():
        return repo_root_templates

    return Path(__file__).resolve().parent / "templates"


def export_html(
    report: InventoryReport,
    path: str | Path,
    template_dir: Optional[str | Path] = None,
    template_name: str = "report.html.j2",
) -> Path:
    """Render the report to a self-contained HTML file using Jinja2.

    Returns the path written. Raises ``jinja2.TemplateNotFound`` if the
    template can't be located -- see :func:`_default_template_dir` for the
    search order.
    """
    template_dir = Path(template_dir) if template_dir else _default_template_dir()
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html", "j2"]),
    )
    template = env.get_template(template_name)
    html = template.render(report=report.as_dict())

    path = Path(path)
    path.write_text(html, encoding="utf-8")
    return path
