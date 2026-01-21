#!/usr/bin/env python3
"""
gvnetdiag - Network diagnostics tool

Ping, traceroute, port probing from local and remote nodes.

Aliases: nd, netdiag, gvnd

Author: Gvol (gvol@nexusystems.org)
"""

from __future__ import annotations

import argparse
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".local" / "lib" / "gvtools"))

from gvcore import (
    Output, Colors, c, die,
    Target, Inventory,
    add_common_args, add_target_args, get_selector_from_args, apply_common_args,
    ssh_connect, ssh_exec, local_exec,
)

__version__ = "1.1.0"


def check_port_local(host: str, port: int, timeout: float = 3.0) -> bool:
    """Check if port is open locally."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        result = sock.connect_ex((host, port))
        return result == 0
    except Exception:
        return False
    finally:
        sock.close()


def cmd_local(args: argparse.Namespace) -> None:
    """Run local diagnostics."""
    target = args.target or "8.8.8.8"
    
    Output.header(f"Local Network Diagnostics -> {target}")
    
    results = {}
    
    Output.step("Ping test...")
    code, stdout, _ = local_exec(f"ping -c 3 -W 2 {target}")
    if code == 0:
        for line in stdout.split("\n"):
            if "rtt" in line or "avg" in line:
                Output.success(line.strip())
                results["ping"] = "ok"
                break
    else:
        Output.error("Ping failed")
        results["ping"] = "fail"
    
    Output.step("DNS resolution...")
    try:
        ip = socket.gethostbyname(target) if not target[0].isdigit() else target
        Output.success(f"Resolved: {ip}")
        results["dns"] = ip
    except Exception as e:
        Output.error(f"DNS failed: {e}")
        results["dns"] = "fail"
    
    Output.step("Default gateway...")
    code, stdout, _ = local_exec("ip route show default | head -1")
    if code == 0 and stdout.strip():
        Output.success(stdout.strip())
        results["gateway"] = stdout.strip().split()[2] if len(stdout.split()) > 2 else "unknown"
    
    if Output.json_mode:
        Output.json_output(results)


def cmd_remote(args: argparse.Namespace) -> None:
    """Run diagnostics from remote host."""
    target_str = args.target
    probe_target = args.probe or "8.8.8.8"
    
    target = Target.parse(target_str)
    if not target.user:
        target.user = "root"
    
    Output.header(f"Remote Diagnostics from {target.host} -> {probe_target}")
    
    script = f"""
echo "=== CONNECTIVITY ==="
ping -c 3 -W 2 {probe_target} 2>&1 | tail -2

echo ""
echo "=== ROUTING ==="
ip route show | head -3

echo ""
echo "=== DNS ==="
cat /etc/resolv.conf | grep nameserver

echo ""
echo "=== INTERFACES ==="
ip -br addr show | head -5
"""
    
    try:
        client = ssh_connect(target, strict_hostkey=args.strict_hostkey)
        exit_code, stdout, stderr = ssh_exec(client, script, sudo=True)
        client.close()
        print(stdout)
    except Exception as e:
        Output.error(str(e))


def cmd_ports(args: argparse.Namespace) -> None:
    """Check ports on target."""
    target_str = args.target
    ports_str = args.ports or "22,80,443"
    
    ports = [int(p.strip()) for p in ports_str.split(",")]
    
    Output.header(f"Port Check: {target_str}")
    
    results = []
    headers = ["Port", "Status", "Service"]
    rows = []
    
    for port in ports:
        is_open = check_port_local(target_str, port, timeout=args.timeout or 3)
        
        service_map = {
            22: "SSH", 80: "HTTP", 443: "HTTPS", 53: "DNS",
            25: "SMTP", 3306: "MySQL", 5432: "PostgreSQL",
            6379: "Redis", 27017: "MongoDB", 8080: "HTTP-Alt",
        }
        
        status = c("OPEN", Colors.GREEN) if is_open else c("CLOSED", Colors.RED)
        service = service_map.get(port, "-")
        
        rows.append([str(port), status, service])
        results.append({"port": port, "open": is_open, "service": service})
    
    if Output.json_mode:
        Output.json_output({"target": target_str, "ports": results})
    else:
        Output.table(headers, rows)


def cmd_trace(args: argparse.Namespace) -> None:
    """Traceroute to target."""
    target = args.target
    
    Output.header(f"Traceroute: {target}")
    
    code, stdout, stderr = local_exec(f"traceroute -w 2 -q 1 -m 15 {target}")
    
    if code == 0:
        print(stdout)
    else:
        code, stdout, _ = local_exec(f"tracepath -m 15 {target}")
        if code == 0:
            print(stdout)
        else:
            Output.error("traceroute/tracepath failed")


def cmd_report(args: argparse.Namespace) -> None:
    """Full network report."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector) if not selector.is_empty() else []
    
    if not hosts:
        die("no targets specified")
    
    Output.header(f"Network Report ({len(hosts)} hosts)")
    
    results = []
    headers = ["Host", "Ping", "SSH", "HTTP", "HTTPS"]
    rows = []
    
    for host in hosts:
        hostname = host.hostname or host.name
        
        code, _, _ = local_exec(f"ping -c 1 -W 2 {hostname}")
        ping_ok = code == 0
        
        ssh_open = check_port_local(hostname, 22, 2)
        http_open = check_port_local(hostname, 80, 2)
        https_open = check_port_local(hostname, 443, 2)
        
        rows.append([
            c(host.name, Colors.CYAN),
            c("✓", Colors.GREEN) if ping_ok else c("✗", Colors.RED),
            c("✓", Colors.GREEN) if ssh_open else c("✗", Colors.RED),
            c("✓", Colors.GREEN) if http_open else c("-", Colors.DIM),
            c("✓", Colors.GREEN) if https_open else c("-", Colors.DIM),
        ])
        
        results.append({
            "host": host.name,
            "hostname": hostname,
            "ping": ping_ok,
            "ssh": ssh_open,
            "http": http_open,
            "https": https_open,
        })
    
    if Output.json_mode:
        Output.json_output({"hosts": results})
    else:
        Output.table(headers, rows)


def main() -> None:
    Output.set_tool("gvnetdiag", "Network diagnostics")
    
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(f"gvnetdiag {__version__}")
        sys.exit(0)
    
    parser = argparse.ArgumentParser(
        prog=Path(sys.argv[0]).name,
        description="Network diagnostics tool",
        epilog="""
Examples:
  nd local
  nd local 1.1.1.1
  nd remote server1 --probe google.com
  nd ports server1 --ports 22,80,443
  nd trace 8.8.8.8
  nd report --targets server1
        """,
    )
    parser.add_argument("--version", "-V", action="version", version=f"gvnetdiag {__version__}")
    
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    
    local_p = subparsers.add_parser("local", help="local diagnostics")
    local_p.add_argument("target", nargs="?", help="target to probe")
    add_common_args(local_p)
    
    remote_p = subparsers.add_parser("remote", help="remote diagnostics")
    remote_p.add_argument("target", help="remote host to run from")
    remote_p.add_argument("--probe", "-p", help="target to probe from remote")
    add_common_args(remote_p)
    
    ports_p = subparsers.add_parser("ports", help="check ports")
    ports_p.add_argument("target", help="target host")
    ports_p.add_argument("--ports", help="ports to check (comma-separated)")
    add_common_args(ports_p)
    
    trace_p = subparsers.add_parser("trace", help="traceroute")
    trace_p.add_argument("target", help="target")
    add_common_args(trace_p)
    
    report_p = subparsers.add_parser("report", help="full report")
    add_target_args(report_p)
    add_common_args(report_p)
    
    args = parser.parse_args()
    apply_common_args(args)
    
    commands = {
        "local": cmd_local,
        "remote": cmd_remote,
        "ports": cmd_ports,
        "trace": cmd_trace,
        "report": cmd_report,
    }
    
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
