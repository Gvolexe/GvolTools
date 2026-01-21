#!/usr/bin/env python3
"""
gv - GVTools help and command dispatcher

Central help and navigation for all GVTools commands.

Author: Gvol (gvol@nexusystems.org)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Import version from gvcore
sys.path.insert(0, str(Path.home() / ".local" / "lib" / "gvtools"))
try:
    from gvcore import __version__
except ImportError:
    __version__ = "unknown"


NO_COLOR = "NO_COLOR" in __import__("os").environ

def c(text: str, color: str) -> str:
    if NO_COLOR:
        return text
    return f"{color}{text}\033[0m"

class Colors:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"


TOOLS = {
    "gvfleet": {
        "aliases": ["fleet", "f", "gvf"],
        "description": "Host inventory management",
        "commands": ["add", "del", "list", "show", "ssh", "export", "import"],
        "category": "Inventory",
    },
    "gvsshprofile": {
        "aliases": ["sp", "gvsp"],
        "description": "SSH connection profiles",
        "commands": ["group add", "group del", "group list", "build", "test", "lint"],
        "category": "SSH",
    },
    "gvhostbootstrap": {
        "aliases": ["hb", "gvhb"],
        "description": "Initial host security bootstrap",
        "commands": ["init", "harden", "full", "status"],
        "category": "Security",
    },
    "gvsshaudit": {
        "aliases": ["sa", "sshaudit", "gvsa"],
        "description": "SSH configuration auditing",
        "commands": ["local", "remote", "fleet", "report"],
        "category": "SSH",
    },
    "gvknownhostsctl": {
        "aliases": ["kh", "gvkh"],
        "description": "Manage SSH known_hosts",
        "commands": ["verify", "add", "rm", "dedupe", "rename"],
        "category": "SSH",
    },
    "gvsecretsync": {
        "aliases": ["sec", "secrets", "gvs"],
        "description": "Encrypted secrets distribution",
        "commands": ["add", "put", "rotate", "status", "rm"],
        "category": "Security",
    },
    "gvcertctl": {
        "aliases": ["cert", "cc", "gvcert"],
        "description": "TLS certificate management",
        "commands": ["provider add", "issue", "renew", "deploy", "status", "revoke"],
        "category": "Certificates",
    },
    "gvfirewallctl": {
        "aliases": ["fw", "gvfw"],
        "description": "Firewall baseline management",
        "commands": ["apply", "diff", "status", "lock"],
        "category": "Security",
    },
    "gvupdates": {
        "aliases": ["upd", "gvu"],
        "description": "Security update management",
        "commands": ["enable", "check", "apply", "report"],
        "category": "System",
    },
    "gvsudoauth": {
        "aliases": ["sudoauth", "gvsu"],
        "description": "Sudo authentication config",
        "commands": ["status", "enable-agent", "disable-agent", "enable-nopasswd", "disable-nopasswd"],
        "category": "Security",
    },
    "gvlogtriage": {
        "aliases": ["lt", "logtriage", "gvlt"],
        "description": "Auth/system log analysis",
        "commands": ["ssh", "sudo", "bans", "report"],
        "category": "Monitoring",
    },
    "gvbackupctl": {
        "aliases": ["bk", "gvbk"],
        "description": "Backup configuration and verification",
        "commands": ["init", "run", "verify", "status", "restore"],
        "category": "Backup",
    },
    "gvdnscheck": {
        "aliases": ["dns", "dc", "gvdns"],
        "description": "DNS validation and consistency",
        "commands": ["lookup", "zone", "ssh-consistency", "report"],
        "category": "Network",
    },
    "gvnetdiag": {
        "aliases": ["nd", "netdiag", "gvnd"],
        "description": "Network diagnostics",
        "commands": ["local", "remote", "ports", "trace", "report"],
        "category": "Network",
    },
    "gvportsentry": {
        "aliases": ["ports", "gvps"],
        "description": "Port scanning and baselines",
        "commands": ["scan", "baseline save", "baseline diff", "report"],
        "category": "Network",
    },
    "gvdotctl": {
        "aliases": ["dt", "dot", "gvdt"],
        "description": "Dotfile management",
        "commands": ["apply", "status", "rollback", "list"],
        "category": "Config",
    },
    "gvgitopsinit": {
        "aliases": ["gi", "gitops", "gvgi"],
        "description": "GitOps repository scaffolding",
        "commands": ["new", "add-role", "add-env", "validate"],
        "category": "GitOps",
    },
    "gvpermcheck": {
        "aliases": ["pc", "perm", "gvpc"],
        "description": "Permission auditing",
        "commands": ["ssh", "sudoers", "paths", "report"],
        "category": "Security",
    },
    "gvolkeymanager": {
        "aliases": ["km", "gvkm"],
        "description": "SSH key management",
        "commands": ["generate", "push", "audit", "revoke"],
        "category": "SSH",
    },
    "gvconfigrender": {
        "aliases": ["render", "rr"],
        "description": "Template rendering and deployment",
        "commands": ["render", "deploy", "vars", "template"],
        "category": "Config",
    },
    "gvdeploy": {
        "aliases": ["dep", "run"],
        "description": "Execute commands across target sets",
        "commands": ["cmd", "script", "copy", "fetch", "results"],
        "category": "Deploy",
    },
    "gvdnsprovider": {
        "aliases": ["dnsprov", "dp"],
        "description": "DNS provider credential store",
        "commands": ["add", "list", "show", "test", "del", "export", "import"],
        "category": "Network",
    },
    "gvhealth": {
        "aliases": ["health", "hl"],
        "description": "Host and service health checks",
        "commands": ["host", "services", "endpoints", "summary", "define"],
        "category": "Monitoring",
    },
    "gvjournal": {
        "aliases": ["jrnl", "j"],
        "description": "Systemd journal log fetching",
        "commands": ["unit", "grep", "boots", "export"],
        "category": "Monitoring",
    },
    "gvmetrics": {
        "aliases": ["metrics", "mx"],
        "description": "Resource metrics and time series",
        "commands": ["snap", "record", "export", "compare"],
        "category": "Monitoring",
    },
    "gvnginxctl": {
        "aliases": ["ngx", "nx"],
        "description": "Nginx configuration management",
        "commands": ["status", "test", "reload", "restart", "logs", "site"],
        "category": "System",
    },
    "gvpolicy": {
        "aliases": ["pol", "pl"],
        "description": "Policy rules for fleet baselines",
        "commands": ["rule", "eval", "waive", "checks"],
        "category": "Security",
    },
    "gvrebootctl": {
        "aliases": ["reboot", "rb"],
        "description": "Safe reboot coordination",
        "commands": ["check", "plan", "run", "validate", "cancel"],
        "category": "System",
    },
    "gvsync": {
        "aliases": ["sync", "sy"],
        "description": "Rsync wrapper with SSH profiles",
        "commands": ["push", "pull", "mirror", "diff"],
        "category": "Deploy",
    },
    "gvsystemdctl": {
        "aliases": ["sd", "svc"],
        "description": "Fleet-safe systemd management",
        "commands": ["status", "restart", "start", "stop", "enable", "disable", "logs", "rollout"],
        "category": "System",
    },
    "gvtcptest": {
        "aliases": ["tcp", "tc"],
        "description": "TCP connectivity testing",
        "commands": ["check", "local", "explain"],
        "category": "Network",
    },
}


def print_banner() -> None:
    banner = f"""
{c('╔═══════════════════════════════════════════════════════════╗', Colors.CYAN)}
{c('║', Colors.CYAN)}  {c('GVTools', Colors.BOLD + Colors.GREEN)} - Infrastructure Management Toolkit  v{__version__}   {c('║', Colors.CYAN)}
{c('╚═══════════════════════════════════════════════════════════╝', Colors.CYAN)}
"""
    print(banner)


def cmd_list(args: argparse.Namespace) -> None:
    """List all available tools."""
    if hasattr(args, 'json') and args.json:
        print(json.dumps(TOOLS, indent=2))
        return
    
    print_banner()
    
    categories = {}
    for tool, info in TOOLS.items():
        cat = info["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append((tool, info))
    
    for cat in sorted(categories.keys()):
        print(f"\n{c(f'  {cat}', Colors.BOLD + Colors.YELLOW)}")
        print(f"  {'─' * 40}")
        
        for tool, info in sorted(categories[cat]):
            aliases = ", ".join(info["aliases"][:2])
            print(f"  {c(tool, Colors.GREEN):<20} {info['description']}")
            print(f"  {c(f'  ({aliases})', Colors.DIM)}")


def cmd_help(args: argparse.Namespace) -> None:
    """Show help for specific tool."""
    tool_name = args.tool
    
    tool_info = None
    canonical_name = None
    
    if tool_name in TOOLS:
        tool_info = TOOLS[tool_name]
        canonical_name = tool_name
    else:
        for name, info in TOOLS.items():
            if tool_name in info["aliases"]:
                tool_info = info
                canonical_name = name
                break
    
    if not tool_info:
        print(f"{c('Error:', Colors.RED)} Unknown tool: {tool_name}")
        print(f"Run {c('gv list', Colors.CYAN)} to see available tools")
        sys.exit(1)
    
    print(f"\n{c(canonical_name, Colors.BOLD + Colors.GREEN)} - {tool_info['description']}")
    print(f"\n{c('Aliases:', Colors.YELLOW)} {', '.join(tool_info['aliases'])}")
    print(f"\n{c('Commands:', Colors.YELLOW)}")
    for cmd in tool_info["commands"]:
        print(f"  • {cmd}")
    
    print(f"\n{c('For full help:', Colors.DIM)} {tool_info['aliases'][0]} --help")
    
    try:
        result = subprocess.run(
            [canonical_name, "--help"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            print(f"\n{c('─' * 50, Colors.DIM)}")
            print(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def cmd_search(args: argparse.Namespace) -> None:
    """Search for tools by keyword."""
    query = args.query.lower()
    
    matches = []
    for tool, info in TOOLS.items():
        if (query in tool.lower() or 
            query in info["description"].lower() or
            query in info["category"].lower() or
            any(query in alias.lower() for alias in info["aliases"]) or
            any(query in cmd.lower() for cmd in info["commands"])):
            matches.append((tool, info))
    
    if not matches:
        print(f"{c('No matches for:', Colors.YELLOW)} {query}")
        return
    
    print(f"\n{c(f'Found {len(matches)} match(es) for:', Colors.GREEN)} {query}\n")
    
    for tool, info in matches:
        aliases = ", ".join(info["aliases"][:2])
        print(f"  {c(tool, Colors.CYAN):<20} {info['description']}")
        print(f"  {c(f'  aliases: {aliases}', Colors.DIM)}")
        print()


def cmd_version(args: argparse.Namespace) -> None:
    """Show version info."""
    print(f"GVTools v{__version__}")
    print(f"Tools installed: {len(TOOLS)}")
    print("\nAuthor: Gvol (gvol@nexusystems.org)")
    print("GitHub: https://github.com/Gvolexe/GvolTools")


def main() -> None:
    if len(sys.argv) == 1:
        cmd_list(argparse.Namespace(json=False))
        return
    
    if sys.argv[1] in ("--version", "-V"):
        cmd_version(argparse.Namespace())
        return
    
    parser = argparse.ArgumentParser(
        prog="gv",
        description="GVTools - Infrastructure Management Toolkit",
        epilog="""
Examples:
  gv                    Show all available tools
  gv list               List tools by category
  gv help fleet         Show help for gvfleet
  gv search ssh         Search for SSH-related tools
  gv version            Show version info
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", "-V", action="version", version=f"gv {__version__}")
    
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    
    list_p = subparsers.add_parser("list", help="list all tools")
    list_p.add_argument("--json", action="store_true", help="JSON output")
    
    help_p = subparsers.add_parser("help", help="show tool help")
    help_p.add_argument("tool", help="tool name or alias")
    
    search_p = subparsers.add_parser("search", help="search tools")
    search_p.add_argument("query", help="search keyword")
    
    version_p = subparsers.add_parser("version", help="show version")
    
    args = parser.parse_args()
    
    commands = {
        "list": cmd_list,
        "help": cmd_help,
        "search": cmd_search,
        "version": cmd_version,
    }
    
    if args.command in commands:
        commands[args.command](args)
    elif args.command in TOOLS or any(args.command in info["aliases"] for info in TOOLS.values()):
        args_obj = argparse.Namespace(tool=args.command)
        cmd_help(args_obj)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
