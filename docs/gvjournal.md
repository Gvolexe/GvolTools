# gvjournal - Journald Log Querying

Fetch and filter systemd journal logs across hosts with consistent time/unit/priority filters.

## Aliases

- `jrnl`

## Usage

```bash
gvjournal <command> [options]
```

## Commands

### logs

Fetch journal logs from targets.

```bash
# Last hour from a host
gvjournal logs web1.example.com --since 1h

# Specific unit
gvjournal logs web1.example.com --unit nginx --since 1h

# Filter by priority
gvjournal logs web1.example.com --priority err --since 24h

# From all hosts in a role
gvjournal logs --role web --unit nginx --since 30m
```

**Options:**

- `--host`, `-H`: Single host to query
- `--role`, `-r`: Target hosts by role
- `--env`, `-e`: Target hosts by environment
- `--unit`, `-u`: Systemd unit name
- `--since`, `-s`: Start time (e.g., "1h", "30m", "2024-01-01 00:00")
- `--until`: End time
- `--priority`, `-p`: Minimum priority (emerg, alert, crit, err, warning, notice, info, debug)
- `--lines`, `-n`: Number of lines (default: 100)
- `--follow`, `-f`: Follow log output (single host only)
- `--json`, `-j`: Output as JSON
- `--grep`, `-g`: Filter log messages by pattern

### units

List available systemd units on hosts.

```bash
# List units on a host
gvjournal units web1.example.com

# Filter by type
gvjournal units web1.example.com --type service
```

### errors

Show only error-level logs.

```bash
# Recent errors
gvjournal errors --role web --since 1h

# Errors for a specific unit
gvjournal errors web1.example.com --unit nginx
```

## Priority Levels

| Level     | Value | Description                      |
| --------- | ----- | -------------------------------- |
| `emerg`   | 0     | System is unusable               |
| `alert`   | 1     | Action must be taken immediately |
| `crit`    | 2     | Critical conditions              |
| `err`     | 3     | Error conditions                 |
| `warning` | 4     | Warning conditions               |
| `notice`  | 5     | Normal but significant           |
| `info`    | 6     | Informational                    |
| `debug`   | 7     | Debug-level messages             |

## Examples

```bash
# Check nginx errors across web tier
jrnl logs --role web --unit nginx --priority err --since 1h

# Follow logs in real-time
jrnl logs web1.example.com --unit myapp --follow

# Search for specific pattern
jrnl logs --role web --since 24h --grep "connection refused"

# Get structured JSON output
jrnl logs web1.example.com --since 1h --json | jq '.[] | select(.priority <= 3)'

# Kernel messages only
jrnl logs web1.example.com --unit kernel --since 1h
```

## Exit Codes

- `0`: Success
- `1`: Some hosts failed to respond
- `2`: Error
