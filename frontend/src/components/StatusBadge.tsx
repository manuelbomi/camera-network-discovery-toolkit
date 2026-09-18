type BadgeTone = "good" | "bad" | "warn" | "neutral";

interface StatusBadgeProps {
  label: string;
  tone: BadgeTone;
}

/** Small color-coded pill used everywhere a check result needs a status. */
export function StatusBadge({ label, tone }: StatusBadgeProps) {
  return <span className={`badge badge-${tone}`}>{label}</span>;
}

/** Maps an RTSP health status ("success" | "timeout" | "error" | "") to a badge tone. */
export function rtspTone(status: string): BadgeTone {
  switch (status) {
    case "success":
      return "good";
    case "timeout":
      return "warn";
    case "error":
      return "bad";
    default:
      return "neutral";
  }
}

/** Maps a TCP port check status ("open" | "closed" | "timeout" | "error") to a badge tone. */
export function portTone(status: string): BadgeTone {
  switch (status) {
    case "open":
      return "good";
    case "timeout":
      return "warn";
    case "closed":
    case "error":
      return "bad";
    default:
      return "neutral";
  }
}

/** Maps a nullable ping-reachability flag to a badge tone. */
export function latencyTone(reachable: boolean | null): BadgeTone {
  if (reachable === true) return "good";
  if (reachable === false) return "bad";
  return "neutral";
}
