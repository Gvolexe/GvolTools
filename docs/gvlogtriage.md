# gvlogtriage - Auth/System Log Analysis

Pull and summarize auth/system logs around SSH and sudo incidents.

## Aliases

- `lt`
- `logtriage`
- `gvlt`

## Usage

```bash
lt <command> [options]
```

## Commands

### ssh

Show SSH authentication logs.

```bash
lt ssh server1
lt ssh server1 --since 2h
lt ssh server1 --since "2024-01-01 00:00"
```

**Options:**

- `--since`: Time range (default: 2h)

### sudo

Show sudo activity logs.

```bash
lt sudo server1
lt sudo server1 --since 24h
```

### bans

Show fail2ban activity.

```bash
lt bans server1
lt bans server1 --since 7d
```

### report

Generate full security event report.

```bash
lt report --targets server1 --since 24h
lt report --env prod --since 7d --json
```

## Time Formats

- `2h` - 2 hours ago
- `24h` - 24 hours ago
- `7d` - 7 days ago
- `2024-01-01` - Specific date
- `"2024-01-01 12:00"` - Specific datetime

## Log Sources

Depending on the system:

- `/var/log/auth.log` (Debian/Ubuntu)
- `/var/log/secure` (RHEL/CentOS)
- `journalctl` (systemd systems)

## Examples

```bash
# Check SSH logs from last 2 hours
lt ssh server1

# Check sudo activity for the day
lt sudo server1 --since 24h

# Check fail2ban bans
lt bans server1

# Full report for production
lt report --env prod --since 24h

# JSON output for processing
lt report --targets server1 --json > events.json
```

## Report Contents

The report includes:

- SSH authentication events (success/failure)
- Sudo command execution
- Fail2ban bans/unbans
- Failed login attempts
