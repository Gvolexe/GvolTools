# gvfirewallctl - Firewall Baseline Management

Apply and manage firewall baselines across your infrastructure.

## Aliases

- `fw`
- `gvfw`

## Usage

```bash
fw <command> [options]
```

## Commands

### apply

Apply a firewall baseline.

```bash
fw apply minimal --targets server1
fw apply web --env prod
fw apply bastion --targets jump-host
```

**Baselines:**

- `minimal`: SSH only (port 22)
- `web`: SSH + HTTP/HTTPS (22, 80, 443)
- `db`: SSH + MySQL (22, 3306)
- `bastion`: SSH only, logging enabled

**Options:**

- All target selection options

### diff

Show differences between current and baseline.

```bash
fw diff minimal --targets server1
fw diff web --env prod
```

### status

Show current firewall status.

```bash
fw status server1
fw status --targets server1,server2
```

### lock

Lock down firewall to baseline.

```bash
fw lock --targets server1
fw lock --env prod --dry-run
```

## Baseline Definitions

### minimal

```
SSH (22/tcp): ALLOW
Default: DENY incoming
```

### web

```
SSH (22/tcp): ALLOW
HTTP (80/tcp): ALLOW
HTTPS (443/tcp): ALLOW
Default: DENY incoming
```

### db

```
SSH (22/tcp): ALLOW
MySQL (3306/tcp): ALLOW from private networks
Default: DENY incoming
```

### bastion

```
SSH (22/tcp): ALLOW
Logging: Enabled
Rate limiting: Enabled
Default: DENY incoming
```

## Examples

```bash
# Apply web baseline to production
fw apply web --env prod --dry-run
fw apply web --env prod

# Check status
fw status web1

# Show what would change
fw diff minimal --targets db1

# Lock down a server
fw lock --targets compromised-server
```

## Backend

Uses UFW (Uncomplicated Firewall) on Ubuntu/Debian.
Firewalld support planned.
