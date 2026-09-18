import type { InventoryReport } from "../types";

interface SummaryStripProps {
  report: InventoryReport;
}

/** Top-of-page strip: cameras found, cameras healthy, and ports failing counts. */
export function SummaryStrip({ report }: SummaryStripProps) {
  const camerasFound = report.camera_count;
  const camerasHealthy = report.cameras.filter((c) => c.rtsp_status === "success").length;

  let portsChecked = 0;
  let portsFailing = 0;
  for (const camera of report.cameras) {
    for (const check of camera.port_checks) {
      portsChecked += 1;
      if (check.status !== "open") {
        portsFailing += 1;
      }
    }
  }

  const stats = [
    { label: "Cameras found", value: camerasFound },
    { label: "Cameras healthy (RTSP OK)", value: `${camerasHealthy} / ${camerasFound}` },
    { label: "Ports failing", value: `${portsFailing} / ${portsChecked}` },
  ];

  return (
    <div className="summary-strip">
      {stats.map((stat) => (
        <div className="summary-tile" key={stat.label}>
          <div className="summary-value">{stat.value}</div>
          <div className="summary-label">{stat.label}</div>
        </div>
      ))}
    </div>
  );
}
