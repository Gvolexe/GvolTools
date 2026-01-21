#!/usr/bin/env python3
"""
gvolkeymanager - SSH key upload and registry utility

Provides two main commands:
  - keyup: Upload SSH public keys to remote servers
  - keyconf: Manage local registry of allowed keys and preferences

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

try:
    import paramiko
except ImportError:
    paramiko = None

__version__ = "1.1.3"

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
    
    @staticmethod
    def option(num: str, text: str, desc: str = "") -> None:
        """Print a menu option."""
        opt = f"    {c(num + ')', Colors.CYAN, Colors.BOLD)} {text}"
        if desc:
            opt += f" {c(desc, Colors.DIM)}"
        print(opt)


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
PREFS_CONFIG = XDG_CONFIG_HOME / "gvolkeymanager" / "prefs.json"

KEY_NAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")
SSH_KEY_PREFIXES = ("ssh-", "ecdsa-", "sk-ssh-", "sk-ecdsa-")

DEFAULT_SSH_PORT = 22
DEFAULT_CREATE_USER = "gvol"


@dataclass
class Preferences:
    """User preferences for keyup defaults."""
    default_user: str = ""
    default_key: str = ""
    strict_hostkey: bool = False
    sudo_with_key: bool = True
    disable_root_login: bool = True
    disable_password_auth: bool = True
    
    @classmethod
    def path(cls) -> Path:
        return PREFS_CONFIG
    
    @classmethod
    def load(cls) -> "Preferences":
        """Load preferences from file."""
        if not cls.path().exists():
            return cls()
        
        try:
            data = json.loads(cls.path().read_text(encoding="utf-8"))
            return cls(
                default_user=data.get("default_user", ""),
                default_key=data.get("default_key", ""),
                strict_hostkey=data.get("strict_hostkey", False),
                sudo_with_key=data.get("sudo_with_key", True),
                disable_root_login=data.get("disable_root_login", True),
                disable_password_auth=data.get("disable_password_auth", True),
            )
        except (json.JSONDecodeError, OSError):
            return cls()
    
    def save(self) -> None:
        """Save preferences to file."""
        self.path().parent.mkdir(parents=True, exist_ok=True)
        data = {
            "default_user": self.default_user,
            "default_key": self.default_key,
            "strict_hostkey": self.strict_hostkey,
            "sudo_with_key": self.sudo_with_key,
            "disable_root_login": self.disable_root_login,
            "disable_password_auth": self.disable_password_auth,
        }
        self.path().write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8"
        )


@dataclass
class Config:
    """Application configuration for key registry."""
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


def make_secure_user_script(
    pubkey_b64: str,
    username: str,
    disable_password: bool = True,
    disable_root_login: bool = True,
    setup_sudo_key: bool = True,
) -> str:
    """Generate comprehensive secure user setup script.
    
    This script:
    1. Creates user if not exists
    2. Installs SSH key
    3. Disables password login for user (optional)
    4. Disables root SSH login (optional)
    5. Sets up pam_ssh_agent_auth for sudo (optional)
    """
    
    disable_password_cmd = ""
    if disable_password:
        disable_password_cmd = """
# Disable password authentication for user
passwd -l "$TARGET_USER" 2>/dev/null || true
echo "OK: disabled password login for $TARGET_USER"
"""
    
    disable_root_cmd = ""
    if disable_root_login:
        disable_root_cmd = """
# Disable root SSH login
SSHD_CONFIG="/etc/ssh/sshd_config"
if [ -f "$SSHD_CONFIG" ]; then
    # Backup config
    cp "$SSHD_CONFIG" "${SSHD_CONFIG}.bak.$(date +%Y%m%d%H%M%S)"
    
    # Disable root login
    if grep -qE "^#?PermitRootLogin" "$SSHD_CONFIG"; then
        sed -i 's/^#\\?PermitRootLogin.*/PermitRootLogin no/' "$SSHD_CONFIG"
    else
        echo "PermitRootLogin no" >> "$SSHD_CONFIG"
    fi
    
    # Reload SSH
    if command -v systemctl >/dev/null 2>&1; then
        systemctl reload sshd 2>/dev/null || systemctl reload ssh 2>/dev/null || true
    elif command -v service >/dev/null 2>&1; then
        service sshd reload 2>/dev/null || service ssh reload 2>/dev/null || true
    fi
    echo "OK: disabled root SSH login"
fi
"""
    
    setup_sudo_key_cmd = ""
    if setup_sudo_key:
        setup_sudo_key_cmd = """
# Install libpam-ssh-agent-auth if not present (Debian/Ubuntu)
if command -v apt-get >/dev/null 2>&1; then
    if ! dpkg -l libpam-ssh-agent-auth 2>/dev/null | grep -q "^ii"; then
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq
        apt-get install -y -qq libpam-ssh-agent-auth >/dev/null 2>&1 || true
    fi
fi

# Arch Linux
if command -v pacman >/dev/null 2>&1; then
    if ! pacman -Q pam_ssh_agent_auth 2>/dev/null; then
        pacman -S --noconfirm pam_ssh_agent_auth 2>/dev/null || true
    fi
fi

# Set up sudo authorized keys directory
SUDO_AUTH_DIR="/etc/security/sudo_authorized_keys"
install -d -m 0755 "$SUDO_AUTH_DIR"

# Create per-user sudo key file
SUDO_KEY_FILE="$SUDO_AUTH_DIR/$TARGET_USER"
install -m 0644 -o root -g root /dev/null "$SUDO_KEY_FILE"
echo "$KEY" > "$SUDO_KEY_FILE"
echo "OK: installed sudo key for $TARGET_USER"

# Configure PAM for sudo
PAM_SUDO="/etc/pam.d/sudo"
PAM_LINE="auth sufficient pam_ssh_agent_auth.so file=/etc/security/sudo_authorized_keys/%u"

if [ -f "$PAM_SUDO" ]; then
    if ! grep -qF "pam_ssh_agent_auth" "$PAM_SUDO"; then
        # Add PAM line before @include common-auth
        if grep -q "@include common-auth" "$PAM_SUDO"; then
            sed -i "/@include common-auth/i $PAM_LINE" "$PAM_SUDO"
        else
            # Add at the beginning after any initial comments
            sed -i "1a $PAM_LINE" "$PAM_SUDO"
        fi
        echo "OK: configured PAM for sudo key auth"
    fi
fi

# Ensure SSH_AUTH_SOCK is preserved by sudo
SUDOERS_DROP="/etc/sudoers.d/ssh_auth_sock"
if [ ! -f "$SUDOERS_DROP" ]; then
    echo 'Defaults env_keep += "SSH_AUTH_SOCK"' > "$SUDOERS_DROP"
    chmod 440 "$SUDOERS_DROP"
    echo "OK: configured sudo to preserve SSH_AUTH_SOCK"
fi
"""
    
    return f"""
set -e

KEY_B64={shlex.quote(pubkey_b64)}
KEY="$(printf '%s' "$KEY_B64" | base64 -d)"
TARGET_USER={shlex.quote(username)}

# Create user if not exists
if ! id -u "$TARGET_USER" >/dev/null 2>&1; then
    useradd -m -s /bin/bash "$TARGET_USER"
    echo "OK: created user $TARGET_USER"
else
    echo "OK: user $TARGET_USER already exists"
fi

# Get home directory
HOME_DIR="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
[ -n "$HOME_DIR" ] || {{ echo "ERROR: could not resolve home dir for $TARGET_USER" >&2; exit 2; }}

# Install SSH key
install -d -m 700 -o "$TARGET_USER" -g "$TARGET_USER" "$HOME_DIR/.ssh"
AUTH="$HOME_DIR/.ssh/authorized_keys"
touch "$AUTH"
chmod 600 "$AUTH"
chown "$TARGET_USER":"$TARGET_USER" "$AUTH"
grep -qxF "$KEY" "$AUTH" || echo "$KEY" >> "$AUTH"
echo "OK: installed SSH key for $TARGET_USER"

# Add to sudo group
if getent group sudo >/dev/null 2>&1; then
    usermod -aG sudo "$TARGET_USER" 2>/dev/null || true
    echo "OK: added $TARGET_USER to sudo group"
elif getent group wheel >/dev/null 2>&1; then
    usermod -aG wheel "$TARGET_USER" 2>/dev/null || true
    echo "OK: added $TARGET_USER to wheel group"
fi
{disable_password_cmd}
{disable_root_cmd}
{setup_sudo_key_cmd}
echo ""
echo "DONE: secure user setup complete for $TARGET_USER on $(hostname)"
"""


def make_simple_user_script(pubkey_b64: str, username: str) -> str:
    """Generate simple script to create user and upload key (no security hardening)."""
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


def cmd_keyconf_prefs_show() -> None:
    """Show current preferences."""
    prefs = Preferences.load()
    
    Output.header("Preferences")
    print()
    
    Output.keyvalue("Default user", prefs.default_user or c("(not set)", Colors.DIM))
    Output.keyvalue("Default key", prefs.default_key or c("(not set)", Colors.DIM))
    Output.keyvalue("Strict host key", c("yes", Colors.GREEN) if prefs.strict_hostkey else c("no", Colors.YELLOW))
    
    print()
    Output.info("Security defaults (when creating users):")
    Output.keyvalue("Sudo with SSH key", c("yes", Colors.GREEN) if prefs.sudo_with_key else c("no", Colors.YELLOW), indent=4)
    Output.keyvalue("Disable root login", c("yes", Colors.GREEN) if prefs.disable_root_login else c("no", Colors.YELLOW), indent=4)
    Output.keyvalue("Disable password auth", c("yes", Colors.GREEN) if prefs.disable_password_auth else c("no", Colors.YELLOW), indent=4)
    
    print()
    Output.step(f"Config: {c(str(Preferences.path()), Colors.DIM)}")
    print()


def cmd_keyconf_prefs_set(key: str, value: str) -> None:
    """Set a preference value."""
    prefs = Preferences.load()
    
    key_lower = key.lower().replace("-", "_")
    
    bool_keys = {"strict_hostkey", "sudo_with_key", "disable_root_login", "disable_password_auth"}
    str_keys = {"default_user", "default_key"}
    
    if key_lower in bool_keys:
        if value.lower() in {"true", "yes", "1", "on"}:
            setattr(prefs, key_lower, True)
        elif value.lower() in {"false", "no", "0", "off"}:
            setattr(prefs, key_lower, False)
        else:
            die(f"invalid boolean value '{value}' - use yes/no, true/false, or 1/0")
    elif key_lower in str_keys:
        setattr(prefs, key_lower, value)
    else:
        valid_keys = ", ".join(sorted(bool_keys | str_keys))
        die(f"unknown preference '{key}'\n  Valid keys: {valid_keys}")
    
    prefs.save()
    Output.success(f"set {c(key_lower, Colors.CYAN)} = {c(value, Colors.MAGENTA)}")


# ─────────────────────────────────────────────────────────────────────────────
# Commands: keyup
# ─────────────────────────────────────────────────────────────────────────────

def cmd_keyup(
    target_str: str,
    keyname: str,
    strict_hostkey: bool = False,
    create_user: str = "",
    dry_run: bool = False,
) -> None:
    """Upload SSH key to remote server."""
    cfg = Config.load()
    prefs = Preferences.load()
    
    # Use preferences as defaults
    if not keyname and prefs.default_key:
        keyname = prefs.default_key
    
    if not keyname:
        die("no key specified and no default key configured\n  Set default: keyconf prefs set default_key <name>")
    
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
    
    # Apply preference for strict_hostkey if not overridden
    if prefs.strict_hostkey and not strict_hostkey:
        strict_hostkey = True
    
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
    
    user_to_create = create_user or prefs.default_user or DEFAULT_CREATE_USER
    
    Output.option("1", f"Secure setup: create '{c(user_to_create, Colors.MAGENTA)}'", "(recommended)")
    print(f"       {c('└─ disable root, password auth, sudo with key', Colors.DIM)}")
    Output.option("2", f"Simple setup: create '{c(user_to_create, Colors.MAGENTA)}'")
    print(f"       {c('└─ just add user and key', Colors.DIM)}")
    Output.option("3", f"Upload key to '{c(target.user, Colors.MAGENTA)}' only")
    
    choice = input(f"\n  {c('Option', Colors.DIM)} [{c('1', Colors.CYAN)}/{c('2', Colors.CYAN)}/{c('3', Colors.CYAN)}]: ").strip()
    
    if choice not in {"1", "2", "3"}:
        die("invalid option - must be 1, 2, or 3")
    
    print()
    Output.divider()
    client = connect_ssh(target, password, strict_hostkey)
    
    try:
        if choice == "3":
            Output.info(f"uploading key to {c(target.user, Colors.CYAN)}...")
            script = make_upload_script(pubkey_b64)
            rc, out, err = exec_remote(client, script)
        elif choice == "2":
            Output.info(f"creating user '{c(user_to_create, Colors.CYAN)}' (simple mode)...")
            script = make_simple_user_script(pubkey_b64, user_to_create)
            needs_sudo = target.user != "root"
            rc, out, err = exec_remote(client, script, sudo=needs_sudo, password=password)
        else:  # choice == "1" - secure setup
            Output.info(f"secure setup for '{c(user_to_create, Colors.CYAN)}'...")
            print()
            script = make_secure_user_script(
                pubkey_b64,
                user_to_create,
                disable_password=prefs.disable_password_auth,
                disable_root_login=prefs.disable_root_login,
                setup_sudo_key=prefs.sudo_with_key,
            )
            needs_sudo = target.user != "root"
            rc, out, err = exec_remote(client, script, sudo=needs_sudo, password=password)
        
        print()
        if out.strip():
            for line in out.strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                if line.startswith("OK:"):
                    Output.success(line[3:].strip())
                elif line.startswith("DONE:"):
                    print()
                    Output.success(c(line[5:].strip(), Colors.BOLD))
                elif line.startswith("ERROR:"):
                    Output.error(line[6:].strip())
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
        
        if choice == "1":
            print()
            Output.divider()
            Output.info("next steps:")
            print()
            Output.step(f"SSH: {c(f'ssh {user_to_create}@{target.host}', Colors.CYAN)}")
            Output.step(f"Sudo will use your SSH key (requires agent forwarding: {c('ssh -A', Colors.CYAN)})")
            print()
    
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
  keyconf prefs                           # show preferences
  keyconf prefs set default_user gvol     # set default username
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
    
    # Preferences subcommand
    p_prefs = keyconf_sub.add_parser("prefs", help="manage preferences")
    prefs_sub = p_prefs.add_subparsers(dest="prefs_action", metavar="<action>")
    
    prefs_sub.add_parser("show", help="show current preferences")
    
    p_prefs_set = prefs_sub.add_parser("set", help="set a preference")
    p_prefs_set.add_argument("key", help="preference key")
    p_prefs_set.add_argument("value", help="preference value")
    
    # keyup subcommand
    p_keyup = sub.add_parser(
        "keyup",
        help="upload key to server",
        description="Upload an SSH public key to a remote server"
    )
    p_keyup.add_argument("target", help="user@host or user@host:port")
    p_keyup.add_argument("keyname", nargs="?", default="", help="registered key name (or use default)")
    p_keyup.add_argument(
        "--strict-hostkey",
        action="store_true",
        help="reject unknown host keys (recommended for production)"
    )
    p_keyup.add_argument(
        "--create-user", "-u",
        metavar="USER",
        default="",
        help=f"custom username to create (default: from prefs or {DEFAULT_CREATE_USER})"
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
    
    # Handle --version / -V before subcommand injection
    if argv and argv[0] in ("--version", "-V"):
        print(f"{prog} {__version__}")
        return
    
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
        elif args.keyconf_action == "prefs":
            if getattr(args, "prefs_action", None) == "set":
                cmd_keyconf_prefs_set(args.key, args.value)
            else:
                cmd_keyconf_prefs_show()
        else:
            parser.parse_args(["keyconf", "--help"])
    
    elif args.command == "keyup":
        cmd_keyup(
            args.target,
            args.keyname,
            strict_hostkey=args.strict_hostkey,
            create_user=args.create_user,
            dry_run=args.dry_run,
        )
    
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
