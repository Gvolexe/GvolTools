#!/usr/bin/env python3
"""
gvcore - Shared library for gvtools

Provides common functionality for all gv* tools:
- Terminal colors and output formatting
- Configuration management (XDG paths)
- Target selection (hosts, inventory, selectors)
- SSH connection handling
- Common CLI patterns

Author: Gvol (gvol@nexusystems.org)
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

try:
    import paramiko
except ImportError:
    paramiko = None

__version__ = "1.1.0"

# ─────────────────────────────────────────────────────────────────────────────
# XDG Paths
# ─────────────────────────────────────────────────────────────────────────────

XDG_CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
XDG_DATA_HOME = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))

GVTOOLS_CONFIG = XDG_CONFIG_HOME / "gvtools"
GVTOOLS_DATA = XDG_DATA_HOME / "gvtools"

INVENTORY_PATH = GVTOOLS_CONFIG / "inventory.json"
SSH_PROFILES_PATH = GVTOOLS_CONFIG / "sshprofiles.json"
SECRETS_PATH = GVTOOLS_CONFIG / "secrets"


# ─────────────────────────────────────────────────────────────────────────────
# Terminal Colors
# ─────────────────────────────────────────────────────────────────────────────

class Colors:
    """ANSI color codes for terminal output."""
    
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"
    
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"
    
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"
    
    @classmethod
    def enabled(cls) -> bool:
        """Check if colors should be enabled."""
        if os.environ.get("NO_COLOR"):
            return False
        if not sys.stdout.isatty():
            return False
        return True


def c(text: str, *codes: str) -> str:
    """Apply color codes to text if colors are enabled."""
    if not Colors.enabled():
        return text
    return "".join(codes) + text + Colors.RESET


# ─────────────────────────────────────────────────────────────────────────────
# Output Helpers
# ─────────────────────────────────────────────────────────────────────────────

class Output:
    """Structured output with consistent formatting."""
    
    verbose = False
    json_mode = False
    _tool_name = "gvtools"
    _tool_desc = "gvtools utility"
    
    @classmethod
    def set_tool(cls, name: str, desc: str) -> None:
        """Set tool name for banners."""
        cls._tool_name = name
        cls._tool_desc = desc
    
    @classmethod
    def banner(cls, subtitle: str = "") -> None:
        """Print application banner."""
        if cls.json_mode:
            return
        name = cls._tool_name
        desc = subtitle or cls._tool_desc
        width = max(len(name) + 8, len(desc) + 8, 42)
        
        lines = [
            "",
            c("╭" + "─" * (width - 2) + "╮", Colors.CYAN),
            c("│", Colors.CYAN) + f"{name:^{width - 2}}" + c("│", Colors.CYAN),
            c("│", Colors.CYAN) + c(f"{desc:^{width - 2}}", Colors.DIM) + c("│", Colors.CYAN),
            c("╰" + "─" * (width - 2) + "╯", Colors.CYAN),
        ]
        for line in lines:
            print(line)
    
    @staticmethod
    def error(msg: str) -> None:
        prefix = c("✖ error:", Colors.RED, Colors.BOLD)
        print(f"{prefix} {msg}", file=sys.stderr)
    
    @staticmethod
    def success(msg: str) -> None:
        prefix = c("✔", Colors.GREEN, Colors.BOLD)
        print(f"{prefix} {msg}")
    
    @staticmethod
    def warn(msg: str) -> None:
        prefix = c("⚠ warning:", Colors.YELLOW, Colors.BOLD)
        print(f"{prefix} {msg}", file=sys.stderr)
    
    @staticmethod
    def info(msg: str) -> None:
        prefix = c("→", Colors.BLUE, Colors.BOLD)
        print(f"{prefix} {msg}")
    
    @staticmethod
    def step(msg: str) -> None:
        prefix = c("  •", Colors.DIM)
        print(f"{prefix} {msg}")
    
    @staticmethod
    def debug(msg: str) -> None:
        if Output.verbose:
            prefix = c("  ⋯", Colors.DIM)
            print(f"{prefix} {msg}")
    
    @staticmethod
    def header(msg: str) -> None:
        if Output.json_mode:
            return
        width = max(len(msg) + 4, 40)
        print()
        print(c("┌" + "─" * (width - 2) + "┐", Colors.CYAN))
        padding = width - len(msg) - 4
        left_pad = padding // 2
        right_pad = padding - left_pad
        print(c("│", Colors.CYAN) + " " * (left_pad + 1) + c(msg, Colors.BOLD) + " " * (right_pad + 1) + c("│", Colors.CYAN))
        print(c("└" + "─" * (width - 2) + "┘", Colors.CYAN))
    
    @staticmethod
    def divider() -> None:
        if not Output.json_mode:
            print(c("─" * 40, Colors.DIM))
    
    @staticmethod
    def keyvalue(key: str, value: str, indent: int = 2) -> None:
        if Output.json_mode:
            return
        prefix = " " * indent
        print(f"{prefix}{c(key + ':', Colors.DIM)} {value}")
    
    @staticmethod
    def option(num: str, text: str, desc: str = "") -> None:
        """Print a menu option."""
        if Output.json_mode:
            return
        opt = f"    {c(num + ')', Colors.CYAN, Colors.BOLD)} {text}"
        if desc:
            opt += f" {c(desc, Colors.DIM)}"
        print(opt)
    
    @staticmethod
    def table(headers: list[str], rows: list[list[str]], indent: int = 2) -> None:
        """Print a formatted table."""
        if Output.json_mode:
            return
        
        # Calculate column widths
        widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(widths):
                    widths[i] = max(widths[i], len(str(cell)))
        
        prefix = " " * indent
        
        # Header
        header_line = " │ ".join(c(h.ljust(widths[i]), Colors.BOLD) for i, h in enumerate(headers))
        print(f"{prefix}{header_line}")
        
        # Separator
        sep_line = "─┼─".join("─" * w for w in widths)
        print(f"{prefix}{c(sep_line, Colors.DIM)}")
        
        # Rows
        for row in rows:
            row_line = " │ ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row))
            print(f"{prefix}{row_line}")
    
    @staticmethod
    def json_output(data: Any) -> None:
        """Print JSON output."""
        print(json.dumps(data, indent=2, default=str))


def die(msg: str, code: int = 1) -> None:
    """Print error and exit."""
    Output.error(msg)
    sys.exit(code)


# ─────────────────────────────────────────────────────────────────────────────
# Host/Target Handling
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_SSH_PORT = 22


@dataclass
class Host:
    """Represents a host in the inventory or a direct target."""
    name: str
    address: str = ""
    port: int = DEFAULT_SSH_PORT
    user: str = ""
    env: str = ""  # prod, staging, dev
    roles: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    domain: str = ""
    group: str = ""
    owner: str = ""
    ssh_profile: str = ""
    metadata: dict = field(default_factory=dict)
    
    @property
    def effective_address(self) -> str:
        """Get the address to connect to."""
        return self.address or self.name
    
    def matches_selector(self, selector: "TargetSelector") -> bool:
        """Check if host matches selector criteria."""
        if selector.host and not fnmatch.fnmatch(self.name, selector.host):
            return False
        if selector.domain and not self.name.endswith(selector.domain):
            return False
        if selector.env and self.env != selector.env:
            return False
        if selector.role and selector.role not in self.roles:
            return False
        if selector.tag and selector.tag not in self.tags:
            return False
        if selector.group and self.group != selector.group:
            return False
        if selector.glob and not fnmatch.fnmatch(self.name, selector.glob):
            return False
        return True
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "address": self.address,
            "port": self.port,
            "user": self.user,
            "env": self.env,
            "roles": self.roles,
            "tags": self.tags,
            "domain": self.domain,
            "group": self.group,
            "owner": self.owner,
            "ssh_profile": self.ssh_profile,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Host":
        return cls(
            name=data.get("name", ""),
            address=data.get("address", ""),
            port=data.get("port", DEFAULT_SSH_PORT),
            user=data.get("user", ""),
            env=data.get("env", ""),
            roles=data.get("roles", []),
            tags=data.get("tags", []),
            domain=data.get("domain", ""),
            group=data.get("group", ""),
            owner=data.get("owner", ""),
            ssh_profile=data.get("ssh_profile", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class TargetSelector:
    """Selector for filtering hosts from inventory."""
    host: str = ""
    domain: str = ""
    env: str = ""
    role: str = ""
    tag: str = ""
    group: str = ""
    glob: str = ""
    file: str = ""  # hosts.txt file
    direct: str = ""  # Direct user@host[:port]
    
    def is_empty(self) -> bool:
        return not any([
            self.host, self.domain, self.env, self.role, 
            self.tag, self.group, self.glob, self.file, self.direct
        ])


@dataclass
class Target:
    """Parsed SSH target with connection details."""
    user: str
    host: str
    port: int
    
    @classmethod
    def parse(cls, target: str) -> "Target":
        """Parse user@host[:port] format."""
        if "@" not in target:
            # Just hostname - no user
            host = target
            port = DEFAULT_SSH_PORT
            user = ""
            
            if ":" in host:
                h, p = host.rsplit(":", 1)
                if p.isdigit():
                    host, port = h, int(p)
            
            return cls(user=user, host=host, port=port)
        
        user, hostpart = target.split("@", 1)
        host = hostpart
        port = DEFAULT_SSH_PORT
        
        if ":" in hostpart:
            h, p = hostpart.rsplit(":", 1)
            if p.isdigit():
                host, port = h, int(p)
        
        return cls(user=user, host=host, port=port)
    
    @classmethod
    def from_host(cls, host: Host, default_user: str = "") -> "Target":
        """Create target from inventory Host."""
        return cls(
            user=host.user or default_user,
            host=host.effective_address,
            port=host.port,
        )
    
    def __str__(self) -> str:
        parts = []
        if self.user:
            parts.append(f"{self.user}@{self.host}")
        else:
            parts.append(self.host)
        if self.port != DEFAULT_SSH_PORT:
            return f"{parts[0]}:{self.port}"
        return parts[0]


# ─────────────────────────────────────────────────────────────────────────────
# Inventory
# ─────────────────────────────────────────────────────────────────────────────

class Inventory:
    """Host inventory manager."""
    
    def __init__(self, path: Path = INVENTORY_PATH):
        self.path = path
        self.hosts: dict[str, Host] = {}
        self._load()
    
    def _load(self) -> None:
        """Load inventory from file."""
        if not self.path.exists():
            return
        
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            for name, host_data in data.get("hosts", {}).items():
                host_data["name"] = name
                self.hosts[name] = Host.from_dict(host_data)
        except (json.JSONDecodeError, OSError) as e:
            Output.warn(f"could not load inventory: {e}")
    
    def save(self) -> None:
        """Save inventory to file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "hosts": {name: host.to_dict() for name, host in self.hosts.items()}
        }
        self.path.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8"
        )
    
    def add(self, host: Host) -> None:
        """Add or update a host."""
        self.hosts[host.name] = host
    
    def remove(self, name: str) -> bool:
        """Remove a host by name."""
        if name in self.hosts:
            del self.hosts[name]
            return True
        return False
    
    def get(self, name: str) -> Host | None:
        """Get a host by name."""
        return self.hosts.get(name)
    
    def select(self, selector: TargetSelector) -> list[Host]:
        """Select hosts matching selector."""
        if selector.direct:
            # Direct target - parse and return as Host
            target = Target.parse(selector.direct)
            return [Host(
                name=target.host,
                address=target.host,
                port=target.port,
                user=target.user,
            )]
        
        if selector.file:
            # Load from file
            try:
                lines = Path(selector.file).read_text().strip().split("\n")
                hosts = []
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        target = Target.parse(line)
                        hosts.append(Host(
                            name=target.host,
                            address=target.host,
                            port=target.port,
                            user=target.user,
                        ))
                return hosts
            except OSError as e:
                die(f"cannot read hosts file: {e}")
        
        if selector.is_empty():
            return list(self.hosts.values())
        
        return [h for h in self.hosts.values() if h.matches_selector(selector)]
    
    def list_all(self) -> list[Host]:
        """List all hosts."""
        return list(self.hosts.values())


# ─────────────────────────────────────────────────────────────────────────────
# SSH Profiles
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SSHProfile:
    """SSH connection profile for a group of hosts."""
    name: str
    patterns: list[str]  # Domain/host patterns
    user: str = ""
    port: int = DEFAULT_SSH_PORT
    key: str = ""  # Key name from keymanager
    key_path: str = ""  # Direct key path
    jump_host: str = ""  # Bastion/jump host
    agent_forward: bool = False
    options: dict[str, str] = field(default_factory=dict)
    
    def matches(self, hostname: str) -> bool:
        """Check if hostname matches any pattern."""
        for pattern in self.patterns:
            if fnmatch.fnmatch(hostname, pattern):
                return True
        return False
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "patterns": self.patterns,
            "user": self.user,
            "port": self.port,
            "key": self.key,
            "key_path": self.key_path,
            "jump_host": self.jump_host,
            "agent_forward": self.agent_forward,
            "options": self.options,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "SSHProfile":
        return cls(
            name=data.get("name", ""),
            patterns=data.get("patterns", []),
            user=data.get("user", ""),
            port=data.get("port", DEFAULT_SSH_PORT),
            key=data.get("key", ""),
            key_path=data.get("key_path", ""),
            jump_host=data.get("jump_host", ""),
            agent_forward=data.get("agent_forward", False),
            options=data.get("options", {}),
        )


class SSHProfileManager:
    """Manage SSH connection profiles."""
    
    def __init__(self, path: Path = SSH_PROFILES_PATH):
        self.path = path
        self.profiles: dict[str, SSHProfile] = {}
        self._load()
    
    def _load(self) -> None:
        """Load profiles from file."""
        if not self.path.exists():
            return
        
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            for name, profile_data in data.get("profiles", {}).items():
                profile_data["name"] = name
                self.profiles[name] = SSHProfile.from_dict(profile_data)
        except (json.JSONDecodeError, OSError) as e:
            Output.warn(f"could not load SSH profiles: {e}")
    
    def save(self) -> None:
        """Save profiles to file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "profiles": {name: p.to_dict() for name, p in self.profiles.items()}
        }
        self.path.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8"
        )
    
    def add(self, profile: SSHProfile) -> None:
        """Add or update a profile."""
        self.profiles[profile.name] = profile
    
    def remove(self, name: str) -> bool:
        """Remove a profile."""
        if name in self.profiles:
            del self.profiles[name]
            return True
        return False
    
    def get(self, name: str) -> SSHProfile | None:
        """Get profile by name."""
        return self.profiles.get(name)
    
    def resolve(self, hostname: str) -> SSHProfile | None:
        """Find first matching profile for hostname."""
        for profile in self.profiles.values():
            if profile.matches(hostname):
                return profile
        return None
    
    def list_all(self) -> list[SSHProfile]:
        """List all profiles."""
        return list(self.profiles.values())
    
    def generate_ssh_config(self) -> str:
        """Generate ~/.ssh/config content from profiles."""
        lines = [
            "# Generated by gvsshprofile",
            "# Do not edit manually - changes will be overwritten",
            "",
        ]
        
        for profile in self.profiles.values():
            for pattern in profile.patterns:
                lines.append(f"Host {pattern}")
                if profile.user:
                    lines.append(f"    User {profile.user}")
                if profile.port != DEFAULT_SSH_PORT:
                    lines.append(f"    Port {profile.port}")
                if profile.key_path:
                    lines.append(f"    IdentityFile {profile.key_path}")
                if profile.jump_host:
                    lines.append(f"    ProxyJump {profile.jump_host}")
                if profile.agent_forward:
                    lines.append("    ForwardAgent yes")
                for key, value in profile.options.items():
                    lines.append(f"    {key} {value}")
                lines.append("")
        
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# SSH Operations
# ─────────────────────────────────────────────────────────────────────────────

def check_paramiko() -> None:
    """Ensure paramiko is available."""
    if paramiko is None:
        die(
            "paramiko is not installed\n"
            "  Install with: pip install paramiko\n"
            "  Or use: ./installgvtools.sh install gvcore --deps"
        )


def ssh_connect(
    target: Target,
    password: str = "",
    key_path: str = "",
    strict_hostkey: bool = False,
    timeout: int = 15,
) -> "paramiko.SSHClient":
    """Establish SSH connection."""
    check_paramiko()
    
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    
    if strict_hostkey:
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
    else:
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        Output.debug("host key verification disabled (use --strict-hostkey for production)")
    
    Output.debug(f"connecting to {target}...")
    
    connect_kwargs = {
        "hostname": target.host,
        "port": target.port,
        "username": target.user,
        "timeout": timeout,
        "banner_timeout": timeout,
        "auth_timeout": timeout,
    }
    
    if password:
        connect_kwargs["password"] = password
        connect_kwargs["look_for_keys"] = False
        connect_kwargs["allow_agent"] = False
    elif key_path:
        connect_kwargs["key_filename"] = key_path
        connect_kwargs["look_for_keys"] = False
        connect_kwargs["allow_agent"] = False
    else:
        # Use default keys and agent
        connect_kwargs["look_for_keys"] = True
        connect_kwargs["allow_agent"] = True
    
    try:
        client.connect(**connect_kwargs)
    except paramiko.AuthenticationException:
        die("authentication failed - check credentials")
    except paramiko.SSHException as e:
        die(f"SSH error: {e}")
    except OSError as e:
        die(f"connection failed: {e}")
    
    Output.debug("connected successfully")
    return client


def ssh_exec(
    client: "paramiko.SSHClient",
    command: str,
    sudo: bool = False,
    password: str = "",
) -> tuple[int, str, str]:
    """Execute command on remote host."""
    if sudo:
        cmd = f"sudo -S -p '' sh -lc {shlex.quote(command)}"
        stdin, stdout, stderr = client.exec_command(cmd, get_pty=True)
        if password:
            stdin.write(password + "\n")
            stdin.flush()
    else:
        cmd = f"sh -lc {shlex.quote(command)}"
        stdin, stdout, stderr = client.exec_command(cmd)
    
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    
    return exit_code, out, err


def local_exec(command: str, capture: bool = True) -> tuple[int, str, str]:
    """Execute command locally."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=capture,
            text=True,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.SubprocessError as e:
        return 1, "", str(e)


# ─────────────────────────────────────────────────────────────────────────────
# Common CLI Patterns
# ─────────────────────────────────────────────────────────────────────────────

def add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add common arguments to parser."""
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would happen without making changes",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="output in JSON format",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="verbose output",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=15,
        help="connection timeout in seconds (default: 15)",
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="non-interactive mode, assume yes",
    )
    parser.add_argument(
        "--strict-hostkey",
        action="store_true",
        help="reject unknown SSH host keys",
    )


def add_target_args(parser: argparse.ArgumentParser) -> None:
    """Add target selection arguments to parser."""
    group = parser.add_argument_group("target selection")
    group.add_argument(
        "target",
        nargs="?",
        help="direct target: user@host[:port] or hostname",
    )
    group.add_argument(
        "--host",
        help="select by hostname pattern",
    )
    group.add_argument(
        "--tag",
        help="select by tag",
    )
    group.add_argument(
        "--role",
        help="select by role",
    )
    group.add_argument(
        "--env",
        choices=["prod", "staging", "dev"],
        help="select by environment",
    )
    group.add_argument(
        "--domain",
        help="select by domain suffix",
    )
    group.add_argument(
        "--group",
        help="select by group",
    )
    group.add_argument(
        "--targets",
        help="glob pattern for hostnames",
    )
    group.add_argument(
        "--file",
        help="file containing list of hosts",
    )


def get_selector_from_args(args: argparse.Namespace) -> TargetSelector:
    """Build TargetSelector from parsed arguments."""
    return TargetSelector(
        direct=getattr(args, "target", "") or "",
        host=getattr(args, "host", "") or "",
        tag=getattr(args, "tag", "") or "",
        role=getattr(args, "role", "") or "",
        env=getattr(args, "env", "") or "",
        domain=getattr(args, "domain", "") or "",
        group=getattr(args, "group", "") or "",
        glob=getattr(args, "targets", "") or "",
        file=getattr(args, "file", "") or "",
    )


def apply_common_args(args: argparse.Namespace) -> None:
    """Apply common arguments to Output settings."""
    Output.verbose = getattr(args, "verbose", False)
    Output.json_mode = getattr(args, "json_output", False)


def confirm(prompt: str, default: bool = False) -> bool:
    """Ask for confirmation."""
    if not sys.stdin.isatty():
        return default
    
    suffix = " [Y/n] " if default else " [y/N] "
    try:
        response = input(prompt + suffix).strip().lower()
        if not response:
            return default
        return response in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Tool Registry (for gv help)
# ─────────────────────────────────────────────────────────────────────────────

TOOL_REGISTRY: dict[str, dict] = {
    "gvfleet": {
        "aliases": ["fleet", "f", "gvf"],
        "description": "Host inventory and selection engine",
        "commands": ["add", "del", "list", "show", "ssh", "export", "import"],
    },
    "gvsshprofile": {
        "aliases": ["sp", "gvsp"],
        "description": "SSH connection profiles and config generation",
        "commands": ["group add", "group del", "group list", "build", "test", "lint"],
    },
    "gvhostbootstrap": {
        "aliases": ["hb", "gvhb"],
        "description": "Bootstrap hosts to secure baseline",
        "commands": ["init", "harden", "full", "status"],
    },
    "gvsshaudit": {
        "aliases": ["sa", "sshaudit", "gvsa"],
        "description": "Audit SSH server config and access",
        "commands": ["local", "remote", "fleet", "report"],
    },
    "gvknownhostsctl": {
        "aliases": ["kh", "gvkh"],
        "description": "Manage known_hosts safely",
        "commands": ["verify", "add", "rm", "dedupe", "rename"],
    },
    "gvsecretsync": {
        "aliases": ["sec", "secrets", "gvs"],
        "description": "Encrypted secrets management and deployment",
        "commands": ["add", "put", "rotate", "status", "rm"],
    },
    "gvcertctl": {
        "aliases": ["cert", "cc", "gvcert"],
        "description": "TLS certificate issuance and deployment",
        "commands": ["provider add", "issue", "renew", "deploy", "status", "revoke"],
    },
    "gvfirewallctl": {
        "aliases": ["fw", "gvfw"],
        "description": "Firewall baseline management",
        "commands": ["apply", "diff", "status", "lock"],
    },
    "gvupdates": {
        "aliases": ["upd", "gvu"],
        "description": "Security updates management",
        "commands": ["enable", "check", "apply", "report"],
    },
    "gvsudoauth": {
        "aliases": ["su", "sudoauth", "gvsu"],
        "description": "Sudo authentication configuration",
        "commands": ["status", "enable-agent", "disable-agent", "enable-nopasswd", "disable-nopasswd"],
    },
    "gvlogtriage": {
        "aliases": ["lt", "logtriage", "gvlt"],
        "description": "Auth/system log analysis",
        "commands": ["ssh", "sudo", "bans", "report"],
    },
    "gvbackupctl": {
        "aliases": ["bk", "backup", "gvbk"],
        "description": "Backup configuration and verification",
        "commands": ["init", "run", "verify", "status", "restore"],
    },
    "gvdnscheck": {
        "aliases": ["dns", "dc", "gvdns"],
        "description": "DNS record validation",
        "commands": ["lookup", "zone", "ssh-consistency", "report"],
    },
    "gvnetdiag": {
        "aliases": ["nd", "netdiag", "gvnd"],
        "description": "Network diagnostics",
        "commands": ["local", "remote", "ports", "trace", "report"],
    },
    "gvportsentry": {
        "aliases": ["ps", "ports", "gvps"],
        "description": "Port/service baseline management",
        "commands": ["scan", "baseline save", "baseline diff", "report"],
    },
    "gvdotctl": {
        "aliases": ["dt", "dot", "gvdt"],
        "description": "Workstation dotfile management",
        "commands": ["apply", "status", "rollback", "list"],
    },
    "gvgitopsinit": {
        "aliases": ["gi", "gitops", "gvgi"],
        "description": "GitOps repo scaffolding",
        "commands": ["new", "add-role", "add-env", "validate"],
    },
    "gvpermcheck": {
        "aliases": ["pc", "perm", "gvpc"],
        "description": "Permission/ownership auditing",
        "commands": ["ssh", "sudoers", "paths", "report"],
    },
    "gvolkeymanager": {
        "aliases": ["keyup", "keyconf"],
        "description": "SSH key upload and registry",
        "commands": ["keyup", "keyconf add", "keyconf del", "keyconf list", "keyconf prefs"],
    },
}


def get_all_tools() -> list[dict]:
    """Get list of all registered tools with their info."""
    tools = []
    for name, info in sorted(TOOL_REGISTRY.items()):
        tools.append({
            "name": name,
            "aliases": info["aliases"],
            "description": info["description"],
            "commands": info["commands"],
        })
    return tools


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point Helper
# ─────────────────────────────────────────────────────────────────────────────

def run_tool(
    tool_name: str,
    tool_desc: str,
    version: str,
    subcommands: dict[str, Callable],
    default_subcommand: str = "",
) -> None:
    """
    Standard entry point for gvtools.
    
    Args:
        tool_name: Canonical tool name (e.g., "gvfleet")
        tool_desc: Short description
        version: Version string
        subcommands: Dict mapping subcommand names to handler functions
        default_subcommand: Default subcommand if none specified
    """
    Output.set_tool(tool_name, tool_desc)
    
    # Check for version flag early
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(f"{tool_name} {version}")
        sys.exit(0)
    
    # Determine which alias was used
    invoked_as = Path(sys.argv[0]).name
    
    # Build parser
    parser = argparse.ArgumentParser(
        prog=invoked_as,
        description=tool_desc,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", "-V", action="version", version=f"{tool_name} {version}")
    
    subparsers = parser.add_subparsers(dest="subcommand", metavar="command")
    
    for name, handler in subcommands.items():
        # Each handler should set up its own subparser
        sub = subparsers.add_parser(name, help=handler.__doc__)
        if hasattr(handler, "setup_parser"):
            handler.setup_parser(sub)  # type: ignore
    
    # Parse and dispatch
    args = parser.parse_args()
    
    apply_common_args(args)
    
    if not args.subcommand:
        if default_subcommand and default_subcommand in subcommands:
            subcommands[default_subcommand](args)
        else:
            parser.print_help()
            sys.exit(0)
    elif args.subcommand in subcommands:
        subcommands[args.subcommand](args)
    else:
        parser.print_help()
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Module Test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    Output.set_tool("gvcore", "gvtools shared library")
    Output.banner()
    Output.info(f"gvcore version {__version__}")
    Output.step("This is a shared library, not a standalone tool.")
    Output.step("Import it in other gvtools: from gvcore import Output, Inventory, ...")
