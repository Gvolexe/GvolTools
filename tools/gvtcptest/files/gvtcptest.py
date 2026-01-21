#!/usr/bin/env python3
"""
gvtcptest - TCP connectivity testing with failure classification

Test TCP connectivity to specific targets/ports and explain failures
(DNS vs routing vs firewall vs service).

Aliases: tcp, tc

Author: Gvol (gvol@nexusystems.org)
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".local" / "lib" / "gvtools"))

from gvcore import (
    __version__,
    Output, Colors, c, die,
    Host, Inventory, Target,
    add_common_args, add_target_args, get_selector_from_args, apply_common_args,
    ssh_connect, ssh_exec, get_ssh_credentials,
)


# ─────────────────────────────────────────────────────────────────────────────
# TCP Testing
# ─────────────────────────────────────────────────────────────────────────────

TCP_TEST_SCRIPT = """
#!/bin/sh
# Test TCP connectivity to endpoints
ENDPOINTS="$1"
TIMEOUT="${2:-5}"

check_tcp() {
    HOST="$1"
    PORT="$2"
    
    # Try DNS resolution first
    if command -v getent >/dev/null 2>&1; then
        RESOLVED=$(getent hosts "$HOST" 2>/dev/null | awk '{print $1}' | head -1)
    elif command -v host >/dev/null 2>&1; then
        RESOLVED=$(host "$HOST" 2>/dev/null | awk '/has address/ {print $4}' | head -1)
    elif command -v nslookup >/dev/null 2>&1; then
        RESOLVED=$(nslookup "$HOST" 2>/dev/null | awk '/^Address: / {print $2}' | head -1)
    else
        RESOLVED=""
    fi
    
    # If no resolution and host is not IP, it's DNS failure
    case "$HOST" in
        [0-9]*.[0-9]*.[0-9]*.[0-9]*) RESOLVED="$HOST" ;;
    esac
    
    if [ -z "$RESOLVED" ]; then
        echo "dns_failure"
        return
    fi
    
    # Try connection
    START=$(date +%s%N 2>/dev/null || echo 0)
    
    if command -v nc >/dev/null 2>&1; then
        nc -z -w "$TIMEOUT" "$HOST" "$PORT" >/dev/null 2>&1
        RESULT=$?
    elif command -v timeout >/dev/null 2>&1 && [ -e /dev/tcp ]; then
        timeout "$TIMEOUT" bash -c "echo >/dev/tcp/$HOST/$PORT" 2>/dev/null
        RESULT=$?
    else
        # Fallback: use Python if available
        python3 -c "import socket; s=socket.socket(); s.settimeout($TIMEOUT); s.connect(('$HOST', $PORT)); s.close()" 2>/dev/null
        RESULT=$?
    fi
    
    END=$(date +%s%N 2>/dev/null || echo 0)
    if [ "$START" != "0" ] && [ "$END" != "0" ]; then
        LATENCY_NS=$((END - START))
        LATENCY_MS=$((LATENCY_NS / 1000000))
    else
        LATENCY_MS=0
    fi
    
    if [ "$RESULT" -eq 0 ]; then
        echo "ok:$RESOLVED:$LATENCY_MS"
    elif [ "$RESULT" -eq 124 ]; then
        echo "timeout:$RESOLVED:0"
    else
        echo "refused:$RESOLVED:0"
    fi
}

RESULTS=""
IFS=','
for EP in $ENDPOINTS; do
    HOST=$(echo "$EP" | cut -d: -f1)
    PORT=$(echo "$EP" | cut -d: -f2)
    if [ -z "$PORT" ]; then
        PORT=80
    fi
    RESULT=$(check_tcp "$HOST" "$PORT")
    if [ -n "$RESULTS" ]; then
        RESULTS="${RESULTS};"
    fi
    RESULTS="${RESULTS}${HOST}:${PORT}=${RESULT}"
done

echo "$RESULTS"
"""


@dataclass
class TCPTestResult:
    """Result of a TCP connectivity test."""
    endpoint: str
    host: str
    port: int
    status: str  # ok, dns_failure, timeout, refused, unreachable
    resolved_ip: str = ""
    latency_ms: int = 0
    error: str = ""
    
    def to_dict(self) -> dict:
        return {
            "endpoint": self.endpoint,
            "host": self.host,
            "port": self.port,
            "status": self.status,
            "resolved_ip": self.resolved_ip,
            "latency_ms": self.latency_ms,
            "error": self.error,
        }


def parse_tcp_result(result_str: str) -> list[TCPTestResult]:
    """Parse TCP test results from shell script output."""
    results = []
    
    for item in result_str.strip().split(";"):
        if "=" not in item:
            continue
        
        endpoint, result = item.split("=", 1)
        parts = endpoint.split(":")
        host = parts[0]
        port = int(parts[1]) if len(parts) > 1 else 80
        
        result_parts = result.split(":")
        status = result_parts[0]
        resolved = result_parts[1] if len(result_parts) > 1 else ""
        latency = int(result_parts[2]) if len(result_parts) > 2 else 0
        
        results.append(TCPTestResult(
            endpoint=endpoint,
            host=host,
            port=port,
            status=status,
            resolved_ip=resolved,
            latency_ms=latency,
        ))
    
    return results


def tcp_test_local(host: str, port: int, timeout: int = 5) -> TCPTestResult:
    """Test TCP connectivity locally."""
    result = TCPTestResult(
        endpoint=f"{host}:{port}",
        host=host,
        port=port,
        status="unknown",
    )
    
    # DNS resolution
    try:
        resolved = socket.gethostbyname(host)
        result.resolved_ip = resolved
    except socket.gaierror:
        result.status = "dns_failure"
        result.error = "DNS resolution failed"
        return result
    
    # TCP connection
    try:
        start = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.close()
        result.latency_ms = int((time.time() - start) * 1000)
        result.status = "ok"
    except socket.timeout:
        result.status = "timeout"
        result.error = "Connection timed out"
    except ConnectionRefusedError:
        result.status = "refused"
        result.error = "Connection refused"
    except OSError as e:
        if "No route to host" in str(e) or "Network is unreachable" in str(e):
            result.status = "unreachable"
        else:
            result.status = "refused"
        result.error = str(e)
    
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

def cmd_check(args: argparse.Namespace) -> None:
    """Test TCP connectivity from remote hosts."""
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if not hosts:
        die("no hosts matched selector")
    
    endpoints = getattr(args, "to", "")
    if not endpoints:
        die("--to is required (e.g., --to 'db:5432,1.1.1.1:53')")
    
    timeout = getattr(args, "timeout", 5) or 5
    password, key_path, sudo_pass = get_ssh_credentials(args)
    
    all_results: dict[str, list[TCPTestResult]] = {}
    
    for host in hosts:
        target = Target.from_host(host, default_user=host.user or "root")
        
        try:
            Output.info(f"Testing from {c(host.name, Colors.CYAN)}...")
            client = ssh_connect(
                target,
                password=password,
                key_path=key_path,
                timeout=15,
            )
            
            code, out, err = ssh_exec(client, f'ENDPOINTS="{endpoints}"; TIMEOUT="{timeout}"; {TCP_TEST_SCRIPT}')
            client.close()
            
            if code == 0:
                results = parse_tcp_result(out)
            else:
                results = [TCPTestResult(
                    endpoint="error",
                    host="",
                    port=0,
                    status="error",
                    error=f"exit {code}: {err[:50]}"
                )]
        
        except Exception as e:
            results = [TCPTestResult(
                endpoint="error",
                host="",
                port=0,
                status="error",
                error=str(e)
            )]
        
        all_results[host.name] = results
    
    if Output.json_mode:
        Output.json_output({
            "results": {h: [r.to_dict() for r in rs] for h, rs in all_results.items()}
        })
        return
    
    Output.header(f"TCP Connectivity ({len(hosts)} hosts)")
    
    for host_name, results in all_results.items():
        Output.info(f"{c(host_name, Colors.CYAN)}")
        for r in results:
            if r.status == "ok":
                status_str = c("OK", Colors.GREEN)
                detail = f"→ {r.resolved_ip} ({r.latency_ms}ms)"
            elif r.status == "dns_failure":
                status_str = c("DNS_FAIL", Colors.RED)
                detail = "DNS resolution failed"
            elif r.status == "timeout":
                status_str = c("TIMEOUT", Colors.YELLOW)
                detail = f"→ {r.resolved_ip}"
            elif r.status == "refused":
                status_str = c("REFUSED", Colors.RED)
                detail = f"→ {r.resolved_ip}"
            elif r.status == "error":
                status_str = c("ERROR", Colors.RED)
                detail = r.error
            else:
                status_str = c(r.status.upper(), Colors.YELLOW)
                detail = r.error or ""
            
            Output.step(f"{r.endpoint}: {status_str} {detail}")


def cmd_local(args: argparse.Namespace) -> None:
    """Test TCP connectivity from local machine."""
    endpoints = getattr(args, "to", "")
    if not endpoints:
        die("--to is required (e.g., --to 'db:5432,1.1.1.1:53')")
    
    timeout = getattr(args, "timeout", 5) or 5
    results = []
    
    Output.info("Testing from local machine...")
    
    for ep in endpoints.split(","):
        ep = ep.strip()
        if not ep:
            continue
        
        parts = ep.split(":")
        host = parts[0]
        port = int(parts[1]) if len(parts) > 1 else 80
        
        result = tcp_test_local(host, port, timeout)
        results.append(result)
    
    if Output.json_mode:
        Output.json_output({"results": [r.to_dict() for r in results]})
        return
    
    Output.header("TCP Connectivity (local)")
    
    # Determine exit code
    all_ok = True
    partial_fail = False
    
    for r in results:
        if r.status == "ok":
            status_str = c("OK", Colors.GREEN)
            detail = f"→ {r.resolved_ip} ({r.latency_ms}ms)"
        elif r.status == "dns_failure":
            status_str = c("DNS_FAIL", Colors.RED)
            detail = "DNS resolution failed"
            all_ok = False
        elif r.status == "timeout":
            status_str = c("TIMEOUT", Colors.YELLOW)
            detail = f"→ {r.resolved_ip}"
            partial_fail = True
        elif r.status == "refused":
            status_str = c("REFUSED", Colors.RED)
            detail = f"→ {r.resolved_ip}"
            all_ok = False
        else:
            status_str = c(r.status.upper(), Colors.YELLOW)
            detail = r.error or ""
            partial_fail = True
        
        Output.step(f"{r.endpoint}: {status_str} {detail}")
    
    # Exit codes: 0 = all OK, 1 = partial failures, 2 = critical failures
    if not all_ok:
        sys.exit(2)
    elif partial_fail:
        sys.exit(1)


def cmd_explain(args: argparse.Namespace) -> None:
    """Detailed explanation of connectivity to one endpoint."""
    inventory = Inventory()
    
    host_name = args.target
    if not host_name:
        die("host is required")
    
    host = inventory.get(host_name)
    if not host:
        target = Target.parse(host_name)
        host = Host(name=target.host, address=target.host, port=target.port, user=target.user)
    
    endpoint = getattr(args, "to", "")
    if not endpoint:
        die("--to is required")
    
    parts = endpoint.split(":")
    dest_host = parts[0]
    dest_port = int(parts[1]) if len(parts) > 1 else 80
    
    password, key_path, sudo_pass = get_ssh_credentials(args)
    target = Target.from_host(host, default_user=host.user or "root")
    
    Output.header(f"Connection Analysis: {host.name} → {endpoint}")
    
    explain_script = f"""
#!/bin/sh
DEST="{dest_host}"
PORT="{dest_port}"

echo "=== DNS Resolution ==="
if command -v getent >/dev/null 2>&1; then
    getent hosts "$DEST" 2>&1 || echo "FAILED"
elif command -v host >/dev/null 2>&1; then
    host "$DEST" 2>&1 || echo "FAILED"
else
    echo "No DNS tools available"
fi

echo ""
echo "=== Route to destination ==="
if command -v ip >/dev/null 2>&1; then
    ip route get "$DEST" 2>&1 | head -3
else
    route -n 2>&1 | head -5
fi

echo ""
echo "=== TCP Connection Test ==="
if command -v nc >/dev/null 2>&1; then
    nc -zv -w 5 "$DEST" "$PORT" 2>&1
elif command -v timeout >/dev/null 2>&1; then
    timeout 5 bash -c "echo >/dev/tcp/$DEST/$PORT" 2>&1 && echo "SUCCESS" || echo "FAILED"
else
    echo "No TCP test tools available"
fi

echo ""
echo "=== Firewall Rules (if accessible) ==="
if command -v iptables >/dev/null 2>&1; then
    iptables -L OUTPUT -n 2>/dev/null | head -10 || echo "Cannot read iptables"
elif command -v nft >/dev/null 2>&1; then
    nft list ruleset 2>/dev/null | head -20 || echo "Cannot read nftables"
else
    echo "No firewall tools found"
fi
"""
    
    try:
        client = ssh_connect(
            target,
            password=password,
            key_path=key_path,
            timeout=15,
        )
        
        code, out, err = ssh_exec(client, explain_script, sudo=True, password=sudo_pass or password)
        client.close()
        
        if Output.json_mode:
            Output.json_output({"output": out, "exit_code": code})
            return
        
        print(out)
        if err:
            Output.warn(f"Errors: {err[:200]}")
    
    except Exception as e:
        die(f"failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Parser Setup
# ─────────────────────────────────────────────────────────────────────────────

def setup_check_parser(parser: argparse.ArgumentParser) -> None:
    add_target_args(parser)
    parser.add_argument("--to", required=True, help="endpoints to test (host:port,...)")
    add_common_args(parser)


def setup_local_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--to", required=True, help="endpoints to test (host:port,...)")
    add_common_args(parser)


def setup_explain_parser(parser: argparse.ArgumentParser) -> None:
    add_target_args(parser)
    parser.add_argument("--to", required=True, help="endpoint to analyze")
    add_common_args(parser)


cmd_check.setup_parser = setup_check_parser  # type: ignore
cmd_local.setup_parser = setup_local_parser  # type: ignore
cmd_explain.setup_parser = setup_explain_parser  # type: ignore


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    Output.set_tool("gvtcptest", "TCP connectivity testing")
    
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(f"gvtcptest {__version__}")
        sys.exit(0)
    
    invoked_as = Path(sys.argv[0]).name
    
    parser = argparse.ArgumentParser(
        prog=invoked_as,
        description="TCP connectivity testing with failure classification",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  tc check --role web --to "db:5432,1.1.1.1:53"
  tc local --to "example.com:443,db.internal:5432"
  tc explain web1.example.com --to "db:5432"

Exit codes:
  0 - all connections OK
  1 - partial failures (timeouts)
  2 - critical failures (refused, DNS failure)
        """,
    )
    parser.add_argument("--version", "-V", action="version", version=f"gvtcptest {__version__}")
    
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    
    check_p = subparsers.add_parser("check", help="test from remote hosts")
    setup_check_parser(check_p)
    
    local_p = subparsers.add_parser("local", help="test from local machine")
    setup_local_parser(local_p)
    
    explain_p = subparsers.add_parser("explain", help="detailed connection analysis")
    setup_explain_parser(explain_p)
    
    args = parser.parse_args()
    apply_common_args(args)
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    commands = {
        "check": cmd_check,
        "local": cmd_local,
        "explain": cmd_explain,
    }
    
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
