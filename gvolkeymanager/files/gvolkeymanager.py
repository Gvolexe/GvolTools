#!/usr/bin/env python3
"""
gvolkeymanager - SSH key upload and registry utility

Provides two main commands:
  - keyup: Upload SSH public keys to remote servers
  - keyconf: Manage local registry of allowed keys

Author: Gvol (gvol@nexusystems.org)
"""

import argparse
import base64
import getpass
import json
import os
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import paramiko
except ImportError:
    paramiko = None

__version__ = "0.2.0"

# ─────────────────────────────────────────────────────────────────────────────
# Terminal Colors
# ─────────────────────────────────────────────────────────────────────────────

class Colors:
    """ANSI color codes for terminal output."""
    
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    
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
    
    @staticmethod
    def banner() -> None:
        """Print application banner."""
        lines = [
            "",
            c("╭─────────────────────────────────────────╮", Colors.CYAN),
            c("│", Colors.CYAN) + c("         gvolkeymanager                ", Colors.BOLD) + c("│", Colors.CYAN),
            c("│", Colors.CYAN) + c("    SSH Key Upload & Registry          ", Colors.DIM) + c("│", Colors.CYAN),
            c("╰─────────────────────────────────────────╯", Colors.CYAN),
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
        print(c("─" * 40, Colors.DIM))
    
    @staticmethod
    def keyvalue(key: str, value: str, indent: int = 2) -> None:
        prefix = " " * indent
        print(f"{prefix}{c(key + ':', Colors.DIM)} {value}")


def die(msg: str, code: int = 1) -> None:
    """Print error and exit."""
    Output.error(msg)
    sys.exit(code)


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

XDG_CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
LEGACY_CONFIG = XDG_CONFIG_HOME / "keyup" / "keys.json"
DEFAULT_CONFIG = XDG_CONFIG_HOME / "gvolkeymanager" / "keys.json"

KEY_NAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")
SSH_KEY_PREFIXES = ("ssh-", "ecdsa-", "sk-ssh-", "sk-ecdsa-")

DEFAULT_SSH_PORT = 22
DEFAULT_CREATE_USER = "gvol"


@dataclass
class Config:
    """Application configuration."""
    keys: dict
    path: Path
    
    @classmethod
    def load(cls) -> "Config":
        """Load config from file, preferring legacy location if it exists."""
        config_path = LEGACY_CONFIG if LEGACY_CONFIG.exists() else DEFAULT_CONFIG
        
        if not config_path.exists():
            return cls(keys={}, path=config_path)
        
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            return cls(keys=data.get("keys", {}), path=config_path)
        except json.JSONDecodeError as e:
            die(f"invalid JSON in {config_path}: {e}")
        except OSError as e:
            die(f"cannot read {config_path}: {e}")
    
    def save(self) -> None:
        """Save config to file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"keys": self.keys}
        self.path.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────────────

def validate_key_name(name: str) -> None:
    """Validate key name format."""
    if not KEY_NAME_PATTERN.match(name):
        die(
            f"invalid key name '{name}'\n"
            "  Key names must:\n"
            "  • Start with a letter\n"
            "  • Contain only letters, numbers, dashes, underscores\n"
            "  • Be 1-64 characters long"
        )


def validate_pubkey_content(content: str, path: Path) -> None:
    """Validate SSH public key content."""
    if not any(content.startswith(prefix) for prefix in SSH_KEY_PREFIXES):
        die(
            f"file doesn't look like an SSH public key: {path}\n"
            f"  Expected to start with one of: {', '.join(SSH_KEY_PREFIXES)}"
        )


@dataclass
class Target:
    """Parsed SSH target."""
    user: str
    host: str
    port: int
    
    @classmethod
    def parse(cls, target: str) -> "Target":
        """Parse user@host[:port] format."""
        if "@" not in target:
            die("target must be user@host or user@host:port")
        
        user, hostpart = target.split("@", 1)
        if not user:
            die("missing user in target")
        
        host = hostpart
        port = DEFAULT_SSH_PORT
        
        if ":" in hostpart:
            h, p = hostpart.rsplit(":", 1)
            if p.isdigit():
                host, port = h, int(p)
        
        if not host:
            die("missing host in target")
        
        return cls(user=user, host=host, port=port)
    
    def __str__(self) -> str:
        if self.port == DEFAULT_SSH_PORT:
            return f"{self.user}@{self.host}"
        return f"{self.user}@{self.host}:{self.port}"


# ─────────────────────────────────────────────────────────────────────────────
# SSH Operations
# ─────────────────────────────────────────────────────────────────────────────

def check_paramiko() -> None:
    """Ensure paramiko is available."""
    if paramiko is None:
        die(
            "paramiko is not installed\n"
            "  Install with: pip install paramiko\n"
            "  Or use: ./installgvtools.sh install gvolkeymanager --deps"
        )


def connect_ssh(
    target: Target,
    password: str,
    strict_hostkey: bool = False
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
    
    try:
        client.connect(
            hostname=target.host,
            port=target.port,
            username=target.user,
            password=password,
            look_for_keys=False,
            allow_agent=False,
            timeout=15,
            banner_timeout=15,
            auth_timeout=15,
        )
    except paramiko.AuthenticationException:
        die("authentication failed - check username and password")
    except paramiko.SSHException as e:
        die(f"SSH error: {e}")
    except OSError as e:
        die(f"connection failed: {e}")
    
    Output.debug("connected successfully")
    return client


def exec_remote(
    client: "paramiko.SSHClient",
    script: str,
    sudo: bool = False,
    password: str = ""
) -> tuple[int, str, str]:
    """Execute command on remote host."""
    if sudo:
        cmd = f"sudo -S -p '' sh -lc {shlex.quote(script)}"
        stdin, stdout, stderr = client.exec_command(cmd, get_pty=True)
        stdin.write(password + "\n")
        stdin.flush()
    else:
        cmd = f"sh -lc {shlex.quote(script)}"
        stdin, stdout, stderr = client.exec_command(cmd)
    
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    
    return exit_code, out, err


# ─────────────────────────────────────────────────────────────────────────────
# Remote Scripts
# ─────────────────────────────────────────────────────────────────────────────

def make_upload_script(pubkey_b64: str) -> str:
    """Generate script to upload key to current user."""
    return f"""
KEY_B64={shlex.quote(pubkey_b64)}
KEY="$(printf '%s' "$KEY_B64" | base64 -d)"
umask 077
mkdir -p ~/.ssh
touch ~/.ssh/authorized_keys
grep -qxF "$KEY" ~/.ssh/authorized_keys || echo "$KEY" >> ~/.ssh/authorized_keys
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
echo "OK: key installed for $(whoami) on $(hostname)"
"""


def make_create_user_script(pubkey_b64: str, username: str) -> str:
    """Generate script to create user and upload key."""
    return f"""
KEY_B64={shlex.quote(pubkey_b64)}
KEY="$(printf '%s' "$KEY_B64" | base64 -d)"
TARGET_USER={shlex.quote(username)}

id -u "$TARGET_USER" >/dev/null 2>&1 || useradd -m -s /bin/bash "$TARGET_USER"
HOME_DIR="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
[ -n "$HOME_DIR" ] || {{ echo "could not resolve home dir for $TARGET_USER" >&2; exit 2; }}

install -d -m 700 -o "$TARGET_USER" -g "$TARGET_USER" "$HOME_DIR/.ssh"
AUTH="$HOME_DIR/.ssh/authorized_keys"
touch "$AUTH"
chmod 600 "$AUTH"
chown "$TARGET_USER":"$TARGET_USER" "$AUTH"
grep -qxF "$KEY" "$AUTH" || echo "$KEY" >> "$AUTH"

if getent group sudo >/dev/null 2>&1; then
  usermod -aG sudo "$TARGET_USER" 2>/dev/null || true
fi

echo "OK: key installed for $TARGET_USER on $(hostname)"
"""


# ─────────────────────────────────────────────────────────────────────────────
# Commands: keyconf
# ─────────────────────────────────────────────────────────────────────────────

def cmd_keyconf_add(name: str, path: str) -> None:
    """Add a key to the registry."""
    validate_key_name(name)
    
    pubkey_path = Path(path).expanduser().resolve()
    if not pubkey_path.exists():
        die(f"file not found: {pubkey_path}")
    
    content = pubkey_path.read_text(encoding="utf-8").strip()
    validate_pubkey_content(content, pubkey_path)
    
    cfg = Config.load()
    
    if name in cfg.keys:
        Output.warn(f"key '{name}' already exists, updating path")
    
    cfg.keys[name] = str(pubkey_path)
    cfg.save()
    
    Output.success(f"added key '{c(name, Colors.CYAN)}'")
    print(f"  {c('path:', Colors.DIM)} {pubkey_path}")


def cmd_keyconf_del(name: str) -> None:
    """Remove a key from the registry."""
    cfg = Config.load()
    
    if name not in cfg.keys:
        die(f"key '{name}' not found in registry")
    
    del cfg.keys[name]
    cfg.save()
    
    Output.success(f"removed key '{c(name, Colors.CYAN)}'")


def cmd_keyconf_list() -> None:
    """List all registered keys."""
    cfg = Config.load()
    
    if not cfg.keys:
        Output.info("no keys registered")
        print()
        Output.step(f"{c('Tip:', Colors.YELLOW)} keyconf add <name> /path/to/key.pub")
        return
    
    Output.header("Registered Keys")
    print()
    
    for i, (name, path) in enumerate(sorted(cfg.keys.items())):
        path_obj = Path(path)
        exists = path_obj.exists()
        
        status = c("●", Colors.GREEN) if exists else c("○", Colors.RED)
        name_fmt = c(name, Colors.CYAN, Colors.BOLD)
        path_fmt = c(str(path_obj), Colors.DIM) if exists else c(str(path_obj) + " (missing)", Colors.RED)
        
        print(f"  {status} {name_fmt}")
        print(f"    └─ {path_fmt}")
        
        if i < len(cfg.keys) - 1:
            print()
    
    print()
    Output.divider()
    print(f"  {c('Total:', Colors.DIM)} {len(cfg.keys)} key(s)")


def cmd_keyconf_show(name: str) -> None:
    """Show details for a specific key."""
    cfg = Config.load()
    
    if name not in cfg.keys:
        die(f"key '{name}' not found in registry")
    
    path = Path(cfg.keys[name])
    exists = path.exists()
    
    Output.header(f"Key: {name}")
    print()
    
    Output.keyvalue("Path", str(path))
    Output.keyvalue("Status", c("✔ available", Colors.GREEN) if exists else c("✖ missing", Colors.RED))
    
    if exists:
        content = path.read_text(encoding="utf-8").strip()
        parts = content.split()
        if len(parts) >= 2:
            key_type = parts[0]
            key_data = parts[1][:20] + "..." if len(parts[1]) > 20 else parts[1]
            comment = parts[2] if len(parts) > 2 else c("(none)", Colors.DIM)
            
            print()
            Output.keyvalue("Type", c(key_type, Colors.MAGENTA))
            Output.keyvalue("Comment", comment)
            Output.keyvalue("Fingerprint", c(key_data, Colors.DIM))
    
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Commands: keyup
# ─────────────────────────────────────────────────────────────────────────────

def cmd_keyup(
    target_str: str,
    keyname: str,
    strict_hostkey: bool = False,
    create_user: str = "",
    dry_run: bool = False
) -> None:
    """Upload SSH key to remote server."""
    cfg = Config.load()
    
    if keyname not in cfg.keys:
        die(
            f"key '{keyname}' not in registry\n"
            f"  Add it first: keyconf add {keyname} /path/to/key.pub"
        )
    
    pubkey_path = Path(cfg.keys[keyname]).expanduser()
    if not pubkey_path.exists():
        die(f"key file not found: {pubkey_path}")
    
    pubkey = pubkey_path.read_text(encoding="utf-8").strip()
    pubkey_b64 = base64.b64encode(pubkey.encode("utf-8")).decode("ascii")
    
    target = Target.parse(target_str)
    
    Output.header("Key Upload")
    print()
    Output.keyvalue("Target", f"{c(str(target), Colors.CYAN)}")
    Output.keyvalue("Key", f"{c(keyname, Colors.MAGENTA)} ({pubkey_path.name})")
    
    if not strict_hostkey:
        Output.keyvalue("Security", c("⚠ auto-accept host keys", Colors.YELLOW))
    else:
        Output.keyvalue("Security", c("✔ strict host key checking", Colors.GREEN))
    
    if dry_run:
        print()
        Output.info("dry run mode - no changes will be made")
        Output.divider()
        return
    
    print()
    password = getpass.getpass(f"  {c('Password:', Colors.DIM)} ")
    
    print()
    Output.divider()
    Output.info("choose upload option:")
    print()
    print(f"    {c('1)', Colors.CYAN, Colors.BOLD)} Create user '{c(create_user or DEFAULT_CREATE_USER, Colors.MAGENTA)}' and upload key")
    print(f"    {c('2)', Colors.CYAN, Colors.BOLD)} Upload key to '{c(target.user, Colors.MAGENTA)}'")
    
    choice = input(f"\n  {c('Option', Colors.DIM)} [{c('1', Colors.CYAN)}/{c('2', Colors.CYAN)}]: ").strip()
    
    if choice not in {"1", "2"}:
        die("invalid option - must be 1 or 2")
    
    print()
    Output.divider()
    client = connect_ssh(target, password, strict_hostkey)
    
    try:
        if choice == "2":
            Output.info(f"uploading key to {c(target.user, Colors.CYAN)}...")
            script = make_upload_script(pubkey_b64)
            rc, out, err = exec_remote(client, script)
        else:
            user = create_user or DEFAULT_CREATE_USER
            Output.info(f"creating user '{c(user, Colors.CYAN)}' and uploading key...")
            script = make_create_user_script(pubkey_b64, user)
            needs_sudo = target.user != "root"
            rc, out, err = exec_remote(client, script, sudo=needs_sudo, password=password)
        
        print()
        if out.strip():
            for line in out.strip().split("\n"):
                if line.startswith("OK:"):
                    Output.success(line[3:].strip())
                else:
                    Output.step(line)
        
        if rc != 0:
            if err.strip():
                for line in err.strip().split("\n"):
                    Output.error(line)
            die(f"remote command failed (exit code {rc})")
        
        if err.strip():
            for line in err.strip().split("\n"):
                if line and not line.startswith("[sudo]"):
                    Output.warn(line)
    
    finally:
        client.close()
        Output.debug("connection closed")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def build_parser(prog: str) -> argparse.ArgumentParser:
    """Build argument parser."""
    parser = argparse.ArgumentParser(
        prog=prog,
        description="SSH key upload and registry utility",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  keyconf add mykey ~/.ssh/id_ed25519.pub
  keyconf list
  keyup user@host mykey
  keyup --strict-hostkey admin@server:2222 mykey
"""
    )
    
    parser.add_argument(
        "--version", "-V",
        action="version",
        version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="enable verbose output"
    )
    
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    
    # keyconf subcommand
    p_keyconf = sub.add_parser(
        "keyconf",
        help="manage key registry",
        description="Manage the local registry of SSH public keys"
    )
    keyconf_sub = p_keyconf.add_subparsers(dest="keyconf_action", metavar="<action>")
    
    p_add = keyconf_sub.add_parser("add", help="register a key")
    p_add.add_argument("name", help="name for the key (e.g., 'personal', 'work')")
    p_add.add_argument("path", help="path to the .pub file")
    
    p_del = keyconf_sub.add_parser("del", help="remove a key")
    p_del.add_argument("name", help="name of the key to remove")
    
    keyconf_sub.add_parser("list", help="list all registered keys")
    
    p_show = keyconf_sub.add_parser("show", help="show key details")
    p_show.add_argument("name", help="name of the key")
    
    # keyup subcommand
    p_keyup = sub.add_parser(
        "keyup",
        help="upload key to server",
        description="Upload an SSH public key to a remote server"
    )
    p_keyup.add_argument("target", help="user@host or user@host:port")
    p_keyup.add_argument("keyname", help="registered key name")
    p_keyup.add_argument(
        "--strict-hostkey",
        action="store_true",
        help="reject unknown host keys (recommended for production)"
    )
    p_keyup.add_argument(
        "--create-user",
        metavar="USER",
        default="",
        help=f"custom username to create (default: {DEFAULT_CREATE_USER})"
    )
    p_keyup.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="show what would happen without connecting"
    )
    
    return parser


def main() -> None:
    """Main entry point."""
    prog = Path(sys.argv[0]).name
    argv = sys.argv[1:]
    
    # Handle symlink invocations
    if prog == "keyconf":
        argv = ["keyconf"] + argv
    elif prog == "keyup":
        argv = ["keyup"] + argv
    
    parser = build_parser(prog)
    args = parser.parse_args(argv)
    
    Output.verbose = getattr(args, "verbose", False)
    
    if args.command == "keyconf":
        if args.keyconf_action == "add":
            cmd_keyconf_add(args.name, args.path)
        elif args.keyconf_action == "del":
            cmd_keyconf_del(args.name)
        elif args.keyconf_action == "list":
            cmd_keyconf_list()
        elif args.keyconf_action == "show":
            cmd_keyconf_show(args.name)
        else:
            parser.parse_args(["keyconf", "--help"])
    
    elif args.command == "keyup":
        cmd_keyup(
            args.target,
            args.keyname,
            strict_hostkey=args.strict_hostkey,
            create_user=args.create_user,
            dry_run=args.dry_run
        )
    
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
