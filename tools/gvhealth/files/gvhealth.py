#!/usr/bin/env python3
"""
gvhealth - Host and service health checks across fleet

Run host-level and service-level health checks, aggregate results across a fleet,
and provide a consistent OK/WARN/FAIL output.

Aliases: health, hl

Author: Gvol (gvol@nexusystems.org)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".local" / "lib" / "gvtools"))

from gvcore import (
    __version__,
    Output, Colors, c, die,
    Inventory, Target,
    GVTOOLS_CONFIG,
    add_common_args, add_target_args, get_selector_from_args, apply_common_args,
    ssh_connect, ssh_exec, get_ssh_credentials,
)


# ─────────────────────────────────────────────────────────────────────────────
# Health Specs
# ─────────────────────────────────────────────────────────────────────────────

HEALTH_SPECS_PATH = GVTOOLS_CONFIG / "health_specs.json"

HOST_CHECK_SCRIPT = """
#!/bin/sh
# Host-level health checks

# Disk usage (root partition)
DISK_USAGE=$(df -h / 2>/dev/null | awk 'NR==2 {print $5}' | tr -d '%')
DISK_TOTAL=$(df -h / 2>/dev/null | awk 'NR==2 {print $2}')
DISK_AVAIL=$(df -h / 2>/dev/null | awk 'NR==2 {print $4}')

# Memory
MEM_TOTAL=$(free -m 2>/dev/null | awk '/^Mem:/ {print $2}')
MEM_USED=$(free -m 2>/dev/null | awk '/^Mem:/ {print $3}')
MEM_AVAIL=$(free -m 2>/dev/null | awk '/^Mem:/ {print $7}')
if [ -n "$MEM_TOTAL" ] && [ "$MEM_TOTAL" -gt 0 ]; then
    MEM_PCT=$((MEM_USED * 100 / MEM_TOTAL))
else
    MEM_PCT=0
fi

# Load average
LOAD_1=$(cat /proc/loadavg 2>/dev/null | awk '{print $1}')
LOAD_5=$(cat /proc/loadavg 2>/dev/null | awk '{print $2}')
LOAD_15=$(cat /proc/loadavg 2>/dev/null | awk '{print $3}')
CPU_COUNT=$(nproc 2>/dev/null || echo 1)

# Uptime
UPTIME_SECS=$(cat /proc/uptime 2>/dev/null | awk '{print int($1)}')
UPTIME_DAYS=$((UPTIME_SECS / 86400))

# Time sync (check if NTP is synchronized)
TIME_SYNC="unknown"
if command -v timedatectl >/dev/null 2>&1; then
    if timedatectl status 2>/dev/null | grep -q "synchronized: yes"; then
        TIME_SYNC="synced"
    else
        TIME_SYNC="not_synced"
    fi
fi

# Package updates pending
UPDATES_PENDING=0
if command -v apt-get >/dev/null 2>&1; then
    UPDATES_PENDING=$(apt-get -s upgrade 2>/dev/null | grep -c '^Inst' || echo 0)
elif command -v dnf >/dev/null 2>&1; then
    UPDATES_PENDING=$(dnf check-update 2>/dev/null | grep -c '^[a-zA-Z]' || echo 0)
elif command -v pacman >/dev/null 2>&1; then
    UPDATES_PENDING=$(pacman -Qu 2>/dev/null | wc -l || echo 0)
fi

# SSH check (we're already connected, so it works)
SSH_OK="true"

# Systemd state
SYSTEMD_STATE="unknown"
if command -v systemctl >/dev/null 2>&1; then
    SYSTEMD_STATE=$(systemctl is-system-running 2>/dev/null || echo "unknown")
fi

echo "{"
echo "  \\"disk_pct\\": $DISK_USAGE,"
echo "  \\"disk_total\\": \\"$DISK_TOTAL\\","
echo "  \\"disk_avail\\": \\"$DISK_AVAIL\\","
echo "  \\"mem_pct\\": $MEM_PCT,"
echo "  \\"mem_total_mb\\": $MEM_TOTAL,"
echo "  \\"mem_avail_mb\\": $MEM_AVAIL,"
echo "  \\"load_1\\": $LOAD_1,"
echo "  \\"load_5\\": $LOAD_5,"
echo "  \\"load_15\\": $LOAD_15,"
echo "  \\"cpu_count\\": $CPU_COUNT,"
echo "  \\"uptime_days\\": $UPTIME_DAYS,"
echo "  \\"time_sync\\": \\"$TIME_SYNC\\","
echo "  \\"updates_pending\\": $UPDATES_PENDING,"
echo "  \\"ssh_ok\\": $SSH_OK,"
echo "  \\"systemd_state\\": \\"$SYSTEMD_STATE\\","
echo "  \\"hostname\\": \\"$(hostname)\\""
echo "}"
"""

SERVICE_CHECK_SCRIPT = """
#!/bin/sh
# Check systemd services
SERVICES="$1"
RESULTS=""

for svc in $SERVICES; do
    ACTIVE=$(systemctl is-active "$svc" 2>/dev/null || echo "unknown")
    ENABLED=$(systemctl is-enabled "$svc" 2>/dev/null || echo "unknown")
    
    # Get last failure if any
    LAST_FAIL=""
    if [ "$ACTIVE" != "active" ]; then
        LAST_FAIL=$(journalctl -u "$svc" -n 1 --no-pager 2>/dev/null | tail -1 | head -c 100)
    fi
    
    if [ -n "$RESULTS" ]; then
        RESULTS="${RESULTS},"
    fi
    RESULTS="${RESULTS}{\\"name\\": \\"$svc\\", \\"active\\": \\"$ACTIVE\\", \\"enabled\\": \\"$ENABLED\\", \\"last_fail\\": \\"$LAST_FAIL\\"}"
done

echo "{"
echo "  \\"services\\": [$RESULTS],"
echo "  \\"hostname\\": \\"$(hostname)\\""
echo "}"
"""


@dataclass
class HealthResult:
    """Health check result for a host."""
    host: str
    status: str = "unknown"  # ok, warn, fail, error
    checks: dict = field(default_factory=dict)
    services: list = field(default_factory=list)
    endpoints: list = field(default_factory=list)
    error: str = ""
    
    def to_dict(self) -> dict:
        return {
            "host": self.host,
            "status": self.status,
            "checks": self.checks,
            "services": self.services,
            "endpoints": self.endpoints,
            "error": self.error,
        }


@dataclass
class HealthSpec:
    """Health check specification for a role."""
    name: str
    services: list[str] = field(default_factory=list)
    endpoints: list[str] = field(default_factory=list)
    ports: list[int] = field(default_factory=list)
    disk_warn_pct: int = 80
    disk_fail_pct: int = 95
    mem_warn_pct: int = 80
    mem_fail_pct: int = 95
    load_warn_factor: float = 2.0  # load_1 / cpu_count
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "services": self.services,
            "endpoints": self.endpoints,
            "ports": self.ports,
            "disk_warn_pct": self.disk_warn_pct,
            "disk_fail_pct": self.disk_fail_pct,
            "mem_warn_pct": self.mem_warn_pct,
            "mem_fail_pct": self.mem_fail_pct,
            "load_warn_factor": self.load_warn_factor,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "HealthSpec":
        return cls(
            name=data.get("name", ""),
            services=data.get("services", []),
            endpoints=data.get("endpoints", []),
            ports=data.get("ports", []),
            disk_warn_pct=data.get("disk_warn_pct", 80),
            disk_fail_pct=data.get("disk_fail_pct", 95),
            mem_warn_pct=data.get("mem_warn_pct", 80),
            mem_fail_pct=data.get("mem_fail_pct", 95),
            load_warn_factor=data.get("load_warn_factor", 2.0),
        )


class HealthSpecManager:
    """Manage health specifications."""
    
    def __init__(self, path: Path = HEALTH_SPECS_PATH):
        self.path = path
        self.specs: dict[str, HealthSpec] = {}
        self._load()
    
    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            for name, spec_data in data.get("specs", {}).items():
                spec_data["name"] = name
                self.specs[name] = HealthSpec.from_dict(spec_data)
        except Exception as e:
            Output.warn(f"could not load health specs: {e}")
    
    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"specs": {n: s.to_dict() for n, s in self.specs.items()}}
        self.path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    
    def get(self, name: str) -> HealthSpec | None:
        return self.specs.get(name)
    
    def add(self, spec: HealthSpec) -> None:
        self.specs[spec.name] = spec


def evaluate_status(checks: dict, spec: HealthSpec | None = None) -> str:
    """Evaluate overall status from checks."""
    if not spec:
        spec = HealthSpec(name="default")
    
    status = "ok"
    
    # Disk
    disk_pct = checks.get("disk_pct", 0)
    if disk_pct >= spec.disk_fail_pct:
        return "fail"
    if disk_pct >= spec.disk_warn_pct:
        status = "warn"
    
    # Memory
    mem_pct = checks.get("mem_pct", 0)
    if mem_pct >= spec.mem_fail_pct:
        return "fail"
    if mem_pct >= spec.mem_warn_pct:
        status = "warn"
    
    # Load
    load_1 = checks.get("load_1", 0)
    cpu_count = checks.get("cpu_count", 1) or 1
    if load_1 / cpu_count > spec.load_warn_factor:
        status = "warn"
    
    # Systemd state
    systemd_state = checks.get("systemd_state", "")
    if systemd_state == "degraded":
        status = "warn"
    elif systemd_state not in ("running", "unknown", ""):
        return "fail"
    
    # Time sync
    if checks.get("time_sync") == "not_synced":
        if status == "ok":
            status = "warn"
    
    return status


# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

def cmd_host(args: argparse.Namespace) -> None:
    """Run host-level health checks."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if not hosts:
        die("no hosts matched selector")
    
    password, key_path, sudo_pass = get_ssh_credentials(args)
    results = []
    
    for host in hosts:
        target = Target.from_host(host, default_user=host.user or "root")
        result = HealthResult(host=host.name)
        
        try:
            Output.info(f"Checking {c(host.name, Colors.CYAN)}...")
            client = ssh_connect(
                target,
                password=password,
                key_path=key_path,
                timeout=getattr(args, "timeout", 15),
            )
            
            code, out, err = ssh_exec(client, HOST_CHECK_SCRIPT, sudo=True, password=sudo_pass or password)
            client.close()
            
            if code == 0:
                try:
                    data = json.loads(out)
                    result.checks = data
                    result.status = evaluate_status(data)
                except json.JSONDecodeError:
                    result.error = f"invalid output: {out[:100]}"
                    result.status = "error"
            else:
                result.error = f"exit {code}: {err[:100]}"
                result.status = "error"
        
        except Exception as e:
            result.error = str(e)
            result.status = "error"
        
        results.append(result)
    
    if Output.json_mode:
        Output.json_output({"hosts": [r.to_dict() for r in results]})
        return
    
    Output.header(f"Host Health ({len(results)} hosts)")
    
    headers = ["Host", "Status", "Disk", "Memory", "Load", "Uptime", "Updates"]
    rows = []
    for r in results:
        if r.error:
            status_str = c("ERROR", Colors.RED)
            rows.append([c(r.host, Colors.CYAN), status_str, "-", "-", "-", "-", "-"])
        else:
            status_color = {"ok": Colors.GREEN, "warn": Colors.YELLOW, "fail": Colors.RED}.get(r.status, Colors.DIM)
            status_str = c(r.status.upper(), status_color)
            
            disk = f"{r.checks.get('disk_pct', 0)}%"
            mem = f"{r.checks.get('mem_pct', 0)}%"
            load = f"{r.checks.get('load_1', 0)}"
            uptime = f"{r.checks.get('uptime_days', 0)}d"
            updates = str(r.checks.get('updates_pending', 0))
            
            rows.append([c(r.host, Colors.CYAN), status_str, disk, mem, load, uptime, updates])
    
    Output.table(headers, rows)


def cmd_services(args: argparse.Namespace) -> None:
    """Check systemd services on hosts."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if not hosts:
        die("no hosts matched selector")
    
    services = getattr(args, "services", "") or "sshd"
    services_list = services.replace(",", " ")
    
    password, key_path, sudo_pass = get_ssh_credentials(args)
    results = []
    
    for host in hosts:
        target = Target.from_host(host, default_user=host.user or "root")
        result = HealthResult(host=host.name)
        
        try:
            Output.info(f"Checking services on {c(host.name, Colors.CYAN)}...")
            client = ssh_connect(
                target,
                password=password,
                key_path=key_path,
                timeout=getattr(args, "timeout", 15),
            )
            
            script = f'{SERVICE_CHECK_SCRIPT.replace("$1", services_list)}'
            code, out, err = ssh_exec(client, f'SERVICES="{services_list}"; {SERVICE_CHECK_SCRIPT}')
            client.close()
            
            if code == 0:
                try:
                    # Find JSON in output
                    start = out.find("{")
                    end = out.rfind("}") + 1
                    if start >= 0 and end > start:
                        data = json.loads(out[start:end])
                        result.services = data.get("services", [])
                        # Check if any services failed
                        failed = [s for s in result.services if s.get("active") != "active"]
                        result.status = "fail" if failed else "ok"
                    else:
                        result.error = "no JSON found"
                        result.status = "error"
                except json.JSONDecodeError:
                    result.error = f"invalid output: {out[:100]}"
                    result.status = "error"
            else:
                result.error = f"exit {code}: {err[:100]}"
                result.status = "error"
        
        except Exception as e:
            result.error = str(e)
            result.status = "error"
        
        results.append(result)
    
    if Output.json_mode:
        Output.json_output({"hosts": [r.to_dict() for r in results]})
        return
    
    Output.header(f"Service Health ({len(results)} hosts)")
    
    for r in results:
        status_color = {"ok": Colors.GREEN, "warn": Colors.YELLOW, "fail": Colors.RED, "error": Colors.RED}.get(r.status, Colors.DIM)
        Output.info(f"{c(r.host, Colors.CYAN)}: {c(r.status.upper(), status_color)}")
        
        if r.error:
            Output.step(f"Error: {r.error}")
        
        for svc in r.services:
            active = svc.get("active", "unknown")
            enabled = svc.get("enabled", "unknown")
            svc_color = Colors.GREEN if active == "active" else Colors.RED
            Output.step(f"{svc.get('name')}: {c(active, svc_color)} (enabled: {enabled})")


def cmd_endpoints(args: argparse.Namespace) -> None:
    """Check HTTP endpoints on hosts."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if not hosts:
        die("no hosts matched selector")
    
    endpoints = getattr(args, "endpoints", "") or ""
    if not endpoints:
        die("--endpoints is required")
    
    endpoint_list = [e.strip() for e in endpoints.split(",") if e.strip()]
    
    password, key_path, sudo_pass = get_ssh_credentials(args)
    results = []
    
    for host in hosts:
        target = Target.from_host(host, default_user=host.user or "root")
        result = HealthResult(host=host.name)
        
        try:
            Output.info(f"Checking endpoints on {c(host.name, Colors.CYAN)}...")
            client = ssh_connect(
                target,
                password=password,
                key_path=key_path,
                timeout=getattr(args, "timeout", 15),
            )
            
            for endpoint in endpoint_list:
                check_cmd = f'curl -sf -o /dev/null -w "%{{http_code}},%{{time_total}}" --connect-timeout 5 "{endpoint}"'
                code, out, err = ssh_exec(client, check_cmd)
                
                parts = out.strip().split(",")
                http_code = parts[0] if parts else "000"
                latency = parts[1] if len(parts) > 1 else "0"
                
                ep_result = {
                    "url": endpoint,
                    "status_code": http_code,
                    "latency_ms": int(float(latency) * 1000) if latency else 0,
                    "ok": http_code in ("200", "201", "204"),
                }
                result.endpoints.append(ep_result)
            
            client.close()
            
            failed = [e for e in result.endpoints if not e.get("ok")]
            result.status = "fail" if failed else "ok"
        
        except Exception as e:
            result.error = str(e)
            result.status = "error"
        
        results.append(result)
    
    if Output.json_mode:
        Output.json_output({"hosts": [r.to_dict() for r in results]})
        return
    
    Output.header(f"Endpoint Health ({len(results)} hosts)")
    
    for r in results:
        status_color = {"ok": Colors.GREEN, "fail": Colors.RED, "error": Colors.RED}.get(r.status, Colors.DIM)
        Output.info(f"{c(r.host, Colors.CYAN)}: {c(r.status.upper(), status_color)}")
        
        if r.error:
            Output.step(f"Error: {r.error}")
        
        for ep in r.endpoints:
            ep_color = Colors.GREEN if ep.get("ok") else Colors.RED
            Output.step(f"{ep.get('url')}: {c(ep.get('status_code'), ep_color)} ({ep.get('latency_ms')}ms)")


def cmd_summary(args: argparse.Namespace) -> None:
    """Fleet health summary."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if not hosts:
        die("no hosts matched selector")
    
    password, key_path, sudo_pass = get_ssh_credentials(args)
    results = []
    
    for host in hosts:
        target = Target.from_host(host, default_user=host.user or "root")
        result = HealthResult(host=host.name)
        result.checks["env"] = host.env
        result.checks["roles"] = host.roles
        result.checks["tags"] = host.tags
        
        try:
            client = ssh_connect(
                target,
                password=password,
                key_path=key_path,
                timeout=getattr(args, "timeout", 15),
            )
            
            code, out, err = ssh_exec(client, HOST_CHECK_SCRIPT, sudo=True, password=sudo_pass or password)
            client.close()
            
            if code == 0:
                try:
                    data = json.loads(out)
                    result.checks.update(data)
                    result.status = evaluate_status(data)
                except json.JSONDecodeError:
                    result.status = "error"
            else:
                result.status = "error"
        except Exception as e:
            result.status = "error"
            result.error = str(e)
        
        results.append(result)
    
    if Output.json_mode:
        Output.json_output({"hosts": [r.to_dict() for r in results]})
        return
    
    # Aggregate by group
    group_by = getattr(args, "group_by", "env") or "env"
    groups: dict[str, list[HealthResult]] = {}
    
    for r in results:
        if group_by == "role":
            roles = r.checks.get("roles", [])
            key = roles[0] if roles else "none"
        elif group_by == "tag":
            tags = r.checks.get("tags", [])
            key = tags[0] if tags else "none"
        else:  # env
            key = r.checks.get("env") or "none"
        
        if key not in groups:
            groups[key] = []
        groups[key].append(r)
    
    Output.header(f"Fleet Summary (by {group_by})")
    
    headers = ["Group", "Hosts", "OK", "Warn", "Fail", "Error"]
    rows = []
    
    for group_name, group_results in sorted(groups.items()):
        ok = len([r for r in group_results if r.status == "ok"])
        warn = len([r for r in group_results if r.status == "warn"])
        fail = len([r for r in group_results if r.status == "fail"])
        error = len([r for r in group_results if r.status == "error"])
        
        rows.append([
            c(group_name, Colors.CYAN),
            str(len(group_results)),
            c(str(ok), Colors.GREEN) if ok else "0",
            c(str(warn), Colors.YELLOW) if warn else "0",
            c(str(fail), Colors.RED) if fail else "0",
            c(str(error), Colors.RED) if error else "0",
        ])
    
    Output.table(headers, rows)
    
    # Total
    total_ok = len([r for r in results if r.status == "ok"])
    total_warn = len([r for r in results if r.status == "warn"])
    total_fail = len([r for r in results if r.status == "fail"])
    total_error = len([r for r in results if r.status == "error"])
    
    print()
    Output.info(f"Total: {len(results)} hosts - "
                f"{c(str(total_ok), Colors.GREEN)} OK, "
                f"{c(str(total_warn), Colors.YELLOW)} WARN, "
                f"{c(str(total_fail), Colors.RED)} FAIL, "
                f"{c(str(total_error), Colors.RED)} ERROR")


def cmd_define(args: argparse.Namespace) -> None:
    """Define health spec for a role."""
    manager = HealthSpecManager()
    
    name = args.role
    
    # Parse spec from file or args
    if args.spec:
        try:
            spec_data = json.loads(Path(args.spec).read_text())
            spec_data["name"] = name
            spec = HealthSpec.from_dict(spec_data)
        except Exception as e:
            die(f"could not load spec: {e}")
    else:
        spec = HealthSpec(
            name=name,
            services=[s.strip() for s in (args.services or "").split(",") if s.strip()],
            endpoints=[e.strip() for e in (args.endpoints or "").split(",") if e.strip()],
        )
    
    manager.add(spec)
    manager.save()
    
    if Output.json_mode:
        Output.json_output({"status": "ok", "spec": spec.to_dict()})
    else:
        Output.success(f"Defined health spec: {c(name, Colors.CYAN)}")


# ─────────────────────────────────────────────────────────────────────────────
# Parser Setup
# ─────────────────────────────────────────────────────────────────────────────

def setup_host_parser(parser: argparse.ArgumentParser) -> None:
    add_target_args(parser)
    add_common_args(parser)


def setup_services_parser(parser: argparse.ArgumentParser) -> None:
    add_target_args(parser)
    parser.add_argument("--services", "-s", required=True, help="comma-separated services")
    add_common_args(parser)


def setup_endpoints_parser(parser: argparse.ArgumentParser) -> None:
    add_target_args(parser)
    parser.add_argument("--endpoints", "-e", required=True, help="comma-separated HTTP endpoints")
    add_common_args(parser)


def setup_summary_parser(parser: argparse.ArgumentParser) -> None:
    add_target_args(parser)
    parser.add_argument("--group-by", "-g", choices=["env", "role", "tag"], default="env", help="grouping")
    add_common_args(parser)


def setup_define_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("role", help="role name for spec")
    parser.add_argument("--spec", help="path to spec JSON file")
    parser.add_argument("--services", help="comma-separated services")
    parser.add_argument("--endpoints", help="comma-separated endpoints")
    add_common_args(parser)


cmd_host.setup_parser = setup_host_parser  # type: ignore
cmd_services.setup_parser = setup_services_parser  # type: ignore
cmd_endpoints.setup_parser = setup_endpoints_parser  # type: ignore
cmd_summary.setup_parser = setup_summary_parser  # type: ignore
cmd_define.setup_parser = setup_define_parser  # type: ignore


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    Output.set_tool("gvhealth", "Host & service health checks")
    
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(f"gvhealth {__version__}")
        sys.exit(0)
    
    invoked_as = Path(sys.argv[0]).name
    
    parser = argparse.ArgumentParser(
        prog=invoked_as,
        description="Host and service health checks across fleet",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  hl host web1.example.com
  hl host --role web
  hl services --role web --services "nginx,sshd"
  hl endpoints --role web --endpoints "https://example.com/health"
  hl summary --env prod --group-by role
  hl define web --services "nginx,php-fpm" --endpoints "http://localhost/health"
        """,
    )
    parser.add_argument("--version", "-V", action="version", version=f"gvhealth {__version__}")
    
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    
    host_p = subparsers.add_parser("host", help="host-level health checks")
    setup_host_parser(host_p)
    
    services_p = subparsers.add_parser("services", help="check systemd services")
    setup_services_parser(services_p)
    
    endpoints_p = subparsers.add_parser("endpoints", help="check HTTP endpoints")
    setup_endpoints_parser(endpoints_p)
    
    summary_p = subparsers.add_parser("summary", help="fleet health summary")
    setup_summary_parser(summary_p)
    
    define_p = subparsers.add_parser("define", help="define health spec for role")
    setup_define_parser(define_p)
    
    args = parser.parse_args()
    apply_common_args(args)
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    commands = {
        "host": cmd_host,
        "services": cmd_services,
        "endpoints": cmd_endpoints,
        "summary": cmd_summary,
        "define": cmd_define,
    }
    
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
