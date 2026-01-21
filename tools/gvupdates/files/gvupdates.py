#!/usr/bin/env python3
"""
gvupdates - Security updates management

Manage security updates and reporting on hosts.

Aliases: upd, gvu

Author: Gvol (gvol@nexusystems.org)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".local" / "lib" / "gvtools"))

from gvcore import (
    Output, Colors, c, die,
    Target, Inventory,
    add_common_args, add_target_args, get_selector_from_args, apply_common_args,
    ssh_connect, ssh_exec,
)

__version__ = "1.0.0"


ENABLE_SCRIPT = """
set -e
export DEBIAN_FRONTEND=noninteractive

# Install unattended-upgrades
apt-get update -qq
apt-get install -y -qq unattended-upgrades apt-listchanges

# Configure
cat > /etc/apt/apt.conf.d/20auto-upgrades << 'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF

# Enable security updates only
cat > /etc/apt/apt.conf.d/50unattended-upgrades << 'EOF'
Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}-security";
};
Unattended-Upgrade::AutoFixInterruptedDpkg "true";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
Unattended-Upgrade::Automatic-Reboot "false";
EOF

systemctl enable unattended-upgrades
systemctl restart unattended-upgrades

echo "OK: unattended-upgrades enabled"
"""

CHECK_SCRIPT = """
echo "=== PENDING UPDATES ==="
apt-get update -qq 2>/dev/null
apt-get -s upgrade 2>/dev/null | grep -E "^[0-9]+ upgraded" || echo "0 upgrades"

echo ""
echo "=== SECURITY UPDATES ==="
apt-get -s upgrade 2>/dev/null | grep -i security | head -10 || echo "None pending"

echo ""
echo "=== REBOOT REQUIRED ==="
if [ -f /var/run/reboot-required ]; then
    echo "YES - reboot required"
    cat /var/run/reboot-required.pkgs 2>/dev/null || true
else
    echo "No"
fi

echo ""
echo "=== UNATTENDED-UPGRADES STATUS ==="
systemctl is-active unattended-upgrades 2>/dev/null || echo "not installed"
"""

APPLY_SCRIPT = """
set -e
export DEBIAN_FRONTEND=noninteractive
echo "Updating package lists..."
apt-get update -qq
echo "Upgrading packages..."
apt-get upgrade -y -qq
echo "Cleaning up..."
apt-get autoremove -y -qq
apt-get autoclean -qq
echo "OK: updates applied"

if [ -f /var/run/reboot-required ]; then
    echo "WARNING: reboot required"
fi
"""


def cmd_enable(args: argparse.Namespace) -> None:
    """Enable unattended security upgrades."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector) if not selector.is_empty() else []
    
    if not hosts:
        die("no targets specified")
    
    Output.header("Enable Unattended Upgrades")
    
    if args.dry_run:
        Output.info("Would enable on:")
        for h in hosts:
            Output.step(h.name)
        return
    
    for host in hosts:
        Output.info(f"Configuring {host.name}...")
        target = Target.from_host(host, default_user="root")
        
        try:
            client = ssh_connect(target, strict_hostkey=args.strict_hostkey)
            exit_code, stdout, stderr = ssh_exec(client, ENABLE_SCRIPT, sudo=True)
            client.close()
            
            if exit_code == 0:
                Output.success(f"Enabled on {host.name}")
            else:
                Output.error(f"Failed on {host.name}: {stderr}")
        except Exception as e:
            Output.error(f"Failed on {host.name}: {e}")


def cmd_check(args: argparse.Namespace) -> None:
    """Check pending updates."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector) if not selector.is_empty() else []
    
    if not hosts:
        die("no targets specified")
    
    results = []
    
    for host in hosts:
        Output.header(f"Check: {host.name}")
        target = Target.from_host(host, default_user="root")
        
        try:
            client = ssh_connect(target, strict_hostkey=args.strict_hostkey)
            exit_code, stdout, stderr = ssh_exec(client, CHECK_SCRIPT, sudo=True)
            client.close()
            
            if Output.json_mode:
                results.append({"host": host.name, "output": stdout})
            else:
                print(stdout)
        except Exception as e:
            Output.error(str(e))
            if Output.json_mode:
                results.append({"host": host.name, "error": str(e)})
    
    if Output.json_mode:
        Output.json_output({"results": results})


def cmd_apply(args: argparse.Namespace) -> None:
    """Apply pending updates."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector) if not selector.is_empty() else []
    
    if not hosts:
        die("no targets specified")
    
    Output.header("Apply Updates")
    
    if args.dry_run:
        Output.info("Would apply updates on:")
        for h in hosts:
            Output.step(h.name)
        return
    
    for host in hosts:
        Output.info(f"Updating {host.name}...")
        target = Target.from_host(host, default_user="root")
        
        try:
            client = ssh_connect(target, strict_hostkey=args.strict_hostkey)
            exit_code, stdout, stderr = ssh_exec(client, APPLY_SCRIPT, sudo=True)
            client.close()
            
            if exit_code == 0:
                Output.success(f"Updated {host.name}")
                if "reboot required" in stdout.lower():
                    Output.warn("Reboot required")
            else:
                Output.error(f"Failed on {host.name}")
        except Exception as e:
            Output.error(f"Failed on {host.name}: {e}")


def cmd_report(args: argparse.Namespace) -> None:
    """Fleet-wide patch compliance report."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector) if not selector.is_empty() else inventory.list_all()
    
    if not hosts:
        die("no hosts in inventory")
    
    Output.header(f"Update Report ({len(hosts)} hosts)")
    
    results = []
    
    for host in hosts:
        target = Target.from_host(host, default_user="root")
        
        try:
            client = ssh_connect(target, strict_hostkey=args.strict_hostkey)
            exit_code, stdout, stderr = ssh_exec(client, CHECK_SCRIPT, sudo=True)
            client.close()
            
            # Parse results
            needs_reboot = "reboot required" in stdout.lower() and "yes" in stdout.lower()
            
            results.append({
                "host": host.name,
                "status": "ok",
                "needs_reboot": needs_reboot,
            })
        except Exception as e:
            results.append({
                "host": host.name,
                "status": "error",
                "error": str(e),
            })
    
    if Output.json_mode:
        Output.json_output({"results": results})
        return
    
    # Summary table
    headers = ["Host", "Status", "Reboot Needed"]
    rows = []
    for r in results:
        status_str = c("✔", Colors.GREEN) if r["status"] == "ok" else c("✖", Colors.RED)
        reboot_str = c("Yes", Colors.YELLOW) if r.get("needs_reboot") else "No"
        rows.append([r["host"], status_str, reboot_str])
    
    Output.table(headers, rows)


def main() -> None:
    Output.set_tool("gvupdates", "Security updates manager")
    
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(f"gvupdates {__version__}")
        sys.exit(0)
    
    parser = argparse.ArgumentParser(
        prog=Path(sys.argv[0]).name,
        description="Manage security updates and reporting",
        epilog="""
Examples:
  upd enable server1
  upd check --env prod
  upd apply --targets webservers
  upd report --json
        """,
    )
    parser.add_argument("--version", "-V", action="version", version=f"gvupdates {__version__}")
    
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    
    enable_p = subparsers.add_parser("enable", help="enable unattended upgrades")
    add_target_args(enable_p)
    add_common_args(enable_p)
    
    check_p = subparsers.add_parser("check", help="check pending updates")
    add_target_args(check_p)
    add_common_args(check_p)
    
    apply_p = subparsers.add_parser("apply", help="apply updates")
    add_target_args(apply_p)
    add_common_args(apply_p)
    
    report_p = subparsers.add_parser("report", help="compliance report")
    add_target_args(report_p)
    add_common_args(report_p)
    
    args = parser.parse_args()
    apply_common_args(args)
    
    commands = {"enable": cmd_enable, "check": cmd_check, "apply": cmd_apply, "report": cmd_report}
    
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
