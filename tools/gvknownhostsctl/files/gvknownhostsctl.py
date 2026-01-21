#!/usr/bin/env python3
"""
gvknownhostsctl - Manage ~/.ssh/known_hosts safely

Handle host key changes, collisions, and cleanup:
- Verify current vs remote host keys
- Add/remove entries safely
- Dedupe and cleanup

Aliases: kh, gvkh

Author: Gvol (gvol@nexusystems.org)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".local" / "lib" / "gvtools"))

from gvcore import (
    Output, die,
    add_common_args, apply_common_args, confirm,
)

__version__ = "1.1.3"

KNOWN_HOSTS = Path.home() / ".ssh" / "known_hosts"


# ─────────────────────────────────────────────────────────────────────────────
# Known Hosts Handling
# ─────────────────────────────────────────────────────────────────────────────

def read_known_hosts() -> list[str]:
    """Read known_hosts file."""
    if not KNOWN_HOSTS.exists():
        return []
    return KNOWN_HOSTS.read_text().strip().split("\n")


def write_known_hosts(lines: list[str]) -> None:
    """Write known_hosts file."""
    KNOWN_HOSTS.parent.mkdir(parents=True, exist_ok=True)
    KNOWN_HOSTS.write_text("\n".join(lines) + "\n" if lines else "")
    KNOWN_HOSTS.chmod(0o644)


def get_remote_key(host: str, port: int = 22) -> str | None:
    """Get host key from remote server using ssh-keyscan."""
    try:
        cmd = ["ssh-keyscan", "-p", str(port), "-T", "5", host]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return None
    except Exception:
        return None


def get_key_fingerprint(key_line: str) -> str | None:
    """Get SHA256 fingerprint of a key line."""
    try:
        # Extract just the key part
        parts = key_line.split()
        if len(parts) >= 3:
            key_data = parts[1] + " " + parts[2]
        else:
            key_data = key_line
        
        result = subprocess.run(
            ["ssh-keygen", "-lf", "-"],
            input=key_data,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip().split()[1]
        return None
    except Exception:
        return None


def find_entries(hostname: str, lines: list[str]) -> list[tuple[int, str]]:
    """Find entries for a hostname in known_hosts."""
    entries = []
    for i, line in enumerate(lines):
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split()
        if parts:
            hosts = parts[0].split(",")
            if hostname in hosts or any(h.startswith(f"[{hostname}]") for h in hosts):
                entries.append((i, line))
    return entries


# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

def cmd_verify(args: argparse.Namespace) -> None:
    """Verify host key matches known_hosts."""
    host = args.host
    port = args.port or 22
    
    Output.header(f"Verify: {host}")
    
    lines = read_known_hosts()
    entries = find_entries(host, lines)
    
    if not entries:
        Output.warn(f"No entry for {host} in known_hosts")
        return
    
    Output.info(f"Found {len(entries)} entry/entries in known_hosts")
    
    # Get current remote key
    Output.step("Fetching remote key...")
    remote_key = get_remote_key(host, port)
    
    if not remote_key:
        Output.error("Could not fetch remote key")
        return
    
    # Compare
    remote_parts = remote_key.split("\n")[0].split() if remote_key else []
    
    for idx, entry in entries:
        entry_parts = entry.split()
        if len(entry_parts) >= 3 and len(remote_parts) >= 3:
            if entry_parts[1] == remote_parts[1] and entry_parts[2] == remote_parts[2]:
                Output.success(f"Key matches (line {idx + 1})")
            else:
                Output.error(f"KEY MISMATCH (line {idx + 1})")
                Output.keyvalue("known", entry_parts[1][:20] + "...")
                Output.keyvalue("remote", remote_parts[1][:20] + "...")
        else:
            Output.step(f"Line {idx + 1}: could not compare")


def cmd_add(args: argparse.Namespace) -> None:
    """Add host key to known_hosts."""
    host = args.host
    port = args.port or 22
    fingerprint = args.fingerprint
    
    Output.header(f"Add: {host}")
    
    # Fetch key
    Output.step("Fetching host key...")
    remote_key = get_remote_key(host, port)
    
    if not remote_key:
        die("Could not fetch host key")
    
    # Verify fingerprint if provided
    if fingerprint:
        actual_fp = get_key_fingerprint(remote_key.split("\n")[0])
        if actual_fp and fingerprint not in actual_fp:
            die(f"Fingerprint mismatch!\n  Expected: {fingerprint}\n  Got: {actual_fp}")
        Output.success(f"Fingerprint verified: {actual_fp}")
    
    if args.dry_run:
        Output.info("Would add:")
        print(remote_key)
        return
    
    lines = read_known_hosts()
    
    # Remove existing entries
    existing = find_entries(host, lines)
    if existing:
        Output.step(f"Removing {len(existing)} existing entries")
        for idx, _ in reversed(existing):
            del lines[idx]
    
    # Add new entries
    for line in remote_key.split("\n"):
        if line.strip():
            lines.append(line)
    
    write_known_hosts(lines)
    Output.success(f"Added {host} to known_hosts")


def cmd_rm(args: argparse.Namespace) -> None:
    """Remove host from known_hosts."""
    host = args.host
    
    lines = read_known_hosts()
    entries = find_entries(host, lines)
    
    if not entries:
        Output.info(f"No entries for {host}")
        return
    
    Output.header(f"Remove: {host}")
    Output.info(f"Found {len(entries)} entries")
    
    if not args.yes:
        if not confirm(f"Remove {len(entries)} entries for {host}?"):
            return
    
    if args.dry_run:
        Output.info("Would remove these entries:")
        for idx, entry in entries:
            print(f"  Line {idx + 1}: {entry[:60]}...")
        return
    
    for idx, _ in reversed(entries):
        del lines[idx]
    
    write_known_hosts(lines)
    Output.success(f"Removed {len(entries)} entries")


def cmd_dedupe(args: argparse.Namespace) -> None:
    """Remove duplicate entries."""
    lines = read_known_hosts()
    
    seen = set()
    new_lines = []
    removed = 0
    
    for line in lines:
        if not line.strip() or line.startswith("#"):
            new_lines.append(line)
            continue
        
        # Create a normalized key for deduplication
        parts = line.split()
        if len(parts) >= 3:
            key = (parts[1], parts[2])
            if key in seen:
                removed += 1
                continue
            seen.add(key)
        
        new_lines.append(line)
    
    if removed == 0:
        Output.success("No duplicates found")
        return
    
    if args.dry_run:
        Output.info(f"Would remove {removed} duplicates")
        return
    
    write_known_hosts(new_lines)
    Output.success(f"Removed {removed} duplicates")


def cmd_rename(args: argparse.Namespace) -> None:
    """Rename host entries."""
    old_host = args.old
    new_host = args.new
    
    lines = read_known_hosts()
    entries = find_entries(old_host, lines)
    
    if not entries:
        die(f"No entries for {old_host}")
    
    Output.header(f"Rename: {old_host} → {new_host}")
    
    if args.dry_run:
        Output.info(f"Would rename {len(entries)} entries")
        return
    
    for idx, entry in entries:
        # Replace hostname in entry
        new_entry = entry.replace(old_host, new_host, 1)
        lines[idx] = new_entry
    
    write_known_hosts(lines)
    Output.success(f"Renamed {len(entries)} entries")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    Output.set_tool("gvknownhostsctl", "known_hosts manager")
    
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(f"gvknownhostsctl {__version__}")
        sys.exit(0)
    
    parser = argparse.ArgumentParser(
        prog=Path(sys.argv[0]).name,
        description="Manage ~/.ssh/known_hosts safely",
        epilog="""
Examples:
  kh verify server.example.com
  kh add newserver.example.com --fingerprint SHA256:abc...
  kh rm oldserver.example.com
  kh dedupe
  kh rename old.example.com new.example.com
        """,
    )
    parser.add_argument("--version", "-V", action="version", version=f"gvknownhostsctl {__version__}")
    
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    
    # verify
    verify_p = subparsers.add_parser("verify", help="verify host key")
    verify_p.add_argument("host", help="hostname to verify")
    verify_p.add_argument("--port", "-p", type=int, help="SSH port")
    add_common_args(verify_p)
    
    # add
    add_p = subparsers.add_parser("add", help="add host key")
    add_p.add_argument("host", help="hostname to add")
    add_p.add_argument("--port", "-p", type=int, help="SSH port")
    add_p.add_argument("--fingerprint", "-f", help="expected SHA256 fingerprint")
    add_common_args(add_p)
    
    # rm
    rm_p = subparsers.add_parser("rm", help="remove host entries")
    rm_p.add_argument("host", help="hostname to remove")
    add_common_args(rm_p)
    
    # dedupe
    dedupe_p = subparsers.add_parser("dedupe", help="remove duplicates")
    add_common_args(dedupe_p)
    
    # rename
    rename_p = subparsers.add_parser("rename", help="rename host entries")
    rename_p.add_argument("old", help="old hostname")
    rename_p.add_argument("new", help="new hostname")
    add_common_args(rename_p)
    
    args = parser.parse_args()
    apply_common_args(args)
    
    commands = {
        "verify": cmd_verify,
        "add": cmd_add,
        "rm": cmd_rm,
        "dedupe": cmd_dedupe,
        "rename": cmd_rename,
    }
    
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
