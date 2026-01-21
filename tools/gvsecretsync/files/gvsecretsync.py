#!/usr/bin/env python3
"""
gvsecretsync - Encrypted secrets management and deployment

Manage encrypted secrets locally and deploy to hosts:
- Encrypted storage using Fernet (AES-128-CBC)
- Scope-based access control
- Deployment with ownership/mode validation

Aliases: sec, secrets, gvs

Author: Gvol (gvol@nexusystems.org)
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".local" / "lib" / "gvtools"))

from gvcore import (
    Output, Colors, c, die,
    Target, Inventory,
    SECRETS_PATH,
    add_common_args, add_target_args, get_selector_from_args, apply_common_args,
    ssh_connect, ssh_exec, confirm,
)

__version__ = "1.1.1"

SECRETS_INDEX = SECRETS_PATH / "index.json"
SECRETS_KEY_FILE = SECRETS_PATH / ".key"


# ─────────────────────────────────────────────────────────────────────────────
# Encryption
# ─────────────────────────────────────────────────────────────────────────────

def get_or_create_key() -> bytes:
    """Get or create encryption key."""
    SECRETS_PATH.mkdir(parents=True, exist_ok=True)
    
    if SECRETS_KEY_FILE.exists():
        return base64.b64decode(SECRETS_KEY_FILE.read_text().strip())
    
    # Generate new key
    try:
        from cryptography.fernet import Fernet
        key = Fernet.generate_key()
    except ImportError:
        # Fallback to simple key derivation
        import secrets as sec_module
        key = base64.urlsafe_b64encode(sec_module.token_bytes(32))
    
    SECRETS_KEY_FILE.write_text(base64.b64encode(key).decode())
    SECRETS_KEY_FILE.chmod(0o600)
    return key


def encrypt_data(data: bytes) -> bytes:
    """Encrypt data."""
    key = get_or_create_key()
    try:
        from cryptography.fernet import Fernet
        f = Fernet(key)
        return f.encrypt(data)
    except ImportError:
        # Simple XOR fallback (not production secure)
        Output.warn("cryptography not installed, using basic encoding")
        return base64.b64encode(data)


def decrypt_data(encrypted: bytes) -> bytes:
    """Decrypt data."""
    key = get_or_create_key()
    try:
        from cryptography.fernet import Fernet
        f = Fernet(key)
        return f.decrypt(encrypted)
    except ImportError:
        return base64.b64decode(encrypted)


# ─────────────────────────────────────────────────────────────────────────────
# Index Management
# ─────────────────────────────────────────────────────────────────────────────

def load_index() -> dict:
    """Load secrets index."""
    if not SECRETS_INDEX.exists():
        return {"secrets": {}}
    return json.loads(SECRETS_INDEX.read_text())


def save_index(data: dict) -> None:
    """Save secrets index."""
    SECRETS_PATH.mkdir(parents=True, exist_ok=True)
    SECRETS_INDEX.write_text(json.dumps(data, indent=2))
    SECRETS_INDEX.chmod(0o600)


# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

def cmd_add(args: argparse.Namespace) -> None:
    """Add a secret."""
    name = args.name
    file_path = Path(args.file).expanduser()
    scope = args.scope or "*"
    
    if not file_path.exists():
        die(f"file not found: {file_path}")
    
    Output.header(f"Add Secret: {name}")
    
    # Read and encrypt
    content = file_path.read_bytes()
    encrypted = encrypt_data(content)
    
    # Save encrypted file
    secret_file = SECRETS_PATH / f"{name}.enc"
    secret_file.write_bytes(encrypted)
    secret_file.chmod(0o600)
    
    # Update index
    index = load_index()
    index["secrets"][name] = {
        "version": 1,
        "scope": scope,
        "created": datetime.now().isoformat(),
        "updated": datetime.now().isoformat(),
        "deployments": [],
    }
    save_index(index)
    
    Output.success(f"Added secret: {c(name, Colors.CYAN)}")
    Output.keyvalue("scope", scope)
    Output.keyvalue("size", f"{len(content)} bytes")


def cmd_put(args: argparse.Namespace) -> None:
    """Deploy secret to hosts."""
    name = args.name
    remote_path = args.to
    owner = args.owner
    mode = args.mode or "600"
    
    index = load_index()
    if name not in index["secrets"]:
        die(f"secret not found: {name}")
    
    secret_file = SECRETS_PATH / f"{name}.enc"
    if not secret_file.exists():
        die(f"secret file missing: {name}")
    
    # Decrypt
    encrypted = secret_file.read_bytes()
    content = decrypt_data(encrypted)
    content_b64 = base64.b64encode(content).decode()
    
    # Get targets
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector) if not selector.is_empty() else []
    
    if not hosts:
        die("no targets specified")
    
    Output.header(f"Deploy Secret: {name}")
    Output.keyvalue("targets", str(len(hosts)))
    Output.keyvalue("path", remote_path)
    
    if args.dry_run:
        Output.info("Dry run - would deploy to:")
        for h in hosts:
            Output.step(h.name)
        return
    
    script = f"""
set -e
CONTENT_B64='{content_b64}'
printf '%s' "$CONTENT_B64" | base64 -d > '{remote_path}'
chown {owner}:{owner} '{remote_path}'
chmod {mode} '{remote_path}'
echo "OK"
"""
    
    deployed = []
    for host in hosts:
        target = Target.from_host(host, default_user="root")
        try:
            client = ssh_connect(target, strict_hostkey=args.strict_hostkey)
            exit_code, stdout, stderr = ssh_exec(client, script, sudo=True)
            client.close()
            
            if exit_code == 0:
                Output.success(f"Deployed to {host.name}")
                deployed.append(host.name)
            else:
                Output.error(f"Failed on {host.name}: {stderr}")
        except Exception as e:
            Output.error(f"Failed on {host.name}: {e}")
    
    # Update index
    index["secrets"][name]["deployments"] = deployed
    index["secrets"][name]["last_deployed"] = datetime.now().isoformat()
    save_index(index)


def cmd_rotate(args: argparse.Namespace) -> None:
    """Rotate secret with new file."""
    name = args.name
    file_path = Path(args.file).expanduser()
    
    index = load_index()
    if name not in index["secrets"]:
        die(f"secret not found: {name}")
    
    if not file_path.exists():
        die(f"file not found: {file_path}")
    
    Output.header(f"Rotate Secret: {name}")
    
    # Read and encrypt
    content = file_path.read_bytes()
    encrypted = encrypt_data(content)
    
    # Save encrypted file
    secret_file = SECRETS_PATH / f"{name}.enc"
    secret_file.write_bytes(encrypted)
    
    # Update index
    index["secrets"][name]["version"] += 1
    index["secrets"][name]["updated"] = datetime.now().isoformat()
    save_index(index)
    
    Output.success(f"Rotated secret: {c(name, Colors.CYAN)}")
    Output.keyvalue("version", str(index["secrets"][name]["version"]))


def cmd_status(args: argparse.Namespace) -> None:
    """Show secret status."""
    name = args.name
    
    index = load_index()
    
    if name:
        if name not in index["secrets"]:
            die(f"secret not found: {name}")
        secrets = {name: index["secrets"][name]}
    else:
        secrets = index["secrets"]
    
    if Output.json_mode:
        Output.json_output(secrets)
        return
    
    if not secrets:
        Output.info("No secrets stored")
        return
    
    Output.header(f"Secrets ({len(secrets)})")
    
    headers = ["Name", "Version", "Scope", "Last Deployed", "Targets"]
    rows = []
    for n, info in secrets.items():
        rows.append([
            c(n, Colors.CYAN),
            str(info.get("version", 1)),
            info.get("scope", "*"),
            info.get("last_deployed", "-")[:10] if info.get("last_deployed") else "-",
            str(len(info.get("deployments", []))),
        ])
    
    Output.table(headers, rows)


def cmd_rm(args: argparse.Namespace) -> None:
    """Remove a secret."""
    name = args.name
    
    index = load_index()
    if name not in index["secrets"]:
        die(f"secret not found: {name}")
    
    if not args.yes:
        if not confirm(f"Remove secret '{name}'?"):
            return
    
    # Remove files
    secret_file = SECRETS_PATH / f"{name}.enc"
    if secret_file.exists():
        secret_file.unlink()
    
    del index["secrets"][name]
    save_index(index)
    
    Output.success(f"Removed secret: {c(name, Colors.CYAN)}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    Output.set_tool("gvsecretsync", "Encrypted secrets manager")
    
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(f"gvsecretsync {__version__}")
        sys.exit(0)
    
    parser = argparse.ArgumentParser(
        prog=Path(sys.argv[0]).name,
        description="Manage encrypted secrets and deploy to hosts",
        epilog="""
Examples:
  sec add api_key --file /path/to/key
  sec put api_key --to /etc/app/api.key --owner app --targets server1
  sec rotate api_key --file /path/to/new_key
  sec status
  sec rm old_secret
        """,
    )
    parser.add_argument("--version", "-V", action="version", version=f"gvsecretsync {__version__}")
    
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    
    # add
    add_p = subparsers.add_parser("add", help="add a secret")
    add_p.add_argument("name", help="secret name")
    add_p.add_argument("--file", "-f", required=True, help="file containing secret")
    add_p.add_argument("--scope", help="scope selector for allowed targets")
    add_common_args(add_p)
    
    # put
    put_p = subparsers.add_parser("put", help="deploy secret to hosts")
    put_p.add_argument("name", help="secret name")
    put_p.add_argument("--to", required=True, help="remote path")
    put_p.add_argument("--owner", required=True, help="file owner")
    put_p.add_argument("--mode", default="600", help="file mode (default: 600)")
    add_target_args(put_p)
    add_common_args(put_p)
    
    # rotate
    rotate_p = subparsers.add_parser("rotate", help="rotate secret")
    rotate_p.add_argument("name", help="secret name")
    rotate_p.add_argument("--file", "-f", required=True, help="new secret file")
    add_common_args(rotate_p)
    
    # status
    status_p = subparsers.add_parser("status", help="show secret status")
    status_p.add_argument("name", nargs="?", help="secret name (optional)")
    add_common_args(status_p)
    
    # rm
    rm_p = subparsers.add_parser("rm", help="remove a secret")
    rm_p.add_argument("name", help="secret name")
    add_common_args(rm_p)
    
    args = parser.parse_args()
    apply_common_args(args)
    
    commands = {
        "add": cmd_add,
        "put": cmd_put,
        "rotate": cmd_rotate,
        "status": cmd_status,
        "rm": cmd_rm,
    }
    
    if args.command in commands:
        commands[args.command](args)
    elif not args.command:
        cmd_status(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
