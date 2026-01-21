# gvdeploy - Command and Script Execution

Execute commands and scripts across target sets with concurrency, per-host logs, and clear exit statuses.

## Aliases

- `dep`

## Usage

```bash
gvdeploy <command> [options]
```

## Commands

### cmd

Execute a command across targets.

```bash
# Run command on a host
gvdeploy cmd "uptime" --host web1.example.com

# Run on all hosts in a role
gvdeploy cmd "systemctl restart nginx" --role web

# Run with sudo
gvdeploy cmd "apt update" --role web --sudo

# Parallel execution
gvdeploy cmd "df -h" --env prod --parallel 20
```

**Options:**

- `--host`, `-H`: Single host to target
- `--role`, `-r`: Target hosts by role
- `--env`, `-e`: Target hosts by environment
- `--sudo`, `-s`: Run with sudo
- `--parallel`, `-p`: Number of parallel executions (default: 10)
- `--timeout`, `-t`: Command timeout in seconds (default: 300)
- `--json`, `-j`: Output as JSON
- `--yes`, `-y`: Skip confirmation

### script

Execute a script across targets.

```bash
# Run local script on remote hosts
gvdeploy script ./deploy.sh --role web

# Run with arguments
gvdeploy script ./setup.sh --role web --args "--env prod --force"

# Inline script
gvdeploy script - --role web <<EOF
#!/bin/bash
echo "Hello from \$(hostname)"
EOF
```

**Options:**

- `--script`, `-s`: Path to script file (use `-` for stdin)
- `--args`, `-a`: Arguments to pass to script
- `--interpreter`, `-i`: Script interpreter (default: /bin/bash)
- All targeting options from `cmd`

### history

Show deployment history.

```bash
# Recent deployments
gvdeploy history

# Filter by date
gvdeploy history --since "2024-01-01"

# Show specific deployment details
gvdeploy history --id abc123
```

### rollback

Rollback to previous state (if supported).

```bash
gvdeploy rollback --id abc123
```

## Examples

```bash
# Quick command across web tier
dep cmd "systemctl status nginx" --role web

# Deploy with confirmation
dep script ./deploy.sh --role web --yes

# Check disk space everywhere
dep cmd "df -h /" --env prod --json | jq '.[] | {host: .host, output: .stdout}'

# Run apt upgrade with logging
dep cmd "apt update && apt upgrade -y" --role web --sudo --timeout 600

# Restart services in batches
for batch in web1 web2 web3; do
  dep cmd "systemctl restart myapp" --host $batch
  sleep 30
done
```

## Output Format

Each execution returns:

```json
{
  "host": "web1.example.com",
  "exit_code": 0,
  "stdout": "...",
  "stderr": "...",
  "duration_ms": 1234,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

## Exit Codes

- `0`: All commands succeeded
- `1`: Some commands failed
- `2`: Error setting up execution
