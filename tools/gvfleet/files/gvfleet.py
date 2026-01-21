#!/usr/bin/env python3
"""
gvfleet - Host inventory and selection engine for gvtools

Provides centralized host management for all gv* tools:
- Add/remove hosts with metadata (env, roles, tags, owner)
- Select hosts by various criteria
- Quick SSH access via resolved profiles

Aliases: fleet, f, gvf

Author: Gvol (gvol@nexusystems.org)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Add gvtools lib to path
sys.path.insert(0, str(Path.home() / ".local" / "lib" / "gvtools"))

from gvcore import (
    Output, Colors, c, die,
    Host, Inventory, Target,
    SSHProfileManager,
    add_common_args, get_selector_from_args, apply_common_args,
    confirm,
)

__version__ = "1.1.2"


# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

def cmd_add(args: argparse.Namespace) -> None:
    """Add a host to inventory."""
    inventory = Inventory()
    
    name = args.hostname
    if not name:
        die("hostname is required")
    
    # Parse roles and tags
    roles = [r.strip() for r in args.roles.split(",")] if args.roles else []
    tags = [t.strip() for t in args.tags.split(",")] if args.tags else []
    
    # Extract domain from hostname
    domain = ""
    if "." in name:
        parts = name.split(".")
        if len(parts) >= 2:
            domain = ".".join(parts[-2:])
    
    host = Host(
        name=name,
        address=args.ip or "",
        port=args.port or 22,
        user=args.user or "",
        env=args.env or "",
        roles=roles,
        tags=tags,
        domain=domain,
        group=args.group or "",
        owner=args.owner or "",
    )
    
    existing = inventory.get(name)
    if existing and not args.yes:
        if not confirm(f"Host '{name}' already exists. Update?"):
            Output.info("Cancelled")
            return
    
    inventory.add(host)
    inventory.save()
    
    if Output.json_mode:
        Output.json_output({"status": "ok", "host": host.to_dict()})
    else:
        if existing:
            Output.success(f"Updated host: {c(name, Colors.CYAN)}")
        else:
            Output.success(f"Added host: {c(name, Colors.CYAN)}")
        if args.verbose:
            for key, value in host.to_dict().items():
                if value:
                    Output.keyvalue(key, str(value))


def cmd_del(args: argparse.Namespace) -> None:
    """Remove a host from inventory."""
    inventory = Inventory()
    
    name = args.hostname
    if not name:
        die("hostname is required")
    
    if not inventory.get(name):
        die(f"host not found: {name}")
    
    if not args.yes:
        if not confirm(f"Remove host '{name}'?"):
            Output.info("Cancelled")
            return
    
    inventory.remove(name)
    inventory.save()
    
    if Output.json_mode:
        Output.json_output({"status": "ok", "removed": name})
    else:
        Output.success(f"Removed host: {c(name, Colors.CYAN)}")


def cmd_list(args: argparse.Namespace) -> None:
    """List hosts in inventory."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    
    # Don't use direct target for list
    selector.direct = ""
    
    hosts = inventory.select(selector) if not selector.is_empty() else inventory.list_all()
    
    if Output.json_mode:
        Output.json_output({"hosts": [h.to_dict() for h in hosts]})
        return
    
    if not hosts:
        Output.info("No hosts found")
        return
    
    Output.header(f"Inventory ({len(hosts)} hosts)")
    
    # Build table
    headers = ["Name", "Env", "Roles", "Tags", "Owner"]
    rows = []
    for h in sorted(hosts, key=lambda x: x.name):
        rows.append([
            c(h.name, Colors.CYAN),
            h.env or "-",
            ",".join(h.roles) or "-",
            ",".join(h.tags) or "-",
            h.owner or "-",
        ])
    
    Output.table(headers, rows)


def cmd_show(args: argparse.Namespace) -> None:
    """Show details for a host."""
    inventory = Inventory()
    
    name = args.hostname
    if not name:
        die("hostname is required")
    
    host = inventory.get(name)
    if not host:
        die(f"host not found: {name}")
    
    if Output.json_mode:
        Output.json_output(host.to_dict())
        return
    
    Output.header(f"Host: {host.name}")
    
    for key, value in host.to_dict().items():
        if value:
            if isinstance(value, list):
                value = ", ".join(value)
            elif isinstance(value, dict):
                value = json.dumps(value)
            Output.keyvalue(key, str(value))


def cmd_ssh(args: argparse.Namespace) -> None:
    """SSH to a host using resolved profile."""
    inventory = Inventory()
    profiles = SSHProfileManager()
    
    name = args.hostname
    if not name:
        die("hostname is required")
    
    host = inventory.get(name)
    if not host:
        # Try as direct target
        target = Target.parse(name)
        host = Host(
            name=target.host,
            address=target.host,
            port=target.port,
            user=target.user,
        )
    
    # Resolve profile for this host
    profile = profiles.resolve(host.name)
    
    # Build SSH command
    ssh_args = ["ssh"]
    
    user = args.user or (profile.user if profile else None) or host.user
    port = host.port
    
    if profile:
        if profile.port != 22:
            port = profile.port
        if profile.key_path:
            ssh_args.extend(["-i", profile.key_path])
        if profile.agent_forward:
            ssh_args.append("-A")
        if profile.jump_host:
            ssh_args.extend(["-J", profile.jump_host])
    
    if port != 22:
        ssh_args.extend(["-p", str(port)])
    
    target_str = f"{user}@{host.effective_address}" if user else host.effective_address
    ssh_args.append(target_str)
    
    if args.dry_run:
        Output.info(f"Would run: {' '.join(ssh_args)}")
        return
    
    Output.info(f"Connecting to {c(target_str, Colors.CYAN)}...")
    os.execvp("ssh", ssh_args)


def cmd_export(args: argparse.Namespace) -> None:
    """Export inventory to file."""
    inventory = Inventory()
    hosts = inventory.list_all()
    
    data = {"hosts": {h.name: h.to_dict() for h in hosts}}
    
    fmt = args.format or "json"
    
    if fmt == "json":
        output = json.dumps(data, indent=2)
    elif fmt == "yaml":
        try:
            import yaml
            output = yaml.dump(data, default_flow_style=False)
        except ImportError:
            die("PyYAML not installed. Use --format json or install pyyaml.")
    else:
        die(f"unknown format: {fmt}")
    
    if args.output:
        Path(args.output).write_text(output + "\n")
        Output.success(f"Exported to {args.output}")
    else:
        print(output)


def cmd_import(args: argparse.Namespace) -> None:
    """Import inventory from file."""
    inventory = Inventory()
    
    path = Path(args.file)
    if not path.exists():
        die(f"file not found: {path}")
    
    content = path.read_text()
    
    try:
        if path.suffix in (".yaml", ".yml"):
            try:
                import yaml
                data = yaml.safe_load(content)
            except ImportError:
                die("PyYAML not installed")
        else:
            data = json.loads(content)
    except (json.JSONDecodeError, Exception) as e:
        die(f"failed to parse file: {e}")
    
    hosts_data = data.get("hosts", {})
    imported = 0
    
    for name, host_data in hosts_data.items():
        host_data["name"] = name
        host = Host.from_dict(host_data)
        inventory.add(host)
        imported += 1
    
    inventory.save()
    
    if Output.json_mode:
        Output.json_output({"status": "ok", "imported": imported})
    else:
        Output.success(f"Imported {imported} hosts")


# ─────────────────────────────────────────────────────────────────────────────
# Parser Setup
# ─────────────────────────────────────────────────────────────────────────────

def setup_add_parser(parser: argparse.ArgumentParser) -> None:
    """Set up add subparser."""
    parser.add_argument("hostname", help="hostname to add")
    parser.add_argument("--ip", help="IP address (if different from hostname)")
    parser.add_argument("--port", type=int, help="SSH port")
    parser.add_argument("--user", "-u", help="default SSH user")
    parser.add_argument("--env", "-e", choices=["prod", "staging", "dev"], help="environment")
    parser.add_argument("--roles", "-r", help="comma-separated roles (e.g., 'web,db')")
    parser.add_argument("--tags", "-t", help="comma-separated tags")
    parser.add_argument("--group", "-g", help="group name")
    parser.add_argument("--owner", help="owner name")
    add_common_args(parser)


def setup_del_parser(parser: argparse.ArgumentParser) -> None:
    """Set up del subparser."""
    parser.add_argument("hostname", help="hostname to remove")
    add_common_args(parser)


def setup_list_parser(parser: argparse.ArgumentParser) -> None:
    """Set up list subparser."""
    parser.add_argument("--env", "-e", choices=["prod", "staging", "dev"], help="filter by environment")
    parser.add_argument("--role", "-r", help="filter by role")
    parser.add_argument("--tag", "-t", help="filter by tag")
    parser.add_argument("--domain", "-d", help="filter by domain")
    parser.add_argument("--group", "-g", help="filter by group")
    add_common_args(parser)


def setup_show_parser(parser: argparse.ArgumentParser) -> None:
    """Set up show subparser."""
    parser.add_argument("hostname", help="hostname to show")
    add_common_args(parser)


def setup_ssh_parser(parser: argparse.ArgumentParser) -> None:
    """Set up ssh subparser."""
    parser.add_argument("hostname", help="hostname to connect to")
    parser.add_argument("--as", "-u", dest="user", help="connect as user")
    add_common_args(parser)


def setup_export_parser(parser: argparse.ArgumentParser) -> None:
    """Set up export subparser."""
    parser.add_argument("--format", "-f", choices=["json", "yaml"], default="json", help="output format")
    parser.add_argument("--output", "-o", help="output file (default: stdout)")
    add_common_args(parser)


def setup_import_parser(parser: argparse.ArgumentParser) -> None:
    """Set up import subparser."""
    parser.add_argument("file", help="file to import")
    add_common_args(parser)


# Attach setup functions to handlers
cmd_add.setup_parser = setup_add_parser  # type: ignore
cmd_del.setup_parser = setup_del_parser  # type: ignore
cmd_list.setup_parser = setup_list_parser  # type: ignore
cmd_show.setup_parser = setup_show_parser  # type: ignore
cmd_ssh.setup_parser = setup_ssh_parser  # type: ignore
cmd_export.setup_parser = setup_export_parser  # type: ignore
cmd_import.setup_parser = setup_import_parser  # type: ignore


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    """Main entry point."""
    Output.set_tool("gvfleet", "Host inventory & selection engine")
    
    # Handle version early
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(f"gvfleet {__version__}")
        sys.exit(0)
    
    invoked_as = Path(sys.argv[0]).name
    
    parser = argparse.ArgumentParser(
        prog=invoked_as,
        description="Host inventory and selection engine for gvtools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  fleet add server1.example.com --env prod --roles web,app
  fleet add db1.example.com --env prod --roles db --tags primary
  fleet list --env prod
  fleet list --role web
  fleet ssh server1.example.com
  fleet export --format yaml > inventory.yaml
  fleet import inventory.yaml
        """,
    )
    parser.add_argument("--version", "-V", action="version", version=f"gvfleet {__version__}")
    
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    
    # Add subcommands
    add_p = subparsers.add_parser("add", help="add a host to inventory")
    setup_add_parser(add_p)
    
    del_p = subparsers.add_parser("del", help="remove a host from inventory")
    setup_del_parser(del_p)
    
    list_p = subparsers.add_parser("list", help="list hosts in inventory")
    setup_list_parser(list_p)
    
    show_p = subparsers.add_parser("show", help="show host details")
    setup_show_parser(show_p)
    
    ssh_p = subparsers.add_parser("ssh", help="SSH to a host")
    setup_ssh_parser(ssh_p)
    
    export_p = subparsers.add_parser("export", help="export inventory to file")
    setup_export_parser(export_p)
    
    import_p = subparsers.add_parser("import", help="import inventory from file")
    setup_import_parser(import_p)
    
    args = parser.parse_args()
    apply_common_args(args)
    
    if not args.command:
        # Default to list
        args.env = None
        args.role = None
        args.tag = None
        args.domain = None
        args.group = None
        cmd_list(args)
        return
    
    commands = {
        "add": cmd_add,
        "del": cmd_del,
        "list": cmd_list,
        "show": cmd_show,
        "ssh": cmd_ssh,
        "export": cmd_export,
        "import": cmd_import,
    }
    
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
