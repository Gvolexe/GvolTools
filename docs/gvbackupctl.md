# gvbackupctl - Backup Configuration and Verification

Configure backups and verify restore integrity using restic.

## Aliases

- `bk`
- `backup`
- `gvbk`

## Usage

```bash
bk <command> [options]
```

## Commands

### init

Initialize backup configuration.

```bash
bk init --backend local --repo /backup --targets server1
bk init --backend s3 --repo s3:bucket/prefix --targets server1 --paths "/etc,/srv"
```

**Options:**

- `--backend`, `-b`: Backup backend (local, s3, ssh)
- `--repo`, `-r`: Repository path or URL
- `--paths`, `-p`: Paths to backup (comma-separated)

### run

Run backup.

```bash
bk run --targets server1
bk run --env prod
```

### verify

Verify backup integrity.

```bash
bk verify --targets server1
bk verify --env prod
```

### status

Show backup status.

```bash
bk status
bk status --json
```

### restore

Restore from backup.

```bash
bk restore server1 --snapshot latest --to /tmp/restore
bk restore server1 --snapshot abc123 --to /restore
```

**Options:**

- `--snapshot`, `-s`: Snapshot ID or "latest"
- `--to`, `-t`: Restore destination path

## Backends

### local

```bash
bk init --backend local --repo /backup/server1 --targets server1
```

### s3

```bash
# Requires AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY
bk init --backend s3 --repo s3:mybucket/backups --targets server1
```

## Default Paths

If `--paths` not specified, backs up:

- `/etc`
- `/home`

## Examples

```bash
# Initialize local backup
bk init --backend local --repo /mnt/backup --paths "/etc,/srv,/var/www" --targets server1

# Run backup
bk run --targets server1

# Verify backup integrity
bk verify --targets server1

# Check backup status
bk status

# Restore to temporary location
bk restore server1 --snapshot latest --to /tmp/restore
```

## Retention Policy

Default retention:

- Keep last 7 daily snapshots
- Keep last 4 weekly snapshots
- Keep last 6 monthly snapshots
