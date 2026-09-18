"""Command line entry point for camtoolkit.

Two main workflows, matching how a site survey actually happens:

    camtoolkit discover --subnet 192.168.1.0/24
        Send an ONVIF WS-Discovery probe on the local network and print
        whatever answers back. Requires UDP multicast to be reachable,
        which is not always the case on customer networks (see README).

    camtoolkit survey --inventory cameras.yaml --out report.html
        The main day-to-day command: load a manual camera list, check
        each camera's RTSP stream health and network readiness, and
        write a combined report (CSV, JSON, or HTML based on the file
        extension of --out).
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from camtoolkit import (
    discovery,
    manual_inventory,
    network_readiness,
    rtsp_health,
)
from camtoolkit import (
    report as report_mod,
)


@click.group()
@click.version_option(package_name="camera-network-discovery-toolkit")
def main():
    """camtoolkit - camera network discovery and site-survey toolkit."""


@main.command()
@click.option("--subnet", default=None, help="Optional CIDR to filter results, e.g. 192.168.1.0/24")
@click.option("--timeout", default=4.0, show_default=True, help="Seconds to wait for probe replies.")
@click.option("--out", "out_path", default=None, type=click.Path(), help="Optional file to write results to (.json/.csv/.html).")
def discover(subnet, timeout, out_path):
    """Send a WS-Discovery probe and list ONVIF devices that respond."""
    click.echo(f"Sending WS-Discovery probe (timeout={timeout}s"
               + (f", subnet filter={subnet}" if subnet else "") + ")...")
    try:
        matches = discovery.discover(timeout=timeout, subnet=subnet)
    except OSError as exc:
        click.echo(f"Discovery failed: {exc}", err=True)
        click.echo(
            "This usually means UDP multicast is blocked on this network. "
            "Consider using 'camtoolkit survey --inventory <file.yaml>' instead.",
            err=True,
        )
        sys.exit(1)

    if not matches:
        click.echo("No ONVIF devices responded. This can mean there are none on this "
                    "segment, or that multicast discovery is blocked -- try manual "
                    "inventory mode instead.")
        return

    for match in matches:
        xaddr = match["xaddrs"][0] if match.get("xaddrs") else "(no address)"
        click.echo(f"- {xaddr}  types={','.join(match.get('types', []))}")

    if out_path:
        rows = [
            report_mod.build_row_from_camera(
                {"name": m.get("xaddrs", ["unknown"])[0], "ip": m.get("source_ip", "")},
                source="discovery",
            )
            for m in matches
        ]
        _export(report_mod.build_report(rows, survey_name="WS-Discovery scan"), out_path)
        click.echo(f"Wrote {out_path}")


@main.command()
@click.option("--inventory", "inventory_path", required=True, type=click.Path(exists=True), help="Path to a manual camera inventory YAML file.")
@click.option("--out", "out_path", required=True, type=click.Path(), help="Report file to write (.csv, .json, or .html).")
@click.option("--rtsp-timeout", default=8.0, show_default=True, help="Per-camera RTSP probe timeout (seconds).")
@click.option("--port-timeout", default=2.0, show_default=True, help="Per-port TCP connect timeout (seconds).")
@click.option("--skip-rtsp", is_flag=True, default=False, help="Skip connecting to RTSP streams (inventory + network checks only).")
@click.option("--skip-ports", is_flag=True, default=False, help="Skip TCP port readiness checks.")
@click.option("--skip-ping", is_flag=True, default=False, help="Skip ICMP-style latency checks.")
@click.option("--survey-name", default="Camera Network Discovery Survey", show_default=True, help="Title used in the report.")
def survey(inventory_path, out_path, rtsp_timeout, port_timeout, skip_rtsp, skip_ports, skip_ping, survey_name):
    """Run RTSP health + network readiness checks against a manual camera list."""
    result = manual_inventory.load_inventory_result(inventory_path)
    click.echo(f"Loaded {len(result.entries)} camera(s) from {inventory_path}")

    rows = []
    for entry in result.entries:
        click.echo(f"Checking {entry.name} ({entry.ip})...")

        rtsp_result = None
        if not skip_rtsp and entry.rtsp_url:
            health = rtsp_health.check_rtsp_health(entry.rtsp_url, timeout=rtsp_timeout)
            rtsp_result = health.as_dict()
            click.echo(f"  RTSP: {health.status}")
        elif not entry.rtsp_url:
            click.echo("  RTSP: skipped (no rtsp_url configured)")

        port_results = None
        if not skip_ports:
            checks = network_readiness.check_common_ports(entry.ip, timeout=port_timeout)
            port_results = [c.as_dict() for c in checks]
            summary = ", ".join(f"{c.label}={c.status}" for c in checks)
            click.echo(f"  Ports: {summary}")

        latency_result = None
        if not skip_ping:
            latency = network_readiness.check_latency(entry.ip)
            latency_result = latency.as_dict()
            click.echo(f"  Latency: {'reachable' if latency.reachable else 'unreachable'}"
                       + (f" (avg {latency.avg_ms}ms)" if latency.avg_ms is not None else ""))

        rows.append(
            report_mod.build_row_from_camera(
                entry.redacted_dict(),
                rtsp_result=rtsp_result,
                port_results=port_results,
                latency_result=latency_result,
                source="manual",
            )
        )

    inventory_report = report_mod.build_report(rows, survey_name=survey_name)
    written = _export(inventory_report, out_path)
    click.echo(f"Wrote report to {written}")


def _export(inventory_report: "report_mod.InventoryReport", out_path) -> Path:
    out_path = Path(out_path)
    suffix = out_path.suffix.lower()
    if suffix == ".json":
        return report_mod.export_json(inventory_report, out_path)
    if suffix == ".csv":
        return report_mod.export_csv(inventory_report, out_path)
    if suffix in (".html", ".htm"):
        return report_mod.export_html(inventory_report, out_path)
    raise click.ClickException(f"Unsupported output extension: {suffix!r} (use .csv, .json, or .html)")


if __name__ == "__main__":
    main()
