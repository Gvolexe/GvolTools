# gvhealth - Host and Service Health Checks

Run host-level and service-level health checks across your fleet, aggregate results, and provide consistent OK/WARN/FAIL output.

## Aliases

- `health`
- `hl`

## Usage

```bash
gvhealth <command> [options]
```

## Commands

### check

Run health checks on targets.

```bash
# Check a single host
gvhealth check web1.example.com

# Check all hosts with a role
gvhealth check --role web

# Check with specific specs
gvhealth check --role web --spec production

# Output as JSON
gvhealth check --role web --json
```

**Options:**

- `--host`, `-H`: Single host to check
- `--role`, `-r`: Target hosts by role
- `--env`, `-e`: Target hosts by environment
- `--spec`, `-s`: Health spec to use
- `--json`, `-j`: Output as JSON
- `--parallel`, `-p`: Number of parallel checks (default: 10)

### spec

Manage health specifications.

```bash
# List available specs
gvhealth spec list

# Show spec details
gvhealth spec show production

# Add a custom spec
gvhealth spec add myspec --checks "disk,memory,cpu"

# Delete a spec
gvhealth spec del myspec
```

### status

Show overall fleet health status.

```bash
# Summary of all hosts
gvhealth status

# Filter by environment
gvhealth status --env prod

# JSON output
gvhealth status --json
```

## Health Checks

Built-in checks include:

| Check    | Description      | Thresholds             |
| -------- | ---------------- | ---------------------- |
| `disk`   | Disk usage       | WARN: 80%, FAIL: 90%   |
| `memory` | Memory usage     | WARN: 85%, FAIL: 95%   |
| `cpu`    | CPU load         | WARN: 80%, FAIL: 95%   |
| `swap`   | Swap usage       | WARN: 50%, FAIL: 80%   |
| `uptime` | System uptime    | WARN: < 1h, FAIL: < 5m |
| `zombie` | Zombie processes | WARN: > 0              |

## Examples

```bash
# Quick health check of production web servers
health check --env prod --role web

# Detailed JSON report
health check --role db --json | jq '.hosts[] | select(.status != "OK")'

# Check specific host with all details
hl check web1.example.com --verbose
```

## Exit Codes

- `0`: All checks passed (OK)
- `1`: Some checks have warnings (WARN)
- `2`: Some checks failed (FAIL)
- `3`: Error running checks
