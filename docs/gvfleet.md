# gvfleet - Host Inventory Management

Manage your infrastructure inventory with powerful selection capabilities.

## Aliases

- `fleet`
- `f`
- `gvf`

## Usage

```bash
fleet <command> [options]
```

## Commands

### add

Add a host to the inventory.

```bash
fleet add myserver --hostname server.example.com --env production --role web
fleet add db1 --hostname db.example.com --env prod --role database --owner gvol
```

**Options:**

- `--hostname`, `-H`: Actual hostname/IP
- `--env`, `-e`: Environment (prod, staging, dev)
- `--role`, `-r`: Server role (web, db, etc.)
- `--owner`, `-o`: Owner/admin name
- `--tags`, `-t`: Comma-separated tags
- `--group`, `-g`: Host group
- `--domain`, `-d`: Domain name

### del

Remove a host from inventory.

```bash
fleet del myserver
fleet del myserver --yes
```

### list

List hosts with filtering.

```bash
fleet list
fleet list --env prod
fleet list --role web --json
fleet list --tag critical
```

### show

Show detailed host information.

```bash
fleet show myserver
fleet show myserver --json
```

### ssh

SSH to a host directly.

```bash
fleet ssh myserver
fleet ssh myserver -u admin
```

### export

Export inventory.

```bash
fleet export > backup.json
fleet export --format yaml > hosts.yaml
```

### import

Import hosts.

```bash
fleet import --file hosts.json
fleet import --file hosts.yaml
```

## Configuration

Inventory is stored at `~/.config/gvtools/inventory.json`.

## Examples

```bash
# Add production web server
fleet add web1 -H 10.0.0.1 -e prod -r web -t "critical,https"

# List all production servers
fleet list --env prod

# Export inventory for backup
fleet export > inventory-backup.json

# SSH to a server
fleet ssh web1
```
