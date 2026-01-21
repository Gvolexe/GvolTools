#!/usr/bin/env python3
"""
gvsshprofile - SSH connection profiles and config generation

Maintain SSH connection profiles/groups and generate/validate ~/.ssh/config.

Aliases: sp, gvsp

Author: Gvol (gvol@nexusystems.org)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Add gvtools lib to path
sys.path.insert(0, str(Path.home() / ".local" / "lib" / "gvtools"))

from gvcore import (
    Output, Colors, c, die,
    SSHProfile, SSHProfileManager,
    add_common_args, apply_common_args,
    confirm, DEFAULT_SSH_PORT,
)

__version__ = "0.5.0"


# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

def cmd_group_add(args: argparse.Namespace) -> None:
    """Add or update an SSH profile group."""
    manager = SSHProfileManager()
    
    name = args.name
    if not name:
        die("group name is required")
    
    patterns = [p.strip() for p in args.domains.split(",")] if args.domains else []
    if not patterns:
        die("--domains is required")
    
    profile = SSHProfile(
        name=name,
        patterns=patterns,
        user=args.user or "",
        port=args.port or DEFAULT_SSH_PORT,
        key=args.key or "",
        key_path=args.key_path or "",
        jump_host=args.jump or "",
        agent_forward=args.agent == "on" if args.agent else False,
    )
    
    existing = manager.get(name)
    if existing and not args.yes:
        if not confirm(f"Profile '{name}' exists. Update?"):
            Output.info("Cancelled")
            return
    
    manager.add(profile)
    manager.save()
    
    if Output.json_mode:
        Output.json_output({"status": "ok", "profile": profile.to_dict()})
    else:
        action = "Updated" if existing else "Added"
        Output.success(f"{action} profile: {c(name, Colors.CYAN)}")
        Output.keyvalue("patterns", ", ".join(patterns))
        if profile.user:
            Output.keyvalue("user", profile.user)
        if profile.key or profile.key_path:
            Output.keyvalue("key", profile.key or profile.key_path)
        if profile.jump_host:
            Output.keyvalue("jump", profile.jump_host)


def cmd_group_del(args: argparse.Namespace) -> None:
    """Remove an SSH profile group."""
    manager = SSHProfileManager()
    
    name = args.name
    if not name:
        die("group name is required")
    
    if not manager.get(name):
        die(f"profile not found: {name}")
    
    if not args.yes:
        if not confirm(f"Remove profile '{name}'?"):
            Output.info("Cancelled")
            return
    
    manager.remove(name)
    manager.save()
    
    if Output.json_mode:
        Output.json_output({"status": "ok", "removed": name})
    else:
        Output.success(f"Removed profile: {c(name, Colors.CYAN)}")


def cmd_group_list(args: argparse.Namespace) -> None:
    """List SSH profile groups."""
    manager = SSHProfileManager()
    profiles = manager.list_all()
    
    if Output.json_mode:
        Output.json_output({"profiles": [p.to_dict() for p in profiles]})
        return
    
    if not profiles:
        Output.info("No profiles defined")
        Output.step("Use: sp group add <name> --domains '*.example.com' --key mykey")
        return
    
    Output.header(f"SSH Profiles ({len(profiles)})")
    
    headers = ["Name", "Patterns", "User", "Key", "Jump"]
    rows = []
    for p in sorted(profiles, key=lambda x: x.name):
        rows.append([
            c(p.name, Colors.CYAN),
            ", ".join(p.patterns[:2]) + ("..." if len(p.patterns) > 2 else ""),
            p.user or "-",
            p.key or p.key_path or "-",
            p.jump_host or "-",
        ])
    
    Output.table(headers, rows)


def cmd_build(args: argparse.Namespace) -> None:
    """Generate ~/.ssh/config from profiles."""
    manager = SSHProfileManager()
    
    config_content = manager.generate_ssh_config()
    
    output_path = Path(args.out).expanduser() if args.out else Path.home() / ".ssh" / "config.gvtools"
    
    if args.dry_run:
        Output.info("Would write to: " + str(output_path))
        print()
        print(config_content)
        return
    
    # Create backup if exists
    if output_path.exists():
        backup = output_path.with_suffix(".bak")
        output_path.rename(backup)
        Output.step(f"Backed up to {backup}")
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(config_content)
    output_path.chmod(0o600)
    
    if Output.json_mode:
        Output.json_output({"status": "ok", "path": str(output_path)})
    else:
        Output.success(f"Generated: {c(str(output_path), Colors.CYAN)}")
        Output.step("Include in ~/.ssh/config with:")
        print(f"    Include {output_path}")


def cmd_test(args: argparse.Namespace) -> None:
    """Show resolved params for a host."""
    manager = SSHProfileManager()
    
    hostname = args.hostname
    if not hostname:
        die("hostname is required")
    
    profile = manager.resolve(hostname)
    
    if Output.json_mode:
        if profile:
            Output.json_output({"match": True, "profile": profile.to_dict()})
        else:
            Output.json_output({"match": False, "profile": None})
        return
    
    Output.header(f"Profile for: {hostname}")
    
    if not profile:
        Output.warn("No matching profile found")
        Output.step("Host will use default SSH settings")
        return
    
    Output.success(f"Matched profile: {c(profile.name, Colors.CYAN)}")
    Output.keyvalue("user", profile.user or "(default)")
    Output.keyvalue("port", str(profile.port))
    Output.keyvalue("key", profile.key or profile.key_path or "(default)")
    Output.keyvalue("jump", profile.jump_host or "(none)")
    Output.keyvalue("agent", "yes" if profile.agent_forward else "no")


def cmd_lint(args: argparse.Namespace) -> None:
    """Check for overlaps/precedence issues."""
    manager = SSHProfileManager()
    profiles = manager.list_all()
    
    issues = []
    
    # Check for overlapping patterns
    all_patterns: dict[str, list[str]] = {}
    for profile in profiles:
        for pattern in profile.patterns:
            if pattern in all_patterns:
                issues.append({
                    "type": "overlap",
                    "pattern": pattern,
                    "profiles": all_patterns[pattern] + [profile.name],
                })
            else:
                all_patterns[pattern] = []
            all_patterns[pattern].append(profile.name)
    
    # Check for missing keys
    for profile in profiles:
        if profile.key_path and not Path(profile.key_path).expanduser().exists():
            issues.append({
                "type": "missing_key",
                "profile": profile.name,
                "path": profile.key_path,
            })
    
    if Output.json_mode:
        Output.json_output({"issues": issues, "ok": len(issues) == 0})
        return
    
    if not issues:
        Output.success("No issues found")
        return
    
    Output.header(f"Found {len(issues)} issues")
    
    for issue in issues:
        if issue["type"] == "overlap":
            Output.warn(f"Pattern '{issue['pattern']}' in multiple profiles: {', '.join(issue['profiles'])}")
        elif issue["type"] == "missing_key":
            Output.warn(f"Profile '{issue['profile']}' references missing key: {issue['path']}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    """Main entry point."""
    Output.set_tool("gvsshprofile", "SSH connection profiles")
    
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(f"gvsshprofile {__version__}")
        sys.exit(0)
    
    invoked_as = Path(sys.argv[0]).name
    
    parser = argparse.ArgumentParser(
        prog=invoked_as,
        description="SSH connection profiles and config generation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  sp group add work --domains "*.company.com" --user admin --key work_key
  sp group add personal --domains "*.home.lan,pi*" --agent on
  sp group list
  sp build
  sp test server.company.com
  sp lint
        """,
    )
    parser.add_argument("--version", "-V", action="version", version=f"gvsshprofile {__version__}")
    
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    
    # Group subcommand with its own subcommands
    group_parser = subparsers.add_parser("group", help="manage profile groups")
    group_sub = group_parser.add_subparsers(dest="group_command", metavar="action")
    
    # group add
    add_p = group_sub.add_parser("add", help="add or update a profile group")
    add_p.add_argument("name", help="profile group name")
    add_p.add_argument("--domains", "-d", required=True, help="comma-separated domain/host patterns")
    add_p.add_argument("--key", "-k", help="key name from keymanager")
    add_p.add_argument("--key-path", help="direct path to private key")
    add_p.add_argument("--user", "-u", help="default SSH user")
    add_p.add_argument("--port", "-p", type=int, help="SSH port")
    add_p.add_argument("--jump", "-j", help="jump/bastion host")
    add_p.add_argument("--agent", choices=["on", "off"], help="agent forwarding")
    add_common_args(add_p)
    
    # group del
    del_p = group_sub.add_parser("del", help="remove a profile group")
    del_p.add_argument("name", help="profile group name")
    add_common_args(del_p)
    
    # group list
    list_p = group_sub.add_parser("list", help="list profile groups")
    add_common_args(list_p)
    
    # build
    build_p = subparsers.add_parser("build", help="generate SSH config")
    build_p.add_argument("--out", "-o", help="output path (default: ~/.ssh/config.gvtools)")
    add_common_args(build_p)
    
    # test
    test_p = subparsers.add_parser("test", help="show resolved params for host")
    test_p.add_argument("hostname", help="hostname to test")
    add_common_args(test_p)
    
    # lint
    lint_p = subparsers.add_parser("lint", help="check for issues")
    add_common_args(lint_p)
    
    args = parser.parse_args()
    apply_common_args(args)
    
    if args.command == "group":
        if not args.group_command:
            group_parser.print_help()
            return
        if args.group_command == "add":
            cmd_group_add(args)
        elif args.group_command == "del":
            cmd_group_del(args)
        elif args.group_command == "list":
            cmd_group_list(args)
    elif args.command == "build":
        cmd_build(args)
    elif args.command == "test":
        cmd_test(args)
    elif args.command == "lint":
        cmd_lint(args)
    elif not args.command:
        # Default to list
        cmd_group_list(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
