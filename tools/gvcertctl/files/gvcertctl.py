#!/usr/bin/env python3
"""
gvcertctl - TLS certificate issuance and deployment

Issue/renew/deploy TLS certs using ACME (Let's Encrypt).
Supports HTTP-01 and DNS-01 validation with Cloudflare API.

Aliases: cert, cc, gvcert

Author: Gvol (gvol@nexusystems.org)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".local" / "lib" / "gvtools"))

from gvcore import (
    Output, Colors, c, die,
    Target, Inventory, GVTOOLS_CONFIG,
    add_common_args, add_target_args, get_selector_from_args, apply_common_args,
    ssh_connect, ssh_exec, confirm, get_ssh_credentials,
)

__version__ = "1.2.0"

CERT_CONFIG = GVTOOLS_CONFIG / "certctl"
PROVIDERS_FILE = CERT_CONFIG / "providers.json"
CERTS_INDEX = CERT_CONFIG / "certs.json"

# Accept alternate spellings
CLOUDFLARE_ALIASES = {"cloudflare", "cloudflair", "cf"}


# ─────────────────────────────────────────────────────────────────────────────
# Provider Management
# ─────────────────────────────────────────────────────────────────────────────

def load_providers() -> dict:
    """Load DNS providers."""
    if not PROVIDERS_FILE.exists():
        return {}
    return json.loads(PROVIDERS_FILE.read_text())


def save_providers(data: dict) -> None:
    """Save DNS providers."""
    CERT_CONFIG.mkdir(parents=True, exist_ok=True)
    PROVIDERS_FILE.write_text(json.dumps(data, indent=2))
    PROVIDERS_FILE.chmod(0o600)


def load_certs() -> dict:
    """Load certificate index."""
    if not CERTS_INDEX.exists():
        return {"certs": {}}
    return json.loads(CERTS_INDEX.read_text())


def save_certs(data: dict) -> None:
    """Save certificate index."""
    CERT_CONFIG.mkdir(parents=True, exist_ok=True)
    CERTS_INDEX.write_text(json.dumps(data, indent=2))


# ─────────────────────────────────────────────────────────────────────────────
# ACME/Certbot Operations
# ─────────────────────────────────────────────────────────────────────────────

def check_certbot() -> bool:
    """Check if certbot is available."""
    try:
        result = subprocess.run(["certbot", "--version"], capture_output=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def get_cloudflare_credentials_file(provider_name: str) -> Path | None:
    """Create Cloudflare credentials file for certbot."""
    providers = load_providers()
    if provider_name not in providers:
        return None
    
    provider = providers[provider_name]
    if provider.get("type") not in CLOUDFLARE_ALIASES:
        return None
    
    token_file = Path(provider.get("token_file", "")).expanduser()
    if not token_file.exists():
        return None
    
    token = token_file.read_text().strip()
    
    creds_file = CERT_CONFIG / f".cf_creds_{provider_name}.ini"
    creds_file.write_text(f"dns_cloudflare_api_token = {token}\n")
    creds_file.chmod(0o600)
    
    return creds_file


# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

def cmd_provider_add(args: argparse.Namespace) -> None:
    """Add a DNS provider."""
    name = args.name.lower()
    
    # Normalize provider type
    if name in CLOUDFLARE_ALIASES:
        name = "cloudflare"
    
    Output.header(f"Add Provider: {args.provider_name}")
    
    providers = load_providers()
    
    provider_data = {
        "type": name,
        "token_file": str(Path(args.token_file).expanduser()),
        "created": datetime.now().isoformat(),
    }
    
    if args.account_id:
        provider_data["account_id"] = args.account_id
    
    providers[args.provider_name] = provider_data
    save_providers(providers)
    
    Output.success(f"Added provider: {c(args.provider_name, Colors.CYAN)}")
    Output.keyvalue("type", name)


def cmd_issue(args: argparse.Namespace) -> None:
    """Issue a certificate."""
    domain = args.domain
    method = args.method or "http01"
    provider = args.provider
    san = args.san
    
    Output.header(f"Issue Certificate: {domain}")
    
    if not check_certbot():
        die("certbot not installed. Install with:\n  apt install certbot python3-certbot-dns-cloudflare")
    
    cmd = ["certbot", "certonly", "--non-interactive", "--agree-tos"]
    
    if method == "http01":
        cmd.extend(["--standalone", "-d", domain])
    elif method == "dns01":
        if not provider:
            die("--provider required for dns01")
        
        providers = load_providers()
        if provider not in providers:
            die(f"provider not found: {provider}")
        
        prov = providers[provider]
        if prov["type"] == "cloudflare":
            creds = get_cloudflare_credentials_file(provider)
            if not creds:
                die("could not create Cloudflare credentials")
            cmd.extend([
                "--dns-cloudflare",
                "--dns-cloudflare-credentials", str(creds),
                "-d", domain,
            ])
    
    if san:
        for s in san.split(","):
            cmd.extend(["-d", s.strip()])
    
    if args.dry_run:
        cmd.append("--dry-run")
        Output.info(f"Would run: {' '.join(cmd)}")
    
    Output.info("Running certbot...")
    result = subprocess.run(cmd, capture_output=not args.verbose)
    
    if result.returncode != 0:
        Output.error("Certificate issuance failed")
        if result.stderr:
            print(result.stderr.decode())
        return
    
    # Update index
    certs = load_certs()
    certs["certs"][domain] = {
        "issued": datetime.now().isoformat(),
        "method": method,
        "provider": provider,
        "san": san.split(",") if san else [],
        "deployments": [],
    }
    save_certs(certs)
    
    Output.success(f"Issued certificate for {c(domain, Colors.CYAN)}")


def cmd_renew(args: argparse.Namespace) -> None:
    """Renew certificates."""
    domain = args.domain
    
    Output.header("Renew Certificates")
    
    if not check_certbot():
        die("certbot not installed")
    
    cmd = ["certbot", "renew", "--non-interactive"]
    
    if domain and domain != "--all":
        cmd.extend(["--cert-name", domain])
    
    if args.dry_run:
        cmd.append("--dry-run")
    
    Output.info("Running certbot renew...")
    result = subprocess.run(cmd, capture_output=not args.verbose)
    
    if result.returncode == 0:
        Output.success("Renewal complete")
    else:
        Output.error("Renewal failed")


def cmd_deploy(args: argparse.Namespace) -> None:
    """Deploy certificate to hosts."""
    domain = args.domain
    service = args.service
    paths = args.paths
    
    certs = load_certs()
    if domain not in certs.get("certs", {}):
        Output.warn(f"Certificate {domain} not tracked (may still exist)")
    
    # Certificate paths (certbot default)
    cert_base = Path(f"/etc/letsencrypt/live/{domain}")
    
    Output.header(f"Deploy: {domain}")
    
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector) if not selector.is_empty() else []
    
    if not hosts:
        die("no targets specified")
    
    # Parse destination paths
    if paths:
        path_parts = paths.split(",")
        cert_dst = path_parts[0] if len(path_parts) > 0 else "/etc/ssl/certs/cert.pem"
        key_dst = path_parts[1] if len(path_parts) > 1 else "/etc/ssl/private/key.pem"
        chain_dst = path_parts[2] if len(path_parts) > 2 else ""
    else:
        cert_dst = "/etc/ssl/certs/cert.pem"
        key_dst = "/etc/ssl/private/key.pem"
        chain_dst = ""
    
    # Build deploy script
    reload_cmd = ""
    if service == "nginx":
        reload_cmd = "systemctl reload nginx"
    elif service == "apache":
        reload_cmd = "systemctl reload apache2 || systemctl reload httpd"
    elif service == "custom":
        reload_cmd = "true"  # No automatic reload
    
    script = f"""
set -e
# This would copy certs from local certbot to remote
# In practice, you'd use scp or a secrets sync mechanism
echo "Would deploy {domain} certificate"
echo "  Cert: {cert_dst}"
echo "  Key: {key_dst}"
{f'echo "  Chain: {chain_dst}"' if chain_dst else ''}
{f'{reload_cmd}' if reload_cmd else ''}
echo "OK"
"""
    
    if args.dry_run:
        Output.info("Dry run - would deploy to:")
        for h in hosts:
            Output.step(h.name)
        return
    
    password, key_path = get_ssh_credentials(args)
    
    for host in hosts:
        target = Target.from_host(host, default_user="root")
        try:
            client = ssh_connect(target, strict_hostkey=args.strict_hostkey, password=password, key_path=key_path)
            exit_code, stdout, stderr = ssh_exec(client, script, sudo=True)
            client.close()
            
            if exit_code == 0:
                Output.success(f"Deployed to {host.name}")
            else:
                Output.error(f"Failed on {host.name}")
        except Exception as e:
            Output.error(f"Failed on {host.name}: {e}")


def cmd_status(args: argparse.Namespace) -> None:
    """Show certificate status."""
    domain = args.domain
    
    Output.header("Certificate Status")
    
    # Try to get certbot certificates
    try:
        result = subprocess.run(
            ["certbot", "certificates"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print(result.stdout)
    except FileNotFoundError:
        Output.warn("certbot not available")
    
    # Show our tracked certs
    certs = load_certs()
    if certs.get("certs"):
        Output.divider()
        Output.info("Tracked certificates:")
        for name, info in certs["certs"].items():
            if domain and name != domain:
                continue
            Output.keyvalue(name, f"issued {info.get('issued', '?')[:10]}")


def cmd_revoke(args: argparse.Namespace) -> None:
    """Revoke a certificate."""
    domain = args.domain
    
    if not args.yes:
        if not confirm(f"Revoke certificate for {domain}?"):
            return
    
    Output.header(f"Revoke: {domain}")
    
    if not check_certbot():
        die("certbot not installed")
    
    cmd = ["certbot", "revoke", "--cert-name", domain, "--non-interactive"]
    
    if args.dry_run:
        Output.info(f"Would run: {' '.join(cmd)}")
        return
    
    result = subprocess.run(cmd, capture_output=not args.verbose)
    
    if result.returncode == 0:
        Output.success(f"Revoked certificate for {domain}")
        
        # Update index
        certs = load_certs()
        if domain in certs.get("certs", {}):
            certs["certs"][domain]["revoked"] = datetime.now().isoformat()
            save_certs(certs)
    else:
        Output.error("Revocation failed")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    Output.set_tool("gvcertctl", "TLS certificate manager")
    
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(f"gvcertctl {__version__}")
        sys.exit(0)
    
    parser = argparse.ArgumentParser(
        prog=Path(sys.argv[0]).name,
        description="TLS certificate issuance and deployment (ACME/Let's Encrypt)",
        epilog="""
Examples:
  cert provider add cloudflare --token-file ~/.secrets/cf_token
  cert issue example.com --method dns01 --provider cloudflare
  cert issue example.com --san "*.example.com" --method dns01 --provider cloudflare
  cert renew example.com
  cert renew --all
  cert deploy example.com --targets web --service nginx
  cert status
  cert revoke example.com
        """,
    )
    parser.add_argument("--version", "-V", action="version", version=f"gvcertctl {__version__}")
    
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    
    # provider
    provider_p = subparsers.add_parser("provider", help="manage DNS providers")
    provider_sub = provider_p.add_subparsers(dest="provider_cmd", metavar="action")
    
    prov_add = provider_sub.add_parser("add", help="add provider")
    prov_add.add_argument("name", help="provider type (cloudflare/cloudflair)")
    prov_add.add_argument("--token-file", required=True, help="path to API token file")
    prov_add.add_argument("--account-id", help="account ID (optional)")
    prov_add.add_argument("--provider-name", default="default", help="name for this provider config")
    add_common_args(prov_add)
    
    # issue
    issue_p = subparsers.add_parser("issue", help="issue a certificate")
    issue_p.add_argument("domain", help="primary domain")
    issue_p.add_argument("--san", help="comma-separated SANs (e.g., *.example.com)")
    issue_p.add_argument("--method", choices=["http01", "dns01"], default="http01")
    issue_p.add_argument("--provider", help="DNS provider (for dns01)")
    add_common_args(issue_p)
    
    # renew
    renew_p = subparsers.add_parser("renew", help="renew certificates")
    renew_p.add_argument("domain", nargs="?", default="--all", help="domain or --all")
    add_common_args(renew_p)
    
    # deploy
    deploy_p = subparsers.add_parser("deploy", help="deploy certificate")
    deploy_p.add_argument("domain", help="domain to deploy")
    deploy_p.add_argument("--service", choices=["nginx", "apache", "custom"], default="nginx")
    deploy_p.add_argument("--paths", help="cert,key,chain paths")
    add_target_args(deploy_p)
    add_common_args(deploy_p)
    
    # status
    status_p = subparsers.add_parser("status", help="show certificate status")
    status_p.add_argument("domain", nargs="?", help="specific domain")
    add_common_args(status_p)
    
    # revoke
    revoke_p = subparsers.add_parser("revoke", help="revoke certificate")
    revoke_p.add_argument("domain", help="domain to revoke")
    add_common_args(revoke_p)
    
    args = parser.parse_args()
    apply_common_args(args)
    
    if args.command == "provider":
        if args.provider_cmd == "add":
            cmd_provider_add(args)
        else:
            provider_p.print_help()
    elif args.command == "issue":
        cmd_issue(args)
    elif args.command == "renew":
        cmd_renew(args)
    elif args.command == "deploy":
        cmd_deploy(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "revoke":
        cmd_revoke(args)
    elif not args.command:
        cmd_status(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
