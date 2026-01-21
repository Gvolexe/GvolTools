# gvsync - File Synchronization

Rsync wrapper with SSH profile awareness for file/directory synchronization across the fleet.

## Aliases

- `sx`

## Usage

```bash
gvsync <command> [options]
```

## Commands

### push

Push files to remote hosts.

```bash
# Push to a single host
gvsync push ./app /opt/app --host web1.example.com

# Push to all hosts in a role
gvsync push ./config /etc/myapp --role web

# Push with delete (mirror)
gvsync push ./dist /var/www/html --role web --delete

# Dry run first
gvsync push ./app /opt/app --role web --dry-run
```

**Options:**

- `--host`, `-H`: Single host to target
- `--role`, `-r`: Target hosts by role
- `--env`, `-e`: Target hosts by environment
- `--delete`: Delete extraneous files from destination
- `--dry-run`, `-n`: Show what would be transferred
- `--exclude`: Exclude pattern (can be repeated)
- `--include`: Include pattern (can be repeated)
- `--sudo`: Use sudo on remote
- `--checksum`, `-c`: Use checksum instead of mod-time
- `--parallel`, `-p`: Number of parallel syncs (default: 5)

### pull

Pull files from remote hosts.

```bash
# Pull from a single host
gvsync pull /var/log/app.log ./logs/ --host web1.example.com

# Pull from multiple hosts (creates subdirectories)
gvsync pull /etc/nginx/nginx.conf ./configs/ --role web
```

### mirror

Mirror directory (sync with delete).

```bash
# Mirror dist to web root
gvsync mirror ./dist /var/www/html --role web

# Mirror with backup
gvsync mirror ./dist /var/www/html --role web --backup
```

### diff

Show differences between local and remote.

```bash
# Show what would change
gvsync diff ./config /etc/myapp --host web1.example.com

# Compare across role
gvsync diff ./config /etc/myapp --role web
```

## Common Rsync Options

All commands support standard rsync options:

| Option             | Description                   |
| ------------------ | ----------------------------- |
| `--dry-run`, `-n`  | Show what would be done       |
| `--delete`         | Delete files not in source    |
| `--exclude`        | Exclude pattern               |
| `--include`        | Include pattern               |
| `--checksum`, `-c` | Use checksum for comparison   |
| `--compress`, `-z` | Compress during transfer      |
| `--progress`       | Show progress                 |
| `--backup`, `-b`   | Make backups of changed files |

## Examples

```bash
# Deploy static files to web servers
sx push ./dist /var/www/html --role web --delete

# Pull logs from all servers
sx pull /var/log/myapp.log ./logs/ --env prod

# Sync config with preview
sx diff ./nginx.conf /etc/nginx/nginx.conf --role web
sx push ./nginx.conf /etc/nginx/nginx.conf --role web

# Mirror with exclusions
sx mirror ./app /opt/app --role web \
  --exclude "*.pyc" \
  --exclude "__pycache__" \
  --exclude ".git"

# Pull and organize by hostname
sx pull /etc/nginx/nginx.conf ./configs/ --role web
# Creates: ./configs/web1.example.com/nginx.conf, etc.
```

## SSH Profile Integration

gvsync automatically uses SSH profiles from gvsshprofile, so custom ports, keys, and users are respected.

## Exit Codes

- `0`: All syncs succeeded
- `1`: Some syncs failed
- `2`: Error
