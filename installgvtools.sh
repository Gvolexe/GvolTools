#!/usr/bin/env bash
#
# installgvtools.sh - JSON-driven installer for gvoltools
#
# Author: Gvol (gvol@nexusystems.org)
#
set -euo pipefail

readonly VERSION="1.1.6"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly ROOT_DIR
TOOLS_DIR="$ROOT_DIR/tools"
readonly TOOLS_DIR

# ─────────────────────────────────────────────────────────────────────────────
# Colors
# ─────────────────────────────────────────────────────────────────────────────

setup_colors() {
    if [[ -t 1 ]] && [[ -z "${NO_COLOR:-}" ]]; then
        readonly RED=$'\033[31m'
        readonly GREEN=$'\033[32m'
        readonly YELLOW=$'\033[33m'
        readonly BLUE=$'\033[34m'
        readonly CYAN=$'\033[36m'
        readonly BOLD=$'\033[1m'
        readonly DIM=$'\033[2m'
        readonly RESET=$'\033[0m'
    else
        readonly RED='' GREEN='' YELLOW='' BLUE='' CYAN='' BOLD='' DIM='' RESET=''
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# Output Helpers
# ─────────────────────────────────────────────────────────────────────────────

msg_error() { echo "${RED}${BOLD}✖ error:${RESET} $1" >&2; }
msg_success() { echo "${GREEN}${BOLD}✔${RESET} $1"; }
msg_warn() { echo "${YELLOW}${BOLD}⚠ warning:${RESET} $1" >&2; }
msg_info() { echo "${BLUE}${BOLD}→${RESET} $1"; }
msg_step() { echo "  ${DIM}•${RESET} $1"; }

die() { msg_error "$1"; exit 1; }

header() {
    local text="$1"
    local width=${#text}
    [[ $width -lt 30 ]] && width=30
    width=$((width + 4))
    
    echo
    echo "${CYAN}┌$(printf '─%.0s' $(seq 1 $((width - 2))))┐${RESET}"
    local padding=$(( (width - ${#text} - 2) / 2 ))
    local rpadding=$(( width - ${#text} - 2 - padding ))
    echo "${CYAN}│${RESET}$(printf ' %.0s' $(seq 1 $padding))${BOLD}${text}${RESET}$(printf ' %.0s' $(seq 1 $rpadding))${CYAN}│${RESET}"
    echo "${CYAN}└$(printf '─%.0s' $(seq 1 $((width - 2))))┘${RESET}"
}

divider() {
    echo "${DIM}────────────────────────────────────────${RESET}"
}

banner() {
    echo
    echo "${CYAN}╭─────────────────────────────────────────╮${RESET}"
    echo "${CYAN}│${RESET}${BOLD}          gvoltools installer            ${RESET}${CYAN}│${RESET}"
    echo "${CYAN}│${RESET}${DIM}   A collection of useful utilities      ${RESET}${CYAN}│${RESET}"
    echo "${CYAN}╰─────────────────────────────────────────╯${RESET}"
}

# ─────────────────────────────────────────────────────────────────────────────
# Usage
# ─────────────────────────────────────────────────────────────────────────────

usage() {
    banner
    cat <<EOF

${BOLD}Usage:${RESET}
  ${CYAN}./installgvtools.sh${RESET} <command> [options]

${BOLD}Commands:${RESET}
  ${GREEN}list${RESET}                    List available tools
  ${GREEN}install${RESET} <tool> [--deps] Install a tool (auto-installs requirements)
  ${GREEN}install-all${RESET} [--deps]    Install all tools
  ${GREEN}uninstall${RESET} <tool>        Remove an installed tool
  ${GREEN}status${RESET} <tool>           Check installation status

${BOLD}Options:${RESET}
  ${YELLOW}--deps${RESET}    Install system dependencies (with install)
  ${YELLOW}--help${RESET}    Show this help message
  ${YELLOW}--version${RESET} Show version

${BOLD}Examples:${RESET}
  ./installgvtools.sh list
  ./installgvtools.sh install gvfleet --deps
  ./installgvtools.sh install-all --deps
  ./installgvtools.sh status gvfleet
  ./installgvtools.sh uninstall gvfleet

${DIM}Author: Gvol (gvol@nexusystems.org)${RESET}
EOF
}

# ─────────────────────────────────────────────────────────────────────────────
# Platform Detection
# ─────────────────────────────────────────────────────────────────────────────

detect_platform() {
    if [[ -r /etc/os-release ]]; then
        # Read os-release without sourcing (avoids conflicts with our VERSION)
        local id like
        id=$(grep -E '^ID=' /etc/os-release | cut -d= -f2 | tr -d '"' | tr '[:upper:]' '[:lower:]')
        like=$(grep -E '^ID_LIKE=' /etc/os-release 2>/dev/null | cut -d= -f2 | tr -d '"' | tr '[:upper:]' '[:lower:]' || echo "")

        if [[ "$id" == "arch" || "$id" == "cachyos" || "$like" == *"arch"* ]]; then
            echo "arch"
            return
        fi
        if [[ "$id" == "debian" || "$id" == "ubuntu" || "$like" == *"debian"* ]]; then
            echo "debian"
            return
        fi
    fi
    echo "unknown"
}

# ─────────────────────────────────────────────────────────────────────────────
# Tool Discovery
# ─────────────────────────────────────────────────────────────────────────────

list_tools() {
    header "Available Tools"
    
    local found=0
    for setup_file in "$TOOLS_DIR"/*/setup.json; do
        [[ -f "$setup_file" ]] || continue
        
        local tool_dir
        tool_dir="$(dirname "$setup_file")"
        local tool_name
        tool_name="$(basename "$tool_dir")"
        
        local description version
        description=$(python3 -c "import json; d=json.load(open('$setup_file')); print(d.get('description', 'No description'))" 2>/dev/null || echo "No description")
        version=$(python3 -c "import json; d=json.load(open('$setup_file')); print(d.get('version', '?'))" 2>/dev/null || echo "?")
        
        echo "  ${CYAN}${BOLD}$tool_name${RESET} ${DIM}v$version${RESET}"
        echo "    ${DIM}$description${RESET}"
        echo
        found=1
    done
    
    if [[ $found -eq 0 ]]; then
        msg_info "No tools found"
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# Python Helper
# ─────────────────────────────────────────────────────────────────────────────

py() {
    python3 - "$@"
}

# ─────────────────────────────────────────────────────────────────────────────
# Dependency Installation
# ─────────────────────────────────────────────────────────────────────────────

install_deps() {
    local tool_dir="$1"
    local platform="$2"
    
    local deps
    deps="$(py "$tool_dir/setup.json" "$platform" <<'PY'
import json, sys
setup_path = sys.argv[1]
platform = sys.argv[2]
data = json.load(open(setup_path, "r", encoding="utf-8"))
deps = data.get("deps", {}).get(platform, [])
print("\n".join(deps))
PY
)"
    
    if [[ -z "$deps" ]]; then
        msg_info "No dependencies for platform '$platform'"
        return
    fi
    
    header "Installing Dependencies"
    echo "$deps" | while read -r dep; do
        [[ -n "$dep" ]] && msg_step "$dep"
    done
    echo
    
    if [[ "$platform" == "arch" ]]; then
        # shellcheck disable=SC2086
        sudo pacman -S --needed --noconfirm $deps
    elif [[ "$platform" == "debian" ]]; then
        sudo apt-get update -qq
        # shellcheck disable=SC2086
        sudo apt-get install -y $deps
    else
        msg_warn "Unknown platform '$platform' - install manually:"
        echo "  ${deps// /\n  }"
    fi
    
    msg_success "Dependencies installed"
}

# ─────────────────────────────────────────────────────────────────────────────
# Install
# ─────────────────────────────────────────────────────────────────────────────

do_install() {
    local tool="$1"
    local with_deps="${2:-false}"
    
    local tool_dir="$TOOLS_DIR/$tool"
    [[ -d "$tool_dir" ]] || die "Tool not found: $tool"
    [[ -f "$tool_dir/setup.json" ]] || die "Missing setup.json in $tool"
    
    local platform
    platform="$(detect_platform)"
    
    # Check and install required dependencies (other tools)
    local requires
    requires=$(python3 -c "import json; d=json.load(open('$tool_dir/setup.json')); print(' '.join(d.get('requires', [])))" 2>/dev/null || echo "")
    
    if [[ -n "$requires" ]]; then
        for req in $requires; do
            local req_dir="$TOOLS_DIR/$req"
            if [[ -d "$req_dir" ]] && [[ -f "$req_dir/setup.json" ]]; then
                msg_info "Installing required dependency: $req"
                do_install "$req" "$with_deps"
            fi
        done
    fi
    
    header "Installing $tool"
    
    if [[ "$with_deps" == "true" ]]; then
        install_deps "$tool_dir" "$platform"
    fi
    
    # Run install and colorize output
    while IFS='|' read -r action detail; do
        case "$action" in
            copy) msg_success "Installed: ${CYAN}$detail${RESET}" ;;
            link) msg_success "Linked: ${CYAN}$detail${RESET}" ;;
            mkdir) msg_success "Created: ${CYAN}$detail${RESET}" ;;
            skip) msg_warn "Skipped: $detail" ;;
            error) msg_error "$detail"; exit 1 ;;
        esac
    done < <(py "$tool_dir" <<'PY'
import json, os, shutil, sys
from pathlib import Path

tool_dir = Path(sys.argv[1])
setup = json.loads((tool_dir / "setup.json").read_text(encoding="utf-8"))
targets = setup.get("install", {}).get("targets", [])

if not targets:
    print("error|no install targets in setup.json")
    sys.exit(1)

def expand(p: str) -> Path:
    return Path(os.path.expanduser(p)).resolve()

def expand_no_resolve(p: str) -> Path:
    return Path(os.path.expanduser(p))

for t in targets:
    ttype = t.get("type")
    
    if ttype == "copy":
        src = tool_dir / t["src"]
        dst = expand(t["dst"])
        dst.parent.mkdir(parents=True, exist_ok=True)
        
        if dst.is_symlink():
            dst.unlink()
        
        shutil.copy2(src, dst)
        
        chmod = t.get("chmod")
        if chmod:
            os.chmod(dst, int(chmod, 8))
        
        print(f"copy|{dst}")
    
    elif ttype == "symlink":
        link = expand_no_resolve(t["link"])
        target = expand(t["target"])
        
        if str(link) == str(target):
            print(f"skip|{link} (self-symlink)")
            continue
        
        link.parent.mkdir(parents=True, exist_ok=True)
        
        if link.exists() or link.is_symlink():
            if link.is_dir():
                print(f"error|{link} is a directory")
                sys.exit(1)
            link.unlink()
        
        link.symlink_to(target)
        print(f"link|{link} -> {target}")
    
    elif ttype == "mkdir":
        path = expand(t["path"])
        path.mkdir(parents=True, exist_ok=True)
        chmod = t.get("chmod")
        if chmod:
            os.chmod(path, int(chmod, 8))
        print(f"mkdir|{path}")
    
    else:
        print(f"error|unknown target type: {ttype}")
        sys.exit(1)
PY
)
    
    echo
    msg_success "Installation complete"
    
    # Check if ~/.local/bin is in PATH
    if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
        echo
        msg_warn "\$HOME/.local/bin is not in your PATH"
        echo "  Add this line to your shell config (~/.bashrc, ~/.zshrc, etc.):"
        echo
        echo "    ${CYAN}export PATH=\"\$HOME/.local/bin:\$PATH\"${RESET}"
        echo
        echo "  Then restart your shell or run: ${CYAN}source ~/.bashrc${RESET}"
    else
        msg_info "Run ${CYAN}hash -r${RESET} to refresh your shell"
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# Install All
# ─────────────────────────────────────────────────────────────────────────────

do_install_all() {
    local with_deps="${1:-false}"
    
    header "Installing All GVTools"
    
    # Track installed to avoid duplicates from requires
    declare -A installed
    
    # Install order: gvcore first (no requires), then gv, then others
    local install_order=("gvcore" "gv")
    
    for setup_file in "$TOOLS_DIR"/*/setup.json; do
        [[ -f "$setup_file" ]] || continue
        local tool_name
        tool_name="$(basename "$(dirname "$setup_file")")"
        
        # Skip already in order
        [[ "$tool_name" == "gvcore" || "$tool_name" == "gv" ]] && continue
        install_order+=("$tool_name")
    done
    
    for tool in "${install_order[@]}"; do
        if [[ -z "${installed[$tool]:-}" ]]; then
            local tool_dir="$TOOLS_DIR/$tool"
            if [[ -d "$tool_dir" ]] && [[ -f "$tool_dir/setup.json" ]]; then
                echo
                msg_info "Installing: $tool"
                do_install "$tool" "$with_deps"
                installed[$tool]=1
            fi
        fi
    done
    
    echo
    header "Installation Complete"
    msg_success "All tools installed!"
    msg_info "Run ${CYAN}gv${RESET} to see available commands"
}

# ─────────────────────────────────────────────────────────────────────────────
# Uninstall
# ─────────────────────────────────────────────────────────────────────────────

do_uninstall() {
    local tool="$1"
    local tool_dir="$TOOLS_DIR/$tool"
    
    [[ -f "$tool_dir/setup.json" ]] || die "Missing setup.json in $tool"
    
    header "Uninstalling $tool"
    
    # Run once and colorize output
    while IFS='|' read -r action detail; do
        case "$action" in
            remove) msg_success "Removed: ${CYAN}$detail${RESET}" ;;
            rmdir) msg_success "Removed dir: ${CYAN}$detail${RESET}" ;;
            none) msg_info "$detail" ;;
        esac
    done < <(py "$tool_dir" <<'PY'
import json, os, sys
from pathlib import Path

tool_dir = Path(sys.argv[1])
setup = json.loads((tool_dir / "setup.json").read_text(encoding="utf-8"))
targets = setup.get("install", {}).get("targets", [])

def expand(p: str) -> Path:
    return Path(os.path.expanduser(p)).resolve()

def expand_no_resolve(p: str) -> Path:
    return Path(os.path.expanduser(p))

removed = 0
for t in targets:
    if t.get("type") == "copy":
        dst = expand(t["dst"])
        if dst.exists() or dst.is_symlink():
            dst.unlink()
            print(f"remove|{dst}")
            removed += 1
    elif t.get("type") == "symlink":
        link = expand_no_resolve(t["link"])
        if link.exists() or link.is_symlink():
            link.unlink()
            print(f"remove|{link}")
            removed += 1
    elif t.get("type") == "mkdir":
        path = expand(t["path"])
        # Don't remove directories as they may contain user data

if removed == 0:
    print("none|Nothing to remove")
PY
)
    
    echo
    msg_success "Uninstall complete"
}

# ─────────────────────────────────────────────────────────────────────────────
# Status
# ─────────────────────────────────────────────────────────────────────────────

do_status() {
    local tool="$1"
    local tool_dir="$TOOLS_DIR/$tool"
    
    [[ -f "$tool_dir/setup.json" ]] || die "Missing setup.json in $tool"
    
    header "Status: $tool"
    
    local version description
    version=$(python3 -c "import json; d=json.load(open('$tool_dir/setup.json')); print(d.get('version', '?'))" 2>/dev/null || echo "?")
    description=$(python3 -c "import json; d=json.load(open('$tool_dir/setup.json')); print(d.get('description', ''))" 2>/dev/null || echo "")
    
    echo "  ${DIM}Version:${RESET}     $version"
    echo "  ${DIM}Description:${RESET} $description"
    echo
    
    while IFS='|' read -r status type path; do
        case "$status" in
            ok)
                echo "  ${GREEN}✔${RESET} $path"
                ;;
            missing)
                echo "  ${RED}✖${RESET} $path ${DIM}(not found)${RESET}"
                ;;
            result)
                echo
                if [[ "$type" == "installed" ]]; then
                    msg_success "Tool is installed"
                else
                    msg_warn "Tool is not fully installed"
                fi
                ;;
        esac
    done < <(py "$tool_dir" <<'PY'
import json, os, sys
from pathlib import Path

tool_dir = Path(sys.argv[1])
setup = json.loads((tool_dir / "setup.json").read_text(encoding="utf-8"))
targets = setup.get("install", {}).get("targets", [])

def expand(p: str) -> Path:
    return Path(os.path.expanduser(p)).resolve()

def expand_no_resolve(p: str) -> Path:
    return Path(os.path.expanduser(p))

all_installed = True
for t in targets:
    if t.get("type") == "copy":
        dst = expand(t["dst"])
        installed = dst.exists() and not dst.is_symlink()
        status = "ok" if installed else "missing"
        print(f"{status}|copy|{dst}")
        if not installed:
            all_installed = False
    elif t.get("type") == "symlink":
        link = expand_no_resolve(t["link"])
        installed = link.is_symlink()
        status = "ok" if installed else "missing"
        print(f"{status}|link|{link}")
        if not installed:
            all_installed = False
    elif t.get("type") == "mkdir":
        path = expand(t["path"])
        installed = path.exists() and path.is_dir()
        status = "ok" if installed else "missing"
        print(f"{status}|mkdir|{path}")
        if not installed:
            all_installed = False

if all_installed:
    print("result|installed|")
else:
    print("result|not installed|")
PY
)
}

# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

main() {
    setup_colors
    
    local cmd="${1:-}"
    
    case "$cmd" in
        list)
            list_tools
            ;;
        install)
            local tool="${2:-}"
            [[ -n "$tool" ]] || { usage; die "Missing tool name"; }
            
            local with_deps="false"
            for arg in "${@:3}"; do
                [[ "$arg" == "--deps" ]] && with_deps="true"
            done
            
            do_install "$tool" "$with_deps"
            ;;
        install-all)
            local with_deps="false"
            for arg in "${@:2}"; do
                [[ "$arg" == "--deps" ]] && with_deps="true"
            done
            
            do_install_all "$with_deps"
            ;;
        uninstall)
            local tool="${2:-}"
            [[ -n "$tool" ]] || { usage; die "Missing tool name"; }
            do_uninstall "$tool"
            ;;
        status)
            local tool="${2:-}"
            [[ -n "$tool" ]] || { usage; die "Missing tool name"; }
            do_status "$tool"
            ;;
        --help|-h|help)
            usage
            ;;
        --version)
            echo "installgvtools v${VERSION}"
            ;;
        "")
            usage
            ;;
        *)
            usage
            die "Unknown command: $cmd"
            ;;
    esac
}

main "$@"
