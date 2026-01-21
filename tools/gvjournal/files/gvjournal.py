#!/usr/bin/env python3
"""
gvjournal - Fetch and filter systemd journal logs across hosts

Consistent time/unit/priority filters for journalctl across the fleet.

Aliases: jrnl, j

Author: Gvol (gvol@nexusystems.org)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".local" / "lib" / "gvtools"))

from gvcore import (
    __version__,
    Output, Colors, c, die,
    Host, Inventory, Target,
    add_common_args, add_target_args, get_selector_from_args, apply_common_args,
    ssh_connect, ssh_exec, get_ssh_credentials,
)


# ─────────────────────────────────────────────────────────────────────────────
# Journal Commands
# ─────────────────────────────────────────────────────────────────────────────

def build_journalctl_cmd(
    unit: str = "",
    since: str = "",
    until: str = "",
    priority: str = "",
    lines: int = 0,
    boot: str = "",
    grep: str = "",
    output_format: str = "",
    no_pager: bool = True,
) -> str:
    """Build journalctl command with options."""
    cmd_parts = ["journalctl"]
    
    if no_pager:
        cmd_parts.append("--no-pager")
    
    if unit:
        cmd_parts.extend(["-u", unit])
    
    if since:
        cmd_parts.extend(["--since", f"'{since}'"])
    
    if until:
        cmd_parts.extend(["--until", f"'{until}'"])
    
    if priority:
        cmd_parts.extend(["-p", priority])
    
    if lines:
        cmd_parts.extend(["-n", str(lines)])
    
    if boot:
        cmd_parts.extend(["-b", boot])
    
    if grep:
        cmd_parts.extend(["-g", f"'{grep}'"])
    
    if output_format:
        cmd_parts.extend(["-o", output_format])
    
    return " ".join(cmd_parts)


# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

def cmd_unit(args: argparse.Namespace) -> None:
    """Fetch logs for a systemd unit."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if not hosts:
        die("no hosts matched selector")
    
    unit = args.unit
    if not unit:
        die("unit is required")
    
    since = getattr(args, "since", "") or "2h"
    until = getattr(args, "until_time", "") or ""
    priority = getattr(args, "priority", "") or ""
    lines = getattr(args, "lines", 0) or 100
    
    password, key_path, sudo_pass = get_ssh_credentials(args)
    
    results = {}
    
    for host in hosts:
        target = Target.from_host(host, default_user=host.user or "root")
        
        try:
            Output.info(f"Fetching logs from {c(host.name, Colors.CYAN)}...")
            client = ssh_connect(
                target,
                password=password,
                key_path=key_path,
                timeout=getattr(args, "timeout", 15),
            )
            
            cmd = build_journalctl_cmd(
                unit=unit,
                since=since,
                until=until,
                priority=priority,
                lines=lines,
                output_format="json" if Output.json_mode else "short-iso",
            )
            
            code, out, err = ssh_exec(client, cmd, sudo=True, password=sudo_pass or password)
            client.close()
            
            if code == 0:
                results[host.name] = {"logs": out, "error": ""}
            else:
                results[host.name] = {"logs": "", "error": f"exit {code}: {err[:100]}"}
        
        except Exception as e:
            results[host.name] = {"logs": "", "error": str(e)}
    
    if Output.json_mode:
        # Parse JSON lines from journalctl
        parsed = {}
        for host_name, data in results.items():
            if data["error"]:
                parsed[host_name] = {"error": data["error"], "entries": []}
            else:
                entries = []
                for line in data["logs"].strip().split("\n"):
                    if line.strip():
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
                parsed[host_name] = {"entries": entries}
        Output.json_output({"results": parsed})
        return
    
    for host_name, data in results.items():
        Output.header(f"Logs: {host_name} ({unit})")
        if data["error"]:
            Output.error(data["error"])
        else:
            print(data["logs"])


def cmd_grep(args: argparse.Namespace) -> None:
    """Search logs with a pattern."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if not hosts:
        die("no hosts matched selector")
    
    pattern = args.pattern
    if not pattern:
        die("pattern is required")
    
    since = getattr(args, "since", "") or "24h"
    lines = getattr(args, "lines", 0) or 50
    
    password, key_path, sudo_pass = get_ssh_credentials(args)
    
    results = {}
    
    for host in hosts:
        target = Target.from_host(host, default_user=host.user or "root")
        
        try:
            Output.info(f"Searching logs on {c(host.name, Colors.CYAN)}...")
            client = ssh_connect(
                target,
                password=password,
                key_path=key_path,
                timeout=getattr(args, "timeout", 15),
            )
            
            cmd = build_journalctl_cmd(
                since=since,
                lines=lines,
                grep=pattern,
                output_format="json" if Output.json_mode else "short-iso",
            )
            
            code, out, err = ssh_exec(client, cmd, sudo=True, password=sudo_pass or password)
            client.close()
            
            if code == 0:
                results[host.name] = {"logs": out, "count": len(out.strip().split("\n")) if out.strip() else 0}
            else:
                results[host.name] = {"logs": "", "count": 0, "error": f"exit {code}"}
        
        except Exception as e:
            results[host.name] = {"logs": "", "count": 0, "error": str(e)}
    
    if Output.json_mode:
        Output.json_output({"pattern": pattern, "results": results})
        return
    
    for host_name, data in results.items():
        if data.get("error"):
            Output.error(f"{host_name}: {data['error']}")
        elif data["count"] > 0:
            Output.header(f"Matches: {host_name} ({data['count']})")
            print(data["logs"])
        else:
            Output.info(f"{host_name}: no matches")


def cmd_boots(args: argparse.Namespace) -> None:
    """List boot records."""
    inventory = Inventory()
    
    host_name = args.target
    if not host_name:
        die("host is required")
    
    host = inventory.get(host_name)
    if not host:
        target = Target.parse(host_name)
        host = Host(name=target.host, address=target.host, port=target.port, user=target.user)
    
    password, key_path, sudo_pass = get_ssh_credentials(args)
    target = Target.from_host(host, default_user=host.user or "root")
    
    try:
        client = ssh_connect(
            target,
            password=password,
            key_path=key_path,
            timeout=getattr(args, "timeout", 15),
        )
        
        code, out, err = ssh_exec(client, "journalctl --list-boots --no-pager", sudo=True, password=sudo_pass or password)
        client.close()
        
        if code != 0:
            die(f"failed: {err}")
        
        if Output.json_mode:
            # Parse boot list
            boots = []
            for line in out.strip().split("\n"):
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 4:
                        boots.append({
                            "id": parts[0],
                            "boot_id": parts[1],
                            "first": " ".join(parts[2:5]) if len(parts) >= 5 else "",
                            "last": " ".join(parts[-3:]) if len(parts) >= 8 else "",
                        })
            Output.json_output({"host": host.name, "boots": boots})
        else:
            Output.header(f"Boot Records: {host.name}")
            print(out)
    
    except Exception as e:
        die(f"failed: {e}")


def cmd_export(args: argparse.Namespace) -> None:
    """Export logs to file."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if not hosts:
        die("no hosts matched selector")
    
    since = getattr(args, "since", "") or "2h"
    output_path = getattr(args, "out", "") or "logs.ndjson"
    
    password, key_path, sudo_pass = get_ssh_credentials(args)
    
    all_entries = []
    
    for host in hosts:
        target = Target.from_host(host, default_user=host.user or "root")
        
        try:
            Output.info(f"Exporting from {c(host.name, Colors.CYAN)}...")
            client = ssh_connect(
                target,
                password=password,
                key_path=key_path,
                timeout=getattr(args, "timeout", 15),
            )
            
            cmd = build_journalctl_cmd(
                since=since,
                output_format="json",
            )
            
            code, out, err = ssh_exec(client, cmd, sudo=True, password=sudo_pass or password)
            client.close()
            
            if code == 0:
                for line in out.strip().split("\n"):
                    if line.strip():
                        try:
                            entry = json.loads(line)
                            entry["_GVTOOLS_HOST"] = host.name
                            all_entries.append(entry)
                        except json.JSONDecodeError:
                            pass
        
        except Exception as e:
            Output.warn(f"{host.name}: {e}")
    
    # Write NDJSON
    with open(output_path, "w") as f:
        for entry in all_entries:
            f.write(json.dumps(entry) + "\n")
    
    Output.success(f"Exported {len(all_entries)} entries to {output_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Parser Setup
# ─────────────────────────────────────────────────────────────────────────────

def setup_unit_parser(parser: argparse.ArgumentParser) -> None:
    add_target_args(parser)
    parser.add_argument("unit", help="systemd unit name")
    parser.add_argument("--since", default="2h", help="time window (default: 2h)")
    parser.add_argument("--until", dest="until_time", help="end time")
    parser.add_argument("--priority", "-p", choices=["emerg", "alert", "crit", "err", "warning", "notice", "info", "debug"], help="minimum priority")
    parser.add_argument("--lines", "-n", type=int, default=100, help="max lines (default: 100)")
    add_common_args(parser)


def setup_grep_parser(parser: argparse.ArgumentParser) -> None:
    add_target_args(parser)
    parser.add_argument("pattern", help="pattern to search")
    parser.add_argument("--since", default="24h", help="time window (default: 24h)")
    parser.add_argument("--lines", "-n", type=int, default=50, help="max lines (default: 50)")
    add_common_args(parser)


def setup_boots_parser(parser: argparse.ArgumentParser) -> None:
    add_target_args(parser)
    add_common_args(parser)


def setup_export_parser(parser: argparse.ArgumentParser) -> None:
    add_target_args(parser)
    parser.add_argument("--since", default="2h", help="time window (default: 2h)")
    parser.add_argument("--out", "-o", default="logs.ndjson", help="output file")
    add_common_args(parser)


cmd_unit.setup_parser = setup_unit_parser  # type: ignore
cmd_grep.setup_parser = setup_grep_parser  # type: ignore
cmd_boots.setup_parser = setup_boots_parser  # type: ignore
cmd_export.setup_parser = setup_export_parser  # type: ignore


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    Output.set_tool("gvjournal", "Systemd journal log viewer")
    
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(f"gvjournal {__version__}")
        sys.exit(0)
    
    invoked_as = Path(sys.argv[0]).name
    
    parser = argparse.ArgumentParser(
        prog=invoked_as,
        description="Fetch and filter systemd journal logs across hosts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  j unit web1.example.com sshd --since 2h
  j unit --role web nginx --since 1h --priority warning
  j grep --role web "error" --since 24h
  j boots web1.example.com
  j export --role web --since 4h --out logs.ndjson
        """,
    )
    parser.add_argument("--version", "-V", action="version", version=f"gvjournal {__version__}")
    
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    
    unit_p = subparsers.add_parser("unit", help="fetch logs for a unit")
    setup_unit_parser(unit_p)
    
    grep_p = subparsers.add_parser("grep", help="search logs")
    setup_grep_parser(grep_p)
    
    boots_p = subparsers.add_parser("boots", help="list boot records")
    setup_boots_parser(boots_p)
    
    export_p = subparsers.add_parser("export", help="export logs to file")
    setup_export_parser(export_p)
    
    args = parser.parse_args()
    apply_common_args(args)
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    commands = {
        "unit": cmd_unit,
        "grep": cmd_grep,
        "boots": cmd_boots,
        "export": cmd_export,
    }
    
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
