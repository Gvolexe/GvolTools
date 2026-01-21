#!/usr/bin/env python3
"""
gvnginxctl - Nginx configuration testing and management

Fleet-safe nginx config testing, reloads, and vhost management.

Aliases: ngx, nx

Author: Gvol (gvol@nexusystems.org)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".local" / "lib" / "gvtools"))

from gvcore import (
    __version__,
    Output, Colors, c, die,
    Host, Inventory, Target,
    add_common_args, add_target_args, get_selector_from_args, apply_common_args,
    confirm, ssh_connect, ssh_exec, get_ssh_credentials,
)


# ─────────────────────────────────────────────────────────────────────────────
# Nginx Management
# ─────────────────────────────────────────────────────────────────────────────

NGINX_STATUS_SCRIPT = '''
set -e

# Check nginx status
if command -v nginx &>/dev/null; then
    NGINX_BIN=$(which nginx)
    VERSION=$($NGINX_BIN -v 2>&1 | head -1)
else
    echo "nginx_installed=false"
    exit 0
fi

echo "nginx_installed=true"
echo "nginx_version=$VERSION"

# Check if running
if pgrep -x nginx &>/dev/null; then
    echo "nginx_running=true"
    MASTER_PID=$(pgrep -x nginx | head -1)
    echo "nginx_pid=$MASTER_PID"
    WORKERS=$(pgrep -x nginx | wc -l)
    echo "nginx_workers=$((WORKERS - 1))"
else
    echo "nginx_running=false"
fi

# Check systemd status
if systemctl is-enabled nginx &>/dev/null 2>&1; then
    echo "nginx_enabled=true"
else
    echo "nginx_enabled=false"
fi

# Config file location
if [ -f /etc/nginx/nginx.conf ]; then
    echo "nginx_config=/etc/nginx/nginx.conf"
elif [ -f /usr/local/nginx/conf/nginx.conf ]; then
    echo "nginx_config=/usr/local/nginx/conf/nginx.conf"
fi

# Test config
if $NGINX_BIN -t 2>&1 | grep -q "syntax is ok"; then
    echo "config_valid=true"
else
    echo "config_valid=false"
fi

# Sites
if [ -d /etc/nginx/sites-enabled ]; then
    SITES=$(ls -1 /etc/nginx/sites-enabled 2>/dev/null | tr '\n' ',' | sed 's/,$//')
    echo "sites_enabled=$SITES"
fi

if [ -d /etc/nginx/sites-available ]; then
    SITES=$(ls -1 /etc/nginx/sites-available 2>/dev/null | tr '\n' ',' | sed 's/,$//')
    echo "sites_available=$SITES"
fi
'''


def parse_nginx_status(output: str) -> dict:
    """Parse nginx status output."""
    result = {}
    for line in output.strip().split("\n"):
        if "=" in line:
            key, value = line.split("=", 1)
            if value.lower() == "true":
                result[key] = True
            elif value.lower() == "false":
                result[key] = False
            elif value.isdigit():
                result[key] = int(value)
            else:
                result[key] = value
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

def cmd_status(args: argparse.Namespace) -> None:
    """Show nginx status on hosts."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if not hosts:
        die("no hosts matched selector")
    
    password, key_path, sudo_pass = get_ssh_credentials(args)
    timeout = getattr(args, "timeout", 15) or 15
    
    results = []
    
    for host in hosts:
        target = Target.from_host(host, default_user=host.user or "root")
        
        try:
            client = ssh_connect(target, password=password, key_path=key_path, timeout=timeout)
            code, out, err = ssh_exec(client, NGINX_STATUS_SCRIPT, sudo=True, password=sudo_pass or password)
            client.close()
            
            status = parse_nginx_status(out)
            status["host"] = host.name
            status["success"] = True
            results.append(status)
        
        except Exception as e:
            results.append({"host": host.name, "success": False, "error": str(e)})
    
    if Output.json_mode:
        Output.json_output({"results": results})
        return
    
    Output.header(f"Nginx Status ({len(results)} hosts)")
    
    headers = ["Host", "Version", "Running", "Workers", "Config Valid", "Sites"]
    rows = []
    
    for r in results:
        if not r.get("success"):
            rows.append([c(r["host"], Colors.RED), f"error: {r.get('error', 'unknown')}", "", "", "", ""])
            continue
        
        if not r.get("nginx_installed"):
            rows.append([r["host"], c("not installed", Colors.DIM), "", "", "", ""])
            continue
        
        version = r.get("nginx_version", "").replace("nginx version: ", "")
        running = c("yes", Colors.GREEN) if r.get("nginx_running") else c("no", Colors.RED)
        workers = str(r.get("nginx_workers", "-"))
        config_valid = c("yes", Colors.GREEN) if r.get("config_valid") else c("no", Colors.RED)
        sites = r.get("sites_enabled", "") or ""
        
        rows.append([c(r["host"], Colors.CYAN), version, running, workers, config_valid, sites])
    
    Output.table(headers, rows)


def cmd_test(args: argparse.Namespace) -> None:
    """Test nginx configuration."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if not hosts:
        die("no hosts matched selector")
    
    password, key_path, sudo_pass = get_ssh_credentials(args)
    
    results = []
    
    for host in hosts:
        target = Target.from_host(host, default_user=host.user or "root")
        
        try:
            client = ssh_connect(target, password=password, key_path=key_path)
            code, out, err = ssh_exec(client, "nginx -t 2>&1", sudo=True, password=sudo_pass or password)
            client.close()
            
            success = code == 0
            results.append({
                "host": host.name,
                "success": success,
                "output": out.strip() if success else (err.strip() or out.strip()),
            })
            
            if not Output.json_mode:
                if success:
                    Output.success(f"{host.name}: config valid")
                else:
                    Output.error(f"{host.name}: {err.strip() or out.strip()}")
        
        except Exception as e:
            results.append({"host": host.name, "success": False, "error": str(e)})
            if not Output.json_mode:
                Output.error(f"{host.name}: {e}")
    
    if Output.json_mode:
        Output.json_output({"results": results})


def cmd_reload(args: argparse.Namespace) -> None:
    """Reload nginx configuration."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if not hosts:
        die("no hosts matched selector")
    
    password, key_path, sudo_pass = get_ssh_credentials(args)
    force = getattr(args, "force", False)
    
    results = []
    
    for host in hosts:
        target = Target.from_host(host, default_user=host.user or "root")
        
        try:
            client = ssh_connect(target, password=password, key_path=key_path)
            
            # Test first unless --force
            if not force:
                code, out, err = ssh_exec(client, "nginx -t 2>&1", sudo=True, password=sudo_pass or password)
                if code != 0:
                    results.append({
                        "host": host.name,
                        "success": False,
                        "error": f"config test failed: {err.strip() or out.strip()}",
                    })
                    if not Output.json_mode:
                        Output.error(f"{host.name}: config test failed, skipping reload")
                    client.close()
                    continue
            
            # Reload
            code, out, err = ssh_exec(
                client, "systemctl reload nginx 2>&1 || nginx -s reload 2>&1",
                sudo=True, password=sudo_pass or password
            )
            client.close()
            
            success = code == 0
            results.append({"host": host.name, "success": success, "error": err.strip() if not success else ""})
            
            if not Output.json_mode:
                if success:
                    Output.success(f"{host.name}: reloaded")
                else:
                    Output.error(f"{host.name}: reload failed - {err.strip()}")
        
        except Exception as e:
            results.append({"host": host.name, "success": False, "error": str(e)})
            if not Output.json_mode:
                Output.error(f"{host.name}: {e}")
    
    if Output.json_mode:
        Output.json_output({"results": results})


def cmd_restart(args: argparse.Namespace) -> None:
    """Restart nginx service."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if not hosts:
        die("no hosts matched selector")
    
    password, key_path, sudo_pass = get_ssh_credentials(args)
    
    if not getattr(args, "yes", False):
        if not confirm(f"Restart nginx on {len(hosts)} host(s)?"):
            die("aborted")
    
    results = []
    
    for host in hosts:
        target = Target.from_host(host, default_user=host.user or "root")
        
        try:
            client = ssh_connect(target, password=password, key_path=key_path)
            code, out, err = ssh_exec(client, "systemctl restart nginx", sudo=True, password=sudo_pass or password)
            client.close()
            
            success = code == 0
            results.append({"host": host.name, "success": success, "error": err.strip() if not success else ""})
            
            if not Output.json_mode:
                if success:
                    Output.success(f"{host.name}: restarted")
                else:
                    Output.error(f"{host.name}: restart failed - {err.strip()}")
        
        except Exception as e:
            results.append({"host": host.name, "success": False, "error": str(e)})
            if not Output.json_mode:
                Output.error(f"{host.name}: {e}")
    
    if Output.json_mode:
        Output.json_output({"results": results})


def cmd_site_enable(args: argparse.Namespace) -> None:
    """Enable a site."""
    site = args.site
    
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if not hosts:
        die("no hosts matched selector")
    
    password, key_path, sudo_pass = get_ssh_credentials(args)
    
    results = []
    
    for host in hosts:
        target = Target.from_host(host, default_user=host.user or "root")
        
        try:
            client = ssh_connect(target, password=password, key_path=key_path)
            
            cmd = f'''
            if [ ! -f /etc/nginx/sites-available/{site} ]; then
                echo "site not found" >&2
                exit 1
            fi
            ln -sf /etc/nginx/sites-available/{site} /etc/nginx/sites-enabled/{site}
            nginx -t
            '''
            
            code, out, err = ssh_exec(client, cmd, sudo=True, password=sudo_pass or password)
            client.close()
            
            success = code == 0
            results.append({"host": host.name, "success": success, "site": site, "error": err.strip() if not success else ""})
            
            if not Output.json_mode:
                if success:
                    Output.success(f"{host.name}: enabled {site}")
                else:
                    Output.error(f"{host.name}: {err.strip()}")
        
        except Exception as e:
            results.append({"host": host.name, "success": False, "error": str(e)})
            if not Output.json_mode:
                Output.error(f"{host.name}: {e}")
    
    if Output.json_mode:
        Output.json_output({"results": results})


def cmd_site_disable(args: argparse.Namespace) -> None:
    """Disable a site."""
    site = args.site
    
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if not hosts:
        die("no hosts matched selector")
    
    password, key_path, sudo_pass = get_ssh_credentials(args)
    
    results = []
    
    for host in hosts:
        target = Target.from_host(host, default_user=host.user or "root")
        
        try:
            client = ssh_connect(target, password=password, key_path=key_path)
            
            cmd = f'''
            if [ ! -f /etc/nginx/sites-enabled/{site} ]; then
                echo "site not enabled" >&2
                exit 1
            fi
            rm -f /etc/nginx/sites-enabled/{site}
            nginx -t
            '''
            
            code, out, err = ssh_exec(client, cmd, sudo=True, password=sudo_pass or password)
            client.close()
            
            success = code == 0
            results.append({"host": host.name, "success": success, "site": site, "error": err.strip() if not success else ""})
            
            if not Output.json_mode:
                if success:
                    Output.success(f"{host.name}: disabled {site}")
                else:
                    Output.error(f"{host.name}: {err.strip()}")
        
        except Exception as e:
            results.append({"host": host.name, "success": False, "error": str(e)})
            if not Output.json_mode:
                Output.error(f"{host.name}: {e}")
    
    if Output.json_mode:
        Output.json_output({"results": results})


def cmd_logs(args: argparse.Namespace) -> None:
    """Show nginx logs."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if not hosts:
        die("no hosts matched selector")
    
    password, key_path, sudo_pass = get_ssh_credentials(args)
    
    log_type = getattr(args, "type", "access") or "access"
    lines = getattr(args, "lines", 50) or 50
    follow = getattr(args, "follow", False)
    
    if log_type == "access":
        log_file = "/var/log/nginx/access.log"
    elif log_type == "error":
        log_file = "/var/log/nginx/error.log"
    else:
        log_file = log_type
    
    for host in hosts:
        target = Target.from_host(host, default_user=host.user or "root")
        
        if not Output.json_mode:
            Output.header(f"Logs: {host.name} ({log_type})")
        
        try:
            client = ssh_connect(target, password=password, key_path=key_path)
            
            if follow:
                # Can't do follow in batch mode, just get recent
                cmd = f"tail -n {lines} {log_file}"
            else:
                cmd = f"tail -n {lines} {log_file}"
            
            code, out, err = ssh_exec(client, cmd, sudo=True, password=sudo_pass or password)
            client.close()
            
            if Output.json_mode:
                Output.json_output({"host": host.name, "log": log_type, "content": out})
            else:
                print(out)
        
        except Exception as e:
            if Output.json_mode:
                Output.json_output({"host": host.name, "error": str(e)})
            else:
                Output.error(f"{host.name}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Parser Setup
# ─────────────────────────────────────────────────────────────────────────────

def setup_status_parser(parser: argparse.ArgumentParser) -> None:
    add_target_args(parser)
    add_common_args(parser)


def setup_test_parser(parser: argparse.ArgumentParser) -> None:
    add_target_args(parser)
    add_common_args(parser)


def setup_reload_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--force", "-f", action="store_true", help="skip config test")
    add_target_args(parser)
    add_common_args(parser)


def setup_restart_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--yes", "-y", action="store_true", help="skip confirmation")
    add_target_args(parser)
    add_common_args(parser)


def setup_site_enable_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("site", help="site name")
    add_target_args(parser)
    add_common_args(parser)


def setup_site_disable_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("site", help="site name")
    add_target_args(parser)
    add_common_args(parser)


def setup_logs_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--type", "-t", choices=["access", "error"], default="access", help="log type")
    parser.add_argument("--lines", "-n", type=int, default=50, help="number of lines")
    parser.add_argument("--follow", "-f", action="store_true", help="follow log (limited)")
    add_target_args(parser)
    add_common_args(parser)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    Output.set_tool("gvnginxctl", "Nginx management for fleet")
    
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(f"gvnginxctl {__version__}")
        sys.exit(0)
    
    invoked_as = Path(sys.argv[0]).name
    
    parser = argparse.ArgumentParser(
        prog=invoked_as,
        description="Nginx configuration testing and management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ngx status --role web
  ngx test --host web1
  ngx reload --role web
  ngx restart --role web --yes
  ngx site enable mysite --host web1
  ngx site disable mysite --host web1
  ngx logs --type error --lines 100 --host web1
        """,
    )
    parser.add_argument("--version", "-V", action="version", version=f"gvnginxctl {__version__}")
    
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    
    status_p = subparsers.add_parser("status", help="show nginx status")
    setup_status_parser(status_p)
    
    test_p = subparsers.add_parser("test", help="test configuration")
    setup_test_parser(test_p)
    
    reload_p = subparsers.add_parser("reload", help="reload configuration")
    setup_reload_parser(reload_p)
    
    restart_p = subparsers.add_parser("restart", help="restart nginx")
    setup_restart_parser(restart_p)
    
    logs_p = subparsers.add_parser("logs", help="show logs")
    setup_logs_parser(logs_p)
    
    # Site subcommands
    site_p = subparsers.add_parser("site", help="manage sites")
    site_sub = site_p.add_subparsers(dest="site_command", metavar="subcommand")
    
    site_enable_p = site_sub.add_parser("enable", help="enable site")
    setup_site_enable_parser(site_enable_p)
    
    site_disable_p = site_sub.add_parser("disable", help="disable site")
    setup_site_disable_parser(site_disable_p)
    
    args = parser.parse_args()
    apply_common_args(args)
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    commands = {
        "status": cmd_status,
        "test": cmd_test,
        "reload": cmd_reload,
        "restart": cmd_restart,
        "logs": cmd_logs,
    }
    
    if args.command in commands:
        commands[args.command](args)
    elif args.command == "site":
        if not hasattr(args, "site_command") or not args.site_command:
            site_p.print_help()
            sys.exit(0)
        if args.site_command == "enable":
            cmd_site_enable(args)
        elif args.site_command == "disable":
            cmd_site_disable(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
