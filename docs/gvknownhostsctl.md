# gvknownhostsctl - SSH known_hosts Management

Safely manage the ~/.ssh/known_hosts file.

## Aliases

- `kh`
- `gvkh`

## Usage

```bash
kh <command> [options]
```

## Commands

### verify

Verify known hosts entries.

```bash
kh verify
kh verify --json
```

**Checks:**

- Entry validity
- Duplicate detection
- Key type identification
- Connection status

### add

Add a host's key to known_hosts.

```bash
kh add server.example.com
kh add server.example.com --port 2222
kh add server.example.com --yes
```

### rm

Remove a host from known_hosts.

```bash
kh rm server.example.com
kh rm oldserver.example.com --yes
```

### dedupe

Remove duplicate entries.

```bash
kh dedupe
kh dedupe --dry-run
kh dedupe --yes
```

### rename

Rename a host in known_hosts.

```bash
kh rename oldname.example.com newname.example.com
```

## Examples

```bash
# Verify all entries
kh verify

# Add a new server
kh add newserver.example.com

# Remove old server entry
kh rm decommissioned.example.com --yes

# Clean up duplicates
kh dedupe --dry-run

# Actually remove duplicates
kh dedupe --yes
```

## File Location

known_hosts file: `~/.ssh/known_hosts`

## Safety Features

- Creates backups before modifications
- Dry-run mode for previewing changes
- Validates host keys before adding
