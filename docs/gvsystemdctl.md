# gvsystemdctl - Systemd Service Management

Fleet-safe systemd management with rollout controls and validation hooks.

## Aliases

- `svc`

## Usage

```bash
gvsystemdctl <command> [options]
```

## Commands

### status

Show unit status across targets.

```bash
# Check status on a host
gvsystemdctl status nginx --host web1.example.com

# Check across a role
gvsystemdctl status nginx --role web

# Show all units
gvsystemdctl status --role web
```

**Options:**

- `--host`, `-H`: Single host to target
- `--role`, `-r`: Target hosts by role
- `--env`, `-e`: Target hosts by environment
- `--json`, `-j`: Output as JSON

### restart

Restart a unit across targets.

```bash
# Restart on a single host
gvsystemdctl restart nginx --host web1.example.com

# Restart across role with batching
gvsystemdctl restart nginx --role web --batch-size 2 --interval 60

# Restart with validation
gvsystemdctl restart nginx --role web --validate "curl -sf localhost/health"
```

**Options:**

- `--batch-size`, `-b`: Number of hosts per batch (default: 1)
- `--interval`, `-i`: Seconds between batches (default: 30)
- `--validate`, `-v`: Validation command to run after restart
- `--yes`, `-y`: Skip confirmation

### start

Start a unit.

```bash
gvsystemdctl start myapp --role web
```

### stop

Stop a unit.

```bash
gvsystemdctl stop myapp --role web --yes
```

### enable

Enable a unit to start on boot.

```bash
gvsystemdctl enable myapp --role web
```

### disable

Disable a unit from starting on boot.

```bash
gvsystemdctl disable myapp --role web
```

### logs

Show unit logs (wrapper for journalctl).

```bash
gvsystemdctl logs nginx --host web1.example.com --since 1h
gvsystemdctl logs nginx --role web --since 30m --follow
```

### rollout

Perform rolling restart with validation.

```bash
# Rolling restart with health check
gvsystemdctl rollout nginx --role web \
  --batch-size 1 \
  --interval 60 \
  --validate "curl -sf localhost/health"

# Rollout with automatic rollback on failure
gvsystemdctl rollout myapp --role web \
  --batch-size 2 \
  --validate "systemctl is-active myapp" \
  --rollback-on-failure
```

## Safety Features

- **Critical unit protection**: Refuses to stop critical units (sshd, systemd-\*)
- **Batch size limits**: Prevents restarting too many hosts at once
- **Validation hooks**: Run commands to verify service health
- **Dry run mode**: Preview changes before applying

## Examples

```bash
# Check nginx status across web tier
svc status nginx --role web

# Rolling restart with health checks
svc rollout nginx --role web \
  --batch-size 2 \
  --interval 30 \
  --validate "curl -sf localhost:80/health"

# Enable and start a new service
svc enable myapp --role web
svc start myapp --role web

# View recent logs
svc logs nginx --role web --since 1h --priority err
```

## Exit Codes

- `0`: All operations succeeded
- `1`: Some operations failed
- `2`: Validation failed (rollout stopped)
- `3`: Error
