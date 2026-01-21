#!/usr/bin/env python3
"""
gvdeploy - Execute commands and scripts across target sets

Execute commands/scripts across target sets with concurrency, per-host logs,
and clear exit statuses.

Aliases: dep, run

Author: Gvol (gvol@nexusystems.org)
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".local" / "lib" / "gvtools"))

from gvcore import (
    __version__,
    Output, Colors, c, die,
    Host, Inventory, Target,
    GVTOOLS_DATA,
    add_common_args, add_target_args, get_selector_from_args, apply_common_args,
    confirm, ssh_connect, ssh_exec, get_ssh_credentials,
)


# ─────────────────────────────────────────────────────────────────────────────
# Deployment State
# ─────────────────────────────────────────────────────────────────────────────

DEPLOY_HISTORY_PATH = GVTOOLS_DATA / "deploy_history.json"


@dataclass
class DeployResult:
    """Result of a deployment to a host."""
    host: str
    command: str = ""
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    timestamp: str = ""
    error: str = ""
    
    def to_dict(self) -> dict:
        return {
            "host": self.host,
            "command": self.command[:100],
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
            "error": self.error,
        }


def save_results(results: list[DeployResult]) -> None:
    """Save deployment results to history."""
    DEPLOY_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    # Load existing
    history = []
    if DEPLOY_HISTORY_PATH.exists():
        try:
            history = json.loads(DEPLOY_HISTORY_PATH.read_text())
        except Exception:
            pass
    
    # Add new run
    run = {
        "timestamp": datetime.now().isoformat(),
        "results": [r.to_dict() for r in results],
    }
    history.append(run)
    
    # Keep last 50 runs
    history = history[-50:]
    
    DEPLOY_HISTORY_PATH.write_text(json.dumps(history, indent=2) + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# Execution
# ─────────────────────────────────────────────────────────────────────────────

def execute_on_host(
    host: Host,
    command: str,
    password: str,
    key_path: str,
    sudo_pass: str,
    timeout: int,
    use_sudo: bool = False,
) -> DeployResult:
    """Execute command on a single host."""
    target = Target.from_host(host, default_user=host.user or "root")
    result = DeployResult(
        host=host.name,
        command=command,
        timestamp=datetime.now().isoformat(),
    )
    
    start = time.time()
    
    try:
        client = ssh_connect(
            target,
            password=password,
            key_path=key_path,
            timeout=timeout,
        )
        
        code, out, err = ssh_exec(client, command, sudo=use_sudo, password=sudo_pass or password)
        client.close()
        
        result.exit_code = code
        result.stdout = out
        result.stderr = err
    except Exception as e:
        result.exit_code = -1
        result.error = str(e)
    
    result.duration_ms = int((time.time() - start) * 1000)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

def cmd_cmd(args: argparse.Namespace) -> None:
    """Execute a shell command on targets."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if not hosts:
        die("no hosts matched selector")
    
    command = getattr(args, "command", "") or ""
    if not command:
        die("command is required (use -- to separate)")
    
    concurrency = getattr(args, "concurrency", 1) or 1
    dry_run = getattr(args, "dry_run", False)
    use_sudo = getattr(args, "use_sudo", False)
    
    # Safety: confirm for large target sets
    if len(hosts) > 10 and not getattr(args, "yes", False) and not dry_run:
        if not confirm(f"Execute on {len(hosts)} hosts?"):
            die("cancelled")
    
    if dry_run:
        Output.info(f"[DRY-RUN] Would execute on {len(hosts)} hosts:")
        for h in hosts:
            Output.step(h.name)
        Output.info(f"Command: {command}")
        return
    
    password, key_path, sudo_pass = get_ssh_credentials(args)
    timeout = getattr(args, "timeout", 30) or 30
    continue_on_fail = getattr(args, "continue_on_fail", False)
    
    results = []
    
    if concurrency == 1:
        # Sequential execution
        for host in hosts:
            Output.info(f"Executing on {c(host.name, Colors.CYAN)}...")
            result = execute_on_host(host, command, password, key_path, sudo_pass, timeout, use_sudo)
            results.append(result)
            
            if result.exit_code == 0:
                Output.success(f"{host.name}: exit 0 ({result.duration_ms}ms)")
            else:
                Output.error(f"{host.name}: exit {result.exit_code}")
                if result.stderr:
                    Output.step(result.stderr[:200])
                if not continue_on_fail:
                    Output.warn("stopping (use --continue-on-fail to continue)")
                    break
    else:
        # Parallel execution
        Output.info(f"Executing on {len(hosts)} hosts (concurrency: {concurrency})...")
        
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {
                executor.submit(
                    execute_on_host, host, command, password, key_path, sudo_pass, timeout, use_sudo
                ): host
                for host in hosts
            }
            
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                
                if result.exit_code == 0:
                    Output.success(f"{result.host}: exit 0 ({result.duration_ms}ms)")
                else:
                    Output.error(f"{result.host}: exit {result.exit_code}")
    
    # Save results
    save_results(results)
    
    if Output.json_mode:
        Output.json_output({"results": [r.to_dict() for r in results]})
        return
    
    # Summary
    ok = len([r for r in results if r.exit_code == 0])
    fail = len([r for r in results if r.exit_code != 0])
    Output.divider()
    Output.info(f"Summary: {c(str(ok), Colors.GREEN)} OK, {c(str(fail), Colors.RED)} FAILED")


def cmd_script(args: argparse.Namespace) -> None:
    """Execute a script file on targets."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if not hosts:
        die("no hosts matched selector")
    
    script_path = Path(args.script)
    if not script_path.exists():
        die(f"script not found: {script_path}")
    
    script_content = script_path.read_text()
    script_args = getattr(args, "args", "") or ""
    use_sudo = getattr(args, "use_sudo", False)
    
    # Encode script for transfer
    script_b64 = base64.b64encode(script_content.encode()).decode()
    
    # Build command to decode and execute
    command = f"""
SCRIPT_B64='{script_b64}'
SCRIPT=$(echo "$SCRIPT_B64" | base64 -d)
TMP_SCRIPT=$(mktemp)
echo "$SCRIPT" > "$TMP_SCRIPT"
chmod +x "$TMP_SCRIPT"
"$TMP_SCRIPT" {script_args}
EXIT_CODE=$?
rm -f "$TMP_SCRIPT"
exit $EXIT_CODE
"""
    
    # Reuse cmd logic
    args.command = command
    args.use_sudo = use_sudo
    cmd_cmd(args)


def cmd_copy(args: argparse.Namespace) -> None:
    """Copy a file to targets."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if not hosts:
        die("no hosts matched selector")
    
    src_path = Path(args.src)
    if not src_path.exists():
        die(f"source file not found: {src_path}")
    
    dst_path = args.dst
    owner = getattr(args, "owner", "") or ""
    mode = getattr(args, "mode", "") or ""
    
    # Read and encode file
    content = src_path.read_bytes()
    content_b64 = base64.b64encode(content).decode()
    
    # Build copy command
    copy_cmd = f"""
DST='{dst_path}'
CONTENT_B64='{content_b64}'
mkdir -p "$(dirname "$DST")"
echo "$CONTENT_B64" | base64 -d > "$DST"
"""
    
    if owner:
        copy_cmd += f'\nchown {owner} "$DST"'
    
    if mode:
        copy_cmd += f'\nchmod {mode} "$DST"'
    
    copy_cmd += '\necho "OK: copied to $DST"'
    
    password, key_path, sudo_pass = get_ssh_credentials(args)
    timeout = getattr(args, "timeout", 30) or 30
    results = []
    
    for host in hosts:
        Output.info(f"Copying to {c(host.name, Colors.CYAN)}:{dst_path}...")
        result = execute_on_host(host, copy_cmd, password, key_path, sudo_pass, timeout, use_sudo=True)
        results.append(result)
        
        if result.exit_code == 0:
            Output.success(f"{host.name}: copied")
        else:
            Output.error(f"{host.name}: failed - {result.stderr[:100]}")
    
    save_results(results)
    
    if Output.json_mode:
        Output.json_output({"results": [r.to_dict() for r in results]})


def cmd_fetch(args: argparse.Namespace) -> None:
    """Fetch a file from targets."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if not hosts:
        die("no hosts matched selector")
    
    src_path = args.src
    dst_dir = Path(args.dst)
    dst_dir.mkdir(parents=True, exist_ok=True)
    
    password, key_path, sudo_pass = get_ssh_credentials(args)
    timeout = getattr(args, "timeout", 30) or 30
    
    fetch_cmd = f'cat "{src_path}" | base64'
    
    for host in hosts:
        target = Target.from_host(host, default_user=host.user or "root")
        
        try:
            Output.info(f"Fetching from {c(host.name, Colors.CYAN)}:{src_path}...")
            client = ssh_connect(target, password=password, key_path=key_path, timeout=timeout)
            
            code, out, err = ssh_exec(client, fetch_cmd, sudo=True, password=sudo_pass or password)
            client.close()
            
            if code == 0:
                content = base64.b64decode(out.strip())
                out_file = dst_dir / f"{host.name}_{Path(src_path).name}"
                out_file.write_bytes(content)
                Output.success(f"{host.name}: saved to {out_file}")
            else:
                Output.error(f"{host.name}: failed - {err[:100]}")
        
        except Exception as e:
            Output.error(f"{host.name}: {e}")


def cmd_results(args: argparse.Namespace) -> None:
    """Show last deployment results."""
    if not DEPLOY_HISTORY_PATH.exists():
        die("no deployment history found")
    
    try:
        history = json.loads(DEPLOY_HISTORY_PATH.read_text())
    except Exception as e:
        die(f"could not read history: {e}")
    
    if not history:
        die("no deployment history")
    
    last_run = history[-1]
    
    if Output.json_mode:
        Output.json_output(last_run)
        return
    
    Output.header(f"Last Deployment: {last_run.get('timestamp', 'unknown')}")
    
    headers = ["Host", "Exit", "Duration", "Error"]
    rows = []
    
    for r in last_run.get("results", []):
        exit_code = r.get("exit_code", -1)
        exit_str = c("0", Colors.GREEN) if exit_code == 0 else c(str(exit_code), Colors.RED)
        error = r.get("error", "") or r.get("stderr", "")[:50]
        
        rows.append([
            c(r.get("host", ""), Colors.CYAN),
            exit_str,
            f"{r.get('duration_ms', 0)}ms",
            error,
        ])
    
    Output.table(headers, rows)


# ─────────────────────────────────────────────────────────────────────────────
# Parser Setup
# ─────────────────────────────────────────────────────────────────────────────

def setup_cmd_parser(parser: argparse.ArgumentParser) -> None:
    add_target_args(parser)
    parser.add_argument("command", nargs="?", help="command to execute")
    parser.add_argument("--concurrency", "-c", type=int, default=1, help="parallel execution (default: 1)")
    parser.add_argument("--continue-on-fail", action="store_true", help="continue on failure")
    parser.add_argument("--sudo", dest="use_sudo", action="store_true", help="run with sudo")
    add_common_args(parser)


def setup_script_parser(parser: argparse.ArgumentParser) -> None:
    add_target_args(parser)
    parser.add_argument("--script", "-s", required=True, help="script file to execute")
    parser.add_argument("--args", help="arguments to pass to script")
    parser.add_argument("--sudo", dest="use_sudo", action="store_true", help="run with sudo")
    add_common_args(parser)


def setup_copy_parser(parser: argparse.ArgumentParser) -> None:
    add_target_args(parser)
    parser.add_argument("--src", required=True, help="local source file")
    parser.add_argument("--dst", required=True, help="remote destination path")
    parser.add_argument("--owner", help="owner (e.g., root:root)")
    parser.add_argument("--mode", help="permissions (e.g., 644)")
    add_common_args(parser)


def setup_fetch_parser(parser: argparse.ArgumentParser) -> None:
    add_target_args(parser)
    parser.add_argument("--src", required=True, help="remote source path")
    parser.add_argument("--dst", required=True, help="local destination directory")
    add_common_args(parser)


def setup_results_parser(parser: argparse.ArgumentParser) -> None:
    add_common_args(parser)


cmd_cmd.setup_parser = setup_cmd_parser  # type: ignore
cmd_script.setup_parser = setup_script_parser  # type: ignore
cmd_copy.setup_parser = setup_copy_parser  # type: ignore
cmd_fetch.setup_parser = setup_fetch_parser  # type: ignore
cmd_results.setup_parser = setup_results_parser  # type: ignore


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    Output.set_tool("gvdeploy", "Remote command execution")
    
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(f"gvdeploy {__version__}")
        sys.exit(0)
    
    invoked_as = Path(sys.argv[0]).name
    
    parser = argparse.ArgumentParser(
        prog=invoked_as,
        description="Execute commands and scripts across target sets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  dep cmd --role web "uptime"
  dep cmd --role web --concurrency 5 "apt-get update"
  dep script --role web --script ./deploy.sh
  dep copy --role web --src ./app.conf --dst /etc/app/app.conf --owner root --mode 644
  dep fetch --role web --src /var/log/app.log --dst ./logs/
  dep results
        """,
    )
    parser.add_argument("--version", "-V", action="version", version=f"gvdeploy {__version__}")
    
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    
    cmd_p = subparsers.add_parser("cmd", help="execute a command")
    setup_cmd_parser(cmd_p)
    
    script_p = subparsers.add_parser("script", help="execute a script")
    setup_script_parser(script_p)
    
    copy_p = subparsers.add_parser("copy", help="copy file to targets")
    setup_copy_parser(copy_p)
    
    fetch_p = subparsers.add_parser("fetch", help="fetch file from targets")
    setup_fetch_parser(fetch_p)
    
    results_p = subparsers.add_parser("results", help="show last results")
    setup_results_parser(results_p)
    
    args = parser.parse_args()
    apply_common_args(args)
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    commands = {
        "cmd": cmd_cmd,
        "script": cmd_script,
        "copy": cmd_copy,
        "fetch": cmd_fetch,
        "results": cmd_results,
    }
    
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
