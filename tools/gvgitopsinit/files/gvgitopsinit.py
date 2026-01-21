#!/usr/bin/env python3
"""
gvgitopsinit - GitOps repository scaffolding

Create GitOps-ready infrastructure repositories.

Aliases: gi, gitops, gvgi

Author: Gvol (gvol@nexusystems.org)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".local" / "lib" / "gvtools"))

from gvcore import (
    Output, Colors, c, die,
    add_common_args, apply_common_args,
)

__version__ = "1.2.1"


GITOPS_STRUCTURE = {
    "inventory/": {},
    "inventory/hosts.json": """{
  "hosts": {},
  "groups": {}
}
""",
    "roles/": {},
    "roles/common/": {},
    "roles/common/tasks.sh": """#!/bin/bash
# Common role tasks

echo "Applying common role..."

# Install base packages
apt-get update -qq
apt-get install -y -qq vim curl wget git htop

# Configure timezone
timedatectl set-timezone UTC

# Enable NTP
systemctl enable systemd-timesyncd
systemctl start systemd-timesyncd

echo "Common role complete"
""",
    "envs/": {},
    "envs/production/": {},
    "envs/production/vars.json": """{
  "env": "production",
  "domain": "example.com",
  "dns_provider": "cloudflare"
}
""",
    "envs/staging/": {},
    "envs/staging/vars.json": """{
  "env": "staging",
  "domain": "staging.example.com"
}
""",
    "secrets/": {},
    "secrets/.gitignore": """*
!.gitignore
""",
    "scripts/": {},
    "scripts/deploy.sh": """#!/bin/bash
# Deployment script
set -e

ENV="${1:-production}"
ROLE="${2:-common}"

echo "=== GitOps Deploy ==="
echo "Environment: $ENV"
echo "Role: $ROLE"

# Load environment vars
if [ -f "envs/$ENV/vars.json" ]; then
    echo "Loading $ENV vars..."
fi

# Run role
if [ -f "roles/$ROLE/tasks.sh" ]; then
    echo "Running role: $ROLE"
    bash "roles/$ROLE/tasks.sh"
fi

echo "Deploy complete"
""",
    ".github/": {},
    ".github/workflows/": {},
    ".github/workflows/validate.yml": """name: Validate

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Validate JSON
        run: |
          for f in $(find . -name "*.json" -type f); do
            echo "Checking $f..."
            python3 -m json.tool "$f" > /dev/null
          done
          
      - name: Shellcheck
        run: |
          for f in $(find . -name "*.sh" -type f); do
            echo "Checking $f..."
            shellcheck "$f" || true
          done
""",
    "README.md": """# Infrastructure GitOps Repository

This repository manages infrastructure configuration using GitOps principles.

## Structure

```
.
├── inventory/          # Host inventory
├── roles/              # Reusable role definitions
├── envs/               # Environment-specific configs
│   ├── production/
│   └── staging/
├── secrets/            # Encrypted secrets (gitignored)
└── scripts/            # Deployment scripts
```

## Usage

### Deploy to environment

```bash
./scripts/deploy.sh production common
```

### Add a new host

Edit `inventory/hosts.json` and add your host.

### Add a new role

1. Create `roles/<role-name>/`
2. Add `tasks.sh` with your configuration

## GVTools Integration

This repo is compatible with GVTools. Use:

```bash
gvfleet import --file inventory/hosts.json
gvhb init --targets <host>
```
""",
    ".gitignore": """# Secrets
secrets/*
!secrets/.gitignore

# Local files
*.local
*.bak
.env
.envrc

# Editors
*.swp
*.swo
*~
.idea/
.vscode/

# OS
.DS_Store
Thumbs.db
""",
}


def create_structure(base_path: Path, structure: dict) -> None:
    """Create directory structure."""
    for path, content in structure.items():
        full_path = base_path / path
        
        if path.endswith("/"):
            full_path.mkdir(parents=True, exist_ok=True)
            Output.step(f"mkdir: {path}")
        else:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)
            if path.endswith(".sh"):
                full_path.chmod(0o755)
            Output.step(f"create: {path}")


def cmd_new(args: argparse.Namespace) -> None:
    """Create new GitOps repository."""
    name = args.name
    path = Path(args.path or ".") / name
    
    if path.exists():
        if not args.yes:
            die(f"path already exists: {path}")
    
    Output.header(f"New GitOps Repo: {name}")
    
    if args.dry_run:
        Output.info("Would create structure:")
        for p in sorted(GITOPS_STRUCTURE.keys()):
            Output.step(p)
        return
    
    create_structure(path, GITOPS_STRUCTURE)
    
    if args.git:
        Output.step("Initializing git...")
        subprocess.run(["git", "init"], cwd=path, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial GitOps structure"], cwd=path, capture_output=True)
    
    Output.success(f"Created {name}")
    Output.info(f"cd {path}")


def cmd_add_role(args: argparse.Namespace) -> None:
    """Add a new role."""
    role_name = args.name
    
    roles_dir = Path("roles")
    if not roles_dir.exists():
        die("not in a GitOps repository (roles/ not found)")
    
    role_path = roles_dir / role_name
    
    if role_path.exists():
        die(f"role already exists: {role_name}")
    
    Output.header(f"Add Role: {role_name}")
    
    if args.dry_run:
        Output.info(f"Would create roles/{role_name}/tasks.sh")
        return
    
    role_path.mkdir(parents=True)
    
    tasks_content = f"""#!/bin/bash
# Role: {role_name}

echo "Applying {role_name} role..."

# Add your tasks here

echo "{role_name} role complete"
"""
    
    (role_path / "tasks.sh").write_text(tasks_content)
    (role_path / "tasks.sh").chmod(0o755)
    
    vars_content = f"""{{
  "role": "{role_name}"
}}
"""
    (role_path / "vars.json").write_text(vars_content)
    
    Output.success(f"Created roles/{role_name}/")


def cmd_add_env(args: argparse.Namespace) -> None:
    """Add a new environment."""
    env_name = args.name
    
    envs_dir = Path("envs")
    if not envs_dir.exists():
        die("not in a GitOps repository (envs/ not found)")
    
    env_path = envs_dir / env_name
    
    if env_path.exists():
        die(f"environment already exists: {env_name}")
    
    Output.header(f"Add Environment: {env_name}")
    
    if args.dry_run:
        Output.info(f"Would create envs/{env_name}/vars.json")
        return
    
    env_path.mkdir(parents=True)
    
    vars_content = f"""{{
  "env": "{env_name}",
  "domain": "{env_name}.example.com"
}}
"""
    (env_path / "vars.json").write_text(vars_content)
    
    Output.success(f"Created envs/{env_name}/")


def cmd_validate(args: argparse.Namespace) -> None:
    """Validate repository structure."""
    Output.header("Validate GitOps Repo")
    
    errors = []
    warnings = []
    
    required = ["inventory", "roles", "envs"]
    for d in required:
        if not Path(d).exists():
            errors.append(f"Missing: {d}/")
    
    for json_file in Path(".").rglob("*.json"):
        try:
            json.loads(json_file.read_text())
        except json.JSONDecodeError as e:
            errors.append(f"Invalid JSON: {json_file} - {e}")
    
    for sh_file in Path(".").rglob("*.sh"):
        if not os.access(sh_file, os.X_OK):
            warnings.append(f"Not executable: {sh_file}")
    
    if Output.json_mode:
        Output.json_output({"errors": errors, "warnings": warnings, "valid": len(errors) == 0})
        return
    
    if errors:
        Output.error(f"Errors ({len(errors)}):")
        for e in errors:
            print(f"  {c('✗', Colors.RED)} {e}")
    
    if warnings:
        Output.warn(f"Warnings ({len(warnings)}):")
        for w in warnings:
            print(f"  {c('!', Colors.YELLOW)} {w}")
    
    if not errors:
        Output.success("Repository is valid")
    else:
        die(f"{len(errors)} validation errors")


def main() -> None:
    Output.set_tool("gvgitopsinit", "GitOps scaffolding")
    
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(f"gvgitopsinit {__version__}")
        sys.exit(0)
    
    parser = argparse.ArgumentParser(
        prog=Path(sys.argv[0]).name,
        description="GitOps repository scaffolding",
        epilog="""
Examples:
  gi new my-infra
  gi new my-infra --path ~/projects --git
  gi add-role webserver
  gi add-env staging
  gi validate
        """,
    )
    parser.add_argument("--version", "-V", action="version", version=f"gvgitopsinit {__version__}")
    
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    
    new_p = subparsers.add_parser("new", help="create new repo")
    new_p.add_argument("name", help="repository name")
    new_p.add_argument("--path", "-p", help="parent path")
    new_p.add_argument("--git", "-g", action="store_true", help="initialize git")
    add_common_args(new_p)
    
    role_p = subparsers.add_parser("add-role", help="add role")
    role_p.add_argument("name", help="role name")
    add_common_args(role_p)
    
    env_p = subparsers.add_parser("add-env", help="add environment")
    env_p.add_argument("name", help="environment name")
    add_common_args(env_p)
    
    validate_p = subparsers.add_parser("validate", help="validate repo")
    add_common_args(validate_p)
    
    args = parser.parse_args()
    apply_common_args(args)
    
    commands = {
        "new": cmd_new,
        "add-role": cmd_add_role,
        "add-env": cmd_add_env,
        "validate": cmd_validate,
    }
    
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
