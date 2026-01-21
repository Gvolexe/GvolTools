#!/usr/bin/env python3
"""
gvbackupctl - Backup configuration and verification

Configure backups and verify restore integrity.

Aliases: bk, backup, gvbk

Author: Gvol (gvol@nexusystems.org)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".local" / "lib" / "gvtools"))

from gvcore import (
    Output, Colors, c, die,
    Target, Inventory, GVTOOLS_CONFIG,
    add_common_args, add_target_args, get_selector_from_args, apply_common_args,
    ssh_connect, ssh_exec,
)

__version__ = "1.1.6"

BACKUP_CONFIG = GVTOOLS_CONFIG / "backupctl"
BACKUP_INDEX = BACKUP_CONFIG / "backups.json"


def load_backup_config() -> dict:
    if not BACKUP_INDEX.exists():
        return {"backups": {}}
    return json.loads(BACKUP_INDEX.read_text())


def save_backup_config(data: dict) -> None:
    BACKUP_CONFIG.mkdir(parents=True, exist_ok=True)
    BACKUP_INDEX.write_text(json.dumps(data, indent=2))


def make_init_script(backend: str, repo: str, paths: str) -> str:
    """Generate backup init script (uses restic)."""
    paths_list = paths.replace(",", " ")
    
    if backend == "local":
        return f"""
set -e
if ! command -v restic >/dev/null 2>&1; then
    echo "Installing restic..."
    apt-get update -qq && apt-get install -y -qq restic || pacman -S --noconfirm restic
fi

# Initialize repo if needed
if [ ! -d "{repo}" ] || [ ! -f "{repo}/config" ]; then
    restic init --repo "{repo}"
fi

echo "Backup configured:"
echo "  Repo: {repo}"
echo "  Paths: {paths_list}"
echo "OK"
"""
    elif backend == "s3":
        return f"""
set -e
if ! command -v restic >/dev/null 2>&1; then
    apt-get update -qq && apt-get install -y -qq restic || pacman -S --noconfirm restic
fi

# S3 requires AWS credentials in environment
restic init --repo "s3:{repo}" 2>/dev/null || echo "Repo may already exist"
echo "S3 backup configured: {repo}"
echo "OK"
"""
    else:
        return f'echo "Backend {backend} not implemented"; exit 1'


def make_run_script(repo: str, paths: str) -> str:
    paths_list = paths.replace(",", " ")
    return f"""
set -e
echo "Running backup..."
restic backup --repo "{repo}" {paths_list}
echo "Cleaning old snapshots..."
restic forget --repo "{repo}" --keep-last 7 --keep-weekly 4 --keep-monthly 6 --prune
echo "OK: backup complete"
"""


def make_verify_script(repo: str) -> str:
    return f"""
set -e
echo "=== BACKUP STATUS ==="
restic --repo "{repo}" snapshots --latest 5

echo ""
echo "=== INTEGRITY CHECK ==="
restic --repo "{repo}" check --read-data-subset=1% 2>&1 | tail -5

echo ""
echo "=== LATEST BACKUP ==="
restic --repo "{repo}" snapshots --latest 1 --json 2>/dev/null | head -20
"""


def cmd_init(args: argparse.Namespace) -> None:
    """Initialize backup configuration."""
    backend = args.backend
    repo = args.repo
    paths = args.paths or "/etc,/home"
    
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector) if not selector.is_empty() else []
    
    if not hosts:
        die("no targets specified")
    
    Output.header(f"Initialize Backup: {backend}")
    
    script = make_init_script(backend, repo, paths)
    
    if args.dry_run:
        Output.info("Would initialize on:")
        for h in hosts:
            Output.step(h.name)
        return
    
    config = load_backup_config()
    
    for host in hosts:
        Output.info(f"Configuring {host.name}...")
        target = Target.from_host(host, default_user="root")
        
        try:
            client = ssh_connect(target, strict_hostkey=args.strict_hostkey)
            exit_code, stdout, stderr = ssh_exec(client, script, sudo=True)
            client.close()
            
            if exit_code == 0:
                Output.success(f"Initialized {host.name}")
                config["backups"][host.name] = {
                    "backend": backend,
                    "repo": repo,
                    "paths": paths,
                    "created": datetime.now().isoformat(),
                }
            else:
                Output.error(f"Failed on {host.name}: {stderr}")
        except Exception as e:
            Output.error(f"Failed on {host.name}: {e}")
    
    save_backup_config(config)


def cmd_run(args: argparse.Namespace) -> None:
    """Run backup."""
    config = load_backup_config()
    
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector) if not selector.is_empty() else []
    
    if not hosts:
        die("no targets specified")
    
    Output.header("Run Backups")
    
    for host in hosts:
        if host.name not in config.get("backups", {}):
            Output.warn(f"{host.name} not configured, skipping")
            continue
        
        bc = config["backups"][host.name]
        script = make_run_script(bc["repo"], bc["paths"])
        
        Output.info(f"Backing up {host.name}...")
        target = Target.from_host(host, default_user="root")
        
        try:
            client = ssh_connect(target, strict_hostkey=args.strict_hostkey)
            exit_code, stdout, stderr = ssh_exec(client, script, sudo=True)
            client.close()
            
            if exit_code == 0:
                Output.success(f"Completed {host.name}")
                config["backups"][host.name]["last_run"] = datetime.now().isoformat()
            else:
                Output.error(f"Failed on {host.name}")
        except Exception as e:
            Output.error(f"Failed on {host.name}: {e}")
    
    save_backup_config(config)


def cmd_verify(args: argparse.Namespace) -> None:
    """Verify backup integrity."""
    config = load_backup_config()
    
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector) if not selector.is_empty() else []
    
    if not hosts:
        die("no targets specified")
    
    for host in hosts:
        Output.header(f"Verify: {host.name}")
        
        if host.name not in config.get("backups", {}):
            Output.warn("Not configured")
            continue
        
        bc = config["backups"][host.name]
        script = make_verify_script(bc["repo"])
        
        target = Target.from_host(host, default_user="root")
        
        try:
            client = ssh_connect(target, strict_hostkey=args.strict_hostkey)
            exit_code, stdout, stderr = ssh_exec(client, script, sudo=True)
            client.close()
            print(stdout)
        except Exception as e:
            Output.error(str(e))


def cmd_status(args: argparse.Namespace) -> None:
    """Show backup status."""
    config = load_backup_config()
    
    if Output.json_mode:
        Output.json_output(config)
        return
    
    backups = config.get("backups", {})
    if not backups:
        Output.info("No backups configured")
        return
    
    Output.header(f"Backup Status ({len(backups)} hosts)")
    
    headers = ["Host", "Backend", "Paths", "Last Run"]
    rows = []
    for name, info in backups.items():
        rows.append([
            c(name, Colors.CYAN),
            info.get("backend", "-"),
            info.get("paths", "-")[:30],
            info.get("last_run", "never")[:10] if info.get("last_run") else "never",
        ])
    
    Output.table(headers, rows)


def cmd_restore(args: argparse.Namespace) -> None:
    """Restore from backup."""
    target_str = args.target
    snapshot = args.snapshot
    to_path = args.to
    
    config = load_backup_config()
    
    target = Target.parse(target_str)
    if target.host not in config.get("backups", {}):
        die(f"no backup config for {target.host}")
    
    bc = config["backups"][target.host]
    
    Output.header(f"Restore: {target.host}")
    Output.warn("This will restore files to the specified path!")
    
    script = f"""
set -e
restic restore --repo "{bc['repo']}" {snapshot} --target "{to_path}"
echo "OK: restored to {to_path}"
"""
    
    if args.dry_run:
        Output.info(f"Would restore snapshot {snapshot} to {to_path}")
        return
    
    try:
        client = ssh_connect(target, strict_hostkey=args.strict_hostkey)
        exit_code, stdout, stderr = ssh_exec(client, script, sudo=True)
        client.close()
        
        if exit_code == 0:
            Output.success("Restore complete")
        else:
            Output.error(f"Restore failed: {stderr}")
    except Exception as e:
        Output.error(str(e))


def main() -> None:
    Output.set_tool("gvbackupctl", "Backup manager")
    
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(f"gvbackupctl {__version__}")
        sys.exit(0)
    
    parser = argparse.ArgumentParser(
        prog=Path(sys.argv[0]).name,
        description="Configure backups and verify integrity",
        epilog="""
Examples:
  bk init --backend local --repo /backup --paths "/etc,/srv" --targets server1
  bk run --targets server1
  bk verify --targets server1
  bk status
  bk restore server1 --snapshot latest --to /tmp/restore
        """,
    )
    parser.add_argument("--version", "-V", action="version", version=f"gvbackupctl {__version__}")
    
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    
    init_p = subparsers.add_parser("init", help="initialize backup")
    init_p.add_argument("--backend", "-b", required=True, choices=["local", "s3", "ssh"])
    init_p.add_argument("--repo", "-r", required=True, help="repository path/URL")
    init_p.add_argument("--paths", "-p", help="paths to backup (comma-separated)")
    add_target_args(init_p)
    add_common_args(init_p)
    
    run_p = subparsers.add_parser("run", help="run backup")
    add_target_args(run_p)
    add_common_args(run_p)
    
    verify_p = subparsers.add_parser("verify", help="verify backup")
    add_target_args(verify_p)
    add_common_args(verify_p)
    
    status_p = subparsers.add_parser("status", help="show status")
    add_common_args(status_p)
    
    restore_p = subparsers.add_parser("restore", help="restore from backup")
    restore_p.add_argument("target", help="target host")
    restore_p.add_argument("--snapshot", "-s", default="latest", help="snapshot ID")
    restore_p.add_argument("--to", "-t", required=True, help="restore destination")
    add_common_args(restore_p)
    
    args = parser.parse_args()
    apply_common_args(args)
    
    commands = {
        "init": cmd_init,
        "run": cmd_run,
        "verify": cmd_verify,
        "status": cmd_status,
        "restore": cmd_restore,
    }
    
    if args.command in commands:
        commands[args.command](args)
    elif not args.command:
        cmd_status(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
