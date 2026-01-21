# gvportsentry - Port Scanning and Baselines

Scan open ports and compare against baselines.

## Aliases

- `ports`
- `gvps`

## Usage

```bash
ports <command> [options]
```

## Commands

### scan

Scan ports on target.

```bash
ports scan server1
ports scan 192.168.1.1
```

**For hostnames:** Connects via SSH and lists listening ports
**For IPs:** Scans common ports externally

### baseline save

Save current ports as baseline.

```bash
ports baseline save server1
```

### baseline diff

Compare current ports against baseline.

```bash
ports baseline diff server1
ports baseline diff server1 --json
```

### report

Port report for inventory hosts.

```bash
ports report
ports report --env prod
ports report --json
```

## Common Ports Scanned

External scans check:

- 22 (SSH)
- 25 (SMTP)
- 53 (DNS)
- 80 (HTTP)
- 110 (POP3)
- 143 (IMAP)
- 443 (HTTPS)
- 465 (SMTPS)
- 587 (Submission)
- 993 (IMAPS)
- 995 (POP3S)
- 3306 (MySQL)
- 5432 (PostgreSQL)
- 6379 (Redis)
- 8080 (HTTP-Alt)
- 8443 (HTTPS-Alt)
- 27017 (MongoDB)

## Examples

```bash
# Scan a server's open ports
ports scan server1

# Save as baseline
ports baseline save server1

# Later, check for changes
ports baseline diff server1

# Fleet report
ports report --env prod
```

## Baseline Diff Output

```
NEW ports:
  + 8080 (java)
  + 27017 (mongod)

CLOSED ports:
  - 3000 (node)
```

## Storage

Baselines stored at: `~/.config/gvtools/port-baselines/`

## Security Use Cases

1. **Change detection**: Alert on unexpected ports
2. **Compliance**: Verify only allowed ports are open
3. **Troubleshooting**: Quickly see what's listening
4. **Inventory**: Document service exposure
