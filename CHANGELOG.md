# Changelog

All notable changes to GVTools will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] - 2026-01-21

### Added

- **gvcore** — Shared library providing common functionality for all tools
  - Terminal colors and output formatting
  - Host inventory management
  - SSH connection handling
  - Target selection system
  - Common CLI patterns

- **gv** — Central help and command dispatcher
  - List all available tools
  - Search tools by keyword
  - Show help for any tool

- **gvfleet** — Host inventory and selection engine
  - Add/remove hosts with metadata (env, roles, tags, owner)
  - Select hosts by various criteria
  - Quick SSH access via resolved profiles
  - Import/export inventory

- **gvsshprofile** — SSH connection profiles
  - Define profiles with domain patterns
  - Generate ~/.ssh/config
  - Test profile resolution
  - Lint for overlaps and issues

- **gvhostbootstrap** — Initial host security bootstrap
  - Create users with sudo access
  - Configure SSH key authentication
  - Disable password auth and root login
  - Apply security hardening

- **gvsshaudit** — SSH configuration auditing
  - Audit local SSH client config
  - Audit remote sshd config
  - Fleet-wide auditing
  - Security recommendations

- **gvknownhostsctl** — known_hosts management
  - Verify host keys
  - Add/remove entries
  - Deduplicate entries
  - Handle hostname renames

- **gvsecretsync** — Encrypted secrets management
  - Fernet encryption for secrets
  - Deploy secrets to remote hosts
  - Key rotation support
  - Status checking

- **gvcertctl** — TLS certificate management
  - ACME/Let's Encrypt integration
  - Cloudflare DNS-01 validation (also accepts "cloudflair")
  - Certificate deployment
  - Renewal tracking

- **gvfirewallctl** — Firewall baseline management
  - Apply UFW/nftables rules
  - Compare against baseline
  - Lock down configurations

- **gvupdates** — Security update management
  - Enable/check automatic updates
  - Apply security patches
  - Generate update reports

- **gvsudoauth** — Sudo authentication configuration
  - Check sudo auth status
  - Enable/disable SSH agent forwarding
  - Configure NOPASSWD access

- **gvlogtriage** — Log analysis
  - SSH authentication logs
  - Sudo usage logs
  - fail2ban ban logs
  - Summary reports

- **gvbackupctl** — Backup management with restic
  - Initialize backup repositories
  - Run backups
  - Verify backup integrity
  - Restore files

- **gvdnscheck** — DNS validation
  - Record lookups
  - Zone checks
  - SSH hostname consistency
  - DNS reports

- **gvnetdiag** — Network diagnostics
  - Local network info
  - Remote connectivity tests
  - Port scanning
  - Traceroute

- **gvportsentry** — Port scanning and baselines
  - Scan open ports
  - Save baselines
  - Compare against baselines
  - Alert on changes

- **gvdotctl** — Dotfile management
  - Apply dotfiles from repository
  - Status checking
  - Rollback support

- **gvgitopsinit** — GitOps scaffolding
  - Create GitOps repository structure
  - Add roles and environments
  - Validate configurations

- **gvpermcheck** — Permission auditing
  - SSH directory permissions
  - Sudoers file checks
  - Custom path auditing

### Changed

- **gvolkeymanager** — Updated to v0.5.0
  - Now integrates with gvcore shared library
  - Consistent coloring with other tools

- **installgvtools.sh** — Enhanced installer
  - Added `install-all` command
  - Added `requires` field for tool dependencies
  - Auto-installs gvcore before dependent tools

### Infrastructure

- Added comprehensive GitHub Actions CI workflow
  - Tests on Python 3.10, 3.11, 3.12, 3.13
  - JSON validation for all setup.json files
  - Ruff linting
  - ShellCheck for bash scripts
  - Full installer testing
  - Integration tests

- Added release workflow
  - Version consistency validation
  - Automated changelog generation
  - GitHub release creation

## [0.3.0] - 2025-01-XX

### Added

- Initial gvolkeymanager release
  - `keyup` command for SSH key upload
  - `keyconf` command for key registry
  - Secure server setup options
  - Preferences system

---

[0.5.0]: https://github.com/Gvolexe/GvolTools/compare/v0.3.0...v0.5.0
[0.3.0]: https://github.com/Gvolexe/GvolTools/releases/tag/v0.3.0
