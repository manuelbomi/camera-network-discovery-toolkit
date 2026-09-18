/**
 * TypeScript mirror of the JSON shape produced by
 * `src/camtoolkit/report.py` (`InventoryReport.as_dict()` /
 * `CameraReportRow.as_dict()`), plus the per-check dataclasses in
 * `network_readiness.py` and `rtsp_health.py` that feed into it.
 *
 * Field names and optionality intentionally match the Python source
 * exactly so the viewer never silently drops or mislabels data from a
 * real `camtoolkit survey --out report.json` run.
 */

/** One TCP port readiness check, from `network_readiness.PortCheckResult.as_dict()`. */
export interface PortCheckResult {
  host: string;
  port: number;
  label: string;
  /** "open" | "closed" | "timeout" | "error" */
  status: string;
  error_message: string;
  connect_time_sec: number | null;
}

/** One camera row, from `report.CameraReportRow.as_dict()`. */
export interface CameraReportRow {
  name: string;
  ip: string;
  /** "manual" | "discovery" */
  source: string;
  rtsp_url: string;
  onvif_port: number | null;
  /** "" | "success" | "timeout" | "error" */
  rtsp_status: string;
  rtsp_latency_sec: number | null;
  rtsp_fps: number | null;
  /** e.g. "1920x1080", or "" if unknown */
  rtsp_resolution: string;
  rtsp_error: string;
  port_checks: PortCheckResult[];
  /** Human-readable "LABEL:status, LABEL:status" summary, from a computed property. */
  port_summary: string;
  latency_avg_ms: number | null;
  latency_reachable: boolean | null;
  notes: string;
}

/** The full report, from `report.InventoryReport.as_dict()`. */
export interface InventoryReport {
  survey_name: string;
  /** ISO-8601 UTC timestamp, e.g. "2026-09-18T20:41:07+00:00" */
  generated_at: string;
  camera_count: number;
  cameras: CameraReportRow[];
}
