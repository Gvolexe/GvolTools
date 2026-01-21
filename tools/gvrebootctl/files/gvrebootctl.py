#!/usr/bin/env python3
"""
gvrebootctl - Reboot coordination and validation for fleet hosts

Detect whether hosts require a reboot, coordinate safe reboots across target sets,
and validate that critical services return healthy post-reboot.

Aliases: reboot, rb

Author: Gvol (gvol@nexusystems.org)
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".local" / "lib" / "gvtools"))

from gvcore import (
    __version__,
    Output, Colors, c, die,
    Host, Inventory, Target,
    SSHProfileManager,
    add_common_args, add_target_args, get_selector_from_args, apply_common_args,
    confirm, ssh_connect, ssh_exec, get_ssh_credentials,
)


# ─────────────────────────────────────────────────────────────────────────────
# Reboot Detection
# ─────────────────────────────────────────────────────────────────────────────

REBOOT_CHECK_SCRIPT = """
#!/bin/sh
# Detect if reboot is required across distros

NEEDS_REBOOT=0
REASONS=""

# Debian/Ubuntu: check reboot-required file
if [ -f /var/run/reboot-required ]; then
    NEEDS_REBOOT=1
    REASONS="${REASONS}reboot-required file exists,"
    if [ -f /var/run/reboot-required.pkgs ]; then
        PKGS=$(cat /var/run/reboot-required.pkgs | tr '\\n' ' ')
        REASONS="${REASONS}packages: ${PKGS},"
    fi
fi

# Check for kernel upgrade (compare running vs installed)
RUNNING_KERNEL=$(uname -r)
if command -v rpm >/dev/null 2>&1; then
    # RHEL/Fedora
    INSTALLED_KERNEL=$(rpm -q kernel --qf '%{VERSION}-%{RELEASE}.%{ARCH}\\n' 2>/dev/null | tail -1)
elif command -v dpkg >/dev/null 2>&1; then
    # Debian/Ubuntu  
    INSTALLED_KERNEL=$(dpkg -l 'linux-image-*' 2>/dev/null | grep '^ii' | awk '{print $2}' | sed 's/linux-image-//' | sort -V | tail -1)
elif [ -f /boot/vmlinuz ]; then
    # Arch
    INSTALLED_KERNEL=$(file /boot/vmlinuz 2>/dev/null | grep -oP 'version \\K[0-9]+\\.[0-9]+\\.[0-9]+[^ ]*' || echo "")
fi

if [ -n "$INSTALLED_KERNEL" ] && [ "$INSTALLED_KERNEL" != "$RUNNING_KERNEL" ]; then
    # Only flag if versions differ significantly
    if ! echo "$INSTALLED_KERNEL" | grep -q "$RUNNING_KERNEL"; then
        NEEDS_REBOOT=1
        REASONS="${REASONS}kernel: running=$RUNNING_KERNEL installed=$INSTALLED_KERNEL,"
    fi
fi

# Check for libc update (processes using old libc)
if command -v lsof >/dev/null 2>&1; then
    OLD_LIBC=$(lsof 2>/dev/null | grep -c 'libc.*DEL' || echo "0")
    if [ "$OLD_LIBC" -gt "0" ]; then
        NEEDS_REBOOT=1
        REASONS="${REASONS}libc: $OLD_LIBC processes using deleted libc,"
    fi
fi

# Check systemd hints
if command -v systemctl >/dev/null 2>&1; then
    if systemctl is-system-running 2>/dev/null | grep -q 'degraded'; then
        REASONS="${REASONS}systemd: degraded state,"
    fi
fi

# Get last boot time
LAST_BOOT=$(uptime -s 2>/dev/null || who -b 2>/dev/null | awk '{print $3, $4}')

# Output JSON
REASONS=$(echo "$REASONS" | sed 's/,$//')
echo "{"
echo "  \\"needs_reboot\\": $NEEDS_REBOOT,"
echo "  \\"reasons\\": \\"$REASONS\\","
echo "  \\"running_kernel\\": \\"$RUNNING_KERNEL\\","
echo "  \\"last_boot\\": \\"$LAST_BOOT\\","
echo "  \\"hostname\\": \\"$(hostname)\\""
echo "}"
"""

REBOOT_SCRIPT = """
#!/bin/sh
# Initiate system reboot
echo "Initiating reboot..."
nohup sh -c 'sleep 2 && reboot' >/dev/null 2>&1 &
echo '{"status": "reboot_initiated"}'
"""

VALIDATE_SCRIPT = """
#!/bin/sh
# Validate services are running
SERVICES="$1"
FAILED=""
OK=""

if [ -z "$SERVICES" ]; then
    SERVICES="sshd ssh"
fi

for svc in $SERVICES; do
    if systemctl is-active "$svc" >/dev/null 2>&1; then
        OK="${OK}${svc},"
    else
        FAILED="${FAILED}${svc},"
    fi
done

OK=$(echo "$OK" | sed 's/,$//')
FAILED=$(echo "$FAILED" | sed 's/,$//')

echo "{"
echo "  \\"ok_services\\": \\"$OK\\","
echo "  \\"failed_services\\": \\"$FAILED\\","
echo "  \\"hostname\\": \\"$(hostname)\\""
echo "}"
"""


@dataclass
class RebootStatus:
    """Reboot status for a host."""
    host: str
    needs_reboot: bool = False
    reasons: list[str] = field(default_factory=list)
    running_kernel: str = ""
    last_boot: str = ""
    reboot_time: str = ""
    validation_status: str = ""
    error: str = ""
    
    def to_dict(self) -> dict:
        return {
            "host": self.host,
            "needs_reboot": self.needs_reboot,
            "reasons": self.reasons,
            "running_kernel": self.running_kernel,
            "last_boot": self.last_boot,
            "reboot_time": self.reboot_time,
            "validation_status": self.validation_status,
            "error": self.error,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────

def is_localhost(host: str) -> bool:
    """Check if host is the local machine."""
    local_names = {"localhost", "127.0.0.1", "::1"}
    if host.lower() in local_names:
        return True
    try:
        local_hostname = socket.gethostname()
        local_fqdn = socket.getfqdn()
        if host.lower() in (local_hostname.lower(), local_fqdn.lower()):
            return True
    except Exception:
        pass
    return False


def wait_for_ssh_down(host: str, port: int, timeout: int = 60) -> bool:
    """Wait for SSH to become unavailable (host rebooting)."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((host, port))
            sock.close()
            if result != 0:
                return True  # SSH is down
        except Exception:
            return True
        time.sleep(1)
    return False


def wait_for_ssh_up(host: str, port: int, timeout: int = 300) -> bool:
    """Wait for SSH to become available (host back up)."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                # SSH port is open, wait a bit for sshd to be fully ready
                time.sleep(3)
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

def cmd_check(args: argparse.Namespace) -> None:
    """Check if hosts need reboot."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if not hosts:
        die("no hosts matched selector")
    
    password, key_path, sudo_pass = get_ssh_credentials(args)
    results = []
    
    for host in hosts:
        target = Target.from_host(host, default_user=host.user or "root")
        status = RebootStatus(host=host.name)
        
        try:
            Output.info(f"Checking {c(host.name, Colors.CYAN)}...")
            client = ssh_connect(
                target,
                password=password,
                key_path=key_path,
                timeout=getattr(args, "timeout", 15),
            )
            
            code, out, err = ssh_exec(client, REBOOT_CHECK_SCRIPT, sudo=True, password=sudo_pass or password)
            client.close()
            
            if code == 0:
                try:
                    data = json.loads(out)
                    status.needs_reboot = bool(data.get("needs_reboot", 0))
                    reasons = data.get("reasons", "")
                    status.reasons = [r.strip() for r in reasons.split(",") if r.strip()]
                    status.running_kernel = data.get("running_kernel", "")
                    status.last_boot = data.get("last_boot", "")
                except json.JSONDecodeError:
                    status.error = f"invalid output: {out[:100]}"
            else:
                status.error = f"exit code {code}: {err[:100]}"
        
        except Exception as e:
            status.error = str(e)
        
        results.append(status)
    
    if Output.json_mode:
        Output.json_output({"hosts": [r.to_dict() for r in results]})
        return
    
    Output.header(f"Reboot Check ({len(results)} hosts)")
    
    headers = ["Host", "Needs Reboot", "Reasons", "Kernel", "Last Boot"]
    rows = []
    for r in results:
        if r.error:
            reboot_str = c("ERROR", Colors.RED)
            reasons_str = r.error[:30]
        else:
            reboot_str = c("YES", Colors.YELLOW) if r.needs_reboot else c("NO", Colors.GREEN)
            reasons_str = "; ".join(r.reasons)[:40] if r.reasons else "-"
        rows.append([
            c(r.host, Colors.CYAN),
            reboot_str,
            reasons_str,
            r.running_kernel or "-",
            r.last_boot or "-",
        ])
    
    Output.table(headers, rows)


def cmd_plan(args: argparse.Namespace) -> None:
    """Generate a reboot plan."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if not hosts:
        die("no hosts matched selector")
    
    batch_size = getattr(args, "batch_size", 1) or 1
    interval = getattr(args, "interval", 60) or 60
    order = getattr(args, "order", "host") or "host"
    
    # Sort hosts
    if order == "role":
        hosts = sorted(hosts, key=lambda h: (h.roles[0] if h.roles else "", h.name))
    elif order == "random":
        import random
        random.shuffle(hosts)
    else:  # host
        hosts = sorted(hosts, key=lambda h: h.name)
    
    # Create batches
    batches = []
    for i in range(0, len(hosts), batch_size):
        batch = hosts[i:i + batch_size]
        batches.append({
            "batch": len(batches) + 1,
            "hosts": [h.name for h in batch],
            "interval_after": interval if i + batch_size < len(hosts) else 0,
        })
    
    plan = {
        "total_hosts": len(hosts),
        "batch_size": batch_size,
        "interval_seconds": interval,
        "order": order,
        "batches": batches,
    }
    
    if Output.json_mode:
        Output.json_output(plan)
        return
    
    Output.header("Reboot Plan")
    Output.keyvalue("Total hosts", str(len(hosts)))
    Output.keyvalue("Batch size", str(batch_size))
    Output.keyvalue("Interval", f"{interval}s")
    Output.keyvalue("Order", order)
    print()
    
    for batch in batches:
        hosts_str = ", ".join(batch["hosts"])
        Output.info(f"Batch {batch['batch']}: {c(hosts_str, Colors.CYAN)}")
        if batch["interval_after"]:
            Output.step(f"Wait {batch['interval_after']}s after")


def cmd_run(args: argparse.Namespace) -> None:
    """Execute reboot plan."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if not hosts:
        die("no hosts matched selector")
    
    batch_size = getattr(args, "batch_size", 1) or 1
    interval = getattr(args, "interval", 60) or 60
    timeout = getattr(args, "timeout", 600) or 600
    dry_run = getattr(args, "dry_run", False)
    
    # Safety: never reboot localhost unless explicitly targeted
    local_hosts = [h for h in hosts if is_localhost(h.effective_address)]
    if local_hosts:
        Output.warn(f"Local machine ({local_hosts[0].name}) is in target set!")
        if not getattr(args, "yes", False):
            if not confirm("Reboot local machine?"):
                die("cancelled")
    
    if not dry_run and not getattr(args, "yes", False):
        if not confirm(f"Reboot {len(hosts)} host(s)?"):
            die("cancelled")
    
    password, key_path, sudo_pass = get_ssh_credentials(args)
    results = []
    
    # Sort and batch
    hosts = sorted(hosts, key=lambda h: h.name)
    
    for i in range(0, len(hosts), batch_size):
        batch = hosts[i:i + batch_size]
        
        Output.header(f"Batch {i // batch_size + 1}")
        
        for host in batch:
            target = Target.from_host(host, default_user=host.user or "root")
            status = RebootStatus(host=host.name)
            
            if dry_run:
                Output.info(f"[DRY-RUN] Would reboot {c(host.name, Colors.CYAN)}")
                status.validation_status = "dry-run"
                results.append(status)
                continue
            
            try:
                Output.info(f"Rebooting {c(host.name, Colors.CYAN)}...")
                client = ssh_connect(
                    target,
                    password=password,
                    key_path=key_path,
                    timeout=15,
                )
                
                # Issue reboot
                ssh_exec(client, REBOOT_SCRIPT, sudo=True, password=sudo_pass or password)
                client.close()
                
                status.reboot_time = time.strftime("%Y-%m-%d %H:%M:%S")
                
                # Wait for SSH to go down
                Output.step("Waiting for host to go down...")
                if not wait_for_ssh_down(host.effective_address, host.port, timeout=60):
                    Output.warn("Host did not go down - may not have rebooted")
                
                # Wait for SSH to come back
                Output.step("Waiting for host to come back...")
                if not wait_for_ssh_up(host.effective_address, host.port, timeout=timeout):
                    status.error = "FAILED_UNREACHABLE"
                    status.validation_status = "failed"
                    Output.error(f"Host did not come back within {timeout}s")
                    if not getattr(args, "continue_on_fail", False):
                        die("stopping due to unreachable host")
                else:
                    # Validate
                    Output.step("Validating services...")
                    try:
                        client = ssh_connect(
                            target,
                            password=password,
                            key_path=key_path,
                            timeout=30,
                        )
                        services = getattr(args, "services", "") or "sshd"
                        code, out, err = ssh_exec(client, f'{VALIDATE_SCRIPT} "{services}"')
                        client.close()
                        
                        if code == 0:
                            try:
                                data = json.loads(out)
                                failed = data.get("failed_services", "")
                                if failed:
                                    status.validation_status = f"degraded: {failed}"
                                    Output.warn(f"Some services failed: {failed}")
                                else:
                                    status.validation_status = "healthy"
                                    Output.success(f"{host.name} is healthy")
                            except json.JSONDecodeError:
                                status.validation_status = "unknown"
                        else:
                            status.validation_status = f"error: {err[:50]}"
                    except Exception as e:
                        status.validation_status = f"error: {e}"
            
            except Exception as e:
                status.error = str(e)
                Output.error(f"Failed: {e}")
            
            results.append(status)
        
        # Wait between batches
        if i + batch_size < len(hosts) and not dry_run:
            Output.info(f"Waiting {interval}s before next batch...")
            time.sleep(interval)
    
    if Output.json_mode:
        Output.json_output({"results": [r.to_dict() for r in results]})
        return
    
    Output.header("Reboot Summary")
    headers = ["Host", "Status", "Reboot Time", "Validation"]
    rows = []
    for r in results:
        if r.error:
            status = c("FAILED", Colors.RED)
        elif r.validation_status == "healthy":
            status = c("OK", Colors.GREEN)
        elif r.validation_status == "dry-run":
            status = c("DRY-RUN", Colors.YELLOW)
        else:
            status = c("DEGRADED", Colors.YELLOW)
        rows.append([
            c(r.host, Colors.CYAN),
            status,
            r.reboot_time or "-",
            r.validation_status or "-",
        ])
    Output.table(headers, rows)


def cmd_validate(args: argparse.Namespace) -> None:
    """Validate services on hosts (no reboot)."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if not hosts:
        die("no hosts matched selector")
    
    password, key_path, sudo_pass = get_ssh_credentials(args)
    services = getattr(args, "services", "") or "sshd"
    endpoints = getattr(args, "endpoints", "") or ""
    results = []
    
    for host in hosts:
        target = Target.from_host(host, default_user=host.user or "root")
        result = {"host": host.name, "services": {}, "endpoints": {}, "error": ""}
        
        try:
            Output.info(f"Validating {c(host.name, Colors.CYAN)}...")
            client = ssh_connect(
                target,
                password=password,
                key_path=key_path,
                timeout=getattr(args, "timeout", 15),
            )
            
            code, out, err = ssh_exec(client, f'{VALIDATE_SCRIPT} "{services}"')
            client.close()
            
            if code == 0:
                try:
                    data = json.loads(out)
                    for svc in (data.get("ok_services") or "").split(","):
                        if svc.strip():
                            result["services"][svc.strip()] = "ok"
                    for svc in (data.get("failed_services") or "").split(","):
                        if svc.strip():
                            result["services"][svc.strip()] = "failed"
                except json.JSONDecodeError:
                    result["error"] = f"invalid output: {out[:50]}"
            else:
                result["error"] = f"exit {code}: {err[:50]}"
            
            # Check endpoints if specified
            if endpoints:
                for endpoint in endpoints.split(","):
                    endpoint = endpoint.strip()
                    if not endpoint:
                        continue
                    # Use curl on remote host
                    check_cmd = f'curl -sf -o /dev/null -w "%{{http_code}}" --connect-timeout 5 {endpoint}'
                    code, out, err = ssh_exec(client, check_cmd)
                    if code == 0 and out.strip() in ("200", "201", "204"):
                        result["endpoints"][endpoint] = "ok"
                    else:
                        result["endpoints"][endpoint] = f"failed: {out.strip()}"
        
        except Exception as e:
            result["error"] = str(e)
        
        results.append(result)
    
    if Output.json_mode:
        Output.json_output({"results": results})
        return
    
    Output.header(f"Validation Results ({len(results)} hosts)")
    for r in results:
        host_color = Colors.GREEN if not r["error"] else Colors.RED
        Output.info(f"{c(r['host'], host_color)}")
        if r["error"]:
            Output.step(f"Error: {r['error']}")
        for svc, status in r["services"].items():
            status_color = Colors.GREEN if status == "ok" else Colors.RED
            Output.step(f"Service {svc}: {c(status, status_color)}")
        for ep, status in r["endpoints"].items():
            status_color = Colors.GREEN if status == "ok" else Colors.RED
            Output.step(f"Endpoint {ep}: {c(status, status_color)}")


def cmd_cancel(args: argparse.Namespace) -> None:
    """Cancel pending scheduled reboots."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if not hosts:
        die("no hosts matched selector")
    
    password, key_path, sudo_pass = get_ssh_credentials(args)
    results = []
    
    cancel_script = """
#!/bin/sh
# Cancel pending shutdown/reboot
if command -v shutdown >/dev/null 2>&1; then
    shutdown -c 2>/dev/null && echo '{"cancelled": true}' || echo '{"cancelled": false, "reason": "no pending shutdown"}'
else
    echo '{"cancelled": false, "reason": "shutdown command not found"}'
fi
"""
    
    for host in hosts:
        target = Target.from_host(host, default_user=host.user or "root")
        result = {"host": host.name, "cancelled": False, "error": ""}
        
        try:
            Output.info(f"Cancelling on {c(host.name, Colors.CYAN)}...")
            client = ssh_connect(
                target,
                password=password,
                key_path=key_path,
                timeout=getattr(args, "timeout", 15),
            )
            
            code, out, err = ssh_exec(client, cancel_script, sudo=True, password=sudo_pass or password)
            client.close()
            
            if code == 0:
                try:
                    data = json.loads(out)
                    result["cancelled"] = data.get("cancelled", False)
                    if not result["cancelled"]:
                        result["error"] = data.get("reason", "unknown")
                except json.JSONDecodeError:
                    result["error"] = f"invalid output: {out[:50]}"
            else:
                result["error"] = f"exit {code}"
        
        except Exception as e:
            result["error"] = str(e)
        
        results.append(result)
    
    if Output.json_mode:
        Output.json_output({"results": results})
        return
    
    for r in results:
        if r["cancelled"]:
            Output.success(f"Cancelled shutdown on {r['host']}")
        else:
            Output.warn(f"Could not cancel on {r['host']}: {r['error']}")


# ─────────────────────────────────────────────────────────────────────────────
# Parser Setup
# ─────────────────────────────────────────────────────────────────────────────

def setup_check_parser(parser: argparse.ArgumentParser) -> None:
    add_target_args(parser)
    parser.add_argument("--reasons", action="store_true", help="show detailed reasons")
    add_common_args(parser)


def setup_plan_parser(parser: argparse.ArgumentParser) -> None:
    add_target_args(parser)
    parser.add_argument("--batch-size", "-b", type=int, default=1, help="hosts per batch (default: 1)")
    parser.add_argument("--interval", type=int, default=60, help="seconds between batches (default: 60)")
    parser.add_argument("--order", choices=["role", "host", "random"], default="host", help="ordering")
    add_common_args(parser)


def setup_run_parser(parser: argparse.ArgumentParser) -> None:
    add_target_args(parser)
    parser.add_argument("--batch-size", "-b", type=int, default=1, help="hosts per batch (default: 1)")
    parser.add_argument("--interval", type=int, default=60, help="seconds between batches")
    parser.add_argument("--services", help="comma-separated services to validate")
    parser.add_argument("--continue-on-fail", action="store_true", help="continue if host fails to come back")
    add_common_args(parser)


def setup_validate_parser(parser: argparse.ArgumentParser) -> None:
    add_target_args(parser)
    parser.add_argument("--services", help="comma-separated services to check")
    parser.add_argument("--endpoints", help="comma-separated HTTP endpoints to check")
    add_common_args(parser)


def setup_cancel_parser(parser: argparse.ArgumentParser) -> None:
    add_target_args(parser)
    add_common_args(parser)


cmd_check.setup_parser = setup_check_parser  # type: ignore
cmd_plan.setup_parser = setup_plan_parser  # type: ignore
cmd_run.setup_parser = setup_run_parser  # type: ignore
cmd_validate.setup_parser = setup_validate_parser  # type: ignore
cmd_cancel.setup_parser = setup_cancel_parser  # type: ignore


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    Output.set_tool("gvrebootctl", "Fleet reboot coordination")
    
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(f"gvrebootctl {__version__}")
        sys.exit(0)
    
    invoked_as = Path(sys.argv[0]).name
    
    parser = argparse.ArgumentParser(
        prog=invoked_as,
        description="Reboot coordination and validation for fleet hosts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  rb check web1.example.com
  rb check --role web --reasons
  rb plan --role web --batch-size 2 --interval 120
  rb run --role web --batch-size 1 --yes
  rb validate --role web --services "nginx,sshd"
  rb cancel --role web
        """,
    )
    parser.add_argument("--version", "-V", action="version", version=f"gvrebootctl {__version__}")
    
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    
    check_p = subparsers.add_parser("check", help="check if hosts need reboot")
    setup_check_parser(check_p)
    
    plan_p = subparsers.add_parser("plan", help="generate reboot plan")
    setup_plan_parser(plan_p)
    
    run_p = subparsers.add_parser("run", help="execute reboots")
    setup_run_parser(run_p)
    
    validate_p = subparsers.add_parser("validate", help="validate services post-reboot")
    setup_validate_parser(validate_p)
    
    cancel_p = subparsers.add_parser("cancel", help="cancel pending reboots")
    setup_cancel_parser(cancel_p)
    
    args = parser.parse_args()
    apply_common_args(args)
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    commands = {
        "check": cmd_check,
        "plan": cmd_plan,
        "run": cmd_run,
        "validate": cmd_validate,
        "cancel": cmd_cancel,
    }
    
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
