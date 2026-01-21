# GVTools Overview

**Infrastructure Management Toolkit** - Version 2.0.0

GVTools is a comprehensive collection of command-line utilities for managing SSH-based server infrastructure, developed with a focus on security, automation, and operator experience.

## Philosophy

- **Unix philosophy**: Each tool does one thing well
- **Consistency**: All tools share common flags and target selection
- **Safety**: Dry-run mode, confirmations, and backups by default
- **Automation**: JSON output for scripting, CI/CD integration

## Quick Start

```bash
# Clone the repository
git clone https://github.com/Gvolexe/GvolTools.git
cd GvolTools

# Install all tools
./installgvtools.sh install-all --deps

# View available commands
gv

# Get help for a specific tool
gv help fleet
```

## Tool Categories

### Inventory & Profiles

| Tool         | Aliases  | Purpose                     |
| ------------ | -------- | --------------------------- |
| gv           | gvtools  | Help and command dispatcher |
| gvfleet      | fleet, f | Host inventory management   |
| gvsshprofile | sp       | SSH connection profiles     |

### Security & Hardening

| Tool            | Aliases | Purpose                         |
| --------------- | ------- | ------------------------------- |
| gvhostbootstrap | hb      | Initial host security bootstrap |
| gvsshaudit      | sa      | SSH configuration auditing      |
| gvknownhostsctl | kh      | known_hosts management          |
| gvsecretsync    | sec     | Encrypted secrets distribution  |
| gvfirewallctl   | fw      | Firewall baselines              |
| gvsudoauth      | su      | Sudo authentication config      |
| gvpermcheck     | pc      | Permission auditing             |
| gvolkeymanager  | km      | SSH key management              |

### Certificates & Updates

| Tool      | Aliases | Purpose                           |
| --------- | ------- | --------------------------------- |
| gvcertctl | cert    | TLS certificate management (ACME) |
| gvupdates | upd     | Security update management        |

### Monitoring & Diagnostics

| Tool         | Aliases     | Purpose                          |
| ------------ | ----------- | -------------------------------- |
| gvlogtriage  | lt          | Auth/system log analysis         |
| gvdnscheck   | dns         | DNS validation                   |
| gvnetdiag    | nd          | Network diagnostics              |
| gvportsentry | ports       | Port scanning and baselines      |
| gvhealth     | health, hl  | Host and service health checks   |
| gvmetrics    | metrics, mx | Resource metrics and time series |
| gvtcptest    | tcp, tc     | TCP connectivity testing         |
| gvjournal    | jrnl, j     | Systemd journal log fetching     |

### Configuration & DevOps

| Tool           | Aliases    | Purpose                             |
| -------------- | ---------- | ----------------------------------- |
| gvdotctl       | dt         | Dotfile management                  |
| gvgitopsinit   | gi         | GitOps scaffolding                  |
| gvbackupctl    | bk         | Backup configuration                |
| gvconfigrender | render, rr | Template rendering and deployment   |
| gvnginxctl     | ngx, nx    | Nginx config testing and management |

### Fleet Operations (New in 2.0)

| Tool          | Aliases     | Purpose                                   |
| ------------- | ----------- | ----------------------------------------- |
| gvdeploy      | dep, run    | Execute commands/scripts across hosts     |
| gvsync        | sync, sx    | Rsync wrapper with SSH profile awareness  |
| gvsystemdctl  | sd, svc     | Fleet-safe systemd service management     |
| gvrebootctl   | reboot, rb  | Safe reboot coordination and validation   |
| gvpolicy      | pol, pl     | Policy rules for fleet security baselines |
| gvdnsprovider | dnsprov, dp | DNS provider credential management        |

## Architecture

```
~/.local/bin/               # Tool executables + symlinks
~/.local/lib/gvtools/       # Shared library (gvcore)
~/.config/gvtools/          # Configuration data
    ├── inventory.json      # Host inventory
    ├── sshprofiles.json    # SSH profiles
    ├── secrets/            # Encrypted secrets
    ├── certs/              # Certificate configs
    └── ...
```

## Target Selection

All tools support consistent target selection:

```bash
# Direct target
tool command user@host

# From inventory
tool command --targets server1,server2

# By attributes
tool command --env production
tool command --role webserver
tool command --tag critical
tool command --owner gvol
```

## Common Flags

| Flag               | Description              |
| ------------------ | ------------------------ |
| `--dry-run`        | Preview without applying |
| `--json`           | JSON output              |
| `--verbose`        | Verbose output           |
| `--yes`            | Skip confirmations       |
| `--timeout`        | Operation timeout        |
| `--strict-hostkey` | Require known hosts      |

## Shared Library (gvcore)

All tools import from gvcore for:

- Output formatting (colors, tables, JSON)
- Host/inventory management
- SSH connection handling
- Target selection parsing
- CLI argument patterns

## Development

```bash
# Run tests
python3 tests/test_integration.py
python3 tests/test_tools.py

# Install single tool for testing
./installgvtools.sh install gvfleet
```

## Requirements

- Python 3.10+
- paramiko (SSH connections)
- Optional: cryptography (secrets), certbot (certs), restic (backups)

## Author

**Gvol** (gvol@nexusystems.org)  
GitHub: https://github.com/Gvolexe/GvolTools

## License

MIT License
