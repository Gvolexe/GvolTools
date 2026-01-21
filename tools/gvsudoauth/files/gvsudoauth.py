#!/usr/bin/env python3
"""
gvsudoauth - Sudo authentication configuration

Configure sudo authentication: password, NOPASSWD, or SSH-agent-based PAM.

Aliases: su, sudoauth, gvsu

Author: Gvol (gvol@nexusystems.org)
"""

from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".local" / "lib" / "gvtools"))

from gvcore import (
    Output, die,
    Target, Inventory,
    add_common_args, add_target_args, get_selector_from_args, apply_common_args,
    ssh_connect, ssh_exec,
)

__version__ = "1.1.4"


STATUS_SCRIPT = """
echo "=== SUDO GROUP MEMBERSHIP ==="
groups 2>/dev/null | tr ' ' '\n' | grep -E "^(sudo|wheel)$" || echo "Not in sudo/wheel"

echo ""
echo "=== SUDOERS RULES ==="
sudo -l 2>/dev/null | head -20 || echo "Could not query sudoers"

echo ""
echo "=== PAM SUDO CONFIG ==="
if [ -f /etc/pam.d/sudo ]; then
    grep -v "^#" /etc/pam.d/sudo | grep -v "^$" | head -10
else
    echo "No /etc/pam.d/sudo"
fi

echo ""
echo "=== SSH AGENT AUTH ==="
if grep -q "pam_ssh_agent_auth" /etc/pam.d/sudo 2>/dev/null; then
    echo "pam_ssh_agent_auth: ENABLED"
else
    echo "pam_ssh_agent_auth: not configured"
fi
"""


def make_enable_agent_script(user: str, pubkey_b64: str) -> str:
    """Generate script to enable SSH agent sudo auth."""
    return f"""
set -e

TARGET_USER='{user}'
PUBKEY_B64='{pubkey_b64}'
PUBKEY="$(printf '%s' "$PUBKEY_B64" | base64 -d)"

# Install libpam-ssh-agent-auth
if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq libpam-ssh-agent-auth >/dev/null 2>&1 || true
fi

if command -v pacman >/dev/null 2>&1; then
    pacman -S --noconfirm pam_ssh_agent_auth 2>/dev/null || true
fi

# Set up sudo authorized keys directory
SUDO_AUTH_DIR="/etc/security/sudo_authorized_keys"
install -d -m 0755 "$SUDO_AUTH_DIR"

# Create per-user sudo key file
SUDO_KEY_FILE="$SUDO_AUTH_DIR/$TARGET_USER"
echo "$PUBKEY" > "$SUDO_KEY_FILE"
chmod 644 "$SUDO_KEY_FILE"
chown root:root "$SUDO_KEY_FILE"
echo "OK: installed sudo key for $TARGET_USER"

# Configure PAM for sudo
PAM_SUDO="/etc/pam.d/sudo"
PAM_LINE="auth sufficient pam_ssh_agent_auth.so file=/etc/security/sudo_authorized_keys/%u"

if [ -f "$PAM_SUDO" ]; then
    if ! grep -qF "pam_ssh_agent_auth" "$PAM_SUDO"; then
        if grep -q "@include common-auth" "$PAM_SUDO"; then
            sed -i "/@include common-auth/i $PAM_LINE" "$PAM_SUDO"
        else
            sed -i "1a $PAM_LINE" "$PAM_SUDO"
        fi
        echo "OK: configured PAM"
    else
        echo "OK: PAM already configured"
    fi
fi

# Ensure SSH_AUTH_SOCK is preserved
SUDOERS_DROP="/etc/sudoers.d/ssh_auth_sock"
if [ ! -f "$SUDOERS_DROP" ]; then
    echo 'Defaults env_keep += "SSH_AUTH_SOCK"' > "$SUDOERS_DROP"
    chmod 440 "$SUDOERS_DROP"
    echo "OK: configured sudo env"
fi

echo "DONE: SSH agent sudo enabled for $TARGET_USER"
"""


DISABLE_AGENT_SCRIPT = """
set -e

# Remove PAM line
PAM_SUDO="/etc/pam.d/sudo"
if [ -f "$PAM_SUDO" ]; then
    sed -i '/pam_ssh_agent_auth/d' "$PAM_SUDO"
    echo "OK: removed PAM config"
fi

echo "DONE: SSH agent sudo disabled"
"""


def make_nopasswd_script(user: str) -> str:
    """Generate script to enable NOPASSWD sudo."""
    return f"""
set -e

TARGET_USER='{user}'
SUDOERS_DROP="/etc/sudoers.d/$TARGET_USER-nopasswd"

echo "$TARGET_USER ALL=(ALL) NOPASSWD: ALL" > "$SUDOERS_DROP"
chmod 440 "$SUDOERS_DROP"

# Validate sudoers
if visudo -c >/dev/null 2>&1; then
    echo "OK: NOPASSWD enabled for $TARGET_USER"
else
    rm -f "$SUDOERS_DROP"
    echo "ERROR: invalid sudoers syntax"
    exit 1
fi
"""


def make_disable_nopasswd_script(user: str) -> str:
    """Generate script to disable NOPASSWD sudo."""
    return f"""
SUDOERS_DROP="/etc/sudoers.d/{user}-nopasswd"
if [ -f "$SUDOERS_DROP" ]; then
    rm -f "$SUDOERS_DROP"
    echo "OK: NOPASSWD disabled for {user}"
else
    echo "OK: no NOPASSWD rule found"
fi
"""


def cmd_status(args: argparse.Namespace) -> None:
    """Report sudo policy status."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector) if not selector.is_empty() else []
    
    if not hosts:
        die("no targets specified")
    
    for host in hosts:
        Output.header(f"Sudo Status: {host.name}")
        target = Target.from_host(host, default_user=host.user or "root")
        
        try:
            client = ssh_connect(target, strict_hostkey=args.strict_hostkey)
            exit_code, stdout, stderr = ssh_exec(client, STATUS_SCRIPT, sudo=True)
            client.close()
            print(stdout)
        except Exception as e:
            Output.error(str(e))


def cmd_enable_agent(args: argparse.Namespace) -> None:
    """Enable SSH agent sudo auth."""
    user = args.user
    pubkey_path = Path(args.pubkey).expanduser()
    
    if not pubkey_path.exists():
        die(f"public key not found: {pubkey_path}")
    
    pubkey = pubkey_path.read_text().strip()
    pubkey_b64 = base64.b64encode(pubkey.encode()).decode()
    
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector) if not selector.is_empty() else []
    
    if not hosts:
        die("no targets specified")
    
    Output.header(f"Enable Agent Auth: {user}")
    
    script = make_enable_agent_script(user, pubkey_b64)
    
    if args.dry_run:
        Output.info("Would enable on:")
        for h in hosts:
            Output.step(h.name)
        return
    
    for host in hosts:
        Output.info(f"Configuring {host.name}...")
        target = Target.from_host(host, default_user="root")
        
        try:
            client = ssh_connect(target, strict_hostkey=args.strict_hostkey)
            exit_code, stdout, stderr = ssh_exec(client, script, sudo=True)
            client.close()
            
            if exit_code == 0:
                Output.success(f"Enabled on {host.name}")
            else:
                Output.error(f"Failed on {host.name}")
        except Exception as e:
            Output.error(f"Failed on {host.name}: {e}")


def cmd_disable_agent(args: argparse.Namespace) -> None:
    """Disable SSH agent sudo auth."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector) if not selector.is_empty() else []
    
    if not hosts:
        die("no targets specified")
    
    Output.header("Disable Agent Auth")
    
    if args.dry_run:
        Output.info("Would disable on:")
        for h in hosts:
            Output.step(h.name)
        return
    
    for host in hosts:
        target = Target.from_host(host, default_user="root")
        
        try:
            client = ssh_connect(target, strict_hostkey=args.strict_hostkey)
            exit_code, stdout, stderr = ssh_exec(client, DISABLE_AGENT_SCRIPT, sudo=True)
            client.close()
            
            if exit_code == 0:
                Output.success(f"Disabled on {host.name}")
            else:
                Output.error(f"Failed on {host.name}")
        except Exception as e:
            Output.error(f"Failed on {host.name}: {e}")


def cmd_enable_nopasswd(args: argparse.Namespace) -> None:
    """Enable NOPASSWD sudo."""
    user = args.user
    
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector) if not selector.is_empty() else []
    
    if not hosts:
        die("no targets specified")
    
    Output.header(f"Enable NOPASSWD: {user}")
    
    script = make_nopasswd_script(user)
    
    if args.dry_run:
        Output.info("Would enable on:")
        for h in hosts:
            Output.step(h.name)
        return
    
    for host in hosts:
        target = Target.from_host(host, default_user="root")
        
        try:
            client = ssh_connect(target, strict_hostkey=args.strict_hostkey)
            exit_code, stdout, stderr = ssh_exec(client, script, sudo=True)
            client.close()
            
            if exit_code == 0:
                Output.success(f"Enabled on {host.name}")
            else:
                Output.error(f"Failed on {host.name}")
        except Exception as e:
            Output.error(f"Failed on {host.name}: {e}")


def cmd_disable_nopasswd(args: argparse.Namespace) -> None:
    """Disable NOPASSWD sudo."""
    user = args.user
    
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector) if not selector.is_empty() else []
    
    if not hosts:
        die("no targets specified")
    
    script = make_disable_nopasswd_script(user)
    
    for host in hosts:
        target = Target.from_host(host, default_user="root")
        
        try:
            client = ssh_connect(target, strict_hostkey=args.strict_hostkey)
            exit_code, stdout, stderr = ssh_exec(client, script, sudo=True)
            client.close()
            
            if exit_code == 0:
                Output.success(f"Disabled on {host.name}")
            else:
                Output.error(f"Failed on {host.name}")
        except Exception as e:
            Output.error(f"Failed on {host.name}: {e}")


def main() -> None:
    Output.set_tool("gvsudoauth", "Sudo authentication config")
    
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(f"gvsudoauth {__version__}")
        sys.exit(0)
    
    parser = argparse.ArgumentParser(
        prog=Path(sys.argv[0]).name,
        description="Configure sudo authentication mode",
        epilog="""
Examples:
  su status server1
  su enable-agent admin --pubkey ~/.ssh/id_ed25519.pub --targets server1
  su disable-agent --targets server1
  su enable-nopasswd admin --targets server1
  su disable-nopasswd admin --targets server1
        """,
    )
    parser.add_argument("--version", "-V", action="version", version=f"gvsudoauth {__version__}")
    
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    
    status_p = subparsers.add_parser("status", help="show sudo policy")
    add_target_args(status_p)
    add_common_args(status_p)
    
    enable_agent_p = subparsers.add_parser("enable-agent", help="enable SSH agent auth")
    enable_agent_p.add_argument("user", help="target user")
    enable_agent_p.add_argument("--pubkey", required=True, help="public key file")
    add_target_args(enable_agent_p)
    add_common_args(enable_agent_p)
    
    disable_agent_p = subparsers.add_parser("disable-agent", help="disable SSH agent auth")
    add_target_args(disable_agent_p)
    add_common_args(disable_agent_p)
    
    enable_nopasswd_p = subparsers.add_parser("enable-nopasswd", help="enable NOPASSWD")
    enable_nopasswd_p.add_argument("user", help="target user")
    add_target_args(enable_nopasswd_p)
    add_common_args(enable_nopasswd_p)
    
    disable_nopasswd_p = subparsers.add_parser("disable-nopasswd", help="disable NOPASSWD")
    disable_nopasswd_p.add_argument("user", help="target user")
    add_target_args(disable_nopasswd_p)
    add_common_args(disable_nopasswd_p)
    
    args = parser.parse_args()
    apply_common_args(args)
    
    commands = {
        "status": cmd_status,
        "enable-agent": cmd_enable_agent,
        "disable-agent": cmd_disable_agent,
        "enable-nopasswd": cmd_enable_nopasswd,
        "disable-nopasswd": cmd_disable_nopasswd,
    }
    
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
