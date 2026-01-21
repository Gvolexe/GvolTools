#!/usr/bin/env python3
"""
gvsync - Rsync wrapper with SSH profile awareness

File/directory synchronization using rsync with fleet integration
and SSH profile support.

Aliases: sync, sx

Author: Gvol (gvol@nexusystems.org)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".local" / "lib" / "gvtools"))

from gvcore import (
    __version__,
    Output, Colors, c, die,
    Inventory, Target,
    GVTOOLS_DATA,
    add_common_args, add_target_args, get_selector_from_args, apply_common_args,
    SSHProfileManager,
)


# ─────────────────────────────────────────────────────────────────────────────
# Sync Configuration
# ─────────────────────────────────────────────────────────────────────────────

SYNC_HISTORY_PATH = GVTOOLS_DATA / "sync_history.json"

@dataclass
class SyncResult:
    """Result of a sync operation."""
    host: str
    source: str
    dest: str
    success: bool
    bytes_transferred: int = 0
    files_transferred: int = 0
    duration_ms: int = 0
    error: str = ""
    
    def to_dict(self) -> dict:
        return {
            "host": self.host,
            "source": self.source,
            "dest": self.dest,
            "success": self.success,
            "bytes_transferred": self.bytes_transferred,
            "files_transferred": self.files_transferred,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


def format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    for unit in ["B", "KB", "MB", "GB"]:
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f}TB"


def build_rsync_command(
    source: str,
    dest: str,
    ssh_cmd: str | None = None,
    delete: bool = False,
    dry_run: bool = False,
    exclude: list[str] | None = None,
    include: list[str] | None = None,
    checksum: bool = False,
    compress: bool = True,
    progress: bool = True,
    archive: bool = True,
    partial: bool = True,
) -> list[str]:
    """Build rsync command."""
    cmd = ["rsync"]
    
    if archive:
        cmd.append("-a")
    if compress:
        cmd.append("-z")
    if progress:
        cmd.append("--progress")
    if checksum:
        cmd.append("-c")
    if partial:
        cmd.append("--partial")
    if delete:
        cmd.append("--delete")
    if dry_run:
        cmd.append("--dry-run")
    
    # Always include stats for parsing
    cmd.append("--stats")
    
    if ssh_cmd:
        cmd.extend(["-e", ssh_cmd])
    
    if exclude:
        for pat in exclude:
            cmd.extend(["--exclude", pat])
    
    if include:
        for pat in include:
            cmd.extend(["--include", pat])
    
    cmd.append(source)
    cmd.append(dest)
    
    return cmd


def parse_rsync_stats(output: str) -> tuple[int, int]:
    """Parse rsync stats output to extract bytes and files transferred."""
    bytes_transferred = 0
    files_transferred = 0
    
    for line in output.split("\n"):
        if "Number of regular files transferred:" in line:
            try:
                files_transferred = int(line.split(":")[-1].strip().replace(",", ""))
            except ValueError:
                pass
        elif "Total transferred file size:" in line:
            try:
                # Extract bytes value
                parts = line.split(":")[-1].strip().split()
                if parts:
                    bytes_transferred = int(parts[0].replace(",", ""))
            except ValueError:
                pass
    
    return bytes_transferred, files_transferred


# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

def cmd_push(args: argparse.Namespace) -> None:
    """Push files to remote host(s)."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if not hosts:
        die("no hosts matched selector")
    
    source = args.source
    dest = args.dest
    dry_run = getattr(args, "dry_run", False)
    delete = getattr(args, "delete", False)
    exclude = getattr(args, "exclude", []) or []
    
    if not os.path.exists(source):
        die(f"source path does not exist: {source}")
    
    profile_mgr = SSHProfileManager()
    results = []
    
    for host in hosts:
        target = Target.from_host(host, default_user=host.user or "root")
        
        # Build SSH command
        ssh_opts = []
        profile = profile_mgr.active()
        if profile:
            if profile.get("identity_file"):
                ssh_opts.extend(["-i", profile["identity_file"]])
            if profile.get("port"):
                ssh_opts.extend(["-p", str(profile["port"])])
        
        ssh_opts.extend(["-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes"])
        ssh_cmd = f"ssh {' '.join(ssh_opts)}"
        
        remote_path = f"{target.user}@{target.hostname}:{dest}"
        
        cmd = build_rsync_command(
            source=source,
            dest=remote_path,
            ssh_cmd=ssh_cmd,
            delete=delete,
            dry_run=dry_run,
            exclude=exclude,
            progress=not Output.json_mode,
        )
        
        if not Output.json_mode:
            action = "Would push" if dry_run else "Pushing"
            Output.info(f"{action} to {c(host.name, Colors.CYAN)}")
        
        start_time = datetime.now()
        
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=getattr(args, "timeout", 300) or 300,
            )
            
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            if proc.returncode == 0:
                bytes_xfer, files_xfer = parse_rsync_stats(proc.stdout + proc.stderr)
                result = SyncResult(
                    host=host.name,
                    source=source,
                    dest=dest,
                    success=True,
                    bytes_transferred=bytes_xfer,
                    files_transferred=files_xfer,
                    duration_ms=duration_ms,
                )
            else:
                result = SyncResult(
                    host=host.name,
                    source=source,
                    dest=dest,
                    success=False,
                    duration_ms=duration_ms,
                    error=proc.stderr.strip() or proc.stdout.strip(),
                )
        
        except subprocess.TimeoutExpired:
            result = SyncResult(
                host=host.name,
                source=source,
                dest=dest,
                success=False,
                error="timeout",
            )
        except Exception as e:
            result = SyncResult(
                host=host.name,
                source=source,
                dest=dest,
                success=False,
                error=str(e),
            )
        
        results.append(result)
        
        if not Output.json_mode:
            if result.success:
                Output.success(f"{host.name}: {format_size(result.bytes_transferred)} ({result.files_transferred} files)")
            else:
                Output.error(f"{host.name}: {result.error}")
    
    if Output.json_mode:
        Output.json_output({"results": [r.to_dict() for r in results]})


def cmd_pull(args: argparse.Namespace) -> None:
    """Pull files from remote host."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if len(hosts) != 1:
        die("pull requires exactly one host (use a specific hostname)")
    
    host = hosts[0]
    source = args.source
    dest = args.dest
    dry_run = getattr(args, "dry_run", False)
    
    target = Target.from_host(host, default_user=host.user or "root")
    
    profile_mgr = SSHProfileManager()
    ssh_opts = []
    profile = profile_mgr.active()
    if profile:
        if profile.get("identity_file"):
            ssh_opts.extend(["-i", profile["identity_file"]])
        if profile.get("port"):
            ssh_opts.extend(["-p", str(profile["port"])])
    
    ssh_opts.extend(["-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes"])
    ssh_cmd = f"ssh {' '.join(ssh_opts)}"
    
    remote_path = f"{target.user}@{target.hostname}:{source}"
    
    cmd = build_rsync_command(
        source=remote_path,
        dest=dest,
        ssh_cmd=ssh_cmd,
        dry_run=dry_run,
        progress=not Output.json_mode,
    )
    
    if not Output.json_mode:
        action = "Would pull" if dry_run else "Pulling"
        Output.info(f"{action} from {c(host.name, Colors.CYAN)}")
    
    start_time = datetime.now()
    
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=getattr(args, "timeout", 300) or 300,
        )
        
        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        
        if proc.returncode == 0:
            bytes_xfer, files_xfer = parse_rsync_stats(proc.stdout + proc.stderr)
            result = SyncResult(
                host=host.name,
                source=source,
                dest=dest,
                success=True,
                bytes_transferred=bytes_xfer,
                files_transferred=files_xfer,
                duration_ms=duration_ms,
            )
        else:
            result = SyncResult(
                host=host.name,
                source=source,
                dest=dest,
                success=False,
                duration_ms=duration_ms,
                error=proc.stderr.strip() or proc.stdout.strip(),
            )
    
    except subprocess.TimeoutExpired:
        result = SyncResult(
            host=host.name,
            source=source,
            dest=dest,
            success=False,
            error="timeout",
        )
    except Exception as e:
        result = SyncResult(
            host=host.name,
            source=source,
            dest=dest,
            success=False,
            error=str(e),
        )
    
    if Output.json_mode:
        Output.json_output({"result": result.to_dict()})
    else:
        if result.success:
            Output.success(f"Transferred {format_size(result.bytes_transferred)} ({result.files_transferred} files)")
        else:
            Output.error(f"Failed: {result.error}")


def cmd_mirror(args: argparse.Namespace) -> None:
    """Mirror directory to remote (delete extra files)."""
    # Same as push with delete enabled
    args.delete = True
    cmd_push(args)


def cmd_diff(args: argparse.Namespace) -> None:
    """Show differences between local and remote."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if not hosts:
        die("no hosts matched selector")
    
    source = args.source
    dest = args.dest
    
    if not os.path.exists(source):
        die(f"source path does not exist: {source}")
    
    profile_mgr = SSHProfileManager()
    
    for host in hosts:
        target = Target.from_host(host, default_user=host.user or "root")
        
        ssh_opts = []
        profile = profile_mgr.active()
        if profile:
            if profile.get("identity_file"):
                ssh_opts.extend(["-i", profile["identity_file"]])
            if profile.get("port"):
                ssh_opts.extend(["-p", str(profile["port"])])
        
        ssh_opts.extend(["-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes"])
        ssh_cmd = f"ssh {' '.join(ssh_opts)}"
        
        remote_path = f"{target.user}@{target.hostname}:{dest}"
        
        # Use -n --itemize-changes for diff
        cmd = ["rsync", "-avnc", "--itemize-changes", "-e", ssh_cmd, source, remote_path]
        
        if not Output.json_mode:
            Output.header(f"Differences: {host.name}")
        
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            
            changes = []
            for line in proc.stdout.split("\n"):
                if line.startswith(">") or line.startswith("<") or line.startswith("*"):
                    changes.append(line)
            
            if Output.json_mode:
                Output.json_output({"host": host.name, "changes": changes})
            else:
                if changes:
                    for change in changes:
                        Output.step(change)
                else:
                    Output.success("In sync")
        
        except Exception as e:
            if Output.json_mode:
                Output.json_output({"host": host.name, "error": str(e)})
            else:
                Output.error(f"Error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Parser Setup
# ─────────────────────────────────────────────────────────────────────────────

def setup_push_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("source", help="local source path")
    parser.add_argument("dest", help="remote destination path")
    parser.add_argument("--delete", action="store_true", help="delete files not in source")
    parser.add_argument("--dry-run", "-n", action="store_true", help="dry run")
    parser.add_argument("--exclude", action="append", help="exclude pattern")
    parser.add_argument("--timeout", type=int, default=300, help="timeout in seconds")
    add_target_args(parser)
    add_common_args(parser)


def setup_pull_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("source", help="remote source path")
    parser.add_argument("dest", help="local destination path")
    parser.add_argument("--dry-run", "-n", action="store_true", help="dry run")
    parser.add_argument("--timeout", type=int, default=300, help="timeout in seconds")
    add_target_args(parser)
    add_common_args(parser)


def setup_mirror_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("source", help="local source path")
    parser.add_argument("dest", help="remote destination path")
    parser.add_argument("--dry-run", "-n", action="store_true", help="dry run")
    parser.add_argument("--timeout", type=int, default=300, help="timeout in seconds")
    add_target_args(parser)
    add_common_args(parser)


def setup_diff_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("source", help="local source path")
    parser.add_argument("dest", help="remote path")
    add_target_args(parser)
    add_common_args(parser)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    Output.set_tool("gvsync", "File synchronization with fleet awareness")
    
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(f"gvsync {__version__}")
        sys.exit(0)
    
    invoked_as = Path(sys.argv[0]).name
    
    parser = argparse.ArgumentParser(
        prog=invoked_as,
        description="Rsync wrapper with SSH profile awareness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  sx push ./app /opt/app --host web1
  sx push ./config /etc/myapp --role web --delete
  sx pull /var/log/app.log ./logs/ --host web1
  sx mirror ./dist /var/www/html --role web --dry-run
  sx diff ./config /etc/myapp --host web1
        """,
    )
    parser.add_argument("--version", "-V", action="version", version=f"gvsync {__version__}")
    
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    
    push_p = subparsers.add_parser("push", help="push files to remote")
    setup_push_parser(push_p)
    
    pull_p = subparsers.add_parser("pull", help="pull files from remote")
    setup_pull_parser(pull_p)
    
    mirror_p = subparsers.add_parser("mirror", help="mirror directory (delete extra)")
    setup_mirror_parser(mirror_p)
    
    diff_p = subparsers.add_parser("diff", help="show differences")
    setup_diff_parser(diff_p)
    
    args = parser.parse_args()
    apply_common_args(args)
    
    commands = {
        "push": cmd_push,
        "pull": cmd_pull,
        "mirror": cmd_mirror,
        "diff": cmd_diff,
    }
    
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
