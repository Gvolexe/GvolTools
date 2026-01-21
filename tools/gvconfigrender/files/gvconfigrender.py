#!/usr/bin/env python3
"""
gvconfigrender - Template rendering and deployment for fleet configurations

Render configuration templates with host/environment variables and deploy
to fleet hosts.

Aliases: render, rr

Author: Gvol (gvol@nexusystems.org)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".local" / "lib" / "gvtools"))

from gvcore import (
    __version__,
    Output, Colors, c, die,
    Host, Inventory, Target,
    GVTOOLS_CONFIG,
    add_common_args, add_target_args, get_selector_from_args, apply_common_args,
    ssh_connect, ssh_exec, get_ssh_credentials,
)


# ─────────────────────────────────────────────────────────────────────────────
# Template Configuration
# ─────────────────────────────────────────────────────────────────────────────

TEMPLATES_PATH = GVTOOLS_CONFIG / "templates"
VARS_PATH = GVTOOLS_CONFIG / "template_vars.json"


class TemplateVars:
    """Manage template variables."""
    
    def __init__(self, path: Path = VARS_PATH):
        self.path = path
        self.vars: dict = {}
        self._load()
    
    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            self.vars = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as e:
            Output.warn(f"could not load variables: {e}")
    
    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.vars, indent=2) + "\n", encoding="utf-8")
    
    def get_for_host(self, host: Host) -> dict:
        """Get variables for a specific host."""
        result = {}
        
        # Global variables
        result.update(self.vars.get("global", {}))
        
        # Environment variables
        env = host.tags.get("env", "")
        if env and env in self.vars.get("environments", {}):
            result.update(self.vars["environments"][env])
        
        # Role variables
        if host.role and host.role in self.vars.get("roles", {}):
            result.update(self.vars["roles"][host.role])
        
        # Group variables
        if host.group and host.group in self.vars.get("groups", {}):
            result.update(self.vars["groups"][host.group])
        
        # Host-specific variables
        if host.name in self.vars.get("hosts", {}):
            result.update(self.vars["hosts"][host.name])
        
        # Add host metadata
        result["hostname"] = host.hostname
        result["host_name"] = host.name
        result["host_ip"] = host.ip
        result["host_role"] = host.role or ""
        result["host_group"] = host.group or ""
        result["host_user"] = host.user or ""
        
        return result


class Jinja2LikeTemplate:
    """Simple Jinja2-like template engine (no dependencies)."""
    
    # Patterns for template syntax
    VAR_PATTERN = re.compile(r'\{\{\s*(\w+)\s*\}\}')
    COMMENT_PATTERN = re.compile(r'\{#.*?#\}', re.DOTALL)
    IF_PATTERN = re.compile(r'\{% if (\w+) %\}(.*?)\{% endif %\}', re.DOTALL)
    FOR_PATTERN = re.compile(r'\{% for (\w+) in (\w+) %\}(.*?)\{% endfor %\}', re.DOTALL)
    
    def __init__(self, template: str):
        self.template = template
    
    def render(self, **context: dict) -> str:
        result = self.template
        
        # Remove comments
        result = self.COMMENT_PATTERN.sub('', result)
        
        # Handle if blocks
        def replace_if(match):
            var = match.group(1)
            content = match.group(2)
            if context.get(var):
                return content
            return ""
        
        result = self.IF_PATTERN.sub(replace_if, result)
        
        # Handle for loops
        def replace_for(match):
            item_var = match.group(1)
            list_var = match.group(2)
            content = match.group(3)
            items = context.get(list_var, [])
            output = []
            for item in items:
                item_content = content
                item_content = re.sub(
                    r'\{\{\s*' + item_var + r'\s*\}\}',
                    str(item),
                    item_content
                )
                output.append(item_content)
            return ''.join(output)
        
        result = self.FOR_PATTERN.sub(replace_for, result)
        
        # Replace variables
        def replace_var(match):
            var = match.group(1)
            return str(context.get(var, f'{{{{ {var} }}}}'))
        
        result = self.VAR_PATTERN.sub(replace_var, result)
        
        return result


# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

def cmd_render(args: argparse.Namespace) -> None:
    """Render a template for a host."""
    template_file = Path(args.template)
    
    if not template_file.exists():
        # Try templates directory
        template_file = TEMPLATES_PATH / args.template
        if not template_file.exists():
            die(f"template not found: {args.template}")
    
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if not hosts:
        die("no hosts matched selector")
    
    if len(hosts) > 1 and not getattr(args, "output_dir", None):
        die("multiple hosts require --output-dir")
    
    template_content = template_file.read_text(encoding="utf-8")
    template = Jinja2LikeTemplate(template_content)
    
    vars_manager = TemplateVars()
    
    # Extra variables from command line
    extra_vars = {}
    if getattr(args, "var", None):
        for v in args.var:
            if "=" in v:
                k, val = v.split("=", 1)
                extra_vars[k] = val
    
    results = []
    
    for host in hosts:
        host_vars = vars_manager.get_for_host(host)
        host_vars.update(extra_vars)
        
        try:
            rendered = template.render(**host_vars)
            
            if getattr(args, "output_dir", None):
                output_file = Path(args.output_dir) / f"{host.name}_{template_file.name}"
                output_file.parent.mkdir(parents=True, exist_ok=True)
                output_file.write_text(rendered, encoding="utf-8")
                results.append({"host": host.name, "output": str(output_file), "success": True})
                
                if not Output.json_mode:
                    Output.success(f"{host.name} → {output_file}")
            
            elif getattr(args, "output", None):
                output_file = Path(args.output)
                output_file.parent.mkdir(parents=True, exist_ok=True)
                output_file.write_text(rendered, encoding="utf-8")
                results.append({"host": host.name, "output": str(output_file), "success": True})
                
                if not Output.json_mode:
                    Output.success(f"Rendered to {output_file}")
            
            else:
                # Print to stdout
                print(rendered)
                results.append({"host": host.name, "success": True})
        
        except Exception as e:
            results.append({"host": host.name, "success": False, "error": str(e)})
            if not Output.json_mode:
                Output.error(f"{host.name}: {e}")
    
    if Output.json_mode:
        Output.json_output({"results": results})


def cmd_deploy(args: argparse.Namespace) -> None:
    """Render and deploy template to hosts."""
    template_file = Path(args.template)
    
    if not template_file.exists():
        template_file = TEMPLATES_PATH / args.template
        if not template_file.exists():
            die(f"template not found: {args.template}")
    
    remote_path = args.dest
    
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector)
    
    if not hosts:
        die("no hosts matched selector")
    
    template_content = template_file.read_text(encoding="utf-8")
    template = Jinja2LikeTemplate(template_content)
    
    vars_manager = TemplateVars()
    password, key_path, sudo_pass = get_ssh_credentials(args)
    
    dry_run = getattr(args, "dry_run", False)
    
    results = []
    
    for host in hosts:
        target = Target.from_host(host, default_user=host.user or "root")
        host_vars = vars_manager.get_for_host(host)
        
        try:
            rendered = template.render(**host_vars)
            
            if dry_run:
                if not Output.json_mode:
                    Output.info(f"Would deploy to {c(host.name, Colors.CYAN)}:{remote_path}")
                results.append({"host": host.name, "success": True, "dry_run": True})
                continue
            
            client = ssh_connect(target, password=password, key_path=key_path)
            
            # Create temp file and copy content
            import tempfile
            with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".conf") as f:
                f.write(rendered)
                local_tmp = f.name
            
            # Use SFTP to upload
            sftp = client.open_sftp()
            sftp.put(local_tmp, remote_path)
            sftp.close()
            
            # Clean up local temp
            os.unlink(local_tmp)
            
            # Set permissions if specified
            if getattr(args, "mode", None):
                ssh_exec(client, f"chmod {args.mode} {remote_path}", sudo=True, password=sudo_pass or password)
            
            if getattr(args, "owner", None):
                ssh_exec(client, f"chown {args.owner} {remote_path}", sudo=True, password=sudo_pass or password)
            
            # Validate if specified
            if getattr(args, "validate", None):
                validate_cmd = args.validate.replace("%s", remote_path)
                code, out, err = ssh_exec(client, validate_cmd, sudo=True, password=sudo_pass or password)
                if code != 0:
                    results.append({
                        "host": host.name,
                        "success": False,
                        "error": f"validation failed: {err or out}",
                    })
                    if not Output.json_mode:
                        Output.error(f"{host.name}: validation failed")
                    client.close()
                    continue
            
            client.close()
            
            results.append({"host": host.name, "success": True})
            if not Output.json_mode:
                Output.success(f"{host.name}: deployed to {remote_path}")
        
        except Exception as e:
            results.append({"host": host.name, "success": False, "error": str(e)})
            if not Output.json_mode:
                Output.error(f"{host.name}: {e}")
    
    if Output.json_mode:
        Output.json_output({"results": results})


def cmd_vars_set(args: argparse.Namespace) -> None:
    """Set a variable."""
    vars_manager = TemplateVars()
    
    scope = args.scope  # global, environment:<name>, role:<name>, group:<name>, host:<name>
    key = args.key
    value = args.value
    
    if scope == "global":
        if "global" not in vars_manager.vars:
            vars_manager.vars["global"] = {}
        vars_manager.vars["global"][key] = value
    elif scope.startswith("environment:"):
        env = scope.split(":", 1)[1]
        if "environments" not in vars_manager.vars:
            vars_manager.vars["environments"] = {}
        if env not in vars_manager.vars["environments"]:
            vars_manager.vars["environments"][env] = {}
        vars_manager.vars["environments"][env][key] = value
    elif scope.startswith("role:"):
        role = scope.split(":", 1)[1]
        if "roles" not in vars_manager.vars:
            vars_manager.vars["roles"] = {}
        if role not in vars_manager.vars["roles"]:
            vars_manager.vars["roles"][role] = {}
        vars_manager.vars["roles"][role][key] = value
    elif scope.startswith("group:"):
        group = scope.split(":", 1)[1]
        if "groups" not in vars_manager.vars:
            vars_manager.vars["groups"] = {}
        if group not in vars_manager.vars["groups"]:
            vars_manager.vars["groups"][group] = {}
        vars_manager.vars["groups"][group][key] = value
    elif scope.startswith("host:"):
        host = scope.split(":", 1)[1]
        if "hosts" not in vars_manager.vars:
            vars_manager.vars["hosts"] = {}
        if host not in vars_manager.vars["hosts"]:
            vars_manager.vars["hosts"][host] = {}
        vars_manager.vars["hosts"][host][key] = value
    else:
        die(f"invalid scope: {scope}")
    
    vars_manager.save()
    
    if Output.json_mode:
        Output.json_output({"status": "ok", "scope": scope, "key": key, "value": value})
    else:
        Output.success(f"Set {scope}/{key} = {value}")


def cmd_vars_list(args: argparse.Namespace) -> None:
    """List variables."""
    vars_manager = TemplateVars()
    
    if Output.json_mode:
        Output.json_output({"vars": vars_manager.vars})
        return
    
    Output.header("Template Variables")
    
    if not vars_manager.vars:
        Output.info("No variables defined")
        return
    
    def print_scope(name: str, data: dict) -> None:
        Output.info(c(name, Colors.CYAN))
        for k, v in sorted(data.items()):
            Output.step(f"{k} = {v}")
    
    if "global" in vars_manager.vars:
        print_scope("global", vars_manager.vars["global"])
    
    for scope_type in ["environments", "roles", "groups", "hosts"]:
        if scope_type in vars_manager.vars:
            for name, data in sorted(vars_manager.vars[scope_type].items()):
                print_scope(f"{scope_type[:-1]}:{name}", data)


def cmd_template_save(args: argparse.Namespace) -> None:
    """Save a template to the templates directory."""
    source = Path(args.source)
    name = args.name or source.name
    
    if not source.exists():
        die(f"source file not found: {source}")
    
    TEMPLATES_PATH.mkdir(parents=True, exist_ok=True)
    dest = TEMPLATES_PATH / name
    
    dest.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    
    if Output.json_mode:
        Output.json_output({"status": "ok", "template": name, "path": str(dest)})
    else:
        Output.success(f"Saved template: {name}")


def cmd_template_list(args: argparse.Namespace) -> None:
    """List saved templates."""
    if not TEMPLATES_PATH.exists():
        if Output.json_mode:
            Output.json_output({"templates": []})
        else:
            Output.info("No templates saved")
        return
    
    templates = list(TEMPLATES_PATH.iterdir())
    
    if Output.json_mode:
        Output.json_output({
            "templates": [
                {"name": t.name, "size": t.stat().st_size}
                for t in templates if t.is_file()
            ]
        })
        return
    
    Output.header(f"Templates ({len(templates)})")
    for t in sorted(templates):
        if t.is_file():
            Output.step(f"{t.name} ({t.stat().st_size} bytes)")


# ─────────────────────────────────────────────────────────────────────────────
# Parser Setup
# ─────────────────────────────────────────────────────────────────────────────

def setup_render_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("template", help="template file path")
    parser.add_argument("-o", "--output", help="output file")
    parser.add_argument("--output-dir", help="output directory (for multiple hosts)")
    parser.add_argument("--var", action="append", help="extra variable (key=value)")
    add_target_args(parser)
    add_common_args(parser)


def setup_deploy_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("template", help="template file path")
    parser.add_argument("dest", help="remote destination path")
    parser.add_argument("--mode", help="file mode (e.g., 644)")
    parser.add_argument("--owner", help="file owner (e.g., root:root)")
    parser.add_argument("--validate", help="validation command (%s = file path)")
    parser.add_argument("--dry-run", "-n", action="store_true", help="dry run")
    add_target_args(parser)
    add_common_args(parser)


def setup_vars_set_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("scope", help="scope (global, environment:name, role:name, group:name, host:name)")
    parser.add_argument("key", help="variable name")
    parser.add_argument("value", help="variable value")
    add_common_args(parser)


def setup_vars_list_parser(parser: argparse.ArgumentParser) -> None:
    add_common_args(parser)


def setup_template_save_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("source", help="source file path")
    parser.add_argument("--name", help="template name (default: source filename)")
    add_common_args(parser)


def setup_template_list_parser(parser: argparse.ArgumentParser) -> None:
    add_common_args(parser)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    Output.set_tool("gvconfigrender", "Template rendering and deployment")
    
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(f"gvconfigrender {__version__}")
        sys.exit(0)
    
    invoked_as = Path(sys.argv[0]).name
    
    parser = argparse.ArgumentParser(
        prog=invoked_as,
        description="Template rendering and deployment for fleet configurations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  rr render nginx.conf.j2 --host web1
  rr render nginx.conf.j2 --role web --output-dir ./rendered/
  rr deploy nginx.conf.j2 /etc/nginx/nginx.conf --role web --validate "nginx -t"
  rr vars set global domain example.com
  rr vars set role:web upstream_port 8080
  rr template save ./nginx.conf.j2 --name nginx
        """,
    )
    parser.add_argument("--version", "-V", action="version", version=f"gvconfigrender {__version__}")
    
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    
    render_p = subparsers.add_parser("render", help="render template")
    setup_render_parser(render_p)
    
    deploy_p = subparsers.add_parser("deploy", help="render and deploy template")
    setup_deploy_parser(deploy_p)
    
    # Vars subcommands
    vars_p = subparsers.add_parser("vars", help="manage variables")
    vars_sub = vars_p.add_subparsers(dest="vars_command", metavar="subcommand")
    
    vars_set_p = vars_sub.add_parser("set", help="set a variable")
    setup_vars_set_parser(vars_set_p)
    
    vars_list_p = vars_sub.add_parser("list", help="list variables")
    setup_vars_list_parser(vars_list_p)
    
    # Template subcommands
    tpl_p = subparsers.add_parser("template", help="manage templates")
    tpl_sub = tpl_p.add_subparsers(dest="template_command", metavar="subcommand")
    
    tpl_save_p = tpl_sub.add_parser("save", help="save template")
    setup_template_save_parser(tpl_save_p)
    
    tpl_list_p = tpl_sub.add_parser("list", help="list templates")
    setup_template_list_parser(tpl_list_p)
    
    args = parser.parse_args()
    apply_common_args(args)
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    if args.command == "render":
        cmd_render(args)
    elif args.command == "deploy":
        cmd_deploy(args)
    elif args.command == "vars":
        if not hasattr(args, "vars_command") or not args.vars_command:
            vars_p.print_help()
            sys.exit(0)
        if args.vars_command == "set":
            cmd_vars_set(args)
        elif args.vars_command == "list":
            cmd_vars_list(args)
    elif args.command == "template":
        if not hasattr(args, "template_command") or not args.template_command:
            tpl_p.print_help()
            sys.exit(0)
        if args.template_command == "save":
            cmd_template_save(args)
        elif args.template_command == "list":
            cmd_template_list(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
