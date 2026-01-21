#!/usr/bin/env python3
"""
gvsystemdctl - Fleet-safe systemd management with rollout controls

Fleet-safe systemd management with rollout controls and validation hooks.

Aliases: sd, svc

Author: Gvol (gvol@nexusystems.org)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".local" / "lib" / "gvtools"))

from gvcore import (
    __version__,
    Output, Colors, c, die,
    Host, Inventory, Target,
    add_common_args, add_target_args, get_selector_from_args, apply_common_args,
    confirm, ssh_connect, ssh_exec, get_ssh_credentials,
)


# ─────────────────────────────────────────────────────────────────────────────
# Systemd Operations
# ─────────────────────────────────────────────────────────────────────────────

CRITICAL_UNITS = {"sshd", "ssh", "systemd-journald", "systemd-udevd", "dbus"}


def systemd_action(
    host: Host,
    unit: str,
    action: str,  # status, start, stop, restart, enable, disable
    password: str,
    key_path: str,
    sudo_pass: str,
    timeout: int,
) -> dict:
    """Execute systemd action on a host."""
    target = Target.from_host(host, default_user=host.user or "root")
    result = {"host": host.name, "unit": unit, "action": action, "success": False, "output": "", "error": ""}
    
    try:
        client = ssh_connect(target, password=password, key_path=key_path, timeout=timeout)
        
        if action == "status":
            cmd = f"systemctl status {unit} --no-pager 2>&1; echo EXIT_CODE:$?"
        elif action in ("start", "stop", "restart", "enable", "disable", "reload"):
            cmd = f"systemctl {action} {unit} 2>&1; echo EXIT_CODE:$?"
        else:
            result["error"] = f"unknown action: {action}"
            return result
        
        code, out, err = ssh_exec(client, cmd, sudo=True, password=sudo_pass or password)
        client.close()
        
        # Parse exit code from output
        lines = out.strip().split("\n")
        exit_code = 0
        output_lines = []
        for line in lines:
            if line.startswith("EXIT_CODE:"):
                try:
                    exit_code = int(line.split(":")[1])
                except ValueError:
                    pass
            else:
                output_lines.append(line)
        
        result["output"] = "\n".join(output_lines)
        result["success"] = exit_code == 0
        if not result["success"]:
            result["error"] = err or f"exit code {exit_code}"
    
    except Exception as e:
        result["error"] = str(e)
    
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

def cmd_status(args: argparse.Namespace) -> None:
    """Show systemd unit status."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if not hosts:
        die("no hosts matched selector")
    
    unit = args.unit
    if not unit:
        die("unit is required")
    
    password, key_path, sudo_pass = get_ssh_credentials(args)
    timeout = getattr(args, "timeout", 15) or 15
    results = []
    
    for host in hosts:
        Output.info(f"Checking {unit} on {c(host.name, Colors.CYAN)}...")
        result = systemd_action(host, unit, "status", password, key_path, sudo_pass, timeout)
        results.append(result)
    
    if Output.json_mode:
        Output.json_output({"results": results})
        return
    
    for r in results:
        status_color = Colors.GREEN if r["success"] else Colors.RED
        Output.info(f"{c(r['host'], Colors.CYAN)}: {c('active' if r['success'] else 'inactive', status_color)}")
        if Output.verbose and r["output"]:
            for line in r["output"].split("\n")[:5]:
                Output.step(line)


def cmd_action(args: argparse.Namespace, action: str) -> None:
    """Execute systemd action (start/stop/restart/enable/disable)."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if not hosts:
        die("no hosts matched selector")
    
    unit = args.unit
    if not unit:
        die("unit is required")
    
    batch_size = getattr(args, "batch_size", 1) or 1
    interval = getattr(args, "interval", 30) or 30
    dry_run = getattr(args, "dry_run", False)
    
    # Safety for critical units
    if unit in CRITICAL_UNITS and action in ("stop", "disable"):
        if not getattr(args, "yes", False):
            if not confirm(f"⚠️  {unit} is a critical unit. Continue with {action}?"):
                die("cancelled")
    
    if dry_run:
        Output.info(f"[DRY-RUN] Would {action} {unit} on {len(hosts)} hosts")
        for h in hosts:
            Output.step(h.name)
        return
    
    password, key_path, sudo_pass = get_ssh_credentials(args)
    timeout = getattr(args, "timeout", 30) or 30
    results = []
    
    # Process in batches
    for i in range(0, len(hosts), batch_size):
        batch = hosts[i:i + batch_size]
        
        if i > 0:
            Output.info(f"Waiting {interval}s before next batch...")
            time.sleep(interval)
        
        for host in batch:
            Output.info(f"{action.capitalize()}ing {unit} on {c(host.name, Colors.CYAN)}...")
            result = systemd_action(host, unit, action, password, key_path, sudo_pass, timeout)
            results.append(result)
            
            if result["success"]:
                Output.success(f"{host.name}: {action} OK")
            else:
                Output.error(f"{host.name}: {action} failed - {result['error']}")
    
    if Output.json_mode:
        Output.json_output({"results": results})
        return
    
    # Summary
    ok = len([r for r in results if r["success"]])
    fail = len([r for r in results if not r["success"]])
    Output.divider()
    Output.info(f"Summary: {c(str(ok), Colors.GREEN)} OK, {c(str(fail), Colors.RED)} FAILED")


def cmd_restart(args: argparse.Namespace) -> None:
    """Restart a systemd unit."""
    cmd_action(args, "restart")


def cmd_start(args: argparse.Namespace) -> None:
    """Start a systemd unit."""
    cmd_action(args, "start")


def cmd_stop(args: argparse.Namespace) -> None:
    """Stop a systemd unit."""
    cmd_action(args, "stop")


def cmd_enable(args: argparse.Namespace) -> None:
    """Enable a systemd unit."""
    cmd_action(args, "enable")


def cmd_disable(args: argparse.Namespace) -> None:
    """Disable a systemd unit."""
    cmd_action(args, "disable")


def cmd_logs(args: argparse.Namespace) -> None:
    """Show unit logs."""
    inventory = Inventory()
    
    host_name = args.target
    if not host_name:
        die("host is required")
    
    host = inventory.get(host_name)
    if not host:
        target = Target.parse(host_name)
        host = Host(name=target.host, address=target.host, port=target.port, user=target.user)
    
    unit = args.unit
    since = getattr(args, "since", "1h") or "1h"
    lines = getattr(args, "lines", 50) or 50
    
    password, key_path, sudo_pass = get_ssh_credentials(args)
    target = Target.from_host(host, default_user=host.user or "root")
    
    try:
        client = ssh_connect(target, password=password, key_path=key_path, timeout=15)
        
        cmd = f"journalctl -u {unit} --since '{since}' -n {lines} --no-pager"
        code, out, err = ssh_exec(client, cmd, sudo=True, password=sudo_pass or password)
        client.close()
        
        if Output.json_mode:
            Output.json_output({"host": host.name, "unit": unit, "logs": out})
        else:
            Output.header(f"Logs: {host.name} ({unit})")
            print(out)
    
    except Exception as e:
        die(f"failed: {e}")


def cmd_rollout(args: argparse.Namespace) -> None:
    """Rollout restart with validation."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if not hosts:
        die("no hosts matched selector")
    
    unit = args.unit
    if not unit:
        die("unit is required")
    
    batch_size = getattr(args, "batch_size", 1) or 1
    interval = getattr(args, "interval", 30) or 30
    validate_cmd = getattr(args, "validate", "") or ""
    
    password, key_path, sudo_pass = get_ssh_credentials(args)
    timeout = getattr(args, "timeout", 30) or 30
    
    Output.info(f"Rolling restart of {unit} across {len(hosts)} hosts")
    Output.info(f"Batch size: {batch_size}, Interval: {interval}s")
    
    results = []
    
    for i in range(0, len(hosts), batch_size):
        batch = hosts[i:i + batch_size]
        
        if i > 0:
            Output.info(f"Waiting {interval}s...")
            time.sleep(interval)
        
        Output.header(f"Batch {i // batch_size + 1}")
        
        for host in batch:
            Output.info(f"Restarting {unit} on {c(host.name, Colors.CYAN)}...")
            result = systemd_action(host, unit, "restart", password, key_path, sudo_pass, timeout)
            
            if not result["success"]:
                Output.error(f"{host.name}: restart failed - {result['error']}")
                result["validation"] = "skipped"
            else:
                Output.success(f"{host.name}: restarted")
                
                # Validate if command provided
                if validate_cmd:
                    time.sleep(2)  # Brief wait for service to stabilize
                    Output.step("Validating...")
                    
                    try:
                        target = Target.from_host(host, default_user=host.user or "root")
                        client = ssh_connect(target, password=password, key_path=key_path, timeout=timeout)
                        code, out, err = ssh_exec(client, validate_cmd, sudo=True, password=sudo_pass or password)
                        client.close()
                        
                        if code == 0:
                            result["validation"] = "passed"
                            Output.success(f"{host.name}: validation passed")
                        else:
                            result["validation"] = "failed"
                            Output.error(f"{host.name}: validation failed")
                    except Exception as e:
                        result["validation"] = f"error: {e}"
                else:
                    result["validation"] = "none"
            
            results.append(result)
    
    if Output.json_mode:
        Output.json_output({"results": results})


# ─────────────────────────────────────────────────────────────────────────────
# Parser Setup
# ─────────────────────────────────────────────────────────────────────────────

def setup_status_parser(parser: argparse.ArgumentParser) -> None:
    add_target_args(parser)
    parser.add_argument("unit", help="systemd unit name")
    add_common_args(parser)


def setup_action_parser(parser: argparse.ArgumentParser) -> None:
    add_target_args(parser)
    parser.add_argument("unit", help="systemd unit name")
    parser.add_argument("--batch-size", "-b", type=int, default=1, help="hosts per batch (default: 1)")
    parser.add_argument("--interval", type=int, default=30, help="seconds between batches (default: 30)")
    add_common_args(parser)


def setup_logs_parser(parser: argparse.ArgumentParser) -> None:
    add_target_args(parser)
    parser.add_argument("unit", help="systemd unit name")
    parser.add_argument("--since", default="1h", help="time window (default: 1h)")
    parser.add_argument("--lines", "-n", type=int, default=50, help="max lines (default: 50)")
    add_common_args(parser)


def setup_rollout_parser(parser: argparse.ArgumentParser) -> None:
    add_target_args(parser)
    parser.add_argument("unit", help="systemd unit name")
    parser.add_argument("--batch-size", "-b", type=int, default=1, help="hosts per batch")
    parser.add_argument("--interval", type=int, default=30, help="seconds between batches")
    parser.add_argument("--validate", help="validation command to run after restart")
    add_common_args(parser)


cmd_status.setup_parser = setup_status_parser  # type: ignore
cmd_restart.setup_parser = setup_action_parser  # type: ignore
cmd_start.setup_parser = setup_action_parser  # type: ignore
cmd_stop.setup_parser = setup_action_parser  # type: ignore
cmd_enable.setup_parser = setup_action_parser  # type: ignore
cmd_disable.setup_parser = setup_action_parser  # type: ignore
cmd_logs.setup_parser = setup_logs_parser  # type: ignore
cmd_rollout.setup_parser = setup_rollout_parser  # type: ignore


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    Output.set_tool("gvsystemdctl", "Fleet systemd management")
    
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(f"gvsystemdctl {__version__}")
        sys.exit(0)
    
    invoked_as = Path(sys.argv[0]).name
    
    parser = argparse.ArgumentParser(
        prog=invoked_as,
        description="Fleet-safe systemd management with rollout controls",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  sd status --role web nginx
  sd restart --role web nginx --batch-size 2 --interval 60
  sd stop web1.example.com nginx
  sd logs web1.example.com nginx --since 1h
  sd rollout --role web nginx --batch-size 1 --validate "curl -sf localhost/health"
        """,
    )
    parser.add_argument("--version", "-V", action="version", version=f"gvsystemdctl {__version__}")
    
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    
    status_p = subparsers.add_parser("status", help="show unit status")
    setup_status_parser(status_p)
    
    restart_p = subparsers.add_parser("restart", help="restart unit")
    setup_action_parser(restart_p)
    
    start_p = subparsers.add_parser("start", help="start unit")
    setup_action_parser(start_p)
    
    stop_p = subparsers.add_parser("stop", help="stop unit")
    setup_action_parser(stop_p)
    
    enable_p = subparsers.add_parser("enable", help="enable unit")
    setup_action_parser(enable_p)
    
    disable_p = subparsers.add_parser("disable", help="disable unit")
    setup_action_parser(disable_p)
    
    logs_p = subparsers.add_parser("logs", help="show unit logs")
    setup_logs_parser(logs_p)
    
    rollout_p = subparsers.add_parser("rollout", help="rollout restart with validation")
    setup_rollout_parser(rollout_p)
    
    args = parser.parse_args()
    apply_common_args(args)
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    commands = {
        "status": cmd_status,
        "restart": cmd_restart,
        "start": cmd_start,
        "stop": cmd_stop,
        "enable": cmd_enable,
        "disable": cmd_disable,
        "logs": cmd_logs,
        "rollout": cmd_rollout,
    }
    
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
