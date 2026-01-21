#!/usr/bin/env python3
"""
gvdotctl - Dotfile management

Distribute and manage dotfiles across hosts.

Aliases: dt, dot, gvdt

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
    __version__,
    Output, Colors, c, die,
    Target, Inventory, GVTOOLS_CONFIG,
    add_common_args, add_target_args, get_selector_from_args, apply_common_args,
    ssh_connect, ssh_exec, get_ssh_credentials,
)


DOTFILES_DIR = GVTOOLS_CONFIG / "dotfiles"
HISTORY_FILE = DOTFILES_DIR / "history.json"


DOTFILE_TEMPLATES = {
    "ssh": {
        "~/.ssh/config": """
# GVTools SSH Config
Host *
    ServerAliveInterval 60
    ServerAliveCountMax 3
    AddKeysToAgent yes
    IdentitiesOnly yes
""",
    },
    "zsh": {
        "~/.zshrc": """
# GVTools Zsh Config
export HISTSIZE=10000
export SAVEHIST=10000
export HISTFILE=~/.zsh_history

setopt SHARE_HISTORY
setopt HIST_IGNORE_DUPS
setopt HIST_IGNORE_SPACE

alias ll='ls -la'
alias la='ls -A'
alias l='ls -CF'
alias ..='cd ..'
alias ...='cd ../..'

# Prompt
PROMPT='%F{green}%n@%m%f:%F{blue}%~%f$ '
""",
    },
    "git": {
        "~/.gitconfig": """
# GVTools Git Config
[core]
    editor = vim
    autocrlf = input
[alias]
    st = status
    co = checkout
    br = branch
    ci = commit
    lg = log --oneline --graph --all
[pull]
    rebase = false
[init]
    defaultBranch = main
""",
    },
    "vim": {
        "~/.vimrc": """
\" GVTools Vim Config
set nocompatible
syntax on
set number
set relativenumber
set expandtab
set tabstop=4
set shiftwidth=4
set autoindent
set smartindent
set hlsearch
set incsearch
set ignorecase
set smartcase
set ruler
set laststatus=2
set wildmenu
set wildmode=longest:full,full
set backspace=indent,eol,start
""",
    },
    "tmux": {
        "~/.tmux.conf": """
# GVTools Tmux Config
set -g default-terminal "screen-256color"
set -g history-limit 10000
set -g base-index 1
setw -g pane-base-index 1
set -g renumber-windows on
set -g mouse on

# Prefix
unbind C-b
set -g prefix C-a
bind C-a send-prefix

# Split panes
bind | split-window -h
bind - split-window -v
unbind '"'
unbind %

# Reload config
bind r source-file ~/.tmux.conf \\; display "Reloaded!"
""",
    },
}


def load_history() -> dict:
    if not HISTORY_FILE.exists():
        return {"deployments": []}
    return json.loads(HISTORY_FILE.read_text())


def save_history(data: dict) -> None:
    DOTFILES_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(data, indent=2))


def cmd_apply(args: argparse.Namespace) -> None:
    """Apply dotfile set."""
    dotfile_type = args.type
    
    if dotfile_type not in DOTFILE_TEMPLATES:
        die(f"unknown dotfile type: {dotfile_type} (available: {', '.join(DOTFILE_TEMPLATES.keys())})")
    
    inventory = Inventory()
    selector = get_selector_from_args(args)
    hosts = inventory.select(selector) if not selector.is_empty() else []
    
    if not hosts:
        die("no targets specified")
    
    Output.header(f"Apply: {dotfile_type}")
    
    templates = DOTFILE_TEMPLATES[dotfile_type]
    history = load_history()
    password, key_path, sudo_password = get_ssh_credentials(args)
    
    for host in hosts:
        Output.info(f"Deploying to {host.name}...")
        target = Target.from_host(host, default_user="root")
        
        if args.dry_run:
            Output.step(f"Would apply {dotfile_type} to {host.name}")
            continue
        
        try:
            client = ssh_connect(target, strict_hostkey=args.strict_hostkey, password=password, key_path=key_path)
            
            for dest_path, content in templates.items():
                dest = dest_path.replace("~", "$HOME")
                
                script = f"""
mkdir -p $(dirname {dest})
if [ -f {dest} ]; then
    cp {dest} {dest}.bak.$(date +%Y%m%d%H%M%S)
fi
cat > {dest} << 'GVEOF'
{content}
GVEOF
echo "OK: {dest}"
"""
                exit_code, stdout, stderr = ssh_exec(client, script)
                if exit_code == 0:
                    Output.step(stdout.strip())
                else:
                    Output.error(f"Failed: {stderr}")
            
            client.close()
            Output.success(f"Applied to {host.name}")
            
            history["deployments"].append({
                "host": host.name,
                "type": dotfile_type,
                "date": datetime.now().isoformat(),
            })
            
        except Exception as e:
            Output.error(f"Failed on {host.name}: {e}")
    
    save_history(history)


def cmd_status(args: argparse.Namespace) -> None:
    """Show dotfile status."""
    target_str = args.target
    
    target = Target.parse(target_str)
    if not target.user:
        target.user = "root"
    
    Output.header(f"Dotfile Status: {target.host}")
    
    script = """
echo "=== DOTFILES ==="
for f in ~/.zshrc ~/.bashrc ~/.gitconfig ~/.vimrc ~/.tmux.conf ~/.ssh/config; do
    if [ -f "$f" ]; then
        echo "$(stat -c '%Y %s' $f 2>/dev/null || stat -f '%m %z' $f 2>/dev/null) $f"
    fi
done | while read ts size file; do
    date -d "@$ts" "+%Y-%m-%d $file ($size bytes)" 2>/dev/null || echo "$file exists"
done
"""
    
    try:
        password, key_path, sudo_password = get_ssh_credentials(args)
        client = ssh_connect(target, strict_hostkey=args.strict_hostkey, password=password, key_path=key_path)
        exit_code, stdout, stderr = ssh_exec(client, script)
        client.close()
        print(stdout)
    except Exception as e:
        Output.error(str(e))


def cmd_rollback(args: argparse.Namespace) -> None:
    """Rollback to backup."""
    target_str = args.target
    dotfile_path = args.file
    
    target = Target.parse(target_str)
    if not target.user:
        target.user = "root"
    
    Output.header(f"Rollback: {dotfile_path}")
    
    dest = dotfile_path.replace("~", "$HOME")
    
    script = f"""
latest_backup=$(ls -t {dest}.bak.* 2>/dev/null | head -1)
if [ -n "$latest_backup" ]; then
    cp "$latest_backup" {dest}
    echo "Restored from: $latest_backup"
else
    echo "No backup found for {dest}"
    exit 1
fi
"""
    
    if args.dry_run:
        Output.info(f"Would rollback {dotfile_path}")
        return
    
    try:
        password, key_path, sudo_password = get_ssh_credentials(args)
        client = ssh_connect(target, strict_hostkey=args.strict_hostkey, password=password, key_path=key_path)
        exit_code, stdout, stderr = ssh_exec(client, script)
        client.close()
        
        if exit_code == 0:
            Output.success(stdout.strip())
        else:
            Output.error(f"Rollback failed: {stderr}")
    except Exception as e:
        Output.error(str(e))


def cmd_list(args: argparse.Namespace) -> None:
    """List available dotfile sets."""
    Output.header("Available Dotfile Sets")
    
    if Output.json_mode:
        Output.json_output({"types": list(DOTFILE_TEMPLATES.keys())})
        return
    
    for dtype, files in DOTFILE_TEMPLATES.items():
        Output.step(f"{c(dtype, Colors.CYAN)}:")
        for path in files.keys():
            print(f"    {path}")


def main() -> None:
    Output.set_tool("gvdotctl", "Dotfile manager")
    
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(f"gvdotctl {__version__}")
        sys.exit(0)
    
    parser = argparse.ArgumentParser(
        prog=Path(sys.argv[0]).name,
        description="Dotfile management and distribution",
        epilog="""
Examples:
  dt list
  dt apply ssh --targets server1
  dt apply zsh --env prod
  dt status server1
  dt rollback server1 --file ~/.zshrc
        """,
    )
    parser.add_argument("--version", "-V", action="version", version=f"gvdotctl {__version__}")
    
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    
    apply_p = subparsers.add_parser("apply", help="apply dotfiles")
    apply_p.add_argument("type", choices=list(DOTFILE_TEMPLATES.keys()), help="dotfile type")
    add_target_args(apply_p)
    add_common_args(apply_p)
    
    status_p = subparsers.add_parser("status", help="check status")
    status_p.add_argument("target", help="target host")
    add_common_args(status_p)
    
    rollback_p = subparsers.add_parser("rollback", help="rollback to backup")
    rollback_p.add_argument("target", help="target host")
    rollback_p.add_argument("--file", "-f", required=True, help="file to rollback")
    add_common_args(rollback_p)
    
    list_p = subparsers.add_parser("list", help="list dotfile sets")
    add_common_args(list_p)
    
    args = parser.parse_args()
    apply_common_args(args)
    
    commands = {
        "apply": cmd_apply,
        "status": cmd_status,
        "rollback": cmd_rollback,
        "list": cmd_list,
    }
    
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
