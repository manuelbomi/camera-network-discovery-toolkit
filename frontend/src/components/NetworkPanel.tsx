import type { CameraReportRow } from "../types";
import { StatusBadge, latencyTone, portTone } from "./StatusBadge";

interface NetworkPanelProps {
  cameras: CameraReportRow[];
}

function formatMs(ms: number | null): string {
  if (ms === null) return "-";
  return `${ms.toFixed(1)} ms`;
}

/** Network-readiness panel: per-camera port check results and ping latency. */
export function NetworkPanel({ cameras }: NetworkPanelProps) {
  return (
    <div className="network-panel">
      {cameras.map((camera) => (
        <div className="network-card" key={camera.ip || camera.name}>
          <div className="network-card-header">
            <span className="camera-name">{camera.name}</span>
            <code>{camera.ip}</code>
            <StatusBadge
              label={
                camera.latency_reachable === null
                  ? "ping not checked"
                  : camera.latency_reachable
                    ? `reachable (${formatMs(camera.latency_avg_ms)} avg)`
                    : "unreachable"
              }
              tone={latencyTone(camera.latency_reachable)}
            />
          </div>
          {camera.port_checks.length === 0 ? (
            <p className="cell-subtext">No port checks were run for this camera.</p>
          ) : (
            <div className="port-chip-row">
              {camera.port_checks.map((check) => (
                <div className="port-chip" key={`${check.host}:${check.port}`}>
                  <span className="port-chip-label">
                    {check.label || check.port} ({check.port})
                  </span>
                  <StatusBadge label={check.status} tone={portTone(check.status)} />
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
