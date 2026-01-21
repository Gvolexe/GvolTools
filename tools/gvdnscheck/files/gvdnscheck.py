#!/usr/bin/env python3
"""
gvdnscheck - DNS validation and consistency checking

Validate DNS resolution and SSH fingerprint consistency.

Aliases: dns, dc, gvdns

Author: Gvol (gvol@nexusystems.org)
"""

from __future__ import annotations

import argparse
import hashlib
import socket
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".local" / "lib" / "gvtools"))

from gvcore import (
    Output, Colors, c, die,
    Inventory,
    add_common_args, add_target_args, get_selector_from_args, apply_common_args,
)

__version__ = "1.1.1"


def resolve_dns(hostname: str, record_type: str = "A") -> list[str]:
    """Resolve DNS using system resolver."""
    results = []
    try:
        if record_type == "A":
            addrs = socket.getaddrinfo(hostname, None, socket.AF_INET)
            results = list(set(addr[4][0] for addr in addrs))
        elif record_type == "AAAA":
            addrs = socket.getaddrinfo(hostname, None, socket.AF_INET6)
            results = list(set(addr[4][0] for addr in addrs))
        elif record_type in ("TXT", "MX", "CNAME", "NS"):
            proc = subprocess.run(
                ["dig", "+short", record_type, hostname],
                capture_output=True, text=True, timeout=10
            )
            if proc.returncode == 0:
                results = [line.strip() for line in proc.stdout.strip().split("\n") if line.strip()]
    except Exception as e:
        Output.debug(f"DNS resolution error: {e}")
    return results


def get_ssh_fingerprint(hostname: str, port: int = 22) -> dict:
    """Get SSH host key fingerprint."""
    try:
        proc = subprocess.run(
            ["ssh-keyscan", "-t", "ed25519,rsa", "-p", str(port), hostname],
            capture_output=True, text=True, timeout=15
        )
        if proc.returncode == 0 and proc.stdout.strip():
            keys = {}
            for line in proc.stdout.strip().split("\n"):
                if line and not line.startswith("#"):
                    parts = line.split()
                    if len(parts) >= 3:
                        key_type = parts[1]
                        key_data = parts[2]
                        key_hash = hashlib.sha256(key_data.encode()).hexdigest()[:16]
                        keys[key_type] = key_hash
            return keys
    except Exception as e:
        Output.debug(f"SSH fingerprint error: {e}")
    return {}


def cmd_lookup(args: argparse.Namespace) -> None:
    """Lookup DNS records."""
    hostname = args.hostname
    record_type = args.type or "A"
    
    Output.header(f"DNS: {hostname} ({record_type})")
    
    results = resolve_dns(hostname, record_type)
    
    if Output.json_mode:
        Output.json_output({"hostname": hostname, "type": record_type, "records": results})
        return
    
    if results:
        for r in results:
            Output.step(r)
    else:
        Output.warn("No records found")
    
    if record_type == "A":
        aaaa = resolve_dns(hostname, "AAAA")
        if aaaa:
            Output.info(f"IPv6: {', '.join(aaaa)}")


def cmd_zone(args: argparse.Namespace) -> None:
    """Query zone records."""
    domain = args.domain
    
    Output.header(f"Zone: {domain}")
    
    record_types = ["A", "AAAA", "MX", "TXT", "NS", "CNAME"]
    
    results = {}
    for rt in record_types:
        records = resolve_dns(domain, rt)
        if records:
            results[rt] = records
    
    if Output.json_mode:
        Output.json_output({"domain": domain, "records": results})
        return
    
    for rt, records in results.items():
        Output.step(f"{rt}:")
        for r in records:
            print(f"    {r}")


def cmd_ssh_consistency(args: argparse.Namespace) -> None:
    """Check SSH fingerprint consistency with DNS."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector) if not selector.is_empty() else []
    
    if not hosts:
        die("no targets specified")
    
    Output.header("SSH/DNS Consistency")
    
    results = []
    
    headers = ["Host", "Resolved IP", "SSH Keys", "Status"]
    rows = []
    
    for host in hosts:
        hostname = host.hostname or host.name
        
        ip_addrs = resolve_dns(hostname)
        ssh_keys = get_ssh_fingerprint(hostname)
        
        ip_str = ", ".join(ip_addrs[:2]) if ip_addrs else "FAIL"
        key_str = ", ".join(ssh_keys.keys()) if ssh_keys else "FAIL"
        
        if ip_addrs and ssh_keys:
            status = c("OK", Colors.GREEN)
            result_status = "ok"
        elif ip_addrs and not ssh_keys:
            status = c("NO SSH", Colors.YELLOW)
            result_status = "no_ssh"
        elif not ip_addrs:
            status = c("NO DNS", Colors.RED)
            result_status = "no_dns"
        else:
            status = c("FAIL", Colors.RED)
            result_status = "fail"
        
        rows.append([
            c(host.name, Colors.CYAN),
            ip_str,
            key_str,
            status,
        ])
        
        if Output.json_mode:
            results.append({
                "host": host.name,
                "hostname": hostname,
                "ips": ip_addrs,
                "ssh_keys": ssh_keys,
                "status": result_status,
            })
    
    if Output.json_mode:
        Output.json_output({"hosts": results})
    else:
        Output.table(headers, rows)


def cmd_report(args: argparse.Namespace) -> None:
    """Full DNS report."""
    inventory = Inventory()
    
    hosts = inventory.all_hosts()
    if not hosts:
        Output.info("No hosts in inventory")
        return
    
    Output.header(f"DNS Report ({len(hosts)} hosts)")
    
    ok_count = 0
    fail_count = 0
    results = []
    
    for host in hosts:
        hostname = host.hostname or host.name
        
        a_records = resolve_dns(hostname, "A")
        aaaa_records = resolve_dns(hostname, "AAAA")
        
        if a_records or aaaa_records:
            ok_count += 1
            status = "ok"
        else:
            fail_count += 1
            status = "fail"
        
        results.append({
            "host": host.name,
            "hostname": hostname,
            "ipv4": a_records,
            "ipv6": aaaa_records,
            "status": status,
        })
    
    if Output.json_mode:
        Output.json_output({"total": len(hosts), "ok": ok_count, "fail": fail_count, "hosts": results})
    else:
        Output.success(f"Resolving: {ok_count}")
        Output.error(f"Failed: {fail_count}") if fail_count else None
        
        Output.step("Failures:")
        for r in results:
            if r["status"] == "fail":
                Output.warn(f"  {r['host']} ({r['hostname']})")


def main() -> None:
    Output.set_tool("gvdnscheck", "DNS validator")
    
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(f"gvdnscheck {__version__}")
        sys.exit(0)
    
    parser = argparse.ArgumentParser(
        prog=Path(sys.argv[0]).name,
        description="DNS validation and consistency checking",
        epilog="""
Examples:
  dns lookup example.com
  dns lookup example.com --type MX
  dns zone example.com
  dns ssh-consistency --targets server1
  dns report --json
        """,
    )
    parser.add_argument("--version", "-V", action="version", version=f"gvdnscheck {__version__}")
    
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    
    lookup_p = subparsers.add_parser("lookup", help="lookup DNS records")
    lookup_p.add_argument("hostname", help="hostname to lookup")
    lookup_p.add_argument("--type", "-t", choices=["A", "AAAA", "MX", "TXT", "NS", "CNAME"])
    add_common_args(lookup_p)
    
    zone_p = subparsers.add_parser("zone", help="zone records")
    zone_p.add_argument("domain", help="domain to query")
    add_common_args(zone_p)
    
    ssh_p = subparsers.add_parser("ssh-consistency", help="check SSH/DNS consistency")
    add_target_args(ssh_p)
    add_common_args(ssh_p)
    
    report_p = subparsers.add_parser("report", help="full DNS report")
    add_common_args(report_p)
    
    args = parser.parse_args()
    apply_common_args(args)
    
    commands = {
        "lookup": cmd_lookup,
        "zone": cmd_zone,
        "ssh-consistency": cmd_ssh_consistency,
        "report": cmd_report,
    }
    
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
