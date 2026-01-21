# GVTools

[![CI](https://github.com/Gvolexe/GvolTools/actions/workflows/ci.yml/badge.svg)](https://github.com/Gvolexe/GvolTools/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Version](https://img.shields.io/github/v/release/Gvolexe/GvolTools?color=green&label=version)](https://github.com/Gvolexe/GvolTools/releases)

**Infrastructure Management Toolkit** — A comprehensive collection of CLI utilities for managing SSH-based server infrastructure.

**Author:** Gvol ([gvol@nexusystems.org](mailto:gvol@nexusystems.org))

## Features

- 🔐 **Security** — Host hardening, SSH auditing, secrets management
- 🔑 **SSH** — Key management, connection profiles, known_hosts control
- 📊 **Monitoring** — Log analysis, DNS checks, network diagnostics
- ⚙️ **Automation** — Host inventory, target selection, JSON output
- 🎨 **Beautiful CLI** — Colorful, consistent output across all tools

---

## Quick Start

```bash
# Clone the repository
git clone https://github.com/Gvolexe/GvolTools.git
cd GvolTools

# Install all tools
./installgvtools.sh install-all --deps

# See what's available
gv

# Get help for a specific tool
gv help fleet
```

### PATH Setup

Tools are installed to `~/.local/bin`. Add to your PATH if needed:

```bash
# Add to ~/.bashrc or ~/.zshrc
export PATH="$HOME/.local/bin:$PATH"
```

## Available Tools (20)

### Inventory & Profiles

| Tool           | Aliases  | Description                  |
| -------------- | -------- | ---------------------------- |
| **gv**         | gvtools  | Help and command dispatcher  |
| **gvfleet**    | fleet, f | Host inventory management    |
| **gvsshprofile** | sp     | SSH connection profiles      |

### Security & Hardening

| Tool              | Aliases     | Description                   |
| ----------------- | ----------- | ----------------------------- |
| **gvhostbootstrap** | hb        | Initial host bootstrap        |
| **gvsshaudit**    | sa          | SSH configuration auditing    |
| **gvknownhostsctl** | kh        | known_hosts management        |
| **gvsecretsync**  | sec, secrets | Encrypted secrets sync       |
| **gvfirewallctl** | fw          | Firewall baselines            |
| **gvsudoauth**    | su          | Sudo authentication config    |
| **gvpermcheck**   | pc, perm    | Permission auditing           |
| **gvolkeymanager** | keyup, keyconf | SSH key management        |

### Certificates & Updates

| Tool          | Aliases    | Description                  |
| ------------- | ---------- | ---------------------------- |
| **gvcertctl** | cert, cc   | TLS certs (ACME/Cloudflare)  |
| **gvupdates** | upd        | Security update management   |

### Monitoring & Diagnostics

| Tool           | Aliases     | Description               |
| -------------- | ----------- | ------------------------- |
| **gvlogtriage** | lt         | Log analysis              |
| **gvdnscheck** | dns, dc     | DNS validation            |
| **gvnetdiag**  | nd          | Network diagnostics       |
| **gvportsentry** | ps, ports | Port scanning/baselines   |

### Configuration & DevOps

| Tool           | Aliases   | Description           |
| -------------- | --------- | --------------------- |
| **gvdotctl**   | dt, dot   | Dotfile management    |
| **gvgitopsinit** | gi      | GitOps scaffolding    |
| **gvbackupctl** | bk       | Backup with restic    |

## Target Selection

All tools support consistent target selection:

```bash
# Direct target
gvfleet ssh admin@server.example.com

# From inventory
gvfleet ssh --targets "web*"

# By attributes  
gvfleet ssh --env production --role webserver
```

## Common Flags

| Flag             | Description              |
| ---------------- | ------------------------ |
| `--dry-run`      | Preview without applying |
| `--json`         | JSON output for scripts  |
| `--verbose`      | Verbose output           |
| `--yes`          | Skip confirmations       |
| `--strict-hostkey` | Require known hosts    |

## Installer Usage

```bash
./installgvtools.sh <command> [options]

Commands:
  list                    List available tools
  install <tool> [--deps] Install a tool
  install-all [--deps]    Install all tools
  uninstall <tool>        Remove a tool
  status <tool>           Check installation status
```

## Architecture

```
~/.local/bin/              # Tool executables + alias symlinks
~/.local/lib/gvtools/      # Shared library (gvcore.py)
~/.config/gvtools/         # Configuration data
    ├── inventory.json     # Host inventory
    ├── sshprofiles.json   # SSH profiles
    ├── secrets/           # Encrypted secrets
    └── certctl/           # Certificate configs
```

## Documentation

See [docs/](docs/) for detailed documentation on each tool:

- [docs/README.md](docs/README.md) — Documentation index
- [OVERVIEW.md](OVERVIEW.md) — Architecture overview

## Requirements

- **Python 3.10+**
- **paramiko** — SSH connections
- **cryptography** — Secrets encryption (optional)
- **certbot** — Certificate management (optional)
- **restic** — Backups (optional)

## Development

```bash
# Run tests
python3 -m pytest tests/ -v

# Run integration tests
python3 tests/test_integration.py

# Install single tool for testing
./installgvtools.sh install gvfleet
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request

## License

MIT License — see [LICENSE](LICENSE)

---

Made with care by [Gvol](mailto:gvol@nexusystems.org)
