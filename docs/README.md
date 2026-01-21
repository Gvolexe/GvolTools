# GVTools Documentation

GVTools is a comprehensive infrastructure management toolkit for SSH-based server administration.

## Quick Start

```bash
# Install all tools
./installgvtools.sh install-all --deps

# View available commands
gv

# Get help for a specific tool
gv help fleet
```

## Tools Overview

### Core Tools

| Tool                                | Aliases         | Description                 |
| ----------------------------------- | --------------- | --------------------------- |
| [gv](gv.md)                         | gvtools, gvhelp | Help and command dispatcher |
| [gvfleet](gvfleet.md)               | fleet, f        | Host inventory management   |
| [gvsshprofile](gvsshprofile.md)     | sp              | SSH connection profiles     |
| [gvolkeymanager](gvolkeymanager.md) | km              | SSH key management          |

### Security & Hardening

| Tool                                  | Aliases | Description                    |
| ------------------------------------- | ------- | ------------------------------ |
| [gvhostbootstrap](gvhostbootstrap.md) | hb      | Host security bootstrap        |
| [gvsshaudit](gvsshaudit.md)           | sa      | SSH configuration auditing     |
| [gvknownhostsctl](gvknownhostsctl.md) | kh      | SSH known_hosts management     |
| [gvsecretsync](gvsecretsync.md)       | sec     | Encrypted secrets distribution |
| [gvcertctl](gvcertctl.md)             | cert    | TLS certificate management     |
| [gvfirewallctl](gvfirewallctl.md)     | fw      | Firewall baseline management   |
| [gvsudoauth](gvsudoauth.md)           | su      | Sudo authentication config     |
| [gvpermcheck](gvpermcheck.md)         | pc      | Permission auditing            |
| [gvpolicy](gvpolicy.md)               | pol     | Security policy enforcement    |

### Fleet Operations (New in 2.0)

| Tool                                | Aliases     | Description                    |
| ----------------------------------- | ----------- | ------------------------------ |
| [gvhealth](gvhealth.md)             | health, hl  | Host and service health checks |
| [gvmetrics](gvmetrics.md)           | metrics, mx | Resource metrics collection    |
| [gvtcptest](gvtcptest.md)           | tcp         | TCP connectivity testing       |
| [gvjournal](gvjournal.md)           | jrnl        | Journald log querying          |
| [gvdeploy](gvdeploy.md)             | dep         | Command/script execution       |
| [gvsync](gvsync.md)                 | sx          | File synchronization (rsync)   |
| [gvsystemdctl](gvsystemdctl.md)     | svc         | Systemd service management     |
| [gvrebootctl](gvrebootctl.md)       | rb          | Reboot coordination            |
| [gvdnsprovider](gvdnsprovider.md)   | dnsprov, dp | DNS provider configuration     |
| [gvconfigrender](gvconfigrender.md) | render, rr  | Template rendering/deployment  |
| [gvnginxctl](gvnginxctl.md)         | ngx, nx     | Nginx configuration management |

### System Administration

| Tool                            | Aliases | Description                 |
| ------------------------------- | ------- | --------------------------- |
| [gvupdates](gvupdates.md)       | upd     | Security update management  |
| [gvlogtriage](gvlogtriage.md)   | lt      | Auth/system log analysis    |
| [gvbackupctl](gvbackupctl.md)   | bk      | Backup configuration        |
| [gvdnscheck](gvdnscheck.md)     | dns     | DNS validation              |
| [gvnetdiag](gvnetdiag.md)       | nd      | Network diagnostics         |
| [gvportsentry](gvportsentry.md) | ports   | Port scanning and baselines |
| [gvdotctl](gvdotctl.md)         | dt      | Dotfile management          |
| [gvgitopsinit](gvgitopsinit.md) | gi      | GitOps scaffolding          |

## Target Selection

All tools support consistent target selection:

```bash
# Direct target
tool command user@host

# From inventory by name
tool command --targets server1,server2

# By environment
tool command --env production

# By role
tool command --role webserver

# By tag
tool command --tag critical

# By owner
tool command --owner gvol

# Bulk operations on all matching hosts
tool command --env prod --role web
```

## Common Flags

All tools support these common flags:

| Flag               | Description                      |
| ------------------ | -------------------------------- |
| `--dry-run`        | Preview changes without applying |
| `--json`           | Output in JSON format            |
| `--verbose` / `-v` | Enable verbose output            |
| `--timeout`        | Set operation timeout (seconds)  |
| `--yes` / `-y`     | Skip confirmation prompts        |
| `--strict-hostkey` | Require known host keys          |

## Configuration

Configuration is stored in `~/.config/gvtools/`:

```
~/.config/gvtools/
├── inventory.json      # Host inventory
├── sshprofiles.json    # SSH profiles
├── secrets/            # Encrypted secrets
├── certs/              # Certificate configs
└── ...
```

## License

MIT License - See LICENSE file.

## Author

Gvol (gvol@nexusystems.org)  
GitHub: https://github.com/Gvolexe/GvolTools
