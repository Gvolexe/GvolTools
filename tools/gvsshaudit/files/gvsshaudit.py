#!/usr/bin/env python3
"""
gvsshaudit - Audit SSH server config and access

Audit SSH configuration for security issues:
- Local client config and permissions
- Remote sshd config and key permissions
- Fleet-wide audits with aggregation

Aliases: sa, sshaudit, gvsa

Author: Gvol (gvol@nexusystems.org)
"""

from __future__ import annotations

import argparse
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".local" / "lib" / "gvtools"))

from gvcore import (
    Output, Colors, c, die,
    Target, Inventory,
    add_common_args, add_target_args, get_selector_from_args, apply_common_args,
    ssh_connect, ssh_exec, get_ssh_credentials,
)

__version__ = "1.2.1"


# ─────────────────────────────────────────────────────────────────────────────
# Audit Checks
# ─────────────────────────────────────────────────────────────────────────────

def check_file_perms(path: Path, expected: int, desc: str) -> dict:
    """Check file permissions."""
    if not path.exists():
        return {"path": str(path), "status": "missing", "severity": "info", "desc": desc}
    
    actual = stat.S_IMODE(path.stat().st_mode)
    if actual == expected:
        return {"path": str(path), "status": "ok", "mode": oct(actual), "desc": desc}
    
    severity = "high" if actual & 0o077 else "medium"
    return {
        "path": str(path),
        "status": "bad",
        "expected": oct(expected),
        "actual": oct(actual),
        "severity": severity,
        "desc": desc,
    }


def audit_local() -> list[dict]:
    """Audit local SSH client configuration."""
    findings = []
    ssh_dir = Path.home() / ".ssh"
    
    # Check .ssh directory
    findings.append(check_file_perms(ssh_dir, 0o700, ".ssh directory"))
    
    # Check known_hosts
    findings.append(check_file_perms(ssh_dir / "known_hosts", 0o644, "known_hosts"))
    
    # Check authorized_keys
    findings.append(check_file_perms(ssh_dir / "authorized_keys", 0o600, "authorized_keys"))
    
    # Check private keys
    for key_file in ssh_dir.glob("id_*"):
        if not key_file.name.endswith(".pub"):
            findings.append(check_file_perms(key_file, 0o600, f"private key: {key_file.name}"))
    
    # Check config
    config = ssh_dir / "config"
    if config.exists():
        findings.append(check_file_perms(config, 0o600, "SSH config"))
    
    return findings


REMOTE_AUDIT_SCRIPT = """
echo "=== SSHD CONFIG ==="
for opt in PermitRootLogin PasswordAuthentication PubkeyAuthentication ChallengeResponseAuthentication X11Forwarding MaxAuthTries LoginGraceTime; do
    val=$(grep -E "^$opt" /etc/ssh/sshd_config 2>/dev/null | head -1 | awk '{print $2}')
    echo "$opt: ${val:-default}"
done

echo ""
echo "=== FILE PERMISSIONS ==="
for f in /etc/ssh/sshd_config /etc/ssh/ssh_host_*_key; do
    if [ -f "$f" ]; then
        perm=$(stat -c "%a" "$f" 2>/dev/null)
        echo "$f: $perm"
    fi
done

echo ""
echo "=== AUTH METHODS ==="
if command -v sshd >/dev/null 2>&1; then
    sshd -T 2>/dev/null | grep -E "^(passwordauthentication|pubkeyauthentication|permitrootlogin)" || echo "Could not query sshd"
fi
"""


def audit_remote(target: Target, strict_hostkey: bool = False, password: str = "", key_path: str = "") -> dict:
    """Audit remote SSH server."""
    try:
        client = ssh_connect(target, password=password, key_path=key_path, strict_hostkey=strict_hostkey)
        exit_code, stdout, stderr = ssh_exec(client, REMOTE_AUDIT_SCRIPT, sudo=True, password=sudo_password)
        client.close()
        
        return {"host": target.host, "status": "ok", "output": stdout}
    except Exception as e:
        return {"host": target.host, "status": "error", "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

def cmd_local(args: argparse.Namespace) -> None:
    """Audit local SSH client configuration."""
    Output.header("Local SSH Audit")
    
    findings = audit_local()
    
    if Output.json_mode:
        Output.json_output({"findings": findings})
        return
    
    issues = 0
    for f in findings:
        status = f["status"]
        path = f["path"]
        
        if status == "ok":
            Output.success(f"{f['desc']}: {c(f['mode'], Colors.GREEN)}")
        elif status == "missing":
            Output.step(f"{f['desc']}: {c('not found', Colors.DIM)}")
        else:
            issues += 1
            severity = f.get("severity", "medium")
            sev_color = Colors.RED if severity == "high" else Colors.YELLOW
            Output.warn(f"{f['desc']}: {c(f['actual'], sev_color)} (expected {f['expected']})")
    
    Output.divider()
    if issues == 0:
        Output.success("All checks passed")
    else:
        Output.warn(f"{issues} issue(s) found")


def cmd_remote(args: argparse.Namespace) -> None:
    """Audit remote SSH server."""
    target = args.target
    if not target:
        die("target is required")
    
    t = Target.parse(target)
    if not t.user:
        t.user = "root"
    
    password, key_path, sudo_password = get_ssh_credentials(args)
    
    Output.header(f"Remote SSH Audit: {t.host}")
    
    result = audit_remote(t, strict_hostkey=args.strict_hostkey, password=password, key_path=key_path)
    
    if Output.json_mode:
        Output.json_output(result)
        return
    
    if result["status"] == "error":
        Output.error(result["error"])
        return
    
    print(result["output"])


def cmd_fleet(args: argparse.Namespace) -> None:
    """Run audit across fleet and aggregate."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    
    hosts = inventory.select(selector) if not selector.is_empty() else inventory.list_all()
    
    if not hosts:
        die("no hosts in inventory")
    
    password, key_path, sudo_password = get_ssh_credentials(args)
    
    Output.header(f"Fleet SSH Audit ({len(hosts)} hosts)")
    
    results = []
    for host in hosts:
        Output.info(f"Auditing {host.name}...")
        target = Target.from_host(host, default_user=host.user or "root")
        result = audit_remote(target, strict_hostkey=args.strict_hostkey, password=password, key_path=key_path)
        results.append(result)
    
    if Output.json_mode:
        Output.json_output({"results": results})
        return
    
    # Summary
    ok = sum(1 for r in results if r["status"] == "ok")
    errors = sum(1 for r in results if r["status"] == "error")
    
    Output.divider()
    Output.success(f"Completed: {ok}/{len(hosts)} successful")
    if errors:
        Output.warn(f"Errors: {errors}")


def cmd_report(args: argparse.Namespace) -> None:
    """Generate detailed audit report."""
    # Same as remote but with more formatting
    cmd_remote(args)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    Output.set_tool("gvsshaudit", "SSH configuration auditor")
    
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(f"gvsshaudit {__version__}")
        sys.exit(0)
    
    parser = argparse.ArgumentParser(
        prog=Path(sys.argv[0]).name,
        description="Audit SSH server config and access",
        epilog="""
Examples:
  sa local
  sa remote root@server
  sa fleet --env prod
  sa report user@host --json
        """,
    )
    parser.add_argument("--version", "-V", action="version", version=f"gvsshaudit {__version__}")
    
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    
    # local
    local_p = subparsers.add_parser("local", help="audit local SSH client")
    add_common_args(local_p)
    
    # remote
    remote_p = subparsers.add_parser("remote", help="audit remote SSH server")
    remote_p.add_argument("target", help="target: user@host[:port]")
    add_common_args(remote_p)
    
    # fleet
    fleet_p = subparsers.add_parser("fleet", help="audit fleet")
    add_target_args(fleet_p)
    add_common_args(fleet_p)
    
    # report
    report_p = subparsers.add_parser("report", help="detailed report")
    report_p.add_argument("target", help="target: user@host[:port]")
    report_p.add_argument("--format", choices=["text", "json"], default="text")
    add_common_args(report_p)
    
    args = parser.parse_args()
    apply_common_args(args)
    
    commands = {"local": cmd_local, "remote": cmd_remote, "fleet": cmd_fleet, "report": cmd_report}
    
    if args.command in commands:
        commands[args.command](args)
    elif not args.command:
        cmd_local(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
