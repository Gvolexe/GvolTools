#!/usr/bin/env python3
"""
gvpermcheck - Permission and ownership auditing

Audit SSH, sudo, and general file permissions.

Aliases: pc, perm, gvpc

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

__version__ = "1.1.4"


SSH_PERM_SCRIPT = """
echo "=== SSH PERMISSIONS AUDIT ==="
problems=0

check_perm() {
    path="$1"
    expected="$2"
    desc="$3"
    
    if [ -e "$path" ]; then
        actual=$(stat -c '%a' "$path" 2>/dev/null)
        owner=$(stat -c '%U' "$path" 2>/dev/null)
        
        if [ "$actual" != "$expected" ]; then
            echo "FAIL: $path is $actual, should be $expected ($desc)"
            problems=$((problems + 1))
        else
            echo "OK: $path ($actual, $owner)"
        fi
    else
        echo "SKIP: $path (not found)"
    fi
}

echo "--- User SSH ---"
for user_home in /home/* /root; do
    [ -d "$user_home/.ssh" ] || continue
    user=$(basename "$user_home")
    [ "$user" = "root" ] && user_home="/root"
    
    check_perm "$user_home/.ssh" "700" ".ssh directory"
    check_perm "$user_home/.ssh/authorized_keys" "600" "authorized_keys"
    
    for key in "$user_home/.ssh/id_*"; do
        [ -f "$key" ] && [ "${key%.pub}" = "$key" ] && check_perm "$key" "600" "private key"
    done
done

echo ""
echo "--- System SSH ---"
check_perm "/etc/ssh" "755" "sshd config dir"
check_perm "/etc/ssh/sshd_config" "600" "sshd_config"

for hostkey in /etc/ssh/ssh_host_*_key; do
    [ -f "$hostkey" ] && check_perm "$hostkey" "600" "host key"
done

echo ""
echo "Problems: $problems"
exit $problems
"""


SUDOERS_PERM_SCRIPT = """
echo "=== SUDOERS PERMISSIONS AUDIT ==="
problems=0

check_perm() {
    path="$1"
    expected="$2"
    owner="$3"
    desc="$4"
    
    if [ -e "$path" ]; then
        actual=$(stat -c '%a' "$path" 2>/dev/null)
        actual_owner=$(stat -c '%U:%G' "$path" 2>/dev/null)
        
        if [ "$actual" != "$expected" ]; then
            echo "FAIL: $path is $actual, should be $expected"
            problems=$((problems + 1))
        elif [ -n "$owner" ] && [ "$actual_owner" != "$owner" ]; then
            echo "FAIL: $path owned by $actual_owner, should be $owner"
            problems=$((problems + 1))
        else
            echo "OK: $path ($actual, $actual_owner)"
        fi
    fi
}

check_perm "/etc/sudoers" "440" "root:root" "main sudoers"

if [ -d /etc/sudoers.d ]; then
    check_perm "/etc/sudoers.d" "755" "root:root" "sudoers.d"
    
    for f in /etc/sudoers.d/*; do
        [ -f "$f" ] && check_perm "$f" "440" "root:root" "sudoers.d file"
    done
fi

echo ""
echo "--- Syntax Check ---"
if command -v visudo >/dev/null 2>&1; then
    if visudo -c 2>&1; then
        echo "OK: sudoers syntax valid"
    else
        problems=$((problems + 1))
    fi
fi

echo ""
echo "Problems: $problems"
exit $problems
"""


PATHS_PERM_SCRIPT = """
echo "=== CRITICAL PATHS AUDIT ==="
problems=0

check_perm() {
    path="$1"
    max_perm="$2"
    desc="$3"
    
    if [ -e "$path" ]; then
        actual=$(stat -c '%a' "$path" 2>/dev/null)
        owner=$(stat -c '%U:%G' "$path" 2>/dev/null)
        
        # Check if world-writable
        if [ $((actual & 002)) -ne 0 ]; then
            echo "FAIL: $path is world-writable ($actual)"
            problems=$((problems + 1))
        else
            echo "OK: $path ($actual, $owner)"
        fi
    fi
}

echo "--- Sensitive Files ---"
check_perm "/etc/passwd" "644" "passwd"
check_perm "/etc/shadow" "640" "shadow" 
check_perm "/etc/group" "644" "group"
check_perm "/etc/gshadow" "640" "gshadow"

echo ""
echo "--- System Dirs ---"
check_perm "/tmp" "1777" "tmp"
check_perm "/var/tmp" "1777" "var/tmp"

echo ""
echo "--- World-Writable Search ---"
ww_count=$(find /etc -perm -002 -type f 2>/dev/null | wc -l)
echo "World-writable files in /etc: $ww_count"
[ "$ww_count" -gt 0 ] && problems=$((problems + ww_count))

echo ""
echo "--- SUID Binaries ---"
suid_count=$(find /usr -perm -4000 -type f 2>/dev/null | wc -l)
echo "SUID binaries in /usr: $suid_count"

echo ""
echo "Problems: $problems"
exit $problems
"""


def cmd_ssh(args: argparse.Namespace) -> None:
    """Audit SSH permissions."""
    target_str = args.target
    
    target = Target.parse(target_str)
    if not target.user:
        target.user = "root"
    
    Output.header(f"SSH Permission Audit: {target.host}")
    
    try:
        client = ssh_connect(target, strict_hostkey=args.strict_hostkey)
        exit_code, stdout, stderr = ssh_exec(client, SSH_PERM_SCRIPT, sudo=True)
        client.close()
        
        print(stdout)
        
        if exit_code == 0:
            Output.success("All SSH permissions OK")
        else:
            Output.warn(f"{exit_code} issue(s) found")
            
    except Exception as e:
        Output.error(str(e))


def cmd_sudoers(args: argparse.Namespace) -> None:
    """Audit sudoers permissions."""
    target_str = args.target
    
    target = Target.parse(target_str)
    if not target.user:
        target.user = "root"
    
    Output.header(f"Sudoers Audit: {target.host}")
    
    try:
        client = ssh_connect(target, strict_hostkey=args.strict_hostkey)
        exit_code, stdout, stderr = ssh_exec(client, SUDOERS_PERM_SCRIPT, sudo=True)
        client.close()
        
        print(stdout)
        
        if exit_code == 0:
            Output.success("All sudoers permissions OK")
        else:
            Output.warn(f"{exit_code} issue(s) found")
            
    except Exception as e:
        Output.error(str(e))


def cmd_paths(args: argparse.Namespace) -> None:
    """Audit critical path permissions."""
    target_str = args.target
    
    target = Target.parse(target_str)
    if not target.user:
        target.user = "root"
    
    Output.header(f"Path Permissions Audit: {target.host}")
    
    try:
        client = ssh_connect(target, strict_hostkey=args.strict_hostkey)
        exit_code, stdout, stderr = ssh_exec(client, PATHS_PERM_SCRIPT, sudo=True)
        client.close()
        
        print(stdout)
        
        if exit_code == 0:
            Output.success("All path permissions OK")
        else:
            Output.warn(f"{exit_code} issue(s) found")
            
    except Exception as e:
        Output.error(str(e))


def cmd_report(args: argparse.Namespace) -> None:
    """Full permission report."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector) if not selector.is_empty() else []
    
    if not hosts:
        die("no targets specified")
    
    Output.header(f"Permission Report ({len(hosts)} hosts)")
    
    results = []
    headers = ["Host", "SSH", "Sudoers", "Paths"]
    rows = []
    
    full_script = f"""
ssh_problems=0
{SSH_PERM_SCRIPT} 2>/dev/null | tail -1 | grep -o '[0-9]*' | head -1 || echo 0

sudo_problems=0
{SUDOERS_PERM_SCRIPT} 2>/dev/null | tail -1 | grep -o '[0-9]*' | head -1 || echo 0

path_problems=0
{PATHS_PERM_SCRIPT} 2>/dev/null | tail -1 | grep -o '[0-9]*' | head -1 || echo 0
"""
    
    check_script = """
ssh_p=$( (
    problems=0
    for user_home in /home/* /root; do
        [ -d "$user_home/.ssh" ] || continue
        ssh_dir_perm=$(stat -c '%a' "$user_home/.ssh" 2>/dev/null)
        [ "$ssh_dir_perm" != "700" ] && problems=$((problems + 1))
    done
    echo $problems
) )

sudo_p=$( (
    problems=0
    sudo_perm=$(stat -c '%a' /etc/sudoers 2>/dev/null)
    [ "$sudo_perm" != "440" ] && problems=$((problems + 1))
    echo $problems
) )

path_p=$( (
    find /etc -perm -002 -type f 2>/dev/null | wc -l
) )

echo "$ssh_p $sudo_p $path_p"
"""
    
    for host in hosts:
        target = Target.from_host(host, default_user="root")
        
        try:
            client = ssh_connect(target, strict_hostkey=args.strict_hostkey)
            exit_code, stdout, stderr = ssh_exec(client, check_script, sudo=True)
            client.close()
            
            parts = stdout.strip().split()
            ssh_issues = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 0
            sudo_issues = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
            path_issues = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
            
            rows.append([
                c(host.name, Colors.CYAN),
                c("✓", Colors.GREEN) if ssh_issues == 0 else c(str(ssh_issues), Colors.RED),
                c("✓", Colors.GREEN) if sudo_issues == 0 else c(str(sudo_issues), Colors.RED),
                c("✓", Colors.GREEN) if path_issues == 0 else c(str(path_issues), Colors.YELLOW),
            ])
            
            results.append({
                "host": host.name,
                "ssh_issues": ssh_issues,
                "sudo_issues": sudo_issues,
                "path_issues": path_issues,
            })
            
        except Exception as e:
            rows.append([
                c(host.name, Colors.CYAN),
                c("?", Colors.RED),
                c("?", Colors.RED),
                c("?", Colors.RED),
            ])
            results.append({"host": host.name, "error": str(e)})
    
    if Output.json_mode:
        Output.json_output({"hosts": results})
    else:
        Output.table(headers, rows)


def main() -> None:
    Output.set_tool("gvpermcheck", "Permission auditor")
    
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(f"gvpermcheck {__version__}")
        sys.exit(0)
    
    parser = argparse.ArgumentParser(
        prog=Path(sys.argv[0]).name,
        description="Permission and ownership auditing",
        epilog="""
Examples:
  pc ssh server1
  pc sudoers server1
  pc paths server1
  pc report --env prod --json
        """,
    )
    parser.add_argument("--version", "-V", action="version", version=f"gvpermcheck {__version__}")
    
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    
    ssh_p = subparsers.add_parser("ssh", help="audit SSH permissions")
    ssh_p.add_argument("target", help="target host")
    add_common_args(ssh_p)
    
    sudoers_p = subparsers.add_parser("sudoers", help="audit sudoers permissions")
    sudoers_p.add_argument("target", help="target host")
    add_common_args(sudoers_p)
    
    paths_p = subparsers.add_parser("paths", help="audit path permissions")
    paths_p.add_argument("target", help="target host")
    add_common_args(paths_p)
    
    report_p = subparsers.add_parser("report", help="full report")
    add_target_args(report_p)
    add_common_args(report_p)
    
    args = parser.parse_args()
    apply_common_args(args)
    
    commands = {
        "ssh": cmd_ssh,
        "sudoers": cmd_sudoers,
        "paths": cmd_paths,
        "report": cmd_report,
    }
    
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
