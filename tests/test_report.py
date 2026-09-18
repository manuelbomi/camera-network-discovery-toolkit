"""Tests for report aggregation and CSV/JSON/HTML export."""

import csv
import json

from camtoolkit.report import (
    build_report,
    build_row_from_camera,
    export_csv,
    export_html,
    export_json,
)


def _sample_report():
    camera_a = {"name": "lobby-cam", "ip": "192.0.2.10", "rtsp_url": "rtsp://192.0.2.10/stream1"}
    camera_b = {"name": "dock-cam", "ip": "192.0.2.11", "rtsp_url": "rtsp://192.0.2.11/stream1"}

    rtsp_ok = {
        "status": "success",
        "time_to_first_frame_sec": 0.42,
        "achieved_fps": 14.8,
        "resolution": "1920x1080",
        "error_message": "",
    }
    rtsp_bad = {
        "status": "timeout",
        "time_to_first_frame_sec": None,
        "achieved_fps": None,
        "resolution": "",
        "error_message": "No response within 8.0s",
    }
    ports = [
        {"host": "192.0.2.10", "port": 554, "label": "RTSP", "status": "open", "error_message": ""},
        {"host": "192.0.2.10", "port": 80, "label": "HTTP", "status": "closed", "error_message": ""},
    ]
    latency = {"avg_ms": 3.5, "reachable": True}

    row_a = build_row_from_camera(camera_a, rtsp_result=rtsp_ok, port_results=ports, latency_result=latency, source="manual")
    row_b = build_row_from_camera(camera_b, rtsp_result=rtsp_bad, source="discovery")

    return build_report([row_a, row_b], survey_name="Unit Test Survey")


def test_build_report_metadata():
    report = _sample_report()
    assert report.survey_name == "Unit Test Survey"
    assert len(report.rows) == 2
    assert report.generated_at  # ISO timestamp populated


def test_row_port_summary_formats_label_and_status():
    report = _sample_report()
    row_a = report.rows[0]
    assert "RTSP:open" in row_a.port_summary
    assert "HTTP:closed" in row_a.port_summary


def test_export_json_contains_key_fields(tmp_path):
    report = _sample_report()
    path = export_json(report, tmp_path / "report.json")
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["survey_name"] == "Unit Test Survey"
    assert data["camera_count"] == 2
    names = {cam["name"] for cam in data["cameras"]}
    assert names == {"lobby-cam", "dock-cam"}

    lobby = next(cam for cam in data["cameras"] if cam["name"] == "lobby-cam")
    assert lobby["ip"] == "192.0.2.10"
    assert lobby["rtsp_status"] == "success"
    assert lobby["rtsp_fps"] == 14.8


def test_export_csv_contains_key_fields(tmp_path):
    report = _sample_report()
    path = export_csv(report, tmp_path / "report.csv")

    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    assert len(rows) == 2
    lobby_row = next(r for r in rows if r["name"] == "lobby-cam")
    assert lobby_row["ip"] == "192.0.2.10"
    assert lobby_row["rtsp_status"] == "success"
    assert lobby_row["source"] == "manual"

    dock_row = next(r for r in rows if r["name"] == "dock-cam")
    assert dock_row["rtsp_status"] == "timeout"
    assert dock_row["source"] == "discovery"


def test_export_html_renders_camera_names_and_status(tmp_path):
    report = _sample_report()
    path = export_html(report, tmp_path / "report.html")
    html = path.read_text(encoding="utf-8")

    assert "Unit Test Survey" in html
    assert "lobby-cam" in html
    assert "dock-cam" in html
    assert "192.0.2.10" in html
    # no plaintext credentials should ever land in a report
    assert "password" not in html.lower() or "REPLACE_ME" not in html


def test_export_html_uses_custom_template_dir(tmp_path):
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "minimal.html.j2").write_text(
        "<html><body>{{ report.survey_name }} - {{ report.camera_count }}</body></html>",
        encoding="utf-8",
    )
    report = _sample_report()
    path = export_html(
        report, tmp_path / "out.html", template_dir=template_dir, template_name="minimal.html.j2"
    )
    html = path.read_text(encoding="utf-8")
    assert "Unit Test Survey - 2" in html
