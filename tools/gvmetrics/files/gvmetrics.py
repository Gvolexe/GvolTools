#!/usr/bin/env python3
"""
gvmetrics - Resource metrics collection and time series recording

Collect lightweight resource metrics snapshots and optionally record time series
suitable for export (CSV/JSON).

Aliases: metrics, mx

Author: Gvol (gvol@nexusystems.org)
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".local" / "lib" / "gvtools"))

from gvcore import (
    __version__,
    Output, Colors, c, die,
    Host, Inventory, Target,
    add_common_args, add_target_args, get_selector_from_args, apply_common_args,
    ssh_connect, ssh_exec, get_ssh_credentials,
)


# ─────────────────────────────────────────────────────────────────────────────
# Metrics Collection
# ─────────────────────────────────────────────────────────────────────────────

METRICS_SCRIPT = """
#!/bin/sh
# Collect system metrics snapshot

# CPU usage (from /proc/stat - calculate over 1 second)
CPU1=$(cat /proc/stat | head -1 | awk '{print $2+$3+$4+$5+$6+$7+$8}')
IDLE1=$(cat /proc/stat | head -1 | awk '{print $5}')
sleep 1
CPU2=$(cat /proc/stat | head -1 | awk '{print $2+$3+$4+$5+$6+$7+$8}')
IDLE2=$(cat /proc/stat | head -1 | awk '{print $5}')
CPU_DIFF=$((CPU2 - CPU1))
IDLE_DIFF=$((IDLE2 - IDLE1))
if [ "$CPU_DIFF" -gt 0 ]; then
    CPU_PCT=$(( (CPU_DIFF - IDLE_DIFF) * 100 / CPU_DIFF ))
else
    CPU_PCT=0
fi

# Load average
LOAD_1=$(cat /proc/loadavg | awk '{print $1}')
LOAD_5=$(cat /proc/loadavg | awk '{print $2}')
LOAD_15=$(cat /proc/loadavg | awk '{print $3}')

# Memory
MEM_TOTAL=$(free -b 2>/dev/null | awk '/^Mem:/ {print $2}')
MEM_USED=$(free -b 2>/dev/null | awk '/^Mem:/ {print $3}')
MEM_FREE=$(free -b 2>/dev/null | awk '/^Mem:/ {print $4}')
MEM_AVAIL=$(free -b 2>/dev/null | awk '/^Mem:/ {print $7}')

# Disk usage
DISK_TOTAL=$(df -B1 / 2>/dev/null | awk 'NR==2 {print $2}')
DISK_USED=$(df -B1 / 2>/dev/null | awk 'NR==2 {print $3}')
DISK_AVAIL=$(df -B1 / 2>/dev/null | awk 'NR==2 {print $4}')

# Network (bytes RX/TX on primary interface)
IFACE=$(ip route | awk '/default/ {print $5}' | head -1)
if [ -n "$IFACE" ]; then
    NET_RX=$(cat /sys/class/net/$IFACE/statistics/rx_bytes 2>/dev/null || echo 0)
    NET_TX=$(cat /sys/class/net/$IFACE/statistics/tx_bytes 2>/dev/null || echo 0)
else
    NET_RX=0
    NET_TX=0
fi

# Top processes by CPU
TOP_PROCS=$(ps aux --sort=-%cpu 2>/dev/null | head -6 | tail -5 | awk '{printf "%s:%s%%,", $11, $3}' | sed 's/,$//')

echo "{"
echo "  \\"timestamp\\": \\"$(date -Iseconds)\\","
echo "  \\"hostname\\": \\"$(hostname)\\","
echo "  \\"cpu_pct\\": $CPU_PCT,"
echo "  \\"load_1\\": $LOAD_1,"
echo "  \\"load_5\\": $LOAD_5,"
echo "  \\"load_15\\": $LOAD_15,"
echo "  \\"mem_total_bytes\\": $MEM_TOTAL,"
echo "  \\"mem_used_bytes\\": $MEM_USED,"
echo "  \\"mem_avail_bytes\\": $MEM_AVAIL,"
echo "  \\"disk_total_bytes\\": $DISK_TOTAL,"
echo "  \\"disk_used_bytes\\": $DISK_USED,"
echo "  \\"disk_avail_bytes\\": $DISK_AVAIL,"
echo "  \\"net_rx_bytes\\": $NET_RX,"
echo "  \\"net_tx_bytes\\": $NET_TX,"
echo "  \\"top_procs\\": \\"$TOP_PROCS\\""
echo "}"
"""


@dataclass
class MetricsSnapshot:
    """A single metrics snapshot."""
    timestamp: str = ""
    hostname: str = ""
    cpu_pct: int = 0
    load_1: float = 0.0
    load_5: float = 0.0
    load_15: float = 0.0
    mem_total_bytes: int = 0
    mem_used_bytes: int = 0
    mem_avail_bytes: int = 0
    disk_total_bytes: int = 0
    disk_used_bytes: int = 0
    disk_avail_bytes: int = 0
    net_rx_bytes: int = 0
    net_tx_bytes: int = 0
    top_procs: str = ""
    error: str = ""
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "hostname": self.hostname,
            "cpu_pct": self.cpu_pct,
            "load_1": self.load_1,
            "load_5": self.load_5,
            "load_15": self.load_15,
            "mem_total_bytes": self.mem_total_bytes,
            "mem_used_bytes": self.mem_used_bytes,
            "mem_avail_bytes": self.mem_avail_bytes,
            "disk_total_bytes": self.disk_total_bytes,
            "disk_used_bytes": self.disk_used_bytes,
            "disk_avail_bytes": self.disk_avail_bytes,
            "net_rx_bytes": self.net_rx_bytes,
            "net_tx_bytes": self.net_tx_bytes,
            "top_procs": self.top_procs,
            "error": self.error,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "MetricsSnapshot":
        return cls(
            timestamp=data.get("timestamp", ""),
            hostname=data.get("hostname", ""),
            cpu_pct=int(data.get("cpu_pct", 0)),
            load_1=float(data.get("load_1", 0)),
            load_5=float(data.get("load_5", 0)),
            load_15=float(data.get("load_15", 0)),
            mem_total_bytes=int(data.get("mem_total_bytes", 0)),
            mem_used_bytes=int(data.get("mem_used_bytes", 0)),
            mem_avail_bytes=int(data.get("mem_avail_bytes", 0)),
            disk_total_bytes=int(data.get("disk_total_bytes", 0)),
            disk_used_bytes=int(data.get("disk_used_bytes", 0)),
            disk_avail_bytes=int(data.get("disk_avail_bytes", 0)),
            net_rx_bytes=int(data.get("net_rx_bytes", 0)),
            net_tx_bytes=int(data.get("net_tx_bytes", 0)),
            top_procs=data.get("top_procs", ""),
            error=data.get("error", ""),
        )
    
    @property
    def mem_pct(self) -> int:
        if self.mem_total_bytes > 0:
            return int(self.mem_used_bytes * 100 / self.mem_total_bytes)
        return 0
    
    @property
    def disk_pct(self) -> int:
        if self.disk_total_bytes > 0:
            return int(self.disk_used_bytes * 100 / self.disk_total_bytes)
        return 0


def bytes_to_human(n: int) -> str:
    """Convert bytes to human readable format."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(n) < 1024.0:
            return f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}PB"


# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

def cmd_snap(args: argparse.Namespace) -> None:
    """Take a metrics snapshot."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if not hosts:
        die("no hosts matched selector")
    
    password, key_path, sudo_pass = get_ssh_credentials(args)
    results = []
    
    for host in hosts:
        target = Target.from_host(host, default_user=host.user or "root")
        snapshot = MetricsSnapshot(hostname=host.name)
        
        try:
            Output.info(f"Collecting from {c(host.name, Colors.CYAN)}...")
            client = ssh_connect(
                target,
                password=password,
                key_path=key_path,
                timeout=getattr(args, "timeout", 15),
            )
            
            code, out, err = ssh_exec(client, METRICS_SCRIPT, sudo=True, password=sudo_pass or password)
            client.close()
            
            if code == 0:
                try:
                    data = json.loads(out)
                    snapshot = MetricsSnapshot.from_dict(data)
                except json.JSONDecodeError:
                    snapshot.error = f"invalid output: {out[:100]}"
            else:
                snapshot.error = f"exit {code}: {err[:100]}"
        
        except Exception as e:
            snapshot.error = str(e)
        
        results.append(snapshot)
    
    if Output.json_mode:
        Output.json_output({"snapshots": [r.to_dict() for r in results]})
        return
    
    Output.header(f"Metrics Snapshot ({len(results)} hosts)")
    
    headers = ["Host", "CPU", "Load", "Memory", "Disk", "Net RX", "Net TX"]
    rows = []
    for s in results:
        if s.error:
            rows.append([c(s.hostname, Colors.CYAN), c("ERROR", Colors.RED), "-", "-", "-", "-", "-"])
        else:
            rows.append([
                c(s.hostname, Colors.CYAN),
                f"{s.cpu_pct}%",
                f"{s.load_1}",
                f"{s.mem_pct}%",
                f"{s.disk_pct}%",
                bytes_to_human(s.net_rx_bytes),
                bytes_to_human(s.net_tx_bytes),
            ])
    
    Output.table(headers, rows)


def cmd_record(args: argparse.Namespace) -> None:
    """Record metrics over time."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if not hosts:
        die("no hosts matched selector")
    
    interval = getattr(args, "interval", 10)
    duration = getattr(args, "duration", 60)
    output_path = getattr(args, "out", "") or "metrics.json"
    
    # Default max duration: 30 minutes
    if duration > 1800:
        Output.warn("duration capped at 30 minutes")
        duration = 1800
    
    password, key_path, sudo_pass = get_ssh_credentials(args)
    all_snapshots = []
    
    iterations = duration // interval
    Output.info(f"Recording {iterations} samples over {duration}s (every {interval}s)")
    Output.info(f"Output: {output_path}")
    
    start_time = time.time()
    
    for i in range(iterations):
        elapsed = time.time() - start_time
        if elapsed >= duration:
            break
        
        Output.step(f"Sample {i + 1}/{iterations}...")
        
        for host in hosts:
            target = Target.from_host(host, default_user=host.user or "root")
            snapshot = MetricsSnapshot(hostname=host.name)
            
            try:
                client = ssh_connect(
                    target,
                    password=password,
                    key_path=key_path,
                    timeout=15,
                )
                
                code, out, err = ssh_exec(client, METRICS_SCRIPT, sudo=True, password=sudo_pass or password)
                client.close()
                
                if code == 0:
                    try:
                        data = json.loads(out)
                        snapshot = MetricsSnapshot.from_dict(data)
                    except json.JSONDecodeError:
                        snapshot.error = f"parse error"
                else:
                    snapshot.error = f"exit {code}"
            except Exception as e:
                snapshot.error = str(e)
            
            all_snapshots.append(snapshot.to_dict())
        
        # Sleep until next interval
        if i < iterations - 1:
            time.sleep(interval)
    
    # Write output
    output_data = {
        "start": start_time,
        "end": time.time(),
        "interval": interval,
        "hosts": [h.name for h in hosts],
        "snapshots": all_snapshots,
    }
    
    Path(output_path).write_text(json.dumps(output_data, indent=2) + "\n")
    Output.success(f"Recorded {len(all_snapshots)} samples to {output_path}")


def cmd_export(args: argparse.Namespace) -> None:
    """Export recorded metrics to different format."""
    input_path = args.input
    output_path = getattr(args, "out", "") or ""
    fmt = getattr(args, "format", "csv")
    
    if not Path(input_path).exists():
        die(f"input file not found: {input_path}")
    
    try:
        data = json.loads(Path(input_path).read_text())
    except json.JSONDecodeError as e:
        die(f"invalid JSON: {e}")
    
    snapshots = data.get("snapshots", [])
    
    if fmt == "csv":
        output = StringIO()
        if snapshots:
            writer = csv.DictWriter(output, fieldnames=snapshots[0].keys())
            writer.writeheader()
            writer.writerows(snapshots)
        result = output.getvalue()
    else:  # json
        result = json.dumps(snapshots, indent=2)
    
    if output_path:
        Path(output_path).write_text(result)
        Output.success(f"Exported to {output_path}")
    else:
        print(result)


def cmd_compare(args: argparse.Namespace) -> None:
    """Compare current snapshot to earlier record."""
    inventory = Inventory()
    
    host_name = args.target
    if not host_name:
        die("host is required")
    
    host = inventory.get(host_name)
    if not host:
        # Try as direct target
        target = Target.parse(host_name)
        host = Host(name=target.host, address=target.host, port=target.port, user=target.user)
    
    since = getattr(args, "since", "") or "1h"
    
    # Get current snapshot
    password, key_path, sudo_pass = get_ssh_credentials(args)
    target = Target.from_host(host, default_user=host.user or "root")
    
    try:
        Output.info(f"Getting current metrics from {c(host.name, Colors.CYAN)}...")
        client = ssh_connect(
            target,
            password=password,
            key_path=key_path,
            timeout=getattr(args, "timeout", 15),
        )
        
        code, out, err = ssh_exec(client, METRICS_SCRIPT, sudo=True, password=sudo_pass or password)
        client.close()
        
        if code != 0:
            die(f"failed to get metrics: {err}")
        
        current = MetricsSnapshot.from_dict(json.loads(out))
    except Exception as e:
        die(f"failed: {e}")
    
    if Output.json_mode:
        Output.json_output({"current": current.to_dict(), "message": "comparison requires historical data"})
        return
    
    Output.header(f"Current Metrics: {host.name}")
    Output.keyvalue("CPU", f"{current.cpu_pct}%")
    Output.keyvalue("Load", f"{current.load_1} / {current.load_5} / {current.load_15}")
    Output.keyvalue("Memory", f"{current.mem_pct}% ({bytes_to_human(current.mem_used_bytes)} / {bytes_to_human(current.mem_total_bytes)})")
    Output.keyvalue("Disk", f"{current.disk_pct}% ({bytes_to_human(current.disk_used_bytes)} / {bytes_to_human(current.disk_total_bytes)})")
    Output.keyvalue("Network RX", bytes_to_human(current.net_rx_bytes))
    Output.keyvalue("Network TX", bytes_to_human(current.net_tx_bytes))
    Output.keyvalue("Top Procs", current.top_procs)
    
    Output.info("Note: Historical comparison requires recorded data (use 'mx record' first)")


# ─────────────────────────────────────────────────────────────────────────────
# Parser Setup
# ─────────────────────────────────────────────────────────────────────────────

def setup_snap_parser(parser: argparse.ArgumentParser) -> None:
    add_target_args(parser)
    add_common_args(parser)


def setup_record_parser(parser: argparse.ArgumentParser) -> None:
    add_target_args(parser)
    parser.add_argument("--interval", type=int, default=10, help="seconds between samples (default: 10)")
    parser.add_argument("--duration", type=int, default=60, help="total duration in seconds (default: 60)")
    parser.add_argument("--out", "-o", help="output file (default: metrics.json)")
    add_common_args(parser)


def setup_export_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("input", help="input JSON file from 'mx record'")
    parser.add_argument("--format", "-f", choices=["csv", "json"], default="csv", help="output format")
    parser.add_argument("--out", "-o", help="output file")
    add_common_args(parser)


def setup_compare_parser(parser: argparse.ArgumentParser) -> None:
    add_target_args(parser)
    parser.add_argument("--since", default="1h", help="time window for comparison")
    add_common_args(parser)


cmd_snap.setup_parser = setup_snap_parser  # type: ignore
cmd_record.setup_parser = setup_record_parser  # type: ignore
cmd_export.setup_parser = setup_export_parser  # type: ignore
cmd_compare.setup_parser = setup_compare_parser  # type: ignore


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    Output.set_tool("gvmetrics", "Resource metrics collection")
    
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(f"gvmetrics {__version__}")
        sys.exit(0)
    
    invoked_as = Path(sys.argv[0]).name
    
    parser = argparse.ArgumentParser(
        prog=invoked_as,
        description="Resource metrics collection and time series recording",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  mx snap web1.example.com
  mx snap --role web
  mx record --role web --interval 10 --duration 300 --out metrics.json
  mx export metrics.json --format csv --out metrics.csv
  mx compare web1.example.com --since 1h
        """,
    )
    parser.add_argument("--version", "-V", action="version", version=f"gvmetrics {__version__}")
    
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    
    snap_p = subparsers.add_parser("snap", help="take metrics snapshot")
    setup_snap_parser(snap_p)
    
    record_p = subparsers.add_parser("record", help="record metrics over time")
    setup_record_parser(record_p)
    
    export_p = subparsers.add_parser("export", help="export recorded metrics")
    setup_export_parser(export_p)
    
    compare_p = subparsers.add_parser("compare", help="compare to earlier metrics")
    setup_compare_parser(compare_p)
    
    args = parser.parse_args()
    apply_common_args(args)
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    commands = {
        "snap": cmd_snap,
        "record": cmd_record,
        "export": cmd_export,
        "compare": cmd_compare,
    }
    
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
