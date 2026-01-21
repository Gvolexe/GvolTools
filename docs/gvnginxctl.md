# gvnginxctl - Nginx Configuration Management

Fleet-safe nginx config testing, reloads, and vhost management.

## Aliases

- `ngx`
- `nx`

## Usage

```bash
gvnginxctl <command> [options]
```

## Commands

### status

Show nginx status across targets.

```bash
# Status on a host
gvnginxctl status --host web1.example.com

# Status across role
gvnginxctl status --role web

# JSON output
gvnginxctl status --role web --json
```

**Options:**

- `--host`, `-H`: Single host to check
- `--role`, `-r`: Target hosts by role
- `--env`, `-e`: Target hosts by environment
- `--json`, `-j`: Output as JSON

### test

Test nginx configuration.

```bash
# Test on a host
gvnginxctl test --host web1.example.com

# Test across role
gvnginxctl test --role web

# Test specific config file
gvnginxctl test --host web1 --config /etc/nginx/sites-available/mysite
```

### reload

Reload nginx configuration.

```bash
# Reload on a host
gvnginxctl reload --host web1.example.com

# Reload across role (tests first)
gvnginxctl reload --role web

# Force reload without test
gvnginxctl reload --role web --force
```

### restart

Restart nginx service.

```bash
# Restart on a host
gvnginxctl restart --host web1.example.com --yes

# Rolling restart across role
gvnginxctl restart --role web \
  --batch-size 1 \
  --interval 30 \
  --yes
```

### logs

Show nginx logs.

```bash
# Access logs
gvnginxctl logs --host web1 --type access --lines 100

# Error logs
gvnginxctl logs --host web1 --type error --since 1h

# Follow logs
gvnginxctl logs --host web1 --type error --follow
```

**Options:**

- `--type`, `-t`: Log type (access, error)
- `--lines`, `-n`: Number of lines
- `--since`, `-s`: Time range
- `--follow`, `-f`: Follow log output

### site

Manage nginx sites/vhosts.

```bash
# List sites
gvnginxctl site list --host web1

# Enable site
gvnginxctl site enable mysite --host web1

# Disable site
gvnginxctl site disable mysite --host web1

# Show site config
gvnginxctl site show mysite --host web1
```

## Safety Features

- **Config testing**: Always tests before reload
- **Rollback support**: Keeps backup of working config
- **Batch operations**: Rolling restarts across fleet
- **Validation hooks**: Custom health checks

## Examples

```bash
# Check nginx status across web tier
ngx status --role web

# Test config on all web servers
ngx test --role web

# Safe reload with testing
ngx reload --role web

# Rolling restart
ngx restart --role web --batch-size 1 --interval 60 --yes

# Enable a site
ngx site enable example.com --host web1
ngx reload --host web1

# View recent errors
ngx logs --role web --type error --since 1h

# Full status report
ngx status --role web --json | jq '.[] | {host: .host, status: .status, sites: .sites_enabled}'
```

## Configuration Paths

Automatically detects configuration paths:

| Distribution  | Config Path                   | Sites Path                  |
| ------------- | ----------------------------- | --------------------------- |
| Debian/Ubuntu | `/etc/nginx/nginx.conf`       | `/etc/nginx/sites-enabled/` |
| RHEL/CentOS   | `/etc/nginx/nginx.conf`       | `/etc/nginx/conf.d/`        |
| Custom        | Detected from running process | -                           |

## Exit Codes

- `0`: All operations succeeded
- `1`: Some operations failed
- `2`: Configuration test failed
- `3`: Error
