#!/usr/bin/env python3
"""
gvdnsprovider - DNS provider credential and configuration store

Unified credential and configuration store for DNS providers (Cloudflare, etc.)
to be consumed by gvcertctl and gvdnscheck.

Aliases: dnsprov, dp

Author: Gvol (gvol@nexusystems.org)
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".local" / "lib" / "gvtools"))

from gvcore import (
    __version__,
    Output, Colors, c, die,
    GVTOOLS_CONFIG,
    add_common_args, apply_common_args,
    confirm,
)


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

DNS_PROVIDERS_PATH = GVTOOLS_CONFIG / "dns_providers.json"

# Provider name normalization
PROVIDER_ALIASES = {
    "cloudflare": "cloudflare",
    "cloudflair": "cloudflare",  # Common typo
    "cf": "cloudflare",
    "route53": "route53",
    "aws": "route53",
    "digitalocean": "digitalocean",
    "do": "digitalocean",
    "linode": "linode",
    "vultr": "vultr",
    "gandi": "gandi",
    "namecheap": "namecheap",
    "godaddy": "godaddy",
}

SUPPORTED_PROVIDERS = ["cloudflare", "route53", "digitalocean", "linode", "vultr", "gandi"]


@dataclass
class DNSProvider:
    """DNS provider configuration."""
    name: str
    provider_type: str  # cloudflare, route53, etc.
    token: str = ""  # Encrypted or reference
    api_key: str = ""
    api_email: str = ""
    account_id: str = ""
    default_zone: str = ""
    options: dict = field(default_factory=dict)
    
    def to_dict(self, redact: bool = True) -> dict:
        data = {
            "name": self.name,
            "provider_type": self.provider_type,
            "account_id": self.account_id,
            "default_zone": self.default_zone,
            "options": self.options,
        }
        if redact:
            data["token"] = "***" if self.token else ""
            data["api_key"] = "***" if self.api_key else ""
            data["api_email"] = self.api_email  # Email is not secret
        else:
            data["token"] = self.token
            data["api_key"] = self.api_key
            data["api_email"] = self.api_email
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> "DNSProvider":
        return cls(
            name=data.get("name", ""),
            provider_type=data.get("provider_type", ""),
            token=data.get("token", ""),
            api_key=data.get("api_key", ""),
            api_email=data.get("api_email", ""),
            account_id=data.get("account_id", ""),
            default_zone=data.get("default_zone", ""),
            options=data.get("options", {}),
        )


class DNSProviderManager:
    """Manage DNS provider configurations."""
    
    def __init__(self, path: Path = DNS_PROVIDERS_PATH):
        self.path = path
        self.providers: dict[str, DNSProvider] = {}
        self._load()
    
    def _load(self) -> None:
        if not self.path.exists():
            return
        
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            for name, prov_data in data.get("providers", {}).items():
                prov_data["name"] = name
                self.providers[name] = DNSProvider.from_dict(prov_data)
        except (json.JSONDecodeError, OSError) as e:
            Output.warn(f"could not load DNS providers: {e}")
    
    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "providers": {name: p.to_dict(redact=False) for name, p in self.providers.items()}
        }
        self.path.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8"
        )
        # Secure the file
        os.chmod(self.path, 0o600)
    
    def add(self, provider: DNSProvider) -> None:
        self.providers[provider.name] = provider
    
    def remove(self, name: str) -> bool:
        if name in self.providers:
            del self.providers[name]
            return True
        return False
    
    def get(self, name: str) -> DNSProvider | None:
        return self.providers.get(name)
    
    def list_all(self) -> list[DNSProvider]:
        return list(self.providers.values())


def normalize_provider(name: str) -> str:
    """Normalize provider name to canonical form."""
    return PROVIDER_ALIASES.get(name.lower(), name.lower())


# ─────────────────────────────────────────────────────────────────────────────
# Cloudflare API
# ─────────────────────────────────────────────────────────────────────────────

def cloudflare_test(token: str, zone: str = "") -> tuple[bool, str]:
    """Test Cloudflare API token."""
    try:
        import urllib.request
        import urllib.error
        
        # Test token by verifying it
        req = urllib.request.Request(
            "https://api.cloudflare.com/client/v4/user/tokens/verify",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
        )
        
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            if not data.get("success"):
                return False, "token verification failed"
        
        # Test zone access if specified
        if zone:
            req = urllib.request.Request(
                f"https://api.cloudflare.com/client/v4/zones?name={zone}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                }
            )
            
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                if not data.get("result"):
                    return False, f"zone '{zone}' not found or not accessible"
        
        return True, "token valid"
    
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        return False, str(e)


def cloudflare_create_test_record(token: str, zone: str) -> tuple[bool, str]:
    """Create and cleanup a test TXT record."""
    try:
        import urllib.request
        import urllib.error
        import time
        
        # Get zone ID
        req = urllib.request.Request(
            f"https://api.cloudflare.com/client/v4/zones?name={zone}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
        )
        
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            if not data.get("result"):
                return False, f"zone '{zone}' not found"
            zone_id = data["result"][0]["id"]
        
        # Create test record
        test_name = f"_gvtools-test.{zone}"
        test_value = f"test-{int(time.time())}"
        
        create_data = json.dumps({
            "type": "TXT",
            "name": test_name,
            "content": test_value,
            "ttl": 60,
        }).encode()
        
        req = urllib.request.Request(
            f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records",
            data=create_data,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST"
        )
        
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            if not data.get("success"):
                return False, "failed to create test record"
            record_id = data["result"]["id"]
        
        # Cleanup
        req = urllib.request.Request(
            f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{record_id}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="DELETE"
        )
        
        with urllib.request.urlopen(req, timeout=10) as resp:
            pass
        
        return True, "DNS-01 permissions verified"
    
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        return False, str(e)


# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

def cmd_add(args: argparse.Namespace) -> None:
    """Add a DNS provider."""
    manager = DNSProviderManager()
    
    provider_type = normalize_provider(args.provider)
    if provider_type not in SUPPORTED_PROVIDERS:
        Output.warn(f"provider '{provider_type}' is not officially supported but will be stored")
    
    name = args.name or provider_type
    
    # Get token
    token = ""
    if args.token:
        if args.token.startswith("env:"):
            # Read from environment variable
            env_var = args.token[4:]
            token = os.environ.get(env_var, "")
            if not token:
                die(f"environment variable {env_var} not set")
        elif args.token.startswith("file:"):
            # Read from file
            file_path = Path(args.token[5:]).expanduser()
            if not file_path.exists():
                die(f"token file not found: {file_path}")
            token = file_path.read_text().strip()
        elif args.token == "prompt":
            # Prompt for token
            token = getpass.getpass("API Token: ")
        else:
            token = args.token
    else:
        # Default to prompt
        token = getpass.getpass("API Token: ")
    
    if not token:
        die("token is required")
    
    existing = manager.get(name)
    if existing and not getattr(args, "yes", False):
        if not confirm(f"Provider '{name}' exists. Update?"):
            die("cancelled")
    
    provider = DNSProvider(
        name=name,
        provider_type=provider_type,
        token=token,
        account_id=args.account_id or "",
        default_zone=args.default_zone or "",
    )
    
    manager.add(provider)
    manager.save()
    
    if Output.json_mode:
        Output.json_output({"status": "ok", "provider": provider.to_dict()})
    else:
        if existing:
            Output.success(f"Updated provider: {c(name, Colors.CYAN)}")
        else:
            Output.success(f"Added provider: {c(name, Colors.CYAN)}")


def cmd_list(args: argparse.Namespace) -> None:
    """List configured providers."""
    manager = DNSProviderManager()
    providers = manager.list_all()
    
    if Output.json_mode:
        Output.json_output({"providers": [p.to_dict() for p in providers]})
        return
    
    if not providers:
        Output.info("No DNS providers configured. Add one with: dp add cloudflare")
        return
    
    Output.header(f"DNS Providers ({len(providers)})")
    
    headers = ["Name", "Type", "Zone", "Account"]
    rows = []
    for p in sorted(providers, key=lambda x: x.name):
        rows.append([
            c(p.name, Colors.CYAN),
            p.provider_type,
            p.default_zone or "-",
            p.account_id[:12] + "..." if len(p.account_id) > 15 else (p.account_id or "-"),
        ])
    
    Output.table(headers, rows)


def cmd_show(args: argparse.Namespace) -> None:
    """Show provider details."""
    manager = DNSProviderManager()
    
    name = args.provider
    provider = manager.get(name)
    if not provider:
        die(f"provider not found: {name}")
    
    redact = not getattr(args, "unsafe", False)
    
    if Output.json_mode:
        Output.json_output(provider.to_dict(redact=redact))
        return
    
    Output.header(f"Provider: {provider.name}")
    
    data = provider.to_dict(redact=redact)
    for key, value in data.items():
        if value and key != "name":
            Output.keyvalue(key, str(value) if not isinstance(value, dict) else json.dumps(value))


def cmd_test(args: argparse.Namespace) -> None:
    """Test provider credentials."""
    manager = DNSProviderManager()
    
    name = args.provider
    provider = manager.get(name)
    if not provider:
        die(f"provider not found: {name}")
    
    zone = args.zone or provider.default_zone
    
    Output.info(f"Testing {c(provider.name, Colors.CYAN)} ({provider.provider_type})...")
    
    if provider.provider_type == "cloudflare":
        # Basic token test
        ok, msg = cloudflare_test(provider.token, zone)
        if not ok:
            if Output.json_mode:
                Output.json_output({"success": False, "error": msg})
            else:
                Output.error(f"Token test failed: {msg}")
            sys.exit(1)
        
        Output.success("Token valid")
        
        # DNS-01 permissions test
        if zone:
            Output.step(f"Testing DNS-01 permissions on {zone}...")
            ok, msg = cloudflare_create_test_record(provider.token, zone)
            if ok:
                Output.success(msg)
            else:
                Output.warn(f"DNS-01 test failed: {msg}")
        
        if Output.json_mode:
            Output.json_output({"success": True, "provider": name, "zone": zone})
    else:
        Output.warn(f"Testing for {provider.provider_type} not implemented yet")
        if Output.json_mode:
            Output.json_output({"success": False, "error": "not implemented"})


def cmd_del(args: argparse.Namespace) -> None:
    """Delete a provider."""
    manager = DNSProviderManager()
    
    name = args.provider
    if not manager.get(name):
        die(f"provider not found: {name}")
    
    if not getattr(args, "yes", False):
        if not confirm(f"Delete provider '{name}'?"):
            die("cancelled")
    
    manager.remove(name)
    manager.save()
    
    if Output.json_mode:
        Output.json_output({"status": "ok", "deleted": name})
    else:
        Output.success(f"Deleted provider: {c(name, Colors.CYAN)}")


def cmd_export(args: argparse.Namespace) -> None:
    """Export providers to file."""
    manager = DNSProviderManager()
    providers = manager.list_all()
    
    # Always redact on export unless --unsafe
    redact = not getattr(args, "unsafe", False)
    
    data = {
        "providers": {p.name: p.to_dict(redact=redact) for p in providers}
    }
    
    output = json.dumps(data, indent=2)
    
    if args.output:
        Path(args.output).write_text(output + "\n")
        Output.success(f"Exported to {args.output}")
    else:
        print(output)


def cmd_import(args: argparse.Namespace) -> None:
    """Import providers from file."""
    manager = DNSProviderManager()
    
    path = Path(args.file)
    if not path.exists():
        die(f"file not found: {path}")
    
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        die(f"invalid JSON: {e}")
    
    imported = 0
    for name, prov_data in data.get("providers", {}).items():
        prov_data["name"] = name
        # Skip if token is redacted
        if prov_data.get("token") == "***":
            Output.warn(f"Skipping {name}: token is redacted")
            continue
        provider = DNSProvider.from_dict(prov_data)
        manager.add(provider)
        imported += 1
    
    manager.save()
    
    if Output.json_mode:
        Output.json_output({"status": "ok", "imported": imported})
    else:
        Output.success(f"Imported {imported} providers")


# ─────────────────────────────────────────────────────────────────────────────
# Parser Setup
# ─────────────────────────────────────────────────────────────────────────────

def setup_add_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("provider", help="provider type (cloudflare, route53, etc.)")
    parser.add_argument("--name", "-n", help="name for this provider config (default: provider type)")
    parser.add_argument("--token", "-t", help="API token (env:VAR, file:path, prompt, or value)")
    parser.add_argument("--account-id", help="account ID if required")
    parser.add_argument("--default-zone", help="default zone for operations")
    add_common_args(parser)


def setup_list_parser(parser: argparse.ArgumentParser) -> None:
    add_common_args(parser)


def setup_show_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("provider", help="provider name")
    parser.add_argument("--unsafe", action="store_true", help="show unredacted secrets (dangerous)")
    add_common_args(parser)


def setup_test_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("provider", help="provider name")
    parser.add_argument("--zone", "-z", help="zone to test (overrides default)")
    add_common_args(parser)


def setup_del_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("provider", help="provider name")
    add_common_args(parser)


def setup_export_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", "-f", choices=["json"], default="json", help="output format")
    parser.add_argument("--output", "-o", help="output file")
    parser.add_argument("--unsafe", action="store_true", help="include secrets (dangerous)")
    add_common_args(parser)


def setup_import_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("file", help="file to import")
    add_common_args(parser)


cmd_add.setup_parser = setup_add_parser  # type: ignore
cmd_list.setup_parser = setup_list_parser  # type: ignore
cmd_show.setup_parser = setup_show_parser  # type: ignore
cmd_test.setup_parser = setup_test_parser  # type: ignore
cmd_del.setup_parser = setup_del_parser  # type: ignore
cmd_export.setup_parser = setup_export_parser  # type: ignore
cmd_import.setup_parser = setup_import_parser  # type: ignore


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    Output.set_tool("gvdnsprovider", "DNS provider credential store")
    
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(f"gvdnsprovider {__version__}")
        sys.exit(0)
    
    invoked_as = Path(sys.argv[0]).name
    
    parser = argparse.ArgumentParser(
        prog=invoked_as,
        description="DNS provider credential and configuration store",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  dp add cloudflare --token env:CF_API_TOKEN --default-zone example.com
  dp add cloudflare --token prompt
  dp list
  dp show cloudflare
  dp test cloudflare --zone example.com
  dp del cloudflare
        """,
    )
    parser.add_argument("--version", "-V", action="version", version=f"gvdnsprovider {__version__}")
    
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    
    add_p = subparsers.add_parser("add", help="add a DNS provider")
    setup_add_parser(add_p)
    
    list_p = subparsers.add_parser("list", help="list configured providers")
    setup_list_parser(list_p)
    
    show_p = subparsers.add_parser("show", help="show provider details")
    setup_show_parser(show_p)
    
    test_p = subparsers.add_parser("test", help="test provider credentials")
    setup_test_parser(test_p)
    
    del_p = subparsers.add_parser("del", help="delete a provider")
    setup_del_parser(del_p)
    
    export_p = subparsers.add_parser("export", help="export providers")
    setup_export_parser(export_p)
    
    import_p = subparsers.add_parser("import", help="import providers")
    setup_import_parser(import_p)
    
    args = parser.parse_args()
    apply_common_args(args)
    
    if not args.command:
        cmd_list(args)
        return
    
    commands = {
        "add": cmd_add,
        "list": cmd_list,
        "show": cmd_show,
        "test": cmd_test,
        "del": cmd_del,
        "export": cmd_export,
        "import": cmd_import,
    }
    
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
