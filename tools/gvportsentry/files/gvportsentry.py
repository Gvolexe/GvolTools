#!/usr/bin/env python3
"""
gvportsentry - Port scanning and baseline comparison

Scan open ports and compare against baselines.

Aliases: ps, ports, gvps

Author: Gvol (gvol@nexusystems.org)
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".local" / "lib" / "gvtools"))

from gvcore import (
    __version__,
    Output, Colors, c, die,
    Target, Inventory, GVTOOLS_CONFIG,
    add_common_args, add_target_args, get_selector_from_args, apply_common_args,
    ssh_connect, ssh_exec, get_ssh_credentials,
)


BASELINES_DIR = GVTOOLS_CONFIG / "port-baselines"


def load_baseline(host: str) -> dict | None:
    baseline_file = BASELINES_DIR / f"{host}.json"
    if baseline_file.exists():
        return json.loads(baseline_file.read_text())
    return None


def save_baseline(host: str, data: dict) -> None:
    BASELINES_DIR.mkdir(parents=True, exist_ok=True)
    baseline_file = BASELINES_DIR / f"{host}.json"
    baseline_file.write_text(json.dumps(data, indent=2))


def scan_ports_local(host: str, ports: list[int], timeout: float = 1.5) -> list[int]:
    """Scan ports locally."""
    open_ports = []
    for port in ports:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            result = sock.connect_ex((host, port))
            if result == 0:
                open_ports.append(port)
        except Exception:
            pass
        finally:
            sock.close()
    return open_ports


def make_remote_scan_script() -> str:
    return r"""
echo "=== LISTENING PORTS ==="
ss -tlnp 2>/dev/null | grep LISTEN | awk '{print $4, $6}' | sed 's/.*://' | while read port proc; do
    service=$(echo "$proc" | sed 's/.*"\([^"]*\)".*/\1/')
    echo "$port $service"
done
"""


def cmd_scan(args: argparse.Namespace) -> None:
    """Scan ports on target."""
    target_str = args.target
    
    common_ports = [
        22, 25, 53, 80, 110, 143, 443, 465, 587, 993, 995,
        3306, 5432, 6379, 8080, 8443, 27017,
    ]
    
    if "." in target_str or target_str[0].isdigit():
        Output.header(f"External Port Scan: {target_str}")
        
        open_ports = scan_ports_local(target_str, common_ports)
        
        if Output.json_mode:
            Output.json_output({"target": target_str, "ports": open_ports})
            return
        
        if open_ports:
            Output.success(f"Open: {', '.join(map(str, open_ports))}")
        else:
            Output.info("No common ports open")
    else:
        Output.header(f"Remote Port Scan: {target_str}")
        
        target = Target.parse(target_str)
        if not target.user:
            target.user = "root"
        
        try:
            password, key_path, sudo_password = get_ssh_credentials(args)
            client = ssh_connect(target, strict_hostkey=args.strict_hostkey, password=password, key_path=key_path)
            exit_code, stdout, stderr = ssh_exec(client, make_remote_scan_script(), sudo=True)
            client.close()
            print(stdout)
        except Exception as e:
            Output.error(str(e))


def cmd_baseline_save(args: argparse.Namespace) -> None:
    """Save port baseline."""
    target_str = args.target
    
    target = Target.parse(target_str)
    if not target.user:
        target.user = "root"
    
    Output.header(f"Save Baseline: {target.host}")
    
    try:
        password, key_path, sudo_password = get_ssh_credentials(args)
        client = ssh_connect(target, strict_hostkey=args.strict_hostkey, password=password, key_path=key_path)
        exit_code, stdout, stderr = ssh_exec(client, make_remote_scan_script(), sudo=True)
        client.close()
        
        ports = {}
        for line in stdout.strip().split("\n"):
            if line.startswith("==="):
                continue
            parts = line.split()
            if parts and parts[0].isdigit():
                port = int(parts[0])
                service = parts[1] if len(parts) > 1 else "unknown"
                ports[port] = service
        
        baseline = {
            "host": target.host,
            "created": datetime.now().isoformat(),
            "ports": ports,
        }
        
        save_baseline(target.host, baseline)
        Output.success(f"Saved baseline: {len(ports)} ports")
        
    except Exception as e:
        Output.error(str(e))


def cmd_baseline_diff(args: argparse.Namespace) -> None:
    """Compare against baseline."""
    target_str = args.target
    
    target = Target.parse(target_str)
    if not target.user:
        target.user = "root"
    
    baseline = load_baseline(target.host)
    if not baseline:
        die(f"no baseline for {target.host}")
    
    Output.header(f"Baseline Diff: {target.host}")
    Output.info(f"Baseline from: {baseline.get('created', 'unknown')[:10]}")
    
    try:
        password, key_path, sudo_password = get_ssh_credentials(args)
        client = ssh_connect(target, strict_hostkey=args.strict_hostkey, password=password, key_path=key_path)
        exit_code, stdout, stderr = ssh_exec(client, make_remote_scan_script(), sudo=True)
        client.close()
        
        current_ports = {}
        for line in stdout.strip().split("\n"):
            if line.startswith("==="):
                continue
            parts = line.split()
            if parts and parts[0].isdigit():
                port = int(parts[0])
                service = parts[1] if len(parts) > 1 else "unknown"
                current_ports[port] = service
        
        baseline_ports = {int(k): v for k, v in baseline.get("ports", {}).items()}
        
        current_set = set(current_ports.keys())
        baseline_set = set(baseline_ports.keys())
        
        new_ports = current_set - baseline_set
        closed_ports = baseline_set - current_set
        unchanged = current_set & baseline_set
        
        if Output.json_mode:
            Output.json_output({
                "host": target.host,
                "new": list(new_ports),
                "closed": list(closed_ports),
                "unchanged": list(unchanged),
            })
            return
        
        if new_ports:
            Output.warn("NEW ports:")
            for p in sorted(new_ports):
                print(f"  {c('+', Colors.RED)} {p} ({current_ports.get(p, '?')})")
        
        if closed_ports:
            Output.info("CLOSED ports:")
            for p in sorted(closed_ports):
                print(f"  {c('-', Colors.GREEN)} {p} ({baseline_ports.get(p, '?')})")
        
        if not new_ports and not closed_ports:
            Output.success("No changes from baseline")
        
    except Exception as e:
        Output.error(str(e))


def cmd_report(args: argparse.Namespace) -> None:
    """Port report for fleet."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector) if not selector.is_empty() else inventory.all_hosts()
    
    if not hosts:
        Output.info("No hosts in inventory")
        return
    
    Output.header(f"Port Report ({len(hosts)} hosts)")
    
    results = []
    headers = ["Host", "SSH", "HTTP/S", "DB", "Other"]
    rows = []
    
    for host in hosts:
        hostname = host.hostname or host.name
        
        ssh_open = check_port(hostname, 22)
        http_open = check_port(hostname, 80) or check_port(hostname, 443)
        db_open = check_port(hostname, 3306) or check_port(hostname, 5432)
        redis_open = check_port(hostname, 6379)
        
        rows.append([
            c(host.name, Colors.CYAN),
            c("✓", Colors.GREEN) if ssh_open else c("✗", Colors.RED),
            c("✓", Colors.GREEN) if http_open else c("-", Colors.DIM),
            c("✓", Colors.GREEN) if db_open else c("-", Colors.DIM),
            c("redis", Colors.YELLOW) if redis_open else c("-", Colors.DIM),
        ])
        
        results.append({
            "host": host.name,
            "ssh": ssh_open,
            "http": http_open,
            "db": db_open,
            "redis": redis_open,
        })
    
    if Output.json_mode:
        Output.json_output({"hosts": results})
    else:
        Output.table(headers, rows)


def check_port(host: str, port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    try:
        return sock.connect_ex((host, port)) == 0
    except Exception:
        return False
    finally:
        sock.close()


def main() -> None:
    Output.set_tool("gvportsentry", "Port scanner")
    
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(f"gvportsentry {__version__}")
        sys.exit(0)
    
    parser = argparse.ArgumentParser(
        prog=Path(sys.argv[0]).name,
        description="Port scanning and baseline comparison",
        epilog="""
Examples:
  ps scan server1
  ps scan 192.168.1.1
  ps baseline save server1
  ps baseline diff server1
  ps report --env prod
        """,
    )
    parser.add_argument("--version", "-V", action="version", version=f"gvportsentry {__version__}")
    
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    
    scan_p = subparsers.add_parser("scan", help="scan ports")
    scan_p.add_argument("target", help="target host or IP")
    add_common_args(scan_p)
    
    baseline_p = subparsers.add_parser("baseline", help="baseline management")
    baseline_sub = baseline_p.add_subparsers(dest="baseline_cmd", metavar="action")
    
    save_p = baseline_sub.add_parser("save", help="save baseline")
    save_p.add_argument("target", help="target host")
    add_common_args(save_p)
    
    diff_p = baseline_sub.add_parser("diff", help="diff against baseline")
    diff_p.add_argument("target", help="target host")
    add_common_args(diff_p)
    
    report_p = subparsers.add_parser("report", help="fleet report")
    add_target_args(report_p)
    add_common_args(report_p)
    
    args = parser.parse_args()
    apply_common_args(args)
    
    if args.command == "scan":
        cmd_scan(args)
    elif args.command == "baseline":
        if args.baseline_cmd == "save":
            cmd_baseline_save(args)
        elif args.baseline_cmd == "diff":
            cmd_baseline_diff(args)
        else:
            baseline_p.print_help()
    elif args.command == "report":
        cmd_report(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
