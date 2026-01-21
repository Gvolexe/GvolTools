#!/usr/bin/env python3
"""
gvfirewallctl - Firewall baseline management

Apply and verify firewall baselines per role using UFW/nftables.

Aliases: fw, gvfw

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

# Role-based firewall baselines
BASELINES = {
    "web": {
        "allow": ["22/tcp", "80/tcp", "443/tcp"],
        "default": "deny",
        "description": "Web server (SSH, HTTP, HTTPS)",
    },
    "db": {
        "allow": ["22/tcp"],
        "allow_from": {"5432/tcp": "10.0.0.0/8", "3306/tcp": "10.0.0.0/8"},
        "default": "deny",
        "description": "Database server (SSH, DB from internal)",
    },
    "bastion": {
        "allow": ["22/tcp"],
        "default": "deny",
        "description": "Bastion/jump host (SSH only)",
    },
    "minimal": {
        "allow": ["22/tcp"],
        "default": "deny",
        "description": "Minimal (SSH only)",
    },
}


def make_ufw_script(role: str) -> str:
    """Generate UFW configuration script."""
    baseline = BASELINES.get(role)
    if not baseline:
        return f"echo 'Unknown role: {role}'; exit 1"
    
    lines = [
        "set -e",
        "# Reset UFW",
        "ufw --force reset",
        f"ufw default {baseline['default']} incoming",
        "ufw default allow outgoing",
    ]
    
    for port in baseline.get("allow", []):
        lines.append(f"ufw allow {port}")
    
    for port, src in baseline.get("allow_from", {}).items():
        lines.append(f"ufw allow from {src} to any port {port.split('/')[0]} proto {port.split('/')[1]}")
    
    lines.extend([
        "ufw --force enable",
        "ufw status verbose",
        "echo 'OK: firewall configured'",
    ])
    
    return "\n".join(lines)


def make_status_script() -> str:
    """Generate firewall status script."""
    return """
echo "=== FIREWALL STATUS ==="
if command -v ufw >/dev/null 2>&1; then
    ufw status verbose
elif command -v nft >/dev/null 2>&1; then
    nft list ruleset
elif command -v iptables >/dev/null 2>&1; then
    iptables -L -n -v
else
    echo "No firewall detected"
fi
"""


def cmd_apply(args: argparse.Namespace) -> None:
    """Apply firewall baseline."""
    role = args.role
    if role not in BASELINES:
        die(f"unknown role: {role}\nAvailable: {', '.join(BASELINES.keys())}")
    
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector) if not selector.is_empty() else []
    
    if not hosts:
        die("no targets specified")
    
    Output.header(f"Apply Firewall: {role}")
    Output.step(BASELINES[role]["description"])
    
    script = make_ufw_script(role)
    
    if args.dry_run:
        Output.info("Would apply to:")
        for h in hosts:
            Output.step(h.name)
        Output.divider()
        Output.info("Script:")
        print(script)
        return
    
    password, key_path, sudo_password = get_ssh_credentials(args)
    
    for host in hosts:
        Output.info(f"Configuring {host.name}...")
        target = Target.from_host(host, default_user="root")
        
        try:
            client = ssh_connect(target, strict_hostkey=args.strict_hostkey, password=password, key_path=key_path)
            exit_code, stdout, stderr = ssh_exec(client, script, sudo=True, password=sudo_password)
            client.close()
            
            if exit_code == 0:
                Output.success(f"Applied to {host.name}")
            else:
                Output.error(f"Failed on {host.name}: {stderr}")
        except Exception as e:
            Output.error(f"Failed on {host.name}: {e}")


def cmd_diff(args: argparse.Namespace) -> None:
    """Show diff between current and baseline."""
    target_str = args.target
    if not target_str:
        die("target is required")
    
    target = Target.parse(target_str)
    if not target.user:
        target.user = "root"
    
    Output.header(f"Firewall Diff: {target.host}")
    
    password, key_path, sudo_password = get_ssh_credentials(args)
    
    try:
        client = ssh_connect(target, strict_hostkey=args.strict_hostkey, password=password, key_path=key_path)
        exit_code, stdout, stderr = ssh_exec(client, make_status_script(), sudo=True)
        client.close()
        
        print(stdout)
        Output.info("Compare with baseline using: fw apply --role <role> --dry-run")
    except Exception as e:
        Output.error(str(e))


def cmd_status(args: argparse.Namespace) -> None:
    """Show firewall status."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector) if not selector.is_empty() else []
    
    if not hosts:
        die("no targets specified")
    
    password, key_path, sudo_password = get_ssh_credentials(args)
    
    for host in hosts:
        Output.header(f"Status: {host.name}")
        target = Target.from_host(host, default_user="root")
        
        try:
            client = ssh_connect(target, strict_hostkey=args.strict_hostkey, password=password, key_path=key_path)
            exit_code, stdout, stderr = ssh_exec(client, make_status_script(), sudo=True)
            client.close()
            print(stdout)
        except Exception as e:
            Output.error(str(e))


def cmd_lock(args: argparse.Namespace) -> None:
    """Lock down to minimal access."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector) if not selector.is_empty() else []
    
    if not hosts:
        die("no targets specified")
    
    Output.header("Lock Firewall (Maintenance Mode)")
    Output.warn("This will restrict to SSH only!")
    
    script = make_ufw_script("minimal")
    
    if args.dry_run:
        Output.info("Would lock:")
        for h in hosts:
            Output.step(h.name)
        return
    
    password, key_path, sudo_password = get_ssh_credentials(args)
    
    for host in hosts:
        target = Target.from_host(host, default_user="root")
        
        try:
            client = ssh_connect(target, strict_hostkey=args.strict_hostkey, password=password, key_path=key_path)
            exit_code, stdout, stderr = ssh_exec(client, script, sudo=True, password=sudo_password)
            client.close()
            
            if exit_code == 0:
                Output.success(f"Locked {host.name}")
            else:
                Output.error(f"Failed on {host.name}")
        except Exception as e:
            Output.error(f"Failed on {host.name}: {e}")


def main() -> None:
    Output.set_tool("gvfirewallctl", "Firewall baseline manager")
    
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(f"gvfirewallctl {__version__}")
        sys.exit(0)
    
    parser = argparse.ArgumentParser(
        prog=Path(sys.argv[0]).name,
        description="Apply and verify firewall baselines",
        epilog=f"""
Available roles: {', '.join(BASELINES.keys())}

Examples:
  fw apply --role web --targets webservers
  fw diff server1.example.com
  fw status --env prod
  fw lock --targets server1
        """,
    )
    parser.add_argument("--version", "-V", action="version", version=f"gvfirewallctl {__version__}")
    
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    
    apply_p = subparsers.add_parser("apply", help="apply baseline")
    apply_p.add_argument("--role", "-r", required=True, choices=list(BASELINES.keys()))
    add_target_args(apply_p)
    add_common_args(apply_p)
    
    diff_p = subparsers.add_parser("diff", help="show diff")
    diff_p.add_argument("target", help="target host")
    add_common_args(diff_p)
    
    status_p = subparsers.add_parser("status", help="show status")
    add_target_args(status_p)
    add_common_args(status_p)
    
    lock_p = subparsers.add_parser("lock", help="lock to minimal")
    add_target_args(lock_p)
    add_common_args(lock_p)
    
    args = parser.parse_args()
    apply_common_args(args)
    
    commands = {"apply": cmd_apply, "diff": cmd_diff, "status": cmd_status, "lock": cmd_lock}
    
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
