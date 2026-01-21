#!/usr/bin/env python3
"""
gvlogtriage - Auth/system log analysis

Pull and summarize auth/system logs around SSH/sudo incidents.

Aliases: lt, logtriage, gvlt

Author: Gvol (gvol@nexusystems.org)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".local" / "lib" / "gvtools"))

from gvcore import (
    Output, die,
    Target, Inventory,
    add_common_args, add_target_args, get_selector_from_args, apply_common_args,
    ssh_connect, ssh_exec, get_ssh_credentials,
)

__version__ = "1.2.1"


def make_ssh_log_script(since: str) -> str:
    return f"""
echo "=== SSH AUTH LOGS (since {since}) ==="
if [ -f /var/log/auth.log ]; then
    grep -E "sshd\\[" /var/log/auth.log | tail -100
elif [ -f /var/log/secure ]; then
    grep -E "sshd\\[" /var/log/secure | tail -100
else
    journalctl -u sshd --since "{since}" 2>/dev/null || journalctl -u ssh --since "{since}" 2>/dev/null || echo "No SSH logs found"
fi | tail -50
"""


def make_sudo_log_script(since: str) -> str:
    return f"""
echo "=== SUDO LOGS (since {since}) ==="
if [ -f /var/log/auth.log ]; then
    grep -E "sudo\\[" /var/log/auth.log | tail -50
elif [ -f /var/log/secure ]; then
    grep -E "sudo\\[" /var/log/secure | tail -50
else
    journalctl -t sudo --since "{since}" 2>/dev/null || echo "No sudo logs found"
fi
"""


def make_bans_script(since: str) -> str:
    return f"""
echo "=== FAIL2BAN ACTIVITY (since {since}) ==="
if command -v fail2ban-client >/dev/null 2>&1; then
    fail2ban-client status 2>/dev/null
    echo ""
    echo "Recent bans:"
    journalctl -u fail2ban --since "{since}" 2>/dev/null | grep -E "Ban|Unban" | tail -20
else
    echo "fail2ban not installed"
fi
"""


def make_full_report_script(since: str) -> str:
    return f"""
echo "=== SECURITY EVENT TIMELINE (since {since}) ==="
echo ""

echo "--- SSH Events ---"
journalctl -u sshd -u ssh --since "{since}" 2>/dev/null | grep -E "Failed|Accepted|Invalid|Disconnected" | tail -20 || echo "No SSH events"

echo ""
echo "--- Sudo Events ---"
journalctl -t sudo --since "{since}" 2>/dev/null | tail -10 || echo "No sudo events"

echo ""
echo "--- Fail2ban Events ---"
journalctl -u fail2ban --since "{since}" 2>/dev/null | grep -E "Ban|Unban" | tail -10 || echo "No fail2ban events"

echo ""
echo "--- Failed Logins ---"
lastb 2>/dev/null | head -10 || echo "No failed logins recorded"

echo ""
echo "=== END REPORT ==="
"""


def cmd_ssh(args: argparse.Namespace) -> None:
    """Show SSH auth logs."""
    target_str = args.target
    since = args.since or "2h"
    
    if not target_str:
        die("target is required")
    
    target = Target.parse(target_str)
    if not target.user:
        target.user = "root"
    
    Output.header(f"SSH Logs: {target.host}")
    
    try:
        password, key_path = get_ssh_credentials(args)
        client = ssh_connect(target, strict_hostkey=args.strict_hostkey, password=password, key_path=key_path)
        exit_code, stdout, stderr = ssh_exec(client, make_ssh_log_script(since), sudo=True)
        client.close()
        print(stdout)
    except Exception as e:
        Output.error(str(e))


def cmd_sudo(args: argparse.Namespace) -> None:
    """Show sudo logs."""
    target_str = args.target
    since = args.since or "2h"
    
    if not target_str:
        die("target is required")
    
    target = Target.parse(target_str)
    if not target.user:
        target.user = "root"
    
    Output.header(f"Sudo Logs: {target.host}")
    
    try:
        password, key_path = get_ssh_credentials(args)
        client = ssh_connect(target, strict_hostkey=args.strict_hostkey, password=password, key_path=key_path)
        exit_code, stdout, stderr = ssh_exec(client, make_sudo_log_script(since), sudo=True)
        client.close()
        print(stdout)
    except Exception as e:
        Output.error(str(e))


def cmd_bans(args: argparse.Namespace) -> None:
    """Show fail2ban activity."""
    target_str = args.target
    since = args.since or "24h"
    
    if not target_str:
        die("target is required")
    
    target = Target.parse(target_str)
    if not target.user:
        target.user = "root"
    
    Output.header(f"Fail2ban: {target.host}")
    
    try:
        password, key_path = get_ssh_credentials(args)
        client = ssh_connect(target, strict_hostkey=args.strict_hostkey, password=password, key_path=key_path)
        exit_code, stdout, stderr = ssh_exec(client, make_bans_script(since), sudo=True)
        client.close()
        print(stdout)
    except Exception as e:
        Output.error(str(e))


def cmd_report(args: argparse.Namespace) -> None:
    """Full security event report."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector) if not selector.is_empty() else []
    since = args.since or "24h"
    
    if not hosts:
        die("no targets specified")
    
    results = []
    
    password, key_path = get_ssh_credentials(args)
    for host in hosts:
        Output.header(f"Report: {host.name}")
        target = Target.from_host(host, default_user="root")
        
        try:
            client = ssh_connect(target, strict_hostkey=args.strict_hostkey, password=password, key_path=key_path)
            exit_code, stdout, stderr = ssh_exec(client, make_full_report_script(since), sudo=True)
            client.close()
            
            if Output.json_mode:
                results.append({"host": host.name, "report": stdout})
            else:
                print(stdout)
        except Exception as e:
            Output.error(str(e))
            if Output.json_mode:
                results.append({"host": host.name, "error": str(e)})
    
    if Output.json_mode:
        Output.json_output({"results": results})


def main() -> None:
    Output.set_tool("gvlogtriage", "Security log analyzer")
    
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(f"gvlogtriage {__version__}")
        sys.exit(0)
    
    parser = argparse.ArgumentParser(
        prog=Path(sys.argv[0]).name,
        description="Pull and summarize auth/system logs",
        epilog="""
Examples:
  lt ssh server1 --since 2h
  lt sudo server1 --since "2024-01-01 00:00"
  lt bans server1 --since 24h
  lt report --targets server1 --since 24h --json
        """,
    )
    parser.add_argument("--version", "-V", action="version", version=f"gvlogtriage {__version__}")
    
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    
    ssh_p = subparsers.add_parser("ssh", help="SSH auth logs")
    ssh_p.add_argument("target", help="target host")
    ssh_p.add_argument("--since", default="2h", help="time range (default: 2h)")
    add_common_args(ssh_p)
    
    sudo_p = subparsers.add_parser("sudo", help="sudo logs")
    sudo_p.add_argument("target", help="target host")
    sudo_p.add_argument("--since", default="2h", help="time range")
    add_common_args(sudo_p)
    
    bans_p = subparsers.add_parser("bans", help="fail2ban activity")
    bans_p.add_argument("target", help="target host")
    bans_p.add_argument("--since", default="24h", help="time range")
    add_common_args(bans_p)
    
    report_p = subparsers.add_parser("report", help="full report")
    report_p.add_argument("--since", default="24h", help="time range")
    add_target_args(report_p)
    add_common_args(report_p)
    
    args = parser.parse_args()
    apply_common_args(args)
    
    commands = {"ssh": cmd_ssh, "sudo": cmd_sudo, "bans": cmd_bans, "report": cmd_report}
    
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
