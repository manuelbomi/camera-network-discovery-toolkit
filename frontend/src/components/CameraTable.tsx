import type { CameraReportRow } from "../types";
import { StatusBadge, rtspTone } from "./StatusBadge";

interface CameraTableProps {
  cameras: CameraReportRow[];
}

function formatLatency(seconds: number | null): string {
  if (seconds === null) return "-";
  return `${(seconds * 1000).toFixed(0)} ms`;
}

function formatFps(fps: number | null): string {
  if (fps === null) return "-";
  return fps.toFixed(1);
}

/** Camera inventory table: name/IP, RTSP status, resolution/FPS, latency. */
export function CameraTable({ cameras }: CameraTableProps) {
  return (
    <table className="report-table">
      <thead>
        <tr>
          <th>Camera</th>
          <th>IP address</th>
          <th>Source</th>
          <th>RTSP status</th>
          <th>Resolution</th>
          <th>FPS</th>
          <th>Time to first frame</th>
          <th>Notes</th>
        </tr>
      </thead>
      <tbody>
        {cameras.map((camera) => (
          <tr key={camera.ip || camera.name}>
            <td className="camera-name">{camera.name}</td>
            <td>
              <code>{camera.ip}</code>
            </td>
            <td>{camera.source}</td>
            <td>
              <StatusBadge
                label={camera.rtsp_status || "not checked"}
                tone={rtspTone(camera.rtsp_status)}
              />
              {camera.rtsp_error && (
                <div className="cell-subtext" title={camera.rtsp_error}>
                  {camera.rtsp_error}
                </div>
              )}
            </td>
            <td>{camera.rtsp_resolution || "-"}</td>
            <td>{formatFps(camera.rtsp_fps)}</td>
            <td>{formatLatency(camera.rtsp_latency_sec)}</td>
            <td className="cell-notes">{camera.notes || "-"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
