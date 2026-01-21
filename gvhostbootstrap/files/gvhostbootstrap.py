#!/usr/bin/env python3
"""
gvhostbootstrap - Bootstrap hosts to secure baseline

Bootstrap a fresh Debian/Ubuntu host to a secure baseline:
- Non-root admin user creation
- Key-based authentication
- SSH hardening
- Firewall baseline

Aliases: hb, gvhb

Author: Gvol (gvol@nexusystems.org)
"""

from __future__ import annotations

import argparse
import base64
import getpass
import sys
from pathlib import Path

# Add gvtools lib to path
sys.path.insert(0, str(Path.home() / ".local" / "lib" / "gvtools"))

from gvcore import (
    Output, die,
    Target, Inventory,
    add_common_args, add_target_args, get_selector_from_args, apply_common_args,
    ssh_connect, ssh_exec,
)

__version__ = "0.5.0"

# Key registry path (compatible with gvolkeymanager)
KEY_REGISTRY = Path.home() / ".config" / "gvolkeymanager" / "keys.json"


# ─────────────────────────────────────────────────────────────────────────────
# Key Loading
# ─────────────────────────────────────────────────────────────────────────────

def load_key_registry() -> dict[str, str]:
    """Load key registry from gvolkeymanager."""
    import json
    if not KEY_REGISTRY.exists():
        return {}
    try:
        data = json.loads(KEY_REGISTRY.read_text())
        return data.get("keys", {})
    except Exception:
        return {}


def get_pubkey(keyname: str) -> str:
    """Get public key content by name."""
    keys = load_key_registry()
    if keyname not in keys:
        die(f"key not found in registry: {keyname}\n  Use: keyconf add {keyname} /path/to/key.pub")
    
    key_path = Path(keys[keyname]).expanduser()
    if not key_path.exists():
        die(f"key file not found: {key_path}")
    
    return key_path.read_text().strip()


# ─────────────────────────────────────────────────────────────────────────────
# Bootstrap Scripts
# ─────────────────────────────────────────────────────────────────────────────

def make_init_script(pubkey_b64: str, username: str) -> str:
    """Create user and install SSH key."""
    return f"""
set -e
KEY_B64='{pubkey_b64}'
KEY="$(printf '%s' "$KEY_B64" | base64 -d)"
TARGET_USER='{username}'

# Create user if not exists
if ! id -u "$TARGET_USER" >/dev/null 2>&1; then
    useradd -m -s /bin/bash "$TARGET_USER"
    echo "CREATED: user $TARGET_USER"
else
    echo "EXISTS: user $TARGET_USER"
fi

# Get home directory
HOME_DIR="$(getent passwd "$TARGET_USER" | cut -d: -f6)"

# Install SSH key
install -d -m 700 -o "$TARGET_USER" -g "$TARGET_USER" "$HOME_DIR/.ssh"
AUTH="$HOME_DIR/.ssh/authorized_keys"
touch "$AUTH"
chmod 600 "$AUTH"
chown "$TARGET_USER":"$TARGET_USER" "$AUTH"
grep -qxF "$KEY" "$AUTH" || echo "$KEY" >> "$AUTH"
echo "INSTALLED: SSH key"

# Add to sudo group
if getent group sudo >/dev/null 2>&1; then
    usermod -aG sudo "$TARGET_USER" 2>/dev/null || true
    echo "ADDED: $TARGET_USER to sudo group"
elif getent group wheel >/dev/null 2>&1; then
    usermod -aG wheel "$TARGET_USER" 2>/dev/null || true
    echo "ADDED: $TARGET_USER to wheel group"
fi

echo "DONE: init complete for $TARGET_USER"
"""


def make_harden_script() -> str:
    """Apply SSH hardening and basic security."""
    return """
set -e

SSHD_CONFIG="/etc/ssh/sshd_config"

# Backup sshd_config
cp "$SSHD_CONFIG" "${SSHD_CONFIG}.bak.$(date +%Y%m%d%H%M%S)"

# Function to set sshd option
set_sshd_opt() {
    local key="$1" val="$2"
    if grep -qE "^#?$key" "$SSHD_CONFIG"; then
        sed -i "s/^#\\?$key.*/$key $val/" "$SSHD_CONFIG"
    else
        echo "$key $val" >> "$SSHD_CONFIG"
    fi
}

# SSH hardening
set_sshd_opt "PermitRootLogin" "no"
set_sshd_opt "PasswordAuthentication" "no"
set_sshd_opt "PubkeyAuthentication" "yes"
set_sshd_opt "ChallengeResponseAuthentication" "no"
set_sshd_opt "X11Forwarding" "no"
set_sshd_opt "UsePAM" "yes"
set_sshd_opt "MaxAuthTries" "3"
set_sshd_opt "LoginGraceTime" "30"

echo "HARDENED: sshd_config"

# Test sshd config
if ! sshd -t 2>/dev/null; then
    echo "ERROR: sshd config test failed, restoring backup"
    cp "${SSHD_CONFIG}.bak."* "$SSHD_CONFIG" 2>/dev/null || true
    exit 1
fi

# Reload SSH
if command -v systemctl >/dev/null 2>&1; then
    systemctl reload sshd 2>/dev/null || systemctl reload ssh 2>/dev/null || true
elif command -v service >/dev/null 2>&1; then
    service sshd reload 2>/dev/null || service ssh reload 2>/dev/null || true
fi
echo "RELOADED: SSH service"

# Basic firewall (UFW if available)
if command -v ufw >/dev/null 2>&1; then
    ufw --force reset >/dev/null 2>&1 || true
    ufw default deny incoming
    ufw default allow outgoing
    ufw allow ssh
    ufw --force enable
    echo "ENABLED: UFW firewall"
fi

# Enable unattended upgrades if available
if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq unattended-upgrades >/dev/null 2>&1 || true
    dpkg-reconfigure -plow unattended-upgrades 2>/dev/null || true
    echo "ENABLED: unattended-upgrades"
fi

# Fail2ban if available
if command -v apt-get >/dev/null 2>&1; then
    apt-get install -y -qq fail2ban >/dev/null 2>&1 || true
    systemctl enable fail2ban 2>/dev/null || true
    systemctl start fail2ban 2>/dev/null || true
    echo "ENABLED: fail2ban"
fi

echo "DONE: hardening complete"
"""


def make_status_script() -> str:
    """Check security status of host."""
    return """
echo "=== SSHD STATUS ==="
if [ -f /etc/ssh/sshd_config ]; then
    echo "PermitRootLogin: $(grep -E '^PermitRootLogin' /etc/ssh/sshd_config 2>/dev/null | awk '{print $2}' || echo 'default')"
    echo "PasswordAuthentication: $(grep -E '^PasswordAuthentication' /etc/ssh/sshd_config 2>/dev/null | awk '{print $2}' || echo 'default')"
    echo "PubkeyAuthentication: $(grep -E '^PubkeyAuthentication' /etc/ssh/sshd_config 2>/dev/null | awk '{print $2}' || echo 'default')"
fi

echo ""
echo "=== FIREWALL STATUS ==="
if command -v ufw >/dev/null 2>&1; then
    ufw status 2>/dev/null || echo "UFW not configured"
elif command -v iptables >/dev/null 2>&1; then
    iptables -L -n 2>/dev/null | head -20 || echo "iptables check failed"
else
    echo "No firewall detected"
fi

echo ""
echo "=== UPDATES STATUS ==="
if [ -f /etc/apt/apt.conf.d/20auto-upgrades ]; then
    echo "Unattended upgrades: $(grep -q '1' /etc/apt/apt.conf.d/20auto-upgrades 2>/dev/null && echo 'enabled' || echo 'disabled')"
else
    echo "Unattended upgrades: not configured"
fi

echo ""
echo "=== FAIL2BAN STATUS ==="
if command -v fail2ban-client >/dev/null 2>&1; then
    fail2ban-client status 2>/dev/null || echo "fail2ban not running"
else
    echo "fail2ban not installed"
fi

echo ""
echo "=== DONE ==="
"""


# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

def cmd_init(args: argparse.Namespace) -> None:
    """Create user and install SSH key on remote host."""
    target_str = args.target
    if not target_str:
        die("target is required (user@host)")
    
    target = Target.parse(target_str)
    if not target.user:
        target.user = "root"
    
    new_user = args.new_user
    keyname = args.key
    
    if not new_user:
        die("--new-user is required")
    if not keyname:
        die("--key is required")
    
    pubkey = get_pubkey(keyname)
    pubkey_b64 = base64.b64encode(pubkey.encode()).decode()
    
    Output.header(f"Bootstrap Init: {target.host}")
    Output.keyvalue("target", str(target))
    Output.keyvalue("new user", new_user)
    Output.keyvalue("key", keyname)
    
    if args.dry_run:
        Output.info("Dry run - would execute init script")
        return
    
    # Get password
    password = getpass.getpass(f"Password for {target}: ")
    
    Output.info("Connecting...")
    client = ssh_connect(target, password=password, strict_hostkey=args.strict_hostkey)
    
    Output.info("Running init script...")
    script = make_init_script(pubkey_b64, new_user)
    exit_code, stdout, stderr = ssh_exec(client, script, sudo=(target.user != "root"), password=password)
    
    client.close()
    
    if exit_code != 0:
        Output.error(f"Init failed (exit code {exit_code})")
        if stderr:
            print(stderr)
        sys.exit(1)
    
    # Parse output
    for line in stdout.split("\n"):
        line = line.strip()
        if line.startswith("CREATED:"):
            Output.success(line[8:].strip())
        elif line.startswith("EXISTS:"):
            Output.info(line[7:].strip())
        elif line.startswith("INSTALLED:"):
            Output.success(line[10:].strip())
        elif line.startswith("ADDED:"):
            Output.success(line[6:].strip())
        elif line.startswith("DONE:"):
            Output.success(line[5:].strip())
        elif line:
            Output.step(line)
    
    Output.divider()
    Output.success("Init complete!")
    Output.step(f"Test: ssh {new_user}@{target.host}")


def cmd_harden(args: argparse.Namespace) -> None:
    """Apply security hardening to host."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    
    if selector.is_empty():
        die("target is required")
    
    hosts = inventory.select(selector)
    if not hosts:
        die("no hosts matched selector")
    
    for host in hosts:
        Output.header(f"Hardening: {host.name}")
        
        if args.dry_run:
            Output.info("Dry run - would apply hardening")
            continue
        
        # Get password if needed
        target = Target.from_host(host, default_user="root")
        password = getpass.getpass(f"Password for {target}: ")
        
        Output.info("Connecting...")
        client = ssh_connect(target, password=password, strict_hostkey=args.strict_hostkey)
        
        Output.info("Applying hardening...")
        script = make_harden_script()
        exit_code, stdout, stderr = ssh_exec(client, script, sudo=True, password=password)
        
        client.close()
        
        if exit_code != 0:
            Output.error(f"Hardening failed on {host.name}")
            if stderr:
                print(stderr)
            continue
        
        # Parse output
        for line in stdout.split("\n"):
            line = line.strip()
            if line.startswith("HARDENED:") or line.startswith("ENABLED:") or line.startswith("RELOADED:"):
                Output.success(line.split(":", 1)[1].strip())
            elif line.startswith("ERROR:"):
                Output.error(line[6:].strip())
            elif line.startswith("DONE:"):
                Output.success(line[5:].strip())
    
    Output.divider()
    Output.success("Hardening complete!")


def cmd_full(args: argparse.Namespace) -> None:
    """Run init then harden with verification."""
    Output.header("Full Bootstrap")
    
    # Run init
    cmd_init(args)
    
    if args.dry_run:
        Output.info("Dry run - would run harden next")
        return
    
    # Verify we can connect as new user
    target_str = args.target
    target = Target.parse(target_str)
    new_user = args.new_user
    
    Output.info(f"Verifying SSH access as {new_user}...")
    
    new_target = Target(user=new_user, host=target.host, port=target.port)
    
    try:
        # Try key-based auth
        client = ssh_connect(new_target, strict_hostkey=args.strict_hostkey)
        client.close()
        Output.success(f"Verified: can connect as {new_user}")
    except Exception as e:
        Output.warn(f"Could not verify key-based access: {e}")
        Output.step("Continuing with hardening anyway...")
    
    # Run harden
    args.target = f"root@{target.host}:{target.port}" if target.port != 22 else f"root@{target.host}"
    cmd_harden(args)
    
    Output.divider()
    Output.success("Full bootstrap complete!")
    Output.step(f"Connect: ssh -A {new_user}@{target.host}")
    Output.step("Root login is now disabled")


def cmd_status(args: argparse.Namespace) -> None:
    """Report security status of host."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    
    if selector.is_empty():
        die("target is required")
    
    hosts = inventory.select(selector)
    if not hosts:
        die("no hosts matched selector")
    
    results = []
    
    for host in hosts:
        Output.header(f"Status: {host.name}")
        
        target = Target.from_host(host, default_user=host.user or "root")
        
        try:
            client = ssh_connect(target, strict_hostkey=args.strict_hostkey)
            
            script = make_status_script()
            exit_code, stdout, stderr = ssh_exec(client, script, sudo=True)
            
            client.close()
            
            if Output.json_mode:
                results.append({"host": host.name, "status": "ok", "output": stdout})
            else:
                print(stdout)
        except Exception as e:
            if Output.json_mode:
                results.append({"host": host.name, "status": "error", "error": str(e)})
            else:
                Output.error(f"Could not connect: {e}")
    
    if Output.json_mode:
        Output.json_output({"results": results})


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    """Main entry point."""
    Output.set_tool("gvhostbootstrap", "Host security bootstrap")
    
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(f"gvhostbootstrap {__version__}")
        sys.exit(0)
    
    invoked_as = Path(sys.argv[0]).name
    
    parser = argparse.ArgumentParser(
        prog=invoked_as,
        description="Bootstrap hosts to secure baseline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  hb init root@newserver --new-user admin --key personal
  hb harden admin@server
  hb full root@newserver --new-user admin --key personal
  hb status server1.example.com
        """,
    )
    parser.add_argument("--version", "-V", action="version", version=f"gvhostbootstrap {__version__}")
    
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    
    # init
    init_p = subparsers.add_parser("init", help="create user and install SSH key")
    init_p.add_argument("target", help="target: user@host[:port]")
    init_p.add_argument("--new-user", "-u", required=True, help="username to create")
    init_p.add_argument("--key", "-k", required=True, help="key name from registry")
    add_common_args(init_p)
    
    # harden
    harden_p = subparsers.add_parser("harden", help="apply security hardening")
    add_target_args(harden_p)
    add_common_args(harden_p)
    
    # full
    full_p = subparsers.add_parser("full", help="init + harden with verification")
    full_p.add_argument("target", help="target: root@host[:port]")
    full_p.add_argument("--new-user", "-u", required=True, help="username to create")
    full_p.add_argument("--key", "-k", required=True, help="key name from registry")
    add_common_args(full_p)
    
    # status
    status_p = subparsers.add_parser("status", help="check security status")
    add_target_args(status_p)
    add_common_args(status_p)
    
    args = parser.parse_args()
    apply_common_args(args)
    
    commands = {
        "init": cmd_init,
        "harden": cmd_harden,
        "full": cmd_full,
        "status": cmd_status,
    }
    
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
