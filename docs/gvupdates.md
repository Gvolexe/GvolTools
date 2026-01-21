# gvupdates - Security Update Management

Manage unattended security updates across your infrastructure.

## Aliases

- `upd`
- `gvu`

## Usage

```bash
upd <command> [options]
```

## Commands

### enable

Enable unattended upgrades.

```bash
upd enable --targets server1
upd enable --env prod
upd enable --targets server1 --reboot-time "02:00"
```

**Options:**

- `--reboot-time`: Automatic reboot time for kernel updates
- `--security-only`: Only security updates (default)

### check

Check for available updates.

```bash
upd check server1
upd check --env prod --json
```

### apply

Apply pending security updates.

```bash
upd apply --targets server1
upd apply --env staging --yes
```

### report

Generate update status report.

```bash
upd report
upd report --env prod --json
```

## Unattended Upgrades Configuration

When enabled, configures:

1. **APT::Periodic::Update-Package-Lists**: "1"
2. **APT::Periodic::Unattended-Upgrade**: "1"
3. **Unattended-Upgrade::Allowed-Origins**: Security updates
4. **Unattended-Upgrade::Remove-Unused-Dependencies**: "true"
5. **Unattended-Upgrade::Automatic-Reboot**: Configurable
6. **Unattended-Upgrade::Automatic-Reboot-Time**: Configurable

## Examples

```bash
# Enable on all production servers with 2 AM reboot
upd enable --env prod --reboot-time "02:00"

# Check what updates are available
upd check --env prod

# Apply updates manually
upd apply --targets server1 --yes

# Generate report
upd report --json > updates.json
```

## Supported Systems

- Debian
- Ubuntu

CentOS/RHEL support via yum-cron planned.
