#!/usr/bin/env python3
"""
gvpolicy - Policy rules for fleet security and ops baselines

Define policy rules for your fleet (security/hardening/ops baselines)
and evaluate compliance.

Aliases: pol, pl

Author: Gvol (gvol@nexusystems.org)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
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
# Policy Configuration
# ─────────────────────────────────────────────────────────────────────────────

POLICY_PATH = GVTOOLS_CONFIG / "policies.json"
WAIVERS_PATH = GVTOOLS_CONFIG / "policy_waivers.json"

# Built-in checks
BUILTIN_CHECKS = {
    "ssh.password_disabled": {
        "description": "SSH password authentication is disabled",
        "script": "grep -qE '^PasswordAuthentication\\s+no' /etc/ssh/sshd_config",
    },
    "ssh.root_login_disabled": {
        "description": "SSH root login is disabled",
        "script": "grep -qE '^PermitRootLogin\\s+no' /etc/ssh/sshd_config",
    },
    "ssh.key_only": {
        "description": "SSH accepts only key authentication",
        "script": "grep -qE '^PubkeyAuthentication\\s+yes' /etc/ssh/sshd_config",
    },
    "updates.unattended_enabled": {
        "description": "Unattended security updates are enabled",
        "script": "systemctl is-enabled unattended-upgrades 2>/dev/null || dpkg -l unattended-upgrades 2>/dev/null | grep -q '^ii'",
    },
    "fw.ufw_enabled": {
        "description": "UFW firewall is enabled",
        "script": "ufw status 2>/dev/null | grep -q 'Status: active'",
    },
    "fw.iptables_active": {
        "description": "iptables has active rules",
        "script": "iptables -L INPUT -n 2>/dev/null | wc -l | xargs test 3 -lt",
    },
    "time.ntp_synced": {
        "description": "System time is NTP synchronized",
        "script": "timedatectl status 2>/dev/null | grep -q 'synchronized: yes'",
    },
    "disk.usage_below_90": {
        "description": "Disk usage is below 90%",
        "script": "df / | awk 'NR==2 {gsub(/%/,\"\",$5); exit ($5 >= 90)}'",
    },
    "sudoers.nopasswd_limited": {
        "description": "NOPASSWD sudo is limited to specific users",
        "script": "! grep -r 'NOPASSWD.*ALL.*ALL' /etc/sudoers /etc/sudoers.d/ 2>/dev/null | grep -v '^#'",
    },
}


@dataclass
class PolicyRule:
    """A policy rule definition."""
    name: str
    check_id: str
    scope: str = "*"  # Selector pattern
    severity: str = "medium"  # low, medium, high
    enabled: bool = True
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "check_id": self.check_id,
            "scope": self.scope,
            "severity": self.severity,
            "enabled": self.enabled,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "PolicyRule":
        return cls(
            name=data.get("name", ""),
            check_id=data.get("check_id", ""),
            scope=data.get("scope", "*"),
            severity=data.get("severity", "medium"),
            enabled=data.get("enabled", True),
        )


@dataclass
class PolicyWaiver:
    """A policy waiver."""
    rule_name: str
    host: str
    until: str  # ISO date
    reason: str
    created: str = ""
    
    def to_dict(self) -> dict:
        return {
            "rule_name": self.rule_name,
            "host": self.host,
            "until": self.until,
            "reason": self.reason,
            "created": self.created,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "PolicyWaiver":
        return cls(
            rule_name=data.get("rule_name", ""),
            host=data.get("host", ""),
            until=data.get("until", ""),
            reason=data.get("reason", ""),
            created=data.get("created", ""),
        )
    
    def is_active(self) -> bool:
        try:
            until_date = datetime.fromisoformat(self.until)
            return datetime.now() < until_date
        except Exception:
            return False


class PolicyManager:
    """Manage policy rules."""
    
    def __init__(self, path: Path = POLICY_PATH):
        self.path = path
        self.rules: dict[str, PolicyRule] = {}
        self._load()
    
    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            for name, rule_data in data.get("rules", {}).items():
                rule_data["name"] = name
                self.rules[name] = PolicyRule.from_dict(rule_data)
        except Exception as e:
            Output.warn(f"could not load policies: {e}")
    
    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"rules": {n: r.to_dict() for n, r in self.rules.items()}}
        self.path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    
    def add(self, rule: PolicyRule) -> None:
        self.rules[rule.name] = rule
    
    def remove(self, name: str) -> bool:
        if name in self.rules:
            del self.rules[name]
            return True
        return False


class WaiverManager:
    """Manage policy waivers."""
    
    def __init__(self, path: Path = WAIVERS_PATH):
        self.path = path
        self.waivers: list[PolicyWaiver] = []
        self._load()
    
    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.waivers = [PolicyWaiver.from_dict(w) for w in data.get("waivers", [])]
        except Exception as e:
            Output.warn(f"could not load waivers: {e}")
    
    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"waivers": [w.to_dict() for w in self.waivers]}
        self.path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    
    def add(self, waiver: PolicyWaiver) -> None:
        self.waivers.append(waiver)
    
    def get_active(self, rule_name: str, host: str) -> PolicyWaiver | None:
        for w in self.waivers:
            if w.rule_name == rule_name and w.host == host and w.is_active():
                return w
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

def cmd_rule_add(args: argparse.Namespace) -> None:
    """Add a policy rule."""
    manager = PolicyManager()
    
    name = args.name
    check_id = args.check
    
    if check_id not in BUILTIN_CHECKS:
        Output.warn(f"check '{check_id}' is not a builtin check - will need custom implementation")
    
    rule = PolicyRule(
        name=name,
        check_id=check_id,
        scope=getattr(args, "scope", "*") or "*",
        severity=getattr(args, "severity", "medium") or "medium",
    )
    
    manager.add(rule)
    manager.save()
    
    if Output.json_mode:
        Output.json_output({"status": "ok", "rule": rule.to_dict()})
    else:
        Output.success(f"Added rule: {c(name, Colors.CYAN)}")


def cmd_rule_del(args: argparse.Namespace) -> None:
    """Delete a policy rule."""
    manager = PolicyManager()
    
    name = args.name
    if not manager.remove(name):
        die(f"rule not found: {name}")
    
    manager.save()
    
    if Output.json_mode:
        Output.json_output({"status": "ok", "deleted": name})
    else:
        Output.success(f"Deleted rule: {c(name, Colors.CYAN)}")


def cmd_rule_list(args: argparse.Namespace) -> None:
    """List policy rules."""
    manager = PolicyManager()
    
    if Output.json_mode:
        Output.json_output({"rules": [r.to_dict() for r in manager.rules.values()]})
        return
    
    if not manager.rules:
        Output.info("No policy rules defined. Add one with: pl rule add <name> --check <check-id>")
        Output.info("Available checks:")
        for check_id, check in BUILTIN_CHECKS.items():
            Output.step(f"{check_id}: {check['description']}")
        return
    
    Output.header(f"Policy Rules ({len(manager.rules)})")
    
    headers = ["Name", "Check", "Scope", "Severity", "Enabled"]
    rows = []
    for r in sorted(manager.rules.values(), key=lambda x: x.name):
        sev_color = {"low": Colors.DIM, "medium": Colors.YELLOW, "high": Colors.RED}.get(r.severity, Colors.DIM)
        rows.append([
            c(r.name, Colors.CYAN),
            r.check_id,
            r.scope,
            c(r.severity, sev_color),
            c("yes", Colors.GREEN) if r.enabled else c("no", Colors.RED),
        ])
    
    Output.table(headers, rows)


def cmd_eval(args: argparse.Namespace) -> None:
    """Evaluate policies against hosts."""
    policy_mgr = PolicyManager()
    waiver_mgr = WaiverManager()
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if not hosts:
        die("no hosts matched selector")
    
    if not policy_mgr.rules:
        die("no policy rules defined")
    
    password, key_path, sudo_pass = get_ssh_credentials(args)
    timeout = getattr(args, "timeout", 15) or 15
    
    results = []
    
    for host in hosts:
        target = Target.from_host(host, default_user=host.user or "root")
        host_results = {"host": host.name, "checks": [], "score": 0, "max_score": 0}
        
        try:
            client = ssh_connect(target, password=password, key_path=key_path, timeout=timeout)
            
            for rule in policy_mgr.rules.values():
                if not rule.enabled:
                    continue
                
                # Check if waived
                waiver = waiver_mgr.get_active(rule.name, host.name)
                if waiver:
                    host_results["checks"].append({
                        "rule": rule.name,
                        "status": "waived",
                        "reason": waiver.reason,
                    })
                    continue
                
                # Get check script
                if rule.check_id in BUILTIN_CHECKS:
                    script = BUILTIN_CHECKS[rule.check_id]["script"]
                else:
                    script = f"echo 'Unknown check: {rule.check_id}'; exit 1"
                
                code, out, err = ssh_exec(client, script, sudo=True, password=sudo_pass or password)
                
                passed = code == 0
                severity_weight = {"low": 1, "medium": 2, "high": 3}.get(rule.severity, 2)
                
                host_results["max_score"] += severity_weight
                if passed:
                    host_results["score"] += severity_weight
                
                host_results["checks"].append({
                    "rule": rule.name,
                    "check_id": rule.check_id,
                    "status": "pass" if passed else "fail",
                    "severity": rule.severity,
                })
            
            client.close()
        
        except Exception as e:
            host_results["error"] = str(e)
        
        results.append(host_results)
    
    if Output.json_mode:
        Output.json_output({"results": results})
        return
    
    Output.header(f"Policy Evaluation ({len(results)} hosts)")
    
    for hr in results:
        if hr.get("error"):
            Output.error(f"{hr['host']}: {hr['error']}")
            continue
        
        score_pct = int(hr["score"] * 100 / hr["max_score"]) if hr["max_score"] > 0 else 0
        score_color = Colors.GREEN if score_pct >= 80 else (Colors.YELLOW if score_pct >= 60 else Colors.RED)
        
        Output.info(f"{c(hr['host'], Colors.CYAN)}: {c(f'{score_pct}%', score_color)} ({hr['score']}/{hr['max_score']})")
        
        for check in hr["checks"]:
            if check["status"] == "pass":
                status_str = c("PASS", Colors.GREEN)
            elif check["status"] == "waived":
                status_str = c("WAIVED", Colors.YELLOW)
            else:
                status_str = c("FAIL", Colors.RED)
            Output.step(f"{check['rule']}: {status_str}")


def cmd_waive(args: argparse.Namespace) -> None:
    """Add a policy waiver."""
    waiver_mgr = WaiverManager()
    
    rule = args.rule
    host = args.host
    until = getattr(args, "until", "") or ""
    reason = getattr(args, "reason", "") or ""
    
    if not until:
        die("--until is required")
    if not reason:
        die("--reason is required")
    
    waiver = PolicyWaiver(
        rule_name=rule,
        host=host,
        until=until,
        reason=reason,
        created=datetime.now().isoformat(),
    )
    
    waiver_mgr.add(waiver)
    waiver_mgr.save()
    
    if Output.json_mode:
        Output.json_output({"status": "ok", "waiver": waiver.to_dict()})
    else:
        Output.success(f"Added waiver for {rule} on {host} until {until}")


def cmd_checks(args: argparse.Namespace) -> None:
    """List available checks."""
    if Output.json_mode:
        Output.json_output({"checks": BUILTIN_CHECKS})
        return
    
    Output.header("Available Policy Checks")
    
    for check_id, check in sorted(BUILTIN_CHECKS.items()):
        Output.info(c(check_id, Colors.CYAN))
        Output.step(check["description"])


# ─────────────────────────────────────────────────────────────────────────────
# Parser Setup
# ─────────────────────────────────────────────────────────────────────────────

def setup_rule_add_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("name", help="rule name")
    parser.add_argument("--check", required=True, help="check ID")
    parser.add_argument("--scope", default="*", help="selector scope")
    parser.add_argument("--severity", choices=["low", "medium", "high"], default="medium")
    add_common_args(parser)


def setup_rule_del_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("name", help="rule name")
    add_common_args(parser)


def setup_rule_list_parser(parser: argparse.ArgumentParser) -> None:
    add_common_args(parser)


def setup_eval_parser(parser: argparse.ArgumentParser) -> None:
    add_target_args(parser)
    add_common_args(parser)


def setup_waive_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("rule", help="rule name")
    parser.add_argument("host", help="host name")
    parser.add_argument("--until", required=True, help="expiry date (ISO format)")
    parser.add_argument("--reason", required=True, help="waiver reason")
    add_common_args(parser)


def setup_checks_parser(parser: argparse.ArgumentParser) -> None:
    add_common_args(parser)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    Output.set_tool("gvpolicy", "Fleet policy management")
    
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(f"gvpolicy {__version__}")
        sys.exit(0)
    
    invoked_as = Path(sys.argv[0]).name
    
    parser = argparse.ArgumentParser(
        prog=invoked_as,
        description="Policy rules for fleet security and ops baselines",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  pl checks                                    # List available checks
  pl rule add ssh-hardened --check ssh.password_disabled --severity high
  pl rule list
  pl eval --role web
  pl waive ssh-hardened web1 --until 2024-12-31 --reason "Legacy app requires password auth"
        """,
    )
    parser.add_argument("--version", "-V", action="version", version=f"gvpolicy {__version__}")
    
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    
    # Rule subcommands
    rule_p = subparsers.add_parser("rule", help="manage rules")
    rule_sub = rule_p.add_subparsers(dest="rule_command", metavar="subcommand")
    
    rule_add_p = rule_sub.add_parser("add", help="add a rule")
    setup_rule_add_parser(rule_add_p)
    
    rule_del_p = rule_sub.add_parser("del", help="delete a rule")
    setup_rule_del_parser(rule_del_p)
    
    rule_list_p = rule_sub.add_parser("list", help="list rules")
    setup_rule_list_parser(rule_list_p)
    
    # Other commands
    eval_p = subparsers.add_parser("eval", help="evaluate policies")
    setup_eval_parser(eval_p)
    
    waive_p = subparsers.add_parser("waive", help="add waiver")
    setup_waive_parser(waive_p)
    
    checks_p = subparsers.add_parser("checks", help="list available checks")
    setup_checks_parser(checks_p)
    
    args = parser.parse_args()
    apply_common_args(args)
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    if args.command == "rule":
        if not hasattr(args, "rule_command") or not args.rule_command:
            rule_p.print_help()
            sys.exit(0)
        
        rule_commands = {
            "add": cmd_rule_add,
            "del": cmd_rule_del,
            "list": cmd_rule_list,
        }
        if args.rule_command in rule_commands:
            rule_commands[args.rule_command](args)
    elif args.command == "eval":
        cmd_eval(args)
    elif args.command == "waive":
        cmd_waive(args)
    elif args.command == "checks":
        cmd_checks(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
